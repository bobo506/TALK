"""Project registration and metadata APIs (TALK project integration layer).

These endpoints back the `talk init` / `talk sync` CLI flows described in
``docs/spec/PROJECT_INTEGRATION.md`` §3 and §7: a project registers itself with
the TALK server and keeps its metadata in sync. The server only stores project
metadata; the actual ``.talk/`` profile files stay in the project repo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import (
    Group,
    GroupMember,
    GroupOut,
    Member,
    Project,
    ProjectAgent,
    ProjectAgentOut,
    ProjectCreate,
    ProjectOut,
    ProjectSyncRequest,
    ProjectUpdate,
)
from server.routes.groups import _group_out

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _require_human(current: Member) -> None:
    if current.kind != "human":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only human members can manage projects")


def _get_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


def _get_member(member_id: str, session: Session) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"member not found: {member_id}")
    return member


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def register_project(
    body: ProjectCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Register a project with the TALK server (called by `talk init`)."""
    _require_human(current)
    project_id = body.project_id or f"prj_{uuid4().hex[:12]}"
    if session.get(Project, project_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="project id already exists")

    maintainer_id = body.maintainer_member_id or current.id
    _get_member(maintainer_id, session)

    now = datetime.now(timezone.utc)
    project = Project(
        project_id=project_id,
        display_name=body.display_name,
        description=body.description,
        project_root_path=body.project_root_path,
        maintainer_member_id=maintainer_id,
        created_at=now,
        last_seen_at=now,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectOut.from_orm_project(project)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List all registered projects."""
    projects = session.exec(select(Project).order_by(Project.created_at.desc())).all()
    return [ProjectOut.from_orm_project(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Return one registered project."""
    project = _get_project(project_id, session)
    return ProjectOut.from_orm_project(project)


@router.get("/{project_id}/groups", response_model=list[GroupOut])
def list_project_groups(
    project_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List groups belonging to a project (visibility same as GET /api/groups)."""
    _get_project(project_id, session)
    stmt = select(Group).where(Group.project_id == project_id)
    if current.kind != "human":
        stmt = stmt.join(GroupMember, GroupMember.group_id == Group.id).where(
            GroupMember.member_id == current.id
        )
    groups = session.exec(stmt.order_by(Group.created_at.desc())).all()
    return [_group_out(group, session) for group in groups]


@router.get("/{project_id}/agents", response_model=list[ProjectAgentOut])
def list_project_agents(
    project_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List the agent profile-path index for a project (PROJECT_INTEGRATION §7.3)."""
    _get_project(project_id, session)
    agents = session.exec(
        select(ProjectAgent)
        .where(ProjectAgent.project_id == project_id)
        .order_by(ProjectAgent.member_id)
    ).all()
    return [ProjectAgentOut.from_orm_agent(agent) for agent in agents]


@router.post("/{project_id}/sync", response_model=list[ProjectAgentOut])
def sync_project(
    project_id: str,
    body: ProjectSyncRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Sync the project's `.talk/` agent index to the server (called by `talk sync`).

    Full-replace semantics: rows not present in the payload are removed, so the
    server index always mirrors the project's local `.talk/agents/`.
    """
    _require_human(current)
    project = _get_project(project_id, session)

    existing = session.exec(
        select(ProjectAgent).where(ProjectAgent.project_id == project_id)
    ).all()
    for row in existing:
        session.delete(row)

    now = datetime.now(timezone.utc)
    for entry in body.agents:
        session.add(
            ProjectAgent(
                project_id=project_id,
                member_id=entry.member_id,
                identity_path=entry.identity_path,
                soul_path=entry.soul_path,
                user_path=entry.user_path,
                memory_pointer=entry.memory_pointer,
                updated_at=now,
            )
        )
    project.last_seen_at = now
    session.add(project)
    session.commit()

    agents = session.exec(
        select(ProjectAgent)
        .where(ProjectAgent.project_id == project_id)
        .order_by(ProjectAgent.member_id)
    ).all()
    return [ProjectAgentOut.from_orm_agent(agent) for agent in agents]


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    body: ProjectUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Update project metadata (display name / description / root path)."""
    _require_human(current)
    project = _get_project(project_id, session)
    fields_set = body.model_fields_set
    if "display_name" in fields_set:
        project.display_name = body.display_name
    if "description" in fields_set:
        project.description = body.description
    if "project_root_path" in fields_set:
        project.project_root_path = body.project_root_path
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectOut.from_orm_project(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def unregister_project(
    project_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Unregister a project from the TALK server."""
    _require_human(current)
    project = _get_project(project_id, session)
    session.delete(project)
    session.commit()
    return None
