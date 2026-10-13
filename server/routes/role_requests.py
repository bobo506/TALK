"""角色生命周期 R1-4a：请求驱动创建 / 恢复的 10 个 API（REQUEST_CONTRACT §3）。

- A1–A10 全部实现在 :mod:`server.role_provision_requests` 的**共享守卫**里，本模块只做
  路由、human-only 边界与响应装配，因此与既有 ``projects`` 入口（C1–C4）共用同一份
  规范化 / 来源 / 租约 / 世代判定，不存在两套规则；
- GET 只需已有认证，所有 POST **仅 human**；写事务用 ``BEGIN IMMEDIATE`` 并在锁内刷新
  ORM 事实；
- 公共投影严格白名单：不返回 token / 哈希 / 绝对路径 / roster 路径 / argv / 异常正文；
  明文租约 token 只在 ``claim`` 响应出现一次，且响应**不含**角色 Key；
- 本片服务端不写宿主文件、不 spawn、不读凭据。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlmodel import Session

from server.auth import get_current_member
from server.db import get_session
from server.models import (
    Member,
    RoleProvisionHostDisableRequest,
    RoleProvisionHostEnableRequest,
    RoleRequestClaimRequest,
    RoleRequestCreate,
    RoleRequestReportRequest,
    RoleRequestRevisionRequest,
    ROLE_REQUEST_LIST_LIMIT_DEFAULT,
)
from server.role_provision_requests import (
    cancel_request,
    claim_request,
    create_request_intent,
    disable_host_config,
    enable_host_config,
    get_request,
    host_config_projection,
    list_requests,
    report_request,
    resume_request,
)

router = APIRouter(prefix="/api/projects", tags=["role-requests"])


def _require_human(current: Member) -> None:
    if current.kind != "human":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only human members can manage role provision requests",
        )


@router.get("/{project_id}/role-provision-host")
def get_project_role_provision_host(
    project_id: str,
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> dict:
    """A1：只读公开配置投影（未建行 = disabled / version 0，不伪造配置行）。"""
    return host_config_projection(project_id, session)


@router.post("/{project_id}/role-provision-host/enable")
def enable_project_role_provision_host(
    project_id: str,
    body: RoleProvisionHostEnableRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> dict:
    """A2：CAS 启用（``expected_version`` 不匹配即 409，不静默覆盖）。"""
    _require_human(current)
    return enable_host_config(
        project_id,
        host_label=body.host_label,
        expected_version=body.expected_version,
        lease_seconds=body.lease_seconds,
        max_active_leases=body.max_active_leases,
        max_attempts=body.max_attempts,
        caller=current,
        session=session,
    )


@router.post("/{project_id}/role-provision-host/disable")
def disable_project_role_provision_host(
    project_id: str,
    body: RoleProvisionHostDisableRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> dict:
    """A3：CAS 关闭；``config_version`` 换代后所有旧租约失去写资格，再启用不复活旧 token。"""
    _require_human(current)
    return disable_host_config(
        project_id,
        expected_version=body.expected_version,
        caller=current,
        session=session,
    )


@router.post("/{project_id}/role-requests", status_code=status.HTTP_201_CREATED)
def create_project_role_request(
    project_id: str,
    body: RoleRequestCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """A4：创建 / 幂等重放创建或恢复意图。

    同 ``request_key`` 同规范化载荷返回**原行**（200，不重建、不刷新快照）；异载荷 409。
    """
    _require_human(current)
    projection, reused = create_request_intent(
        project_id, body, caller=current, session=session
    )
    if reused:
        # 幂等重放：返回**原行**（不重建、不刷新快照），语义上是一次读取。
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(projection))
    return projection


@router.get("/{project_id}/role-requests")
def list_project_role_requests(
    project_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    claimable: bool | None = Query(default=None),
    limit: int = Query(default=ROLE_REQUEST_LIST_LIMIT_DEFAULT),
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> list[dict]:
    """A7：只读发现（覆盖 requested、失效 leased 与失联 created）；不写库。"""
    return list_requests(
        project_id,
        status_filter=status_filter,
        claimable_filter=claimable,
        limit=limit,
        session=session,
    )


@router.get("/{project_id}/role-requests/{request_key}")
def get_project_role_request(
    project_id: str,
    request_key: str,
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> dict:
    """A8：只读请求 + 实际作业进度（严格白名单投影）。"""
    return get_request(project_id, request_key, session)


@router.post("/{project_id}/role-requests/{request_key}/claim")
def claim_project_role_request(
    project_id: str,
    request_key: str,
    body: RoleRequestClaimRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> dict:
    """A5：领取或失效后重领；返回一次性 token 与执行所需**非凭据**事实。"""
    _require_human(current)
    return claim_request(
        project_id,
        request_key,
        host=body.host,
        expected_revision=body.expected_revision,
        lease_seconds=body.lease_seconds,
        session=session,
    )


@router.post("/{project_id}/role-requests/{request_key}/report")
def report_project_role_request(
    project_id: str,
    request_key: str,
    body: RoleRequestReportRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> dict:
    """A6：回报 ``provisioned`` / ``failed``；成员身份由服务端从请求事实取。"""
    _require_human(current)
    return report_request(
        project_id,
        request_key,
        lease_token=body.lease_token,
        expected_revision=body.expected_revision,
        outcome=body.outcome,
        error_code=body.error_code,
        session=session,
    )


@router.post("/{project_id}/role-requests/{request_key}/cancel")
def cancel_project_role_request(
    project_id: str,
    request_key: str,
    body: RoleRequestRevisionRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> dict:
    """A9：仅未创建成员的 requested/leased/failed 可取消；成员已创建返回 ``member_created``。"""
    _require_human(current)
    return cancel_request(
        project_id,
        request_key,
        expected_revision=body.expected_revision,
        session=session,
    )


@router.post("/{project_id}/role-requests/{request_key}/resume")
def resume_project_role_request(
    project_id: str,
    request_key: str,
    body: RoleRequestRevisionRequest,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> dict:
    """A10：failed 或次数耗尽且租约无效时的人工续跑；重置 attempts 并失效旧代。"""
    _require_human(current)
    return resume_request(
        project_id,
        request_key,
        expected_revision=body.expected_revision,
        confirm=body.confirm,
        session=session,
    )
