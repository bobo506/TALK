"""Project registration and metadata APIs (TALK project integration layer).

These endpoints back the `talk init` / `talk sync` CLI flows described in
``docs/spec/PROJECT_INTEGRATION.md`` §3 and §7: a project registers itself with
the TALK server and keeps its metadata in sync. The server only stores project
metadata; the actual ``.talk/`` profile files stay in the project repo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from cli.profiles import load_profile, resolve_profile_path, write_profile_file
from server.auth import get_current_member
from server.role_deletions import RoleDeletion, public as deletion_public
from server.role_startup import projection as startup_projection
from server.db import begin_immediate_write, get_session
from server.models import (
    CHOICE_SOURCE_CREATION_OPERATION,
    CHOICE_SOURCE_CREATION_OPERATION_MISMATCH,
    CHOICE_SOURCE_LEGACY_ATTACH,
    CHOICE_SOURCE_LEGACY_ATTACH_MISMATCH,
    CHOICE_SOURCE_LEGACY_MANUAL,
    IDENTITY_EXCLUSIVE_REFERENCE_REFUSED,
    PROJECT_ROLE_ORIGIN_IMPORTED,
    PROJECT_ROLE_ORIGIN_MANAGED,
    PROJECT_ROLE_POLICY_SOURCE_HUMAN,
    PROVISION_ACK_STATES,
    PROVISION_ERROR_CODE_MAX_CHARS,
    PROVISION_JOB_STATUS_PENDING,
    PROVISION_JOB_STATUS_SUCCEEDED,
    PROVISION_STEP_KEY_FILE,
    PROVISION_STEP_ORDER,
    PROVISION_STEP_PREFLIGHT,
    PROVISION_STEP_STATE_FAILED,
    PROVISION_STEP_STATE_PENDING,
    PROVISION_STEP_STATE_SKIPPED,
    PROVISION_STEP_STATE_SUCCEEDED,
    ROLE_IDENTITY_LEGACY,
    RUNNER_ADAPTER_RETIRED,
    SQLITE_SIGNED_INTEGER_MAX,
    AgentInstance,
    AgentInstanceOut,
    AgentProfileOut,
    AgentProfileUpdate,
    AgentTask,
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
    ProjectRole,
    ProjectRoleBinding,
    ProjectRoleCreate,
    ProjectRoleDescription,
    ProjectRoleDescriptionOut,
    ProjectRoleLegacyAttach,
    ProjectRoleListItem,
    ProjectRoleModelOut,
    ProjectRolePolicy,
    ProjectRoleRunnerOut,
    ProjectRoleTaskSummaryOut,
    ProjectRoleUpdate,
    ProjectSyncRequest,
    ProjectUpdate,
    RoleBindingResponse,
    RoleBindingUpdate,
    RoleCreationOperation,
    RoleCredentialRotateOut,
    RoleCredentialRotation,
    RoleDescriptionUpdate,
    RoleLegacyAttachOperation,
    RoleProvisionAckRequest,
    RoleProvisionJob,
    RoleProvisionJobOut,
    RoleProvisionRequest,
    RoleProvisionRosterPathsOut,
    RoleProvisionRosterPathsRequest,
    RoleRequestRotateRequest,
    ROLE_REQUEST_ERROR_CREDENTIAL_MISMATCH,
    ROLE_REQUEST_ERROR_KEY_CONFLICT,
    ROLE_REQUEST_ERROR_PAYLOAD_INVALID,
    ROLE_REQUEST_ERROR_SOURCE_REQUIRED,
    ROLE_REQUEST_HOST_ERROR_CODES,
    ROLE_REQUEST_KIND_RECOVER,
    RunnerModelChoice,
    RunnerRegistry,
    binding_fingerprint,
    build_fresh_provision_steps,
    build_role_binding_out,
    build_role_creation_fingerprint,
    build_role_legacy_attach_fingerprint,
    build_role_member_id,
    compute_provision_job_status,
    ensure_identity_exclusive_reference_allowed,
    model_choice_dimension_facts,
    new_role_api_key,
    new_role_member_id_suffix,
    normalize_operation_key,
    normalize_provision_roster_paths,
    normalize_provision_steps,
    provision_member_dir_name,
    normalize_role_description,
    normalize_role_name,
    normalize_runner_id,
    normalize_safe_identifier_token,
    prove_exclusive_identity,
    read_role_binding_facts,
    read_role_binding_facts_batch,
    resolve_role_binding_state,
    role_binding_dimension_facts,
    serialize_provision_job,
)
from server.role_provision_requests import (
    apply_create_intent_created,
    request_has_source_for_member,
    require_create_intent_for_creation,
    resolve_request_source,
)
from server.routes.groups import _group_out
from server.role_services import project_role_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _require_human(current: Member) -> None:
    if current.kind != "human":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only human members can manage projects")


def _get_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


def _project_row_exists_now(project_id: str, session: Session) -> bool:
    """TX-ALL 写锁内按**真实 SQL** 复查项目是否存在（F3 补正）。

    不能复用 ORM ``session.get(Project, ...)``：identity map 里可能已有本请求早先
    读取的旧 ``Project`` 对象，项目已被并发注销时它仍会命中缓存。这里直接发事实
    SQL，结果只反映当前事务快照。事实助手本身不固定 HTTP 错误码，映射由 API 层完成。
    """
    return (
        session.execute(
            text("SELECT 1 FROM projects WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).first()
        is not None
    )


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
        project_id=instance.project_id,
        launch_id=instance.launch_id,
        process_started_at=instance.process_started_at,
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

    projection_now = datetime.now(timezone.utc)
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
    role_rows = {
        role.member_id: role
        for role in session.exec(
            select(ProjectRole).where(
                ProjectRole.project_id == project_id,
                ProjectRole.member_id.in_(member_ids),
            )
        ).all()
    }
    names_by_member = {member: role.role_name for member, role in role_rows.items()}
    deletion_rows = {row.member_id: row for row in session.exec(select(RoleDeletion).where(
        RoleDeletion.project_id == project_id, RoleDeletion.member_id.in_(member_ids))).all()}
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
            archived=bool(role_rows.get(agent.member_id) and role_rows[agent.member_id].archived_at),
            deletion=deletion_public(deletion_rows[agent.member_id]) if agent.member_id in deletion_rows else None,
            startup=startup_projection(project_id, agent.member_id, session),
            role_name=names_by_member.get(agent.member_id),
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
            # R1-3：角色页真实数据源是 GET /agents，受管服务投影必须一并给出；
            # 无状态行时不伪造（默认 stopped / not_started 由投影如实表达）。
            service=project_role_service(
                project_id, agent.member_id, session, now=projection_now
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

    begin_immediate_write(session)
    ensure_identity_exclusive_reference_allowed(member_id, project_id, session)
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
    # F2 补正（合同 §7.5 第 3 条）：说明写入的引用守卫必须与实际 INSERT/UPDATE 处于
    # 同一个 SQLite 写事务；BEGIN IMMEDIATE 在守卫读取之前取得写锁。
    begin_immediate_write(session)

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

    # 角色生命周期 R1-1（合同 §7.5 第 3 条）：说明写入是“新增引用”，
    # 与写入同一事务校验新独占身份的项目归属。
    ensure_identity_exclusive_reference_allowed(
        target_member_id, project_id, session
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

    # F2 补正（合同 §7.5 第 3 条）：非空绑定的引用守卫与实际 upsert 处于同一
    # SQLite 写事务；显式写锁在守卫读取之前取得。解除绑定分支不需要引用守卫。
    begin_immediate_write(session)
    _require_binding_target(project_id, target_member_id, session)
    # 角色生命周期 R1-1（合同 §7.5 第 3 条）：绑定写入是“新增引用”，
    # 与写入同一事务校验新独占身份的项目归属。
    ensure_identity_exclusive_reference_allowed(
        target_member_id, project_id, session
    )
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

    # F2 补正（合同 §7.5 第 3 条）：名册 sync 的引用守卫与实际 delete/add 必须处于
    # 同一个 SQLite 写事务；BEGIN IMMEDIATE 在守卫读取之前取得写锁。
    begin_immediate_write(session)

    # 角色生命周期 R1-1（合同 §7.5 第 3 条）：名册 sync 是与新增写入同一事务的引用守卫。
    # 新独占身份只归属创建项目；历史无 ProjectRole / imported / 非独占成员完全保留旧行为。
    for entry in body.agents:
        ensure_identity_exclusive_reference_allowed(entry.member_id, project_id, session)

    existing = session.exec(
        select(ProjectAgent).where(ProjectAgent.project_id == project_id)
    ).all()
    pending_deletions = {row.member_id for row in session.exec(select(RoleDeletion).where(
        RoleDeletion.project_id == project_id, RoleDeletion.status != "complete")).all()}
    for row in existing:
        if row.member_id not in pending_deletions:
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


# ══════════════════════════════════════════════════════════════════════
# 角色生命周期 R1-1：项目角色读取 / 原子创建 / 改名与豁免 / 凭据恢复
# （合同 §5.2、§7.2、§7.3、§7.5、§8）
#
# 本片**不**启动角色服务、不做宿主配置、不实现删除/归档入口；公开读取面
# 永不返回 api_key / owner_token / claim_token / 绝对路径 / argv。
# ══════════════════════════════════════════════════════════════════════


def _tx_add_role_fact(session: Session, row: object) -> None:
    """TX-ALL 的唯一写入漏斗。

    六个写入点全部经此函数，使“逐步故障注入”测试可以在任意一步抛异常，
    验证单事务整体回滚后六表零残留、且没有操作行（合同 §7.7 T-R1-a）。
    """
    session.add(row)


def _mapped_choice_matches_current_binding(
    session: Session, facts: dict, mapped_choice_id: str
) -> bool:
    """映射 choice 是否存在，且与**当前绑定**六维逐项完全一致。

    创建映射与补录映射共用这一条判定（ROLE_LEGACY_ATTACH_DESIGN §投影与宿主守卫）：
    只有 ``binding_exists`` 且 ``runner_id/model_source/provider_id/connection_ref/model_id/
    model_alias`` 六项全等才算“同一次选择”；否则一律失配并置空 ``choice_id``，
    **不**按 ``model_id`` 反查猜测（同一 ``model_id`` 可能对应多条连接）。
    """
    mapped = session.get(RunnerModelChoice, mapped_choice_id)
    if mapped is None or not facts.get("binding_exists"):
        return False
    current_dimensions = (
        facts.get("runner_id"),
        facts.get("model_source"),
        facts.get("provider_id"),
        facts.get("connection_ref"),
        facts.get("model_id"),
        facts.get("model_alias") or "",
    )
    return model_choice_dimension_facts(mapped) == current_dimensions


def _role_projection(
    project_id: str, member_ids: list[str], session: Session
) -> dict[str, ProjectRoleListItem]:
    """构造角色列表/单角色投影（合同 §5.2）。

    ``model.choice_id`` 的唯一可信来源是创建操作映射，且必须与**当前绑定**六维事实
    完全一致；失配或老名册一律 ``null`` 并用 ``choice_source`` 如实标注，
    **不**按 ``model_id`` 反查猜测（同 model_id 可能有多连接）。
    """
    if not member_ids:
        return {}
    roles = {
        row.member_id: row
        for row in session.exec(
            select(ProjectRole)
            .where(ProjectRole.project_id == project_id)
            .where(ProjectRole.member_id.in_(member_ids))
        ).all()
    }
    members = {
        row.id: row
        for row in session.exec(
            select(Member).where(Member.id.in_(member_ids))
        ).all()
    }
    descriptions = {
        row.member_id: row.description
        for row in session.exec(
            select(ProjectRoleDescription)
            .where(ProjectRoleDescription.project_id == project_id)
            .where(ProjectRoleDescription.member_id.in_(member_ids))
        ).all()
    }
    operations = {
        row.member_id: row
        for row in session.exec(
            select(RoleCreationOperation)
            .where(RoleCreationOperation.project_id == project_id)
            .where(RoleCreationOperation.member_id.in_(member_ids))
        ).all()
    }
    # 存量角色补录映射（ROLE_LEGACY_ATTACH_DESIGN §投影与宿主守卫）：与创建映射**独立**成表，
    # 因此这里也独立读取；两者并存时按冲突处理，不任选一条放行。
    attach_operations = {
        row.member_id: row
        for row in session.exec(
            select(RoleLegacyAttachOperation)
            .where(RoleLegacyAttachOperation.project_id == project_id)
            .where(RoleLegacyAttachOperation.member_id.in_(member_ids))
        ).all()
    }
    facts_by_member = {
        row["requested_member_id"]: row
        for row in read_role_binding_facts_batch(
            session, project_id=project_id, member_ids=member_ids
        )
    }
    deletion_rows = {row.member_id: row for row in session.exec(select(RoleDeletion).where(
        RoleDeletion.project_id == project_id, RoleDeletion.member_id.in_(member_ids))).all()}

    projected: dict[str, ProjectRoleListItem] = {}
    now = datetime.now(timezone.utc)
    for member_id in member_ids:
        role = roles.get(member_id)
        member = members.get(member_id)
        facts = facts_by_member.get(member_id) or {}
        binding_out = build_role_binding_out(facts)
        if role is not None:
            role_name = role.role_name
            origin = role.origin
            identity = role.origin
            archived = role.archived_at is not None
            identity_exclusive = bool(role.identity_exclusive)
        else:
            # 历史老名册兼容投影：如实标 imported / legacy，不具备生命周期操作。
            role_name = (
                member.display_name if member is not None else member_id
            )
            origin = PROJECT_ROLE_ORIGIN_IMPORTED
            identity = ROLE_IDENTITY_LEGACY
            archived = False
            identity_exclusive = False

        operation = operations.get(member_id)
        attach_operation = attach_operations.get(member_id)
        choice_source = CHOICE_SOURCE_LEGACY_MANUAL
        choice_id = None
        choice_binding_mismatch = False
        if operation is not None and attach_operation is not None:
            # 双创建/补录映射冲突：同一身份不允许同时存在两类可信映射，如实失配并拒绝启动，
            # **不**挑一条“看起来对得上”的放行。
            choice_source = CHOICE_SOURCE_LEGACY_ATTACH_MISMATCH
            choice_binding_mismatch = True
        elif attach_operation is not None:
            if _mapped_choice_matches_current_binding(
                session, facts, attach_operation.choice_id
            ):
                choice_source = CHOICE_SOURCE_LEGACY_ATTACH
                choice_id = attach_operation.choice_id
            else:
                choice_source = CHOICE_SOURCE_LEGACY_ATTACH_MISMATCH
                choice_binding_mismatch = True
        elif operation is not None:
            if _mapped_choice_matches_current_binding(
                session, facts, operation.choice_id
            ):
                choice_source = CHOICE_SOURCE_CREATION_OPERATION
                choice_id = operation.choice_id
            else:
                choice_source = CHOICE_SOURCE_CREATION_OPERATION_MISMATCH
                choice_binding_mismatch = True

        projected[member_id] = ProjectRoleListItem(
            member_id=member_id,
            deletion=deletion_public(deletion_rows[member_id]) if member_id in deletion_rows else None,
            startup=startup_projection(project_id,member_id,session),
            role_name=role_name,
            origin=origin,
            identity=identity,
            archived=archived,
            identity_exclusive=identity_exclusive,
            runner=ProjectRoleRunnerOut(
                runner_id=binding_out.runner_id if binding_out else None,
                runtime=binding_out.runtime if binding_out else None,
                display_name=binding_out.runner_display_name if binding_out else None,
                status=binding_out.runner_status if binding_out else None,
            ),
            model=ProjectRoleModelOut(
                choice_id=choice_id,
                choice_source=choice_source,
                choice_binding_mismatch=choice_binding_mismatch,
                model_id=binding_out.model_id if binding_out else None,
                model_alias=binding_out.model_alias if binding_out else None,
                model_display_name=binding_out.model_display_name if binding_out else None,
            ),
            role_description=descriptions.get(member_id),
            binding_state=resolve_role_binding_state(facts),
            # R1-3：真实服务投影（只读、无 token/argv/绝对路径；无状态行时不伪造）。
            service=project_role_service(project_id, member_id, session, now=now),
        )
    return projected


def _role_list_member_ids(project_id: str, session: Session) -> list[str]:
    """角色列表的成员集合：本项目角色行 ∪ 当前名册成员（历史老名册兼容投影）。"""
    role_ids = {
        row.member_id
        for row in session.exec(
            select(ProjectRole).where(ProjectRole.project_id == project_id)
        ).all()
    }
    roster_ids = {
        row.member_id
        for row in session.exec(
            select(ProjectAgent).where(ProjectAgent.project_id == project_id)
        ).all()
    }
    deleted = {row.member_id for row in session.exec(select(RoleDeletion).where(
        RoleDeletion.project_id == project_id, RoleDeletion.status == "complete")).all()}
    return sorted((role_ids | roster_ids) - deleted)


@router.get("/{project_id}/roles", response_model=list[ProjectRoleListItem])
def list_project_roles(
    project_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """列出项目角色（任意已认证成员可读；合同 §5.2）。

    - 包含尚未补录的**历史名册**成员（``origin=imported`` / ``identity=legacy``）；
    - ``service`` 在 R1-1 恒为 ``null``（无服务表，不推导状态）；
    - 不返回 Key / token / 绝对路径 / argv。
    """
    _get_project(project_id, session)
    member_ids = _role_list_member_ids(project_id, session)
    if not member_ids:
        return []
    projected = _role_projection(project_id, member_ids, session)
    return [projected[member_id] for member_id in member_ids]


def _allocate_role_member_id(project_id: str, role_name: str, session: Session) -> str:
    """分配全新 ``member_id``：主键冲突只重取随机后缀，**绝不**复用已存在成员。"""
    for _ in range(8):
        candidate = build_role_member_id(
            project_id, role_name, new_role_member_id_suffix()
        )
        if session.get(Member, candidate) is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="member_id_allocation_failed"
    )


def _allocate_role_api_key(session: Session) -> str:
    """分配全新 API Key（唯一列冲突重试；不落任何额外明文副本）。"""
    for _ in range(8):
        candidate = new_role_api_key()
        if session.exec(select(Member).where(Member.api_key == candidate)).first() is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="api_key_generation_failed"
    )


@router.post("/{project_id}/roles")
def create_project_role(
    project_id: str,
    body: ProjectRoleCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """创建项目角色（**仅 human**；合同 §7.2 TX-ALL 单写事务）。

    - 同一 ``operation_key`` 重放：同载荷 → ``200 {reused:true}`` 且**不返回 Key**；
      异载荷 → ``409 operation_key_conflict``；
    - 目录后来下架/改名**不**阻断重放（命中即回原身份的当前投影）；
    - 任一步失败整体回滚：六张表零残留、**没有操作行**，同 key 同载荷可直接重试；
    - 原子写入 ``members`` / ``project_roles`` / ``project_agents`` /
      ``project_role_bindings`` / ``project_role_descriptions`` / ``role_creation_operations``。
    """
    _require_human(current)
    _get_project(project_id, session)

    try:
        role_name = normalize_role_name(body.role_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role_name_invalid",
        ) from exc
    try:
        # R1-4 补正：与注册入口 ``POST /api/runners``（``RunnerCreate`` 校验器）同源，
        # 用 ``normalize_runner_id`` 校验 ``runner_id``；``choice_id`` 仍走通用安全 token
        # 规则（含有限凭据启发式），不放宽任何其它字段。
        runner_id = normalize_runner_id(body.runner_id)
        choice_id = normalize_safe_identifier_token(body.choice_id, field="choice_id")
        operation_key = normalize_operation_key(body.operation_key)
        role_description = normalize_role_description(body.role_description)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    fingerprint = build_role_creation_fingerprint(
        project_id=project_id,
        role_name=role_name,
        runner_id=runner_id,
        choice_id=choice_id,
        role_description=role_description,
    )

    # TX-ALL：BEGIN IMMEDIATE 让写事务互斥，重放判定与写入之间没有可被并发插入的窗口。
    begin_immediate_write(session)
    try:
        # 创建与补录共用操作键命名空间：同一写锁内反向核验补录已提交事实，
        # 防止补录先成功后又按同key创建第二个身份（包括跨项目和并发入口）。
        if session.get(RoleLegacyAttachOperation, operation_key) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="operation_key_conflict"
            )
        committed = session.get(RoleCreationOperation, operation_key)
        if committed is not None:
            if committed.request_fingerprint != fingerprint:
                session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="operation_key_conflict",
                )
            replay_member_id = committed.member_id
            deleted_role = session.get(ProjectRole, (project_id, replay_member_id))
            if deleted_role and deleted_role.archived_at is not None:
                raise HTTPException(409, "role_archived")
            # 未写任何事实：直接释放写锁，再按原身份的当前只读投影返回（不发 Key）。
            session.rollback()
            item = _role_projection(project_id, [replay_member_id], session)[
                replay_member_id
            ]
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=jsonable_encoder(
                    {"role": item, "member_id": replay_member_id, "reused": True}
                ),
            )

        # F3 补正（合同 §7.2 步骤 1）：新操作必须在 TX-ALL 写锁内复查**真实**项目，
        # 而不是只信 begin_immediate_write 之前的 ORM 读取（identity map 会保留已被
        # 并发注销的旧 Project 对象）。注销先提交 → 这里 404 且六表零新增；已提交
        # operation 的重放已在上面返回，不受目录实时状态影响。
        if not _project_row_exists_now(project_id, session):
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
            )

        # R1-4a（REQUEST_CONTRACT §6）：`operation_key` 命中 create 意图时走首次创建守卫。
        # 未命中任何意图时返回 None，下面继续走原有 R1-1 旧人工创建路径（行为不变）。
        intent_row = require_create_intent_for_creation(
            project_id,
            operation_key,
            fingerprinted_payload={
                "role_name": role_name,
                "runner_id": runner_id,
                "choice_id": choice_id,
                "role_description": role_description,
            },
            request_fingerprint=fingerprint,
            lease_token=body.lease_token,
            session=session,
        )

        runner = session.get(RunnerRegistry, runner_id)
        if runner is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="runner_not_found"
            )
        choice = session.get(RunnerModelChoice, choice_id)
        if choice is None or choice.runner_id != runner_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="choice_not_found"
            )
        if runner.adapter_status == RUNNER_ADAPTER_RETIRED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="runner_retired"
            )
        if choice.retired_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="choice_retired"
            )
        conflict = session.exec(
            select(ProjectRole)
            .where(ProjectRole.project_id == project_id)
            .where(ProjectRole.role_name == role_name)
            .where(ProjectRole.archived_at.is_(None))
        ).first()
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="role_name_conflict"
            )

        member_id = _allocate_role_member_id(project_id, role_name, session)
        api_key = _allocate_role_api_key(session)
        now = datetime.now(timezone.utc)
        _tx_add_role_fact(
            session,
            Member(
                id=member_id,
                kind="agent",
                display_name=role_name,
                api_key=api_key,
                created_at=now,
            ),
        )
        _tx_add_role_fact(
            session,
            ProjectRole(
                project_id=project_id,
                member_id=member_id,
                role_name=role_name,
                origin=PROJECT_ROLE_ORIGIN_MANAGED,
                identity_exclusive=1,
                credential_version=1,
                key_issued_at=now,
                key_rotated_at=None,
                created_by=current.id,
                created_at=now,
                updated_at=now,
                archived_at=None,
            ),
        )
        _tx_add_role_fact(
            session,
            ProjectAgent(
                project_id=project_id,
                member_id=member_id,
                identity_path=None,
                soul_path=None,
                user_path=None,
                memory_pointer=None,
                business_role=None,
                decision_tier=None,
                capability_summary=[],
                updated_at=now,
            ),
        )
        _tx_add_role_fact(
            session,
            ProjectRoleBinding(
                project_id=project_id,
                member_id=member_id,
                runner_id=choice.runner_id,
                model_source=choice.model_source,
                provider_id=choice.provider_id,
                connection_ref=choice.connection_ref,
                model_id=choice.model_id,
                model_alias=choice.model_alias or None,
                model_display_name=choice.model_display_name,
                updated_by=current.id,
                updated_at=now,
            ),
        )
        if role_description is not None:
            _tx_add_role_fact(
                session,
                ProjectRoleDescription(
                    project_id=project_id,
                    member_id=member_id,
                    description=role_description,
                    updated_by=current.id,
                    updated_at=now,
                ),
            )
        _tx_add_role_fact(
            session,
            RoleCreationOperation(
                operation_key=operation_key,
                request_fingerprint=fingerprint,
                project_id=project_id,
                requested_role_name=role_name,
                runner_id=runner_id,
                choice_id=choice_id,
                member_id=member_id,
                committed_at=now,
                created_by=current.id,
                created_at=now,
                updated_at=now,
            ),
        )
        if intent_row is not None:
            # 同一 TX-ALL：请求 `leased`→`created` 并回填真实 member_id / origin_operation_key。
            apply_create_intent_created(intent_row, member_id=member_id, session=session)
        session.commit()
    except HTTPException:
        if session.in_transaction():
            session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        committed = session.get(RoleCreationOperation, operation_key)
        if committed is not None:
            if committed.request_fingerprint != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="operation_key_conflict",
                ) from exc
            replay_member_id = committed.member_id
            item = _role_projection(project_id, [replay_member_id], session)[
                replay_member_id
            ]
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=jsonable_encoder(
                    {"role": item, "member_id": replay_member_id, "reused": True}
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="role_name_conflict"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - 任何未预期失败都整体回滚，不留部分事实
        if session.in_transaction():
            session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="role_creation_failed",
        ) from exc

    item = _role_projection(project_id, [member_id], session)[member_id]
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=jsonable_encoder(
            {
                "role": item,
                "member_id": member_id,
                "api_key": api_key,
                "reused": False,
                "credential_version": 1,
            }
        ),
    )


def _derive_legacy_role_name(member: Member) -> str:
    """补录角色名沿用当前display_name，仅空白时回落member_id。

    非空名称不合法时由调用方返回422 role_name_invalid，不能悄悄换成member_id；
    同名冲突另行409，保持原成员与角色名称事实。
    """
    candidate = (member.display_name or "").strip() or member.id
    return normalize_role_name(candidate)


@router.post("/{project_id}/roles/legacy-attach")
def legacy_attach_project_role(
    project_id: str,
    body: ProjectRoleLegacyAttach,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """存量角色补录：把**已有身份**登记为页面可管角色（**仅 human**）。

    ROLE_LEGACY_ATTACH_DESIGN §接口与保留事实 / §原子补录、幂等与来源：

    - 只接受当前项目名册内、未禁用的 ``agent``，且其本项目尚无 ``ProjectRole`` 行；
    - 原子新增 ``origin=imported`` / ``identity_exclusive=0`` / ``credential_version=1``
      （仅跟踪基线，未签发/未轮换）的角色行 + **缺失时**的精确绑定 + 独立补录审计行；
    - **不**生成/返回/轮换 Key，**不**改 ``Member``、既有绑定/名册/说明/策略/运行器状态、
      其它项目或历史，**不**创建 provision 作业、**不**写 launch、**不**启动服务；
    - 同 ``operation_key`` 同载荷重放 → ``200 {reused:true}``（不恢复后续被改的绑定或归档）；
      异载荷/跨项目/跨成员/与既有创建操作同 key → ``409 operation_key_conflict``；
    - 任何一步失败整体回滚：三张表零残留、无 pending 行，同 key 同载荷可直接重试。
    """
    _require_human(current)
    _get_project(project_id, session)

    try:
        member_id = normalize_safe_identifier_token(body.member_id, field="member_id")
        runner_id = normalize_runner_id(body.runner_id)
        choice_id = normalize_safe_identifier_token(body.choice_id, field="choice_id")
        operation_key = normalize_operation_key(body.operation_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    fingerprint = build_role_legacy_attach_fingerprint(
        project_id=project_id,
        member_id=member_id,
        runner_id=runner_id,
        choice_id=choice_id,
    )

    # TX-ALL：BEGIN IMMEDIATE 让写事务互斥，引用重读、幂等判定与写入之间没有并发插入窗口。
    begin_immediate_write(session)
    try:
        # 与创建入口双向核验；即使底层存在非法双映射，也不能把重放当成成功。
        if session.get(RoleCreationOperation, operation_key) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="operation_key_conflict"
            )
        committed = session.get(RoleLegacyAttachOperation, operation_key)
        if committed is not None:
            if committed.request_fingerprint != fingerprint:
                session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="operation_key_conflict",
                )
            replay_member_id = committed.member_id
            # 未写任何事实：释放写锁后按原身份的**当前**只读投影返回；重放不恢复后续变更。
            session.rollback()
            item = _role_projection(project_id, [replay_member_id], session)[
                replay_member_id
            ]
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=jsonable_encoder(
                    {"role": item, "member_id": replay_member_id, "reused": True}
                ),
            )

        # 写锁内用真实 SQL 复查项目（identity map 可能仍持有已被并发注销的旧对象）。
        if not _project_row_exists_now(project_id, session):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
            )

        member = session.get(Member, member_id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="member_not_found"
            )
        if member.kind != "agent":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="member_not_agent"
            )
        if member.disabled_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="member_disabled"
            )
        roster_entry = session.exec(
            select(ProjectAgent)
            .where(ProjectAgent.project_id == project_id)
            .where(ProjectAgent.member_id == member_id)
        ).first()
        if roster_entry is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="member_not_in_roster"
            )
        existing_role = session.exec(
            select(ProjectRole)
            .where(ProjectRole.project_id == project_id)
            .where(ProjectRole.member_id == member_id)
        ).first()
        if existing_role is not None:
            # 已有 managed / 已有 imported / 已归档：一律拒绝，不借此恢复、改写或改名。
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="role_already_exists"
            )
        # 新独占身份（本流程创建）只归属创建项目：跨项目补录引用一律拒绝。
        ensure_identity_exclusive_reference_allowed(member_id, project_id, session)
        if (
            session.exec(
                select(RoleCreationOperation).where(
                    RoleCreationOperation.member_id == member_id
                )
            ).first()
            is not None
        ):
            # 该身份已有创建映射：不接受同一身份同时存在创建与补录两类可信映射。
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=IDENTITY_EXCLUSIVE_REFERENCE_REFUSED,
            )

        try:
            role_name = _derive_legacy_role_name(member)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="role_name_invalid",
            ) from exc
        name_conflict = session.exec(
            select(ProjectRole)
            .where(ProjectRole.project_id == project_id)
            .where(ProjectRole.role_name == role_name)
            .where(ProjectRole.archived_at.is_(None))
        ).first()
        if name_conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="role_name_conflict"
            )

        runner = session.get(RunnerRegistry, runner_id)
        if runner is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="runner_not_found"
            )
        choice = session.get(RunnerModelChoice, choice_id)
        if choice is None or choice.runner_id != runner_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="choice_not_found"
            )
        if runner.adapter_status == RUNNER_ADAPTER_RETIRED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="runner_retired"
            )
        if choice.retired_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="choice_retired"
            )

        now = datetime.now(timezone.utc)
        binding = session.exec(
            select(ProjectRoleBinding)
            .where(ProjectRoleBinding.project_id == project_id)
            .where(ProjectRoleBinding.member_id == member_id)
        ).first()
        if binding is not None:
            # 既有绑定必须与显式选择的 choice 六维完全一致：保留原行每个字段（含
            # updated_at/updated_by），不推断模型、不替换、不“顺手修正”。
            if role_binding_dimension_facts(binding) != model_choice_dimension_facts(
                choice
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="binding_choice_mismatch",
                )
        else:
            _tx_add_role_fact(
                session,
                ProjectRoleBinding(
                    project_id=project_id,
                    member_id=member_id,
                    runner_id=choice.runner_id,
                    model_source=choice.model_source,
                    provider_id=choice.provider_id,
                    connection_ref=choice.connection_ref,
                    model_id=choice.model_id,
                    model_alias=choice.model_alias or None,
                    model_display_name=choice.model_display_name,
                    updated_by=current.id,
                    updated_at=now,
                ),
            )
        _tx_add_role_fact(
            session,
            ProjectRole(
                project_id=project_id,
                member_id=member_id,
                role_name=role_name,
                origin=PROJECT_ROLE_ORIGIN_IMPORTED,
                identity_exclusive=0,
                credential_version=1,
                key_issued_at=None,
                key_rotated_at=None,
                created_by=current.id,
                created_at=now,
                updated_at=now,
                archived_at=None,
            ),
        )
        _tx_add_role_fact(
            session,
            RoleLegacyAttachOperation(
                operation_key=operation_key,
                request_fingerprint=fingerprint,
                project_id=project_id,
                member_id=member_id,
                runner_id=runner_id,
                choice_id=choice_id,
                derived_role_name=role_name,
                committed_at=now,
                created_by=current.id,
                created_at=now,
                updated_at=now,
            ),
        )
        session.commit()
    except HTTPException:
        if session.in_transaction():
            session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        committed = session.get(RoleLegacyAttachOperation, operation_key)
        if committed is not None:
            if committed.request_fingerprint != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="operation_key_conflict",
                ) from exc
            replay_member_id = committed.member_id
            item = _role_projection(project_id, [replay_member_id], session)[
                replay_member_id
            ]
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=jsonable_encoder(
                    {"role": item, "member_id": replay_member_id, "reused": True}
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="role_already_exists"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - 任何未预期失败都整体回滚，不留部分事实
        if session.in_transaction():
            session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="legacy_attach_failed",
        ) from exc

    item = _role_projection(project_id, [member_id], session)[member_id]
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=jsonable_encoder({"role": item, "member_id": member_id, "reused": False}),
    )


@router.patch("/{project_id}/roles/{member_id}", response_model=ProjectRoleListItem)
def update_project_role(
    project_id: str,
    member_id: str,
    body: ProjectRoleUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """改角色名 / 介绍 / 复核豁免（**仅 human**；合同 §5.2 / §8.2）。

    - 改名只写 ``project_roles.role_name``，**不动** ``members.display_name``，
      也不影响其它项目；
    - ``role_description`` 显式 ``null`` = 恢复默认（删除自定义行）；
    - ``review_exempt`` 只能由 human 经本入口授予/撤销，agent 403（不可自授）；
    - 未知字段 422。
    """
    _require_human(current)
    _get_project(project_id, session)
    target_member_id = member_id.strip()
    role = session.get(ProjectRole, (project_id, target_member_id))
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found"
        )
    if role.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="role_archived"
        )

    provided = body.model_fields_set
    now = datetime.now(timezone.utc)
    if "role_name" in provided:
        try:
            new_role_name = normalize_role_name(body.role_name)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="role_name_invalid",
            ) from exc
        if new_role_name != role.role_name:
            conflict = session.exec(
                select(ProjectRole)
                .where(ProjectRole.project_id == project_id)
                .where(ProjectRole.role_name == new_role_name)
                .where(ProjectRole.member_id != target_member_id)
                .where(ProjectRole.archived_at.is_(None))
            ).first()
            if conflict is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="role_name_conflict",
                )
            role.role_name = new_role_name

    if "role_description" in provided:
        try:
            description = normalize_role_description(body.role_description)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        existing_description = session.get(
            ProjectRoleDescription, (project_id, target_member_id)
        )
        if description is None:
            if existing_description is not None:
                session.delete(existing_description)
        elif existing_description is None:
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
            existing_description.description = description
            existing_description.updated_by = current.id
            existing_description.updated_at = now
            session.add(existing_description)

    if "review_exempt" in provided:
        if body.review_exempt is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="review_exempt cannot be null",
            )
        policy = session.get(ProjectRolePolicy, (project_id, target_member_id))
        if policy is None:
            policy = ProjectRolePolicy(
                project_id=project_id,
                member_id=target_member_id,
                review_exempt=1 if body.review_exempt else 0,
                source=PROJECT_ROLE_POLICY_SOURCE_HUMAN,
                granted_by=current.id,
                granted_at=now,
                updated_at=now,
            )
        else:
            policy.review_exempt = 1 if body.review_exempt else 0
            policy.source = PROJECT_ROLE_POLICY_SOURCE_HUMAN
            policy.granted_by = current.id
            policy.granted_at = now
            policy.updated_at = now
        session.add(policy)

    role.updated_at = now
    session.add(role)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="role_name_conflict"
        ) from exc
    return _role_projection(project_id, [target_member_id], session)[target_member_id]


@router.post(
    "/{project_id}/roles/{member_id}/rotate-key",
    response_model=RoleCredentialRotateOut,
)
def rotate_project_role_key(
    project_id: str,
    member_id: str,
    body: RoleRequestRotateRequest | None = None,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """managed 独占身份的凭据恢复（**仅 human**；合同 §7.5 / REQUEST_CONTRACT §7）。

    同一写事务内“证明独占 → 换 Key → 递增 ``credential_version``”：旧 Key 立即失效，
    新 Key 只在本次响应出现一次。imported/共享、离册、跨项目引用、在用实例/任务
    一律返回稳定拒绝码；R1-1 无服务表，**不查询不存在的表**（未来表存在时补查）。

    R1-4a：可选 body ``{request_key, lease_token, expected_credential_version}``。
    请求驱动角色必须带**明确 recover 来源**；无 body 且该成员已有任何 recover 来源行
    （含终态）时返回 ``provision_lease_required``，不退回旧旁路。请求驱动路径的重放
    **先查已执行记录**（``role_credential_rotations``）再对新副作用做当前版本 CAS，
    同意图最多轮换一次；重放响应省略 ``api_key``，旧无 body 响应结构保持不变。
    """
    _require_human(current)
    _get_project(project_id, session)
    target_member_id = member_id.strip()

    request_key = body.request_key if body is not None else None
    lease_token = body.lease_token if body is not None else None
    expected_version = body.expected_credential_version if body is not None else None

    source_row = None
    begin_immediate_write(session)
    session.expire_all()
    try:
        role = session.get(ProjectRole, (project_id, target_member_id))
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found"
            )
        if role.archived_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="role_archived"
            )
        if role.origin != PROJECT_ROLE_ORIGIN_MANAGED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="rotate_not_managed_identity",
            )
        member = session.get(Member, target_member_id)
        if member is None or member.kind != "agent":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="rotate_member_not_agent",
            )
        if member.disabled_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="rotate_member_disabled",
            )
        if not role.identity_exclusive:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="rotate_shared_identity_refused",
            )

        if request_key is None:
            if lease_token is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ROLE_REQUEST_ERROR_SOURCE_REQUIRED,
                )
            if request_has_source_for_member(project_id, target_member_id, session):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ROLE_REQUEST_ERROR_SOURCE_REQUIRED,
                )
        else:
            operation = session.exec(
                select(RoleCreationOperation)
                .where(RoleCreationOperation.project_id == project_id)
                .where(RoleCreationOperation.member_id == target_member_id)
            ).first()
            if operation is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="role_request_operation_mismatch",
                )
            source_row = resolve_request_source(
                project_id,
                operation_key=operation.operation_key,
                member_id=target_member_id,
                request_key=request_key,
                lease_token=lease_token,
                required_kind=ROLE_REQUEST_KIND_RECOVER,
                session=session,
            )
            fixed_before = int(source_row.expected_credential_version or 0)
            if expected_version is not None and int(expected_version) != fixed_before:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ROLE_REQUEST_ERROR_CREDENTIAL_MISMATCH,
                )
            # §7 顺序：先查该 intent_key 已执行记录（正常重放即使当前版本已是 after 也返回
            # 200 reused 且省略 Key），只有未执行才进入下面的当前版本 CAS 与新副作用。
            rotation = session.get(RoleCredentialRotation, source_row.request_key)
            if rotation is not None:
                if (
                    rotation.project_id != project_id
                    or rotation.member_id != target_member_id
                    or (
                        expected_version is not None
                        and int(expected_version)
                        != int(rotation.before_credential_version)
                    )
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=ROLE_REQUEST_ERROR_CREDENTIAL_MISMATCH,
                    )
                replayed_version = int(rotation.after_credential_version)
                session.rollback()
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "member_id": target_member_id,
                        "credential_version": replayed_version,
                        "reused": True,
                    },
                )
            if int(role.credential_version or 1) != fixed_before:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ROLE_REQUEST_ERROR_CREDENTIAL_MISMATCH,
                )

        proof = prove_exclusive_identity(project_id, target_member_id, session)
        if proof["refusal"] is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=proof["refusal"]
            )

        api_key = _allocate_role_api_key(session)
        now = datetime.now(timezone.utc)
        member.api_key = api_key
        session.add(member)
        role.credential_version = (role.credential_version or 1) + 1
        role.key_rotated_at = now
        role.updated_at = now
        session.add(role)
        if source_row is not None:
            session.add(
                RoleCredentialRotation(
                    intent_key=source_row.request_key,
                    project_id=project_id,
                    member_id=target_member_id,
                    before_credential_version=int(
                        source_row.expected_credential_version or 1
                    ),
                    after_credential_version=int(role.credential_version),
                    created_by=current.id,
                    created_at=now,
                )
            )
            source_row.revision = int(source_row.revision or 1) + 1
            source_row.updated_at = now
            session.add(source_row)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if source_row is not None:
                # 并发同意图：恰好一次轮换，另一个连接返回只读重放。
                existing = session.get(RoleCredentialRotation, source_row.request_key)
                if existing is not None:
                    return JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={
                            "member_id": target_member_id,
                            "credential_version": int(existing.after_credential_version),
                            "reused": True,
                        },
                    )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ROLE_REQUEST_ERROR_CREDENTIAL_MISMATCH,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="api_key_generation_failed",
            ) from exc
        credential_version = role.credential_version
    except HTTPException:
        if session.in_transaction():
            session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 - 失败整体回滚，旧 Key 保持有效
        if session.in_transaction():
            session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="role_rotation_failed",
        ) from exc

    if source_row is not None:
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "member_id": target_member_id,
                "credential_version": int(credential_version),
                "reused": False,
                "api_key": api_key,
            },
        )
    return RoleCredentialRotateOut(
        member_id=target_member_id,
        api_key=api_key,
        credential_version=credential_version,
    )


@router.get(
    "/{project_id}/roles/{member_id}/tasks",
    response_model=list[ProjectRoleTaskSummaryOut],
)
def list_project_role_tasks(
    project_id: str,
    member_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """该角色在本项目内的**非终态**任务摘要（任意已认证成员可读；合同 §5.2）。

    只读，不改任何任务行；创建侧与执行侧（``target_member_id`` / ``created_by``）
    都算该角色的在途任务，作为删除前置检查的索引。
    """
    _get_project(project_id, session)
    target_member_id = member_id.strip()
    if session.get(ProjectRole, (project_id, target_member_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found"
        )
    rows = session.exec(
        select(AgentTask)
        .where(AgentTask.project_id == project_id)
        .where(
            (AgentTask.target_member_id == target_member_id)
            | (AgentTask.created_by == target_member_id)
        )
        .where(AgentTask.status.in_(("queued", "running")))
        .order_by(AgentTask.id)
    ).all()
    return [
        ProjectRoleTaskSummaryOut(
            id=row.id,
            title=row.title,
            status=row.status,
            workflow_status=row.workflow_status,
            target_member_id=row.target_member_id,
            created_by=row.created_by,
            created_at=row.created_at,
        )
        for row in rows
        if row.id is not None
    ]


# ══════════════════════════════════════════════════════════════════════
# 角色生命周期 R1-2：跨宿主配置作业（PROVISION_CONTRACT §1/§2）
#
# 三个入口全部 **human-only**，只作用于已有服务端身份的宿主三步
# （profile / key_file / preflight）。作业**不**重建 Member / ProjectRole、
# **不**重发 Key、**不**改绑定/说明/权限策略/名册，也**不**返回或存储任何 Key、
# 凭据路径、绝对路径、argv 或原始异常文本。
# ══════════════════════════════════════════════════════════════════════


def _normalize_provision_operation_key(value: object) -> str:
    """归一化作业锚点 key；缺失/非法 → 422 ``operation_key_invalid``。"""
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="operation_key_invalid",
        )
    try:
        return normalize_operation_key(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="operation_key_invalid",
        ) from exc


def _normalize_provision_step_subset(
    steps: object,
) -> tuple[str, ...] | None:
    """``steps`` 只允许 ``null`` 或三步的**非空子集**（不重复）；否则 422。"""
    if steps is None:
        return None
    if not isinstance(steps, list) or not steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="provision_step_invalid",
        )
    subset: list[str] = []
    for step in steps:
        if (
            not isinstance(step, str)
            or step not in PROVISION_STEP_ORDER
            or step in subset
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="provision_step_invalid",
            )
        subset.append(step)
    return tuple(subset)


def _require_provision_identity(
    project_id: str, member_id: str, operation_key: str, session: Session
) -> None:
    """四个入口共用的前置校验（PROVISION_CONTRACT §2.1 第 1 条，顺序固定）。

    - imported/legacy（有 ``project_roles`` 或 ``project_agents`` 行但没有创建操作）
      一律拒绝 ``provision_imported_identity_unsupported``，**绝不**伪造创建操作；
    - 传入的 ``operation_key`` 必须命中该 ``(project_id, member_id)`` 的创建操作，
      否则 ``provision_operation_mismatch``（含 key 不存在的情况）；
    - 不写库、不改任何身份事实，只做读取判定。

    R1-2 补正 F2：三个**写入**入口都在 :func:`_begin_provision_write` 之后调用本函数，
    因此这里的可变引用读取（项目/角色/成员/名册）落在真实 ``BEGIN IMMEDIATE`` 写事务内；
    配合 ``session.expire_all()`` 不会命中 ORM identity map 的陈旧值。
    """
    if session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found"
        )

    identity_operation = session.exec(
        select(RoleCreationOperation)
        .where(RoleCreationOperation.project_id == project_id)
        .where(RoleCreationOperation.member_id == member_id)
    ).first()
    if identity_operation is None:
        has_role = session.get(ProjectRole, (project_id, member_id)) is not None
        has_roster = session.get(ProjectAgent, (project_id, member_id)) is not None
        if has_role or has_roster:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="provision_imported_identity_unsupported",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="provision_operation_not_found",
        )

    anchor = session.get(RoleCreationOperation, operation_key)
    if (
        anchor is None
        or anchor.project_id != project_id
        or anchor.member_id != member_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="provision_operation_mismatch",
        )

    role = session.get(ProjectRole, (project_id, member_id))
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found"
        )
    if role.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="role_archived"
        )
    member = session.get(Member, member_id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="provision_member_missing"
        )
    if member.kind != "agent":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="provision_member_not_agent"
        )
    if member.disabled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="provision_member_disabled"
        )
    if session.get(ProjectAgent, (project_id, member_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="provision_roster_missing"
        )


def _begin_provision_write(session: Session) -> None:
    """取得真实 SQLite 写锁并清空 ORM identity map（R1-2 补正 F2）。

    ``BEGIN IMMEDIATE`` 之后的引用守卫读取都落在同一物理写事务内；``expire_all()``
    保证随后 ``session.get(...)`` 重新走 SELECT，而不是命中同一 Session 里已加载的
    陈旧 ORM 对象。只作用于本请求自己的连接。
    """
    begin_immediate_write(session)
    session.expire_all()


def _provision_role_credential_version(
    project_id: str, member_id: str, session: Session
) -> int:
    """读当前角色的凭据版本（写事务内调用；行缺失 → 404 ``role_not_found``）。"""
    role = session.get(ProjectRole, (project_id, member_id))
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found"
        )
    return int(role.credential_version or 1)


def _normalize_provision_error_code(
    state: str, error_code: object, *, strict: bool = False
) -> str | None:
    """ACK 的 ``error_code`` 白名单（PROVISION_CONTRACT §2.3 / REQUEST_CONTRACT §2）。

    只有 ``failed`` 允许携带非空 ``error_code``，且必须是 ≤64 的安全 token；
    非 ``failed`` 携带任何非 ``null`` 值、或 ``failed`` 携带非法值 → 422。

    ``strict=True``（请求驱动 ACK，即请求携带了 ``request_key``/``lease_token`` 之一）时
    额外要求命中 ``ROLE_REQUEST_HOST_ERROR_CODES`` 有限稳定码白名单：未知串（含误传假
    凭据 / token / 路径片段）一律 422 且零写入。旧无请求入口保持原有安全 token 语义，
    不因本约束收窄既有行为。
    """
    if state != PROVISION_STEP_STATE_FAILED:
        if error_code is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="provision_error_code_invalid",
            )
        return None
    if error_code is None:
        return None
    if not isinstance(error_code, str) or not error_code.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="provision_error_code_invalid",
        )
    try:
        normalized = normalize_safe_identifier_token(
            error_code,
            field="error_code",
            max_chars=PROVISION_ERROR_CODE_MAX_CHARS,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="provision_error_code_invalid",
        ) from exc
    if strict and normalized not in ROLE_REQUEST_HOST_ERROR_CODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="provision_error_code_invalid",
        )
    return normalized


def _provision_expected_binding_fingerprint(
    job: RoleProvisionJob, session: Session
) -> str | None:
    """本作业锚定的创建操作所选 choice 的绑定内容指纹（只读、无密、可核对）。

    R1-2 followup 补正 G3：``job.operation_key`` 就是创建操作 ``operation_key``
    （``_require_provision_identity`` 已校验其 project/member 锚点），因此这里取得的
    choice 六维是**不可变预期来源**。消费者把它与 ``GET .../binding`` 本次读取的
    ``binding_fingerprint`` 逐对比较，就能发现分次投影之间的连接/来源/provider 漂移。
    choice 或运行器登记不可解析时如实为 ``null``（消费方 fail closed），不猜。
    """
    operation = session.get(RoleCreationOperation, job.operation_key)
    if operation is None:
        return None
    choice = session.get(RunnerModelChoice, operation.choice_id)
    if choice is None:
        return None
    runner = session.get(RunnerRegistry, choice.runner_id)
    return binding_fingerprint(
        {
            "runner_id": choice.runner_id,
            "runtime": runner.runtime if runner is not None else None,
            "model_source": choice.model_source,
            "provider_id": choice.provider_id,
            "connection_ref": choice.connection_ref,
            "model_id": choice.model_id,
        }
    )


def _provision_job_out(
    job: RoleProvisionJob,
    session: Session,
    role_credential_version: int | None = None,
) -> RoleProvisionJobOut:
    return RoleProvisionJobOut(
        **serialize_provision_job(
            job,
            role_credential_version=role_credential_version,
            expected_binding_fingerprint=_provision_expected_binding_fingerprint(
                job, session
            ),
        )
    )


@router.post(
    "/{project_id}/roles/{member_id}/provision",
    response_model=RoleProvisionJobOut,
)
def provision_project_role(
    project_id: str,
    member_id: str,
    body: RoleProvisionRequest,
    response: Response,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """创建 / 幂等读取 / 定向续跑跨宿主配置作业（**仅 human**；§2.1）。

    - 新建：全部三步 ``pending``、``attempts=1``、``status=pending``、``revision=1``、
      ``resume_of=null``，返回 **201**；若只是想读现有作业，用 ``GET``；
    - ``resume=false`` 且作业已存在：**原样返回**，不写库（幂等，200）；
    - 有作业行：
      - ``resume=false`` → **原样返回现有作业**（幂等，不写库）。
      - ``resume=true``：
        - ``status == "succeeded"`` 且凭据版本未变 → 409 ``provision_job_terminal``；
          凭据版本已变（轮换后旧证明失效）则允许重开：强制重置凭据相关的
          ``key_file`` / ``preflight``；
        - 否则：把 ``steps``（默认 = 全部 ``state in {"failed","pending"}`` 的步骤）重置为
          ``pending/attempts+=1/error_code=null``；``resume_of=operation_key``；
          ``revision+=1``；重算 ``status``。
        - ``steps`` 子集里若有步骤当前为 ``succeeded``/``skipped`` → 不重置它，仍计入响应
          （定向续跑不改已完成步骤）；但凭据版本已变时 ``key_file``/``preflight`` 例外。
    - 4. 响应状态码：创建 201，已存在未变 200，续跑 200。响应体 ``RoleProvisionJobOut``。
    - 补正 F1：创建/续跑都把当前 ``project_roles.credential_version`` 快照进作业
      （``credential_version`` 列），ACK 用它做代际校验。
    - 补正 F2：引用守卫（项目/角色/成员/名册/创建操作）在 ``BEGIN IMMEDIATE`` 写锁内执行，
      并对并发注销/离册/禁用/归档零脏写。
    """
    _require_human(current)
    target_member_id = member_id.strip()
    operation_key = _normalize_provision_operation_key(body.operation_key)
    target_steps = _normalize_provision_step_subset(body.steps)

    _begin_provision_write(session)
    try:
        _require_provision_identity(project_id, target_member_id, operation_key, session)
        # R1-4a（REQUEST_CONTRACT §5.1）：请求驱动角色必须按 body.request_key 精确取源并
        # 复查租约；省略 request_key 时若该原键存在**任何**来源行（含终态）一律拒绝，
        # 不退回旧人工旁路；确实没有来源行才保持原行为。
        resolve_request_source(
            project_id,
            operation_key=operation_key,
            member_id=target_member_id,
            request_key=body.request_key,
            lease_token=body.lease_token,
            required_kind=None,
            session=session,
        )
        current_credential_version = _provision_role_credential_version(
            project_id, target_member_id, session
        )
        job = session.get(RoleProvisionJob, operation_key)
        if job is None:
            now = datetime.now(timezone.utc)
            job = RoleProvisionJob(
                operation_key=operation_key,
                project_id=project_id,
                member_id=target_member_id,
                status=PROVISION_JOB_STATUS_PENDING,
                steps=build_fresh_provision_steps(),
                resume_of=None,
                revision=1,
                credential_version=current_credential_version,
                created_by=current.id,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            response.status_code = status.HTTP_201_CREATED
            return _provision_job_out(job, session, current_credential_version)

        if not body.resume:
            # 幂等读取：先构造响应，再释放写锁，不留任何未提交写入。
            payload = _provision_job_out(job, session, current_credential_version)
            session.rollback()
            return payload

        previous_credential_version = int(job.credential_version or 1)
        credential_changed = previous_credential_version != current_credential_version
        if job.status == PROVISION_JOB_STATUS_SUCCEEDED and not credential_changed:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="provision_job_terminal"
            )

        steps = normalize_provision_steps(job.steps)
        if target_steps is None:
            resume_steps = tuple(
                step
                for step in PROVISION_STEP_ORDER
                if steps[step]["state"]
                in (PROVISION_STEP_STATE_FAILED, PROVISION_STEP_STATE_PENDING)
            )
        else:
            resume_steps = target_steps
        if credential_changed:
            # 凭据轮换使旧 key_file/preflight 证明失效：无论之前成功与否都强制重置，
            # 否则作业会带着一个已经无法通过身份核验的 Key 报成功（补正 F1）。
            resume_steps = tuple(
                dict.fromkeys(
                    tuple(resume_steps)
                    + (PROVISION_STEP_KEY_FILE, PROVISION_STEP_PREFLIGHT)
                )
            )
        for step in resume_steps:
            entry = steps[step]
            if not credential_changed and entry["state"] in (
                PROVISION_STEP_STATE_SUCCEEDED,
                PROVISION_STEP_STATE_SKIPPED,
            ):
                continue
            entry["state"] = PROVISION_STEP_STATE_PENDING
            entry["attempts"] = int(entry["attempts"]) + 1
            entry["error_code"] = None
            entry["updated_at"] = None

        now = datetime.now(timezone.utc)
        job.steps = steps
        job.resume_of = operation_key
        job.revision = (job.revision or 1) + 1
        job.credential_version = current_credential_version
        job.status = compute_provision_job_status(steps)
        job.updated_at = now
        session.add(job)
        session.commit()
        session.refresh(job)
        return _provision_job_out(job, session, current_credential_version)
    except HTTPException:
        if session.in_transaction():
            session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        existing = session.get(RoleProvisionJob, operation_key)
        if existing is not None and not body.resume:
            return _provision_job_out(
                existing,
                session,
                _provision_role_credential_version(
                    project_id, target_member_id, session
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="provision_job_failed",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - 失败整体回滚，不留半截作业
        if session.in_transaction():
            session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="provision_job_failed",
        ) from exc


@router.get(
    "/{project_id}/roles/{member_id}/provision",
    response_model=RoleProvisionJobOut,
)
def get_project_role_provision(
    project_id: str,
    member_id: str,
    operation_key: str | None = Query(default=None),
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """读取一份跨宿主配置作业（**仅 human**；§2.2）。

    ``operation_key`` 缺失或非法 → 422；前置校验同 POST（imported/离册/归档等照样拒绝），
    但**不**要求作业一定存在：没有作业行 → 404 ``provision_job_not_found``。
    只读，不写任何表，响应白名单同 §2.4。

    同时回传**读取时**角色行的当前凭据版本（``role_credential_version``，补正 G1），
    让宿主能判定作业快照是否已被轮换作废。
    """
    _require_human(current)
    target_member_id = member_id.strip()
    key = _normalize_provision_operation_key(operation_key)
    _require_provision_identity(project_id, target_member_id, key, session)
    job = session.get(RoleProvisionJob, key)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="provision_job_not_found"
        )
    return _provision_job_out(
        job,
        session,
        _provision_role_credential_version(project_id, target_member_id, session),
    )


@router.post(
    "/{project_id}/roles/{member_id}/provision/ack",
    response_model=RoleProvisionJobOut,
)
def ack_project_role_provision(
    project_id: str,
    member_id: str,
    body: RoleProvisionAckRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """宿主单步 ACK / 回报（**仅 human**；§2.3），只写本作业。

    校验顺序与稳定错误码固定（先角色/成员/项目前置校验；再作业存在性；再 ``step``/
    ``state`` 合法；再 ``revision`` CAS；再该步必须 ``pending``；再 ``attempt`` CAS；
    再 ``credential_version`` 代际 CAS；最后 ``error_code`` 白名单），因此迟到或旧尝试的
    回报**不可能**把已完成步骤翻成成功：``revision``/``attempt``/``credential_version``
    任一过期即 409。成功时写步骤终态、``revision+=1``、重算 ``status``。
    本入口**不**触碰 R1-3 服务 claim/report。

    R1-2 补正 F1：``credential_version`` 必须同时等于作业快照与角色**当前**值；任一轮换
    都会让在途的旧成功证明失效（409 ``provision_credential_stale``），服务端不再允许
    用回报时的新 attempt 套旧工作。

    R1-2 补正 F2：引用守卫在 ``BEGIN IMMEDIATE`` 写锁内执行，并在锁内重读作业与角色。
    """
    _require_human(current)
    target_member_id = member_id.strip()
    operation_key = _normalize_provision_operation_key(body.operation_key)

    _begin_provision_write(session)
    try:
        _require_provision_identity(project_id, target_member_id, operation_key, session)
        job = session.get(RoleProvisionJob, operation_key)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="provision_job_not_found",
            )
        if body.step not in PROVISION_STEP_ORDER:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="provision_step_invalid",
            )
        if body.state not in PROVISION_ACK_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="provision_ack_state_invalid",
            )
        if body.revision != job.revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="provision_revision_conflict",
            )
        steps = normalize_provision_steps(job.steps)
        entry = steps[body.step]
        if entry["state"] != PROVISION_STEP_STATE_PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="provision_step_not_pending",
            )
        if body.attempt != entry["attempts"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="provision_stale_attempt",
            )
        current_credential_version = _provision_role_credential_version(
            project_id, target_member_id, session
        )
        if (
            body.credential_version != int(job.credential_version or 1)
            or body.credential_version != current_credential_version
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="provision_credential_stale",
            )
        # R1-4a（REQUEST_CONTRACT §2/§8）：请求驱动的 ACK 与 A6 report 共用同一份有限
        # 稳定码白名单（参数“存在”按 is not None 判定）；旧无请求入口保持原安全 token 语义。
        request_driven = body.request_key is not None or body.lease_token is not None
        error_code = _normalize_provision_error_code(
            body.state, body.error_code, strict=request_driven
        )

        # R1-4a（REQUEST_CONTRACT §5.1/§8）：既有 ACK 规则与错误顺序全部跑完之后，才复查
        # 本请求来源与有效租约；失败零写入，旧 human 无 body 回放路径保持不变。
        resolve_request_source(
            project_id,
            operation_key=operation_key,
            member_id=target_member_id,
            request_key=body.request_key,
            lease_token=body.lease_token,
            required_kind=None,
            session=session,
        )

        now = datetime.now(timezone.utc)
        entry["state"] = body.state
        entry["error_code"] = error_code
        entry["updated_at"] = now.isoformat()
        job.steps = steps
        job.status = compute_provision_job_status(steps)
        job.revision = (job.revision or 1) + 1
        job.updated_at = now
        session.add(job)
        session.commit()
        session.refresh(job)
        return _provision_job_out(job, session, current_credential_version)
    except HTTPException:
        if session.in_transaction():
            session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 - 失败整体回滚，步骤状态保持原样
        if session.in_transaction():
            session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="provision_ack_failed",
        ) from exc


@router.post(
    "/{project_id}/roles/{member_id}/provision/roster-paths",
    response_model=RoleProvisionRosterPathsOut,
)
def register_project_role_roster_paths(
    project_id: str,
    member_id: str,
    body: RoleProvisionRosterPathsRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """登记本作业所属**单角色**的三条档案相对路径（**仅 human**）。

    为什么需要：``PUT /agents/{id}/profile`` 只写档案文件内容，从不回写
    ``project_agents`` 的 ``identity_path``/``soul_path``/``user_path``，宿主脚本因此
    无法让“档案与名册路径指向同一独立角色”成立。本入口是该作业范围内**唯一**的路径
    登记通道，且只作用于显式 ``(project_id, member_id)``。

    - 前置校验复用 ``_normalize_provision_operation_key`` + ``_require_provision_identity``：
      human-only 403、imported/离册/归档/禁用/策略不一致等稳定拒绝码与 POST /provision 相同；
    - 三条路径必须是**非空仓库相对路径**，归一化反斜杠为 ``/``，拒绝绝对路径（盘符/
      前导 ``/`` 或 ``\\\\``）、任何 ``..`` 段与控制字符，且必须恰好落在同一个
      ``.talk/agents/<role_dir>/`` 下、basename 分别为 ``IDENTITY.md``/``SOUL.md``/
      ``USER.md``；否则 422 ``provision_roster_path_invalid``；
    - 补正 F8：``<role_dir>`` 必须**恰好**等于目标 ``member_id`` 自己的目录名，拒绝把
      另一个角色的档案路径登记到本角色（跨角色路径一律 422）；
    - 成功时**只**更新该 ``ProjectAgent(project_id, member_id)`` 行的三条路径列与
      ``updated_at``：不动 ``business_role``/``decision_tier``/``capability_summary``、
      不动 Member/ProjectRole/绑定/说明/权限策略，也不动任何其它名册行；
    - 补正 F2：引用守卫与名册行复查都在 ``BEGIN IMMEDIATE`` 写锁内，与并发注销/离册/
      禁用/归档零脏写；
    - 不调用 ``/sync``、不写任何文件、不触网；响应只含
      ``{member_id, identity_path, soul_path, user_path}``。
    """
    _require_human(current)
    target_member_id = member_id.strip()
    operation_key = _normalize_provision_operation_key(body.operation_key)

    _begin_provision_write(session)
    try:
        _require_provision_identity(project_id, target_member_id, operation_key, session)
        try:
            paths = normalize_provision_roster_paths(
                body.identity_path,
                body.soul_path,
                body.user_path,
                expected_member_dir=provision_member_dir_name(target_member_id),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="provision_roster_path_invalid",
            ) from exc

        # 同一写锁内复查名册行仍然存在（并发 sync/注销不可能插进守卫与写入之间）。
        roster = session.get(ProjectAgent, (project_id, target_member_id))
        if roster is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="provision_roster_missing",
            )
        roster.identity_path = paths["identity_path"]
        roster.soul_path = paths["soul_path"]
        roster.user_path = paths["user_path"]
        roster.updated_at = datetime.now(timezone.utc)
        session.add(roster)
        session.commit()
        session.refresh(roster)
        return RoleProvisionRosterPathsOut(
            member_id=target_member_id,
            identity_path=roster.identity_path,
            soul_path=roster.soul_path,
            user_path=roster.user_path,
        )
    except HTTPException:
        if session.in_transaction():
            session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 - 失败整体回滚，名册行保持原样
        if session.in_transaction():
            session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="provision_roster_path_failed",
        ) from exc
