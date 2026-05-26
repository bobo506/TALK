"""Discussion session APIs for recorded multi-Agent coordination."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import (
    DiscussionSession,
    DiscussionSessionCreate,
    DiscussionSessionOut,
    DiscussionSessionUpdate,
    DiscussionTurn,
    DiscussionTurnCreate,
    DiscussionTurnOut,
    Group,
    GroupMember,
    Member,
    Message,
)

router = APIRouter(prefix="/api/discussions", tags=["discussions"])


def _require_group_member(group_id: str, member_id: str, session: Session) -> None:
    if session.get(Group, group_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="group_id not found")
    if session.get(GroupMember, (group_id, member_id)) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="current member is not in group")


def _require_group_members(group_id: str, member_ids: list[str], session: Session) -> None:
    for member_id in member_ids:
        member = session.get(Member, member_id)
        if member is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"participant not found: {member_id}")
        if session.get(GroupMember, (group_id, member_id)) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"participant is not in group: {member_id}",
            )


def _require_scope_message(group_id: str, message_id: int | None, session: Session) -> None:
    if message_id is None:
        return
    message = session.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="root_message_id not found")
    if message.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="root message is not in discussion group")


def _get_visible_discussion(discussion_id: int, current: Member, session: Session) -> DiscussionSession:
    discussion = session.get(DiscussionSession, discussion_id)
    if discussion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="discussion not found")
    _require_group_member(discussion.group_id, current.id, session)
    return discussion


def _turn_out(turn: DiscussionTurn) -> DiscussionTurnOut:
    return DiscussionTurnOut(
        id=int(turn.id or 0),
        session_id=turn.session_id,
        turn_index=turn.turn_index,
        message_id=turn.message_id,
        speaker_id=turn.speaker_id,
        target_member_id=turn.target_member_id,
        stance=turn.stance,
        round_index=turn.round_index,
        created_at=turn.created_at,
    )


def _next_turn_index(discussion_id: int, session: Session) -> int:
    current_max = session.exec(
        select(func.max(DiscussionTurn.turn_index)).where(DiscussionTurn.session_id == discussion_id)
    ).one()
    return int(current_max or 0) + 1


@router.post("", response_model=DiscussionSessionOut, status_code=status.HTTP_201_CREATED)
def create_discussion(
    body: DiscussionSessionCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Create a recorded discussion session scoped to one Group Hall."""
    _require_group_member(body.group_id, current.id, session)
    _require_group_members(body.group_id, body.participant_ids, session)
    scope_members = [member_id for member_id in [body.requester_id, body.assignee_id] if member_id is not None]
    if scope_members:
        _require_group_members(body.group_id, scope_members, session)
    _require_scope_message(body.group_id, body.root_message_id, session)

    now = datetime.now(timezone.utc)
    discussion = DiscussionSession(
        group_id=body.group_id,
        created_by=current.id,
        topic=body.topic,
        participant_ids=json.dumps(body.participant_ids),
        root_message_id=body.root_message_id,
        requester_id=body.requester_id,
        assignee_id=body.assignee_id,
        scope_text=body.scope_text,
        status="active",
        max_rounds=body.max_rounds,
        created_at=now,
        updated_at=now,
    )
    session.add(discussion)
    session.commit()
    session.refresh(discussion)
    return DiscussionSessionOut.from_orm_session(discussion)


@router.get("", response_model=list[DiscussionSessionOut])
def list_discussions(
    group_id: str | None = Query(None),
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List discussions visible to the current member."""
    stmt = select(DiscussionSession)
    if group_id is not None:
        _require_group_member(group_id, current.id, session)
        stmt = stmt.where(DiscussionSession.group_id == group_id)
    else:
        visible_group_ids = session.exec(
            select(GroupMember.group_id).where(GroupMember.member_id == current.id)
        ).all()
        if not visible_group_ids:
            return []
        stmt = stmt.where(DiscussionSession.group_id.in_(visible_group_ids))

    discussions = session.exec(stmt.order_by(DiscussionSession.updated_at.desc())).all()
    return [DiscussionSessionOut.from_orm_session(item) for item in discussions]


@router.get("/{discussion_id}", response_model=DiscussionSessionOut)
def get_discussion(
    discussion_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Read one discussion session visible to the current member."""
    return DiscussionSessionOut.from_orm_session(_get_visible_discussion(discussion_id, current, session))


@router.patch("/{discussion_id}", response_model=DiscussionSessionOut)
def update_discussion(
    discussion_id: int,
    body: DiscussionSessionUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Update a discussion session status."""
    discussion = _get_visible_discussion(discussion_id, current, session)
    now = datetime.now(timezone.utc)
    discussion.status = body.status
    discussion.updated_at = now
    session.add(discussion)
    session.commit()
    session.refresh(discussion)
    return DiscussionSessionOut.from_orm_session(discussion)


@router.post("/{discussion_id}/turns", response_model=DiscussionTurnOut, status_code=status.HTTP_201_CREATED)
def append_discussion_turn(
    discussion_id: int,
    body: DiscussionTurnCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Append one ordered turn that references a committed Hall message."""
    discussion = _get_visible_discussion(discussion_id, current, session)
    message = session.get(Message, body.message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message_id not found")
    if message.group_id != discussion.group_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message is not in discussion group")
    if message.from_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="turn message must belong to current member")
    if body.target_member_id is not None:
        _require_group_members(discussion.group_id, [body.target_member_id], session)

    now = datetime.now(timezone.utc)
    turn = DiscussionTurn(
        session_id=int(discussion.id or 0),
        turn_index=_next_turn_index(int(discussion.id or 0), session),
        message_id=body.message_id,
        speaker_id=message.from_id,
        target_member_id=body.target_member_id,
        stance=body.stance,
        round_index=body.round_index,
        created_at=now,
    )
    discussion.updated_at = now
    session.add(turn)
    session.add(discussion)
    session.commit()
    session.refresh(turn)
    return _turn_out(turn)


@router.get("/{discussion_id}/turns", response_model=list[DiscussionTurnOut])
def list_discussion_turns(
    discussion_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Return ordered turns for one visible discussion session."""
    _get_visible_discussion(discussion_id, current, session)
    turns = session.exec(
        select(DiscussionTurn)
        .where(DiscussionTurn.session_id == discussion_id)
        .order_by(DiscussionTurn.turn_index.asc(), DiscussionTurn.message_id.asc())
    ).all()
    return [_turn_out(turn) for turn in turns]
