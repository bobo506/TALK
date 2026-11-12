"""Workspace operation guards; callers hold the SQLite write transaction."""
from sqlalchemy import select

from server.models import AgentTask, RoleServiceState
from server.workspace_operations import WorkspaceOperation


def active_relink(session, project_id, *, exclude_operation_id=None):
    statement = select(WorkspaceOperation).where(
        WorkspaceOperation.project_id == project_id,
        WorkspaceOperation.stage.not_in(("completed", "failed")),
    )
    if exclude_operation_id is not None:
        statement = statement.where(WorkspaceOperation.operation_id != exclude_operation_id)
    return list(session.execute(statement.execution_options(populate_existing=True)).scalars())


def operation_code(session, project_id, *, claim=False, exclude_operation_id=None):
    active = active_relink(session, project_id, exclude_operation_id=exclude_operation_id)
    if not active:
        return None
    if not claim and any(op.stage == "recovery_required" for op in active):
        return "workspace_recovery_required"
    return "workspace_busy"


def relink_busy_code(session, project_id, operation_id):
    code = operation_code(session, project_id, exclude_operation_id=operation_id)
    if code:
        return code
    roles = session.execute(select(RoleServiceState).where(
        RoleServiceState.project_id == project_id).execution_options(populate_existing=True)).scalars()
    for role in roles:
        if (role.desired_state != "stopped" or role.observed_state not in ("stopped", "not_started")
                or role.owner_host or role.process_launch_id or role.pid or role.current_launch_id):
            return "workspace_busy"
    tasks = session.execute(select(AgentTask).where(
        AgentTask.project_id == project_id).execution_options(populate_existing=True)).scalars()
    for task in tasks:
        if (task.status not in ("queued", "succeeded", "failed", "canceled")
                or (task.status == "queued" and task.claimed_by)):
            return "workspace_busy"
    return None
