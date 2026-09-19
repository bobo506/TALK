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
from sqlalchemy import update
from sqlmodel import Session, select

from cli.profiles import load_profile, resolve_profile_path, write_profile_file
from server.auth import get_current_member
from server.db import get_session
from server.models import (
    SQLITE_SIGNED_INTEGER_MAX,
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
    ProjectControllerAssignmentUpdate,
    ProjectControllerModeUpdate,
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


def _require_controller_candidate(project_id: str, member_id: str, session: Session) -> None:
    """校验“新指定”的候选成员：已注册、未禁用、在项目名册中且为 agent。

    - 只校验候选事实，**不要求在线**：指定是长期职责，不是运行实例绑定；
    - 本函数只读，任何失败都在写入前抛出，不会改变既有指定或版本；
    - 前端的置灰/过滤只是体验优化，真正的候选约束由这里（以及 CAS 写入）保证。
    """
    member = _get_member(member_id, session)  # 未注册 → 400 member not found
    if member.kind != "agent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"controller candidate is not an agent member: {member_id}",
        )
    if member.disabled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"controller candidate is disabled: {member_id}",
        )
    if session.get(ProjectAgent, (project_id, member_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"controller candidate is not in the project roster: {member_id}",
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
        development_requirements=body.development_requirements,
        maintainer_member_id=maintainer_id,
        created_at=now,
        last_seen_at=now,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectOut.from_orm_project(project, session=session)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List all registered projects."""
    projects = session.exec(select(Project).order_by(Project.created_at.desc())).all()
    return [ProjectOut.from_orm_project(project, session=session) for project in projects]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Return one registered project."""
    project = _get_project(project_id, session)
    return ProjectOut.from_orm_project(project, session=session)


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
    """Update project metadata (display name / description / root path / development requirements)."""
    _require_human(current)
    project = _get_project(project_id, session)
    fields_set = body.model_fields_set
    if "display_name" in fields_set:
        project.display_name = body.display_name
    if "description" in fields_set:
        project.description = body.description
    if "project_root_path" in fields_set:
        project.project_root_path = body.project_root_path
    if "development_requirements" in fields_set:
        # 省略即保持原值；显式空文本或 null 归一为 None（清空）。
        project.development_requirements = body.development_requirements
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectOut.from_orm_project(project, session=session)


@router.patch("/{project_id}/controller-mode", response_model=ProjectOut)
def update_project_controller_mode(
    project_id: str,
    body: ProjectControllerModeUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """更新项目主控模式“意向”（C1a 专用配置入口；human 可写、agent 只读）。

    - 与普通元数据 ``PATCH /api/projects/{id}`` 分离，模式字段不能由后者修改；
    - 版本校验与写入是同一条**条件 UPDATE**（CAS 落在数据库写入层）：只有
      ``controller_mode_version == expected_version`` 且意向确实变化的请求会写入并 +1；
    - 版本不匹配返回 409（无论请求模式是否与当前相同都先验证版本）；
      合法同值请求返回 200、不写库、不递增版本；缺 ``expected_version`` 或非法 mode → 422；
    - 项目不存在 → 404。

    本片只保存配置意向：不创建任务、不调度、不等待、不唤醒或授权任何会话。
    """
    _require_human(current)
    _get_project(project_id, session)  # 项目不存在 → 404（先于任何写入）

    result = session.execute(
        update(Project)
        .where(
            Project.project_id == project_id,
            Project.controller_mode_version == body.expected_version,
            Project.controller_mode != body.mode,
        )
        .values(
            controller_mode=body.mode,
            controller_mode_version=Project.controller_mode_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()

    # 复读最新已提交状态：end 上一个事务，避免拿旧快照下结论。
    project = session.get(Project, project_id, populate_existing=True)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

    if result.rowcount == 0 and project.controller_mode_version != body.expected_version:
        # 条件更新未命中且版本已被推进：陈旧版本请求，不写入、不覆盖。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "controller mode version conflict: "
                f"expected_version={body.expected_version}, "
                f"current_version={project.controller_mode_version}"
            ),
        )
    return ProjectOut.from_orm_project(project, session=session)


@router.patch("/{project_id}/controller-assignment", response_model=ProjectOut)
def update_project_controller_assignment(
    project_id: str,
    body: ProjectControllerAssignmentUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """指定或解除项目长期主控（C1b-S1 专用入口；human 可写、agent 只读）。

    - ``member_id`` 必填键：项目内具体成员 ID（必须是已注册、未禁用、在该项目名册中的
      agent；不要求在线）或显式 ``null`` 表示解除；
    - ``expected_version`` 必填且为严格整数：读写分离的 CAS 依据；
    - 版本匹配且指定实际变化 → 原子条件 UPDATE 并 +1；版本匹配且同值 → 200 不写库、不增版本；
      版本陈旧（即使同值）→ 409；已有其他非 null 指定 → 409，必须先显式解除再另选；
    - 指定长期保存、无期限：名册 sync 移除成员、成员被禁用、服务重启都不会自动清除或转移，
      只影响读取时 ``controller_assignment_status``；human 仍可随时解除；
    - 本入口只保存职责指定，与 business_role / decision_tier 分开，不改变任何任务授权、
      派发、领取、完成或收取规则，也不创建任务/实例/会话。

    冲突（409）后应重新 ``GET`` 项目取最新 ``controller_assignment_version`` 再决定是否重试。
    """
    _require_human(current)
    project = _get_project(project_id, session)  # 项目不存在 → 404（先于任何写入）

    requested = body.member_id
    stored = project.controller_member_id or None
    if requested is not None and stored not in (None, requested):
        # 已有其他非 null 指定：禁止直接覆盖，避免"悄悄换人"绕过人工确认。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "project already has a controller assignment: "
                f"current_member_id={stored}; clear it first (member_id=null)"
            ),
        )
    if requested is not None and stored != requested:
        # 只对"新指定"做候选校验；同值重试是纯 no-op，不因期间失效而改变语义。
        # 诚实说明竞态窗口：候选事实（已注册 / 未禁用 / 在名册）是写入前的读校验，与下面的
        # 条件 UPDATE 不在同一事务里；并发的 sync / 禁用可能正好落在这中间。那时指定仍会写入，
        # 但读取状态会如实报 not_in_roster / member_disabled，不会伪装成有效主控，human 可解除。
        _require_controller_candidate(project_id, requested, session)

    conditions = [
        Project.project_id == project_id,
        Project.controller_assignment_version == body.expected_version,
        # 版本耗尽保护：实际变化需要 +1，已达 SQLite 有符号 64 位上界时不再写入，
        # 让上界请求得到可控的 409，而不是绑定溢出导致的 500。
        Project.controller_assignment_version < SQLITE_SIGNED_INTEGER_MAX,
    ]
    if requested is None:
        conditions.append(Project.controller_member_id.is_not(None))  # 确实已指定才需要写
    else:
        conditions.append(Project.controller_member_id.is_(None))  # 无指定才可设

    result = session.execute(
        update(Project)
        .where(*conditions)
        .values(
            controller_member_id=requested,
            controller_assignment_version=Project.controller_assignment_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()

    # 复读最新已提交状态：end 上一个事务，避免拿旧快照下结论。
    project = session.get(Project, project_id, populate_existing=True)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

    if result.rowcount == 0:
        if project.controller_assignment_version != body.expected_version:
            # 条件更新未命中且版本已被推进：陈旧版本请求，不写入、不覆盖。
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "controller assignment version conflict: "
                    f"expected_version={body.expected_version}, "
                    f"current_version={project.controller_assignment_version}"
                ),
            )
        if (project.controller_member_id or None) == requested:
            # 合法同值请求：版本正确且指定未变，200 返回当前状态，无任何副作用。
            return ProjectOut.from_orm_project(project, session=session)
        if project.controller_assignment_version >= SQLITE_SIGNED_INTEGER_MAX:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "controller assignment version exhausted: "
                    f"current_version={project.controller_assignment_version}"
                ),
            )
        if requested is not None and project.controller_member_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "project already has a controller assignment: "
                    f"current_member_id={project.controller_member_id}; clear it first (member_id=null)"
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="controller assignment conflict: state changed concurrently; re-read and retry",
        )
    return ProjectOut.from_orm_project(project, session=session)


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
