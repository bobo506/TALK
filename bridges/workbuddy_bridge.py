"""WorkBuddy所带官方引擎的独立CLI入口；保留桌面应用和原模型目录。

351-F：WorkBuddy 的模型配置（``models.json``）逐模型带 ``reasoning.defaultEffort`` 与
``reasoning.supportedEfforts``，CLI 接受 ``--effort``；因此可以像 Codex 一样按角色逐任务传参，
不改用户全局 ``models.json``。
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote
from bridges import cli_bridge


def build_command(executable: Path, model: str, *, tools: str, effort: str | None = None) -> list[str]:
    entry = executable.parent / "resources/app.asar/cli/bin/codebuddy"
    command = [str(executable), str(entry), "--model", model]
    if effort:
        command += ["--effort", effort]
    command += ["--permission-mode", "default", "--tools", tools,
                "--mcp-config", json.dumps({"mcpServers": {}}, separators=(",", ":")),
                "--strict-mcp-config", "--setting-sources", "", "-p"]
    return command


def read_model_reasoning(models_home: Path, model_alias: str) -> dict | None:
    """只读模型条目里的公开能力字段（不返回原始配置或凭据）。"""
    try:
        data = json.loads((Path(models_home) / "models.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = data if isinstance(data, list) else (data.get("models") if isinstance(data, dict) else None)
    if not isinstance(rows, list):
        return None
    found = [row for row in rows if isinstance(row, dict)
             and "custom-local:" + str(row.get("id")) == model_alias]
    if len(found) != 1:
        return None
    reasoning = found[0].get("reasoning")
    supported = reasoning.get("supportedEfforts") if isinstance(reasoning, dict) else None
    default = reasoning.get("defaultEffort") if isinstance(reasoning, dict) else None
    return {
        "supports_reasoning": bool(found[0].get("supportsReasoning")),
        "default": default if isinstance(default, str) else None,
        "supported": [item for item in supported if isinstance(item, str)] if isinstance(supported, list) else None,
    }


def _diagnostic(event: str) -> None:
    try:
        print("[WorkBuddy bridge] " + event, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


async def _binding_for(client: Any, project: str, member_id: str):
    try:
        rows = await client._request_json(
            "GET", "/api/projects/" + quote(project, safe="") + "/agents"
        )
    except Exception:
        _diagnostic("workbuddy_effort_lookup_failed")
        return None
    if isinstance(rows, dict):
        rows = rows.get("data")
    if not isinstance(rows, list):
        return None
    matches = [row for row in rows if isinstance(row, dict) and row.get("member_id") == member_id]
    return matches[0].get("binding") if len(matches) == 1 else None


def set_command_effort(command: Any, effort: str) -> tuple[Any, str]:
    """把强度写入命令：已有 ``--effort`` 就替换，没有则插到 ``--model <alias>`` 之后。"""
    from bridges.codex_effort import apply_effort

    rewritten, mode = apply_effort(command, effort)
    if mode != "unchanged":
        return rewritten, mode
    if isinstance(command, list) and "--model" in command:
        index = command.index("--model") + 2
        return command[:index] + ["--effort", effort] + command[index:], "inserted"
    return command, "unchanged"


def make_effort_hook(client: Any, args: argparse.Namespace):
    """每个任务前按公开绑定改写 ``--effort``；值必须在该模型官方清单内。"""
    from bridges.codex_effort import apply_effort
    from bridges.kimi_effort import resolve_target_effort

    async def apply_effort_hook(task: Any) -> None:
        del task
        project = str(
            getattr(args, "project_id", None) or os.environ.get("TALK_PROJECT_ID") or ""
        ).strip()
        if not project:
            return
        binding = await _binding_for(client, project, cli_bridge.member_id_from_name(args.name))
        target = resolve_target_effort(binding)
        if target is None:
            if isinstance(binding, dict) and binding.get("effort_override"):
                _diagnostic("workbuddy_effort_capability_unknown")
            return
        command = getattr(args, "task_command", None) or getattr(args, "command", None)
        if command is None:
            return
        rewritten, mode = set_command_effort(command, target)
        if mode == "unchanged":
            _diagnostic("workbuddy_effort_command_unrecognized")
            return
        args.task_command = rewritten

    return apply_effort_hook


def prepare_environment(args: argparse.Namespace) -> None:
    models_home = Path(args.workbuddy_models_home or "").expanduser().resolve()
    if not args.workbuddy_models_home or not (models_home / "models.json").is_file():
        raise ValueError("workbuddy_models_home_required")
    native_home = Path(args.workbuddy_native_home or (Path.home() / ".codebuddy")).expanduser().resolve()
    if native_home == models_home:
        raise ValueError("workbuddy_native_home_must_be_separate")
    native_home.mkdir(parents=True, exist_ok=True)
    os.environ.update(CODEBUDDY_CONFIG_DIR=str(native_home), WORKBUDDY_CONFIG_DIR=str(models_home),
        ELECTRON_RUN_AS_NODE="1", CODEBUDDY_FORCE_LITE_WB_BUNDLE="1", DISABLE_AUTOUPDATER="1",
        CODEBUDDY_REMOTE_CONFIG_DISABLED="1", CODEBUDDY_CODE_DISABLE_BACKGROUND_TASKS="1")
    args.workbuddy_models_home_resolved = models_home


async def run_bridge(args: argparse.Namespace) -> None:
    prepare_environment(args)
    executable = Path(args.workbuddy_executable).resolve()
    if not executable.is_file():
        raise ValueError("workbuddy_executable_missing")
    if not args.workbuddy_model or not args.workbuddy_model.startswith("custom-local:"):
        raise ValueError("workbuddy_explicit_model_required")
    reasoning = read_model_reasoning(args.workbuddy_models_home_resolved, args.workbuddy_model) or {}
    supported = reasoning.get("supported")
    startup = reasoning.get("default")
    if supported and startup not in supported:
        startup = None
    args.command = build_command(executable, args.workbuddy_model, tools="", effort=startup)
    args.task_command = build_command(executable, args.workbuddy_model, tools="default", effort=startup)
    args.task_preflight_command = build_command(executable, args.workbuddy_model, tools="", effort=startup)
    args.runtime = "workbuddy"
    args.prompt_transport = "stdin"
    args.before_task_factory = make_effort_hook
    await cli_bridge.run_bridge(args)


def build_parser():
    parser = cli_bridge.build_parser(description="TALK WorkBuddy embedded CLI bridge (not desktop automation)",
        default_name="workbuddy", default_runtime="workbuddy", default_command="workbuddy-runtime",
        default_prompt_transport="stdin", default_bridge_label="WorkBuddy embedded CLI")
    parser.add_argument("--workbuddy-model", required=True)
    parser.add_argument("--workbuddy-models-home", default=os.environ.get("TALK_WORKBUDDY_MODELS_HOME"))
    parser.add_argument("--workbuddy-native-home", default=os.environ.get("TALK_WORKBUDDY_NATIVE_HOME"))
    parser.add_argument("--workbuddy-executable", default=str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/WorkBuddy/WorkBuddy.exe"))
    return parser


def main():
    asyncio.run(run_bridge(build_parser().parse_args()))


if __name__ == "__main__":
    main()
