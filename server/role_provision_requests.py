"""角色生命周期 R1-4a：请求驱动创建 / 恢复的**共享守卫**（REQUEST_CONTRACT）。

本模块是 ``docs/spec/ROLE_CREATION_PROVISION_REQUEST_CONTRACT.md`` 的唯一实现点：

- 新路由 ``server/routes/role_requests.py``（A1–A10）与既有 ``projects`` 入口的
  C1–C4 接线**共用**这里的规范化、来源选择、租约/世代判定、事务与公共投影规则，
  因此不存在两套授权或租约判定，也不产生 router/projects 循环导入；
- 服务端**只**保存意图与事实：不写宿主文件、不 spawn、不读凭据、不重放 Key；
- 明文租约 token 只在 claim 响应出现一次，库内只存 ``sha256``；
- 全部写入口都是 human-only（路由层判定），默认项目配置关闭（``enabled=0``）。

约定：所有需要“锁内事实”的入口都在 ``BEGIN IMMEDIATE`` + ``expire_all()`` 之后
读取，绝不使用锁前的 ORM identity map 缓存。
"""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, select

from server.db import begin_immediate_write
from server.models import (
    Member,
    Project,
    ProjectAgent,
    ProjectRole,
    RoleCreationOperation,
    RoleCredentialRotation,
    RoleProvisionHostConfig,
    RoleProvisionJob,
    RoleProvisionRequestRow,
    RoleRequestCreate,
    RoleServiceState,
    RunnerModelChoice,
    RunnerRegistry,
    PROVISION_ERROR_CODE_MAX_CHARS,
    PROVISION_JOB_STATUS_SUCCEEDED,
    PROVISION_STEP_ORDER,
    PROVISION_STEP_STATE_FAILED,
    PROVISION_STEP_STATE_PENDING,
    PROJECT_ROLE_ORIGIN_MANAGED,
    ROLE_AUTO_START_STATUS_ENQUEUED,
    ROLE_AUTO_START_STATUS_FAILED,
    ROLE_AUTO_START_STATUS_NOT_ELIGIBLE,
    ROLE_AUTO_START_STATUS_PENDING,
    ROLE_PROVISION_HOST_ERROR_BUSY,
    ROLE_PROVISION_HOST_ERROR_CONFIG_INVALID,
    ROLE_PROVISION_HOST_ERROR_DISABLED,
    ROLE_PROVISION_HOST_ERROR_VERSION_CONFLICT,
    ROLE_PROVISION_HOST_LABEL_MAX_CHARS,
    ROLE_PROVISION_HOST_LEASE_SECONDS_DEFAULT,
    ROLE_PROVISION_HOST_LEASE_SECONDS_MAX,
    ROLE_PROVISION_HOST_LEASE_SECONDS_MIN,
    ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_DEFAULT,
    ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_MAX,
    ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_MIN,
    ROLE_PROVISION_HOST_MAX_ATTEMPTS_DEFAULT,
    ROLE_PROVISION_HOST_MAX_ATTEMPTS_MAX,
    ROLE_PROVISION_HOST_MAX_ATTEMPTS_MIN,
    ROLE_REQUEST_ACTIVE_STATUSES,
    ROLE_REQUEST_CLAIMABLE_STATUSES,
    ROLE_REQUEST_ERROR_AUTO_START_CONFIG_DISABLED,
    ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED,
    ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT,
    ROLE_REQUEST_ERROR_BINDING_MISMATCH,
    ROLE_REQUEST_ERROR_CANCEL_REFUSED,
    ROLE_REQUEST_ERROR_CHOICE_UNAVAILABLE,
    ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE,
    ROLE_REQUEST_ERROR_CONFIRM_REQUIRED,
    ROLE_REQUEST_ERROR_CREDENTIAL_MISMATCH,
    ROLE_REQUEST_ERROR_CREDENTIAL_STALE,
    ROLE_REQUEST_ERROR_HOST_MISMATCH,
    ROLE_REQUEST_ERROR_KEY_CONFLICT,
    ROLE_REQUEST_ERROR_KIND_INVALID,
    ROLE_REQUEST_ERROR_LEASE_CONFLICT,
    ROLE_REQUEST_ERROR_LEASE_INVALID,
    ROLE_REQUEST_ERROR_LEASE_SECONDS_INVALID,
    ROLE_REQUEST_ERROR_MEMBER_CREATED,
    ROLE_REQUEST_ERROR_NOT_FOUND,
    ROLE_REQUEST_ERROR_NOT_RESUMABLE,
    ROLE_REQUEST_ERROR_OPERATION_CONFLICT,
    ROLE_REQUEST_ERROR_OPERATION_MISMATCH,
    ROLE_REQUEST_ERROR_PAYLOAD_INVALID,
    ROLE_REQUEST_ERROR_PAYLOAD_MISMATCH,
    ROLE_REQUEST_ERROR_REVISION_CONFLICT,
    ROLE_REQUEST_ERROR_ROLE_CONFLICT,
    ROLE_REQUEST_ERROR_SOURCE_REQUIRED,
    ROLE_REQUEST_ERROR_STALE_REPORT,
    ROLE_REQUEST_ERROR_STATUS_CONFLICT,
    ROLE_REQUEST_ERROR_SUPERSEDED,
    ROLE_REQUEST_HOST_ERROR_CODES,
    ROLE_REQUEST_KIND_CREATE,
    ROLE_REQUEST_KIND_RECOVER,
    ROLE_REQUEST_KINDS,
    ROLE_REQUEST_LIST_LIMIT_DEFAULT,
    ROLE_REQUEST_LIST_LIMIT_MAX,
    ROLE_REQUEST_REPORT_OUTCOMES,
    ROLE_REQUEST_STATUS_CANCELED,
    ROLE_REQUEST_STATUS_CREATED,
    ROLE_REQUEST_STATUS_FAILED,
    ROLE_REQUEST_STATUS_LEASED,
    ROLE_REQUEST_STATUS_PROVISIONED,
    ROLE_REQUEST_STATUS_REQUESTED,
    RUNNER_ADAPTER_RETIRED,
    build_role_creation_fingerprint,
    build_role_recovery_fingerprint,
    binding_fingerprint,
    hash_role_provision_lease_token,
    model_choice_dimension_facts,
    new_role_provision_lease_token,
    normalize_operation_key,
    normalize_provision_steps,
    normalize_role_description,
    normalize_role_name,
    normalize_runner_id,
    normalize_safe_identifier_token,
    serialize_provision_job,
)
from server.role_services import enqueue_auto_start_launch

_NOT_FOUND = status.HTTP_404_NOT_FOUND
_FORBIDDEN = status.HTTP_403_FORBIDDEN
_CONFLICT = status.HTTP_409_CONFLICT
_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_ENTITY


# ── 基础工具 ────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """库内 datetimes 是 UTC naive；比较/投影前统一补 tz（沿用 R1-2/R1-3 先例）。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _fail(http_status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=http_status, detail=detail)


def write_begin(session: Session) -> None:
    """取得真实 SQLite 写锁并清空 ORM identity map（锁前读取不得代替锁内事实）。"""
    begin_immediate_write(session)
    session.expire_all()


def _rollback(session: Session) -> None:
    if session.in_transaction():
        session.rollback()


def _normalize_request_key(value: object) -> str:
    """``request_key`` 沿既有 8–128 安全 operation token 规则。"""
    try:
        return normalize_operation_key(value)  # type: ignore[arg-type]
    except ValueError as exc:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID) from exc


def _normalize_host_label(value: object) -> str:
    if not isinstance(value, str):
        raise _fail(_UNPROCESSABLE, ROLE_PROVISION_HOST_ERROR_CONFIG_INVALID)
    candidate = value.strip()
    if (
        not candidate
        or len(candidate) > ROLE_PROVISION_HOST_LABEL_MAX_CHARS
        or any(ord(char) < 32 or ord(char) == 127 for char in candidate)
    ):
        raise _fail(_UNPROCESSABLE, ROLE_PROVISION_HOST_ERROR_CONFIG_INVALID)
    return candidate


def _normalize_budget(
    value: object, *, minimum: int, maximum: int, default: int, field: str
) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not (
        minimum <= value <= maximum
    ):
        raise _fail(_UNPROCESSABLE, ROLE_PROVISION_HOST_ERROR_CONFIG_INVALID)
    return int(value)


def _normalize_request_error_code(outcome: str, error_code: object) -> Optional[str]:
    """report 的 ``error_code``：只有 ``failed`` 允许携带**白名单内**的稳定安全码。

    合同 §2/§3/§8：错误码只落稳定白名单，未知串（含误传假凭据 / token / 路径片段）
    一律 422 且零写入；错误响应只回稳定码，不回显输入值，也不把任意安全标识串当成
    “无密”。新增宿主码必须先按合同登记到 ``ROLE_REQUEST_HOST_ERROR_CODES``。
    """
    if outcome != ROLE_REQUEST_STATUS_FAILED:
        if error_code is not None:
            raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
        return None
    if error_code is None:
        return None
    try:
        normalized = normalize_safe_identifier_token(
            error_code, field="error_code", max_chars=PROVISION_ERROR_CODE_MAX_CHARS
        )
    except ValueError as exc:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID) from exc
    if normalized not in ROLE_REQUEST_HOST_ERROR_CODES:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    return normalized


# ── 项目宿主配置（A1–A3）────────────────────────────────────────────────


def load_host_config(
    project_id: str, session: Session
) -> Optional[RoleProvisionHostConfig]:
    return session.get(RoleProvisionHostConfig, project_id)


def _budgets(config: Optional[RoleProvisionHostConfig]) -> tuple[int, int, int]:
    """返回 ``(lease_seconds, max_active_leases, max_attempts)``；无行时用默认值。"""
    if config is None:
        return (
            ROLE_PROVISION_HOST_LEASE_SECONDS_DEFAULT,
            ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_DEFAULT,
            ROLE_PROVISION_HOST_MAX_ATTEMPTS_DEFAULT,
        )
    return (
        int(config.lease_seconds or ROLE_PROVISION_HOST_LEASE_SECONDS_DEFAULT),
        int(
            config.max_active_leases or ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_DEFAULT
        ),
        int(config.max_attempts or ROLE_PROVISION_HOST_MAX_ATTEMPTS_DEFAULT),
    )


def host_config_projection(project_id: str, session: Session) -> dict:
    """只读公开配置投影；未建行 = disabled / version 0（不伪造配置行）。"""
    _require_project(project_id, session)
    config = load_host_config(project_id, session)
    if config is None:
        return {
            "project_id": project_id,
            "enabled": False,
            "host_label": None,
            "lease_seconds": ROLE_PROVISION_HOST_LEASE_SECONDS_DEFAULT,
            "max_active_leases": ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_DEFAULT,
            "max_attempts": ROLE_PROVISION_HOST_MAX_ATTEMPTS_DEFAULT,
            "config_version": 0,
            "updated_by": None,
            "updated_at": None,
        }
    return {
        "project_id": project_id,
        "enabled": bool(config.enabled),
        "host_label": config.host_label,
        "lease_seconds": int(config.lease_seconds),
        "max_active_leases": int(config.max_active_leases),
        "max_attempts": int(config.max_attempts),
        "config_version": int(config.config_version),
        "updated_by": config.updated_by,
        "updated_at": _as_utc(config.updated_at),
    }


def _require_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise _fail(_NOT_FOUND, "project_not_found")
    return project


def enable_host_config(
    project_id: str,
    *,
    host_label: str,
    expected_version: int,
    lease_seconds: Optional[int],
    max_active_leases: Optional[int],
    max_attempts: Optional[int],
    caller: Member,
    session: Session,
) -> dict:
    """CAS 启用项目宿主配置（A2）：版本不匹配即 409，不静默覆盖。"""
    label = _normalize_host_label(host_label)
    lease = _normalize_budget(
        lease_seconds,
        minimum=ROLE_PROVISION_HOST_LEASE_SECONDS_MIN,
        maximum=ROLE_PROVISION_HOST_LEASE_SECONDS_MAX,
        default=ROLE_PROVISION_HOST_LEASE_SECONDS_DEFAULT,
        field="lease_seconds",
    )
    parallel = _normalize_budget(
        max_active_leases,
        minimum=ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_MIN,
        maximum=ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_MAX,
        default=ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_DEFAULT,
        field="max_active_leases",
    )
    attempts = _normalize_budget(
        max_attempts,
        minimum=ROLE_PROVISION_HOST_MAX_ATTEMPTS_MIN,
        maximum=ROLE_PROVISION_HOST_MAX_ATTEMPTS_MAX,
        default=ROLE_PROVISION_HOST_MAX_ATTEMPTS_DEFAULT,
        field="max_attempts",
    )
    if isinstance(expected_version, bool) or not isinstance(expected_version, int):
        raise _fail(_UNPROCESSABLE, ROLE_PROVISION_HOST_ERROR_CONFIG_INVALID)

    write_begin(session)
    try:
        _require_project(project_id, session)
        config = load_host_config(project_id, session)
        current_version = int(config.config_version) if config is not None else 0
        if expected_version != current_version:
            raise _fail(_CONFLICT, ROLE_PROVISION_HOST_ERROR_VERSION_CONFLICT)
        now = _now()
        if config is None:
            config = RoleProvisionHostConfig(
                project_id=project_id,
                enabled=1,
                host_label=label,
                lease_seconds=lease,
                max_active_leases=parallel,
                max_attempts=attempts,
                config_version=1,
                updated_by=caller.id,
                created_at=now,
                updated_at=now,
            )
        else:
            config.enabled = 1
            config.host_label = label
            config.lease_seconds = lease
            config.max_active_leases = parallel
            config.max_attempts = attempts
            config.config_version = current_version + 1
            config.updated_by = caller.id
            config.updated_at = now
        session.add(config)
        session.commit()
        session.refresh(config)
        return host_config_projection(project_id, session)
    except HTTPException:
        _rollback(session)
        raise
    except Exception as exc:  # noqa: BLE001 - 失败整体回滚，配置保持原样
        _rollback(session)
        raise _fail(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "role_provision_host_failed"
        ) from exc


def disable_host_config(
    project_id: str,
    *,
    expected_version: int,
    caller: Member,
    session: Session,
) -> dict:
    """CAS 关闭项目宿主配置（A3）：换代后所有旧 ``config_version`` 租约失去写资格。"""
    if isinstance(expected_version, bool) or not isinstance(expected_version, int):
        raise _fail(_UNPROCESSABLE, ROLE_PROVISION_HOST_ERROR_CONFIG_INVALID)

    write_begin(session)
    try:
        _require_project(project_id, session)
        config = load_host_config(project_id, session)
        current_version = int(config.config_version) if config is not None else 0
        if config is None or expected_version != current_version:
            raise _fail(_CONFLICT, ROLE_PROVISION_HOST_ERROR_VERSION_CONFLICT)
        config.enabled = 0
        config.config_version = current_version + 1
        config.updated_by = caller.id
        config.updated_at = _now()
        session.add(config)
        session.commit()
        session.refresh(config)
        return host_config_projection(project_id, session)
    except HTTPException:
        _rollback(session)
        raise
    except Exception as exc:  # noqa: BLE001
        _rollback(session)
        raise _fail(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "role_provision_host_failed"
        ) from exc


# ── 意图规范化（A4）─────────────────────────────────────────────────────


def _pure_create_intent(project_id: str, body: RoleRequestCreate) -> dict:
    """create 意图的**纯载荷**归一化（合同 §6）：不读实时目录 / 不依赖当前选择状态。

    只做规范化四字段与既有创建指纹。A4 必须先用它判断“同键同载荷”重放，因此已提交的
    目录退役 / 改名 / 绑定漂移都不能把正常重放拒掉；实时资格只在**新键**分支另做。
    """
    if body.member_id is not None or body.expected_credential_version is not None:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    try:
        role_name = normalize_role_name(body.role_name)
    except ValueError as exc:
        raise _fail(_UNPROCESSABLE, "role_name_invalid") from exc
    try:
        # R1-4 补正：``runner_id`` 消费者与注册入口（``POST /api/runners`` ->
        # ``RunnerCreate``）**同源**用 ``normalize_runner_id``（slug、≤64）。此前这里用
        # ``normalize_safe_identifier_token``，其凭据启发式（连续 ≥40 token 字符）会命中本
        # 仓库自己的生成规则 ``runner:<runtime[:24]>-<sha256[:32]>``，导致“登记成功、
        # 创建恒 422”。这里仍是**纯载荷**归一（不查库、不加“已登记豁免”），首次实时资格
        # 依旧只在新键分支的 ``_normalize_create_intent`` 里做。
        runner_id = normalize_runner_id(body.runner_id)
        choice_id = normalize_safe_identifier_token(body.choice_id, field="choice_id")
        role_description = normalize_role_description(body.role_description)
    except ValueError as exc:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID) from exc
    return {
        "payload": {
            "role_name": role_name,
            "runner_id": runner_id,
            "choice_id": choice_id,
            "role_description": role_description,
        },
        "fingerprint": build_role_creation_fingerprint(
            project_id=project_id,
            role_name=role_name,
            runner_id=runner_id,
            choice_id=choice_id,
            role_description=role_description,
        ),
        # R1-4c-a：意图维度的规范布尔值（None→False）。**独立落列、不进共享创建
        # 指纹**；同 request_key 重放时严格比较，异值 409 ``role_request_key_conflict``。
        "auto_start": bool(body.auto_start),
        "choice_snapshot": None,
        "role_name": role_name,
        "member_id": None,
        "expected_credential_version": None,
    }


def _normalize_create_intent(
    project_id: str, body: RoleRequestCreate, session: Session
) -> dict:
    """纯载荷 + **实时**目录 / 冻结六维快照（仅新键分支调用）。"""
    normalized = _pure_create_intent(project_id, body)
    payload = normalized["payload"]
    runner_id = payload["runner_id"]
    choice_id = payload["choice_id"]

    runner = session.get(RunnerRegistry, runner_id)
    if runner is None:
        raise _fail(_NOT_FOUND, "runner_not_found")
    choice = session.get(RunnerModelChoice, choice_id)
    if choice is None or choice.runner_id != runner_id:
        raise _fail(_NOT_FOUND, "choice_not_found")
    if runner.adapter_status == RUNNER_ADAPTER_RETIRED:
        raise _fail(_CONFLICT, "runner_retired")
    if choice.retired_at is not None:
        raise _fail(_CONFLICT, "choice_retired")

    normalized["choice_snapshot"] = {
        "choice_id": choice.choice_id,
        "runner_id": choice.runner_id,
        "runtime": runner.runtime,
        "model_source": choice.model_source,
        "provider_id": choice.provider_id,
        "connection_ref": choice.connection_ref,
        "model_id": choice.model_id,
        "model_alias": choice.model_alias or "",
        "model_display_name": choice.model_display_name,
        "binding_fingerprint": binding_fingerprint(
            {
                "runner_id": choice.runner_id,
                "runtime": runner.runtime,
                "model_source": choice.model_source,
                "provider_id": choice.provider_id,
                "connection_ref": choice.connection_ref,
                "model_id": choice.model_id,
            }
        ),
    }
    return normalized


def _pure_recover_intent(project_id: str, body: RoleRequestCreate) -> dict:
    """recover 意图的**纯载荷**归一化（合同 §2/§7）：只覆盖成员与固定期望版本。

    不读当前角色版本 / 原创建操作，因此轮换后的正常重放不会被“before 与 current 比对”
    拒绝；实时资格只在**新键**分支另做。
    """
    if any(
        value is not None
        for value in (body.role_name, body.runner_id, body.choice_id, body.role_description)
    ):
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    # R1-4c-a：recover 载荷互斥——``auto_start`` 非 None 一律 422；恢复只修复，
    # 本身不自动启动。
    if body.auto_start is not None:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    if not isinstance(body.member_id, str) or not body.member_id.strip():
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    member_id = body.member_id.strip()
    version = body.expected_credential_version
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    return {
        "payload": {
            "member_id": member_id,
            "expected_credential_version": version,
        },
        "fingerprint": build_role_recovery_fingerprint(
            project_id=project_id,
            member_id=member_id,
            expected_credential_version=version,
        ),
        "auto_start": False,
        "choice_snapshot": None,
        "role_name": None,
        "member_id": member_id,
        "expected_credential_version": version,
        "origin_operation_key": None,
    }


def _normalize_recover_intent(
    project_id: str, body: RoleRequestCreate, session: Session
) -> dict:
    """纯载荷 + **实时**角色 / 成员 / 原创建操作资格（仅新键分支调用）。

    ``origin_operation_key`` 由服务端按 ``(project_id, member_id)`` 解析，调用者不能指定。
    """
    normalized = _pure_recover_intent(project_id, body)
    member_id = normalized["member_id"]
    version = normalized["expected_credential_version"]

    role = session.get(ProjectRole, (project_id, member_id))
    if role is None or role.archived_at is not None:
        raise _fail(_NOT_FOUND, "role_not_found")
    if role.origin != PROJECT_ROLE_ORIGIN_MANAGED:
        # imported/legacy 身份不得借恢复扩大边界（与配置入口同一稳定错误码）。
        raise _fail(_CONFLICT, "provision_imported_identity_unsupported")
    if not role.identity_exclusive:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_ROLE_CONFLICT)
    member = session.get(Member, member_id)
    if member is None or member.kind != "agent":
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_ROLE_CONFLICT)
    if member.disabled_at is not None:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_ROLE_CONFLICT)
    if session.get(ProjectAgent, (project_id, member_id)) is None:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_ROLE_CONFLICT)
    operation = session.exec(
        select(RoleCreationOperation)
        .where(RoleCreationOperation.project_id == project_id)
        .where(RoleCreationOperation.member_id == member_id)
    ).first()
    if operation is None:
        # imported/legacy（有名册行但没有创建操作）不得借恢复扩大边界。
        raise _fail(_CONFLICT, "provision_imported_identity_unsupported")
    if int(role.credential_version or 1) != version:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_CREDENTIAL_MISMATCH)

    normalized["role_name"] = role.role_name
    normalized["origin_operation_key"] = operation.operation_key
    return normalized


def _active_rows(
    project_id: str, session: Session, *, kind: Optional[str] = None
) -> list[RoleProvisionRequestRow]:
    statement = (
        select(RoleProvisionRequestRow)
        .where(RoleProvisionRequestRow.project_id == project_id)
        .where(RoleProvisionRequestRow.status.in_(ROLE_REQUEST_ACTIVE_STATUSES))
    )
    if kind is not None:
        statement = statement.where(RoleProvisionRequestRow.kind == kind)
    return list(session.exec(statement).all())


def _supersedable(
    row: RoleProvisionRequestRow,
    config: Optional[RoleProvisionHostConfig],
    now: datetime,
) -> bool:
    """旧 recover 行可被人类新意图原子替代的条件（合同 §7）。

    必须是**已经领取过**并已失效的 ``leased``/``created``；没有租约的 ``requested``
    是待执行，不能仅因 ``expires_at`` 为空就当作过期随意替代（应由 human 显式 cancel）。
    """
    if int(row.lease_generation or 0) <= 0:
        return False
    if row.status not in (ROLE_REQUEST_STATUS_LEASED, ROLE_REQUEST_STATUS_CREATED):
        return False
    return not lease_valid(row, config, now)


def _enforce_occupancy(
    project_id: str,
    *,
    kind: str,
    role_name: Optional[str],
    member_id: Optional[str],
    session: Session,
    config: Optional[RoleProvisionHostConfig],
    now: datetime,
    ignore_request_key: Optional[str] = None,
    allow_supersede: bool = True,
) -> Optional[RoleProvisionRequestRow]:
    """跨 kind 同角色占用检查（合同 §2/§5/§7）。返回需要原子 supersede 的旧行。

    - ``create``：同名活动意图或同名活动角色都算占用（角色尚未创建时保留同名保护）；
    - ``recover``：以**稳定成员锚点** ``member_id`` 判“同成员”占用（活动 create 行的
      ``member_id`` 在创建成功时同事务回填，因此目标角色后来改名也不能绕过）；尚未
      创建的 create 行仍按同名保护；
    - ``allow_supersede`` 只在 A4 人类新意图路径为真（允许原子替代**租约已失效**的旧
      recover 行）；claim / resume 一律为假，旧 resume 不得夺回新请求资格。
    """
    obsolete: Optional[RoleProvisionRequestRow] = None
    for row in _active_rows(project_id, session):
        if ignore_request_key is not None and row.request_key == ignore_request_key:
            continue
        if kind == ROLE_REQUEST_KIND_CREATE:
            target = (
                session.get(ProjectRole, (project_id, row.member_id))
                if row.member_id
                else None
            )
            same_role = (
                target is not None
                and target.archived_at is None
                and role_name is not None
                and target.role_name == role_name
            ) or (
                row.kind == ROLE_REQUEST_KIND_CREATE
                and role_name is not None
                and row.role_name == role_name
            )
            if same_role:
                raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_ROLE_CONFLICT)
        else:
            same_member = member_id is not None and row.member_id == member_id
            if row.kind == ROLE_REQUEST_KIND_RECOVER and same_member:
                if allow_supersede and _supersedable(row, config, now):
                    obsolete = row
                    continue
                raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_ROLE_CONFLICT)
            if row.kind == ROLE_REQUEST_KIND_CREATE and (
                same_member
                or (role_name is not None and row.role_name == role_name)
            ):
                raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_ROLE_CONFLICT)
    return obsolete


def _supersede_row(
    row: RoleProvisionRequestRow, session: Session, now: datetime
) -> None:
    """原子替代旧失效 recover：保留行与执行记录，清掉旧资格。"""
    row.status = ROLE_REQUEST_STATUS_CANCELED
    row.last_error_code = ROLE_REQUEST_ERROR_SUPERSEDED
    row.lease_token_hash = None
    row.lease_expires_at = None
    row.revision = int(row.revision or 1) + 1
    row.updated_at = now
    row.finished_at = now
    session.add(row)


def create_request_intent(
    project_id: str,
    body: RoleRequestCreate,
    *,
    caller: Member,
    session: Session,
) -> tuple[dict, bool]:
    """A4：创建 / 幂等重放创建或恢复意图。返回 ``(projection, reused)``。"""
    if body.kind not in ROLE_REQUEST_KINDS:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_KIND_INVALID)
    if not body.confirm:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_CONFIRM_REQUIRED)
    request_key = _normalize_request_key(body.request_key)
    kind = body.kind

    write_begin(session)
    try:
        _require_project(project_id, session)
        # F2 补正（合同 §6）：**先**做纯载荷归一化 / 指纹与既有键重放判断，重放判定不依赖
        # 当前 choice 是否退役、当前角色是否已轮换；只有新键分支才做实时目录 / 角色版本 /
        # 占用 / 新快照校验，因此不绕过首次真实 create 的冻结快照与实时资格。
        pure = (
            _pure_create_intent(project_id, body)
            if kind == ROLE_REQUEST_KIND_CREATE
            else _pure_recover_intent(project_id, body)
        )
        existing = session.get(RoleProvisionRequestRow, request_key)
        if existing is not None:
            if (
                existing.project_id != project_id
                or existing.kind != kind
                or existing.request_fingerprint != pure["fingerprint"]
                # R1-4c-a：共享四字段 payload / 指纹不变，意图维度在行内单独严格
                # 比较；异值 409（旧行默认 0 = 缺省 false，与旧客户端重放兼容）。
                or bool(int(existing.auto_start_intent or 0))
                != bool(pure["auto_start"])
            ):
                raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_KEY_CONFLICT)
            projection = request_projection(
                existing, session=session, now=_now(), config=load_host_config(project_id, session)
            )
            _rollback(session)  # 只读重放：不重建、不刷新快照，立即释放写锁
            return projection, True

        normalized = (
            _normalize_create_intent(project_id, body, session)
            if kind == ROLE_REQUEST_KIND_CREATE
            else _normalize_recover_intent(project_id, body, session)
        )

        # 键冲突：create 不得占用既有旧人工创建操作键；recover 使用全新键。
        if kind == ROLE_REQUEST_KIND_CREATE:
            if session.get(RoleCreationOperation, request_key) is not None:
                raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_OPERATION_CONFLICT)
        elif session.get(RoleCreationOperation, request_key) is not None:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_KEY_CONFLICT)

        now = _now()
        config = load_host_config(project_id, session)
        if kind == ROLE_REQUEST_KIND_CREATE:
            live = session.exec(
                select(ProjectRole)
                .where(ProjectRole.project_id == project_id)
                .where(ProjectRole.role_name == normalized["role_name"])
                .where(ProjectRole.archived_at.is_(None))
            ).first()
            if live is not None:
                raise _fail(_CONFLICT, "role_name_conflict")

        obsolete = _enforce_occupancy(
            project_id,
            kind=kind,
            role_name=normalized["role_name"],
            member_id=normalized["member_id"],
            session=session,
            config=config,
            now=now,
        )
        row = RoleProvisionRequestRow(
            request_key=request_key,
            project_id=project_id,
            kind=kind,
            payload=normalized["payload"],
            request_fingerprint=normalized["fingerprint"],
            choice_snapshot=normalized["choice_snapshot"],
            role_name=normalized["role_name"],
            member_id=normalized["member_id"],
            origin_operation_key=normalized.get("origin_operation_key"),
            expected_credential_version=normalized["expected_credential_version"],
            status=ROLE_REQUEST_STATUS_REQUESTED,
            revision=1,
            attempts=0,
            lease_generation=0,
            lease_token_hash=None,
            lease_host=None,
            lease_claimed_at=None,
            lease_expires_at=None,
            lease_config_version=None,
            report_outcome=None,
            report_revision=None,
            report_credential_version=None,
            last_error_code=None,
            # R1-4c-a：有意图则记 pending（尚未到配置成功）；无意图保持 NULL。
            auto_start_intent=1 if normalized["auto_start"] else 0,
            auto_start_status=(
                ROLE_AUTO_START_STATUS_PENDING if normalized["auto_start"] else None
            ),
            auto_start_launch_id=None,
            auto_start_error_code=None,
            created_by=caller.id,
            created_at=now,
            updated_at=now,
            finished_at=None,
        )
        session.add(row)
        if obsolete is not None:
            _supersede_row(obsolete, session, now)
        session.commit()
        session.refresh(row)
        return (
            request_projection(
                row, session=session, now=now, config=load_host_config(project_id, session)
            ),
            False,
        )
    except HTTPException:
        _rollback(session)
        raise
    except Exception as exc:  # noqa: BLE001 - 失败零残留（部分唯一索引竞争也收敛为冲突）
        _rollback(session)
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_ROLE_CONFLICT) from exc


# ── 租约判定与投影（A5–A8）──────────────────────────────────────────────


def lease_valid(
    row: RoleProvisionRequestRow,
    config: Optional[RoleProvisionHostConfig],
    now: datetime,
) -> bool:
    """有效租约：项目启用 + ``config_version`` 未换代 + 未到期 + 世代/哈希齐全。"""
    if config is None or not config.enabled:
        return False
    if not row.lease_token_hash or int(row.lease_generation or 0) <= 0:
        return False
    if row.lease_config_version is None or int(row.lease_config_version) != int(
        config.config_version
    ):
        return False
    expires_at = _as_utc(row.lease_expires_at)
    if expires_at is None or now > expires_at:
        return False
    return True


def retry_exhausted(
    row: RoleProvisionRequestRow,
    config: Optional[RoleProvisionHostConfig],
    now: datetime,
) -> bool:
    _, _, max_attempts = _budgets(config)
    return int(row.attempts or 0) >= max_attempts and not lease_valid(row, config, now)


def is_claimable(
    row: RoleProvisionRequestRow,
    config: Optional[RoleProvisionHostConfig],
    now: datetime,
) -> bool:
    if config is None or not config.enabled:
        return False
    if row.status not in ROLE_REQUEST_CLAIMABLE_STATUSES:
        return False
    if lease_valid(row, config, now):
        return False
    return not retry_exhausted(row, config, now)


def expected_binding_fingerprint(
    row: RoleProvisionRequestRow, session: Session
) -> Optional[str]:
    """预期绑定指纹：已有成员用原创建操作的六维；未创建直接用意图快照。"""
    if row.origin_operation_key:
        operation = session.get(RoleCreationOperation, row.origin_operation_key)
        if operation is None:
            return None
        choice = session.get(RunnerModelChoice, operation.choice_id)
        if choice is None:
            return None
        runner = session.get(RunnerRegistry, choice.runner_id)
        return binding_fingerprint(
            {
                "runner_id": choice.runner_id,
                "runtime": runner.runtime if runner is not None else None,
                "model_source": choice.model_source,
                "provider_id": choice.provider_id,
                "connection_ref": choice.connection_ref,
                "model_id": choice.model_id,
            }
        )
    snapshot = row.choice_snapshot or {}
    value = snapshot.get("binding_fingerprint")
    return value if isinstance(value, str) else None


def request_projection(
    row: RoleProvisionRequestRow,
    *,
    session: Session,
    now: datetime,
    config: Optional[RoleProvisionHostConfig],
) -> dict:
    """公共投影**严格白名单**（合同 §4）：不含 token/哈希/路径/argv/异常正文。"""
    payload = dict(row.payload or {})
    role = (
        session.get(ProjectRole, (row.project_id, row.member_id))
        if row.member_id
        else None
    )
    member = session.get(Member, row.member_id) if row.member_id else None
    operation = (
        session.get(RoleCreationOperation, row.origin_operation_key)
        if row.origin_operation_key
        else None
    )
    held = lease_valid(row, config, now)
    exhausted = retry_exhausted(row, config, now)
    if row.kind == ROLE_REQUEST_KIND_CREATE:
        role_name = row.role_name or payload.get("role_name")
        role_description = payload.get("role_description")
        runner_id = payload.get("runner_id")
        choice_id = payload.get("choice_id")
    else:
        role_name = role.role_name if role is not None else None
        role_description = None
        runner_id = operation.runner_id if operation is not None else None
        choice_id = operation.choice_id if operation is not None else None

    effective_status = row.status
    if (
        row.status == ROLE_REQUEST_STATUS_LEASED
        and member is None
        and not held
    ):
        effective_status = ROLE_REQUEST_STATUS_REQUESTED

    job = (
        session.get(RoleProvisionJob, row.origin_operation_key)
        if row.origin_operation_key
        else None
    )
    projection = {
        "request_key": row.request_key,
        "project_id": row.project_id,
        "kind": row.kind,
        "status": row.status,
        "effective_status": effective_status,
        "revision": int(row.revision or 1),
        "attempts": int(row.attempts or 0),
        "role_name": role_name,
        "role_description": role_description,
        "runner_id": runner_id,
        "choice_id": choice_id,
        "member_id": row.member_id,
        "origin_operation_key": row.origin_operation_key,
        "credential_version": int(role.credential_version) if role is not None else None,
        "lease_held": held,
        "claimable": is_claimable(row, config, now),
        "retry_exhausted": exhausted,
        "lease_host": row.lease_host,
        "claimed_at": _as_utc(row.lease_claimed_at),
        "expires_at": _as_utc(row.lease_expires_at),
        "last_error_code": row.last_error_code,
        # R1-4c-a（AUTO_START_DESIGN §6.4）：意图/投递事实的只读投影。只增这 4 个
        # 白名单字段；不回显 ``auto_start_intent`` 原始 int、token/哈希/路径/argv/
        # 异常正文。``enqueued`` 不等于 ready，``pending`` 不等于已启动。
        "auto_start": bool(int(row.auto_start_intent or 0)),
        "auto_start_status": row.auto_start_status,
        "auto_start_launch_id": row.auto_start_launch_id,
        "auto_start_error_code": row.auto_start_error_code,
        "created_by": row.created_by,
        "created_at": _as_utc(row.created_at),
        "updated_at": _as_utc(row.updated_at),
        "finished_at": _as_utc(row.finished_at),
        "provision_job": (
            serialize_provision_job(
                job,
                role_credential_version=(
                    int(role.credential_version) if role is not None else None
                ),
                expected_binding_fingerprint=expected_binding_fingerprint(row, session),
            )
            if job is not None
            else None
        ),
    }
    return projection


def _require_request(
    project_id: str, request_key: str, session: Session
) -> RoleProvisionRequestRow:
    row = session.get(RoleProvisionRequestRow, request_key)
    if row is None or row.project_id != project_id:
        raise _fail(_NOT_FOUND, ROLE_REQUEST_ERROR_NOT_FOUND)
    return row


def get_request(
    project_id: str, request_key: str, session: Session
) -> dict:
    """A8：只读请求 + 实际作业进度。"""
    key = _normalize_request_key(request_key)
    _require_project(project_id, session)
    row = _require_request(project_id, key, session)
    return request_projection(
        row,
        session=session,
        now=_now(),
        config=load_host_config(project_id, session),
    )


def list_requests(
    project_id: str,
    *,
    status_filter: Optional[str],
    claimable_filter: Optional[bool],
    limit: int,
    session: Session,
) -> list[dict]:
    """A7：只读发现。过滤与投影按**同一个 now**计算；不写库。"""
    _require_project(project_id, session)
    if status_filter is not None and status_filter not in (
        ROLE_REQUEST_STATUS_REQUESTED,
        ROLE_REQUEST_STATUS_LEASED,
        ROLE_REQUEST_STATUS_CREATED,
        ROLE_REQUEST_STATUS_PROVISIONED,
        ROLE_REQUEST_STATUS_FAILED,
        ROLE_REQUEST_STATUS_CANCELED,
    ):
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    limit = min(int(limit), ROLE_REQUEST_LIST_LIMIT_MAX)

    now = _now()
    config = load_host_config(project_id, session)
    rows = session.exec(
        select(RoleProvisionRequestRow)
        .where(RoleProvisionRequestRow.project_id == project_id)
        .order_by(RoleProvisionRequestRow.created_at, RoleProvisionRequestRow.request_key)
    ).all()
    projections = [
        request_projection(row, session=session, now=now, config=config)
        for row in rows
        if status_filter is None or row.status == status_filter
    ]
    if claimable_filter is not None:
        projections = [
            item for item in projections if bool(item["claimable"]) == claimable_filter
        ]
    return projections[:limit]


# ── 领取 / 取消 / 续跑 / 回报（A5/A9/A10/A6）─────────────────────────────


def claim_request(
    project_id: str,
    request_key: str,
    *,
    host: str,
    expected_revision: int,
    lease_seconds: Optional[int],
    session: Session,
) -> dict:
    """A5：领取或失效后重领，签发**新世代**与一次性 token。"""
    key = _normalize_request_key(request_key)
    # host 只是路由标签（认证仍是 human Key）；先按当前 host_label 规则规范化，
    # 再在写锁内与 config.host_label 比对（F1，合同 §5）。
    host_label = _normalize_host_label(host)
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)

    write_begin(session)
    try:
        _require_project(project_id, session)
        row = _require_request(project_id, key, session)
        config = load_host_config(project_id, session)
        now = _now()
        if config is None or not config.enabled:
            raise _fail(_CONFLICT, ROLE_PROVISION_HOST_ERROR_DISABLED)
        if row.revision != expected_revision:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_REVISION_CONFLICT)
        # F1 补正：错标签必须在签发 token 前拒绝，请求 / 租约 / attempts / revision 零变更。
        if not config.host_label or host_label != config.host_label:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_HOST_MISMATCH)
        if row.status not in ROLE_REQUEST_CLAIMABLE_STATUSES:
            if retry_exhausted(row, config, now):
                raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_STATUS_CONFLICT)
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_STATUS_CONFLICT)
        if retry_exhausted(row, config, now):
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_STATUS_CONFLICT)
        if lease_valid(row, config, now):
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_CONFLICT)

        # 合同 §5：claim 与 A4/resume 共用同一份跨 kind 占用规则；claim **不**允许替代
        # 任何旧行（allow_supersede=False），避免旧资格被领取时挤掉新意图。
        occupancy_role = (
            session.get(ProjectRole, (project_id, row.member_id))
            if row.member_id
            else None
        )
        _enforce_occupancy(
            project_id,
            kind=row.kind,
            role_name=(
                occupancy_role.role_name
                if row.kind == ROLE_REQUEST_KIND_RECOVER and occupancy_role is not None
                else row.role_name
            ),
            member_id=row.member_id,
            session=session,
            config=config,
            now=now,
            ignore_request_key=row.request_key,
            allow_supersede=False,
        )

        budget_seconds, max_active, _ = _budgets(config)
        seconds = budget_seconds
        if lease_seconds is not None:
            if (
                isinstance(lease_seconds, bool)
                or not isinstance(lease_seconds, int)
                or not (
                    ROLE_PROVISION_HOST_LEASE_SECONDS_MIN
                    <= lease_seconds
                    <= ROLE_PROVISION_HOST_LEASE_SECONDS_MAX
                )
            ):
                raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_LEASE_SECONDS_INVALID)
            if lease_seconds > budget_seconds:
                raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_LEASE_SECONDS_INVALID)
            seconds = int(lease_seconds)

        held = 0
        for other in session.exec(
            select(RoleProvisionRequestRow).where(
                RoleProvisionRequestRow.project_id == project_id
            )
        ).all():
            if other.request_key == row.request_key:
                continue
            if lease_valid(other, config, now):
                held += 1
        if held >= max_active:
            raise _fail(_CONFLICT, ROLE_PROVISION_HOST_ERROR_BUSY)

        member = session.get(Member, row.member_id) if row.member_id else None
        token = new_role_provision_lease_token()
        row.lease_generation = int(row.lease_generation or 0) + 1
        row.lease_token_hash = hash_role_provision_lease_token(token)
        row.lease_host = host_label
        row.lease_claimed_at = now
        row.lease_expires_at = now + timedelta(seconds=seconds)
        row.lease_config_version = int(config.config_version)
        row.attempts = int(row.attempts or 0) + 1
        row.status = (
            ROLE_REQUEST_STATUS_CREATED if member is not None else ROLE_REQUEST_STATUS_LEASED
        )
        row.revision = int(row.revision or 1) + 1
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        projection = request_projection(
            row, session=session, now=now, config=load_host_config(project_id, session)
        )
        role = (
            session.get(ProjectRole, (project_id, row.member_id))
            if row.member_id
            else None
        )
        projection.update(
            {
                "payload": dict(row.payload or {}),
                "choice_snapshot": dict(row.choice_snapshot)
                if row.choice_snapshot
                else None,
                "credential_version": (
                    int(role.credential_version) if role is not None else None
                ),
                "expected_binding_fingerprint": expected_binding_fingerprint(
                    row, session
                ),
                "lease_generation": int(row.lease_generation),
                "lease_config_version": int(row.lease_config_version or 0),
                # 唯一一次明文投递点；响应**不含**角色 Key。
                "lease_token": token,
            }
        )
        return projection
    except HTTPException:
        _rollback(session)
        raise
    except Exception as exc:  # noqa: BLE001
        _rollback(session)
        raise _fail(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "role_request_claim_failed"
        ) from exc


def cancel_request(
    project_id: str,
    request_key: str,
    *,
    expected_revision: int,
    session: Session,
) -> dict:
    """A9：仅**未创建成员**的 requested/leased/failed 可取消。"""
    key = _normalize_request_key(request_key)
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)

    write_begin(session)
    try:
        _require_project(project_id, session)
        row = _require_request(project_id, key, session)
        if row.revision != expected_revision:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_REVISION_CONFLICT)
        if row.status in (
            ROLE_REQUEST_STATUS_PROVISIONED,
            ROLE_REQUEST_STATUS_CANCELED,
        ):
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_STATUS_CONFLICT)
        if row.member_id and session.get(Member, row.member_id) is not None:
            # 成员事实已提交：cancel 不假装删除（合同 §9“创建先提交”分支）。
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_MEMBER_CREATED)
        if row.status not in (
            ROLE_REQUEST_STATUS_REQUESTED,
            ROLE_REQUEST_STATUS_LEASED,
            ROLE_REQUEST_STATUS_FAILED,
        ):
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_CANCEL_REFUSED)

        now = _now()
        row.status = ROLE_REQUEST_STATUS_CANCELED
        row.last_error_code = None
        row.lease_token_hash = None
        row.revision = int(row.revision or 1) + 1
        row.updated_at = now
        row.finished_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        return request_projection(
            row, session=session, now=now, config=load_host_config(project_id, session)
        )
    except HTTPException:
        _rollback(session)
        raise
    except Exception as exc:  # noqa: BLE001
        _rollback(session)
        raise _fail(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "role_request_cancel_failed"
        ) from exc


def resume_request(
    project_id: str,
    request_key: str,
    *,
    expected_revision: int,
    confirm: bool,
    session: Session,
) -> dict:
    """A10：失败或领取次数耗尽且租约无效时的人工续跑；占用复查、清旧资格、世代 +1。"""
    key = _normalize_request_key(request_key)
    if not confirm:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_CONFIRM_REQUIRED)
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)

    write_begin(session)
    try:
        _require_project(project_id, session)
        row = _require_request(project_id, key, session)
        if row.revision != expected_revision:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_REVISION_CONFLICT)
        if row.status in (
            ROLE_REQUEST_STATUS_PROVISIONED,
            ROLE_REQUEST_STATUS_CANCELED,
        ):
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_NOT_RESUMABLE)
        now = _now()
        config = load_host_config(project_id, session)
        exhausted = retry_exhausted(row, config, now)
        if row.status == ROLE_REQUEST_STATUS_FAILED:
            # 宿主已明确回报失败（合同 §9）：人工可立即续跑并清旧资格。
            pass
        elif exhausted:
            # 次数耗尽且租约无效（``retry_exhausted`` 的定义已包含租约失效）。
            pass
        else:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_NOT_RESUMABLE)

        # 旧 resume 不得夺回新意图资格：占用在同一写锁内复查（忽略自身），并**禁止**
        # 替代任何其它活动行（allow_supersede=False）——新意图即使租约失效也由人类显式
        # 处理，不由旧 resume 静默夺回。
        _enforce_occupancy(
            project_id,
            kind=row.kind,
            role_name=row.role_name,
            member_id=row.member_id,
            session=session,
            config=config,
            now=now,
            ignore_request_key=row.request_key,
            allow_supersede=False,
        )
        member = session.get(Member, row.member_id) if row.member_id else None
        row.status = (
            ROLE_REQUEST_STATUS_CREATED if member is not None else ROLE_REQUEST_STATUS_REQUESTED
        )
        row.attempts = 0
        row.lease_token_hash = None
        row.lease_host = None
        row.lease_claimed_at = None
        row.lease_expires_at = None
        row.lease_config_version = None
        row.lease_generation = int(row.lease_generation or 0) + 1
        row.report_outcome = None
        row.report_revision = None
        row.report_credential_version = None
        row.last_error_code = None
        row.revision = int(row.revision or 1) + 1
        row.updated_at = now
        row.finished_at = None
        session.add(row)
        session.commit()
        session.refresh(row)
        return request_projection(
            row, session=session, now=now, config=load_host_config(project_id, session)
        )
    except HTTPException:
        _rollback(session)
        raise
    except Exception as exc:  # noqa: BLE001
        _rollback(session)
        raise _fail(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "role_request_resume_failed"
        ) from exc


def expected_completion_generation(
    row: RoleProvisionRequestRow, session: Session
) -> Optional[int]:
    """本次请求的**执行预期代际**（合同 §8）：create=1；recover=已执行 after 或固定 before。"""
    if row.kind == ROLE_REQUEST_KIND_CREATE:
        return 1
    rotation = session.get(RoleCredentialRotation, row.request_key)
    if rotation is not None:
        return int(rotation.after_credential_version)
    if row.expected_credential_version is None:
        return None
    return int(row.expected_credential_version)


def require_completion_facts(
    row: RoleProvisionRequestRow, session: Session
) -> None:
    """report(provisioned) 的事实核验（合同 §8）：缺任一事实即 409，零写入。"""
    if not row.member_id:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    member = session.get(Member, row.member_id)
    role = session.get(ProjectRole, (row.project_id, row.member_id))
    if member is None or member.kind != "agent" or member.disabled_at is not None:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    if role is None or role.archived_at is not None:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    if session.get(ProjectAgent, (row.project_id, row.member_id)) is None:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    if not row.origin_operation_key:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    operation = session.get(RoleCreationOperation, row.origin_operation_key)
    if (
        operation is None
        or operation.project_id != row.project_id
        or operation.member_id != row.member_id
    ):
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    if row.kind == ROLE_REQUEST_KIND_CREATE:
        if operation.request_fingerprint != row.request_fingerprint:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    job = session.get(RoleProvisionJob, row.origin_operation_key)
    if job is None:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    steps = normalize_provision_steps(job.steps)
    states = [steps[step]["state"] for step in PROVISION_STEP_ORDER]
    if PROVISION_STEP_STATE_FAILED in states or PROVISION_STEP_STATE_PENDING in states:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    if job.status != PROVISION_JOB_STATUS_SUCCEEDED:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE)
    current_version = int(role.credential_version or 1)
    if int(job.credential_version or 1) != current_version:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_CREDENTIAL_STALE)
    expected = expected_completion_generation(row, session)
    if expected is None or current_version != int(expected):
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_CREDENTIAL_STALE)


# ── 配置成功后的自动首次启动（R1-4c-a，AUTO_START_DESIGN §3/§4）───────────

#: ``_set_auto_start`` 的 ``launch_id`` 缺省哨兵：不覆盖既有锚点列。
_AUTO_START_LAUNCH_KEEP = object()


def _set_auto_start(
    session: Session,
    request_key: str,
    *,
    status: Optional[str],
    code: Optional[str],
    now: datetime,
    launch_id: object = _AUTO_START_LAUNCH_KEEP,
) -> None:
    """Core UPDATE 写 ``auto_start_*`` 列（AUTO_START_DESIGN §4/§5.3）。

    统一走 Core UPDATE + ``synchronize_session=False``，避免保存点回滚后的 ORM
    内存脏值被误回写；报告路径在外层 ``commit`` 后 ``session.refresh(row)`` 按
    实际落库值刷新投影，因此这里不做 ORM 赋值。
    """
    values: dict = {
        "auto_start_status": status,
        "auto_start_error_code": code,
        "updated_at": now,
    }
    if launch_id is not _AUTO_START_LAUNCH_KEEP:
        values["auto_start_launch_id"] = launch_id
    session.execute(
        update(RoleProvisionRequestRow)
        .where(RoleProvisionRequestRow.request_key == request_key)
        .values(**values)
        .execution_options(synchronize_session=False)
    )


def _outer_write_transaction_alive(
    session: Session, row: RoleProvisionRequestRow
) -> bool:
    """入队保存点失败后，确认**外层写事务与已 flush 报告事实**仍然成立。

    只有同时满足才允许把入队失败降级为 ``failed/auto_start_enqueue_failed``：

    1. driver 级真实事务仍活动（``BEGIN IMMEDIATE`` 取得的外层写事务未被
       RAISE(ROLLBACK)/连接失效撤销——ORM 的 ``Session.in_transaction`` 只是
       逻辑记账，不能证明底层连接仍持有事务，与 ``begin_immediate_write``
       同一判定口径）；
    2. 能在**同一事务内**读到本请求已 flush 的 ``provisioned`` 终态（读不到
       说明外层事实已被撤销或读到的是旧已提交数据）。

    任一不成立即返回 ``False``：外层损坏必须整体回滚、按错误协议 500，绝不在
    新事务里补写任何 auto 状态再 commit。按事务真实状态判定，不按异常字符串
    或 SQLite 错误文案分类。
    """
    connection = session.connection()
    driver = connection.connection.driver_connection
    if driver is None or not bool(getattr(driver, "in_transaction", False)):
        return False
    status = connection.execute(
        select(RoleProvisionRequestRow.status).where(
            RoleProvisionRequestRow.request_key == row.request_key
        )
    ).scalar_one_or_none()
    return status == ROLE_REQUEST_STATUS_PROVISIONED


def _auto_start_after_provision(
    row: RoleProvisionRequestRow,
    *,
    session: Session,
    config: Optional[RoleProvisionHostConfig],
    now: datetime,
) -> None:
    """report(provisioned) 成功分支内的自动首次启动段（AUTO_START_DESIGN §3/§4）。

    仅**新 create 意图 + 首次有效 report(provisioned)** 会到达这里（外层已 flush
    配置终态与 report 代际，重复/迟到精确重放早在外层只读返回）。判定顺序：

    1. ``auto_start_intent == 0``（旧请求/旧客户端/recover）→ 保持原行为；
    2. 幂等锚点已存在（防御）→ 不重复入队；
    3. 宿主配置未启用 → ``not_eligible`` + ``auto_start_config_disabled``；
    4. **人工意图优先**：该角色已有 ``RoleServiceState`` 行且 ``generation != 0``
       （任何已发生的人工 start/stop，含 stop-before-report）→ ``not_eligible``
       + ``auto_start_manual_intent_present``，零 launch、不覆盖人工世代；
    5. 其余交给共享入队核心（守卫拒绝翻译稳定码；可恢复写入异常回滚保存点后记
       ``failed/auto_start_enqueue_failed``）。

    入队的全部写（state CAS + launch INSERT，含实际 flush）都在**嵌套 SAVEPOINT**
    内：失败只回滚自己，配置完成事实（``status=provisioned`` 与 report 代际）照常
    随外层唯一提交点提交；外层提交失败整体回滚、按原错误协议 500，有效租约下同
    token/同 revision 可安全重试。配置 failed/canceled 绝不进入本段。

    可恢复降级有严格前提（``_outer_write_transaction_alive``）：保存点回滚后仍持有
    同一实际写事务、且已 flush 报告事实可读，才登记 ``failed/auto_start_enqueue_failed``；
    若保存点失败已撤销整个外层事务（如触发器 ``RAISE(ROLLBACK)``）或连接失效，
    不得在新事务里补写 auto 状态，原样上抛由外层 500 整体回滚、零残留。
    """
    if not int(row.auto_start_intent or 0):
        return  # 旧请求 / 旧客户端 / recover：无意图，行为与今日完全一致。
    if row.auto_start_launch_id:
        # 幂等锚点（防御分支）：已投递过，重复/迟到回报绝不产生第二次启动。
        _set_auto_start(
            session,
            row.request_key,
            status=ROLE_AUTO_START_STATUS_ENQUEUED,
            code=None,
            now=now,
        )
        return
    if config is None or not config.enabled:
        _set_auto_start(
            session,
            row.request_key,
            status=ROLE_AUTO_START_STATUS_NOT_ELIGIBLE,
            code=ROLE_REQUEST_ERROR_AUTO_START_CONFIG_DISABLED,
            now=now,
        )
        return
    state = session.get(RoleServiceState, (row.project_id, row.member_id))
    if state is not None and int(state.generation or 0) != 0:
        # 默认初始 stopped 不落状态行，与人工动作天然可区分；任何非零世代都
        # 保持原人工/服务动作，不推进新世代。
        _set_auto_start(
            session,
            row.request_key,
            status=ROLE_AUTO_START_STATUS_NOT_ELIGIBLE,
            code=ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT,
            now=now,
        )
        return

    savepoint = session.begin_nested()
    try:
        launch_id, code = enqueue_auto_start_launch(
            row.project_id, row.member_id, session=session, now=now
        )
    except Exception:  # noqa: BLE001 - 入队写入异常：先证明外层仍有效才允许降级
        # 降级前提：保存点回滚后仍持有同一实际写事务，且已 flush 的报告事实
        # 未被撤销（如 SQLite 触发器 RAISE(ROLLBACK) 已撤销整个外层事务）。
        # 外层已丢失/连接失效时不得在新事务里补写 auto 状态，原样上抛由外层
        # 整体回滚 500。注意保存点回滚前 Session 处于 flush 失败停用态，
        # 只能在此之后探测（同 begin_immediate_write 的 driver 级判定口径）。
        savepoint.rollback()
        if not _outer_write_transaction_alive(session, row):
            raise
        _set_auto_start(
            session,
            row.request_key,
            status=ROLE_AUTO_START_STATUS_FAILED,
            code=ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED,
            now=now,
        )
        return
    if launch_id:
        savepoint.commit()
        _set_auto_start(
            session,
            row.request_key,
            status=ROLE_AUTO_START_STATUS_ENQUEUED,
            code=None,
            now=now,
            launch_id=launch_id,
        )
    else:
        savepoint.rollback()
        _set_auto_start(
            session,
            row.request_key,
            status=(
                ROLE_AUTO_START_STATUS_FAILED
                if code == ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED
                else ROLE_AUTO_START_STATUS_NOT_ELIGIBLE
            ),
            code=code,
            now=now,
        )


def _is_exact_report_replay(
    row: RoleProvisionRequestRow,
    *,
    session: Session,
    outcome: str,
    expected_revision: int,
    normalized_error: Optional[str],
    token_hash: str,
) -> bool:
    """判断“同一次终态提交”的精确重放（合同 §8）。

    除 ``report_outcome`` / ``report_revision`` / 当前 token 外，还必须同时命中：
    规范化后的**实际错误结果**（``last_error_code`` 对 ``normalized_error``）、本次签发
    世代，以及**报告期凭据代际**（``report_credential_version`` 对角色当前版本）。
    因此异结果、非法输入、旧代（此后角色已被轮换/resume）都不算精确重放。
    """
    if row.report_outcome != outcome:
        return False
    if row.report_revision != expected_revision:
        return False
    if not row.lease_token_hash or not hmac.compare_digest(
        token_hash, row.lease_token_hash
    ):
        return False
    if int(row.lease_generation or 0) <= 0:
        return False
    if row.last_error_code != normalized_error:
        return False
    role = (
        session.get(ProjectRole, (row.project_id, row.member_id))
        if row.member_id
        else None
    )
    current_version = int(role.credential_version) if role is not None else None
    return current_version == row.report_credential_version


def report_request(
    project_id: str,
    request_key: str,
    *,
    lease_token: str,
    expected_revision: int,
    outcome: str,
    error_code: Optional[str],
    session: Session,
) -> dict:
    """A6：宿主回报完成/失败。终态**同一次提交**的精确重放只读返回。"""
    key = _normalize_request_key(request_key)
    if outcome not in ROLE_REQUEST_REPORT_OUTCOMES:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    if not isinstance(lease_token, str) or not lease_token:
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)

    write_begin(session)
    try:
        _require_project(project_id, session)
        row = _require_request(project_id, key, session)
        now = _now()
        config = load_host_config(project_id, session)
        token_hash = hash_role_provision_lease_token(lease_token)
        # F5 补正（合同 §8）：**先验证载荷**（含 error_code 白名单）再处理终态回放，
        # 非法错误输入不能被当成“精确重放”返回 200，也不会写入任何行。
        normalized_error = _normalize_request_error_code(outcome, error_code)

        if row.report_outcome is not None:
            if not _is_exact_report_replay(
                row,
                session=session,
                outcome=outcome,
                expected_revision=expected_revision,
                normalized_error=normalized_error,
                token_hash=token_hash,
            ):
                raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_STALE_REPORT)
            projection = request_projection(
                row, session=session, now=now, config=config
            )
            projection["replayed"] = True
            _rollback(session)  # 终态只读重放：不改任何行
            return projection

        if config is None or not config.enabled:
            raise _fail(_CONFLICT, ROLE_PROVISION_HOST_ERROR_DISABLED)
        if row.status not in ROLE_REQUEST_CLAIMABLE_STATUSES:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_STATUS_CONFLICT)
        if not row.lease_token_hash or not hmac.compare_digest(
            token_hash, row.lease_token_hash
        ):
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_INVALID)
        if int(row.lease_generation or 0) <= 0:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_INVALID)
        if row.lease_config_version is None or int(row.lease_config_version) != int(
            config.config_version
        ):
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_INVALID)
        expires_at = _as_utc(row.lease_expires_at)
        if expires_at is None or now > expires_at:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_INVALID)
        if row.revision != expected_revision:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_REVISION_CONFLICT)

        role = (
            session.get(ProjectRole, (project_id, row.member_id))
            if row.member_id
            else None
        )
        if outcome == ROLE_REQUEST_STATUS_PROVISIONED:
            require_completion_facts(row, session)
            row.status = ROLE_REQUEST_STATUS_PROVISIONED
            row.last_error_code = None
        else:
            row.status = ROLE_REQUEST_STATUS_FAILED
            row.last_error_code = normalized_error
        row.report_outcome = outcome
        row.report_revision = expected_revision
        row.report_credential_version = (
            int(role.credential_version) if role is not None else None
        )
        # 终态不再持有并发名额：释放时间窗但**保留** token 哈希与世代，
        # 以便“同一次提交的精确重放”仍能被识别为只读回放（§8）。
        row.lease_expires_at = now
        row.revision = int(row.revision or 1) + 1
        row.updated_at = now
        row.finished_at = now
        session.add(row)
        # R1-4c-a：先让外层配置终态与 report 代际进入同一事务，再开 SAVEPOINT
        # 做自动启动入队——入队失败只回滚自己，不会把未 flush 的外层改动卷进去。
        session.flush()
        if outcome == ROLE_REQUEST_STATUS_PROVISIONED and row.kind == ROLE_REQUEST_KIND_CREATE:
            _auto_start_after_provision(row, session=session, config=config, now=now)
        session.commit()
        session.refresh(row)
        projection = request_projection(
            row, session=session, now=now, config=load_host_config(project_id, session)
        )
        projection["replayed"] = False
        return projection
    except HTTPException:
        _rollback(session)
        raise
    except Exception as exc:  # noqa: BLE001
        _rollback(session)
        raise _fail(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "role_request_report_failed"
        ) from exc


# ── 既有入口 C1–C4 的请求来源守卫 ───────────────────────────────────────


def require_lease_holder(
    row: RoleProvisionRequestRow,
    *,
    lease_token: Optional[str],
    config: Optional[RoleProvisionHostConfig],
    now: datetime,
    allowed_statuses: tuple[str, ...],
) -> None:
    """共享的写资格复查（合同 §5）：任一条件不满足即拒绝，调用方零写入。"""
    if config is None or not config.enabled:
        raise _fail(_CONFLICT, ROLE_PROVISION_HOST_ERROR_DISABLED)
    if row.status not in allowed_statuses:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_STATUS_CONFLICT)
    if not lease_token or not row.lease_token_hash:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_SOURCE_REQUIRED)
    if not hmac.compare_digest(
        hash_role_provision_lease_token(lease_token), row.lease_token_hash
    ):
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_INVALID)
    if int(row.lease_generation or 0) <= 0:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_INVALID)
    if row.lease_config_version is None or int(row.lease_config_version) != int(
        config.config_version
    ):
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_INVALID)
    expires_at = _as_utc(row.lease_expires_at)
    if expires_at is None or now > expires_at:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_LEASE_INVALID)


def require_create_intent_for_creation(
    project_id: str,
    operation_key: str,
    *,
    fingerprinted_payload: dict,
    request_fingerprint: str,
    lease_token: Optional[str],
    session: Session,
) -> Optional[RoleProvisionRequestRow]:
    """C1 首次创建守卫（合同 §6）：命中 create 意图时逐项比对并复查有效租约。

    - 未命中任何 create 意图且调用方**未携带**租约时返回 ``None``，继续走原有旧人工
      创建路径（R1-1 行为不变）；
    - F6 补正（合同 §5.1/§6）：明确携带 ``lease_token`` 却没有任何请求来源（键错 / 过期 /
      伪造来源）时必须拒绝，不能退回无守卫人工旁路；参数“存在”按 ``is not None`` 判定，
      不依赖 truthiness。
    """
    row = session.get(RoleProvisionRequestRow, operation_key)
    if row is None:
        if lease_token is not None:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_SOURCE_REQUIRED)
        return None
    if row.project_id != project_id or row.kind != ROLE_REQUEST_KIND_CREATE:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_OPERATION_CONFLICT)
    if dict(row.payload or {}) != fingerprinted_payload or row.request_fingerprint != request_fingerprint:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_PAYLOAD_MISMATCH)
    config = load_host_config(project_id, session)
    require_lease_holder(
        row,
        lease_token=lease_token,
        config=config,
        now=_now(),
        allowed_statuses=(ROLE_REQUEST_STATUS_LEASED,),
    )
    # 当前选择必须与冻结快照逐维一致，且未下架。
    snapshot = dict(row.choice_snapshot or {})
    choice = session.get(RunnerModelChoice, fingerprinted_payload["choice_id"])
    if choice is None or choice.retired_at is not None:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_CHOICE_UNAVAILABLE)
    runner = session.get(RunnerRegistry, choice.runner_id)
    if runner is None or runner.adapter_status == RUNNER_ADAPTER_RETIRED:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_CHOICE_UNAVAILABLE)
    current = {
        "choice_id": choice.choice_id,
        "runner_id": choice.runner_id,
        "runtime": runner.runtime,
        "model_source": choice.model_source,
        "provider_id": choice.provider_id,
        "connection_ref": choice.connection_ref,
        "model_id": choice.model_id,
        "model_alias": choice.model_alias or "",
    }
    for field, value in current.items():
        if snapshot.get(field) != value:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_BINDING_MISMATCH)
    if model_choice_dimension_facts(choice) != (
        snapshot.get("runner_id"),
        snapshot.get("model_source"),
        snapshot.get("provider_id"),
        snapshot.get("connection_ref"),
        snapshot.get("model_id"),
        snapshot.get("model_alias") or "",
    ):
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_BINDING_MISMATCH)
    return row


def apply_create_intent_created(
    row: RoleProvisionRequestRow,
    *,
    member_id: str,
    session: Session,
) -> None:
    """C1 成功时在**同一事务**内回填真实成员与来源操作键（合同 §6）。"""
    now = _now()
    row.status = ROLE_REQUEST_STATUS_CREATED
    row.member_id = member_id
    row.origin_operation_key = row.request_key
    row.revision = int(row.revision or 1) + 1
    row.updated_at = now
    session.add(row)


def resolve_request_source(
    project_id: str,
    *,
    operation_key: str,
    member_id: Optional[str],
    request_key: Optional[str],
    lease_token: Optional[str],
    required_kind: Optional[str],
    session: Session,
) -> Optional[RoleProvisionRequestRow]:
    """C2/C3/C4 的来源选择（合同 §5.1）：精确取一行；省略即拒绝旁路。

    - 带 ``request_key``：按 key 取**那一行**，再核项目/成员/原创建操作键/租约；
    - 不带 ``request_key``：若该原 ``operation_key`` 有**任何**来源行（含终态）→
      ``provision_lease_required``；确实没有来源行才返回 ``None`` 保留旧人工路径。
      携带租约（含空串）同样按“存在”拒绝，不依赖 truthiness。
    """
    if lease_token is not None and not isinstance(lease_token, str):
        raise _fail(_UNPROCESSABLE, ROLE_REQUEST_ERROR_PAYLOAD_INVALID)
    if request_key is not None:
        key = _normalize_request_key(request_key)
        row = session.get(RoleProvisionRequestRow, key)
        if row is None or row.project_id != project_id:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_OPERATION_MISMATCH)
        if required_kind is not None and row.kind != required_kind:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_OPERATION_MISMATCH)
        if row.origin_operation_key != operation_key:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_OPERATION_MISMATCH)
        if member_id is not None and row.member_id is not None and row.member_id != member_id:
            raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_OPERATION_MISMATCH)
        config = load_host_config(project_id, session)
        require_lease_holder(
            row,
            lease_token=lease_token,
            config=config,
            now=_now(),
            allowed_statuses=(ROLE_REQUEST_STATUS_CREATED,),
        )
        return row

    if lease_token is not None:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_SOURCE_REQUIRED)
    sources = session.exec(
        select(RoleProvisionRequestRow)
        .where(RoleProvisionRequestRow.project_id == project_id)
        .where(RoleProvisionRequestRow.origin_operation_key == operation_key)
    ).all()
    if sources:
        raise _fail(_CONFLICT, ROLE_REQUEST_ERROR_SOURCE_REQUIRED)
    return None


def request_has_source_for_operation(
    project_id: str, operation_key: str, session: Session
) -> bool:
    """该原创建操作键是否存在**任何**请求来源行（含终态）。"""
    return (
        session.exec(
            select(RoleProvisionRequestRow)
            .where(RoleProvisionRequestRow.project_id == project_id)
            .where(RoleProvisionRequestRow.origin_operation_key == operation_key)
        ).first()
        is not None
    )


def request_has_source_for_member(
    project_id: str,
    member_id: str,
    session: Session,
    *,
    kind: Optional[str] = None,
) -> bool:
    """该成员是否已有**任何**请求来源行（含终态）——用于关闭旧无 body 轮换旁路。

    合同 §3/§5.1：只有“无请求来源且无活动意图”的旧 human 路径才保持；一旦该角色
    由请求链创建或恢复过（行永久保留），旧旁路不得因过期/完成而重新获得无守卫写权限。
    """
    statement = (
        select(RoleProvisionRequestRow)
        .where(RoleProvisionRequestRow.project_id == project_id)
        .where(RoleProvisionRequestRow.member_id == member_id)
    )
    if kind is not None:
        statement = statement.where(RoleProvisionRequestRow.kind == kind)
    return session.exec(statement).first() is not None


__all__ = [
    "apply_create_intent_created",
    "cancel_request",
    "claim_request",
    "create_request_intent",
    "disable_host_config",
    "enable_host_config",
    "expected_binding_fingerprint",
    "expected_completion_generation",
    "get_request",
    "host_config_projection",
    "is_claimable",
    "lease_valid",
    "list_requests",
    "load_host_config",
    "report_request",
    "request_has_source_for_member",
    "request_has_source_for_operation",
    "request_projection",
    "require_completion_facts",
    "require_create_intent_for_creation",
    "require_lease_holder",
    "resolve_request_source",
    "resume_request",
    "retry_exhausted",
    "write_begin",
]
