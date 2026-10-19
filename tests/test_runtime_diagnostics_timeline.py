"""276 阶段时间线助手的隔离测试。"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from bridges import runtime_diagnostics as runtime_diag
from bridges.runtime_diagnostics_timeline import StageTimeline, timed_lock

BASE = datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc)


class _FakeWriter:
    def __init__(self, *, fail: bool = False):
        self.records: list[dict] = []
        self.fail = fail

    def record_event(self, event: str, **kwargs):
        if self.fail:
            raise RuntimeError("diagnostics writer down")
        self.records.append({"event": event, **kwargs})
        return f"log-{len(self.records):04d}"


class TimelineUnitTests(unittest.TestCase):
    def test_pairing_monotonic_duration_attempt_and_phase(self) -> None:
        wall = [BASE, BASE + timedelta(milliseconds=250)]
        mono = [10.0, 10.25]
        writer = _FakeWriter()
        timeline = StageTimeline(
            writer,
            wall_clock=lambda: wall.pop(0),
            monotonic=lambda: mono.pop(0),
        )
        operation = timeline.start(
            "task_model_preflight",
            phase="task_preflight",
            task_id=276,
            attempt=2,
            budgets={"cli_timeout_seconds": 5},
        )
        operation.finish("succeeded", returncode=0, timeout=False)

        self.assertEqual(len(writer.records), 2)
        started, finished = writer.records
        self.assertEqual(started["event"], "task_model_preflight_started")
        self.assertEqual(finished["event"], "task_model_preflight_finished")
        self.assertEqual(started["task_id"], 276)
        self.assertEqual(started["phase"], "task_preflight")
        self.assertEqual(started["budgets"]["cli_timeout_seconds"], 5)
        transition = started["extra"]["transition"]
        final = finished["extra"]["transition"]
        self.assertEqual(transition["operation_id"], final["operation_id"])
        self.assertEqual(transition["status"], "started")
        self.assertIsNone(transition["finished_at"])
        self.assertIsNone(transition["duration_ms"])
        self.assertEqual(transition["attempt"], 2)
        self.assertEqual(final["status"], "succeeded")
        self.assertEqual(final["duration_ms"], 250.0)
        self.assertEqual(final["attempt"], 2)
        self.assertEqual(final["started_at"], transition["started_at"])
        self.assertEqual(finished["returncode"], 0)
        self.assertFalse(finished["timeout"])

    def test_failure_and_cancellation_statuses_are_distinct(self) -> None:
        writer = _FakeWriter()
        timeline = StageTimeline(writer)
        failed = timeline.start("task_cli", phase="task", task_id=1)
        failed.finish("failed", returncode=2, timeout=False)
        canceled = timeline.start("task_cli", phase="task", task_id=2)
        canceled.finish("canceled")
        unknown = timeline.start("task_cli", phase="task", task_id=3)
        unknown.finish("not-a-status")

        statuses = [
            record["extra"]["transition"]["status"] for record in writer.records[1::2]
        ]
        self.assertEqual(statuses, ["failed", "canceled", "unknown"])
        self.assertEqual(
            writer.records[3]["cancel_category"], "asyncio_cancelled"
        )
        self.assertTrue(writer.records[1]["extra"]["transition"]["duration_ms"] >= 0)

    def test_attempt_is_not_shared_between_operations(self) -> None:
        writer = _FakeWriter()
        timeline = StageTimeline(writer)
        first = timeline.start("task_model_preflight", attempt=1)
        first.finish("failed")
        second = timeline.start("task_model_preflight", attempt=2)
        second.finish("succeeded")
        attempts = [
            record["extra"]["transition"]["attempt"] for record in writer.records
        ]
        operation_ids = [
            record["extra"]["transition"]["operation_id"] for record in writer.records
        ]
        self.assertEqual(attempts, [1, 1, 2, 2])
        self.assertNotEqual(operation_ids[0], operation_ids[2])

    def test_writer_failure_never_replaces_business_exception_or_cancellation(self) -> None:
        writer = _FakeWriter(fail=True)
        timeline = StageTimeline(writer)
        operation = timeline.start("task_cli", phase="task", task_id=9)
        with self.assertRaisesRegex(RuntimeError, "business"):
            try:
                raise RuntimeError("business")
            except RuntimeError:
                operation.finish("failed")
                raise
        self.assertIsNone(operation._start_log_id)
        self.assertIsNone(operation._finish_log_id)
        self.assertEqual(writer.records, [])

        canceled = timeline.start("task_cli", phase="task", task_id=10)
        with self.assertRaises(asyncio.CancelledError):
            try:
                raise asyncio.CancelledError
            except asyncio.CancelledError:
                canceled.finish("canceled")
                raise

    def test_abandon_keeps_idle_poll_out_of_the_timeline(self) -> None:
        writer = _FakeWriter()
        operation = StageTimeline(writer).begin("task_discovery", phase="queue")
        operation.abandon()
        operation.finish("succeeded")
        self.assertEqual(writer.records, [])

    def test_stage_and_phase_are_bounded_identifiers(self) -> None:
        writer = _FakeWriter()
        timeline = StageTimeline(writer)
        operation = timeline.start("../bad stage", phase="task/preflight")
        operation.finish("succeeded")
        self.assertEqual(writer.records[0]["stage"], "bad_stage")
        self.assertEqual(writer.records[0]["phase"], "task_preflight")


class TimelineIntegrationTests(unittest.TestCase):
    def test_records_are_persisted_with_real_writer_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            writer = runtime_diag.RuntimeDiagnostics(
                member_id="agent:timeline-test",
                instance_id="ins_timeline",
                root=root,
                project_id="prj_timeline",
                launch_id="launch-timeline",
                runtime="dsh",
            )
            operation = StageTimeline(writer).start(
                "task_result_send",
                phase="task",
                task_id=42,
                budgets={"http_timeout_seconds": 15},
            )
            operation.finish("succeeded")
            files = list(root.rglob("events-*.jsonl"))
            self.assertEqual(len(files), 1)
            rows = [
                json.loads(line)
                for line in files[0].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["schema"], runtime_diag.SCHEMA)
            self.assertEqual(rows[0]["event"], "task_result_send_started")
            self.assertEqual(rows[1]["event"], "task_result_send_finished")
            self.assertEqual(
                rows[0]["extra"]["transition"]["operation_id"],
                rows[1]["extra"]["transition"]["operation_id"],
            )
            self.assertEqual(rows[0]["task_id"], 42)
            self.assertEqual(rows[0]["instance_id"], "ins_timeline")
            self.assertEqual(rows[0]["launch_id"], "launch-timeline")
            self.assertEqual(rows[0]["budgets"]["http_timeout_seconds"], 15)
            self.assertNotIn("message", rows[0])


class AsyncLockTimelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_lock_wait_is_recorded_and_lock_is_released(self) -> None:
        writer = _FakeWriter()
        timeline = StageTimeline(writer)
        lock = asyncio.Lock()
        await lock.acquire()
        entered = asyncio.Event()

        async def worker():
            async with timed_lock(
                lock,
                timeline=timeline,
                stage="task_lock_wait",
                phase="queue",
                task_id=7,
            ):
                entered.set()

        task = asyncio.create_task(worker())
        await asyncio.sleep(0.02)
        self.assertFalse(entered.is_set())
        lock.release()
        await asyncio.wait_for(task, timeout=2)
        self.assertTrue(entered.is_set())
        self.assertFalse(lock.locked())
        statuses = [
            record["extra"]["transition"]["status"] for record in writer.records
        ]
        self.assertEqual(statuses, ["started", "succeeded"])
        self.assertEqual(writer.records[0]["task_id"], 7)

    async def test_canceled_lock_wait_is_recorded(self) -> None:
        writer = _FakeWriter()
        timeline = StageTimeline(writer)
        lock = asyncio.Lock()
        await lock.acquire()

        async def worker():
            async with timed_lock(
                lock,
                timeline=timeline,
                stage="task_lock_wait",
                phase="queue",
                task_id=8,
            ):
                pass

        task = asyncio.create_task(worker())
        await asyncio.sleep(0.02)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        lock.release()
        statuses = [
            record["extra"]["transition"]["status"] for record in writer.records
        ]
        self.assertEqual(statuses, ["started", "canceled"])


class _BridgeClient:
    timeout = 10.0

    def __init__(self):
        self.claimed = []
        self.completed = []
        self.sent = []
        self.accepted = 0
        self.claimed_leases = []

    async def fetch_history(self, group_id, before=None, limit=500):
        return []

    async def accept_task(self, task_id):
        self.accepted += 1
        return {
            "id": task_id,
            "content": "do the task",
            "created_by": "human:test",
            "hall_group_id": "group:task-1",
            "workflow_status": "accepted",
        }

    async def get_task(self, task_id):
        return {
            "id": task_id,
            "content": "do the task",
            "created_by": "human:test",
            "hall_group_id": "group:task-1",
            "workflow_status": "accepted",
        }

    async def request_task_clarification(self, task_id, *, question_message_id):
        return {"id": task_id}

    async def claim_task(self, task_id, *, instance_id=None, lease_seconds=120):
        self.claimed.append(task_id)
        self.claimed_leases.append(lease_seconds)
        return {
            "id": task_id,
            "content": "do the task",
            "created_by": "human:test",
            "claim_token": "fake-claim-token",
            "hall_group_id": "group:task-1",
            "task_kind": "general",
        }

    async def heartbeat_task(self, task_id, *, claim_token, lease_seconds=120):
        return {}

    async def send_text(self, text, to=None, group_id=None):
        self.sent.append((text, to, group_id))
        return {"id": 900 + len(self.sent)}

    async def complete_task(self, task_id, **kwargs):
        self.completed.append((task_id, kwargs))
        return {"id": task_id}


class BridgeStageIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.diagnostics = runtime_diag.RuntimeDiagnostics(
            member_id="agent:stage-test",
            instance_id="ins_stage",
            root=self.root,
            project_id="prj_stage",
            launch_id="launch-stage",
            runtime="dsh",
        )

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _records(self) -> list[dict]:
        rows = []
        for path in self.root.rglob("events-*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def _operations(self) -> dict[str, dict]:
        by_id: dict[str, dict] = {}
        for row in self._records():
            transition = (row.get("extra") or {}).get("transition")
            if not transition:
                continue
            by_id.setdefault(transition["operation_id"], []).append(row)
        return by_id

    def _run(self, *, runner, task_id: int = 276, preflight_attempt: int = 1):
        from bridges import cli_bridge

        async def scenario():
            client = _BridgeClient()
            handled = await cli_bridge.handle_queued_task(
                {
                    "id": task_id,
                    "workflow_status": "assigned",
                    "content": "do the task",
                    "hall_group_id": "group:task-1",
                },
                client=client,
                member_id="agent:stage-test",
                workdir=Path.cwd(),
                instance_id="ins_stage",
                command=["task"],
                preflight_command=["preflight"],
                timeout=5,
                max_reply_chars=300,
                runtime="dsh",
                bridge_label="stage bridge",
                lease_seconds=30,
                heartbeat_interval=1,
                diagnostics=self.diagnostics,
                preflight_attempt=preflight_attempt,
                command_runner=runner,
            )
            return handled, client

        return asyncio.run(scenario())

    def test_success_path_records_all_stage_pairs(self) -> None:
        from bridges.cli_bridge import CliRunResult

        async def runner(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            if command == ["preflight"]:
                return CliRunResult(
                    returncode=0,
                    stdout='TALK_TASK_PREFLIGHT {"action":"accept"}',
                    stderr="",
                )
            return CliRunResult(returncode=0, stdout="finished", stderr="")

        handled, client = self._run(runner=runner)
        self.assertTrue(handled)
        self.assertEqual(client.completed[0][1]["status"], "succeeded")
        operations = self._operations()
        starts = {
            row["stage"]: row
            for rows in operations.values()
            for row in rows
            if row["event"].endswith("_started")
        }
        for stage in (
            "task_model_preflight",
            "task_accept",
            "task_claim",
            "task_cli",
            "task_result_send",
            "task_complete",
        ):
            self.assertIn(stage, starts)
        for operation_id, rows in operations.items():
            self.assertEqual(len(rows), 2, operation_id)
            statuses = [row["extra"]["transition"]["status"] for row in rows]
            self.assertEqual(statuses[0], "started")
            self.assertIn(statuses[1], {
                "succeeded",
                "failed",
                "canceled",
                "interrupted",
                "unknown",
            })
            self.assertEqual(rows[0]["stage"], rows[1]["stage"])
            self.assertGreaterEqual(
                rows[1]["extra"]["transition"]["duration_ms"], 0
            )

    def test_nonzero_and_timeout_are_failed_cli_stages(self) -> None:
        from bridges.cli_bridge import CliRunResult

        async def nonzero_runner(
            command, prompt, *, cwd, timeout, prompt_transport="stdin"
        ):
            if command == ["preflight"]:
                return CliRunResult(
                    returncode=0,
                    stdout='TALK_TASK_PREFLIGHT {"action":"accept"}',
                    stderr="",
                )
            return CliRunResult(returncode=3, stdout="", stderr="failed")

        self._run(runner=nonzero_runner, task_id=301)
        cli_rows = [
            row
            for row in self._records()
            if row["stage"] == "task_cli" and row["event"].endswith("_finished")
        ]
        self.assertTrue(cli_rows)
        self.assertEqual(cli_rows[0]["extra"]["transition"]["status"], "failed")
        self.assertEqual(cli_rows[0]["returncode"], 3)
        self.assertFalse(cli_rows[0]["timeout"])

        async def timeout_runner(
            command, prompt, *, cwd, timeout, prompt_transport="stdin"
        ):
            if command == ["preflight"]:
                return CliRunResult(
                    returncode=0,
                    stdout='TALK_TASK_PREFLIGHT {"action":"accept"}',
                    stderr="",
                )
            return CliRunResult(
                returncode=-1, stdout="", stderr="", timed_out=True
            )

        self._run(runner=timeout_runner, task_id=302)
        timeout_rows = [
            row
            for row in self._records()
            if row["stage"] == "task_cli"
            and row["event"].endswith("_finished")
            and row["task_id"] == 302
        ]
        self.assertTrue(timeout_rows)
        self.assertEqual(timeout_rows[0]["extra"]["transition"]["status"], "failed")
        self.assertTrue(timeout_rows[0]["timeout"])

    def test_cancellation_marks_cli_canceled_and_propagates(self) -> None:
        from bridges.cli_bridge import CliRunResult

        async def runner(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            if command == ["preflight"]:
                return CliRunResult(
                    returncode=0,
                    stdout='TALK_TASK_PREFLIGHT {"action":"accept"}',
                    stderr="",
                )
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            self._run(runner=runner, task_id=303)
        canceled = [
            row
            for row in self._records()
            if row["stage"] == "task_cli" and row["event"].endswith("_finished")
        ]
        self.assertTrue(canceled)
        self.assertEqual(canceled[0]["extra"]["transition"]["status"], "canceled")
        self.assertEqual(canceled[0]["cancel_category"], "asyncio_cancelled")

    def test_preflight_repair_makes_two_recorded_calls(self) -> None:
        from bridges.cli_bridge import CliRunResult

        calls = []

        async def runner(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            if command == ["preflight"]:
                calls.append(prompt)
                if len(calls) == 1:
                    return CliRunResult(
                        returncode=0, stdout="not a valid protocol", stderr=""
                    )
                return CliRunResult(
                    returncode=0,
                    stdout='TALK_TASK_PREFLIGHT {"action":"accept"}',
                    stderr="",
                )
            return CliRunResult(returncode=0, stdout="finished", stderr="")

        handled, _client = self._run(runner=runner, task_id=304, preflight_attempt=1)
        self.assertTrue(handled)
        self.assertEqual(len(calls), 2)
        operations = self._operations()
        preflight = [
            rows
            for rows in operations.values()
            if rows[0]["stage"] == "task_model_preflight"
        ]
        repair = [
            rows
            for rows in operations.values()
            if rows[0]["stage"] == "task_model_preflight_repair"
        ]
        self.assertEqual(len(preflight), 1)
        self.assertEqual(len(repair), 1)
        self.assertEqual(
            preflight[0][1]["extra"]["transition"]["status"], "failed"
        )
        self.assertEqual(
            repair[0][1]["extra"]["transition"]["status"], "succeeded"
        )
        self.assertEqual(preflight[0][0]["extra"]["transition"]["attempt"], 1)
        self.assertEqual(repair[0][0]["extra"]["transition"]["attempt"], 1)

    def test_retry_attempts_are_separate_operations(self) -> None:
        from bridges.cli_bridge import CliRunResult

        async def runner(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            if command == ["preflight"]:
                return CliRunResult(
                    returncode=0,
                    stdout='TALK_TASK_PREFLIGHT {"action":"accept"}',
                    stderr="",
                )
            return CliRunResult(returncode=0, stdout="finished", stderr="")

        self._run(runner=runner, task_id=305, preflight_attempt=1)
        self._run(runner=runner, task_id=305, preflight_attempt=2)
        preflight_ops = [
            rows
            for rows in self._operations().values()
            if rows[0]["stage"] == "task_model_preflight"
        ]
        self.assertEqual(len(preflight_ops), 2)
        self.assertEqual(
            sorted(rows[0]["extra"]["transition"]["attempt"] for rows in preflight_ops),
            [1, 2],
        )
        self.assertNotEqual(
            preflight_ops[0][0]["extra"]["transition"]["operation_id"],
            preflight_ops[1][0]["extra"]["transition"]["operation_id"],
        )

    def test_log_write_failure_does_not_change_task_result(self) -> None:
        from bridges.cli_bridge import CliRunResult

        async def runner(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            if command == ["preflight"]:
                return CliRunResult(
                    returncode=0,
                    stdout='TALK_TASK_PREFLIGHT {"action":"accept"}',
                    stderr="",
                )
            return CliRunResult(returncode=0, stdout="finished", stderr="")

        with mock.patch.object(
            self.diagnostics, "_append_locked", side_effect=OSError("disk full")
        ), contextlib.redirect_stderr(io.StringIO()):
            handled, client = self._run(runner=runner, task_id=306)
        self.assertTrue(handled)
        self.assertEqual(client.completed[0][1]["status"], "succeeded")


class HostStageIntegrationTests(unittest.TestCase):
    def test_host_start_and_stop_emit_paired_stage_events(self) -> None:
        from tests.test_role_service_host_diagnostics import (
            HostDiagnosticsTestCase,
            LAUNCH,
        )

        case = HostDiagnosticsTestCase()
        case.setUp()
        try:
            manager = case.make_manager()
            self.assertEqual(case.start_ready(manager)["outcome"], "ready")
            self.assertIn(LAUNCH, manager._handles)
            stop_action = dict(
                case.launch(launch_id="stop-timeline", generation=2),
                action="stop",
            )
            with case.fake_popen_isinstance():
                self.assertEqual(
                    manager.execute_stop(stop_action)["outcome"], "stopped"
                )
            records = case.query()
        finally:
            case.tearDown()

        operations: dict[str, list[dict]] = {}
        for record in records:
            transition = (record.get("extra") or {}).get("transition")
            if transition:
                operations.setdefault(transition["operation_id"], []).append(record)
        stages = {rows[0]["stage"] for rows in operations.values()}
        for stage in (
            "host_start_claim",
            "host_preflight",
            "host_spawn_io",
            "host_spawn",
            "host_readiness",
            "host_start_report",
            "host_stop_claim",
            "host_stop_control",
            "host_stop_exit_wait",
            "host_stop_report",
        ):
            self.assertIn(stage, stages)
        for rows in operations.values():
            self.assertEqual(len(rows), 2, rows[0]["stage"])
            self.assertEqual(rows[0]["event"], f"{rows[0]['stage']}_started")
            self.assertEqual(rows[1]["event"], f"{rows[0]['stage']}_finished")
            self.assertEqual(
                rows[0]["extra"]["transition"]["operation_id"],
                rows[1]["extra"]["transition"]["operation_id"],
            )
            self.assertEqual(
                rows[0]["extra"]["transition"]["status"], "started"
            )
            self.assertIn(
                rows[1]["extra"]["transition"]["status"],
                {"succeeded", "failed", "canceled", "interrupted", "unknown"},
            )
            self.assertGreaterEqual(
                rows[1]["extra"]["transition"]["duration_ms"], 0
            )


if __name__ == "__main__":
    unittest.main()