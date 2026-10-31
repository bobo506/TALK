"""351-B 思考强度解析与执行命令改写（纯函数）。

351-A 起公开绑定会下发用户覆盖值（``effort_override``）、生效值（``effective_effort``）、
可选项（``effort_options``）与来源（``effort_source``）。本模块只做两件事：

- ``resolve_binding_effort``：根据公开字段决定“本次执行该用哪一档”，旧服务缺字段时回退到
  启动时烘焙的 native 配置值；
- ``apply_effort``：把该档位写回已构建好的执行命令（``-c model_reasoning_effort=...``
  或旧入口的 ``--effort ...``），让**下一次执行**用新值，而不必重启角色服务。

两条纪律：只读公开字段、不猜档位；改写不认识的命令形态时原样返回，绝不臆测参数位置。
"""
from __future__ import annotations

import json
import shlex
from typing import Any

# 与 bridges/codex_execution_native.py 的 Codex 适配器校验集合一致。
ADAPTER_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")

EFFORT_SOURCE_USER = "user"
EFFORT_SOURCE_MODEL = "model"
EFFORT_SOURCE_CONFIG = "config"

_CONFIG_KEY = "model_reasoning_effort"


class EffortUnavailable(ValueError):
    """无法确定可执行的强度；``reason`` 是稳定的机器可读代码。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _normalize(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip().lower()
    return item if item in ADAPTER_EFFORTS else None


def resolve_binding_effort(binding: Any, fallback: Any) -> tuple[str, str]:
    """返回 ``(effort, source)``；无法安全确定时抛 :class:`EffortUnavailable`。

    - 旧服务/旧快照没有 ``effective_effort`` → 用 ``fallback``（native 配置值），``source='config'``；
    - 生效值必须在适配器集合内；``effort_options`` 非空时还必须在其中；
    - 设有用户覆盖但能力来源未知 → 拒绝（不把“无法校验”当成“可以执行”）。
    """
    if not isinstance(binding, dict):
        raise EffortUnavailable("codex_effort_capability_unknown")
    effective = binding.get("effective_effort")
    if effective is None or (isinstance(effective, str) and not effective.strip()):
        fallback_effort = _normalize(fallback)
        if fallback_effort is None:
            raise EffortUnavailable("codex_effort_unsupported")
        return fallback_effort, EFFORT_SOURCE_CONFIG
    effort = _normalize(effective)
    if effort is None:
        raise EffortUnavailable("codex_effort_unsupported")
    override = binding.get("effort_override")
    has_override = isinstance(override, str) and bool(override.strip())
    options = binding.get("effort_options")
    if isinstance(options, list) and options:
        allowed = {_normalize(value) for value in options} - {None}
        if effort not in allowed:
            raise EffortUnavailable("codex_effort_unsupported")
    elif has_override:
        raise EffortUnavailable("codex_effort_capability_unknown")
    if has_override and not isinstance(binding.get("effort_source"), str):
        raise EffortUnavailable("codex_effort_capability_unknown")
    return effort, (EFFORT_SOURCE_USER if has_override else EFFORT_SOURCE_MODEL)


def _split(command: Any) -> list[str] | None:
    """按 bridge 解析命令的同一规则（``shlex.split(posix=True)``）还原 token。"""
    if isinstance(command, str):
        try:
            return shlex.split(command, posix=True)
        except ValueError:
            return None
    if isinstance(command, (list, tuple)) and all(isinstance(item, str) for item in command):
        return list(command)
    return None


def apply_effort(command: Any, effort: str) -> tuple[Any, str]:
    """把 ``effort`` 写入命令；返回 ``(new_command, mode)``。

    ``mode``：``config``（``-c model_reasoning_effort=...``）、``flag``（``--effort ...``）
    或 ``unchanged``（不认识的命令形态，原样返回，不臆测）。

    字符串命令与 bridge 使用同一套 POSIX 解析/重组（``shlex``），保持与既有
    ``cli_bridge.parse_command`` 一致；列表命令按 token 边界替换。
    """
    if _normalize(effort) is None:
        raise EffortUnavailable("codex_effort_unsupported")
    tokens = _split(command)
    if tokens is None:
        return command, "unchanged"
    mode = "unchanged"
    for index in range(len(tokens) - 1):
        if tokens[index] in ("-c", "--config") and tokens[index + 1].split("=", 1)[0] == _CONFIG_KEY:
            key, sep, _value = tokens[index + 1].partition("=")
            tokens[index + 1] = key + sep + json.dumps(effort)
            mode = "config"
            break
        if tokens[index] in ("--effort", "--" + _CONFIG_KEY):
            tokens[index + 1] = effort
            mode = "flag"
            break
    if mode == "unchanged":
        return command, mode
    return (shlex.join(tokens) if isinstance(command, str) else tokens), mode
