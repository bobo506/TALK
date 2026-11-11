"""Read-only workspace diagnostics; observations never authorize a move."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from sqlmodel import Session, select

import server.db as db
from server.auth import OPERATOR_ID, is_trusted_host, resolve_member_by_key
from server.db import get_session
from server.models import Member, Project
from server.workspace_diagnostics import detect_duplicates, evaluate_move, inspect_root

router = APIRouter(prefix="/api/projects", tags=["workspace diagnostics"])


def _human(request: Request, x_api_key: str | None = Header(None, alias="X-API-Key"),
           session: Session = Depends(get_session)) -> Member:
    # The ordinary trusted-mode helper can create an operator. This endpoint is
    # read-only, so it only accepts an already registered operator.
    host = request.client.host if request.client else None
    if db.AUTH_MODE == "key" and x_api_key is None:
        raise HTTPException(422, "X-API-Key header required")
    if db.AUTH_MODE == "trusted" and not is_trusted_host(host):
        raise HTTPException(401, "Invalid API key")
    if x_api_key:
        member = resolve_member_by_key(x_api_key, session)
    elif x_api_key is None and db.AUTH_MODE == "trusted":
        member = session.get(Member, OPERATOR_ID)
    else:
        member = None
    if member is None:
        raise HTTPException(401, "Invalid API key")
    if member.disabled_at is not None or member.kind != "human":
        raise HTTPException(403, "only enabled human members can inspect projects")
    return member


def _project(session, project_id):
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def _marker(marker, project_id):
    value = marker["project_id"]
    # A marker is untrusted input; do not echo paths, control characters or
    # unbounded strings even when YAML treats them as a project ID.
    visible = value if (isinstance(value, str) and len(value) <= 256
                        and not any(ch in value for ch in "/\\")
                        and all(ch.isprintable() for ch in value)) else None
    return {"exists": marker["exists"], "project_id": visible,
            "parseable": marker["parseable"],
            "matches_project": value == project_id if marker["parseable"] else None}


def _identity(identity):
    if identity is None:
        return None
    return {key: identity[key] for key in ("platform", "volume_id", "file_id", "collected_at")}


def _projects(session):
    return list(session.exec(select(Project.project_id, Project.project_root_path).order_by(Project.project_id)).all())


def _revision(project, root):
    identity = root["identity"] or {}
    material = [1, project.project_id, project.project_root_path, root["status"],
                [identity.get(k) for k in ("platform", "machine", "volume_id", "file_id")], root["marker"]]
    return hashlib.sha256(json.dumps(material, ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _report(project, root, duplicates):
    groups = [g for g in duplicates["duplicates"] if project.project_id in g["project_ids"]]
    return {"project_id": project.project_id, "observed_at": datetime.now(timezone.utc).isoformat(),
            "revision": _revision(project, root), "root_status": root["status"],
            "identity_confidence": "strong" if root["identity"] else "unknown",
            "identity": _identity(root["identity"]), "marker": _marker(root["marker"], project.project_id),
            "issues": root["issues"], "duplicate_projects": [pid for g in groups for pid in g["project_ids"] if pid != project.project_id],
            "duplicate_check": "unknown" if duplicates["unknown"] else "complete",
            "duplicate_unknown_projects": duplicates["unknown"], "binding": "not_checked"}


@router.get("/{project_id}/workspace-diagnostics")
def diagnostics(project_id: str, current: Member = Depends(_human), session: Session = Depends(get_session)):
    project = _project(session, project_id)
    root = inspect_root(project.project_root_path)
    return _report(project, root, detect_duplicates(_projects(session)))


@router.post("/{project_id}/workspace-relink-preview")
def preview(project_id: str, body: Any = Body(...), current: Member = Depends(_human),
            session: Session = Depends(get_session)):
    project = _project(session, project_id)
    candidate_root = body.get("candidate_root") if isinstance(body, dict) else None
    if (not isinstance(candidate_root, str) or not candidate_root.strip() or len(candidate_root) > 32767
            or "\x00" in candidate_root or not Path(candidate_root).is_absolute()):
        raise HTTPException(422, "invalid candidate_root")
    old = inspect_root(project.project_root_path)
    move = evaluate_move(old, candidate_root)
    candidate = move["candidate"]
    rows = _projects(session)
    duplicates = detect_duplicates(rows)
    comparisons = detect_duplicates([(pid, root) for pid, root in rows if pid != project_id] + [(project_id, candidate_root)])
    conflicts = [pid for group in comparisons["duplicates"] if project_id in group["project_ids"]
                 for pid in group["project_ids"] if pid != project_id]
    marker = candidate["marker"]
    code = move["code"]
    reasons = []
    if marker["parseable"] and marker["project_id"] != project_id:
        code = "workspace_marker_conflict"
        reasons.append({"code": code})
    if candidate["status"] != "ok":
        code = candidate["issues"][0]["code"]
        reasons.append({"code": code})
    if conflicts:
        if not reasons:
            code = "workspace_duplicate"
        reasons.append({"code": "workspace_duplicate", "project_ids": conflicts})
    if comparisons["unknown"]:
        reasons.append({"code": "workspace_identity_unknown", "project_ids": comparisons["unknown"]})
    report = _report(project, old, duplicates)
    report.update(code=code, candidate_status=candidate["status"], candidate_marker=_marker(marker, project_id),
                  candidate_identity_confidence="strong" if candidate["identity"] else "unknown",
                  match_confidence="strong" if code == "workspace_move_candidate" else "unknown",
                  conflict_project_ids=conflicts, blocked_reasons=reasons)
    return report
