"""角色生命周期 R1-3：受管 CLI 服务生命周期的六个 API（合同 §5.3）。

- 全部实现在 :mod:`server.role_services`；本模块只做路由、权限边界与响应模型；
- 意图写（start/stop/start-all）**仅 human**；claim/report 只允许目标角色的 agent
  或合法 human 宿主，agent **不能**修改 ``desired_state``；
- 角色原生进程由本机runtime/宿主执行；服务端不按PID接管/kill角色进程；
- 公共 GET 与所有响应都不返回 ``owner_token``/``claim_token``、argv 或绝对路径。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from server.auth import get_current_member
from server.db import get_session
from server.models import (
    Member,
    RoleServiceLaunchClaimOut,
    RoleServiceLaunchClaimRequest,
    RoleServiceLaunchReportOut,
    RoleServiceLaunchReportRequest,
    RoleServiceStartAllOut,
    RoleServiceStartAllRequest,
    RoleServiceStartOut,
    RoleServiceStopOut,
    RoleServiceProjectionOut,
    RoleServiceRecoveryRequest,
    RoleServiceRecoveryPlan,
    RoleServiceRecoveryOut,
)
from server.role_service_recovery import recovery_plan, recover_stopped
from server.local_runtime import require_local_runtime, recover_local_human_stop
from server.role_services import (
    claim_role_service_launch,
    list_role_services,
    report_role_service_launch,
    start_all_role_services,
    start_role_service,
    stop_role_service,
)

router = APIRouter(prefix="/api", tags=["role-services"])


def _require_human(current: Member) -> None:
    if current.kind != "human":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only human members can control role services",
        )


@router.post(
    "/projects/{project_id}/roles/{member_id}/service/start",
    response_model=RoleServiceStartOut,
)
def start_project_role_service(
    project_id: str,
    member_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """请求启动（**仅 human**）：CAS 递增世代并建 ``action='start'`` 的 pending launch。

    服务端预分配全新 ``expected_instance_id`` 与 ``launch_expires_at``；
    **不返回任何 token**，不直接spawn角色；已绑定本机入口时确保后台宿主可用。
    """
    _require_human(current)
    require_local_runtime(session.get_bind())
    return start_role_service(project_id, member_id, current, session)


@router.post(
    "/projects/{project_id}/roles/{member_id}/service/stop",
    response_model=RoleServiceStopOut,
)
def stop_project_role_service(
    project_id: str,
    member_id: str,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """请求关闭（**仅 human**）：沿用原 start 的进程归属与实例 ID。

    无受管进程且可证明已停 → 幂等 ``stopped``；所有权未知 → ``409 unknown_owner``。
    """
    _require_human(current)
    recover_local_human_stop(project_id, member_id, current, session)
    require_local_runtime(session.get_bind())
    return stop_role_service(project_id, member_id, current, session)


@router.get("/projects/{project_id}/roles/{member_id}/service/recovery-plan",
            response_model=RoleServiceRecoveryPlan)
def get_recovery_plan(project_id: str, member_id: str,
                      current: Member = Depends(get_current_member),
                      session: Session = Depends(get_session)):
    return recovery_plan(project_id, member_id, current, session)


@router.post("/projects/{project_id}/roles/{member_id}/service/recover-stopped",
             response_model=RoleServiceRecoveryOut)
def recover_role_stopped(project_id: str, member_id: str, body: RoleServiceRecoveryRequest,
                         current: Member = Depends(get_current_member),
                         session: Session = Depends(get_session)):
    return recover_stopped(project_id, member_id, body, current, session)


@router.post(
    "/projects/{project_id}/role-services/start-all",
    response_model=RoleServiceStartAllOut,
)
def start_all_project_role_services(
    project_id: str,
    body: RoleServiceStartAllRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """项目“全部启动”（**仅 human**）：跳过 ``running/starting``，返回逐角色结果。

    ``member_ids`` 只用于重试失败子集；跨项目/不存在 ID 稳定拒绝（404 ``role_not_found``）。
    部分失败不整体回滚。
    """
    _require_human(current)
    require_local_runtime(session.get_bind())
    return start_all_role_services(project_id, body.member_ids, current, session)


@router.get(
    "/projects/{project_id}/role-services",
    response_model=list[RoleServiceProjectionOut],
)
def list_project_role_services(
    project_id: str,
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """只读服务状态投影（任意已认证；供页面轮询/刷新）。

    **不含** owner_token/claim_token/argv/绝对路径；三个独立事实
    （``native_login``/``model_alias``/``readiness_service``）分列，不合并成假的 ready。
    """
    return list_role_services(project_id, session)


@router.post(
    "/role-service-launches/{launch_id}/claim",
    response_model=RoleServiceLaunchClaimOut,
)
def claim_launch(
    launch_id: str,
    body: RoleServiceLaunchClaimRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """宿主领取动作（目标角色的 agent 或合法 human 宿主）。

    start 返回 ``owner_token`` + ``claim_token``；stop 只返回新的 ``claim_token``
    （必须提交原 start 的 owner token 与原 host）。库内只存哈希。
    """
    return claim_role_service_launch(
        launch_id,
        host=body.host,
        expected_instance_id=body.expected_instance_id,
        owner_token=body.owner_token,
        caller=current,
        session=session,
    )


@router.post(
    "/role-service-launches/{launch_id}/report",
    response_model=RoleServiceLaunchReportOut,
)
def report_launch(
    launch_id: str,
    body: RoleServiceLaunchReportRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """宿主回报观测结果。

    核 ``launch + 世代 + action + 领取身份 + host + 两 token + claimed 状态 + 时间窗``；
    同一完整载荷重放只读返回原 receipt（即使已过截止也不改当前状态）；
    不同载荷 ``report_conflict``；被新动作取代的旧动作首次迟到 ``stale_report``。
    """
    return report_role_service_launch(
        launch_id,
        generation=body.generation,
        action=body.action,
        claim_token=body.claim_token,
        owner_token=body.owner_token,
        outcome=body.outcome,
        instance_id=body.instance_id,
        pid=body.pid,
        process_started_at=body.process_started_at,
        host=body.host,
        error_code=body.error_code,
        spawned=body.spawned,
        caller=current,
        session=session,
    )
