"""Member registration, identity, and listing."""

from __future__ import annotations

from sqlalchemy import func
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import Member, MemberCreate, MemberOut

router = APIRouter(prefix="/api/members", tags=["members"])
setup_router = APIRouter(tags=["setup"])


def _derive_kind(member_id: str) -> str:
    if member_id.startswith("human:"):
        return "human"
    if member_id.startswith("agent:"):
        return "agent"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="id must start with 'human:' or 'agent:'",
    )


def count_human_members(session: Session) -> int:
    return int(
        session.exec(
            select(func.count()).select_from(Member).where(Member.kind == "human")
        ).one()
    )


def needs_human_setup(session: Session) -> bool:
    return count_human_members(session) == 0


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    body: MemberCreate,
    response: Response,
    session: Session = Depends(get_session),
):
    """Register a new member, with idempotent self-registration for agents."""
    kind = _derive_kind(body.id)
    existing = session.get(Member, body.id)

    if existing is not None:
        if kind != "agent":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Member '{body.id}' already exists",
            )
        if existing.api_key != body.api_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent '{body.id}' already exists with a different API key",
            )

        existing.display_name = body.display_name
        existing.poll_hint = body.poll_hint
        session.add(existing)
        session.commit()
        session.refresh(existing)
        response.status_code = status.HTTP_200_OK
        return existing

    existing_key = session.exec(
        select(Member).where(Member.api_key == body.api_key)
    ).first()
    if existing_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"API key already in use by '{existing_key.id}'",
        )

    member = Member(
        id=body.id,
        kind=kind,
        display_name=body.display_name,
        api_key=body.api_key,
        poll_hint=body.poll_hint,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


@router.get("", response_model=list[MemberOut])
def list_members(
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List all registered members (for UI @ autocomplete)."""
    return session.exec(select(Member)).all()


@router.get("/me", response_model=MemberOut)
def get_me(current: Member = Depends(get_current_member)):
    """Return the member resolved from the current API key."""
    return current


@setup_router.get("/api/setup/status", response_model=dict[str, bool])
def get_setup_status(session: Session = Depends(get_session)):
    """Report whether the instance still needs its first human admin."""
    return {"needs_setup": needs_human_setup(session)}
