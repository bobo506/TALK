import unittest
import shlex

from bridges import pi_bridge


class PiBridgeTests(unittest.TestCase):
    def test_parser_defaults_to_pi_identity_and_argv_transport(self):
        args = pi_bridge.build_parser().parse_args(["--key", "pi-key"])

        self.assertEqual(args.name, "pi")
        self.assertEqual(args.runtime, "pi")
        self.assertEqual(args.bridge_label, "pi bridge")
        self.assertEqual(args.prompt_transport, "argv")
        command_args = shlex.split(args.pi_command, posix=True)
        self.assertEqual(command_args[:4], ["pi", "--print", "--mode", "text"])
        self.assertIn("--no-context-files", command_args)
        self.assertIn("--no-tools", command_args)
        self.assertIn("--no-session", command_args)
        self.assertIn("--thinking", command_args)
        self.assertIn("off", command_args)
        self.assertIn("--system-prompt", command_args)
        system_prompt = command_args[command_args.index("--system-prompt") + 1]
        self.assertIn("TALK Group Hall", system_prompt)
        self.assertIn("群聊参与者", system_prompt)
        self.assertIn("按用户语言自然回复", system_prompt)
        self.assertIn("默认讨论模式", system_prompt)
        self.assertIn("安全行协议", system_prompt)
        self.assertIn("TALK_ACTION", system_prompt)
        self.assertIn("final_to_human", system_prompt)
        self.assertNotIn("talk-action", system_prompt)
        # 5.3 P0 修复：禁止 system prompt 里出现任何具体人名硬编码
        # （之前 to=human:bobo 导致 pi 把"bobo"幻觉成群里的人类）
        self.assertNotIn("human:bobo", system_prompt)
        self.assertNotIn("human:qa", system_prompt)
        self.assertNotIn("agent:codex", system_prompt)
        # 5.3 P0 修复：禁止 system prompt 自封业务角色
        # （之前"评审方案"让 pi 把自己定位成"方案评审者"主动招揽工作）
        self.assertNotIn("评审方案", system_prompt)
        # 5.3 P0 修复：必须强调"只能提及清单内成员"与"回复克制"
        self.assertIn("成员清单", system_prompt)
        self.assertIn("不得", system_prompt)  # "不得称呼或 @ 清单外的任何名字"
        self.assertIn("回复克制", system_prompt)
        # 5.3 热修：回复克制必须区分 A/B/C 三类，且 B 类（用户派 pi 联系另一个 agent）
        # 必须明确"必须用 TALK_ACTION 实际执行任务转交"。
        # 上一轮被这条规则误压制，pi 收到"请和 codex 确认在线状态"只敷衍回了一句 hi。
        self.assertIn("A 类", system_prompt)
        self.assertIn("B 类", system_prompt)
        self.assertIn("C 类", system_prompt)
        self.assertIn("任务转交", system_prompt)
        self.assertIn("必须用 TALK_ACTION send_message", system_prompt)
        # 防止误简化：必须出现"先承接用户再 TALK_ACTION"的顺序约束
        self.assertIn("先简短承接用户一句", system_prompt)
        for metachar in ("|", "/", "<", ">", "&"):
            self.assertNotIn(metachar, system_prompt)

    def test_parser_can_enable_pi_tools_profile_with_default_command(self):
        args = pi_bridge.build_parser().parse_args(["--key", "pi-key", "--pi-execution-profile", "tools"])

        self.assertEqual(args.pi_execution_profile, "tools")
        self.assertEqual(args.pi_command, pi_bridge.DEFAULT_PI_COMMAND)
        args.pi_command = pi_bridge.DEFAULT_PI_TOOLS_COMMAND
        command_args = shlex.split(args.pi_command, posix=True)
        self.assertIn("--tools", command_args)
        self.assertIn("read,grep,find,ls,bash,edit,write", command_args)
        self.assertNotIn("--no-tools", command_args)

    def test_parser_accepts_custom_pi_command(self):
        args = pi_bridge.build_parser().parse_args([
            "--key",
            "pi-key",
            "--pi-command",
            "pi --provider deepseek --print --mode text",
        ])

        self.assertEqual(args.pi_command, "pi --provider deepseek --print --mode text")


if __name__ == "__main__":
    unittest.main()
