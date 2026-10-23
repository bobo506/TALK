"""Isolated contracts for the metadata-only maintenance entry."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest import mock

from scripts import runtime_log_inventory as audit


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "logs"
        self.run = self.root / "agent-one" / "ins-one" / "run-one"
        self.run.mkdir(parents=True)
        self.now = datetime(2026, 10, 23, tzinfo=timezone.utc)

    def put(self, name, content=b"fixture-secret", days=45, run=None):
        path = (run or self.run) / name
        path.write_bytes(content)
        stamp = self.now.timestamp() - days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def read(self, **kwargs):
        return audit.inventory(self.root, now=self.now, **kwargs)

    def snapshot(self):
        return {str(p.relative_to(self.root)): (hashlib.sha256(p.read_bytes()).hexdigest(),
                p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}

    def test_only_older_segments_flagged_never_deletable(self):
        self.put("events-00001.jsonl", b"a" * 30)
        self.put("events-00002.jsonl", b"b" * 40)
        for name in ("manifest.json", "retention.jsonl", "rotation.jsonl"):
            self.put(name, b"c" * 10)
        result = self.read(max_total_bytes=50)
        self.assertEqual(result["scan"]["status"], "complete")
        self.assertEqual(result["observed"]["bytes"], 100)
        self.assertEqual(result["proposal_only"]["over_capacity_bytes"], 50)
        review = result["age_review"]
        self.assertEqual(review["older_segment_bytes"], 30)
        self.assertEqual(review["latest_segment_bytes_excluded"], 40)
        self.assertEqual(review["eligible_for_deletion_bytes"], 0)
        self.assertFalse(review["closed_run_verified"])

    def test_no_content_reads_no_writes_and_all_fixture_bytes_unchanged(self):
        self.put("events-00001.jsonl")
        self.put("events-00002.jsonl")
        self.put("manifest.json", b"not even valid JSON")
        before = self.snapshot()
        with mock.patch("builtins.open", side_effect=AssertionError("content read")), \
             mock.patch.object(Path, "open", side_effect=AssertionError("content read")), \
             mock.patch("os.open", side_effect=AssertionError("write/open")), \
             mock.patch.object(Path, "unlink", side_effect=AssertionError("delete")):
            result = self.read()
        self.assertEqual(before, self.snapshot())
        self.assertNotIn("fixture-secret", json.dumps(result))

    def test_missing_root_is_unknown_not_zero_capacity(self):
        result = audit.inventory(self.root / "missing", now=self.now)
        self.assertEqual(result["scan"]["status"], "missing")
        self.assertIsNone(result["observed"]["bytes"])
        self.assertIsNone(result["proposal_only"]["over_capacity_bytes"])
        self.assertFalse((self.root / "missing").exists())

    def test_unreadable_directory_is_partial(self):
        original = os.scandir
        def scan(path):
            if Path(path) == self.run:
                raise PermissionError("must not echo this")
            return original(path)
        with mock.patch("os.scandir", side_effect=scan):
            result = self.read()
        self.assertEqual(result["scan"]["status"], "partial")
        self.assertIn("entry_unavailable_or_changed", result["scan"]["reasons"])
        self.assertNotIn("must not echo this", json.dumps(result))

    def test_root_reparse_rejected_before_enumeration(self):
        original = Path.lstat
        def lstat(path):
            if path == self.root:
                return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original(path)
        with mock.patch.object(Path, "lstat", lstat), \
             mock.patch("os.scandir", side_effect=AssertionError("unsafe scan")):
            result = self.read()
        self.assertEqual(result["scan"]["status"], "unavailable")

    def test_nested_reparse_is_not_traversed(self):
        original = Path.lstat
        def lstat(path):
            if path == self.run:
                return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original(path)
        with mock.patch.object(Path, "lstat", lstat):
            result = self.read()
        self.assertEqual(result["scan"]["links_skipped"], 1)
        self.assertEqual(result["scan"]["status"], "partial")

    def test_entry_and_time_limits_report_partial(self):
        self.put("events-00001.jsonl")
        result = self.read(max_entries=1)
        self.assertEqual(result["scan"]["status"], "partial")
        self.assertIn("entry_limit", result["scan"]["reasons"])
        with mock.patch("time.monotonic", side_effect=[0, 10]):
            result = self.read(max_seconds=1)
        self.assertIn("time_limit", result["scan"]["reasons"])

    def test_future_files_not_flagged_and_old_mtime_does_not_prove_closed(self):
        self.put("events-00001.jsonl", days=-1)
        self.put("events-00002.jsonl", days=100)
        result = self.read()
        self.assertEqual(result["scan"]["future_mtime_files"], 1)
        self.assertEqual(result["age_review"]["older_segment_files"], 0)
        self.assertEqual(result["age_review"]["eligible_for_deletion_bytes"], 0)

    def test_all_runs_counted_and_preview_bounded(self):
        for i in range(4):
            run = self.run.parent / ("run-" + str(i))
            run.mkdir()
            self.put("events-00001.jsonl", run=run)
            self.put("events-00002.jsonl", run=run)
        result = self.read(preview_limit=2)
        self.assertEqual(result["observed"]["runs"], 4)
        self.assertEqual(len(result["age_review"]["preview"]), 2)
        self.assertTrue(result["age_review"]["preview_truncated"])

    def test_metadata_traces_and_other_files_not_age_candidates(self):
        self.put("events-00001.jsonl")
        self.put("events-00002.jsonl")
        self.put("retention.jsonl")
        self.put("private.key")
        nested = self.run / "unexpected"
        nested.mkdir()
        (nested / "events-00001.jsonl").write_bytes(b"not scanned")
        result = self.read()
        self.assertEqual(result["observed"]["by_kind"]["other"]["files"], 1)
        self.assertEqual(result["age_review"]["older_segment_files"], 1)
        self.assertEqual(result["scan"]["status"], "partial")
        self.assertNotIn("private.key", json.dumps(result))

    def test_directory_replacement_detected(self):
        original = audit._chain
        calls = 0
        def chain(path):
            nonlocal calls
            value = original(path)
            if path == self.run:
                calls += 1
                if calls >= 3:
                    value = (*value[:-1], (str(path), 999, 999, stat.S_IFDIR))
            return value
        self.put("events-00001.jsonl")
        with mock.patch.object(audit, "_chain", side_effect=chain):
            result = self.read()
        self.assertIn("directory_changed", result["scan"]["reasons"])

    def test_invalid_policies_rejected(self):
        cases = [{"retention_days": float("nan")}, {"retention_days": -1},
                 {"max_total_bytes": True}, {"max_entries": 0},
                 {"max_seconds": float("inf")}, {"preview_limit": 101},
                 {"now": datetime(2026, 1, 1)}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                audit.inventory(self.root, **case)

    def test_cli_json_and_exit_codes(self):
        self.put("events-00001.jsonl")
        for root, expected in ((self.root, 0), (self.root / "missing", 2)):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = audit.main(["--log-dir", str(root)])
            self.assertEqual(code, expected)
            self.assertEqual(json.loads(out.getvalue())["mode"], "metadata_only_no_deletion")

    def test_blank_roots_rejected_before_scan_but_explicit_dot_allowed(self):
        for root in ("", " ", "\t\r\n", "\x00"):
            with self.subTest(root=repr(root)), \
                 mock.patch("os.scandir", side_effect=AssertionError("unexpected scan")):
                with self.assertRaises(ValueError):
                    audit.inventory(root)
                with contextlib.redirect_stderr(io.StringIO()), \
                     self.assertRaises(SystemExit) as error:
                    audit.main(["--log-dir", root])
                self.assertEqual(error.exception.code, 2)
        previous = os.getcwd()
        try:
            os.chdir(self.root)
            self.assertEqual(audit.inventory(".")["scan"]["status"], "complete")
        finally:
            os.chdir(previous)

    def test_real_ntfs_ancient_mtime_and_numeric_sort(self):
        older = self.put("events-00001.jsonl", b"one")
        oldest = self.put("events-00002.jsonl", b"two")
        self.put("events-00003.jsonl")
        for path, year in ((older, 1900), (oldest, 1601)):
            # FILETIME zero (1601-01-01 exactly) means 'leave unchanged' in
            # Windows APIs. Use the next day and verify the real fixture time.
            stamp = (datetime(year, 1, 2, tzinfo=timezone.utc) - audit.EPOCH).total_seconds()
            os.utime(path, (stamp, stamp))
            self.assertEqual(path.stat().st_mtime_ns, int(stamp * 10**9))
        result = self.read()
        self.assertEqual(result["scan"]["status"], "complete")
        preview = result["age_review"]["preview"]
        self.assertEqual([p["modified_at"][:4] for p in preview], ["1601", "1900"])
        self.assertLess(preview[0]["modified_ns"], preview[1]["modified_ns"])
        self.assertEqual(result["age_review"]["mtime_unavailable_files"], 0)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(audit.main(["--log-dir", str(self.root)]), 0)
        self.assertEqual(json.loads(out.getvalue())["scan"]["status"], "complete")

    def test_unrepresentable_mtime_keeps_counts_and_partial_json(self):
        older = self.put("events-00001.jsonl", b"one")
        self.put("events-00002.jsonl", b"two")
        original = Path.lstat
        impossible_ns = -(10**30)
        def lstat(path):
            if path == older:
                return types.SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0,
                                             st_size=3, st_mtime_ns=impossible_ns)
            return original(path)
        with mock.patch.object(Path, "lstat", lstat):
            result = self.read()
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = audit.main(["--log-dir", str(self.root)])
        self.assertEqual(result["scan"]["status"], "partial")
        self.assertIn("mtime_format_unavailable", result["scan"]["reasons"])
        self.assertEqual(result["observed"]["bytes"], 6)
        self.assertEqual(result["age_review"]["mtime_unavailable_files"], 1)
        self.assertIsNone(result["age_review"]["preview"][0]["modified_at"])
        self.assertEqual(result["age_review"]["preview"][0]["modified_ns"], impossible_ns)
        self.assertEqual(result["age_review"]["eligible_for_deletion_bytes"], 0)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["scan"]["status"], "partial")

    def test_single_ancient_latest_segment_never_formatted(self):
        path = self.put("events-00001.jsonl")
        stamp = (datetime(1601, 1, 2, tzinfo=timezone.utc) - audit.EPOCH).total_seconds()
        os.utime(path, (stamp, stamp))
        self.assertEqual(path.stat().st_mtime_ns, int(stamp * 10**9))
        with mock.patch.object(audit, "_mtime_text", side_effect=AssertionError("latest")):
            result = self.read()
        self.assertEqual(result["scan"]["status"], "complete")
        self.assertEqual(result["age_review"]["older_segment_files"], 0)

    def test_mtime_formatter_edges_without_crt_timestamp_conversion(self):
        for value in (datetime(1601, 1, 1, tzinfo=timezone.utc),
                      datetime(1900, 1, 1, tzinfo=timezone.utc),
                      datetime.max.replace(tzinfo=timezone.utc)):
            delta = value - audit.EPOCH
            ns = ((delta.days * 86400 + delta.seconds) * 10**6 + delta.microseconds) * 1000
            self.assertEqual(audit._mtime_text(ns), value.isoformat())
        self.assertIsNone(audit._mtime_text(10**30))

    def test_real_writer_namespace_and_reference_preserved(self):
        from bridges.runtime_diagnostics import DiagnosticsPolicy, RuntimeDiagnostics
        writer = RuntimeDiagnostics(member_id="agent:fixture", instance_id="ins_fixture",
                                    policy=DiagnosticsPolicy.create(root=self.root),
                                    clock=lambda: self.now)
        reference = writer.record_event("bridge_started", stage="bridge")
        before = self.snapshot()
        result = self.read()
        self.assertEqual(result["scan"]["status"], "complete")
        self.assertEqual(result["observed"]["by_kind"]["events"]["files"], 1)
        self.assertEqual(result["observed"]["by_kind"]["manifest"]["files"], 1)
        self.assertEqual(before, self.snapshot())
        from bridges.runtime_diagnostics import query_records
        self.assertEqual(query_records(self.root, ref=reference)["records"][0]["log_id"],
                         reference)
        writer.close()


if __name__ == "__main__":
    unittest.main()
