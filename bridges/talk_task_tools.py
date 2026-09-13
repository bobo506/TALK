"""Shared HTTP-backed Task Hall tools for Codex MCP and pi extensions."""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from bridges import talk_delivery
from bridges.talk_delivery import (
    DELIVERY_DETAIL_DEFAULT_PAGE_CHARS,
    DELIVERY_DETAIL_MAX_PAGE_CHARS,
    DELIVERY_SUMMARY_JSON_LIMIT,
    DELIVERY_SUMMARY_TEXT_LIMIT,
    TOP_LEVEL_FIELDS,
    DeliveryParamError,
)

JsonDict = dict[str, Any]
# 提前返回的协作状态：成果提交 / 完成 / 失败 / 需澄清（含澄清已答复、需决策、取消）。
# 这些状态一旦出现即可结束等待，不需要等满整个超时窗口。
DEFAULT_WAIT_WORKFLOW_STATUSES = [
    "clarification_requested",
    "clarification_answered",
    "needs_decision",
    "submitted",
    "completed",
    "failed",
    "canceled",
]
WAIT_MAX_TIMEOUT_SECONDS = 600.0
WAIT_DEFAULT_TIMEOUT_SECONDS = 600.0
# 客户端单工具超时必须比最长等待更长，留出网络与序列化余量；低于该值会让 600 秒等待
# 被客户端提前取消或超时。
WAIT_RECOMMENDED_CLIENT_TIMEOUT_SECONDS = 660.0
# 程序轮询节奏：先密后疏，长等待的 HTTP 次数保持有界（600 秒约 120 余次）。
WAIT_INITIAL_POLL_INTERVAL_SECONDS = 0.5
WAIT_MAX_POLL_INTERVAL_SECONDS = 5.0
# 等待结果只回传任务与成果引用所需的短字段，不回传任务正文、消息历史或实例历史。
_WAIT_TASK_REFERENCE_FIELDS = (
    "id",
    "title",
    "project_id",
    "task_kind",
    "status",
    "workflow_status",
    "created_by",
    "target_member_id",
    "hall_group_id",
    "result_message_id",
    "updated_at",
)
# tasks 引用的数量上限：项目级等待会轮询到项目内全部可见任务，输出必须保持有界；
# 超出上限的条目以计数 + ID 标记，不静默丢弃结果引用。
WAIT_MAX_TASK_REFERENCES = 20
WAIT_TASKS_NOTE = (
    "tasks 只含引用字段：提前返回时是命中集合，超时返回时是本轮轮询到的任务，两者最多 "
    f"{WAIT_MAX_TASK_REFERENCES} 条；超出上限的条目以 tasks_truncated / tasks_omitted_count / "
    "omitted_task_ids 明确标记，不静默漏报；matched_task_ids 始终给出完整命中集合，"
    "任务 ID 引用不因截断丢失。"
)
WAIT_COUNTING_NOTE = (
    "query_stats 只含本工具内部实测的程序级计数（poll_rounds / http_requests / elapsed_seconds / "
    "return_reason）；模型侧的 talk_get_task/talk_list_tasks 调用数与客户端外层等待回合不由本工具"
    "统计，本工具也无法观测，需由主控在外部实测。"
)
# 取消/断线边界（工具描述与 --check 共用，避免被读成"取消会立即终止服务端等待"）。
WAIT_CANCELLATION_NOTE = (
    "talk_wait_tasks 是同步阻塞轮询：程序内部不调用模型，但本工具无法保证宿主外层零回合；"
    "客户端取消（notifications/cancelled）不会立即终止程序侧等待，等待仍会跑到命中或超时截止；"
    "Windows 下客户端进程退出不保证带走 MCP 子进程；等待全程只读，不改变任务状态。"
)
# 实例摘要只保留短字段（id / runtime / status / current_task_id / last_seen_at / pid），
# 不含 last_error 与历史实例；availability 仍需消费者结合 last_seen_at 判断心跳新鲜度。
AVAILABILITY_NOTE = (
    "availability 仅依据 agent_instances 上报状态，未做心跳核验，"
    "可能滞后于真实在线状态，使用前请按 last_seen_at 判断新鲜度。"
)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class TalkToolError(RuntimeError):
    """A user-facing TALK tool failure."""


def _config() -> tuple[str, str]:
    base_url = os.environ.get("TALK_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    api_key = os.environ.get("TALK_API_KEY", "").strip()
    if not api_key:
        raise TalkToolError("TALK_API_KEY 未设置")
    return base_url, api_key


def _api_request(
    method: str,
    path: str,
    *,
    json_body: JsonDict | None = None,
    params: JsonDict | None = None,
    stats: JsonDict | None = None,
) -> Any:
    base_url, api_key = _config()
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
    url = f"{base_url}{path}" + (f"?{query}" if query else "")
    data = None if json_body is None else json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(url, data=data, headers=headers, method=method.upper())
    if stats is not None:
        stats["http_requests"] = int(stats.get("http_requests", 0)) + 1

    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read()
    except HTTPError as exc:
        payload = exc.read()
        detail: Any = payload.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            detail = parsed.get("detail", parsed)
        except json.JSONDecodeError:
            pass
        raise TalkToolError(f"TALK API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise TalkToolError(f"无法连接 TALK API: {exc.reason}") from exc

    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TalkToolError("TALK API 返回了无效 JSON") from exc


def _project_id(value: Any = None, *, required: bool = False) -> str | None:
    project_id = str(value or os.environ.get("TALK_PROJECT_ID") or "").strip() or None
    if required and project_id is None:
        raise TalkToolError("缺少 project_id，且当前 bridge 未设置 TALK_PROJECT_ID")
    return project_id


def _member_id() -> str:
    member_id = os.environ.get("TALK_MEMBER_ID", "").strip()
    if member_id:
        return member_id
    current = _api_request("GET", "/api/members/me")
    return str(current["id"])


def _availability(statuses: list[str]) -> str:
    if "busy" in statuses:
        return "busy"
    if any(status in {"online", "idle", "starting"} for status in statuses):
        return "available"
    if "error" in statuses:
        return "error"
    return "offline"


def _timestamp_key(value: Any) -> datetime:
    """把实例时间戳归一化成可比较的 aware datetime；无法解析时按最早时间处理。"""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return _EPOCH
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return _EPOCH


def _summary_timestamp(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def latest_instance_summary(instances: list[JsonDict]) -> list[JsonDict]:
    """按 last_seen_at 只保留最新一个实例摘要，避免历史实例与错误日志进入模型上下文。"""
    latest: JsonDict | None = None
    latest_key = _EPOCH
    for instance in instances:
        key = _timestamp_key(instance.get("last_seen_at"))
        if latest is None or key >= latest_key:
            latest = instance
            latest_key = key
    if latest is None:
        return []
    return [
        {
            "id": str(latest.get("id") or ""),
            "runtime": latest.get("runtime"),
            "status": str(latest.get("status") or "offline"),
            "current_task_id": latest.get("current_task_id"),
            "last_seen_at": _summary_timestamp(latest.get("last_seen_at")),
            "pid": latest.get("pid"),
        }
    ]


def list_agents(*, project_id: str | None = None) -> JsonDict:
    effective_project_id = _project_id(project_id)
    if effective_project_id is not None:
        project_agents = _api_request(
            "GET",
            f"/api/projects/{quote(effective_project_id, safe='')}/agents",
        )
        active_agent_ids = {
            str(member["id"])
            for member in _api_request("GET", "/api/members")
            if member.get("kind") == "agent" and member.get("disabled_at") is None
        }
        agents: list[JsonDict] = []
        for agent in project_agents:
            if str(agent["member_id"]) not in active_agent_ids:
                continue
            member_instances = list(agent.get("instances") or [])
            statuses = [
                str(instance.get("status") or "offline")
                for instance in member_instances
            ]
            agents.append(
                {
                    "member_id": str(agent["member_id"]),
                    "display_name": agent.get("display_name"),
                    "business_role": agent.get("business_role"),
                    "decision_tier": agent.get("decision_tier"),
                    "capability_summary": list(
                        agent.get("capability_summary") or []
                    ),
                    "availability": agent.get("availability")
                    or _availability(statuses),
                    "instances": latest_instance_summary(member_instances),
                }
            )
        return {
            "project_id": effective_project_id,
            "availability_note": AVAILABILITY_NOTE,
            "agents": agents,
        }

    members = _api_request("GET", "/api/members")
    instances = _api_request("GET", "/api/instances")

    instances_by_member: dict[str, list[JsonDict]] = {}
    for instance in instances:
        instances_by_member.setdefault(str(instance["member_id"]), []).append(instance)

    agents: list[JsonDict] = []
    for member in members:
        member_id = str(member["id"])
        if member.get("kind") != "agent" or member.get("disabled_at") is not None:
            continue
        member_instances = instances_by_member.get(member_id, [])
        statuses = [str(instance.get("status") or "offline") for instance in member_instances]
        agents.append(
            {
                "member_id": member_id,
                "display_name": member.get("display_name"),
                "availability": _availability(statuses),
                "instances": latest_instance_summary(member_instances),
            }
        )
    return {
        "project_id": effective_project_id,
        "availability_note": AVAILABILITY_NOTE,
        "agents": agents,
    }


def delegate_task(
    *,
    target_member_id: str,
    content: str,
    title: str | None = None,
    project_id: str | None = None,
    task_kind: str = "general",
    review_policy: str | None = None,
    related_task_ids: list[int] | None = None,
    trigger_task_id: int | None = None,
    parent_task_id: int | None = None,
    authorization_epoch: int | None = None,
    max_clarification_rounds: int = 1,
) -> JsonDict:
    effective_project_id = _project_id(project_id, required=True)
    return _api_request(
        "POST",
        "/api/tasks",
        json_body={
            "target_member_id": target_member_id,
            "content": content,
            "title": title,
            "project_id": effective_project_id,
            "task_kind": task_kind,
            "review_policy": review_policy,
            "related_task_ids": list(related_task_ids or []),
            "trigger_task_id": trigger_task_id,
            "parent_task_id": parent_task_id,
            "authorization_epoch": authorization_epoch,
            "max_clarification_rounds": max_clarification_rounds,
        },
    )


def list_tasks(
    *,
    target_member_id: str | None = None,
    status: str | None = None,
    workflow_status: str | None = None,
    project_id: str | None = None,
    task_kind: str | None = None,
    stats: JsonDict | None = None,
) -> JsonDict:
    effective_project_id = _project_id(project_id)
    tasks = _api_request(
        "GET",
        "/api/tasks",
        params={
            "target_member_id": target_member_id,
            "status": status,
            "workflow_status": workflow_status,
            "project_id": effective_project_id,
            "task_kind": task_kind,
        },
        stats=stats,
    )
    return {"project_id": effective_project_id, "tasks": tasks}


def get_task(task_id: int, *, include_messages: bool = True) -> JsonDict:
    task = _api_request("GET", f"/api/tasks/{int(task_id)}")
    relations = _api_request("GET", f"/api/tasks/{int(task_id)}/relations")
    result: JsonDict = {"task": task, "relations": relations}
    if include_messages:
        params: JsonDict = {"limit": 50}
        if task.get("hall_group_id"):
            params["group_id"] = task["hall_group_id"]
        messages = _api_request("GET", "/api/messages", params=params)
        result["messages"] = messages
        result_message_id = task.get("result_message_id")
        result["result_message"] = next(
            (message for message in messages if message.get("id") == result_message_id),
            None,
        )
    return result


def reply_task(
    *,
    task_id: int,
    body: str,
    workflow_action: str = "none",
    allow_additional_round: bool = False,
) -> JsonDict:
    normalized_action = workflow_action.strip().lower()
    allowed_actions = {
        "none",
        "request_clarification",
        "submit_clarification_answer",
        "resolve_clarification",
        "accept",
    }
    if normalized_action not in allowed_actions:
        raise TalkToolError(
            "workflow_action 必须是 none、request_clarification、"
            "submit_clarification_answer、resolve_clarification 或 accept"
        )
    task = _api_request("GET", f"/api/tasks/{int(task_id)}")
    current_member_id = _member_id()
    if current_member_id == task.get("created_by"):
        target = str(task["target_member_id"])
    elif current_member_id == task.get("target_member_id"):
        target = str(task["created_by"])
    else:
        raise TalkToolError("当前成员不是该 Task Hall 的请求者或执行者")

    message_body: JsonDict = {"type": "text", "content": body, "to": [target]}
    if task.get("hall_group_id"):
        message_body["group_id"] = task["hall_group_id"]
    message = _api_request("POST", "/api/messages", json_body=message_body)

    if normalized_action == "request_clarification":
        task = _api_request(
            "POST",
            f"/api/tasks/{int(task_id)}/request-clarification",
            json_body={"question_message_id": message["id"]},
        )
    elif normalized_action == "submit_clarification_answer":
        task = _api_request(
            "POST",
            f"/api/tasks/{int(task_id)}/submit-clarification-answer",
            json_body={"answer_message_id": message["id"]},
        )
    elif normalized_action == "resolve_clarification":
        task = _api_request(
            "POST",
            f"/api/tasks/{int(task_id)}/resolve-clarification",
            json_body={"allow_additional_round": bool(allow_additional_round)},
        )
    elif normalized_action == "accept":
        task = _api_request("POST", f"/api/tasks/{int(task_id)}/accept")
    return {"task": task, "message": message}


def cancel_task(*, task_id: int, reason: str | None = None) -> JsonDict:
    task = _api_request("GET", f"/api/tasks/{int(task_id)}")
    if task.get("status") not in {"queued", "canceled"}:
        raise TalkToolError("当前仅支持取消尚未 claim 的任务；运行中取消等待 runner 协作中断协议")
    message = None
    if reason and task.get("status") != "canceled":
        message = reply_task(task_id=task_id, body=reason, workflow_action="none")["message"]
    canceled = _api_request("POST", f"/api/tasks/{int(task_id)}/cancel")
    return {"task": canceled, "message": message}


def collect_result(*, task_id: int) -> JsonDict:
    task = _api_request("GET", f"/api/tasks/{int(task_id)}")
    if task.get("workflow_status") == "submitted":
        _api_request("POST", f"/api/tasks/{int(task_id)}/collect-result")
    elif task.get("workflow_status") != "completed":
        raise TalkToolError(f"任务协作状态为 {task.get('workflow_status')}，尚无可收取结果")
    return get_task(task_id, include_messages=True)


# 只读边界说明：交付摘要不代替业务验收，也不触发任何状态流转。
DELIVERY_READ_ONLY_NOTE = (
    "talk_get_delivery 完全只读：不自动 collect / accept，不改变任务状态，不扫描整个 Hall 历史，"
    "也不按结果正文里的路径读取本机文件。"
)


def _delivery_result_message(task: JsonDict) -> tuple[JsonDict | None, str]:
    """按 result_message_id 精确取回结果消息（最多一条），不拉取整个 Hall 时间线。"""
    reference = task.get("result_message_id")
    if reference is None:
        return None, "no_result_reference"
    params: JsonDict = {"since": int(reference) - 1, "limit": 1}
    if task.get("hall_group_id"):
        params["group_id"] = task["hall_group_id"]
    messages = _api_request("GET", "/api/messages", params=params)
    for message in messages or []:
        if int(message.get("id", -1)) == int(reference):
            return message, "ok"
    return None, "result_message_unavailable"


def get_delivery(
    *,
    task_id: int,
    mode: str = "summary",
    result_message_id: int | None = None,
    offset: int = 0,
    limit: int | None = None,
    fields: list[str] | None = None,
    expect_sha256: str | None = None,
) -> JsonDict:
    """只读交付摘要（summary）与可追溯分页补读（detail）。

    - summary：按 task_id 定位最新结果消息，返回有界摘要；业务结论只来自通过本地
      talk-delivery-1 校验的结构化自报，自由文本 / 无效结构化报告一律 unknown / invalid。
    - detail：必须带 result_message_id 稳定引用，按 offset / limit 分页读取完整结果原文，
      或用 fields 读取交付包顶层字段；引用变化时返回 stale_reference 并要求重置。
    - 两种模式都不自动 collect / accept，不改变任务状态，不读任何本机文件。
    """
    normalized_mode = str(mode or "summary").strip().lower()
    if normalized_mode not in {"summary", "detail"}:
        raise TalkToolError("mode 必须是 summary 或 detail")
    if normalized_mode == "summary" and (
        fields is not None or limit is not None or offset not in (0, None)
    ):
        raise TalkToolError("summary 模式不接受 offset / limit / fields；补读请显式使用 mode=detail")
    try:
        page_offset, page_limit, selected_fields = talk_delivery.normalize_detail_params(
            offset=offset, limit=limit, fields=fields
        )
    except DeliveryParamError as exc:
        raise TalkToolError(str(exc)) from exc

    task = _api_request("GET", f"/api/tasks/{int(task_id)}")
    task_ref_id = task.get("id")
    current_reference = task.get("result_message_id")
    requested_reference = (
        None if result_message_id is None else int(result_message_id)
    )
    if (
        requested_reference is not None
        and current_reference is not None
        and requested_reference != current_reference
    ):
        return talk_delivery.build_stale_payload(
            mode=normalized_mode,
            task_id=task_ref_id,
            reason="result_reference_changed",
            requested_result_message_id=requested_reference,
            current_result_message_id=current_reference,
            current_content_sha256=None,
            page_limit=page_limit,
        )

    message: JsonDict | None = None
    message_state = "no_result_reference"
    if current_reference is not None:
        message, message_state = _delivery_result_message(task)

    if normalized_mode == "summary":
        return talk_delivery.build_delivery_summary(task, message)

    if requested_reference is None:
        raise TalkToolError(
            "detail 模式必须提供 result_message_id（取自 summary 的 runner_status.result_message_id），"
            "用于防止把两份结果拼在一起"
        )
    if current_reference is None:
        return talk_delivery.build_unavailable_payload(
            mode="detail",
            task_id=task_ref_id,
            reason="no_result_reference",
            message="该任务当前没有结果消息引用，无法分页补读；任务正文与 Hall 历史请用既有 talk_get_task。",
        )
    if message is None:
        return talk_delivery.build_unavailable_payload(
            mode="detail",
            task_id=task_ref_id,
            reason=message_state,
            message="按 result_message_id 未能取回结果消息（可能不可见或已删除）；本工具不会退回扫描 Hall 历史。",
        )

    raw_content = message.get("content")
    full_text = raw_content if isinstance(raw_content, str) else ""
    digest = talk_delivery.text_sha256(full_text)
    if expect_sha256 is not None and str(expect_sha256).strip() != digest:
        return talk_delivery.build_stale_payload(
            mode="detail",
            task_id=task_ref_id,
            reason="content_changed",
            requested_result_message_id=requested_reference,
            current_result_message_id=current_reference,
            current_content_sha256=digest,
            page_limit=page_limit,
        )

    report = talk_delivery.parse_delivery_report(raw_content, expect_task_id=task_ref_id)
    if selected_fields is not None:
        if report.kind != "valid" or not isinstance(report.report, dict):
            return talk_delivery.build_unavailable_payload(
                mode="detail",
                task_id=task_ref_id,
                reason=f"structured_report_{report.kind}",
                message=(
                    f"结果消息没有通过 {talk_delivery.SCHEMA_ID} 校验的结构化自报（{report.detail}）；"
                    "请省略 fields，用原文分页补读。"
                ),
            )
        document = json.dumps(
            {name: report.report.get(name) for name in selected_fields}, ensure_ascii=False
        )
        source = "field:" + ",".join(selected_fields)
    else:
        document = full_text
        source = "raw_text"

    try:
        page = talk_delivery.page_document(document, offset=page_offset, limit=page_limit)
    except DeliveryParamError as exc:
        raise TalkToolError(str(exc)) from exc

    next_params = None
    if page["next_offset"] is not None:
        next_params = {
            "task_id": task_ref_id,
            "mode": "detail",
            "result_message_id": requested_reference,
            "offset": page["next_offset"],
            "limit": page_limit,
            "expect_sha256": digest,
        }
        if selected_fields is not None:
            next_params["fields"] = list(selected_fields)
    return {
        "mode": "detail",
        "status": "ok",
        "task_ref": talk_delivery.task_reference(task),
        "reference": {
            "result_message_id": requested_reference,
            "content_sha256": digest,
            "from_id": message.get("from_id"),
            "created_at": message.get("created_at"),
            "chars": len(full_text),
        },
        "delivery_conclusion": talk_delivery.conclusion_for(
            message, report, expect_task_id=task_ref_id
        ),
        "structured_available": report.kind == "valid",
        "source": source,
        "page": page,
        "next_params": next_params,
        "read_only_note": DELIVERY_READ_ONLY_NOTE,
        "notes": [talk_delivery.DELIVERY_STITCH_NOTE, DELIVERY_READ_ONLY_NOTE],
    }


def _normalize_wait_timeout(value: Any) -> tuple[float, float]:
    """把调用方给的超时归一化为 (请求值, 生效值)；生效值落在 0..600 秒。"""
    if value is None:
        return WAIT_DEFAULT_TIMEOUT_SECONDS, WAIT_DEFAULT_TIMEOUT_SECONDS
    if isinstance(value, bool):
        raise TalkToolError("timeout_seconds 必须是数字，不能是布尔值")
    try:
        requested = float(value)
    except (TypeError, ValueError) as exc:
        raise TalkToolError(f"timeout_seconds 必须是数字，收到 {value!r}") from exc
    if math.isnan(requested) or math.isinf(requested):
        raise TalkToolError("timeout_seconds 必须是有限数字")
    return requested, min(max(requested, 0.0), WAIT_MAX_TIMEOUT_SECONDS)


def _normalize_task_ids(values: Any) -> list[int]:
    """校验并去重 task_ids；非法输入直接报错，不退化成项目全量查询。"""
    if values is None:
        return []
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple, set, frozenset)):
        raise TalkToolError("task_ids 必须是整数数组")
    task_ids: list[int] = []
    for raw in values:
        if isinstance(raw, bool):
            raise TalkToolError(f"task_ids 含非法值：{raw!r}")
        try:
            parsed = int(raw)
        except (TypeError, ValueError) as exc:
            raise TalkToolError(f"task_ids 含非法值：{raw!r}") from exc
        if parsed not in task_ids:
            task_ids.append(parsed)
    return task_ids


def _wait_task_reference(task: JsonDict) -> JsonDict:
    """任务进入模型上下文的有界摘要：只保留状态与引用字段，不含正文和历史。"""
    return {field: task.get(field) for field in _WAIT_TASK_REFERENCE_FIELDS}


def _monotonic() -> float:
    """单调时钟间接层：生产用 time.monotonic，测试可替换为模拟时钟。"""
    return time.monotonic()


def _sleep(seconds: float) -> None:
    """轮询间隔间接层：生产用 time.sleep，测试可替换为模拟推进。"""
    time.sleep(seconds)


def _record_wait_stats(record: JsonDict) -> None:
    """可选程序级计数落盘：设置 TALK_WAIT_STATS_FILE 时每次等待追加一行 JSON。"""
    path = str(os.environ.get("TALK_WAIT_STATS_FILE") or "").strip()
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # 统计写入失败不影响等待结果本身。
        return


def wait_tasks(
    *,
    task_ids: list[int] | None = None,
    workflow_statuses: list[str] | None = None,
    project_id: str | None = None,
    timeout_seconds: float = WAIT_DEFAULT_TIMEOUT_SECONDS,
) -> JsonDict:
    """有界等待任务进入目标协作状态。

    - 最长 600 秒、默认 600 秒；超出上限按 600 秒生效并在返回值中标注请求值。
    - 成果提交（submitted）、完成（completed）、失败（failed）、需澄清
      （clarification_requested 等）等状态一旦出现立即返回，不等满超时。
    - 等待全部由程序轮询完成，等待期间不产生新的模型回合、也不经工具分发新增 get/list
      调用（实现声明，非计数）；但本工具无法保证宿主外层零回合。
    - tasks 与成果只回传引用字段（id / hall_group_id / result_message_id 等）和状态，
      不回传任务正文、消息历史或实例历史；提前返回时 tasks 即命中集合（兼容原契约），
      超时返回时是本轮轮询到的任务，两者最多 WAIT_MAX_TASK_REFERENCES 条，超出部分以
      tasks_truncated / tasks_omitted_count / omitted_task_ids 标记，matched_task_ids 完整。
    - TALK API 错误（含 4xx/5xx/网络错误）直接抛出错误，绝不复用超时返回结构。
    - 同步阻塞：客户端取消不会立即终止程序侧等待（仍会跑到命中或超时截止），Windows 下
      客户端进程退出不保证带走 MCP 子进程；等待全程只读，不改变任务状态。
    - query_stats 给出本次调用的程序级实测计数（轮询轮次、HTTP 请求数、耗时、返回原因）。
    """
    effective_project_id = _project_id(project_id)
    desired = {
        str(status).strip().lower()
        for status in (workflow_statuses or DEFAULT_WAIT_WORKFLOW_STATUSES)
        if str(status).strip()
    }
    requested_timeout, effective_timeout = _normalize_wait_timeout(timeout_seconds)
    selected_task_ids = _normalize_task_ids(task_ids)
    stats: JsonDict = {"http_requests": 0}
    started_monotonic = _monotonic()
    started_at = datetime.now(timezone.utc)
    deadline = started_monotonic + effective_timeout
    poll_rounds = 0
    poll_interval = WAIT_INITIAL_POLL_INTERVAL_SECONDS

    def finish(
        *,
        timed_out: bool,
        reason: str,
        polled: list[JsonDict],
        matched: list[JsonDict],
    ) -> JsonDict:
        elapsed = max(0.0, _monotonic() - started_monotonic)
        # 兼容原契约：提前返回时 tasks 就是命中集合；超时路径保留本轮轮询到的全部任务。
        selected = matched if matched else polled
        references = [_wait_task_reference(task) for task in selected]
        returned = references[:WAIT_MAX_TASK_REFERENCES]
        omitted = references[WAIT_MAX_TASK_REFERENCES:]
        payload: JsonDict = {
            "timed_out": timed_out,
            "return_reason": reason,
            "workflow_statuses": sorted(desired),
            "project_id": effective_project_id,
            "task_ids": selected_task_ids or None,
            "requested_timeout_seconds": requested_timeout,
            "timeout_seconds": effective_timeout,
            "max_timeout_seconds": WAIT_MAX_TIMEOUT_SECONDS,
            "elapsed_seconds": round(elapsed, 3),
            "task_count": len(polled),
            "tasks_returned": len(returned),
            "tasks_truncated": bool(omitted),
            "tasks_omitted_count": len(omitted),
            "omitted_task_ids": [task.get("id") for task in omitted],
            "matched_task_ids": [task.get("id") for task in matched],
            "tasks": returned,
            "tasks_note": WAIT_TASKS_NOTE,
            "query_stats": {
                "poll_rounds": poll_rounds,
                "http_requests": int(stats["http_requests"]),
                "elapsed_seconds": round(elapsed, 3),
                "return_reason": reason,
            },
            "counting_note": WAIT_COUNTING_NOTE,
        }
        _record_wait_stats(
            {
                "event": "talk_wait_tasks",
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "project_id": effective_project_id,
                "task_ids": selected_task_ids or None,
                "workflow_statuses": sorted(desired),
                "requested_timeout_seconds": requested_timeout,
                "timeout_seconds": effective_timeout,
                "elapsed_seconds": round(elapsed, 3),
                "return_reason": reason,
                "timed_out": timed_out,
                "poll_rounds": poll_rounds,
                "http_requests": int(stats["http_requests"]),
                "matched_task_ids": [task.get("id") for task in matched],
                "task_count": len(polled),
                "tasks_returned": len(returned),
                "tasks_truncated": bool(omitted),
                "tasks_omitted_count": len(omitted),
            }
        )
        return payload

    while True:
        poll_rounds += 1
        try:
            if selected_task_ids:
                tasks = [
                    _api_request("GET", f"/api/tasks/{int(task_id)}", stats=stats)
                    for task_id in selected_task_ids
                ]
            else:
                tasks = list_tasks(project_id=effective_project_id, stats=stats)["tasks"]
        except TalkToolError as exc:
            elapsed = max(0.0, _monotonic() - started_monotonic)
            _record_wait_stats(
                {
                    "event": "talk_wait_tasks",
                    "started_at": started_at.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "project_id": effective_project_id,
                    "task_ids": selected_task_ids or None,
                    "workflow_statuses": sorted(desired),
                    "requested_timeout_seconds": requested_timeout,
                    "timeout_seconds": effective_timeout,
                    "elapsed_seconds": round(elapsed, 3),
                    "return_reason": "api_error",
                    "timed_out": False,
                    "poll_rounds": poll_rounds,
                    "http_requests": int(stats["http_requests"]),
                    "error": str(exc),
                }
            )
            raise TalkToolError(
                "等待任务状态时 TALK API 调用失败（这不是超时）："
                f"{exc}；已等待 {elapsed:.1f} 秒，轮询 {poll_rounds} 次"
            ) from exc
        matched = [
            task for task in tasks if str(task.get("workflow_status") or "") in desired
        ]
        if matched:
            return finish(timed_out=False, reason="matched", polled=tasks, matched=matched)
        if _monotonic() - started_monotonic >= effective_timeout:
            return finish(timed_out=True, reason="timeout", polled=tasks, matched=[])
        sleep_seconds = min(poll_interval, max(0.0, deadline - _monotonic()))
        _sleep(sleep_seconds)
        poll_interval = min(poll_interval * 2, WAIT_MAX_POLL_INTERVAL_SECONDS)


TOOL_SCHEMAS: list[JsonDict] = [
    {
        "name": "talk_list_agents",
        "description": (
            "列出当前项目可委派的 Agent 及其最新实例状态。返回有界摘要："
            "每个角色最多一个按 last_seen_at 取最新的实例，且只含 "
            "id / runtime / status / current_task_id / last_seen_at / pid，"
            "不返回历史实例、last_error 或既有 CLI 日志。"
            "availability 仅依据实例上报，未做心跳核验，可能滞后，使用时请参考 last_seen_at。"
            "project_id 省略时使用 bridge 项目上下文。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
        },
    },
    {
        "name": "talk_delegate_task",
        "description": "向指定 Agent 创建项目化任务并自动建立独立 Task Hall。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "target_member_id": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "task_kind": {
                    "type": "string",
                    "enum": ["general", "development", "review", "test", "rework"],
                    "default": "general",
                },
                "review_policy": {
                    "type": "string",
                    "enum": ["required", "batch", "exempt"],
                },
                "related_task_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "trigger_task_id": {"type": "integer"},
                "parent_task_id": {"type": "integer"},
                "authorization_epoch": {"type": "integer"},
                "max_clarification_rounds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 2,
                    "default": 1,
                },
            },
            "required": ["target_member_id", "content"],
        },
    },
    {
        "name": "talk_get_task",
        "description": "读取一个任务、任务关系、Task Hall 最近消息及关联结果。",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "talk_list_tasks",
        "description": "按项目、目标 Agent、runner 状态或协作状态查询可见任务。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "target_member_id": {"type": "string"},
                "status": {"type": "string"},
                "workflow_status": {"type": "string"},
                "task_kind": {
                    "type": "string",
                    "enum": ["general", "development", "review", "test", "rework"],
                },
            },
        },
    },
    {
        "name": "talk_wait_tasks",
        "description": (
            "等待任务进入需澄清、成果已提交、已完成或失败等协作状态，最长 600 秒、默认 600 秒；"
            "命中目标状态立即提前返回，不必等满超时。等待由程序轮询完成：程序内部不调用模型，"
            "也不经工具分发新增 get/list 调用（实现声明，非计数），但不保证宿主外层零回合。"
            "返回有界摘要：tasks 只含状态与引用字段（id / project_id / status / workflow_status / "
            "hall_group_id / result_message_id 等），不含任务正文、消息历史或实例历史；"
            "提前返回时 tasks 即命中集合（兼容原契约），超时返回本轮轮询到的任务，"
            f"两者最多 {WAIT_MAX_TASK_REFERENCES} 条，超出部分以 tasks_truncated / tasks_omitted_count / "
            "omitted_task_ids 标记，matched_task_ids 始终是完整命中集合。"
            "query_stats 只含本工具内部实测计数（轮询轮次、HTTP 请求数、耗时、返回原因）。"
            "TALK API 错误会直接返回错误，不会被当成超时。"
            "本工具同步阻塞：客户端取消不会立即终止程序侧等待（仍会跑到命中或超时截止），"
            "Windows 下客户端进程退出不保证带走 MCP 子进程；等待全程只读，不改变任务状态。"
            "客户端单工具超时必须大于最长等待，建议 >= 660 秒。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_ids": {"type": "array", "items": {"type": "integer"}},
                "workflow_statuses": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": WAIT_MAX_TIMEOUT_SECONDS,
                    "default": WAIT_DEFAULT_TIMEOUT_SECONDS,
                },
            },
        },
    },
    {
        "name": "talk_reply_task",
        "description": "在 Task Hall 回复，并可同步请求澄清、明确提交回答、释放人工决策或接受任务。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "body": {"type": "string"},
                "workflow_action": {
                    "type": "string",
                    "enum": [
                        "none",
                        "request_clarification",
                        "submit_clarification_answer",
                        "resolve_clarification",
                        "accept",
                    ],
                },
                "allow_additional_round": {"type": "boolean"},
            },
            "required": ["task_id", "body"],
        },
    },
    {
        "name": "talk_cancel_task",
        "description": "原请求者取消尚未 claim 的任务；运行中任务暂不支持强制取消。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "talk_collect_result",
        "description": "原请求者收取已提交结果，并返回任务、结果消息和 Task Hall 最近消息。",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "talk_get_delivery",
        "description": (
            "只读读取一个任务的交付摘要，并可按稳定引用分页补读完整结果。"
            "summary 模式（默认）按 task_id 定位结果消息，返回有界摘要：task_ref / "
            "runner_status（runner 状态与协作状态）/ delivery_conclusion（业务结论，"
            "只来自结果消息中通过本地 talk-delivery-1 校验、且**自身 task_id 与本任务号一致**"
            "的结构化自报，delivery_conclusion.task_id_check 会如实回显 declared/expected/matches；"
            "自由文本、无效结构化报告或错号自报一律 unknown / invalid，绝不从 succeeded 或正文词汇"
            "推断 complete）/ counts / "
            "preview（阻塞优先）/ summary_text / limits / read_more。"
            f"summary_text 上限 {DELIVERY_SUMMARY_TEXT_LIMIT} 字符，整个 JSON 响应上限 "
            f"{DELIVERY_SUMMARY_JSON_LIMIT} 字符，是两个独立预算，"
            f"不承诺把整份交付报告无损压进 {DELIVERY_SUMMARY_TEXT_LIMIT} 字符；"
            "所有省略都会在 read_more.omitted 与摘要截断标记里显式列出，不会静默丢弃，"
            "更不会在隐藏阻塞项的同时只报完成。"
            "detail 模式必须提供 result_message_id（取自 summary），按 offset / limit 分页读取"
            f"完整结果原文（单页上限 {DELIVERY_DETAIL_MAX_PAGE_CHARS} 字符），"
            "或用 fields 指定 talk-delivery-1 顶层字段读取结构化值；按 offset 顺序拼接各页可无损重建完整结果。"
            "fields 只接受通过校验且 task_id 与本任务号一致的结构化自报，错号时返回 unavailable，"
            "但按 result_message_id 读取完整原文始终不受该核对影响。"
            "结果引用变化（result_message_id 改变，或 expect_sha256 与当前内容不一致）时返回 "
            "status=stale_reference 并要求从 offset=0 重新开始，绝不把两份结果拼在一起。"
            "本工具完全只读：不自动 collect / accept，不改变任务状态，不扫描整个 Hall 历史，"
            "也不按结果正文里的路径读取本机文件；runner 结束不等于用户目标完成。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": (
                        "实际任务号；结果消息里的结构化自报必须自带与之规范化一致的 task_id，"
                        "否则 delivery_conclusion 判 invalid / 不可信"
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["summary", "detail"],
                    "default": "summary",
                },
                "result_message_id": {
                    "type": "integer",
                    "description": "detail 模式必填的稳定结果引用；summary 模式下传入则作为引用一致性断言",
                },
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": DELIVERY_DETAIL_MAX_PAGE_CHARS,
                    "default": DELIVERY_DETAIL_DEFAULT_PAGE_CHARS,
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(TOP_LEVEL_FIELDS)},
                    "description": "detail 模式下按结构化字段补读；省略表示补读完整结果原文",
                },
                "expect_sha256": {
                    "type": "string",
                    "description": "可选：上一页返回的 content_sha256，用于拒绝内容已变化的结果",
                },
            },
            "required": ["task_id"],
        },
    },
]


def dispatch_tool(name: str, arguments: JsonDict) -> JsonDict:
    if name == "talk_list_agents":
        return list_agents(project_id=arguments.get("project_id"))
    if name == "talk_delegate_task":
        return delegate_task(
            project_id=arguments.get("project_id"),
            target_member_id=str(arguments.get("target_member_id") or "").strip(),
            title=str(arguments.get("title") or "").strip() or None,
            content=str(arguments.get("content") or "").strip(),
            task_kind=str(arguments.get("task_kind") or "general").strip().lower(),
            review_policy=str(arguments.get("review_policy") or "").strip().lower() or None,
            related_task_ids=[
                int(task_id) for task_id in (arguments.get("related_task_ids") or [])
            ],
            trigger_task_id=(
                int(arguments["trigger_task_id"])
                if arguments.get("trigger_task_id") is not None
                else None
            ),
            parent_task_id=(
                int(arguments["parent_task_id"])
                if arguments.get("parent_task_id") is not None
                else None
            ),
            authorization_epoch=(
                int(arguments["authorization_epoch"])
                if arguments.get("authorization_epoch") is not None
                else None
            ),
            max_clarification_rounds=int(
                arguments.get("max_clarification_rounds", 1)
            ),
        )
    if name == "talk_get_task":
        return get_task(int(arguments["task_id"]))
    if name == "talk_list_tasks":
        return list_tasks(
            project_id=arguments.get("project_id"),
            target_member_id=arguments.get("target_member_id"),
            status=arguments.get("status"),
            workflow_status=arguments.get("workflow_status"),
            task_kind=arguments.get("task_kind"),
        )
    if name == "talk_wait_tasks":
        return wait_tasks(
            project_id=arguments.get("project_id"),
            task_ids=arguments.get("task_ids"),
            workflow_statuses=arguments.get("workflow_statuses"),
            timeout_seconds=arguments.get("timeout_seconds"),
        )
    if name == "talk_reply_task":
        return reply_task(
            task_id=int(arguments["task_id"]),
            body=str(arguments.get("body") or "").strip(),
            workflow_action=str(arguments.get("workflow_action") or "none"),
            allow_additional_round=bool(arguments.get("allow_additional_round", False)),
        )
    if name == "talk_cancel_task":
        return cancel_task(
            task_id=int(arguments["task_id"]),
            reason=str(arguments.get("reason") or "").strip() or None,
        )
    if name == "talk_collect_result":
        return collect_result(task_id=int(arguments["task_id"]))
    if name == "talk_get_delivery":
        return get_delivery(
            task_id=int(arguments["task_id"]),
            mode=str(arguments.get("mode") or "summary"),
            result_message_id=(
                int(arguments["result_message_id"])
                if arguments.get("result_message_id") is not None
                else None
            ),
            offset=arguments.get("offset", 0),
            limit=arguments.get("limit"),
            fields=arguments.get("fields"),
            expect_sha256=arguments.get("expect_sha256"),
        )
    raise TalkToolError(f"未知 Task Hall 工具: {name}")
