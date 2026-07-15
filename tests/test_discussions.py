import json

import server.db as db
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

    def test_append_turn_accepts_decision_stance(self):
        message = self.add_message(
            from_id=self.agent_codex.id,
            to_ids=json.dumps([self.agent_pi.id]),
            group_id="group:lab",
            message_type="text",
            content="@agent:pi final call",
        )

        with self.make_client() as client:
            created = client.post(
                "/api/discussions",
                headers={"X-API-Key": "codex-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "decision stance",
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
                    "stance": "decision",
                    "round_index": 1,
                },
            )

        self.assertEqual(turn.status_code, 201)
        self.assertEqual(turn.json()["stance"], "decision")

    def test_update_discussion_end_reason_and_preserve_on_status_only_patch(self):
        with self.make_client() as client:
            created = client.post(
                "/api/discussions",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "end reason",
                    "participant_ids": ["agent:codex", "agent:pi"],
                },
            )
            self.assertEqual(created.status_code, 201)
            discussion_id = created.json()["id"]
            self.assertIsNone(created.json()["end_reason"])

            resolved = client.patch(
                f"/api/discussions/{discussion_id}",
                headers={"X-API-Key": "bobo-key"},
                json={"status": "resolved", "end_reason": "consensus"},
            )
            self.assertEqual(resolved.status_code, 200)
            self.assertEqual(resolved.json()["status"], "resolved")
            self.assertEqual(resolved.json()["end_reason"], "consensus")

            fetched = client.get(
                f"/api/discussions/{discussion_id}",
                headers={"X-API-Key": "bobo-key"},
            )
            self.assertEqual(fetched.status_code, 200)
            self.assertEqual(fetched.json()["end_reason"], "consensus")

            escalated = client.patch(
                f"/api/discussions/{discussion_id}",
                headers={"X-API-Key": "bobo-key"},
                json={"status": "escalated"},
            )

        self.assertEqual(escalated.status_code, 200)
        self.assertEqual(escalated.json()["status"], "escalated")
        self.assertEqual(escalated.json()["end_reason"], "consensus")

    def test_update_discussion_rejects_invalid_end_reason(self):
        with self.make_client() as client:
            created = client.post(
                "/api/discussions",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "group_id": "group:lab",
                    "topic": "bad end reason",
                    "participant_ids": ["agent:codex", "agent:pi"],
                },
            )
            self.assertEqual(created.status_code, 201)
            discussion_id = created.json()["id"]

            patched = client.patch(
                f"/api/discussions/{discussion_id}",
                headers={"X-API-Key": "bobo-key"},
                json={"status": "resolved", "end_reason": "bogus"},
            )

        self.assertEqual(patched.status_code, 422)

    def test_init_db_adds_end_reason_to_legacy_discussion_sessions(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE discussion_sessions")
            conn.exec_driver_sql(
                """
                CREATE TABLE discussion_sessions (
                    id INTEGER NOT NULL,
                    group_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    participant_ids TEXT NOT NULL,
                    root_message_id INTEGER,
                    requester_id TEXT,
                    assignee_id TEXT,
                    scope_text TEXT,
                    status TEXT NOT NULL,
                    max_rounds INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (id)
                )
                """
            )
            conn.exec_driver_sql(
                """
                INSERT INTO discussion_sessions (
                    id, group_id, created_by, topic, participant_ids, status,
                    max_rounds, created_at, updated_at
                ) VALUES (
                    1, 'group:lab', 'human:bobo', 'legacy', '["agent:codex","agent:pi"]',
                    'resolved', 2, '2026-06-28 00:00:00', '2026-06-28 00:00:00'
                )
                """
            )

        db.init_db()

        with self.engine.connect() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(discussion_sessions)").fetchall()}
            end_reason = conn.exec_driver_sql(
                "SELECT end_reason FROM discussion_sessions WHERE id = 1"
            ).scalar_one()

        self.assertIn("end_reason", columns)
        self.assertIsNone(end_reason)

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
