import ctypes
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from server import workspace_diagnostics as wd
from server.workspace_paths import WorkspacePathError, is_within


def marker(root, project_id="project-a"):
    (root / ".talk").mkdir()
    (root / ".talk" / "project.yaml").write_text("project_id: " + project_id + "\n", encoding="utf-8")


def snapshot(root):
    entries = [root] + sorted(root.rglob("*"))
    return [(str(p.relative_to(root)), p.lstat().st_size, p.lstat().st_mtime_ns) for p in entries]


class WorkspaceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "root"
        self.root.mkdir()

    def test_root_states_and_errors(self):
        self.assertEqual(wd.inspect_root(self.root)["status"], "ok")
        self.assertEqual(wd.inspect_root(self.base / "missing")["status"], "missing")
        f = self.base / "file"
        f.write_text("x", encoding="utf-8")
        self.assertEqual(wd.inspect_root(f)["status"], "invalid")
        self.assertEqual(wd.inspect_root("relative")["status"], "invalid")
        self.assertEqual(wd.inspect_root(None)["status"], "unconfigured")
        for exc in (PermissionError(13, "secret"), OSError(110, "secret"), OSError("secret")):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(Path, "stat", side_effect=exc):
                got = wd.inspect_root(self.root)
                self.assertEqual(got["status"], "inaccessible")
                self.assertNotIn("secret", str(got))
        with mock.patch.object(wd, "_identity", return_value=None):
            got = wd.inspect_root(self.root)
            self.assertEqual(got["status"], "ok")
            self.assertIsNone(got["identity"])
            self.assertEqual(got["issues"][0]["code"], "workspace_identity_unknown")

    def test_marker_parsing_and_rejection(self):
        self.assertFalse(wd.inspect_root(self.root)["marker"]["exists"])
        marker(self.root)
        self.assertEqual(wd.inspect_root(self.root)["marker"], {"exists": True, "project_id": "project-a", "parseable": True})
        f = self.root / ".talk" / "project.yaml"
        for text in ("project_id: [", "project_id: a\nproject_id: b\n", "project_id: !!python/object:bad {}\n"):
            f.write_text(text, encoding="utf-8")
            got = wd.inspect_root(self.root)["marker"]
            self.assertTrue(got["exists"])
            self.assertFalse(got["parseable"])

    def test_duplicates_and_unknown(self):
        other = self.base / "other"
        other.mkdir()
        alias = self.root / ".." / "root"
        result = wd.detect_duplicates([("a", self.root), ("b", alias), ("c", other)])
        self.assertEqual(result["duplicates"], [{"code": "workspace_duplicate", "project_ids": ["a", "b"]}])
        self.assertEqual(result["unknown"], [])
        with mock.patch.object(wd, "_identity", side_effect=[wd.inspect_root(self.root)["identity"], None]):
            result = wd.detect_duplicates([("a", self.root), ("b", other)])
        self.assertEqual(result["duplicates"], [])
        self.assertEqual(result["unknown"], ["b"])

    def test_move_identity_and_markers(self):
        marker(self.root)
        old = wd.inspect_root(self.root)
        new = self.base / "renamed"
        self.root.rename(new)
        self.assertEqual(wd.evaluate_move(old, new)["code"], "workspace_move_candidate")
        copy = self.base / "copy"
        shutil.copytree(new, copy)
        self.assertEqual(wd.evaluate_move(old, copy)["code"], "marker_only")
        (copy / ".talk" / "project.yaml").write_text("project_id: different\n", encoding="utf-8")
        self.assertEqual(wd.evaluate_move(old, copy)["code"], "workspace_marker_conflict")
        (copy / ".talk" / "project.yaml").write_text("project_id: project-a\n", encoding="utf-8")
        old["identity"] = None
        self.assertEqual(wd.evaluate_move(old, copy)["code"], "workspace_identity_unverified")

    def test_no_side_effects(self):
        marker(self.root)
        (self.root / "nested").mkdir()
        (self.root / "nested" / "data").write_text("abc", encoding="utf-8")
        bare = self.base / "bare"
        bare.mkdir()
        before = {str(p): snapshot(p) for p in (self.root, bare)}
        old = wd.inspect_root(self.root)
        wd.inspect_root(bare)
        wd.detect_duplicates([("a", self.root), ("b", bare)])
        wd.evaluate_move(old, self.root)
        after = {str(p): snapshot(p) for p in (self.root, bare)}
        self.assertEqual(before, after)
        self.assertFalse((bare / ".talk").exists())

    def test_symlink_identity_but_marker_guard(self):
        marker(self.root)
        alias = self.base / "alias"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + type(exc).__name__)
        got = wd.detect_duplicates([("a", self.root), ("b", alias)])
        self.assertEqual(got["duplicates"][0]["project_ids"], ["a", "b"])
        self.assertIsNone(wd.inspect_root(alias)["marker"]["exists"])
        with self.assertRaises(WorkspacePathError) as exc:
            is_within(alias / "anything", self.base)
        self.assertEqual(exc.exception.code, "link_refused")

    def test_marker_symlink_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "project.yaml").write_text("project_id: outside\n", encoding="utf-8")
        try:
            (self.root / ".talk").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + type(exc).__name__)
        self.assertIsNone(wd.inspect_root(self.root)["marker"]["project_id"])

    @unittest.skipUnless(os.name == "nt", "Windows junction requires Windows")
    def test_windows_junction(self):
        alias = self.base / "junction"
        process = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(self.root)], capture_output=True)
        if process.returncode:
            self.skipTest("junction creation unsupported")
        self.addCleanup(lambda: os.rmdir(alias) if alias.exists() else None)
        self.assertEqual(wd.detect_duplicates([("a", self.root), ("b", alias)])["duplicates"][0]["project_ids"], ["a", "b"])
        with mock.patch.object(wd.os, "open", side_effect=AssertionError("marker read through junction")):
            self.assertIsNone(wd.inspect_root(alias)["marker"]["exists"])
        with self.assertRaises(WorkspacePathError):
            is_within(alias, self.base)

    @unittest.skipUnless(os.name == "nt", "Windows case aliases require Windows")
    def test_windows_case_alias(self):
        self.assertTrue(wd.detect_duplicates([("a", self.root), ("b", str(self.root).swapcase())])["duplicates"])

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 requires Windows")
    def test_windows_short_name(self):
        root = self.base / "long workspace name for short path"
        root.mkdir()
        get_short = ctypes.windll.kernel32.GetShortPathNameW
        buf = ctypes.create_unicode_buffer(32768)
        length = get_short(str(root), buf, len(buf))
        if not length or length >= len(buf) or os.path.normcase(buf.value) == os.path.normcase(str(root)):
            self.skipTest("8.3 short name unavailable on this volume")
        self.assertTrue(wd.detect_duplicates([("a", root), ("b", buf.value)])["duplicates"])


if __name__ == "__main__":
    unittest.main()
