#!/usr/bin/env python3
"""pi CLI bridge for TALK."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridges import cli_bridge

PI_SYSTEM_PROMPT = (
    "You are agent:pi in TALK, a concise chat agent. "
    "Reply only to the user's Task. "
    "If the user asks what you can do or asks for an introduction, briefly explain that you can do lightweight chat, "
    "answer questions, help break down tasks, and participate in TALK group discussions; also mention that the default "
    "bridge mode does not read project files or use tools. "
    "Do not read or summarize project files, AGENTS.md, CLAUDE.md, progress docs, or runtime status unless the user explicitly asks. "
    "Never output status tables for greetings or presence checks. "
    "If the user asks for one sentence, answer in exactly one sentence."
)
DEFAULT_PI_COMMAND = (
    "pi --print --mode text --no-context-files --no-tools --no-session --thinking off "
    f"--system-prompt {shlex.quote(PI_SYSTEM_PROMPT)}"
)
DEFAULT_TIMEOUT_SEC = cli_bridge.DEFAULT_TIMEOUT_SEC
DEFAULT_MAX_REPLY_CHARS = cli_bridge.DEFAULT_MAX_REPLY_CHARS
DEFAULT_TASK_POLL_INTERVAL = cli_bridge.DEFAULT_TASK_POLL_INTERVAL


async def run_bridge(args: argparse.Namespace) -> None:
    args.command = args.pi_command
    await cli_bridge.run_bridge(args)


def build_parser() -> argparse.ArgumentParser:
    return cli_bridge.build_parser(
        description="TALK pi CLI bridge",
        default_name="pi",
        default_runtime="pi",
        default_command=os.environ.get("TALK_PI_COMMAND", DEFAULT_PI_COMMAND),
        command_help="pi CLI command. The TALK prompt is appended as the final argv argument.",
        command_option="--pi-command",
        command_dest="pi_command",
        command_metavar="PI_COMMAND",
        default_prompt_transport="argv",
        default_bridge_label="pi bridge",
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == "__main__":
    main()
