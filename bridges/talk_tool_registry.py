"""HTTP-facing aggregation of the existing TALK MCP tool surface.

The stdio terminal entry (``bridges/talk_terminal_mcp.py``) exposes exactly the
Task Hall tool set from ``bridges.talk_task_tools.TOOL_SCHEMAS`` (no deferred
``talk_send``).  The streamable HTTP endpoint (``server/routes/mcp.py``) serves
the same set through this module: only existing schemas/handlers are reused —
no tool behavior changes.
"""

from __future__ import annotations

import contextlib
import copy
from typing import Any, Iterator

from bridges.talk_call_context import call_context
from bridges.talk_task_tools import TOOL_SCHEMAS, TalkToolError, dispatch_tool

__all__ = [
    "PROTOCOL_VERSION",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TalkToolError",
    "call_tool",
    "tool_environment",
    "tool_names",
    "tool_schemas",
]

# Same server identity the stdio MCP entry reports.
SERVER_NAME = "talk_tools_mcp"
SERVER_VERSION = "3.0.0"
# Oldest streamable-HTTP MCP protocol version clients (Codex --url, WorkBuddy)
# still speak; the endpoint is stateless so nothing newer is required.
PROTOCOL_VERSION = "2024-11-05"

#: Bridge variables scoped per request.  The HTTP endpoint must not write the
#: process environment (that would force a global lock around every tool
#: call), so the per-request values ride a contextvar instead and the tool
#: layer reads them through ``bridges.talk_call_context.env``.  The project /
#: member hints are explicitly cleared for the call so no stale bridge
#: context leaks in — identical to the previous env-based scoping.

def tool_schemas() -> list[dict[str, Any]]:
    """Deep copy of the exact tool list the stdio terminal entry serves."""
    return copy.deepcopy(TOOL_SCHEMAS)


def tool_names() -> set[str]:
    """Names of the tools the HTTP endpoint exposes (= stdio terminal entry)."""
    return {schema["name"] for schema in TOOL_SCHEMAS}


@contextlib.contextmanager
def tool_environment(base_url: str, api_key: str) -> Iterator[None]:
    """Point the existing bridge tools at ``base_url`` with ``api_key`` for the
    current execution context only, then drop the overrides.

    The scope is context-local (``contextvars``): no ``os.environ`` variable
    is written and no process-wide lock is taken, so any number of member
    requests — including long ``talk_wait_tasks`` calls — run concurrently
    with strict per-request isolation.  Identity is governed by the API key
    (the tools resolve it via ``GET /api/members/me``);
    ``TALK_MEMBER_ID`` / ``TALK_PROJECT_ID`` are cleared for the call so no
    stale bridge context leaks in.
    """
    with call_context(
        {
            "TALK_BASE_URL": base_url,
            "TALK_API_KEY": api_key,
            "TALK_PROJECT_ID": None,
            "TALK_MEMBER_ID": None,
        }
    ):
        yield


def call_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    base_url: str,
    api_key: str | None,
) -> dict[str, Any]:
    """Dispatch one tool through the shared stdio handler.

    Runs ``bridges.talk_task_tools.dispatch_tool`` unchanged inside a
    per-request context so the HTTP endpoint and the stdio entry share the
    same handler, identity source and permission checks.  A missing/empty
    member key is rejected before the context is installed, so no request
    can crash mid-setup or leave bridge variables behind.
    """
    key = (api_key or "").strip()
    if not key:
        raise TalkToolError("当前成员未配置 API Key，无法代理工具调用")
    with tool_environment(base_url, key):
        return dispatch_tool(name, arguments)
