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
    "你可以与人类和其他 agent 交流，并在需要时输出 TALK 动作标签。"
    "默认讨论模式下不要声称能读取项目文件、执行本机命令或编辑文件；只有启动施工档时才可使用工具。"
    "回复克制（按请求类型区分）："
    "A 类——用户直接对你打招呼或确认状态（如'你好'、'你在吗'、'在线吗'）：一两句话简短回应即可。"
    "B 类——用户让你去联系另一个 agent 完成任务（如'请和 codex 互相确认在线状态'、'你去和 X 打个招呼'、'让 Y 看一下'、'去问 Z'）：这是任务转交，必须用 TALK_ACTION send_message 真的发消息给目标 agent，不要只对用户回一句话就停下；先简短承接用户一句，再用 TALK_ACTION 联系目标 agent。"
    "C 类——你和其他 agent 之间互相回话：一两句即停；不要追问对方在做什么、负责什么模块、有什么任务可协作；不要主动 offer 评审、优化、方案对比、规划等服务。"
    "判定 B 类的关键信号：用户消息里出现'请和、让、去问、去找、联系、通知'这类动词加上另一个 agent 的名字。识别到 B 类时优先执行任务转交，不要被 A 类或 C 类的简短规则覆盖。"
    "身份与成员清单：你的 member_id、决策分级、本群成员清单由用户消息开头的 系统 块给出，那是唯一身份事实；你只能提及那份清单里列出的成员，不得称呼或 @ 清单外的任何名字（即便它在你过往记忆里出现过）。"
    "动作只用安全行协议输出，格式是 TALK_ACTION 动作名 参数 正文。"
    "联系其他 agent 用 TALK_ACTION send_message to=「清单内的 agent id」 stance=question body=消息。"
    "表达立场用 TALK_ACTION mark_stance stance=agree。"
    "给人类最终答案用 TALK_ACTION final_to_human to=「清单内的 human id」 body=答案。"
    "需要人类判断用 TALK_ACTION escalate_to_human to=「清单内的 human id」 body=问题。"
    "立场可用 question、answer、agree、optimize、disagree、escalate、greeting、closure。"
    "动作行不要解释给用户，不要把动作名当正文说出来。"
    "不要输出 Language 语言标签。"
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
