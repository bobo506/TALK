import json
import os
import subprocess
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import httpx

import server.main as main
from bridges.cli_bridge import configure_talk_tool_environment
from bridges.talk_task_tools import dispatch_tool
from cli.talk import scaffold_project
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer


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
            process = subprocess.run(
                [sys.executable, str(Path("bridges/talk_send_mcp.py").resolve())],
                input=requests,
                capture_output=True,
                text=True,
                encoding="utf-8",
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
