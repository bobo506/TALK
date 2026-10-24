"""Role removal is fenced in one transaction; a local runtime cleans owned resources.

The tombstone and public audit survive. No key, pathname, argv or raw exception is
ever returned by the public projection. Failed cleanup is retryable, never usable.
"""
from __future__ import annotations

import hashlib
import secrets
import re
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import select

from server import models as m
from server.db import begin_immediate_write


RoleDeletion = m.RoleDeletion


STEPS = ("manager", "profiles", "credentials", "private_state", "startup_config")
ERRORS = {"cleanup_failed", "cleanup_busy", "cleanup_budget", "unsafe_resource",
          "credential_mismatch", "manager_not_stopped", "runtime_config_changed",
          "local_runtime_required"}


def public(row):
    return {"member_id": row.member_id, "status": row.status, "revision": row.revision,
            "steps": row.steps, "error_code": row.error_code,
            "identity_disabled": row.revoke_identity, "updated_at": row.updated_at,
            "lease_expires_at": row.lease_expires_at if row.status == "cleaning" else None}


def _human(current):
    if current.kind != "human":
        raise HTTPException(403, "only human members can delete roles")


def _row(session, project, member):
    row = session.get(RoleDeletion, (project, member))
    if row is None:
        raise HTTPException(404, "role_deletion_not_found")
    return row


def _cleanup_binding_digest(session, project):
    """Same authenticated DB + local project binding used by lifecycle recovery.

    Only an opaque digest reaches the host, never private config paths or argv.
    A missing binding permits a durable failure receipt, not local deletion.
    """
    from server.local_runtime import configured_runtime
    try:
        bound = configured_runtime(session.get_bind())
        if not bound:
            return None
        _, config = bound
        row = session.get(m.Project, project)
        if config["project_id"] != project or not row or not row.project_root_path or (
                Path(row.project_root_path).resolve() != Path(config["project_root"]).resolve()):
            return None
        return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    except (OSError, ValueError, RuntimeError):
        return None


def _idle(session, project, member):
    service = session.get(m.RoleServiceState, (project, member))
    if service and (service.desired_state != "stopped"
                    or service.observed_state not in ("stopped", "not_started", "failed")
                    or service.owner_host or service.process_launch_id or service.pid
                    or service.spawned):
        raise HTTPException(409, "role_service_running")
    if session.exec(select(m.RoleServiceLaunch).where(
            m.RoleServiceLaunch.project_id == project,
            m.RoleServiceLaunch.member_id == member,
            m.RoleServiceLaunch.state.in_(["pending", "claimed"]))).first():
        raise HTTPException(409, "role_service_running")
    if session.exec(select(m.AgentInstance).where(
            m.AgentInstance.member_id == member,
            or_(m.AgentInstance.project_id == project, m.AgentInstance.project_id.is_(None)),
            m.AgentInstance.status.notin_(["offline", "stopped"]))).first():
        raise HTTPException(409, "role_instance_active")
    # Uncollected submissions, pauses and creator obligations must be resolved too.
    tasks = session.exec(select(m.AgentTask).where(
        or_(m.AgentTask.project_id == project, m.AgentTask.project_id.is_(None)),
        or_(m.AgentTask.target_member_id == member, m.AgentTask.created_by == member))).all()
    if any(t.workflow_status not in ("completed", "canceled")
           or t.status in ("queued", "running") or t.control_status == "paused" for t in tasks):
        raise HTTPException(409, "role_has_active_tasks")
    if session.exec(select(m.AgentTaskSchedule).where(
            or_(m.AgentTaskSchedule.target_member_id == member,
                m.AgentTaskSchedule.created_by == member),
            m.AgentTaskSchedule.status.in_(["active", "paused"]))).first():
        raise HTTPException(409, "role_has_active_schedules")
    if session.exec(select(m.RoleProvisionRequestRow).where(
            m.RoleProvisionRequestRow.project_id == project,
            m.RoleProvisionRequestRow.member_id == member,
            m.RoleProvisionRequestRow.status.in_(["requested", "leased", "created"]))).first():
        raise HTTPException(409, "role_provision_active")


def _unambiguous_resources(session, project, member):
    def token(value):
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:120].casefold()
    if not re.fullmatch(r"agent:[A-Za-z0-9_.:-]+", member):
        raise HTTPException(409, "role_resource_ownership_unknown")
    for other in session.exec(select(m.Member)).all():
        if other.id != member and (token(other.id) == token(member)
                                  or other.id.replace(":", "_").casefold() == member.replace(":", "_").casefold()):
            raise HTTPException(409, "role_resource_ownership_unknown")
    current = session.get(m.Project, project)
    for other in session.exec(select(m.Project)).all():
        if other.project_id != project and (token(other.project_id) == token(project) or (
                current.project_root_path and other.project_root_path
                and str(Path(current.project_root_path).resolve()).casefold()
                == str(Path(other.project_root_path).resolve()).casefold())):
            raise HTTPException(409, "role_resource_ownership_unknown")


def request_delete(project, member, confirm, current, session):
    _human(current)
    if confirm != member:
        raise HTTPException(422, "role_delete_confirmation_required")
    begin_immediate_write(session)
    try:
        existing = session.get(RoleDeletion, (project, member))
        if existing:
            if existing.status == "failed":
                existing.status = "pending"
                existing.error_code = None
                existing.steps = {}
                existing.revision += 1
                existing.updated_at = datetime.now(timezone.utc)
                session.add(existing)
                session.commit()
            return public(existing)
        role = session.get(m.ProjectRole, (project, member))
        roster = session.get(m.ProjectAgent, (project, member))
        identity = session.get(m.Member, member)
        if not session.get(m.Project, project) or not identity or identity.kind != "agent" or not (role or roster):
            raise HTTPException(404, "role_not_found")
        _idle(session, project, member)
        _unambiguous_resources(session, project, member)
        proof = m.prove_exclusive_identity(project, member, session)
        managed_exclusive = bool(role and role.origin == "managed" and role.identity_exclusive)
        if managed_exclusive and proof["refusal"] is not None:
            raise HTTPException(409, "role_delete_identity_proof_required")
        exclusive = managed_exclusive
        now = datetime.now(timezone.utc)
        row = RoleDeletion(project_id=project, member_id=member, created_by=current.id,
                           revoke_identity=exclusive,
                           credential_digest=hashlib.sha256(identity.api_key.encode()).hexdigest()
                           if exclusive else None)
        if role is None:
            role = m.ProjectRole(project_id=project, member_id=member,
                                 role_name=identity.display_name, origin="imported", created_by=current.id)
        role.archived_at = now
        role.updated_at = now
        session.add(role)
        # Retain a bare roster until cleanup completes so failed cleanup remains visible.
        if roster is None:
            roster = m.ProjectAgent(project_id=project, member_id=member)
        if roster:
            roster.identity_path = roster.soul_path = roster.user_path = roster.memory_pointer = None
            roster.capability_summary = []
            roster.business_role = roster.decision_tier = None
            session.add(roster)
        for model in (m.ProjectRoleBinding, m.ProjectRoleDescription, m.ProjectRolePolicy):
            item = session.get(model, (project, member))
            if item:
                session.delete(item)
        for job in session.exec(select(m.RoleProvisionJob).where(
                m.RoleProvisionJob.project_id == project, m.RoleProvisionJob.member_id == member)).all():
            session.delete(job)
        if exclusive:
            identity.disabled_at = now
            identity.api_key = secrets.token_urlsafe(48)
            session.add(identity)
        project_row = session.get(m.Project, project)
        if project_row.controller_member_id == member:
            project_row.controller_member_id = None
            project_row.controller_assignment_version += 1
            session.add(project_row)
        session.add(row)
        session.commit()
        return public(row)
    except Exception:
        session.rollback()
        raise


def claim(project, member, revision, current, session):
    _human(current)
    begin_immediate_write(session)
    try:
        row = _row(session, project, member)
        now = datetime.now(timezone.utc)
        expiry = row.lease_expires_at
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if row.revision != revision or row.status not in ("pending", "cleaning") or (
                row.status == "cleaning" and expiry and expiry > now):
            raise HTTPException(409, "role_deletion_claim_conflict")
        token = secrets.token_urlsafe(32)
        row.lease_hash = hashlib.sha256(token.encode()).hexdigest()
        row.lease_expires_at = now + timedelta(seconds=180)
        row.status = "cleaning"
        row.revision += 1
        row.updated_at = now
        session.add(row)
        session.commit()
        return {**public(row), "lease_token": token,
                "cleanup_config_digest": _cleanup_binding_digest(session, project),
                "credential_digest": row.credential_digest}
    except Exception:
        session.rollback()
        raise


def report(project, member, token, revision, outcome, steps, error, current, session):
    _human(current)
    if outcome not in ("complete", "failed") or set(steps) != set(STEPS) or any(
            v not in ("complete", "preserved", "failed", "pending") for v in steps.values()):
        raise HTTPException(422, "role_deletion_report_invalid")
    if outcome == "complete" and any(v not in ("complete", "preserved") for v in steps.values()):
        raise HTTPException(422, "role_deletion_report_incomplete")
    if (outcome == "failed" and error not in ERRORS) or (outcome == "complete" and error is not None):
        raise HTTPException(422, "role_deletion_report_invalid")
    if outcome == "failed" and "failed" not in steps.values():
        raise HTTPException(422, "role_deletion_report_incomplete")
    begin_immediate_write(session)
    try:
        row = _row(session, project, member)
        expiry = row.lease_expires_at
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if row.status != "cleaning" or row.revision != revision or not expiry or expiry <= datetime.now(timezone.utc) or not secrets.compare_digest(
                row.lease_hash or "", hashlib.sha256(token.encode()).hexdigest()):
            raise HTTPException(409, "role_deletion_lease_conflict")
        expected = {step:"complete" for step in STEPS}
        expected["credentials"] = "complete" if row.revoke_identity else "preserved"
        if outcome == "complete" and steps != expected:
            raise HTTPException(422, "role_deletion_report_incomplete")
        row.status, row.steps, row.error_code = outcome, steps, error
        row.updated_at = datetime.now(timezone.utc)
        row.lease_hash = None
        if outcome == "complete":
            roster = session.get(m.ProjectAgent, (project, member))
            if roster:
                session.delete(roster)
            service = session.get(m.RoleServiceState, (project, member))
            if service:
                session.delete(service)
            row.credential_digest = None
        session.add(row)
        session.commit()
        return public(row)
    except Exception:
        session.rollback()
        raise
