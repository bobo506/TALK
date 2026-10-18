"""271首次交付的独立复核反例；仅临时文件与假凭据。"""
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridges import cli_bridge, runtime_diagnostics as rd


class RuntimeDiagnosticsReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.diag = rd.RuntimeDiagnostics(member_id="agent:test", instance_id="ins_test", root=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def raw(self):
        return "\n".join(p.read_text(encoding="utf-8") for p in self.root.rglob("events-*.jsonl"))

    def test_cli_summary_redacts_full_multiline_prompt_before_splitting(self):
        prompt = "PRIVATE_PROMPT_MARKER_271_" + "x" * 700 + "\nsecond private line"
        result = cli_bridge.CliRunResult(returncode=1, stdout="", stderr=prompt)
        cli_bridge._record_cli_failure(self.diag, result, stage="task_cli", task_id=271,
            timeout=10, client=object(), sensitive_values=(prompt,))
        self.assertNotIn("PRIVATE_PROMPT_MARKER_271_", self.raw())

    def test_subprocess_exception_never_serializes_cmd_or_output(self):
        prompt = "SUBPROCESS_PRIVATE_271\nsecret instruction"
        exc = subprocess.CalledProcessError(2, ["fake", "--prompt", prompt], output="PRIVATE_OUTPUT")
        self.diag.record_exception(exc)
        self.assertNotIn("SUBPROCESS_PRIVATE_271", self.raw())
        self.assertNotIn("PRIVATE_OUTPUT", self.raw())

    def test_exception_chain_carries_sensitive_values_to_outer_boundary(self):
        prompt = "NESTED_PRIVATE_271\nsecond instruction"
        try:
            try:
                inner = RuntimeError("command: " + repr(prompt))
                inner.diagnostic_sensitive_values = (prompt,)
                raise inner
            except RuntimeError as inner:
                raise ValueError("outer boundary") from inner
        except ValueError as outer:
            self.diag.record_exception(outer)
        self.assertNotIn("NESTED_PRIVATE_271", self.raw())

    def test_closed_stderr_cannot_turn_log_failure_into_product_failure(self):
        class BrokenStream(io.StringIO):
            def write(self, text):
                raise OSError("closed console")
        with patch.object(self.diag, "_append_locked", side_effect=OSError("disk unavailable")):
            with patch("sys.stderr", BrokenStream()):
                self.assertIsNone(self.diag.record_exception(RuntimeError("original failure")))

    def test_query_stops_enumerating_when_file_budget_is_reached(self):
        count = []
        path = self.root / "events-fake.jsonl"
        path.write_text("", encoding="utf-8")
        def inventory(root, **kwargs):
            for _ in range(20):
                count.append(1)
                yield path
        with patch.object(rd, "_iter_log_files", inventory):
            result = rd.query_records(self.root, max_files=2)
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(count), 3)

    def test_chain_limit_is_explicit_in_default_integrity(self):
        exc = RuntimeError("root")
        for _ in range(rd.MAX_CHAIN_DEPTH + 1):
            outer = RuntimeError("outer")
            outer.__cause__ = exc
            exc = outer
        ref = self.diag.record_exception(exc)
        record = rd.query_records(self.root, ref=ref)["records"][0]
        self.assertTrue(record["integrity"]["truncated"])
        self.assertIn("exception.cause_chain", record["integrity"]["truncated_fields"])

    def test_quoted_whitespace_and_owner_tokens_are_redacted(self):
        text = "password='white space private value'; owner_token=owner-opaque-private"
        safe = rd.sanitize_text(text)
        self.assertNotIn("white space private value", safe)
        self.assertNotIn("owner-opaque-private", safe)


if __name__ == "__main__":
    unittest.main()
