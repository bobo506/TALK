#!/usr/bin/env python3
"""Human-only unified diagnostic export (contract 276).

This module is intentionally independent from the two existing log endpoints:
it performs **one** bounded scan of the configured source, keeps the requested
half-open time window, projects every selected record through the same strict
274 allow-list used by the detail endpoint, and serializes one meta line plus
one JSON object per physical line.

Only the controlled source, the 274 scanner and the existing DTO projection are
used.  Raw ``extra`` (except ``extra.transition``), top-level free ``message``,
prompt/argv/env, source paths and credentials never enter the output.
"""

from __future__ import annotations

import heapq
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from bridges.runtime_diagnostics_timeline import (
    FINAL_STATUSES,
    STARTED,
    TRANSITION_STATUSES,
    validate_operation_id,
)
from server.runtime_diagnostics_query import (
    ProjectionFailure,
    ScanLimits,
    Source,
    parse_recorded_at,
    project_detail,
    projection_failed_error,
    record_sort_key,
    scan_model,
    scan_source,
)

SCHEMA = "talk-diagnostics-export-1"
MAX_EXPORT_RECORDS = 10000
MAX_EXPORT_BYTES = 16 * 1024 * 1024
MAX_META_BYTES = 64 * 1024
MAX_RANGE = timedelta(days=31)
MAX_QUERY_TIME_CHARS = 128

_REASON_ORDER = (
    "scan_incomplete",
    "source_changed",
    "malformed_records",
    "unavailable_records",
    "projection_failed",
    "record_limit",
    "byte_limit",
    "time_limit",
    "duplicate_log_id",
)
_TRUNCATION_REASONS = frozenset(
    {"scan_incomplete", "record_limit", "byte_limit", "time_limit"}
)
_STATE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
#: The export only accepts known coarse phase identifiers.  Unknown persisted
#: values become ``null`` instead of being echoed as free text.
_EXPORT_PHASES = frozenset(
    {"start", "stop", "serve", "queue", "task", "task_preflight", "bridge", "report"}
)
_TRANSITION_KEYS = frozenset(
    {
        "operation_id",
        "status",
        "from_state",
        "to_state",
        "started_at",
        "finished_at",
        "duration_ms",
        "attempt",
    }
)


def utc_text(value: datetime) -> str:
    text = value.astimezone(timezone.utc).isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def export_filename(since: datetime, until: datetime) -> str:
    def stamp(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    return f"talk-diagnostics_{stamp(since)}_{stamp(until)}.jsonl"


def parse_export_time(value: str) -> datetime:
    """Parse one explicit, timezone-aware ISO-8601 bound (no local fallback)."""
    if not isinstance(value, str) or not value or len(value) > MAX_QUERY_TIME_CHARS:
        raise ValueError("invalid time")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    try:
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid time") from exc


def validate_export_window(since: datetime, until: datetime) -> None:
    if since >= until or until - since > MAX_RANGE:
        raise ValueError("invalid range")


def _json_line(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _bounded_state(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProjectionFailure("transition")
    text = value.strip()
    if not _STATE_RE.fullmatch(text):
        raise ProjectionFailure("transition")
    return text


def _bounded_duration(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectionFailure("transition")
    if isinstance(value, float) and not math.isfinite(value):
        raise ProjectionFailure("transition")
    if value < 0:
        raise ProjectionFailure("transition")
    return value


def _bounded_attempt(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectionFailure("transition")
    if value < 1:
        raise ProjectionFailure("transition")
    return value


def _transition(value: Any) -> dict[str, Any] | None:
    """Strictly project only ``extra.transition``; never any other extra key."""
    if not isinstance(value, dict):
        return None
    raw = value.get("transition")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProjectionFailure("transition")
    if set(raw) != _TRANSITION_KEYS:
        raise ProjectionFailure("transition")
    operation_id = validate_operation_id(raw.get("operation_id"))
    if operation_id is None:
        raise ProjectionFailure("transition")
    status = raw.get("status")
    if status not in TRANSITION_STATUSES:
        raise ProjectionFailure("transition")
    started = parse_recorded_at(raw.get("started_at"))
    if started is None:
        raise ProjectionFailure("transition")
    finished_at = raw.get("finished_at")
    finished = None if finished_at is None else parse_recorded_at(finished_at)
    if finished_at is not None and finished is None:
        raise ProjectionFailure("transition")
    duration = _bounded_duration(raw.get("duration_ms"))
    attempt = _bounded_attempt(raw.get("attempt"))
    if status == STARTED:
        if finished is not None or duration is not None:
            raise ProjectionFailure("transition")
    else:
        if status in FINAL_STATUSES and (finished is None or duration is None):
            raise ProjectionFailure("transition")
    return {
        "operation_id": operation_id,
        "status": status,
        "from_state": _bounded_state(raw.get("from_state")),
        "to_state": _bounded_state(raw.get("to_state")),
        "started_at": utc_text(started),
        "finished_at": utc_text(finished) if finished is not None else None,
        "duration_ms": duration,
        "attempt": attempt,
    }


def _phase(value: Any) -> str | None:
    """Return only a known bounded phase identifier; never free-form text."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if text in _EXPORT_PHASES else None


def _project_event(record: dict[str, Any], scope: tuple[str, str]) -> dict[str, Any]:
    detail = project_detail(record, scope)
    event: dict[str, Any] = {"kind": "event"}
    event.update(detail.model_dump())
    event["phase"] = _phase(record.get("phase"))
    event["transition"] = _transition(record.get("extra"))
    return event


def _reason_list(reasons: set[str]) -> list[str]:
    return [reason for reason in _REASON_ORDER if reason in reasons]


def _meta(
    *,
    project_id: str,
    member_id: str,
    since: datetime,
    until: datetime,
    generated_at: datetime,
    record_count: int,
    reasons: list[str],
    outcome: Any,
) -> dict[str, Any]:
    scan = scan_model(outcome).model_dump()
    complete = bool(outcome.complete) and not reasons
    truncated = bool(set(reasons) & _TRUNCATION_REASONS)
    return {
        "kind": "meta",
        "schema": SCHEMA,
        "scope": {"project_id": project_id, "member_id": member_id},
        "query": {"since": utc_text(since), "until": utc_text(until)},
        "generated_at": utc_text(generated_at),
        "record_count": record_count,
        "complete": complete,
        "truncated": truncated,
        "reasons": reasons,
        "scan": scan,
    }


class _MaxRecord:
    """Reverse-order heap item keeping the earliest ``(recorded_at, log_id)``."""

    __slots__ = ("key", "sequence", "record")

    def __init__(self, key: tuple[datetime, str], sequence: int, record: dict[str, Any]):
        self.key = key
        self.sequence = sequence
        self.record = record

    def __lt__(self, other: "_MaxRecord") -> bool:
        return (self.key, self.sequence) > (other.key, other.sequence)


def _collector(
    *,
    project_id: str,
    member_id: str,
    since: datetime,
    until: datetime,
    max_records: int,
) -> tuple[dict[str, int], list[_MaxRecord], Any]:
    counter = {"matches": 0, "sequence": 0}
    heap: list[_MaxRecord] = []

    def visit(record: dict[str, Any]) -> None:
        if (
            record.get("project_id") != project_id
            or record.get("member_id") != member_id
        ):
            return
        key = record_sort_key(record)
        if key is None:
            return
        if key[0] < since or key[0] >= until:
            return
        counter["matches"] += 1
        counter["sequence"] += 1
        item = _MaxRecord(key, counter["sequence"], record)
        if max_records <= 0:
            return
        if len(heap) < max_records:
            heapq.heappush(heap, item)
            return
        if item.key < heap[0].key:
            heapq.heapreplace(heap, item)

    return counter, heap, visit


def _meta_reserve(max_bytes: int) -> int:
    # Small test budgets still need a realistic meta reservation; the real
    # contract cap reserves the full 64 KiB.
    return min(MAX_META_BYTES, max(512, max_bytes // 16))


def build_export(
    source: Source,
    *,
    project_id: str,
    member_id: str,
    since: datetime,
    until: datetime,
    generated_at: datetime | None = None,
    limits: ScanLimits | None = None,
    max_records: int = MAX_EXPORT_RECORDS,
    max_bytes: int = MAX_EXPORT_BYTES,
) -> bytes:
    """Build one bounded NDJSON export from exactly one logical source scan."""
    limits = limits or ScanLimits()
    max_records = max(0, int(max_records))
    max_bytes = max(1, int(max_bytes))
    if since >= until or until - since > MAX_RANGE:
        raise ValueError("invalid range")
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    started = time.monotonic()
    deadline = started + max(0.0, float(limits.max_seconds))
    counter, heap, visit = _collector(
        project_id=project_id,
        member_id=member_id,
        since=since,
        until=until,
        max_records=max_records,
    )
    outcome = scan_source(source, limits=limits, visitor=visit)
    scan_elapsed = time.monotonic() - started
    timed_out = time.monotonic() >= deadline

    reasons: set[str] = set()
    if not outcome.complete:
        reasons.add("scan_incomplete")
    if outcome.source_changed:
        reasons.add("source_changed")
    if outcome.malformed_lines:
        reasons.add("malformed_records")
    if outcome.unavailable_sources or outcome.availability_failed:
        reasons.add("unavailable_records")
    if outcome.truncated and (
        scan_elapsed >= max(0.0, float(limits.max_seconds)) - 0.02
    ):
        timed_out = True
    if timed_out:
        reasons.add("time_limit")

    selected = sorted(heap, key=lambda item: (item.key, item.sequence))
    log_ids: set[str] = set()
    for item in selected:
        log_id = item.key[1]
        if log_id in log_ids:
            reasons.add("duplicate_log_id")
        else:
            log_ids.add(log_id)

    if counter["matches"] > max_records:
        reasons.add("record_limit")

    event_reserve = _meta_reserve(max_bytes)
    event_cap = max(0, max_bytes - event_reserve)
    event_bytes = 0
    lines: list[bytes] = []
    projection_failures = 0
    byte_limited = False
    for item in selected:
        if time.monotonic() >= deadline:
            reasons.add("time_limit")
            timed_out = True
            break
        try:
            event = _project_event(item.record, (project_id, member_id))
            line = _json_line(event)
        except Exception:
            projection_failures += 1
            continue
        if event_bytes + len(line) > event_cap:
            byte_limited = True
            break
        lines.append(line)
        event_bytes += len(line)

    if projection_failures:
        reasons.add("projection_failed")
    if byte_limited:
        reasons.add("byte_limit")

    # Include the last projection/serialization and ordering work in the budget,
    # even when no further iteration would perform another deadline check.
    if time.monotonic() >= deadline:
        reasons.add("time_limit")

    events_body = b"".join(lines)

    while True:
        if time.monotonic() >= deadline:
            reasons.add("time_limit")
        meta = _meta(
            project_id=project_id,
            member_id=member_id,
            since=since,
            until=until,
            generated_at=generated_at,
            record_count=len(lines),
            reasons=_reason_list(reasons),
            outcome=outcome,
        )
        meta_line = _json_line(meta)
        if len(meta_line) > MAX_META_BYTES:
            raise projection_failed_error()
        if len(meta_line) + event_bytes <= max_bytes:
            break
        if not lines:
            raise projection_failed_error()
        removed = lines.pop()
        event_bytes -= len(removed)
        events_body = events_body[:-len(removed)]
        reasons.add("byte_limit")
    # If construction of the meta itself crossed the deadline, regenerate its
    # flags before returning. Do not restart serialization of all event records.
    if "time_limit" not in reasons and time.monotonic() >= deadline:
        reasons.add("time_limit")
        return build_timeout_result(meta, events_body, max_bytes)
    return meta_line + events_body


def build_timeout_result(meta: dict[str, Any], events_body: bytes, max_bytes: int) -> bytes:
    meta["complete"] = False
    meta["truncated"] = True
    meta["reasons"] = _reason_list(set(meta["reasons"]) | {"time_limit"})
    # The normal builder reserved ample room for flags. Fail closed if a custom
    # tiny budget cannot accommodate the updated meta without dropping records.
    line = _json_line(meta)
    if len(line) > MAX_META_BYTES or len(line) + len(events_body) > max_bytes:
        raise projection_failed_error()
    return line + events_body


__all__ = [
    "SCHEMA",
    "MAX_EXPORT_RECORDS",
    "MAX_EXPORT_BYTES",
    "MAX_META_BYTES",
    "MAX_RANGE",
    "build_export",
    "export_filename",
    "parse_export_time",
    "utc_text",
    "validate_export_window",
]
