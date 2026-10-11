"""角色生命周期 R1-2：跨宿主配置作业表 + human-only API。

依据 ``.tmp/project-role-lifecycle-r1-2/PROVISION_CONTRACT.md`` §1/§2 与设计
``docs/spec/ROLE_LIFECYCLE_DESIGN.md`` §7.4–7.6/§7.8。覆盖：

- 作业创建绑定**真实已提交**的创建操作，响应是 §2.4 白名单（无 Key/路径/argv）；
- 三个入口 human-only（agent 403）；
- §2.1 第 1 条前置校验的固定顺序与稳定错误码（imported/归档/禁用/离册/缺成员等）；
- ``resume=false`` 幂等重放；定向续跑只重置失败/待跑步骤，终态续跑 409；
- 三步成功路径与 §1.1 状态聚合（pending/running/partial/failed/succeeded）；
- ACK 的 CAS（revision/attempt）、步骤 pending 要求、error_code 白名单；
- 迟到旧尝试不能覆盖新尝试；并发同 key 双 POST 只产生一行；
- ``init_db()`` 重复调用幂等且不改作业行；作业行/JSON 从不存 Key。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型、不读凭据。
"""

from __future__ import annotations

import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

from sqlalchemy import text
from sqlmodel import select

import server.db as db
from server.models import (
    Member,
    ProjectAgent,
    ProjectRole,
    RoleCreationOperation,
    RoleProvisionJob,
    compute_provision_job_status,
)
from tests.test_project_roles import RoleApiTestCase

JOB_KEYS = {
    "operation_key",
    "project_id",
    "member_id",
    "status",
    "revision",
    "credential_version",
    "role_credential_version",
    "expected_binding_fingerprint",
    "resume_of",
    "steps",
    "created_by",
    "created_at",
    "updated_at",
}
STEP_KEYS = {"state", "attempts", "error_code", "updated_at"}
STEPS = ("profile", "key_file", "preflight")


def encode(member_id: str) -> str:
    return quote(member_id, safe="")


class RoleProvisionJobTests(RoleApiTestCase):
    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.register_project("prj_beta")
        self.choice_id = self.seed_runner_and_choice()

    # ── helpers ──────────────────────────────────────────────────────

    def provision_url(self, project_id: str, member_id: str, suffix: str = "") -> str:
        return f"/api/projects/{project_id}/roles/{encode(member_id)}{suffix}"

    def provision(self, project_id, member_id, body, *, key="bobo-key"):
        with self.make_client() as client:
            return client.post(
                self.provision_url(project_id, member_id, "/provision"),
                headers={"X-API-Key": key},
                json=body,
            )

    def get_provision(self, project_id, member_id, operation_key, *, key="bobo-key"):
        params = None if operation_key is None else {"operation_key": operation_key}
        with self.make_client() as client:
            return client.get(
                self.provision_url(project_id, member_id, "/provision"),
                headers={"X-API-Key": key},
                params=params,
            )

    def ack(self, project_id, member_id, body, *, key="bobo-key"):
        with self.make_client() as client:
            return client.post(
                self.provision_url(project_id, member_id, "/provision/ack"),
                headers={"X-API-Key": key},
                json=body,
            )

    def ack_body(
        self,
        operation_key,
        step,
        *,
        attempt,
        revision,
        state,
        error_code=None,
        credential_version=1,
    ):
        return {
            "operation_key": operation_key,
            "step": step,
            "attempt": attempt,
            "revision": revision,
            "credential_version": credential_version,
            "state": state,
            "error_code": error_code,
        }

    def make_role(self, project_id="prj_alpha", *, operation_key, role_name=None):
        """创建真实角色并返回创建响应体（含一次性 api_key）。"""
        created = self.create_role(
            project_id,
            role_name=role_name or f"role-{operation_key}",
            choice_id=self.choice_id,
            operation_key=operation_key,
        )
        self.assertEqual(created.status_code, 201, created.text)
        return created.json()

    def job_rows(self):
        with self.session() as session:
            return list(session.exec(select(RoleProvisionJob)).all())

    def raw_job_steps(self, operation_key: str) -> str:
        with self.session() as session:
            return session.execute(
                text(
                    "SELECT steps FROM role_provision_jobs WHERE operation_key = :key"
                ),
                {"key": operation_key},
            ).scalar()

    def assert_error(self, response, status_code: int, detail: str):
        self.assertEqual(response.status_code, status_code, response.text)
        self.assertEqual(response.json()["detail"], detail)

    def roster_paths(self, project_id, member_id, body, *, key="bobo-key"):
        with self.make_client() as client:
            return client.post(
                self.provision_url(project_id, member_id, "/provision/roster-paths"),
                headers={"X-API-Key": key},
                json=body,
            )

    def paths_body(self, operation_key, member_id=None, directory=None, **overrides):
        """单角色路径登记体；F8 之后 ``<role_dir>`` 必须等于目标角色自己的目录名。"""
        if directory is None:
            directory = member_id.replace(":", "_") if member_id else "role-a"
        body = {
            "operation_key": operation_key,
            "identity_path": f".talk/agents/{directory}/IDENTITY.md",
            "soul_path": f".talk/agents/{directory}/SOUL.md",
            "user_path": f".talk/agents/{directory}/USER.md",
        }
        body.update(overrides)
        return body

    def roster_snapshot(self, project_id, member_id) -> dict:
        with self.session() as session:
            row = session.get(ProjectAgent, (project_id, member_id))
            return {
                column.name: getattr(row, column.name)
                for column in ProjectAgent.__table__.columns
            }

    # ── 创建：白名单与真实锚点 ───────────────────────────────────────

    def test_create_job_whitelist_and_creation_operation_anchor(self):
        role = self.make_role(operation_key="op-key-prov-0001")
        member_id = role["member_id"]

        response = self.provision(
            "prj_alpha", member_id, {"operation_key": "op-key-prov-0001"}
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(set(body), JOB_KEYS)
        self.assertEqual(body["operation_key"], "op-key-prov-0001")
        self.assertEqual(body["project_id"], "prj_alpha")
        self.assertEqual(body["member_id"], member_id)
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["revision"], 1)
        self.assertIsNone(body["resume_of"])
        self.assertEqual(body["created_by"], "human:bobo")
        # G1/G3：读取时角色当前凭据版本 + 创建操作所选 choice 的预期绑定指纹，都在白名单里。
        self.assertEqual(body["role_credential_version"], 1)
        self.assertIsInstance(body["expected_binding_fingerprint"], str)
        self.assertEqual(len(body["expected_binding_fingerprint"]), 64)
        self.assertEqual(
            body["expected_binding_fingerprint"],
            body["expected_binding_fingerprint"].lower(),
        )
        self.assertEqual(set(body["steps"]), set(STEPS))
        for step in STEPS:
            self.assertEqual(set(body["steps"][step]), STEP_KEYS)
            self.assertEqual(body["steps"][step]["state"], "pending")
            self.assertEqual(body["steps"][step]["attempts"], 1)
            self.assertIsNone(body["steps"][step]["error_code"])
            self.assertIsNone(body["steps"][step]["updated_at"])

        # 公开响应不含任何凭据/路径/argv。
        raw = response.text
        self.assertNotIn("api_key", raw)
        self.assertNotIn(role["api_key"], raw)
        self.assertNotIn("argv", raw)
        self.assertNotIn(":\\", raw)
        self.assertNotIn("/home/", raw)

        # 作业锚点就是真实已提交的创建操作行。
        with self.session() as session:
            operation = session.get(RoleCreationOperation, "op-key-prov-0001")
            self.assertIsNotNone(operation)
            self.assertEqual(operation.member_id, member_id)
            job = session.get(RoleProvisionJob, "op-key-prov-0001")
            self.assertIsNotNone(job)
            self.assertEqual(job.operation_key, operation.operation_key)
            self.assertEqual(job.project_id, "prj_alpha")
            # 作业只写本表：创建后的事实未被重建/重发。
            self.assertIsNotNone(session.get(Member, member_id))
            role_row = session.get(ProjectRole, ("prj_alpha", member_id))
            self.assertEqual(role_row.credential_version, 1)
            self.assertIsNotNone(
                session.get(ProjectAgent, ("prj_alpha", member_id))
            )
        self.assertEqual(len(self.job_rows()), 1)

    def test_agent_forbidden_on_all_three_endpoints(self):
        role = self.make_role(operation_key="op-key-prov-0002")
        member_id = role["member_id"]
        body = {"operation_key": "op-key-prov-0002"}
        responses = (
            self.provision("prj_alpha", member_id, body, key="worker-key"),
            self.get_provision(
                "prj_alpha", member_id, "op-key-prov-0002", key="worker-key"
            ),
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0002",
                    "profile",
                    attempt=1,
                    revision=1,
                    state="succeeded",
                ),
                key="worker-key",
            ),
        )
        for response in responses:
            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                response.json()["detail"], "only human members can manage projects"
            )
        self.assertEqual(self.job_rows(), [])
        # human 正常可用。
        self.assertEqual(self.provision("prj_alpha", member_id, body).status_code, 201)
        self.assertEqual(
            self.get_provision("prj_alpha", member_id, "op-key-prov-0002").status_code,
            200,
        )

    # ── 前置校验：固定顺序与稳定错误码 ───────────────────────────────

    def test_unknown_project_is_404(self):
        response = self.provision(
            "prj_ghost", "agent:x", {"operation_key": "op-key-prov-0003"}
        )
        self.assert_error(response, 404, "project_not_found")

    def test_imported_legacy_identity_is_refused(self):
        synced = self.sync_roster(
            "prj_alpha",
            [
                {
                    "member_id": "agent:worker",
                    "identity_path": ".talk/agents/agent_worker/IDENTITY.md",
                }
            ],
        )
        self.assertEqual(synced.status_code, 200, synced.text)
        responses = (
            self.provision(
                "prj_alpha", "agent:worker", {"operation_key": "op-key-prov-0004"}
            ),
            self.get_provision("prj_alpha", "agent:worker", "op-key-prov-0004"),
            self.ack(
                "prj_alpha",
                "agent:worker",
                self.ack_body(
                    "op-key-prov-0004",
                    "profile",
                    attempt=1,
                    revision=1,
                    state="succeeded",
                ),
            ),
        )
        for response in responses:
            self.assert_error(
                response, 409, "provision_imported_identity_unsupported"
            )
        self.assertEqual(self.job_rows(), [])

    def test_missing_operation_without_identity_is_404(self):
        response = self.provision(
            "prj_alpha", "agent:ghost", {"operation_key": "op-key-prov-0005"}
        )
        self.assert_error(response, 404, "provision_operation_not_found")

    def test_wrong_and_foreign_operation_key_is_mismatch(self):
        role = self.make_role(operation_key="op-key-prov-0006")
        member_id = role["member_id"]
        # key 完全不存在 → mismatch（不伪造锚点）。
        wrong = self.provision(
            "prj_alpha", member_id, {"operation_key": "op-key-ghost-0006"}
        )
        self.assert_error(wrong, 409, "provision_operation_mismatch")
        self.assertEqual(
            self.get_provision(
                "prj_alpha", member_id, "op-key-ghost-0006"
            ).status_code,
            409,
        )

        # key 属于另一个项目。
        beta = self.make_role("prj_beta", operation_key="op-key-prov-0007")
        cross_project = self.provision(
            "prj_alpha", member_id, {"operation_key": "op-key-prov-0007"}
        )
        self.assert_error(cross_project, 409, "provision_operation_mismatch")

        # key 属于同项目另一个成员。
        other = self.make_role("prj_alpha", operation_key="op-key-prov-0008")
        cross_member = self.provision(
            "prj_alpha", other["member_id"], {"operation_key": "op-key-prov-0006"}
        )
        self.assert_error(cross_member, 409, "provision_operation_mismatch")
        self.assertEqual(beta["member_id"] != member_id, True)
        self.assertEqual(self.job_rows(), [])

    def test_role_and_member_preconditions(self):
        # 归档角色。
        archived = self.make_role(operation_key="op-key-prov-0010")
        self.archive_role("prj_alpha", archived["member_id"])
        self.assert_error(
            self.provision(
                "prj_alpha", archived["member_id"], {"operation_key": "op-key-prov-0010"}
            ),
            409,
            "role_archived",
        )

        # 禁用成员。
        disabled = self.make_role(operation_key="op-key-prov-0011")
        with self.session() as session:
            member = session.get(Member, disabled["member_id"])
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        self.assert_error(
            self.provision(
                "prj_alpha",
                disabled["member_id"],
                {"operation_key": "op-key-prov-0011"},
            ),
            409,
            "provision_member_disabled",
        )

        # 成员行缺失。
        deleted = self.make_role(operation_key="op-key-prov-0012")
        with self.session() as session:
            session.delete(session.get(Member, deleted["member_id"]))
            session.commit()
        self.assert_error(
            self.provision(
                "prj_alpha", deleted["member_id"], {"operation_key": "op-key-prov-0012"}
            ),
            409,
            "provision_member_missing",
        )

        # 非 agent。
        humanized = self.make_role(operation_key="op-key-prov-0013")
        with self.session() as session:
            member = session.get(Member, humanized["member_id"])
            member.kind = "human"
            session.add(member)
            session.commit()
        self.assert_error(
            self.provision(
                "prj_alpha",
                humanized["member_id"],
                {"operation_key": "op-key-prov-0013"},
            ),
            409,
            "provision_member_not_agent",
        )

        # 离册（名册行被 sync 移除）。
        off_roster = self.make_role(operation_key="op-key-prov-0014")
        with self.session() as session:
            session.delete(
                session.get(ProjectAgent, ("prj_alpha", off_roster["member_id"]))
            )
            session.commit()
        self.assert_error(
            self.provision(
                "prj_alpha",
                off_roster["member_id"],
                {"operation_key": "op-key-prov-0014"},
            ),
            409,
            "provision_roster_missing",
        )
        self.assertEqual(self.job_rows(), [])

    def test_request_shape_validation(self):
        role = self.make_role(operation_key="op-key-prov-0020")
        member_id = role["member_id"]
        short_key = self.provision(
            "prj_alpha", member_id, {"operation_key": "short"}
        )
        self.assert_error(short_key, 422, "operation_key_invalid")
        for steps in ([], ["bogus"], ["profile", "profile"], ["profile", "bogus"]):
            with self.subTest(steps=steps):
                invalid = self.provision(
                    "prj_alpha",
                    member_id,
                    {"operation_key": "op-key-prov-0020", "resume": True, "steps": steps},
                )
                self.assert_error(invalid, 422, "provision_step_invalid")
        extra = self.provision(
            "prj_alpha",
            member_id,
            {"operation_key": "op-key-prov-0020", "unexpected": True},
        )
        self.assertEqual(extra.status_code, 422)
        # GET：缺失/非法 key → 422。
        missing = self.get_provision("prj_alpha", member_id, None)
        self.assert_error(missing, 422, "operation_key_invalid")
        self.assert_error(
            self.get_provision("prj_alpha", member_id, "short"),
            422,
            "operation_key_invalid",
        )
        self.assertEqual(self.job_rows(), [])

    # ── 幂等 / 续跑 ─────────────────────────────────────────────────

    def test_repeat_provision_without_resume_is_idempotent(self):
        role = self.make_role(operation_key="op-key-prov-0030")
        member_id = role["member_id"]
        first = self.provision(
            "prj_alpha", member_id, {"operation_key": "op-key-prov-0030"}
        )
        self.assertEqual(first.status_code, 201)
        second = self.provision(
            "prj_alpha",
            member_id,
            {"operation_key": "op-key-prov-0030", "resume": False},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        rows = self.job_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].revision, 1)
        self.assertEqual(rows[0].resume_of, None)

    def test_three_step_success_path(self):
        role = self.make_role(operation_key="op-key-prov-0031")
        member_id = role["member_id"]
        self.provision("prj_alpha", member_id, {"operation_key": "op-key-prov-0031"})

        response = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0031", "profile", attempt=1, revision=1, state="succeeded"
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "running")
        self.assertEqual(response.json()["revision"], 2)
        self.assertIsNotNone(response.json()["steps"]["profile"]["updated_at"])

        response = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0031", "key_file", attempt=1, revision=2, state="succeeded"
            ),
        )
        self.assertEqual(response.json()["status"], "running")
        response = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0031", "preflight", attempt=1, revision=3, state="succeeded"
            ),
        )
        body = response.json()
        self.assertEqual(body["status"], "succeeded")
        self.assertEqual(body["revision"], 4)
        for step in STEPS:
            self.assertEqual(body["steps"][step]["state"], "succeeded")
            self.assertEqual(body["steps"][step]["attempts"], 1)
            self.assertIsNone(body["steps"][step]["error_code"])

    def test_status_aggregation_after_ack(self):
        cases = {
            "op-key-agg-none": ((), "pending"),
            "op-key-agg-one": ((("profile", "succeeded"),), "running"),
            "op-key-agg-skip-pending": ((("profile", "skipped"),), "running"),
            "op-key-agg-fail": ((("profile", "failed"),), "partial"),
            "op-key-agg-all-fail": (
                (
                    ("profile", "failed"),
                    ("key_file", "failed"),
                    ("preflight", "failed"),
                ),
                "failed",
            ),
            "op-key-agg-mixed": (
                (("profile", "succeeded"), ("key_file", "failed")),
                "partial",
            ),
            "op-key-agg-skip": (
                (
                    ("profile", "skipped"),
                    ("key_file", "skipped"),
                    ("preflight", "skipped"),
                ),
                "succeeded",
            ),
        }
        for operation_key, (acks, expected) in cases.items():
            with self.subTest(operation_key=operation_key):
                body = self._drive_job(operation_key, acks)
                self.assertEqual(body["status"], expected)

    def _drive_job(self, operation_key: str, acks) -> dict:
        role = self.make_role(operation_key=operation_key)
        created = self.provision(
            "prj_alpha", role["member_id"], {"operation_key": operation_key}
        )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        revision = 1
        for step, state in acks:
            response = self.ack(
                "prj_alpha",
                role["member_id"],
                self.ack_body(
                    operation_key,
                    step,
                    attempt=body["steps"][step]["attempts"],
                    revision=revision,
                    state=state,
                    error_code="step_probe_failed" if state == "failed" else None,
                ),
            )
            self.assertEqual(response.status_code, 200, response.text)
            revision += 1
            body = response.json()
        return body

    def test_targeted_resume_resets_only_unfinished_steps(self):
        role = self.make_role(operation_key="op-key-prov-0040")
        member_id = role["member_id"]
        self.provision("prj_alpha", member_id, {"operation_key": "op-key-prov-0040"})
        self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0040", "profile", attempt=1, revision=1, state="succeeded"
            ),
        )
        self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0040",
                "key_file",
                attempt=1,
                revision=2,
                state="failed",
                error_code="key_write_failed",
            ),
        )
        done = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0040", "preflight", attempt=1, revision=3, state="succeeded"
            ),
        )
        self.assertEqual(done.json()["status"], "partial")
        profile_before = done.json()["steps"]["profile"]
        preflight_before = done.json()["steps"]["preflight"]

        resumed = self.provision(
            "prj_alpha",
            member_id,
            {
                "operation_key": "op-key-prov-0040",
                "resume": True,
                "steps": ["profile", "key_file"],
            },
        )
        self.assertEqual(resumed.status_code, 200)
        body = resumed.json()
        self.assertEqual(body["revision"], 5)
        self.assertEqual(body["resume_of"], "op-key-prov-0040")
        self.assertEqual(body["status"], "running")
        # 已完成步骤不被重置。
        self.assertEqual(body["steps"]["profile"], profile_before)
        self.assertEqual(body["steps"]["preflight"], preflight_before)
        self.assertEqual(body["steps"]["key_file"]["state"], "pending")
        self.assertEqual(body["steps"]["key_file"]["attempts"], 2)
        self.assertIsNone(body["steps"]["key_file"]["error_code"])
        self.assertIsNone(body["steps"]["key_file"]["updated_at"])

        # 补跑成功后即为终态；终态续跑 409。
        self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0040", "key_file", attempt=2, revision=5, state="succeeded"
            ),
        )
        terminal = self.provision(
            "prj_alpha",
            member_id,
            {"operation_key": "op-key-prov-0040", "resume": True},
        )
        self.assert_error(terminal, 409, "provision_job_terminal")

    def test_default_resume_resets_failed_and_pending_only(self):
        role = self.make_role(operation_key="op-key-prov-0041")
        member_id = role["member_id"]
        self.provision("prj_alpha", member_id, {"operation_key": "op-key-prov-0041"})
        self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0041", "profile", attempt=1, revision=1, state="succeeded"
            ),
        )
        self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0041",
                "key_file",
                attempt=1,
                revision=2,
                state="failed",
                error_code="key_write_failed",
            ),
        )
        body = self.provision(
            "prj_alpha",
            member_id,
            {"operation_key": "op-key-prov-0041", "resume": True},
        ).json()
        self.assertEqual(body["revision"], 4)
        self.assertEqual(body["resume_of"], "op-key-prov-0041")
        self.assertEqual(body["steps"]["profile"]["state"], "succeeded")
        self.assertEqual(body["steps"]["profile"]["attempts"], 1)
        self.assertEqual(body["steps"]["key_file"]["state"], "pending")
        self.assertEqual(body["steps"]["key_file"]["attempts"], 2)
        self.assertEqual(body["steps"]["preflight"]["state"], "pending")
        self.assertEqual(body["steps"]["preflight"]["attempts"], 2)
        self.assertEqual(body["status"], "running")

    # ── ACK：CAS、步骤状态与 error_code 白名单 ──────────────────────

    def test_ack_job_not_found(self):
        role = self.make_role(operation_key="op-key-prov-0050")
        member_id = role["member_id"]
        self.assert_error(
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0050",
                    "profile",
                    attempt=1,
                    revision=1,
                    state="succeeded",
                ),
            ),
            404,
            "provision_job_not_found",
        )
        self.assert_error(
            self.get_provision("prj_alpha", member_id, "op-key-prov-0050"),
            404,
            "provision_job_not_found",
        )

    def test_ack_validation_codes_and_cas(self):
        role = self.make_role(operation_key="op-key-prov-0051")
        member_id = role["member_id"]
        self.provision("prj_alpha", member_id, {"operation_key": "op-key-prov-0051"})

        self.assert_error(
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0051", "bogus", attempt=1, revision=1, state="succeeded"
                ),
            ),
            422,
            "provision_step_invalid",
        )
        self.assert_error(
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0051", "profile", attempt=1, revision=1, state="done"
                ),
            ),
            422,
            "provision_ack_state_invalid",
        )
        self.assert_error(
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0051",
                    "profile",
                    attempt=1,
                    revision=9,
                    state="succeeded",
                ),
            ),
            409,
            "provision_revision_conflict",
        )
        self.assert_error(
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0051",
                    "profile",
                    attempt=1,
                    revision=1,
                    state="succeeded",
                    error_code="not_allowed",
                ),
            ),
            422,
            "provision_error_code_invalid",
        )
        for bad_code in ("sk-abcdefgh", "x" * 65, "has space", ""):
            with self.subTest(error_code=bad_code):
                self.assert_error(
                    self.ack(
                        "prj_alpha",
                        member_id,
                        self.ack_body(
                            "op-key-prov-0051",
                            "profile",
                            attempt=1,
                            revision=1,
                            state="failed",
                            error_code=bad_code,
                        ),
                    ),
                    422,
                    "provision_error_code_invalid",
                )
        # 以上全部被拒：作业事实零变化。
        row = self.job_rows()[0]
        self.assertEqual(row.revision, 1)
        self.assertEqual(row.status, "pending")

        # 合法终态。
        self.assertEqual(
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0051",
                    "profile",
                    attempt=1,
                    revision=1,
                    state="succeeded",
                ),
            ).status_code,
            200,
        )
        # 已完成的步骤不可再回报。
        self.assert_error(
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0051",
                    "profile",
                    attempt=1,
                    revision=2,
                    state="failed",
                    error_code="retry_failed",
                ),
            ),
            409,
            "provision_step_not_pending",
        )
        # 旧 attempt 不得冒充当前尝试。
        self.assert_error(
            self.ack(
                "prj_alpha",
                member_id,
                self.ack_body(
                    "op-key-prov-0051", "key_file", attempt=0, revision=2, state="succeeded"
                ),
            ),
            409,
            "provision_stale_attempt",
        )

    def test_late_old_attempt_cannot_flip_newer_attempt(self):
        role = self.make_role(operation_key="op-key-prov-0052")
        member_id = role["member_id"]
        self.provision("prj_alpha", member_id, {"operation_key": "op-key-prov-0052"})
        self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0052",
                "profile",
                attempt=1,
                revision=1,
                state="failed",
                error_code="step_probe_failed",
            ),
        )
        resumed = self.provision(
            "prj_alpha",
            member_id,
            {"operation_key": "op-key-prov-0052", "resume": True, "steps": ["profile"]},
        )
        self.assertEqual(resumed.json()["steps"]["profile"]["attempts"], 2)

        # 新尝试仍是 pending 时，旧 attempt 的迟到回报被 stale_attempt 挡住。
        late = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0052",
                "profile",
                attempt=1,
                revision=3,
                state="succeeded",
            ),
        )
        self.assert_error(late, 409, "provision_stale_attempt")
        row = self.job_rows()[0]
        self.assertEqual(row.steps["profile"]["state"], "pending")
        self.assertEqual(row.steps["profile"]["attempts"], 2)
        self.assertEqual(row.revision, 3)

        # 新尝试完成后，旧尝试（含旧 revision）一律不得翻盘。
        completed = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0052", "profile", attempt=2, revision=3, state="succeeded"
            ),
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        late_after_completion = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0052",
                "profile",
                attempt=1,
                revision=4,
                state="failed",
                error_code="late_old_attempt",
            ),
        )
        self.assert_error(late_after_completion, 409, "provision_step_not_pending")
        stale_revision = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0052",
                "profile",
                attempt=2,
                revision=1,
                state="failed",
                error_code="late_revision",
            ),
        )
        self.assert_error(stale_revision, 409, "provision_revision_conflict")

        row = self.job_rows()[0]
        self.assertEqual(row.steps["profile"]["state"], "succeeded")
        self.assertEqual(row.steps["profile"]["attempts"], 2)
        self.assertIsNone(row.steps["profile"]["error_code"])

    # ── 并发 ────────────────────────────────────────────────────────

    def test_concurrent_same_key_double_post_creates_one_job(self):
        role = self.make_role(operation_key="op-key-prov-0060")
        member_id = role["member_id"]
        barrier = threading.Barrier(2)

        def call(_index):
            with self.make_client() as client:
                barrier.wait(timeout=15)
                return client.post(
                    self.provision_url("prj_alpha", member_id, "/provision"),
                    headers={"X-API-Key": "bobo-key"},
                    json={"operation_key": "op-key-prov-0060"},
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(call, range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 201])
        bodies = [r.json() for r in responses]
        self.assertEqual({b["operation_key"] for b in bodies}, {"op-key-prov-0060"})
        self.assertEqual({b["revision"] for b in bodies}, {1})
        self.assertEqual({b["status"] for b in bodies}, {"pending"})
        self.assertEqual(len(self.job_rows()), 1)

    # ── 迁移幂等 / 凭据不外泄 ────────────────────────────────────────

    def test_init_db_twice_is_idempotent_for_job_rows(self):
        role = self.make_role(operation_key="op-key-prov-0070")
        member_id = role["member_id"]
        self.provision("prj_alpha", member_id, {"operation_key": "op-key-prov-0070"})
        self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0070", "profile", attempt=1, revision=1, state="succeeded"
            ),
        )
        with self.session() as session:
            before = session.exec(select(RoleProvisionJob)).one()
            snapshot = (
                before.revision,
                before.status,
                json.dumps(before.steps, sort_keys=True),
                before.resume_of,
                before.updated_at,
            )
        db.init_db()
        db.init_db()
        with self.session() as session:
            after = session.exec(select(RoleProvisionJob)).one()
            self.assertEqual(
                (
                    after.revision,
                    after.status,
                    json.dumps(after.steps, sort_keys=True),
                    after.resume_of,
                    after.updated_at,
                ),
                snapshot,
            )
        with self.engine.connect() as conn:
            indexes = {
                row[0]
                for row in conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
        self.assertIn("ix_role_provision_jobs_project", indexes)
        self.assertIn("ix_role_provision_jobs_status", indexes)

    def test_job_never_stores_key_credentials_or_paths(self):
        role = self.make_role(operation_key="op-key-prov-0080")
        member_id = role["member_id"]
        api_key = role["api_key"]
        provisioned = self.provision(
            "prj_alpha", member_id, {"operation_key": "op-key-prov-0080"}
        )
        self.assertEqual(provisioned.status_code, 201)
        self.assertNotIn(api_key, provisioned.text)
        failed = self.ack(
            "prj_alpha",
            member_id,
            self.ack_body(
                "op-key-prov-0080",
                "profile",
                attempt=1,
                revision=1,
                state="failed",
                error_code="profile_write_failed",
            ),
        )
        self.assertEqual(failed.status_code, 200)
        self.assertNotIn(api_key, failed.text)

        raw_steps = self.raw_job_steps("op-key-prov-0080")
        self.assertIsInstance(raw_steps, str)
        self.assertNotIn(api_key, raw_steps)
        self.assertNotIn("api_key", raw_steps)
        self.assertNotIn("key_file_path", raw_steps)
        self.assertNotIn("argv", raw_steps)
        self.assertNotIn(":\\", raw_steps)
        self.assertNotIn("/home/", raw_steps)

        with self.session() as session:
            row = session.get(RoleProvisionJob, "op-key-prov-0080")
            dumped = json.dumps(
                {
                    "steps": row.steps,
                    "resume_of": row.resume_of,
                    "created_by": row.created_by,
                    "project_id": row.project_id,
                    "member_id": row.member_id,
                }
            )
        self.assertNotIn(api_key, dumped)
        self.assertNotIn("api_key", dumped)
        self.assertNotIn("argv", dumped)
        self.assertNotIn(":\\", dumped)
        self.assertNotIn("/home/", dumped)
        # 失败步骤只记录脚本层稳定错误码。
        self.assertEqual(
            row.steps["profile"]["error_code"], "profile_write_failed"
        )

    # ── 单角色路径登记：/provision/roster-paths ──────────────────────

    def test_roster_paths_agent_forbidden_and_human_ok(self):
        role = self.make_role(operation_key="op-key-rp-0001")
        body = self.paths_body("op-key-rp-0001", role["member_id"])
        denied = self.roster_paths(
            "prj_alpha", role["member_id"], body, key="worker-key"
        )
        self.assert_error(denied, 403, "only human members can manage projects")
        # 拒绝时不得写任何路径。
        snapshot = self.roster_snapshot("prj_alpha", role["member_id"])
        self.assertIsNone(snapshot["identity_path"])
        self.assertIsNone(snapshot["soul_path"])
        self.assertIsNone(snapshot["user_path"])
        allowed = self.roster_paths("prj_alpha", role["member_id"], body)
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_roster_paths_anchor_and_identity_rejections(self):
        role = self.make_role(operation_key="op-key-rp-0010")
        member_id = role["member_id"]
        # key 不存在 → mismatch。
        self.assert_error(
            self.roster_paths(
                "prj_alpha", member_id, self.paths_body("op-key-ghost-0010")
            ),
            409,
            "provision_operation_mismatch",
        )
        # key 属于另一个项目。
        self.make_role("prj_beta", operation_key="op-key-rp-0011")
        self.assert_error(
            self.roster_paths(
                "prj_alpha", member_id, self.paths_body("op-key-rp-0011")
            ),
            409,
            "provision_operation_mismatch",
        )

        # 归档角色。
        archived = self.make_role(operation_key="op-key-rp-0012")
        self.archive_role("prj_alpha", archived["member_id"])
        self.assert_error(
            self.roster_paths(
                "prj_alpha",
                archived["member_id"],
                self.paths_body("op-key-rp-0012"),
            ),
            409,
            "role_archived",
        )

        # 禁用成员。
        disabled = self.make_role(operation_key="op-key-rp-0013")
        with self.session() as session:
            member = session.get(Member, disabled["member_id"])
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        self.assert_error(
            self.roster_paths(
                "prj_alpha",
                disabled["member_id"],
                self.paths_body("op-key-rp-0013"),
            ),
            409,
            "provision_member_disabled",
        )

        # 成员行缺失（offline）。
        gone = self.make_role(operation_key="op-key-rp-0014")
        with self.session() as session:
            session.delete(session.get(Member, gone["member_id"]))
            session.commit()
        self.assert_error(
            self.roster_paths(
                "prj_alpha", gone["member_id"], self.paths_body("op-key-rp-0014")
            ),
            409,
            "provision_member_missing",
        )

        # 离册（名册行被移除）。
        off_roster = self.make_role(operation_key="op-key-rp-0015")
        with self.session() as session:
            session.delete(
                session.get(ProjectAgent, ("prj_alpha", off_roster["member_id"]))
            )
            session.commit()
        self.assert_error(
            self.roster_paths(
                "prj_alpha",
                off_roster["member_id"],
                self.paths_body("op-key-rp-0015"),
            ),
            409,
            "provision_roster_missing",
        )

    def test_roster_paths_imported_identity_refused(self):
        synced = self.sync_roster(
            "prj_alpha",
            [
                {
                    "member_id": "agent:worker",
                    "identity_path": ".talk/agents/agent_worker/IDENTITY.md",
                }
            ],
        )
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assert_error(
            self.roster_paths(
                "prj_alpha", "agent:worker", self.paths_body("op-key-rp-0020")
            ),
            409,
            "provision_imported_identity_unsupported",
        )

    def test_roster_paths_reject_invalid_paths(self):
        role = self.make_role(operation_key="op-key-rp-0030")
        member_id = role["member_id"]
        operation_key = "op-key-rp-0030"
        bad_cases = {
            "absolute_windows_backslash": {
                "identity_path": "C:\\talk\\agents\\role-a\\IDENTITY.md"
            },
            "absolute_windows_slash": {
                "identity_path": "C:/talk/agents/role-a/IDENTITY.md"
            },
            "leading_slash": {"identity_path": "/talk/agents/role-a/IDENTITY.md"},
            "unc_backslash": {
                "identity_path": "\\\\server\\share\\IDENTITY.md"
            },
            "dotdot_segment": {
                "identity_path": ".talk/agents/role-a/../role-b/IDENTITY.md"
            },
            "mixed_role_dirs": {"soul_path": ".talk/agents/role-b/SOUL.md"},
            "bad_basename": {"user_path": ".talk/agents/role-a/PROFILE.md"},
            "swapped_basename": {
                "identity_path": ".talk/agents/role-a/SOUL.md"
            },
            "extra_nesting": {
                "identity_path": ".talk/agents/role-a/sub/IDENTITY.md"
            },
            "wrong_root": {"identity_path": ".talk/roles/role-a/IDENTITY.md"},
            "empty_path": {"soul_path": ""},
            "control_char": {"user_path": ".talk/agents/role-a/USE\x00R.md"},
        }
        for name, overrides in bad_cases.items():
            with self.subTest(case=name):
                self.assert_error(
                    self.roster_paths(
                        "prj_alpha",
                        member_id,
                        self.paths_body(operation_key, member_id, **overrides),
                    ),
                    422,
                    "provision_roster_path_invalid",
                )
        # 全部被拒后名册行保持未登记。
        snapshot = self.roster_snapshot("prj_alpha", member_id)
        self.assertIsNone(snapshot["identity_path"])
        self.assertIsNone(snapshot["soul_path"])
        self.assertIsNone(snapshot["user_path"])

    def test_roster_paths_success_updates_only_that_row(self):
        role_a = self.make_role(operation_key="op-key-rp-0040")
        role_b = self.make_role(operation_key="op-key-rp-0041")
        before_a = self.roster_snapshot("prj_alpha", role_a["member_id"])
        before_b = self.roster_snapshot("prj_alpha", role_b["member_id"])
        directory = role_a["member_id"].replace(":", "_")

        response = self.roster_paths(
            "prj_alpha",
            role_a["member_id"],
            {
                "operation_key": "op-key-rp-0040",
                # 反斜杠必须被归一为 `/`。
                "identity_path": f".talk\\agents\\{directory}\\IDENTITY.md",
                "soul_path": f".talk/agents/{directory}/SOUL.md",
                "user_path": f".talk/agents/{directory}/USER.md",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            set(body),
            {"member_id", "identity_path", "soul_path", "user_path"},
        )
        self.assertEqual(body["member_id"], role_a["member_id"])
        self.assertEqual(
            body["identity_path"], f".talk/agents/{directory}/IDENTITY.md"
        )
        self.assertEqual(body["soul_path"], f".talk/agents/{directory}/SOUL.md")
        self.assertEqual(body["user_path"], f".talk/agents/{directory}/USER.md")
        self.assertNotIn(role_a["api_key"], response.text)
        self.assertNotIn(":\\", response.text)

        after_a = self.roster_snapshot("prj_alpha", role_a["member_id"])
        self.assertEqual(
            after_a["identity_path"], f".talk/agents/{directory}/IDENTITY.md"
        )
        self.assertEqual(after_a["soul_path"], f".talk/agents/{directory}/SOUL.md")
        self.assertEqual(after_a["user_path"], f".talk/agents/{directory}/USER.md")
        # 该行其它列原样保留。
        for field in (
            "project_id",
            "member_id",
            "memory_pointer",
            "business_role",
            "decision_tier",
            "capability_summary",
        ):
            self.assertEqual(after_a[field], before_a[field])
        # 第二条名册行 byte-identical（含 updated_at）。
        self.assertEqual(
            self.roster_snapshot("prj_alpha", role_b["member_id"]), before_b
        )

    def test_provision_create_does_not_fill_roster_paths(self):
        role = self.make_role(operation_key="op-key-rp-0050")
        self.assertEqual(
            self.provision(
                "prj_alpha", role["member_id"], {"operation_key": "op-key-rp-0050"}
            ).status_code,
            201,
        )
        snapshot = self.roster_snapshot("prj_alpha", role["member_id"])
        self.assertIsNone(snapshot["identity_path"])
        self.assertIsNone(snapshot["soul_path"])
        self.assertIsNone(snapshot["user_path"])


class RoleProvisionStatusHelperTests(unittest.TestCase):
    """§1.1 状态聚合的边角组合（纯函数，含 failed+skipped / skipped+pending）。"""

    def _steps(self, *states):
        return {
            step: {
                "state": state,
                "attempts": 1,
                "error_code": None,
                "updated_at": None,
            }
            for step, state in zip(STEPS, states)
        }

    def test_hardcoded_combinations(self):
        cases = (
            (("pending", "pending", "pending"), "pending"),
            (("succeeded", "pending", "pending"), "running"),
            (("skipped", "pending", "pending"), "running"),
            (("failed", "pending", "pending"), "partial"),
            (("failed", "failed", "pending"), "partial"),
            (("failed", "failed", "failed"), "failed"),
            (("failed", "succeeded", "succeeded"), "partial"),
            (("failed", "skipped", "skipped"), "partial"),
            (("succeeded", "succeeded", "pending"), "running"),
            (("succeeded", "skipped", "succeeded"), "succeeded"),
        )
        for states, expected in cases:
            with self.subTest(states=states):
                self.assertEqual(
                    compute_provision_job_status(self._steps(*states)), expected
                )


if __name__ == "__main__":
    unittest.main()
