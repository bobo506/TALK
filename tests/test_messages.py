import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from server.models import MessageCreate
from server.routes.messages import get_messages, send_message
from tests.test_support import RouteTestCase


class MessagesRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.agent_ai1 = self.add_member("agent:AI1", api_key="ai1-key", display_name="AI1")
        self.agent_ai2 = self.add_member("agent:AI2", api_key="ai2-key", display_name="AI2")

    def assert_presence(self, websocket, expected_ids: list[str]) -> None:
        event = websocket.receive_json()
        self.assertEqual(event["type"], "presence")
        self.assertEqual(event["payload"]["online_ids"], expected_ids)

    def assert_revoke(self, websocket) -> dict:
        event = websocket.receive_json()
        self.assertEqual(event["type"], "revoke")
        return event["payload"]

    def assert_message(self, websocket) -> dict:
        event = websocket.receive_json()
        self.assertEqual(event["type"], "message")
        return event["payload"]

    def test_leading_mentions_override_explicit_recipients(self):
        with self.session() as session:
            out = asyncio.run(
                send_message(
                    MessageCreate(
                        type="text",
                        content="@agent:AI1 hi there",
                        to=["agent:AI2"],
                    ),
                    current=self.human,
                    session=session,
                )
            )

        self.assertEqual(out.to, ["agent:AI1"])

        results = get_messages(
            since=0,
            before=None,
            to="agent:AI1",
            q=None,
            limit=10,
            _current=self.agent_ai1,
            session=self.session(),
        )
        self.assertEqual([msg.to for msg in results], [["agent:AI1"]])

    def test_invalid_leading_mention_is_rejected(self):
        with self.session() as session:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    send_message(
                        MessageCreate(
                            type="text",
                            content="@agent:UNKNOWN hi",
                        ),
                        current=self.human,
                        session=session,
                    )
                )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("invalid recipient mention", ctx.exception.detail)

    def test_history_before_and_search_cover_caption_and_filename(self):
        self.add_message(
            from_id=self.human.id,
            to_ids=None,
            message_type="text",
            content="alpha",
        )
        file_message = self.add_message(
            from_id=self.human.id,
            to_ids=json.dumps([self.agent_ai1.id]),
            message_type="file",
            content="report.zip",
            file_id="file-1",
            caption="build ready",
            filename="report.zip",
            size_bytes=3,
            mime="application/zip",
        )
        self.add_message(
            from_id=self.human.id,
            to_ids=None,
            message_type="text",
            content="gamma",
        )

        page = get_messages(
            since=0,
            before=3,
            to=None,
            q=None,
            limit=2,
            _current=self.agent_ai1,
            session=self.session(),
        )
        self.assertEqual([msg.id for msg in page], [1, 2])

        by_filename = get_messages(
            since=0,
            before=None,
            to=None,
            q="report",
            limit=10,
            _current=self.agent_ai1,
            session=self.session(),
        )
        self.assertEqual([msg.id for msg in by_filename], [file_message.id])

        by_caption = get_messages(
            since=0,
            before=None,
            to=None,
            q="build",
            limit=10,
            _current=self.agent_ai1,
            session=self.session(),
        )
        self.assertEqual([msg.id for msg in by_caption], [file_message.id])

    def test_history_hides_private_message_from_third_party(self):
        alice = self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        bob = self.add_member("human:bob", api_key="bob-key", display_name="Bob")
        charlie = self.add_member("human:charlie", api_key="charlie-key", display_name="Charlie")
        private = self.add_message(
            from_id=alice.id,
            to_ids=json.dumps([bob.id]),
            message_type="text",
            content="alice to bob only",
        )

        history = get_messages(
            since=0,
            before=None,
            to=None,
            q=None,
            limit=20,
            _current=charlie,
            session=self.session(),
        )

        self.assertNotIn(private.id, [msg.id for msg in history])

    def test_history_to_filter_cannot_escape_visibility(self):
        alice = self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        bob = self.add_member("human:bob", api_key="bob-key", display_name="Bob")
        charlie = self.add_member("human:charlie", api_key="charlie-key", display_name="Charlie")
        private = self.add_message(
            from_id=alice.id,
            to_ids=json.dumps([bob.id]),
            message_type="text",
            content="still private",
        )

        history = get_messages(
            since=0,
            before=None,
            to=bob.id,
            q=None,
            limit=20,
            _current=charlie,
            session=self.session(),
        )

        self.assertNotIn(private.id, [msg.id for msg in history])

    def test_broadcast_visible_to_all_members(self):
        alice = self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        bob = self.add_member("human:bob", api_key="bob-key", display_name="Bob")
        charlie = self.add_member("human:charlie", api_key="charlie-key", display_name="Charlie")
        broadcast = self.add_message(
            from_id=alice.id,
            to_ids=None,
            message_type="text",
            content="hello everyone",
        )

        bob_history = get_messages(
            since=0,
            before=None,
            to=None,
            q=None,
            limit=20,
            _current=bob,
            session=self.session(),
        )
        charlie_history = get_messages(
            since=0,
            before=None,
            to=None,
            q=None,
            limit=20,
            _current=charlie,
            session=self.session(),
        )

        self.assertIn(broadcast.id, [msg.id for msg in bob_history])
        self.assertIn(broadcast.id, [msg.id for msg in charlie_history])

    def test_to_filter_returns_pair_view_plus_broadcast_and_shared_group(self):
        alice = self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        bob = self.add_member("human:bob", api_key="bob-key", display_name="Bob")
        charlie = self.add_member("human:charlie", api_key="charlie-key", display_name="Charlie")

        alice_to_bob = self.add_message(
            from_id=alice.id,
            to_ids=json.dumps([bob.id]),
            message_type="text",
            content="alice direct to bob",
        )
        bob_to_alice = self.add_message(
            from_id=bob.id,
            to_ids=json.dumps([alice.id]),
            message_type="text",
            content="bob direct to alice",
        )
        broadcast = self.add_message(
            from_id=charlie.id,
            to_ids=None,
            message_type="text",
            content="broadcast to all",
        )
        shared_group = self.add_message(
            from_id=charlie.id,
            to_ids=json.dumps([alice.id, bob.id]),
            message_type="text",
            content="shared group context",
        )
        alice_only = self.add_message(
            from_id=charlie.id,
            to_ids=json.dumps([alice.id]),
            message_type="text",
            content="alice only context",
        )

        history = get_messages(
            since=0,
            before=None,
            to=alice.id,
            q=None,
            limit=20,
            _current=bob,
            session=self.session(),
        )

        visible_ids = [msg.id for msg in history]
        self.assertEqual(visible_ids, [alice_to_bob.id, bob_to_alice.id, broadcast.id, shared_group.id])
        self.assertNotIn(alice_only.id, visible_ids)

    def test_search_never_returns_invisible_messages(self):
        alice = self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        bob = self.add_member("human:bob", api_key="bob-key", display_name="Bob")
        charlie = self.add_member("human:charlie", api_key="charlie-key", display_name="Charlie")
        hidden = self.add_message(
            from_id=alice.id,
            to_ids=json.dumps([bob.id]),
            message_type="text",
            content="needle-visible-only-to-bob",
        )
        visible = self.add_message(
            from_id=alice.id,
            to_ids=None,
            message_type="text",
            content="needle-broadcast",
        )

        history = get_messages(
            since=0,
            before=None,
            to=None,
            q="needle",
            limit=20,
            _current=charlie,
            session=self.session(),
        )

        visible_ids = [msg.id for msg in history]
        self.assertIn(visible.id, visible_ids)
        self.assertNotIn(hidden.id, visible_ids)

    def test_sender_can_revoke_message_within_window_and_history_hides_payload(self):
        message = self.add_message(
            from_id=self.human.id,
            to_ids=json.dumps([self.agent_ai1.id]),
            message_type="text",
            content="secret hello",
        )

        with self.make_client() as client:
            response = client.post(
                f"/api/messages/{message.id}/revoke",
                headers={"X-API-Key": "bobo-key"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()

            history = client.get(
                "/api/messages",
                headers={"X-API-Key": "ai1-key"},
                params={"to": "agent:AI1"},
            )

        self.assertEqual(payload["id"], message.id)
        self.assertEqual(payload["revoked_by"], self.human.id)
        self.assertIsNotNone(payload["revoked_at"])

        revoked_message = history.json()[0]
        self.assertTrue(revoked_message["revoked"])
        self.assertEqual(revoked_message["type"], "text")
        self.assertIsNone(revoked_message["content"])
        self.assertIsNone(revoked_message["caption"])
        self.assertIsNone(revoked_message["filename"])

    def test_revoke_window_expired_returns_403(self):
        message = self.add_message(
            from_id=self.human.id,
            to_ids=None,
            message_type="text",
            content="too late",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=121),
        )

        with self.make_client() as client:
            response = client.post(
                f"/api/messages/{message.id}/revoke",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("revoke window expired", response.json()["detail"])

    def test_other_member_cannot_revoke_foreign_message(self):
        message = self.add_message(
            from_id=self.human.id,
            to_ids=None,
            message_type="text",
            content="hands off",
        )

        with self.make_client() as client:
            response = client.post(
                f"/api/messages/{message.id}/revoke",
                headers={"X-API-Key": "ai1-key"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "only sender can revoke message")

    def test_revoked_file_message_keeps_file_entity_and_hides_snapshot_fields(self):
        file_record = self.add_file(
            file_id="file-1",
            uploader_id=self.human.id,
            filename="report.zip",
            content=b"zip-data",
            mime="application/zip",
        )
        message = self.add_message(
            from_id=self.human.id,
            to_ids=json.dumps([self.agent_ai1.id]),
            message_type="file",
            content=file_record.filename,
            file_id=file_record.id,
            caption="latest build",
            filename=file_record.filename,
            size_bytes=file_record.size_bytes,
            mime=file_record.mime,
        )

        with self.make_client() as client:
            response = client.post(
                f"/api/messages/{message.id}/revoke",
                headers={"X-API-Key": "bobo-key"},
            )
            self.assertEqual(response.status_code, 200)

            history = client.get(
                "/api/messages",
                headers={"X-API-Key": "ai1-key"},
                params={"to": "agent:AI1"},
            )

        self.assertTrue((self.storage_dir / file_record.path).exists())
        revoked_message = history.json()[0]
        self.assertTrue(revoked_message["revoked"])
        self.assertEqual(revoked_message["type"], "file")
        self.assertEqual(revoked_message["file_id"], file_record.id)
        self.assertIsNone(revoked_message["content"])
        self.assertIsNone(revoked_message["caption"])
        self.assertIsNone(revoked_message["filename"])
        self.assertIsNone(revoked_message["size_bytes"])
        self.assertIsNone(revoked_message["mime"])

    def test_revoke_notifies_online_websocket_clients(self):
        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                with client.websocket_connect("/ws?token=ai1-key") as agent_ws:
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(human_ws, ["agent:AI1", "human:bobo"])

                    created = client.post(
                        "/api/messages",
                        headers={"X-API-Key": "bobo-key"},
                        json={"type": "text", "content": "@agent:AI1 hello then revoke"},
                    )
                    self.assertEqual(created.status_code, 201)
                    created_payload = created.json()

                    self.assertEqual(human_ws.receive_json()["type"], "message")
                    self.assertEqual(agent_ws.receive_json()["type"], "message")

                    revoked = client.post(
                        f"/api/messages/{created_payload['id']}/revoke",
                        headers={"X-API-Key": "bobo-key"},
                    )
                    self.assertEqual(revoked.status_code, 200)

                    human_revoke = self.assert_revoke(human_ws)
                    agent_revoke = self.assert_revoke(agent_ws)
                    self.assertEqual(human_revoke["id"], created_payload["id"])
                    self.assertEqual(agent_revoke["id"], created_payload["id"])
                    self.assertEqual(agent_revoke["revoked_by"], self.human.id)

    def test_reply_to_visible_message_succeeds(self):
        original = self.add_message(
            from_id=self.human.id,
            to_ids=json.dumps([self.agent_ai1.id]),
            message_type="text",
            content="context line for reply",
        )

        with self.make_client() as client:
            response = client.post(
                "/api/messages",
                headers={"X-API-Key": "ai1-key"},
                json={
                    "type": "text",
                    "content": "@human:bobo reply ack",
                    "reply_to": original.id,
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["reply_to"]["id"], original.id)
        self.assertEqual(payload["reply_to"]["from_id"], self.human.id)
        self.assertEqual(payload["reply_to"]["preview"], "context line for reply")
        self.assertFalse(payload["reply_to"]["revoked"])

    def test_reply_to_invisible_message_returns_400(self):
        hidden = self.add_message(
            from_id=self.human.id,
            to_ids=json.dumps([self.agent_ai2.id]),
            message_type="text",
            content="private to ai2",
        )

        with self.make_client() as client:
            response = client.post(
                "/api/messages",
                headers={"X-API-Key": "ai1-key"},
                json={
                    "type": "text",
                    "content": "cannot quote this",
                    "reply_to": hidden.id,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cannot_reply_to_invisible")

    def test_reply_to_revoked_message_returns_400(self):
        revoked = self.add_message(
            from_id=self.human.id,
            to_ids=json.dumps([self.agent_ai1.id]),
            message_type="text",
            content="temporary context",
            revoked_at=datetime.now(timezone.utc),
            revoked_by=self.human.id,
        )

        with self.make_client() as client:
            response = client.post(
                "/api/messages",
                headers={"X-API-Key": "ai1-key"},
                json={
                    "type": "text",
                    "content": "too late to quote",
                    "reply_to": revoked.id,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cannot_reply_to_revoked")

    def test_history_response_includes_reply_preview_and_revoked_marker(self):
        original = self.add_message(
            from_id=self.human.id,
            to_ids=json.dumps([self.agent_ai1.id]),
            message_type="text",
            content="A" * 120,
        )
        reply = self.add_message(
            from_id=self.agent_ai1.id,
            to_ids=json.dumps([self.human.id]),
            message_type="text",
            content="reply content",
            reply_to=original.id,
        )

        with self.make_client() as client:
            history = client.get(
                "/api/messages",
                headers={"X-API-Key": "bobo-key"},
                params={"since": 0},
            )

        self.assertEqual(history.status_code, 200)
        reply_payload = next(message for message in history.json() if message["id"] == reply.id)
        self.assertEqual(reply_payload["reply_to"]["id"], original.id)
        self.assertEqual(reply_payload["reply_to"]["preview"], "A" * 80)
        self.assertFalse(reply_payload["reply_to"]["revoked"])

        with self.session() as session:
            original_record = session.get(type(original), original.id)
            original_record.revoked_at = datetime.now(timezone.utc)
            original_record.revoked_by = self.human.id
            session.add(original_record)
            session.commit()

        with self.make_client() as client:
            history_after_revoke = client.get(
                "/api/messages",
                headers={"X-API-Key": "bobo-key"},
                params={"since": 0},
            )

        updated_reply_payload = next(message for message in history_after_revoke.json() if message["id"] == reply.id)
        self.assertIsNone(updated_reply_payload["reply_to"]["preview"])
        self.assertTrue(updated_reply_payload["reply_to"]["revoked"])

    def test_websocket_message_payload_includes_reply_to(self):
        original = self.add_message(
            from_id=self.human.id,
            to_ids=json.dumps([self.agent_ai1.id]),
            message_type="text",
            content="ws quote source",
        )

        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                with client.websocket_connect("/ws?token=ai1-key") as agent_ws:
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(human_ws, ["agent:AI1", "human:bobo"])

                    response = client.post(
                        "/api/messages",
                        headers={"X-API-Key": "ai1-key"},
                        json={
                            "type": "text",
                            "content": "@human:bobo reply over ws",
                            "reply_to": original.id,
                        },
                    )
                    self.assertEqual(response.status_code, 201)

                    human_payload = self.assert_message(human_ws)
                    agent_payload = self.assert_message(agent_ws)
                    self.assertEqual(human_payload["reply_to"]["id"], original.id)
                    self.assertEqual(agent_payload["reply_to"]["preview"], "ws quote source")

    def test_public_config_endpoint_exposes_frontend_constants(self):
        with self.make_client() as client:
            response = client.get("/api/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("revoke_window_sec", payload)
        self.assertIn("max_upload_bytes", payload)
        self.assertIn("ws_ping_interval", payload)
