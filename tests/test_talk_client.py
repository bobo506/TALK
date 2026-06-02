import asyncio
import contextlib
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
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

    def test_task_helpers(self):
        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "bobo-key") as human_client:
                created = await human_client.create_task(
                    "agent:demo",
                    "Run from SDK",
                    title="SDK task",
                )

            async with TalkClient(base_url, "demo-key") as agent_client:
                await agent_client.report_instance_status("demo-instance-1", runtime="codex", status="idle")
                queued = await agent_client.list_tasks(status="queued")
                claimed = await agent_client.claim_task(created["id"], instance_id="demo-instance-1")
                completed = await agent_client.complete_task(claimed["id"], status="succeeded")

            self.assertEqual(queued[0]["id"], created["id"])
            self.assertEqual(claimed["status"], "running")
            self.assertEqual(completed["status"], "succeeded")

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_task_schedule_helpers(self):
        async def scenario(base_url: str) -> None:
            run_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            async with TalkClient(base_url, "bobo-key") as human_client:
                created = await human_client.create_task_schedule(
                    "agent:demo",
                    "Run scheduled SDK task",
                    title="SDK schedule",
                    run_at=run_at,
                )
                visible = await human_client.list_task_schedules(status="active")
                materialized = await human_client.run_due_task_schedules()
                completed = await human_client.get_task_schedule(created["id"])

            self.assertEqual(visible[0]["id"], created["id"])
            self.assertEqual(materialized["created_tasks"][0]["schedule_id"], created["id"])
            self.assertEqual(completed["status"], "completed")

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    def test_group_helpers_and_hall_history(self):
        async def scenario(base_url: str) -> None:
            async with TalkClient(base_url, "bobo-key") as human_client:
                group = await human_client.create_group(
                    "SDK Lab",
                    group_id="group:sdk-lab",
                    description="Created from SDK tests",
                    member_ids=["agent:demo"],
                )
                renamed = await human_client.update_group(
                    "group:sdk-lab",
                    name="SDK Lab Renamed",
                    description="Updated from SDK tests",
                )
                updated = await human_client.upsert_group_member("group:sdk-lab", "agent:other", role="moderator")
                removed = await human_client.remove_group_member("group:sdk-lab", "agent:other")

                hall_message = await human_client.send_text(
                    "@agent:demo hello inside hall",
                    group_id="group:sdk-lab",
                )
                discussion = await human_client.create_discussion(
                    "group:sdk-lab",
                    "SDK discussion",
                    ["human:bobo", "agent:demo"],
                    max_rounds=2,
                )
                human_turn = await human_client.append_discussion_turn(
                    discussion["id"],
                    message_id=hall_message["id"],
                    stance="question",
                    target_member_id="agent:demo",
                    turn_kind="demand",
                    round_index=1,
                )
                global_history = await human_client.fetch_history(since=0)

            async with TalkClient(base_url, "demo-key") as agent_client:
                groups = await agent_client.list_groups()
                fetched = await agent_client.get_group("group:sdk-lab")
                agent_message = await agent_client.send_text(
                    "@human:bobo reply inside discussion",
                    group_id="group:sdk-lab",
                )
                agent_turn = await agent_client.append_discussion_turn(
                    discussion["id"],
                    message_id=agent_message["id"],
                    stance="answer",
                    target_member_id="human:bobo",
                    round_index=1,
                )
                turns = await agent_client.list_discussion_turns(discussion["id"])
                hall_history = await agent_client.fetch_history(group_id="group:sdk-lab", since=0)

            self.assertEqual(group["id"], "group:sdk-lab")
            self.assertEqual(group["description"], "Created from SDK tests")
            self.assertEqual(renamed["name"], "SDK Lab Renamed")
            self.assertEqual(renamed["description"], "Updated from SDK tests")
            self.assertIn("agent:other", {member["member_id"] for member in updated["members"]})
            self.assertNotIn("agent:other", {member["member_id"] for member in removed["members"]})
            self.assertEqual([item["id"] for item in groups], ["group:sdk-lab"])
            self.assertEqual(
                {member["member_id"] for member in fetched["members"]},
                {"human:bobo", "agent:demo"},
            )
            self.assertEqual(fetched["name"], "SDK Lab Renamed")
            self.assertEqual(hall_message["group_id"], "group:sdk-lab")
            self.assertEqual(discussion["topic"], "SDK discussion")
            self.assertEqual(human_turn["turn_index"], 1)
            self.assertEqual(human_turn["turn_kind"], "demand")
            self.assertEqual(agent_turn["turn_index"], 2)
            self.assertEqual(agent_turn["turn_kind"], "reply")
            self.assertEqual([turn["stance"] for turn in turns], ["question", "answer"])
            self.assertIn("@agent:demo hello inside hall", [message["content"] for message in hall_history])
            self.assertIn("@human:bobo reply inside discussion", [message["content"] for message in hall_history])
            self.assertNotIn(hall_message["id"], {message["id"] for message in global_history})

        with LiveTalkServer(main.app) as base_url:
            asyncio.run(scenario(base_url))

    async def _wait_for(self, predicate, timeout: float = 2.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if predicate():
                return
            await asyncio.sleep(0.05)
        raise AssertionError("condition not met in time")
