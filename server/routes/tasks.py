"""Agent task queue and scheduling foundation APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

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
    Group,
    GroupMember,
    Member,
    Message,
    Project,
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


def _touch_task(task: AgentTask, now: datetime) -> None:
    task.updated_at = now


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
    return task


def _create_task_from_schedule(schedule: AgentTaskSchedule, now: datetime, session: Session) -> AgentTask:
    return _create_task_with_hall(
        schedule_id=schedule.id,
        project_id=None,
        target_member_id=schedule.target_member_id,
        created_by=schedule.created_by,
        content=schedule.content,
        title=schedule.title,
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
    _ensure_project_exists(body.project_id, session)
    now = datetime.now(timezone.utc)
    task = _create_task_with_hall(
        target_member_id=body.target_member_id,
        created_by=current.id,
        content=body.content,
        title=body.title,
        project_id=body.project_id,
        schedule_id=None,
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


@router.post("/{task_id}/request-clarification", response_model=AgentTaskOut)
def request_task_clarification(
    task_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Record that the assignee has asked a question in the Task Hall."""
    task = _get_task(task_id, session)
    if task.target_member_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only the task assignee can request clarification")
    if task.workflow_status == "clarification_requested":
        return task
    if task.workflow_status != "assigned":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not assigned",
        )
    return _update_workflow_status(task, "clarification_requested", datetime.now(timezone.utc), session)


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
    if task.workflow_status == "accepted":
        return task
    if task.workflow_status not in {"assigned", "clarification_requested"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not assignable",
        )
    return _update_workflow_status(task, "accepted", datetime.now(timezone.utc), session)


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
            detail="only unclaimed tasks can be canceled; running cancellation requires runner lease support",
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
    if task.workflow_status == "clarification_requested":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task is waiting for clarification before acceptance")
    if task.workflow_status not in {"assigned", "accepted"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task workflow is {task.workflow_status}, not ready to start",
        )

    now = datetime.now(timezone.utc)
    task.status = "running"
    task.workflow_status = "in_progress"
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

    _ensure_result_message_owner(body.result_message_id, current, task, session)
    instance = _ensure_instance_owner(task.instance_id, current, session)

    now = datetime.now(timezone.utc)
    task.status = body.status
    task.workflow_status = {
        "succeeded": "submitted",
        "failed": "failed",
        "canceled": "canceled",
    }[body.status]
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
