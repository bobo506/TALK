"""Relink operation ledger. Callers own transactions and all external effects."""

import hashlib
import json
import os
from datetime import datetime, timezone

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session

from server.models import Project, WorkspaceOperation


ERROR_CODES = frozenset({
    "workspace_project_not_found", "workspace_operation_conflict",
    "workspace_stage_conflict", "workspace_operation_input_invalid",
})
CHAIN = ("started", "prepared", "files_staged", "committed", "completed")
RECOVERABLE = (*CHAIN[:-1], "recovery_required")
MAX_PATH = 4096


class WorkspaceOperationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _invalid():
    raise WorkspaceOperationError("workspace_operation_input_invalid")


def _identifier(value):
    if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value:
        _invalid()
    return value


def _root(value):
    if value is None:
        return None
    if (not isinstance(value, str) or not value or len(value) > MAX_PATH
            or "\x00" in value or not os.path.isabs(value)):
        _invalid()
    value = os.path.normcase(os.path.normpath(value))
    if len(value) > MAX_PATH:
        _invalid()
    return value


def _request(project_id, old_root, candidate_root, expected_revision):
    _identifier(project_id)
    if type(expected_revision) is not int or not 0 <= expected_revision <= 2**63 - 1:
        _invalid()
    return {"project_id": project_id, "old_root": _root(old_root),
            "candidate_root": _root(candidate_root), "expected_revision": expected_revision}


def _digest(values):
    encoded = json.dumps(values, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def digest_request(project_id, old_root, candidate_root, expected_revision) -> str:
    return _digest(_request(project_id, old_root, candidate_root, expected_revision))


def get_operation(session: Session, operation_id: str) -> WorkspaceOperation | None:
    with session.no_autoflush:
        return session.get(WorkspaceOperation, operation_id, populate_existing=True)


def begin_operation(session: Session, operation_id, project_id, old_root, candidate_root,
                    expected_revision) -> WorkspaceOperation:
    _identifier(operation_id)
    values = _request(project_id, old_root, candidate_root, expected_revision)
    digest = _digest(values)
    with session.no_autoflush:
        if not session.execute(select(exists().where(Project.project_id == project_id))).scalar_one():
            raise WorkspaceOperationError("workspace_project_not_found")
        row = get_operation(session, operation_id)
        if row is not None:
            if row.request_digest != digest:
                raise WorkspaceOperationError("workspace_operation_conflict")
            return row
        now = datetime.now(timezone.utc)
        session.execute(insert(WorkspaceOperation).values(
            operation_id=operation_id, project_id=project_id, request_digest=digest,
            stage="started", old_root=values["old_root"], candidate_root=values["candidate_root"],
            created_at=now, updated_at=now,
        ).on_conflict_do_nothing(index_elements=[WorkspaceOperation.operation_id]))
        row = get_operation(session, operation_id)
        if row.request_digest != digest:
            raise WorkspaceOperationError("workspace_operation_conflict")
        return row


def advance_stage(session: Session, operation_id, expected_stage, next_stage,
                  error_code=None) -> WorkspaceOperation:
    _identifier(operation_id)
    with session.no_autoflush:
        if expected_stage is None and next_stage == "completed" and error_code is None:
            row = get_operation(session, operation_id)
            if row is not None and row.stage == "completed":
                return row
            raise WorkspaceOperationError("workspace_stage_conflict")
        if expected_stage not in CHAIN[:-1]:
            raise WorkspaceOperationError("workspace_stage_conflict")
        valid = next_stage in ("failed", "recovery_required") or next_stage == CHAIN[CHAIN.index(expected_stage) + 1]
        if not valid:
            raise WorkspaceOperationError("workspace_stage_conflict")
        if next_stage in ("failed", "recovery_required"):
            if not isinstance(error_code, str) or error_code not in ERROR_CODES:
                _invalid()
        elif error_code is not None:
            _invalid()
        result = session.execute(
            update(WorkspaceOperation)
            .where(WorkspaceOperation.operation_id == operation_id,
                   WorkspaceOperation.stage == expected_stage)
            .values(stage=next_stage, error_code=error_code, updated_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise WorkspaceOperationError("workspace_stage_conflict")
        return get_operation(session, operation_id)


def list_recoverable(session: Session, project_id=None) -> list[WorkspaceOperation]:
    with session.no_autoflush:
        statement = select(WorkspaceOperation).where(WorkspaceOperation.stage.in_(RECOVERABLE))
        if project_id is not None:
            statement = statement.where(WorkspaceOperation.project_id == project_id)
        return list(session.execute(statement.order_by(WorkspaceOperation.operation_id)
                                    .execution_options(populate_existing=True)).scalars())
