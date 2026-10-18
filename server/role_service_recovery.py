"""异常退出的显式人类处置：只解除已确认停止的遗留归属，不操作OS进程。"""
from datetime import datetime
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from server.models import (
    AgentInstance, AgentTask, Member, RoleServiceLaunch, RoleServiceState,
    RoleServiceRecovery, RoleServiceRecoveryRequest, RoleServiceRecoveryPlan,
    RoleServiceRecoveryOut, ROLE_SERVICE_INSTANCE_FRESH_SECONDS,
)
from server.role_services import _as_utc, _now, _write_begin, load_role_service_context

STATE_FIELDS = (
    "generation", "desired_state", "observed_state", "current_launch_id", "process_launch_id",
    "observed_instance_id", "owner_host", "pid", "process_started_at", "spawned",
    "last_result", "started_at", "stopped_at", "updated_at", "updated_by",
)


def require_human(operator: Member) -> None:
    if operator.kind != "human":
        raise HTTPException(403, "only human members can recover role services")


def fail(code: str):
    raise HTTPException(409, code)


def candidate(project_id: str, member_id: str, session: Session, now: datetime):
    load_role_service_context(project_id, member_id, session)
    state = session.get(RoleServiceState, (project_id, member_id))
    if state is None or not state.process_launch_id:
        fail("recovery_no_ownership")
    launch = session.get(RoleServiceLaunch, state.process_launch_id)
    instance = session.get(AgentInstance, state.observed_instance_id) if state.observed_instance_id else None
    if (launch is None or launch.action != "start" or launch.project_id != project_id
            or launch.member_id != member_id or launch.claim_host != state.owner_host
            or launch.expected_instance_id != state.observed_instance_id
            or instance is None or instance.project_id != project_id or instance.member_id != member_id
            or instance.launch_id != state.process_launch_id or instance.pid != state.pid
            or not state.owner_host or not state.pid or state.pid <= 0
            or state.process_started_at is None or instance.last_seen_at is None):
        fail("recovery_identity_mismatch")
    if (now - _as_utc(instance.last_seen_at)).total_seconds() <= ROLE_SERVICE_INSTANCE_FRESH_SECONDS:
        fail("recovery_recent_heartbeat")
    if instance.current_task_id is not None or session.exec(select(AgentTask.id).where(
        AgentTask.target_member_id == member_id, AgentTask.status.in_(("queued", "running"))
    ).limit(1)).first() is not None:
        fail("recovery_tasks_active")
    if session.exec(select(RoleServiceLaunch.launch_id).where(
        RoleServiceLaunch.project_id == project_id, RoleServiceLaunch.member_id == member_id,
        RoleServiceLaunch.state.in_(("pending", "claimed")), RoleServiceLaunch.launch_expires_at >= now,
    ).limit(1)).first() is not None:
        fail("recovery_action_active")
    return state, instance


def recovery_plan(project_id: str, member_id: str, operator: Member, session: Session):
    require_human(operator)
    now = _now()
    state, instance = candidate(project_id, member_id, session, now)
    return RoleServiceRecoveryPlan(
        project_id=project_id, member_id=member_id, expected_generation=state.generation,
        expected_process_launch_id=state.process_launch_id, expected_instance_id=state.observed_instance_id,
        expected_owner_host=state.owner_host, process_pid=state.pid,
        process_started_at=_as_utc(state.process_started_at),
        instance_last_seen_at=_as_utc(instance.last_seen_at), checked_at=now,
    )


def receipt(audit: RoleServiceRecovery, *, replayed=False):
    return RoleServiceRecoveryOut(
        project_id=audit.project_id, member_id=audit.member_id, operation_key=audit.operation_key,
        recovery_id=audit.recovery_id, previous_generation=audit.previous_generation,
        generation=audit.generation, confirmed_by=audit.confirmed_by,
        recovered_at=_as_utc(audit.recovered_at), replayed=replayed,
    )


def recover_stopped(project_id: str, member_id: str, body: RoleServiceRecoveryRequest,
                    operator: Member, session: Session):
    require_human(operator)
    _write_begin(session)
    try:
        fingerprint = hashlib.sha256(json.dumps(
            {**body.model_dump(), "confirmed_by": operator.id}, sort_keys=True,
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        prior = session.get(RoleServiceRecovery, (project_id, member_id, body.operation_key))
        if prior is not None:
            if prior.request_fingerprint != fingerprint:
                fail("recovery_conflict")
            # 重放只返回原审计，不再检查/释放后来启动的归属。
            result = receipt(prior, replayed=True)
            session.rollback()
            return result
        now = _now()
        state, instance = candidate(project_id, member_id, session, now)
        if (state.generation != body.expected_generation
                or state.process_launch_id != body.expected_process_launch_id
                or state.observed_instance_id != body.expected_instance_id
                or state.owner_host != body.expected_owner_host):
            fail("recovery_generation_conflict")
        before = {}
        for field in STATE_FIELDS:
            value = getattr(state, field)
            before[field] = _as_utc(value).isoformat() if isinstance(value, datetime) else value
        audit = RoleServiceRecovery(
            project_id=project_id, member_id=member_id, operation_key=body.operation_key,
            request_fingerprint=fingerprint, previous_generation=state.generation,
            generation=state.generation + 1, process_launch_id=state.process_launch_id,
            instance_id=state.observed_instance_id, owner_host=state.owner_host,
            confirmed_by=operator.id, reason=body.reason, recovered_at=now, before_state=before,
        )
        changed = session.execute(update(RoleServiceState).where(
            RoleServiceState.project_id == project_id, RoleServiceState.member_id == member_id,
            RoleServiceState.generation == body.expected_generation,
            RoleServiceState.process_launch_id == body.expected_process_launch_id,
        ).values(
            generation=audit.generation, desired_state="stopped", observed_state="stopped",
            current_launch_id=None, process_launch_id=None, owner_host=None, spawned=False,
            observed_instance_id=None, pid=None, process_started_at=None, last_result="stopped",
            last_error_code=None, last_error_message=None, stopped_at=now,
            updated_at=now, updated_by=operator.id,
        ).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            fail("recovery_generation_conflict")
        instance.status = "offline"
        instance.updated_at = now
        # last_seen_at 保留原执行端心跳时间，不把人工处置伪装成在线上报。
        session.add(instance)
        session.add(audit)
        session.flush()
        result = receipt(audit)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
