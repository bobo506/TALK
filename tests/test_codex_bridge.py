import asyncio
import sys
import unittest
from pathlib import Path

from bridges.codex_bridge import (
    CodexRunResult,
    build_codex_prompt,
    format_codex_reply,
    member_id_from_name,
    run_codex_command,
    should_handle_message,
    strip_leading_mentions,
)


class CodexBridgeTests(unittest.TestCase):
    def test_member_id_from_name_adds_agent_prefix(self):
        self.assertEqual(member_id_from_name("codex"), "agent:codex")
        self.assertEqual(member_id_from_name("agent:codex"), "agent:codex")

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
            "@agent:other leave intact",
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

    def test_format_codex_reply_handles_error_and_truncation(self):
        reply = format_codex_reply(
            CodexRunResult(returncode=2, stdout="out", stderr="err"),
            max_chars=100,
        )
        self.assertIn("exit code 2", reply)
        self.assertIn("stderr", reply)

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


if __name__ == "__main__":
    unittest.main()
