"""新建角色原生授权、启动门禁与完整启停的隔离合成测试。"""
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from sqlmodel import select

from server.kimi_native_setup import NativeSetupManager, ensure_native_setup_required, _safe_url
from server.models import (
    ProjectRoleBinding, RoleNativeSetup, RoleProvisionJob, RoleServiceState, RunnerRegistry,
)
from server.role_services import start_role_service
from tests.test_role_services import RoleServiceTestCase, PROJECT_ID, RUNNER_ID, HOST, iso_ago


class FakeProcess:
    def __init__(self, lines=(), returncode=0, gate=None):
        self.stdout = list(lines)
        self.returncode = returncode
        self.gate = gate
        self.terminated = False

    def wait(self, timeout=None):
        if self.gate is not None:
            if not self.gate.wait(2):
                raise TimeoutError("synthetic process did not finish")
        return self.returncode

    def poll(self):
        return self.returncode if self.gate is None or self.gate.is_set() else None

    def terminate(self):
        self.terminated = True
        self.returncode = 1
        if self.gate is not None:
            self.gate.set()

    def kill(self):
        self.terminate()


class KimiNativeSetupTests(RoleServiceTestCase):
    def setUp(self):
        super().setUp()
        with self.session() as session:
            runner = session.get(RunnerRegistry, RUNNER_ID)
            runner.runtime = "kimi-code"
            session.add(runner)
            session.add(RoleProvisionJob(operation_key="op-alpha-0001", project_id=PROJECT_ID,
                member_id=self.role_a, status="succeeded", revision=4,
                credential_version=1, created_by="human:bobo"))
            ensure_native_setup_required(PROJECT_ID, self.role_a, session)
            session.commit()
        self.manager = NativeSetupManager()
        self.addCleanup(self._drain)

    def _drain(self):
        with self.manager._lock:
            attempts = list(self.manager._attempts.values())
            self.manager._attempts.clear()
        for _, attempt in attempts:
            if attempt.process.gate is not None:
                attempt.process.gate.set()

    def _get(self):
        with self.session() as session:
            return self.manager.get(PROJECT_ID, self.role_a, session)

    def _wait_status(self, status):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            row = self._get()
            if row.status == status:
                return row
            time.sleep(0.01)
        self.fail(f"status did not become {status}: {self._get().status}")

    def _start_manager(self, process, finish=None):
        attempt = SimpleNamespace(process=process, released=False)
        patchers = [patch("scripts.kimi_role_setup.begin_native_login", return_value=attempt),
            patch("scripts.kimi_role_setup.finish_native_login", side_effect=finish or (lambda _: None)),
            patch("scripts.kimi_role_setup.release_native_login", side_effect=lambda a: setattr(a, "released", True))]
        begin, done, _ = [p.start() for p in patchers]
        for p in patchers:
            self.addCleanup(p.stop)
        with self.session() as session:
            row = self.manager.start(PROJECT_ID, self.role_a, 1, "human:bobo", session)
        self.assertEqual(begin.call_count, 1)
        return row, done

    def test_required_blocks_start_without_changing_legacy_no_row_behavior(self):
        with self.session() as session:
            with self.assertRaisesRegex(Exception, "native_authorization_required"):
                start_role_service(PROJECT_ID, self.role_a, self.human_member(), session)
            session.rollback()
            self.assertEqual(len(session.exec(select(RoleServiceState)).all()), 0)
            session.delete(session.get(RoleNativeSetup, (PROJECT_ID, self.role_a)))
            session.commit()
            result = start_role_service(PROJECT_ID, self.role_a, self.human_member(), session)
            self.assertEqual(result.generation, 1)  # 既有无记录角色保持原行为。

    def test_authorization_ready_uses_selected_model_and_allows_full_start_ready_stop(self):
        process = FakeProcess(["open https://kimi.example/device?state=public#fragment\n"])
        _, done = self._start_manager(process)
        ready = self._wait_status("ready")
        self.assertEqual(done.call_count, 1)
        self.assertIsNone(ready.authorization_url)
        self.assertFalse(ready.can_start)
        started = self.start()
        self.assertEqual(started.status_code, 200, started.text)
        # 上面已显式验证从未启动到受理；使用本次 launch 完成 claim/instance/report。
        body = started.json()
        claimed = self.claim(body["launch_id"], {"host": HOST,
            "expected_instance_id": body["expected_instance_id"]}, key=self.role_a_key)
        self.assertEqual(claimed.status_code, 200, claimed.text)
        claim_body = claimed.json()
        self.assertEqual(self.bind_instance(body, claim_body).status_code, 200)
        self.assertEqual(self.ready_report(body, claim_body).status_code, 200)
        running = self.list_services().json()[0]
        self.assertEqual(running["observed"], "running")
        self.assertEqual(running["readiness_service"], "ready")
        self.assertEqual(running["native_login"], "configured")
        stopped = self.stop().json()
        stop_claim = self.claim(stopped["launch_id"], {"host": HOST,
            "expected_instance_id": stopped["expected_instance_id"],
            "owner_token": claim_body["owner_token"]}, key=self.role_a_key).json()
        reported = self.report(stopped["launch_id"], {"generation": stopped["generation"],
            "action": "stop", "claim_token": stop_claim["claim_token"],
            "owner_token": claim_body["owner_token"], "outcome": "stopped", "host": HOST,
            "pid": 4321, "process_started_at": iso_ago(5)}, key=self.role_a_key)
        self.assertEqual(reported.status_code, 200, reported.text)
        state = self.state_row()
        self.assertEqual(state.observed_state, "stopped")
        self.assertIsNone(state.owner_host)
        self.assertIsNone(state.process_launch_id)

    def test_cancel_and_duplicate_start_keep_failure_truth(self):
        gate = threading.Event()
        process = FakeProcess(["https://kimi.example/auth\n"], gate=gate)
        row, done = self._start_manager(process)
        waiting = self._wait_status("awaiting_authorization")
        self.assertEqual(waiting.authorization_url, "https://kimi.example/auth")
        with self.session() as session:
            with self.assertRaisesRegex(Exception, "native_setup_active"):
                self.manager.start(PROJECT_ID, self.role_a, waiting.revision, "human:bobo", session)
        with patch("scripts.kimi_role_setup.cancel_native_login",
                side_effect=lambda attempt: attempt.process.terminate()):
            with self.session() as session:
                canceled = self.manager.cancel(PROJECT_ID, self.role_a, waiting.revision, session)
        self.assertEqual(canceled.status, "failed")
        self.assertEqual(canceled.error_code, "native_authorization_canceled")
        self.assertTrue(process.terminated)
        time.sleep(0.05)
        self.assertEqual(self._get().error_code, "native_authorization_canceled")
        self.assertEqual(done.call_count, 0)
        self.manager._update(PROJECT_ID, self.role_a, status="awaiting_authorization", token="stale")
        self.assertEqual(self._get().status, "failed")
        self.assertEqual(self.start().status_code, 409)

    def test_environment_failure_authorization_failure_and_interrupted_recovery(self):
        with patch("scripts.kimi_role_setup.begin_native_login", side_effect=RuntimeError("SECRET-NOT-PUBLIC")):
            with self.session() as session:
                failed = self.manager.start(PROJECT_ID, self.role_a, 1, "human:bobo", session)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error_code, "native_setup_failed")
        self.assertNotIn("SECRET", json.dumps(failed.model_dump(mode="json")))
        process = FakeProcess(returncode=7)
        with self.session() as session:
            current = session.get(RoleNativeSetup, (PROJECT_ID, self.role_a))
            revision = current.revision
        attempt = SimpleNamespace(process=process, released=False)
        with patch("scripts.kimi_role_setup.begin_native_login", return_value=attempt), \
             patch("scripts.kimi_role_setup.release_native_login", side_effect=lambda a: setattr(a, "released", True)):
            with self.session() as session:
                self.manager.start(PROJECT_ID, self.role_a, revision, "human:bobo", session)
        self.assertEqual(self._wait_status("failed").error_code, "native_authorization_failed")
        with self.session() as session:
            row = session.get(RoleNativeSetup, (PROJECT_ID, self.role_a))
            row.status = "starting"
            session.add(row)
            session.commit()
        self.assertEqual(self._get().error_code, "native_setup_interrupted")

    def test_permissions_revision_and_public_shape(self):
        path = f"/api/projects/{PROJECT_ID}/roles/{quote(self.role_a, safe='')}/native-setup"
        with self.make_client() as client:
            forbidden = client.get(path, headers={"X-API-Key": self.role_a_key})
            self.assertEqual(forbidden.status_code, 403)
            response = client.get(path, headers={"X-API-Key": "bobo-key"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "required")
        self.assertEqual(body["revision"], 1)
        for forbidden_key in ("api_key", "token", "home", "path", "argv", "stdout"):
            self.assertNotIn(forbidden_key, body)
        with self.session() as session:
            with self.assertRaisesRegex(Exception, "native_setup_revision_conflict"):
                self.manager.start(PROJECT_ID, self.role_a, 99, "human:bobo", session)

    def test_real_http_start_and_idempotent_ready(self):
        path = f"/api/projects/{PROJECT_ID}/roles/{quote(self.role_a, safe='')}/native-setup"
        attempt = SimpleNamespace(process=FakeProcess(), released=False)
        with patch("server.kimi_native_setup.manager", self.manager), \
             patch("scripts.kimi_role_setup.begin_native_login", return_value=attempt) as begin, \
             patch("scripts.kimi_role_setup.finish_native_login", return_value="added"), \
             patch("scripts.kimi_role_setup.release_native_login", side_effect=lambda a: setattr(a, "released", True)):
            with self.make_client() as client:
                denied = client.post(path + "/start", headers={"X-API-Key": self.role_a_key},
                    json={"confirm": True, "expected_revision": 1})
                self.assertEqual(denied.status_code, 403)
                accepted = client.post(path + "/start", headers={"X-API-Key": "bobo-key"},
                    json={"confirm": True, "expected_revision": 1})
                self.assertEqual(accepted.status_code, 200, accepted.text)
                ready = self._wait_status("ready")
                replay = client.post(path + "/start", headers={"X-API-Key": "bobo-key"},
                    json={"confirm": True, "expected_revision": ready.revision})
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json()["status"], "ready")
            self.assertEqual(begin.call_count, 1)

    def test_binding_drift_invalidates_old_ready(self):
        with self.session() as session:
            row = session.get(RoleNativeSetup, (PROJECT_ID, self.role_a))
            row.status = "ready"
            session.add(row)
            binding = session.get(ProjectRoleBinding, (PROJECT_ID, self.role_a))
            binding.model_id = "different-model"
            session.add(binding)
            session.commit()
        self.assertEqual(self._get().error_code, "native_model_selection_changed")
        self.assertEqual(self.start().status_code, 409)
        with self.session() as session:
            with self.assertRaisesRegex(Exception, "native_model_selection_changed"):
                self.manager.start(PROJECT_ID, self.role_a, 1, "human:bobo", session)

    def test_url_filter_and_choice_invalidation(self):
        self.assertEqual(_safe_url("https://kimi.example/auth?x=1#private"), "https://kimi.example/auth?x=1")
        self.assertIsNone(_safe_url("http://kimi.example/auth"))
        self.assertIsNone(_safe_url("https://user:secret@kimi.example/auth"))
        with self.session() as session:
            row = session.get(RoleNativeSetup, (PROJECT_ID, self.role_a))
            row.status = "ready"
            row.choice_id = "rmc_old"
            session.add(row)
            session.commit()
        service = self.list_services().json()[0]
        self.assertEqual(service["native_login"], "unverified")
        self.assertFalse(service["can_start"])
        self.assertEqual(self.start().status_code, 409)


if __name__ == "__main__":
    import unittest
    unittest.main()
