from tests.test_support import RouteTestCase


class ProjectRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")

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
