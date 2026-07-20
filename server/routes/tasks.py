"""Agent task queue and scheduling foundation APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, update
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import (
    AgentInstance,
    AgentTask,
    AgentTaskClaim,
    AgentTaskClaimOut,
    AgentTaskClarificationAnswer,
    AgentTaskClarificationDecision,
    AgentTaskClarificationRequest,
    AgentTaskClarificationRound,
    AgentTaskClarificationRoundOut,
    AgentTaskComplete,
    AgentTaskCreate,
    AgentTaskHeartbeat,
    AgentTaskOut,
    AgentTaskSchedule,
    AgentTaskScheduleCreate,
    AgentTaskScheduleOut,
    AgentTaskScheduleRunOut,
    AgentTaskScheduleUpdate,
    AgentTaskTreeCheckpoint,
    AgentTaskTreeOut,
    AgentTaskTreeResume,
    Group,
    GroupMember,
    Member,
    Message,
    Project,
    TASK_AUTHORIZATION_TTL_DEFAULT_SECONDS,
    TASK_AUTHORIZED_SLICE_BUDGET_DEFAULT,
    TASK_MAX_CLARIFICATION_ROUNDS_DEFAULT,
    TASK_MAX_CLARIFICATION_ROUNDS_LIMIT,
    TASK_MAX_DELEGATION_DEPTH_DEFAULT,
    TASK_MAX_NONTERMINAL_DESCENDANTS_DEFAULT,
    TASK_MAX_RUNNING_DESCENDANTS_DEFAULT,
    TASK_MAX_RUNNING_PER_TARGET_DEFAULT,
    _SCHEDULE_STATUSES,
    _TASK_STATUSES,
    _TASK_WORKFLOW_STATUSES,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _require_agent(current: Member) -> None:
    if current.kind != "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only agent members can claim or complete tasks",
        )


def _get_task(task_id: int, session: Session) -> AgentTask:
    task = session.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return task


def _ensure_task_visible(task: AgentTask, current: Member) -> None:
    if current.kind == "human" or current.id in {task.created_by, task.target_member_id}:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")


def _get_schedule(schedule_id: int, current: Member, session: Session) -> AgentTaskSchedule:
    schedule = session.get(AgentTaskSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found")
    if current.kind != "human" and schedule.target_member_id != current.id and schedule.created_by != current.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found")
    return schedule


def _ensure_target_agent(member_id: str, session: Session) -> Member:
    member = session.get(Member, member_id)
    if member is None or member.kind != "agent":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_member_id must be an agent")
    return member


def _ensure_project_exists(project_id: str | None, session: Session) -> None:
    if project_id is not None and session.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_id not found")


def _get_root_task(task: AgentTask, session: Session) -> AgentTask:
    root_id = task.root_task_id or task.id
    root = session.get(AgentTask, root_id)
    if root is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task root is missing")
    return root


def _root_limit(value: int | None, default: int) -> int:
    return value if value is not None else default


def _ensure_root_governance_request_allowed(body: AgentTaskCreate, current: Member) -> None:
    custom_governance = body.may_delegate or any(
        value is not None
        for value in (
            body.max_delegation_depth,
            body.max_running_descendants,
            body.max_running_per_target,
            body.max_nonterminal_descendants,
            body.slice_budget,
            body.authorization_ttl_seconds,
        )
    )
    if current.kind != "human" and custom_governance:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only human members can grant root delegation or override root governance limits",
        )


def _resolve_child_context(
    body: AgentTaskCreate,
    current: Member,
    session: Session,
) -> tuple[AgentTask, AgentTask, str | None, int]:
    if body.parent_task_id is None:
        raise RuntimeError("parent_task_id is required")

    parent = session.get(AgentTask, body.parent_task_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="parent task not found")
    root = _get_root_task(parent, session)
    if current.kind != "human" and current.id not in {parent.target_member_id, root.created_by}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="parent task not found")
    if root.control_status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task tree control is {root.control_status}, not active",
        )
    current_epoch = root.authorization_epoch or 0
    if body.authorization_epoch != current_epoch:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"authorization epoch {body.authorization_epoch} is stale; current epoch is {current_epoch}",
        )
    if parent.status != "running" or parent.workflow_status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="parent task must be running before it can delegate child tasks",
        )
    if not parent.may_delegate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="parent task has no delegation permission",
        )

    project_id = parent.project_id
    if body.project_id is not None and body.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="child task project_id must match its parent task",
        )

    delegation_depth = parent.delegation_depth + 1
    max_depth = _root_limit(root.max_delegation_depth, TASK_MAX_DELEGATION_DEPTH_DEFAULT)
    if delegation_depth > max_depth:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task delegation depth exceeds root limit {max_depth}",
        )
    if body.may_delegate and delegation_depth >= max_depth:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="child task cannot delegate because it is already at the root depth limit",
        )
    return parent, root, project_id, delegation_depth


def _authorization_expired(root: AgentTask, now: datetime) -> bool:
    return (
        root.authorization_expires_at is not None
        and _as_utc(root.authorization_expires_at) <= now
    )


def _reserve_authorized_descendant(
    root: AgentTask,
    expected_epoch: int,
    now: datetime,
    session: Session,
) -> None:
    if root.id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task root is missing")

    descendants = AgentTask.__table__.alias("nonterminal_descendants")
    nonterminal_count = (
        select(func.count())
        .select_from(descendants)
        .where(
            descendants.c.root_task_id == root.id,
            descendants.c.parent_task_id.is_not(None),
            descendants.c.status.in_(("queued", "running")),
        )
        .scalar_subquery()
    )
    limit = _root_limit(
        root.max_nonterminal_descendants,
        TASK_MAX_NONTERMINAL_DESCENDANTS_DEFAULT,
    )
    result = session.execute(
        update(AgentTask)
        .where(
            AgentTask.id == root.id,
            AgentTask.status == "running",
            AgentTask.control_status == "active",
            AgentTask.authorization_epoch == expected_epoch,
            or_(
                AgentTask.authorization_expires_at.is_(None),
                AgentTask.authorization_expires_at > now,
            ),
            AgentTask.reserved_slice_count < AgentTask.authorized_slice_budget,
            nonterminal_count < limit,
        )
        .values(
            reserved_slice_count=AgentTask.reserved_slice_count + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        current_root = session.get(AgentTask, root.id)
        if current_root is None or current_root.status != "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="task root must be running before it can add descendants",
            )
        if current_root.control_status != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"task tree control is {current_root.control_status}, not active",
            )
        if _authorization_expired(current_root, now):
            _expire_root_authorization(current_root, now, session)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="task tree authorization has expired and is awaiting human approval",
            )
        current_epoch = current_root.authorization_epoch or 0
        if current_epoch != expected_epoch:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"authorization epoch {expected_epoch} is stale; current epoch is {current_epoch}",
            )
        reserved = current_root.reserved_slice_count or 0
        authorized = current_root.authorized_slice_budget or 0
        if reserved >= authorized:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"task tree authorized slice budget {authorized} exhausted",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"root task nonterminal descendant limit {limit} reached",
        )


def _root_control_claim_conditions(
    root: AgentTask,
    now: datetime,
    *,
    require_unexpired: bool = True,
) -> list:
    if root.id is None:
        return []

    root_rows = AgentTask.__table__.alias("claim_root")
    root_conditions = [
        root_rows.c.id == root.id,
        root_rows.c.control_status == "active",
    ]
    if require_unexpired:
        root_conditions.append(
            or_(
                root_rows.c.authorization_expires_at.is_(None),
                root_rows.c.authorization_expires_at > now,
            )
        )
    root_is_active = (
        select(func.count())
        .select_from(root_rows)
        .where(*root_conditions)
        .scalar_subquery()
    )
    return [root_is_active == 1]


def _descendant_claim_conditions(task: AgentTask, root: AgentTask, now: datetime) -> list:
    conditions = _root_control_claim_conditions(root, now)
    if task.parent_task_id is None or root.id is None:
        return conditions

    root_rows = AgentTask.__table__.alias("claim_running_root")
    running_descendants = AgentTask.__table__.alias("claim_running_descendants")
    running_for_target = AgentTask.__table__.alias("claim_running_for_target")
    root_is_running = (
        select(func.count())
        .select_from(root_rows)
        .where(root_rows.c.id == root.id, root_rows.c.status == "running")
        .scalar_subquery()
    )
    running_descendant_count = (
        select(func.count())
        .select_from(running_descendants)
        .where(
            running_descendants.c.root_task_id == root.id,
            running_descendants.c.parent_task_id.is_not(None),
            running_descendants.c.status == "running",
        )
        .scalar_subquery()
    )
    running_for_target_count = (
        select(func.count())
        .select_from(running_for_target)
        .where(
            running_for_target.c.root_task_id == root.id,
            running_for_target.c.parent_task_id.is_not(None),
            running_for_target.c.target_member_id == task.target_member_id,
            running_for_target.c.status == "running",
        )
        .scalar_subquery()
    )
    conditions.extend([
        root_is_running == 1,
        running_descendant_count
        < _root_limit(root.max_running_descendants, TASK_MAX_RUNNING_DESCENDANTS_DEFAULT),
        running_for_target_count
        < _root_limit(root.max_running_per_target, TASK_MAX_RUNNING_PER_TARGET_DEFAULT),
    ])
    return conditions


def _running_descendant_count(
    root_id: int,
    session: Session,
    *,
    target_member_id: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(AgentTask).where(
        AgentTask.root_task_id == root_id,
        AgentTask.parent_task_id.is_not(None),
        AgentTask.status == "running",
    )
    if target_member_id is not None:
        stmt = stmt.where(AgentTask.target_member_id == target_member_id)
    return int(session.execute(stmt).scalar_one())


def _claim_budget_conflict_detail(task: AgentTask, now: datetime, session: Session) -> str:
    root = _get_root_task(task, session)
    if root.control_status != "active":
        return f"task tree control is {root.control_status}, not active"
    if _authorization_expired(root, now):
        _expire_root_authorization(root, now, session)
        return "task tree authorization has expired and is awaiting human approval"
    if task.parent_task_id is None:
        return "task claim was blocked by task tree control state"
    if root.id is None or root.status != "running":
        return "task root must be running before descendants can be claimed"

    running_descendants = _running_descendant_count(root.id, session)
    max_running = _root_limit(
        root.max_running_descendants,
        TASK_MAX_RUNNING_DESCENDANTS_DEFAULT,
    )
    if running_descendants >= max_running:
        return f"root task running descendant limit {max_running} reached"

    running_for_target = _running_descendant_count(
        root.id,
        session,
        target_member_id=task.target_member_id,
    )
    max_per_target = _root_limit(
        root.max_running_per_target,
        TASK_MAX_RUNNING_PER_TARGET_DEFAULT,
    )
    if running_for_target >= max_per_target:
        return f"root task per-target running limit {max_per_target} reached"
    return "task claim was blocked by root governance limits"


def _tree_tasks(root: AgentTask, session: Session) -> list[AgentTask]:
    if root.id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task root is missing")
    return list(
        session.exec(
            select(AgentTask)
            .where(AgentTask.root_task_id == root.id)
            .order_by(AgentTask.id)
        ).all()
    )


def _ensure_tree_visible(root: AgentTask, current: Member) -> None:
    if current.kind == "human" or current.id in {root.created_by, root.target_member_id}:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task tree not found")


def _require_tree_pause_actor(root: AgentTask, current: Member) -> None:
    if current.kind == "human" or current.id in {root.created_by, root.target_member_id}:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only a human manager, root requester, or root executor can pause this task tree")


def _require_tree_manager(root: AgentTask, current: Member) -> None:
    if current.kind == "human" or current.id == root.created_by:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only a human manager or root requester can resume or cancel this task tree")


def _require_checkpoint_actor(root: AgentTask, current: Member) -> None:
    if current.kind == "human" or current.id == root.target_member_id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only a human manager or root executor can checkpoint this task tree")


def _tree_response(root: AgentTask, now: datetime, session: Session) -> dict:
    tasks = _tree_tasks(root, session)
    descendants = [task for task in tasks if task.parent_task_id is not None]
    authorized = root.authorized_slice_budget or 0
    reserved = root.reserved_slice_count or 0
    return {
        "root": root,
        "tasks": tasks,
        "running_descendants": sum(task.status == "running" for task in descendants),
        "nonterminal_descendants": sum(task.status in {"queued", "running"} for task in descendants),
        "remaining_slice_budget": max(authorized - reserved, 0),
        "authorization_expired": _authorization_expired(root, now),
    }


def _release_tree_claims(root: AgentTask, now: datetime, reason: str, session: Session) -> None:
    running_tasks = [task for task in _tree_tasks(root, session) if task.status == "running"]
    if not running_tasks:
        return

    running_ids = [task.id for task in running_tasks if task.id is not None]
    session.execute(
        update(AgentTask)
        .where(AgentTask.id.in_(running_ids), AgentTask.status == "running")
        .values(
            status="queued",
            workflow_status="accepted",
            claimed_by=None,
            instance_id=None,
            claim_token=None,
            lease_expires_at=None,
            last_error=reason,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    for task in running_tasks:
        if task.instance_id is None:
            continue
        instance = session.get(AgentInstance, task.instance_id)
        if instance is None or instance.current_task_id != str(task.id):
            continue
        instance.status = "idle"
        instance.current_task_id = None
        instance.last_error = reason
        instance.updated_at = now
        instance.last_seen_at = now
        session.add(instance)


def _cancel_tree_tasks(root: AgentTask, now: datetime, session: Session) -> None:
    active_tasks = [
        task for task in _tree_tasks(root, session) if task.status in {"queued", "running"}
    ]
    if not active_tasks:
        return

    active_ids = [task.id for task in active_tasks if task.id is not None]
    session.execute(
        update(AgentTask)
        .where(AgentTask.id.in_(active_ids), AgentTask.status.in_(("queued", "running")))
        .values(
            status="canceled",
            workflow_status="canceled",
            claimed_by=None,
            instance_id=None,
            claim_token=None,
            lease_expires_at=None,
            finished_at=now,
            last_error="task tree canceled",
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    for task in active_tasks:
        if task.instance_id is None:
            continue
        instance = session.get(AgentInstance, task.instance_id)
        if instance is None or instance.current_task_id != str(task.id):
            continue
        instance.status = "idle"
        instance.current_task_id = None
        instance.last_error = "task tree canceled"
        instance.updated_at = now
        instance.last_seen_at = now
        session.add(instance)


def _transition_root_control(
    root: AgentTask,
    *,
    allowed_statuses: set[str],
    next_status: str,
    now: datetime,
    session: Session,
    **values,
) -> AgentTask:
    if root.id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task root is missing")
    result = session.execute(
        update(AgentTask)
        .where(
            AgentTask.id == root.id,
            AgentTask.control_status.in_(allowed_statuses),
        )
        .values(control_status=next_status, updated_at=now, **values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        current_root = _get_task(root.id, session)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task tree control changed to {current_root.control_status}; retry from the current state",
        )
    session.commit()
    session.expire_all()
    return _get_task(root.id, session)


def _expire_root_authorization(root: AgentTask, now: datetime, session: Session) -> AgentTask:
    root = _transition_root_control(
        root,
        allowed_statuses={"active"},
        next_status="awaiting_human",
        checkpoint_reason="time_limit",
        now=now,
        session=session,
    )
    _release_tree_claims(root, now, "task tree authorization expired", session)
    session.commit()
    session.expire_all()
    return _get_task(int(root.id), session)


def _ensure_distinct_participants(requester_id: str, target_member_id: str) -> None:
    if requester_id == target_member_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task requester and target member must be different",
        )


def _ensure_instance_owner(instance_id: str | None, current: Member, session: Session) -> AgentInstance | None:
    if instance_id is None:
        return None

    instance = session.get(AgentInstance, instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="instance_id not found")
    if instance.member_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="instance belongs to another member")
    return instance


def _ensure_result_message_owner(
    message_id: int | None,
    current: Member,
    task: AgentTask,
    session: Session,
) -> None:
    if message_id is None:
        return

    message = session.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="result_message_id not found")
    if message.from_id != current.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="result_message_id must belong to task agent")
    if task.hall_group_id is not None and message.group_id not in {None, task.hall_group_id}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="result_message_id must belong to the task Hall or the legacy global timeline",
        )
    if message.group_id is None and message.to_list is not None and task.created_by not in message.to_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="legacy result message must be visible to the task requester",
        )


def _latest_clarification_round(task_id: int, session: Session) -> AgentTaskClarificationRound | None:
    return session.exec(
        select(AgentTaskClarificationRound)
        .where(AgentTaskClarificationRound.task_id == task_id)
        .order_by(AgentTaskClarificationRound.round_index.desc())
    ).first()


def _clarification_message(
    task: AgentTask,
    *,
    message_id: int | None,
    expected_sender_id: str,
    boundary_name: str,
    session: Session,
) -> Message:
    if task.hall_group_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task has no Task Hall for clarification message boundaries",
        )

    if message_id is None:
        message = session.exec(
            select(Message)
            .where(
                Message.group_id == task.hall_group_id,
                Message.from_id == expected_sender_id,
                Message.revoked_at.is_(None),
            )
            .order_by(Message.id.desc())
        ).first()
    else:
        message = session.get(Message, message_id)

    if message is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{boundary_name}_message_id not found in the task Hall",
        )
    if message.group_id != task.hall_group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{boundary_name}_message_id must belong to the task Hall",
        )
    if message.from_id != expected_sender_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{boundary_name}_message_id must belong to {expected_sender_id}",
        )
    if message.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{boundary_name}_message_id cannot reference a revoked message",
        )
    return message


def _answer_message_bounds(
    task: AgentTask,
    clarification_round: AgentTaskClarificationRound,
    answer_message_id: int,
    session: Session,
) -> tuple[int, int]:
    answer_end = _clarification_message(
        task,
        message_id=answer_message_id,
        expected_sender_id=task.created_by,
        boundary_name="answer",
        session=session,
    )
    question_message_id = clarification_round.question_message_id
    if answer_end.id is None or answer_end.id <= question_message_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clarification answer must be posted after the question boundary",
        )
    answer_messages = session.exec(
        select(Message)
        .where(
            Message.group_id == task.hall_group_id,
            Message.from_id == task.created_by,
            Message.revoked_at.is_(None),
            Message.id > question_message_id,
            Message.id <= answer_end.id,
        )
        .order_by(Message.id.asc())
    ).all()
    if not answer_messages or answer_messages[0].id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clarification answer has no requester messages after the question boundary",
        )
    return int(answer_messages[0].id), int(answer_end.id)


def _escalate_clarification_decision(
    task: AgentTask,
    root: AgentTask,
    now: datetime,
    session: Session,
) -> AgentTask:
    if task.id is None or root.id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task tree is incomplete")
    task_result = session.execute(
        update(AgentTask)
        .where(
            AgentTask.id == task.id,
            AgentTask.status == "queued",
            AgentTask.workflow_status == "clarification_answered",
            AgentTask.clarification_round_count >= AgentTask.max_clarification_rounds,
        )
        .values(workflow_status="needs_decision", updated_at=now)
        .execution_options(synchronize_session=False)
    )
    root_result = session.execute(
        update(AgentTask)
        .where(
            AgentTask.id == root.id,
            AgentTask.control_status == "active",
        )
        .values(
            control_status="awaiting_human",
            checkpoint_reason="needs_decision",
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if task_result.rowcount != 1 or root_result.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task or root control changed while escalating clarification",
        )
    _release_tree_claims(root, now, "clarification needs human decision", session)
    session.commit()
    session.expire_all()
    return _get_task(int(task.id), session)


def _touch_task(task: AgentTask, now: datetime) -> None:
    task.updated_at = now


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _lease_expired(task: AgentTask, now: datetime) -> bool:
    return task.lease_expires_at is not None and _as_utc(task.lease_expires_at) <= now


def _release_expired_instance(task: AgentTask, now: datetime, session: Session, reason: str) -> None:
    if task.instance_id is None:
        return
    instance = session.get(AgentInstance, task.instance_id)
    if instance is None or instance.current_task_id != str(task.id):
        return
    instance.status = "error"
    instance.current_task_id = None
    instance.last_error = reason
    instance.updated_at = now
    session.add(instance)


def _try_requeue_expired_task(task: AgentTask, now: datetime, session: Session) -> bool:
    if task.id is None or not _lease_expired(task, now):
        return False
    reason = f"claim lease expired after attempt {task.attempt}"
    result = session.execute(
        update(AgentTask)
        .where(
            AgentTask.id == task.id,
            AgentTask.status == "running",
            AgentTask.lease_expires_at.is_not(None),
            AgentTask.lease_expires_at <= now,
        )
        .values(
            status="queued",
            workflow_status="accepted",
            claimed_by=None,
            instance_id=None,
            claim_token=None,
            lease_expires_at=None,
            last_error=reason,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return False
    _release_expired_instance(task, now, session, reason)
    return True


def _touch_schedule(schedule: AgentTaskSchedule, now: datetime) -> None:
    schedule.updated_at = now


def _require_schedule_manager(schedule: AgentTaskSchedule, current: Member) -> None:
    if current.kind == "human" or schedule.created_by == current.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only human members or schedule creators can update schedules")


def _task_hall_name(title: str | None, content: str) -> str:
    source = " ".join((title or content).split())
    return source[:80] or "Task"


def _create_task_with_hall(
    *,
    target_member_id: str,
    created_by: str,
    content: str,
    title: str | None,
    project_id: str | None,
    schedule_id: int | None,
    parent_task_id: int | None,
    root_task_id: int | None,
    delegation_depth: int,
    may_delegate: bool,
    max_delegation_depth: int | None,
    max_running_descendants: int | None,
    max_running_per_target: int | None,
    max_nonterminal_descendants: int | None,
    control_status: str | None,
    authorization_epoch: int | None,
    authorized_slice_budget: int | None,
    reserved_slice_count: int | None,
    authorization_expires_at: datetime | None,
    checkpoint_reason: str | None,
    max_clarification_rounds: int,
    now: datetime,
    session: Session,
) -> AgentTask:
    hall_group_id = f"group:task-{uuid4().hex}"
    session.add(
        Group(
            id=hall_group_id,
            name=_task_hall_name(title, content),
            description=content,
            type="task",
            project_id=project_id,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
    )
    for member_id in dict.fromkeys((created_by, target_member_id)):
        session.add(
            GroupMember(
                group_id=hall_group_id,
                member_id=member_id,
                role="owner" if member_id == created_by else "member",
                created_at=now,
            )
        )

    task = AgentTask(
        schedule_id=schedule_id,
        project_id=project_id,
        hall_group_id=hall_group_id,
        parent_task_id=parent_task_id,
        root_task_id=root_task_id,
        delegation_depth=delegation_depth,
        may_delegate=may_delegate,
        max_delegation_depth=max_delegation_depth,
        max_running_descendants=max_running_descendants,
        max_running_per_target=max_running_per_target,
        max_nonterminal_descendants=max_nonterminal_descendants,
        control_status=control_status,
        authorization_epoch=authorization_epoch,
        authorized_slice_budget=authorized_slice_budget,
        reserved_slice_count=reserved_slice_count,
        authorization_expires_at=authorization_expires_at,
        checkpoint_reason=checkpoint_reason,
        max_clarification_rounds=max_clarification_rounds,
        clarification_round_count=0,
        target_member_id=target_member_id,
        created_by=created_by,
        content=content,
        title=title,
        status="queued",
        workflow_status="assigned",
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.flush()
    if task.root_task_id is None:
        task.root_task_id = task.id
        session.add(task)
    return task


def _create_task_from_schedule(schedule: AgentTaskSchedule, now: datetime, session: Session) -> AgentTask:
    return _create_task_with_hall(
        schedule_id=schedule.id,
        project_id=None,
        target_member_id=schedule.target_member_id,
        created_by=schedule.created_by,
        content=schedule.content,
        title=schedule.title,
        parent_task_id=None,
        root_task_id=None,
        delegation_depth=0,
        may_delegate=False,
        max_delegation_depth=TASK_MAX_DELEGATION_DEPTH_DEFAULT,
        max_running_descendants=TASK_MAX_RUNNING_DESCENDANTS_DEFAULT,
        max_running_per_target=TASK_MAX_RUNNING_PER_TARGET_DEFAULT,
        max_nonterminal_descendants=TASK_MAX_NONTERMINAL_DESCENDANTS_DEFAULT,
        control_status="active",
        authorization_epoch=0,
        authorized_slice_budget=0,
        reserved_slice_count=0,
        authorization_expires_at=None,
        checkpoint_reason=None,
        max_clarification_rounds=TASK_MAX_CLARIFICATION_ROUNDS_DEFAULT,
        now=now,
        session=session,
    )


def _update_workflow_status(task: AgentTask, workflow_status: str, now: datetime, session: Session) -> AgentTask:
    task.workflow_status = workflow_status
    _touch_task(task, now)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("", response_model=AgentTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    body: AgentTaskCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Create a queued task and its dedicated one-to-one Task Hall."""
    _ensure_target_agent(body.target_member_id, session)
    _ensure_distinct_participants(current.id, body.target_member_id)
    now = datetime.now(timezone.utc)

    if body.parent_task_id is None:
        _ensure_root_governance_request_allowed(body, current)
        project_id = body.project_id
        _ensure_project_exists(project_id, session)
        parent_task_id = None
        root_task_id = None
        delegation_depth = 0
        max_delegation_depth = (
            body.max_delegation_depth
            if body.max_delegation_depth is not None
            else TASK_MAX_DELEGATION_DEPTH_DEFAULT
        )
        max_running_descendants = (
            body.max_running_descendants
            if body.max_running_descendants is not None
            else TASK_MAX_RUNNING_DESCENDANTS_DEFAULT
        )
        max_running_per_target = (
            body.max_running_per_target
            if body.max_running_per_target is not None
            else TASK_MAX_RUNNING_PER_TARGET_DEFAULT
        )
        max_nonterminal_descendants = (
            body.max_nonterminal_descendants
            if body.max_nonterminal_descendants is not None
            else TASK_MAX_NONTERMINAL_DESCENDANTS_DEFAULT
        )
        control_status = "active"
        authorization_epoch = 1 if body.may_delegate else 0
        authorized_slice_budget = (
            body.slice_budget
            if body.slice_budget is not None
            else TASK_AUTHORIZED_SLICE_BUDGET_DEFAULT
        ) if body.may_delegate else 0
        reserved_slice_count = 0
        authorization_expires_at = (
            now
            + timedelta(
                seconds=body.authorization_ttl_seconds
                if body.authorization_ttl_seconds is not None
                else TASK_AUTHORIZATION_TTL_DEFAULT_SECONDS
            )
            if body.may_delegate
            else None
        )
        checkpoint_reason = None
    else:
        parent, root, project_id, delegation_depth = _resolve_child_context(body, current, session)
        _ensure_project_exists(project_id, session)
        _reserve_authorized_descendant(root, int(body.authorization_epoch), now, session)
        parent_task_id = parent.id
        root_task_id = root.id
        max_delegation_depth = None
        max_running_descendants = None
        max_running_per_target = None
        max_nonterminal_descendants = None
        control_status = None
        authorization_epoch = None
        authorized_slice_budget = None
        reserved_slice_count = None
        authorization_expires_at = None
        checkpoint_reason = None

    task = _create_task_with_hall(
        target_member_id=body.target_member_id,
        created_by=current.id,
        content=body.content,
        title=body.title,
        project_id=project_id,
        schedule_id=None,
        parent_task_id=parent_task_id,
        root_task_id=root_task_id,
        delegation_depth=delegation_depth,
        may_delegate=body.may_delegate,
        max_delegation_depth=max_delegation_depth,
        max_running_descendants=max_running_descendants,
        max_running_per_target=max_running_per_target,
        max_nonterminal_descendants=max_nonterminal_descendants,
        control_status=control_status,
        authorization_epoch=authorization_epoch,
        authorized_slice_budget=authorized_slice_budget,
        reserved_slice_count=reserved_slice_count,
        authorization_expires_at=authorization_expires_at,
        checkpoint_reason=checkpoint_reason,
        max_clarification_rounds=body.max_clarification_rounds,
        now=now,
        session=session,
    )
    session.commit()
    session.refresh(task)
    return task


@router.get("", response_model=list[AgentTaskOut])
def list_tasks(
    target_member_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    workflow_status: str | None = Query(None),
    project_id: str | None = Query(None),
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List tasks visible to the current member."""
    stmt = select(AgentTask)
    if current.kind != "human":
        stmt = stmt.where(or_(AgentTask.target_member_id == current.id, AgentTask.created_by == current.id))
    if target_member_id:
        stmt = stmt.where(AgentTask.target_member_id == target_member_id)
    if status_filter:
        normalized_status = status_filter.strip().lower()
        if normalized_status not in _TASK_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"status must be one of {sorted(_TASK_STATUSES)}",
            )
        stmt = stmt.where(AgentTask.status == normalized_status)
    if workflow_status:
        normalized_workflow_status = workflow_status.strip().lower()
        if normalized_workflow_status not in _TASK_WORKFLOW_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"workflow_status must be one of {sorted(_TASK_WORKFLOW_STATUSES)}",
            )
        stmt = stmt.where(AgentTask.workflow_status == normalized_workflow_status)
    if project_id:
        stmt = stmt.where(AgentTask.project_id == project_id.strip())
    return session.exec(stmt.order_by(AgentTask.created_at.desc())).all()  # type: ignore[union-attr]


@router.post("/schedules", response_model=AgentTaskScheduleOut, status_code=status.HTTP_201_CREATED)
def create_task_schedule(
    body: AgentTaskScheduleCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Create a one-off or interval task schedule."""
    _ensure_target_agent(body.target_member_id, session)
    _ensure_distinct_participants(current.id, body.target_member_id)
    now = datetime.now(timezone.utc)
    run_at = body.run_at or now
    schedule = AgentTaskSchedule(
        target_member_id=body.target_member_id,
        created_by=current.id,
        content=body.content,
        title=body.title,
        schedule_type="interval" if body.interval_seconds is not None else "once",
        status="active",
        next_run_at=run_at,
        interval_seconds=body.interval_seconds,
        created_at=now,
        updated_at=now,
    )
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


@router.get("/schedules", response_model=list[AgentTaskScheduleOut])
def list_task_schedules(
    target_member_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List task schedules visible to the current member."""
    stmt = select(AgentTaskSchedule)
    if current.kind != "human":
        stmt = stmt.where(
            or_(AgentTaskSchedule.target_member_id == current.id, AgentTaskSchedule.created_by == current.id)
        )
    if target_member_id:
        stmt = stmt.where(AgentTaskSchedule.target_member_id == target_member_id)
    if status_filter:
        normalized_status = status_filter.strip().lower()
        if normalized_status not in _SCHEDULE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"status must be one of {sorted(_SCHEDULE_STATUSES)}",
            )
        stmt = stmt.where(AgentTaskSchedule.status == normalized_status)
    return session.exec(stmt.order_by(AgentTaskSchedule.created_at.desc())).all()  # type: ignore[union-attr]


@router.post("/schedules/run-due", response_model=AgentTaskScheduleRunOut)
def run_due_task_schedules(
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Materialize due active schedules into queued tasks.

    This endpoint is intentionally explicit: TALK records schedules, but this
    first slice does not start an internal background scheduler.
    """
    now = datetime.now(timezone.utc)
    stmt = select(AgentTaskSchedule).where(
        AgentTaskSchedule.status == "active",
        AgentTaskSchedule.next_run_at <= now,
    )
    if current.kind != "human":
        stmt = stmt.where(
            or_(AgentTaskSchedule.target_member_id == current.id, AgentTaskSchedule.created_by == current.id)
        )

    schedules = session.exec(stmt.order_by(AgentTaskSchedule.next_run_at.asc())).all()  # type: ignore[union-attr]
    created_tasks: list[AgentTask] = []
    updated_schedules: list[AgentTaskSchedule] = []
    for schedule in schedules:
        task = _create_task_from_schedule(schedule, now, session)
        session.flush()

        schedule.last_run_at = now
        schedule.last_task_id = task.id
        if schedule.schedule_type == "interval":
            assert schedule.interval_seconds is not None
            schedule.next_run_at = now + timedelta(seconds=schedule.interval_seconds)
        else:
            schedule.status = "completed"
        _touch_schedule(schedule, now)
        session.add(schedule)
        created_tasks.append(task)
        updated_schedules.append(schedule)

    session.commit()
    for task in created_tasks:
        session.refresh(task)
    for schedule in updated_schedules:
        session.refresh(schedule)
    return {"created_tasks": created_tasks, "updated_schedules": updated_schedules}


@router.get("/schedules/{schedule_id}", response_model=AgentTaskScheduleOut)
def get_task_schedule(
    schedule_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Read one task schedule visible to the current member."""
    return _get_schedule(schedule_id, current, session)


@router.patch("/schedules/{schedule_id}", response_model=AgentTaskScheduleOut)
def update_task_schedule(
    schedule_id: int,
    body: AgentTaskScheduleUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Pause, resume, or cancel a task schedule."""
    schedule = _get_schedule(schedule_id, current, session)
    _require_schedule_manager(schedule, current)
    if schedule.status == "completed" and body.status != "canceled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="completed schedules cannot be resumed or paused")
    if schedule.status == "canceled" and body.status != "canceled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="canceled schedules cannot be resumed or paused")
    now = datetime.now(timezone.utc)
    schedule.status = body.status
    _touch_schedule(schedule, now)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


@router.post("/requeue-expired", response_model=list[AgentTaskOut])
def requeue_expired_tasks(
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Return this Agent's expired running claims to the queued state."""
    _require_agent(current)
    now = datetime.now(timezone.utc)
    expired = session.exec(
        select(AgentTask).where(
            AgentTask.target_member_id == current.id,
            AgentTask.status == "running",
            AgentTask.lease_expires_at.is_not(None),
            AgentTask.lease_expires_at <= now,
        )
    ).all()
    requeued_ids = [
        int(task.id)
        for task in expired
        if task.id is not None and _try_requeue_expired_task(task, now, session)
    ]
    session.commit()
    session.expire_all()
    return [_get_task(task_id, session) for task_id in requeued_ids]


@router.get("/{task_id}", response_model=AgentTaskOut)
def get_task(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Read one task visible to the requester or assignee."""
    task = _get_task(task_id, session)
    _ensure_task_visible(task, current)
    return task


@router.get("/{task_id}/tree", response_model=AgentTaskTreeOut)
def get_task_tree(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Read the root control state and all tasks in a task tree."""
    root = _get_root_task(_get_task(task_id, session), session)
    _ensure_tree_visible(root, current)
    return _tree_response(root, datetime.now(timezone.utc), session)


@router.post("/{task_id}/pause-tree", response_model=AgentTaskTreeOut)
def pause_task_tree(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Stop new claims and revoke current server-side claims for a task tree."""
    root = _get_root_task(_get_task(task_id, session), session)
    _require_tree_pause_actor(root, current)
    if root.control_status == "canceled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task tree is canceled")

    now = datetime.now(timezone.utc)
    root = _transition_root_control(
        root,
        allowed_statuses={"active", "pause_requested", "paused", "awaiting_human"},
        next_status="pause_requested",
        checkpoint_reason="manual_pause",
        now=now,
        session=session,
    )
    _release_tree_claims(root, now, "task tree paused", session)
    root = _transition_root_control(
        root,
        allowed_statuses={"pause_requested"},
        next_status="paused",
        now=now,
        session=session,
    )
    return _tree_response(root, now, session)


@router.post("/{task_id}/checkpoint", response_model=AgentTaskTreeOut)
def checkpoint_task_tree(
    task_id: int,
    body: AgentTaskTreeCheckpoint,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Pause a task tree at a declared checkpoint pending human approval."""
    root = _get_root_task(_get_task(task_id, session), session)
    _require_checkpoint_actor(root, current)
    if root.control_status == "canceled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task tree is canceled")

    now = datetime.now(timezone.utc)
    root = _transition_root_control(
        root,
        allowed_statuses={"active", "pause_requested", "paused", "awaiting_human"},
        next_status="awaiting_human",
        checkpoint_reason=body.reason,
        now=now,
        session=session,
    )
    _release_tree_claims(root, now, f"task tree checkpoint: {body.reason}", session)
    session.commit()
    session.expire_all()
    return _tree_response(_get_task(int(root.id), session), now, session)


@router.post("/{task_id}/resume-tree", response_model=AgentTaskTreeOut)
def resume_task_tree(
    task_id: int,
    body: AgentTaskTreeResume,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Open a new finite authorization epoch for a paused task tree."""
    root = _get_root_task(_get_task(task_id, session), session)
    _require_tree_manager(root, current)
    if root.control_status not in {"paused", "awaiting_human"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task tree control is {root.control_status}, not paused or awaiting_human",
        )
    if root.may_delegate and body.slice_budget < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="delegating task trees require a slice_budget between 1 and 3",
        )
    if not root.may_delegate and body.slice_budget != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="non-delegating task trees require slice_budget=0",
        )

    now = datetime.now(timezone.utc)
    root = _transition_root_control(
        root,
        allowed_statuses={"paused", "awaiting_human"},
        next_status="active",
        authorization_epoch=(root.authorization_epoch or 0) + 1,
        authorized_slice_budget=body.slice_budget,
        reserved_slice_count=0,
        authorization_expires_at=(
            now + timedelta(seconds=body.authorization_ttl_seconds)
            if root.may_delegate
            else None
        ),
        checkpoint_reason=None,
        now=now,
        session=session,
    )
    return _tree_response(root, now, session)


@router.post("/{task_id}/cancel-tree", response_model=AgentTaskTreeOut)
def cancel_task_tree(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Cancel every nonterminal task and permanently close the task tree."""
    root = _get_root_task(_get_task(task_id, session), session)
    _require_tree_manager(root, current)
    now = datetime.now(timezone.utc)
    if root.control_status != "canceled":
        root = _transition_root_control(
            root,
            allowed_statuses={
                "active",
                "pause_requested",
                "paused",
                "awaiting_human",
                "cancel_requested",
            },
            next_status="cancel_requested",
            checkpoint_reason="manual_cancel",
            now=now,
            session=session,
        )
        _cancel_tree_tasks(root, now, session)
        root = _transition_root_control(
            root,
            allowed_statuses={"cancel_requested"},
            next_status="canceled",
            now=now,
            session=session,
        )
    return _tree_response(root, now, session)


@router.get("/{task_id}/clarification-rounds", response_model=list[AgentTaskClarificationRoundOut])
def list_task_clarification_rounds(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Return the explicit question and answer boundaries for a task."""
    task = _get_task(task_id, session)
    _ensure_task_visible(task, current)
    return session.exec(
        select(AgentTaskClarificationRound)
        .where(AgentTaskClarificationRound.task_id == task_id)
        .order_by(AgentTaskClarificationRound.round_index.asc())
    ).all()


@router.post("/{task_id}/request-clarification", response_model=AgentTaskOut)
def request_task_clarification(
    task_id: int,
    body: AgentTaskClarificationRequest | None = None,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Open one bounded clarification round around an assignee Hall message."""
    task = _get_task(task_id, session)
    if task.target_member_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only the task assignee can request clarification")
    if task.status != "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clarification can only be requested before the task is claimed",
        )
    root = _get_root_task(task, session)
    if root.control_status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task tree control is {root.control_status}, not active",
        )

    requested_message_id = body.question_message_id if body is not None else None
    latest_round = _latest_clarification_round(task_id, session)
    if task.workflow_status == "clarification_requested":
        if latest_round is None or requested_message_id in {None, latest_round.question_message_id}:
            return task
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task already has a different open clarification round",
        )
    if task.workflow_status not in {"assigned", "clarification_answered"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not ready for clarification",
        )

    # Preserve the old no-Hall task path. New tasks always use explicit Hall boundaries.
    if task.hall_group_id is None and requested_message_id is None and task.workflow_status == "assigned":
        return _update_workflow_status(task, "clarification_requested", datetime.now(timezone.utc), session)

    question = _clarification_message(
        task,
        message_id=requested_message_id,
        expected_sender_id=current.id,
        boundary_name="question",
        session=session,
    )
    if question.id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="clarification question is missing an id")
    if latest_round is not None:
        previous_boundary = latest_round.answer_end_message_id or latest_round.question_message_id
        if question.id <= previous_boundary:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="clarification question must be posted after the previous round boundary",
            )

    now = datetime.now(timezone.utc)
    if task.clarification_round_count >= task.max_clarification_rounds:
        return _escalate_clarification_decision(task, root, now, session)

    next_round_index = task.clarification_round_count + 1
    update_conditions = [
        AgentTask.id == task_id,
        AgentTask.status == "queued",
        AgentTask.workflow_status == task.workflow_status,
        AgentTask.clarification_round_count == task.clarification_round_count,
    ]
    update_conditions.extend(_root_control_claim_conditions(root, now, require_unexpired=False))
    result = session.execute(
        update(AgentTask)
        .where(*update_conditions)
        .values(
            workflow_status="clarification_requested",
            clarification_round_count=next_round_index,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task workflow or root control changed while opening clarification",
        )
    session.add(
        AgentTaskClarificationRound(
            task_id=task_id,
            round_index=next_round_index,
            status="requested",
            question_message_id=int(question.id),
            requested_at=now,
        )
    )
    session.commit()
    session.expire_all()
    return _get_task(task_id, session)


@router.post("/{task_id}/submit-clarification-answer", response_model=AgentTaskOut)
def submit_task_clarification_answer(
    task_id: int,
    body: AgentTaskClarificationAnswer,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Close the current clarification round at an explicit requester message boundary."""
    task = _get_task(task_id, session)
    if task.created_by != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only the task requester can submit clarification answers")
    latest_round = _latest_clarification_round(task_id, session)
    if task.workflow_status == "clarification_answered":
        if latest_round is not None and latest_round.answer_end_message_id == body.answer_message_id:
            return task
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clarification answer was already submitted with a different boundary",
        )
    if task.workflow_status != "clarification_requested":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not awaiting a clarification answer",
        )
    if latest_round is None or latest_round.status != "requested" or latest_round.id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="legacy clarification has no explicit round boundary; the assignee may accept it through the compatibility path",
        )
    root = _get_root_task(task, session)
    if root.control_status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task tree control is {root.control_status}, not active",
        )
    answer_start_id, answer_end_id = _answer_message_bounds(
        task,
        latest_round,
        body.answer_message_id,
        session,
    )
    now = datetime.now(timezone.utc)
    round_result = session.execute(
        update(AgentTaskClarificationRound)
        .where(
            AgentTaskClarificationRound.id == latest_round.id,
            AgentTaskClarificationRound.status == "requested",
        )
        .values(
            status="answered",
            answer_start_message_id=answer_start_id,
            answer_end_message_id=answer_end_id,
            answered_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    task_conditions = [
        AgentTask.id == task_id,
        AgentTask.status == "queued",
        AgentTask.workflow_status == "clarification_requested",
        AgentTask.clarification_round_count == latest_round.round_index,
    ]
    task_conditions.extend(_root_control_claim_conditions(root, now, require_unexpired=False))
    task_result = session.execute(
        update(AgentTask)
        .where(*task_conditions)
        .values(workflow_status="clarification_answered", updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if round_result.rowcount != 1 or task_result.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clarification round or root control changed while submitting the answer",
        )
    session.commit()
    session.expire_all()
    return _get_task(task_id, session)


@router.post("/{task_id}/resolve-clarification", response_model=AgentTaskOut)
def resolve_task_clarification_decision(
    task_id: int,
    body: AgentTaskClarificationDecision,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Release a needs-decision task after human/root-controller intervention."""
    task = _get_task(task_id, session)
    root = _get_root_task(task, session)
    if current.kind != "human" and current.id not in {task.created_by, root.created_by}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only a human manager or task-tree requester can resolve clarification decisions",
        )
    if task.workflow_status == "clarification_answered":
        return task
    if task.workflow_status != "needs_decision":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not needs_decision",
        )
    if root.control_status != "awaiting_human":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task tree control is {root.control_status}, not awaiting_human",
        )
    if body.allow_additional_round and task.max_clarification_rounds >= TASK_MAX_CLARIFICATION_ROUNDS_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"clarification round limit {TASK_MAX_CLARIFICATION_ROUNDS_LIMIT} already reached",
        )
    now = datetime.now(timezone.utc)
    new_limit = task.max_clarification_rounds + (1 if body.allow_additional_round else 0)
    result = session.execute(
        update(AgentTask)
        .where(
            AgentTask.id == task_id,
            AgentTask.status == "queued",
            AgentTask.workflow_status == "needs_decision",
            AgentTask.max_clarification_rounds == task.max_clarification_rounds,
        )
        .values(
            workflow_status="clarification_answered",
            max_clarification_rounds=new_limit,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="clarification decision changed concurrently")
    session.commit()
    session.expire_all()
    return _get_task(task_id, session)


@router.post("/{task_id}/accept", response_model=AgentTaskOut)
def accept_task(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Record that the assignee accepts the task after any clarification."""
    task = _get_task(task_id, session)
    if task.target_member_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only the task assignee can accept the task")
    root = _get_root_task(task, session)
    if root.control_status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task tree control is {root.control_status}, not active",
        )
    if task.workflow_status == "accepted":
        return task
    if task.workflow_status == "clarification_requested" and _latest_clarification_round(task_id, session) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the requester must explicitly submit the current clarification answer before acceptance",
        )
    if task.workflow_status not in {"assigned", "clarification_requested", "clarification_answered"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not assignable",
        )
    now = datetime.now(timezone.utc)
    accept_conditions = [
        AgentTask.id == task_id,
        AgentTask.status == "queued",
        AgentTask.workflow_status == task.workflow_status,
    ]
    accept_conditions.extend(_root_control_claim_conditions(root, now, require_unexpired=False))
    result = session.execute(
        update(AgentTask)
        .where(*accept_conditions)
        .values(workflow_status="accepted", updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task workflow changed while accepting")
    session.commit()
    session.expire_all()
    return _get_task(task_id, session)


@router.post("/{task_id}/collect-result", response_model=AgentTaskOut)
def collect_task_result(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Mark a submitted result as collected by the original requester."""
    task = _get_task(task_id, session)
    if task.created_by != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only the task requester can collect the result")
    if task.workflow_status == "completed":
        return task
    if task.workflow_status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not submitted",
        )
    if task.result_message_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task has no result message to collect")

    now = datetime.now(timezone.utc)
    task.result_collected_at = now
    return _update_workflow_status(task, "completed", now, session)


@router.post("/{task_id}/cancel", response_model=AgentTaskOut)
def cancel_task(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Cancel a task before it is claimed by its runner."""
    task = _get_task(task_id, session)
    if task.created_by != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only the task requester can cancel the task")
    if task.status == "canceled":
        return task
    if task.status != "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only unclaimed tasks can be canceled; running cancellation requires cooperative runner interruption",
        )

    now = datetime.now(timezone.utc)
    task.status = "canceled"
    task.workflow_status = "canceled"
    task.finished_at = now
    _touch_task(task, now)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/{task_id}/claim", response_model=AgentTaskClaimOut)
def claim_task(
    task_id: int,
    body: AgentTaskClaim,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Claim a queued task for the target Agent."""
    _require_agent(current)
    task = _get_task(task_id, session)
    if task.target_member_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="task belongs to another agent")

    instance = _ensure_instance_owner(body.instance_id, current, session)
    now = datetime.now(timezone.utc)
    if task.status == "running" and _lease_expired(task, now):
        _try_requeue_expired_task(task, now, session)
        session.commit()
        session.expire_all()
        task = _get_task(task_id, session)
        instance = _ensure_instance_owner(body.instance_id, current, session)
    root = _get_root_task(task, session)
    if task.status == "running" and task.claimed_by == current.id and task.instance_id == body.instance_id:
        if root.control_status != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"task tree control is {root.control_status}, not active",
            )
        if task.claim_token is None:
            claim_token = uuid4().hex
            token_conditions = [
                AgentTask.id == task_id,
                AgentTask.status == "running",
                AgentTask.claimed_by == current.id,
                AgentTask.claim_token.is_(None),
            ]
            token_conditions.extend(
                _root_control_claim_conditions(root, now, require_unexpired=False)
            )
            result = session.execute(
                update(AgentTask)
                .where(*token_conditions)
                .values(
                    claim_token=claim_token,
                    attempt=func.max(AgentTask.attempt, 1),
                    heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=body.lease_seconds),
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="task claim is no longer active",
                )
            session.commit()
            session.expire_all()
            return _get_task(task_id, session)
        return task
    if task.status != "queued":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"task is already {task.status}")
    if task.workflow_status in {"clarification_requested", "clarification_answered", "needs_decision"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}; the assignee must finish the clarification protocol before claim",
        )
    if task.workflow_status not in {"assigned", "accepted"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not ready to start",
        )

    claim_token = uuid4().hex
    claim_conditions = [
        AgentTask.id == task_id,
        AgentTask.status == "queued",
        AgentTask.workflow_status.in_(("assigned", "accepted")),
    ]
    claim_conditions.extend(_descendant_claim_conditions(task, root, now))
    result = session.execute(
        update(AgentTask)
        .where(*claim_conditions)
        .values(
            status="running",
            workflow_status="in_progress",
            attempt=AgentTask.attempt + 1,
            claimed_by=current.id,
            instance_id=body.instance_id,
            claim_token=claim_token,
            claimed_at=now,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=body.lease_seconds),
            last_error=None,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        current_task = _get_task(task_id, session)
        if (
            current_task.status == "running"
            and current_task.claimed_by == current.id
            and current_task.instance_id == body.instance_id
        ):
            return current_task
        if current_task.status == "queued":
            if current_task.workflow_status not in {"assigned", "accepted"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"task workflow is {current_task.workflow_status}, not ready to start",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_claim_budget_conflict_detail(current_task, now, session),
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"task is already {current_task.status}")

    if instance is not None:
        instance.status = "busy"
        instance.current_task_id = str(task.id)
        instance.last_error = None
        instance.updated_at = now
        instance.last_seen_at = now
        session.add(instance)

    session.commit()
    session.expire_all()
    return _get_task(task_id, session)


@router.post("/{task_id}/heartbeat", response_model=AgentTaskOut)
def heartbeat_task(
    task_id: int,
    body: AgentTaskHeartbeat,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Renew an active task claim lease held by this Agent."""
    _require_agent(current)
    task = _get_task(task_id, session)
    if task.target_member_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="task belongs to another agent")
    if task.status != "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"task is {task.status}, not running")
    if task.claim_token != body.claim_token:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task claim token is stale")

    now = datetime.now(timezone.utc)
    if _lease_expired(task, now):
        _try_requeue_expired_task(task, now, session)
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task claim lease has expired")

    root = _get_root_task(task, session)
    heartbeat_conditions = [
        AgentTask.id == task_id,
        AgentTask.status == "running",
        AgentTask.claim_token == body.claim_token,
        or_(AgentTask.lease_expires_at.is_(None), AgentTask.lease_expires_at > now),
    ]
    heartbeat_conditions.extend(
        _root_control_claim_conditions(root, now, require_unexpired=False)
    )
    result = session.execute(
        update(AgentTask)
        .where(*heartbeat_conditions)
        .values(
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=body.lease_seconds),
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task claim is no longer active")

    instance = _ensure_instance_owner(task.instance_id, current, session)
    if instance is not None:
        instance.last_seen_at = now
        instance.updated_at = now
        session.add(instance)
    session.commit()
    session.expire_all()
    return _get_task(task_id, session)


@router.post("/{task_id}/complete", response_model=AgentTaskOut)
def complete_task(
    task_id: int,
    body: AgentTaskComplete,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Mark a running task as succeeded, failed, or canceled."""
    _require_agent(current)
    task = _get_task(task_id, session)
    if task.target_member_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="task belongs to another agent")
    if task.status != "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"task is {task.status}, not running")

    now = datetime.now(timezone.utc)
    if task.claim_token is not None:
        if body.claim_token is None and task.attempt > 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="claim_token is required after a task is reclaimed")
        if body.claim_token is not None and body.claim_token != task.claim_token:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task claim token is stale")
        if _lease_expired(task, now):
            _try_requeue_expired_task(task, now, session)
            session.commit()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task claim lease has expired")

    _ensure_result_message_owner(body.result_message_id, current, task, session)
    instance = _ensure_instance_owner(task.instance_id, current, session)

    workflow_status = {
        "succeeded": "submitted",
        "failed": "failed",
        "canceled": "canceled",
    }[body.status]
    completion_conditions = [AgentTask.id == task_id, AgentTask.status == "running"]
    root = _get_root_task(task, session)
    completion_conditions.extend(
        _root_control_claim_conditions(root, now, require_unexpired=False)
    )
    if task.claim_token is not None:
        completion_conditions.extend(
            [
                AgentTask.claim_token == task.claim_token,
                or_(AgentTask.lease_expires_at.is_(None), AgentTask.lease_expires_at > now),
            ]
        )
    else:
        completion_conditions.append(AgentTask.claim_token.is_(None))
    result = session.execute(
        update(AgentTask)
        .where(*completion_conditions)
        .values(
            status=body.status,
            workflow_status=workflow_status,
            claim_token=None,
            lease_expires_at=None,
            result_message_id=body.result_message_id,
            last_error=body.last_error,
            finished_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task claim is no longer active")

    if instance is not None:
        instance.status = "error" if body.status == "failed" else "idle"
        instance.current_task_id = None
        instance.last_error = body.last_error
        instance.updated_at = now
        instance.last_seen_at = now
        session.add(instance)

    session.commit()
    session.expire_all()
    return _get_task(task_id, session)
