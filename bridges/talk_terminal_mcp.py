#!/usr/bin/env python3
"""普通终端的 TALK Task Hall MCP 入口；不依赖 bridge 消息上下文。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from bridges import talk_send_mcp
from bridges.talk_task_tools import TalkToolError, _api_request, list_agents
from cli.talk import load_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="在普通终端接入 TALK 任务工具")
    parser.add_argument("--project-root", type=Path, help="包含 .talk/project.yaml 的项目目录")
    parser.add_argument("--project", help="默认 project_id；覆盖环境变量及项目文件")
    parser.add_argument("--server", help="TALK 服务地址；覆盖环境变量及项目文件")
    parser.add_argument("--check", action="store_true", help="只读检查身份、项目及可用角色，然后退出")
    return parser


def configure(args: argparse.Namespace) -> tuple[str, str]:
    root = (args.project_root or Path.cwd()).resolve()
    project = {}
    if args.project_root is not None or (root / ".talk" / "project.yaml").exists():
        try:
            project = load_project(root)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise TalkToolError("无法读取 .talk/project.yaml，请检查 --project-root 和文件格式") from exc
        if not isinstance(project, dict):
            raise TalkToolError(".talk/project.yaml 必须是 YAML 对象")

    server = args.server or os.environ.get("TALK_BASE_URL") or project.get("talk_server") or "http://127.0.0.1:8000"
    project_id = args.project or os.environ.get("TALK_PROJECT_ID") or project.get("project_id")
    if not isinstance(server, str) or not server.strip():
        raise TalkToolError("TALK 服务地址必须是非空字符串")
    server = server.strip().rstrip("/")
    try:
        url = urlsplit(server)
        valid_url = url.scheme in {"http", "https"} and url.hostname and url.port != 0
        valid_url = valid_url and not (url.username or url.password or url.query or url.fragment)
    except ValueError:
        valid_url = False
    if not valid_url:
        raise TalkToolError("服务地址必须是 HTTP(S) URL，且不能包含用户名、密码、查询参数或片段")
    if not isinstance(project_id, str) or not project_id.strip():
        raise TalkToolError("缺少 project_id：请指定 --project、TALK_PROJECT_ID 或有效项目目录")
    api_key = os.environ.get("TALK_API_KEY", "").strip()
    if not api_key:
        raise TalkToolError("TALK_API_KEY 未设置；请通过终端或 MCP 客户端的环境变量提供现有成员密钥")

    project_id = project_id.strip()
    os.environ.update(TALK_BASE_URL=server, TALK_PROJECT_ID=project_id, TALK_API_KEY=api_key)
    # 独立终端以 API Key 的真实身份为准，避免继承另一个 bridge 的成员提示。
    os.environ.pop("TALK_MEMBER_ID", None)
    return server, project_id


def check_connection(server: str, project_id: str) -> dict:
    me = _api_request("GET", "/api/members/me")
    discovered = list_agents(project_id=project_id)
    return {
        "ok": True,
        "server": server,
        "project_id": project_id,
        "member_id": me["id"],
        "display_name": me.get("display_name"),
        "agents": [
            {key: agent.get(key) for key in ("member_id", "display_name", "availability")}
            for agent in discovered["agents"]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        server, project_id = configure(args)
        if args.check:
            print(json.dumps(check_connection(server, project_id), ensure_ascii=False))
        else:
            # 普通终端仅开放八个 HTTP 任务工具，不暴露依赖 bridge 回收的延迟发送。
            talk_send_mcp.main(include_deferred_send=False)
    except (TalkToolError, OSError, ValueError) as exc:
        message = str(exc)
        api_key = os.environ.get("TALK_API_KEY", "").strip()
        if api_key:
            message = message.replace(api_key, "[已隐藏]")
        print(f"TALK 终端接入失败：{message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
