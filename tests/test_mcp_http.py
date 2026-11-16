"""End-to-end tests for the streamable HTTP MCP endpoint (POST /mcp)."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import uvicorn

import server.db as db
import server.main as main
from bridges.talk_task_tools import TOOL_SCHEMAS
from server.auth import OPERATOR_ID, ensure_local_operator
from server.models import Member, Project, ProjectAgent
from tests.test_support import RouteTestCase


@contextmanager
def mcp_test_server(app):
    """Run the app on an ephemeral loopback port with lifespan side effects off."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    try:
        while time.time() < deadline:
            if server.started:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("test MCP server did not start in time")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


class McpHttpTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self._auth_patches = [
            patch.object(db, "AUTH_MODE", "trusted"),
            patch.object(db, "TRUSTED_NETWORKS", ("loopback", "private")),
        ]
        for item in self._auth_patches:
            item.start()
            self.addCleanup(item.stop)
        with self.session() as session:
            ensure_local_operator(session)
            session.add(
                Member(id="agent:demo", kind="agent", display_name="Demo", api_key="demo-key")
            )
            session.add(
                Project(
                    project_id="prj_mcp",
                    display_name="MCP Project",
                    maintainer_member_id=OPERATOR_ID,
                )
            )
            session.add(ProjectAgent(project_id="prj_mcp", member_id="agent:demo"))
            session.commit()
        self._managed_env = {
            name: os.environ.get(name)
            for name in ("TALK_BASE_URL", "TALK_API_KEY", "TALK_PROJECT_ID", "TALK_MEMBER_ID")
        }
        self.addCleanup(self._assert_env_restored)

    def _assert_env_restored(self):
        for name, value in self._managed_env.items():
            self.assertEqual(os.environ.get(name), value, f"{name} leaked into process env")

    def rpc(self, base_url, method, params=None, request_id=1, headers=None):
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        return httpx.post(
            base_url + "/mcp", json=payload, headers=headers or {}, timeout=30, trust_env=False
        )

    def call_tool(self, base_url, name, arguments=None, headers=None, request_id=7):
        response = self.rpc(
            base_url,
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            request_id=request_id,
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["jsonrpc"], "2.0")
        self.assertEqual(body["id"], request_id)
        return body

    def test_initialize_reports_stdio_server_identity(self):
        with mcp_test_server(main.app) as base_url:
            response = self.rpc(
                base_url,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "workbuddy", "version": "0.0.1"},
                },
            )
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertEqual(result["serverInfo"], {"name": "talk_tools_mcp", "version": "3.0.0"})
        self.assertEqual(result["capabilities"], {"tools": {}})

    def test_tools_list_matches_stdio_terminal_entry(self):
        with mcp_test_server(main.app) as base_url:
            response = self.rpc(base_url, "tools/list")
        self.assertEqual(response.status_code, 200)
        tools = response.json()["result"]["tools"]
        self.assertEqual(tools, TOOL_SCHEMAS)
        names = {tool["name"] for tool in tools}
        self.assertIn("talk_delegate_task", names)
        self.assertIn("talk_get_delivery", names)
        self.assertNotIn("talk_send", names)
        for tool in tools:
            self.assertEqual(set(tool), {"name", "description", "inputSchema"}, tool["name"])
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_trusted_loopback_without_key_calls_tools_as_operator(self):
        with mcp_test_server(main.app) as base_url:
            listed = self.call_tool(base_url, "talk_list_tasks")
            self.assertFalse(listed["result"]["isError"])
            payload = json.loads(listed["result"]["content"][0]["text"])
            self.assertEqual(payload["tasks"], [])

            agents = self.call_tool(
                base_url, "talk_list_agents", {"project_id": "prj_mcp"}, request_id=8
            )
            self.assertFalse(agents["result"]["isError"])
            payload = json.loads(agents["result"]["content"][0]["text"])
            self.assertEqual(payload["caller_identity"]["member_id"], OPERATOR_ID)
            self.assertEqual(payload["caller_identity"]["kind"], "human")
            self.assertEqual([agent["member_id"] for agent in payload["agents"]], ["agent:demo"])

    def test_api_key_identity_is_used_for_tool_dispatch(self):
        headers = {"X-API-Key": "demo-key"}
        with mcp_test_server(main.app) as base_url:
            agents = self.call_tool(
                base_url, "talk_list_agents", {"project_id": "prj_mcp"}, headers=headers
            )
        self.assertFalse(agents["result"]["isError"])
        payload = json.loads(agents["result"]["content"][0]["text"])
        self.assertEqual(payload["caller_identity"]["member_id"], "agent:demo")
        self.assertEqual(payload["caller_identity"]["kind"], "agent")

    def test_unknown_tool_returns_minus_32601(self):
        with mcp_test_server(main.app) as base_url:
            body = self.call_tool(base_url, "talk_no_such_tool")
        self.assertNotIn("result", body)
        self.assertEqual(body["error"]["code"], -32601)
        self.assertIn("talk_no_such_tool", body["error"]["message"])

    def test_unknown_method_returns_minus_32601(self):
        with mcp_test_server(main.app) as base_url:
            response = self.rpc(base_url, "resources/list")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["error"]["code"], -32601)
        self.assertIn("resources/list", body["error"]["message"])

    def test_invalid_json_returns_minus_32700(self):
        with mcp_test_server(main.app) as base_url:
            response = httpx.post(
                base_url + "/mcp",
                content=b"{not json",
                headers={"Content-Type": "application/json"},
                timeout=30,
                trust_env=False,
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["id"])
        self.assertEqual(body["error"]["code"], -32700)

    def test_non_object_arguments_return_minus_32602(self):
        with mcp_test_server(main.app) as base_url:
            response = self.rpc(
                base_url, "tools/call", {"name": "talk_list_tasks", "arguments": "oops"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], -32602)

    def test_batch_request_is_rejected_as_single_request_only(self):
        with mcp_test_server(main.app) as base_url:
            response = httpx.post(
                base_url + "/mcp",
                json=[
                    {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                    {"jsonrpc": "2.0", "id": 2, "method": "ping"},
                ],
                timeout=30,
                trust_env=False,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], -32602)

    def test_get_is_not_supported(self):
        with mcp_test_server(main.app) as base_url:
            response = httpx.get(base_url + "/mcp", timeout=30, trust_env=False)
        self.assertEqual(response.status_code, 405)

    def test_notification_returns_202_without_body(self):
        with mcp_test_server(main.app) as base_url:
            response = httpx.post(
                base_url + "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                timeout=30,
                trust_env=False,
            )
        self.assertEqual(response.status_code, 202)

    def test_key_mode_requires_api_key(self):
        with patch.object(db, "AUTH_MODE", "key"):
            with mcp_test_server(main.app) as base_url:
                missing = self.rpc(base_url, "initialize")
                self.assertEqual(missing.status_code, 422)
                denied = self.rpc(base_url, "initialize", headers={"X-API-Key": "wrong-key"})
                self.assertEqual(denied.status_code, 401)
                ok = self.rpc(base_url, "initialize", headers={"X-API-Key": "demo-key"})
                self.assertEqual(ok.status_code, 200)
                self.assertEqual(ok.json()["result"]["serverInfo"]["name"], "talk_tools_mcp")

    def test_tool_level_failure_returns_static_message_only(self):
        from server.routes import mcp as mcp_route

        with mcp_test_server(main.app) as base_url:
            body = self.call_tool(base_url, "talk_get_task", {"task_id": 1})
        result = body["result"]
        self.assertTrue(result["isError"])
        # K2.8 收口：客户端只拿到静态消息，不再回传工具名/原始异常文本。
        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["text"], mcp_route.TOOL_FAILURE_TEXT)

    def test_tool_error_leaks_nothing_and_full_exception_is_logged(self):
        from bridges.talk_task_tools import TalkToolError
        from server.routes import mcp as mcp_route

        bs = chr(92)
        sensitive = (
            "open C:" + bs + "secret.txt failed; see file:///root/Private"
            " Folder/secret.txt; api_key=demo-key"
        )
        with patch.object(mcp_route, "call_tool", side_effect=TalkToolError(sensitive)):
            with self.assertLogs("talk", level="ERROR") as caplog:
                with mcp_test_server(main.app) as base_url:
                    body = self.call_tool(
                        base_url,
                        "talk_list_tasks",
                        headers={"X-API-Key": "demo-key"},
                    )
        result = body["result"]
        self.assertTrue(result["isError"])
        rendered = json.dumps(body, ensure_ascii=False)
        self.assertEqual(result["content"][0]["text"], mcp_route.TOOL_FAILURE_TEXT)
        # 客户端可见的任何字节都不得包含原始路径、Key 或异常细节。
        for leaked in ("secret.txt", "Private Folder", "/root", "C:", "demo-key", "TalkToolError", "Traceback"):
            self.assertNotIn(leaked, rendered)
        # 完整异常（类型、消息、堆栈摘要）只写入服务端日志。
        logged = str(caplog.output)
        self.assertIn("mcp tools/call failed", logged)
        self.assertIn("TalkToolError", logged)
        self.assertIn("secret.txt", logged)
        self.assertIn("Private Folder", logged)
        self.assertIn("demo-key", logged)

    def test_jsonrpc_version_is_validated(self):
        with mcp_test_server(main.app) as base_url:
            missing = httpx.post(
                base_url + "/mcp", json={"id": 1, "method": "ping"}, timeout=30, trust_env=False
            )
            legacy = httpx.post(
                base_url + "/mcp",
                json={"jsonrpc": "1.0", "id": 2, "method": "ping"},
                timeout=30,
                trust_env=False,
            )
        for response in (missing, legacy):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["error"]["code"], -32600)

    def test_notification_with_id_gets_normal_response(self):
        with mcp_test_server(main.app) as base_url:
            response = httpx.post(
                base_url + "/mcp",
                json={"jsonrpc": "2.0", "id": 5, "method": "notifications/initialized"},
                timeout=30,
                trust_env=False,
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], 5)
        self.assertEqual(body["error"]["code"], -32601)

    def test_idless_method_is_treated_as_notification(self):
        with mcp_test_server(main.app) as base_url:
            response = httpx.post(
                base_url + "/mcp",
                json={"jsonrpc": "2.0", "method": "ping"},
                timeout=30,
                trust_env=False,
            )
        self.assertEqual(response.status_code, 202)

    def test_empty_array_params_return_minus_32602(self):
        with mcp_test_server(main.app) as base_url:
            response = self.rpc(base_url, "tools/call", [], request_id=11)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], -32602)

    def test_tool_argument_coercion_errors_return_minus_32602(self):
        with mcp_test_server(main.app) as base_url:
            bad_value = self.rpc(
                base_url, "tools/call", {"name": "talk_get_task", "arguments": {"task_id": "abc"}}
            )
            missing_arg = self.rpc(base_url, "tools/call", {"name": "talk_get_task", "arguments": {}})
        for response in (bad_value, missing_arg):
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["error"]["code"], -32602)
            self.assertNotIn("KeyError", body["error"]["message"])
            self.assertNotIn("ValueError", body["error"]["message"])
            self.assertNotIn("Traceback", body["error"]["message"])

    def test_host_header_forgery_cannot_redirect_member_key(self):
        headers = {"X-API-Key": "demo-key", "Host": "attacker.example:5555"}
        with mcp_test_server(main.app) as base_url:
            agents = self.call_tool(
                base_url, "talk_list_agents", {"project_id": "prj_mcp"}, headers=headers
            )
        self.assertFalse(agents["result"]["isError"])
        payload = json.loads(agents["result"]["content"][0]["text"])
        self.assertEqual(payload["caller_identity"]["member_id"], "agent:demo")

    def test_tools_call_rejected_when_no_loopback_self_url(self):
        from server.routes import mcp as mcp_route

        with patch.object(mcp_route, "_self_base_url", return_value=None):
            with mcp_test_server(main.app) as base_url:
                response = self.rpc(base_url, "tools/call", {"name": "talk_list_tasks"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["error"]["code"], -32603)
        self.assertNotIn("Key", body["error"]["message"])

    def test_self_base_url_never_trusts_host_header(self):
        from starlette.requests import Request

        from server.routes import mcp as mcp_route

        def request_with(server_addr):
            return Request(
                {"type": "http", "method": "POST", "path": "/mcp", "server": server_addr}
            )

        self.assertEqual(
            mcp_route._self_base_url(request_with(("127.0.0.1", 8123))),
            "http://127.0.0.1:8123",
        )
        # An unspecified bind address maps to real loopback for self-calls.
        self.assertEqual(
            mcp_route._self_base_url(request_with(("0.0.0.0", 8124))),
            "http://127.0.0.1:8124",
        )
        # A LAN arrival falls back to a configured loopback URL, never Host.
        with patch.dict(
            mcp_route.db.CONFIG, {"server": {"public_url": "http://127.0.0.1:8000"}}
        ):
            self.assertEqual(
                mcp_route._self_base_url(request_with(("192.168.1.5", 8125))),
                "http://127.0.0.1:8000",
            )
        # No loopback source at all -> no callback URL (key must not leave).
        with patch.dict(
            mcp_route.db.CONFIG, {"server": {"public_url": "http://203.0.113.9:8000"}}
        ):
            self.assertIsNone(mcp_route._self_base_url(request_with(("192.168.1.5", 8125))))
        with patch.dict(mcp_route.db.CONFIG, {}, clear=True):
            self.assertIsNone(mcp_route._self_base_url(request_with(("192.168.1.5", 8125))))

    def test_concurrent_tool_calls_keep_identity_isolated(self):
        with self.session() as session:
            session.add(
                Member(id="agent:other", kind="agent", display_name="Other", api_key="other-key")
            )
            session.add(ProjectAgent(project_id="prj_mcp", member_id="agent:other"))
            session.commit()
        outcomes = {}

        def worker(key, tag):
            body = self.call_tool(
                base_url,
                "talk_list_agents",
                {"project_id": "prj_mcp"},
                headers={"X-API-Key": key},
                request_id=tag,
            )
            payload = json.loads(body["result"]["content"][0]["text"])
            outcomes[tag] = payload["caller_identity"]["member_id"]

        with mcp_test_server(main.app) as base_url:
            threads = [
                threading.Thread(target=worker, args=("demo-key", 1)),
                threading.Thread(target=worker, args=("other-key", 2)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(outcomes, {1: "agent:demo", 2: "agent:other"})

    def test_tool_environment_isolates_concurrent_scopes(self):
        from bridges import talk_call_context, talk_task_tools
        from bridges.talk_tool_registry import tool_environment

        seen_keys = {"a": [], "b": []}
        seen_projects = {"a": [], "b": []}

        def worker(tag, key, port):
            with tool_environment("http://127.0.0.1:" + str(port), key):
                for _ in range(30):
                    seen_keys[tag].append(talk_task_tools._config()[1])
                    seen_projects[tag].append(talk_call_context.env("TALK_PROJECT_ID"))
                    time.sleep(0.002)

        threads = [
            threading.Thread(target=worker, args=("a", "key-a", 9101)),
            threading.Thread(target=worker, args=("b", "key-b", 9102)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        # Each scope observed only its own key and a cleared project var; the
        # pre-fix os.environ free-for-all fails this deterministically.
        self.assertEqual(set(seen_keys["a"]), {"key-a"})
        self.assertEqual(set(seen_keys["b"]), {"key-b"})
        self.assertEqual(set(seen_projects["a"]), {None})
        self.assertEqual(set(seen_projects["b"]), {None})

    def test_none_api_key_fails_clearly_and_restores_env(self):
        from bridges.talk_task_tools import TalkToolError
        from bridges.talk_tool_registry import call_tool

        with self.assertRaises(TalkToolError) as ctx:
            call_tool("talk_list_tasks", {}, base_url="http://127.0.0.1:9", api_key=None)
        self.assertIn("API Key", str(ctx.exception))
        # The per-test cleanup (_assert_env_restored) proves nothing leaked.

    def test_sanitize_redacts_keys_and_paths(self):
        from server.routes import mcp as mcp_route

        backslash_path = "D:" + chr(92) + "claude-test" + chr(92) + "TALK" + chr(92) + "talk.db"
        text = mcp_route._sanitize(
            "boom " + backslash_path + " and /home/user/secret.txt token=sekret-1",
            secret="sekret-1",
        )
        self.assertNotIn("sekret-1", text)
        self.assertNotIn("claude-test", text)
        self.assertNotIn("/home/user", text)
        self.assertIn("<path>", text)
        # Normal user-facing tool text passes through untouched.
        self.assertEqual(
            mcp_route._sanitize("TALK API HTTP 404: task_not_found"),
            "TALK API HTTP 404: task_not_found",
        )

    def test_sanitize_redacts_terra_counterexamples_and_unc_paths(self):
        from server.routes import mcp as mcp_route

        bs = chr(92)
        # Terra #800 counterexamples: every one must be fully redacted.
        counterexamples = [
            "C:" + bs + "secret.txt",                            # single-segment drive path
            "D:" + bs + "Private Folder" + bs + "secret.txt",    # segments containing spaces
            "/root/secret.txt",                                  # POSIX outside the old allow-list
            "/workspace/project/secret.txt",                     # POSIX multi-segment
        ]
        for raw in counterexamples:
            text = mcp_route._sanitize("open " + raw + " failed")
            self.assertNotIn("secret.txt", text, raw)
            self.assertNotIn("Private Folder", text, raw)
            self.assertNotIn("/root", text, raw)
            self.assertNotIn("/workspace", text, raw)
            self.assertIn("<path>", text, raw)

        # UNC paths need at least server + share; spaces are covered too.
        unc_cases = [
            bs * 2 + "server" + bs + "share",
            bs * 2 + "server" + bs + "share" + bs + "dir" + bs + "secret.txt",
            bs * 2 + "my server" + bs + "share folder" + bs + "secret.txt",
        ]
        for raw in unc_cases:
            text = mcp_route._sanitize("read " + raw + " denied")
            self.assertNotIn("server", text, raw)
            self.assertNotIn("secret.txt", text, raw)
            self.assertIn("<path>", text, raw)

        # Mixed separators and forward-slash drive variants.
        mixed = "D:" + bs + "Private Folder/inner" + bs + "deep.txt"
        self.assertNotIn("Private Folder", mcp_route._sanitize(mixed))
        self.assertIn("<path>", mcp_route._sanitize(mixed))
        self.assertIn("<path>", mcp_route._sanitize("x C:/secret.txt y"))

        # Member keys are replaced wholesale, on top of path redaction.
        text = mcp_route._sanitize(
            "token=seekret-key path C:" + bs + "k.txt", secret="seekret-key"
        )
        self.assertNotIn("seekret-key", text)
        self.assertIn("***", text)
        self.assertIn("<path>", text)

        # URLs and prose without absolute paths stay untouched.
        self.assertEqual(
            mcp_route._sanitize("TALK API HTTP 404: task_not_found"),
            "TALK API HTTP 404: task_not_found",
        )
        self.assertEqual(
            mcp_route._sanitize("callback http://127.0.0.1:8000/api/members ready"),
            "callback http://127.0.0.1:8000/api/members ready",
        )

    def test_sanitize_redacts_posix_space_paths_and_file_uris(self):
        from server.routes import mcp as mcp_route

        bs = chr(92)
        # K2.8 返修反例 1：含空格的 POSIX 路径必须整段遮掉，不得残留 " Folder/secret.txt"。
        spaced = mcp_route._sanitize("open /root/Private Folder/secret.txt failed")
        self.assertNotIn("Private Folder", spaced)
        self.assertNotIn("secret.txt", spaced)
        self.assertNotIn("/root", spaced)
        self.assertIn("<path>", spaced)

        # K2.8 返修反例 2：file:// 本地 URI 各形态整体替换，绝不原样保留。
        file_uris = [
            "file:///root/secret.txt",
            "file:///root/dir/deep.txt",
            "file://C:/Users/me/secret.txt",
            "file://C:" + bs + "Users" + bs + "me" + bs + "secret.txt",
            "file://server/share/secret.txt",
            "file://server/share/dir/deep.txt",
        ]
        for raw in file_uris:
            text = mcp_route._sanitize("read " + raw + " denied")
            self.assertNotIn("secret.txt", text, raw)
            self.assertNotIn("deep.txt", text, raw)
            self.assertNotIn("file://", text, raw)
            self.assertNotIn("server", text, raw)
            self.assertIn("<path>", text, raw)

        # Terra 原始 4 个反例保持全遮（回归）。
        counterexamples = [
            "C:" + bs + "secret.txt",
            "D:" + bs + "Private Folder" + bs + "secret.txt",
            "/root/secret.txt",
            "/workspace/project/secret.txt",
        ]
        for raw in counterexamples:
            text = mcp_route._sanitize("open " + raw + " failed")
            self.assertNotIn("secret.txt", text, raw)
            self.assertIn("<path>", text, raw)

        # UNC 与 Windows 混合分隔符（回归）。
        unc = bs * 2 + "server" + bs + "share" + bs + "secret.txt"
        text = mcp_route._sanitize("read " + unc + " denied")
        self.assertNotIn("server", text)
        self.assertNotIn("secret.txt", text)
        self.assertIn("<path>", text)
        mixed = "D:" + bs + "Private Folder/inner" + bs + "deep.txt"
        text = mcp_route._sanitize(mixed)
        self.assertNotIn("Private Folder", text)
        self.assertIn("<path>", text)

        # Terra #804 收口反例：含空格的 file URI 必须整体遮掉（失败模式只许
        # 过度遮蔽，不许泄漏路径片段）。
        spaced_uris = [
            "file://server/share/a b.txt",
            "file:///root/Private Folder/secret.txt",
            "file:///root/My Dir/a b.txt",
        ]
        for raw in spaced_uris:
            text = mcp_route._sanitize("read " + raw + " then close")
            self.assertNotIn("a b.txt", text, raw)
            self.assertNotIn("My Dir", text, raw)
            self.assertNotIn("Private Folder", text, raw)
            self.assertNotIn("secret.txt", text, raw)
            self.assertNotIn("file://", text, raw)
            self.assertIn("<path>", text, raw)

        # Terra 非阻断项：POSIX 路径不再吞掉尾随说明文字。
        self.assertEqual(
            mcp_route._sanitize("Failed at /root/secret.txt with explanation"),
            "Failed at <path> with explanation",
        )

        # 正例：普通 URL 与版本号必须原样保留。
        self.assertEqual(
            mcp_route._sanitize("GET https://example.com/api/v1 ok"),
            "GET https://example.com/api/v1 ok",
        )
        self.assertEqual(mcp_route._sanitize("version 1.2.3"), "version 1.2.3")
        self.assertEqual(
            mcp_route._sanitize("callback http://127.0.0.1:8000/api/members ready"),
            "callback http://127.0.0.1:8000/api/members ready",
        )

    def test_stdio_empty_base_url_is_preserved_and_unset_falls_back(self):
        from bridges import talk_call_context, talk_task_tools

        # stdio 语义回归：TALK_BASE_URL 显式为空串时保持空串（与原
        # os.environ.get 行为一致）；只有“未设置”才回退默认地址。
        with patch.dict(os.environ, {"TALK_BASE_URL": "", "TALK_API_KEY": "k"}, clear=True):
            self.assertEqual(talk_task_tools._config()[0], "")
        with patch.dict(os.environ, {"TALK_API_KEY": "k"}, clear=True):
            self.assertEqual(talk_task_tools._config()[0], "http://127.0.0.1:8000")
        # contextvar 覆盖：显式空串与“未设置”可区分；清除(None)读作未设置，
        # 即使进程 env 里存在值也回退默认地址。
        with patch.dict(
            os.environ, {"TALK_BASE_URL": "http://env.invalid", "TALK_API_KEY": "k"}, clear=True
        ):
            with talk_call_context.call_context({"TALK_BASE_URL": ""}):
                self.assertEqual(talk_task_tools._config()[0], "")
            with talk_call_context.call_context({"TALK_BASE_URL": None}):
                self.assertEqual(talk_task_tools._config()[0], "http://127.0.0.1:8000")

    def test_non_object_params_rejected_for_every_method(self):
        with mcp_test_server(main.app) as base_url:
            for method in ("initialize", "ping", "tools/list", "tools/call"):
                for params in ([], "scalar", 123, ["a"], True):
                    response = self.rpc(
                        base_url, method, params, request_id=f"{method}-{params!r}"
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    body = response.json()
                    self.assertEqual(
                        body.get("error", {}).get("code"), -32602, f"{method} {params!r}"
                    )
            # Object params and absent params keep working everywhere.
            for method in ("initialize", "ping", "tools/list"):
                as_object = self.rpc(base_url, method, {}, request_id=f"{method}-obj")
                self.assertIsNone(as_object.json().get("error"), method)
                absent = self.rpc(base_url, method, request_id=f"{method}-absent")
                self.assertIsNone(absent.json().get("error"), method)
            # An explicit JSON null counts as "absent", not an error.
            explicit_null = httpx.post(
                base_url + "/mcp",
                json={"jsonrpc": "2.0", "id": "nullp", "method": "ping", "params": None},
                timeout=30,
                trust_env=False,
            )
            self.assertEqual(explicit_null.json()["result"], {})
            # tools/call with a valid object still dispatches.
            listed = self.call_tool(base_url, "talk_list_tasks")
            self.assertFalse(listed["result"]["isError"])

    def test_call_tool_scopes_identity_per_thread_without_env_mutation(self):
        from bridges import talk_call_context, talk_task_tools
        from bridges import talk_tool_registry

        seen = {}
        waited = {}
        entered = threading.Event()
        release = threading.Event()

        def slow_dispatch(name, arguments):
            base_url, api_key = talk_task_tools._config()
            seen["slow"] = (base_url, api_key, talk_call_context.env("TALK_PROJECT_ID"))
            entered.set()
            waited["slow"] = release.wait(10)
            return {"ok": True}

        def fast_dispatch(name, arguments):
            base_url, api_key = talk_task_tools._config()
            seen["fast"] = (base_url, api_key, talk_call_context.env("TALK_PROJECT_ID"))
            return {"ok": True}

        names = ("TALK_BASE_URL", "TALK_API_KEY", "TALK_PROJECT_ID", "TALK_MEMBER_ID")
        env_before = {name: os.environ.get(name) for name in names}
        with patch.object(talk_tool_registry, "dispatch_tool", slow_dispatch):
            slow = threading.Thread(
                target=lambda: talk_tool_registry.call_tool(
                    "talk_list_tasks", {}, base_url="http://127.0.0.1:9101", api_key="key-slow"
                )
            )
            slow.start()
            self.assertTrue(entered.wait(10))
            with patch.object(talk_tool_registry, "dispatch_tool", fast_dispatch):
                fast = threading.Thread(
                    target=lambda: talk_tool_registry.call_tool(
                        "talk_list_tasks", {}, base_url="http://127.0.0.1:9102", api_key="key-fast"
                    )
                )
                fast.start()
                fast.join(timeout=10)
            # The fast call must finish while the slow one is still running;
            # the pre-fix global env lock would block it until release.
            self.assertFalse(fast.is_alive(), "concurrent call blocked behind the long-running call")
            release.set()
            slow.join(timeout=10)
        self.assertFalse(slow.is_alive())
        self.assertTrue(waited.get("slow"))
        # Each request observed only its own key/base_url and a cleared project.
        self.assertEqual(seen["slow"], ("http://127.0.0.1:9101", "key-slow", None))
        self.assertEqual(seen["fast"], ("http://127.0.0.1:9102", "key-fast", None))
        for name, value in env_before.items():
            self.assertEqual(os.environ.get(name), value, f"{name} leaked into process env")

    def test_wait_tasks_http_call_does_not_block_other_member_calls(self):
        from bridges import talk_task_tools

        with self.session() as session:
            session.add(
                Member(id="agent:other", kind="agent", display_name="Other", api_key="other-key")
            )
            session.add(ProjectAgent(project_id="prj_mcp", member_id="agent:other"))
            session.commit()

        queued = {"id": 1, "project_id": "prj_mcp", "workflow_status": "queued"}

        def fake_api_request(method, path, **kwargs):
            if path == "/api/tasks":
                return [queued]
            raise AssertionError(f"unexpected API path {path}")

        a_done = threading.Event()
        outcomes = {}
        timings = {}

        def call_wait():
            started = time.monotonic()
            body = self.call_tool(
                base_url,
                "talk_wait_tasks",
                {"project_id": "prj_mcp", "timeout_seconds": 3.0},
                headers={"X-API-Key": "demo-key"},
                request_id=31,
            )
            timings["wait"] = time.monotonic() - started
            outcomes["wait"] = body
            a_done.set()

        def call_list():
            started = time.monotonic()
            body = self.call_tool(
                base_url,
                "talk_list_tasks",
                {"project_id": "prj_mcp"},
                headers={"X-API-Key": "other-key"},
                request_id=32,
            )
            timings["list"] = time.monotonic() - started
            outcomes["list"] = body

        with patch.object(talk_task_tools, "_api_request", fake_api_request):
            with mcp_test_server(main.app) as base_url:
                wait_thread = threading.Thread(target=call_wait)
                wait_thread.start()
                list_thread = threading.Thread(target=call_list)
                list_thread.start()
                list_thread.join(timeout=10)
                # The other member's call is answered while the 3-second wait
                # is still in flight; the pre-fix env lock would queue it.
                self.assertFalse(list_thread.is_alive())
                self.assertLess(timings["list"], 2.0)
                self.assertFalse(a_done.is_set(), "talk_wait_tasks blocked a concurrent member call")
                wait_thread.join(timeout=10)
        self.assertFalse(wait_thread.is_alive())
        wait = outcomes["wait"]["result"]
        self.assertFalse(wait["isError"])
        payload = json.loads(wait["content"][0]["text"])
        self.assertTrue(payload["timed_out"])
        self.assertEqual(payload["return_reason"], "timeout")
        self.assertEqual(payload["timeout_seconds"], 3.0)
        self.assertFalse(outcomes["list"]["result"]["isError"])
