"""Isolated tests for the human orphan recovery boundary."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import json
import os
import socket
import subprocess
import sys

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import select

from scripts import role_service_recovery as proof
from server.models import AgentInstance, AgentTask, RoleServiceRecovery
from tests.test_project_roles import encode
from tests.test_role_services import RoleServiceTestCase, PROJECT_ID, OTHER_PROJECT_ID


class OrphanApiTests(RoleServiceTestCase):
    def setUp(self):
        super().setUp()
        self.launch, self.claimed = self.start_and_claim()
        self.bind_instance(self.launch, self.claimed)
        self.assertEqual(self.ready_report(self.launch, self.claimed).status_code, 200)
        self.body = {"operation_key": "orphan-test-123", "expected_generation": self.launch["generation"],
                     "reason": "人工确认原宿主已退出"}
        self.binding = patch("server.local_runtime.configured_runtime", return_value=(None, {"project_id": PROJECT_ID}))
        self.resolve = patch("server.role_host_resolution.resolve_recovery_host", return_value=SimpleNamespace(health_file=Path("health"), host_entry=Path("host")))
        self.proof = patch("scripts.role_service_recovery.orphan_local_proof", return_value={"already_exited": False, "created_at": 100.0})
        self.term = patch("scripts.role_service_recovery.terminate_orphan", return_value={"pid": 4321, "already_exited": False, "exit_code": 1, "exit_confirmed": True, "termination_initiated": True})
        for p in (self.binding, self.resolve, self.proof):
            p.start()
            self.addCleanup(p.stop)
        self.term_mock = self.term.start()
        self.addCleanup(self.term.stop)

    def post(self, body=None, key="bobo-key"):
        with self.make_client() as client:
            return client.post(f"/api/projects/{PROJECT_ID}/roles/{encode(self.role_a)}/service/recover-orphan",
                               headers={"X-API-Key": key}, json=self.body if body is None else body)

    def audits(self):
        with self.session() as session:
            return session.exec(select(RoleServiceRecovery)).all()

    def test_permission_binding_generation_and_identity_are_pretermination(self):
        before = self.state_row().model_dump()
        self.assertEqual(self.post(key=self.role_a_key).status_code, 403)
        with patch("server.local_runtime.configured_runtime", return_value=None):
            self.assertEqual(self.post().status_code, 503)
        response = self.post({**self.body, "expected_generation": 999})
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "recovery_generation_conflict"))
        self.assertEqual(self.state_row().model_dump(), before)
        with self.session() as session:
            instance = session.get(AgentInstance, self.claimed["expected_instance_id"])
            instance.pid = 999999
            session.add(instance)
            session.commit()
        self.assertEqual(self.post().json()["detail"], "orphan_identity_mismatch")
        self.assertEqual(self.audits(), [])
        self.term_mock.assert_not_called()

    def test_busy_gate_project_scope_and_replay(self):
        with self.session() as session:
            instance = session.get(AgentInstance, self.claimed["expected_instance_id"])
            a = AgentTask(project_id=PROJECT_ID, target_member_id=self.role_a, created_by="human:bobo", content="task", status="running", instance_id=instance.id, claim_token="x", lease_expires_at=datetime.now(timezone.utc))
            b = AgentTask(project_id=OTHER_PROJECT_ID, target_member_id=self.role_a, created_by="human:bobo", content="other", status="queued", instance_id=instance.id)
            session.add(a); session.add(b); session.commit()
            a_id, b_id = a.id, b.id
            instance.current_task_id = str(a_id)
            session.add(instance); session.commit()
        # The test client's startup also applies legacy task normalization.
        with self.make_client():
            pass
        with self.session() as session:
            task_before = session.get(AgentTask, a_id).model_dump()
            instance_before = session.get(AgentInstance, self.claimed["expected_instance_id"]).model_dump()
        before = self.state_row().model_dump()
        response = self.post()
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "orphan_tasks_active"))
        self.term_mock.assert_not_called()
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(self.audits(), [])
        with self.session() as session:
            self.assertEqual(session.get(AgentTask, a_id).model_dump(), task_before)
            self.assertEqual(session.get(AgentInstance, self.claimed["expected_instance_id"]).model_dump(), instance_before)
        response = self.post({**self.body, "confirm_task_interrupt": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["interrupted_task_ids"], [a_id])
        with self.session() as session:
            a, b = session.get(AgentTask, a_id), session.get(AgentTask, b_id)
            self.assertEqual((a.status, a.last_error, a.claim_token), ("failed", "orphan_terminated_by_human", None))
            self.assertEqual(a.workflow_status, "failed")
            self.assertIsNone(a.lease_expires_at)
            self.assertIsNotNone(a.finished_at)
            self.assertEqual(b.status, "queued")
            self.assertIsNone(session.get(AgentInstance, self.claimed["expected_instance_id"]).current_task_id)
        replay = self.post({**self.body, "confirm_task_interrupt": True})
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["recovery"]["replayed"])
        self.assertEqual(self.term_mock.call_count, 1)
        with patch("server.routes.role_services.require_local_runtime", return_value=None):
            restarted = self.start()
        self.assertEqual(restarted.status_code, 200, restarted.text)

    def test_already_exited_and_termination_failure_rollback(self):
        before = self.state_row().model_dump()
        with patch("scripts.role_service_recovery.terminate_orphan", side_effect=proof.OrphanTerminationFailed(4321, True)):
            response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["termination_initiated"], True)
        self.assertEqual(response.json()["detail"]["exit_confirmed"], False)
        self.assertEqual(response.json()["detail"]["terminated_pid"], 4321)
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(self.audits(), [])
        with patch("scripts.role_service_recovery.orphan_local_proof", return_value={"already_exited": True}):
            result = self.post()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["already_exited"])

    def test_proof_rejection_matrix_never_terminates_or_writes(self):
        before = self.state_row().model_dump()
        for code in ("recovery_wrong_local_host", "orphan_manager_alive", "orphan_process_unverified", "recovery_os_unsupported"):
            with self.subTest(code=code), patch("scripts.role_service_recovery.orphan_local_proof", side_effect=proof.HostError(code)):
                response = self.post()
                self.assertEqual((response.status_code, response.json()["detail"]), (409, code))
                self.assertEqual(self.state_row().model_dump(), before)
                self.assertEqual(self.audits(), [])
        self.term_mock.assert_not_called()

    def test_current_task_id_is_also_interrupted(self):
        with self.session() as session:
            task = AgentTask(project_id=PROJECT_ID, target_member_id=self.role_a, created_by="human:bobo", content="current", status="queued")
            session.add(task)
            session.flush()
            task_id = task.id
            instance = session.get(AgentInstance, self.claimed["expected_instance_id"])
            instance.current_task_id = str(task_id)
            session.add(instance)
            session.commit()
        self.assertEqual(self.post().json()["detail"], "orphan_tasks_active")
        response = self.post({**self.body, "confirm_task_interrupt": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["interrupted_task_ids"], [task_id])
        with self.session() as session:
            self.assertEqual(session.get(AgentTask, task_id).workflow_status, "failed")
            self.assertIsNone(session.get(AgentInstance, self.claimed["expected_instance_id"]).current_task_id)

    def test_unclaimed_and_other_instance_tasks_remain_queued(self):
        with self.session() as session:
            other = AgentInstance(id="other-instance", member_id=self.role_a, runtime="codex", status="idle", project_id=PROJECT_ID)
            session.add(other)
            session.flush()
            unclaimed = AgentTask(project_id=PROJECT_ID, target_member_id=self.role_a, created_by="human:bobo", content="unclaimed", status="queued")
            claimed_elsewhere = AgentTask(project_id=PROJECT_ID, target_member_id=self.role_a, created_by="human:bobo", content="other instance", status="queued", instance_id=other.id)
            session.add(unclaimed); session.add(claimed_elsewhere); session.commit()
            task_ids = (unclaimed.id, claimed_elsewhere.id)
        with self.make_client():
            pass
        with self.session() as session:
            before = {task_id: session.get(AgentTask, task_id).model_dump() for task_id in task_ids}
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["interrupted_task_ids"], [])
        with self.session() as session:
            for task_id, snapshot in before.items():
                self.assertEqual(session.get(AgentTask, task_id).model_dump(), snapshot)

    def test_invalid_operation_keys_rejected_before_termination(self):
        before = self.state_row().model_dump()
        for key in ("bad key 123", "_invalid-key"):
            with self.subTest(key=key):
                self.assertEqual(self.post({**self.body, "operation_key": key}).status_code, 422)
        self.term_mock.assert_not_called()
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(self.audits(), [])

    def test_current_pointer_to_paused_task_does_not_interrupt_it(self):
        with self.session() as session:
            task = AgentTask(project_id=PROJECT_ID, target_member_id=self.role_a, created_by="human:bobo", content="paused", status="paused")
            session.add(task); session.flush()
            task_id = task.id
            instance = session.get(AgentInstance, self.claimed["expected_instance_id"])
            instance.current_task_id = str(task_id)
            session.add(instance); session.commit()
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["interrupted_task_ids"], [])
        with self.session() as session:
            self.assertEqual(session.get(AgentTask, task_id).status, "paused")
            self.assertIsNone(session.get(AgentInstance, self.claimed["expected_instance_id"]).current_task_id)

    def test_wait_timeout_at_api_has_no_database_writes(self):
        before = self.state_row().model_dump()
        kernel = Mock()
        kernel.OpenProcess.return_value = 42
        kernel.GetExitCodeProcess.side_effect = lambda handle, ptr: (setattr(ptr._obj, "value", 259) or True)
        kernel.TerminateProcess.return_value = True
        kernel.WaitForSingleObject.return_value = 258
        self.term.stop()
        with patch.object(proof.ctypes, "WinDLL", return_value=kernel), \
                patch("scripts.talk_runtime._orphan_handle_creation_time", return_value=100.0):
            response = self.post()
        detail = response.json()["detail"]
        self.assertEqual(response.status_code, 409)
        self.assertEqual(detail["code"], "orphan_terminate_failed")
        self.assertEqual((detail["termination_initiated"], detail["exit_confirmed"], detail["terminated_pid"]), (True, False, 4321))
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(self.audits(), [])

    def test_database_error_rolls_back_then_already_exited_retry(self):
        before = self.state_row().model_dump()
        with self.session() as session:
            instance = session.get(AgentInstance, self.claimed["expected_instance_id"])
            task = AgentTask(project_id=PROJECT_ID, target_member_id=self.role_a, created_by="human:bobo", content="rollback", status="running", instance_id=instance.id, claim_token="token")
            session.add(task); session.flush()
            task_id = task.id
            instance.current_task_id = str(task_id)
            session.add(instance); session.commit()
        with self.make_client():
            pass
        with self.session() as session:
            task_before = session.get(AgentTask, task_id).model_dump()
            instance_before = session.get(AgentInstance, self.claimed["expected_instance_id"]).model_dump()
            session.execute(text("CREATE TRIGGER orphan_test_fail BEFORE INSERT ON role_service_recoveries BEGIN SELECT RAISE(ABORT, 'orphan test'); END"))
            session.commit()
        try:
            failed = self.post({**self.body, "confirm_task_interrupt": True})
            self.assertEqual(failed.status_code, 500)
            self.assertEqual(failed.json()["detail"]["code"], "orphan_recovery_write_failed")
            self.assertTrue(failed.json()["detail"]["exit_confirmed"])
            self.assertEqual(self.state_row().model_dump(), before)
            self.assertEqual(self.audits(), [])
            with self.session() as session:
                self.assertEqual(session.get(AgentTask, task_id).model_dump(), task_before)
                self.assertEqual(session.get(AgentInstance, self.claimed["expected_instance_id"]).model_dump(), instance_before)
        finally:
            with self.session() as session:
                session.execute(text("DROP TRIGGER orphan_test_fail"))
                session.commit()
        with patch("scripts.role_service_recovery.orphan_local_proof", return_value={"already_exited": True}):
            response = self.post({**self.body, "confirm_task_interrupt": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["already_exited"])


class LocalProofTests(TestCase):
    def test_host_manager_and_process_guards(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            health = root / "health.json"
            health.write_text(json.dumps({"project_id": "p", "member_id": "m", "pid": 11,
                "seen_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
            started = datetime.now(timezone.utc)
            plan = {"project_id": "p", "member_id": "m", "expected_owner_host": socket.gethostname(),
                    "expected_process_launch_id": "l", "expected_instance_id": "i", "process_pid": 12,
                    "process_started_at": started.isoformat(), "instance_last_seen_at": started.isoformat()}
            argv = 'python -m bridges.codex_bridge --project-id p --name m --launch-id l --instance-id i'
            inv = lambda: [{"ProcessId": 12, "CommandLine": argv}]
            probe = lambda pid: "absent" if pid == 11 else "present"
            with patch.object(proof.os, "name", "nt"), patch.object(proof, "process_argv", side_effect=lambda s: s.split()):
                result = proof.orphan_local_proof(plan, health, root / "entry", probe=probe, inventory=inv, creation_time=lambda _: started.timestamp())
                self.assertFalse(result["already_exited"])
                for altered, expected in (({"expected_owner_host": "remote-host"}, "recovery_wrong_local_host"),):
                    with self.assertRaises(proof.HostError) as exc:
                        proof.orphan_local_proof({**plan, **altered}, health, root / "entry", probe=probe, inventory=inv)
                    self.assertEqual(exc.exception.code, expected)
                for p, create, command, expected in (
                    (lambda _: "present", lambda _: started.timestamp(), argv, "orphan_manager_alive"),
                    (probe, lambda _: None, argv, "orphan_process_unverified"),
                    (probe, lambda _: started.timestamp(), argv.replace("--name m", "--name other"), "orphan_process_unverified"),
                    (probe, lambda _: started.timestamp(), argv.replace("--name m", ""), "orphan_process_unverified"),
                ):
                    with self.assertRaises(proof.HostError) as exc:
                        proof.orphan_local_proof(plan, health, root / "entry", probe=p, creation_time=create,
                            inventory=lambda: [{"ProcessId": 12, "CommandLine": command}])
                    self.assertEqual(exc.exception.code, expected)
                with patch.object(proof, "recorded_process_state", side_effect=["absent", "pid_reused"]):
                    with self.assertRaises(proof.HostError) as exc:
                        proof.orphan_local_proof(plan, health, root / "entry")
                    self.assertEqual(exc.exception.code, "orphan_process_unverified")
                self.assertTrue(proof.orphan_local_proof(plan, health, root / "entry", probe=lambda _: "absent")["already_exited"])

    def test_wait_timeout_after_termination_is_reported(self):
        kernel = Mock()
        kernel.OpenProcess.return_value = 42
        kernel.GetExitCodeProcess.side_effect = lambda handle, ptr: (setattr(ptr._obj, "value", 259) or True)
        kernel.TerminateProcess.return_value = True
        kernel.WaitForSingleObject.return_value = 258
        with patch.object(proof.os, "name", "nt"), patch.object(proof.ctypes, "WinDLL", return_value=kernel), \
                patch("scripts.talk_runtime._orphan_handle_creation_time", return_value=100.0):
            with self.assertRaises(proof.OrphanTerminationFailed) as exc:
                proof.terminate_orphan(123, 100.0)
        self.assertTrue(exc.exception.initiated)
        self.assertEqual(exc.exception.pid, 123)
        kernel.CloseHandle.assert_called_once()
        kernel.WaitForSingleObject.side_effect = ValueError("wait failed")
        with patch.object(proof.os, "name", "nt"), patch.object(proof.ctypes, "WinDLL", return_value=kernel), \
                patch("scripts.talk_runtime._orphan_handle_creation_time", return_value=100.0):
            with self.assertRaises(proof.OrphanTerminationFailed) as exc:
                proof.terminate_orphan(123, 100.0)
        self.assertTrue(exc.exception.initiated)

    def test_terminate_owned_dummy_process(self):
        if os.name != "nt":
            self.skipTest("Windows-only process handle")
        from scripts.role_service_host import process_creation_time
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            created = process_creation_time(process.pid)
            self.assertIsNotNone(created)
            result = proof.terminate_orphan(process.pid, created)
            self.assertTrue(result["termination_initiated"])
            self.assertTrue(result["exit_confirmed"])
            self.assertEqual(process.wait(timeout=5), result["exit_code"])
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
