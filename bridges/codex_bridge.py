#!/usr/bin/env python3
"""Codex CLI bridge for TALK.

This module keeps the original Codex-specific entry point while reusing the
generic CLI bridge implementation.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridges import cli_bridge

DEFAULT_CODEX_COMMAND = "codex exec --skip-git-repo-check --sandbox workspace-write --color never -"
DEFAULT_TIMEOUT_SEC = cli_bridge.DEFAULT_TIMEOUT_SEC
DEFAULT_MAX_REPLY_CHARS = cli_bridge.DEFAULT_MAX_REPLY_CHARS
DEFAULT_TASK_POLL_INTERVAL = cli_bridge.DEFAULT_TASK_POLL_INTERVAL

CodexRunResult = cli_bridge.CliRunResult
member_id_from_name = cli_bridge.member_id_from_name
parse_command = cli_bridge.parse_command
strip_leading_mentions = cli_bridge.strip_leading_mentions
should_handle_message = cli_bridge.should_handle_message


def default_codex_command() -> str:
    if os.environ.get("TALK_CODEX_COMMAND"):
        return os.environ["TALK_CODEX_COMMAND"]

    windows_codex = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    if windows_codex.exists():
        return f"{windows_codex.as_posix()} exec --skip-git-repo-check --sandbox workspace-write --color never -"

    return DEFAULT_CODEX_COMMAND


def build_codex_prompt(message: dict[str, Any], *, member_id: str, workdir: Path) -> str:
    return cli_bridge.build_cli_prompt(message, member_id=member_id, workdir=workdir, runtime="Codex")


def build_codex_task_prompt(task: dict[str, Any], *, member_id: str, workdir: Path) -> str:
    return cli_bridge.build_cli_task_prompt(task, member_id=member_id, workdir=workdir, runtime="Codex")


def format_codex_reply(
    result: CodexRunResult,
    *,
    max_chars: int = DEFAULT_MAX_REPLY_CHARS,
) -> str:
    return cli_bridge.format_cli_reply(result, max_chars=max_chars, bridge_label="Codex bridge")


async def run_codex_command(
    command: str | Sequence[str],
    prompt: str,
    *,
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> CodexRunResult:
    return await cli_bridge.run_cli_command(command, prompt, cwd=cwd, timeout=timeout)


async def handle_queued_task(
    task: dict[str, Any],
    *,
    client: Any,
    member_id: str,
    workdir: Path,
    instance_id: str,
    codex_command: str | Sequence[str],
    timeout: int,
    max_reply_chars: int,
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

    prompt = build_codex_task_prompt(claimed, member_id=member_id, workdir=workdir)
    result_message_id: int | None = None
    completion_status = "succeeded"
    last_error: str | None = None

    try:
        result = await run_codex_command(codex_command, prompt, cwd=workdir, timeout=timeout)
        reply = format_codex_reply(result, max_chars=max_reply_chars)
        completion_status = "failed" if result.timed_out or result.returncode != 0 else "succeeded"
        if completion_status == "failed":
            last_error = reply
    except Exception as exc:
        reply = f"Codex bridge failed before completing task {task_id}: {exc}"
        completion_status = "failed"
        last_error = reply

    creator = claimed.get("created_by")
    if creator:
        try:
            result_message = await client.send_text(reply, to=[str(creator)])
            result_message_id = int(result_message["id"])
        except Exception as exc:
            completion_status = "failed"
            last_error = f"Codex bridge could not post task result: {exc}"

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
    args.command = args.codex_command
    args.runtime = "codex"
    args.bridge_label = "Codex bridge"
    await cli_bridge.run_task_queue_worker(
        client=client,
        member_id=member_id,
        workdir=workdir,
        instance_id=instance_id,
        args=args,
        run_lock=run_lock,
        report_status=report_status,
    )


async def run_bridge(args: argparse.Namespace) -> None:
    args.command = args.codex_command
    args.runtime = "codex"
    args.bridge_label = "Codex bridge"
    await cli_bridge.run_bridge(args)


def build_parser() -> argparse.ArgumentParser:
    parser = cli_bridge.build_parser(
        description="TALK Codex CLI bridge",
        default_name="codex",
        default_runtime="codex",
        default_command=default_codex_command(),
        command_help="Codex CLI command that reads the TALK prompt from stdin",
        command_option="--codex-command",
        command_dest="codex_command",
        command_metavar="CODEX_COMMAND",
        default_bridge_label="Codex bridge",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == "__main__":
    main()
