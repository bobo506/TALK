import asyncio
import contextlib
import io
import sys
import unittest
from pathlib import Path

from bridges import cli_bridge
from bridges.cli_bridge import (
    CliRunResult,
    build_cli_task_prompt,
    build_parser,
    format_cli_reply,
    handle_queued_task,
    run_cli_command,
)


class CliBridgeTests(unittest.TestCase):
    def test_parser_requires_command_for_generic_cli(self):
        parser = build_parser()

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--key", "pi-key"])

        args = parser.parse_args([
            "--key",
            "pi-key",
            "--name",
            "pi",
            "--runtime",
            "pi",
            "--command",
            "pi run -",
        ])

        self.assertEqual(args.name, "pi")
        self.assertEqual(args.runtime, "pi")
        self.assertEqual(args.command, "pi run -")

    def test_build_cli_task_prompt_uses_runtime_label(self):
        prompt = build_cli_task_prompt(
            {
                "id": 7,
                "created_by": "human:bobo",
                "content": "ask codex to review this too",
            },
            member_id="agent:pi",
            workdir=Path("D:/claude-test/TALK"),
            runtime="pi",
        )

        self.assertIn("agent:pi", prompt)
        self.assertIn("pi CLI agent", prompt)
        self.assertIn("human:bobo", prompt)
        self.assertIn("ask codex to review this too", prompt)

    def test_format_cli_reply_uses_bridge_label(self):
        reply = format_cli_reply(
            CliRunResult(returncode=2, stdout="", stderr="boom"),
            max_chars=200,
            bridge_label="pi bridge",
        )

        self.assertIn("pi bridge failed with exit code 2", reply)
        self.assertIn("stderr", reply)

    def test_run_cli_command_pipes_prompt_to_subprocess(self):
        async def scenario():
            return await run_cli_command(
                [sys.executable, "-c", "import sys; print('PI:' + sys.stdin.read().strip())"],
                "hello",
                cwd=Path.cwd(),
                timeout=5,
            )

        result = asyncio.run(scenario())

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "PI:hello")

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
                    "content": "say ok",
                }

            async def send_text(self, text, to=None):
                self.sent.append((text, to))
                return {"id": 99}

            async def complete_task(self, task_id, *, status, result_message_id=None, last_error=None):
                self.completed.append((task_id, status, result_message_id, last_error))
                return {"id": task_id, "status": status}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout):
            self.assertEqual(command, ["pi", "run"])
            self.assertIn("say ok", prompt)
            self.assertIn("pi CLI agent", prompt)
            return CliRunResult(returncode=0, stdout="OK", stderr="")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                handled = await handle_queued_task(
                    {"id": 12},
                    client=client,
                    member_id="agent:pi",
                    workdir=Path.cwd(),
                    instance_id="agent:pi:test",
                    command=["pi", "run"],
                    timeout=5,
                    max_reply_chars=100,
                    runtime="pi",
                    bridge_label="pi bridge",
                )
                return handled, client
            finally:
                cli_bridge.run_cli_command = original

        handled, client = asyncio.run(scenario())

        self.assertTrue(handled)
        self.assertEqual(client.claimed, [(12, "agent:pi:test")])
        self.assertEqual(client.sent, [("OK", ["human:bobo"])])
        self.assertEqual(client.completed, [(12, "succeeded", 99, None)])


if __name__ == "__main__":
    unittest.main()
