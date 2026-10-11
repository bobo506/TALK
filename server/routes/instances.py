"""Agent runtime instance status APIs."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import begin_immediate_write, get_session
from server.models import (
    AgentInstance,
    AgentInstanceOut,
    AgentInstanceUpdate,
    Member,
    ProjectAgent,
    ProjectRole,
)

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
        if "launch_id" in provided and body.launch_id is not None:
            # R1-1：服务协议与 launch 表尚未实施，不用裸字符串冒充启动证据。
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="instance_launch_not_supported",
            )
        effective_launch_id = None

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
