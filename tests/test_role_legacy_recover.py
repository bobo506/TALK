"""B1-a：存量补录角色（imported + 已提交 attach）可发起恢复请求。

覆盖：放行条件、仍拒绝未补录的导入角色、agents 投影的 recoverable/credential_version。
不写、不复用 role_creation_operations 是本组用例的硬断言。

2026-10-29 复核补齐（WorkBuddy）：原 5 项只到"建作业 201"，恢复链最后一步
``require_completion_facts``（完成回写）与两条拒绝分支无永久用例，本组追加：
补录锚点缺失/choice 失配/runner 失配/有锚点但无 recover 请求，以及三步成功后回写。
"""
from server.models import (
    ROLE_REQUEST_KIND_CREATE,
    ProjectAgent,
    ProjectRole,
    RoleCreationOperation,
    RoleLegacyAttachOperation,
    RoleProvisionRequestRow,
    RunnerModelChoice,
    RunnerRegistry,
)
from server.role_provision_requests import (
    expected_binding_fingerprint,
    require_completion_facts,
)
from tests.test_role_legacy_attach import OP_KEY, RUNNER_ID, LegacyAttachTestCase

#: 复核补齐用例使用的恢复请求键与宿主标签（与原有 0001 号用例互不干扰）。
RECOVER_KEY = "op-recover-0100"
HOST_LABEL = "host-legacy-writeback"


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

    # ── 恢复链后半段：完成回写（2026-10-29 复核补齐）────────────────────

    def prepare_legacy_job(self):
        """补录 → 恢复请求 → 启用宿主并领取 → 建配置作业；返回 ``(job, lease_token)``。"""
        self.assertEqual(self.attach().status_code, 201)
        response = self.recover(request_key=RECOVER_KEY)
        self.assertIn(response.status_code, (200, 201), response.text)
        with self.make_client() as client:
            host = client.post(
                "/api/projects/prj_alpha/role-provision-host/enable",
                headers={"X-API-Key": "bobo-key"},
                json={"host_label": HOST_LABEL, "expected_version": 0},
            )
        self.assertEqual(host.status_code, 200, host.text)
        with self.make_client() as client:
            detail = client.get(
                f"/api/projects/prj_alpha/role-requests/{RECOVER_KEY}",
                headers={"X-API-Key": "bobo-key"},
            ).json()
            claimed = client.post(
                f"/api/projects/prj_alpha/role-requests/{RECOVER_KEY}/claim",
                headers={"X-API-Key": "bobo-key"},
                json={"host": HOST_LABEL, "expected_revision": detail["revision"]},
            )
        self.assertEqual(claimed.status_code, 200, claimed.text)
        lease_token = claimed.json()["lease_token"]
        with self.make_client() as client:
            job = client.post(
                "/api/projects/prj_alpha/roles/agent:legacy/provision",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "operation_key": OP_KEY,
                    "request_key": RECOVER_KEY,
                    "lease_token": lease_token,
                },
            )
        self.assertEqual(job.status_code, 201, job.text)
        return job.json(), lease_token

    def acknowledge(self, step, revision, credential_version, lease_token, *, request_key=RECOVER_KEY):
        """宿主单步 ACK；请求驱动路径必须同时带 ``request_key`` 与租约。"""
        with self.make_client() as client:
            return client.post(
                "/api/projects/prj_alpha/roles/agent:legacy/provision/ack",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "operation_key": OP_KEY,
                    "request_key": request_key,
                    "step": step,
                    "attempt": 1,
                    "revision": revision,
                    "credential_version": credential_version,
                    "state": "succeeded",
                    "error_code": None,
                    "lease_token": lease_token,
                },
            )

    def test_three_steps_then_completion_writeback_passes_for_legacy(self):
        """三步成功后 ``require_completion_facts`` 必须放行，不得要求创建操作。"""
        job, lease_token = self.prepare_legacy_job()
        version = int(job.get("credential_version") or 1)
        for index, step in enumerate(("profile", "key_file", "preflight")):
            response = self.acknowledge(step, index + 1, version, lease_token)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "succeeded")
        with self.session() as session:
            row = session.get(RoleProvisionRequestRow, RECOVER_KEY)
            self.assertEqual(row.origin_operation_key, OP_KEY)
            # 正向：不抛异常即通过；同时补录来源仍不得伪造创建操作。
            require_completion_facts(row, session)
            self.assertIsNone(session.get(RoleCreationOperation, OP_KEY))

    def test_create_kind_without_creation_operation_still_refused_on_writeback(self):
        """create 不得借补录锚点通过完成回写（legacy 分支仅限 recover）。"""
        self.prepare_legacy_job()
        with self.session() as session:
            row = session.get(RoleProvisionRequestRow, RECOVER_KEY)
            row.kind = ROLE_REQUEST_KIND_CREATE
            session.add(row)
            session.commit()
            with self.assertRaises(Exception) as caught:
                require_completion_facts(row, session)
        self.assertEqual(
            getattr(caught.exception, "detail", ""), "role_request_completion_incomplete"
        )

    def test_missing_attach_refused_on_writeback(self):
        """补录锚点不存在时，完成回写不得放行。"""
        self.prepare_legacy_job()
        with self.session() as session:
            session.delete(session.get(RoleLegacyAttachOperation, OP_KEY))
            session.commit()
            row = session.get(RoleProvisionRequestRow, RECOVER_KEY)
            with self.assertRaises(Exception) as caught:
                require_completion_facts(row, session)
        self.assertEqual(
            getattr(caught.exception, "detail", ""), "role_request_completion_incomplete"
        )

    # ── 补录来源不可用：拒绝恢复，不按 model_id 反查猜测 ────────────────

    def test_missing_choice_rejects_legacy_recover(self):
        self.assertEqual(self.attach().status_code, 201)
        with self.session() as session:
            session.delete(session.get(RunnerModelChoice, self.choice_id))
            session.commit()
        response = self.recover(request_key="op-recover-0201")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "provision_imported_identity_unsupported"
        )

    def test_missing_runner_rejects_legacy_recover(self):
        self.assertEqual(self.attach().status_code, 201)
        with self.session() as session:
            session.delete(session.get(RunnerRegistry, RUNNER_ID))
            session.commit()
        response = self.recover(request_key="op-recover-0202")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "provision_imported_identity_unsupported"
        )

    def test_choice_runner_mismatch_rejects_legacy_recover(self):
        self.assertEqual(self.attach().status_code, 201)
        with self.session() as session:
            choice = session.get(RunnerModelChoice, self.choice_id)
            choice.runner_id = "runner-detached"
            session.add(choice)
            session.commit()
        response = self.recover(request_key="op-recover-0203")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "provision_imported_identity_unsupported"
        )

    def test_attach_key_without_recover_request_is_refused(self):
        """``_require_provision_identity`` 反向：只有补录锚点、没有 recover 请求不得开作业。"""
        self.assertEqual(self.attach().status_code, 201)
        with self.make_client() as client:
            job = client.post(
                "/api/projects/prj_alpha/roles/agent:legacy/provision",
                headers={"X-API-Key": "bobo-key"},
                json={"operation_key": OP_KEY},
            )
        self.assertEqual(job.status_code, 409)
        self.assertEqual(
            job.json()["detail"], "provision_imported_identity_unsupported"
        )

    # ── 凭据轮换（B1-b）：补录来源可在恢复意图下轮换一次 ──────────────────

    def claim_recover(self, request_key=RECOVER_KEY):
        """创建并领取恢复请求，返回 ``(request_key, lease_token)``。"""
        self.assertEqual(self.attach().status_code, 201)
        # 补录夹具默认把 agent:legacy 也挂在 prj_beta 名册；换 Key 要求该身份
        # 仅在本项目被引用，这里先移除跨项目名册行（服务端会如实拒绝，不会自动清理）。
        with self.session() as session:
            other = session.get(ProjectAgent, ("prj_beta", "agent:legacy"))
            if other is not None:
                session.delete(other)
                session.commit()
        response = self.recover(request_key=request_key)
        self.assertIn(response.status_code, (200, 201), response.text)
        with self.make_client() as client:
            host = client.post(
                "/api/projects/prj_alpha/role-provision-host/enable",
                headers={"X-API-Key": "bobo-key"},
                json={"host_label": HOST_LABEL, "expected_version": 0},
            )
        self.assertEqual(host.status_code, 200, host.text)
        with self.make_client() as client:
            detail = client.get(
                f"/api/projects/prj_alpha/role-requests/{request_key}",
                headers={"X-API-Key": "bobo-key"},
            ).json()
            claimed = client.post(
                f"/api/projects/prj_alpha/role-requests/{request_key}/claim",
                headers={"X-API-Key": "bobo-key"},
                json={"host": HOST_LABEL, "expected_revision": detail["revision"]},
            )
        self.assertEqual(claimed.status_code, 200, claimed.text)
        return request_key, claimed.json()["lease_token"]

    def rotate(self, *, member_id="agent:legacy", body=None):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/prj_alpha/roles/{member_id}/rotate-key",
                headers={"X-API-Key": "bobo-key"},
                json=body,
            )

    def test_legacy_rotate_with_recover_request_returns_new_key_once(self):
        request_key, lease_token = self.claim_recover()
        body = {
            "request_key": request_key,
            "lease_token": lease_token,
            "expected_credential_version": 1,
        }
        first = self.rotate(body=body)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertTrue(first.json()["api_key"])
        self.assertEqual(first.json()["credential_version"], 2)
        # 重放同一意图：只读回放，绝不再返 Key。
        replay = self.rotate(body=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["reused"])
        self.assertNotIn("api_key", replay.json())
        with self.session() as session:
            role = session.get(ProjectRole, ("prj_alpha", "agent:legacy"))
            self.assertEqual(role.credential_version, 2)
            # 轮换不得伪造创建操作，也不得改身份来源。
            self.assertIsNone(session.get(RoleCreationOperation, OP_KEY))
            self.assertEqual(role.origin, "imported")

    def test_legacy_rotate_without_request_key_is_refused(self):
        """补录来源不接受无来源的手工轮换，必须由恢复请求驱动。"""
        self.assertEqual(self.attach().status_code, 201)
        response = self.rotate(body=None)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "provision_lease_required")

    def test_imported_role_without_attach_cannot_rotate(self):
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
        response = self.rotate(
            member_id="agent:second",
            body={"request_key": "op-recover-0301", "lease_token": "synthetic-lease"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "rotate_not_managed_identity")

    # ── 绑定指纹回落（B1-c）：补录来源没有创建操作时用请求快照 ─────────

    def test_expected_binding_fingerprint_falls_back_to_request_snapshot(self):
        request_key, _ = self.claim_recover()
        with self.session() as session:
            row = session.get(RoleProvisionRequestRow, request_key)
            fingerprint = expected_binding_fingerprint(row, session)
            snapshot_fingerprint = row.choice_snapshot["binding_fingerprint"]
        # 必须给出 64 位指纹（否则 preflight 会当作"无法取得预期指纹"失败）。
        self.assertIsInstance(fingerprint, str)
        self.assertEqual(len(fingerprint), 64)
        self.assertEqual(fingerprint, snapshot_fingerprint)
