"""显式绑定的本机宿主：随API恢复；遗留归属只在human关闭请求内逐项核实。"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import uuid
from datetime import datetime

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
POINTER = ROOT / ".talk/runtime.local.json"
logger = logging.getLogger(__name__)

RUNTIME_MANAGER_PROTOCOLS = {"talk-runtime-1": "talk-manager-1"}


def bind_local_runtime(config_file, config):
    """显式运行统一入口时记住本机绑定；仅存清单路径，不复制任何凭据。"""
    import tomllib
    with (ROOT/"config.toml").open("rb") as stream:
        database = tomllib.load(stream)["storage"]["db_path"]
    database = Path(database)
    if not database.is_absolute():
        database = ROOT/database
    pointer = Path(config["project_root"]).resolve() / ".talk" / "runtime.local.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps({"schema":"talk-local-runtime-1", "database_file":str(database.resolve()),
                                  "config_file":str(Path(config_file).resolve())}), encoding="utf-8")


def configured_runtime(engine, project_id=None):
    if project_id is not None:
        # Project-specific lookups never fall back to the repository binding.
        try:
            from sqlalchemy import text
            with engine.connect() as connection:
                root_value = connection.execute(
                    text("SELECT project_root_path FROM projects WHERE project_id=:p"),
                    {"p": project_id},
                ).scalar_one_or_none()
            if not isinstance(root_value, str) or not Path(root_value).is_absolute():
                return None
            root = Path(root_value).resolve()
            pointer = json.loads((root / ".talk" / "runtime.local.json").read_text(encoding="utf-8"))
            database = engine.url.database
            if (not isinstance(pointer, dict) or pointer.get("schema") != "talk-local-runtime-1"
                    or not database or not isinstance(pointer.get("database_file"), str)
                    or not Path(pointer["database_file"]).is_absolute()
                    or Path(database).resolve() != Path(pointer["database_file"]).resolve()
                    or not isinstance(pointer.get("config_file"), str)):
                return None
            path = Path(pointer["config_file"])
            if not path.is_absolute() or not path.is_file():
                return None
            from scripts.talk_runtime import load_config
            config = load_config(path)
            if config["project_id"] != project_id or Path(config["project_root"]).resolve() != root:
                return None
            return path, config
        except Exception:
            return None
    # 本机绑定同时精确限定数据库；隔离TestClient/临时数据库不会触及生产宿主。
    if not POINTER.is_file():
        return None
    pointer = json.loads(POINTER.read_text(encoding="utf-8"))
    database = engine.url.database
    if (pointer.get("schema") != "talk-local-runtime-1" or not database
            or Path(database).resolve() != Path(pointer["database_file"]).resolve()):
        return None
    from scripts.talk_runtime import load_config
    path = Path(pointer["config_file"])
    if not path.is_absolute():
        raise ValueError("local_runtime_config_path_invalid")
    config = load_config(path)
    if Path(config["project_root"]).resolve() != ROOT:
        raise ValueError("local_runtime_project_mismatch")
    return path, config


def _capability_pid_alive(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        if pid > 0xffffffff:
            return False
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259)
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except (OSError, OverflowError):
        return False


def workspace_runtime_capability(engine, project_id=None):
    """Return validated local runtime evidence, or None with a safe diagnostic."""
    reason = "runtime_binding_unavailable"
    try:
        bound = configured_runtime(engine, project_id)
        if bound is None:
            raise ValueError
        reason = "capability_unreadable"
        path = Path(bound[1]["state_dir"]) / "runtime" / "capability.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        reason = "capability_invalid_schema"
        if not isinstance(value, dict) or value.get("schema") != "talk-runtime-capability-1":
            raise ValueError
        reason = "capability_invalid_protocol"
        if (not isinstance(value.get("runtime_protocol"), str)
                or value["runtime_protocol"] not in RUNTIME_MANAGER_PROTOCOLS
                or value.get("manager_protocol") != RUNTIME_MANAGER_PROTOCOLS[value["runtime_protocol"]]):
            raise ValueError
        reason = "capability_invalid_layouts"
        layouts = value.get("supported_layouts")
        if not isinstance(layouts, list) or "workspace-v1" not in layouts:
            raise ValueError
        reason = "capability_pid_not_alive"
        pid = value.get("pid")
        if type(pid) is not int or pid <= 0 or not _capability_pid_alive(pid):
            raise ValueError
        reason = "capability_invalid_time"
        for field in ("started_at", "written_at"):
            timestamp = value.get(field)
            if not isinstance(timestamp, str):
                raise ValueError
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return value
    except Exception:
        # Never include configuration contents, paths, or exception text in logs.
        logger.debug("workspace runtime capability rejected: %s", reason)
        return None


def ensure_local_runtime(engine, project_id=None):
    bound = configured_runtime(engine, project_id)
    if bound is None:
        return "disabled"
    path, config = bound
    from scripts.talk_runtime import launcher_lock, RuntimeErrorCode
    from scripts.role_service_host import ensure_private_dir, _hidden_startupinfo
    private = ensure_private_dir(Path(config["state_dir"]) / "runtime")
    try:
        with launcher_lock(private):
            pass
    except RuntimeErrorCode:
        return "already_running"
    command = [sys.executable, "-B", "-X", "utf8", "-m", "scripts.talk_runtime",
               "serve", "--config", str(path), "--apply", "--attach-api"]
    # 启动于真实API进程，不依赖当前聊天的工具进程；不接管已有API或角色PID。
    # DETACHED_PROCESS会令venv包装器的解释器另开可见控制台；NO_WINDOW让整条子链继承无控制台。
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (private/"launcher.out").open("ab") as out, (private/"launcher.err").open("ab") as err:
        subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                         **({"creationflags": flags, "startupinfo": _hidden_startupinfo()} if os.name == "nt" else {"start_new_session": True}))
    return "requested"


def require_local_runtime(engine, project_id=None):
    try:
        return ensure_local_runtime(engine, project_id)
    except Exception as exc:
        raise HTTPException(503, "local_runtime_unavailable") from exc


def recover_local_orphan(project_id, member_id, body, operator, session):
    """Explicit human operation, fenced by the SQLite write transaction."""
    import hashlib
    from sqlmodel import select
    from server.models import (AgentTask, RoleServiceRecovery, RoleServiceRecoveryRequest,
                               RoleServiceOrphanRecoveryOut)
    from server.role_service_recovery import orphan_candidate, recover_stopped, receipt
    from server.role_services import _as_utc, _now, _write_begin, load_role_service_context
    from server.role_host_resolution import RecoveryHostError, resolve_recovery_host
    from scripts.role_service_recovery import orphan_local_proof, terminate_orphan, OrphanTerminationFailed
    from scripts.role_service_host import HostError
    if operator.kind != "human":
        raise HTTPException(403, "only human members can recover role services")
    bound = configured_runtime(session.get_bind(), project_id)
    if bound is None or bound[1].get("project_id") != project_id:
        raise HTTPException(503, "local_runtime_unavailable")
    fingerprint = hashlib.sha256(json.dumps(
        {**body.model_dump(), "confirmed_by": operator.id}, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    _write_begin(session)
    try:
        prior = session.get(RoleServiceRecovery, (project_id, member_id, body.operation_key))
        if prior:
            if prior.request_fingerprint != fingerprint or "orphan_result" not in prior.before_state:
                raise HTTPException(409, "recovery_conflict")
            result = RoleServiceOrphanRecoveryOut(project_id=project_id, member_id=member_id,
                recovery=receipt(prior, replayed=True), **prior.before_state["orphan_result"])
            session.rollback()
            return result
        state, instance = orphan_candidate(project_id, member_id, session)
        if state.generation != body.expected_generation:
            raise HTTPException(409, "recovery_generation_conflict")
        tasks = session.exec(select(AgentTask).where(
            AgentTask.project_id == project_id, AgentTask.target_member_id == member_id,
            AgentTask.status.in_(("queued", "running")))).all()
        if instance.current_task_id is not None:
            current_task = session.get(AgentTask, instance.current_task_id)
            if (current_task is not None and current_task.project_id == project_id
                    and current_task not in tasks):
                tasks.append(current_task)
        if (tasks or instance.current_task_id is not None) and not body.confirm_task_interrupt:
            raise HTTPException(409, "orphan_tasks_active")
        plan = {"project_id": project_id, "member_id": member_id,
                "expected_generation": state.generation, "expected_process_launch_id": state.process_launch_id,
                "expected_instance_id": state.observed_instance_id, "expected_owner_host": state.owner_host,
                "process_pid": state.pid, "process_started_at": _as_utc(state.process_started_at).isoformat(),
                "instance_last_seen_at": _as_utc(instance.last_seen_at).isoformat()}
        ctx = load_role_service_context(project_id, member_id, session)
        try:
            target = resolve_recovery_host(config=bound[1], project_id=project_id, member_id=member_id,
                original_runtime=instance.runtime, current_runtime=ctx.runner.runtime if ctx.runner else None,
                control_kind=ctx.control_kind, storage_layout=ctx.role.storage_layout, data_root=ROOT)
            proof_args = {"workspace_runner": instance.runtime} if ctx.role.storage_layout == "workspace-v1" else {}
            proof = orphan_local_proof(plan, target.health_file, target.host_entry, **proof_args)
            if proof["already_exited"]:
                outcome = {"pid": state.pid, "already_exited": True, "exit_code": None,
                           "exit_confirmed": True, "termination_initiated": False}
            else:
                if orphan_local_proof(plan, target.health_file, target.host_entry, **proof_args) != proof:
                    raise HostError("orphan_process_unverified")
                outcome = terminate_orphan(state.pid, proof["created_at"])
        except OrphanTerminationFailed as exc:
            raise HTTPException(409, {"code": "orphan_terminate_failed", "termination_initiated": exc.initiated,
                "terminated_pid": exc.pid, "exit_confirmed": False,
                "message": "终止已发起但未能确认退出" if exc.initiated else "终止未能发起"}) from exc
        except (HostError, RecoveryHostError) as exc:
            raise HTTPException(409, exc.code) from exc
        interrupted = []
        for task in tasks:
            task.status = "failed"
            task.workflow_status = "failed"
            task.finished_at = _now()
            task.updated_at = task.finished_at
            task.last_error = "orphan_terminated_by_human"
            task.claim_token = None
            task.lease_expires_at = None
            session.add(task)
            interrupted.append(task.id)
        info = {"terminated_pid": outcome["pid"], "already_exited": outcome["already_exited"],
                "exit_code": outcome["exit_code"], "exit_confirmed": outcome["exit_confirmed"],
                "termination_initiated": outcome["termination_initiated"], "interrupted_task_ids": interrupted}
        request = RoleServiceRecoveryRequest.model_construct(operation_key=body.operation_key,
            expected_generation=state.generation, expected_process_launch_id=state.process_launch_id,
            expected_instance_id=state.observed_instance_id, expected_owner_host=state.owner_host,
            confirmation="orphan_process_terminated", reason="human_terminated_orphan")
        def audit_orphan(audit, _session):
            audit.before_state = {**audit.before_state, "orphan_result": info, "human_reason": body.reason,
                                  "confirmation": "orphan_process_terminated"}
        try:
            recovery = recover_stopped(project_id, member_id, request, operator, session, _orphan_locked=True,
                                       _fingerprint=fingerprint, _on_recovered=audit_orphan)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(500, {"code": "orphan_recovery_write_failed", "terminated_pid": outcome["pid"],
                "termination_initiated": outcome["termination_initiated"], "exit_confirmed": outcome["exit_confirmed"],
                "message": "进程退出已确认，但恢复状态未能保存；请重试。"}) from exc
        return RoleServiceOrphanRecoveryOut(project_id=project_id, member_id=member_id, recovery=recovery, **info)
    except Exception:
        session.rollback()
        raise


def recover_local_human_stop(project_id, member_id, operator, session):
    """仅明确human关闭动作触发；本机证明+原generation/launch CAS，失败不入队假关闭。"""
    if operator.kind != "human":
        raise HTTPException(403, "only human members can recover role services")
    try:
        bound = configured_runtime(session.get_bind(), project_id)
    except Exception as exc:
        raise HTTPException(503, "local_runtime_unavailable") from exc
    if bound is None or bound[1]["project_id"] != project_id:
        return False
    from server.role_service_recovery import recovery_plan, recover_stopped
    from server.models import AgentInstance, RoleServiceLaunch, RoleServiceRecoveryRequest
    from server.role_host_resolution import RecoveryHostError, resolve_recovery_host
    from server.role_services import load_role_service_context
    from scripts.role_service_recovery import local_proof
    from scripts.role_service_host import HostError
    ctx = load_role_service_context(project_id, member_id, session)
    layout = ctx.role.storage_layout
    try:
        plan = recovery_plan(project_id, member_id, operator, session, _expected_layout=layout).model_dump(mode="json")
    except HTTPException as exc:
        if exc.detail in ("recovery_no_ownership", "recovery_recent_heartbeat", "recovery_action_active"):
            return False
        raise
    config = bound[1]
    instance = session.get(AgentInstance, plan["expected_instance_id"])
    try:
        target = resolve_recovery_host(
            config=config, project_id=project_id, member_id=member_id,
            original_runtime=(instance.runtime if instance is not None else None),
            current_runtime=(ctx.runner.runtime if ctx.runner is not None else None),
            control_kind=ctx.control_kind, storage_layout=layout, data_root=ROOT)
    except RecoveryHostError as exc:
        raise HTTPException(409, exc.code) from exc
    health, entry = target.health_file, target.host_entry
    try:
        from scripts.role_service_recovery import recorded_process_state
        manager = json.loads(health.read_text(encoding="utf-8"))
        if not isinstance(manager, dict):
            raise HostError("recovery_manager_identity_mismatch")
        if recorded_process_state(manager.get("pid"),manager.get("seen_at")) == "present":
            # 原宿主仍在时继续沿它持有的Popen执行普通关闭，不能释放归属。
            return False
        # 两次独立核验紧邻CAS；活进程/未知/替代进程/新健康文件均拒绝。
        proof_args = {}
        if layout == "workspace-v1":
            launch = session.get(RoleServiceLaunch, plan["expected_process_launch_id"])
            proof_args = {"workspace_data_root": ROOT, "workspace_runner": instance.runtime,
                          "owner_token_hash": launch.owner_token_hash if launch else None}
        proof = local_proof(plan, health, entry, **proof_args)
        if local_proof(plan, health, entry, **proof_args) != proof:
            raise HostError("recovery_local_evidence_changed")
    except (HostError, OSError, ValueError) as exc:
        raise HTTPException(409, getattr(exc, "code", "local_recovery_unverified")) from exc
    request = RoleServiceRecoveryRequest(operation_key="human-stop-" + uuid.uuid4().hex,
        **{k:v for k,v in plan.items() if k.startswith("expected_")},
        confirmation="old_processes_confirmed_stopped", reason="original_host_exited")
    recover_stopped(project_id, member_id, request, operator, session, _expected_layout=layout)
    return True
