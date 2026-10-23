import asyncio
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bridges import cli_bridge
from bridges import runtime_diagnostics as runtime_diag
from bridges.cli_bridge import CliRunResult
from TALK.client.exceptions import TalkValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.runtime_diagnostics import main as diagnostics_cli_main
except ImportError:
    diagnostics_cli_main = None


def _load_diagnostics_cli():
    if diagnostics_cli_main is not None:
        return diagnostics_cli_main
    path = PROJECT_ROOT / "scripts" / "runtime_diagnostics.py"
    spec = importlib.util.spec_from_file_location("talk_runtime_diagnostics_cli", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.main


class RuntimeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self._writers = []

    def tearDown(self):
        for writer in self._writers:
            writer.close()
        self._tempdir.cleanup()

    def make_diagnostics(self, **kwargs):
        policy = kwargs.pop(
            "policy",
            runtime_diag.DiagnosticsPolicy.create(root=self.root),
        )
        writer = runtime_diag.RuntimeDiagnostics(
            member_id=kwargs.pop("member_id", "agent:deepseek"),
            instance_id=kwargs.pop("instance_id", "agent:deepseek:test"),
            policy=policy,
            project_id=kwargs.pop("project_id", "prj_test"),
            launch_id=kwargs.pop("launch_id", "launch-test"),
            runtime=kwargs.pop("runtime", "dsh"),
            known_secrets=kwargs.pop("known_secrets", ()),
            **kwargs,
        )
        self._writers.append(writer)
        return writer

    def records(self, **kwargs):
        kwargs.setdefault("limit", 200)
        return runtime_diag.query_records(self.root, **kwargs)["records"]

    def event_files(self):
        return sorted(self.root.rglob("events-*.jsonl"))

    def raw_text(self):
        parts = []
        for path in sorted(self.root.rglob("*.jsonl")):
            parts.append(path.read_text(encoding="utf-8"))
        return "\n".join(parts)

    def test_empty_message_and_explicit_chain_persist_with_timezone(self):
        def leaf():
            raise ValueError("")

        def middle():
            try:
                leaf()
            except ValueError as exc:
                raise RuntimeError("outer boom") from exc

        diagnostics = self.make_diagnostics()
        try:
            middle()
        except Exception as exc:
            log_id = diagnostics.record_exception(
                exc,
                stage="unit_chain",
                task_id=271,
                budgets={
                    "cli_timeout_seconds": 600,
                    "http_timeout_seconds": 10.0,
                    "task_lease_seconds": 120,
                    "mcp_wait_seconds": None,
                },
            )
        self.assertIsNotNone(log_id)
        self.assertRegex(log_id, r"^rtd-[A-Za-z0-9.-]+$")

        raw = self.raw_text()
        self.assertIn(log_id, raw)
        self.assertTrue(self.event_files())
        stored = json.loads(self.event_files()[0].read_text(encoding="utf-8").splitlines()[0])
        recorded = datetime.fromisoformat(stored["recorded_at"])
        self.assertIsNotNone(recorded.tzinfo)

        records = self.records(ref=log_id)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["task_id"], 271)
        self.assertEqual(record["project_id"], "prj_test")
        self.assertEqual(record["launch_id"], "launch-test")
        self.assertEqual(record["exception"]["type"], "RuntimeError")
        self.assertGreaterEqual(record["exception"]["frames_total"], 2)
        self.assertEqual(len(record["exception"]["cause_chain"]), 1)
        cause = record["exception"]["cause_chain"][0]
        self.assertEqual(cause["type"], "ValueError")
        self.assertEqual(cause["relation"], "explicit_cause")
        self.assertEqual(cause["str_empty"], True)
        self.assertGreaterEqual(cause["frames_total"], 2)
        self.assertEqual(record["budgets"]["cli_timeout_seconds"], 600)
        self.assertIsNone(record["budgets"]["mcp_wait_seconds"])

    def test_implicit_context_is_captured(self):
        diagnostics = self.make_diagnostics()
        try:
            try:
                raise KeyError("inner-key")
            except KeyError:
                raise LookupError("outer-lookup")
        except Exception as exc:
            log_id = diagnostics.record_exception(exc, stage="implicit_context")
        record = self.records(ref=log_id)[0]
        chain = record["exception"]["cause_chain"]
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0]["relation"], "implicit_context")
        self.assertEqual(chain[0]["type"], "KeyError")

    def test_multi_level_explicit_cause_chain_is_captured(self):
        diagnostics = self.make_diagnostics()
        try:
            try:
                try:
                    raise ValueError("leaf")
                except ValueError as leaf:
                    raise KeyError("middle") from leaf
            except KeyError as middle:
                raise RuntimeError("top") from middle
        except Exception as exc:
            log_id = diagnostics.record_exception(exc, stage="deep_chain")
        record = self.records(ref=log_id)[0]
        chain = record["exception"]["cause_chain"]
        self.assertEqual([item["type"] for item in chain], ["KeyError", "ValueError"])
        self.assertTrue(all(item["relation"] == "explicit_cause" for item in chain))
        self.assertEqual(record["exception"]["chain_depth"], 2)

    def test_redaction_covers_known_opaque_headers_url_prompt_and_nested(self):
        secret = "sk-live-OPAQUE-abcdef1234567890"
        prompt = "PROMPT-ONLY-4f6b-do-not-persist"
        diagnostics = self.make_diagnostics(known_secrets=[secret])
        exception = RuntimeError(
            f"cmd failed --prompt '{prompt}' "
            f"Authorization: Bearer {secret} "
            f"X-Api-Key: {secret} "
            f"Proxy-Authorization: Basic dXNlcjpwYXNzLW9wYXF1ZQ== "
            f"https://example.test/task?token={secret}&ok=1 "
            f"password=hunter2 api_key=opaque-value-123 "
            f"nested={{'claim_token': 'lease-secret', 'safe': 'keep'}}"
        )
        log_id = diagnostics.record_exception(
            exception,
            stage="redaction",
            sensitive_values=[prompt],
            extra={
                "headers": {"Authorization": f"Bearer {secret}", "Accept": "json"},
                "password": "hunter2",
                "nested": {"token": "tok-nested-123", "safe": "keep"},
                "prompt": prompt,
            },
        )
        raw = self.raw_text()
        for forbidden in (
            secret,
            prompt,
            "hunter2",
            "opaque-value-123",
            "lease-secret",
            "tok-nested-123",
            "dXNlcjpwYXNzLW9wYXF1ZQ==",
        ):
            self.assertNotIn(forbidden, raw)
        self.assertIn("keep", raw)

        record = self.records(ref=log_id)[0]
        self.assertTrue(record["integrity"]["redacted"])
        self.assertIn("known_value", record["integrity"]["redaction_kinds"])
        summary = runtime_diag.format_record_summary(record)
        detail = runtime_diag.format_record_detail(record)
        for forbidden in (
            secret,
            prompt,
            "hunter2",
            "opaque-value-123",
            "dXNlcjpwYXNzLW9wYXF1ZQ==",
        ):
            self.assertNotIn(forbidden, summary)
            self.assertNotIn(forbidden, detail)

    def test_rotation_preserves_old_refs_and_cleanup_leaves_tombstone(self):
        policy = runtime_diag.DiagnosticsPolicy.create(
            root=self.root,
            max_file_bytes=320,
            max_bytes=64 * 1024,
            retention_days=1,
        )
        diagnostics = self.make_diagnostics(policy=policy)
        refs = []
        for index in range(10):
            refs.append(
                diagnostics.record_event(
                    "rotation_probe",
                    stage="rotation",
                    message=f"probe-{index}-" + ("x" * 180),
                )
            )
        files = self.event_files()
        self.assertGreater(len(files), 1)
        self.assertIn(refs[0], self.raw_text())
        self.assertEqual(len(self.records(event="rotation_probe")), 10)

        # Retention is explicit and only touches this run.  Make the oldest
        # segment expired; the current segment and a second run must survive.
        oldest = files[0]
        old_time = time.time() - 10 * 86400
        os.utime(oldest, (old_time, old_time))
        other = self.make_diagnostics(instance_id="agent:deepseek:other")
        other_ref = other.record_event("other_run", stage="rotation")
        other_file = next(
            path for path in self.event_files() if "other" in path.as_posix()
        )
        os.utime(other_file, (old_time, old_time))
        removed = diagnostics.cleanup_expired()
        self.assertIn(oldest.name, removed)
        self.assertFalse(oldest.exists())
        self.assertTrue(other_file.exists())
        self.assertTrue(self.records(ref=other_ref))
        tombstones = (diagnostics.namespace / "retention.jsonl").read_text(encoding="utf-8")
        self.assertIn('"action":"delete"', tombstones.replace(" ", ""))
        self.assertIn(oldest.name, tombstones)
        self.assertTrue((diagnostics.namespace / "manifest.json").exists())

    def test_capacity_overflow_is_explicitly_marked(self):
        policy = runtime_diag.DiagnosticsPolicy.create(
            root=self.root,
            max_bytes=256,
            max_file_bytes=256,
            retention_days=1,
        )
        diagnostics = self.make_diagnostics(policy=policy)
        ref = diagnostics.record_event(
            "oversize",
            stage="capacity",
            message="x" * 1000,
        )
        self.assertIsNotNone(ref)
        record = self.records(ref=ref)[0]
        self.assertTrue(record["integrity"]["truncated"])
        self.assertTrue(record["integrity"]["capacity_soft_exceeded"])

    def test_restart_locates_old_reference_and_new_run_does_not_clear(self):
        first = self.make_diagnostics(instance_id="agent:deepseek:first")
        log_id = first.record_exception(RuntimeError("first"), stage="restart")
        first_file = self.event_files()[0]
        first.close()

        second = self.make_diagnostics(instance_id="agent:deepseek:second")
        second_ref = second.record_event("second_started", stage="restart")
        self.assertTrue(first_file.exists())
        old = self.records(ref=log_id)
        self.assertEqual(len(old), 1)
        self.assertEqual(old[0]["instance_id"], "agent:deepseek:first")
        self.assertTrue(self.records(ref=second_ref))

    def test_two_instances_write_concurrently_without_overwrite(self):
        def writer(instance: str):
            diagnostics = self.make_diagnostics(instance_id=f"agent:deepseek:{instance}")
            for index in range(6):
                diagnostics.record_event(
                    f"concurrent_{instance}",
                    stage="concurrency",
                    message=f"{instance}-{index}",
                )
            diagnostics.close()

        threads = [
            threading.Thread(target=writer, args=(f"instance-{index}",))
            for index in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        records = self.records()
        events = [record for record in records if str(record.get("event")).startswith("concurrent_")]
        self.assertEqual(len(events), 12)
        self.assertEqual(
            {record["instance_id"] for record in events},
            {"agent:deepseek:instance-0", "agent:deepseek:instance-1"},
        )
        self.assertEqual(len({record["log_id"] for record in events}), 12)

    def test_defaults_and_explicit_overrides_are_visible(self):
        policy = runtime_diag.DiagnosticsPolicy.create()
        self.assertEqual(policy.root, runtime_diag.DEFAULT_ROOT)
        self.assertEqual(policy.retention_days, 30.0)
        self.assertEqual(policy.max_bytes, 256 * 1024 * 1024)
        self.assertEqual(policy.max_file_bytes, 8 * 1024 * 1024)

        args = SimpleNamespace(
            runtime_log_dir=str(self.root),
            runtime_log_retention_days=3,
            runtime_log_max_bytes=4096,
            runtime_log_max_file_bytes=1024,
            runtime_log_disabled=False,
        )
        diagnostics = runtime_diag.RuntimeDiagnostics.from_bridge_args(
            args,
            member_id="agent:deepseek",
            instance_id="agent:deepseek:config-test",
            runtime="dsh",
        )
        self.assertIsNotNone(diagnostics)
        self.assertEqual(diagnostics.policy.root, self.root)
        self.assertEqual(diagnostics.policy.retention_days, 3.0)
        self.assertEqual(diagnostics.policy.max_bytes, 4096)
        self.assertEqual(diagnostics.policy.max_file_bytes, 1024)
        diagnostics.close()

        with patch.dict(
            os.environ,
            {
                "TALK_RUNTIME_LOG_DIR": str(self.root / "env-root"),
                "TALK_RUNTIME_LOG_RETENTION_DAYS": "5",
                "TALK_RUNTIME_LOG_MAX_BYTES": "8192",
                "TALK_RUNTIME_LOG_MAX_FILE_BYTES": "2048",
            },
            clear=False,
        ):
            env_args = SimpleNamespace(runtime_log_disabled=False)
            env_diag = runtime_diag.RuntimeDiagnostics.from_bridge_args(
                env_args,
                member_id="agent:deepseek",
                instance_id="agent:deepseek:env-test",
                runtime="dsh",
            )
            self.assertEqual(env_diag.policy.root.resolve(), (self.root / "env-root").resolve())
            self.assertEqual(env_diag.policy.retention_days, 5.0)
            self.assertEqual(env_diag.policy.max_bytes, 8192)
            self.assertEqual(env_diag.policy.max_file_bytes, 2048)
            env_diag.close()

    def test_two_processes_write_to_separate_namespaces(self):
        child_code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from bridges import runtime_diagnostics as rd; "
            "d=rd.RuntimeDiagnostics(member_id='agent:deepseek', "
            "instance_id=sys.argv[2], root=sys.argv[3]); "
            "d.record_event('process_write', stage='multiprocess')"
        )
        processes = []
        try:
            for index in range(2):
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            child_code,
                            str(PROJECT_ROOT),
                            f"agent:deepseek:process-{index}",
                            str(self.root),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        cwd=str(PROJECT_ROOT),
                    )
                )
        except OSError as exc:
            for process in processes:
                process.kill()
            self.skipTest(f"subprocess spawn unavailable: {type(exc).__name__}")
        for process in processes:
            self.assertEqual(process.wait(timeout=15), 0)
        records = self.records(event="process_write")
        self.assertEqual(len(records), 2)
        self.assertEqual(
            {record["instance_id"] for record in records},
            {"agent:deepseek:process-0", "agent:deepseek:process-1"},
        )

    def test_query_rejects_path_like_reference_and_missing_root(self):
        diagnostics = self.make_diagnostics()
        ref = diagnostics.record_event("safe", stage="query")
        self.assertTrue(self.records(ref=ref))
        with self.assertRaises(runtime_diag.DiagnosticsQueryError):
            runtime_diag.query_records(self.root, ref="../../etc/passwd")
        with self.assertRaises(runtime_diag.DiagnosticsQueryError):
            runtime_diag.query_records(self.root / "missing")

    def test_log_write_failure_is_visible_sanitized_and_does_not_raise(self):
        bad_root = self.root / "not-a-directory"
        bad_root.write_text("occupied", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            diagnostics = runtime_diag.RuntimeDiagnostics(
                member_id="agent:deepseek",
                instance_id="agent:deepseek:failure",
                root=bad_root,
                known_secrets=["sk-failure-secret-123"],
            )
            ref = diagnostics.record_exception(
                RuntimeError("write failure sk-failure-secret-123"),
                stage="io_failure",
            )
        self.assertIsNone(ref)
        self.assertIn("本地诊断日志降级", stderr.getvalue())
        self.assertNotIn("sk-failure-secret-123", stderr.getvalue())


class RuntimeDiagnosticsCliTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.diagnostics = runtime_diag.RuntimeDiagnostics(
            member_id="agent:deepseek",
            instance_id="agent:deepseek:cli-test",
            root=self.root,
            project_id="prj_test",
        )
        self.secret = "sk-cli-OPAQUE-998877665544"
        self.ref = self.diagnostics.record_exception(
            RuntimeError(f"detail Authorization: Bearer {self.secret}"),
            stage="cli_query",
            extra={"nested": {"password": "hunter2"}},
        )

    def tearDown(self):
        self.diagnostics.close()
        self._tempdir.cleanup()

    def test_default_output_is_summary_only_and_detail_includes_frames(self):
        main = _load_diagnostics_cli()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--log-dir", str(self.root), "--ref", self.ref])
        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn(self.ref, text)
        self.assertNotIn("traceback [", text)
        self.assertNotIn(self.secret, text)
        self.assertNotIn("hunter2", text)

        detail = io.StringIO()
        with contextlib.redirect_stdout(detail):
            code = main(["--log-dir", str(self.root), "--ref", self.ref, "--detail"])
        self.assertEqual(code, 0)
        detail_text = detail.getvalue()
        self.assertIn("traceback [primary]", detail_text)
        self.assertNotIn(self.secret, detail_text)
        self.assertNotIn("hunter2", detail_text)

    def test_invalid_reference_is_usage_error_and_does_not_echo(self):
        main = _load_diagnostics_cli()
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            code = main(["--log-dir", str(self.root), "--ref", "../../etc/passwd"])
        self.assertEqual(code, 2)
        self.assertNotIn("passwd", output.getvalue())


class BridgeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.secret = "sk-bridge-OPAQUE-1234567890"
        self.prompt = "BRIDGE-PROMPT-ONLY-xyz"
        self.diagnostics = runtime_diag.RuntimeDiagnostics(
            member_id="agent:deepseek",
            instance_id="agent:deepseek:bridge-test",
            root=self.root,
            project_id="prj_test",
            launch_id="launch-test",
            runtime="dsh",
            known_secrets=[self.secret],
        )

    def tearDown(self):
        self.diagnostics.close()
        self._tempdir.cleanup()

    def records(self, **kwargs):
        kwargs.setdefault("limit", 200)
        return runtime_diag.query_records(self.root, **kwargs)["records"]

    def test_message_cli_failure_persists_ref_and_redacts_public_fields(self):
        class FakeClient:
            timeout = 10.0

            def __init__(self):
                self.replies = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 501}

        statuses = []

        async def report_status(status, **kwargs):
            statuses.append((status, kwargs))

        async def fake_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=1,
                stdout="",
                stderr=f"failure token={self.secret} prompt={prompt}",
            )

        async def scenario():
            with patch.object(cli_bridge, "run_cli_command", fake_run):
                client = FakeClient()
                await cli_bridge.handle_incoming_message(
                    {
                        "id": 40,
                        "from": "human:bobo",
                        "to": ["agent:deepseek"],
                        "type": "text",
                        "content": "@agent:deepseek do the work",
                    },
                    client=client,
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    command=["fake"],
                    timeout=5,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    report_status=report_status,
                    diagnostics=self.diagnostics,
                )
                return client

        client = asyncio.run(scenario())
        self.assertEqual(len(client.replies), 1)
        self.assertIn("日志引用", client.replies[0][1])
        self.assertNotIn(self.secret, client.replies[0][1])
        self.assertEqual(statuses[-1][0], "error")
        self.assertIn("log_ref=", statuses[-1][1]["last_error"])
        self.assertNotIn(self.secret, statuses[-1][1]["last_error"])

        records = self.records(event="cli_failed")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertIsNone(record["task_id"])
        self.assertEqual(record["message_id"], "40")
        self.assertEqual(record["returncode"], 1)
        self.assertFalse(record["timeout"])
        self.assertEqual(record["budgets"]["cli_timeout_seconds"], 5)
        self.assertEqual(record["budgets"]["http_timeout_seconds"], 10.0)
        self.assertIsNone(record["budgets"]["mcp_wait_seconds"])
        self.assertTrue(record["integrity"]["redacted"])
        raw = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self.root.rglob("events-*.jsonl")
        )
        self.assertNotIn(self.secret, raw)
        self.assertNotIn(self.prompt, raw)

    def test_message_cli_timeout_and_cancel_are_logged(self):
        class FakeClient:
            timeout = 10.0

            async def reply(self, message_id, *, text, to=None, group_id=None):
                return {"id": 502}

        async def report_status(status, **kwargs):
            return None

        async def timeout_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(returncode=-1, stdout="", stderr="", timed_out=True)

        async def timeout_scenario():
            with patch.object(cli_bridge, "run_cli_command", timeout_run):
                await cli_bridge.handle_incoming_message(
                    {
                        "id": 41,
                        "from": "human:bobo",
                        "to": ["agent:deepseek"],
                        "type": "text",
                        "content": "do the work",
                    },
                    client=FakeClient(),
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    command=["fake"],
                    timeout=7,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    report_status=report_status,
                    diagnostics=self.diagnostics,
                )

        asyncio.run(timeout_scenario())
        timeout_records = self.records(event="cli_timeout")
        self.assertEqual(len(timeout_records), 1)
        self.assertTrue(timeout_records[0]["timeout"])
        self.assertEqual(timeout_records[0]["returncode"], -1)
        self.assertEqual(timeout_records[0]["budgets"]["cli_timeout_seconds"], 7)

        async def cancel_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            raise asyncio.CancelledError

        async def cancel_scenario():
            with patch.object(cli_bridge, "run_cli_command", cancel_run):
                await cli_bridge.handle_incoming_message(
                    {
                        "id": 42,
                        "from": "human:bobo",
                        "to": ["agent:deepseek"],
                        "type": "text",
                        "content": "cancel this",
                    },
                    client=FakeClient(),
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    command=["fake"],
                    timeout=7,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    report_status=report_status,
                    diagnostics=self.diagnostics,
                )

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(cancel_scenario())
        cancelled = self.records(event="message_cancelled")
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["cancel_category"], "asyncio_cancelled")

    def test_secondary_status_failure_links_primary_and_preserves_original(self):
        class FakeClient:
            timeout = 10.0

            async def reply(self, message_id, *, text, to=None, group_id=None):
                return {"id": 503}

        async def report_status(status, **kwargs):
            if status == "error":
                raise RuntimeError("status channel down")

        async def fake_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            raise RuntimeError(f"runner boom token={self.secret}")

        async def scenario():
            with patch.object(cli_bridge, "run_cli_command", fake_run):
                await cli_bridge.handle_incoming_message(
                    {
                        "id": 43,
                        "from": "human:bobo",
                        "to": ["agent:deepseek"],
                        "type": "text",
                        "content": "fail the runner",
                    },
                    client=FakeClient(),
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    command=["fake"],
                    timeout=5,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    report_status=report_status,
                    diagnostics=self.diagnostics,
                )

        with self.assertRaisesRegex(RuntimeError, "runner boom"):
            asyncio.run(scenario())
        primary = self.records(event="message_exception")
        secondary = self.records(event="secondary_failure")
        self.assertEqual(len(primary), 1)
        self.assertEqual(len(secondary), 1)
        self.assertEqual(secondary[0]["related_log_id"], primary[0]["log_id"])
        self.assertNotIn(self.secret, json.dumps(primary, ensure_ascii=False))
        self.assertNotIn(self.secret, json.dumps(secondary, ensure_ascii=False))

    def test_queue_worker_survives_secondary_report_failure(self):
        class QueueClient:
            timeout = 10.0

            def __init__(self):
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError(f"queue boom token={self.secret}")
                raise asyncio.CancelledError

        args = SimpleNamespace(
            command="fake",
            task_command="fake",
            task_preflight_command="fake",
            timeout=5,
            max_reply_chars=300,
            runtime="dsh",
            bridge_label="DeepSeek bridge",
            prompt_transport="argv",
            decision_tier=None,
            task_lease_seconds=30,
            task_heartbeat_interval=1,
            task_poll_interval=0,
            task_preflight_max_attempts=1,
        )

        async def report_status(status, **kwargs):
            if status == "error":
                raise RuntimeError("status channel down")

        async def scenario():
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(asyncio.CancelledError):
                    await cli_bridge.run_task_queue_worker(
                        client=QueueClient(),
                        member_id="agent:deepseek",
                        workdir=Path.cwd(),
                        instance_id="agent:deepseek:test",
                        args=args,
                        run_lock=asyncio.Lock(),
                        report_status=report_status,
                        diagnostics=self.diagnostics,
                    )

        asyncio.run(scenario())
        primary = self.records(event="queue_worker_exception")
        secondary = self.records(event="secondary_failure")
        started = self.records(event="queue_started")
        stopped = self.records(event="queue_stopped")
        self.assertEqual(len(primary), 1)
        self.assertEqual(len(secondary), 1)
        self.assertEqual(secondary[0]["related_log_id"], primary[0]["log_id"])
        self.assertEqual(len(started), 1)
        self.assertEqual(len(stopped), 1)
        self.assertIn("cancelled", stopped[0]["message"])

    def test_task_cli_failure_and_result_send_failure_are_both_persisted(self):
        class TaskClient:
            timeout = 10.0

            def __init__(self):
                self.sent = []
                self.completed = []

            async def claim_task(self, task_id, *, instance_id=None, lease_seconds=120):
                return {
                    "id": task_id,
                    "content": "task content",
                    "created_by": "human:bobo",
                    "hall_group_id": None,
                    "claim_token": "lease-12",
                }

            async def heartbeat_task(self, task_id, *, claim_token, lease_seconds=120):
                return {}

            async def send_text(self, text, to=None, group_id=None):
                raise RuntimeError(f"send failed token={self.secret}")

            async def complete_task(self, task_id, **kwargs):
                self.completed.append((task_id, kwargs))
                return {"id": task_id}

        async def fake_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(returncode=1, stdout="", stderr=f"failed {self.secret}")

        async def scenario():
            with patch.object(cli_bridge, "run_cli_command", fake_run):
                client = TaskClient()
                handled = await cli_bridge.handle_queued_task(
                    {"id": 12, "workflow_status": "assigned"},
                    client=client,
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    instance_id="agent:deepseek:test",
                    command=["fake"],
                    timeout=5,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    lease_seconds=30,
                    heartbeat_interval=1,
                    diagnostics=self.diagnostics,
                )
                return handled, client

        handled, client = asyncio.run(scenario())
        self.assertTrue(handled)
        self.assertEqual(len(client.completed), 1)
        completion = client.completed[0][1]
        self.assertEqual(completion["status"], "failed")
        self.assertIn("could not post task result", completion["last_error"])
        self.assertIn("log_ref=", completion["last_error"])
        self.assertNotIn(self.secret, completion["last_error"])

        primary = self.records(event="cli_failed")
        secondary = self.records(event="secondary_failure")
        self.assertEqual(len(primary), 1)
        self.assertEqual(len(secondary), 1)
        self.assertEqual(secondary[0]["related_log_id"], primary[0]["log_id"])
        self.assertEqual(secondary[0]["task_id"], 12)
        self.assertEqual(secondary[0]["budgets"]["task_lease_seconds"], 30)
        self.assertNotIn(self.secret, json.dumps(primary + secondary, ensure_ascii=False))

    def test_secondary_completion_failure_links_first_error_and_propagates(self):
        secret = self.secret

        class TaskClient:
            timeout = 10.0

            async def claim_task(self, task_id, *, instance_id=None, lease_seconds=120):
                return {
                    "id": task_id,
                    "content": "task content",
                    "created_by": "human:bobo",
                    "claim_token": "lease-12",
                }

            async def heartbeat_task(self, task_id, *, claim_token, lease_seconds=120):
                return {}

            async def send_text(self, text, to=None, group_id=None):
                raise RuntimeError(f"send failed token={secret}")

            async def complete_task(self, task_id, **kwargs):
                raise RuntimeError(f"complete failed token={secret}")

        async def fake_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(returncode=1, stdout="", stderr=f"failed {secret}")

        async def scenario():
            with patch.object(cli_bridge, "run_cli_command", fake_run):
                await cli_bridge.handle_queued_task(
                    {"id": 17, "workflow_status": "assigned"},
                    client=TaskClient(),
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    instance_id="agent:deepseek:test",
                    command=["fake"],
                    timeout=5,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    lease_seconds=30,
                    heartbeat_interval=1,
                    diagnostics=self.diagnostics,
                )

        with self.assertRaisesRegex(RuntimeError, "complete failed"):
            asyncio.run(scenario())
        primary = self.records(event="cli_failed")
        secondary = self.records(event="secondary_failure")
        self.assertEqual(len(primary), 1)
        self.assertEqual(len(secondary), 2)
        self.assertTrue(
            all(
                record["related_log_id"] == primary[0]["log_id"]
                for record in secondary
            )
        )
        stages = {record["stage"] for record in secondary}
        self.assertEqual(stages, {"task_result_send", "task_complete"})
        self.assertNotIn(self.secret, json.dumps(primary + secondary, ensure_ascii=False))

    def test_task_lease_loss_is_logged_and_returns_false(self):
        class TaskClient:
            timeout = 10.0

            def __init__(self):
                self.completed = []

            async def claim_task(self, task_id, *, instance_id=None, lease_seconds=120):
                return {
                    "id": task_id,
                    "content": "lease task",
                    "created_by": "human:bobo",
                    "claim_token": "lease-12",
                }

            async def heartbeat_task(self, task_id, *, claim_token, lease_seconds=120):
                raise TalkValidationError("claim revoked", status_code=409)

            async def complete_task(self, task_id, **kwargs):
                self.completed.append((task_id, kwargs))
                return {"id": task_id}

        async def slow_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            await asyncio.sleep(1)
            return CliRunResult(returncode=0, stdout="late", stderr="")

        async def scenario():
            with patch.object(cli_bridge, "run_cli_command", slow_run):
                client = TaskClient()
                handled = await cli_bridge.handle_queued_task(
                    {"id": 13, "workflow_status": "assigned"},
                    client=client,
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    instance_id="agent:deepseek:test",
                    command=["fake"],
                    timeout=5,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    lease_seconds=0.2,
                    heartbeat_interval=0.01,
                    diagnostics=self.diagnostics,
                )
                return handled, client

        handled, client = asyncio.run(scenario())
        self.assertFalse(handled)
        self.assertEqual(client.completed, [])
        records = self.records(event="task_lease_lost")
        self.assertEqual(len(records), 1)
        self.assertGreaterEqual(records[0]["exception"]["chain_depth"], 1)

    def test_preflight_failure_is_logged_with_cause_chain(self):
        class TaskClient:
            timeout = 10.0

            async def fetch_history(self, group_id, before=None, limit=500):
                return []

            async def claim_task(self, task_id, *, instance_id=None, lease_seconds=120):
                raise AssertionError("must not claim after failed preflight")

        async def invalid_preflight(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(returncode=0, stdout="not a preflight envelope", stderr="")

        async def scenario():
            with patch.object(cli_bridge, "run_cli_command", invalid_preflight):
                with self.assertRaises(cli_bridge.TaskPreflightError):
                    await cli_bridge.handle_queued_task(
                        {
                            "id": 14,
                            "workflow_status": "assigned",
                            "hall_group_id": "group:task-14",
                            "content": "do it",
                        },
                        client=TaskClient(),
                        member_id="agent:deepseek",
                        workdir=Path.cwd(),
                        instance_id="agent:deepseek:test",
                        command=["fake"],
                        timeout=5,
                        max_reply_chars=300,
                        runtime="dsh",
                        bridge_label="DeepSeek bridge",
                        lease_seconds=30,
                        heartbeat_interval=1,
                        diagnostics=self.diagnostics,
                    )

        asyncio.run(scenario())
        records = self.records(event="preflight_failed")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["task_id"], 14)
        self.assertGreaterEqual(records[0]["exception"]["chain_depth"], 1)

    def test_preflight_subprocess_exception_prompt_is_redacted(self):
        seen = {}

        class TaskClient:
            timeout = 10.0

            async def fetch_history(self, group_id, before=None, limit=500):
                return []

        async def broken_preflight(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            seen["prompt"] = prompt
            raise RuntimeError(f"subprocess command included: {prompt}")

        async def scenario():
            with patch.object(cli_bridge, "run_cli_command", broken_preflight):
                with self.assertRaises(cli_bridge.TaskPreflightError):
                    await cli_bridge.handle_queued_task(
                        {
                            "id": 19,
                            "workflow_status": "assigned",
                            "hall_group_id": "group:task-19",
                            "content": "prompt content that must not be persisted",
                        },
                        client=TaskClient(),
                        member_id="agent:deepseek",
                        workdir=Path.cwd(),
                        instance_id="agent:deepseek:test",
                        command=["fake"],
                        timeout=5,
                        max_reply_chars=300,
                        runtime="dsh",
                        bridge_label="DeepSeek bridge",
                        lease_seconds=30,
                        heartbeat_interval=1,
                        diagnostics=self.diagnostics,
                    )

        asyncio.run(scenario())
        self.assertIn("prompt", seen)
        raw = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self.root.rglob("events-*.jsonl")
        )
        self.assertNotIn(seen["prompt"], raw)
        self.assertNotIn("prompt content that must not be persisted", raw)

    def test_claim_failure_is_logged(self):
        class TaskClient:
            timeout = 10.0

            async def claim_task(self, task_id, *, instance_id=None, lease_seconds=120):
                raise TalkValidationError("claim broken", status_code=500)

        async def scenario():
            with self.assertRaises(TalkValidationError):
                await cli_bridge.handle_queued_task(
                    {"id": 15, "workflow_status": "assigned"},
                    client=TaskClient(),
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    instance_id="agent:deepseek:test",
                    command=["fake"],
                    timeout=5,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    diagnostics=self.diagnostics,
                )

        asyncio.run(scenario())
        records = self.records(event="task_claim_failed")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["task_id"], 15)


class ManagedHeartbeatDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)

    def tearDown(self):
        self._tempdir.cleanup()

    def test_managed_heartbeat_failure_is_persisted_with_ref(self):
        secret = "sk-managed-OPAQUE-556677"
        control_dir = self.root / "control"
        control_dir.mkdir()
        control_file = control_dir / "launch-1.ctl"
        control_file.write_text("", encoding="utf-8")

        class FakeTalkClient:
            def __init__(self, base_url, api_key, poll_interval=2.0, *, start_from_latest=False):
                self.timeout = 10.0
                self.put_calls = 0
                self.closed = False
                self.transport_event = asyncio.Event()

            async def register(self, member_id, *, display_name=None):
                return None

            def on_message(self, handler):
                self.handler = handler
                return handler

            async def _request_json(self, method, path, json_body=None):
                self.put_calls += 1
                if self.put_calls == 2:
                    raise RuntimeError(
                        f"heartbeat failed Authorization: Bearer {secret}"
                    )
                return {}

            async def run(self):
                await self.transport_event.wait()

            async def close(self):
                self.closed = True

        args = cli_bridge.build_parser().parse_args(
            [
                "--key",
                "fake-managed-key",
                "--name",
                "deepseek",
                "--command",
                "fake-command",
                "--instance-id",
                "agent:deepseek:managed-test",
                "--project-id",
                "prj_test",
                "--launch-id",
                "launch-1",
                "--runtime",
                "dsh",
                "--disable-task-queue",
                "--runtime-log-dir",
                str(self.root / "logs"),
            ]
        )

        async def scenario():
            with patch.dict(
                os.environ,
                {
                    "TALK_ROLE_SERVICE_CONTROL_FILE": str(control_file),
                },
                clear=True,
            ), patch.object(
                cli_bridge, "MANAGED_INSTANCE_HEARTBEAT_INTERVAL", 0.05
            ), patch(
                "TALK.client.TalkClient", FakeTalkClient
            ), contextlib.redirect_stderr(io.StringIO()) as stderr:
                task = asyncio.create_task(cli_bridge.run_bridge(args))
                await asyncio.sleep(0.2)
                control_file.write_bytes(b"shutdown\n")
                await asyncio.wait_for(task, timeout=4)
                return stderr.getvalue()

        stderr_text = asyncio.run(scenario())
        records = runtime_diag.query_records(
            self.root / "logs", limit=200
        )["records"]
        events = {record["event"] for record in records}
        self.assertIn("bridge_started", events)
        self.assertIn("managed_heartbeat_failure", events)
        self.assertIn("bridge_stopped", events)
        heartbeat = next(
            record for record in records if record["event"] == "managed_heartbeat_failure"
        )
        self.assertNotIn(secret, json.dumps(heartbeat, ensure_ascii=False))
        self.assertIn("log_ref=", stderr_text)
        stopped = next(
            record for record in records if record["event"] == "bridge_stopped"
        )
        self.assertIn("managed_stop", stopped["message"])


class FailureContainmentTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self._writers = []

    def tearDown(self):
        for writer in self._writers:
            writer.close()
        self._tempdir.cleanup()

    def test_queued_task_still_completes_when_log_writer_fails(self):
        diagnostics = runtime_diag.RuntimeDiagnostics(
            member_id="agent:deepseek",
            instance_id="agent:deepseek:writer-failure",
            root=self.root,
        )
        self._writers.append(diagnostics)

        class TaskClient:
            timeout = 10.0

            def __init__(self):
                self.completed = []

            async def claim_task(self, task_id, *, instance_id=None, lease_seconds=120):
                return {
                    "id": task_id,
                    "content": "task",
                    "created_by": "human:bobo",
                    "claim_token": "lease-12",
                }

            async def heartbeat_task(self, task_id, *, claim_token, lease_seconds=120):
                return {}

            async def send_text(self, text, to=None, group_id=None):
                return {"id": 600}

            async def complete_task(self, task_id, **kwargs):
                self.completed.append((task_id, kwargs))
                return {"id": task_id}

        async def fake_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(returncode=0, stdout="done", stderr="")

        async def scenario():
            with patch.object(diagnostics, "_append_locked", side_effect=OSError("disk full")), \
                 patch.object(cli_bridge, "run_cli_command", fake_run), \
                 contextlib.redirect_stderr(io.StringIO()):
                client = TaskClient()
                handled = await cli_bridge.handle_queued_task(
                    {"id": 16, "workflow_status": "assigned"},
                    client=client,
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    instance_id="agent:deepseek:test",
                    command=["fake"],
                    timeout=5,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    lease_seconds=30,
                    heartbeat_interval=1,
                    diagnostics=diagnostics,
                )
                return handled, client

        handled, client = asyncio.run(scenario())
        self.assertTrue(handled)
        self.assertEqual(len(client.completed), 1)
        self.assertEqual(client.completed[0][1]["status"], "succeeded")
        self.assertEqual(client.completed[0][1]["claim_token"], "lease-12")

    def test_cli_failure_public_reply_marks_log_write_degradation(self):
        diagnostics = runtime_diag.RuntimeDiagnostics(
            member_id="agent:deepseek",
            instance_id="agent:deepseek:public-degradation",
            root=self.root,
        )
        self._writers.append(diagnostics)

        class TaskClient:
            timeout = 10.0

            def __init__(self):
                self.sent = []
                self.completed = []

            async def claim_task(self, task_id, *, instance_id=None, lease_seconds=120):
                return {
                    "id": task_id,
                    "content": "task",
                    "created_by": "human:bobo",
                    "claim_token": "lease-12",
                }

            async def heartbeat_task(self, task_id, *, claim_token, lease_seconds=120):
                return {}

            async def send_text(self, text, to=None, group_id=None):
                self.sent.append(text)
                return {"id": 601}

            async def complete_task(self, task_id, **kwargs):
                self.completed.append((task_id, kwargs))
                return {"id": task_id}

        async def fake_run(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(returncode=1, stdout="", stderr="failed safely")

        async def scenario():
            with patch.object(diagnostics, "_append_locked", side_effect=OSError("disk full")), \
                 patch.object(cli_bridge, "run_cli_command", fake_run), \
                 contextlib.redirect_stderr(io.StringIO()):
                client = TaskClient()
                handled = await cli_bridge.handle_queued_task(
                    {"id": 18, "workflow_status": "assigned"},
                    client=client,
                    member_id="agent:deepseek",
                    workdir=Path.cwd(),
                    instance_id="agent:deepseek:test",
                    command=["fake"],
                    timeout=5,
                    max_reply_chars=300,
                    runtime="dsh",
                    bridge_label="DeepSeek bridge",
                    lease_seconds=30,
                    heartbeat_interval=1,
                    diagnostics=diagnostics,
                )
                return handled, client

        handled, client = asyncio.run(scenario())
        self.assertTrue(handled)
        self.assertEqual(client.completed[0][1]["status"], "failed")
        self.assertIn("诊断日志写入失败", client.sent[0])
        self.assertNotIn("日志引用", client.sent[0])
        self.assertNotIn("log_ref=", client.completed[0][1]["last_error"] or "")


if __name__ == "__main__":
    unittest.main()
