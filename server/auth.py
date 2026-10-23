"""API Key authentication dependency."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import Session, select

from server.db import get_session
from server.models import Member, ProjectAgent, ProjectRole


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
