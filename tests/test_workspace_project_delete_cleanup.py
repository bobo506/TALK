"""Project deletion cleans workspace metadata in an isolated database."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

import server.db as db
import server.main as main
from server.db import get_session
from server.models import (Member, Project, WorkspaceOperation,
                           WorkspaceRegistration, WorkspaceRelinkPreview)


class WorkspaceProjectDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "test.sqlite"
        self.engine = create_engine("sqlite:///" + path.as_posix(),
                                    connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add(Member(id="human:test", kind="human", display_name="Test", api_key="test-key"))
            for project_id in ("target", "other"):
                session.add(Project(project_id=project_id, display_name=project_id,
                                    maintainer_member_id="human:test"))
            session.commit()

        def override():
            with Session(self.engine) as session:
                yield session

        main.app.dependency_overrides[get_session] = override
        self.addCleanup(main.app.dependency_overrides.pop, get_session, None)
        patch = mock.patch.object(db, "AUTH_MODE", "key")
        patch.start()
        self.addCleanup(patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def seed(self, project_id, stages):
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            session.add(WorkspaceRegistration(project_id=project_id))
            session.add(WorkspaceRelinkPreview(token="token-" + project_id,
                project_id=project_id, actor_member_id="human:test", candidate_root="sample",
                candidate_identity="sample", expected_revision=1, created_at=now,
                expires_at=now + timedelta(hours=1)))
            for index, stage in enumerate(stages):
                session.add(WorkspaceOperation(operation_id=f"{project_id}-{index}",
                    project_id=project_id, request_digest="sample", stage=stage))
            session.commit()

    def snapshot(self, project_id):
        with self.engine.connect() as connection:
            rows = {}
            for table in ("workspace_operations", "workspace_relink_previews", "workspace_registrations"):
                rows[table] = connection.execute(text(f"SELECT * FROM {table} WHERE project_id = :id"),
                                                  {"id": project_id}).all()
            rows["projects"] = connection.execute(text("SELECT * FROM projects WHERE project_id = :id"),
                                                   {"id": project_id}).all()
            return rows

    def delete(self):
        return self.client.delete("/api/projects/target", headers={"X-API-Key": "test-key"})

    def test_terminal_operations_cleanup_and_other_project_preserved(self):
        self.seed("target", ["completed", "failed"])
        self.seed("other", ["prepared"])
        before = self.snapshot("target")
        other = self.snapshot("other")
        response = self.delete()
        after = self.snapshot("target")
        print("SCENARIO terminal status=", response.status_code, "before=", {k: len(v) for k, v in before.items()},
              "after=", {k: len(v) for k, v in after.items()}, flush=True)
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual({k: len(v) for k, v in before.items()},
                         {"workspace_operations": 2, "workspace_relink_previews": 1,
                          "workspace_registrations": 1, "projects": 1})
        self.assertTrue(all(not rows for rows in after.values()))
        self.assertEqual(self.snapshot("other"), other)

    def test_active_operations_leave_everything_untouched(self):
        for stage in ("prepared", "recovery_required"):
            with self.subTest(stage=stage):
                self.seed("target", [stage])
                before = self.snapshot("target")
                response = self.delete()
                after = self.snapshot("target")
                print("SCENARIO", stage, "status=", response.status_code, "body=", response.json(),
                      "before=", {k: len(v) for k, v in before.items()},
                      "after=", {k: len(v) for k, v in after.items()}, flush=True)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["detail"], "workspace_busy")
                self.assertEqual(after, before)
                with Session(self.engine) as session:
                    for model in (WorkspaceOperation, WorkspaceRelinkPreview, WorkspaceRegistration):
                        for row in session.query(model).filter(model.project_id == "target").all():
                            session.delete(row)
                    session.commit()

    def test_no_workspace_rows(self):
        before = self.snapshot("target")
        response = self.delete()
        after = self.snapshot("target")
        print("SCENARIO empty status=", response.status_code, "before=", {k: len(v) for k, v in before.items()},
              "after=", {k: len(v) for k, v in after.items()}, flush=True)
        self.assertEqual(response.status_code, 204, response.text)
        self.assertTrue(all(not rows for rows in after.values()))

    def test_cleanup_error_rolls_back_prior_deletes(self):
        self.seed("target", ["completed"])
        before = self.snapshot("target")
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TRIGGER fail_preview_delete BEFORE DELETE ON workspace_relink_previews "
                                       "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(Exception):
            self.delete()
        self.assertEqual(self.snapshot("target"), before)


if __name__ == "__main__":
    unittest.main()
