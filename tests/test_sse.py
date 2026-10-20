import json
import socket
import threading
import time
from datetime import datetime, timezone

import httpx
import uvicorn

import server.db as db
import server.main as main
from server.ws_hub import hub
from tests.test_support import RouteTestCase


class LiveTalkServer:
    def __init__(self, app, host: str = "127.0.0.1") -> None:
        self.host = host
        self.port = self._pick_port()
        self.base_url = f"http://{self.host}:{self.port}"
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            if self.server.started:
                return self.base_url
            time.sleep(0.05)
        raise RuntimeError("uvicorn test server did not start in time")

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)

    @staticmethod
    def _pick_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


class ServerSentEventsTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.agent_ai1 = self.add_member("agent:AI1", api_key="ai1-key", display_name="AI1")
        self.agent_ai2 = self.add_member("agent:AI2", api_key="ai2-key", display_name="AI2")

    def read_sse_event(self, lines, expected_event: str) -> dict:
        event_type = None
        event_id = None
        data_lines: list[str] = []

        for _ in range(80):
            line = next(lines)
            if line == "":
                if event_type is None:
                    continue
                if event_type != expected_event:
                    event_type = None
                    event_id = None
                    data_lines = []
                    continue
                payload = json.loads("\n".join(data_lines) or "{}")
                if event_id is not None:
                    payload["_event_id"] = event_id
                return payload
            if line.startswith("id: "):
                event_id = line[4:]
            elif line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])

        self.fail(f"timed out waiting for SSE event {expected_event!r}")

    def test_sse_rejects_invalid_api_key(self):
        with self.make_client() as client:
            response = client.get("/api/events?token=bad-key")

        self.assertEqual(response.status_code, 401)

    def test_sse_rejects_invalid_last_event_id_header(self):
        with self.make_client() as client:
            response = client.get(
                "/api/events?token=ai1-key",
                headers={"Last-Event-ID": "not-an-int"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Last-Event-ID must be a non-negative integer")

    def test_sse_presence_and_message_events(self):
        with LiveTalkServer(main.app) as base_url:
            with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
                with client.stream("GET", "/api/events?token=ai1-key") as stream:
                    self.assertEqual(stream.status_code, 200)
                    self.assertEqual(stream.headers["content-type"].split(";")[0], "text/event-stream")
                    lines = stream.iter_lines()

                    initial_presence = self.read_sse_event(lines, "presence")
                    self.assertEqual(initial_presence["online_ids"], ["agent:AI1"])

                    response = client.post(
                        "/api/messages",
                        headers={"X-API-Key": "bobo-key"},
                        json={"type": "text", "content": "@agent:AI1 hello sse"},
                    )
                    self.assertEqual(response.status_code, 201)
                    created = response.json()

                    event = self.read_sse_event(lines, "message")
                    self.assertEqual(event["id"], created["id"])
                    self.assertEqual(event["_event_id"], str(created["id"]))
                    self.assertEqual(event["content"], "@agent:AI1 hello sse")
                    self.assertEqual(event["to"], ["agent:AI1"])

        self.assertEqual(hub.online_members_count(), 0)

    def test_sse_replays_visible_messages_after_last_event_id_header(self):
        first = self.add_message(
            from_id="human:bobo",
            to_ids=None,
            message_type="text",
            content="already delivered",
        )
        hidden = self.add_message(
            from_id="human:bobo",
            to_ids='["agent:AI2"]',
            message_type="text",
            content="@agent:AI2 hidden from ai1",
        )
        direct = self.add_message(
            from_id="human:bobo",
            to_ids='["agent:AI1"]',
            message_type="text",
            content="@agent:AI1 replay me",
        )

        with LiveTalkServer(main.app) as base_url:
            with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
                with client.stream(
                    "GET",
                    "/api/events?token=ai1-key",
                    headers={"Last-Event-ID": str(first.id)},
                ) as stream:
                    self.assertEqual(stream.status_code, 200)
                    lines = stream.iter_lines()

                    initial_presence = self.read_sse_event(lines, "presence")
                    self.assertEqual(initial_presence["online_ids"], ["agent:AI1"])

                    event = self.read_sse_event(lines, "message")
                    self.assertEqual(event["id"], direct.id)
                    self.assertEqual(event["_event_id"], str(direct.id))
                    self.assertNotEqual(event["id"], hidden.id)
                    self.assertEqual(event["content"], "@agent:AI1 replay me")

        self.assertEqual(hub.online_members_count(), 0)

    def test_sse_replay_zero_last_event_id_backfills_current_snapshot(self):
        revoked = self.add_message(
            from_id="human:bobo",
            to_ids='["agent:AI1"]',
            message_type="text",
            content="@agent:AI1 now revoked",
            revoked_at=datetime.now(timezone.utc),
            revoked_by="human:bobo",
        )

        with LiveTalkServer(main.app) as base_url:
            with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
                with client.stream("GET", "/api/events?token=ai1-key&last_event_id=0") as stream:
                    self.assertEqual(stream.status_code, 200)
                    lines = stream.iter_lines()
                    self.read_sse_event(lines, "presence")

                    event = self.read_sse_event(lines, "message")
                    self.assertEqual(event["id"], revoked.id)
                    self.assertTrue(event["revoked"])
                    self.assertIsNone(event["content"])
                    self.assertEqual(event["revoked_by"], "human:bobo")

        self.assertEqual(hub.online_members_count(), 0)

    def test_sse_revoke_event(self):
        with LiveTalkServer(main.app) as base_url:
            with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
                created = client.post(
                    "/api/messages",
                    headers={"X-API-Key": "bobo-key"},
                    json={"type": "text", "content": "@agent:AI1 revoke over sse"},
                )
                self.assertEqual(created.status_code, 201)
                message = created.json()

                with client.stream("GET", "/api/events?token=ai1-key") as stream:
                    lines = stream.iter_lines()
                    self.read_sse_event(lines, "presence")

                    revoked = client.post(
                        f"/api/messages/{message['id']}/revoke",
                        headers={"X-API-Key": "bobo-key"},
                    )
                    self.assertEqual(revoked.status_code, 200)

                    event = self.read_sse_event(lines, "revoke")
                    self.assertEqual(event["id"], message["id"])
                    self.assertEqual(event["_event_id"], str(message["id"]))
                    self.assertEqual(event["revoked_by"], "human:bobo")


class ObserverSseTests(RouteTestCase):
    """285：观察者经真实 SSE 端点收到 Group 实时消息与断线补发；非观察者隔离。"""

    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.other_human = self.add_member("human:carol", api_key="carol-key", display_name="Carol")
        self.agent_ai1 = self.add_member("agent:AI1", api_key="ai1-key", display_name="AI1")
        self.agent_ai2 = self.add_member("agent:AI2", api_key="ai2-key", display_name="AI2")

    def set_observer_config(self, section):
        old_config = db.CONFIG
        new_config = dict(old_config)
        if section is None:
            new_config.pop("conversation_access", None)
        else:
            new_config["conversation_access"] = section
        db.CONFIG = new_config
        self.addCleanup(setattr, db, "CONFIG", old_config)

    def read_sse_event(self, lines, expected_event: str) -> dict:
        event_type = None
        event_id = None
        data_lines: list[str] = []

        for _ in range(80):
            line = next(lines)
            if line == "":
                if event_type is None:
                    continue
                if event_type != expected_event:
                    event_type = None
                    event_id = None
                    data_lines = []
                    continue
                payload = json.loads("\n".join(data_lines) or "{}")
                if event_id is not None:
                    payload["_event_id"] = event_id
                return payload
            if line.startswith("id: "):
                event_id = line[4:]
            elif line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])

        self.fail(f"timed out waiting for SSE event {expected_event!r}")

    def make_group(self, group_id="group:lab", member_ids=()):
        with self.make_client() as client:
            response = client.post(
                "/api/groups",
                headers={"X-API-Key": "ai1-key"},
                json={"id": group_id, "name": "Local Lab", "member_ids": list(member_ids)},
            )
        assert response.status_code == 201, response.text

    def post_group_message(self, content, group_id="group:lab", key="ai1-key"):
        with self.make_client() as client:
            response = client.post(
                "/api/messages",
                headers={"X-API-Key": key},
                json={"type": "text", "group_id": group_id, "content": content},
            )
        assert response.status_code == 201, response.text
        return response.json()

    def test_observer_receives_live_group_message_and_revoke_over_sse(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])

        with LiveTalkServer(main.app) as base_url:
            with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
                with client.stream("GET", "/api/events?token=bobo-key") as stream:
                    self.assertEqual(stream.status_code, 200)
                    lines = stream.iter_lines()
                    self.read_sse_event(lines, "presence")

                    created = self.post_group_message("hello observer over sse")
                    event = self.read_sse_event(lines, "message")
                    self.assertEqual(event["id"], created["id"])
                    self.assertEqual(event["group_id"], "group:lab")

                    revoked = client.post(
                        f"/api/messages/{created['id']}/revoke",
                        headers={"X-API-Key": "ai1-key"},
                    )
                    self.assertEqual(revoked.status_code, 200)
                    revoke_event = self.read_sse_event(lines, "revoke")
                    self.assertEqual(revoke_event["id"], created["id"])

        self.assertEqual(hub.online_members_count(), 0)

    def test_observer_backfill_includes_group_but_not_direct_messages(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        # 顺序固定：广播 < 私信 < 群消息；若私信泄漏给观察者，它会先出现。
        broadcast = self.add_message(
            from_id="agent:AI1", to_ids=None, message_type="text", content="broadcast visible"
        )
        direct = self.add_message(
            from_id="agent:AI1", to_ids='["agent:AI2"]', message_type="text", content="direct hidden"
        )
        group_message = self.post_group_message("group backfill visible")

        with LiveTalkServer(main.app) as base_url:
            with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
                with client.stream("GET", "/api/events?token=bobo-key&last_event_id=0") as stream:
                    self.assertEqual(stream.status_code, 200)
                    lines = stream.iter_lines()
                    self.read_sse_event(lines, "presence")

                    first = self.read_sse_event(lines, "message")
                    self.assertEqual(first["id"], broadcast.id)
                    second = self.read_sse_event(lines, "message")
                    self.assertEqual(second["id"], group_message["id"])
                    self.assertNotEqual(second["id"], direct.id)

        self.assertEqual(hub.online_members_count(), 0)

    def test_non_observer_backfill_excludes_foreign_group_messages(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        foreign = self.post_group_message("not for carol")
        # carol 自己所在群的消息作为边界：若越权读到 group:lab，第一条就会是 foreign。
        self.make_group(group_id="group:carol-room", member_ids=["human:carol"])
        own = self.post_group_message("carol room message", group_id="group:carol-room")

        with LiveTalkServer(main.app) as base_url:
            with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
                with client.stream("GET", "/api/events?token=carol-key&last_event_id=0") as stream:
                    self.assertEqual(stream.status_code, 200)
                    lines = stream.iter_lines()
                    self.read_sse_event(lines, "presence")

                    event = self.read_sse_event(lines, "message")
                    self.assertEqual(event["id"], own["id"])
                    self.assertNotEqual(event["id"], foreign["id"])

        self.assertEqual(hub.online_members_count(), 0)

    def test_default_config_live_group_message_not_pushed_to_non_member(self):
        self.set_observer_config(None)
        self.make_group(member_ids=[])

        with LiveTalkServer(main.app) as base_url:
            with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
                with client.stream("GET", "/api/events?token=bobo-key") as stream:
                    self.assertEqual(stream.status_code, 200)
                    lines = stream.iter_lines()
                    self.read_sse_event(lines, "presence")

                    self.post_group_message("no push when disabled")
                    # 边界消息：广播对 bobo 可见；若群消息越权推送，它会先于广播到达。
                    with self.make_client() as barrier_client:
                        barrier = barrier_client.post(
                            "/api/messages",
                            headers={"X-API-Key": "ai1-key"},
                            json={"type": "text", "content": "broadcast barrier"},
                        )
                    self.assertEqual(barrier.status_code, 201)
                    event = self.read_sse_event(lines, "message")
                    self.assertEqual(event["id"], barrier.json()["id"])
                    self.assertIsNone(event["group_id"])

        self.assertEqual(hub.online_members_count(), 0)
