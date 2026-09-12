# -*- coding: utf-8 -*-
"""`scripts/talk_workflow.py` 的离线针对性测试。

覆盖：成功交付包、部分完成（本地清理好但 push 失败）、缺字段/矛盾字段、
超长文本与历史注入、摘要边界与 UTF-8 中文、深度嵌套 JSON 的短错误、
complete 与失败验证记录的自报矛盾、--expect-task-id 的任务号核对。

全程离线：不创建真实任务、不联网、不 push、不做长等待。
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "talk_workflow.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("talk_workflow", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses 解析字符串注解时需要模块已注册到 sys.modules。
    sys.modules["talk_workflow"] = module
    spec.loader.exec_module(module)
    return module


talk_workflow = _load_module()


def sample_report(**overrides):
    """一份可通过校验的 complete 交付包。"""
    data = {
        "task_id": "38",
        "conclusion": "complete",
        "completed": ["实现交付包校验与有界摘要", "补充离线测试"],
        "unfinished": [],
        "blocked": [],
        "changed_files": ["scripts/talk_workflow.py", "docs/guides/TASK_WORKFLOW.md"],
        "baseline": {"ref": "aa90682", "diff_note": "仅新增本地脚本、指南与测试，未改生产实现"},
        "verification": [
            {
                "check": "python -m unittest tests.test_talk_workflow",
                "result": "pass",
                "evidence": "全部用例通过，未联网",
            }
        ],
        "limitations": ["校验只覆盖格式与自报一致性，不代表业务验收通过"],
        "progress_draft": {"summary": "完成本地校验脚本与使用指南", "next": "等待独立复核"},
    }
    data.update(overrides)
    return data


def partial_report(**overrides):
    """#37 场景：本地清理好，但 push 失败，只能报 partial。"""
    data = sample_report(
        conclusion="partial",
        completed=["本地临时材料已清理，git status 干净"],
        unfinished=["push 到远端失败：凭据被拒，需人工确认后重试"],
        verification=[
            {"check": "git status --porcelain", "result": "pass", "evidence": "无输出"},
            {"check": "git push origin main", "result": "fail", "evidence": "远端拒绝，未重复重试"},
        ],
        progress_draft={"summary": "本地清理完成，推送未完成", "next": "等待人工确认凭据"},
    )
    data.update(overrides)
    return data


class CliMixin:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write_json(self, payload, name="report.json", encoding="utf-8"):
        path = self.tmpdir / name
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
        path.write_text(text, encoding=encoding)
        return path

    def write_bytes(self, raw: bytes, name="report.json"):
        path = self.tmpdir / name
        path.write_bytes(raw)
        return path

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = talk_workflow.main(argv)
        return code, out.getvalue(), err.getvalue()


class ValidReportTests(CliMixin, unittest.TestCase):
    def test_complete_report_passes(self):
        result = talk_workflow.validate_report(sample_report())
        self.assertTrue(result.ok, [issue.as_dict() for issue in result.errors])
        self.assertEqual([], result.errors)

    def test_partial_report_with_failed_push_passes(self):
        result = talk_workflow.validate_report(partial_report())
        self.assertTrue(result.ok, [issue.as_dict() for issue in result.errors])

    def test_blocked_report_allows_empty_completed(self):
        report = sample_report(
            conclusion="blocked",
            completed=[],
            blocked=["需要人工确认凭据后才能继续"],
            progress_draft={"summary": "本地完成，等待人工裁决", "next": "人工确认凭据"},
        )
        result = talk_workflow.validate_report(report)
        self.assertTrue(result.ok, [issue.as_dict() for issue in result.errors])

    def test_schema_covers_required_fixed_fields(self):
        required = {
            "task_id",
            "conclusion",
            "completed",
            "unfinished",
            "blocked",
            "changed_files",
            "baseline",
            "verification",
            "limitations",
            "progress_draft",
        }
        self.assertTrue(required.issubset(set(talk_workflow.TOP_LEVEL_FIELDS)))

    def test_cli_validate_exit_zero_and_no_report_body_echo(self):
        marker = "正文标记不得回显-ALPHA"
        report = sample_report(completed=[f"{marker}：实现校验脚本"])
        path = self.write_json(report)
        code, out, err = self.run_cli(["validate", str(path)])
        self.assertEqual(0, code)
        self.assertIn("OK", out)
        self.assertIn(path.name, out)
        self.assertNotIn(marker, out)
        self.assertEqual("", err)

    def test_cli_validate_json_mode(self):
        path = self.write_json(sample_report())
        code, out, _ = self.run_cli(["validate", str(path), "--json"])
        payload = json.loads(out)
        self.assertEqual(0, code)
        self.assertTrue(payload["ok"])
        self.assertEqual("talk-delivery-1", payload["schema"])


class FieldErrorTests(CliMixin, unittest.TestCase):
    def error_codes(self, report):
        result = talk_workflow.validate_report(report)
        return [(issue.field, issue.code) for issue in result.errors]

    def test_missing_conclusion_is_reported_by_name(self):
        report = sample_report()
        report.pop("conclusion")
        codes = self.error_codes(report)
        self.assertIn(("conclusion", "missing_field"), codes)

    def test_wrong_type_list(self):
        codes = self.error_codes(sample_report(completed="不是数组"))
        self.assertIn(("completed", "wrong_type"), codes)

    def test_too_many_items(self):
        codes = self.error_codes(sample_report(completed=[f"条目 {i}" for i in range(21)]))
        self.assertIn(("completed", "too_many_items"), codes)

    def test_changed_files_must_be_relative(self):
        codes = self.error_codes(sample_report(changed_files=["D:\\claude-test\\TALK\\scripts\\x.py"]))
        self.assertIn(("changed_files[0]", "not_relative_path"), codes)

    def test_unknown_nested_field_rejected(self):
        report = sample_report()
        report["verification"][0]["raw_log"] = "长日志"
        codes = self.error_codes(report)
        self.assertIn(("verification[0].raw_log", "unknown_field"), codes)

    def test_baseline_missing_key(self):
        report = sample_report(baseline={"ref": "aa90682"})
        codes = self.error_codes(report)
        self.assertIn(("baseline.diff_note", "missing_field"), codes)

    def test_conclusion_enum_rejects_succeeded(self):
        codes = self.error_codes(sample_report(conclusion="succeeded"))
        self.assertIn(("conclusion", "bad_enum"), codes)


class ContradictionTests(CliMixin, unittest.TestCase):
    def contradiction_fields(self, report):
        result = talk_workflow.validate_report(report)
        return [issue.field for issue in result.errors if issue.code == "contradiction"]

    def test_complete_with_unfinished_is_contradiction(self):
        report = sample_report(unfinished=["还有一项没做完"])
        self.assertFalse(talk_workflow.validate_report(report).ok)
        self.assertIn("conclusion", self.contradiction_fields(report))

    def test_complete_with_blocked_is_contradiction(self):
        report = sample_report(blocked=["被权限卡住"])
        self.assertFalse(talk_workflow.validate_report(report).ok)
        self.assertIn("conclusion", self.contradiction_fields(report))

    def test_complete_with_empty_completed_is_contradiction(self):
        report = sample_report(completed=[])
        self.assertIn("completed", self.contradiction_fields(report))

    def test_partial_without_unfinished_is_contradiction(self):
        report = partial_report(unfinished=[], blocked=[])
        self.assertIn("conclusion", self.contradiction_fields(report))

    def test_blocked_without_blocked_items_is_contradiction(self):
        report = sample_report(conclusion="blocked", blocked=[], unfinished=["x"])
        self.assertIn("blocked", self.contradiction_fields(report))

    def test_cli_returns_one_and_names_field(self):
        path = self.write_json(sample_report(unfinished=["没做完"]))
        code, out, _ = self.run_cli(["validate", str(path)])
        self.assertEqual(1, code)
        self.assertIn("FAIL", out)
        self.assertIn("conclusion", out)


class InjectionAndSecretTests(CliMixin, unittest.TestCase):
    def test_unknown_field_rejected_and_content_not_echoed(self):
        injected = "原任务正文：" + "很长的历史内容" * 40
        report = sample_report()
        report["task_text"] = injected
        path = self.write_json(report)
        code, out, _ = self.run_cli(["validate", str(path)])
        self.assertEqual(1, code)
        self.assertIn("task_text", out)
        self.assertNotIn("很长的历史内容", out)
        self.assertNotIn(injected[:20], out)

    def test_runner_succeeded_does_not_imply_complete(self):
        report = sample_report()
        report.pop("conclusion")
        report["status"] = "succeeded"
        path = self.write_json(report)
        code, out, _ = self.run_cli(["validate", str(path)])
        self.assertEqual(1, code)
        self.assertIn("status", out)
        self.assertIn("conclusion", out)
        self.assertNotIn("OK", out)

    def test_summary_ignores_non_allowlisted_keys(self):
        report = sample_report()
        report["hall_history"] = "不应出现在摘要里的历史消息"
        summary = talk_workflow.build_summary(report)
        self.assertNotIn("不应出现在摘要里的历史消息", summary["text"])

    def test_secret_is_redacted_in_summary(self):
        secret = "sk-live-abcdef1234567890"
        report = sample_report(limitations=[f"临时使用 api_key={secret} 调试"])
        summary = talk_workflow.build_summary(report)
        self.assertNotIn(secret, summary["text"])
        self.assertIn("[REDACTED]", summary["text"])
        self.assertGreaterEqual(summary["redactions"], 1)

    def test_secret_warning_names_field_without_value(self):
        secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        report = sample_report(limitations=[f"token={secret}"])
        result = talk_workflow.validate_report(report)
        self.assertTrue(result.ok)
        warning_text = " ".join(issue.message for issue in result.warnings)
        self.assertIn("疑似密钥", warning_text)
        self.assertNotIn(secret, warning_text)
        self.assertTrue(any("limitations" in issue.field for issue in result.warnings))


class SummaryBoundaryTests(CliMixin, unittest.TestCase):
    def big_report(self):
        return sample_report(
            conclusion="partial",
            completed=[f"已完成条目 {i}：" + "内容" * 140 for i in range(20)],
            unfinished=[f"未完成条目 {i}：" + "待办" * 140 for i in range(10)],
            blocked=["阻塞条目：" + "卡住" * 140],
            changed_files=[f"docs/sample_{i}.md" for i in range(50)],
            limitations=[f"限制 {i}" + "说明" * 120 for i in range(20)],
            verification=[
                {"check": f"检查项 {i}", "result": "pass", "evidence": "证据" * 140}
                for i in range(20)
            ],
        )

    def test_never_exceeds_limit_for_several_limits(self):
        report = self.big_report()
        for limit in (600, 700, 1200, 2000, 4000):
            summary = talk_workflow.build_summary(report, max_chars=limit)
            self.assertLessEqual(len(summary["text"]), limit, f"limit={limit}")
            self.assertEqual(len(summary["text"]), summary["chars"])
            self.assertEqual(limit, summary["limit"])

    def test_limit_is_clamped(self):
        report = sample_report()
        self.assertEqual(talk_workflow.MIN_SUMMARY_LIMIT, talk_workflow.build_summary(report, max_chars=10)["limit"])
        self.assertEqual(talk_workflow.MAX_SUMMARY_LIMIT, talk_workflow.build_summary(report, max_chars=99999)["limit"])

    def test_truncation_is_visible(self):
        summary = talk_workflow.build_summary(self.big_report(), max_chars=700)
        self.assertTrue(summary["truncated"])
        self.assertIn("[摘要截断", summary["text"])
        self.assertIn("已截断：是", summary["text"])

    def test_unfinished_items_are_not_silently_dropped(self):
        summary = talk_workflow.build_summary(self.big_report(), max_chars=600)
        text = summary["text"]
        self.assertTrue(
            "未完成条目 0" in text or "未完成" in text,
            "未完成项必须出现在摘要或被显式标注未展开",
        )
        self.assertIn("未完成", text)

    def test_section_item_cap_is_reported(self):
        summary = talk_workflow.build_summary(self.big_report(), max_chars=2000)
        self.assertIn("已完成", summary["text"])
        self.assertTrue(summary["truncated"])
        self.assertIn("未展开", summary["text"])

    def test_small_report_is_not_truncated(self):
        summary = talk_workflow.build_summary(sample_report())
        self.assertFalse(summary["truncated"])
        self.assertIn("已截断：否", summary["text"])
        self.assertEqual(0, summary["redactions"])

    def test_footer_reports_actual_length(self):
        for limit in (600, 1200):
            summary = talk_workflow.build_summary(self.big_report(), max_chars=limit)
            match = re.search(r"— 摘要 (\d+)/(\d+) 字符", summary["text"])
            self.assertIsNotNone(match)
            self.assertEqual(len(summary["text"]), int(match.group(1)))
            self.assertEqual(limit, int(match.group(2)))

    def test_cli_summary_utf8_chinese(self):
        report = partial_report(completed=["清理掉临时文件：中文标点、emoji 边界字符"])
        path = self.write_json(report)
        code, out, _ = self.run_cli(["summary", str(path)])
        self.assertEqual(0, code)
        self.assertIn("清理掉临时文件", out)
        self.assertIn("结论=partial", out)
        self.assertIn("未完成(1)", out)

    def test_cli_summary_json_mode(self):
        path = self.write_json(self.big_report())
        code, out, _ = self.run_cli(["summary", str(path), "--max-chars", "600", "--json"])
        payload = json.loads(out)
        self.assertEqual(0, code)
        self.assertTrue(payload["truncated"])
        self.assertLessEqual(payload["chars"], 600)

    def test_summary_refuses_invalid_report(self):
        path = self.write_json(sample_report(conclusion="complete", unfinished=["没做完"]))
        code, out, _ = self.run_cli(["summary", str(path)])
        self.assertEqual(1, code)
        self.assertIn("FAIL", out)
        self.assertNotIn("摘要 schema=", out)


class FileAndCliTests(CliMixin, unittest.TestCase):
    def test_missing_file_exit_two(self):
        code, _, err = self.run_cli(["validate", str(self.tmpdir / "nope.json")])
        self.assertEqual(2, code)
        self.assertIn("文件不存在", err)

    def test_non_utf8_file_exit_two(self):
        path = self.write_bytes("交付包".encode("gbk"))
        code, _, err = self.run_cli(["validate", str(path)])
        self.assertEqual(2, code)
        self.assertIn("UTF-8", err)

    def test_invalid_json_exit_two(self):
        path = self.write_json('{"task_id": "38", ')
        code, _, err = self.run_cli(["validate", str(path)])
        self.assertEqual(2, code)
        self.assertIn("JSON 解析失败", err)

    def test_oversized_file_exit_two(self):
        raw = json.dumps(sample_report()).encode("utf-8") + b" " * talk_workflow.MAX_REPORT_BYTES
        path = self.write_bytes(raw)
        code, _, err = self.run_cli(["validate", str(path)])
        self.assertEqual(2, code)
        self.assertIn("过大", err)

    def test_utf8_bom_is_tolerated(self):
        raw = ("\ufeff" + json.dumps(sample_report(), ensure_ascii=False)).encode("utf-8")
        path = self.write_bytes(raw)
        code, out, _ = self.run_cli(["validate", str(path)])
        self.assertEqual(0, code)
        self.assertIn("OK", out)

    def test_non_object_root_rejected(self):
        path = self.write_json([1, 2, 3])
        code, out, _ = self.run_cli(["validate", str(path)])
        self.assertEqual(1, code)
        self.assertIn("<root>", out)

    def test_module_has_no_third_party_or_project_imports(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in ("import yaml", "import fastapi", "import sqlmodel", "from server", "import requests"):
            self.assertNotIn(forbidden, source)


class DeepNestingTests(CliMixin, unittest.TestCase):
    """深度嵌套 JSON：必须转成短错误 + exit 2，不吐 traceback，也不回显原输入。"""

    DEPTH = 20000

    def deep_json(self):
        return "[" * self.DEPTH + "]" * self.DEPTH

    def assert_deep_error(self, err):
        self.assertIn("嵌套层级过深", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("RecursionError", err)
        self.assertNotIn("[[[", err)

    def test_load_report_converts_recursion_error(self):
        path = self.write_json(self.deep_json())
        with self.assertRaises(talk_workflow.WorkflowError) as ctx:
            talk_workflow.load_report(path)
        self.assertIn("嵌套层级过深", str(ctx.exception))

    def test_validate_exits_two_with_short_error(self):
        path = self.write_json(self.deep_json())
        self.assertLess(path.stat().st_size, talk_workflow.MAX_REPORT_BYTES)
        code, out, err = self.run_cli(["validate", str(path), "--expect-task-id", "40"])
        self.assertEqual(2, code)
        self.assertEqual("", out)
        self.assert_deep_error(err)

    def test_summary_exits_two_with_short_error(self):
        path = self.write_json(self.deep_json())
        code, out, err = self.run_cli(["summary", str(path), "--expect-task-id", "40"])
        self.assertEqual(2, code)
        self.assertEqual("", out)
        self.assert_deep_error(err)


class VerificationConsistencyTests(CliMixin, unittest.TestCase):
    """complete 是"本次交付可用"的自报结论，与自己的 fail 记录冲突；partial/blocked 仍可记录失败。"""

    def failing_verification(self):
        return [
            {"check": "python -m unittest tests.test_talk_workflow", "result": "pass", "evidence": "通过"},
            {"check": "python scripts/talk_workflow.py validate <包>", "result": "fail", "evidence": "脚本报字段错误"},
        ]

    def test_complete_with_failed_verification_is_contradiction(self):
        result = talk_workflow.validate_report(sample_report(verification=self.failing_verification()))
        self.assertFalse(result.ok)
        codes = [(issue.field, issue.code) for issue in result.errors]
        self.assertIn(("verification[1].result", "contradiction"), codes)

    def test_complete_with_not_run_verification_is_allowed(self):
        report = sample_report(
            verification=[
                {"check": "人工页面验收", "result": "not_run", "evidence": "属项目管理者验收范围，本片不做"}
            ]
        )
        result = talk_workflow.validate_report(report)
        self.assertTrue(result.ok, [issue.as_dict() for issue in result.errors])

    def test_partial_keeps_failed_verification(self):
        result = talk_workflow.validate_report(partial_report())
        self.assertTrue(result.ok, [issue.as_dict() for issue in result.errors])

    def test_blocked_keeps_failed_verification(self):
        report = sample_report(
            conclusion="blocked",
            completed=[],
            blocked=["需要人工确认凭据后才能继续"],
            verification=self.failing_verification(),
        )
        result = talk_workflow.validate_report(report)
        self.assertTrue(result.ok, [issue.as_dict() for issue in result.errors])

    def test_cli_complete_with_fail_exits_one_without_echo(self):
        marker = "正文标记不得回显-BETA"
        report = sample_report(
            completed=[f"{marker}：修复本地脚本"],
            verification=self.failing_verification(),
        )
        path = self.write_json(report)
        code, out, err = self.run_cli(["validate", str(path), "--expect-task-id", "38"])
        self.assertEqual(1, code)
        self.assertIn("verification[1].result", out)
        self.assertIn("自报矛盾", out)
        self.assertNotIn(marker, out)
        self.assertEqual("", err)

    def test_cli_summary_refuses_complete_with_fail(self):
        path = self.write_json(sample_report(verification=self.failing_verification()))
        code, out, _ = self.run_cli(["summary", str(path), "--expect-task-id", "38"])
        self.assertEqual(1, code)
        self.assertIn("FAIL", out)
        self.assertNotIn("摘要 schema=", out)


class ExpectTaskIdTests(CliMixin, unittest.TestCase):
    """--expect-task-id：匹配通过、不匹配退出 1 且短错误不吐报告，38 与 #38 等价。"""

    def test_normalize_helper(self):
        self.assertEqual("38", talk_workflow.normalize_task_id("38"))
        self.assertEqual("38", talk_workflow.normalize_task_id("#38"))
        self.assertEqual("38", talk_workflow.normalize_task_id("  #38 "))
        self.assertIsNone(talk_workflow.normalize_task_id("#"))
        self.assertIsNone(talk_workflow.normalize_task_id("   "))
        self.assertIsNone(talk_workflow.normalize_task_id(38))

    def test_validate_matching_task_id(self):
        path = self.write_json(sample_report())
        code, out, err = self.run_cli(["validate", str(path), "--expect-task-id", "38"])
        self.assertEqual(0, code)
        self.assertIn("OK", out)
        self.assertEqual("", err)

    def test_validate_accepts_hash_forms_both_ways(self):
        hash_path = self.write_json(sample_report(task_id="#38"), name="hash.json")
        code, _, err = self.run_cli(["validate", str(hash_path), "--expect-task-id", "38"])
        self.assertEqual(0, code, err)

        plain_path = self.write_json(sample_report(), name="plain.json")
        code, _, err = self.run_cli(["validate", str(plain_path), "--expect-task-id", "#38"])
        self.assertEqual(0, code, err)

    def test_summary_matching_task_id(self):
        path = self.write_json(sample_report())
        code, out, err = self.run_cli(["summary", str(path), "--expect-task-id", "38"])
        self.assertEqual(0, code, err)
        self.assertIn("task_id=38", out)
        self.assertIn("摘要 schema=", out)

    def test_validate_mismatch_exits_one_without_report_body(self):
        marker = "正文标记不得回显-GAMMA"
        report = sample_report(completed=[f"{marker}：本地改动"])
        path = self.write_json(report)
        code, out, err = self.run_cli(["validate", str(path), "--expect-task-id", "40"])
        self.assertEqual(1, code)
        self.assertIn("FAIL", out)
        self.assertIn("不是本次任务号 40", out)
        self.assertNotIn(marker, out)
        self.assertEqual("", err)

    def test_summary_mismatch_exits_one_without_summary(self):
        path = self.write_json(sample_report())
        code, out, _ = self.run_cli(["summary", str(path), "--expect-task-id", "40"])
        self.assertEqual(1, code)
        self.assertIn("FAIL", out)
        self.assertIn("不是本次任务号 40", out)
        self.assertNotIn("摘要 schema=", out)

    def test_mismatch_error_stays_visible_when_errors_are_truncated(self):
        report = sample_report()
        for index in range(12):
            report[f"extra_field_{index}"] = "额外字段"
        path = self.write_json(report)
        code, out, _ = self.run_cli(["validate", str(path), "--expect-task-id", "40"])
        self.assertEqual(1, code)
        self.assertIn("其余", out)
        self.assertIn("不是本次任务号 40", out)

    def test_missing_task_id_cannot_match_expectation(self):
        report = sample_report()
        report.pop("task_id")
        result = talk_workflow.validate_report(report, expect_task_id="40")
        codes = [(issue.field, issue.code) for issue in result.errors]
        self.assertIn(("task_id", "unexpected_task_id"), codes)
        self.assertIn(("task_id", "missing_field"), codes)

    def test_empty_expect_task_id_is_usage_error(self):
        path = self.write_json(sample_report())
        code, out, err = self.run_cli(["validate", str(path), "--expect-task-id", "   "])
        self.assertEqual(2, code)
        self.assertEqual("", out)
        self.assertIn("不能为空", err)
        self.assertNotIn("Traceback", err)

    def test_without_flag_still_works(self):
        for command in ("validate", "summary"):
            path = self.write_json(sample_report(), name=f"{command}.json")
            code, out, err = self.run_cli([command, str(path)])
            self.assertEqual(0, code, err)
            self.assertNotIn("expect-task-id", out)


if __name__ == "__main__":
    unittest.main()
