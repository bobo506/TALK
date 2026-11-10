"""Create and bind a local workspace without provisioning roles."""
from __future__ import annotations

import json
import os
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from server import local_runtime
from server.auth import get_current_member
from server.db import begin_immediate_write, get_session
from server.models import Member, Project
from server.role_provision_requests import enable_host_config, host_config_projection

router = APIRouter(prefix="/api/local/workspaces", tags=["local-workspaces"])
_lock = threading.Lock()


class WorkspaceEnsure(BaseModel):
    project_root: str
    display_name: str | None = None


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


@router.post("/ensure")
def ensure_workspace(body: WorkspaceEnsure, current: Member = Depends(get_current_member),
                     session: Session = Depends(get_session)):
    if current.kind != "human":
        raise HTTPException(403, "human_required")
    with _lock:
        root = _root(body.project_root)
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
                        identity = os.path.normcase(str(root))
                        project = next((p for p in work.exec(select(Project)).all()
                                        if p.project_root_path and os.path.normcase(str(Path(p.project_root_path).expanduser().resolve())) == identity), None)
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
