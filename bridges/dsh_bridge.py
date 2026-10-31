"""351-E：DSH 入口包装层（与 Kimi/Codex 同构）。

DSH 之前直接用通用 ``bridges.cli_bridge`` 启动，没有地方挂"每任务前"的钩子。
本模块只做一层薄包装：解析同样的参数 → 注册逐任务强度钩子 → 交给通用桥接执行。
其余行为（命令模板、超时、任务协议）保持不变。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridges import cli_bridge  # noqa: E402


def _diagnostic(event: str) -> None:
    try:
        print("[DSH bridge] " + event, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


def native_home() -> Path | None:
    """宿主导入的原生 HOME 环境变量指向该角色目录。"""
    for name in ("HOME", "USERPROFILE"):
        value = os.environ.get(name)
        if isinstance(value, str) and value.strip():
            path = Path(value)
            if path.is_dir():
                return path
    return None


async def _binding_for(client: Any, project: str, member_id: str):
    try:
        rows = await client._request_json(
            "GET", "/api/projects/" + quote(project, safe="") + "/agents"
        )
    except Exception:
        _diagnostic("dsh_effort_lookup_failed")
        return None
    if isinstance(rows, dict):
        rows = rows.get("data")
    if not isinstance(rows, list):
        return None
    matches = [row for row in rows if isinstance(row, dict) and row.get("member_id") == member_id]
    return matches[0].get("binding") if len(matches) == 1 else None


def make_effort_hook(client: Any, args: argparse.Namespace):
    """每个任务执行前把已开放的强度写进角色 patch（当前只开放 max）。"""
    from bridges.dsh_effort import apply_patch_effort, find_patch, resolve_open_effort

    async def apply_effort(task: Any) -> None:
        del task
        project = str(
            getattr(args, "project_id", None) or os.environ.get("TALK_PROJECT_ID") or ""
        ).strip()
        home = native_home()
        if not project or home is None:
            return
        patch = find_patch(home)
        if patch is None:
            return
        binding = await _binding_for(client, project, cli_bridge.member_id_from_name(args.name))
        target = resolve_open_effort(binding)
        if target is None:
            if isinstance(binding, dict) and binding.get("effort_override"):
                _diagnostic("dsh_effort_capability_unknown")
            return
        try:
            apply_patch_effort(patch, target)
        except Exception:
            _diagnostic("dsh_effort_apply_failed")

    return apply_effort


async def run_bridge(args: argparse.Namespace) -> None:
    args.before_task_factory = make_effort_hook
    await cli_bridge.run_bridge(args)


def build_parser() -> argparse.ArgumentParser:
    # 与通用入口完全相同的参数契约（只换模块名），避免宿主 argv 变化。
    return cli_bridge.build_parser(
        description="TALK DSH bridge (per-task reasoning effort into the role patch)",
        default_command=cli_bridge.DEFAULT_COMMAND,
    )


def main() -> None:
    asyncio_run(run_bridge(build_parser().parse_args()))


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":
    main()
