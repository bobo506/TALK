"""Agent runtime instance status APIs."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import AgentInstance, AgentInstanceOut, AgentInstanceUpdate, Member

router = APIRouter(prefix="/api/instances", tags=["instances"])


def _require_agent(current: Member) -> None:
    if current.kind != "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only agent members can report instance status",
        )


@router.put("/{instance_id}", response_model=AgentInstanceOut)
def upsert_instance_status(
    instance_id: str,
    body: AgentInstanceUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Create or update the current Agent's runtime instance status."""
    _require_agent(current)
    now = datetime.now(timezone.utc)
    existing = session.get(AgentInstance, instance_id)

    if existing is not None and existing.member_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="instance belongs to another member",
        )

    instance = existing or AgentInstance(
        id=instance_id,
        member_id=current.id,
        runtime=body.runtime,
        status=body.status,
        created_at=now,
    )
    instance.runtime = body.runtime
    instance.status = body.status
    instance.host = body.host
    instance.pid = body.pid
    instance.current_task_id = body.current_task_id
    instance.last_error = body.last_error
    instance.updated_at = now
    instance.last_seen_at = now

    session.add(instance)
    session.commit()
    session.refresh(instance)
    return instance


@router.get("", response_model=list[AgentInstanceOut])
def list_instances(
    member_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List Agent runtime instances visible to any authenticated member."""
    stmt = select(AgentInstance)
    if member_id:
        stmt = stmt.where(AgentInstance.member_id == member_id)
    if status_filter:
        stmt = stmt.where(AgentInstance.status == status_filter.strip().lower())
    return session.exec(stmt.order_by(AgentInstance.updated_at.desc())).all()  # type: ignore[union-attr]
