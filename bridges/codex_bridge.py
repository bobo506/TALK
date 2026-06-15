#!/usr/bin/env python3
"""Codex CLI bridge for TALK.

This module keeps the original Codex-specific entry point while reusing the
generic CLI bridge implementation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridges import cli_bridge
from cli.profiles import compose_system_prompt, load_profile

_MCP_SERVER_PATH = str(PROJECT_ROOT / "bridges" / "talk_send_mcp.py").replace("\\", "/")
CODEX_SYSTEM_INSTRUCTIONS = cli_bridge.FUNCTION_CALLING_SYSTEM_PROMPT


def _codex_config_arg(key: str, value: Any) -> str:
    return shlex.quote(f"{key}={json.dumps(value, ensure_ascii=False)}")


_CODEX_SYSTEM_CONFIG_ARG = _codex_config_arg("base_instructions", CODEX_SYSTEM_INSTRUCTIONS)
_CODEX_MCP_COMMAND_CONFIG_ARG = _codex_config_arg("mcp_servers.talk_send.command", "python")
_CODEX_MCP_ARGS_CONFIG_ARG = _codex_config_arg("mcp_servers.talk_send.args", [_MCP_SERVER_PATH])
# Windows 下 MCP server 子进程必须强制 UTF-8，否则 stdin/stdout 走系统 codepage(cp936)，
# 处理中文 prompt/参数时初始化失败:"invalid unicode code point"。
# Per-call TALK_* 环境变量(TALK_API_KEY/TALK_BASE_URL/TALK_MEMBER_ID/TALK_GROUP_ID/
# TALK_DEFERRED_FILE)走父进程继承链(bridge -> codex -> MCP child)，不在这里 hardcode。
_CODEX_MCP_ENV_UTF8_CONFIG_ARG = _codex_config_arg("mcp_servers.talk_send.env.PYTHONUTF8", "1")
_CODEX_MCP_ENV_IOENC_CONFIG_ARG = _codex_config_arg("mcp_servers.talk_send.env.PYTHONIOENCODING", "utf-8")

# Codex 非交互(exec)模式下，MCP tool call 默认会进 approval 闸门并被 deny("user cancelled")。
# 我们的 MCP catalog 只暴露 talk_send 一个工具，工具行为完全受控，bridge 在此显式放行 MCP 调用。
# TODO: 等 codex 提供更精细的 per-tool approval policy 后，改为只放行 talk_send，而非全 bypass。
# 目前已知最稳妥的兜底是 --dangerously-bypass-approvals-and-sandbox。
# 注意:这个 flag 同时绕过 sandbox，所以 discussion 档保留 --sandbox read-only 兼具风险面控制；
# 实测两者可以同时存在，sandbox 仍受 --sandbox 控制，只是 approval 闸门被关掉。
_CODEX_APPROVAL_BYPASS_FLAG = "--dangerously-bypass-approvals-and-sandbox"

# 讨论档默认命令：只读 sandbox + talk_send MCP server，不启用文件编辑/执行
DEFAULT_CODEX_COMMAND_DISCUSSION = (
    f"codex exec --skip-git-repo-check --ignore-rules --sandbox read-only --color never "
    f"{_CODEX_APPROVAL_BYPASS_FLAG} "
    f"-c {_CODEX_SYSTEM_CONFIG_ARG} "
    f"-c {_CODEX_MCP_COMMAND_CONFIG_ARG} "
    f"-c {_CODEX_MCP_ARGS_CONFIG_ARG} "
    f"-c {_CODEX_MCP_ENV_UTF8_CONFIG_ARG} "
    f"-c {_CODEX_MCP_ENV_IOENC_CONFIG_ARG} "
    f"-"
)

# 施工档默认命令：读写 sandbox + talk_send MCP server，用于需要动代码的任务
DEFAULT_CODEX_COMMAND_TOOLS = (
    f"codex exec --skip-git-repo-check --ignore-rules --sandbox workspace-write --color never "
    f"{_CODEX_APPROVAL_BYPASS_FLAG} "
    f"-c {_CODEX_SYSTEM_CONFIG_ARG} "
    f"-c {_CODEX_MCP_COMMAND_CONFIG_ARG} "
    f"-c {_CODEX_MCP_ARGS_CONFIG_ARG} "
    f"-c {_CODEX_MCP_ENV_UTF8_CONFIG_ARG} "
    f"-c {_CODEX_MCP_ENV_IOENC_CONFIG_ARG} "
    f"-"
)

DEFAULT_CODEX_COMMAND = DEFAULT_CODEX_COMMAND_DISCUSSION
DEFAULT_TIMEOUT_SEC = cli_bridge.DEFAULT_TIMEOUT_SEC
DEFAULT_MAX_REPLY_CHARS = cli_bridge.DEFAULT_MAX_REPLY_CHARS
DEFAULT_TASK_POLL_INTERVAL = cli_bridge.DEFAULT_TASK_POLL_INTERVAL

CodexRunResult = cli_bridge.CliRunResult
member_id_from_name = cli_bridge.member_id_from_name
parse_command = cli_bridge.parse_command
strip_leading_mentions = cli_bridge.strip_leading_mentions
should_handle_message = cli_bridge.should_handle_message


def _default_codex_exe() -> str:
    windows_codex = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    if windows_codex.exists():
        return windows_codex.as_posix()
    return "codex"


def _build_codex_command(
    codex_exe: str,
    *,
    profile: str = "discussion",
    system_instructions: str = CODEX_SYSTEM_INSTRUCTIONS,
) -> str:
    """Build the codex exec command for a given system instructions + profile.

    The system layer for codex is the ``base_instructions`` config value
    (PROJECT_INTEGRATION §5.4); Phase 2 profile injection works by passing an
    enhanced ``system_instructions`` here. ``_codex_config_arg`` already wraps
    values with ``shlex.quote`` over a JSON encoding, so arbitrary profile
    content (quotes/newlines) round-trips through ``shlex.split`` safely.
    """
    sandbox = "workspace-write" if profile == "tools" else "read-only"
    return (
        f"{codex_exe} exec --skip-git-repo-check --ignore-rules --sandbox {sandbox} --color never "
        f"{_CODEX_APPROVAL_BYPASS_FLAG} "
        f"-c {_codex_config_arg('base_instructions', system_instructions)} "
        f"-c {_CODEX_MCP_COMMAND_CONFIG_ARG} "
        f"-c {_CODEX_MCP_ARGS_CONFIG_ARG} "
        f"-c {_CODEX_MCP_ENV_UTF8_CONFIG_ARG} "
        f"-c {_CODEX_MCP_ENV_IOENC_CONFIG_ARG} "
        f"-"
    )


def default_codex_command(profile: str = "discussion") -> str:
    if os.environ.get("TALK_CODEX_COMMAND"):
        return os.environ["TALK_CODEX_COMMAND"]
    return _build_codex_command(_default_codex_exe(), profile=profile)


def resolve_codex_command(args: argparse.Namespace) -> str:
    """Resolve the codex command, applying execution profile + opt-in injection.

    - ``TALK_CODEX_COMMAND`` env or a custom ``--codex-command`` is respected
      as-is; whoever overrides owns the system instructions.
    - With ``--project`` set and a non-empty ``.talk/`` profile for this member,
      the IDENTITY/SOUL/USER profile is composed into ``base_instructions``
      (approach B, system layer).
    - Without ``--project`` (or with an empty profile) the result is
      byte-identical to today — strictly opt-in, zero regression.
    """
    if os.environ.get("TALK_CODEX_COMMAND"):
        return args.codex_command
    resolved_default = _build_codex_command(_default_codex_exe(), profile="discussion")
    if args.codex_command not in (resolved_default, DEFAULT_CODEX_COMMAND_DISCUSSION):
        return args.codex_command
    system_instructions = CODEX_SYSTEM_INSTRUCTIONS
    if getattr(args, "project", None):
        member_id = cli_bridge.member_id_from_name(args.name)
        profile = load_profile(args.project, member_id)
        system_instructions = compose_system_prompt(CODEX_SYSTEM_INSTRUCTIONS, profile)
    return _build_codex_command(
        _default_codex_exe(),
        profile=args.codex_execution_profile,
        system_instructions=system_instructions,
    )


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
            last_error = "\n".join(
                part for part in (cli_bridge.clean_cli_output(result.stderr), cli_bridge.clean_cli_output(result.stdout)) if part
            ) or reply
    except Exception as exc:
        reply = "Codex bridge 运行失败，错误详情已记录。"
        completion_status = "failed"
        last_error = f"Codex bridge failed before completing task {task_id}: {exc}"

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
    # resolve_codex_command applies the execution profile AND (opt-in) the
    # --project identity-layer injection in one place.
    args.codex_command = resolve_codex_command(args)
    args.command = args.codex_command
    args.runtime = "codex"
    args.bridge_label = "Codex bridge"
    # 把 TALK 连接信息注入环境变量，供 talk_send_mcp.py 使用
    # 每个 bridge 实例必须用自己的 key/url/id
    os.environ["TALK_API_KEY"] = args.key
    os.environ["TALK_BASE_URL"] = args.base_url
    os.environ["TALK_MEMBER_ID"] = cli_bridge.member_id_from_name(args.name)
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
    parser.add_argument(
        "--codex-execution-profile",
        choices=("discussion", "tools"),
        default="discussion",
        help="Codex runtime permission profile. 'discussion' uses read-only sandbox with talk_send MCP only; 'tools' enables workspace-write sandbox for code tasks.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == "__main__":
    main()
