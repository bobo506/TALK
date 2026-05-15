import json
import socket
import threading
import time

import httpx
import uvicorn

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
