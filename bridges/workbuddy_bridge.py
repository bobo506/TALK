"""WorkBuddy所带官方引擎的独立CLI入口；保留桌面应用和原模型目录。"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
from bridges import cli_bridge


def build_command(executable: Path, model: str, *, tools: str) -> list[str]:
    entry = executable.parent / "resources/app.asar/cli/bin/codebuddy"
    return [str(executable), str(entry), "--model", model, "--permission-mode", "default", "--tools", tools,
            "--mcp-config", json.dumps({"mcpServers": {}}, separators=(",", ":")),
            "--strict-mcp-config", "--setting-sources", "", "-p"]


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


async def run_bridge(args: argparse.Namespace) -> None:
    prepare_environment(args)
    executable = Path(args.workbuddy_executable).resolve()
    if not executable.is_file():
        raise ValueError("workbuddy_executable_missing")
    if not args.workbuddy_model or not args.workbuddy_model.startswith("custom-local:"):
        raise ValueError("workbuddy_explicit_model_required")
    args.command = build_command(executable, args.workbuddy_model, tools="")
    args.task_command = build_command(executable, args.workbuddy_model, tools="default")
    args.task_preflight_command = build_command(executable, args.workbuddy_model, tools="")
    args.runtime = "workbuddy"
    args.prompt_transport = "stdin"
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
