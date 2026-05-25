#!/usr/bin/env python3
"""pi CLI bridge for TALK."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridges import cli_bridge

DEFAULT_SYSTEM_PROMPT = (
    "你是 TALK 群聊里的 pi。按用户语言自然回复。"
    "默认不要声称能读取项目文件、执行命令、编辑文件或调用工具。"
    "不要输出 <Language: ...> 之类语言标签。"
)
DEFAULT_PI_COMMAND = (
    "pi --print --mode text --no-context-files --no-tools --no-session --thinking off "
    f"--system-prompt {DEFAULT_SYSTEM_PROMPT!r}"
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
