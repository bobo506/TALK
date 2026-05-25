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
    "你是 TALK Group Hall 里的 pi，是群聊参与者，不是 TALK 管理员或说明书。按用户语言自然回复。"
    "你可以与人类和其他 agent 交流，评审方案，提出优化或分歧，并在需要时输出 TALK 动作标签。"
    "默认讨论模式下不要声称能读取项目文件、执行本机命令或编辑文件；只有启动施工档时才可使用工具。"
    "动作格式：<talk-action type=\"send_message\" to=\"agent:name\" stance=\"question\">消息</talk-action>，"
    "<talk-action type=\"mark_stance\" stance=\"agree|optimize|disagree|answer\"></talk-action>，"
    "或 <talk-action type=\"escalate_to_human\" to=\"human:name\">问题</talk-action>。"
    "不要输出 <Language: ...> 之类语言标签。"
)
DEFAULT_PI_COMMAND = (
    "pi --print --mode text --no-context-files --no-tools --no-session --thinking off "
    f"--system-prompt {DEFAULT_SYSTEM_PROMPT!r}"
)
DEFAULT_PI_TOOLS_COMMAND = (
    "pi --print --mode text --no-context-files --no-session --thinking off "
    "--tools read,grep,find,ls,bash,edit,write "
    f"--system-prompt {DEFAULT_SYSTEM_PROMPT!r}"
)
DEFAULT_TIMEOUT_SEC = cli_bridge.DEFAULT_TIMEOUT_SEC
DEFAULT_MAX_REPLY_CHARS = cli_bridge.DEFAULT_MAX_REPLY_CHARS
DEFAULT_TASK_POLL_INTERVAL = cli_bridge.DEFAULT_TASK_POLL_INTERVAL


async def run_bridge(args: argparse.Namespace) -> None:
    if args.pi_execution_profile == "tools" and args.pi_command == DEFAULT_PI_COMMAND:
        args.pi_command = DEFAULT_PI_TOOLS_COMMAND
    args.command = args.pi_command
    await cli_bridge.run_bridge(args)


def build_parser() -> argparse.ArgumentParser:
    parser = cli_bridge.build_parser(
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
    parser.add_argument(
        "--pi-execution-profile",
        choices=("discussion", "tools"),
        default="discussion",
        help="pi runtime permission profile. 'discussion' keeps tools disabled; 'tools' enables local read/bash/edit/write tools when using the default command.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == "__main__":
    main()
