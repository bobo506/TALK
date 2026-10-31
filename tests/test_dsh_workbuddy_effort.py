"""351-E/F：DSH patch 强度写入与 WorkBuddy 逐任务 --effort（隔离、无模型调用）。"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridges import dsh_effort
from bridges.dsh_effort import apply_patch_effort, resolve_open_effort, set_patch_effort
from bridges.workbuddy_bridge import build_command, read_model_reasoning

PATCH = """llm-deepseek:
  config:
    model: deepseek-flash
    reasoningEffort: max
other:
  keep: value
"""


class DshPatchTests(unittest.TestCase):
    def test_replaces_only_the_effort_line(self):
        text, mode = set_patch_effort(PATCH, "max")
        self.assertEqual(mode, "replace")
        self.assertIn("reasoningEffort: max", text)
        self.assertIn("keep: value", text)
        self.assertIn("model: deepseek-flash", text)
        self.assertEqual(text.count("reasoningEffort"), 1)

    def test_missing_line_is_refused_instead_of_inserting(self):
        with self.assertRaises(ValueError):
            set_patch_effort("other:\n  keep: value\n", "max")

    def test_all_observed_values_are_open_and_unknown_are_refused(self):
        # 用户确认：off/low/high/max 四档全部开放；集合外的值一律拒绝。
        for value in ("off", "low", "high", "max"):
            self.assertEqual(dsh_effort.normalize_effort(value), value)
            self.assertIn("reasoningEffort: %s" % value, set_patch_effort(PATCH, value)[0])
        with self.assertRaises(ValueError):
            set_patch_effort(PATCH, "ultra")

    def test_open_effort_needs_catalog_option(self):
        self.assertEqual(resolve_open_effort({"effective_effort": "max", "effort_options": ["max"]}), "max")
        self.assertEqual(resolve_open_effort({"effective_effort": "low", "effort_options": ["low", "max"]}), "low")
        self.assertIsNone(resolve_open_effort({"effective_effort": "ultra", "effort_options": ["ultra"]}))
        self.assertIsNone(resolve_open_effort({}))

    def test_atomic_write_and_unchanged(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "model-x.patch.yml"
            path.write_text(PATCH, encoding="utf-8")
            self.assertEqual(apply_patch_effort(path, "max"), "unchanged")
            before = path.stat().st_mtime_ns
            self.assertEqual(apply_patch_effort(path, "max"), "unchanged")
            self.assertEqual(path.stat().st_mtime_ns, before)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["model-x.patch.yml"])


class DshHookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / "model-dsh.patch.yml").write_text(PATCH, encoding="utf-8")
        self.args = argparse.Namespace(name="dsh", project_id="prj_1")

    async def run_hook(self, binding):
        from bridges.dsh_bridge import make_effort_hook

        class Client:
            async def _request_json(self, method, path, **kwargs):
                from bridges.cli_bridge import member_id_from_name

                return {"data": [{"member_id": member_id_from_name("dsh"), "binding": binding}]}

        with patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}):
            await make_effort_hook(Client(), self.args)({"id": 1})
        return (self.home / "model-dsh.patch.yml").read_text(encoding="utf-8")

    async def test_hook_writes_open_effort(self):
        text = await self.run_hook({"effective_effort": "max", "effort_options": ["max"]})
        self.assertIn("reasoningEffort: max", text)

    async def test_hook_writes_any_open_level_and_skips_unknown(self):
        text = await self.run_hook({"effective_effort": "off", "effort_options": ["off", "low", "high", "max"]})
        self.assertIn("reasoningEffort: off", text)
        text = await self.run_hook({})
        self.assertIn("reasoningEffort: off", text)  # 未知时保持原样


class DshRecipeTests(unittest.TestCase):
    def test_dsh_recipe_uses_dedicated_bridge(self):
        from scripts.role_service_host import RUNTIME_RECIPES

        recipe = RUNTIME_RECIPES["dsh"]
        self.assertEqual(recipe.module, "bridges.dsh_bridge")
        self.assertEqual(recipe.argv, ("{python}", "-m", "bridges.dsh_bridge"))


class WorkBuddyCatalogTests(unittest.TestCase):
    def models_json(self, name):
        path = Path(name) / "models.json"
        path.write_text(json.dumps([
            {"id": "deepseek-flash", "supportsReasoning": True,
             "reasoning": {"defaultEffort": "max", "supportedEfforts": ["high", "max"]}},
            {"id": "k3.1-pro", "supportsReasoning": True,
             "reasoning": {"defaultEffort": "max", "supportedEfforts": ["low", "high", "max"]}},
        ]), encoding="utf-8")
        return path

    def test_reads_official_default_and_supported(self):
        with tempfile.TemporaryDirectory() as name:
            self.models_json(name)
            data = read_model_reasoning(Path(name), "custom-local:deepseek-flash")
            self.assertEqual(data["default"], "max")
            self.assertEqual(data["supported"], ["high", "max"])
            self.assertTrue(data["supports_reasoning"])
            self.assertIsNone(read_model_reasoning(Path(name), "custom-local:absent"))

    def test_command_carries_effort_before_prompt_flag(self):
        executable = Path("C:/fake/WorkBuddy.exe")
        command = build_command(executable, "custom-local:deepseek-flash", tools="default", effort="max")
        self.assertIn("--effort", command)
        self.assertEqual(command[command.index("--effort") + 1], "max")
        self.assertLess(command.index("--effort"), command.index("-p"))
        without = build_command(executable, "custom-local:deepseek-flash", tools="default")
        self.assertNotIn("--effort", without)


class WorkBuddyHookTests(unittest.IsolatedAsyncioTestCase):
    def args(self):
        return argparse.Namespace(
            name="workbuddy", project_id="prj_1",
            task_command=["WorkBuddy.exe", "codebuddy", "--model", "custom-local:deepseek-flash", "-p"],
        )

    async def run_hook(self, binding):
        from bridges.workbuddy_bridge import make_effort_hook

        class Client:
            async def _request_json(self, method, path, **kwargs):
                from bridges.cli_bridge import member_id_from_name

                return {"data": [{"member_id": member_id_from_name("workbuddy"), "binding": binding}]}

        args = self.args()
        await make_effort_hook(Client(), args)({"id": 1})
        return args.task_command

    async def test_hook_rewrites_effort_for_next_task(self):
        command = await self.run_hook(
            {"effective_effort": "high", "effort_options": ["high", "max"], "effort_source": "catalog"}
        )
        self.assertEqual(command[command.index("--effort") + 1], "high")

    async def test_hook_skips_when_capability_unknown(self):
        command = await self.run_hook({})
        self.assertNotIn("--effort", command)


if __name__ == "__main__":
    unittest.main()
