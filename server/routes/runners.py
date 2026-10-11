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

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import get_session
from server.models import (
    MODEL_CHOICE_ALIAS_MAX_CHARS,
    MODEL_CHOICE_SOURCE_KIND_DEFAULT,
    RUNNER_ADAPTER_RETIRED,
    Member,
    RunnerControlKindUpdate,
    RunnerCreate,
    RunnerModelChoice,
    RunnerModelChoiceCreate,
    RunnerModelChoiceOut,
    RunnerModelChoiceUpdate,
    RunnerOut,
    RunnerRegistry,
    RunnerUpdate,
    new_model_choice_id,
    normalize_model_choice_source_kind,
    normalize_model_display_name,
    normalize_model_source,
    normalize_runner_capabilities,
    normalize_safe_identifier_token,
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


# ── 角色生命周期 R1-1：模型选择目录与控制能力（合同 §4.1.1 / §5.1） ──────────
#
# 本组入口只登记“TALK 见过哪些模型选择”与“谁可能控制该运行器”：
# 不代表模型在线/可用/已授权，也不启动任何进程；只有 human 可写。

CHOICE_DIMENSION_FIELDS = (
    "model_id",
    "model_source",
    "provider_id",
    "connection_ref",
    "model_alias",
)


def _require_runner(runner_id: str, session: Session) -> RunnerRegistry:
    runner = session.get(RunnerRegistry, runner_id)
    if runner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"runner not found: {runner_id}",
        )
    return runner


def _find_choice_by_dimensions(
    runner_id: str,
    *,
    model_id: str,
    model_source: str,
    provider_id: str,
    connection_ref: str,
    model_alias: str,
    session: Session,
) -> RunnerModelChoice | None:
    return session.exec(
        select(RunnerModelChoice)
        .where(RunnerModelChoice.runner_id == runner_id)
        .where(RunnerModelChoice.model_id == model_id)
        .where(RunnerModelChoice.model_source == model_source)
        .where(RunnerModelChoice.provider_id == provider_id)
        .where(RunnerModelChoice.connection_ref == connection_ref)
        .where(RunnerModelChoice.model_alias == model_alias)
    ).first()


def _normalize_choice_dimensions(runner_id: str, body: RunnerModelChoiceCreate) -> dict:
    """归一化选择维度；非法值一律 422（不静默截断、不静默丢弃）。"""
    try:
        return {
            "runner_id": runner_id,
            "model_id": normalize_safe_identifier_token(body.model_id, field="model_id"),
            "model_source": normalize_model_source(body.model_source),
            "provider_id": normalize_safe_identifier_token(
                body.provider_id, field="provider_id"
            ),
            "connection_ref": normalize_safe_identifier_token(
                body.connection_ref, field="connection_ref"
            ),
            "model_alias": normalize_safe_identifier_token(
                body.model_alias,
                field="model_alias",
                max_chars=MODEL_CHOICE_ALIAS_MAX_CHARS,
                required=False,
            )
            or "",
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/{runner_id}/model-choices", response_model=list[RunnerModelChoiceOut])
def list_model_choices(
    runner_id: str,
    include_retired: bool = Query(False),
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """列出某运行器的模型选择目录（任意已认证成员可读）。

    默认过滤 ``retired_at``（软下架只影响新选择）；``?include_retired=true`` 如实返回全部，
    供页面区分“已下架”与“从未登记”。空目录返回 ``[]``（不是 404）。
    """
    _require_runner(runner_id, session)
    stmt = select(RunnerModelChoice).where(RunnerModelChoice.runner_id == runner_id)
    if not include_retired:
        stmt = stmt.where(RunnerModelChoice.retired_at.is_(None))
    rows = session.exec(
        stmt.order_by(RunnerModelChoice.created_at, RunnerModelChoice.choice_id)
    ).all()
    return [RunnerModelChoiceOut.from_orm_choice(row) for row in rows]


@router.post(
    "/{runner_id}/model-choices",
    response_model=RunnerModelChoiceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_model_choice(
    runner_id: str,
    body: RunnerModelChoiceCreate,
    response: Response,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """新建或复用一条模型选择（**仅 human**；合同 §4.1.1）。

    - 按**选择维度**唯一键查找：命中 → 200，只更新显式提供的展示/来源字段；
      未命中 → 201 新 ``choice_id``；
    - 同运行器同 ``model_id`` 的不同 provider/connection/alias **可并存**；
    - 运行器不存在 404；运行器已退役 409 ``runner_retired``；
    - 只登记事实：不探测连接、不校验凭据、不代表模型可用。
    """
    _require_human(current)
    runner = _require_runner(runner_id, session)
    if runner.adapter_status == RUNNER_ADAPTER_RETIRED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="runner_retired"
        )

    dimensions = _normalize_choice_dimensions(runner_id, body)
    provided = body.model_fields_set
    try:
        display_name = (
            normalize_model_display_name(body.model_display_name)
            if "model_display_name" in provided
            else None
        )
        source_kind = (
            normalize_model_choice_source_kind(body.source_kind)
            if "source_kind" in provided
            else None
        )
        capabilities = (
            normalize_runner_capabilities(list(body.capabilities or []))
            if "capabilities" in provided
            else None
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    now = datetime.now(timezone.utc)
    existing = _find_choice_by_dimensions(session=session, **dimensions)
    if existing is not None:
        if "model_display_name" in provided:
            existing.model_display_name = display_name
        if source_kind is not None:
            existing.source_kind = source_kind
        if capabilities is not None:
            existing.capabilities = capabilities
        existing.updated_at = now
        session.add(existing)
        session.commit()
        session.refresh(existing)
        response.status_code = status.HTTP_200_OK
        return RunnerModelChoiceOut.from_orm_choice(existing)

    choice = RunnerModelChoice(
        choice_id=new_model_choice_id(),
        model_display_name=display_name,
        source_kind=source_kind or MODEL_CHOICE_SOURCE_KIND_DEFAULT,
        capabilities=capabilities or [],
        retired_at=None,
        created_by=current.id,
        created_at=now,
        updated_at=now,
        **dimensions,
    )
    session.add(choice)
    try:
        session.commit()
    except IntegrityError:
        # 并发插入撞唯一键：重查一次；仍冲突按 409（不静默改名/不改写既有行）。
        session.rollback()
        existing = _find_choice_by_dimensions(session=session, **dimensions)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="choice_dimension_conflict",
            )
        response.status_code = status.HTTP_200_OK
        return RunnerModelChoiceOut.from_orm_choice(existing)
    session.refresh(choice)
    return RunnerModelChoiceOut.from_orm_choice(choice)


@router.patch(
    "/{runner_id}/model-choices/{choice_id}", response_model=RunnerModelChoiceOut
)
def update_model_choice(
    runner_id: str,
    choice_id: str,
    body: RunnerModelChoiceUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """只改展示/来源/软下架（**仅 human**；合同 §4.1.1）。

    选择维度不可变：请求出现任一维度键 → 409 ``choice_dimension_immutable``
    （客户端应改为新建选择）；``retired_at`` 是软下架，改它不影响历史绑定行。
    """
    _require_human(current)
    _require_runner(runner_id, session)
    choice = session.get(RunnerModelChoice, choice_id)
    if choice is None or choice.runner_id != runner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="choice_not_found"
        )
    if set(CHOICE_DIMENSION_FIELDS) & body.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="choice_dimension_immutable",
        )

    provided = body.model_fields_set
    try:
        if "model_display_name" in provided:
            choice.model_display_name = normalize_model_display_name(
                body.model_display_name
            )
        if "capabilities" in provided:
            choice.capabilities = normalize_runner_capabilities(
                list(body.capabilities or [])
            )
        if "source_kind" in provided:
            if body.source_kind is None:
                raise ValueError("source_kind cannot be null")
            choice.source_kind = normalize_model_choice_source_kind(body.source_kind)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if "retired_at" in provided:
        choice.retired_at = body.retired_at

    choice.updated_at = datetime.now(timezone.utc)
    session.add(choice)
    session.commit()
    session.refresh(choice)
    return RunnerModelChoiceOut.from_orm_choice(choice)


@router.patch("/{runner_id}/control-kind", response_model=RunnerOut)
def update_runner_control_kind(
    runner_id: str,
    body: RunnerControlKindUpdate,
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """设置运行器控制能力分类（**仅 human**；合同 §5.1/§12）。

    独立入口：避免与既有 ``PATCH /api/runners/{id}`` 四字段白名单冲突。
    只声明“谁可能控制它”，不代表已核验、在线或允许启动。
    """
    _require_human(current)
    runner = _require_runner(runner_id, session)
    runner.control_kind = body.control_kind
    runner.updated_at = datetime.now(timezone.utc)
    session.add(runner)
    session.commit()
    session.refresh(runner)
    return RunnerOut.from_orm_runner(runner)
