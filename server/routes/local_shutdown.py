"""Local, no-key desktop shutdown control."""
import ipaddress
import os
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

import server.db as db
from server.auth import OPERATOR_ID, is_trusted_host, resolve_transport_member
from server.db import get_session
from server.models import AgentTask

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
    task_ids = session.exec(select(AgentTask.id).where(AgentTask.status == 'running').order_by(AgentTask.id).limit(10)).all()
    if task_ids:
        raise HTTPException(409, {'code': 'tasks_running', 'task_ids': task_ids,
                                  'message': '有任务执行中，请等待结束后再退出服务'})
    control = os.environ.get('TALK_API_CONTROL_FILE')
    if not control:
        raise HTTPException(409, 'shutdown_unavailable')
    cfg = os.environ.get('TALK_RUNTIME_CONFIG')
    if cfg:
        try:
            options = {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
            process = subprocess.Popen(
                [sys.executable, '-B', '-X', 'utf8', '-m', 'scripts.talk_runtime',
                 'stop', '--config', cfg, '--apply', '--wait'],
                cwd=Path(__file__).resolve().parents[2], close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        except OSError:
            raise HTTPException(409, 'shutdown_unavailable') from None

        def finish_shutdown():
            # Runtime needs its API while it drains role hosts.
            if process.wait() != 0:
                return
            try:
                Path(control).write_text('stop', encoding='utf-8')
            except OSError:
                pass

        threading.Thread(target=finish_shutdown, daemon=True).start()
        return {'status': 'stopping', 'runtime': True}
    try:
        Path(control).write_text('stop', encoding='utf-8')
    except OSError:
        raise HTTPException(409, 'shutdown_unavailable') from None
    return {'status': 'stopping', 'runtime': False}
