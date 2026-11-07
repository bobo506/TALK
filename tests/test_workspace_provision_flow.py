"""Workspace roster reference checks against the real API."""

from unittest.mock import patch

from server.models import RoleProvisionRequestRow
from server.workspace_paths import member_component
from tests.test_role_provision_requests import RoleRequestApiTestCase
from tests.test_role_provision_worker import WorkerTestCase
from server.workspace_paths import key_path, profiles_dir, workspace_root


class WorkspaceRosterTests(RoleRequestApiTestCase):
    def test_workspace_roster_reference_and_invalid_reference(self):
        created, _ = self.seed_created_role_via_pipeline()
        member = created["member_id"]
        prefix = f"workspace-v1:roles/{member_component(member)}/profiles/"
        body = {
            "operation_key": "op-intent-0001",
            "identity_path": prefix + "IDENTITY.md",
            "soul_path": prefix + "SOUL.md",
            "user_path": prefix + "USER.md",
        }
        url = f"/api/projects/prj_alpha/roles/{member}/provision/roster-paths"
        with self.make_client() as client:
            response = client.post(url, headers={"X-API-Key": "bobo-key"}, json=body)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["identity_path"], body["identity_path"])
            body["soul_path"] = prefix + "../SOUL.md"
            response = client.post(url, headers={"X-API-Key": "bobo-key"}, json=body)
            self.assertEqual(response.status_code, 422)


class WorkspaceWorkerFlowTests(WorkerTestCase):
    def test_workspace_error_reports_are_validated_and_persisted(self):
        codes = (
            "key_root_mismatch", "workspace_path_unavailable", "workspace_link_refused",
            "workspace_shape_unknown", "workspace_id_invalid",
        )
        self.assertEqual(self.enable_host().status_code, 200)
        worker = self.make_worker()
        for index, code in enumerate(codes):
            with self.subTest(code=code):
                request_key = f"op-workspace-error-{index:04d}"
                created = self.create_intent(request_key, role_name=f"dev-{index}")
                self.assertEqual(created.status_code, 201, created.text)
                claimed_response = self.claim_request(request_key)
                self.assertEqual(claimed_response.status_code, 200, claimed_response.text)
                claimed = claimed_response.json()
                body = {
                    "lease_token": claimed["lease_token"],
                    "expected_revision": claimed["revision"],
                    "outcome": "failed", "error_code": "unregistered_error_code",
                }
                with self.make_client() as client:
                    rejected = client.post(
                        f"/api/projects/prj_alpha/role-requests/{request_key}/report",
                        headers={"X-API-Key": "bobo-key"}, json=body,
                    )
                self.assertEqual(rejected.status_code, 422, rejected.text)
                with self.session() as session:
                    row = session.get(RoleProvisionRequestRow, request_key)
                    self.assertEqual(row.status, "leased")
                    self.assertIsNone(row.last_error_code)
                with patch.object(worker, "report", wraps=worker.report) as report:
                    result = worker._finish_failed(request_key, claimed["lease_token"], {}, code)
                self.assertEqual(report.call_args.kwargs["error_code"], code)
                self.assertEqual(result["outcome"], "reported")
                self.assertEqual(result["error_code"], code)
                self.assertEqual(result["report_error_code"], code)
                self.assertEqual(self.get_request(request_key)["last_error_code"], code)
                with self.session() as session:
                    self.assertEqual(session.get(RoleProvisionRequestRow, request_key).last_error_code, code)

    def test_worker_does_not_report_unregistered_codes(self):
        worker = self.make_worker()
        with patch.object(worker, "_current_revision", return_value=3), \
             patch.object(worker, "report", return_value={"status": 200, "payload": {}}) as report:
            for code in ("worker_disabled", "arbitrary_unregistered_code"):
                with self.subTest(code=code):
                    result = worker._finish_failed("request", "lease", {}, code)
                    self.assertEqual(report.call_args.kwargs["error_code"], "http_error")
                    self.assertEqual(result["report_error_code"], "http_error")

    def test_non_git_request_creates_workspace_and_profiles(self):
        self.assertEqual(self.enable_host().status_code, 200)
        self.assertEqual(self.create_intent("op-workspace-flow-0001").status_code, 201)
        result = self.make_worker(repo_root=self._tmpdir).process("op-workspace-flow-0001")
        self.assertEqual(result["outcome"], "provisioned", result)
        member = result["member_id"]
        workspace = workspace_root(self._tmpdir, "prj_alpha")
        self.assertTrue((workspace / "workspace.json").is_file())
        self.assertTrue(key_path(self._tmpdir, "prj_alpha", member).is_file())
        for name in ("IDENTITY.md", "SOUL.md", "USER.md"):
            self.assertTrue((profiles_dir(self._tmpdir, "prj_alpha", member) / name).is_file(), name)
