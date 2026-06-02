#!/usr/bin/env python3
"""
TALK talk_send MCP server — Codex bridge 专用（方案 D function-calling）

最小 stdio MCP server，暴露 talk_send 工具，行为与 talk_tools_extension.ts 完全镜像：
- 从 os.environ 读 TALK_DEFERRED_FILE / TALK_GROUP_ID / TALK_API_KEY
- 把 {tool: "talk_send", target, body, stance, group_id} 追加到 JSONL
- 返回"talk_send 已登记"

协议：MCP (Model Context Protocol) JSON-RPC 2.0 over stdin/stdout。
MCP 子进程从 Codex 父进程继承环境变量，bridge 每次 handle_incoming_message
更新的 TALK_DEFERRED_FILE / TALK_GROUP_ID 自然带进去。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

SERVER_NAME = "talk_send_mcp"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _write_json(data: dict[str, Any]) -> None:
    """写一行 JSON 到 stdout。"""
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _write_response(id_: Any, result: Any) -> None:
    _write_json({"jsonrpc": "2.0", "id": id_, "result": result})


def _write_error(id_: Any, code: int, message: str) -> None:
    _write_json({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})


# ---------------------------------------------------------------------------
# talk_send 核心
# ---------------------------------------------------------------------------


def _talk_send(target: str, body: str, stance: str = "greeting") -> dict[str, Any]:
    """写 JSONL 记录到 TALK_DEFERRED_FILE。"""
    api_key = os.environ.get("TALK_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "TALK_API_KEY 未设置"}

    deferred_file = os.environ.get("TALK_DEFERRED_FILE")
    if not deferred_file:
        return {"ok": False, "error": "talk_send 暂不可用（当前消息不需要向其他成员发送）"}

    group_id = os.environ.get("TALK_GROUP_ID") or None
    record = json.dumps({
        "tool": "talk_send",
        "target": target.strip(),
        "body": body.strip(),
        "stance": stance.strip() or "greeting",
        "group_id": group_id,
    }, ensure_ascii=False)

    try:
        with open(deferred_file, "a", encoding="utf-8") as f:
            f.write(record + "\n")
        return {
            "ok": True,
            "deferred": True,
            "target": target,
            "message": f"talk_send 已登记：将向 {target} 发送消息（本轮结束后执行）。",
        }
    except OSError as exc:
        return {"ok": False, "error": f"talk_send 登记失败：{exc}"}


# ---------------------------------------------------------------------------
# MCP 工具定义
# ---------------------------------------------------------------------------

_TOOL_SCHEMA = {
    "name": "talk_send",
    "description": (
        "向当前群内的指定成员发送消息。当你需要联系、转告、询问或通知另一成员时使用。"
        "发送后你会收到确认。target 必须是群成员清单中列出的成员。"
        "当 human 明确要求你联系、转告、询问、通知或打招呼给另一位群成员时，调用本工具。"
        "调用后在可见回复里简要告诉 human 已发送即可。"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "目标成员完整 member_id（如 agent:codex），必须是群成员清单中的成员",
            },
            "body": {
                "type": "string",
                "description": "消息正文，不要加 @ 前缀",
            },
            "stance": {
                "type": "string",
                "description": "消息立场（可选）。question=提问, answer=回答, agree=同意, disagree=反对, greeting=寒暄, closure=收尾。不填默认 greeting",
            },
        },
        "required": ["target", "body"],
    },
}

# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = request.get("method", "")
        req_id = request.get("id")
        params: dict[str, Any] = request.get("params", {})

        try:
            if method == "initialize":
                _write_response(req_id, {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {}},
                })
            elif method == "notifications/initialized":
                # MCP 初始化完成通知，无需响应
                pass
            elif method == "tools/list":
                _write_response(req_id, {"tools": [_TOOL_SCHEMA]})
            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args: dict[str, Any] = params.get("arguments", {})
                if tool_name == "talk_send":
                    target = str(tool_args.get("target", "")).strip()
                    body = str(tool_args.get("body", "")).strip()
                    stance = str(tool_args.get("stance", "greeting")).strip()
                    if not target or not body:
                        _write_response(req_id, {
                            "content": [{"type": "text", "text": "talk_send 失败：缺少 target 或 body 参数"}],
                            "isError": True,
                        })
                    else:
                        result = _talk_send(target, body, stance)
                        text = result.get("message") or result.get("error", "talk_send 完成")
                        is_error = not result.get("ok", False)
                        _write_response(req_id, {
                            "content": [{"type": "text", "text": text}],
                            "isError": is_error,
                        })
                else:
                    _write_error(req_id, -32601, f"未知工具: {tool_name}")
            else:
                _write_error(req_id, -32601, f"未知方法: {method}")
        except Exception as exc:
            _write_error(req_id or 0, -32603, str(exc))

            # 诊断记录
            try:
                from datetime import datetime
                dump_path = os.environ.get("TALK_DUMP_PROMPT_FILE", "logs/pi_prompt_dump.log")
                os.makedirs(os.path.dirname(dump_path) or ".", exist_ok=True)
                with open(dump_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": datetime.now().isoformat(),
                        "event": "talk_send_mcp_error",
                        "error": str(exc),
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass


if __name__ == "__main__":
    main()
