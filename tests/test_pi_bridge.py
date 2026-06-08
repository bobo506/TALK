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
        # 5.5 function-calling：禁用内置工具与自动发现扩展，只显式保留 talk_send
        self.assertIn("--no-builtin-tools", command_args)
        self.assertIn("--no-extensions", command_args)
        self.assertIn("--tools", command_args)
        self.assertIn("talk_send", command_args)
        self.assertIn("--extension", command_args)
        self.assertIn("--no-session", command_args)
        self.assertIn("--thinking", command_args)
        self.assertIn("off", command_args)
        self.assertIn("--system-prompt", command_args)
        system_prompt = command_args[command_args.index("--system-prompt") + 1]
        # 系统层 prompt 承载角色、输出通道、单轮语义与反工具幻觉约束
        self.assertIn("TALK 群里的一个 agent", system_prompt)
        self.assertIn("输出通道", system_prompt)
        self.assertIn("不存在下一轮", system_prompt)
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
        self.assertIn("--no-extensions", command_args)

    def test_parser_accepts_custom_pi_command(self):
        args = pi_bridge.build_parser().parse_args([
            "--key",
            "pi-key",
            "--pi-command",
            "pi --provider deepseek --print --mode text",
        ])

        self.assertEqual(args.pi_command, "pi --provider deepseek --print --mode text")

    def test_default_pi_command_disables_auto_discovered_extensions(self):
        """plan-mode 在 rebindSession 里硬编码 setActiveTools 会覆盖我们注册的 talk_send。
        -ne 禁用所有自动发现扩展(包括 plan-mode),`-e <path>` 显式加载的不受影响。"""
        cmd = pi_bridge.DEFAULT_PI_COMMAND
        self.assertIn("--no-extensions", cmd)
        self.assertIn("--tools talk_send", cmd)
        self.assertIn("--extension", cmd)  # 我们的扩展仍然显式加载

    def test_default_pi_tools_command_disables_auto_discovered_extensions(self):
        """施工档同样要规避 plan-mode 覆盖,虽然 NORMAL_MODE_TOOLS 跟我们白名单几乎重合,
        但保留 -ne 让工具表面完全由 bridge 控制,避免未来 plan-mode 改成员时炸我们。"""
        cmd = pi_bridge.DEFAULT_PI_TOOLS_COMMAND
        self.assertIn("--no-extensions", cmd)


if __name__ == "__main__":
    unittest.main()
