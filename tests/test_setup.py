from tests.test_support import RouteTestCase


class SetupTests(RouteTestCase):
    def test_setup_status_requires_first_human_even_if_agents_exist(self):
        self.add_member("agent:demo", api_key="agent-key")

        with self.make_client() as client:
            response = client.get("/api/setup/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"needs_setup": True})

    def test_first_human_can_be_created_and_used_immediately(self):
        payload = {
            "id": "human:bobo",
            "display_name": "Bobo",
            "api_key": "bobo-key",
        }

        with self.make_client() as client:
            create_response = client.post("/api/members", json=payload)
            me_response = client.get(
                "/api/members/me",
                headers={"X-API-Key": payload["api_key"]},
            )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["id"], payload["id"])
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["id"], payload["id"])

    def test_setup_status_turns_off_after_first_human_exists(self):
        self.add_member("human:bobo", api_key="bobo-key")

        with self.make_client() as client:
            response = client.get("/api/setup/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"needs_setup": False})
