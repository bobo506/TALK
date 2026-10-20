#!/usr/bin/env python3
"""宿主本地管理循环与原 Popen 运行证据（任务 282 A 片）。

本模块只做**只读**采样，不改变 ``HostManager.serve`` 的轮询、动作执行、
worker 收尾、异常对象或退出码：

1. 每次真实 ``serve`` 生成独立的 ``mgr-`` + 32 位十六进制 run ID；每个真实
   轮次开始时递增 ``manager_seq``（初值 1），没有后台定时器或假心跳；
2. 在真实 begin/finish 边界按单调时钟固定 60 秒采样。首轮、首个失败完成、
   连续失败周期、真实恢复和取消分别按合同写 ``manager_round_snapshot``；
3. 只在真正要写 terminal 快照时只读观测本进程仍持有的原 Popen 句柄；每次最多
   32 次 ``poll``、最多 256 条元数据检查，轮转选择避免稳定前 32 条饿死后面的
   已核 launch；
4. 仅对 project/host/launch_id/PID/member/instance 全部匹配的原内存 record
   产生 ``launch_process_snapshot``；跨项目、错 launch、错 PID、缺身份一律不
   归入角色，也不按 PID 重新认领进程；
5. 任何日志初始化、时钟、观测或写入失败都只让证据缺失/未知，不向业务抛出。

底层 schema（``talk-runtime-diagnostics-1``）与既有写入器 API 完全不变。新对象
只放在 ``extra.manager_run`` / ``extra.launch_process`` 两个固定键下，且不写
路径、argv、环境、凭据、子进程输出或 ``received_at``。
"""

from __future__ import annotations

import asyncio
import math
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

#: 新事件名（稳定、可过滤；不改变既有事件）。
MANAGER_EVENT = "manager_round_snapshot"
LAUNCH_EVENT = "launch_process_snapshot"

#: 采样间隔固定 60 秒；不是客户端可控配置。
SAMPLE_INTERVAL_SECONDS = 60

#: 序号、失败计数与查询行数上限（10000）完全独立。
MANAGER_SEQ_MAX = 2**53 - 1

#: 一次 terminal 观测的最大 poll 次数和最大元数据检查条数。
MAX_POLLS_PER_SNAPSHOT = 32
MAX_HANDLE_CHECKS = 256

#: terminal 单调耗时上限：31 天毫秒。
MAX_DURATION_MS = 31 * 24 * 60 * 60 * 1000

#: 保留原平台退出码：Windows 允许无符号 32 位错误码。
EXIT_CODE_MIN = -(2**31)
EXIT_CODE_MAX = 2**32 - 1

MANAGER_RUN_ID_PREFIX = "mgr-"
_CANCELLED_ERROR_TYPES = (KeyboardInterrupt, SystemExit, asyncio.CancelledError)


# ---------------------------------------------------------------------------
# 基础事实：ID / 取消 / 时钟 / 数值
# ---------------------------------------------------------------------------


def new_manager_run_id() -> str:
    """生成新的独立 manager run ID（``mgr-`` + 32 位小写十六进制）。"""
    return f"{MANAGER_RUN_ID_PREFIX}{uuid.uuid4().hex}"


def is_cancellation(exc: BaseException) -> bool:
    """取消类异常保持原对象/退出码/控制流，不能被诊断改写。"""
    return isinstance(exc, _CANCELLED_ERROR_TYPES)


def _is_valid_run_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) != len(MANAGER_RUN_ID_PREFIX) + 32:
        return False
    if not value.startswith(MANAGER_RUN_ID_PREFIX):
        return False
    suffix = value[len(MANAGER_RUN_ID_PREFIX):]
    return all(char in "0123456789abcdef" for char in suffix)


def _strict_int(value: Any, minimum: int, maximum: int) -> Optional[int]:
    """严格整数（拒绝 bool），且必须在闭区间内；否则返回 None。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < minimum or value > maximum:
        return None
    return value


def _bounded_text(value: Any, *, limit: int = 200) -> str:
    if value is None:
        return "unknown"
    try:
        text = str(value).strip()
    except Exception:
        return "unknown"
    if not text:
        return "unknown"
    text = "".join(char for char in text if char.isprintable())
    return text[:limit] or "unknown"


def _valid_identity(value: Any, *, colon: bool = False) -> bool:
    if not isinstance(value, str) or value.lower() == "unknown":
        return False
    pattern = r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}" if colon else r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
    return re.fullmatch(pattern, value) is not None


def _valid_manager_payload(payload: Any) -> bool:
    """固定投影：不把不可表示的完成事实写成符合合同的成功。"""
    keys = {"manager_run_id", "host", "manager_seq", "state", "started_at",
            "finished_at", "duration_ms", "last_success_at", "last_failure_at",
            "failure_streak_started_at", "consecutive_failures", "recovered_failures",
            "poll_interval_seconds", "sample_interval_seconds", "actions_seen", "process"}
    if not isinstance(payload, dict) or set(payload) != keys:
        return False
    if not _is_valid_run_id(payload["manager_run_id"]):
        return False
    label = payload["host"]
    if not isinstance(label, str) or not label or len(label) > 200 or not label.isprintable():
        return False
    if _strict_int(payload["manager_seq"], 1, MANAGER_SEQ_MAX) is None:
        return False
    state = payload["state"]
    if not isinstance(state, str) or state not in {"started", "succeeded", "failed", "canceled"}:
        return False
    for name in ("started_at", "finished_at", "last_success_at", "last_failure_at", "failure_streak_started_at"):
        value = payload[name]
        if value is None and name != "started_at":
            continue
        if not isinstance(value, str) or len(value) > 64:
            return False
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return False
        except (ValueError, OverflowError):
            return False
    duration = payload["duration_ms"]
    actions = _strict_int(payload["actions_seen"], 0, MANAGER_SEQ_MAX)
    consecutive = _strict_int(payload["consecutive_failures"], 0, MANAGER_SEQ_MAX)
    recovered = _strict_int(payload["recovered_failures"], 0, MANAGER_SEQ_MAX)
    if actions is None or consecutive is None or recovered is None:
        return False
    if state == "started":
        if payload["finished_at"] is not None or duration is not None or actions != 0:
            return False
    elif payload["finished_at"] is None or _strict_int(duration, 0, MAX_DURATION_MS) is None:
        return False
    if state == "succeeded" and (consecutive != 0 or payload["last_success_at"] != payload["finished_at"]):
        return False
    if state == "failed" and (consecutive == 0 or payload["last_failure_at"] != payload["finished_at"]):
        return False
    if recovered and state != "succeeded":
        return False
    if (consecutive or recovered) and payload["failure_streak_started_at"] is None:
        return False
    if not consecutive and not recovered and payload["failure_streak_started_at"] is not None:
        return False
    if payload["sample_interval_seconds"] != SAMPLE_INTERVAL_SECONDS or isinstance(payload["sample_interval_seconds"], bool):
        return False
    if _valid_poll_interval(payload["poll_interval_seconds"]) is None:
        return False
    process = payload["process"]
    if not isinstance(process, dict) or set(process) != {"held", "alive", "exited", "unknown", "truncated"}:
        return False
    if not isinstance(process["truncated"], bool):
        return False
    counts = [process[name] for name in ("held", "alive", "exited", "unknown")]
    if all(value is None for value in counts):
        return process["truncated"]
    if state == "started":
        return False
    if any(_strict_int(value, 0, MANAGER_SEQ_MAX) is None for value in counts):
        return False
    return counts[0] == sum(counts[1:])


def _wall_iso(value: Any) -> Optional[str]:
    """只接受真实带时区 datetime；坏墙钟不造值。"""
    if not isinstance(value, datetime):
        return None
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        text = value.isoformat()
    except (ValueError, OverflowError, OSError):
        return None
    return text or None


def _read_wall(clock: Callable[[], Any]) -> Optional[str]:
    try:
        return _wall_iso(clock())
    except Exception:
        return None


def _read_monotonic(clock: Callable[[], Any]) -> Optional[float]:
    try:
        value = clock()
    except Exception:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _duration_ms(start: Optional[float], end: Optional[float]) -> Optional[int]:
    if start is None or end is None:
        return None
    if end < start:
        return None
    elapsed = end - start
    if not math.isfinite(elapsed) or elapsed < 0:
        return None
    milliseconds = int(elapsed * 1000)
    if milliseconds < 0 or milliseconds > MAX_DURATION_MS:
        return None
    return milliseconds


def _valid_poll_interval(value: Any) -> Any:
    """只对诊断字段做有限非负清洗；绝不改变原 ``time.sleep`` 参数。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return value


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 采样器
# ---------------------------------------------------------------------------


class LoopEvidenceRecorder:
    """单个 ``serve`` 进程内的本地循环/原 Popen 采样器。

    构造与所有公开方法都不向业务抛 ``Exception``；``BaseException``（取消）仍
    保持原控制流。调用方应在真实 begin/finish 边界调用 ``begin_round``、
    ``finish_round``，取消当前未完成轮时调用 ``cancel_round``。
    """

    def __init__(
        self,
        *,
        project_id: str,
        host: str,
        poll_interval: Any,
        manager_diagnostics: Any = None,
        handles: Optional[Mapping[str, Any]] = None,
        launch_writer: Optional[Callable[[Mapping[str, Any]], Any]] = None,
        manager_run_id: Optional[str] = None,
        wall_clock: Optional[Callable[[], Any]] = None,
        monotonic_clock: Optional[Callable[[], Any]] = None,
    ):
        self.project_id = str(project_id or "")
        # 用原标签核scope；面向日志的清洗/截断不能改变归因条件。
        self._scope_host = host if isinstance(host, str) else None
        self.host = _bounded_text(host)
        self.poll_interval = _valid_poll_interval(poll_interval)
        self.manager_diagnostics = manager_diagnostics
        self.handles = handles if handles is not None else {}
        self.launch_writer = launch_writer
        self._wall = wall_clock if wall_clock is not None else _now_utc
        self._mono = (
            monotonic_clock if monotonic_clock is not None else time.monotonic
        )
        self._run_id = manager_run_id if _is_valid_run_id(manager_run_id) else None
        if self._run_id is None:
            try:
                candidate = new_manager_run_id()
                if _is_valid_run_id(candidate):
                    self._run_id = candidate
            except Exception:
                self._run_id = None
        self._enabled = self._run_id is not None and manager_diagnostics is not None
        if self._enabled:
            try:
                self._enabled = bool(getattr(manager_diagnostics, "enabled", True))
            except Exception:
                self._enabled = False
        self._seq = 0
        self._in_flight = False
        self._round: Optional[dict[str, Any]] = None
        self._last_group_mono: Optional[float] = None
        self._last_failure_terminal_mono: Optional[float] = None
        self._first_terminal_written = False
        self._last_success_at: Optional[str] = None
        self._last_failure_at: Optional[str] = None
        self._failure_streak_started_at: Optional[str] = None
        self._consecutive_failures = 0
        self._counter_overflow = False
        self._observe_cursor: Optional[str] = None
        self._handle_iterator: Any = None
        self._handle_iterator_source: Any = None

    # ── 只读属性 ────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def manager_run_id(self) -> Optional[str]:
        return self._run_id

    @property
    def manager_seq(self) -> int:
        return self._seq

    # ── 真实轮次边界 ────────────────────────────────────────────────

    def begin_round(self) -> Optional[int]:
        """真实轮次开始：递增 seq，并按 60 秒采样规则决定是否写 started。

        不观测任何 Popen，也不在 started 记录中伪造进程计数。
        """
        if not self._enabled:
            return None
        try:
            self._seq += 1
            seq = self._seq
            mono = self._mono_now()
            wall = self._wall_now()
            self._round = {
                "seq": seq,
                "started_at": wall,
                "start_mono": mono,
                "started_written": False,
            }
            self._in_flight = True
            self._reanchor_on_rollback(mono)
            if seq > MANAGER_SEQ_MAX or self._counter_overflow:
                return seq
            due = seq == 1 or self._interval_due(mono, self._last_group_mono)
            if due and wall is not None:
                payload = self._manager_payload(
                    state="started",
                    seq=seq,
                    started_at=wall,
                    finished_at=None,
                    duration_ms=None,
                    last_success_at=self._last_success_at,
                    last_failure_at=self._last_failure_at,
                    failure_streak_started_at=self._failure_streak_started_at,
                    consecutive_failures=self._consecutive_failures,
                    recovered_failures=0,
                    actions_seen=0,
                    process=self._unknown_process(),
                )
                self._write_manager(payload)
                self._round["started_written"] = True
                self._note_group(mono)
            return seq
        except Exception:
            self._in_flight = False
            return None

    def finish_round(self, *, poll_ok: bool, actions_seen: int = 0) -> None:
        """真实整轮完成：更新事实，并按失败/恢复/60 秒规则决定是否写 terminal。

        ``poll_ok=False`` 只表示本轮 ``claimable_actions`` 是可恢复失败；动作的
        可恢复异常仍由既有 ``action_failed`` 记录，不进入这里的失败计数。
        """
        if not self._enabled:
            return
        round_info = self._round
        if not self._in_flight or not isinstance(round_info, dict):
            return
        self._in_flight = False
        reset_success = bool(poll_ok)
        try:
            seq = round_info.get("seq")
            started_at = round_info.get("started_at")
            start_mono = round_info.get("start_mono")
            mono = self._mono_now()
            finished_at = self._wall_now()
            self._reanchor_on_rollback(mono)
            if poll_ok:
                actions = _strict_int(actions_seen, 0, MANAGER_SEQ_MAX)
            else:
                actions = 0

            if finished_at is None:
                # 没有真实完成时刻：只推进内部事实，不写伪造的 terminal。
                if not poll_ok:
                    if self._consecutive_failures == 0:
                        # 新失败段：即使首条时间不可用，也不能让上一段
                        # 的 60 秒限频压住本段第一条可写完成。
                        self._last_failure_terminal_mono = None
                    self._bump_failure()
                return

            if poll_ok:
                self._last_success_at = finished_at
                recovered = self._consecutive_failures
            else:
                self._last_failure_at = finished_at
                if self._consecutive_failures == 0:
                    # 新失败段：首条完成立即写，不受上一段 60 秒限频影响；
                    # 首条完成时间才可作为真实 streak 起点。
                    self._last_failure_terminal_mono = None
                    self._failure_streak_started_at = finished_at
                # 首条时间不可用时 streak 保持 null；后续失败不能拿自己的
                # 时间冒充“真实首轮完成时间”。
                self._bump_failure()
                recovered = 0

            if self._counter_overflow:
                return

            started_this_round = bool(round_info.get("started_written"))
            if poll_ok:
                state = "succeeded"
                should = recovered > 0 or self._success_due(
                    mono, started_this_round
                )
                if recovered > 0 and self._failure_streak_started_at is None:
                    # 无法诚实写出恢复段的真实首败时间；放弃该条。
                    should = False
                if actions is None:
                    # 无法表示真实 poll 条数时不写伪造的 0。
                    should = False
            else:
                state = "failed"
                should = self._failure_due(mono)

            if not should:
                return
            if (
                started_at is None
                or seq is None
                or seq < 1
                or seq > MANAGER_SEQ_MAX
            ):
                return

            duration = _duration_ms(start_mono, mono)
            if duration is None or self.poll_interval is None:
                return
            if self._consecutive_failures and self._failure_streak_started_at is None:
                return
            process = self._observe_and_write_launches(seq)
            payload = self._manager_payload(
                state=state,
                seq=seq,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration,
                last_success_at=(
                    finished_at if poll_ok else self._last_success_at
                ),
                last_failure_at=(
                    self._last_failure_at if poll_ok else finished_at
                ),
                failure_streak_started_at=self._failure_streak_started_at,
                consecutive_failures=(
                    0 if poll_ok else self._consecutive_failures
                ),
                recovered_failures=(recovered if poll_ok else 0),
                actions_seen=actions,
                process=process,
            )
            self._write_manager(payload)
            self._note_group(mono)
            self._first_terminal_written = True
            if not poll_ok:
                if mono is not None:
                    self._last_failure_terminal_mono = mono
        except Exception:
            return
        finally:
            if reset_success:
                # 成功完成即结束失败段；即使记录因坏时钟被跳过也不让后续
                # 每个成功轮都继续冒充“恢复”。
                self._consecutive_failures = 0
                self._failure_streak_started_at = None

    def cancel_round(self, *, actions_seen: int = 0) -> None:
        """取消当前未完成轮：只写 canceled terminal，不补造 started。"""
        if not self._enabled:
            return
        round_info = self._round
        if not self._in_flight or not isinstance(round_info, dict):
            return
        self._in_flight = False
        try:
            seq = round_info.get("seq")
            started_at = round_info.get("started_at")
            start_mono = round_info.get("start_mono")
            mono = self._mono_now()
            finished_at = self._wall_now()
            self._reanchor_on_rollback(mono)
            if (
                finished_at is None
                or started_at is None
                or seq is None
                or seq < 1
                or seq > MANAGER_SEQ_MAX
                or self._counter_overflow
            ):
                return
            actions = _strict_int(actions_seen, 0, MANAGER_SEQ_MAX)
            if actions is None:
                # 无法表示真实 poll 条数时不写伪造的 0。
                return
            duration = _duration_ms(start_mono, mono)
            if duration is None or self.poll_interval is None:
                return
            if self._consecutive_failures and self._failure_streak_started_at is None:
                return
            process = self._observe_and_write_launches(seq)
            payload = self._manager_payload(
                state="canceled",
                seq=seq,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration,
                last_success_at=self._last_success_at,
                last_failure_at=self._last_failure_at,
                failure_streak_started_at=self._failure_streak_started_at,
                consecutive_failures=self._consecutive_failures,
                recovered_failures=0,
                actions_seen=actions,
                process=process,
            )
            self._write_manager(payload)
            self._note_group(mono)
            self._first_terminal_written = True
        except Exception:
            return

    # ── 时钟辅助 ────────────────────────────────────────────────────

    def _wall_now(self) -> Optional[str]:
        return _read_wall(self._wall)

    def _mono_now(self) -> Optional[float]:
        return _read_monotonic(self._mono)

    @staticmethod
    def _interval_due(mono: Optional[float], last: Optional[float]) -> bool:
        if mono is None:
            return False
        if last is None:
            return True
        elapsed = mono - last
        if not math.isfinite(elapsed):
            return False
        return elapsed >= SAMPLE_INTERVAL_SECONDS

    def _reanchor_on_rollback(self, mono: Optional[float]) -> None:
        if mono is None:
            return
        for name in (
            "_last_group_mono",
            "_last_failure_terminal_mono",
        ):
            last = getattr(self, name)
            if last is not None and mono < last:
                # 单调时钟回拨：不以墙钟/0 推测耗时，只重新锚定采样窗。
                setattr(self, name, None)

    def _note_group(self, mono: Optional[float]) -> None:
        if mono is not None:
            self._last_group_mono = mono

    def _success_due(
        self, mono: Optional[float], started_this_round: bool
    ) -> bool:
        if not self._first_terminal_written:
            return True
        if started_this_round:
            # 本轮已写 started；结束记录完成同一组，不额外制造组。
            return True
        # 稳态普通成功沿用 60 秒组间隔；不能因上一次成功更久以前就在
        # 取消/失败后的 60 秒内再写一个无 started 的普通成功组。
        return self._interval_due(mono, self._last_group_mono)

    def _failure_due(self, mono: Optional[float]) -> bool:
        if not self._first_terminal_written:
            return True
        if self._last_failure_terminal_mono is None:
            return True
        return self._interval_due(mono, self._last_failure_terminal_mono)

    def _bump_failure(self) -> None:
        if self._consecutive_failures < MANAGER_SEQ_MAX:
            self._consecutive_failures += 1
        else:
            self._counter_overflow = True

    # ── 固定对象 ────────────────────────────────────────────────────

    @staticmethod
    def _unknown_process() -> dict[str, Any]:
        return {
            "held": None,
            "alive": None,
            "exited": None,
            "unknown": None,
            "truncated": True,
        }

    def _manager_payload(
        self,
        *,
        state: str,
        seq: int,
        started_at: str,
        finished_at: Optional[str],
        duration_ms: Optional[int],
        last_success_at: Optional[str],
        last_failure_at: Optional[str],
        failure_streak_started_at: Optional[str],
        consecutive_failures: int,
        recovered_failures: int,
        actions_seen: int,
        process: dict[str, Any],
    ) -> dict[str, Any]:
        # 固定 16 键；新增字段必须先改合同，不能在这里夹带自由文本。
        return {
            "manager_run_id": self._run_id,
            "host": self.host,
            "manager_seq": seq,
            "state": state,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "last_success_at": last_success_at,
            "last_failure_at": last_failure_at,
            "failure_streak_started_at": failure_streak_started_at,
            "consecutive_failures": consecutive_failures,
            "recovered_failures": recovered_failures,
            "poll_interval_seconds": self.poll_interval,
            "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
            "actions_seen": actions_seen,
            "process": process,
        }

    # ── 写入 ────────────────────────────────────────────────────────

    def _write_manager(self, manager_run: dict[str, Any]) -> bool:
        if not _valid_manager_payload(manager_run):
            return False
        writer = self.manager_diagnostics
        if writer is None or not getattr(writer, "enabled", False):
            return False
        state = str(manager_run.get("state") or "")
        severity = "warning" if state in ("failed", "canceled") else "info"
        try:
            writer.record_event(
                MANAGER_EVENT,
                severity=severity,
                phase="serve",
                stage="loop",
                extra={"manager_run": manager_run},
            )
            return True
        except Exception:
            return False

    def _write_launch_event(
        self, item: Mapping[str, Any], seq: int
    ) -> None:
        observed_at = item.get("observed_at")
        if observed_at is None:
            return
        writer = None
        try:
            if self.launch_writer is not None:
                writer = self.launch_writer(item["record"])
        except Exception:
            writer = None
        if writer is None or not getattr(writer, "enabled", False):
            return
        launch_process = {
            "manager_run_id": self._run_id,
            "manager_seq": seq,
            "launch_id": item["launch_id"],
            "state": item["state"],
            "observed_at": observed_at,
            "exit_code": item["exit_code"],
        }
        severity = "warning" if item["state"] == "unknown" else "info"
        try:
            writer.record_event(
                LAUNCH_EVENT,
                severity=severity,
                phase="serve",
                stage="process",
                extra={"launch_process": launch_process},
            )
        except Exception:
            return

    # ── 原 Popen 只读观测 ───────────────────────────────────────────

    def _observe_and_write_launches(self, seq: int) -> dict[str, Any]:
        process, launches = self._observe_handles()
        for item in launches:
            self._write_launch_event(item, seq)
        return process

    def _observe_handles(
        self,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        unknown = self._unknown_process()
        try:
            handles = self.handles
            if not isinstance(handles, Mapping):
                return unknown, []
            total = len(handles)
            over_limit = total > MAX_HANDLE_CHECKS
            metadata_incomplete = over_limit
            scoped: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
            # 超限时保留原字典迭代位置，每次收集最多32个可观测项。
            # 不固定扫描前256条，也不复制/跳过无界全部句柄。
            if over_limit:
                if self._handle_iterator is None or self._handle_iterator_source is not handles:
                    self._handle_iterator = iter(handles.items())
                    self._handle_iterator_source = handles
                entries = self._handle_iterator
            else:
                self._handle_iterator = None
                self._handle_iterator_source = None
                entries = iter(handles.items())
            eligible = []
            for _ in range(MAX_HANDLE_CHECKS):
                try:
                    key, handle = next(entries)
                except StopIteration:
                    self._handle_iterator = None
                    break
                if not isinstance(key, str) or not isinstance(handle, Mapping):
                    metadata_incomplete = True
                    continue
                record = handle.get("record")
                if not isinstance(record, Mapping):
                    metadata_incomplete = True
                    continue
                project = record.get("project_id")
                if not isinstance(project, str) or not project or project.lower() == "unknown":
                    metadata_incomplete = True
                    continue
                if project != self.project_id:
                    # 明确其它项目：跳过，不读取其进程，也不算入本项目。
                    continue
                host = record.get("host")
                if not isinstance(host, str) or self._scope_host is None:
                    metadata_incomplete = True
                    continue
                if host != self._scope_host:
                    continue
                scoped.append((key, handle, record))
                if self._eligible(key, handle, record):
                    eligible.append((key, handle, record))
                    if over_limit and len(eligible) >= MAX_POLLS_PER_SNAPSHOT:
                        break
            selected = self._select_fair(eligible)
            counts = {"alive": 0, "exited": 0, "unknown": 0}
            launches: list[dict[str, Any]] = []
            for _key, handle, record in selected:
                # 固定身份快照，poll不能让记录中的可变字典改写本条归因。
                identity = {name: record.get(name) for name in (
                    "project_id", "host", "launch_id", "pid", "member_id", "instance_id", "runtime"
                )}
                state_name, exit_code, observed_at = self._poll_process(
                    handle.get("process")
                )
                counts[state_name] += 1
                launches.append(
                    {
                        "record": identity,
                        "launch_id": identity["launch_id"],
                        "state": state_name,
                        "exit_code": exit_code,
                        "observed_at": observed_at,
                    }
                )

            if metadata_incomplete:
                # 无法确定项目内总数：整体未知，绝不伪装精确空集合。
                return unknown, launches

            held = len(scoped)
            unobserved = held - len(selected)
            if unobserved < 0:
                unobserved = 0
            process = {
                "held": held,
                "alive": counts["alive"],
                "exited": counts["exited"],
                "unknown": counts["unknown"] + unobserved,
                "truncated": bool(unobserved > 0),
            }
            if (
                process["held"]
                != process["alive"] + process["exited"] + process["unknown"]
            ):
                return unknown, launches
            return process, launches
        except Exception:
            self._handle_iterator = None
            self._handle_iterator_source = None
            return unknown, []

    def _eligible(
        self,
        key: str,
        handle: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> bool:
        try:
            launch_id = record.get("launch_id")
            if not _valid_identity(launch_id):
                return False
            if key != launch_id:
                return False
            process = handle.get("process")
            pid = getattr(process, "pid", None)
            record_pid = record.get("pid")
            if _strict_int(pid, 1, 2**31 - 1) is None:
                return False
            if _strict_int(record_pid, 1, 2**31 - 1) is None:
                return False
            if record_pid != pid:
                return False
            member = record.get("member_id")
            instance = record.get("instance_id")
            if not _valid_identity(member, colon=True):
                return False
            if not _valid_identity(instance):
                return False
            return True
        except Exception:
            return False

    def _select_fair(
        self,
        eligible: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]],
    ) -> list[tuple[str, Mapping[str, Any], Mapping[str, Any]]]:
        if len(eligible) <= MAX_POLLS_PER_SNAPSHOT:
            selected = list(eligible)
        else:
            keys = [item[0] for item in eligible]
            start = 0
            if self._observe_cursor in keys:
                start = keys.index(self._observe_cursor) + 1
            selected = [
                eligible[(start + offset) % len(eligible)]
                for offset in range(MAX_POLLS_PER_SNAPSHOT)
            ]
        if selected:
            self._observe_cursor = selected[-1][0]
        return selected

    def _poll_process(
        self, process: Any
    ) -> tuple[str, Optional[int], Optional[str]]:
        observed_at = self._wall_now()
        try:
            poll = getattr(process, "poll", None)
            if not callable(poll):
                return "unknown", None, observed_at
            code = poll()
        except Exception:
            return "unknown", None, observed_at
        if code is None:
            return "alive", None, observed_at
        if isinstance(code, bool) or not isinstance(code, int):
            return "unknown", None, observed_at
        if code < EXIT_CODE_MIN or code > EXIT_CODE_MAX:
            return "unknown", None, observed_at
        return "exited", code, observed_at


__all__ = [
    "MANAGER_EVENT",
    "LAUNCH_EVENT",
    "SAMPLE_INTERVAL_SECONDS",
    "MANAGER_SEQ_MAX",
    "MAX_POLLS_PER_SNAPSHOT",
    "MAX_HANDLE_CHECKS",
    "MAX_DURATION_MS",
    "EXIT_CODE_MIN",
    "EXIT_CODE_MAX",
    "LoopEvidenceRecorder",
    "new_manager_run_id",
    "is_cancellation",
]
