"""272首次独立复核反例；只使用隔离假件和临时根。"""
from __future__ import annotations
import unittest
from unittest.mock import patch
from pathlib import Path
from scripts import role_service_host_diagnostics as host_diag
import tests.test_role_service_host_diagnostics as fixtures
from scripts import role_service_host as host

class HostDiagnosticsReviewTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.HostDiagnosticsTestCase()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)

    def test_runtime_child_environment_secret_is_protected(self):
        c = self.case
        secret = "opaque-native-07c2-value"
        manager = c.make_manager(child_env={})
        facts = c.facts()
        facts.child_env["DEEPSEEK_API_KEY"] = secret
        with patch.object(manager, "preflight", return_value=facts), patch.object(
            host, "spawn_hidden", side_effect=OSError("native startup failed " + secret)
        ):
            result = manager.execute_start(c.launch())
        self.assertEqual(result["outcome"], "failed")
        self.assertNotIn(secret, c.log_text())
        self.assertTrue(c.find("spawn_failed")["integrity"]["redacted"])

    def _check_fresh_stop_token(self, exited):
        c = self.case
        manager = c.make_manager()
        process = fixtures.FakeProcess()
        c.start_ready(manager, process=process)
        if exited:
            process.wait()
        token = "opaque-new-stop-claim-712d"
        failure = OSError("cannot send result " + token)
        c.client.report_errors.append(failure)
        stop = c.launch(launch_id="stop-new-generation", generation=2)
        with patch.object(manager, "_identity_evidence", return_value=None), patch.object(
            manager, "_claim_stop", return_value=token
        ), self.assertRaises(OSError) as caught:
            manager.execute_stop(stop)
        self.assertIs(caught.exception, failure)
        self.assertIn(fixtures.LAUNCH, manager._handles)
        self.assertNotIn(token, c.log_text())
        self.assertTrue(c.find("report_failed")["integrity"]["redacted"])

    def test_fresh_stop_claim_token_is_protected_for_live_child(self):
        self._check_fresh_stop_token(False)

    def test_fresh_stop_claim_token_is_protected_for_exited_child(self):
        self._check_fresh_stop_token(True)

    def test_stdout_preparation_failure_is_logged_without_changing_error(self):
        c = self.case
        blocked = c.root / "blocked-output"
        blocked.write_text("not a directory", encoding="utf-8")
        manager = c.make_manager(child_log_dir=blocked)
        with patch.object(manager, "preflight", return_value=c.facts()), patch.object(
            host, "spawn_hidden"
        ) as spawn, self.assertRaises(FileExistsError):
            manager.execute_start(c.launch())
        spawn.assert_not_called()
        self.assertFalse(manager._handles)
        self.assertFalse(c.client.reports)
        records = c.query()
        self.assertTrue(any(r.get("exception", {}).get("type") == "FileExistsError" for r in records))


    def test_second_output_open_failure_closes_first_stream(self):
        c = self.case
        logdir = c.root / "output-files"
        logdir.mkdir()
        (logdir / (fixtures.LAUNCH + ".err")).mkdir()
        manager = c.make_manager(child_log_dir=logdir)
        opened = []
        real_open = open
        def track_open(*args, **kwargs):
            stream = real_open(*args, **kwargs)
            opened.append(stream)
            return stream
        with patch.object(manager, "preflight", return_value=c.facts()), patch.object(
            host, "open", side_effect=track_open, create=True
        ), patch.object(host, "spawn_hidden") as spawn, self.assertRaises(OSError):
            manager.execute_start(c.launch())
        spawn.assert_not_called()
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)
        self.assertTrue(c.find("spawn_setup_failed")["exception"]["frames"])
        self.assertFalse(manager.client.reports)

    def test_dynamic_secret_remains_protected_when_exception_reaches_serve(self):
        c = self.case
        secret = "opaque-injected-62aa-value"
        manager = c.make_manager(child_env={})
        facts = c.facts()
        facts.child_env["DEEPSEEK_API_KEY"] = secret
        failure = RuntimeError("readiness failed " + secret)
        with patch.object(manager, "preflight", return_value=facts), patch.object(
            host, "spawn_hidden", return_value=fixtures.FakeProcess()
        ), patch.object(manager, "_wait_ready", side_effect=failure), patch.object(
            manager, "claimable_actions", return_value=[c.launch()]
        ), self.assertRaises(RuntimeError) as caught:
            manager.serve(fixtures.PROJECT, once=True)
        self.assertIs(caught.exception, failure)
        self.assertIn(fixtures.LAUNCH, manager._handles)
        self.assertNotIn(secret, c.log_text())
        self.assertTrue({"readiness_failed", "action_failed"}.issubset(c.event_names()))


    def test_relative_log_root_is_frozen_for_child_argv(self):
        c = self.case
        with patch("os.getcwd", return_value=str(c.root)):
            policy = host_diag.HostDiagnosticsPolicy.resolve(root="relative-logs", env={})
        arguments = policy.child_diagnostics_arguments()
        selected = Path(arguments[arguments.index("--runtime-log-dir") + 1])
        self.assertTrue(selected.is_absolute())
        self.assertEqual(selected, c.root / "relative-logs")

if __name__ == "__main__":
    unittest.main()
