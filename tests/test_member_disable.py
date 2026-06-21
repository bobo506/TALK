"""UI #3: global enable/disable of agent members (soft delete + auth rejection)."""

from tests.test_support import RouteTestCase


class MemberDisableTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")

    def test_human_can_disable_then_enable_agent(self):
        with self.make_client() as client:
            # before: agent can authenticate
            self.assertEqual(client.get("/api/members/me", headers={"X-API-Key": "codex-key"}).status_code, 200)

            disabled = client.patch(
                "/api/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
                json={"disabled": True},
            )
            self.assertEqual(disabled.status_code, 200)
            self.assertIsNotNone(disabled.json()["disabled_at"])

            # disabled agent is rejected at auth (403) on any authed endpoint
            self.assertEqual(client.get("/api/members/me", headers={"X-API-Key": "codex-key"}).status_code, 403)
            self.assertEqual(client.get("/api/groups", headers={"X-API-Key": "codex-key"}).status_code, 403)

            # human listing still shows the (disabled) agent with its flag
            listed = client.get("/api/members", headers={"X-API-Key": "bobo-key"}).json()
            codex = next(m for m in listed if m["id"] == "agent:codex")
            self.assertIsNotNone(codex["disabled_at"])

            # re-enable → agent can authenticate again
            enabled = client.patch(
                "/api/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
                json={"disabled": False},
            )
            self.assertEqual(enabled.status_code, 200)
            self.assertIsNone(enabled.json()["disabled_at"])
            self.assertEqual(client.get("/api/members/me", headers={"X-API-Key": "codex-key"}).status_code, 200)

    def test_agent_cannot_disable_members(self):
        with self.make_client() as client:
            res = client.patch(
                "/api/members/agent:codex",
                headers={"X-API-Key": "codex-key"},
                json={"disabled": True},
            )
        self.assertEqual(res.status_code, 403)

    def test_cannot_disable_human_member(self):
        with self.make_client() as client:
            res = client.patch(
                "/api/members/human:alice",
                headers={"X-API-Key": "bobo-key"},
                json={"disabled": True},
            )
        self.assertEqual(res.status_code, 400)

    def test_disable_missing_member_returns_404(self):
        with self.make_client() as client:
            res = client.patch(
                "/api/members/agent:ghost",
                headers={"X-API-Key": "bobo-key"},
                json={"disabled": True},
            )
        self.assertEqual(res.status_code, 404)
