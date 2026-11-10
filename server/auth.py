"""API key and local-trust authentication dependency."""

from __future__ import annotations

import ipaddress
import secrets

from sqlalchemy.exc import IntegrityError
import server.db as db
from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import Session, select

from server.db import get_session
from server.models import Member, ProjectAgent, ProjectRole


OPERATOR_ID = "human:operator"


def is_trusted_host(host: str | None) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (("loopback" in db.TRUSTED_NETWORKS and address.is_loopback)
            or ("private" in db.TRUSTED_NETWORKS and address.is_private))


def ensure_local_operator(session: Session) -> Member:
    member = session.get(Member, OPERATOR_ID)
    if member is not None:
        return member
    member = Member(id=OPERATOR_ID, display_name="本机操作员", kind="human",
                    api_key=secrets.token_urlsafe(48))
    session.add(member)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        member = session.get(Member, OPERATOR_ID)
        if member is None:
            raise
        return member
    session.refresh(member)
    return member


def resolve_transport_member(token: str | None, host: str | None, session: Session) -> Member | None:
    if db.AUTH_MODE == "trusted" and not is_trusted_host(host):
        return None
    if token:
        return resolve_member_by_key(token, session)
    if token is None and db.AUTH_MODE == "trusted":
        return ensure_local_operator(session)
    return None


def resolve_member_by_key(api_key: str, session: Session) -> Member | None:
    """Resolve a raw API key to a Member, or return None."""
    return session.exec(
        select(Member).where(Member.api_key == api_key)
    ).first()


def get_current_member(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    session: Session = Depends(get_session),
) -> Member:
    """Authenticate the source and key, preserving the missing-header contract."""
    if db.AUTH_MODE == "key" and x_api_key is None:
        raise HTTPException(status_code=422, detail="X-API-Key header required")
    member = resolve_transport_member(x_api_key, request.client.host if request.client else None, session)
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
    request.state.auth_database_file = session.get_bind().url.database
    # A matched path is not proof that its member_id is a TALK role. Only this
    # request's authenticated DB may establish diagnostic target identity.
    request.state.backend_member_id = None
    try:
        from server.db import CONFIG
        from bridges.backend_diagnostics import settings
        value = settings(CONFIG, database_file=request.state.auth_database_file)
        project_id = request.path_params.get("project_id")
        target_id = request.path_params.get("member_id")
        if (value is not None and project_id in value["projects"] and isinstance(target_id, str)
                and (session.get(ProjectRole, (project_id, target_id)) is not None
                    or session.get(ProjectAgent, (project_id, target_id)) is not None)):
            request.state.backend_member_id = target_id
    except Exception:
        # A diagnostic lookup cannot change the authentication decision.
        pass
    return member
