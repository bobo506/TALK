#!/usr/bin/env python3
"""Antigravity CLI (``agy``) bridge for TALK.

复用通用 ``cli_bridge`` 任务队列、心跳与结构化交付机制，提供：
- 3 个目标模型（Neon / Carbon / Hydrogen）与思考强度命令构建；
- 每次任务前按公开绑定动态刷新强度（Carbon 仅 3 档，Neon/Hydrogen 4 档），
  修改强度后下一次任务即刻生效，无需重启角色服务；
- 权限档区分（``tools`` 全工具施工档 / ``review`` 沙箱只读复核档）。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridges import cli_bridge
from bridges.antigravity_effort import (
    AntigravityEffortUnavailable,
    apply_effort,
    cli_model_id,
    default_effort_for_model,
    extract_command_models,
    parse_model_id,
    resolve_binding_effort,
)
from bridges.antigravity_execution_native import find_antigravity_executable

DEFAULT_ANTIGRAVITY_MODEL = "gemini-4-neon"
DEFAULT_ANTIGRAVITY_EFFORT = "high"
DEFAULT_ANTIGRAVITY_COMMAND = (
    "agy --mode auto --sandbox --disable-slash-commands "
    "--output-format stream-json --print-timeout 0 "
    f"--model {DEFAULT_ANTIGRAVITY_MODEL}-{DEFAULT_ANTIGRAVITY_EFFORT} "
    f"--effort {DEFAULT_ANTIGRAVITY_EFFORT} -p"
)


def build_antigravity_command(
    agy_exe: str | None = None,
    *,
    model: str = DEFAULT_ANTIGRAVITY_MODEL,
    effort: str | None = None,
    profile: str = "review",
) -> str:
    """构建无头 ``agy`` 命令（以 ``-p`` 结尾，供 ``cli_bridge`` 通过 ``argv`` 附加 prompt）。"""
    exe = agy_exe if agy_exe else (find_antigravity_executable() or "agy")
    parsed = parse_model_id(model)
    if parsed is None:
        raise AntigravityEffortUnavailable("antigravity_model_unsupported")
    base, embedded = parsed
    if effort is not None:
        resolved_effort = effort
    else:
        resolved_effort = embedded or default_effort_for_model(base) or DEFAULT_ANTIGRAVITY_EFFORT
    resolved_cli_model = cli_model_id(base, resolved_effort)
    resolved_effort = parse_model_id(resolved_cli_model)[1]  # type: ignore[index]

    tokens = [exe, "--mode", "auto"]
    if profile == "tools":
        tokens.append("--dangerously-skip-permissions")
    else:
        tokens.append("--sandbox")
    tokens.extend(
        [
            "--disable-slash-commands",
            "--output-format",
            "stream-json",
            "--print-timeout",
            "0",
            "--model",
            resolved_cli_model,
            "--effort",
            str(resolved_effort),
            "-p",
        ]
    )
    return " ".join(shlex.quote(token) for token in tokens)


def _effort_diagnostic(event: str) -> None:
    try:
        print("[Antigravity bridge] " + event, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


def _has_effort_override(binding: Any) -> bool:
    override = binding.get("effort_override") if isinstance(binding, dict) else None
    return isinstance(override, str) and bool(override.strip())


async def fetch_task_binding(client: Any, task: dict[str, Any], member_id: str) -> dict[str, Any] | None:
    """读取项目公开角色绑定（含 ``effective_effort`` / ``effort_options``）；失败或旧服务返回 None。"""
    project = str(task.get("project_id") or os.environ.get("TALK_PROJECT_ID") or "").strip()
    if not project:
        return None
    try:
        rows = await client._request_json(
            "GET", "/api/projects/" + quote(project, safe="") + "/agents"
        )
    except Exception:
        _effort_diagnostic("antigravity_effort_lookup_failed")
        return None
    if isinstance(rows, dict):
        rows = rows.get("data")
    if not isinstance(rows, list):
        return None
    matches = [row for row in rows if isinstance(row, dict) and row.get("member_id") == member_id]
    if len(matches) != 1:
        return None
    binding = matches[0].get("binding")
    if not isinstance(binding, dict) or "effective_effort" not in binding:
        return None
    return binding


def _resolve_target_model(args: argparse.Namespace, binding: dict[str, Any]) -> str | None:
    """结合显式 CLI 模型、命令现有 ``--model`` 与公开绑定确定唯一基础模型，冲突则 fail-closed。"""
    candidates: list[str] = []
    explicit = getattr(args, "antigravity_model", None)
    if isinstance(explicit, str) and explicit.strip():
        candidates.append(explicit.strip())
    for attr in ("task_command", "task_preflight_command"):
        command = getattr(args, attr, None)
        if command:
            candidates.extend(extract_command_models(command))
    binding_model = binding.get("model_id") or binding.get("model_alias")
    if isinstance(binding_model, str) and binding_model.strip():
        candidates.append(binding_model.strip())

    bases: set[str] = set()
    for raw in candidates:
        parsed = parse_model_id(raw)
        if parsed is None:
            raise AntigravityEffortUnavailable("antigravity_model_unsupported")
        bases.add(parsed[0])
    if len(bases) > 1:
        raise AntigravityEffortUnavailable("antigravity_model_mismatch")
    return next(iter(bases)) if bases else None


def _rewrite_effort_commands(args: argparse.Namespace, effort: str, *, base_model: str | None = None) -> None:
    """原子改写 ``task_command`` 与 ``task_preflight_command``；任一失败不留半改状态。"""
    staged: list[tuple[str, Any]] = []
    for attr in ("task_command", "task_preflight_command"):
        command = getattr(args, attr, None)
        if not command:
            continue
        updated, mode = apply_effort(command, effort, base_model=base_model)
        if mode == "unchanged":
            raise cli_bridge.TaskPreflightError("antigravity_effort_command_unrecognized")
        staged.append((attr, updated))
    if not staged:
        raise cli_bridge.TaskPreflightError("antigravity_effort_command_unrecognized")
    for attr, updated in staged:
        setattr(args, attr, updated)


def make_effort_hook(client: Any, args: argparse.Namespace):
    """每次任务前按公开绑定重算思考强度并同步改写 ``--model`` 与 ``--effort``。"""
    member_id = cli_bridge.member_id_from_name(getattr(args, "name", "antigravity"))

    async def refresh(task: dict[str, Any]) -> None:
        task_template = getattr(args, "task_command_template", None)
        preflight_template = getattr(args, "task_preflight_command_template", None)
        if task_template is not None:
            args.task_command = task_template
        if preflight_template is not None:
            args.task_preflight_command = preflight_template

        binding = await fetch_task_binding(client, task, member_id)
        if binding is None:
            return
        try:
            target_model = _resolve_target_model(args, binding)
            effort, _source = resolve_binding_effort(binding, None, model_id=target_model)
            _rewrite_effort_commands(args, effort, base_model=target_model)
        except AntigravityEffortUnavailable as exc:
            if _has_effort_override(binding):
                raise cli_bridge.TaskPreflightError(f"antigravity_effort_unavailable: {exc.reason}")
            _effort_diagnostic(exc.reason)
        except cli_bridge.TaskPreflightError:
            if _has_effort_override(binding):
                raise
            _effort_diagnostic("antigravity_effort_command_unrecognized")

    return refresh


def materialize_antigravity_commands(args: argparse.Namespace) -> tuple[str, str, str]:
    """根据 CLI 参数生成讨论/任务/预检三条受控命令。"""
    if getattr(args, "antigravity_command", DEFAULT_ANTIGRAVITY_COMMAND) != DEFAULT_ANTIGRAVITY_COMMAND:
        override = args.antigravity_command
        return override, override, getattr(args, "task_preflight_command", None) or override

    exe = getattr(args, "antigravity_executable", None) or find_antigravity_executable() or "agy"
    model = getattr(args, "antigravity_model", None) or DEFAULT_ANTIGRAVITY_MODEL
    effort = getattr(args, "antigravity_effort", None)
    task_profile = getattr(args, "antigravity_task_profile", "review")

    message_command = build_antigravity_command(exe, model=model, effort=effort, profile="review")
    task_command = build_antigravity_command(exe, model=model, effort=effort, profile=task_profile)
    preflight_command = getattr(args, "task_preflight_command", None) or build_antigravity_command(
        exe, model=model, effort=effort, profile="review"
    )
    return message_command, task_command, preflight_command


async def run_bridge(args: argparse.Namespace) -> None:
    message_command, task_command, preflight_command = materialize_antigravity_commands(args)
    args.antigravity_command = message_command
    args.command = message_command
    args.task_command = task_command
    args.task_preflight_command = preflight_command
    args.task_command_template = task_command
    args.task_preflight_command_template = preflight_command
    args.before_task_factory = make_effort_hook
    args.runtime = "antigravity"
    args.bridge_label = "Antigravity bridge"
    if getattr(args, "prompt_transport", None) not in cli_bridge.PROMPT_TRANSPORTS:
        args.prompt_transport = "argv"
    await cli_bridge.run_bridge(args)


def build_parser() -> argparse.ArgumentParser:
    parser = cli_bridge.build_parser(
        description="TALK Antigravity CLI bridge",
        default_name="antigravity",
        default_runtime="antigravity",
        default_command=DEFAULT_ANTIGRAVITY_COMMAND,
        default_prompt_transport="argv",
        command_help="Antigravity CLI command ending with -p / --print",
        command_option="--antigravity-command",
        command_dest="antigravity_command",
        command_metavar="ANTIGRAVITY_COMMAND",
        default_bridge_label="Antigravity bridge",
    )
    parser.add_argument(
        "--antigravity-executable",
        default=None,
        help="Path to agy executable (defaults to PATH or Windows default install path)",
    )
    parser.add_argument(
        "--antigravity-model",
        default=None,
        help="Base or full Antigravity model ID (gemini-4-neon / gemini-4-carbon / gemini-4-hydrogen)",
    )
    parser.add_argument(
        "--antigravity-effort",
        default=None,
        help="Initial reasoning effort (low / medium / high / xhigh; Carbon supports low/medium/high)",
    )
    parser.add_argument(
        "--antigravity-task-profile",
        choices=("review", "tools"),
        default="review",
        help="Permission profile for Task Hall runs: review (sandboxed) or tools (auto-approved)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(run_bridge(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
