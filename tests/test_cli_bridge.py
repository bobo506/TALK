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
    normalize_pi_reply_language,
    parse_talk_actions,
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

    def test_build_cli_task_prompt_for_pi_uses_raw_content(self):
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

        self.assertEqual(prompt, "ask codex to review this too")
        self.assertNotIn("用户任务", prompt)
        self.assertNotIn("回复要求", prompt)
        self.assertNotIn("Task creator:", prompt)
        self.assertNotIn("TALK task id:", prompt)
        self.assertNotIn("Project root:", prompt)

    def test_build_cli_task_prompt_for_pi_keeps_title_as_user_text(self):
        prompt = build_cli_task_prompt(
            {
                "id": 7,
                "created_by": "human:bobo",
                "title": "复盘",
                "content": "总结一下",
            },
            member_id="agent:pi",
            workdir=Path("D:/claude-test/TALK"),
            runtime="pi",
        )

        self.assertEqual(prompt, "标题：复盘\n\n总结一下")

    def test_build_cli_prompt_for_pi_uses_raw_user_text(self):
        prompt = build_cli_prompt({
            "id": 4,
            "from": "human:bobo",
            "content": "@agent:pi 在吗",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertEqual(prompt, "在吗")
        self.assertNotIn("用户消息", prompt)
        self.assertNotIn("回复要求", prompt)
        self.assertNotIn("Sender:", prompt)
        self.assertNotIn("TALK message id:", prompt)
        self.assertNotIn("Project root:", prompt)

    def test_build_cli_prompt_for_pi_does_not_embed_capability_boundary(self):
        prompt = build_cli_prompt({
            "id": 40,
            "from": "human:bobo",
            "content": "@agent:pi 你好啊，你有哪些功能？用中文回复",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertEqual(prompt, "你好啊，你有哪些功能？用中文回复")
        self.assertNotIn("TALK", prompt)
        self.assertNotIn("执行命令", prompt)
        self.assertNotIn("<Language:", prompt)

    def test_build_cli_prompt_for_pi_omits_group_context_when_present(self):
        prompt = build_cli_prompt({
            "id": 8,
            "from": "human:bobo",
            "group_id": "group:lab",
            "content": "@agent:pi 在群里回我",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertEqual(prompt, "在群里回我")
        self.assertNotIn("TALK group id: group:lab", prompt)

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

    def test_normalize_pi_reply_language_replaces_non_chinese_capability_reply(self):
        reply = normalize_pi_reply_language(
            "你好啊，你有哪些功能？用中文回复",
            "Hey there! I'm pi, powered by Claude. I can read files and execute commands.",
        )

        self.assertIn("我是 pi", reply)
        self.assertIn("参与者", reply)
        self.assertIn("默认讨论模式", reply)

    def test_normalize_pi_reply_language_replaces_language_tagged_arabic_reply(self):
        reply = normalize_pi_reply_language(
            "你好啊，你有哪些功能？",
            "<Language: ar> مرحباً! أنا pi.",
        )

        self.assertIn("我是 pi", reply)
        self.assertIn("默认讨论模式", reply)

    def test_normalize_pi_reply_language_keeps_requested_english_reply(self):
        reply = normalize_pi_reply_language(
            "请用英文介绍你有哪些功能",
            "I can chat and help break down tasks.",
        )

        self.assertEqual(reply, "I can chat and help break down tasks.")

    def test_decode_subprocess_output_falls_back_to_windows_codepage(self):
        data = "成功: 已终止 PID 1 (属于 PID 2 子进程)的进程。".encode("gbk")

        self.assertEqual(
            decode_subprocess_output(data),
            "成功: 已终止 PID 1 (属于 PID 2 子进程)的进程。",
        )

    def test_parse_talk_actions_strips_visible_tags(self):
        visible, actions = parse_talk_actions(
            '我来问它。\n<talk-action type="send_message" to="agent:codex" stance="question">请给出下一步计划</talk-action>'
        )

        self.assertEqual(visible, "我来问它。")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, "send_message")
        self.assertEqual(actions[0].to, "agent:codex")
        self.assertEqual(actions[0].stance, "question")
        self.assertEqual(actions[0].body, "请给出下一步计划")

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
            self.assertEqual(prompt, "say ok")
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
            self.assertEqual(prompt, "group task")
            self.assertNotIn("TALK group id: group:lab", prompt)
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

    def test_handle_incoming_message_executes_send_message_action(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.created_discussions = []
                self.turns = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 41}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 42}

            async def list_discussions(self, *, group_id=None):
                return []

            async def create_discussion(self, group_id, topic, participant_ids, *, max_rounds=2):
                self.created_discussions.append((group_id, topic, participant_ids, max_rounds))
                return {"id": 7}

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append((discussion_id, message_id, stance, target_member_id, round_index))
                return {"id": 1}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=0,
                stdout='我去问 codex。\n<talk-action type="send_message" to="agent:codex" stance="question">请给 pi 下一步开发计划</talk-action>',
                stderr="",
            )

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
                        "content": "@agent:pi 请向 codex 要下一步计划",
                    },
                    client=client,
                    member_id="agent:pi",
                    workdir=Path.cwd(),
                    command=["pi", "run"],
                    timeout=5,
                    max_reply_chars=400,
                    runtime="pi",
                    bridge_label="pi bridge",
                    prompt_transport="argv",
                )
                return client
            finally:
                cli_bridge.run_cli_command = original

        client = asyncio.run(scenario())

        self.assertEqual(client.sent, [("@agent:codex 请给 pi 下一步开发计划", ["agent:codex"], 40, "group:lab")])
        self.assertEqual(client.created_discussions[0][0], "group:lab")
        self.assertEqual(client.created_discussions[0][2], ["agent:pi", "agent:codex"])
        self.assertEqual(client.turns, [(7, 42, "question", "agent:codex", 1)])
        self.assertEqual(client.replies, [(40, "我去问 codex。", ["human:bobo"], "group:lab")])

    def test_handle_incoming_message_escalates_after_two_disagree_turns(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.turns = [
                    {"speaker_id": "agent:codex", "stance": "disagree"},
                ]

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 51}

            async def list_discussions(self, *, group_id=None):
                return [{
                    "id": 9,
                    "status": "active",
                    "participant_ids": ["agent:codex", "agent:pi"],
                }]

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append({"speaker_id": "agent:pi", "stance": stance})
                return {"id": 2}

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:codex"}, {"member_id": "agent:pi"}]}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 52}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=0,
                stdout='我仍然不同意，建议先补协议测试。\n<talk-action type="mark_stance" stance="disagree"></talk-action>',
                stderr="",
            )

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 50,
                        "from": "agent:codex",
                        "to": ["agent:pi"],
                        "group_id": "group:lab",
                        "type": "text",
                        "content": "@agent:pi 我不同意你的方案",
                    },
                    client=client,
                    member_id="agent:pi",
                    workdir=Path.cwd(),
                    command=["pi", "run"],
                    timeout=5,
                    max_reply_chars=400,
                    runtime="pi",
                    bridge_label="pi bridge",
                    prompt_transport="argv",
                )
                return client
            finally:
                cli_bridge.run_cli_command = original

        client = asyncio.run(scenario())

        self.assertEqual(client.replies, [(50, "我仍然不同意，建议先补协议测试。", ["agent:codex"], "group:lab")])
        self.assertEqual(
            client.sent,
            [("@human:bobo 我和对方连续两轮仍有不同判断，请你做最终决定。", ["human:bobo"], 51, "group:lab")],
        )

    def test_handle_incoming_message_normalizes_pi_chinese_capability_reply(self):
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
            self.assertEqual(prompt, "你好啊，你有哪些功能？用中文回复")
            return CliRunResult(
                returncode=0,
                stdout="Hey there! I'm pi, powered by Claude. I can read files and execute commands.",
                stderr="",
            )

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
                        "content": "@agent:pi 你好啊，你有哪些功能？用中文回复",
                    },
                    client=client,
                    member_id="agent:pi",
                    workdir=Path.cwd(),
                    command=["pi", "run"],
                    timeout=5,
                    max_reply_chars=400,
                    runtime="pi",
                    bridge_label="pi bridge",
                    prompt_transport="argv",
                    report_status=fake_report_status,
                )
                return client
            finally:
                cli_bridge.run_cli_command = original

        client = asyncio.run(scenario())

        self.assertIn("我是 pi", client.replies[0][1])
        self.assertIn("不会读取项目文件", client.replies[0][1])
        self.assertEqual(client.replies[0][3], "group:lab")


if __name__ == "__main__":
    unittest.main()
