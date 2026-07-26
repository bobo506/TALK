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

from cli.profiles import load_profile, resolve_profile_path, write_profile_file
from server.auth import get_current_member
from server.db import get_session
from server.models import (
    AgentInstance,
    AgentInstanceOut,
    AgentProfileOut,
    AgentProfileUpdate,
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


def _require_project_root(project: Project) -> str:
    if not project.project_root_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project has no root path; cannot locate profile files",
        )
    return project.project_root_path


def _profile_out(project_id: str, member_id: str, root: str) -> AgentProfileOut:
    try:
        for kind in ("identity", "soul", "user"):
            resolve_profile_path(root, member_id, kind)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    profile = load_profile(root, member_id)
    return AgentProfileOut(
        project_id=project_id,
        member_id=member_id,
        identity=profile.identity,
        soul=profile.soul,
        user=profile.user,
    )


def _availability(statuses: list[str]) -> str:
    if "busy" in statuses:
        return "busy"
    if any(instance_status in {"online", "idle", "starting"} for instance_status in statuses):
        return "available"
    if "error" in statuses:
        return "error"
    return "offline"


def _instance_out(instance: AgentInstance) -> AgentInstanceOut:
    return AgentInstanceOut(
        id=instance.id,
        member_id=instance.member_id,
        runtime=instance.runtime,
        status=instance.status,
        host=instance.host,
        pid=instance.pid,
        current_task_id=instance.current_task_id,
        last_error=instance.last_error,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        last_seen_at=instance.last_seen_at,
    )


def _project_agent_outs(
    agents: list[ProjectAgent],
    session: Session,
) -> list[ProjectAgentOut]:
    member_ids = [agent.member_id for agent in agents]
    members = (
        session.exec(select(Member).where(Member.id.in_(member_ids))).all()
        if member_ids
        else []
    )
    instances = (
        session.exec(
            select(AgentInstance)
            .where(AgentInstance.member_id.in_(member_ids))
            .order_by(AgentInstance.member_id, AgentInstance.created_at)
        ).all()
        if member_ids
        else []
    )
    members_by_id = {member.id: member for member in members}
    instances_by_member: dict[str, list[AgentInstance]] = {}
    for instance in instances:
        instances_by_member.setdefault(instance.member_id, []).append(instance)

    return [
        ProjectAgentOut.from_orm_agent(
            agent,
            display_name=(
                members_by_id[agent.member_id].display_name
                if agent.member_id in members_by_id
                else None
            ),
            availability=_availability(
                [
                    instance.status
                    for instance in instances_by_member.get(agent.member_id, [])
                ]
            ),
            instances=[
                _instance_out(instance)
                for instance in instances_by_member.get(agent.member_id, [])
            ],
        )
        for agent in agents
    ]


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
    return _project_agent_outs(list(agents), session)


@router.get("/{project_id}/agents/{member_id:path}/profile", response_model=AgentProfileOut)
def get_agent_profile(
    project_id: str,
    member_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Read one agent's IDENTITY/SOUL/USER files from the registered project root."""
    _require_human(current)
    project = _get_project(project_id, session)
    root = _require_project_root(project)
    return _profile_out(project_id, member_id, root)


@router.put("/{project_id}/agents/{member_id:path}/profile", response_model=AgentProfileOut)
def update_agent_profile(
    project_id: str,
    member_id: str,
    body: AgentProfileUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Write selected IDENTITY/SOUL/USER files under the registered project root."""
    _require_human(current)
    project = _get_project(project_id, session)
    root = _require_project_root(project)

    try:
        for kind in ("identity", "soul", "user"):
            if kind in body.model_fields_set:
                write_profile_file(root, member_id, kind, getattr(body, kind) or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _profile_out(project_id, member_id, root)


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
                business_role=entry.business_role,
                decision_tier=entry.decision_tier,
                capability_summary=entry.capability_summary,
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
    return _project_agent_outs(list(agents), session)


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
