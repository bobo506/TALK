from pathlib import Path

import yaml

from cli import talk
from tests.test_support import RouteTestCase


class TalkCliTests(RouteTestCase):
    def _root(self) -> Path:
        root = self._tmpdir / "proj"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_scaffold_creates_talk_dir(self):
        root = self._root()
        meta = talk.scaffold_project(root, display_name="自行车计划", server_url="http://x:8000")

        talk_dir = root / ".talk"
        for rel in ("project.yaml", "AGENTS.md", "groups.yaml", "agents/README.md", ".gitignore"):
            self.assertTrue((talk_dir / rel).exists(), f"missing {rel}")

        loaded = yaml.safe_load((talk_dir / "project.yaml").read_text(encoding="utf-8"))
        self.assertEqual(loaded["display_name"], "自行车计划")
        self.assertEqual(loaded["talk_server"], "http://x:8000")
        self.assertTrue(loaded["project_id"].startswith("prj_"))
        self.assertEqual(meta["project_id"], loaded["project_id"])

        groups_doc = yaml.safe_load((talk_dir / "groups.yaml").read_text(encoding="utf-8"))
        self.assertEqual(groups_doc, {"groups": []})
        self.assertIn("memory/", (talk_dir / ".gitignore").read_text(encoding="utf-8"))

    def test_default_group_is_optional(self):
        root = self._root()
        talk.scaffold_project(root, display_name="Bike", create_default_group=True)
        groups_doc = yaml.safe_load((root / ".talk" / "groups.yaml").read_text(encoding="utf-8"))
        self.assertEqual(groups_doc["groups"][0]["id"], "group:default")

    def test_scaffold_refuses_existing_without_force(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P1")
        with self.assertRaises(FileExistsError):
            talk.scaffold_project(root, display_name="P1")
        # force overwrites project.yaml content
        talk.scaffold_project(root, display_name="P2", force=True)
        loaded = yaml.safe_load((root / ".talk" / "project.yaml").read_text(encoding="utf-8"))
        self.assertEqual(loaded["display_name"], "P2")

    def test_generate_project_id_format(self):
        pid = talk.generate_project_id()
        self.assertTrue(pid.startswith("prj_"))
        self.assertEqual(len(pid), len("prj_") + 12)

    def test_register_project_against_server(self):
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        root = self._root()
        meta = talk.scaffold_project(root, display_name="Bike", maintainer="human:bobo")

        with self.make_client() as client:
            result = talk.register_project(
                "http://testserver",
                "bobo-key",
                {**meta, "project_root_path": str(root)},
                http=client,
            )

        self.assertEqual(result["project_id"], meta["project_id"])
        self.assertEqual(result["maintainer_member_id"], "human:bobo")
        self.assertEqual(result["project_root_path"], str(root))

    def test_register_project_raises_on_error(self):
        # no member registered → server rejects with 422 (validation) or 400; either way non-2xx
        root = self._root()
        meta = talk.scaffold_project(root, display_name="Bike", maintainer="human:ghost")
        with self.make_client() as client:
            with self.assertRaises(RuntimeError):
                talk.register_project(
                    "http://testserver",
                    "missing-key",
                    {**meta, "project_root_path": str(root)},
                    http=client,
                )

    def test_cmd_init_no_register(self):
        root = self._root()
        rc = talk.main(["init", "--root", str(root), "--name", "Demo", "--no-register"])
        self.assertEqual(rc, 0)
        self.assertTrue((root / ".talk" / "project.yaml").exists())

    def test_cmd_init_refuses_existing(self):
        root = self._root()
        talk.scaffold_project(root, display_name="Exists")
        rc = talk.main(["init", "--root", str(root), "--no-register"])
        self.assertEqual(rc, 1)
