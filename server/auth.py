"""API Key authentication dependency."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import Session, select

from server.db import get_session
from server.models import Member


def resolve_member_by_key(api_key: str, session: Session) -> Member | None:
    """Resolve a raw API key to a Member, or return None."""
    return session.exec(
        select(Member).where(Member.api_key == api_key)
    ).first()


def get_current_member(
    request: Request,
    x_api_key: str = Header(...),
    session: Session = Depends(get_session),
) -> Member:
    """Resolve X-API-Key header to a Member, or 401."""
    member = resolve_member_by_key(x_api_key, session)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    if member.disabled_at is not None:
        # Globally disabled (UI #3): the key is valid but the account is turned off.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="member is disabled",
        )
    request.state.member_id = member.id
    return member
