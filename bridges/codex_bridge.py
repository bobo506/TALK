#!/usr/bin/env python3
"""Minimal Codex CLI bridge for TALK."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import sys
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CODEX_COMMAND = "codex exec --skip-git-repo-check --sandbox workspace-write --color never -"
DEFAULT_TIMEOUT_SEC = 600
DEFAULT_MAX_REPLY_CHARS = 12000


@dataclass(frozen=True)
class CodexRunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def member_id_from_name(name: str) -> str:
    return name if name.startswith("agent:") else f"agent:{name}"


def parse_command(command: str) -> list[str]:
    parsed = shlex.split(command, posix=True)
    if not parsed:
        raise ValueError("codex command cannot be empty")
    return parsed


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


def build_codex_prompt(message: dict[str, Any], *, member_id: str, workdir: Path) -> str:
    content = str(message.get("content") or "")
    task = strip_leading_mentions(content, member_id=member_id) or content.strip()
    sender = message.get("from") or "unknown"
    message_id = message.get("id") or "unknown"

    return (
        f"You are {member_id}, a Codex CLI agent connected to TALK.\n"
        f"Project root: {workdir}\n"
        "Answer the user's task. Keep the final response suitable for posting back into TALK.\n"
        "Do not mention internal bridge mechanics unless they are relevant to the task.\n\n"
        f"Sender: {sender}\n"
        f"TALK message id: {message_id}\n\n"
        "Task:\n"
        f"{task}\n"
    )


def format_codex_reply(result: CodexRunResult, *, max_chars: int = DEFAULT_MAX_REPLY_CHARS) -> str:
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()

    if result.timed_out:
        text = "Codex bridge timed out before producing a final answer."
        if output:
            text += f"\n\nPartial output:\n{output}"
    elif result.returncode != 0:
        text = f"Codex bridge failed with exit code {result.returncode}."
        if error:
            text += f"\n\nstderr:\n{error}"
        if output:
            text += f"\n\nstdout:\n{output}"
    else:
        text = output or "(Codex finished without output.)"

    if len(text) > max_chars:
        remaining = len(text) - max_chars
        text = f"{text[:max_chars].rstrip()}\n\n[truncated {remaining} chars]"
    return text


async def run_codex_command(
    command: str | Sequence[str],
    prompt: str,
    *,
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> CodexRunResult:
    args = parse_command(command) if isinstance(command, str) else list(command)
    if not args:
        raise ValueError("codex command cannot be empty")

    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(prompt.encode("utf-8")),
            timeout=timeout,
        )
        return CodexRunResult(
            returncode=int(process.returncode or 0),
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return CodexRunResult(
            returncode=-1,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            timed_out=True,
        )


async def run_bridge(args: argparse.Namespace) -> None:
    from TALK.client import TalkClient

    member_id = member_id_from_name(args.name)
    workdir = Path(args.workdir).expanduser().resolve()
    client = TalkClient(args.base_url, args.key, poll_interval=args.poll_interval)
    await client.register(member_id, display_name=args.display_name or f"Codex Bridge ({member_id})")
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
            runtime="codex",
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

        sender = message.get("from")
        if not sender:
            return

        async with run_lock:
            task_id = str(message.get("id") or "")
            await report_status("busy", current_task_id=task_id)
            try:
                if args.send_ack:
                    await client.reply(
                        int(message["id"]),
                        text="Codex bridge received the task and is working on it.",
                        to=[sender],
                    )

                prompt = build_codex_prompt(message, member_id=member_id, workdir=workdir)
                result = await run_codex_command(
                    args.codex_command,
                    prompt,
                    cwd=workdir,
                    timeout=args.timeout,
                )
                reply = format_codex_reply(result, max_chars=args.max_reply_chars)
                await client.reply(int(message["id"]), text=reply, to=[sender])
                await report_status(
                    "error" if result.timed_out or result.returncode != 0 else "idle",
                    last_error=reply if result.timed_out or result.returncode != 0 else None,
                )
            except Exception as exc:
                try:
                    await report_status("error", current_task_id=task_id, last_error=str(exc))
                finally:
                    raise

    try:
        await client.run()
    finally:
        try:
            await report_status("offline")
        finally:
            await client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TALK Codex CLI bridge")
    parser.add_argument("--name", default="codex", help="Agent name or full member id. Default: codex")
    parser.add_argument("--key", required=True, help="API key for this bridge member")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--instance-id", default=None)
    parser.add_argument("--workdir", default=".", help="Working directory passed to Codex")
    parser.add_argument("--codex-command", default=os.environ.get("TALK_CODEX_COMMAND", DEFAULT_CODEX_COMMAND))
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--poll-interval", type=float, default=2.0)
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
