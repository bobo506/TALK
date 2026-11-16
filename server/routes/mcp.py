"""Stateless streamable-HTTP MCP endpoint: ``POST /mcp``.

Accepts a single JSON-RPC 2.0 request per POST and serves the same tool set
and handlers as the stdio terminal entry (``bridges/talk_terminal_mcp.py``),
so URL-based clients (WorkBuddy MCP wizard, Codex ``--url``) can connect.
Authentication reuses ``server.auth.get_current_member``: trusted-mode
loopback without a key acts as ``human:operator``; key mode requires a valid
``X-API-Key`` header.  The endpoint is stateless: no GET/SSE, no session, one
request per response.

Hardening contract (independent review #798):

* JSON-RPC 2.0 is enforced: ``jsonrpc`` must be ``"2.0"``, requests without an
  ``id`` are notifications and get ``202`` with no body (any method), and a
  ``notifications/`` method that carries an ``id`` is processed like any other
  method instead of being swallowed into ``202``.
* Tool callbacks never trust the client-controlled ``Host`` header.  The
  self-call base URL is derived from the ASGI ``server`` scope (the local
  socket the request actually arrived on) or, as a fallback, from the
  server-side ``server.public_url`` configuration when it is loopback-only;
  non-loopback candidates are rejected, so a member key can never be sent to
  an attacker-chosen address.
* Tool-level failures (``tools/call`` results with ``isError``) return a
  static message — the original exception text (paths, key material,
  internals) is written to the server log only and never reaches the
  client; ``-32602`` / ``-32603`` stay static, and unexpected exceptions
  become a bare ``-32603``.  ``_sanitize`` is retained as a defensive
  second layer for any future client-bound dynamic text.
* Tool dispatch is scoped per request through a ``contextvars`` override
  (``bridges.talk_call_context``): the process environment is never mutated
  and no global lock is held, so concurrent members' ``tools/call`` requests
  (including long ``talk_wait_tasks`` waits) never block each other.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from bridges.talk_tool_registry import (
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    TalkToolError,
    call_tool,
    tool_names,
    tool_schemas,
)
import server.db as db
from server.auth import get_current_member
from server.models import Member

router = APIRouter(tags=["mcp"])
logger = logging.getLogger("talk")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

#: Local paths that must never reach a client in error text.  Since the K2.8
#: close-out no client-bound error text is dynamic (tool failures return a
#: static message; -32602/-32603 are static), so this sanitizer is a
#: defensive second layer only -- it is still kept complete and unit-tested.
#: file:// URIs are replaced whole *first* (file:///root/..., file://C:/...
#: with either separator, and file://server/share/...), so neither the
#: scheme prefix nor any path fragment can survive.  URI tails allow
#: spaces, covering the Terra #804 cases file:///root/Private
#: Folder/secret.txt and file://server/share/a b.txt: a tail that runs one
#: space too far only over-redacts prose, which is the safe failure mode
#: for a sanitizer (sentence punctuation and CR/LF still terminate the
#: match).
#: Windows drive paths match right after the drive separator (the
#: separator is mandatory, so URLs like http://host:8000/api are never
#: mangled); segments may contain spaces and mix backslash/forward-slash
#: separators.  UNC paths need at least server + share components.
#: POSIX paths match any absolute multi-segment path; interior segments
#: may contain spaces but the final segment may not, so trailing prose
#: survives ("Failed at /root/secret.txt with explanation" keeps "with
#: explanation"); lookbehinds keep URL authorities (http://...) and any
#: surviving scheme URIs untouched.
_FILE_URI_DRIVE_TAIL = r"[^?#\"'<>|,;!()\[\]{}\r\n]"
_FILE_URI_PATH_TAIL = r"[^\\/?#\"'<>|,;!()\[\]{}\r\n]"
_FILE_URI_RE = re.compile(
    r"(?i)file://(?:"
    r"[A-Za-z]:[\\/]" + _FILE_URI_DRIVE_TAIL + r"*"  # file://C:/... (mixed seps)
    r"|/" + _FILE_URI_PATH_TAIL + r"+(?:/" + _FILE_URI_PATH_TAIL + r"+)*"  # file:///root/...
    r"|" + _FILE_URI_PATH_TAIL + r"+(?:[\\/]+" + _FILE_URI_PATH_TAIL + r"+)+"  # file://server/share
    r")"
)
_WINDOWS_DRIVE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?:[^\\/:*?\"<>|\r\n]+[\\/])*[^\\/:*?\"<>|\r\n]*"
)
_WINDOWS_UNC_PATH_RE = re.compile(
    r"(?<!:)\\\\[^\\/:*?\"<>|\r\n]+(?:[\\/]+[^\\/:*?\"<>|\r\n]+)+"
)
_POSIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_:/])/(?:[^/\s](?:[^/\r\n]*[^/\s])?/)+[^/\s]+"
)
_IPV6_RE = re.compile(r"^[0-9a-fA-F:]+$")

#: Static text every tool-level failure returns to the client.  The
#: original exception (type, message, stack summary) is logged server-side
#: only, so no path, key material or internals can leak through error text.
TOOL_FAILURE_TEXT = "工具执行失败（错误详情已记录到服务端日志）"


def _rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _respond(payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(payload, status_code=200)


def _sanitize(text: Any, *, secret: str | None = None) -> str:
    """Redact key material and local filesystem paths from ``text``.

    Defensive second layer: since the K2.8 close-out no client-bound error
    text is dynamic -- tool-level failures return the static
    ``TOOL_FAILURE_TEXT``, ``-32602`` / ``-32603`` messages are static, and
    unexpected exceptions become a bare ``-32603`` -- so nothing sanitized
    here is currently shipped to clients.  Kept, and covered by unit tests,
    so any future path that returns dynamic text inherits the redaction
    instead of starting from zero; the full original text remains available
    server-side in the logs.
    """
    redacted = "" if text is None else str(text)
    if secret:
        redacted = redacted.replace(secret, "***")
    redacted = _FILE_URI_RE.sub("<path>", redacted)
    redacted = _WINDOWS_DRIVE_PATH_RE.sub("<path>", redacted)
    redacted = _WINDOWS_UNC_PATH_RE.sub("<path>", redacted)
    redacted = _POSIX_PATH_RE.sub("<path>", redacted)
    return redacted


def _host_is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if host.lower() != "localhost":
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return False
    return all(ipaddress.ip_address(address).is_loopback for address in addresses)


def _format_host(host: str) -> str:
    """Bracket IPv6 literals so they can sit inside an http URL authority."""
    if _IPV6_RE.match(host) and ":" in host:
        return f"[{host}]"
    return host


def _normalize_host(host: str) -> str:
    """Map an unspecified bind address (0.0.0.0 / ::) to real loopback."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.lower()
    if address.is_unspecified:
        return "127.0.0.1" if address.version == 4 else "::1"
    return str(address)


def _configured_loopback_base_url() -> str | None:
    """Server-side ``server.public_url`` when it is an explicit loopback URL."""
    try:
        server_cfg = db.CONFIG.get("server") or {}
        raw = str(server_cfg.get("public_url") or "").strip()
        if not raw:
            return None
        url = urlsplit(raw)
    except (ValueError, AttributeError):
        return None
    if url.scheme != "http" or not url.hostname or url.port is None:
        return None
    if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        return None
    if not _host_is_loopback(url.hostname):
        return None
    try:
        version = ipaddress.ip_address(url.hostname).version
    except ValueError:
        version = 4  # "localhost" and friends: render without brackets
    host = "127.0.0.1" if version == 4 else f"[{url.hostname}]"
    return f"http://{host}:{url.port}"


def _self_base_url(request: Request) -> str | None:
    """Loopback-only base URL this server can call back on, or ``None``.

    The client-controlled ``Host`` header is never consulted.  Primary source
    is the ASGI ``server`` scope (the local address of the socket this request
    arrived on, so it always matches this very process's listener); when that
    is missing or not loopback, fall back to a configured loopback
    ``server.public_url``.  Any other candidate is rejected so the member key
    is never posted to a non-loopback address.
    """
    server = request.scope.get("server")
    if isinstance(server, (list, tuple)) and len(server) == 2:
        host = str(server[0] or "")
        try:
            port = int(server[1])
        except (TypeError, ValueError):
            port = 0
        if host and port > 0:
            normalized = _normalize_host(host)
            if _host_is_loopback(normalized):
                return f"http://{_format_host(normalized)}:{port}"
    return _configured_loopback_base_url()


@router.get("/mcp")
def mcp_get_not_supported() -> Response:
    """GET/SSE are intentionally not part of this stateless slice."""
    return JSONResponse(
        {"detail": "GET not supported; POST a single JSON-RPC 2.0 request to /mcp"},
        status_code=405,
    )


@router.post("/mcp")
async def talk_mcp_endpoint(
    request: Request,
    member: Member = Depends(get_current_member),
) -> Response:
    """Single JSON-RPC 2.0 request: ``initialize`` / ``tools/list`` / ``tools/call``."""
    raw = await request.body()
    try:
        message: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _respond(_rpc_error(None, PARSE_ERROR, "Parse error"))

    if not isinstance(message, dict):
        return _respond(
            _rpc_error(None, INVALID_PARAMS, "invalid request: expected a single JSON-RPC object")
        )

    request_id = message.get("id") if "id" in message else None

    if message.get("jsonrpc") != "2.0":
        return _respond(_rpc_error(request_id, INVALID_REQUEST, "jsonrpc must be '2.0'"))

    method = message.get("method")
    if not isinstance(method, str) or not method:
        return _respond(_rpc_error(request_id, INVALID_REQUEST, "method must be a non-empty string"))

    if "id" not in message:
        # JSON-RPC notifications (any method without an id) expect no response.
        # This also covers "notifications/*" sent without an id by MCP clients.
        return Response(status_code=202)

    params = message.get("params")
    if params is not None and not isinstance(params, dict):
        # Uniform for every method (initialize/ping/tools/list/call alike):
        # params must be an object or absent; arrays/scalars are -32602.
        return _respond(_rpc_error(request_id, INVALID_PARAMS, "params must be an object"))

    if method == "initialize":
        return _respond(
            _rpc_result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {}},
                },
            )
        )
    if method == "ping":
        return _respond(_rpc_result(request_id, {}))
    if method == "tools/list":
        return _respond(_rpc_result(request_id, {"tools": tool_schemas()}))
    if method == "tools/call":
        if not isinstance(params, dict):
            return _respond(_rpc_error(request_id, INVALID_PARAMS, "params must be an object"))
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _respond(
                _rpc_error(request_id, INVALID_PARAMS, "params.name must be a non-empty string")
            )
        if "arguments" in params and params["arguments"] is not None:
            arguments = params["arguments"]
            if not isinstance(arguments, dict):
                return _respond(_rpc_error(request_id, INVALID_PARAMS, "arguments must be an object"))
        else:
            arguments = {}
        if name not in tool_names():
            return _respond(_rpc_error(request_id, METHOD_NOT_FOUND, f"未知工具: {name}"))
        # Never trust the request Host header: derive a loopback-only callback
        # address from server-side facts, and refuse to send the member's key
        # anywhere else.
        base_url = _self_base_url(request)
        if base_url is None:
            logger.error("mcp tools/call rejected: server has no loopback callback address")
            return _respond(
                _rpc_error(
                    request_id,
                    INTERNAL_ERROR,
                    "server has no loopback callback address; refusing to forward the member key",
                )
            )
        try:
            result = await run_in_threadpool(
                call_tool, name, arguments, base_url=base_url, api_key=member.api_key
            )
        except (TypeError, ValueError, KeyError):
            # Argument shape/coercion failures are invalid params, not tool
            # results; the exception text (paths, internals) stays server-side.
            logger.warning("mcp tools/call invalid arguments", extra={"tool": name})
            return _respond(
                _rpc_error(request_id, INVALID_PARAMS, f"invalid arguments for tool: {name}")
            )
        except TalkToolError:
            # Tool-level failure: log the full exception (type, message, stack
            # summary) server-side; the client only ever receives the static
            # TOOL_FAILURE_TEXT, so no path, key material or internals can
            # leak -- the same guarantee the static -32602/-32603 messages
            # give.
            logger.exception("mcp tools/call failed", extra={"tool": name})
            return _respond(
                _rpc_result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": TOOL_FAILURE_TEXT}],
                        "isError": True,
                    },
                )
            )
        except Exception:
            logger.exception("mcp tools/call crashed", extra={"tool": name})
            return _respond(_rpc_error(request_id, INTERNAL_ERROR, "internal error"))
        return _respond(
            _rpc_result(
                request_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                    ],
                    "isError": False,
                },
            )
        )
    return _respond(_rpc_error(request_id, METHOD_NOT_FOUND, f"未知方法: {method}"))
