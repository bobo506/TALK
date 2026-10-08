# -*- coding: utf-8 -*-
"""`scripts/kimi_k28_executor.py` 的针对性测试（Kimi Code + K2.8 Preview 执行入口）。

覆盖本片风险的回归：

- 合同字段分离：运行器 / `model_source=builtin` / provider 与连接引用 /
  模型 alias、后端 model ID、显示名（显示名不得当 API 模型 ID）；
- native `config.toml` 只读检查：alias 缺失、provider/model 不符、配置缺失，
  以及检查前后文件哈希不变（不改全局 `default_model`）；
- 模型锁：三档命令都带锁定 alias；`--kimi-command` 覆盖若不携带同一 alias 直接判失败；
- 工具档隔离：任务档含 `Edit/Write`，讨论与预检 `tools: []`，三档 `subagents: []`；
- 两个角色互不影响：`agent:kimi` 仍走 native 默认模型（不带 `--model`），
  新成员显式锁定 `kimi-code/kimi-for-coding`；
- 真实 argv 运输：用假 CLI 子进程核对最后一个 argv 是完整 prompt、`-p` 在其前、
  stream-json 最终 Assistant 被解析为可见回复；
- 失败脱敏：非 0 退出只给简短提示，不回显 stdout/stderr；
- 凭据安全：环境变量优先、仓库内密钥文件被拒、既有 `agent:kimi` 的 Key 被拒、
  渲染输出不含密钥正文。

全部离线：不调用真实 Kimi 模型、不访问 TALK 服务、不写生产数据。
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import kimi_k28_executor as k28  # noqa: E402
from bridges import cli_bridge, kimi_bridge  # noqa: E402

FIXTURE_CONFIG = """
default_model = "kimi-code/k3"

[providers."managed:kimi-code"]
type = "kimi"
base_url = "https://api.kimi.com/coding/v1"

[models."kimi-code/kimi-for-coding"]
provider = "managed:kimi-code"
model = "kimi-for-coding"
display_name = "K2.8 Preview"
capabilities = [ "thinking", "tool_use" ]

[models."kimi-code/k3"]
provider = "managed:kimi-code"
model = "k3"
display_name = "K3"
capabilities = [ "thinking", "tool_use" ]
"""

FAKE_KIMI_SCRIPT = '''
import json, os, sys

record = {"argv": sys.argv[1:], "prompt": sys.argv[-1]}
target = os.environ.get("FAKE_KIMI_RECORD")
if target:
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False)
print(json.dumps({"role": "tool", "content": "内部工具输出"}, ensure_ascii=False))
print(json.dumps({"role": "assistant", "content": "最终结论"}, ensure_ascii=False))
print(json.dumps({"role": "meta", "type": "session.resume_hint"}, ensure_ascii=False))
'''


class K28ExecutorTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-k28-executor-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))
        self.config_path = self._tmp / "config.toml"
        self.config_path.write_text(FIXTURE_CONFIG, encoding="utf-8")
        # 仓库外、且默认不存在的密钥文件路径：保证检查在无凭据时走 not_run。
        self.key_file = self._tmp / "outside-repo.key"

    def run_offline_check(self, **overrides):
        kwargs = {
            "project_root": PROJECT_ROOT,
            "kimi_config": self.config_path,
            "key_file": self.key_file,
            "environ": {},
        }
        kwargs.update(overrides)
        return k28.run_check(**kwargs)


class ContractTests(K28ExecutorTestCase):
    def test_contract_separates_runner_model_and_identity_fields(self):
        contract = k28.build_contract(project_root=PROJECT_ROOT, kimi_config=self.config_path, environ={})

        self.assertEqual(contract["schema_version"], k28.CONTRACT_SCHEMA)
        self.assertEqual(contract["member"]["member_id"], "agent:kimi-code-k28-preview")
        self.assertEqual(contract["member"]["business_role"], "dev")
        self.assertEqual(contract["member"]["decision_tier"], "execution")
        self.assertEqual(contract["member"]["project_id"], "prj_e8fe7066bbec")

        runner = contract["runner"]
        self.assertEqual(runner["entry"], "bridges/kimi_bridge.py")
        self.assertEqual(runner["runtime"], "kimi-code")
        self.assertEqual(runner["model_source"], "builtin")
        self.assertEqual(runner["prompt_transport"], "argv")
        self.assertEqual(runner["task_tool_profile"], "tools")
        self.assertEqual(runner["discussion_tool_profile"], "none")
        self.assertEqual(runner["preflight_tool_profile"], "none")
        self.assertFalse(runner["command_override_allowed"])
        self.assertEqual(runner["controlled_command"], k28.CONTROLLED_KIMI_COMMAND)
        self.assertEqual(runner["controlled_command_source"], "explicit_fixed_contract")
        self.assertTrue(runner["env_command_ignored"])
        self.assertEqual(runner["env_command_var"], "TALK_KIMI_COMMAND")
        self.assertEqual(runner["decision_tier_argv"], "execution")
        self.assertEqual(runner["base_url_default"], k28.DEFAULT_BASE_URL)

        model = contract["model"]
        self.assertEqual(model["provider_id"], "managed:kimi-code")
        self.assertEqual(model["connection_ref"], "native-kimi-code-managed-login")
        self.assertEqual(model["model_config_key"], "kimi-code/kimi-for-coding")
        self.assertEqual(model["model_id"], "kimi-for-coding")
        self.assertEqual(model["model_version_label"], "K2.8 Preview")
        self.assertNotEqual(model["model_config_key"], model["model_id"])
        self.assertNotEqual(model["model_version_label"], model["model_id"])
        self.assertFalse(model["version_pinned"])
        self.assertEqual(model["default_model_untouched"], "kimi-code/k3")

        self.assertFalse(contract["talk_identity"]["reuse_agent_kimi_key"])
        self.assertIn("TALK_K28_KEY", contract["talk_identity"]["key_env"])

    def test_budget_records_template_value_as_unverified(self):
        budget = k28.budget_contract()

        self.assertEqual(budget["client_tool_timeout_ms"]["value"], 660000)
        self.assertFalse(budget["client_tool_timeout_ms"]["loaded_on_host"])
        self.assertFalse(budget["client_tool_timeout_ms"]["verified_on_host"])
        self.assertFalse(budget["explicit_wait_seconds"]["enabled"])
        self.assertIsNone(budget["explicit_wait_seconds"]["value"])
        self.assertEqual(budget["bridge_execution_timeout_seconds"]["value"], 3600)
        self.assertEqual(budget["identity_preflight_http_timeout_seconds"]["value"], 15.0)
        self.assertFalse(budget["initiator_wait_in_this_slice"])

    def test_render_is_keyless_and_pins_the_model_alias(self):
        rendered = k28.render_launch(project_root=PROJECT_ROOT, environ={})
        text = json.dumps(rendered, ensure_ascii=False, indent=2)

        self.assertFalse(rendered["contains_secret"])
        self.assertIn(k28.KEY_PLACEHOLDER, rendered["command_template"])
        self.assertEqual(rendered["model_alias"], "kimi-code/kimi-for-coding")
        self.assertNotIn("TALK_API_KEY", text)
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{8,}", text))
        for marker in ("Bearer ", "ghp_"):
            self.assertNotIn(marker, text)
        argv = rendered["bridge_argv"]
        self.assertEqual(argv[argv.index("--name") + 1], k28.MEMBER_ID)
        self.assertEqual(argv[argv.index("--kimi-model") + 1], k28.MODEL_ALIAS)
        self.assertEqual(argv[argv.index("--kimi-task-profile") + 1], "tools")


class NativeConfigCheckTests(K28ExecutorTestCase):
    def test_check_passes_against_matching_native_config(self):
        report = self.run_offline_check()

        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(report["native_config"]["default_model"], "kimi-code/k3")
        binding = report["native_config"]["binding"]
        self.assertEqual(binding["model_id"], "kimi-for-coding")
        self.assertEqual(binding["display_name"], "K2.8 Preview")
        self.assertTrue(binding["tool_use"])
        self.assertIn("talk_identity_key", report["not_run"])
        self.assertEqual(report["network_calls"], 0)

    def test_check_reports_missing_alias(self):
        self.config_path.write_text(
            """
default_model = "kimi-code/k3"

[models."kimi-code/k3"]
provider = "managed:kimi-code"
model = "k3"
capabilities = [ "tool_use" ]
""",
            encoding="utf-8",
        )
        report = self.run_offline_check()

        self.assertFalse(report["ok"])
        self.assertTrue(any("缺少模型 alias" in item for item in report["problems"]), report["problems"])
        names = {check["name"]: check for check in report["checks"]}
        self.assertFalse(names["native_model_alias"]["ok"])

    def test_check_reports_provider_or_model_mismatch(self):
        self.config_path.write_text(
            """
default_model = "kimi-code/k3"

[models."kimi-code/kimi-for-coding"]
provider = "managed:other"
model = "not-kimi-for-coding"
display_name = "K2.8 Preview"
capabilities = [ "thinking" ]
""",
            encoding="utf-8",
        )
        report = self.run_offline_check()

        self.assertFalse(report["ok"])
        joined = " ".join(report["problems"])
        self.assertIn("provider", joined)
        self.assertIn("model", joined)
        self.assertIn("tool_use", joined)

    def test_check_reports_missing_config_file(self):
        report = self.run_offline_check(kimi_config=self._tmp / "does-not-exist.toml")

        self.assertFalse(report["ok"])
        self.assertTrue(any("未找到 Kimi Code 配置文件" in item for item in report["problems"]))
        self.assertFalse(report["native_config"]["exists"])

    def test_check_never_writes_native_config(self):
        before = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
        report = self.run_offline_check()
        after = hashlib.sha256(self.config_path.read_bytes()).hexdigest()

        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(before, after)
        names = {check["name"]: check for check in report["checks"]}
        self.assertTrue(names["default_model_untouched"]["ok"])


class MalformedConfigTests(K28ExecutorTestCase):
    """R2：malformed native 配置类型给可预期短错误，不崩 traceback。"""

    CASES = (
        ("models = 3", "models 不是表结构"),
        (
            '[models]\n"kimi-code/kimi-for-coding" = "oops"',
            "不是表结构",
        ),
        (
            '[models."kimi-code/kimi-for-coding"]\n'
            'provider = "managed:kimi-code"\n'
            'model = "kimi-for-coding"\n'
            'capabilities = "tool_use"',
            "不是字符串数组",
        ),
        (
            '[models."kimi-code/kimi-for-coding"]\n'
            "provider = 3\n"
            'model = "kimi-for-coding"\n'
            'capabilities = [ "tool_use" ]',
            "provider 不是字符串",
        ),
    )

    def test_native_model_binding_raises_expected_short_errors(self):
        for config in ({"models": []}, {"models": {k28.MODEL_ALIAS: []}},
                       {"models": {k28.MODEL_ALIAS: {"capabilities": "tool_use"}}}):
            with self.subTest(config=config):
                with self.assertRaises(k28.K28ExecutorError):
                    k28.native_model_binding(config)

    def test_check_reports_malformed_types_instead_of_crashing(self):
        for body, needle in self.CASES:
            with self.subTest(body=body):
                self.config_path.write_text(
                    'default_model = "kimi-code/k3"\n' + body + "\n", encoding="utf-8"
                )
                report = self.run_offline_check()

                self.assertFalse(report["ok"], body)
                self.assertTrue(any(needle in item for item in report["problems"]), report["problems"])
                self.assertFalse(any("Traceback" in item for item in report["problems"]))

    def test_check_cli_returns_short_error_without_traceback(self):
        self.config_path.write_text('default_model = "kimi-code/k3"\nmodels = 3\n', encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = k28.main(
                [
                    "check",
                    "--project-root", str(PROJECT_ROOT),
                    "--kimi-config", str(self.config_path),
                    "--key-file", str(self.key_file),
                ]
            )

        self.assertEqual(code, 1)
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn("Traceback", combined)
        self.assertIn("models 不是表结构", combined)


class KeyEnvContractTests(K28ExecutorTestCase):
    """R2：`--key-env` 不再只影响 require 却被 resolve 静默忽略。"""

    def test_unknown_key_env_is_rejected(self):
        report = self.run_offline_check(
            key_env="TALK_OTHER_KEY", environ={"TALK_OTHER_KEY": "env-key"}
        )

        self.assertFalse(report["ok"])
        self.assertTrue(
            any("只支持合同环境变量" in item for item in report["problems"]), report["problems"]
        )
        names = {check["name"]: check for check in report["checks"]}
        self.assertFalse(names["key_env_contract"]["ok"])

    def test_resolve_reads_the_named_contract_environment_variable(self):
        key, source = k28.resolve_api_key(
            environ={k28.KEY_ENV: "named-env-key"}, key_file=self.key_file
        )

        self.assertEqual(key, "named-env-key")
        self.assertEqual(source, f"环境变量 {k28.KEY_ENV}")


class ModelLockTests(K28ExecutorTestCase):
    def test_check_pins_model_in_all_three_runtime_profiles(self):
        report = self.run_offline_check()
        names = {check["name"]: check for check in report["checks"]}

        self.assertTrue(names["command_override"]["ok"])
        self.assertTrue(names["controlled_command_contract"]["ok"])
        self.assertTrue(names["model_lock_and_tool_isolation"]["ok"])
        self.assertIn("--model", names["model_lock_and_tool_isolation"]["detail"])

    def test_check_rejects_any_custom_command_even_with_same_alias(self):
        for override in (
            "kimi-wrapper --json",
            f"kimi-wrapper --json --model {k28.MODEL_ALIAS}",
            "kimi --output-format stream-json -p --model kimi-code/k3",
        ):
            with self.subTest(override=override):
                report = self.run_offline_check(kimi_command=override)

                self.assertFalse(report["ok"], override)
                joined = " ".join(report["problems"])
                self.assertIn("command_override_allowed=false", joined)
                names = {check["name"]: check for check in report["checks"]}
                self.assertFalse(names["command_override"]["ok"])
                self.assertIn("materialize_commands", report["not_run"])

    def test_check_accepts_explicit_contract_command(self):
        report = self.run_offline_check(kimi_command=k28.CONTROLLED_KIMI_COMMAND)

        self.assertTrue(report["ok"], report["problems"])
        names = {check["name"]: check for check in report["checks"]}
        self.assertTrue(names["command_override"]["ok"])
        self.assertTrue(names["model_lock_and_tool_isolation"]["ok"])

    def test_check_rejects_wrong_member_runtime_profile_or_transport(self):
        for kwargs, needle in (
            ({"name": "agent:kimi"}, "成员身份"),
            ({"runtime": "pi"}, "runtime 必须是"),
            ({"task_profile": "review"}, "任务工具档"),
            ({"prompt_transport": "stdin"}, "prompt 传递"),
            ({"model": "kimi-code/k3"}, "模型 alias"),
            ({"timeout": 0}, "执行预算"),
        ):
            with self.subTest(kwargs=kwargs):
                report = self.run_offline_check(**kwargs)
                self.assertFalse(report["ok"], kwargs)
                self.assertTrue(
                    any(needle in item for item in report["problems"])
                    or any(needle in item for item in report["not_run"]),
                    (kwargs, report["problems"], report["not_run"]),
                )


class ControlledCommandTests(K28ExecutorTestCase):
    """R1：启动/检查使用同一固定受控命令，环境继承与显式覆盖都不能绕过。"""

    K3_ENV_COMMAND = "kimi --model kimi-code/k3 --output-format stream-json -p"

    def test_build_bridge_argv_always_carries_the_contract_command(self):
        argv = k28.build_bridge_argv()
        self.assertIn("--kimi-command", argv)
        self.assertEqual(argv[argv.index("--kimi-command") + 1], k28.CONTROLLED_KIMI_COMMAND)
        self.assertEqual(argv[argv.index("--decision-tier") + 1], k28.DECISION_TIER)
        self.assertEqual(argv[argv.index("--base-url") + 1], k28.DEFAULT_BASE_URL)
        self.assertEqual(k28.bridge_default_command(), k28.CONTROLLED_KIMI_COMMAND)

    def test_inherited_env_command_cannot_change_the_three_tiers(self):
        with patch.dict(os.environ, {k28.ENV_COMMAND_VAR: self.K3_ENV_COMMAND}, clear=False):
            report = self.run_offline_check()
            self.assertTrue(report["ok"], report["problems"])

            args = kimi_bridge.build_parser().parse_args(k28.build_bridge_argv())
            commands = kimi_bridge.materialize_kimi_commands(args, self._tmp / "env-locked")

        self.assertEqual(args.kimi_command, k28.CONTROLLED_KIMI_COMMAND)
        parsed = [shlex.split(command, posix=True) for command in commands]
        for item in parsed:
            self.assertIn("--agent-file", item)
            self.assertEqual(item[item.index("--model") + 1], k28.MODEL_ALIAS)
            self.assertNotIn("kimi-code/k3", item)
        files = {
            label: Path(item[item.index("--agent-file") + 1]).read_text(encoding="utf-8")
            for label, item in zip(("discussion", "task", "preflight"), parsed)
        }
        self.assertIn("tools: []", files["discussion"])
        self.assertIn("tools: []", files["preflight"])
        self.assertIn("  - Edit", files["task"])
        self.assertIn("  - Write", files["task"])

    def test_inherited_env_command_cannot_reach_the_launch_bridge(self):
        captured = {}

        async def fake_run_bridge(args):
            captured["args"] = args

        with patch.dict(os.environ, {k28.ENV_COMMAND_VAR: self.K3_ENV_COMMAND}, clear=False):
            with patch.object(k28, "identity_preflight", return_value=self._ok_identity()):
                with patch.object(kimi_bridge, "run_bridge", side_effect=fake_run_bridge):
                    code = k28.run_launch(
                        project_root=PROJECT_ROOT,
                        key_file=self._write_key(),
                        environ={"KIMI_CODE_HOME": str(self._tmp)},
                    )

        self.assertEqual(code, 0)
        self.assertEqual(captured["args"].kimi_command, k28.CONTROLLED_KIMI_COMMAND)
        self.assertEqual(captured["args"].kimi_model, k28.MODEL_ALIAS)
        self.assertEqual(captured["args"].kimi_task_profile, "tools")

    # --- helpers -----------------------------------------------------------
    def _write_key(self) -> Path:
        self.key_file.write_text("unit-test-key\n", encoding="utf-8")
        return self.key_file

    @staticmethod
    def _ok_identity() -> dict:
        return {
            "ok": True,
            "mode": "identity-preflight",
            "member_id": k28.MEMBER_ID,
            "kind": "agent",
            "business_role": k28.BUSINESS_ROLE,
            "decision_tier": k28.DECISION_TIER,
            "problems": [],
            "network_calls": 2,
        }


class RoleIndependenceTests(K28ExecutorTestCase):
    @staticmethod
    def _agent_file(command: str) -> Path:
        parts = shlex.split(command, posix=True)
        return Path(parts[parts.index("--agent-file") + 1])

    def test_existing_kimi_role_keeps_native_default_model(self):
        args = kimi_bridge.build_parser().parse_args(["--key", "kimi-key"])
        commands = kimi_bridge.materialize_kimi_commands(args, self._tmp / "existing")

        for command in commands:
            self.assertNotIn("--model", shlex.split(command, posix=True))
        self.assertNotIn("  - Edit", self._agent_file(commands[1]).read_text(encoding="utf-8"))

    def test_new_role_locks_alias_and_tools_without_affecting_existing_role(self):
        args = kimi_bridge.build_parser().parse_args(k28.build_bridge_argv())
        commands = kimi_bridge.materialize_kimi_commands(args, self._tmp / "new")

        for command in commands:
            parts = shlex.split(command, posix=True)
            self.assertEqual(parts[parts.index("--model") + 1], k28.MODEL_ALIAS)
            self.assertEqual(parts[parts.index("--output-format") + 1], "stream-json")
            self.assertEqual(parts[-1], "-p")
        self.assertIn("tools: []", self._agent_file(commands[0]).read_text(encoding="utf-8"))
        self.assertIn("tools: []", self._agent_file(commands[2]).read_text(encoding="utf-8"))
        task_text = self._agent_file(commands[1]).read_text(encoding="utf-8")
        self.assertIn("  - Edit", task_text)
        self.assertIn("  - Write", task_text)
        for command in commands:
            self.assertIn("subagents: []", self._agent_file(command).read_text(encoding="utf-8"))

        # 新角色生成之后，原 Kimi 角色仍然不带 --model（无共享可变状态）。
        again = kimi_bridge.materialize_kimi_commands(
            kimi_bridge.build_parser().parse_args(["--key", "kimi-key"]),
            self._tmp / "existing-again",
        )
        for command in again:
            self.assertNotIn("--model", shlex.split(command, posix=True))


class ArgvTransportTests(K28ExecutorTestCase):
    """真实子进程验证生成命令的 argv 运输与最终交付解析。

    本仓库沙箱禁止命名管道（`WinError 5`），`cli_bridge.run_cli_command` 的
    asyncio PIPE 路径在本环境不可用；因此主路径用**文件型 stdio** 跑同一个生成命令，
    并复用 bridge 自己的 `parse_command` / `resolve_command_executable` /
    `normalize_runtime_result`；PIPE 路径单独保留并在受限环境如实 skip。
    """

    def _materialized_commands(self):
        with tempfile.TemporaryDirectory(prefix="k28-check-") as runtime_dir:
            _module, commands = k28._materialize_reference_commands(
                k28.build_bridge_argv(), Path(runtime_dir)
            )
        return commands

    @staticmethod
    def _run_file_stdio(command: str, prompt: str, *, cwd: Path, timeout: float = 60.0):
        args = cli_bridge.resolve_command_executable(cli_bridge.parse_command(command))
        args = [*args, prompt]  # 与 run_cli_command 的 argv 运输规则一致
        with tempfile.TemporaryDirectory(prefix="k28-stdio-") as workdir:
            out_path = Path(workdir) / "stdout.txt"
            err_path = Path(workdir) / "stderr.txt"
            with out_path.open("w", encoding="utf-8") as out_handle, err_path.open(
                "w", encoding="utf-8"
            ) as err_handle:
                completed = subprocess.run(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=out_handle,
                    stderr=err_handle,
                    cwd=str(cwd),
                    timeout=timeout,
                )
            return cli_bridge.CliRunResult(
                completed.returncode,
                cli_bridge.decode_subprocess_output(out_path.read_bytes()),
                cli_bridge.decode_subprocess_output(err_path.read_bytes()),
            )

    def test_generated_task_command_delivers_intact_prompt_and_final_assistant(self):
        script = self._tmp / "fake_kimi.py"
        script.write_text(FAKE_KIMI_SCRIPT, encoding="utf-8")
        record = self._tmp / "record.json"
        task_command = self._materialized_commands()[1]

        parts = shlex.split(task_command, posix=True)
        self.assertEqual(parts[0], "kimi")
        command = " ".join(shlex.quote(item) for item in [sys.executable, str(script), *parts[1:]])
        prompt = "第一行\n第二行\n第三行"

        with patch.dict(os.environ, {"FAKE_KIMI_RECORD": str(record)}, clear=False):
            result = self._run_file_stdio(command, prompt, cwd=self._tmp)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(payload["prompt"], prompt)
        self.assertEqual(payload["argv"][-1], prompt)
        self.assertEqual(payload["argv"][-2], "-p")
        self.assertEqual(payload["argv"][payload["argv"].index("--model") + 1], k28.MODEL_ALIAS)
        self.assertEqual(
            payload["argv"][payload["argv"].index("--output-format") + 1], "stream-json"
        )

        visible = cli_bridge.normalize_runtime_result(result, runtime="kimi-code")
        self.assertEqual(visible.stdout.strip(), "最终结论")
        self.assertNotIn("内部工具输出", visible.stdout)

    def test_run_cli_command_pipe_path_when_host_allows_pipes(self):
        script = self._tmp / "fake_kimi.py"
        script.write_text(FAKE_KIMI_SCRIPT, encoding="utf-8")
        record = self._tmp / "record-pipe.json"
        task_command = self._materialized_commands()[1]
        parts = shlex.split(task_command, posix=True)
        command = " ".join(shlex.quote(item) for item in [sys.executable, str(script), *parts[1:]])
        prompt = "管道路径 probe"

        with patch.dict(os.environ, {"FAKE_KIMI_RECORD": str(record)}, clear=False):
            try:
                result = asyncio.run(
                    cli_bridge.run_cli_command(
                        command, prompt, cwd=self._tmp, timeout=60, prompt_transport="argv"
                    )
                )
            except PermissionError as exc:  # 沙箱禁止命名管道（WinError 5）
                self.skipTest(f"当前宿主禁止命名管道，无法运行 PIPE 路径：{exc}")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(payload["prompt"], prompt)
        self.assertEqual(payload["argv"][-1], prompt)

    def test_failed_cli_reply_is_short_and_hides_process_output(self):
        code = (
            'import sys; sys.stderr.write("sk-abcdefghijklmnop details\\n"); '
            'sys.stdout.write("internal-stdout\\n"); sys.exit(3)'
        )
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

        result = self._run_file_stdio(command, "", cwd=self._tmp)
        reply = cli_bridge.format_cli_reply(result, bridge_label="Kimi Code bridge")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("运行失败", reply)
        self.assertNotIn("sk-", reply)
        self.assertNotIn("internal-stdout", reply)
        self.assertNotIn("details", reply)


class CredentialSafetyTests(K28ExecutorTestCase):
    def test_environment_key_wins_and_is_never_echoed_in_source_text(self):
        key, source = k28.resolve_api_key(environ={k28.KEY_ENV: "env-key"}, key_file=self.key_file)

        self.assertEqual(key, "env-key")
        self.assertEqual(source, f"环境变量 {k28.KEY_ENV}")
        self.assertNotIn("env-key", source)

    def test_key_file_outside_repo_is_used(self):
        self.key_file.write_text("\n  \nfile-key\nsecond-line\n", encoding="utf-8")

        key, source = k28.resolve_api_key(environ={}, key_file=self.key_file)

        self.assertEqual(key, "file-key")
        self.assertIn(str(self.key_file.resolve()), source)
        self.assertNotIn("file-key", source)

    def test_in_repo_and_agent_kimi_key_files_are_rejected(self):
        fake_repo = self._tmp / "fake-repo"
        fake_repo.mkdir()
        inside = fake_repo / "leaked.key"
        inside.write_text("in-repo-key\n", encoding="utf-8")
        with self.assertRaises(k28.K28ExecutorError) as ctx:
            k28.resolve_api_key(environ={}, key_file=inside, repo_root=fake_repo)
        self.assertIn("仓库内", str(ctx.exception))
        self.assertNotIn("in-repo-key", str(ctx.exception))

        fake_home = self._tmp / "home"
        (fake_home / ".talk").mkdir(parents=True)
        existing = fake_home / ".talk" / "agent-kimi.key"
        existing.write_text("agent-kimi-key\n", encoding="utf-8")
        with self.assertRaises(k28.K28ExecutorError) as ctx:
            k28.resolve_api_key(
                environ={"USERPROFILE": str(fake_home)},
                key_file=existing,
            )
        self.assertIn("拒绝复用", str(ctx.exception))
        self.assertNotIn("agent-kimi-key", str(ctx.exception))

    def test_check_requires_key_only_when_asked(self):
        without = self.run_offline_check()
        self.assertTrue(without["ok"], without["problems"])
        self.assertIn("talk_identity_key", without["not_run"])

        with_requirement = self.run_offline_check(require_key=True)
        self.assertFalse(with_requirement["ok"])
        self.assertTrue(any("未找到密钥文件" in item for item in with_requirement["problems"]))

    def test_identity_mismatch_is_reported_without_leaking_credentials(self):
        report = self.run_offline_check(
            identity_report={"ok": True, "member_id": "human:bobo", "project_id": k28.PROJECT_ID}
        )

        self.assertFalse(report["ok"])
        joined = " ".join(report["problems"])
        self.assertIn("human:bobo", joined)
        self.assertIn(k28.MEMBER_ID, joined)

    def test_matching_identity_report_passes(self):
        report = self.run_offline_check(
            identity_report={"ok": True, "member_id": k28.MEMBER_ID, "project_id": k28.PROJECT_ID}
        )

        self.assertTrue(report["ok"], report["problems"])
        names = {check["name"]: check for check in report["checks"]}
        self.assertTrue(names["identity_binding"]["ok"])


class CliEntryTests(K28ExecutorTestCase):
    def test_contract_and_render_subcommands_print_keyless_json(self):
        for argv in (["contract"], ["render"]):
            with self.subTest(argv=argv):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = k28.main(argv)
                self.assertEqual(code, 0, stderr.getvalue())
                payload = json.loads(stdout.getvalue())
                self.assertNotIn("TALK_API_KEY", stdout.getvalue())

    def test_check_subcommand_exit_codes(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = k28.main(
                [
                    "check",
                    "--project-root", str(PROJECT_ROOT),
                    "--kimi-config", str(self.config_path),
                    "--key-file", str(self.key_file),
                ]
            )
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertTrue(json.loads(stdout.getvalue())["ok"])

        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = k28.main(
                [
                    "check",
                    "--project-root", str(PROJECT_ROOT),
                    "--kimi-config", str(self._tmp / "missing.toml"),
                    "--key-file", str(self.key_file),
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("未找到 Kimi Code 配置文件", stdout.getvalue())

    def test_launch_failure_is_a_short_chinese_error_without_traceback(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = k28.main(["launch", "--key-file", str(self.key_file), "--dry-run"])

        self.assertEqual(code, 1)
        message = stderr.getvalue()
        self.assertIn("Kimi K2.8 执行入口失败", message)
        self.assertIn("未找到密钥文件", message)
        self.assertNotIn("Traceback", message)
        self.assertNotIn(str(self.key_file), stdout.getvalue())

    def test_launch_dry_run_never_prints_the_key(self):
        self.key_file.write_text("file-key\n", encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = k28.run_launch(
                project_root=PROJECT_ROOT,
                key_file=self.key_file,
                environ={"KIMI_CODE_HOME": str(self._tmp)},
                dry_run=True,
            )
        self.assertEqual(code, 0)
        self.assertNotIn("file-key", stdout.getvalue())
        self.assertNotIn("file-key", stderr.getvalue())
        self.assertIn("[REDACTED]", stdout.getvalue())
        self.assertIn(k28.MODEL_ALIAS, stderr.getvalue())


class LaunchGateTests(K28ExecutorTestCase):
    """R2/R3：真实 launch 在任何 bridge/模型调用前完成配置与身份门禁。"""

    def setUp(self):
        super().setUp()
        self.key_file.write_text("unit-launch-key\n", encoding="utf-8")
        self.env = {"KIMI_CODE_HOME": str(self._tmp)}

    @staticmethod
    def _identity(ok: bool = True, problems: list[str] | None = None) -> dict:
        return {
            "ok": ok,
            "mode": "identity-preflight",
            "member_id": k28.MEMBER_ID if ok else None,
            "kind": "agent" if ok else None,
            "business_role": k28.BUSINESS_ROLE if ok else None,
            "decision_tier": k28.DECISION_TIER if ok else None,
            "problems": problems or [],
            "network_calls": 2 if ok else 1,
        }

    def test_wrong_project_yaml_blocks_before_bridge(self):
        wrong = self._tmp / "wrong-project"
        (wrong / ".talk").mkdir(parents=True)
        (wrong / ".talk" / "project.yaml").write_text(
            "version: 1\nproject_id: prj_not_this_project\n", encoding="utf-8"
        )

        with patch.object(kimi_bridge, "run_bridge", new=AsyncMock()) as bridge:
            with self.assertRaises(k28.K28ExecutorError) as ctx:
                k28.run_launch(project_root=wrong, key_file=self.key_file, environ=self.env)

        bridge.assert_not_called()
        self.assertIn("项目绑定", str(ctx.exception))
        self.assertNotIn("unit-launch-key", str(ctx.exception))

    def test_missing_alias_or_malformed_config_blocks_before_bridge(self):
        self.config_path.write_text(
            'default_model = "kimi-code/k3"\n\n'
            '[models."kimi-code/k3"]\nprovider = "managed:kimi-code"\nmodel = "k3"\n'
            'capabilities = [ "tool_use" ]\n',
            encoding="utf-8",
        )

        with patch.object(kimi_bridge, "run_bridge", new=AsyncMock()) as bridge:
            with self.assertRaises(k28.K28ExecutorError) as ctx:
                k28.run_launch(project_root=PROJECT_ROOT, key_file=self.key_file, environ=self.env)

        bridge.assert_not_called()
        self.assertIn("缺少模型 alias", str(ctx.exception))

    def test_identity_failure_blocks_before_bridge_and_hides_key(self):
        failure = self._identity(
            ok=False,
            problems=["身份核验失败：该 Key 对应 agent:someone-else，不是本入口成员"],
        )

        with patch.object(k28, "identity_preflight", return_value=failure) as pre:
            with patch.object(kimi_bridge, "run_bridge", new=AsyncMock()) as bridge:
                with self.assertRaises(k28.K28ExecutorError) as ctx:
                    k28.run_launch(project_root=PROJECT_ROOT, key_file=self.key_file, environ=self.env)

        bridge.assert_not_called()
        pre.assert_called_once()
        self.assertIn("身份核验未通过", str(ctx.exception))
        self.assertNotIn("unit-launch-key", str(ctx.exception))

    def test_matching_identity_allows_bridge_start(self):
        captured = {}

        async def fake_run_bridge(args):
            captured["args"] = args

        with patch.object(k28, "identity_preflight", return_value=self._identity()) as pre:
            with patch.object(kimi_bridge, "run_bridge", side_effect=fake_run_bridge):
                code = k28.run_launch(
                    project_root=PROJECT_ROOT, key_file=self.key_file, environ=self.env
                )

        self.assertEqual(code, 0)
        args = captured["args"]
        self.assertEqual(args.name, k28.MEMBER_ID)
        self.assertEqual(args.key, "unit-launch-key")
        self.assertEqual(args.kimi_command, k28.CONTROLLED_KIMI_COMMAND)
        self.assertEqual(args.kimi_model, k28.MODEL_ALIAS)
        self.assertEqual(pre.call_args.kwargs["api_key"], "unit-launch-key")

    def test_dry_run_stays_offline_and_reports_unverified_identity(self):
        with patch.object(k28, "identity_preflight", new=AsyncMock()) as pre:
            with patch.object(kimi_bridge, "run_bridge", new=AsyncMock()) as bridge:
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = k28.run_launch(
                        project_root=PROJECT_ROOT,
                        key_file=self.key_file,
                        environ=self.env,
                        dry_run=True,
                    )

        self.assertEqual(code, 0)
        pre.assert_not_called()
        bridge.assert_not_called()
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["identity_verified"])
        self.assertFalse(payload["online_identity_checked"])
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn("unit-launch-key", combined)
        self.assertIn(k28.CONTROLLED_KIMI_COMMAND, payload["argv"])


class LaunchConsistencyTests(K28ExecutorTestCase):
    """B1/B2：服务地址与固定执行分级必须贯通“检查对象 == 执行对象”。"""

    BASE_URL = "http://127.0.0.1:19091"

    def setUp(self):
        super().setUp()
        self.key_file.write_text("plain-launch-token-4c1f\n", encoding="utf-8")
        self.env = {"KIMI_CODE_HOME": str(self._tmp)}

    @staticmethod
    def _ok_identity() -> dict:
        return {
            "ok": True,
            "mode": "identity-preflight",
            "member_id": k28.MEMBER_ID,
            "kind": "agent",
            "business_role": k28.BUSINESS_ROLE,
            "decision_tier": k28.DECISION_TIER,
            "problems": [],
            "network_calls": 2,
        }

    def _project_with_local_tier(self, tier: str | None) -> Path:
        root = self._tmp / f"local-tier-{tier or 'missing'}"
        (root / ".talk").mkdir(parents=True)
        (root / ".talk" / "project.yaml").write_text(
            f"version: 1\nproject_id: {k28.PROJECT_ID}\n", encoding="utf-8"
        )
        if tier is not None:
            (root / ".talk" / "groups.yaml").write_text(
                "groups:\n"
                "  - id: grp_local\n"
                "    members:\n"
                f"      - member_id: {k28.MEMBER_ID}\n"
                f"        decision_tier: {tier}\n"
                "        business_role: dev\n",
                encoding="utf-8",
            )
        return root

    def test_non_default_base_url_reaches_preflight_and_bridge_argv(self):
        seen_urls: list[str] = []

        def fake_get(url, *, api_key, timeout):
            seen_urls.append(url)
            if url.endswith("/api/members/me"):
                return {"id": k28.MEMBER_ID, "kind": "agent"}
            return [
                {
                    "member_id": k28.MEMBER_ID,
                    "business_role": k28.BUSINESS_ROLE,
                    "decision_tier": k28.DECISION_TIER,
                }
            ]

        captured = {}

        async def fake_run_bridge(args):
            captured["args"] = args

        with patch.object(k28, "_http_get_json", side_effect=fake_get):
            with patch.object(kimi_bridge, "run_bridge", side_effect=fake_run_bridge):
                code = k28.run_launch(
                    project_root=PROJECT_ROOT,
                    key_file=self.key_file,
                    environ=self.env,
                    base_url=self.BASE_URL,
                )

        self.assertEqual(code, 0)
        self.assertTrue(seen_urls, "只读预检必须真的发请求")
        self.assertTrue(all(url.startswith(self.BASE_URL) for url in seen_urls), seen_urls)
        self.assertEqual(captured["args"].base_url, self.BASE_URL)
        argv = k28.build_bridge_argv(base_url=self.BASE_URL)
        self.assertEqual(argv[argv.index("--base-url") + 1], self.BASE_URL)

    def test_render_passes_through_non_default_base_url(self):
        rendered = k28.render_launch(base_url=self.BASE_URL, environ={})

        self.assertEqual(rendered["base_url"], self.BASE_URL)
        argv = rendered["bridge_argv"]
        self.assertEqual(argv[argv.index("--base-url") + 1], self.BASE_URL)

    def test_check_rejects_argv_that_does_not_pin_execution(self):
        report = self.run_offline_check(decision_tier="decision")

        self.assertFalse(report["ok"])
        names = {check["name"]: check for check in report["checks"]}
        self.assertFalse(names["decision_tier_binding"]["ok"])
        self.assertTrue(any("执行分级" in item for item in report["problems"]), report["problems"])

    def test_check_rejects_empty_base_url(self):
        report = self.run_offline_check(base_url="")

        self.assertFalse(report["ok"])
        names = {check["name"]: check for check in report["checks"]}
        self.assertFalse(names["base_url_contract"]["ok"])

    def test_argv_pins_execution_over_local_decision_groups_yaml(self):
        for tier in ("decision", None):
            with self.subTest(local_tier=tier):
                root = self._project_with_local_tier(tier)
                argv = k28.build_bridge_argv(project_root=root)

                self.assertEqual(argv[argv.index("--decision-tier") + 1], "execution")
                parsed = kimi_bridge.build_parser().parse_args(argv)
                self.assertEqual(
                    cli_bridge.resolve_decision_tier(parsed, k28.MEMBER_ID), "execution"
                )

    def test_launch_runs_as_execution_despite_local_decision_tier(self):
        root = self._project_with_local_tier("decision")
        captured = {}

        async def fake_run_bridge(args):
            captured["args"] = args

        with patch.object(k28, "identity_preflight", return_value=self._ok_identity()):
            with patch.object(kimi_bridge, "run_bridge", side_effect=fake_run_bridge):
                code = k28.run_launch(
                    project_root=root,
                    key_file=self.key_file,
                    environ=self.env,
                )

        self.assertEqual(code, 0)
        args = captured["args"]
        self.assertEqual(args.decision_tier, "execution")
        # 既有 bridge 真正使用的解析函数面对本地 decision 也必须给出 execution
        self.assertEqual(cli_bridge.resolve_decision_tier(args, k28.MEMBER_ID), "execution")


class IdentityPreflightTests(K28ExecutorTestCase):
    """R3：只读服务端身份核验的失败边界（mock HTTP，零真实 TALK 写操作）。"""

    ROSTER = [
        {
            "member_id": "agent:someone-else",
            "business_role": "dev",
            "decision_tier": "execution",
        },
        {
            "member_id": k28.MEMBER_ID,
            "business_role": k28.BUSINESS_ROLE,
            "decision_tier": k28.DECISION_TIER,
        },
    ]

    def _getter(self, responses: dict):
        calls: list[tuple[str, str]] = []

        def get_json(url: str, *, api_key: str, timeout: float):
            calls.append((url, api_key))
            key = "me" if url.endswith("/api/members/me") else "roster"
            value = responses.get(key)
            if isinstance(value, Exception):
                raise value
            return value

        return get_json, calls

    def _run(
        self, responses: dict, *, api_key: str = "unit-key"
    ) -> tuple[dict, list[tuple[str, str]]]:
        get_json, calls = self._getter(responses)
        report = k28.identity_preflight(
            base_url="http://127.0.0.1:9", api_key=api_key, get_json=get_json
        )
        return report, calls

    def test_matching_identity_and_roster_passes_and_reads_only(self):
        report, calls = self._run(
            {"me": {"id": k28.MEMBER_ID, "kind": "agent"}, "roster": self.ROSTER}
        )

        self.assertTrue(report["ok"], report["problems"])
        self.assertTrue(report["roster_found"])
        self.assertEqual(report["business_role"], k28.BUSINESS_ROLE)
        self.assertEqual(report["decision_tier"], k28.DECISION_TIER)
        self.assertEqual(report["network_calls"], 2)
        self.assertTrue(report["read_only"])
        self.assertEqual(
            [url for url, _key in calls],
            [
                "http://127.0.0.1:9/api/members/me",
                f"http://127.0.0.1:9/api/projects/{k28.PROJECT_ID}/agents",
            ],
        )
        self.assertTrue(all(key == "unit-key" for _url, key in calls))

    def test_other_member_key_is_rejected(self):
        report, _calls = self._run(
            {"me": {"id": "agent:someone-else", "kind": "agent"}, "roster": self.ROSTER}
        )

        self.assertFalse(report["ok"])
        self.assertTrue(any(k28.MEMBER_ID in item for item in report["problems"]), report["problems"])

    def test_non_agent_kind_is_rejected(self):
        report, _calls = self._run(
            {"me": {"id": k28.MEMBER_ID, "kind": "human"}, "roster": self.ROSTER}
        )

        self.assertFalse(report["ok"])
        self.assertTrue(any("kind" in item for item in report["problems"]), report["problems"])

    def test_unregistered_key_http_401_is_rejected(self):
        report, calls = self._run(
            {"me": k28.K28ExecutorError("只读身份请求失败：HTTP 401 无效的 API Key")}
        )

        self.assertFalse(report["ok"])
        self.assertIn("HTTP 401", " ".join(report["problems"]))
        self.assertEqual(report["network_calls"], 1)
        self.assertEqual(len(calls), 1)

    def test_missing_from_roster_is_rejected(self):
        report, _calls = self._run(
            {
                "me": {"id": k28.MEMBER_ID, "kind": "agent"},
                "roster": [self.ROSTER[0]],
            }
        )

        self.assertFalse(report["ok"])
        self.assertTrue(any("名册" in item for item in report["problems"]), report["problems"])

    def test_role_or_tier_mismatch_is_rejected(self):
        roster = [
            {
                "member_id": k28.MEMBER_ID,
                "business_role": "reviewer",
                "decision_tier": "decision",
            }
        ]
        report, _calls = self._run(
            {"me": {"id": k28.MEMBER_ID, "kind": "agent"}, "roster": roster}
        )

        self.assertFalse(report["ok"])
        joined = " ".join(report["problems"])
        self.assertIn("business_role", joined)
        self.assertIn("decision_tier", joined)

    def test_network_failure_is_rejected_before_any_write(self):
        report, _calls = self._run(
            {"me": k28.K28ExecutorError("只读身份请求失败：无法连接 TALK API（拒绝访问）")}
        )

        self.assertFalse(report["ok"])
        self.assertIn("无法连接 TALK API", " ".join(report["problems"]))
        self.assertFalse(report["roster_found"])

    def test_problems_never_contain_the_api_key(self):
        # 非 sk 前缀的“文件型”Key：异常正文确实回显它，且它确实是本次请求使用的 Key。
        secret = "plain-ascii-file-token-9f3a2c"
        report, calls = self._run(
            {
                "me": k28.K28ExecutorError(
                    f"只读身份请求失败：HTTP 500 内部错误 body={secret}"
                )
            },
            api_key=secret,
        )

        self.assertTrue(calls, "Key 必须真的传进只读请求")
        self.assertTrue(all(key == secret for _url, key in calls))
        dumped = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(secret, dumped)
        self.assertIn("[REDACTED]", dumped)
        self.assertIn("HTTP 500", dumped)


class HttpErrorBodyLeakTests(K28ExecutorTestCase):
    """B3：HTTPError 正文即使原样回显文件型 Key，也不得进入 report / 入口 stderr。"""

    SECRET = "plain-file-key-3d7b91"
    BODY_MARKER = "internal-body-marker"

    def _http_error(self) -> HTTPError:
        body = json.dumps(
            {"detail": f"invalid api key {self.SECRET} ({self.BODY_MARKER})"}
        ).encode("utf-8")
        return HTTPError(
            "http://127.0.0.1:9/api/members/me",
            500,
            "Internal Server Error",
            None,
            io.BytesIO(body),
        )

    def test_http_error_detail_reports_status_only(self):
        detail = k28._http_error_detail(self._http_error())

        self.assertIn("HTTP 500", detail)
        self.assertNotIn(self.SECRET, detail)
        self.assertNotIn(self.BODY_MARKER, detail)

    def test_http_get_json_hides_server_body(self):
        with patch.object(k28, "urlopen", side_effect=self._http_error()):
            with self.assertRaises(k28.K28ExecutorError) as ctx:
                k28._http_get_json(
                    "http://127.0.0.1:9/api/members/me", api_key=self.SECRET, timeout=1.0
                )

        message = str(ctx.exception)
        self.assertIn("HTTP 500", message)
        self.assertNotIn(self.SECRET, message)
        self.assertNotIn(self.BODY_MARKER, message)

    def test_preflight_report_hides_key_echoed_by_http_error(self):
        with patch.object(k28, "urlopen", side_effect=self._http_error()):
            report = k28.identity_preflight(
                base_url="http://127.0.0.1:9", api_key=self.SECRET
            )

        dumped = json.dumps(report, ensure_ascii=False)
        self.assertFalse(report["ok"])
        self.assertIn("HTTP 500", dumped)
        self.assertNotIn(self.SECRET, dumped)
        self.assertNotIn(self.BODY_MARKER, dumped)

    def test_file_key_used_in_real_request_and_entry_hides_body(self):
        import http.server
        import threading

        secret = self.SECRET
        body_marker = self.BODY_MARKER
        seen: list[str | None] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server 接口
                seen.append(self.headers.get("X-API-Key"))
                body = json.dumps(
                    {"detail": f"invalid api key {secret} ({body_marker})"}
                ).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # noqa: D102 - 静音测试日志
                return

        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except OSError as exc:
            self.skipTest(f"当前宿主禁止本地监听：{exc}")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        self.key_file.write_text(secret + "\n", encoding="utf-8")
        base_url = f"http://127.0.0.1:{server.server_port}"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = k28.main(
                [
                    "check",
                    "--project-root", str(PROJECT_ROOT),
                    "--kimi-config", str(self.config_path),
                    "--key-file", str(self.key_file),
                    "--online-identity",
                    "--base-url", base_url,
                ]
            )

        self.assertEqual(code, 1)
        self.assertTrue(seen, "文件 Key 必须真的用于本次请求")
        self.assertTrue(all(key == secret for key in seen), seen)
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertIn("HTTP 500", combined)
        self.assertNotIn(secret, combined)
        self.assertNotIn(body_marker, combined)


class LoopbackIdentityTests(K28ExecutorTestCase):
    """用真实 loopback HTTP 证明 `_http_get_json` 的路径与 X-API-Key 头。"""

    def test_http_get_json_sends_key_header_and_parses_json(self):
        import http.server
        import threading

        seen: list[tuple[str, str | None]] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server 接口
                seen.append((self.path, self.headers.get("X-API-Key")))
                if self.path.endswith("/api/members/me"):
                    payload = {"id": k28.MEMBER_ID, "kind": "agent"}
                else:
                    payload = [
                        {
                            "member_id": k28.MEMBER_ID,
                            "business_role": k28.BUSINESS_ROLE,
                            "decision_tier": k28.DECISION_TIER,
                        }
                    ]
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # noqa: D102 - 静音测试日志
                return

        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except OSError as exc:
            self.skipTest(f"当前宿主禁止本地监听：{exc}")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            report = k28.identity_preflight(base_url=base_url, api_key="loop-key")
        except k28.K28ExecutorError as exc:
            self.skipTest(f"当前宿主禁止 loopback HTTP：{exc}")

        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(seen[0][0], "/api/members/me")
        self.assertEqual(seen[1][0], f"/api/projects/{k28.PROJECT_ID}/agents")
        self.assertTrue(all(key == "loop-key" for _path, key in seen))
        self.assertNotIn("loop-key", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
