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
        # 5.5 function-calling：默认不再使用 --no-tools，改用 --no-builtin-tools + --tools talk_send
        self.assertIn("--no-builtin-tools", command_args)
        self.assertIn("--tools", command_args)
        self.assertIn("talk_send", command_args)
        self.assertIn("--extension", command_args)
        self.assertIn("--no-session", command_args)
        self.assertIn("--thinking", command_args)
        self.assertIn("off", command_args)
        self.assertIn("--system-prompt", command_args)
        system_prompt = command_args[command_args.index("--system-prompt") + 1]
        # 极简 system prompt：不预设身份，只要求讲中文
        self.assertIn("自然回复", system_prompt)
        # 无场景分类标签
        self.assertNotIn("信使场景", system_prompt)
        self.assertNotIn("自身询问场景", system_prompt)
        # 无 TALK_ACTION 文本协议残留
        self.assertNotIn("TALK_ACTION", system_prompt)
        # 禁止硬编码具体人名
        self.assertNotIn("human:bobo", system_prompt)
        self.assertNotIn("human:qa", system_prompt)
        self.assertNotIn("agent:codex", system_prompt)

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
