"""Agent task queue and scheduling foundation APIs."""

from __future__ import annotations

from datetime import datetime, timezone

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
    Member,
    Message,
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
