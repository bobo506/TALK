"""新角色页面内官方授权与角色独立模型准备（保留原模块导入路径）。

公开层只保存状态、选择 ID、官方授权 URL 和设备码；原生输出和认证凭据不进入公开层。
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import threading
import time
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlmodel import Session, select

from server import db
from server.models import (
    DEFAULT_EFFORT_VALUES,
    ProjectRole,
    RoleCreationOperation,
    RoleNativeSetup,
    RoleNativeSetupOut,
    RoleProvisionJob,
    RoleServiceState,
)

ACTIVE = {"starting", "awaiting_authorization", "finalizing"}
CANCELABLE = {"starting", "awaiting_authorization"}
_URL = re.compile(r"https://[^\s<>\"']+", re.IGNORECASE)
_ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
_DEVICE_CODE = re.compile(r'(?<![A-Z0-9])([A-Z0-9]{4}-[A-Z0-9]{4,5})(?![A-Z0-9])')
SUPPORTED_RUNTIMES = {'kimi-code', 'codex'}


def _adapter(runtime):
    if runtime == 'codex':
        from scripts import codex_role_setup
        return codex_role_setup
    from scripts import kimi_role_setup
    return kimi_role_setup


def _attempt_adapter(attempt):
    return _adapter(getattr(attempt, 'setup_runtime', 'kimi-code'))


def _now():
    return datetime.now(timezone.utc)


def _operation(project_id: str, member_id: str, session: Session):
    return session.exec(select(RoleCreationOperation).where(
        RoleCreationOperation.project_id == project_id,
        RoleCreationOperation.member_id == member_id,
    )).first()


def ensure_native_setup_required(project_id: str, member_id: str, session: Session) -> bool:
    """新建角色配置完成时登记已接入的准备流程；既有角色不追溯登记。

    返回本次是否**新建**了准备行，调用方据此只在首次 report 后触发一次后台准备。
    """
    from server.models import ProjectRoleBinding, RunnerRegistry
    if session.get(RoleNativeSetup, (project_id, member_id)) is not None:
        return False
    binding = session.get(ProjectRoleBinding, (project_id, member_id))
    runner = session.get(RunnerRegistry, binding.runner_id) if binding and binding.runner_id else None
    operation = _operation(project_id, member_id, session)
    role = session.get(ProjectRole, (project_id, member_id))
    if runner is None or runner.runtime not in SUPPORTED_RUNTIMES or operation is None or role is None:
        return False
    session.add(RoleNativeSetup(project_id=project_id, member_id=member_id,
        choice_id=operation.choice_id, created_by=role.created_by))
    return True


def _current_choice_id(project_id: str, member_id: str, session: Session):
    operation = _operation(project_id, member_id, session)
    return operation.choice_id if operation is not None else None


def _selection_current(project_id: str, member_id: str, choice_id: str, session: Session) -> bool:
    from server.models import ProjectRoleBinding, RunnerModelChoice
    if choice_id != _current_choice_id(project_id, member_id, session):
        return False
    binding = session.get(ProjectRoleBinding, (project_id, member_id))
    choice = session.get(RunnerModelChoice, choice_id)
    if binding is None or choice is None:
        return False
    return all(getattr(binding, field) == getattr(choice, field) for field in
        ("runner_id", "model_source", "provider_id", "connection_ref", "model_id", "model_alias"))


def native_login_fact(project_id: str, member_id: str, session: Session) -> tuple[bool, bool]:
    """返回（是否有新流程记录，授权与当前所选模型是否已准备）。"""
    row = session.get(RoleNativeSetup, (project_id, member_id))
    if row is None:
        return False, False
    return True, row.status == "ready" and _selection_current(project_id, member_id, row.choice_id, session)


def require_native_setup_for_start(project_id: str, member_id: str, session: Session) -> None:
    present, ready = native_login_fact(project_id, member_id, session)
    if present and not ready:
        raise HTTPException(409, "native_authorization_required")


def _out(row: RoleNativeSetup, session: Session) -> RoleNativeSetupOut:
    current = _selection_current(row.project_id, row.member_id, row.choice_id, session)
    ready = row.status == "ready" and current
    return RoleNativeSetupOut(project_id=row.project_id, member_id=row.member_id,
        choice_id=row.choice_id, status=row.status if current else "failed", revision=row.revision,
        authorization_url=row.authorization_url if row.status in ACTIVE else None,
        authorization_code=row.authorization_code if row.status in ACTIVE else None,
        error_code=row.error_code if current else "native_model_selection_changed",
        requires_user_action=row.status == "awaiting_authorization" or (row.status == "failed" and current),
        can_start=not ready and row.status not in ACTIVE,
        can_cancel=row.status in CANCELABLE, updated_at=row.updated_at, completed_at=row.completed_at)


def _placeholder(project_id: str, member_id: str, session: Session) -> RoleNativeSetupOut:
    role = session.get(ProjectRole, (project_id, member_id))
    if role is None or role.archived_at is not None:
        raise HTTPException(404, "role_not_found")
    choice = _current_choice_id(project_id, member_id, session) or ""
    now = _now()
    return RoleNativeSetupOut(project_id=project_id, member_id=member_id, choice_id=choice,
        status="not_required", revision=0, requires_user_action=False, can_start=False,
        updated_at=now)


def _error_code(exc: BaseException) -> str:
    text = str(exc)
    if text in {'native_cli_missing', 'native_cli_version_unsupported', 'native_role_busy',
                'native_model_configuration_required', 'native_model_selection_changed',
                'native_model_catalog_unavailable', 'native_selected_model_unavailable',
                'native_authorization_failed', 'native_setup_not_supported'}:
        return text
    if text in {"native_previous_process_unverified", "native_previous_process_identity_changed",
                "native_previous_process_stop_unconfirmed", "native_process_identity_unverified",
                "native_process_scope_unavailable"}:
        return text
    if "找不到 Kimi Code CLI" in text:
        return "native_cli_missing"
    if "先关闭" in text:
        return "native_role_busy"
    if "模型" in text or "providers" in text or "登录未生成" in text:
        return "native_model_configuration_required"
    return "native_setup_failed"


class NativeSetupManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._attempts = {}

    def _active(self, key) -> bool:
        with self._lock:
            return key in self._attempts

    def _update(self, project_id, member_id, *, status=None, url=None, code=None, error=None, token=None):
        key = (project_id, member_id)
        with self._lock:
            if token is not None and not self._current(key, token):
                return
            with Session(db.engine) as session:
                row = session.get(RoleNativeSetup, (project_id, member_id))
                if row is None or (token is not None and row.attempt_id != token):
                    return
                if status is not None:
                    row.status = status
                if url is not None:
                    row.authorization_url = url
                if code is not None:
                    row.authorization_code = code
                if status is not None and status not in ACTIVE:
                    row.authorization_url = row.authorization_code = None
                row.error_code = error
                row.updated_at = _now()
                row.completed_at = _now() if status == "ready" else None
                row.revision += 1
                session.add(row)
                session.commit()
                if status == "ready":
                    _enqueue_auto_start(project_id, member_id)
                return True

    def get(self, project_id: str, member_id: str, session: Session) -> RoleNativeSetupOut:
        with self._lock:
            session.expire_all()
            return self._get_locked(project_id, member_id, session)

    def _get_locked(self, project_id: str, member_id: str, session: Session) -> RoleNativeSetupOut:
        row = session.get(RoleNativeSetup, (project_id, member_id))
        if row is None:
            return _placeholder(project_id, member_id, session)
        if row.status in ACTIVE and not self._active((project_id, member_id)):
            row.status = "failed"
            row.error_code = "native_setup_interrupted"
            row.authorization_url = None
            row.authorization_code = None
            row.revision += 1
            row.updated_at = _now()
            session.add(row)
            session.commit()
        return _out(row, session)

    def start(self, project_id: str, member_id: str, expected_revision: int,
              actor_id: str, session: Session, *, root=None) -> RoleNativeSetupOut:
        from server.role_services import _write_begin
        with self._lock:
            _write_begin(session)
            try:
                return self._start_locked(project_id, member_id, expected_revision, actor_id, session, root=root)
            except Exception:
                session.rollback()
                raise

    def _start_locked(self, project_id: str, member_id: str, expected_revision: int,
                      actor_id: str, session: Session, *, root=None) -> RoleNativeSetupOut:
        from server.models import ProjectRoleBinding, RunnerRegistry
        role = session.get(ProjectRole, (project_id, member_id))
        binding = session.get(ProjectRoleBinding, (project_id, member_id))
        runner = session.get(RunnerRegistry, binding.runner_id) if binding and binding.runner_id else None
        operation = _operation(project_id, member_id, session)
        if role is None or role.archived_at is not None or runner is None or runner.runtime not in SUPPORTED_RUNTIMES \
                or runner.control_kind != "managed_cli" or operation is None:
            raise HTTPException(409, "native_setup_not_supported")
        job = session.get(RoleProvisionJob, operation.operation_key)
        if job is None or job.status != "succeeded" or job.credential_version != role.credential_version:
            raise HTTPException(409, "role_provision_incomplete")
        service = session.get(RoleServiceState, (project_id, member_id))
        if service is not None and (service.owner_host or service.process_launch_id
                or service.desired_state not in (None, "stopped")
                or service.observed_state not in (None, "not_started", "stopped", "failed")):
            raise HTTPException(409, "native_role_busy")
        row = session.get(RoleNativeSetup, (project_id, member_id))
        revision = row.revision if row is not None else 0
        if revision != expected_revision:
            raise HTTPException(409, "native_setup_revision_conflict")
        if not _selection_current(project_id, member_id, operation.choice_id, session):
            raise HTTPException(409, "native_model_selection_changed")
        if row is not None and row.status in ACTIVE and self._active((project_id, member_id)):
            raise HTTPException(409, "native_setup_active")
        if row is not None and row.status == "ready" and row.choice_id == operation.choice_id:
            return _out(row, session)
        if row is None:
            row = RoleNativeSetup(project_id=project_id, member_id=member_id,
                choice_id=operation.choice_id, created_by=actor_id)
        token = uuid.uuid4().hex
        row.attempt_id = token
        row.status = "starting"
        row.choice_id = operation.choice_id
        row.authorization_url = None
        row.authorization_code = None
        row.error_code = None
        row.completed_at = None
        row.revision = revision + 1
        row.updated_at = _now()
        session.add(row)
        session.commit()
        try:
            kwargs = {"root": root} if root is not None else {}
            attempt = _adapter(runner.runtime).begin_native_login(project_id, member_id, **kwargs)
            attempt.setup_runtime = runner.runtime
        except Exception as exc:  # 公开只落稳定分类，绝不落原生异常正文。
            row = session.get(RoleNativeSetup, (project_id, member_id))
            row.status = "failed"
            row.error_code = _error_code(exc)
            row.revision += 1
            row.updated_at = _now()
            session.add(row)
            session.commit()
            return _out(row, session)
        with self._lock:
            self._attempts[(project_id, member_id)] = (token, attempt)
        thread = threading.Thread(target=self._monitor, args=(project_id, member_id, token, attempt),
            name=f"role-native-setup-{uuid.uuid4().hex[:8]}", daemon=True)
        thread.start()
        return _out(row, session)

    def _monitor(self, project_id, member_id, token, attempt):
        key = (project_id, member_id)
        seen = 0
        try:
            for line in attempt.process.stdout:
                seen += len(line)
                if seen > 65536:
                    continue  # 继续排空管道，但不把无界原生输出带入状态。
                line = _ANSI.sub('', line)
                is_codex = getattr(attempt, 'setup_runtime', None) == 'codex'
                code = _DEVICE_CODE.search(line) if is_codex else None
                if code:
                    self._update(project_id, member_id, code=code.group(1), token=token)
                match = _URL.search(line)
                if match and self._current(key, token):
                    url = _safe_url(match.group(0).rstrip(".,);]"))
                    if url and (not is_codex or (urlsplit(url).hostname == 'auth.openai.com'
                            and urlsplit(url).path == '/codex/device' and not urlsplit(url).query)):
                        self._update(project_id, member_id, status="awaiting_authorization", url=url, token=token)
            returncode = attempt.process.wait()
            if not self._current(key, token):
                return
            if not self._update(project_id, member_id, status="finalizing", token=token):
                return
            if returncode != 0:
                self._update(project_id, member_id, status="failed", error="native_authorization_failed", token=token)
                return
            _attempt_adapter(attempt).finish_native_login(attempt)
            if self._current(key, token):
                # 2026-10-28：把官方目录返回的默认强度落库，供角色列表展示；取不到保持 NULL。
                _record_default_effort(project_id, member_id, getattr(attempt, "default_effort", None))
                self._update(project_id, member_id, status="ready", token=token)
        except Exception as exc:
            if self._current(key, token):
                self._update(project_id, member_id, status="failed", error=_error_code(exc), token=token)
        finally:
            with self._lock:
                if key in self._attempts and self._attempts[key][0] == token:
                    self._attempts.pop(key, None)
            try:
                _attempt_adapter(attempt).release_native_login(attempt)
                attempt.process.stdout.close()
            except Exception:
                pass

    def _current(self, key, token):
        with self._lock:
            return key in self._attempts and self._attempts[key][0] == token

    def cancel(self, project_id: str, member_id: str, expected_revision: int,
               session: Session) -> RoleNativeSetupOut:
        from server.role_services import _write_begin
        with self._lock:
            _write_begin(session)
            try:
                return self._cancel_locked(project_id, member_id, expected_revision, session)
            except Exception:
                session.rollback()
                raise

    def _cancel_locked(self, project_id: str, member_id: str, expected_revision: int,
                       session: Session) -> RoleNativeSetupOut:
        row = session.get(RoleNativeSetup, (project_id, member_id))
        if row is None or row.revision != expected_revision:
            raise HTTPException(409, "native_setup_revision_conflict")
        if row.status not in CANCELABLE:
            raise HTTPException(409, "native_setup_not_active")
        key = (project_id, member_id)
        with self._lock:
            current = self._attempts.get(key)
        if current is None:
            row.status = "failed"
            row.error_code = "native_setup_interrupted"
        else:
            try:
                _attempt_adapter(current[1]).cancel_native_login(current[1])
            except Exception as exc:
                session.rollback()
                raise HTTPException(409, _error_code(exc)) from None
            self._attempts.pop(key, None)
            row.status = "failed"
            row.error_code = "native_authorization_canceled"
        row.authorization_url = None
        row.authorization_code = None
        row.revision += 1
        row.updated_at = _now()
        session.add(row)
        session.commit()
        return _out(row, session)


manager = NativeSetupManager()


def _role_runtime(project_id: str, member_id: str, session: Session):
    from server.models import ProjectRoleBinding, RunnerRegistry
    binding = session.get(ProjectRoleBinding, (project_id, member_id))
    runner = session.get(RunnerRegistry, binding.runner_id) if binding and binding.runner_id else None
    return runner.runtime if runner is not None else None


_DEFAULT_EFFORT_VALUES = DEFAULT_EFFORT_VALUES


def _record_default_effort(project_id: str, member_id: str, effort) -> None:
    """把准备阶段从官方模型目录取回的默认思考强度写回绑定行（只用于展示）。

    - 只接受已知强度字面量；取不到或不认识时保持 NULL，列表不显示强度，不猜、不回退展示名；
    - 不参与六维指纹、绑定有效性与启停判定；绑定行不存在（已删除）时静默跳过。
    """
    from server.models import ProjectRoleBinding

    value = effort.strip().lower() if isinstance(effort, str) else ""
    if value not in _DEFAULT_EFFORT_VALUES:
        value = None
    with Session(db.engine) as session:
        binding = session.get(ProjectRoleBinding, (project_id, member_id))
        if binding is None or binding.default_effort == value:
            return
        binding.default_effort = value
        session.add(binding)
        session.commit()


def _mark_auto_setup_failed(project_id: str, member_id: str, code: str) -> None:
    """只把仍处于 required 的自动准备标记失败；不覆盖用户已重试出的活动状态。"""
    with manager._lock:
        with Session(db.engine) as session:
            row = session.get(RoleNativeSetup, (project_id, member_id))
            if row is None or row.status != "required":
                return
            row.status = "failed"
            row.error_code = code
            row.authorization_url = row.authorization_code = None
            row.revision += 1
            row.updated_at = _now()
            session.add(row)
            session.commit()


def schedule_auto_native_setup(project_id: str, member_id: str) -> None:
    """配置完成后自动开始 Codex 设备授权：页面无需先点“开始官方授权”。

    仅 Codex 新角色自动推进；Kimi 既有合同保持人工触发。线程只负责调用共享
    manager.start，所有状态机、锁、进程守卫和错误分类仍只有一份实现。
    """
    thread = threading.Thread(target=_auto_native_setup,
        args=(project_id, member_id), name=f"role-auto-native-setup-{uuid.uuid4().hex[:8]}",
        daemon=True)
    thread.start()


def _auto_native_setup(project_id: str, member_id: str) -> None:
    for attempt in range(20):
        with Session(db.engine) as session:
            row = session.get(RoleNativeSetup, (project_id, member_id))
            if row is None or row.status != "required":
                return
            if _role_runtime(project_id, member_id, session) != "codex":
                return
            revision, actor = row.revision, row.created_by
        try:
            with Session(db.engine) as session:
                manager.start(project_id, member_id, revision, actor, session)
            return
        except HTTPException as exc:
            code = str(exc.detail)
            if code in {"native_setup_active", "native_setup_revision_conflict"}:
                return
            if code == "native_role_busy" and attempt < 9:
                time.sleep(0.1)
                continue
            _mark_auto_setup_failed(project_id, member_id, code)
            return
        except Exception:
            _mark_auto_setup_failed(project_id, member_id, "native_setup_failed")
            return
    _mark_auto_setup_failed(project_id, member_id, "native_setup_interrupted")


def _enqueue_auto_start(project_id: str, member_id: str) -> None:
    """准备刚变为 ready 后，沿创建请求原 auto_start 意图投递一次启动。

    失败不回写准备状态：角色保持 ready，页面显示可手动启动/重试。
    """
    try:
        from server.role_provision_requests import enqueue_pending_auto_start
        enqueue_pending_auto_start(project_id, member_id)
    except Exception:
        pass


def _safe_url(value: str):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        # 原生输出只用于打开官方授权页；去除片段，避免把本地误输出当凭据回显。
        return parsed._replace(fragment="").geturl()
    except ValueError:
        return None
