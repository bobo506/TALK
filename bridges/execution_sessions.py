"""执行会话选择、上下文 60% 阈值与首轮/续轮投递计划离线内核。

本模块只使用调用方显式传入的数据：不访问环境变量、文件、数据库或网络，不
spawn 进程，不在导入时产生副作用，也不创建/恢复真实原生会话。统一入口
:func:`plan_execution_session` 返回一个可 JSON 序列化的计划，**不发送消息**、
不写 TALK 任务状态、不产生原生 session 成功事实。

动作：
- ``reuse_session``：续用指定候选，投递增量正文。
- ``new_session``：生成新窗计划，投递完整基础合同 + 本次增量。
- ``wait``：候选忙、存在活动 writer 或无法证明执行通道独占，暂不投递。
- ``reject``：输入不合法，未生成投递计划。

阈值只使用原始整数精确比较：``used * 5 >= capacity * 3``（即 ``>= 60%``）。
没有固定 10 轮或其他轮数后备规则。
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
    "MAX_SAFE_INTEGER",
    "THRESHOLD_DENOMINATOR",
    "THRESHOLD_NUMERATOR",
    "plan_execution_session",
    "reconstruct_full_requirements",
]

SCHEMA_PLAN = "execution-session-plan-1"
SCHEMA_ARCHIVE = "execution-session-archive-1"

# JSON / JavaScript 安全整数上界（2**53 - 1）。token 数、容量和代次均不得超出。
MAX_SAFE_INTEGER = 9_007_199_254_740_991

# 60% = 3/5；用 used * 5 >= capacity * 3 做原始整数比较。
THRESHOLD_NUMERATOR = 3
THRESHOLD_DENOMINATOR = 5

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
        "上下文原始占用已达到 60% 阈值，下一次投递转新窗并恢复完整基础介绍。"
    ),
    "new_context_unknown": (
        "候选上下文指标不可用，不能把未知占比当作可续用，生成新窗完整首轮计划。"
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
    "reuse_session": "候选作用域匹配且上下文低于 60%，生成增量续窗计划。",
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
            "used_times_5": str(used * THRESHOLD_DENOMINATOR),
            "capacity_times_3": str(capacity * THRESHOLD_NUMERATOR),
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
) -> dict[str, Any]:
    if "text" not in base:
        return _reject_plan(
            selection=selection,
            error=_InputError("base_contract.text", "新窗完整计划需要提供基础正文"),
            reason_code="reject_base_text_required",
            scope_fingerprint=_fingerprint(scope),
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
) -> dict[str, Any]:
    text = _compose_delivery(base, task, messages, include_base=False)
    native_session_id = candidate_info["native_session_id"]
    return {
        "schema": SCHEMA_PLAN,
        "action": "reuse_session",
        "reason_code": "reuse_session",
        "reason": _REASON_TEXT["reuse_session"],
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
) -> dict[str, Any]:
    """统一规划入口：校验显式输入、选择会话、判断 60% 阈值并生成正文/留档。

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

    返回计划是普通 dict / JSON 可序列化对象。``wait``/``reject`` 不带可执行
    正文；``new_session`` 不伪造 native session id，``reuse_session`` 才带候选
    id。输入对象不会被修改。
    """

    try:
        scope_value = copy.deepcopy(scope)
        base_value = copy.deepcopy(base_contract)
        task_value = copy.deepcopy(task)
        candidate_value = copy.deepcopy(candidate)
        sample_value = copy.deepcopy(context_sample)
        messages_value = copy.deepcopy(new_messages)
        channel_value = copy.deepcopy(execution_channel)
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
    if metrics["status"] != "known":
        return _new_plan(
            reason_code="new_context_unknown",
            scope=scope_norm,
            base=base_norm,
            task=task_norm,
            messages=messages_norm,
            candidate_info=candidate_info,
            selection=selection_norm,
            metrics=metrics,
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
        )

    return _reuse_plan(
        scope=scope_norm,
        base=base_norm,
        task=task_norm,
        messages=messages_norm,
        candidate_info=candidate_info,
        selection=selection_norm,
        metrics=metrics,
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
