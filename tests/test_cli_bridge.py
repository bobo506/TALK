import asyncio
import contextlib
import io
import sys
import unittest
from pathlib import Path

from bridges import cli_bridge
from bridges.cli_bridge import (
    CliRunResult,
    build_cli_prompt,
    build_cli_task_prompt,
    clean_cli_output,
    decode_subprocess_output,
    first_sentence,
    build_parser,
    format_cli_reply,
    handle_incoming_message,
    handle_queued_task,
    resolve_command_executable,
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

    def test_resolve_command_executable_uses_path_lookup(self):
        resolved = resolve_command_executable([Path(sys.executable).name, "--version"])

        self.assertTrue(Path(resolved[0]).is_absolute())
        self.assertEqual(resolved[1], "--version")

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
        self.assertIn("simple presence check", prompt)

    def test_build_cli_prompt_discourages_status_report_for_presence_check(self):
        prompt = build_cli_prompt({
            "id": 4,
            "from": "human:bobo",
            "content": "@agent:pi 在吗",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertIn("one short sentence", prompt)
        self.assertIn("Do not inspect project files", prompt)
        self.assertIn("在吗", prompt)

    def test_build_cli_prompt_includes_group_context_when_present(self):
        prompt = build_cli_prompt({
            "id": 8,
            "from": "human:bobo",
            "group_id": "group:lab",
            "content": "@agent:pi 在群里回我",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertIn("TALK group id: group:lab", prompt)

    def test_format_cli_reply_uses_bridge_label(self):
        reply = format_cli_reply(
            CliRunResult(returncode=2, stdout="", stderr="boom"),
            max_chars=200,
            bridge_label="pi bridge",
        )

        self.assertIn("pi bridge failed with exit code 2", reply)
        self.assertIn("stderr", reply)

    def test_format_cli_reply_can_force_one_sentence(self):
        reply = format_cli_reply(
            CliRunResult(returncode=0, stdout="第一句。\n\n第二句，还有很多状态。", stderr=""),
            force_one_sentence=True,
        )

        self.assertEqual(reply, "第一句。")

    def test_decode_subprocess_output_falls_back_to_windows_codepage(self):
        data = "成功: 已终止 PID 1 (属于 PID 2 子进程)的进程。".encode("gbk")

        self.assertEqual(
            decode_subprocess_output(data),
            "成功: 已终止 PID 1 (属于 PID 2 子进程)的进程。",
        )

    def test_decode_subprocess_output_handles_mixed_encoded_lines(self):
        data = (
            "成功: 已终止 PID 1 (属于 PID 2 子进程)的进程。\n".encode("gbk")
            + "codex 在线。\n".encode("utf-8")
        )

        self.assertEqual(
            decode_subprocess_output(data),
            "成功: 已终止 PID 1 (属于 PID 2 子进程)的进程。\ncodex 在线。\n",
        )

    def test_clean_cli_output_filters_taskkill_noise(self):
        output = clean_cli_output(
            "成功: 已终止 PID 4956 (属于 PID 12336 子进程)的进程。\n"
            "\ufffd\u0279\ufffd: \ufffd\ufffd\ufffd\ufffdֹ PID 12336 "
            "(\ufffd\ufffd\ufffd\ufffd PID 6340 \ufffdӽ\ufffd\ufffd\ufffd)\ufffdĽ\ufffd\ufffd̡\ufffd\n"
            "codex 在线。"
        )

        self.assertEqual(output, "codex 在线。")

    def test_first_sentence_falls_back_to_first_compact_line(self):
        reply = first_sentence("agent:pi 已连接 — 状态报告\n\n项目 | 状态")

        self.assertEqual(reply, "agent:pi 已连接 — 状态报告")

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

    def test_run_cli_command_can_pass_prompt_as_final_argv(self):
        async def scenario():
            return await run_cli_command(
                [sys.executable, "-c", "import sys; print('ARGV:' + sys.argv[1])"],
                "hello argv",
                cwd=Path.cwd(),
                timeout=5,
                prompt_transport="argv",
            )

        result = asyncio.run(scenario())

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ARGV:hello argv")

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

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            self.assertEqual(command, ["pi", "run"])
            self.assertIn("say ok", prompt)
            self.assertIn("pi CLI agent", prompt)
            self.assertEqual(prompt_transport, "argv")
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
                    prompt_transport="argv",
                )
                return handled, client
            finally:
                cli_bridge.run_cli_command = original

        handled, client = asyncio.run(scenario())

        self.assertTrue(handled)
        self.assertEqual(client.claimed, [(12, "agent:pi:test")])
        self.assertEqual(client.sent, [("OK", ["human:bobo"])])
        self.assertEqual(client.completed, [(12, "succeeded", 99, None)])

    def test_handle_incoming_message_replies_inside_same_group(self):
        class FakeClient:
            def __init__(self):
                self.replies = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 41}

        statuses = []

        async def fake_report_status(status, **kwargs):
            statuses.append((status, kwargs))

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            self.assertIn("TALK group id: group:lab", prompt)
            self.assertIn("group task", prompt)
            return CliRunResult(returncode=0, stdout="group reply", stderr="")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 40,
                        "from": "human:bobo",
                        "to": ["agent:pi"],
                        "group_id": "group:lab",
                        "type": "text",
                        "content": "@agent:pi group task",
                    },
                    client=client,
                    member_id="agent:pi",
                    workdir=Path.cwd(),
                    command=["pi", "run"],
                    timeout=5,
                    max_reply_chars=100,
                    runtime="pi",
                    bridge_label="pi bridge",
                    prompt_transport="argv",
                    report_status=fake_report_status,
                )
                return client
            finally:
                cli_bridge.run_cli_command = original

        client = asyncio.run(scenario())

        self.assertEqual(client.replies, [(40, "group reply", ["human:bobo"], "group:lab")])
        self.assertEqual(statuses[0][0], "busy")
        self.assertEqual(statuses[-1][0], "idle")


if __name__ == "__main__":
    unittest.main()
