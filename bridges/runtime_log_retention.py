"""Local Windows log retention. No pathname-based deletion or PID adoption.

Only explicit sources, a writer's closed receipt, an exclusive run handle and
a caller-supplied task transaction can authorize expiration. Legacy/unknown
runs stay protected. File deletion targets the checked Windows HANDLE itself.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

EVENT = re.compile(r"^events-[0-9]{1,12}\.jsonl$")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
REF = re.compile(r"^(rtd-[A-Za-z0-9.-]{4,150})-([0-9]{6,12})$")
MAX_RECEIPT = 1024 * 1024
MAX_JOURNAL = 8 * 1024 * 1024
MAX_TASKS = 1024
MAX_SEGMENTS = 4096


def utcnow():
    return datetime.now(timezone.utc)


def epoch(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_required")
    return value.timestamp()


def _link(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def identity(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns]


def _chain(path):
    result = []
    for p in reversed((path, *path.parents)):
        st = p.lstat()
        if _link(st) or not stat.S_ISDIR(st.st_mode):
            raise OSError("unsafe_directory")
        result.append(p)
    return result


class NativeFile:
    """A checked, non-reparse handle with no FILE_SHARE_DELETE/WRITE."""
    def __init__(self, path, *, write=False, create=False, delete=False, directory=False):
        if os.name != "nt":
            raise OSError("retention_platform_unsupported")
        import ctypes
        import msvcrt
        from ctypes import wintypes as w
        self.path = Path(os.path.abspath(path))
        self.fd = None
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        # Expand 8.3 spelling without resolving junction/symlink targets. A
        # resolved HANDLE must still match this lexical long path exactly.
        self.k.GetLongPathNameW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
        self.k.GetLongPathNameW.restype = w.DWORD
        original = self.path
        spelling = original if original.exists() else original.parent
        long_name = ctypes.create_unicode_buffer(32768)
        length = self.k.GetLongPathNameW(str(spelling), long_name, len(long_name))
        if not length or length >= len(long_name):
            raise OSError("retention_path_unavailable")
        self.path = Path(long_name.value) if spelling == original else Path(long_name.value) / original.name
        self.k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID,
                                       w.DWORD, w.DWORD, w.HANDLE]
        self.k.CreateFileW.restype = w.HANDLE
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.k.CloseHandle.restype = w.BOOL
        access = 0x80 if directory else 0x80000000
        if write:
            access |= 0x40000000
        if delete:
            access |= 0x10000
        share = 3 if directory else 1
        flags = 0x00200000 | (0x02000000 if directory else 0)
        handle = self.k.CreateFileW(str(self.path), access, share, None,
                                    4 if create else 3, flags, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "retention_open_unavailable")
        try:
            class Attributes(ctypes.Structure):
                _fields_ = [("attributes", w.DWORD), ("tag", w.DWORD)]
            self.k.GetFileInformationByHandleEx.argtypes = [w.HANDLE, ctypes.c_int,
                                                            w.LPVOID, w.DWORD]
            self.k.GetFileInformationByHandleEx.restype = w.BOOL
            attrs = Attributes()
            if (not self.k.GetFileInformationByHandleEx(handle, 9, ctypes.byref(attrs),
                                                       ctypes.sizeof(attrs))
                    or attrs.attributes & 0x400):
                raise OSError("retention_reparse_or_unavailable")
            self.k.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
            self.k.GetFinalPathNameByHandleW.restype = w.DWORD
            buffer = ctypes.create_unicode_buffer(32768)
            length = self.k.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
            actual = buffer.value
            if actual.startswith("\\\\?\\"):
                actual = actual[4:]
            if (not length or length >= len(buffer)
                    or os.path.normcase(actual) != os.path.normcase(str(self.path))):
                raise OSError("retention_opened_path_changed")
            self.fd = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_RDWR if write else os.O_RDONLY))
            handle = None
            if not directory and not stat.S_ISREG(os.fstat(self.fd).st_mode):
                raise OSError("retention_not_regular")
        except Exception:
            self.close()
            raise
        finally:
            if handle is not None:
                self.k.CloseHandle(handle)

    def close(self):
        if getattr(self, "fd", None) is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        self.close()

    def read(self, limit):
        if os.fstat(self.fd).st_size > limit:
            raise OSError("retention_read_limit")
        os.lseek(self.fd, 0, os.SEEK_SET)
        data = os.read(self.fd, limit + 1)
        if len(data) > limit:
            raise OSError("retention_read_limit")
        return data

    def write(self, data, *, append=False, limit=MAX_JOURNAL):
        size = os.fstat(self.fd).st_size
        if len(data) + (size if append else 0) > limit:
            raise OSError("retention_write_limit")
        os.lseek(self.fd, 0, os.SEEK_END if append else os.SEEK_SET)
        view = memoryview(data)
        while view:
            count = os.write(self.fd, view)
            if count <= 0:
                raise OSError("retention_write_failed")
            view = view[count:]
        if not append:
            os.ftruncate(self.fd, len(data))
        os.fsync(self.fd)

    def expire(self, expected):
        import ctypes
        import msvcrt
        from ctypes import wintypes as w
        if identity(os.fstat(self.fd)) != expected:
            raise OSError("retention_file_changed")
        class Disposition(ctypes.Structure):
            _fields_ = [("delete", ctypes.c_ubyte)]
        self.k.SetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
        self.k.SetFileInformationByHandle.restype = w.BOOL
        value = Disposition(1)
        if not self.k.SetFileInformationByHandle(msvcrt.get_osfhandle(self.fd), 4,
                                                ctypes.byref(value), ctypes.sizeof(value)):
            raise OSError("retention_delete_failed")
        self.close()  # The exact checked object is deleted here, never unlink(path).


@contextlib.contextmanager
def pinned(path):
    with contextlib.ExitStack() as stack:
        for p in _chain(Path(os.path.abspath(path))):
            stack.enter_context(NativeFile(p, directory=True))
        yield


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def read_json(path, limit=MAX_RECEIPT):
    with NativeFile(path) as handle:
        return json.loads(handle.read(limit))


def write_json(path, value):
    with NativeFile(path, write=True, create=True) as handle:
        handle.write(encoded(value), limit=MAX_RECEIPT)


def journal(path, value):
    with NativeFile(path, write=True, create=True) as handle:
        handle.write(encoded(value), append=True)


def read_journal(path):
    if not path.exists():
        return []
    with NativeFile(path) as handle:
        data = handle.read(MAX_JOURNAL)
    return [json.loads(line) for line in data.splitlines() if line]


def receipt_valid(value, run, scopes, *, allow_taskless=False):
    from bridges.runtime_diagnostics import _safe_token
    if (not isinstance(value, dict) or value.get("schema") != "talk-log-closed-1"
            or value.get("complete") is not True):
        return False
    pair = (value.get("project_id"), value.get("member_id"))
    if pair not in scopes or value.get("run_id") != run.name:
        return False
    if not isinstance(value.get("instance_id"), str):
        return False
    if (_safe_token(pair[1], fallback="unknown-member") != run.parent.parent.name
            or _safe_token(value["instance_id"], fallback="unknown-instance") != run.parent.name):
        return False
    tasks = value.get("task_ids")
    segments = value.get("segments")
    if (not isinstance(tasks, list) or (not tasks and not allow_taskless) or len(tasks) > MAX_TASKS
            or any(type(i) is not int or not 0 < i <= 2**53-1 for i in tasks)
            or not isinstance(segments, list) or len(segments) > MAX_SEGMENTS
            or not isinstance(value.get("prefix"), str)
            or not REF.fullmatch(value["prefix"] + "-000001")):
        return False
    seen = set()
    for item in segments:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            return False
        name = item["name"]
        snap = item.get("identity")
        if (not EVENT.fullmatch(name) or name in seen or not isinstance(snap, list)
                or len(snap) != 4 or any(type(i) is not int for i in snap)
                or any(i < 0 for i in snap[:3])
                or type(item.get("first")) is not int or type(item.get("last")) is not int
                or not 0 < item["first"] <= item["last"] <= 10**12-1):
            return False
        seen.add(name)
    return True


def iter_runs(root, *, max_entries=20000, deadline=None):
    """Fixed three levels, no links. Reparse/unknown/IO errors fail the sweep."""
    stack = [(root, 0)]
    count = 0
    while stack:
        path, depth = stack.pop()
        if deadline is not None and time.monotonic() >= deadline:
            raise OSError("retention_time_limit")
        _chain(path)
        with os.scandir(path) as items:
            for entry in items:
                if deadline is not None and time.monotonic() >= deadline:
                    raise OSError("retention_time_limit")
                count += 1
                if count > max_entries:
                    raise OSError("retention_entry_limit")
                child = Path(entry.path)
                st = child.lstat()
                if _link(st):
                    raise OSError("retention_reparse_skipped")
                if stat.S_ISDIR(st.st_mode):
                    if not TOKEN.fullmatch(child.name):
                        raise OSError("retention_unknown_directory")
                    if depth == 2:
                        yield child
                    else:
                        stack.append((child, depth + 1))


def check_segments(run, value, known_intents, cutoff, deadline):
    declared = {item["name"] for item in value["segments"]}
    with os.scandir(run) as entries:
        for entry in entries:
            st = Path(entry.path).lstat()
            if _link(st) or (EVENT.fullmatch(entry.name) and entry.name not in declared):
                raise OSError("retention_unrecorded_or_unsafe_file")
    for item in value["segments"]:
        if time.monotonic() >= deadline:
            raise OSError("retention_time_limit")
        path = run / item["name"]
        key = (item["name"], value["prefix"], item["first"], item["last"])
        try:
            st = path.lstat()
        except FileNotFoundError:
            if key not in known_intents:
                raise OSError("retention_unexplained_missing")
            continue
        if (_link(st) or not stat.S_ISREG(st.st_mode) or identity(st) != item["identity"]
                or st.st_mtime_ns / 10**9 >= cutoff):
            raise OSError("retention_run_changed_or_recent")


def sweep(root, scopes, task_guard, *, now=None, retention_days=30,
          max_total_bytes=1024**3, max_seconds=10, max_deletions=100,
          interval_seconds=86400, stop=None, receipt_validator=None):
    """One automatic sweep. task_guard holds the task-state transaction."""
    now = now or utcnow()
    current = epoch(now)
    if not isinstance(root, (str, os.PathLike)) or not str(root).strip():
        raise ValueError("retention_root_required")
    if (not isinstance(retention_days, (float, int)) or isinstance(retention_days, bool)
            or not math.isfinite(retention_days) or not 0 < retention_days <= 36500
            or type(max_total_bytes) is not int or max_total_bytes <= 0
            or type(interval_seconds) is not int or not 60 <= interval_seconds <= 604800
            or type(max_deletions) is not int or not 1 <= max_deletions <= 1000
            or type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
            or not 0 < max_seconds <= 60
            or (receipt_validator is not None and not callable(receipt_validator))):
        raise ValueError("retention_policy_invalid")
    cutoff = current - retention_days * 86400
    root = Path(os.path.abspath(root))
    report = {"schema": "talk-log-retention-sweep-1", "at": now.isoformat(),
              "deleted_files": 0, "deleted_bytes": 0, "protected_runs": 0,
              "protected_reasons": {}, "status": "complete", "errors": [],
              "max_total_bytes": max_total_bytes}
    def protect(reason):
        report["protected_runs"] += 1
        report["protected_reasons"][reason] = report["protected_reasons"].get(reason, 0) + 1
    deadline = time.monotonic() + max_seconds
    try:
        with pinned(root), NativeFile(root / ".retention.lock", write=True, create=True):
            write_json(root / ".retention-policy.json", {
                "schema": "talk-log-retention-policy-1", "enabled": True,
                "scopes": [list(pair) for pair in sorted(scopes)]})
            try:
                state = read_json(root / ".retention-state.json")
            except FileNotFoundError:
                state = {}
            except OSError:
                # NativeFile deliberately has stable errors; stat distinguishes absence.
                if (root / ".retention-state.json").exists():
                    raise
                state = {}
            except (ValueError, TypeError):
                state = {}
            due = state.get("next_check") if isinstance(state, dict) else None
            if type(due) in (int, float) and math.isfinite(due) and current < due <= current+interval_seconds:
                return {**report, "status": "not_due"}
            for run in iter_runs(root, deadline=deadline):
                if stop is not None and stop.is_set():
                    report["status"] = "partial"
                    report["errors"].append("stopping")
                    break
                if report["deleted_files"] >= max_deletions:
                    report["status"] = "partial"
                    report["errors"].append("deletion_limit")
                    break
                try:
                    if not (run / "closed.json").exists() or not (run / "run.lease").exists():
                        protect("legacy_or_unclosed")
                        continue
                    with (pinned(run), NativeFile(run / "run.lease", write=True),
                          NativeFile(run / "closed.json") as closed_handle):
                        # Keep closure evidence read-pinned through the whole batch.
                        value = json.loads(closed_handle.read(MAX_RECEIPT))
                        if not (receipt_validator or receipt_valid)(value, run, scopes):
                            protect("scope_or_incomplete_evidence")
                            continue
                        closed = datetime.fromisoformat(value["closed_at"])
                        if epoch(closed) >= cutoff:
                            protect("within_retention_period")
                            continue
                        traces = read_journal(run / "retention.jsonl")
                        def trace_key(v):
                            return (v.get("file"), v.get("prefix"), v.get("first"), v.get("last"))
                        known_intents = {trace_key(v) for v in traces if isinstance(v, dict)
                                         and v.get("action") == "auto_expire_intent"}
                        known_results = {trace_key(v) for v in traces if isinstance(v, dict)
                                         and v.get("action") == "auto_expire_result"
                                         and v.get("outcome") in {"deleted", "missing_after_intent"}}
                        def recheck():
                            try:
                                check_segments(run, value, known_intents, cutoff, deadline)
                            except OSError:
                                journal(run / "retention.jsonl", {
                                    "schema": "talk-log-expiration-1", "action": "auto_expire_protected",
                                    "reason": "run_evidence_changed_or_unavailable", "at": now.isoformat()})
                                raise
                        recheck()
                        with task_guard(value["project_id"], value["member_id"], value["task_ids"]) as safe:
                            if not safe:
                                protect("unfinished_or_unknown_task_reference")
                                continue
                            batch_deadline = time.monotonic() + .25
                            batch_deleted = 0
                            for item in value["segments"]:
                                if (time.monotonic() >= deadline or report["deleted_files"] >= max_deletions
                                        or time.monotonic() >= batch_deadline or batch_deleted >= 10
                                        or (stop is not None and stop.is_set())):
                                    raise OSError("retention_batch_limit")
                                # The DB reservation may have waited/run caller code.
                                # Revalidate inside it and before every exact-handle deletion.
                                recheck()
                                path = run / item["name"]
                                entry = {"schema": "talk-log-expiration-1", "file": item["name"],
                                         "prefix": value["prefix"], "first": item["first"], "last": item["last"],
                                         "project_id": value["project_id"], "member_id": value["member_id"],
                                         "at": now.isoformat()}
                                if not path.exists():
                                    key = (item["name"], value["prefix"], item["first"], item["last"])
                                    if key not in known_intents:
                                        journal(run / "retention.jsonl", {**entry,
                                            "action": "auto_expire_protected", "reason": "unexplained_missing"})
                                        raise OSError("retention_unexplained_missing")
                                    if key in known_intents and key not in known_results:
                                        journal(run / "retention.jsonl", {**entry, "action": "auto_expire_result",
                                                "outcome": "missing_after_intent"})
                                    continue
                                with NativeFile(path, delete=True) as h:
                                    if identity(os.fstat(h.fd)) != item["identity"]:
                                        raise OSError("retention_file_changed")
                                    journal(run / "retention.jsonl", {**entry, "action": "auto_expire_intent"})
                                    try:
                                        h.expire(item["identity"])
                                    except OSError:
                                        journal(run / "retention.jsonl", {**entry, "action": "auto_expire_result",
                                                "outcome": "failed"})
                                        raise
                                journal(run / "retention.jsonl", {**entry, "action": "auto_expire_result",
                                        "outcome": "deleted"})
                                known_intents.add((item["name"], value["prefix"], item["first"], item["last"]))
                                report["deleted_files"] += 1
                                report["deleted_bytes"] += item["identity"][2]
                                batch_deleted += 1
                            # Detect uncooperative external additions during the final
                            # deletion as partial; an already-deleted file cannot be restored.
                            recheck()
                except Exception:
                    protect("evidence_changed_or_io_failed")
                    report["status"] = "partial"
                    if "run_evidence_or_io_failed" not in report["errors"]:
                        report["errors"].append("run_evidence_or_io_failed")
            # Observe total logical bytes after cleanup. Soft capacity never overrides age/protection.
            from scripts.runtime_log_inventory import inventory
            totals = inventory(root, max_seconds=2)
            report["observed_bytes"] = totals["observed"]["bytes"]
            report["capacity_scan"] = totals["scan"]["status"]
            observed = totals["observed"]["bytes"]
            report["over_budget"] = (True if observed is not None and observed > max_total_bytes
                                     else False if totals["scan"]["status"] == "complete" else None)
            write_json(root / ".retention-state.json", {"next_check": current +
                       (min(300, interval_seconds) if report["status"] == "partial" else interval_seconds),
                       "last": report})
    except (OSError, ValueError, TypeError):
        report["status"] = "partial"
        report["errors"].append("retention_unavailable_or_limited")
    return report


def expired_reference(root, project_id, member_id, log_ref):
    """Bounded positive expiration evidence; never returns source paths."""
    match = REF.fullmatch(log_ref)
    if not match:
        return False
    policy = Path(root) / ".retention-policy.json"
    if not policy.exists() and not policy.is_symlink():
        return False  # Preserve the old 404 contract for sources never managed here.
    prefix, sequence = match.group(1), int(match.group(2))
    deadline = time.monotonic() + 2
    total = 0
    try:
        with pinned(Path(root)):
            for run in iter_runs(Path(root), max_entries=5000, deadline=deadline):
                path = run / "retention.jsonl"
                if not path.exists():
                    continue
                with pinned(run):
                    if not (run / "closed.json").exists():
                        continue
                    receipt = read_json(run / "closed.json")
                    if (not receipt_valid(receipt, run, {(project_id, member_id)})
                            or receipt["prefix"] != prefix):
                        continue
                    segment_keys = {(v["name"], v["first"], v["last"]) for v in receipt["segments"]}
                    size = path.lstat().st_size
                    total += size + (run / "closed.json").stat().st_size
                    if total > MAX_JOURNAL:
                        return None
                    for item in read_journal(path):
                        if (isinstance(item, dict) and item.get("schema") == "talk-log-expiration-1"
                                and item.get("action") == "auto_expire_result"
                                and item.get("outcome") in {"deleted", "missing_after_intent"}
                                and item.get("project_id") == project_id and item.get("member_id") == member_id
                                and item.get("prefix") == prefix and type(item.get("first")) is int
                                and type(item.get("last")) is int
                                and (item.get("file"), item["first"], item["last"]) in segment_keys
                                and item["first"] <= sequence <= item["last"]):
                            return True
        return False
    except (OSError, ValueError, TypeError):
        return None
