import shutil
from pathlib import Path
from unittest.mock import patch

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

    # ── add-agent ────────────────────────────────────────────────────

    def test_member_dir_name_sanitizes_colon(self):
        self.assertEqual(talk.member_dir_name("agent:codex"), "agent_codex")
        self.assertEqual(talk.member_dir_name("agent:pi-kimi"), "agent_pi-kimi")
        self.assertEqual(talk.member_dir_name("human:bobo"), "human_bobo")

    def test_scaffold_agent_creates_sanitized_profile(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P")
        agent_dir = talk.scaffold_agent(root, "agent:codex")

        self.assertEqual(agent_dir.name, "agent_codex")
        for fname in ("IDENTITY.md", "SOUL.md", "USER.md", "MEMORY.md"):
            self.assertTrue((agent_dir / fname).exists(), f"missing {fname}")
        # the full member_id (with colon) is preserved inside the file content
        self.assertIn("agent:codex", (agent_dir / "IDENTITY.md").read_text(encoding="utf-8"))

    def test_scaffold_agent_requires_talk_dir(self):
        root = self._root()  # no `talk init` run
        with self.assertRaises(FileNotFoundError):
            talk.scaffold_agent(root, "agent:codex")

    def test_scaffold_agent_refuses_existing_without_force(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P")
        talk.scaffold_agent(root, "agent:codex")
        with self.assertRaises(FileExistsError):
            talk.scaffold_agent(root, "agent:codex")
        # force overwrites
        talk.scaffold_agent(root, "agent:codex", force=True)

    def test_cmd_add_agent(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P")
        rc = talk.main(["add-agent", "agent:pi-kimi", "--root", str(root)])
        self.assertEqual(rc, 0)
        self.assertTrue((root / ".talk" / "agents" / "agent_pi-kimi" / "SOUL.md").exists())

    def test_cmd_add_agent_without_init_returns_1(self):
        root = self._root()
        rc = talk.main(["add-agent", "agent:codex", "--root", str(root)])
        self.assertEqual(rc, 1)

    # ── create-group ─────────────────────────────────────────────────

    def test_create_group_against_server_with_project(self):
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_x", "display_name": "X"},
            )
            result = talk.create_group(
                "http://testserver",
                "bobo-key",
                name="设计讨论",
                project_id="prj_x",
                member_ids=["agent:codex"],
                http=client,
            )
        self.assertEqual(result["project_id"], "prj_x")
        self.assertIn("agent:codex", [m["member_id"] for m in result["members"]])

    def test_create_group_raises_on_unknown_project(self):
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        with self.make_client() as client:
            with self.assertRaises(RuntimeError):
                talk.create_group(
                    "http://testserver",
                    "bobo-key",
                    name="孤儿群",
                    project_id="prj_ghost",
                    http=client,
                )

    def test_cmd_create_group_updates_local_groups_yaml(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P", project_id="prj_local")

        fake_result = {
            "id": "group:abc",
            "name": "设计讨论",
            "project_id": "prj_local",
            "members": [{"member_id": "agent:codex"}, {"member_id": "human:bobo"}],
        }
        with patch.object(talk, "create_group", return_value=fake_result) as mocked:
            rc = talk.main(
                [
                    "create-group",
                    "--root", str(root),
                    "--name", "设计讨论",
                    "--members", "agent:codex",
                    "--key", "bobo-key",
                ]
            )

        self.assertEqual(rc, 0)
        # project_id defaulted from local project.yaml
        self.assertEqual(mocked.call_args.kwargs["project_id"], "prj_local")
        groups_doc = yaml.safe_load((root / ".talk" / "groups.yaml").read_text(encoding="utf-8"))
        self.assertEqual(groups_doc["groups"][0]["id"], "group:abc")
        self.assertEqual(
            [m["member_id"] for m in groups_doc["groups"][0]["members"]],
            ["agent:codex", "human:bobo"],
        )

    def test_cmd_create_group_requires_key(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P")
        rc = talk.main(["create-group", "--root", str(root), "--name", "X"])
        self.assertEqual(rc, 1)

    # ── sync ─────────────────────────────────────────────────────────

    def test_member_id_from_dir_name_restores_colon(self):
        self.assertEqual(talk.member_id_from_dir_name("agent_codex"), "agent:codex")
        self.assertEqual(talk.member_id_from_dir_name("agent_pi-kimi"), "agent:pi-kimi")
        self.assertEqual(talk.member_id_from_dir_name("human_bobo"), "human:bobo")

    def test_scan_agents_builds_sorted_index(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P")
        talk.scaffold_agent(root, "agent:pi")
        talk.scaffold_agent(root, "agent:codex")

        entries = talk.scan_agents(root)
        # sorted by member_id, colon restored from the sanitized dir name
        self.assertEqual([e["member_id"] for e in entries], ["agent:codex", "agent:pi"])
        codex = entries[0]
        # relative-to-root forward-slash paths (stable across OSes)
        self.assertEqual(codex["identity_path"], ".talk/agents/agent_codex/IDENTITY.md")
        self.assertEqual(codex["soul_path"], ".talk/agents/agent_codex/SOUL.md")
        self.assertEqual(codex["user_path"], ".talk/agents/agent_codex/USER.md")
        # MEMORY.md is surfaced as the memory_pointer
        self.assertEqual(codex["memory_pointer"], ".talk/agents/agent_codex/MEMORY.md")

    def test_scan_agents_marks_missing_files_none(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P")
        talk.scaffold_agent(root, "agent:codex")
        (root / ".talk" / "agents" / "agent_codex" / "USER.md").unlink()

        entry = talk.scan_agents(root)[0]
        self.assertIsNone(entry["user_path"])
        self.assertEqual(entry["identity_path"], ".talk/agents/agent_codex/IDENTITY.md")

    def test_scan_agents_empty_without_profiles(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P")  # only agents/README.md exists
        self.assertEqual(talk.scan_agents(root), [])

    def test_sync_project_against_server(self):
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        root = self._root()
        talk.scaffold_project(root, display_name="P", project_id="prj_sync", maintainer="human:bobo")
        talk.scaffold_agent(root, "agent:codex")
        talk.scaffold_agent(root, "agent:pi")

        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_sync", "display_name": "P"},
            )
            result = talk.sync_project(
                "http://testserver", "bobo-key", "prj_sync", talk.scan_agents(root), http=client
            )
            self.assertEqual([a["member_id"] for a in result], ["agent:codex", "agent:pi"])

            listed = client.get("/api/projects/prj_sync/agents", headers={"X-API-Key": "bobo-key"})
            self.assertEqual(
                [a["member_id"] for a in listed.json()], ["agent:codex", "agent:pi"]
            )
            self.assertEqual(
                listed.json()[0]["identity_path"], ".talk/agents/agent_codex/IDENTITY.md"
            )

    def test_sync_project_is_full_replace(self):
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        root = self._root()
        talk.scaffold_project(root, display_name="P", project_id="prj_fr", maintainer="human:bobo")
        talk.scaffold_agent(root, "agent:codex")
        talk.scaffold_agent(root, "agent:pi")

        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_fr", "display_name": "P"},
            )
            talk.sync_project("http://testserver", "bobo-key", "prj_fr", talk.scan_agents(root), http=client)
            # drop one profile locally, re-sync → server mirrors the local state
            shutil.rmtree(root / ".talk" / "agents" / "agent_pi")
            result = talk.sync_project(
                "http://testserver", "bobo-key", "prj_fr", talk.scan_agents(root), http=client
            )
            self.assertEqual([a["member_id"] for a in result], ["agent:codex"])

    def test_sync_project_raises_on_error(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P", project_id="prj_ghost")
        with self.make_client() as client:
            with self.assertRaises(RuntimeError):
                talk.sync_project(
                    "http://testserver", "bobo-key", "prj_ghost", talk.scan_agents(root), http=client
                )

    def test_cmd_sync_defaults_project_from_yaml(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P", project_id="prj_local")
        talk.scaffold_agent(root, "agent:codex")

        fake_result = [{"member_id": "agent:codex"}]
        with patch.object(talk, "sync_project", return_value=fake_result) as mocked:
            rc = talk.main(["sync", "--root", str(root), "--key", "bobo-key"])

        self.assertEqual(rc, 0)
        # project_id defaulted from local project.yaml; scanned agents passed through
        self.assertEqual(mocked.call_args.args[2], "prj_local")
        passed_agents = mocked.call_args.args[3]
        self.assertEqual([a["member_id"] for a in passed_agents], ["agent:codex"])

    def test_cmd_sync_requires_key(self):
        root = self._root()
        talk.scaffold_project(root, display_name="P")
        rc = talk.main(["sync", "--root", str(root)])
        self.assertEqual(rc, 1)

    def test_cmd_sync_without_init_returns_1(self):
        root = self._root()  # no `talk init`
        rc = talk.main(["sync", "--root", str(root), "--key", "k"])
        self.assertEqual(rc, 1)
