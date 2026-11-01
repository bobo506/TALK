import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "talk_review_pretest.py"


def run(args, root):
    command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT), "--repo", str(root), *args]
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class ReviewPretestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "review-pretest@example.invalid")
        git(self.root, "config", "user.name", "Review Pretest")
        (self.root / "tracked.txt").write_text("one\n", encoding="utf-8")
        git(self.root, "add", "tracked.txt")
        git(self.root, "commit", "-q", "-m", "initial")
        self.commit = git(self.root, "rev-parse", "HEAD").stdout.strip()

    def test_pretest_passes_and_writes_log(self):
        result = run(
            ["--task-id", "11", "--command", 'python -c "print(111)"'],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["state"], "passed")
        self.assertEqual(data["head"], self.commit)
        log = Path(data["log"])
        self.assertTrue(log.is_file())
        self.assertIn("111", log.read_text(encoding="utf-8"))

    def test_pretest_records_failed_exit_code(self):
        result = run(
            ["--command", 'python -c "raise SystemExit(3)"'],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["state"], "failed")
        self.assertEqual(data["exit_code"], 3)

    def test_pretest_records_git_status_delta(self):
        result = run(
            ["--command", 'python -c "open(\'junk.txt\', \'w\').write(\'x\')"'],
            self.root,
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["state"], "passed")
        self.assertTrue(any("junk.txt" in line for line in data["git_status_after"]))


if __name__ == "__main__":
    unittest.main()
