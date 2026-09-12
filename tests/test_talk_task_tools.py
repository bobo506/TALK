import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

import server.main as main
from bridges import talk_task_tools
from bridges.cli_bridge import configure_talk_tool_environment
from bridges.talk_task_tools import (
    DEFAULT_WAIT_WORKFLOW_STATUSES,
    TOOL_SCHEMAS,
    TalkToolError,
    dispatch_tool,
    latest_instance_summary,
    wait_tasks,
)
from cli.talk import scaffold_project
from server.models import AgentInstance
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

LEAKED_LOG_MARKER = "LEAKED_CLI_LOG_MARKER"
INSTANCE_SUMMARY_KEYS = {"id", "runtime", "status", "current_task_id", "last_seen_at", "pid"}
STDIO_FALLBACK_MARKER = "STDIO_FALLBACK_FILE_STDIO"


def run_stdio_process(command, *, input_text, env, cwd=None, timeout=15, check=False):
    """运行 stdio MCP 子进程并取回输出。

    首选匿名管道，与真实 MCP 客户端一致；当运行沙箱禁止 CreatePipe
    （Windows 报 PermissionError / WinError 5，例如 DSH 的受限文件沙箱）时，
    退化为临时文件型 stdio。两种通道喂入同一份 JSON-RPC 文本、断言完全相同，
    只有传输方式不同；退化会在 stderr 留下 STDIO_FALLBACK_MARKER 以便如实记录。
    """
    pipe_kwargs = {
        "input": input_text,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "env": env,
        "timeout": timeout,
        "check": check,
    }
    if cwd is not None:
        pipe_kwargs["cwd"] = cwd
    try:
        return subprocess.run(list(command), **pipe_kwargs)
    except PermissionError:
        return run_stdio_process_with_files(
            command, input_text=input_text, env=env, cwd=cwd, timeout=timeout, check=check
        )


def run_stdio_process_with_files(command, *, input_text, env, cwd, timeout, check):
    """文件型 stdio 退化通道：stdin/stdout/stderr 都用普通文件，不创建任何管道。"""
    command = [str(part) for part in command]
    with tempfile.TemporaryDirectory(prefix="talk-stdio-") as tmp_name:
        workdir = Path(tmp_name)
        stdin_path = workdir / "stdin.jsonl"
        stdout_path = workdir / "stdout.jsonl"
        stderr_path = workdir / "stderr.log"
        stdin_path.write_text(input_text, encoding="utf-8")
        with stdin_path.open("r", encoding="utf-8") as stdin_handle, stdout_path.open(
            "w", encoding="utf-8"
        ) as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            process = subprocess.Popen(
                command,
                stdin=stdin_handle,
                stdout=stdout_handle,
                stderr=stderr_handle,
                env=env,
                cwd=cwd,
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
                raise
        stdout = stdout_path.read_text(encoding="utf-8")
        stderr = stderr_path.read_text(encoding="utf-8")
    print(f"{STDIO_FALLBACK_MARKER} {command[1] if len(command) > 1 else command[0]}", file=sys.stderr)
    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class TalkTaskToolTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        self.add_member("agent:other", api_key="other-key", display_name="Other")
        with self.make_client() as client:
            created = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_tools", "display_name": "Tool Project"},
            )
            synced = client.post(
                "/api/projects/prj_tools/sync",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "agents": [
                        {
                            "member_id": "agent:worker",
                            "business_role": "developer",
                            "decision_tier": "execution",
                            "capability_summary": ["代码实现", "API 测试"],
                        }
                    ]
                },
            )
            instance = client.put(
                "/api/instances/worker-1",
                headers={"X-API-Key": "worker-key"},
                json={"runtime": "pi", "status": "idle"},
            )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(synced.status_code, 200)
        self.assertEqual(instance.status_code, 200)

    @staticmethod
    def _environment(base_url: str, api_key: str, member_id: str) -> dict[str, str]:
        return {
            "TALK_BASE_URL": base_url,
            "TALK_API_KEY": api_key,
            "TALK_MEMBER_ID": member_id,
            "TALK_PROJECT_ID": "prj_tools",
        }

    def seed_instance_history(
        self,
        *,
        member_id: str = "agent:worker",
        history_count: int = 240,
        error_length: int = 4000,
    ) -> str:
        """写入数百条历史实例（含超长 last_error），并追加一条真正最新的实例。"""
        now = datetime.now(timezone.utc)
        long_error = LEAKED_LOG_MARKER + "旧 CLI 日志" * error_length
        prefix = member_id.split(":", 1)[-1]
        with self.session() as session:
            for index in range(history_count):
                seen = now - timedelta(minutes=index + 5)
                session.add(
                    AgentInstance(
                        id=f"{prefix}-old-{index:04d}",
                        member_id=member_id,
                        runtime="pi",
                        status="error",
                        host="lab-host",
                        pid=1000 + index,
                        current_task_id=f"task-{index}",
                        last_error=long_error,
                        created_at=now - timedelta(days=30),
                        updated_at=seen,
                        last_seen_at=seen,
                    )
                )
            session.add(
                AgentInstance(
                    id=f"{prefix}-latest",
                    member_id=member_id,
                    runtime="dsh",
                    status="busy",
                    host="lab-host",
                    pid=4321,
                    current_task_id="42",
                    last_error=long_error,
                    created_at=now - timedelta(days=1),
                    updated_at=now,
                    last_seen_at=now,
                )
            )
            session.commit()
        return long_error

    def test_list_agents_project_path_returns_bounded_latest_instance(self):
        long_error = self.seed_instance_history()
        with LiveTalkServer(main.app) as base_url:
            human_env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, human_env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        payload = json.dumps(result, ensure_ascii=False)
        self.assertGreater(len(long_error), 20000)
        self.assertEqual([agent["member_id"] for agent in result["agents"]], ["agent:worker"])
        agent = result["agents"][0]
        self.assertEqual(agent["business_role"], "developer")
        self.assertEqual(agent["decision_tier"], "execution")
        self.assertEqual(agent["capability_summary"], ["代码实现", "API 测试"])
        self.assertEqual(agent["display_name"], "Worker")
        self.assertEqual(agent["availability"], "busy")
        self.assertEqual(len(agent["instances"]), 1)
        instance = agent["instances"][0]
        self.assertEqual(instance["id"], "worker-latest")
        self.assertEqual(instance["runtime"], "dsh")
        self.assertEqual(instance["status"], "busy")
        self.assertEqual(instance["current_task_id"], "42")
        self.assertEqual(instance["pid"], 4321)
        self.assertEqual(set(instance), INSTANCE_SUMMARY_KEYS)
        self.assertIn("availability_note", result)
        self.assertLess(len(payload), 1500)
        self.assertNotIn(LEAKED_LOG_MARKER, payload)
        self.assertNotIn("last_error", payload)
        self.assertNotIn("worker-old-", payload)

    def test_list_agents_without_project_path_still_bounds_instances(self):
        long_error = self.seed_instance_history()
        with LiveTalkServer(main.app) as base_url:
            human_env = self._environment(base_url, "bobo-key", "human:bobo")
            # 空 project_id 等同 bridge 未设置 TALK_PROJECT_ID，走非项目路径。
            human_env["TALK_PROJECT_ID"] = ""
            with patch.dict(os.environ, human_env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        payload = json.dumps(result, ensure_ascii=False)
        self.assertIsNone(result["project_id"])
        agents = {agent["member_id"]: agent for agent in result["agents"]}
        self.assertEqual(sorted(agents), ["agent:other", "agent:worker"])
        worker = agents["agent:worker"]
        self.assertEqual(worker["availability"], "busy")
        self.assertEqual(len(worker["instances"]), 1)
        self.assertEqual(worker["instances"][0]["id"], "worker-latest")
        self.assertEqual(set(worker["instances"][0]), INSTANCE_SUMMARY_KEYS)
        self.assertEqual(worker["display_name"], "Worker")
        other = agents["agent:other"]
        self.assertEqual(other["instances"], [])
        self.assertEqual(other["availability"], "offline")
        self.assertLess(len(payload), 1500)
        self.assertNotIn(LEAKED_LOG_MARKER, payload)
        self.assertNotIn("last_error", payload)
        self.assertNotIn(long_error[:20], payload)

    def test_latest_instance_summary_orders_by_last_seen_at(self):
        summary = latest_instance_summary(
            [
                {
                    "id": "b",
                    "runtime": "dsh",
                    "status": "idle",
                    "last_seen_at": "2026-09-11T10:00:00+00:00",
                    "last_error": LEAKED_LOG_MARKER,
                },
                {
                    "id": "c",
                    "runtime": "codex",
                    "status": "busy",
                    "pid": 7,
                    "last_seen_at": "2026-09-11T12:00:00Z",
                    "last_error": LEAKED_LOG_MARKER,
                },
                {
                    "id": "a",
                    "runtime": "pi",
                    "status": "offline",
                    "last_seen_at": "2026-09-11T08:00:00+00:00",
                },
                {
                    "id": "broken",
                    "runtime": "pi",
                    "status": "error",
                    "last_seen_at": "not-a-timestamp",
                },
            ]
        )

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["id"], "c")
        self.assertEqual(summary[0]["pid"], 7)
        self.assertEqual(set(summary[0]), INSTANCE_SUMMARY_KEYS)
        self.assertNotIn(LEAKED_LOG_MARKER, json.dumps(summary, ensure_ascii=False))
        self.assertEqual(latest_instance_summary([]), [])

    def test_mcp_catalog_exposes_task_hall_tools(self):
        with LiveTalkServer(main.app) as base_url:
            requests = "\n".join(
                [
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
                    json.dumps({
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "talk_list_agents", "arguments": {}},
                    }),
                ]
            ) + "\n"
            env = os.environ.copy()
            env.update(self._environment(base_url, "bobo-key", "human:bobo"))
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            process = run_stdio_process(
                [sys.executable, str(Path("bridges/talk_send_mcp.py").resolve())],
                input_text=requests,
                env=env,
                timeout=10,
                check=True,
            )

        responses = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
        tools = responses[1]["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertEqual(
            names,
            {
                "talk_send",
                "talk_list_agents",
                "talk_delegate_task",
                "talk_get_task",
                "talk_list_tasks",
                "talk_wait_tasks",
                "talk_reply_task",
                "talk_cancel_task",
                "talk_collect_result",
            },
        )
        delegate_schema = next(
            tool["inputSchema"]
            for tool in tools
            if tool["name"] == "talk_delegate_task"
        )
        self.assertTrue(
            {
                "task_kind",
                "review_policy",
                "related_task_ids",
                "trigger_task_id",
                "parent_task_id",
                "authorization_epoch",
                "max_clarification_rounds",
            }.issubset(delegate_schema["properties"])
        )
        self.assertFalse(responses[2]["result"]["isError"])
        listed = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual([agent["member_id"] for agent in listed["agents"]], ["agent:worker"])

    def test_bridge_project_context_becomes_tool_default(self):
        with tempfile.TemporaryDirectory(prefix="talk-tool-project-") as tmpdir:
            project_root = Path(tmpdir)
            scaffold_project(project_root, display_name="Tool Context", project_id="prj_context")
            args = Namespace(
                key="context-key",
                base_url="http://talk.test",
                project=str(project_root),
            )
            with patch.dict(os.environ, {}, clear=True):
                configure_talk_tool_environment(args, "agent:context")
                self.assertEqual(os.environ["TALK_API_KEY"], "context-key")
                self.assertEqual(os.environ["TALK_BASE_URL"], "http://talk.test")
                self.assertEqual(os.environ["TALK_MEMBER_ID"], "agent:context")
                self.assertEqual(os.environ["TALK_PROJECT_ID"], "prj_context")

    def test_task_tools_run_full_live_service_flow(self):
        with LiveTalkServer(main.app) as base_url:
            human_env = self._environment(base_url, "bobo-key", "human:bobo")
            worker_env = self._environment(base_url, "worker-key", "agent:worker")
            with patch.dict(os.environ, human_env, clear=False):
                agents = dispatch_tool("talk_list_agents", {})
                created = dispatch_tool(
                    "talk_delegate_task",
                    {
                        "target_member_id": "agent:worker",
                        "title": "Tool delegation",
                        "content": "Produce a result",
                    },
                )
                listed = dispatch_tool(
                    "talk_list_tasks",
                    {"workflow_status": "assigned", "task_kind": "general"},
                )
                fetched = dispatch_tool("talk_get_task", {"task_id": created["id"]})

            with patch.dict(os.environ, worker_env, clear=False):
                clarification = dispatch_tool(
                    "talk_reply_task",
                    {
                        "task_id": created["id"],
                        "body": "Which format should I use?",
                        "workflow_action": "request_clarification",
                    },
                )

            with patch.dict(os.environ, human_env, clear=False):
                answer = dispatch_tool(
                    "talk_reply_task",
                    {
                        "task_id": created["id"],
                        "body": "Use Markdown.",
                        "workflow_action": "submit_clarification_answer",
                    },
                )

            with patch.dict(os.environ, worker_env, clear=False):
                accepted = dispatch_tool(
                    "talk_reply_task",
                    {
                        "task_id": created["id"],
                        "body": "Accepted.",
                        "workflow_action": "accept",
                    },
                )

            with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
                claimed = client.post(
                    f"/api/tasks/{created['id']}/claim",
                    headers={"X-API-Key": "worker-key"},
                    json={"instance_id": "worker-1"},
                ).json()
                result_message = client.post(
                    "/api/messages",
                    headers={"X-API-Key": "worker-key"},
                    json={
                        "type": "text",
                        "content": "# Result\nDone",
                        "to": ["human:bobo"],
                        "group_id": claimed["hall_group_id"],
                    },
                ).json()
                completed = client.post(
                    f"/api/tasks/{created['id']}/complete",
                    headers={"X-API-Key": "worker-key"},
                    json={"status": "succeeded", "result_message_id": result_message["id"]},
                )
                self.assertEqual(completed.status_code, 200)

            with patch.dict(os.environ, human_env, clear=False):
                waited = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "task_ids": [created["id"]],
                        "workflow_statuses": ["submitted"],
                        "timeout_seconds": 0,
                    },
                )
                collected = dispatch_tool("talk_collect_result", {"task_id": created["id"]})
                cancelable = dispatch_tool(
                    "talk_delegate_task",
                    {"target_member_id": "agent:worker", "content": "Cancel me"},
                )
                canceled = dispatch_tool(
                    "talk_cancel_task",
                    {"task_id": cancelable["id"], "reason": "No longer needed."},
                )

        self.assertEqual([agent["member_id"] for agent in agents["agents"]], ["agent:worker"])
        self.assertEqual(agents["agents"][0]["availability"], "available")
        self.assertEqual(agents["agents"][0]["business_role"], "developer")
        self.assertEqual(agents["agents"][0]["decision_tier"], "execution")
        self.assertEqual(
            agents["agents"][0]["capability_summary"],
            ["代码实现", "API 测试"],
        )
        self.assertEqual([task["id"] for task in listed["tasks"]], [created["id"]])
        self.assertEqual(fetched["task"]["hall_group_id"], created["hall_group_id"])
        self.assertEqual(fetched["relations"], [])
        self.assertEqual(clarification["task"]["workflow_status"], "clarification_requested")
        self.assertEqual(answer["message"]["group_id"], created["hall_group_id"])
        self.assertEqual(answer["task"]["workflow_status"], "clarification_answered")
        self.assertEqual(accepted["task"]["workflow_status"], "accepted")
        self.assertFalse(waited["timed_out"])
        self.assertEqual(collected["task"]["workflow_status"], "completed")
        self.assertEqual(collected["result_message"]["content"], "# Result\nDone")
        self.assertEqual(canceled["task"]["workflow_status"], "canceled")
        self.assertEqual(canceled["message"]["group_id"], cancelable["hall_group_id"])

    def test_task_tools_create_typed_children_and_return_relations(self):
        self.add_member(
            "agent:reviewer",
            api_key="reviewer-key",
            display_name="Reviewer",
        )
        with LiveTalkServer(main.app) as base_url:
            worker_env = self._environment(base_url, "worker-key", "agent:worker")
            with httpx.Client(
                base_url=base_url,
                timeout=10,
                trust_env=False,
            ) as client:
                client.post(
                    "/api/projects/prj_tools/sync",
                    headers={"X-API-Key": "bobo-key"},
                    json={
                        "agents": [
                            {"member_id": "agent:worker"},
                            {"member_id": "agent:reviewer"},
                        ]
                    },
                ).raise_for_status()
                root = client.post(
                    "/api/tasks",
                    headers={"X-API-Key": "bobo-key"},
                    json={
                        "target_member_id": "agent:worker",
                        "content": "Coordinate a reviewed slice",
                        "project_id": "prj_tools",
                        "may_delegate": True,
                        "slice_budget": 2,
                        "authorization_ttl_seconds": 60,
                    },
                ).json()
                claimed_root = client.post(
                    f"/api/tasks/{root['id']}/claim",
                    headers={"X-API-Key": "worker-key"},
                    json={},
                ).json()

            with patch.dict(os.environ, worker_env, clear=False):
                development = dispatch_tool(
                    "talk_delegate_task",
                    {
                        "target_member_id": "agent:other",
                        "content": "Implement the frozen slice",
                        "task_kind": "development",
                        "review_policy": "required",
                        "parent_task_id": claimed_root["id"],
                        "authorization_epoch": claimed_root["authorization_epoch"],
                    },
                )

            with httpx.Client(
                base_url=base_url,
                timeout=10,
                trust_env=False,
            ) as client:
                claimed_development = client.post(
                    f"/api/tasks/{development['id']}/claim",
                    headers={"X-API-Key": "other-key"},
                    json={},
                ).json()
                result = client.post(
                    "/api/messages",
                    headers={"X-API-Key": "other-key"},
                    json={
                        "type": "text",
                        "content": "Frozen implementation result",
                        "to": ["agent:worker"],
                        "group_id": development["hall_group_id"],
                    },
                ).json()
                client.post(
                    f"/api/tasks/{development['id']}/complete",
                    headers={"X-API-Key": "other-key"},
                    json={
                        "status": "succeeded",
                        "result_message_id": result["id"],
                        "claim_token": claimed_development["claim_token"],
                    },
                ).raise_for_status()

            with patch.dict(os.environ, worker_env, clear=False):
                dispatch_tool("talk_collect_result", {"task_id": development["id"]})
                review = dispatch_tool(
                    "talk_delegate_task",
                    {
                        "target_member_id": "agent:reviewer",
                        "content": "Review the frozen slice",
                        "task_kind": "review",
                        "related_task_ids": [development["id"]],
                        "parent_task_id": claimed_root["id"],
                        "authorization_epoch": claimed_root["authorization_epoch"],
                        "max_clarification_rounds": 2,
                    },
                )
                fetched = dispatch_tool(
                    "talk_get_task",
                    {"task_id": review["id"]},
                )
                listed = dispatch_tool(
                    "talk_list_tasks",
                    {"project_id": "prj_tools", "task_kind": "review"},
                )

        self.assertEqual(development["task_kind"], "development")
        self.assertEqual(development["review_policy"], "required")
        self.assertEqual(review["task_kind"], "review")
        self.assertEqual(review["max_clarification_rounds"], 2)
        self.assertEqual(fetched["relations"][0]["relation_type"], "reviews")
        self.assertEqual(
            fetched["relations"][0]["target_task_id"],
            development["id"],
        )
        self.assertEqual([task["id"] for task in listed["tasks"]], [review["id"]])

    def test_pi_extension_registers_same_task_tool_surface(self):
        source = Path("bridges/talk_tools_extension.ts").read_text(encoding="utf-8")
        for name in (
            "talk_list_agents",
            "talk_delegate_task",
            "talk_get_task",
            "talk_list_tasks",
            "talk_wait_tasks",
            "talk_reply_task",
            "talk_cancel_task",
            "talk_collect_result",
        ):
            self.assertIn(f'name: "{name}"', source)
        for field in (
            "task_kind",
            "review_policy",
            "related_task_ids",
            "trigger_task_id",
            "parent_task_id",
            "authorization_epoch",
            "max_clarification_rounds",
            "capability_summary",
            "relations",
        ):
            self.assertIn(field, source)


class TalkWaitTaskTests(RouteTestCase):
    """600 秒有界等待：提前返回、有界输出、程序级计数与错误语义。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        self.add_member("agent:other", api_key="other-key", display_name="Other")
        with self.make_client() as client:
            created = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_wait", "display_name": "Wait Project"},
            )
            synced = client.post(
                "/api/projects/prj_wait/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": "agent:worker", "business_role": "dev"}]},
            )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(synced.status_code, 200)

    @staticmethod
    def _environment(base_url: str, api_key: str, member_id: str) -> dict[str, str]:
        return {
            "TALK_BASE_URL": base_url,
            "TALK_API_KEY": api_key,
            "TALK_MEMBER_ID": member_id,
            "TALK_PROJECT_ID": "prj_wait",
        }

    def _create_task(
        self,
        base_url: str,
        *,
        content: str = "等待测试任务",
        project_id: str = "prj_wait",
        key: str = "bobo-key",
    ) -> dict:
        with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
            response = client.post(
                "/api/tasks",
                headers={"X-API-Key": key},
                json={
                    "target_member_id": "agent:worker",
                    "content": content,
                    "project_id": project_id,
                },
            )
            response.raise_for_status()
            return response.json()

    def _cancel_task(self, base_url: str, task_id: int, key: str = "bobo-key") -> dict:
        with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
            response = client.post(
                f"/api/tasks/{task_id}/cancel",
                headers={"X-API-Key": key},
            )
            response.raise_for_status()
            return response.json()

    def _submit_result(self, base_url: str, task_id: int, key: str = "worker-key") -> dict:
        with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
            claimed = client.post(
                f"/api/tasks/{task_id}/claim",
                headers={"X-API-Key": key},
                json={},
            )
            claimed.raise_for_status()
            claim = claimed.json()
            message = client.post(
                "/api/messages",
                headers={"X-API-Key": key},
                json={
                    "type": "text",
                    "content": "# 成果\n已完成",
                    "to": ["human:bobo"],
                    "group_id": claim["hall_group_id"],
                },
            )
            message.raise_for_status()
            completed = client.post(
                f"/api/tasks/{task_id}/complete",
                headers={"X-API-Key": key},
                json={
                    "status": "succeeded",
                    "result_message_id": message.json()["id"],
                    "claim_token": claim["claim_token"],
                },
            )
            completed.raise_for_status()
            return message.json()

    def test_wait_defaults_and_early_return_statuses_are_the_600_second_contract(self):
        signature_default = talk_task_tools.wait_tasks.__kwdefaults__["timeout_seconds"]
        self.assertEqual(signature_default, 600.0)
        self.assertEqual(talk_task_tools.WAIT_MAX_TIMEOUT_SECONDS, 600.0)
        self.assertEqual(talk_task_tools.WAIT_DEFAULT_TIMEOUT_SECONDS, 600.0)
        self.assertGreaterEqual(
            talk_task_tools.WAIT_RECOMMENDED_CLIENT_TIMEOUT_SECONDS,
            660.0,
        )
        schema = next(tool for tool in TOOL_SCHEMAS if tool["name"] == "talk_wait_tasks")
        timeout_schema = schema["inputSchema"]["properties"]["timeout_seconds"]
        self.assertEqual(timeout_schema["maximum"], 600)
        self.assertEqual(timeout_schema["default"], 600)
        self.assertIn("600", schema["description"])
        self.assertIn("660", schema["description"])
        # 输出上限与取消/断线边界必须写在工具描述里，不能只留在报告。
        self.assertIn("omitted_task_ids", schema["description"])
        self.assertIn(str(talk_task_tools.WAIT_MAX_TASK_REFERENCES), schema["description"])
        self.assertIn("不保证宿主外层零回合", schema["description"])
        self.assertIn("不保证带走 MCP 子进程", schema["description"])
        self.assertIn("不改变任务状态", schema["description"])
        self.assertIn("程序内部不调用模型", schema["description"])
        # 成果提交 / 完成 / 失败 / 需澄清都必须在默认提前返回集合里。
        for status in ("submitted", "completed", "failed", "clarification_requested"):
            self.assertIn(status, DEFAULT_WAIT_WORKFLOW_STATUSES)

    def test_wait_zero_timeout_returns_after_one_poll(self):
        with LiveTalkServer(main.app) as base_url:
            task = self._create_task(base_url)
            with patch.dict(
                os.environ,
                self._environment(base_url, "bobo-key", "human:bobo"),
                clear=False,
            ):
                started = time.monotonic()
                result = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "task_ids": [task["id"]],
                        "workflow_statuses": ["submitted"],
                        "timeout_seconds": 0,
                    },
                )
                wall = time.monotonic() - started

        self.assertTrue(result["timed_out"])
        self.assertEqual(result["return_reason"], "timeout")
        self.assertEqual(result["timeout_seconds"], 0.0)
        self.assertEqual(result["requested_timeout_seconds"], 0.0)
        self.assertEqual(result["query_stats"]["poll_rounds"], 1)
        self.assertEqual(result["query_stats"]["http_requests"], 1)
        self.assertLess(wall, 5)
        self.assertEqual(result["tasks"][0]["workflow_status"], "assigned")

    def test_wait_clamps_out_of_range_and_rejects_invalid_parameters(self):
        with LiveTalkServer(main.app) as base_url:
            task = self._create_task(base_url)
            self._cancel_task(base_url, task["id"])  # canceled 属于默认提前返回状态
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                oversized = dispatch_tool(
                    "talk_wait_tasks",
                    {"task_ids": [task["id"]], "timeout_seconds": 100000},
                )
                negative = dispatch_tool(
                    "talk_wait_tasks",
                    {"task_ids": [task["id"]], "timeout_seconds": -5},
                )
                missing = dispatch_tool("talk_wait_tasks", {"task_ids": [task["id"]]})
                numeric_string = dispatch_tool(
                    "talk_wait_tasks",
                    {"task_ids": [task["id"]], "timeout_seconds": "600"},
                )

        for result in (oversized, negative, missing, numeric_string):
            self.assertFalse(result["timed_out"])
            self.assertEqual(result["return_reason"], "matched")
        self.assertEqual(oversized["requested_timeout_seconds"], 100000.0)
        self.assertEqual(oversized["timeout_seconds"], 600.0)
        self.assertEqual(oversized["max_timeout_seconds"], 600.0)
        self.assertEqual(negative["timeout_seconds"], 0.0)
        self.assertEqual(missing["timeout_seconds"], 600.0)
        self.assertEqual(numeric_string["timeout_seconds"], 600.0)

        for value in (float("nan"), float("inf"), "abc", True):
            with self.subTest(value=value), self.assertRaises(TalkToolError):
                wait_tasks(
                    project_id="prj_wait",
                    task_ids=[task["id"]],
                    timeout_seconds=value,
                )
        for task_ids in ("12", [None], [object()]):
            with self.subTest(task_ids=task_ids), self.assertRaises(TalkToolError):
                wait_tasks(
                    project_id="prj_wait",
                    task_ids=task_ids,
                    timeout_seconds=0,
                )

    def test_wait_returns_early_when_result_is_submitted_without_full_history(self):
        holder: dict = {}
        with LiveTalkServer(main.app) as base_url:
            task = self._create_task(base_url)
            env = self._environment(base_url, "bobo-key", "human:bobo")

            def run_wait() -> None:
                holder["result"] = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "task_ids": [task["id"]],
                        "workflow_statuses": ["submitted"],
                    },
                )

            with patch.dict(os.environ, env, clear=False):
                thread = threading.Thread(target=run_wait, daemon=True)
                started = time.monotonic()
                thread.start()
                time.sleep(2.0)
                message = self._submit_result(base_url, task["id"])
                thread.join(timeout=60)
                wall = time.monotonic() - started
            self.assertFalse(thread.is_alive())

        result = holder["result"]
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["return_reason"], "matched")
        self.assertEqual(result["timeout_seconds"], 600.0)
        self.assertGreaterEqual(wall, 2.0)
        self.assertLess(wall, 30)  # 命中 submitted 立即返回，不等满 600 秒
        self.assertEqual(result["matched_task_ids"], [task["id"]])
        # 兼容原契约：提前返回时 tasks 就是命中集合，且数量上限与截断标记齐备。
        self.assertEqual(
            [summary["id"] for summary in result["tasks"]], result["matched_task_ids"]
        )
        self.assertEqual(result["tasks_returned"], 1)
        self.assertFalse(result["tasks_truncated"])
        self.assertEqual(result["tasks_omitted_count"], 0)
        self.assertIn("omitted_task_ids", result["tasks_note"])
        summary = result["tasks"][0]
        self.assertEqual(set(summary), set(talk_task_tools._WAIT_TASK_REFERENCE_FIELDS))
        self.assertEqual(summary["workflow_status"], "submitted")
        self.assertEqual(summary["hall_group_id"], task["hall_group_id"])
        self.assertEqual(summary["result_message_id"], message["id"])
        payload = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("等待测试任务", payload)
        self.assertNotIn("# 成果", payload)
        self.assertNotIn("messages", result)
        self.assertLess(len(payload), 2500)
        self.assertIn("counting_note", result)

    def test_wait_filters_multiple_tasks_and_keeps_project_scope(self):
        with LiveTalkServer(main.app) as base_url:
            first = self._create_task(base_url, content="任务一")
            second = self._create_task(base_url, content="任务二")
            third = self._create_task(base_url, content="任务三")
            with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
                client.post(
                    "/api/projects",
                    headers={"X-API-Key": "bobo-key"},
                    json={"project_id": "prj_other", "display_name": "Other"},
                ).raise_for_status()
                client.post(
                    "/api/projects/prj_other/sync",
                    headers={"X-API-Key": "bobo-key"},
                    json={"agents": [{"member_id": "agent:worker"}]},
                ).raise_for_status()
            foreign = self._create_task(base_url, content="其它项目任务", project_id="prj_other")
            self._cancel_task(base_url, third["id"])
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                scoped = dispatch_tool(
                    "talk_wait_tasks",
                    {"timeout_seconds": 0, "workflow_statuses": ["submitted"]},
                )
                filtered = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "task_ids": [first["id"], second["id"], third["id"]],
                        "workflow_statuses": ["canceled"],
                        "timeout_seconds": 0,
                    },
                )
                deduped = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "task_ids": [third["id"], third["id"]],
                        "workflow_statuses": ["submitted"],
                        "timeout_seconds": 0,
                    },
                )

        listed_ids = [task["id"] for task in scoped["tasks"]]
        self.assertEqual({task["project_id"] for task in scoped["tasks"]}, {"prj_wait"})
        self.assertNotIn(foreign["id"], listed_ids)
        self.assertIn(third["id"], listed_ids)
        # 兼容原契约：提前返回时 tasks 只列命中任务；本轮轮询到的总数由 task_count 表达。
        self.assertEqual([task["id"] for task in filtered["tasks"]], [third["id"]])
        self.assertEqual(filtered["matched_task_ids"], [third["id"]])
        self.assertEqual(filtered["task_count"], 3)
        self.assertEqual(filtered["tasks_returned"], 1)
        self.assertFalse(filtered["tasks_truncated"])
        self.assertEqual(filtered["tasks_omitted_count"], 0)
        self.assertEqual(filtered["omitted_task_ids"], [])
        self.assertTrue(deduped["timed_out"])
        self.assertEqual(deduped["task_ids"], [third["id"]])
        self.assertEqual(len(deduped["tasks"]), 1)
        self.assertEqual(deduped["query_stats"]["poll_rounds"], 1)
        self.assertEqual(deduped["query_stats"]["http_requests"], 1)

    def test_wait_task_references_are_capped_and_keep_traceable_ids(self):
        """输出数量上限：命中集合与超时全量都封顶，超出部分以计数 + ID 标记，不静默漏报。"""
        cap = talk_task_tools.WAIT_MAX_TASK_REFERENCES
        overflow = 3
        with LiveTalkServer(main.app) as base_url:
            tasks = [
                self._create_task(base_url, content=f"上限测试任务 {index}")
                for index in range(cap + overflow)
            ]
            all_ids = [task["id"] for task in tasks]
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                matched = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "task_ids": all_ids,
                        "workflow_statuses": ["assigned"],
                        "timeout_seconds": 0,
                    },
                )
                timed_out = dispatch_tool(
                    "talk_wait_tasks",
                    {"workflow_statuses": ["submitted"], "timeout_seconds": 0},
                )

        # 提前返回：tasks 即命中集合，命中 ID 完整可追溯，超出上限部分只以计数 + ID 标记。
        self.assertFalse(matched["timed_out"])
        self.assertEqual(matched["return_reason"], "matched")
        self.assertEqual(matched["matched_task_ids"], all_ids)
        self.assertEqual(matched["task_count"], len(all_ids))
        self.assertEqual([task["id"] for task in matched["tasks"]], all_ids[:cap])
        self.assertEqual(matched["tasks_returned"], cap)
        self.assertTrue(matched["tasks_truncated"])
        self.assertEqual(matched["tasks_omitted_count"], overflow)
        self.assertEqual(matched["omitted_task_ids"], all_ids[cap:])
        for summary in matched["tasks"]:
            self.assertEqual(set(summary), set(talk_task_tools._WAIT_TASK_REFERENCE_FIELDS))

        # 超时路径仍可摘要本轮轮询到的全部任务，但同样封顶，且被截断的 ID 不丢失。
        returned_ids = [task["id"] for task in timed_out["tasks"]]
        self.assertTrue(timed_out["timed_out"])
        self.assertEqual(timed_out["task_count"], len(all_ids))
        self.assertEqual(len(returned_ids), cap)
        self.assertEqual(len(set(returned_ids)), cap)
        self.assertTrue(timed_out["tasks_truncated"])
        self.assertEqual(timed_out["tasks_omitted_count"], overflow)
        self.assertEqual(
            sorted(returned_ids + timed_out["omitted_task_ids"]), sorted(all_ids)
        )
        self.assertEqual(
            set(timed_out["omitted_task_ids"]), set(all_ids) - set(returned_ids)
        )
        self.assertEqual(timed_out["matched_task_ids"], [])
        self.assertIn(str(cap), timed_out["tasks_note"])
        self.assertEqual(timed_out["tasks_note"], talk_task_tools.WAIT_TASKS_NOTE)
        self.assertLess(len(json.dumps(timed_out, ensure_ascii=False)), 12000)

    def test_wait_reports_permission_and_api_errors_instead_of_timeout(self):
        stats_path = self._tmpdir / "wait-error-stats.jsonl"
        with LiveTalkServer(main.app) as base_url:
            task = self._create_task(base_url)
            with patch.dict(
                os.environ,
                self._environment(base_url, "other-key", "agent:other"),
                clear=False,
            ):
                with self.assertRaises(TalkToolError) as denied:
                    dispatch_tool(
                        "talk_wait_tasks",
                        {
                            "task_ids": [task["id"]],
                            "workflow_statuses": ["submitted"],
                            "timeout_seconds": 5,
                        },
                    )
            self.assertIn("不是超时", str(denied.exception))
            self.assertIn("404", str(denied.exception))

            unreachable = self._environment(base_url, "bobo-key", "human:bobo")
            unreachable["TALK_BASE_URL"] = "http://127.0.0.1:1"
            unreachable["TALK_WAIT_STATS_FILE"] = str(stats_path)
            with patch.dict(os.environ, unreachable, clear=False):
                with self.assertRaises(TalkToolError) as broken:
                    wait_tasks(
                        project_id="prj_wait",
                        task_ids=[task["id"]],
                        workflow_statuses=["submitted"],
                        timeout_seconds=5,
                    )
        self.assertIn("不是超时", str(broken.exception))
        records = [
            json.loads(line)
            for line in stats_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual([record["return_reason"] for record in records], ["api_error"])
        self.assertFalse(records[0]["timed_out"])
        self.assertEqual(records[0]["poll_rounds"], 1)
        self.assertEqual(records[0]["http_requests"], 1)

    def test_wait_real_timeout_records_program_level_counters(self):
        stats_path = self._tmpdir / "wait-stats.jsonl"
        with LiveTalkServer(main.app) as base_url:
            task = self._create_task(base_url)
            env = self._environment(base_url, "bobo-key", "human:bobo")
            env["TALK_WAIT_STATS_FILE"] = str(stats_path)
            with patch.dict(os.environ, env, clear=False):
                started = time.monotonic()
                result = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "task_ids": [task["id"]],
                        "workflow_statuses": ["submitted", "completed", "failed"],
                        "timeout_seconds": 3,
                    },
                )
                wall = time.monotonic() - started

        record = json.loads(
            stats_path.read_text(encoding="utf-8").strip().splitlines()[-1]
        )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["return_reason"], "timeout")
        # query_stats 只保留实测计数；被移除的硬编码工具调用常量不得回归。
        self.assertEqual(
            set(result["query_stats"]),
            {"poll_rounds", "http_requests", "elapsed_seconds", "return_reason"},
        )
        for removed in ("wait_tool_calls", "get_task_tool_calls", "list_tasks_tool_calls"):
            self.assertNotIn(removed, result["query_stats"])
        self.assertIn("主控", result["counting_note"])
        self.assertGreaterEqual(wall, 2.9)
        self.assertLess(wall, 20)
        self.assertGreaterEqual(result["query_stats"]["poll_rounds"], 3)
        self.assertEqual(
            result["query_stats"]["http_requests"],
            result["query_stats"]["poll_rounds"],
        )
        self.assertEqual(record["timeout_seconds"], 3.0)
        self.assertEqual(record["return_reason"], "timeout")
        self.assertEqual(record["poll_rounds"], result["query_stats"]["poll_rounds"])
        self.assertEqual(record["http_requests"], result["query_stats"]["http_requests"])
        self.assertAlmostEqual(
            record["elapsed_seconds"],
            result["elapsed_seconds"],
            places=1,
        )
        self.assertIn("started_at", record)
        self.assertIn("finished_at", record)

    def test_wait_simulated_600_seconds_stays_bounded(self):
        """用模拟时钟走完 600 秒：轮询次数与 HTTP 数有界，不真实等待 10 分钟。"""
        clock = {"now": 1000.0}
        slept: list[float] = []

        def fake_monotonic() -> float:
            return clock["now"]

        def fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            clock["now"] += seconds

        with LiveTalkServer(main.app) as base_url:
            task = self._create_task(base_url)
            with patch.dict(
                os.environ,
                self._environment(base_url, "bobo-key", "human:bobo"),
                clear=False,
            ), patch.object(
                talk_task_tools, "_monotonic", side_effect=fake_monotonic
            ), patch.object(talk_task_tools, "_sleep", side_effect=fake_sleep):
                started = time.monotonic()
                result = dispatch_tool(
                    "talk_wait_tasks",
                    {"task_ids": [task["id"]], "workflow_statuses": ["submitted"]},
                )
                wall = time.monotonic() - started

        self.assertTrue(result["timed_out"])
        self.assertEqual(result["return_reason"], "timeout")
        self.assertEqual(result["timeout_seconds"], 600.0)
        self.assertEqual(result["elapsed_seconds"], 600.0)
        self.assertAlmostEqual(sum(slept), 600.0, places=6)
        self.assertLessEqual(max(slept), 5.0)
        self.assertEqual(result["query_stats"]["poll_rounds"], len(slept) + 1)
        self.assertEqual(
            result["query_stats"]["http_requests"],
            result["query_stats"]["poll_rounds"],
        )
        self.assertGreaterEqual(len(slept), 100)
        self.assertLess(len(slept), 300)
        self.assertLess(wall, 120)
