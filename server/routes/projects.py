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
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from cli.profiles import load_profile, resolve_profile_path, write_profile_file
from server.auth import get_current_member
from server.db import get_session
from server.models import (
    RUNNER_ADAPTER_RETIRED,
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
    ProjectRoleBinding,
    ProjectRoleDescription,
    ProjectRoleDescriptionOut,
    ProjectSyncRequest,
    ProjectUpdate,
    RoleBindingResponse,
    RoleBindingUpdate,
    RoleDescriptionUpdate,
    RunnerRegistry,
    build_role_binding_out,
    read_role_binding_facts,
    read_role_binding_facts_batch,
    resolve_role_binding_state,
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


def _require_facts_project(facts: dict) -> None:
    """把事实行里的 ``project_exists`` 映射成项目 404（R1 定向修正）。

    前置 ``_get_project`` 的 ORM 读取**不能**代替事实 SQL 的最终视图：项目可能在同一
    请求的前置检查之后、事实读取之前被另一连接删除。此时成功响应不得返回 200 与
    ``binding_state = null``，必须按最终事实映射项目 404（合同 §4.4 序 0：``project_exists
    = 0`` 不是一种 ``binding_state``；事实助手本身不固定 HTTP 错误码，映射由 API 层完成）。
    """
    if not facts or not facts.get("project_exists"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )


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


def _require_binding_target(project_id: str, member_id: str, session: Session) -> None:
    """校验非空绑定写入的目标角色（合同 §4.3，全部失败一律 404）。

    目标必须**同时**满足：成员已注册、未被全局禁用、``kind == "agent"``、在当前项目名册
    （``project_agents``）。四类失败都视为“目标不在有效名册”→ **404**，不区分具体原因，
    也不暴露成员是否存在；本函数只读，任何失败都在写入前抛出。

    配对读取侧不同：读取（``GET`` / 事实助手）**不**做这层校验，成员离册/被删/禁用/非 agent
    时仍返回保留的存储行与失效状态（“存着但不有效”正是要如实展示的事实）。
    """
    member = session.get(Member, member_id) if member_id else None
    if member is None or member.disabled_at is not None or member.kind != "agent":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"binding target is not an active agent in the project roster: {member_id}",
        )
    if session.get(ProjectAgent, (project_id, member_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"binding target is not an active agent in the project roster: {member_id}",
        )


def _project_agent_outs(
    agents: list[ProjectAgent],
    session: Session,
    *,
    project_id: str | None = None,
) -> list[ProjectAgentOut]:
    """构造项目名册输出（GET /agents 与 POST /sync 共用）。

    角色说明（ROLE-DESC-B1）在**两处共用**的这一函数内统一填充：一次 ``member_id IN (...)``
    批量查询 ``project_role_descriptions`` 组装成 dict，避免按成员逐条查询的 N+1；无自定义
    记录的成员一律为 ``null``，因此 GET 与 sync 响应里同一成员的 ``role_description`` 语义一致。

    角色绑定（ROLE-BINDING-B1a）同样在这一处统一填充 ``binding`` / ``binding_state``：
    一次批量事实 SQL 取齐全部成员的项目/成员/名册/绑定/登记事实（不是按成员逐条的 N+1，
    也不是复用早先 ORM 缓存推断），状态与单角色读取共用同一阶梯与同一批列。

    ``project_id`` 可显式传入；不传时从名册行自身推断（调用方两条路径都只有一个项目）。
    空名册直接短路返回 ``[]``，不额外查库、不改数据。

    批量事实行取回后，再用其**最终** ``project_exists`` 判定项目是否仍存在（R1），不存在
    则 404：GET /agents 与 POST /sync 这两条批量角色响应都不允许在项目已被并发删除时
    返回 200 与 ``binding_state = null``。空名册短路分支没有角色状态可返回，保持原样。
    """
    if not agents:
        return []

    project_id = project_id or agents[0].project_id
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
    role_descriptions = (
        session.exec(
            select(ProjectRoleDescription).where(
                ProjectRoleDescription.project_id == project_id,
                ProjectRoleDescription.member_id.in_(member_ids),
            )
        ).all()
        if member_ids
        else []
    )
    members_by_id = {member.id: member for member in members}
    instances_by_member: dict[str, list[AgentInstance]] = {}
    for instance in instances:
        instances_by_member.setdefault(instance.member_id, []).append(instance)
    descriptions_by_member = {
        row.member_id: row.description for row in role_descriptions
    }
    # 角色运行器/模型绑定（ROLE-BINDING-B1a）：对全部名册成员用**同一条**批量事实 SQL
    # （合同 §7.3 的同一段 SELECT/JOIN，只把请求 CTE 换成多行）一次取齐身份/名册/绑定/
    # 登记事实，避免逐角色 N+1；每个请求 pair 恒定 1 行（含无绑定行），因此空名册之外的
    # 成员都一定有事实行，binding_state 不会因为“查不到”而缺失。
    binding_facts_by_member: dict[str, dict] = {
        row["requested_member_id"]: row
        for row in read_role_binding_facts_batch(
            session, project_id=project_id, member_ids=member_ids
        )
    }
    if binding_facts_by_member:
        # R1 定向修正：批量事实 SQL 的最终视图是项目存在性的权威。若前置 ``_get_project``
        # 通过后项目被另一连接删除，批量子句的 ``project_exists = 0``，此时不得返回旧角色
        # 条目与 ``binding_state = null``，而应映射项目 404（与单角色读取同一事实规则）。
        if not any(
            row.get("project_exists") for row in binding_facts_by_member.values()
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
            )

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
            role_description=descriptions_by_member.get(agent.member_id),
            binding=build_role_binding_out(
                binding_facts_by_member.get(agent.member_id)
            ),
            binding_state=resolve_role_binding_state(
                binding_facts_by_member.get(agent.member_id)
            ),
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
    return _project_agent_outs(list(agents), session, project_id=project_id)


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


@router.put(
    "/{project_id}/agents/{member_id:path}/description",
    response_model=ProjectRoleDescriptionOut,
)
def update_agent_role_description(
    project_id: str,
    member_id: str,
    body: RoleDescriptionUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """保存或清除某成员在本项目的角色说明（ROLE-DESC-B1，专用入口）。

    合同（设计 §3.2–§3.3）：

    - **仅 human 可写**（``_require_human``），agent 调用 403；
    - ``description`` 必填键：``str`` 或显式 ``null``。请求体先经
      :func:`server.models.normalize_role_description` 归一化——**先判空白归 null、再查 2000
      Unicode 码点**，非空原文（含换行、``<script>`` 字面量）原样保存；
    - 非 ``null`` 写入要求目标成员**在当前名册**（``project_agents``），否则 404；
    - ``null``（无论来自显式 null 还是全空白归一）是"恢复默认"：删除该行；对不存在记录、
      甚至不在名册的成员都幂等返回 200 且 ``description=null``（设计 §3.3-D7）；
    - 响应 ``description`` 是**归一化后**的值（设计 §3.3-D6），``null`` 时 ``updated_at`` /
      ``updated_by`` 也如实为 ``null``（当前没有自定义记录）；
    - 并发为 last-write-wins：单一全文本字段，不引入版本号/CAS；
    - 本入口**只写说明文本**：不读也不写 ``business_role`` / ``decision_tier`` / 主控指定 /
      任务权限 / 名册 ``project_agents`` 行。
    """
    _require_human(current)
    _get_project(project_id, session)  # 项目不存在 → 404（先于任何写入）

    target_member_id = member_id.strip()
    description = body.description
    existing = (
        session.get(ProjectRoleDescription, (project_id, target_member_id))
        if target_member_id
        else None
    )

    if description is None:
        # 恢复默认：清理（含无记录 / 不在名册）幂等返回 200 + description=null。
        if existing is not None:
            session.delete(existing)
            session.commit()
        return ProjectRoleDescriptionOut(
            project_id=project_id,
            member_id=target_member_id,
            description=None,
            updated_at=None,
            updated_by=None,
        )

    if session.get(ProjectAgent, (project_id, target_member_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "role description target is not in the project roster: "
                f"{target_member_id}"
            ),
        )

    now = datetime.now(timezone.utc)
    if existing is None:
        session.add(
            ProjectRoleDescription(
                project_id=project_id,
                member_id=target_member_id,
                description=description,
                updated_by=current.id,
                updated_at=now,
            )
        )
    else:
        existing.description = description
        existing.updated_by = current.id
        existing.updated_at = now
        session.add(existing)
    session.commit()

    return ProjectRoleDescriptionOut(
        project_id=project_id,
        member_id=target_member_id,
        description=description,
        updated_at=now,
        updated_by=current.id,
    )


def _binding_response(
    project_id: str, member_id: str, session: Session
) -> RoleBindingResponse:
    """用**单条**事实 SQL 构造绑定响应（读取与写入响应共用同一套阶梯）。

    项目是否仍存在以这条事实 SQL 的最终 ``project_exists`` 为准（R1）：前置 ORM 读取
    之后被并发删除的项目同样映射 404，成功响应不会出现 ``binding_state = null``。
    """
    facts = read_role_binding_facts(session, project_id=project_id, member_id=member_id)
    _require_facts_project(facts)
    return RoleBindingResponse(
        project_id=project_id,
        member_id=member_id,
        binding=build_role_binding_out(facts),
        binding_state=resolve_role_binding_state(facts),
    )


@router.get(
    "/{project_id}/agents/{member_id:path}/binding",
    response_model=RoleBindingResponse,
)
def get_agent_role_binding(
    project_id: str,
    member_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """读取单角色绑定（任意已认证成员可读；合同 §4.3）。

    - 项目不存在 → **404**（保持原 API 错误语义，不造 ``unconfigured`` 之类状态）；
      存在性只认事实 SQL 的最终 ``project_exists``（R1）：不再先做一次会被并发删除淘汰的
      前置 ORM 项目读取，因此也不存在“前置通过、事实已无项目却返回 200/null”的窗口；
    - 成员已离册/已删除/被禁用/非 agent 时**仍返回**保留的存储行与失效状态
      （不 404、不自动清理），因为“存着但不有效”正是需要如实展示的事实；
    - ``binding: null`` 只表示**没有存储行**，不伪造默认运行器或模型；
    - 读取只做一条事实 SQL：不 UPDATE、不自动清理、不做第二条补查询。
    """
    target_member_id = member_id.strip()
    return _binding_response(project_id, target_member_id, session)


@router.put(
    "/{project_id}/agents/{member_id:path}/binding",
    response_model=RoleBindingResponse,
)
def put_agent_role_binding(
    project_id: str,
    member_id: str,
    body: RoleBindingUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """保存或解除某成员在本项目的运行器/模型绑定（**仅 human**；合同 §4.3）。

    - ``binding`` 是必填键；显式 ``null`` = 解除绑定（删除该行），对“无行”“成员不在名册”
      都幂等返回 200；
    - 非空写入按 §4.3 校验：项目不存在 → 404；目标不存在/禁用/非 agent/未入册 → 404；
      ``runner_id`` 不存在或已 ``retired`` → 422；字段校验失败 → 422（schema 层）；
    - 写入用**单条 SQLite upsert**（D3 last-write-wins），两个并发 ``PUT`` 不会因主键冲突
      报 409，最终收敛到后提交者；
    - 本入口**只写绑定表**：不新建角色、不改名册、不改 ``business_role`` /
      ``decision_tier`` / 主控指定 / 任务权限，也不触碰任何任务行或历史快照。
    """
    _require_human(current)
    _get_project(project_id, session)  # 项目不存在 → 404（先于任何写入）
    target_member_id = member_id.strip()

    binding = body.binding
    if binding is None:
        # 解除绑定：无行 / 不在名册都幂等 200，不做目标校验。
        existing = (
            session.get(ProjectRoleBinding, (project_id, target_member_id))
            if target_member_id
            else None
        )
        if existing is not None:
            session.delete(existing)
            session.commit()
        return _binding_response(project_id, target_member_id, session)

    _require_binding_target(project_id, target_member_id, session)
    runner = session.get(RunnerRegistry, binding.runner_id)
    if runner is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"runner_id is not registered: {binding.runner_id}",
        )
    if runner.adapter_status == RUNNER_ADAPTER_RETIRED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "runner_id is retired and cannot be used for new bindings: "
                f"{binding.runner_id}"
            ),
        )

    now = datetime.now(timezone.utc)
    values = {
        "project_id": project_id,
        "member_id": target_member_id,
        "runner_id": binding.runner_id,
        "model_source": binding.model_source,
        "provider_id": binding.provider_id,
        "connection_ref": binding.connection_ref,
        "model_id": binding.model_id,
        "model_alias": binding.model_alias,
        "model_display_name": binding.model_display_name,
        "updated_by": current.id,
        "updated_at": now,
    }
    # 残余窗口（合同 §4.3，如实记录）：runner_id 有效性是 upsert 之前的读校验；若登记恰在
    # 同瞬间被改为 retired，可能落一行引用 retired 运行器的绑定，读取时如实报
    # runner_retired，不会被误报为 bound；本片不扩 CAS。
    session.execute(
        sqlite_insert(ProjectRoleBinding)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["project_id", "member_id"],
            set_={
                key: value
                for key, value in values.items()
                if key not in {"project_id", "member_id"}
            },
        )
    )
    session.commit()
    return _binding_response(project_id, target_member_id, session)


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
    # R1：sync 的响应同样是“批量角色响应”，与 GET /agents 共用同一最终事实规则——
    # 项目在本请求提交后被另一连接删除时，不得返回 200 与 ``binding_state = null``。
    return _project_agent_outs(list(agents), session, project_id=project_id)


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
    # ROLE-DESC-B1（设计 §3.1-D9）：SQLite 未开启 foreign_keys PRAGMA，新表若不显式清理
    # 就会在删项目后留下孤儿行。这里显式删除本项目全部角色说明行；既有 project_agents
    # 的孤儿行是本片之前的既有事实，**本片不追改**（不为此扩大范围）。
    role_descriptions = session.exec(
        select(ProjectRoleDescription).where(
            ProjectRoleDescription.project_id == project_id
        )
    ).all()
    for row in role_descriptions:
        session.delete(row)
    # ROLE-BINDING-B1a（合同 §4.3）：项目删除时显式清理本项目绑定行；名册
    # ``project_agents`` 的孤儿行沿用既有边界，**本片不扩改**。
    role_bindings = session.exec(
        select(ProjectRoleBinding).where(ProjectRoleBinding.project_id == project_id)
    ).all()
    for row in role_bindings:
        session.delete(row)
    session.delete(project)
    session.commit()
    return None
