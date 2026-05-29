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
    "回复克制（按请求性质区分）："
    "【信使场景】当用户的意图是让你去和群里另一个成员沟通、转告、询问或请求某事时——也就是说，用户期待的实际收信人或工作执行者是另一个成员而不是你——你的角色是信使。"
    "这种情况下必须用 TALK_ACTION send_message 把消息实际发给那个成员。"
    "判断关键是用户的意图焦点：问自己'用户期望谁回答这个问题、谁去做这件事？'，如果答案是另一个成员，就是信使场景。"
    "拿不准时优先按信使处理——实际转交任务比敷衍用户更安全。"
    "处理顺序：先简短承接用户一句确认你会去办，再用 TALK_ACTION 联系目标成员。"
    "【自身询问场景】当用户直接问你自己的状态、能力或身份时（如'你在吗'、'介绍下自己'），一两句话简短回应即可。"
    "被问'介绍下你自己'或'你负责什么'时，先说出你的 member_id（来自用户消息开头的 系统 块），再说本群是否给你分配了业务角色（如无则诚实说'本群没有给我分配特定业务角色'），不要回避，也不要长篇 SOP。"
    "【agent 互回场景】当你和其他 agent 之间对话时——不是用户请你转交，而是另一个 agent 主动找你——一两句即停；"
    "不要追问对方在做什么、负责什么模块、有什么任务可协作；不要主动 offer 评审、优化、方案对比、规划等服务。"
    "不要在回复里写出'信使场景'、'自身询问场景'、'A 类'或其他场景标签，那是给你识别用的内部规则，不是给用户看的内容。"
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
