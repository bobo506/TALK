"""产品片B（TALK 任务 260）：受管宿主运行器模板与执行预算的首次实现自测。

覆盖 ``docs/spec/ROLE_HOST_RUNTIME_CONFIGURATION_DESIGN.md`` 的全部验收面，且**不**访问
真实模型、真实 CLI、生产 API/SQLite 或真实凭据：

- ``--runtime-command-template``：同一 manager 上 codex+dsh 不串用、per-runtime 优先于旧
  全局回退、旧全局单字符串兼容、无模板保持原错误路径、重复同值去重、异值
  ``runtime_template_conflict``、未知/不适用 runtime、空白、缺 ``{model}``、Windows 空格路径；
- ``--cli-execution-timeout-seconds``：内置全部配方默认 86400、显式 60/43200、非法值
  （``bool``/0/负/小数/``NaN``/``Inf``/字符串/超范围）稳定拒绝，CLI 未显式给出时保留
  ``None``；
- 预检冻结的 argv/预算**直达**最终 ``spawn_hidden``：外层恰好一个 ``--timeout``，公开诊断
  与冻结快照一致，且不会在 spawn 时重取被篡改的 manager 配置；
- 显式 ``--cli-executable`` 自定义入口：旧接线保持、不附加 ``--timeout``、预算
  unknown/not_applied、与新参数组合稳定拒绝；
- 定向反例：同样的断言在**旧路径**（无 ``--timeout`` / 单一全局模板串用）上必然失败，
  证明断言不是恒真；
- 回归：``runtime-verified``、``legacy_attach`` choice 来源、unknown owner/stop 守卫、
  kimi-code 原生 ``--kimi-model`` 均保持。
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.role_service_host as role_service_host
from scripts.role_provision import profile_target_paths
from scripts.role_service_host import (
    DEFAULT_CLI_EXECUTION_TIMEOUT_SECONDS,
    MAX_CLI_EXECUTION_TIMEOUT_SECONDS,
    RUNTIME_RECIPES,
    HostError,
    HostManager,
    build_arg_parser,
    build_runtime_argv,
    main as host_main,
    normalize_execution_timeout,
    normalize_runtime_command_templates,
    redact,
    resolve_alias_flag,
    verify_runtime_entry,
)

PYTHON_EXECUTABLE = getattr(sys, "_base_executable", sys.executable)

MEMBER_ID = "agent:probe.role-12345678"
PROJECT_ID = "prj_alpha"
RUNNER_ID = "runner:dsh-cli"
MODEL_ALIAS = "deepseek-flash"

CODEX_TEMPLATE = 'codex exec --model {model} -'
DSH_TEMPLATE = "dsh --model {model} --print"
CLI_TEMPLATE = "my-cli -m {model} --batch"
WINDOWS_TEMPLATE = '"C:\\Program Files\\Codex CLI\\codex.cmd" exec --model {model} -'

BUILTIN_RUNTIMES = ("kimi-code", "codex", "dsh", "cli")
COMMAND_TEMPLATES = {"codex": CODEX_TEMPLATE, "dsh": DSH_TEMPLATE, "cli": CLI_TEMPLATE}


# ---------------------------------------------------------------------------
# 本片新增不变式（同时供正向用例与“旧坏路径”反例使用）
# ---------------------------------------------------------------------------


def outer_timeout_indexes(argv) -> list[int]:
    return [index for index, part in enumerate(argv) if part == "--timeout"]


def single_outer_timeout(argv) -> int:
    """外层 argv 必须**恰好一个** ``--timeout N``，返回 N。

    旧实现（本片之前）根本不会给外层 argv 加 ``--timeout``；因此该断言在旧路径上必然
    失败——这正是“定向反例证明新断言有效”的对象。
    """
    indexes = outer_timeout_indexes(argv)
    if len(indexes) != 1 or indexes[0] + 1 >= len(argv):
        raise AssertionError(f"外层 --timeout 不唯一: {argv}")
    return int(argv[indexes[0] + 1])


def template_present(argv, template: str, alias: str) -> bool:
    """argv 里是否原样出现了某个运行器的模板（用于证明 runtime 之间**没有**串用）。"""
    rendered = template.replace("{model}", alias)
    return any(str(part) == rendered for part in argv)


def real_parser_timeout(runtime: str, argv) -> int:
    """用**真实仓库入口**的 parser 解析 argv，返回 ``args.timeout``。"""
    module = importlib.import_module(RUNTIME_RECIPES[runtime].module)
    namespace = module.build_parser().parse_args([str(part) for part in argv[3:]])
    return int(namespace.timeout)


def free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# ---------------------------------------------------------------------------
# 离线脚手架
# ---------------------------------------------------------------------------


class _NeverCalledClient:
    """只用于**构造** manager 的假客户端：被调用即说明发生了不该发生的网络访问。"""

    base_url = "http://isolated.invalid"

    def request(self, method, path, body=None, key=None):  # pragma: no cover - 守卫
        raise AssertionError(f"离线用例不应发起网络访问: {method} {path}")


class FakeProcess:
    """宿主单测用的假子进程（只实现宿主真正依赖的 Popen 表面）。"""

    def __init__(self, pid: int):
        self.pid = pid
        self.exited = False

    def poll(self):
        return 0 if self.exited else None

    def wait(self, timeout=None):
        self.exited = True
        return 0

    def terminate(self):  # pragma: no cover - 清理路径
        self.exited = True

    def kill(self):  # pragma: no cover - 清理路径
        self.exited = True


class ScriptedHostClient:
    """脚本化假 TALK 客户端：回放成员/角色投影与 claim/report，完全不联网。"""

    base_url = "http://isolated.invalid"

    def __init__(self, *, runtime: str = "dsh", choice_source: str = "creation_operation"):
        self.runtime = runtime
        self.choice_source = choice_source
        self.member_id = MEMBER_ID
        self.expected_instance_id = "ins_l1"
        self.claims: list[dict] = []
        self.reports: list[dict] = []
        self.role_reads = 0
        self.command = {
            "runtime": runtime,
            "model_alias": MODEL_ALIAS,
            "runner_id": RUNNER_ID,
            "project_root": "",
        }

    def role_row(self) -> dict:
        return {
            "member_id": MEMBER_ID,
            "archived": False,
            "binding_state": "bound",
            "runner": {"runner_id": RUNNER_ID, "runtime": self.runtime},
            "model": {
                "choice_id": "rmc_0123456789ab",
                "choice_source": self.choice_source,
                "choice_binding_mismatch": False,
                "model_id": MODEL_ALIAS,
                "model_alias": MODEL_ALIAS,
            },
            "service": {"can_start": True, "can_stop": False},
        }

    def request(self, method, path, body=None, key=None):
        if path.endswith("/members/me"):
            return {"id": self.member_id}
        if "/roles" in path:
            self.role_reads += 1
            return {"data": [self.role_row()]}
        if path.endswith("/claim"):
            self.claims.append(dict(body or {}))
            return {
                "owner_token": "FAKE-OWNER",
                "claim_token": "FAKE-CLAIM",
                "expected_instance_id": self.expected_instance_id,
                "command": dict(self.command),
            }
        if path.endswith("/report"):
            self.reports.append(dict(body or {}))
            return {"ok": True}
        if "/api/instances" in path:
            return {"data": [{"id": self.expected_instance_id, "status": "idle"}]}
        raise AssertionError(path)


class HostConfigTestCase(unittest.TestCase):
    """公共脚手架：临时根、假 Key、本人三档、离线 client。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="r13-host-config-")
        self.root = Path(self._tmp.name)
        # 先断言隔离事实，再构造任何 manager / 客户端：状态根与身份档都在**工作区之外**的
        # 系统临时区，绝不触碰生产 `talk.db`、`~/.talk/role-service-host` 或真实 Key。
        self.assertFalse(
            self.root.is_relative_to(role_service_host.REPO_ROOT.resolve()),
            "测试根必须位于项目工作区之外",
        )
        self.state_dir = self.root / "state"
        self.assertFalse(self.state_dir.exists())
        self.key_file = self.root / "role.key"
        self.key_file.write_text("FAKE-ROLE-KEY-FOR-ISOLATION-ONLY\n", encoding="utf-8")
        self.profiles = profile_target_paths(self.root, MEMBER_ID)
        for kind, path in self.profiles.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {kind}\n固定文本测试身份档\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def make_manager(self, *, client=None, **overrides) -> HostManager:
        options = dict(
            host="probe-host",
            state_dir=self.state_dir,
            role_key_file=self.key_file,
            project_root=self.root,
            verified_runtimes=["codex", "dsh", "cli", "kimi-code"],
        )
        options.update(overrides)
        return HostManager(client or _NeverCalledClient(), **options)

    @staticmethod
    def launch(launch_id: str = "l1", generation: int = 1) -> dict:
        return {
            "launch_id": launch_id,
            "project_id": PROJECT_ID,
            "member_id": MEMBER_ID,
            "generation": generation,
            "expected_instance_id": "ins_l1",
        }


# ---------------------------------------------------------------------------
# 1. 运行器命令模板
# ---------------------------------------------------------------------------


class RuntimeCommandTemplateTests(HostConfigTestCase):
    def test_falsey_non_collections_are_not_silently_treated_as_missing(self):
        for value in (False, 0, "", 0.0):
            with self.subTest(value=repr(value)):
                with self.assertRaises(HostError) as ctx:
                    self.make_manager(runtime_command_templates=value)
                self.assertEqual(ctx.exception.code, "runtime_template_invalid")
                self.assertFalse(self.state_dir.exists())

    def test_programmatic_mapping_is_validated_and_copied(self):
        source = {"codex": CODEX_TEMPLATE}
        manager = self.make_manager(runtime_command_templates=source)
        self.assertEqual(manager.runtime_command_templates, {"codex": CODEX_TEMPLATE})
        # 构造后修改外部 dict：已构造 manager 的登记事实不受影响（副本语义）。
        source["codex"] = "HIJACKED --model {model}"
        source["dsh"] = DSH_TEMPLATE
        self.assertEqual(manager.runtime_command_templates, {"codex": CODEX_TEMPLATE})

    def test_repeatable_pairs_dedupe_same_value_and_refuse_conflict(self):
        resolved = normalize_runtime_command_templates(
            [
                ["codex", CODEX_TEMPLATE],
                ["codex", CODEX_TEMPLATE],  # 同值重复 → 去重
                ["  dsh  ", f"  {DSH_TEMPLATE}  "],  # 运行器名/模板空白会被规整
            ]
        )
        self.assertEqual(resolved, {"codex": CODEX_TEMPLATE, "dsh": DSH_TEMPLATE})

        with self.assertRaises(HostError) as ctx:
            normalize_runtime_command_templates(
                [["dsh", DSH_TEMPLATE], ["dsh", "dsh --model {model} --other"]]
            )
        self.assertEqual(ctx.exception.code, "runtime_template_conflict")
        # 同一冲突在程序化构造上也必须稳定拒绝（CLI 与构造共享校验）。
        with self.assertRaises(HostError) as ctx:
            self.make_manager(
                runtime_command_templates=[["dsh", DSH_TEMPLATE], ["dsh", "other {model}"]]
            )
        self.assertEqual(ctx.exception.code, "runtime_template_conflict")

    def test_unknown_and_not_applicable_runtimes_are_refused(self):
        for runtime in ("", "   ", "unknown-runtime", "kimi-code", "claude", "pi"):
            with self.subTest(runtime=runtime):
                with self.assertRaises(HostError) as ctx:
                    normalize_runtime_command_templates([[runtime, "x --model {model}"]])
                self.assertEqual(ctx.exception.code, "runtime_template_unsupported")

    def test_blank_and_missing_model_templates_are_refused(self):
        cases = (
            ("   ", "runtime_template_empty"),
            ("", "runtime_template_empty"),
            ("dsh --print", "runtime_template_missing_model"),
            ("dsh --model model --print", "runtime_template_missing_model"),
        )
        for template, code in cases:
            with self.subTest(template=template):
                with self.assertRaises(HostError) as ctx:
                    normalize_runtime_command_templates([["dsh", template]])
                self.assertEqual(ctx.exception.code, code)
                # 不合格模板**绝不**回退全局：显式给出就必须合格，且必须在构造期拒绝。
                with self.assertRaises(HostError) as ctx2:
                    self.make_manager(
                        cli_command_template=DSH_TEMPLATE,
                        runtime_command_templates={"dsh": template},
                    )
                self.assertEqual(ctx2.exception.code, code)

    def test_windows_style_template_with_spaces_is_accepted_verbatim(self):
        manager = self.make_manager(runtime_command_templates={"codex": WINDOWS_TEMPLATE})
        argv = manager.base_argv("codex", MODEL_ALIAS)
        self.assertTrue(template_present(argv, WINDOWS_TEMPLATE, MODEL_ALIAS))
        self.assertEqual(single_outer_timeout(argv), DEFAULT_CLI_EXECUTION_TIMEOUT_SECONDS)
        self.assertTrue(verify_runtime_entry("codex", argv).startswith("bridges.codex_bridge@"))

    def test_two_runtimes_on_one_manager_do_not_cross_use_templates(self):
        manager = self.make_manager(runtime_command_templates=dict(COMMAND_TEMPLATES))
        codex = manager.base_argv("codex", MODEL_ALIAS)
        dsh = manager.base_argv("dsh", MODEL_ALIAS)
        cli = manager.base_argv("cli", MODEL_ALIAS)
        self.assertTrue(template_present(codex, CODEX_TEMPLATE, MODEL_ALIAS))
        self.assertTrue(template_present(dsh, DSH_TEMPLATE, MODEL_ALIAS))
        self.assertTrue(template_present(cli, CLI_TEMPLATE, MODEL_ALIAS))
        self.assertFalse(template_present(codex, DSH_TEMPLATE, MODEL_ALIAS))
        self.assertFalse(template_present(codex, CLI_TEMPLATE, MODEL_ALIAS))
        self.assertFalse(template_present(dsh, CODEX_TEMPLATE, MODEL_ALIAS))
        self.assertFalse(template_present(dsh, CLI_TEMPLATE, MODEL_ALIAS))
        self.assertFalse(template_present(cli, DSH_TEMPLATE, MODEL_ALIAS))
        # 每个 runtime 各自的外层 argv 仍然恰好一个预算参数。
        for argv in (codex, dsh, cli):
            self.assertEqual(single_outer_timeout(argv), DEFAULT_CLI_EXECUTION_TIMEOUT_SECONDS)

    def test_runtime_without_its_own_template_is_not_satisfied_by_another_runtime(self):
        manager = self.make_manager(runtime_command_templates={"codex": CODEX_TEMPLATE})
        with self.assertRaises(HostError) as ctx:
            manager.base_argv("dsh", MODEL_ALIAS)
        self.assertEqual(ctx.exception.code, "cli_command_unresolved")
        self.assertEqual(manager.resolve_command_template("dsh")[1], "unresolved")

    def test_per_runtime_template_takes_priority_over_global_fallback(self):
        manager = self.make_manager(
            cli_command_template=DSH_TEMPLATE,
            runtime_command_templates={"dsh": CLI_TEMPLATE},
        )
        argv = manager.base_argv("dsh", MODEL_ALIAS)
        self.assertTrue(template_present(argv, CLI_TEMPLATE, MODEL_ALIAS))
        self.assertFalse(template_present(argv, DSH_TEMPLATE, MODEL_ALIAS))
        self.assertEqual(manager.resolve_command_template("dsh"), (CLI_TEMPLATE, "runtime_template"))

    def test_global_fallback_still_works_and_is_labelled(self):
        # 旧调用点：只给单字符串全局模板，不给任何新参数 → 行为与来源标注都可用。
        manager = self.make_manager(cli_command_template=DSH_TEMPLATE)
        argv, template_source, timeout_source = manager.build_entry_argv("dsh", MODEL_ALIAS)
        self.assertTrue(template_present(argv, DSH_TEMPLATE, MODEL_ALIAS))
        self.assertEqual(template_source, "global_template")
        self.assertEqual(timeout_source, "builtin_default")
        self.assertEqual(single_outer_timeout(argv), DEFAULT_CLI_EXECUTION_TIMEOUT_SECONDS)

    def test_missing_template_keeps_the_original_error_paths(self):
        manager = self.make_manager()
        for runtime, code in (
            ("codex", "runtime_alias_unsupported"),
            ("dsh", "cli_command_unresolved"),
            ("cli", "cli_command_unresolved"),
        ):
            with self.subTest(runtime=runtime):
                with self.assertRaises(HostError) as ctx:
                    manager.base_argv(runtime, MODEL_ALIAS)
                self.assertEqual(ctx.exception.code, code)
        # 旧全局模板缺 {model} 仍走既有 runtime_alias_unsupported。
        broken = self.make_manager(cli_command_template="dsh --print")
        with self.assertRaises(HostError) as ctx:
            broken.base_argv("dsh", MODEL_ALIAS)
        self.assertEqual(ctx.exception.code, "runtime_alias_unsupported")

    def test_kimi_code_keeps_native_model_flag_and_needs_no_template(self):
        manager = self.make_manager(runtime_command_templates=dict(COMMAND_TEMPLATES))
        argv = manager.base_argv("kimi-code", "kimi-code/kimi-for-coding")
        self.assertEqual(resolve_alias_flag("kimi-code"), "--kimi-model")
        self.assertIn("--kimi-model", argv)
        self.assertIn("kimi-code/kimi-for-coding", argv)
        self.assertNotIn("--model", argv)
        self.assertEqual(manager.resolve_command_template("kimi-code")[1], "not_applicable")
        self.assertTrue(verify_runtime_entry("kimi-code", argv).startswith("bridges.kimi_bridge@"))

    def test_custom_executable_with_new_options_is_refused(self):
        custom = dict(
            cli_executable=PYTHON_EXECUTABLE,
            cli_args=["child.py"],
        )
        with self.assertRaises(HostError) as ctx:
            self.make_manager(
                **custom, runtime_command_templates={"dsh": DSH_TEMPLATE}
            )
        self.assertEqual(ctx.exception.code, "cli_executable_option_unsupported")

        with self.assertRaises(HostError) as ctx:
            self.make_manager(**custom, execution_timeout_seconds=21600)
        self.assertEqual(ctx.exception.code, "cli_executable_option_unsupported")

        for build_argv in (
            lambda: normalize_runtime_command_templates(
                [["dsh", DSH_TEMPLATE]], cli_executable=PYTHON_EXECUTABLE
            ),
            lambda: normalize_execution_timeout(60, cli_executable=PYTHON_EXECUTABLE),
        ):
            with self.subTest(build=build_argv):
                with self.assertRaises(HostError) as ctx:
                    build_argv()
                self.assertEqual(ctx.exception.code, "cli_executable_option_unsupported")

        # 只给旧的全局模板（不给新参数）不算组合冲突：旧 custom 调用保持。
        legacy = self.make_manager(
            cli_executable=PYTHON_EXECUTABLE,
            cli_args=["child.py"],
            cli_command_template=DSH_TEMPLATE,
        )
        argv, template_source, timeout_source = legacy.build_entry_argv("dsh", MODEL_ALIAS)
        self.assertEqual(argv, [PYTHON_EXECUTABLE, "child.py"])
        self.assertEqual(template_source, "custom_executable")
        self.assertEqual(timeout_source, "not_applied")


# ---------------------------------------------------------------------------
# 2. 执行预算
# ---------------------------------------------------------------------------


class ExecutionTimeoutTests(HostConfigTestCase):
    def test_very_long_out_of_range_decimal_has_a_stable_error(self):
        with self.assertRaises(HostError) as ctx:
            normalize_execution_timeout("9" * 5000)
        self.assertEqual(ctx.exception.code, "execution_timeout_invalid")

    def test_leading_zeroes_do_not_change_a_representable_decimal_budget(self):
        self.assertEqual(normalize_execution_timeout("0" * 5000 + "60"), 60)

    def test_default_is_24_hours_on_every_builtin_recipe(self):
        manager = self.make_manager(runtime_command_templates=dict(COMMAND_TEMPLATES))
        self.assertIsNone(manager.execution_timeout_seconds)
        self.assertEqual(
            manager.effective_execution_timeout(), DEFAULT_CLI_EXECUTION_TIMEOUT_SECONDS
        )
        for runtime in BUILTIN_RUNTIMES:
            with self.subTest(runtime=runtime):
                argv, _template_source, timeout_source = manager.build_entry_argv(
                    runtime, MODEL_ALIAS
                )
                self.assertEqual(
                    single_outer_timeout(argv), DEFAULT_CLI_EXECUTION_TIMEOUT_SECONDS
                )
                self.assertEqual(timeout_source, "builtin_default")
                # 真实 parser 必须看到同一个数值（不是只写在宿主诊断里）。
                self.assertEqual(real_parser_timeout(runtime, argv), 86400)

    def test_explicit_60_and_43200_override_every_builtin_recipe(self):
        for requested in (60, 43200):
            manager = self.make_manager(
                runtime_command_templates=dict(COMMAND_TEMPLATES),
                execution_timeout_seconds=requested,
            )
            self.assertEqual(manager.execution_timeout_seconds, requested)
            self.assertEqual(manager.effective_execution_timeout(), requested)
            for runtime in BUILTIN_RUNTIMES:
                with self.subTest(runtime=runtime, requested=requested):
                    argv, _template_source, timeout_source = manager.build_entry_argv(
                        runtime, MODEL_ALIAS
                    )
                    self.assertEqual(single_outer_timeout(argv), requested)
                    self.assertEqual(timeout_source, "explicit")
                    self.assertEqual(real_parser_timeout(runtime, argv), requested)
                    self.assertTrue(
                        verify_runtime_entry(runtime, argv).startswith(
                            RUNTIME_RECIPES[runtime].module + "@"
                        )
                    )

    def test_invalid_values_are_refused_programmatically(self):
        invalid = (
            True,
            False,
            0,
            -1,
            -21600,
            1.5,
            21600.0,
            float("nan"),
            float("inf"),
            float("-inf"),
            "",
            "   ",
            "abc",
            "1.5",
            "21600.0",
            "nan",
            "inf",
            "1e9",
            "-60",
            "0",
            MAX_CLI_EXECUTION_TIMEOUT_SECONDS + 1,
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(HostError) as ctx:
                    normalize_execution_timeout(value)
                self.assertEqual(ctx.exception.code, "execution_timeout_invalid")
                with self.assertRaises(HostError) as ctx2:
                    self.make_manager(execution_timeout_seconds=value)
                self.assertEqual(ctx2.exception.code, "execution_timeout_invalid")

    def test_valid_numeric_forms_are_accepted_without_an_artificial_cap(self):
        self.assertIsNone(normalize_execution_timeout(None))
        for value, expected in (
            (1, 1),
            (21600, 21600),
            ("60", 60),
            ("  43200  ", 43200),
            (MAX_CLI_EXECUTION_TIMEOUT_SECONDS, MAX_CLI_EXECUTION_TIMEOUT_SECONDS),
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_execution_timeout(value), expected)

    def test_cli_keeps_none_when_the_flag_is_absent(self):
        args = build_arg_parser().parse_args(["status", "--project", PROJECT_ID])
        self.assertIsNone(args.cli_execution_timeout_seconds)
        explicit = build_arg_parser().parse_args(
            ["status", "--project", PROJECT_ID, "--cli-execution-timeout-seconds", "60"]
        )
        self.assertEqual(explicit.cli_execution_timeout_seconds, "60")
        self.assertEqual(
            normalize_execution_timeout(explicit.cli_execution_timeout_seconds), 60
        )

    def test_custom_executable_budget_is_unknown_and_not_applied(self):
        manager = self.make_manager(cli_executable=PYTHON_EXECUTABLE, cli_args=["child.py"])
        self.assertIsNone(manager.effective_execution_timeout())
        argv, _template_source, timeout_source = manager.build_entry_argv("dsh", MODEL_ALIAS)
        self.assertNotIn("--timeout", argv)
        self.assertEqual(timeout_source, "not_applied")


# ---------------------------------------------------------------------------
# 3. 预检 → 最终 spawn 的一致性（离线，假 API/Key/三档 + 假进程）
# ---------------------------------------------------------------------------


class PreflightToSpawnConsistencyTests(HostConfigTestCase):
    def test_budget_diagnostics_use_the_validated_argv_when_config_changes_during_preflight(self):
        real_verify = role_service_host.verify_runtime_entry
        for runtime in BUILTIN_RUNTIMES:
            for requested in (None, 60, 43200):
                with self.subTest(runtime=runtime, requested=requested):
                    client = self.make_client(runtime=runtime)
                    manager = self.make_manager(
                        client=client,
                        runtime_command_templates=dict(COMMAND_TEMPLATES),
                        execution_timeout_seconds=requested,
                    )
                    effective = 86400 if requested is None else requested

                    def verify_then_change_config(*args):
                        fingerprint = real_verify(*args)
                        manager.execution_timeout_seconds = 120
                        return fingerprint

                    with patch.object(role_service_host, "verify_runtime_entry", side_effect=verify_then_change_config):
                        outcome, captured = self.run_start(
                            manager, client, self.launch(f"budget-{runtime}-{requested}")
                        )
                    self.assertEqual(outcome["outcome"], "ready", outcome)
                    self.assertEqual(single_outer_timeout(captured["argv"]), effective)
                    self.assertEqual(real_parser_timeout(runtime, captured["argv"]), effective)
                    self.assertEqual(outcome["execution_timeout_seconds"], effective)
                    self.assertEqual(outcome["execution_timeout_source"], "builtin_default" if requested is None else "explicit")
                    for body in client.claims + client.reports:
                        self.assertNotIn("execution_timeout_seconds", body)
                        self.assertNotIn("execution_timeout_source", body)

    def test_budget_source_is_captured_together_with_argv(self):
        manager = self.make_manager(runtime_command_templates={"dsh": DSH_TEMPLATE})
        real_build = role_service_host.build_runtime_argv

        def build_then_change_config(*args, **kwargs):
            argv = real_build(*args, **kwargs)
            manager.execution_timeout_seconds = 60
            return argv

        with patch.object(role_service_host, "build_runtime_argv", side_effect=build_then_change_config):
            argv, _template_source, timeout_source = manager.build_entry_argv("dsh", MODEL_ALIAS)
        self.assertEqual(single_outer_timeout(argv), 86400)
        self.assertEqual(timeout_source, "builtin_default")

    def make_client(self, **overrides) -> ScriptedHostClient:
        client = ScriptedHostClient(**overrides)
        client.command["project_root"] = str(self.root)
        return client

    def run_start(self, manager: HostManager, client: ScriptedHostClient, launch: dict):
        captured: dict = {}

        def fake_spawn(argv, **kwargs):
            captured["argv"] = [str(part) for part in argv]
            captured["kwargs"] = kwargs
            return FakeProcess(4242)

        with patch("scripts.role_service_host.spawn_hidden", side_effect=fake_spawn):
            outcome = manager.execute_start(launch)
        return outcome, captured

    def test_preflight_argv_reaches_spawn_unchanged_with_one_outer_timeout(self):
        client = self.make_client()
        manager = self.make_manager(
            client=client, runtime_command_templates={"dsh": DSH_TEMPLATE}
        )
        facts = manager.preflight(
            client.command, MEMBER_ID, project_id=PROJECT_ID, action="start"
        )
        self.assertEqual(single_outer_timeout(facts.argv), 86400)
        self.assertEqual(facts.execution_timeout_seconds, 86400)
        self.assertEqual(facts.execution_timeout_source, "builtin_default")
        self.assertEqual(facts.command_template_source, "runtime_template")
        self.assertTrue(template_present(facts.argv, DSH_TEMPLATE, MODEL_ALIAS))

        outcome, captured = self.run_start(manager, client, self.launch())
        self.assertEqual(outcome["outcome"], "ready", outcome)
        argv = captured["argv"]
        # 最终 spawn 的 base 前缀逐项等于预检冻结的 argv。
        self.assertEqual(argv[: len(facts.argv)], list(facts.argv))
        self.assertEqual(single_outer_timeout(argv), 86400)
        self.assertEqual(
            single_outer_timeout(argv), outcome["execution_timeout_seconds"]
        )
        self.assertEqual(outcome["execution_timeout_seconds"], facts.execution_timeout_seconds)
        self.assertEqual(outcome["execution_timeout_source"], "builtin_default")
        self.assertEqual(outcome["command_template_source"], "runtime_template")
        # 公开诊断不是服务端协议字段：claim/report 里没有新增键。
        for body in client.claims + client.reports:
            self.assertNotIn("execution_timeout_seconds", body)
            self.assertNotIn("execution_timeout_source", body)
            self.assertNotIn("command_template_source", body)

    def test_explicit_43200_is_frozen_and_reaches_spawn(self):
        client = self.make_client()
        manager = self.make_manager(
            client=client,
            runtime_command_templates={"dsh": DSH_TEMPLATE},
            execution_timeout_seconds=43200,
        )
        facts = manager.preflight(
            client.command, MEMBER_ID, project_id=PROJECT_ID, action="start"
        )
        self.assertEqual(single_outer_timeout(facts.argv), 43200)
        self.assertEqual(facts.execution_timeout_source, "explicit")

        outcome, captured = self.run_start(manager, client, self.launch())
        self.assertEqual(outcome["outcome"], "ready", outcome)
        self.assertEqual(single_outer_timeout(captured["argv"]), 43200)
        self.assertEqual(outcome["execution_timeout_seconds"], 43200)
        self.assertEqual(outcome["execution_timeout_source"], "explicit")

    def test_spawn_uses_the_frozen_snapshot_not_mutated_manager_state(self):
        client = self.make_client()
        manager = self.make_manager(
            client=client, runtime_command_templates={"dsh": DSH_TEMPLATE}
        )
        original_preflight = manager.preflight

        def mutating_preflight(*args, **kwargs):
            facts = original_preflight(*args, **kwargs)
            # 预检之后、spawn 之前篡改 manager 的可变配置：最终 spawn 必须继续使用
            # 预检冻结的 argv/预算，绝不能重取配置造成前后不一致。
            manager.execution_timeout_seconds = 60
            manager.runtime_command_templates["dsh"] = "HIJACKED --model {model}"
            manager.cli_command_template = "HIJACKED-GLOBAL --model {model}"
            return facts

        with patch.object(manager, "preflight", side_effect=mutating_preflight):
            outcome, captured = self.run_start(manager, client, self.launch())
        self.assertEqual(outcome["outcome"], "ready", outcome)
        self.assertEqual(single_outer_timeout(captured["argv"]), 86400)
        self.assertTrue(template_present(captured["argv"], DSH_TEMPLATE, MODEL_ALIAS))
        self.assertFalse(
            any("HIJACKED" in str(part) for part in captured["argv"]),
            captured["argv"],
        )
        self.assertEqual(outcome["execution_timeout_seconds"], 86400)
        self.assertEqual(outcome["command_template_source"], "runtime_template")

    def test_custom_executable_spawn_has_no_bridge_timeout_and_no_budget_claim(self):
        client = self.make_client()
        manager = self.make_manager(
            client=client,
            cli_executable=PYTHON_EXECUTABLE,
            cli_args=["child.py"],
            alias_flag="--model",
        )
        facts = manager.preflight(
            client.command, MEMBER_ID, project_id=PROJECT_ID, action="start"
        )
        self.assertNotIn("--timeout", facts.argv)
        self.assertIsNone(facts.execution_timeout_seconds)
        self.assertEqual(facts.execution_timeout_source, "not_applied")
        self.assertEqual(facts.command_template_source, "custom_executable")

        outcome, captured = self.run_start(manager, client, self.launch())
        self.assertEqual(outcome["outcome"], "ready", outcome)
        self.assertNotIn("--timeout", captured["argv"])
        self.assertIsNone(outcome["execution_timeout_seconds"])
        self.assertEqual(outcome["execution_timeout_source"], "not_applied")
        self.assertEqual(outcome["command_template_source"], "custom_executable")
        # 旧 alias 接线保持：自定义入口仍由 build_child_argv 追加显式 alias flag。
        self.assertEqual(captured["argv"][captured["argv"].index("--model") + 1], MODEL_ALIAS)

    def test_public_diagnostics_are_bounded_and_never_leak_templates_or_argv(self):
        client = self.make_client()
        manager = self.make_manager(
            client=client, runtime_command_templates={"dsh": DSH_TEMPLATE}
        )
        facts = manager.preflight(
            client.command, MEMBER_ID, project_id=PROJECT_ID, action="start"
        )
        cleaned = redact(
            {
                "launch_id": "l1",
                **facts.diagnostics(),
                "argv": facts.argv,
                "key_file": str(facts.key_file),
                "command_template": DSH_TEMPLATE,
            }
        )
        self.assertEqual(
            set(cleaned),
            {
                "launch_id",
                "execution_timeout_seconds",
                "execution_timeout_source",
                "command_template_source",
            },
        )
        text = json.dumps(cleaned, ensure_ascii=False)
        self.assertNotIn(DSH_TEMPLATE, text)
        self.assertNotIn("child.py", text)
        self.assertNotIn(str(self.key_file), text)
        self.assertNotIn("FAKE-ROLE-KEY", text)


# ---------------------------------------------------------------------------
# 4. CLI main 接线（真实 HostManager 构造 + 校验先于凭据读取）
# ---------------------------------------------------------------------------


class CliWiringTests(HostConfigTestCase):
    def test_very_long_budget_fails_cleanly_before_credentials_network_or_spawn(self):
        with patch.object(role_service_host, "load_operator_key") as key_read, patch.object(
            role_service_host, "TalkHostClient"
        ) as client, patch.object(role_service_host, "spawn_hidden") as spawn:
            code, stdout = self.run_main([
                "status", "--project", PROJECT_ID,
                "--cli-execution-timeout-seconds", "9" * 5000,
            ])
        self.assertEqual(code, role_service_host.EXIT_FAILED)
        self.assertEqual(json.loads(stdout)["error_code"], "execution_timeout_invalid")
        key_read.assert_not_called()
        client.assert_not_called()
        spawn.assert_not_called()

    def setUp(self):
        super().setUp()
        self.operator_key_file = self.root / "operator.key"
        self.operator_key_file.write_text("FAKE-OPERATOR-KEY\n", encoding="utf-8")

    def run_main(self, argv, *, env=None):
        buffer = io.StringIO()
        with patch.dict(
            os.environ,
            env
            or {
                "TALK_OPERATOR_API_KEY": "",
                "TALK_OPERATOR_KEY_FILE": "",
            },
        ), contextlib.redirect_stdout(buffer):
            code = host_main(argv)
        return code, buffer.getvalue()

    def test_parser_accepts_repeatable_pairs_and_optional_budget(self):
        args = build_arg_parser().parse_args(
            [
                "serve",
                "--project",
                PROJECT_ID,
                "--runtime-command-template",
                "codex",
                CODEX_TEMPLATE,
                "--runtime-command-template",
                "dsh",
                DSH_TEMPLATE,
            ]
        )
        self.assertEqual(
            args.runtime_command_template,
            [["codex", CODEX_TEMPLATE], ["dsh", DSH_TEMPLATE]],
        )
        self.assertIsNone(args.cli_execution_timeout_seconds)
        with self.assertRaises(SystemExit):
            build_arg_parser().parse_args(
                ["serve", "--project", PROJECT_ID, "--runtime-command-template", "dsh"]
            )

    def test_invalid_new_config_is_rejected_before_any_credential_read(self):
        cases = (
            (
                ["status", "--project", PROJECT_ID, "--runtime-command-template", "codex", "no-placeholder"],
                "runtime_template_missing_model",
            ),
            (
                ["status", "--project", PROJECT_ID, "--runtime-command-template", "kimi-code", "kimi {model}"],
                "runtime_template_unsupported",
            ),
            (
                ["status", "--project", PROJECT_ID, "--runtime-command-template", "dsh", DSH_TEMPLATE, "--runtime-command-template", "dsh", CLI_TEMPLATE],
                "runtime_template_conflict",
            ),
            (
                ["status", "--project", PROJECT_ID, "--cli-execution-timeout-seconds", "0"],
                "execution_timeout_invalid",
            ),
            (
                ["status", "--project", PROJECT_ID, "--cli-execution-timeout-seconds", "1.5"],
                "execution_timeout_invalid",
            ),
            (
                ["status", "--project", PROJECT_ID, "--cli-executable", PYTHON_EXECUTABLE, "--cli-execution-timeout-seconds", "60"],
                "cli_executable_option_unsupported",
            ),
            (
                ["status", "--project", PROJECT_ID, "--cli-executable", PYTHON_EXECUTABLE, "--runtime-command-template", "dsh", DSH_TEMPLATE],
                "cli_executable_option_unsupported",
            ),
        )
        for argv, code in cases:
            with self.subTest(code=code, argv=argv):
                exit_code, stdout = self.run_main(argv)
                self.assertEqual(exit_code, role_service_host.EXIT_FAILED)
                payload = json.loads(stdout)
                # 没有 operator Key 也必须先报配置错误码 → 校验先于私有凭据读取。
                self.assertEqual(payload["error_code"], code)
                self.assertNotIn("no-placeholder", stdout)
                self.assertNotIn(DSH_TEMPLATE, stdout)
                self.assertNotIn("operator_key_missing", stdout)

    def test_main_wires_new_options_into_a_real_manager(self):
        port = free_port()
        argv = [
            "status",
            "--project",
            PROJECT_ID,
            "--base-url",
            f"http://127.0.0.1:{port}",
            "--operator-key-file",
            str(self.operator_key_file),
            "--state-dir",
            str(self.state_dir),
            "--project-root",
            str(self.root),
            "--runtime-command-template",
            "dsh",
            DSH_TEMPLATE,
            "--cli-execution-timeout-seconds",
            "43200",
        ]
        buffer = io.StringIO()
        with patch.object(
            role_service_host, "HostManager", wraps=role_service_host.HostManager
        ) as spy, contextlib.redirect_stdout(buffer):
            code = host_main(argv)
        stdout = buffer.getvalue()
        # 真实 HostManager 已按新参数构造；随后只是被不可达的 base-url 挡住。
        self.assertEqual(code, role_service_host.EXIT_FAILED)
        self.assertEqual(json.loads(stdout)["error_code"], "host_unreachable")
        kwargs = spy.call_args.kwargs
        self.assertEqual(kwargs["runtime_command_templates"], {"dsh": DSH_TEMPLATE})
        self.assertEqual(kwargs["execution_timeout_seconds"], 43200)
        self.assertEqual(kwargs["cli_executable"], None)
        self.assertNotIn(DSH_TEMPLATE, stdout)
        self.assertNotIn("FAKE-OPERATOR-KEY", stdout)

    def test_main_accepts_legacy_invocation_without_the_new_options(self):
        port = free_port()
        argv = [
            "status",
            "--project",
            PROJECT_ID,
            "--base-url",
            f"http://127.0.0.1:{port}",
            "--operator-key-file",
            str(self.operator_key_file),
            "--state-dir",
            str(self.state_dir),
            "--project-root",
            str(self.root),
            "--cli-command-template",
            DSH_TEMPLATE,
        ]
        buffer = io.StringIO()
        with patch.object(
            role_service_host, "HostManager", wraps=role_service_host.HostManager
        ) as spy, contextlib.redirect_stdout(buffer):
            code = host_main(argv)
        self.assertEqual(code, role_service_host.EXIT_FAILED)
        kwargs = spy.call_args.kwargs
        self.assertEqual(kwargs["runtime_command_templates"], {})
        self.assertIsNone(kwargs["execution_timeout_seconds"])
        self.assertEqual(kwargs["cli_command_template"], DSH_TEMPLATE)


# ---------------------------------------------------------------------------
# 5. 定向反例：同样的断言在旧坏路径上必然失败
# ---------------------------------------------------------------------------


class NegativeControlTests(HostConfigTestCase):
    def test_new_assertions_reject_the_old_bad_paths(self):
        # 旧路径 1：外层 argv 没有 --timeout（本片之前 build_runtime_argv 的行为）。
        old_style = [
            PYTHON_EXECUTABLE,
            "-m",
            "bridges.cli_bridge",
            "--command",
            f"dsh --model {MODEL_ALIAS}",
        ]
        with self.assertRaises(AssertionError):
            single_outer_timeout(old_style)
        # 旧路径 1b：预算被重复给出（后值覆盖），新断言同样必须失败。
        with self.assertRaises(AssertionError):
            single_outer_timeout(old_style + ["--timeout", "600", "--timeout", "21600"])

        # 旧路径 2：同一个全局模板被套给别的 runtime（跨 runtime 串用）。
        crossed = [
            PYTHON_EXECUTABLE,
            "-m",
            "bridges.cli_bridge",
            "--command",
            CODEX_TEMPLATE.replace("{model}", MODEL_ALIAS),
            "--timeout",
            "21600",
        ]
        self.assertTrue(template_present(crossed, CODEX_TEMPLATE, MODEL_ALIAS))
        with self.assertRaises(AssertionError):
            # “dsh 不串用 codex 模板”的新断言在旧路径上直接失败。
            self.assertFalse(template_present(crossed, CODEX_TEMPLATE, MODEL_ALIAS))

        # 新代码路径：同样的断言全部通过（不是恒真，也不是恒假）。
        manager = self.make_manager(runtime_command_templates={"dsh": DSH_TEMPLATE})
        argv = manager.base_argv("dsh", MODEL_ALIAS)
        self.assertEqual(single_outer_timeout(argv), 86400)
        self.assertFalse(template_present(argv, CODEX_TEMPLATE, MODEL_ALIAS))
        self.assertTrue(template_present(argv, DSH_TEMPLATE, MODEL_ALIAS))


# ---------------------------------------------------------------------------
# 6. 回归：既有守卫与来源口径保持
# ---------------------------------------------------------------------------


class ExistingGuardRegressionTests(HostConfigTestCase):
    def make_client(self, **overrides) -> ScriptedHostClient:
        client = ScriptedHostClient(**overrides)
        client.command["project_root"] = str(self.root)
        return client

    def test_registered_runtime_guard_still_applies_with_templates(self):
        client = self.make_client()
        manager = self.make_manager(
            client=client,
            runtime_command_templates={"dsh": DSH_TEMPLATE},
            verified_runtimes=[],
        )
        with self.assertRaises(HostError) as ctx:
            manager._require_runtime_registered("dsh")
        self.assertEqual(ctx.exception.code, "runtime_unverified")
        # 模板登记不等于能力验收：预检仍在组装 argv 之前稳定拒绝。
        with self.assertRaises(HostError) as ctx2:
            manager.preflight(client.command, MEMBER_ID, project_id=PROJECT_ID, action="start")
        self.assertEqual(ctx2.exception.code, "runtime_unverified")

    def test_legacy_attach_choice_source_and_binding_unchanged(self):
        client = self.make_client(choice_source="legacy_attach")
        manager = self.make_manager(
            client=client,
            runtime_command_templates={"dsh": DSH_TEMPLATE},
            execution_timeout_seconds=60,
        )
        facts = manager.preflight(
            client.command, MEMBER_ID, project_id=PROJECT_ID, action="start"
        )
        self.assertEqual(facts.runtime, "dsh")
        self.assertEqual(single_outer_timeout(facts.argv), 60)
        row = client.role_row()
        fingerprint = manager.binding_fingerprint(
            {
                "member_id": MEMBER_ID,
                "project_id": PROJECT_ID,
                "runner": row["runner"],
                "model": row["model"],
            },
            client.command,
        )
        self.assertEqual(len(fingerprint), 64)
        # 未知/不受支持的来源继续稳定拒绝。
        bad_client = self.make_client(choice_source="legacy_manual")
        bad_manager = self.make_manager(
            client=bad_client, runtime_command_templates={"dsh": DSH_TEMPLATE}
        )
        with self.assertRaises(HostError) as ctx:
            bad_manager.preflight(
                bad_client.command, MEMBER_ID, project_id=PROJECT_ID, action="start"
            )
        self.assertEqual(ctx.exception.code, "choice_unverified")

    def test_binding_mismatch_still_refused(self):
        client = self.make_client()
        client.command["model_alias"] = "another-model"
        manager = self.make_manager(
            client=client, runtime_command_templates={"dsh": DSH_TEMPLATE}
        )
        with self.assertRaises(HostError) as ctx:
            manager.preflight(client.command, MEMBER_ID, project_id=PROJECT_ID, action="start")
        self.assertEqual(ctx.exception.code, "binding_fingerprint_mismatch")

    def test_unknown_owner_stop_guard_unchanged(self):
        client = self.make_client()
        manager = self.make_manager(
            client=client, runtime_command_templates={"dsh": DSH_TEMPLATE}
        )
        result = manager.execute_stop(self.launch())
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "unknown_owner")
        self.assertEqual(client.claims, [])
        self.assertEqual(client.reports, [])
        self.assertEqual(manager._handles, {})

    def test_real_recipe_table_and_alias_flags_unchanged(self):
        self.assertEqual(
            sorted(RUNTIME_RECIPES),
            ["cli", "codex", "dsh", "kimi-code", "workbuddy"],
        )
        self.assertEqual(RUNTIME_RECIPES["kimi-code"].alias_flag, "--kimi-model")
        self.assertEqual(RUNTIME_RECIPES["kimi-code"].command_flag, None)
        self.assertEqual(RUNTIME_RECIPES["codex"].command_flag, "--codex-command")
        self.assertEqual(RUNTIME_RECIPES["dsh"].command_flag, "--command")
        self.assertEqual(resolve_alias_flag("dsh"), "--model")
        self.assertEqual(resolve_alias_flag("custom", "--my-model"), "--my-model")

    def test_build_runtime_argv_defaults_to_24_hours_without_new_parameters(self):
        # 旧调用点（只给 command_template）自动获得内置 86400 预算，且仍被真实 parser 接受。
        argv = build_runtime_argv(
            "dsh", model_alias=MODEL_ALIAS, command_template=DSH_TEMPLATE
        )
        self.assertEqual(single_outer_timeout(argv), 86400)
        self.assertTrue(verify_runtime_entry("dsh", argv).startswith("bridges.cli_bridge@"))
        with self.assertRaises(HostError) as ctx:
            build_runtime_argv("unknown-runtime", model_alias=MODEL_ALIAS)
        self.assertEqual(ctx.exception.code, "cli_missing")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
