"""326：全入口默认执行时限24小时的跨入口一致性检查。

只验证真实 parser、真实受管配方的 argv 以及随包模板，不等待 24 小时、不调用
真实模型、不访问生产 HTTP、不写任何运行时状态。导入放在各用例内部，便于在
受限隔离环境里按组执行。
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMEOUT = 86400
TEMPLATES = {
    "codex": "codex exec --model {model}",
    "dsh": "dsh --model {model}",
    "cli": "cli --model {model}",
}


def _bridge_cases():
    from bridges import (
        cli_bridge,
        codex_bridge,
        kimi_bridge,
        pi_bridge,
        workbuddy_bridge,
    )

    return (
        ("generic/dsh", cli_bridge.build_parser(), ["--command", "controlled-cli"]),
        (
            "codex",
            codex_bridge.build_parser(),
            ["--codex-command", "controlled-codex"],
        ),
        ("pi", pi_bridge.build_parser(), []),
        ("kimi-code", kimi_bridge.build_parser(), []),
        (
            "workbuddy",
            workbuddy_bridge.build_parser(),
            ["--workbuddy-model", "controlled-model"],
        ),
    )


class BridgeParserDefaultsTests(unittest.TestCase):
    def test_real_bridge_parsers_default_to_24_hours(self):
        for label, parser, argv in _bridge_cases():
            with self.subTest(label=label):
                self.assertEqual(parser.parse_args(argv).timeout, DEFAULT_TIMEOUT)

    def test_explicit_timeout_is_still_preserved(self):
        for label, parser, argv in _bridge_cases():
            with self.subTest(label=label):
                parsed = parser.parse_args(argv + ["--timeout", "600"])
                self.assertEqual(parsed.timeout, 600)


class ManagedRecipeDefaultsTests(unittest.TestCase):
    def test_every_builtin_recipe_emits_exactly_one_24_hour_timeout(self):
        from scripts import role_service_host as host

        self.assertEqual(
            sorted(host.RUNTIME_RECIPES),
            ["cli", "codex", "dsh", "kimi-code", "workbuddy"],
        )
        for runtime in sorted(host.RUNTIME_RECIPES):
            with self.subTest(runtime=runtime):
                kwargs = {"model_alias": "controlled-model"}
                if runtime in TEMPLATES:
                    kwargs["command_template"] = TEMPLATES[runtime]
                argv = host.build_runtime_argv(runtime, **kwargs)
                self.assertEqual(argv.count("--timeout"), 1)
                self.assertEqual(
                    argv[argv.index("--timeout") + 1], str(DEFAULT_TIMEOUT)
                )
                fingerprint = host.verify_runtime_entry(runtime, argv)
                self.assertTrue(
                    fingerprint.startswith(
                        host.RUNTIME_RECIPES[runtime].module + "@"
                    )
                )

    def test_explicit_override_reaches_the_real_parser(self):
        from scripts import role_service_host as host

        argv = host.build_runtime_argv(
            "dsh",
            model_alias="controlled-model",
            command_template=TEMPLATES["dsh"],
            execution_timeout=43200,
        )
        self.assertEqual(argv.count("--timeout"), 1)
        self.assertEqual(argv[argv.index("--timeout") + 1], "43200")
        self.assertTrue(host.verify_runtime_entry("dsh", argv))


class K28DefaultsAndTemplatesTests(unittest.TestCase):
    def test_k28_defaults_and_budget_contract(self):
        from scripts import kimi_k28_executor as k28

        self.assertEqual(k28.EXECUTION_TIMEOUT_SECONDS, DEFAULT_TIMEOUT)
        parser = k28.build_parser()
        for mode in ("check", "render", "launch"):
            with self.subTest(mode=mode):
                self.assertEqual(parser.parse_args([mode]).timeout, DEFAULT_TIMEOUT)
        argv = k28.build_bridge_argv(project_root=PROJECT_ROOT)
        self.assertEqual(argv[argv.index("--timeout") + 1], str(DEFAULT_TIMEOUT))
        rendered = k28.render_launch(project_root=PROJECT_ROOT, environ={})
        bridge_argv = rendered["bridge_argv"]
        self.assertEqual(
            bridge_argv[bridge_argv.index("--timeout") + 1], str(DEFAULT_TIMEOUT)
        )
        budget = k28.budget_contract()
        self.assertEqual(
            budget["bridge_execution_timeout_seconds"]["value"], DEFAULT_TIMEOUT
        )

    def test_shipped_templates_and_deploy_example_are_24_hours(self):
        contract = json.loads(
            (
                PROJECT_ROOT / "deploy/kimi-code/k28-executor.contract.template.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            contract["runner"]["execution_timeout_seconds"], DEFAULT_TIMEOUT
        )
        self.assertEqual(
            contract["budget"]["bridge_execution_timeout_seconds"]["value"],
            DEFAULT_TIMEOUT,
        )
        launch = (
            PROJECT_ROOT / "deploy/kimi-code/k28-executor.launch.template.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(f"$TimeoutSeconds = {DEFAULT_TIMEOUT}", launch)
        example = json.loads(
            (PROJECT_ROOT / "deploy/bridges.example.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [bridge["timeout"] for bridge in example["bridges"]],
            [DEFAULT_TIMEOUT, DEFAULT_TIMEOUT],
        )


class UnrelatedWaitBudgetTests(unittest.TestCase):
    def test_mcp_wait_budget_stays_at_600_seconds(self):
        from bridges import talk_task_tools

        self.assertEqual(talk_task_tools.WAIT_DEFAULT_TIMEOUT_SECONDS, 600.0)
        self.assertEqual(talk_task_tools.WAIT_MAX_TIMEOUT_SECONDS, 600.0)


if __name__ == "__main__":
    unittest.main()
