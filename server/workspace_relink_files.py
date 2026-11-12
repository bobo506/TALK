"""File staging and compensation primitives; callers own persistence and locking.

Path checks and digest checks do not close races with hostile concurrent writers.
Receipts contain old bytes and must be protected by the caller.
"""
from __future__ import annotations

import hashlib
import os
import stat
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from server.workspace_paths import WorkspacePathError, is_within

MAX_PATH = 4096
MAX_FILE_BYTES = 1024 * 1024


class WorkspaceFileError(Exception):
    def __init__(self, code, *, original_code=None, rolled_back=(), not_rolled_back=()):
        self.code = code
        self.original_code = original_code
        self.rolled_back = tuple(rolled_back)
        self.not_rolled_back = tuple(not_rolled_back)
        super().__init__(code)


@dataclass
class WriteReceipt:
    target: Path
    temp: Path
    old_digest: str | None
    new_digest: str
    created: bool
    prepared_at: datetime
    old_bytes: bytes | None = field(repr=False)
    committed: bool = False
    finished: bool = False


def _error(code):
    raise WorkspaceFileError(code) from None


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _path(value):
    try:
        raw = os.fspath(value)
        if (not isinstance(raw, str) or not raw or len(raw) > MAX_PATH or "\0" in raw
                or not os.path.isabs(raw) or ".." in Path(raw).parts):
            _error("workspace_path_refused")
        return Path(os.path.normpath(raw))
    except (TypeError, ValueError, OSError):
        _error("workspace_path_refused")


def _checked(target, roots):
    target = _path(target)
    try:
        bases = [_path(root) for root in roots]
        if not bases or not any(is_within(target, root) for root in bases):
            _error("workspace_path_refused")
        # is_within checks all existing ancestors, including target, for reparse points.
        try:
            info = target.lstat()
        except FileNotFoundError:
            return target
        if not stat.S_ISREG(info.st_mode):
            _error("workspace_path_refused")
        return target
    except WorkspacePathError:
        _error("workspace_path_refused")
    except (OSError, TypeError, ValueError):
        _error("workspace_path_refused")


def _read(target):
    try:
        if target.lstat().st_size > MAX_FILE_BYTES:
            _error("workspace_file_too_large")
        # Bound the read too, in case the file grows after lstat.
        with target.open('rb') as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            _error("workspace_file_too_large")
        return data
    except FileNotFoundError:
        return None
    except OSError:
        _error("workspace_write_failed")


def _stage(target, payload):
    temp = target.parent / ('.' + target.name + '.talk-tmp-' + uuid.uuid4().hex)
    fd = None
    made = False
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
        made = True
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        actual = _read(temp)
        if actual != payload or _digest(actual) != _digest(payload):
            _error("workspace_write_failed")
        return temp
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if made:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        _error("workspace_write_failed")


def _sync_dir(directory):
    fd = None
    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        os.fsync(fd)
    except OSError:
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def prepare_write(target, payload: bytes, expected_digest: str | None, allowed_roots) -> WriteReceipt:
    target = _checked(target, allowed_roots)
    if not isinstance(payload, bytes):
        _error("workspace_write_failed")
    if len(payload) > MAX_FILE_BYTES:
        _error("workspace_file_too_large")
    old = _read(target)
    if (old is None and expected_digest is not None) or (old is not None and expected_digest != _digest(old)):
        _error("workspace_file_conflict")
    temp = _stage(target, payload)
    return WriteReceipt(target, temp, None if old is None else _digest(old), _digest(payload),
                        old is None, datetime.now(timezone.utc), old)


def commit_write(receipt: WriteReceipt, allowed_roots) -> WriteReceipt:
    if receipt.committed or receipt.finished:
        _error("workspace_write_failed")
    target = _path(receipt.target)
    temp = _checked(receipt.temp, allowed_roots)
    if temp.parent != target.parent or not temp.name.startswith('.' + target.name + '.talk-tmp-'):
        _error("workspace_path_refused")
    try:
        target = _checked(target, allowed_roots)
        staged = _read(temp)
        if staged is None or _digest(staged) != receipt.new_digest:
            _error("workspace_write_failed")
        current = _read(target)
        if (current is None) != receipt.created or (current is not None and _digest(current) != receipt.old_digest):
            _error("workspace_file_conflict")
        try:
            os.replace(temp, target)
        except OSError:
            _error("workspace_write_failed")
    except WorkspaceFileError:
        abort_write(receipt)
        raise
    receipt.committed = True
    _sync_dir(target.parent)
    return receipt


def abort_write(receipt: WriteReceipt):
    if receipt.committed or receipt.finished:
        return
    try:
        receipt.temp.unlink(missing_ok=True)
    except OSError:
        _error("workspace_write_failed")
    receipt.finished = True


def rollback_write(receipt: WriteReceipt, allowed_roots) -> WriteReceipt:
    if not receipt.committed:
        abort_write(receipt)
        return receipt
    temp = None
    try:
        target = _checked(receipt.target, allowed_roots)
        current = _read(target)
        if current is None or _digest(current) != receipt.new_digest:
            _error("workspace_recovery_required")
        if receipt.created:
            target.unlink()
        else:
            if receipt.old_bytes is None or _digest(receipt.old_bytes) != receipt.old_digest:
                _error("workspace_recovery_required")
            temp = _stage(target, receipt.old_bytes)
            # Check again after staging; do not knowingly overwrite a concurrent change.
            _checked(target, allowed_roots)
            current = _read(target)
            if current is None or _digest(current) != receipt.new_digest:
                _error("workspace_recovery_required")
            os.replace(temp, target)
            temp = None
        receipt.committed = False
        receipt.finished = True
        _sync_dir(target.parent)
        return receipt
    except (WorkspaceFileError, OSError):
        _error("workspace_recovery_required")
    finally:
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def commit_batch(receipts, allowed_roots):
    receipts = list(receipts)
    done = []
    try:
        for receipt in receipts:
            commit_write(receipt, allowed_roots)
            done.append(receipt)
        return done
    except WorkspaceFileError as original:
        rolled_back, not_rolled_back = [], []
        for receipt in reversed(done):
            try:
                rollback_write(receipt, allowed_roots)
                rolled_back.append(str(receipt.target))
            except WorkspaceFileError:
                not_rolled_back.append(str(receipt.target))
        for receipt in receipts[len(done):]:
            try:
                abort_write(receipt)
            except WorkspaceFileError:
                not_rolled_back.append(str(receipt.target))
        if not_rolled_back:
            raise WorkspaceFileError('workspace_recovery_required', original_code=original.code,
                                     rolled_back=rolled_back, not_rolled_back=not_rolled_back) from None
        raise
