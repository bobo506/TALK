"""Antigravity CLI (``agy``) 模型目录与思考强度解析（纯函数）。

基于本机 ``agy 1.5.16`` 实测的 ``agy models`` 输出：
- Gemini 4 Neon (``gemini-4-neon``)：支持 ``low / medium / high / xhigh``
- Gemini 4 Carbon (``gemini-4-carbon``)：支持 ``low / medium / high``（无 ``xhigh``）
- Gemini 4 Hydrogen (``gemini-4-hydrogen``)：支持 ``low / medium / high / xhigh``

``agy`` CLI 中每个模型+强度对应精确的模型 ID（如 ``gemini-4-neon-xhigh``、
``gemini-4-carbon-high``）。本模块负责：
1. 解析 ``agy models`` 输出，聚合出上述 3 个基础模型及各自真实支持的思考强度；
2. 按公开绑定事实决定下一次执行的目标强度（用户覆盖 > 模型默认 > 兜底配置），
   严格校验模型专属档位集合（绝不给 Carbon 放行 ``xhigh``）；
3. 将目标强度与精确模型 ID 写回已构建的 ``agy`` 执行命令，无需重启角色服务。
"""
from __future__ import annotations

import shlex
from typing import Any

from bridges import cli_bridge

EFFORT_ORDER = ("low", "medium", "high", "xhigh")
ADAPTER_EFFORTS = frozenset(EFFORT_ORDER)

EFFORT_SOURCE_USER = "user"
EFFORT_SOURCE_MODEL = "model"
EFFORT_SOURCE_CONFIG = "config"

# 本切片显式适配的 3 个 Antigravity 基础模型及其已验证强度能力。
SUPPORTED_BASE_MODELS: dict[str, dict[str, Any]] = {
    "gemini-4-neon": {
        "display_name": "Gemini 4 Neon",
        "supported_efforts": ("low", "medium", "high", "xhigh"),
        "default_effort": "high",
    },
    "gemini-4-carbon": {
        "display_name": "Gemini 4 Carbon",
        "supported_efforts": ("low", "medium", "high"),
        "default_effort": "high",
    },
    "gemini-4-hydrogen": {
        "display_name": "Gemini 4 Hydrogen",
        "supported_efforts": ("low", "medium", "high", "xhigh"),
        "default_effort": "high",
    },
}

# 按顺序稳定输出 3 个目标模型。
SUPPORTED_MODEL_ORDER: tuple[str, ...] = (
    "gemini-4-neon",
    "gemini-4-carbon",
    "gemini-4-hydrogen",
)


class AntigravityEffortUnavailable(ValueError):
    """无法安全确定可执行的 Antigravity 思考强度；``reason`` 为稳定机器可读码。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _normalize_effort(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip().lower()
    return item if item in ADAPTER_EFFORTS else None


def _match_base_prefix(raw: Any) -> tuple[str, str | None] | None:
    """识别基础模型前缀，即使后缀强度非法也返回 ``(base, suffix)`` 供精确报错区分。"""
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower()
    if not token:
        return None
    if token in SUPPORTED_BASE_MODELS:
        return token, None
    for base in SUPPORTED_BASE_MODELS:
        prefix = base + "-"
        if token.startswith(prefix):
            return base, token[len(prefix):]
    return None


def parse_model_id(raw: Any) -> tuple[str, str | None] | None:
    """将基础模型 ID 或带强度后缀的 CLI 模型 ID 解析为 ``(base_model, effort_or_none)``。

    只识别 3 个受支持目标模型；对非法组合（如 ``gemini-4-carbon-xhigh``）返回 ``None``。
    """
    matched = _match_base_prefix(raw)
    if matched is None:
        return None
    base, suffix = matched
    if suffix is None:
        return base, None
    if suffix in SUPPORTED_BASE_MODELS[base]["supported_efforts"]:
        return base, suffix
    return None


def supported_efforts_for_model(model_id: Any) -> tuple[str, ...]:
    """返回目标模型专属的支持强度元组；未知模型返回空元组。"""
    parsed = parse_model_id(model_id)
    if parsed is None:
        return ()
    return tuple(SUPPORTED_BASE_MODELS[parsed[0]]["supported_efforts"])


def default_effort_for_model(model_id: Any) -> str | None:
    """返回目标模型的默认强度；未知模型返回 ``None``。"""
    parsed = parse_model_id(model_id)
    if parsed is None:
        return None
    return str(SUPPORTED_BASE_MODELS[parsed[0]]["default_effort"])


def cli_model_id(model_id: str, effort: str | None = None) -> str:
    """将基础模型（或带后缀模型）与思考强度合成精确的 ``agy --model`` 参数。"""
    matched = _match_base_prefix(model_id)
    if matched is None:
        raise AntigravityEffortUnavailable("antigravity_model_unsupported")
    base, raw_suffix = matched
    allowed = SUPPORTED_BASE_MODELS[base]["supported_efforts"]
    if raw_suffix is not None and raw_suffix not in allowed:
        raise AntigravityEffortUnavailable("antigravity_effort_unsupported")
    chosen = _normalize_effort(effort) if effort is not None else (
        raw_suffix or SUPPORTED_BASE_MODELS[base]["default_effort"]
    )
    if chosen is None or chosen not in allowed:
        raise AntigravityEffortUnavailable("antigravity_effort_unsupported")
    return f"{base}-{chosen}"


def parse_agy_models_output(output: str) -> list[dict[str, Any]]:
    """解析 ``agy models`` 输出，只聚合本机真实列出的 3 个目标模型及其实测强度集合。

    忽略非制表符行（例如 ``Fetching available models...`` 进度提示）；绝不编造
    输出中未出现的强度档位。
    """
    observed: dict[str, dict[str, str]] = {}
    for line in (output or "").splitlines():
        if "\t" not in line:
            continue
        raw_id = line.split("\t", 1)[0].strip()
        parsed = parse_model_id(raw_id)
        if parsed is None:
            continue
        base, effort = parsed
        if effort is None:
            continue
        observed.setdefault(base, {})[effort] = raw_id

    catalog: list[dict[str, Any]] = []
    for base in SUPPORTED_MODEL_ORDER:
        entries = observed.get(base)
        if not entries:
            continue
        meta = SUPPORTED_BASE_MODELS[base]
        efforts = [e for e in EFFORT_ORDER if e in entries and e in meta["supported_efforts"]]
        if not efforts:
            continue
        preferred = meta["default_effort"]
        default_effort = preferred if preferred in efforts else efforts[0]
        catalog.append(
            {
                "model_id": base,
                "display_name": meta["display_name"],
                "supported_efforts": efforts,
                "default_effort": default_effort,
                "cli_model_ids": {e: entries[e] for e in efforts},
            }
        )
    return catalog


def resolve_binding_effort(
    binding: Any,
    fallback: Any = None,
    *,
    model_id: Any = None,
) -> tuple[str, str]:
    """按公开绑定决定本次应执行的 ``(effort, source)``；无法安全校验时抛异常。

    - 校验顺序：基础模型专属集合 → 公开 ``effort_options``（如非空）→ 覆盖来源完整性；
    - 设有用户覆盖但能力清单或来源缺失 → ``antigravity_effort_capability_unknown``；
    - 档位不在该模型允许集合（例如给 Carbon 设 ``xhigh``）→ ``antigravity_effort_unsupported``。
    """
    if not isinstance(binding, dict):
        raise AntigravityEffortUnavailable("antigravity_effort_capability_unknown")
    resolved_model = model_id or binding.get("model_id") or binding.get("model_alias")
    parsed_model = parse_model_id(resolved_model) if resolved_model is not None else None
    model_allowed = (
        frozenset(SUPPORTED_BASE_MODELS[parsed_model[0]]["supported_efforts"])
        if parsed_model is not None
        else ADAPTER_EFFORTS
    )
    if resolved_model is not None and parsed_model is None:
        matched = _match_base_prefix(resolved_model)
        raise AntigravityEffortUnavailable(
            "antigravity_effort_unsupported" if matched is not None else "antigravity_model_unsupported"
        )

    effective = binding.get("effective_effort")
    if effective is None or (isinstance(effective, str) and not effective.strip()):
        fallback_effort = _normalize_effort(fallback)
        if fallback_effort is None or fallback_effort not in model_allowed:
            raise AntigravityEffortUnavailable("antigravity_effort_unsupported")
        return fallback_effort, EFFORT_SOURCE_CONFIG

    effort = _normalize_effort(effective)
    if effort is None or effort not in model_allowed:
        raise AntigravityEffortUnavailable("antigravity_effort_unsupported")

    override = binding.get("effort_override")
    has_override = isinstance(override, str) and bool(override.strip())
    options = binding.get("effort_options")
    if isinstance(options, list) and options:
        allowed = {_normalize_effort(value) for value in options} - {None}
        allowed &= model_allowed
        if effort not in allowed:
            raise AntigravityEffortUnavailable("antigravity_effort_unsupported")
    elif has_override:
        raise AntigravityEffortUnavailable("antigravity_effort_capability_unknown")
    if has_override and not isinstance(binding.get("effort_source"), str):
        raise AntigravityEffortUnavailable("antigravity_effort_capability_unknown")
    return effort, (EFFORT_SOURCE_USER if has_override else EFFORT_SOURCE_MODEL)


def _split_command(command: Any) -> list[str] | None:
    if isinstance(command, str):
        try:
            return cli_bridge.parse_command(command)
        except ValueError:
            return None
    if isinstance(command, (list, tuple)) and all(isinstance(item, str) for item in command):
        return list(command)
    return None


def extract_command_models(command: Any) -> list[str]:
    """提取命令中所有 ``--model <val>`` 与 ``--model=<val>`` 原始模型值。"""
    tokens = _split_command(command)
    if tokens is None:
        return []
    found: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--model" and index + 1 < len(tokens):
            found.append(tokens[index + 1])
            index += 2
            continue
        if token.startswith("--model="):
            found.append(token.split("=", 1)[1])
        index += 1
    return found


def apply_effort(
    command: Any,
    effort: str,
    *,
    base_model: str | None = None,
) -> tuple[Any, str]:
    """将 ``effort`` 写回 ``agy`` 命令中所有 ``--model`` 与 ``--effort`` 参数。

    同时支持 ``--flag val`` 与 Go 风格 ``--flag=val`` 语法；遇到不支持的 ``--model``
    或 ``base_model`` 与命令现有模型家族冲突时 fail-closed 抛异常，绝不静默切换模型家族
    或留下冲突的重复参数。
    """
    normalized = _normalize_effort(effort)
    if normalized is None:
        raise AntigravityEffortUnavailable("antigravity_effort_unsupported")

    tokens = _split_command(command)
    if tokens is None:
        return command, "unchanged"

    resolved_base: str | None = None
    if base_model is not None:
        parsed_override = parse_model_id(base_model)
        if parsed_override is None:
            matched = _match_base_prefix(base_model)
            raise AntigravityEffortUnavailable(
                "antigravity_effort_unsupported" if matched is not None else "antigravity_model_unsupported"
            )
        resolved_base = parsed_override[0]

    # 先完整收集并校验命令里全部 --model 与 --effort 位置（支持 --flag=val 与重复参数）。
    model_slots: list[tuple[int, bool, str]] = []
    effort_slots: list[tuple[int, bool]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--model":
            if index + 1 >= len(tokens):
                raise AntigravityEffortUnavailable("antigravity_model_unsupported")
            model_slots.append((index + 1, False, tokens[index + 1]))
            index += 2
            continue
        if token.startswith("--model="):
            model_slots.append((index, True, token.split("=", 1)[1]))
            index += 1
            continue
        if token == "--effort":
            if index + 1 >= len(tokens):
                raise AntigravityEffortUnavailable("antigravity_effort_unsupported")
            effort_slots.append((index + 1, False))
            index += 2
            continue
        if token.startswith("--effort="):
            effort_slots.append((index, True))
            index += 1
            continue
        index += 1

    # 校验命令里所有 --model 都属于受支持目标模型且彼此及与 base_model 一致。
    command_base: str | None = None
    for _pos, _eq, raw_val in model_slots:
        parsed_token = parse_model_id(raw_val)
        if parsed_token is None:
            matched = _match_base_prefix(raw_val)
            raise AntigravityEffortUnavailable(
                "antigravity_effort_unsupported" if matched is not None else "antigravity_model_unsupported"
            )
        token_base = parsed_token[0]
        if command_base is not None and command_base != token_base:
            raise AntigravityEffortUnavailable("antigravity_model_mismatch")
        command_base = token_base

    if resolved_base is not None and command_base is not None and resolved_base != command_base:
        raise AntigravityEffortUnavailable("antigravity_model_mismatch")
    final_base = command_base or resolved_base

    if final_base is not None and normalized not in SUPPORTED_BASE_MODELS[final_base]["supported_efforts"]:
        raise AntigravityEffortUnavailable("antigravity_effort_unsupported")

    if not model_slots and not effort_slots:
        return command, "unchanged"

    for pos, is_eq, _raw in model_slots:
        assert final_base is not None
        new_model = cli_model_id(final_base, normalized)
        tokens[pos] = f"--model={new_model}" if is_eq else new_model

    for pos, is_eq in effort_slots:
        tokens[pos] = f"--effort={normalized}" if is_eq else normalized

    mode = (
        "model_and_flag"
        if (model_slots and effort_slots)
        else ("model" if model_slots else "flag")
    )
    return (shlex.join(tokens) if isinstance(command, str) else tokens), mode
