import server.main as main
from starlette.websockets import WebSocketDisconnect

from server.ws_hub import hub
from tests.test_support import RouteTestCase


class WebSocketTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.agent_ai1 = self.add_member("agent:AI1", api_key="ai1-key", display_name="AI1")
        self.agent_ai2 = self.add_member("agent:AI2", api_key="ai2-key", display_name="AI2")

    def set_ping_config(self, interval: float, timeout: float) -> None:
        old_interval = main.WS_PING_INTERVAL
        old_timeout = main.WS_PING_TIMEOUT
        main.WS_PING_INTERVAL = interval
        main.WS_PING_TIMEOUT = timeout
        self.addCleanup(setattr, main, "WS_PING_INTERVAL", old_interval)
        self.addCleanup(setattr, main, "WS_PING_TIMEOUT", old_timeout)

    def assert_presence(self, websocket, expected_ids: list[str]) -> None:
        event = websocket.receive_json()
        self.assertEqual(event["type"], "presence")
        self.assertEqual(event["payload"]["online_ids"], expected_ids)

    def assert_message(self, websocket) -> dict:
        event = websocket.receive_json()
        self.assertEqual(event["type"], "message")
        return event["payload"]

    def assert_ping(self, websocket) -> None:
        event = websocket.receive_json()
        self.assertEqual(event["type"], "ping")

    def assert_send_ack(self, websocket) -> dict:
        event = websocket.receive_json()
        self.assertEqual(event["type"], "send_ack")
        return event

    def test_websocket_rejects_invalid_api_key(self):
        with self.make_client() as client:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with client.websocket_connect("/ws?token=bad-key"):
                    pass

        self.assertEqual(ctx.exception.code, 4001)

    def test_presence_snapshot_and_disconnect_broadcast(self):
        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                with client.websocket_connect("/ws?token=ai1-key") as agent_ws:
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(human_ws, ["agent:AI1", "human:bobo"])

                self.assert_presence(human_ws, ["human:bobo"])

        self.assertEqual(hub._count(), 0)

    def test_ping_pong_loop_keeps_connection_alive(self):
        self.set_ping_config(0.05, 0.12)

        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                self.assert_ping(human_ws)
                human_ws.send_json({"type": "pong"})
                self.assert_ping(human_ws)
                human_ws.send_json({"type": "pong"})

                with client.websocket_connect("/ws?token=ai1-key") as agent_ws:
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(human_ws, ["agent:AI1", "human:bobo"])

    def test_ping_timeout_disconnects_idle_connection(self):
        self.set_ping_config(0.05, 0.12)

        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                with self.assertRaises(WebSocketDisconnect) as ctx:
                    while True:
                        human_ws.receive_json()

        self.assertEqual(ctx.exception.code, main.WS_CLOSE_IDLE_TIMEOUT)

    def test_message_push_reaches_websocket_and_since_returns_no_duplicate(self):
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
                        headers={"X-API-Key": "bobo-key"},
                        json={"type": "text", "content": "@agent:AI1 hello realtime"},
                    )
                    self.assertEqual(response.status_code, 201)
                    created = response.json()

                    human_payload = self.assert_message(human_ws)
                    agent_payload = self.assert_message(agent_ws)
                    self.assertEqual(human_payload["id"], created["id"])
                    self.assertEqual(agent_payload["id"], created["id"])
                    self.assertEqual(agent_payload["to"], ["agent:AI1"])

                    since_response = client.get(
                        "/api/messages",
                        headers={"X-API-Key": "ai1-key"},
                        params={"since": created["id"], "to": "agent:AI1"},
                    )
                    self.assertEqual(since_response.status_code, 200)
                    self.assertEqual(since_response.json(), [])

    def test_inbound_send_success_path_matches_rest_behavior(self):
        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                with client.websocket_connect("/ws?token=ai1-key") as agent_ws:
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(human_ws, ["agent:AI1", "human:bobo"])

                    human_ws.send_json(
                        {"type": "send", "payload": {"type": "text", "content": "@agent:AI1 hello over ws"}}
                    )

                    human_payload = self.assert_message(human_ws)
                    agent_payload = self.assert_message(agent_ws)
                    self.assertEqual(human_payload["id"], agent_payload["id"])
                    self.assertEqual(agent_payload["to"], ["agent:AI1"])

                    since_response = client.get(
                        "/api/messages",
                        headers={"X-API-Key": "ai1-key"},
                        params={"since": agent_payload["id"], "to": "agent:AI1"},
                    )
                    self.assertEqual(since_response.status_code, 200)
                    self.assertEqual(since_response.json(), [])

    def test_inbound_send_failure_returns_send_ack(self):
        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                human_ws.send_json(
                    {"type": "send", "payload": {"type": "text", "content": "@agent:UNKNOWN hello over ws"}}
                )

                ack = self.assert_send_ack(human_ws)
                self.assertFalse(ack["ok"])
                self.assertIn("invalid recipient mention", ack["error"])

    def test_broadcast_message_reaches_all_online_connections(self):
        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                with client.websocket_connect("/ws?token=ai1-key") as agent1_ws:
                    self.assert_presence(agent1_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(agent1_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(human_ws, ["agent:AI1", "human:bobo"])

                    with client.websocket_connect("/ws?token=ai2-key") as agent2_ws:
                        expected_online = ["agent:AI1", "agent:AI2", "human:bobo"]
                        self.assert_presence(agent2_ws, expected_online)
                        self.assert_presence(agent2_ws, expected_online)
                        self.assert_presence(human_ws, expected_online)
                        self.assert_presence(agent1_ws, expected_online)

                        human_ws.send_json({"type": "send", "payload": {"type": "text", "content": "hello everyone"}})

                        human_payload = self.assert_message(human_ws)
                        agent1_payload = self.assert_message(agent1_ws)
                        agent2_payload = self.assert_message(agent2_ws)
                        self.assertIsNone(human_payload["to"])
                        self.assertEqual(human_payload["id"], agent1_payload["id"])
                        self.assertEqual(agent1_payload["id"], agent2_payload["id"])

    def test_same_member_multiple_connections_all_receive_push(self):
        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws_1:
                self.assert_presence(human_ws_1, ["human:bobo"])
                self.assert_presence(human_ws_1, ["human:bobo"])

                with client.websocket_connect("/ws?token=bobo-key") as human_ws_2:
                    self.assert_presence(human_ws_2, ["human:bobo"])

                    with client.websocket_connect("/ws?token=ai1-key") as agent_ws:
                        self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                        self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                        self.assert_presence(human_ws_1, ["agent:AI1", "human:bobo"])
                        self.assert_presence(human_ws_2, ["agent:AI1", "human:bobo"])

                        agent_ws.send_json(
                            {"type": "send", "payload": {"type": "text", "content": "@human:bobo hello both tabs"}}
                        )

                        human_payload_1 = self.assert_message(human_ws_1)
                        human_payload_2 = self.assert_message(human_ws_2)
                        agent_payload = self.assert_message(agent_ws)
                        self.assertEqual(human_payload_1["id"], human_payload_2["id"])
                        self.assertEqual(human_payload_2["id"], agent_payload["id"])
                        self.assertEqual(agent_payload["to"], ["human:bobo"])

    def test_reconnect_recovers_missed_history_via_http_since(self):
        with self.make_client() as client:
            with client.websocket_connect("/ws?token=bobo-key") as human_ws:
                self.assert_presence(human_ws, ["human:bobo"])
                self.assert_presence(human_ws, ["human:bobo"])

                with client.websocket_connect("/ws?token=ai1-key") as agent_ws:
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(human_ws, ["agent:AI1", "human:bobo"])

                    first_response = client.post(
                        "/api/messages",
                        headers={"X-API-Key": "bobo-key"},
                        json={"type": "text", "content": "@agent:AI1 first"},
                    )
                    self.assertEqual(first_response.status_code, 201)
                    first_created = first_response.json()
                    self.assertEqual(self.assert_message(human_ws)["id"], first_created["id"])
                    self.assertEqual(self.assert_message(agent_ws)["id"], first_created["id"])

                self.assert_presence(human_ws, ["human:bobo"])

                second_response = client.post(
                    "/api/messages",
                    headers={"X-API-Key": "bobo-key"},
                    json={"type": "text", "content": "@agent:AI1 second"},
                )
                self.assertEqual(second_response.status_code, 201)
                second_created = second_response.json()
                self.assertEqual(self.assert_message(human_ws)["id"], second_created["id"])

                history_response = client.get(
                    "/api/messages",
                    headers={"X-API-Key": "ai1-key"},
                    params={"since": first_created["id"], "to": "agent:AI1"},
                )
                self.assertEqual(history_response.status_code, 200)
                self.assertEqual(
                    [message["id"] for message in history_response.json()],
                    [second_created["id"]],
                )

                with client.websocket_connect("/ws?token=ai1-key") as agent_ws:
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(agent_ws, ["agent:AI1", "human:bobo"])
                    self.assert_presence(human_ws, ["agent:AI1", "human:bobo"])
