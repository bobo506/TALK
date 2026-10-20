"""任务 282 A 片：宿主本地循环与原 Popen 运行证据的隔离测试。

只使用系统临时根（显式放在本任务根）、内存假件、假时钟、真实维护者 CLI
以及自建短命 Popen；不连接 TALK 生产接口、不启动真实角色/模型、不读写真实
Key 或生产日志根。所有真实 Popen 都由本测试创建并等待/清理。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bridges import runtime_diagnostics as runtime_diag
from scripts import role_service_host as host
from scripts import role_service_host_diagnostics as host_diag
from scripts import role_service_host_loop_evidence as evidence
from scripts.runtime_diagnostics import main as diagnostics_cli_main

PROJECT = "prj_probe_282"
HOST = "host-282"
MEMBER = "agent:probe.282"
INSTANCE = "ins_282"
LAUNCH = "launch-282"
PYTHON_EXECUTABLE = getattr(sys, "_base_executable", sys.executable)


# ---------------------------------------------------------------------------
# 假件
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.t = float(start)
        self.wall_start = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)

    def mono(self) -> float:
        return self.t

    def wall_clock(self) -> datetime:
        return self.wall_start + timedelta(seconds=self.t)

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


class MemoryDiagnostics:
    enabled = True

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.records: list[dict] = []

    def record_event(self, event: str, **kwargs) -> str:
        record = {"event": event, **kwargs}
        self.records.append(record)
        return f"mem-{len(self.records)}"

    def record_exception(self, exc: BaseException, **kwargs) -> str:
        record = {"event": kwargs.get("event", "exception"), **kwargs}
        self.records.append(record)
        return f"mem-{len(self.records)}"

    def close(self) -> None:
        return None

    def events(self, name: str) -> list[dict]:
        return [record for record in self.records if record.get("event") == name]


class CountingDiagnostics:
    """只计数/记录序号，便于 21600 轮不堆积大量记录。"""

    enabled = True

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.manager_seqs: set[int] = set()
        self.last_manager: dict | None = None

    def record_event(self, event: str, **kwargs) -> str:
        self.counts[event] = self.counts.get(event, 0) + 1
        if event == evidence.MANAGER_EVENT:
            manager_run = (kwargs.get("extra") or {}).get("manager_run") or {}
            seq = manager_run.get("manager_seq")
            if isinstance(seq, int) and not isinstance(seq, bool):
                self.manager_seqs.add(seq)
            self.last_manager = manager_run
        return f"count-{sum(self.counts.values())}"

    def record_exception(self, exc: BaseException, **kwargs) -> str:
        return self.record_event(kwargs.get("event", "exception"), **kwargs)

    def close(self) -> None:
        return None


class PollProcess:
    def __init__(self, pid: int = 4242, poll=None):
        self.pid = int(pid)
        self._poll = poll or (lambda: None)
        self.calls = 0

    def poll(self):
        self.calls += 1
        return self._poll()


class MemoryLaunchWriter:
    enabled = True

    def __init__(self):
        self.records: list[dict] = []
        self.records_seen: list[dict] = []

    def factory(self, record):
        self.records_seen.append(dict(record))
        return self

    def record_event(self, event: str, **kwargs) -> str:
        self.records.append({"event": event, **kwargs})
        return f"launch-{len(self.records)}"

    def events(self, name: str) -> list[dict]:
        return [record for record in self.records if record.get("event") == name]


class SilentClient:
    """serve 只读轮询用的假 TALK 客户端；没有任何网络。"""

    base_url = "http://isolated.invalid"
    timeout = 15.0

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def request(self, method, path, body=None, key=None):
        self.calls.append((method, path))
        if "/role-services" in path:
            return {"data": []}
        raise AssertionError(path)


def make_handle(
    launch_id: str = LAUNCH,
    *,
    pid: int | None = None,
    project: str = PROJECT,
    host_label: str = HOST,
    member: str | None = MEMBER,
    instance: str | None = INSTANCE,
    process=None,
    record_pid: int | None = None,
    runtime: str = "dsh",
):
    process = process if process is not None else PollProcess(pid or 4242)
    actual_pid = getattr(process, "pid", pid or 4242)
    record = {
        "project_id": project,
        "host": host_label,
        "launch_id": launch_id,
        "member_id": member,
        "instance_id": instance,
        "pid": actual_pid if record_pid is None else record_pid,
        "runtime": runtime,
    }
    return launch_id, {"process": process, "record": record}


def make_recorder(
    *,
    handles=None,
    diagnostics=None,
    clock=None,
    launch_writer=None,
    poll_interval=1.0,
    manager_run_id=None,
    project=PROJECT,
    host_label=HOST,
    wall_clock=None,
    monotonic_clock=None,
):
    clock = clock or FakeClock()
    diagnostics = diagnostics if diagnostics is not None else MemoryDiagnostics()
    return evidence.LoopEvidenceRecorder(
        project_id=project,
        host=host_label,
        poll_interval=poll_interval,
        manager_diagnostics=diagnostics,
        handles=handles if handles is not None else {},
        launch_writer=launch_writer,
        manager_run_id=manager_run_id,
        wall_clock=wall_clock if wall_clock is not None else clock.wall_clock,
        monotonic_clock=(
            monotonic_clock if monotonic_clock is not None else clock.mono
        ),
    )


def run_round(recorder, *, poll_ok=True, actions_seen=0):
    recorder.begin_round()
    recorder.finish_round(poll_ok=poll_ok, actions_seen=actions_seen)


# ---------------------------------------------------------------------------
# 采样、序号与生命周期
# ---------------------------------------------------------------------------


class ManagerRunSamplingTests(unittest.TestCase):
    def test_21600_rounds_and_10000_boundary_are_not_query_limited(self):
        clock = FakeClock()
        diagnostics = CountingDiagnostics()
        recorder = make_recorder(diagnostics=diagnostics, clock=clock)
        for _ in range(21600):
            run_round(recorder, actions_seen=3)
            clock.advance(60)
        self.assertEqual(recorder.manager_seq, 21600)
        self.assertEqual(
            diagnostics.counts.get(evidence.MANAGER_EVENT), 21600 * 2
        )
        self.assertIn(10001, diagnostics.manager_seqs)
        self.assertIn(21600, diagnostics.manager_seqs)
        self.assertTrue(all(seq >= 1 for seq in diagnostics.manager_seqs))
        self.assertLessEqual(max(diagnostics.manager_seqs), 2**53 - 1)

    def test_fixed_60s_sampling_and_started_never_polls(self):
        clock = FakeClock()
        diagnostics = MemoryDiagnostics()
        process = PollProcess()
        _, handle = make_handle(process=process)
        writer = MemoryLaunchWriter()
        recorder = make_recorder(
            handles={LAUNCH: handle},
            diagnostics=diagnostics,
            launch_writer=writer.factory,
            clock=clock,
        )
        for index in range(61):
            run_round(recorder, actions_seen=1)
            if index < 60:
                clock.advance(1)
        started = [
            record["extra"]["manager_run"]
            for record in diagnostics.events(evidence.MANAGER_EVENT)
            if record["extra"]["manager_run"]["state"] == "started"
        ]
        succeeded = [
            record["extra"]["manager_run"]
            for record in diagnostics.events(evidence.MANAGER_EVENT)
            if record["extra"]["manager_run"]["state"] == "succeeded"
        ]
        self.assertEqual(len(started), 2)
        self.assertEqual(len(succeeded), 2)
        self.assertEqual(started[0]["manager_seq"], 1)
        self.assertEqual(started[1]["manager_seq"], 61)
        # 60 轮未采样 finish + 所有 started 均未调用 poll；只有两次 terminal 观测。
        self.assertEqual(process.calls, 2)
        self.assertEqual(len(writer.events(evidence.LAUNCH_EVENT)), 2)
        for manager in started:
            self.assertEqual(
                manager["process"],
                {
                    "held": None,
                    "alive": None,
                    "exited": None,
                    "unknown": None,
                    "truncated": True,
                },
            )
            self.assertIsNone(manager["finished_at"])
            self.assertIsNone(manager["duration_ms"])
            self.assertEqual(manager["actions_seen"], 0)

    def test_failure_first_then_60s_limit_then_real_recovery(self):
        clock = FakeClock()
        diagnostics = MemoryDiagnostics()
        recorder = make_recorder(diagnostics=diagnostics, clock=clock)
        run_round(recorder, poll_ok=True)
        clock.advance(1)
        run_round(recorder, poll_ok=False)
        for _ in range(59):
            clock.advance(1)
            run_round(recorder, poll_ok=False)
        # t=61: 距首个失败完成 60 秒，允许再写一个失败完成。
        clock.advance(1)
        run_round(recorder, poll_ok=False)
        clock.advance(1)
        run_round(recorder, poll_ok=True)

        managers = [
            record["extra"]["manager_run"]
            for record in diagnostics.events(evidence.MANAGER_EVENT)
        ]
        failed = [item for item in managers if item["state"] == "failed"]
        recovered = [
            item
            for item in managers
            if item["state"] == "succeeded" and item["recovered_failures"]
        ]
        self.assertEqual(len(failed), 2)
        self.assertEqual(failed[0]["consecutive_failures"], 1)
        self.assertEqual(failed[-1]["consecutive_failures"], 61)
        self.assertEqual(len(recovered), 1)
        recovery = recovered[0]
        self.assertEqual(recovery["consecutive_failures"], 0)
        self.assertEqual(recovery["recovered_failures"], 61)
        self.assertEqual(
            recovery["failure_streak_started_at"],
            failed[0]["finished_at"],
        )
        self.assertEqual(recovery["last_failure_at"], failed[-1]["finished_at"])
        self.assertEqual(recovery["last_success_at"], recovery["finished_at"])

    def test_new_failure_segment_first_completion_is_immediate(self):
        clock = FakeClock()
        diagnostics = MemoryDiagnostics()
        recorder = make_recorder(diagnostics=diagnostics, clock=clock)
        run_round(recorder, poll_ok=True)
        clock.advance(1)
        run_round(recorder, poll_ok=False)
        clock.advance(1)
        run_round(recorder, poll_ok=True)
        clock.advance(1)
        run_round(recorder, poll_ok=False)
        failed = [
            record["extra"]["manager_run"]
            for record in diagnostics.events(evidence.MANAGER_EVENT)
            if record["extra"]["manager_run"]["state"] == "failed"
        ]
        self.assertEqual(len(failed), 2)
        self.assertEqual(failed[0]["consecutive_failures"], 1)
        self.assertEqual(failed[1]["consecutive_failures"], 1)
        self.assertEqual(
            failed[1]["failure_streak_started_at"], failed[1]["finished_at"]
        )

    def test_no_background_heartbeat_while_blocked(self):
        clock = FakeClock()
        diagnostics = MemoryDiagnostics()
        recorder = make_recorder(diagnostics=diagnostics, clock=clock)
        recorder.begin_round()
        self.assertEqual(recorder.manager_seq, 1)
        time.sleep(0.2)
        self.assertEqual(recorder.manager_seq, 1)
        self.assertEqual(len(diagnostics.records), 1)
        recorder.finish_round(poll_ok=True, actions_seen=0)

    def test_invalid_actions_seen_is_not_written_as_zero(self):
        clock = FakeClock()
        diagnostics = MemoryDiagnostics()
        recorder = make_recorder(diagnostics=diagnostics, clock=clock)
        run_round(recorder, actions_seen=True)
        states = [
            record["extra"]["manager_run"]["state"]
            for record in diagnostics.events(evidence.MANAGER_EVENT)
        ]
        self.assertEqual(states, ["started"])
        clock.advance(60)
        run_round(recorder, actions_seen=2)
        succeeded = [
            record["extra"]["manager_run"]
            for record in diagnostics.events(evidence.MANAGER_EVENT)
            if record["extra"]["manager_run"]["state"] == "succeeded"
        ]
        self.assertEqual(len(succeeded), 1)
        self.assertEqual(succeeded[0]["actions_seen"], 2)

    def test_manager_run_id_shape_and_independent_runs(self):
        first = make_recorder()
        second = make_recorder()
        pattern = re.compile(r"^mgr-[0-9a-f]{32}$")
        self.assertRegex(first.manager_run_id, pattern)
        self.assertRegex(second.manager_run_id, pattern)
        self.assertNotEqual(first.manager_run_id, second.manager_run_id)

    def test_bad_poll_interval_is_cleaned_without_business_validation(self):
        for value in (-1, float("nan"), float("inf"), True, "1"):
            with self.subTest(value=value):
                diagnostics = MemoryDiagnostics()
                recorder = make_recorder(
                    diagnostics=diagnostics, poll_interval=value
                )
                run_round(recorder)
                # 旧业务入参不受新校验影响；不发布不符合固定对象的null预算。
                self.assertEqual(diagnostics.events(evidence.MANAGER_EVENT), [])


# ---------------------------------------------------------------------------
# 坏时钟
# ---------------------------------------------------------------------------


class ClockTests(unittest.TestCase):
    def test_rollback_and_nonfinite_monotonic_do_not_fake_duration(self):
        values = [100.0, 90.0]
        diagnostics = MemoryDiagnostics()
        recorder = make_recorder(
            diagnostics=diagnostics,
            monotonic_clock=lambda: values.pop(0),
        )
        run_round(recorder)
        managers = diagnostics.events(evidence.MANAGER_EVENT)
        self.assertTrue(managers)
        self.assertTrue(all(r["extra"]["manager_run"]["state"] == "started" for r in managers))

        for bad in (float("nan"), float("inf"), "bad", True):
            with self.subTest(bad=bad):
                diagnostics = MemoryDiagnostics()
                clock = FakeClock()
                recorder = make_recorder(
                    diagnostics=diagnostics,
                    clock=clock,
                    monotonic_clock=lambda bad=bad: bad,
                )
                run_round(recorder)
                managers = diagnostics.events(evidence.MANAGER_EVENT)
                self.assertTrue(all(r["extra"]["manager_run"]["state"] == "started" for r in managers))

    def test_unknown_first_failure_time_is_not_backfilled(self):
        class ToggleWallClock:
            def __init__(self):
                self.bad = False
                self.now = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)

            def __call__(self):
                if self.bad:
                    raise RuntimeError("wall clock unavailable")
                return self.now

        wall = ToggleWallClock()
        clock = FakeClock()
        diagnostics = MemoryDiagnostics()
        recorder = make_recorder(
            diagnostics=diagnostics, clock=clock, wall_clock=wall
        )
        run_round(recorder, poll_ok=True)
        clock.advance(1)
        wall.bad = True
        run_round(recorder, poll_ok=False)
        wall.bad = False
        clock.advance(1)
        run_round(recorder, poll_ok=False)
        failed = [
            record["extra"]["manager_run"]
            for record in diagnostics.events(evidence.MANAGER_EVENT)
            if record["extra"]["manager_run"]["state"] == "failed"
        ]
        # 首轮完成时刻缺失，不能发布缺少真实失败段起点的新对象。
        self.assertEqual(failed, [])
        # 恢复段起点未知时不写 recovered>0 的伪造恢复记录。
        clock.advance(1)
        run_round(recorder, poll_ok=True)
        recovered = [
            record["extra"]["manager_run"]
            for record in diagnostics.events(evidence.MANAGER_EVENT)
            if record["extra"]["manager_run"]["state"] == "succeeded"
            and record["extra"]["manager_run"]["recovered_failures"]
        ]
        self.assertEqual(recovered, [])

    def test_raising_monotonic_clock_does_not_break_rounds(self):
        diagnostics = MemoryDiagnostics()
        recorder = make_recorder(
            diagnostics=diagnostics,
            monotonic_clock=lambda: (_ for _ in ()).throw(RuntimeError("bad")),
        )
        run_round(recorder)
        managers = diagnostics.events(evidence.MANAGER_EVENT)
        self.assertEqual(len(managers), 1)
        self.assertEqual(managers[-1]["extra"]["manager_run"]["state"], "started")

    def test_bad_wall_clock_skips_records_without_fake_duration(self):
        naive = datetime(2026, 10, 20, 0, 0, 0)
        for bad_clock in (
            lambda: (_ for _ in ()).throw(RuntimeError("bad")),
            lambda: naive,
            lambda: "not-a-datetime",
        ):
            with self.subTest(clock=bad_clock):
                diagnostics = MemoryDiagnostics()
                recorder = make_recorder(
                    diagnostics=diagnostics,
                    wall_clock=bad_clock,
                )
                run_round(recorder)
                run_round(recorder)
                self.assertEqual(diagnostics.records, [])


# ---------------------------------------------------------------------------
# 原 Popen 观测
# ---------------------------------------------------------------------------


class ProcessObservationTests(unittest.TestCase):
    def _sample(self, handles, *, clock=None, diagnostics=None, writer=None):
        clock = clock or FakeClock()
        diagnostics = diagnostics or MemoryDiagnostics()
        recorder = make_recorder(
            handles=handles,
            diagnostics=diagnostics,
            clock=clock,
            launch_writer=writer.factory if writer is not None else None,
        )
        run_round(recorder)
        managers = diagnostics.events(evidence.MANAGER_EVENT)
        manager = managers[-1]["extra"]["manager_run"]
        return recorder, diagnostics, manager

    def test_real_popen_alive_then_exit_and_nonzero_exit(self):
        process = subprocess.Popen(
            [PYTHON_EXECUTABLE, "-c", "import time; time.sleep(0.35)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _, handle = make_handle(process=process)
            clock = FakeClock()
            writer = MemoryLaunchWriter()
            recorder, diagnostics, manager = self._sample(
                {LAUNCH: handle}, clock=clock, writer=writer
            )
            self.assertEqual(manager["process"]["held"], 1)
            self.assertEqual(manager["process"]["alive"], 1)
            self.assertFalse(manager["process"]["truncated"])
            self.assertEqual(
                writer.events(evidence.LAUNCH_EVENT)[-1]["extra"][
                    "launch_process"
                ]["state"],
                "alive",
            )
            process.wait(timeout=10)
            clock.advance(60)
            run_round(recorder)
            manager = diagnostics.events(evidence.MANAGER_EVENT)[-1]["extra"][
                "manager_run"
            ]
            self.assertEqual(manager["process"]["exited"], 1)
            launch = writer.events(evidence.LAUNCH_EVENT)[-1]["extra"][
                "launch_process"
            ]
            self.assertEqual(launch["state"], "exited")
            self.assertEqual(launch["exit_code"], 0)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)

        exiting = subprocess.Popen(
            [PYTHON_EXECUTABLE, "-c", "import sys; sys.exit(7)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            exiting.wait(timeout=10)
            _, handle = make_handle(
                "launch-nonzero", process=exiting
            )
            writer = MemoryLaunchWriter()
            _, _, manager = self._sample(
                {"launch-nonzero": handle}, writer=writer
            )
            self.assertEqual(manager["process"]["exited"], 1)
            launch = writer.events(evidence.LAUNCH_EVENT)[-1]["extra"][
                "launch_process"
            ]
            self.assertEqual(launch["exit_code"], 7)
        finally:
            if exiting.poll() is None:
                exiting.kill()
            exiting.wait(timeout=10)

    def test_poll_errors_non_integer_bool_and_out_of_range_are_unknown(self):
        handles = {}

        def add(name, poll_fn, pid):
            _, handle = make_handle(
                name,
                pid=pid,
                process=PollProcess(pid=pid, poll=poll_fn),
            )
            handles[name] = handle

        add("raise", lambda: (_ for _ in ()).throw(RuntimeError("x")), 11)
        add("bool", lambda: True, 12)
        add("float", lambda: 1.5, 13)
        add("too-high", lambda: 2**32, 14)
        add("min", lambda: -(2**31), 15)
        add("max", lambda: 2**32 - 1, 16)

        writer = MemoryLaunchWriter()
        _, _, manager = self._sample(handles, writer=writer)
        launches = {
            item["extra"]["launch_process"]["launch_id"]: item["extra"][
                "launch_process"
            ]
            for item in writer.events(evidence.LAUNCH_EVENT)
        }
        self.assertEqual(launches["raise"]["state"], "unknown")
        self.assertEqual(launches["bool"]["state"], "unknown")
        self.assertEqual(launches["float"]["state"], "unknown")
        self.assertEqual(launches["too-high"]["state"], "unknown")
        self.assertEqual(launches["min"]["state"], "exited")
        self.assertEqual(launches["min"]["exit_code"], -(2**31))
        self.assertEqual(launches["max"]["state"], "exited")
        self.assertEqual(launches["max"]["exit_code"], 2**32 - 1)
        for name in ("raise", "bool", "float", "too-high"):
            self.assertIsNone(launches[name]["exit_code"])
        self.assertEqual(manager["process"]["held"], 6)
        self.assertEqual(manager["process"]["exited"], 2)
        self.assertEqual(manager["process"]["unknown"], 4)
        self.assertFalse(manager["process"]["truncated"])

    def test_identity_mismatch_is_not_attributed(self):
        handles = {}
        for name, overrides in {
            "wrong-project": {"project": "prj_other"},
            "wrong-host": {"host_label": "host-other"},
            "wrong-launch": {},
            "wrong-pid": {"record_pid": 9999},
            "missing-member": {"member": None},
            "missing-instance": {"instance": ""},
            "unknown-member": {"member": "unknown"},
        }.items():
            key, handle = make_handle(
                name,
                pid=1234,
                process=PollProcess(pid=1234),
                **overrides,
            )
            if name == "wrong-launch":
                handle["record"]["launch_id"] = "record-other"
            handles[key] = handle
        writer = MemoryLaunchWriter()
        _, _, manager = self._sample(handles, writer=writer)
        launches = writer.events(evidence.LAUNCH_EVENT)
        self.assertEqual(launches, [])
        # 仅 project+host 匹配的 5 条计入 held；跨项目/跨 host 不归入本项目。
        self.assertEqual(manager["process"]["held"], 5)
        self.assertEqual(manager["process"]["alive"], 0)
        self.assertEqual(manager["process"]["unknown"], 5)
        self.assertTrue(manager["process"]["truncated"])

    def test_observation_overall_failure_is_unknown_not_empty(self):
        diagnostics = MemoryDiagnostics()
        recorder = make_recorder(
            handles=object(), diagnostics=diagnostics
        )
        run_round(recorder)
        manager = diagnostics.events(evidence.MANAGER_EVENT)[-1]["extra"][
            "manager_run"
        ]
        self.assertEqual(
            manager["process"],
            {
                "held": None,
                "alive": None,
                "exited": None,
                "unknown": None,
                "truncated": True,
            },
        )
        self.assertNotEqual(manager["process"]["held"], 0)

    def test_gt32_fair_selection_covers_later_handles(self):
        handles = {}
        for index in range(40):
            key, handle = make_handle(
                f"launch-{index:02d}",
                pid=2000 + index,
                process=PollProcess(pid=2000 + index),
            )
            handles[key] = handle
        clock = FakeClock()
        diagnostics = MemoryDiagnostics()
        writer = MemoryLaunchWriter()
        recorder = make_recorder(
            handles=handles,
            diagnostics=diagnostics,
            clock=clock,
            launch_writer=writer.factory,
        )
        run_round(recorder)
        first_batch = [
            item["extra"]["launch_process"]["launch_id"]
            for item in writer.events(evidence.LAUNCH_EVENT)
            if item["extra"]["launch_process"]["manager_seq"] == 1
        ]
        clock.advance(60)
        run_round(recorder)
        second_batch = [
            item["extra"]["launch_process"]["launch_id"]
            for item in writer.events(evidence.LAUNCH_EVENT)
            if item["extra"]["launch_process"]["manager_seq"] == 2
        ]
        self.assertEqual(len(first_batch), 32)
        self.assertEqual(len(second_batch), 32)
        self.assertEqual(len(set(first_batch)), 32)
        self.assertEqual(len(set(second_batch)), 32)
        self.assertEqual(set(first_batch) | set(second_batch), set(handles))
        self.assertNotEqual(set(first_batch), set(second_batch))
        manager = diagnostics.events(evidence.MANAGER_EVENT)[-1]["extra"][
            "manager_run"
        ]
        self.assertEqual(manager["process"]["held"], 40)
        self.assertEqual(manager["process"]["alive"], 32)
        self.assertEqual(manager["process"]["unknown"], 8)
        self.assertTrue(manager["process"]["truncated"])

    def test_gt256_is_bounded_and_aggregate_unknown(self):
        class CountingDict(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.item_reads = 0

            def items(self):
                for item in super().items():
                    self.item_reads += 1
                    yield item

        handles = CountingDict()
        for index in range(300):
            key, handle = make_handle(
                f"launch-{index:03d}",
                pid=3000 + index,
                process=PollProcess(pid=3000 + index),
            )
            handles[key] = handle
        writer = MemoryLaunchWriter()
        _, _, manager = self._sample(handles, writer=writer)
        self.assertLessEqual(handles.item_reads, 256)
        self.assertLessEqual(
            len(writer.events(evidence.LAUNCH_EVENT)), 32
        )
        self.assertEqual(
            manager["process"],
            {
                "held": None,
                "alive": None,
                "exited": None,
                "unknown": None,
                "truncated": True,
            },
        )


# ---------------------------------------------------------------------------
# 固定对象、真实写入器、CLI 与导出投影
# ---------------------------------------------------------------------------


class FixedObjectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="talk282-loop-evidence-")
        self.root = Path(self._tmp.name)
        self.policy = host_diag.HostDiagnosticsPolicy.resolve(root=self.root / "logs")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_one_round(self):
        manager_writer = host_diag.create_writer(
            policy=self.policy,
            member_id="unknown",
            project_id=PROJECT,
            runtime="role-service-host",
        )
        launch_writer = host_diag.create_writer(
            policy=self.policy,
            member_id=MEMBER,
            instance_id=INSTANCE,
            project_id=PROJECT,
            launch_id=LAUNCH,
            runtime="dsh",
        )
        _, handle = make_handle(process=PollProcess())
        recorder = evidence.LoopEvidenceRecorder(
            project_id=PROJECT,
            host=HOST,
            poll_interval=1.0,
            manager_diagnostics=manager_writer,
            handles={LAUNCH: handle},
            launch_writer=lambda record: launch_writer,
            wall_clock=FakeClock().wall_clock,
            monotonic_clock=FakeClock().mono,
        )
        run_round(recorder)
        manager_writer.close()
        launch_writer.close()
        return self.root / "logs"

    def test_manager_and_launch_objects_have_exact_keys_and_identity(self):
        root = self._write_one_round()
        managers = runtime_diag.query_records(
            root=root, event=evidence.MANAGER_EVENT, limit=20
        )["records"]
        launches = runtime_diag.query_records(
            root=root, event=evidence.LAUNCH_EVENT, limit=20
        )["records"]
        self.assertEqual(len(managers), 2)
        self.assertEqual(len(launches), 1)
        succeeded = [
            record
            for record in managers
            if record["extra"]["manager_run"]["state"] == "succeeded"
        ][-1]
        manager_run = succeeded["extra"]["manager_run"]
        self.assertEqual(
            set(manager_run),
            {
                "manager_run_id",
                "host",
                "manager_seq",
                "state",
                "started_at",
                "finished_at",
                "duration_ms",
                "last_success_at",
                "last_failure_at",
                "failure_streak_started_at",
                "consecutive_failures",
                "recovered_failures",
                "poll_interval_seconds",
                "sample_interval_seconds",
                "actions_seen",
                "process",
            },
        )
        self.assertEqual(
            set(manager_run["process"]),
            {"held", "alive", "exited", "unknown", "truncated"},
        )
        self.assertEqual(succeeded["member_id"], "unknown")
        self.assertEqual(succeeded["instance_id"], "unknown")
        self.assertEqual(succeeded["project_id"], PROJECT)
        self.assertRegex(manager_run["manager_run_id"], r"^mgr-[0-9a-f]{32}$")

        launch = launches[0]
        launch_process = launch["extra"]["launch_process"]
        self.assertEqual(
            set(launch_process),
            {
                "manager_run_id",
                "manager_seq",
                "launch_id",
                "state",
                "observed_at",
                "exit_code",
            },
        )
        self.assertEqual(launch["member_id"], MEMBER)
        self.assertEqual(launch["instance_id"], INSTANCE)
        self.assertEqual(launch["launch_id"], LAUNCH)
        self.assertEqual(launch_process["manager_run_id"], manager_run["manager_run_id"])
        self.assertEqual(launch_process["manager_seq"], manager_run["manager_seq"])
        self.assertEqual(launch["pid"], os.getpid())
        self.assertNotIn("received_at", json.dumps(succeeded, ensure_ascii=False))

    def test_cli_summary_hides_extra_and_detail_shows_fixed_objects(self):
        root = self._write_one_round()
        summary_out, summary_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(summary_out), contextlib.redirect_stderr(
            summary_err
        ):
            code = diagnostics_cli_main(
                [
                    "--log-dir",
                    str(root),
                    "--event",
                    evidence.MANAGER_EVENT,
                    "--limit",
                    "20",
                    "--json",
                ]
            )
        self.assertEqual(code, 0)
        summary = json.loads(summary_out.getvalue())
        self.assertTrue(summary["records"])
        for record in summary["records"]:
            self.assertNotIn("extra", record)
            self.assertNotIn("manager_run", json.dumps(record, ensure_ascii=False))

        detail_out, detail_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(detail_out), contextlib.redirect_stderr(
            detail_err
        ):
            code = diagnostics_cli_main(
                [
                    "--log-dir",
                    str(root),
                    "--event",
                    evidence.MANAGER_EVENT,
                    "--limit",
                    "20",
                    "--json",
                    "--detail",
                ]
            )
        self.assertEqual(code, 0)
        detail = json.loads(detail_out.getvalue())
        manager_runs = [
            record["extra"]["manager_run"] for record in detail["records"]
        ]
        self.assertEqual(len(manager_runs), 2)
        for manager_run in manager_runs:
            self.assertEqual(len(manager_run), 16)
            self.assertEqual(len(manager_run["process"]), 5)

    def test_role_scope_projection_rejects_manager_and_hides_extra(self):
        from server.runtime_diagnostics_query import (
            ProjectionFailure,
            project_detail,
        )

        root = self._write_one_round()
        managers = runtime_diag.query_records(
            root=root, event=evidence.MANAGER_EVENT, limit=20
        )["records"]
        launches = runtime_diag.query_records(
            root=root, event=evidence.LAUNCH_EVENT, limit=20
        )["records"]
        manager_record = managers[-1]
        with self.assertRaises(ProjectionFailure):
            project_detail(manager_record, (PROJECT, MEMBER))
        launch_detail = project_detail(launches[0], (PROJECT, MEMBER))
        dumped = launch_detail.model_dump()
        self.assertNotIn("extra", dumped)
        self.assertNotIn("manager_run", json.dumps(dumped, ensure_ascii=False))

    def test_export_projection_drops_new_extra_in_role_scope(self):
        from server.runtime_diagnostics_export import (
            build_export,
            parse_export_time,
        )
        from server.runtime_diagnostics_query import Source

        pinned = datetime(2026, 10, 18, 19, 0, tzinfo=timezone.utc)
        export_root = self.root / "export-logs"
        writer = runtime_diag.RuntimeDiagnostics(
            member_id=MEMBER,
            instance_id=INSTANCE,
            root=export_root,
            project_id=PROJECT,
            launch_id=LAUNCH,
            runtime="dsh",
            clock=lambda: pinned,
        )
        writer.record_event(
            "launch_process_snapshot",
            phase="serve",
            stage="process",
            extra={
                "launch_process": {
                    "manager_run_id": "mgr-" + "a" * 32,
                    "manager_seq": 1,
                    "launch_id": LAUNCH,
                    "state": "alive",
                    "observed_at": pinned.isoformat(),
                    "exit_code": None,
                }
            },
        )
        writer.close()
        body = build_export(
            Source(PROJECT, MEMBER, export_root),
            project_id=PROJECT,
            member_id=MEMBER,
            since=parse_export_time("2026-10-18T00:00:00Z"),
            until=parse_export_time("2026-10-20T00:00:00Z"),
            generated_at=pinned,
        )
        lines = [
            json.loads(line)
            for line in body.decode("utf-8").splitlines()
            if line.strip()
        ]
        meta, events = lines[0], lines[1:]
        self.assertEqual(meta["record_count"], 1)
        self.assertEqual(events[0]["event"], "launch_process_snapshot")
        self.assertNotIn("extra", events[0])
        self.assertNotIn(
            "manager_run", json.dumps(events[0], ensure_ascii=False)
        )

    def test_disabled_recorder_does_not_observe_or_write(self):
        diagnostics = MemoryDiagnostics(enabled=False)
        process = PollProcess()
        _, handle = make_handle(process=process)
        recorder = make_recorder(
            handles={LAUNCH: handle}, diagnostics=diagnostics
        )
        run_round(recorder)
        self.assertEqual(diagnostics.records, [])
        self.assertEqual(process.calls, 0)
        self.assertFalse(recorder.enabled)


# ---------------------------------------------------------------------------
# 真实 serve 集成（假客户端、无真实网络/动作）
# ---------------------------------------------------------------------------


class ServeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="talk282-serve-")
        self.root = Path(self._tmp.name)
        self.client = SilentClient()
        self.manager = host.HostManager(
            self.client,
            host=HOST,
            state_dir=self.root / "state",
            operator_key="fake-operator",
            project_root=self.root,
            ready_timeout=0.01,
            stop_timeout=0.01,
            runtime_log_dir=self.root / "logs",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _records(self, event):
        return runtime_diag.query_records(
            root=self.root / "logs", event=event, limit=200
        )["records"]

    def test_once_and_max_rounds_stop_reasons_and_snapshot_once(self):
        outcomes = self.manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertEqual(outcomes, [])
        stopped = self._records("host_stopped")
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["extra"]["stop_reason"], "once")
        self.assertRegex(
            stopped[0]["extra"]["manager_run_id"], r"^mgr-[0-9a-f]{32}$"
        )
        managers = self._records(evidence.MANAGER_EVENT)
        self.assertEqual(len(managers), 2)
        self.assertEqual(
            [record["extra"]["manager_run"]["state"] for record in managers],
            ["started", "succeeded"],
        )

    def test_max_rounds_stop_reason(self):
        outcomes = self.manager.serve(
            PROJECT, poll_interval=0, max_rounds=3
        )
        self.assertEqual(outcomes, [])
        stopped = self._records("host_stopped")
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["extra"]["stop_reason"], "max_rounds")
        self.assertEqual(stopped[0]["extra"]["rounds"], 3)

    def test_poll_failure_then_recovery_snapshots(self):
        with patch.object(
            self.manager,
            "claimable_actions",
            side_effect=[host.HostError("http_unavailable"), []],
        ):
            outcomes = self.manager.serve(
                PROJECT, poll_interval=0, max_rounds=2
            )
        self.assertEqual(outcomes[0]["error_code"], "http_unavailable")
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual(
            [item["state"] for item in managers],
            ["started", "failed", "succeeded"],
        )
        self.assertEqual(managers[1]["consecutive_failures"], 1)
        self.assertEqual(managers[2]["recovered_failures"], 1)
        self.assertEqual(
            managers[2]["failure_streak_started_at"],
            managers[1]["finished_at"],
        )

    def test_cancel_during_poll_writes_canceled_and_preserves_object(self):
        failure = KeyboardInterrupt()
        with patch.object(
            self.manager, "claimable_actions", side_effect=failure
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertIs(caught.exception, failure)
        stopped = self._records("host_stopped")
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["extra"]["stop_reason"], "canceled")
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual(
            [item["state"] for item in managers], ["started", "canceled"]
        )

    def test_recoverable_action_exception_keeps_round_succeeded(self):
        action = {
            "action": "start",
            "launch_id": "launch-action-failed",
            "member_id": MEMBER,
        }
        with patch.object(
            self.manager, "claimable_actions", return_value=[action]
        ), patch.object(
            self.manager,
            "execute_start",
            side_effect=host.HostError("http_unavailable"),
        ):
            outcomes = self.manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertEqual(outcomes[0]["outcome"], "failed")
        self.assertEqual(outcomes[0]["error_code"], "http_unavailable")
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual(
            [item["state"] for item in managers], ["started", "succeeded"]
        )
        self.assertEqual(managers[-1]["consecutive_failures"], 0)
        self.assertEqual(managers[-1]["actions_seen"], 1)
        self.assertEqual(len(self._records("action_failed")), 1)

    def test_unhandled_action_exception_preserves_object_and_no_succeeded(self):
        action = {
            "action": "start",
            "launch_id": "launch-action-error",
            "member_id": MEMBER,
        }
        failure = RuntimeError("unhandled action")
        with patch.object(
            self.manager, "claimable_actions", return_value=[action]
        ), patch.object(
            self.manager, "execute_start", side_effect=failure
        ):
            with self.assertRaises(RuntimeError) as caught:
                self.manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertIs(caught.exception, failure)
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual([item["state"] for item in managers], ["started"])
        self.assertEqual(
            self._records("host_stopped")[0]["extra"]["stop_reason"],
            "exception",
        )

    def test_system_exit_cancel_preserves_code(self):
        failure = SystemExit(7)
        with patch.object(
            self.manager, "claimable_actions", side_effect=failure
        ):
            with self.assertRaises(SystemExit) as caught:
                self.manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertIs(caught.exception, failure)
        self.assertEqual(caught.exception.code, 7)
        self.assertEqual(
            self._records("host_stopped")[0]["extra"]["stop_reason"],
            "canceled",
        )
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual(
            [item["state"] for item in managers], ["started", "canceled"]
        )

    def test_cancel_during_worker_finalize_does_not_duplicate_canceled(self):
        worker = type(
            "Worker",
            (),
            {"io_budget_seconds": 0.01, "timeout_seconds": 0.01},
        )()
        failure = KeyboardInterrupt()
        with patch.object(
            self.manager,
            "_start_worker_round",
            return_value=(object(), {"outcomes": []}),
        ), patch.object(
            self.manager, "_collect_worker_round", return_value=None
        ), patch.object(
            self.manager, "_finish_worker_round", side_effect=failure
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.manager.serve(
                    PROJECT,
                    poll_interval=0,
                    once=True,
                    provision_worker=worker,
                )
        self.assertIs(caught.exception, failure)
        self.assertEqual(
            self._records("host_stopped")[0]["extra"]["stop_reason"],
            "canceled",
        )
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual(
            [item["state"] for item in managers], ["started", "succeeded"]
        )

    def test_exception_during_worker_finalize_preserves_object(self):
        worker = type(
            "Worker",
            (),
            {"io_budget_seconds": 0.01, "timeout_seconds": 0.01},
        )()
        failure = RuntimeError("worker finalize")
        with patch.object(
            self.manager,
            "_start_worker_round",
            return_value=(object(), {"outcomes": []}),
        ), patch.object(
            self.manager, "_collect_worker_round", return_value=None
        ), patch.object(
            self.manager, "_finish_worker_round", side_effect=failure
        ):
            with self.assertRaises(RuntimeError) as caught:
                self.manager.serve(
                    PROJECT,
                    poll_interval=0,
                    once=True,
                    provision_worker=worker,
                )
        self.assertIs(caught.exception, failure)
        self.assertEqual(
            self._records("host_stopped")[0]["extra"]["stop_reason"],
            "exception",
        )
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual(
            [item["state"] for item in managers], ["started", "succeeded"]
        )

    def test_cancel_during_sleep_does_not_duplicate_completed_round(self):
        with patch.object(
            host.time, "sleep", side_effect=KeyboardInterrupt()
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.serve(PROJECT, poll_interval=1, once=False)
        stopped = self._records("host_stopped")
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["extra"]["stop_reason"], "canceled")
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual(
            [item["state"] for item in managers], ["started", "succeeded"]
        )

    def test_unhandled_exception_preserves_object_and_marks_exception(self):
        failure = RuntimeError("boom")
        with patch.object(
            self.manager, "claimable_actions", side_effect=failure
        ):
            with self.assertRaises(RuntimeError) as caught:
                self.manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertIs(caught.exception, failure)
        stopped = self._records("host_stopped")
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["extra"]["stop_reason"], "exception")
        managers = [
            record["extra"]["manager_run"]
            for record in self._records(evidence.MANAGER_EVENT)
        ]
        self.assertEqual([item["state"] for item in managers], ["started"])

    def test_recorder_init_failure_does_not_change_business_result(self):
        with patch.object(
            evidence,
            "LoopEvidenceRecorder",
            side_effect=RuntimeError("init failed"),
        ):
            outcomes = self.manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertEqual(outcomes, [])
        self.assertEqual(len(self._records("host_stopped")), 1)
        self.assertEqual(self._records(evidence.MANAGER_EVENT), [])

    def test_worker_outcomes_still_collected_with_evidence_enabled(self):
        class Worker:
            io_budget_seconds = 0.01
            timeout_seconds = 0.01

            def run_round(self):
                return [
                    {
                        "stage": "worker",
                        "outcome": "ready",
                        "error_code": None,
                    }
                ]

            def request_stop(self):
                return None

        outcomes = self.manager.serve(
            PROJECT,
            poll_interval=0,
            once=True,
            provision_worker=Worker(),
        )
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["action"], "provision-worker")
        self.assertEqual(outcomes[0]["outcome"], "ready")
        stopped = self._records("host_stopped")
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["extra"]["stop_reason"], "once")

    def test_real_short_lived_popen_is_observed_by_serve(self):
        process = subprocess.Popen(
            [PYTHON_EXECUTABLE, "-c", "import time; time.sleep(0.2)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        launch_id = "launch-serve-popen"
        record = {
            "project_id": PROJECT,
            "host": HOST,
            "launch_id": launch_id,
            "member_id": MEMBER,
            "instance_id": INSTANCE,
            "pid": process.pid,
            "runtime": "dsh",
        }
        self.manager._handles[launch_id] = {
            "process": process,
            "record": record,
            "record_persisted": False,
        }
        try:
            self.manager.serve(PROJECT, poll_interval=0, once=True)
            launches = self._records(evidence.LAUNCH_EVENT)
            self.assertEqual(len(launches), 1)
            self.assertEqual(
                launches[0]["extra"]["launch_process"]["state"], "alive"
            )
            process.wait(timeout=10)
            clock_result = self.manager.serve(
                PROJECT, poll_interval=0, once=True
            )
            self.assertEqual(clock_result, [])
            launches = self._records(evidence.LAUNCH_EVENT)
            exited = [
                item
                for item in launches
                if item["extra"]["launch_process"]["state"] == "exited"
            ]
            self.assertTrue(exited)
            self.assertEqual(exited[-1]["extra"]["launch_process"]["exit_code"], 0)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            self.manager._handles.pop(launch_id, None)


class _ReviewWriter:
    enabled = True
    def __init__(self):
        self.records = []
    def record_event(self, event, **kwargs):
        self.records.append({'event': event, **kwargs})
        return 'test-ref'
    def record_exception(self, exc, **kwargs):
        return self.record_event(kwargs.pop('event', 'error'), **kwargs)
    def add_sensitive_values(self, values):
        pass


class _ReviewClock:
    def __init__(self):
        self.mono = 0.0
    def wall(self):
        return datetime(2026, 10, 20, tzinfo=timezone.utc) + timedelta(seconds=self.mono)


class _ReviewProcess:
    def __init__(self, pid=123):
        self.pid, self.calls = pid, 0
    def poll(self):
        self.calls += 1
        return None


def _review_handles(count, host_name='probe-host'):
    return {f'launch-{n}': {'process': _ReviewProcess(n + 1), 'record': {
        'project_id': 'prj_probe', 'host': host_name, 'launch_id': f'launch-{n}',
        'pid': n + 1, 'member_id': 'agent:probe', 'instance_id': f'ins_{n}', 'runtime': 'dsh'}}
        for n in range(count)}


def _review_recorder(clock, writer, state=None, launch_writer=None, **kwargs):
    return evidence.LoopEvidenceRecorder(project_id='prj_probe', host=kwargs.pop('host_name', 'probe-host'),
        poll_interval=1, manager_diagnostics=writer, handles=state or {},
        launch_writer=(lambda record: launch_writer) if launch_writer else None,
        monotonic_clock=kwargs.pop('mono', lambda: clock.mono), wall_clock=kwargs.pop('wall', clock.wall), **kwargs)


def _review_runs(writer):
    return [r['extra']['manager_run'] for r in writer.records if r['event'] == evidence.MANAGER_EVENT]


class IndependentBoundaryReviewTests(unittest.TestCase):
    def test_native_negative_exit_code_keeps_platform_value(self):
        process = subprocess.Popen([PYTHON_EXECUTABLE, "-c", "import sys; sys.exit(-1)"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            code = process.wait(timeout=10)
            self.assertEqual(code, 2**32 - 1 if os.name == "nt" else 255)
            clock, writer, launches = _ReviewClock(), _ReviewWriter(), _ReviewWriter()
            state = _review_handles(1)
            state["launch-0"]["process"] = process
            state["launch-0"]["record"]["pid"] = process.pid
            rec = _review_recorder(clock, writer, state, launches)
            rec.begin_round()
            rec.finish_round(poll_ok=True)
            observation = launches.records[-1]["extra"]["launch_process"]
            self.assertEqual(observation["state"], "exited")
            self.assertEqual(observation["exit_code"], code)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)

    def test_poll_cannot_rewrite_captured_launch_identity(self):
        clock, writer, launches = _ReviewClock(), _ReviewWriter(), _ReviewWriter()
        state = _review_handles(1)
        record = state["launch-0"]["record"]
        record["owner_token"] = "synthetic-owner-not-projected"
        def poll():
            record["member_id"] = "agent:changed"
            return None
        state["launch-0"]["process"].poll = poll
        captured = []
        def launch_writer(identity):
            captured.append(dict(identity))
            return launches
        rec = evidence.LoopEvidenceRecorder(project_id="prj_probe", host="probe-host",
            poll_interval=1, manager_diagnostics=writer, handles=state,
            launch_writer=launch_writer, wall_clock=clock.wall, monotonic_clock=lambda: clock.mono)
        rec.begin_round()
        rec.finish_round(poll_ok=True)
        self.assertEqual(captured[0]["member_id"], "agent:probe")
        self.assertNotIn("owner_token", captured[0])

    def test_host_start_has_same_manager_run_identity_as_end(self):
        class Client:
            base_url, timeout = 'http://isolated.invalid', 1
            def request(self, method, path, **kwargs):
                return {'data': []}
        with tempfile.TemporaryDirectory() as temp:
            manager = host.HostManager(Client(), host='probe-host', state_dir=Path(temp) / 'state',
                project_root=Path(temp), runtime_log_disabled=True)
            writer = _ReviewWriter()
            with patch.object(manager, '_manager_diagnostics', return_value=writer):
                manager.serve('prj_probe', once=True)
            started = next(r for r in writer.records if r['event'] == 'host_started')
            stopped = next(r for r in writer.records if r['event'] == 'host_stopped')
            self.assertEqual(started['extra'].get('manager_run_id'), stopped['extra']['manager_run_id'])
            self.assertIsInstance(started['extra'].get('manager_run_id'), str)

    def test_bad_monotonic_does_not_publish_invalid_terminal(self):
        for bad in (float('nan'), float('inf'), -1.0):
            with self.subTest(bad=bad):
                clock, writer = _ReviewClock(), _ReviewWriter()
                sequence = iter((10.0, bad))
                rec = _review_recorder(clock, writer, mono=lambda: next(sequence))
                rec.begin_round()
                rec.finish_round(poll_ok=True)
                terminal = [r for r in _review_runs(writer) if r['state'] != 'started']
                self.assertEqual(terminal, [], 'terminal duration is unknowable: drop rather than violate schema')

    def test_unknown_first_failure_time_does_not_publish_invalid_streak(self):
        clock, writer = _ReviewClock(), _ReviewWriter()
        wall = iter((clock.wall(), None, clock.wall(), clock.wall()))
        rec = _review_recorder(clock, writer, wall=lambda: next(wall))
        for _ in range(2):
            rec.begin_round()
            rec.finish_round(poll_ok=False)
        for run in _review_runs(writer):
            if run['consecutive_failures']:
                self.assertIsNotNone(run['failure_streak_started_at'])

    def test_handles_after_256_are_not_permanently_starved(self):
        clock, writer, launches = _ReviewClock(), _ReviewWriter(), _ReviewWriter()
        state = _review_handles(300)
        rec = _review_recorder(clock, writer, state, launches)
        for _ in range(20):
            before = sum(h['process'].calls for h in state.values())
            rec.begin_round()
            rec.finish_round(poll_ok=True)
            self.assertLessEqual(sum(h['process'].calls for h in state.values()) - before, 32)
            clock.mono += 60
        seen = {r['extra']['launch_process']['launch_id'] for r in launches.records}
        self.assertEqual(seen, set(state), 'fixed first256 metadata window starves later original _review_handles')

    def test_invalid_identity_or_pid_never_gets_role_record(self):
        for field, value in (('member_id', '../agent'), ('instance_id', 'ins_bad\n'),
                             ('launch_id', '../launch'), ('pid', 0)):
            with self.subTest(field=field):
                clock, writer, launches = _ReviewClock(), _ReviewWriter(), _ReviewWriter()
                state = _review_handles(1)
                item = state.pop('launch-0')
                item['record'][field] = value
                if field == 'pid':
                    item['process'].pid = 0
                key = value if field == 'launch_id' else 'launch-0'
                state[key] = item
                rec = _review_recorder(clock, writer, state, launches)
                rec.begin_round()
                rec.finish_round(poll_ok=True)
                self.assertEqual(launches.records, [])

    def test_display_host_truncation_does_not_change_raw_scope(self):
        clock, writer, launches = _ReviewClock(), _ReviewWriter(), _ReviewWriter()
        host_name = 'host-' + 'a' * 220
        rec = _review_recorder(clock, writer, _review_handles(1, host_name), launches, host_name=host_name)
        rec.begin_round()
        rec.finish_round(poll_ok=True)
        terminal = [r for r in _review_runs(writer) if r['state'] == 'succeeded']
        self.assertEqual(terminal[-1]['process']['held'], 1)
        self.assertEqual(len(launches.records), 1)

if __name__ == "__main__":
    unittest.main()
