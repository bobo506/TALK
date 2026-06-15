"""Group and Hall room APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import Group, GroupCreate, GroupMember, GroupMemberOut, GroupMemberUpdate, GroupOut, GroupUpdate, Member, Project

router = APIRouter(prefix="/api/groups", tags=["groups"])


def _require_human(current: Member) -> None:
    if current.kind != "human":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only human members can manage groups")


def _get_group(group_id: str, session: Session) -> Group:
    group = session.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group not found")
    return group


def _get_member(member_id: str, session: Session) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"member not found: {member_id}")
    return member


def _ensure_project_exists(project_id: str, session: Session) -> None:
    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"project not found: {project_id}")


def _is_group_member(group_id: str, member_id: str, session: Session) -> bool:
    return session.get(GroupMember, (group_id, member_id)) is not None


def _ensure_can_view_group(group_id: str, current: Member, session: Session) -> None:
    if current.kind == "human":
        return
    if not _is_group_member(group_id, current.id, session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="group is not visible to this member")


def _group_out(group: Group, session: Session) -> GroupOut:
    members = session.exec(
        select(GroupMember)
        .where(GroupMember.group_id == group.id)
        .order_by(GroupMember.created_at, GroupMember.member_id)
    ).all()
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        project_id=group.project_id,
        created_by=group.created_by,
        created_at=group.created_at,
        updated_at=group.updated_at,
        members=[
            GroupMemberOut(member_id=member.member_id, role=member.role, created_at=member.created_at)
            for member in members
        ],
    )


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    body: GroupCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Create a discussion Group and its initial Hall membership."""
    group_id = body.id or f"group:{uuid4().hex[:12]}"
    if session.get(Group, group_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="group id already exists")

    if body.project_id is not None:
        _ensure_project_exists(body.project_id, session)

    member_ids = list(dict.fromkeys([current.id, *body.member_ids]))
    for member_id in member_ids:
        _get_member(member_id, session)

    now = datetime.now(timezone.utc)
    group = Group(
        id=group_id,
        name=body.name,
        description=body.description,
        project_id=body.project_id,
        created_by=current.id,
        created_at=now,
        updated_at=now,
    )
    session.add(group)
    for member_id in member_ids:
        session.add(
            GroupMember(
                group_id=group_id,
                member_id=member_id,
                role="owner" if member_id == current.id else "member",
                created_at=now,
            )
        )
    session.commit()
    session.refresh(group)
    return _group_out(group, session)


@router.get("", response_model=list[GroupOut])
def list_groups(
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List Groups visible to the current member."""
    stmt = select(Group)
    if current.kind != "human":
        stmt = stmt.join(GroupMember, GroupMember.group_id == Group.id).where(GroupMember.member_id == current.id)
    groups = session.exec(stmt.order_by(Group.created_at.desc())).all()
    return [_group_out(group, session) for group in groups]


@router.get("/{group_id}", response_model=GroupOut)
def get_group(
    group_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Return one Group if it is visible to the current member."""
    group = _get_group(group_id, session)
    _ensure_can_view_group(group_id, current, session)
    return _group_out(group, session)


@router.patch("/{group_id}", response_model=GroupOut)
def update_group(
    group_id: str,
    body: GroupUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Update Group display metadata."""
    _require_human(current)
    group = _get_group(group_id, session)
    group.name = body.name
    group.description = body.description
    group.updated_at = datetime.now(timezone.utc)
    session.add(group)
    session.commit()
    session.refresh(group)
    return _group_out(group, session)


@router.put("/{group_id}/members/{member_id}", response_model=GroupOut)
def upsert_group_member(
    group_id: str,
    member_id: str,
    body: GroupMemberUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Add a member to a Group or update that member's role."""
    _require_human(current)
    group = _get_group(group_id, session)
    _get_member(member_id, session)
    now = datetime.now(timezone.utc)

    membership = session.get(GroupMember, (group_id, member_id))
    if membership is None:
        membership = GroupMember(group_id=group_id, member_id=member_id, role=body.role, created_at=now)
    else:
        membership.role = body.role
    group.updated_at = now
    session.add(membership)
    session.add(group)
    session.commit()
    session.refresh(group)
    return _group_out(group, session)


@router.delete("/{group_id}/members/{member_id}", response_model=GroupOut)
def remove_group_member(
    group_id: str,
    member_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Remove a member from a Group."""
    _require_human(current)
    group = _get_group(group_id, session)
    membership = session.get(GroupMember, (group_id, member_id))
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group member not found")

    group.updated_at = datetime.now(timezone.utc)
    session.delete(membership)
    session.add(group)
    session.commit()
    session.refresh(group)
    return _group_out(group, session)
