"""Create and bind a local workspace without provisioning roles."""
from __future__ import annotations

import json
import ipaddress
import ntpath
import os
import re
import socket
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from server import local_runtime
from server.auth import get_current_member
from server.db import begin_immediate_write, get_session
from server.models import Member, Project, ProjectAgent
from server.role_provision_requests import enable_host_config, host_config_projection

router = APIRouter(prefix="/api/local/workspaces", tags=["local-workspaces"])
_lock = threading.Lock()
_picker_lock = threading.Lock()

# Fixed script only. Client input is passed through the environment, never code.
_PICKER_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
if (-not [Environment]::UserInteractive -or [Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) { exit 12 }
Add-Type -AssemblyName System.Windows.Forms
if (-not [System.Windows.Forms.SystemInformation]::UserInteractive) { exit 12 }
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$owner = $null
try {
    $owner = New-Object System.Windows.Forms.Form
    $owner.TopMost = $true
    $owner.ShowInTaskbar = $false
    $owner.FormBorderStyle = 'None'
    $owner.StartPosition = 'CenterScreen'
    $owner.Width = 1
    $owner.Height = 1
    $owner.Opacity = 0
    if ($env:TALK_PICKER_INITIAL_DIR) { $dialog.SelectedPath = $env:TALK_PICKER_INITIAL_DIR }
    $owner.Show()
    $owner.Activate()
    [System.Windows.Forms.Application]::DoEvents()
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        [Console]::Out.Write($dialog.SelectedPath)
    }
} finally {
    if ($owner) { $owner.Close(); $owner.Dispose() }
    $dialog.Dispose()
}
'''


def _picker_path_valid(value):
    return (isinstance(value, str) and 0 < len(value) <= 32767 and '\0' not in value
            and ntpath.isabs(value) and bool(re.match(r'^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$))', value)))


def _picker_windows():
    return os.name == 'nt'


@router.post('/pick-directory')
def pick_directory(request: Request, body: object = Body(default=None),
                   current: Member = Depends(get_current_member)):
    if current.kind != 'human':
        raise HTTPException(403, 'human_required')
    try:
        loopback = ipaddress.ip_address(request.client.host if request.client else '').is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise HTTPException(403, 'workspace_picker_unavailable')
    if body is None:
        body = {}
    if not isinstance(body, dict) or set(body) - {'initial_dir'}:
        raise HTTPException(422, 'workspace_picker_input_invalid')
    initial = body.get('initial_dir')
    if 'initial_dir' in body and not _picker_path_valid(initial):
        raise HTTPException(422, 'workspace_picker_input_invalid')
    if not _picker_windows():
        raise HTTPException(503, 'workspace_picker_unavailable')
    if not _picker_lock.acquire(blocking=False):
        raise HTTPException(409, 'workspace_picker_busy')
    try:
        # Keep runtime credentials out of the dialog subprocess environment.
        safe_names = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT',
                      'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA',
                      'HOMEDRIVE', 'HOMEPATH', 'SYSTEMDRIVE', 'PSMODULEPATH'}
        env = {name: value for name, value in os.environ.items() if name.upper() in safe_names}
        env['TALK_PICKER_INITIAL_DIR'] = initial or ''
        try:
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-STA',
                                     '-Command', _PICKER_SCRIPT], env=env, capture_output=True,
                                    timeout=120, check=False)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, 'workspace_picker_timeout') from None
        except OSError:
            raise HTTPException(503, 'workspace_picker_unavailable') from None
        if result.returncode == 12:
            raise HTTPException(503, 'workspace_picker_unavailable')
        if result.returncode:
            raise HTTPException(500, 'workspace_picker_failed')
        try:
            path = result.stdout.decode('utf-8')
        except (UnicodeError, AttributeError):
            raise HTTPException(500, 'workspace_picker_failed') from None
        if path and not _picker_path_valid(path):
            raise HTTPException(500, 'workspace_picker_failed')
        return {'path': path or None}
    finally:
        _picker_lock.release()


class WorkspaceEnsure(BaseModel):
    project_root: str
    display_name: str | None = None


class WorkspaceJoin(BaseModel):
    project_id: str


@router.post("/join")
def join_workspace(body: WorkspaceJoin, current: Member = Depends(get_current_member),
                   session: Session = Depends(get_session)):
    if current.kind != "agent":
        raise HTTPException(403, "join_requires_agent")
    member_id = current.id
    # Serialize the existence checks and insert across SQLite connections.
    begin_immediate_write(session)
    if session.get(Project, body.project_id) is None:
        raise HTTPException(404, "project_not_found")
    if session.get(ProjectAgent, (body.project_id, member_id)) is not None:
        return {"project_id": body.project_id, "member_id": member_id, "joined": True, "already": True}
    session.add(ProjectAgent(project_id=body.project_id, member_id=member_id))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        if session.get(ProjectAgent, (body.project_id, member_id)) is None:
            raise
        return {"project_id": body.project_id, "member_id": member_id, "joined": True, "already": True}
    return {"project_id": body.project_id, "member_id": member_id, "joined": True, "already": False}


def _create_file(path: Path, contents: str, created: list[Path]) -> None:
    # Exclusive creation preserves all pre-existing files and closes races with other writers.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    created.append(path)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(contents)


def _root(value: str) -> Path:
    try:
        path = Path(value).expanduser().resolve()
        if not value.strip() or not path.is_dir() or path == Path(path.anchor) or path == Path.home().resolve():
            raise ValueError
        return path
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(422, "project_root_invalid")


def _existing_project(root: Path, session: Session):
    identity = os.path.normcase(str(root))
    project = None
    for existing in session.exec(select(Project)).all():
        if not existing.project_root_path:
            continue
        try:
            existing_root = Path(existing.project_root_path).expanduser().resolve()
            same = os.path.samefile(root, existing_root)
        except (OSError, RuntimeError, ValueError):
            continue
        if same:
            if project is not None or os.path.normcase(str(existing_root)) != identity:
                raise HTTPException(409, "workspace_duplicate")
            project = existing
    return project


@router.post("/ensure")
def ensure_workspace(body: WorkspaceEnsure, current: Member = Depends(get_current_member),
                     session: Session = Depends(get_session)):
    if current.kind != "human":
        raise HTTPException(403, "human_required")
    with _lock:
        root = _root(body.project_root)
        _existing_project(root, session)
        engine = session.get_bind()
        try:
            template = local_runtime.configured_runtime(engine)
            if not template:
                raise ValueError
            config = dict(template[1])
            if not engine.url.database or engine.url.database == ":memory:":
                raise ValueError
            database = str(Path(engine.url.database).resolve())
        except Exception as exc:
            raise HTTPException(503, "runtime_template_unavailable") from exc
        created = []
        try:
            # A connection-owned transaction encloses the host helper's Session.commit().
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with Session(bind=connection) as work:
                        begin_immediate_write(work)
                        project = _existing_project(root, work)
                        marker = root / ".talk" / "project.yaml"
                        metadata = None
                        if marker.exists():
                            metadata = yaml.safe_load(marker.read_text(encoding="utf-8"))
                            if not isinstance(metadata, dict) or not project or metadata.get("project_id") != project.project_id:
                                raise HTTPException(409, "workspace_already_bound")
                        if project is None:
                            now = datetime.now(timezone.utc)
                            project = Project(project_id="prj_" + uuid4().hex[:12],
                                              display_name=(body.display_name or root.name),
                                              project_root_path=str(root), maintainer_member_id=current.id,
                                              created_at=now, last_seen_at=now)
                            work.add(project)
                            work.flush()
                        project_id, name = project.project_id, project.display_name
                        projection = host_config_projection(project_id, work)
                        if not projection["enabled"]:
                            enable_host_config(project_id, host_label=socket.gethostname(),
                                               expected_version=projection["config_version"],
                                               lease_seconds=None, max_active_leases=None, max_attempts=None,
                                               caller=current, session=work)
                        home = Path.home()
                        config_path = home / ".talk" / "runtimes" / project_id / "runtime.json"
                        config.update(project_id=project_id, project_root=str(root),
                                      host=config.get("host") or socket.gethostname(),
                                      state_dir=str(home / ".talk" / "role-service-host" / "projects" / project_id),
                                      key_root=str(home / ".talk" / "keys" / project_id),
                                      hosts=[], provision_worker=True)
                        config_path.parent.mkdir(parents=True, exist_ok=True)
                        if not config_path.exists():
                            _create_file(config_path, json.dumps(config, ensure_ascii=False, indent=2), created)
                        else:
                            existing = json.loads(config_path.read_text(encoding="utf-8"))
                            if existing.get("project_id") != project_id or Path(existing.get("project_root", "")).resolve() != root:
                                raise HTTPException(409, "workspace_runtime_conflict")
                        marker.parent.mkdir(parents=True, exist_ok=True)
                        if metadata is None:
                            metadata = {"version": 1, "project_id": project_id, "display_name": name,
                                        "description": project.description, "talk_server": config.get("base_url"),
                                        "created_at": project.created_at.isoformat(), "maintainer": project.maintainer_member_id}
                            _create_file(marker, yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False), created)
                        pointer = marker.parent / "runtime.local.json"
                        pointer_data = {"schema": "talk-local-runtime-1", "database_file": database,
                                        "config_file": str(config_path.resolve())}
                        if not pointer.exists():
                            _create_file(pointer, json.dumps(pointer_data, ensure_ascii=False, indent=2), created)
                        else:
                            existing = json.loads(pointer.read_text(encoding="utf-8"))
                            if existing != pointer_data:
                                raise HTTPException(409, "workspace_runtime_conflict")
                        work.flush()
                    transaction.commit()
                except BaseException:
                    transaction.rollback()
                    raise
        except BaseException as exc:
            for path in reversed(created):
                try:
                    path.unlink()
                except OSError:
                    pass
            if isinstance(exc, OSError):
                raise HTTPException(500, "workspace_write_failed") from exc
            raise
        try:
            state = local_runtime.ensure_local_runtime(engine, project_id)
        except Exception as exc:
            raise HTTPException(503, {"code": "local_runtime_unavailable", "runtime_state": "disabled",
                                      "project_id": project_id, "message": "项目和绑定已写入，可重试"}) from exc
        return {"project_id": project_id, "display_name": name, "project_root": str(root),
                "runtime_state": state, "needs_role": True}
