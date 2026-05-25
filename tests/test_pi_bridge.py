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
