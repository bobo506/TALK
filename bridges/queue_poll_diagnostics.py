#!/usr/bin/env python3
"""接单轮询的低成本诊断：周期快照、连续查询失败与恢复事件。

本模块只服务通用 CLI bridge 的 ``run_task_queue_worker``。一次“轮询”仅指：

* 可选的过期任务回收；
* 查询本人 queued 任务；
* 既有工作流筛选与按 id 排序。

成功在任务锁、预检和模型执行之前记录；任务执行慢、持锁或模型等待不会产生
新的查询成功。所有记录都写入现有 ``talk-runtime-diagnostics-1`` 的
``extra.queue_poll``，不改变持久根 schema。

设计约束：

* 首次轮询必须可观察；
* 正常成功快照用单调时钟限频，每 30 秒最多一组开始/结束；
* 失败、恢复与取消证据不受成功快照限频影响；
* ``poll_seq`` 只在真正开始查询时递增；
* ``asyncio.CancelledError`` 只记录取消事实，不计失败或恢复；
* 诊断写入失败绝不打断查询、取消或调用方的业务异常。
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

QUEUE_POLL_KEY = "queue_poll"
SNAPSHOT_EVENT = "queue_poll_snapshot"
RECOVERED_EVENT = "queue_poll_recovered"
PHASE = "queue"
STAGE = "queue_poll"
INTERVAL_SECONDS = 30

STARTED = "started"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELED = "canceled"
STATES = frozenset({STARTED, SUCCEEDED, FAILED, CANCELED})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def monotonic_now() -> float:
    return time.monotonic()


def _aware(value: Any) -> datetime:
    if not isinstance(value, datetime):
        value = utc_now()
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def utc_text(value: datetime | None) -> str | None:
    """Normalize an aware datetime to a UTC ``Z`` string."""
    if value is None:
        return None
    text = _aware(value).astimezone(timezone.utc).isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def _safe_wall_clock(clock: Any) -> datetime:
    try:
        return _aware(clock())
    except Exception:
        return utc_now()


def _safe_monotonic(clock: Any) -> float:
    try:
        return float(clock())
    except Exception:
        try:
            return time.monotonic()
        except Exception:
            return 0.0


def _duration_ms(started: float, finished: float) -> float:
    try:
        value = (float(finished) - float(started)) * 1000.0
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return round(max(0.0, value), 3)


class QueuePollCycle:
    """One真实开始的查询轮次；由 :class:`QueuePollRecorder` 创建。"""

    __slots__ = (
        "seq",
        "started_at",
        "started_text",
        "started_mono",
        "sample_start",
        "start_emitted",
        "active",
    )

    def __init__(
        self,
        seq: int,
        *,
        started_at: datetime,
        started_mono: float,
        sample_start: bool,
    ) -> None:
        self.seq = seq
        self.started_at = started_at
        self.started_text = utc_text(started_at) or utc_text(utc_now()) or ""
        self.started_mono = started_mono
        self.sample_start = bool(sample_start)
        self.start_emitted = False
        self.active = True


class QueuePollRecorder:
    """Per-worker poll sequence and failure/recovery state (best effort only)."""

    def __init__(
        self,
        diagnostics: Any | None = None,
        *,
        budgets: dict[str, Any] | None = None,
        wall_clock: Any | None = None,
        monotonic: Any | None = None,
    ) -> None:
        self.diagnostics = diagnostics
        self.budgets = budgets
        self._wall_clock = wall_clock or utc_now
        self._monotonic = monotonic or monotonic_now
        self._seq = 0
        self._last_success_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._streak_started_at: datetime | None = None
        self._consecutive_failures = 0
        self._recent_error_log_id: str | None = None
        self._last_sampled_success_mono: float | None = None
        self._active: QueuePollCycle | None = None

    @property
    def poll_seq(self) -> int:
        return self._seq

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def begin(self) -> QueuePollCycle:
        """Record the true start of one query discovery cycle."""
        started_at = _safe_wall_clock(self._wall_clock)
        started_mono = _safe_monotonic(self._monotonic)
        self._seq += 1
        in_failure_streak = self._consecutive_failures > 0
        due = (
            self._last_sampled_success_mono is None
            or started_mono - self._last_sampled_success_mono >= INTERVAL_SECONDS
        )
        cycle = QueuePollCycle(
            self._seq,
            started_at=started_at,
            started_mono=started_mono,
            sample_start=in_failure_streak or due,
        )
        self._active = cycle
        if cycle.sample_start:
            self._emit_started(cycle)
        return cycle

    def succeed(self, cycle: QueuePollCycle | None) -> None:
        """Finish one discovery cycle successfully (before any task lock)."""
        if cycle is None or not cycle.active:
            return
        cycle.active = False
        self._active = None
        finished_at = _safe_wall_clock(self._wall_clock)
        finished_mono = _safe_monotonic(self._monotonic)
        duration = _duration_ms(cycle.started_mono, finished_mono)
        try:
            if self._consecutive_failures > 0:
                recovered = self._consecutive_failures
                streak_started_at = self._streak_started_at
                self._ensure_started(cycle)
                self._last_success_at = finished_at
                self._consecutive_failures = 0
                self._streak_started_at = None
                self._last_sampled_success_mono = finished_mono
                snapshot = self._snapshot(
                    cycle,
                    SUCCEEDED,
                    finished_at=finished_at,
                    duration_ms=duration,
                    failure_streak_started_at=streak_started_at,
                    consecutive_failures=0,
                    recovered_failures=recovered,
                )
                self._emit(RECOVERED_EVENT, snapshot, "info")
                return
            self._last_success_at = finished_at
            if not cycle.sample_start:
                return
            snapshot = self._snapshot(
                cycle,
                SUCCEEDED,
                finished_at=finished_at,
                duration_ms=duration,
                failure_streak_started_at=None,
                consecutive_failures=0,
                recovered_failures=0,
            )
            self._last_sampled_success_mono = finished_mono
            self._emit(SNAPSHOT_EVENT, snapshot, "info")
        except Exception:
            # Diagnostics are observational; never affect the worker loop.
            return

    def fail(self, cycle: QueuePollCycle | None, error_log_id: str | None = None) -> None:
        """Record one ordinary query-discovery failure once."""
        if cycle is None or not cycle.active:
            return
        cycle.active = False
        self._active = None
        finished_at = _safe_wall_clock(self._wall_clock)
        finished_mono = _safe_monotonic(self._monotonic)
        duration = _duration_ms(cycle.started_mono, finished_mono)
        try:
            self._ensure_started(cycle)
            if self._consecutive_failures == 0:
                self._streak_started_at = finished_at
                # The table's ``error_log_id`` is the current/recent failure
                # segment's original exception.  Each individual failure still
                # has its own full ``queue_worker_exception`` record; later
                # failures in the same streak never overwrite this first ref.
                self._recent_error_log_id = (
                    error_log_id
                    if isinstance(error_log_id, str) and error_log_id
                    else None
                )
            self._consecutive_failures += 1
            self._last_failure_at = finished_at
            snapshot = self._snapshot(
                cycle,
                FAILED,
                finished_at=finished_at,
                duration_ms=duration,
                failure_streak_started_at=self._streak_started_at,
                consecutive_failures=self._consecutive_failures,
                recovered_failures=0,
            )
            self._emit(SNAPSHOT_EVENT, snapshot, "error")
        except Exception:
            return

    def cancel(self, cycle: QueuePollCycle | None) -> None:
        """Record cancellation of an in-flight query; never a failure/recovery."""
        if cycle is None or not cycle.active:
            return
        cycle.active = False
        self._active = None
        finished_at = _safe_wall_clock(self._wall_clock)
        finished_mono = _safe_monotonic(self._monotonic)
        duration = _duration_ms(cycle.started_mono, finished_mono)
        try:
            self._ensure_started(cycle)
            snapshot = self._snapshot(
                cycle,
                CANCELED,
                finished_at=finished_at,
                duration_ms=duration,
                failure_streak_started_at=self._streak_started_at,
                consecutive_failures=self._consecutive_failures,
                recovered_failures=0,
            )
            self._emit(SNAPSHOT_EVENT, snapshot, "warning")
        except Exception:
            return

    def _ensure_started(self, cycle: QueuePollCycle) -> None:
        if cycle.start_emitted:
            return
        self._emit_started(cycle)

    def _emit_started(self, cycle: QueuePollCycle) -> None:
        if cycle.start_emitted:
            return
        cycle.start_emitted = True
        try:
            snapshot = self._snapshot(
                cycle,
                STARTED,
                finished_at=None,
                duration_ms=None,
                failure_streak_started_at=self._streak_started_at,
                consecutive_failures=self._consecutive_failures,
                recovered_failures=0,
            )
            self._emit(SNAPSHOT_EVENT, snapshot, "info")
        except Exception:
            return

    def _snapshot(
        self,
        cycle: QueuePollCycle,
        state: str,
        *,
        finished_at: datetime | None,
        duration_ms: float | None,
        failure_streak_started_at: datetime | None,
        consecutive_failures: int,
        recovered_failures: int,
    ) -> dict[str, Any]:
        # The exact fixed 12-key object, in contract order. No free text.
        return {
            "poll_seq": cycle.seq,
            "state": state,
            "started_at": cycle.started_text,
            "finished_at": utc_text(finished_at),
            "duration_ms": duration_ms,
            "last_success_at": utc_text(self._last_success_at),
            "last_failure_at": utc_text(self._last_failure_at),
            "failure_streak_started_at": utc_text(failure_streak_started_at),
            "consecutive_failures": int(consecutive_failures),
            "recovered_failures": int(recovered_failures),
            "error_log_id": self._recent_error_log_id,
            "interval_seconds": INTERVAL_SECONDS,
        }

    def _emit(
        self,
        event: str,
        snapshot: dict[str, Any],
        severity: str,
    ) -> None:
        writer = self.diagnostics
        if writer is None:
            return
        try:
            writer.record_event(
                event,
                severity=severity,
                phase=PHASE,
                stage=STAGE,
                budgets=self.budgets,
                extra={QUEUE_POLL_KEY: snapshot},
            )
        except Exception:
            # A broken diagnostics writer must not change query/cancel behavior,
            # and a failed failure record must never be reported as success.
            return


__all__ = [
    "QUEUE_POLL_KEY",
    "SNAPSHOT_EVENT",
    "RECOVERED_EVENT",
    "PHASE",
    "STAGE",
    "INTERVAL_SECONDS",
    "STATES",
    "QueuePollCycle",
    "QueuePollRecorder",
    "monotonic_now",
    "utc_now",
    "utc_text",
]
