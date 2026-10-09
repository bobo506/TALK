"""ROLE-BINDING-B1a 项目角色绑定：迁移、读写、有效性阶梯与事实读取合同测试。

覆盖实施计划 §1.6/§1.7 的 A1、A5–A21（A22 由既有回归文件承担）：

- A1 老形态库 ``init_db()`` 两次幂等，只加新表/新索引，不回填虚构数据；
- A5/A6/A7/A8 绑定读写、并存行、同角色版本、同指纹不同角色；
- A9/A10 校验与错误码（422/404/403）；
- A11 目标不在有效名册、解除绑定幂等；
- A12/A13 离册回册与状态优先级；
- A14/A15/A16 不影响其它维度、sync 全量替换、项目删除清理；
- A17 双连接 upsert 收敛（last-write-wins，无主键 409）；
- A18 载荷计数冒烟（不越界改 bridge/B3）；
- A19/A20/A21 事实助手：无绑定四例 1 行、离册有/无绑定、项目不存在、27 列、
  单语句性质（带项目 1 条 / 无项目 0 条）、批量等价与查询数固定。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型、不读 Key、
不改生产数据库/名册/.talk/安装配置。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from sqlalchemy import event, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, create_engine, select

import server.db as db
import server.main as main
import server.routes.projects as projects_route
from server.models import (
    BINDING_FACTS_COLUMNS,
    BINDING_FACTS_SQL,
    ROLE_BINDING_BOUND,
    ROLE_BINDING_MEMBER_DISABLED,
    ROLE_BINDING_MEMBER_MISSING,
    ROLE_BINDING_NOT_AGENT,
    ROLE_BINDING_NOT_IN_ROSTER,
    ROLE_BINDING_PARTIAL,
    ROLE_BINDING_RUNNER_MISSING,
    ROLE_BINDING_RUNNER_RETIRED,
    ROLE_BINDING_UNCONFIGURED,
    Member,
    Project,
    ProjectAgent,
    ProjectRoleBinding,
    RunnerRegistry,
    binding_fingerprint,
    is_parseable_stored_runner_id,
    is_parseable_stored_runtime,
    is_safe_identifier_token,
    read_role_binding_facts,
    read_role_binding_facts_batch,
    resolve_role_binding_state,
)
from tests.test_support import RouteTestCase

EXPECTED_SQL_SHA = "a812ee474b4710f5eac29f773fb02f39dec70201c3fdd0abc66709f7b17f0f1e"

RUNNER_ID = "runner:dsh-cli"
RUNNER_RUNTIME = "dsh"
MODEL_ID = "deepseek-flash"
CONNECTION_REF = "native-deepseek-managed-login"


def encode(member_id: str) -> str:
    return quote(member_id, safe="")


def fingerprint_of(
    runner_id: str = RUNNER_ID,
    runtime: str = RUNNER_RUNTIME,
    model_source: str = "builtin",
    provider_id: str = "managed:deepseek",
    connection_ref: str = CONNECTION_REF,
    model_id: str = MODEL_ID,
) -> str:
    payload = "|".join(
        [runner_id, runtime, model_source, provider_id, connection_ref, model_id]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BindingApiTestCase(RouteTestCase):
    """绑定 API 公共夹具：human / agent / disabled / 非 agent 成员与常用请求封装。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:ann", api_key="ann-key", display_name="Ann")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        self.add_member("agent:other", api_key="other-key", display_name="Other")
        self.add_member("agent:parked", api_key="parked-key", display_name="Parked")
        self.add_member("agent:extra", api_key="extra-key", display_name="Extra")
        self.add_member("agent:extra2", api_key="extra2-key", display_name="Extra2")
        self.add_member("agent:extra3", api_key="extra3-key", display_name="Extra3")
        self.add_member("human:henry", api_key="henry-key", display_name="Henry")
        with self.session() as session:
            parked = session.get(Member, "agent:parked")
            parked.disabled_at = datetime.now(timezone.utc)
            session.add(parked)
            session.commit()

    # ── helpers ──────────────────────────────────────────────────────

    def register_project(self, project_id: str, *, key: str = "bobo-key", **extra):
        body = {"project_id": project_id, "display_name": project_id}
        body.update(extra)
        with self.make_client() as client:
            return client.post(
                "/api/projects", headers={"X-API-Key": key}, json=body
            )

    def sync(self, project_id: str, agents: list[dict], *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/sync",
                headers={"X-API-Key": key},
                json={"agents": agents},
            )

    def register_runner(
        self,
        runner_id: str = RUNNER_ID,
        *,
        runtime: str = RUNNER_RUNTIME,
        adapter_status: str = "adapted",
        key: str = "bobo-key",
    ):
        with self.make_client() as client:
            return client.post(
                "/api/runners",
                headers={"X-API-Key": key},
                json={
                    "runner_id": runner_id,
                    "runtime": runtime,
                    "display_name": "DeepSeek Harness (CLI)",
                    "adapter_status": adapter_status,
                },
            )

    def patch_runner(self, runner_id: str, body, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.patch(
                f"/api/runners/{runner_id}", headers={"X-API-Key": key}, json=body
            )

    def put_binding(
        self,
        project_id: str,
        member_id: str,
        binding=None,
        *,
        key: str = "bobo-key",
        raw_body=None,
    ):
        body = raw_body if raw_body is not None else {"binding": binding}
        with self.make_client() as client:
            return client.put(
                f"/api/projects/{project_id}/agents/{encode(member_id)}/binding",
                headers={"X-API-Key": key},
                json=body,
            )

    def get_binding(self, project_id: str, member_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/agents/{encode(member_id)}/binding",
                headers={"X-API-Key": key},
            )

    def get_agents(self, project_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/agents", headers={"X-API-Key": key}
            )

    def delete_project(self, project_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.delete(
                f"/api/projects/{project_id}", headers={"X-API-Key": key}
            )

    def agent_by_id(self, project_id: str, member_id: str, *, key: str = "bobo-key"):
        payload = self.get_agents(project_id, key=key).json()
        return next(entry for entry in payload if entry["member_id"] == member_id)

    def binding_rows(self, project_id: str) -> list[ProjectRoleBinding]:
        with self.session() as session:
            return list(
                session.exec(
                    select(ProjectRoleBinding).where(
                        ProjectRoleBinding.project_id == project_id
                    )
                ).all()
            )

    def binding_payload(self, **overrides) -> dict:
        payload = {
            "runner_id": RUNNER_ID,
            "model_source": "builtin",
            "provider_id": "managed:deepseek",
            "connection_ref": CONNECTION_REF,
            "model_id": MODEL_ID,
            "model_alias": "dsh/deepseek-flash",
            "model_display_name": "DeepSeek Flash",
        }
        payload.update(overrides)
        return payload

    def seed_binding_row(self, project_id: str, member_id: str, **overrides):
        """直接落一行绑定（模拟旧库/手工行），用于构造 API 写不出的边界数据。"""
        values = {
            "project_id": project_id,
            "member_id": member_id,
            "runner_id": RUNNER_ID,
            "model_source": "builtin",
            "provider_id": "managed:deepseek",
            "connection_ref": CONNECTION_REF,
            "model_id": MODEL_ID,
            "model_alias": None,
            "model_display_name": None,
            "updated_by": "human:bobo",
            "updated_at": datetime.now(timezone.utc),
        }
        values.update(overrides)
        with self.session() as session:
            session.add(ProjectRoleBinding(**values))
            session.commit()

    def facts(self, project_id: str, member_id: str) -> dict:
        with self.session() as session:
            return read_role_binding_facts(
                session, project_id=project_id, member_id=member_id
            )

    def capture_statements(self):
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", _capture)
        return statements, _capture


# ════════════════════════════════════════════════════════════════════
# A1：老形态库迁移
# ════════════════════════════════════════════════════════════════════


class RoleBindingMigrationTests(unittest.TestCase):
    """老库只加新表与幂等索引；重复 init_db() 不重建、不覆盖、不回填虚构数据。"""

    def setUp(self):
        super().setUp()
        tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self._tmpdir = Path(tempfile.mkdtemp(prefix="talk-legacy-b1a-", dir=tmp_root))
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
        """写一个 B1a 之前形态的库：只有老 projects 表（没有本片之前多批新增列）。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE projects (
                    project_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    project_root_path TEXT,
                    maintainer_member_id TEXT NOT NULL,
                    created_at TIMESTAMP,
                    last_seen_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, display_name, description, project_root_path,
                    maintainer_member_id, created_at, last_seen_at
                ) VALUES (
                    'prj_legacy', 'Legacy Project', '升级前就存在的项目',
                    'D:/legacy/root', 'human:bobo',
                    '2026-01-01 00:00:00', '2026-01-02 00:00:00'
                )
                """
            )
            conn.commit()

    def _tables(self) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[0]
                for row in conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

    def _indexes(self) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[0]
                for row in conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }

    def test_legacy_database_upgrades_and_repeats_idempotently(self):
        self.assertNotIn("runner_registry", self._tables())
        self.assertNotIn("project_role_bindings", self._tables())

        db.init_db()
        self.assertIn("runner_registry", self._tables())
        self.assertIn("project_role_bindings", self._tables())
        indexes = self._indexes()
        self.assertIn("ix_runner_registry_runtime", indexes)
        self.assertIn("ix_project_role_bindings_project_id", indexes)
        self.assertIn("ix_project_role_bindings_runner_id", indexes)

        # 回填保护：新表必须是空的，不给旧项目/旧角色造默认运行器或模型。
        with Session(self.engine) as session:
            self.assertEqual(list(session.exec(select(RunnerRegistry)).all()), [])
            self.assertEqual(list(session.exec(select(ProjectRoleBinding)).all()), [])
            legacy = session.get(Project, "prj_legacy")
            self.assertEqual(legacy.display_name, "Legacy Project")
            self.assertIsNone(legacy.development_requirements)

        # 重复初始化必须幂等：既有的登记行不被覆盖/删除。
        with Session(self.engine) as session:
            session.add(
                RunnerRegistry(
                    runner_id=RUNNER_ID,
                    runtime=RUNNER_RUNTIME,
                    display_name="Kept",
                    adapter_status="adapted",
                    adapter_note=None,
                    capabilities=["prompt-argv"],
                    created_by="human:bobo",
                )
            )
            session.commit()
        db.init_db()
        db.init_db()
        with Session(self.engine) as session:
            rows = list(session.exec(select(RunnerRegistry)).all())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].display_name, "Kept")
            self.assertEqual(rows[0].capabilities, ["prompt-argv"])
            self.assertEqual(len(session.exec(select(Project)).all()), 1)


# ════════════════════════════════════════════════════════════════════
# A5–A18：绑定 API
# ════════════════════════════════════════════════════════════════════


class RoleBindingApiTests(BindingApiTestCase):
    def test_bound_role_exposes_full_binding_and_state(self):
        self.register_project("prj_b1a")
        self.sync(
            "prj_b1a",
            [
                {
                    "member_id": "agent:worker",
                    "business_role": "dev",
                    "decision_tier": "execution",
                }
            ],
        )
        self.register_runner()

        response = self.put_binding("prj_b1a", "agent:worker", self.binding_payload())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["project_id"], "prj_b1a")
        self.assertEqual(body["member_id"], "agent:worker")
        self.assertEqual(body["binding_state"], ROLE_BINDING_BOUND)
        binding = body["binding"]
        self.assertEqual(binding["runner_id"], RUNNER_ID)
        self.assertEqual(binding["runtime"], RUNNER_RUNTIME)
        self.assertEqual(binding["runner_display_name"], "DeepSeek Harness (CLI)")
        self.assertEqual(binding["runner_status"], "adapted")
        self.assertEqual(binding["model_source"], "builtin")
        self.assertEqual(binding["provider_id"], "managed:deepseek")
        self.assertEqual(binding["connection_ref"], CONNECTION_REF)
        self.assertEqual(binding["model_id"], MODEL_ID)
        self.assertEqual(binding["model_alias"], "dsh/deepseek-flash")
        self.assertEqual(binding["model_display_name"], "DeepSeek Flash")
        self.assertEqual(binding["updated_by"], "human:bobo")
        self.assertIsNotNone(binding["updated_at"])
        expected = fingerprint_of()
        self.assertEqual(binding["binding_fingerprint"], expected)

        entry = self.agent_by_id("prj_b1a", "agent:worker")
        self.assertEqual(entry["binding_state"], ROLE_BINDING_BOUND)
        self.assertEqual(entry["binding"]["binding_fingerprint"], expected)
        # 绑定附加字段不改变既有维度。
        self.assertEqual(entry["business_role"], "dev")
        self.assertEqual(entry["decision_tier"], "execution")

        single = self.get_binding("prj_b1a", "agent:worker").json()
        self.assertEqual(single["binding"], body["binding"])
        self.assertEqual(single["binding_state"], ROLE_BINDING_BOUND)

    def test_custom_api_source_and_alias_are_stored_verbatim(self):
        self.register_project("prj_custom")
        self.sync("prj_custom", [{"member_id": "agent:worker"}])
        self.register_runner()
        payload = self.binding_payload(
            model_source="custom_api",
            provider_id="user:moonshot-openai",
            connection_ref="user-moonshot-conn-2",
            model_id="kimi-for-coding",
            model_alias="kimi-code/kimi-for-coding",
            model_display_name="用户 API · K2.8",
        )
        response = self.put_binding("prj_custom", "agent:worker", payload)
        self.assertEqual(response.status_code, 200)
        binding = response.json()["binding"]
        self.assertEqual(binding["model_source"], "custom_api")
        self.assertEqual(binding["model_alias"], "kimi-code/kimi-for-coding")
        self.assertEqual(binding["model_display_name"], "用户 API · K2.8")
        self.assertEqual(
            binding["binding_fingerprint"],
            fingerprint_of(
                model_source="custom_api",
                provider_id="user:moonshot-openai",
                connection_ref="user-moonshot-conn-2",
                model_id="kimi-for-coding",
            ),
        )

    def test_roster_without_binding_is_unconfigured_not_faked(self):
        self.register_project("prj_unconf")
        self.sync("prj_unconf", [{"member_id": "agent:worker"}])
        entry = self.agent_by_id("prj_unconf", "agent:worker")
        self.assertIsNone(entry["binding"])
        self.assertEqual(entry["binding_state"], ROLE_BINDING_UNCONFIGURED)

        single = self.get_binding("prj_unconf", "agent:worker")
        self.assertEqual(single.status_code, 200)
        self.assertIsNone(single.json()["binding"])
        self.assertEqual(single.json()["binding_state"], ROLE_BINDING_UNCONFIGURED)
        self.assertEqual(self.binding_rows("prj_unconf"), [])

    def test_registration_alone_does_not_join_project_or_create_binding(self):
        self.register_project("prj_reg_only")
        self.sync("prj_reg_only", [{"member_id": "agent:worker"}])
        self.register_runner()
        self.assertEqual(self.binding_rows("prj_reg_only"), [])
        entry = self.agent_by_id("prj_reg_only", "agent:worker")
        self.assertIsNone(entry["binding"])
        self.assertEqual(entry["binding_state"], ROLE_BINDING_UNCONFIGURED)

    # ── A6/A7/A8：行身份 vs 内容指纹 ─────────────────────────────────

    def test_two_roles_keep_two_rows_with_same_model_id(self):
        self.register_project("prj_rows")
        self.sync(
            "prj_rows",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        self.register_runner()
        first = self.put_binding(
            "prj_rows",
            "agent:worker",
            self.binding_payload(connection_ref="conn-a"),
        )
        second = self.put_binding(
            "prj_rows",
            "agent:other",
            self.binding_payload(connection_ref="conn-b"),
        )
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        first_fingerprint = first.json()["binding"]["binding_fingerprint"]
        second_fingerprint = second.json()["binding"]["binding_fingerprint"]
        self.assertNotEqual(first_fingerprint, second_fingerprint)
        self.assertEqual(len(self.binding_rows("prj_rows")), 2)
        self.assertEqual(
            {
                self.agent_by_id("prj_rows", member)["binding_state"]
                for member in ("agent:worker", "agent:other")
            },
            {ROLE_BINDING_BOUND},
        )

    def test_same_role_put_is_one_row_new_version(self):
        self.register_project("prj_version")
        self.sync("prj_version", [{"member_id": "agent:worker"}])
        self.register_runner()
        first = self.put_binding("prj_version", "agent:worker", self.binding_payload())
        second = self.put_binding(
            "prj_version",
            "agent:worker",
            self.binding_payload(
                model_source="custom_api",
                provider_id="user:user-1",
                connection_ref="conn-2",
            ),
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(
            first.json()["binding"]["binding_fingerprint"],
            second.json()["binding"]["binding_fingerprint"],
        )
        self.assertEqual(second.json()["binding"]["connection_ref"], "conn-2")
        self.assertGreaterEqual(
            second.json()["binding"]["updated_at"],
            first.json()["binding"]["updated_at"],
        )
        rows = self.binding_rows("prj_version")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].member_id, "agent:worker")
        self.assertEqual(rows[0].connection_ref, "conn-2")

    def test_identical_content_for_two_roles_shares_fingerprint_but_not_row(self):
        self.register_project("prj_same")
        self.sync(
            "prj_same",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        self.register_runner()
        for member_id in ("agent:worker", "agent:other"):
            self.assertEqual(
                self.put_binding(
                    "prj_same", member_id, self.binding_payload()
                ).status_code,
                200,
            )
        rows = self.binding_rows("prj_same")
        self.assertEqual({row.member_id for row in rows}, {"agent:worker", "agent:other"})
        first = self.get_binding("prj_same", "agent:worker").json()
        second = self.get_binding("prj_same", "agent:other").json()
        self.assertEqual(
            first["binding"]["binding_fingerprint"],
            second["binding"]["binding_fingerprint"],
        )
        self.assertNotEqual(first["member_id"], second["member_id"])

    # ── A9：校验 ─────────────────────────────────────────────────────

    def test_invalid_binding_payloads_are_rejected(self):
        self.register_project("prj_invalid")
        self.sync("prj_invalid", [{"member_id": "agent:worker"}])
        self.register_runner()

        bad_bindings = {
            "missing runner_id": self.binding_payload(runner_id=None),
            "missing model_source": self.binding_payload(model_source=None),
            "blank provider_id": self.binding_payload(provider_id="   "),
            "blank connection_ref": self.binding_payload(connection_ref=""),
            "blank model_id": self.binding_payload(model_id="\t"),
            "provider_id too long": self.binding_payload(provider_id="p" * 129),
            "connection_ref too long": self.binding_payload(connection_ref="c" * 129),
            "model_id too long": self.binding_payload(model_id="m" * 129),
            "model_alias too long": self.binding_payload(model_alias="a" * 129),
            "illegal provider char": self.binding_payload(provider_id="managed;rm -rf"),
            "illegal connection backtick": self.binding_payload(connection_ref="conn`x"),
            "illegal model paren": self.binding_payload(model_id="model(x)"),
            "suspicious sk- prefix": self.binding_payload(provider_id="sk-abcdef123456"),
            "suspicious bearer": self.binding_payload(connection_ref="Bearer abcdef"),
            "suspicious url credential": self.binding_payload(
                connection_ref="https://user:pass@host"
            ),
            "suspicious long base64": self.binding_payload(model_id="A" * 48),
            "bad model_source enum": self.binding_payload(model_source="openai"),
            "model_display_name too long": self.binding_payload(
                model_display_name="名" * 65
            ),
            "unknown binding field": self.binding_payload(binding_v2={}),
            "bad runner_id slug": self.binding_payload(runner_id="Runner:DSH"),
        }
        for name, binding in bad_bindings.items():
            with self.subTest(name=name):
                response = self.put_binding("prj_invalid", "agent:worker", binding)
                self.assertEqual(response.status_code, 422, response.text)

        self.assertEqual(
            self.put_binding("prj_invalid", "agent:worker", raw_body={}).status_code,
            422,
        )
        self.assertEqual(
            self.put_binding(
                "prj_invalid", "agent:worker", None, raw_body={"binding": "x"}
            ).status_code,
            422,
        )
        self.assertEqual(self.binding_rows("prj_invalid"), [])

    def test_optional_binding_fields_normalize_blank_to_null(self):
        self.register_project("prj_optional")
        self.sync("prj_optional", [{"member_id": "agent:worker"}])
        self.register_runner()
        response = self.put_binding(
            "prj_optional",
            "agent:worker",
            self.binding_payload(model_alias="   ", model_display_name="  "),
        )
        self.assertEqual(response.status_code, 200)
        binding = response.json()["binding"]
        self.assertIsNone(binding["model_alias"])
        self.assertIsNone(binding["model_display_name"])

    # ── A10：runner 不存在 / retired ─────────────────────────────────

    def test_unregistered_or_retired_runner_is_rejected(self):
        self.register_project("prj_runner")
        self.sync("prj_runner", [{"member_id": "agent:worker"}])
        missing = self.put_binding(
            "prj_runner",
            "agent:worker",
            self.binding_payload(runner_id="runner:gone"),
        )
        self.assertEqual(missing.status_code, 422)

        self.register_runner("runner:old", adapter_status="retired")
        retired = self.put_binding(
            "prj_runner",
            "agent:worker",
            self.binding_payload(runner_id="runner:old"),
        )
        self.assertEqual(retired.status_code, 422)
        self.assertEqual(self.binding_rows("prj_runner"), [])

    # ── A11：目标与解除绑定 ──────────────────────────────────────────

    def test_non_roster_targets_are_404(self):
        self.register_project("prj_target")
        self.sync(
            "prj_target",
            [{"member_id": "agent:worker"}, {"member_id": "human:henry"}],
        )
        self.register_runner()

        cases = {
            "unregistered member": "agent:ghost",
            "disabled member": "agent:parked",
            "non-agent member": "human:henry",
            "registered but not in roster": "agent:other",
        }
        for name, member_id in cases.items():
            with self.subTest(name=name):
                response = self.put_binding(
                    "prj_target", member_id, self.binding_payload()
                )
                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.binding_rows("prj_target"), [])

    def test_clear_binding_is_idempotent(self):
        self.register_project("prj_clear")
        self.sync("prj_clear", [{"member_id": "agent:worker"}])
        self.register_runner()
        self.put_binding("prj_clear", "agent:worker", self.binding_payload())

        cleared = self.put_binding("prj_clear", "agent:worker", None)
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()["binding"])
        self.assertEqual(cleared.json()["binding_state"], ROLE_BINDING_UNCONFIGURED)
        self.assertEqual(self.binding_rows("prj_clear"), [])

        # 无行、离册、禁用、未注册都幂等 200。
        repeat = self.put_binding("prj_clear", "agent:worker", None)
        self.assertEqual(repeat.status_code, 200)
        off_roster = self.put_binding("prj_clear", "agent:other", None)
        self.assertEqual(off_roster.status_code, 200)
        self.assertEqual(off_roster.json()["binding_state"], ROLE_BINDING_NOT_IN_ROSTER)
        disabled = self.put_binding("prj_clear", "agent:parked", None)
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["binding_state"], ROLE_BINDING_MEMBER_DISABLED)
        unknown = self.put_binding("prj_clear", "agent:ghost", None)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.json()["binding_state"], ROLE_BINDING_MEMBER_MISSING)

    def test_no_actual_match_or_receipt_fields_are_exposed(self):
        """本片只记录配置：不输出任何 B2 实际对照字段，也不新增读取回执字段。"""
        self.register_project("prj_scope")
        self.sync("prj_scope", [{"member_id": "agent:worker"}])
        self.register_runner()
        payloads = [
            self.get_agents("prj_scope").json(),
            self.get_binding("prj_scope", "agent:worker").json(),
            self.put_binding(
                "prj_scope", "agent:worker", self.binding_payload()
            ).json(),
        ]
        text = json.dumps(payloads, ensure_ascii=False)
        self.assertNotIn("binding_match", text)
        self.assertNotIn("reported_", text)
        self.assertNotIn("read_receipt", text)

    def test_agent_cannot_write_binding(self):
        self.register_project("prj_perm")
        self.sync("prj_perm", [{"member_id": "agent:worker"}])
        self.register_runner()
        self.assertEqual(
            self.put_binding(
                "prj_perm", "agent:worker", self.binding_payload(), key="worker-key"
            ).status_code,
            403,
        )
        self.assertEqual(self.binding_rows("prj_perm"), [])
        self.assertEqual(
            self.get_binding("prj_perm", "agent:worker", key="worker-key").status_code,
            200,
        )

    def test_unknown_project_is_404(self):
        self.assertEqual(
            self.get_binding("prj_ghost", "agent:worker").status_code, 404
        )
        self.assertEqual(
            self.put_binding(
                "prj_ghost", "agent:worker", self.binding_payload()
            ).status_code,
            404,
        )
        self.assertEqual(
            self.put_binding("prj_ghost", "agent:worker", None).status_code, 404
        )

    # ── A12/A13：离册回册与优先级 ────────────────────────────────────

    def test_offboard_keeps_binding_and_rejoin_restores_bound(self):
        self.register_project("prj_lifecycle")
        self.sync(
            "prj_lifecycle",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        self.register_runner()
        self.put_binding("prj_lifecycle", "agent:worker", self.binding_payload())

        self.sync("prj_lifecycle", [{"member_id": "agent:other"}])
        offboard = self.get_binding("prj_lifecycle", "agent:worker").json()
        self.assertEqual(offboard["binding_state"], ROLE_BINDING_NOT_IN_ROSTER)
        self.assertEqual(offboard["binding"]["runner_id"], RUNNER_ID)
        self.assertEqual(offboard["binding"]["model_id"], MODEL_ID)
        self.assertEqual(
            offboard["binding"]["binding_fingerprint"], fingerprint_of()
        )
        self.assertEqual(len(self.binding_rows("prj_lifecycle")), 1)
        # 离册成员不再出现在名册列表里（GET /agents 只列当前名册），
        # 但单角色读取仍返回保留行与 not_in_roster 事实。
        self.assertNotIn(
            "agent:worker",
            [entry["member_id"] for entry in self.get_agents("prj_lifecycle").json()],
        )

        self.sync(
            "prj_lifecycle",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        rejoined = self.get_binding("prj_lifecycle", "agent:worker").json()
        self.assertEqual(rejoined["binding_state"], ROLE_BINDING_BOUND)
        self.assertEqual(len(self.binding_rows("prj_lifecycle")), 1)

    def test_state_priority_identity_before_runner_and_roster(self):
        self.register_project("prj_priority")
        self.sync(
            "prj_priority",
            [{"member_id": "agent:worker"}, {"member_id": "agent:parked"}],
        )
        self.register_runner()
        self.put_binding("prj_priority", "agent:worker", self.binding_payload())

        # 离册 + runner retired → not_in_roster（序 3 优先于序 8），指纹仍给出。
        self.sync("prj_priority", [{"member_id": "agent:parked"}])
        self.patch_runner(RUNNER_ID, {"adapter_status": "retired"})
        facts = self.facts("prj_priority", "agent:worker")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_NOT_IN_ROSTER)
        self.assertEqual(facts["runner_status"], "retired")
        self.assertIsNotNone(binding_fingerprint(facts))

        # 禁用 + 离册 → member_disabled（序 2 优先于序 3）。
        self.sync("prj_priority", [{"member_id": "agent:worker"}])
        facts = self.facts("prj_priority", "agent:parked")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_MEMBER_DISABLED)

        # 无行 + 离册 → not_in_roster（序 3 优先于序 5）：agent:other 已注册但不在名册。
        facts = self.facts("prj_priority", "agent:other")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_NOT_IN_ROSTER)
        self.assertEqual(facts["binding_exists"], 0)

    # ── A14/A15/A16：不影响其它维度 / sync / 项目删除 ────────────────

    def test_binding_write_does_not_change_other_dimensions(self):
        self.register_project("prj_dims")
        self.sync(
            "prj_dims",
            [
                {
                    "member_id": "agent:worker",
                    "business_role": "dev",
                    "decision_tier": "execution",
                }
            ],
        )
        self.register_runner()
        with self.make_client() as client:
            assigned = client.patch(
                "/api/projects/prj_dims/controller-assignment",
                headers={"X-API-Key": "bobo-key"},
                json={"member_id": "agent:worker", "expected_version": 0},
            )
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(assigned.json()["controller_member_id"], "agent:worker")
        self.assertEqual(assigned.json()["controller_assignment_status"], "assigned")

        self.put_binding("prj_dims", "agent:worker", self.binding_payload())

        with self.make_client() as client:
            project = client.get(
                "/api/projects/prj_dims", headers={"X-API-Key": "bobo-key"}
            ).json()
        self.assertEqual(project["controller_member_id"], "agent:worker")
        self.assertEqual(project["controller_assignment_status"], "assigned")
        self.assertEqual(project["controller_assignment_version"], 1)
        entry = self.agent_by_id("prj_dims", "agent:worker")
        self.assertEqual(entry["business_role"], "dev")
        self.assertEqual(entry["decision_tier"], "execution")
        self.assertEqual(entry["binding_state"], ROLE_BINDING_BOUND)

    def test_sync_full_replace_keeps_binding_and_sync_payload_agrees(self):
        self.register_project("prj_sync")
        self.sync(
            "prj_sync",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        self.register_runner()
        self.put_binding("prj_sync", "agent:worker", self.binding_payload())

        synced = self.sync(
            "prj_sync",
            [
                {"member_id": "agent:worker", "business_role": "lead"},
                {"member_id": "agent:other", "business_role": "tester"},
            ],
        )
        self.assertEqual(synced.status_code, 200)
        by_member = {entry["member_id"]: entry for entry in synced.json()}
        self.assertEqual(by_member["agent:worker"]["binding_state"], ROLE_BINDING_BOUND)
        self.assertEqual(by_member["agent:other"]["binding_state"], ROLE_BINDING_UNCONFIGURED)
        for member_id, entry in by_member.items():
            single = self.get_binding("prj_sync", member_id).json()
            self.assertEqual(entry["binding_state"], single["binding_state"])
            self.assertEqual(entry["binding"], single["binding"])
        self.assertEqual(len(self.binding_rows("prj_sync")), 1)

    def test_project_delete_cleans_bindings_but_not_roster_orphans(self):
        self.register_project("prj_delete")
        self.sync(
            "prj_delete",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        self.register_runner()
        self.put_binding("prj_delete", "agent:worker", self.binding_payload())
        self.put_binding("prj_delete", "agent:other", self.binding_payload())

        self.assertEqual(self.delete_project("prj_delete").status_code, 204)
        self.assertEqual(self.binding_rows("prj_delete"), [])
        with self.session() as session:
            self.assertIsNone(session.get(Project, "prj_delete"))
            orphans = list(
                session.exec(
                    select(ProjectAgent).where(
                        ProjectAgent.project_id == "prj_delete"
                    )
                ).all()
            )
        # 既有名册孤儿行边界不扩改：不追删。
        self.assertEqual({row.member_id for row in orphans}, {"agent:worker", "agent:other"})

    # ── A17：upsert 并发收敛 ─────────────────────────────────────────

    def test_concurrent_upsert_converges_without_conflict(self):
        self.register_project("prj_conc")
        self.sync("prj_conc", [{"member_id": "agent:worker"}])
        self.register_runner()

        engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        self.addCleanup(engine.dispose)
        barrier = threading.Barrier(2)
        commit_order: list[str] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def writer(tag: str, connection_ref: str) -> None:
            try:
                with Session(engine) as session:
                    barrier.wait(timeout=20)
                    values = {
                        "project_id": "prj_conc",
                        "member_id": "agent:worker",
                        "runner_id": RUNNER_ID,
                        "model_source": "builtin",
                        "provider_id": "managed:deepseek",
                        "connection_ref": connection_ref,
                        "model_id": MODEL_ID,
                        "model_alias": None,
                        "model_display_name": None,
                        "updated_by": "human:bobo",
                        "updated_at": datetime.now(timezone.utc),
                    }
                    session.execute(
                        sqlite_insert(ProjectRoleBinding)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=["project_id", "member_id"],
                            set_={
                                key: value
                                for key, value in values.items()
                                if key not in {"project_id", "member_id"}
                            },
                        )
                    )
                    session.commit()
                with lock:
                    commit_order.append(tag)
            except BaseException as exc:  # noqa: BLE001 - 记录真实异常用于断言
                with lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=("a", "conn-a")),
            threading.Thread(target=writer, args=("b", "conn-b")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [], [repr(error) for error in errors])
        self.assertEqual(sorted(commit_order), ["a", "b"])
        rows = self.binding_rows("prj_conc")
        self.assertEqual(len(rows), 1)
        expected_connection = "conn-a" if commit_order[-1] == "a" else "conn-b"
        self.assertEqual(rows[0].connection_ref, expected_connection)

    # ── A18：载荷计数冒烟（B3 归 bridge/MCP，本片不越界改） ────────────

    def test_agents_payload_has_binding_fields_without_duplicating_requirements(self):
        self.register_project("prj_payload")
        with self.make_client() as client:
            written = client.patch(
                "/api/projects/prj_payload",
                headers={"X-API-Key": "bobo-key"},
                json={"development_requirements": "1.开发要求快照文本"},
            )
        self.assertEqual(written.status_code, 200)
        self.sync(
            "prj_payload",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        payload = json.dumps(self.get_agents("prj_payload").json(), ensure_ascii=False)
        self.assertEqual(payload.count("development_requirements"), 0)
        self.assertEqual(payload.count('"binding_state"'), 2)
        self.assertEqual(payload.count('"binding"'), 2)


# ════════════════════════════════════════════════════════════════════
# R1：最终事实 project_exists 决定项目 404（确定性交错回归）
# ════════════════════════════════════════════════════════════════════


class ProjectFinalFactsTests(BindingApiTestCase):
    """前置 ORM 读取通过后、事实 SQL 之前由另一连接删除项目，仍须 404。

    交错点是确定性的：把 ``server.routes.projects`` 里实际使用的读取助手替换成
    “先在独立连接删除该项目、再委托原助手”的包装函数，不依赖时序运气。
    """

    def _delete_project_via_other_connection(self, project_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM project_role_bindings WHERE project_id = :p"),
                {"p": project_id},
            )
            conn.execute(
                text("DELETE FROM project_agents WHERE project_id = :p"),
                {"p": project_id},
            )
            conn.execute(
                text("DELETE FROM projects WHERE project_id = :p"), {"p": project_id}
            )

    def test_project_deleted_before_single_facts_maps_to_404(self):
        self.register_project("prj_race_single")
        self.sync("prj_race_single", [{"member_id": "agent:worker"}])
        self.register_runner()
        self.put_binding("prj_race_single", "agent:worker", self.binding_payload())
        self.assertEqual(
            self.get_binding("prj_race_single", "agent:worker").status_code, 200
        )

        real_read = projects_route.read_role_binding_facts

        def delete_then_read(session, **kwargs):
            self._delete_project_via_other_connection(kwargs["project_id"])
            return real_read(session, **kwargs)

        with patch.object(
            projects_route, "read_role_binding_facts", side_effect=delete_then_read
        ):
            racing = self.get_binding("prj_race_single", "agent:worker")
        self.assertEqual(racing.status_code, 404, racing.text)
        self.assertNotEqual(racing.status_code, 200)
        with self.session() as session:
            self.assertIsNone(session.get(Project, "prj_race_single"))

    def test_project_deleted_before_put_readback_maps_to_404(self):
        """PUT 读回同样以最终事实为准，不返回 200/``binding_state = null``。"""
        self.register_project("prj_race_put")
        self.sync("prj_race_put", [{"member_id": "agent:worker"}])
        self.register_runner()

        real_read = projects_route.read_role_binding_facts

        def delete_then_read(session, **kwargs):
            self._delete_project_via_other_connection(kwargs["project_id"])
            return real_read(session, **kwargs)

        with patch.object(
            projects_route, "read_role_binding_facts", side_effect=delete_then_read
        ):
            upsert = self.put_binding(
                "prj_race_put", "agent:worker", self.binding_payload()
            )
        self.assertEqual(upsert.status_code, 404, upsert.text)

        self.register_project("prj_race_put_clear")
        self.sync("prj_race_put_clear", [{"member_id": "agent:worker"}])
        with patch.object(
            projects_route, "read_role_binding_facts", side_effect=delete_then_read
        ):
            cleared = self.put_binding("prj_race_put_clear", "agent:worker", None)
        self.assertEqual(cleared.status_code, 404, cleared.text)

    def test_project_deleted_before_batch_facts_maps_to_404(self):
        self.register_project("prj_race_batch")
        self.sync(
            "prj_race_batch",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        self.register_runner()
        self.put_binding("prj_race_batch", "agent:worker", self.binding_payload())

        real_batch = projects_route.read_role_binding_facts_batch

        def delete_then_batch(session, **kwargs):
            self._delete_project_via_other_connection(kwargs["project_id"])
            return real_batch(session, **kwargs)

        with patch.object(
            projects_route,
            "read_role_binding_facts_batch",
            side_effect=delete_then_batch,
        ):
            racing = self.get_agents("prj_race_batch")
        self.assertEqual(racing.status_code, 404, racing.text)
        self.assertNotEqual(racing.status_code, 200)

    def test_sync_response_also_uses_final_project_facts(self):
        """POST /sync 同样是批量角色响应：提交后项目被删也 404，不返回 null 状态。"""
        self.register_project("prj_race_sync")
        self.sync("prj_race_sync", [{"member_id": "agent:worker"}])
        real_batch = projects_route.read_role_binding_facts_batch

        def delete_then_batch(session, **kwargs):
            self._delete_project_via_other_connection(kwargs["project_id"])
            return real_batch(session, **kwargs)

        with patch.object(
            projects_route,
            "read_role_binding_facts_batch",
            side_effect=delete_then_batch,
        ):
            racing = self.sync(
                "prj_race_sync",
                [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
            )
        self.assertEqual(racing.status_code, 404, racing.text)

    def test_successful_project_responses_never_expose_null_state(self):
        """项目仍存在时，单角色与批量响应的 ``binding_state`` 必须具体，不能为 null。"""
        self.register_project("prj_states")
        self.sync(
            "prj_states",
            [{"member_id": "agent:worker"}, {"member_id": "agent:extra"}],
        )
        listed = self.get_agents("prj_states")
        self.assertEqual(listed.status_code, 200)
        by_member = {entry["member_id"]: entry for entry in listed.json()}
        for member_id in ("agent:worker", "agent:extra"):
            self.assertEqual(
                by_member[member_id]["binding_state"], ROLE_BINDING_UNCONFIGURED
            )
            single = self.get_binding("prj_states", member_id)
            self.assertEqual(single.status_code, 200)
            self.assertEqual(
                single.json()["binding_state"], ROLE_BINDING_UNCONFIGURED
            )
            self.assertIsNotNone(single.json()["binding_state"])

        # 成员离册但项目存在：仍是具体状态（not_in_roster），不是 null。
        self.sync("prj_states", [{"member_id": "agent:other"}])
        offboard = self.get_binding("prj_states", "agent:worker")
        self.assertEqual(offboard.status_code, 200)
        self.assertEqual(
            offboard.json()["binding_state"], ROLE_BINDING_NOT_IN_ROSTER
        )


# ════════════════════════════════════════════════════════════════════
# A19–A21：单语句事实助手
# ════════════════════════════════════════════════════════════════════


class RoleBindingFactsTests(BindingApiTestCase):
    # 覆盖 enabled agent / disabled agent / 非 agent / 未注册成员，全部真实入册，
    # 用于无绑定四例、partial 与 runner_missing 的边界构造。
    ROSTER = [
        {"member_id": "agent:worker"},
        {"member_id": "agent:extra"},
        {"member_id": "agent:extra2"},
        {"member_id": "agent:extra3"},
        {"member_id": "agent:parked"},
        {"member_id": "human:henry"},
        {"member_id": "agent:ghost"},
    ]

    def setUp(self):
        super().setUp()
        self.register_project("prj_facts")
        self.sync("prj_facts", list(self.ROSTER))

    def test_contract_sql_is_verbatim_single_statement(self):
        digest = hashlib.sha256(BINDING_FACTS_SQL.encode("utf-8")).hexdigest()
        self.assertEqual(digest, EXPECTED_SQL_SHA)
        self.assertEqual(BINDING_FACTS_SQL.count(";"), 1)
        self.assertTrue(BINDING_FACTS_SQL.rstrip().endswith(";"))
        self.assertEqual(len(BINDING_FACTS_COLUMNS), 27)
        self.assertEqual(len(set(BINDING_FACTS_COLUMNS)), 27)
        # 27 个别名都要真的出现在 SQL 里。
        for column in BINDING_FACTS_COLUMNS:
            self.assertIn(column, BINDING_FACTS_SQL)

    def test_no_binding_cases_still_return_exactly_one_row(self):
        cases = {
            "in roster without binding": (
                "agent:worker",
                {"member_exists": 1, "in_roster": 1, "member_kind": "agent"},
                ROLE_BINDING_UNCONFIGURED,
            ),
            "disabled without binding": (
                "agent:parked",
                {"member_exists": 1, "in_roster": 1, "member_kind": "agent"},
                ROLE_BINDING_MEMBER_DISABLED,
            ),
            "unregistered without binding": (
                "agent:ghost",
                {"member_exists": 0, "in_roster": 1, "member_kind": None},
                ROLE_BINDING_MEMBER_MISSING,
            ),
            "non-agent without binding": (
                "human:henry",
                {"member_exists": 1, "in_roster": 1, "member_kind": "human"},
                ROLE_BINDING_NOT_AGENT,
            ),
        }
        for name, (member_id, expected, state) in cases.items():
            with self.subTest(name=name):
                facts = self.facts("prj_facts", member_id)
                # `.one()` 已经强制“恰好 1 行”，这里再核验列集合与关键事实。
                self.assertEqual(len(facts), 27)
                self.assertEqual(set(facts), set(BINDING_FACTS_COLUMNS))
                self.assertEqual(facts["project_exists"], 1)
                self.assertEqual(facts["binding_exists"], 0)
                self.assertEqual(facts["requested_member_id"], member_id)
                for key, value in expected.items():
                    self.assertEqual(facts[key], value, key)
                self.assertEqual(resolve_role_binding_state(facts), state)

    def test_offboard_with_and_without_binding_and_missing_project(self):
        self.register_runner()
        self.put_binding("prj_facts", "agent:worker", self.binding_payload())

        # 离册 + 有绑定：行值照存，状态 not_in_roster。
        self.sync("prj_facts", [{"member_id": "agent:other"}])
        facts = self.facts("prj_facts", "agent:worker")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_NOT_IN_ROSTER)
        self.assertEqual(facts["binding_exists"], 1)
        self.assertEqual(facts["model_id"], MODEL_ID)
        self.assertEqual(facts["model_alias"], "dsh/deepseek-flash")
        self.assertEqual(facts["runtime"], RUNNER_RUNTIME)

        # 离册 + 无绑定：仍是 not_in_roster（不是 unconfigured）。
        facts = self.facts("prj_facts", "agent:extra")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_NOT_IN_ROSTER)
        self.assertEqual(facts["member_exists"], 1)
        self.assertEqual(facts["in_roster"], 0)
        self.assertEqual(facts["binding_exists"], 0)

        # 项目不存在：只返回不存在事实，不造任何绑定状态。
        absent = self.facts("prj_missing", "agent:worker")
        self.assertEqual(absent["project_exists"], 0)
        self.assertEqual(len(absent), 27)
        self.assertIsNone(resolve_role_binding_state(absent))

    def test_bound_row_exposes_all_columns_and_fingerprint(self):
        self.register_runner()
        self.put_binding("prj_facts", "agent:worker", self.binding_payload())
        facts = self.facts("prj_facts", "agent:worker")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_BOUND)
        for column in (
            "runner_id",
            "runtime",
            "model_source",
            "provider_id",
            "connection_ref",
            "model_id",
        ):
            self.assertTrue(facts[column], column)
        self.assertEqual(facts["runner_display_name"], "DeepSeek Harness (CLI)")
        self.assertEqual(facts["runner_status"], "adapted")
        self.assertEqual(facts["updated_by"], "human:bobo")
        self.assertEqual(
            binding_fingerprint(facts), fingerprint_of()
        )

    # ── partial / runner_missing / runner_retired 的精确边界 ─────────

    def test_partial_is_triggered_only_by_stored_required_fields(self):
        self.register_runner()
        # 行缺 model_id（API 写不出来，模拟旧库/手工行）。
        self.seed_binding_row("prj_facts", "agent:worker", model_id=None)
        response = self.get_binding("prj_facts", "agent:worker").json()
        self.assertEqual(response["binding_state"], ROLE_BINDING_PARTIAL)
        self.assertEqual(response["binding"]["runner_id"], RUNNER_ID)
        self.assertEqual(response["binding"]["runtime"], RUNNER_RUNTIME)
        self.assertIsNone(response["binding"]["model_id"])
        self.assertIsNone(response["binding"]["binding_fingerprint"])

        # 行缺 runner_id → partial，runtime 也不可解析。
        self.seed_binding_row("prj_facts", "agent:extra", runner_id=None)
        response = self.get_binding("prj_facts", "agent:extra").json()
        self.assertEqual(response["binding_state"], ROLE_BINDING_PARTIAL)
        self.assertIsNone(response["binding"]["runner_id"])
        self.assertIsNone(response["binding"]["runtime"])
        self.assertIsNone(response["binding"]["binding_fingerprint"])

        # 存储 model_source 非法枚举 → 仍是 partial（存储必填项不合法）。
        self.seed_binding_row("prj_facts", "agent:extra2", model_source="openai")
        response = self.get_binding("prj_facts", "agent:extra2").json()
        self.assertEqual(response["binding_state"], ROLE_BINDING_PARTIAL)
        self.assertEqual(response["binding"]["runtime"], RUNNER_RUNTIME)
        self.assertIsNone(response["binding"]["binding_fingerprint"])

        # 身份类事实优先于 partial：非 agent 即使行内容损坏也报 not_agent。
        self.seed_binding_row("prj_facts", "human:henry", model_source="openai")
        self.assertEqual(
            self.get_binding("prj_facts", "human:henry").json()["binding_state"],
            ROLE_BINDING_NOT_AGENT,
        )

        # 可选字段损坏不触发 partial：仍是 bound，行值照存、指纹不变。
        self.seed_binding_row(
            "prj_facts",
            "agent:extra3",
            model_alias="a" * 200,
            model_display_name="名" * 200,
        )
        response = self.get_binding("prj_facts", "agent:extra3").json()
        self.assertEqual(response["binding_state"], ROLE_BINDING_BOUND)
        self.assertEqual(response["binding"]["model_alias"], "a" * 200)
        self.assertEqual(response["binding"]["model_display_name"], "名" * 200)
        self.assertEqual(
            response["binding"]["binding_fingerprint"], fingerprint_of()
        )

    def test_runner_missing_is_not_swallowed_by_partial(self):
        self.seed_binding_row("prj_facts", "agent:worker", runner_id="runner:gone")
        facts = self.facts("prj_facts", "agent:worker")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_RUNNER_MISSING)
        self.assertIsNone(facts["runtime"])
        self.assertIsNone(binding_fingerprint(facts))
        response = self.get_binding("prj_facts", "agent:worker").json()
        self.assertEqual(response["binding_state"], ROLE_BINDING_RUNNER_MISSING)
        self.assertEqual(response["binding"]["runner_id"], "runner:gone")
        self.assertIsNone(response["binding"]["runtime"])
        self.assertIsNone(response["binding"]["runner_display_name"])
        self.assertIsNone(response["binding"]["runner_status"])
        self.assertIsNone(response["binding"]["binding_fingerprint"])

        # 登记行存在但 runtime 为空（旧库边界）：同样 runner_missing。
        with self.session() as session:
            session.add(
                RunnerRegistry(
                    runner_id="runner:no-runtime",
                    runtime="",
                    display_name="No Runtime",
                    adapter_status="unverified",
                    adapter_note=None,
                    capabilities=[],
                    created_by="human:bobo",
                )
            )
            session.commit()
        self.seed_binding_row(
            "prj_facts", "agent:extra", runner_id="runner:no-runtime"
        )
        facts = self.facts("prj_facts", "agent:extra")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_RUNNER_MISSING)
        self.assertIsNone(binding_fingerprint(facts))

    def test_retired_runner_keeps_fingerprint_and_residual_window_is_honest(self):
        self.register_runner()
        self.put_binding("prj_facts", "agent:worker", self.binding_payload())
        # 写入后登记被改为 retired（合同 §4.3 记录的残余窗口）：读时如实报失效。
        self.patch_runner(RUNNER_ID, {"adapter_status": "retired"})
        facts = self.facts("prj_facts", "agent:worker")
        self.assertEqual(resolve_role_binding_state(facts), ROLE_BINDING_RUNNER_RETIRED)
        self.assertEqual(facts["runtime"], RUNNER_RUNTIME)
        self.assertEqual(binding_fingerprint(facts), fingerprint_of())
        response = self.get_binding("prj_facts", "agent:worker").json()
        self.assertEqual(response["binding_state"], ROLE_BINDING_RUNNER_RETIRED)
        self.assertEqual(response["binding"]["runner_status"], "retired")
        self.assertEqual(
            response["binding"]["binding_fingerprint"], fingerprint_of()
        )

    # ── R2/R3：派生字段规范化与整串标识校验（定向修正回归） ──────────

    def test_unparseable_runtime_nulls_all_three_derived_fields_single_and_batch(self):
        """登记 runtime 不可解析时 ``runtime``/display/status 三者都为 null（R2）。"""
        self.register_runner()
        self.put_binding("prj_facts", "agent:worker", self.binding_payload())

        def _set_registry_runtime(value: str) -> None:
            with self.session() as session:
                runner = session.get(RunnerRegistry, RUNNER_ID)
                runner.runtime = value
                session.add(runner)
                session.commit()

        for runtime in ("", "   ", RUNNER_RUNTIME + "\n"):
            with self.subTest(runtime=repr(runtime)):
                _set_registry_runtime(runtime)
                single = self.get_binding("prj_facts", "agent:worker")
                self.assertEqual(single.status_code, 200)
                body = single.json()
                self.assertEqual(body["binding_state"], ROLE_BINDING_RUNNER_MISSING)
                binding = body["binding"]
                self.assertEqual(binding["runner_id"], RUNNER_ID)
                self.assertIsNone(binding["runtime"])
                self.assertIsNone(binding["runner_display_name"])
                self.assertIsNone(binding["runner_status"])
                self.assertIsNone(binding["binding_fingerprint"])
                # 单角色与批量来自同一输出助手，布局必须一致。
                entry = self.agent_by_id("prj_facts", "agent:worker")
                self.assertEqual(entry["binding_state"], ROLE_BINDING_RUNNER_MISSING)
                self.assertEqual(entry["binding"], binding)

        # 登记行照存、不被读取改写（含 display_name / adapter_status）。
        with self.session() as session:
            stored = session.get(RunnerRegistry, RUNNER_ID)
            self.assertEqual(stored.runtime, RUNNER_RUNTIME + "\n")
            self.assertEqual(stored.display_name, "DeepSeek Harness (CLI)")
            self.assertEqual(stored.adapter_status, "adapted")

        # 登记行缺失（runner_id 查不到）：同样三者 null（旧用例只断言了 runtime）。
        self.seed_binding_row("prj_facts", "agent:extra", runner_id="runner:gone")
        missing = self.get_binding("prj_facts", "agent:extra").json()
        self.assertEqual(missing["binding_state"], ROLE_BINDING_RUNNER_MISSING)
        self.assertIsNone(missing["binding"]["runner_display_name"])
        self.assertIsNone(missing["binding"]["runner_status"])
        batch_missing = self.agent_by_id("prj_facts", "agent:extra")
        self.assertEqual(batch_missing["binding"], missing["binding"])

        # 身份/名册类状态不遮蔽仍可解析的登记事实：runtime 恢复后离册仍派生运行器字段。
        _set_registry_runtime(RUNNER_RUNTIME)
        self.sync("prj_facts", [{"member_id": "agent:other"}])
        offboard = self.get_binding("prj_facts", "agent:worker").json()
        self.assertEqual(offboard["binding_state"], ROLE_BINDING_NOT_IN_ROSTER)
        self.assertEqual(offboard["binding"]["runtime"], RUNNER_RUNTIME)
        self.assertEqual(
            offboard["binding"]["runner_display_name"], "DeepSeek Harness (CLI)"
        )
        self.assertEqual(offboard["binding"]["runner_status"], "adapted")
        self.assertIsNotNone(offboard["binding"]["binding_fingerprint"])

    def test_stored_identifier_with_trailing_control_char_is_partial(self):
        """存储标识必须整串匹配：末尾换行/回车/制表 → ``partial``、指纹 null（R3）。"""
        self.register_runner()

        # 单元层：整串判定，末尾控制字符不再被 ``$`` 放行。
        for token in ("model:test\n", "model:test\r", "model:test\t", "conn\n"):
            with self.subTest(token=repr(token)):
                self.assertFalse(is_safe_identifier_token(token))
        self.assertFalse(is_parseable_stored_runner_id(RUNNER_ID + "\n"))
        self.assertFalse(is_parseable_stored_runtime(RUNNER_RUNTIME + "\n"))
        self.assertFalse(is_parseable_stored_runtime(""))
        self.assertFalse(is_parseable_stored_runtime("   "))
        self.assertTrue(is_safe_identifier_token("model:test"))
        self.assertTrue(is_safe_identifier_token("kimi-code/kimi-for-coding"))
        self.assertTrue(is_parseable_stored_runner_id(RUNNER_ID))
        self.assertTrue(is_parseable_stored_runtime(RUNNER_RUNTIME))

        cases = {
            "model_id": ("agent:extra", {"model_id": "model:test\n"}),
            "provider_id": (
                "agent:extra2",
                {"provider_id": "managed:deepseek\n"},
            ),
            "connection_ref": (
                "agent:extra3",
                {"connection_ref": CONNECTION_REF + "\n"},
            ),
            "runner_id": ("agent:worker", {"runner_id": RUNNER_ID + "\n"}),
        }
        for name, (member_id, overrides) in cases.items():
            with self.subTest(name=name):
                self.seed_binding_row("prj_facts", member_id, **overrides)
                body = self.get_binding("prj_facts", member_id).json()
                binding = body["binding"]
                self.assertEqual(body["binding_state"], ROLE_BINDING_PARTIAL)
                self.assertIsNone(binding["binding_fingerprint"])
                # 坏值照存、照返，不用 strip 掩盖读取到的坏值。
                for key, value in overrides.items():
                    self.assertEqual(binding[key], value)
                entry = self.agent_by_id("prj_facts", member_id)
                self.assertEqual(entry["binding_state"], ROLE_BINDING_PARTIAL)
                self.assertIsNone(entry["binding"]["binding_fingerprint"])

        # 合法输入的归一化保持不变：API 写入先 strip，坏值不会因此入库。
        normalized = self.put_binding(
            "prj_facts",
            "agent:extra",
            self.binding_payload(
                model_id="  model:padded  ", runner_id="  " + RUNNER_ID + "  "
            ),
        )
        self.assertEqual(normalized.status_code, 200, normalized.text)
        stored = normalized.json()["binding"]
        self.assertEqual(stored["model_id"], "model:padded")
        self.assertEqual(stored["runner_id"], RUNNER_ID)
        self.assertEqual(normalized.json()["binding_state"], ROLE_BINDING_BOUND)

    # ── A21：语句计数与批量等价 ─────────────────────────────────────

    def test_single_statement_with_project_and_zero_without(self):
        statements, capture = self.capture_statements()
        try:
            with self.session() as session:
                read_role_binding_facts(
                    session, project_id="prj_facts", member_id="agent:worker"
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(len(statements), 1, statements)
        self.assertIn("AS requested_project_id", statements[0])

        statements.clear()
        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            with self.session() as session:
                facts = read_role_binding_facts(
                    session, project_id=None, member_id="agent:worker"
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(statements, [])
        self.assertEqual(facts["requested_member_id"], "agent:worker")
        for column in BINDING_FACTS_COLUMNS:
            if column != "requested_member_id":
                self.assertIsNone(facts[column], column)

    def test_batch_facts_match_single_facts(self):
        self.register_runner()
        self.put_binding("prj_facts", "agent:worker", self.binding_payload())
        member_ids = ["agent:worker", "agent:parked", "agent:ghost", "human:henry"]
        statements, capture = self.capture_statements()
        try:
            with self.session() as session:
                rows = read_role_binding_facts_batch(
                    session, project_id="prj_facts", member_ids=member_ids
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(len(statements), 1, statements)
        self.assertIn("AS requested_project_id", statements[0])
        self.assertEqual(len(rows), len(member_ids))
        self.assertEqual(
            {row["requested_member_id"] for row in rows}, set(member_ids)
        )
        for row in rows:
            single = self.facts("prj_facts", row["requested_member_id"])
            self.assertEqual(set(row), set(BINDING_FACTS_COLUMNS))
            self.assertEqual(resolve_role_binding_state(row), resolve_role_binding_state(single))
            self.assertEqual(binding_fingerprint(row), binding_fingerprint(single))

        # 空请求不查库。
        statements.clear()
        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            with self.session() as session:
                self.assertEqual(
                    read_role_binding_facts_batch(
                        session, project_id="prj_facts", member_ids=[]
                    ),
                    [],
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(statements, [])

    def test_get_agents_query_count_is_fixed_and_empty_roster_is_legal(self):
        self.register_runner()
        self.put_binding("prj_facts", "agent:worker", self.binding_payload())

        statements, capture = self.capture_statements()
        try:
            listed = self.get_agents("prj_facts")
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), len(self.ROSTER))
        matched = [
            statement
            for statement in statements
            if "AS requested_project_id" in statement
        ]
        self.assertEqual(len(matched), 1, matched)
        self.assertIn("VALUES", matched[0])
        # 读时状态与单角色助手一致（不是多读缓存推断）。
        for entry in listed.json():
            single = self.get_binding("prj_facts", entry["member_id"]).json()
            self.assertEqual(entry["binding_state"], single["binding_state"])
            self.assertEqual(entry["binding"], single["binding"])

        # 空名册合法：返回 []，且不产生事实读取语句、不写数据。
        self.register_project("prj_empty")
        self.assertEqual(self.sync("prj_empty", []).status_code, 200)
        statements.clear()
        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            empty = self.get_agents("prj_empty")
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json(), [])
        self.assertEqual(
            [s for s in statements if "requested_project_id" in s], []
        )
        self.assertEqual(self.binding_rows("prj_empty"), [])


if __name__ == "__main__":
    unittest.main()
