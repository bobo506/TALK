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
from typing import Any
from urllib.parse import quote

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


def _effort_diagnostic(event: str) -> None:
    """固定、有界的一行诊断；不回显配置内容或绑定细节。"""
    try:
        print("[Kimi bridge] " + event, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


async def _binding_for(client: Any, project: str, member_id: str):
    """读公开绑定（351-A 起含有效强度与能力来源）；失败返回 None，不阻断任务。"""
    try:
        rows = await client._request_json(
            "GET", "/api/projects/" + quote(project, safe="") + "/agents"
        )
    except Exception:
        _effort_diagnostic("kimi_effort_lookup_failed")
        return None
    if isinstance(rows, dict):
        rows = rows.get("data")
    if not isinstance(rows, list):
        return None
    matches = [row for row in rows if isinstance(row, dict) and row.get("member_id") == member_id]
    return matches[0].get("binding") if len(matches) == 1 else None


def make_effort_hook(client: Any, args: argparse.Namespace):
    """351-D：每个任务执行前把生效强度写进角色自己的 config.toml。

    只在能安全确定目标值时写入（用户覆盖 > 模型默认，且必须通过公开清单校验）；
    读取失败/能力未知时保留原配置并留一行诊断，绝不猜档位。
    """
    from bridges.kimi_effort import apply_role_config_effort, resolve_target_effort

    async def apply_effort(task: Any) -> None:
        del task
        project = str(
            getattr(args, "project_id", None) or os.environ.get("TALK_PROJECT_ID") or ""
        ).strip()
        alias = getattr(args, "kimi_model", None)
        home = os.environ.get("KIMI_CODE_HOME")
        if not project or not isinstance(alias, str) or not alias.strip() or not home:
            return
        binding = await _binding_for(
            client, project, cli_bridge.member_id_from_name(args.name)
        )
        target = resolve_target_effort(binding)
        if target is None:
            if isinstance(binding, dict) and binding.get("effort_override"):
                _effort_diagnostic("kimi_effort_capability_unknown")
            return
        try:
            apply_role_config_effort(Path(home) / "config.toml", alias, target)
        except Exception:
            _effort_diagnostic("kimi_effort_apply_failed")

    return apply_effort


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
        # 351-D：注册逐任务钩子；cli_bridge 在拿到 client 后构造它。
        args.before_task_factory = make_effort_hook
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
