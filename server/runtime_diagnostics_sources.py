"""Source configuration and provider lifecycle for the runtime log API.

Sources come only from ``CONFIG["runtime_diagnostics"]["sources"]``.  There is
no environment fallback and no default ``logs/runtime`` directory.  The default
provider and the cursor signing secret are process-lifetime singletons; tests
can inject a replacement provider through the FastAPI dependency.
"""

from __future__ import annotations

import base64
import hashlib
import heapq
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from server.db import CONFIG
from server.runtime_diagnostics_models import RuntimeLogDetail, RuntimeLogPage
from server.runtime_diagnostics_query import (
    DEFAULT_PAGE_LIMIT,
    ProjectionFailure,
    QuerySpec,
    RuntimeDiagnosticsError,
    ScanLimits,
    Source,
    detail_model,
    filter_hash,
    page_model,
    parse_recorded_at,
    project_detail,
    project_summary,
    projection_failed_error,
    record_sort_key,
    scan_incomplete_error,
    scan_source,
    scope_hash,
    unavailable_error,
)

_SOURCE_KEYS = frozenset({"project_id", "member_id", "root"})
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_CURSOR_TTL_SECONDS = 600.0
_CURSOR_MAX_CHARS = 8192
_DEFAULT_LOCK = threading.RLock()
_DEFAULT_PROVIDER: "RuntimeDiagnosticsProvider | None" = None
_DEFAULT_CODEC: "CursorCodec | None" = None


class _SourceConfigError(ValueError):
    pass


class CursorCodec:
    """Signed, opaque pagination token bound to one server generation."""

    version = 1

    def __init__(
        self,
        *,
        secret: bytes | None = None,
        epoch: str | None = None,
        ttl_seconds: float = _CURSOR_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._secret = secret if secret is not None else secrets.token_bytes(32)
        self.epoch = epoch or secrets.token_hex(16)
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock or _default_clock

    def _now(self) -> datetime:
        return _as_utc(self._clock())

    def encode(self, payload: dict[str, Any]) -> str:
        now = self._now()
        body = dict(payload)
        body["v"] = self.version
        body["epoch"] = self.epoch
        body["exp"] = int(now.timestamp() + self.ttl_seconds)
        raw = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        signature = hmac.new(self._secret, raw, hashlib.sha256).digest()
        return _b64(raw) + "." + _b64(signature)

    def decode(self, token: str) -> dict[str, Any]:
        if (
            not isinstance(token, str)
            or not token
            or len(token) > _CURSOR_MAX_CHARS
            or _CONTROL_RE.search(token)
        ):
            raise _invalid_cursor()
        parts = token.split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise _invalid_cursor()
        try:
            raw = _unb64(parts[0])
            supplied_signature = _unb64(parts[1])
            body = json.loads(raw)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            raise _invalid_cursor()
        if not isinstance(body, dict) or body.get("v") != self.version:
            raise _invalid_cursor()
        # The epoch is public and non-secret.  Comparing it before signature
        # verification lets a process restart return the contract's 409 rather
        # than 422, without trusting any other field from an old token.
        if body.get("epoch") != self.epoch:
            raise _stale_cursor()
        expected = hmac.new(self._secret, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, supplied_signature):
            raise _invalid_cursor()
        exp = body.get("exp")
        if isinstance(exp, bool) or not isinstance(exp, int):
            raise _invalid_cursor()
        if self._now().timestamp() > exp:
            raise _stale_cursor()
        return body


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return datetime.now(timezone.utc)
    return value.astimezone(timezone.utc)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise ValueError("invalid base64url")
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def _invalid_cursor() -> RuntimeDiagnosticsError:
    return RuntimeDiagnosticsError("invalid_cursor", 422)


def _stale_cursor() -> RuntimeDiagnosticsError:
    return RuntimeDiagnosticsError("stale_cursor", 409)


def _log_not_found() -> RuntimeDiagnosticsError:
    return RuntimeDiagnosticsError("log_not_found", 404)


def _log_ref_conflict() -> RuntimeDiagnosticsError:
    return RuntimeDiagnosticsError("log_ref_conflict", 409)


def _conflicting_filters() -> RuntimeDiagnosticsError:
    return RuntimeDiagnosticsError("conflicting_filters", 422)


def _source_revision(sources: Iterable[Source]) -> str:
    payload = [
        [source.project_id, source.member_id, str(source.root)]
        for source in sorted(
            sources, key=lambda item: (item.project_id, item.member_id, str(item.root))
        )
    ]
    data = json.dumps(
        {"schema": "runtime-diagnostics-sources-1", "sources": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _parse_sources(config: Any) -> list[Source]:
    if not isinstance(config, dict):
        raise _SourceConfigError("config")
    section = config.get("runtime_diagnostics", {})
    if section is None:
        section = {}
    if not isinstance(section, dict):
        raise _SourceConfigError("section")
    raw_sources = section.get("sources", [])
    if raw_sources is None or not isinstance(raw_sources, list):
        raise _SourceConfigError("sources")
    parsed: list[Source] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_sources:
        if not isinstance(item, dict) or set(item) != _SOURCE_KEYS:
            raise _SourceConfigError("entry")
        project_id = item.get("project_id")
        member_id = item.get("member_id")
        root_raw = item.get("root")
        if (
            not isinstance(project_id, str)
            or not project_id
            or len(project_id) > 200
            or _CONTROL_RE.search(project_id)
        ):
            raise _SourceConfigError("project_id")
        if (
            not isinstance(member_id, str)
            or not member_id
            or len(member_id) > 200
            or _CONTROL_RE.search(member_id)
        ):
            raise _SourceConfigError("member_id")
        if (
            not isinstance(root_raw, str)
            or not root_raw
            or "\x00" in root_raw
            or _CONTROL_RE.search(root_raw)
        ):
            raise _SourceConfigError("root")
        if root_raw.startswith("//") or root_raw.startswith("\\\\"):
            # Same-machine first release: a UNC source is not accepted.
            raise _SourceConfigError("root")
        try:
            root_path = Path(root_raw)
            if not root_path.is_absolute():
                raise _SourceConfigError("root")
        except (OSError, ValueError) as exc:
            raise _SourceConfigError("root") from exc
        key = (project_id, member_id)
        if key in seen:
            raise _SourceConfigError("duplicate")
        seen.add(key)
        parsed.append(
            Source(
                project_id=project_id,
                member_id=member_id,
                root=Path(os.path.abspath(root_raw)),
            )
        )
    return parsed


class _MatchCollector:
    """Bounded record collector used as the scanner's per-record visitor."""

    def __init__(
        self,
        *,
        project_id: str,
        member_id: str,
        query: QuerySpec,
        cursor_payload: dict[str, Any] | None,
    ) -> None:
        self.project_id = project_id
        self.member_id = member_id
        self.query = query
        self.cursor_payload = cursor_payload
        self.heap: list[tuple[datetime, str, int, dict[str, Any]]] = []
        self.ref_matches: list[dict[str, Any]] = []
        self._sequence = 0
        self._last_key: tuple[datetime, str] | None = None
        if cursor_payload is not None:
            last_at = parse_recorded_at(cursor_payload.get("last_recorded_at"))
            last_id = cursor_payload.get("last_log_id")
            if last_at is None or not isinstance(last_id, str):
                raise _invalid_cursor()
            self._last_key = (last_at, last_id)

    def visit(self, record: dict[str, Any]) -> None:
        if (
            record.get("project_id") != self.project_id
            or record.get("member_id") != self.member_id
        ):
            return
        if self.query.exact_ref:
            if record.get("log_id") == self.query.ref and len(self.ref_matches) < 2:
                self.ref_matches.append(record)
            return
        key = record_sort_key(record)
        if key is None:
            return
        if self.query.since is not None and key[0] < self.query.since:
            return
        if self.query.until is not None and key[0] > self.query.until:
            return
        if self.query.severity is not None and record.get("severity") not in self.query.severity:
            return
        if self.query.instance_id is not None and record.get("instance_id") != self.query.instance_id:
            return
        if self.query.launch_id is not None and record.get("launch_id") != self.query.launch_id:
            return
        if self.query.event is not None and record.get("event") != self.query.event:
            return
        if self.query.stage is not None and record.get("stage") != self.query.stage:
            return
        if self.query.task_id is not None:
            record_task = record.get("task_id")
            if isinstance(record_task, bool):
                return
            try:
                if int(record_task) != self.query.task_id:
                    return
            except (TypeError, ValueError):
                return
        if self._last_key is not None and key >= self._last_key:
            return
        self._sequence += 1
        item = (key[0], key[1], self._sequence, record)
        if len(self.heap) < self.query.limit + 1:
            heapq.heappush(self.heap, item)
        elif (key[0], key[1]) > (self.heap[0][0], self.heap[0][1]):
            heapq.heapreplace(self.heap, item)

    def ordered(self) -> list[tuple[datetime, str, dict[str, Any]]]:
        return [
            (item[0], item[1], item[3])
            for item in sorted(
                self.heap, key=lambda entry: (entry[0], entry[1]), reverse=True
            )
        ]


class RuntimeDiagnosticsProvider:
    """Stable, replaceable provider for the two read-only log endpoints."""

    def __init__(
        self,
        sources: Iterable[Source],
        *,
        config_error: str | None = None,
        scan_limits: ScanLimits | None = None,
        cursor_codec: CursorCodec | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.sources = tuple(sources)
        self._by_scope = {
            (source.project_id, source.member_id): source for source in self.sources
        }
        self._config_error = config_error
        self._scan_limits = scan_limits or ScanLimits()
        self.cursor_codec = cursor_codec or get_default_codec()
        self._clock = clock or _default_clock
        self.source_revision = _source_revision(self.sources)

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        scan_limits: ScanLimits | None = None,
        cursor_codec: CursorCodec | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> "RuntimeDiagnosticsProvider":
        try:
            sources = _parse_sources(config)
        except Exception:
            # Invalid configuration is a stable 503, never a startup traceback
            # or a fallback to a default directory.
            return cls(
                [],
                config_error="invalid_source_config",
                scan_limits=scan_limits,
                cursor_codec=cursor_codec,
                clock=clock,
            )
        return cls(
            sources,
            scan_limits=scan_limits,
            cursor_codec=cursor_codec,
            clock=clock,
        )

    def _now(self) -> datetime:
        return _as_utc(self._clock())

    def now(self) -> datetime:
        """Current provider clock, used to freeze default query windows."""
        return self._now()

    def source_for(self, project_id: str, member_id: str) -> Source | None:
        if self._config_error is not None:
            return None
        return self._by_scope.get((project_id, member_id))

    def require_source(self, project_id: str, member_id: str) -> Source:
        source = self.source_for(project_id, member_id)
        if source is None:
            raise unavailable_error()
        return source

    def list_logs(
        self,
        project_id: str,
        member_id: str,
        query: QuerySpec,
    ) -> RuntimeLogPage:
        if query.exact_ref and query.cursor is not None:
            raise _conflicting_filters()
        source = self.require_source(project_id, member_id)
        cursor_payload = self._prepare_cursor(project_id, member_id, query)
        collector = _MatchCollector(
            project_id=project_id,
            member_id=member_id,
            query=query,
            cursor_payload=cursor_payload,
        )
        outcome = scan_source(
            source, limits=self._scan_limits, visitor=collector.visit
        )
        if cursor_payload is not None:
            if outcome.availability_failed:
                raise unavailable_error()
            if not outcome.complete:
                raise _stale_cursor()
            if outcome.inventory_hash != cursor_payload.get("inventory_hash"):
                raise _stale_cursor()
        if query.exact_ref:
            if not outcome.complete:
                raise scan_incomplete_error()
            if not collector.ref_matches:
                from bridges.runtime_log_retention import expired_reference
                expired = expired_reference(source.root, project_id, member_id, query.ref)
                if expired is True:
                    raise RuntimeDiagnosticsError("log_expired", 410)
                if expired is None:
                    raise scan_incomplete_error()
                raise _log_not_found()
            if len(collector.ref_matches) > 1:
                raise _log_ref_conflict()
            try:
                summary = project_summary(
                    collector.ref_matches[0], (project_id, member_id)
                )
            except ProjectionFailure:
                raise projection_failed_error()
            return page_model(
                project_id=project_id,
                member_id=member_id,
                query=query,
                records=[summary],
                snapshot_until=None,
                has_more=False,
                next_cursor=None,
                outcome=outcome,
            )

        ordered = collector.ordered()
        has_more = len(ordered) > query.limit
        selected = ordered[: query.limit]
        try:
            summaries = [
                project_summary(record, (project_id, member_id))
                for _, _, record in selected
            ]
        except ProjectionFailure:
            raise projection_failed_error()
        next_cursor: str | None = None
        if outcome.complete and has_more and selected:
            last_at, last_id, _ = selected[-1]
            next_cursor = self.cursor_codec.encode(
                {
                    "scope_hash": scope_hash(project_id, member_id),
                    "filter_hash": filter_hash(query),
                    "source_revision": self.source_revision,
                    "inventory_hash": outcome.inventory_hash,
                    "snapshot_until": (
                        _query_text(query.until) if query.until is not None else None
                    ),
                    "last_recorded_at": _query_text(last_at),
                    "last_log_id": last_id,
                }
            )
        return page_model(
            project_id=project_id,
            member_id=member_id,
            query=query,
            records=summaries,
            snapshot_until=_query_text(query.until) if query.until is not None else None,
            has_more=has_more,
            next_cursor=next_cursor,
            outcome=outcome,
        )

    def get_detail(
        self,
        project_id: str,
        member_id: str,
        log_ref: str,
    ) -> RuntimeLogDetail:
        source = self.require_source(project_id, member_id)
        collector = _MatchCollector(
            project_id=project_id,
            member_id=member_id,
            query=QuerySpec(
                ref=log_ref,
                since=None,
                until=None,
                instance_id=None,
                launch_id=None,
                task_id=None,
                event=None,
                stage=None,
                severity=None,
                limit=DEFAULT_PAGE_LIMIT,
                cursor=None,
                provided=frozenset(),
            ),
            cursor_payload=None,
        )
        outcome = scan_source(
            source, limits=self._scan_limits, visitor=collector.visit
        )
        if not outcome.complete:
            raise scan_incomplete_error()
        if not collector.ref_matches:
            from bridges.runtime_log_retention import expired_reference
            expired = expired_reference(source.root, project_id, member_id, log_ref)
            if expired is True:
                raise RuntimeDiagnosticsError("log_expired", 410)
            if expired is None:
                raise scan_incomplete_error()
            raise _log_not_found()
        if len(collector.ref_matches) > 1:
            raise _log_ref_conflict()
        try:
            record = project_detail(
                collector.ref_matches[0], (project_id, member_id)
            )
        except ProjectionFailure:
            raise projection_failed_error()
        return detail_model(
            project_id=project_id,
            member_id=member_id,
            record=record,
            outcome=outcome,
        )

    def _prepare_cursor(
        self,
        project_id: str,
        member_id: str,
        query: QuerySpec,
    ) -> dict[str, Any] | None:
        if query.cursor is None:
            return None
        if not {"since", "until", "severity"}.issubset(query.provided):
            raise _invalid_cursor()
        payload = self.cursor_codec.decode(query.cursor)
        if payload.get("scope_hash") != scope_hash(project_id, member_id):
            raise _invalid_cursor()
        if payload.get("filter_hash") != filter_hash(query):
            raise _invalid_cursor()
        if payload.get("source_revision") != self.source_revision:
            raise _stale_cursor()
        return payload


def _query_text(value: datetime) -> str:
    text = value.astimezone(timezone.utc).isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def get_default_codec() -> CursorCodec:
    global _DEFAULT_CODEC
    if _DEFAULT_CODEC is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_CODEC is None:
                _DEFAULT_CODEC = CursorCodec()
    return _DEFAULT_CODEC


def get_default_provider() -> RuntimeDiagnosticsProvider:
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_PROVIDER is None:
                _DEFAULT_PROVIDER = RuntimeDiagnosticsProvider.from_config(
                    CONFIG, cursor_codec=get_default_codec()
                )
    return _DEFAULT_PROVIDER


def reset_default_provider() -> None:
    global _DEFAULT_PROVIDER
    with _DEFAULT_LOCK:
        _DEFAULT_PROVIDER = None
