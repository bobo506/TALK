"""Relink orchestration with kernel-owned, independently committed transactions.

A successful return means the operation has committed. Callers must not attempt
to roll back this operation through their own session.
"""
import os
from collections.abc import Mapping, Sequence

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from server.models import Project
from server import workspace_operations as ops, workspace_registry as registry
from server.workspace_diagnostics import inspect_root
from server import workspace_relink_files as files


class WorkspaceRelinkError(Exception):
    def __init__(self, code, original_code=None, rolled_back=(), not_rolled_back=()):
        self.code = code
        self.original_code = original_code
        self.rolled_back = tuple(rolled_back)
        self.not_rolled_back = tuple(not_rolled_back)
        super().__init__(code)


def _result(session, op):
    project = session.get(Project, op.project_id, populate_existing=True)
    registration = registry.get_registration(session, op.project_id)
    return {"operation_id": op.operation_id, "project_id": op.project_id,
            "stage": op.stage, "project_root": project.project_root_path if project else None,
            "revision": registration.revision if registration else None}


def _preflight(session, project_id, candidate_root, expected_revision, writes, allowed_roots):
    project = session.get(Project, project_id, populate_existing=True)
    if project is None:
        raise WorkspaceRelinkError("workspace_project_not_found")
    registration = registry.get_registration(session, project_id)
    if registration is None:
        raise WorkspaceRelinkError("workspace_registration_not_found")
    if registration.revision != expected_revision:
        raise WorkspaceRelinkError("workspace_revision_conflict")
    try:
        candidate_root = os.fspath(candidate_root)
        if not isinstance(candidate_root, str) or not os.path.isabs(candidate_root) or "\0" in candidate_root:
            raise ValueError
    except (TypeError, ValueError):
        raise WorkspaceRelinkError("workspace_root_invalid") from None
    info = inspect_root(candidate_root)
    if info.get("status") != "ok":
        status = info.get("status")
        raise WorkspaceRelinkError({"missing": "workspace_root_missing", "inaccessible": "workspace_root_inaccessible"}.get(status, "workspace_root_invalid"))
    identity = info.get("identity")
    if identity is None:
        raise WorkspaceRelinkError("workspace_identity_unknown")
    try:
        registry._identity_values(identity)
    except registry.WorkspaceRegistryError as exc:
        raise WorkspaceRelinkError(exc.code) from None
    try:
        roots = tuple(allowed_roots)
        normalized = [files._path(root) for root in roots]
        if os.path.normcase(os.path.normpath(candidate_root)) not in [os.path.normcase(os.path.normpath(root)) for root in normalized]:
            raise WorkspaceRelinkError("workspace_path_refused")
        if not isinstance(writes, Sequence) or not writes:
            raise WorkspaceRelinkError("workspace_write_failed")
        targets = set()
        for item in writes:
            if not isinstance(item, Mapping) or not {"target", "payload", "expected_digest"} <= item.keys():
                raise WorkspaceRelinkError("workspace_write_failed")
            target = files._checked(item["target"], roots)
            key = os.path.normcase(str(target))
            if key in targets:
                raise WorkspaceRelinkError("workspace_path_refused")
            targets.add(key)
            if not isinstance(item["payload"], bytes):
                raise WorkspaceRelinkError("workspace_write_failed")
            if len(item["payload"]) > files.MAX_FILE_BYTES:
                raise WorkspaceRelinkError("workspace_file_too_large")
    except files.WorkspaceFileError as exc:
        raise WorkspaceRelinkError(exc.code) from None
    except (TypeError, ValueError):
        raise WorkspaceRelinkError("workspace_path_refused") from None
    try:
        ops.digest_request(project_id, project.project_root_path, candidate_root, expected_revision)
    except ops.WorkspaceOperationError as exc:
        raise WorkspaceRelinkError(exc.code) from None
    return project.project_root_path, identity, roots


def execute_relink(session_factory, *, project_id, candidate_root, expected_revision, operation_id, writes, allowed_roots):
    """Relink a workspace using transactions owned by the kernel.

    The caller supplies a session_factory that returns a new session on every
    invocation. The kernel uses its own sessions for T1, T2 and T3; it never
    holds, commits or rolls back a caller session. Do not call while holding
    uncommitted changes in a session, and do not commit or roll back the
    kernel's sessions after return. A completed success means T2 committed.

    For the same operation_id and request digest, a completed operation returns
    its result without side effects; a nonterminal operation returns its
    current stage without side effects. A different digest raises
    workspace_operation_conflict.

    If T2 fails, file changes are rolled back and T3 marks the operation
    failed. If file rollback fails, the operation is marked recovery_required
    and the error includes rolled_back and not_rolled_back. A crash after files
    commit while the operation is prepared and T2 has not committed is handled
    by the 4b recovery scan; this function does not recover it automatically.

    A partial unique index rejects a second nonterminal operation for the same
    project, mapped to workspace_busy. The caller must map SQLite busy/locked
    to workspace_busy; that mapping is implemented in 4b.
    """
    try:
        with session_factory() as session:
            ops._identifier(operation_id)
            existing = ops.get_operation(session, operation_id)
            if existing is not None:
                try:
                    digest = ops.digest_request(project_id, existing.old_root, os.fspath(candidate_root), expected_revision)
                except (TypeError, ops.WorkspaceOperationError):
                    raise WorkspaceRelinkError("workspace_operation_conflict") from None
                if digest != existing.request_digest:
                    raise WorkspaceRelinkError("workspace_operation_conflict")
                return _result(session, existing)
            old_root, identity, roots = _preflight(
                session, project_id, candidate_root, expected_revision, writes, allowed_roots)
            candidate_root = os.fspath(candidate_root)
            busy = session.execute(select(ops.WorkspaceOperation.operation_id).where(
                ops.WorkspaceOperation.project_id == project_id,
                ops.WorkspaceOperation.stage.not_in(("completed", "failed")))).first()
            if busy:
                raise WorkspaceRelinkError("workspace_busy")
            try:
                ops.begin_operation(session, operation_id, project_id, old_root, candidate_root, expected_revision)
                ops.advance_stage(session, operation_id, "started", "prepared")
                session.commit()
            except IntegrityError:
                raise WorkspaceRelinkError("workspace_busy") from None
    except ops.WorkspaceOperationError as exc:
        raise WorkspaceRelinkError(exc.code) from None

    receipts = []
    try:
        for item in writes:
            receipts.append(files.prepare_write(item["target"], item["payload"], item["expected_digest"], roots))
        files.commit_batch(receipts, roots)
        with session_factory() as session:
            ops.advance_stage(session, operation_id, "prepared", "files_staged")
            ops.advance_stage(session, operation_id, "files_staged", "committed")
            result = session.execute(update(Project).where(
                Project.project_id == project_id, Project.project_root_path == old_root
            ).values(project_root_path=candidate_root).execution_options(synchronize_session=False))
            if result.rowcount != 1:
                raise WorkspaceRelinkError("workspace_revision_conflict")
            registry.save_identity(session, project_id, identity, expected_revision)
            op = ops.advance_stage(session, operation_id, "committed", "completed")
            result = _result(session, op)
            session.commit()
            return result
    except Exception as exc:
        code = exc.code if isinstance(exc, (WorkspaceRelinkError, files.WorkspaceFileError,
                                             ops.WorkspaceOperationError, registry.WorkspaceRegistryError)) else "workspace_write_failed"
        rolled = list(getattr(exc, "rolled_back", ()))
        failed = list(getattr(exc, "not_rolled_back", ()))
        for receipt in reversed(receipts):
            name = str(receipt.target)
            if name in failed:
                continue
            try:
                if receipt.committed:
                    files.rollback_write(receipt, roots)
                    rolled.append(name)
                elif not receipt.finished:
                    files.abort_write(receipt)
            except Exception:
                failed.append(name)
        final_code = "workspace_recovery_required" if failed else code
        try:
            with session_factory() as session:
                current = ops.get_operation(session, operation_id)
                ops.advance_stage(session, operation_id, current.stage, "recovery_required" if failed else "failed", final_code)
                session.commit()
        except Exception as mark_error:
            raise WorkspaceRelinkError("workspace_recovery_required", original_code=code,
                                       rolled_back=rolled, not_rolled_back=(*failed, "operation:" + str(operation_id))) from mark_error
        raise WorkspaceRelinkError(final_code, original_code=(getattr(exc, "original_code", None) or code) if failed else None,
                                   rolled_back=rolled, not_rolled_back=failed) from exc
