"""存量角色保留身份补录（产品片A）合同测试。

覆盖 ``docs/spec/ROLE_LEGACY_ATTACH_DESIGN.md`` 的全部不变量：

- ``POST /api/projects/{project_id}/roles/legacy-attach`` 仅 human、严格四字段请求体；
- 只接受当前名册内、未禁用的 ``agent``，且本项目没有其 ``ProjectRole`` 行；已有
  managed / imported / 归档角色与同名活跃角色一律拒绝，不借补录恢复/改名/重写；
- 同一 ``BEGIN IMMEDIATE`` 事务内原子新增 ``imported`` / ``identity_exclusive=0`` /
  ``credential_version=1`` 角色行 + **缺失时**的精确绑定 + 独立补录审计行；
- 不生成/返回/轮换 Key，不改 Member/名册/既有绑定/说明/策略/其它项目/历史/任务；
- 首次 201、精确重放 200/``reused``、异载荷/跨项目/跨成员/与创建操作同 key 409；
- 投影按独立映射与当前绑定六维精确相等给 ``legacy_attach``，失配/双映射冲突如实失配；
- 每个写入点及提交前故障注入证明整体回滚；并发同 key / 异 key 的稳定收敛。

全部用例使用真实 router + 进程内隔离临时 SQLite 与假 Key；不调用生产 API、不写生产库、
不读真实凭据、不启动真实服务或模型。
"""

from __future__ import annotations

import json
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, select

from server.models import (
    AgentTask,
    Member,
    Message,
    ProjectAgent,
    ProjectRole,
    ProjectRoleBinding,
    ProjectRoleDescription,
    ProjectRolePolicy,
    RoleCreationOperation,
    RoleLegacyAttachOperation,
    RoleProvisionJob,
    RoleServiceLaunch,
    RoleServiceState,
    RunnerModelChoice,
    build_role_legacy_attach_fingerprint,
)
from tests.test_project_roles import RUNNER_ID, RoleApiTestCase
from tests.test_support import RouteTestCase

ATTACH_PATH = "/api/projects/{project_id}/roles/legacy-attach"
OP_KEY = "attach-op-key-0001"
REPO_ROOT = Path(__file__).resolve().parent.parent


class LegacyAttachIsolationTests(RouteTestCase):
    """先断言 engine/storage 隔离，再建 TestClient（合同 §验证与交付）。

    本类刻意不继承补录夹具：断言必须在**任何 TestClient 出现之前**完成，并且只使用
    隔离临时 SQLite 与假 Key；不调用生产 API、不运行生产 ``init_db``、不读真实凭据。
    """

    def test_isolation_facts_hold_before_the_first_client(self):
        import server.db as db
        import server.main as main
        import server.routes.files as files_route

        # 1) 进程内 engine 已整体替换为临时库，请求不可能落到生产 SQLite。
        self.assertIs(db.engine, self.engine)
        self.assertIs(main.engine, self.engine)
        self.assertIn(".tmp-tests", str(self.engine.url))
        production_db = Path(db.DB_PATH)
        if not production_db.is_absolute():
            production_db = REPO_ROOT / production_db
        self.assertNotEqual(production_db.resolve(), Path(self.db_path).resolve())
        # 2) 存储目录同样是隔离的临时目录（不写生产上传目录）。
        self.assertEqual(db.STORAGE_DIR, self.storage_dir)
        self.assertEqual(files_route.STORAGE_DIR, self.storage_dir)
        self.assertNotEqual(Path(db.STORAGE_DIR).resolve(), (REPO_ROOT / "storage").resolve())
        # 3) 假 Key：临时库里只有本测试写入的成员。
        self.add_member("human:iso", api_key="iso-fake-key", display_name="Iso")
        with self.session() as session:
            self.assertEqual(
                [row.id for row in session.exec(select(Member)).all()], ["human:iso"]
            )

        # 4) 隔离断言完成后才创建第一个 TestClient；请求读到的正是临时库里的假 Key。
        with self.make_client() as client:
            self.assertEqual(client.get("/healthz").status_code, 200)
            projects = client.get(
                "/api/projects", headers={"X-API-Key": "iso-fake-key"}
            )
        self.assertEqual(projects.status_code, 200)
        self.assertEqual(projects.json(), [])


class LegacyAttachTestCase(RoleApiTestCase):
    """补录接口公共夹具：两个项目、一个已登记 runner + choice、两名存量 agent。"""

    def setUp(self):
        super().setUp()
        self.choice_id = self.seed_runner_and_choice()
        self.register_project("prj_alpha")
        self.register_project("prj_beta")
        self.add_member("agent:legacy", api_key="legacy-key", display_name="Legacy One")
        self.add_member("agent:second", api_key="second-key", display_name="Second One")
        self.sync_roster(
            "prj_alpha",
            [
                {
                    "member_id": "agent:legacy",
                    "identity_path": ".talk/agents/legacy/IDENTITY.md",
                    "business_role": "dev",
                    "capability_summary": ["backend"],
                },
                {"member_id": "agent:second"},
                {"member_id": "human:ann"},
            ],
        )
        self.sync_roster("prj_beta", [{"member_id": "agent:legacy"}])

    # ── helpers ──────────────────────────────────────────────────────

    def attach(
        self,
        *,
        project_id: str = "prj_alpha",
        member_id: str = "agent:legacy",
        runner_id: str = RUNNER_ID,
        choice_id: str | None = None,
        operation_key: str = OP_KEY,
        key: str = "bobo-key",
        extra: dict | None = None,
        body: dict | None = None,
    ):
        payload = body if body is not None else {
            "member_id": member_id,
            "runner_id": runner_id,
            "choice_id": choice_id or self.choice_id,
            "operation_key": operation_key,
        }
        if extra:
            payload = dict(payload)
            payload.update(extra)
        with self.make_client() as client:
            return client.post(
                ATTACH_PATH.format(project_id=project_id),
                headers={"X-API-Key": key},
                json=payload,
            )

    def roles(self, project_id: str = "prj_alpha", *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/roles", headers={"X-API-Key": key}
            )

    def role_row(self, project_id: str = "prj_alpha", member_id: str = "agent:legacy"):
        for row in self.roles(project_id).json():
            if row["member_id"] == member_id:
                return row
        raise AssertionError(f"role row missing for {member_id}")

    def seed_binding(
        self,
        *,
        project_id: str = "prj_alpha",
        member_id: str = "agent:legacy",
        **overrides,
    ):
        fields = {
            "runner_id": RUNNER_ID,
            "model_source": "builtin",
            "provider_id": "managed:deepseek",
            "connection_ref": "native-deepseek-managed-login",
            "model_id": "deepseek-flash",
            "model_alias": "deepseek-flash",
            "model_display_name": "DeepSeek Flash",
            "updated_by": "human:bobo",
        }
        fields.update(overrides)
        with self.session() as session:
            session.add(
                ProjectRoleBinding(
                    project_id=project_id,
                    member_id=member_id,
                    **fields,
                )
            )
            session.commit()

    def set_member_disabled(self, member_id: str = "agent:legacy") -> None:
        with self.session() as session:
            member = session.get(Member, member_id)
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()

    def archive_role(
        self, *, project_id: str = "prj_alpha", member_id: str = "agent:legacy"
    ) -> None:
        with self.session() as session:
            role = session.get(ProjectRole, (project_id, member_id))
            role.archived_at = datetime.now(timezone.utc)
            session.add(role)
            session.commit()

    def counts(self) -> dict:
        with self.session() as session:
            return {
                "roles": len(session.exec(select(ProjectRole)).all()),
                "bindings": len(session.exec(select(ProjectRoleBinding)).all()),
                "attach_ops": len(session.exec(select(RoleLegacyAttachOperation)).all()),
                "creation_ops": len(session.exec(select(RoleCreationOperation)).all()),
                "service_states": len(session.exec(select(RoleServiceState)).all()),
                "service_launches": len(session.exec(select(RoleServiceLaunch)).all()),
                "provision_jobs": len(session.exec(select(RoleProvisionJob)).all()),
            }

    def snapshot(self) -> dict:
        """全表逐字段快照：证明补录没有改写任何保留事实（不是只比较长度/数量）。"""
        with self.session() as session:

            def rows(model, key):
                return {
                    key(row): row.model_dump()
                    for row in session.exec(select(model)).all()
                }

            return {
                "members": rows(Member, lambda r: r.id),
                "project_agents": rows(ProjectAgent, lambda r: (r.project_id, r.member_id)),
                "roles": rows(ProjectRole, lambda r: (r.project_id, r.member_id)),
                "bindings": rows(ProjectRoleBinding, lambda r: (r.project_id, r.member_id)),
                "descriptions": rows(
                    ProjectRoleDescription, lambda r: (r.project_id, r.member_id)
                ),
                "policies": rows(ProjectRolePolicy, lambda r: (r.project_id, r.member_id)),
                "creation_ops": rows(RoleCreationOperation, lambda r: r.operation_key),
                "attach_ops": rows(RoleLegacyAttachOperation, lambda r: r.operation_key),
                "provision_jobs": rows(RoleProvisionJob, lambda r: r.operation_key),
                "service_states": rows(RoleServiceState, lambda r: (r.project_id, r.member_id)),
                "service_launches": rows(RoleServiceLaunch, lambda r: r.launch_id),
                "messages": rows(Message, lambda r: r.id),
                "tasks": rows(AgentTask, lambda r: r.id),
            }


class LegacyAttachAtomicityTests(LegacyAttachTestCase):
    """首次补录的原子事实、保留事实与响应面。"""

    def test_first_attach_creates_imported_role_binding_and_audit(self):
        response = self.attach()
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["member_id"], "agent:legacy")
        self.assertFalse(payload["reused"])
        self.assertNotIn("api_key", json.dumps(payload))
        self.assertEqual(payload["role"]["origin"], "imported")
        self.assertEqual(payload["role"]["identity"], "imported")
        self.assertFalse(payload["role"]["identity_exclusive"])
        self.assertFalse(payload["role"]["archived"])
        self.assertEqual(payload["role"]["role_name"], "Legacy One")
        self.assertEqual(payload["role"]["model"]["choice_source"], "legacy_attach")
        self.assertEqual(payload["role"]["model"]["choice_id"], self.choice_id)
        self.assertFalse(payload["role"]["model"]["choice_binding_mismatch"])
        self.assertEqual(payload["role"]["runner"]["runner_id"], RUNNER_ID)
        self.assertEqual(payload["role"]["binding_state"], "bound")

        with self.session() as session:
            role = session.get(ProjectRole, ("prj_alpha", "agent:legacy"))
            self.assertEqual(role.origin, "imported")
            self.assertEqual(role.identity_exclusive, 0)
            self.assertEqual(role.credential_version, 1)
            self.assertIsNone(role.key_issued_at)
            self.assertIsNone(role.key_rotated_at)
            self.assertIsNone(role.archived_at)
            self.assertEqual(role.created_by, "human:bobo")
            self.assertEqual(role.role_name, "Legacy One")

            binding = session.get(ProjectRoleBinding, ("prj_alpha", "agent:legacy"))
            self.assertEqual(binding.runner_id, RUNNER_ID)
            self.assertEqual(binding.model_id, "deepseek-flash")
            self.assertEqual(binding.model_alias, "deepseek-flash")
            self.assertEqual(binding.updated_by, "human:bobo")

            audit = session.get(RoleLegacyAttachOperation, OP_KEY)
            self.assertEqual(audit.project_id, "prj_alpha")
            self.assertEqual(audit.member_id, "agent:legacy")
            self.assertEqual(audit.runner_id, RUNNER_ID)
            self.assertEqual(audit.choice_id, self.choice_id)
            self.assertEqual(audit.derived_role_name, "Legacy One")
            self.assertEqual(audit.created_by, "human:bobo")
            self.assertIsNotNone(audit.committed_at)
            self.assertEqual(len(audit.request_fingerprint), 64)
            # 补录不得伪造“创建了新身份”的事实。
            self.assertIsNone(session.get(RoleCreationOperation, OP_KEY))

    def test_attach_preserves_existing_binding_fields_verbatim(self):
        self.seed_binding(
            model_display_name="自定义展示名", updated_by="human:ann"
        )
        with self.session() as session:
            before = session.get(
                ProjectRoleBinding, ("prj_alpha", "agent:legacy")
            ).model_dump()
        self.assertEqual(self.attach().status_code, 201)
        with self.session() as session:
            after = session.get(
                ProjectRoleBinding, ("prj_alpha", "agent:legacy")
            ).model_dump()
        # 既有绑定存在时逐字段保留（含 updated_at / updated_by），不替换、不“顺手修正”。
        self.assertEqual(before, after)

    def test_attach_preserves_member_roster_history_and_other_projects(self):
        self.add_message(
            from_id="agent:legacy", to_ids=None, message_type="text", content="历史消息"
        )
        before = self.snapshot()
        member_api_key_before = before["members"]["agent:legacy"]["api_key"]

        self.assertEqual(self.attach().status_code, 201)

        after = self.snapshot()
        # 成员身份与凭据逐字段不变（假 Key 也不被读取/轮换/返回）。
        self.assertEqual(before["members"], after["members"])
        self.assertEqual(member_api_key_before, "legacy-key")
        self.assertEqual(after["members"]["agent:legacy"]["api_key"], "legacy-key")
        self.assertEqual(after["members"]["agent:legacy"]["display_name"], "Legacy One")
        # 名册、说明、策略、其它项目、历史任务/消息/成果全部保持。
        self.assertEqual(before["project_agents"], after["project_agents"])
        self.assertEqual(before["descriptions"], after["descriptions"])
        self.assertEqual(before["policies"], after["policies"])
        self.assertEqual(before["messages"], after["messages"])
        self.assertEqual(before["tasks"], after["tasks"])
        self.assertEqual(before["creation_ops"], after["creation_ops"])
        # 不创建 provision 作业、不写任何 service 状态/launch。
        self.assertEqual(after["provision_jobs"], {})
        self.assertEqual(after["service_states"], {})
        self.assertEqual(after["service_launches"], {})
        # 本片唯一新增的三个事实：本项目角色行、缺失时的绑定、独立补录审计。
        self.assertEqual(before["roles"], {})
        self.assertEqual(before["bindings"], {})
        self.assertEqual(before["attach_ops"], {})
        self.assertEqual(sorted(after["roles"]), [("prj_alpha", "agent:legacy")])
        self.assertEqual(sorted(after["bindings"]), [("prj_alpha", "agent:legacy")])
        self.assertEqual(sorted(after["attach_ops"]), [OP_KEY])

    def test_attaching_second_member_adds_only_its_own_rows(self):
        self.assertEqual(self.attach().status_code, 201)
        second = self.attach(
            member_id="agent:second", operation_key="attach-op-key-0002"
        )
        self.assertEqual(second.status_code, 201)
        with self.session() as session:
            roles = {row.member_id: row for row in session.exec(select(ProjectRole)).all()}
            attach_ops = {
                row.member_id: row
                for row in session.exec(select(RoleLegacyAttachOperation)).all()
            }
        self.assertEqual(sorted(roles), ["agent:legacy", "agent:second"])
        self.assertEqual(roles["agent:second"].role_name, "Second One")
        self.assertEqual(roles["agent:legacy"].role_name, "Legacy One")
        self.assertEqual(sorted(attach_ops), ["agent:legacy", "agent:second"])

    def test_response_body_never_exposes_key_material(self):
        response = self.attach()
        self.assertEqual(response.status_code, 201)
        text = response.text
        self.assertNotIn("legacy-key", text)
        self.assertNotIn("api_key", text)
        self.assertNotIn("key_issued_at", text)
        self.assertNotIn("provision", text)


class LegacyAttachIdempotencyTests(LegacyAttachTestCase):
    """幂等、冲突与重放不恢复后续事实。"""

    def test_exact_replay_returns_200_reused_without_any_write(self):
        self.assertEqual(self.attach().status_code, 201)
        counts_after_first = self.counts()
        with self.session() as session:
            role_before = session.get(ProjectRole, ("prj_alpha", "agent:legacy")).model_dump()
            audit_before = session.get(RoleLegacyAttachOperation, OP_KEY).model_dump()

        response = self.attach()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["reused"])
        self.assertEqual(response.json()["member_id"], "agent:legacy")
        self.assertNotIn("api_key", response.text)
        self.assertEqual(self.counts(), counts_after_first)
        with self.session() as session:
            self.assertEqual(
                session.get(ProjectRole, ("prj_alpha", "agent:legacy")).model_dump(),
                role_before,
            )
            self.assertEqual(
                session.get(RoleLegacyAttachOperation, OP_KEY).model_dump(), audit_before
            )

    def test_replay_after_binding_change_does_not_restore_binding(self):
        self.assertEqual(self.attach().status_code, 201)
        # 绑定已存在；下面直接改写它，模拟补录之后发生的合法变更。
        with self.session() as session:
            binding = session.get(ProjectRoleBinding, ("prj_alpha", "agent:legacy"))
            binding.model_alias = "changed-after-attach"
            session.add(binding)
            session.commit()

        response = self.attach()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["reused"])
        # 重放如实显示**当前**失配，且不把绑定改回去。
        self.assertEqual(response.json()["role"]["model"]["choice_id"], None)
        self.assertEqual(
            response.json()["role"]["model"]["choice_source"], "legacy_attach_mismatch"
        )
        self.assertTrue(response.json()["role"]["model"]["choice_binding_mismatch"])
        with self.session() as session:
            self.assertEqual(
                session.get(ProjectRoleBinding, ("prj_alpha", "agent:legacy")).model_alias,
                "changed-after-attach",
            )

    def test_replay_after_archive_does_not_unarchive(self):
        self.assertEqual(self.attach().status_code, 201)
        self.archive_role()
        response = self.attach()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["reused"])
        self.assertTrue(response.json()["role"]["archived"])
        with self.session() as session:
            self.assertIsNotNone(
                session.get(ProjectRole, ("prj_alpha", "agent:legacy")).archived_at
            )

    def test_same_key_different_choice_conflicts(self):
        second_choice = self.create_choice(model_alias="other-alias").json()["choice_id"]
        self.assertEqual(self.attach().status_code, 201)
        counts = self.counts()
        response = self.attach(choice_id=second_choice)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "operation_key_conflict")
        self.assertEqual(self.counts(), counts)

    def test_same_key_other_member_conflicts(self):
        self.assertEqual(self.attach().status_code, 201)
        response = self.attach(member_id="agent:second")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "operation_key_conflict")
        with self.session() as session:
            self.assertIsNone(session.get(ProjectRole, ("prj_alpha", "agent:second")))

    def test_same_key_cross_project_conflicts(self):
        self.assertEqual(self.attach().status_code, 201)
        response = self.attach(project_id="prj_beta")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "operation_key_conflict")
        with self.session() as session:
            self.assertIsNone(session.get(ProjectRole, ("prj_beta", "agent:legacy")))
            audit = session.get(RoleLegacyAttachOperation, OP_KEY)
            self.assertEqual(audit.project_id, "prj_alpha")

    def test_same_key_as_creation_operation_conflicts(self):
        created = self.create_role(
            "prj_alpha",
            role_name="Created Role",
            choice_id=self.choice_id,
            operation_key="shared-op-key-0001",
        )
        self.assertEqual(created.status_code, 201)
        counts = self.counts()
        response = self.attach(operation_key="shared-op-key-0001")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "operation_key_conflict")
        self.assertEqual(self.counts(), counts)
        with self.session() as session:
            self.assertIsNone(session.get(RoleLegacyAttachOperation, "shared-op-key-0001"))

    def test_failed_attempt_leaves_no_pending_row_and_retry_succeeds(self):
        self.assertEqual(self.attach(operation_key="short").status_code, 422)
        self.set_member_disabled()
        self.assertEqual(self.attach().status_code, 409)
        with self.session() as session:
            self.assertIsNone(session.get(RoleLegacyAttachOperation, OP_KEY))
        with self.session() as session:
            member = session.get(Member, "agent:legacy")
            member.disabled_at = None
            session.add(member)
            session.commit()
        self.assertEqual(self.attach().status_code, 201)


class LegacyAttachGuardTests(LegacyAttachTestCase):
    """权限、引用、维度与命名守卫的稳定拒绝与零残留。"""

    def test_agent_caller_is_forbidden(self):
        response = self.attach(key="legacy-key")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts()["roles"], 0)

    def test_extra_fields_are_rejected(self):
        for extra in (
            {"api_key": "forged-key"},
            {"auto_start": True},
            {"role_name": "Override"},
            {"role_description": "写给角色"},
            {"identity_exclusive": 1},
            {"key_issued_at": "2026-10-17T00:00:00Z"},
            {"legacy_attach": True},
        ):
            with self.subTest(extra=extra):
                response = self.attach(extra=extra)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.counts()["roles"], 0)

    def test_invalid_tokens_are_422(self):
        valid = {
            "member_id": "agent:legacy",
            "runner_id": RUNNER_ID,
            "choice_id": self.choice_id,
            "operation_key": OP_KEY,
        }
        for field, bad in (
            ("member_id", "bad id"),
            ("runner_id", "BAD RUNNER"),
            ("choice_id", "bad choice"),
            ("operation_key", "short"),
        ):
            with self.subTest(field=field):
                body = dict(valid)
                body[field] = bad
                self.assertEqual(self.attach(body=body).status_code, 422)
        self.assertEqual(self.counts()["roles"], 0)

    def test_project_not_found(self):
        response = self.attach(project_id="prj_ghost")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "project not found")

    def test_member_not_found(self):
        response = self.attach(member_id="agent:ghost")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "member_not_found")

    def test_non_agent_member_rejected(self):
        response = self.attach(member_id="human:ann")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "member_not_agent")

    def test_disabled_member_rejected(self):
        self.set_member_disabled()
        response = self.attach()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "member_disabled")
        self.assertEqual(self.counts()["roles"], 0)

    def test_member_not_in_roster_rejected(self):
        response = self.attach(member_id="agent:other")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "member_not_in_roster")
        self.assertEqual(self.counts()["roles"], 0)

    def test_exclusive_identity_from_creation_is_refused(self):
        # 直接构造“该身份在另一项目已独占登记”的既有事实（名册不允许这样同步）。
        with self.session() as session:
            session.add(
                ProjectRole(
                    project_id="prj_beta",
                    member_id="agent:legacy",
                    role_name="Beta Role",
                    origin="managed",
                    identity_exclusive=1,
                    credential_version=1,
                    created_by="human:bobo",
                )
            )
            session.commit()
        response = self.attach()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "identity_exclusive_reference_refused"
        )
        with self.session() as session:
            self.assertIsNone(session.get(ProjectRole, ("prj_alpha", "agent:legacy")))
            self.assertIsNone(session.get(RoleLegacyAttachOperation, OP_KEY))

    def test_existing_creation_mapping_for_same_identity_is_refused(self):
        with self.session() as session:
            session.add(
                RoleCreationOperation(
                    operation_key="prior-creation-op-0001",
                    request_fingerprint="f" * 64,
                    project_id="prj_beta",
                    requested_role_name="Beta Role",
                    runner_id=RUNNER_ID,
                    choice_id=self.choice_id,
                    member_id="agent:legacy",
                    committed_at=datetime.now(timezone.utc),
                    created_by="human:bobo",
                )
            )
            session.commit()
        response = self.attach()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "identity_exclusive_reference_refused"
        )
        with self.session() as session:
            self.assertIsNone(session.get(ProjectRole, ("prj_alpha", "agent:legacy")))

    def test_existing_imported_role_is_refused_not_replayed(self):
        self.assertEqual(self.attach().status_code, 201)
        response = self.attach(operation_key="attach-op-key-0009")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "role_already_exists")
        with self.session() as session:
            self.assertIsNone(session.get(RoleLegacyAttachOperation, "attach-op-key-0009"))
            self.assertEqual(len(session.exec(select(ProjectRole)).all()), 1)

    def test_existing_managed_role_is_refused(self):
        created = self.create_role(
            "prj_alpha",
            role_name="Managed Role",
            choice_id=self.choice_id,
            operation_key="managed-op-key-0001",
        )
        self.assertEqual(created.status_code, 201)
        managed_member_id = created.json()["member_id"]
        self.sync_roster(
            "prj_alpha",
            [{"member_id": "agent:legacy"}, {"member_id": managed_member_id}],
        )
        response = self.attach(member_id=managed_member_id, operation_key="attach-op-key-0011")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "role_already_exists")

    def test_archived_role_is_refused(self):
        self.assertEqual(self.attach().status_code, 201)
        self.archive_role()
        response = self.attach(operation_key="attach-op-key-0012")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "role_already_exists")

    def test_role_name_conflict_is_refused_without_random_suffix(self):
        self.assertEqual(self.attach().status_code, 201)
        self.add_member("agent:clash", api_key="clash-key", display_name="Legacy One")
        self.sync_roster(
            "prj_alpha",
            [{"member_id": "agent:legacy"}, {"member_id": "agent:clash"}],
        )
        response = self.attach(member_id="agent:clash", operation_key="attach-op-key-0013")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "role_name_conflict")
        with self.session() as session:
            self.assertIsNone(session.get(ProjectRole, ("prj_alpha", "agent:clash")))

    def test_blank_display_name_falls_back_to_member_id(self):
        self.add_member("agent:blank", api_key="blank-key", display_name="   ")
        self.sync_roster("prj_alpha", [{"member_id": "agent:blank"}])
        response = self.attach(member_id="agent:blank", operation_key="attach-op-key-0014")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"]["role_name"], "agent:blank")

    def test_runner_and_choice_guards(self):
        unknown_runner = self.attach(runner_id="runner:ghost")
        self.assertEqual(unknown_runner.status_code, 404)
        self.assertEqual(unknown_runner.json()["detail"], "runner_not_found")

        unknown_choice = self.attach(choice_id="rmc_deadbeef0000")
        self.assertEqual(unknown_choice.status_code, 404)
        self.assertEqual(unknown_choice.json()["detail"], "choice_not_found")

        self.register_runner("runner:other", runtime="codex")
        other_choice = self.create_choice("runner:other").json()["choice_id"]
        cross_runner = self.attach(choice_id=other_choice)
        self.assertEqual(cross_runner.status_code, 404)
        self.assertEqual(cross_runner.json()["detail"], "choice_not_found")

        self.register_runner("runner:retired", adapter_status="adapted")
        retired_choice = self.create_choice("runner:retired").json()["choice_id"]
        with self.make_client() as client:
            patched = client.patch(
                "/api/runners/runner:retired",
                headers={"X-API-Key": "bobo-key"},
                json={"adapter_status": "retired"},
            )
        self.assertEqual(patched.status_code, 200)
        retired_runner = self.attach(runner_id="runner:retired", choice_id=retired_choice)
        self.assertEqual(retired_runner.status_code, 409)
        self.assertEqual(retired_runner.json()["detail"], "runner_retired")

        retired = self.create_choice(model_alias="retired-alias").json()["choice_id"]
        with self.session() as session:
            choice = session.get(RunnerModelChoice, retired)
            choice.retired_at = datetime.now(timezone.utc)
            session.add(choice)
            session.commit()
        retired_choice_response = self.attach(choice_id=retired)
        self.assertEqual(retired_choice_response.status_code, 409)
        self.assertEqual(retired_choice_response.json()["detail"], "choice_retired")
        self.assertEqual(self.counts()["roles"], 0)

    def test_binding_six_dimension_mismatch_is_refused_and_preserved(self):
        self.seed_binding(connection_ref="another-connection")
        with self.session() as session:
            before = session.get(ProjectRoleBinding, ("prj_alpha", "agent:legacy")).model_dump()
        response = self.attach()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "binding_choice_mismatch")
        with self.session() as session:
            self.assertIsNone(session.get(ProjectRole, ("prj_alpha", "agent:legacy")))
            self.assertIsNone(session.get(RoleLegacyAttachOperation, OP_KEY))
            self.assertEqual(
                session.get(ProjectRoleBinding, ("prj_alpha", "agent:legacy")).model_dump(),
                before,
            )

    def test_same_model_id_different_dimension_is_not_guessed(self):
        # 同 model_id、不同 alias/connection：不得按 model_id 反查“猜”成同一选择。
        self.seed_binding(model_alias="", connection_ref="native-other-login")
        response = self.attach()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "binding_choice_mismatch")


class LegacyAttachRollbackTests(LegacyAttachTestCase):
    """每个写入点与提交前的故障注入：同一事务整体回滚、零残留。"""

    @staticmethod
    def _failing_add(fail_at: int):
        state = {"calls": 0}

        def patched(session, row):
            state["calls"] += 1
            if state["calls"] == fail_at:
                raise RuntimeError("injected write failure")
            session.add(row)

        return patched

    def test_each_write_point_failure_rolls_back_everything(self):
        for fail_at in (1, 2, 3):
            with self.subTest(fail_at=fail_at):
                counts = self.counts()
                with patch(
                    "server.routes.projects._tx_add_role_fact",
                    side_effect=self._failing_add(fail_at),
                ):
                    response = self.attach()
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.json()["detail"], "legacy_attach_failed")
                self.assertEqual(self.counts(), counts)
                with self.session() as session:
                    self.assertIsNone(session.get(ProjectRole, ("prj_alpha", "agent:legacy")))
                    self.assertIsNone(
                        session.get(ProjectRoleBinding, ("prj_alpha", "agent:legacy"))
                    )
                    self.assertIsNone(session.get(RoleLegacyAttachOperation, OP_KEY))

    def test_commit_failure_rolls_back_everything(self):
        counts = self.counts()
        member_before = self.snapshot()["members"]
        real_commit = Session.commit

        def boom(self):  # noqa: ANN001 - 注入真实提交失败
            raise RuntimeError("injected commit failure")

        with patch.object(Session, "commit", boom):
            response = self.attach()
        self.assertIs(Session.commit, real_commit)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.snapshot()["members"], member_before)
        with self.session() as session:
            self.assertIsNone(session.get(ProjectRole, ("prj_alpha", "agent:legacy")))
            self.assertIsNone(session.get(RoleLegacyAttachOperation, OP_KEY))

    def test_retry_after_injected_failure_succeeds_with_same_key(self):
        with patch(
            "server.routes.projects._tx_add_role_fact",
            side_effect=self._failing_add(2),
        ):
            self.assertEqual(self.attach().status_code, 500)
        self.assertEqual(self.attach().status_code, 201)
        self.assertEqual(self.counts()["attach_ops"], 1)


class LegacyAttachConcurrencyTests(LegacyAttachTestCase):
    """并发同 key / 异 key 的稳定收敛（真实 SQLite 事务 + 线程）。"""

    def _run_parallel(self, payloads: list[dict]) -> list:
        results: list = [None] * len(payloads)
        barrier = threading.Barrier(len(payloads))

        def worker(index: int, payload: dict) -> None:
            barrier.wait()
            with self.make_client() as client:
                results[index] = client.post(
                    ATTACH_PATH.format(project_id="prj_alpha"),
                    headers={"X-API-Key": "bobo-key"},
                    json=payload,
                )

        threads = [
            threading.Thread(target=worker, args=(index, payload))
            for index, payload in enumerate(payloads)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        return results

    def _payload(self, *, member_id: str = "agent:legacy", operation_key: str = OP_KEY):
        return {
            "member_id": member_id,
            "runner_id": RUNNER_ID,
            "choice_id": self.choice_id,
            "operation_key": operation_key,
        }

    def test_concurrent_same_key_produces_single_commit(self):
        results = self._run_parallel([self._payload(), self._payload()])
        codes = sorted(response.status_code for response in results)
        self.assertEqual(codes, [200, 201])
        self.assertEqual(self.counts()["roles"], 1)
        self.assertEqual(self.counts()["attach_ops"], 1)
        replayed = [r for r in results if r.status_code == 200][0]
        self.assertTrue(replayed.json()["reused"])

    def test_concurrent_different_keys_produce_one_winner(self):
        results = self._run_parallel(
            [
                self._payload(operation_key="attach-op-key-1001"),
                self._payload(operation_key="attach-op-key-1002"),
            ]
        )
        codes = sorted(response.status_code for response in results)
        self.assertEqual(codes, [201, 409])
        loser = [r for r in results if r.status_code == 409][0]
        self.assertEqual(loser.json()["detail"], "role_already_exists")
        self.assertEqual(self.counts()["roles"], 1)
        self.assertEqual(self.counts()["attach_ops"], 1)

    def test_concurrent_different_members_keep_independent_rows(self):
        results = self._run_parallel(
            [
                self._payload(member_id="agent:legacy", operation_key="attach-op-key-2001"),
                self._payload(member_id="agent:second", operation_key="attach-op-key-2002"),
            ]
        )
        self.assertEqual(sorted(r.status_code for r in results), [201, 201])
        self.assertEqual(self.counts()["roles"], 2)
        self.assertEqual(self.counts()["attach_ops"], 2)


class LegacyAttachProjectionTests(LegacyAttachTestCase):
    """投影来源口径：legacy_attach / mismatch / 双映射冲突 / 原有来源不回归。"""

    def test_projection_uses_legacy_attach_after_attach(self):
        self.assertEqual(self.attach().status_code, 201)
        row = self.role_row()
        self.assertEqual(row["model"]["choice_source"], "legacy_attach")
        self.assertEqual(row["model"]["choice_id"], self.choice_id)
        self.assertEqual(row["model"]["choice_binding_mismatch"], False)

    def test_projection_reports_mismatch_when_choice_row_disappears(self):
        self.assertEqual(self.attach().status_code, 201)
        with self.session() as session:
            choice = session.get(RunnerModelChoice, self.choice_id)
            session.delete(choice)
            session.commit()
        row = self.role_row()
        self.assertIsNone(row["model"]["choice_id"])
        self.assertEqual(row["model"]["choice_source"], "legacy_attach_mismatch")
        self.assertTrue(row["model"]["choice_binding_mismatch"])

    def test_projection_dual_mapping_conflict_is_not_resolved_by_picking_one(self):
        self.assertEqual(self.attach().status_code, 201)
        with self.session() as session:
            session.add(
                RoleCreationOperation(
                    operation_key="dual-mapping-op-0001",
                    request_fingerprint="d" * 64,
                    project_id="prj_alpha",
                    requested_role_name="Legacy One",
                    runner_id=RUNNER_ID,
                    choice_id=self.choice_id,
                    member_id="agent:legacy",
                    committed_at=datetime.now(timezone.utc),
                    created_by="human:bobo",
                )
            )
            session.commit()
        row = self.role_row()
        self.assertIsNone(row["model"]["choice_id"])
        self.assertEqual(row["model"]["choice_source"], "legacy_attach_mismatch")
        self.assertTrue(row["model"]["choice_binding_mismatch"])

    def test_projection_legacy_manual_and_creation_sources_unchanged(self):
        # 未补录的存量名册成员：仍是 legacy_manual / 无 choice。
        rows = {row["member_id"]: row for row in self.roles().json()}
        self.assertEqual(rows["agent:legacy"]["model"]["choice_source"], "legacy_manual")
        self.assertIsNone(rows["agent:legacy"]["model"]["choice_id"])
        self.assertEqual(rows["agent:legacy"]["identity"], "legacy")

        # 创建路径不受本片影响。
        created = self.create_role(
            "prj_alpha",
            role_name="Created Role",
            choice_id=self.choice_id,
            operation_key="creation-regression-0001",
        )
        self.assertEqual(created.status_code, 201)
        created_id = created.json()["member_id"]
        row = self.role_row(member_id=created_id)
        self.assertEqual(row["model"]["choice_source"], "creation_operation")
        self.assertEqual(row["model"]["choice_id"], self.choice_id)
        self.assertEqual(row["identity"], "managed")

    def test_projection_keeps_archived_and_unmatched_registration_visible(self):
        self.assertEqual(self.attach().status_code, 201)
        self.archive_role()
        row = self.role_row()
        self.assertTrue(row["archived"])
        self.assertEqual(row["origin"], "imported")
        self.assertEqual(row["model"]["choice_source"], "legacy_attach")
        self.assertEqual(row["model"]["choice_id"], self.choice_id)

    def test_roster_sync_does_not_remove_attached_role(self):
        self.assertEqual(self.attach().status_code, 201)
        self.sync_roster("prj_alpha", [{"member_id": "agent:legacy"}])
        row = self.role_row()
        self.assertEqual(row["role_name"], "Legacy One")
        self.assertEqual(row["model"]["choice_source"], "legacy_attach")


class LegacyAttachAuditTests(LegacyAttachTestCase):
    """审计行只存公开元数据，且不向创建审计表写入。"""

    def test_audit_row_excludes_secret_and_payload_fields(self):
        self.assertEqual(self.attach().status_code, 201)
        with self.session() as session:
            audit = session.get(RoleLegacyAttachOperation, OP_KEY)
            columns = set(audit.model_dump().keys())
        self.assertEqual(
            columns,
            {
                "operation_key",
                "request_fingerprint",
                "project_id",
                "member_id",
                "runner_id",
                "choice_id",
                "derived_role_name",
                "committed_at",
                "created_by",
                "created_at",
                "updated_at",
            },
        )

    def test_fingerprint_covers_project_member_runner_choice(self):
        base = build_role_legacy_attach_fingerprint(
            project_id="prj_alpha",
            member_id="agent:legacy",
            runner_id=RUNNER_ID,
            choice_id=self.choice_id,
        )
        variants = [
            build_role_legacy_attach_fingerprint(
                project_id="prj_beta",
                member_id="agent:legacy",
                runner_id=RUNNER_ID,
                choice_id=self.choice_id,
            ),
            build_role_legacy_attach_fingerprint(
                project_id="prj_alpha",
                member_id="agent:second",
                runner_id=RUNNER_ID,
                choice_id=self.choice_id,
            ),
            build_role_legacy_attach_fingerprint(
                project_id="prj_alpha",
                member_id="agent:legacy",
                runner_id="runner:other",
                choice_id=self.choice_id,
            ),
            build_role_legacy_attach_fingerprint(
                project_id="prj_alpha",
                member_id="agent:legacy",
                runner_id=RUNNER_ID,
                choice_id="rmc_000000000001",
            ),
        ]
        self.assertEqual(len(base), 64)
        for variant in variants:
            self.assertNotEqual(base, variant)

    def test_attach_never_touches_creation_audit_table(self):
        self.assertEqual(self.attach().status_code, 201)
        with self.session() as session:
            self.assertEqual(session.exec(select(RoleCreationOperation)).all(), [])


class LegacyAttachReviewRegressionTests(LegacyAttachTestCase):
    """Codex独立复核新增：双向操作键隔离、跨入口并发与原角色名保留。"""

    def make_client(self):
        import server.db as db
        import server.main as main
        import server.routes.files as files_route

        self.assertIs(db.engine, self.engine)
        self.assertIs(main.engine, self.engine)
        self.assertEqual(db.STORAGE_DIR, self.storage_dir)
        self.assertEqual(files_route.STORAGE_DIR, self.storage_dir)
        self.assertNotEqual(Path(self.db_path).resolve(), (REPO_ROOT / "talk.db").resolve())
        return super().make_client()

    def test_create_cannot_reuse_an_attach_key(self):
        self.assertEqual(self.attach().status_code, 201)
        before = self.snapshot()
        response = self.create_role(
            "prj_alpha", role_name="Must Not Create", choice_id=self.choice_id,
            operation_key=OP_KEY,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "operation_key_conflict")
        self.assertNotIn("api_key", response.json())
        self.assertEqual(self.snapshot(), before)

    def test_create_in_other_project_cannot_reuse_an_attach_key(self):
        self.assertEqual(self.attach().status_code, 201)
        before = self.snapshot()
        response = self.create_role(
            "prj_beta", role_name="Must Not Create", choice_id=self.choice_id,
            operation_key=OP_KEY,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "operation_key_conflict")
        self.assertEqual(self.snapshot(), before)

    def _check_cross_endpoint_race(self, *, attach_wins):
        import server.routes.projects as routes

        first_writing = threading.Event()
        second_entered = threading.Event()
        first_session = []
        results = {}
        errors = []
        original_add = routes._tx_add_role_fact
        original_begin = routes.begin_immediate_write
        winner_model = RoleLegacyAttachOperation if attach_wins else RoleCreationOperation

        def hold_before_commit(session, row):
            if isinstance(row, winner_model) and not first_writing.is_set():
                first_session.append(session)
                first_writing.set()
                if not second_entered.wait(10):
                    raise AssertionError("other endpoint did not enter write transaction")
            original_add(session, row)

        def observe_begin(session):
            if first_writing.is_set() and session is not first_session[0]:
                second_entered.set()
            return original_begin(session)

        # 两个客户端先完成临时库lifespan，再在真实SQLite写锁上交错两个HTTP入口。
        with self.make_client() as attach_client, self.make_client() as create_client:
            def request(kind):
                try:
                    if kind == "attach":
                        results[kind] = attach_client.post(
                            ATTACH_PATH.format(project_id="prj_alpha"),
                            headers={"X-API-Key": "bobo-key"},
                            json={"member_id": "agent:legacy", "runner_id": RUNNER_ID,
                                  "choice_id": self.choice_id, "operation_key": OP_KEY},
                        )
                    else:
                        results[kind] = create_client.post(
                            "/api/projects/prj_alpha/roles",
                            headers={"X-API-Key": "bobo-key"},
                            json={"role_name": "New Identity", "runner_id": RUNNER_ID,
                                  "choice_id": self.choice_id, "operation_key": OP_KEY},
                        )
                except Exception as exc:
                    errors.append(type(exc).__name__)

            winner = "attach" if attach_wins else "create"
            loser = "create" if attach_wins else "attach"
            first = threading.Thread(target=request, args=(winner,))
            second = threading.Thread(target=request, args=(loser,))
            with patch.object(routes, "_tx_add_role_fact", hold_before_commit), patch.object(
                routes, "begin_immediate_write", observe_begin
            ):
                first.start()
                self.assertTrue(first_writing.wait(10))
                second.start()
                first.join(20)
                second.join(20)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results[winner].status_code, 201)
            self.assertEqual(results[loser].status_code, 409)
            self.assertEqual(results[loser].json()["detail"], "operation_key_conflict")
        counts = self.counts()
        self.assertEqual(counts["attach_ops"] + counts["creation_ops"], 1)
        self.assertEqual(counts["roles"], 1)
        with self.session() as session:
            self.assertEqual(session.get(Member, "agent:legacy").api_key, "legacy-key")

    def test_attach_winning_cross_endpoint_race_blocks_create(self):
        self._check_cross_endpoint_race(attach_wins=True)

    def test_create_winning_cross_endpoint_race_blocks_attach(self):
        self._check_cross_endpoint_race(attach_wins=False)

    def test_nonempty_overlong_display_name_is_not_silently_replaced(self):
        with self.session() as session:
            member = session.get(Member, "agent:legacy")
            member.display_name = "旧角色" * 22
            session.add(member)
            session.commit()
        before = self.snapshot()
        response = self.attach()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "role_name_invalid")
        self.assertEqual(self.snapshot(), before)

    def test_nonempty_history_description_policy_and_artifact_are_preserved(self):
        from server.models import File

        self.seed_binding(model_display_name="原展示名", updated_by="human:ann")
        with self.session() as session:
            session.add(ProjectRoleDescription(
                project_id="prj_alpha", member_id="agent:legacy",
                description="原角色说明", updated_by="human:ann",
            ))
            policy = session.get(ProjectRolePolicy, ("prj_alpha", "agent:legacy"))
            if policy is None:
                policy = ProjectRolePolicy(project_id="prj_alpha", member_id="agent:legacy")
            policy.review_exempt = 1
            policy.source = "human_grant"
            policy.granted_by = "human:ann"
            session.add(policy)
            session.commit()
        task = self.create_task("prj_alpha", "agent:legacy")
        self.assertEqual(task.status_code, 201)
        self.add_message(from_id="agent:legacy", to_ids=None, message_type="text", content="既有结果")
        self.add_file(file_id="legacy-proof", uploader_id="agent:legacy",
                      filename="result.txt", content="既有成果".encode("utf-8"))
        disk = self.storage_dir / "files/legacy-proof"
        before = self.snapshot()
        with self.session() as session:
            file_before = session.get(File, "legacy-proof").model_dump()
        disk_before = disk.read_bytes()
        for field in ("tasks", "messages", "descriptions", "policies", "bindings"):
            self.assertTrue(before[field], f"{field} must be nonempty")
        self.assertEqual(self.attach().status_code, 201)
        after = self.snapshot()
        for field in ("members", "project_agents", "tasks", "messages", "descriptions", "policies", "bindings"):
            self.assertEqual(after[field], before[field], field)
        with self.session() as session:
            self.assertEqual(session.get(File, "legacy-proof").model_dump(), file_before)
        self.assertEqual(disk.read_bytes(), disk_before)

    def test_64_character_display_name_is_preserved(self):
        with self.session() as session:
            member = session.get(Member, "agent:legacy")
            member.display_name = "名" * 64
            session.add(member)
            session.commit()
        response = self.attach()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"]["role_name"], "名" * 64)


if __name__ == "__main__":  # pragma: no cover - 便于单独运行本模块
    unittest.main()
