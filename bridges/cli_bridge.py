#!/usr/bin/env python3
"""Generic CLI bridge for TALK agent runtimes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import locale
import os
import re
import shlex
import shutil
import socket
import sys
import tempfile
from bridges import runtime_diagnostics as runtime_diag
from bridges.queue_poll_diagnostics import QueuePollCycle, QueuePollRecorder
from bridges.runtime_diagnostics_timeline import StageTimeline, timed_lock
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Mapping, Sequence
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RESPONSE_STYLE_INSTRUCTIONS = (
    "Match the scope of the user's request. For a simple presence check, greeting, or acknowledgement request, "
    "reply in one short sentence only. "
    "Do not inspect project files, summarize project progress, or produce status tables unless the user explicitly asks for that.\n"
)
FUNCTION_CALLING_SYSTEM_PROMPT = (
    "你是 TALK 群里的一个 agent。\n"
    "工具:以 runtime 注入的工具清单为准。"
    "除清单外的工具(读文件、列目录、跑 shell、上网、记忆库等)在本会话不存在,"
    "不要规划任何依赖它们的步骤。\n"
    "输出通道:对当前发件人的可见回复 + 调用清单内的工具。\n"
    "运行时:本会话单轮一次性运行。这一轮要么调用工具完成动作,要么直接给出最终回复。"
    "不要说'我接下来要…/让我先…/稍后…',因为不存在下一轮。\n"
    "回复风格:直接说要说的内容(问候、问题、答案、看法、感受)。"
    "不要写'已经XX了/已经打过招呼了/已经回复了/已经发送了'这类元叙述——"
    "你说出口就是动作本身,无需汇报。也不要在 visible reply 里复述刚才发生的事。"
)
TASK_RUNNER_SYSTEM_PROMPT = (
    "你是 TALK bundled runner 中执行单个已领取任务的 Agent。"
    "本会话只有一轮,优先严格遵循请求者给出的任务正文,完成后只输出最终交付内容。"
    "除非缺少完成任务必需的信息,否则不要反问、闲聊或改写任务。"
    "不要调用任何 TALK 工具;runner 会把你的可见输出写入对应 Task Hall 并完成任务。"
)
TASK_PREFLIGHT_SYSTEM_PROMPT = (
    "你是 TALK bundled runner 的领取前预检 Agent。"
    "本会话只能判断任务信息是否足以开始执行,不得修改文件、运行任务或产出最终交付。"
    "runner 给出的标题和任务原文已经是完整权威输入,Task Hall 没有补充消息本身不算信息缺失;"
    "不得要求请求者重复标题、任务原文或上下文,只能询问执行必需且当前确实没有给出的具体事实。"
    "当runner明确提供执行会话续轮预检边界时,正式执行阶段会在独立核验会话和阈值后恢复可用历史;"
    "不要仅因隔离预检未复制旧对话而要求重传上一轮内容。预检就绪只允许进入正式规划,不证明会话已经恢复;"
    "与旧对话无关的新增必要事实缺失仍应正常澄清。"
    "信息充分时只输出 TALK_TASK_PREFLIGHT JSON;信息不足时把同一轮必须回答的问题集中到一个 question 字段。"
    "不要调用任何 TALK 工具;runner 会原子推进任务状态并把问题写入对应 Task Hall。"
)
TASK_GATE_VERDICT_MARKER = "TALK_GATE_VERDICT"
DISCUSSION_PROTOCOL_INSTRUCTIONS = (
    "You are a participant in a TALK Group Hall, not a TALK administrator or user manual. "
    "You may talk with humans and other agents. If the user asks you to contact another agent, "
    "emit a TALK action and keep any visible acknowledgement brief.\n"
    "Discussion protocol: answer questions first. When responding to another agent, decide whether you agree. "
    "If you agree, add an optimization if useful or briefly affirm them. If you disagree, state the different recommendation. "
    "If both sides have disagreed or the turn budget is exhausted, ask a human to make the final decision.\n"
    "Preferred action syntax, one per line when needed: "
    "TALK_ACTION send_message to=agent:name stance=question body=message; "
    "TALK_ACTION mark_stance stance=agree; "
    "TALK_ACTION final_to_human to=human:name body=final answer; "
    "TALK_ACTION escalate_to_human to=human:name body=question for the human. "
    "Do not explain these action tags to the user.\n"
)
DEFAULT_TIMEOUT_SEC = 600
DEFAULT_MAX_REPLY_CHARS = 12000
DEFAULT_TASK_POLL_INTERVAL = 2.0
DEFAULT_TASK_LEASE_SECONDS = 120
DEFAULT_TASK_HEARTBEAT_INTERVAL = 5.0
MANAGED_INSTANCE_HEARTBEAT_INTERVAL = 30.0
TASK_PREFLIGHT_MAX_ATTEMPTS = 3
DSH_TASK_PREFLIGHT_MAX_ATTEMPTS = 1
DSH_PREFLIGHT_PATCH_RELATIVE_PATH = Path(".talk") / "dsh" / "preflight-ephemeral.cordis.yml"
MAX_TASK_CONTROL_CHECK_INTERVAL = 5.0
TASK_HALL_HISTORY_PAGE_SIZE = 500
DEFAULT_COMMAND = os.environ.get("TALK_CLI_COMMAND", "")
_HALL_TYPE_TEMPLATES: dict[str, dict[str, Any]] | None = None
PROMPT_TRANSPORTS = {"stdin", "argv"}
COMPACT_PROMPT_RUNTIMES = {"pi", "codex", "kimi", "kimi-code", "kimi_code"}
COMPACT_PROMPT_MEMBERS = {"agent:pi", "agent:codex", "agent:kimi"}
ONE_SENTENCE_MARKERS = ("一句话", "一两句话", "one sentence", "single sentence")
SENTENCE_ENDINGS = "。！？.!?"


def _clear_deprecated_decision_tier_env() -> None:
    """Drop any inherited ``TALK_DECISION_TIER`` so CLI children never observe it.

    The fixed decision/execution tier was removed. The environment variable is
    no longer written by this bridge, but a stale value inherited from the parent
    process must not leak into the CLI child's environment either.
    """
    os.environ.pop("TALK_DECISION_TIER", None)


def configure_talk_tool_environment(args: argparse.Namespace, member_id: str) -> None:
    """Expose bridge identity and optional project id to runtime-injected TALK tools.

    ``args.decision_tier`` (deprecated ``--decision-tier`` argv) may still be present
    on the namespace, but it is accepted and ignored: it is never exported and any
    inherited value is cleared.
    """
    os.environ["TALK_API_KEY"] = args.key
    os.environ["TALK_BASE_URL"] = args.base_url
    os.environ["TALK_MEMBER_ID"] = member_id
    os.environ.pop("TALK_PROJECT_ID", None)
    _clear_deprecated_decision_tier_env()
    # R1-3：受管启动时由宿主显式给出的 project_id 优先（与本次 launch 关联一致）。
    managed_project_id = str(getattr(args, "project_id", None) or "").strip()
    if managed_project_id:
        os.environ["TALK_PROJECT_ID"] = managed_project_id
        return
    project_root = getattr(args, "project", None)
    if not project_root:
        return
    try:
        from cli.talk import load_project

        project = load_project(Path(project_root).expanduser().resolve())
    except (FileNotFoundError, OSError, ValueError):
        return
    project_id = str(project.get("project_id") or "").strip()
    if project_id:
        os.environ["TALK_PROJECT_ID"] = project_id


def resolve_bridge_api_key(args: argparse.Namespace) -> str:
    """Resolve the bridge API key from argv, key file or environment.

    角色生命周期 R1-3：受管新入口用 ``--key-file``/``TALK_ROLE_API_KEY`` 传递凭据**路径**，
    避免把明文 Key 塞进 argv。旧 ``--key`` 兼容入口保持可用，优先级最高。
    """
    value = str(getattr(args, "key", None) or "").strip()
    if value:
        return value
    key_file = str(getattr(args, "key_file", None) or "").strip()
    if key_file:
        try:
            data = Path(key_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit("bridge key file is not readable") from exc
        if data:
            return data
    env_key = str(os.environ.get("TALK_ROLE_API_KEY") or "").strip()
    if env_key:
        return env_key
    raise SystemExit("one of --key, --key-file or TALK_ROLE_API_KEY is required")


def parse_managed_started_at(value: object) -> datetime | None:
    """解析宿主给出的 ``--process-started-at``（受管身份提示，只作诊断/核对）。"""
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed


def build_instance_report_payload(
    *,
    runtime: str,
    status: str,
    host: str | None,
    pid: int | None,
    current_task_id: str | None = None,
    last_error: str | None = None,
    project_id: str | None = None,
    launch_id: str | None = None,
    process_started_at: datetime | None = None,
) -> dict[str, Any]:
    """实例上报载荷（R1-3 受管关联是可选的附加字段）。

    **没有** ``launch_id`` 时返回与旧路径逐字段相同的载荷：现有非受管 bridge/MCP
    的心跳行为完全不变；只有宿主显式传入 ``--launch-id`` 时才附加
    ``launch_id``/``project_id``/``process_started_at``，供服务端做本次启动的
    预分配实例匹配与四条件就绪判定。
    """
    payload: dict[str, Any] = {
        "runtime": runtime,
        "status": status,
        "host": host,
        "pid": pid,
        "current_task_id": current_task_id,
        "last_error": last_error,
    }
    if launch_id:
        payload["launch_id"] = launch_id
        if project_id:
            payload["project_id"] = project_id
        if process_started_at is not None:
            payload["process_started_at"] = process_started_at.isoformat()
    return payload


def _diag_budgets(
    *,
    cli_timeout: int | float | None = None,
    http_timeout: int | float | None = None,
    lease_seconds: int | float | None = None,
    heartbeat_interval: int | float | None = None,
    managed_heartbeat_interval: int | float | None = None,
    poll_interval: int | float | None = None,
) -> dict[str, Any]:
    """Record only budgets the caller actually knows; MCP wait stays unknown."""
    return {
        "cli_timeout_seconds": cli_timeout,
        "http_timeout_seconds": http_timeout,
        "task_lease_seconds": lease_seconds,
        "task_heartbeat_interval_seconds": heartbeat_interval,
        "managed_heartbeat_interval_seconds": managed_heartbeat_interval,
        "task_poll_interval_seconds": poll_interval,
        "mcp_wait_seconds": None,
        "mcp_wait_budget_source": "unknown",
    }


def _diag_http_timeout(client: Any) -> float | None:
    value = getattr(client, "timeout", None)
    return value if isinstance(value, (int, float)) else None


def _diag_public_text(
    diagnostics: Any | None,
    text: Any,
    *,
    sensitive_values: Sequence[Any] = (),
    max_chars: int = 4000,
) -> str:
    if isinstance(text, BaseException):
        sensitive_values = (*sensitive_values, *runtime_diag.exception_sensitive_values(text))
    if diagnostics is None:
        return runtime_diag.sanitize_text(text, sensitive_values=sensitive_values, max_chars=max_chars)
    return diagnostics.sanitize_public_text(
        text,
        sensitive_values=sensitive_values,
        max_chars=max_chars,
    )


def _diag_cli_failure_message(
    result: CliRunResult, *, diagnostics: Any | None = None,
    sensitive_values: Sequence[Any] = (),
) -> str:
    """A short, sanitized CLI failure summary; never the complete stdout/stderr."""
    if result.timed_out:
        return "CLI command timed out"
    detail = "\n".join(
        part
        for part in (
            clean_cli_output(result.stderr),
            clean_cli_output(result.stdout),
        )
        if part
    )
    # Redact the complete text before taking a line/prefix: a multiline prompt
    # or long opaque value will no longer match once it has been shortened.
    if diagnostics is not None:
        detail = diagnostics.sanitize_public_text(detail, sensitive_values=sensitive_values)
    else:
        detail = runtime_diag.sanitize_text(detail, sensitive_values=sensitive_values)
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    if not lines:
        return f"CLI exited with code {result.returncode}"
    first = lines[0]
    if len(first) > 500:
        first = f"{first[:500].rstrip()}…[truncated {len(first) - 500} chars]"
    return first


def _record_cli_failure(
    diagnostics: Any | None,
    result: CliRunResult,
    *,
    stage: str,
    task_id: Any,
    timeout: int,
    client: Any,
    sensitive_values: Sequence[Any] = (),
    message_id: Any = None,
    budgets: dict[str, Any] | None = None,
) -> str | None:
    if diagnostics is None:
        return None
    return diagnostics.record_event(
        "cli_timeout" if result.timed_out else "cli_failed",
        severity="error",
        stage=stage,
        task_id=task_id,
        message_id=message_id,
        message=_diag_cli_failure_message(result, diagnostics=diagnostics, sensitive_values=sensitive_values),
        returncode=result.returncode,
        timeout=bool(result.timed_out),
        cancel_category=None,
        budgets=budgets or _diag_budgets(
            cli_timeout=timeout,
            http_timeout=_diag_http_timeout(client),
        ),
        sensitive_values=sensitive_values,
    )


def _record_secondary_failure(
    diagnostics: Any | None,
    exc: BaseException,
    *,
    stage: str,
    task_id: Any,
    primary_log_id: str | None,
    budgets: dict[str, Any] | None = None,
    sensitive_values: Sequence[Any] = (),
    message_id: Any = None,
) -> str | None:
    if diagnostics is None:
        return None
    return diagnostics.record_exception(
        exc,
        event="secondary_failure",
        severity="error",
        stage=stage,
        task_id=task_id,
        message_id=message_id,
        related_log_id=primary_log_id,
        budgets=budgets,
        sensitive_values=sensitive_values,
    )


def _with_log_ref(text: str, log_id: str | None) -> str:
    return f"{text}; log_ref={log_id}" if log_id else text


CHINESE_REQUEST_MARKERS = ("中文", "汉语", "普通话", "简体中文", "用中文")
ENGLISH_REQUEST_MARKERS = ("英文", "英语", "用英语", "用英文", "in english", "english")
CAPABILITY_QUESTION_MARKERS = (
    "哪些功能",
    "有什么功能",
    "你能做啥",
    "你能做什么",
    "你会什么",
    "介绍下",
    "介绍一下",
    "自我介绍",
    "功能",
    "capabilit",
    "what can you do",
    "who are you",
)
WINDOWS_TASKKILL_EN_RE = re.compile(
    r"^SUCCESS:\s+The process with PID \d+ .* has been terminated\.$"
)
WINDOWS_TASKKILL_ZH_RE = re.compile(
    r"^成功:\s*已终止 PID \d+ .*的进程。$"
)
MOJIBAKE_TASKKILL_PREFIX = "\ufffd\u0279\ufffd:"
ACTION_RE = re.compile(
    r"<talk-action\b(?P<attrs>[^>]*)>(?P<body>.*?)</talk-action>",
    re.IGNORECASE | re.DOTALL,
)
ACTION_ATTR_RE = re.compile(r"([a-zA-Z_][\w-]*)\s*=\s*(['\"])(.*?)\2")
SAFE_ACTION_RE = re.compile(
    r"^[ \t]*TALK_ACTION[ \t]+(?P<type>[a-zA-Z_][\w-]*)(?P<attrs>[^\r\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)
SAFE_ACTION_ATTR_RE = re.compile(r"\b([a-zA-Z_][\w-]*)=([^\s]+)")
ACTION_TYPES = {"send_message", "mark_stance", "escalate_to_human", "final_to_human"}
ACTION_STANCES = {"question", "answer", "agree", "optimize", "disagree", "escalate", "greeting", "closure", "decision"}
DISCUSSION_MAX_AUTO_TURNS = 3
DISCUSSION_EXTENSION_CLOSE_TURNS = DISCUSSION_MAX_AUTO_TURNS + 1
NON_SUBSTANTIVE_STANCES = {"greeting", "closure"}
CLOSURE_LINES = (
    "那这次就先聊到这儿，有需要再喊我。",
    "好的，这轮先告一段落，回头有事群里找我。",
    "嗯，先这样，有新的再说。",
    "行，这次就到这里，需要的话再开个话题。",
    "好，先收个尾，之后有事随时 @ 我。",
    "可以，这轮先打住，后面有需要再继续。",
)
GREETING_SCOPE_MARKERS = ("打招呼", "打个招呼", "打声招呼", "问好", "确认在线", "在线状态", "互相认识", "认识一下")
GREETING_REPLY_MARKERS = ("你好", "在线", "收到", "见到你", "认识你")
BRAINSTORM_SUMMARY_MARKERS = (
    "汇总",
    "总结",
    "归纳",
    "形成结论",
    "给出结论",
    "产出结论",
    "最终结论",
    "最终决定",
    "summarize",
    "synthesi",
    "final decision",
    "conclusion",
)
INTERNAL_SCOPE_MARKERS = (
    "discussion_id",
    "root_message_id",
    "requester_id",
    "assignee_id",
    "scope_text",
    "TALK_SCOPE",
    "控制上下文",
)
CONTROL_PROTOCOL_RESIDUE_RE = re.compile(
    r"(?is)(\bTALK_ACTION\b|</?talk-action\b|"
    r"\b(?:send_message|mark_stance|final_to_human|escalate_to_human)\b[^\r\n]*(?:\bto=|\bbody=|\bstance=))"
)
LEADING_MENTION_RE = re.compile(r"@(agent|human):[^\s]+", re.IGNORECASE)


@dataclass(frozen=True)
class CliRunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class TaskPreflightDecision:
    action: str
    question: str | None = None


@dataclass(frozen=True)
class TaskGateVerdict:
    verdict: str
    summary: str
    findings: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "summary": self.summary,
            "findings": list(self.findings),
        }


@dataclass(frozen=True)
class TalkAction:
    action_type: str
    body: str = ""
    to: str | None = None
    target_member_id: str | None = None
    stance: str | None = None
    discussion_id: int | None = None
    round_index: int | None = None


@dataclass(frozen=True)
class DiscussionScopeContext:
    discussion: dict[str, Any] | None
    turns: list[dict[str, Any]]
    closed: bool = False


def member_id_from_name(name: str) -> str:
    return name if name.startswith("agent:") else f"agent:{name}"


def parse_command(command: str) -> list[str]:
    parsed = shlex.split(command, posix=True)
    if not parsed:
        raise ValueError("CLI command cannot be empty")
    return parsed


def _resolve_windows_dsh_npm_shim(args: Sequence[str], *, platform: str) -> list[str]:
    resolved = list(args)
    if platform != "nt" or not resolved:
        return resolved

    shim_path = Path(resolved[0])
    if shim_path.name.lower() != "dsh.cmd":
        return resolved

    package_root = shim_path.parent / "node_modules" / "@deepseek-ai" / "dsh"
    manifest_path = package_root / "package.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != "@deepseek-ai/dsh":
            return resolved
        bin_config = manifest.get("bin")
        bin_entry = bin_config.get("dsh") if isinstance(bin_config, dict) else bin_config
        if not isinstance(bin_entry, str) or not bin_entry:
            return resolved
        package_root = package_root.resolve(strict=True)
        entry_path = (package_root / bin_entry).resolve(strict=True)
        entry_path.relative_to(package_root)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return resolved

    sibling_node = shim_path.parent / "node.exe"
    node_executable = str(sibling_node) if sibling_node.is_file() else None
    if node_executable is None:
        node_executable = shutil.which("node.exe") or shutil.which("node")
    if node_executable is None:
        return resolved

    return [node_executable, str(entry_path), *resolved[1:]]


def resolve_command_executable(
    args: Sequence[str],
    *,
    platform: str | None = None,
) -> list[str]:
    resolved = list(args)
    if not resolved:
        raise ValueError("CLI command cannot be empty")

    executable = resolved[0]
    if Path(executable).parent == Path("."):
        found = shutil.which(executable)
        if found:
            resolved[0] = found
    return _resolve_windows_dsh_npm_shim(
        resolved,
        platform=os.name if platform is None else platform,
    )


def _is_dsh_launcher_command(command_args: Sequence[str]) -> bool:
    if not command_args:
        return False
    return Path(command_args[0]).name.lower() in {"dsh", "dsh.cmd", "dsh.exe"}


def _dsh_package_root_from_command(command: str | Sequence[str]) -> str | None:
    """292：从已配置的 dsh 入口解析公开安装包根，供原生 runner 校验。

    只读取同一命令路径旁的 ``package.json``；不扫描 HOME、不读取配置。
    解析失败返回 ``None``，由调用方明确报 ``native_package_unresolved``。
    """

    args = parse_command(command) if isinstance(command, str) else [str(part) for part in command]
    try:
        resolved = resolve_command_executable(args)
    except (OSError, ValueError):
        return None
    for item in resolved:
        candidate = Path(item)
        if candidate.name == "bin.js" and candidate.parent.name == "lib":
            root = candidate.parent.parent
            try:
                manifest = json.loads(
                    (root / "package.json").read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                return None
            if manifest.get("name") == "@deepseek-ai/dsh":
                return str(root.resolve())
    return None


def resolve_task_preflight_command(args: argparse.Namespace) -> str | list[str]:
    """Resolve the Task Hall preflight command, including the DSH overlay."""
    configured = getattr(args, "task_preflight_command", None)
    if configured:
        return configured

    task_command = getattr(args, "task_command", None) or args.command
    if str(getattr(args, "runtime", "")).strip().lower() != "dsh":
        return task_command

    project_root = getattr(args, "project", None)
    if not project_root:
        return task_command
    patch_path = (
        Path(project_root).expanduser().resolve()
        / DSH_PREFLIGHT_PATCH_RELATIVE_PATH
    )
    if not patch_path.is_file():
        return task_command

    command_args = (
        parse_command(task_command)
        if isinstance(task_command, str)
        else list(task_command)
    )
    if not _is_dsh_launcher_command(command_args):
        return task_command
    return [*command_args, "--patch", str(patch_path)]


def resolve_task_preflight_max_attempts(args: argparse.Namespace) -> int:
    configured = getattr(args, "task_preflight_max_attempts", None)
    if configured is not None:
        return int(configured)
    if str(getattr(args, "runtime", "")).strip().lower() == "dsh":
        return DSH_TASK_PREFLIGHT_MAX_ATTEMPTS
    return TASK_PREFLIGHT_MAX_ATTEMPTS


def strip_leading_mentions(text: str, *, member_id: str | None = None) -> str:
    cursor = 0
    length = len(text)

    while cursor < length and text[cursor].isspace():
        cursor += 1

    saw_mention = False
    while cursor < length:
        match = LEADING_MENTION_RE.match(text, cursor)
        if not match:
            break

        saw_mention = True
        cursor = match.end()
        while cursor < length and text[cursor].isspace():
            cursor += 1

    if not saw_mention:
        return text.strip()
    return text[cursor:].strip()


def wants_one_sentence(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ONE_SENTENCE_MARKERS)


def first_sentence(text: str, *, max_chars: int = 240) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    compact = " ".join(lines)
    if not compact:
        return text

    positions = [compact.find(mark) for mark in SENTENCE_ENDINGS if compact.find(mark) != -1]
    if positions:
        index = min(positions) + 1
        return compact[:index].strip()

    if len(lines) > 1:
        return first_sentence(lines[0], max_chars=max_chars)

    if len(compact) > max_chars:
        return f"{compact[:max_chars].rstrip()}..."
    return compact


def _compact_text(text: str) -> str:
    return " ".join(text.split())


def _is_short_text(text: str, *, max_chars: int = 80) -> bool:
    return len(_compact_text(text)) <= max_chars


def _is_greeting_like(text: str) -> bool:
    compact = _compact_text(text)
    if not compact:
        return False
    lowered = compact.lower()
    return any(marker in compact for marker in GREETING_REPLY_MARKERS) or any(
        marker in lowered for marker in ("hello", "hi ", "hi,", "hey", "online")
    )


def _is_greeting_scope(text: str) -> bool:
    compact = _compact_text(text)
    lowered = compact.lower()
    return any(marker in compact for marker in GREETING_SCOPE_MARKERS) or any(
        marker in lowered for marker in ("say hello", "greet", "check online")
    )


def infer_reply_stance(task_text: str, visible_reply: str) -> str:
    if _is_greeting_scope(task_text) and _is_short_text(visible_reply) and _is_greeting_like(visible_reply):
        return "greeting"
    return "answer"


def _is_summary_request(text: str) -> bool:
    lowered = _compact_text(text).lower()
    return bool(lowered) and any(marker.lower() in lowered for marker in BRAINSTORM_SUMMARY_MARKERS)


def infer_discussion_stance(task_text: str, visible_reply: str, *, default: str = "answer") -> str:
    if infer_reply_stance(task_text, visible_reply) == "greeting":
        return "greeting"
    return default or "answer"


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def prefers_chinese(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in ENGLISH_REQUEST_MARKERS):
        return False
    return contains_cjk(text) or any(marker in lowered for marker in CHINESE_REQUEST_MARKERS)


def asks_capability_question(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in CAPABILITY_QUESTION_MARKERS)


def pi_chinese_capability_reply() -> str:
    return (
        "我是 pi，TALK Group Hall 里的参与者。"
        "我可以聊天、回答问题、评审方案、联系其他 agent，并通过 TALK 动作参与协作；"
        "默认讨论模式下我不会读取项目文件、执行本机命令或编辑文件。"
    )


def pi_chinese_language_fallback_reply() -> str:
    return "我是 pi，已切换为中文回复。你可以继续告诉我想聊什么，或让我帮你拆解一个具体任务。"


def normalize_pi_reply_language(task_text: str, reply: str) -> str:
    if not prefers_chinese(task_text):
        return reply
    if contains_cjk(reply) and not reply.lstrip().lower().startswith("<language:"):
        return reply
    if asks_capability_question(task_text):
        return pi_chinese_capability_reply()
    return pi_chinese_language_fallback_reply()


def contains_internal_scope_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in INTERNAL_SCOPE_MARKERS)


def sanitize_scope_leak(text: str) -> str:
    if not contains_internal_scope_marker(text):
        return text
    return "我需要先确认当前请求范围后再继续。"


def contains_control_protocol_residue(text: str) -> bool:
    return bool(text and CONTROL_PROTOCOL_RESIDUE_RE.search(text))


def sanitize_visible_reply(text: str) -> str:
    text = sanitize_scope_leak(text)
    if contains_control_protocol_residue(text):
        return "我需要先确认当前请求范围后再继续。"
    return text


def _substantive_discussion_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [turn for turn in turns if str(turn.get("stance") or "") not in NON_SUBSTANTIVE_STANCES]


def _discussion_auto_turn_budget(discussion: dict[str, Any] | None) -> int:
    """自动回合预算：多方场（>2 参与者，如 brainstorm）按参与者规模放大（DELIBERATION §8.3）。

    N 个 agent 的头脑风暴预期实质轮次 ≈ N(想法) + N×(N-1)(表态) + 1(decision) = N²+1；
    1:1 讨论保持原常量 DISCUSSION_MAX_AUTO_TURNS。
    """
    participants = list((discussion or {}).get("participant_ids") or [])
    if len(participants) <= 2:
        return DISCUSSION_MAX_AUTO_TURNS
    agent_count = sum(1 for participant in participants if str(participant).startswith("agent:"))
    return max(agent_count * agent_count + 1, DISCUSSION_MAX_AUTO_TURNS)


def _max_demand_round(turns: list[dict[str, Any]]) -> int:
    max_round = 0
    for turn in turns:
        if str(turn.get("turn_kind") or "reply") != "demand":
            continue
        try:
            max_round = max(max_round, int(turn.get("round_index") or 1))
        except (TypeError, ValueError):
            max_round = max(max_round, 1)
    return max_round


def _next_demand_round(turns: list[dict[str, Any]]) -> int:
    return _max_demand_round(turns) + 1


def _can_create_deferred_file(
    *,
    group_id: str | None,
    sender_id: str,
    message: dict[str, Any],
    discussion: dict[str, Any] | None,
    turns: list[dict[str, Any]],
) -> bool:
    if not group_id:
        return False
    if not sender_id.startswith("agent:"):
        return True
    if discussion is None:
        return _message_reply_to_id(message) is None
    return _max_demand_round(turns) < 2


def _pick_closure_line(responder_id: str) -> str:
    digest = hashlib.sha256(responder_id.encode("utf-8")).digest()
    index = int.from_bytes(digest[:2], "big") % len(CLOSURE_LINES)
    return CLOSURE_LINES[index]


def _parse_action_attrs(raw_attrs: str) -> dict[str, str]:
    return {match.group(1).replace("-", "_").lower(): html.unescape(match.group(3)).strip() for match in ACTION_ATTR_RE.finditer(raw_attrs)}


def _parse_safe_action_attrs(raw_attrs: str) -> tuple[dict[str, str], str]:
    body = ""
    attrs_text = raw_attrs
    body_match = re.search(r"\b(?:body|text|message)=", raw_attrs, flags=re.IGNORECASE)
    if body_match:
        attrs_text = raw_attrs[: body_match.start()]
        body = raw_attrs[body_match.end() :].strip()
    attrs = {
        match.group(1).replace("-", "_").lower(): match.group(2).strip()
        for match in SAFE_ACTION_ATTR_RE.finditer(attrs_text)
    }
    return attrs, body


def _action_from_parts(action_type: str, attrs: dict[str, str], body: str) -> TalkAction | None:
    action_type = action_type.strip().lower()
    if action_type not in ACTION_TYPES:
        return None

    stance = attrs.get("stance", "").strip().lower() or None
    if stance is not None and stance not in ACTION_STANCES:
        stance = None

    discussion_id: int | None = None
    raw_discussion_id = attrs.get("discussion_id") or attrs.get("session_id")
    if raw_discussion_id:
        try:
            discussion_id = int(raw_discussion_id)
        except ValueError:
            discussion_id = None

    round_index: int | None = None
    raw_round_index = attrs.get("round_index") or attrs.get("round")
    if raw_round_index:
        try:
            round_index = int(raw_round_index)
        except ValueError:
            round_index = None

    target = attrs.get("target") or attrs.get("target_member_id")
    to = attrs.get("to") or target
    return TalkAction(
        action_type=action_type,
        body=body.strip(),
        to=to or None,
        target_member_id=target or to or None,
        stance=stance,
        discussion_id=discussion_id,
        round_index=round_index if round_index and round_index > 0 else None,
    )


def clean_protocol_visible_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(
        r"^\s*(?:mark_stance\s*)?动作已记录[^\n]*(?:\n\s*)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"^\s*(?:mark_stance|send_message|escalate_to_human|final_to_human|update)\s*[:：,，。.-]*\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower() in {"mark_stance", "send_message", "escalate_to_human", "final_to_human", "update"}:
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def parse_talk_actions(text: str) -> tuple[str, list[TalkAction]]:
    actions: list[TalkAction] = []

    def replace(match: re.Match[str]) -> str:
        attrs = _parse_action_attrs(match.group("attrs") or "")
        body = html.unescape(match.group("body") or "").strip()
        action = _action_from_parts(attrs.get("type", ""), attrs, body)
        if action is not None:
            actions.append(action)
        return ""

    visible_text = ACTION_RE.sub(replace, text).strip()

    def replace_safe(match: re.Match[str]) -> str:
        attrs, body = _parse_safe_action_attrs(match.group("attrs") or "")
        action = _action_from_parts(match.group("type") or "", attrs, body)
        if action is not None:
            actions.append(action)
        return ""

    visible_text = SAFE_ACTION_RE.sub(replace_safe, visible_text).strip()
    return clean_protocol_visible_text(visible_text), actions


def _discussion_topic_from_text(text: str, *, max_chars: int = 120) -> str:
    topic = " ".join(text.split())
    if len(topic) > max_chars:
        topic = f"{topic[:max_chars].rstrip()}..."
    return topic or "TALK Agent discussion"


def _discussion_participants(*member_ids: str | None) -> list[str]:
    return list(dict.fromkeys(member_id for member_id in member_ids if member_id))


def _message_id(message: dict[str, Any]) -> int | None:
    raw_id = message.get("id")
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _message_reply_to_id(message: dict[str, Any]) -> int | None:
    raw_reply_to = message.get("reply_to")
    if isinstance(raw_reply_to, dict):
        raw_reply_to = raw_reply_to.get("id")
    if raw_reply_to is None:
        return None
    try:
        return int(raw_reply_to)
    except (TypeError, ValueError):
        return None


def _is_talk_not_found(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404


async def _create_discussion(
    client: Any,
    group_id: str,
    topic: str,
    participant_ids: list[str],
    *,
    root_message_id: int | None = None,
    requester_id: str | None = None,
    assignee_id: str | None = None,
    scope_text: str | None = None,
    max_rounds: int = 2,
) -> dict[str, Any]:
    try:
        return await client.create_discussion(
            group_id,
            topic,
            participant_ids,
            root_message_id=root_message_id,
            requester_id=requester_id,
            assignee_id=assignee_id,
            scope_text=scope_text,
            max_rounds=max_rounds,
        )
    except TypeError:
        return await client.create_discussion(
            group_id,
            topic,
            participant_ids,
            max_rounds=max_rounds,
        )


async def _resolve_discussion_id(
    client: Any,
    *,
    group_id: str | None,
    member_id: str,
    peer_id: str | None,
    topic: str,
    create_if_missing: bool,
    root_message_id: int | None = None,
    requester_id: str | None = None,
    assignee_id: str | None = None,
    scope_text: str | None = None,
    max_rounds: int = 2,
) -> int | None:
    if not group_id or not peer_id:
        return None

    try:
        discussions = await client.list_discussions(group_id=group_id)
    except AttributeError:
        return None
    except Exception as exc:
        if _is_talk_not_found(exc):
            return None
        raise

    for discussion in discussions:
        if root_message_id is not None and discussion.get("root_message_id") is not None:
            try:
                if int(discussion["root_message_id"]) == root_message_id:
                    return int(discussion["id"])
            except (TypeError, ValueError):
                pass
        participants = set(discussion.get("participant_ids") or [])
        if root_message_id is None and discussion.get("status") == "active" and {member_id, peer_id}.issubset(participants):
            return int(discussion["id"])

    if not create_if_missing:
        return None

    try:
        created = await _create_discussion(
            client,
            group_id,
            topic,
            _discussion_participants(member_id, peer_id),
            root_message_id=root_message_id,
            requester_id=requester_id,
            assignee_id=assignee_id,
            scope_text=scope_text,
            max_rounds=max_rounds,
        )
    except Exception as exc:
        if _is_talk_not_found(exc):
            return None
        raise
    return int(created["id"])


async def _append_discussion_turn(
    client: Any,
    *,
    discussion_id: int | None,
    message_id: int | None,
    stance: str,
    target_member_id: str | None = None,
    turn_kind: str = "reply",
    round_index: int = 1,
) -> bool:
    if discussion_id is None or message_id is None:
        return False
    try:
        try:
            await client.append_discussion_turn(
                discussion_id,
                message_id=message_id,
                stance=stance,
                target_member_id=target_member_id,
                turn_kind=turn_kind,
                round_index=round_index,
            )
        except TypeError as exc:
            if "turn_kind" not in str(exc):
                raise
            await client.append_discussion_turn(
                discussion_id,
                message_id=message_id,
                stance=stance,
                target_member_id=target_member_id,
                round_index=round_index,
            )
        return True
    except AttributeError:
        return False
    except Exception as exc:
        if _is_talk_not_found(exc):
            return False
        raise


def _last_two_turns_disagree(turns: list[dict[str, Any]]) -> bool:
    if len(turns) < 2:
        return False
    latest = turns[-2:]
    return (
        latest[0].get("stance") == "disagree"
        and latest[1].get("stance") == "disagree"
        and latest[0].get("speaker_id") != latest[1].get("speaker_id")
    )


async def _find_human_reviewer(client: Any, group_id: str | None) -> str | None:
    if not group_id:
        return None
    try:
        group = await client.get_group(group_id)
    except AttributeError:
        return None
    except Exception as exc:
        if _is_talk_not_found(exc):
            return None
        raise
    for member in group.get("members") or []:
        member_id = str(member.get("member_id") or "")
        if member_id.startswith("human:"):
            return member_id
    return None


async def _discussion_initiator(client: Any, discussion_id: int | None) -> str | None:
    """Return the discussion initiator (``requester_id`` / ``created_by``), if known.

    Close-out is decided by the initiator and the existing stance rules; the removed
    fixed decision tier is no longer consulted anywhere.
    """
    if discussion_id is None:
        return None
    getter = getattr(client, "get_discussion", None)
    if getter is None:
        return None
    try:
        discussion = await getter(discussion_id)
    except Exception as exc:
        if _is_talk_not_found(exc):
            return None
        raise
    if not isinstance(discussion, dict):
        return None
    for key in ("requester_id", "created_by"):
        value = str(discussion.get(key) or "").strip()
        if value:
            return value
    return None


async def _group_member_ids(client: Any, group_id: str | None) -> set[str] | None:
    if not group_id:
        return None
    try:
        group = await client.get_group(group_id)
    except AttributeError:
        return None
    except Exception as exc:
        if _is_talk_not_found(exc):
            return set()
        raise
    return {str(member.get("member_id") or "") for member in group.get("members") or []}


# ----------------------------------------------------------------------------
# 临时诊断工具：TALK_DUMP_PROMPT=1 时把 pi spawn 前的完整 prompt 写到日志
# 用完即移除，不应进入正式发布
# ----------------------------------------------------------------------------
_DIAGNOSTIC_DUMP_PATH = Path(os.environ.get("TALK_DUMP_PROMPT_FILE", "logs/pi_prompt_dump.log"))


def _dump_diagnostic(line: str) -> None:
    """Append a single diagnostic line (no full prompt). Best-effort, never raises."""
    try:
        _DIAGNOSTIC_DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_DIAGNOSTIC_DUMP_PATH, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {line}\n")
    except Exception:
        pass


def _dump_prompt(
    *,
    member_id: str,
    message_id: str,
    sender: str,
    group_id: str | None,
    group_member_context: str,
    runtime: str,
    prompt: str,
) -> None:
    """Append the full prompt that's about to be sent to the LLM CLI. Best-effort, never raises."""
    try:
        _DIAGNOSTIC_DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        with open(_DIAGNOSTIC_DUMP_PATH, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 78 + "\n")
            f.write(f"timestamp        : {datetime.now().isoformat(timespec='seconds')}\n")
            f.write(f"member_id        : {member_id}\n")
            f.write(f"runtime          : {runtime}\n")
            f.write(f"incoming msg id  : {message_id}\n")
            f.write(f"sender           : {sender}\n")
            f.write(f"group_id         : {group_id!r}\n")
            f.write(f"group_member_ctx : {'(EMPTY!)' if not group_member_context else f'({len(group_member_context)} chars)'}\n")
            f.write("-" * 78 + "\n")
            f.write("FULL PROMPT (between <<<PROMPT and PROMPT>>> markers):\n")
            f.write("<<<PROMPT\n")
            f.write(prompt)
            if not prompt.endswith("\n"):
                f.write("\n")
            f.write("PROMPT>>>\n")
            f.write("=" * 78 + "\n")
    except Exception:
        pass


async def _read_and_execute_deferred_actions(
    filepath: str,
    *,
    client: Any,
    group_id: str | None,
    reply_to: int | None = None,
    current_turn_count: int = 0,
    max_auto_turns: int = DISCUSSION_MAX_AUTO_TURNS,
) -> list[dict[str, Any]]:
    """读取 JSONL 延迟文件，用 TALK SDK 逐条执行 talk_send。

    返回每条的执行结果（ok / skipped / target / message_id / error）。
    文件不存在或读不到有效行不报错，返回空列表。

    Turn limit 刹车：
    - greeting / answer / agree / closure 类型的 talk_send，current_turn_count >= max_auto_turns 时跳过
    - question / disagree 类型不受 turn limit 限制
    - 无 stance 视为 greeting（保守策略）
    """
    results: list[dict[str, Any]] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    action = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if action.get("tool") != "talk_send":
                    continue
                target = str(action.get("target", "")).strip()
                body = str(action.get("body", "")).strip()
                stance = str(action.get("stance", "greeting")).strip().lower() or "greeting"
                act_group_id = action.get("group_id") or group_id
                if not target or not body:
                    continue
                # ---- turn limit 刹车 ----
                if stance in ("greeting", "answer", "agree", "closure"):
                    if current_turn_count >= max_auto_turns:
                        results.append({
                            "ok": False, "skipped": True, "target": target, "stance": stance,
                            "reason": f"turn limit ({current_turn_count} >= {max_auto_turns})",
                        })
                        continue
                try:
                    result = await client.send_text(
                        to=[target],
                        text=f"@{target} {body}",
                        reply_to=reply_to,
                        group_id=act_group_id,
                    )
                    msg_id = result.get("id") if isinstance(result, dict) else None
                    results.append({"ok": True, "target": target, "message_id": msg_id, "stance": stance})
                except Exception as exc:
                    results.append({"ok": False, "target": target, "error": str(exc), "stance": stance})
    except FileNotFoundError:
        pass
    return results


async def _record_deferred_demand_turns(
    results: list[dict[str, Any]],
    *,
    client: Any,
    group_id: str | None,
    member_id: str,
    discussion: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    task_text: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not group_id:
        return discussion, turns

    current_discussion = discussion
    current_turns = list(turns)
    for result in results:
        if not result.get("ok") or result.get("skipped"):
            continue
        target = str(result.get("target") or "")
        message_id = result.get("message_id")
        if not target or message_id is None:
            continue
        demand_round = min(_next_demand_round(current_turns), 2)
        discussion_id = int(current_discussion["id"]) if current_discussion and current_discussion.get("id") is not None else None
        if discussion_id is None:
            discussion_id = await _resolve_discussion_id(
                client,
                group_id=group_id,
                member_id=member_id,
                peer_id=target,
                topic=_discussion_topic_from_text(task_text),
                create_if_missing=True,
                root_message_id=int(message_id),
                requester_id=member_id,
                assignee_id=target,
                scope_text=task_text,
            )
            if discussion_id is not None:
                try:
                    current_discussion = await client.get_discussion(discussion_id)
                except AttributeError:
                    current_discussion = {
                        "id": discussion_id,
                        "status": "active",
                        "topic": _discussion_topic_from_text(task_text),
                        "participant_ids": [member_id, target],
                        "root_message_id": int(message_id),
                        "requester_id": member_id,
                        "assignee_id": target,
                        "scope_text": task_text,
                    }
        stance = str(result.get("stance") or "question")
        appended = await _append_discussion_turn(
            client,
            discussion_id=discussion_id,
            message_id=int(message_id),
            stance=stance,
            target_member_id=target,
            turn_kind="demand",
            round_index=demand_round,
        )
        await _resolve_if_discussion_initiator(
            client,
            discussion_id=discussion_id,
            group_id=group_id,
            member_id=member_id,
            stance=stance,
        )
        if appended:
            current_turns.append(
                {
                    "message_id": int(message_id),
                    "speaker_id": member_id,
                    "target_member_id": target,
                    "turn_kind": "demand",
                    "stance": stance,
                    "round_index": demand_round,
                }
            )
    return current_discussion, current_turns


async def _get_hall_type_templates(client: Any) -> dict[str, dict[str, Any]]:
    global _HALL_TYPE_TEMPLATES
    if _HALL_TYPE_TEMPLATES is not None:
        return _HALL_TYPE_TEMPLATES

    try:
        payload = await client.get_hall_types()
    except Exception:
        return {}

    templates: dict[str, dict[str, Any]] = {}
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        hall_type = str(item.get("type") or "").strip()
        if hall_type:
            templates[hall_type] = item

    _HALL_TYPE_TEMPLATES = templates
    return templates


async def _build_group_member_context(
    client: Any,
    group_id: str | None,
    member_id: str,
    sender: str = "",
) -> str:
    """Build group member list and role context for prompt injection.

    All "no list available" paths now return an explicit anti-hallucination
    notice instead of an empty string, because empty prompts caused pi/codex
    to invent fictitious member names (orchestrator / oracle / dan / sage ...)
    when calling talk_send.
    """
    def _no_list_fallback(reason: str) -> str:
        sender_hint = (
            f"如需回复，目标只能是当前消息的发件人 {sender}。"
            if sender
            else "如需回复，目标只能是当前消息的发件人。"
        )
        return (
            "\n[当前群成员清单 — 不可用]\n"
            f"{reason}\n"
            "严格禁止凭想象列出或向任何未经清单确认的 member_id 调用 talk_send。"
            "特别注意：agent:orchestrator / agent:oracle / agent:dan / agent:sage "
            "/ agent:trace / agent:omni / agent:review 等常见 multi-agent 框架角色名"
            "在本系统中默认不存在，禁止凭印象使用。\n"
            f"{sender_hint}\n"
            "本条消息不要调用 talk_send 工具转发给其它成员。\n"
        )

    if not group_id:
        if os.environ.get("TALK_DUMP_PROMPT") == "1":
            _dump_diagnostic(
                f"_build_group_member_context: group_id is None/empty (P2P scope); "
                f"emitting no-list fallback for member_id={member_id}"
            )
        return _no_list_fallback("本条消息不在任何群组上下文中（P2P 私聊场景）。")

    try:
        group = await client.get_group(group_id)
    except Exception as exc:
        if os.environ.get("TALK_DUMP_PROMPT") == "1":
            _dump_diagnostic(
                f"_build_group_member_context: get_group({group_id!r}) raised "
                f"{type(exc).__name__}: {exc}; emitting no-list fallback"
            )
        return _no_list_fallback(
            f"查询群成员清单失败（group_id={group_id}），清单暂不可用。"
        )

    members = group.get("members") or []
    member_lines: list[str] = []
    for m in members:
        mid = str(m.get("member_id") or "")
        display = str(m.get("display_name") or "")
        if display and display != mid:
            member_lines.append(f"  {mid}（{display}）")
        else:
            member_lines.append(f"  {mid}")

    if not member_lines:
        if os.environ.get("TALK_DUMP_PROMPT") == "1":
            _dump_diagnostic(
                f"_build_group_member_context: group {group_id!r} has no visible members; "
                f"emitting no-list fallback for member_id={member_id}"
            )
        return _no_list_fallback(f"群 {group_id} 当前无可见成员。")

    # 正常路径：返回紧凑逗号分隔名单，同时写入环境变量供扩展使用
    mids = [str(m.get("member_id") or "") for m in members]
    os.environ["TALK_GROUP_MEMBERS"] = ",".join(mids)
    context = f"群成员：{', '.join(mids)}。\n"
    # 协作层（PROJECT_INTEGRATION §5.2 / P3-2）：注入"我在本群的业务角色"，让 agent 知道
    # 自己在这一群里的岗位（lead / reviewer / ...）。业务角色只是人工定义的职责说明；
    # 固定"决策/执行"分级已移除，此处不再注入任何分级文本。
    self_role = next(
        (
            str(m.get("business_role") or "").strip()
            for m in members
            if str(m.get("member_id") or "") == member_id
        ),
        "",
    )
    if self_role:
        context += f"你在本群的业务角色：{self_role}。\n"
    group_type = str(group.get("type") or "free").strip().lower() or "free"
    if group_type == "free":
        return context

    templates = await _get_hall_type_templates(client)
    template = templates.get(group_type)
    if not template:
        return context

    label = str(template.get("label") or group_type).strip()
    protocol_guidance = str(template.get("protocol_guidance") or "").strip()
    if protocol_guidance:
        context += f"本群类型：{label}（{group_type}）。流程指引：{protocol_guidance}\n"

    if self_role:
        self_role_normalized = self_role.lower()
        for role in template.get("roles") or []:
            if not isinstance(role, dict):
                continue
            if str(role.get("role") or "").strip().lower() != self_role_normalized:
                continue
            norm = str(role.get("norm") or "").strip()
            if norm:
                context += f"你的角色职责：{norm}\n"
            break
    return context


async def _update_discussion_status(
    client: Any,
    discussion_id: int | None,
    status: str,
    *,
    end_reason: str | None = None,
) -> None:
    if discussion_id is None:
        return
    try:
        if end_reason is None:
            await client.update_discussion(discussion_id, status=status)
        else:
            await client.update_discussion(discussion_id, status=status, end_reason=end_reason)
    except AttributeError:
        pass
    except Exception as exc:
        if not _is_talk_not_found(exc):
            raise


async def _resolve_if_discussion_initiator(
    client: Any,
    *,
    discussion_id: int | None,
    group_id: str | None,
    member_id: str,
    stance: str,
) -> None:
    """Close a discussion on an explicit ``decision`` stance from its initiator.

    ``group_id`` is kept for call-site compatibility only. Close-out no longer picks a
    person by the removed fixed decision tier: it follows the discussion initiator
    (``requester_id`` / ``created_by``) plus the existing stance rules
    (``escalate`` -> deadlock, otherwise consensus).
    """
    if stance != "decision":
        return
    initiator = await _discussion_initiator(client, discussion_id)
    if initiator is None or initiator != member_id:
        return
    end_reason = "consensus"
    try:
        turns = await _list_discussion_turns(client, discussion_id)
    except Exception:
        turns = []
    if any(str(turn.get("stance") or "") == "escalate" for turn in turns if isinstance(turn, dict)):
        end_reason = "deadlock"
    await _update_discussion_status(client, discussion_id, "resolved", end_reason=end_reason)


async def _maybe_escalate_disagreement(
    client: Any,
    *,
    discussion_id: int | None,
    group_id: str | None,
    reply_to: int | None,
) -> None:
    if discussion_id is None or not group_id:
        return
    try:
        turns = await client.list_discussion_turns(discussion_id)
    except AttributeError:
        return
    except Exception as exc:
        if _is_talk_not_found(exc):
            return
        raise
    if not _last_two_turns_disagree(turns):
        return

    human_id = await _find_human_reviewer(client, group_id)
    if human_id is None:
        return
    text = f"@{human_id} 我和对方连续两轮仍有不同判断，请你做最终决定。"
    message = await client.send_text(text, to=[human_id], reply_to=reply_to, group_id=group_id)
    await _append_discussion_turn(
        client,
        discussion_id=discussion_id,
        message_id=int(message["id"]),
        stance="escalate",
        target_member_id=human_id,
        turn_kind="demand",
        round_index=2,
    )
    await _update_discussion_status(client, discussion_id, "escalated")


async def _active_discussion_for_peer(
    client: Any,
    *,
    group_id: str | None,
    member_id: str,
    peer_id: str | None,
) -> dict[str, Any] | None:
    if not group_id or not peer_id:
        return None
    try:
        discussions = await client.list_discussions(group_id=group_id)
    except AttributeError:
        return None
    except Exception as exc:
        if _is_talk_not_found(exc):
            return None
        raise

    for discussion in discussions:
        participants = set(discussion.get("participant_ids") or [])
        if discussion.get("status") == "active" and {member_id, peer_id}.issubset(participants):
            return discussion
    return None


async def _active_multiparty_discussion(
    client: Any,
    *,
    group_id: str | None,
    member_id: str,
    peer_id: str | None,
) -> dict[str, Any] | None:
    """找包含双方的 active 多方（>2 参与者）discussion——人驱动编排（DELIBERATION §8）的记账场。

    只匹配多方场，避免把 human 的普通消息记进 1:1 讨论（保持既有 1:1 流程零变化）。
    """
    if not group_id or not peer_id:
        return None
    try:
        discussions = await client.list_discussions(group_id=group_id)
    except AttributeError:
        return None
    except Exception as exc:
        if _is_talk_not_found(exc):
            return None
        raise

    for discussion in discussions:
        participants = set(discussion.get("participant_ids") or [])
        if (
            discussion.get("status") == "active"
            and len(participants) > 2
            and {member_id, peer_id}.issubset(participants)
        ):
            return discussion
    return None


# 多方场（brainstorm）发言可见性（DELIBERATION §8）：拉本场发言喂进 prompt，
# 让 agent 能对彼此的想法表态/汇总。仅 >2 参与者的场生效；1:1/free 不注入。
_SHARED_HISTORY_MAX_MESSAGES = 24
_SHARED_HISTORY_MAX_CHARS_EACH = 240
_SUMMARY_OPINION_MAX_CHARS_EACH = 4000


async def _is_brainstorm_summary_request(
    client: Any,
    *,
    message: dict[str, Any],
    group_id: str | None,
    discussion: dict[str, Any] | None,
    member_id: str,
    sender_id: str,
    task_text: str,
) -> bool:
    if not group_id or not sender_id.startswith("human:") or not discussion or not _is_summary_request(task_text):
        return False
    recipients = message.get("to")
    if not isinstance(recipients, list) or {str(recipient) for recipient in recipients} != {member_id}:
        return False
    participants = set(discussion.get("participant_ids") or [])
    if discussion.get("status") != "active" or len(participants) <= 2 or {member_id, sender_id} - participants:
        return False
    try:
        group = await client.get_group(group_id)
    except AttributeError:
        return False
    except Exception as exc:
        if _is_talk_not_found(exc):
            return False
        raise
    return group.get("type") == "brainstorm"


async def _brainstorm_summary_grounding(
    client: Any,
    *,
    group_id: str,
    discussion: dict[str, Any],
    turns: list[dict[str, Any]],
) -> str:
    """取齐每位 Agent 的首条意见原文，给最终汇总者一个有边界的事实块。"""
    agent_ids = {
        str(participant)
        for participant in discussion.get("participant_ids") or []
        if str(participant).startswith("agent:")
    }
    first_opinions: list[tuple[str, int]] = []
    seen: set[str] = set()
    for turn in turns:
        if not isinstance(turn, dict) or str(turn.get("stance") or "") != "answer":
            continue
        if turn.get("turn_kind") not in (None, "reply"):
            continue
        speaker = str(turn.get("speaker_id") or "")
        if speaker not in agent_ids or speaker in seen:
            continue
        try:
            message_id = int(turn["message_id"])
        except (KeyError, TypeError, ValueError):
            continue
        seen.add(speaker)
        first_opinions.append((speaker, message_id))

    if not agent_ids or seen != agent_ids:
        return ""

    root_id = discussion.get("root_message_id")
    try:
        since = int(root_id) - 1 if root_id is not None else None
        messages = await client.fetch_history(group_id=group_id, since=since, limit=500)
    except AttributeError:
        return ""
    except Exception as exc:
        if _is_talk_not_found(exc):
            return ""
        raise

    messages_by_id = {
        str(message.get("id")): message
        for message in messages or []
        if isinstance(message, dict) and not message.get("revoked_at") and not message.get("revoked")
    }
    blocks: list[str] = []
    for index, (speaker, message_id) in enumerate(first_opinions, start=1):
        message = messages_by_id.get(str(message_id))
        if not message or str(message.get("from") or "") != speaker:
            return ""
        content = str(message.get("content") or "").strip()
        if not content:
            return ""
        if len(content) > _SUMMARY_OPINION_MAX_CHARS_EACH:
            content = content[:_SUMMARY_OPINION_MAX_CHARS_EACH] + "…（原文过长，已截断）"
        blocks.append(f"[{index}] {speaker}（message_id={message_id}）\n{content}")

    return (
        "【本轮汇总材料（必须据此形成最终结论）】\n"
        "以下是每位 Agent 在本场的首条意见原文，你此前的意见也在其中。"
        "现在不要再补一条并列意见；请综合全部意见，直接产出唯一的最终结论。\n\n"
        + "\n\n".join(blocks)
    )


async def _shared_discussion_history(
    client: Any,
    *,
    group_id: str | None,
    discussion: dict[str, Any] | None,
    current_message_id: int | None,
    self_id: str,
) -> str:
    """多方场里，把本场（从 root 消息起）的群发言拼成回顾块，供 agent 表态/汇总参考。

    只对 >2 参与者的 discussion 生效（brainstorm）；1:1/free/无场 → 空串，行为不变。
    拉历史失败（无该方法 / 404）也返回空串，绝不阻断回复。
    """
    if not group_id or not discussion:
        return ""
    participants = list(discussion.get("participant_ids") or [])
    if len(participants) <= 2:
        return ""
    root_id = discussion.get("root_message_id")
    try:
        since = int(root_id) - 1 if root_id is not None else None
        messages = await client.fetch_history(
            group_id=group_id, since=since, limit=_SHARED_HISTORY_MAX_MESSAGES
        )
    except AttributeError:
        return ""
    except Exception as exc:
        if _is_talk_not_found(exc):
            return ""
        raise

    lines: list[str] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if msg.get("revoked_at") or msg.get("revoked"):
            continue
        if current_message_id is not None and str(msg.get("id")) == str(current_message_id):
            continue  # 当前触发消息已在 prompt 里，不重复
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        speaker = str(msg.get("from") or "?")
        lines.append(f"{speaker}：{content[:_SHARED_HISTORY_MAX_CHARS_EACH]}")

    if not lines:
        return ""
    body = "\n".join(lines[-_SHARED_HISTORY_MAX_MESSAGES:])
    return "【本场已有发言（供你表态/汇总参考，请勿逐条复述）】\n" + body


async def _discussion_for_message_id(
    client: Any,
    *,
    group_id: str | None,
    message_id: int | None,
) -> dict[str, Any] | None:
    if not group_id or message_id is None:
        return None
    try:
        discussions = await client.list_discussions(group_id=group_id)
    except AttributeError:
        return None
    except Exception as exc:
        if _is_talk_not_found(exc):
            return None
        raise

    for discussion in discussions:
        try:
            if discussion.get("root_message_id") is not None and int(discussion["root_message_id"]) == message_id:
                return discussion
        except (TypeError, ValueError):
            pass

    for discussion in discussions:
        discussion_id = discussion.get("id")
        if discussion_id is None:
            continue
        turns = await _list_discussion_turns(client, int(discussion_id))
        for turn in turns:
            try:
                if int(turn.get("message_id")) == message_id:
                    return discussion
            except (TypeError, ValueError):
                continue
    return None


async def _discussion_scope_for_incoming_agent_message(
    client: Any,
    *,
    group_id: str | None,
    member_id: str,
    sender_id: str,
    message: dict[str, Any],
    task_text: str,
) -> DiscussionScopeContext:
    reply_discussion = await _discussion_for_message_id(
        client,
        group_id=group_id,
        message_id=_message_reply_to_id(message),
    )
    if reply_discussion is not None:
        turns = await _list_discussion_turns(client, int(reply_discussion["id"]))
        return DiscussionScopeContext(
            discussion=reply_discussion,
            turns=turns,
            closed=reply_discussion.get("status") != "active",
        )

    root_discussion = await _discussion_for_message_id(
        client,
        group_id=group_id,
        message_id=_message_id(message),
    )
    if root_discussion is not None:
        turns = await _list_discussion_turns(client, int(root_discussion["id"]))
        return DiscussionScopeContext(
            discussion=root_discussion,
            turns=turns,
            closed=root_discussion.get("status") != "active",
        )

    legacy_discussion = await _active_discussion_for_peer(
        client,
        group_id=group_id,
        member_id=member_id,
        peer_id=sender_id,
    )
    if legacy_discussion is not None and legacy_discussion.get("root_message_id") is None:
        turns = await _list_discussion_turns(client, int(legacy_discussion["id"]))
        return DiscussionScopeContext(discussion=legacy_discussion, turns=turns)

    discussion_id = await _resolve_discussion_id(
        client,
        group_id=group_id,
        member_id=sender_id,
        peer_id=member_id,
        topic=_discussion_topic_from_text(task_text),
        create_if_missing=group_id is not None,
        root_message_id=_message_id(message),
        requester_id=sender_id,
        assignee_id=member_id,
        scope_text=task_text,
    )
    discussion = None
    if discussion_id is not None:
        try:
            discussion = await client.get_discussion(discussion_id)
        except AttributeError:
            discussion = {
                "id": discussion_id,
                "status": "active",
                "topic": _discussion_topic_from_text(task_text),
                "participant_ids": [sender_id, member_id],
                "root_message_id": _message_id(message),
                "requester_id": sender_id,
                "assignee_id": member_id,
                "scope_text": task_text,
            }
    return DiscussionScopeContext(discussion=discussion, turns=[])


async def _list_discussion_turns(client: Any, discussion_id: int | None) -> list[dict[str, Any]]:
    if discussion_id is None:
        return []
    try:
        return list(await client.list_discussion_turns(discussion_id))
    except AttributeError:
        return []
    except Exception as exc:
        if _is_talk_not_found(exc):
            return []
        raise


def _discussion_context_text(
    discussion: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    *,
    current_message_id: int | None,
    current_message_text: str,
    responder_id: str,
    direct_requester_id: str | None,
    human_id: str | None,
) -> str:
    if not discussion:
        return ""
    topic = str(discussion.get("topic") or "当前讨论").strip()
    scope_text = str(discussion.get("scope_text") or topic).strip()
    requester_id = str(discussion.get("requester_id") or direct_requester_id or "unknown")
    assignee_id = str(discussion.get("assignee_id") or responder_id)
    discussion_id = discussion.get("id")
    root_message_id = discussion.get("root_message_id")
    latest = turns[-1].get("stance") if turns else "question"
    remaining = max(0, _discussion_auto_turn_budget(discussion) - len(turns))
    return (
        "TALK 控制上下文，以下内容只用于约束回复，不要在可见回复中复述字段名或 ID：\n"
        f"discussion_id: {discussion_id}\n"
        f"root_message_id: {root_message_id}\n"
        f"current_message_id: {current_message_id}\n"
        f"requester_id: {requester_id}\n"
        f"assignee_id: {assignee_id}\n"
        f"responder_id: {responder_id}\n"
        f"scope_text: {scope_text}\n"
        f"current_message_text: {current_message_text}\n"
        f"current_stage: {latest}\n"
        f"remaining_auto_turns: {remaining}\n"
        "回复必须服务于 requester_id 在 scope_text/current_message_text 中提出的当前请求。"
        "可以补充必要上下文、指出风险或提出确认问题，但不能把话题迁移到无关任务。"
        "如果想引申但不确定是否仍在范围内，先向 requester_id 追问确认。"
        "不要展示 discussion_id、root_message_id、requester_id、assignee_id、scope_text、TALK_SCOPE 或控制上下文。"
        "确需向人类裁决时用 talk_send target=human 或 TALK_ACTION escalate_to_human to=human 告知裁决问题。"
    )


async def _send_human_escalation(
    client: Any,
    *,
    discussion_id: int | None,
    group_id: str | None,
    reply_to: int | None,
    text: str,
    human_id: str | None = None,
) -> bool:
    target = human_id or await _find_human_reviewer(client, group_id)
    if target is None:
        return False
    message = await client.send_text(f"@{target} {text}".strip(), to=[target], reply_to=reply_to, group_id=group_id)
    await _append_discussion_turn(
        client,
        discussion_id=discussion_id,
        message_id=int(message["id"]),
        stance="escalate",
        target_member_id=target,
        round_index=2,
    )
    await _update_discussion_status(client, discussion_id, "escalated")
    return True


async def _send_agent_scope_closure(
    client: Any,
    *,
    discussion_id: int | None,
    group_id: str | None,
    reply_to: int | None,
    responder_id: str,
    target_agent_id: str,
) -> bool:
    text = _pick_closure_line(responder_id)
    message = await client.reply(reply_to, text=text, to=[target_agent_id], group_id=group_id)
    message_id = int(message["id"]) if message and message.get("id") is not None else None
    await _append_discussion_turn(
        client,
        discussion_id=discussion_id,
        message_id=message_id,
        stance="closure",
        target_member_id=target_agent_id,
        turn_kind="reply",
        round_index=2,
    )
    await _update_discussion_status(client, discussion_id, "resolved")
    return True


async def execute_talk_actions(
    actions: list[TalkAction],
    *,
    client: Any,
    source_message: dict[str, Any],
    member_id: str,
    task_text: str,
) -> list[str]:
    summaries: list[str] = []
    group_id = source_message.get("group_id") if isinstance(source_message.get("group_id"), str) else None
    source_message_id = int(source_message["id"]) if source_message.get("id") is not None else None
    group_member_ids: set[str] | None = None

    async def _group_target_known(candidate: str) -> bool:
        """Return False only when a Group lookup proves the target is not a member.

        ``None`` from ``_group_member_ids`` means the member list is unavailable;
        keep the previous behavior and let the server's strict recipient guard
        decide.  This helper does not choose a replacement recipient.
        """
        nonlocal group_member_ids
        if not group_id or not candidate:
            return True
        if group_member_ids is None:
            group_member_ids = await _group_member_ids(client, group_id)
        return group_member_ids is None or candidate in group_member_ids

    for action in actions:
        target = action.to or action.target_member_id
        if action.action_type == "send_message":
            if not target or not target.startswith("agent:"):
                summaries.append("我不能代发给这个目标；请确认要联系的 agent。")
                continue
            if not await _group_target_known(target):
                summaries.append(f"当前 Group 里没有 {target}，我不能代发；请确认是否需要我直接处理。")
                continue
            action_body = sanitize_scope_leak(action.body)
            if not action_body:
                summaries.append("我不能代发空消息；请补充要发送的内容。")
                continue
            text = f"@{target} {action_body}".strip()
            sent = await client.send_text(text, to=[target], reply_to=source_message_id, group_id=group_id)
            discussion_id = action.discussion_id
            if discussion_id is None and str(source_message.get("from") or "").startswith("agent:"):
                discussion_id = await _resolve_discussion_id(
                    client,
                    group_id=group_id,
                    member_id=member_id,
                    peer_id=target,
                    topic=_discussion_topic_from_text(task_text),
                    create_if_missing=False,
                )
            if discussion_id is None:
                discussion_id = await _resolve_discussion_id(
                    client,
                    group_id=group_id,
                    member_id=member_id,
                    peer_id=target,
                    topic=_discussion_topic_from_text(action_body or task_text),
                    create_if_missing=True,
                    root_message_id=int(sent["id"]) if sent and sent.get("id") is not None else source_message_id,
                    requester_id=member_id,
                    assignee_id=target,
                    scope_text=action_body,
                )
            existing_turns = await _list_discussion_turns(client, discussion_id)
            demand_round = action.round_index or min(_next_demand_round(existing_turns), 2)
            effective_stance = infer_discussion_stance(task_text, action_body, default=action.stance or "question")
            await _append_discussion_turn(
                client,
                discussion_id=discussion_id,
                message_id=int(sent["id"]),
                stance=effective_stance,
                target_member_id=target,
                turn_kind="demand",
                round_index=demand_round,
            )
            await _resolve_if_discussion_initiator(
                client,
                discussion_id=discussion_id,
                group_id=group_id,
                member_id=member_id,
                stance=effective_stance,
            )
            summaries.append(f"sent message to {target}")
        elif action.action_type == "escalate_to_human":
            if not target or not target.startswith("human:"):
                target = await _find_human_reviewer(client, group_id)
            if not target or not target.startswith("human:"):
                summaries.append("escalate_to_human skipped: target must be a human member")
                continue

            if not await _group_target_known(target):
                summaries.append(
                    f"未通知人类 {target}：该收件人不在当前群，请确认正确成员。"
                )
                continue
            action_body = sanitize_scope_leak(action.body or "请你做最终判断。")
            discussion_id = action.discussion_id or await _resolve_discussion_id(
                client,
                group_id=group_id,
                member_id=member_id,
                peer_id=str(source_message.get("from") or ""),
                topic=_discussion_topic_from_text(task_text),
                create_if_missing=False,
            )
            sent = await client.send_text(
                f"@{target} {action_body}".strip(),
                to=[target],
                reply_to=source_message_id,
                group_id=group_id,
            )
            await _append_discussion_turn(
                client,
                discussion_id=discussion_id,
                message_id=int(sent["id"]),
                stance="escalate",
                target_member_id=target,
                turn_kind="demand",
                round_index=action.round_index or 2,
            )
            await _update_discussion_status(client, discussion_id, "escalated")
            summaries.append(f"escalated to {target}")
        elif action.action_type == "final_to_human":
            if not target or not target.startswith("human:"):
                target = await _find_human_reviewer(client, group_id)
            if not target or not target.startswith("human:"):
                summaries.append("final_to_human skipped: target must be a human member")
                continue

            if not await _group_target_known(target):
                summaries.append(
                    f"未发送最终答复给 {target}：该收件人不在当前群，请确认正确成员。"
                )
                continue
            action_body = sanitize_scope_leak(action.body)
            if not action_body:
                summaries.append("final_to_human skipped: message body is empty")
                continue
            discussion_id = action.discussion_id or await _resolve_discussion_id(
                client,
                group_id=group_id,
                member_id=member_id,
                peer_id=str(source_message.get("from") or ""),
                topic=_discussion_topic_from_text(task_text),
                create_if_missing=False,
            )
            sent = await client.send_text(
                f"@{target} {action_body}".strip(),
                to=[target],
                reply_to=source_message_id,
                group_id=group_id,
            )
            await _append_discussion_turn(
                client,
                discussion_id=discussion_id,
                message_id=int(sent["id"]),
                stance=action.stance or "answer",
                target_member_id=target,
                turn_kind="reply",
                round_index=action.round_index or 1,
            )
            await _update_discussion_status(client, discussion_id, "resolved")
            summaries.append(f"sent final answer to {target}")
    return summaries


def decode_subprocess_output(data: bytes) -> str:
    if not data:
        return ""

    return "".join(decode_subprocess_output_chunk(chunk) for chunk in data.splitlines(keepends=True))


def decode_subprocess_output_chunk(data: bytes) -> str:
    if not data:
        return ""

    encodings = ["utf-8", "utf-8-sig", locale.getpreferredencoding(False)]
    if os.name == "nt":
        encodings.extend(["mbcs", "gbk", "cp936"])

    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, encoding in enumerate(encodings):
        if not encoding or encoding.lower() in seen:
            continue
        seen.add(encoding.lower())
        try:
            text = data.decode(encoding, errors="replace")
        except LookupError:
            continue
        candidates.append((text.count("\ufffd"), index, text))

    if not candidates:
        return data.decode("utf-8", errors="replace")
    return min(candidates, key=lambda item: (item[0], item[1]))[2]


def is_process_cleanup_noise(line: str) -> bool:
    stripped = line.strip()
    if WINDOWS_TASKKILL_EN_RE.match(stripped):
        return True
    if WINDOWS_TASKKILL_ZH_RE.match(stripped):
        return True
    return stripped.startswith(MOJIBAKE_TASKKILL_PREFIX) and "PID " in stripped


def clean_cli_output(text: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    kept = [line for line in lines if not is_process_cleanup_noise(line)]
    return "\n".join(kept).strip()


def _kimi_content_text(content: Any) -> str:
    """Extract visible text from one Kimi Code stream-json content value."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict) and str(item.get("type") or "") == "text":
            text = str(item.get("text") or "").strip()
        else:
            text = ""
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def extract_kimi_final_assistant(output: str) -> str | None:
    """Return the final Assistant text from Kimi Code JSONL.

    ``None`` means the output was not stream-json and should be left untouched.
    An empty string means valid JSONL was received but contained no visible
    Assistant message.
    """
    parsed_json = False
    assistant_messages: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        parsed_json = True
        if str(payload.get("role") or "").lower() != "assistant":
            continue
        visible = _kimi_content_text(payload.get("content"))
        if visible:
            assistant_messages.append(visible)
    if not parsed_json:
        return None
    return assistant_messages[-1] if assistant_messages else ""


def normalize_runtime_result(result: CliRunResult, *, runtime: str) -> CliRunResult:
    """Normalize runtime-specific stdout into the bridge's final-text contract."""
    if runtime.strip().lower() not in {"kimi", "kimi-code", "kimi_code"}:
        return result
    extracted = extract_kimi_final_assistant(result.stdout)
    if extracted is None:
        return result
    return CliRunResult(
        returncode=result.returncode,
        stdout=extracted,
        stderr=result.stderr,
        timed_out=result.timed_out,
    )


def _uses_compact_prompt(runtime: str, member_id: str) -> bool:
    return runtime.strip().lower() in COMPACT_PROMPT_RUNTIMES or member_id in COMPACT_PROMPT_MEMBERS


def should_handle_message(
    message: dict[str, Any],
    member_id: str,
    *,
    respond_to_broadcast: bool = False,
) -> bool:
    if message.get("revoked"):
        return False
    if message.get("type") != "text":
        return False
    if message.get("from") == member_id:
        return False
    if not (message.get("content") or "").strip():
        return False

    recipients = message.get("to")
    if isinstance(recipients, list) and member_id in recipients:
        return True
    return recipients is None and respond_to_broadcast


def _task_hall_message_text(message: dict[str, Any]) -> str:
    message_id = message.get("id") or "unknown"
    sender = message.get("from") or "unknown"
    if message.get("revoked"):
        return f"[消息 #{message_id}] {sender}: [已撤回]"

    message_type = str(message.get("type") or "text")
    if message_type == "file":
        filename = message.get("filename") or message.get("content") or "未命名文件"
        mime = message.get("mime") or "unknown"
        size = message.get("size_bytes")
        size_text = f", {size} bytes" if size is not None else ""
        caption = str(message.get("caption") or "").strip()
        caption_text = f"\n  附言: {caption}" if caption else ""
        return f"[消息 #{message_id}] {sender}: [文件: {filename}, {mime}{size_text}]{caption_text}"

    content = str(message.get("content") or "").strip() or "[空消息]"
    return f"[消息 #{message_id}] {sender}: {content}"


def format_task_hall_history(messages: Sequence[dict[str, Any]]) -> str:
    """Render the complete, chronological Task Hall transcript for model replay."""
    if not messages:
        return "（Task Hall 暂无消息）"
    return "\n".join(_task_hall_message_text(message) for message in messages)


def format_task_quality_context(context: dict[str, Any] | None) -> str:
    """Render relation-granted, read-only context for review/test/rework tasks."""
    if not context:
        return ""

    sections: list[str] = []
    for heading, key in (
        ("关联任务", "related_tasks"),
        ("触发门禁任务", "trigger_tasks"),
    ):
        entries = context.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            relation = entry.get("relation") if isinstance(entry.get("relation"), dict) else {}
            task = entry.get("task") if isinstance(entry.get("task"), dict) else {}
            messages = entry.get("messages") if isinstance(entry.get("messages"), list) else []
            task_id = task.get("id") or "unknown"
            task_kind = task.get("task_kind") or "general"
            relation_type = relation.get("relation_type") or "related"
            title = str(task.get("title") or "").strip()
            title_line = f"\n标题: {title}" if title else ""
            verdict = task.get("gate_verdict")
            verdict_line = (
                f"\n结构化门禁结论: {json.dumps(verdict, ensure_ascii=False)}"
                if isinstance(verdict, dict)
                else ""
            )
            sections.append(
                f"{heading} #{task_id}（{task_kind}，关系 {relation_type}）"
                f"{title_line}\n任务原文:\n{str(task.get('content') or '').strip()}"
                f"{verdict_line}\nTask Hall 完整上下文:\n"
                f"{format_task_hall_history(messages)}"
            )
    if not sections:
        return ""
    return "\n\n".join(sections)


async def fetch_task_quality_context(client: Any, task: dict[str, Any]) -> str:
    task_kind = str(task.get("task_kind") or "general").strip().lower()
    if task_kind not in {"review", "test", "rework"}:
        return ""
    context = await client.get_task_quality_context(int(task["id"]))
    return format_task_quality_context(context)


async def fetch_complete_task_hall_history(
    client: Any,
    group_id: str | None,
    *,
    page_size: int = TASK_HALL_HISTORY_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Fetch every visible Task Hall message through stable backward pagination."""
    if not group_id:
        return []

    pages: list[list[dict[str, Any]]] = []
    before: int | None = None
    seen_first_ids: set[int] = set()
    while True:
        batch = await client.fetch_history(group_id=group_id, before=before, limit=page_size)
        if not batch:
            break
        normalized = [message for message in batch if isinstance(message, dict)]
        if not normalized:
            break
        pages.append(normalized)
        first_ids = [int(message["id"]) for message in normalized if message.get("id") is not None]
        if not first_ids or len(normalized) < page_size:
            break
        first_id = min(first_ids)
        if first_id in seen_first_ids:
            raise RuntimeError(f"Task Hall pagination did not advance before message {first_id}")
        seen_first_ids.add(first_id)
        before = first_id

    messages: list[dict[str, Any]] = []
    seen_message_ids: set[int] = set()
    for page in reversed(pages):
        for message in page:
            message_id = message.get("id")
            if message_id is None:
                messages.append(message)
                continue
            normalized_id = int(message_id)
            if normalized_id in seen_message_ids:
                continue
            seen_message_ids.add(normalized_id)
            messages.append(message)
    messages.sort(key=lambda message: int(message.get("id") or 0))
    return messages


def build_cli_task_preflight_prompt(
    task: dict[str, Any],
    *,
    member_id: str,
    workdir: Path,
    runtime: str = "cli",
    decision_tier: str | None = None,
    hall_history: str = "",
) -> str:
    """Build the pre-claim preflight prompt.

    ``decision_tier`` is accepted for backward compatibility with older callers and
    ``--decision-tier`` argv, but it is deprecated and ignored: the removed fixed
    decision/execution tier is never rendered into the prompt.
    """
    del decision_tier
    content = str(task.get("content") or "").strip()
    title = str(task.get("title") or "").strip()
    task_id = task.get("id") or "unknown"
    creator = task.get("created_by") or "unknown"
    title_block = f"标题: {title}\n" if title else ""
    history = hall_history.strip() or "（Task Hall 暂无消息）"
    output_contract = (
        "判断规则: 上面的标题和任务原文已经完整提供；Task Hall 没有补充消息本身不构成缺失。"
        "不要要求请求者重复任务，只能询问执行所必需且当前确实没有给出的具体事实。\n"
        '信息充分时只输出一行: TALK_TASK_PREFLIGHT {"action":"accept"}\n'
        '信息不足时只输出一行: TALK_TASK_PREFLIGHT {"action":"clarify","question":"集中后的必要问题"}'
    )
    if _uses_compact_prompt(runtime, member_id):
        return (
            f"你是 {member_id}。请对任务 #{task_id} 做领取前预检，不要执行任务或修改文件。\n"
            f"请求者: {creator}\n"
            f"{title_block}任务原文:\n{content}\n\n"
            f"Task Hall 完整上下文（按消息顺序）:\n{history}\n\n"
            f"{output_contract}"
        )
    return (
        f"你是 {member_id}，通过 {runtime} CLI bridge 接入 TALK。\n"
        f"Project root: {workdir}\n"
        f"请对任务 #{task_id} 做领取前预检，不要执行任务或修改文件。\n"
        f"请求者: {creator}\n"
        f"{title_block}任务原文:\n{content}\n\n"
        f"Task Hall 完整上下文（按消息顺序）:\n{history}\n\n"
        f"{output_contract}\n"
    )


def parse_task_preflight_result(result: CliRunResult) -> TaskPreflightDecision:
    if result.timed_out:
        raise RuntimeError("task preflight timed out")
    if result.returncode != 0:
        detail = clean_cli_output(result.stderr) or clean_cli_output(result.stdout)
        raise RuntimeError(f"task preflight failed: {detail or f'exit code {result.returncode}'}")

    output = clean_cli_output(result.stdout).strip()
    candidates: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("TALK_TASK_PREFLIGHT "):
            candidates.append(stripped.removeprefix("TALK_TASK_PREFLIGHT ").strip())
    decoder = json.JSONDecoder()
    for marker_match in re.finditer(r"TALK_TASK_PREFLIGHT(?:\s+|$)", output):
        marked_output = output[marker_match.end() :].lstrip()
        if not marked_output.startswith("{"):
            continue
        try:
            marked_payload, _ = decoder.raw_decode(marked_output)
        except json.JSONDecodeError:
            continue
        candidates.append(json.dumps(marked_payload, ensure_ascii=False))
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            output,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if "TALK_TASK_PREFLIGHT" in match.group(1)
    )
    if output.startswith("{") and output.endswith("}"):
        candidates.append(output)

    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        decision_payload = payload
        nested = payload.get("TALK_TASK_PREFLIGHT")
        if isinstance(nested, dict):
            decision_payload = nested
        action = str(decision_payload.get("action") or "").strip().lower()
        if action == "accept":
            return TaskPreflightDecision(action="accept")
        if action == "clarify":
            question = str(decision_payload.get("question") or "").strip()
            if question:
                return TaskPreflightDecision(action="clarify", question=question)
        if isinstance(decision_payload.get("ready"), bool):
            if decision_payload["ready"]:
                return TaskPreflightDecision(action="accept")
            question = str(
                decision_payload.get("question")
                or decision_payload.get("decision")
                or decision_payload.get("reason")
                or ""
            ).strip()
            if question:
                return TaskPreflightDecision(action="clarify", question=question)
    raise RuntimeError("task preflight did not return a valid TALK_TASK_PREFLIGHT decision")


def build_cli_prompt(
    message: dict[str, Any],
    *,
    member_id: str,
    workdir: Path,
    runtime: str = "cli",
    discussion_context: str | None = None,
    decision_tier: str | None = None,
    group_member_context: str = "",
    shared_history: str = "",
) -> str:
    """Build the group/direct-message prompt.

    ``decision_tier`` is accepted for backward compatibility with older callers and
    ``--decision-tier`` argv, but it is deprecated and ignored: no fixed
    decision/execution identity is injected into the prompt.
    """
    del decision_tier
    content = str(message.get("content") or "")
    task = strip_leading_mentions(content, member_id=member_id) or content.strip()
    context_block = f"\n\n{discussion_context}" if discussion_context else ""
    sender = message.get("from") or "unknown"

    if _uses_compact_prompt(runtime, member_id):
        # 身份在 per-call 注入,系统层是静态文本无法区分同一 runtime 的不同实例。
        # 写法刻意紧凑:身份和任务同一行,避免占据独立首行让模型陷入"自我介绍"模式,
        # 把"对你说"的动词淡化(2026-06-06 黑盒实测:独立首行 + 括号注释会让 pi 忽略任务,
        # 改成"已就位,有什么需要帮忙"式空回应)。
        #
        # discussion_context 在此**故意不注入**:那段 600+ 字的"TALK 控制上下文"
        # (assignee_id / requester_id / scope_text / remaining_auto_turns 等)是 5.x
        # 之前 scenario-1 scope 严格化时为"任务式讨论"设计的,在 function-calling +
        # 方案 D 账本的当前架构下完全冗余 —— round_index 刹车由 bridge 的
        # _can_create_deferred_file 自动执行,模型不需要看到协议字段。2026-06-06 黑盒
        # 实测:注入这段会让闲聊场景产生"已经XX啦"式元叙述(模型把寒暄当成 assignee
        # 完成的 request),信噪比被 10x 压垮。其他 runtime(legacy 文本协议)仍保留,
        # 兼容由下方分支承担。
        parts = [f"你是 {member_id}。{sender} 对你说:{task}"]
        history_line = shared_history.strip()
        if history_line:
            parts.append(history_line)
        member_line = group_member_context.strip()
        if member_line:
            parts.append(member_line)
        return "\n".join(parts)

    sender = message.get("from") or "unknown"
    message_id = message.get("id") or "unknown"
    group_id = message.get("group_id")
    group_line = f"TALK group id: {group_id}\n" if group_id else ""
    history_block = f"{shared_history.strip()}\n\n" if shared_history.strip() else ""
    return (
        f"你是 {member_id}，通过 {runtime} CLI bridge 接入 TALK。\n"
        f"{group_member_context}"
        f"Project root: {workdir}\n"
        "Answer the user's task. Keep the final response suitable for posting back into TALK.\n"
        f"{RESPONSE_STYLE_INSTRUCTIONS}"
        f"{DISCUSSION_PROTOCOL_INSTRUCTIONS}"
        "Do not mention internal bridge mechanics unless they are relevant to the task.\n\n"
        f"Sender: {sender}\n"
        f"TALK message id: {message_id}\n\n"
        f"{group_line}"
        f"{history_block}"
        "Task:\n"
        f"{task}{context_block}\n"
    )


def build_cli_task_prompt(
    task: dict[str, Any],
    *,
    member_id: str,
    workdir: Path,
    runtime: str = "cli",
    decision_tier: str | None = None,
    hall_history: str = "",
) -> str:
    """Build the queued-task prompt.

    ``decision_tier`` is accepted for backward compatibility with older callers and
    ``--decision-tier`` argv, but it is deprecated and ignored: no fixed
    decision/execution identity is injected into the prompt.
    """
    del decision_tier
    content = str(task.get("content") or "").strip()
    title = str(task.get("title") or "").strip()
    task_kind = str(task.get("task_kind") or "general").strip().lower()
    history = hall_history.strip()
    history_block = f"\n\nTask Hall 完整上下文（按消息顺序）:\n{history}" if history else ""
    gate_contract = ""
    if task_kind == "review":
        gate_contract = (
            "\n\n这是只读 Review 任务：不得修改被审结果。完成审查后，最终输出必须包含且只包含一个"
            '显式结构化结论行：TALK_GATE_VERDICT {"verdict":"approved|changes_requested|blocked",'
            '"summary":"审查摘要","findings":["具体发现"]}。'
            "`changes_requested` 或 `blocked` 的 findings 不得为空；不要从自然语言暗示结论。"
        )
    elif task_kind == "test":
        gate_contract = (
            "\n\n这是 Test 任务。完成验证后，最终输出必须包含且只包含一个显式结构化结论行："
            'TALK_GATE_VERDICT {"verdict":"passed|failed|blocked","summary":"测试摘要",'
            '"findings":["具体发现"]}。'
            "`failed` 或 `blocked` 的 findings 不得为空；不要从自然语言暗示结论。"
        )

    if _uses_compact_prompt(runtime, member_id):
        creator = task.get("created_by") or "unknown"
        task_text = f"{title}\n{content}" if title else content
        # 任务路径同样注入身份(紧凑写法,理由同 build_cli_prompt)。
        return (
            f"你是 {member_id}。{creator} 对你说:"
            f"{task_text}{history_block}{gate_contract}"
        )

    task_id = task.get("id") or "unknown"
    creator = task.get("created_by") or "unknown"
    title_block = f"Title: {title}\n" if title else ""
    return (
        f"你是 {member_id}，通过 {runtime} CLI bridge 接入 TALK。\n"
        f"Project root: {workdir}\n"
        "Answer the queued Agent task. Keep the final response suitable for posting back into TALK.\n"
        f"{RESPONSE_STYLE_INSTRUCTIONS}"
        f"{DISCUSSION_PROTOCOL_INSTRUCTIONS}"
        "Do not mention internal bridge mechanics unless they are relevant to the task.\n\n"
        f"Task creator: {creator}\n"
        f"TALK task id: {task_id}\n"
        f"{title_block}\n"
        "Task:\n"
        f"{content}\n"
        f"{history_block}\n"
        f"{gate_contract}\n"
    )


def parse_task_gate_verdict(result: CliRunResult, *, task_kind: str) -> TaskGateVerdict:
    if result.timed_out:
        raise RuntimeError("task gate command timed out")
    if result.returncode != 0:
        detail = clean_cli_output(result.stderr) or clean_cli_output(result.stdout)
        raise RuntimeError(f"task gate command failed: {detail or f'exit code {result.returncode}'}")

    output = clean_cli_output(result.stdout).strip()
    candidates: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{TASK_GATE_VERDICT_MARKER} "):
            candidates.append(stripped.removeprefix(f"{TASK_GATE_VERDICT_MARKER} ").strip())

    decoder = json.JSONDecoder()
    for marker_match in re.finditer(r"TALK_GATE_VERDICT(?:\s+|$)", output):
        marked_output = output[marker_match.end() :].lstrip()
        if not marked_output.startswith("{"):
            continue
        try:
            marked_payload, _ = decoder.raw_decode(marked_output)
        except json.JSONDecodeError:
            continue
        candidates.append(json.dumps(marked_payload, ensure_ascii=False))
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            output,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if TASK_GATE_VERDICT_MARKER in match.group(1)
    )
    if output.startswith("{") and output.endswith("}"):
        candidates.append(output)

    normalized_kind = task_kind.strip().lower()
    allowed = {
        "review": {"approved", "changes_requested", "blocked"},
        "test": {"passed", "failed", "blocked"},
    }.get(normalized_kind)
    if allowed is None:
        raise RuntimeError(f"task kind {task_kind!r} does not accept a gate verdict")

    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        nested = payload.get(TASK_GATE_VERDICT_MARKER)
        if isinstance(nested, dict):
            payload = nested
        verdict = str(payload.get("verdict") or "").strip().lower()
        summary = str(payload.get("summary") or "").strip()
        raw_findings = payload.get("findings", [])
        if verdict not in allowed or not summary or not isinstance(raw_findings, list):
            continue
        findings = tuple(
            str(finding).strip()
            for finding in raw_findings
            if str(finding).strip()
        )
        if verdict in {"changes_requested", "blocked", "failed"} and not findings:
            continue
        return TaskGateVerdict(verdict=verdict, summary=summary, findings=findings)
    raise RuntimeError("task gate output did not return a valid TALK_GATE_VERDICT decision")


def format_cli_reply(
    result: CliRunResult,
    *,
    max_chars: int = DEFAULT_MAX_REPLY_CHARS,
    bridge_label: str = "CLI bridge",
    force_one_sentence: bool = False,
    log_ref: str | None = None,
    log_write_failed: bool = False,
) -> str:
    output = clean_cli_output((result.stdout or "").strip())

    if result.timed_out:
        text = f"{bridge_label} 暂时没有返回结果，错误详情已记录。"
    elif result.returncode != 0:
        text = f"{bridge_label} 运行失败，错误详情已记录。"
    else:
        text = output or f"({bridge_label} finished without output.)"

    if log_write_failed and (result.timed_out or result.returncode != 0):
        text = f"{bridge_label} 运行失败，本地诊断日志写入失败（已降级）。"

    if force_one_sentence and not result.timed_out and result.returncode == 0:
        text = first_sentence(text)

    if len(text) > max_chars:
        remaining = len(text) - max_chars
        text = f"{text[:max_chars].rstrip()}\n\n[truncated {remaining} chars]"
    # Failure summaries may expose a stable local reference; the stack itself
    # never goes into the chat reply.  Append after truncation so the reference
    # cannot be cut away.
    if log_ref:
        text = f"{text}\n\n{runtime_diag.public_log_reference(log_ref)}"
    return text


async def run_cli_command(
    command: str | Sequence[str],
    prompt: str,
    *,
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    prompt_transport: str = "stdin",
) -> CliRunResult:
    args = parse_command(command) if isinstance(command, str) else list(command)
    if not args:
        raise ValueError("CLI command cannot be empty")
    if prompt_transport not in PROMPT_TRANSPORTS:
        raise ValueError(f"prompt transport must be one of: {', '.join(sorted(PROMPT_TRANSPORTS))}")
    args = resolve_command_executable(args)

    stdin = asyncio.subprocess.PIPE if prompt_transport == "stdin" else asyncio.subprocess.DEVNULL
    if prompt_transport == "argv":
        args = [*args, prompt]

    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=stdin,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
    )

    try:
        input_data = prompt.encode("utf-8") if prompt_transport == "stdin" else None
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input_data),
            timeout=timeout,
        )
        return CliRunResult(
            returncode=int(process.returncode or 0),
            stdout=decode_subprocess_output(stdout),
            stderr=decode_subprocess_output(stderr),
        )
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return CliRunResult(
            returncode=-1,
            stdout=decode_subprocess_output(stdout),
            stderr=decode_subprocess_output(stderr),
            timed_out=True,
        )
    except asyncio.CancelledError:
        process.kill()
        await process.communicate()
        raise


class TaskLeaseLostError(RuntimeError):
    """Raised when a runner can no longer prove ownership of a task claim."""


class TaskPreflightError(RuntimeError):
    """Raised when one Task Hall preflight attempt cannot produce a decision."""


def _effective_task_claim_check_interval(*, lease_seconds: int, heartbeat_interval: float) -> float:
    """Keep claim/control probes frequent enough to honor the five-second stop contract."""
    if lease_seconds <= 0 or heartbeat_interval <= 0:
        raise ValueError("task lease and heartbeat intervals must be positive")
    return min(
        heartbeat_interval,
        MAX_TASK_CONTROL_CHECK_INTERVAL,
        max(0.5, lease_seconds / 3),
    )


async def _task_heartbeat_loop(
    *,
    client: Any,
    task_id: int,
    claim_token: str,
    lease_seconds: int,
    heartbeat_interval: float,
) -> None:
    from TALK.client.exceptions import TalkValidationError

    loop = asyncio.get_running_loop()
    deadline = loop.time() + lease_seconds
    # The heartbeat endpoint also validates the root control state atomically.
    # A pause/checkpoint/cancel revokes the claim with 409, so this probe doubles
    # as the runner's bounded control check while the local command is running.
    interval = _effective_task_claim_check_interval(
        lease_seconds=lease_seconds,
        heartbeat_interval=heartbeat_interval,
    )
    last_error: Exception | None = None
    while True:
        await asyncio.sleep(min(interval, max(0.05, deadline - loop.time())))
        try:
            await client.heartbeat_task(
                task_id,
                claim_token=claim_token,
                lease_seconds=lease_seconds,
            )
        except TalkValidationError as exc:
            if exc.status_code in {404, 409}:
                raise TaskLeaseLostError(f"task {task_id} claim is no longer active") from exc
            last_error = exc
        except Exception as exc:
            last_error = exc
        else:
            deadline = loop.time() + lease_seconds
            last_error = None
            continue

        if loop.time() >= deadline:
            raise TaskLeaseLostError(f"task {task_id} heartbeat failed until its local lease deadline") from last_error


def _start_task_heartbeat(
    *,
    client: Any,
    task_id: int,
    claim_token: str | None,
    lease_seconds: int,
    heartbeat_interval: float,
) -> asyncio.Task[None] | None:
    if not claim_token:
        return None
    _effective_task_claim_check_interval(
        lease_seconds=lease_seconds,
        heartbeat_interval=heartbeat_interval,
    )
    return asyncio.create_task(
        _task_heartbeat_loop(
            client=client,
            task_id=task_id,
            claim_token=claim_token,
            lease_seconds=lease_seconds,
            heartbeat_interval=heartbeat_interval,
        )
    )


async def _raise_if_task_lease_lost(heartbeat_task: asyncio.Task[None] | None) -> None:
    if heartbeat_task is not None and heartbeat_task.done():
        await heartbeat_task


async def _run_while_task_lease_active(
    operation: Awaitable[Any],
    heartbeat_task: asyncio.Task[None] | None,
) -> Any:
    if heartbeat_task is None:
        return await operation
    operation_task = asyncio.create_task(operation)
    try:
        done, _ = await asyncio.wait({operation_task, heartbeat_task}, return_when=asyncio.FIRST_COMPLETED)
        if heartbeat_task in done:
            operation_task.cancel()
            await asyncio.gather(operation_task, return_exceptions=True)
            await heartbeat_task
        return await operation_task
    finally:
        if not operation_task.done():
            operation_task.cancel()
        await asyncio.gather(operation_task, return_exceptions=True)


async def _stop_task_heartbeat(heartbeat_task: asyncio.Task[None] | None) -> None:
    if heartbeat_task is None:
        return
    if heartbeat_task.done():
        try:
            await heartbeat_task
        except TaskLeaseLostError:
            pass
        return
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass


_TASK_RUNNER_ACTIONABLE_WORKFLOWS = {"assigned", "clarification_answered", "accepted"}


def _task_preflight_question_marker(task: dict[str, Any]) -> str:
    task_id = int(task["id"])
    round_index = int(task.get("clarification_round_count") or 0) + 1
    return f"【TALK 自动预检｜任务 #{task_id}｜澄清轮次 {round_index}】"


def _find_pending_preflight_question(
    messages: Sequence[dict[str, Any]],
    *,
    member_id: str,
    marker: str,
) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("revoked") or message.get("type") != "text":
            continue
        if str(message.get("from") or "") != member_id:
            continue
        if str(message.get("content") or "").startswith(marker):
            return message
    return None


async def _prepare_task_before_claim(
    task: dict[str, Any],
    *,
    client: Any,
    member_id: str,
    workdir: Path,
    preflight_command: str | Sequence[str],
    timeout: int,
    runtime: str,
    prompt_transport: str,
    decision_tier: str | None = None,
    command_runner: Any,
    diagnostics: Any | None = None,
    preflight_attempt: int = 1,
    budgets: dict[str, Any] | None = None,
    preflight_base_context: str | None = None,
) -> tuple[dict[str, Any] | None, str, bool]:
    """Run Task Hall preflight and return (ready_task, replay_context, workflow_advanced).

    ``decision_tier`` is a deprecated compatibility parameter: it is accepted and
    ignored and never reaches the prompt.
    """
    del decision_tier
    from TALK.client.exceptions import TalkValidationError

    hall_group_id = str(task.get("hall_group_id") or "").strip()
    if not hall_group_id:
        return task, "", False

    history = await fetch_complete_task_hall_history(client, hall_group_id)
    quality_context = await fetch_task_quality_context(client, task)
    replay_context = format_task_hall_history(history)
    if quality_context:
        replay_context = (
            f"{replay_context}\n\n"
            "关系授权的只读质量上下文：\n"
            f"{quality_context}"
        )
    workflow_status = str(task.get("workflow_status") or "assigned")
    if workflow_status == "accepted":
        return task, replay_context, False
    if workflow_status not in {"assigned", "clarification_answered"}:
        return None, replay_context, False

    task_id = int(task["id"])
    marker = _task_preflight_question_marker(task)
    pending_question = _find_pending_preflight_question(
        history,
        member_id=member_id,
        marker=marker,
    )
    if pending_question is not None and pending_question.get("id") is not None:
        try:
            await client.request_task_clarification(
                task_id,
                question_message_id=int(pending_question["id"]),
            )
            return None, replay_context, True
        except TalkValidationError as exc:
            if exc.status_code != 409:
                raise
            current = await client.get_task(task_id)
            if str(current.get("workflow_status") or "") in {"clarification_requested", "needs_decision"}:
                return None, replay_context, True
            return None, replay_context, False

    # 预检仍走原只读、非持久化命令，不进入正式会话或累计交办次数。
    # 仅预检副本补基础合同；正式续轮的增量正文与任务账本不被改写。
    preflight_task = task
    if preflight_base_context is not None:
        continuation_note = ""
        execution_meta = task.get("execution_session") or {}
        if (runtime == "codex" and execution_meta.get("runtime") == "codex"
                and type(execution_meta.get("base_task_id")) is int
                and execution_meta["base_task_id"] > 0 and not execution_meta.get("force_new")):
            continuation_note = (
                "[[执行会话续轮预检边界]]\n"
                "本轮通过已核基础合同引用声明同功能续接；正式执行器随后独立核验原生窗口、权限、历史和占比，"
                "满足条件才恢复该窗口。此隔离预检不复制旧原生记录，也不计交办轮次。"
                "仅因任务引用上一轮对话而本预检未携带旧记录，不要求用户重传；预检就绪只表示可进入正式规划，"
                "不能承诺一定续用、越过阈值或补造事实。其它新增必要参数缺失仍正常澄清。\n\n"
            )
        preflight_task = {**task, "content": (
            continuation_note + "[[已核冻结基础合同，仅供本次只读预检]]\n"
            + preflight_base_context + "\n\n[[本次增量]]\n"
            + str(task.get("content") or "")
        )}
    prompt = build_cli_task_preflight_prompt(
        preflight_task,
        member_id=member_id,
        workdir=workdir,
        runtime=runtime,
        hall_history=replay_context,
    )
    timeline = StageTimeline(diagnostics)
    preflight_operation = timeline.start(
        "task_model_preflight",
        phase="task_preflight",
        task_id=task_id,
        attempt=preflight_attempt,
        budgets=budgets,
    )
    repair_operation = None
    initial_result: CliRunResult | None = None
    repaired_result: CliRunResult | None = None
    try:
        initial_result = await command_runner(
            preflight_command,
            prompt,
            cwd=workdir,
            timeout=timeout,
            prompt_transport=prompt_transport,
        )
        initial_result = normalize_runtime_result(initial_result, runtime=runtime)
        try:
            decision = parse_task_preflight_result(initial_result)
        except RuntimeError:
            preflight_operation.finish(
                "failed",
                returncode=initial_result.returncode,
                timeout=bool(initial_result.timed_out),
                message="protocol_invalid",
            )
            if initial_result.timed_out or initial_result.returncode != 0:
                raise
            repair_prompt = (
                f"{prompt}\n\n"
                "你上一次的输出没有遵守协议。请重新判断，并且禁止解释、禁止 Markdown "
                "代码围栏、禁止嵌套 JSON；只输出上面约定的一行 TALK_TASK_PREFLIGHT。"
            )
            repair_operation = timeline.start(
                "task_model_preflight_repair",
                phase="task_preflight",
                task_id=task_id,
                attempt=preflight_attempt,
                budgets=budgets,
            )
            repaired_result = await command_runner(
                preflight_command,
                repair_prompt,
                cwd=workdir,
                timeout=timeout,
                prompt_transport=prompt_transport,
            )
            repaired_result = normalize_runtime_result(
                repaired_result, runtime=runtime
            )
            decision = parse_task_preflight_result(repaired_result)
    except asyncio.CancelledError:
        preflight_operation.finish("canceled")
        if repair_operation is not None:
            repair_operation.finish("canceled")
        raise
    except Exception as exc:
        preflight_operation.finish(
            "failed",
            returncode=initial_result.returncode if initial_result is not None else None,
            timeout=bool(initial_result.timed_out) if initial_result is not None else None,
        )
        if repair_operation is not None:
            repair_operation.finish(
                "failed",
                returncode=(
                    repaired_result.returncode
                    if repaired_result is not None
                    else None
                ),
                timeout=(
                    bool(repaired_result.timed_out)
                    if repaired_result is not None
                    else None
                ),
            )
        wrapped = TaskPreflightError(f"task {task_id} preflight failed: {exc}")
        # The CLI exception can carry the full prompt (and therefore the task
        # text).  Keep it in memory for the diagnostics redactor only; the
        # exception message itself is never written unredacted.
        setattr(wrapped, "diagnostic_sensitive_values", (prompt,))
        raise wrapped from exc
    else:
        preflight_operation.finish(
            "succeeded",
            returncode=initial_result.returncode,
            timeout=bool(initial_result.timed_out),
        )
        if repair_operation is not None:
            repair_operation.finish(
                "succeeded",
                returncode=repaired_result.returncode,
                timeout=bool(repaired_result.timed_out),
            )
    if decision.action == "accept":
        accept_operation = timeline.start(
            "task_accept",
            phase="task_preflight",
            task_id=task_id,
            attempt=preflight_attempt,
            budgets=budgets,
        )
        try:
            accepted = await client.accept_task(task_id)
        except TalkValidationError as exc:
            accept_operation.finish("failed")
            if exc.status_code != 409:
                raise
            current = await client.get_task(task_id)
            if str(current.get("workflow_status") or "") == "accepted":
                return current, replay_context, True
            return None, replay_context, False
        except asyncio.CancelledError:
            accept_operation.finish("canceled")
            raise
        except Exception:
            accept_operation.finish("failed")
            raise
        accept_operation.finish("succeeded")
        return accepted, replay_context, True

    creator = str(task.get("created_by") or "").strip()
    if not creator or not decision.question:
        raise RuntimeError(f"task {task_id} preflight clarification is missing a requester or question")
    question = await client.send_text(
        f"{marker}\n{decision.question}",
        to=[creator],
        group_id=hall_group_id,
    )
    question_message_id = int(question["id"])
    try:
        await client.request_task_clarification(
            task_id,
            question_message_id=question_message_id,
        )
        return None, replay_context, True
    except TalkValidationError as exc:
        if exc.status_code != 409:
            raise
        current = await client.get_task(task_id)
        if str(current.get("workflow_status") or "") in {"clarification_requested", "needs_decision"}:
            return None, replay_context, True
        return None, replay_context, False


async def _handle_execution_session_claimed(
    claimed: dict[str, Any],
    *,
    client: Any,
    member_id: str,
    workdir: Path,
    command: str | Sequence[str],
    timeout: int,
    max_reply_chars: int,
    bridge_label: str,
    claim_token: str | None,
    heartbeat_task: asyncio.Task[None] | None,
    execution_context: Mapping[str, Any],
    diagnostics: Any | None,
    replay_context: str,
) -> bool:
    """292：claim 后的执行会话分支；结果发送/完成仍走原任务账本。"""

    from bridges.dsh_execution_channel import (
        ExecutionSessionRunError,
        run_execution_session_task,
    )
    if (claimed.get("execution_session") or {}).get("runtime") == "codex":
        from bridges.codex_execution_channel import run_execution_session_task

    task_id = int(claimed["id"])
    creator = claimed.get("created_by")
    if isinstance(command, str):
        command_args: str | Sequence[str] = parse_command(command)
    else:
        command_args = list(command)
    state: dict[str, Any] | None = None
    completion_status = "failed"
    last_error: str | None = None
    try:
        try:
            outcome = await _run_while_task_lease_active(run_execution_session_task(
                task=claimed,
                client=client,
                member_id=member_id,
                workdir=workdir,
                command=command_args,
                timeout=timeout,
                launch_id=execution_context.get("launch_id"),
                project_id=execution_context.get("project_id"),
                binding_snapshot=claimed.get("target_binding_snapshot"),
                hall_history=replay_context,
                diagnostics=diagnostics,
                store_override=execution_context.get("store_override"),
                native_package_root=execution_context.get("native_package_root"),
                runner=execution_context.get("runner"),
            ), heartbeat_task)
        except TaskLeaseLostError:
            raise
        except asyncio.CancelledError:
            raise
        except ExecutionSessionRunError as exc:
            reason = exc.reason_code
            completion_status = "failed"
            reply = (
                f"{bridge_label} 执行会话未完成（{reason}）。"
                "本次没有自动重跑模型；TALK 任务记录与已有窗口状态已保留。"
            )
            last_error = f"execution session failed: {reason}"
            state = {
                "schema": "talk-execution-session-state-1",
                "version": 1,
                "status": "failed",
                "decision": "unconfirmed",
                "reason_code": reason,
                "limitations": "未取得可核任务回执；计数与窗口以持久账本为准，未自动重跑模型。",
            }
        except Exception:
            completion_status = "failed"
            reply = (
                f"{bridge_label} 执行会话运行失败，错误详情已记录。"
                "本次没有自动重跑模型。"
            )
            last_error = "execution session failed before confirmed delivery"
            state = {
                "schema": "talk-execution-session-state-1",
                "version": 1,
                "status": "failed",
                "decision": "unconfirmed",
                "reason_code": "runner_failed",
                "limitations": "未取得可核任务回执；计数与窗口以持久账本为准，未自动重跑模型。",
            }
        else:
            reply = str(outcome.reply or "").strip()
            completion_status = outcome.completion_status
            last_error = outcome.last_error
            state = outcome.state
        reply = reply or f"{bridge_label} 执行会话已完成，但没有可展示文本。"
        if len(reply) > max_reply_chars:
            reply = reply[: max(0, max_reply_chars - 20)].rstrip() + "\n…（结果已截断）"

        await _raise_if_task_lease_lost(heartbeat_task)
        result_message_id: int | None = None
        if creator:
            result_message = await client.send_text(
                reply,
                to=[str(creator)],
                group_id=claimed.get("hall_group_id"),
            )
            result_message_id = int(result_message["id"])
        await _raise_if_task_lease_lost(heartbeat_task)
        completion_kwargs: dict[str, Any] = {
            "status": completion_status,
            "result_message_id": result_message_id,
            "last_error": last_error,
            "execution_session_state": state,
        }
        if claim_token is not None:
            completion_kwargs["claim_token"] = claim_token
        await client.complete_task(task_id, **completion_kwargs)
        if diagnostics is not None:
            try:
                diagnostics.record_event(
                    "execution_session_completed",
                    stage="execution_session",
                    task_id=task_id,
                    message=completion_status,
                    extra={
                        "native_session_id": (state or {}).get("native_session_id"),
                        "reused": (state or {}).get("reused"),
                        "confirmed_count": (state or {}).get("confirmed_count"),
                    },
                )
            except Exception:
                pass
        return True
    except TaskLeaseLostError:
        return False
    except asyncio.CancelledError:
        raise
    finally:
        await _stop_task_heartbeat(heartbeat_task)


async def handle_queued_task(
    task: dict[str, Any],
    *,
    client: Any,
    member_id: str,
    workdir: Path,
    instance_id: str,
    command: str | Sequence[str],
    timeout: int,
    max_reply_chars: int,
    runtime: str = "cli",
    bridge_label: str = "CLI bridge",
    prompt_transport: str = "stdin",
    decision_tier: str | None = None,
    preflight_command: str | Sequence[str] | None = None,
    command_runner: Any | None = None,
    lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
    heartbeat_interval: float = DEFAULT_TASK_HEARTBEAT_INTERVAL,
    diagnostics: Any | None = None,
    preflight_attempt: int = 1,
    execution_context: Mapping[str, Any] | None = None,
) -> bool:
    """Preflight, claim, and execute one task; return False when no action was acquired.

    ``decision_tier`` is a deprecated compatibility parameter: accepted and ignored
    (the removed fixed tier never changes preflight, prompt or execution behavior).
    """
    del decision_tier
    from TALK.client.exceptions import TalkValidationError

    _clear_deprecated_decision_tier_env()
    task_id = int(task["id"])
    execution_task = bool(
        execution_context is not None
        and str(runtime).lower() in {"dsh", "codex"}
        and isinstance(task.get("execution_session"), dict)
    )
    runner = command_runner or run_cli_command
    budgets = _diag_budgets(
        cli_timeout=timeout,
        http_timeout=_diag_http_timeout(client),
        lease_seconds=lease_seconds,
        heartbeat_interval=heartbeat_interval,
    )
    first_log_id: str | None = None
    try:
        preflight_base_context = None
        if execution_task:
            from bridges.dsh_execution_channel import _load_base_contract
            try:
                preflight_base_context = (await _load_base_contract(
                    client, task, task["execution_session"]
                ))["text"]
            except Exception as exc:
                raise TaskPreflightError("execution session base preflight unavailable") from exc
        ready_task, replay_context, workflow_advanced = await _prepare_task_before_claim(
            task,
            client=client,
            member_id=member_id,
            workdir=workdir,
            preflight_command=preflight_command or command,
            timeout=timeout,
            runtime=runtime,
            prompt_transport=prompt_transport,
            command_runner=runner,
            diagnostics=diagnostics,
            preflight_attempt=preflight_attempt,
            budgets=budgets,
            preflight_base_context=preflight_base_context,
        )
    except asyncio.CancelledError:
        if diagnostics is not None:
            diagnostics.record_event(
                "task_cancelled",
                severity="warning",
                stage="task_preflight",
                task_id=task_id,
                cancel_category="asyncio_cancelled",
                budgets=budgets,
            )
        raise
    except TaskPreflightError as exc:
        if diagnostics is not None:
            first_log_id = diagnostics.record_exception(
                exc,
                event="preflight_failed",
                stage="task_preflight",
                task_id=task_id,
                budgets=budgets,
                sensitive_values=(
                    *getattr(exc, "diagnostic_sensitive_values", ()),
                    str(task.get("content") or ""),
                ),
            )
            if first_log_id:
                setattr(exc, "diagnostic_log_id", first_log_id)
        raise
    except Exception as exc:
        if diagnostics is not None:
            first_log_id = diagnostics.record_exception(
                exc,
                event="preflight_exception",
                stage="task_preflight",
                task_id=task_id,
                budgets=budgets,
            )
        raise
    if ready_task is None:
        return workflow_advanced

    claim_operation = StageTimeline(diagnostics).start(
        "task_claim",
        phase="task",
        task_id=task_id,
        budgets=budgets,
    )
    try:
        claimed = await client.claim_task(task_id, instance_id=instance_id, lease_seconds=lease_seconds)
    except TalkValidationError as exc:
        claim_operation.finish("failed")
        if exc.status_code == 409:
            if diagnostics is not None:
                diagnostics.record_event(
                    "task_claim_conflict",
                    severity="warning",
                    stage="task_claim",
                    task_id=task_id,
                    message=f"claim conflict: HTTP {exc.status_code}",
                    budgets=budgets,
                )
            return False
        if diagnostics is not None:
            first_log_id = diagnostics.record_exception(
                exc,
                event="task_claim_failed",
                stage="task_claim",
                task_id=task_id,
                budgets=budgets,
            )
        raise
    except asyncio.CancelledError:
        claim_operation.finish("canceled")
        if diagnostics is not None:
            diagnostics.record_event(
                "task_cancelled",
                severity="warning",
                stage="task_claim",
                task_id=task_id,
                cancel_category="asyncio_cancelled",
                budgets=budgets,
            )
        raise
    except Exception as exc:
        claim_operation.finish("failed")
        if diagnostics is not None:
            first_log_id = diagnostics.record_exception(
                exc,
                event="task_claim_failed",
                stage="task_claim",
                task_id=task_id,
                budgets=budgets,
            )
        raise
    claim_operation.finish("succeeded")

    if diagnostics is not None:
        diagnostics.record_event(
            "task_claimed",
            stage="task_claim",
            task_id=task_id,
            budgets=budgets,
        )

    claim_token = str(claimed.get("claim_token") or "") or None
    heartbeat_task = _start_task_heartbeat(
        client=client,
        task_id=task_id,
        claim_token=claim_token,
        lease_seconds=lease_seconds,
        heartbeat_interval=heartbeat_interval,
    )
    if (
        execution_task
        and execution_context is not None
        and isinstance(claimed.get("execution_session"), dict)
    ):
        return await _handle_execution_session_claimed(
            claimed,
            client=client,
            member_id=member_id,
            workdir=workdir,
            command=execution_context.get("command", command),
            timeout=timeout,
            max_reply_chars=max_reply_chars,
            bridge_label=bridge_label,
            claim_token=claim_token,
            heartbeat_task=heartbeat_task,
            execution_context=execution_context,
            diagnostics=diagnostics,
            replay_context=replay_context,
        )
    gate_verdict_payload: dict[str, Any] | None = None
    prompt = ""
    task_text = ""
    try:
        try:
            task_text = str(claimed.get("content") or "")
            task_kind = str(claimed.get("task_kind") or "general").strip().lower()
            prompt = build_cli_task_prompt(
                claimed,
                member_id=member_id,
                workdir=workdir,
                runtime=runtime,
                hall_history=replay_context,
            )
            cli_operation = StageTimeline(diagnostics).start(
                "task_cli",
                phase="task",
                task_id=task_id,
                budgets=budgets,
            )
            try:
                result = await _run_while_task_lease_active(
                    runner(
                        command,
                        prompt,
                        cwd=workdir,
                        timeout=timeout,
                        prompt_transport=prompt_transport,
                    ),
                    heartbeat_task,
                )
                result = normalize_runtime_result(result, runtime=runtime)
            except TaskLeaseLostError:
                cli_operation.finish("interrupted")
                raise
            except asyncio.CancelledError:
                cli_operation.finish("canceled")
                raise
            except Exception:
                cli_operation.finish("failed")
                raise
            if result.timed_out or result.returncode != 0:
                cli_operation.finish(
                    "failed",
                    returncode=result.returncode,
                    timeout=bool(result.timed_out),
                )
            else:
                cli_operation.finish(
                    "succeeded",
                    returncode=result.returncode,
                    timeout=False,
                )
            cli_failure_log_id: str | None = None
            if result.timed_out or result.returncode != 0:
                cli_failure_log_id = _record_cli_failure(
                    diagnostics,
                    result,
                    stage="task_cli",
                    task_id=task_id,
                    timeout=timeout, budgets=budgets,
                    client=client,
                    sensitive_values=(task_text, prompt, claim_token),
                )
                if cli_failure_log_id is not None and first_log_id is None:
                    first_log_id = cli_failure_log_id
            if task_kind in {"review", "test"} and not result.timed_out and result.returncode == 0:
                try:
                    gate_verdict = parse_task_gate_verdict(result, task_kind=task_kind)
                except RuntimeError:
                    repair_prompt = (
                        f"{prompt}\n\n"
                        "你上一次的门禁输出没有遵守协议。不要修改任何文件，也不要解释格式；"
                        "请重新检查现有结论，只输出一行约定的 TALK_GATE_VERDICT JSON。"
                    )
                    repair_operation = StageTimeline(diagnostics).start(
                        "task_cli_gate_repair",
                        phase="task",
                        task_id=task_id,
                        budgets=budgets,
                    )
                    try:
                        result = await _run_while_task_lease_active(
                            runner(
                                command,
                                repair_prompt,
                                cwd=workdir,
                                timeout=timeout,
                                prompt_transport=prompt_transport,
                            ),
                            heartbeat_task,
                        )
                        result = normalize_runtime_result(
                            result, runtime=runtime
                        )
                    except TaskLeaseLostError:
                        repair_operation.finish("interrupted")
                        raise
                    except asyncio.CancelledError:
                        repair_operation.finish("canceled")
                        raise
                    except Exception:
                        repair_operation.finish("failed")
                        raise
                    if result.timed_out or result.returncode != 0:
                        repair_operation.finish(
                            "failed",
                            returncode=result.returncode,
                            timeout=bool(result.timed_out),
                        )
                    else:
                        repair_operation.finish(
                            "succeeded",
                            returncode=result.returncode,
                            timeout=False,
                        )
                    if result.timed_out or result.returncode != 0:
                        cli_failure_log_id = _record_cli_failure(
                            diagnostics,
                            result,
                            stage="task_cli_gate_repair",
                            task_id=task_id,
                            timeout=timeout, budgets=budgets,
                            client=client,
                            sensitive_values=(task_text, prompt, repair_prompt, claim_token),
                        )
                        if cli_failure_log_id is not None and first_log_id is None:
                            first_log_id = cli_failure_log_id
                    gate_verdict = parse_task_gate_verdict(result, task_kind=task_kind)
                gate_verdict_payload = gate_verdict.as_payload()
            reply = format_cli_reply(
                result,
                max_chars=max_reply_chars,
                bridge_label=bridge_label,
                force_one_sentence=wants_one_sentence(task_text),
                log_ref=cli_failure_log_id if result.timed_out or result.returncode != 0 else None,
                log_write_failed=bool(
                    diagnostics is not None
                    and (result.timed_out or result.returncode != 0)
                    and cli_failure_log_id is None
                ),
            )
            if (
                task_kind not in {"review", "test"}
                and (runtime.lower() == "pi" or member_id == "agent:pi")
                and not result.timed_out
                and result.returncode == 0
            ):
                reply = normalize_pi_reply_language(task_text, reply)
            completion_status = "failed" if result.timed_out or result.returncode != 0 else "succeeded"
            last_error = None
            if completion_status == "failed":
                if diagnostics is not None:
                    # Public error fields carry only a bounded sanitized
                    # summary + reference; the local JSONL record is the
                    # place for the diagnostic envelope.
                    detail = _diag_cli_failure_message(result, diagnostics=diagnostics, sensitive_values=(task_text, prompt, claim_token))
                else:
                    detail = "\n".join(
                        part for part in (clean_cli_output(result.stderr), clean_cli_output(result.stdout)) if part
                    )
                detail = _diag_public_text(
                    diagnostics,
                    detail,
                    sensitive_values=(task_text, prompt, claim_token),
                    max_chars=800,
                )
                last_error = detail or reply
                if cli_failure_log_id:
                    last_error = _with_log_ref(str(last_error), cli_failure_log_id)
        except TaskLeaseLostError:
            raise
        except asyncio.CancelledError:
            if diagnostics is not None:
                diagnostics.record_event(
                    "task_cancelled",
                    severity="warning",
                    stage="task_run",
                    task_id=task_id,
                    cancel_category="asyncio_cancelled",
                    budgets=budgets,
                )
            raise
        except Exception as exc:
            if diagnostics is not None:
                exc_log_id = diagnostics.record_exception(
                    exc,
                    event="task_exception",
                    stage="task_run",
                    task_id=task_id,
                    related_log_id=first_log_id,
                    budgets=budgets,
                    sensitive_values=(task_text, prompt, claim_token),
                )
                if first_log_id is None:
                    first_log_id = exc_log_id
            reply = f"{bridge_label} 运行失败，错误详情已记录。"
            if diagnostics is not None and first_log_id is None:
                reply = f"{bridge_label} 运行失败，本地诊断日志写入失败（已降级）。"
            completion_status = "failed"
            detail = _diag_public_text(
                diagnostics,
                exc,
                sensitive_values=(task_text, prompt, claim_token),
                max_chars=800,
            )
            last_error = f"{bridge_label} failed before completing task {task_id}: {detail}"
            if first_log_id:
                last_error = _with_log_ref(last_error, first_log_id)
        await _raise_if_task_lease_lost(heartbeat_task)
        result_message_id: int | None = None
        creator = claimed.get("created_by")
        if creator:
            send_operation = StageTimeline(diagnostics).start(
                "task_result_send",
                phase="task",
                task_id=task_id,
                budgets=budgets,
            )
            try:
                result_message = await client.send_text(
                    reply,
                    to=[str(creator)],
                    group_id=claimed.get("hall_group_id"),
                )
                result_message_id = int(result_message["id"])
            except asyncio.CancelledError:
                send_operation.finish("canceled")
                if diagnostics is not None:
                    diagnostics.record_event(
                        "task_cancelled",
                        severity="warning",
                        stage="task_result_send",
                        task_id=task_id,
                        cancel_category="asyncio_cancelled",
                        budgets=budgets,
                    )
                raise
            except Exception as exc:
                send_operation.finish("failed")
                secondary_log_id = _record_secondary_failure(
                    diagnostics,
                    exc,
                    stage="task_result_send",
                    task_id=task_id,
                    primary_log_id=first_log_id,
                    budgets=budgets,
                    sensitive_values=(task_text, prompt, claim_token),
                )
                completion_status = "failed"
                send_error = _diag_public_text(
                    diagnostics,
                    exc,
                    sensitive_values=(task_text, prompt, claim_token),
                    max_chars=800,
                )
                previous = str(last_error) if last_error else ""
                combined = (
                    f"{previous}; {bridge_label} could not post task result: {send_error}"
                    if previous
                    else f"{bridge_label} could not post task result: {send_error}"
                )
                if first_log_id is None:
                    first_log_id = secondary_log_id
                last_error = _with_log_ref(combined, first_log_id)
            else:
                send_operation.finish("succeeded")

        await _raise_if_task_lease_lost(heartbeat_task)
        completion_kwargs: dict[str, Any] = {
            "status": completion_status,
            "result_message_id": result_message_id,
            "last_error": last_error,
        }
        if claim_token is not None:
            completion_kwargs["claim_token"] = claim_token
        if completion_status == "succeeded" and gate_verdict_payload is not None:
            completion_kwargs["gate_verdict"] = gate_verdict_payload
        complete_operation = StageTimeline(diagnostics).start(
            "task_complete",
            phase="task",
            task_id=task_id,
            budgets=budgets,
        )
        try:
            await client.complete_task(task_id, **completion_kwargs)
        except asyncio.CancelledError:
            complete_operation.finish("canceled")
            if diagnostics is not None:
                diagnostics.record_event(
                    "task_cancelled",
                    severity="warning",
                    stage="task_complete",
                    task_id=task_id,
                    cancel_category="asyncio_cancelled",
                    budgets=budgets,
                )
            raise
        except Exception as exc:
            complete_operation.finish("failed")
            secondary_log_id = _record_secondary_failure(
                diagnostics,
                exc,
                stage="task_complete",
                task_id=task_id,
                primary_log_id=first_log_id,
                budgets=budgets,
                sensitive_values=(task_text, prompt, claim_token),
            )
            if first_log_id is None:
                first_log_id = secondary_log_id
            raise
        complete_operation.finish("succeeded")
        if diagnostics is not None:
            diagnostics.record_event(
                "task_completed",
                stage="task_complete",
                severity="info" if completion_status == "succeeded" else "warning",
                task_id=task_id,
                message=completion_status,
                budgets=budgets,
                extra={
                    "result_message_id": result_message_id,
                    "error_log_id": first_log_id,
                },
            )
        return True
    except TaskLeaseLostError as exc:
        if diagnostics is not None:
            lease_log_id = diagnostics.record_exception(
                exc,
                event="task_lease_lost",
                stage="task_lease",
                task_id=task_id,
                related_log_id=first_log_id,
                budgets=budgets,
            )
            if lease_log_id:
                print(
                    f"Task {task_id} lease lost; log_ref={lease_log_id}",
                    file=sys.stderr,
                )
        return False
    finally:
        await _stop_task_heartbeat(heartbeat_task)


async def _fail_task_after_preflight_limit(
    task: dict[str, Any],
    *,
    client: Any,
    instance_id: str,
    attempts: int,
    error: TaskPreflightError,
    lease_seconds: int,
    diagnostics: Any | None = None,
    primary_log_id: str | None = None,
) -> bool:
    """Persistently fail a poison task after its bounded preflight attempts."""
    from TALK.client.exceptions import TalkValidationError

    task_id = int(task["id"])
    budgets = _diag_budgets(
        http_timeout=_diag_http_timeout(client),
        lease_seconds=lease_seconds,
    )
    protected_error = _diag_public_text(
        diagnostics,
        error,
        sensitive_values=(
            *getattr(error, "diagnostic_sensitive_values", ()),
            str(task.get("content") or ""),
        ),
        max_chars=800,
    )
    last_error = (
        f"task {task_id} preflight failed after {attempts} attempts; "
        f"automatic retries stopped: {protected_error}"
    )
    if primary_log_id:
        last_error = _with_log_ref(last_error, primary_log_id)
    accept_operation = StageTimeline(diagnostics).start(
        "task_accept",
        phase="task_preflight",
        task_id=task_id,
        budgets=budgets,
    )
    try:
        await client.accept_task(task_id)
    except asyncio.CancelledError:
        accept_operation.finish("canceled")
        raise
    except TalkValidationError as exc:
        accept_operation.finish("failed")
        if exc.status_code != 409:
            if diagnostics is not None:
                diagnostics.record_exception(
                    exc,
                    event="secondary_failure",
                    stage="task_preflight_terminal_accept",
                    task_id=task_id,
                    related_log_id=primary_log_id,
                    budgets=budgets,
                )
            raise
        try:
            current = await client.get_task(task_id)
        except Exception as exc2:
            if diagnostics is not None:
                diagnostics.record_exception(
                    exc2,
                    event="secondary_failure",
                    stage="task_preflight_terminal_reread",
                    task_id=task_id,
                    related_log_id=primary_log_id,
                    budgets=budgets,
                )
            raise
        if str(current.get("workflow_status") or "") != "accepted":
            return False
    except Exception:
        accept_operation.finish("failed")
        raise
    else:
        accept_operation.finish("succeeded")
    claim_operation = StageTimeline(diagnostics).start(
        "task_claim",
        phase="task",
        task_id=task_id,
        budgets=budgets,
    )
    try:
        claimed = await client.claim_task(
            task_id,
            instance_id=instance_id,
            lease_seconds=lease_seconds,
        )
    except asyncio.CancelledError:
        claim_operation.finish("canceled")
        raise
    except TalkValidationError as exc:
        claim_operation.finish("failed")
        if exc.status_code == 409:
            if diagnostics is not None:
                diagnostics.record_event(
                    "task_claim_conflict",
                    severity="warning",
                    stage="task_preflight_terminal_claim",
                    task_id=task_id,
                    message=f"claim conflict: HTTP {exc.status_code}",
                    budgets=budgets,
                )
            return False
        if diagnostics is not None:
            diagnostics.record_exception(
                exc,
                event="secondary_failure",
                stage="task_preflight_terminal_claim",
                task_id=task_id,
                related_log_id=primary_log_id,
                budgets=budgets,
            )
        raise
    except Exception as exc:
        claim_operation.finish("failed")
        if diagnostics is not None:
            diagnostics.record_exception(
                exc,
                event="secondary_failure",
                stage="task_preflight_terminal_claim",
                task_id=task_id,
                related_log_id=primary_log_id,
                budgets=budgets,
            )
        raise
    claim_operation.finish("succeeded")

    result_message_id: int | None = None
    creator = str(claimed.get("created_by") or task.get("created_by") or "").strip()
    if creator:
        send_operation = StageTimeline(diagnostics).start(
            "task_result_send",
            phase="task",
            task_id=task_id,
            budgets=budgets,
        )
        try:
            result_message = await client.send_text(
                (
                    f"自动预检连续失败 {attempts} 次，已停止重试并将任务标记为失败。"
                    "请检查 Agent 的 TALK_TASK_PREFLIGHT 输出协议后重新创建任务。"
                ),
                to=[creator],
                group_id=claimed.get("hall_group_id") or task.get("hall_group_id"),
            )
            result_message_id = int(result_message["id"])
        except asyncio.CancelledError:
            send_operation.finish("canceled")
            raise
        except Exception as exc:
            send_operation.finish("failed")
            secondary_log_id = _record_secondary_failure(
                diagnostics,
                exc,
                stage="task_preflight_terminal_result_send",
                task_id=task_id,
                primary_log_id=primary_log_id,
                budgets=budgets,
            )
            send_error = _diag_public_text(diagnostics, exc, max_chars=800)
            last_error = (
                f"{last_error}; could not post preflight failure result: {send_error}"
            )
            if primary_log_id is None:
                primary_log_id = secondary_log_id
            last_error = _with_log_ref(last_error, primary_log_id)
        else:
            send_operation.finish("succeeded")

    completion_kwargs: dict[str, Any] = {
        "status": "failed",
        "result_message_id": result_message_id,
        "last_error": last_error,
    }
    claim_token = str(claimed.get("claim_token") or "").strip()
    if claim_token:
        completion_kwargs["claim_token"] = claim_token
    complete_operation = StageTimeline(diagnostics).start(
        "task_complete",
        phase="task",
        task_id=task_id,
        budgets=budgets,
    )
    try:
        await client.complete_task(task_id, **completion_kwargs)
    except asyncio.CancelledError:
        complete_operation.finish("canceled")
        raise
    except Exception as exc:
        complete_operation.finish("failed")
        _record_secondary_failure(
            diagnostics,
            exc,
            stage="task_preflight_terminal_complete",
            task_id=task_id,
            primary_log_id=primary_log_id,
            budgets=budgets,
        )
        raise
    complete_operation.finish("succeeded")
    if diagnostics is not None:
        diagnostics.record_event(
            "task_preflight_failed_terminal",
            severity="warning",
            stage="task_preflight",
            task_id=task_id,
            message=f"preflight stopped after {attempts} attempts",
            budgets=budgets,
            extra={"error_log_id": primary_log_id},
        )
    return True


async def handle_incoming_message(
    message: dict[str, Any],
    *,
    client: Any,
    member_id: str,
    workdir: Path,
    command: str | Sequence[str],
    timeout: int,
    max_reply_chars: int,
    runtime: str = "cli",
    bridge_label: str = "CLI bridge",
    prompt_transport: str = "stdin",
    send_ack: bool = False,
    report_status: Any | None = None,
    decision_tier: str | None = None,
    diagnostics: Any | None = None,
) -> None:
    """Handle one incoming group/direct message.

    ``decision_tier`` is a deprecated compatibility parameter: accepted and ignored
    (never placed in the prompt or the child environment).
    """
    del decision_tier
    _clear_deprecated_decision_tier_env()
    sender = message.get("from")
    if not sender:
        return

    task_id = str(message.get("id") or "")
    group_id = message.get("group_id") if isinstance(message.get("group_id"), str) else None
    budgets = _diag_budgets(
        cli_timeout=timeout,
        http_timeout=_diag_http_timeout(client),
    )
    task_text = ""
    prompt = ""
    cli_failure_log_id: str | None = None
    report_failure_handled = False
    if report_status is not None:
        try:
            await report_status("busy", current_task_id=task_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if diagnostics is not None:
                diagnostics.record_exception(
                    exc,
                    event="message_status_failed",
                    stage="message_status_busy",
                    task_id=None, message_id=task_id,
                    budgets=budgets,
                )
            raise

    deferred_file: str | None = None
    try:
        if send_ack:
            await client.reply(
                int(message["id"]),
                text=f"{bridge_label} received the task and is working on it.",
                to=[sender],
                group_id=group_id,
            )

        task_text = strip_leading_mentions(
            str(message.get("content") or ""),
            member_id=member_id,
        )
        sender_id = str(sender)
        discussion: dict[str, Any] | None = None
        turns: list[dict[str, Any]] = []
        discussion_context = ""
        discussion_turn_count: int = 0
        if sender_id.startswith("agent:") and group_id:
            scope_context = await _discussion_scope_for_incoming_agent_message(
                client,
                group_id=group_id,
                member_id=member_id,
                sender_id=sender_id,
                message=message,
                task_text=task_text,
            )
            if scope_context.closed:
                if report_status is not None:
                    await report_status("idle")
                return
            discussion = scope_context.discussion
            turns = scope_context.turns
            discussion_id = int(discussion["id"]) if discussion and discussion.get("id") is not None else None
            latest_stance = str(turns[-1].get("stance") or "") if turns else ""
            substantive_turns = _substantive_discussion_turns(turns)
            discussion_turn_count = len(substantive_turns)
            # 多方场（如 brainstorm）预算按参与者规模放大；1:1 阈值不变（DELIBERATION §8.3）
            close_threshold = _discussion_auto_turn_budget(discussion) + 1
            if (
                discussion_id is not None
                and latest_stance == "disagree"
                and len(substantive_turns) >= close_threshold
            ):
                await _send_human_escalation(
                    client,
                    discussion_id=discussion_id,
                    group_id=group_id,
                    reply_to=int(message["id"]),
                    text="自动讨论回合已达到上限，请你做最终判断。",
                )
                if report_status is not None:
                    await report_status("idle")
                return
            if (
                discussion_id is not None
                and latest_stance != "disagree"
                and len(substantive_turns) >= close_threshold
            ):
                await _send_agent_scope_closure(
                    client,
                    discussion_id=discussion_id,
                    group_id=group_id,
                    reply_to=int(message["id"]),
                    responder_id=member_id,
                    target_agent_id=sender_id,
                )
                if report_status is not None:
                    await report_status("idle")
                return
            discussion_context = _discussion_context_text(
                discussion,
                turns,
                current_message_id=_message_id(message),
                current_message_text=task_text,
                responder_id=member_id,
                direct_requester_id=sender_id,
                human_id=await _find_human_reviewer(client, group_id),
            )
        elif group_id:
            # 人驱动编排（DELIBERATION §8）：human 发起/点名时，把本次回复记账到已开的多方场
            # （如 brainstorm 自动开的场）。只解析多方场，1:1 流程与 prompt 保持零变化。
            discussion = await _active_multiparty_discussion(
                client,
                group_id=group_id,
                member_id=member_id,
                peer_id=sender_id,
            )
            if discussion is not None and discussion.get("id") is not None:
                turns = await _list_discussion_turns(client, int(discussion["id"]))
                discussion_turn_count = len(_substantive_discussion_turns(turns))

        group_member_context = await _build_group_member_context(client, group_id, member_id, sender=str(sender))

        # 5.5：元数据走环境变量，不放 prompt。空值不设，避免扩展误判
        if group_id:
            os.environ["TALK_GROUP_ID"] = group_id
        else:
            os.environ.pop("TALK_GROUP_ID", None)
        _clear_deprecated_decision_tier_env()

        # 5.5 方案 D：reply_to 只作为 UI 引用；需求轮次由 discussion_turns.turn_kind 账本判断。
        # 整个 active discussion 最多允许 round_index=2 的 demand，之后不再暴露 talk_send。
        talk_send_allowed = _can_create_deferred_file(
            group_id=group_id,
            sender_id=sender_id,
            message=message,
            discussion=discussion,
            turns=turns,
        )
        if talk_send_allowed:
            fd, deferred_path = tempfile.mkstemp(suffix=".jsonl", prefix="talk_deferred_")
            os.close(fd)
            os.environ["TALK_DEFERRED_FILE"] = deferred_path
            deferred_file = deferred_path

        summary_request = await _is_brainstorm_summary_request(
            client,
            message=message,
            group_id=group_id,
            discussion=discussion,
            member_id=member_id,
            sender_id=sender_id,
            task_text=task_text,
        )
        summary_grounding = ""
        if summary_request and discussion is not None:
            summary_grounding = await _brainstorm_summary_grounding(
                client,
                group_id=group_id or "",
                discussion=discussion,
                turns=turns,
            )

        # 汇总轮只注入每位 Agent 的首条意见原文；其它多方轮次沿用 BS-2b 历史回顾。
        shared_history = summary_grounding
        if not shared_history:
            shared_history = await _shared_discussion_history(
                client,
                group_id=group_id,
                discussion=discussion,
                current_message_id=_message_id(message),
                self_id=member_id,
            )

        prompt = build_cli_prompt(
            message,
            member_id=member_id,
            workdir=workdir,
            runtime=runtime,
            discussion_context=discussion_context,
            group_member_context=group_member_context,
            shared_history=shared_history,
        )
        if os.environ.get("TALK_DUMP_PROMPT") == "1":
            _dump_prompt(
                member_id=member_id,
                message_id=str(message.get("id") or ""),
                sender=str(message.get("from") or ""),
                group_id=group_id,
                group_member_context=group_member_context,
                runtime=runtime,
                prompt=prompt,
            )
        result = await run_cli_command(
            command,
            prompt,
            cwd=workdir,
            timeout=timeout,
            prompt_transport=prompt_transport,
        )
        result = normalize_runtime_result(result, runtime=runtime)
        if result.timed_out or result.returncode != 0:
            cli_failure_log_id = _record_cli_failure(
                diagnostics,
                result,
                stage="message_cli",
                task_id=None, message_id=task_id,
                timeout=timeout,
                client=client,
                sensitive_values=(task_text, prompt),
            )
        # 诊断：function-calling 模式下，工具调用由 LLM 扩展内部处理
        # bridge 只读取 stdout 作为可见回复；TALK_ACTION 文本协议解析继续共存
        if os.environ.get("TALK_DUMP_PROMPT") == "1" and result.returncode == 0:
            raw_output = (result.stdout or "").strip()
            _dump_diagnostic(
                f"LLM raw output ({len(raw_output)} chars, ends with '"
                f"{raw_output[-80:] if len(raw_output) > 80 else raw_output}')"
            )
        reply = format_cli_reply(
            result,
            max_chars=max_reply_chars,
            bridge_label=bridge_label,
            force_one_sentence=wants_one_sentence(task_text),
            log_ref=cli_failure_log_id if result.timed_out or result.returncode != 0 else None,
            log_write_failed=bool(
                diagnostics is not None
                and (result.timed_out or result.returncode != 0)
                and cli_failure_log_id is None
            ),
        )
        if (runtime.lower() == "pi" or member_id == "agent:pi") and not result.timed_out and result.returncode == 0:
            reply = normalize_pi_reply_language(task_text, reply)
        visible_reply, actions = parse_talk_actions(reply)
        visible_reply = sanitize_visible_reply(visible_reply)
        mark_actions = [action for action in actions if action.action_type == "mark_stance"]
        has_final_action = any(action.action_type == "final_to_human" for action in actions)
        summary_reply_is_decision = bool(
            summary_grounding and visible_reply and not result.timed_out and result.returncode == 0
        )

        # Reply to sender FIRST, before executing any TALK_ACTION side effects
        reply_message_id: int | None = None
        if visible_reply:
            reply_message = await client.reply(int(message["id"]), text=visible_reply, to=[sender], group_id=group_id)
            reply_message_id = int(reply_message["id"]) if reply_message and reply_message.get("id") is not None else None
            # agent 发送者：沿用原记账；human 发送者：仅当解析到多方场（人驱动编排）时记账
            if discussion and not mark_actions:
                reply_stance = "decision" if summary_reply_is_decision else infer_reply_stance(task_text, visible_reply)
                appended = await _append_discussion_turn(
                    client,
                    discussion_id=int(discussion["id"]) if discussion.get("id") is not None else None,
                    message_id=reply_message_id,
                    stance=reply_stance,
                    target_member_id=sender_id,
                    turn_kind="reply",
                    round_index=1,
                )
                if appended:
                    await _resolve_if_discussion_initiator(
                        client,
                        discussion_id=int(discussion["id"]) if discussion.get("id") is not None else None,
                        group_id=group_id,
                        member_id=member_id,
                        stance=reply_stance,
                    )

        # 5.5 方案 D：执行延迟的 talk_send（visible reply 之后、TALK_ACTION 之前）。
        # reply_to 只保留 UI 引用；需求轮次写入 discussion_turns 账本。
        deferred_results: list[dict[str, Any]] = []
        if deferred_file:
            current_msg_id = int(message["id"]) if message.get("id") is not None else None
            deferred_results = await _read_and_execute_deferred_actions(
                deferred_file,
                client=client,
                group_id=group_id,
                reply_to=current_msg_id,
                current_turn_count=discussion_turn_count,
                max_auto_turns=_discussion_auto_turn_budget(discussion),
            )
            discussion, turns = await _record_deferred_demand_turns(
                deferred_results,
                client=client,
                group_id=group_id,
                member_id=member_id,
                discussion=discussion,
                turns=turns,
                task_text=task_text,
            )

        # Then execute TALK_ACTION side effects (backward compat)
        action_notices = await execute_talk_actions(
            actions,
            client=client,
            source_message=message,
            member_id=member_id,
            task_text=task_text,
        )

        # Relay action error notices to sender (as follow-up if visible reply was already sent)
        visible_action_notices = [notice for notice in action_notices if not notice.startswith("sent ")]
        if visible_action_notices:
            reply_message = await client.reply(
                int(message["id"]), text=visible_action_notices[0], to=[sender], group_id=group_id
            )
            if reply_message_id is None:
                reply_message_id = int(reply_message["id"]) if reply_message and reply_message.get("id") is not None else None

        for action in mark_actions:
            peer_id = action.target_member_id or str(sender)
            existing_discussion_id = int(discussion["id"]) if discussion and discussion.get("id") is not None else None
            discussion_id = action.discussion_id or existing_discussion_id
            if discussion_id is None:
                discussion_id = await _resolve_discussion_id(
                    client,
                    group_id=group_id,
                    member_id=member_id,
                    peer_id=peer_id,
                    topic=_discussion_topic_from_text(task_text),
                    create_if_missing=group_id is not None,
                )
            stance = "decision" if summary_reply_is_decision else action.stance or "answer"
            await _append_discussion_turn(
                client,
                discussion_id=discussion_id,
                message_id=reply_message_id,
                stance=stance,
                target_member_id=peer_id,
                turn_kind="reply",
                round_index=action.round_index or 1,
            )
            await _resolve_if_discussion_initiator(
                client,
                discussion_id=discussion_id,
                group_id=group_id,
                member_id=member_id,
                stance=stance,
            )
            if stance == "agree" and not has_final_action:
                await _update_discussion_status(client, discussion_id, "resolved")
            elif stance == "disagree":
                await _maybe_escalate_disagreement(
                    client,
                    discussion_id=discussion_id,
                    group_id=group_id,
                    reply_to=reply_message_id,
                )
        if report_status is not None:
            failure_error = None
            if result.timed_out or result.returncode != 0:
                if diagnostics is not None:
                    failure_error = _diag_cli_failure_message(result, diagnostics=diagnostics, sensitive_values=(task_text, prompt))
                else:
                    failure_error = (
                        clean_cli_output(result.stderr)
                        or clean_cli_output(result.stdout)
                        or reply
                    )[-4000:]
                failure_error = _diag_public_text(
                    diagnostics,
                    failure_error,
                    sensitive_values=(task_text, prompt),
                    max_chars=800,
                )
                if cli_failure_log_id:
                    failure_error = _with_log_ref(str(failure_error), cli_failure_log_id)
            try:
                await report_status(
                    "error" if result.timed_out or result.returncode != 0 else "idle",
                    last_error=failure_error,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                report_failure_handled = True
                secondary_log_id = _record_secondary_failure(
                    diagnostics,
                    exc,
                    stage="message_status_report",
                    task_id=None, message_id=task_id,
                    primary_log_id=cli_failure_log_id,
                    budgets=budgets,
                    sensitive_values=(task_text, prompt),
                )
                if diagnostics is not None:
                    print(
                        "Message status report failed "
                        f"({type(exc).__name__}); log_ref={secondary_log_id or 'unavailable'}",
                        file=sys.stderr,
                    )
                raise
    except asyncio.CancelledError:
        if diagnostics is not None:
            diagnostics.record_event(
                "message_cancelled",
                severity="warning",
                stage="message",
                task_id=None, message_id=task_id,
                cancel_category="asyncio_cancelled",
                budgets=budgets,
            )
        raise
    except Exception as exc:
        if report_failure_handled:
            raise
        primary_log_id: str | None = None
        if diagnostics is not None:
            primary_log_id = diagnostics.record_exception(
                exc,
                event="message_exception",
                stage="message",
                task_id=None, message_id=task_id,
                related_log_id=cli_failure_log_id,
                budgets=budgets,
                sensitive_values=(task_text, prompt),
            )
        if report_status is not None:
            try:
                await report_status(
                    "error",
                    current_task_id=task_id,
                    last_error=_with_log_ref(
                        _diag_public_text(
                            diagnostics,
                            exc,
                            sensitive_values=(task_text, prompt),
                            max_chars=800,
                        ),
                        primary_log_id,
                    ),
                )
            except asyncio.CancelledError:
                raise
            except Exception as report_exc:
                secondary_log_id = _record_secondary_failure(
                    diagnostics,
                    report_exc,
                    stage="message_status_report",
                    task_id=None, message_id=task_id,
                    primary_log_id=primary_log_id,
                    budgets=budgets,
                    sensitive_values=(task_text, prompt),
                )
                if diagnostics is not None:
                    print(
                        "Message status report failed "
                        f"({type(report_exc).__name__}); "
                        f"log_ref={secondary_log_id or primary_log_id or 'unavailable'}",
                        file=sys.stderr,
                    )
        raise
    finally:
        if deferred_file:
            try:
                os.unlink(deferred_file)
            except OSError:
                pass
            os.environ.pop("TALK_DEFERRED_FILE", None)


async def run_task_queue_worker(
    *,
    client: Any,
    member_id: str,
    workdir: Path,
    instance_id: str,
    args: argparse.Namespace,
    run_lock: asyncio.Lock,
    report_status: Any,
    diagnostics: Any | None = None,
    report_query_error: Any | None = None,
    recover_query_error: Any | None = None,
) -> None:
    preflight_failures: dict[int, tuple[int, TaskPreflightError, str | None]] = {}
    max_preflight_attempts = resolve_task_preflight_max_attempts(args)
    queue_budgets = _diag_budgets(
        cli_timeout=getattr(args, "timeout", None),
        http_timeout=_diag_http_timeout(client),
        lease_seconds=getattr(args, "task_lease_seconds", None),
        heartbeat_interval=getattr(args, "task_heartbeat_interval", None),
        poll_interval=getattr(args, "task_poll_interval", None),
    )
    poll_recorder = QueuePollRecorder(
        diagnostics,
        budgets=queue_budgets,
    )
    poll_cycle: QueuePollCycle | None = None
    current_task_id: int | None = None
    query_status_recovery_pending = False
    stop_reason = "unexpected_exit"
    queue_start_log_id: str | None = None
    if diagnostics is not None:
        queue_start_log_id = diagnostics.record_event(
            "queue_started",
            stage="queue_worker",
            message="task queue worker started",
            budgets=queue_budgets,
        )
    try:
        while True:
            current_task_id = None
            poll_cycle = None
            try:
                poll_cycle = poll_recorder.begin()
                discovery_operation = StageTimeline(diagnostics).begin(
                    "task_discovery",
                    phase="queue",
                    budgets=queue_budgets,
                )
                requeue_expired = getattr(client, "requeue_expired_tasks", None)
                if requeue_expired is not None:
                    await requeue_expired()
                tasks = await client.list_tasks(target_member_id=member_id, status="queued")
                queued = sorted(
                    (
                        task
                        for task in tasks
                        if str(task.get("workflow_status") or "assigned") in _TASK_RUNNER_ACTIONABLE_WORKFLOWS
                    ),
                    key=lambda item: int(item["id"]),
                )
                # The query discovery ends here: before the task lock, preflight
                # or model execution. Task/model delays never create a new poll
                # success or advance poll_seq.
                poll_recorder.succeed(poll_cycle)
                poll_cycle = None
                if queued:
                    discovery_operation.finish("succeeded")
                else:
                    # Idle polling stays out of the persistent timeline.
                    discovery_operation.abandon()
                if query_status_recovery_pending and recover_query_error is not None:
                    try:
                        recovered = await recover_query_error()
                    except asyncio.CancelledError:
                        stop_reason = "cancelled"
                        raise
                    except Exception as report_exc:
                        # The query already succeeded. A status PUT failure must
                        # neither count as a query failure nor kill its retries.
                        secondary_log_id = _record_secondary_failure(
                            diagnostics, report_exc,
                            stage="queue_poll_status_recovery",
                            task_id=None, primary_log_id=None, budgets=queue_budgets,
                        )
                        print(
                            "Task queue recovery status report failed "
                            f"({type(report_exc).__name__}); "
                            f"log_ref={secondary_log_id or 'unavailable'}",
                            file=sys.stderr,
                        )
                    else:
                        query_status_recovery_pending = not recovered
                for task in queued:
                    task_id = int(task["id"])
                    current_task_id = task_id
                    async with timed_lock(
                        run_lock,
                        timeline=StageTimeline(diagnostics),
                        stage="task_lock_wait",
                        phase="queue",
                        task_id=task_id,
                        budgets=queue_budgets,
                    ):
                        failure = preflight_failures.get(task_id)
                        if failure is not None and failure[0] >= max_preflight_attempts:
                            terminal = await _fail_task_after_preflight_limit(
                                task,
                                client=client,
                                instance_id=instance_id,
                                attempts=failure[0],
                                error=failure[1],
                                lease_seconds=getattr(
                                    args,
                                    "task_lease_seconds",
                                    DEFAULT_TASK_LEASE_SECONDS,
                                ),
                                diagnostics=diagnostics,
                                primary_log_id=failure[2],
                            )
                            if terminal:
                                preflight_failures.pop(task_id, None)
                            continue
                        preflight_attempt = (
                            failure[0] if failure is not None else 0
                        ) + 1
                        try:
                            await handle_queued_task(
                                task,
                                client=client,
                                member_id=member_id,
                                workdir=workdir,
                                instance_id=instance_id,
                                command=getattr(args, "task_command", args.command),
                                timeout=args.timeout,
                                max_reply_chars=args.max_reply_chars,
                                runtime=args.runtime,
                                bridge_label=args.bridge_label,
                                prompt_transport=args.prompt_transport,
                                # Deprecated compat: accepted and ignored by handle_queued_task.
                                decision_tier=getattr(args, "decision_tier", None),
                                preflight_command=getattr(
                                    args,
                                    "task_preflight_command",
                                    getattr(args, "task_command", args.command),
                                ),
                                lease_seconds=getattr(
                                    args,
                                    "task_lease_seconds",
                                    DEFAULT_TASK_LEASE_SECONDS,
                                ),
                                heartbeat_interval=getattr(
                                    args,
                                    "task_heartbeat_interval",
                                    DEFAULT_TASK_HEARTBEAT_INTERVAL,
                                ),
                                diagnostics=diagnostics,
                                preflight_attempt=preflight_attempt,
                                execution_context={
                                    "project_id": getattr(args, "project_id", None),
                                    "launch_id": getattr(args, "launch_id", None),
                                    "store_override": None,
                                    "native_package_root": _dsh_package_root_from_command(
                                        getattr(args, "task_command", args.command)
                                    ),
                                },
                            )
                        except TaskPreflightError as exc:
                            attempts = (failure[0] if failure is not None else 0) + 1
                            error_log_id = getattr(exc, "diagnostic_log_id", None)
                            if diagnostics is not None and not error_log_id:
                                error_log_id = diagnostics.record_exception(
                                    exc,
                                    event="preflight_failed",
                                    stage="task_preflight",
                                    task_id=task_id,
                                    budgets=queue_budgets,
                                    sensitive_values=(
                                        *getattr(exc, "diagnostic_sensitive_values", ()),
                                        str(task.get("content") or ""),
                                    ),
                                )
                                if error_log_id:
                                    setattr(exc, "diagnostic_log_id", error_log_id)
                            preflight_failures[task_id] = (attempts, exc, error_log_id)
                            if attempts >= max_preflight_attempts:
                                terminal = await _fail_task_after_preflight_limit(
                                    task,
                                    client=client,
                                    instance_id=instance_id,
                                    attempts=attempts,
                                    error=exc,
                                    lease_seconds=getattr(
                                        args,
                                        "task_lease_seconds",
                                        DEFAULT_TASK_LEASE_SECONDS,
                                    ),
                                    diagnostics=diagnostics,
                                    primary_log_id=error_log_id,
                                )
                                if terminal:
                                    preflight_failures.pop(task_id, None)
                            elif report_status is not None:
                                try:
                                    await report_status(
                                        "error",
                                        last_error=_with_log_ref(
                                            (
                                                f"task {task_id} preflight attempt "
                                                f"{attempts}/{max_preflight_attempts} failed: "
                                                f"{_diag_public_text(diagnostics, exc, max_chars=800)}"
                                            ),
                                            error_log_id,
                                        ),
                                    )
                                except asyncio.CancelledError:
                                    stop_reason = "cancelled"
                                    raise
                                except Exception as report_exc:
                                    if diagnostics is None:
                                        raise
                                    secondary_log_id = _record_secondary_failure(
                                        diagnostics,
                                        report_exc,
                                        stage="queue_worker_status_report",
                                        task_id=task_id,
                                        primary_log_id=error_log_id,
                                        budgets=queue_budgets,
                                    )
                                    print(
                                        "Task queue status report failed "
                                        f"({type(report_exc).__name__}); "
                                        f"log_ref={secondary_log_id or error_log_id or 'unavailable'}",
                                        file=sys.stderr,
                                    )
                        else:
                            preflight_failures.pop(task_id, None)
            except asyncio.CancelledError:
                if poll_cycle is not None:
                    poll_recorder.cancel(poll_cycle)
                    poll_cycle = None
                stop_reason = "cancelled"
                raise
            except Exception as exc:
                query_failure = poll_cycle is not None
                queue_error_log_id: str | None = None
                if diagnostics is not None:
                    queue_error_log_id = diagnostics.record_exception(
                        exc,
                        event="queue_worker_exception",
                        stage="queue_worker",
                        task_id=current_task_id,
                        budgets=queue_budgets,
                    )
                if query_failure:
                    # Only a real exception in the discovery phase increments the
                    # consecutive query failure streak. Lock waits, preflight,
                    # task execution and status reporting are recorded by their
                    # own events and never pollute this counter.
                    poll_recorder.fail(poll_cycle, queue_error_log_id)
                    poll_cycle = None
                last_error = f"task queue worker failed ({type(exc).__name__})"
                if queue_error_log_id:
                    last_error = _with_log_ref(last_error, queue_error_log_id)
                elif diagnostics is None:
                    # Legacy behavior for callers that did not opt into local
                    # diagnostics; type remains visible even for an empty str().
                    last_error = f"{last_error}: {exc}"
                try:
                    if query_failure and report_query_error is not None:
                        # Retain this intent even if the error PUT itself fails;
                        # the reporter may already have updated its heartbeat.
                        query_status_recovery_pending = True
                        await report_query_error(last_error)
                    elif report_status is not None:
                        await report_status("error", last_error=last_error)
                except asyncio.CancelledError:
                    stop_reason = "cancelled"
                    raise
                except Exception as report_exc:
                    if diagnostics is None and not (
                        query_failure and report_query_error is not None
                    ):
                        raise
                    secondary_log_id = _record_secondary_failure(
                        diagnostics,
                        report_exc,
                        stage="queue_worker_status_report",
                        task_id=current_task_id,
                        primary_log_id=queue_error_log_id,
                        budgets=queue_budgets,
                    )
                    print(
                        "Task queue status report failed "
                        f"({type(report_exc).__name__}); "
                        f"log_ref={secondary_log_id or queue_error_log_id or 'unavailable'}",
                        file=sys.stderr,
                    )

            await asyncio.sleep(getattr(args, "task_poll_interval", DEFAULT_TASK_POLL_INTERVAL))
    finally:
        if diagnostics is not None:
            reason = diagnostics.stop_reason or stop_reason
            diagnostics.record_event(
                "queue_stopped",
                stage="queue_worker",
                message=f"task queue worker stopped: {reason}",
                budgets=queue_budgets,
                extra={
                    "reason": reason,
                    "start_log_id": queue_start_log_id,
                },
            )


def managed_stop_control_path(
    project_id: str | None,
    launch_id: str | None,
    env: dict[str, str] | None = None,
) -> Path | None:
    """只接受本次受管 launch 的宿主停止文件；旧手动入口不增加监听。"""
    if not project_id or not launch_id:
        return None
    raw = (os.environ if env is None else env).get("TALK_ROLE_SERVICE_CONTROL_FILE", "")
    if not raw:
        return None
    path = Path(raw)
    # 与宿主 OwnershipStore.control_path 的文件名规则一致。
    launch_name = re.sub(r"[^A-Za-z0-9._-]+", "_", launch_id)[:120] or "role"
    if not path.is_absolute() or path.name != f"{launch_name}.ctl":
        raise ValueError("Managed stop control path must match the current launch")
    return path


async def wait_for_managed_stop(control_file: Path, *, poll_interval: float = .25) -> None:
    """有界读取私有控制文件；缺失/暂不可读/错误内容均不冒认关闭请求。"""
    while True:
        try:
            if not control_file.is_symlink():
                with control_file.open("rb") as stream:
                    if stream.read(64) == b"shutdown\n":
                        return
        except OSError:
            pass
        await asyncio.sleep(poll_interval)


async def run_until_managed_stop(client: Any, control_file: Path | None) -> str:
    if control_file is None:
        await client.run()
        return "transport_closed"
    transport = asyncio.create_task(client.run())
    stop_waiter = asyncio.create_task(wait_for_managed_stop(control_file))
    try:
        done, _ = await asyncio.wait(
            (transport, stop_waiter), return_when=asyncio.FIRST_COMPLETED
        )
        # 保留连接失败；停止请求则取消当前连接/消息，随后走 run_bridge 原清理路径。
        if transport in done:
            await transport
            return "transport_closed"
        await stop_waiter
        return "managed_stop"
    finally:
        for task in (transport, stop_waiter):
            task.cancel()
        await asyncio.gather(transport, stop_waiter, return_exceptions=True)


async def run_bridge(args: argparse.Namespace) -> None:
    from TALK.client import TalkClient

    member_id = member_id_from_name(args.name)
    # ``--decision-tier`` stays accepted on the parser but is deprecated and ignored:
    # no project-local tier is read, no fallback to "execution" happens, and the value
    # is never injected into prompts or the child environment.
    args.decision_tier = getattr(args, "decision_tier", None)
    _clear_deprecated_decision_tier_env()
    # R1-3：``--key-file``/``TALK_ROLE_API_KEY`` 与旧 ``--key`` 统一解析成内存里的 Key；
    # 明文 Key 不写日志、不进 argv 之外的任何输出。
    args.key = resolve_bridge_api_key(args)
    configure_talk_tool_environment(args, member_id)
    workdir = Path(args.workdir).expanduser().resolve()
    args.task_preflight_command = resolve_task_preflight_command(args)
    client = TalkClient(args.base_url, args.key, poll_interval=args.poll_interval)
    instance_id = args.instance_id or f"{member_id}:{uuid4()}"
    host = socket.gethostname()
    # R1-3 受管关联：只有宿主显式传入 ``--launch-id`` 时才附加 project/launch/进程身份，
    # 现有非受管 bridge 的实例上报载荷与行为完全不变。
    managed_launch_id = str(getattr(args, "launch_id", None) or "").strip() or None
    managed_project_id = str(getattr(args, "project_id", None) or "").strip() or None
    managed_started_at = parse_managed_started_at(getattr(args, "process_started_at", None))
    stop_control_file = managed_stop_control_path(managed_project_id, managed_launch_id)
    # The project id is the explicit managed launch binding when present; otherwise
    # use the identity already exported by configure_talk_tool_environment().  A
    # missing value stays None instead of being guessed.
    diagnostics_project_id = managed_project_id or (
        os.environ.get("TALK_PROJECT_ID") or None
    )
    try:
        diagnostics = runtime_diag.RuntimeDiagnostics.from_bridge_args(
            args,
            member_id=member_id,
            instance_id=instance_id,
            runtime=args.runtime,
            project_id=diagnostics_project_id,
            launch_id=managed_launch_id,
            known_secrets=(args.key,),
        )
    except Exception as exc:
        # Diagnostics must never prevent the bridge from starting.  Keep the
        # degradation visible without echoing exception text (which may contain
        # the in-memory key or another secret).
        diagnostics = None
        print(
            f"[runtime-diagnostics] 本地诊断日志降级：初始化失败 ({type(exc).__name__})",
            file=sys.stderr,
        )
    bridge_budgets = _diag_budgets(
        cli_timeout=getattr(args, "timeout", None),
        http_timeout=_diag_http_timeout(client),
        lease_seconds=getattr(args, "task_lease_seconds", None),
        heartbeat_interval=getattr(args, "task_heartbeat_interval", None),
        managed_heartbeat_interval=(
            MANAGED_INSTANCE_HEARTBEAT_INTERVAL if managed_launch_id else None
        ),
        poll_interval=getattr(args, "task_poll_interval", None),
    )
    if diagnostics is not None:
        diagnostics.record_event(
            "bridge_started",
            stage="bridge",
            message="bridge process started",
            budgets=bridge_budgets,
            extra={
                "runtime": args.runtime,
                "managed": bool(managed_launch_id),
            },
        )
    try:
        await client.register(member_id, display_name=args.display_name or f"{args.runtime} CLI Bridge ({member_id})")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if diagnostics is not None:
            diagnostics.record_exception(
                exc,
                event="bridge_register_failed",
                stage="register",
                budgets=bridge_budgets,
            )
        raise
    status_lock = asyncio.Lock()
    run_lock = asyncio.Lock()
    current_managed_payload: dict[str, Any] = {}
    status_revision = 0
    query_error_revision: int | None = None

    async def publish_status_locked(
        status: str,
        *,
        current_task_id: str | None = None,
        last_error: str | None = None,
        query_owned: bool = False,
    ) -> None:
        nonlocal status_revision, query_error_revision
        payload = build_instance_report_payload(
            runtime=args.runtime,
            status=status,
            host=host,
            pid=os.getpid(),
            current_task_id=current_task_id,
            last_error=last_error,
            project_id=managed_project_id,
            launch_id=managed_launch_id,
            process_started_at=managed_started_at,
        )
        status_revision += 1
        query_error_revision = status_revision if query_owned else None
        # Keep retry/heartbeat state even when the following request fails.
        current_managed_payload.clear()
        current_managed_payload.update(payload)
        if managed_launch_id:
            await client._request_json(
                "PUT", f"/api/instances/{instance_id}", json_body=payload
            )
        else:
            await client.report_instance_status(instance_id, **payload)

    async def report_status(
        status: str,
        *,
        current_task_id: str | None = None,
        last_error: str | None = None,
    ) -> None:
        async with status_lock:
            await publish_status_locked(
                status, current_task_id=current_task_id, last_error=last_error,
            )

    async def report_query_error(last_error: str) -> None:
        async with status_lock:
            owned = query_error_revision is not None and query_error_revision == status_revision
            if run_lock.locked() or current_managed_payload.get("current_task_id") is not None:
                return
            if current_managed_payload.get("status") != "idle" and not owned:
                return
            await publish_status_locked("error", last_error=last_error, query_owned=True)

    async def recover_query_error() -> bool:
        nonlocal query_error_revision
        async with status_lock:
            # A normal message/task/offline report invalidates ownership even
            # if its text happens to equal the previous query error.
            if query_error_revision is None or query_error_revision != status_revision:
                return True
            if run_lock.locked():
                return False
            if current_managed_payload.get("current_task_id") is not None or current_managed_payload.get("status") not in ("idle", "error"):
                return True
            # Preserve ownership on failure so the next genuine query success
            # retries this PUT; any intervening status report cancels it.
            await publish_status_locked("idle", query_owned=True)
            query_error_revision = None
            return True

    try:
        await report_status("idle")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if diagnostics is not None:
            diagnostics.record_exception(
                exc,
                event="bridge_initial_status_failed",
                stage="instance_status",
                budgets=bridge_budgets,
            )
        raise

    @client.on_message
    async def handle_message(message: dict[str, Any]) -> None:
        if not should_handle_message(
            message,
            member_id,
            respond_to_broadcast=args.respond_to_broadcast,
        ):
            return

        async with run_lock:
            await handle_incoming_message(
                message,
                client=client,
                member_id=member_id,
                workdir=workdir,
                command=args.command,
                timeout=args.timeout,
                max_reply_chars=args.max_reply_chars,
                runtime=args.runtime,
                bridge_label=args.bridge_label,
                prompt_transport=args.prompt_transport,
                send_ack=args.send_ack,
                report_status=report_status,
                decision_tier=args.decision_tier,
                diagnostics=diagnostics,
            )

    task_worker: asyncio.Task[None] | None = None
    if not args.disable_task_queue:
        task_worker = asyncio.create_task(
            run_task_queue_worker(
                client=client,
                member_id=member_id,
                workdir=workdir,
                instance_id=instance_id,
                args=args,
                run_lock=run_lock,
                report_status=report_status,
                diagnostics=diagnostics,
                report_query_error=report_query_error,
                recover_query_error=recover_query_error,
            )
        )

    async def refresh_managed_instance() -> None:
        while True:
            await asyncio.sleep(MANAGED_INSTANCE_HEARTBEAT_INTERVAL)
            try:
                async with status_lock:
                    await client._request_json(
                        "PUT", f"/api/instances/{instance_id}",
                        json_body=dict(current_managed_payload),
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 断连不停止 transport；不回显可能含凭据/正文的异常详情。
                heartbeat_log_id: str | None = None
                if diagnostics is not None:
                    heartbeat_log_id = diagnostics.record_exception(
                        exc,
                        event="managed_heartbeat_failure",
                        stage="managed_instance_heartbeat",
                        severity="warning",
                        budgets=_diag_budgets(
                            http_timeout=_diag_http_timeout(client),
                            managed_heartbeat_interval=MANAGED_INSTANCE_HEARTBEAT_INTERVAL,
                        ),
                    )
                suffix = f"; log_ref={heartbeat_log_id}" if heartbeat_log_id else ""
                print(
                    f"Managed instance heartbeat failed ({type(exc).__name__}){suffix}",
                    file=sys.stderr,
                )

    instance_heartbeat = (
        asyncio.create_task(refresh_managed_instance()) if managed_launch_id else None
    )
    stop_reason = "transport_closed"
    stop_error_log_id: str | None = None
    try:
        stop_reason = await run_until_managed_stop(client, stop_control_file)
    except asyncio.CancelledError:
        stop_reason = "cancelled"
        raise
    except Exception as exc:
        stop_reason = "transport_error"
        if diagnostics is not None:
            stop_error_log_id = diagnostics.record_exception(
                exc,
                event="bridge_transport_exception",
                stage="bridge_transport",
                budgets=bridge_budgets,
            )
        raise
    finally:
        had_original_error = sys.exc_info()[0] is not None
        cleanup_error: BaseException | None = None
        if diagnostics is not None:
            diagnostics.set_stop_reason(stop_reason)
        if instance_heartbeat is not None:
            instance_heartbeat.cancel()
            await asyncio.gather(instance_heartbeat, return_exceptions=True)
        if task_worker is not None:
            task_worker.cancel()
            try:
                await task_worker
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
                if diagnostics is not None:
                    diagnostics.record_exception(
                        exc,
                        event="secondary_failure",
                        stage="task_worker_shutdown",
                        related_log_id=stop_error_log_id,
                        budgets=bridge_budgets,
                    )
        try:
            try:
                await report_status("offline")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                cleanup_error = cleanup_error or exc
                if diagnostics is not None:
                    offline_log_id = diagnostics.record_exception(
                        exc,
                        event="secondary_failure",
                        stage="offline_status_report",
                        related_log_id=stop_error_log_id,
                        budgets=bridge_budgets,
                    )
                    print(
                        "Bridge offline status report failed "
                        f"({type(exc).__name__}); log_ref={offline_log_id or 'unavailable'}",
                        file=sys.stderr,
                    )
        finally:
            try:
                await client.close()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if diagnostics is not None:
                    close_log_id = diagnostics.record_exception(
                        exc,
                        event="secondary_failure",
                        stage="client_close",
                        related_log_id=stop_error_log_id,
                        budgets=bridge_budgets,
                    )
                    print(
                        "Bridge client close failed "
                        f"({type(exc).__name__}); log_ref={close_log_id or 'unavailable'}",
                        file=sys.stderr,
                    )
                if cleanup_error is None:
                    cleanup_error = exc
            if diagnostics is not None:
                diagnostics.record_event(
                    "bridge_stopped",
                    stage="bridge",
                    message=f"bridge stopped: {stop_reason}",
                    budgets=bridge_budgets,
                    related_log_id=stop_error_log_id,
                    extra={"reason": stop_reason},
                )
                diagnostics.close()
        if cleanup_error is not None and not had_original_error:
            raise cleanup_error


def build_parser(
    *,
    description: str = "TALK generic CLI bridge",
    default_name: str = "cli",
    default_runtime: str = "cli",
    default_command: str = DEFAULT_COMMAND,
    command_help: str = "CLI command that reads the TALK prompt from stdin",
    command_option: str = "--command",
    command_dest: str = "command",
    command_metavar: str | None = None,
    default_prompt_transport: str = "stdin",
    default_bridge_label: str = "CLI bridge",
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--name", default=default_name, help=f"Agent name or full member id. Default: {default_name}")
    parser.add_argument("--key", required=False, default=None, help="API key for this bridge member")
    parser.add_argument(
        "--key-file",
        default=None,
        help="File holding this bridge member's API key (R1-3 managed entry; keeps the "
        "plaintext key out of argv). Used only when --key is absent.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--instance-id", default=None)
    parser.add_argument(
        "--project-id",
        default=None,
        help="TALK project_id bound to this managed launch (R1-3). Overrides the id "
        "derived from --project when set.",
    )
    parser.add_argument(
        "--launch-id",
        default=None,
        help="Managed role-service launch this instance belongs to (R1-3). Unset keeps "
        "the legacy instance payload unchanged.",
    )
    parser.add_argument(
        "--process-started-at",
        default=None,
        help="ISO timestamp of this process start, supplied by the host manager (R1-3 "
        "managed association only).",
    )
    parser.add_argument(
        "--runtime-log-dir",
        default=None,
        help="Explicit local runtime diagnostics root. Defaults to TALK_RUNTIME_LOG_DIR "
        "or <project>/logs/runtime (ignored by Git).",
    )
    parser.add_argument(
        "--runtime-log-retention-days",
        type=float,
        default=None,
        help="Retention in days for rotated diagnostics segments of this run. "
        "Default: 30 (or TALK_RUNTIME_LOG_RETENTION_DAYS).",
    )
    parser.add_argument(
        "--runtime-log-max-bytes",
        type=int,
        default=None,
        help="Per-run diagnostics capacity in bytes. Default: 268435456 (256 MiB) "
        "or TALK_RUNTIME_LOG_MAX_BYTES.",
    )
    parser.add_argument(
        "--runtime-log-max-file-bytes",
        type=int,
        default=None,
        help="Rotate a diagnostics segment after this many bytes. Default: 8388608 "
        "(8 MiB) or TALK_RUNTIME_LOG_MAX_FILE_BYTES.",
    )
    parser.add_argument(
        "--disable-runtime-logs",
        dest="runtime_log_disabled",
        action="store_true",
        help="Disable the local runtime diagnostics writer for this bridge process.",
    )
    parser.add_argument("--runtime", default=default_runtime, help=f"Runtime label reported to TALK. Default: {default_runtime}")
    parser.add_argument("--bridge-label", default=default_bridge_label, help="Human-readable label used in error replies")
    parser.add_argument("--workdir", default=".", help="Working directory passed to the CLI command")
    parser.add_argument(
        "--prompt-transport",
        choices=sorted(PROMPT_TRANSPORTS),
        default=default_prompt_transport,
        help="How to pass the TALK prompt to the CLI command. Default: %(default)s",
    )
    parser.add_argument(
        command_option,
        dest=command_dest,
        metavar=command_metavar,
        default=default_command,
        required=not bool(default_command),
        help=command_help,
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--task-poll-interval", type=float, default=DEFAULT_TASK_POLL_INTERVAL)
    parser.add_argument(
        "--task-preflight-command",
        default=None,
        help="Optional read-only CLI command used for Task Hall preflight; defaults to the task execution command",
    )
    parser.add_argument(
        "--task-preflight-max-attempts",
        type=int,
        choices=range(1, TASK_PREFLIGHT_MAX_ATTEMPTS + 1),
        default=None,
        help="Maximum consecutive Task Hall preflight polling attempts; defaults to 1 for dsh and 3 for other runtimes",
    )
    parser.add_argument("--task-lease-seconds", type=int, default=DEFAULT_TASK_LEASE_SECONDS)
    parser.add_argument(
        "--task-heartbeat-interval",
        type=float,
        default=DEFAULT_TASK_HEARTBEAT_INTERVAL,
        help="Task claim heartbeat interval; effective control checks are capped at 5 seconds",
    )
    parser.add_argument("--disable-task-queue", action="store_true")
    parser.add_argument("--max-reply-chars", type=int, default=DEFAULT_MAX_REPLY_CHARS)
    parser.add_argument("--respond-to-broadcast", action="store_true")
    parser.add_argument("--send-ack", action="store_true")
    parser.add_argument(
        "--decision-tier",
        choices=["decision", "execution"],
        default=None,
        help=(
            "DEPRECATED and ignored: the fixed decision/execution tier was removed. "
            "Accepted only so older launch argv keeps working; it never changes prompts, "
            "environment, routing or permissions."
        ),
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Project root holding a .talk/ directory. When set, this member's "
        "IDENTITY/SOUL/USER profile is composed into the runtime system prompt "
        "(Phase 2 identity layer). Omit to keep current behavior unchanged.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == "__main__":
    main()
