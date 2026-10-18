"""真实 run_bridge 的受管心跳：保留忙碌事实、短暂断连恢复及退出清理。"""
import asyncio
import contextlib
import io
import os
import unittest
from unittest.mock import patch

from bridges import cli_bridge


class ManagedInstanceLivenessTests(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, *, managed=True, transient_failure=False, cancel=False, idle=False):
        reports = []
        attempts = []
        repeated = asyncio.Event()
        clients = []
        busy_attempts = 0
        idle_attempts = 0

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.closed = False
                clients.append(self)

            async def register(self, *args, **kwargs):
                pass

            def on_message(self, callback):
                return callback

            async def _request_json(self, method, path, *, json_body):
                nonlocal busy_attempts, idle_attempts
                self_test.assertEqual((method, path), ("PUT", "/api/instances/ins-test"))
                attempts.append(dict(json_body))
                if json_body["status"] == "busy":
                    busy_attempts += 1
                    if transient_failure and busy_attempts == 2:
                        raise OSError("sensitive exception detail")
                reports.append(dict(json_body))
                if json_body["status"] == "idle":
                    idle_attempts += 1
                if busy_attempts >= 3 or (idle and idle_attempts >= 3):
                    repeated.set()

            async def report_instance_status(self, *args, **kwargs):
                reports.append(kwargs)

            async def run(self):
                if managed:
                    await asyncio.wait_for(repeated.wait(), timeout=1)
                if cancel:
                    raise asyncio.CancelledError

            async def close(self):
                self.closed = True

        async def busy_worker(*, report_status, **kwargs):
            await report_status("busy", current_task_id="42", last_error="preserved")
            await asyncio.Event().wait()

        self_test = self
        args = cli_bridge.build_parser().parse_args([
            "--key", "fixture-key", "--command", "fixture-command", "--name", "fixture",
            "--instance-id", "ins-test",
            *(["--launch-id", "launch-test", "--project-id", "prj-test"] if managed else []),
            *(["--disable-task-queue"] if idle or not managed else []),
        ])
        output = io.StringIO()
        with patch.dict(os.environ), patch("TALK.client.TalkClient", FakeClient), \
                patch.object(cli_bridge, "MANAGED_INSTANCE_HEARTBEAT_INTERVAL", .005, create=True), \
                patch.object(cli_bridge, "run_task_queue_worker", busy_worker), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            if cancel:
                with self.assertRaises(asyncio.CancelledError):
                    await cli_bridge.run_bridge(args)
            else:
                await cli_bridge.run_bridge(args)
            finished_count = len(reports)
            await asyncio.sleep(.02)
            self.assertEqual(len(reports), finished_count, "退出后不能继续心跳或覆盖 offline")
        self.assertTrue(clients[0].closed)
        self.assertEqual(reports[-1]["status"], "offline")
        self.assertEqual(sum(row["status"] == "offline" for row in reports), 1)
        self.assertNotIn("sensitive exception detail", output.getvalue())
        return reports, attempts

    async def test_periodic_managed_heartbeat_preserves_task_and_status(self):
        reports, _ = await self.scenario()
        busy = [row for row in reports if row["status"] == "busy"]
        self.assertGreaterEqual(len(busy), 3)
        for row in busy:
            self.assertEqual((row["current_task_id"], row["last_error"]), ("42", "preserved"))
            self.assertEqual((row["project_id"], row["launch_id"]), ("prj-test", "launch-test"))

    async def test_transient_failure_retries_without_stopping_transport(self):
        reports, attempts = await self.scenario(transient_failure=True)
        self.assertGreater(len(attempts), len(reports))

    async def test_idle_managed_bridge_also_sends_periodic_heartbeats(self):
        reports, _ = await self.scenario(idle=True)
        self.assertGreaterEqual(sum(row["status"] == "idle" for row in reports), 3)
        self.assertTrue(all(row["current_task_id"] is None for row in reports))

    async def test_cancellation_stops_heartbeat_and_reports_offline(self):
        await self.scenario(cancel=True)

    async def test_unmanaged_bridge_keeps_event_only_reporting(self):
        reports, attempts = await self.scenario(managed=False)
        self.assertEqual(attempts, [])
        self.assertEqual([row["status"] for row in reports], ["idle", "offline"])
