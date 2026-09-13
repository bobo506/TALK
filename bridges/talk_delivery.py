"""交付摘要与可追溯补读的共享逻辑（只读）。

职责边界：
- 本模块只做纯计算：把**已经取回**的任务记录与结果消息整形为有界摘要，并按稳定引用
  分页读取完整结果原文或指定结构化字段。
- 不发起 HTTP（网络读取留在 ``bridges/talk_task_tools.py``）、不读本机任何文件、
  不改变任务状态，也不自动收取 / accept 结果。

结构化交付复用 ``scripts/talk_workflow.py`` 的 ``talk-delivery-1`` 校验能力，
不另建第二套 schema；业务结论只来自通过该校验的结构化自报，且不代表独立验收证明。
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.talk_workflow import (  # noqa: E402  (需要先修正 sys.path)
    CONCLUSIONS,
    MAX_REPORT_BYTES,
    SCHEMA_ID,
    TOP_LEVEL_FIELDS,
    normalize_task_id,
    redact_secrets,
    validate_report,
)

JsonDict = dict[str, Any]

# 摘要正文（给人读的文本）上限；与整个 JSON 上限是两个独立预算，互不替代。
DELIVERY_SUMMARY_TEXT_LIMIT = 1200
# 整个摘要 JSON 响应上限；保证正常响应有界，而不是只约束正文。
DELIVERY_SUMMARY_JSON_LIMIT = 6000
# detail 分页：单页字符数默认值与上限。
DELIVERY_DETAIL_DEFAULT_PAGE_CHARS = 2000
DELIVERY_DETAIL_MAX_PAGE_CHARS = 4000
# 预览条目数与单条预览长度上限。
DELIVERY_MAX_PREVIEW_ITEMS = 3
DELIVERY_PREVIEW_ITEM_CHARS = 80
# 自由文本结果预览长度上限（旧任务只给带 unknown 的短预览 + 补读入口）。
DELIVERY_TEXT_PREVIEW_CHARS = 300
# 校验问题回显条数上限（避免无效结构化报告把整份 JSON 撑爆）。
DELIVERY_MAX_VALIDATION_ISSUES = 5
# 结构化自报的长度上限复用本地交付包上限（64 KiB）。
DELIVERY_STRUCTURED_MAX_CHARS = MAX_REPORT_BYTES

CONCLUSION_UNKNOWN = "unknown"
CONCLUSION_INVALID = "invalid"

# 摘要文本与 JSON 的边界说明：明确"不承诺无损压到 1200 字符"。
DELIVERY_LIMITS_NOTE = (
    f"summary_text 是给人读的摘要文本，上限 {DELIVERY_SUMMARY_TEXT_LIMIT} 字符；"
    f"整个 JSON 响应另有 {DELIVERY_SUMMARY_JSON_LIMIT} 字符上限。两者是两个独立预算，"
    "不承诺把整份交付报告无损压进 1200 字符；完整内容必须用 detail 模式分页补读。"
)
DELIVERY_TRUST_NOTE = (
    "业务结论只来自结果消息中通过本地 talk-delivery-1 校验的结构化自报，"
    "且该自报自身声明的 task_id 必须与实际任务号（task_ref.id）规范化后一致；"
    "错号或缺失一律判 invalid 且 trusted_source=false。"
    "它仍然属于执行者自报，不是独立验收证明；runner 状态 succeeded 不能推断为 complete。"
)
DELIVERY_STITCH_NOTE = (
    "detail 分页按 result_message_id + offset 顺序拼接可无损重建完整结果；"
    "引用变化时返回 stale_reference 并要求从 offset=0 重新开始，禁止把两份结果拼在一起。"
)

# 摘要里允许出现的任务字段：只有引用与状态，绝不含任务正文 / Hall 历史 / 实例历史。
DELIVERY_TASK_REF_FIELDS = (
    "id",
    "title",
    "project_id",
    "task_kind",
    "target_member_id",
    "created_by",
    "hall_group_id",
    "updated_at",
    "finished_at",
)
# preview 区块顺序即优先级：阻塞 → 未完成 → 已完成。
DELIVERY_PREVIEW_SECTIONS = ("blocked", "unfinished", "completed")


class DeliveryParamError(ValueError):
    """调用参数不合法（mode / offset / limit / fields / 稳定引用）。"""


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _redact(text: str) -> str:
    return redact_secrets(text)[0]


# ---------------------------------------------------------------------------
# 结构化自报识别（复用 talk-delivery-1 校验）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliveryReport:
    """结果消息正文的分类结果。

    kind 取值：
    - ``empty``：结果消息没有文本正文；
    - ``unstructured``：不是 JSON 对象（自由文本旧报告）；
    - ``too_large``：超过结构化交付包长度上限，不按结构化报告解析；
    - ``invalid``：能解析成 JSON 对象，但未通过 talk-delivery-1 校验，
      或自报 task_id 与实际任务号不一致 / 无法比对；
    - ``valid``：通过 talk-delivery-1 校验且 task_id 与实际任务号一致，业务结论可用。

    ``declared_task_id`` 始终记录自报里规范化后的 task_id（能取到时），
    便于错号时如实回显"自报了什么"，而不是只给一个 invalid。
    """

    kind: str
    report: JsonDict | None = None
    issues: tuple[JsonDict, ...] = ()
    detail: str = ""
    declared_task_id: str | None = None


def normalize_delivery_task_id(value: Any) -> str | None:
    """把任务号规范成可比对文本，沿用原 CLI 的 `38` / `#38` 等价规则。

    ``task.id`` 是整数、结构化自报的 ``task_id`` 是字符串，两者都先归一化再比对。
    返回 None 表示"不可比对"（缺失、布尔、非字符串非整数、规范化后为空），
    调用方必须把"不可比对"当作不可信，**不得**退化成跳过核对。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    return normalize_task_id(value)


def task_id_issue(expected: str | None, declared: str | None) -> JsonDict:
    """与 ``talk_workflow.Issue.as_dict()`` 同形，保证 validation_issues 结构一致。"""
    expected_label = expected if expected is not None else "未知"
    if declared is None:
        message = (
            f"结构化自报缺少可用的 task_id，无法确认是本次任务（本次任务号 {expected_label}）"
        )
    else:
        message = (
            f"结构化自报 task_id={declared} 不是本次任务号 {expected_label}；"
            "可能是旧结果或另一个任务的报告"
        )
    return {"field": "task_id", "code": "unexpected_task_id", "message": message}


def task_id_check(declared: Any, expect_task_id: Any) -> JsonDict:
    """自报任务号与实际任务号的核对结果：matches=None 表示不可比对（同样不可信）。"""
    expected = normalize_delivery_task_id(expect_task_id)
    declared_norm = normalize_delivery_task_id(declared)
    matches: bool | None = None
    if expected is not None and declared_norm is not None:
        matches = expected == declared_norm
    return {"expected": expected, "declared": declared_norm, "matches": matches}


def _strip_code_fence(text: str) -> str:
    """整段被 ``` 围栏包住时剥掉围栏；只处理"整个正文是一个围栏块"这一种形态。"""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return stripped
    return "\n".join(lines[1:-1]).strip()


def parse_delivery_report(content: Any, *, expect_task_id: Any) -> DeliveryReport:
    """把结果消息正文分类成 empty / unstructured / too_large / invalid / valid。

    ``expect_task_id`` 是**实际任务号**（调用方必须显式传入，通常取任务记录的 ``id``）：
    结构化自报只有先通过 ``talk-delivery-1`` 校验、**并且**自身 ``task_id`` 规范化后
    与实际任务号一致，才可能是 valid；错号、缺号或无法比对一律 invalid，
    绝不因为"格式合法"就给出可信业务结论。
    """
    if not isinstance(content, str) or not content.strip():
        return DeliveryReport(kind="empty", detail="结果消息没有文本正文")
    if len(content) > DELIVERY_STRUCTURED_MAX_CHARS:
        return DeliveryReport(
            kind="too_large",
            detail=(
                f"正文 {len(content)} 字符，超过结构化交付包上限 "
                f"{DELIVERY_STRUCTURED_MAX_CHARS} 字符，不按结构化自报解析"
            ),
        )
    candidate = _strip_code_fence(content)
    if not candidate.startswith(("{", "[")):
        return DeliveryReport(kind="unstructured", detail="正文不是 JSON 对象，按自由文本处理")
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return DeliveryReport(kind="unstructured", detail="正文不是合法 JSON，按自由文本处理")
    except RecursionError:
        return DeliveryReport(kind="invalid", detail="JSON 嵌套层级过深，无法按结构化自报解析")
    if not isinstance(data, dict):
        return DeliveryReport(kind="invalid", detail="JSON 顶层不是对象，不构成交付包")

    declared = normalize_delivery_task_id(data.get("task_id"))
    expected = normalize_delivery_task_id(expect_task_id)
    if expected is None:
        # 没有可用的实际任务号就无法确认归属：宁可判不可信，也不放行"未核对"的自报。
        return DeliveryReport(
            kind="invalid",
            issues=(task_id_issue(None, declared),),
            detail=(
                "无法确认结果消息属于本任务：调用方未提供可用的实际任务号，"
                "不按可信结构化自报处理"
            ),
            declared_task_id=declared,
        )

    result = validate_report(data, expect_task_id=expected)
    if result.ok:
        return DeliveryReport(kind="valid", report=data, declared_task_id=declared)
    issues = tuple(issue.as_dict() for issue in result.errors[:DELIVERY_MAX_VALIDATION_ISSUES])
    detail = (
        f"结构化报告未通过 {SCHEMA_ID} 校验（{len(result.errors)} 个问题，"
        f"最多回显 {DELIVERY_MAX_VALIDATION_ISSUES} 个）"
    )
    if declared != expected:
        detail = (
            f"结构化报告自身 task_id（{declared if declared is not None else '缺失'}）"
            f"与实际任务号 {expected} 不一致，判为不可信；{detail}"
        )
    return DeliveryReport(
        kind="invalid",
        issues=issues,
        detail=detail,
        declared_task_id=declared,
    )


def conclusion_for(
    message: JsonDict | None,
    report: DeliveryReport | None = None,
    *,
    expect_task_id: Any,
) -> JsonDict:
    """业务结论：只认"通过校验且 task_id 与实际任务号一致"的结构化自报。

    ``expect_task_id`` 是实际任务号（通常取任务记录的 ``id``），必须显式传入。
    这里会对传入的 ``report`` 再做一次 task_id 复核：即使某个调用方拿的是未核对过的
    解析结果，也不会得到 ``trusted_source=true``。
    """
    parsed = (
        report
        if report is not None
        else parse_delivery_report(
            (message or {}).get("content"), expect_task_id=expect_task_id
        )
    )
    check = task_id_check(parsed.declared_task_id, expect_task_id)
    if parsed.kind == "valid" and isinstance(parsed.report, dict):
        if check["matches"] is not True:
            return {
                "value": CONCLUSION_INVALID,
                "trusted_source": False,
                "source": "invalid_structured_report",
                "source_label": "结构化报告无效",
                "schema": None,
                "reason": (
                    "结构化自报的 task_id 与实际任务号不一致或无法比对，"
                    "判为不可信（不代表本任务完成）"
                ),
                "validation_issues": [task_id_issue(check["expected"], check["declared"])],
                "task_id_check": check,
            }
        value = str(parsed.report.get("conclusion"))
        return {
            "value": value if value in CONCLUSIONS else CONCLUSION_UNKNOWN,
            "trusted_source": True,
            "source": "structured_self_report",
            "source_label": f"{SCHEMA_ID} 结构化自报（已通过本地校验且任务号一致）",
            "schema": SCHEMA_ID,
            "reason": "结果消息提供了通过本地交付 schema 校验、且自带本次任务号的结构化自报",
            "validation_issues": [],
            "task_id_check": check,
        }
    if parsed.kind == "invalid":
        return {
            "value": CONCLUSION_INVALID,
            "trusted_source": False,
            "source": "invalid_structured_report",
            "source_label": "结构化报告无效",
            "schema": None,
            "reason": parsed.detail or "结构化报告未通过本地交付 schema 校验",
            "validation_issues": list(parsed.issues),
            "task_id_check": check,
        }
    if parsed.kind == "too_large":
        return {
            "value": CONCLUSION_UNKNOWN,
            "trusted_source": False,
            "source": "oversized_result",
            "source_label": "结果过大，未按结构化自报解析",
            "schema": None,
            "reason": parsed.detail,
            "validation_issues": [],
            "task_id_check": check,
        }
    if parsed.kind == "unstructured":
        return {
            "value": CONCLUSION_UNKNOWN,
            "trusted_source": False,
            "source": "unstructured_text",
            "source_label": "自由文本（无可信结构化自报）",
            "schema": None,
            "reason": "结果消息是自由文本，没有 talk-delivery-1 结构化自报，不做结论推断",
            "validation_issues": [],
            "task_id_check": check,
        }
    return {
        "value": CONCLUSION_UNKNOWN,
        "trusted_source": False,
        "source": "none",
        "source_label": "无可读结果正文",
        "schema": None,
        "reason": parsed.detail or "结果消息没有文本正文",
        "validation_issues": [],
        "task_id_check": check,
    }


# ---------------------------------------------------------------------------
# 有界摘要
# ---------------------------------------------------------------------------


def task_reference(task: JsonDict) -> JsonDict:
    """摘要里允许出现的任务引用字段：只有引用与状态，绝不含任务正文 / Hall 历史。"""
    return {field: task.get(field) for field in DELIVERY_TASK_REF_FIELDS}


def _preview_item(value: str, limit: int = DELIVERY_PREVIEW_ITEM_CHARS) -> str:
    text = _redact(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _preview_values(values: Any, cap: int) -> tuple[list[str], int]:
    if not isinstance(values, list):
        return [], 0
    items = [_preview_item(value) for value in values if isinstance(value, str) and value.strip()]
    return items[:cap], len(items)


def _dump(payload: JsonDict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def build_delivery_summary(
    task: JsonDict,
    message: JsonDict | None,
    *,
    text_limit: int = DELIVERY_SUMMARY_TEXT_LIMIT,
    json_limit: int = DELIVERY_SUMMARY_JSON_LIMIT,
) -> JsonDict:
    """生成有界摘要：区分 runner / workflow / 业务结论，所有省略都显式标记。

    实际任务号只从 ``task`` 记录自身取（``task["id"]``），调用方无法省略这一核对：
    结构化自报的 task_id 与它不一致时一律 invalid / 不可信。
    """
    expect_task_id = task.get("id")
    report = parse_delivery_report(
        (message or {}).get("content"), expect_task_id=expect_task_id
    )
    conclusion = conclusion_for(message, report, expect_task_id=expect_task_id)
    source = report.report if report.kind == "valid" else {}
    counts = {
        "completed": len(source.get("completed") or []),
        "unfinished": len(source.get("unfinished") or []),
        "blocked": len(source.get("blocked") or []),
        "changed_files": len(source.get("changed_files") or []),
        "limitations": len(source.get("limitations") or []),
        "verification": len(source.get("verification") or []),
    }
    raw_preview: dict[str, tuple[list[str], int]] = {
        section: _preview_values(source.get(section), DELIVERY_MAX_PREVIEW_ITEMS)
        for section in DELIVERY_PREVIEW_SECTIONS
    }

    result_message_id = task.get("result_message_id")
    task_ref = task_reference(task)
    runner_status = {
        "status": task.get("status"),
        "workflow_status": task.get("workflow_status"),
        "result_message_id": result_message_id,
        "result_collected_at": task.get("result_collected_at"),
        "note": "runner_status / workflow_status 只表示流程位置；runner 结束不等于用户目标完成",
    }

    preview: JsonDict = {}
    for section in DELIVERY_PREVIEW_SECTIONS:
        items, total = raw_preview[section]
        preview[section] = {
            "items": list(items),
            "total": total,
            "shown": len(items),
            "omitted": total - len(items),
            "note": (
                f"{section} 共 {total} 条，本摘要展示 {len(items)} 条；"
                "被省略条目必须用 read_more 指向的 detail 模式补读"
                if total > len(items)
                else ""
            ),
        }

    payload: JsonDict = {
        "mode": "summary",
        "task_ref": task_ref,
        "runner_status": runner_status,
        "delivery_conclusion": conclusion,
        "counts": counts,
        "preview": preview,
        "summary_text": "",
        "limits": {},
        "read_more": {},
        "notes": [DELIVERY_TRUST_NOTE, DELIVERY_STITCH_NOTE],
    }
    if report.kind != "valid":
        content = (message or {}).get("content")
        # 只对预览窗口内的文本做脱敏：结果正文可能极大，摘要侧不做整篇扫描。
        window = (
            content[: DELIVERY_TEXT_PREVIEW_CHARS + 200] if isinstance(content, str) else ""
        )
        preview_text = _redact(window)[:DELIVERY_TEXT_PREVIEW_CHARS]
        payload["result_preview"] = {
            "kind": report.kind,
            "chars": len(content) if isinstance(content, str) else 0,
            "text": preview_text,
            "truncated": isinstance(content, str) and len(content) > len(preview_text),
            "trusted": False,
            "note": "此处只是结果正文的截断预览，不可作为业务结论来源",
        }

    def render_read_more() -> JsonDict:
        omitted = [
            {"field": section, "omitted_items": preview[section]["omitted"]}
            for section in DELIVERY_PREVIEW_SECTIONS
            if preview[section]["omitted"]
        ]
        if result_message_id is None:
            params_hint = {"task_id": task_ref.get("id"), "mode": "detail"}
            hint = "该任务当前没有结果消息引用，detail 模式不可用；需要 Hall 上下文请用既有 talk_get_task。"
        else:
            params_hint = {
                "task_id": task_ref.get("id"),
                "mode": "detail",
                "result_message_id": result_message_id,
                "offset": 0,
                "limit": DELIVERY_DETAIL_DEFAULT_PAGE_CHARS,
            }
            hint = (
                "用 read_more.params 调用 talk_get_delivery 的 detail 模式，"
                "按 offset 顺序翻页可无损重建完整结果；也可用 fields 参数单独补读结构化字段。"
            )
        return {
            "tool": "talk_get_delivery",
            "mode": "detail",
            "params": params_hint,
            "fields_param": {
                "name": "fields",
                "allowed": list(TOP_LEVEL_FIELDS),
                "note": "仅当结果是通过校验的 talk-delivery-1 结构化自报时可用",
            },
            "omitted": omitted,
            "hint": hint,
        }

    def render_text() -> str:
        """渲染摘要文本：预算内按优先级排布，放不下的区块一律留下显式标记。"""
        head = [
            f"交付摘要 task={task_ref.get('id')} "
            f"runner={runner_status['status']}/{runner_status['workflow_status']}",
            f"业务结论={conclusion['value']}（来源：{conclusion['source_label']}；非独立验收证明）",
            f"阻塞={counts['blocked']} 未完成={counts['unfinished']} 已完成={counts['completed']}",
        ]
        labels = {"blocked": "阻塞", "unfinished": "未完成", "completed": "已完成"}
        detail_lines: list[tuple[str, str]] = []
        omitted_notes: list[str] = []
        for section in DELIVERY_PREVIEW_SECTIONS:
            label = labels[section]
            entry = preview[section]
            if entry["omitted"]:
                omitted_notes.append(f"{label}{entry['omitted']}项")
            if not entry["items"]:
                continue
            shown = "；".join(entry["items"])
            if entry["omitted"]:
                shown += f"…（另 {entry['omitted']} 项未展开）"
            detail_lines.append((label, f"{label}({entry['total']}): {shown}"))
        caution = (
            f"[注意] {conclusion['reason']}"
            if conclusion["value"] != "complete"
            else None
        )

        def compose(dropped: list[str]) -> str:
            notes = list(omitted_notes) + list(dropped)
            tail = [caution] if caution else []
            if notes:
                tail.append(
                    "[摘要截断：" + "、".join(notes[:4]) + " 未展开，"
                    "请用 talk_get_delivery mode=detail 补读，勿据本摘要认定目标已完成]"
                )
            return "\n".join(head + [line for _label, line in detail_lines] + tail)

        dropped: list[str] = []
        text = compose(dropped)
        while len(text) > text_limit and detail_lines:
            label, _line = detail_lines.pop()
            dropped.append(f"{label}明细")
            text = compose(dropped)
        if len(text) > text_limit:
            # 极端参数下的最后兜底：仍然保留可见的截断标记，绝不静默丢内容。
            marker = "\n[摘要文本超限，请用 detail 补读]"
            text = text[: max(text_limit - len(marker), 1)] + marker
        return text

    shrink_stage = 0
    while True:
        payload["read_more"] = render_read_more()
        payload["summary_text"] = render_text()
        json_chars = len(_dump(payload))
        payload["limits"] = {
            "text_limit_chars": text_limit,
            "text_chars": len(payload["summary_text"]),
            "text_truncated": bool(payload["read_more"]["omitted"]),
            "json_limit_chars": json_limit,
            "json_chars": json_chars,
            "json_truncated": False,
            "note": DELIVERY_LIMITS_NOTE,
        }
        if len(_dump(payload)) <= json_limit:
            break
        # 分阶段收缩，先牺牲冗余说明，最后才牺牲"阻塞"预览；被牺牲的条目一律留计数与补读指引。
        if shrink_stage == 0:
            shrunk = False
            for section in ("completed", "unfinished", "blocked"):
                entry = preview[section]
                if entry["items"]:
                    entry["items"].pop()
                    entry["omitted"] += 1
                    entry["shown"] -= 1
                    entry["note"] = (
                        f"{section} 共 {entry['total']} 条，本摘要展示 {entry['shown']} 条；"
                        "被省略条目必须用 read_more 指向的 detail 模式补读"
                    )
                    shrunk = True
                    break
            if shrunk:
                continue
            shrink_stage = 1
            continue
        if shrink_stage == 1:
            payload["read_more"].pop("fields_param", None)
            payload["notes"] = [DELIVERY_TRUST_NOTE]
            shrink_stage = 2
            continue
        if shrink_stage == 2 and payload.get("result_preview"):
            payload["result_preview"] = None
            shrink_stage = 3
            continue
        break
    if len(_dump(payload)) > json_limit:
        # 下限兜底：即使极端参数也给出可辨认的最小摘要（保留计数与预览结构），并如实报告是否仍超限。
        payload = {
            "mode": "summary",
            "task_ref": {"id": task_ref.get("id")},
            "runner_status": {
                "status": runner_status["status"],
                "workflow_status": runner_status["workflow_status"],
                "result_message_id": result_message_id,
            },
            "delivery_conclusion": {
                "value": conclusion["value"],
                "trusted_source": conclusion["trusted_source"],
                "source": conclusion["source"],
            },
            "counts": counts,
            "preview": preview,
            "summary_text": (
                f"交付摘要 task={task_ref.get('id')} 结论={conclusion['value']} "
                f"阻塞={counts['blocked']} 未完成={counts['unfinished']}"
            ),
            "limits": {
                "text_limit_chars": text_limit,
                "text_chars": 0,
                "json_limit_chars": json_limit,
                "note": DELIVERY_LIMITS_NOTE,
            },
            "read_more": {
                "tool": "talk_get_delivery",
                "mode": "detail",
                "params": {"task_id": task_ref.get("id"), "mode": "detail"},
                "omitted": [
                    {"field": section, "omitted_items": preview[section]["omitted"]}
                    for section in DELIVERY_PREVIEW_SECTIONS
                    if preview[section]["omitted"]
                ],
                "hint": "摘要 JSON 已达上限并收缩，请用 detail 模式补读完整结果，勿据本摘要认定目标已完成。",
            },
            "minimal": True,
            "notes": [DELIVERY_TRUST_NOTE],
        }
    payload["limits"]["text_chars"] = len(payload["summary_text"])
    payload["limits"]["json_chars"] = len(_dump(payload))
    payload["limits"]["json_truncated"] = bool(payload["limits"]["json_chars"] > json_limit)
    return payload


# ---------------------------------------------------------------------------
# 分页补读
# ---------------------------------------------------------------------------


def normalize_detail_params(
    *, offset: Any = 0, limit: Any = None, fields: Any = None
) -> tuple[int, int, list[str] | None]:
    """校验 detail 参数；非法游标直接报错，不做静默纠正。"""
    if offset is None:
        offset = 0
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise DeliveryParamError(f"offset 必须是整数，收到 {offset!r}")
    if offset < 0:
        raise DeliveryParamError(f"offset 不能为负数，收到 {offset}")
    if limit is None:
        page_limit = DELIVERY_DETAIL_DEFAULT_PAGE_CHARS
    else:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise DeliveryParamError(f"limit 必须是整数，收到 {limit!r}")
        if limit < 1 or limit > DELIVERY_DETAIL_MAX_PAGE_CHARS:
            raise DeliveryParamError(
                f"limit 必须在 1..{DELIVERY_DETAIL_MAX_PAGE_CHARS} 之间，收到 {limit}"
            )
        page_limit = limit
    if fields is None:
        return offset, page_limit, None
    if isinstance(fields, (str, bytes)) or not isinstance(fields, (list, tuple)):
        raise DeliveryParamError("fields 必须是字符串数组")
    selected: list[str] = []
    for raw in fields:
        if not isinstance(raw, str) or raw not in TOP_LEVEL_FIELDS:
            raise DeliveryParamError(
                f"fields 只支持交付包顶层字段：{'/'.join(TOP_LEVEL_FIELDS)}"
            )
        if raw not in selected:
            selected.append(raw)
    if not selected:
        raise DeliveryParamError("fields 不能为空数组；省略该参数表示补读完整结果原文")
    return offset, page_limit, selected


def page_document(document: str, *, offset: int, limit: int) -> JsonDict:
    """按 offset 切一页；offset 超出长度视为非法游标，不返回误导性内容。"""
    total = len(document)
    if offset > total:
        raise DeliveryParamError(f"offset {offset} 超出结果长度 {total}；非法游标")
    page = document[offset : offset + limit]
    next_offset = offset + len(page)
    done = next_offset >= total
    return {
        "offset": offset,
        "limit": limit,
        "page_chars": len(page),
        "total_chars": total,
        "next_offset": None if done else next_offset,
        "done": done,
        "text": page,
    }


def build_stale_payload(
    *,
    mode: str,
    task_id: Any,
    reason: str,
    requested_result_message_id: Any,
    current_result_message_id: Any,
    current_content_sha256: str | None,
    page_limit: int,
) -> JsonDict:
    """引用变化：拒绝按旧引用继续，明确要求重置，绝不拼接两份结果。"""
    return {
        "mode": mode,
        "status": "stale_reference",
        "reason": reason,
        "task_id": task_id,
        "requested_result_message_id": requested_result_message_id,
        "current_result_message_id": current_result_message_id,
        "current_content_sha256": current_content_sha256,
        "reset_required": True,
        "next_params": {
            "task_id": task_id,
            "mode": mode,
            "result_message_id": current_result_message_id,
            "offset": 0,
            "limit": page_limit,
        },
        "note": (
            "结果引用已变化：本次不返回任何正文，必须按 next_params 从 offset=0 重新开始；"
            "禁止把两份结果的分页拼在一起。"
        ),
    }


def build_unavailable_payload(*, mode: str, task_id: Any, reason: str, message: str) -> JsonDict:
    """数据条件不满足：返回结构化的 unavailable，而不是伪装成空结果。"""
    return {
        "mode": mode,
        "status": "unavailable",
        "reason": reason,
        "task_id": task_id,
        "message": message,
        "reset_required": False,
        "note": "本工具只读，不会自动收取 / accept 结果，也不会改变任务状态。",
    }
