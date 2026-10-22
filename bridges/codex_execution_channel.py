"""Codex 原生会话接线：共享规划/计数/锁，独立核验 Codex 原生送达与指标。

不把 Codex 伪装成 DSH 快照。指标使用本会话最近请求的
last_token_usage.total_tokens / model_context_window，保留原生来源时间；
累计计费用量不参与换窗。仅单纯缺数且窗口历史完整时使用共享十次备用。
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bridges.codex_execution_native import (
    CodexNative, CodexNativeError, digest, now_iso, resolve_launch, text_digest,
)
from bridges.dsh_context_metrics import build_metrics_unavailability
from bridges.dsh_execution_channel import (
    ExecutionOutcome, ExecutionSessionRunError, _acquire_channel, _build_increment,
    _load_base_contract, _renew_channel_loop, _state_view, _workspace_identity,
)
from bridges.execution_session_store import ExecutionSessionStore, json_sha256, resolve_store_path
from bridges.execution_sessions import (
    confirm_window_delivery, initialize_window_count, plan_execution_session,
)


def _metric_inputs(snapshot: dict, scope: dict) -> tuple[dict | None, dict | None]:
    if snapshot.get("metrics_invalid"):
        return None, None
    identity = {key: scope[key] for key in (
        "project_id", "target_member_id", "requester_id", "continuity_key", "workspace_identity",
        "runner_id", "native_home_namespace", "service_launch_id", "provider_id", "model_id",
        "model_binding_fingerprint", "config_permission_fingerprint")}
    expected = {**identity, "native_session_id": snapshot["native_session_id"],
                "session_generation": scope["session_generation"],
                "session_revision": snapshot["session_revision"]}
    if snapshot.get("metrics_missing") is True:
        # Reuse the public kernel's legacy-named unavailability contract, with a
        # truthful Codex producer label. This does not manufacture a DSH sample.
        unavailable = build_metrics_unavailability(reason_code="metrics_not_provided",
            expected_scope=expected, observed_at=snapshot["observed_at"],
            trusted_host={"verified": True, "source": "talk-codex-execution-channel/1.0.0"},
            producer_supported=True)
        return None, unavailable
    sample = {**{k: scope[k] for k in ("provider_id", "model_id", "model_binding_fingerprint")},
        "native_session_id": snapshot["native_session_id"], "session_generation": scope["session_generation"],
        "session_revision": snapshot["session_revision"], "pressure_tokens": snapshot["used_tokens"],
        "context_window": snapshot["context_window"], "sampled_at": snapshot["source_time"],
        "now": now_iso(), "max_age_seconds": 21600}
    source_time = datetime.fromisoformat(snapshot["source_time"].replace("Z", "+00:00"))
    if (datetime.now(timezone.utc) - source_time).total_seconds() > 21600:
        # Identity and disk cut are still exact, only the native metric is old.
        unavailable = build_metrics_unavailability(reason_code="metrics_not_provided",
            expected_scope=expected, observed_at=snapshot["observed_at"],
            trusted_host={"verified": True, "source": "talk-codex-execution-channel/1.0.0"}, producer_supported=True)
        unavailable.update(reason_code="used_sample_expired", category="source_expired")
        unavailable["evidence"]["trust"] = "adapter_verified_snapshot"
        unavailable["evidence"]["checks"] = {name: True for name in (
            "scope_match", "workspace_verified", "session_id_match", "generation_match", "revision_match",
            "session_live", "projection_exact", "model_match", "binding_match", "config_source_known")}
        return sample, unavailable
    return sample, None


def _public_snapshot(snapshot: dict) -> dict:
    return {"session_revision": snapshot["session_revision"], "observed_at": snapshot["observed_at"],
        "capture_status": "unavailable" if snapshot.get("metrics_invalid") else "partial" if snapshot["metrics_missing"] else "available",
        "used_source": "pressure_tokens", "used_tokens": snapshot["used_tokens"],
        "pressure_tokens": snapshot["used_tokens"], "context_window": snapshot["context_window"],
        "pressure_tokens_source_time": snapshot["source_time"],
        "context_window_source_time": snapshot["source_time"]}


async def run_execution_session_task(*, task: Mapping[str, Any], client: Any, member_id: str,
        workdir: Path, command: Sequence[str], timeout: int, launch_id: str | None,
        project_id: str | None, binding_snapshot: Mapping[str, Any] | None,
        hall_history: str = "", diagnostics: Any = None, store_override: str | None = None,
        native_package_root: str | None = None, runner: Any = None) -> ExecutionOutcome:
    """只处理已领取的 Codex general 顶层任务；不自动重试模型或恢复旧归属。"""
    del diagnostics, native_package_root
    meta = task.get("execution_session")
    binding = binding_snapshot or task.get("target_binding_snapshot")
    if not isinstance(meta, Mapping) or not isinstance(binding, Mapping):
        raise ExecutionSessionRunError("execution_session_missing")
    project = str(project_id or task.get("project_id") or "")
    if (not project or project != meta.get("project_id") or task.get("project_id") != project
            or task.get("target_member_id") != member_id or meta.get("target_member_id") != member_id
            or task.get("created_by") != meta.get("requester_id")):
        raise ExecutionSessionRunError("codex_task_identity_mismatch")
    if (task.get("task_kind", "general") != "general" or task.get("parent_task_id") is not None
            or binding.get("state") != "bound" or binding.get("runtime") != "codex"
            or meta.get("runtime") != "codex" or binding.get("binding_fingerprint") != meta.get("binding_fingerprint")
            or not all(binding.get(k) for k in ("runner_id", "provider_id", "model_id"))):
        raise ExecutionSessionRunError("codex_binding_unusable")
    workdir = workdir.resolve()
    if (not workdir.is_dir() or workdir != Path(str(meta.get("workspace_root") or "")).resolve()
            or _workspace_identity(workdir) != meta.get("workspace_identity")):
        raise ExecutionSessionRunError("workspace_mismatch")
    base = await _load_base_contract(client, task, meta)
    try:
        native = runner if runner is not None else CodexNative(resolve_launch(command, workdir, binding), workdir)
        scope = {"project_id": project, "target_member_id": member_id, "requester_id": meta["requester_id"],
            "continuity_key": meta["continuity_key"], "workspace_identity": meta["workspace_identity"],
            "runtime": "codex", "runner_id": binding["runner_id"],
            "native_home_namespace": "codex:" + digest(str(native.home.resolve()).casefold())[:32],
            "provider_id": binding["provider_id"], "model_id": binding["model_id"],
            "model_binding_fingerprint": binding["binding_fingerprint"],
            "config_permission_fingerprint": native.fingerprint, "service_launch_id": str(launch_id or "unmanaged"),
            "base_contract_version": base["version"], "base_contract_sha256": base["sha256"],
            "session_generation": 1, "workspace_verified": True}
        store = ExecutionSessionStore(resolve_store_path(workdir, override=store_override))
        key = "|".join((project, member_id, scope["native_home_namespace"], binding["runner_id"]))
        owner = f"chan-{os.getpid()}-{uuid.uuid4().hex}"
        if not await _acquire_channel(store, channel_key=key, owner_token=owner, ttl_seconds=180):
            raise ExecutionSessionRunError("channel_busy")
        heartbeat = asyncio.create_task(_renew_channel_loop(store, channel_key=key, owner_token=owner, ttl_seconds=180))
        operation = asyncio.create_task(_run_locked(task, meta, base, scope, store, native, workdir,
                                                   timeout, hall_history, key, owner))
        try:
            done, _ = await asyncio.wait((heartbeat, operation), return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done:
                raise ExecutionSessionRunError("channel_lease_lost")
            return operation.result()
        finally:
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            # Never release the writer lease while our native process can still write.
            await asyncio.shield(native.close())
            store.release_channel(scope_key=key, owner_token=owner)
    except CodexNativeError as exc:
        raise ExecutionSessionRunError(exc.reason_code) from exc


async def _run_locked(task, meta, base, scope, store, native, workdir, timeout, history, key, owner):
    task_id, attempt = int(task["id"]), int(task.get("attempt") or 0)
    if store.get_attempt(task_id, attempt) is not None:
        raise ExecutionSessionRunError("task_attempt_already_started")
    await native.open()
    scope_hash = digest(scope)
    window = None if meta.get("force_new") else store.get_active_window(scope_hash)
    snapshot, users = None, []
    candidate = None
    if window is not None:
        state = "tainted"
        try:
            snapshot, users = await native.query(str(window["native_session_id"]))
            old = window.get("last_snapshot")
            if (isinstance(old, Mapping) and snapshot["native_sha256"] == old.get("native_sha256")
                    and snapshot["session_revision"] == old.get("session_revision")
                    and window.get("config_inventory_hash") == native.fingerprint):
                state = "ready"
            else:
                snapshot = None
        except (CodexNativeError, OSError):
            snapshot = None
        candidate = {"native_session_id": window["native_session_id"], "scope": scope, "state": state,
            "execution_channel_exclusive": True, "active_writer": False,
            "first_turn_confirmed": isinstance(window.get("count_state"), Mapping),
            "session_revision": snapshot["session_revision"] if snapshot else 0}
    execution_id = "exec-" + digest({"task_id": task_id, "attempt": attempt,
        "content": text_digest(str(task.get("content") or "")), "history": text_digest(history), "base": base["sha256"]})[:32]
    increment, messages = _build_increment(task, meta, task_id=task_id, attempt=attempt,
                                         execution_id=execution_id, hall_history=history)
    sample, unavailable = _metric_inputs(snapshot, scope) if snapshot is not None else (None, None)
    plan = plan_execution_session(scope=scope, base_contract=base, task=increment,
        selection="new" if meta.get("force_new") else "auto", candidate=candidate,
        context_sample=sample, context_unavailability=unavailable, new_messages=messages,
        execution_channel={"state": "ready", "active_writer": False, "execution_channel_exclusive": True},
        window_count_state=window.get("count_state") if window else None,
        fallback_clock={"now": now_iso(), "max_age_seconds": 30 * 24 * 60 * 60})
    if plan.get("action") not in {"new_session", "reuse_session"}:
        raise ExecutionSessionRunError(str(plan.get("reason_code") or "plan_rejected"))
    first = plan["action"] == "new_session"
    directive = plan["delivery"]["text"]
    body_hash = text_digest(directive)
    if body_hash != plan["delivery"].get("sha256"):
        raise ExecutionSessionRunError("plan_delivery_hash_mismatch")
    if first:
        # Native allocates the ID without a model call. Never invent a Codex ID.
        sid = await native.create()
        before, users = native.snapshot(sid)
        window = store.create_window(scope=scope, scope_fingerprint=scope_hash,
            native_session_id=None, session_generation=1,
            base_task_id=int(meta.get("base_task_id") or task_id), now=datetime.now(timezone.utc))
    else:
        sid = window["native_session_id"]
        before = snapshot
    delivery_id = "delivery-" + digest({"task": task_id, "attempt": attempt, "execution": execution_id,
                                         "body": body_hash, "session": sid})[:40]
    store.reserve_attempt(task_id=task_id, attempt=attempt, execution_id=execution_id,
        body_sha256=body_hash, window_id=window["window_id"], native_session_id=sid,
        channel_key=key, owner_token=owner)
    result = {"status": "failed", "reply": "", "rerouted": False}
    interrupted = None
    try:
        # Re-check the exact on-disk cut immediately before sending the directive.
        current, _ = native.snapshot(sid)
        if current["native_sha256"] != before["native_sha256"]:
            raise ExecutionSessionRunError("codex_native_history_changed")
        result = await native.deliver(sid, directive, max(1, int(timeout)), expected_sha256=before["native_sha256"])
    except (asyncio.CancelledError, asyncio.TimeoutError, CodexNativeError, ExecutionSessionRunError) as exc:
        interrupted = exc
    finally:
        try:
            await asyncio.shield(native.close())
        except Exception:
            store.taint_window(window_id=window["window_id"], reason="native_termination_unverified")
            raise ExecutionSessionRunError("native_termination_unverified")
    try:
        after, user_rows = native.snapshot(sid)
        delivered = [(index, sha) for index, sha in user_rows if index >= before["session_revision"]]
        matches = [(i, sha) for i, sha in delivered if sha == body_hash]
        if len(matches) != 1:
            raise ExecutionSessionRunError("delivery_not_confirmed")
    except Exception as exc:
        store.taint_window(window_id=window["window_id"], reason="delivery_unconfirmed")
        if isinstance(interrupted, asyncio.CancelledError):
            raise interrupted
        if isinstance(exc, ExecutionSessionRunError):
            raise
        raise ExecutionSessionRunError("codex_delivery_proof_invalid") from exc
    outcome = "canceled_after_delivery" if isinstance(interrupted, asyncio.CancelledError) else (
        "timed_out_after_delivery" if isinstance(interrupted, asyncio.TimeoutError) else "delivered")
    turn_outcome = "completed" if result.get("status") == "completed" else (
        "canceled" if outcome == "canceled_after_delivery" else "timeout" if outcome == "timed_out_after_delivery" else "error")
    receipt = {"delivery_id": delivery_id, "task_id": task_id, "attempt": attempt,
        "execution_id": execution_id, "body_sha256": body_hash, "native_session_id": sid,
        "session_generation": 1, "session_revision": after["session_revision"],
        "outcome": outcome, "first_turn": first}
    ack = {**receipt, "turn_outcome": turn_outcome, "assistant_text": str(result.get("reply") or "")}
    confirmation = (initialize_window_count(scope=scope, native_session_id=sid, first_delivery=receipt)
                    if first else confirm_window_delivery(state=window["count_state"], scope=scope, delivery=receipt))
    state = confirmation.get("state")
    if confirmation.get("status") not in {"initialized", "incremented"} or not isinstance(state, Mapping):
        store.taint_window(window_id=window["window_id"], reason="delivery_count_conflict")
        raise ExecutionSessionRunError("delivery_count_conflict")
    try:
        store.commit_confirmed_delivery(window_id=window["window_id"], expected_row_revision=window["row_revision"],
            native_session_id=sid, count_state=state, snapshot=after, receipt=receipt, ack=ack,
            inventory_hash=native.fingerprint, first_turn=first, channel_key=key, owner_token=owner)
    except Exception as exc:
        store.taint_window(window_id=window["window_id"], reason="delivery_commit_unknown")
        raise ExecutionSessionRunError("delivery_commit_unknown") from exc
    if len(delivered) != 1 or interrupted is not None or result.get("rerouted") or after.get("metrics_invalid"):
        store.taint_window(window_id=window["window_id"], reason="native_history_or_outcome_unverified")
    window = store.get_window(window["window_id"])
    view = _state_view(plan=plan, window=window, state=state, ack=ack, snapshot=None,
                       task=task, base_contract=base, execution_id=execution_id, reused=not first)
    view["last_snapshot"] = _public_snapshot(after)
    if meta.get("force_new"):
        view["decision"] = view["reason_code"] = "new_force_new"
    if isinstance(interrupted, asyncio.CancelledError):
        raise interrupted
    succeeded = turn_outcome == "completed" and len(delivered) == 1 and not result.get("rerouted")
    return ExecutionOutcome(reply=str(result.get("reply") or "本轮指令已在原生会话确认送达，模型未返回最终文本。"),
        completion_status="succeeded" if succeeded else "failed", state=view, delivered=True,
        last_error=None if succeeded else "Codex原生轮次失败或历史存在歧义；已确认送达仍计数，未自动重跑。")
