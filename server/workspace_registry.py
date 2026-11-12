"""Explicit registration metadata operations; transaction ownership stays with the caller.

Windows file IDs are unsigned 64-bit; only 0..2^63-1 are accepted here.
Larger IDs fail closed as unavailable identity, reported as workspace_identity_invalid.
"""

from datetime import datetime, timezone
from collections.abc import Mapping

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session

from server.models import Project, WorkspaceRegistration


class WorkspaceRegistryError(ValueError):
    """An error whose message and code are stable for callers."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require_project(session: Session, project_id: str) -> None:
    if not session.execute(select(exists().where(Project.project_id == project_id))).scalar_one():
        raise WorkspaceRegistryError("workspace_project_not_found")


def _identity_values(identity):
    if identity is None:
        return dict(identity_platform=None, identity_volume_id=None,
                    identity_file_id=None, identity_collected_at=None)
    if not isinstance(identity, Mapping):
        raise WorkspaceRegistryError("workspace_identity_invalid")
    platform = identity.get("platform")
    volume_id, file_id = identity.get("volume_id"), identity.get("file_id")
    collected_at = identity.get("collected_at")
    if not isinstance(platform, str) or platform not in ("posix", "nt"):
        raise WorkspaceRegistryError("workspace_identity_invalid")
    if any(type(value) is not int or value < 0 or value > 2**63 - 1
           for value in (volume_id, file_id)):
        raise WorkspaceRegistryError("workspace_identity_invalid")
    try:
        if isinstance(collected_at, str):
            collected_at = datetime.fromisoformat(collected_at)
        if not isinstance(collected_at, datetime) or collected_at.utcoffset() is None:
            raise ValueError
        collected_at = collected_at.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        raise WorkspaceRegistryError("workspace_identity_invalid") from None
    return dict(identity_platform=platform, identity_volume_id=volume_id,
                identity_file_id=file_id, identity_collected_at=collected_at)


def get_registration(session: Session, project_id: str) -> WorkspaceRegistration | None:
    with session.no_autoflush:
        return session.get(WorkspaceRegistration, project_id, populate_existing=True)


def ensure_registration(session: Session, project_id: str) -> WorkspaceRegistration:
    with session.no_autoflush:
        _require_project(session, project_id)
        session.execute(insert(WorkspaceRegistration).values(
            project_id=project_id, revision=1, updated_at=datetime.now(timezone.utc)
        ).on_conflict_do_nothing(index_elements=[WorkspaceRegistration.project_id]))
        return get_registration(session, project_id)


def save_identity(session: Session, project_id: str, identity, expected_revision: int) -> WorkspaceRegistration:
    values = _identity_values(identity)
    with session.no_autoflush:
        _require_project(session, project_id)
        result = session.execute(
            update(WorkspaceRegistration)
            .where(WorkspaceRegistration.project_id == project_id,
                   WorkspaceRegistration.revision == expected_revision,
                   exists().where(Project.project_id == project_id))
            .values(**values, revision=WorkspaceRegistration.revision + 1,
                    updated_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            if get_registration(session, project_id) is None:
                raise WorkspaceRegistryError("workspace_registration_not_found")
            raise WorkspaceRegistryError("workspace_revision_conflict")
        return get_registration(session, project_id)
