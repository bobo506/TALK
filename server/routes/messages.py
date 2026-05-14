"""Message send and receive routes."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, exists, func, literal, or_
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import REVOKE_WINDOW_SEC, get_session
from server.models import File, Group, GroupMember, Member, Message, MessageCreate, MessageOut, MessageReplyOut, MessageRevokeOut
from server.ws_hub import hub

router = APIRouter(prefix="/api/messages", tags=["messages"])
_REPLY_PREVIEW_LIMIT = 80


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_leading_mentions(text: str | None, member_ids: set[str]) -> tuple[list[str], str | None]:
    """Parse leading @mention blocks and validate them against known members."""
    if not text:
        return [], None

    cursor = 0
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1

    recipients: list[str] = []
    saw_mention = False

    while cursor < len(text) and text[cursor] == "@":
        token_start = cursor + 1
        token_end = token_start
        while token_end < len(text) and not text[token_end].isspace():
            token_end += 1

        member_id = text[token_start:token_end]
        if not member_id or member_id not in member_ids:
            return [], f"@{member_id}"

        recipients.append(member_id)
        saw_mention = True
        cursor = token_end

        while cursor < len(text) and text[cursor].isspace():
            cursor += 1

    if not saw_mention:
        return [], None

    return list(dict.fromkeys(recipients)), None


def _validate_recipient_ids(recipient_ids: Iterable[str] | None, member_ids: set[str]) -> list[str] | None:
    """Normalize explicit recipient ids and reject unknown targets."""
    if recipient_ids is None:
        return None

    normalized = list(dict.fromkeys(recipient_ids))
    invalid = next((member_id for member_id in normalized if member_id not in member_ids), None)
    if invalid is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid recipient: {invalid}",
        )

    return normalized or None


def _resolve_recipients(body: MessageCreate, session: Session, *, allowed_member_ids: set[str] | None = None) -> list[str] | None:
    """Resolve recipients from leading mentions first, then fall back to explicit ids."""
    member_ids = allowed_member_ids if allowed_member_ids is not None else set(session.exec(select(Member.id)).all())
    routing_text = body.content if body.type == "text" else body.caption
    mentioned_ids, invalid_mention = _extract_leading_mentions(routing_text, member_ids)

    if invalid_mention is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid recipient mention: {invalid_mention}",
        )

    if mentioned_ids:
        return mentioned_ids

    return _validate_recipient_ids(body.to, member_ids)


def _is_message_visible_to_member(message: Message, member_id: str) -> bool:
    if message.group_id is not None:
        return message.from_id == member_id
    if message.from_id == member_id or message.to_ids is None:
        return True
    return member_id in message.to_list


def _is_group_member(group_id: str, member_id: str, session: Session) -> bool:
    return session.get(GroupMember, (group_id, member_id)) is not None


def _group_member_ids(group_id: str, session: Session) -> list[str]:
    return list(
        session.exec(
            select(GroupMember.member_id)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.member_id)
        ).all()
    )


def _resolve_group_scope(group_id: str | None, current: Member, session: Session) -> list[str] | None:
    if group_id is None:
        return None

    if session.get(Group, group_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="group_id not found")
    if not _is_group_member(group_id, current.id, session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="current member is not in group")
    return _group_member_ids(group_id, session)


def _json_array_contains(column, member_id: str):
    recipients = func.json_each(column).table_valued("value").alias()
    return exists(
        select(literal(1))
        .select_from(recipients)
        .where(recipients.c.value == member_id)
    )


def _visible_to_member_expr(member_id: str):
    return or_(
        Message.from_id == member_id,
        Message.to_ids.is_(None),
        _json_array_contains(Message.to_ids, member_id),
    )


def _pair_view_expr(member_id: str, other_member_id: str):
    return or_(
        Message.to_ids.is_(None),
        Message.from_id == other_member_id,
        and_(
            Message.from_id == member_id,
            _json_array_contains(Message.to_ids, other_member_id),
        ),
        and_(
            _json_array_contains(Message.to_ids, member_id),
            _json_array_contains(Message.to_ids, other_member_id),
        ),
    )


def _normalize_reply_preview(message: Message) -> str | None:
    source = message.filename or message.content
    if not source:
        return None
    collapsed = " ".join(source.split())
    return collapsed[:_REPLY_PREVIEW_LIMIT] or None


def _build_reply_summary(message: Message) -> MessageReplyOut:
    is_revoked = message.revoked_at is not None
    return MessageReplyOut(
        id=message.id,
        from_id=message.from_id,
        preview=None if is_revoked else _normalize_reply_preview(message),
        type=message.type,
        revoked=is_revoked,
    )


def _resolve_reply_target(
    reply_to_id: int | None,
    current: Member,
    session: Session,
    group_id: str | None,
) -> Message | None:
    if reply_to_id is None:
        return None

    target = session.get(Message, reply_to_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reply_to_not_found")
    if target.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot_reply_to_different_group")
    if target.group_id is not None:
        if not _is_group_member(target.group_id, current.id, session):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot_reply_to_invisible")
    elif not _is_message_visible_to_member(target, current.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot_reply_to_invisible")
    if target.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot_reply_to_revoked")
    return target


def _build_reply_lookup(messages: list[Message], session: Session) -> dict[int, MessageReplyOut]:
    reply_ids = {message.reply_to for message in messages if message.reply_to is not None}
    if not reply_ids:
        return {}

    targets = session.exec(select(Message).where(Message.id.in_(reply_ids))).all()
    return {target.id: _build_reply_summary(target) for target in targets if target.id is not None}


async def create_message(
    body: MessageCreate,
    current: Member,
    session: Session,
) -> MessageOut:
    """Create, persist, and broadcast a message."""
    group_member_ids = _resolve_group_scope(body.group_id, current, session)
    resolved_to = _resolve_recipients(
        body,
        session,
        allowed_member_ids=set(group_member_ids) if group_member_ids is not None else None,
    )
    reply_target = _resolve_reply_target(body.reply_to, current, session, body.group_id)
    file_record = None
    if body.type == "file":
        file_record = session.get(File, body.file_id)
        if file_record is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="file_id does not reference an existing file",
            )

    msg = Message(
        group_id=body.group_id,
        from_id=current.id,
        to_ids=json.dumps(resolved_to) if resolved_to else None,
        type=body.type,
        content=file_record.filename if file_record else body.content,
        file_id=body.file_id,
        reply_to=reply_target.id if reply_target is not None else None,
        caption=body.caption,
        filename=file_record.filename if file_record else None,
        size_bytes=file_record.size_bytes if file_record else None,
        mime=file_record.mime if file_record else None,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)

    out = MessageOut.from_orm_msg(
        msg,
        reply_to=_build_reply_summary(reply_target) if reply_target is not None else None,
    )

    await hub.broadcast(out, targets=group_member_ids)
    return out


async def revoke_message(
    message_id: int,
    current: Member,
    session: Session,
) -> MessageRevokeOut:
    """Mark a message as revoked and broadcast the revoke event."""
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")

    if msg.from_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only sender can revoke message")

    if msg.revoked_at is not None and msg.revoked_by is not None:
        return MessageRevokeOut(
            id=msg.id,
            revoked_at=msg.revoked_at,
            revoked_by=msg.revoked_by,
        )

    created_at = _as_utc(msg.created_at)
    deadline = created_at + timedelta(seconds=REVOKE_WINDOW_SEC)
    if datetime.now(timezone.utc) > deadline:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"revoke window expired after {REVOKE_WINDOW_SEC} seconds",
        )

    msg.revoked_at = datetime.now(timezone.utc)
    msg.revoked_by = current.id
    session.add(msg)
    session.commit()
    session.refresh(msg)

    targets = _group_member_ids(msg.group_id, session) if msg.group_id is not None else None
    await hub.broadcast_revoke(msg, targets=targets)
    return MessageRevokeOut(
        id=msg.id,
        revoked_at=msg.revoked_at,
        revoked_by=msg.revoked_by,
    )


@router.post("", response_model=MessageOut, status_code=201)
async def send_message(
    body: MessageCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Send a message (text or file reference with optional caption)."""
    return await create_message(body, current, session)


@router.post("/{message_id}/revoke", response_model=MessageRevokeOut)
async def revoke_message_route(
    message_id: int,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Revoke a message within the configured revoke window."""
    return await revoke_message(message_id, current, session)


@router.get("", response_model=list[MessageOut])
def get_messages(
    since: int = Query(0, ge=0),
    before: Optional[int] = Query(None, ge=1),
    to: Optional[str] = Query(None),
    q: Optional[str] = Query(None, min_length=1),
    group_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Pull messages.

    - since: return messages with id > since
    - before: return messages with id < before, ordered chronologically
    - visibility: always restricted to what the current member can see
    - to: if provided, further narrow the already-visible set to a member-specific view
    - q: if provided, keyword search across content/caption/filename
    - limit: max number of messages to return
    """
    if since > 0 and before is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="since and before cannot be used together",
        )

    if group_id is not None:
        if session.get(Group, group_id) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="group_id not found")
        if not _is_group_member(group_id, _current.id, session):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="current member is not in group")
        stmt = select(Message).where(Message.group_id == group_id)
    else:
        stmt = select(Message).where(Message.group_id.is_(None)).where(_visible_to_member_expr(_current.id))

    if group_id is None and to and to != _current.id:
        stmt = stmt.where(_pair_view_expr(_current.id, to))

    if before is not None:
        stmt = stmt.where(Message.id < before).order_by(Message.id.desc()).limit(limit)  # type: ignore[operator]
    elif since > 0:
        stmt = stmt.where(Message.id > since).order_by(Message.id).limit(limit)  # type: ignore[operator]
    else:
        stmt = stmt.order_by(Message.id.desc()).limit(limit)  # type: ignore[operator]

    if q:
        query_text = q.strip()
        if query_text:
            stmt = stmt.where(Message.revoked_at.is_(None)).where(
                or_(
                    Message.content.contains(query_text),
                    Message.caption.contains(query_text),
                    Message.filename.contains(query_text),
                )
            )

    results = session.exec(stmt).all()
    if before is not None or since == 0:
        results = list(reversed(results))

    reply_lookup = _build_reply_lookup(results, session)
    return [
        MessageOut.from_orm_msg(message, reply_to=reply_lookup.get(message.reply_to))
        for message in results
    ]
