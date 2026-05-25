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
        self.assertIn("你是 TALK 群聊里的 pi", system_prompt)
        self.assertIn("按用户语言自然回复", system_prompt)
        self.assertIn("默认不要声称能读取项目文件、执行命令、编辑文件或调用工具", system_prompt)

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
