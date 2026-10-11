"""Hall type template API and migration tests."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from sqlmodel import create_engine

import server.db as db
from server.hall_types import HALL_TYPE_TEMPLATES
from tests.test_support import RouteTestCase


class HallTypeRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")

    def test_list_hall_types_returns_builtin_templates(self):
        with self.make_client() as client:
            response = client.get("/api/hall-types", headers={"X-API-Key": "bobo-key"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["type"] for item in payload], list(HALL_TYPE_TEMPLATES))
        by_type = {item["type"]: item for item in payload}
        self.assertEqual(by_type["free"]["roles"], [])
        for item in payload:
            self.assertIn("label", item)
            self.assertIn("protocol_guidance", item)
            self.assertIsInstance(item["roles"], list)
            for role in item["roles"]:
                self.assertEqual(set(role), {"role", "norm"})

    def test_list_hall_types_requires_authentication(self):
        with self.make_client() as client:
            response = client.get("/api/hall-types", headers={"X-API-Key": "bad-key"})

        self.assertEqual(response.status_code, 401)


class HallTypeTemplateResponsibilityTests(unittest.TestCase):
    """R1-2：软预设模板按任务职责描述，不出现固定“决策/执行”分级。"""

    def test_no_template_text_mentions_fixed_decision_tier(self):
        serialized = json.dumps(HALL_TYPE_TEMPLATES, ensure_ascii=False)
        self.assertNotIn("decision_tier", serialized)
        for forbidden in ("决策人", "决策 Agent", "执行 Agent", "decision Agent", "execution Agent"):
            self.assertNotIn(forbidden, serialized)

    def test_task_template_describes_initiator_and_assigned_members(self):
        guidance = HALL_TYPE_TEMPLATES["task"]["protocol_guidance"]
        # 发起者/需求方驱动拆解/分派/验收/收口
        for token in ("发起者", "拆解", "分派", "验收", "收口"):
            self.assertIn(token, guidance)
        # 被分派成员认领切片并回报
        for token in ("分派", "认领", "汇报"):
            self.assertIn(token, guidance)

    def test_brainstorm_and_review_close_by_responsibility(self):
        for hall_type in ("brainstorm", "review"):
            guidance = HALL_TYPE_TEMPLATES[hall_type]["protocol_guidance"]
            self.assertIn("发起人", guidance)
            self.assertIn("escalate_to_human", guidance)
            self.assertIn("收口", guidance)
            self.assertIn("decision", guidance)
            self.assertNotIn("决策人", guidance)

    def test_roles_entries_stay_duty_based_without_tier_fields(self):
        for template in HALL_TYPE_TEMPLATES.values():
            for role in template["roles"]:
                self.assertEqual(set(role), {"role", "norm"})
                for value in role.values():
                    self.assertNotIn("decision_tier", str(value))
                    self.assertNotIn("决策人", str(value))


class HallTypeMigrationTests(unittest.TestCase):
    def test_init_db_adds_group_type_to_existing_schema(self):
        tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        tmp_root.mkdir(parents=True, exist_ok=True)
        tmpdir = Path(tempfile.mkdtemp(prefix="talk-migration-", dir=tmp_root))
        engine = create_engine(
            f"sqlite:///{tmpdir / 'talk.db'}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        old_engine = db.engine
        db.engine = engine
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    """
                    CREATE TABLE groups (
                      id TEXT PRIMARY KEY,
                      name TEXT NOT NULL,
                      description TEXT,
                      created_by TEXT NOT NULL,
                      created_at TIMESTAMP NOT NULL,
                      updated_at TIMESTAMP NOT NULL
                    )
                    """
                )
                conn.exec_driver_sql(
                    """
                    INSERT INTO groups (id, name, description, created_by, created_at, updated_at)
                    VALUES ('group:old', '旧群', NULL, 'human:bobo', '2026-06-24 00:00:00', '2026-06-24 00:00:00')
                    """
                )

            db.init_db()

            with engine.connect() as conn:
                columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(groups)").fetchall()}
                hall_type = conn.exec_driver_sql("SELECT type FROM groups WHERE id = 'group:old'").scalar_one()
                indexes = {row[1] for row in conn.exec_driver_sql("PRAGMA index_list(groups)").fetchall()}

            self.assertIn("type", columns)
            self.assertEqual(hall_type, "free")
            self.assertIn("ix_groups_type", indexes)
        finally:
            db.engine = old_engine
            engine.dispose()
            shutil.rmtree(tmpdir, ignore_errors=True)
