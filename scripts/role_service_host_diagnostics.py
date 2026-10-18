#!/usr/bin/env python3
"""宿主侧持久诊断适配层（任务 272）。

本模块只做三件事：

1. 把宿主自己的显式日志策略（CLI > 环境变量 > 默认值）收敛成
   :class:`HostDiagnosticsPolicy`，并复用 ``bridges.runtime_diagnostics`` 的
   :class:`~bridges.runtime_diagnostics.DiagnosticsPolicy` 构造写入器；
2. 用一个**永不向业务抛异常**的 :class:`HostDiagnostics` 包装底层
   :class:`~bridges.runtime_diagnostics.RuntimeDiagnostics`，保证日志构造/写入/
   格式化/脱敏/降级失败都不会替换原异常、丢失原 Popen/owner 或阻断后续动作；
3. 给出内置 bridge 已支持的子进程日志参数（``--runtime-log-*`` /
   ``--disable-runtime-logs``），仅当宿主显式配置了非默认策略时才传递；显式
   ``--cli-executable`` 自定义入口保持旧 argv 语义，不追加任何日志参数。

底层日志 schema（``talk-runtime-diagnostics-1``）与公共写入 API 保持不变；宿主
只使用现有的 ``record_event`` / ``record_exception`` 接口。身份字段的原则：

- 具体启动动作使用真实 ``project_id / member_id / 预分配 instance_id /
  launch_id``；``pid`` 是**宿主**进程 PID，子进程 PID 只放在 ``extra.child_pid``；
- 宿主级（poll / 配置 worker / 服务循环）事件没有单一角色，``member_id`` 使用
  ``"unknown"``，不借用任何真实角色；项目已知时仍写 ``project_id``；
- 执行预算、HTTP 预算等只写实际已知值；MCP 读取等待预算保持 ``null`` +
  ``source=unknown``；不写 argv、完整环境、配置、认证正文、提示词或子进程输出。
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional

from bridges import runtime_diagnostics as runtime_diag

ENV_RUNTIME_LOG_DIR = "TALK_RUNTIME_LOG_DIR"
ENV_RUNTIME_LOG_RETENTION_DAYS = "TALK_RUNTIME_LOG_RETENTION_DAYS"
ENV_RUNTIME_LOG_MAX_BYTES = "TALK_RUNTIME_LOG_MAX_BYTES"
ENV_RUNTIME_LOG_MAX_FILE_BYTES = "TALK_RUNTIME_LOG_MAX_FILE_BYTES"
ENV_RUNTIME_LOG_DISABLED = "TALK_RUNTIME_LOG_DISABLED"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: writer 构造阶段自身失败时的降级提示去重（不递归写日志，不含异常正文）。
_DEGRADE_LOCK = threading.Lock()
_DEGRADED: set[str] = set()


def _normalized_disabled(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY
    return bool(value)


def _text_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number_text(value: Any) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _safe_degrade(kind: str, exc: BaseException | None = None) -> None:
    """有界 stderr 降级提示；stderr 也不可写时静默，不替换任何业务异常。"""
    suffix = f" ({type(exc).__name__})" if exc is not None else ""
    marker = f"{kind}{suffix}"
    with _DEGRADE_LOCK:
        if marker in _DEGRADED:
            return
        _DEGRADED.add(marker)
    try:
        print(f"[runtime-diagnostics] 本地诊断日志降级：{kind}{suffix}", file=sys.stderr)
    except Exception:
        # 控制台/管道关闭时不能递归写日志，也不能改变原业务结果。
        pass


def _secret_values(values: Iterable[Any]) -> tuple[Any, ...]:
    """把单个字符串当作一个秘密，而不是逐字符拆分。"""
    if isinstance(values, (str, bytes)):
        return (values,)
    return tuple(values)


@dataclass(frozen=True)
class HostDiagnosticsPolicy:
    """宿主显式日志策略（不读取完整环境之外的任何配置/凭据）。"""

    diagnostics_policy: runtime_diag.DiagnosticsPolicy = field(repr=False)
    disabled: bool = False
    explicit_root: bool = False
    explicit_retention_days: bool = False
    explicit_max_bytes: bool = False
    explicit_max_file_bytes: bool = False

    @property
    def root(self):
        return self.diagnostics_policy.root

    @property
    def retention_days(self) -> float:
        return self.diagnostics_policy.retention_days

    @property
    def max_bytes(self) -> int:
        return self.diagnostics_policy.max_bytes

    @property
    def max_file_bytes(self) -> int:
        return self.diagnostics_policy.max_file_bytes

    @classmethod
    def resolve(
        cls,
        *,
        root: Any = None,
        retention_days: Any = None,
        max_bytes: Any = None,
        max_file_bytes: Any = None,
        disabled: Any = False,
        env: Optional[dict[str, str]] = None,
    ) -> "HostDiagnosticsPolicy":
        """解析策略：显式参数 > 环境变量 > 基础 API 默认值。

        值本身交给底层 :meth:`DiagnosticsPolicy.create` 校验/归一；非法数值沿用
        基础 API 的“回退到默认值”语义，宿主不因日志配置拒绝服务。``disabled``
        接受 CLI 布尔或环境变量真值（``1/true/yes/on``，大小写不敏感）。
        """
        env_map = os.environ if env is None else env
        raw_root = root if _text_or_none(root) is not None else env_map.get(ENV_RUNTIME_LOG_DIR)
        raw_retention = (
            retention_days
            if retention_days is not None and _text_or_none(retention_days) is not None
            else env_map.get(ENV_RUNTIME_LOG_RETENTION_DAYS)
        )
        raw_max_bytes = (
            max_bytes
            if max_bytes is not None and _text_or_none(max_bytes) is not None
            else env_map.get(ENV_RUNTIME_LOG_MAX_BYTES)
        )
        raw_max_file = (
            max_file_bytes
            if max_file_bytes is not None and _text_or_none(max_file_bytes) is not None
            else env_map.get(ENV_RUNTIME_LOG_MAX_FILE_BYTES)
        )
        env_disabled = env_map.get(ENV_RUNTIME_LOG_DISABLED)
        resolved_disabled = _normalized_disabled(disabled) or _normalized_disabled(
            env_disabled
        )
        resolved = runtime_diag.DiagnosticsPolicy.create(
            root=raw_root,
            retention_days=raw_retention,
            max_bytes=raw_max_bytes,
            max_file_bytes=raw_max_file,
        )
        # 宿主与角色子进程的cwd可能不同。解析策略时冻结绝对根；
        # absolute不创建目录，也不为日志配置访问额外认证或完整环境。
        resolved = replace(resolved, root=resolved.root.absolute())
        return cls(
            diagnostics_policy=resolved,
            disabled=resolved_disabled,
            explicit_root=_text_or_none(raw_root) is not None,
            explicit_retention_days=_text_or_none(raw_retention) is not None,
            explicit_max_bytes=_text_or_none(raw_max_bytes) is not None,
            explicit_max_file_bytes=_text_or_none(raw_max_file) is not None,
        )

    def child_diagnostics_arguments(self) -> list[str]:
        """传给内置 bridge 的日志参数；默认策略下为空，保持旧 argv 语义。

        只使用真实内置 bridge 已支持的参数。若宿主被显式禁用，则子进程也显式
        禁用，避免“宿主关了但子进程仍写”的歧义；显式根/保留/容量只在调用方
        真的显式配置时传递，默认值不重复塞进 argv。
        """
        if self.disabled:
            return ["--disable-runtime-logs"]
        arguments: list[str] = []
        if self.explicit_root:
            arguments += ["--runtime-log-dir", str(self.root)]
        if self.explicit_retention_days:
            arguments += [
                "--runtime-log-retention-days",
                _number_text(self.retention_days),
            ]
        if self.explicit_max_bytes:
            arguments += ["--runtime-log-max-bytes", _number_text(self.max_bytes)]
        if self.explicit_max_file_bytes:
            arguments += [
                "--runtime-log-max-file-bytes",
                _number_text(self.max_file_bytes),
            ]
        return arguments


class HostDiagnostics:
    """底层 ``RuntimeDiagnostics`` 的安全包装；任何日志失败都不向业务抛出。"""

    __slots__ = ("_writer", "_secrets", "_lock")

    def __init__(
        self,
        writer: Optional[runtime_diag.RuntimeDiagnostics] = None,
        *,
        known_secrets: Iterable[Any] = (),
    ):
        self._writer = writer
        self._secrets = tuple(
            str(value) for value in _secret_values(known_secrets) if value
        )
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        writer = self._writer
        return bool(writer is not None and getattr(writer, "enabled", False))

    def add_sensitive_value(self, value: Any) -> None:
        self.add_sensitive_values((value,))

    def add_sensitive_values(self, values: Iterable[Any]) -> None:
        additions = [str(value) for value in _secret_values(values) if value]
        if not additions:
            return
        with self._lock:
            merged = list(self._secrets)
            for value in additions:
                if value not in merged:
                    merged.append(value)
            self._secrets = tuple(merged)

    def _sensitive(self, values: Iterable[Any]) -> tuple[str, ...]:
        with self._lock:
            base = self._secrets
        return (*base, *[str(value) for value in _secret_values(values) if value])

    def record_event(
        self,
        event: str,
        *,
        sensitive_values: Iterable[Any] = (),
        **kwargs: Any,
    ) -> Optional[str]:
        writer = self._writer
        if writer is None or not getattr(writer, "enabled", False):
            return None
        try:
            return writer.record_event(
                event,
                sensitive_values=self._sensitive(sensitive_values),
                **kwargs,
            )
        except Exception as exc:
            # 日志记录失败只丢失本条记录；原业务异常/句柄/owner 不受影响。
            _safe_degrade("host_event_write_failed", exc)
            return None

    def record_exception(
        self,
        exc: BaseException,
        *,
        sensitive_values: Iterable[Any] = (),
        **kwargs: Any,
    ) -> Optional[str]:
        writer = self._writer
        if writer is None or not getattr(writer, "enabled", False):
            return None
        try:
            return writer.record_exception(
                exc,
                sensitive_values=self._sensitive(sensitive_values),
                **kwargs,
            )
        except Exception as write_exc:
            _safe_degrade("host_exception_write_failed", write_exc)
            return None

    def close(self) -> None:
        writer = self._writer
        if writer is None:
            return
        try:
            writer.close()
        except Exception:
            pass


def create_writer(
    *,
    policy: HostDiagnosticsPolicy,
    member_id: str,
    instance_id: Optional[str] = None,
    project_id: Optional[str] = None,
    launch_id: Optional[str] = None,
    runtime: Optional[str] = None,
    pid: Optional[int] = None,
    known_secrets: Iterable[Any] = (),
) -> HostDiagnostics:
    """构造宿主写入器；禁用或构造失败时返回一个安全空包装，绝不抛给业务。"""
    if policy.disabled:
        return HostDiagnostics(None, known_secrets=known_secrets)
    secrets = tuple(str(value) for value in _secret_values(known_secrets) if value)
    try:
        writer = runtime_diag.RuntimeDiagnostics(
            member_id=member_id,
            instance_id=instance_id,
            policy=policy.diagnostics_policy,
            project_id=project_id,
            launch_id=launch_id,
            runtime=runtime,
            pid=os.getpid() if pid is None else int(pid),
            known_secrets=secrets,
        )
    except Exception as exc:
        _safe_degrade("host_writer_unavailable", exc)
        writer = None
    return HostDiagnostics(writer, known_secrets=secrets)


__all__ = [
    "ENV_RUNTIME_LOG_DIR",
    "ENV_RUNTIME_LOG_RETENTION_DAYS",
    "ENV_RUNTIME_LOG_MAX_BYTES",
    "ENV_RUNTIME_LOG_MAX_FILE_BYTES",
    "ENV_RUNTIME_LOG_DISABLED",
    "HostDiagnosticsPolicy",
    "HostDiagnostics",
    "create_writer",
]
