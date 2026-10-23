"""显式绑定的本机宿主：随API恢复；遗留归属只在human关闭请求内逐项核实。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
POINTER = ROOT / ".talk/runtime.local.json"


def bind_local_runtime(config_file, config):
    """显式运行统一入口时记住本机绑定；仅存清单路径，不复制任何凭据。"""
    if Path(config["project_root"]).resolve() != ROOT:
        return
    import tomllib
    with (ROOT/"config.toml").open("rb") as stream:
        database = tomllib.load(stream)["storage"]["db_path"]
    database = Path(database)
    if not database.is_absolute():
        database = ROOT/database
    POINTER.parent.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps({"schema":"talk-local-runtime-1", "database_file":str(database.resolve()),
                                  "config_file":str(Path(config_file).resolve())}), encoding="utf-8")


def configured_runtime(engine):
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


def ensure_local_runtime(engine):
    bound = configured_runtime(engine)
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


def require_local_runtime(engine):
    try:
        return ensure_local_runtime(engine)
    except Exception as exc:
        raise HTTPException(503, "local_runtime_unavailable") from exc


def recover_local_human_stop(project_id, member_id, operator, session):
    """仅明确human关闭动作触发；本机证明+原generation/launch CAS，失败不入队假关闭。"""
    if operator.kind != "human":
        raise HTTPException(403, "only human members can recover role services")
    try:
        bound = configured_runtime(session.get_bind())
    except Exception as exc:
        raise HTTPException(503, "local_runtime_unavailable") from exc
    if bound is None or bound[1]["project_id"] != project_id:
        return False
    from server.role_service_recovery import recovery_plan, recover_stopped
    from server.models import RoleServiceRecoveryRequest
    from scripts.role_service_recovery import local_proof
    from scripts.role_service_host import HostError, _sanitize_token
    try:
        plan = recovery_plan(project_id, member_id, operator, session).model_dump(mode="json")
    except HTTPException as exc:
        if exc.detail in ("recovery_no_ownership", "recovery_recent_heartbeat", "recovery_action_active"):
            return False
        raise
    config = bound[1]
    spec = next((s for s in config.get("hosts", []) if s["member_id"] == member_id), None)
    if spec:
        health = Path(spec["health_file"])
        entry = next((Path(a) for a in spec["argv"][1:] if a.endswith(".py")), None)
    elif config.get("workbuddy"):
        health = Path(config["state_dir"]) / "workbuddy-native" / _sanitize_token(project_id) / _sanitize_token(member_id) / "manager-health.json"
        entry = ROOT / "scripts/workbuddy_role_host.py"
    else:
        return False
    if entry is None:
        raise HTTPException(409, "local_recovery_entry_unverified")
    try:
        from scripts.role_service_recovery import recorded_process_state
        manager = json.loads(health.read_text(encoding="utf-8"))
        if recorded_process_state(manager.get("pid"),manager.get("seen_at")) == "present":
            # 原宿主仍在时继续沿它持有的Popen执行普通关闭，不能释放归属。
            return False
        # 两次独立核验紧邻CAS；活进程/未知/替代进程/新健康文件均拒绝。
        proof = local_proof(plan, health, entry)
        if local_proof(plan, health, entry) != proof:
            raise HostError("recovery_local_evidence_changed")
    except (HostError, OSError, ValueError) as exc:
        raise HTTPException(409, getattr(exc, "code", "local_recovery_unverified")) from exc
    request = RoleServiceRecoveryRequest(operation_key="human-stop-" + uuid.uuid4().hex,
        **{k:v for k,v in plan.items() if k.startswith("expected_")},
        confirmation="old_processes_confirmed_stopped", reason="original_host_exited")
    recover_stopped(project_id, member_id, request, operator, session)
    return True
