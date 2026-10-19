"""接单轮询诊断的真实 worker 调用链测试（假 TALK 客户端/真实诊断写入）。"""

from __future__ import annotations

import asyncio
import contextlib
import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bridges import cli_bridge
from bridges import queue_poll_diagnostics as qpd
from bridges import runtime_diagnostics as runtime_diag


PROJECT = "prj_qp_worker"
MEMBER = "agent:qp-worker"
INSTANCE = "agent:qp-worker:test"
WALL_START = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
EXPECTED_KEYS = {
    "poll_seq",
    "state",
    "started_at",
    "finished_at",
    "duration_ms",
    "last_success_at",
    "last_failure_at",
    "failure_streak_started_at",
    "consecutive_failures",
    "recovered_failures",
    "error_log_id",
    "interval_seconds",
}


class FakeClock:
    def __init__(self) -> None:
        self.wall = WALL_START
        self.monotonic = 0.0

    def now(self):
        return self.wall

    def mono(self):
        return self.monotonic

    def advance(self, seconds: float) -> None:
        self.wall = self.wall + timedelta(seconds=seconds)
        self.monotonic += seconds


def make_args(**overrides):
    values = {
        "command": "fake-command",
        "task_command": "fake-task-command",
        "task_preflight_command": "fake-preflight-command",
        "timeout": 5,
        "max_reply_chars": 300,
        "runtime": "dsh",
        "bridge_label": "fake bridge",
        "prompt_transport": "argv",
        "decision_tier": None,
        "task_lease_seconds": 30,
        "task_heartbeat_interval": 1,
        "task_poll_interval": 0,
        "task_preflight_max_attempts": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_writer(root: Path, clock: FakeClock) -> runtime_diag.RuntimeDiagnostics:
    return runtime_diag.RuntimeDiagnostics(
        member_id=MEMBER,
        instance_id=INSTANCE,
        root=root,
        project_id=PROJECT,
        launch_id="launch-qp-worker",
        runtime="dsh",
        clock=clock.now,
    )


def read_events(root: Path, event: str | None = None) -> list[dict]:
    result = runtime_diag.query_records(root, event=event, limit=200)
    records = result["records"]
    return sorted(records, key=lambda item: (item["recorded_at"], item["log_id"]))


async def run_worker(client, writer, args, report_status=None) -> None:
    try:
        await cli_bridge.run_task_queue_worker(
            client=client,
            member_id=MEMBER,
            workdir=Path.cwd(),
            instance_id=INSTANCE,
            args=args,
            run_lock=asyncio.Lock(),
            report_status=report_status,
            diagnostics=writer,
        )
    except asyncio.CancelledError:
        return


class IdleRateLimitClient:
    def __init__(self, clock: FakeClock, limit: int) -> None:
        self.clock = clock
        self.limit = limit
        self.calls = 0

    async def requeue_expired_tasks(self):
        return []

    async def list_tasks(self, **kwargs):
        self.calls += 1
        if self.calls > self.limit:
            raise asyncio.CancelledError
        self.clock.advance(10)
        return []


class FailureRecoveryClient:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls = 0

    async def requeue_expired_tasks(self):
        return []

    async def list_tasks(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            self.clock.advance(1)
            raise RuntimeError("query failure one")
        if self.calls == 2:
            self.clock.advance(1)
            raise RuntimeError("query failure two")
        if self.calls == 3:
            self.clock.advance(1)
            return []
        if self.calls == 4:
            self.clock.advance(40)
            return []
        if self.calls == 5:
            self.clock.advance(1)
            return []
        raise asyncio.CancelledError


class QueuePollWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="queue-poll-worker-")
        self.root = Path(self._temp.name) / "runtime"
        self.root.mkdir()
        self.clock = FakeClock()

    def tearDown(self) -> None:
        self._temp.cleanup()

    async def test_idle_rate_limit_and_real_poll_sequence(self) -> None:
        writer = make_writer(self.root, self.clock)
        client = IdleRateLimitClient(self.clock, limit=5)
        with patch.object(qpd, "utc_now", self.clock.now), patch.object(
            qpd, "monotonic_now", self.clock.mono
        ):
            await run_worker(client, writer, make_args())

        started = read_events(self.root, "queue_started")
        stopped = read_events(self.root, "queue_stopped")
        snapshots = read_events(self.root, "queue_poll_snapshot")
        self.assertEqual(len(started), 1)
        self.assertEqual(len(stopped), 1)
        self.assertIn("cancelled", stopped[0]["message"])

        states = [item["extra"]["queue_poll"]["state"] for item in snapshots]
        self.assertIn("started", states)
        self.assertIn("succeeded", states)
        self.assertIn("canceled", states)
        successes = [
            item
            for item in snapshots
            if item["extra"]["queue_poll"]["state"] == "succeeded"
        ]
        starts = [
            item for item in snapshots if item["extra"]["queue_poll"]["state"] == "started"
        ]
        self.assertEqual([item["extra"]["queue_poll"]["poll_seq"] for item in successes], [1, 5])
        self.assertEqual(
            [item["extra"]["queue_poll"]["poll_seq"] for item in starts],
            [1, 5, 6],
        )
        for item in snapshots:
            self.assertEqual(set(item["extra"]["queue_poll"]), EXPECTED_KEYS)
            self.assertEqual(item["phase"], "queue")
        sequence = sorted({item["extra"]["queue_poll"]["poll_seq"] for item in snapshots})
        self.assertEqual(sequence, [1, 5, 6])
        self.assertEqual(client.calls, 6)
        first_start = datetime.fromisoformat(
            successes[0]["extra"]["queue_poll"]["started_at"].replace("Z", "+00:00")
        )
        second_start = datetime.fromisoformat(
            successes[1]["extra"]["queue_poll"]["started_at"].replace("Z", "+00:00")
        )
        self.assertGreaterEqual((second_start - first_start).total_seconds(), 30)
        self.assertEqual(
            snapshots[-1]["extra"]["queue_poll"]["state"], "canceled"
        )

    async def test_query_failures_recover_once_and_keep_exception_links(self) -> None:
        writer = make_writer(self.root, self.clock)
        client = FailureRecoveryClient(self.clock)
        reports: list[tuple[str, dict]] = []

        async def report_status(status, **kwargs):
            reports.append((status, kwargs))

        with patch.object(qpd, "utc_now", self.clock.now), patch.object(
            qpd, "monotonic_now", self.clock.mono
        ):
            await run_worker(client, writer, make_args(), report_status=report_status)

        exceptions = read_events(self.root, "queue_worker_exception")
        failed = [
            item
            for item in read_events(self.root, "queue_poll_snapshot")
            if item["extra"]["queue_poll"]["state"] == "failed"
        ]
        recovered = read_events(self.root, "queue_poll_recovered")
        success = [
            item
            for item in read_events(self.root, "queue_poll_snapshot")
            if item["extra"]["queue_poll"]["state"] == "succeeded"
        ]
        self.assertEqual(len(exceptions), 2)
        self.assertEqual(len(failed), 2)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(len(success), 1)
        self.assertEqual(len(reports), 2)
        self.assertEqual(exceptions[0]["exception"]["type"], "RuntimeError")
        self.assertEqual(exceptions[0]["exception"]["message"], "query failure one")
        self.assertEqual(
            failed[0]["extra"]["queue_poll"]["error_log_id"], exceptions[0]["log_id"]
        )
        self.assertEqual(
            failed[1]["extra"]["queue_poll"]["error_log_id"], exceptions[0]["log_id"]
        )
        self.assertEqual(
            [item["extra"]["queue_poll"]["consecutive_failures"] for item in failed],
            [1, 2],
        )
        self.assertEqual(
            failed[1]["extra"]["queue_poll"]["failure_streak_started_at"],
            failed[0]["extra"]["queue_poll"]["failure_streak_started_at"],
        )
        recovery = recovered[0]["extra"]["queue_poll"]
        self.assertEqual(recovery["poll_seq"], 3)
        self.assertEqual(recovery["recovered_failures"], 2)
        self.assertEqual(recovery["consecutive_failures"], 0)
        self.assertEqual(
            recovery["failure_streak_started_at"],
            failed[0]["extra"]["queue_poll"]["failure_streak_started_at"],
        )
        self.assertEqual(
            recovery["last_failure_at"], failed[1]["extra"]["queue_poll"]["finished_at"]
        )
        self.assertEqual(recovery["error_log_id"], exceptions[0]["log_id"])
        self.assertEqual(recovery["last_success_at"], recovery["finished_at"])
        normal = success[0]["extra"]["queue_poll"]
        self.assertEqual(normal["poll_seq"], 5)
        self.assertEqual(normal["recovered_failures"], 0)
        self.assertIsNone(normal["failure_streak_started_at"])
        self.assertEqual(len(read_events(self.root, "queue_poll_recovered")), 1)

    async def test_requeue_failure_counts_and_recovers(self) -> None:
        writer = make_writer(self.root, self.clock)

        class Client:
            def __init__(self):
                self.requeue_calls = 0
                self.list_calls = 0

            async def requeue_expired_tasks(self):
                self.requeue_calls += 1
                if self.requeue_calls == 1:
                    raise RuntimeError("requeue failure")

            async def list_tasks(self, **kwargs):
                self.list_calls += 1
                if self.list_calls == 1:
                    return []
                raise asyncio.CancelledError

        with patch.object(qpd, "utc_now", self.clock.now), patch.object(
            qpd, "monotonic_now", self.clock.mono
        ):
            await run_worker(Client(), writer, make_args())

        failed = [
            item
            for item in read_events(self.root, "queue_poll_snapshot")
            if item["extra"]["queue_poll"]["state"] == "failed"
        ]
        recovered = read_events(self.root, "queue_poll_recovered")
        exceptions = read_events(self.root, "queue_worker_exception")
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0]["exception"]["message"], "requeue failure")
        self.assertEqual(
            failed[0]["extra"]["queue_poll"]["error_log_id"], exceptions[0]["log_id"]
        )
        self.assertEqual(recovered[0]["extra"]["queue_poll"]["recovered_failures"], 1)

    async def test_filter_or_sort_failure_counts_and_recovers(self) -> None:
        writer = make_writer(self.root, self.clock)

        class Client:
            def __init__(self):
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return [{"id": "not-an-integer", "workflow_status": "assigned"}]
                if self.calls == 2:
                    return []
                raise asyncio.CancelledError

        with patch.object(qpd, "utc_now", self.clock.now), patch.object(
            qpd, "monotonic_now", self.clock.mono
        ):
            await run_worker(Client(), writer, make_args())

        failed = [
            item
            for item in read_events(self.root, "queue_poll_snapshot")
            if item["extra"]["queue_poll"]["state"] == "failed"
        ]
        recovered = read_events(self.root, "queue_poll_recovered")
        exceptions = read_events(self.root, "queue_worker_exception")
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(len(exceptions), 1)
        self.assertTrue(exceptions[0]["exception"]["type"].endswith("ValueError"))
        self.assertEqual(
            failed[0]["extra"]["queue_poll"]["error_log_id"], exceptions[0]["log_id"]
        )

    async def test_long_task_wait_does_not_advance_poll_sequence(self) -> None:
        writer = make_writer(self.root, self.clock)

        class Client:
            def __init__(self):
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return [{"id": 12, "workflow_status": "assigned"}]
                raise asyncio.CancelledError

        async def slow_task(task, **kwargs):
            # Model/lock execution consumes wall and monotonic time, but no new
            # query starts until the worker actually loops again.
            self.clock.advance(45)
            return True

        with patch.object(cli_bridge, "handle_queued_task", slow_task), patch.object(
            qpd, "utc_now", self.clock.now
        ), patch.object(qpd, "monotonic_now", self.clock.mono):
            await run_worker(Client(), writer, make_args())

        snapshots = [
            item["extra"]["queue_poll"]
            for item in read_events(self.root, "queue_poll_snapshot")
        ]
        sequence = sorted({item["poll_seq"] for item in snapshots})
        self.assertEqual(sequence, [1, 2])
        self.assertEqual(
            [item["state"] for item in snapshots if item["poll_seq"] == 1],
            ["started", "succeeded"],
        )
        self.assertEqual(
            [item["state"] for item in snapshots if item["poll_seq"] == 2],
            ["started", "canceled"],
        )

    async def test_task_execution_exception_is_not_a_query_failure(self) -> None:
        writer = make_writer(self.root, self.clock)

        class Client:
            def __init__(self):
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return [{"id": 12, "workflow_status": "assigned"}]
                raise asyncio.CancelledError

        async def boom(task, **kwargs):
            raise RuntimeError("runner boom")

        with patch.object(cli_bridge, "handle_queued_task", boom), patch.object(
            qpd, "utc_now", self.clock.now
        ), patch.object(qpd, "monotonic_now", self.clock.mono):
            with contextlib.redirect_stderr(io.StringIO()):
                await run_worker(Client(), writer, make_args())

        snapshots = [
            item["extra"]["queue_poll"]
            for item in read_events(self.root, "queue_poll_snapshot")
        ]
        self.assertEqual([item["state"] for item in snapshots].count("failed"), 0)
        succeeded = [item for item in snapshots if item["state"] == "succeeded"]
        self.assertEqual(len(succeeded), 1)
        self.assertEqual(succeeded[0]["poll_seq"], 1)
        self.assertEqual(succeeded[0]["consecutive_failures"], 0)
        exceptions = read_events(self.root, "queue_worker_exception")
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0]["exception"]["message"], "runner boom")
        self.assertEqual(read_events(self.root, "queue_poll_recovered"), [])

    async def test_preflight_failure_is_not_a_query_failure(self) -> None:
        writer = make_writer(self.root, self.clock)

        class Client:
            def __init__(self):
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return [{"id": 12, "workflow_status": "assigned"}]
                raise asyncio.CancelledError

        async def preflight_failure(task, **kwargs):
            raise cli_bridge.TaskPreflightError("invalid preflight envelope")

        reports: list[tuple[str, dict]] = []

        async def report_status(status, **kwargs):
            reports.append((status, kwargs))
            return None

        with patch.object(
            cli_bridge, "handle_queued_task", preflight_failure
        ), patch.object(qpd, "utc_now", self.clock.now), patch.object(
            qpd, "monotonic_now", self.clock.mono
        ):
            await run_worker(
                Client(), writer, make_args(task_preflight_max_attempts=2),
                report_status=report_status,
            )

        snapshots = [
            item["extra"]["queue_poll"]
            for item in read_events(self.root, "queue_poll_snapshot")
        ]
        self.assertEqual([item["state"] for item in snapshots].count("failed"), 0)
        succeeded = [item for item in snapshots if item["state"] == "succeeded"]
        self.assertEqual(len(succeeded), 1)
        self.assertEqual(succeeded[0]["poll_seq"], 1)
        self.assertEqual(succeeded[0]["consecutive_failures"], 0)
        preflight = read_events(self.root, "preflight_failed")
        self.assertEqual(len(preflight), 1)
        self.assertTrue(
            preflight[0]["exception"]["type"].endswith("TaskPreflightError")
        )
        # The bounded preflight attempt reports "error", but the query succeeded.
        self.assertEqual(reports[-1][0], "error")
        self.assertEqual(read_events(self.root, "queue_poll_recovered"), [])

    async def test_secondary_status_failure_preserves_queue_poll_failure(self) -> None:
        writer = make_writer(self.root, self.clock)

        class Client:
            def __init__(self):
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("query failure")
                raise asyncio.CancelledError

        async def report_status(status, **kwargs):
            if status == "error":
                raise RuntimeError("status channel down")
            return None

        with patch.object(qpd, "utc_now", self.clock.now), patch.object(
            qpd, "monotonic_now", self.clock.mono
        ):
            with contextlib.redirect_stderr(io.StringIO()):
                await run_worker(Client(), writer, make_args(), report_status=report_status)

        primary = read_events(self.root, "queue_worker_exception")
        secondary = read_events(self.root, "secondary_failure")
        failed = [
            item
            for item in read_events(self.root, "queue_poll_snapshot")
            if item["extra"]["queue_poll"]["state"] == "failed"
        ]
        self.assertEqual(len(primary), 1)
        self.assertEqual(len(secondary), 1)
        self.assertEqual(secondary[0]["related_log_id"], primary[0]["log_id"])
        self.assertEqual(len(failed), 1)
        self.assertEqual(
            failed[0]["extra"]["queue_poll"]["error_log_id"], primary[0]["log_id"]
        )

    async def test_queue_poll_write_failure_does_not_break_worker(self) -> None:
        inner = make_writer(self.root, self.clock)

        class FailingQueuePollWriter:
            def __init__(self, wrapped):
                self._wrapped = wrapped

            def __getattr__(self, name):
                return getattr(self._wrapped, name)

            def record_event(self, event, **kwargs):
                if event.startswith("queue_poll_"):
                    raise RuntimeError("queue poll log down")
                return self._wrapped.record_event(event, **kwargs)

            def record_exception(self, exc, **kwargs):
                return self._wrapped.record_exception(exc, **kwargs)

        class Client:
            def __init__(self):
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("query failure")
                raise asyncio.CancelledError

        writer = FailingQueuePollWriter(inner)
        with patch.object(qpd, "utc_now", self.clock.now), patch.object(
            qpd, "monotonic_now", self.clock.mono
        ):
            await run_worker(Client(), writer, make_args())

        self.assertEqual(len(read_events(self.root, "queue_worker_exception")), 1)
        self.assertEqual(len(read_events(self.root, "queue_stopped")), 1)
        self.assertEqual(read_events(self.root, "queue_poll_snapshot"), [])

    async def test_no_diagnostics_still_runs_and_stops(self) -> None:
        class Client:
            def __init__(self):
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("query failure")
                raise asyncio.CancelledError

        reports: list[str] = []

        async def report_status(status, **kwargs):
            reports.append(status)
            return None

        await run_worker(Client(), None, make_args(), report_status=report_status)
        self.assertEqual(reports, ["error"])

    async def test_two_worker_instances_each_start_at_one(self) -> None:
        roots = []
        sequences = []
        for index in range(2):
            root = Path(self._temp.name) / f"runtime-{index}"
            root.mkdir()
            roots.append(root)
            clock = FakeClock()
            writer = make_writer(root, clock)

            class Client:
                def __init__(self):
                    self.calls = 0

                async def requeue_expired_tasks(self):
                    return []

                async def list_tasks(self, **kwargs):
                    self.calls += 1
                    if self.calls == 1:
                        return []
                    raise asyncio.CancelledError

            with patch.object(qpd, "utc_now", clock.now), patch.object(
                qpd, "monotonic_now", clock.mono
            ):
                await run_worker(Client(), writer, make_args())
            snapshots = read_events(root, "queue_poll_snapshot")
            sequences.append(
                sorted(
                    {
                        item["extra"]["queue_poll"]["poll_seq"]
                        for item in snapshots
                    }
                )
            )
        self.assertEqual(sequences, [[1, 2], [1, 2]])


if __name__ == "__main__":
    unittest.main()
