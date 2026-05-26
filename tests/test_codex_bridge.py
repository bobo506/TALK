import asyncio
import os
import sys
import unittest
from pathlib import Path

from bridges import codex_bridge
from bridges.codex_bridge import (
    CodexRunResult,
    build_codex_task_prompt,
    build_codex_prompt,
    default_codex_command,
    format_codex_reply,
    handle_queued_task,
    member_id_from_name,
    run_codex_command,
    should_handle_message,
    strip_leading_mentions,
)


class CodexBridgeTests(unittest.TestCase):
    def test_member_id_from_name_adds_agent_prefix(self):
        self.assertEqual(member_id_from_name("codex"), "agent:codex")
        self.assertEqual(member_id_from_name("agent:codex"), "agent:codex")

    def test_default_codex_command_prefers_env_override(self):
        old_value = os.environ.get("TALK_CODEX_COMMAND")
        os.environ["TALK_CODEX_COMMAND"] = "custom codex command"
        try:
            self.assertEqual(default_codex_command(), "custom codex command")
        finally:
            if old_value is None:
                os.environ.pop("TALK_CODEX_COMMAND", None)
            else:
                os.environ["TALK_CODEX_COMMAND"] = old_value

    def test_should_handle_only_direct_text_by_default(self):
        member_id = "agent:codex"

        self.assertTrue(should_handle_message({
            "from": "human:bobo",
            "to": ["agent:codex"],
            "type": "text",
            "content": "hello",
        }, member_id))
        self.assertFalse(should_handle_message({
            "from": "human:bobo",
            "to": None,
            "type": "text",
            "content": "broadcast",
        }, member_id))
        self.assertTrue(should_handle_message({
            "from": "human:bobo",
            "to": None,
            "type": "text",
            "content": "broadcast",
        }, member_id, respond_to_broadcast=True))
        self.assertFalse(should_handle_message({
            "from": "agent:codex",
            "to": ["agent:codex"],
            "type": "text",
            "content": "self echo",
        }, member_id))
        self.assertFalse(should_handle_message({
            "from": "human:bobo",
            "to": ["agent:codex"],
            "type": "file",
            "content": "artifact.zip",
        }, member_id))

    def test_strip_leading_mentions(self):
        self.assertEqual(
            strip_leading_mentions("@agent:codex please inspect", member_id="agent:codex"),
            "please inspect",
        )
        self.assertEqual(
            strip_leading_mentions("  @agent:codex   @agent:other review", member_id=None),
            "review",
        )
        self.assertEqual(
            strip_leading_mentions("@agent:other leave intact", member_id="agent:codex"),
            "leave intact",
        )
        self.assertEqual(
            strip_leading_mentions("请让 @agent:other 看看", member_id="agent:codex"),
            "请让 @agent:other 看看",
        )

    def test_build_codex_prompt_contains_task_context(self):
        prompt = build_codex_prompt({
            "id": 42,
            "from": "human:bobo",
            "content": "@agent:codex summarize this",
        }, member_id="agent:codex", workdir=Path("D:/claude-test/TALK"))

        self.assertIn("agent:codex", prompt)
        self.assertIn("human:bobo", prompt)
        self.assertIn("TALK message id: 42", prompt)
        self.assertIn("summarize this", prompt)
        self.assertNotIn("@agent:codex summarize this", prompt)

    def test_build_codex_task_prompt_contains_task_context(self):
        prompt = build_codex_task_prompt({
            "id": 7,
            "created_by": "human:bobo",
            "title": "Smoke task",
            "content": "inspect the queue",
        }, member_id="agent:codex", workdir=Path("D:/claude-test/TALK"))

        self.assertIn("agent:codex", prompt)
        self.assertIn("human:bobo", prompt)
        self.assertIn("TALK task id: 7", prompt)
        self.assertIn("Title: Smoke task", prompt)
        self.assertIn("inspect the queue", prompt)

    def test_format_codex_reply_handles_error_and_truncation(self):
        reply = format_codex_reply(
            CodexRunResult(returncode=2, stdout="out", stderr="err"),
            max_chars=100,
        )
        self.assertIn("Codex bridge 运行失败", reply)
        self.assertNotIn("stderr", reply)
        self.assertNotIn("err", reply)

        truncated = format_codex_reply(
            CodexRunResult(returncode=0, stdout="x" * 20, stderr=""),
            max_chars=10,
        )
        self.assertIn("[truncated", truncated)

    def test_run_codex_command_pipes_prompt_to_subprocess(self):
        async def scenario():
            return await run_codex_command(
                [sys.executable, "-c", "import sys; print(sys.stdin.read().strip().upper())"],
                "hello bridge",
                cwd=Path.cwd(),
                timeout=5,
            )

        result = asyncio.run(scenario())

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "HELLO BRIDGE")
        self.assertEqual(result.stderr, "")

    def test_handle_queued_task_claims_runs_replies_and_completes(self):
        class FakeClient:
            def __init__(self):
                self.claimed = []
                self.sent = []
                self.completed = []

            async def claim_task(self, task_id, *, instance_id=None):
                self.claimed.append((task_id, instance_id))
                return {
                    "id": task_id,
                    "created_by": "human:bobo",
                    "title": "Queue smoke",
                    "content": "say ok",
                }

            async def send_text(self, text, to=None):
                self.sent.append((text, to))
                return {"id": 99}

            async def complete_task(self, task_id, *, status, result_message_id=None, last_error=None):
                self.completed.append((task_id, status, result_message_id, last_error))
                return {"id": task_id, "status": status}

        async def fake_run_codex_command(command, prompt, *, cwd, timeout):
            self.assertEqual(command, ["codex", "exec"])
            self.assertIn("say ok", prompt)
            self.assertEqual(timeout, 5)
            return CodexRunResult(returncode=0, stdout="OK", stderr="")

        async def scenario():
            original = codex_bridge.run_codex_command
            codex_bridge.run_codex_command = fake_run_codex_command
            try:
                client = FakeClient()
                handled = await handle_queued_task(
                    {"id": 12},
                    client=client,
                    member_id="agent:codex",
                    workdir=Path.cwd(),
                    instance_id="agent:codex:test",
                    codex_command=["codex", "exec"],
                    timeout=5,
                    max_reply_chars=100,
                )
                return handled, client
            finally:
                codex_bridge.run_codex_command = original

        handled, client = asyncio.run(scenario())

        self.assertTrue(handled)
        self.assertEqual(client.claimed, [(12, "agent:codex:test")])
        self.assertEqual(client.sent, [("OK", ["human:bobo"])])
        self.assertEqual(client.completed, [(12, "succeeded", 99, None)])


if __name__ == "__main__":
    unittest.main()
