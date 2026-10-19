#!/usr/bin/env python3
"""Small, fail-open helpers for paired runtime diagnostic stage records.

A stage operation is represented by two persisted events which share one opaque
``operation_id``:

* ``<stage>_started`` with ``extra.transition.status == "started"``;
* ``<stage>_finished`` with one of ``succeeded`` / ``failed`` / ``canceled`` /
  ``interrupted`` / ``unknown`` plus the monotonic ``duration_ms``.

Only ``extra.transition`` is written.  No prompt, argv, environment, HTTP body
or child output is accepted by this module.  The helper deliberately swallows
all logging failures: recording a stage must never replace a business
exception, hide a cancellation, alter task state or stop the caller.

The persisted record schema stays ``talk-runtime-diagnostics-1``; the extra
``transition`` object is the only addition and is projected by the diagnostic
export endpoint.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

TRANSITION_KEY = "transition"
STARTED = "started"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELED = "canceled"
INTERRUPTED = "interrupted"
UNKNOWN = "unknown"

TRANSITION_STATUSES = frozenset(
    {STARTED, SUCCEEDED, FAILED, CANCELED, INTERRUPTED, UNKNOWN}
)
FINAL_STATUSES = frozenset({SUCCEEDED, FAILED, CANCELED, INTERRUPTED, UNKNOWN})

_OPERATION_RE = re.compile(r"^op-[A-Za-z0-9]{8,64}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_text(value: datetime | None) -> str | None:
    """Normalize an aware datetime to a second/microsecond UTC ``Z`` string."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    text = value.astimezone(timezone.utc).isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def new_operation_id() -> str:
    """Opaque operation id; the contract requires the ``op-`` prefix."""
    return f"op-{uuid4().hex}"


def validate_operation_id(value: Any) -> str | None:
    if isinstance(value, str) and _OPERATION_RE.fullmatch(value):
        return value
    return None


def _identifier(value: Any, fallback: str, *, max_chars: int = 64) -> str:
    text = str(value if value is not None else "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:max_chars].strip("_.-")
    if not text or not text[0].isalpha():
        return fallback
    return text


def _attempt(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _duration_ms(start: float, end: float) -> float | None:
    try:
        value = (float(end) - float(start)) * 1000.0
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value):
        return None
    return round(max(0.0, value), 3)


def _transition(
    *,
    operation_id: str,
    status: str,
    from_state: str | None,
    to_state: str | None,
    started_at: str,
    finished_at: str | None,
    duration_ms: float | None,
    attempt: int | None,
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "status": status,
        "from_state": from_state,
        "to_state": to_state,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "attempt": attempt,
    }


class StageOperation:
    """One paired stage; all methods are best-effort and never raise."""

    __slots__ = (
        "stage",
        "phase",
        "task_id",
        "message_id",
        "attempt",
        "budgets",
        "diagnostics",
        "operation_id",
        "started_at",
        "started_text",
        "_started_mono",
        "_wall_clock",
        "_monotonic",
        "_start_log_id",
        "_finish_log_id",
        "_start_emitted",
        "_finished",
        "_abandoned",
    )

    def __init__(
        self,
        stage: str,
        *,
        phase: str | None = None,
        task_id: Any = None,
        message_id: Any = None,
        attempt: Any = None,
        budgets: dict[str, Any] | None = None,
        diagnostics: Any = None,
        wall_clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.stage = _identifier(stage, "unknown_stage")
        self.phase = _identifier(phase, "unknown") if phase is not None else None
        self.task_id = task_id
        self.message_id = message_id
        self.attempt = _attempt(attempt)
        self.budgets = budgets
        self.diagnostics = diagnostics
        self.operation_id = new_operation_id()
        self._wall_clock = wall_clock or utc_now
        self._monotonic = monotonic or time.monotonic
        try:
            self.started_at = self._wall_clock()
            if not isinstance(self.started_at, datetime):
                self.started_at = utc_now()
            if self.started_at.tzinfo is None:
                self.started_at = self.started_at.replace(tzinfo=timezone.utc)
        except Exception:
            self.started_at = utc_now()
        self.started_text = utc_text(self.started_at) or utc_text(utc_now()) or ""
        try:
            self._started_mono = float(self._monotonic())
        except Exception:
            self._started_mono = time.monotonic()
        self._start_log_id: str | None = None
        self._finish_log_id: str | None = None
        self._start_emitted = False
        self._finished = False
        self._abandoned = False

    @property
    def finished(self) -> bool:
        return self._finished

    def _event(
        self,
        suffix: str,
        *,
        severity: str,
        transition: dict[str, Any],
        returncode: Any = None,
        timeout: bool | None = None,
        cancel_category: str | None = None,
        message: Any = None,
        diagnostics: Any = None,
    ) -> str | None:
        writer = self.diagnostics if diagnostics is None else diagnostics
        if writer is None or self._abandoned:
            return None
        try:
            return writer.record_event(
                f"{self.stage}_{suffix}",
                severity=severity,
                phase=self.phase,
                stage=self.stage,
                task_id=self.task_id,
                message_id=self.message_id,
                message=message,
                returncode=returncode,
                timeout=timeout,
                cancel_category=cancel_category,
                budgets=self.budgets,
                extra={TRANSITION_KEY: transition},
            )
        except Exception:
            # Diagnostics must never change the caller's result or exception.
            return None

    def emit_start(self, diagnostics: Any = None) -> str | None:
        if self._abandoned or self._start_emitted:
            return self._start_log_id
        self._start_emitted = True
        self._start_log_id = self._event(
            "started",
            severity="info",
            transition=_transition(
                operation_id=self.operation_id,
                status=STARTED,
                from_state=None,
                to_state=self.stage,
                started_at=self.started_text,
                finished_at=None,
                duration_ms=None,
                attempt=self.attempt,
            ),
            diagnostics=diagnostics,
        )
        return self._start_log_id

    def finish(
        self,
        status: str = SUCCEEDED,
        *,
        diagnostics: Any = None,
        returncode: Any = None,
        timeout: bool | None = None,
        cancel_category: str | None = None,
        message: Any = None,
    ) -> str | None:
        if self._abandoned or self._finished:
            return self._finish_log_id
        self._finished = True
        if not self._start_emitted:
            self.emit_start(diagnostics)
        normalized = status if status in FINAL_STATUSES else UNKNOWN
        try:
            finished_at = self._wall_clock()
            if not isinstance(finished_at, datetime):
                finished_at = utc_now()
            if finished_at.tzinfo is None:
                finished_at = finished_at.replace(tzinfo=timezone.utc)
        except Exception:
            finished_at = utc_now()
        try:
            end_mono = float(self._monotonic())
        except Exception:
            end_mono = self._started_mono
        duration = _duration_ms(self._started_mono, end_mono)
        severity = {
            SUCCEEDED: "info",
            FAILED: "error",
            CANCELED: "warning",
            INTERRUPTED: "warning",
            UNKNOWN: "warning",
        }.get(normalized, "warning")
        if normalized == CANCELED and cancel_category is None:
            cancel_category = "asyncio_cancelled"
        self._finish_log_id = self._event(
            "finished",
            severity=severity,
            transition=_transition(
                operation_id=self.operation_id,
                status=normalized,
                from_state=self.stage,
                to_state=None,
                started_at=self.started_text,
                finished_at=utc_text(finished_at),
                duration_ms=duration,
                attempt=self.attempt,
            ),
            returncode=returncode,
            timeout=timeout,
            cancel_category=cancel_category,
            message=message,
            diagnostics=diagnostics,
        )
        return self._finish_log_id

    def abandon(self) -> None:
        """Drop the operation without writing (used to keep idle polls quiet)."""
        self._abandoned = True


class StageTimeline:
    """Factory for :class:`StageOperation` objects bound to one writer."""

    __slots__ = ("diagnostics", "_wall_clock", "_monotonic")

    def __init__(
        self,
        diagnostics: Any = None,
        *,
        wall_clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.diagnostics = diagnostics
        self._wall_clock = wall_clock or utc_now
        self._monotonic = monotonic or time.monotonic

    def begin(
        self,
        stage: str,
        *,
        phase: str | None = None,
        task_id: Any = None,
        message_id: Any = None,
        attempt: Any = None,
        budgets: dict[str, Any] | None = None,
    ) -> StageOperation:
        return StageOperation(
            stage,
            phase=phase,
            task_id=task_id,
            message_id=message_id,
            attempt=attempt,
            budgets=budgets,
            diagnostics=self.diagnostics,
            wall_clock=self._wall_clock,
            monotonic=self._monotonic,
        )

    def start(
        self,
        stage: str,
        *,
        phase: str | None = None,
        task_id: Any = None,
        message_id: Any = None,
        attempt: Any = None,
        budgets: dict[str, Any] | None = None,
    ) -> StageOperation:
        operation = self.begin(
            stage,
            phase=phase,
            task_id=task_id,
            message_id=message_id,
            attempt=attempt,
            budgets=budgets,
        )
        operation.emit_start()
        return operation


def begin_stage(
    stage: str,
    *,
    phase: str | None = None,
    task_id: Any = None,
    message_id: Any = None,
    attempt: Any = None,
    budgets: dict[str, Any] | None = None,
    diagnostics: Any = None,
) -> StageOperation:
    """Module-level convenience for a deferred or already-bound operation."""
    return StageOperation(
        stage,
        phase=phase,
        task_id=task_id,
        message_id=message_id,
        attempt=attempt,
        budgets=budgets,
        diagnostics=diagnostics,
    )


@asynccontextmanager
async def timed_lock(
    lock: Any,
    *,
    timeline: StageTimeline,
    stage: str,
    phase: str | None = None,
    task_id: Any = None,
    budgets: dict[str, Any] | None = None,
):
    """Record one real lock acquisition; never changes lock semantics."""
    operation = timeline.start(
        stage,
        phase=phase,
        task_id=task_id,
        budgets=budgets,
    )
    try:
        await lock.acquire()
    except asyncio.CancelledError:
        operation.finish("canceled")
        raise
    except BaseException:
        operation.finish("failed")
        raise
    operation.finish("succeeded")
    try:
        yield operation
    finally:
        lock.release()


__all__ = [
    "TRANSITION_KEY",
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "CANCELED",
    "INTERRUPTED",
    "UNKNOWN",
    "TRANSITION_STATUSES",
    "FINAL_STATUSES",
    "StageOperation",
    "StageTimeline",
    "begin_stage",
    "new_operation_id",
    "timed_lock",
    "utc_now",
    "utc_text",
    "validate_operation_id",
]
