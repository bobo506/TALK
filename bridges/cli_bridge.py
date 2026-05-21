#!/usr/bin/env python3
"""Generic CLI bridge for TALK agent runtimes."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_TIMEOUT_SEC = 600
DEFAULT_MAX_REPLY_CHARS = 12000
DEFAULT_TASK_POLL_INTERVAL = 2.0
DEFAULT_COMMAND = os.environ.get("TALK_CLI_COMMAND", "")
PROMPT_TRANSPORTS = {"stdin", "argv"}


@dataclass(frozen=True)
class CliRunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def member_id_from_name(name: str) -> str:
    return name if name.startswith("agent:") else f"agent:{name}"


def parse_command(command: str) -> list[str]:
    parsed = shlex.split(command, posix=True)
    if not parsed:
        raise ValueError("CLI command cannot be empty")
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


def build_cli_prompt(
    message: dict[str, Any],
    *,
    member_id: str,
    workdir: Path,
    runtime: str = "cli",
) -> str:
    content = str(message.get("content") or "")
    task = strip_leading_mentions(content, member_id=member_id) or content.strip()
    sender = message.get("from") or "unknown"
    message_id = message.get("id") or "unknown"

    return (
        f"You are {member_id}, a {runtime} CLI agent connected to TALK.\n"
        f"Project root: {workdir}\n"
        "Answer the user's task. Keep the final response suitable for posting back into TALK.\n"
        "Do not mention internal bridge mechanics unless they are relevant to the task.\n\n"
        f"Sender: {sender}\n"
        f"TALK message id: {message_id}\n\n"
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
    task_id = task.get("id") or "unknown"
    creator = task.get("created_by") or "unknown"
    title = str(task.get("title") or "").strip()

    title_block = f"Title: {title}\n" if title else ""
    return (
        f"You are {member_id}, a {runtime} CLI agent connected to TALK.\n"
        f"Project root: {workdir}\n"
        "Answer the queued Agent task. Keep the final response suitable for posting back into TALK.\n"
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
) -> str:
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()

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
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return CliRunResult(
            returncode=-1,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
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
        reply = format_cli_reply(result, max_chars=max_reply_chars, bridge_label=bridge_label)
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
                        text=f"{args.bridge_label} received the task and is working on it.",
                        to=[sender],
                    )

                prompt = build_cli_prompt(message, member_id=member_id, workdir=workdir, runtime=args.runtime)
                result = await run_cli_command(
                    args.command,
                    prompt,
                    cwd=workdir,
                    timeout=args.timeout,
                    prompt_transport=args.prompt_transport,
                )
                reply = format_cli_reply(result, max_chars=args.max_reply_chars, bridge_label=args.bridge_label)
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
