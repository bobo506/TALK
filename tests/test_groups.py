from tests.test_support import RouteTestCase


class GroupRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")
        self.add_member("agent:other", api_key="other-key", display_name="Other")

    def test_human_creates_group_and_agents_only_list_joined_groups(self):
        with self.make_client() as client:
            created = client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "id": "group:lab",
                    "name": "Local Lab",
                    "description": "Agent discussion room",
                    "member_ids": ["agent:codex"],
                },
            )
            human_groups = client.get("/api/groups", headers={"X-API-Key": "alice-key"})
            codex_groups = client.get("/api/groups", headers={"X-API-Key": "codex-key"})
            other_groups = client.get("/api/groups", headers={"X-API-Key": "other-key"})

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["id"], "group:lab")
        self.assertEqual(
            {member["member_id"]: member["role"] for member in created.json()["members"]},
            {"human:bobo": "owner", "agent:codex": "member"},
        )
        self.assertEqual([group["id"] for group in human_groups.json()], ["group:lab"])
        self.assertEqual([group["id"] for group in codex_groups.json()], ["group:lab"])
        self.assertEqual(other_groups.json(), [])

    def test_human_can_add_update_and_remove_group_members(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab"},
            )
            added = client.put(
                "/api/groups/group:lab/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "moderator"},
            )
            updated = client.put(
                "/api/groups/group:lab/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "member"},
            )
            removed = client.delete(
                "/api/groups/group:lab/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
            )
            codex_groups = client.get("/api/groups", headers={"X-API-Key": "codex-key"})

        self.assertEqual(added.status_code, 200)
        self.assertIn({"member_id": "agent:codex", "role": "moderator"}, [
            {"member_id": member["member_id"], "role": member["role"]}
            for member in added.json()["members"]
        ])
        self.assertEqual(updated.status_code, 200)
        self.assertIn({"member_id": "agent:codex", "role": "member"}, [
            {"member_id": member["member_id"], "role": member["role"]}
            for member in updated.json()["members"]
        ])
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(codex_groups.json(), [])

    def test_human_can_update_group_metadata(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab", "description": "Old"},
            )
            updated = client.patch(
                "/api/groups/group:lab",
                headers={"X-API-Key": "bobo-key"},
                json={"name": "Research Lab", "description": "New focus"},
            )
            fetched = client.get("/api/groups/group:lab", headers={"X-API-Key": "alice-key"})

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Research Lab")
        self.assertEqual(updated.json()["description"], "New focus")
        self.assertEqual(fetched.json()["name"], "Research Lab")

    def test_agent_cannot_update_group_metadata(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab", "member_ids": ["agent:codex"]},
            )
            updated = client.patch(
                "/api/groups/group:lab",
                headers={"X-API-Key": "codex-key"},
                json={"name": "Agent Lab"},
            )

        self.assertEqual(updated.status_code, 403)

    def test_group_can_be_associated_with_a_project_on_create(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_bike", "display_name": "自行车计划"},
            )
            created = client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:design", "name": "设计讨论", "project_id": "prj_bike"},
            )
            fetched = client.get("/api/groups/group:design", headers={"X-API-Key": "bobo-key"})

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["project_id"], "prj_bike")
        self.assertEqual(fetched.json()["project_id"], "prj_bike")

    def test_group_without_project_is_backward_compatible(self):
        with self.make_client() as client:
            created = client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:legacy", "name": "历史群"},
            )

        self.assertEqual(created.status_code, 201)
        self.assertIsNone(created.json()["project_id"])

    def test_group_create_rejects_unknown_project(self):
        with self.make_client() as client:
            created = client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:orphan", "name": "孤儿群", "project_id": "prj_ghost"},
            )

        self.assertEqual(created.status_code, 400)

    def test_agent_and_missing_member_cannot_manage_group_members(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab", "member_ids": ["agent:codex"]},
            )
            agent_update = client.put(
                "/api/groups/group:lab/members/agent:other",
                headers={"X-API-Key": "codex-key"},
                json={"role": "member"},
            )
            missing_member = client.put(
                "/api/groups/group:lab/members/agent:missing",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "member"},
            )
            invalid_role = client.put(
                "/api/groups/group:lab/members/agent:other",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "speaker"},
            )

        self.assertEqual(agent_update.status_code, 403)
        self.assertEqual(missing_member.status_code, 400)
        self.assertEqual(invalid_role.status_code, 422)
