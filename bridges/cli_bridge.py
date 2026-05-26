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
SAFE_ACTION_RE = re.compile(
    r"^[ \t]*TALK_ACTION[ \t]+(?P<type>[a-zA-Z_][\w-]*)(?P<attrs>[^\r\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)
SAFE_ACTION_ATTR_RE = re.compile(r"\b([a-zA-Z_][\w-]*)=([^\s]+)")
ACTION_TYPES = {"send_message", "mark_stance", "escalate_to_human", "final_to_human"}
ACTION_STANCES = {"question", "answer", "agree", "optimize", "disagree", "escalate"}
DISCUSSION_MAX_AUTO_TURNS = 3
DISCUSSION_EXTENSION_CLOSE_TURNS = DISCUSSION_MAX_AUTO_TURNS + 1
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


async def _update_discussion_status(client: Any, discussion_id: int | None, status: str) -> None:
    if discussion_id is None:
        return
    try:
        await client.update_discussion(discussion_id, status=status)
    except AttributeError:
        pass
    except Exception as exc:
        if not _is_talk_not_found(exc):
            raise


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
    remaining = max(0, DISCUSSION_MAX_AUTO_TURNS - len(turns))
    human_hint = human_id or "human:bobo"
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
        f"确需向人类裁决时用 TALK_ACTION escalate_to_human to={human_hint} body=裁决问题。"
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
    text = f"收到。这个扩展先停在这里；如果还需要我继续判断，请在群里 @{responder_id} 另开请求。"
    message = await client.reply(reply_to, text=text, to=[target_agent_id], group_id=group_id)
    message_id = int(message["id"]) if message and message.get("id") is not None else None
    await _append_discussion_turn(
        client,
        discussion_id=discussion_id,
        message_id=message_id,
        stance="answer",
        target_member_id=target_agent_id,
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

    for action in actions:
        target = action.to or action.target_member_id
        if action.action_type == "send_message":
            if not target or not target.startswith("agent:"):
                summaries.append("我不能代发给这个目标；请确认要联系的 agent。")
                continue
            if group_id:
                if group_member_ids is None:
                    group_member_ids = await _group_member_ids(client, group_id)
                if group_member_ids is not None and target not in group_member_ids:
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
                target = await _find_human_reviewer(client, group_id)
            if not target or not target.startswith("human:"):
                summaries.append("escalate_to_human skipped: target must be a human member")
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
    discussion_context: str | None = None,
) -> str:
    content = str(message.get("content") or "")
    task = strip_leading_mentions(content, member_id=member_id) or content.strip()
    context_block = f"\n\n{discussion_context}" if discussion_context else ""
    if runtime.lower() == "pi" or member_id == "agent:pi":
        return f"{task}{context_block}"

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
        f"{task}{context_block}\n"
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

    if result.timed_out:
        text = f"{bridge_label} 暂时没有返回结果，错误详情已记录。"
    elif result.returncode != 0:
        text = f"{bridge_label} 运行失败，错误详情已记录。"
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
            detail = "\n".join(part for part in (clean_cli_output(result.stderr), clean_cli_output(result.stdout)) if part)
            last_error = detail or reply
    except Exception as exc:
        reply = f"{bridge_label} 运行失败，错误详情已记录。"
        completion_status = "failed"
        last_error = f"{bridge_label} failed before completing task {task_id}: {exc}"

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

        task_text = strip_leading_mentions(
            str(message.get("content") or ""),
            member_id=member_id,
        )
        sender_id = str(sender)
        discussion: dict[str, Any] | None = None
        turns: list[dict[str, Any]] = []
        discussion_context = ""
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
            if discussion_id is not None and latest_stance == "disagree" and len(turns) >= DISCUSSION_EXTENSION_CLOSE_TURNS:
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
            if discussion_id is not None and latest_stance != "disagree" and len(turns) >= DISCUSSION_EXTENSION_CLOSE_TURNS:
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

        prompt = build_cli_prompt(
            message,
            member_id=member_id,
            workdir=workdir,
            runtime=runtime,
            discussion_context=discussion_context,
        )
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
        visible_reply, actions = parse_talk_actions(reply)
        visible_reply = sanitize_visible_reply(visible_reply)
        action_notices = await execute_talk_actions(
            actions,
            client=client,
            source_message=message,
            member_id=member_id,
            task_text=task_text,
        )
        visible_action_notices = [notice for notice in action_notices if not notice.startswith("sent ")]
        if visible_action_notices:
            visible_reply = visible_action_notices[0]
        mark_actions = [action for action in actions if action.action_type == "mark_stance"]
        has_final_action = any(action.action_type == "final_to_human" for action in actions)
        should_post_reply = True
        if not visible_reply and actions:
            if sender_id.startswith("agent:"):
                should_post_reply = False
            else:
                visible_reply = "已按讨论协议继续推进。"
        if not visible_reply:
            if should_post_reply:
                visible_reply = f"({bridge_label} finished without visible output.)"

        reply_message_id: int | None = None
        if should_post_reply:
            reply_message = await client.reply(int(message["id"]), text=visible_reply, to=[sender], group_id=group_id)
            reply_message_id = int(reply_message["id"]) if reply_message and reply_message.get("id") is not None else None
        if sender_id.startswith("agent:") and discussion and not mark_actions and reply_message_id is not None:
            await _append_discussion_turn(
                client,
                discussion_id=int(discussion["id"]) if discussion.get("id") is not None else None,
                message_id=reply_message_id,
                stance="answer",
                target_member_id=sender_id,
                round_index=1,
            )
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
            stance = action.stance or "answer"
            await _append_discussion_turn(
                client,
                discussion_id=discussion_id,
                message_id=reply_message_id,
                stance=stance,
                target_member_id=peer_id,
                round_index=action.round_index or 1,
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
