"""Deterministic tests of relink/claim serialization and operation gates."""
import unittest
from unittest import mock

from sqlmodel import Session
from server.models import AgentTask, Project, WorkspaceOperation
from server import workspace_relink, role_startup
from tests.test_workspace_relink_api import RelinkApiTests


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.case = RelinkApiTests(methodName="test_success_and_idempotent_retry")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        with Session(self.case.engine) as session:
            task = AgentTask(project_id="p", target_member_id="agent:p", created_by="human:p", content="race", control_status="active")
            session.add(task); session.commit(); session.refresh(task); self.task_id = task.id

    def claim(self):
        return self.case.client.post(f"/api/tasks/{self.task_id}/claim", headers={"X-API-Key": "agent-key"}, json={})

    def operation(self, stage):
        with Session(self.case.engine) as session:
            row = session.get(WorkspaceOperation, "guard")
            if row is None:
                row = WorkspaceOperation(operation_id="guard", project_id="p", request_digest="synthetic", stage=stage)
            else:
                row.stage = stage
            session.add(row); session.commit()

    def test_claim_gates_and_terminal_recovery(self):
        for stage in ("started", "recovery_required"):
            self.operation(stage)
            response = self.claim()
            self.assertEqual((response.status_code, response.json()["detail"]), (409, "workspace_busy"))
            with Session(self.case.engine) as session:
                self.assertEqual(session.get(AgentTask, self.task_id).status, "queued")
        self.operation("failed")
        self.assertEqual(self.claim().status_code, 200)

    def test_completed_allows_claim(self):
        self.operation("completed")
        self.assertEqual(self.claim().status_code, 200)

    def test_claim_first_between_route_and_t1(self):
        token = self.case.preview().json()["preview_token"]
        original = workspace_relink.execute_relink
        outcome = {}
        def interleave(*args, **kwargs):
            claim = self.claim(); outcome["claim"] = (claim.status_code, claim.json().get("status"))
            return original(*args, **kwargs)
        with mock.patch.object(workspace_relink, "execute_relink", side_effect=interleave):
            response = self.case.submit(token)
        self.assertEqual(outcome["claim"], (200, "running"))
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "workspace_busy"))
        with Session(self.case.engine) as session:
            from server.workspace_registry import get_registration
            self.assertIsNone(session.get(WorkspaceOperation, "op"))
            self.assertEqual(session.get(Project, "p").project_root_path, str(self.case.old))
            self.assertEqual(get_registration(session, "p").revision, 1)
        self.assertFalse((self.case.new / ".talk" / "runtime.local.json").exists())
        print("RACE claim-first: claim=200/running relink=409/workspace_busy operation=absent root=old")

    def test_relink_first_blocks_claim_before_file_write(self):
        token = self.case.preview().json()["preview_token"]
        original = workspace_relink.files.prepare_write
        outcome = {}
        def interleave(*args, **kwargs):
            claim = self.claim(); outcome["claim"] = (claim.status_code, claim.json().get("detail"))
            return original(*args, **kwargs)
        with mock.patch.object(workspace_relink.files, "prepare_write", side_effect=interleave):
            response = self.case.submit(token)
        self.assertEqual((response.status_code, response.json().get("stage")), (200, "completed"))
        self.assertEqual(outcome["claim"], (409, "workspace_busy"))
        with Session(self.case.engine) as session:
            self.assertEqual(session.get(AgentTask, self.task_id).status, "queued")
        print("RACE relink-first: relink=200/completed claim=409/workspace_busy task=queued")

    def test_automatic_start_skips_without_state_change(self):
        self.operation("recovery_required")
        key = ("p", "activation", "agent:p")
        with Session(self.case.engine) as session, \
             mock.patch.object(role_startup, "verified_runtime", return_value=(None, None, None)), \
             mock.patch.object(role_startup, "_locked_entry", return_value=object()), \
             mock.patch.object(role_startup, "_generation", return_value=None), \
             mock.patch.object(role_startup, "_complete") as complete:
            role_startup._apply(key, "digest", None, session)
            complete.assert_called_once_with(key, "digest", "skipped", session, error="workspace_recovery_required")
            session.rollback()
