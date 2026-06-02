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

# ---------------------------------------------------------------------------
# pi 扩展路径（talk_send 工具）
# 用正斜杠避免 Windows 反斜杠被 shlex.split(posix=True) 当成转义符
# ---------------------------------------------------------------------------
_TALK_EXTENSION_PATH = str(PROJECT_ROOT / "bridges" / "talk_tools_extension.ts").replace("\\", "/")

# ---------------------------------------------------------------------------
# 系统层 prompt：角色、输出通道、单轮语义与反工具幻觉约束。
# 工具能力说明由 pi runtime 的 extension/tool catalog 注入。
# ---------------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = cli_bridge.FUNCTION_CALLING_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# pi 命令模板
# ---------------------------------------------------------------------------
# 旧文本协议命令（保留作过渡兼容）
DEFAULT_PI_COMMAND_LEGACY = (
    "pi --print --mode text --no-context-files --no-tools --no-session --thinking off "
    f"--system-prompt {DEFAULT_SYSTEM_PROMPT!r}"
)
# 施工档命令（文件工具启用）
DEFAULT_PI_TOOLS_COMMAND = (
    "pi --print --mode text --no-context-files --no-extensions --no-session --thinking off "
    "--tools read,grep,find,ls,bash,edit,write "
    f"--system-prompt {DEFAULT_SYSTEM_PROMPT!r}"
)
# 当前默认命令：function-calling 模式
# --no-builtin-tools  禁用 read/bash/edit/write 等(LLM 表面只剩 talk_send)
# --no-extensions     禁用自动发现扩展(规避 plan-mode 在 rebindSession 中
#                     setActiveTools(NORMAL_MODE_TOOLS) 覆盖 talk_send 的 bug)
# --extension <path>  显式加载我们自己的 talk_tools_extension.ts 不受 -ne 影响
DEFAULT_PI_COMMAND = (
    f"pi --print --mode text --no-context-files --no-builtin-tools --no-extensions "
    f"--tools talk_send --no-session --thinking off "
    f"--extension {_TALK_EXTENSION_PATH} "
    f"--system-prompt {DEFAULT_SYSTEM_PROMPT!r}"
)

DEFAULT_TIMEOUT_SEC = cli_bridge.DEFAULT_TIMEOUT_SEC
DEFAULT_MAX_REPLY_CHARS = cli_bridge.DEFAULT_MAX_REPLY_CHARS
DEFAULT_TASK_POLL_INTERVAL = cli_bridge.DEFAULT_TASK_POLL_INTERVAL


async def run_bridge(args: argparse.Namespace) -> None:
    if args.pi_execution_profile == "tools" and args.pi_command == DEFAULT_PI_COMMAND:
        args.pi_command = DEFAULT_PI_TOOLS_COMMAND
    args.command = args.pi_command
    # 把 TALK 连接信息注入环境变量，供 talk_tools_extension.ts 使用
    # 每个 bridge 实例必须用自己的 key/url/id，不能复用其他实例的旧值
    os.environ["TALK_API_KEY"] = args.key
    os.environ["TALK_BASE_URL"] = args.base_url
    os.environ["TALK_MEMBER_ID"] = cli_bridge.member_id_from_name(args.name)
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
