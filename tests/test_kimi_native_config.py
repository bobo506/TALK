"""Kimi Code 角色 ``config.toml`` 的结构化启动校验（2026-11-02）。

口径与 DeepSeek patch 一致：只校验与绑定一致的 ``provider``/``model``；
``default_effort`` 由 TALK 按绑定逐任务写入，**不参与**校验。这样改强度永远不会
把角色挡在启动之外（对照 2026-11-01 小d 的整份字节比对事故）。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridges.kimi_native_config import (
    KimiConfigError,
    config_problem,
    read_config_text,
)

ALIAS = "kimi-code/k3.1-pro"
MODEL_ID = "k3.1-pro"
PROVIDER_ID = "managed:kimi-code"

CONFIG = """[providers."managed:kimi-code"]
kind = "managed"

[models."kimi-code/k3.1-pro"]
provider = "managed:kimi-code"
model = "k3.1-pro"
default_effort = "high"
max_context_size = 1000000

[models."kimi-code/other"]
provider = "managed:kimi-code"
model = "other"
default_effort = "max"
"""


def check(text: str) -> str | None:
    return config_problem(text, ALIAS, MODEL_ID, PROVIDER_ID)


class ConfigProblemTests(unittest.TestCase):
    def test_confirmed_config_passes(self):
        self.assertIsNone(check(CONFIG))

    def test_effort_changes_never_block_startup(self):
        # 事故回归：产品按绑定改强度，启动门槛必须继续放行。
        for value in ("off", "low", "high", "max"):
            text = CONFIG.replace('default_effort = "high"', 'default_effort = "%s"' % value)
            self.assertIsNone(check(text), value)
        without = CONFIG.replace('default_effort = "high"\n', "")
        self.assertIsNone(check(without))

    def test_cosmetic_differences_pass(self):
        self.assertIsNone(check(CONFIG.replace("\n", "\r\n")))
        self.assertIsNone(check(CONFIG.replace('model = "k3.1-pro"', 'model = "k3.1-pro"  # hand edit')))
        # 兼容键 name（官方历史配置两种写法都出现过）。
        named = CONFIG.replace('model = "k3.1-pro"', 'name = "k3.1-pro"')
        self.assertIsNone(check(named))

    def test_provider_or_model_drift_is_refused(self):
        provider = check(CONFIG.replace('provider = "managed:kimi-code"', 'provider = "other"', 1))
        self.assertIn("provider", provider)
        model = check(CONFIG.replace('model = "k3.1-pro"', 'model = "k3"'))
        self.assertIn("model", model)
        self.assertIn(MODEL_ID, model)

    def test_missing_section_or_field_is_refused(self):
        self.assertIn(ALIAS, check(CONFIG.replace('[models."kimi-code/k3.1-pro"]', '[models."kimi-code/absent"]')))
        self.assertIn("model", check(CONFIG.replace('model = "k3.1-pro"\n', "")))

    def test_undeclared_provider_is_refused(self):
        undeclared = CONFIG.replace('[providers."managed:kimi-code"]', '[providers."managed:other"]')
        self.assertIn("providers", check(undeclared))

    def test_broken_toml_fails_closed_without_raising(self):
        for text in ("", "[models.\n", "models = 3\n", 'models = {"kimi-code/k3.1-pro" = "x"}\n'):
            problem = check(text)
            self.assertIsInstance(problem, str, repr(text))
            self.assertTrue(problem, repr(text))


class ReadConfigTests(unittest.TestCase):
    def test_reads_utf8_and_enforces_size_limit(self):
        with tempfile.TemporaryDirectory(prefix="talk-kimi-config-") as name:
            path = Path(name) / "config.toml"
            path.write_text(CONFIG, encoding="utf-8")
            self.assertEqual(read_config_text(path), CONFIG)
            with self.assertRaises(KimiConfigError):
                read_config_text(path, max_bytes=10)
            with self.assertRaises(FileNotFoundError):
                read_config_text(Path(name) / "absent.toml")


if __name__ == "__main__":
    unittest.main()
