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
    "return_reason）；受控等待（controlled_wait=true）下 identity GET、项目 GET、G8 逐任务核验 GET、"
    "每 30 秒重读 GET 与任务轮询 GET 全部计入 http_requests（含失败的尝试），非受控路径只计入任务轮询；"
    "模型侧的 talk_get_task/talk_list_tasks 调用数与客户端外层等待回合不由本工具"
    "统计，本工具也无法观测，需由任务发起者（调用方）在外部实测。"
)
# 取消/断线边界（工具描述与 --check 共用，避免被读成"取消会立即终止服务端等待"）。
WAIT_CANCELLATION_NOTE = (
    "talk_wait_tasks 是同步阻塞轮询：程序内部不调用模型，但本工具无法保证宿主外层零回合；"
    "客户端取消（notifications/cancelled）不会立即终止程序侧等待，等待仍会跑到命中或超时截止；"
    "Windows 下客户端进程退出不保证带走 MCP 子进程；等待全程只读，不改变任务状态。"
)
# ---------------------------------------------------------------------------
# C2-A1 受控等待（opt-in）常量
#
# 受控等待只有显式 ``controlled_wait=true`` 且 G1–G8 进入门禁全部通过时才启用；
# 省略或 false 的一切调用与旧路径逐字段一致（无身份 GET、无项目重读、返回结构无新字段）。
# 数值来自 CONTROLLER_MODE_DESIGN.md §5.3，本片照表实现。
# ---------------------------------------------------------------------------
# 受控等待期间项目模式字段的低频重读间隔：距上次项目读取 >= 30 秒时在下一循环节点重读一次。
CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS = 30.0
# 客户端单工具预算的显式余量（网络 + 序列化 + 客户端处理）；推荐单次受控预算 = 客户端预算 - 5 秒。
# 本工具读不到宿主客户端预算，这个常量只用于提示调用方，不构成强制。
WAIT_CLIENT_MARGIN_SECONDS = 5.0
# 单次 HTTP 请求超时：旧 helper 固定 10 秒，保持不变；受控路径取 min(该值, 剩余 deadline)。
WAIT_REQUEST_TIMEOUT_SECONDS = 10.0
# 受控等待允许的 return_reason（正常退出枚举）：不新增 cancelled（本版本没有可检测的客户端取消来源）；
# ``controller_changed`` 随固定主控退役一并移除，api_error 是错误路径、不属于本枚举。
CONTROLLED_WAIT_EXIT_REASONS = (
    "matched",
    "timeout",
    "mode_changed",
)
CONTROLLED_WAIT_NOTE = (
    "受控等待是显式 opt-in：只有 controlled_wait=true 且 G1–G8 进入门禁（G1 项目上下文、G2 显式有限正数 "
    "timeout_seconds、G3 按 API Key 反查的 agent 身份、G4 human 凭据拒绝、G5 服务端返回模式字段、"
    "G6 requested_mode=active、G7 显式非空严格正整数 task_ids、G8 逐任务核验存在/可见/同项目/created_by=调用者）"
    "全部通过才启用；任一不满足直接报错，绝不静默降级为普通等待，也不等待合法子集。协调资格只依据任务 "
    "created_by（任务发起者归属）：target、业务角色、模型名、终端名与旧的固定主控指定都不是协调资格。"
    "进入后固定顺序为：每轮先查任务命中（matched 优先），"
    f"再按 {CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS:.0f} 秒节奏重读项目模式字段（不再读取或比对主控指定），"
    "再查 deadline，最后 sleep；模式值变化 / 版本变化 / 字段消失返回 mode_changed。"
    "单次 deadline 从开始核验起算，覆盖身份 GET、项目 GET、逐任务核验 GET、轮询 GET、重读 GET 与 sleep；"
    f"发任何 HTTP 前剩余预算 <=0 就不再发请求，否则该请求超时取 min({WAIT_REQUEST_TIMEOUT_SECONDS:.0f} 秒, "
    "剩余预算)，睡眠不超剩余 deadline。受控短预算需要调用方自行匹配宿主客户端预算（桌面客户端单工具上限 "
    f"65 秒时建议 <=60 秒，即预留 {WAIT_CLIENT_MARGIN_SECONDS:.0f} 秒余量）；工具读不到宿主预算，"
    f"它唯一强制的上限是 {WAIT_MAX_TIMEOUT_SECONDS:.0f} 秒 clamp。受控路径正常退出只有 matched / timeout / "
    "mode_changed；api_error 是错误路径（显式报错、恰一条统计），不属于正常退出枚举。身份门禁只是桥内 "
    "advisory 自我保护与如实退出机制，不代表在线、不代表已获授权，也不替代服务端任务权限。"
)
# 项目路径的 caller_identity 固定三键；成功 note 为 null，失败/不合法时 id 与 kind 均为 null。
CALLER_IDENTITY_FAILED_NOTE = (
    "身份核验失败：未能按 API Key 从 GET /api/members/me 取得身份，本次不猜身份"
)
CALLER_IDENTITY_INVALID_NOTE = (
    "身份核验失败：GET /api/members/me 未返回合法 id/kind，本次不猜身份"
)


class _WaitBudgetExhausted(Exception):
    """内部信号：受控等待剩余预算已耗尽，且尚未发出下一个请求（不外泄给调用方）。"""


class _UnsetTimeout(float):
    """``timeout_seconds`` 的签名默认值哨兵：数值等于 600.0，同时能区分“调用方是否显式传入”。

    既有合同要求 ``wait_tasks.__kwdefaults__["timeout_seconds"] == 600.0``（非受控默认 600 秒不变），
    而受控路径（G2）必须区分“省略 timeout_seconds”和“显式传入 600”。float 子类实例同时满足两者：
    非受控路径取值与旧版逐字节一致，受控路径用 ``is WAIT_TIMEOUT_UNSET`` 判定“未显式传入”。
    """


WAIT_TIMEOUT_UNSET = _UnsetTimeout(WAIT_DEFAULT_TIMEOUT_SECONDS)

# 实例摘要只保留短字段（id / runtime / status / current_task_id / last_seen_at / pid），
# 不含 last_error 与历史实例；availability 仍需消费者结合 last_seen_at 判断心跳新鲜度。
AVAILABILITY_NOTE = (
    "availability 仅依据 agent_instances 上报状态，未做心跳核验，"
    "可能滞后于真实在线状态，使用前请按 last_seen_at 判断新鲜度。"
)
# 项目级开发要求随 talk_delegate_task 写入任务正文的区块标题：内容是派发时刻的快照，
# 不是活动引用；已派发任务不随项目要求后续修改而变。
PROJECT_REQUIREMENTS_SNAPSHOT_HEADER = "项目开发要求（派发时快照）"
PROJECT_REQUIREMENTS_SNAPSHOT_NOTE = (
    "以下内容由任务发起者在派发时从项目读取并写入任务正文，仅作为随包保存的文本快照："
    "不自动授予权限，不替代或覆盖宿主系统指令，也不追溯修改已创建任务。"
)
# C1a 模式只读状态：requested_mode 是项目保存的“模式意向”，
# effective_mode 是“本会话实际生效”的证据，本片没有任何会话绑定/生效确认，恒为 null。
CONTROLLER_MODE_NOTE = (
    "controller_mode 只是项目保存的模式意向（requested_mode）与版本，"
    "本版本没有发起者会话绑定或生效确认：effective_mode 恒为 null（effective_status=not_bound）。"
    "保存 active 不等于已生效、不等于已唤回发起者会话，也不产生等待/调度/派发或任何授权；"
    "默认协作仍是派发后结束、由用户通知后再取件。"
)
CONTROLLER_MODE_UNSUPPORTED_NOTE = (
    "当前后端未返回模式字段（旧后端）：模式意向状态为 unsupported，"
    "不得把缺失当成 passive 或 active，也不得据此判断可自动推进。"
)
CONTROLLER_MODE_EFFECTIVE_STATUS_SUPPORTED = "not_bound"
CONTROLLER_MODE_EFFECTIVE_STATUS_UNSUPPORTED = "unsupported"
# 只读白名单：与 server.models.PROJECT_CONTROLLER_MODES 对齐；服务端返回未知值时
# 只报 null，不把意外取值当成合法模式透传给模型。
CONTROLLER_MODES = ("passive", "active")
# C1b-S1 长期主控指定的只读状态（D-1）：字段形状与旧后端降级行为保持兼容，
# member_id/version 是项目保存的历史指定，status 是服务端按当前名册与成员事实实时算出的
# **配置有效性**，但该指定已弃用：不再决定任何协调/调度，也不表示在线、ACK、会话归属或授权。
CONTROLLER_ASSIGNMENT_NOTE = (
    "该指定为历史兼容字段，已弃用：不再决定任何协调/调度，不产生任何权限。"
    "回显历史保存的 member_id + version 与配置有效性：assigned 只表示成员已注册、未禁用、"
    "在册且为 agent，不代表在线/已确认(ACK)/会话生效或获得额外权限；本版本没有会话 token、"
    "租约或心跳，不自动唤醒进程。unassigned=未指定；not_in_roster / member_disabled / "
    "member_missing / not_agent 是读取瞬间实测的无效原因，不会自动解除或转移，仍由 human 清空。"
    "与 business_role / decision_tier 分开，不改变派发、领取、完成、收取权限。"
)
CONTROLLER_ASSIGNMENT_UNSUPPORTED_NOTE = (
    "当前后端未返回主控指定字段（旧后端）：controller_assignment 为 supported=false / "
    "status=unsupported，member_id 与 version 均为 null；不得把缺失当成未指定，"
    "也不得据此声称项目已指定主控或无人指定。该字段已弃用，缺字段不影响任何协调资格，"
    "受控等待也不读取它。"
)
CONTROLLER_ASSIGNMENT_UNKNOWN_STATUS_NOTE = (
    "后端返回了主控指定成员，但没有可识别的有效性状态：status=unknown，"
    "无法判断该指定当前是否有效，需读取方自行核对名册与成员状态，不得假定有效。"
    "该字段已弃用，unknown 不影响任何协调资格。"
)
CONTROLLER_ASSIGNMENT_EFFECTIVE_STATUS_UNSUPPORTED = "unsupported"
# 只读白名单：与 server.models.PROJECT_ASSIGNMENT_STATUSES 对齐；未知取值只报 unknown。
CONTROLLER_ASSIGNMENT_STATUSES = (
    "unassigned",
    "assigned",
    "member_missing",
    "member_disabled",
    "not_in_roster",
    "not_agent",
)
CONTROLLER_ASSIGNMENT_STATUS_UNKNOWN = "unknown"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class TalkToolError(RuntimeError):
    """A user-facing TALK tool failure."""


class TalkApiHttpError(TalkToolError):
    """TALK API 返回了 HTTP 错误状态码时的结构化出口（I-1）。

    - 由 ``_api_request`` 的 ``HTTPError`` 分支抛出，**消息文本形态与旧版逐字一致**
      （``TALK API HTTP <code>: <detail>``），旧调用方按文本处理不受影响；
    - 额外携带 ``.status``，供 G8 按状态码判定业务拒绝（404），不脆弱解析整段错误文案；
      其它 HTTP/网络失败仍按 ``api_error`` 分类。
    """

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.status = int(status)


class _IdentityShapeError(TalkToolError):
    """内部错误：身份响应存在但缺少合法 ``id`` / ``kind``（区别于身份请求本身失败）。"""


def _config() -> tuple[str, str]:
    base_url = os.environ.get("TALK_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    api_key = os.environ.get("TALK_API_KEY", "").strip()
    if not api_key:
        raise TalkToolError("TALK_API_KEY 未设置")
    return base_url, api_key


def _request_timeout_message(timeout: float) -> str:
    """单次 HTTP 请求被超时掐断时的工具错误文案（不泄露密钥，也不冒充正常 deadline timeout）。"""
    return (
        f"TALK API 请求超时（本次单次请求超时上限 {timeout:g} 秒）："
        "这是 API/网络层错误，不是任务等待 deadline 的正常 timeout"
    )


def _api_request(
    method: str,
    path: str,
    *,
    json_body: JsonDict | None = None,
    params: JsonDict | None = None,
    stats: JsonDict | None = None,
    timeout: float = WAIT_REQUEST_TIMEOUT_SECONDS,
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
        # 计数在发请求前自增：失败的尝试同样计入 query_stats.http_requests。
        stats["http_requests"] = int(stats.get("http_requests", 0)) + 1

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as exc:
        try:
            payload = exc.read()
        except (TimeoutError, OSError):
            payload = b""
        detail: Any = payload.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            detail = parsed.get("detail", parsed)
        except json.JSONDecodeError:
            pass
        raise TalkApiHttpError(f"TALK API HTTP {exc.code}: {detail}", status=exc.code) from exc
    except TimeoutError as exc:
        # 连接阶段或 getresponse/read 阶段的裸超时：归一为工具错误，不让裸异常逃出工具层。
        raise TalkToolError(_request_timeout_message(timeout)) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            raise TalkToolError(_request_timeout_message(timeout)) from exc
        raise TalkToolError(f"无法连接 TALK API: {reason}") from exc
    except OSError as exc:
        # 未被 URLError 包装的网络 OSError：同样归一，但如实按网络错误报告，不统称“超时”。
        if isinstance(exc, TimeoutError):
            raise TalkToolError(_request_timeout_message(timeout)) from exc
        raise TalkToolError(f"无法连接 TALK API: {exc}") from exc

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


def _identity_from_api(
    *,
    stats: JsonDict | None = None,
    timeout: float = WAIT_REQUEST_TIMEOUT_SECONDS,
) -> tuple[str, str]:
    """唯一可靠身份来源：``GET /api/members/me``（服务端按 API Key 反查），返回 (id, kind)。

    - 不使用 ``TALK_MEMBER_ID``、模型名、业务角色标签或会话标题自证（C2-A1 §5.2）；
      ``_member_id()`` 的环境变量优先语义保留给旧调用方，受控门禁与 caller_identity 都不复用它。
    - 请求失败或响应缺合法 ``id`` / ``kind`` 时抛 ``TalkToolError``，由调用方决定是拒绝（受控门禁）
      还是降级成 null + note（``talk_list_agents``）。
    """
    current = _api_request("GET", "/api/members/me", stats=stats, timeout=timeout)
    if not isinstance(current, dict):
        raise _IdentityShapeError("身份响应不是对象")
    member_id = current.get("id")
    kind = current.get("kind")
    if not isinstance(member_id, str) or not member_id.strip():
        raise _IdentityShapeError("身份响应缺少合法 id")
    if kind not in {"human", "agent"}:
        raise _IdentityShapeError("身份响应缺少合法 kind")
    return member_id.strip(), str(kind)


def caller_identity_summary(
    *,
    stats: JsonDict | None = None,
    timeout: float = WAIT_REQUEST_TIMEOUT_SECONDS,
) -> JsonDict:
    """项目路径的固定三键身份披露：``{member_id, kind, note}``（C2-A1 §5.2 / R3）。

    - 成功：``member_id`` / ``kind`` 来自 ``GET /api/members/me``，``note`` 为 ``null``；
    - 失败或不合法：``member_id`` / ``kind`` 均为 ``null``，``note`` 是简短中文原因，
      不含密钥或完整异常正文，也**不阻断**角色清单的其余内容；
    - 非项目路径不调用本函数（``talk_list_agents`` 显式返回 ``caller_identity: null``，且不额外发身份请求）。
    """
    try:
        member_id, kind = _identity_from_api(stats=stats, timeout=timeout)
    except _IdentityShapeError:
        return {"member_id": None, "kind": None, "note": CALLER_IDENTITY_INVALID_NOTE}
    except TalkToolError:
        return {"member_id": None, "kind": None, "note": CALLER_IDENTITY_FAILED_NOTE}
    return {"member_id": member_id, "kind": kind, "note": None}


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


def project_development_requirements(project_id: str) -> str | None:
    """读取指定项目当前的最新开发要求（只读，不做缓存）。

    - 项目缺失或不可见时沿用 ``GET /api/projects/{id}`` 的既有错误语义，抛 ``TalkToolError``；
      不会回退到其它项目或上一次读到的陈旧快照；
    - 无内容（服务端存 NULL/空）时返回 ``None``，调用方据此保持原有行为。
    """
    project = _api_request("GET", f"/api/projects/{quote(project_id, safe='')}")
    value = project.get("development_requirements") if isinstance(project, dict) else None
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def snapshot_task_content(content: str, requirements: str | None) -> str:
    """把非空项目开发要求以清晰区块追加进任务正文，保留调用者原始 content。

    - 要求为空时原样返回 ``content``，派发行为与旧版本完全一致；
    - 快照放在原始正文之后，保证 Task Hall 名称推导（无标题时取正文开头）
      与既有标题规则不受影响；
    - 只做文本拼接，不解析、不执行要求内容。
    """
    if requirements is None:
        return content
    note = PROJECT_REQUIREMENTS_SNAPSHOT_NOTE
    return (
        f"{content}\n\n"
        f"【{PROJECT_REQUIREMENTS_SNAPSHOT_HEADER}】\n"
        f"{note}\n"
        "----------------------------------------\n"
        f"{requirements}"
    )


def controller_mode_summary(project: JsonDict) -> JsonDict:
    """把项目详情里的模式意向整理成只读状态对象（C1a，不做任何网络请求）。

    调用方必须传入**同一次** ``GET /api/projects/{id}`` 的结果：与
    ``development_requirements`` 复用同一份响应，避免重复请求。

    - 后端已支持（响应含 ``controller_mode`` 与 ``controller_mode_version``）：
      ``requested_mode`` / ``requested_version`` 回显保存值，``effective_mode`` 恒为 ``null``，
      ``effective_status=not_bound``；
    - 旧后端缺字段：``supported=false``、``effective_status=unsupported``，
      不回退猜测成 passive；
    - 非项目路径不调用本函数（``talk_list_agents`` 明确返回 ``controller_mode: null``）。
    """
    if "controller_mode" not in project or "controller_mode_version" not in project:
        return {
            "project_id": project.get("project_id"),
            "supported": False,
            "requested_mode": None,
            "requested_version": None,
            "effective_mode": None,
            "effective_status": CONTROLLER_MODE_EFFECTIVE_STATUS_UNSUPPORTED,
            "note": CONTROLLER_MODE_UNSUPPORTED_NOTE,
        }
    mode = project.get("controller_mode")
    version = project.get("controller_mode_version")
    return {
        "project_id": project.get("project_id"),
        "supported": True,
        "requested_mode": mode if isinstance(mode, str) and mode in CONTROLLER_MODES else None,
        "requested_version": (
            version
            if isinstance(version, int) and not isinstance(version, bool)
            else None
        ),
        "effective_mode": None,
        "effective_status": CONTROLLER_MODE_EFFECTIVE_STATUS_SUPPORTED,
        "note": CONTROLLER_MODE_NOTE,
    }


def controller_assignment_summary(project: JsonDict) -> JsonDict:
    """把项目详情里的历史主控指定整理成只读状态对象（C1b-S1 / D-1，不做任何网络请求）。

    该字段已弃用：输出形状、status 取值与旧后端降级行为**保持不变**，供旧消费者有一个如实的
    降级窗口，但它不再决定任何协调/调度，受控等待的门禁也不再读取它。

    调用方必须传入**同一次** ``GET /api/projects/{id}`` 的结果：与
    ``development_requirements`` / ``controller_mode`` 复用同一份响应，不新增请求。

    - 后端已支持（响应含 ``controller_member_id`` 与 ``controller_assignment_version``）：
      回显 ``member_id`` / ``version``，``status`` 取服务端实时计算的配置有效性；
      成员为 null 时恒为 ``unassigned``（这一条不需要额外信息即可如实判定）；
      后端未给可识别状态而成员非 null 时只报 ``unknown``，不猜测有效性；
    - 旧后端缺字段：``supported=false`` / ``status=unsupported``，两个值均为 null，
      不回退猜测成“未指定”；
    - 非项目路径不调用本函数（``talk_list_agents`` 明确返回 ``controller_assignment: null``）。
    """
    if "controller_member_id" not in project or "controller_assignment_version" not in project:
        return {
            "project_id": project.get("project_id"),
            "supported": False,
            "member_id": None,
            "version": None,
            "status": CONTROLLER_ASSIGNMENT_EFFECTIVE_STATUS_UNSUPPORTED,
            "note": CONTROLLER_ASSIGNMENT_UNSUPPORTED_NOTE,
        }

    raw_member_id = project.get("controller_member_id")
    member_id = (
        raw_member_id.strip() or None if isinstance(raw_member_id, str) else None
    )
    raw_version = project.get("controller_assignment_version")
    version = (
        raw_version
        if isinstance(raw_version, int) and not isinstance(raw_version, bool)
        else None
    )
    raw_status = project.get("controller_assignment_status")
    if isinstance(raw_status, str) and raw_status in CONTROLLER_ASSIGNMENT_STATUSES:
        status = raw_status
    elif member_id is None:
        status = "unassigned"
    else:
        status = CONTROLLER_ASSIGNMENT_STATUS_UNKNOWN

    if status == CONTROLLER_ASSIGNMENT_STATUS_UNKNOWN:
        note = CONTROLLER_ASSIGNMENT_UNKNOWN_STATUS_NOTE
    else:
        note = CONTROLLER_ASSIGNMENT_NOTE
    return {
        "project_id": project.get("project_id"),
        "supported": True,
        "member_id": member_id,
        "version": version,
        "status": status,
        "note": note,
    }


# B3（ROLE-BINDING-B3）：角色摘要只读消费 B1a 已公开的绑定事实（合同 §4.3）。
# 白名单 = ``server.models.RoleBindingOut`` 的公开键；角色摘要只透传这些键，
# 未知键（凭据正文/凭据路径/实例日志/未来 B2 的 binding_match*）一律不带入摘要，
# 也不在 bridge 侧新增字段，或从模型名、业务角色、环境、native 配置、最新实例推断绑定值。
ROLE_BINDING_PUBLIC_FIELDS = (
    "runner_id",
    "runtime",
    "runner_display_name",
    "runner_status",
    "model_source",
    "provider_id",
    "connection_ref",
    "model_id",
    "model_alias",
    "model_display_name",
    "binding_state",
    "binding_fingerprint",
    "updated_by",
    "updated_at",
)


def role_binding_summary(raw_binding: Any) -> JsonDict | None:
    """把同次角色读取里的 ``binding`` 整理成只读公开字段字典；无存储行 = ``None``。

    - 只按 :data:`ROLE_BINDING_PUBLIC_FIELDS` 白名单取键，值**原样透传**（含 ``null``）：
      不解析/执行/探测 ``connection_ref``，不猜运行器或模型，不生成任何实际匹配结论；
    - 后端缺该键或不是对象（旧后端 / 异常载荷）→ ``None``：不伪造默认绑定，
      也不把缺失填成 ``unconfigured`` 或某个运行器。
    """
    if not isinstance(raw_binding, dict):
        return None
    return {field: raw_binding.get(field) for field in ROLE_BINDING_PUBLIC_FIELDS}


def role_binding_state_value(raw_state: Any) -> str | None:
    """把同次角色读取里的 ``binding_state`` 原样透传；缺失 / 非字符串 → ``None``。

    缺失时保持 ``null``（不猜 ``unconfigured`` 或 ``bound``）；服务器实测的保留配置或异常状态
    （``partial`` / ``runner_missing`` / ``runner_retired`` 等）同样照原样传出，**不压成** ``bound``。
    """
    if isinstance(raw_state, str) and raw_state.strip():
        return raw_state
    return None


def list_agents(*, project_id: str | None = None) -> JsonDict:
    effective_project_id = _project_id(project_id)
    if effective_project_id is not None:
        # 同一个项目 GET 响应同时承载开发要求与模式意向，不额外发起第二次项目请求。
        project = _api_request(
            "GET",
            f"/api/projects/{quote(effective_project_id, safe='')}",
        )
        project_agents = _api_request(
            "GET",
            f"/api/projects/{quote(effective_project_id, safe='')}/agents",
        )
        active_agent_ids = {
            str(member["id"])
            for member in _api_request("GET", "/api/members")
            if member.get("kind") == "agent" and member.get("disabled_at") is None
        }
        # C2-A1：项目路径额外用一次 GET /api/members/me 按 Key 反查调用者身份并如实披露；
        # 该请求失败只降级为 {id: null, kind: null, note}，不阻断角色清单，也不计入任何 query_stats
        # （list_agents 没有 query_stats 字段，不凭空添加）。
        caller_identity = caller_identity_summary()
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
                    # B3：绑定事实与角色清单来自**同一次** GET /projects/{id}/agents 响应，
                    # 不额外发绑定/身份请求，不做写入，也不从实例 runtime 推断绑定值。
                    "binding": role_binding_summary(agent.get("binding")),
                    "binding_state": role_binding_state_value(
                        agent.get("binding_state")
                    ),
                }
            )
        return {
            "project_id": effective_project_id,
            "development_requirements": project.get("development_requirements"),
            "controller_mode": controller_mode_summary(project),
            "controller_assignment": controller_assignment_summary(project),
            "caller_identity": caller_identity,
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
                # B3：非项目路径没有项目绑定上下文，两个字段都明确为 null，
                # 且不额外发项目/角色绑定/身份请求（全局路径读取边界保持原样）。
                "binding": None,
                "binding_state": None,
            }
        )
    return {
        "project_id": effective_project_id,
        # 非项目路径没有项目上下文，保持字段存在以便调用方统一取值。
        "development_requirements": None,
        # 非项目路径没有项目模式意向：明确 null，不伪造 passive。
        "controller_mode": None,
        # 非项目路径同样没有（已弃用的）主控指定上下文：明确 null，不伪造“未指定”。
        "controller_assignment": None,
        # 非项目路径没有可靠的 Key 反查上下文：明确 null，且不额外发身份请求。
        "caller_identity": None,
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
    # 派发前读取该项目的当前开发要求：只作用于本次新建任务的存储正文，
    # 不追溯修改已创建任务，也不改变任何权限或预算字段。
    requirements = project_development_requirements(effective_project_id)
    stored_content = snapshot_task_content(content, requirements)
    return _api_request(
        "POST",
        "/api/tasks",
        json_body={
            "target_member_id": target_member_id,
            "content": stored_content,
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

    - summary：按 task_id 定位最新结果消息，返回默认不做机械裁剪的完整摘要；业务结论只来自通过本地
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


def _controlled_task_ids(values: Any) -> list[int]:
    """受控 true 专用（D-3 / G7）的严格 task_ids 校验：先全量校验，再按首次出现顺序稳定去重。

    - 必须**显式提供**（非省略/None）、为**数组**且**非空**；字符串/数字/对象整体、集合等一律拒绝；
    - 元素必须是**严格正整数**：bool（True/False）、float（含 ``1.0`` 这类整数值浮点）、字符串
      （含 ``"5"``）、None、0、负整数与其它类型**一律拒绝**，不做 ``int()`` 转换、不截断、不静默丢弃；
    - **任一非法即整批报错并指明非法项**，绝不返回合法子集，也绝不退化成项目级范围查询；
    - 全部合法后按首次出现顺序稳定去重（重复不是错误）。

    调用位置固定在 G6（模式 active）之后、G8 逐任务核验之前：G3 之前的宽松归一化
    ``_normalize_task_ids`` 只保留给 false/省略路径，旧语义不变。
    """
    if values is None:
        raise TalkToolError(
            "受控等待必须显式传入非空 task_ids（G7）：省略或 null 无法确定要跟进的具体任务"
        )
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise TalkToolError(
            "受控等待的 task_ids 必须是 JSON 数组（G7），不能是字符串/数字/对象/集合或其它类型，"
            f"收到 {values!r}"
        )
    if not values:
        raise TalkToolError("受控等待的 task_ids 不能为空数组（G7）：必须明确要跟进的具体任务")
    invalid: list[Any] = []
    task_ids: list[int] = []
    for raw in values:
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
            invalid.append(raw)
            continue
        if raw not in task_ids:
            task_ids.append(raw)
    if invalid:
        raise TalkToolError(
            "受控等待的 task_ids 必须是严格正整数数组（G7）：不接受 bool、浮点（含 1.0）、字符串、"
            f"null、0 或负整数；非法项 {invalid!r} 整批拒绝，不等待合法子集"
        )
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


def _normalize_controlled_wait(value: Any) -> bool:
    """校验 ``controlled_wait``：只接受 true/false（含缺省 None 等价 false），其它类型直接报错。"""
    if value is None or value is False:
        return False
    if value is True:
        return True
    raise TalkToolError(
        f"controlled_wait 必须是布尔值 true/false（缺省等价 false），收到 {value!r}"
    )


def _controlled_wait_timeout(value: Any) -> tuple[float, float]:
    """G2：受控路径必须显式传入有限正数 timeout，不采用 600 秒默认值。

    bool、非数值（字符串/None/其它类型）、NaN、inf、0 与负值一律拒绝；合法值按既有上限 clamp 到 600。
    非受控路径继续走 ``_normalize_wait_timeout``，旧语义（缺省 600、负数归零、数字字符串可接受）不变。
    """
    if value is None or value is WAIT_TIMEOUT_UNSET:
        raise TalkToolError(
            "受控等待必须显式传入 timeout_seconds（有限正数，单位秒，且不超过 "
            f"{WAIT_MAX_TIMEOUT_SECONDS:.0f}）"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TalkToolError(
            f"受控等待的 timeout_seconds 必须是数字（JSON number），不能是布尔值/字符串/其它类型，收到 {value!r}"
        )
    requested = float(value)
    if math.isnan(requested) or math.isinf(requested):
        raise TalkToolError("受控等待的 timeout_seconds 必须是有限数字")
    if requested <= 0:
        raise TalkToolError(f"受控等待的 timeout_seconds 必须大于 0，收到 {requested!r}")
    return requested, min(requested, WAIT_MAX_TIMEOUT_SECONDS)


def _wait_payload(
    *,
    timed_out: bool,
    reason: str,
    polled: list[JsonDict],
    matched: list[JsonDict],
    desired: set[str],
    effective_project_id: str | None,
    selected_task_ids: list[int],
    requested_timeout: float,
    effective_timeout: float,
    elapsed: float,
    poll_rounds: int,
    stats: JsonDict,
    controlled: bool = False,
    controlled_entry: JsonDict | None = None,
    controlled_rechecks: int = 0,
) -> JsonDict:
    """等待返回结构（受控/非受控共用）：非受控路径不加任何新字段，受控路径只追加合同允许的三个。"""
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
    if controlled:
        # 合同 §5.1：仅受控路径新增且仅新增这三个字段。
        payload["controlled_wait"] = True
        payload["controlled_entry"] = controlled_entry
        payload["controlled_rechecks"] = controlled_rechecks
    return payload


def _wait_tasks_legacy(
    *,
    task_ids: list[int] | None,
    workflow_statuses: list[str] | None,
    project_id: str | None,
    timeout_seconds: Any,
) -> JsonDict:
    """非受控路径：与 C2-A1 之前逐字段一致，不产生身份 GET、不做项目重读、不加新字段。"""
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
        payload = _wait_payload(
            timed_out=timed_out,
            reason=reason,
            polled=polled,
            matched=matched,
            desired=desired,
            effective_project_id=effective_project_id,
            selected_task_ids=selected_task_ids,
            requested_timeout=requested_timeout,
            effective_timeout=effective_timeout,
            elapsed=elapsed,
            poll_rounds=poll_rounds,
            stats=stats,
        )
        returned_count = len(payload["tasks"])
        omitted_count = payload["tasks_omitted_count"]
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
                "tasks_returned": returned_count,
                "tasks_truncated": bool(omitted_count),
                "tasks_omitted_count": omitted_count,
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


def _wait_tasks_controlled(
    *,
    task_ids: Any,
    workflow_statuses: Any,
    project_id: str | None,
    timeout_seconds: Any,
) -> JsonDict:
    """受控等待（发起者门禁 G1–G8）：进入门禁 + 30 秒模式重读 + 单次 deadline 全记账。

    进入门禁顺序固定：G1 项目上下文 → G2 显式有限正数 timeout → G3 按 API Key 反查 agent 身份
    → G4 human 凭据拒绝 → G5 服务端返回模式字段 → G6 requested_mode=active（用 G5 同一次响应判定，
    零新增请求）→ G7 task_ids 严格校验与稳定去重（位置固定在 G6 之后）→ G8 按去重顺序逐唯一 ID
    各发恰好一次任务 GET，核验存在/可见/同项目/created_by==调用者，任一不符整批拒绝、不等待合法子集。
    协调资格只依据任务 ``created_by``：target、业务角色、模型名、终端名与旧的固定主控指定都不是资格。
    失败策略只有两类：进入期=报错（不轮询、不降级），运行期=显式原因正常退出
    （matched / mode_changed / timeout；``controller_changed`` 已随固定主控退役），
    API 错误=显式抛错（api_error）；运行期的任务轮询节点与 30 秒重读节点走同一 api_error 出口
    （带真实 elapsed/rounds，并落恰好一条 ``return_reason=api_error`` 统计）。
    本函数全程只读：不修改任务状态、不取消在途任务、不收取，也不伪造 effective_mode 或调度互斥。
    """
    # G1 项目上下文
    effective_project_id = _project_id(project_id)
    if effective_project_id is None:
        raise TalkToolError(
            "受控等待必须有项目上下文（G1）：请显式传入 project_id，或让 bridge 设置 TALK_PROJECT_ID"
        )
    # G2 显式、严格、有限、正的 timeout
    requested_timeout, effective_timeout = _controlled_wait_timeout(timeout_seconds)
    desired = {
        str(status).strip().lower()
        for status in (workflow_statuses or DEFAULT_WAIT_WORKFLOW_STATUSES)
        if str(status).strip()
    }
    # R-6 / D-3：true 路径的 selected_task_ids 初始为 None，仅在 G7 全量校验与稳定去重通过后才赋值；
    # 因此 G3–G6 失败与 G7 非法失败的 entry JSONL 写 task_ids=null（不落原始非法输入、不部分保留合法子集），
    # G8 失败则记录完整已合法去重列表（ID 来自调用者，不来自任务响应）。
    selected_task_ids: list[int] | None = None

    stats: JsonDict = {"http_requests": 0}
    started_monotonic = _monotonic()
    started_at = datetime.now(timezone.utc)
    # 单次 deadline 从开始核验起算：身份 GET、项目 GET、逐任务核验 GET、轮询 GET、重读 GET、sleep 全部计入。
    deadline = started_monotonic + effective_timeout
    poll_rounds = 0
    poll_interval = WAIT_INITIAL_POLL_INTERVAL_SECONDS
    last_polled: list[JsonDict] = []
    rechecks = 0
    last_project_read = started_monotonic

    def remaining() -> float:
        return deadline - _monotonic()

    def next_request_timeout() -> float:
        """发 HTTP 前用剩余预算 clamp 单次请求超时；调用方必须先确认 remaining > 0。"""
        return min(WAIT_REQUEST_TIMEOUT_SECONDS, max(remaining(), 0.001))

    def record_entry_failure(gate: str, message: str, *, api_error: bool) -> None:
        """进入门禁拒绝：写一条可追溯的 JSONL（``return_reason`` 置 null，明确不是等待返回结构）后报错。

        - G1/G2 在发出任何 HTTP 前就直接报错，不写本记录（没有任何计数可记）；
        - ``return_reason`` 只在本次拒绝由 TALK API/网络错误引起时写 ``api_error``；
          纯参数或配置性拒绝（G3 预算不足、G4、G5 缺字段、G6、G7 非法输入、G8 业务拒绝/核验预算耗尽）
          写 ``null``，因为它们不产生等待返回结构，也不是 API 错误；
        - 记录里保留 ``entry_gate`` 与 ``entry_error``，便于按门禁号追溯为什么没有开始等待。
        """
        _record_wait_stats(
            {
                "event": "talk_wait_tasks_entry",
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "project_id": effective_project_id,
                "task_ids": selected_task_ids or None,
                "workflow_statuses": sorted(desired),
                "requested_timeout_seconds": requested_timeout,
                "timeout_seconds": effective_timeout,
                "elapsed_seconds": round(max(0.0, _monotonic() - started_monotonic), 3),
                "return_reason": "api_error" if api_error else None,
                "timed_out": False,
                "controlled_wait": True,
                "entry_gate": gate,
                "http_requests": int(stats["http_requests"]),
                "entry_error": message,
            }
        )
        raise TalkToolError(message)

    # ---- 进入门禁 G3–G8：任一不过报错，不执行任何等待，也绝不静默降级为普通等待 ----
    if remaining() <= 0:
        record_entry_failure(
            "G3",
            "受控等待进入核验失败（G3）：开始核验时剩余预算已耗尽，"
            "未完成身份核验，按进入错误返回且不开始普通等待",
            api_error=False,
        )
    try:
        caller_member_id, caller_kind = _identity_from_api(
            stats=stats, timeout=next_request_timeout()
        )
    except _IdentityShapeError as exc:
        record_entry_failure(
            "G3",
            f"受控等待进入核验失败（G3：身份响应不合法，无法核实调用者）：{exc}",
            api_error=False,
        )
    except TalkToolError as exc:
        record_entry_failure(
            "G3",
            f"受控等待进入核验失败（G3：无法按 API Key 核实调用者身份）：{exc}",
            api_error=True,
        )
    if caller_kind != "agent":
        record_entry_failure(
            "G4",
            "受控等待仅允许 agent 身份调用（G4）：当前 API Key 的身份是 "
            f"{caller_member_id}（kind={caller_kind}），human 凭据不能驱动受控主动等待",
            api_error=False,
        )
    if remaining() <= 0:
        record_entry_failure(
            "G5",
            "受控等待进入核验失败（G5）：读取项目前剩余预算已耗尽，"
            "未完成模式字段核验，按进入错误返回且不开始普通等待",
            api_error=False,
        )
    try:
        project = _api_request(
            "GET",
            f"/api/projects/{quote(effective_project_id, safe='')}",
            stats=stats,
            timeout=next_request_timeout(),
        )
    except TalkToolError as exc:
        record_entry_failure(
            "G5",
            f"受控等待进入核验失败（G5：无法读取项目 {effective_project_id}）：{exc}",
            api_error=True,
        )
    last_project_read = _monotonic()
    project_payload = project if isinstance(project, dict) else {}
    mode = controller_mode_summary(project_payload)
    # G5 只要求服务端返回模式字段：不再要求主控指定字段存在（旧字段缺失/无效只影响只读输出层降级）。
    if not mode["supported"]:
        record_entry_failure(
            "G5",
            "受控等待进入核验失败（G5）：当前服务未返回模式字段"
            "（controller_mode / controller_mode_version），不支持受控等待；"
            "缺失字段不猜测成 passive 或 active",
            api_error=False,
        )
    # G6 模式必须是 active：复用 G5 的同一次项目响应判定，零新增请求，且前置到逐任务 GET 之前。
    if mode["requested_mode"] != "active":
        record_entry_failure(
            "G6",
            f"受控等待进入核验失败（G6）：项目 {effective_project_id} 的模式意向是 "
            f"{mode['requested_mode']}，不是 active；保存 active 只是模式意向，"
            "缺失或未知取值同样按不支持处理，不猜成 active",
            api_error=False,
        )
    # G7 严格输入校验与稳定去重：位置固定在 G6 之后、G8 之前，非法输入整批拒绝（任务 GET=0）。
    try:
        selected_task_ids = _controlled_task_ids(task_ids)
    except TalkToolError as exc:
        record_entry_failure("G7", str(exc), api_error=False)
    # G8 逐唯一 ID 各发恰好一次任务 GET：存在、对调用者可见、同项目、created_by==调用者，任一不符整批拒绝。
    # 核验通过的响应直接作为进入运行期后的**第一轮**任务集合，不重复 GET 同一批任务
    # （与旧实现“身份+项目+每轮任务 GET”的计数口径一致：全部通过=2+N）。
    verified_task_count = 0
    verified_tasks: list[JsonDict] = []
    total_task_ids = len(selected_task_ids)
    for position, task_id in enumerate(selected_task_ids, start=1):
        # 每个唯一 ID 发 GET 之前检查剩余预算；不足即按进入错误停止，绝不进入轮询。
        if remaining() <= 0:
            record_entry_failure(
                "G8",
                f"受控等待进入核验失败（G8）：任务核验进行到第 {position}/{total_task_ids} 个时剩余预算耗尽，"
                "未完成核验，按进入错误停止且不进入轮询",
                api_error=False,
            )
        try:
            task = _api_request(
                "GET",
                f"/api/tasks/{int(task_id)}",
                stats=stats,
                timeout=next_request_timeout(),
            )
        except TalkApiHttpError as exc:
            if exc.status == 404:
                # 404：不存在与对调用者不可见同形，按业务拒绝（return_reason=null），
                # 只回显调用者提交的 ID，不断言存在性、不泄露任务内容。
                record_entry_failure(
                    "G8",
                    f"受控等待进入核验失败（G8）：任务 {task_id} 不存在或对当前调用者不可见",
                    api_error=False,
                )
            record_entry_failure(
                "G8",
                f"受控等待进入核验失败（G8）：读取任务 {task_id} 时 TALK API 调用失败：{exc}",
                api_error=True,
            )
        except TalkToolError as exc:
            record_entry_failure(
                "G8",
                f"受控等待进入核验失败（G8）：读取任务 {task_id} 时 TALK API 调用失败：{exc}",
                api_error=True,
            )
        if not isinstance(task, dict):
            record_entry_failure(
                "G8",
                f"受控等待进入核验失败（G8）：任务 {task_id} 的响应不是任务对象，无法核验归属，整批拒绝",
                api_error=False,
            )
        if task.get("project_id") != effective_project_id:
            record_entry_failure(
                "G8",
                f"受控等待进入核验失败（G8）：任务 {task_id} 属于项目 {task.get('project_id')!r}，"
                f"不是当前项目 {effective_project_id}",
                api_error=False,
            )
        if task.get("created_by") != caller_member_id:
            record_entry_failure(
                "G8",
                f"受控等待进入核验失败（G8）：任务 {task_id} 的发起者（created_by）是 "
                f"{task.get('created_by')!r}，不是调用者 {caller_member_id}；"
                "target、角色、模型与终端都不是协调资格",
                api_error=False,
            )
        verified_task_count += 1
        verified_tasks.append(task)
    # G8 全部通过后才产生进入快照：只使用全部通过核验的事实（task_ids 来自调用者提交的合法去重列表）。
    entry_snapshot: JsonDict = {
        "requested_mode": mode["requested_mode"],
        "requested_version": mode["requested_version"],
        "caller_member_id": caller_member_id,
        "task_ids": list(selected_task_ids),
        "verified_task_count": verified_task_count,
    }

    def poll_round_tasks() -> list[JsonDict]:
        """运行期逐 ID 轮询：发每个请求前检查剩余预算，remaining <=0 抛内部信号。

        受控 true 的 task_ids 已经过 G7 严格校验且非空（D-3），因此这里不再有“无 ID 时按项目拉取”
        的分支；普通 false/省略路径的项目级轮询继续由 ``_wait_tasks_legacy`` 提供，行为不变。
        """
        collected: list[JsonDict] = []
        for task_id in selected_task_ids or []:
            if remaining() <= 0:
                raise _WaitBudgetExhausted
            collected.append(
                _api_request(
                    "GET",
                    f"/api/tasks/{int(task_id)}",
                    stats=stats,
                    timeout=next_request_timeout(),
                )
            )
        return collected

    def recheck_project() -> tuple[str | None, str]:
        """重读项目并比对进入快照：只关注模式字段存在性、模式值与版本；无变化返回 (None, "")。

        不再读取、不再比对主控指定字段：created_by 创建即固定，运行期无需复核任务归属，
        指定变化也不产生任何退出。
        """
        nonlocal rechecks, last_project_read
        reread = _api_request(
            "GET",
            f"/api/projects/{quote(effective_project_id, safe='')}",
            stats=stats,
            timeout=next_request_timeout(),
        )
        rechecks += 1
        last_project_read = _monotonic()
        current_mode = controller_mode_summary(reread if isinstance(reread, dict) else {})
        if not current_mode["supported"]:
            return "mode_changed", "重读时项目响应不再包含模式字段（旧服务或字段失效）"
        if current_mode["requested_mode"] != entry_snapshot["requested_mode"]:
            return (
                "mode_changed",
                f"模式意向从 {entry_snapshot['requested_mode']} 变为 {current_mode['requested_mode']}",
            )
        if current_mode["requested_version"] != entry_snapshot["requested_version"]:
            return (
                "mode_changed",
                f"模式版本从 {entry_snapshot['requested_version']} 变为 "
                f"{current_mode['requested_version']}",
            )
        return None, ""

    def finish(
        *,
        timed_out: bool,
        reason: str,
        polled: list[JsonDict],
        matched: list[JsonDict],
        exit_detail: str = "",
    ) -> JsonDict:
        elapsed = max(0.0, _monotonic() - started_monotonic)
        payload = _wait_payload(
            timed_out=timed_out,
            reason=reason,
            polled=polled,
            matched=matched,
            desired=desired,
            effective_project_id=effective_project_id,
            selected_task_ids=selected_task_ids,
            requested_timeout=requested_timeout,
            effective_timeout=effective_timeout,
            elapsed=elapsed,
            poll_rounds=poll_rounds,
            stats=stats,
            controlled=True,
            controlled_entry=entry_snapshot,
            controlled_rechecks=rechecks,
        )
        returned_count = len(payload["tasks"])
        omitted_count = payload["tasks_omitted_count"]
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
                "tasks_returned": returned_count,
                "tasks_truncated": bool(omitted_count),
                "tasks_omitted_count": omitted_count,
                "controlled_wait": True,
                "controlled_rechecks": rechecks,
                "controlled_entry": entry_snapshot,
                "exit_detail": exit_detail or None,
            }
        )
        return payload

    def fail_as_api_error(exc: TalkToolError, *, stage: str) -> None:
        """运行期 API 错误统一出口：任务轮询节点与 30 秒重读节点共用同一形态。

        - 与进入期门禁失败不同，这里是“等待已经启动”之后的运行期错误：落且只落一条
          ``return_reason=api_error`` 的 ``talk_wait_tasks`` 统计记录，带真实 elapsed 与轮询轮次；
        - 每个失败节点只在 except 里调用一次，随即抛错终止等待，不会重复落盘或重复计数；
        - 失败的 GET 尝试由 ``_api_request`` 在发请求前计入 ``stats['http_requests']``（只计一次）；
        - 异常形态与 #156 的任务轮询路径逐字一致（仅多一条 JSONL 专属 ``failure_stage`` 标注），
          不重试、不降级成 timeout/matched、不写任务、不泄露密钥，只把上游错误原文作为原因。
        """
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
                "controlled_wait": True,
                "controlled_rechecks": rechecks,
                "controlled_entry": entry_snapshot,
                # JSONL 专属可追溯信息（不进返回结构）：本次失败发生在哪个节点。
                "failure_stage": stage,
                "error": str(exc),
            }
        )
        raise TalkToolError(
            "受控等待期间 TALK API 调用失败（按 api_error 显式报错，不伪装成正常 timeout，"
            f"也不伪装成 matched）：{exc}；已等待 {elapsed:.1f} 秒，轮询 {poll_rounds} 次"
        ) from exc

    # 运行期第一轮复用 G8 核验响应；之后每轮按 task_ids 逐 ID 重新 GET。
    pending_tasks: list[JsonDict] | None = verified_tasks
    while True:
        poll_rounds += 1
        if pending_tasks is not None:
            # 第一轮直接复用 G8 已核验的响应：同一批任务不在进入后立刻重复 GET。
            tasks = pending_tasks
            pending_tasks = None
        else:
            try:
                tasks = poll_round_tasks()
            except _WaitBudgetExhausted:
                # R5：预算耗尽且未发出下一个请求 → 正常 timeout，返回最近一次成功完成的轮询集合
                # （从未完成过任务轮询时为 tasks=[] / task_count=0）。
                return finish(
                    timed_out=True,
                    reason="timeout",
                    polled=last_polled,
                    matched=[],
                    exit_detail="剩余预算不足，未再发出请求；返回最近一次成功完成的轮询集合",
                )
            except TalkToolError as exc:
                fail_as_api_error(exc, stage="poll")
        last_polled = tasks
        matched = [
            task for task in tasks if str(task.get("workflow_status") or "") in desired
        ]
        # 固定检查顺序：任务命中（matched 优先）→ 30 秒模式重读 → deadline → sleep。
        if matched:
            return finish(timed_out=False, reason="matched", polled=tasks, matched=matched)
        if (
            remaining() > 0
            and _monotonic() - last_project_read >= CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS
        ):
            try:
                changed_reason, change_detail = recheck_project()
            except TalkToolError as exc:
                # F-1：重读节点的项目 GET 失败与任务轮询失败同形处理——显式 api_error、
                # 带真实 elapsed/rounds、恰好一条统计记录，不重试也不降级。
                fail_as_api_error(exc, stage="recheck")
            if changed_reason is not None:
                return finish(
                    timed_out=False,
                    reason=changed_reason,
                    polled=tasks,
                    matched=[],
                    exit_detail=change_detail,
                )
        if remaining() <= 0:
            return finish(
                timed_out=True,
                reason="timeout",
                polled=tasks,
                matched=[],
                exit_detail="deadline 耗尽，未再发出请求",
            )
        sleep_seconds = min(poll_interval, max(0.0, remaining()))
        _sleep(sleep_seconds)
        poll_interval = min(poll_interval * 2, WAIT_MAX_POLL_INTERVAL_SECONDS)


def wait_tasks(
    *,
    task_ids: list[int] | None = None,
    workflow_statuses: list[str] | None = None,
    project_id: str | None = None,
    timeout_seconds: float = WAIT_TIMEOUT_UNSET,
    controlled_wait: bool = False,
) -> JsonDict:
    """有界等待任务进入目标协作状态。

    - 默认（``controlled_wait`` 省略或 false）：与旧路径逐字段一致——最长/默认 600 秒、超出上限按
      600 秒生效并标注请求值，不发身份 GET、不做项目重读、返回结构无新字段。
    - ``controlled_wait=true`` 是显式 opt-in 的受控等待：必须先通过 G1–G8 进入门禁（G1 项目上下文、
      G2 显式有限正数 timeout_seconds、G3 按 API Key 反查的 agent 身份、G4 human 凭据拒绝、
      G5 服务端返回模式字段、G6 requested_mode=active、G7 显式非空严格正整数 task_ids 稳定去重、
      G8 逐唯一 ID 核验存在/可见/同项目/created_by==调用者），任一不满足直接报错、不轮询、不降级，
      也不等待合法子集。协调资格只依据任务 created_by（任务发起者归属），target/角色/模型/终端与
      旧的主控指定都不是资格。
    - 受控路径进入后记录 ``{requested_mode, requested_version, caller_member_id, task_ids,
      verified_task_count}`` 快照，每 30 秒只重读项目模式字段一次；模式值/版本变化或字段失效返回
      ``mode_changed``；受控路径的 ``return_reason`` 只可能是 matched / timeout / mode_changed
      （``controller_changed`` 已随固定主控退役），API 错误照旧显式抛错（api_error），不新增 cancelled。
    - 成果提交（submitted）、完成（completed）、失败（failed）、需澄清
      （clarification_requested 等）等状态一旦出现立即返回，不等满超时。
    - 等待全部由程序轮询完成，等待期间不产生新的模型回合、也不经工具分发新增 get/list
      调用（实现声明，非计数）；但本工具无法保证宿主外层零回合。
    - tasks 与成果只回传引用字段（id / hall_group_id / result_message_id 等）和状态，
      不回传任务正文、消息历史或实例历史；提前返回时 tasks 即命中集合（兼容原契约），
      超时返回时是最近一次轮询到的任务，两者最多 WAIT_MAX_TASK_REFERENCES 条，超出部分以
      tasks_truncated / tasks_omitted_count / omitted_task_ids 标记，matched_task_ids 完整。
    - TALK API 错误（含 4xx/5xx/网络错误/单次请求超时）直接抛出错误，绝不复用超时返回结构；
      受控路径连接受阻或响应读取阶段超时同样按 api_error 报错，不伪装成正常 timeout。
    - 同步阻塞：客户端取消不会立即终止程序侧等待（仍会跑到命中或超时截止），Windows 下
      客户端进程退出不保证带走 MCP 子进程；等待全程只读，不改变任务状态、不取消在途任务、不收取。
    - query_stats 给出本次调用的程序级实测计数（轮询轮次、HTTP 请求数、耗时、返回原因）；
      受控路径把身份 GET、项目 GET、G8 逐任务核验 GET、每 30 秒重读 GET 与任务轮询 GET
      （含失败尝试）全部计入。
    """
    controlled = _normalize_controlled_wait(controlled_wait)
    if controlled:
        return _wait_tasks_controlled(
            task_ids=task_ids,
            workflow_statuses=workflow_statuses,
            project_id=project_id,
            timeout_seconds=timeout_seconds,
        )
    return _wait_tasks_legacy(
        task_ids=task_ids,
        workflow_statuses=workflow_statuses,
        project_id=project_id,
        timeout_seconds=timeout_seconds,
    )


TOOL_SCHEMAS: list[JsonDict] = [
    {
        "name": "talk_list_agents",
        "description": (
            "列出当前项目可委派的 Agent 及其最新实例状态。返回有界摘要："
            "每个角色最多一个按 last_seen_at 取最新的实例，且只含 "
            "id / runtime / status / current_task_id / last_seen_at / pid，"
            "不返回历史实例、last_error 或既有 CLI 日志。"
            "顶层同时返回项目级最新开发要求 development_requirements（角色清单只出现一次，"
            "不重复写进每个 Agent；无内容时为 null）：任务发起者派发新任务前应先读取它与角色清单，"
            "再按该要求派发。"
            "顶层还返回只读的 controller_mode（与开发要求复用同一次项目读取）："
            "requested_mode / requested_version 是项目保存的模式意向与版本，"
            "effective_mode 恒为 null、effective_status=not_bound，表示本版本没有发起者会话绑定或"
            "生效确认。保存 active 不等于已生效、不等于已唤回任何会话，也不授权自动等待、调度、"
            "派发或推进；默认协作仍是派发后结束、由用户通知后再取件，不得据此字段声称已唤回会话。"
            "非项目路径 controller_mode 为 null；旧后端缺模式字段时为 supported=false / "
            "effective_status=unsupported，不能当成 passive 或已支持。"
            "顶层还返回只读的 controller_assignment（同样复用这一次项目读取）："
            "**该字段已弃用，不再决定任何协调或调度，也不产生任何权限**。"
            "member_id / version 是项目历史保存的主控指定与独立版本，status 是服务端按当前名册与"
            "成员事实算出的配置有效性（unassigned / assigned / not_in_roster / member_disabled / "
            "member_missing / not_agent）。assigned 只表示该成员已注册、未禁用、在该项目名册中且为 "
            "agent，**不代表在线、已确认(ACK)、会话已生效或获得任何额外权限**；本版本没有会话 "
            "token、租约、心跳或后台线程，指定不自动唤醒进程，也不改变派发/领取/完成/收取权限。"
            "协调资格只依据具体任务的 created_by（任务发起者归属），受控等待既不读取也不比对"
            "该指定；无效状态不会自动解除或转给他人，仍由 human 显式清空；只有 human 能写入该指定，"
            "agent 侧为只读。字段形状与旧后端降级行为保持不变，供旧消费者如实降级。"
            "非项目路径 controller_assignment 为 null；旧后端缺字段时为 "
            "supported=false / status=unsupported，不能当成未指定或已指定。"
            "顶层还返回 caller_identity（项目路径新增一次 GET /api/members/me，按 API Key 反查，"
            "不使用 TALK_MEMBER_ID、模型名或会话标签自证）：固定三键 {member_id, kind, note}，"
            "成功时 member_id / kind 来自服务端响应且 note=null；获取失败或响应缺合法 id/kind 时"
            "member_id 与 kind 均为 null 并给出简短中文 note，且该失败不阻断角色清单。"
            "非项目路径 caller_identity 为 null，不额外发身份请求。caller_identity 只是如实披露入口"
            "身份，自身不构成权限，也不代表在线、已确认或已获授权。"
            "availability 仅依据实例上报，未做心跳核验，可能滞后，使用时请参考 last_seen_at。"
            "每个角色还返回只读的 binding 与 binding_state，取自已有的同一次项目角色读取响应"
            "（不新增绑定请求、不新增工具或参数）：binding 只透传 B1a 公开绑定字段"
            "（runner_id / runtime / runner_display_name / runner_status / model_source / provider_id / "
            "connection_ref / model_id / model_alias / model_display_name / binding_state / "
            "binding_fingerprint / updated_by / updated_at），没有存储行时为 null；"
            "binding_state 是服务器读取时实测的状态：未配置为 unconfigured，另有 partial / "
            "runner_missing / runner_retired 等保留配置或异常状态，只有全部通过才是 bound，"
            "不得把异常状态当成 bound。旧后端缺这两个键时两者均为 null，不得猜成 unconfigured 或 "
            "bound；非项目路径两者均为 null。connection_ref 只是不透明连接标识，本工具不解析、"
            "不执行、不探测，也不透传凭据、凭据路径或实例日志。binding 只是派发配置事实："
            "不代表运行器在线、已适配主动等待或能按任务切换模型，也不代表实际使用的模型与配置一致；"
            "本版本不输出任何实际匹配（binding_match*）结论。"
            "project_id 省略时使用 bridge 项目上下文。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
        },
    },
    {
        "name": "talk_delegate_task",
        "description": (
            "向指定 Agent 创建项目化任务并自动建立独立 Task Hall。"
            "派发前先读取所解析项目当前的最新开发要求（可先用 talk_list_agents 查看），"
            "创建新任务时把非空要求以“项目开发要求（派发时快照）”区块写入所存任务正文，"
            "并保留调用者原始 content；要求为空时正文与旧行为一致。"
            "该快照只是随任务包保存的文本：不解析、不执行、不自动授予权限、不覆盖宿主系统指令，"
            "已创建任务不因项目要求后续修改而追溯变更。"
        ),
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
            "客户端单工具超时必须大于最长等待，建议 >= 660 秒（本工具读不到宿主客户端预算，"
            "唯一强制上限是 600 秒 clamp）。"
            "受控等待是显式 opt-in 参数 controlled_wait（默认 false，缺省/ false 时与旧行为逐字段一致，"
            "不产生身份 GET、不做项目重读、返回结构无新字段）：true 时必须通过 G1–G8 进入门禁"
            "（G1 项目上下文 / G2 显式有限正数 timeout_seconds（bool、非数值、NaN、inf、0、负值一律拒绝，"
            "不采用 600 默认值）/ G3 按 API Key 反查的 agent 身份 / G4 human 凭据拒绝 / "
            "G5 服务端返回模式字段（缺字段=不支持，不猜 passive 或 active）/ "
            "G6 requested_mode=active（用 G5 同一次项目响应判定，零新增请求；passive 时零任务 GET）/ "
            "G7 显式非空 task_ids 且元素全为严格正整数（bool、浮点含 1.0、字符串、null、0、负整数整批拒绝，"
            "全部合法后按首次出现顺序稳定去重）/ G8 按去重顺序逐唯一 ID 各发恰好一次 GET，"
            "核验任务存在、对调用者可见、属于本项目且 created_by=调用者，任一不符整批拒绝、不等待合法子集），"
            "任一不满足直接报错，不轮询、不静默降级为普通等待。协调资格只依据任务 created_by"
            "（任务发起者归属）：target、业务角色、模型名、终端名与旧的主控指定都不是协调资格，"
            "旧指定字段缺失/无效/变化也不影响门禁或退出。门禁通过后返回快照 controlled_entry="
            "{requested_mode, requested_version, caller_member_id, task_ids, verified_task_count}，"
            "先查任务命中（matched 优先），再按 30 秒节奏重读项目模式字段：模式值变化/版本变化/字段失效"
            "返回 mode_changed；运行期只按模式字段判定退出，不再读取或比对旧主控指定；预算耗尽返回 timeout。"
            "受控路径的单次 deadline 从开始核验起算，覆盖身份 GET、项目 GET、G8 核验 GET、轮询 GET、"
            "重读 GET 与 sleep：发任何 HTTP 前剩余预算 <=0 就不再发请求并按 timeout 返回最近一次成功完成的"
            "轮询集合（从未完成轮询则 tasks=[]、task_count=0），否则该请求超时取 min(10 秒, 剩余预算)；"
            "G8 核验途中剩余预算耗尽按进入错误停止，"
            "不进入轮询。受控路径的连接受阻、响应头/响应体读取阶段超时与网络 OSError 一律归一为 "
            "TalkToolError（api_error），不伪装成正常 timeout，也不伪装成 matched；G8 的任务 404 是业务拒绝"
            "（return_reason=null，措辞只说“不存在或对当前调用者不可见”并回显调用者提交的 ID，"
            "不泄露任务存在性或内容）；其它 HTTP/网络失败按 api_error。"
            "socket 单请求超时不等于任意慢速响应的端到端硬中断。"
            "受控路径的身份/项目/G8 核验/重读/轮询 GET（含失败尝试）全部计入 query_stats.http_requests，"
            "并只额外返回 controlled_wait / controlled_entry / controlled_rechecks 三个字段。"
            f"受控预算需调用方自行匹配宿主客户端预算（预留 {WAIT_CLIENT_MARGIN_SECONDS:.0f} 秒余量，"
            "桌面 65 秒上限时建议 <=60 秒）。身份门禁只是桥内 advisory 自我保护，不代表在线、"
            "不代表已获授权，也不替代服务端权限；matched 只表示任务命中，不表示仍具备 active 资格。"
            "受控等待不修改任务状态、不取消在途任务、不重复收取，也不伪造 effective_mode 或调度互斥；"
            "本版本没有客户端取消检测源，取消消息在等待期间读不到，也不新增 cancelled 返回原因；"
            "等待占用同一条 MCP stdio 连接，期间其它工具调用排队。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "要跟进的任务 ID。非受控路径沿用旧归一化（字符串/浮点可被转换、重复静默去重）；"
                        "controlled_wait=true 时改为严格语义：必须显式提供、非空，元素必须是严格正整数"
                        "（bool/浮点含 1.0/字符串/null/0/负数整批拒绝），全部合法后按首次出现顺序稳定去重。"
                    ),
                },
                "workflow_statuses": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": WAIT_MAX_TIMEOUT_SECONDS,
                    "default": WAIT_DEFAULT_TIMEOUT_SECONDS,
                    "description": (
                        "等待预算（秒）。非受控路径：省略即 600，负数归零，超过 600 按 600 生效。"
                        "controlled_wait=true 时必须显式传入有限正数（bool、非数值、NaN、inf、0、负值"
                        "直接报错，不采用 600 默认值）；超过 600 时按既有上限 clamp 到 600 生效，"
                        "与旧 clamp 行为一致。"
                    ),
                },
                "controlled_wait": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "显式 opt-in 的受控等待开关（默认 false）。true 时先走 G1–G8 进入门禁"
                        "（含显式非空严格正整数 task_ids 与逐任务 created_by 归属核验）并启用 "
                        "30 秒模式重读与单次 deadline 记账；false/省略时行为与旧路径完全一致，"
                        "task_ids 仍是旧的宽松归一化语义。"
                    ),
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
            "summary 模式（默认）按 task_id 定位结果消息，返回**默认不做机械裁剪**的完整摘要："
            "task_ref / runner_status（runner 状态与协作状态）/ delivery_conclusion（业务结论，"
            "只来自结果消息中通过本地 talk-delivery-1 校验、且**自身 task_id 与本任务号一致**"
            "的结构化自报，delivery_conclusion.task_id_check 会如实回显 declared/expected/matches；"
            "自由文本、无效结构化报告或错号自报一律 unknown / invalid，绝不从 succeeded 或正文词汇"
            "推断 complete）/ counts / preview（阻塞优先）/ summary_text / limits / read_more。"
            "合法结构化交付的必要字段与全部条目均按原文完整返回，不丢列表后项、不切字符串尾部、"
            "不用省略号替代；但必要内容在同一响应里只出现一次、由两个载体分工承载："
            "阻塞 / 未完成 / 已完成三类明细原文只在 preview.<区块>.items（含 total/shown/omitted），"
            "summary_text 只给任务号、业务结论、计数与清楚的 preview 定位提示，"
            "外加 preview 未承载的必要内容（验证结果与证据、限制、下一步、变更文件、基线）。"
            "因此**完整摘要 = 同一响应中的核心字段整体，不能只读 summary_text**。"
            "limits.text_limit_chars / limits.json_limit_chars 为 null 表示默认未启用长度上限，"
            "此时 limits.text_truncated=false、preview.<区块>.omitted=0、read_more.omitted=[]，"
            "summary_text 里也不会出现 [摘要截断]；显式限长时 text_truncated 只按 summary_text 是否"
            "真的被裁剪取值、json_truncated 只按 JSON 预算取值，两者分别如实反映，"
            "省略项在 read_more.omitted 里以 source=preview / source=summary_text 区分。"
            "自由文本旧结果不做结论推断，只给 unknown + 明确标记 truncated 的有界原文预览（≤300 字符）"
            "与 detail 补读入口，既不把巨大旧正文塞进默认结果，也不把短预览说成完整摘要；"
            "64 KiB 等超规格输入是**明确拒收**的保护，不转成静默截断。"
            "detail 模式必须提供 result_message_id（取自 summary），按 offset / limit 分页读取"
            f"完整结果原文（单页上限 {DELIVERY_DETAIL_MAX_PAGE_CHARS} 字符），"
            "或用 fields 指定 talk-delivery-1 顶层字段读取结构化值；按 offset 顺序拼接各页可无损重建完整结果；"
            "该分页属于按需补读，不属于摘要裁剪。"
            "fields 只接受通过校验且 task_id 与本任务号一致的结构化自报，错号时返回 unavailable，"
            "但按 result_message_id 读取完整原文始终不受该核对影响。"
            "结果引用变化（result_message_id 改变，或 expect_sha256 与当前内容不一致）时返回 "
            "status=stale_reference 并要求从 offset=0 重新开始，绝不把两份结果拼在一起。"
            "本工具完全只读：不自动 collect / accept，不改变任务状态，不扫描整个 Hall 历史，"
            "也不按结果正文里的路径读取本机文件；runner 结束不等于用户目标完成。"
            "摘要仍只是执行者自报的索引，不代表独立验收通过。"
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
            controlled_wait=arguments.get("controlled_wait"),
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
