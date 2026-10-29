"""B1-a：存量补录角色（imported + 已提交 attach）可发起恢复请求。

覆盖：放行条件、仍拒绝未补录的导入角色、agents 投影的 recoverable/credential_version。
不写、不复用 role_creation_operations 是本组用例的硬断言。
"""
from server.models import ProjectRole, RoleCreationOperation, RoleProvisionRequestRow
from tests.test_role_legacy_attach import OP_KEY, LegacyAttachTestCase


class LegacyRecoverTests(LegacyAttachTestCase):
    def recover(self, **overrides):
        payload = {
            "request_key": "op-recover-0001",
            "kind": "recover",
            "confirm": True,
            "member_id": "agent:legacy",
            "expected_credential_version": 1,
        }
        payload.update(overrides)
        with self.make_client() as client:
            return client.post(
                "/api/projects/prj_alpha/role-requests",
                headers={"X-API-Key": "bobo-key"},
                json=payload,
            )

    def test_committed_attach_allows_recover_without_creation_operation(self):
        self.assertEqual(self.attach().status_code, 201)
        response = self.recover()
        self.assertIn(response.status_code, (200, 201), response.text)
        body = response.json()
        self.assertEqual(body["kind"], "recover")
        self.assertEqual(body["origin_operation_key"], OP_KEY)
        with self.session() as session:
            # 补录来源不得伪造“创建了新身份”。
            self.assertIsNone(session.get(RoleCreationOperation, OP_KEY))
            row = session.get(RoleProvisionRequestRow, "op-recover-0001")
            self.assertIsNotNone(row)
            self.assertEqual(row.origin_operation_key, OP_KEY)
            self.assertEqual(row.choice_snapshot["choice_id"], self.choice_id)
            self.assertEqual(row.choice_snapshot["model_id"], "deepseek-flash")

    def test_imported_role_without_attach_is_still_rejected(self):
        with self.session() as session:
            session.add(
                ProjectRole(
                    project_id="prj_alpha",
                    member_id="agent:second",
                    role_name="Second One",
                    origin="imported",
                    identity_exclusive=0,
                    credential_version=1,
                    created_by="human:bobo",
                )
            )
            session.commit()
        response = self.recover(member_id="agent:second", request_key="op-recover-0002")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "provision_imported_identity_unsupported"
        )

    def test_credential_version_mismatch_still_rejected_for_legacy(self):
        self.assertEqual(self.attach().status_code, 201)
        response = self.recover(expected_credential_version=2)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "role_request_credential_mismatch")

    def test_legacy_recover_can_open_provision_job_with_attach_key(self):
        """恢复请求领取后，宿主可用补录锚点键创建配置作业（不要求创建操作）。"""
        self.assertEqual(self.attach().status_code, 201)
        self.assertIn(self.recover().status_code, (200, 201))
        with self.make_client() as client:
            host = client.post(
                "/api/projects/prj_alpha/role-provision-host/enable",
                headers={"X-API-Key": "bobo-key"},
                json={"host_label": "host-legacy-1", "expected_version": 0},
            )
        self.assertEqual(host.status_code, 200, host.text)
        with self.make_client() as client:
            detail = client.get(
                "/api/projects/prj_alpha/role-requests/op-recover-0001",
                headers={"X-API-Key": "bobo-key"},
            ).json()
            claimed = client.post(
                "/api/projects/prj_alpha/role-requests/op-recover-0001/claim",
                headers={"X-API-Key": "bobo-key"},
                json={"host": "host-legacy-1", "expected_revision": detail["revision"]},
            )
        self.assertEqual(claimed.status_code, 200, claimed.text)
        with self.make_client() as client:
            job = client.post(
                "/api/projects/prj_alpha/roles/agent:legacy/provision",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "operation_key": OP_KEY,
                    "request_key": "op-recover-0001",
                    "lease_token": claimed.json()["lease_token"],
                },
            )
        self.assertEqual(job.status_code, 201, job.text)
        self.assertEqual(job.json()["operation_key"], OP_KEY)

    def test_agents_projection_exposes_recoverable_and_credential_version(self):
        self.assertEqual(self.attach().status_code, 201)
        with self.make_client() as client:
            agents = client.get(
                "/api/projects/prj_alpha/agents", headers={"X-API-Key": "bobo-key"}
            ).json()
        legacy = next(item for item in agents if item["member_id"] == "agent:legacy")
        self.assertTrue(legacy["recoverable"])
        self.assertEqual(legacy["credential_version"], 1)
        second = next(item for item in agents if item["member_id"] == "agent:second")
        self.assertFalse(second["recoverable"])
