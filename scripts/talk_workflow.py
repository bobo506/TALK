#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TALK 使用流程本地辅助：交付包校验 + 有界摘要（仅标准库，无第三方依赖）。

用法：
    python scripts/talk_workflow.py validate .tmp/workflow-usage-1/development.json --expect-task-id 38
    python scripts/talk_workflow.py summary  .tmp/workflow-usage-1/development.json --expect-task-id 38
    python scripts/talk_workflow.py summary  <交付包> --expect-task-id 38 --max-chars 800 --json

`--expect-task-id` 可选：传入后核对交付包 task_id 是否为本次任务（`38` 与 `#38` 等价），
用于防止旧文件或别的任务的报告被当成当前交付；不带参数时行为与旧版一致。

退出码：
    0 = 校验通过 / 摘要输出成功
    1 = 交付包不合法（缺字段、类型/长度/条数越界、自相矛盾、与 --expect-task-id 不一致）
    2 = 用法错误、文件不存在、非 UTF-8、JSON 解析失败（含嵌套过深）、文件过大

边界（重要）：
    - 只校验交付包格式与自报一致性，不代表业务验收通过，不自动收取或 accept 任务。
    - 不访问 TALK 数据库、HTTP、MCP 或 bridge，不改变任何任务状态。
    - 不把 runner / 任务状态 succeeded 推断为交付结论 complete。
    - 报错与摘要都不回显原任务正文、Hall 历史、未知字段与长日志原文。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA_ID = "talk-delivery-1"

# 交付包文件上限：交付包是结构化摘要，不是日志容器。
MAX_REPORT_BYTES = 64 * 1024

# 深度嵌套 JSON 会让 json 解析器抛 RecursionError；统一转成这条短错误，
# 不输出 traceback，也不回显任何原输入片段。
DEEP_NESTING_MESSAGE = "JSON 嵌套层级过深，超出解析上限；请确认交付包是结构化短文本"

# 有界摘要：默认总长度上限（字符），可用 --max-chars 调整，但会被夹到下面的区间。
DEFAULT_SUMMARY_LIMIT = 1200
MIN_SUMMARY_LIMIT = 600
MAX_SUMMARY_LIMIT = 4000
NOTICE_RESERVE = 160
ITEM_PREVIEW_CHARS = 80
MIN_ITEM_CHARS = 24
SECTION_ITEM_LIMIT = 6

CONCLUSIONS = ("complete", "partial", "blocked")
VERIFICATION_RESULTS = ("pass", "fail", "not_run")
TOP_LEVEL_FIELDS = (
    "task_id",
    "conclusion",
    "completed",
    "unfinished",
    "blocked",
    "changed_files",
    "baseline",
    "verification",
    "limitations",
    "progress_draft",
)
TEXT_LIMITS = {"task_id": 64, "conclusion": 16}
LIST_LIMITS = {
    # completed 允许为空数组，但 conclusion 为 complete/partial 时由一致性规则要求非空。
    "completed": (20, 300, 0),
    "unfinished": (20, 300, 0),
    "blocked": (20, 300, 0),
    "changed_files": (50, 200, 0),
    "limitations": (20, 300, 0),
}
BASELINE_LIMITS = {"ref": 120, "diff_note": 300}
BASELINE_KEYS = tuple(BASELINE_LIMITS)
VERIFICATION_LIMITS = {"check": 120, "result": 16, "evidence": 300}
VERIFICATION_KEYS = tuple(VERIFICATION_LIMITS)
PROGRESS_LIMITS = {"summary": 300, "next": 300}
PROGRESS_KEYS = tuple(PROGRESS_LIMITS)

TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9#][A-Za-z0-9#._-]{0,63}$")
WINDOWS_ABS_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 未知字段提示：这些都是"不要回灌进交付包"的常见来源。
UNKNOWN_FIELD_HINTS = {
    "status": "runner/任务状态不属于交付包字段；succeeded 不能推断为 complete，请用 conclusion",
    "task_status": "runner/任务状态不属于交付包字段；succeeded 不能推断为 complete，请用 conclusion",
    "runner_status": "runner/任务状态不属于交付包字段；succeeded 不能推断为 complete，请用 conclusion",
    "succeeded": "runner/任务状态不属于交付包字段；succeeded 不能推断为 complete，请用 conclusion",
    "task": "原任务正文默认不进入交付包，请改用结构化字段",
    "task_text": "原任务正文默认不进入交付包，请改用结构化字段",
    "prompt": "原任务正文默认不进入交付包，请改用结构化字段",
    "hall": "Hall 历史默认不进入交付包，请改用结构化字段",
    "messages": "Hall 历史默认不进入交付包，请改用结构化字段",
    "history": "Hall 历史默认不进入交付包，请改用结构化字段",
    "log": "长日志默认不进入交付包，请改用简短 evidence",
    "logs": "长日志默认不进入交付包，请改用简短 evidence",
    "stdout": "长日志默认不进入交付包，请改用简短 evidence",
    "stderr": "长日志默认不进入交付包，请改用简短 evidence",
    "diff": "完整 diff 默认不进入交付包，请在 baseline.diff_note 里写结论性描述",
}

REDACTED = "[REDACTED]"
# 只覆盖可机械识别的常见形态；未命中的密钥仍应由"不要写进交付包"这条规则兜住。
SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(api[_-]?key|apikey|access[_-]?token|token|secret|password|passwd|pwd|authorization)\b"
        r"(\s*[:=]\s*)(\S+)"
    ),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_\-]{5,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
)


class WorkflowError(Exception):
    """用法或读取层面的错误（退出码 2）。"""


@dataclass(frozen=True)
class Issue:
    field: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message}


@dataclass
class ValidationResult:
    ok: bool
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    data: dict[str, Any] | None = None


# --------------------------------------------------------------------------
# 脱敏
# --------------------------------------------------------------------------


def redact_secrets(text: str) -> tuple[str, int]:
    """把疑似密钥的值替换为 [REDACTED]，返回 (脱敏后文本, 命中次数)。"""
    if not isinstance(text, str) or not text:
        return text, 0
    count = 0
    result = text

    def _sub_assignment(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}{match.group(2)}{REDACTED}"

    def _sub_token(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return REDACTED

    for index, pattern in enumerate(SECRET_PATTERNS):
        result = pattern.sub(_sub_assignment if index == 0 else _sub_token, result)
    return result, count


def _iter_strings(value: Any, path: str = "<root>") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_strings(item, f"{path}[{index}]")


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------


def _safe_label(raw: Any, limit: int = 32) -> str:
    text = str(raw)
    text = CONTROL_PATTERN.sub("", text)
    return text[:limit]


def normalize_task_id(value: Any) -> str | None:
    """把 task_id 的既有写法规范化：去首尾空白与一个前导 `#`，`38` 与 `#38` 等价。

    非字符串或规范化后为空返回 None（表示"不可比对"）。
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    return text or None


def _check_text(
    container: dict[str, Any],
    key: str,
    path: str,
    max_chars: int,
    errors: list[Issue],
    *,
    allow_empty: bool = False,
) -> str | None:
    if key not in container:
        errors.append(Issue(path, "missing_field", "缺少必填字段"))
        return None
    value = container[key]
    if not isinstance(value, str):
        errors.append(Issue(path, "wrong_type", "必须是字符串"))
        return None
    if not value.strip() and not allow_empty:
        errors.append(Issue(path, "empty_value", "不能为空"))
        return None
    if len(value) > max_chars:
        errors.append(
            Issue(path, "too_long", f"超过长度上限 {max_chars} 字符（实际 {len(value)}）")
        )
        return None
    if "\n" in value or "\r" in value or "\t" in value:
        errors.append(Issue(path, "multiline_text", "不允许换行或制表符，请写单行短句"))
        return None
    if CONTROL_PATTERN.search(value):
        errors.append(Issue(path, "control_char", "包含不可见控制字符"))
        return None
    return value


def _check_text_list(
    container: dict[str, Any],
    key: str,
    path: str,
    max_items: int,
    item_max_chars: int,
    min_items: int,
    errors: list[Issue],
    *,
    is_path: bool = False,
) -> list[str] | None:
    if key not in container:
        errors.append(Issue(path, "missing_field", "缺少必填字段（允许空数组但不能缺省）"))
        return None
    value = container[key]
    if not isinstance(value, list):
        errors.append(Issue(path, "wrong_type", "必须是字符串数组"))
        return None
    if len(value) > max_items:
        errors.append(
            Issue(path, "too_many_items", f"条目数超过上限 {max_items}（实际 {len(value)}）")
        )
        return None
    if len(value) < min_items:
        errors.append(Issue(path, "too_few_items", f"至少需要 {min_items} 条"))
        return None
    items: list[str] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, str):
            errors.append(Issue(item_path, "wrong_type", "必须是字符串"))
            continue
        if not item.strip():
            errors.append(Issue(item_path, "empty_value", "不能为空"))
            continue
        if len(item) > item_max_chars:
            errors.append(
                Issue(
                    item_path,
                    "too_long",
                    f"超过长度上限 {item_max_chars} 字符（实际 {len(item)}）",
                )
            )
            continue
        if any(ch in item for ch in "\r\n\t"):
            errors.append(Issue(item_path, "multiline_text", "不允许换行或制表符"))
            continue
        if CONTROL_PATTERN.search(item):
            errors.append(Issue(item_path, "control_char", "包含不可见控制字符"))
            continue
        if is_path and (
            WINDOWS_ABS_PATTERN.match(item) or item.startswith("/") or item.startswith("\\\\")
        ):
            errors.append(Issue(item_path, "not_relative_path", "必须是仓库相对路径"))
            continue
        items.append(item)
    return items


def _check_object_keys(
    container: dict[str, Any],
    key: str,
    path: str,
    allowed: Sequence[str],
    errors: list[Issue],
) -> dict[str, Any] | None:
    if key not in container:
        errors.append(Issue(path, "missing_field", "缺少必填字段"))
        return None
    value = container[key]
    if not isinstance(value, dict):
        errors.append(Issue(path, "wrong_type", "必须是对象"))
        return None
    for raw_key in value:
        if raw_key not in allowed:
            errors.append(
                Issue(
                    f"{path}.{_safe_label(raw_key)}",
                    "unknown_field",
                    f"不允许的字段，仅支持 {'/'.join(allowed)}",
                )
            )
    return value


def _check_unknown_top_level(data: dict[str, Any], errors: list[Issue]) -> None:
    for raw_key in data:
        if raw_key in TOP_LEVEL_FIELDS:
            continue
        label = _safe_label(raw_key)
        hint = UNKNOWN_FIELD_HINTS.get(str(raw_key), "未知字段一律拒收，避免原任务/Hall/日志回灌")
        errors.append(Issue(label, "unknown_field", hint))


def validate_report(data: Any, *, expect_task_id: str | None = None) -> ValidationResult:
    """校验交付包，返回结构化结果；不打印、不写文件。

    expect_task_id 非空时额外核对"这份包是不是本次任务的交付"：规范化后必须一致，
    否则判不通过。该检查放在最前面，保证报错列表被截断时它一定可见。
    """
    errors: list[Issue] = []
    warnings: list[Issue] = []

    if not isinstance(data, dict):
        errors.append(Issue("<root>", "wrong_type", "交付包顶层必须是 JSON 对象"))
        return ValidationResult(ok=False, errors=errors, warnings=warnings, data=None)

    if expect_task_id is not None:
        expected = normalize_task_id(expect_task_id)
        actual = normalize_task_id(data.get("task_id"))
        expected_label = _safe_label(expect_task_id, 64)
        if expected is None:
            errors.append(
                Issue("task_id", "unexpected_task_id", "--expect-task-id 为空；请传本次 TALK 任务号")
            )
        elif actual is None:
            errors.append(
                Issue(
                    "task_id",
                    "unexpected_task_id",
                    f"交付包缺少可用的 task_id，无法确认是本次任务（本次任务号 {expected_label}）",
                )
            )
        elif actual != expected:
            errors.append(
                Issue(
                    "task_id",
                    "unexpected_task_id",
                    f"交付包 task_id={_safe_label(actual, 64)} 不是本次任务号 {expected_label}；"
                    "可能是旧文件或另一个任务的报告",
                )
            )

    _check_unknown_top_level(data, errors)

    _check_text(data, "task_id", "task_id", TEXT_LIMITS["task_id"], errors)
    task_id = data.get("task_id")
    if isinstance(task_id, str) and task_id.strip() and not TASK_ID_PATTERN.match(task_id):
        errors.append(
            Issue("task_id", "bad_format", "只允许字母/数字/#/./_/-，长度 1-64，且不能含空格")
        )

    conclusion = _check_text(data, "conclusion", "conclusion", TEXT_LIMITS["conclusion"], errors)
    if isinstance(conclusion, str) and conclusion not in CONCLUSIONS:
        errors.append(
            Issue("conclusion", "bad_enum", f"取值必须是 {'/'.join(CONCLUSIONS)} 之一")
        )
        conclusion = None

    completed = _check_text_list(
        data, "completed", "completed", LIST_LIMITS["completed"][0], LIST_LIMITS["completed"][1],
        LIST_LIMITS["completed"][2], errors,
    )
    unfinished = _check_text_list(
        data, "unfinished", "unfinished", LIST_LIMITS["unfinished"][0], LIST_LIMITS["unfinished"][1],
        LIST_LIMITS["unfinished"][2], errors,
    )
    blocked = _check_text_list(
        data, "blocked", "blocked", LIST_LIMITS["blocked"][0], LIST_LIMITS["blocked"][1],
        LIST_LIMITS["blocked"][2], errors,
    )
    _check_text_list(
        data, "changed_files", "changed_files", LIST_LIMITS["changed_files"][0],
        LIST_LIMITS["changed_files"][1], LIST_LIMITS["changed_files"][2], errors, is_path=True,
    )
    _check_text_list(
        data, "limitations", "limitations", LIST_LIMITS["limitations"][0],
        LIST_LIMITS["limitations"][1], LIST_LIMITS["limitations"][2], errors,
    )

    baseline = _check_object_keys(data, "baseline", "baseline", BASELINE_KEYS, errors)
    if baseline is not None:
        _check_text(baseline, "ref", "baseline.ref", BASELINE_LIMITS["ref"], errors)
        _check_text(baseline, "diff_note", "baseline.diff_note", BASELINE_LIMITS["diff_note"], errors)

    # verification 是对象数组，单独校验。
    failed_verification: list[int] = []
    if "verification" not in data:
        errors.append(Issue("verification", "missing_field", "缺少必填字段"))
    else:
        raw_items = data.get("verification")
        if isinstance(raw_items, list):
            if len(raw_items) > 20:
                errors.append(
                    Issue("verification", "too_many_items", f"条目数超过上限 20（实际 {len(raw_items)}）")
                )
            elif not raw_items:
                errors.append(Issue("verification", "too_few_items", "至少需要 1 条验证记录"))
            for index, item in enumerate(raw_items):
                item_path = f"verification[{index}]"
                if not isinstance(item, dict):
                    errors.append(Issue(item_path, "wrong_type", "必须是对象"))
                    continue
                for raw_key in item:
                    if raw_key not in VERIFICATION_KEYS:
                        errors.append(
                            Issue(
                                f"{item_path}.{_safe_label(raw_key)}",
                                "unknown_field",
                                f"不允许的字段，仅支持 {'/'.join(VERIFICATION_KEYS)}",
                            )
                        )
                _check_text(item, "check", f"{item_path}.check", VERIFICATION_LIMITS["check"], errors)
                result = _check_text(
                    item, "result", f"{item_path}.result", VERIFICATION_LIMITS["result"], errors
                )
                if isinstance(result, str) and result not in VERIFICATION_RESULTS:
                    errors.append(
                        Issue(
                            f"{item_path}.result",
                            "bad_enum",
                            f"取值必须是 {'/'.join(VERIFICATION_RESULTS)} 之一",
                        )
                    )
                elif result == "fail":
                    failed_verification.append(index)
                _check_text(
                    item, "evidence", f"{item_path}.evidence", VERIFICATION_LIMITS["evidence"], errors
                )
        elif raw_items is not None:
            errors.append(Issue("verification", "wrong_type", "必须是对象数组"))

    progress = _check_object_keys(data, "progress_draft", "progress_draft", PROGRESS_KEYS, errors)
    if progress is not None:
        _check_text(progress, "summary", "progress_draft.summary", PROGRESS_LIMITS["summary"], errors)
        _check_text(progress, "next", "progress_draft.next", PROGRESS_LIMITS["next"], errors)

    # 自报一致性：只做机械规则，不做业务判断。
    if conclusion == "complete":
        if unfinished:
            errors.append(Issue("conclusion", "contradiction", "结论 complete 与 unfinished 非空互斥"))
        if blocked:
            errors.append(Issue("conclusion", "contradiction", "结论 complete 与 blocked 非空互斥"))
        if completed is not None and not completed:
            errors.append(Issue("completed", "contradiction", "结论 complete 时 completed 不能为空"))
        # complete 是"本次交付可用"的自报结论，与自己的失败验证记录直接冲突；
        # 这不属于业务验收判断，不能用"验收另算"豁免。not_run 是"确实没跑"，不算冲突。
        for index in failed_verification:
            errors.append(
                Issue(
                    f"verification[{index}].result",
                    "contradiction",
                    "结论 complete 与 result=fail 自报矛盾；请改报 partial/blocked，或修复后重跑该项",
                )
            )
    elif conclusion == "partial":
        if completed is not None and not completed:
            errors.append(Issue("completed", "contradiction", "结论 partial 时 completed 不能为空"))
        if completed is not None and not unfinished and not blocked:
            errors.append(
                Issue("conclusion", "contradiction", "结论 partial 必须列出 unfinished 或 blocked")
            )
    elif conclusion == "blocked":
        if blocked is not None and not blocked:
            errors.append(Issue("blocked", "contradiction", "结论 blocked 时 blocked 不能为空"))

    secret_hits = 0
    secret_fields: list[str] = []
    for path, text in _iter_strings(data):
        _, hits = redact_secrets(text)
        if hits:
            secret_hits += hits
            if path not in secret_fields:
                secret_fields.append(path)
    if secret_hits:
        warnings.append(
            Issue(
                ", ".join(secret_fields[:5]),
                "secret_like_text",
                f"疑似密钥 {secret_hits} 处；输出已脱敏，建议改为引用环境变量或不写值",
            )
        )

    ok = not errors
    return ValidationResult(ok=ok, errors=errors, warnings=warnings, data=data if ok else None)


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------


def load_report(path: Path) -> Any:
    """读取交付包（显式 UTF-8，限长）。读取层问题抛 WorkflowError。"""
    if not path.exists():
        raise WorkflowError(f"文件不存在：{path}")
    if not path.is_file():
        raise WorkflowError(f"不是文件：{path}")
    raw = path.read_bytes()
    if len(raw) > MAX_REPORT_BYTES:
        raise WorkflowError(
            f"交付包过大：{len(raw)} 字节，上限 {MAX_REPORT_BYTES} 字节；请只保留结构化字段"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkflowError(f"文件不是合法 UTF-8（首个错误字节偏移 {exc.start}）") from exc
    if text.startswith("\ufeff"):
        text = text[1:]  # 容忍 Windows 工具写入的 UTF-8 BOM
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"JSON 解析失败（第 {exc.lineno} 行第 {exc.colno} 列）") from exc
    except RecursionError as exc:
        # 深度嵌套 JSON（如几万层数组）会在此抛 RecursionError；转短错误，不吐 traceback 与原文。
        raise WorkflowError(DEEP_NESTING_MESSAGE) from exc
    return data


# --------------------------------------------------------------------------
# 有界摘要
# --------------------------------------------------------------------------


def _clamp_limit(value: int) -> int:
    return max(MIN_SUMMARY_LIMIT, min(MAX_SUMMARY_LIMIT, int(value)))


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def build_summary(data: dict[str, Any], *, max_chars: int = DEFAULT_SUMMARY_LIMIT) -> dict[str, Any]:
    """生成有界摘要：只输出允许字段，总长受限，被截断一定可见。"""
    limit = _clamp_limit(max_chars)
    redactions = 0
    clipped_items = 0

    def clean(value: str) -> str:
        nonlocal redactions
        text, hits = redact_secrets(value)
        redactions += hits
        return text

    def preview(value: str) -> str:
        nonlocal clipped_items
        text = clean(value)
        if len(text) > ITEM_PREVIEW_CHARS:
            clipped_items += 1
            return text[: ITEM_PREVIEW_CHARS - 1] + "…"
        return text

    task_id = data.get("task_id")
    task_id_text = clean(task_id) if isinstance(task_id, str) and task_id else "(未知)"
    conclusion = data.get("conclusion")
    conclusion_text = conclusion if conclusion in CONCLUSIONS else "(未知)"

    baseline = data.get("baseline") if isinstance(data.get("baseline"), dict) else {}
    baseline_ref = baseline.get("ref")
    baseline_ref_text = clean(baseline_ref) if isinstance(baseline_ref, str) and baseline_ref else "(未填)"
    diff_note = baseline.get("diff_note")
    diff_note_text = clean(diff_note) if isinstance(diff_note, str) and diff_note else "(未填)"

    progress = data.get("progress_draft") if isinstance(data.get("progress_draft"), dict) else {}
    progress_summary = progress.get("summary")
    progress_next = progress.get("next")

    verification_lines: list[str] = []
    raw_verification = data.get("verification")
    if isinstance(raw_verification, list):
        for item in raw_verification:
            if not isinstance(item, dict):
                continue
            check = item.get("check")
            result = item.get("result")
            if isinstance(check, str) and check:
                verification_lines.append(f"{preview(check)}={clean(result) if isinstance(result, str) else '?'}")

    # 区块按优先级排列：摘要头/基线 > 阻塞 > 未完成 > 已完成 > 变更文件 > 限制 > 验证 > 进度草稿。
    sections: list[tuple[str, list[str], int | None]] = [
        ("阻塞", [preview(x) for x in _text_list(data.get("blocked"))], None),
        ("未完成", [preview(x) for x in _text_list(data.get("unfinished"))], None),
        ("已完成", [preview(x) for x in _text_list(data.get("completed"))], SECTION_ITEM_LIMIT),
        ("变更文件", [preview(x) for x in _text_list(data.get("changed_files"))], SECTION_ITEM_LIMIT),
        ("限制", [preview(x) for x in _text_list(data.get("limitations"))], SECTION_ITEM_LIMIT),
        ("验证", verification_lines, SECTION_ITEM_LIMIT),
    ]

    progress_text = preview(progress_summary) if isinstance(progress_summary, str) and progress_summary else "(未填)"
    next_text = preview(progress_next) if isinstance(progress_next, str) and progress_next else "(未填)"

    # (标签, 固定行或 None, 条目预览, 条目总数, 展示上限)
    blocks: list[tuple[str, str | None, list[str], int, int | None]] = [
        ("摘要头", f"交付包摘要 schema={SCHEMA_ID} task_id={task_id_text} 结论={conclusion_text}", [], 0, None),
        ("基线", f"基线={baseline_ref_text} 差异说明={diff_note_text}", [], 0, None),
    ]
    for label, items, cap in sections:
        if items:
            blocks.append((label, None, items, len(items), cap))
    blocks.append(("进度草稿", f"进度草稿: {progress_text}｜下一步: {next_text}", [], 0, None))

    def fit_section(label: str, items: list[str], total: int, remaining: int) -> tuple[str | None, int, int]:
        """按剩余空间渲染区块行：返回 (行文本, 展示条数, 被压缩条数)。"""
        prefix = f"{label}({total}): "
        if remaining <= len(prefix) + MIN_ITEM_CHARS:
            return None, 0, 0
        avail = remaining - len(prefix)
        shown: list[str] = []
        used_chars = 0
        short_clipped = 0
        for item in items:
            piece = item if not shown else "；" + item
            if used_chars + len(piece) <= avail:
                shown.append(item)
                used_chars += len(piece)
                continue
            space = avail - used_chars - (1 if shown else 0)
            if space >= MIN_ITEM_CHARS:
                shown.append(item[: space - 1] + "…")
                short_clipped += 1
            break
        if not shown:
            return None, 0, 0
        return prefix + "；".join(shown), len(shown), short_clipped

    budget = limit - NOTICE_RESERVE
    taken: list[tuple[str, str]] = []
    omitted: list[tuple[str, int]] = []
    used = 0
    for index, (label, fixed_line, items, total, cap) in enumerate(blocks):
        remaining = budget - used
        if fixed_line is not None:
            if len(fixed_line) + 1 > remaining:
                omitted.extend(
                    (rest_label, rest_total or 1)
                    for rest_label, _f, _i, rest_total, _c in blocks[index:]
                )
                break
            taken.append((label, fixed_line))
            used += len(fixed_line) + 1
            continue
        candidate = items if cap is None else items[:cap]
        line, shown_count, short_clipped = fit_section(label, candidate, total, remaining)
        if line is None:
            omitted.extend(
                (rest_label, rest_total or 1)
                for rest_label, _f, _i, rest_total, _c in blocks[index:]
            )
            break
        taken.append((label, line))
        used += len(line) + 1
        clipped_items += short_clipped
        hidden = (total - len(candidate)) + (len(candidate) - shown_count)
        if hidden:
            omitted.append((label, hidden))

    def compose(taken_blocks: list[tuple[str, str]], omitted_pairs: list[tuple[str, int]]) -> tuple[str, bool]:
        lines = [line for _label, line in taken_blocks]
        notes: list[str] = []
        if omitted_pairs:
            detail = "、".join(
                f"{label}{count}项" if count > 1 else f"{label}" for label, count in omitted_pairs[:4]
            )
            if len(omitted_pairs) > 4:
                detail += "等"
            notes.append(f"[摘要截断：{detail} 未展开，详见交付包文件]")
        if clipped_items:
            notes.append(f"[{clipped_items} 项文本超出预览长度已截断]")
        lines.extend(notes)
        truncated = bool(notes)
        body = "\n".join(lines)
        # 页脚长度只依赖字符数的位数，多次迭代收敛后：显示值 == 实际长度。
        chars = len(body) + 1
        text = body
        for _ in range(4):
            text = f"{body}\n— 摘要 {chars}/{limit} 字符｜已截断：{'是' if truncated else '否'}"
            chars = len(text)
        return text, truncated

    text, truncated = compose(taken, omitted)
    while len(text) > limit and len(taken) > 2:
        pop_label, _line = taken.pop()
        omitted.append((pop_label, 1))
        text, truncated = compose(taken, omitted)
    if len(text) > limit:
        # 极端参数下的最后兜底：保留可见截断标记，绝不静默丢内容。
        text = text[: max(limit - 30, 1)] + "…[摘要超出上限已截断]"
        truncated = True

    return {
        "text": text,
        "chars": len(text),
        "limit": limit,
        "truncated": truncated,
        "redactions": redactions,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write(stream: Any, text: str) -> None:
    try:
        stream.write(text)
    except UnicodeEncodeError:
        stream.reconfigure(encoding="utf-8", errors="replace")
        stream.write(text)


def _force_utf8_streams() -> None:
    """CLI 输出固定 UTF-8：中文摘要被管道/文件捕获时不会退化成乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            continue


def _emit_summary(result: dict[str, Any], *, as_json: bool, source: str) -> None:
    source = redact_secrets(source)[0]
    if as_json:
        payload = {
            "schema": SCHEMA_ID,
            "source": source,
            "summary": result["text"],
            "chars": result["chars"],
            "limit": result["limit"],
            "truncated": result["truncated"],
            "redactions": result["redactions"],
        }
        _write(sys.stdout, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return
    _write(sys.stdout, result["text"] + "\n")


def _emit_validation(result: ValidationResult, *, as_json: bool, source: str) -> None:
    source = redact_secrets(source)[0]
    errors = [issue.as_dict() for issue in result.errors]
    warnings = [issue.as_dict() for issue in result.warnings]
    if as_json:
        payload = {
            "schema": SCHEMA_ID,
            "source": source,
            "ok": result.ok,
            "errors": errors,
            "warnings": warnings,
        }
        _write(sys.stdout, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return
    if result.ok:
        line = f"OK 交付包校验通过：{source}"
        data = result.data or {}
        if isinstance(data.get("task_id"), str):
            line += f"（task_id={data['task_id']}，结论={data.get('conclusion')}）"
        _write(sys.stdout, line + "\n")
    else:
        _write(sys.stdout, f"FAIL 交付包校验未通过：{source}（{len(errors)} 个问题）\n")
        for issue in result.errors[:10]:
            _write(sys.stdout, f"- {issue.field}: {issue.message}\n")
        if len(errors) > 10:
            _write(sys.stdout, f"- 其余 {len(errors) - 10} 个问题已省略\n")
    for issue in result.warnings:
        _write(sys.stdout, f"WARN {issue.field}: {issue.message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="talk_workflow.py",
        description="TALK 交付包本地校验与有界摘要（仅标准库；不代表业务验收通过）。",
        epilog="退出码：0 通过 / 1 交付包不合法 / 2 用法或读取错误。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    expect_help = (
        "本次 TALK 任务号（如 38 或 '#38'，两者等价）；与交付包 task_id 规范化后不一致则退出 1，"
        "用于防止旧文件或另一个任务的报告被当成当前交付。省略时不做该核对"
    )

    validate_parser = sub.add_parser("validate", help="校验交付包 JSON 的字段、类型、长度与自报一致性")
    validate_parser.add_argument("report", help="交付包 JSON 路径")
    validate_parser.add_argument("--expect-task-id", metavar="TASK_ID", help=expect_help)
    validate_parser.add_argument("--json", action="store_true", help="输出机器可读结果")

    summary_parser = sub.add_parser("summary", help="输出有界摘要（只含允许字段，超长会显式标注截断）")
    summary_parser.add_argument("report", help="交付包 JSON 路径")
    summary_parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_SUMMARY_LIMIT,
        help=f"摘要总长上限（字符），默认 {DEFAULT_SUMMARY_LIMIT}，夹取区间 [{MIN_SUMMARY_LIMIT}, {MAX_SUMMARY_LIMIT}]",
    )
    summary_parser.add_argument("--expect-task-id", metavar="TASK_ID", help=expect_help)
    summary_parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_streams()
    parser = _build_parser()
    args = parser.parse_args(argv)
    source = args.report

    expect_task_id = getattr(args, "expect_task_id", None)
    if expect_task_id is not None and normalize_task_id(expect_task_id) is None:
        _write(sys.stderr, "ERROR --expect-task-id 不能为空；请传本次 TALK 任务号（如 38 或 '#38'）\n")
        return 2

    try:
        data = load_report(Path(args.report))
        result = validate_report(data, expect_task_id=expect_task_id)
        if args.command == "validate":
            _emit_validation(result, as_json=args.json, source=source)
            return 0 if result.ok else 1

        if not result.ok:
            _emit_validation(result, as_json=args.json, source=source)
            return 1

        summary = build_summary(result.data or {}, max_chars=args.max_chars)
        _emit_summary(summary, as_json=args.json, source=source)
        return 0
    except WorkflowError as exc:
        _write(sys.stderr, f"ERROR {exc}\n")
        return 2
    except RecursionError:
        # 兜底：解析成功但结构遍历仍可能触碰递归上限，一律转短错误而不是 traceback。
        _write(sys.stderr, f"ERROR {DEEP_NESTING_MESSAGE}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
