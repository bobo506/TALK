import json

from tests.test_support import RouteTestCase
from server.models import Group, GroupMember


class DiscussionRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.agent_codex = self.add_member("agent:codex", api_key="codex-key", display_name="Codex")
        self.agent_pi = self.add_member("agent:pi", api_key="pi-key", display_name="pi")
        self.agent_other = self.add_member("agent:other", api_key="other-key", display_name="Other")
        with self.session() as session:
            session.add(Group(id="group:lab", name="Lab", created_by=self.human.id))
            session.add(GroupMember(group_id="group:lab", member_id=self.human.id, role="owner"))
            session.add(GroupMember(group_id="group:lab", member_id=self.agent_codex.id, role="member"))
            session.add(GroupMember(group_id="group:lab", member_id=self.agent_pi.id, role="member"))
            session.commit()

    def test_create_discussion_and_append_ordered_turns(self):
        first = self.add_message(
            from_id=self.agent_codex.id,
            to_ids=json.dumps([self.agent_pi.id]),
            group_id="group:lab",
            message_type="text",
            content="@agent:pi 下一步计划如下",
        )
        second = self.add_message(
            from_id=self.agent_pi.id,
            to_ids=json.dumps([self.agent_codex.id]),
            group_id="group:lab",
            message_type="text",
            content="@agent:codex 我有一个优化建议",
        )

        with self.make_client() as client:
            created = client.post(
                "/api/discussions",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "下一步开发计划",
                    "participant_ids": ["agent:codex", "agent:pi"],
                    "root_message_id": first.id,
                    "requester_id": "agent:codex",
                    "assignee_id": "agent:pi",
                    "scope_text": "下一步计划如下",
                    "max_rounds": 2,
                },
            )
            self.assertEqual(created.status_code, 201)
            discussion = created.json()
            self.assertEqual(discussion["participant_ids"], ["agent:codex", "agent:pi"])
            self.assertEqual(discussion["root_message_id"], first.id)
            self.assertEqual(discussion["requester_id"], "agent:codex")
            self.assertEqual(discussion["assignee_id"], "agent:pi")
            self.assertEqual(discussion["scope_text"], "下一步计划如下")

            codex_turn = client.post(
                f"/api/discussions/{discussion['id']}/turns",
                headers={"X-API-Key": "codex-key"},
                json={
                    "message_id": first.id,
                    "target_member_id": "agent:pi",
                    "stance": "greeting",
                    "round_index": 1,
                },
            )
            pi_turn = client.post(
                f"/api/discussions/{discussion['id']}/turns",
                headers={"X-API-Key": "pi-key"},
                json={
                    "message_id": second.id,
                    "target_member_id": "agent:codex",
                    "stance": "closure",
                    "round_index": 1,
                },
            )
            self.assertEqual(codex_turn.status_code, 201)
            self.assertEqual(pi_turn.status_code, 201)

            turns = client.get(
                f"/api/discussions/{discussion['id']}/turns",
                headers={"X-API-Key": "bobo-key"},
            )
            self.assertEqual(turns.status_code, 200)
            payload = turns.json()
            self.assertEqual([turn["turn_index"] for turn in payload], [1, 2])
            self.assertEqual([turn["message_id"] for turn in payload], [first.id, second.id])
            self.assertEqual([turn["stance"] for turn in payload], ["greeting", "closure"])
            self.assertEqual([turn["turn_kind"] for turn in payload], ["reply", "reply"])

    def test_append_turn_accepts_explicit_demand_kind(self):
        message = self.add_message(
            from_id=self.agent_codex.id,
            to_ids=json.dumps([self.agent_pi.id]),
            group_id="group:lab",
            message_type="text",
            content="@agent:pi 请确认接口方案",
        )

        with self.make_client() as client:
            created = client.post(
                "/api/discussions",
                headers={"X-API-Key": "codex-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "接口方案",
                    "participant_ids": ["agent:codex", "agent:pi"],
                    "root_message_id": message.id,
                },
            )
            self.assertEqual(created.status_code, 201)
            discussion_id = created.json()["id"]

            turn = client.post(
                f"/api/discussions/{discussion_id}/turns",
                headers={"X-API-Key": "codex-key"},
                json={
                    "message_id": message.id,
                    "target_member_id": "agent:pi",
                    "stance": "question",
                    "turn_kind": "demand",
                    "round_index": 2,
                },
            )

        self.assertEqual(turn.status_code, 201)
        payload = turn.json()
        self.assertEqual(payload["turn_kind"], "demand")
        self.assertEqual(payload["round_index"], 2)

    def test_non_group_member_cannot_create_or_read_discussion(self):
        with self.make_client() as client:
            created = client.post(
                "/api/discussions",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "协议讨论",
                    "participant_ids": ["agent:codex", "agent:pi"],
                },
            )
            self.assertEqual(created.status_code, 201)
            discussion_id = created.json()["id"]

            denied_create = client.post(
                "/api/discussions",
                headers={"X-API-Key": "other-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "越权讨论",
                    "participant_ids": ["agent:other"],
                },
            )
            denied_read = client.get(
                f"/api/discussions/{discussion_id}",
                headers={"X-API-Key": "other-key"},
            )

        self.assertEqual(denied_create.status_code, 403)
        self.assertEqual(denied_read.status_code, 403)

    def test_turn_message_must_belong_to_current_member_and_group(self):
        codex_message = self.add_message(
            from_id=self.agent_codex.id,
            to_ids=json.dumps([self.agent_pi.id]),
            group_id="group:lab",
            message_type="text",
            content="@agent:pi plan",
        )
        with self.make_client() as client:
            created = client.post(
                "/api/discussions",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "ownership check",
                    "participant_ids": ["agent:codex", "agent:pi"],
                },
            )
            discussion_id = created.json()["id"]
            wrong_owner = client.post(
                f"/api/discussions/{discussion_id}/turns",
                headers={"X-API-Key": "pi-key"},
                json={"message_id": codex_message.id, "stance": "answer"},
            )

        self.assertEqual(wrong_owner.status_code, 403)

    def test_scope_root_message_must_belong_to_discussion_group(self):
        global_message = self.add_message(
            from_id=self.agent_codex.id,
            to_ids=json.dumps([self.agent_pi.id]),
            group_id=None,
            message_type="text",
            content="@agent:pi outside group",
        )

        with self.make_client() as client:
            created = client.post(
                "/api/discussions",
                headers={"X-API-Key": "codex-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "bad scope",
                    "participant_ids": ["agent:codex", "agent:pi"],
                    "root_message_id": global_message.id,
                },
            )

        self.assertEqual(created.status_code, 400)
        self.assertEqual(created.json()["detail"], "root message is not in discussion group")
