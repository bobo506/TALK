"""受管 CLI 的真实停止请求与异步清理边界；全部使用假凭据/本地假件。"""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridges import cli_bridge


class ManagedControlPathTests(unittest.TestCase):
    def test_legacy_or_missing_control_environment_does_not_enable_watcher(self):
        for project, launch, env in [
            (None, "launch-1", {"TALK_ROLE_SERVICE_CONTROL_FILE": "bad"}),
            ("prj", None, {"TALK_ROLE_SERVICE_CONTROL_FILE": "bad"}),
            ("prj", "launch-1", {}),
        ]:
            with self.subTest(project=project, launch=launch):
                self.assertIsNone(cli_bridge.managed_stop_control_path(project, launch, env))

    def test_managed_path_must_be_absolute_and_match_this_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            for raw in ["control/launch-1.ctl", str(Path(tmp) / "other.ctl")]:
                with self.subTest(path=raw), self.assertRaises(ValueError):
                    cli_bridge.managed_stop_control_path(
                        "prj", "launch-1", {"TALK_ROLE_SERVICE_CONTROL_FILE": raw}
                    )

    def test_host_control_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control" / "launch-1.ctl"
            self.assertEqual(
                cli_bridge.managed_stop_control_path(
                    "prj", "launch-1", {"TALK_ROLE_SERVICE_CONTROL_FILE": str(path)}
                ), path,
            )


class ManagedStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_client_runs_without_creating_stop_watcher(self):
        class Client:
            async def run(self):
                return None

        with patch.object(cli_bridge, "wait_for_managed_stop", side_effect=AssertionError):
            await cli_bridge.run_until_managed_stop(Client(), None)

    async def test_only_exact_shutdown_marker_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp) / "launch.ctl"
            waiter = asyncio.create_task(cli_bridge.wait_for_managed_stop(control, poll_interval=.01))
            try:
                for content in [b"", b"stop\n", b"shutdown\nextra", b"x" * 100]:
                    control.write_bytes(content)
                    await asyncio.sleep(.025)
                    self.assertFalse(waiter.done(), content)
                control.write_text("shutdown\n", encoding="utf-8", newline="\n")
                await asyncio.wait_for(waiter, 1)
            finally:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)

    async def test_unreadable_control_file_does_not_stop_or_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp) / "launch.ctl"
            with patch.object(Path, "open", side_effect=PermissionError("fixture")):
                waiter = asyncio.create_task(cli_bridge.wait_for_managed_stop(control, poll_interval=.01))
                await asyncio.sleep(.03)
                self.assertFalse(waiter.done())
            control.write_text("shutdown\n", encoding="utf-8", newline="\n")
            await asyncio.wait_for(waiter, 1)

    async def test_transport_failure_propagates_and_reaps_watcher(self):
        cleaned = asyncio.Event()

        async def watcher(_):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        class Client:
            async def run(self):
                await asyncio.sleep(.01)
                raise RuntimeError("transport fixture")

        with patch.object(cli_bridge, "wait_for_managed_stop", watcher):
            with self.assertRaisesRegex(RuntimeError, "transport fixture"):
                await cli_bridge.run_until_managed_stop(Client(), Path("fixture"))
        self.assertTrue(cleaned.is_set())

    async def test_external_cancellation_reaps_transport_and_watcher(self):
        cleaned = set()
        started = asyncio.Event()

        class Client:
            async def run(self):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.add("transport")

        async def watcher(_):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.add("watcher")

        with patch.object(cli_bridge, "wait_for_managed_stop", watcher):
            task = asyncio.create_task(cli_bridge.run_until_managed_stop(Client(), Path("fixture")))
            await started.wait()
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(cleaned, {"transport", "watcher"})

    async def test_bridge_stop_cancels_worker_reports_offline_and_closes_client(self):
        reports = []
        worker_started = asyncio.Event()
        worker_stopped = asyncio.Event()
        transport_stopped = asyncio.Event()
        closed = asyncio.Event()

        class Client:
            def __init__(self, *args, **kwargs):
                pass

            async def register(self, *args, **kwargs):
                pass

            def on_message(self, callback):
                return callback

            async def _request_json(self, method, path, json_body):
                reports.append(json_body)

            async def run(self):
                try:
                    await asyncio.Event().wait()
                finally:
                    transport_stopped.set()

            async def close(self):
                closed.set()

        async def worker(**kwargs):
            worker_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                worker_stopped.set()

        args = cli_bridge.build_parser().parse_args([
            "--name", "pilot", "--key", "fake-unit-key", "--command", "fixture",
            "--project-id", "prj", "--launch-id", "launch-1",
            "--process-started-at", "2026-10-17T00:00:00+00:00",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp) / "launch-1.ctl"
            with patch.dict(os.environ, {"TALK_ROLE_SERVICE_CONTROL_FILE": str(control)}), \
                    patch("TALK.client.TalkClient", Client), \
                    patch.object(cli_bridge, "configure_talk_tool_environment"), \
                    patch.object(cli_bridge, "run_task_queue_worker", worker):
                task = asyncio.create_task(cli_bridge.run_bridge(args))
                try:
                    await asyncio.wait_for(worker_started.wait(), 1)
                    control.write_text("shutdown\n", encoding="utf-8", newline="\n")
                    await asyncio.wait_for(task, 1)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(worker_stopped.is_set())
        self.assertTrue(transport_stopped.is_set())
        self.assertTrue(closed.is_set())
        self.assertEqual([x["status"] for x in reports], ["idle", "offline"])
        self.assertTrue(all(x["launch_id"] == "launch-1" for x in reports))


if __name__ == "__main__":
    unittest.main()
