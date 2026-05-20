"""Agent task queue and scheduling foundation APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import (
    AgentInstance,
    AgentTask,
    AgentTaskClaim,
    AgentTaskComplete,
    AgentTaskCreate,
    AgentTaskOut,
    AgentTaskSchedule,
    AgentTaskScheduleCreate,
    AgentTaskScheduleOut,
    AgentTaskScheduleRunOut,
    AgentTaskScheduleUpdate,
    Member,
    Message,
    _SCHEDULE_STATUSES,
    _TASK_STATUSES,
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


def _ensure_instance_owner(instance_id: str | None, current: Member, session: Session) -> AgentInstance | None:
    if instance_id is None:
        return None

    instance = session.get(AgentInstance, instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="instance_id not found")
    if instance.member_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="instance belongs to another member")
    return instance


def _ensure_result_message_owner(message_id: int | None, current: Member, session: Session) -> None:
    if message_id is None:
        return

    message = session.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="result_message_id not found")
    if message.from_id != current.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="result_message_id must belong to task agent")


def _touch_task(task: AgentTask, now: datetime) -> None:
    task.updated_at = now


def _touch_schedule(schedule: AgentTaskSchedule, now: datetime) -> None:
    schedule.updated_at = now


def _require_schedule_manager(schedule: AgentTaskSchedule, current: Member) -> None:
    if current.kind == "human" or schedule.created_by == current.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only human members or schedule creators can update schedules")


def _create_task_from_schedule(schedule: AgentTaskSchedule, now: datetime) -> AgentTask:
    return AgentTask(
        schedule_id=schedule.id,
        target_member_id=schedule.target_member_id,
        created_by=schedule.created_by,
        content=schedule.content,
        title=schedule.title,
        status="queued",
        created_at=now,
        updated_at=now,
    )


@router.post("", response_model=AgentTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    body: AgentTaskCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Create a queued task for an Agent member."""
    _ensure_target_agent(body.target_member_id, session)
    now = datetime.now(timezone.utc)
    task = AgentTask(
        target_member_id=body.target_member_id,
        created_by=current.id,
        content=body.content,
        title=body.title,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.get("", response_model=list[AgentTaskOut])
def list_tasks(
    target_member_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
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
    return session.exec(stmt.order_by(AgentTask.created_at.desc())).all()  # type: ignore[union-attr]


@router.post("/schedules", response_model=AgentTaskScheduleOut, status_code=status.HTTP_201_CREATED)
def create_task_schedule(
    body: AgentTaskScheduleCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Create a one-off or interval task schedule."""
    _ensure_target_agent(body.target_member_id, session)
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
        task = _create_task_from_schedule(schedule, now)
        session.add(task)
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


@router.post("/{task_id}/claim", response_model=AgentTaskOut)
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
    if task.status == "running" and task.claimed_by == current.id and task.instance_id == body.instance_id:
        return task
    if task.status != "queued":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"task is already {task.status}")

    now = datetime.now(timezone.utc)
    task.status = "running"
    task.claimed_by = current.id
    task.instance_id = body.instance_id
    task.claimed_at = now
    _touch_task(task, now)
    session.add(task)
    session.flush()

    if instance is not None:
        instance.status = "busy"
        instance.current_task_id = str(task.id)
        instance.last_error = None
        instance.updated_at = now
        instance.last_seen_at = now
        session.add(instance)

    session.commit()
    session.refresh(task)
    return task


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

    _ensure_result_message_owner(body.result_message_id, current, session)
    instance = _ensure_instance_owner(task.instance_id, current, session)

    now = datetime.now(timezone.utc)
    task.status = body.status
    task.result_message_id = body.result_message_id
    task.last_error = body.last_error
    task.finished_at = now
    _touch_task(task, now)

    if instance is not None:
        instance.status = "error" if body.status == "failed" else "idle"
        instance.current_task_id = None
        instance.last_error = body.last_error
        instance.updated_at = now
        instance.last_seen_at = now
        session.add(instance)

    session.add(task)
    session.commit()
    session.refresh(task)
    return task
