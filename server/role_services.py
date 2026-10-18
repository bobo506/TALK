"""角色生命周期 R1-3：受管 CLI 服务生命周期的服务端核心。

本合同实现（依据 ``docs/spec/ROLE_LIFECYCLE_DESIGN.md`` §4.1.5/§4.1.6/§10）：

- 服务端**只**记录期望状态、世代、动作与宿主回报的观测状态，**不** spawn/kill 进程；
- 每个启动/停止动作是一条 ``role_service_launches`` 行，``expected_instance_id`` 由服务端
  **预分配**，``launch_expires_at`` 是一等列；
- 同一角色同一时刻只有一个动作生效：``BEGIN IMMEDIATE`` 真实写事务 +
  ``role_service_state.generation`` 条件更新 + ``(project_id, member_id, generation)``
  唯一索引三重保证；
- start claim 一次性生成 ``owner_token`` + ``claim_token``（库内只存 sha256），
  stop claim 必须提交**原 start** 的 owner token 与原 host，只新发 ``claim_token``，
  绝不为原进程重新发行所有权；
- 就绪必须同时满足四条件（合法 ready 回报 + 本次预分配实例 + 当前世代/意图 +
  claim 后截止前的首次实例证据），``report`` 单独**不**判成功；
- 任何 token/Key 明文都不进公共 GET、页面、日志、交付包或异常文本；
- 本片**不**读取或改写任何生产 Key/配置/账号，也不调用真实模型。

R1-3 的动作错误码沿用合同 §10.6，并补充：
``control_kind_not_managed``（运行器未声明 ``managed_cli``，启动入口如实拒绝，
避免建一个没有宿主能领取的 launch）、``member_disabled``、``role_not_in_roster``、
``already_stopped``（重复关闭）。停止入口**不**受 ``control_kind`` 限制：
已受管的进程必须始终可停。
运行期另有实例不可用、关联不符和心跳过期三项只读诊断，不改动作回执或所有权。
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, select

from server.db import begin_immediate_write
from server.models import (
    ROLE_AUTO_START_ACTOR,
    ROLE_SERVICE_ACTION_START,
    ROLE_SERVICE_ACTION_STOP,
    ROLE_SERVICE_ERROR_ALREADY_RUNNING,
    ROLE_SERVICE_ERROR_ALREADY_STOPPED,
    ROLE_SERVICE_ERROR_CONTROL_KIND_NOT_MANAGED,
    ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH,
    ROLE_SERVICE_ERROR_GENERATION_CONFLICT,
    ROLE_SERVICE_ERROR_INSTANCE_HEARTBEAT_EXPIRED,
    ROLE_SERVICE_ERROR_INSTANCE_IDENTITY_MISMATCH,
    ROLE_SERVICE_ERROR_INSTANCE_UNAVAILABLE,
    ROLE_SERVICE_ERROR_LAUNCH_ACTION_MISMATCH,
    ROLE_SERVICE_ERROR_LAUNCH_EXPIRED,
    ROLE_SERVICE_ERROR_LAUNCH_NOT_FOUND,
    ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING,
    ROLE_SERVICE_ERROR_MEMBER_DISABLED,
    ROLE_SERVICE_ERROR_PROJECT_NOT_FOUND,
    ROLE_SERVICE_ERROR_READINESS_TIMEOUT,
    ROLE_SERVICE_ERROR_REPORT_CONFLICT,
    ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED,
    ROLE_SERVICE_ERROR_ROLE_ARCHIVED,
    ROLE_SERVICE_ERROR_ROLE_BINDING_MISSING,
    ROLE_SERVICE_ERROR_ROLE_NOT_FOUND,
    ROLE_SERVICE_ERROR_ROLE_NOT_IN_ROSTER,
    ROLE_SERVICE_ERROR_STALE_REPORT,
    ROLE_SERVICE_ERROR_STOP_TIMEOUT,
    ROLE_SERVICE_ERROR_UNKNOWN_OWNER,
    ROLE_SERVICE_INSTANCE_FRESH_SECONDS,
    ROLE_SERVICE_LAUNCH_CLAIMED,
    ROLE_SERVICE_LAUNCH_EXPIRED,
    ROLE_SERVICE_LAUNCH_PENDING,
    ROLE_SERVICE_LAUNCH_REPORTED,
    ROLE_SERVICE_LAUNCH_TTL_SECONDS,
    ROLE_SERVICE_MANAGER_CLI_PROCESS,
    ROLE_SERVICE_MODEL_ALIAS_RESOLVED,
    ROLE_SERVICE_MODEL_ALIAS_UNCONFIGURED,
    ROLE_SERVICE_MODEL_ALIAS_UNRESOLVED,
    ROLE_SERVICE_NATIVE_LOGIN_UNVERIFIED,
    ROLE_SERVICE_OBSERVED_FAILED,
    ROLE_SERVICE_OBSERVED_NOT_STARTED,
    ROLE_SERVICE_OBSERVED_RUNNING,
    ROLE_SERVICE_OBSERVED_STARTING,
    ROLE_SERVICE_OBSERVED_STOPPED,
    ROLE_SERVICE_OBSERVED_STOPPING,
    ROLE_SERVICE_OBSERVED_UNKNOWN,
    ROLE_SERVICE_OUTCOME_FAILED,
    ROLE_SERVICE_OUTCOME_READY,
    ROLE_SERVICE_OUTCOME_STOPPED,
    ROLE_SERVICE_READINESS_FAILED,
    ROLE_SERVICE_READINESS_PENDING,
    ROLE_SERVICE_READINESS_READY,
    ROLE_SERVICE_READINESS_UNKNOWN,
    ROLE_SERVICE_RESULT_FAILED,
    ROLE_SERVICE_RESULT_STOPPED,
    ROLE_SERVICE_RESULT_SUCCESS,
    ROLE_SERVICE_DESIRED_RUNNING,
    ROLE_SERVICE_DESIRED_STOPPED,
    ROLE_SERVICE_START_OUTCOMES,
    ROLE_SERVICE_STOP_OUTCOMES,
    ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED,
    ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED,
    RUNNER_CONTROL_MANAGED_CLI,
    RUNNER_CONTROL_UNKNOWN,
    AgentInstance,
    Member,
    Project,
    ProjectAgent,
    ProjectRole,
    ProjectRoleBinding,
    ProjectRoleServiceLaunchOut,
    ProjectRoleServiceOut,
    RoleServiceProjectionOut,
    RoleServiceLaunch,
    RoleServiceLaunchClaimOut,
    RoleServiceLaunchCommandOut,
    RoleServiceLaunchReportOut,
    RoleServiceStartAllCounts,
    RoleServiceStartAllMemberResult,
    RoleServiceStartAllOut,
    RoleServiceStartOut,
    RoleServiceState,
    RoleServiceStopOut,
    RunnerRegistry,
    hash_role_service_token,
    new_expected_instance_id,
    new_role_service_host_token,
    new_role_service_launch_id,
)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """库内 datetimes 是 UTC 的 naive 值；比较前统一补 tz（沿用 tasks.py 先例）。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fail(http_status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=http_status, detail=detail)


def _write_begin(session: Session) -> None:
    """取得真实 SQLite 写锁并清空 ORM identity map（同 R1-2 ``_begin_provision_write``）。"""
    begin_immediate_write(session)
    session.expire_all()


# ── 资格检查（严格身份/项目/角色/名册/归档/禁用）──────────────────────────


class ServiceRoleContext:
    """一次资格检查的结果（只读事实快照）。"""

    __slots__ = ("project", "role", "member", "binding", "runner", "control_kind")

    def __init__(self, project, role, member, binding, runner):
        self.project = project
        self.role = role
        self.member = member
        self.binding = binding
        self.runner = runner
        self.control_kind = (
            runner.control_kind if runner is not None else RUNNER_CONTROL_UNKNOWN
        )


def load_role_service_context(
    project_id: str, member_id: str, session: Session
) -> ServiceRoleContext:
    """严格资格检查（顺序固定，先命中先返回）。

    项目 → 角色行 → 归档 → 成员 → 禁用 → 名册。**不使用事务前缓存**：调用方在
    ``BEGIN IMMEDIATE`` + ``expire_all()`` 之后调用，读取落在真实写事务内。
    """
    project = session.get(Project, project_id)
    if project is None:
        raise _fail(status.HTTP_404_NOT_FOUND, ROLE_SERVICE_ERROR_PROJECT_NOT_FOUND)
    role = session.get(ProjectRole, (project_id, member_id))
    if role is None:
        raise _fail(status.HTTP_404_NOT_FOUND, ROLE_SERVICE_ERROR_ROLE_NOT_FOUND)
    if role.archived_at is not None:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ROLE_ARCHIVED)
    member = session.get(Member, member_id)
    if member is None or member.kind != "agent":
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ROLE_NOT_IN_ROSTER)
    if member.disabled_at is not None:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_MEMBER_DISABLED)
    if session.get(ProjectAgent, (project_id, member_id)) is None:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ROLE_NOT_IN_ROSTER)
    binding = session.get(ProjectRoleBinding, (project_id, member_id))
    runner = (
        session.get(RunnerRegistry, binding.runner_id)
        if binding is not None and binding.runner_id
        else None
    )
    return ServiceRoleContext(project, role, member, binding, runner)


def _require_managed_cli(ctx: ServiceRoleContext) -> None:
    """启动入口的能力门控：只有 ``managed_cli`` 的运行器才可能有宿主执行者。

    当前原生 Codex/Kimi/DSH/WorkBuddy 的受管能力**未真实验收**，生产登记保持
    ``unknown``，因此这里会如实拒绝，而不是建一个没有宿主领取的 launch 挂到超时。
    """
    if ctx.binding is None or not ctx.binding.runner_id:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ROLE_BINDING_MISSING)
    if ctx.runner is None:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ROLE_BINDING_MISSING)
    if ctx.control_kind != RUNNER_CONTROL_MANAGED_CLI:
        raise _fail(
            status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_CONTROL_KIND_NOT_MANAGED
        )


def _get_state(
    project_id: str, member_id: str, session: Session
) -> Optional[RoleServiceState]:
    return session.get(RoleServiceState, (project_id, member_id))


def _current_launch(
    state: Optional[RoleServiceState], session: Session
) -> Optional[RoleServiceLaunch]:
    if state is None or not state.current_launch_id:
        return None
    return session.get(RoleServiceLaunch, state.current_launch_id)


def ownership_held(state: Optional[RoleServiceState]) -> bool:
    """原 start 进程归属是否**仍未释放**（R1-3 返修 F2）。

    不变式：``process_launch_id`` 非空 ⟺ 宿主仍可能持有原活进程。该字段只在 start
    claim 时写入、只在“已证明停止”（stop 成功回报）或“纯预检失败（宿主明确未 spawn）”
    时清空。因此：

    - ``starting``/``running``/``stopping``：持有；
    - ``failed``/``unknown``（宿主 spawn 后失败、readiness_timeout、stop_timeout、
      停服失败、缺活句柄）：**仍然持有** —— 必须可由人类显式关闭，且**禁止**重试启动
      覆盖所有权（否则旧进程会变成无主进程）；
    - ``stopped``/``not_started`` 或无状态行：不持有。

    这里刻意只看 ``process_launch_id``，不看 ``pid``：PID 只是诊断提示，不能用来
    “重新认领”一个没有活句柄的进程（合同 §10.7）。
    """
    return state is not None and state.process_launch_id is not None


def _preallocate_instance_id(session: Session) -> str:
    """预分配一个**库里不存在**的全新实例 ID（合同 §4.1.6）。"""
    for _ in range(16):
        candidate = new_expected_instance_id()
        if session.get(AgentInstance, candidate) is not None:
            continue
        existing = session.exec(
            select(RoleServiceLaunch).where(
                RoleServiceLaunch.expected_instance_id == candidate
            )
        ).first()
        if existing is None:
            return candidate
    raise _fail(status.HTTP_409_CONFLICT, "expected_instance_id_allocation_failed")


# ── 共享 start 入队核心（R1-4c-a：人工 start 与配置成功后的自动首次启动复用）──


def _enqueue_start_launch(
    ctx: ServiceRoleContext,
    project_id: str,
    member_id: str,
    *,
    session: Session,
    now: datetime,
    actor_id: str,
    expected_generation: int,
) -> RoleServiceLaunch:
    """共享 start 入队核心：CAS 推进世代 + 新建 ``pending`` start launch。

    R1-4c-a 从 ``start_role_service`` 抽出，供人工启动与配置成功后的自动首次启动
    **复用同一份**真实 binding/control_kind/CAS/TTL 语义；不放宽任何守卫，也不写
    ``can_start``（它仍是投影计算结果）。

    事务边界由**调用方**负责：本核心**绝不** commit、rollback 或另开 BEGIN——
    人工入口回滚/提交整个写事务；自动入口只在嵌套 SAVEPOINT 内调用，由调用方决定
    回滚范围。失败抛 ``HTTPException``（世代冲突）或原始异常，均不上吞。
    ``expected_generation`` 必须由调用方在 ``expire_due_launches`` 之后按锁内
    事实传入；CAS 沿用 ``synchronize_session=False`` 的 Core update，调用方在
    保存点回滚后如需读取 state 必须重新 ``session.get()``。
    """
    old_generation = int(expected_generation)
    new_generation = old_generation + 1
    launch = RoleServiceLaunch(
        launch_id=new_role_service_launch_id(),
        project_id=project_id,
        member_id=member_id,
        action=ROLE_SERVICE_ACTION_START,
        generation=new_generation,
        state=ROLE_SERVICE_LAUNCH_PENDING,
        expected_instance_id=_preallocate_instance_id(session),
        launch_expires_at=now + timedelta(seconds=ROLE_SERVICE_LAUNCH_TTL_SECONDS),
        created_at=now,
        updated_at=now,
    )
    state = _get_state(project_id, member_id, session)
    if state is None:
        state = RoleServiceState(
            project_id=project_id,
            member_id=member_id,
            generation=0,
            updated_at=now,
        )
        session.add(state)
        session.flush()
    result = session.execute(
        update(RoleServiceState)
        .where(
            RoleServiceState.project_id == project_id,
            RoleServiceState.member_id == member_id,
            RoleServiceState.generation == old_generation,
        )
        .values(
            generation=new_generation,
            desired_state=ROLE_SERVICE_DESIRED_RUNNING,
            observed_state=ROLE_SERVICE_OBSERVED_STARTING,
            manager_kind=ROLE_SERVICE_MANAGER_CLI_PROCESS,
            control_kind=ctx.control_kind,
            current_launch_id=launch.launch_id,
            last_result=state.last_result,
            last_error_code=None,
            last_error_message=None,
            updated_at=now,
            updated_by=actor_id,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        # 调用方决定回滚范围：人工入口回滚整个写事务；自动入口回滚 SAVEPOINT。
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_GENERATION_CONFLICT)
    session.add(launch)
    # 必须实际 flush：launch INSERT 的错误（唯一索引/触发器/磁盘）要在此处暴露，
    # 让自动入口能在 SAVEPOINT 内回滚，而不是拖到外层的唯一提交点。
    session.flush()
    return launch


# ── 过期收敛 ─────────────────────────────────────────────────────────────


def expire_due_launches(
    session: Session,
    *,
    now: Optional[datetime] = None,
    project_id: Optional[str] = None,
    member_id: Optional[str] = None,
) -> int:
    """把到期且未回报的动作标 ``expired``，并**只在仍是当前动作时**收敛角色状态。

    - start：``observed_state='failed'``、``last_result='failed'``、
      ``last_error_code='readiness_timeout'``（**包括已回报 ready 但缺实例**，
      不能让 ``starting`` 永久悬挂）；
    - stop：``observed_state='unknown'``、``last_error_code='stop_timeout'``；
      **保留** ``process_launch_id``/``owner_host`` 等所有权记录，不重新认领、不杀进程；
    - 过期旧动作**不得**污染新世代（``current_launch_id``/``generation`` 不匹配时只标自己）。
    """
    now = now or _now()
    stmt = select(RoleServiceLaunch).where(
        RoleServiceLaunch.state.in_(
            (
                ROLE_SERVICE_LAUNCH_PENDING,
                ROLE_SERVICE_LAUNCH_CLAIMED,
                ROLE_SERVICE_LAUNCH_REPORTED,
            )
        ),
        RoleServiceLaunch.launch_expires_at < now,
    )
    if project_id is not None:
        stmt = stmt.where(RoleServiceLaunch.project_id == project_id)
    if member_id is not None:
        stmt = stmt.where(RoleServiceLaunch.member_id == member_id)
    expired = 0
    for launch in session.exec(stmt).all():
        state = _get_state(launch.project_id, launch.member_id, session)
        if launch.state == ROLE_SERVICE_LAUNCH_REPORTED:
            # 已回报的动作：只有“合法 ready 回报但缺实例证据”必须在截止后收敛为
            # readiness_timeout（不能 reported 让 starting 永久悬挂）；
            # 已就绪的 running 或已收敛的 stop/failed 回执**不得**被过期扫描改写。
            if state is not None and state.observed_state == ROLE_SERVICE_OBSERVED_RUNNING:
                continue
            if (
                launch.action != ROLE_SERVICE_ACTION_START
                or launch.outcome != ROLE_SERVICE_OUTCOME_READY
            ):
                continue
        launch.state = ROLE_SERVICE_LAUNCH_EXPIRED
        launch.updated_at = now
        expired += 1
        if (
            state is None
            or state.current_launch_id != launch.launch_id
            or state.generation != launch.generation
        ):
            continue
        if launch.action == ROLE_SERVICE_ACTION_START:
            state.observed_state = ROLE_SERVICE_OBSERVED_FAILED
            state.last_result = ROLE_SERVICE_RESULT_FAILED
            state.last_error_code = ROLE_SERVICE_ERROR_READINESS_TIMEOUT
            state.last_error_message = "service did not become ready before the deadline"
        else:
            state.observed_state = ROLE_SERVICE_OBSERVED_UNKNOWN
            state.last_error_code = ROLE_SERVICE_ERROR_STOP_TIMEOUT
            state.last_error_message = "stop was not proven before the deadline"
        state.updated_at = now
    return expired


# ── 就绪判定（四条件，合同 §10.3）───────────────────────────────────────


def _instance_is_fresh(instance: AgentInstance, now: datetime) -> bool:
    last_seen = _as_utc(instance.last_seen_at)
    if last_seen is None:
        return False
    return (now - last_seen).total_seconds() <= ROLE_SERVICE_INSTANCE_FRESH_SECONDS


def readiness_conditions_met(
    launch: RoleServiceLaunch,
    state: Optional[RoleServiceState],
    session: Session,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """``action='start'`` 的四条件就绪判定（只读，不写库）。

    明确**不**作为成功条件：模型版本正确、额度充足、任务能力可用、原生登录态有效。
    """
    now = now or _now()
    if launch.action != ROLE_SERVICE_ACTION_START:
        return False
    if launch.state != ROLE_SERVICE_LAUNCH_REPORTED:
        return False
    if launch.outcome != ROLE_SERVICE_OUTCOME_READY:
        return False
    reported_at = _as_utc(launch.reported_at)
    expires_at = _as_utc(launch.launch_expires_at)
    if reported_at is None or expires_at is None or reported_at > expires_at:
        return False
    instance = session.get(AgentInstance, launch.expected_instance_id)
    if instance is None:
        return False
    if instance.member_id != launch.member_id:
        return False
    if instance.project_id != launch.project_id:
        return False
    if instance.launch_id != launch.launch_id:
        return False
    if instance.status not in ("idle", "busy"):
        return False
    if not _instance_is_fresh(instance, now):
        return False
    if state is None:
        return False
    if state.generation != launch.generation:
        return False
    if state.current_launch_id != launch.launch_id:
        return False
    if state.desired_state != ROLE_SERVICE_DESIRED_RUNNING:
        return False
    claimed_at = _as_utc(launch.claimed_at)
    first_seen = _as_utc(launch.first_instance_seen_at)
    if claimed_at is None or first_seen is None or expires_at is None:
        return False
    return claimed_at <= first_seen <= expires_at


def _finalize_readiness_if_ready(
    launch: RoleServiceLaunch, state: RoleServiceState, session: Session, now: datetime
) -> bool:
    """四条件齐备时把角色收敛为 ``running``/``success``；否则保持 ``starting``。"""
    if not readiness_conditions_met(launch, state, session, now=now):
        return False
    state.observed_state = ROLE_SERVICE_OBSERVED_RUNNING
    state.last_result = ROLE_SERVICE_RESULT_SUCCESS
    state.last_error_code = None
    state.last_error_message = None
    state.observed_instance_id = launch.expected_instance_id
    state.started_at = now
    state.updated_at = now
    return True


def note_instance_launch_evidence(
    session: Session, instance: AgentInstance, *, now: Optional[datetime] = None
) -> bool:
    """记录“本次预分配实例”的首次证据并尝试收敛就绪（实例先到 / 报告先到都收敛）。

    由 ``PUT /api/instances/{id}`` 在**同一写事务内**调用。只有满足
    “该动作已 claim、实例 ID 正是本次预分配、心跳不早于 claim、且未过截止”时才记录
    ``first_instance_seen_at``；旧实例、错项目、旧心跳一律不产生就绪证据。
    """
    now = now or _now()
    if not instance.launch_id:
        return False
    launch = session.get(RoleServiceLaunch, instance.launch_id)
    if launch is None:
        return False
    if launch.action != ROLE_SERVICE_ACTION_START:
        return False
    # ``reported`` 也算合法：实例先到 / 报告先到都必须能收敛（合同 §10.3）。
    if launch.state not in (
        ROLE_SERVICE_LAUNCH_CLAIMED,
        ROLE_SERVICE_LAUNCH_REPORTED,
    ):
        return False
    if launch.expected_instance_id != instance.id:
        return False
    if launch.member_id != instance.member_id or launch.project_id != instance.project_id:
        return False
    claimed_at = _as_utc(launch.claimed_at)
    expires_at = _as_utc(launch.launch_expires_at)
    if claimed_at is None or expires_at is None:
        return False
    if now > expires_at:
        return False
    last_seen = _as_utc(instance.last_seen_at)
    if last_seen is None or last_seen < claimed_at:
        return False
    if _as_utc(launch.first_instance_seen_at) is None:
        launch.first_instance_seen_at = now
        launch.updated_at = now
    state = _get_state(launch.project_id, launch.member_id, session)
    if state is None:
        return False
    return _finalize_readiness_if_ready(launch, state, session, now)


# ── 启动 / 停止（human-only 意图写）─────────────────────────────────────


def start_role_service(
    project_id: str, member_id: str, operator: Member, session: Session
) -> RoleServiceStartOut:
    """请求启动单个角色（合同 §5.3）。

    CAS 递增 ``generation`` 并建 ``action='start'``、``state='pending'`` 的 launch，
    **服务端预分配**全新 ``expected_instance_id`` 与 ``launch_expires_at``；
    响应**不返回任何 token**。服务端不 spawn 任何进程。

    R1-4c-a：入队核心抽到 :func:`_enqueue_start_launch` 与配置成功后的自动首次
    启动复用；本包装继续负责原事务边界与 human 审计（``updated_by=operator.id``），
    行为/返回模型/错误码与 R1-3 逐字一致。
    """
    _write_begin(session)
    ctx = load_role_service_context(project_id, member_id, session)
    _require_managed_cli(ctx)
    now = _now()
    expire_due_launches(session, now=now, project_id=project_id, member_id=member_id)
    state = _get_state(project_id, member_id, session)
    if state is not None and state.observed_state in (
        ROLE_SERVICE_OBSERVED_STARTING,
        ROLE_SERVICE_OBSERVED_RUNNING,
    ):
        if state.desired_state == ROLE_SERVICE_DESIRED_RUNNING:
            raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ALREADY_RUNNING)
    # R1-3 返修 F2：原 start 的进程归属未释放（失败/过期/unknown/stopping，或宿主已
    # spawn 但未就绪）时**禁止**用新 start 覆盖它。否则 ``process_launch_id`` 会被新
    # 动作改写，旧活进程失去归属记录，成为无法管理的服务。人类必须先显式 stop。
    if ownership_held(state):
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ALREADY_RUNNING)

    old_generation = int(state.generation) if state is not None else 0
    try:
        launch = _enqueue_start_launch(
            ctx,
            project_id,
            member_id,
            session=session,
            now=now,
            actor_id=operator.id,
            expected_generation=old_generation,
        )
    except HTTPException:
        session.rollback()
        raise
    session.commit()
    return RoleServiceStartOut(
        project_id=project_id,
        member_id=member_id,
        role_name=ctx.role.role_name,
        launch_id=launch.launch_id,
        generation=int(launch.generation),
        expected_instance_id=launch.expected_instance_id,
        launch_expires_at=_as_utc(launch.launch_expires_at),
    )


def _idempotent_stopped(
    project_id: str,
    member_id: str,
    role_name: Optional[str],
    state: Optional[RoleServiceState],
    session: Session,
    now: datetime,
    operator: Member,
) -> RoleServiceStopOut:
    """没有受管进程且可证明已停时的幂等返回（合同 §10.2）。

    同时使任何**未领取**的 start 动作失效（把 ``generation`` 推进）——否则一个先前的
    pending start 还能被宿主 claim 并 spawn 出无人拥有的进程。
    """
    current = _current_launch(state, session)
    if current is not None and current.action == ROLE_SERVICE_ACTION_START:
        if current.state in (ROLE_SERVICE_LAUNCH_PENDING, ROLE_SERVICE_LAUNCH_CLAIMED):
            current.state = ROLE_SERVICE_LAUNCH_EXPIRED
            current.error_code = ROLE_SERVICE_ERROR_UNKNOWN_OWNER
            current.updated_at = now
    target = state
    if target is None:
        target = RoleServiceState(project_id=project_id, member_id=member_id)
        session.add(target)
        session.flush()
    target.generation = (target.generation or 0) + 1
    target.desired_state = ROLE_SERVICE_DESIRED_STOPPED
    target.observed_state = ROLE_SERVICE_OBSERVED_STOPPED
    target.last_result = ROLE_SERVICE_RESULT_STOPPED
    target.last_error_code = None
    target.last_error_message = None
    target.current_launch_id = None
    target.process_launch_id = None
    target.owner_host = None
    target.spawned = False
    target.pid = None
    target.process_started_at = None
    target.updated_at = now
    target.updated_by = operator.id
    session.commit()
    return RoleServiceStopOut(
        project_id=project_id,
        member_id=member_id,
        role_name=role_name,
        launch_id=None,
        generation=target.generation,
        expected_instance_id=None,
        launch_expires_at=None,
        idempotent_stopped=True,
    )


def stop_role_service(
    project_id: str, member_id: str, operator: Member, session: Session
) -> RoleServiceStopOut:
    """请求关闭单个角色（合同 §5.3）。

    - 沿用**原 start** 的 ``process_launch_id``、``owner_host`` 与实例 ID；
      stop 动作**不能**拿自己的新 token 认领旧进程；
    - 无进程且有已停证明 → 幂等 ``stopped``（**不记失败**）；
    - 所有权未知 → ``409 unknown_owner``，不伪造 \'\'none_\'\' 占位实例；
    - 停止入口**不**受 ``control_kind`` 限制（已受管进程必须始终可停）。
    """
    _write_begin(session)
    ctx = load_role_service_context(project_id, member_id, session)
    now = _now()
    expire_due_launches(session, now=now, project_id=project_id, member_id=member_id)
    state = _get_state(project_id, member_id, session)

    if state is None or state.process_launch_id is None:
        observed = state.observed_state if state is not None else None
        if observed == ROLE_SERVICE_OBSERVED_UNKNOWN:
            raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)
        if observed in (
            ROLE_SERVICE_OBSERVED_STARTING,
            ROLE_SERVICE_OBSERVED_RUNNING,
        ):
            # starting 且尚无 owner：只有“从未被 claim 的 start 动作”才可安全失效；
            # 一旦 claim 过，process_launch_id 必然非空。
            current = _current_launch(state, session)
            if current is None or current.action != ROLE_SERVICE_ACTION_START:
                raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)
            if current.state not in (
                ROLE_SERVICE_LAUNCH_PENDING,
                ROLE_SERVICE_LAUNCH_CLAIMED,
            ):
                raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)
        return _idempotent_stopped(
            project_id, member_id, ctx.role.role_name, state, session, now, operator
        )

    if state.desired_state == ROLE_SERVICE_DESIRED_STOPPED and state.observed_state in (
        ROLE_SERVICE_OBSERVED_STOPPING,
    ):
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ALREADY_STOPPED)
    if state.observed_state == ROLE_SERVICE_OBSERVED_STOPPED:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_ALREADY_STOPPED)

    start_launch = session.get(RoleServiceLaunch, state.process_launch_id)
    if (
        start_launch is None
        or start_launch.action != ROLE_SERVICE_ACTION_START
        or start_launch.project_id != project_id
        or start_launch.member_id != member_id
    ):
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)

    old_generation = state.generation or 0
    new_generation = old_generation + 1
    launch = RoleServiceLaunch(
        launch_id=new_role_service_launch_id(),
        project_id=project_id,
        member_id=member_id,
        action=ROLE_SERVICE_ACTION_STOP,
        generation=new_generation,
        state=ROLE_SERVICE_LAUNCH_PENDING,
        expected_instance_id=start_launch.expected_instance_id,
        target_start_launch_id=start_launch.launch_id,
        launch_expires_at=now + timedelta(seconds=ROLE_SERVICE_LAUNCH_TTL_SECONDS),
        created_at=now,
        updated_at=now,
    )
    result = session.execute(
        update(RoleServiceState)
        .where(
            RoleServiceState.project_id == project_id,
            RoleServiceState.member_id == member_id,
            RoleServiceState.generation == old_generation,
        )
        .values(
            generation=new_generation,
            desired_state=ROLE_SERVICE_DESIRED_STOPPED,
            observed_state=ROLE_SERVICE_OBSERVED_STOPPING,
            current_launch_id=launch.launch_id,
            last_error_code=None,
            last_error_message=None,
            updated_at=now,
            updated_by=operator.id,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_GENERATION_CONFLICT)
    session.add(launch)
    session.commit()
    return RoleServiceStopOut(
        project_id=project_id,
        member_id=member_id,
        role_name=ctx.role.role_name,
        launch_id=launch.launch_id,
        generation=new_generation,
        expected_instance_id=launch.expected_instance_id,
        launch_expires_at=_as_utc(launch.launch_expires_at),
        observed=ROLE_SERVICE_OBSERVED_STOPPING,
    )


# ── 自动首次启动入队（R1-4c-a，配置成功后的同事实入口）────────────────────

#: ``enqueue_auto_start_launch`` 把共享核心的稳定拒绝码翻译成自动启动分类码：
#: ``_require_managed_cli`` 的两种拒绝（绑定/运行器缺失、control_kind 非
#: ``managed_cli``）如实归为 ``auto_start_control_kind_not_managed``；
#: 其余意外（资格/上下文/世代冲突等）统一如实归为 ``auto_start_enqueue_failed``。
_AUTO_START_CODE_BY_SERVICE_ERROR = {
    ROLE_SERVICE_ERROR_CONTROL_KIND_NOT_MANAGED: (
        ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED
    ),
    ROLE_SERVICE_ERROR_ROLE_BINDING_MISSING: (
        ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED
    ),
}


def enqueue_auto_start_launch(
    project_id: str,
    member_id: str,
    *,
    session: Session,
    now: datetime,
) -> tuple[Optional[str], Optional[str]]:
    """配置成功后的自动首次启动入队（AUTO_START_DESIGN §3/§6）。

    由 ``report_request(provisioned)`` 在**嵌套 SAVEPOINT 内**调用，复用与人工
    ``start_role_service`` 完全相同的共享核心：真实 binding/control_kind 守卫、
    过期收敛、ownership/运行中防御、世代 CAS 与 120 秒 launch TTL，一个守卫都
    不放宽，也不伪造 ready。

    返回 ``(launch_id, error_code)``：成功 ``(launch_id, None)``；守卫拒绝
    ``(None, 稳定码)``。本函数**绝不** commit、rollback 或另开 BEGIN，也绝不把
    ``HTTPException`` 抛给 report 外层；可恢复的写入异常（flush/INSERT 失败）
    原样上抛，由调用方回滚保存点后登记 ``auto_start_enqueue_failed``。自动动作
    的审计身份是 ``system:auto-start``（不冒充 human，不新增权限入口）。
    """
    try:
        ctx = load_role_service_context(project_id, member_id, session)
        _require_managed_cli(ctx)
        expire_due_launches(session, now=now, project_id=project_id, member_id=member_id)
        state = _get_state(project_id, member_id, session)
        # 人工意图优先的防御兜底：所有权未释放或已运行中早被调用方守卫覆盖，
        # 此处仍如实拒绝，不产生第二个世代。
        if ownership_held(state) or (
            state is not None
            and state.observed_state
            in (ROLE_SERVICE_OBSERVED_STARTING, ROLE_SERVICE_OBSERVED_RUNNING)
            and state.desired_state == ROLE_SERVICE_DESIRED_RUNNING
        ):
            return None, ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED
        launch = _enqueue_start_launch(
            ctx,
            project_id,
            member_id,
            session=session,
            now=now,
            actor_id=ROLE_AUTO_START_ACTOR,
            expected_generation=int(state.generation) if state is not None else 0,
        )
        return launch.launch_id, None
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else ""
        return None, _AUTO_START_CODE_BY_SERVICE_ERROR.get(
            detail, ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED
        )


# ── claim / report（宿主协议）────────────────────────────────────────────


def _require_launch_participant(
    launch: RoleServiceLaunch, caller: Member
) -> None:
    """claim/report 的身份边界：目标角色的 agent，或合法 human 宿主。

    该角色的 agent 只能领取/回报**属于自己**的动作；agent 永远不能修改
    ``desired_state``（本模块没有任何 agent 可调用的意图写入口）。
    """
    if caller.kind == "agent" and caller.id != launch.member_id:
        raise _fail(status.HTTP_403_FORBIDDEN, ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED)
    if caller.kind not in ("agent", "human"):
        raise _fail(status.HTTP_403_FORBIDDEN, ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED)


def claim_role_service_launch(
    launch_id: str,
    *,
    host: str,
    expected_instance_id: str,
    owner_token: Optional[str],
    caller: Member,
    session: Session,
) -> RoleServiceLaunchClaimOut:
    """宿主领取动作（合同 §5.3/§10.2）。

    - start：生成 ``owner_token`` + ``claim_token``，固定 ``process_launch_id``/``owner_host``；
    - stop：必须提交**原 start** 的 owner token 且 host 等于原 ``claim_host``，
      只新发 ``claim_token``，绝不重新发行原进程所有权；
    - CAS 只允许 ``pending``→``claimed`` 且未过期。
    """
    _write_begin(session)
    launch = session.get(RoleServiceLaunch, launch_id)
    if launch is None:
        raise _fail(status.HTTP_404_NOT_FOUND, ROLE_SERVICE_ERROR_LAUNCH_NOT_FOUND)
    ctx = load_role_service_context(launch.project_id, launch.member_id, session)
    _require_launch_participant(launch, caller)
    now = _now()
    expires_at = _as_utc(launch.launch_expires_at)
    if launch.state == ROLE_SERVICE_LAUNCH_EXPIRED or (
        expires_at is not None and now > expires_at
    ):
        expire_due_launches(
            session,
            now=now,
            project_id=launch.project_id,
            member_id=launch.member_id,
        )
        session.commit()
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_LAUNCH_EXPIRED)
    if launch.state != ROLE_SERVICE_LAUNCH_PENDING:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING)
    state = _get_state(launch.project_id, launch.member_id, session)
    if (
        state is None
        or state.current_launch_id != launch.launch_id
        or state.generation != launch.generation
    ):
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_STALE_REPORT)
    if expected_instance_id != launch.expected_instance_id:
        raise _fail(
            status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH
        )
    host = (host or "").strip()
    if not host:
        raise _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "host_invalid")

    owner_token_out: Optional[str] = None
    if launch.action == ROLE_SERVICE_ACTION_START:
        owner_token_out = new_role_service_host_token()
        claim_token = new_role_service_host_token()
        launch.owner_token_hash = hash_role_service_token(owner_token_out)
        launch.claim_token_hash = hash_role_service_token(claim_token)
        state.process_launch_id = launch.launch_id
        state.owner_host = host
        state.manager_kind = ROLE_SERVICE_MANAGER_CLI_PROCESS
        state.control_kind = ctx.control_kind
        state.updated_at = now
    else:
        target = (
            session.get(RoleServiceLaunch, launch.target_start_launch_id)
            if launch.target_start_launch_id
            else None
        )
        if target is None or target.owner_token_hash is None:
            raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)
        if target.claim_host is None or target.claim_host != host:
            raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)
        if not owner_token or not hmac.compare_digest(
            hash_role_service_token(owner_token), target.owner_token_hash
        ):
            raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)
        claim_token = new_role_service_host_token()
        launch.claim_token_hash = hash_role_service_token(claim_token)

    launch.claim_member_id = caller.id
    launch.claim_host = host
    launch.claimed_at = now
    launch.state = ROLE_SERVICE_LAUNCH_CLAIMED
    launch.updated_at = now
    session.commit()

    binding = ctx.binding
    return RoleServiceLaunchClaimOut(
        launch_id=launch.launch_id,
        project_id=launch.project_id,
        member_id=launch.member_id,
        action=launch.action,
        generation=launch.generation,
        expected_instance_id=launch.expected_instance_id,
        state=launch.state,
        claimed_at=now,
        launch_expires_at=_as_utc(launch.launch_expires_at),
        claim_host=host,
        owner_token=owner_token_out,
        claim_token=claim_token,
        command=RoleServiceLaunchCommandOut(
            action=launch.action,
            runtime=ctx.runner.runtime if ctx.runner is not None else None,
            runner_id=binding.runner_id if binding is not None else None,
            model_alias=binding.model_alias if binding is not None else None,
            project_root=ctx.project.project_root_path,
            member_id=launch.member_id,
            project_id=launch.project_id,
        ),
    )


def _report_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _receipt(
    launch: RoleServiceLaunch,
    state: Optional[RoleServiceState],
    *,
    replayed: bool,
) -> RoleServiceLaunchReportOut:
    return RoleServiceLaunchReportOut(
        launch_id=launch.launch_id,
        project_id=launch.project_id,
        member_id=launch.member_id,
        action=launch.action,
        generation=launch.generation,
        state=launch.state,
        outcome=launch.outcome,
        instance_id=launch.instance_id,
        error_code=launch.error_code,
        reported_at=_as_utc(launch.reported_at),
        observed_state=state.observed_state if state is not None else None,
        replayed=replayed,
    )


def report_role_service_launch(
    launch_id: str,
    *,
    generation: int,
    action: str,
    claim_token: str,
    owner_token: Optional[str],
    outcome: str,
    instance_id: Optional[str],
    pid: Optional[int],
    process_started_at: Optional[datetime],
    host: str,
    error_code: Optional[str],
    caller: Member,
    session: Session,
    spawned: Optional[bool] = None,
) -> RoleServiceLaunchReportOut:
    """宿主回报观测结果（合同 §5.3/§10.5）。

    校验顺序固定：launch 存在 → 资格 → 领取身份 → host → claim token → owner token
    → action → generation → 载荷指纹（同载荷只读重放）→ 过期/未领取 → 当前世代 →
    时间窗 → 落库收敛。任何不合法的回报都**不**改当前状态。
    """
    _write_begin(session)
    launch = session.get(RoleServiceLaunch, launch_id)
    if launch is None:
        raise _fail(status.HTTP_404_NOT_FOUND, ROLE_SERVICE_ERROR_LAUNCH_NOT_FOUND)
    ctx = load_role_service_context(launch.project_id, launch.member_id, session)
    _require_launch_participant(launch, caller)
    now = _now()

    host = (host or "").strip()
    if launch.claim_member_id is None or launch.claim_member_id != caller.id:
        raise _fail(status.HTTP_403_FORBIDDEN, ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED)
    if not host or launch.claim_host != host:
        raise _fail(status.HTTP_403_FORBIDDEN, ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED)
    if not claim_token or launch.claim_token_hash is None or not hmac.compare_digest(
        hash_role_service_token(claim_token), launch.claim_token_hash
    ):
        raise _fail(status.HTTP_403_FORBIDDEN, ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED)

    if launch.action == ROLE_SERVICE_ACTION_START:
        owner_hash = launch.owner_token_hash
    else:
        target = (
            session.get(RoleServiceLaunch, launch.target_start_launch_id)
            if launch.target_start_launch_id
            else None
        )
        if target is None:
            raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)
        owner_hash = target.owner_token_hash
    if owner_hash is None or not owner_token or not hmac.compare_digest(
        hash_role_service_token(owner_token), owner_hash
    ):
        raise _fail(status.HTTP_403_FORBIDDEN, ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED)

    if action != launch.action:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_LAUNCH_ACTION_MISMATCH)
    if launch.action == ROLE_SERVICE_ACTION_START:
        allowed_outcomes = ROLE_SERVICE_START_OUTCOMES
    else:
        allowed_outcomes = ROLE_SERVICE_STOP_OUTCOMES
    if outcome not in allowed_outcomes:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_LAUNCH_ACTION_MISMATCH)
    if generation != launch.generation:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_STALE_REPORT)
    if (
        launch.action == ROLE_SERVICE_ACTION_START
        and instance_id is not None
        and instance_id != launch.expected_instance_id
    ):
        raise _fail(
            status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH
        )

    fingerprint = _report_fingerprint(
        {
            "generation": generation,
            "action": action,
            "outcome": outcome,
            "instance_id": instance_id,
            "pid": pid,
            "process_started_at": _as_utc(process_started_at).isoformat()
            if process_started_at is not None
            else None,
            "host": host,
            "error_code": error_code,
            "spawned": spawned,
        }
    )

    state = _get_state(launch.project_id, launch.member_id, session)
    if launch.state == ROLE_SERVICE_LAUNCH_REPORTED:
        # 相同完整载荷重放：先核原身份/token（已在上方完成），再**只读**返回 receipt；
        # 即使截止后也不改当前状态。
        if launch.report_fingerprint == fingerprint:
            return _receipt(launch, state, replayed=True)
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_REPORT_CONFLICT)
    # 已被新动作取代（世代/当前动作不匹配）的旧动作：首次迟到一律 ``stale_report``，
    # 只写审计，绝不覆盖新世代。
    if (
        state is None
        or state.current_launch_id != launch.launch_id
        or state.generation != launch.generation
    ):
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_STALE_REPORT)
    expires_at = _as_utc(launch.launch_expires_at)
    if launch.state == ROLE_SERVICE_LAUNCH_EXPIRED or (
        expires_at is not None and now > expires_at
    ):
        expire_due_launches(
            session,
            now=now,
            project_id=launch.project_id,
            member_id=launch.member_id,
        )
        session.commit()
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_LAUNCH_EXPIRED)
    if launch.state != ROLE_SERVICE_LAUNCH_CLAIMED:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING)

    claimed_at = _as_utc(launch.claimed_at)
    if claimed_at is None or now < claimed_at:
        raise _fail(status.HTTP_409_CONFLICT, ROLE_SERVICE_ERROR_STALE_REPORT)

    launch.state = ROLE_SERVICE_LAUNCH_REPORTED
    launch.outcome = outcome
    launch.error_code = error_code
    launch.reported_at = now
    launch.report_fingerprint = fingerprint
    launch.updated_at = now

    if launch.action == ROLE_SERVICE_ACTION_START:
        if outcome == ROLE_SERVICE_OUTCOME_READY:
            launch.instance_id = launch.expected_instance_id
            if pid is not None:
                state.pid = pid
            if process_started_at is not None:
                state.process_started_at = process_started_at
            state.spawned = True
            state.updated_at = now
            _finalize_readiness_if_ready(launch, state, session, now)
        else:
            state.observed_state = ROLE_SERVICE_OBSERVED_FAILED
            state.last_result = ROLE_SERVICE_RESULT_FAILED
            state.last_error_code = error_code
            state.last_error_message = "service reported failure"
            # R1-3 返修 F2：失败**不**等于可以重试。只有宿主明确“没有 spawn 过”
            # （纯预检/凭据/入口失败）时才释放原所有权；已 spawn 的失败（就绪超时、
            # 落盘异常、上报异常）必须保留 ``process_launch_id``/pid，让人类先 stop。
            # 旧宿主不传 ``spawned`` 时保守回退：带 pid 即视为已 spawn。
            did_spawn = spawned if spawned is not None else (pid is not None)
            state.spawned = bool(did_spawn)
            if did_spawn:
                if pid is not None:
                    state.pid = pid
                if process_started_at is not None:
                    state.process_started_at = process_started_at
            else:
                state.process_launch_id = None
                state.owner_host = None
                state.pid = None
                state.process_started_at = None
            state.updated_at = now
    else:
        if outcome == ROLE_SERVICE_OUTCOME_STOPPED:
            state.observed_state = ROLE_SERVICE_OBSERVED_STOPPED
            state.last_result = ROLE_SERVICE_RESULT_STOPPED
            state.last_error_code = None
            state.last_error_message = None
            state.stopped_at = now
            state.current_launch_id = None
            state.process_launch_id = None
            state.owner_host = None
            state.spawned = False
            state.observed_instance_id = None
            state.pid = None
            state.process_started_at = None
            state.updated_at = now
        else:
            state.last_result = ROLE_SERVICE_RESULT_FAILED
            state.last_error_code = error_code
            state.last_error_message = "stop was not completed"
            live = (
                error_code != ROLE_SERVICE_ERROR_UNKNOWN_OWNER
                and pid is not None
                and state.pid is not None
                and state.pid == pid
            )
            state.observed_state = (
                ROLE_SERVICE_OBSERVED_RUNNING if live else ROLE_SERVICE_OBSERVED_UNKNOWN
            )
            # 所有权记录**保留**：进程可能仍存活，不得丢失或遗留无主受控进程。
            state.updated_at = now
    session.commit()
    state = _get_state(launch.project_id, launch.member_id, session)
    return _receipt(launch, state, replayed=False)


# ── 只读投影（页面 / 公共 GET）──────────────────────────────────────────


def running_instance_problem(
    state: RoleServiceState,
    launch: Optional[RoleServiceLaunch],
    session: Session,
    now: datetime,
) -> Optional[str]:
    """运行期只认本次启动实例的近期心跳；失联不等于进程已停止。"""
    if (
        launch is None
        or launch.action != ROLE_SERVICE_ACTION_START
        or launch.project_id != state.project_id
        or launch.member_id != state.member_id
        or launch.generation != state.generation
        or launch.launch_id != state.process_launch_id
        or launch.expected_instance_id != state.observed_instance_id
    ):
        return ROLE_SERVICE_ERROR_INSTANCE_IDENTITY_MISMATCH
    instance = session.get(AgentInstance, state.observed_instance_id)
    if instance is None:
        return ROLE_SERVICE_ERROR_INSTANCE_UNAVAILABLE
    if (
        instance.member_id != state.member_id
        or instance.project_id != state.project_id
        or instance.launch_id != state.process_launch_id
    ):
        return ROLE_SERVICE_ERROR_INSTANCE_IDENTITY_MISMATCH
    if instance.status not in ("idle", "busy"):
        return ROLE_SERVICE_ERROR_INSTANCE_UNAVAILABLE
    if not _instance_is_fresh(instance, now):
        return ROLE_SERVICE_ERROR_INSTANCE_HEARTBEAT_EXPIRED
    return None


def build_service_projection(
    *,
    project_id: str,
    member_id: str,
    role_name: Optional[str],
    archived: bool,
    archived_missing: bool,
    session: Session,
    control_kind: Optional[str] = None,
    model_alias_configured: bool = False,
    binding_ready: bool = False,
    state: Optional[RoleServiceState] = None,
    now: Optional[datetime] = None,
) -> ProjectRoleServiceOut:
    """把状态/动作/资格事实投影成**公开**结构（不含任何 token/argv/绝对路径）。"""
    now = now or _now()
    if state is None:
        state = _get_state(project_id, member_id, session)
    launch = _current_launch(state, session)
    effective_control = control_kind
    if effective_control is None:
        effective_control = state.control_kind if state is not None else RUNNER_CONTROL_UNKNOWN

    desired = state.desired_state if state is not None else ROLE_SERVICE_DESIRED_STOPPED
    observed = (
        state.observed_state if state is not None else ROLE_SERVICE_OBSERVED_NOT_STARTED
    )
    stored_observed = observed
    generation = state.generation if state is not None else 0
    error_code = state.last_error_code if state is not None else None
    error_message = state.last_error_message if state is not None else None
    if observed == ROLE_SERVICE_OBSERVED_RUNNING and state is not None:
        problem = running_instance_problem(state, launch, session, now)
        if problem is not None:
            # 仅降级本次公开投影；原 ready 回执、世代和所有权全部保持。
            observed = ROLE_SERVICE_OBSERVED_UNKNOWN
            error_code = problem
            error_message = {
                ROLE_SERVICE_ERROR_INSTANCE_HEARTBEAT_EXPIRED: "未收到近期运行心跳，服务运行状态待核实。",
                ROLE_SERVICE_ERROR_INSTANCE_UNAVAILABLE: "当前执行实例不可用，服务运行状态待核实。",
                ROLE_SERVICE_ERROR_INSTANCE_IDENTITY_MISMATCH: "当前实例与本次启动信息不匹配，服务运行状态待核实。",
            }[problem]

    if observed == ROLE_SERVICE_OBSERVED_RUNNING and (
        state is not None and state.last_result == ROLE_SERVICE_RESULT_SUCCESS
    ):
        readiness = ROLE_SERVICE_READINESS_READY
    elif observed == ROLE_SERVICE_OBSERVED_FAILED:
        readiness = ROLE_SERVICE_READINESS_FAILED
    elif observed == ROLE_SERVICE_OBSERVED_UNKNOWN:
        readiness = ROLE_SERVICE_READINESS_UNKNOWN
    else:
        readiness = ROLE_SERVICE_READINESS_PENDING

    if model_alias_configured:
        alias_state = ROLE_SERVICE_MODEL_ALIAS_RESOLVED
    elif binding_ready:
        alias_state = ROLE_SERVICE_MODEL_ALIAS_UNRESOLVED
    else:
        alias_state = ROLE_SERVICE_MODEL_ALIAS_UNCONFIGURED

    can_start = (
        not archived
        and not archived_missing
        and binding_ready
        and effective_control == RUNNER_CONTROL_MANAGED_CLI
        and stored_observed
        not in (ROLE_SERVICE_OBSERVED_STARTING, ROLE_SERVICE_OBSERVED_RUNNING)
        and not ownership_held(state)
    )
    can_stop = (
        not archived
        and not archived_missing
        and (
            stored_observed
            in (ROLE_SERVICE_OBSERVED_STARTING, ROLE_SERVICE_OBSERVED_RUNNING)
            or ownership_held(state)
        )
    )

    current_launch = None
    if launch is not None:
        current_launch = ProjectRoleServiceLaunchOut(
            launch_id=launch.launch_id,
            action=launch.action,
            state=launch.state,
            expected_instance_id=launch.expected_instance_id,
            launch_expires_at=_as_utc(launch.launch_expires_at),
            claimed_at=_as_utc(launch.claimed_at),
            reported_at=_as_utc(launch.reported_at),
            outcome=launch.outcome,
            error_code=launch.error_code,
        )

    return ProjectRoleServiceOut(
        desired=desired,
        observed=observed,
        last_action=launch.action if launch is not None else None,
        last_result=state.last_result if state is not None else None,
        error_code=error_code,
        error_message=error_message,
        control_kind=effective_control,
        manager_kind=(
            state.manager_kind
            if state is not None
            else ROLE_SERVICE_MANAGER_CLI_PROCESS
        ),
        generation=generation,
        current_launch=current_launch,
        observed_instance_id=(
            state.observed_instance_id if state is not None else None
        ),
        native_login=ROLE_SERVICE_NATIVE_LOGIN_UNVERIFIED,
        model_alias=alias_state,
        readiness_service=readiness,
        can_start=can_start,
        can_stop=can_stop,
        ownership_held=ownership_held(state),
        started_at=_as_utc(state.started_at) if state is not None else None,
        stopped_at=_as_utc(state.stopped_at) if state is not None else None,
        updated_at=_as_utc(state.updated_at) if state is not None else None,
    )


def project_role_service(
    project_id: str,
    member_id: str,
    session: Session,
    *,
    now: Optional[datetime] = None,
) -> ProjectRoleServiceOut:
    """单角色服务投影：自己读取角色/绑定/运行器事实（供角色列表调用）。"""
    now = now or _now()
    role = session.get(ProjectRole, (project_id, member_id))
    member = session.get(Member, member_id)
    binding = session.get(ProjectRoleBinding, (project_id, member_id))
    runner = (
        session.get(RunnerRegistry, binding.runner_id)
        if binding is not None and binding.runner_id
        else None
    )
    in_roster = session.get(ProjectAgent, (project_id, member_id)) is not None
    archived = role is not None and role.archived_at is not None
    archived_missing = role is None
    binding_ready = (
        binding is not None
        and runner is not None
        and in_roster
        and member is not None
        and member.kind == "agent"
        and member.disabled_at is None
    )
    return build_service_projection(
        project_id=project_id,
        member_id=member_id,
        role_name=role.role_name if role is not None else None,
        archived=archived,
        archived_missing=archived_missing,
        session=session,
        control_kind=runner.control_kind if runner is not None else RUNNER_CONTROL_UNKNOWN,
        model_alias_configured=bool(binding is not None and binding.model_alias),
        binding_ready=binding_ready,
        now=now,
    )


def list_role_services(
    project_id: str, session: Session, *, now: Optional[datetime] = None
) -> list[RoleServiceProjectionOut]:
    """``GET /api/projects/{project_id}/role-services`` 的只读投影（页面轮询用）。"""
    now = now or _now()
    role_rows = session.exec(
        select(ProjectRole).where(ProjectRole.project_id == project_id)
    ).all()
    roster_ids = {
        row.member_id
        for row in session.exec(
            select(ProjectAgent).where(ProjectAgent.project_id == project_id)
        ).all()
    }
    role_ids = {row.member_id for row in role_rows}
    member_ids = sorted(role_ids | roster_ids)
    out: list[RoleServiceProjectionOut] = []
    for member_id in member_ids:
        service = project_role_service(project_id, member_id, session, now=now)
        role = session.get(ProjectRole, (project_id, member_id))
        out.append(
            RoleServiceProjectionOut(
                **service.model_dump(),
                member_id=member_id,
                role_name=role.role_name if role is not None else None,
                archived=bool(role is not None and role.archived_at is not None),
            )
        )
    return out


# ── 全部启动（逐角色结果，部分失败不回滚）──────────────────────────────


def start_all_role_services(
    project_id: str,
    member_ids: Optional[list[str]],
    operator: Member,
    session: Session,
) -> RoleServiceStartAllOut:
    """项目“全部启动”：跳过 ``running/starting``，返回逐角色结果（合同 §10.9）。

    - ``member_ids`` 只用于“只重试失败子集”；出现跨项目或不存在 ID 时稳定拒绝
      （``404 role_not_found``），不静默忽略；
    - 单个角色失败**不**回滚其它角色；失败清单可定向重试；
    - 不重复 spawn：已在 ``running/starting`` 的角色一律跳过。
    """
    if session.get(Project, project_id) is None:
        raise _fail(status.HTTP_404_NOT_FOUND, ROLE_SERVICE_ERROR_PROJECT_NOT_FOUND)
    role_rows = session.exec(
        select(ProjectRole).where(ProjectRole.project_id == project_id)
    ).all()
    by_member = {row.member_id: row for row in role_rows}
    candidates = sorted(by_member)
    if member_ids is not None:
        requested: list[str] = []
        for raw in member_ids:
            member_id = str(raw).strip()
            if not member_id or member_id not in by_member:
                raise _fail(
                    status.HTTP_404_NOT_FOUND, ROLE_SERVICE_ERROR_ROLE_NOT_FOUND
                )
            if member_id not in requested:
                requested.append(member_id)
        candidates = requested
    else:
        requested = list(candidates)

    results: list[RoleServiceStartAllMemberResult] = []
    for member_id in candidates:
        role = by_member[member_id]
        state = _get_state(project_id, member_id, session)
        if state is not None and state.observed_state in (
            ROLE_SERVICE_OBSERVED_STARTING,
            ROLE_SERVICE_OBSERVED_RUNNING,
        ):
            results.append(
                RoleServiceStartAllMemberResult(
                    member_id=member_id,
                    role_name=role.role_name,
                    status="skipped_running",
                    generation=state.generation,
                )
            )
            continue
        # R1-3 返修 F2：失败/过期/unknown 且**仍持有原进程归属**的角色不能重复启动
        # （否则旧活进程失去归属记录）。必须由人类先显式关闭，再重试。
        if ownership_held(state):
            results.append(
                RoleServiceStartAllMemberResult(
                    member_id=member_id,
                    role_name=role.role_name,
                    status="skipped_ownership_held",
                    generation=state.generation,
                    error_code=ROLE_SERVICE_ERROR_ALREADY_RUNNING,
                )
            )
            continue
        try:
            started = start_role_service(project_id, member_id, operator, session)
        except HTTPException as exc:
            session.rollback()
            results.append(
                RoleServiceStartAllMemberResult(
                    member_id=member_id,
                    role_name=role.role_name,
                    status="failed",
                    error_code=str(exc.detail),
                )
            )
            continue
        # F2/F6：写入意图**不**等于启动成功。只有本次动作对应的世代已经**实际收敛为
        # running + success** 才记 ``ready``；否则如实记 ``requested``（宿主尚未执行完）。
        after = _get_state(project_id, member_id, session)
        converged = bool(
            after is not None
            and after.current_launch_id == started.launch_id
            and after.generation == started.generation
            and after.observed_state == ROLE_SERVICE_OBSERVED_RUNNING
            and after.last_result == ROLE_SERVICE_RESULT_SUCCESS
        )
        results.append(
            RoleServiceStartAllMemberResult(
                member_id=member_id,
                role_name=role.role_name,
                status="ready" if converged else "requested",
                launch_id=started.launch_id,
                generation=started.generation,
                expected_instance_id=started.expected_instance_id,
            )
        )

    return RoleServiceStartAllOut(
        project_id=project_id,
        requested=requested,
        results=results,
        counts=RoleServiceStartAllCounts(
            started=sum(1 for row in results if row.status == "ready"),
            requested=sum(1 for row in results if row.status == "requested"),
            skipped=sum(
                1
                for row in results
                if row.status in ("skipped_running", "skipped_ownership_held")
            ),
            failed=sum(1 for row in results if row.status == "failed"),
        ),
    )
