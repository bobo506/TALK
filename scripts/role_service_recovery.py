#!/usr/bin/env python3
"""原宿主消失后的显式人工恢复。plan只读，apply需审过的计划和明确确认。"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.role_service_host import HostError, TalkHostClient, _parse_iso
from server.models import RoleServiceRecoveryRequest


def probe_pid(pid: int) -> str:
    if os.name != "nt" or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return "unknown"
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return "absent" if ctypes.get_last_error() == 87 else "unknown"
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return "unknown"
        return "present" if code.value == 259 else "exited"
    finally:
        kernel.CloseHandle(handle)


def process_inventory():
    if os.name != "nt":
        raise HostError("recovery_os_unsupported")
    # argv仅在本地内存中用于识别，不输出、落盘或送入服务端。
    command = (
        "$ErrorActionPreference='Stop'; [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding; "
        "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw|node|kimi|dsh|codex)\\.exe$' } "
        "| Select-Object ProcessId,ParentProcessId,CommandLine) | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, encoding="utf-8", check=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        rows = json.loads(result.stdout.lstrip("\ufeff") or "[]")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise HostError("recovery_process_inventory_unknown") from exc
    return rows if isinstance(rows, list) else [rows]


def normalized(value):
    return str(value).strip('"').replace("\\", "/").casefold()


def local_proof(plan, health_path: Path, host_entry: Path, *, probe=None, inventory=None):
    probe = probe or probe_pid
    inventory = inventory or process_inventory
    if plan["expected_owner_host"].casefold() != socket.gethostname().casefold():
        raise HostError("recovery_wrong_local_host")
    health_bytes = health_path.read_bytes()
    health = json.loads(health_bytes.decode("utf-8"))
    if health.get("project_id") != plan["project_id"] or health.get("member_id") != plan["member_id"]:
        raise HostError("recovery_manager_identity_mismatch")
    seen = _parse_iso(health.get("seen_at"))
    if seen is None or (datetime.now(timezone.utc) - seen).total_seconds() <= 90:
        raise HostError("recovery_manager_recent")
    manager_pid, bridge_pid = health.get("pid"), plan["process_pid"]
    if probe(manager_pid) != "absent" or probe(bridge_pid) != "absent":
        raise HostError("recovery_process_not_absent")
    entry = normalized(host_entry.resolve(strict=True))
    for row in inventory():
        command = row.get("CommandLine")
        if not isinstance(command, str) or not command.strip():
            raise HostError("recovery_process_inventory_unknown")
        try:
            argv = [normalized(value) for value in shlex.split(command, posix=False)]
        except ValueError as exc:
            raise HostError("recovery_process_inventory_unknown") from exc
        scripts = [value for value in argv[1:] if value.endswith(".py")]
        active_entry = scripts[0] if scripts else ""
        if active_entry and Path(active_entry).is_absolute():
            try:
                # Windows 8.3短路径与完整路径必须识别为同一入口。
                active_entry = normalized(Path(active_entry).resolve(strict=True))
            except OSError as exc:
                raise HostError("recovery_process_inventory_unknown") from exc
        if (active_entry == entry or active_entry.endswith("/scripts/role_service_host.py")
                or (active_entry and not Path(active_entry).is_absolute()
                    and Path(active_entry).name == host_entry.name.casefold())
                or "scripts.role_service_host" in argv
                or normalized(plan["expected_instance_id"]) in argv
                or normalized(plan["expected_process_launch_id"]) in argv):
            raise HostError("recovery_replacement_process_present")
    return {"manager_pid": manager_pid, "bridge_pid": bridge_pid, "both_absent": True,
            "manager_health_sha256": hashlib.sha256(health_bytes).hexdigest(),
            "host_entry_sha256": hashlib.sha256(host_entry.read_bytes()).hexdigest()}


def api_path(project, member):
    return f"/api/projects/{quote(project, safe='')}/roles/{quote(member, safe='')}/service"


def create_plan(client, project, member, health_path, host_entry, operation_key):
    if client.request("GET", "/api/members/me").get("kind") != "human":
        raise HostError("recovery_operator_not_human")
    plan = client.request("GET", api_path(project, member) + "/recovery-plan")
    if plan.get("project_id") != project or plan.get("member_id") != member:
        raise HostError("recovery_plan_identity_mismatch")
    proof = local_proof(plan, health_path, host_entry)
    request = RoleServiceRecoveryRequest(
        operation_key=operation_key, **{key: value for key, value in plan.items() if key.startswith("expected_")},
        confirmation="old_processes_confirmed_stopped", reason="original_host_exited",
    )
    return {"schema": "talk-role-recovery-plan-1", "target": plan, "request": request.model_dump(),
            "manager_health_file": str(health_path.resolve()), "host_entry": str(host_entry.resolve()),
            "local_proof": proof}


def apply_plan(client, plan, *, confirm_stopped=False):
    if not confirm_stopped or plan.get("schema") != "talk-role-recovery-plan-1":
        raise HostError("recovery_confirmation_required")
    if client.request("GET", "/api/members/me").get("kind") != "human":
        raise HostError("recovery_operator_not_human")
    target = plan["target"]
    request = RoleServiceRecoveryRequest.model_validate(plan["request"])
    if any(getattr(request, key) != value for key, value in target.items() if key.startswith("expected_")):
        raise HostError("recovery_plan_identity_mismatch")
    health_path, entry = Path(plan["manager_health_file"]), Path(plan["host_entry"])
    for _ in range(2):
        proof = local_proof(target, health_path, entry)
        if proof != plan["local_proof"]:
            raise HostError("recovery_local_evidence_changed")
        current = client.request("GET", api_path(target["project_id"], target["member_id"]) + "/recovery-plan")
        if {k: v for k, v in current.items() if k != "checked_at"} != {k: v for k, v in target.items() if k != "checked_at"}:
            raise HostError("recovery_plan_changed")
    # 末次服务端读取后紧邻再查本地事实；仍不能冒称OS与HTTP为原子事务。
    if local_proof(target, health_path, entry) != plan["local_proof"]:
        raise HostError("recovery_local_evidence_changed")
    return client.request("POST", api_path(target["project_id"], target["member_id"]) + "/recover-stopped",
                          request.model_dump())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--operator-key-file", required=True)
    parser.add_argument("--project")
    parser.add_argument("--member")
    parser.add_argument("--manager-health-file", type=Path)
    parser.add_argument("--host-entry", type=Path)
    parser.add_argument("--operation-key")
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--confirm-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        key = Path(args.operator_key_file).read_text(encoding="utf-8").strip()
        if not key:
            raise HostError("recovery_operator_key_missing")
        client = TalkHostClient(args.base_url, key)
        if args.mode == "plan":
            if not all((args.project, args.member, args.manager_health_file, args.host_entry, args.operation_key)):
                parser.error("plan requires --project/--member/--manager-health-file/--host-entry/--operation-key")
            if args.plan_file.exists():
                raise HostError("recovery_plan_file_exists")
            plan = create_plan(client, args.project, args.member, args.manager_health_file,
                               args.host_entry, args.operation_key)
            args.plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"plan_written": True, "member_id": args.member, "production_mutations": 0}))
        else:
            result = apply_plan(client, json.loads(args.plan_file.read_text(encoding="utf-8")),
                                confirm_stopped=args.confirm_stopped)
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except HostError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code}))
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"ok": False, "error_code": "recovery_input_invalid"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
