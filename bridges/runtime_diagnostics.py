#!/usr/bin/env python3
"""Local, persistent runtime diagnostics for TALK bridge processes.

This module is deliberately standard-library only.  It does not import the
server, the TALK database or any private configuration loader.  A bridge hands
it the identities and budgets it already knows in memory; unknown values stay
``None`` instead of being inferred from a template.

Storage layout (under ``logs/runtime`` by default)::

    <root>/<safe member>/<safe instance>/<run id>/manifest.json
    <root>/<safe member>/<safe instance>/<run id>/events-00001.jsonl
    <root>/<safe member>/<safe instance>/<run id>/rotation.jsonl
    <root>/<safe member>/<safe instance>/<run id>/retention.jsonl

Every process/bridge instance gets its own run namespace, so two processes can
write and rotate independently without sharing a file.  Old files are never
deleted on startup.  Rotation/capacity/retention work only inside the current
run namespace and always leave a tombstone record when a segment is removed.

Public error messages use :func:`public_log_reference` for a stable reference;
the full sanitized stack is available only through the controlled local query
helpers (and ``scripts/runtime_diagnostics.py``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, quote_plus
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "logs" / "runtime"
DEFAULT_RETENTION_DAYS = 30.0
DEFAULT_MAX_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_EVENT_BYTES = 1024 * 1024
MAX_EXCEPTION_MESSAGE_CHARS = 16 * 1024
MAX_FRAME_SOURCE_CHARS = 4 * 1024
MAX_CHAIN_DEPTH = 16
MAX_FRAMES_PER_EXCEPTION = 2048
MAX_EXTRA_DEPTH = 8
MAX_EXTRA_ITEMS = 200
REDACTED = "[REDACTED]"
SCHEMA = "talk-runtime-diagnostics-1"
LOG_ID_RE = re.compile(r"^rtd-[A-Za-z0-9.-]{4,160}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# These patterns are intentionally conservative: they cover common credential
# shapes and the exact in-memory values supplied by the bridge, without trying
# to read environment files or scan the machine for secrets.
_HEADER_AUTH_RE = re.compile(
    r"(?i)\b(authorization|proxy-authorization)\s*:\s*[^\r\n]+"
)
_HEADER_API_KEY_RE = re.compile(r"(?i)\b(x-api-key|api-key)\s*:\s*[^\r\n]+")
_HEADER_COOKIE_RE = re.compile(r"(?i)\b(cookie|set-cookie)\s*:\s*[^\r\n]+")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_BASIC_AUTH_RE = re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|apikey|key|token|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|password|passwd|secret|signature|sig|auth)=)([^&#\s]+)"
)
_FIELD_SECRET_RE = re.compile(
    r"""(?ix)
    (?P<prefix>
        \b(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token|
             claim[_-]?token|owner[_-]?token|session[_-]?token|token|secret|
             client[_-]?secret|password|passwd|pwd|credentials?)\b
        ["']?\s*[:=]\s*
    )
    (?:(?P<quoted>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|
       (?P<bare>[^"'\s,;&}\]]+))
    """
)
_URL_USERINFO_RE = re.compile(r"(?i)(https?://)([^/\s:@]+):([^/\s@]+)@")
_SENSITIVE_KEY_RE = re.compile(
    r"""(?ix)^\s*["']?
    (?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token|
       claim[_-]?token|owner[_-]?token|session[_-]?token|token|secret|client[_-]?secret|password|passwd|pwd|
       authorization|proxy[_-]?authorization|x-api-key|cookie|set-cookie|
       credentials?)
    ["']?\s*$"""
)
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
    re.DOTALL,
)
_OPAQUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        return path == root or root in path.parents
    except (OSError, ValueError):
        return False


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _safe_token(value: Any, *, fallback: str) -> str:
    """Turn an identity into one safe path component, never ``.`` or ``..``."""
    text = str(value if value is not None else "").strip()
    if not text:
        return fallback
    if _SAFE_TOKEN_RE.fullmatch(text) and text not in {".", ".."}:
        return text
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = fallback
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:10]
    return f"{cleaned[:48]}-{digest}"


def _now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.astimezone()


def _timestamp(value: datetime) -> str:
    return _aware(value).isoformat(timespec="microseconds")


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _compact_text(value: Any, limit: int = 200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + f"…[+{len(text) - limit}]"
    return text


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(value) <= limit:
        return value, False
    remaining = len(value) - limit
    return f"{value[:limit].rstrip()}…[truncated {remaining} chars]", True


def public_log_reference(log_id: str) -> str:
    """Stable, non-secret reference suitable for a public error summary."""
    return f"[日志引用：{log_id}]"


def _replace_secret_field(match: re.Match[str]) -> str:
    value = match.group("quoted") or match.group("bare") or ""
    if REDACTED in value:
        return match.group(0)
    quote_char = value[0] if match.group("quoted") else ""
    return f"{match.group('prefix')}{quote_char}{REDACTED}{quote_char}"


class _Redactor:
    """Redact known in-memory values, common headers, URLs and field names."""

    def __init__(self, values: Iterable[Any] = ()):
        candidates: set[str] = set()
        for value in values:
            if value is None:
                continue
            text = str(value)
            if len(text) < 4:
                continue
            candidates.add(text)
            # Exceptions often embed repr(argv) or JSON-escaped multiline prompts.
            candidates.add(repr(text)[1:-1])
            candidates.add(json.dumps(text, ensure_ascii=False)[1:-1])
            candidates.add(json.dumps(text, ensure_ascii=True)[1:-1])
            if len(text) <= 4096:
                candidates.add(quote(text, safe=""))
                candidates.add(quote_plus(text, safe=""))
        # Longer values first so a full token is replaced before a prefix.
        self._values = sorted(
            (value for value in candidates if len(value) >= 4),
            key=len,
            reverse=True,
        )
        self.kinds: set[str] = set()
        self.changed = False

    def _mark(self, kind: str, changed: bool) -> None:
        if changed:
            self.changed = True
            self.kinds.add(kind)

    def text(self, value: Any) -> tuple[str, bool]:
        try:
            if value is None:
                return "", False
            if isinstance(value, bytes):
                text = value.decode("utf-8", "replace")
            else:
                text = str(value)
        except Exception:
            self._mark("unreadable_text", True)
            return "", True

        original = text
        if REDACTED in original:
            self._mark("upstream_redaction", True)
        for secret in self._values:
            if secret in text:
                text = text.replace(secret, REDACTED)
        if text != original:
            self._mark("known_value", True)

        text, changed = self._regex(
            text, _HEADER_AUTH_RE, lambda m: f"{m.group(1)}: {REDACTED}", "authorization_header"
        )
        self._mark("authorization_header", changed)
        text, changed = self._regex(
            text, _HEADER_API_KEY_RE, lambda m: f"{m.group(1)}: {REDACTED}", "api_key_header"
        )
        self._mark("api_key_header", changed)
        text, changed = self._regex(
            text, _HEADER_COOKIE_RE, lambda m: f"{m.group(1)}: {REDACTED}", "cookie_header"
        )
        self._mark("cookie_header", changed)
        text, changed = self._regex(text, _BEARER_RE, lambda _m: f"Bearer {REDACTED}", "bearer_token")
        self._mark("bearer_token", changed)
        text, changed = self._regex(
            text, _BASIC_AUTH_RE, lambda _m: f"Basic {REDACTED}", "basic_auth"
        )
        self._mark("basic_auth", changed)
        text, changed = self._regex(
            text,
            _QUERY_SECRET_RE,
            lambda m: f"{m.group(1)}{REDACTED}",
            "url_query",
        )
        self._mark("url_query", changed)
        text, changed = self._regex(
            text,
            _FIELD_SECRET_RE,
            _replace_secret_field,
            "secret_field",
        )
        self._mark("secret_field", changed)
        text, changed = self._regex(
            text,
            _URL_USERINFO_RE,
            lambda m: f"{m.group(1)}{REDACTED}@",
            "url_userinfo",
        )
        self._mark("url_userinfo", changed)
        text, changed = self._regex(
            text, _PRIVATE_KEY_RE, lambda _m: REDACTED, "private_key"
        )
        self._mark("private_key", changed)
        for pattern in _OPAQUE_PATTERNS:
            text, changed = self._regex(text, pattern, lambda _m: REDACTED, "opaque_token")
            self._mark("opaque_token", changed)
        return text, self.changed

    @staticmethod
    def _regex(text: str, pattern: re.Pattern[str], replacement: Any, kind: str) -> tuple[str, bool]:
        del kind
        replaced, count = pattern.subn(replacement, text)
        return replaced, count > 0 and replaced != text


def sanitize_text(text: Any, *, sensitive_values: Iterable[Any] = (), max_chars: int | None = None) -> str:
    """Return a sanitized string; explicit truncation is marked in the text."""
    redactor = _Redactor(sensitive_values)
    value, _changed = redactor.text(text)
    if max_chars is not None:
        value, _truncated = _truncate(value, max_chars)
    return value


def _sanitize_nested(
    value: Any,
    redactor: _Redactor,
    *,
    depth: int = 0,
) -> Any:
    """Sanitize data destined for ``extra`` without recording locals/objects."""
    if depth > MAX_EXTRA_DEPTH:
        return "[omitted: nesting limit]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redactor.text(value)[0]
    if isinstance(value, bytes):
        return f"[bytes:{len(value)}]"
    if isinstance(value, BaseException):
        return {
            "type": f"{type(value).__module__}.{type(value).__qualname__}",
            "message": redactor.text(value)[0],
        }
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_EXTRA_ITEMS:
                result["[omitted]"] = f"{len(value) - index} items"
                break
            safe_key = redactor.text(key)[0] if isinstance(key, str) else str(key)
            if _SENSITIVE_KEY_RE.fullmatch(str(key)):
                result[safe_key] = REDACTED
                redactor.changed = True
                redactor.kinds.add("secret_field")
                continue
            result[safe_key] = _sanitize_nested(
                item, redactor, depth=depth + 1
            )
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        result = [
            _sanitize_nested(item, redactor, depth=depth + 1)
            for item in items[:MAX_EXTRA_ITEMS]
        ]
        if len(items) > MAX_EXTRA_ITEMS:
            result.append(f"[omitted: {len(items) - MAX_EXTRA_ITEMS} items]")
        return result
    text, _changed = redactor.text(value)
    return text



def exception_sensitive_values(exc: BaseException) -> tuple[str, ...]:
    """Carry explicit in-memory protection through cause/context boundaries."""
    values = []
    pending = [exc]
    seen = set()
    while pending and len(seen) < MAX_CHAIN_DEPTH * 2:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        protected = getattr(current, "diagnostic_sensitive_values", ())
        if isinstance(protected, (str, bytes)):
            protected = (protected,)
        for value in protected:
            if isinstance(value, str) and value:
                values.append(value)
        if isinstance(current, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            command = current.cmd
            values.append(str(command))
        for cause in (current.__cause__, current.__context__):
            if isinstance(cause, BaseException):
                pending.append(cause)
    return tuple(dict.fromkeys(values))


def _describe_exception(
    exc: BaseException,
    *,
    relation: str,
    redactor: _Redactor,
) -> tuple[dict[str, Any], set[str]]:
    truncated_fields: set[str] = set()
    type_module = type(exc).__module__
    type_qualname = type(exc).__qualname__
    type_name = type_qualname if type_module == "builtins" else f"{type_module}.{type_qualname}"

    message_error = False
    try:
        if isinstance(exc, subprocess.CalledProcessError):
            raw_message = f"Process exited with return code {exc.returncode}; command/output omitted"
        elif isinstance(exc, subprocess.TimeoutExpired):
            raw_message = f"Process exceeded timeout {exc.timeout}; command/output omitted"
        else:
            raw_message = str(exc)
    except Exception:
        raw_message = ""
        message_error = True
    str_empty = raw_message == ""
    message, _redacted = redactor.text(raw_message)
    message, truncated = _truncate(message, MAX_EXCEPTION_MESSAGE_CHARS)
    if truncated:
        truncated_fields.add("exception.message")

    frames: list[dict[str, Any]] = []
    tb = exc.__traceback__
    extracted: list[Any] = []
    if tb is not None:
        try:
            extracted = list(traceback.extract_tb(tb))
        except Exception:
            extracted = []
        for frame in extracted[:MAX_FRAMES_PER_EXCEPTION]:
            try:
                filename, filename_changed = redactor.text(frame.filename)
            except Exception:
                filename, filename_changed = "<unavailable>", False
            del filename_changed
            try:
                source, source_changed = redactor.text(frame.line or "")
            except Exception:
                source, source_changed = "", False
            del source_changed
            source, source_truncated = _truncate(source, MAX_FRAME_SOURCE_CHARS)
            if source_truncated:
                truncated_fields.add("exception.frames.source")
            frames.append(
                {
                    "file": filename,
                    "line": int(frame.lineno or 0),
                    "function": str(frame.name or ""),
                    "source": source,
                }
            )
        if len(extracted) > MAX_FRAMES_PER_EXCEPTION:
            truncated_fields.add("exception.frames")
            frames_omitted = len(extracted) - MAX_FRAMES_PER_EXCEPTION
        else:
            frames_omitted = 0
    else:
        frames_omitted = 0

    cause = exc.__cause__
    context = exc.__context__
    context_suppressed = bool(getattr(exc, "__suppress_context__", False))
    info: dict[str, Any] = {
        "relation": relation,
        "type": type_name,
        "type_module": type_module,
        "type_qualname": type_qualname,
        "message": message,
        "str_empty": str_empty,
        "message_error": message_error,
        "frames": frames,
        "frames_total": len(extracted),
        "frames_omitted": frames_omitted,
        "context_present": context is not None,
        "context_suppressed": context_suppressed,
        "has_explicit_cause": cause is not None,
    }
    return info, truncated_fields


def _capture_exception(
    exc: BaseException,
    redactor: _Redactor,
) -> tuple[dict[str, Any], set[str], bool]:
    """Capture the primary exception plus explicit/implicit cause chain."""
    truncated_fields: set[str] = set()
    chain: list[dict[str, Any]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    relation = "primary"
    chain_truncated = False
    chain_cycle = False
    while current is not None:
        if id(current) in seen:
            chain_cycle = True
            break
        if len(chain) >= MAX_CHAIN_DEPTH:
            chain_truncated = True
            truncated_fields.add("exception.cause_chain")
            break
        seen.add(id(current))
        info, fields = _describe_exception(
            current, relation=relation, redactor=redactor
        )
        truncated_fields.update(fields)
        chain.append(info)

        next_exc: BaseException | None = None
        next_relation = "cause"
        cause = current.__cause__
        if cause is not None:
            next_exc = cause
            next_relation = "explicit_cause"
        elif not bool(getattr(current, "__suppress_context__", False)):
            context = current.__context__
            if context is not None:
                next_exc = context
                next_relation = "implicit_context"
        if next_exc is None:
            break
        current = next_exc
        relation = next_relation

    primary = chain[0] if chain else {
        "relation": "primary",
        "type": type(exc).__name__,
        "message": "",
        "frames": [],
        "frames_total": 0,
        "frames_omitted": 0,
    }
    primary["cause_chain"] = chain[1:]
    primary["chain_depth"] = len(chain) - 1
    primary["chain_truncated"] = chain_truncated
    primary["chain_cycle"] = chain_cycle
    return primary, truncated_fields, chain_cycle


@dataclass(frozen=True)
class DiagnosticsPolicy:
    root: Path = DEFAULT_ROOT
    retention_days: float = DEFAULT_RETENTION_DAYS
    max_bytes: int = DEFAULT_MAX_BYTES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES

    @classmethod
    def create(
        cls,
        *,
        root: str | os.PathLike[str] | None = None,
        retention_days: Any = None,
        max_bytes: Any = None,
        max_file_bytes: Any = None,
    ) -> "DiagnosticsPolicy":
        resolved_root = Path(root).expanduser() if root else DEFAULT_ROOT
        resolved_retention = (
            DEFAULT_RETENTION_DAYS
            if retention_days is None
            else _positive_float(retention_days, DEFAULT_RETENTION_DAYS)
        )
        resolved_max = (
            DEFAULT_MAX_BYTES
            if max_bytes is None
            else _positive_int(max_bytes, DEFAULT_MAX_BYTES)
        )
        resolved_file = (
            DEFAULT_MAX_FILE_BYTES
            if max_file_bytes is None
            else _positive_int(max_file_bytes, DEFAULT_MAX_FILE_BYTES)
        )
        return cls(
            root=resolved_root,
            retention_days=resolved_retention,
            max_bytes=resolved_max,
            max_file_bytes=min(resolved_file, resolved_max),
        )


class RuntimeDiagnostics:
    """One process/instance writer with a private stable run namespace."""

    def __init__(
        self,
        *,
        member_id: str,
        instance_id: str | None = None,
        root: str | os.PathLike[str] | None = None,
        policy: DiagnosticsPolicy | None = None,
        project_id: str | None = None,
        launch_id: str | None = None,
        runtime: str | None = None,
        pid: int | None = None,
        known_secrets: Iterable[Any] = (),
        clock: Any | None = None,
    ) -> None:
        self.member_id = str(member_id or "unknown")
        self.instance_id = str(instance_id or "unknown")
        self.project_id = str(project_id) if project_id else None
        self.launch_id = str(launch_id) if launch_id else None
        self.runtime = str(runtime) if runtime else None
        self.pid = int(pid if pid is not None else os.getpid())
        self.policy = policy or DiagnosticsPolicy.create(root=root)
        self._now = clock or _now_local
        self._known_secrets = tuple(str(value) for value in known_secrets if value)
        self._lock = threading.RLock()
        self._closed = False
        self._enabled = True
        self._namespace_ready = False
        self._degraded_reported: set[str] = set()
        self.degradations: list[str] = []
        self._seq = 0
        self._current_index = 0
        self._current_path: Path | None = None
        self._current_size = 0
        self._closure_tasks: set[int] = set()
        self._closure_ranges: dict[str, list[int]] = {}
        self._closure_complete = True
        self._run_lease = None
        self._writes_since_cleanup = 0
        self.stop_reason: str | None = None

        started_at = _aware(self._now())
        utc = started_at.astimezone(timezone.utc)
        self.started_at = _timestamp(started_at)
        self.run_id = (
            f"{utc.strftime('%Y%m%dT%H%M%S%fZ')}-{self.pid}-{uuid4().hex[:8]}"
        )
        self._log_prefix = f"rtd-{uuid4().hex[:10]}"
        member_token = _safe_token(self.member_id, fallback="unknown-member")
        instance_token = _safe_token(self.instance_id, fallback="unknown-instance")
        run_token = _safe_token(self.run_id, fallback="run")
        self.root = Path(self.policy.root).expanduser().resolve()
        self.namespace = self.root / member_token / instance_token / run_token
        self.manifest_path = self.namespace / "manifest.json"
        self.rotation_path = self.namespace / "rotation.jsonl"
        self.retention_path = self.namespace / "retention.jsonl"
        self._ensure_namespace()
        if self._namespace_ready:
            try:
                from bridges.runtime_log_retention import NativeFile, pinned
                with pinned(self.namespace):
                    self._run_lease = NativeFile(self.namespace / "run.lease", write=True, create=True)
            except Exception:
                # Logging stays usable; without a lifetime lease this run is never auto-expirable.
                self._closure_complete = False

    @property
    def enabled(self) -> bool:
        return self._enabled and not self._closed

    def set_stop_reason(self, reason: str | None) -> None:
        self.stop_reason = str(reason) if reason else None

    def _degrade(self, kind: str, exc: BaseException | None = None) -> None:
        suffix = f" ({type(exc).__name__})" if exc is not None else ""
        marker = f"{kind}{suffix}"
        if marker not in self.degradations:
            self.degradations.append(marker)
        if marker in self._degraded_reported:
            return
        self._degraded_reported.add(marker)
        # Visible but deliberately free of exception text, paths from secrets,
        # prompts, argv or child output.
        try:
            print(
                f"[runtime-diagnostics] 本地诊断日志降级：{kind}{suffix}",
                file=sys.stderr,
            )
        except Exception:
            # A closed/broken console cannot replace the original product error.
            pass

    def _ensure_namespace(self) -> None:
        if self._namespace_ready:
            return
        try:
            root = self.root
            if root.exists() and (root.is_symlink() or not root.is_dir()):
                raise OSError("diagnostics root is not a regular directory")
            root.mkdir(parents=True, exist_ok=True)
            root_resolved = root.resolve()
            current = root_resolved
            relative = self.namespace.resolve().relative_to(root_resolved)
            for part in relative.parts:
                current = current / part
                try:
                    current.mkdir(exist_ok=True)
                except FileExistsError:
                    pass
                if current.is_symlink() or not current.is_dir():
                    raise OSError("diagnostics namespace component is unsafe")
                if not _is_relative_to(current.resolve(), root_resolved):
                    raise OSError("diagnostics namespace escapes its root")
            if not self.manifest_path.exists():
                manifest = {
                    "schema": SCHEMA,
                    "run_id": self.run_id,
                    "member_id": self.member_id,
                    "instance_id": self.instance_id,
                    "project_id": self.project_id,
                    "launch_id": self.launch_id,
                    "runtime": self.runtime,
                    "pid": self.pid,
                    "started_at": self.started_at,
                    "retention_days": self.policy.retention_days,
                    "max_bytes": self.policy.max_bytes,
                    "max_file_bytes": self.policy.max_file_bytes,
                }
                data = json.dumps(
                    manifest, ensure_ascii=False, sort_keys=True, indent=2
                ).encode("utf-8") + b"\n"
                fd = os.open(
                    str(self.manifest_path),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                try:
                    os.write(fd, data)
                finally:
                    os.close(fd)
            self._namespace_ready = True
        except Exception as exc:
            self._enabled = False
            self._degrade("namespace_unavailable", exc)

    def _base_record(
        self,
        *,
        event: str,
        severity: str,
        phase: str | None,
        stage: str | None,
        task_id: Any,
        message_id: Any,
        returncode: Any,
        timeout: bool | None,
        cancel_category: str | None,
        budgets: dict[str, Any] | None,
        related_log_id: str | None,
    ) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "event": str(event),
            "severity": str(severity),
            "phase": str(phase) if phase else None,
            "stage": str(stage) if stage else None,
            "project_id": self.project_id,
            "member_id": self.member_id,
            "instance_id": self.instance_id,
            "launch_id": self.launch_id,
            "pid": self.pid,
            "runtime": self.runtime,
            "task_id": task_id,
            "message_id": message_id,
            "returncode": returncode,
            "timeout": timeout,
            "cancel_category": cancel_category,
            "budgets": budgets or {},
            "related_log_id": str(related_log_id) if related_log_id else None,
        }

    def record_event(
        self,
        event: str,
        *,
        severity: str = "info",
        phase: str | None = None,
        stage: str | None = None,
        task_id: Any = None,
        message_id: Any = None,
        message: Any = None,
        returncode: Any = None,
        timeout: bool | None = None,
        cancel_category: str | None = None,
        budgets: dict[str, Any] | None = None,
        related_log_id: str | None = None,
        extra: Any = None,
        sensitive_values: Iterable[Any] = (),
    ) -> str | None:
        if not self.enabled:
            return None
        try:
            redactor = _Redactor((*self._known_secrets, *sensitive_values))
            record = self._base_record(
                event=event,
                severity=severity,
                phase=phase,
                stage=stage,
                task_id=task_id,
                message_id=message_id,
                returncode=returncode,
                timeout=timeout,
                cancel_category=cancel_category,
                budgets=budgets,
                related_log_id=related_log_id,
            )
            truncated_fields: set[str] = set()
            if message is not None:
                text, _changed = redactor.text(message)
                text, truncated = _truncate(text, MAX_EXCEPTION_MESSAGE_CHARS)
                record["message"] = text
                if truncated:
                    truncated_fields.add("message")
            if extra is not None:
                record["extra"] = _sanitize_nested(extra, redactor)
            record["integrity"] = {
                "redacted": redactor.changed,
                "redaction_kinds": sorted(redactor.kinds),
                "truncated": bool(truncated_fields),
                "truncated_fields": sorted(truncated_fields),
                "write_complete": True,
            }
            return self._write_event(record)
        except Exception as exc:
            self._degrade("event_format_failed", exc)
            return None

    def record_exception(
        self,
        exc: BaseException,
        *,
        event: str = "exception",
        severity: str = "error",
        phase: str | None = None,
        stage: str | None = None,
        task_id: Any = None,
        message_id: Any = None,
        message: Any = None,
        returncode: Any = None,
        timeout: bool | None = None,
        cancel_category: str | None = None,
        budgets: dict[str, Any] | None = None,
        related_log_id: str | None = None,
        extra: Any = None,
        sensitive_values: Iterable[Any] = (),
    ) -> str | None:
        if not self.enabled:
            return None
        try:
            protected = tuple(sensitive_values) + exception_sensitive_values(exc)
            try:
                exc.diagnostic_sensitive_values = tuple(dict.fromkeys(
                    value for value in protected if isinstance(value, str) and value
                ))
            except Exception:
                pass
            redactor = _Redactor((*self._known_secrets, *protected))
            exception, truncated_fields, _cycle = _capture_exception(exc, redactor)
            record = self._base_record(
                event=event,
                severity=severity,
                phase=phase,
                stage=stage,
                task_id=task_id,
                message_id=message_id,
                returncode=returncode,
                timeout=timeout,
                cancel_category=cancel_category,
                budgets=budgets,
                related_log_id=related_log_id,
            )
            record["exception"] = exception
            if message is not None:
                text, _changed = redactor.text(message)
                text, truncated = _truncate(text, MAX_EXCEPTION_MESSAGE_CHARS)
                record["message"] = text
                if truncated:
                    truncated_fields.add("message")
            if extra is not None:
                record["extra"] = _sanitize_nested(extra, redactor)
            record["integrity"] = {
                "redacted": redactor.changed,
                "redaction_kinds": sorted(redactor.kinds),
                "truncated": bool(truncated_fields),
                "truncated_fields": sorted(truncated_fields),
                "write_complete": True,
            }
            return self._write_event(record)
        except Exception as format_exc:
            self._degrade("exception_format_failed", format_exc)
            return self._write_minimal_exception(
                exc,
                event=event,
                severity=severity,
                stage=stage,
                task_id=task_id,
                related_log_id=related_log_id,
            )

    def _write_minimal_exception(
        self,
        exc: BaseException,
        *,
        event: str,
        severity: str,
        stage: str | None,
        task_id: Any,
        related_log_id: str | None,
    ) -> str | None:
        try:
            record = self._base_record(
                event=event,
                severity=severity,
                phase=None,
                stage=stage,
                task_id=task_id,
                message_id=None,
                returncode=None,
                timeout=None,
                cancel_category=None,
                budgets=None,
                related_log_id=related_log_id,
            )
            record["exception"] = {
                "relation": "primary",
                "type": type(exc).__name__,
                "message": "",
                "str_empty": True,
                "frames": [],
                "frames_total": 0,
                "frames_omitted": 0,
                "cause_chain": [],
                "chain_depth": 0,
                "chain_truncated": False,
                "chain_cycle": False,
            }
            record["integrity"] = {
                "redacted": True,
                "redaction_kinds": ["formatting_failure"],
                "truncated": True,
                "truncated_fields": ["exception"],
                "write_complete": True,
            }
            return self._write_event(record)
        except Exception as exc2:
            self._degrade("minimal_exception_write_failed", exc2)
            return None

    def sanitize_public_text(
        self,
        text: Any,
        *,
        sensitive_values: Iterable[Any] = (),
        max_chars: int | None = None,
    ) -> str:
        return sanitize_text(
            text,
            sensitive_values=(*self._known_secrets, *sensitive_values),
            max_chars=max_chars,
        )

    def _write_event(self, record: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None
        with self._lock:
            if not self.enabled:
                return None
            try:
                self._ensure_namespace()
                if not self.enabled:
                    return None
                self._seq += 1
                log_id = f"{self._log_prefix}-{self._seq:06d}"
                recorded_at = _aware(self._now())
                record["log_id"] = log_id
                record["recorded_at"] = _timestamp(recorded_at)
                record["run_id"] = self.run_id
                record["segment_file"] = None
                data = self._fit_event(record)
                if self._current_path is None:
                    self._start_segment_locked()
                if (
                    self._current_size > 0
                    and self._current_size + len(data) > self.policy.max_file_bytes
                ):
                    self._rotate_locked("max_file_bytes")
                record["segment_file"] = (
                    self._current_path.name if self._current_path is not None else None
                )
                data = self._fit_event(record)
                integrity = record.setdefault("integrity", {})
                if len(data) > self.policy.max_file_bytes:
                    integrity["capacity_soft_exceeded"] = True
                    integrity["truncated"] = True
                self._enforce_capacity_locked(incoming=len(data), record=record)
                data = _json_bytes(record)
                if not self._append_locked(self._current_path, data):
                    return None
                task = record.get("task_id")
                if task is not None:
                    if isinstance(task, str) and task.isascii() and task.isdigit():
                        task = int(task)
                    if (type(task) is int and 0 < task <= 2**53-1
                            and (task in self._closure_tasks or len(self._closure_tasks) < 1024)):
                        self._closure_tasks.add(task)
                    else:
                        self._closure_complete = False
                name = self._current_path.name
                if name in self._closure_ranges or len(self._closure_ranges) < 4096:
                    bounds = self._closure_ranges.setdefault(name, [self._seq, self._seq])
                    bounds[1] = self._seq
                else:
                    self._closure_complete = False
                self._current_size += len(data)
                self._writes_since_cleanup += 1
                if self._writes_since_cleanup >= 100:
                    self._writes_since_cleanup = 0
                    self._cleanup_expired_locked("retention")
                return log_id
            except Exception as exc:
                self._closure_complete = False
                self._degrade("event_write_failed", exc)
                return None

    def _fit_event(self, record: dict[str, Any]) -> bytes:
        data = _json_bytes(record)
        if len(data) <= MAX_EVENT_BYTES:
            return data
        integrity = record.setdefault("integrity", {})
        fields = set(integrity.get("truncated_fields") or [])
        # Source lines are optional context; all frames (file/line/function)
        # are retained first.
        exception = record.get("exception")
        if isinstance(exception, dict):
            for item in [exception, *list(exception.get("cause_chain") or [])]:
                if isinstance(item, dict):
                    for frame in item.get("frames") or []:
                        if isinstance(frame, dict):
                            frame.pop("source", None)
            fields.add("exception.frames.source")
        integrity["truncated"] = True
        integrity["truncated_fields"] = sorted(fields)
        data = _json_bytes(record)
        if len(data) <= MAX_EVENT_BYTES:
            return data
        # Next reduce overlong message text; frame locations and cause chain
        # remain, and every omission is visible.
        if isinstance(exception, dict):
            message, truncated = _truncate(
                str(exception.get("message") or ""), 4096
            )
            exception["message"] = message
            if truncated:
                fields.add("exception.message")
            for item in list(exception.get("cause_chain") or []):
                if isinstance(item, dict):
                    message, truncated = _truncate(
                        str(item.get("message") or ""), 4096
                    )
                    item["message"] = message
                    if truncated:
                        fields.add("exception.cause_chain.message")
        if record.get("message"):
            message, truncated = _truncate(str(record["message"]), 4096)
            record["message"] = message
            if truncated:
                fields.add("message")
        integrity["truncated_fields"] = sorted(fields)
        data = _json_bytes(record)
        if len(data) > MAX_EVENT_BYTES:
            integrity["event_size_soft_exceeded"] = True
            integrity["truncated"] = True
            data = _json_bytes(record)
        return data

    def _event_files_locked(self) -> list[Path]:
        try:
            files = [
                path
                for path in self.namespace.glob("events-*.jsonl")
                if path.is_file() and not path.is_symlink()
            ]
        except OSError:
            return []
        return sorted(files, key=lambda path: (path.stat().st_mtime_ns, path.name))

    def _start_segment_locked(self) -> None:
        try:
            existing = [
                int(match.group(1))
                for path in self.namespace.glob("events-*.jsonl")
                if (match := re.fullmatch(r"events-(\d+)\.jsonl", path.name))
            ]
        except OSError:
            existing = []
        self._current_index = (max(existing) if existing else 0) + 1
        self._current_path = self.namespace / f"events-{self._current_index:05d}.jsonl"
        if self._current_path.is_symlink():
            raise OSError("diagnostics segment is a symlink")
        try:
            self._current_size = (
                self._current_path.stat().st_size
                if self._current_path.exists()
                else 0
            )
        except OSError:
            self._current_size = 0

    def _rotate_locked(self, reason: str) -> None:
        old = self._current_path
        old_index = self._current_index
        self._current_index += 1
        new_path = self.namespace / f"events-{self._current_index:05d}.jsonl"
        if new_path.is_symlink():
            raise OSError("diagnostics rotation target is a symlink")
        self._current_path = new_path
        self._current_size = 0
        self._append_trace_locked(
            self.rotation_path,
            {
                "schema": SCHEMA,
                "recorded_at": _timestamp(_aware(self._now())),
                "action": "rotate",
                "reason": reason,
                "from": old.name if old else None,
                "to": new_path.name,
                "from_index": old_index,
                "to_index": self._current_index,
                "max_file_bytes": self.policy.max_file_bytes,
            },
        )
        self._cleanup_expired_locked("rotation")

    def _enforce_capacity_locked(self, *, incoming: int, record: dict[str, Any]) -> None:
        if self._defer_to_global_retention():
            if sum(self._safe_size(p) for p in self._event_files_locked()) + incoming > self.policy.max_bytes:
                record.setdefault("integrity", {})["capacity_soft_exceeded"] = True
            return
        files = self._event_files_locked()
        total = sum(self._safe_size(path) for path in files) + incoming
        if total <= self.policy.max_bytes:
            return
        for path in files:
            if path == self._current_path:
                continue
            size = self._safe_size(path)
            if not self._delete_segment_locked(path, "max_bytes"):
                break
            total -= size
            if total <= self.policy.max_bytes:
                return
        if total > self.policy.max_bytes:
            integrity = record.setdefault("integrity", {})
            integrity["capacity_soft_exceeded"] = True
            integrity["truncated"] = True
            fields = set(integrity.get("truncated_fields") or [])
            fields.add("capacity.max_bytes")
            integrity["truncated_fields"] = sorted(fields)

    def _cleanup_expired_locked(self, reason: str) -> None:
        if self._defer_to_global_retention():
            return
        now_ns = _aware(self._now()).timestamp() * 1_000_000_000
        cutoff_ns = now_ns - int(self.policy.retention_days * 86400 * 1_000_000_000)
        for path in self._event_files_locked():
            if path == self._current_path:
                continue
            try:
                modified_ns = path.stat().st_mtime_ns
            except OSError:
                continue
            if modified_ns >= cutoff_ns:
                continue
            self._delete_segment_locked(path, f"retention:{reason}")

    def _defer_to_global_retention(self) -> bool:
        marker = self.root / ".retention-policy.json"
        if not marker.exists() and not marker.is_symlink():
            return False
        try:
            from bridges.runtime_log_retention import pinned, read_json
            with pinned(self.root):
                value = read_json(marker, limit=64*1024)
            if value.get("schema") != "talk-log-retention-policy-1":
                return True
            return value.get("enabled") is not False and [self.project_id, self.member_id] in value.get("scopes", [])
        except Exception:
            # Unavailable policy never falls back to deleting active/recent segments.
            return True

    def _delete_segment_locked(self, path: Path, reason: str) -> bool:
        if path == self._current_path or path.name in {"manifest.json", "rotation.jsonl", "retention.jsonl"}:
            return False
        try:
            stat = path.stat()
        except OSError:
            return False
        tombstone_ok = self._append_trace_locked(
            self.retention_path,
            {
                "schema": SCHEMA,
                "recorded_at": _timestamp(_aware(self._now())),
                "action": "delete",
                "reason": reason,
                "file": path.name,
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "retention_days": self.policy.retention_days,
                "max_bytes": self.policy.max_bytes,
            },
        )
        if not tombstone_ok:
            return False
        try:
            path.unlink()
            return True
        except OSError as exc:
            self._degrade("retention_delete_failed", exc)
            return False

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _append_locked(self, path: Path | None, data: bytes) -> bool:
        if path is None:
            raise OSError("diagnostics segment is not initialized")
        if path.is_symlink():
            raise OSError("diagnostics segment is a symlink")
        fd = os.open(
            str(path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("diagnostics write returned no progress")
                view = view[written:]
        finally:
            os.close(fd)
        return True

    def _append_trace_locked(self, path: Path, payload: dict[str, Any]) -> bool:
        try:
            if path.is_symlink():
                raise OSError("diagnostics trace file is a symlink")
            return self._append_locked(path, _json_bytes(payload))
        except Exception as exc:
            self._degrade("trace_write_failed", exc)
            return False

    def cleanup_expired(self) -> list[str]:
        """Explicitly remove expired segments of this run (never other runs)."""
        if not self.enabled:
            return []
        with self._lock:
            removed: list[str] = []
            try:
                self._ensure_namespace()
                before = {path.name for path in self._event_files_locked()}
                self._cleanup_expired_locked("explicit")
                after = {path.name for path in self._event_files_locked()}
                removed = sorted(before - after)
            except Exception as exc:
                self._degrade("cleanup_failed", exc)
            return removed

    def _closed_receipt_extra(self) -> dict[str, Any]:
        """Code-owned source proof; extensions cannot override closure facts."""
        return {}

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._run_lease is None:
                return
            try:
                from bridges.runtime_log_retention import NativeFile, identity, pinned, write_json
                with pinned(self.namespace):
                    segments = []
                    for path in self._event_files_locked():
                        with NativeFile(path) as handle:
                            bounds = self._closure_ranges.get(path.name)
                            if bounds is None:
                                self._closure_complete = False
                                continue
                            segments.append({"name": path.name, "identity": identity(os.fstat(handle.fd)),
                                             "first": bounds[0], "last": bounds[1]})
                    if len(segments) > 4096:
                        self._closure_complete = False
                    value = {"schema": "talk-log-closed-1", "run_id": self.run_id,
                             "project_id": self.project_id, "member_id": self.member_id,
                             "instance_id": self.instance_id, "closed_at": _timestamp(_aware(self._now())),
                             "prefix": self._log_prefix, "task_ids": sorted(self._closure_tasks),
                             "complete": self._closure_complete, "segments": segments}
                    extra = self._closed_receipt_extra()
                    if not isinstance(extra, dict) or set(extra) & set(value):
                        raise ValueError("retention_receipt_extension_invalid")
                    value.update(extra)
                    write_json(self.namespace / "closed.json", value)
            except Exception as exc:
                self._degrade("close_receipt_failed", exc)
            finally:
                self._run_lease.close()
                self._run_lease = None

    @property
    def run_log_id_prefix(self) -> str:
        return self._log_prefix

    @classmethod
    def from_bridge_args(
        cls,
        args: Any,
        *,
        member_id: str,
        instance_id: str,
        runtime: str | None = None,
        project_id: str | None = None,
        launch_id: str | None = None,
        http_timeout_seconds: float | None = None,
        known_secrets: Iterable[Any] = (),
    ) -> "RuntimeDiagnostics | None":
        """Build a bridge writer without reading DB/config/whole environment."""
        del http_timeout_seconds  # kept as a keyword for the caller's clarity
        if bool(getattr(args, "runtime_log_disabled", False)):
            return None
        env_disabled = os.environ.get("TALK_RUNTIME_LOG_DISABLED", "").strip().lower()
        if env_disabled in {"1", "true", "yes", "on"}:
            return None
        root = getattr(args, "runtime_log_dir", None) or os.environ.get(
            "TALK_RUNTIME_LOG_DIR"
        )
        retention = getattr(args, "runtime_log_retention_days", None)
        if retention is None:
            retention = os.environ.get("TALK_RUNTIME_LOG_RETENTION_DAYS")
        max_bytes = getattr(args, "runtime_log_max_bytes", None)
        if max_bytes is None:
            max_bytes = os.environ.get("TALK_RUNTIME_LOG_MAX_BYTES")
        max_file_bytes = getattr(args, "runtime_log_max_file_bytes", None)
        if max_file_bytes is None:
            max_file_bytes = os.environ.get("TALK_RUNTIME_LOG_MAX_FILE_BYTES")
        policy = DiagnosticsPolicy.create(
            root=root,
            retention_days=retention,
            max_bytes=max_bytes,
            max_file_bytes=max_file_bytes,
        )
        return cls(
            member_id=member_id,
            instance_id=instance_id,
            policy=policy,
            project_id=project_id,
            launch_id=launch_id,
            runtime=runtime,
            known_secrets=known_secrets,
        )


class DiagnosticsQueryError(RuntimeError):
    """Raised for a malformed or out-of-root local diagnostics query."""


def _validate_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    value = str(ref).strip()
    if not value or not LOG_ID_RE.fullmatch(value):
        raise DiagnosticsQueryError("invalid log reference")
    return value


def _iter_log_files(root: Path, *, deadline: float | None = None) -> Iterable[Path]:
    """Yield regular, non-symlinked event files below the controlled root."""
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            if deadline is not None and time.monotonic() >= deadline:
                return
            current = Path(dirpath)
            safe_dirs: list[str] = []
            for name in dirnames:
                if deadline is not None and time.monotonic() >= deadline:
                    return
                candidate = current / name
                try:
                    if candidate.is_symlink() or not candidate.is_dir():
                        continue
                    if not _is_relative_to(candidate.resolve(), root.resolve()):
                        continue
                    safe_dirs.append(name)
                except OSError:
                    continue
            dirnames[:] = safe_dirs
            for name in filenames:
                if deadline is not None and time.monotonic() >= deadline:
                    return
                if not (name.startswith("events-") and name.endswith(".jsonl")):
                    continue
                path = current / name
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    if not _is_relative_to(path.resolve(), root.resolve()):
                        continue
                except OSError:
                    continue
                yield path
    except OSError:
        return


def query_records(
    root: str | os.PathLike[str] | None = None,
    *,
    ref: str | None = None,
    member_id: str | None = None,
    instance_id: str | None = None,
    task_id: Any = None,
    event: str | None = None,
    stage: str | None = None,
    limit: int = 20,
    max_files: int = 5000,
    max_bytes: int = 128 * 1024 * 1024,
    max_seconds: float = 10.0,
) -> dict[str, Any]:
    """Read only sanitized diagnostics records below a controlled root.

    The query never accepts a file path or resolves a log reference into a
    filesystem path.  It walks the controlled root, skips symlinks and returns
    at most ``limit`` matching records; scan limits are reported explicitly.
    """
    safe_ref = _validate_ref(ref)
    if int(limit) < 1 or int(limit) > 200:
        raise DiagnosticsQueryError("limit is outside 1..200")
    candidate_root = Path(root).expanduser() if root else DEFAULT_ROOT
    try:
        if candidate_root.is_symlink():
            raise DiagnosticsQueryError("diagnostics root must not be a symlink")
        resolved_root = candidate_root.resolve()
    except OSError as exc:
        raise DiagnosticsQueryError("diagnostics root is not readable") from exc
    if not resolved_root.exists() or not resolved_root.is_dir():
        raise DiagnosticsQueryError("diagnostics root does not exist")

    deadline = time.monotonic() + max(0.0, float(max_seconds))
    truncated = False
    files: list[Path] = []
    for path in _iter_log_files(resolved_root, deadline=deadline):
        if len(files) >= max_files or time.monotonic() >= deadline:
            truncated = True
            break
        try:
            files.append(path)
        except OSError:
            continue
    # Newest first is friendlier for a default summary; a reference query still
    # scans until it finds the single matching record.
    if time.monotonic() >= deadline:
        truncated = True
    files.sort(key=lambda path: _file_mtime_ns(path), reverse=True)

    records: list[dict[str, Any]] = []
    scanned_files = 0
    scanned_bytes = 0
    malformed = 0
    for path in files:
        if scanned_files >= max_files:
            truncated = True
            break
        if time.monotonic() >= deadline:
            truncated = True
            break
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if scanned_bytes + size > max_bytes:
            truncated = True
            break
        scanned_files += 1
        scanned_bytes += size
        try:
            rel = path.relative_to(resolved_root).as_posix()
        except ValueError:
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if time.monotonic() >= deadline:
                        truncated = True
                        break
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        malformed += 1
                        continue
                    if not isinstance(record, dict):
                        malformed += 1
                        continue
                    if safe_ref is not None and record.get("log_id") != safe_ref:
                        continue
                    if member_id is not None and record.get("member_id") != member_id:
                        continue
                    if instance_id is not None and record.get("instance_id") != instance_id:
                        continue
                    if task_id is not None and str(record.get("task_id")) != str(task_id):
                        continue
                    if event is not None and record.get("event") != event:
                        continue
                    if stage is not None and record.get("stage") != stage:
                        continue
                    record = dict(record)
                    record["_source_file"] = rel
                    records.append(record)
                    if safe_ref is not None:
                        break
                    if len(records) >= int(limit):
                        truncated = True
                        break
                if safe_ref is not None and records:
                    break
                if len(records) >= int(limit):
                    break
        except OSError:
            continue
    if safe_ref is not None and len(records) > 1:
        records = records[:1]
    return {
        "records": records,
        "scanned_files": scanned_files,
        "scanned_bytes": scanned_bytes,
        "malformed_lines": malformed,
        "truncated": truncated,
        "root": str(resolved_root),
    }


def _file_mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _record_exception_preview(record: dict[str, Any]) -> str:
    exception = record.get("exception")
    if not isinstance(exception, dict):
        return ""
    message = _compact_text(exception.get("message"), 200)
    type_name = str(exception.get("type") or "unknown")
    return f"{type_name}: {message}" if message else type_name


def record_summary_dict(record: dict[str, Any]) -> dict[str, Any]:
    """A bounded projection for default (non-detail) local queries."""
    exception = record.get("exception") if isinstance(record.get("exception"), dict) else {}
    chain = exception.get("cause_chain") if isinstance(exception, dict) else []
    budgets = record.get("budgets") if isinstance(record.get("budgets"), dict) else {}
    integrity = record.get("integrity") if isinstance(record.get("integrity"), dict) else {}
    return {
        "log_id": record.get("log_id"),
        "recorded_at": record.get("recorded_at"),
        "event": record.get("event"),
        "severity": record.get("severity"),
        "stage": record.get("stage"),
        "member_id": record.get("member_id"),
        "instance_id": record.get("instance_id"),
        "project_id": record.get("project_id"),
        "task_id": record.get("task_id"),
        "message_id": record.get("message_id"),
        "exception": _record_exception_preview(record) or None,
        "frames": exception.get("frames_total") if exception else None,
        "cause_depth": len(chain) if isinstance(chain, list) else 0,
        "related_log_id": record.get("related_log_id"),
        "returncode": record.get("returncode"),
        "timeout": record.get("timeout"),
        "cancel_category": record.get("cancel_category"),
        "budgets": {
            "cli_timeout_seconds": budgets.get("cli_timeout_seconds"),
            "http_timeout_seconds": budgets.get("http_timeout_seconds"),
            "task_lease_seconds": budgets.get("task_lease_seconds"),
            "task_heartbeat_interval_seconds": budgets.get(
                "task_heartbeat_interval_seconds"
            ),
            "managed_heartbeat_interval_seconds": budgets.get(
                "managed_heartbeat_interval_seconds"
            ),
            "task_poll_interval_seconds": budgets.get("task_poll_interval_seconds"),
            "mcp_wait_seconds": budgets.get("mcp_wait_seconds"),
        },
        "integrity": {
            "redacted": bool(integrity.get("redacted")),
            "truncated": bool(integrity.get("truncated")),
            "write_complete": bool(integrity.get("write_complete", True)),
        },
        "source_file": record.get("_source_file"),
    }


def format_record_summary(record: dict[str, Any]) -> str:
    summary = record_summary_dict(record)
    exception = summary.get("exception")
    lines = [
        f"log_id: {summary.get('log_id')}",
        f"time: {summary.get('recorded_at')}",
        f"event: {summary.get('event')}  severity: {summary.get('severity')}  "
        f"stage: {summary.get('stage')}",
        f"member: {summary.get('member_id')}  instance: {summary.get('instance_id')}  "
        f"task: {summary.get('task_id')}",
    ]
    if exception:
        lines.append(f"exception: {exception}")
        lines.append(
            f"frames: {summary.get('frames')}  cause_depth: {summary.get('cause_depth')}"
        )
    if summary.get("related_log_id"):
        lines.append(f"related_log_id: {summary.get('related_log_id')}")
    if summary.get("timeout") is not None or summary.get("returncode") is not None:
        lines.append(
            f"returncode: {summary.get('returncode')}  timeout: {summary.get('timeout')}  "
            f"cancel: {summary.get('cancel_category')}"
        )
    budgets = summary.get("budgets") or {}

    def budget(name: str) -> str:
        value = budgets.get(name)
        return "unknown" if value is None else f"{value}s"

    lines.append(
        "budgets: cli={cli} http={http} lease={lease} mcp={mcp}".format(
            cli=budget("cli_timeout_seconds"),
            http=budget("http_timeout_seconds"),
            lease=budget("task_lease_seconds"),
            mcp=budget("mcp_wait_seconds"),
        )
    )
    integrity = summary.get("integrity") or {}
    lines.append(
        "integrity: redacted={redacted} truncated={truncated} write_complete={complete}".format(
            redacted=str(bool(integrity.get("redacted"))).lower(),
            truncated=str(bool(integrity.get("truncated"))).lower(),
            complete=str(bool(integrity.get("write_complete", True))).lower(),
        )
    )
    lines.append(f"source: {summary.get('source_file')}")
    return "\n".join(lines)


def format_record_detail(record: dict[str, Any]) -> str:
    lines = [format_record_summary(record)]
    exception = record.get("exception")
    if not isinstance(exception, dict):
        return "\n".join(lines)

    def append_exception(item: dict[str, Any], *, prefix: str = "") -> None:
        relation = item.get("relation") or "primary"
        type_name = item.get("type") or "unknown"
        message = str(item.get("message") or "")
        lines.append("")
        lines.append(f"{prefix}traceback [{relation}] {type_name}")
        if message:
            lines.append(f"{prefix}message: {message}")
        for frame in item.get("frames") or []:
            if not isinstance(frame, dict):
                continue
            lines.append(
                f'{prefix}  File "{frame.get("file")}", line {frame.get("line")}, '
                f'in {frame.get("function")}'
            )
            source = str(frame.get("source") or "")
            if source:
                lines.append(f"{prefix}    {source}")
        if item.get("frames_omitted"):
            lines.append(
                f"{prefix}  ... {item.get('frames_omitted')} frame(s) omitted ..."
            )

    append_exception(exception)
    for cause in exception.get("cause_chain") or []:
        if isinstance(cause, dict):
            append_exception(cause, prefix="cause ")
    if exception.get("chain_truncated"):
        lines.append("cause chain truncated at the configured depth")
    if exception.get("chain_cycle"):
        lines.append("cause chain contains a cycle marker")
    return "\n".join(lines)
