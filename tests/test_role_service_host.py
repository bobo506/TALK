"""角色生命周期 R1-3：宿主受管执行闭环的真实端到端测试（含首轮返修 F1–F6）。

在**隔离临时库 + 显式随机回环端口**上用真实 HTTP 跑完整链路：

``human start → 宿主 claim → 真实固定文本 Python 子进程 → 本次预分配实例上报
→ ready 回报 → 服务端四条件就绪 → human stop → 宿主优雅停止 → stopped``。

Windows 下由 ``subprocess.Popen`` 直接控制真实子进程 PID；父进程持有活句柄并核对
真实进程创建时刻（``GetProcessTimes``）。**不触碰任何生产进程/端口/Key/数据库**。
"""

from __future__ import annotations

import contextlib
import io
import http.client
import http.server
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import uvicorn
from sqlmodel import select

import server.main as main
from server.models import AgentInstance, RoleServiceLaunch, RoleServiceState
from scripts.role_provision import (
    _windows_verify_private_acl,
    key_file_path,
    profile_target_paths,
)
from scripts.role_service_host import (
    HostError,
    HostManager,
    OwnershipStore,
    PreflightFacts,
    TalkHostClient,
    build_child_argv,
    build_runtime_argv,
    load_operator_key,
    main as host_main,
    parse_unit_count,
    process_creation_time,
    redact,
    resolve_alias_flag,
    verify_runtime_entry,
)
from tests.test_role_services import RoleServiceTestCase

PYTHON_EXECUTABLE = getattr(sys, "_base_executable", sys.executable)

CHILD_SCRIPT = '''\
"""固定文本受控子进程（R1-3 隔离测试夹具，不访问真实模型/网络资源）。"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="")
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--runtime", default="fixed-text")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--project", default="")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--launch-id", required=True)
    parser.add_argument("--process-started-at", default="")
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    log_path = os.environ.get("TALK_TEST_CHILD_LOG")
    if log_path:
        with open(log_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "argv": list(sys.argv),
                    "pid": os.getpid(),
                    "model": args.model,
                    "env_keys": sorted(os.environ.keys()),
                    "home": os.environ.get("HOME") or os.environ.get("USERPROFILE") or "",
                    "inherited_native": bool(os.environ.get("TALK_TEST_NATIVE_SECRET")),
                    "has_key_value": any(
                        len(part) == 64 and part.isalnum() for part in sys.argv
                    ),
                },
                handle,
            )

    with open(args.key_file, "r", encoding="utf-8") as handle:
        key = handle.read().strip()

    base = args.base_url.rstrip("/")
    body = {
        "runtime": args.runtime,
        "status": "idle",
        "host": os.environ.get("TALK_TEST_HOST", "host-alpha"),
        "pid": os.getpid(),
        "project_id": args.project_id,
        "launch_id": args.launch_id,
    }
    if args.process_started_at:
        body["process_started_at"] = args.process_started_at
    request = urllib.request.Request(
        base + "/api/instances/" + args.instance_id,
        data=json.dumps(body).encode("utf-8"),
        headers={"X-API-Key": key, "Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(request, timeout=10).read()

    stop = threading.Event()

    def heartbeat():
        while not stop.is_set():
            time.sleep(0.5)
            try:
                beat = dict(body)
                beat["status"] = "idle"
                urllib.request.urlopen(
                    urllib.request.Request(
                        base + "/api/instances/" + args.instance_id,
                        data=json.dumps(beat).encode("utf-8"),
                        headers={"X-API-Key": key, "Content-Type": "application/json"},
                        method="PUT",
                    ),
                    timeout=10,
                ).read()
            except Exception:
                return

    worker = threading.Thread(target=heartbeat, daemon=True)
    worker.start()

    control = os.environ.get("TALK_ROLE_SERVICE_CONTROL_FILE", "")
    while True:
        time.sleep(0.2)
        if not control:
            continue
        try:
            with open(control, "r", encoding="utf-8") as handle:
                if handle.read().strip() == "shutdown":
                    break
        except OSError:
            continue
    stop.set()
    try:
        off = dict(body)
        off["status"] = "offline"
        urllib.request.urlopen(
            urllib.request.Request(
                base + "/api/instances/" + args.instance_id,
                data=json.dumps(off).encode("utf-8"),
                headers={"X-API-Key": key, "Content-Type": "application/json"},
                method="PUT",
            ),
            timeout=5,
        ).read()
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
'''


class FakeProcess:
    """宿主单测用的假子进程（只实现宿主真正依赖的 Popen 表面）。"""

    def __init__(self, pid: int):
        self.pid = pid
        self.exited = False
        self.killed = False

    def poll(self):
        return 0 if self.exited else None

    def wait(self, timeout=None):
        self.exited = True
        return 0

    def terminate(self):
        self.exited = True

    def kill(self):  # pragma: no cover - 清理路径
        self.exited = True
        self.killed = True


class FakeHostClient:
    """离线宿主单测用的假 TALK 客户端（只记录 claim/report，不联网）。"""

    base_url = "http://isolated.invalid"

    def __init__(self, member_id: str = "agent:probe.role-12345678"):
        self.member_id = member_id
        self.reports: list[dict] = []
        self.claims: list[dict] = []

    def request(self, method, path, body=None, key=None):
        if path.endswith("/members/me"):
            return {"id": self.member_id}
        if path.endswith("/claim"):
            self.claims.append(dict(body or {}))
            launch_id = path.split("/")[-2]
            return {
                "owner_token": "FAKE-OWNER",
                "claim_token": "FAKE-CLAIM",
                "expected_instance_id": "ins_" + launch_id,
                "command": {"runtime": "dsh", "model_alias": "fake-model"},
            }
        if path.endswith("/report"):
            self.reports.append(dict(body or {}))
            return {"ok": True}
        if "/role-services" in path:
            return {"data": []}
        raise AssertionError(path)


def _fake_facts(key_file: Path) -> PreflightFacts:
    return PreflightFacts(
        argv=[PYTHON_EXECUTABLE, "fixed_child.py"],
        key_file=key_file,
        entry_fingerprint="local:fixed_child.py",
        binding_fingerprint="b" * 64,
        profile_fingerprint="p" * 64,
        child_env={"TALK_ROLE_SERVICE_MANAGED": "1"},
        runtime="dsh",
    )


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class RoleServiceHostLoopTests(RoleServiceTestCase):
    """真实回环 HTTP + 真实子进程的受管启停闭环。"""

    def setUp(self):
        super().setUp()
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(
            main.app,
            host="127.0.0.1",
            port=self.port,
            log_level="critical",
            lifespan="on",
        )
        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(target=self.server.run, daemon=True)
        self.server_thread.start()
        self._wait_server()

        # 宿主私有状态根：与项目树无关的本机私有目录（默认在 ``~/.talk`` 的同级语义）。
        # 刻意放在项目工作区之外：受限令牌下，工作区内的私有 ACL 文件会被宿主拒绝
        # 原子替换/删除；生产默认根与系统临时区都具有完整的私有 ACL 生命周期。
        self.state_root = Path(tempfile.mkdtemp(prefix="r13-host-state-"))
        self.state_dir = self.state_root / "host-state"
        self.key_root = self._tmpdir / "keys"
        self.key_root.mkdir(parents=True, exist_ok=True)
        self.child_path = self._tmpdir / "fixed_child.py"
        self.child_path.write_text(CHILD_SCRIPT, encoding="utf-8")
        self.child_log = self._tmpdir / "child-argv.json"
        self.operator_key_file = self._tmpdir / "operator.key"
        self.operator_key_file.write_text("bobo-key\n", encoding="utf-8")

        # 本人三档（身份档）必须存在且非空：宿主预检据此核验 creation 事实。
        self.profiles = profile_target_paths(self._tmpdir, self.role_a)
        for kind, path in self.profiles.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {kind}\n固定文本测试身份档\n", encoding="utf-8")

        role_key = key_file_path(self.key_root, self.role_a)
        role_key.parent.mkdir(parents=True, exist_ok=True)
        role_key.write_text(self.role_a_key, encoding="utf-8")
        self.role_key_path = role_key
        self.manager = self._manager()
        self.spawned = []

    def tearDown(self):
        for handle in self.spawned:
            process = handle.get("process")
            if process is not None and process.poll() is None:
                with contextlib.suppress(Exception):
                    process.kill()
                with contextlib.suppress(Exception):
                    process.wait(timeout=10)
        self.server.should_exit = True
        self.server_thread.join(timeout=20)
        shutil.rmtree(self.state_root, ignore_errors=True)
        super().tearDown()

    def _wait_server(self):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.1)
        raise AssertionError("test server did not start")

    def _manager(self, *, state_dir: Path | None = None, **overrides) -> HostManager:
        client = TalkHostClient(self.base_url, "bobo-key")
        options = dict(
            host="host-alpha",
            state_dir=state_dir or self.state_dir,
            operator_key="bobo-key",
            role_key_root=self.key_root,
            cli_executable=PYTHON_EXECUTABLE,
            cli_args=[str(self.child_path)],
            ready_timeout=20.0,
            stop_timeout=10.0,
            project_root=self._tmpdir,
            child_log_dir=self._tmpdir / "child-logs",
            child_env={
                "TALK_TEST_CHILD_LOG": str(self.child_log),
                "TALK_TEST_HOST": "host-alpha",
            },
        )
        options.update(overrides)
        return HostManager(client, **options)

    def _track(self, manager: HostManager) -> None:
        for handle in manager._handles.values():
            if handle not in self.spawned:
                self.spawned.append(handle)

    def _child_logs(self) -> str:
        directory = self._tmpdir / "child-logs"
        parts = []
        if self.child_log.exists():
            with contextlib.suppress(OSError):
                parts.append(
                    "== argv ==\n" + self.child_log.read_text(encoding="utf-8")
                )
        if directory.exists():
            for path in sorted(directory.iterdir()):
                with contextlib.suppress(OSError):
                    parts.append(
                        f"== {path.name} ==\n{path.read_text(encoding='utf-8', errors='replace')}"
                    )
        return "\n".join(parts) or "<no child logs>"

    def _start_launch_via_api(self, *, project: str = "prj_alpha", member: str | None = None) -> dict:
        response = self.start(member, project=project)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    # ── 端到端闭环 ───────────────────────────────────────────────────

    def test_full_managed_start_and_stop_loop(self):
        launch = self._start_launch_via_api()
        outcome = self.manager.execute_start(launch)
        self._track(self.manager)
        handle = self.manager._handles.get(launch["launch_id"], {})
        process = handle.get("process")
        self.assertEqual(
            outcome["outcome"],
            "ready",
            f"{outcome}\npoll={process.poll() if process else None}\n{self._child_logs()}",
        )

        state = self.state_row()
        self.assertEqual(state.observed_state, "running")
        self.assertEqual(state.last_result, "success")
        self.assertEqual(state.observed_instance_id, launch["expected_instance_id"])
        self.assertEqual(state.process_launch_id, launch["launch_id"])
        self.assertEqual(state.owner_host, "host-alpha")
        self.assertTrue(state.spawned)
        row = self.launch_row(launch["launch_id"])
        self.assertEqual(row.state, "reported")
        self.assertEqual(row.outcome, "ready")

        with self.session() as session:
            instance = session.get(AgentInstance, launch["expected_instance_id"])
        self.assertIsNotNone(instance)
        self.assertEqual(instance.launch_id, launch["launch_id"])
        self.assertEqual(instance.project_id, "prj_alpha")
        self.assertEqual(instance.member_id, self.role_a)

        # 子进程 argv 里没有明文 Key、没有 owner/claim token、没有 operator Key。
        self.assertTrue(self.child_log.exists())
        argv_log = json.loads(self.child_log.read_text(encoding="utf-8"))
        joined = " ".join(argv_log["argv"])
        self.assertNotIn(self.role_a_key, joined)
        self.assertNotIn("bobo-key", joined)
        self.assertNotIn(row.claim_token_hash or "never", joined)
        self.assertIn("--key-file", argv_log["argv"])
        self.assertEqual(
            argv_log["argv"][argv_log["argv"].index("--instance-id") + 1],
            launch["expected_instance_id"],
        )
        # 子进程环境按角色隔离：私有 HOME，且不继承未核验的原生认证变量。
        self.assertEqual(argv_log["home"], str(self.manager.store.native_home_dir("prj_alpha", self.role_a)))
        self.assertFalse(argv_log["inherited_native"])
        self.assertNotIn("TALK_OPERATOR_API_KEY", argv_log["env_keys"])

        # 记录含真实 PID 与真实进程创建时刻，且磁盘记录与活句柄一致。
        record = handle["record"]
        self.assertEqual(record["pid"], process.pid)
        self.assertEqual(record["process_identity_source"], "os")
        self.assertAlmostEqual(
            process_creation_time(process.pid),
            datetime.fromisoformat(record["process_started_at"]).timestamp(),
            delta=2.0,
        )
        record_path = self.manager.store.record_path(
            "prj_alpha", self.role_a, launch["launch_id"]
        )
        self.assertTrue(record_path.is_file())
        if os.name == "nt":
            verified, detail = _windows_verify_private_acl(record_path)
            self.assertTrue(verified, detail)

        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        stop_outcome = self.manager.execute_stop(stopped.json())
        self.assertEqual(stop_outcome["outcome"], "stopped", stop_outcome)

        state = self.state_row()
        self.assertEqual(state.observed_state, "stopped")
        self.assertEqual(state.last_result, "stopped")
        self.assertIsNone(state.process_launch_id)
        self.assertIsNone(state.owner_host)
        self.assertIsNone(state.current_launch_id)
        self.assertFalse(state.spawned)
        self.assertIsNone(self.manager._handles.get(launch["launch_id"]))
        self.assertFalse(record_path.exists())

    def test_stop_without_live_handle_reports_unknown_owner_and_does_not_kill(self):
        launch = self._start_launch_via_api()
        outcome = self.manager.execute_start(launch)
        self._track(self.manager)
        self.assertEqual(outcome["outcome"], "ready", outcome)
        live = self.manager._handles[launch["launch_id"]]["process"]

        # 模拟管理器重启：新的管理器进程没有活句柄，只有磁盘记录 → 无法证明归属。
        restarted = self._manager()
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        result = restarted.execute_stop(stopped.json())
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "unknown_owner")
        # PID 只作诊断：没有活句柄就不杀进程，也不清原记录。
        self.assertIsNone(live.poll())
        record_path = restarted.store.record_path(
            "prj_alpha", self.role_a, launch["launch_id"]
        )
        self.assertTrue(record_path.exists())
        state = self.state_row()
        self.assertEqual(state.observed_state, "stopping")

    def test_tampered_owner_record_is_unknown_owner_and_writes_nothing(self):
        launch = self._start_launch_via_api()
        outcome = self.manager.execute_start(launch)
        self._track(self.manager)
        self.assertEqual(outcome["outcome"], "ready", outcome)
        handle = self.manager._handles[launch["launch_id"]]
        process = handle["process"]
        record_path = self.manager.store.record_path(
            "prj_alpha", self.role_a, launch["launch_id"]
        )
        original = json.loads(record_path.read_text(encoding="utf-8"))
        outside_marker = self._tmpdir / "outside-marker.txt"
        outside_marker.write_text("KEEP", encoding="utf-8")

        tampered = dict(
            original,
            pid=int(original["pid"]) + 12345,
            process_started_at="2020-01-01T00:00:00+00:00",
            control_file=str(outside_marker),
        )
        # 模拟“可改的磁盘记录”：删掉私有记录后写入被篡改的副本。
        os.remove(record_path)
        record_path.write_text(json.dumps(tampered), encoding="utf-8")

        stopped = self.stop()
        result = self.manager.execute_stop(stopped.json())
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "unknown_owner")
        # 零写入（控制文件不被覆盖）、零停止（进程仍活）、不清记录。
        self.assertEqual(outside_marker.read_text(encoding="utf-8"), "KEEP")
        self.assertIsNone(process.poll())
        self.assertIn(launch["launch_id"], self.manager._handles)
        self.assertTrue(record_path.exists())

        # 记录改回来后仍可正常停止（证明拒绝来自身份核对，而不是路径/权限副作用）。
        os.remove(record_path)
        self.manager.store.save(original)
        result = self.manager.execute_stop(stopped.json())
        self.assertEqual(result["outcome"], "stopped", result)
        self.assertIsNotNone(process.poll())

    def test_live_child_without_persisted_record_can_be_closed(self):
        launch = self._start_launch_via_api()

        def fail_after_instance(record):
            # 让真实子进程先完成本次实例登记，再注入落盘失败和停止超时。
            self.manager._wait_ready(record["instance_id"], "prj_alpha", self.role_a)
            raise HostError("storage_unavailable", "injected owned-file failure")

        try:
            with patch.object(self.manager.store, "save", side_effect=fail_after_instance), patch.object(
                self.manager, "_abort_spawned_child", return_value=False
            ):
                result = self.manager.execute_start(launch)
        finally:
            self._track(self.manager)
        self.assertEqual(result["error_code"], "storage_unavailable")
        process = self.manager._handles[launch["launch_id"]]["process"]
        self.assertIsNone(process.poll())
        self.assertIsNone(self.manager.store.load("prj_alpha", self.role_a, launch["launch_id"]))
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        outcome = self.manager.execute_stop(stopped.json())
        self.assertEqual(outcome["outcome"], "stopped", outcome)
        self.assertIsNotNone(process.poll())
        self.assertIsNone(self.state_row().process_launch_id)

    def test_close_request_survives_runner_control_kind_change(self):
        launch = self._start_launch_via_api()
        try:
            result = self.manager.execute_start(launch)
        finally:
            self._track(self.manager)
        self.assertEqual(result["outcome"], "ready", result)
        from tests.test_role_services import RUNNER_ID

        self.manager.client.request(
            "PATCH", f"/api/runners/{RUNNER_ID}/control-kind", {"control_kind": "unknown"}
        )
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        actions = self.manager.claimable_actions("prj_alpha")
        self.assertEqual([item["launch_id"] for item in actions], [stopped.json()["launch_id"]])
        outcomes = self.manager.serve("prj_alpha", once=True)
        self.assertEqual(outcomes[0]["outcome"], "stopped", outcomes)
        self.assertIsNone(self.state_row().process_launch_id)

    def test_live_child_can_close_after_poll_transport_interruptions(self):
        import urllib.request

        launch = self._start_launch_via_api()
        try:
            result = self.manager.execute_start(launch)
        finally:
            self._track(self.manager)
        self.assertEqual(result["outcome"], "ready", result)
        process = self.manager._handles[launch["launch_id"]]["process"]
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        original_urlopen = urllib.request.urlopen
        interruptions = [TimeoutError("read timed out"), http.client.IncompleteRead(b"{", 10)]

        def interrupted_get(request, *args, **kwargs):
            if request.get_method() == "GET" and interruptions:
                raise interruptions.pop(0)
            return original_urlopen(request, *args, **kwargs)

        with patch("scripts.role_service_host.urllib.request.urlopen", side_effect=interrupted_get):
            outcomes = self.manager.serve("prj_alpha", poll_interval=0, max_rounds=3)
        self.assertFalse(interruptions)
        self.assertEqual(outcomes[0], {"action": "poll", "outcome": "failed", "error_code": "host_unreachable"})
        self.assertEqual(outcomes[-1]["outcome"], "stopped", outcomes)
        self.assertIsNotNone(process.poll())
        self.assertIsNone(self.state_row().process_launch_id)
        self.assertNotIn(launch["launch_id"], self.manager._handles)

    def test_preflight_requires_profiles_and_registered_runtime(self):
        for path in self.profiles.values():
            path.unlink()
        launch = self._start_launch_via_api()
        result = self.manager.execute_start(launch)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "profile_missing")
        state = self.state_row()
        # 纯预检失败（没有 spawn）→ 服务端安全释放所有权，允许修正后重试。
        self.assertEqual(state.observed_state, "failed")
        self.assertIsNone(state.process_launch_id)
        self.assertFalse(state.spawned)
        projection = {row["member_id"]: row for row in self.list_services().json()}
        self.assertTrue(projection[self.role_a]["can_start"])

        for kind, path in self.profiles.items():
            path.write_text(f"# {kind}\n固定文本测试身份档\n", encoding="utf-8")

        # 未由人类登记的真实运行器入口稳定拒绝（只靠 control_kind=managed_cli 不放行）。
        real_manager = self._manager(cli_executable=None, cli_args=[])
        second = self._start_launch_via_api()
        result = real_manager.execute_start(second)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "runtime_unverified")

        registered = self._manager(
            cli_executable=None, cli_args=[], verified_runtimes=["dsh"]
        )
        third = self._start_launch_via_api()
        result = registered.execute_start(third)
        # dsh 的真实入口需要本地命令模板承载 alias → 未登记时稳定禁用，不会 spawn。
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "cli_command_unresolved")
        self.assertEqual(registered._handles, {})

    def test_status_and_cli_entry_are_wired(self):
        launch = self._start_launch_via_api()
        manager = self._manager()
        rows = manager.status("prj_alpha")
        row = {item["member_id"]: item for item in rows}[self.role_a]
        self.assertEqual(row["observed"], "starting")

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = host_main(
                [
                    "status",
                    "--project",
                    "prj_alpha",
                    "--base-url",
                    self.base_url,
                    "--operator-key-file",
                    str(self.operator_key_file),
                    "--state-dir",
                    str(self.state_dir),
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["schema"], "talk-role-service-host-1")
        self.assertTrue(payload["ok"])
        self.assertNotIn("token", json.dumps(payload).lower())
        self.assertEqual(launch["member_id"], self.role_a)

    def test_cli_start_never_spawns_and_hands_off_to_resident_manager(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = host_main(
                [
                    "start",
                    "--project",
                    "prj_alpha",
                    "--member",
                    self.role_a,
                    "--base-url",
                    self.base_url,
                    "--operator-key-file",
                    str(self.operator_key_file),
                    "--state-dir",
                    str(self.state_dir),
                    "--key-root",
                    str(self.key_root),
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["result"]["status"], "requested")
        self.assertEqual(payload["result"]["executor"], "serve")
        state = self.state_row()
        self.assertEqual(state.observed_state, "starting")
        self.assertIsNone(state.process_launch_id)
        # 常规 CLI 进程退出后不留任何无主受控进程：句柄只在常驻管理器里。
        self.assertEqual(self.manager._handles, {})

    def test_cli_start_all_never_spawns(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = host_main(
                [
                    "start-all",
                    "--project",
                    "prj_alpha",
                    "--base-url",
                    self.base_url,
                    "--operator-key-file",
                    str(self.operator_key_file),
                    "--state-dir",
                    str(self.state_dir),
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["result"]["counts"]["requested"], 1)
        self.assertEqual(payload["result"]["counts"]["started"], 0)
        self.assertEqual(self.state_row().observed_state, "starting")

    def test_serve_loop_executes_pending_actions_only(self):
        # 启动管理器本身不启动任何角色：没有 pending 动作时什么都不做。
        self.assertEqual(self.manager.serve("prj_alpha", once=True), [])
        self.assertIsNone(self.state_row())

        launch = self._start_launch_via_api()
        outcomes = self.manager.serve("prj_alpha", once=True)
        self._track(self.manager)
        self.assertEqual([row["outcome"] for row in outcomes], ["ready"])
        self.assertEqual(self.state_row().observed_state, "running")

        stopped = self.stop().json()
        stop_outcomes = self.manager.serve("prj_alpha", once=True)
        self.assertEqual([row["outcome"] for row in stop_outcomes], ["stopped"])
        self.assertEqual(self.state_row().observed_state, "stopped")
        self.assertEqual(stopped["action"], "stop")


class RoleServiceHostOwnershipUnitTests(unittest.TestCase):
    """宿主所有权保护（返修 F2）的离线单测：失败不覆盖、落盘失败不留无主子进程。"""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory(prefix="r13-host-unit-")
        self.root = Path(self._tmp.name)
        self.key = self.root / "role.key"
        self.key.write_text("FAKE-KEY-FOR-ISOLATION-ONLY\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _manager(self, client: FakeHostClient) -> HostManager:
        return HostManager(
            client,
            host="probe-host",
            state_dir=self.root / "state",
            role_key_file=self.key,
            project_root=self.root,
        )

    @staticmethod
    def _launch(client: FakeHostClient, launch_id: str, generation: int = 1) -> dict:
        return {
            "launch_id": launch_id,
            "project_id": "prj_probe",
            "member_id": client.member_id,
            "generation": generation,
            "expected_instance_id": "ins_" + launch_id,
        }

    def test_second_start_does_not_overwrite_live_ownership(self):
        client = FakeHostClient()
        manager = self._manager(client)
        first, second = FakeProcess(201), FakeProcess(202)
        with patch.object(manager, "preflight", return_value=_fake_facts(self.key)), patch(
            "scripts.role_service_host.spawn_hidden", side_effect=[first, second]
        ), patch.object(
            manager, "_wait_ready", side_effect=HostError("readiness_timeout")
        ):
            result1 = manager.execute_start(self._launch(client, "start1"))
            result2 = manager.execute_start(self._launch(client, "start2", 2))
        self.assertEqual(result1["error_code"], "readiness_timeout")
        self.assertEqual(result2["error_code"], "ownership_unreleased")
        # 第二个 start 根本没 claim、没 spawn，旧句柄与旧记录都保留。
        self.assertEqual(len(client.claims), 1)
        self.assertIsNone(first.poll())
        self.assertIsNone(second.poll())
        self.assertEqual(list(manager._handles), ["start1"])
        record = manager.store.load("prj_probe", client.member_id, "start1")
        self.assertIsNotNone(record)
        self.assertEqual(record["launch_id"], "start1")
        # 失败也带 spawned=True 的失败报告（服务端据此保留所有权）。
        self.assertTrue(any(row.get("spawned") is True for row in client.reports))

    def test_ownership_write_failure_after_spawn_keeps_handle_and_reports(self):
        client = FakeHostClient()
        manager = self._manager(client)

        class BoomStore(OwnershipStore):
            def save(self, record):  # noqa: D401 - 注入真实落盘失败
                raise HostError("storage_unavailable", "injected owned-file failure")

        manager.store = BoomStore(self.root / "state2")
        orphan = FakeProcess(301)
        with patch.object(manager, "preflight", return_value=_fake_facts(self.key)), patch(
            "scripts.role_service_host.spawn_hidden", return_value=orphan
        ):
            result = manager.execute_start(self._launch(client, "save-failed"))
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "storage_unavailable")
        # 子进程被成功优雅停止 → 不算所有权、不留无主进程，并且**一定**有失败报告。
        self.assertTrue(orphan.exited)
        self.assertEqual(manager._handles, {})
        self.assertTrue(client.reports)
        self.assertEqual(client.reports[-1]["spawned"], False)

    def test_ownership_write_failure_with_live_child_keeps_handle(self):
        client = FakeHostClient()
        manager = self._manager(client)

        class BoomStore(OwnershipStore):
            def save(self, record):
                raise HostError("storage_unavailable", "injected owned-file failure")

        manager.store = BoomStore(self.root / "state3")
        orphan = FakeProcess(302)
        orphan.wait = lambda timeout=None: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd="fake", timeout=timeout or 0)
        )
        with patch.object(manager, "preflight", return_value=_fake_facts(self.key)), patch(
            "scripts.role_service_host.spawn_hidden", return_value=orphan
        ):
            result = manager.execute_start(self._launch(client, "save-failed-2"))
        self.assertEqual(result["error_code"], "storage_unavailable")
        # 进程没停下：句柄必须保留，且失败报告必须带 spawned=True + 真实 PID。
        self.assertEqual(list(manager._handles), ["save-failed-2"])
        self.assertEqual(client.reports[-1]["spawned"], True)
        self.assertEqual(client.reports[-1]["pid"], 302)

    def test_oserror_while_publishing_record_keeps_original_handle(self):
        client = FakeHostClient()
        manager = self._manager(client)
        process = FakeProcess(303)
        with patch.object(manager, "preflight", return_value=_fake_facts(self.key)), patch(
            "scripts.role_service_host.spawn_hidden", return_value=process
        ), patch.object(manager.store, "save", side_effect=PermissionError("injected")), patch.object(
            manager, "_abort_spawned_child", return_value=False
        ):
            result = manager.execute_start(self._launch(client, "save-oserror"))
        self.assertEqual(result["error_code"], "storage_unavailable")
        self.assertIs(manager._handles["save-oserror"]["process"], process)
        self.assertFalse(manager._handles["save-oserror"]["record_persisted"])
        self.assertTrue(client.reports[-1]["spawned"])

    def test_report_failure_keeps_proof_of_an_already_stopped_child(self):
        client = FakeHostClient()
        manager = self._manager(client)
        process = FakeProcess(304)
        with patch.object(manager, "preflight", return_value=_fake_facts(self.key)), patch(
            "scripts.role_service_host.spawn_hidden", return_value=process
        ), patch.object(manager.store, "save", side_effect=HostError("storage_unavailable")), patch.object(
            manager, "_report", side_effect=HostError("http_unavailable")
        ):
            with self.assertRaises(HostError):
                manager.execute_start(self._launch(client, "save-report-error"))
        self.assertIsNotNone(process.poll())
        self.assertIs(manager._handles["save-report-error"]["process"], process)

    def test_supervisor_keeps_handles_across_a_poll_failure(self):
        client = FakeHostClient()
        manager = self._manager(client)
        process = FakeProcess(305)
        manager._handles["original"] = {"process": process, "record": {"member_id": client.member_id}}
        with patch.object(manager, "status", side_effect=[HostError("http_unavailable"), []]) as status:
            outcomes = manager.serve("prj_probe", poll_interval=0, max_rounds=2)
        self.assertEqual(status.call_count, 2)
        self.assertEqual(outcomes[0]["error_code"], "http_unavailable")
        self.assertIs(manager._handles["original"]["process"], process)
        self.assertIsNone(process.poll())

    def test_supervisor_survives_raw_network_failures(self):
        for error in (TimeoutError("read timed out"), http.client.IncompleteRead(b"{", 10)):
            with self.subTest(error=type(error).__name__):
                client = FakeHostClient()
                manager = self._manager(client)
                process = FakeProcess(306)
                manager._handles["original"] = {"process": process, "record": {"member_id": client.member_id}}
                with patch.object(manager, "status", side_effect=[error, error, []]) as status:
                    outcomes = manager.serve("prj_probe", poll_interval=0, max_rounds=3)
                self.assertEqual(status.call_count, 3)
                self.assertEqual(outcomes, [{"action": "poll", "outcome": "failed", "error_code": "host_unreachable"}])
                self.assertIs(manager._handles["original"]["process"], process)
                self.assertIsNone(process.poll())

    def test_action_transport_error_does_not_exit_supervisor(self):
        client = FakeHostClient()
        manager = self._manager(client)
        process = FakeProcess(307)
        manager._handles["original"] = {"process": process, "record": {"member_id": client.member_id}}
        action = {"action": "stop", "launch_id": "stop-original", "member_id": client.member_id}
        with patch.object(manager, "claimable_actions", side_effect=[[action], []]) as poll, patch.object(
            manager, "execute_stop", side_effect=http.client.IncompleteRead(b"{", 10)
        ):
            outcomes = manager.serve("prj_probe", poll_interval=0, max_rounds=2)
        self.assertEqual(poll.call_count, 2)
        self.assertEqual(outcomes[0]["error_code"], "host_unreachable")
        self.assertIs(manager._handles["original"]["process"], process)
        self.assertIsNone(process.poll())

    def test_record_file_is_private_and_paths_are_bounded(self):
        store = OwnershipStore(self.root / "state4")
        record = {
            "project_id": "prj_probe",
            "member_id": "agent:probe.role-12345678",
            "launch_id": "l1",
            "owner_token": "FAKE-OWNER",
            "host": "probe-host",
            "pid": 1,
            "process_started_at": "2026-10-11T00:00:00+00:00",
            "process_identity_source": "os",
            "instance_id": "ins_l1",
            "control_file": str(store.control_path("l1")),
            "created_at": "2026-10-11T00:00:00+00:00",
        }
        path = store.save(record)
        if os.name == "nt":
            verified, detail = _windows_verify_private_acl(path)
            self.assertTrue(verified, detail)
        self.assertEqual(store.load("prj_probe", "agent:probe.role-12345678", "l1"), record)
        # 路径越界的控制文件永远不会被接受为本次私有根内路径。
        escaped = store.control_path("../../escape")
        self.assertTrue(escaped.is_relative_to(store.state_dir))


class RoleServiceHostHttpTests(unittest.TestCase):
    """真实回环HTTP读中断不能终止持有原进程的管理循环。"""

    @contextlib.contextmanager
    def endpoint(self, modes):
        release = threading.Event()
        calls = []
        lock = threading.Lock()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                with lock:
                    mode = modes[min(len(calls), len(modes) - 1)]
                    calls.append(mode)
                self.close_connection = True
                if mode == "disconnect":
                    return
                status = 503 if mode == "error_body_timeout" else 409 if mode == "http_error" else 200
                body = json.dumps({"detail": "launch_busy"} if mode == "http_error" else {"data": []}).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(128 if mode in ("body_timeout", "error_body_timeout", "truncated") else len(body)))
                self.end_headers()
                self.wfile.flush()
                if mode in ("body_timeout", "error_body_timeout"):
                    release.wait(3)
                elif mode == "truncated":
                    self.wfile.write(b"{")
                    self.wfile.flush()
                else:
                    self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            yield TalkHostClient(f"http://127.0.0.1:{server.server_port}", "FAKE-HTTP-KEY", timeout=0.2), calls
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_network_failures_become_stable_host_errors(self):
        for mode in ("body_timeout", "error_body_timeout", "truncated", "disconnect"):
            with self.subTest(mode=mode), self.endpoint([mode]) as (client, calls):
                with self.assertRaises(HostError) as caught:
                    client.request("GET", "/temporary-response")
                self.assertEqual(caught.exception.code, "host_unreachable")
                self.assertNotIn("FAKE-HTTP-KEY", str(caught.exception))
                self.assertEqual(calls, [mode])

    def test_complete_responses_keep_api_semantics(self):
        with self.endpoint(["ok", "http_error"]) as (client, calls):
            self.assertEqual(client.request("GET", "/ok"), {"data": []})
            with self.assertRaises(HostError) as caught:
                client.request("GET", "/conflict")
            self.assertEqual(caught.exception.code, "launch_busy")
            self.assertEqual(calls, ["ok", "http_error"])

    def test_supervisor_recovers_from_response_body_failures(self):
        with tempfile.TemporaryDirectory(prefix="r13-http-recovery-") as directory, self.endpoint(
            ["body_timeout", "truncated", "ok"]
        ) as (client, calls):
            manager = HostManager(client, host="http-probe", state_dir=Path(directory) / "state", project_root=Path(directory))
            process = FakeProcess(308)
            manager._handles["original"] = {"process": process, "record": {"member_id": "agent:probe"}}
            outcomes = manager.serve("prj_probe", poll_interval=0, max_rounds=3)
            self.assertEqual(calls, ["body_timeout", "truncated", "ok"])
            self.assertEqual(outcomes, [{"action": "poll", "outcome": "failed", "error_code": "host_unreachable"}])
            self.assertIs(manager._handles["original"]["process"], process)
            self.assertIsNone(process.poll())


class RoleServiceHostArgumentTests(unittest.TestCase):
    """宿主脚本的 argv/凭据/入口兼容边界（不启进程、不联网）。"""

    def test_child_argv_is_a_list_without_plaintext_secret(self):
        argv = build_child_argv(
            ["python", "child.py"],
            member_id="agent:x.y-12345678",
            key_file=Path("C:/keys/agent.key"),
            runtime="dsh",
            model_alias="deepseek-flash",
            alias_flag=resolve_alias_flag("dsh"),
            instance_id="ins_abcdef123456",
            project_id="prj_alpha",
            project_root="C:/proj",
            launch_id="launch-1",
            process_started_at=datetime(2026, 10, 11, tzinfo=timezone.utc),
            base_url="http://127.0.0.1:8000",
        )
        self.assertIsInstance(argv, list)
        self.assertIn("--key-file", argv)
        self.assertIn("deepseek-flash", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "deepseek-flash")
        joined = " ".join(argv)
        self.assertNotIn("api_key=", joined)

    def test_alias_flag_uses_kimi_specific_option(self):
        self.assertEqual(resolve_alias_flag("kimi-code"), "--kimi-model")
        self.assertEqual(resolve_alias_flag("dsh"), "--model")
        self.assertEqual(resolve_alias_flag("custom", "--my-model"), "--my-model")

    def test_real_entry_argv_parses_with_real_repo_parsers(self):
        """返修 F1：模板必须被**真实仓库入口**接受，不支持则稳定禁用。"""
        kimi = build_runtime_argv("kimi-code", model_alias="kimi-code/kimi-for-coding")
        self.assertIn("--kimi-model", kimi)
        self.assertIn("kimi-code/kimi-for-coding", kimi)
        fingerprint = verify_runtime_entry("kimi-code", kimi)
        self.assertTrue(fingerprint.startswith("bridges.kimi_bridge@"))
        self.assertGreater(parse_unit_count(kimi, "kimi-code"), 10)

        # codex 的真实 parser 不接受任何模型参数 → 不允许猜 --model，稳定禁用。
        with self.assertRaises(HostError) as ctx:
            build_runtime_argv("codex", model_alias="fake-model")
        self.assertEqual(ctx.exception.code, "runtime_alias_unsupported")
        # dsh 的真实 parser 要求 --command → 没有本地登记命令模板时稳定禁用。
        with self.assertRaises(HostError) as ctx:
            build_runtime_argv("dsh", model_alias="fake-model")
        self.assertEqual(ctx.exception.code, "cli_command_unresolved")
        # 未知运行器稳定拒绝。
        with self.assertRaises(HostError) as ctx:
            build_runtime_argv("unknown-runtime", model_alias="fake-model")
        self.assertEqual(ctx.exception.code, "cli_missing")

        # 本地登记命令模板后，alias 精确进入真实入口，并被真实 parser 接受。
        dsh = build_runtime_argv(
            "dsh", model_alias="deepseek-flash", command_template="dsh --model {model} --print"
        )
        self.assertIn("dsh --model deepseek-flash --print", dsh)
        self.assertTrue(verify_runtime_entry("dsh", dsh).startswith("bridges.cli_bridge@"))
        self.assertGreater(parse_unit_count(dsh, "dsh"), 10)
        codex = build_runtime_argv(
            "codex", model_alias="gpt-5", command_template="codex exec --model {model} -"
        )
        self.assertTrue(verify_runtime_entry("codex", codex).startswith("bridges.codex_bridge@"))

    def test_operator_key_never_comes_from_plaintext_argv(self):
        from scripts.role_service_host import build_arg_parser

        with self.assertRaises(SystemExit):
            build_arg_parser().parse_args(
                ["status", "--project", "prj_alpha", "--operator-key", "plaintext"]
            )
        self.assertEqual(load_operator_key(None, {"TALK_OPERATOR_API_KEY": "env-key"}), "env-key")
        with self.assertRaises(HostError) as ctx:
            load_operator_key(None, {})
        self.assertEqual(ctx.exception.code, "operator_key_missing")

    def test_redact_is_a_strict_whitelist(self):
        payload = {
            "launch_id": "l1",
            "owner_token": "secret",
            "claim_token": "secret",
            "key_file": "C:/keys/x.key",
            "argv": ["python"],
            "outcome": "ready",
            "results": [{"member_id": "agent:a", "status": "requested", "owner_token": "x"}],
        }
        cleaned = redact(payload)
        self.assertEqual(set(cleaned), {"launch_id", "outcome", "results"})
        self.assertEqual(set(cleaned["results"][0]), {"member_id", "status"})


class FakeRoleFactsClient:
    """只回放一份角色投影的离线客户端（不发网络请求）。"""

    base_url = "http://isolated.invalid"

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def request(self, method, path, body=None, key=None):
        if "/roles" in path:
            return {"data": self.rows}
        raise AssertionError(path)


class RoleServiceHostChoiceSourceTests(unittest.TestCase):
    """补录来源准入（ROLE_LEGACY_ATTACH_DESIGN §投影与宿主守卫）。

    宿主只新增 ``legacy_attach`` 这一个合法来源；归档/绑定/能力/归属/unknown 守卫逐项保持，
    未知来源与失配一律继续稳定拒绝（``choice_unverified``）。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="r13-host-choice-source-")
        self.root = Path(self._tmp.name)
        self.key = self.root / "role.key"
        self.key.write_text("FAKE-KEY-FOR-ISOLATION-ONLY\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _row(**overrides) -> dict:
        row = {
            "member_id": "agent:legacy",
            "archived": False,
            "binding_state": "bound",
            "runner": {"runner_id": "runner:dsh-cli", "runtime": "dsh"},
            "model": {
                "choice_id": "rmc_0123456789ab",
                "choice_source": "legacy_attach",
                "choice_binding_mismatch": False,
                "model_id": "deepseek-flash",
                "model_alias": "deepseek-flash",
            },
            "service": {"can_start": True, "can_stop": False},
        }
        for section in ("runner", "model", "service"):
            if section in overrides and isinstance(overrides[section], dict):
                provided = overrides.pop(section)
                # 空字典 = 显式“缺该投影”，非空字典 = 局部覆盖默认字段。
                row[section] = {**row[section], **provided} if provided else {}
        row.update(overrides)
        return row

    def _manager(self, row: dict) -> HostManager:
        return HostManager(
            FakeRoleFactsClient([row]),
            host="probe-host",
            state_dir=self.root / "state",
            role_key_file=self.key,
            project_root=self.root,
        )

    def _facts(self, row: dict) -> dict:
        return self._manager(row)._role_facts(
            "prj_alpha", "agent:legacy", "FAKE-ROLE-KEY", action="start"
        )

    def test_legacy_attach_source_is_accepted(self):
        facts = self._facts(self._row())
        self.assertEqual(facts["model"]["choice_source"], "legacy_attach")
        self.assertEqual(facts["model"]["choice_id"], "rmc_0123456789ab")
        self.assertEqual(facts["runner"]["runner_id"], "runner:dsh-cli")

    def test_creation_operation_source_still_accepted(self):
        facts = self._facts(
            self._row(model={"choice_source": "creation_operation"})
        )
        self.assertEqual(facts["model"]["choice_source"], "creation_operation")

    def test_binding_fingerprint_includes_the_choice_source(self):
        creation = self._manager(
            self._row(model={"choice_source": "creation_operation"})
        )
        attach = self._manager(self._row(model={"choice_source": "legacy_attach"}))
        command = {"runner_id": "runner:dsh-cli", "runtime": "dsh", "model_alias": "deepseek-flash"}
        creation_facts = creation._role_facts(
            "prj_alpha", "agent:legacy", "FAKE-ROLE-KEY", action="start"
        )
        attach_facts = attach._role_facts(
            "prj_alpha", "agent:legacy", "FAKE-ROLE-KEY", action="start"
        )
        self.assertNotEqual(
            creation.binding_fingerprint(creation_facts, command),
            attach.binding_fingerprint(attach_facts, command),
        )

    def test_untrusted_sources_are_refused(self):
        for source in (
            "legacy_manual",
            "creation_operation_mismatch",
            "legacy_attach_mismatch",
            "",
            "unknown",
            "shadow_attach",
        ):
            with self.subTest(source=source):
                with self.assertRaises(HostError) as ctx:
                    self._facts(self._row(model={"choice_source": source}))
                self.assertEqual(ctx.exception.code, "choice_unverified")

    def test_missing_choice_or_mismatch_is_refused(self):
        for overrides in (
            {"model": {"choice_id": None}},
            {"model": {"choice_binding_mismatch": True}},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(HostError) as ctx:
                    self._facts(self._row(**overrides))
                self.assertEqual(ctx.exception.code, "choice_unverified")

    def test_existing_guards_still_apply_to_legacy_attach(self):
        cases = (
            ({"archived": True}, "role_facts_unavailable"),
            ({"binding_state": "unconfigured"}, "binding_fingerprint_mismatch"),
            ({"binding_state": None}, "binding_fingerprint_mismatch"),
            ({"service": {}}, "role_facts_unavailable"),
        )
        for overrides, code in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(HostError) as ctx:
                    self._facts(self._row(**overrides))
                self.assertEqual(ctx.exception.code, code)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
