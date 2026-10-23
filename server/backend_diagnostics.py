"""DB-bound backend collection and bounded, human-only export projection."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from sqlmodel import select

from bridges.backend_diagnostics import (
    BackendJournal, COMPONENTS, EVENTS, MEMBER, project_root, safe_context, settings,
)
from server.runtime_diagnostics_export import (
    MAX_EXPORT_BYTES, MAX_EXPORT_RECORDS, MAX_META_BYTES, build_export, utc_text,
)
from server.runtime_diagnostics_query import (
    ProjectionFailure, ScanLimits, Source, RuntimeDiagnosticsError, _scrub_text,
    project_detail,
)


def project_members(session, project_id):
    """Same historical role/roster rule as the existing target read contract."""
    from server.models import ProjectAgent, ProjectRole
    return frozenset(session.exec(select(ProjectRole.member_id).where(ProjectRole.project_id == project_id)).all()) | frozenset(
        session.exec(select(ProjectAgent.member_id).where(ProjectAgent.project_id == project_id)).all())


def project_routes(app):
    """Only code-owned templates, never a request path or client parameter."""
    return frozenset(route.path for route in app.routes
        if isinstance(getattr(route, "path", None), str)
        and route.path.startswith("/api/projects/{project_id}"))


class BackendRecorder:
    def __init__(self, config, engine):
        self.settings = settings(config, database_file=engine.url.database)
        self.journals = {}
        self.lock = threading.RLock()
        self.database_file = engine.url.database
        self.closed = False

    def emit(self, project_id, event, *, context=None, exc=None):
        if not self.settings or project_id not in self.settings["projects"]:
            return
        try:
            with self.lock:
                if self.closed:
                    return
                journal = self.journals.get(project_id)
                if journal is None:
                    journal = BackendJournal(self.settings["root"], project_id, "api")
                    self.journals[project_id] = journal
                journal.emit(event, context=context, exc=exc)
        except Exception:
            pass

    def lifecycle(self, event, *, stage, exc=None, context=None):
        for project in (self.settings or {}).get("projects", ()):
            self.emit(project, event, context={**(context or {}), "stage": stage}, exc=exc)

    def close(self):
        with self.lock:
            self.closed = True
            for journal in self.journals.values():
                journal.close()
            self.journals.clear()


def _exception(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProjectionFailure("backend_exception")

    def one(raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("frames"), list) or len(raw["frames"]) > 64:
            raise ProjectionFailure("backend_exception")
        frames = []
        for frame in raw["frames"]:
            if not isinstance(frame, dict) or type(frame.get("line")) is not int or not 0 <= frame["line"] <= 2**31:
                raise ProjectionFailure("backend_exception")
            file_name = _scrub_text(frame.get("file_name"), field="file", max_chars=128)
            frames.append({"file_name": file_name, "line": frame["line"],
                "function": _scrub_text(frame.get("function"), field="function", max_chars=128)})
        return {"type": _scrub_text(raw.get("type"), field="type", max_chars=128),
            "message_omitted": True, "frames": frames, "frames_truncated": raw.get("frames_truncated") is not False}

    result = one(value)
    chain = value.get("cause_chain", [])
    if not isinstance(chain, list) or len(chain) > 8 or any(not isinstance(c, dict) for c in chain):
        raise ProjectionFailure("backend_exception")
    result["cause_chain"] = [{"relation": c.get("relation") if c.get("relation") in ("cause", "context") else None,
        **one(c)} for c in chain if isinstance(c, dict)]
    result["chain_truncated"] = value.get("chain_truncated") is True
    return result


def project_event(record, scope, *, allowed_members=frozenset(), allowed_routes=frozenset()):
    component, event = record.get("runtime"), record.get("event")
    if component not in COMPONENTS or event not in EVENTS:
        raise ProjectionFailure("backend_event")
    result = {"kind": "backend_event", **project_detail(record, scope).model_dump()}
    # The storage namespace is not a role identity. Network output always says so.
    result.pop("member_id", None)
    result["component"] = component
    raw = record.get("extra")
    raw = raw if isinstance(raw, dict) else {}
    context = raw.get("backend_context")
    context = context if isinstance(context, dict) else {}
    # Syntax/redaction is not an identity or route attestation. Validate again
    # against the request DB and application code even for old/tampered files.
    member = context.get("member_id")
    route = context.get("route")
    if member is not None and (not isinstance(member, str) or member not in allowed_members):
        raise ProjectionFailure("backend_member")
    if route is not None and (not isinstance(route, str) or route not in allowed_routes):
        raise ProjectionFailure("backend_route")
    projected = safe_context({k: v for k, v in context.items() if k != "request_key"})
    for key in ("request_key_sha256", "error_code_digest"):
        value = context.get(key)
        if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
            projected[key] = value
    result["context"] = projected
    result["attribution"] = "role" if projected.get("member_id") else "project_shared"
    result["exception"] = _exception(raw.get("backend_exception"))
    return result


def build_backend_export(value, project_id, *, since, until, member_id=None,
                         limits=None, max_bytes=MAX_EXPORT_BYTES, max_records=MAX_EXPORT_RECORDS,
                         allowed_members=frozenset(), allowed_routes=frozenset()):
    if value is None or project_id not in value["projects"]:
        raise RuntimeDiagnosticsError("backend_diagnostics_unavailable", 503)
    limits = limits or ScanLimits()
    deadline = time.monotonic()+limits.max_seconds
    source = Source(project_id, MEMBER, project_root(value["root"], project_id))
    def role_filter(record):
        extra = record.get("extra")
        if not isinstance(extra, dict):
            return True  # projection will decide whether this is malformed
        context = extra.get("backend_context")
        if not isinstance(context, dict):
            return True
        candidate = context.get("member_id")
        if candidate is not None and (not isinstance(candidate, str) or candidate not in allowed_members):
            return True  # selected, then rejected with an explicit projection_failed
        return candidate in (None, member_id)
    body = build_export(source, project_id=project_id, member_id=MEMBER, since=since, until=until,
        limits=limits, max_bytes=max_bytes-MAX_META_BYTES, max_records=max_records,
        event_projector=lambda r, s: project_event(r, s, allowed_members=allowed_members, allowed_routes=allowed_routes),
        record_filter=role_filter if member_id else None)
    lines = body.splitlines()
    meta = json.loads(lines[0])
    events = [json.loads(line) for line in lines[1:]]
    present = {event["component"] for event in events}
    missing = sorted(COMPONENTS - present)
    # An available new stream cannot attest that pre-instrumentation output,
    # crashed intervals or old private stdout/stderr were captured completely.
    reasons = set(meta["reasons"]) | {"backend_coverage_unverified"}
    if missing:
        reasons.add("backend_missing_components")
    if time.monotonic() >= deadline:
        reasons.add("time_limit")
        meta["truncated"] = True
    meta.update(schema="talk-backend-diagnostics-export-1", scope={"project_id": project_id, "member_id": member_id},
        complete=False, reasons=sorted(reasons), coverage={"components_present": sorted(present),
            "components_missing": missing, "history_complete": False,
            "capture": "structured_events_only", "raw_outputs_included": False,
            "exception_messages_included": False})
    return _encode(meta, events, max_bytes)


def _encode(meta, events, max_bytes):
    def line(value):
        return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))+"\n").encode("utf-8")
    chunks = [line(e) for e in events]
    size = sum(map(len, chunks))
    while True:
        meta["record_count"] = len(chunks)
        header = line(meta)
        if len(header) > MAX_META_BYTES:
            raise RuntimeDiagnosticsError("diagnostics_projection_failed", 503)
        if len(header)+size <= max_bytes:
            return header+b"".join(chunks)
        if not chunks:
            raise RuntimeDiagnosticsError("diagnostics_projection_failed", 503)
        size -= len(chunks.pop())
        meta["complete"], meta["truncated"] = False, True
        meta["reasons"] = sorted(set(meta["reasons"]) | {"byte_limit"})


def unavailable_role_export(project_id, member_id, *, since, until):
    """Explicit gap for a known role with no readable role log source."""
    return _encode({"kind": "meta", "schema": "talk-diagnostics-export-1",
        "scope": {"project_id": project_id, "member_id": member_id},
        "query": {"since": utc_text(since), "until": utc_text(until)},
        "generated_at": utc_text(datetime.now(timezone.utc)), "record_count": 0,
        "complete": False, "truncated": False, "reasons": ["unavailable_records"],
        "scan": {"complete": False, "truncated": False, "scanned_files": 0, "scanned_bytes": 0,
            "malformed_lines": 0, "unavailable_sources": 1}, "role": {"available": False}}, [], MAX_EXPORT_BYTES)


def merge_role_export(role_body, value, project_id, member_id, *, since, until, remaining_seconds, limits=None,
                      allowed_members=frozenset(), allowed_routes=frozenset()):
    """One total file budget. Role scan keeps priority; no second full budget."""
    role_lines = role_body.splitlines()
    deadline = time.monotonic()+max(0, remaining_seconds)
    limits = limits or ScanLimits()
    meta = json.loads(role_lines[0])
    events = [json.loads(line) for line in role_lines[1:]]
    count_left = max(0, MAX_EXPORT_RECORDS-len(events))
    # Reserve space for the combined meta instead of granting another 16MiB.
    bytes_left = MAX_EXPORT_BYTES-sum(len(line)+1 for line in role_lines[1:])-2*MAX_META_BYTES
    if remaining_seconds <= 0 or count_left == 0 or bytes_left <= 2*MAX_META_BYTES:
        meta.update(complete=False, truncated=True)
        meta["reasons"] = sorted(set(meta["reasons"]) | {"backend_unavailable", "time_limit" if remaining_seconds <= 0 else "byte_limit"})
        meta["backend"] = {"available": False, "history_complete": False}
        return _encode(meta, events, MAX_EXPORT_BYTES)
    try:
        backend = build_backend_export(value, project_id, member_id=member_id, since=since, until=until,
            limits=ScanLimits(max_seconds=max(0, deadline-time.monotonic()),
                max_bytes=max(0, limits.max_bytes-meta["scan"]["scanned_bytes"]),
                max_files=max(0, limits.max_files-2*meta["scan"]["scanned_files"])),
            max_records=count_left, max_bytes=bytes_left, allowed_members=allowed_members, allowed_routes=allowed_routes)
        backend_lines = backend.splitlines()
        backend_meta = json.loads(backend_lines[0])
        events += [json.loads(line) for line in backend_lines[1:]]
        meta["backend"] = {"available": True, "scan": backend_meta["scan"], **backend_meta["coverage"]}
        meta["complete"] = meta["complete"] and backend_meta["complete"]
        meta["truncated"] = meta["truncated"] or backend_meta["truncated"]
        meta["reasons"] = sorted(set(meta["reasons"]) | set(backend_meta["reasons"]))
    except Exception:
        meta["complete"] = False
        meta["reasons"] = sorted(set(meta["reasons"]) | {"backend_unavailable"})
        meta["backend"] = {"available": False, "history_complete": False}
    events.sort(key=lambda event: (event["recorded_at"], event["log_id"]))
    if len({event["log_id"] for event in events}) != len(events):
        meta["complete"] = False
        meta["reasons"] = sorted(set(meta["reasons"]) | {"duplicate_log_id"})
    if time.monotonic() >= deadline:
        meta["complete"], meta["truncated"] = False, True
        meta["reasons"] = sorted(set(meta["reasons"]) | {"time_limit"})
    return _encode(meta, events, MAX_EXPORT_BYTES)
