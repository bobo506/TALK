"""DSH 角色 patch 的启动前结构化校验（2026-11-01 小d 启动失败回归）。

事故口径：遗留 DeepSeek 宿主按「整份文本与确认基线逐字节相等」做启动门槛，而同一份
patch 又被产品逐任务写入 ``reasoningEffort``；强度从 ``max`` 改成 ``low`` 后角色再也
起不来（``deepseek_native_patch_changed``）。修复后的门槛只认确认过的模型事实，
本文件锁定该口径。
"""
from __future__ import annotations

import unittest

from bridges.dsh_patch import (
    CONFIRMED_MODEL,
    CONFIRMED_PROVIDER,
    MODEL_ROW_ID,
    PatchStructureError,
    parse_patch_rows,
    patch_problem,
)

# 小d 确认时的真实基线形态（注释头 + 两个列表项 + 两级嵌套）。
CONFIRMED = """# 原角色模型与推理强度由用户确认；不内联凭据。
- id: agent-default-model
  config:
    provider: deepseek-official
    model: deepseek-flash
- id: llm-deepseek
  config:
    reasoningEffort: max
"""


def with_effort(value: str) -> str:
    return CONFIRMED.replace("reasoningEffort: max", "reasoningEffort: %s" % value)


class PatchProblemTests(unittest.TestCase):
    def test_confirmed_patch_passes(self):
        self.assertIsNone(patch_problem(CONFIRMED))

    def test_every_open_effort_passes(self):
        # 强度由 TALK 按绑定逐任务写入，四档都不能再挡启动。
        for value in ("off", "low", "high", "max"):
            self.assertIsNone(patch_problem(with_effort(value)), value)

    def test_cosmetic_changes_pass(self):
        # 注释、行尾、引号、行内注释与字段顺序都只是书写差异。
        self.assertIsNone(patch_problem(CONFIRMED.replace("# 原角色", "# 手写备注：原角色")))
        self.assertIsNone(patch_problem(CONFIRMED.replace("\n", "\r\n")))
        self.assertIsNone(patch_problem(CONFIRMED.replace("model: deepseek-flash", "model: 'deepseek-flash'")))
        self.assertIsNone(patch_problem(with_effort("max").replace("reasoningEffort: max", "reasoningEffort: max  # 手改")))
        reordered = CONFIRMED.replace(
            "  config:\n    provider: deepseek-official\n    model: deepseek-flash\n",
            "  config:\n    model: deepseek-flash\n    provider: deepseek-official\n",
        )
        self.assertIsNone(patch_problem(reordered))

    def test_provider_or_model_change_is_refused(self):
        for old, new in (
            ("provider: deepseek-official", "provider: openai"),
            ("model: deepseek-flash", "model: deepseek-pro"),
        ):
            problem = patch_problem(CONFIRMED.replace(old, new))
            self.assertIsInstance(problem, str, new)
            self.assertIn("确认值", problem, new)
        self.assertIn(CONFIRMED_PROVIDER, patch_problem(CONFIRMED.replace("provider: deepseek-official", "provider: openai")))
        self.assertIn(CONFIRMED_MODEL, patch_problem(CONFIRMED.replace("model: deepseek-flash", "model: deepseek-pro")))

    def test_missing_or_unknown_effort_is_refused(self):
        missing = CONFIRMED.replace("    reasoningEffort: max\n", "")
        self.assertIn("reasoningEffort", patch_problem(missing))
        self.assertIn("档位", patch_problem(with_effort("ultra")))

    def test_scalar_or_missing_config_is_refused(self):
        # 空值会被解析成映射：config 是标量、或整段缺失时都不能当成通过。
        scalar = patch_problem(CONFIRMED.replace("  config:\n    provider", "  config: ignored\n    provider"))
        self.assertIn("结构无法识别", scalar)
        missing = patch_problem(
            CONFIRMED.replace(
                "- id: agent-default-model\n  config:\n    provider: deepseek-official\n    model: deepseek-flash\n",
                "- id: agent-default-model\n",
            )
        )
        self.assertIn("缺少 config 映射", missing)

    def test_duplicate_or_missing_sections_are_refused(self):
        duplicate = CONFIRMED + "- id: %s\n  config:\n    provider: deepseek-official\n    model: deepseek-flash\n" % MODEL_ROW_ID
        self.assertIn("实际 2 个", patch_problem(duplicate))
        self.assertIn("llm-deepseek 段", patch_problem(CONFIRMED.replace("- id: llm-deepseek", "- id: llm-other")))
        self.assertIn("agent-default-model 段", patch_problem(CONFIRMED.replace("- id: agent-default-model", "- id: agent-other")))

    def test_structure_errors_fail_closed_without_raising(self):
        samples = (
            "",
            "llm-deepseek:\n  config:\n    reasoningEffort: max\n",
            "not: [a, list\n",
            "- id: agent-default-model\n\tconfig:\n\t\tprovider: deepseek-official\n",
            "- id: agent-default-model\n  config:\n    provider: deepseek-official\n        model: deepseek-flash\n",
        )
        for text in samples:
            problem = patch_problem(text)
            self.assertIsInstance(problem, str, repr(text))
            self.assertTrue(problem, repr(text))


class ParseRowsTests(unittest.TestCase):
    def test_rows_keep_two_level_nesting(self):
        rows = parse_patch_rows(CONFIRMED)
        self.assertEqual([row["id"] for row in rows], [MODEL_ROW_ID, "llm-deepseek"])
        self.assertEqual(rows[0]["config"]["provider"], "deepseek-official")
        self.assertEqual(rows[1]["config"]["reasoningEffort"], "max")

    def test_extra_rows_and_keys_are_allowed(self):
        extra = CONFIRMED + "- id: probe\n  config:\n    keep: value\n"
        self.assertIsNone(patch_problem(extra))

    def test_tab_indentation_is_refused(self):
        with self.assertRaises(PatchStructureError):
            parse_patch_rows("- id: x\n\tconfig:\n\t\tprovider: y\n")


if __name__ == "__main__":
    unittest.main()
