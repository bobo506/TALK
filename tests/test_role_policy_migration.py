"""角色生命周期 R1-1：权限策略一次性迁移与分级读路径切换（合同 §6.2/§8）。

覆盖实施计划 §3.5/§3.6 与合同 §8.5 的步骤 0–11：

- 老形态库 ``init_db()`` 两次幂等：只新增表/列/索引 + **一次**策略回填行，
  旧行/旧列值不变；人工改权后重复初始化不覆盖；
- ``_can_exempt_review`` 四条件读路径：human 与 ``project_id is None`` 分支不变，
  离册休眠 / 回册恢复 / 归档休眠 / 老名册兼容放行 / 新角色不获豁免；
- 改旧 ``decision_tier`` 既不重授也不撤权；sync 两次权限不变；
- 归档守卫：创建 ``400 task_role_archived``、领取 ``409 role_archived``，
  历史不带项目任务保持旧边界。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型、不读凭据。
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, create_engine, select

import server.db as db
import server.main as main
from server.models import (
    ROLE_POLICY_MIGRATION_KEY,
    Member,
    ProjectAgent,
    ProjectRole,
    ProjectRolePolicy,
    SchemaMigration,
)
from server.routes.tasks import _can_exempt_review
from tests.test_project_roles import RoleApiTestCase

LEGACY_RUNNER_ID = "runner:legacy-cli"


class LegacyPolicyMigrationTests(unittest.TestCase):
    """I12：老库只增表/列/索引 + 一次性策略回填；重复 init_db() 不改写既有事实。"""

    def setUp(self):
        super().setUp()
        tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self._tmpdir = Path(tempfile.mkdtemp(prefix="talk-r1-1-legacy-", dir=tmp_root))
        self.db_path = self._tmpdir / "legacy.db"
        self._write_legacy_database()
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self._old_engine = db.engine
        self._old_main_engine = main.engine
        db.engine = self.engine
        main.engine = self.engine
        self.addCleanup(self._restore_engines)

    def _restore_engines(self):
        db.engine = self._old_engine
        main.engine = self._old_main_engine
        self.engine.dispose()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_legacy_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE projects (
                    project_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    maintainer_member_id TEXT NOT NULL,
                    created_at TIMESTAMP,
                    last_seen_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE members (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    api_key TEXT NOT NULL UNIQUE,
                    poll_hint INTEGER,
                    created_at TIMESTAMP,
                    disabled_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE project_agents (
                    project_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    identity_path TEXT,
                    soul_path TEXT,
                    user_path TEXT,
                    memory_pointer TEXT,
                    business_role TEXT,
                    decision_tier TEXT,
                    capability_summary JSON NOT NULL DEFAULT '[]',
                    updated_at TIMESTAMP,
                    PRIMARY KEY (project_id, member_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE runner_registry (
                    runner_id TEXT PRIMARY KEY,
                    runtime TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    adapter_status TEXT NOT NULL DEFAULT 'unverified',
                    adapter_note TEXT,
                    capabilities JSON NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE agent_instances (
                    id TEXT PRIMARY KEY,
                    member_id TEXT NOT NULL,
                    runtime TEXT NOT NULL,
                    status TEXT NOT NULL,
                    host TEXT,
                    pid INTEGER,
                    current_task_id TEXT,
                    last_error TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    last_seen_at TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO projects (project_id, display_name, maintainer_member_id) "
                "VALUES ('prj_legacy', 'Legacy', 'human:bobo')"
            )
            conn.execute(
                "INSERT INTO members (id, kind, display_name, api_key) "
                "VALUES ('human:bobo', 'human', 'Bobo', 'bobo-key')"
            )
            conn.execute(
                "INSERT INTO members (id, kind, display_name, api_key) "
                "VALUES ('agent:worker', 'agent', 'Worker', 'worker-key')"
            )
            conn.execute(
                "INSERT INTO project_agents (project_id, member_id, decision_tier) "
                "VALUES ('prj_legacy', 'agent:worker', 'decision')"
            )
            conn.execute(
                "INSERT INTO project_agents (project_id, member_id, decision_tier) "
                "VALUES ('prj_legacy', 'agent:other', 'execution')"
            )
            conn.execute(
                """
                INSERT INTO runner_registry (
                    runner_id, runtime, display_name, adapter_status, capabilities, created_by
                ) VALUES (?, 'dsh', 'Legacy CLI', 'discovered', '[]', 'human:bobo')
                """,
                (LEGACY_RUNNER_ID,),
            )
            conn.execute(
                """
                INSERT INTO agent_instances (id, member_id, runtime, status)
                VALUES ('legacy-instance', 'agent:worker', 'dsh', 'idle')
                """
            )
            conn.commit()

    def _tables(self) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[0]
                for row in conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

    def _indexes(self) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[0]
                for row in conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }

    def test_legacy_upgrade_adds_tables_columns_indexes_once(self):
        self.assertNotIn("project_role_policies", self._tables())
        self.assertNotIn("runner_model_choices", self._tables())

        db.init_db()
        db.init_db()  # 重复初始化必须幂等

        tables = self._tables()
        for table in (
            "runner_model_choices",
            "project_roles",
            "role_creation_operations",
            "project_role_policies",
            "schema_migrations",
        ):
            self.assertIn(table, tables)
        indexes = self._indexes()
        for index in (
            "ux_runner_model_choices_dim",
            "ux_project_roles_active_name",
            "ux_role_creation_operations_identity",
            "ix_role_creation_operations_member",
            "ix_agent_instances_project_id",
            "ix_agent_instances_launch_id",
            "ix_runner_registry_control_kind",
        ):
            self.assertIn(index, indexes)

        with Session(self.engine) as session:
            # 一次性回填只产生一行，且只针对 decision 行。
            policies = list(session.exec(select(ProjectRolePolicy)).all())
            self.assertEqual(len(policies), 1)
            self.assertEqual(policies[0].member_id, "agent:worker")
            self.assertEqual(policies[0].review_exempt, 1)
            self.assertEqual(policies[0].source, "migration_decision_tier")
            self.assertEqual(
                [row.key for row in session.exec(select(SchemaMigration)).all()],
                [ROLE_POLICY_MIGRATION_KEY],
            )
            # 旧行原值不变。
            roster = list(session.exec(select(ProjectAgent)).all())
            self.assertEqual(
                {(row.member_id, row.decision_tier) for row in roster},
                {("agent:worker", "decision"), ("agent:other", "execution")},
            )
            # 新列/新索引：旧行 control_kind='unknown'，实例新列保持 NULL。
            runner = session.execute(
                text("SELECT control_kind FROM runner_registry WHERE runner_id=:r"),
                {"r": LEGACY_RUNNER_ID},
            ).scalar()
            self.assertEqual(runner, "unknown")
            instance = session.execute(
                text(
                    "SELECT project_id, launch_id, process_started_at "
                    "FROM agent_instances WHERE id='legacy-instance'"
                )
            ).one()
            self.assertEqual(tuple(instance), (None, None, None))

    def test_repeated_init_db_does_not_overwrite_human_policy_change(self):
        db.init_db()
        with Session(self.engine) as session:
            policy = session.get(ProjectRolePolicy, ("prj_legacy", "agent:worker"))
            policy.review_exempt = 0
            policy.source = "human_grant"
            policy.granted_by = "human:bobo"
            session.add(policy)
            session.commit()

        db.init_db()
        db.init_db()

        with Session(self.engine) as session:
            policies = list(session.exec(select(ProjectRolePolicy)).all())
            self.assertEqual(len(policies), 1)
            self.assertEqual(policies[0].review_exempt, 0)
            self.assertEqual(policies[0].source, "human_grant")
            self.assertEqual(
                len(list(session.exec(select(SchemaMigration)).all())), 1
            )
            self.assertEqual(
                len(list(session.exec(select(ProjectAgent)).all())), 2
            )


class RolePolicyReadPathTests(RoleApiTestCase):
    """§8.5 步骤 0–11：保留策略事实 ≠ 当前可用权限。"""

    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.choice_id = self.seed_runner_and_choice()
        # 步骤 0：老形态库（名册行带旧分级、无策略行）。
        self.sync_roster(
            "prj_alpha",
            [
                {
                    "member_id": "agent:worker",
                    "decision_tier": "decision",
                    "identity_path": ".talk/agents/agent_worker/IDENTITY.md",
                },
                {
                    "member_id": "agent:other",
                    "decision_tier": "execution",
                    "identity_path": ".talk/agents/agent_other/IDENTITY.md",
                },
            ],
        )
        self._run_policy_migration()

    def _run_policy_migration(self) -> None:
        """把当前名册行当成“迁移前旧库”，重跑一次性回填（测试内受控，不改生产库）。"""
        with self.session() as session:
            session.execute(
                text("DELETE FROM schema_migrations WHERE key = :key"),
                {"key": ROLE_POLICY_MIGRATION_KEY},
            )
            session.commit()
        db.init_db()

    def _exempt(self, member_id: str, project_id: str | None = "prj_alpha") -> bool:
        with self.session() as session:
            member = session.get(Member, member_id)
            return _can_exempt_review(member, project_id, session)

    def _roster_payload(self, entries: list[tuple[str, str]]) -> list[dict]:
        return [
            {"member_id": member_id, "decision_tier": tier}
            for member_id, tier in entries
        ]

    # ── 步骤 1–6：迁移、幂等、sync、改旧分级 ─────────────────────────

    def test_migration_backfills_once_and_survives_repeated_init(self):
        with self.session() as session:
            policies = {
                row.member_id: row
                for row in session.exec(select(ProjectRolePolicy)).all()
            }
        self.assertEqual(set(policies), {"agent:worker"})
        self.assertEqual(policies["agent:worker"].review_exempt, 1)
        self.assertEqual(policies["agent:worker"].source, "migration_decision_tier")
        self.assertTrue(self._exempt("agent:worker"))
        self.assertFalse(self._exempt("agent:other"))

        db.init_db()
        db.init_db()
        with self.session() as session:
            self.assertEqual(
                len(list(session.exec(select(ProjectRolePolicy)).all())), 1
            )
            self.assertEqual(
                len(list(session.exec(select(SchemaMigration)).all())), 1
            )
        self.assertTrue(self._exempt("agent:worker"))

    def test_sync_twice_keeps_exemption_and_old_tier_edits_do_not_change_it(self):
        for _ in range(2):
            response = self.sync_roster(
                "prj_alpha",
                self._roster_payload(
                    [("agent:worker", "decision"), ("agent:other", "execution")]
                ),
            )
            self.assertEqual(response.status_code, 200)
        self.assertTrue(self._exempt("agent:worker"))
        self.assertFalse(self._exempt("agent:other"))

        # 步骤 5：改旧分级为 execution → 不撤权。
        self.sync_roster(
            "prj_alpha",
            self._roster_payload(
                [("agent:worker", "execution"), ("agent:other", "execution")]
            ),
        )
        self.assertTrue(self._exempt("agent:worker"))

        # 步骤 6：把从未迁移的成员改成分级 decision → 不重授。
        self.sync_roster(
            "prj_alpha",
            self._roster_payload(
                [("agent:worker", "execution"), ("agent:other", "decision")]
            ),
        )
        self.assertFalse(self._exempt("agent:other"))
        with self.session() as session:
            self.assertIsNone(
                session.get(ProjectRolePolicy, ("prj_alpha", "agent:other"))
            )

    # ── 步骤 7–9：离册休眠 / 回册恢复 / 归档休眠 ─────────────────────

    def test_off_roster_sleeps_and_rejoin_restores(self):
        self.sync_roster("prj_alpha", self._roster_payload([("agent:other", "execution")]))
        self.assertFalse(self._exempt("agent:worker"))
        with self.session() as session:
            self.assertIsNotNone(
                session.get(ProjectRolePolicy, ("prj_alpha", "agent:worker"))
            )

        self.sync_roster(
            "prj_alpha",
            self._roster_payload(
                [("agent:worker", "execution"), ("agent:other", "execution")]
            ),
        )
        self.assertTrue(self._exempt("agent:worker"))

    def test_archived_role_sleeps_but_keeps_policy_row(self):
        with self.session() as session:
            session.add(
                ProjectRole(
                    project_id="prj_alpha",
                    member_id="agent:worker",
                    role_name="legacy-worker",
                    origin="imported",
                    identity_exclusive=0,
                    credential_version=1,
                    created_by="human:bobo",
                    archived_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        self.assertFalse(self._exempt("agent:worker"))
        with self.session() as session:
            policy = session.get(ProjectRolePolicy, ("prj_alpha", "agent:worker"))
            self.assertEqual(policy.review_exempt, 1)

    def test_legacy_roster_without_project_role_still_passes(self):
        # 步骤 11：老名册（无 ProjectRole 行）走 ①②④ 兼容放行。
        with self.session() as session:
            self.assertIsNone(
                session.get(ProjectRole, ("prj_alpha", "agent:worker"))
            )
        self.assertTrue(self._exempt("agent:worker"))

    # ── 步骤 10：新角色不获豁免；human 与无项目分支不变 ───────────────

    def test_new_role_gets_no_policy_and_human_branch_unchanged(self):
        created = self.create_role(
            "prj_alpha",
            role_name="new-dev",
            choice_id=self.choice_id,
            operation_key="op-key-policy-1",
        )
        self.assertEqual(created.status_code, 201)
        member_id = created.json()["member_id"]
        self.assertFalse(self._exempt(member_id))
        with self.session() as session:
            self.assertIsNone(
                session.get(ProjectRolePolicy, ("prj_alpha", member_id))
            )
        self.assertTrue(self._exempt("human:bobo"))
        self.assertTrue(self._exempt("human:bobo", None))
        self.assertFalse(self._exempt("agent:worker", None))

    def test_disabled_agent_loses_exemption_even_with_policy(self):
        with self.session() as session:
            member = session.get(Member, "agent:worker")
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        self.assertFalse(self._exempt("agent:worker"))

    # ── API 级：development + review_policy=exempt ───────────────────

    def test_api_level_exemption_requires_current_policy(self):
        """真实子任务路径：development + review_policy=exempt 才走 `_can_exempt_review`。"""
        with self.make_client() as client:
            worker_root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:worker",
                    "content": "root for worker",
                    "project_id": "prj_alpha",
                    "may_delegate": True,
                },
            )
            other_root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:other",
                    "content": "root for other",
                    "project_id": "prj_alpha",
                    "may_delegate": True,
                },
            )
            self.assertEqual(worker_root.status_code, 201)
            self.assertEqual(other_root.status_code, 201)
            worker_root_id = worker_root.json()["id"]
            other_root_id = other_root.json()["id"]
            for task_id, key in ((worker_root_id, "worker-key"), (other_root_id, "other-key")):
                claim = client.post(
                    f"/api/tasks/{task_id}/claim",
                    headers={"X-API-Key": key},
                    json={},
                )
                self.assertEqual(claim.status_code, 200)

            exempt = client.post(
                "/api/tasks",
                headers={"X-API-Key": "worker-key"},
                json={
                    "target_member_id": "agent:other",
                    "content": "dev slice",
                    "parent_task_id": worker_root_id,
                    "authorization_epoch": worker_root.json()["authorization_epoch"],
                    "task_kind": "development",
                    "review_policy": "exempt",
                },
            )
            not_exempt = client.post(
                "/api/tasks",
                headers={"X-API-Key": "other-key"},
                json={
                    "target_member_id": "agent:worker",
                    "content": "dev slice",
                    "parent_task_id": other_root_id,
                    "authorization_epoch": other_root.json()["authorization_epoch"],
                    "task_kind": "development",
                    "review_policy": "exempt",
                },
            )
        self.assertEqual(exempt.status_code, 201)
        self.assertEqual(not_exempt.status_code, 403)


class ArchivedRoleTaskGuardTests(RoleApiTestCase):
    """R5：归档守卫同时落在创建与领取两处；归档入口本身不在 R1-1。"""

    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.choice_id = self.seed_runner_and_choice()

    def test_create_guard_refuses_archived_role(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-archived-guard-1",
        )
        member_id = created.json()["member_id"]
        with self.make_client() as client:
            before = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": member_id,
                    "content": "before archive",
                    "project_id": "prj_alpha",
                },
            )
        self.assertEqual(before.status_code, 201)
        self.archive_role("prj_alpha", member_id)

        with self.make_client() as client:
            after = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": member_id,
                    "content": "after archive",
                    "project_id": "prj_alpha",
                },
            )
        self.assertEqual(after.status_code, 400)
        self.assertEqual(after.json()["detail"], "task_role_archived")

    def test_claim_guard_refuses_archived_role_and_keeps_committed_facts(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-archived-guard-2",
        )
        member_id = created.json()["member_id"]
        api_key = created.json()["api_key"]
        with self.make_client() as client:
            task = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": member_id,
                    "content": "queued before archive",
                    "project_id": "prj_alpha",
                },
            )
        self.assertEqual(task.status_code, 201)
        task_id = task.json()["id"]
        self.archive_role("prj_alpha", member_id)

        with self.make_client() as client:
            claim = client.post(
                f"/api/tasks/{task_id}/claim",
                headers={"X-API-Key": api_key},
                json={},
            )
        self.assertEqual(claim.status_code, 409)
        self.assertEqual(claim.json()["detail"], "role_archived")

        # 已提交事实保留：任务仍是 queued，未被取消或改写。
        with self.make_client() as client:
            visible = client.get(
                f"/api/tasks/{task_id}", headers={"X-API-Key": "bobo-key"}
            )
        self.assertEqual(visible.json()["status"], "queued")

    def test_historical_member_without_new_identity_keeps_old_boundary(self):
        """历史成员（non-exclusive imported 角色）不带项目时保持旧行为。"""
        with self.make_client() as client:
            client.post(
                "/api/projects/prj_alpha/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": "agent:other"}]},
            )
        with self.session() as session:
            session.add(
                ProjectRole(
                    project_id="prj_alpha",
                    member_id="agent:other",
                    role_name="legacy-other",
                    origin="imported",
                    identity_exclusive=0,
                    credential_version=1,
                    created_by="human:bobo",
                    archived_at=datetime.now(timezone.utc),
                )
            )
            session.commit()

        with self.make_client() as client:
            project_task = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:other",
                    "content": "project scoped",
                    "project_id": "prj_alpha",
                },
            )
            global_task = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:other", "content": "global"},
            )
        self.assertEqual(project_task.status_code, 400)
        self.assertEqual(project_task.json()["detail"], "task_role_archived")
        self.assertEqual(global_task.status_code, 201)


if __name__ == "__main__":
    unittest.main()
