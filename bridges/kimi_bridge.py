#!/usr/bin/env python3
"""Official Kimi Code CLI bridge for TALK."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridges import cli_bridge
from cli.profiles import compose_system_prompt, load_profile

DEFAULT_KIMI_COMMAND = "kimi --output-format stream-json -p"
KIMI_DISCUSSION_TOOLS: tuple[str, ...] = ()
KIMI_REVIEW_TOOLS = ("Read", "Grep", "Glob", "Bash")
KIMI_FULL_TOOLS = (*KIMI_REVIEW_TOOLS, "Edit", "Write")


def _command_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _agent_markdown(
    *,
    name: str,
    description: str,
    tools: tuple[str, ...],
    system_prompt: str,
) -> str:
    tool_lines = "\n".join(f"  - {tool}" for tool in tools)
    tools_block = f"tools:\n{tool_lines}" if tool_lines else "tools: []"
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"{tools_block}\n"
        "subagents: []\n"
        "---\n\n"
        f"{system_prompt.strip()}\n"
    )


def _write_agent_file(
    path: Path,
    *,
    name: str,
    description: str,
    tools: tuple[str, ...],
    system_prompt: str,
) -> None:
    path.write_text(
        _agent_markdown(
            name=name,
            description=description,
            tools=tools,
            system_prompt=system_prompt,
        ),
        encoding="utf-8",
    )


def _profiled_prompt(args: argparse.Namespace, base_prompt: str) -> str:
    project_root = getattr(args, "project", None)
    if not project_root:
        return base_prompt
    member_id = cli_bridge.member_id_from_name(args.name)
    profile = load_profile(project_root, member_id)
    return compose_system_prompt(base_prompt, profile)


def _build_kimi_command(
    *,
    agent_file: Path,
    skills_dir: Path,
    model: str | None,
) -> str:
    args = [
        "kimi",
        "--output-format",
        "stream-json",
        "--agent-file",
        _command_path(agent_file),
        "--skills-dir",
        _command_path(skills_dir),
    ]
    if model:
        args.extend(("--model", model))
    # cli_bridge appends the TALK prompt as the final argv value consumed by -p.
    args.append("-p")
    return " ".join(shlex.quote(value) for value in args)


def materialize_kimi_commands(
    args: argparse.Namespace,
    runtime_dir: Path,
) -> tuple[str, str, str]:
    """Create controlled Agent files and return message/task/preflight commands."""
    if args.kimi_command != DEFAULT_KIMI_COMMAND:
        override = args.kimi_command
        return override, override, args.task_preflight_command or override

    runtime_dir.mkdir(parents=True, exist_ok=True)
    skills_dir = runtime_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    discussion_file = runtime_dir / "discussion.md"
    task_file = runtime_dir / "task.md"
    preflight_file = runtime_dir / "preflight.md"
    discussion_prompt = (
        f"{cli_bridge.FUNCTION_CALLING_SYSTEM_PROMPT}\n"
        f"{cli_bridge.DISCUSSION_PROTOCOL_INSTRUCTIONS}"
    )
    task_tools = KIMI_REVIEW_TOOLS if args.kimi_task_profile == "review" else KIMI_FULL_TOOLS
    _write_agent_file(
        discussion_file,
        name="talk-kimi-discussion",
        description="TALK Group Hall 中无本地工具的 Kimi 参与者",
        tools=KIMI_DISCUSSION_TOOLS,
        system_prompt=_profiled_prompt(args, discussion_prompt),
    )
    _write_agent_file(
        task_file,
        name="talk-kimi-task",
        description="TALK Task Hall 中执行 Review 与 Test 的 Kimi Agent",
        tools=task_tools,
        system_prompt=_profiled_prompt(args, cli_bridge.TASK_RUNNER_SYSTEM_PROMPT),
    )
    _write_agent_file(
        preflight_file,
        name="talk-kimi-preflight",
        description="TALK Task Hall 领取前无工具预检 Agent",
        tools=(),
        system_prompt=_profiled_prompt(args, cli_bridge.TASK_PREFLIGHT_SYSTEM_PROMPT),
    )

    message_command = _build_kimi_command(
        agent_file=discussion_file,
        skills_dir=skills_dir,
        model=args.kimi_model,
    )
    task_command = _build_kimi_command(
        agent_file=task_file,
        skills_dir=skills_dir,
        model=args.kimi_model,
    )
    preflight_command = args.task_preflight_command or _build_kimi_command(
        agent_file=preflight_file,
        skills_dir=skills_dir,
        model=args.kimi_model,
    )
    return message_command, task_command, preflight_command


async def run_bridge(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(prefix="talk-kimi-bridge-") as temp_dir:
        message_command, task_command, preflight_command = materialize_kimi_commands(
            args,
            Path(temp_dir),
        )
        args.kimi_command = message_command
        args.command = message_command
        args.task_command = task_command
        args.task_preflight_command = preflight_command
        await cli_bridge.run_bridge(args)


def build_parser() -> argparse.ArgumentParser:
    parser = cli_bridge.build_parser(
        description="TALK official Kimi Code CLI bridge",
        default_name="kimi",
        default_runtime="kimi-code",
        default_command=os.environ.get("TALK_KIMI_COMMAND", DEFAULT_KIMI_COMMAND),
        command_help="Kimi Code CLI command. The TALK prompt is appended as the final -p argv value.",
        command_option="--kimi-command",
        command_dest="kimi_command",
        command_metavar="KIMI_COMMAND",
        default_prompt_transport="argv",
        default_bridge_label="Kimi Code bridge",
    )
    parser.add_argument(
        "--kimi-task-profile",
        choices=("review", "tools"),
        default="review",
        help=(
            "Task runtime permission profile. 'review' allows Read/Grep/Glob/Bash; "
            "'tools' additionally allows Edit/Write. Discussion and preflight stay tool-free."
        ),
    )
    parser.add_argument(
        "--kimi-model",
        default=None,
        help="Optional Kimi Code model alias; otherwise use the CLI configured default model.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == "__main__":
    main()
