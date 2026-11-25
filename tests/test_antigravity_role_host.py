"""Slice C tests: Antigravity managed role setup, host, runtime/recovery/delete/bootstrap/server wiring."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from sqlmodel import Session, create_engine, select

from bridges import antigravity_bridge
from bridges import antigravity_execution_native as agy_native
from bridges.antigravity_execution_native import AntigravityNativeError
from scripts import antigravity_role_host as host
from scripts import antigravity_role_setup as setup
from scripts import portable_bootstrap
from scripts import role_delete
from scripts import role_provision as provision
from scripts import role_service_host as rsh
from scripts import role_service_recovery as recovery
from scripts import talk_runtime as runtime
from server import role_host_resolution as resolution
from server import workspace_paths as wp
from server.models import (
    Project,
    ProjectRoleBinding,
    RunnerModelChoice,
    RunnerRegistry,
    SQLModel,
)
from tests.test_talk_runtime import Client, Process
from tests.test_support import RouteTestCase

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_AGY_MODELS = "\n".join(
    [
        "Fetching available models...",
        "gemini-4-neon-low\tGemini 4 Neon (Low)",
        "gemini-4-neon-medium\tGemini 4 Neon (Medium)",
        "gemini-4-neon-high\tGemini 4 Neon (High)",
        "gemini-4-neon-xhigh\tGemini 4 Neon (Extra High)",
        "gemini-4-carbon-low\tGemini 4 Carbon (Low)",
        "gemini-4-carbon-medium\tGemini 4 Carbon (Medium)",
        "gemini-4-carbon-high\tGemini 4 Carbon (High)",
        "gemini-4-hydrogen-low\tGemini 4 Hydrogen (Low)",
        "gemini-4-hydrogen-medium\tGemini 4 Hydrogen (Medium)",
        "gemini-4-hydrogen-high\tGemini 4 Hydrogen (High)",
        "gemini-4-hydrogen-xhigh\tGemini 4 Hydrogen (Extra High)",
        "other-unrelated-model\tOther Model",
    ]
)


class AntigravityRoleSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agy-role-setup-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / ("agy.exe" if os.name == "nt" else "agy")
        self.exe.write_text("synthetic", encoding="utf-8")

    def test_executable_and_recipe_validation(self):
        self.assertEqual(
            setup.executable({"antigravity": {"enabled": True, "executable": str(self.exe)}}),
            str(self.exe.resolve()),
        )
        for bad_config in (
            {},
            {"antigravity": {"enabled": False, "executable": str(self.exe)}},
            {"antigravity": {"enabled": True, "executable": "agy.exe"}},
            {"antigravity": {"enabled": True, "executable": str(self.root / "other.exe")}},
            {"antigravity": {"enabled": True, "executable": str(self.root / "missing.exe")}},
        ):
            with self.subTest(bad_config=bad_config), self.assertRaisesRegex(
                setup.SetupError, "native_cli_missing"
            ):
                setup.executable(bad_config)
        with patch.object(setup, "find_antigravity_executable", return_value=str(self.exe)):
            self.assertEqual(
                setup.antigravity_recipe(),
                {"enabled": True, "executable": str(self.exe.resolve()), "task_profiles": {}},
            )
        with patch.object(setup, "find_antigravity_executable", return_value=str(self.root / "codex.cmd")):
            self.assertIsNone(setup.antigravity_recipe())

    def test_environment_and_prepare_role_home_isolate_all_vars(self):
        import urllib.request

        home = self.root / "isolated-home"
        prepared = setup.prepare_role_home(home)
        self.assertTrue(prepared.is_dir())
        clean_proxy_base = {
            k: v for k, v in os.environ.items() if k.upper() not in set(setup.CANONICAL_PROXY_ENV_VARS)
        }
        with patch.dict(
            os.environ,
            {
                **clean_proxy_base,
                "HTTPS_PROXY": " http://user:s3cr3t@127.0.0.1:7890 ",
                "NO_PROXY": "internal.local",
            },
            clear=True,
        ):
            env = setup.environment(home)
            secrets = setup.sensitive_proxy_values()
        for var in rsh.NATIVE_HOME_ENV_VARS:
            self.assertEqual(Path(env[var]), home.resolve())
        self.assertEqual(Path(env["ANTIGRAVITY_HOME"]), home.resolve())
        self.assertEqual(env["HTTPS_PROXY"], "http://user:s3cr3t@127.0.0.1:7890")
        if os.name == "nt":
            for lower_key in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
                self.assertNotIn(lower_key, env)
        no_proxy_tokens = {item.strip().lower() for item in env["NO_PROXY"].split(",")}
        self.assertTrue({"internal.local", "127.0.0.1", "localhost", "::1"}.issubset(no_proxy_tokens))
        self.assertIn("http://user:s3cr3t@127.0.0.1:7890", secrets)
        self.assertIn("user:s3cr3t", secrets)
        self.assertIn("s3cr3t", secrets)

        # Lowercase-only no_proxy is preserved in NO_PROXY (never shadowed in Go httpproxy).
        lower_env = setup.apply_proxy_env(
            {}, source={"http_proxy": "http://127.0.0.1:7890", "no_proxy": "corp.local"}
        )
        for key in ("NO_PROXY", "no_proxy"):
            tokens = {item.strip().lower() for item in lower_env[key].split(",")}
            self.assertTrue({"corp.local", "127.0.0.1", "localhost", "::1"}.issubset(tokens), lower_env)

        # Wildcard NO_PROXY="*" must remain exact "*" so urllib wildcard bypass still works.
        wild_env = setup.apply_proxy_env(
            {}, source={"HTTPS_PROXY": "http://127.0.0.1:7890", "NO_PROXY": "*"}
        )
        self.assertEqual(wild_env["NO_PROXY"], "*")
        self.assertTrue(urllib.request.proxy_bypass_environment("example.com", {"no": wild_env["NO_PROXY"]}))

        # Control characters in proxy values are ignored; without proxy vars, NO_PROXY is not fabricated.
        self.assertEqual(setup.apply_proxy_env({}, source={"HTTP_PROXY": "http://bad\r\nheader"}), {})
        self.assertEqual(setup.apply_proxy_env({}, source={}), {})

        # Credential parsing handles bare tokens, percent-encoded passwords, and ignores degenerate values.
        token_secrets = setup.sensitive_proxy_values(
            {
                "HTTPS_PROXY": " http://mysecrettoken@127.0.0.1:7890 ",
                "ALL_PROXY": "socks5://alice:p%40ssword@127.0.0.1:1080",
                "HTTP_PROXY": " @ ",
                "NO_PROXY": "foo@bar.local",
            }
        )
        self.assertIn("http://mysecrettoken@127.0.0.1:7890", token_secrets)
        self.assertIn("mysecrettoken", token_secrets)
        self.assertIn("p%40ssword", token_secrets)
        self.assertIn("p@ssword", token_secrets)
        self.assertNotIn(" @ ", token_secrets)
        self.assertNotIn("foo@bar.local", token_secrets)
        self.assertEqual(setup.sensitive_proxy_values({"HTTPS_PROXY": "http://127.0.0.1:7890"}), ())

    def test_probe_catalog_real_check_and_real_error_mapping(self):
        help_text = "\n".join(
            [
                "Usage of agy.exe:",
                "  --print                         Run a single prompt",
                "  --model                         Model for session",
                "  --effort                        Reasoning effort",
                "  --output-format                 Output format (text, json, stream-json)",
                "  --conversation                  Resume conversation",
                "  --mode                          Mode (accept-edits, auto, plan)",
                "  --sandbox                       Run in sandbox",
                "  --dangerously-skip-permissions  Auto-approve",
                "  --disable-slash-commands        Disable slash commands",
                "  --print-timeout                 Print timeout",
                "Available subcommands:",
                "  models                          List available models",
            ]
        )

        class FakeCompleted:
            def __init__(self, stdout="", stderr="", returncode=0):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode

        def ok_run(argv, **kwargs):
            if argv[1:] == ["--version"]:
                return FakeCompleted(stdout="agy version 1.5.16\n")
            if argv[1:] == ["--help"]:
                return FakeCompleted(stderr=help_text)
            if argv[1:] == ["models"]:
                return FakeCompleted(stdout=SAMPLE_AGY_MODELS)
            raise AssertionError(f"unexpected argv: {argv}")

        agy_native.clear_antigravity_probe_cache()
        self.addCleanup(agy_native.clear_antigravity_probe_cache)
        with patch.object(agy_native.subprocess, "run", side_effect=ok_run):
            info = setup.probe_catalog(str(self.exe), cwd=self.root, use_cache=False)
        self.assertEqual(info["version"], "1.5.16")
        self.assertEqual(
            [m["model_id"] for m in info["models"]],
            ["gemini-4-neon", "gemini-4-carbon", "gemini-4-hydrogen"],
        )
        self.assertEqual(info["models"][1]["supported_efforts"], ["low", "medium", "high"])

        # Real models failure emits antigravity_models_probe_failed -> native_model_catalog_unavailable.
        def models_fail(argv, **kwargs):
            if argv[1:] == ["models"]:
                return FakeCompleted(returncode=1)
            return ok_run(argv, **kwargs)

        with patch.object(agy_native.subprocess, "run", side_effect=models_fail):
            with self.assertRaisesRegex(setup.SetupError, "native_model_catalog_unavailable"):
                setup.probe_catalog(str(self.exe), cwd=self.root, use_cache=False)

        # Missing binary FileNotFoundError -> antigravity_probe_failed -> native_cli_missing.
        with patch.object(agy_native.subprocess, "run", side_effect=FileNotFoundError("no such binary")):
            with self.assertRaisesRegex(setup.SetupError, "native_cli_missing"):
                setup.probe_catalog(str(self.exe), cwd=self.root, use_cache=False)

        # Unsupported version -> antigravity_version_unsupported -> native_cli_version_unsupported.
        def old_ver(argv, **kwargs):
            if argv[1:] == ["--version"]:
                return FakeCompleted(stdout="agy version 0.1.0\n")
            return ok_run(argv, **kwargs)

        with patch.object(agy_native.subprocess, "run", side_effect=old_ver):
            with self.assertRaisesRegex(setup.SetupError, "native_cli_version_unsupported"):
                setup.probe_catalog(str(self.exe), cwd=self.root, use_cache=False)

        # Empty model catalog -> native_model_catalog_unavailable.
        def empty_models(argv, **kwargs):
            if argv[1:] == ["models"]:
                return FakeCompleted(stdout="Fetching available models...\nother-model\tOther\n")
            return ok_run(argv, **kwargs)

        with patch.object(agy_native.subprocess, "run", side_effect=empty_models):
            with self.assertRaisesRegex(setup.SetupError, "native_model_catalog_unavailable"):
                setup.probe_catalog(str(self.exe), cwd=self.root, use_cache=False)

    def test_executable_validation_rejects_arbitrary_binary_and_parent_junction(self):
        evil = self.root / "evil.exe"
        evil.write_text("synthetic", encoding="utf-8")
        with self.assertRaisesRegex(setup.SetupError, "native_cli_missing"):
            setup.validate_executable_path(str(evil), must_exist=True)
        with patch.object(setup, "probe_catalog", side_effect=AssertionError("must not run evil binary")), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = setup.main(["--antigravity-executable", str(evil)])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out.getvalue())["error_code"], "native_cli_missing")

        if os.name == "nt":
            import subprocess as _sp

            outside = self.root / "outside-target"
            outside.mkdir()
            junction = self.root / "junction-parent"
            res = _sp.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            try:
                escaped = junction / "new-home"
                with self.assertRaisesRegex(setup.SetupError, "state_dir_insecure"):
                    setup.prepare_role_home(escaped)
                self.assertFalse((outside / "new-home").exists())

                linked_exe = junction / "agy.exe"
                (outside / "agy.exe").write_text("synthetic", encoding="utf-8")
                with self.assertRaisesRegex(setup.SetupError, "native_cli_missing"):
                    setup.validate_executable_path(str(linked_exe), must_exist=True)
            finally:
                _sp.run(["cmd", "/c", "rmdir", str(junction)], capture_output=True)

    def test_seed_antigravity_choices_idempotent_and_exact_efforts(self):
        db_path = self.root / "seed.db"
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        try:
            SQLModel.metadata.create_all(engine)
            with Session(engine) as session:
                first = setup.seed_antigravity_choices(session, "human:operator")
                self.assertEqual(first, {"runners": 1, "models": 3})
                second = setup.seed_antigravity_choices(session, "human:operator")
                self.assertEqual(second, {"runners": 0, "models": 0})
                runner = session.get(RunnerRegistry, setup.RUNNER_ID)
                self.assertIsNotNone(runner)
                self.assertEqual(runner.runtime, "antigravity")
                self.assertEqual(runner.display_name, "Antigravity CLI")
                self.assertEqual(runner.control_kind, "managed_cli")
                choices = {
                    row.model_id: row
                    for row in session.exec(
                        select(RunnerModelChoice).where(RunnerModelChoice.runner_id == setup.RUNNER_ID)
                    ).all()
                }
                self.assertEqual(set(choices), {"gemini-4-neon", "gemini-4-carbon", "gemini-4-hydrogen"})
                self.assertEqual(
                    choices["gemini-4-neon"].capabilities,
                    ["effort:low", "effort:medium", "effort:high", "effort:xhigh", "effort_default:high"],
                )
                self.assertEqual(
                    choices["gemini-4-carbon"].capabilities,
                    ["effort:low", "effort:medium", "effort:high", "effort_default:high"],
                )
                self.assertEqual(
                    choices["gemini-4-hydrogen"].capabilities,
                    ["effort:low", "effort:medium", "effort:high", "effort:xhigh", "effort_default:high"],
                )
        finally:
            engine.dispose()

    def test_cli_main_dry_run_and_apply_seed(self):
        db_path = self.root / "cli.db"
        fake_info = {
            "executable": str(self.exe),
            "version": "1.5.16",
            "warning": None,
            "capabilities": {},
            "models": [
                {
                    "model_id": "gemini-4-carbon",
                    "display_name": "Gemini 4 Carbon",
                    "supported_efforts": ["low", "medium", "high"],
                    "default_effort": "high",
                }
            ],
        }
        with patch.object(setup, "probe_catalog", return_value=fake_info), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = setup.main(["--antigravity-executable", str(self.exe), "--seed-db", str(db_path)])
        self.assertEqual(rc, 0)
        parsed = json.loads(out.getvalue())
        self.assertEqual(parsed["mode"], "dry_run")
        self.assertEqual(parsed["seed"], "dry_run")
        self.assertFalse(db_path.exists())

        with patch.object(setup, "probe_catalog", return_value=fake_info), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = setup.main(["--antigravity-executable", str(self.exe), "--seed-db", str(db_path), "--apply"])
        self.assertEqual(rc, 0)
        parsed = json.loads(out.getvalue())
        self.assertEqual(parsed["mode"], "apply")
        self.assertEqual(parsed["seed"], {"runners": 1, "models": 1})


class AntigravityRoleHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agy-new-role-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project").mkdir()
        (self.root / "state").mkdir()
        self.exe = self.root / ("agy.exe" if os.name == "nt" else "agy")
        self.exe.write_text("synthetic", encoding="utf-8")
        self.config = {
            "schema": "talk-runtime-config-1",
            "version": 1,
            "project_id": "p",
            "project_root": str(self.root / "project"),
            "state_dir": str(self.root / "state"),
            "key_root": str(self.root / "keys"),
            "operator_key_file": str(self.root / "human.key"),
            "base_url": "http://127.0.0.1:1",
            "hosts": [],
            "antigravity": {"enabled": True, "executable": str(self.exe), "task_profiles": {}},
            "api_argv": [sys.executable, "-m", "scripts.talk_api", "--control-file", "{control_file}"],
        }
        self.role = {
            "project_id": "p",
            "member_id": "agent:agy-neon",
            "role_name": "Neon Worker",
            "archived": False,
            "binding_state": "bound",
            "runner": {"runtime": "antigravity", "status": "unverified"},
            "model": {
                "choice_id": "rmc_neon",
                "model_alias": "gemini-4-neon",
                "model_id": "gemini-4-neon",
            },
            "service": {
                "generation": 1,
                "ownership_held": False,
                "control_kind": "managed_cli",
                "current_launch": {"action": "start", "state": "pending"},
            },
        }
        self.client = Client()
        self.client.identity = {"id": "agent:agy-neon", "kind": "agent", "display_name": "Neon Worker"}
        self.spawned = []

        def spawn(label, argv):
            process = Process(400 + len(self.spawned))
            self.spawned.append((label, argv, process))
            return process

        self.runtime = runtime.TalkRuntime(self.config, client=self.client, spawn=spawn)

    def key(self, member="agent:agy-neon"):
        key = provision.key_file_path(Path(self.config["key_root"]), member)
        key.parent.mkdir(parents=True, exist_ok=True)
        rsh._publish_private_bytes(key, b"synthetic-agy-role-key\n")
        return key

    def manager(self, member="agent:agy-neon", profile="tools"):
        return host.AntigravityRoleHost(
            self.client,
            project="p",
            member=member,
            display_name="Neon Worker",
            task_profile=profile,
            antigravity_executable=str(self.exe),
            private=host.manager_directory(self.config["state_dir"], "p", member),
            state_dir=Path(self.config["state_dir"]),
            project_root=self.root / "project",
        )

    def workspace_context(self, member="agent:agy-neon"):
        data = self.root / "data"
        data.mkdir(exist_ok=True)
        args = (data, "p", member)
        return {
            "data_root": str(data),
            "project_root": str(self.root / "project"),
            "project_id": "p",
            "member_id": member,
            "layout": "workspace-v1",
            "runner": "antigravity",
            "key": str(wp.key_path(*args, git_key_root=Path(self.config["key_root"]))),
            "home": str(wp.native_home_dir(*args)),
            "session": str(wp.execution_session_store_path(*args)),
            "logs": str(wp.logs_dir(*args)),
            "state": {
                "records": str(wp.records_dir(*args)),
                "control": str(wp.control_dir(*args)),
                "manager": str(wp.manager_dir(*args, "antigravity")),
            },
        }

    def workspace_manager(self, context):
        return host.AntigravityRoleHost(
            self.client,
            project="p",
            member=context["member_id"],
            display_name="Neon Worker",
            task_profile="review",
            private=self.root / "unused-global",
            state_dir=Path(self.config["state_dir"]),
            project_root=self.root / "project",
            role_key_root=Path(self.config["key_root"]),
            role_key_file=Path(context["key"]),
            workspace_context=context,
            workspace_project="p",
            workspace_member=context["member_id"],
            workspace_data_root=self.root / "data",
            runtime_log_dir=Path(context["logs"]),
            antigravity_executable=str(self.exe),
        )

    def test_runtime_discovers_and_spawns_dynamic_antigravity_host(self):
        self.runtime.reconcile_hosts([])
        self.assertFalse(self.spawned)
        self.key()
        self.runtime.reconcile_hosts([self.role])
        self.runtime.reconcile_hosts([self.role])
        self.assertEqual(len(self.spawned), 1)
        argv = self.spawned[0][1]
        self.assertIn("scripts.antigravity_role_host", argv)
        self.assertEqual(argv[argv.index("--member") + 1], "agent:agy-neon")
        self.assertEqual(argv[argv.index("--expected-choice-id") + 1], "rmc_neon")
        self.assertEqual(argv[argv.index("--expected-model-alias") + 1], "gemini-4-neon")
        self.assertEqual(argv[argv.index("--antigravity-executable") + 1], str(self.exe))
        self.assertEqual(argv[argv.index("--task-profile") + 1], "tools")

    def test_host_spec_guards_and_task_profiles(self):
        role_no_proj = deepcopy(self.role)
        role_no_proj.pop("project_id")
        self.assertIsNotNone(host.host_spec(self.config, role_no_proj))

        for field, value in [("project_id", "other"), ("binding_state", "unconfigured"), ("archived", True)]:
            bad = deepcopy(self.role)
            bad[field] = value
            self.assertIsNone(self.runtime.antigravity_spec(bad))
        non_managed = deepcopy(self.role)
        non_managed["service"]["control_kind"] = "external_desktop"
        self.assertIsNone(self.runtime.antigravity_spec(non_managed))

        self.config["antigravity"]["task_profiles"] = {"agent:agy-neon": "review"}
        spec = host.host_spec(self.config, self.role)
        self.assertEqual(spec["argv"][spec["argv"].index("--task-profile") + 1], "review")

        self.config["antigravity"]["task_profiles"] = {"agent:agy-neon": "unrestricted"}
        cfg_file = self.root / "runtime.json"
        cfg_file.write_text(json.dumps(self.config), encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeErrorCode, "runtime_host_config_invalid"):
            runtime.load_config(cfg_file)

        # Falsy non-dict task_profiles must be rejected by both host_spec and load_config.
        for bad_profiles in ([], "", 0, False):
            bad_cfg = deepcopy(self.config)
            bad_cfg["antigravity"]["task_profiles"] = bad_profiles
            with self.subTest(bad_profiles=bad_profiles), self.assertRaisesRegex(
                ValueError, "antigravity_task_profile_invalid"
            ):
                host.host_spec(bad_cfg, self.role)

        # Arbitrary non-agy executables must be rejected by host_spec, load_config, and build_entry_argv.
        evil_exe = self.root / "cmd.exe"
        evil_exe.write_text("synthetic", encoding="utf-8")
        evil_cfg = deepcopy(self.config)
        evil_cfg["antigravity"]["executable"] = str(evil_exe)
        evil_cfg["antigravity"]["task_profiles"] = {}
        with self.assertRaisesRegex(ValueError, "antigravity_executable_required"):
            host.host_spec(evil_cfg, self.role)
        cfg_file.write_text(json.dumps(evil_cfg), encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeErrorCode, "runtime_host_config_invalid"):
            runtime.load_config(cfg_file)

        self.config["antigravity"] = {"enabled": False, "executable": str(self.exe)}
        self.assertIsNone(host.host_spec(self.config, self.role))

    def test_missing_or_mismatched_key_blocks_spawn(self):
        self.runtime.reconcile_hosts([self.role])
        self.assertEqual(self.runtime.statuses["agent:agy-neon"]["state"], "key_not_configured")
        self.key()
        self.client.identity["id"] = "agent:other"
        self.runtime.reconcile_hosts([self.role])
        self.assertEqual(self.runtime.statuses["agent:agy-neon"]["state"], "identity_mismatch")
        self.assertFalse(self.spawned)

    def test_configuration_resolves_efforts_and_strictly_rejects_carbon_xhigh(self):
        manager = self.manager()
        neon_binding = {
            "runtime": "antigravity",
            "model_alias": "gemini-4-neon",
            "model_id": "gemini-4-neon",
            "provider_id": "google-antigravity",
            "default_effort": "high",
            "effective_effort": "xhigh",
            "effort_override": "xhigh",
            "effort_options": ["low", "medium", "high", "xhigh"],
            "effort_source": "adapter",
        }
        with patch.object(manager, "_current_binding", return_value=neon_binding):
            self.assertEqual(manager._configuration("gemini-4-neon"), ("gemini-4-neon", "xhigh"))

        carbon_ok = {
            "runtime": "antigravity",
            "model_alias": "gemini-4-carbon",
            "model_id": "gemini-4-carbon",
            "provider_id": "google-antigravity",
            "default_effort": "high",
            "effective_effort": "medium",
            "effort_override": "medium",
            "effort_options": ["low", "medium", "high"],
            "effort_source": "adapter",
        }
        with patch.object(manager, "_current_binding", return_value=carbon_ok):
            self.assertEqual(manager._configuration("gemini-4-carbon"), ("gemini-4-carbon", "medium"))

        # Carbon MUST reject xhigh even if binding advertises it.
        carbon_xhigh = dict(
            carbon_ok,
            effective_effort="xhigh",
            effort_override="xhigh",
            effort_options=["low", "medium", "high", "xhigh"],
        )
        with patch.object(manager, "_current_binding", return_value=carbon_xhigh):
            with self.assertRaises(rsh.HostError) as caught:
                manager._configuration("gemini-4-carbon")
        self.assertEqual(caught.exception.code, "antigravity_effort_unsupported")

        # Unsupported model fails closed.
        unsupported = dict(carbon_ok, model_id="claude-4", model_alias="claude-4")
        with patch.object(manager, "_current_binding", return_value=unsupported):
            with self.assertRaises(rsh.HostError) as caught:
                manager._configuration("claude-4")
        self.assertEqual(caught.exception.code, "antigravity_model_unsupported")

        # Mismatched model_id vs model_alias fails closed.
        mismatch = dict(carbon_ok, model_id="gemini-4-neon", model_alias="gemini-4-carbon")
        with patch.object(manager, "_current_binding", return_value=mismatch):
            with self.assertRaises(rsh.HostError) as caught:
                manager._configuration("gemini-4-carbon")
        self.assertEqual(caught.exception.code, "binding_fingerprint_mismatch")

        # Missing effective_effort falls back to model default ("high").
        fallback_binding = {
            "runtime": "antigravity",
            "model_alias": "gemini-4-hydrogen",
            "model_id": "gemini-4-hydrogen",
            "provider_id": "google-antigravity",
        }
        with patch.object(manager, "_current_binding", return_value=fallback_binding):
            self.assertEqual(manager._configuration("gemini-4-hydrogen"), ("gemini-4-hydrogen", "high"))

    def test_generated_bridge_argv_passes_real_host_preflight_parser(self):
        for profile, timeout, model, effort in [
            ("review", None, "gemini-4-neon", "xhigh"),
            ("tools", 123, "gemini-4-carbon", "medium"),
            ("tools", 600, "gemini-4-hydrogen", "low"),
        ]:
            with self.subTest(profile=profile, timeout=timeout, model=model, effort=effort):
                manager = self.manager(profile=profile)
                manager.execution_timeout_seconds = timeout
                with patch.object(manager, "_configuration", return_value=(model, effort)), \
                     patch.object(manager, "child_environment", return_value={}), \
                     patch.object(
                         host,
                         "check_antigravity",
                         return_value={"version": "1.5.16", "warning": None, "capabilities": {}},
                     ):
                    argv, source, budget = manager.build_entry_argv("antigravity", model)
                self.assertEqual(source, "antigravity_role_selection")
                self.assertEqual(budget, "explicit" if timeout else "builtin_default")
                fingerprint = rsh.verify_runtime_entry("antigravity", argv)
                self.assertTrue(fingerprint.startswith("bridges.antigravity_bridge@"))
                self.assertGreater(rsh.parse_unit_count(argv, "antigravity"), 0)
                parsed = antigravity_bridge.build_parser().parse_args(argv[3:])
                self.assertEqual(parsed.antigravity_executable, str(self.exe))
                self.assertEqual(parsed.antigravity_model, model)
                self.assertEqual(parsed.antigravity_effort, effort)
                self.assertEqual(parsed.antigravity_task_profile, profile)
                self.assertEqual(parsed.timeout, timeout or 86400)
                self.assertEqual(parsed.display_name, "Neon Worker")
                self.assertEqual(Path(parsed.workdir), (self.root / "project").resolve())

        manager = self.manager()
        with self.assertRaises(rsh.HostError) as caught:
            manager.build_entry_argv("codex", "gemini-4-neon")
        self.assertEqual(caught.exception.code, "antigravity_runtime_only")

        with patch.object(manager, "_configuration", return_value=("gemini-4-neon", "high")), \
             patch.object(manager, "child_environment", return_value={}), \
             patch.object(
                 host,
                 "check_antigravity",
                 side_effect=AntigravityNativeError("antigravity_probe_failed", "FileNotFoundError"),
             ):
            with self.assertRaises(rsh.HostError) as caught:
                manager.build_entry_argv("antigravity", "gemini-4-neon")
        self.assertEqual(caught.exception.code, "antigravity_probe_failed")

        # Tampered non-agy executable fails before check_antigravity is ever executed.
        evil_exe = self.root / "cmd.exe"
        evil_exe.write_text("synthetic", encoding="utf-8")
        manager.antigravity_executable = str(evil_exe)
        with patch.object(manager, "_configuration", return_value=("gemini-4-neon", "high")), \
             patch.object(host, "check_antigravity", side_effect=AssertionError("must not invoke arbitrary exe")):
            with self.assertRaises(rsh.HostError) as caught:
                manager.build_entry_argv("antigravity", "gemini-4-neon")
        self.assertEqual(caught.exception.code, "antigravity_executable_required")

    def test_workspace_home_environment_health_and_drain(self):
        context = self.workspace_context()
        manager = self.workspace_manager(context)
        role_home = Path(context["home"])
        clean_proxy_base = {
            k: v for k, v in os.environ.items() if k.upper() not in set(setup.CANONICAL_PROXY_ENV_VARS)
        }
        with patch.dict(
            os.environ,
            {
                **clean_proxy_base,
                "ALL_PROXY": "socks5://proxyuser:proxys3cr3t@127.0.0.1:7897",
                "NO_PROXY": "corp.local",
            },
            clear=True,
        ):
            environment = manager.child_environment("p", "agent:agy-neon")
            sensitive = manager._host_sensitive_values()
            diag = manager._launch_diagnostics(
                project_id="p",
                member_id="agent:agy-neon",
                launch_id="launch-proxy-redact",
                instance_id="ins_1",
                runtime="antigravity",
            )
            diag.record_event(
                "proxy_probe",
                extra={
                    "detail": "Proxy socks5://proxyuser:proxys3cr3t@127.0.0.1:7897 rejected proxys3cr3t",
                },
            )
        for variable in rsh.NATIVE_HOME_ENV_VARS:
            self.assertEqual(Path(environment[variable]), role_home)
        self.assertEqual(Path(environment["ANTIGRAVITY_HOME"]), role_home)
        self.assertEqual(environment["ALL_PROXY"], "socks5://proxyuser:proxys3cr3t@127.0.0.1:7897")
        if os.name == "nt":
            for lower_key in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
                self.assertNotIn(lower_key, environment)
        no_proxy_tokens = {item.strip().lower() for item in environment["NO_PROXY"].split(",")}
        self.assertTrue({"corp.local", "127.0.0.1", "localhost", "::1"}.issubset(no_proxy_tokens))
        self.assertIn("socks5://proxyuser:proxys3cr3t@127.0.0.1:7897", sensitive)
        self.assertIn("proxys3cr3t", sensitive)
        log_files = list(Path(context["logs"]).rglob("events-*.jsonl"))
        self.assertTrue(log_files)
        log_text = "\n".join(p.read_text(encoding="utf-8") for p in log_files)
        self.assertNotIn("proxys3cr3t", log_text)
        self.assertIn("REDACTED", log_text)
        self.assertEqual(manager.private, Path(context["state"]["manager"]))
        self.assertEqual(manager.private.parts[-3:], ("state", "manager", "antigravity"))
        manager.publish_health()
        health = json.loads((manager.private / "manager-health.json").read_text(encoding="utf-8"))
        self.assertEqual(health["schema"], "talk-antigravity-manager-health-1")
        self.assertEqual(health["member_id"], "agent:agy-neon")
        (manager.private / "drain.request").write_text("drain", encoding="utf-8")
        with self.assertRaises(host.Drained):
            manager.claimable_actions("p")
        self.assertFalse((self.root / "unused-global").exists())

    def test_workspace_rejects_inconsistent_context_and_scope(self):
        context = self.workspace_context()
        for mutate in ("runner", "member_id", "home", "manager"):
            bad = deepcopy(context)
            if mutate == "manager":
                bad["state"]["manager"] = str(self.root / "other")
            else:
                bad[mutate] = "other" if mutate != "home" else str(self.root / "other")
            with self.subTest(mutate=mutate), self.assertRaises(rsh.HostError) as caught:
                self.workspace_manager(bad)
            self.assertEqual(caught.exception.code, "workspace_context_invalid")
        manager = self.workspace_manager(context)
        with self.assertRaises(rsh.HostError):
            manager.child_environment("p", "agent:other")

    def test_main_check_version_and_dry_run(self):
        with patch.object(
            host,
            "check_antigravity",
            return_value={"allowed": True, "version": "1.5.16", "warning": None},
        ), patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(host.main(["--check-version", "--antigravity-executable", str(self.exe)]), 0)
        self.assertEqual(json.loads(out.getvalue())["version"], "1.5.16")

        with patch.object(
            host,
            "check_antigravity",
            side_effect=AntigravityNativeError("antigravity_probe_failed", "FileNotFoundError"),
        ), patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(host.main(["--check-version", "--antigravity-executable", str(self.exe)]), 1)
        self.assertEqual(json.loads(out.getvalue())["error_code"], "antigravity_probe_failed")

        evil_exe = self.root / "cmd.exe"
        evil_exe.write_text("synthetic", encoding="utf-8")
        with patch.object(host, "check_antigravity", side_effect=AssertionError("must not probe evil exe")), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(host.main(["--check-version", "--antigravity-executable", str(evil_exe)]), 1)
        self.assertEqual(json.loads(out.getvalue())["error_code"], "antigravity_executable_required")

        spec = host.host_spec(self.config, self.role)
        dry_argv = [tok for tok in spec["argv"][spec["argv"].index("scripts.antigravity_role_host") + 1:] if tok != "--apply"]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(host.main(dry_argv), 0)
        self.assertEqual(json.loads(out.getvalue())["mode"], "dry_run")

    def test_main_legacy_and_workspace_layout_checks(self):
        self.key()
        layout_called = []

        class FakeLegacyClient:
            def request(inner, method, path, **kwargs):
                if path.endswith("/role-storage-layouts"):
                    layout_called.append(path)
                if path == "/api/members/me":
                    return {"id": "agent:agy-neon", "kind": "agent", "display_name": "Neon"} if kwargs.get("key") else {"kind": "human"}
                return [self.role]

        def drain(manager, *args, **kwargs):
            self.assertIsNone(manager.workspace_context)
            expected_private = Path(self.config["state_dir"]) / "antigravity-dynamic" / "p" / "agent_agy-neon"
            self.assertEqual(manager.private, expected_private)
            env = manager.child_environment("p", "agent:agy-neon")
            self.assertEqual(Path(env["ANTIGRAVITY_HOME"]), Path(self.config["state_dir"]) / "native" / "p" / "agent_agy-neon")
            manager.publish_health()
            (expected_private / "drain.request").write_text("drain", encoding="utf-8")
            with self.assertRaises(host.Drained):
                manager.claimable_actions("p")
            raise host.Drained()

        spec = host.host_spec(self.config, self.role)
        argv = spec["argv"][spec["argv"].index("scripts.antigravity_role_host") + 1:]
        with patch.object(rsh, "load_operator_key", return_value="synthetic"), \
             patch.object(rsh, "TalkHostClient", return_value=FakeLegacyClient()), \
             patch.object(host.AntigravityRoleHost, "serve", new=drain):
            self.assertEqual(host.main(argv), 0)
        self.assertEqual(layout_called, [])
        health = json.loads(
            (Path(self.config["state_dir"]) / "antigravity-dynamic" / "p" / "agent_agy-neon" / "manager-health.json").read_text(encoding="utf-8")
        )
        self.assertEqual((health["state"], health["draining"]), ("stopped", True))

        # Workspace mismatch must fail BEFORE reading role key.
        class FakeBadLayoutClient:
            def request(inner, method, path, **kwargs):
                if path == "/api/members/me":
                    return {"kind": "human"}
                if path.endswith("/role-storage-layouts"):
                    return [{"member_id": "agent:agy-neon", "storage_layout": "legacy"}]
                return [self.role]

        context = self.workspace_context()
        ws_argv = list(argv)
        ws_argv[ws_argv.index("--role-key-file") + 1] = context["key"]
        ws_argv += ["--workspace-context", json.dumps(context), "--key-root", self.config["key_root"]]
        orig_validate = rsh.validate_workspace_context

        def isolated_validate(value, **kwargs):
            kwargs["data_root"] = self.root / "data"
            return orig_validate(value, **kwargs)

        with patch.object(rsh, "validate_workspace_context", side_effect=isolated_validate), \
             patch.object(rsh, "load_operator_key", return_value="synthetic"), \
             patch.object(rsh, "TalkHostClient", return_value=FakeBadLayoutClient()), \
             patch.object(Path, "read_text", side_effect=AssertionError("role key must not be read")), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(host.main(ws_argv), 1)
        self.assertEqual(json.loads(out.getvalue())["error_code"], "workspace_context_invalid")


class AntigravityWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agy-wiring-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_role_host_resolution_legacy_and_workspace(self):
        config = {
            "project_root": str(ROOT),
            "state_dir": str(self.root / "state"),
            "hosts": [],
            "antigravity": {"enabled": True, "executable": str(self.root / "agy.exe")},
        }
        legacy = resolution.resolve_recovery_host(
            config=config,
            project_id="prj_1",
            member_id="agent:neon",
            original_runtime="antigravity",
            current_runtime="antigravity",
            control_kind="managed_cli",
            storage_layout="legacy",
        )
        self.assertEqual(legacy.source, "dynamic-antigravity")
        self.assertEqual(legacy.runner, "antigravity")
        self.assertEqual(legacy.host_entry.name, "antigravity_role_host.py")
        self.assertIn("antigravity-dynamic", legacy.health_file.parts)

        workspace = resolution.resolve_recovery_host(
            config=config,
            project_id="prj_1",
            member_id="agent:neon",
            original_runtime="antigravity",
            current_runtime="antigravity",
            control_kind="managed_cli",
            storage_layout="workspace-v1",
            data_root=self.root / "data",
        )
        self.assertEqual(workspace.source, "workspace-antigravity")
        self.assertEqual(
            workspace.health_file,
            wp.manager_dir(self.root / "data", "prj_1", "agent:neon", "antigravity") / "manager-health.json",
        )

        disabled = deepcopy(config)
        disabled["antigravity"]["enabled"] = False
        for layout in ("legacy", "workspace-v1"):
            with self.subTest(layout=layout), self.assertRaises(resolution.RecoveryHostError) as caught:
                resolution.resolve_recovery_host(
                    config=disabled,
                    project_id="prj_1",
                    member_id="agent:neon",
                    original_runtime="antigravity",
                    current_runtime="antigravity",
                    control_kind="managed_cli",
                    storage_layout=layout,
                    data_root=self.root / "data",
                )
            self.assertEqual(caught.exception.code, "local_recovery_host_unconfigured")

    def test_recovery_recognizes_antigravity_host_and_bridge(self):
        self.assertIn("scripts.antigravity_role_host", recovery._HOST_MODULES)
        entry = recovery.normalized(ROOT / "scripts" / "antigravity_role_host.py")
        self.assertEqual(
            recovery._host_candidate([sys.executable, "-m", "scripts.antigravity_role_host"], entry),
            "shared",
        )
        self.assertEqual(
            recovery._host_candidate(
                [sys.executable, "-m", "bridges.antigravity_bridge"], entry, include_bridges=True
            ),
            "bridge",
        )

    @unittest.skipUnless(os.name == "nt", "Windows handle deletion")
    def test_role_delete_cleans_antigravity_dynamic_and_blocks_live_manager(self):
        scratch = ROOT / ".tmp-tests"
        scratch.mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(prefix="talk-agy-delete-", dir=scratch)
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        project = base / "project"
        keys = base / "keys"
        state = base / "state"
        for d_path in (project, keys, state):
            d_path.mkdir()
        member = "agent:agy-del"
        project_id = "prj_agy"
        config = {
            "project_id": project_id,
            "project_root": str(project),
            "state_dir": str(state),
            "key_root": str(keys),
            "hosts": [],
            "base_url": "http://127.0.0.1:1",
        }
        cfg_path = base / "runtime.json"
        cfg_path.write_text(json.dumps(config), encoding="utf-8")
        rt = runtime.TalkRuntime(deepcopy(config), config_path=cfg_path)
        receipt = {
            "identity_disabled": True,
            "credential_digest": hashlib.sha256(b"isolated-agy-key").hexdigest(),
        }
        key = provision.key_file_path(keys, member)
        key.write_text("isolated-agy-key\n", encoding="utf-8")
        meta = provision.credential_metadata_path(keys, member)
        meta.write_text(json.dumps({"member_id": member}), encoding="utf-8")

        agy_dir = state / "antigravity-dynamic" / project_id / rsh._sanitize_token(member)
        agy_dir.mkdir(parents=True)
        other_dir = state / "antigravity-dynamic" / project_id / "agent_other"
        other_dir.mkdir(parents=True)
        (other_dir / "manager-health.json").write_text("{}", encoding="utf-8")

        # Live owned launch in antigravity-dynamic must block deletion.
        (agy_dir / "manager-health.json").write_text(
            json.dumps(
                {
                    "schema": "talk-antigravity-manager-health-1",
                    "pid": os.getpid(),
                    "seen_at": "2026-11-24T00:00:00+00:00",
                    "owned_launches": ["launch_busy"],
                }
            ),
            encoding="utf-8",
        )
        blocked = role_delete.cleanup(rt, member, receipt)
        self.assertEqual(blocked["outcome"], "failed")
        self.assertEqual(blocked["error_code"], "manager_not_stopped")
        self.assertTrue(agy_dir.exists())

        # Stopped dead manager with empty owned_launches allows clean removal while preserving sibling.
        (agy_dir / "manager-health.json").write_text(
            json.dumps(
                {
                    "schema": "talk-antigravity-manager-health-1",
                    "pid": 2147483000,
                    "seen_at": "2020-01-01T00:00:00+00:00",
                    "owned_launches": [],
                }
            ),
            encoding="utf-8",
        )
        done = role_delete.cleanup(rt, member, receipt)
        self.assertEqual(done["outcome"], "complete", done)
        self.assertFalse(agy_dir.exists())
        self.assertTrue((other_dir / "manager-health.json").is_file())

    @unittest.skipUnless(os.name == "nt", "Windows handle deletion")
    def test_workspace_v1_antigravity_spec_and_delete_cleanup(self):
        scratch = ROOT / ".tmp-tests"
        scratch.mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(prefix="talk-agy-ws-", dir=scratch)
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        data = base / "data"
        project = base / "project"
        keys = base / "keys"
        state = base / "state"
        for d_path in (data, project, keys, state):
            d_path.mkdir()
        exe = base / "agy.exe"
        exe.write_text("synthetic", encoding="utf-8")
        project_id, member = "prj_agy_ws", "agent:agy-ws"
        role = {
            "project_id": project_id,
            "member_id": member,
            "role_name": "Agy WS",
            "storage_layout": "workspace-v1",
            "archived": False,
            "binding_state": "bound",
            "runner": {"runtime": "antigravity", "status": "unverified"},
            "model": {"choice_id": "rmc_ws", "model_alias": "gemini-4-neon", "model_id": "gemini-4-neon"},
            "service": {
                "generation": 1,
                "ownership_held": False,
                "control_kind": "managed_cli",
                "current_launch": {"action": "start", "state": "pending"},
            },
        }
        config = {
            "project_id": project_id,
            "project_root": str(project),
            "state_dir": str(state),
            "key_root": str(keys),
            "hosts": [],
            "base_url": "http://127.0.0.1:1",
            "operator_key_file": str(base / "human.key"),
            "antigravity": {"enabled": True, "executable": str(exe), "task_profiles": {}},
        }
        cfg_path = base / "runtime.json"
        cfg_path.write_text(json.dumps(config), encoding="utf-8")
        key_file = wp.key_path(data, project_id, member, git_key_root=keys)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text("isolated-agy-ws-key\n", encoding="utf-8")
        meta = provision.credential_metadata_path(key_file.parent, member)
        meta.write_text(json.dumps({"member_id": member}), encoding="utf-8")

        class WsClient:
            def request(inner, method, path, body=None, **kwargs):
                if path == "/api/members/me":
                    return {"id": member, "kind": "agent", "display_name": "Agy WS"}
                if path == f"/api/projects/{project_id}":
                    return {"project_id": project_id, "project_root_path": str(project)}
                if path == f"/api/projects/{project_id}/roles":
                    return [role]
                if path == f"/api/projects/{project_id}/role-storage-layouts":
                    return [{"member_id": member, "storage_layout": "workspace-v1"}]
                raise AssertionError(path)

        rt = runtime.TalkRuntime(deepcopy(config), client=WsClient(), config_path=cfg_path)
        with patch.object(runtime, "ROOT", data):
            spec = rt.antigravity_spec(role)
        self.assertIsNotNone(spec)
        self.assertEqual(spec["workspace_context"]["runner"], "antigravity")
        self.assertEqual(
            Path(spec["health_file"]),
            wp.manager_dir(data, project_id, member, "antigravity") / "manager-health.json",
        )

        # Workspace-v1 deletion removes state/manager/antigravity cleanly.
        mgr = wp.manager_dir(data, project_id, member, "antigravity")
        mgr.mkdir(parents=True, exist_ok=True)
        (mgr / "manager-health.json").write_text(
            json.dumps({"pid": 2147483000, "seen_at": "2020-01-01T00:00:00+00:00", "owned_launches": []}),
            encoding="utf-8",
        )
        receipt = {
            "identity_disabled": True,
            "credential_digest": hashlib.sha256(b"isolated-agy-ws-key").hexdigest(),
        }
        with patch.object(runtime, "ROOT", data):
            done = role_delete.cleanup(rt, member, receipt, role=role)
        self.assertEqual(done["outcome"], "complete", done)
        self.assertFalse(mgr.exists())

    def test_portable_bootstrap_seeds_antigravity_and_recipe(self):
        fake_agy = self.root / ("agy.exe" if os.name == "nt" else "agy")
        fake_agy.write_text("synthetic", encoding="utf-8")
        with patch.object(setup, "find_antigravity_executable", return_value=str(fake_agy)):
            recipes = portable_bootstrap.runner_recipes()
        self.assertEqual(
            recipes.get("antigravity"),
            {"enabled": True, "executable": str(fake_agy.resolve()), "task_profiles": {}},
        )
        db_path = self.root / "portable.db"
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        try:
            SQLModel.metadata.create_all(engine)
            with Session(engine) as session:
                admin = type("Admin", (), {"id": "human:operator"})()
                portable_bootstrap.seed_runners(session, admin, "prj_p")
            with closing(sqlite3.connect(db_path)) as conn:
                runner = conn.execute(
                    "select runner_id, runtime, display_name, control_kind from runner_registry where runner_id=?",
                    ("runner:antigravity-local",),
                ).fetchall()
                models = conn.execute(
                    "select model_id, model_alias, model_display_name, provider_id, connection_ref, capabilities "
                    "from runner_model_choices where runner_id=? order by model_id",
                    ("runner:antigravity-local",),
                ).fetchall()
        finally:
            engine.dispose()
        self.assertEqual(runner, [("runner:antigravity-local", "antigravity", "Antigravity CLI", "managed_cli")])
        self.assertEqual(
            [(m[0], m[1], m[2], m[3], m[4], json.loads(m[5])) for m in models],
            [
                (
                    "gemini-4-carbon",
                    "gemini-4-carbon",
                    "Gemini 4 Carbon",
                    "google-antigravity",
                    "native-antigravity-login",
                    ["effort:low", "effort:medium", "effort:high", "effort_default:high"],
                ),
                (
                    "gemini-4-hydrogen",
                    "gemini-4-hydrogen",
                    "Gemini 4 Hydrogen",
                    "google-antigravity",
                    "native-antigravity-login",
                    ["effort:low", "effort:medium", "effort:high", "effort:xhigh", "effort_default:high"],
                ),
                (
                    "gemini-4-neon",
                    "gemini-4-neon",
                    "Gemini 4 Neon",
                    "google-antigravity",
                    "native-antigravity-login",
                    ["effort:low", "effort:medium", "effort:high", "effort:xhigh", "effort_default:high"],
                ),
            ],
        )


class AntigravityRoleCreationApiTests(RouteTestCase):
    def _seed_project_and_choices(self):
        self.add_member("human:operator", api_key="human-key")
        with self.session() as session:
            session.add(
                Project(
                    project_id="prj_agy_create",
                    display_name="Agy Create",
                    maintainer_member_id="human:operator",
                )
            )
            session.commit()
            setup.seed_antigravity_choices(session, "human:operator")
            choices = {
                row.model_id: row.choice_id
                for row in session.exec(
                    select(RunnerModelChoice).where(RunnerModelChoice.runner_id == setup.RUNNER_ID)
                ).all()
            }
        return "prj_agy_create", {"X-API-Key": "human-key"}, choices

    def test_create_role_sets_default_effort_and_enforces_carbon_effort_bounds(self):
        project_id, headers, choices = self._seed_project_and_choices()
        with self.make_client() as client:
            carbon_resp = client.post(
                f"/api/projects/{project_id}/roles",
                headers=headers,
                json={
                    "operation_key": "op-agy-carbon-001",
                    "role_name": "Carbon Dev",
                    "runner_id": setup.RUNNER_ID,
                    "choice_id": choices["gemini-4-carbon"],
                },
            )
            self.assertEqual(carbon_resp.status_code, 201, carbon_resp.text)
            carbon_member = carbon_resp.json()["role"]["member_id"]

            binding_resp = client.get(
                f"/api/projects/{project_id}/agents/{carbon_member}/binding",
                headers=headers,
            )
            self.assertEqual(binding_resp.status_code, 200, binding_resp.text)
            binding = binding_resp.json()["binding"]
            self.assertEqual(binding["default_effort"], "high")
            self.assertEqual(binding["effective_effort"], "high")
            self.assertEqual(binding["effort_options"], ["low", "medium", "high"])
            self.assertEqual(binding["effort_source"], "adapter")

            # Carbon rejects xhigh on both PUT /binding/effort and POST /binding/default-effort.
            bad_override = client.put(
                f"/api/projects/{project_id}/roles/{carbon_member}/binding/effort",
                headers=headers,
                json={"effort": "xhigh"},
            )
            self.assertEqual(bad_override.status_code, 422)
            self.assertEqual(bad_override.json()["detail"], "effort_not_supported")

            bad_default = client.post(
                f"/api/projects/{project_id}/roles/{carbon_member}/binding/default-effort",
                headers=headers,
                json={"default_effort": "xhigh"},
            )
            self.assertEqual(bad_default.status_code, 422)
            self.assertEqual(bad_default.json()["detail"], "default_effort_invalid")

            ok_override = client.put(
                f"/api/projects/{project_id}/roles/{carbon_member}/binding/effort",
                headers=headers,
                json={"effort": "medium"},
            )
            self.assertEqual(ok_override.status_code, 200, ok_override.text)
            self.assertEqual(ok_override.json()["binding"]["effective_effort"], "medium")

            # Neon accepts xhigh.
            neon_resp = client.post(
                f"/api/projects/{project_id}/roles",
                headers=headers,
                json={
                    "operation_key": "op-agy-neon-001",
                    "role_name": "Neon Dev",
                    "runner_id": setup.RUNNER_ID,
                    "choice_id": choices["gemini-4-neon"],
                },
            )
            self.assertEqual(neon_resp.status_code, 201, neon_resp.text)
            neon_member = neon_resp.json()["role"]["member_id"]
            neon_xhigh = client.put(
                f"/api/projects/{project_id}/roles/{neon_member}/binding/effort",
                headers=headers,
                json={"effort": "xhigh"},
            )
            self.assertEqual(neon_xhigh.status_code, 200, neon_xhigh.text)
            self.assertEqual(neon_xhigh.json()["binding"]["effective_effort"], "xhigh")

            # Stale/corrupt DB supported_efforts containing xhigh on Carbon must still be clamped to 3 levels.
            with self.session() as session:
                carbon_binding = session.get(ProjectRoleBinding, (project_id, carbon_member))
                carbon_binding.supported_efforts = json.dumps(["low", "medium", "high", "xhigh"])
                session.add(carbon_binding)
                session.commit()
            clamped = client.put(
                f"/api/projects/{project_id}/roles/{carbon_member}/binding/effort",
                headers=headers,
                json={"effort": "xhigh"},
            )
            self.assertEqual(clamped.status_code, 422, clamped.text)
            self.assertEqual(clamped.json()["detail"], "effort_not_supported")

            # Rebinding via PUT /agents/{member}/binding initializes Antigravity default_effort="high",
            # and an unsupported Antigravity model returns 409 effort_capability_unknown on PUT /binding/effort.
            rebound = client.put(
                f"/api/projects/{project_id}/agents/{carbon_member}/binding",
                headers=headers,
                json={
                    "binding": {
                        "runner_id": setup.RUNNER_ID,
                        "model_source": "builtin",
                        "provider_id": setup.PROVIDER_ID,
                        "connection_ref": setup.CONNECTION_REF,
                        "model_id": "gemini-4-hydrogen",
                        "model_alias": "gemini-4-hydrogen",
                        "model_display_name": "Gemini 4 Hydrogen",
                    }
                },
            )
            self.assertEqual(rebound.status_code, 200, rebound.text)
            self.assertEqual(rebound.json()["binding"]["default_effort"], "high")
            self.assertEqual(rebound.json()["binding"]["effective_effort"], "high")

            unsupported_bind = client.put(
                f"/api/projects/{project_id}/agents/{carbon_member}/binding",
                headers=headers,
                json={
                    "binding": {
                        "runner_id": setup.RUNNER_ID,
                        "model_source": "builtin",
                        "provider_id": setup.PROVIDER_ID,
                        "connection_ref": setup.CONNECTION_REF,
                        "model_id": "claude-4-unsupported",
                        "model_alias": "claude-4-unsupported",
                        "model_display_name": "Unsupported",
                    }
                },
            )
            self.assertEqual(unsupported_bind.status_code, 200, unsupported_bind.text)
            self.assertEqual(unsupported_bind.json()["binding"]["effort_options"], [])
            self.assertIsNone(unsupported_bind.json()["binding"]["effort_source"])
            for method, path, body, expected_status in (
                ("PUT", f"/api/projects/{project_id}/roles/{carbon_member}/binding/effort", {"effort": "xhigh"}, 409),
                ("POST", f"/api/projects/{project_id}/roles/{carbon_member}/binding/default-effort", {"default_effort": "high"}, 409),
            ):
                resp = client.request(method, path, headers=headers, json=body)
                self.assertEqual(resp.status_code, expected_status, resp.text)
                self.assertEqual(resp.json()["detail"], "effort_capability_unknown")


if __name__ == "__main__":
    unittest.main()
