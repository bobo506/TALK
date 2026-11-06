"""Workspace roster reference checks against the real API."""

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
