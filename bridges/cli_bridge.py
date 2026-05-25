#!/usr/bin/env python3
"""Generic CLI bridge for TALK agent runtimes."""

from __future__ import annotations

import argparse
import asyncio
import html
import locale
import os
import re
import shlex
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RESPONSE_STYLE_INSTRUCTIONS = (
    "Match the scope of the user's request. For a simple presence check, greeting, or acknowledgement request, "
    "reply in one short sentence only, for example '<agent id> 在线。'. "
    "Do not inspect project files, summarize project progress, or produce status tables unless the user explicitly asks for that.\n"
)
DISCUSSION_PROTOCOL_INSTRUCTIONS = (
    "You are a participant in a TALK Group Hall, not a TALK administrator or user manual. "
    "You may talk with humans and other agents. If the user asks you to contact another agent, "
    "emit a TALK action and keep any visible acknowledgement brief.\n"
    "Discussion protocol: answer questions first. When responding to another agent, decide whether you agree. "
    "If you agree, add an optimization if useful or briefly affirm them. If you disagree, state the different recommendation. "
    "If both sides have disagreed across two turns, ask a human to make the final decision.\n"
    "Action syntax, one per line when needed: "
    "<talk-action type=\"send_message\" to=\"agent:name\" stance=\"question\">message</talk-action>, "
    "<talk-action type=\"mark_stance\" stance=\"agree|optimize|disagree|answer\"></talk-action>, "
    "or <talk-action type=\"escalate_to_human\" to=\"human:name\">question for the human</talk-action>. "
    "Do not explain these action tags to the user.\n"
)
DEFAULT_TIMEOUT_SEC = 600
DEFAULT_MAX_REPLY_CHARS = 12000
DEFAULT_TASK_POLL_INTERVAL = 2.0
DEFAULT_COMMAND = os.environ.get("TALK_CLI_COMMAND", "")
PROMPT_TRANSPORTS = {"stdin", "argv"}
ONE_SENTENCE_MARKERS = ("一句话", "一两句话", "one sentence", "single sentence")
SENTENCE_ENDINGS = "。！？.!?"
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
ACTION_TYPES = {"send_message", "mark_stance", "escalate_to_human"}
ACTION_STANCES = {"question", "answer", "agree", "optimize", "disagree", "escalate"}


@dataclass(frozen=True)
class CliRunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class TalkAction:
    action_type: str
    body: str = ""
    to: str | None = None
    target_member_id: str | None = None
    stance: str | None = None
    discussion_id: int | None = None
    round_index: int | None = None


def member_id_from_name(name: str) -> str:
    return name if name.startswith("agent:") else f"agent:{name}"


def parse_command(command: str) -> list[str]:
    parsed = shlex.split(command, posix=True)
    if not parsed:
        raise ValueError("CLI command cannot be empty")
    return parsed


def resolve_command_executable(args: Sequence[str]) -> list[str]:
    resolved = list(args)
    if not resolved:
        raise ValueError("CLI command cannot be empty")

    executable = resolved[0]
    if Path(executable).parent != Path("."):
        return resolved

    found = shutil.which(executable)
    if found:
        resolved[0] = found
    return resolved


def strip_leading_mentions(text: str, *, member_id: str | None = None) -> str:
    cursor = 0
    length = len(text)

    while cursor < length and text[cursor].isspace():
        cursor += 1

    saw_mention = False
    while cursor < length and text[cursor] == "@":
        token_start = cursor + 1
        token_end = token_start
        while token_end < length and not text[token_end].isspace():
            token_end += 1

        token = text[token_start:token_end]
        if member_id is not None and token != member_id:
            break

        saw_mention = True
        cursor = token_end
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


def _parse_action_attrs(raw_attrs: str) -> dict[str, str]:
    return {match.group(1).replace("-", "_").lower(): html.unescape(match.group(3)).strip() for match in ACTION_ATTR_RE.finditer(raw_attrs)}


def parse_talk_actions(text: str) -> tuple[str, list[TalkAction]]:
    actions: list[TalkAction] = []

    def replace(match: re.Match[str]) -> str:
        attrs = _parse_action_attrs(match.group("attrs") or "")
        action_type = attrs.get("type", "").strip().lower()
        if action_type not in ACTION_TYPES:
            return ""

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
        body = html.unescape(match.group("body") or "").strip()
        actions.append(
            TalkAction(
                action_type=action_type,
                body=body,
                to=to or None,
                target_member_id=target or to or None,
                stance=stance,
                discussion_id=discussion_id,
                round_index=round_index if round_index and round_index > 0 else None,
            )
        )
        return ""

    visible_text = ACTION_RE.sub(replace, text).strip()
    return visible_text, actions


def _discussion_topic_from_text(text: str, *, max_chars: int = 120) -> str:
    topic = " ".join(text.split())
    if len(topic) > max_chars:
        topic = f"{topic[:max_chars].rstrip()}..."
    return topic or "TALK Agent discussion"


def _discussion_participants(*member_ids: str | None) -> list[str]:
    return list(dict.fromkeys(member_id for member_id in member_ids if member_id))


def _is_talk_not_found(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404


async def _resolve_discussion_id(
    client: Any,
    *,
    group_id: str | None,
    member_id: str,
    peer_id: str | None,
    topic: str,
    create_if_missing: bool,
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
        participants = set(discussion.get("participant_ids") or [])
        if discussion.get("status") == "active" and {member_id, peer_id}.issubset(participants):
            return int(discussion["id"])

    if not create_if_missing:
        return None

    try:
        created = await client.create_discussion(
            group_id,
            topic,
            _discussion_participants(member_id, peer_id),
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
    round_index: int = 1,
) -> bool:
    if discussion_id is None or message_id is None:
        return False
    try:
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
        round_index=2,
    )
    try:
        await client.update_discussion(discussion_id, status="escalated")
    except AttributeError:
        pass
    except Exception as exc:
        if not _is_talk_not_found(exc):
            raise


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

    for action in actions:
        target = action.to or action.target_member_id
        if action.action_type == "send_message":
            if not target or not target.startswith("agent:"):
                summaries.append("send_message skipped: target must be an agent member")
                continue
            if not action.body:
                summaries.append("send_message skipped: message body is empty")
                continue
            text = f"@{target} {action.body}".strip()
            discussion_id = action.discussion_id or await _resolve_discussion_id(
                client,
                group_id=group_id,
                member_id=member_id,
                peer_id=target,
                topic=_discussion_topic_from_text(task_text),
                create_if_missing=True,
            )
            sent = await client.send_text(text, to=[target], reply_to=source_message_id, group_id=group_id)
            await _append_discussion_turn(
                client,
                discussion_id=discussion_id,
                message_id=int(sent["id"]),
                stance=action.stance or "question",
                target_member_id=target,
                round_index=action.round_index or 1,
            )
            summaries.append(f"sent message to {target}")
        elif action.action_type == "escalate_to_human":
            if not target or not target.startswith("human:"):
                summaries.append("escalate_to_human skipped: target must be a human member")
                continue
            text = f"@{target} {action.body or '请你做最终判断。'}".strip()
            sent = await client.send_text(text, to=[target], reply_to=source_message_id, group_id=group_id)
            discussion_id = action.discussion_id or await _resolve_discussion_id(
                client,
                group_id=group_id,
                member_id=member_id,
                peer_id=str(source_message.get("from") or ""),
                topic=_discussion_topic_from_text(task_text),
                create_if_missing=False,
            )
            await _append_discussion_turn(
                client,
                discussion_id=discussion_id,
                message_id=int(sent["id"]),
                stance="escalate",
                target_member_id=target,
                round_index=action.round_index or 2,
            )
            if discussion_id is not None:
                try:
                    await client.update_discussion(discussion_id, status="escalated")
                except AttributeError:
                    pass
                except Exception as exc:
                    if not _is_talk_not_found(exc):
                        raise
            summaries.append(f"escalated to {target}")
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


def build_cli_prompt(
    message: dict[str, Any],
    *,
    member_id: str,
    workdir: Path,
    runtime: str = "cli",
) -> str:
    content = str(message.get("content") or "")
    task = strip_leading_mentions(content, member_id=member_id) or content.strip()
    if runtime.lower() == "pi" or member_id == "agent:pi":
        return task

    sender = message.get("from") or "unknown"
    message_id = message.get("id") or "unknown"
    group_id = message.get("group_id")
    group_line = f"TALK group id: {group_id}\n" if group_id else ""
    return (
        f"You are {member_id}, a {runtime} CLI agent connected to TALK.\n"
        f"Project root: {workdir}\n"
        "Answer the user's task. Keep the final response suitable for posting back into TALK.\n"
        f"{RESPONSE_STYLE_INSTRUCTIONS}"
        f"{DISCUSSION_PROTOCOL_INSTRUCTIONS}"
        "Do not mention internal bridge mechanics unless they are relevant to the task.\n\n"
        f"Sender: {sender}\n"
        f"TALK message id: {message_id}\n\n"
        f"{group_line}"
        "Task:\n"
        f"{task}\n"
    )


def build_cli_task_prompt(
    task: dict[str, Any],
    *,
    member_id: str,
    workdir: Path,
    runtime: str = "cli",
) -> str:
    content = str(task.get("content") or "").strip()
    title = str(task.get("title") or "").strip()

    if runtime.lower() == "pi" or member_id == "agent:pi":
        return f"标题：{title}\n\n{content}" if title else content

    task_id = task.get("id") or "unknown"
    creator = task.get("created_by") or "unknown"
    title_block = f"Title: {title}\n" if title else ""
    return (
        f"You are {member_id}, a {runtime} CLI agent connected to TALK.\n"
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
    )


def format_cli_reply(
    result: CliRunResult,
    *,
    max_chars: int = DEFAULT_MAX_REPLY_CHARS,
    bridge_label: str = "CLI bridge",
    force_one_sentence: bool = False,
) -> str:
    output = clean_cli_output((result.stdout or "").strip())
    error = clean_cli_output((result.stderr or "").strip())

    if result.timed_out:
        text = f"{bridge_label} timed out before producing a final answer."
        if output:
            text += f"\n\nPartial output:\n{output}"
    elif result.returncode != 0:
        text = f"{bridge_label} failed with exit code {result.returncode}."
        if error:
            text += f"\n\nstderr:\n{error}"
        if output:
            text += f"\n\nstdout:\n{output}"
    else:
        text = output or f"({bridge_label} finished without output.)"

    if force_one_sentence and not result.timed_out and result.returncode == 0:
        text = first_sentence(text)

    if len(text) > max_chars:
        remaining = len(text) - max_chars
        text = f"{text[:max_chars].rstrip()}\n\n[truncated {remaining} chars]"
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
) -> bool:
    """Claim and execute one queued task. Returns False when another worker claimed it first."""
    from TALK.client.exceptions import TalkValidationError

    task_id = int(task["id"])
    try:
        claimed = await client.claim_task(task_id, instance_id=instance_id)
    except TalkValidationError as exc:
        if exc.status_code == 409:
            return False
        raise

    task_text = str(claimed.get("content") or "")
    prompt = build_cli_task_prompt(claimed, member_id=member_id, workdir=workdir, runtime=runtime)
    result_message_id: int | None = None
    completion_status = "succeeded"
    last_error: str | None = None

    try:
        result = await run_cli_command(
            command,
            prompt,
            cwd=workdir,
            timeout=timeout,
            prompt_transport=prompt_transport,
        )
        reply = format_cli_reply(
            result,
            max_chars=max_reply_chars,
            bridge_label=bridge_label,
            force_one_sentence=wants_one_sentence(task_text),
        )
        if (runtime.lower() == "pi" or member_id == "agent:pi") and not result.timed_out and result.returncode == 0:
            reply = normalize_pi_reply_language(task_text, reply)
        completion_status = "failed" if result.timed_out or result.returncode != 0 else "succeeded"
        if completion_status == "failed":
            last_error = reply
    except Exception as exc:
        reply = f"{bridge_label} failed before completing task {task_id}: {exc}"
        completion_status = "failed"
        last_error = reply

    creator = claimed.get("created_by")
    if creator:
        try:
            result_message = await client.send_text(reply, to=[str(creator)])
            result_message_id = int(result_message["id"])
        except Exception as exc:
            completion_status = "failed"
            last_error = f"{bridge_label} could not post task result: {exc}"

    await client.complete_task(
        task_id,
        status=completion_status,
        result_message_id=result_message_id,
        last_error=last_error,
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
) -> None:
    sender = message.get("from")
    if not sender:
        return

    task_id = str(message.get("id") or "")
    group_id = message.get("group_id") if isinstance(message.get("group_id"), str) else None
    if report_status is not None:
        await report_status("busy", current_task_id=task_id)

    try:
        if send_ack:
            await client.reply(
                int(message["id"]),
                text=f"{bridge_label} received the task and is working on it.",
                to=[sender],
                group_id=group_id,
            )

        prompt = build_cli_prompt(message, member_id=member_id, workdir=workdir, runtime=runtime)
        result = await run_cli_command(
            command,
            prompt,
            cwd=workdir,
            timeout=timeout,
            prompt_transport=prompt_transport,
        )
        task_text = strip_leading_mentions(
            str(message.get("content") or ""),
            member_id=member_id,
        )
        reply = format_cli_reply(
            result,
            max_chars=max_reply_chars,
            bridge_label=bridge_label,
            force_one_sentence=wants_one_sentence(task_text),
        )
        if (runtime.lower() == "pi" or member_id == "agent:pi") and not result.timed_out and result.returncode == 0:
            reply = normalize_pi_reply_language(task_text, reply)
        visible_reply, actions = parse_talk_actions(reply)
        await execute_talk_actions(
            actions,
            client=client,
            source_message=message,
            member_id=member_id,
            task_text=task_text,
        )
        mark_actions = [action for action in actions if action.action_type == "mark_stance"]
        if not visible_reply and actions:
            visible_reply = "已按讨论协议继续推进。"
        if not visible_reply:
            visible_reply = f"({bridge_label} finished without visible output.)"

        reply_message = await client.reply(int(message["id"]), text=visible_reply, to=[sender], group_id=group_id)
        reply_message_id = int(reply_message["id"]) if reply_message and reply_message.get("id") is not None else None
        for action in mark_actions:
            peer_id = action.target_member_id or str(sender)
            discussion_id = action.discussion_id or await _resolve_discussion_id(
                client,
                group_id=group_id,
                member_id=member_id,
                peer_id=peer_id,
                topic=_discussion_topic_from_text(task_text),
                create_if_missing=group_id is not None,
            )
            stance = action.stance or "answer"
            await _append_discussion_turn(
                client,
                discussion_id=discussion_id,
                message_id=reply_message_id,
                stance=stance,
                target_member_id=peer_id,
                round_index=action.round_index or 1,
            )
            if stance == "disagree":
                await _maybe_escalate_disagreement(
                    client,
                    discussion_id=discussion_id,
                    group_id=group_id,
                    reply_to=reply_message_id,
                )
        if report_status is not None:
            await report_status(
                "error" if result.timed_out or result.returncode != 0 else "idle",
                last_error=reply if result.timed_out or result.returncode != 0 else None,
            )
    except Exception as exc:
        if report_status is not None:
            await report_status("error", current_task_id=task_id, last_error=str(exc))
        raise


async def run_task_queue_worker(
    *,
    client: Any,
    member_id: str,
    workdir: Path,
    instance_id: str,
    args: argparse.Namespace,
    run_lock: asyncio.Lock,
    report_status: Any,
) -> None:
    while True:
        try:
            tasks = await client.list_tasks(target_member_id=member_id, status="queued")
            queued = sorted(tasks, key=lambda item: int(item["id"]))
            for task in queued:
                async with run_lock:
                    await handle_queued_task(
                        task,
                        client=client,
                        member_id=member_id,
                        workdir=workdir,
                        instance_id=instance_id,
                        command=args.command,
                        timeout=args.timeout,
                        max_reply_chars=args.max_reply_chars,
                        runtime=args.runtime,
                        bridge_label=args.bridge_label,
                        prompt_transport=args.prompt_transport,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await report_status("error", last_error=f"task queue worker failed: {exc}")

        await asyncio.sleep(args.task_poll_interval)


async def run_bridge(args: argparse.Namespace) -> None:
    from TALK.client import TalkClient

    member_id = member_id_from_name(args.name)
    workdir = Path(args.workdir).expanduser().resolve()
    client = TalkClient(args.base_url, args.key, poll_interval=args.poll_interval)
    await client.register(member_id, display_name=args.display_name or f"{args.runtime} CLI Bridge ({member_id})")
    instance_id = args.instance_id or f"{member_id}:{uuid4()}"
    host = socket.gethostname()

    async def report_status(
        status: str,
        *,
        current_task_id: str | None = None,
        last_error: str | None = None,
    ) -> None:
        await client.report_instance_status(
            instance_id,
            runtime=args.runtime,
            status=status,
            host=host,
            pid=os.getpid(),
            current_task_id=current_task_id,
            last_error=last_error,
        )

    await report_status("idle")

    run_lock = asyncio.Lock()

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
            )
        )

    try:
        await client.run()
    finally:
        if task_worker is not None:
            task_worker.cancel()
            try:
                await task_worker
            except asyncio.CancelledError:
                pass
        try:
            await report_status("offline")
        finally:
            await client.close()


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
    parser.add_argument("--key", required=True, help="API key for this bridge member")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--instance-id", default=None)
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
    parser.add_argument("--disable-task-queue", action="store_true")
    parser.add_argument("--max-reply-chars", type=int, default=DEFAULT_MAX_REPLY_CHARS)
    parser.add_argument("--respond-to-broadcast", action="store_true")
    parser.add_argument("--send-ack", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == "__main__":
    main()
