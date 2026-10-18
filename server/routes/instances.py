"""Agent runtime instance status APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import begin_immediate_write, get_session
from server.models import (
    ROLE_SERVICE_ACTION_START,
    ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH,
    ROLE_SERVICE_ERROR_IDENTITY_MISMATCH,
    ROLE_SERVICE_ERROR_INSTANCE_LAUNCH_IMMUTABLE,
    ROLE_SERVICE_ERROR_LAUNCH_ACTION_MISMATCH,
    ROLE_SERVICE_ERROR_LAUNCH_EXPIRED,
    ROLE_SERVICE_ERROR_LAUNCH_NOT_FOUND,
    ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING,
    ROLE_SERVICE_LAUNCH_CLAIMED,
    ROLE_SERVICE_LAUNCH_EXPIRED,
    ROLE_SERVICE_LAUNCH_PENDING,
    ROLE_SERVICE_LAUNCH_REPORTED,
    AgentInstance,
    AgentInstanceOut,
    AgentInstanceUpdate,
    Member,
    ProjectAgent,
    ProjectRole,
    RoleServiceLaunch,
    RoleServiceRecovery,
)
from server.role_services import _as_utc, note_instance_launch_evidence

router = APIRouter(prefix="/api/instances", tags=["instances"])


def _require_agent(current: Member) -> None:
    if current.kind != "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only agent members can report instance status",
        )


def _project_declaration_allowed(
    project_id: str, member_id: str, session: Session
) -> bool:
    """项目声明校验（合同 §10.4）：名册行存在且角色（若有）未归档。"""
    if session.get(ProjectAgent, (project_id, member_id)) is None:
        return False
    role = session.get(ProjectRole, (project_id, member_id))
    return not (role is not None and role.archived_at is not None)


def _authorize_launch_first_binding(
    launch_id: str,
    instance_id: str,
    project_id: Optional[str],
    current: Member,
    session: Session,
    now: datetime,
) -> None:
    """R1-3：实例**首次**绑定非空 ``launch_id`` 的真实校验（合同 §10.4）。

    替换 R1-1 的 ``instance_launch_not_supported`` 阶段拒绝。首次关联必须同时满足：

    - launch 行真实存在，且 ``action='start'``；
    - ``launch.expected_instance_id == instance_id``（**预分配**的新实例，不允许用
      另一个恰好同 member 的旧实例顶替）；
    - ``member_id``/``project_id`` 一致；
    - 已 claim（``claim_member_id``/``claimed_at`` 已建立）且未过截止；``reported``
      也算合法（“报告先到、实例后到”同样要能收敛）；
    - 已存在非空 ``launch_id`` 的实例在调用方已按 ``instance_launch_immutable`` 拒绝，
      **legacy 旧实例不能重新贴标签**；不新增 ``instance.generation`` 列。
    """
    launch = session.get(RoleServiceLaunch, launch_id)
    if launch is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ROLE_SERVICE_ERROR_LAUNCH_NOT_FOUND,
        )
    if launch.action != ROLE_SERVICE_ACTION_START:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ROLE_SERVICE_ERROR_LAUNCH_ACTION_MISMATCH,
        )
    if launch.member_id != current.id or launch.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ROLE_SERVICE_ERROR_IDENTITY_MISMATCH,
        )
    if launch.expected_instance_id != instance_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH,
        )
    if launch.state == ROLE_SERVICE_LAUNCH_PENDING or launch.claimed_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING,
        )
    expires_at = _as_utc(launch.launch_expires_at)
    if launch.state == ROLE_SERVICE_LAUNCH_EXPIRED or (
        expires_at is not None and now > expires_at
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ROLE_SERVICE_ERROR_LAUNCH_EXPIRED,
        )
    if launch.state not in (
        ROLE_SERVICE_LAUNCH_CLAIMED,
        ROLE_SERVICE_LAUNCH_REPORTED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING,
        )


@router.put("/{instance_id}", response_model=AgentInstanceOut)
def upsert_instance_status(
    instance_id: str,
    body: AgentInstanceUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Create or update the current Agent's runtime instance status.

    角色生命周期 R1-1（合同 §5.4 / §10.4）：

    - 只赋值请求中**显式出现**的字段（``model_fields_set``）：旧心跳省略可选字段时
      保持原值，不再被抹成 ``NULL``；
    - ``project_id`` 一旦非空不可改写/清空（``409 instance_project_immutable``）；
      首次声明要求该成员在本项目名册内且角色未归档，否则
      ``422 instance_project_not_in_roster``；
    - ``launch_id`` 一旦非空不可改写/清空（``409 instance_launch_immutable``）；
      R1-1 尚未实现服务协议，**首次**非空关联统一拒绝
      ``422 instance_launch_not_supported``（夹具预置的非空值可同值重复/省略保持）。

    F1 补正：身份归属（403）、名册/launch 读取与**首次** ``project_id`` 声明必须原子。
    处理器先在 ``BEGIN IMMEDIATE`` 实际写锁内运行，两个真实连接不会各自读到 ``NULL``
    再互相覆盖：后到者在锁上等待并读到已提交事实（同值 200 / 异值
    ``409 instance_project_immutable``），插入竞态也在同一把写锁内串行。
    """
    _require_agent(current)
    # 实际写事务边界（合同 §5.4/§10.4）：先取写锁，再读取校验，最后写入。
    begin_immediate_write(session)
    now = datetime.now(timezone.utc)
    existing = session.get(AgentInstance, instance_id)

    if existing is not None and existing.member_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="instance belongs to another member",
        )

    if existing is not None and existing.launch_id and session.exec(
        select(RoleServiceRecovery.recovery_id).where(
            RoleServiceRecovery.project_id == existing.project_id,
            RoleServiceRecovery.member_id == existing.member_id,
            RoleServiceRecovery.instance_id == instance_id,
        ).limit(1)
    ).first() is not None:
        raise HTTPException(status_code=409, detail="instance_launch_recovered")

    provided = body.model_fields_set

    if existing is not None and existing.project_id is not None:
        if "project_id" in provided and body.project_id != existing.project_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="instance_project_immutable",
            )
        effective_project_id = existing.project_id
    else:
        if "project_id" in provided and body.project_id is not None:
            if not _project_declaration_allowed(body.project_id, current.id, session):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="instance_project_not_in_roster",
                )
        effective_project_id = body.project_id if "project_id" in provided else None

    if existing is not None and existing.launch_id is not None:
        if "launch_id" in provided and body.launch_id != existing.launch_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="instance_launch_immutable",
            )
        effective_launch_id = existing.launch_id
    else:
        effective_launch_id = None
        if "launch_id" in provided and body.launch_id is not None:
            if existing is not None:
                # 已经存在的实例（含 legacy 行）**不能**被重新贴上本次 launch_id：
                # 首次关联只允许在“本次请求新建该实例行”时发生（合同 §10.4 / I49）。
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ROLE_SERVICE_ERROR_INSTANCE_LAUNCH_IMMUTABLE,
                )
            # R1-3：接通真实 launch 存在/领取/实例匹配校验（合同 §10.4）。
            _authorize_launch_first_binding(
                body.launch_id,
                instance_id,
                effective_project_id,
                current,
                session,
                now,
            )
            effective_launch_id = body.launch_id

    instance = existing or AgentInstance(
        id=instance_id,
        member_id=current.id,
        runtime=body.runtime,
        status=body.status,
        created_at=now,
    )
    instance.runtime = body.runtime
    instance.status = body.status
    if "host" in provided:
        instance.host = body.host
    if "pid" in provided:
        instance.pid = body.pid
    if "current_task_id" in provided:
        instance.current_task_id = body.current_task_id
    if "last_error" in provided:
        instance.last_error = body.last_error
    if "project_id" in provided:
        instance.project_id = effective_project_id
    if "launch_id" in provided:
        instance.launch_id = effective_launch_id
    if "process_started_at" in provided:
        instance.process_started_at = body.process_started_at
    instance.updated_at = now
    instance.last_seen_at = now

    session.add(instance)
    # R1-3：本次预分配实例的**首次证据**（claim 之后、截止之前的新心跳）与四条件
    # 就绪收敛都在同一写事务内完成；实例先到/报告先到都能收敛，旧心跳不产生就绪。
    if instance.launch_id:
        note_instance_launch_evidence(session, instance, now=now)
    session.commit()
    session.refresh(instance)
    return instance


@router.get("", response_model=list[AgentInstanceOut])
def list_instances(
    member_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    project_id: str | None = Query(None),
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """List Agent runtime instances visible to any authenticated member.

    ``project_id`` 是 R1-1 新增的附加过滤；不传时行为与改动前一致。
    """
    stmt = select(AgentInstance)
    if member_id:
        stmt = stmt.where(AgentInstance.member_id == member_id)
    if status_filter:
        stmt = stmt.where(AgentInstance.status == status_filter.strip().lower())
    if project_id:
        stmt = stmt.where(AgentInstance.project_id == project_id)
    return session.exec(stmt.order_by(AgentInstance.updated_at.desc())).all()  # type: ignore[union-attr]
