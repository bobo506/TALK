"""REQ-1 项目级开发要求：持久化、权限、MCP 读取路径与派发时快照。

覆盖：
- 老库增量迁移（不删列/不重建业务数据、重复初始化幂等、旧行保留）；
- 项目 API 的新建/读取/更新/清空/省略、中文换行、长度边界、越权与跨项目隔离；
- ``talk_list_agents`` 顶层项目级字段（含空值、只出现一次）；
- ``talk_delegate_task`` 派发时把当前要求写入所存任务正文并保留原始 content；
- 执行 bridge 实际从存储正文取快照、既有标题/Task Hall 命名规则不变；
- 非 MCP 入口（直接 ``POST /api/tasks``）不在本片覆盖范围内的限制。
"""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

import server.db as db
import server.main as main
from bridges.cli_bridge import build_cli_task_prompt
from bridges.talk_task_tools import (
    PROJECT_REQUIREMENTS_SNAPSHOT_HEADER,
    TOOL_SCHEMAS,
    TalkToolError,
    dispatch_tool,
    snapshot_task_content,
)
from server.models import Member, Project
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

REQUIREMENTS_A = (
    "角色职责与交叉复核（项目级）：\n"
    "- Kimi：文字 / 交互 / 前端，独立复核 DeepSeek 的后端改动\n"
    "- DeepSeek：后端，独立复核 Kimi 的前端改动\n"
    "约定：开发完成即暂停，等独立复核后再进入下一片。"
)
REQUIREMENTS_B = "更新后的要求：\n- DeepSeek：后端与主控工具\n- Kimi：前端编辑区"
MAX_CHARS = 20000


def tool_description(name: str) -> str:
    return next(tool["description"] for tool in TOOL_SCHEMAS if tool["name"] == name)


class SnapshotHelperTests(unittest.TestCase):
    def test_empty_requirements_keep_content_identical(self):
        self.assertEqual(snapshot_task_content("原始正文\n第二行", None), "原始正文\n第二行")

    def test_snapshot_appends_block_after_original_content(self):
        stored = snapshot_task_content("原始正文", REQUIREMENTS_A)
        self.assertTrue(stored.startswith("原始正文\n\n"))
        self.assertIn(f"【{PROJECT_REQUIREMENTS_SNAPSHOT_HEADER}】", stored)
        self.assertIn(REQUIREMENTS_A, stored)
        # 只拼接一次，且原始正文逐字保留。
        self.assertEqual(stored.count(REQUIREMENTS_A), 1)
        self.assertEqual(stored.count(PROJECT_REQUIREMENTS_SNAPSHOT_HEADER), 1)


class ProjectRequirementsApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")

    def register(self, project_id: str = "prj_req", **extra):
        with self.make_client() as client:
            return client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": project_id, "display_name": project_id, **extra},
            )

    def patch_project(self, project_id: str, payload: dict, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.patch(
                f"/api/projects/{project_id}",
                headers={"X-API-Key": key},
                json=payload,
            )

    def get_project(self, project_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(f"/api/projects/{project_id}", headers={"X-API-Key": key})

    def test_new_project_defaults_to_no_requirements(self):
        created = self.register()
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertIn("development_requirements", body)
        self.assertIsNone(body["development_requirements"])
        self.assertIsNone(self.get_project("prj_req").json()["development_requirements"])
        with self.session() as session:
            self.assertIsNone(session.get(Project, "prj_req").development_requirements)

    def test_requirements_round_trip_keeps_chinese_and_newlines(self):
        self.register()
        updated = self.patch_project("prj_req", {"development_requirements": REQUIREMENTS_A})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["development_requirements"], REQUIREMENTS_A)
        fetched = self.get_project("prj_req").json()["development_requirements"]
        self.assertEqual(fetched, REQUIREMENTS_A)
        self.assertEqual(fetched.count("\n"), REQUIREMENTS_A.count("\n"))

    def test_update_only_applies_explicit_fields(self):
        self.register(description="旧描述")
        self.patch_project("prj_req", {"development_requirements": REQUIREMENTS_A})

        # 省略 development_requirements 时保持原值，其它字段照常生效。
        omitted = self.patch_project("prj_req", {"description": "新描述"})
        self.assertEqual(omitted.status_code, 200)
        self.assertEqual(omitted.json()["description"], "新描述")
        self.assertEqual(omitted.json()["development_requirements"], REQUIREMENTS_A)

        # 显式 null 与空文本都可清空。
        cleared = self.patch_project("prj_req", {"development_requirements": None})
        self.assertIsNone(cleared.json()["development_requirements"])
        self.assertIsNone(self.get_project("prj_req").json()["development_requirements"])

        self.patch_project("prj_req", {"development_requirements": REQUIREMENTS_B})
        blank = self.patch_project("prj_req", {"development_requirements": ""})
        self.assertIsNone(blank.json()["development_requirements"])

        self.patch_project("prj_req", {"development_requirements": REQUIREMENTS_A})
        spaces = self.patch_project("prj_req", {"development_requirements": "   \n\t  "})
        self.assertIsNone(spaces.json()["development_requirements"])

    def test_length_boundary_accepts_limit_and_rejects_over_limit(self):
        self.register()
        at_limit = "要" * (MAX_CHARS - 1) + "\n"
        accepted = self.patch_project("prj_req", {"development_requirements": at_limit})
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(len(accepted.json()["development_requirements"]), MAX_CHARS)

        over_limit = "要" * (MAX_CHARS + 1)
        rejected = self.patch_project("prj_req", {"development_requirements": over_limit})
        self.assertEqual(rejected.status_code, 422)
        # 被拒绝的更新不落库，边界值保持不变。
        self.assertEqual(self.get_project("prj_req").json()["development_requirements"], at_limit)

        created_over = self.register("prj_over", development_requirements=over_limit)
        self.assertEqual(created_over.status_code, 422)

        created_at_limit = self.register(
            "prj_at_limit",
            development_requirements="第一行\n" + "要" * (MAX_CHARS - 4),
        )
        self.assertEqual(created_at_limit.status_code, 201)
        self.assertEqual(
            len(created_at_limit.json()["development_requirements"]),
            MAX_CHARS,
        )

    def test_agent_can_read_but_not_write_requirements(self):
        self.register()
        self.patch_project("prj_req", {"development_requirements": REQUIREMENTS_A})

        readable = self.get_project("prj_req", key="worker-key")
        self.assertEqual(readable.status_code, 200)
        self.assertEqual(readable.json()["development_requirements"], REQUIREMENTS_A)

        denied_patch = self.patch_project(
            "prj_req",
            {"development_requirements": REQUIREMENTS_B},
            key="worker-key",
        )
        self.assertEqual(denied_patch.status_code, 403)

        with self.make_client() as client:
            denied_create = client.post(
                "/api/projects",
                headers={"X-API-Key": "worker-key"},
                json={"project_id": "prj_agent", "display_name": "agent project"},
            )
        self.assertEqual(denied_create.status_code, 403)
        self.assertEqual(
            self.get_project("prj_req").json()["development_requirements"],
            REQUIREMENTS_A,
        )

    def test_requirements_are_isolated_per_project(self):
        self.register("prj_a")
        self.register("prj_b")
        self.patch_project("prj_a", {"development_requirements": REQUIREMENTS_A})
        self.patch_project("prj_b", {"development_requirements": REQUIREMENTS_B})

        self.assertEqual(
            self.get_project("prj_a").json()["development_requirements"],
            REQUIREMENTS_A,
        )
        self.assertEqual(
            self.get_project("prj_b").json()["development_requirements"],
            REQUIREMENTS_B,
        )
        self.patch_project("prj_a", {"development_requirements": None})
        self.assertIsNone(self.get_project("prj_a").json()["development_requirements"])
        self.assertEqual(
            self.get_project("prj_b").json()["development_requirements"],
            REQUIREMENTS_B,
        )

    def test_unknown_project_keeps_explicit_error_semantics(self):
        missing_get = self.get_project("prj_ghost")
        self.assertEqual(missing_get.status_code, 404)
        missing_patch = self.patch_project(
            "prj_ghost",
            {"development_requirements": REQUIREMENTS_A},
        )
        self.assertEqual(missing_patch.status_code, 404)


class ProjectRequirementsMigrationTests(unittest.TestCase):
    """老库（projects 表没有 development_requirements 列）安全升级。"""

    def setUp(self):
        super().setUp()
        tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self._tmpdir = Path(tempfile.mkdtemp(prefix="talk-legacy-", dir=tmp_root))
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
        # Windows 下连接池未释放会锁住 sqlite 文件，先 dispose 再删除临时目录。
        self.engine.dispose()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_legacy_database(self):
        """写一个本片之前形态的 projects 表：没有 development_requirements 列。"""
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

    def _client(self) -> TestClient:
        return TestClient(main.app)

    def test_legacy_database_upgrades_and_repeats_idempotently(self):
        self.assertNotIn("development_requirements", self._columns("projects"))

        db.init_db()
        db.init_db()  # 重复初始化必须幂等，且不覆盖已有数据

        self.assertIn("development_requirements", self._columns("projects"))
        with Session(self.engine) as session:
            legacy = session.get(Project, "prj_legacy")
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy.display_name, "Legacy Project")
            self.assertEqual(legacy.description, "升级前就存在的项目")
            self.assertEqual(legacy.project_root_path, "D:/legacy/root")
            self.assertEqual(legacy.maintainer_member_id, "human:bobo")
            self.assertIsNone(legacy.development_requirements)
            self.assertEqual(len(session.exec(select(Project)).all()), 1)

    def test_legacy_project_reads_and_writes_after_upgrade(self):
        db.init_db()
        self._seed_member()
        with self._client() as client:
            listed = client.get("/api/projects", headers={"X-API-Key": "bobo-key"})
            self.assertEqual(listed.status_code, 200)
            body = listed.json()[0]
            self.assertEqual(body["project_id"], "prj_legacy")
            self.assertIn("development_requirements", body)
            self.assertIsNone(body["development_requirements"])

            written = client.patch(
                "/api/projects/prj_legacy",
                headers={"X-API-Key": "bobo-key"},
                json={"development_requirements": REQUIREMENTS_A},
            )
            self.assertEqual(written.status_code, 200)
            self.assertEqual(written.json()["development_requirements"], REQUIREMENTS_A)

            # 只改其它字段时不丢要求；升级后的库再次初始化也不丢。
            renamed = client.patch(
                "/api/projects/prj_legacy",
                headers={"X-API-Key": "bobo-key"},
                json={"display_name": "Legacy Renamed"},
            )
            self.assertEqual(renamed.json()["development_requirements"], REQUIREMENTS_A)
            db.init_db()
            self.assertEqual(
                client.get(
                    "/api/projects/prj_legacy",
                    headers={"X-API-Key": "bobo-key"},
                ).json()["development_requirements"],
                REQUIREMENTS_A,
            )

            # 新项目在同一升级库里可正常写入新字段。
            created = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_new",
                    "display_name": "New Project",
                    "development_requirements": REQUIREMENTS_B,
                },
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json()["development_requirements"], REQUIREMENTS_B)


class ProjectRequirementsToolTests(RouteTestCase):
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

    @staticmethod
    def _environment(base_url: str, api_key: str, member_id: str) -> dict[str, str]:
        return {
            "TALK_BASE_URL": base_url,
            "TALK_API_KEY": api_key,
            "TALK_MEMBER_ID": member_id,
            "TALK_PROJECT_ID": "prj_tools",
        }

    def set_requirements(self, value, project_id: str = "prj_tools"):
        with self.make_client() as client:
            response = client.patch(
                f"/api/projects/{project_id}",
                headers={"X-API-Key": "bobo-key"},
                json={"development_requirements": value},
            )
        self.assertIn(response.status_code, (200, 422))
        return response

    def test_list_agents_returns_project_requirements_once(self):
        self.set_requirements(REQUIREMENTS_A)
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        self.assertEqual(result["project_id"], "prj_tools")
        self.assertEqual(result["development_requirements"], REQUIREMENTS_A)
        payload = json.dumps(result, ensure_ascii=False)
        # JSON 里换行会被转义，按同样转义后的文本计数。
        escaped_requirements = json.dumps(REQUIREMENTS_A, ensure_ascii=False)[1:-1]
        self.assertEqual(payload.count(escaped_requirements), 1)
        self.assertEqual(payload.count("development_requirements"), 1)
        for agent in result["agents"]:
            self.assertNotIn("development_requirements", agent)

    def test_list_agents_reports_empty_requirements_as_null(self):
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                project_result = dispatch_tool("talk_list_agents", {})
                other_result = dispatch_tool(
                    "talk_list_agents",
                    {"project_id": "prj_other"},
                )
            env_without_project = dict(env, TALK_PROJECT_ID="")
            with patch.dict(os.environ, env_without_project, clear=False):
                global_result = dispatch_tool("talk_list_agents", {})

        self.assertIn("development_requirements", project_result)
        self.assertIsNone(project_result["development_requirements"])
        self.assertIsNone(other_result["development_requirements"])
        self.assertIsNone(global_result["development_requirements"])
        self.assertIsNone(global_result["project_id"])

    def test_delegate_snapshot_uses_the_resolved_project(self):
        self.set_requirements(REQUIREMENTS_A, "prj_tools")
        self.set_requirements(REQUIREMENTS_B, "prj_other")
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                default_task = dispatch_tool(
                    "talk_delegate_task",
                    {"target_member_id": "agent:worker", "content": "原始正文一"},
                )
                other_task = dispatch_tool(
                    "talk_delegate_task",
                    {
                        "project_id": "prj_other",
                        "target_member_id": "agent:worker",
                        "content": "原始正文二",
                    },
                )

        self.assertIn(REQUIREMENTS_A, default_task["content"])
        self.assertNotIn(REQUIREMENTS_B, default_task["content"])
        self.assertIn(REQUIREMENTS_B, other_task["content"])
        self.assertNotIn(REQUIREMENTS_A, other_task["content"])
        self.assertTrue(default_task["content"].startswith("原始正文一\n\n"))
        self.assertTrue(other_task["content"].startswith("原始正文二\n\n"))

    def test_delegate_keeps_snapshot_of_previously_dispatched_task(self):
        self.set_requirements(REQUIREMENTS_A)
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                first = dispatch_tool(
                    "talk_delegate_task",
                    {"target_member_id": "agent:worker", "content": "任务一正文"},
                )
                self.set_requirements(REQUIREMENTS_B)
                second = dispatch_tool(
                    "talk_delegate_task",
                    {"target_member_id": "agent:worker", "content": "任务二正文"},
                )
                self.set_requirements(None)
                third = dispatch_tool(
                    "talk_delegate_task",
                    {"target_member_id": "agent:worker", "content": "任务三正文"},
                )
                reloaded_first = dispatch_tool("talk_get_task", {"task_id": first["id"]})

        self.assertIn(REQUIREMENTS_A, reloaded_first["task"]["content"])
        self.assertNotIn(REQUIREMENTS_B, reloaded_first["task"]["content"])
        self.assertIn(REQUIREMENTS_B, second["content"])
        self.assertNotIn(REQUIREMENTS_A, second["content"])
        self.assertEqual(third["content"], "任务三正文")
        self.assertNotIn(PROJECT_REQUIREMENTS_SNAPSHOT_HEADER, third["content"])

    def test_delegate_without_requirements_keeps_original_behavior(self):
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                created = dispatch_tool(
                    "talk_delegate_task",
                    {"target_member_id": "agent:worker", "content": "无要求项目正文"},
                )
        self.assertEqual(created["content"], "无要求项目正文")

    def test_delegate_missing_project_fails_without_fallback(self):
        self.set_requirements(REQUIREMENTS_A, "prj_tools")
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            env["TALK_PROJECT_ID"] = ""
            with patch.dict(os.environ, env, clear=False):
                with self.assertRaises(TalkToolError) as caught:
                    dispatch_tool(
                        "talk_delegate_task",
                        {
                            "project_id": "prj_ghost",
                            "target_member_id": "agent:worker",
                            "content": "不应创建",
                        },
                    )
                self.assertIn("404", str(caught.exception))
                # 不会拿别的项目/陈旧要求代替：失败没有创建任何新任务。
                listed = dispatch_tool(
                    "talk_list_tasks",
                    {"project_id": "prj_tools", "status": "queued"},
                )
                self.assertEqual(listed["tasks"], [])

                with self.assertRaises(TalkToolError):
                    dispatch_tool(
                        "talk_delegate_task",
                        {"target_member_id": "agent:worker", "content": "缺少项目"},
                    )

    def test_delegate_keeps_title_and_hall_naming_rules(self):
        self.set_requirements(REQUIREMENTS_A)
        untitled_content = "无标题任务：按既有规则命名"
        titled_content = "带标题任务正文"
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                untitled = dispatch_tool(
                    "talk_delegate_task",
                    {"target_member_id": "agent:worker", "content": untitled_content},
                )
                titled = dispatch_tool(
                    "talk_delegate_task",
                    {
                        "target_member_id": "agent:worker",
                        "title": "项目要求快照任务",
                        "content": titled_content,
                    },
                )
        with self.make_client() as client:
            untitled_hall = client.get(
                f"/api/groups/{untitled['hall_group_id']}",
                headers={"X-API-Key": "bobo-key"},
            ).json()
            titled_hall = client.get(
                f"/api/groups/{titled['hall_group_id']}",
                headers={"X-API-Key": "bobo-key"},
            ).json()

        self.assertEqual(untitled["title"], f"{untitled['id']}-未命名任务")
        self.assertEqual(titled["title"], f"{titled['id']}-项目要求快照任务")
        self.assertEqual(untitled_hall["name"], untitled["title"])
        self.assertEqual(titled_hall["name"], titled["title"])
        self.assertTrue(titled["content"].startswith(f"{titled_content}\n\n"))

    def test_claimed_content_is_what_the_executing_bridge_reads(self):
        self.set_requirements(REQUIREMENTS_A)
        content = "实现一个明确切片"
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                created = dispatch_tool(
                    "talk_delegate_task",
                    {"target_member_id": "agent:worker", "content": content},
                )
            with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
                claimed = client.post(
                    f"/api/tasks/{created['id']}/claim",
                    headers={"X-API-Key": "worker-key"},
                    json={},
                ).json()

        self.assertIn(PROJECT_REQUIREMENTS_SNAPSHOT_HEADER, claimed["content"])
        self.assertIn(REQUIREMENTS_A, claimed["content"])
        self.assertIn(content, claimed["content"])
        # cli_bridge 的 prompt 只从 claim 回来的存储正文取任务文本，
        # 因此快照会随任务包进入执行者上下文。
        prompt = build_cli_task_prompt(
            claimed,
            member_id="agent:worker",
            workdir=Path("D:/claude-test/TALK"),
            runtime="pi",
            decision_tier="execution",
        )
        self.assertIn(PROJECT_REQUIREMENTS_SNAPSHOT_HEADER, prompt)
        self.assertIn(REQUIREMENTS_A, prompt)
        self.assertIn(content, prompt)

    def test_direct_rest_task_creation_is_out_of_scope(self):
        """限制：本片只覆盖 MCP talk_delegate_task，直接调用 REST 不写快照。"""
        self.set_requirements(REQUIREMENTS_A)
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:worker",
                    "content": "直接 REST 创建",
                    "project_id": "prj_tools",
                },
            )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["content"], "直接 REST 创建")

    def test_tool_descriptions_document_requirements_flow(self):
        list_description = tool_description("talk_list_agents")
        delegate_description = tool_description("talk_delegate_task")
        self.assertIn("development_requirements", list_description)
        self.assertIn("派发", list_description)
        self.assertIn("派发前", delegate_description)
        self.assertIn(PROJECT_REQUIREMENTS_SNAPSHOT_HEADER, delegate_description)
        self.assertIn("不覆盖宿主系统指令", delegate_description)


if __name__ == "__main__":
    unittest.main()
