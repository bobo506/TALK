"""角色生命周期 R1-1：`rotate-key` 独占引用证明与新独占身份引用守卫（合同 §7.5）。

覆盖实施计划 §3.2/§3.6 的 R3 验收项：

- 独占 managed 身份轮换成功：旧 Key 立即 401、新 Key 可用、`credential_version` 递增；
- 资格与引用证明的稳定拒绝码：``rotate_not_managed_identity`` /
  ``rotate_member_not_agent`` / ``rotate_member_disabled`` /
  ``rotate_shared_identity_refused`` / ``rotate_legacy_roster_reference_refused`` /
  ``rotate_identity_off_roster`` / ``rotate_group_reference_refused`` /
  ``rotate_identity_in_use``（含 target 与 created_by 两条任务路径、未来服务表分支）；
- 新独占身份引用守卫：名册 sync、绑定/说明写入、任务创建、群创建/成员新增一律
  ``409 identity_exclusive_reference_refused``；历史无角色成员完全保留旧行为；
- **真实两连接并发**：轮换与跨项目引用新增由写锁 + 守卫收敛。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest import mock

from sqlalchemy import text
from sqlmodel import select

from server.models import (
    AgentInstance,
    Group,
    GroupMember,
    Member,
    ProjectAgent,
    ProjectRole,
    ProjectRoleBinding,
    ProjectRoleDescription,
)
from tests.test_project_roles import CHOICE_DEFAULTS, RUNNER_ID, RoleApiTestCase, encode


class RoleRotationTests(RoleApiTestCase):
    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.register_project("prj_beta")
        self.choice_id = self.seed_runner_and_choice()
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-rotate-1",
        )
        assert created.status_code == 201, created.text
        self.role = created.json()
        self.member_id = self.role["member_id"]
        self.api_key = self.role["api_key"]

    # ── helpers ──────────────────────────────────────────────────────

    def add_role_row(self, project_id: str) -> None:
        with self.session() as session:
            session.add(
                ProjectRole(
                    project_id=project_id,
                    member_id=self.member_id,
                    role_name="dev",
                    origin="managed",
                    identity_exclusive=1,
                    credential_version=1,
                    created_by="human:bobo",
                )
            )
            session.commit()

    def add_roster_row(self, project_id: str) -> None:
        with self.session() as session:
            session.add(
                ProjectAgent(project_id=project_id, member_id=self.member_id)
            )
            session.commit()

    def remove_own_roster_row(self) -> None:
        with self.session() as session:
            row = session.get(ProjectAgent, ("prj_alpha", self.member_id))
            session.delete(row)
            session.commit()

    def add_global_group_with_member(self) -> str:
        group_id = "group:global"
        with self.session() as session:
            session.add(
                Group(
                    id=group_id,
                    name="Global",
                    type="free",
                    project_id=None,
                    created_by="human:bobo",
                )
            )
            session.add(GroupMember(group_id=group_id, member_id=self.member_id))
            session.commit()
        return group_id

    def add_instance(self, status: str = "idle") -> None:
        with self.make_client() as client:
            response = client.put(
                "/api/instances/role-instance-1",
                headers={"X-API-Key": self.api_key},
                json={"runtime": "dsh", "status": status, "project_id": "prj_alpha"},
            )
        assert response.status_code == 200, response.text

    # ── 成功路径 ────────────────────────────────────────────────────

    def test_exclusive_managed_identity_rotates_and_invalidates_old_key(self):
        rotated = self.rotate_key("prj_alpha", self.member_id)
        self.assertEqual(rotated.status_code, 200)
        payload = rotated.json()
        self.assertEqual(
            set(payload), {"member_id", "api_key", "credential_version"}
        )
        self.assertEqual(payload["member_id"], self.member_id)
        self.assertEqual(payload["credential_version"], 2)
        self.assertNotEqual(payload["api_key"], self.api_key)
        with self.make_client() as client:
            self.assertEqual(
                client.get(
                    "/api/members/me", headers={"X-API-Key": self.api_key}
                ).status_code,
                401,
            )
            self.assertEqual(
                client.get(
                    "/api/members/me", headers={"X-API-Key": payload["api_key"]}
                ).status_code,
                200,
            )
        with self.session() as session:
            role = session.get(ProjectRole, ("prj_alpha", self.member_id))
            self.assertEqual(role.credential_version, 2)
            self.assertIsNotNone(role.key_rotated_at)
            self.assertIsNotNone(role.key_issued_at)

    def test_human_only_and_unknown_role(self):
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id, key="worker-key").status_code,
            403,
        )
        self.assertEqual(
            self.rotate_key("prj_alpha", "agent:ghost").json()["detail"],
            "role_not_found",
        )
        self.assertEqual(self.rotate_key("prj_ghost", self.member_id).status_code, 404)

    def test_archived_role_cannot_rotate(self):
        self.archive_role("prj_alpha", self.member_id)
        response = self.rotate_key("prj_alpha", self.member_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "role_archived")

    def test_imported_identity_is_refused(self):
        with self.session() as session:
            role = session.get(ProjectRole, ("prj_alpha", self.member_id))
            role.origin = "imported"
            session.add(role)
            session.commit()
        response = self.rotate_key("prj_alpha", self.member_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "rotate_not_managed_identity")

    def test_non_agent_and_disabled_member_are_refused(self):
        with self.session() as session:
            member = session.get(Member, self.member_id)
            member.kind = "human"
            session.add(member)
            session.commit()
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_member_not_agent",
        )
        with self.session() as session:
            member = session.get(Member, self.member_id)
            member.kind = "agent"
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_member_disabled",
        )

    def test_non_exclusive_marker_is_refused(self):
        with self.session() as session:
            role = session.get(ProjectRole, ("prj_alpha", self.member_id))
            role.identity_exclusive = 0
            session.add(role)
            session.commit()
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_shared_identity_refused",
        )

    # ── 引用证明的稳定拒绝码 ─────────────────────────────────────────

    def test_other_project_role_reference_is_refused(self):
        self.add_role_row("prj_beta")
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_shared_identity_refused",
        )

    def test_legacy_roster_reference_is_refused(self):
        self.add_roster_row("prj_beta")
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_legacy_roster_reference_refused",
        )

    def test_off_roster_identity_is_refused(self):
        self.remove_own_roster_row()
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_identity_off_roster",
        )

    def test_cross_project_binding_and_description_are_refused(self):
        with self.session() as session:
            session.add(
                ProjectRoleBinding(
                    project_id="prj_beta",
                    member_id=self.member_id,
                    runner_id="runner:dsh-cli",
                    model_source="builtin",
                    provider_id="managed:deepseek",
                    connection_ref="native-deepseek-managed-login",
                    model_id="deepseek-flash",
                    model_alias="deepseek-flash",
                    updated_by="human:bobo",
                )
            )
            session.commit()
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_shared_identity_refused",
        )
        with self.session() as session:
            binding = session.get(ProjectRoleBinding, ("prj_beta", self.member_id))
            session.delete(binding)
            session.add(
                ProjectRoleDescription(
                    project_id="prj_beta",
                    member_id=self.member_id,
                    description="他项目说明",
                    updated_by="human:bobo",
                )
            )
            session.commit()
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_shared_identity_refused",
        )

    def test_cross_project_group_reference_is_refused(self):
        self.add_global_group_with_member()
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_group_reference_refused",
        )

    def test_active_instance_is_refused(self):
        self.add_instance("idle")
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_identity_in_use",
        )
        with self.session() as session:
            instance = session.get(AgentInstance, "role-instance-1")
            instance.status = "offline"
            session.add(instance)
            session.commit()
        self.assertEqual(self.rotate_key("prj_alpha", self.member_id).status_code, 200)

    def test_active_task_as_target_and_as_creator_is_refused(self):
        from server.models import AgentTask

        # created_by 侧：该角色发起的在途任务同样构成“在用”。
        with self.make_client() as client:
            created_by_role = client.post(
                "/api/tasks",
                headers={"X-API-Key": self.api_key},
                json={
                    "target_member_id": "agent:other",
                    "content": "由角色发起",
                    "project_id": "prj_alpha",
                },
            )
        self.assertEqual(created_by_role.status_code, 201)
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_identity_in_use",
        )
        with self.session() as session:
            task = session.get(AgentTask, created_by_role.json()["id"])
            task.status = "succeeded"
            session.add(task)
            session.commit()
        self.assertEqual(self.rotate_key("prj_alpha", self.member_id).status_code, 200)

        # target 侧。
        created = self.create_task("prj_alpha", self.member_id)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(
            self.rotate_key("prj_alpha", self.member_id).json()["detail"],
            "rotate_identity_in_use",
        )
        with self.session() as session:
            task = session.get(AgentTask, created.json()["id"])
            task.status = "succeeded"
            session.add(task)
            session.commit()
        self.assertEqual(self.rotate_key("prj_alpha", self.member_id).status_code, 200)

    def test_service_state_in_use_is_honored(self):
        """R1-3 起 ``role_service_state`` 是**真实表**：在用服务必须拒绝轮换。

        R1-1 时该表尚不存在，所以旧用例用一条 ``CREATE TABLE`` 模拟“未来表”；
        R1-3 已按合同 §4.1.5 建表并写入真实状态行，这里直接构造真实在用事实。
        """
        with self.session() as session:
            session.execute(
                text(
                    "INSERT INTO role_service_state (project_id, member_id, "
                    "desired_state, observed_state, manager_kind, control_kind, "
                    "generation, updated_at) VALUES "
                    "('prj_alpha', :member_id, 'running', 'running', "
                    "'cli_process', 'managed_cli', 1, datetime('now'))"
                ),
                {"member_id": self.member_id},
            )
            session.commit()
        response = self.rotate_key("prj_alpha", self.member_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "rotate_identity_in_use")

    # ── 真实并发 ────────────────────────────────────────────────────

    def test_concurrent_rotations_serialize_through_write_lock(self):
        barrier = threading.Barrier(2)

        def rotate():
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    f"/api/projects/prj_alpha/roles/{self.member_id}/rotate-key",
                    headers={"X-API-Key": "bobo-key"},
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: rotate(), range(2)))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        versions = sorted(r.json()["credential_version"] for r in responses)
        self.assertEqual(versions, [2, 3])
        latest = next(r for r in responses if r.json()["credential_version"] == 3)
        stale = next(r for r in responses if r.json()["credential_version"] == 2)
        with self.make_client() as client:
            self.assertEqual(
                client.get(
                    "/api/members/me",
                    headers={"X-API-Key": latest.json()["api_key"]},
                ).status_code,
                200,
            )
            self.assertEqual(
                client.get(
                    "/api/members/me",
                    headers={"X-API-Key": stale.json()["api_key"]},
                ).status_code,
                401,
            )
        with self.session() as session:
            self.assertEqual(
                session.get(
                    ProjectRole, ("prj_alpha", self.member_id)
                ).credential_version,
                3,
            )


class ExclusiveIdentityGuardTests(RoleApiTestCase):
    """合同 §7.5 第 3 条：新独占身份只归属创建项目。"""

    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.register_project("prj_beta")
        self.choice_id = self.seed_runner_and_choice()
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-guard-1",
        )
        assert created.status_code == 201, created.text
        self.member_id = created.json()["member_id"]
        self.api_key = created.json()["api_key"]

    def create_group(self, *, project_id, member_ids, key="bobo-key"):
        with self.make_client() as client:
            return client.post(
                "/api/groups",
                headers={"X-API-Key": key},
                json={
                    "name": "G",
                    "type": "free",
                    "project_id": project_id,
                    "member_ids": member_ids,
                },
            )

    def add_group_member(self, group_id, member_id, *, key="bobo-key"):
        with self.make_client() as client:
            return client.put(
                f"/api/groups/{group_id}/members/{member_id}",
                headers={"X-API-Key": key},
                json={"role": "member"},
            )

    def test_same_project_references_are_allowed(self):
        # 本项目的名册 sync / 绑定 / 说明 / 任务 / 群都保持可用。
        sync = self.sync_roster(
            "prj_alpha", [{"member_id": self.member_id}]
        )
        self.assertEqual(sync.status_code, 200)
        binding = self.put_binding(
            "prj_alpha",
            self.member_id,
            {
                "runner_id": "runner:dsh-cli",
                "model_source": "builtin",
                "provider_id": "managed:deepseek",
                "connection_ref": "native-deepseek-managed-login",
                "model_id": "deepseek-flash",
                "model_alias": "deepseek-flash",
            },
        )
        self.assertEqual(binding.status_code, 200)
        with self.make_client() as client:
            description = client.put(
                f"/api/projects/prj_alpha/agents/{self.member_id}/description",
                headers={"X-API-Key": "bobo-key"},
                json={"description": "本项目说明"},
            )
        self.assertEqual(description.status_code, 200)
        self.assertEqual(self.create_task("prj_alpha", self.member_id).status_code, 201)
        group = self.create_group(project_id="prj_alpha", member_ids=[self.member_id])
        self.assertEqual(group.status_code, 201)

    def test_cross_project_roster_binding_and_description_are_refused(self):
        sync = self.sync_roster("prj_beta", [{"member_id": self.member_id}])
        self.assertEqual(sync.status_code, 409)
        self.assertEqual(
            sync.json()["detail"], "identity_exclusive_reference_refused"
        )
        with self.session() as session:
            self.assertIsNone(
                session.get(ProjectAgent, ("prj_beta", self.member_id))
            )

        # 绑定目标必须先在名册：先手工构造他项目名册行，再验证绑定/说明写入守卫。
        with self.session() as session:
            session.add(
                ProjectAgent(project_id="prj_beta", member_id=self.member_id)
            )
            session.commit()
        binding = self.put_binding(
            "prj_beta",
            self.member_id,
            {
                "runner_id": "runner:dsh-cli",
                "model_source": "builtin",
                "provider_id": "managed:deepseek",
                "connection_ref": "native-deepseek-managed-login",
                "model_id": "deepseek-flash",
                "model_alias": "deepseek-flash",
            },
        )
        self.assertEqual(binding.status_code, 409)
        self.assertEqual(
            binding.json()["detail"], "identity_exclusive_reference_refused"
        )
        with self.make_client() as client:
            description = client.put(
                f"/api/projects/prj_beta/agents/{self.member_id}/description",
                headers={"X-API-Key": "bobo-key"},
                json={"description": "跨项目说明"},
            )
        self.assertEqual(description.status_code, 409)
        with self.session() as session:
            self.assertIsNone(
                session.get(ProjectRoleBinding, ("prj_beta", self.member_id))
            )
            self.assertIsNone(
                session.get(ProjectRoleDescription, ("prj_beta", self.member_id))
            )

    def test_cross_project_and_global_groups_are_refused(self):
        other_project = self.create_group(
            project_id="prj_beta", member_ids=[self.member_id]
        )
        self.assertEqual(other_project.status_code, 409)
        self.assertEqual(
            other_project.json()["detail"], "identity_exclusive_reference_refused"
        )
        global_group = self.create_group(project_id=None, member_ids=[self.member_id])
        self.assertEqual(global_group.status_code, 409)

        # 成员新增路径同样拒绝：先建一个不含该成员的本项目群。
        ok_group = self.create_group(project_id="prj_alpha", member_ids=[])
        self.assertEqual(ok_group.status_code, 201)
        group_id = ok_group.json()["id"]
        with self.session() as session:
            session.add(
                Group(
                    id="group:other-project",
                    name="Other",
                    type="free",
                    project_id="prj_beta",
                    created_by="human:bobo",
                )
            )
            session.commit()
        self.assertEqual(
            self.add_group_member("group:other-project", self.member_id).status_code,
            409,
        )
        self.assertEqual(self.add_group_member(group_id, self.member_id).status_code, 200)

    def test_global_task_reference_is_refused(self):
        with self.make_client() as client:
            response = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": self.member_id, "content": "全局任务"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "identity_exclusive_reference_refused"
        )
        with self.make_client() as client:
            created_by_role = client.post(
                "/api/tasks",
                headers={"X-API-Key": self.api_key},
                json={"target_member_id": "agent:other", "content": "全局任务"},
            )
        self.assertEqual(created_by_role.status_code, 409)

    def test_schedule_derived_task_is_guarded(self):
        """计划派生与直接创建共用同一写入漏斗：全局派生同样被拒。"""
        with self.make_client() as client:
            schedule = client.post(
                "/api/tasks/schedules",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": self.member_id,
                    "content": "计划派生",
                    "run_at": "2026-01-01T00:00:00+00:00",
                },
            )
            self.assertEqual(schedule.status_code, 201)
            run_due = client.post(
                "/api/tasks/schedules/run-due", headers={"X-API-Key": "bobo-key"}
            )
        self.assertEqual(run_due.status_code, 409)
        self.assertEqual(
            run_due.json()["detail"], "identity_exclusive_reference_refused"
        )
        with self.session() as session:
            from server.models import AgentTask

            self.assertEqual(
                list(session.exec(select(AgentTask)).all()), []
            )

    def test_legacy_members_keep_old_behavior(self):
        """历史无 ProjectRole 成员：跨项目群/任务照旧可用（不误伤）。"""
        global_group = self.create_group(
            project_id=None, member_ids=["agent:worker"]
        )
        self.assertEqual(global_group.status_code, 201)
        with self.make_client() as client:
            task = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:worker", "content": "全局任务"},
            )
        self.assertEqual(task.status_code, 201)

    def test_concurrent_rotation_and_reference_insert_converge(self):
        """写入锁 + 守卫：并发跨项目引用新增不会绕过独占身份归属。"""
        barrier = threading.Barrier(2)

        def rotate():
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    f"/api/projects/prj_alpha/roles/{self.member_id}/rotate-key",
                    headers={"X-API-Key": "bobo-key"},
                )

        def add_reference():
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    "/api/groups",
                    headers={"X-API-Key": "bobo-key"},
                    json={
                        "name": "Cross",
                        "type": "free",
                        "project_id": "prj_beta",
                        "member_ids": [self.member_id],
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            rotation_future = executor.submit(rotate)
            reference_future = executor.submit(add_reference)
            rotation = rotation_future.result()
            reference = reference_future.result()

        self.assertEqual(rotation.status_code, 200)
        self.assertEqual(reference.status_code, 409)
        self.assertEqual(
            reference.json()["detail"], "identity_exclusive_reference_refused"
        )
        with self.session() as session:
            memberships = list(
                session.exec(
                    select(GroupMember).where(
                        GroupMember.member_id == self.member_id
                    )
                ).all()
            )
        self.assertEqual(memberships, [])


class ReferenceGuardWriteTransactionTests(ExclusiveIdentityGuardTests):
    """F2 补正：六类引用守卫必须运行在**实际 SQLite 写事务（写锁）**内。

    独立探针（review F2）在守卫处观察到 ``session.in_transaction()=True`` 而
    ``driver_connection.in_transaction=False``：ORM 逻辑事务不能替代真实写事务。
    本类覆盖名册 sync、绑定、说明、群创建（含 creator）、群成员新增、任务 Hall
    （含 created_by/target、子任务实际根项目、计划派生），并给出真实 WAL 双连接的
    锁顺序/边界证据（引用先持锁、轮换先持锁两个方向）。
    """

    # ── 真实连接与写锁证据 ───────────────────────────────────────────

    def enable_wal(self) -> str:
        with self.engine.connect() as connection:
            mode = connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar()
            connection.commit()
        return str(mode).lower()

    def try_write_lock_from_independent_connection(self) -> dict:
        """独立真实连接尝试 ``BEGIN IMMEDIATE``：持锁者存在时应被 SQLite 拒绝。"""
        connection = sqlite3.connect(
            str(self.db_path), timeout=0.3, isolation_level=None
        )
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                return {"blocked": True, "error": str(exc)}
            connection.execute("ROLLBACK")
            return {"blocked": False, "error": None}
        finally:
            connection.close()

    def _binding_body(self) -> dict:
        return {
            key: value
            for key, value in CHOICE_DEFAULTS.items()
            if key != "source_kind"
        } | {"runner_id": RUNNER_ID}

    def _run_due_schedule(self) -> int:
        with self.make_client() as client:
            schedule = client.post(
                "/api/tasks/schedules",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": self.member_id,
                    "content": "计划派生守卫",
                    "run_at": "2026-01-01T00:00:00+00:00",
                },
            )
            assert schedule.status_code == 201, schedule.text
            response = client.post(
                "/api/tasks/schedules/run-due", headers={"X-API-Key": "bobo-key"}
            )
        # 计划派生没有项目维度 → 独占身份守卫拒绝，但必须先进入真实写事务。
        return response.status_code

    def _create_guarded_subtask(self) -> int:
        root = self.create_task("prj_alpha", self.member_id, may_delegate=True)
        assert root.status_code == 201, root.text
        root_body = root.json()
        with self.make_client() as client:
            claim = client.post(
                f"/api/tasks/{root_body['id']}/claim",
                headers={"X-API-Key": self.api_key},
                json={},
            )
            assert claim.status_code == 200, claim.text
            child = client.post(
                "/api/tasks",
                headers={"X-API-Key": self.api_key},
                json={
                    "parent_task_id": root_body["id"],
                    "authorization_epoch": root_body["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "子任务实际根项目守卫",
                },
            )
        return child.status_code

    def _add_global_group_reference(self):
        with self.make_client() as client:
            return client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "name": "Cross",
                    "type": "free",
                    "project_id": None,
                    "member_ids": [self.member_id],
                },
            )

    # ── 六类路径的实际写事务证据 ─────────────────────────────────────

    def test_reference_guards_run_inside_actual_write_transaction(self):
        self.assertEqual(self.enable_wal(), "wal")
        import server.models as models

        observed: list[dict] = []
        label = [""]
        original_projection = models.exclusive_identity_owner_project

        def observer(member_id, session):
            driver = session.connection().connection.driver_connection
            observed.append(
                {
                    "operation": label[0],
                    "member_id": member_id,
                    "sqlalchemy_in_transaction": session.in_transaction(),
                    "sqlite_in_transaction": bool(driver.in_transaction),
                }
            )
            return original_projection(member_id, session)

        statuses: dict[str, int] = {}
        with mock.patch.object(
            models, "exclusive_identity_owner_project", observer
        ):
            label[0] = "roster_sync"
            statuses[label[0]] = self.sync_roster(
                "prj_alpha", [{"member_id": self.member_id}]
            ).status_code
            label[0] = "binding"
            statuses[label[0]] = self.put_binding(
                "prj_alpha", self.member_id, self._binding_body()
            ).status_code
            label[0] = "description"
            with self.make_client() as client:
                statuses[label[0]] = client.put(
                    f"/api/projects/prj_alpha/agents/{encode(self.member_id)}"
                    "/description",
                    headers={"X-API-Key": "bobo-key"},
                    json={"description": "写事务守卫"},
                ).status_code
            label[0] = "group_create"
            created_group = self.create_group(
                project_id="prj_alpha", member_ids=[self.member_id]
            )
            statuses[label[0]] = created_group.status_code
            label[0] = "group_member"
            empty_group = self.create_group(project_id="prj_alpha", member_ids=[])
            statuses[label[0]] = self.add_group_member(
                empty_group.json()["id"], self.member_id
            ).status_code
            label[0] = "task_hall"
            statuses[label[0]] = self.create_task(
                "prj_alpha", self.member_id
            ).status_code
            label[0] = "subtask"
            statuses[label[0]] = self._create_guarded_subtask()
            label[0] = "schedule_derived"
            statuses[label[0]] = self._run_due_schedule()

        self.assertEqual(
            statuses,
            {
                "roster_sync": 200,
                "binding": 200,
                "description": 200,
                "group_create": 201,
                "group_member": 200,
                "task_hall": 201,
                "subtask": 201,
                "schedule_derived": 409,
            },
        )
        operations = {row["operation"] for row in observed}
        self.assertTrue(
            {
                "roster_sync",
                "binding",
                "description",
                "group_create",
                "group_member",
                "task_hall",
                "subtask",
                "schedule_derived",
            }
            <= operations,
            f"守卫未被全部路径触发: {sorted(operations)}",
        )
        # ORM 逻辑事务成立（与独立探针一致）……
        self.assertTrue(any(row["sqlalchemy_in_transaction"] for row in observed))
        # ……但真正要证明的是实际 SQLite 写事务：任何一次守卫读取都必须为 True。
        offenders = [
            row for row in observed if not row["sqlite_in_transaction"]
        ]
        self.assertEqual(
            offenders, [], f"守卫读取未进入实际 SQLite 写事务: {offenders}"
        )

    # ── 锁顺序：引用先持锁 / 轮换先持锁 ─────────────────────────────

    def test_reference_write_holds_lock_before_rotation(self):
        self.assertEqual(self.enable_wal(), "wal")
        import server.models as models

        original_projection = models.exclusive_identity_owner_project
        entered = threading.Event()
        release = threading.Event()
        calls: list[str] = []
        calls_lock = threading.Lock()
        probe: dict = {}
        rotation_was_blocked = False

        def gated(member_id, session):
            owner = original_projection(member_id, session)
            if owner is not None:
                with calls_lock:
                    calls.append(member_id)
                    is_first = len(calls) == 1
                if is_first:
                    entered.set()
                    release.wait(timeout=15)
            return owner

        def add_reference():
            return self._add_global_group_reference()

        def rotate():
            return self.rotate_key("prj_alpha", self.member_id)

        with mock.patch.object(models, "exclusive_identity_owner_project", gated):
            with ThreadPoolExecutor(max_workers=2) as executor:
                reference_future = executor.submit(add_reference)
                rotation_future = None
                try:
                    entered_ok = entered.wait(timeout=15)
                    if entered_ok:
                        # 引用写路径持锁中：独立真实连接取不到写锁。
                        probe = self.try_write_lock_from_independent_connection()
                        rotation_future = executor.submit(rotate)
                        time.sleep(0.6)
                        rotation_was_blocked = (
                            rotation_future is not None
                            and not rotation_future.done()
                        )
                finally:
                    release.set()
                reference = reference_future.result(timeout=30)
                rotation = (
                    rotation_future.result(timeout=30)
                    if rotation_future is not None
                    else None
                )

        self.assertTrue(entered_ok, "引用写路径未进入独占身份守卫")
        self.assertTrue(
            probe.get("blocked"),
            f"守卫执行时未持有实际写锁：{probe.get('error')}",
        )
        self.assertTrue(rotation_was_blocked, "轮换未被引用写路径的写锁串行化")
        self.assertEqual(reference.status_code, 409)
        self.assertEqual(
            reference.json()["detail"], "identity_exclusive_reference_refused"
        )
        self.assertIsNotNone(rotation)
        self.assertEqual(rotation.status_code, 200)

    def test_rotation_holds_lock_before_reference_write(self):
        self.assertEqual(self.enable_wal(), "wal")
        import server.routes.projects as projects_route

        original_proof = projects_route.prove_exclusive_identity
        entered = threading.Event()
        release = threading.Event()
        started = threading.Event()
        probe: dict = {}
        state: dict = {}
        reference_was_blocked = False

        def gated(project_id, member_id, session):
            driver = session.connection().connection.driver_connection
            state["sqlite_in_transaction"] = bool(driver.in_transaction)
            entered.set()
            release.wait(timeout=15)
            return original_proof(project_id, member_id, session)

        def rotate():
            return self.rotate_key("prj_alpha", self.member_id)

        def add_reference():
            started.set()
            return self._add_global_group_reference()

        with mock.patch.object(projects_route, "prove_exclusive_identity", gated):
            with ThreadPoolExecutor(max_workers=2) as executor:
                rotation_future = executor.submit(rotate)
                reference_future = None
                try:
                    entered_ok = entered.wait(timeout=15)
                    if entered_ok:
                        # 轮换持锁中（独占证明内）：独立真实连接取不到写锁。
                        probe = self.try_write_lock_from_independent_connection()
                        reference_future = executor.submit(add_reference)
                        self.assertTrue(started.wait(timeout=15))
                        time.sleep(0.6)
                        reference_was_blocked = (
                            reference_future is not None
                            and not reference_future.done()
                        )
                finally:
                    release.set()
                rotation = rotation_future.result(timeout=30)
                reference = (
                    reference_future.result(timeout=30)
                    if reference_future is not None
                    else None
                )

        self.assertTrue(entered_ok, "轮换未进入独占证明")
        self.assertTrue(
            state.get("sqlite_in_transaction"),
            "独占证明未在实际 SQLite 写事务内执行",
        )
        self.assertTrue(
            probe.get("blocked"),
            f"独占证明执行时未持有实际写锁：{probe.get('error')}",
        )
        self.assertTrue(reference_was_blocked, "引用新增未被轮换的写锁串行化")
        self.assertEqual(rotation.status_code, 200)
        self.assertIsNotNone(reference)
        self.assertEqual(reference.status_code, 409)
        self.assertEqual(
            reference.json()["detail"], "identity_exclusive_reference_refused"
        )


if __name__ == "__main__":
    unittest.main()
