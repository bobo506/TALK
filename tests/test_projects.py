from urllib.parse import quote

from cli.profiles import member_dir_name
from tests.test_support import RouteTestCase


class ProjectRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")

    def register_profile_project(self, client, project_id: str = "prj_profile"):
        project_root = self._tmpdir / project_id
        project_root.mkdir(parents=True, exist_ok=True)
        response = client.post(
            "/api/projects",
            headers={"X-API-Key": "bobo-key"},
            json={
                "project_id": project_id,
                "display_name": project_id,
                "project_root_path": str(project_root),
            },
        )
        self.assertEqual(response.status_code, 201)
        return project_root

    def test_human_registers_project_and_anyone_can_read(self):
        with self.make_client() as client:
            created = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_bike",
                    "display_name": "自行车计划",
                    "description": "家庭自行车管理",
                    "project_root_path": "/home/bobo/projects/bike",
                },
            )
            listed = client.get("/api/projects", headers={"X-API-Key": "alice-key"})
            fetched = client.get("/api/projects/prj_bike", headers={"X-API-Key": "codex-key"})

        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["project_id"], "prj_bike")
        self.assertEqual(body["display_name"], "自行车计划")
        # maintainer defaults to the registering member
        self.assertEqual(body["maintainer_member_id"], "human:bobo")
        self.assertEqual([p["project_id"] for p in listed.json()], ["prj_bike"])
        self.assertEqual(fetched.json()["project_root_path"], "/home/bobo/projects/bike")

    def test_server_generates_project_id_when_omitted(self):
        with self.make_client() as client:
            created = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"display_name": "Untitled"},
            )

        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["project_id"].startswith("prj_"))

    def test_explicit_maintainer_must_exist(self):
        with self.make_client() as client:
            ok = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"display_name": "P1", "maintainer_member_id": "human:alice"},
            )
            missing = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"display_name": "P2", "maintainer_member_id": "human:ghost"},
            )

        self.assertEqual(ok.status_code, 201)
        self.assertEqual(ok.json()["maintainer_member_id"], "human:alice")
        self.assertEqual(missing.status_code, 400)

    def test_duplicate_project_id_conflicts(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_dup", "display_name": "First"},
            )
            again = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_dup", "display_name": "Second"},
            )

        self.assertEqual(again.status_code, 409)

    def test_agent_cannot_register_update_or_delete(self):
        with self.make_client() as client:
            registered = client.post(
                "/api/projects",
                headers={"X-API-Key": "codex-key"},
                json={"project_id": "prj_x", "display_name": "X"},
            )
            # human creates one so agent has a target to attempt mutations on
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_y", "display_name": "Y"},
            )
            updated = client.patch(
                "/api/projects/prj_y",
                headers={"X-API-Key": "codex-key"},
                json={"display_name": "Hacked"},
            )
            deleted = client.delete(
                "/api/projects/prj_y",
                headers={"X-API-Key": "codex-key"},
            )

        self.assertEqual(registered.status_code, 403)
        self.assertEqual(updated.status_code, 403)
        self.assertEqual(deleted.status_code, 403)

    def test_partial_patch_only_touches_provided_fields(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_patch",
                    "display_name": "Old Name",
                    "description": "Keep me",
                    "project_root_path": "/old/path",
                },
            )
            updated = client.patch(
                "/api/projects/prj_patch",
                headers={"X-API-Key": "bobo-key"},
                json={"project_root_path": "/new/path"},
            )

        self.assertEqual(updated.status_code, 200)
        body = updated.json()
        self.assertEqual(body["project_root_path"], "/new/path")
        # untouched fields survive the partial patch
        self.assertEqual(body["display_name"], "Old Name")
        self.assertEqual(body["description"], "Keep me")

    def test_unregister_then_get_is_404(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_del", "display_name": "Bye"},
            )
            deleted = client.delete("/api/projects/prj_del", headers={"X-API-Key": "bobo-key"})
            fetched = client.get("/api/projects/prj_del", headers={"X-API-Key": "bobo-key"})

        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(fetched.status_code, 404)

    def test_list_project_groups_filters_by_project(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_a", "display_name": "A"},
            )
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:in", "name": "属于项目", "project_id": "prj_a"},
            )
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:out", "name": "无项目"},
            )
            listed = client.get("/api/projects/prj_a/groups", headers={"X-API-Key": "bobo-key"})
            missing = client.get("/api/projects/prj_ghost/groups", headers={"X-API-Key": "bobo-key"})

        self.assertEqual(listed.status_code, 200)
        self.assertEqual([g["id"] for g in listed.json()], ["group:in"])
        self.assertEqual(missing.status_code, 404)

    def test_list_project_groups_respects_agent_visibility(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_v", "display_name": "V"},
            )
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:joined", "name": "已入群", "project_id": "prj_v", "member_ids": ["agent:codex"]},
            )
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:other", "name": "未入群", "project_id": "prj_v"},
            )
            agent_view = client.get("/api/projects/prj_v/groups", headers={"X-API-Key": "codex-key"})

        self.assertEqual([g["id"] for g in agent_view.json()], ["group:joined"])

    def test_sync_then_list_agents(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_s", "display_name": "S"},
            )
            synced = client.post(
                "/api/projects/prj_s/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [
                    {"member_id": "agent:codex", "identity_path": ".talk/agents/agent_codex/IDENTITY.md",
                     "soul_path": ".talk/agents/agent_codex/SOUL.md"},
                    {"member_id": "agent:pi", "identity_path": ".talk/agents/agent_pi/IDENTITY.md"},
                ]},
            )
            listed = client.get("/api/projects/prj_s/agents", headers={"X-API-Key": "codex-key"})

        self.assertEqual(synced.status_code, 200)
        self.assertEqual([a["member_id"] for a in synced.json()], ["agent:codex", "agent:pi"])
        self.assertEqual(
            listed.json()[0]["soul_path"], ".talk/agents/agent_codex/SOUL.md"
        )
        self.assertEqual([a["member_id"] for a in listed.json()], ["agent:codex", "agent:pi"])
        for agent in synced.json():
            self.assertIsNone(agent["business_role"])
            self.assertIsNone(agent["decision_tier"])
            self.assertEqual(agent["capability_summary"], [])
            self.assertEqual(agent["availability"], "offline")
            self.assertEqual(agent["instances"], [])
        for agent in listed.json():
            self.assertIsNone(agent["business_role"])
            self.assertIsNone(agent["decision_tier"])
            self.assertEqual(agent["capability_summary"], [])
            self.assertEqual(agent["availability"], "offline")
            self.assertEqual(agent["instances"], [])

    def test_sync_and_list_agents_return_role_capability_and_live_availability(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_roles", "display_name": "Roles"},
            )
            instance = client.put(
                "/api/instances/codex-reviewer",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            synced = client.post(
                "/api/projects/prj_roles/sync",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "agents": [
                        {
                            "member_id": "agent:codex",
                            "business_role": "reviewer",
                            "decision_tier": "decision",
                            "capability_summary": ["代码审查", "风险分析"],
                        }
                    ]
                },
            )
            listed = client.get(
                "/api/projects/prj_roles/agents",
                headers={"X-API-Key": "codex-key"},
            )

        self.assertEqual(instance.status_code, 200)
        self.assertEqual(synced.status_code, 200)
        self.assertEqual(listed.status_code, 200)
        for payload in (synced.json()[0], listed.json()[0]):
            self.assertEqual(payload["business_role"], "reviewer")
            self.assertEqual(payload["decision_tier"], "decision")
            self.assertEqual(payload["capability_summary"], ["代码审查", "风险分析"])
            self.assertEqual(payload["availability"], "available")
            self.assertEqual(
                [(item["id"], item["status"]) for item in payload["instances"]],
                [("codex-reviewer", "idle")],
            )

    def test_sync_is_full_replace(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_r", "display_name": "R"},
            )
            client.post(
                "/api/projects/prj_r/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": "agent:codex"}, {"member_id": "agent:pi"}]},
            )
            replaced = client.post(
                "/api/projects/prj_r/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": "agent:pi"}]},
            )

        self.assertEqual([a["member_id"] for a in replaced.json()], ["agent:pi"])

    def test_sync_unknown_project_404(self):
        with self.make_client() as client:
            res = client.post(
                "/api/projects/prj_ghost/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": []},
            )
        self.assertEqual(res.status_code, 404)

    def test_agent_cannot_sync(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_a2", "display_name": "A2"},
            )
            res = client.post(
                "/api/projects/prj_a2/sync",
                headers={"X-API-Key": "codex-key"},
                json={"agents": []},
            )
        self.assertEqual(res.status_code, 403)

    def test_sync_rejects_duplicate_member(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_d", "display_name": "D"},
            )
            res = client.post(
                "/api/projects/prj_d/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": "agent:pi"}, {"member_id": "agent:pi"}]},
            )
        self.assertEqual(res.status_code, 422)

    def test_list_agents_empty_when_unsynced(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_e", "display_name": "E"},
            )
            listed = client.get("/api/projects/prj_e/agents", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(listed.json(), [])

    def test_agent_profile_get_returns_nulls_when_files_are_missing(self):
        with self.make_client() as client:
            self.register_profile_project(client)
            response = client.get(
                "/api/projects/prj_profile/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "project_id": "prj_profile",
                "member_id": "agent:codex",
                "identity": None,
                "soul": None,
                "user": None,
            },
        )

    def test_agent_profile_put_round_trips_and_writes_files(self):
        with self.make_client() as client:
            project_root = self.register_profile_project(client)
            written = client.put(
                "/api/projects/prj_profile/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "identity": "# Codex\n工程执行者",
                    "soul": "# Soul\n稳健直接",
                    "user": "# User\nBobo",
                },
            )
            fetched = client.get(
                "/api/projects/prj_profile/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(written.status_code, 200)
        self.assertEqual(fetched.json()["identity"], "# Codex\n工程执行者")
        self.assertEqual(fetched.json()["soul"], "# Soul\n稳健直接")
        self.assertEqual(fetched.json()["user"], "# User\nBobo")

        profile_dir = project_root / ".talk" / "agents" / member_dir_name("agent:codex")
        self.assertEqual((profile_dir / "IDENTITY.md").read_text(encoding="utf-8"), "# Codex\n工程执行者")
        self.assertEqual((profile_dir / "SOUL.md").read_text(encoding="utf-8"), "# Soul\n稳健直接")
        self.assertEqual((profile_dir / "USER.md").read_text(encoding="utf-8"), "# User\nBobo")

    def test_agent_profile_put_only_touches_provided_fields(self):
        with self.make_client() as client:
            self.register_profile_project(client)
            client.put(
                "/api/projects/prj_profile/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "bobo-key"},
                json={"identity": "identity v1", "soul": "soul v1", "user": "user v1"},
            )
            updated = client.put(
                "/api/projects/prj_profile/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "bobo-key"},
                json={"soul": "soul v2"},
            )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["identity"], "identity v1")
        self.assertEqual(updated.json()["soul"], "soul v2")
        self.assertEqual(updated.json()["user"], "user v1")

    def test_agent_profile_project_without_root_path_returns_400(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_no_root", "display_name": "No Root"},
            )
            fetched = client.get(
                "/api/projects/prj_no_root/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "bobo-key"},
            )
            updated = client.put(
                "/api/projects/prj_no_root/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "bobo-key"},
                json={"soul": "new"},
            )

        self.assertEqual(fetched.status_code, 400)
        self.assertEqual(updated.status_code, 400)
        self.assertIn("project has no root path", fetched.json()["detail"])

    def test_agent_profile_path_traversal_returns_400_without_writing(self):
        bad_member_id = "agent:../../evil"
        encoded_member_id = quote(bad_member_id, safe="")
        with self.make_client() as client:
            project_root = self.register_profile_project(client)
            response = client.put(
                f"/api/projects/prj_profile/agents/{encoded_member_id}/profile",
                headers={"X-API-Key": "bobo-key"},
                json={"identity": "escape"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "profile path escapes project")
        self.assertFalse((project_root / ".talk" / "evil" / "IDENTITY.md").exists())

    def test_agent_cannot_read_or_write_agent_profile(self):
        with self.make_client() as client:
            self.register_profile_project(client)
            fetched = client.get(
                "/api/projects/prj_profile/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "codex-key"},
            )
            updated = client.put(
                "/api/projects/prj_profile/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "codex-key"},
                json={"soul": "hacked"},
            )

        self.assertEqual(fetched.status_code, 403)
        self.assertEqual(updated.status_code, 403)

    def test_validation_rejects_bad_input(self):
        with self.make_client() as client:
            no_name = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"display_name": "   "},
            )
            spaced_id = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj bad", "display_name": "Spaced"},
            )

        self.assertEqual(no_name.status_code, 422)
        self.assertEqual(spaced_id.status_code, 422)
