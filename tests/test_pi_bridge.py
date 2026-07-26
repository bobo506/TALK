import shlex
import shutil
import tempfile
import unittest
from pathlib import Path

from bridges import pi_bridge
from cli.profiles import SYSTEM_PROMPT_PROFILE_HEADER, agent_profile_dir


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
        # function-calling：禁用内置工具与自动发现扩展，只显式保留 TALK 工具面
        self.assertIn("--no-builtin-tools", command_args)
        self.assertIn("--no-extensions", command_args)
        self.assertIn("--tools", command_args)
        tool_names = command_args[command_args.index("--tools") + 1].split(",")
        self.assertEqual(set(tool_names), set(pi_bridge.TALK_TOOL_NAMES))
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

    def test_system_prompt_has_no_newlines(self):
        # pi.CMD (Windows shim) mangles a --system-prompt arg containing newlines
        # → pi 0.79.8 emits nothing. The bridge collapses the prompt to one line.
        args = pi_bridge.build_parser().parse_args(["--key", "pi-key"])
        command_args = shlex.split(args.pi_command, posix=True)
        system_prompt = command_args[command_args.index("--system-prompt") + 1]
        self.assertNotIn("\n", system_prompt)
        # content is preserved across the collapse
        self.assertIn("TALK 群里的一个 agent", system_prompt)
        self.assertIn("不存在下一轮", system_prompt)

    def test_tools_profile_resolves_to_tools_command(self):
        args = pi_bridge.build_parser().parse_args(["--key", "pi-key", "--pi-execution-profile", "tools"])

        self.assertEqual(args.pi_execution_profile, "tools")
        resolved = pi_bridge.resolve_pi_command(args)
        command_args = shlex.split(resolved, posix=True)
        self.assertIn("--tools", command_args)
        tool_names = command_args[command_args.index("--tools") + 1].split(",")
        for name in ("read", "grep", "find", "ls", "bash", "edit", "write", *pi_bridge.TALK_TOOL_NAMES):
            self.assertIn(name, tool_names)
        self.assertNotIn("--no-tools", command_args)
        self.assertIn("--no-extensions", command_args)
        self.assertIn("--extension", command_args)

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
        self.assertIn("talk_delegate_task", cmd)
        self.assertIn("--extension", cmd)  # 我们的扩展仍然显式加载

    def test_default_pi_tools_command_disables_auto_discovered_extensions(self):
        """施工档同样要规避 plan-mode 覆盖,虽然 NORMAL_MODE_TOOLS 跟我们白名单几乎重合,
        但保留 -ne 让工具表面完全由 bridge 控制,避免未来 plan-mode 改成员时炸我们。"""
        cmd = pi_bridge.DEFAULT_PI_TOOLS_COMMAND
        self.assertIn("--no-extensions", cmd)
        self.assertIn("talk_delegate_task", cmd)
        self.assertIn("--extension", cmd)

    def test_default_task_command_leaves_result_delivery_to_runner(self):
        command_args = shlex.split(pi_bridge.DEFAULT_PI_TASK_COMMAND, posix=True)
        system_prompt = command_args[command_args.index("--system-prompt") + 1]

        self.assertIn("--no-tools", command_args)
        self.assertIn("--no-extensions", command_args)
        self.assertNotIn("--extension", command_args)
        self.assertFalse(any(name in command_args for name in pi_bridge.TALK_TOOL_NAMES))
        self.assertIn("优先严格遵循请求者给出的任务正文", system_prompt)
        self.assertIn("runner 会把你的可见输出写入对应 Task Hall", system_prompt)

    def test_tools_profile_task_command_keeps_local_tools_only(self):
        args = pi_bridge.build_parser().parse_args(
            ["--key", "pi-key", "--pi-execution-profile", "tools"]
        )
        command_args = shlex.split(pi_bridge.resolve_pi_task_command(args), posix=True)
        tool_names = command_args[command_args.index("--tools") + 1].split(",")

        self.assertEqual(set(tool_names), {"read", "grep", "find", "ls", "bash", "edit", "write"})
        self.assertNotIn("--extension", command_args)
        self.assertTrue(set(tool_names).isdisjoint(pi_bridge.TALK_TOOL_NAMES))

    def test_task_preflight_command_disables_tools_for_tools_profile(self):
        args = pi_bridge.build_parser().parse_args(
            ["--key", "pi-key", "--pi-execution-profile", "tools"]
        )
        command_args = shlex.split(pi_bridge.resolve_pi_task_preflight_command(args), posix=True)
        system_prompt = command_args[command_args.index("--system-prompt") + 1]

        self.assertIn("--no-tools", command_args)
        self.assertNotIn("--tools", command_args)
        self.assertNotIn("--extension", command_args)
        self.assertIn("领取前预检", system_prompt)


class PiBridgeProfileInjectionTests(unittest.TestCase):
    """Phase 2 / approach B: --project injects IDENTITY/SOUL into the system prompt."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-pi-project-"))
        self.addCleanup(lambda: shutil.rmtree(self._tmp, ignore_errors=True))

    def _write_pi_profile(self):
        agent_dir = agent_profile_dir(self._tmp, "agent:pi")
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "IDENTITY.md").write_text("# IDENTITY\n我是 pi，对话型 Agent。", encoding="utf-8")
        (agent_dir / "SOUL.md").write_text("# SOUL\n语气平实，绝不写汇报体。", encoding="utf-8")

    def _system_prompt_of(self, command: str) -> str:
        args = shlex.split(command, posix=True)
        return args[args.index("--system-prompt") + 1]

    def test_without_project_is_byte_identical(self):
        args = pi_bridge.build_parser().parse_args(["--key", "pi-key"])
        self.assertEqual(pi_bridge.resolve_pi_command(args), pi_bridge.DEFAULT_PI_COMMAND)

    def test_project_with_profile_injects_into_system_prompt(self):
        self._write_pi_profile()
        args = pi_bridge.build_parser().parse_args(
            ["--key", "pi-key", "--name", "pi", "--project", str(self._tmp)]
        )
        resolved = pi_bridge.resolve_pi_command(args)
        system_prompt = self._system_prompt_of(resolved)

        # base system prompt is preserved …
        self.assertIn("TALK 群里的一个 agent", system_prompt)
        # … and the profile is appended as framed background
        self.assertIn(SYSTEM_PROMPT_PROFILE_HEADER, system_prompt)
        self.assertIn("绝不写汇报体", system_prompt)
        self.assertIn("对话型 Agent", system_prompt)
        # injected profile is also collapsed to one line (pi.CMD newline mangling)
        self.assertNotIn("\n", system_prompt)
        # the rest of the command is untouched (still function-calling shape)
        self.assertIn("--tools talk_send", resolved)
        self.assertIn("talk_delegate_task", resolved)

        task_system_prompt = self._system_prompt_of(pi_bridge.resolve_pi_task_command(args))
        self.assertIn("优先严格遵循请求者给出的任务正文", task_system_prompt)
        self.assertIn("绝不写汇报体", task_system_prompt)

    def test_project_without_matching_profile_is_byte_identical(self):
        # .talk/ exists but no profile for agent:pi → opt-in stays a no-op
        agent_profile_dir(self._tmp, "agent:other").mkdir(parents=True, exist_ok=True)
        args = pi_bridge.build_parser().parse_args(
            ["--key", "pi-key", "--name", "pi", "--project", str(self._tmp)]
        )
        self.assertEqual(pi_bridge.resolve_pi_command(args), pi_bridge.DEFAULT_PI_COMMAND)

    def test_command_override_is_respected_even_with_project(self):
        self._write_pi_profile()
        args = pi_bridge.build_parser().parse_args(
            ["--key", "pi-key", "--name", "pi", "--project", str(self._tmp),
             "--pi-command", "pi --provider deepseek --print"]
        )
        self.assertEqual(pi_bridge.resolve_pi_command(args), "pi --provider deepseek --print")


if __name__ == "__main__":
    unittest.main()
