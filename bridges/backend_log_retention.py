"""Explicit adapter for closed, project-shared backend runs; no role impersonation."""
from __future__ import annotations

import hashlib
import re

from bridges.backend_diagnostics import COMPONENTS, MEMBER, RETENTION_SCOPE
from bridges.runtime_log_retention import receipt_valid


def backend_receipt_valid(value, run, scopes):
    if not isinstance(value, dict):
        return False
    component = value.get("backend_component")
    project = value.get("project_id")
    if (not isinstance(project, str) or value.get("member_id") != MEMBER
            or value.get("task_ids") != [] or value.get("retention_scope") != RETENTION_SCOPE
            or not isinstance(component, str) or component not in COMPONENTS):
        return False
    return (receipt_valid(value, run, scopes, allow_taskless=True)
        and re.fullmatch(re.escape(component)+r"-[1-9][0-9]*", value["instance_id"]) is not None
        and run.parents[2].name == hashlib.sha256(project.encode()).hexdigest())
