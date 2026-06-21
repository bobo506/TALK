import asyncio
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

from bridges import cli_bridge
from TALK.client.exceptions import TalkNotFoundError
from bridges.cli_bridge import (
    _build_group_member_context,
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
        self.assertIn("human:bobo 对你说:", prompt)
        self.assertIn("agent:pi", prompt)  # 身份锚:identity in per-call prompt
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

        self.assertIn("复盘", prompt)
        self.assertIn("总结一下", prompt)
        self.assertIn("human:bobo 对你说:", prompt)
        self.assertIn("agent:pi", prompt)  # 身份锚:identity in per-call prompt

    def test_build_cli_prompt_for_pi_uses_raw_user_text(self):
        prompt = build_cli_prompt({
            "id": 4,
            "from": "human:bobo",
            "content": "@agent:pi 在吗",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue("human:bobo 对你说:在吗" in prompt)
        # identity no longer in prompt
        self.assertIn("agent:pi", prompt)  # 身份锚:identity in per-call prompt
        self.assertNotIn("Sender:", prompt)
        self.assertNotIn("TALK message id:", prompt)
        self.assertNotIn("Project root:", prompt)

    def test_build_cli_prompt_injects_identity_inline(self):
        """身份锚必须出现在 per-call prompt 里,且**紧凑内嵌**而非独占首行。
        历史教训(2026-06-06 黑盒实测):身份独占首行 + 大段括号注释会让 pi 陷入"自我介绍"
        模式,忽略任务动词。改回身份和任务同一行的紧凑写法。
        参考 INTERACTION_FRAMEWORK §5.3 修正记录。
        """
        prompt = build_cli_prompt({
            "id": 5,
            "from": "human:qa",
            "content": "@agent:pi-kimi 你忙不忙",
        }, member_id="agent:pi-kimi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        # 身份必须出现,且明确告诉模型"你是 agent:pi-kimi"
        self.assertIn("你是 agent:pi-kimi", prompt)
        # 任务必须直接跟在身份后(同一行),让动词获得焦点
        self.assertIn("你是 agent:pi-kimi。human:qa 对你说:你忙不忙", prompt)

    def test_build_cli_task_prompt_for_pi_injects_identity(self):
        """任务路径同样要注入身份,跟 build_cli_prompt 一致(同一行紧凑写法)。"""
        prompt = build_cli_task_prompt({
            "id": 7,
            "created_by": "human:qa",
            "content": "整理一下今天的进度",
        }, member_id="agent:pi-kimi", workdir=Path("D:/claude-test/TALK"), runtime="pi")
        self.assertIn("你是 agent:pi-kimi。human:qa 对你说:整理一下今天的进度", prompt)

    def test_build_cli_prompt_strips_leading_mention_cluster_for_pi(self):
        prompt = build_cli_prompt({
            "id": 4,
            "from": "human:bobo",
            "content": "@agent:pi @agent:codex 我觉得这个对话系统还需要完善",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue("human:bobo 对你说:我觉得这个对话系统还需要完善" in prompt)
        self.assertNotIn("@agent:pi", prompt)  # leading mention cluster stripped from task
        self.assertNotIn("@agent:codex", prompt)
        self.assertIn("agent:pi", prompt)  # 身份锚仍在(identity line,非 @mention)

    def test_build_cli_prompt_keeps_mid_sentence_mentions(self):
        prompt = build_cli_prompt({
            "id": 4,
            "from": "human:bobo",
            "content": "@agent:pi 请去问 @agent:codex 能不能看一下",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue("请去问 @agent:codex 能不能看一下" in prompt)
        self.assertNotIn("工具：", prompt)

    def test_build_cli_prompt_for_pi_does_not_embed_capability_boundary(self):
        prompt = build_cli_prompt({
            "id": 40,
            "from": "human:bobo",
            "content": "@agent:pi 你好啊，你有哪些功能？用中文回复",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue("human:bobo 对你说:你好啊" in prompt)
        # identity no longer in prompt
        self.assertNotIn("执行命令", prompt)
        self.assertNotIn("<Language:", prompt)

    def test_build_cli_prompt_for_pi_omits_group_context_when_present(self):
        prompt = build_cli_prompt({
            "id": 8,
            "from": "human:bobo",
            "group_id": "group:lab",
            "content": "@agent:pi 在群里回我",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        self.assertTrue("human:bobo 对你说:在群里回我" in prompt)
        # identity no longer in prompt
        self.assertNotIn("当前群 ID", prompt)

    def test_build_cli_prompt_for_pi_does_not_duplicate_restraint_instructions(self):
        """5.3 热修：'回复克制'语义规则应当只由 pi system prompt 承载，cli_bridge 不再重复注入。

        上一轮把'回复克制'同时塞进 DEFAULT_SYSTEM_PROMPT 和 cli_bridge 的 [系统] 块，
        双重指令导致 pi 把'用户派我去联系另一个 agent'误判为'打招呼克制'而不执行 TALK_ACTION。
        本测试断言 cli_bridge 不再注入该指令，避免双重压制。
        """
        prompt = build_cli_prompt({
            "id": 9,
            "from": "human:qa",
            "content": "@agent:pi 你去和 codex 打个招呼",
        }, member_id="agent:pi", workdir=Path("D:/claude-test/TALK"), runtime="pi")

        # 极简格式：无身份声明，用户消息在前
        # 5.5 方案 D：旧"回复克制"语义已移除，不再双重压制 pi 执行 talk_send
        self.assertNotIn("回复克制", prompt)
        self.assertNotIn("不要追问", prompt)
        self.assertNotIn("talk_send", prompt)
        # 5.5 codex 统一 prompt："一两句话"作为行为指引保留（非克制语义）

    def test_build_cli_prompt_for_pi_injects_group_member_context_at_top(self):
        """5.5：群成员上下文出现在背景信息块中"""
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

        self.assertTrue("human:qa 对你说:" in prompt)
        self.assertIn("human:qa", prompt)
        self.assertIn("本群无角色约定", prompt)

    def test_group_member_context_injects_self_business_role(self):
        """P3-2：群成员上下文带上"我在本群的业务角色"（business_role 来自群成员数据）。"""
        class FakeClient:
            async def get_group(self, group_id):
                return {"members": [
                    {"member_id": "human:qa"},
                    {"member_id": "agent:pi", "business_role": "reviewer"},
                ]}

        ctx = asyncio.run(_build_group_member_context(FakeClient(), "group:lab", "agent:pi"))
        self.assertIn("群成员：human:qa, agent:pi。", ctx)
        self.assertIn("你在本群的业务角色：reviewer。", ctx)

    def test_group_member_context_omits_role_when_absent(self):
        """无 business_role 时不注入角色行（保持现状字节）。"""
        class FakeClient:
            async def get_group(self, group_id):
                return {"members": [
                    {"member_id": "human:qa"},
                    {"member_id": "agent:pi"},
                ]}

        ctx = asyncio.run(_build_group_member_context(FakeClient(), "group:lab", "agent:pi"))
        self.assertIn("群成员：", ctx)
        self.assertNotIn("你在本群的业务角色", ctx)

    def test_function_calling_prompt_is_minimal(self):
        message = {
            "id": 1,
            "from": "human:qa",
            "content": "@agent:pi 去跟agent:pi-kimi打个招呼",
            "group_id": "g1",
        }
        prompt = build_cli_prompt(
            message,
            member_id="agent:pi",
            workdir=Path("."),
            runtime="pi",
            group_member_context="群成员:human:qa, agent:pi, agent:pi-kimi。\n",
        )

        self.assertLess(len(prompt), 200)
        self.assertIn("human:qa 对你说:去跟agent:pi-kimi打个招呼", prompt)
        self.assertNotIn("不存在下一轮", prompt)
        self.assertNotIn("反工具幻觉", prompt)
        self.assertNotIn("输出通道", prompt)
        self.assertNotIn("talk_send", prompt)

    def test_function_calling_prompt_does_not_depend_on_tool_catalog(self):
        message = {
            "id": 1,
            "from": "human:qa",
            "content": "@agent:pi 去跟agent:pi-kimi打个招呼",
            "group_id": "g1",
        }
        old_command = os.environ.get("TALK_PI_COMMAND")
        try:
            os.environ["TALK_PI_COMMAND"] = "pi --tools talk_send"
            prompt_one_tool = build_cli_prompt(message, member_id="agent:pi", workdir=Path("."), runtime="pi")
            os.environ["TALK_PI_COMMAND"] = "pi --tools talk_send,talk_create_task"
            prompt_two_tools = build_cli_prompt(message, member_id="agent:pi", workdir=Path("."), runtime="pi")
        finally:
            if old_command is None:
                os.environ.pop("TALK_PI_COMMAND", None)
            else:
                os.environ["TALK_PI_COMMAND"] = old_command

        self.assertEqual(prompt_one_tool, prompt_two_tools)

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
            # identity no longer in prompt
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
            # identity no longer in prompt
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

    def test_deferred_talk_send_records_demand_round_one(self):
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

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:qa"}, {"member_id": "agent:pi"}, {"member_id": "agent:pi-kimi"}]}

            async def list_discussions(self, *, group_id=None):
                return []

            async def create_discussion(self, group_id, topic, participant_ids, *, max_rounds=2, **kwargs):
                self.created_discussions.append((group_id, topic, participant_ids, max_rounds, kwargs))
                return {"id": 7}

            async def append_discussion_turn(
                self, discussion_id, *, message_id, stance, target_member_id=None, turn_kind="reply", round_index=1
            ):
                self.turns.append((discussion_id, message_id, stance, target_member_id, turn_kind, round_index))
                return {"id": len(self.turns)}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            path = os.environ.get("TALK_DEFERRED_FILE")
            assert path
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"tool": "talk_send", "target": "agent:pi-kimi", "body": "你好", "stance": "greeting"}, ensure_ascii=False) + "\n")
            return CliRunResult(returncode=0, stdout="我去打个招呼。", stderr="")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 40,
                        "from": "human:qa",
                        "to": ["agent:pi"],
                        "group_id": "group:lab",
                        "type": "text",
                        "content": "@agent:pi 去跟 agent:pi-kimi 打个招呼",
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

        self.assertEqual(client.sent, [("@agent:pi-kimi 你好", ["agent:pi-kimi"], 40, "group:lab")])
        self.assertEqual(client.turns, [(7, 42, "greeting", "agent:pi-kimi", "demand", 1)])

    def test_round_one_demand_receiver_may_extend_once(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.next_id = 51
                self.turns = [{"message_id": 42, "speaker_id": "agent:pi", "stance": "greeting", "turn_kind": "demand", "round_index": 1}]
                self.appended = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                self.next_id += 1
                return {"id": self.next_id - 1}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                self.next_id += 1
                return {"id": self.next_id - 1}

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:qa"}, {"member_id": "agent:pi"}, {"member_id": "agent:pi-kimi"}]}

            async def list_discussions(self, *, group_id=None):
                return [{"id": 9, "status": "active", "participant_ids": ["agent:pi", "agent:pi-kimi"], "root_message_id": 40}]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def append_discussion_turn(
                self, discussion_id, *, message_id, stance, target_member_id=None, turn_kind="reply", round_index=1
            ):
                item = {
                    "message_id": message_id,
                    "speaker_id": "agent:pi-kimi",
                    "stance": stance,
                    "target_member_id": target_member_id,
                    "turn_kind": turn_kind,
                    "round_index": round_index,
                }
                self.turns.append(item)
                self.appended.append((discussion_id, message_id, stance, target_member_id, turn_kind, round_index))
                return {"id": len(self.turns)}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            path = os.environ.get("TALK_DEFERRED_FILE")
            assert path
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"tool": "talk_send", "target": "agent:pi", "body": "我再确认一个点", "stance": "question"}, ensure_ascii=False) + "\n")
            return CliRunResult(returncode=0, stdout="你好，我再确认一个点。", stderr="")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 42,
                        "from": "agent:pi",
                        "to": ["agent:pi-kimi"],
                        "group_id": "group:lab",
                        "reply_to": 40,
                        "type": "text",
                        "content": "@agent:pi-kimi 你好",
                    },
                    client=client,
                    member_id="agent:pi-kimi",
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

        self.assertEqual(client.sent, [("@agent:pi 我再确认一个点", ["agent:pi"], 42, "group:lab")])
        self.assertEqual([turn[4] for turn in client.appended], ["reply", "demand"])
        self.assertEqual(client.appended[-1], (9, 52, "question", "agent:pi", "demand", 2))

    def test_reply_receiver_may_extend_round_two_from_ledger(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.next_id = 61
                self.turns = [{"message_id": 42, "speaker_id": "agent:pi", "stance": "greeting", "turn_kind": "demand", "round_index": 1}]
                self.appended = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                self.next_id += 1
                return {"id": self.next_id - 1}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                self.next_id += 1
                return {"id": self.next_id - 1}

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:qa"}, {"member_id": "agent:pi"}, {"member_id": "agent:pi-kimi"}]}

            async def list_discussions(self, *, group_id=None):
                return [{"id": 9, "status": "active", "participant_ids": ["agent:pi", "agent:pi-kimi"], "root_message_id": 40}]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def append_discussion_turn(
                self, discussion_id, *, message_id, stance, target_member_id=None, turn_kind="reply", round_index=1
            ):
                item = {
                    "message_id": message_id,
                    "speaker_id": "agent:pi",
                    "stance": stance,
                    "target_member_id": target_member_id,
                    "turn_kind": turn_kind,
                    "round_index": round_index,
                }
                self.turns.append(item)
                self.appended.append((discussion_id, message_id, stance, target_member_id, turn_kind, round_index))
                return {"id": len(self.turns)}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            path = os.environ.get("TALK_DEFERRED_FILE")
            assert path
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"tool": "talk_send", "target": "agent:pi-kimi", "body": "再补一个上下文", "stance": "question"}, ensure_ascii=False) + "\n")
            return CliRunResult(returncode=0, stdout="收到，我补一个上下文。", stderr="")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 60,
                        "from": "agent:pi-kimi",
                        "to": ["agent:pi"],
                        "group_id": "group:lab",
                        "reply_to": 42,
                        "type": "text",
                        "content": "@agent:pi 你好呀",
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

        self.assertEqual(client.sent, [("@agent:pi-kimi 再补一个上下文", ["agent:pi-kimi"], 60, "group:lab")])
        self.assertEqual([turn[4] for turn in client.appended], ["reply", "demand"])
        self.assertEqual(client.appended[-1], (9, 62, "question", "agent:pi-kimi", "demand", 2))

    def test_existing_round_two_demand_blocks_deferred_talk_send(self):
        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.turns = [
                    {"message_id": 42, "speaker_id": "agent:pi", "stance": "greeting", "turn_kind": "demand", "round_index": 1},
                    {"message_id": 52, "speaker_id": "agent:pi-kimi", "stance": "question", "turn_kind": "demand", "round_index": 2},
                ]
                self.appended = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 61}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 62}

            async def get_group(self, group_id):
                return {"members": [{"member_id": "human:qa"}, {"member_id": "agent:pi"}, {"member_id": "agent:pi-kimi"}]}

            async def list_discussions(self, *, group_id=None):
                return [{"id": 9, "status": "active", "participant_ids": ["agent:pi", "agent:pi-kimi"], "root_message_id": 40}]

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def append_discussion_turn(
                self, discussion_id, *, message_id, stance, target_member_id=None, turn_kind="reply", round_index=1
            ):
                self.appended.append((discussion_id, message_id, stance, target_member_id, turn_kind, round_index))
                return {"id": len(self.turns) + len(self.appended)}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            assert os.environ.get("TALK_DEFERRED_FILE") is None
            return CliRunResult(returncode=0, stdout="收到，这里收口。", stderr="")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 60,
                        "from": "agent:pi-kimi",
                        "to": ["agent:pi"],
                        "group_id": "group:lab",
                        "reply_to": 52,
                        "type": "text",
                        "content": "@agent:pi 再确认一下",
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
        self.assertEqual(client.appended, [(9, 61, "answer", "agent:pi-kimi", "reply", 1)])

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
            # 2026-06-06:pi/codex 分支不再注入 TALK 控制上下文(scope_text / requester_id /
            # remaining_auto_turns 等),那段任务式 metadata 在闲聊场景会让模型陷入"已经XX了"
            # 元叙述,且方案 D 账本已经在 bridge 端代管 scope/round 刹车,模型不需要看。
            self.assertNotIn("scope_text:", prompt)
            self.assertNotIn("requester_id:", prompt)
            self.assertIn("agent:codex 对你说:你怎么看？", prompt)
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
            # 2026-06-06:pi/codex 分支不再注入 TALK 控制上下文。本测试仍然覆盖账本写入
            # (discussion / turn 创建)行为,prompt 内容只需保留身份 + sender + task。
            self.assertNotIn("requester_id:", prompt)
            self.assertNotIn("assignee_id:", prompt)
            self.assertNotIn("scope_text:", prompt)
            self.assertIn("agent:codex 对你说:请检查这个按钮文案是否清楚", prompt)
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
            # identity no longer in prompt
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


class BuildGroupMemberContextTests(unittest.TestCase):
    """回归测试：_build_group_member_context 在所有 fallback 路径返回非空反幻觉提示"""

    def test_p2p_scope_returns_anti_hallucination_notice(self):
        """P2P（无 group_id）必须返回非空反幻觉提示"""
        async def run():
            from unittest.mock import MagicMock
            client = MagicMock()
            ctx = await _build_group_member_context(client, None, "agent:pi", sender="agent:codex")
            return ctx
        ctx = asyncio.run(run())
        self.assertIn("当前群成员清单 — 不可用", ctx)
        self.assertIn("orchestrator", ctx)
        self.assertIn("oracle", ctx)
        self.assertIn("agent:codex", ctx)
        self.assertIn("禁止", ctx)
        self.assertIn("不要调用 talk_send", ctx)

    def test_get_group_failure_returns_anti_hallucination_notice(self):
        """get_group 失败时必须返回非空反幻觉提示"""
        async def run():
            from unittest.mock import AsyncMock, MagicMock
            client = MagicMock()
            client.get_group = AsyncMock(side_effect=RuntimeError("network down"))
            ctx = await _build_group_member_context(client, "group:foo", "agent:pi", sender="agent:codex")
            return ctx
        ctx = asyncio.run(run())
        self.assertIn("查询群成员清单失败", ctx)
        self.assertIn("orchestrator", ctx)
        self.assertIn("agent:codex", ctx)

    def test_empty_members_returns_anti_hallucination_notice(self):
        """群无可见成员时必须返回非空反幻觉提示"""
        async def run():
            from unittest.mock import AsyncMock, MagicMock
            client = MagicMock()
            client.get_group = AsyncMock(return_value={"members": [], "metadata": {}})
            ctx = await _build_group_member_context(client, "group:foo", "agent:pi", sender="agent:codex")
            return ctx
        ctx = asyncio.run(run())
        self.assertIn("无可见成员", ctx)
        self.assertIn("orchestrator", ctx)

    def test_normal_path_compact_member_list(self):
        """正常路径返回紧凑逗号分隔的成员名单"""
        async def run():
            from unittest.mock import AsyncMock, MagicMock
            client = MagicMock()
            client.get_group = AsyncMock(return_value={
                "members": [
                    {"member_id": "agent:pi", "display_name": "pi"},
                    {"member_id": "agent:codex", "display_name": "Codex"},
                ],
                "metadata": {},
            })
            ctx = await _build_group_member_context(client, "group:foo", "agent:pi", sender="agent:codex")
            return ctx
        ctx = asyncio.run(run())
        self.assertIn("agent:pi", ctx)
        self.assertIn("agent:codex", ctx)
        self.assertIn("群成员：", ctx)
        self.assertIn(",", ctx)  # 逗号分隔
        self.assertNotIn("oracle", ctx)  # 正常路径不列禁止名单

    # ------------------------------------------------------------------
    # 5.5 方案 D：codex MCP 路径与 pi TS extension 产物等价测试
    # ------------------------------------------------------------------

    def test_codex_deferred_talk_send_via_mcp_equivalent_to_pi_path(self):
        """codex bridge 通过 MCP server 写 JSONL → bridge 消费 → 写 demand turn，与 pi 路径产物等价"""

        class FakeClient:
            def __init__(self):
                self.replies = []
                self.sent = []
                self.created_discussions = []
                self.turns = []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 81}

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to, reply_to, group_id))
                return {"id": 82}

            async def get_group(self, group_id):
                return {"members": [
                    {"member_id": "human:bobo"},
                    {"member_id": "agent:codex"},
                    {"member_id": "agent:pi"},
                ]}

            async def list_discussions(self, *, group_id=None):
                return []

            async def create_discussion(self, group_id, topic, participant_ids, *, max_rounds=2, **kwargs):
                self.created_discussions.append((group_id, topic, participant_ids, max_rounds, kwargs))
                return {"id": 9}

            async def append_discussion_turn(
                self, discussion_id, *, message_id, stance, target_member_id=None, turn_kind="reply", round_index=1
            ):
                self.turns.append((discussion_id, message_id, stance, target_member_id, turn_kind, round_index))
                return {"id": len(self.turns)}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            # 模拟 codex MCP server 写 JSONL 到 TALK_DEFERRED_FILE
            path = os.environ.get("TALK_DEFERRED_FILE")
            assert path, "TALK_DEFERRED_FILE must be set for talk_send to work"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "tool": "talk_send",
                    "target": "agent:pi",
                    "body": "你好，Codex 向你问好",
                    "stance": "greeting",
                }, ensure_ascii=False) + "\n")
            return CliRunResult(returncode=0, stdout="我去打个招呼。", stderr="")

        async def scenario():
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                client = FakeClient()
                await handle_incoming_message(
                    {
                        "id": 80,
                        "from": "human:bobo",
                        "to": ["agent:codex"],
                        "group_id": "group:lab",
                        "type": "text",
                        "content": "@agent:codex 去跟 agent:pi 打个招呼",
                    },
                    client=client,
                    member_id="agent:codex",
                    workdir=Path.cwd(),
                    command=["codex", "exec", "-"],
                    timeout=5,
                    max_reply_chars=400,
                    runtime="codex",
                    bridge_label="Codex bridge",
                    prompt_transport="stdin",
                )
                return client
            finally:
                cli_bridge.run_cli_command = original

        client = asyncio.run(scenario())

        # visible reply 先于 talk_send 发送
        self.assertTrue(any("我去打个招呼" in str(r) for r in client.replies),
                        "visible reply should be sent before deferred talk_send")
        # defer talk_send 被消费并发送
        self.assertIn(("@agent:pi 你好，Codex 向你问好", ["agent:pi"], 80, "group:lab"), client.sent)
        # demand turn 已写入账本
        self.assertEqual(client.turns, [(9, 82, "greeting", "agent:pi", "demand", 1)])


if __name__ == "__main__":
    unittest.main()
