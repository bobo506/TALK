import asyncio
import contextlib
import socket
import threading
import time
from pathlib import Path

import uvicorn

import server.main as main
from TALK.client import TalkClient
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


class TalkClientTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.agent = self.add_member("agent:demo", api_key="demo-key", display_name="Demo")
        self.other = self.add_member("agent:other", api_key="other-key", display_name="Other")

        self._old_ping_interval = main.WS_PING_INTERVAL
        self._old_ping_timeout = main.WS_PING_TIMEOUT
        main.WS_PING_INTERVAL = 1.0
        main.WS_PING_TIMEOUT = 3.0
        self.addCleanup(setattr, main, "WS_PING_INTERVAL", self._old_ping_interval)
        self.addCleanup(setattr, main, "WS_PING_TIMEOUT", self._old_ping_timeout)

    def test_me_and_members(self):
        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "demo-key") as client:
                me = await client.me()
                members = await client.list_members()

            self.assertEqual(me["id"], "agent:demo")
            self.assertEqual({member["id"] for member in members}, {"human:bobo", "agent:demo", "agent:other"})

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_send_text(self):
        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "demo-key") as agent_client:
                await agent_client.me()
                created = await agent_client.send_text("hello from sdk", to=["human:bobo"])

            with self.make_client() as client:
                response = client.get(
                    "/api/messages",
                    headers={"X-API-Key": "bobo-key"},
                    params={"to": "human:bobo", "since": 0},
                )

            self.assertEqual(created["type"], "text")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[-1]["content"], "hello from sdk")

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_send_file(self):
        upload_path = self._tmpdir / "sdk-upload.txt"
        upload_path.write_text("sdk payload", encoding="utf-8")

        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "demo-key") as agent_client:
                created = await agent_client.send_file(upload_path, caption="demo artifact", to=["human:bobo"])

            self.assertEqual(created["type"], "file")
            self.assertEqual(created["filename"], "sdk-upload.txt")
            self.assertEqual(created["caption"], "demo artifact")

            async with TalkClient(base_url, "bobo-key") as human_client:
                content = await human_client.download_file(created["file_id"])

            self.assertEqual(content, b"sdk payload")

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_receives_message_over_websocket(self):
        async def scenario(base_url: str) -> None:
            received: asyncio.Queue = asyncio.Queue()
            async with TalkClient(base_url, "demo-key", poll_interval=0.1) as agent_client:
                await agent_client.me()

                @agent_client.on_message
                async def handle_message(message: dict) -> None:
                    await received.put(message)

                run_task = asyncio.create_task(agent_client.run())
                try:
                    await self._wait_for(lambda: agent_client._ws is not None)

                    async with TalkClient(base_url, "bobo-key") as human_client:
                        await human_client.me()
                        await human_client.send_text("ping over ws", to=["agent:demo"])

                    message = await asyncio.wait_for(received.get(), timeout=2)
                    self.assertEqual(message["content"], "ping over ws")
                    self.assertEqual(message["from"], "human:bobo")
                finally:
                    await agent_client.close()
                    await asyncio.wait_for(run_task, timeout=2)

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_disconnect_falls_back_to_http_polling(self):
        async def scenario(base_url: str) -> None:
            received: asyncio.Queue = asyncio.Queue()
            async with TalkClient(
                base_url,
                "demo-key",
                poll_interval=0.1,
                reconnect_initial_delay=1.0,
                reconnect_max_delay=1.0,
            ) as agent_client:
                await agent_client.me()

                @agent_client.on_message
                async def handle_message(message: dict) -> None:
                    await received.put(message)

                run_task = asyncio.create_task(agent_client.run())
                try:
                    await self._wait_for(lambda: agent_client._ws is not None)
                    await agent_client._ws.close()
                    await self._wait_for(lambda: agent_client._ws is None)

                    async with TalkClient(base_url, "bobo-key") as human_client:
                        await human_client.me()
                        await human_client.send_text("missed while ws down", to=["agent:demo"])

                    message = await asyncio.wait_for(received.get(), timeout=2)
                    self.assertEqual(message["content"], "missed while ws down")
                finally:
                    await agent_client.close()
                    await asyncio.wait_for(run_task, timeout=2)

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_revoke_push_triggers_handler(self):
        async def scenario(base_url: str) -> None:
            revoked_events: asyncio.Queue = asyncio.Queue()
            async with TalkClient(base_url, "demo-key", poll_interval=0.1) as agent_client:
                await agent_client.me()

                @agent_client.on_revoke
                async def handle_revoke(event: dict) -> None:
                    await revoked_events.put(event)

                run_task = asyncio.create_task(agent_client.run())
                try:
                    await self._wait_for(lambda: agent_client._ws is not None)

                    async with TalkClient(base_url, "bobo-key") as human_client:
                        await human_client.me()
                        created = await human_client.send_text("please revoke me", to=["agent:demo"])
                        await human_client.revoke(created["id"])

                    event = await asyncio.wait_for(revoked_events.get(), timeout=2)
                    self.assertEqual(event["id"], created["id"])
                    self.assertEqual(event["revoked_by"], "human:bobo")
                finally:
                    await agent_client.close()
                    await asyncio.wait_for(run_task, timeout=2)

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_reply_shortcut(self):
        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "bobo-key") as human_client:
                await human_client.me()
                original = await human_client.send_text("reply target", to=["agent:demo"])

            async with TalkClient(base_url, "demo-key") as agent_client:
                await agent_client.me()
                created = await agent_client.reply(original["id"], text="reply via sdk", to=["human:bobo"])

            self.assertEqual(created["reply_to"]["id"], original["id"])
            self.assertEqual(created["reply_to"]["preview"], "reply target")

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_instance_status_helpers(self):
        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "demo-key") as agent_client:
                created = await agent_client.report_instance_status(
                    "demo-instance-1",
                    runtime="codex",
                    status="idle",
                    host="test-host",
                    pid=1234,
                )

            async with TalkClient(base_url, "bobo-key") as human_client:
                instances = await human_client.list_instances(member_id="agent:demo", status="idle")

            self.assertEqual(created["id"], "demo-instance-1")
            self.assertEqual(created["member_id"], "agent:demo")
            self.assertEqual(instances[0]["id"], "demo-instance-1")

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    async def _wait_for(self, predicate, timeout: float = 2.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if predicate():
                return
            await asyncio.sleep(0.05)
        raise AssertionError("condition not met in time")
