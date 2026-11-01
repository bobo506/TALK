"""Codex native ``config.toml`` 的结构化校验（忽略排版，不忽略约束）。

2026-11-01：Codex 0.164 在首次执行后会把项目信任写回原生配置：

```toml
[projects.'d:\\claude-test\\talk']
trust_level = "trusted"
```

旧入口拿整份文本与预设字符串比较，把这条已授权的权限设置误判成配置漂移，
角色因此启动失败（``codex_native_config_changed``）。本模块只比较解析后的
字段，注释、空白与字段顺序都不影响结论，同时继续锁住：

- 角色身份：``model`` 必须等于绑定的模型；
- 隔离：``cli_auth_credentials_store="file"``，认证只落在角色自己的 HOME；
- 信任范围：``projects`` 只允许项目根本身，且只能出现 ``trust_level``；
- 沙箱/审批：只接受受限取值，拒绝 ``disabled``/``danger-full-access`` 等放宽项。

未知字段一律拒绝。确需放行新的 Codex 配置项时，先确认它属于哪一类约束，
再加入 :data:`KNOWN_TOP_LEVEL` 并补对应取值校验与测试，不做整键放行。
"""
from __future__ import annotations

import os
from pathlib import Path
import tomllib
from typing import Any, Mapping

# 与 bridges/codex_execution_native.py 的适配器接受集合一致。
EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})
SANDBOX_MODES = frozenset({"read-only", "workspace-write"})
APPROVAL_POLICIES = frozenset({"never", "on-request", "untrusted"})
WINDOWS_SANDBOX = frozenset({"elevated", "unelevated"})
TRUST_LEVELS = frozenset({"trusted", "untrusted"})

KNOWN_TOP_LEVEL = frozenset({
    "model",
    "model_reasoning_effort",
    "model_provider",
    "forced_login_method",
    "cli_auth_credentials_store",
    "approval_policy",
    "sandbox_mode",
    "projects",
    "windows",
})
# 这些键不是“允许任意值”：校验函数会逐项检查取值。
MAX_CONFIG_BYTES = 65536


class NativeConfigChanged(RuntimeError):
    """结构化校验失败；``fields`` 只含字段名，绝不携带配置值。"""

    def __init__(self, reason: str, fields: tuple[str, ...] = ()) -> None:
        self.reason = reason
        self.fields = fields
        detail = reason + (": " + ",".join(fields) if fields else "")
        super().__init__(detail)


def _same_path(value: Any, root: Path | None) -> bool:
    if root is None or not isinstance(value, str) or not value:
        return False
    if not os.path.isabs(value):
        return False
    try:
        left = os.path.normcase(os.path.realpath(os.path.normpath(value)))
        right = os.path.normcase(os.path.realpath(os.path.normpath(os.fspath(root))))
    except (OSError, ValueError):
        return False
    return left == right


def validate_config(value: Any, *, model: str | None = None, root: Path | None = None,
                    required: Mapping[str, Any] | None = None) -> None:
    """校验解析后的配置；失败抛 :class:`NativeConfigChanged`。

    ``model`` 为 ``None`` 时只校验结构（供角色准备阶段读取旧配置），
    ``required`` 用于调用方额外要求“字段必须存在且等于该值”。
    """
    if not isinstance(value, dict):
        raise NativeConfigChanged("not_a_table")

    unknown = tuple(sorted(set(value) - KNOWN_TOP_LEVEL))
    if unknown:
        raise NativeConfigChanged("unknown_fields", unknown)

    if model is not None and value.get("model") != model:
        raise NativeConfigChanged("model")
    if "model" in value and not isinstance(value["model"], str):
        raise NativeConfigChanged("model")

    for key, expected in (required or {}).items():
        if value.get(key) != expected:
            raise NativeConfigChanged("required_field", (key,))

    effort = value.get("model_reasoning_effort")
    if effort is not None and effort not in EFFORTS:
        raise NativeConfigChanged("unsupported_value", ("model_reasoning_effort",))

    if "model_provider" in value and value["model_provider"] != "openai":
        raise NativeConfigChanged("unsupported_value", ("model_provider",))
    if "forced_login_method" in value and value["forced_login_method"] != "chatgpt":
        raise NativeConfigChanged("unsupported_value", ("forced_login_method",))
    # 角色隔离：认证存储必须落在角色自己的 CODEX_HOME 文件里。
    if "cli_auth_credentials_store" in value and value["cli_auth_credentials_store"] != "file":
        raise NativeConfigChanged("unsupported_value", ("cli_auth_credentials_store",))

    if "approval_policy" in value and value["approval_policy"] not in APPROVAL_POLICIES:
        raise NativeConfigChanged("unsupported_value", ("approval_policy",))
    if "sandbox_mode" in value and value["sandbox_mode"] not in SANDBOX_MODES:
        raise NativeConfigChanged("unsupported_value", ("sandbox_mode",))

    windows = value.get("windows")
    if windows is not None:
        if not isinstance(windows, dict):
            raise NativeConfigChanged("invalid_table", ("windows",))
        unknown_windows = tuple(sorted(set(windows) - {"sandbox"}))
        if unknown_windows:
            raise NativeConfigChanged("unknown_fields", tuple("windows." + key for key in unknown_windows))
        if "sandbox" in windows and windows["sandbox"] not in WINDOWS_SANDBOX:
            raise NativeConfigChanged("unsupported_value", ("windows.sandbox",))

    projects = value.get("projects")
    if projects is not None:
        if not isinstance(projects, dict):
            raise NativeConfigChanged("invalid_table", ("projects",))
        for path, settings in projects.items():
            if not _same_path(path, root):
                # 只回字段名，不回显信任路径。
                raise NativeConfigChanged("projects_outside_root", ("projects.path",))
            if not isinstance(settings, dict):
                raise NativeConfigChanged("invalid_table", ("projects.trust_level",))
            unknown_project = tuple(sorted(set(settings) - {"trust_level"}))
            if unknown_project:
                raise NativeConfigChanged("unknown_fields",
                                          tuple("projects." + key for key in unknown_project))
            if settings.get("trust_level") not in TRUST_LEVELS:
                raise NativeConfigChanged("unsupported_value", ("projects.trust_level",))


def read_config(path: Path | str, *, model: str | None = None, root: Path | str | None = None,
                required: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """读取并校验 ``config.toml``；返回解析结果，错误统一为 :class:`NativeConfigChanged`。"""
    config_path = Path(path)
    try:
        if not config_path.is_file():
            raise NativeConfigChanged("missing")
        if config_path.stat().st_size > MAX_CONFIG_BYTES:
            raise NativeConfigChanged("too_large")
        with config_path.open("rb") as stream:
            value = tomllib.load(stream)
    except NativeConfigChanged:
        raise
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise NativeConfigChanged("invalid_toml") from None
    validate_config(value, model=model, root=Path(root) if root is not None else None,
                    required=required)
    return value
