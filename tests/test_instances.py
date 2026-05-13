from tests.test_support import RouteTestCase


class AgentInstanceTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")
        self.add_member("agent:other", api_key="other-key", display_name="Other")

    def test_agent_can_upsert_own_instance_status(self):
        with self.make_client() as client:
            created = client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={
                    "runtime": "codex",
                    "status": "idle",
                    "host": "test-host",
                    "pid": 1234,
                },
            )
            updated = client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={
                    "runtime": "codex",
                    "status": "busy",
                    "current_task_id": "42",
                },
            )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["member_id"], "agent:codex")
        self.assertEqual(created.json()["status"], "idle")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "busy")
        self.assertEqual(updated.json()["current_task_id"], "42")

    def test_human_cannot_report_instance_status(self):
        with self.make_client() as client:
            response = client.put(
                "/api/instances/human-1",
                headers={"X-API-Key": "bobo-key"},
                json={"runtime": "manual", "status": "idle"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("only agent", response.json()["detail"])

    def test_agent_cannot_take_over_other_agent_instance(self):
        with self.make_client() as client:
            created = client.put(
                "/api/instances/shared-id",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            takeover = client.put(
                "/api/instances/shared-id",
                headers={"X-API-Key": "other-key"},
                json={"runtime": "other", "status": "idle"},
            )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(takeover.status_code, 403)
        self.assertIn("another member", takeover.json()["detail"])

    def test_authenticated_members_can_list_instances_with_filters(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            client.put(
                "/api/instances/other-1",
                headers={"X-API-Key": "other-key"},
                json={"runtime": "pi", "status": "busy"},
            )
            all_instances = client.get("/api/instances", headers={"X-API-Key": "bobo-key"})
            codex_instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"member_id": "agent:codex"},
            )
            busy_instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"status": "busy"},
            )

        self.assertEqual(all_instances.status_code, 200)
        self.assertEqual({item["id"] for item in all_instances.json()}, {"codex-1", "other-1"})
        self.assertEqual([item["id"] for item in codex_instances.json()], ["codex-1"])
        self.assertEqual([item["id"] for item in busy_instances.json()], ["other-1"])

    def test_invalid_status_is_rejected(self):
        with self.make_client() as client:
            response = client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "sleeping"},
            )

        self.assertEqual(response.status_code, 422)
