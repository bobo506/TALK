"""351-C：准备流程把官方支持清单落库到绑定（catalog 来源）。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

import server.db as db
from server import kimi_native_setup
from server.models import ProjectRoleBinding


class EffortCapabilityRecordingTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix="talk-effort-record-")
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "record.db"
        self.engine = create_engine(
            f"sqlite:///{path}", echo=False, connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(self.engine)
        self._old_engine = db.engine
        db.engine = self.engine
        self.addCleanup(self._restore)
        with Session(self.engine) as session:
            session.add(
                ProjectRoleBinding(
                    project_id="prj_effort_record",
                    member_id="agent:worker",
                    runner_id="runner:codex",
                    model_source="builtin",
                    provider_id="openai",
                    connection_ref="native-codex-chatgpt-login",
                    model_id="gpt-6.1-sol",
                    updated_by="human:bobo",
                )
            )
            session.commit()

    def _restore(self):
        db.engine = self._old_engine
        self.engine.dispose()

    def row(self):
        with Session(self.engine) as session:
            return session.get(ProjectRoleBinding, ("prj_effort_record", "agent:worker"))

    def test_default_and_catalog_list_are_recorded_together(self):
        kimi_native_setup._record_default_effort(
            "prj_effort_record", "agent:worker", "high", ["medium", "high"]
        )
        row = self.row()
        self.assertEqual(row.default_effort, "high")
        self.assertEqual(row.supported_efforts, '["medium", "high"]')

    def test_catalog_list_is_canonical_and_unknown_values_are_dropped(self):
        kimi_native_setup._record_default_effort(
            "prj_effort_record", "agent:worker", "high", ["high", "turbo", "low", "low"]
        )
        self.assertEqual(self.row().supported_efforts, '["low", "high"]')

    def test_missing_catalog_keeps_column_null_instead_of_guessing(self):
        kimi_native_setup._record_default_effort("prj_effort_record", "agent:worker", "low", None)
        row = self.row()
        self.assertEqual(row.default_effort, "low")
        self.assertIsNone(row.supported_efforts)
        # 换模型/重新准备时旧清单不能留着冒充新模型能力。
        kimi_native_setup._record_default_effort(
            "prj_effort_record", "agent:worker", "high", ["high"]
        )
        self.assertEqual(self.row().supported_efforts, '["high"]')
        kimi_native_setup._record_default_effort("prj_effort_record", "agent:worker", None, None)
        row = self.row()
        self.assertIsNone(row.default_effort)
        self.assertIsNone(row.supported_efforts)

    def test_missing_binding_row_is_skipped(self):
        kimi_native_setup._record_default_effort("prj_effort_record", "agent:ghost", "high", ["high"])
        self.assertIsNone(self.row().supported_efforts)  # 不创建行


class KimiCatalogParsingTests(unittest.TestCase):
    def test_support_efforts_are_canonical_and_filtered(self):
        from scripts.kimi_role_setup import canonical_support_efforts

        self.assertEqual(
            canonical_support_efforts(["high", "turbo", "low", "high", 3, None]),
            ["low", "high"],
        )
        self.assertEqual(canonical_support_efforts(["max", "minimal"]), ["minimal", "max"])
        self.assertEqual(canonical_support_efforts([]), [])
        self.assertEqual(canonical_support_efforts(["unknown"]), [])


if __name__ == "__main__":
    unittest.main()
