import asyncio
import sys
from pathlib import Path

import server.main as main
from TALK.client import TalkClient
from bridges.cli_bridge import handle_queued_task
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer


class TaskHallEndToEndTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:qa", api_key="qa-key", display_name="QA")
        self.add_member("agent:runner", api_key="runner-key", display_name="Runner")

        with self.make_client() as client:
            response = client.post(
                "/api/projects",
                headers={"X-API-Key": "qa-key"},
                json={
                    "project_id": "prj_task_hall_e2e",
                    "display_name": "Task Hall E2E",
                },
            )
        self.assertEqual(response.status_code, 201)

    def test_bundled_runner_writes_result_to_hall_and_requester_collects_it(self):
        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "qa-key") as human_client:
                created = await human_client.create_task(
                    "agent:runner",
                    "请由 bundled runner 执行并把结果写入 Task Hall。",
                    title="完整任务链",
                    project_id="prj_task_hall_e2e",
                )

            async with TalkClient(base_url, "runner-key") as runner_client:
                await runner_client.report_instance_status(
                    "e2e-runner-instance",
                    runtime="cli",
                    status="idle",
                )
                queued = await runner_client.list_tasks(
                    target_member_id="agent:runner",
                    status="queued",
                    project_id="prj_task_hall_e2e",
                )
                handled = await handle_queued_task(
                    queued[0],
                    client=runner_client,
                    member_id="agent:runner",
                    workdir=Path.cwd(),
                    instance_id="e2e-runner-instance",
                    command=[sys.executable, "-c", "print('runner-e2e-result')"],
                    preflight_command=[
                        sys.executable,
                        "-c",
                        'print(\'TALK_TASK_PREFLIGHT {"action":"accept"}\')',
                    ],
                    timeout=10,
                    max_reply_chars=2000,
                    runtime="cli",
                    bridge_label="E2E runner",
                    lease_seconds=10,
                    heartbeat_interval=0.2,
                )

            async with TalkClient(base_url, "qa-key") as human_client:
                submitted = await human_client.get_task(created["id"])
                hall_history = await human_client.fetch_history(
                    group_id=created["hall_group_id"],
                    since=0,
                )
                collected = await human_client.collect_task_result(created["id"])

            self.assertTrue(handled)
            self.assertEqual(submitted["status"], "succeeded")
            self.assertEqual(submitted["workflow_status"], "submitted")
            self.assertEqual(submitted["attempt"], 1)
            self.assertEqual(len(hall_history), 1)
            self.assertEqual(hall_history[0]["from"], "agent:runner")
            self.assertEqual(hall_history[0]["content"], "runner-e2e-result")
            self.assertEqual(submitted["result_message_id"], hall_history[0]["id"])
            self.assertEqual(collected["workflow_status"], "completed")
            self.assertIsNotNone(collected["result_collected_at"])

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_bundled_runner_clarifies_then_replays_answer_before_execution(self):
        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "qa-key") as human_client:
                created = await human_client.create_task(
                    "agent:runner",
                    "启动测试服务。",
                    title="澄清后执行",
                    project_id="prj_task_hall_e2e",
                )

            async with TalkClient(base_url, "runner-key") as runner_client:
                await runner_client.report_instance_status(
                    "e2e-clarification-runner",
                    runtime="cli",
                    status="idle",
                )
                queued = await runner_client.get_task(created["id"])
                clarified = await handle_queued_task(
                    queued,
                    client=runner_client,
                    member_id="agent:runner",
                    workdir=Path.cwd(),
                    instance_id="e2e-clarification-runner",
                    command=[sys.executable, "-c", "print('must-not-run')"],
                    preflight_command=[
                        sys.executable,
                        "-c",
                        (
                            'print(\'TALK_TASK_PREFLIGHT '
                            '{"action":"clarify","question":"请确认目标端口。"}\')'
                        ),
                    ],
                    timeout=10,
                    max_reply_chars=2000,
                    runtime="cli",
                    bridge_label="E2E runner",
                    lease_seconds=10,
                    heartbeat_interval=0.2,
                )
                waiting = await runner_client.get_task(created["id"])

            async with TalkClient(base_url, "qa-key") as human_client:
                question_history = await human_client.fetch_history(
                    group_id=created["hall_group_id"],
                    since=0,
                )
                answer = await human_client.send_text(
                    "使用 8123 端口。",
                    to=["agent:runner"],
                    group_id=created["hall_group_id"],
                )
                answered = await human_client.submit_task_clarification_answer(
                    created["id"],
                    answer_message_id=answer["id"],
                )

            async with TalkClient(base_url, "runner-key") as runner_client:
                executable = await runner_client.get_task(created["id"])
                handled = await handle_queued_task(
                    executable,
                    client=runner_client,
                    member_id="agent:runner",
                    workdir=Path.cwd(),
                    instance_id="e2e-clarification-runner",
                    command=[
                        sys.executable,
                        "-c",
                        (
                            "import sys; prompt=sys.stdin.read(); "
                            "print('context-ok' if '8123' in prompt else 'context-missing')"
                        ),
                    ],
                    preflight_command=[
                        sys.executable,
                        "-c",
                        'print(\'TALK_TASK_PREFLIGHT {"action":"accept"}\')',
                    ],
                    timeout=10,
                    max_reply_chars=2000,
                    runtime="cli",
                    bridge_label="E2E runner",
                    lease_seconds=10,
                    heartbeat_interval=0.2,
                )

            async with TalkClient(base_url, "qa-key") as human_client:
                submitted = await human_client.get_task(created["id"])
                final_history = await human_client.fetch_history(
                    group_id=created["hall_group_id"],
                    since=0,
                )

            self.assertTrue(clarified)
            self.assertEqual(waiting["workflow_status"], "clarification_requested")
            self.assertEqual(waiting["attempt"], 0)
            self.assertEqual(len(question_history), 1)
            self.assertTrue(question_history[0]["content"].startswith("【TALK 自动预检"))
            self.assertEqual(answered["workflow_status"], "clarification_answered")
            self.assertTrue(handled)
            self.assertEqual(submitted["workflow_status"], "submitted")
            self.assertEqual(submitted["attempt"], 1)
            self.assertEqual([message["from"] for message in final_history], [
                "agent:runner",
                "human:qa",
                "agent:runner",
            ])
            self.assertEqual(final_history[-1]["content"], "context-ok")

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))


if __name__ == "__main__":
    import unittest

    unittest.main()
