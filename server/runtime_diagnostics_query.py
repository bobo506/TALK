"""Controlled, human-only runtime log scanning and network projection.

The persisted ``talk-runtime-diagnostics-1`` records are treated as untrusted
input.  This module provides:

* a bounded, no-follow scanner for a configured ``events-<digits>.jsonl`` tree;
* an inventory/hash layer used by the stable cursor contract;
* a strict allow-list projection and a second path/secret scrub for every free
  text field that can leave the server.

It deliberately does **not** reuse ``query_records()`` for API responses: that
local helper has no network pagination contract, no safe-open race checks and
its raw result contains server paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from bridges.runtime_diagnostics import LOG_ID_RE, SCHEMA, sanitize_text
from server.runtime_diagnostics_models import (
    RuntimeLogBudgets,
    RuntimeLogCause,
    RuntimeLogDetail,
    RuntimeLogExceptionDetail,
    RuntimeLogExceptionSummary,
    RuntimeLogFrame,
    RuntimeLogIntegrityDetail,
    RuntimeLogIntegritySummary,
    RuntimeLogPageInfo,
    RuntimeLogQuery,
    RuntimeLogRecordDetail,
    RuntimeLogRecordSummary,
    RuntimeLogScan,
    RuntimeLogScope,
)

MAX_FILES = 5000
MAX_BYTES = 128 * 1024 * 1024
MAX_SECONDS = 10.0
MAX_PAGE_LIMIT = 50
DEFAULT_PAGE_LIMIT = 20
MAX_RANGE = timedelta(days=31)
MAX_SAFE_INTEGER = 2**53 - 1
MAX_TASK_ID = MAX_SAFE_INTEGER
MAX_MESSAGE_CHARS = 16 * 1024
MAX_FIELD_CHARS = 4096
MAX_IDENTIFIER_CHARS = 128
MAX_PREVIEW_CHARS = 200
MAX_NETWORK_FRAMES = 4096
MAX_NETWORK_CAUSES = 64
MAX_RECORD_LINE_BYTES = 2 * 1024 * 1024
_EVENT_FILE_RE = re.compile(r"^events-\d+\.jsonl$")
_SAFE_FILTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SEVERITIES = ("error", "info", "warning")
_C0_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PATH_PATTERNS = (
    # UNC / Windows extended forms (two leading separators).
    re.compile(r"(?:\\\\|//)[^\r\n\"'<>|]+"),
    # Windows drive absolute path.
    re.compile(r"(?i)\b[A-Za-z]:(?:\\|/)[^\r\n\"'<>|]*"),
    # Any POSIX absolute path (including /srv, /mnt, /data, /home).
    re.compile(r"(?<![\w:/])/(?:[^\s/\\\x00-\x1f\"'<>|,;:{}()\[\]]+)(?:/[^\s/\\\x00-\x1f\"'<>|,;:{}()\[\]]+)*"),
)


class RuntimeDiagnosticsError(Exception):
    """A stable public error code; never carries an internal path or text."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def unavailable_error() -> RuntimeDiagnosticsError:
    return RuntimeDiagnosticsError("diagnostics_unavailable", 503)


def scan_incomplete_error() -> RuntimeDiagnosticsError:
    return RuntimeDiagnosticsError("diagnostics_scan_incomplete", 503)


def projection_failed_error() -> RuntimeDiagnosticsError:
    return RuntimeDiagnosticsError("diagnostics_projection_failed", 503)


class ProjectionFailure(ValueError):
    """Raised when a record cannot be projected without leaking raw input."""


@dataclass(frozen=True)
class Source:
    project_id: str
    member_id: str
    root: Path


@dataclass(frozen=True)
class ScanLimits:
    max_files: int = MAX_FILES
    max_bytes: int = MAX_BYTES
    max_seconds: float = MAX_SECONDS


@dataclass(frozen=True)
class QuerySpec:
    ref: str | None
    since: datetime | None
    until: datetime | None
    instance_id: str | None
    launch_id: str | None
    task_id: int | None
    event: str | None
    stage: str | None
    severity: tuple[str, ...] | None
    limit: int
    cursor: str | None = None
    provided: frozenset[str] = frozenset()

    @property
    def exact_ref(self) -> bool:
        return self.ref is not None


@dataclass(frozen=True)
class FileSnapshot:
    relative_path: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    digest: str


@dataclass
class ScanOutcome:
    complete: bool = False
    truncated: bool = False
    scanned_files: int = 0
    scanned_bytes: int = 0
    malformed_lines: int = 0
    unavailable_sources: int = 0
    source_changed: bool = False
    availability_failed: bool = False
    warnings: list[str] = field(default_factory=list)
    inventory_hash: str | None = None


class _ScanBudget:
    def __init__(self, limits: ScanLimits) -> None:
        self.limits = limits
        self.started = time.monotonic()
        self.deadline = self.started + max(0.0, float(limits.max_seconds))
        self.files = 0
        self.bytes = 0
        self.truncated = False

    def expired(self) -> bool:
        if time.monotonic() >= self.deadline:
            self.truncated = True
            return True
        return False

    def note_candidate(self) -> bool:
        if self.files >= self.limits.max_files:
            self.truncated = True
            return False
        self.files += 1
        return True

    def note_bytes(self, count: int) -> bool:
        if count < 0:
            return False
        if self.bytes + count > self.limits.max_bytes:
            self.truncated = True
            return False
        self.bytes += count
        return True


def _is_link_or_reparse(st: os.stat_result) -> bool:
    if stat.S_ISLNK(st.st_mode):
        return True
    attributes = getattr(st, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse)


def _root_chain(root: Path) -> tuple[tuple[str, int, int, int], ...]:
    """Lstat every configured root component, rejecting links/reparse points."""
    result: list[tuple[str, int, int, int]] = []
    current = Path(os.path.abspath(root))
    seen: set[str] = set()
    while True:
        key = os.path.normcase(str(current))
        if key in seen:
            break
        seen.add(key)
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise unavailable_error() from exc
        if _is_link_or_reparse(st) or not stat.S_ISDIR(st.st_mode):
            raise unavailable_error()
        result.append((str(current), st.st_dev, st.st_ino, st.st_mode))
        parent = current.parent
        if parent == current:
            break
        current = parent
    return tuple(reversed(result))


def _same_root_chain(
    left: tuple[tuple[str, int, int, int], ...],
    right: tuple[tuple[str, int, int, int], ...],
) -> bool:
    return left == right


def _assert_root_readable(root: Path) -> None:
    """A configured root that cannot be listed is unavailable, not an empty page."""
    try:
        with os.scandir(root) as scan:
            next(scan, None)
    except OSError as exc:
        raise unavailable_error() from exc


def _inside_root(root: Path, path: Path) -> bool:
    try:
        root_abs = os.path.abspath(root)
        path_abs = os.path.abspath(path)
        common = os.path.commonpath([root_abs, path_abs])
    except (OSError, ValueError):
        return False
    return os.path.normcase(common) == os.path.normcase(root_abs)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


class _EntryChanged(OSError):
    """Positive evidence of entry replacement, distinct from unreadable IO."""


def _note_entry_failure(outcome: ScanOutcome, exc: OSError) -> None:
    outcome.unavailable_sources += 1
    if isinstance(exc, (FileNotFoundError, _EntryChanged)):
        outcome.source_changed = True
    else:
        # Permission/unsafe-open/other IO errors do not prove that a previous
        # snapshot changed. Cursor reads must report unavailable, not stale.
        outcome.availability_failed = True


def _walk_event_files(
    root: Path,
    budget: _ScanBudget,
    outcome: ScanOutcome,
) -> list[tuple[Path, os.stat_result]]:
    candidates: list[tuple[Path, os.stat_result]] = []
    stack = [root]
    while stack:
        if budget.expired():
            outcome.truncated = True
            break
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                for entry in scan:
                    if budget.expired():
                        outcome.truncated = True
                        break
                    try:
                        # ``DirEntry.stat`` on Windows is populated from
                        # FindFirstFile and does not carry the file identity;
                        # use lstat so the later fstat check is meaningful.
                        st = os.lstat(entry.path)
                    except OSError as exc:
                        _note_entry_failure(outcome, exc)
                        continue
                    if _is_link_or_reparse(st):
                        # Any link/reparse point below the controlled root is
                        # skipped and makes the scan explicitly incomplete.
                        outcome.unavailable_sources += 1
                        outcome.availability_failed = True
                        continue
                    path = Path(entry.path)
                    if stat.S_ISDIR(st.st_mode):
                        if _inside_root(root, path):
                            stack.append(path)
                        else:
                            outcome.unavailable_sources += 1
                        continue
                    if not stat.S_ISREG(st.st_mode):
                        continue
                    if not _EVENT_FILE_RE.fullmatch(entry.name):
                        continue
                    if not _inside_root(root, path):
                        outcome.unavailable_sources += 1
                        continue
                    if not budget.note_candidate():
                        break
                    candidates.append((path, st))
        except OSError as exc:
            _note_entry_failure(outcome, exc)
            continue
        if budget.truncated:
            break
    candidates.sort(key=lambda item: _relative(item[0], root))
    return candidates


def _open_checked(path: Path, expected: os.stat_result) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if no_follow:
        flags |= no_follow
    try:
        fd = os.open(str(path), flags)
    except OSError:
        raise
    try:
        actual = os.fstat(fd)
        if not stat.S_ISREG(actual.st_mode):
            raise _EntryChanged("not a regular file")
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise _EntryChanged("identity changed")
        if (actual.st_size, actual.st_mtime_ns) != (
            expected.st_size,
            expected.st_mtime_ns,
        ):
            raise _EntryChanged("metadata changed")
    except Exception:
        os.close(fd)
        raise
    return fd, actual


def _opened_final_path(fd: int) -> Path:
    """Verify the opened object, rather than re-resolving its requested name.

    Windows GetFinalPathNameByHandleW resolves junctions for the actual handle.
    Linux exposes the same opened-object evidence through /proc/self/fd. Other
    platforms fail closed until an equivalent verified implementation exists.
    """
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        function = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
        function.argtypes = (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD)
        function.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        length = function(wintypes.HANDLE(msvcrt.get_osfhandle(fd)), buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise OSError("opened path unavailable")
        final = buffer.value
        if final.startswith("\\\\?\\UNC\\"):
            raise OSError("nonlocal opened path")
        if final.startswith("\\\\?\\"):
            final = final[4:]
        return Path(final)
    if os.name == "posix" and Path("/proc/self/fd").is_dir():
        return Path(os.readlink(f"/proc/self/fd/{fd}"))
    raise OSError("opened path verification unsupported")


def _verify_opened_scope(fd: int, root: Path, path: Path) -> None:
    try:
        # Reject nested links too: checking only the configured root misses a
        # directory replaced between enumeration and opening its children.
        _root_chain(path.parent)
        if _is_link_or_reparse(os.lstat(path)):
            raise OSError("unsafe opened entry")
        approved_root = Path(os.path.realpath(root))
        final = _opened_final_path(fd)
        if not _inside_root(approved_root, final):
            raise OSError("opened object outside configured source")
        if os.path.normcase(str(final)) != os.path.normcase(os.path.realpath(path)):
            raise OSError("opened object no longer matches entry")
    except RuntimeDiagnosticsError as exc:
        raise OSError("opened ancestry unsafe") from exc


def _read_event_file(
    root: Path,
    path: Path,
    expected: os.stat_result,
    budget: _ScanBudget,
    outcome: ScanOutcome,
    visitor: Callable[[dict[str, Any]], None] | None,
) -> FileSnapshot | None:
    if budget.expired():
        outcome.truncated = True
        return None
    if not budget.note_bytes(expected.st_size):
        outcome.truncated = True
        return None
    try:
        fd, opened = _open_checked(path, expected)
        try:
            _verify_opened_scope(fd, root, path)
        except Exception:
            os.close(fd)
            raise
    except OSError as exc:
        _note_entry_failure(outcome, exc)
        return None
    digest = hashlib.sha256()
    actual_bytes = 0
    file_ok = True
    discarding_long_line = False
    try:
        with os.fdopen(fd, "rb", closefd=True) as stream:
            while actual_bytes < opened.st_size:
                if budget.expired():
                    outcome.truncated = True
                    file_ok = False
                    break
                remaining = opened.st_size - actual_bytes
                # Never read appended bytes beyond the size already charged
                # to the budget; never allocate an unbounded JSONL line.
                line = (
                    stream.read(min(64 * 1024, remaining))
                    if visitor is None
                    else stream.readline(min(MAX_RECORD_LINE_BYTES + 1, remaining))
                )
                if not line:
                    break
                actual_bytes += len(line)
                if actual_bytes > opened.st_size:
                    # The file grew while being read.
                    outcome.source_changed = True
                    file_ok = False
                    break
                digest.update(line)
                if visitor is None:
                    continue
                if discarding_long_line:
                    discarding_long_line = not line.endswith(b"\n")
                    continue
                if len(line) > MAX_RECORD_LINE_BYTES:
                    outcome.malformed_lines += 1
                    discarding_long_line = not line.endswith(b"\n")
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    # Includes JSONDecodeError, bad UTF-8, recursion limits and
                    # any other malformed-line shape; always count, never echo.
                    outcome.malformed_lines += 1
                    continue
                if not isinstance(record, dict) or not _valid_record_identity(record):
                    outcome.malformed_lines += 1
                    continue
                visitor(record)
            after = os.fstat(stream.fileno())
        try:
            final = os.lstat(path)
        except OSError as exc:
            _note_entry_failure(outcome, exc)
            file_ok = False
            final = None
        if after.st_size != opened.st_size or after.st_mtime_ns != opened.st_mtime_ns:
            outcome.source_changed = True
            file_ok = False
        if final is not None:
            if _is_link_or_reparse(final):
                outcome.unavailable_sources += 1
                outcome.availability_failed = True
                file_ok = False
            elif (
                final.st_dev,
                final.st_ino,
                final.st_size,
                final.st_mtime_ns,
            ) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            ):
                outcome.source_changed = True
                file_ok = False
    except OSError as exc:
        _note_entry_failure(outcome, exc)
        file_ok = False
    outcome.scanned_bytes += actual_bytes
    if not file_ok:
        return None
    if actual_bytes != opened.st_size:
        outcome.source_changed = True
        return None
    return FileSnapshot(
        relative_path=_relative(path, root),
        device=opened.st_dev,
        inode=opened.st_ino,
        size=opened.st_size,
        mtime_ns=opened.st_mtime_ns,
        ctime_ns=expected.st_ctime_ns,
        digest=digest.hexdigest(),
    )


def _inventory_digest(snapshots: Iterable[FileSnapshot]) -> str:
    payload = [
        [
            item.relative_path,
            item.device,
            item.inode,
            item.size,
            item.mtime_ns,
            item.ctime_ns,
            item.digest,
        ]
        for item in sorted(snapshots, key=lambda item: item.relative_path)
    ]
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def scan_source(
    source: Source,
    *,
    limits: ScanLimits | None = None,
    visitor: Callable[[dict[str, Any]], None] | None = None,
) -> ScanOutcome:
    """Scan one configured source and verify its inventory before returning.

    Source-level availability failures raise ``diagnostics_unavailable``.  A
    budget, bad record, link/reparse entry or observed file/root change is
    reported through ``ScanOutcome.complete`` instead, so the caller can decide
    between a conservative incomplete page and a 409/503 contract response.
    """
    limits = limits or ScanLimits()
    outcome = ScanOutcome()
    root = Path(os.path.abspath(source.root))
    chain = _root_chain(root)
    _assert_root_readable(root)
    budget = _ScanBudget(limits)
    candidates = _walk_event_files(root, budget, outcome)
    snapshots: list[FileSnapshot] = []
    for path, expected in candidates:
        snapshot = _read_event_file(root, path, expected, budget, outcome, visitor)
        outcome.scanned_files += 1
        if snapshot is not None:
            snapshots.append(snapshot)
    initial_hash = _inventory_digest(snapshots)

    # Re-walk and re-read the same inventory.  This is deliberately inside the
    # same file/byte/time budget and is what detects append, delete, rotation,
    # replacement or truncation between pages.
    verify_outcome = ScanOutcome()
    verify_candidates = _walk_event_files(root, budget, verify_outcome)
    verify_snapshots: list[FileSnapshot] = []
    for path, expected in verify_candidates:
        snapshot = _read_event_file(
            root, path, expected, budget, verify_outcome, None
        )
        if snapshot is not None:
            verify_snapshots.append(snapshot)
    verify_hash = _inventory_digest(verify_snapshots)
    if (
        verify_hash != initial_hash
        and not outcome.availability_failed
        and not verify_outcome.availability_failed
        and not budget.truncated
    ):
        outcome.source_changed = True
    outcome.truncated = outcome.truncated or budget.truncated
    outcome.malformed_lines += verify_outcome.malformed_lines
    outcome.unavailable_sources += verify_outcome.unavailable_sources
    outcome.source_changed = outcome.source_changed or verify_outcome.source_changed
    outcome.availability_failed = outcome.availability_failed or verify_outcome.availability_failed
    outcome.scanned_bytes += verify_outcome.scanned_bytes
    try:
        final_chain = _root_chain(root)
    except RuntimeDiagnosticsError:
        # The configured source itself disappeared or was replaced by an
        # unsafe link while being scanned: that is an unavailable source, not
        # a cursor conflict or an empty log set.
        raise unavailable_error()
    if not _same_root_chain(chain, final_chain):
        raise unavailable_error()
    outcome.inventory_hash = initial_hash if initial_hash == verify_hash else None
    if outcome.truncated:
        outcome.warnings.append("scan_limited")
    if outcome.malformed_lines:
        outcome.warnings.append("records_unreadable")
    if outcome.unavailable_sources:
        outcome.warnings.append("source_entries_skipped")
    if outcome.source_changed:
        outcome.warnings.append("source_changed")
    outcome.complete = (
        outcome.inventory_hash is not None
        and not outcome.truncated
        and not outcome.malformed_lines
        and not outcome.unavailable_sources
        and not outcome.source_changed
    )
    return outcome


def _valid_record_identity(record: dict[str, Any]) -> bool:
    if record.get("schema") != SCHEMA:
        return False
    log_id = record.get("log_id")
    if not isinstance(log_id, str) or not LOG_ID_RE.fullmatch(log_id):
        return False
    parsed = parse_recorded_at(record.get("recorded_at"))
    return parsed is not None


def parse_recorded_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def record_sort_key(record: dict[str, Any]) -> tuple[datetime, str] | None:
    recorded = parse_recorded_at(record.get("recorded_at"))
    log_id = record.get("log_id")
    if recorded is None or not isinstance(log_id, str):
        return None
    return recorded, log_id


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _query_utc_text(value: datetime) -> str:
    text = value.astimezone(timezone.utc).isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def canonical_query_dict(query: QuerySpec) -> dict[str, Any]:
    return {
        "since": _query_utc_text(query.since) if query.since is not None else None,
        "until": _query_utc_text(query.until) if query.until is not None else None,
        "instance_id": query.instance_id,
        "launch_id": query.launch_id,
        "task_id": query.task_id,
        "event": query.event,
        "stage": query.stage,
        "severity": list(query.severity) if query.severity is not None else None,
        "ref": query.ref,
    }


def query_model(query: QuerySpec) -> RuntimeLogQuery:
    return RuntimeLogQuery(**canonical_query_dict(query))


def _hash_json(value: Any) -> str:
    data = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def filter_hash(query: QuerySpec) -> str:
    payload = canonical_query_dict(query)
    payload["limit"] = query.limit
    return _hash_json(payload)


def scope_hash(project_id: str, member_id: str) -> str:
    return _hash_json({"project_id": project_id, "member_id": member_id})


def _scrub_paths(text: str) -> str:
    for pattern in _PATH_PATTERNS:
        text = pattern.sub("[PATH]", text)
    return text


def _scrub_text(
    value: Any,
    *,
    field: str,
    max_chars: int = MAX_FIELD_CHARS,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, int, float, bool)):
        raise ProjectionFailure(field)
    text = str(value)
    if "\x00" in text:
        raise ProjectionFailure(field)
    try:
        text = sanitize_text(text)
    except Exception as exc:  # defensive: never fall back to the raw value
        raise ProjectionFailure(field) from exc
    text = _scrub_paths(text)
    text = _C0_RE.sub(" ", text)
    if len(text) > max_chars:
        raise ProjectionFailure(field)
    return text


def _scrub_required(
    value: Any,
    *,
    field: str,
    max_chars: int = MAX_FIELD_CHARS,
) -> str:
    text = _scrub_text(value, field=field, max_chars=max_chars)
    if text is None or text == "":
        raise ProjectionFailure(field)
    return text


def _file_name(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProjectionFailure("file_name")
    normalized = value.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name in {"", ".", ".."} or ":" in name:
        raise ProjectionFailure("file_name")
    cleaned = _scrub_text(name, field="file_name", max_chars=512)
    if cleaned is None or cleaned in {"", ".", ".."}:
        raise ProjectionFailure("file_name")
    if "/" in cleaned or "\\" in cleaned or ":" in cleaned:
        raise ProjectionFailure("file_name")
    return cleaned


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed < minimum or parsed > maximum:
        return None
    return parsed


def _bounded_number(value: Any, minimum: float, maximum: float) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value < minimum or value > maximum:
        return None
    return value


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_log_ref(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not LOG_ID_RE.fullmatch(value):
        raise ProjectionFailure("related_log_id")
    return value


def _budgets(value: Any) -> RuntimeLogBudgets:
    source = value if isinstance(value, dict) else {}
    return RuntimeLogBudgets(
        cli_timeout_seconds=_bounded_number(
            source.get("cli_timeout_seconds"), 0, 10**9
        ),
        http_timeout_seconds=_bounded_number(
            source.get("http_timeout_seconds"), 0, 10**9
        ),
        task_lease_seconds=_bounded_number(
            source.get("task_lease_seconds"), 0, 10**9
        ),
        task_heartbeat_interval_seconds=_bounded_number(
            source.get("task_heartbeat_interval_seconds"), 0, 10**9
        ),
        managed_heartbeat_interval_seconds=_bounded_number(
            source.get("managed_heartbeat_interval_seconds"), 0, 10**9
        ),
        task_poll_interval_seconds=_bounded_number(
            source.get("task_poll_interval_seconds"), 0, 10**9
        ),
        mcp_wait_seconds=_bounded_number(source.get("mcp_wait_seconds"), 0, 10**9),
    )


def _integrity_summary(value: Any) -> RuntimeLogIntegritySummary:
    source = value if isinstance(value, dict) else {}
    return RuntimeLogIntegritySummary(
        redacted=_optional_bool(source.get("redacted")),
        truncated=_optional_bool(source.get("truncated")),
        write_complete=_optional_bool(source.get("write_complete")),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    if len(value) > 100:
        raise ProjectionFailure("integrity")
    result: list[str] = []
    for item in value:
        text = _scrub_text(item, field="integrity", max_chars=128)
        if text is not None:
            result.append(text)
    return result


def _integrity_detail(value: Any) -> RuntimeLogIntegrityDetail:
    source = value if isinstance(value, dict) else {}
    return RuntimeLogIntegrityDetail(
        redacted=_optional_bool(source.get("redacted")),
        redaction_kinds=_string_list(source.get("redaction_kinds")),
        truncated=_optional_bool(source.get("truncated")),
        truncated_fields=_string_list(source.get("truncated_fields")),
        write_complete=_optional_bool(source.get("write_complete")),
        capacity_soft_exceeded=_optional_bool(source.get("capacity_soft_exceeded")),
        event_size_soft_exceeded=_optional_bool(
            source.get("event_size_soft_exceeded")
        ),
    )


def _exception_summary(value: Any) -> RuntimeLogExceptionSummary | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProjectionFailure("exception")
    type_text = _scrub_text(value.get("type"), field="type", max_chars=256)
    message = _scrub_text(
        value.get("message"), field="message", max_chars=MAX_MESSAGE_CHARS
    )
    preview = _compact_text(message or "", MAX_PREVIEW_CHARS)
    chain = value.get("cause_chain")
    cause_depth = len(chain) if isinstance(chain, list) else 0
    return RuntimeLogExceptionSummary(
        type=type_text,
        message_preview=preview,
        frames_total=_bounded_int(value.get("frames_total"), 0, 10**9),
        cause_depth=_bounded_int(cause_depth, 0, 10**6),
    )


def _frames(value: Any) -> list[RuntimeLogFrame]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProjectionFailure("frames")
    if len(value) > MAX_NETWORK_FRAMES:
        raise ProjectionFailure("frames")
    result: list[RuntimeLogFrame] = []
    for item in value:
        if not isinstance(item, dict):
            raise ProjectionFailure("frames")
        file_name = _file_name(item.get("file"))
        line = _bounded_int(item.get("line"), 0, 2**31)
        function = _scrub_text(item.get("function"), field="function", max_chars=512)
        result.append(RuntimeLogFrame(file_name=file_name, line=line, function=function))
    return result


def _exception_detail(value: Any) -> RuntimeLogExceptionDetail | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProjectionFailure("exception")
    chain_raw = value.get("cause_chain")
    if chain_raw is None:
        chain_raw = []
    if not isinstance(chain_raw, list):
        raise ProjectionFailure("cause_chain")
    if len(chain_raw) > MAX_NETWORK_CAUSES:
        raise ProjectionFailure("cause_chain")
    chain: list[RuntimeLogCause] = []
    for item in chain_raw:
        if not isinstance(item, dict):
            raise ProjectionFailure("cause_chain")
        message = _scrub_text(
            item.get("message"), field="message", max_chars=MAX_MESSAGE_CHARS
        )
        chain.append(
            RuntimeLogCause(
                relation=_scrub_text(
                    item.get("relation"), field="relation", max_chars=64
                ),
                type=_scrub_text(item.get("type"), field="type", max_chars=256),
                message=message or "",
                frames_total=_bounded_int(item.get("frames_total"), 0, 10**9),
                frames_omitted=_bounded_int(item.get("frames_omitted"), 0, 10**9),
                frames=_frames(item.get("frames")),
            )
        )
    message = _scrub_text(
        value.get("message"), field="message", max_chars=MAX_MESSAGE_CHARS
    )
    return RuntimeLogExceptionDetail(
        type=_scrub_text(value.get("type"), field="type", max_chars=256),
        message=message or "",
        str_empty=_optional_bool(value.get("str_empty")),
        message_error=_optional_bool(value.get("message_error")),
        frames_total=_bounded_int(value.get("frames_total"), 0, 10**9),
        frames_omitted=_bounded_int(value.get("frames_omitted"), 0, 10**9),
        frames=_frames(value.get("frames")),
        cause_chain=chain,
        chain_depth=_bounded_int(value.get("chain_depth"), 0, 10**6),
        chain_truncated=_optional_bool(value.get("chain_truncated")),
        chain_cycle=_optional_bool(value.get("chain_cycle")),
        has_explicit_cause=_optional_bool(value.get("has_explicit_cause")),
        context_present=_optional_bool(value.get("context_present")),
        context_suppressed=_optional_bool(value.get("context_suppressed")),
    )


def _compact_text(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) > limit:
        return compact[: max(0, limit - 1)].rstrip() + "…"
    return compact


def _common_record_values(
    record: dict[str, Any],
    scope: tuple[str, str],
) -> dict[str, Any]:
    log_id = record.get("log_id")
    if not isinstance(log_id, str) or not LOG_ID_RE.fullmatch(log_id):
        raise ProjectionFailure("log_id")
    recorded_at = parse_recorded_at(record.get("recorded_at"))
    if recorded_at is None:
        raise ProjectionFailure("recorded_at")
    severity = _scrub_required(record.get("severity"), field="severity", max_chars=32)
    if severity not in _SEVERITIES:
        raise ProjectionFailure("severity")
    project_id, member_id = scope
    if record.get("project_id") != project_id or record.get("member_id") != member_id:
        raise ProjectionFailure("scope")
    return {
        "log_id": log_id,
        "recorded_at": _utc_text(recorded_at),
        "event": _scrub_required(record.get("event"), field="event", max_chars=128),
        "severity": severity,
        "stage": _scrub_text(record.get("stage"), field="stage", max_chars=128),
        "project_id": project_id,
        "member_id": member_id,
        "instance_id": _scrub_text(
            record.get("instance_id"), field="instance_id", max_chars=MAX_IDENTIFIER_CHARS
        ),
        "launch_id": _scrub_text(
            record.get("launch_id"), field="launch_id", max_chars=MAX_IDENTIFIER_CHARS
        ),
        "task_id": _bounded_int(record.get("task_id"), 1, MAX_TASK_ID),
        "related_log_id": _optional_log_ref(record.get("related_log_id")),
        "returncode": _bounded_int(record.get("returncode"), -(2**31), 2**31 - 1),
        "timeout": _optional_bool(record.get("timeout")),
        "cancel_category": _scrub_text(
            record.get("cancel_category"), field="cancel_category", max_chars=128
        ),
        "budgets": _budgets(record.get("budgets")),
    }


def project_summary(
    record: dict[str, Any],
    scope: tuple[str, str],
) -> RuntimeLogRecordSummary:
    values = _common_record_values(record, scope)
    return RuntimeLogRecordSummary(
        **values,
        exception=_exception_summary(record.get("exception")),
        integrity=_integrity_summary(record.get("integrity")),
    )


def project_detail(
    record: dict[str, Any],
    scope: tuple[str, str],
) -> RuntimeLogRecordDetail:
    values = _common_record_values(record, scope)
    return RuntimeLogRecordDetail(
        **values,
        exception=_exception_detail(record.get("exception")),
        integrity=_integrity_detail(record.get("integrity")),
    )


def scan_model(outcome: ScanOutcome) -> RuntimeLogScan:
    return RuntimeLogScan(
        complete=bool(outcome.complete),
        truncated=bool(outcome.truncated),
        scanned_files=max(0, int(outcome.scanned_files)),
        scanned_bytes=max(0, int(outcome.scanned_bytes)),
        malformed_lines=max(0, int(outcome.malformed_lines)),
        unavailable_sources=max(0, int(outcome.unavailable_sources)),
    )


def scope_model(project_id: str, member_id: str) -> RuntimeLogScope:
    return RuntimeLogScope(project_id=project_id, member_id=member_id)


def page_model(
    *,
    project_id: str,
    member_id: str,
    query: QuerySpec,
    records: list[RuntimeLogRecordSummary],
    snapshot_until: str | None,
    has_more: bool,
    next_cursor: str | None,
    outcome: ScanOutcome,
) -> Any:
    # Imported lazily to keep this module's pure scanning helpers easy to test.
    from server.runtime_diagnostics_models import RuntimeLogPage

    return RuntimeLogPage(
        scope=scope_model(project_id, member_id),
        query=query_model(query),
        records=records,
        page=RuntimeLogPageInfo(
            limit=query.limit,
            snapshot_until=snapshot_until,
            has_more=bool(has_more),
            next_cursor=next_cursor,
        ),
        scan=scan_model(outcome),
        warnings=_stable_warnings(outcome),
    )


def detail_model(
    *,
    project_id: str,
    member_id: str,
    record: RuntimeLogRecordDetail,
    outcome: ScanOutcome,
) -> RuntimeLogDetail:
    return RuntimeLogDetail(
        scope=scope_model(project_id, member_id),
        record=record,
        scan=scan_model(outcome),
    )


def _stable_warnings(outcome: ScanOutcome) -> list[str]:
    ordered = (
        "scan_limited",
        "records_unreadable",
        "source_entries_skipped",
        "source_changed",
    )
    return [item for item in ordered if item in outcome.warnings]
