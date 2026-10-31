"""351-D：Kimi 受管强度写入（纯函数 + 原子替换 + 逐任务钩子）。"""
from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridges import kimi_effort
from bridges.kimi_effort import (
    apply_role_config_effort,
    resolve_target_effort,
    set_model_default_effort,
)

CONFIG = """[providers."managed:kimi-code"]
token = "KEEP_ME"

[models."kimi-code/k3.1-pro"]
provider = "managed:kimi-code"
model = "k3.1-pro"
max_context_size = 1000000
support_efforts = ["medium", "high"]
default_effort = "high"

[models."kimi-code/other"]
provider = "managed:kimi-code"
model = "other"
default_effort = "low"
"""


class ResolveTargetEffortTests(unittest.TestCase):
    def test_user_override_wins(self):
        binding = {
            "effective_effort": "max",
            "effort_override": "max",
            "effort_options": ["medium", "max"],
            "effort_source": "catalog",
        }
        self.assertEqual(resolve_target_effort(binding), "max")

    def test_model_default_is_used_without_override(self):
        binding = {
            "effective_effort": "high",
            "effort_override": None,
            "effort_options": ["medium", "high"],
            "effort_source": "catalog",
        }
        self.assertEqual(resolve_target_effort(binding), "high")

    def test_old_service_and_unknown_capability_are_skipped(self):
        self.assertIsNone(resolve_target_effort({}))
        self.assertIsNone(resolve_target_effort({"default_effort": "high"}))
        self.assertIsNone(
            resolve_target_effort({"effective_effort": "high", "effort_override": "high"})
        )

    def test_value_outside_reported_options_is_skipped(self):
        binding = {
            "effective_effort": "ultra",
            "effort_override": "ultra",
            "effort_options": ["medium", "high"],
            "effort_source": "catalog",
        }
        self.assertIsNone(resolve_target_effort(binding))


class SetModelDefaultEffortTests(unittest.TestCase):
    def test_replaces_only_the_target_model_key(self):
        text, mode = set_model_default_effort(CONFIG, "kimi-code/k3.1-pro", "medium")
        self.assertEqual(mode, "replace")
        self.assertIn('default_effort = "medium"', text)
        self.assertIn('token = "KEEP_ME"', text)
        self.assertIn('default_effort = "low"', text)  # 其它模型段不受影响
        self.assertEqual(text.count("default_effort"), 2)

    def test_inserts_when_key_missing_and_keeps_other_lines(self):
        without = CONFIG.replace('default_effort = "high"\n', "", 1)
        text, mode = set_model_default_effort(without, "kimi-code/k3.1-pro", "xhigh")
        self.assertEqual(mode, "insert")
        self.assertIn('default_effort = "xhigh"', text)
        self.assertIn('support_efforts = ["medium", "high"]', text)

    def test_missing_model_section_is_rejected(self):
        with self.assertRaises(ValueError):
            set_model_default_effort(CONFIG, "kimi-code/absent", "high")

    def test_invalid_effort_is_rejected(self):
        with self.assertRaises(ValueError):
            set_model_default_effort(CONFIG, "kimi-code/k3.1-pro", "turbo")


class ApplyRoleConfigEffortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="talk-kimi-effort-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.toml"
        self.path.write_text(CONFIG, encoding="utf-8")

    def test_atomic_write_changes_value(self):
        mode = apply_role_config_effort(self.path, "kimi-code/k3.1-pro", "medium")
        self.assertEqual(mode, "replace")
        text = self.path.read_text(encoding="utf-8")
        self.assertIn('default_effort = "medium"', text)
        self.assertNotIn('default_effort = "high"', text)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ["config.toml"])

    def test_same_value_is_unchanged_and_not_rewritten(self):
        before = self.path.stat().st_mtime_ns
        self.assertEqual(
            apply_role_config_effort(self.path, "kimi-code/k3.1-pro", "high"), "unchanged"
        )
        self.assertEqual(self.path.stat().st_mtime_ns, before)


class FakeClient:
    def __init__(self, binding):
        self.binding = binding

    async def _request_json(self, method, path, **kwargs):
        from bridges.cli_bridge import member_id_from_name

        return {"data": [{"member_id": member_id_from_name("kimi"), "binding": self.binding}]}


class EffortHookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="talk-kimi-hook-")
        self.addCleanup(self.temp.cleanup)
        home = Path(self.temp.name)
        (home / "config.toml").write_text(CONFIG, encoding="utf-8")
        self.home = home
        self.args = argparse.Namespace(
            name="kimi",
            project_id="prj_1",
            kimi_model="kimi-code/k3.1-pro",
        )

    def hook(self, binding):
        from bridges.kimi_bridge import make_effort_hook

        return make_effort_hook(FakeClient(binding), self.args)

    def test_hook_writes_effective_effort_before_task(self):
        from bridges.kimi_bridge import make_effort_hook

        binding = {
            "effective_effort": "max",
            "effort_override": "max",
            "effort_options": ["medium", "max"],
            "effort_source": "catalog",
        }
        with patch.dict(os.environ, {"KIMI_CODE_HOME": str(self.home)}):
            asyncio.run(make_effort_hook(FakeClient(binding), self.args)({"id": 1}))
        text = (self.home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('default_effort = "max"', text)

    def test_hook_keeps_config_when_service_reports_nothing(self):
        with patch.dict(os.environ, {"KIMI_CODE_HOME": str(self.home)}):
            asyncio.run(self.hook({})({"id": 1}))
        text = (self.home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('default_effort = "high"', text)

    def test_hook_without_role_home_is_a_noop(self):
        binding = {"effective_effort": "max", "effort_override": "max",
                   "effort_options": ["max"], "effort_source": "catalog"}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KIMI_CODE_HOME", None)
            asyncio.run(self.hook(binding)({"id": 1}))
        self.assertIn('default_effort = "high"',
                      (self.home / "config.toml").read_text(encoding="utf-8"))


class BeforeTaskWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_unregistered_hook_is_a_noop(self):
        from bridges.cli_bridge import run_before_task

        await run_before_task(argparse.Namespace(), {})  # 不抛异常

    async def test_sync_and_async_hooks_are_both_supported(self):
        from bridges.cli_bridge import run_before_task

        seen = []
        await run_before_task(argparse.Namespace(before_task=lambda task: seen.append(task["id"])), {"id": 7})
        self.assertEqual(seen, [7])

        async def hook(task):
            seen.append(task["id"])

        await run_before_task(argparse.Namespace(before_task=hook), {"id": 8})
        self.assertEqual(seen, [7, 8])


if __name__ == "__main__":
    unittest.main()
