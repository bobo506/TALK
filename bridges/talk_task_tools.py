"""Shared HTTP-backed Task Hall tools for Codex MCP and pi extensions."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

JsonDict = dict[str, Any]
DEFAULT_WAIT_WORKFLOW_STATUSES = [
    "clarification_requested",
    "clarification_answered",
    "needs_decision",
    "submitted",
    "completed",
    "failed",
    "canceled",
]


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
) -> Any:
    base_url, api_key = _config()
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
    url = f"{base_url}{path}" + (f"?{query}" if query else "")
    data = None if json_body is None else json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(url, data=data, headers=headers, method=method.upper())

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


def list_agents(*, project_id: str | None = None) -> JsonDict:
    effective_project_id = _project_id(project_id)
    members = _api_request("GET", "/api/members")
    instances = _api_request("GET", "/api/instances")
    project_member_ids: set[str] | None = None
    if effective_project_id is not None:
        project_agents = _api_request(
            "GET",
            f"/api/projects/{quote(effective_project_id, safe='')}/agents",
        )
        project_member_ids = {str(agent["member_id"]) for agent in project_agents}

    instances_by_member: dict[str, list[JsonDict]] = {}
    for instance in instances:
        instances_by_member.setdefault(str(instance["member_id"]), []).append(instance)

    agents: list[JsonDict] = []
    for member in members:
        member_id = str(member["id"])
        if member.get("kind") != "agent" or member.get("disabled_at") is not None:
            continue
        if project_member_ids is not None and member_id not in project_member_ids:
            continue
        member_instances = instances_by_member.get(member_id, [])
        statuses = [str(instance.get("status") or "offline") for instance in member_instances]
        agents.append(
            {
                "member_id": member_id,
                "display_name": member.get("display_name"),
                "availability": _availability(statuses),
                "instances": member_instances,
            }
        )
    return {"project_id": effective_project_id, "agents": agents}


def delegate_task(
    *,
    target_member_id: str,
    content: str,
    title: str | None = None,
    project_id: str | None = None,
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
        },
    )


def list_tasks(
    *,
    target_member_id: str | None = None,
    status: str | None = None,
    workflow_status: str | None = None,
    project_id: str | None = None,
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
        },
    )
    return {"project_id": effective_project_id, "tasks": tasks}


def get_task(task_id: int, *, include_messages: bool = True) -> JsonDict:
    task = _api_request("GET", f"/api/tasks/{int(task_id)}")
    result: JsonDict = {"task": task}
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


def wait_tasks(
    *,
    task_ids: list[int] | None = None,
    workflow_statuses: list[str] | None = None,
    project_id: str | None = None,
    timeout_seconds: float = 10,
) -> JsonDict:
    effective_project_id = _project_id(project_id)
    desired = {
        str(status).strip().lower()
        for status in (workflow_statuses or DEFAULT_WAIT_WORKFLOW_STATUSES)
        if str(status).strip()
    }
    timeout = max(0.0, min(float(timeout_seconds), 30.0))
    deadline = time.monotonic() + timeout

    while True:
        if task_ids:
            tasks = [_api_request("GET", f"/api/tasks/{int(task_id)}") for task_id in task_ids]
        else:
            tasks = list_tasks(project_id=effective_project_id)["tasks"]
        matched = [task for task in tasks if str(task.get("workflow_status") or "") in desired]
        if matched:
            return {
                "timed_out": False,
                "workflow_statuses": sorted(desired),
                "tasks": matched,
            }
        if time.monotonic() >= deadline:
            return {
                "timed_out": True,
                "workflow_statuses": sorted(desired),
                "tasks": tasks,
            }
        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))


TOOL_SCHEMAS: list[JsonDict] = [
    {
        "name": "talk_list_agents",
        "description": "列出当前项目可委派的 Agent 及其实例忙闲状态。project_id 省略时使用 bridge 项目上下文。",
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
            },
            "required": ["target_member_id", "content"],
        },
    },
    {
        "name": "talk_get_task",
        "description": "读取一个任务、Task Hall 最近消息及关联结果。",
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
            },
        },
    },
    {
        "name": "talk_wait_tasks",
        "description": "等待任务进入澄清、已提交、完成或失败等指定协作状态，最长 30 秒。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_ids": {"type": "array", "items": {"type": "integer"}},
                "workflow_statuses": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 30},
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
        )
    if name == "talk_get_task":
        return get_task(int(arguments["task_id"]))
    if name == "talk_list_tasks":
        return list_tasks(
            project_id=arguments.get("project_id"),
            target_member_id=arguments.get("target_member_id"),
            status=arguments.get("status"),
            workflow_status=arguments.get("workflow_status"),
        )
    if name == "talk_wait_tasks":
        return wait_tasks(
            project_id=arguments.get("project_id"),
            task_ids=arguments.get("task_ids"),
            workflow_statuses=arguments.get("workflow_statuses"),
            timeout_seconds=float(arguments.get("timeout_seconds", 10)),
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
    raise TalkToolError(f"未知 Task Hall 工具: {name}")
