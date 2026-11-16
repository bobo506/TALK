"""Local, no-key desktop shutdown control."""
import ipaddress
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

import server.db as db
from server.auth import OPERATOR_ID, is_trusted_host, resolve_transport_member
from server.db import get_session

router = APIRouter()


@router.post('/api/local/shutdown', status_code=202)
def shutdown(request: Request, session: Session = Depends(get_session)):
    host = request.client.host if request.client else None
    try:
        loopback = host == 'testclient' or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    trusted_host = '127.0.0.1' if host == 'testclient' else host
    if (not loopback or db.AUTH_MODE != 'trusted' or not is_trusted_host(trusted_host)
            or 'x-api-key' in request.headers):
        raise HTTPException(403, 'forbidden')
    member = resolve_transport_member(None, trusted_host, session)
    if member is None or member.id != OPERATOR_ID or member.kind != 'human' or member.disabled_at is not None:
        raise HTTPException(403, 'forbidden')
    control = os.environ.get('TALK_API_CONTROL_FILE')
    if not control:
        raise HTTPException(409, 'shutdown_unavailable')
    try:
        Path(control).write_text('stop', encoding='utf-8')
    except OSError:
        raise HTTPException(409, 'shutdown_unavailable') from None
    return {'status': 'stopping'}
