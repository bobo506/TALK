"""351-B 思考强度：公开绑定解析、执行命令改写、bridge 每任务重取（无模型调用）。"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr
import unittest

from bridges.codex_effort import (
    EFFORT_SOURCE_CONFIG,
    EFFORT_SOURCE_MODEL,
    EFFORT_SOURCE_USER,
    EffortUnavailable,
    apply_effort,
    resolve_binding_effort,
)


class ResolveBindingEffortTests(unittest.TestCase):
    def test_user_override_wins_and_reports_user_source(self):
        binding = {
            "effective_effort": "high",
            "effort_override": "high",
            "effort_options": ["low", "medium", "high"],
            "effort_source": "adapter",
        }
        self.assertEqual(resolve_binding_effort(binding, "xhigh"), ("high", EFFORT_SOURCE_USER))

    def test_model_default_is_used_when_no_user_override(self):
        binding = {
            "effective_effort": "low",
            "effort_override": None,
            "effort_options": ["low", "high"],
            "effort_source": "catalog",
        }
        self.assertEqual(resolve_binding_effort(binding, "xhigh"), ("low", EFFORT_SOURCE_MODEL))

    def test_old_service_without_new_fields_falls_back_to_native_config(self):
        self.assertEqual(resolve_binding_effort({}, "xhigh"), ("xhigh", EFFORT_SOURCE_CONFIG))
        self.assertEqual(
            resolve_binding_effort({"default_effort": "low"}, "xhigh"),
            ("xhigh", EFFORT_SOURCE_CONFIG),
        )

    def test_old_service_without_valid_fallback_is_rejected(self):
        with self.assertRaises(EffortUnavailable) as caught:
            resolve_binding_effort({}, None)
        self.assertEqual(caught.exception.reason, "codex_effort_unsupported")
        with self.assertRaises(EffortUnavailable):
            resolve_binding_effort({}, "ultra")

    def test_effective_outside_adapter_set_is_rejected(self):
        with self.assertRaises(EffortUnavailable) as caught:
            resolve_binding_effort({"effective_effort": "ultra"}, "xhigh")
        self.assertEqual(caught.exception.reason, "codex_effort_unsupported")

    def test_effective_outside_reported_options_is_rejected(self):
        binding = {
            "effective_effort": "medium",
            "effort_override": "medium",
            "effort_options": ["low", "high"],
            "effort_source": "catalog",
        }
        with self.assertRaises(EffortUnavailable) as caught:
            resolve_binding_effort(binding, "xhigh")
        self.assertEqual(caught.exception.reason, "codex_effort_unsupported")

    def test_user_override_without_capability_source_is_rejected(self):
        # 有覆盖值却没有任何可校验清单：不把“无法校验”当成“可以执行”。
        with self.assertRaises(EffortUnavailable) as caught:
            resolve_binding_effort({"effective_effort": "high", "effort_override": "high"}, "xhigh")
        self.assertEqual(caught.exception.reason, "codex_effort_capability_unknown")
        with self.assertRaises(EffortUnavailable) as caught:
            resolve_binding_effort(
                {"effective_effort": "high", "effort_override": "high", "effort_options": []}, "xhigh"
            )
        self.assertEqual(caught.exception.reason, "codex_effort_capability_unknown")

    def test_override_with_options_but_missing_source_is_rejected(self):
        binding = {"effective_effort": "high", "effort_override": "high", "effort_options": ["high"]}
        with self.assertRaises(EffortUnavailable) as caught:
            resolve_binding_effort(binding, "xhigh")
        self.assertEqual(caught.exception.reason, "codex_effort_capability_unknown")


class ApplyEffortTests(unittest.TestCase):
    CONFIG_COMMAND = 'codex -c \'model_reasoning_effort="xhigh"\' -'

    def test_config_form_is_rewritten_with_json_literal(self):
        rewritten, mode = apply_effort(self.CONFIG_COMMAND, "high")
        self.assertEqual(mode, "config")
        self.assertIn('model_reasoning_effort="high"', rewritten)
        self.assertNotIn('"xhigh"', rewritten)
        # 其余部分逐字符保持，避免改写 Windows 路径或其它参数。
        self.assertTrue(rewritten.startswith("codex -c "))

    def test_list_form_is_rewritten_by_token(self):
        command = ["codex", "-c", 'model_reasoning_effort="xhigh"', "-"]
        rewritten, mode = apply_effort(command, "low")
        self.assertEqual(mode, "config")
        self.assertEqual(rewritten, ["codex", "-c", 'model_reasoning_effort="low"', "-"])

    def test_legacy_flag_form_is_rewritten(self):
        rewritten, mode = apply_effort(
            "python native_driver.py --mode task --model gpt-6.1-sol --effort xhigh", "low"
        )
        self.assertEqual(mode, "flag")
        self.assertTrue(rewritten.endswith("--effort low"))

    def test_unrecognized_command_is_left_unchanged(self):
        command = "codex exec --model x -"
        self.assertEqual(apply_effort(command, "high"), (command, "unchanged"))

    def test_invalid_effort_is_rejected(self):
        with self.assertRaises(EffortUnavailable):
            apply_effort(self.CONFIG_COMMAND, "ultra")


class FakeClient:
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.calls = []

    async def _request_json(self, method, path, **kwargs):
        self.calls.append((method, path))
        if self.error is not None:
            raise self.error
        return self.rows


class ResolveTaskEffortTests(unittest.IsolatedAsyncioTestCase):
    def binding(self, **overrides):
        value = {
            "runtime": "codex",
            "effective_effort": "high",
            "effort_override": "high",
            "effort_options": ["low", "high"],
            "effort_source": "adapter",
        }
        value.update(overrides)
        return value

    async def test_reads_public_binding_for_current_member(self):
        from bridges.codex_bridge import resolve_task_effort

        client = FakeClient([{"member_id": "agent:x", "binding": self.binding()}])
        effort = await resolve_task_effort(client, {"project_id": "prj_1"}, "agent:x")
        self.assertEqual(effort, "high")
        self.assertEqual(client.calls, [("GET", "/api/projects/prj_1/agents")])

    async def test_old_service_without_effective_field_keeps_baked_value(self):
        from bridges.codex_bridge import resolve_task_effort

        client = FakeClient([{"member_id": "agent:x", "binding": {"default_effort": "low"}}])
        self.assertIsNone(await resolve_task_effort(client, {"project_id": "prj_1"}, "agent:x"))

    async def test_missing_member_or_ambiguous_rows_are_ignored(self):
        from bridges.codex_bridge import resolve_task_effort

        for rows in ([], [{"member_id": "agent:y", "binding": self.binding()}],
                     [{"member_id": "agent:x", "binding": self.binding()},
                      {"member_id": "agent:x", "binding": self.binding()}]):
            self.assertIsNone(await resolve_task_effort(FakeClient(rows), {"project_id": "p"}, "agent:x"))

    async def test_lookup_failure_is_diagnosed_and_does_not_break_the_task(self):
        from bridges.codex_bridge import resolve_task_effort

        stream = io.StringIO()
        with redirect_stderr(stream):
            effort = await resolve_task_effort(FakeClient(error=OSError("boom")), {"project_id": "p"}, "agent:x")
        self.assertIsNone(effort)
        self.assertEqual(stream.getvalue().strip(), "[Codex bridge] codex_effort_lookup_failed")

    async def test_unknown_capability_is_diagnosed(self):
        from bridges.codex_bridge import resolve_task_effort

        binding = self.binding(effort_options=[], effort_source=None)
        stream = io.StringIO()
        with redirect_stderr(stream):
            effort = await resolve_task_effort(
                FakeClient([{"member_id": "agent:x", "binding": binding}]), {"project_id": "p"}, "agent:x"
            )
        self.assertIsNone(effort)
        self.assertEqual(stream.getvalue().strip(), "[Codex bridge] codex_effort_capability_unknown")

    async def test_rewriting_the_command_changes_the_execution_identity(self):
        # 执行会话语义依赖命令指纹：改写强度必须改变命令文本，才能触发既有 taint/new_session 规则。
        from bridges.codex_bridge import handle_queued_task  # noqa: F401  （导入即证明无循环依赖）
        original = 'codex -c \'model_reasoning_effort="xhigh"\' -'
        rewritten, mode = apply_effort(original, "high")
        self.assertEqual(mode, "config")
        self.assertNotEqual(original, rewritten)


if __name__ == "__main__":
    unittest.main()
