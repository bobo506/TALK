"""C1a 项目主控模式配置与只读状态基础。

覆盖：
- 老库幂等增列迁移：不重建表、不删改既有数据，旧项目回落 ``passive`` / ``0``；
- 专用入口 ``PATCH /api/projects/{id}/controller-mode``：认证、human 可写 / agent 只读、
  跨项目隔离、不存在项目 404、非法 mode/类型/负版本/缺 expected_version 拒绝；
- 版本规则：passive→active→passive 递增、同值幂等不增版本、陈旧版本 409（含同值陈旧）；
- CAS 落在数据库写入层：独立 session 陈旧读取不能覆盖、真实并发只有一次有效写入；
- 旁路防护：普通 ``ProjectUpdate``、项目注册、CLI 重注册、``sync`` 都不能改模式或绕过 CAS；
- ``talk_list_agents`` 只读 ``controller_mode``：复用同一次项目 GET、非项目 null、
  旧后端 unsupported、失败明确报错、REQ-1 字段不回归、不新增 MCP 工具；
- 写入只保存意向：不创建任务、不改实例、不产生生效/授权声明。
"""

import gc
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlmodel import Session, create_engine, select

import server.db as db
import server.main as main
from bridges import talk_task_tools
from bridges.talk_task_tools import (
    CONTROLLER_MODE_EFFECTIVE_STATUS_SUPPORTED,
    CONTROLLER_MODE_EFFECTIVE_STATUS_UNSUPPORTED,
    TOOL_SCHEMAS,
    TalkToolError,
    controller_mode_summary,
    dispatch_tool,
)
from server.models import AgentInstance, AgentTask, Member, Project
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

PROJECT_TOOL_NAMES = (
    "talk_list_agents",
    "talk_delegate_task",
    "talk_get_task",
    "talk_list_tasks",
    "talk_wait_tasks",
    "talk_reply_task",
    "talk_cancel_task",
    "talk_collect_result",
    "talk_get_delivery",
)


def tool_description(name: str) -> str:
    return next(tool["description"] for tool in TOOL_SCHEMAS if tool["name"] == name)


class ControllerModeApiTests(RouteTestCase):
    """专用配置入口的权限、校验、版本规则与跨项目隔离。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:carol", api_key="carol-key", display_name="Carol")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")

    def register(self, project_id: str = "prj_mode", **extra):
        with self.make_client() as client:
            return client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": project_id, "display_name": project_id, **extra},
            )

    def patch_mode(
        self,
        project_id: str = "prj_mode",
        payload=None,
        *,
        key: str = "bobo-key",
    ):
        body = {"mode": "active", "expected_version": 0} if payload is None else payload
        with self.make_client() as client:
            return client.patch(
                f"/api/projects/{project_id}/controller-mode",
                headers={"X-API-Key": key} if key else {},
                json=body,
            )

    def get_project(self, project_id: str = "prj_mode", *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}",
                headers={"X-API-Key": key} if key else {},
            )

    def stored_state(self, project_id: str = "prj_mode") -> tuple[str, int]:
        with self.session() as session:
            project = session.get(Project, project_id)
            return project.controller_mode, project.controller_mode_version

    def test_new_project_defaults_to_passive_zero(self):
        created = self.register()
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["controller_mode"], "passive")
        self.assertEqual(body["controller_mode_version"], 0)

        fetched = self.get_project().json()
        self.assertEqual(fetched["controller_mode"], "passive")
        self.assertEqual(fetched["controller_mode_version"], 0)

        with self.make_client() as client:
            listed = client.get(
                "/api/projects", headers={"X-API-Key": "bobo-key"}
            ).json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["controller_mode"], "passive")
        self.assertEqual(listed[0]["controller_mode_version"], 0)
        self.assertEqual(self.stored_state(), ("passive", 0))

    def test_registration_cannot_inject_controller_mode(self):
        """注册旁路：即便客户端塞模式字段，新项目仍是默认 passive/0。"""
        created = self.register(
            controller_mode="active",
            controller_mode_version=7,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["controller_mode"], "passive")
        self.assertEqual(created.json()["controller_mode_version"], 0)
        self.assertEqual(self.stored_state(), ("passive", 0))

    def test_agent_can_read_but_cannot_write(self):
        self.register()
        self.patch_mode(key="bobo-key")  # human 写入 active/1

        read_as_agent = self.get_project(key="worker-key")
        self.assertEqual(read_as_agent.status_code, 200)
        self.assertEqual(read_as_agent.json()["controller_mode"], "active")

        denied = self.patch_mode(payload={"mode": "passive", "expected_version": 1}, key="worker-key")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.stored_state(), ("active", 1))

    def test_missing_or_invalid_key_is_rejected(self):
        self.register()
        missing = self.patch_mode(key=None)
        self.assertEqual(missing.status_code, 422)  # 缺 X-API-Key header
        invalid = self.patch_mode(payload={"mode": "active", "expected_version": 0}, key="ghost-key")
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(self.stored_state(), ("passive", 0))

    def test_unknown_project_returns_404(self):
        response = self.patch_mode(project_id="prj_ghost", payload={"mode": "active", "expected_version": 0})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "project not found")

    def test_invalid_body_is_rejected_without_writing(self):
        self.register()
        invalid_payloads = (
            {"mode": "ACTIVE", "expected_version": 0},
            {"mode": "enabled", "expected_version": 0},
            {"mode": "", "expected_version": 0},
            {"mode": 1, "expected_version": 0},
            {"mode": "active"},
            {"mode": "active", "expected_version": None},
            {"mode": "active", "expected_version": "0"},
            {"mode": "active", "expected_version": 0.0},
            {"mode": "active", "expected_version": 1.5},
            {"mode": "active", "expected_version": True},
            {"mode": "active", "expected_version": -1},
            {"expected_version": 0},
            {},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.patch_mode(payload=payload)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.stored_state(), ("passive", 0))

    def test_expected_version_out_of_sqlite_range_is_rejected(self):
        """越界 expected_version 在请求校验层 422，不进入写入（原为 SQLite 绑定 OverflowError→500）。

        SQLite INTEGER 是有符号 64 位：上界本身可绑定，超界值必须在校验层被拦下，
        否则条件 UPDATE 绑定时抛 OverflowError 变成 HTTP 500。
        """
        sqlite_int_max = 2**63 - 1
        self.register()

        out_of_range = (
            {"mode": "active", "expected_version": 2**63},
            {"mode": "active", "expected_version": 2**63 + 1},
            {"mode": "active", "expected_version": 10**30},
        )
        for payload in out_of_range:
            with self.subTest(payload=payload):
                response = self.patch_mode(payload=payload)
                self.assertNotEqual(response.status_code, 500, response.text)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.stored_state(), ("passive", 0))

        # 上界是合法版本值：当前库为版本 0，因此是正常 409，不是 422/500。
        boundary = self.patch_mode(
            payload={"mode": "active", "expected_version": sqlite_int_max}
        )
        self.assertEqual(boundary.status_code, 409, boundary.text)
        self.assertIn(f"expected_version={sqlite_int_max}", boundary.json()["detail"])
        self.assertIn("current_version=0", boundary.json()["detail"])
        self.assertEqual(self.stored_state(), ("passive", 0))

        # 越界请求不影响库，后续正常 CAS 仍成功。
        normal = self.patch_mode(payload={"mode": "active", "expected_version": 0})
        self.assertEqual(normal.status_code, 200, normal.text)
        self.assertEqual(
            (normal.json()["controller_mode"], normal.json()["controller_mode_version"]),
            ("active", 1),
        )
        self.assertEqual(self.stored_state(), ("active", 1))

    def test_expected_version_type_and_sign_rules_still_apply(self):
        """加范围上界不放松原有 strict/非负规则：bool/float/string/负数仍 422。"""
        self.register()
        still_invalid = (
            {"mode": "active", "expected_version": True},
            {"mode": "active", "expected_version": 1.0},
            {"mode": "active", "expected_version": "9223372036854775807"},
            {"mode": "active", "expected_version": -1},
        )
        for payload in still_invalid:
            with self.subTest(payload=payload):
                response = self.patch_mode(payload=payload)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.stored_state(), ("passive", 0))

    def test_passive_active_passive_increments_version(self):
        self.register()

        first = self.patch_mode(payload={"mode": "active", "expected_version": 0})
        self.assertEqual(first.status_code, 200)
        self.assertEqual((first.json()["controller_mode"], first.json()["controller_mode_version"]), ("active", 1))

        second = self.patch_mode(payload={"mode": "passive", "expected_version": 1})
        self.assertEqual(second.status_code, 200)
        self.assertEqual((second.json()["controller_mode"], second.json()["controller_mode_version"]), ("passive", 2))
        self.assertEqual(self.stored_state(), ("passive", 2))

        third = self.patch_mode(payload={"mode": "active", "expected_version": 2})
        self.assertEqual(third.json()["controller_mode_version"], 3)
        self.assertEqual(self.stored_state(), ("active", 3))

    def test_same_value_request_is_idempotent(self):
        self.register()

        noop_initial = self.patch_mode(payload={"mode": "passive", "expected_version": 0})
        self.assertEqual(noop_initial.status_code, 200)
        self.assertEqual(noop_initial.json()["controller_mode_version"], 0)

        self.patch_mode(payload={"mode": "active", "expected_version": 0})
        noop_after_change = self.patch_mode(payload={"mode": "active", "expected_version": 1})
        self.assertEqual(noop_after_change.status_code, 200)
        self.assertEqual(noop_after_change.json()["controller_mode_version"], 1)
        self.assertEqual(self.stored_state(), ("active", 1))

        repeated = self.patch_mode(payload={"mode": "active", "expected_version": 1})
        self.assertEqual(repeated.json()["controller_mode_version"], 1)
        self.assertEqual(self.stored_state(), ("active", 1))

    def test_stale_version_conflicts_even_when_mode_matches(self):
        self.register()
        self.patch_mode(payload={"mode": "active", "expected_version": 0})  # active / 1

        stale_same_mode = self.patch_mode(payload={"mode": "active", "expected_version": 0})
        self.assertEqual(stale_same_mode.status_code, 409)
        self.assertIn("version conflict", stale_same_mode.json()["detail"])
        self.assertIn("current_version=1", stale_same_mode.json()["detail"])

        stale_other_mode = self.patch_mode(payload={"mode": "passive", "expected_version": 0})
        self.assertEqual(stale_other_mode.status_code, 409)

        future_version = self.patch_mode(payload={"mode": "passive", "expected_version": 9})
        self.assertEqual(future_version.status_code, 409)

        # 冲突请求不写入、不覆盖。
        self.assertEqual(self.stored_state(), ("active", 1))

    def test_regular_project_update_cannot_touch_controller_mode(self):
        self.register()
        self.patch_mode(payload={"mode": "active", "expected_version": 0})  # active / 1

        with self.make_client() as client:
            response = client.patch(
                "/api/projects/prj_mode",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "display_name": "改名",
                    "controller_mode": "passive",
                    "controller_mode_version": 99,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["display_name"], "改名")
        self.assertEqual(response.json()["controller_mode"], "active")
        self.assertEqual(response.json()["controller_mode_version"], 1)
        self.assertEqual(self.stored_state(), ("active", 1))

    def test_cli_reregistration_and_sync_do_not_bypass_cas(self):
        self.register()
        self.patch_mode(payload={"mode": "active", "expected_version": 0})  # active / 1

        # CLI `talk init` 对已存在项目只会拿到 409，不会改写模式字段。
        reregister = self.register(controller_mode="passive", controller_mode_version=0)
        self.assertEqual(reregister.status_code, 409)
        self.assertEqual(self.stored_state(), ("active", 1))

        with self.make_client() as client:
            synced = client.post(
                "/api/projects/prj_mode/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": "agent:worker"}]},
            )
        self.assertEqual(synced.status_code, 200)
        self.assertEqual(self.stored_state(), ("active", 1))

        # sync / 普通 PATCH 之后版本没有被旁路推进，正确版本仍可正常写入。
        self.assertEqual(
            self.patch_mode(payload={"mode": "passive", "expected_version": 1}).status_code,
            200,
        )
        self.assertEqual(self.stored_state(), ("passive", 2))

    def test_cross_project_isolation(self):
        self.register("prj_mode")
        self.register("prj_other")

        self.patch_mode("prj_mode", {"mode": "active", "expected_version": 0})
        self.assertEqual(self.stored_state("prj_other"), ("passive", 0))
        self.assertEqual(
            self.patch_mode("prj_other", {"mode": "active", "expected_version": 0}).status_code,
            200,
        )
        self.assertEqual(self.stored_state("prj_mode"), ("active", 1))
        self.assertEqual(self.stored_state("prj_other"), ("active", 1))

        # 一个项目的陈旧版本不影响另一个项目。
        self.assertEqual(
            self.patch_mode("prj_mode", {"mode": "passive", "expected_version": 0}).status_code,
            409,
        )
        self.assertEqual(
            self.patch_mode("prj_other", {"mode": "active", "expected_version": 1}).status_code,
            200,
        )

    def test_mode_write_creates_no_tasks_instances_or_side_effects(self):
        self.register("prj_mode")
        with self.session() as session:
            tasks_before = len(session.exec(select(AgentTask)).all())
            instances_before = len(session.exec(select(AgentInstance)).all())

        response = self.patch_mode(payload={"mode": "active", "expected_version": 0})
        self.assertEqual(response.status_code, 200)

        with self.session() as session:
            self.assertEqual(len(session.exec(select(AgentTask)).all()), tasks_before)
            self.assertEqual(len(session.exec(select(AgentInstance)).all()), instances_before)
        # 返回体不宣称生效：只有保存的意向与版本。
        body = response.json()
        self.assertEqual(body["controller_mode"], "active")
        self.assertNotIn("effective_mode", body)
        self.assertNotIn("ack", json.dumps(body, ensure_ascii=False).lower())


class ControllerModeRaceTests(RouteTestCase):
    """并发/独立 session：CAS 必须由数据库写入层保证，而不是先读后写。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        # WAL 让并发读写不互相阻塞，避免测试受 rollback journal 读锁影响。
        db.init_db()

    def register(self, project_id: str) -> None:
        with self.make_client() as client:
            response = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": project_id, "display_name": project_id},
            )
        self.assertEqual(response.status_code, 201)

    def patch_mode(self, project_id: str, mode: str, expected_version: int = 0):
        with self.make_client() as client:
            return client.patch(
                f"/api/projects/{project_id}/controller-mode",
                headers={"X-API-Key": "bobo-key"},
                json={"mode": mode, "expected_version": expected_version},
            )

    def stored_state(self, project_id: str) -> tuple[str, int]:
        with self.session() as session:
            project = session.get(Project, project_id)
            return project.controller_mode, project.controller_mode_version

    def race(self, project_id: str, modes: list[str], expected_version: int = 0):
        results: list[tuple[str, int, dict]] = []
        barrier = threading.Barrier(len(modes))

        def call(mode: str) -> None:
            barrier.wait(timeout=20)
            response = self.patch_mode(project_id, mode, expected_version)
            results.append((mode, response.status_code, response.json()))

        threads = [threading.Thread(target=call, args=(mode,)) for mode in modes]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(len(results), len(modes), f"并发请求未全部返回: {results}")
        return results

    def test_concurrent_competing_writes_have_one_effective_update(self):
        for index in range(6):
            project_id = f"prj_race_{index}"
            self.register(project_id)
            results = self.race(project_id, ["active", "active"])

            statuses = sorted(status for _mode, status, _body in results)
            self.assertEqual(statuses, [200, 409], f"第 {index} 轮: {results}")
            winner = next(body for _m, status, body in results if status == 200)
            loser = next(body for _m, status, body in results if status == 409)
            self.assertEqual((winner["controller_mode"], winner["controller_mode_version"]), ("active", 1))
            self.assertIn("version conflict", loser["detail"])
            self.assertEqual(self.stored_state(project_id), ("active", 1))

    def test_concurrent_opposite_intents_keep_legal_state(self):
        for index in range(6):
            project_id = f"prj_race_mixed_{index}"
            self.register(project_id)
            results = self.race(project_id, ["active", "passive"])

            for mode, status, body in results:
                self.assertIn(status, (200, 409), f"{mode}: {body}")
                if status == 409:
                    self.assertIn("version conflict", body["detail"])
                else:
                    # 200 只会返回真实存在过的状态：passive/0（同值幂等）或 active/1（有效更新）。
                    self.assertIn(
                        (body["controller_mode"], body["controller_mode_version"]),
                        (("passive", 0), ("active", 1)),
                    )

            # 只有 active 是相对初始 passive 的有效更新；无论两个请求如何交错，
            # 它都必须真实落库一次，且同值 passive 请求不会把它覆盖回 passive/0。
            self.assertEqual(self.stored_state(project_id), ("active", 1))
            changed = [
                body
                for _m, status, body in results
                if status == 200 and body["controller_mode_version"] == 1
            ]
            self.assertEqual(len(changed), 1, results)
            self.assertEqual(changed[0]["controller_mode"], "active")
            # 写入已真实持久化：陈旧版本现在必须冲突。
            self.assertEqual(self.patch_mode(project_id, "passive", 0).status_code, 409)

    def test_stale_reader_session_cannot_overwrite_newer_version(self):
        self.register("prj_stale")
        with self.session() as stale_session:
            stale_project = stale_session.get(Project, "prj_stale")
            stale_version = stale_project.controller_mode_version

            # 另一个独立会话（HTTP 请求）用同一版本成功推进。
            winner = self.patch_mode("prj_stale", "active", stale_version)
            self.assertEqual(winner.status_code, 200)
            self.assertEqual(winner.json()["controller_mode_version"], stale_version + 1)

            # 陈旧会话按它读到的旧版本重试：必须冲突，且不覆盖 winner。
            loser = self.patch_mode("prj_stale", "passive", stale_version)
            self.assertEqual(loser.status_code, 409)
            stale_session.expire_all()
            self.assertEqual(
                (stale_project.controller_mode, stale_project.controller_mode_version),
                ("active", stale_version + 1),
            )

    def test_conditional_write_predicate_is_enforced_by_database(self):
        """写入层的条件谓词：陈旧版本的条件 UPDATE 命中 0 行，不会覆盖新值。"""
        self.register("prj_predicate")
        self.patch_mode("prj_predicate", "active", 0)  # active / 1

        with self.session() as session:
            result = session.execute(
                update(Project)
                .where(
                    Project.project_id == "prj_predicate",
                    Project.controller_mode_version == 0,
                    Project.controller_mode != "active",
                )
                .values(
                    controller_mode="active",
                    controller_mode_version=Project.controller_mode_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            session.commit()
            self.assertEqual(result.rowcount, 0)

        with self.session() as session:
            project = session.get(Project, "prj_predicate")
            self.assertEqual((project.controller_mode, project.controller_mode_version), ("active", 1))


class ControllerModeMigrationTests(unittest.TestCase):
    """老库（projects 表没有 controller_mode* 列）安全升级。"""

    def setUp(self):
        super().setUp()
        self._tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        self._tmp_root.mkdir(parents=True, exist_ok=True)
        self._old_engine = db.engine
        self._old_main_engine = main.engine
        self._setup_legacy(include_requirements=True)
        self.addCleanup(self._restore_engines)

    def _setup_legacy(self, *, include_requirements: bool) -> None:
        self._tmpdir = Path(
            tempfile.mkdtemp(prefix="talk-c1a-legacy-", dir=self._tmp_root)
        )
        self.db_path = self._tmpdir / "legacy.db"
        self._write_legacy_database(include_requirements=include_requirements)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        db.engine = self.engine
        main.engine = self.engine

    def _restore_engines(self):
        db.engine = self._old_engine
        main.engine = self._old_main_engine
        # Windows 下 sqlite 文件可能被未回收的连接短暂持有：dispose + 重试删除，避免残留临时库。
        self.engine.dispose()
        for _attempt in range(5):
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            if not self._tmpdir.exists():
                break
            gc.collect()
            time.sleep(0.2)
        self.assertFalse(self._tmpdir.exists(), f"临时测试目录未清理: {self._tmpdir}")

    def _write_legacy_database(self, *, include_requirements: bool) -> None:
        """写本片之前形态的 projects 表：可能停在 REQ-1 之前或之后。"""
        requirements_column = (
            "development_requirements TEXT," if include_requirements else ""
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""
                CREATE TABLE projects (
                    project_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    project_root_path TEXT,
                    {requirements_column}
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

    def _columns(self, table: str) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }

    def _seed_member(self):
        with Session(self.engine) as session:
            session.add(
                Member(
                    id="human:bobo",
                    kind="human",
                    display_name="Bobo",
                    api_key="bobo-key",
                )
            )
            session.commit()

    def test_legacy_database_upgrades_and_repeats_idempotently(self):
        self.assertNotIn("controller_mode", self._columns("projects"))
        self.assertNotIn("controller_mode_version", self._columns("projects"))

        db.init_db()
        db.init_db()  # 幂等：重复初始化不重建表、不覆盖数据

        self.assertIn("controller_mode", self._columns("projects"))
        self.assertIn("controller_mode_version", self._columns("projects"))
        with Session(self.engine) as session:
            legacy = session.get(Project, "prj_legacy")
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy.display_name, "Legacy Project")
            self.assertEqual(legacy.description, "升级前就存在的项目")
            self.assertEqual(legacy.project_root_path, "D:/legacy/root")
            self.assertEqual(legacy.controller_mode, "passive")
            self.assertEqual(legacy.controller_mode_version, 0)
            self.assertEqual(len(session.exec(select(Project)).all()), 1)

    def test_oldest_legacy_database_gets_both_migrations(self):
        """停在 REQ-1 之前的更老库：两批迁移可以在同一次升级里共存。"""
        self._restore_engines()
        self._setup_legacy(include_requirements=False)

        self.assertNotIn("development_requirements", self._columns("projects"))
        db.init_db()
        self.assertIn("development_requirements", self._columns("projects"))
        self.assertIn("controller_mode", self._columns("projects"))
        self.assertIn("controller_mode_version", self._columns("projects"))
        with Session(self.engine) as session:
            legacy = session.get(Project, "prj_legacy")
            self.assertEqual(legacy.controller_mode, "passive")
            self.assertEqual(legacy.controller_mode_version, 0)
            self.assertEqual(len(session.exec(select(Project)).all()), 1)

    def test_legacy_project_round_trips_through_api_and_stays_default(self):
        db.init_db()
        self._seed_member()
        with TestClient(main.app) as client:
            listed = client.get("/api/projects", headers={"X-API-Key": "bobo-key"})
            self.assertEqual(listed.status_code, 200)
            body = listed.json()[0]
            self.assertEqual(body["controller_mode"], "passive")
            self.assertEqual(body["controller_mode_version"], 0)

            written = client.patch(
                "/api/projects/prj_legacy/controller-mode",
                headers={"X-API-Key": "bobo-key"},
                json={"mode": "active", "expected_version": 0},
            )
            self.assertEqual(written.status_code, 200)
            self.assertEqual(written.json()["controller_mode_version"], 1)
            db.init_db()  # 再次初始化不重置已升级数据
            self.assertEqual(
                client.get(
                    "/api/projects/prj_legacy", headers={"X-API-Key": "bobo-key"}
                ).json()["controller_mode"],
                "active",
            )


class ControllerModeToolTests(RouteTestCase):
    """MCP ``talk_list_agents`` 顶层只读 controller_mode。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        with self.make_client() as client:
            for project_id in ("prj_tools", "prj_other"):
                created = client.post(
                    "/api/projects",
                    headers={"X-API-Key": "bobo-key"},
                    json={"project_id": project_id, "display_name": project_id},
                )
                self.assertEqual(created.status_code, 201)
                synced = client.post(
                    f"/api/projects/{project_id}/sync",
                    headers={"X-API-Key": "bobo-key"},
                    json={"agents": [{"member_id": "agent:worker"}]},
                )
                self.assertEqual(synced.status_code, 200)

    def set_mode(self, project_id: str, mode: str, expected_version: int):
        with self.make_client() as client:
            response = client.patch(
                f"/api/projects/{project_id}/controller-mode",
                headers={"X-API-Key": "bobo-key"},
                json={"mode": mode, "expected_version": expected_version},
            )
        self.assertEqual(response.status_code, 200)
        return response.json()

    @staticmethod
    def _environment(base_url: str, api_key: str, member_id: str) -> dict[str, str]:
        return {
            "TALK_BASE_URL": base_url,
            "TALK_API_KEY": api_key,
            "TALK_MEMBER_ID": member_id,
            "TALK_PROJECT_ID": "prj_tools",
        }

    def test_list_agents_reports_requested_mode_and_version(self):
        self.set_mode("prj_tools", "active", 0)
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        controller = result["controller_mode"]
        self.assertEqual(result["project_id"], "prj_tools")
        self.assertTrue(controller["supported"])
        self.assertEqual(controller["requested_mode"], "active")
        self.assertEqual(controller["requested_version"], 1)
        self.assertIsNone(controller["effective_mode"])
        self.assertEqual(controller["effective_status"], CONTROLLER_MODE_EFFECTIVE_STATUS_SUPPORTED)
        self.assertEqual(controller["effective_status"], "not_bound")
        self.assertIn("意向", controller["note"])
        # 角色条目仍是原样，不重复写模式字段。
        for agent in result["agents"]:
            self.assertNotIn("controller_mode", agent)
            self.assertNotIn("effective_mode", agent)

    def test_mode_matches_the_project_get_and_reuses_one_request(self):
        self.set_mode("prj_tools", "active", 0)
        requests: list[tuple[str, str]] = []
        real_request = talk_task_tools._api_request

        def counting_request(method, path, **kwargs):
            requests.append((method.upper(), path))
            return real_request(method, path, **kwargs)

        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                with patch.object(talk_task_tools, "_api_request", counting_request):
                    result = dispatch_tool("talk_list_agents", {})
                with self.make_client() as client:
                    direct = client.get(
                        "/api/projects/prj_tools",
                        headers={"X-API-Key": "bobo-key"},
                    ).json()

        controller = result["controller_mode"]
        self.assertEqual(controller["requested_mode"], direct["controller_mode"])
        self.assertEqual(controller["requested_version"], direct["controller_mode_version"])
        project_gets = [
            path for method, path in requests if method == "GET" and path == "/api/projects/prj_tools"
        ]
        self.assertEqual(len(project_gets), 1, requests)
        # REQ-1 开发要求读取路径不回归：同一份项目响应里的字段仍出现在顶层。
        self.assertEqual(result["development_requirements"], direct["development_requirements"])

    def test_non_project_path_reports_null(self):
        with LiveTalkServer(main.app) as base_url:
            env = dict(self._environment(base_url, "bobo-key", "human:bobo"), TALK_PROJECT_ID="")
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        self.assertIsNone(result["project_id"])
        self.assertIsNone(result["controller_mode"])
        self.assertIsNone(result["development_requirements"])

    def test_other_project_reports_its_own_mode(self):
        self.set_mode("prj_tools", "active", 0)
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                other = dispatch_tool("talk_list_agents", {"project_id": "prj_other"})

        self.assertEqual(other["project_id"], "prj_other")
        self.assertEqual(other["controller_mode"]["requested_mode"], "passive")
        self.assertEqual(other["controller_mode"]["requested_version"], 0)

    def test_old_backend_without_fields_is_marked_unsupported(self):
        """旧后端缺模式字段：明确 unsupported，不回退猜测成 passive。"""
        real_request = talk_task_tools._api_request

        def legacy_request(method, path, **kwargs):
            payload = real_request(method, path, **kwargs)
            if path == "/api/projects/prj_tools" and isinstance(payload, dict):
                payload = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"controller_mode", "controller_mode_version"}
                }
            return payload

        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                with patch.object(talk_task_tools, "_api_request", legacy_request):
                    result = dispatch_tool("talk_list_agents", {})

        controller = result["controller_mode"]
        self.assertFalse(controller["supported"])
        self.assertIsNone(controller["requested_mode"])
        self.assertIsNone(controller["requested_version"])
        self.assertIsNone(controller["effective_mode"])
        self.assertEqual(
            controller["effective_status"], CONTROLLER_MODE_EFFECTIVE_STATUS_UNSUPPORTED
        )
        self.assertEqual(controller["effective_status"], "unsupported")
        self.assertIn("旧后端", controller["note"])

    def test_project_read_failure_is_reported_not_faked(self):
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                with self.assertRaises(TalkToolError) as caught:
                    dispatch_tool("talk_list_agents", {"project_id": "prj_ghost"})
        self.assertIn("404", str(caught.exception))

    def test_summary_never_claims_effective_mode(self):
        supported = controller_mode_summary(
            {"project_id": "p", "controller_mode": "active", "controller_mode_version": 3}
        )
        self.assertIsNone(supported["effective_mode"])
        self.assertEqual(supported["effective_status"], "not_bound")

        degraded = controller_mode_summary({"project_id": "p"})
        self.assertFalse(degraded["supported"])
        self.assertIsNone(degraded["effective_mode"])
        self.assertIsNone(degraded["requested_mode"])

        weird = controller_mode_summary(
            {"project_id": "p", "controller_mode": "broken", "controller_mode_version": "x"}
        )
        self.assertTrue(weird["supported"])
        self.assertIsNone(weird["requested_mode"])
        self.assertIsNone(weird["requested_version"])

    def test_tool_surface_unchanged_and_description_documents_intent_only(self):
        self.assertEqual(len(TOOL_SCHEMAS), 9)
        self.assertEqual(
            tuple(tool["name"] for tool in TOOL_SCHEMAS), PROJECT_TOOL_NAMES
        )
        description = tool_description("talk_list_agents")
        self.assertIn("controller_mode", description)
        self.assertIn("requested_mode", description)
        self.assertIn("effective_mode", description)
        self.assertIn("not_bound", description)
        self.assertIn("unsupported", description)
        self.assertIn("不等于已生效", description)
        self.assertIn("用户通知", description)

    def test_mode_is_read_only_for_agents_and_not_a_new_tool(self):
        """agent 身份读取模式不做任何写入；工具也是原样 9 个只读入口。"""
        self.set_mode("prj_tools", "active", 0)
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "worker-key", "agent:worker")
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        self.assertEqual(result["controller_mode"]["requested_mode"], "active")
        with self.session() as session:
            project = session.get(Project, "prj_tools")
            self.assertEqual((project.controller_mode, project.controller_mode_version), ("active", 1))


if __name__ == "__main__":
    unittest.main()
