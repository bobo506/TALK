"""TALK 执行会话的真实窗口通道：查询 → 规划 → 原生投递 → ACK 归并。

本模块把 288/289/290 的纯规则接到当前 DSH 原生入口：

- 用一个独立 overlay 关闭默认 ``headless-startup`` / ``headless-runner``，
  插入 ``dsh_execution_runner.mjs``；
- query 模式只 resume 并读取 live session（不调用模型）核验身份/修订/清单；
- 规划使用 ``bridges.execution_sessions.plan_execution_session`` 与
  ``bridges.dsh_context_metrics.adapt_context_snapshot``，不复制规则；
- deliver 模式在同一私有 spawn 目录写入冻结指令，由原生 runner 创建或
  resume 目标 session，在真实 ``user/message`` 事件被观察到后才写回 ACK；
- 桥接只在通道锁内做一次 query → plan → deliver → ACK 归并，并把最小状态
  持久化到受限 sidecar；模型失败/取消不按“未送达”处理。

安全边界：本模块不读取生产 HOME/配置/凭据/会话正文；只读取本次 task 的
基础合同（经服务端权限保护的只读接口）、公开安装包版本和本功能自己的文件。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bridges.dsh_context_metrics import adapt_context_snapshot
from bridges.execution_session_store import (
    ChannelBusy,
    ExecutionSessionStore,
    ExecutionSessionStoreError,
    StoreConflict,
    canonical_json,
    json_sha256,
    resolve_store_path,
    wait_timeout_seconds,
)
from bridges.execution_sessions import (
    confirm_window_delivery,
    initialize_window_count,
    plan_execution_session,
    record_threshold_observation,
)

REQUEST_SCHEMA = "talk-dsh-execution-request-1"
RESULT_SCHEMA = "talk-dsh-execution-result-1"
REQUEST_VERSION = 1
EXECUTION_CAPABILITY = "talk-execution-session-1"
PLUGIN_VERSION = "1.0.0"
NATIVE_SESSION_RE = re.compile(r"^session-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DEFAULT_METRICS_MAX_AGE_SECONDS = 21_600
DEFAULT_CHANNEL_WAIT_SECONDS = 30.0
# Explicit trusted fallback-clock budget: the metrics sample has its own
# freshness budget; this clock only rejects future/invalid unavailability
# evidence. It must not expire a legitimately old source_expired window.
FALLBACK_CLOCK_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
MAX_RESULT_BYTES = 8 * 1024 * 1024
_CONTROL_TEXT_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ExecutionSessionRunError(RuntimeError):
    """稳定的执行会话失败；message 只含通用原因/短字段名。"""

    def __init__(self, reason_code: str, detail: str | None = None) -> None:
        super().__init__(reason_code if not detail else f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


@dataclass
class ExecutionOutcome:
    reply: str
    completion_status: str
    state: dict
    last_error: str | None = None
    delivered: bool = False
    extras: dict = field(default_factory=dict)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_identifier(value: Any, field: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise ExecutionSessionRunError("invalid_identity", field)
    if _CONTROL_TEXT_RE.search(value):
        raise ExecutionSessionRunError("invalid_identity", field)
    return value


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _realpath(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _workspace_identity(root: Path) -> str:
    payload = {
        "schema": "talk-execution-workspace-1",
        "version": 1,
        "fields": {"path_normcase": str(_realpath(root)).casefold()},
    }
    return _canonical_hash(payload)


def _native_home() -> Path:
    raw = str(os.environ.get("DSH_HOME") or "").strip()
    if raw:
        return _realpath(Path(raw))
    return _realpath(Path.home() / ".dsh")


def _native_home_namespace(home: Path) -> str:
    return "dsh:" + _canonical_hash(
        {"schema": "talk-execution-native-home-1", "version": 1, "path_normcase": str(home).casefold()}
    )[:32]


def _native_package_root(command: Sequence[str], explicit: str | None) -> tuple[Path, str]:
    if explicit:
        root = _realpath(Path(explicit))
    else:
        root = None
        for item in command:
            candidate = Path(str(item))
            if candidate.name == "bin.js" and candidate.parent.name == "lib":
                manifest = candidate.parent.parent / "package.json"
                if manifest.is_file():
                    root = candidate.parent.parent
                    break
        if root is None:
            raise ExecutionSessionRunError("native_package_unresolved")
    manifest_path = root / "package.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExecutionSessionRunError("native_package_unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("name") != "@deepseek-ai/dsh":
        raise ExecutionSessionRunError("native_package_identity")
    version = str(manifest.get("version") or "")
    if not version:
        raise ExecutionSessionRunError("native_package_version_missing")
    if version != '0.1.5-rc.2':
        raise ExecutionSessionRunError('native_package_version_unsupported')
    return root, version


def _plugin_hashes() -> dict:
    base = Path(__file__).resolve().parent
    result = {}
    for name in ("dsh_execution_runner.mjs", "dsh_context_host.mjs", "dsh_context_capture.mjs"):
        path = base / name
        try:
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ExecutionSessionRunError("plugin_unreadable", name) from exc
    return result


def _config_fingerprint(
    *,
    binding: Mapping[str, Any],
    command: Sequence[str],
    package_version: str,
    home_namespace: str,
    plugin_hashes: Mapping[str, str],
) -> str:
    payload = {
        "schema": "talk-dsh-execution-config-1",
        "version": 1,
        "fields": {
            "capability": EXECUTION_CAPABILITY,
            "runtime": "dsh",
            "profile": "headless",
            "runner_id": binding.get("runner_id"),
            "provider_id": binding.get("provider_id"),
            "model_id": binding.get("model_id"),
            "binding_fingerprint": binding.get("binding_fingerprint"),
            "command_sha256": _canonical_hash([str(part) for part in command]),
            "package_version": package_version,
            "native_home_namespace": home_namespace,
            "plugins": dict(plugin_hashes),
        },
    }
    return _canonical_hash(payload)


def _request_digest(body: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in body.items() if key != "requestDigest"}
    return _canonical_hash(payload)


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with temp.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _read_json_file(path: Path, *, max_bytes: int = MAX_RESULT_BYTES) -> dict:
    try:
        size = path.stat().st_size
        if size <= 0 or size > max_bytes:
            raise ExecutionSessionRunError("result_size_invalid")
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExecutionSessionRunError("result_unreadable") from exc
    if not isinstance(value, dict):
        raise ExecutionSessionRunError("result_invalid")
    return value


def _overlay_yaml(*, runner_url: str, request_path: Path, output_path: Path, mode: str) -> str:
    def yaml_string(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return (
        "# TALK execution-session overlay (per spawn, private).\n"
        "- id: headless-startup\n"
        "  disabled: true\n"
        "- id: headless-runner\n"
        "  disabled: true\n"
        "# 执行会话不需要自动标题；标题插件会在 turn 之后再次调用模型并追加事件，\n"
        "# 破坏 ACK 快照与下一任务 query 修订的一致性。\n"
        "- id: session-title-llm\n"
        "  disabled: true\n"
        "- id: session-title\n"
        "  disabled: true\n"
        "- insert:\n"
        "    - id: talk-execution-runner\n"
        f"      name: {yaml_string(runner_url)}\n"
        "      config:\n"
        f"        requestPath: {yaml_string(str(request_path))}\n"
        f"        outputPath: {yaml_string(str(output_path))}\n"
        f"        mode: {yaml_string(mode)}\n"
        f"        pluginVersion: {yaml_string(PLUGIN_VERSION)}\n"
    )


def _entry_inventory_from_result(result: Mapping[str, Any]) -> str | None:
    value = result.get("inventory_hash")
    if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    return None


class _SpawnPaths:
    def __init__(self, store: ExecutionSessionStore, kind: str) -> None:
        base = store.path.parent / "spawns"
        base.mkdir(parents=True, exist_ok=True)
        self.directory = base / f"{kind}-{uuid.uuid4().hex}"
        self.directory.mkdir(mode=0o700)
        self.request = self.directory / "request.json"
        self.overlay = self.directory / "overlay.yml"
        self.output = self.directory / "result.json"

    def relative_evidence(self, store: ExecutionSessionStore) -> str:
        try:
            return str(self.directory.relative_to(store.path.parent))
        except ValueError:
            return self.directory.name


@dataclass
class _Prepared:
    scope: dict
    base_contract: dict
    task_block: dict
    new_messages: list[str]
    execution_id: str
    delivery_id: str
    request_identity: dict
    native_action: str
    native_session_id: str
    native_generation: int
    workspace_path: Path
    window: dict | None
    candidate_state: str | None
    query: dict | None
    previous_cut: int | None


async def run_execution_session_task(
    *,
    task: Mapping[str, Any],
    client: Any,
    member_id: str,
    workdir: Path,
    command: Sequence[str],
    timeout: int,
    launch_id: str | None,
    project_id: str | None,
    binding_snapshot: Mapping[str, Any] | None,
    hall_history: str = "",
    diagnostics: Any | None = None,
    store_override: str | None = None,
    native_package_root: str | None = None,
    runner: Any | None = None,
) -> ExecutionOutcome:
    """执行一个带 ``execution_session`` 的已 claim 任务。

    失败抛出 ``ExecutionSessionRunError``；调用方负责把任务标为 failed，
    不自动重跑模型。成功返回回复与最小窗口状态，由调用方发送结果并完成。
    """

    meta = task.get("execution_session")
    if not isinstance(meta, dict):
        raise ExecutionSessionRunError("execution_session_missing")
    task_id = int(task["id"])
    attempt = int(task.get("attempt") or 0)
    project = str(project_id or task.get("project_id") or meta.get("project_id") or "")
    if not project or project != meta.get("project_id"):
        raise ExecutionSessionRunError("project_mismatch")
    if str(task.get("target_member_id") or "") != meta.get("target_member_id"):
        raise ExecutionSessionRunError("target_mismatch")
    if member_id != meta.get('target_member_id'):
        raise ExecutionSessionRunError('caller_target_mismatch')
    if str(task.get("created_by") or "") != meta.get("requester_id"):
        raise ExecutionSessionRunError("requester_mismatch")
    if str(task.get("task_kind") or "general") != "general":
        raise ExecutionSessionRunError("task_kind_unsupported")
    if binding_snapshot is None:
        binding_snapshot = task.get("target_binding_snapshot")
    if not isinstance(binding_snapshot, Mapping):
        raise ExecutionSessionRunError("binding_missing")
    if binding_snapshot.get("state") != "bound" or binding_snapshot.get("runtime") != "dsh":
        raise ExecutionSessionRunError("binding_unusable")
    if binding_snapshot.get("binding_fingerprint") != meta.get("binding_fingerprint"):
        raise ExecutionSessionRunError("binding_changed")
    if binding_snapshot.get("provider_id") != meta.get("provider_id", binding_snapshot.get("provider_id")):
        # metadata does not duplicate provider/model; binding is the source.
        pass
    if not binding_snapshot.get("provider_id") or not binding_snapshot.get("model_id"):
        raise ExecutionSessionRunError("binding_incomplete")
    if not binding_snapshot.get("runner_id"):
        raise ExecutionSessionRunError("binding_runner_missing")

    workspace_root_raw = str(meta.get("workspace_root") or "")
    if not workspace_root_raw:
        raise ExecutionSessionRunError("workspace_missing")
    try:
        workspace_root = _realpath(Path(workspace_root_raw))
        actual_workdir = _realpath(Path(workdir))
    except (OSError, ValueError) as exc:
        raise ExecutionSessionRunError("workspace_unreadable") from exc
    if not workspace_root.is_dir() or workspace_root != actual_workdir:
        raise ExecutionSessionRunError("workspace_mismatch")
    if _workspace_identity(workspace_root) != meta.get("workspace_identity"):
        raise ExecutionSessionRunError("workspace_identity_mismatch")

    native_root, package_version = _native_package_root(command, native_package_root)
    home = _native_home()
    home_namespace = _native_home_namespace(home)
    binding = {
        "runner_id": str(binding_snapshot.get("runner_id")),
        "provider_id": str(binding_snapshot.get("provider_id")),
        "model_id": str(binding_snapshot.get("model_id")),
        "binding_fingerprint": str(binding_snapshot.get("binding_fingerprint")),
    }
    config_fingerprint = _config_fingerprint(
        binding=binding,
        command=command,
        package_version=package_version,
        home_namespace=home_namespace,
        plugin_hashes=_plugin_hashes(),
    )
    service_launch_id = str(launch_id or "unmanaged")
    base_contract = await _load_base_contract(client, task, meta)
    base = base_contract
    scope_base = {
        "project_id": project,
        "target_member_id": str(meta["target_member_id"]),
        "requester_id": str(meta["requester_id"]),
        "continuity_key": str(meta["continuity_key"]),
        "workspace_identity": str(meta["workspace_identity"]),
        "runtime": "dsh",
        "runner_id": binding["runner_id"],
        "native_home_namespace": home_namespace,
        "provider_id": binding["provider_id"],
        "model_id": binding["model_id"],
        "model_binding_fingerprint": binding["binding_fingerprint"],
        "config_permission_fingerprint": config_fingerprint,
        "service_launch_id": service_launch_id,
        "base_contract_version": base["version"],
        "base_contract_sha256": base["sha256"],
        "workspace_verified": True,
    }
    scope_for_new = {**scope_base, "session_generation": 1}
    scope_fingerprint = _canonical_hash(scope_for_new)

    store = ExecutionSessionStore(resolve_store_path(workspace_root, override=store_override))
    channel_key = "|".join(
        (project, str(meta["target_member_id"]), home_namespace, binding["runner_id"])
    )
    owner_token = f"chan-{os.getpid()}-{uuid.uuid4().hex}"
    channel_ttl = 180
    acquired = await _acquire_channel(
        store,
        channel_key=channel_key,
        owner_token=owner_token,
        ttl_seconds=channel_ttl,
    )
    if not acquired:
        raise ExecutionSessionRunError("channel_busy")
    lease_heartbeat = asyncio.create_task(
        _renew_channel_loop(
            store,
            channel_key=channel_key,
            owner_token=owner_token,
            ttl_seconds=channel_ttl,
        )
    )
    operation = asyncio.create_task(_run_locked(
            task=task,
            task_id=task_id,
            attempt=attempt,
            meta=meta,
            client=client,
            member_id=member_id,
            workdir=actual_workdir,
            command=command,
            timeout=timeout,
            base_contract=base_contract,
            binding=binding,
            scope_base=scope_base,
            scope_for_new=scope_for_new,
            scope_fingerprint=scope_fingerprint,
            home=home,
            home_namespace=home_namespace,
            native_root=native_root,
            package_version=package_version,
            config_fingerprint=config_fingerprint,
            store=store,
            hall_history=hall_history,
            diagnostics=diagnostics,
            native_package_root_hint=native_package_root,
            runner=runner,
            channel_key=channel_key,
            owner_token=owner_token,
        ))
    try:
        done, _ = await asyncio.wait((operation, lease_heartbeat), return_when=asyncio.FIRST_COMPLETED)
        if lease_heartbeat in done:
            raise ExecutionSessionRunError('channel_lease_lost')
        return operation.result()
    finally:
        if not operation.done():
            operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        lease_heartbeat.cancel()
        await asyncio.gather(lease_heartbeat, return_exceptions=True)
        try:
            store.release_channel(scope_key=channel_key, owner_token=owner_token)
        except Exception:
            pass


async def _renew_channel_loop(
    store: ExecutionSessionStore,
    *,
    channel_key: str,
    owner_token: str,
    ttl_seconds: int,
) -> None:
    """Keep a long delivery exclusive without relying on a huge stale lease."""

    interval = max(10.0, float(ttl_seconds) / 3.0)
    while True:
        await asyncio.sleep(interval)
        try:
            store.renew_channel(
                scope_key=channel_key,
                owner_token=owner_token,
                ttl_seconds=ttl_seconds,
            )
        except (StoreConflict, ExecutionSessionStoreError):
            raise ExecutionSessionRunError('channel_lease_lost')


async def _acquire_channel(
    store: ExecutionSessionStore,
    *,
    channel_key: str,
    owner_token: str,
    ttl_seconds: int,
) -> bool:
    deadline = time.monotonic() + wait_timeout_seconds(
        os.environ.get("TALK_EXECUTION_SESSION_CHANNEL_WAIT_SECONDS"),
        default=DEFAULT_CHANNEL_WAIT_SECONDS,
    )
    while True:
        try:
            store.acquire_channel(
                scope_key=channel_key,
                owner_token=owner_token,
                owner_pid=os.getpid(),
                ttl_seconds=ttl_seconds,
            )
            return True
        except ChannelBusy:
            if time.monotonic() >= deadline:
                return False
            import asyncio

            await asyncio.sleep(0.5)


async def _load_base_contract(client: Any, task: Mapping[str, Any], meta: Mapping[str, Any]) -> dict:
    base_task_id = meta.get("base_task_id") or task.get("id")
    try:
        base_task_id = int(base_task_id)
    except (TypeError, ValueError) as exc:
        raise ExecutionSessionRunError("base_reference_invalid") from exc
    getter = getattr(client, "get_execution_session_base", None)
    if getter is None:
        raise ExecutionSessionRunError("base_api_unavailable")
    try:
        payload = await getter(base_task_id)
    except Exception as exc:
        raise ExecutionSessionRunError("base_fetch_failed") from exc
    if not isinstance(payload, dict):
        raise ExecutionSessionRunError("base_invalid")
    expected = {
        "task_id": base_task_id,
        "continuity_key": meta.get("continuity_key"),
        "project_id": meta.get("project_id"),
        "requester_id": meta.get("requester_id"),
        "target_member_id": meta.get("target_member_id"),
        "base_contract_version": meta.get("base_contract_version"),
        "base_contract_sha256": meta.get("base_contract_sha256"),
        "binding_fingerprint": meta.get("binding_fingerprint"),
        "workspace_root": meta.get("workspace_root"),
        "workspace_identity": meta.get("workspace_identity"),
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ExecutionSessionRunError("base_identity_mismatch", key)
    text = payload.get("base_context")
    if not isinstance(text, str) or not text:
        raise ExecutionSessionRunError("base_text_missing")
    if _sha256_text(text) != str(meta.get("base_contract_sha256") or ""):
        raise ExecutionSessionRunError("base_text_hash_mismatch")
    return {
        "version": str(meta["base_contract_version"]),
        "sha256": str(meta["base_contract_sha256"]),
        "text": text,
    }


def _build_increment(
    task: Mapping[str, Any],
    meta: Mapping[str, Any],
    *,
    task_id: int,
    attempt: int,
    execution_id: str,
    hall_history: str,
) -> tuple[dict, list[str]]:
    content = str(task.get("content") or "").strip()
    if not content:
        raise ExecutionSessionRunError("task_content_missing")
    title = str(task.get("title") or "").strip()
    authorization = [
        f"target_member_id={meta.get('target_member_id')}",
        f"requester_id={meta.get('requester_id')}",
        f"task_kind={task.get('task_kind') or 'general'}",
        f"may_delegate={bool(task.get('may_delegate'))}",
        f"review_policy={task.get('review_policy') or 'none'}",
    ]
    control = "\n".join(
        (
            "[[本次任务控制上下文 v1]]",
            f"task_id={task_id}",
            f"attempt={attempt}",
            f"task_hall_group_id={task.get('hall_group_id') or ''}",
            f"project_id={meta.get('project_id')}",
            f"target_member_id={meta.get('target_member_id')}",
            f"requester_id={meta.get('requester_id')}",
            f"continuity_key={meta.get('continuity_key')}",
            f"current_authorization={'; '.join(authorization)}",
            "note=这是本次增量控制上下文；基础介绍与固定规则只在基础合同中保存，不在续轮重复。",
        )
    )
    body = f"{control}\n\n[[本次增量任务正文]]\n{content}"
    task_block = {
        "task_id": f"talk-{task_id}",
        "attempt": attempt,
        "execution_id": execution_id,
        "goal": title or f"TALK task #{task_id}",
        "authorization": authorization,
        "body": body,
    }
    for key in ("baseline_change", "authorization_change", "acceptance_difference"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            task_block[key] = value.strip()
    messages: list[str] = []
    if hall_history.strip():
        # 每个 TALK 任务有自己的 Hall；这是该任务本次的新消息，不是旧任务全量重放。
        messages.append(hall_history.strip())
    return task_block, messages


def _snapshot_summary(snapshot: Mapping[str, Any] | None) -> dict | None:
    if not isinstance(snapshot, Mapping):
        return None
    session = snapshot.get("session") if isinstance(snapshot.get("session"), Mapping) else {}
    metrics = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), Mapping) else {}
    result = {
        "session_revision": session.get("revision"),
        "observed_at": snapshot.get("observed_at"),
        "capture_status": (snapshot.get("capture") or {}).get("status")
        if isinstance(snapshot.get("capture"), Mapping)
        else None,
    }
    for field, key in (
        ("projected_tokens", "projected_tokens"),
        ("pressure_tokens", "pressure_tokens"),
        ("context_window", "context_window"),
    ):
        metric = metrics.get(key)
        if isinstance(metric, Mapping):
            result[field] = metric.get("value") if metric.get("state") == "known" else None
            source = metric.get("source") if isinstance(metric.get("source"), Mapping) else {}
            result[f"{field}_source_time"] = source.get("time")
            if field != "context_window" and metric.get("state") == "known" and 'used_source' not in result:
                result["used_source"] = key
                result["used_tokens"] = metric.get("value")
    return result


def _quantized_age(seconds: int) -> int:
    return max(1, min(int(seconds), 86_400))


async def _run_locked(
    *,
    task: Mapping[str, Any],
    task_id: int,
    attempt: int,
    meta: Mapping[str, Any],
    client: Any,
    member_id: str,
    workdir: Path,
    command: Sequence[str],
    timeout: int,
    base_contract: dict,
    binding: Mapping[str, Any],
    scope_base: dict,
    scope_for_new: dict,
    scope_fingerprint: str,
    home: Path,
    home_namespace: str,
    native_root: Path,
    package_version: str,
    config_fingerprint: str,
    store: ExecutionSessionStore,
    hall_history: str,
    diagnostics: Any | None,
    native_package_root_hint: str | None,
    runner: Any | None,
    channel_key: str,
    owner_token: str,
) -> ExecutionOutcome:
    del member_id, home, package_version  # facts already bound into scope/config
    store.assert_channel(scope_key=channel_key, owner_token=owner_token)
    if store.get_attempt(task_id, attempt) is not None:
        raise ExecutionSessionRunError('task_attempt_already_started')
    force_new = bool(meta.get("force_new"))
    window = None if force_new else store.get_active_window(scope_fingerprint)
    candidate_state: str | None = None
    query: dict | None = None
    previous_cut: int | None = None
    if window is not None:
        if window.get("provenance") != "talk_execution_runner":
            window = None
        elif not NATIVE_SESSION_RE.fullmatch(str(window.get("native_session_id") or "")):
            window = None

    if window is not None:
        previous_cut = _window_last_revision(window)
        query = await _query_candidate(
            store=store,
            task=task,
            task_id=task_id,
            attempt=attempt,
            meta=meta,
            binding=binding,
            scope=scope_base,
            window=window,
            workdir=workdir,
            command=command,
            timeout=timeout,
            home=home_namespace,
            native_root=native_root,
            config_fingerprint=config_fingerprint,
            native_package_root_hint=native_package_root_hint,
            runner=runner,
        )
        if query.get("availability") != "available":
            candidate_state = "closed" if query.get("reason_code") == "session_unavailable" else "tainted"
            query = None
        elif str(query.get("native_session_id")) != str(window.get("native_session_id")):
            candidate_state = "tainted"
            query = None
        elif not isinstance(query.get("inventory_hash"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", str(query.get("inventory_hash"))
        ):
            candidate_state = "tainted"
            query = None
        elif query.get("inventory_hash") != window.get("config_inventory_hash"):
            candidate_state = "tainted"
            query = None
        else:
            native_revision = int(query.get("session_revision") or 0)
            window_revision = previous_cut
            if window_revision is None or native_revision < window_revision:
                candidate_state = "tainted"
                query = None
            elif native_revision == window_revision:
                candidate_state = "ready"
            else:
                # A normal DSH dispose appends one benign `session/end-seed`
                # after our turn-end snapshot. Accept only that auditable delta;
                # any other appended event means another writer/unknown history.
                appended = query.get("appended_event_types")
                expected = native_revision - window_revision
                if (
                    isinstance(appended, list)
                    and len(appended) == expected
                    and expected <= 64
                    and all(item == "session/end-seed" for item in appended)
                ):
                    query = dict(query)
                    query["native_current_revision"] = native_revision
                    candidate_state = "ready"
                else:
                    candidate_state = "tainted"
                    query = None

    execution_id = "exec-" + _canonical_hash(
        {
            "schema": "talk-execution-request-id-1",
            "version": 1,
            "task_id": task_id,
            "attempt": attempt,
            "content_sha256": _sha256_text(str(task.get("content") or "")),
            "hall_sha256": _sha256_text(hall_history),
            "base_sha256": base_contract["sha256"],
        }
    )[:32]
    task_block, new_messages = _build_increment(
        task,
        meta,
        task_id=task_id,
        attempt=attempt,
        execution_id=execution_id,
        hall_history=hall_history,
    )
    target_generation = int(window["session_generation"]) if window is not None else 1
    scope_candidate = {**scope_base, "session_generation": target_generation}
    candidate = None
    if window is not None and query is not None:
        candidate = {
            "native_session_id": str(window["native_session_id"]),
            "scope": scope_candidate,
            "state": candidate_state or "ready",
            "execution_channel_exclusive": True,
            "active_writer": False,
            "first_turn_confirmed": isinstance(window.get("count_state"), Mapping),
            "session_revision": int(query["session_revision"]),
        }
    elif window is not None:
        candidate = {
            "native_session_id": str(window["native_session_id"]),
            "scope": scope_candidate,
            "state": candidate_state or "tainted",
            "execution_channel_exclusive": True,
            "active_writer": False,
            "first_turn_confirmed": isinstance(window.get("count_state"), Mapping),
            "session_revision": previous_cut if previous_cut is not None else 0,
        }

    context_sample, context_unavailability = _context_for_plan(
        window=window,
        query=query,
        scope_candidate=scope_candidate,
        max_age_seconds=_metrics_max_age(),
    )
    now = _now()
    plan = plan_execution_session(
        scope=scope_for_new if window is None else scope_candidate,
        base_contract=base_contract,
        task=task_block,
        selection="new" if force_new else "auto",
        candidate=candidate,
        context_sample=context_sample,
        new_messages=new_messages,
        execution_channel={
            "state": "ready",
            "active_writer": False,
            "execution_channel_exclusive": True,
        },
        context_unavailability=context_unavailability,
        window_count_state=window.get("count_state") if window is not None else None,
        fallback_clock={
            "now": _iso(now),
            "max_age_seconds": FALLBACK_CLOCK_MAX_AGE_SECONDS,
        },
    )
    action = str(plan.get("action") or "")
    if action == "wait":
        raise ExecutionSessionRunError(str(plan.get("reason_code") or "wait"))
    if action == "reject":
        raise ExecutionSessionRunError(str(plan.get("reason_code") or "plan_rejected"))
    if action not in ("new_session", "reuse_session"):
        raise ExecutionSessionRunError("plan_action_invalid")
    delivery = plan.get("delivery")
    if not isinstance(delivery, Mapping) or not isinstance(delivery.get("text"), str):
        raise ExecutionSessionRunError("plan_delivery_missing")
    directive_text = str(delivery["text"])
    directive_sha = str(delivery.get("sha256") or "")
    if directive_sha != _sha256_text(directive_text):
        raise ExecutionSessionRunError("plan_delivery_hash_mismatch")
    if _CONTROL_TEXT_RE.search(directive_text.replace("\n", "").replace("\r", "").replace("\t", "")):
        raise ExecutionSessionRunError("plan_delivery_control")
    first_turn = action == "new_session"
    if first_turn:
        native_session_id = f"session-{uuid.uuid4()}"
        native_generation = 1
        store_window = store.create_window(
            scope={**scope_for_new, "session_generation": native_generation},
            scope_fingerprint=_canonical_hash({**scope_for_new, "session_generation": native_generation}),
            native_session_id=None,
            session_generation=native_generation,
            base_task_id=int(meta.get("base_task_id") or task_id),
            config_inventory_hash=None,
            now=now,
        )
        # Scope fingerprint is stable regardless of session ID; window lookup uses it.
        window = store_window
    else:
        native_session_id = str(window["native_session_id"])
        native_generation = int(window["session_generation"])
    expected_revision = None
    if not first_turn and isinstance(query, Mapping):
        expected_revision = int(
            query.get("native_current_revision")
            if query.get("native_current_revision") is not None
            else query["session_revision"]
        )
    delivery_id = "delivery-" + _canonical_hash(
        {
            "schema": "talk-execution-delivery-1",
            "version": 1,
            "task_id": task_id,
            "attempt": attempt,
            "execution_id": execution_id,
            "body_sha256": directive_sha,
            "native_session_id": native_session_id,
            "session_generation": native_generation,
        }
    )[:40]
    identity = {
        "projectId": scope_base["project_id"],
        "targetMemberId": scope_base["target_member_id"],
        "requesterId": scope_base["requester_id"],
        "continuityKey": scope_base["continuity_key"],
        "workspaceIdentity": scope_base["workspace_identity"],
        "nativeHomeNamespace": home_namespace,
        "runnerId": binding["runner_id"],
        "serviceLaunchId": scope_base["service_launch_id"],
        "providerId": binding["provider_id"],
        "modelId": binding["model_id"],
        "modelBindingFingerprint": binding["binding_fingerprint"],
        "configPermissionFingerprint": config_fingerprint,
    }
    turn_timeout_ms = max(60_000, min(int(timeout) * 900, 6 * 60 * 60 * 1000))
    store.reserve_attempt(task_id=task_id, attempt=attempt, execution_id=execution_id,
        body_sha256=directive_sha, window_id=str(window['window_id']),
        native_session_id=native_session_id, channel_key=channel_key, owner_token=owner_token)
    try:
        result, spawn = await _spawn_and_run(
            store=store,
            mode="deliver",
            kind="deliver",
            identity=identity,
            native_action="create" if first_turn else "resume",
            native_session_id=native_session_id,
            native_generation=native_generation,
            previous_cut=(
                None
                if first_turn
                else (
                    int(window["count_state"]["last_session_revision"])
                    if isinstance(window.get("count_state"), Mapping)
                    and isinstance(window["count_state"].get("last_session_revision"), int)
                    else previous_cut
                )
            ),
            workspace_path=workdir,
            command=command,
            native_root=native_root,
            turn_timeout_ms=turn_timeout_ms,
            directive={
                "text": directive_text,
                "sha256": directive_sha,
                "deliveryId": delivery_id,
                "taskId": str(task_id),
                "attempt": attempt,
                "executionId": execution_id,
                "firstTurn": first_turn,
            },
            proc_timeout=max(120, int(turn_timeout_ms / 1000) + 180),
            runner=runner,
            diagnostics=diagnostics,
            expected_revision=expected_revision,
            expected_inventory_hash=query.get('inventory_hash') if not first_turn and query else None,
        )
    except ExecutionSessionRunError:
        # A reliable observed high/low reading may exist even when this spawn
        # never confirms delivery. Keep it so the next task cannot erase the
        # 60% fact; never fabricate a delivery.
        _persist_plan_observation(
            store=store,
            plan=plan,
            window=window,
            scope={**scope_base, "session_generation": native_generation},
        )
        if window is not None:
            store.taint_window(
                window_id=str(window["window_id"]),
                reason="delivery_unconfirmed",
                now=_now(),
            )
        raise
    except asyncio.CancelledError:
        _persist_plan_observation(
            store=store,
            plan=plan,
            window=window,
            scope={**scope_base, "session_generation": native_generation},
        )
        if window is not None:
            store.taint_window(
                window_id=str(window["window_id"]),
                reason="delivery_cancelled_unknown",
                now=_now(),
            )
        raise
    except Exception:
        _persist_plan_observation(
            store=store,
            plan=plan,
            window=window,
            scope={**scope_base, "session_generation": native_generation},
        )
        if window is not None:
            store.taint_window(
                window_id=str(window["window_id"]),
                reason="delivery_exception_unknown",
                now=_now(),
            )
        raise
    try:
        ack = _validate_delivery_result(
            result,
            request_digest=spawn["requestDigest"],
            delivery_id=delivery_id,
            task_id=task_id,
            attempt=attempt,
            execution_id=execution_id,
            body_sha256=directive_sha,
            native_session_id=native_session_id,
            session_generation=native_generation,
            first_turn=first_turn,
        )
    except ExecutionSessionRunError:
        if window is not None:
            store.taint_window(window_id=str(window["window_id"]), reason="ack_unverifiable", now=_now())
        raise

    snapshot = result.get("snapshot") if isinstance(result.get("snapshot"), Mapping) else None
    inventory_hash = _entry_inventory_from_result(result)
    receipt = {
        "delivery_id": ack["delivery_id"],
        "task_id": task_id,
        "attempt": attempt,
        "execution_id": execution_id,
        "body_sha256": ack["body_sha256"],
        "native_session_id": ack["native_session_id"],
        "session_generation": ack["session_generation"],
        "session_revision": ack["session_revision"],
        "outcome": ack["outcome"],
        "first_turn": first_turn,
    }
    counting = ack["outcome"] in ("delivered", "canceled_after_delivery", "timed_out_after_delivery")
    state = None
    scope_for_count = {**scope_base, "session_generation": native_generation}
    if not counting:
        store.record_delivery(window_id=str(window['window_id']), receipt=receipt,
            ack=ack, snapshot=snapshot, counted=False, now=_now())
        store.taint_window(window_id=str(window['window_id']), reason='delivery_unconfirmed', now=_now())
        raise ExecutionSessionRunError('delivery_not_confirmed')
    if first_turn:
        confirmation = initialize_window_count(scope=scope_for_count,
            native_session_id=native_session_id, first_delivery=receipt, previous_state=None)
        expected_status = {'initialized'}
    else:
        confirmation = confirm_window_delivery(state=window.get('count_state'),
            scope=scope_for_count, delivery=receipt)
        expected_status = {'incremented','duplicate'}
    state = confirmation.get('state')
    if confirmation.get('status') not in expected_status or not isinstance(state, Mapping):
        store.taint_window(window_id=str(window['window_id']),reason='delivery_count_conflict',now=_now())
        raise ExecutionSessionRunError('delivery_count_conflict')
    try:
        store.commit_confirmed_delivery(window_id=str(window['window_id']),
            expected_row_revision=int(window['row_revision']), native_session_id=native_session_id,
            count_state=state, snapshot=snapshot, receipt=receipt, ack=ack,
            inventory_hash=inventory_hash, first_turn=first_turn,
            channel_key=channel_key, owner_token=owner_token)
    except Exception as exc:
        store.taint_window(window_id=str(window['window_id']),reason='delivery_commit_unknown',now=_now())
        raise ExecutionSessionRunError('delivery_commit_unknown') from exc
    if ack.get('turn_outcome') in {'timeout','canceled','unknown'} or result.get('_process_failed'):
        store.taint_window(window_id=str(window['window_id']),reason='native_termination_unverified',now=_now())
    window = store.get_window(str(window["window_id"])) or window
    state_view = _state_view(
        plan=plan,
        window=window,
        state=state,
        ack=ack,
        snapshot=snapshot,
        task=task,
        base_contract=base_contract,
        execution_id=execution_id,
        reused=not first_turn,
    )
    if force_new:
        state_view["decision"] = "new_force_new"
        state_view["reason_code"] = "new_force_new"
    _cleanup_spawn(spawn, failed=False)
    reply = str(ack.get("assistant_text") or "").strip()
    if not reply:
        reply = (
            f"执行会话已送达（native {native_session_id}，第 "
            f"{int(state.get('confirmed_count', 0))} 次），但本轮没有可展示的助手文本。"
        )
    turn_outcome = str(ack.get("turn_outcome") or "unknown")
    if turn_outcome in {"error", "unknown"} or result.get("_process_failed"):
        return ExecutionOutcome(
            reply=reply,
            completion_status="failed",
            state=state_view,
            last_error="执行会话模型轮次失败；指令已送达并计数，未自动重跑。",
            delivered=True,
        )
    if turn_outcome == "timeout":
        return ExecutionOutcome(
            reply=reply,
            completion_status="failed",
            state=state_view,
            last_error="执行会话模型轮次超时；指令是否进入窗口以 ACK 为准。",
            delivered=True,
        )
    if turn_outcome == "canceled":
        return ExecutionOutcome(
            reply=reply,
            completion_status="canceled",
            state=state_view,
            last_error="执行会话模型轮次被取消；已确认送达仍计数。",
            delivered=True,
        )
    return ExecutionOutcome(
        reply=reply,
        completion_status="succeeded",
        state=state_view,
        delivered=True,
    )


def _persist_plan_observation(
    *,
    store: ExecutionSessionStore,
    plan: Mapping[str, Any],
    window: Mapping[str, Any] | None,
    scope: Mapping[str, Any],
) -> None:
    """在投递未确认时保留规划中已核的可靠观测（不增加计数）。"""

    if window is None:
        return
    state = window.get("count_state")
    if not isinstance(state, Mapping) or window.get("status") != "active":
        return
    window_count = plan.get("window_count")
    if not isinstance(window_count, Mapping):
        return
    intent = window_count.get("observation_intent")
    if not isinstance(intent, Mapping):
        return
    observation = intent.get("observation")
    if not isinstance(observation, Mapping):
        return
    result = record_threshold_observation(
        state=state,
        scope=scope,
        observation=observation,
        now=_iso(_now()),
    )
    if result.get("status") in ("recorded", "duplicate") and isinstance(
        result.get("state"), Mapping
    ):
        try:
            store.update_observation(
                window_id=str(window["window_id"]),
                expected_row_revision=int(window["row_revision"]),
                count_state=result["state"],
                observation=observation,
                now=_now(),
            )
        except (StoreConflict, ExecutionSessionStoreError):
            pass


def _metrics_max_age() -> int:
    raw = os.environ.get("TALK_EXECUTION_SESSION_METRICS_MAX_AGE_SECONDS")
    try:
        value = int(raw) if raw is not None else DEFAULT_METRICS_MAX_AGE_SECONDS
    except (TypeError, ValueError):
        value = DEFAULT_METRICS_MAX_AGE_SECONDS
    return _quantized_age(value)


def _window_last_revision(window: Mapping[str, Any]) -> int | None:
    state = window.get("count_state")
    if isinstance(state, Mapping):
        revision = state.get("last_session_revision")
        if isinstance(revision, int) and not isinstance(revision, bool) and revision >= 0:
            return revision
    return None


def _context_for_plan(
    *,
    window: Mapping[str, Any] | None,
    query: Mapping[str, Any] | None,
    scope_candidate: Mapping[str, Any],
    max_age_seconds: int,
) -> tuple[dict | None, dict | None]:
    if window is None or query is None:
        return None, None
    snapshot = query.get("snapshot")
    if not isinstance(snapshot, Mapping):
        return None, None
    expected_scope = {
        **{key: scope_candidate[key] for key in (
            "project_id",
            "target_member_id",
            "requester_id",
            "continuity_key",
            "workspace_identity",
            "runner_id",
            "native_home_namespace",
            "service_launch_id",
            "provider_id",
            "model_id",
            "model_binding_fingerprint",
            "config_permission_fingerprint",
        )},
        "native_session_id": str(query["native_session_id"]),
        "session_generation": int(query["session_generation"]),
        "session_revision": int(query["session_revision"]),
    }
    try:
        adapted = adapt_context_snapshot(
            snapshot,
            expected_scope=expected_scope,
            now=_iso(_now()),
            max_age_seconds=max_age_seconds,
            trusted_host={
                "verified": True,
                "source": "talk-execution-session-channel/1.0.0",
            },
        )
    except (ValueError, TypeError):
        return None, None
    if adapted.get("status") == "known" and isinstance(adapted.get("context_sample"), Mapping):
        return dict(adapted["context_sample"]), None
    unavailable = adapted.get("context_unavailability")
    if isinstance(unavailable, Mapping):
        return None, dict(unavailable)
    return None, None


async def _query_candidate(
    *,
    store: ExecutionSessionStore,
    task: Mapping[str, Any],
    task_id: int,
    attempt: int,
    meta: Mapping[str, Any],
    binding: Mapping[str, Any],
    scope: Mapping[str, Any],
    window: Mapping[str, Any],
    workdir: Path,
    command: Sequence[str],
    timeout: int,
    home: str,
    native_root: Path,
    config_fingerprint: str,
    native_package_root_hint: str | None,
    runner: Any | None,
) -> dict:
    identity = {
        "projectId": scope["project_id"],
        "targetMemberId": scope["target_member_id"],
        "requesterId": scope["requester_id"],
        "continuityKey": scope["continuity_key"],
        "workspaceIdentity": scope["workspace_identity"],
        "nativeHomeNamespace": home,
        "runnerId": binding["runner_id"],
        "serviceLaunchId": scope["service_launch_id"],
        "providerId": binding["provider_id"],
        "modelId": binding["model_id"],
        "modelBindingFingerprint": binding["binding_fingerprint"],
        "configPermissionFingerprint": config_fingerprint,
    }
    result, spawn = await _spawn_and_run(
        store=store,
        mode="query",
        kind="query",
        identity=identity,
        native_action="resume",
        native_session_id=str(window["native_session_id"]),
        native_generation=int(window["session_generation"]),
        previous_cut=_window_last_revision(window),
        workspace_path=workdir,
        command=command,
        native_root=native_root,
        turn_timeout_ms=max(60_000, min(int(timeout) * 900, 6 * 60 * 60 * 1000)),
        directive=None,
        proc_timeout=max(60, min(int(timeout), 300)),
        runner=runner,
        diagnostics=None,
    )
    if result.get("status") != "ok":
        _cleanup_spawn(spawn, failed=False)
        return {"availability": "unavailable", "reason_code": str(result.get("reason_code") or "query_failed")}
    query = result.get("query")
    if not isinstance(query, Mapping):
        _cleanup_spawn(spawn, failed=False)
        return {"availability": "unavailable", "reason_code": "query_missing"}
    native_id = query.get("native_session_id")
    revision = query.get("session_revision")
    if native_id != window.get("native_session_id"):
        _cleanup_spawn(spawn, failed=False)
        return {"availability": "unavailable", "reason_code": "query_session_mismatch"}
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        _cleanup_spawn(spawn, failed=False)
        return {"availability": "unavailable", "reason_code": "query_revision_invalid"}
    if int(query.get("session_generation") or 0) != int(window["session_generation"]):
        _cleanup_spawn(spawn, failed=False)
        return {"availability": "unavailable", "reason_code": "query_generation_mismatch"}
    if query.get("provider_id") != binding["provider_id"] or query.get("model_id") != binding["model_id"]:
        _cleanup_spawn(spawn, failed=False)
        return {"availability": "unavailable", "reason_code": "query_model_mismatch"}
    if query.get("cwd") != str(workdir):
        try:
            if _realpath(Path(str(query.get("cwd") or ""))) != _realpath(Path(workdir)):
                _cleanup_spawn(spawn, failed=False)
                return {"availability": "unavailable", "reason_code": "query_workspace_mismatch"}
        except (OSError, ValueError):
            _cleanup_spawn(spawn, failed=False)
            return {"availability": "unavailable", "reason_code": "query_workspace_mismatch"}
    inventory = query.get("inventory_hash") if "inventory_hash" in query else result.get("inventory_hash")
    _cleanup_spawn(spawn, failed=False)
    return {
        "availability": "available",
        "native_session_id": native_id,
        "session_generation": int(query.get("session_generation") or window["session_generation"]),
        "session_revision": revision,
        "session_seq": query.get("session_seq"),
        "appended_event_types": query.get("appended_event_types")
        if isinstance(query.get("appended_event_types"), list)
        else [],
        "inventory_hash": inventory,
        "provider_id": query.get("provider_id"),
        "model_id": query.get("model_id"),
        "snapshot": result.get("snapshot"),
    }


async def _spawn_and_run(
    *,
    store: ExecutionSessionStore,
    mode: str,
    kind: str,
    identity: Mapping[str, Any],
    native_action: str,
    native_session_id: str,
    native_generation: int,
    previous_cut: int | None,
    workspace_path: Path,
    command: Sequence[str],
    native_root: Path,
    turn_timeout_ms: int,
    directive: Mapping[str, Any] | None,
    proc_timeout: int,
    runner: Any | None,
    diagnostics: Any | None,
    expected_revision: int | None = None,
    expected_inventory_hash: str | None = None,
) -> tuple[dict, dict]:
    paths = _SpawnPaths(store, kind)
    request = {
        "schema": REQUEST_SCHEMA,
        "version": REQUEST_VERSION,
        "mode": mode,
        "identity": dict(identity),
        "workspacePath": str(workspace_path),
        "nativePackageRoot": str(native_root),
        "native": {
            "action": native_action,
            "sessionId": native_session_id,
            "sessionGeneration": native_generation,
            "previousCut": previous_cut,
            "expectedRevision": expected_revision,
            "expectedInventoryHash": expected_inventory_hash,
        },
        "turnTimeoutMs": int(turn_timeout_ms),
        "paths": {
            "allowedRoot": str(paths.directory),
            "request": str(paths.request),
            "output": str(paths.output),
        },
        "directive": dict(directive) if directive is not None else None,
    }
    digest = _request_digest(request)
    request["requestDigest"] = digest
    _write_json_atomic(paths.request, request)
    runner_url = (Path(__file__).resolve().parent / "dsh_execution_runner.mjs").as_uri()
    paths.overlay.write_text(
        _overlay_yaml(
            runner_url=runner_url,
            request_path=paths.request,
            output_path=paths.output,
            mode=mode,
        ),
        encoding="utf-8",
    )
    invocation = [*[str(part) for part in command], "--patch", str(paths.overlay)]
    if runner is None:
        from bridges.cli_bridge import run_cli_command

        async def default_runner(*args: Any, **kwargs: Any) -> Any:
            return await run_cli_command(*args, **kwargs)

        call = default_runner(
            invocation,
            "",
            cwd=workspace_path,
            timeout=proc_timeout,
            prompt_transport="stdin",
        )
    else:
        call = runner(
            invocation,
            "",
            cwd=workspace_path,
            timeout=proc_timeout,
            prompt_transport="stdin",
        )
    import asyncio

    try:
        run_result = await call
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise ExecutionSessionRunError("runner_failed") from exc
    if diagnostics is not None:
        try:
            diagnostics.record_event(
                "execution_session_spawn",
                stage=f"execution_session_{mode}",
                extra={
                    "mode": mode,
                    "spawn": paths.relative_evidence(store),
                    "returncode": int(getattr(run_result, "returncode", -1)),
                    "timed_out": bool(getattr(run_result, "timed_out", False)),
                    "plugin_version": PLUGIN_VERSION,
                },
            )
        except Exception:
            pass
    try:
        result = _read_json_file(paths.output)
    except ExecutionSessionRunError:
        raise ExecutionSessionRunError("runner_output_missing")
    if result.get("schema") != RESULT_SCHEMA or type(result.get('version')) is not int or result.get("version") != 1:
        raise ExecutionSessionRunError("result_schema_invalid")
    if result.get("mode") != mode:
        raise ExecutionSessionRunError("result_mode_mismatch")
    if result.get("status") != "error" and result.get("request_digest") != digest:
        raise ExecutionSessionRunError("result_digest_mismatch")
    if result.get("status") == "error":
        raise ExecutionSessionRunError(str(result.get("reason_code") or "runner_error"))
    if int(getattr(run_result, 'returncode', -1)) != 0 or bool(getattr(run_result, 'timed_out', False)):
        result['_process_failed'] = True
    return result, {
        "requestDigest": digest,
        "spawn": paths.relative_evidence(store),
        "spawn_dir": str(paths.directory),
        "cleanup_root": str(store.path.parent / 'spawns'),
    }


def _cleanup_spawn(spawn: Mapping[str, Any], *, failed: bool) -> None:
    """成功传输文件不长期保留正文；失败/审计模式按证据要求保留。"""

    if failed:
        return
    if str(os.environ.get("TALK_EXECUTION_SESSION_RETAIN_SPAWNS", "")).strip() == "1":
        return
    directory = spawn.get("spawn_dir")
    if not isinstance(directory, str) or not directory:
        return
    import shutil

    try:
        target = Path(directory)
        allowed = Path(str(spawn.get('cleanup_root') or ''))
        if not target.is_absolute() or not allowed.is_absolute():
            return
        if target.resolve().parent != allowed.resolve() or not re.fullmatch(r'(deliver|query)-[0-9a-f]{32}',target.name):
            return
        shutil.rmtree(target)
    except (OSError, ValueError):
        pass


def _validate_delivery_result(
    result: Mapping[str, Any],
    *,
    request_digest: str,
    delivery_id: str,
    task_id: int,
    attempt: int,
    execution_id: str,
    body_sha256: str,
    native_session_id: str,
    session_generation: int,
    first_turn: bool,
) -> dict:
    if result.get("status") != "ok":
        raise ExecutionSessionRunError("result_not_ok")
    if result.get('request_digest') != request_digest:
        raise ExecutionSessionRunError('result_digest_mismatch')
    delivery = result.get("delivery")
    if not isinstance(delivery, Mapping):
        raise ExecutionSessionRunError("delivery_missing")
    expected = {
        "delivery_id": delivery_id,
        "task_id": str(task_id),
        "attempt": attempt,
        "execution_id": execution_id,
        "body_sha256": body_sha256,
        "native_session_id": native_session_id,
        "session_generation": session_generation,
        "first_turn": first_turn,
    }
    for key, value in expected.items():
        if type(delivery.get(key)) is not type(value) or delivery.get(key) != value:
            raise ExecutionSessionRunError("delivery_fact_mismatch", key)
    revision = delivery.get("session_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ExecutionSessionRunError("delivery_revision_invalid")
    outcome = delivery.get("outcome")
    allowed = {
        "delivered",
        "canceled_after_delivery",
        "timed_out_after_delivery",
        "failed_before_delivery",
        "timed_out_before_delivery",
    }
    if outcome not in allowed:
        raise ExecutionSessionRunError("delivery_outcome_invalid")
    committed = delivery.get("directive_committed")
    directive_seq = delivery.get('directive_seq')
    if committed is True and (type(directive_seq) is not int or directive_seq < 0 or directive_seq > revision):
        raise ExecutionSessionRunError('delivery_seq_invalid')
    if delivery.get('turn_outcome') not in {'completed','error','timeout','canceled','unknown'}:
        raise ExecutionSessionRunError('turn_outcome_invalid')
    if committed is not True and outcome in (
        "delivered",
        "canceled_after_delivery",
        "timed_out_after_delivery",
    ):
        raise ExecutionSessionRunError("delivery_not_proven")
    return {
        "delivery_id": delivery_id,
        "task_id": task_id,
        "attempt": attempt,
        "execution_id": execution_id,
        "body_sha256": body_sha256,
        "native_session_id": native_session_id,
        "session_generation": session_generation,
        "session_revision": revision,
        "outcome": outcome,
        "first_turn": first_turn,
        "turn_outcome": delivery.get("turn_outcome"),
        "assistant_text": delivery.get("assistant_text"),
    }


def _state_view(
    *,
    plan: Mapping[str, Any],
    window: Mapping[str, Any],
    state: Mapping[str, Any],
    ack: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None,
    task: Mapping[str, Any],
    base_contract: Mapping[str, Any],
    execution_id: str,
    reused: bool,
) -> dict:
    window_count = plan.get("window_count") if isinstance(plan.get("window_count"), Mapping) else {}
    metrics = plan.get("metrics") if isinstance(plan.get("metrics"), Mapping) else {}
    context_status = "known" if metrics.get("status") == "known" else "unavailable"
    context_reason = str(metrics.get("reason_code") or window_count.get("reason_code") or "unknown")
    if metrics.get("status") == "known" and isinstance(metrics.get("used_tokens"), int):
        context_reason = "known"
    archive_hashes: dict = {}
    archive = plan.get("archive")
    if isinstance(archive, Mapping):
        archive_hashes = {
            "archive_schema": archive.get("schema"),
            "task_increment_sha256": json_sha256(archive.get("task")),
            "hall_messages_sha256": json_sha256(archive.get("new_messages")),
        }
    return {
        "schema": "talk-execution-session-state-1",
        "version": 1,
        "status": "completed",
        "decision": str(plan.get("reason_code") or plan.get("action") or "unknown"),
        "reason_code": str(plan.get("reason_code") or ""),
        "native_session_id": str(ack.get("native_session_id")),
        "session_generation": int(ack.get("session_generation")),
        "reused": bool(reused),
        "first_turn": not bool(reused),
        "context_status": context_status,
        "context_reason": context_reason,
        "confirmed_count": int(state.get("confirmed_count") or 0),
        "proposed_ordinal": window_count.get("proposed_ordinal"),
        "state_revision": int(state.get("state_revision") or 0),
        "delivery_id": str(ack.get("delivery_id")),
        "delivery_outcome": str(ack.get("outcome")),
        "turn_outcome": str(ack.get("turn_outcome") or "unknown"),
        "directive_sha256": str(ack.get("body_sha256")),
        "directive_bytes": int(plan.get("delivery", {}).get("bytes") or 0)
        if isinstance(plan.get("delivery"), Mapping)
        else 0,
        "window_status": str(window.get("status") or "active"),
        "last_snapshot": _snapshot_summary(snapshot),
        "limitations": (
            "execution_session_state 只描述本任务窗口决策与送达事实；"
            "不包含正文、凭据或完整配置。指标缺失时 context_status=unavailable。"
        ),
        "task_id": int(task["id"]),
        "attempt": int(task.get("attempt") or 0),
        "execution_id": execution_id,
        "base_contract_version": str(base_contract["version"]),
        "base_contract_sha256": str(base_contract["sha256"]),
        **archive_hashes,
    }
