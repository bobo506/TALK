"""执行会话选择、上下文 70% 阈值、缺指标 10 次备用与首轮/续轮投递计划离线内核。

本模块只使用调用方显式传入的数据：不访问环境变量、文件、数据库或网络，不
spawn 进程，不在导入时产生副作用，也不创建/恢复真实原生会话。统一入口
:func:`plan_execution_session` 返回一个可 JSON 序列化的计划，**不发送消息**、
不写 TALK 任务状态、不产生原生 session 成功事实，也不预增计数。

动作：
- ``reuse_session``：续用指定候选，投递增量正文。
- ``new_session``：生成新窗计划，投递完整基础合同 + 本次增量。
- ``wait``：候选忙、存在活动 writer 或无法证明执行通道独占，暂不投递。
- ``reject``：输入不合法，未生成投递计划。

阈值只使用原始整数精确比较：``used * 10 >= capacity * 7``（即 ``>= 70%``）。
可靠指标优先：``<70%`` 续窗、``>=70%`` 下一次新窗，即使已交办超过 10 次也
不因轮数换窗。仅当可靠指标明确不可得、分类在有限白名单内且该精确窗口有
可信完整计数时，才允许从新窗首轮起累计的最多 10 次交办；第 10 次可投递，
第 11 次新窗。计数在这里只是纯状态，不等于真实送达；``window_count`` 的
``proposed_ordinal`` 必须等宿主真实确认送达后再通过
:func:`confirm_window_delivery` 归并。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn

__all__ = [
    "COUNT_STATE_SCHEMA",
    "FALLBACK_LIMIT",
    "MAX_SAFE_INTEGER",
    "THRESHOLD_DENOMINATOR",
    "THRESHOLD_NUMERATOR",
    "UNAVAILABILITY_SCHEMA",
    "confirm_window_delivery",
    "initialize_window_count",
    "plan_execution_session",
    "reconstruct_full_requirements",
    "record_threshold_observation",
]

SCHEMA_PLAN = "execution-session-plan-1"
SCHEMA_ARCHIVE = "execution-session-archive-1"
COUNT_STATE_SCHEMA = "execution-session-window-count-1"
COUNT_STATE_VERSION = 1
UNAVAILABILITY_SCHEMA = "talk-dsh-context-unavailability-1"
UNAVAILABILITY_VERSION = 1
# 备用规则：已确认 9 次时允许第 10 次；确认第 10 次后下一次新窗。这不是
# 有效指标下的硬上限。
FALLBACK_LIMIT = 10

# JSON / JavaScript 安全整数上界（2**53 - 1）。token 数、容量和代次均不得超出。
MAX_SAFE_INTEGER = 9_007_199_254_740_991

# 70% = 7/10；用 used * 10 >= capacity * 7 做原始整数比较。
THRESHOLD_NUMERATOR = 7
THRESHOLD_DENOMINATOR = 10

_SELECTIONS = frozenset(("auto", "new", "reuse"))
_CANDIDATE_STATES = frozenset(("ready", "busy", "tainted", "closed"))
_SCOPE_ID_FIELDS = (
    "project_id",
    "target_member_id",
    "requester_id",
    "continuity_key",
    "workspace_identity",
    "runtime",
    "runner_id",
    "native_home_namespace",
    "provider_id",
    "model_id",
    "model_binding_fingerprint",
    "config_permission_fingerprint",
    "service_launch_id",
    "base_contract_version",
)
_SCOPE_FIELDS = _SCOPE_ID_FIELDS + (
    "workspace_verified",
    "session_generation",
    "base_contract_sha256",
)
_BASE_FIELDS = ("version", "sha256", "text")
_TASK_REQUIRED_FIELDS = (
    "task_id",
    "attempt",
    "execution_id",
    "goal",
    "authorization",
    "body",
)
_TASK_OPTIONAL_FIELDS = (
    "baseline_change",
    "authorization_change",
    "acceptance_difference",
)
_TASK_FIELDS = _TASK_REQUIRED_FIELDS + _TASK_OPTIONAL_FIELDS

# 文本允许换行/回车/制表；其它 C0 控制字符与 DEL 拒绝。
_TEXT_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# 标识符不允许任何 C0 控制字符（包括换行、制表）与 DEL。
_IDENTIFIER_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9#][A-Za-z0-9#._-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

# DSH 投影字段的 camelCase 兼容别名。两种写法同时出现视为歧义，保持未知。
_SAMPLE_ALIASES = {
    "projected_tokens": "projectedTokens",
    "pressure_tokens": "pressureTokens",
    "context_window": "contextWindow",
}
_AMBIGUOUS = object()

_REASON_TEXT = {
    "reject_base_text_required": "新窗完整计划需要按合同引用提供基础正文，未生成投递计划。",
    "wait_channel_busy": "当前执行通道忙，暂不投递。",
    "wait_channel_state_unknown": "无法确认当前执行通道状态，暂不投递。",
    "new_no_candidate": "未提供可续用候选，生成新窗完整首轮计划。",
    "new_explicit": "派发者显式选择新窗，生成新窗完整首轮计划。",
    "new_context_threshold": (
        "上下文原始占用已达到 70% 阈值，下一次投递转新窗并恢复完整基础介绍。"
    ),
    "new_context_unknown": (
        "候选上下文指标不可用，不能把未知占比当作可续用，生成新窗完整首轮计划。"
    ),
    "new_fallback_classification_unverified": (
        "指标不可得分类缺失、不可核验或与原始样本/作用域不一致，"
        "不启用备用计数，生成新窗完整首轮计划。"
    ),
    "new_fallback_count_unverified": (
        "缺少该精确窗口首次轮起算的完整可信计数，不启用备用，"
        "生成新窗完整首轮计划。"
    ),
    "new_fallback_threshold_observed": (
        "该窗口最后一次可靠占比已达到 70% 阈值，缺数时仍必须换窗，"
        "不能再用不足 10 次拖延。"
    ),
    "new_fallback_exhausted": (
        "该窗口已确认交办达到 10 次，下一次交办必须新窗并恢复完整介绍。"
    ),
    "reuse_missing_metrics_fallback": (
        "可靠占比不可得，但窗口/配置身份及首轮起算的完整计数可信，"
        "已确认交办数不足 10，允许下一次交办；真实送达确认后才归并计数。"
    ),
    "new_scope_mismatch": "候选与当前作用域不匹配，不能续用，生成新窗完整首轮计划。",
    "new_scope_unverifiable": (
        "候选作用域无法核验，不能按匹配处理，生成新窗完整首轮计划。"
    ),
    "new_candidate_unverifiable": (
        "候选缺少可核验的会话身份，不能续用，生成新窗完整首轮计划。"
    ),
    "new_base_contract_changed": (
        "候选基础合同版本/哈希已变化，不能省略基础信息，生成新窗完整首轮计划。"
    ),
    "new_service_launch_changed": (
        "候选服务 launch 已变化，不能续用，生成新窗完整首轮计划。"
    ),
    "new_session_generation_changed": (
        "候选会话 generation 已变化，不能续用，生成新窗完整首轮计划。"
    ),
    "new_continuity_changed": (
        "候选工作线 continuity key 不同，不能跨工作线续用，生成新窗完整首轮计划。"
    ),
    "new_session_tainted": "候选会话已 taint，不能续用，生成新窗完整首轮计划。",
    "new_session_closed": "候选会话已关闭，不能续用，生成新窗完整首轮计划。",
    "new_first_turn_unconfirmed": (
        "候选首轮基础合同未确认送达，不能按已知上下文省略基础信息，"
        "生成新窗完整首轮计划。"
    ),
    "reuse_session": "候选作用域匹配且上下文低于 70%，生成增量续窗计划。",
    "wait_candidate_busy": (
        "候选执行会话忙，暂不投递；不在同一 home 另起新窗绕过。"
    ),
    "wait_candidate_state_unknown": "无法确认候选执行状态，暂不投递。",
    "wait_active_writer": "候选存在活动 writer，暂不投递。",
    "wait_writer_unknown": "无法确认候选无活动 writer，暂不投递。",
    "wait_channel_not_exclusive": "无法证明该角色执行通道可独占，暂不投递。",
    "wait_exclusive_unknown": "未提供执行通道独占确认，暂不投递。",
    "reject_invalid_input": "输入未通过校验，未生成投递计划。",
    "reject_reuse_without_candidate": "请求续用但未提供候选，未生成投递计划。",
    "reject_scope_base_mismatch": (
        "当前作用域的基础合同版本/哈希与基础合同正文不一致，未生成投递计划。"
    ),
}


class _InputError(Exception):
    """显式输入校验错误；消息只含字段名和通用原因，不回显输入内容。"""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


def _fail(field: str, message: str) -> NoReturn:
    raise _InputError(field, message)


def _is_int(value: Any) -> bool:
    """排除 bool（bool 是 int 子类），只接受真正的整数。"""

    return isinstance(value, int) and not isinstance(value, bool)


def _is_safe_int(value: Any, *, minimum: int = 0) -> bool:
    return _is_int(value) and minimum <= value <= MAX_SAFE_INTEGER


def _require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str):
        _fail(field, "必须是非空字符串")
    if value != value.strip():
        _fail(field, "不能有首尾空白")
    if not value:
        _fail(field, "不能为空")
    if len(value) > 512:
        _fail(field, "超出长度上限 512")
    if _IDENTIFIER_CONTROL_RE.search(value):
        _fail(field, "包含控制字符")
    _require_utf8(value, field)
    return value


def _is_identifier_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if not value or value != value.strip() or len(value) > 512:
        return False
    try:
        _require_utf8(value, "identifier")
    except _InputError:
        return False
    return _IDENTIFIER_CONTROL_RE.search(value) is None


def _require_utf8(value: str, field: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(field, "必须是合法 UTF-8 文本")


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        _fail(field, "必须是字符串")
    if not value.strip():
        _fail(field, "不能为空白")
    if _TEXT_CONTROL_RE.search(value):
        _fail(field, "包含不允许的控制字符")
    _require_utf8(value, field)
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(field, "必须是 64 位十六进制 SHA-256")
    return value.lower()


def _require_strict_mapping(
    value: Any,
    field: str,
    required: Sequence[str],
    allowed: Sequence[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(field, "必须是对象")
    for key in value:
        if not isinstance(key, str):
            _fail(field, "字段名必须是字符串")
    if any(key not in allowed for key in value):
        _fail(field, "包含不支持的字段")
    for key in required:
        if key not in value:
            _fail(f"{field}.{key}", "缺少必填字段")
    return value


def _normalize_selection(value: Any) -> str:
    if value is None:
        return "auto"
    if not isinstance(value, str) or value not in _SELECTIONS:
        _fail("selection", "必须是 auto/new/reuse 之一")
    return value


def _normalize_scope(value: Any, field: str = "scope") -> dict[str, Any]:
    raw = _require_strict_mapping(value, field, _SCOPE_FIELDS, _SCOPE_FIELDS)
    normalized: dict[str, Any] = {}
    for key in _SCOPE_ID_FIELDS:
        normalized[key] = _require_identifier(raw[key], f"{field}.{key}")
    if raw["workspace_verified"] is not True:
        _fail(
            f"{field}.workspace_verified",
            "调用方必须显式确认已核验真实工作区身份（true）",
        )
    normalized["workspace_verified"] = True
    if not _is_safe_int(raw["session_generation"], minimum=1):
        _fail(f"{field}.session_generation", "必须是 1..2^53-1 的整数")
    normalized["session_generation"] = raw["session_generation"]
    normalized["base_contract_sha256"] = _require_sha256(
        raw["base_contract_sha256"], f"{field}.base_contract_sha256"
    )
    return normalized


def _normalize_base_contract(value: Any, *, require_text: bool = False) -> dict[str, Any]:
    raw = _require_strict_mapping(
        value, "base_contract", ("version", "sha256"), _BASE_FIELDS
    )
    version = _require_identifier(raw["version"], "base_contract.version")
    declared = _require_sha256(raw["sha256"], "base_contract.sha256")
    if "text" not in raw:
        if require_text:
            _fail("base_contract.text", "重建或新窗完整计划需要基础正文")
        return {"version": version, "sha256": declared}
    text = _require_text(raw["text"], "base_contract.text")
    actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if actual != declared:
        _fail("base_contract.sha256", "与基础合同正文的 SHA-256 不一致")
    return {"version": version, "sha256": declared, "text": text}


def _normalize_task_id(value: Any) -> str:
    if _is_int(value):
        if not _is_safe_int(value, minimum=1):
            _fail("task.task_id", "整数任务号必须是 1..2^53-1")
        return str(value)
    if isinstance(value, str):
        if not _TASK_ID_RE.fullmatch(value):
            _fail(
                "task.task_id",
                "只允许字母/数字/#/./_/-，长度 1-64，且不能含空格",
            )
        return value
    _fail("task.task_id", "必须是任务号字符串或安全正整数")


def _normalize_authorization(value: Any, field: str) -> list[str]:
    if isinstance(value, str):
        return [_require_text(value, field)]
    if isinstance(value, (list, tuple)):
        if not value:
            _fail(field, "不能为空数组")
        return [
            _require_text(item, f"{field}[{index}]")
            for index, item in enumerate(value)
        ]
    _fail(field, "必须是字符串或非空字符串数组")


def _normalize_task(value: Any) -> dict[str, Any]:
    raw = _require_strict_mapping(
        value, "task", _TASK_REQUIRED_FIELDS, _TASK_FIELDS
    )
    task_id = _normalize_task_id(raw["task_id"])
    if not _is_safe_int(raw["attempt"], minimum=0):
        _fail("task.attempt", "必须是 0..2^53-1 的整数")
    execution_id = _require_identifier(raw["execution_id"], "task.execution_id")
    goal = _require_text(raw["goal"], "task.goal")
    authorization = _normalize_authorization(raw["authorization"], "task.authorization")
    body = _require_text(raw["body"], "task.body")
    normalized: dict[str, Any] = {
        "task_id": task_id,
        "attempt": raw["attempt"],
        "execution_id": execution_id,
        "goal": goal,
        "authorization": authorization,
        "body": body,
    }
    for key in _TASK_OPTIONAL_FIELDS:
        if key not in raw or raw[key] is None:
            continue
        if key == "authorization_change":
            normalized[key] = _normalize_authorization(
                raw[key], f"task.{key}"
            )
        else:
            normalized[key] = _require_text(raw[key], f"task.{key}")
    return normalized


def _normalize_new_messages(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value, Sequence
    ):
        _fail("new_messages", "必须是字符串数组或 null")
    return [
        _require_text(item, f"new_messages[{index}]")
        for index, item in enumerate(value)
    ]


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise _InputError("<canonical>", "输入包含不可规范序列化的值") from exc


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _safe_audit_label(value: Any) -> str | None:
    if (
        isinstance(value, str)
        and value
        and len(value) <= 80
        and _IDENTIFIER_CONTROL_RE.search(value) is None
    ):
        return value
    return None


def _normalize_revision(value: Any, field: str) -> str | int:
    if isinstance(value, str):
        return _require_identifier(value, field)
    if _is_int(value):
        if not _is_safe_int(value, minimum=0):
            _fail(field, "安全整数 revision 必须在 0..2^53-1")
        return value
    _fail(field, "必须是字符串或安全整数")


def _try_normalize_revision(value: Any, field: str) -> tuple[bool, str | int | None]:
    try:
        return True, _normalize_revision(value, field)
    except _InputError:
        return False, None


def _analyze_candidate(value: Any) -> dict[str, Any] | None:
    """尽量解析候选；未知/缺失字段不默认成匹配或独占。"""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        _fail("candidate", "必须是对象或 null")

    info: dict[str, Any] = {
        "native_session_id": None,
        "native_session_id_valid": False,
        "scope": None,
        "scope_error": None,
        "scope_fingerprint": None,
        "scope_match": False,
        "scope_differences": None,
        "state": None,
        "state_valid": False,
        "execution_channel_exclusive": None,
        "active_writer": None,
        "first_turn_confirmed": None,
        "session_revision": None,
        "session_revision_valid": False,
    }

    raw_id = value.get("native_session_id")
    if _is_identifier_value(raw_id):
        info["native_session_id"] = raw_id
        info["native_session_id_valid"] = True

    raw_scope = value.get("scope")
    if isinstance(raw_scope, Mapping):
        try:
            info["scope"] = _normalize_scope(raw_scope, "candidate.scope")
        except _InputError as exc:
            info["scope_error"] = f"{exc.field}: {exc.message}"
        else:
            info["scope_fingerprint"] = _fingerprint(info["scope"])
    else:
        info["scope_error"] = "candidate.scope: 缺少或不是对象"

    raw_state = value.get("state")
    if isinstance(raw_state, str) and raw_state in _CANDIDATE_STATES:
        info["state"] = raw_state
        info["state_valid"] = True

    for key in (
        "execution_channel_exclusive",
        "active_writer",
        "first_turn_confirmed",
    ):
        raw_bool = value.get(key)
        if isinstance(raw_bool, bool):
            info[key] = raw_bool

    revision_ok, revision = _try_normalize_revision(
        value.get("session_revision"), "candidate.session_revision"
    )
    if revision_ok:
        info["session_revision"] = revision
        info["session_revision_valid"] = True

    return info


def _compare_candidate_scope(
    info: dict[str, Any], current_scope: Mapping[str, Any]
) -> None:
    if info["scope"] is None:
        info["scope_match"] = False
        info["scope_differences"] = None
        return
    current_fingerprint = _fingerprint(current_scope)
    info["scope_match"] = info["scope_fingerprint"] == current_fingerprint
    if info["scope_match"]:
        info["scope_differences"] = []
    else:
        info["scope_differences"] = [
            key
            for key in _SCOPE_FIELDS
            if info["scope"][key] != current_scope[key]
        ]


def _scope_mismatch_reason(info: Mapping[str, Any]) -> str:
    if info["scope"] is None:
        return "new_scope_unverifiable"
    differences = info["scope_differences"] or []
    if not differences:
        return "new_scope_mismatch"
    if all(key in {"base_contract_version", "base_contract_sha256"} for key in differences):
        return "new_base_contract_changed"
    if all(key == "service_launch_id" for key in differences):
        return "new_service_launch_changed"
    if all(key == "session_generation" for key in differences):
        return "new_session_generation_changed"
    if all(key == "continuity_key" for key in differences):
        return "new_continuity_changed"
    return "new_scope_mismatch"


def _channel_code(info: Mapping[str, Any]) -> str | None:
    """返回等待原因；None 表示可继续做续用/新窗判断。"""

    if info["state"] == "busy":
        return "wait_candidate_busy"
    if not info["state_valid"]:
        return "wait_candidate_state_unknown"
    if info["active_writer"] is True:
        return "wait_active_writer"
    if info["active_writer"] is not False:
        return "wait_writer_unknown"
    if info["execution_channel_exclusive"] is not True:
        if info["execution_channel_exclusive"] is False:
            return "wait_channel_not_exclusive"
        return "wait_exclusive_unknown"
    return None


def _current_channel(value: Any) -> dict[str, Any]:
    """当前目标通道事实独立于旧候选；未知不能因无候选而绕过。"""
    raw = value if isinstance(value, Mapping) else {}
    state = raw.get("state")
    valid_state = isinstance(state, str) and state in ("ready", "busy")
    writer = raw.get("active_writer")
    exclusive = raw.get("execution_channel_exclusive")
    return {
        "state": state if valid_state else None,
        "state_valid": valid_state,
        "active_writer": writer if isinstance(writer, bool) else None,
        "execution_channel_exclusive": exclusive if isinstance(exclusive, bool) else None,
    }


# ---------------------------------------------------------------------------
# 指标不可得分类：只接受与精确窗口/作用域绑定的有限原因
# ---------------------------------------------------------------------------

_UNAVAILABILITY_SCOPE_FIELDS = (
    "project_id",
    "target_member_id",
    "requester_id",
    "continuity_key",
    "workspace_identity",
    "runner_id",
    "native_home_namespace",
    "service_launch_id",
    "provider_id",
    "model_id",
    "model_binding_fingerprint",
    "config_permission_fingerprint",
)
_FALLBACK_REASON_CATEGORIES = {
    "tokens_missing": "no_usage_sample",
    "capacity_missing": "capacity_missing",
    "used_sample_expired": "source_expired",
    "capacity_sample_expired": "source_expired",
    "pressure_sample_expired": "source_expired",
    "metrics_not_provided": "metrics_not_provided",
    "no_usage_sample": "no_usage_sample",
    "runtime_unsupported": "runtime_unsupported",
}
_FALLBACK_METRIC_COMPATIBILITY = {
    "context_missing": frozenset(_FALLBACK_REASON_CATEGORIES),
    "tokens_missing": frozenset(("tokens_missing", "no_usage_sample")),
    "capacity_missing": frozenset(("capacity_missing",)),
    "sample_expired": frozenset(
        (
            "used_sample_expired",
            "capacity_sample_expired",
            "pressure_sample_expired",
        )
    ),
}
_UNAVAILABILITY_FIELDS = (
    "schema",
    "version",
    "reason_code",
    "category",
    "fallback_eligible",
    "window",
    "evidence",
)
_UNAVAILABILITY_WINDOW_FIELDS = (
    "native_session_id",
    "session_generation",
    "session_revision",
    "scope",
    "scope_fingerprint",
)
_UNAVAILABILITY_EVIDENCE_FIELDS = (
    "trust",
    "trusted_host_source",
    "observed_at",
    "producer_supported",
    "identity_verified",
    "sample_present",
    "checks",
)
_ADAPTER_IDENTITY_CHECKS = (
    "scope_match",
    "workspace_verified",
    "session_id_match",
    "generation_match",
    "revision_match",
    "session_live",
    "projection_exact",
    "model_match",
    "binding_match",
    "config_source_known",
)


def _binding_fingerprint(
    scope: Mapping[str, Any],
    native_session_id: str,
    session_generation: int,
    session_revision: str | int,
) -> str:
    payload = {
        "scope": {field: scope[field] for field in _UNAVAILABILITY_SCOPE_FIELDS},
        "native_session_id": native_session_id,
        "session_generation": session_generation,
        "session_revision": session_revision,
    }
    return _fingerprint(payload)


def _normalize_unavailability(value: Any) -> dict[str, Any]:
    """校验 DSH 适配器/可信宿主给出的不可得分类与绑定证据。"""

    raw = _require_strict_mapping(
        value, "unavailability", _UNAVAILABILITY_FIELDS, _UNAVAILABILITY_FIELDS
    )
    if raw["schema"] != UNAVAILABILITY_SCHEMA:
        _fail("unavailability.schema", "不是当前不可得分类 schema")
    if not _is_int(raw["version"]) or raw["version"] != UNAVAILABILITY_VERSION:
        _fail("unavailability.version", "不是当前不可得分类版本")
    reason = _require_identifier(
        raw["reason_code"], "unavailability.reason_code"
    )
    if reason not in _FALLBACK_REASON_CATEGORIES:
        _fail(
            "unavailability.reason_code",
            "不在可兜底的有限不可得原因白名单",
        )
    expected_category = _FALLBACK_REASON_CATEGORIES[reason]
    if raw["category"] != expected_category:
        _fail("unavailability.category", "与原因码的分类不一致")
    if raw["fallback_eligible"] is not True:
        _fail("unavailability.fallback_eligible", "不可兜底分类不能进入备用判断")

    window = _require_strict_mapping(
        raw["window"],
        "unavailability.window",
        _UNAVAILABILITY_WINDOW_FIELDS,
        _UNAVAILABILITY_WINDOW_FIELDS,
    )
    native_session_id = _require_identifier(
        window["native_session_id"], "unavailability.window.native_session_id"
    )
    if not _is_safe_int(window["session_generation"], minimum=1):
        _fail(
            "unavailability.window.session_generation",
            "必须是 1..2^53-1 的整数",
        )
    session_generation = window["session_generation"]
    session_revision = _normalize_revision(
        window["session_revision"], "unavailability.window.session_revision"
    )
    raw_scope = _require_strict_mapping(
        window["scope"],
        "unavailability.window.scope",
        _UNAVAILABILITY_SCOPE_FIELDS,
        _UNAVAILABILITY_SCOPE_FIELDS,
    )
    scope = {
        field: _require_identifier(
            raw_scope[field], f"unavailability.window.scope.{field}"
        )
        for field in _UNAVAILABILITY_SCOPE_FIELDS
    }
    declared_fingerprint = _require_sha256(
        window["scope_fingerprint"], "unavailability.window.scope_fingerprint"
    )
    actual_fingerprint = _binding_fingerprint(
        scope, native_session_id, session_generation, session_revision
    )
    if declared_fingerprint != actual_fingerprint:
        _fail(
            "unavailability.window.scope_fingerprint",
            "与窗口/作用域绑定内容不一致",
        )

    evidence = _require_strict_mapping(
        raw["evidence"],
        "unavailability.evidence",
        _UNAVAILABILITY_EVIDENCE_FIELDS,
        _UNAVAILABILITY_EVIDENCE_FIELDS,
    )
    trust = evidence["trust"]
    if trust not in ("adapter_verified_snapshot", "trusted_host_capability"):
        _fail("unavailability.evidence.trust", "不是支持的可信来源类型")
    trusted_host_source = _require_identifier(
        evidence["trusted_host_source"],
        "unavailability.evidence.trusted_host_source",
    )
    try:
        observed_at = _parse_time(
            evidence["observed_at"], "unavailability.evidence.observed_at"
        )
    except _InputError as exc:
        _fail("unavailability.evidence.observed_at", exc.message)
    producer_supported = evidence["producer_supported"]
    if not isinstance(producer_supported, bool):
        _fail("unavailability.evidence.producer_supported", "必须是布尔值")
    if evidence["identity_verified"] is not True:
        _fail(
            "unavailability.evidence.identity_verified",
            "身份/配置未核验的不可得证据不能进入备用判断",
        )
    if evidence["sample_present"] is not False:
        _fail(
            "unavailability.evidence.sample_present",
            "不可得分类必须来自无可靠样本的路径",
        )
    checks = evidence["checks"]
    if not isinstance(checks, Mapping) or any(
        not isinstance(key, str) or not isinstance(item, bool)
        for key, item in checks.items()
    ):
        _fail("unavailability.evidence.checks", "必须是字符串到布尔的映射")
    if trust == "adapter_verified_snapshot":
        if producer_supported is not True:
            _fail(
                "unavailability.evidence.producer_supported",
                "适配器来源必须证明 producer 受支持",
            )
        if not all(checks.get(key) is True for key in _ADAPTER_IDENTITY_CHECKS):
            _fail(
                "unavailability.evidence.checks",
                "适配器来源缺少完整身份/配置核验",
            )
    else:
        if reason not in (
            "metrics_not_provided", "no_usage_sample", "runtime_unsupported"
        ):
            _fail("unavailability.reason_code", "宿主能力声明不能冒充适配器样本原因")
        if (
            checks.get("trusted_host_verified") is not True
            or checks.get("trusted_scope_confirmed") is not True
        ):
            _fail(
                "unavailability.evidence.checks",
                "可信宿主来源缺少精确 scope/window 确认",
            )

    return {
        "schema": UNAVAILABILITY_SCHEMA,
        "version": UNAVAILABILITY_VERSION,
        "reason_code": reason,
        "category": expected_category,
        "window": {
            "native_session_id": native_session_id,
            "session_generation": session_generation,
            "session_revision": session_revision,
            "scope": scope,
            "scope_fingerprint": actual_fingerprint,
        },
        "evidence": {
            "trust": trust,
            "trusted_host_source": trusted_host_source,
            "observed_at": observed_at.isoformat(),
            "producer_supported": producer_supported,
            "identity_verified": True,
            "sample_present": False,
            "checks": dict(checks),
        },
    }


def _unavailability_binding_error(
    classification: Mapping[str, Any],
    scope: Mapping[str, Any],
    candidate_info: Mapping[str, Any],
) -> str | None:
    window = classification["window"]
    if not candidate_info["native_session_id_valid"]:
        return "candidate_session_missing"
    if window["native_session_id"] != candidate_info["native_session_id"]:
        return "unavailability_session_mismatch"
    if window["session_generation"] != scope["session_generation"]:
        return "unavailability_generation_mismatch"
    for field in _UNAVAILABILITY_SCOPE_FIELDS:
        if window["scope"][field] != scope[field]:
            return f"unavailability_scope_mismatch:{field}"
    if not candidate_info["session_revision_valid"]:
        return "candidate_revision_missing"
    if _canonical_json(window["session_revision"]) != _canonical_json(
        candidate_info["session_revision"]
    ):
        return "unavailability_revision_mismatch"
    return None


def _raw_fallback_blocker(sample: Any) -> str | None:
    """备用前遍历显式数值，不能由更早发现的 missing/expired 掩盖错误。"""
    if not isinstance(sample, Mapping):
        return None  # 原指标校验会拒绝非映射；None 仍须分类与时钟。
    for field, label in (("context_window", "capacity"),
                         ("projected_tokens", "projected"),
                         ("pressure_tokens", "pressure")):
        present, value = _sample_field(sample, field)
        if present and (value is _AMBIGUOUS or _valid_token_count(value) is None
                        or (field == "context_window" and value <= 0)):
            return f"raw_{label}_invalid"
    return None


def _evaluate_context_unavailability(
    value: Any,
    scope: Mapping[str, Any],
    candidate_info: Mapping[str, Any],
    metrics: Mapping[str, Any],
    clock: Any,
) -> dict[str, Any]:
    """把分类与当前指标失败原因组合；调用方的 allow 布尔值不参与判定。"""

    if value is None:
        return {
            "status": "absent",
            "reason_code": "classification_absent",
            "classification": None,
        }
    try:
        classification = _normalize_unavailability(value)
    except _InputError as exc:
        raw_reason = value.get("reason_code") if isinstance(value, Mapping) else None
        raw_category = (
            value.get("category") if isinstance(value, Mapping) else None
        )
        return {
            "status": "invalid",
            "reason_code": "classification_invalid",
            "classification": None,
            "classification_reason": _safe_audit_label(raw_reason),
            "classification_category": _safe_audit_label(raw_category),
            "errors": [f"{exc.field}: {exc.message}"],
        }
    binding_error = _unavailability_binding_error(
        classification, scope, candidate_info
    )
    if binding_error is not None:
        return {
            "status": "invalid",
            "reason_code": binding_error,
            "classification": None,
            "errors": [binding_error],
        }
    try:
        clock = _require_strict_mapping(
            clock, "fallback_clock",
            ("now", "max_age_seconds"), ("now", "max_age_seconds"),
        )
        now = _parse_time(clock["now"], "fallback_clock.now")
        if not _is_safe_int(clock["max_age_seconds"]):
            _fail("fallback_clock.max_age_seconds", "必须是非负安全整数")
        observed_at = _parse_time(
            classification["evidence"]["observed_at"],
            "unavailability.evidence.observed_at",
        )
        age = now - observed_at
        if age < timedelta(0):
            _fail("unavailability.evidence.observed_at", "不可得证据来自未来")
        if age // timedelta(microseconds=1) > clock["max_age_seconds"] * 1_000_000:
            _fail("unavailability.evidence.observed_at", "不可得证据已过期")
    except _InputError as exc:
        return {
            "status": "invalid", "reason_code": "classification_clock_invalid",
            "classification": None, "errors": [f"{exc.field}: {exc.message}"],
        }
    allowed_reasons = _FALLBACK_METRIC_COMPATIBILITY.get(
        metrics["reason_code"]
    )
    if allowed_reasons is None or classification["reason_code"] not in allowed_reasons:
        return {
            "status": "ineligible",
            "reason_code": "classification_metric_mismatch",
            "classification": classification,
            "errors": ["classification_metric_mismatch"],
        }
    return {
        "status": "eligible",
        "reason_code": classification["reason_code"],
        "classification": classification,
    }


# ---------------------------------------------------------------------------
# 窗口计数纯状态：初始化、送达确认归并、阈值观测
# ---------------------------------------------------------------------------

_COUNT_STATE_FIELDS = (
    "schema",
    "version",
    "native_session_id",
    "session_generation",
    "scope_fingerprint",
    "last_session_revision",
    "confirmed_count",
    "first_turn_confirmed",
    "deliveries",
    "last_threshold_observation",
    "state_revision",
)
_COUNT_DELIVERY_FIELDS = (
    "ordinal",
    "delivery_id",
    "task_id",
    "attempt",
    "execution_id",
    "body_sha256",
    "native_session_id",
    "session_generation",
    "session_revision",
    "first_turn",
)
_RECEIPT_REQUIRED_FIELDS = (
    "delivery_id",
    "task_id",
    "attempt",
    "execution_id",
    "body_sha256",
    "native_session_id",
    "session_generation",
    "session_revision",
    "outcome",
)
_RECEIPT_ALLOWED_FIELDS = _RECEIPT_REQUIRED_FIELDS + ("first_turn",)
_OBSERVATION_STATE_FIELDS = (
    "threshold_met",
    "used_tokens",
    "capacity_tokens",
    "source",
    "session_revision",
    "sampled_at",
)
_OBSERVATION_INPUT_FIELDS = (
    "native_session_id",
    "session_generation",
    "session_revision",
    "used_tokens",
    "capacity_tokens",
    "source",
    "sampled_at",
)
_CONFIRMED_OUTCOMES = frozenset(
    ("delivered", "canceled_after_delivery", "timed_out_after_delivery")
)
_NON_COUNTING_OUTCOMES = frozenset(
    (
        "failed",
        "rejected",
        "preflight",
        "dry_run",
        "planned",
        "repeated_planning",
        "tool_call",
        "internal_step",
        "canceled_before_delivery",
        "timed_out_before_delivery",
    )
)


def _revision_same_type(left: str | int, right: str | int) -> bool:
    return _is_int(left) == _is_int(right)


def _delivery_logical_key(delivery: Mapping[str, Any]) -> tuple[str, int, str]:
    return (delivery["task_id"], delivery["attempt"], delivery["execution_id"])


def _normalize_delivery_record(value: Any, field: str = "delivery") -> dict[str, Any]:
    raw = _require_strict_mapping(
        value, field, _COUNT_DELIVERY_FIELDS, _COUNT_DELIVERY_FIELDS
    )
    if not _is_safe_int(raw["ordinal"], minimum=1):
        _fail(f"{field}.ordinal", "必须是 1..2^53-1 的整数")
    delivery_id = _require_identifier(raw["delivery_id"], f"{field}.delivery_id")
    task_id = _normalize_task_id(raw["task_id"])
    if not _is_safe_int(raw["attempt"], minimum=0):
        _fail(f"{field}.attempt", "必须是 0..2^53-1 的整数")
    execution_id = _require_identifier(
        raw["execution_id"], f"{field}.execution_id"
    )
    body_sha256 = _require_sha256(raw["body_sha256"], f"{field}.body_sha256")
    native_session_id = _require_identifier(
        raw["native_session_id"], f"{field}.native_session_id"
    )
    if not _is_safe_int(raw["session_generation"], minimum=1):
        _fail(f"{field}.session_generation", "必须是 1..2^53-1 的整数")
    session_revision = _normalize_revision(
        raw["session_revision"], f"{field}.session_revision"
    )
    if not isinstance(raw["first_turn"], bool):
        _fail(f"{field}.first_turn", "必须是布尔值")
    return {
        "ordinal": raw["ordinal"],
        "delivery_id": delivery_id,
        "task_id": task_id,
        "attempt": raw["attempt"],
        "execution_id": execution_id,
        "body_sha256": body_sha256,
        "native_session_id": native_session_id,
        "session_generation": raw["session_generation"],
        "session_revision": session_revision,
        "first_turn": raw["first_turn"],
    }


def _normalize_receipt(value: Any, field: str = "delivery") -> dict[str, Any]:
    raw = _require_strict_mapping(
        value, field, _RECEIPT_REQUIRED_FIELDS, _RECEIPT_ALLOWED_FIELDS
    )
    delivery_id = _require_identifier(raw["delivery_id"], f"{field}.delivery_id")
    task_id = _normalize_task_id(raw["task_id"])
    if not _is_safe_int(raw["attempt"], minimum=0):
        _fail(f"{field}.attempt", "必须是 0..2^53-1 的整数")
    execution_id = _require_identifier(
        raw["execution_id"], f"{field}.execution_id"
    )
    body_sha256 = _require_sha256(raw["body_sha256"], f"{field}.body_sha256")
    native_session_id = _require_identifier(
        raw["native_session_id"], f"{field}.native_session_id"
    )
    if not _is_safe_int(raw["session_generation"], minimum=1):
        _fail(f"{field}.session_generation", "必须是 1..2^53-1 的整数")
    session_revision = _normalize_revision(
        raw["session_revision"], f"{field}.session_revision"
    )
    if (
        not isinstance(raw["outcome"], str)
        or raw["outcome"] not in _CONFIRMED_OUTCOMES | _NON_COUNTING_OUTCOMES
    ):
        _fail(f"{field}.outcome", "不是支持的送达/失败结果")
    first_turn = raw.get("first_turn", False)
    if not isinstance(first_turn, bool):
        _fail(f"{field}.first_turn", "必须是布尔值")
    return {
        "delivery_id": delivery_id,
        "task_id": task_id,
        "attempt": raw["attempt"],
        "execution_id": execution_id,
        "body_sha256": body_sha256,
        "native_session_id": native_session_id,
        "session_generation": raw["session_generation"],
        "session_revision": session_revision,
        "outcome": raw["outcome"],
        "first_turn": first_turn,
    }


def _normalize_observation_input(value: Any) -> dict[str, Any]:
    raw = _require_strict_mapping(
        value,
        "observation",
        _OBSERVATION_INPUT_FIELDS,
        _OBSERVATION_INPUT_FIELDS,
    )
    native_session_id = _require_identifier(
        raw["native_session_id"], "observation.native_session_id"
    )
    if not _is_safe_int(raw["session_generation"], minimum=1):
        _fail("observation.session_generation", "必须是 1..2^53-1 的整数")
    session_revision = _normalize_revision(
        raw["session_revision"], "observation.session_revision"
    )
    if not _is_safe_int(raw["used_tokens"]):
        _fail("observation.used_tokens", "必须是非负安全整数")
    if not _is_safe_int(raw["capacity_tokens"], minimum=1):
        _fail("observation.capacity_tokens", "必须是正的安全整数")
    if raw["source"] not in ("projected", "pressure"):
        _fail("observation.source", "必须是 projected/pressure")
    try:
        sampled_at = _parse_time(raw["sampled_at"], "observation.sampled_at")
    except _InputError as exc:
        _fail("observation.sampled_at", exc.message)
    return {
        "native_session_id": native_session_id,
        "session_generation": raw["session_generation"],
        "session_revision": session_revision,
        "used_tokens": raw["used_tokens"],
        "capacity_tokens": raw["capacity_tokens"],
        "source": raw["source"],
        "sampled_at": sampled_at,
    }


def _normalize_observation_state(value: Any) -> dict[str, Any]:
    raw = _require_strict_mapping(
        value,
        "state.last_threshold_observation",
        _OBSERVATION_STATE_FIELDS,
        _OBSERVATION_STATE_FIELDS,
    )
    if not isinstance(raw["threshold_met"], bool):
        _fail(
            "state.last_threshold_observation.threshold_met",
            "必须是布尔值",
        )
    if not _is_safe_int(raw["used_tokens"]):
        _fail("state.last_threshold_observation.used_tokens", "必须是非负安全整数")
    if not _is_safe_int(raw["capacity_tokens"], minimum=1):
        _fail(
            "state.last_threshold_observation.capacity_tokens",
            "必须是正的安全整数",
        )
    if raw["source"] not in ("projected", "pressure"):
        _fail("state.last_threshold_observation.source", "必须是 projected/pressure")
    session_revision = _normalize_revision(
        raw["session_revision"], "state.last_threshold_observation.session_revision"
    )
    try:
        sampled_at = _parse_time(
            raw["sampled_at"], "state.last_threshold_observation.sampled_at"
        )
    except _InputError as exc:
        _fail("state.last_threshold_observation.sampled_at", exc.message)
    threshold_met = (
        raw["used_tokens"] * THRESHOLD_DENOMINATOR
        >= raw["capacity_tokens"] * THRESHOLD_NUMERATOR
    )
    # 旧状态按 60% 保存布尔投影；核对其原规则后，按原始 token 数重新投影为
    # 当前 70% 规则。仅兼容这两个已知规则，不修改原始观测、计数或历史交付。
    legacy_threshold_met = raw["used_tokens"] * 5 >= raw["capacity_tokens"] * 3
    if raw["threshold_met"] not in (threshold_met, legacy_threshold_met):
        _fail(
            "state.last_threshold_observation.threshold_met",
            "与原始整数占用不一致",
        )
    return {
        "threshold_met": threshold_met,
        "used_tokens": raw["used_tokens"],
        "capacity_tokens": raw["capacity_tokens"],
        "source": raw["source"],
        "session_revision": session_revision,
        "sampled_at": sampled_at.isoformat(),
    }


def _normalize_count_state(value: Any) -> dict[str, Any]:
    """严格校验计数状态；任何来源/顺序/重复/修订回退都判无效。"""

    raw = _require_strict_mapping(
        value, "state", _COUNT_STATE_FIELDS, _COUNT_STATE_FIELDS
    )
    if raw["schema"] != COUNT_STATE_SCHEMA:
        _fail("state.schema", "不是当前窗口计数 schema")
    if not _is_int(raw["version"]) or raw["version"] != COUNT_STATE_VERSION:
        _fail("state.version", "不是当前窗口计数版本")
    native_session_id = _require_identifier(
        raw["native_session_id"], "state.native_session_id"
    )
    if not _is_safe_int(raw["session_generation"], minimum=1):
        _fail("state.session_generation", "必须是 1..2^53-1 的整数")
    session_generation = raw["session_generation"]
    scope_fingerprint = _require_sha256(
        raw["scope_fingerprint"], "state.scope_fingerprint"
    )
    last_session_revision = _normalize_revision(
        raw["last_session_revision"], "state.last_session_revision"
    )
    if not _is_safe_int(raw["confirmed_count"], minimum=1):
        _fail("state.confirmed_count", "已有首轮确认时计数必须是 1..2^53-1")
    confirmed_count = raw["confirmed_count"]
    if raw["first_turn_confirmed"] is not True:
        _fail(
            "state.first_turn_confirmed",
            "计数状态必须证明新窗首轮已确认",
        )
    deliveries_raw = raw["deliveries"]
    if not isinstance(deliveries_raw, list):
        _fail("state.deliveries", "必须是数组")
    if len(deliveries_raw) != confirmed_count:
        _fail("state.deliveries", "数量与 confirmed_count 不一致")
    deliveries: list[dict[str, Any]] = []
    seen_delivery_ids: set[str] = set()
    seen_logical: set[tuple[str, int, str]] = set()
    for index, item in enumerate(deliveries_raw):
        delivery = _normalize_delivery_record(
            item, f"state.deliveries[{index}]"
        )
        if delivery["ordinal"] != index + 1:
            _fail(
                f"state.deliveries[{index}].ordinal",
                "必须从 1 连续递增",
            )
        if delivery["native_session_id"] != native_session_id:
            _fail(
                f"state.deliveries[{index}].native_session_id",
                "与状态绑定的原生窗口不一致",
            )
        if delivery["session_generation"] != session_generation:
            _fail(
                f"state.deliveries[{index}].session_generation",
                "与状态绑定的会话代次不一致",
            )
        if not _revision_same_type(
            delivery["session_revision"], last_session_revision
        ):
            _fail(
                f"state.deliveries[{index}].session_revision",
                "修订类型与状态不一致",
            )
        if _is_int(delivery["session_revision"]) and (
            delivery["session_revision"] > last_session_revision
        ):
            _fail(
                f"state.deliveries[{index}].session_revision",
                "晚于状态记录的最后修订",
            )
        if (index and _is_int(delivery["session_revision"])
                and delivery["session_revision"] < deliveries[-1]["session_revision"]):
            _fail(f"state.deliveries[{index}].session_revision", "交办历史修订倒序")
        if not _is_int(delivery["session_revision"]) and (
            delivery["session_revision"] != last_session_revision
        ):
            _fail(
                f"state.deliveries[{index}].session_revision",
                "不透明字符串修订与状态不一致",
            )
        if index == 0 and delivery["first_turn"] is not True:
            _fail("state.deliveries[0].first_turn", "第一条必须是已确认首轮")
        if index > 0 and delivery["first_turn"] is not False:
            _fail(
                f"state.deliveries[{index}].first_turn",
                "只有首轮记录可以标记 first_turn",
            )
        if delivery["delivery_id"] in seen_delivery_ids:
            _fail(
                f"state.deliveries[{index}].delivery_id",
                "同一 delivery ID 重复",
            )
        seen_delivery_ids.add(delivery["delivery_id"])
        logical = _delivery_logical_key(delivery)
        if logical in seen_logical:
            _fail(
                f"state.deliveries[{index}]",
                "同一任务/attempt/execution 重复",
            )
        seen_logical.add(logical)
        deliveries.append(delivery)
    if not _is_safe_int(raw["state_revision"], minimum=1):
        _fail("state.state_revision", "必须是 1..2^53-1 的整数")
    if raw["state_revision"] < confirmed_count:
        _fail(
            "state.state_revision",
            "不能小于已确认交办数，计数来历不完整",
        )
    observation_raw = raw["last_threshold_observation"]
    if observation_raw is None:
        observation = None
    else:
        observation = _normalize_observation_state(observation_raw)
        if not _revision_same_type(
            observation["session_revision"], last_session_revision
        ):
            _fail(
                "state.last_threshold_observation.session_revision",
                "修订类型与状态不一致",
            )
        if _is_int(observation["session_revision"]) and (
            observation["session_revision"] > last_session_revision
        ):
            _fail(
                "state.last_threshold_observation.session_revision",
                "晚于状态记录的最后修订",
            )
        if not _is_int(observation["session_revision"]) and (
            observation["session_revision"] != last_session_revision
        ):
            _fail(
                "state.last_threshold_observation.session_revision",
                "不透明字符串修订与状态不一致",
            )
    return {
        "schema": COUNT_STATE_SCHEMA,
        "version": COUNT_STATE_VERSION,
        "native_session_id": native_session_id,
        "session_generation": session_generation,
        "scope_fingerprint": scope_fingerprint,
        "last_session_revision": last_session_revision,
        "confirmed_count": confirmed_count,
        "first_turn_confirmed": True,
        "deliveries": deliveries,
        "last_threshold_observation": observation,
        "state_revision": raw["state_revision"],
    }


def _count_state_matches_candidate(
    state: Mapping[str, Any],
    scope: Mapping[str, Any],
    candidate_info: Mapping[str, Any],
) -> str | None:
    if state["scope_fingerprint"] != _fingerprint(scope):
        return "state_scope_mismatch"
    if state["native_session_id"] != candidate_info["native_session_id"]:
        return "state_window_mismatch"
    if state["session_generation"] != scope["session_generation"]:
        return "state_generation_mismatch"
    if not candidate_info["session_revision_valid"]:
        return "candidate_revision_missing"
    candidate_revision = candidate_info["session_revision"]
    last_revision = state["last_session_revision"]
    if not _revision_same_type(candidate_revision, last_revision):
        return "state_revision_type_mismatch"
    if _is_int(candidate_revision):
        if candidate_revision < last_revision:
            return "state_revision_rollback"
    elif candidate_revision != last_revision:
        # 不透明字符串修订无法证明先后；备用路径要求精确一致，避免读取恢复
        # 或旧状态被当成当前窗口。
        return "state_revision_unverifiable"
    return None


def _count_state_view(
    status: str,
    reason_code: str,
    *,
    state: Mapping[str, Any] | None = None,
    classification: Mapping[str, Any] | None = None,
    proposed_ordinal: int | None = None,
    requires_confirmation: bool = False,
    count_merge: str | None = None,
) -> dict[str, Any]:
    observation = state["last_threshold_observation"] if state else None
    return {
        "schema": COUNT_STATE_SCHEMA,
        "status": status,
        "reason_code": reason_code,
        "confirmed_count": state["confirmed_count"] if state else None,
        "proposed_ordinal": proposed_ordinal,
        "requires_delivery_confirmation": requires_confirmation,
        "count_merge": count_merge,
        "native_session_id": state["native_session_id"] if state else None,
        "session_generation": state["session_generation"] if state else None,
        "state_revision": state["state_revision"] if state else None,
        "last_threshold_observation_met": (
            observation["threshold_met"] if observation else None
        ),
        "scope_fingerprint": state["scope_fingerprint"] if state else None,
        "classification_reason": (
            classification["reason_code"] if classification else None
        ),
        "classification_category": (
            classification["category"] if classification else None
        ),
        "classification_error": None,
    }


def _count_result(
    status: str,
    reason_code: str,
    *,
    state: Mapping[str, Any] | None = None,
    incremented: bool = False,
    field_errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": COUNT_STATE_SCHEMA,
        "status": status,
        "reason_code": reason_code,
        "incremented": incremented,
        "state": copy.deepcopy(state) if state is not None else None,
        "confirmed_count": state["confirmed_count"] if state else None,
        "errors": list(field_errors or []),
    }


def _default_count_view(status: str, reason_code: str) -> dict[str, Any]:
    view = _count_state_view(status, reason_code)
    view["observation_intent"] = None
    return view


def _new_window_count_view(reason_code: str = "first_turn_pending") -> dict[str, Any]:
    """新窗尚无可信计数；计划不创建窗口，也不伪造首轮 ACK。"""

    view = _default_count_view("not_started", reason_code)
    view["proposed_ordinal"] = 1
    view["requires_delivery_confirmation"] = True
    view["count_merge"] = "after_confirmed_delivery"
    return view


def _attach_classification(
    view: dict[str, Any], classification: Mapping[str, Any] | None
) -> dict[str, Any]:
    view["classification_reason"] = (
        classification["reason_code"] if classification else None
    )
    view["classification_category"] = (
        classification["category"] if classification else None
    )
    view["classification_trust"] = (
        classification["evidence"]["trust"] if classification else None
    )
    return view


def _observation_intent(
    metrics: Mapping[str, Any], scope: Mapping[str, Any]
) -> dict[str, Any] | None:
    if metrics.get("status") != "known":
        return None
    sample = metrics.get("sample")
    if not isinstance(sample, Mapping):
        return None
    return {
        "requires_host_persist": True,
        "reason_code": "record_reliable_threshold_observation",
        "observation": {
            "native_session_id": sample.get("native_session_id"),
            "session_generation": sample.get("session_generation"),
            "session_revision": sample.get("session_revision"),
            "used_tokens": metrics.get("used_tokens"),
            "capacity_tokens": metrics.get("capacity_tokens"),
            "source": metrics.get("source"),
            "sampled_at": sample.get("sampled_at"),
        },
    }


def _known_metrics_count_view(
    count_state_value: Any,
    scope: Mapping[str, Any],
    candidate_info: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """可靠指标优先时只保留计数证据，不用计数改变换窗决定。"""

    if count_state_value is None:
        view = _default_count_view("not_required", "context_known_state_missing")
        return view
    try:
        state = _normalize_count_state(copy.deepcopy(count_state_value))
    except _InputError as exc:
        view = _default_count_view("invalid", "context_known_state_invalid")
        view["state_error"] = f"{exc.field}: {exc.message}"
        return view
    binding_error = _count_state_matches_candidate(state, scope, candidate_info)
    if binding_error is not None:
        view = _count_state_view(
            "unverified", f"context_known_{binding_error}", state=state
        )
        view["observation_intent"] = None
        return view
    view = _count_state_view(
        "verified", "context_known_count_retained", state=state
    )
    view["observation_intent"] = _observation_intent(metrics, scope)
    return view


def _missing_metrics_count_view(
    count_state_value: Any,
    scope: Mapping[str, Any],
    candidate_info: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    """返回 (计划原因码, window_count 视图)。

    只有完整、绑定该精确窗口、首轮起算且读数历史未被抹掉的状态才允许备用。
    """

    if count_state_value is None:
        return "new_fallback_count_unverified", _default_count_view(
            "missing", "count_state_missing"
        )
    try:
        state = _normalize_count_state(copy.deepcopy(count_state_value))
    except _InputError as exc:
        view = _default_count_view("invalid", "count_state_invalid")
        view["state_error"] = f"{exc.field}: {exc.message}"
        return "new_fallback_count_unverified", view
    binding_error = _count_state_matches_candidate(state, scope, candidate_info)
    if binding_error is not None:
        view = _count_state_view(
            "unverified", binding_error, state=state
        )
        view["observation_intent"] = None
        return "new_fallback_count_unverified", view
    observation = state["last_threshold_observation"]
    if observation is not None and observation["threshold_met"] is True:
        view = _count_state_view(
            "blocked_by_observation",
            "last_observation_threshold_met",
            state=state,
        )
        view["observation_intent"] = None
        return "new_fallback_threshold_observed", view
    if state["confirmed_count"] >= FALLBACK_LIMIT:
        view = _count_state_view(
            "exhausted", "fallback_limit_reached", state=state
        )
        view["observation_intent"] = None
        return "new_fallback_exhausted", view
    view = _count_state_view(
        "eligible",
        "missing_metrics_count_eligible",
        state=state,
        proposed_ordinal=state["confirmed_count"] + 1,
        requires_confirmation=True,
        count_merge="after_confirmed_delivery",
    )
    view["observation_intent"] = None
    return "reuse_missing_metrics_fallback", view


def _receipt_matches_stored(
    receipt: Mapping[str, Any], stored: Mapping[str, Any]
) -> bool:
    return (
        receipt["delivery_id"] == stored["delivery_id"]
        and receipt["task_id"] == stored["task_id"]
        and receipt["attempt"] == stored["attempt"]
        and receipt["execution_id"] == stored["execution_id"]
        and receipt["body_sha256"] == stored["body_sha256"]
        and receipt["native_session_id"] == stored["native_session_id"]
        and receipt["session_generation"] == stored["session_generation"]
    )


def _count_delivery_lookup(
    state: Mapping[str, Any], receipt: Mapping[str, Any]
) -> dict[str, Any]:
    by_delivery_id = None
    by_logical = None
    logical = _delivery_logical_key(receipt)
    for stored in state["deliveries"]:
        if stored["delivery_id"] == receipt["delivery_id"]:
            by_delivery_id = stored
        if _delivery_logical_key(stored) == logical:
            by_logical = stored
    if by_delivery_id is not None:
        if not _receipt_matches_stored(receipt, by_delivery_id):
            return {"status": "conflict", "reason_code": "delivery_id_conflict"}
        return {"status": "duplicate", "reason_code": "delivery_duplicate"}
    if by_logical is not None:
        if (
            receipt["body_sha256"] != by_logical["body_sha256"]
            or receipt["native_session_id"] != by_logical["native_session_id"]
            or receipt["session_generation"] != by_logical["session_generation"]
        ):
            return {"status": "conflict", "reason_code": "logical_delivery_conflict"}
        # 同一任务/attempt/execution 的重试回执，即使 delivery ID 不同也幂等。
        return {"status": "duplicate", "reason_code": "delivery_retry_duplicate"}
    return {"status": "new", "reason_code": "new_delivery"}


def _receipt_window_conflict(
    state: Mapping[str, Any], scope: Mapping[str, Any], receipt: Mapping[str, Any]
) -> str | None:
    if state["scope_fingerprint"] != _fingerprint(scope):
        return "state_scope_mismatch"
    if state["session_generation"] != scope["session_generation"]:
        return "state_generation_mismatch"
    if receipt["native_session_id"] != state["native_session_id"]:
        return "receipt_session_mismatch"
    if receipt["session_generation"] != state["session_generation"]:
        return "receipt_generation_mismatch"
    return None


def initialize_window_count(
    *,
    scope: Mapping[str, Any],
    native_session_id: str,
    first_delivery: Mapping[str, Any],
    previous_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """从已确认的新窗首轮建立计数状态（首轮计 1，不伪造 ACK）。

    ``first_delivery`` 必须来自宿主真实确认进入该原生窗口的正式指令；
    普通工具调用、预检、dry-run、重复规划或未投递失败不应调用本函数。
    ``previous_state`` 只用于防止同一窗口被再次初始化重置；新窗口应从
    ``None`` 开始。
    """

    try:
        scope_value = copy.deepcopy(scope)
        native_value = copy.deepcopy(native_session_id)
        first_value = copy.deepcopy(first_delivery)
        previous_value = copy.deepcopy(previous_state)
    except Exception:
        return _count_result("invalid", "input_uncopyable")

    try:
        scope_norm = _normalize_scope(scope_value, "scope")
        native_id = _require_identifier(native_value, "native_session_id")
        receipt = _normalize_receipt(first_value, "first_delivery")
        if receipt["first_turn"] is not True:
            _fail("first_delivery.first_turn", "初始化必须提供新窗首轮")
        if receipt["outcome"] not in _CONFIRMED_OUTCOMES:
            _fail("first_delivery.outcome", "未确认进入窗口的投递不能计数")
        if receipt["native_session_id"] != native_id:
            _fail("first_delivery.native_session_id", "与初始化窗口不一致")
        if receipt["session_generation"] != scope_norm["session_generation"]:
            _fail(
                "first_delivery.session_generation",
                "与作用域会话代次不一致",
            )
    except _InputError as exc:
        return _count_result(
            "invalid",
            "invalid_input",
            field_errors=[f"{exc.field}: {exc.message}"],
        )

    if previous_value is not None:
        try:
            previous = _normalize_count_state(previous_value)
        except _InputError as exc:
            return _count_result(
                "invalid",
                "previous_state_invalid",
                field_errors=[f"{exc.field}: {exc.message}"],
            )
        if (
            previous["scope_fingerprint"] == _fingerprint(scope_norm)
            and previous["native_session_id"] == native_id
            and previous["session_generation"] == scope_norm["session_generation"]
        ):
            duplicate = _count_delivery_lookup(previous, receipt)
            if duplicate["status"] == "duplicate":
                return _count_result(
                    "duplicate", duplicate["reason_code"], state=previous
                )
            return _count_result(
                "conflict",
                "state_already_initialized",
                state=previous,
            )
        return _count_result(
            "conflict",
            "previous_state_scope_mismatch",
            state=previous,
        )

    state = {
        "schema": COUNT_STATE_SCHEMA,
        "version": COUNT_STATE_VERSION,
        "native_session_id": native_id,
        "session_generation": scope_norm["session_generation"],
        "scope_fingerprint": _fingerprint(scope_norm),
        "last_session_revision": receipt["session_revision"],
        "confirmed_count": 1,
        "first_turn_confirmed": True,
        "deliveries": [
            {
                "ordinal": 1,
                "delivery_id": receipt["delivery_id"],
                "task_id": receipt["task_id"],
                "attempt": receipt["attempt"],
                "execution_id": receipt["execution_id"],
                "body_sha256": receipt["body_sha256"],
                "native_session_id": receipt["native_session_id"],
                "session_generation": receipt["session_generation"],
                "session_revision": receipt["session_revision"],
                "first_turn": True,
            }
        ],
        "last_threshold_observation": None,
        "state_revision": 1,
    }
    return _count_result("initialized", "first_turn_counted", state=state, incremented=True)


def confirm_window_delivery(
    *,
    state: Mapping[str, Any],
    scope: Mapping[str, Any],
    delivery: Mapping[str, Any],
) -> dict[str, Any]:
    """把宿主真实确认的送达回执幂等归并到窗口计数；不原地改输入。

    成功的重试/重复 ACK 只返回 duplicate，不重复计数；失败/预检/dry-run
    不计数；确认进入窗口后再取消/超时仍已消耗上下文，因此会按已确认投递
    计数且永不倒扣。相同身份不同正文或窗口事实冲突一律不覆盖。
    """

    try:
        state_value = copy.deepcopy(state)
        scope_value = copy.deepcopy(scope)
        delivery_value = copy.deepcopy(delivery)
    except Exception:
        return _count_result("invalid", "input_uncopyable")

    try:
        state_norm = _normalize_count_state(state_value)
    except _InputError as exc:
        return _count_result(
            "invalid",
            "state_invalid",
            field_errors=[f"{exc.field}: {exc.message}"],
        )
    try:
        scope_norm = _normalize_scope(scope_value, "scope")
        receipt = _normalize_receipt(delivery_value, "delivery")
    except _InputError as exc:
        return _count_result(
            "invalid",
            "invalid_input",
            state=state_norm,
            field_errors=[f"{exc.field}: {exc.message}"],
        )
    window_conflict = _receipt_window_conflict(state_norm, scope_norm, receipt)
    if window_conflict is not None:
        return _count_result(
            "conflict", window_conflict, state=state_norm
        )

    lookup = _count_delivery_lookup(state_norm, receipt)
    if lookup["status"] == "conflict":
        return _count_result(
            "conflict", lookup["reason_code"], state=state_norm
        )
    if lookup["status"] == "duplicate":
        return _count_result(
            "duplicate", lookup["reason_code"], state=state_norm
        )
    if receipt["outcome"] in _NON_COUNTING_OUTCOMES:
        return _count_result("not_counted", "delivery_not_confirmed", state=state_norm)
    if receipt["first_turn"] is True:
        return _count_result(
            "conflict", "first_turn_already_confirmed", state=state_norm
        )
    if not _revision_same_type(
        receipt["session_revision"], state_norm["last_session_revision"]
    ):
        return _count_result(
            "conflict", "revision_type_conflict", state=state_norm
        )
    if _is_int(receipt["session_revision"]) and (
        receipt["session_revision"] < state_norm["last_session_revision"]
    ):
        return _count_result(
            "conflict", "revision_rollback", state=state_norm
        )
    if not _is_int(receipt["session_revision"]) and (
        receipt["session_revision"] != state_norm["last_session_revision"]
    ):
        return _count_result(
            "conflict", "revision_unverifiable", state=state_norm
        )

    updated = copy.deepcopy(state_norm)
    updated["deliveries"].append(
        {
            "ordinal": updated["confirmed_count"] + 1,
            "delivery_id": receipt["delivery_id"],
            "task_id": receipt["task_id"],
            "attempt": receipt["attempt"],
            "execution_id": receipt["execution_id"],
            "body_sha256": receipt["body_sha256"],
            "native_session_id": receipt["native_session_id"],
            "session_generation": receipt["session_generation"],
            "session_revision": receipt["session_revision"],
            "first_turn": False,
        }
    )
    updated["confirmed_count"] += 1
    updated["last_session_revision"] = receipt["session_revision"]
    updated["state_revision"] += 1
    return _count_result(
        "incremented", "delivery_counted", state=updated, incremented=True
    )


def record_threshold_observation(
    *,
    state: Mapping[str, Any],
    scope: Mapping[str, Any],
    observation: Mapping[str, Any],
    now: datetime | str | int | None = None,
) -> dict[str, Any]:
    """记录可靠占比观测；显式 now 禁止未来数据，旧/冲突观测不覆盖历史。"""

    try:
        state_value = copy.deepcopy(state)
        scope_value = copy.deepcopy(scope)
        observation_value = copy.deepcopy(observation)
    except Exception:
        return _count_result("invalid", "input_uncopyable")

    try:
        state_norm = _normalize_count_state(state_value)
        scope_norm = _normalize_scope(scope_value, "scope")
        observed = _normalize_observation_input(observation_value)
        now_value = _parse_time(now, "now")
        if observed["sampled_at"] > now_value:
            _fail("observation.sampled_at", "观测来自未来")
    except _InputError as exc:
        return _count_result(
            "invalid",
            "invalid_input",
            field_errors=[f"{exc.field}: {exc.message}"],
        )
    if state_norm["scope_fingerprint"] != _fingerprint(scope_norm):
        return _count_result("conflict", "state_scope_mismatch", state=state_norm)
    if state_norm["session_generation"] != scope_norm["session_generation"]:
        return _count_result(
            "conflict", "state_generation_mismatch", state=state_norm
        )
    if observed["native_session_id"] != state_norm["native_session_id"]:
        return _count_result(
            "conflict", "observation_session_mismatch", state=state_norm
        )
    if observed["session_generation"] != state_norm["session_generation"]:
        return _count_result(
            "conflict", "observation_generation_mismatch", state=state_norm
        )
    if not _revision_same_type(
        observed["session_revision"], state_norm["last_session_revision"]
    ):
        return _count_result(
            "conflict", "revision_type_conflict", state=state_norm
        )
    if _is_int(observed["session_revision"]):
        if observed["session_revision"] < state_norm["last_session_revision"]:
            return _count_result(
                "conflict", "revision_rollback", state=state_norm
            )
    elif observed["session_revision"] != state_norm["last_session_revision"]:
        return _count_result(
            "conflict", "revision_unverifiable", state=state_norm
        )
    threshold_met = (
        observed["used_tokens"] * THRESHOLD_DENOMINATOR
        >= observed["capacity_tokens"] * THRESHOLD_NUMERATOR
    )
    stored = {
        "threshold_met": threshold_met,
        "used_tokens": observed["used_tokens"],
        "capacity_tokens": observed["capacity_tokens"],
        "source": observed["source"],
        "session_revision": observed["session_revision"],
        "sampled_at": observed["sampled_at"].isoformat(),
    }
    previous = state_norm["last_threshold_observation"]
    if previous is not None:
        previous_time = _parse_time(
            previous["sampled_at"], "state.last_threshold_observation.sampled_at"
        )
        if observed["sampled_at"] < previous_time:
            return _count_result("conflict", "observation_time_rollback", state=state_norm)
        if (observed["sampled_at"] == previous_time
                and observed["session_revision"] == previous["session_revision"]
                and stored != previous):
            return _count_result("conflict", "observation_event_conflict", state=state_norm)
    if state_norm["last_threshold_observation"] == stored:
        return _count_result(
            "duplicate", "observation_duplicate", state=state_norm
        )
    updated = copy.deepcopy(state_norm)
    updated["last_threshold_observation"] = stored
    updated["last_session_revision"] = observed["session_revision"]
    updated["state_revision"] += 1
    return _count_result(
        "recorded", "observation_recorded", state=updated, incremented=False
    )


def _parse_time(value: Any, field: str) -> datetime:
    if isinstance(value, bool):
        _fail(field, "必须是带时区的 ISO-8601 字符串或 epoch 秒")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            _fail(field, "必须带时区")
        try:
            return value.astimezone(timezone.utc)
        except (OverflowError, OSError, ValueError):
            _fail(field, "时间超出可处理范围")
    if _is_int(value):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            _fail(field, "epoch 秒超出可处理范围")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            _fail(field, "不能为空")
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            _fail(field, "不是合法 ISO-8601 时间")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            _fail(field, "必须带时区")
        try:
            return parsed.astimezone(timezone.utc)
        except (OverflowError, OSError, ValueError):
            _fail(field, "时间超出可处理范围")
    _fail(field, "必须是带时区的 ISO-8601 字符串或 epoch 秒")


def _valid_token_count(value: Any) -> int | None:
    if not _is_int(value):
        return None
    if value < 0 or value > MAX_SAFE_INTEGER:
        return None
    return value


def _sample_field(sample: Mapping[str, Any], canonical: str) -> tuple[bool, Any]:
    """返回 (字段是否存在, 值)；camelCase 别名同时出现时标记歧义。"""

    alias = _SAMPLE_ALIASES[canonical]
    has_canonical = canonical in sample
    has_alias = alias in sample
    if has_canonical and has_alias:
        return True, _AMBIGUOUS
    if has_canonical:
        return True, sample[canonical]
    if has_alias:
        return True, sample[alias]
    return False, None


def _empty_metrics(status: str, reason_code: str) -> dict[str, Any]:
    return {
        "status": status,
        "reason_code": reason_code,
        "source": None,
        "used_tokens": None,
        "capacity_tokens": None,
        "threshold_met": None,
        "exact_comparison": None,
        "sample": None,
    }


def _metrics_unknown(reason_code: str) -> dict[str, Any]:
    return _empty_metrics("unknown", reason_code)


def _metrics_known(
    *,
    source: str,
    used: int,
    capacity: int,
    sampled_at: datetime,
    now: datetime,
    age_us: int,
    max_age_seconds: int,
    native_session_id: str,
    sample_generation: int,
    sample_revision: str | int,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    threshold_met = (
        used * THRESHOLD_DENOMINATOR >= capacity * THRESHOLD_NUMERATOR
    )
    return {
        "status": "known",
        "reason_code": "ok",
        "source": source,
        "used_tokens": used,
        "capacity_tokens": capacity,
        "threshold_met": threshold_met,
        "exact_comparison": {
            "operator": ">=",
            "used_times_10": str(used * THRESHOLD_DENOMINATOR),
            "capacity_times_7": str(capacity * THRESHOLD_NUMERATOR),
        },
        "sample": {
            "native_session_id": native_session_id,
            "session_generation": sample_generation,
            "session_revision": sample_revision,
            "provider_id": scope["provider_id"],
            "model_id": scope["model_id"],
            "model_binding_fingerprint": scope["model_binding_fingerprint"],
            "sampled_at": sampled_at.isoformat(),
            "now": now.isoformat(),
            "age_ms": age_us // 1000,
            "max_age_seconds": max_age_seconds,
        },
    }


def _evaluate_metrics(
    scope: Mapping[str, Any],
    candidate: Mapping[str, Any],
    sample: Any,
) -> dict[str, Any]:
    """校验投影/最近请求指标；任何缺失、非法或身份不齐都保持未知。"""

    if sample is None:
        return _metrics_unknown("context_missing")
    if not isinstance(sample, Mapping):
        return _metrics_unknown("sample_invalid")

    if not candidate["native_session_id_valid"]:
        return _metrics_unknown("native_session_missing")
    if sample.get("native_session_id") != candidate["native_session_id"]:
        return _metrics_unknown("session_id_mismatch")

    sample_generation = sample.get("session_generation")
    if not _is_safe_int(sample_generation, minimum=1):
        return _metrics_unknown("generation_invalid")
    if sample_generation != scope["session_generation"]:
        return _metrics_unknown("generation_mismatch")

    if not candidate["session_revision_valid"]:
        return _metrics_unknown("candidate_revision_missing")
    revision_ok, sample_revision = _try_normalize_revision(
        sample.get("session_revision"), "context_sample.session_revision"
    )
    if not revision_ok:
        return _metrics_unknown("revision_invalid")
    if _canonical_json(sample_revision) != _canonical_json(
        candidate["session_revision"]
    ):
        return _metrics_unknown("revision_mismatch")

    for key in ("provider_id", "model_id", "model_binding_fingerprint"):
        if sample.get(key) != scope[key]:
            return _metrics_unknown("model_mismatch")

    if any(
        key not in sample
        for key in ("sampled_at", "now", "max_age_seconds")
    ):
        return _metrics_unknown("time_missing")
    try:
        sampled_at = _parse_time(sample["sampled_at"], "context_sample.sampled_at")
        now = _parse_time(sample["now"], "context_sample.now")
    except _InputError:
        return _metrics_unknown("time_invalid")

    max_age_seconds = sample.get("max_age_seconds")
    if not _is_safe_int(max_age_seconds, minimum=0):
        return _metrics_unknown("max_age_invalid")

    age = now - sampled_at
    if age < timedelta(0):
        return _metrics_unknown("sample_future")
    age_us = age // timedelta(microseconds=1)
    if age_us > max_age_seconds * 1_000_000:
        return _metrics_unknown("sample_expired")

    capacity_present, capacity_value = _sample_field(
        sample, "context_window"
    )
    if not capacity_present:
        return _metrics_unknown("capacity_missing")
    if capacity_value is _AMBIGUOUS:
        return _metrics_unknown("capacity_ambiguous")
    capacity = _valid_token_count(capacity_value)
    if capacity is None or capacity <= 0:
        return _metrics_unknown("capacity_invalid")

    projected_present, projected_value = _sample_field(
        sample, "projected_tokens"
    )
    pressure_present, pressure_value = _sample_field(
        sample, "pressure_tokens"
    )
    if projected_present:
        if projected_value is _AMBIGUOUS:
            return _metrics_unknown("projected_ambiguous")
        used = _valid_token_count(projected_value)
        if used is None:
            # 优先字段已提供但非法：不能悄悄回退到 pressure，避免看似可靠的低占比。
            return _metrics_unknown("projected_invalid")
        source = "projected"
    elif pressure_present:
        if pressure_value is _AMBIGUOUS:
            return _metrics_unknown("pressure_ambiguous")
        used = _valid_token_count(pressure_value)
        if used is None:
            return _metrics_unknown("pressure_invalid")
        source = "pressure"
    else:
        return _metrics_unknown("tokens_missing")

    return _metrics_known(
        source=source,
        used=used,
        capacity=capacity,
        sampled_at=sampled_at,
        now=now,
        age_us=age_us,
        max_age_seconds=max_age_seconds,
        native_session_id=candidate["native_session_id"],
        sample_generation=sample_generation,
        sample_revision=sample_revision,
        scope=scope,
    )


def _render_base_block(base: Mapping[str, Any]) -> str:
    return "\n".join(
        (
            "--- TALK BASE CONTRACT ---",
            f"version: {base['version']}",
            f"sha256: {base['sha256']}",
            "--- BASE CONTRACT TEXT ---",
            base["text"],
            "--- END BASE CONTRACT ---",
        )
    )


def _render_task_block(task: Mapping[str, Any]) -> str:
    lines = [
        "--- TALK TASK INCREMENT ---",
        f"task_id: {task['task_id']}",
        f"attempt: {task['attempt']}",
        f"execution_id: {task['execution_id']}",
        f"goal: {task['goal']}",
        "authorization:",
    ]
    lines.extend(f"- {item}" for item in task["authorization"])
    if "baseline_change" in task:
        lines.append(f"baseline_change: {task['baseline_change']}")
    if "authorization_change" in task:
        lines.append("authorization_change:")
        lines.extend(f"- {item}" for item in task["authorization_change"])
    if "acceptance_difference" in task:
        lines.append(f"acceptance_difference: {task['acceptance_difference']}")
    lines.extend(
        (
            "--- INCREMENT BODY ---",
            task["body"],
            "--- END TASK INCREMENT ---",
        )
    )
    return "\n".join(lines)


def _render_hall_block(messages: Sequence[str]) -> str:
    if not messages:
        return ""
    lines = ["--- NEW HALL MESSAGES ---"]
    lines.extend(
        f"[{index}] {message}" for index, message in enumerate(messages, start=1)
    )
    lines.append("--- END NEW HALL MESSAGES ---")
    return "\n".join(lines)


def _compose_delivery(
    base: Mapping[str, Any],
    task: Mapping[str, Any],
    messages: Sequence[str],
    *,
    include_base: bool,
) -> str:
    blocks: list[str] = []
    if include_base:
        blocks.append(_render_base_block(base))
    blocks.append(_render_task_block(task))
    hall = _render_hall_block(messages)
    if hall:
        blocks.append(hall)
    return "\n\n".join(blocks)


def _base_ref(base: Mapping[str, Any]) -> dict[str, Any]:
    return {"version": base["version"], "sha256": base["sha256"]}


def _task_ref(task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "attempt": task["attempt"],
        "execution_id": task["execution_id"],
    }


def _delivery_record(
    text: str,
    base: Mapping[str, Any],
    task: Mapping[str, Any],
    messages: Sequence[str],
    *,
    include_base: bool,
) -> dict[str, Any]:
    encoded = text.encode("utf-8")
    return {
        "text": text,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
        "characters": len(text),
        "includes": {
            "base_contract": include_base,
            "task_increment": True,
            "new_hall": bool(messages),
        },
        "base_contract": _base_ref(base),
        "task": _task_ref(task),
        "new_message_count": len(messages),
    }


def _archive_record(
    scope: Mapping[str, Any],
    base: Mapping[str, Any],
    task: Mapping[str, Any],
    messages: Sequence[str],
    *,
    mode: str,
    native_session_id: str | None,
    delivery_text: str,
) -> dict[str, Any]:
    encoded = delivery_text.encode("utf-8")
    return {
        "schema": SCHEMA_ARCHIVE,
        "mode": mode,
        "base_contract": _base_ref(base),
        "task": copy.deepcopy(dict(task)),
        "new_messages": list(messages),
        "scope_fingerprint": _fingerprint(scope),
        "identity": {
            "project_id": scope["project_id"],
            "target_member_id": scope["target_member_id"],
            "requester_id": scope["requester_id"],
            "continuity_key": scope["continuity_key"],
        },
        "session": {
            "native_session_id": native_session_id,
            "session_generation": (
                scope["session_generation"] if native_session_id is not None else None
            ),
            "status": (
                "selected_existing"
                if native_session_id is not None
                else "not_created"
            ),
        },
        "delivery": {
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "bytes": len(encoded),
            "mode": mode,
        },
    }


def _candidate_view(
    info: Mapping[str, Any] | None, *, selected: bool
) -> dict[str, Any] | None:
    if info is None:
        return None
    scope = info["scope"]
    return {
        "native_session_id": (
            info["native_session_id"] if info["native_session_id_valid"] else None
        ),
        "state": info["state"],
        "selected": bool(selected),
        "scope_verifiable": scope is not None,
        "scope_match": bool(info["scope_match"]),
        "scope_fingerprint": info["scope_fingerprint"],
        "scope_differences": (
            list(info["scope_differences"])
            if info["scope_differences"] is not None
            else None
        ),
        "session_generation": (
            scope["session_generation"] if scope is not None else None
        ),
        "session_revision": (
            info["session_revision"]
            if info["session_revision_valid"]
            else None
        ),
        "execution_channel_exclusive": info["execution_channel_exclusive"],
        "active_writer": info["active_writer"],
        "first_turn_confirmed": info["first_turn_confirmed"],
    }


def _reject_plan(
    *,
    selection: str | None,
    error: _InputError,
    reason_code: str = "reject_invalid_input",
    scope_fingerprint: str | None = None,
    window_count: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_PLAN,
        "action": "reject",
        "reason_code": reason_code,
        "reason": _REASON_TEXT.get(
            reason_code, _REASON_TEXT["reject_invalid_input"]
        ),
        "briefing_mode": "none",
        "native_session_ref": None,
        "session_generation": None,
        "selection": selection,
        "scope_fingerprint": scope_fingerprint,
        "base_contract": None,
        "task": None,
        "delivery": None,
        "archive": None,
        "metrics": _empty_metrics("not_applicable", reason_code),
        "candidate": None,
        "window_count": (
            dict(window_count)
            if window_count is not None
            else _default_count_view("not_evaluated", "plan_rejected")
        ),
        "warnings": [],
        "errors": [f"{error.field}: {error.message}"],
    }


def _wait_plan(
    *,
    reason_code: str,
    scope: Mapping[str, Any],
    base: Mapping[str, Any],
    task: Mapping[str, Any],
    candidate_info: Mapping[str, Any] | None,
    selection: str,
    execution_channel: Mapping[str, Any] | None = None,
    window_count: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_PLAN,
        "action": "wait",
        "reason_code": reason_code,
        "reason": _REASON_TEXT.get(reason_code, "暂不投递。"),
        "briefing_mode": "none",
        "native_session_ref": None,
        "session_generation": None,
        "selection": selection,
        "scope_fingerprint": _fingerprint(scope),
        "base_contract": _base_ref(base),
        "task": _task_ref(task),
        "delivery": None,
        "archive": None,
        "metrics": _empty_metrics("not_evaluated", "channel_unavailable"),
        "candidate": _candidate_view(candidate_info, selected=False),
        "execution_channel": dict(execution_channel) if execution_channel is not None else None,
        "window_count": (
            dict(window_count)
            if window_count is not None
            else _default_count_view("not_evaluated", "channel_unavailable")
        ),
        "warnings": [],
        "errors": [],
    }


def _new_plan(
    *,
    reason_code: str,
    scope: Mapping[str, Any],
    base: Mapping[str, Any],
    task: Mapping[str, Any],
    messages: Sequence[str],
    candidate_info: Mapping[str, Any] | None,
    selection: str,
    metrics: Mapping[str, Any],
    window_count: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if "text" not in base:
        return _reject_plan(
            selection=selection,
            error=_InputError("base_contract.text", "新窗完整计划需要提供基础正文"),
            reason_code="reject_base_text_required",
            scope_fingerprint=_fingerprint(scope),
            window_count=window_count,
        )
    text = _compose_delivery(base, task, messages, include_base=True)
    reason = _REASON_TEXT.get(reason_code, "生成新窗完整首轮计划。")
    if reason_code == "new_context_unknown":
        reason = f"{reason}（指标原因：{metrics['reason_code']}）"
    return {
        "schema": SCHEMA_PLAN,
        "action": "new_session",
        "reason_code": reason_code,
        "reason": reason,
        "briefing_mode": "full",
        "native_session_ref": None,
        "session_generation": None,
        "selection": selection,
        "scope_fingerprint": _fingerprint(scope),
        "base_contract": _base_ref(base),
        "task": _task_ref(task),
        "delivery": _delivery_record(
            text, base, task, messages, include_base=True
        ),
        "archive": _archive_record(
            scope,
            base,
            task,
            messages,
            mode="full",
            native_session_id=None,
            delivery_text=text,
        ),
        "metrics": dict(metrics),
        "candidate": _candidate_view(candidate_info, selected=False),
        "window_count": (
            dict(window_count)
            if window_count is not None
            else _new_window_count_view()
        ),
        "warnings": [],
        "errors": [],
    }


def _reuse_plan(
    *,
    scope: Mapping[str, Any],
    base: Mapping[str, Any],
    task: Mapping[str, Any],
    messages: Sequence[str],
    candidate_info: Mapping[str, Any],
    selection: str,
    metrics: Mapping[str, Any],
    reason_code: str = "reuse_session",
    window_count: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    text = _compose_delivery(base, task, messages, include_base=False)
    native_session_id = candidate_info["native_session_id"]
    return {
        "schema": SCHEMA_PLAN,
        "action": "reuse_session",
        "reason_code": reason_code,
        "reason": _REASON_TEXT[reason_code],
        "briefing_mode": "incremental",
        "native_session_ref": native_session_id,
        "session_generation": scope["session_generation"],
        "selection": selection,
        "scope_fingerprint": _fingerprint(scope),
        "base_contract": _base_ref(base),
        "task": _task_ref(task),
        "delivery": _delivery_record(
            text, base, task, messages, include_base=False
        ),
        "archive": _archive_record(
            scope,
            base,
            task,
            messages,
            mode="incremental",
            native_session_id=native_session_id,
            delivery_text=text,
        ),
        "metrics": dict(metrics),
        "candidate": _candidate_view(candidate_info, selected=True),
        "window_count": (
            dict(window_count)
            if window_count is not None
            else _default_count_view("not_required", "reuse_count_not_supplied")
        ),
        "warnings": [],
        "errors": [],
    }


def plan_execution_session(
    *,
    scope: Mapping[str, Any],
    base_contract: Mapping[str, Any],
    task: Mapping[str, Any],
    selection: str | None = "auto",
    candidate: Mapping[str, Any] | None = None,
    context_sample: Mapping[str, Any] | None = None,
    new_messages: Sequence[str] | None = None,
    execution_channel: Mapping[str, Any] | None = None,
    context_unavailability: Mapping[str, Any] | None = None,
    window_count_state: Mapping[str, Any] | None = None,
    fallback_clock: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """统一规划入口：校验显式输入、选择会话、判断 70% 阈值并生成正文/留档。

    参数（全部由调用方显式传入，本函数不读取外部状态）：

    ``scope``
        当前作用域。必填字段：
        ``project_id / target_member_id / requester_id / continuity_key /
        workspace_identity / runtime / runner_id / native_home_namespace /
        provider_id / model_id / model_binding_fingerprint /
        config_permission_fingerprint / service_launch_id /
        base_contract_version / base_contract_sha256`` 为非空字符串；
        ``workspace_verified`` 必须为 ``True``（由调用方核验真实工作区）；
        ``session_generation`` 为 1..2^53-1 的整数，同一窗口内稳定。
        ``model_binding_fingerprint`` 只代表配置绑定事实，不冒充后端模型证明。

    ``base_contract``
        ``version``、``sha256`` 和可选 ``text``；正文存在时须与 UTF-8 哈希一致。
        续窗可只传引用；新窗缺正文时拒绝，调用方按引用取回正文后重算。

    ``execution_channel``
        当前目标通道的 ``state``（ready/busy）、``active_writer`` 和
        ``execution_channel_exclusive``。所有投递都须显式确认通道可用，
        即使无候选或旧候选属于另一作用域也不能省略。

    ``task``
        本次增量。必填 ``task_id``、``attempt``、``execution_id``、``goal``、
        ``authorization``、``body``；可选 ``baseline_change``、
        ``authorization_change``、``acceptance_difference``。任务自己的
        attempt/execution 只用于本次增量与留档，不要求跨任务相同。

    ``selection``
        ``auto``（默认；有候选则尝试续用）、``new``（显式新窗）或
        ``reuse``（请求续用；无候选时拒绝）。

    ``candidate``
        派发者显式选定的候选快照，字段：``native_session_id``、``scope``、
        ``state``（``ready/busy/tainted/closed``）、
        ``execution_channel_exclusive``、``active_writer``、
        ``first_turn_confirmed``、``session_revision``。

    ``context_sample``
        显式上下文投影。字段：``native_session_id``、``session_generation``、
        ``session_revision``、``provider_id``、``model_id``、
        ``model_binding_fingerprint``、``projected_tokens``、
        ``pressure_tokens``、``context_window``、``sampled_at``、``now``、
        ``max_age_seconds``。优先合法 ``projected_tokens``；仅当其字段缺失时才
        考虑 ``pressure_tokens``。字段存在但非法不会回退。

    ``new_messages``
        只包含调用方明确传入的本次必要新 Hall 消息（字符串数组）；不读取历史。

    ``context_unavailability``
        可选，DSH 适配器/可信宿主给出的不可得分类（schema
        ``talk-dsh-context-unavailability-1``）。只有有限白名单原因、且
        精确 native session/generation/revision 与当前 scope 均匹配时才可能
        进入备用；裸 ``None``、未知 reason 或仅传可兜底布尔值都不会获准。

    ``window_count_state``
        可选，与精确 native session/generation/规范 JSON scope 指纹绑定的纯
        计数状态。必须证明首轮确认、从 1 连续累计、去重身份完整；可靠指标
        存在时不参与换窗决定，只在指标明确不可得时作为 10 次备用依据。
        本入口不修改状态、不预增计数。

    ``fallback_clock``
        备用路径必须显式提供 ``now`` 和 ``max_age_seconds``，校验不可得证明
        的时间。缺时钟、过期或未来证明不兜底；known 指标仍按其独立样本判定。

    返回计划是普通 dict / JSON 可序列化对象。``wait``/``reject`` 不带可执行
    正文；``new_session`` 不伪造 native session id，``reuse_session`` 才带候选
    id。``window_count`` 只表达计数意图：``count_merge`` 为
    ``after_confirmed_delivery`` 时，宿主必须在真实送达并确认后再调用
    :func:`confirm_window_delivery`；规划本身不是 ACK，也不代表已创建窗口。
    输入对象不会被修改。
    """

    try:
        scope_value = copy.deepcopy(scope)
        base_value = copy.deepcopy(base_contract)
        task_value = copy.deepcopy(task)
        candidate_value = copy.deepcopy(candidate)
        sample_value = copy.deepcopy(context_sample)
        messages_value = copy.deepcopy(new_messages)
        channel_value = copy.deepcopy(execution_channel)
        unavailability_value = copy.deepcopy(context_unavailability)
        count_state_value = copy.deepcopy(window_count_state)
        fallback_clock_value = copy.deepcopy(fallback_clock)
    except Exception:
        return _reject_plan(
            selection=None,
            error=_InputError("input", "输入对象无法复制"),
        )

    try:
        selection_norm = _normalize_selection(selection)
    except _InputError as exc:
        return _reject_plan(selection=None, error=exc)

    try:
        scope_norm = _normalize_scope(scope_value, "scope")
    except _InputError as exc:
        return _reject_plan(selection=selection_norm, error=exc)
    scope_fingerprint = _fingerprint(scope_norm)

    try:
        base_norm = _normalize_base_contract(base_value)
    except _InputError as exc:
        return _reject_plan(
            selection=selection_norm,
            error=exc,
            scope_fingerprint=scope_fingerprint,
        )

    try:
        task_norm = _normalize_task(task_value)
    except _InputError as exc:
        return _reject_plan(
            selection=selection_norm,
            error=exc,
            scope_fingerprint=scope_fingerprint,
        )

    try:
        messages_norm = _normalize_new_messages(messages_value)
    except _InputError as exc:
        return _reject_plan(
            selection=selection_norm,
            error=exc,
            scope_fingerprint=scope_fingerprint,
        )

    if (
        scope_norm["base_contract_version"] != base_norm["version"]
        or scope_norm["base_contract_sha256"] != base_norm["sha256"]
    ):
        return _reject_plan(
            selection=selection_norm,
            error=_InputError(
                "scope.base_contract_version",
                "与 base_contract.version/sha256 不一致",
            ),
            reason_code="reject_scope_base_mismatch",
            scope_fingerprint=scope_fingerprint,
        )

    try:
        candidate_info = _analyze_candidate(candidate_value)
    except _InputError as exc:
        return _reject_plan(
            selection=selection_norm,
            error=exc,
            scope_fingerprint=scope_fingerprint,
        )
    if candidate_info is not None:
        _compare_candidate_scope(candidate_info, scope_norm)

    channel = _current_channel(channel_value)
    current_channel_code = _channel_code(channel)
    if current_channel_code is not None:
        current_channel_code = {
            "wait_candidate_busy": "wait_channel_busy",
            "wait_candidate_state_unknown": "wait_channel_state_unknown",
        }.get(current_channel_code, current_channel_code)
        return _wait_plan(
            reason_code=current_channel_code, scope=scope_norm, base=base_norm,
            task=task_norm, candidate_info=candidate_info, selection=selection_norm,
            execution_channel=channel,
        )

    if candidate_info is None:
        if selection_norm == "reuse":
            return _reject_plan(
                selection=selection_norm,
                error=_InputError("candidate", "请求续用但未提供候选"),
                reason_code="reject_reuse_without_candidate",
                scope_fingerprint=scope_fingerprint,
            )
        return _new_plan(
            reason_code="new_no_candidate",
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=None,
            selection=selection_norm,
            metrics=_empty_metrics("not_applicable", "no_candidate"),
        )

    channel_code = _channel_code(candidate_info)
    if channel_code is not None:
        return _wait_plan(
            reason_code=channel_code,
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
        )

    if selection_norm == "new":
        return _new_plan(
            reason_code="new_explicit",
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=_empty_metrics("not_applicable", "explicit_new"),
        )

    if candidate_info["state"] == "tainted":
        return _new_plan(
            reason_code="new_session_tainted",
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=_empty_metrics("not_evaluated", "session_tainted"),
        )
    if candidate_info["state"] == "closed":
        return _new_plan(
            reason_code="new_session_closed",
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=_empty_metrics("not_evaluated", "session_closed"),
        )
    if not candidate_info["native_session_id_valid"]:
        return _new_plan(
            reason_code="new_candidate_unverifiable",
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=_empty_metrics("not_evaluated", "candidate_unverifiable"),
        )
    if candidate_info["scope"] is None:
        return _new_plan(
            reason_code="new_scope_unverifiable",
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=_empty_metrics("not_evaluated", "scope_unverifiable"),
        )
    if not candidate_info["scope_match"]:
        mismatch_code = _scope_mismatch_reason(candidate_info)
        return _new_plan(
            reason_code=mismatch_code,
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=_empty_metrics("not_evaluated", mismatch_code),
        )
    if candidate_info["first_turn_confirmed"] is not True:
        return _new_plan(
            reason_code="new_first_turn_unconfirmed",
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=_empty_metrics("not_evaluated", "first_turn_unconfirmed"),
        )

    metrics = _evaluate_metrics(scope_norm, candidate_info, sample_value)
    if metrics["status"] == "known":
        count_view = _known_metrics_count_view(
            count_state_value, scope_norm, candidate_info, metrics
        )
        if metrics["threshold_met"]:
            return _new_plan(
                reason_code="new_context_threshold",
                scope=scope_norm,
                base=base_norm,
                task=task_norm,
                messages=messages_norm,
                candidate_info=candidate_info,
                selection=selection_norm,
                metrics=metrics,
                window_count=count_view,
            )
        return _reuse_plan(
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=metrics,
            window_count=count_view,
        )

    # 原校验可能先报告过期或缺容量；备用必须继续检查其它显式非法字段。
    raw_error = (
        _raw_fallback_blocker(sample_value) if unavailability_value is not None else None
    )
    fallback = (
        {"status": "ineligible", "reason_code": raw_error, "classification": None, "errors": [raw_error]}
        if raw_error else _evaluate_context_unavailability(
            unavailability_value, scope_norm, candidate_info, metrics, fallback_clock_value
        )
    )
    if fallback["status"] == "eligible":
        plan_reason, count_view = _missing_metrics_count_view(
            count_state_value, scope_norm, candidate_info
        )
        if plan_reason == "reuse_missing_metrics_fallback":
            observation = count_state_value.get("last_threshold_observation")
            if (observation is not None and _parse_time(
                observation["sampled_at"], "observation.sampled_at"
            ) > _parse_time(fallback_clock_value["now"], "fallback_clock.now")):
                plan_reason = "new_fallback_count_unverified"
                count_view["status"] = "unverified"
                count_view["reason_code"] = "observation_future"
                count_view["proposed_ordinal"] = None
                count_view["requires_delivery_confirmation"] = False
                count_view["count_merge"] = None
        _attach_classification(count_view, fallback.get("classification"))
        if plan_reason == "reuse_missing_metrics_fallback":
            return _reuse_plan(
                scope=scope_norm,
                base=base_norm,
                task=task_norm,
                messages=messages_norm,
                candidate_info=candidate_info,
                selection=selection_norm,
                metrics=metrics,
                reason_code=plan_reason,
                window_count=count_view,
            )
        return _new_plan(
            reason_code=plan_reason,
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=metrics,
            window_count=count_view,
        )

    if fallback["status"] == "absent":
        count_view = _default_count_view(
            "not_required", "classification_absent"
        )
    else:
        classification = fallback.get("classification")
        if classification is not None:
            count_view = _count_state_view(
                "not_eligible",
                fallback["reason_code"],
                classification=classification,
            )
            _attach_classification(count_view, classification)
        else:
            count_view = _default_count_view(
                "unverified", fallback["reason_code"]
            )
            count_view["classification_reason"] = fallback.get(
                "classification_reason"
            )
            count_view["classification_category"] = fallback.get(
                "classification_category"
            )
            error_items = fallback.get("errors")
            if isinstance(error_items, list) and error_items:
                count_view["classification_error"] = str(error_items[0])
        count_view["observation_intent"] = None
    return _new_plan(
        reason_code=(
            "new_context_unknown"
            if fallback["status"] == "absent"
            else "new_fallback_classification_unverified"
        ),
        scope=scope_norm,
        base=base_norm,
        task=task_norm,
        messages=messages_norm,
        candidate_info=candidate_info,
        selection=selection_norm,
        metrics=metrics,
        window_count=count_view,
    )


def reconstruct_full_requirements(
    archive: Mapping[str, Any], *, base_contract: Mapping[str, Any] | None = None
) -> str:
    """从计划 ``archive`` 重建完整任务要求（基础合同 + 增量 + 新 Hall）。

    只读取留档和调用方按引用取回的基础正文，不访问外部状态。留档只保基础
    合同版本/哈希、本次任务差异及必要新消息，不逐轮复制完整背景。
    """

    if not isinstance(archive, Mapping):
        raise ValueError("archive 必须是对象")
    if archive.get("schema") != SCHEMA_ARCHIVE:
        raise ValueError("archive.schema 不匹配")
    try:
        ref = _normalize_base_contract(archive.get("base_contract"))
        base = _normalize_base_contract(base_contract, require_text=True)
        if _base_ref(base) != _base_ref(ref):
            _fail("base_contract", "提供的正文与留档合同引用不匹配")
        task = _normalize_task(archive.get("task"))
        messages = _normalize_new_messages(archive.get("new_messages"))
        mode = archive.get("mode")
        if mode not in ("full", "incremental"):
            _fail("archive.mode", "必须是 full/incremental")
        delivery = archive.get("delivery")
        if not isinstance(delivery, Mapping) or delivery.get("mode") != mode:
            _fail("archive.delivery", "投递模式与留档不一致")
        delivered = _compose_delivery(base, task, messages, include_base=mode == "full")
        encoded = delivered.encode("utf-8")
        if (
            delivery.get("sha256") != hashlib.sha256(encoded).hexdigest()
            or not _is_safe_int(delivery.get("bytes"))
            or delivery["bytes"] != len(encoded)
        ):
            _fail("archive.delivery", "投递哈希或字节长度不匹配")
    except _InputError as exc:
        raise ValueError(f"archive 不合法：{exc.field}") from exc
    return _compose_delivery(base, task, messages, include_base=True)
