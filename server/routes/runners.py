"""全局运行器登记 API（ROLE-BINDING-B1a，合同 §3.4）。

- ``GET /api/runners``：任意已认证成员可读；
- ``POST /api/runners``：**仅 human**，201；``runner_id`` 重复 → 409；
- ``PATCH /api/runners/{runner_id}``：**仅 human**，只允许改 display_name /
  adapter_status / adapter_note / capabilities；``runner_id`` / ``runtime`` 不可改；
- 本片**无 DELETE**：停用走 ``adapter_status=retired``，历史绑定与历史快照保持。

本模块只读写登记事实：不启动进程、不读取或校验任何凭据正文、不探测任何连接、
不把 ``capabilities`` 用于权限/路由/执行判定，也不改动项目名册或任务权限。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import (
    Member,
    RunnerCreate,
    RunnerOut,
    RunnerRegistry,
    RunnerUpdate,
)

router = APIRouter(prefix="/api/runners", tags=["runners"])


def _require_human(current: Member) -> None:
    if current.kind != "human":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only human members can manage runners",
        )


@router.get("", response_model=list[RunnerOut])
def list_runners(
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """列出全部已登记运行器；只描述登记事实，不代表在线或可用。"""
    runners = session.exec(
        select(RunnerRegistry).order_by(RunnerRegistry.runner_id)
    ).all()
    return [RunnerOut.from_orm_runner(runner) for runner in runners]


@router.post("", response_model=RunnerOut, status_code=status.HTTP_201_CREATED)
def register_runner(
    body: RunnerCreate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """登记一个运行器（仅 human）。

    登记 ≠ 加入项目 ≠ 允许启动：不写任何名册/绑定行，也不启动任何进程。
    """
    _require_human(current)
    if session.get(RunnerRegistry, body.runner_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"runner_id already registered: {body.runner_id}",
        )

    now = datetime.now(timezone.utc)
    runner = RunnerRegistry(
        runner_id=body.runner_id,
        runtime=body.runtime,
        display_name=body.display_name,
        adapter_status=body.adapter_status,
        adapter_note=body.adapter_note,
        capabilities=list(body.capabilities),
        created_by=current.id,
        created_at=now,
        updated_at=now,
    )
    session.add(runner)
    try:
        session.commit()
    except IntegrityError as exc:
        # 并发登记同一 runner_id：主键冲突如实映射为 409，不返回 500。
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"runner_id already registered: {body.runner_id}",
        ) from exc
    session.refresh(runner)
    return RunnerOut.from_orm_runner(runner)


@router.patch("/{runner_id}", response_model=RunnerOut)
def update_runner(
    runner_id: str,
    body: RunnerUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """更新登记的展示/接入状态/说明/能力清单（仅 human）。

    ``runner_id`` 与 ``runtime`` 登记后不可改：请求体出现这两个键（或任何未知字段）
    由 ``RunnerUpdate`` 的 ``extra="forbid"`` 直接 422；未登记的 runner_id → 404。
    """
    _require_human(current)
    runner = session.get(RunnerRegistry, runner_id)
    if runner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"runner not found: {runner_id}",
        )

    fields = body.model_fields_set
    if "display_name" in fields:
        runner.display_name = body.display_name
    if "adapter_status" in fields:
        runner.adapter_status = body.adapter_status
    if "adapter_note" in fields:
        runner.adapter_note = body.adapter_note
    if "capabilities" in fields:
        runner.capabilities = list(body.capabilities or [])
    runner.updated_at = datetime.now(timezone.utc)
    session.add(runner)
    session.commit()
    session.refresh(runner)
    return RunnerOut.from_orm_runner(runner)
