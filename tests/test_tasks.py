from tests.test_support import RouteTestCase


class AgentTaskTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")
        self.add_member("agent:other", api_key="other-key", display_name="Other")

    def test_human_can_create_task_for_agent_and_agent_can_list_it(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "title": "Smoke",
                    "content": "Run the smoke task",
                },
            )
            agent_tasks = client.get(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                params={"status": "queued"},
            )
            other_tasks = client.get("/api/tasks", headers={"X-API-Key": "other-key"})

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["created_by"], "human:bobo")
        self.assertEqual(created.json()["status"], "queued")
        self.assertEqual([task["id"] for task in agent_tasks.json()], [created.json()["id"]])
        self.assertEqual(other_tasks.json(), [])

    def test_task_target_must_be_agent_member(self):
        with self.make_client() as client:
            missing = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:missing", "content": "hello"},
            )
            human = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "human:bobo", "content": "hello"},
            )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(human.status_code, 400)

    def test_agent_can_claim_own_task_and_instance_becomes_busy(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            claimed = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-1"},
            )
            instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"member_id": "agent:codex"},
            )

        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json()["status"], "running")
        self.assertEqual(claimed.json()["claimed_by"], "agent:codex")
        self.assertEqual(claimed.json()["instance_id"], "codex-1")
        self.assertEqual(instances.json()[0]["status"], "busy")
        self.assertEqual(instances.json()[0]["current_task_id"], str(created.json()["id"]))

    def test_human_and_wrong_agent_cannot_claim_task(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            human_claim = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "bobo-key"},
                json={},
            )
            other_claim = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "other-key"},
                json={},
            )

        self.assertEqual(human_claim.status_code, 403)
        self.assertEqual(other_claim.status_code, 403)

    def test_claim_rejects_instance_owned_by_another_agent(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/other-1",
                headers={"X-API-Key": "other-key"},
                json={"runtime": "pi", "status": "idle"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            response = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "other-1"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("another member", response.json()["detail"])

    def test_agent_can_complete_running_task_and_instance_returns_idle(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-1"},
            )
            result = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                content="Done",
            )
            completed = client.post(
                f"/api/tasks/{created.json()['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "result_message_id": result.id},
            )
            instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"member_id": "agent:codex"},
            )

        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["status"], "succeeded")
        self.assertEqual(completed.json()["result_message_id"], result.id)
        self.assertIsNotNone(completed.json()["finished_at"])
        self.assertEqual(instances.json()[0]["status"], "idle")
        self.assertIsNone(instances.json()[0]["current_task_id"])

    def test_failed_completion_requires_error_and_sets_instance_error(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-1"},
            )
            missing_error = client.post(
                f"/api/tasks/{created.json()['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "failed"},
            )
            failed = client.post(
                f"/api/tasks/{created.json()['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "failed", "last_error": "boom"},
            )
            instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"member_id": "agent:codex"},
            )

        self.assertEqual(missing_error.status_code, 422)
        self.assertEqual(failed.status_code, 200)
        self.assertEqual(failed.json()["status"], "failed")
        self.assertEqual(instances.json()[0]["status"], "error")
        self.assertEqual(instances.json()[0]["last_error"], "boom")
