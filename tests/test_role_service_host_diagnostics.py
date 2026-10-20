"""任务 272：受管宿主持久诊断接入的隔离测试。

只使用系统临时根、假 TALK 客户端、假子进程与内存/临时文件；不连接真实 TALK API，
不启动真实宿主/模型/CLI，不读取真实 Key 或生产日志根。测试通过
``bridges.runtime_diagnostics`` 的既有查询 API 与维护者 CLI 入口核对落盘事实。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridges import runtime_diagnostics as runtime_diag
from scripts import role_service_host as host
from scripts import role_service_host_diagnostics as host_diag
from scripts.role_service_host import HostError, HostManager, PreflightFacts
from scripts.runtime_diagnostics import main as diagnostics_cli_main

PYTHON_EXECUTABLE = getattr(sys, "_base_executable", sys.executable)
MEMBER = "agent:probe.role-272"
PROJECT = "prj_alpha"
INSTANCE = "ins_l1"
LAUNCH = "launch-272"
OPERATOR_SECRET = "FAKE-OPERATOR-SECRET-272"
ROLE_KEY = "FAKE-ROLE-KEY-272"
OWNER_TOKEN = "FAKE-OWNER-TOKEN-272"
CLAIM_TOKEN = "FAKE-CLAIM-TOKEN-272"
NATIVE_SECRET = "FAKE-NATIVE-SECRET-272"


class FakeProcess:
    """宿主真正依赖的 Popen 表面；不创建 OS 进程。"""

    def __init__(self, pid: int = 4242):
        self.pid = int(pid)
        self.exited = False
        self.returncode = None
        self.killed = False

    def poll(self):
        return self.returncode if self.exited else None

    def wait(self, timeout=None):
        self.exited = True
        self.returncode = 0
        return 0

    def terminate(self):
        self.exited = True
        self.returncode = 0

    def kill(self):  # pragma: no cover - 清理路径
        self.exited = True
        self.returncode = -9
        self.killed = True


class StuckProcess(FakeProcess):
    """stop 等待超时的假进程；用于保留 owner/句柄路径。"""

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd="fake-child", timeout=timeout or 0)


class ScriptedClient:
    """脚本化假 TALK 客户端：claim/report/roles/instances 全部本地回放。"""

    base_url = "http://isolated.invalid"

    def __init__(self):
        self.member_id = MEMBER
        self.expected_instance_id = INSTANCE
        self.command = {
            "runtime": "dsh",
            "model_alias": "fake-model",
            "runner_id": "runner:dsh-cli",
            "project_root": "",
        }
        self.claims: list[dict] = []
        self.reports: list[dict] = []
        self.claim_errors: list[BaseException] = []
        self.report_errors: list[BaseException] = []
        self.role_row = {
            "member_id": MEMBER,
            "archived": False,
            "binding_state": "bound",
            "runner": {"runner_id": "runner:dsh-cli", "runtime": "dsh"},
            "model": {
                "choice_id": "rmc_0123456789ab",
                "choice_source": "creation_operation",
                "choice_binding_mismatch": False,
                "model_id": "fake-model",
                "model_alias": "fake-model",
            },
            "service": {"can_start": True, "can_stop": False},
        }

    def request(self, method, path, body=None, key=None):
        if path.endswith("/members/me"):
            return {"id": self.member_id}
        if "/roles" in path:
            return {"data": [self.role_row]}
        if path.endswith("/claim"):
            self.claims.append(dict(body or {}))
            if self.claim_errors:
                raise self.claim_errors.pop(0)
            return {
                "owner_token": OWNER_TOKEN,
                "claim_token": CLAIM_TOKEN,
                "expected_instance_id": self.expected_instance_id,
                "command": dict(self.command),
            }
        if path.endswith("/report"):
            self.reports.append(dict(body or {}))
            if self.report_errors:
                raise self.report_errors.pop(0)
            return {"ok": True}
        if "/api/instances" in path:
            return {
                "data": [
                    {
                        "id": self.expected_instance_id,
                        "status": "idle",
                        "project_id": PROJECT,
                        "member_id": self.member_id,
                    }
                ]
            }
        if "/role-services" in path:
            return {"data": []}
        raise AssertionError(path)


class HostDiagnosticsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="talk272-host-diag-")
        self.root = Path(self._tmp.name)
        self.state_dir = self.root / "state"
        self.log_root = self.root / "logs"
        self.role_key_file = self.root / "role.key"
        self.role_key_file.write_text(ROLE_KEY + "\n", encoding="utf-8")
        self.client = ScriptedClient()
        self.client.command["project_root"] = str(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    # ── 脚手架 ──────────────────────────────────────────────────────

    def make_manager(self, *, log_root=None, disabled=False, **overrides) -> HostManager:
        options = dict(
            host="host-272",
            state_dir=self.state_dir,
            operator_key=OPERATOR_SECRET,
            role_key_file=self.role_key_file,
            project_root=self.root,
            ready_timeout=0.05,
            stop_timeout=0.02,
            runtime_log_dir=self.log_root if log_root is None else log_root,
            runtime_log_disabled=disabled,
            child_env={"TALK_NATIVE_SECRET": NATIVE_SECRET},
        )
        options.update(overrides)
        return HostManager(self.client, **options)

    def facts(self, *, runtime: str = "dsh", timeout: int | None = 21600) -> PreflightFacts:
        return PreflightFacts(
            argv=[PYTHON_EXECUTABLE, "child.py"],
            key_file=self.role_key_file,
            entry_fingerprint="local:child.py",
            binding_fingerprint="b" * 64,
            profile_fingerprint="p" * 64,
            child_env={"TALK_ROLE_SERVICE_MANAGED": "1"},
            runtime=runtime,
            execution_timeout_seconds=timeout,
            execution_timeout_source=(
                "builtin_default" if timeout == 21600 else "explicit"
            ),
            command_template_source="runtime_template",
        )

    def launch(self, *, launch_id: str = LAUNCH, generation: int = 1) -> dict:
        return {
            "launch_id": launch_id,
            "project_id": PROJECT,
            "member_id": MEMBER,
            "generation": generation,
            "expected_instance_id": INSTANCE,
        }

    def start_ready(self, manager: HostManager, *, process=None) -> dict:
        process = process or FakeProcess()
        with patch.object(manager, "preflight", return_value=self.facts()), patch(
            "scripts.role_service_host.spawn_hidden", return_value=process
        ), patch.object(manager, "_wait_ready", return_value=True):
            return manager.execute_start(self.launch())

    def query(self, **kwargs) -> list[dict]:
        if not Path(self.log_root).exists():
            return []
        return runtime_diag.query_records(
            root=self.log_root, limit=200, **kwargs
        )["records"]

    def find(self, event: str, **kwargs) -> dict:
        records = self.query(event=event, **kwargs)
        self.assertTrue(records, f"missing event {event!r}; have {self.event_names()}")
        return records[-1]

    def find_all(self, event: str, **kwargs) -> list[dict]:
        return self.query(event=event, **kwargs)

    def event_names(self) -> list[str]:
        return [str(record.get("event")) for record in self.query()]

    def log_text(self) -> str:
        if not Path(self.log_root).exists():
            return ""
        chunks: list[str] = []
        for path in sorted(Path(self.log_root).rglob("events-*.jsonl")):
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(chunks)

    def query_cli(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = diagnostics_cli_main(
                ["--log-dir", str(self.log_root), *arguments]
            )
        return code, stdout.getvalue(), stderr.getvalue()

    @contextlib.contextmanager
    def fake_popen_isinstance(self):
        """让宿主现有的 ``isinstance(process, subprocess.Popen)`` 接受假进程。

        生产语义不变；测试用假进程避免创建真实 OS 子进程。仅在当前上下文内把
        模块属性换成一个类型元组，宿主停止路径不会真正调用 ``Popen``。
        """
        with patch.object(host.subprocess, "Popen", (subprocess.Popen, FakeProcess)):
            yield

    # ── 1. 策略、默认开启与旧入口兼容 ───────────────────────────────

    def test_default_policy_is_enabled_and_old_constructors_still_work(self):
        policy = host_diag.HostDiagnosticsPolicy.resolve(env={})
        self.assertFalse(policy.disabled)
        self.assertEqual(policy.root, runtime_diag.DEFAULT_ROOT)
        self.assertEqual(policy.child_diagnostics_arguments(), [])

        # 旧构造：没有新增日志参数也能构造；默认日志开启。
        with patch.dict(
            os.environ, {host_diag.ENV_RUNTIME_LOG_DIR: ""}, clear=False
        ):
            manager = HostManager(
                self.client,
                state_dir=self.state_dir,
                operator_key=OPERATOR_SECRET,
                role_key_file=self.role_key_file,
                project_root=self.root,
            )
            self.assertFalse(manager.diagnostics_policy.disabled)
            self.assertEqual(manager.child_diagnostics_argv(), [])

        parsed = host.build_arg_parser().parse_args(["status", "--project", PROJECT])
        self.assertIsNone(parsed.runtime_log_dir)
        self.assertIsNone(parsed.runtime_log_retention_days)
        self.assertFalse(parsed.runtime_log_disabled)

    def test_default_root_is_used_when_no_explicit_root_is_given(self):
        default_root = self.root / "default-logs"
        with patch.object(runtime_diag, "DEFAULT_ROOT", default_root), patch.dict(
            os.environ, {host_diag.ENV_RUNTIME_LOG_DIR: ""}, clear=False
        ):
            manager = HostManager(
                self.client,
                state_dir=self.state_dir,
                operator_key=OPERATOR_SECRET,
                role_key_file=self.role_key_file,
                project_root=self.root,
            )
            with patch.object(manager, "preflight", return_value=self.facts()), patch(
                "scripts.role_service_host.spawn_hidden", return_value=FakeProcess()
            ), patch.object(manager, "_wait_ready", return_value=True):
                outcome = manager.execute_start(self.launch())
            self.assertEqual(outcome["outcome"], "ready")
            records = runtime_diag.query_records(root=default_root, limit=20)["records"]
            self.assertTrue(records)
            self.assertIn("ready", {record.get("event") for record in records})

    def test_disable_entry_writes_nothing_and_preserves_business_result(self):
        manager = self.make_manager(disabled=True)
        outcome = self.start_ready(manager)
        self.assertEqual(outcome["outcome"], "ready")
        self.assertIn(LAUNCH, manager._handles)
        self.assertTrue(manager.client.reports)
        self.assertFalse(Path(self.log_root).exists())
        self.assertEqual(self.query(), [])
        # 内置配方显式禁用；自定义入口保持旧 argv 语义（不追加任何日志参数）。
        self.assertEqual(
            manager.diagnostics_policy.child_diagnostics_arguments(),
            ["--disable-runtime-logs"],
        )
        custom = self.make_manager(
            disabled=True,
            cli_executable=PYTHON_EXECUTABLE,
            cli_args=["child.py"],
        )
        self.assertEqual(custom.child_diagnostics_argv(), [])

    def test_explicit_policy_child_arguments_only_use_real_bridge_options(self):
        manager = self.make_manager(
            runtime_log_retention_days=7,
            runtime_log_max_bytes=1024 * 1024,
            runtime_log_max_file_bytes=64 * 1024,
        )
        arguments = manager.child_diagnostics_argv()
        self.assertEqual(arguments[arguments.index("--runtime-log-dir") + 1], str(self.log_root))
        self.assertIn("--runtime-log-retention-days", arguments)
        self.assertIn("--runtime-log-max-bytes", arguments)
        self.assertIn("--runtime-log-max-file-bytes", arguments)

        # 用真实内置 bridge parser 解析：证明参数确实被所有真实入口支持，而不是自造标志。
        import importlib

        runtime_bases = {
            "dsh": (
                "bridges.cli_bridge",
                host.build_runtime_argv(
                    "dsh",
                    model_alias="fake-model",
                    command_template="dsh --model {model} --print",
                ),
            ),
            "cli": (
                "bridges.cli_bridge",
                host.build_runtime_argv(
                    "cli",
                    model_alias="fake-model",
                    command_template="my-cli --model {model} --batch",
                ),
            ),
            "codex": (
                "bridges.codex_bridge",
                host.build_runtime_argv(
                    "codex",
                    model_alias="fake-model",
                    command_template="codex exec --model {model} -",
                ),
            ),
            "kimi-code": (
                "bridges.kimi_bridge",
                host.build_runtime_argv("kimi-code", model_alias="fake-model"),
            ),
        }
        for runtime, (module_name, base) in runtime_bases.items():
            with self.subTest(runtime=runtime):
                module = importlib.import_module(module_name)
                namespace = module.build_parser().parse_args(
                    [str(part) for part in base[3:]] + arguments
                )
                self.assertEqual(namespace.runtime_log_dir, str(self.log_root))
                self.assertEqual(namespace.runtime_log_retention_days, 7.0)
                self.assertEqual(namespace.runtime_log_max_bytes, 1024 * 1024)
                self.assertEqual(namespace.runtime_log_max_file_bytes, 64 * 1024)

        custom = self.make_manager(
            cli_executable=PYTHON_EXECUTABLE, cli_args=["child.py"]
        )
        self.assertEqual(custom.child_diagnostics_argv(), [])

    def test_cli_and_environment_precedence_for_explicit_policy(self):
        env = {
            host_diag.ENV_RUNTIME_LOG_DIR: str(self.root / "env-logs"),
            host_diag.ENV_RUNTIME_LOG_RETENTION_DAYS: "9",
        }
        from_env = host_diag.HostDiagnosticsPolicy.resolve(env=env)
        self.assertEqual(from_env.root, self.root / "env-logs")
        self.assertEqual(from_env.retention_days, 9.0)
        self.assertTrue(from_env.explicit_root)
        self.assertEqual(
            from_env.child_diagnostics_arguments()[:2],
            ["--runtime-log-dir", str(self.root / "env-logs")],
        )
        from_cli = host_diag.HostDiagnosticsPolicy.resolve(
            root=self.root / "cli-logs", env=env
        )
        self.assertEqual(from_cli.root, self.root / "cli-logs")
        self.assertEqual(from_cli.retention_days, 9.0)
        disabled_env = host_diag.HostDiagnosticsPolicy.resolve(
            env={host_diag.ENV_RUNTIME_LOG_DISABLED: "true"}
        )
        self.assertTrue(disabled_env.disabled)

    # ── 2. 关联、预算、child PID 与正常生命周期 ─────────────────────

    def test_launch_records_carry_real_identity_budget_and_child_pid(self):
        manager = self.make_manager()
        outcome = self.start_ready(manager)
        self.assertEqual(outcome["outcome"], "ready")

        for event in ("launch_claimed", "spawned", "ready"):
            record = self.find(event)
            self.assertEqual(record["schema"], runtime_diag.SCHEMA)
            self.assertEqual(record["project_id"], PROJECT)
            self.assertEqual(record["member_id"], MEMBER)
            self.assertEqual(record["instance_id"], INSTANCE)
            self.assertEqual(record["launch_id"], LAUNCH)
            self.assertEqual(record["pid"], os.getpid())
            self.assertIsNone(record["task_id"])
            self.assertIsNone(record["message_id"])
            self.assertEqual(record["runtime"], "dsh")
            self.assertEqual(record["extra"]["generation"], 1)
            if event == "launch_claimed":
                self.assertNotIn("child_pid", record.get("extra") or {})
            else:
                self.assertEqual(record["extra"]["child_pid"], 4242)
            self.assertEqual(record["budgets"]["cli_timeout_seconds"], 21600)
            self.assertEqual(record["budgets"]["cli_timeout_source"], "builtin_default")
            self.assertEqual(record["budgets"]["ready_timeout_seconds"], 0.05)
            self.assertEqual(record["budgets"]["stop_timeout_seconds"], 0.02)
            self.assertIsNone(record["budgets"]["mcp_wait_seconds"])
            self.assertEqual(record["budgets"]["mcp_wait_budget_source"], "unknown")
            self.assertRegex(record["log_id"], r"^rtd-[A-Za-z0-9.-]+$")

        # 服务端 report 协议没有新增字段（公共面保持冻结）。
        for body in manager.client.reports:
            self.assertEqual(
                set(body),
                {
                    "generation",
                    "action",
                    "claim_token",
                    "owner_token",
                    "outcome",
                    "instance_id",
                    "pid",
                    "process_started_at",
                    "host",
                    "error_code",
                    "spawned",
                },
            )

    def test_host_level_events_do_not_borrow_a_role_or_a_message_id(self):
        manager = self.make_manager()
        with patch.object(
            manager, "claimable_actions", side_effect=[HostError("http_unavailable"), []]
        ):
            outcomes = manager.serve(PROJECT, poll_interval=0, max_rounds=2)
        self.assertEqual(
            outcomes, [{"action": "poll", "outcome": "failed", "error_code": "http_unavailable"}]
        )
        record = self.find("poll_failed")
        self.assertEqual(record["member_id"], "unknown")
        self.assertEqual(record["project_id"], PROJECT)
        self.assertIsNone(record["task_id"])
        self.assertIsNone(record["message_id"])
        self.assertEqual(record["stage"], "poll")
        self.assertEqual(record["exception"]["type"], "scripts.role_service_host.HostError")
        self.find("poll_recovered")
        self.find("host_started")
        self.find("host_stopped")

    # ── 3. 空消息、嵌套因果链与二次失败 ─────────────────────────────

    def test_empty_message_nested_exception_keeps_type_frames_and_cause_chain(self):
        manager = self.make_manager()
        manager._manager_diagnostics(PROJECT)  # 建立宿主级 writer

        def inner():
            raise ValueError()

        def outer():
            try:
                inner()
            except ValueError:
                raise RuntimeError()  # noqa: B904 - 故意制造空消息隐式上下文

        try:
            outer()
        except RuntimeError as exc:
            ref = manager.record_host_exception(
                PROJECT, exc, event="empty_message_probe", stage="test"
            )
        self.assertIsNotNone(ref)
        record = self.find("empty_message_probe")
        self.assertEqual(record["log_id"], ref)
        primary = record["exception"]
        self.assertTrue(primary["str_empty"])
        self.assertEqual(primary["type"], "RuntimeError")
        self.assertGreater(primary["frames_total"], 0)
        self.assertGreaterEqual(len(primary["frames"]), 1)
        self.assertEqual(primary["chain_depth"], 1)
        self.assertEqual(primary["cause_chain"][0]["relation"], "implicit_context")
        self.assertEqual(primary["cause_chain"][0]["type"], "ValueError")
        self.assertTrue(primary["cause_chain"][0]["str_empty"])

    def test_preflight_failure_and_report_secondary_failure_are_linked(self):
        manager = self.make_manager()
        self.client.report_errors.append(HostError("http_unavailable", "report down"))
        with patch.object(
            manager, "preflight", side_effect=HostError("profile_missing", "no profile")
        ):
            with self.assertRaises(HostError):
                manager.execute_start(self.launch())

        preflight = self.find("preflight_failed")
        report = self.find("report_failed")
        self.assertEqual(preflight["exception"]["type"], "scripts.role_service_host.HostError")
        self.assertEqual(preflight["extra"]["error_code"], "profile_missing")
        self.assertEqual(report["related_log_id"], preflight["log_id"])
        self.assertEqual(report["extra"]["business_error_code"], "profile_missing")
        self.assertEqual(report["extra"]["report_error_code"], "http_unavailable")
        self.assertIsNone(report["extra"]["child_pid"])
        self.assertEqual(manager._handles, {})
        self.assertTrue(self.client.claims)

    def test_spawn_failure_is_recorded_and_does_not_create_a_handle(self):
        manager = self.make_manager()
        with patch.object(manager, "preflight", return_value=self.facts()), patch(
            "scripts.role_service_host.spawn_hidden",
            side_effect=OSError("isolated spawn denial"),
        ):
            outcome = manager.execute_start(self.launch())
        self.assertEqual(outcome["outcome"], "failed")
        self.assertEqual(outcome["error_code"], "cli_missing")
        self.assertEqual(manager._handles, {})
        spawn = self.find("spawn_failed")
        self.assertEqual(spawn["stage"], "spawn")
        self.assertEqual(spawn["exception"]["type"], "OSError")
        self.assertEqual(spawn["extra"]["error_code"], "cli_missing")
        self.assertEqual(self.client.reports[-1]["spawned"], False)

    def test_readiness_failure_and_report_secondary_failure_keep_the_handle(self):
        manager = self.make_manager()
        self.client.report_errors.append(HostError("http_unavailable", "report down"))
        process = FakeProcess()
        with patch.object(manager, "preflight", return_value=self.facts()), patch(
            "scripts.role_service_host.spawn_hidden", return_value=process
        ), patch.object(
            manager, "_wait_ready", side_effect=HostError("readiness_timeout")
        ):
            with self.assertRaises(HostError):
                manager.execute_start(self.launch())
        self.assertIs(manager._handles[LAUNCH]["process"], process)
        readiness = self.find("readiness_failed")
        report = self.find("report_failed")
        self.assertEqual(readiness["extra"]["error_code"], "readiness_timeout")
        self.assertEqual(readiness["extra"]["child_pid"], 4242)
        self.assertEqual(report["related_log_id"], readiness["log_id"])
        self.assertEqual(report["extra"]["business_error_code"], "readiness_timeout")

    def test_claim_failure_is_recorded_without_creating_a_handle(self):
        manager = self.make_manager()
        self.client.claim_errors.append(HostError("launch_busy", "claim rejected"))
        with self.assertRaises(HostError):
            manager.execute_start(self.launch())
        self.assertEqual(manager._handles, {})
        record = self.find("claim_failed")
        self.assertEqual(record["stage"], "claim")
        self.assertEqual(record["member_id"], MEMBER)
        self.assertEqual(record["instance_id"], INSTANCE)
        self.assertEqual(record["launch_id"], LAUNCH)
        self.assertEqual(record["extra"]["error_code"], "launch_busy")
        self.assertIsNone(record["task_id"])

    def test_stop_control_file_failure_links_to_stop_timeout(self):
        manager = self.make_manager()
        process = StuckProcess()
        with patch.object(manager, "preflight", return_value=self.facts()), patch(
            "scripts.role_service_host.spawn_hidden", return_value=process
        ), patch.object(manager, "_wait_ready", return_value=True):
            self.assertEqual(manager.execute_start(self.launch())["outcome"], "ready")
        stop_action = dict(self.launch(launch_id="stop-control", generation=2), action="stop")
        with self.fake_popen_isinstance(), patch(
            "scripts.role_service_host._publish_private_bytes",
            side_effect=OSError("control file denied"),
        ):
            result = manager.execute_stop(stop_action)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "stop_timeout")
        self.assertIn(LAUNCH, manager._handles)
        control = self.find("stop_control_file_failed")
        timeout = self.find("stop_timeout")
        self.assertEqual(timeout["related_log_id"], control["log_id"])
        self.assertEqual(control["exception"]["type"], "OSError")
        self.assertEqual(timeout["exception"]["type"], "subprocess.TimeoutExpired")

    def test_ownership_save_failure_with_live_child_keeps_handle_and_records(self):
        manager = self.make_manager()
        process = FakeProcess()
        with patch.object(manager, "preflight", return_value=self.facts()), patch(
            "scripts.role_service_host.spawn_hidden", return_value=process
        ), patch.object(
            manager.store,
            "save",
            side_effect=HostError("storage_unavailable", "record denied"),
        ), patch.object(
            manager, "_abort_spawned_child", return_value=False
        ):
            result = manager.execute_start(self.launch())
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "storage_unavailable")
        self.assertIs(manager._handles[LAUNCH]["process"], process)
        record = self.find("ownership_save_failed")
        self.assertEqual(record["stage"], "ownership")
        self.assertEqual(record["extra"]["child_pid"], 4242)
        self.assertEqual(record["extra"]["error_code"], "storage_unavailable")
        self.assertEqual(manager.client.reports[-1]["spawned"], True)

    def test_already_exited_child_stop_is_recorded_and_releases_owner(self):
        manager = self.make_manager()
        process = FakeProcess()
        self.start_ready(manager, process=process)
        process.exited = True
        process.returncode = 0
        stop_action = dict(self.launch(launch_id="stop-exited", generation=2), action="stop")
        with self.fake_popen_isinstance():
            result = manager.execute_stop(stop_action)
        self.assertEqual(result["outcome"], "stopped")
        self.assertNotIn(LAUNCH, manager._handles)
        self.assertTrue(process.exited)
        record = self.find("stop_process_exited")
        self.assertEqual(record["extra"]["child_pid"], 4242)
        self.assertEqual(record["extra"]["child_exit_code"], 0)
        self.assertEqual(manager.client.reports[-1]["action"], "stop")
        self.assertEqual(manager.client.reports[-1]["outcome"], "stopped")

    def test_stop_timeout_and_report_secondary_failure_preserve_owner(self):
        manager = self.make_manager()
        process = StuckProcess()
        with patch.object(manager, "preflight", return_value=self.facts()), patch(
            "scripts.role_service_host.spawn_hidden", return_value=process
        ), patch.object(manager, "_wait_ready", return_value=True):
            self.assertEqual(manager.execute_start(self.launch())["outcome"], "ready")
        self.client.report_errors.append(HostError("http_unavailable", "report down"))
        stop_action = dict(self.launch(launch_id="stop-272", generation=2), action="stop")
        with self.fake_popen_isinstance(), self.assertRaises(HostError):
            manager.execute_stop(stop_action)
        self.assertIn(LAUNCH, manager._handles)
        self.assertIs(manager._handles[LAUNCH]["process"], process)
        timeout = self.find("stop_timeout")
        report = self.find("report_failed")
        self.assertEqual(timeout["exception"]["type"], "subprocess.TimeoutExpired")
        self.assertEqual(timeout["extra"]["child_pid"], 4242)
        self.assertEqual(timeout["extra"]["generation"], 2)
        self.assertEqual(report["related_log_id"], timeout["log_id"])
        self.assertEqual(report["extra"]["business_error_code"], "stop_timeout")
        self.assertEqual(report["extra"]["generation"], 2)
        self.assertEqual(
            {body.get("action") for body in manager.client.reports}, {"start", "stop"}
        )

    # ── 4. poll 断连后继续与 worker 边界 ────────────────────────────

    def test_poll_disconnect_then_real_stop_still_runs(self):
        manager = self.make_manager()
        process = FakeProcess()
        self.start_ready(manager, process=process)
        stop_action = dict(self.launch(launch_id="stop-after-poll", generation=2), action="stop")
        with self.fake_popen_isinstance(), patch.object(
            manager,
            "claimable_actions",
            side_effect=[HostError("http_unavailable"), [stop_action], []],
        ):
            outcomes = manager.serve(PROJECT, poll_interval=0, max_rounds=3)
        self.assertEqual(outcomes[0]["error_code"], "http_unavailable")
        self.assertEqual(outcomes[-1]["outcome"], "stopped")
        self.assertNotIn(LAUNCH, manager._handles)
        self.assertTrue(process.exited)
        self.find("poll_failed")
        self.find("poll_recovered")
        stopped = self.find("stopped")
        self.assertEqual(stopped["extra"]["child_pid"], 4242)
        self.assertEqual(stopped["extra"]["generation"], 2)

    def test_worker_round_exception_is_recorded_without_changing_outcomes(self):
        manager = self.make_manager()
        diagnostics = manager._manager_diagnostics(PROJECT)

        class RaisingWorker:
            io_budget_seconds = 0.01
            timeout_seconds = 0.01

            def run_round(self):
                raise RuntimeError()

            def request_stop(self):  # pragma: no cover - 本用例不会走到
                return None

        worker = RaisingWorker()
        thread, box = manager._start_worker_round(worker, diagnostics=diagnostics)
        thread.join(2.0)
        self.assertEqual(
            box["outcomes"],
            [{"stage": "worker", "outcome": "failed", "error_code": "http_error"}],
        )
        record = self.find("worker_round_failed")
        self.assertEqual(record["stage"], "provision_worker")
        self.assertEqual(record["exception"]["type"], "RuntimeError")
        self.assertTrue(record["exception"]["str_empty"])
        self.assertIsNone(record["task_id"])

    def test_worker_stop_failure_and_bounded_stop_are_recorded(self):
        manager = self.make_manager()
        diagnostics = manager._manager_diagnostics(PROJECT)
        outcomes: list[dict] = []

        class AliveThread:
            def join(self, timeout=None):
                return None

            def is_alive(self):
                return True

        class StubbornWorker:
            io_budget_seconds = 0.001
            timeout_seconds = 0.001

            def request_stop(self):
                raise RuntimeError("stop itself failed")

        with patch.object(host, "PROVISION_WORKER_SHUTDOWN_SLACK_SECONDS", 0.001), patch.object(
            host, "PROVISION_WORKER_SHUTDOWN_GRACE_CAP_SECONDS", 0.01
        ):
            manager._finish_worker_round(
                StubbornWorker(),
                AliveThread(),
                {"outcomes": None},
                outcomes,
                diagnostics=diagnostics,
            )
        self.assertEqual(outcomes[-1]["outcome"], "stopped")
        self.assertEqual(outcomes[-1]["error_code"], "worker_stopped")
        self.find("worker_stop_failed")
        self.find("worker_round_stopped")
        self.assertEqual(
            self.find("worker_round_stopped")["extra"]["error_code"], "worker_stopped"
        )

    def test_config_worker_init_failure_is_recorded_and_cli_returns_failed(self):
        from scripts import role_provision_worker

        class BoomWorker:
            def __init__(self, *args, **kwargs):
                raise role_provision_worker.WorkerError(
                    "worker_init_failed", "isolated worker init failure"
                )

        operator_file = self.root / "operator.key"
        operator_file.write_text(OPERATOR_SECRET + "\n", encoding="utf-8")
        buffer = io.StringIO()
        with patch.object(role_provision_worker, "RoleProvisionWorker", BoomWorker), contextlib.redirect_stdout(
            buffer
        ):
            code = host.main(
                [
                    "serve",
                    "--project",
                    PROJECT,
                    "--base-url",
                    "http://isolated.invalid",
                    "--operator-key-file",
                    str(operator_file),
                    "--state-dir",
                    str(self.state_dir),
                    "--project-root",
                    str(self.root),
                    "--runtime-log-dir",
                    str(self.log_root),
                    "--provision-worker",
                ]
            )
        self.assertEqual(code, host.EXIT_FAILED)
        self.assertEqual(json.loads(buffer.getvalue())["error_code"], "worker_init_failed")
        record = self.find("provision_worker_init_failed")
        self.assertEqual(record["stage"], "config_worker")
        self.assertEqual(record["exception"]["type"], "scripts.role_provision_worker.WorkerError")
        self.assertEqual(record["extra"]["error_code"], "worker_init_failed")
        self.assertEqual(record["member_id"], "unknown")

    # ── 5. 秘密保护与“不记录完整 argv/环境/输出” ────────────────────

    def test_known_and_opaque_secrets_are_redacted_before_disk(self):
        manager = self.make_manager(
            cli_executable=PYTHON_EXECUTABLE, cli_args=["child.py"]
        )
        quoted_secret = 'pa"ss\\word'
        opaque = "sk-live-abcdef1234567890"
        message = (
            f"operator={OPERATOR_SECRET} role={ROLE_KEY} owner={OWNER_TOKEN} "
            f"claim={CLAIM_TOKEN} native={NATIVE_SECRET} opaque={opaque} "
            f'password="{quoted_secret}" '
            + json.dumps({"owner_token": OWNER_TOKEN, "password": quoted_secret})
        )
        with patch.object(
            manager, "_role_facts", side_effect=HostError("role_facts_unavailable", message)
        ):
            outcome = manager.execute_start(self.launch())
        self.assertEqual(outcome["outcome"], "failed")
        self.assertEqual(outcome["error_code"], "role_facts_unavailable")
        text = self.log_text()
        for secret in (
            OPERATOR_SECRET,
            ROLE_KEY,
            OWNER_TOKEN,
            CLAIM_TOKEN,
            NATIVE_SECRET,
            quoted_secret,
            opaque,
        ):
            self.assertNotIn(secret, text)
        self.assertIn("[REDACTED]", text)
        record = self.find("preflight_failed")
        self.assertTrue(record["integrity"]["redacted"])
        self.assertTrue(record["integrity"]["redaction_kinds"])
        self.assertTrue(self.client.reports)

        # 维护者默认查询也不打印完整异常正文；--detail 仍只来自同一净化记录。
        code, stdout, _stderr = self.query_cli("--ref", record["log_id"], "--json")
        self.assertEqual(code, 0)
        self.assertNotIn(OPERATOR_SECRET, stdout)
        self.assertNotIn(ROLE_KEY, stdout)

    def test_logs_do_not_contain_full_argv_environment_or_child_output(self):
        manager = self.make_manager(
            cli_executable=PYTHON_EXECUTABLE,
            cli_args=["child.py", "--flag", "sensitive-arg-value"],
        )
        outcome = self.start_ready(manager)
        self.assertEqual(outcome["outcome"], "ready")
        text = self.log_text()
        for value in (
            "sensitive-arg-value",
            str(self.role_key_file),
            "--key-file",
            "TALK_NATIVE_SECRET",
            str(manager.project_root),
        ):
            self.assertNotIn(value, text)

    # ── 6. 日志根/写入/stderr 不可用与业务结果保持不变 ──────────────

    def test_unavailable_log_root_degrades_without_changing_business_result(self):
        bad_root = self.root / "not-a-directory"
        bad_root.write_text("occupied", encoding="utf-8")
        manager = self.make_manager(log_root=bad_root)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            outcome = self.start_ready(manager)
        self.assertEqual(outcome["outcome"], "ready")
        self.assertIn(LAUNCH, manager._handles)
        self.assertTrue(manager.client.reports)
        self.assertIn("本地诊断日志降级", stderr.getvalue())

    def test_write_failure_and_broken_stderr_do_not_replace_the_result(self):
        class BrokenStderr:
            def write(self, _text):
                raise OSError("stderr closed")

            def flush(self):
                raise OSError("stderr closed")

        manager = self.make_manager()
        original_append = runtime_diag.RuntimeDiagnostics._append_locked

        def broken_append(*args, **kwargs):
            raise OSError("injected write failure")

        with patch.object(
            runtime_diag.RuntimeDiagnostics, "_append_locked", side_effect=broken_append
        ), contextlib.redirect_stderr(BrokenStderr()):
            outcome = self.start_ready(manager)
        self.assertEqual(outcome["outcome"], "ready")
        self.assertIn(LAUNCH, manager._handles)
        self.assertTrue(manager.client.reports)
        self.assertIs(runtime_diag.RuntimeDiagnostics._append_locked, original_append)

    # ── 7. 跨重启按旧引用查询、关联不串角色/世代 ───────────────────

    def test_old_reference_survives_restart_and_maintainer_cli_query(self):
        manager = self.make_manager()
        self.start_ready(manager)
        ready = self.find("ready")
        ref = ready["log_id"]
        # 模拟重启：关闭本进程 writer；新进程/新 manager 只按旧引用查询。
        for writer in list(manager._launch_diag_writers.values()):
            writer.close()
        manager._launch_diag_writers.clear()
        for writer in list(manager._host_diag_writers.values()):
            writer.close()
        manager._host_diag_writers.clear()
        restarted = self.make_manager(log_root=self.log_root)
        self.assertEqual(restarted.diagnostics_policy.root, self.log_root)

        records = runtime_diag.query_records(root=self.log_root, ref=ref, limit=20)["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["log_id"], ref)
        self.assertEqual(records[0]["member_id"], MEMBER)
        self.assertEqual(records[0]["launch_id"], LAUNCH)
        self.assertEqual(records[0]["instance_id"], INSTANCE)

        code, stdout, _stderr = self.query_cli("--ref", ref, "--json")
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(len(payload["records"]), 1)
        self.assertEqual(payload["records"][0]["log_id"], ref)
        self.assertEqual(payload["records"][0]["event"], "ready")

        # 角色/实例过滤不串到宿主 worker 或另一个角色。
        member_records = self.query(member_id=MEMBER)
        self.assertTrue(member_records)
        self.assertTrue(all(item["member_id"] == MEMBER for item in member_records))
        self.assertFalse(self.query(member_id="agent:other"))
        self.assertFalse(self.query(instance_id="ins_other"))

    def test_two_role_writers_do_not_cross_contaminate(self):
        manager = self.make_manager()
        diag_a = manager._launch_diagnostics(
            project_id=PROJECT,
            member_id="agent:role-a",
            launch_id="launch-a",
            instance_id="ins_a",
            runtime="dsh",
        )
        diag_b = manager._launch_diagnostics(
            project_id=PROJECT,
            member_id="agent:role-b",
            launch_id="launch-b",
            instance_id="ins_b",
            runtime="codex",
        )
        ref_a = diag_a.record_event("role_probe", stage="test", extra={"role": "a"})
        ref_b = diag_b.record_event("role_probe", stage="test", extra={"role": "b"})
        records_a = self.query(member_id="agent:role-a")
        records_b = self.query(member_id="agent:role-b")
        self.assertEqual([item["log_id"] for item in records_a], [ref_a])
        self.assertEqual([item["log_id"] for item in records_b], [ref_b])
        self.assertFalse(self.query(member_id="agent:role-c"))
        self.assertNotEqual(ref_a, ref_b)


class HostLoopEvidenceDiagnosticsTests(unittest.TestCase):
    """任务 282：在既有 272 诊断夹具上追加本地循环证据集成用例。"""

    def setUp(self):
        self.case = HostDiagnosticsTestCase()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)

    def _manager_runs(self, run_id):
        from scripts import role_service_host_loop_evidence as loop_evidence

        records = self.case.query(event=loop_evidence.MANAGER_EVENT)
        return [
            record["extra"]["manager_run"]
            for record in records
            if record.get("extra", {})
            .get("manager_run", {})
            .get("manager_run_id")
            == run_id
        ]

    def _stopped_for(self, run_id):
        records = self.case.find_all("host_stopped")
        return [
            record
            for record in records
            if (record.get("extra") or {}).get("manager_run_id") == run_id
        ]

    def test_serve_once_and_max_rounds_write_one_stopped_each(self):
        manager = self.case.make_manager()
        self.assertEqual(manager.serve(PROJECT, poll_interval=0, once=True), [])
        first = self.case.find_all("host_stopped")
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["extra"]["stop_reason"], "once")
        run_id = first[0]["extra"]["manager_run_id"]
        self.assertRegex(run_id, r"^mgr-[0-9a-f]{32}$")
        runs = self._manager_runs(run_id)
        self.assertEqual([item["state"] for item in runs], ["started", "succeeded"])
        self.assertEqual(runs[0]["process"]["held"], None)
        self.assertTrue(runs[0]["process"]["truncated"])
        self.assertFalse(runs[1]["process"]["truncated"])

        second_manager = self.case.make_manager()
        self.assertEqual(
            second_manager.serve(PROJECT, poll_interval=0, max_rounds=2), []
        )
        stopped = sorted(
            self.case.find_all("host_stopped"),
            key=lambda item: item["recorded_at"],
        )
        self.assertEqual(len(stopped), 2)
        self.assertEqual(stopped[-1]["extra"]["stop_reason"], "max_rounds")
        self.assertEqual(stopped[-1]["extra"]["rounds"], 2)

    def test_cancel_and_unhandled_exception_have_one_stopped_each(self):
        manager = self.case.make_manager()
        cancellation = KeyboardInterrupt()
        with patch.object(
            manager, "claimable_actions", side_effect=cancellation
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertIs(caught.exception, cancellation)
        stopped = self.case.find_all("host_stopped")
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["extra"]["stop_reason"], "canceled")
        canceled_run = stopped[0]["extra"]["manager_run_id"]
        self.assertEqual(
            [item["state"] for item in self._manager_runs(canceled_run)],
            ["started", "canceled"],
        )

        second_manager = self.case.make_manager()
        failure = RuntimeError("unhandled-action")
        with patch.object(
            second_manager, "claimable_actions", side_effect=failure
        ):
            with self.assertRaises(RuntimeError) as caught:
                second_manager.serve(PROJECT, poll_interval=0, once=True)
        self.assertIs(caught.exception, failure)
        stopped = sorted(
            self.case.find_all("host_stopped"),
            key=lambda item: item["recorded_at"],
        )
        self.assertEqual(len(stopped), 2)
        self.assertEqual(stopped[-1]["extra"]["stop_reason"], "exception")
        exception_run = stopped[-1]["extra"]["manager_run_id"]
        self.assertEqual(
            [item["state"] for item in self._manager_runs(exception_run)],
            ["started"],
        )

    def test_disabled_diagnostics_keeps_serve_result_and_writes_nothing(self):
        manager = self.case.make_manager(disabled=True)
        self.assertEqual(manager.serve(PROJECT, poll_interval=0, once=True), [])
        self.assertFalse(Path(self.case.log_root).exists())
        self.assertEqual(self.case.query(), [])

    def test_cached_launch_identity_mismatch_is_not_written(self):
        from scripts import role_service_host_loop_evidence as loop_evidence

        manager = self.case.make_manager()
        manager._launch_diagnostics(
            project_id=PROJECT,
            member_id="agent:role-a",
            launch_id="launch-identity",
            instance_id="ins_a",
            runtime="dsh",
        )
        process = FakeProcess(pid=5555)
        record = {
            "project_id": PROJECT,
            "host": manager.host,
            "launch_id": "launch-identity",
            "member_id": "agent:role-b",
            "instance_id": "ins_b",
            "pid": process.pid,
            "runtime": "dsh",
        }
        manager._handles["launch-identity"] = {
            "process": process,
            "record": record,
            "record_persisted": False,
        }
        try:
            self.assertEqual(manager.serve(PROJECT, poll_interval=0, once=True), [])
            self.assertEqual(
                self.case.query(event=loop_evidence.LAUNCH_EVENT), []
            )
            stopped = self.case.find("host_stopped")
            run_id = stopped["extra"]["manager_run_id"]
            runs = self._manager_runs(run_id)
            self.assertEqual(runs[-1]["process"]["held"], 1)
            self.assertEqual(runs[-1]["process"]["alive"], 1)
        finally:
            manager._handles.pop("launch-identity", None)
            manager._drop_launch_diagnostics("launch-identity")

    def test_plain_ownership_substitute_keeps_start_ready_business(self):
        """单列替身：只绕开私有 ACL/os.replace，不证明私有发布通过。"""
        manager = self.case.make_manager()

        def plain_save(record):
            path = manager.store.record_path(
                record["project_id"],
                record["member_id"],
                record["launch_id"],
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return path

        with patch.object(manager.store, "save", side_effect=plain_save):
            outcome = self.case.start_ready(manager)
        self.assertEqual(outcome["outcome"], "ready")
        self.assertIn(LAUNCH, manager._handles)
        self.assertTrue(manager._handles[LAUNCH]["record_persisted"])

    def test_manager_events_are_unknown_member_and_summary_hides_extra(self):
        from scripts import role_service_host_loop_evidence as loop_evidence

        manager = self.case.make_manager()
        manager.serve(PROJECT, poll_interval=0, once=True)
        records = self.case.query(event=loop_evidence.MANAGER_EVENT)
        self.assertTrue(records)
        self.assertTrue(all(item["member_id"] == "unknown" for item in records))
        self.assertFalse(
            [
                item
                for item in records
                if item["member_id"] == MEMBER
            ]
        )
        code, stdout, _stderr = self.case.query_cli(
            "--event", loop_evidence.MANAGER_EVENT, "--json"
        )
        self.assertEqual(code, 0)
        summary = json.loads(stdout)
        self.assertTrue(summary["records"])
        for item in summary["records"]:
            self.assertNotIn("extra", item)
        code, stdout, _stderr = self.case.query_cli(
            "--event", loop_evidence.MANAGER_EVENT, "--json", "--detail"
        )
        self.assertEqual(code, 0)
        detail = json.loads(stdout)
        for item in detail["records"]:
            self.assertEqual(len(item["extra"]["manager_run"]), 16)
            self.assertEqual(len(item["extra"]["manager_run"]["process"]), 5)


if __name__ == "__main__":
    unittest.main()
