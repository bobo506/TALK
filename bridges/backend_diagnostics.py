"""Opt-in, project-scoped backend events; never consumes raw process output.

Only code-owned enums, public identifiers and exception *structure* enter this
stream. Exception messages, source lines, locals and arbitrary extras do not.
The existing runtime writer supplies independent runs, leases and segmentation.
Backend runs do not delete segments or participate in the five-role sweeper.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from bridges.runtime_diagnostics import DiagnosticsPolicy, RuntimeDiagnostics, sanitize_text
from bridges.backend_error_codes import HOST_ERROR_CODES, RUNTIME_ERROR_CODES

MEMBER = "backend:project"  # storage namespace, never a registered TALK member
RETENTION_SCOPE = "talk-backend-project-retention-1"
COMPONENTS = frozenset({"api", "runtime", "provision_worker"})
EVENTS = frozenset({
    "backend_starting", "backend_ready", "backend_stopping", "backend_stopped",
    "backend_failed", "backend_heartbeat", "api_request", "api_exception",
    "host_started", "host_exited", "host_start_failed", "worker_result",
    "worker_exception", "runtime_exception", "api_child_exited", "api_background_exception",
})
STAGES = frozenset({"startup", "serve", "shutdown", "request", "discover", "claim",
    "create", "key", "steps", "report", "invalidated", "stopped", "disabled", "plan"})
OUTCOMES = frozenset({"started", "ready", "stopped", "succeeded", "failed", "reported",
    "provisioned", "skipped", "planned", "running"})
METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
ERROR_CODES = frozenset({"http_error", "worker_disabled", "worker_stopped", "worker_io_budget_exceeded",
    "preflight_failed", "identity_mismatch", "ack_failed", "ack_stale", "resume_required",
    "role_request_lease_invalid", "role_request_lease_conflict", "role_request_status_conflict",
    "role_request_host_mismatch", "role_request_credential_stale", "manual_recovery_required",
    "role_key_foreign_refused", "key_provenance_write_failed", "operator_key_missing",
    "provision_lock_busy", "profile_write_failed", "profile_root_invalid", "key_file_write_failed",
    "key_write_failed", "key_permissions_failed", "key_root_inside_repo", "role_key_unknown",
    "role_key_stale", "path_escape_refused", "symlink_refused", "cli_executable_missing",
    "not_apply_mode", "worker_base_url_not_loopback", "worker_redirect_refused"}) | HOST_ERROR_CODES | RUNTIME_ERROR_CODES
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
REQUEST_ID = re.compile(r"^[a-f0-9]{32}$")


def project_root(root: Path, project_id: str) -> Path:
    # Full hash: no traversal, case/normalization collisions or readable private paths.
    return Path(root) / hashlib.sha256(project_id.encode("utf-8")).hexdigest()


def settings(config: Any, *, database_file: Any) -> dict | None:
    """Fail closed; enabled sources are explicitly DB-bound and project-listed."""
    try:
        return _settings(config, database_file=database_file)
    except (OSError, ValueError, TypeError):
        return None


def _settings(config, *, database_file):
    if not isinstance(config, dict):
        return None
    section = config.get("backend_diagnostics")
    if not isinstance(section, dict) or section.get("enabled") is not True:
        return None
    root, database, projects = (section.get(k) for k in ("root", "database_file", "projects"))
    if (not isinstance(root, str) or not root.strip() or not Path(root).is_absolute()
            or root.startswith(("\\\\", "//"))
            or not isinstance(database, str) or not Path(database).is_absolute()
            or database.startswith(("\\\\", "//"))
            or not database_file or str(database_file) == ":memory:"
            or Path(database).resolve() != Path(database_file).resolve()
            or not isinstance(projects, list) or not projects
            or any(not isinstance(p, str) or not TOKEN.fullmatch(p) for p in projects)
            or len(set(projects)) != len(projects) or len(projects) > 100):
        return None
    return {"root": Path(root), "projects": tuple(projects)}


def _public_token(value: Any, secrets=()) -> str | None:
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        return None
    return value if sanitize_text(value, sensitive_values=secrets) == value else None


def safe_context(raw: Any, *, secrets=()) -> dict:
    """Allow-list both at collection and export. No arbitrary str()/repr()."""
    if not isinstance(raw, dict):
        return {}
    result: dict = {}
    for key in ("member_id", "error_code", "request_key"):
        value = _public_token(raw.get(key), secrets)
        if value is not None:
            # Request keys can be supplied by clients; store a stable digest, not text.
            if key == "request_key":
                result["request_key_sha256"] = hashlib.sha256(value.encode()).hexdigest()
            else:
                result[key] = value
    for key, allowed in (("stage", STAGES), ("outcome", OUTCOMES), ("method", METHODS)):
        value = raw.get(key)
        if isinstance(value, str) and value in allowed:
            result[key] = value
    if raw.get("state") in {"waiting_api", "running", "api_exited", "stopping", "stopped", "startup_failed", "stop_blocked"}:
        result["state"] = raw["state"]
    if raw.get("subsystem") in {"local_runtime", "log_retention", "database", "storage"}:
        result["subsystem"] = raw["subsystem"]
    # error codes are arbitrary exceptions' attributes in some callers. Hash them:
    # a user/extension cannot hide a bare credential in a syntactically valid token.
    if "error_code" in result and result["error_code"] not in ERROR_CODES:
        result["error_code_digest"] = hashlib.sha256(result.pop("error_code").encode()).hexdigest()
    value = raw.get("request_id")
    if isinstance(value, str) and REQUEST_ID.fullmatch(value):
        result["request_id"] = value
    for key, low, high in (("status", 100, 599), ("child_pid", 1, 2**31-1),
            ("revision", 0, 2**53-1), ("duration_ms", 0, 2**53-1), ("returncode", -2**31, 2**31-1)):
        value = raw.get(key)
        if type(value) is int and low <= value <= high:
            result[key] = value
    # Caller passes a route *template*, never URL path or query. Only known route
    # templates are accepted by the API recorder, not this general writer.
    value = raw.get("route")
    if (isinstance(value, str) and len(value) <= 256 and re.fullmatch(r"/[A-Za-z0-9_/{.}:-]*", value)
            and sanitize_text(value, sensitive_values=secrets) == value):
        result["route"] = value
    return result


def exception_structure(exc: BaseException, *, secrets=()) -> dict:
    """Bounded traceback/cause structure without ever calling str(exc)."""
    seen: set[int] = set()

    def describe(error: BaseException) -> dict:
        frames, tb = [], error.__traceback__
        total = 0
        while tb is not None and total < 2048:
            total += 1
            if len(frames) < 64:
                code = tb.tb_frame.f_code
                frames.append({
                    "file_name": sanitize_text(Path(code.co_filename).name, sensitive_values=secrets, max_chars=128),
                    "function": sanitize_text(code.co_name, sensitive_values=secrets, max_chars=128),
                    "line": tb.tb_lineno,
                })
            tb = tb.tb_next
        return {"type": sanitize_text(type(error).__name__, sensitive_values=secrets, max_chars=128),
            "message_omitted": True, "frames": frames, "frames_truncated": total > len(frames) or tb is not None}

    first = describe(exc)
    chain = []
    current = exc
    for _ in range(8):
        seen.add(id(current))
        cause = current.__cause__
        relation = "cause"
        if cause is None and not current.__suppress_context__:
            cause, relation = current.__context__, "context"
        if cause is None:
            break
        if id(cause) in seen:
            first["chain_truncated"] = True
            break
        chain.append({"relation": relation, **describe(cause)})
        current = cause
    else:
        first["chain_truncated"] = True
    first["cause_chain"] = chain
    return first


class _BackendWriter(RuntimeDiagnostics):
    def _closed_receipt_extra(self):
        return {"retention_scope": RETENTION_SCOPE, "backend_component": self.runtime}

    def _cleanup_expired_locked(self, reason):
        pass  # only the explicitly enabled backend retention worker may expire runs

    def _enforce_capacity_locked(self, *, incoming, record):
        if sum(self._safe_size(p) for p in self._event_files_locked()) + incoming > self.policy.max_bytes:
            record.setdefault("integrity", {})["capacity_soft_exceeded"] = True


class BackendJournal:
    def __init__(self, root: Path, project_id: str, component: str, *, known_secrets=(), clock=None):
        if component not in COMPONENTS or not TOKEN.fullmatch(project_id):
            raise ValueError("backend_scope_invalid")
        self.component, self.project_id = component, project_id
        self.secrets = tuple(s for s in known_secrets if isinstance(s, str) and s)
        self.writer = _BackendWriter(member_id=MEMBER, instance_id=f"{component}-{os.getpid()}",
            project_id=project_id, runtime=component, known_secrets=self.secrets, clock=clock,
            policy=DiagnosticsPolicy(root=project_root(root, project_id), retention_days=0))

    def emit(self, event: str, *, context=None, exc: BaseException | None = None, severity=None):
        if event not in EVENTS:
            return None
        try:
            extra = {"backend_context": safe_context(context, secrets=self.secrets)}
            if exc is not None:
                try:
                    extra["backend_exception"] = exception_structure(exc, secrets=self.secrets)
                except Exception:
                    extra["backend_exception"] = {"type": "Exception", "message_omitted": True,
                        "frames": [], "frames_truncated": True, "cause_chain": [], "chain_truncated": True}
            if severity not in ("error", "warning", "info"):
                safe = extra["backend_context"]
                failure = exc is not None or safe.get("outcome") in ("failed", "reported")
                failure = failure or bool(safe.get("error_code") or safe.get("error_code_digest")) or safe.get("status", 0) >= 400
                severity = "error" if failure else "info"
            return self.writer.record_event(event, severity=severity,
                phase="serve", stage=(context or {}).get("stage") if (context or {}).get("stage") in STAGES else None,
                extra=extra)
        except Exception:
            # Diagnostics must not change worker, ownership or server behavior.
            return None

    def close(self):
        self.writer.close()


def runtime_journals(project_path: Path, project_id: str, *, known_secrets=(), components=("runtime", "provision_worker")) -> dict:
    """No files on disabled/dry-run paths. Reads only the project's normal TOML."""
    try:
        import tomllib
        with (project_path / "config.toml").open("rb") as stream:
            config = tomllib.load(stream)
        database = Path(config["storage"]["db_path"])
        if not database.is_absolute():
            database = project_path / database
        value = settings(config, database_file=database)
        if value is None or project_id not in value["projects"]:
            return {}
        return {c: BackendJournal(value["root"], project_id, c, known_secrets=known_secrets)
                for c in components}
    except Exception:
        return {}
