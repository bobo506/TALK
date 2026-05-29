import asyncio
import contextlib
import io
import sys
import unittest
from pathlib import Path

from bridges import cli_bridge
from TALK.client.exceptions import TalkNotFoundError
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

        self.assertIn("ask codex to review this too", prompt)
        self.assertIn("你的身份：agent:pi", prompt)
        # 5.3 P1：[系统] 块在 prompt 开头（高权重位置），任务正文紧随其后
        self.assertTrue(prompt.startswith("[系统]"))
        self.assertIn("[任务]", prompt)
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

        self.assertIn("标题：复盘", prompt)
        self.assertIn("总结一下", prompt)
        self.assertIn("你的身份：agent:pi", prompt)
        self.assertTrue(prompt.startswith("[系统]"))

    def test_build_cli_prompt_for_pi_uses_raw_user_text(self):
        prompt = build_cli_prompt({
            "id": 4,
            "from": "human:bobo",
            "content": "@agent:pi 在吗",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        # 5.3 P1：[系统] 块在 prompt 开头，用户消息紧随 [用户消息] 标签后
        self.assertTrue(prompt.startswith("[系统]"))
        self.assertIn("[用户消息]\n在吗", prompt)
        self.assertIn("你的身份：agent:pi", prompt)
        self.assertNotIn("回复要求", prompt)
        self.assertNotIn("Sender:", prompt)
        self.assertNotIn("TALK message id:", prompt)
        self.assertNotIn("Project root:", prompt)

    def test_build_cli_prompt_strips_leading_mention_cluster_for_pi(self):
        prompt = build_cli_prompt({
            "id": 4,
            "from": "human:bobo",
            "content": "@agent:pi @agent:codex 我觉得这个对话系统还需要完善",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue(prompt.startswith("[系统]"))
        self.assertIn("[用户消息]\n我觉得这个对话系统还需要完善", prompt)
        self.assertIn("你的身份：agent:pi", prompt)

    def test_build_cli_prompt_keeps_mid_sentence_mentions(self):
        prompt = build_cli_prompt({
            "id": 4,
            "from": "human:bobo",
            "content": "@agent:pi 请去问 @agent:codex 能不能看一下",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue(prompt.startswith("[系统]"))
        self.assertIn("[用户消息]\n请去问 @agent:codex 能不能看一下", prompt)
        self.assertIn("你的身份：agent:pi", prompt)

    def test_build_cli_prompt_for_pi_does_not_embed_capability_boundary(self):
        prompt = build_cli_prompt({
            "id": 40,
            "from": "human:bobo",
            "content": "@agent:pi 你好啊，你有哪些功能？用中文回复",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue(prompt.startswith("[系统]"))
        self.assertIn("[用户消息]\n你好啊，你有哪些功能？用中文回复", prompt)
        self.assertIn("你的身份：agent:pi", prompt)
        self.assertNotIn("执行命令", prompt)
        self.assertNotIn("<Language:", prompt)

    def test_build_cli_prompt_for_pi_omits_group_context_when_present(self):
        prompt = build_cli_prompt({
            "id": 8,
            "from": "human:bobo",
            "group_id": "group:lab",
            "content": "@agent:pi 在群里回我",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue(prompt.startswith("[系统]"))
        self.assertIn("[用户消息]\n在群里回我", prompt)
        self.assertIn("你的身份：agent:pi", prompt)
        self.assertNotIn("TALK group id: group:lab", prompt)

    def test_build_cli_prompt_for_pi_includes_role_restraint_instructions(self):
        """5.3 P1 回归：pi prompt 必须包含'回复克制'指引（之前 pi 完全没拿到 RESPONSE_STYLE 类指引）。"""
        prompt = build_cli_prompt({
            "id": 9,
            "from": "human:qa",
            "content": "@agent:pi 你去和 codex 打个招呼",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertIn("回复克制", prompt)
        self.assertIn("一两句话", prompt)
        self.assertIn("不要追问", prompt)

    def test_build_cli_prompt_for_pi_injects_group_member_context_at_top(self):
        """5.3 P1 回归：group_member_context 必须出现在 [系统] 块内，位于 prompt 开头。"""
        group_ctx = (
            "\n[当前群成员 — 只能提及以下成员]\n"
            "  human:qa（QA Tester）\n"
            "  agent:pi\n"
            "  agent:codex\n\n"
            "本群无角色约定，只严格回应字面请求，不要主动扩展话题，"
            "不要假设这是项目讨论环境，不要指名群外成员。\n"
        )
        prompt = build_cli_prompt(
            {
                "id": 10,
                "from": "human:qa",
                "group_id": "group:bbtest",
                "content": "@agent:pi 介绍下你自己",
            },
            member_id="agent:pi",
            workdir=Path("D:/claude-test/TALK"),
            runtime="pi",
            group_member_context=group_ctx,
        )

        # 群成员清单必须出现在 [用户消息] 之前（即权重高的位置）
        idx_system = prompt.find("[系统]")
        idx_member_list = prompt.find("[当前群成员")
        idx_user = prompt.find("[用户消息]")
        self.assertGreaterEqual(idx_system, 0)
        self.assertGreater(idx_member_list, idx_system)
        self.assertGreater(idx_user, idx_member_list)
        self.assertIn("human:qa", prompt)
        self.assertIn("本群无角色约定", prompt)

    def test_format_cli_reply_uses_bridge_label(self):
        reply = format_cli_reply(
            CliRunResult(returncode=2, stdout="out", stderr="boom\nTraceback\nD:\\claude-test\\TALK\\x.py"),
            max_chars=200,
            bridge_label="pi bridge",
        )

        self.assertIn("pi bridge 运行失败", reply)
        self.assertNotIn("stderr", reply)
        self.assertNotIn("stdout", reply)
        self.assertNotIn("D:\\", reply)
        self.assertNotIn("Traceback", reply)

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

    def test_parse_talk_actions_accepts_safe_action_lines_and_final_to_human(self):
        visible, actions = parse_talk_actions(
            "结论如下。\n"
            "TALK_ACTION mark_stance stance=agree\n"
            "TALK_ACTION final_to_human to=human:bobo body=人类是长期演化来的。"
        )

        self.assertEqual(visible, "结论如下。")
        self.assertEqual([action.action_type for action in actions], ["mark_stance", "final_to_human"])
        self.assertEqual(actions[0].stance, "agree")
        self.assertEqual(actions[1].to, "human:bobo")
        self.assertEqual(actions[1].body, "人类是长期演化来的。")

    def test_parse_talk_actions_cleans_protocol_fragments_from_visible_text(self):
        visible, actions = parse_talk_actions(
            "mark_stance 动作已记录，当前立场为 agree。\n\n"
            "以下是对三条建议的回应。\n"
            "update\n"
            "TALK_ACTION mark_stance stance=agree"
        )

        self.assertEqual(visible, "以下是对三条建议的回应。")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, "mark_stance")

    def test_parse_talk_actions_drops_invalid_actions(self):
        visible, actions = parse_talk_actions(
            "可见内容\nTALK_ACTION rewrite_files to=agent:pi body=不要执行"
        )

        self.assertEqual(visible, "可见内容")
        self.assertEqual(actions, [])

    def test_malformed_action_residue_is_not_posted_visibly(self):
        class FakeClient:
            def __init__(self):
                self.replies = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 41}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=0,
                stdout="我先问一下。\n\n**TALK_ACTION send_message to=agent:uxwriter stance=question body=请确认上下文**",
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
                        "content": "@agent:pi 检查按钮文案",
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

        self.assertEqual(client.replies, [(40, "我需要先确认当前请求范围后再继续。", ["human:bobo"], "group:lab")])

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
            self.assertIn("你的身份：agent:pi", prompt)
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

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:pi"}]}

        statuses = []

        async def fake_report_status(status, **kwargs):
            statuses.append((status, kwargs))

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            self.assertIn("group task", prompt)
            self.assertIn("你的身份：agent:pi", prompt)
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

            async def create_discussion(self, group_id, topic, participant_ids, *, max_rounds=2, **kwargs):
                self.created_discussions.append((group_id, topic, participant_ids, max_rounds, kwargs))
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
        self.assertEqual(client.created_discussions[0][4]["root_message_id"], 42)
        self.assertEqual(client.created_discussions[0][4]["requester_id"], "agent:pi")
        self.assertEqual(client.created_discussions[0][4]["assignee_id"], "agent:codex")
        self.assertEqual(client.created_discussions[0][4]["scope_text"], "请给 pi 下一步开发计划")
        self.assertEqual(client.turns, [(7, 42, "question", "agent:codex", 1)])
        self.assertEqual(client.replies, [(40, "我去问 codex。", ["human:bobo"], "group:lab")])

    def test_greeting_send_message_action_records_non_substantive_turn(self):
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

            async def create_discussion(self, group_id, topic, participant_ids, *, max_rounds=2, **kwargs):
                self.created_discussions.append((group_id, topic, participant_ids, max_rounds, kwargs))
                return {"id": 7}

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append((discussion_id, message_id, stance, target_member_id, round_index))
                return {"id": 1}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=0,
                stdout='我去打个招呼。\nTALK_ACTION send_message to=agent:codex stance=question body=你好 codex，我是 pi，来打个招呼。',
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
                        "content": "@agent:pi 你去和 codex 打个招呼",
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

        self.assertEqual(client.sent, [("@agent:codex 你好 codex，我是 pi，来打个招呼。", ["agent:codex"], 40, "group:lab")])
        self.assertEqual(client.turns, [(7, 42, "greeting", "agent:codex", 1)])

    def test_reply_stance_defaults_to_answer(self):
        self.assertEqual(cli_bridge.infer_reply_stance("请给 pi 下一步开发计划", "可以，我建议先补测试。"), "answer")
        self.assertEqual(cli_bridge.infer_reply_stance("你去和 codex 打个招呼", "你好，我在线。"), "greeting")
        self.assertEqual(cli_bridge.infer_discussion_stance("请给 pi 下一步开发计划", "可以，我建议先补测试。", default=""), "answer")

    def test_non_substantive_turn_filter_excludes_greeting_and_closure(self):
        turns = [
            {"stance": "greeting"},
            {"stance": "closure"},
            {"stance": "answer"},
            {"stance": ""},
        ]

        self.assertEqual(cli_bridge._substantive_discussion_turns(turns), [{"stance": "answer"}, {"stance": ""}])

    def test_send_message_action_to_missing_group_agent_is_blocked(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 41}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 42}

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:pi"}, {"member_id": "agent:codex"}]}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=0,
                stdout=(
                    "我去问 uxwriter。\n"
                    "TALK_ACTION send_message to=agent:uxwriter stance=question body=请确认按钮文案上下文"
                ),
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
                        "content": "@agent:pi 请检查按钮文案",
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

        self.assertEqual(client.sent, [])
        self.assertEqual(
            client.replies,
            [
                (40, "我去问 uxwriter。", ["human:bobo"], "group:lab"),
                (40, "当前 Group 里没有 agent:uxwriter，我不能代发；请确认是否需要我直接处理。", ["human:bobo"], "group:lab"),
            ],
        )

    def test_send_message_action_degrades_when_discussion_api_is_missing(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 41}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 42}

            async def list_discussions(self, *, group_id=None):
                raise TalkNotFoundError("Not Found", status_code=404)

            async def create_discussion(self, group_id, topic, participant_ids, *, max_rounds=2):
                raise TalkNotFoundError("Not Found", status_code=404)

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                raise AssertionError("append_discussion_turn should not be called without a discussion id")

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=0,
                stdout='<talk-action type="send_message" to="agent:codex" stance="question">请问 pi 的问题</talk-action>',
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
                        "content": "@agent:pi 去问 codex",
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

        self.assertEqual(client.sent, [("@agent:codex 请问 pi 的问题", ["agent:codex"], 40, "group:lab")])
        self.assertEqual(client.replies, [])

    def test_action_only_agent_message_does_not_post_default_reply(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.turns = [{"speaker_id": "agent:codex", "stance": "question"}]

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 41}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 42}

            async def list_discussions(self, *, group_id=None):
                return [{
                    "id": 7,
                    "status": "active",
                    "topic": "人类是怎么进化来的？",
                    "participant_ids": ["agent:codex", "agent:pi"],
                }]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def create_discussion(self, group_id, topic, participant_ids, *, max_rounds=2):
                raise AssertionError("final_to_human should reuse the active discussion")

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:codex"}, {"member_id": "agent:pi"}]}

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append({"speaker_id": "agent:pi", "stance": stance})
                return {"id": 2}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            self.assertIn("scope_text: 人类是怎么进化来的？", prompt)
            self.assertIn("current_message_text: 你怎么看？", prompt)
            self.assertIn("不要在可见回复中复述字段名或 ID", prompt)
            return CliRunResult(
                returncode=0,
                stdout="TALK_ACTION send_message to=agent:codex stance=question body=请确认最终答案",
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
                        "content": "@agent:pi 你怎么看？",
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

        self.assertEqual(client.replies, [])
        self.assertEqual(client.sent, [("@agent:codex 请确认最终答案", ["agent:codex"], 50, "group:lab")])

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

    def test_final_to_human_action_resolves_discussion(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.updated = []
                self.turns = [
                    {"speaker_id": "agent:pi", "stance": "answer"},
                    {"speaker_id": "agent:codex", "stance": "optimize"},
                ]

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 51}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 52}

            async def list_discussions(self, *, group_id=None):
                return [{
                    "id": 9,
                    "status": "active",
                    "topic": "人类是怎么进化来的？",
                    "participant_ids": ["agent:codex", "agent:pi"],
                }]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:codex"}, {"member_id": "agent:pi"}]}

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append({"speaker_id": "agent:codex", "stance": stance})
                return {"id": 3}

            async def update_discussion(self, discussion_id, *, status):
                self.updated.append((discussion_id, status))
                return {"id": discussion_id, "status": status}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=0,
                stdout=(
                    "TALK_ACTION mark_stance stance=agree\n"
                    "TALK_ACTION final_to_human to=human:bobo body=人类是从远古灵长类分支长期演化来的。"
                ),
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
                        "from": "agent:pi",
                        "to": ["agent:codex"],
                        "group_id": "group:lab",
                        "type": "text",
                        "content": "@agent:codex 我同意你的微调",
                    },
                    client=client,
                    member_id="agent:codex",
                    workdir=Path.cwd(),
                    command=["codex", "exec", "-"],
                    timeout=5,
                    max_reply_chars=400,
                    runtime="Codex",
                    bridge_label="Codex bridge",
                )
                return client
            finally:
                cli_bridge.run_cli_command = original

        client = asyncio.run(scenario())

        self.assertEqual(client.replies, [])
        self.assertEqual(
            client.sent,
            [("@human:bobo 人类是从远古灵长类分支长期演化来的。", ["human:bobo"], 50, "group:lab")],
        )
        self.assertEqual(client.updated, [(9, "resolved")])

    def test_agent_message_after_extension_answer_closes_without_running_model(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.updated = []
                self.turns = [
                    {"speaker_id": "agent:codex", "stance": "question"},
                    {"speaker_id": "agent:pi", "stance": "answer"},
                    {"speaker_id": "agent:codex", "stance": "optimize"},
                    {"speaker_id": "agent:pi", "stance": "answer"},
                ]

            async def list_discussions(self, *, group_id=None):
                return [{
                    "id": 9,
                    "status": "active",
                    "topic": "人类是怎么进化来的？",
                    "participant_ids": ["agent:codex", "agent:pi"],
                }]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:codex"}, {"member_id": "agent:pi"}]}

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 52}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 53}

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append({"speaker_id": "agent:pi", "stance": stance})
                return {"id": 4}

            async def update_discussion(self, discussion_id, *, status):
                self.updated.append((discussion_id, status))
                return {"id": discussion_id, "status": status}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            raise AssertionError("model should not run after turn budget is exhausted")

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
                        "content": "@agent:pi 需要继续吗？",
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

        self.assertEqual(
            client.replies,
            [(50, cli_bridge._pick_closure_line("agent:pi"), ["agent:codex"], "group:lab")],
        )
        self.assertEqual(client.sent, [])
        self.assertEqual(client.updated, [(9, "resolved")])
        self.assertEqual(client.turns[-1]["stance"], "closure")

    def test_non_substantive_greeting_turns_do_not_trigger_closure(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.updated = []
                self.turns = [
                    {"speaker_id": "agent:pi", "stance": "greeting"},
                    {"speaker_id": "agent:codex", "stance": "greeting"},
                    {"speaker_id": "agent:pi", "stance": "closure"},
                    {"speaker_id": "agent:codex", "stance": "closure"},
                ]

            async def list_discussions(self, *, group_id=None):
                return [{
                    "id": 9,
                    "status": "active",
                    "topic": "打招呼",
                    "participant_ids": ["agent:codex", "agent:pi"],
                }]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:codex"}, {"member_id": "agent:pi"}]}

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 52}

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append({"speaker_id": "agent:pi", "stance": stance})
                return {"id": 5}

            async def update_discussion(self, discussion_id, *, status):
                self.updated.append((discussion_id, status))
                return {"id": discussion_id, "status": status}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(returncode=0, stdout="你好，我在线。", stderr="")

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
                        "content": "@agent:pi 你好，还在线吗？",
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

        self.assertEqual(client.replies, [(50, "你好，我在线。", ["agent:codex"], "group:lab")])
        self.assertEqual(client.updated, [])

    def test_agent_message_at_extension_budget_allows_one_more_answer(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.turns = [
                    {"speaker_id": "agent:codex", "stance": "question"},
                    {"speaker_id": "agent:pi", "stance": "answer"},
                    {"speaker_id": "agent:codex", "stance": "optimize"},
                ]

            async def list_discussions(self, *, group_id=None):
                return [{
                    "id": 9,
                    "status": "active",
                    "topic": "打招呼",
                    "participant_ids": ["agent:codex", "agent:pi"],
                }]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:codex"}, {"member_id": "agent:pi"}]}

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 52}

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append({"speaker_id": "agent:pi", "stance": stance})
                return {"id": 4}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(returncode=0, stdout="可以，先停在打招呼这里。", stderr="")

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
                        "content": "@agent:pi 我只是回应一下这个扩展问题",
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

        self.assertEqual(client.replies, [(50, "可以，先停在打招呼这里。", ["agent:codex"], "group:lab")])

    def test_agent_reply_to_resolved_scope_does_not_start_new_topic(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.turns = [
                    {"message_id": 120, "speaker_id": "agent:pi", "stance": "question"},
                    {"message_id": 122, "speaker_id": "agent:codex", "stance": "agree"},
                ]

            async def list_discussions(self, *, group_id=None):
                return [{
                    "id": 3,
                    "status": "resolved",
                    "topic": "打个招呼",
                    "participant_ids": ["agent:pi", "agent:codex"],
                    "root_message_id": 120,
                    "requester_id": "agent:pi",
                    "assignee_id": "agent:codex",
                    "scope_text": "嗨 Codex，我是 pi，跟你打个招呼。",
                }]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 130}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 131}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            raise AssertionError("resolved scope should not run the model")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 124,
                        "from": "agent:pi",
                        "to": ["agent:codex"],
                        "reply_to": {"id": 122},
                        "group_id": "group:lab",
                        "type": "text",
                        "content": "有什么想聊聊的，或者需要我协助的地方，尽管说！",
                    },
                    client=client,
                    member_id="agent:codex",
                    workdir=Path.cwd(),
                    command=["codex", "exec", "-"],
                    timeout=5,
                    max_reply_chars=400,
                    runtime="Codex",
                    bridge_label="Codex bridge",
                )
                return client
            finally:
                cli_bridge.run_cli_command = original

        client = asyncio.run(scenario())

        self.assertEqual(client.replies, [])
        self.assertEqual(client.sent, [])

    def test_agent_request_scope_prompt_and_plain_reply_turn(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.turns = []
                self.created = []

            async def list_discussions(self, *, group_id=None):
                return []

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def create_discussion(self, group_id, topic, participant_ids, *, max_rounds=2, **kwargs):
                self.created.append((group_id, topic, participant_ids, kwargs))
                return {"id": 12}

            async def get_discussion(self, discussion_id):
                return {
                    "id": discussion_id,
                    "status": "active",
                    "topic": "检查按钮文案",
                    "participant_ids": ["agent:codex", "agent:pi"],
                    "root_message_id": 60,
                    "requester_id": "agent:codex",
                    "assignee_id": "agent:pi",
                    "scope_text": "请检查这个按钮文案是否清楚",
                }

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:codex"}, {"member_id": "agent:pi"}]}

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 61}

            async def append_discussion_turn(self, discussion_id, *, message_id, stance, target_member_id=None, round_index=1):
                self.turns.append((discussion_id, message_id, stance, target_member_id, round_index))
                return {"id": len(self.turns)}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            self.assertIn("requester_id: agent:codex", prompt)
            self.assertIn("assignee_id: agent:pi", prompt)
            self.assertIn("scope_text: 请检查这个按钮文案是否清楚", prompt)
            self.assertIn("current_message_text: 请检查这个按钮文案是否清楚", prompt)
            return CliRunResult(returncode=0, stdout="这个按钮文案清楚，但可以更短。", stderr="")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 60,
                        "from": "agent:codex",
                        "to": ["agent:pi"],
                        "group_id": "group:lab",
                        "type": "text",
                        "content": "@agent:pi 请检查这个按钮文案是否清楚",
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

        self.assertEqual(client.created[0][3]["root_message_id"], 60)
        self.assertEqual(client.created[0][3]["requester_id"], "agent:codex")
        self.assertEqual(client.created[0][3]["assignee_id"], "agent:pi")
        self.assertEqual(client.replies, [(60, "这个按钮文案清楚，但可以更短。", ["agent:codex"], "group:lab")])
        self.assertEqual(client.turns, [(12, 61, "answer", "agent:codex", 1)])

    def test_internal_scope_fields_are_not_posted_visibly(self):
        class FakeClient:
            def __init__(self):
                self.replies = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 41}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            return CliRunResult(
                returncode=0,
                stdout="根据 discussion_id=7 和 root_message_id=60，我认为 scope_text 是检查按钮。",
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
                        "to": ["agent:codex"],
                        "group_id": "group:lab",
                        "type": "text",
                        "content": "@agent:codex 看看这个文案",
                    },
                    client=client,
                    member_id="agent:codex",
                    workdir=Path.cwd(),
                    command=["codex", "exec", "-"],
                    timeout=5,
                    max_reply_chars=400,
                    runtime="Codex",
                    bridge_label="Codex bridge",
                )
                return client
            finally:
                cli_bridge.run_cli_command = original

        client = asyncio.run(scenario())

        self.assertEqual(client.replies, [(40, "我需要先确认当前请求范围后再继续。", ["human:bobo"], "group:lab")])

    def test_handle_incoming_message_normalizes_pi_chinese_capability_reply(self):
        class FakeClient:
            def __init__(self):
                self.replies = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 41}

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:bobo"}, {"member_id": "agent:pi"}]}

        statuses = []

        async def fake_report_status(status, **kwargs):
            statuses.append((status, kwargs))

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            self.assertIn("你好啊，你有哪些功能？用中文回复", prompt)
            self.assertIn("你的身份：agent:pi", prompt)
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
