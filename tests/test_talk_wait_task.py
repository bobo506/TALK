"""``scripts.talk_wait_task`` 的单元测试（不联网、不调用模型）。"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import talk_wait_task as waiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def task(status: str = "running", workflow: str = "in_progress", **extra) -> dict:
    payload = {
        "id": 417,
        "status": status,
        "workflow_status": workflow,
        "result_message_id": None,
        "last_error": None,
    }
    payload.update(extra)
    return payload


class DefaultBudgetTests(unittest.TestCase):
    """主动等待默认预算必须与任务默认执行预算一致，不能短于长任务耗时。"""

    def test_default_wait_budget_is_one_day(self) -> None:
        self.assertEqual(waiter.DEFAULT_TIMEOUT, 86400.0)
        args = waiter.build_parser().parse_args(["--task-id", "1"])
        self.assertEqual(args.timeout, 86400.0)


class TerminalTests(unittest.TestCase):
    def test_terminal_status(self) -> None:
        for status in ("succeeded", "failed", "canceled"):
            self.assertTrue(waiter.is_terminal(task(status=status)), status)

    def test_terminal_workflow(self) -> None:
        for workflow in ("submitted", "completed", "failed", "canceled"):
            self.assertTrue(waiter.is_terminal(task(workflow=workflow)), workflow)

    def test_non_terminal(self) -> None:
        self.assertFalse(waiter.is_terminal(task()))
        self.assertFalse(waiter.is_terminal({}))


class WaitTests(unittest.TestCase):
    def test_returns_immediately_when_terminal(self) -> None:
        clock = FakeClock()
        seen = []

        def fetch(task_id):
            seen.append(task_id)
            return task(status="succeeded", workflow="submitted", result_message_id=3193)

        result, elapsed = waiter.wait_for_task(
            417, fetch, interval=15, timeout=60, clock=clock, sleep=clock.sleep
        )
        self.assertEqual(seen, [417])
        self.assertEqual(result["result_message_id"], 3193)
        self.assertEqual(elapsed, 0)

    def test_polls_until_terminal(self) -> None:
        clock = FakeClock()
        responses = [task(), task(), task(status="failed", workflow="failed")]

        def fetch(_task_id):
            return responses.pop(0)

        result, elapsed = waiter.wait_for_task(
            417, fetch, interval=10, timeout=60, clock=clock, sleep=clock.sleep
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(elapsed, 20)

    def test_transient_network_error_is_retried(self) -> None:
        clock = FakeClock()
        attempts = {"n": 0}

        def fetch(_task_id):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise OSError("connection reset")
            return task(status="succeeded")

        result, _elapsed = waiter.wait_for_task(
            417, fetch, interval=5, timeout=60, clock=clock, sleep=clock.sleep
        )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(attempts["n"], 3)

    def test_timeout_reports_last_seen(self) -> None:
        clock = FakeClock()

        def fetch(_task_id):
            return task(status="running", workflow="in_progress")

        with self.assertRaises(waiter.WaitTimeout) as ctx:
            waiter.wait_for_task(
                417, fetch, interval=10, timeout=25, clock=clock, sleep=clock.sleep
            )
        self.assertEqual(ctx.exception.last["status"], "running")
        self.assertGreaterEqual(ctx.exception.elapsed, 25)

    def test_fatal_error_propagates_without_sleeping(self) -> None:
        clock = FakeClock()

        def fetch(_task_id):
            raise waiter.WaitError("任务不存在", code="task_unavailable")

        with self.assertRaises(waiter.WaitError) as ctx:
            waiter.wait_for_task(
                417, fetch, interval=10, timeout=60, clock=clock, sleep=clock.sleep
            )
        self.assertEqual(ctx.exception.code, "task_unavailable")
        self.assertEqual(clock.now, 0)

    def test_interval_floor(self) -> None:
        with self.assertRaises(waiter.WaitError):
            waiter.wait_for_task(417, lambda _t: task(status="succeeded"), interval=1)


class KeyTests(unittest.TestCase):
    def test_key_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.key"
            path.write_text("abc123\n", encoding="utf-8")
            key, source = waiter.resolve_key(str(path), environ={})
        self.assertEqual(key, "abc123")
        self.assertIn("密钥文件", source)

    def test_environment_direct_key_wins(self) -> None:
        key, source = waiter.resolve_key(None, environ={"TALK_API_KEY": "k-1"})
        self.assertEqual(key, "k-1")
        self.assertEqual(source, "环境变量 TALK_API_KEY")

    def test_environment_key_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.key"
            path.write_text("k-2", encoding="utf-8")
            key, _source = waiter.resolve_key(
                None, environ={"TALK_WAIT_KEY_FILE": str(path)}
            )
        self.assertEqual(key, "k-2")

    def test_missing_source(self) -> None:
        with self.assertRaises(waiter.WaitError) as ctx:
            waiter.resolve_key(None, environ={})
        self.assertEqual(ctx.exception.code, "key_missing")

    def test_rejects_non_ascii_or_empty(self) -> None:
        with self.assertRaises(waiter.WaitError):
            waiter.resolve_key(None, environ={"TALK_API_KEY": "中文"})
        with self.assertRaises(waiter.WaitError):
            waiter.resolve_key(None, environ={"TALK_API_KEY": "   "})


class FetchTests(unittest.TestCase):
    class _Response:
        def __init__(self, payload: dict) -> None:
            self._body = json.dumps(payload).encode("utf-8")

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            return None

    def test_fetch_sends_api_key_and_parses(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["key"] = req.get_header("X-api-key")
            captured["timeout"] = timeout
            return self._Response({"id": 417, "status": "queued"})

        with mock.patch.object(waiter.request, "urlopen", fake_urlopen):
            payload = waiter.fetch_task("http://127.0.0.1:8000/", "secret", 417)

        self.assertEqual(payload["status"], "queued")
        self.assertEqual(captured["url"], "http://127.0.0.1:8000/api/tasks/417")
        self.assertEqual(captured["key"], "secret")

    def test_fetch_404_is_fatal(self) -> None:
        def fake_urlopen(req, timeout=None):
            raise waiter.error.HTTPError(req.full_url, 404, "not found", None, io.BytesIO(b""))

        with mock.patch.object(waiter.request, "urlopen", fake_urlopen):
            with self.assertRaises(waiter.WaitError) as ctx:
                waiter.fetch_task("http://127.0.0.1:8000", "secret", 417)
        self.assertEqual(ctx.exception.code, "task_unavailable")

    def test_fetch_500_is_retryable(self) -> None:
        def fake_urlopen(req, timeout=None):
            raise waiter.error.HTTPError(req.full_url, 500, "boom", None, io.BytesIO(b""))

        with mock.patch.object(waiter.request, "urlopen", fake_urlopen):
            with self.assertRaises(OSError):
                waiter.fetch_task("http://127.0.0.1:8000", "secret", 417)


class MainTests(unittest.TestCase):
    def _run(self, argv, *, patched_fetch, timeout_error=None):
        output = io.StringIO()
        with mock.patch.object(waiter, "resolve_key", return_value=("SECRET_KEY_VALUE", "test")), \
                mock.patch.object(waiter, "fetch_task", patched_fetch), \
                redirect_stdout(output):
            code = waiter.main(argv)
        return code, output.getvalue()

    def test_done_output(self) -> None:
        code, text = self._run(
            ["--task-id", "417"],
            patched_fetch=lambda *a, **k: task(status="succeeded", workflow="submitted"),
        )
        self.assertEqual(code, 0)
        self.assertIn("TALK_TASK_DONE task=417", text)
        self.assertNotIn("SECRET_KEY_VALUE", text)

    def test_error_output(self) -> None:
        def boom(*_a, **_k):
            raise waiter.WaitError("no task", code="task_unavailable")

        code, text = self._run(["--task-id", "417"], patched_fetch=boom)
        self.assertEqual(code, 2)
        self.assertIn("TALK_TASK_ERROR", text)
        self.assertIn("task_unavailable", text)


class AttentionTests(unittest.TestCase):
    def test_second_poll_and_main_output(self):
        clock = FakeClock()
        responses = iter([task(), task(workflow="clarification_requested")])
        real_wait = waiter.wait_for_task
        def fake_wait(task_id, fetch, **kwargs):
            return real_wait(task_id, fetch, interval=5, timeout=60,
                             clock=clock, sleep=clock.sleep)
        output = io.StringIO()
        with mock.patch.object(waiter, "resolve_key", return_value=("key", "test")), \
             mock.patch.object(waiter, "fetch_task", side_effect=lambda *a, **k: next(responses)) as fetch, \
             mock.patch.object(waiter, "wait_for_task", side_effect=fake_wait), redirect_stdout(output):
            code = waiter.main(["--task-id", "417"])
        self.assertEqual(code, 3)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(output.getvalue(), "TALK_TASK_ATTENTION task=417 status=running workflow=clarification_requested reason=clarification elapsed=5s\n")

    def test_json_outcomes_and_terminal_priority(self):
        cases = [(task(workflow="clarification_requested"), 3, "attention", "clarification"),
                 (task(workflow="needs_decision"), 3, "attention", "decision"),
                 (task(status="succeeded", workflow="needs_decision"), 0, "done", None)]
        for response, expected, outcome, reason in cases:
            with self.subTest(outcome=outcome, reason=reason):
                out = io.StringIO()
                with mock.patch.object(waiter, "resolve_key", return_value=("key", "test")), \
                     mock.patch.object(waiter, "fetch_task", return_value=response), redirect_stdout(out):
                    code = waiter.main(["--task-id", "417", "--json"])
                payload = json.loads(out.getvalue())
                self.assertEqual((code, payload["outcome"], payload["reason"]), (expected, outcome, reason))
                self.assertEqual(payload["event"], outcome)

    def test_timeout_and_error_json(self):
        for exc, code, outcome in [(waiter.WaitTimeout(task_id=417, elapsed=5, last=None), 1, "timeout"),
                                    (waiter.WaitError("error"), 2, "error")]:
            out = io.StringIO()
            with mock.patch.object(waiter, "resolve_key", return_value=("key", "test")), \
                 mock.patch.object(waiter, "wait_for_task", side_effect=exc), redirect_stdout(out):
                self.assertEqual(waiter.main(["--task-id", "417", "--json"]), code)
            payload = json.loads(out.getvalue())
            self.assertEqual((payload["outcome"], payload["reason"]), (outcome, None))

    def test_usage_and_key_errors(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(waiter.main([]), 64)
        with mock.patch.object(waiter, "resolve_key", side_effect=waiter.WaitError("missing", code="key_missing")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(waiter.main(["--task-id", "417"]), 2)


if __name__ == "__main__":
    unittest.main()
