"""接单轮询诊断记录器的隔离单元测试（假时钟/假写入器，无真实服务）。"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from bridges import queue_poll_diagnostics as qpd


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


class FakeWriter:
    def __init__(self, *, fail_events: tuple[str, ...] = ()) -> None:
        self.events: list[tuple[str, dict]] = []
        self.fail_events = set(fail_events)
        self.calls = 0

    def record_event(self, event: str, **kwargs):
        self.calls += 1
        if event in self.fail_events:
            raise RuntimeError("writer unavailable")
        self.events.append((event, kwargs))
        return f"rtd-fake-{len(self.events):06d}"


class FakeClock:
    """Wall clock and monotonic clock can be advanced/reversed independently."""

    def __init__(self, *, wall=WALL_START, monotonic=0.0) -> None:
        self.wall = wall
        self.monotonic = monotonic

    def now(self):
        return self.wall

    def mono(self):
        return self.monotonic

    def advance(self, seconds: float) -> None:
        self.wall = self.wall + timedelta(seconds=seconds)
        self.monotonic += seconds


def _payloads(writer: FakeWriter, event: str | None = None) -> list[dict]:
    result = []
    for name, kwargs in writer.events:
        if event is not None and name != event:
            continue
        result.append(kwargs["extra"]["queue_poll"])
    return result


class QueuePollRecorderTests(unittest.TestCase):
    def make(self, writer=None, clock=None):
        writer = writer or FakeWriter()
        clock = clock or FakeClock()
        recorder = qpd.QueuePollRecorder(
            writer, wall_clock=clock.now, monotonic=clock.mono
        )
        return recorder, writer, clock

    def test_first_poll_is_observable_with_fixed_keys_and_types(self) -> None:
        recorder, writer, clock = self.make()
        cycle = recorder.begin()
        self.assertEqual(cycle.seq, 1)
        self.assertEqual(len(writer.events), 1)
        event, kwargs = writer.events[0]
        self.assertEqual(event, "queue_poll_snapshot")
        self.assertEqual(kwargs["phase"], "queue")
        self.assertEqual(kwargs["stage"], "queue_poll")
        self.assertEqual(set(kwargs["extra"]), {"queue_poll"})
        started = kwargs["extra"]["queue_poll"]
        self.assertEqual(set(started), EXPECTED_KEYS)
        self.assertEqual(started["poll_seq"], 1)
        self.assertEqual(started["state"], "started")
        self.assertIsNone(started["finished_at"])
        self.assertIsNone(started["duration_ms"])
        self.assertIsNone(started["last_success_at"])
        self.assertIsNone(started["last_failure_at"])
        self.assertIsNone(started["failure_streak_started_at"])
        self.assertEqual(started["consecutive_failures"], 0)
        self.assertEqual(started["recovered_failures"], 0)
        self.assertIsNone(started["error_log_id"])
        self.assertEqual(started["interval_seconds"], 30)
        self.assertFalse(isinstance(started["interval_seconds"], bool))
        self.assertTrue(started["started_at"].endswith("Z"))

        clock.advance(0.25)
        recorder.succeed(cycle)
        self.assertEqual(len(writer.events), 2)
        event, kwargs = writer.events[1]
        self.assertEqual(event, "queue_poll_snapshot")
        finished = kwargs["extra"]["queue_poll"]
        self.assertEqual(set(finished), EXPECTED_KEYS)
        self.assertEqual(finished["poll_seq"], 1)
        self.assertEqual(finished["state"], "succeeded")
        self.assertEqual(finished["duration_ms"], 250.0)
        self.assertEqual(finished["last_success_at"], finished["finished_at"])
        self.assertEqual(finished["consecutive_failures"], 0)
        self.assertEqual(finished["recovered_failures"], 0)
        self.assertIsNone(finished["failure_streak_started_at"])
        self.assertEqual(recorder.consecutive_failures, 0)

    def test_idle_success_snapshots_are_bounded_but_sequence_advances(self) -> None:
        recorder, writer, clock = self.make()
        success_starts: list[tuple[int, datetime]] = []
        for index in range(31):  # 0..60 seconds, 2s apart
            clock.monotonic = float(index * 2)
            clock.wall = WALL_START + timedelta(seconds=index * 2)
            cycle = recorder.begin()
            clock.advance(0.1)
            recorder.succeed(cycle)
        self.assertEqual(recorder.poll_seq, 31)
        started = _payloads(writer, "queue_poll_snapshot")
        succeeded = [item for item in started if item["state"] == "succeeded"]
        starts = [item for item in started if item["state"] == "started"]
        self.assertEqual(len(succeeded), len(starts))
        self.assertGreaterEqual(len(succeeded), 1)
        self.assertLessEqual(len(succeeded), 4)
        self.assertEqual([item["poll_seq"] for item in starts], [item["poll_seq"] for item in succeeded])
        # No two sampled success starts may be closer than the 30s interval.
        parsed = [datetime.fromisoformat(item["started_at"].replace("Z", "+00:00")) for item in succeeded]
        for left, right in zip(parsed, parsed[1:]):
            self.assertGreaterEqual((right - left).total_seconds(), 30)
        # Every poll ran, but un-sampled successes still update last_success_at.
        self.assertEqual(recorder.poll_seq, 31)
        self.assertGreater(recorder.poll_seq, len(succeeded))
        last_cycle = recorder.begin()
        clock.advance(0.1)
        recorder.fail(last_cycle, "rtd-fake-000999")
        failed_events = _payloads(writer)
        failed = [item for item in failed_events if item["state"] == "failed"][-1]
        self.assertIsNotNone(failed["last_success_at"])
        self.assertEqual(
            failed["last_success_at"],
            qpd.utc_text(WALL_START + timedelta(seconds=60.1)),
        )

    def test_consecutive_failures_and_single_recovery(self) -> None:
        recorder, writer, clock = self.make()
        first = recorder.begin()
        clock.advance(0.2)
        recorder.fail(first, "rtd-fake-000001")
        second = recorder.begin()
        clock.advance(0.3)
        recorder.fail(second, "rtd-fake-000002")

        failures = [item for item in _payloads(writer) if item["state"] == "failed"]
        self.assertEqual([item["poll_seq"] for item in failures], [1, 2])
        self.assertEqual([item["consecutive_failures"] for item in failures], [1, 2])
        self.assertEqual(failures[0]["failure_streak_started_at"], failures[0]["finished_at"])
        self.assertEqual(
            failures[1]["failure_streak_started_at"],
            failures[0]["failure_streak_started_at"],
        )
        self.assertEqual(failures[0]["last_failure_at"], failures[0]["finished_at"])
        self.assertEqual(failures[1]["last_failure_at"], failures[1]["finished_at"])
        self.assertEqual(failures[0]["error_log_id"], "rtd-fake-000001")
        # The failure segment keeps its original exception reference; the
        # second failure has its own separate evidence record.
        self.assertEqual(failures[1]["error_log_id"], "rtd-fake-000001")
        self.assertEqual(recorder.consecutive_failures, 2)

        # Recovery evidence is written even if the success would not be sampled.
        recovery_cycle = recorder.begin()
        clock.advance(0.4)
        recorder.succeed(recovery_cycle)
        recovered = _payloads(writer, "queue_poll_recovered")
        self.assertEqual(len(recovered), 1)
        recovery = recovered[0]
        self.assertEqual(recovery["poll_seq"], 3)
        self.assertEqual(recovery["state"], "succeeded")
        self.assertEqual(recovery["recovered_failures"], 2)
        self.assertEqual(recovery["consecutive_failures"], 0)
        self.assertEqual(
            recovery["failure_streak_started_at"],
            failures[0]["failure_streak_started_at"],
        )
        self.assertEqual(recovery["last_failure_at"], failures[1]["finished_at"])
        self.assertEqual(recovery["last_success_at"], recovery["finished_at"])
        self.assertEqual(recovery["error_log_id"], "rtd-fake-000001")
        self.assertEqual(recorder.consecutive_failures, 0)

        # A genuinely later success produces a normal snapshot, never a second
        # recovery, and the normal snapshot clears the active streak field.
        clock.advance(31)
        normal_cycle = recorder.begin()
        clock.advance(0.1)
        recorder.succeed(normal_cycle)
        self.assertEqual(len(_payloads(writer, "queue_poll_recovered")), 1)
        normal = [
            item
            for item in _payloads(writer, "queue_poll_snapshot")
            if item["state"] == "succeeded" and item["poll_seq"] == 4
        ]
        self.assertEqual(len(normal), 1)
        self.assertEqual(normal[0]["consecutive_failures"], 0)
        self.assertEqual(normal[0]["recovered_failures"], 0)
        self.assertIsNone(normal[0]["failure_streak_started_at"])
        # last_failure_at/error_log_id remain the most recent failure segment.
        self.assertEqual(normal[0]["last_failure_at"], failures[1]["finished_at"])
        self.assertEqual(normal[0]["error_log_id"], "rtd-fake-000001")

    def test_new_failure_streak_resets_original_exception_reference(self) -> None:
        recorder, writer, clock = self.make()
        first = recorder.begin()
        clock.advance(0.1)
        recorder.fail(first, "rtd-fake-000001")
        recovery_cycle = recorder.begin()
        clock.advance(0.1)
        recorder.succeed(recovery_cycle)
        clock.advance(1)
        second = recorder.begin()
        clock.advance(0.1)
        recorder.fail(second, "rtd-fake-000002")
        failed = [item for item in _payloads(writer) if item["state"] == "failed"]
        self.assertEqual(len(failed), 2)
        self.assertEqual(failed[-1]["error_log_id"], "rtd-fake-000002")
        self.assertEqual(
            failed[-1]["failure_streak_started_at"], failed[-1]["finished_at"]
        )
        self.assertEqual(failed[-1]["consecutive_failures"], 1)
        recovery_cycle = recorder.begin()
        clock.advance(0.1)
        recorder.succeed(recovery_cycle)
        recovered = _payloads(writer, "queue_poll_recovered")
        self.assertEqual(len(recovered), 2)
        self.assertEqual(recovered[-1]["recovered_failures"], 1)
        self.assertEqual(recovered[-1]["error_log_id"], "rtd-fake-000002")

    def test_success_without_prior_failure_is_not_a_recovery(self) -> None:
        recorder, writer, clock = self.make()
        recorder.succeed(recorder.begin())
        clock.advance(1)
        recorder.succeed(recorder.begin())
        self.assertEqual(_payloads(writer, "queue_poll_recovered"), [])

    def test_cancellation_is_neither_failure_nor_recovery(self) -> None:
        recorder, writer, clock = self.make()
        first = recorder.begin()
        clock.advance(0.5)
        recorder.cancel(first)
        canceled = [item for item in _payloads(writer) if item["state"] == "canceled"]
        self.assertEqual(len(canceled), 1)
        self.assertEqual(canceled[0]["poll_seq"], 1)
        self.assertEqual(canceled[0]["consecutive_failures"], 0)
        self.assertEqual(canceled[0]["recovered_failures"], 0)
        self.assertEqual(recorder.consecutive_failures, 0)

        # Canceling during an active failure streak keeps the streak alive but
        # neither increments it nor recovers it.
        failed_cycle = recorder.begin()
        clock.advance(0.1)
        recorder.fail(failed_cycle, "rtd-fake-000001")
        canceled_cycle = recorder.begin()
        clock.advance(0.2)
        recorder.cancel(canceled_cycle)
        canceled = [item for item in _payloads(writer) if item["state"] == "canceled"][-1]
        self.assertEqual(canceled["consecutive_failures"], 1)
        self.assertEqual(canceled["recovered_failures"], 0)
        self.assertIsNotNone(canceled["failure_streak_started_at"])
        self.assertEqual(recorder.consecutive_failures, 1)
        self.assertEqual(_payloads(writer, "queue_poll_recovered"), [])

        recovery_cycle = recorder.begin()
        clock.advance(0.3)
        recorder.succeed(recovery_cycle)
        recovered = _payloads(writer, "queue_poll_recovered")
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["recovered_failures"], 1)

    def test_wall_clock_rollback_keeps_monotonic_duration(self) -> None:
        recorder, writer, clock = self.make()
        cycle = recorder.begin()
        clock.monotonic += 2.0
        clock.wall = clock.wall - timedelta(seconds=5)
        recorder.succeed(cycle)
        succeeded = [
            item for item in _payloads(writer) if item["state"] == "succeeded"
        ][0]
        self.assertEqual(succeeded["duration_ms"], 2000.0)
        self.assertLess(succeeded["finished_at"], succeeded["started_at"])

    def test_writer_failure_never_propagates_or_changes_counters(self) -> None:
        writer = FakeWriter(
            fail_events=("queue_poll_snapshot", "queue_poll_recovered")
        )
        clock = FakeClock()
        recorder = qpd.QueuePollRecorder(writer, wall_clock=clock.now, monotonic=clock.mono)
        cycle = recorder.begin()
        clock.advance(0.1)
        recorder.fail(cycle, "rtd-fake-000001")
        self.assertEqual(recorder.consecutive_failures, 1)
        self.assertEqual(writer.events, [])
        self.assertGreaterEqual(writer.calls, 1)
        cycle = recorder.begin()
        clock.advance(0.1)
        recorder.succeed(cycle)
        self.assertEqual(recorder.consecutive_failures, 0)
        self.assertEqual(writer.events, [])

    def test_no_diagnostics_is_a_safe_noop(self) -> None:
        clock = FakeClock()
        recorder = qpd.QueuePollRecorder(
            None, wall_clock=clock.now, monotonic=clock.mono
        )
        cycle = recorder.begin()
        clock.advance(1)
        recorder.fail(cycle, "rtd-fake-000001")
        cycle = recorder.begin()
        clock.advance(1)
        recorder.succeed(cycle)
        self.assertEqual(recorder.poll_seq, 2)
        self.assertEqual(recorder.consecutive_failures, 0)

    def test_recorders_are_isolated_per_instance(self) -> None:
        first_writer, second_writer = FakeWriter(), FakeWriter()
        first_clock, second_clock = FakeClock(), FakeClock()
        first = qpd.QueuePollRecorder(
            first_writer, wall_clock=first_clock.now, monotonic=first_clock.mono
        )
        second = qpd.QueuePollRecorder(
            second_writer, wall_clock=second_clock.now, monotonic=second_clock.mono
        )
        first.succeed(first.begin())
        first.succeed(first.begin())
        second.succeed(second.begin())
        second_clock.advance(1)
        second.fail(second.begin(), "rtd-fake-000001")
        first_seqs = [item["poll_seq"] for item in _payloads(first_writer)]
        second_seqs = [item["poll_seq"] for item in _payloads(second_writer)]
        self.assertEqual(first_seqs, [1, 1])
        self.assertEqual(second_seqs, [1, 1, 2, 2])

    def test_snapshot_is_json_serializable_without_free_text(self) -> None:
        recorder, writer, clock = self.make()
        cycle = recorder.begin()
        clock.advance(1)
        recorder.fail(cycle, "rtd-fake-000001")
        for _event, kwargs in writer.events:
            payload = kwargs["extra"]["queue_poll"]
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            self.assertNotIn("boom", encoded)
            self.assertNotIn("traceback", encoded.lower())


if __name__ == "__main__":
    unittest.main()
