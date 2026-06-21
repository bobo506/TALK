import json

from sqlmodel import select

from server.models import DiscussionSession, DiscussionTurn, GroupMember, Message
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

    def test_member_business_role_and_decision_tier_roundtrip(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab"},
            )
            added = client.put(
                "/api/groups/group:lab/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "member", "business_role": "lead", "decision_tier": "Decision"},
            )
            fetched = client.get("/api/groups/group:lab", headers={"X-API-Key": "bobo-key"})

        self.assertEqual(added.status_code, 200)
        codex = next(m for m in added.json()["members"] if m["member_id"] == "agent:codex")
        # business_role kept verbatim; decision_tier normalized to lowercase
        self.assertEqual(codex["business_role"], "lead")
        self.assertEqual(codex["decision_tier"], "decision")
        # owner (auto-added at create) has no collaboration role
        owner = next(m for m in added.json()["members"] if m["member_id"] == "human:bobo")
        self.assertIsNone(owner["business_role"])
        self.assertIsNone(owner["decision_tier"])
        # persisted across a fresh GET
        codex_get = next(m for m in fetched.json()["members"] if m["member_id"] == "agent:codex")
        self.assertEqual((codex_get["business_role"], codex_get["decision_tier"]), ("lead", "decision"))

    def test_put_member_full_replace_clears_collab_fields(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab"},
            )
            client.put(
                "/api/groups/group:lab/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "member", "business_role": "lead", "decision_tier": "decision"},
            )
            # a later PUT without the fields clears them (PUT = full replace)
            cleared = client.put(
                "/api/groups/group:lab/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "moderator"},
            )

        codex = next(m for m in cleared.json()["members"] if m["member_id"] == "agent:codex")
        self.assertEqual(codex["role"], "moderator")
        self.assertIsNone(codex["business_role"])
        self.assertIsNone(codex["decision_tier"])

    def test_invalid_decision_tier_rejected(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab"},
            )
            bad = client.put(
                "/api/groups/group:lab/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "member", "decision_tier": "boss"},
            )
        self.assertEqual(bad.status_code, 422)

    # ── delete group (UI #2) ─────────────────────────────────────────

    def test_human_can_delete_group_and_cascade(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab", "member_ids": ["agent:codex"]},
            )
        msg = self.add_message(
            from_id="agent:codex", to_ids=None, message_type="text",
            group_id="group:lab", content="hello",
        )
        with self.session() as s:
            disc = DiscussionSession(
                group_id="group:lab", created_by="human:bobo",
                topic="t", participant_ids=json.dumps(["agent:codex"]),
            )
            s.add(disc)
            s.commit()
            s.refresh(disc)
            disc_id = disc.id
            s.add(DiscussionTurn(
                session_id=disc_id, turn_index=0, message_id=msg.id,
                speaker_id="agent:codex", stance="answer",
            ))
            s.commit()

        with self.make_client() as client:
            deleted = client.delete("/api/groups/group:lab", headers={"X-API-Key": "bobo-key"})
            gone = client.get("/api/groups/group:lab", headers={"X-API-Key": "bobo-key"})

        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(gone.status_code, 404)
        # cascade: membership, messages, discussions and turns all gone
        with self.session() as s:
            self.assertEqual(s.exec(select(GroupMember).where(GroupMember.group_id == "group:lab")).all(), [])
            self.assertEqual(s.exec(select(Message).where(Message.group_id == "group:lab")).all(), [])
            self.assertEqual(s.exec(select(DiscussionSession).where(DiscussionSession.group_id == "group:lab")).all(), [])
            self.assertEqual(s.exec(select(DiscussionTurn).where(DiscussionTurn.session_id == disc_id)).all(), [])

    def test_agent_cannot_delete_group(self):
        with self.make_client() as client:
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:lab", "name": "Local Lab", "member_ids": ["agent:codex"]},
            )
            forbidden = client.delete("/api/groups/group:lab", headers={"X-API-Key": "codex-key"})
            still_there = client.get("/api/groups/group:lab", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(still_there.status_code, 200)

    def test_delete_missing_group_returns_404(self):
        with self.make_client() as client:
            missing = client.delete("/api/groups/group:ghost", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(missing.status_code, 404)

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
