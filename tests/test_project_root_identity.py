import os
from pathlib import Path
from unittest import skipUnless

from server.models import Project
from tests.test_support import RouteTestCase


class ProjectRootIdentityTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:test", api_key="test-key")
        self.headers = {"X-API-Key": "test-key"}
        self.first = self._tmpdir / "first"
        self.second = self._tmpdir / "second"
        self.first.mkdir()
        self.second.mkdir()

    def create(self, client, project_id, root):
        return client.post("/api/projects", headers=self.headers, json={
            "project_id": project_id, "display_name": project_id, "project_root_path": root,
        })

    def test_create_valid_and_invalid_paths_do_not_write(self):
        file = self._tmpdir / "file"
        file.write_text("x", encoding="utf-8")
        with self.make_client() as client:
            result = self.create(client, "valid", str(self.first / ".." / "first"))
            self.assertEqual(result.status_code, 201, result.text)
            self.assertEqual(result.json()["project_root_path"], str(self.first.resolve()))
            for project_id, path, code in [("relative", "relative/path", "project_root_path_relative"),
                    ("missing", str(self._tmpdir / "missing"), "project_root_path_invalid"),
                    ("file", str(file), "project_root_path_invalid"),
                    ("duplicate", str(self.first), "project_root_path_conflict")]:
                response = self.create(client, project_id, path)
                self.assertEqual(response.status_code, 409 if project_id == "duplicate" else 422, response.text)
                self.assertEqual(response.json()["detail"], code)
            with self.session() as session:
                for project_id in ("relative", "missing", "file", "duplicate"):
                    self.assertIsNone(session.get(Project, project_id))

    @skipUnless(os.name == "nt", "Windows case-insensitive paths")
    def test_case_variant_and_existing_talk_root_conflict(self):
        talk_root = Path(r"D:\claude-test\TALK")
        self.assertTrue(talk_root.is_dir())
        with self.session() as session:
            session.add(Project(project_id="prj_e8fe7066bbec", display_name="TALK", project_root_path=str(talk_root), maintainer_member_id="human:test"))
            session.commit()
        with self.make_client() as client:
            result = self.create(client, "dup_talk", str(talk_root).swapcase())
            self.assertEqual(result.status_code, 409, result.text)
            self.assertEqual(result.json()["detail"], "project_root_path_conflict")
            self.assertEqual(self.create(client, "first", str(self.first)).status_code, 201)
            result = self.create(client, "dup_case", str(self.first).swapcase())
            self.assertEqual(result.status_code, 409, result.text)
            self.assertEqual(result.json()["detail"], "project_root_path_conflict")
        with self.session() as session:
            self.assertIsNone(session.get(Project, "dup_talk"))
            self.assertIsNone(session.get(Project, "dup_case"))

    def test_patch_root_and_atomic_failures(self):
        with self.make_client() as client:
            self.assertEqual(self.create(client, "one", str(self.first)).status_code, 201)
            self.assertEqual(self.create(client, "two", str(self.second)).status_code, 201)
            for value, status, detail in [(str(self.second), 409, "project_root_path_conflict"),
                                           (None, 422, "project_root_path_required"),
                                           ("  ", 422, "project_root_path_required")]:
                response = client.patch("/api/projects/one", headers=self.headers,
                                        json={"project_root_path": value, "display_name": "changed"})
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(response.json()["detail"], detail)
                with self.session() as session:
                    item = session.get(Project, "one")
                    self.assertEqual(item.display_name, "one")
                    self.assertEqual(item.project_root_path, str(self.first.resolve()))
            third = self._tmpdir / "third"
            third.mkdir()
            response = client.patch("/api/projects/one", headers=self.headers,
                                    json={"project_root_path": str(third / ".." / "third")})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["project_root_path"], str(third.resolve()))

    def test_omitted_path_does_not_validate_legacy(self):
        with self.session() as session:
            session.add(Project(project_id="legacy", display_name="old", project_root_path="relative-invalid", maintainer_member_id="human:test"))
            session.commit()
        with self.make_client() as client:
            result = client.patch("/api/projects/legacy", headers=self.headers, json={"display_name": "new"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["project_root_path"], "relative-invalid")
