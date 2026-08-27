import json
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path

from bridges import cli_bridge, kimi_bridge
from cli.profiles import SYSTEM_PROMPT_PROFILE_HEADER, agent_profile_dir


class KimiBridgeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-kimi-bridge-test-"))
        self.addCleanup(lambda: shutil.rmtree(self._tmp, ignore_errors=True))

    @staticmethod
    def _agent_file_from(command: str) -> Path:
        args = shlex.split(command, posix=True)
        return Path(args[args.index("--agent-file") + 1])

    def test_parser_defaults_to_native_kimi_identity_and_argv_transport(self):
        args = kimi_bridge.build_parser().parse_args(["--key", "kimi-key"])

        self.assertEqual(args.name, "kimi")
        self.assertEqual(args.runtime, "kimi-code")
        self.assertEqual(args.bridge_label, "Kimi Code bridge")
        self.assertEqual(args.prompt_transport, "argv")
        self.assertEqual(args.kimi_task_profile, "review")
        self.assertEqual(args.kimi_command, kimi_bridge.DEFAULT_KIMI_COMMAND)

    def test_materialized_commands_use_stream_json_and_isolated_agent_files(self):
        args = kimi_bridge.build_parser().parse_args(["--key", "kimi-key"])
        message, task, preflight = kimi_bridge.materialize_kimi_commands(args, self._tmp)

        for command in (message, task, preflight):
            command_args = shlex.split(command, posix=True)
            self.assertEqual(command_args[0], "kimi")
            self.assertNotIn("--auto", command_args)
            self.assertEqual(command_args[command_args.index("--output-format") + 1], "stream-json")
            self.assertIn("--agent-file", command_args)
            self.assertIn("--skills-dir", command_args)
            self.assertEqual(command_args[-1], "-p")

        discussion_text = self._agent_file_from(message).read_text(encoding="utf-8")
        task_text = self._agent_file_from(task).read_text(encoding="utf-8")
        preflight_text = self._agent_file_from(preflight).read_text(encoding="utf-8")
        self.assertIn("tools: []", discussion_text)
        self.assertIn("tools: []", preflight_text)
        for tool in kimi_bridge.KIMI_REVIEW_TOOLS:
            self.assertIn(f"  - {tool}", task_text)
        self.assertNotIn("  - Edit", task_text)
        self.assertNotIn("  - Write", task_text)
        self.assertIn("subagents: []", discussion_text)
        self.assertIn("subagents: []", task_text)
        self.assertIn("subagents: []", preflight_text)
        self.assertIn("TALK Group Hall", discussion_text)
        self.assertIn("领取前预检", preflight_text)

    def test_tools_task_profile_adds_edit_and_write_only_to_task_command(self):
        args = kimi_bridge.build_parser().parse_args(
            ["--key", "kimi-key", "--kimi-task-profile", "tools"]
        )
        message, task, preflight = kimi_bridge.materialize_kimi_commands(args, self._tmp)

        task_text = self._agent_file_from(task).read_text(encoding="utf-8")
        self.assertIn("  - Edit", task_text)
        self.assertIn("  - Write", task_text)
        self.assertIn("tools: []", self._agent_file_from(message).read_text(encoding="utf-8"))
        self.assertIn("tools: []", self._agent_file_from(preflight).read_text(encoding="utf-8"))

    def test_model_is_pinned_across_generated_commands(self):
        args = kimi_bridge.build_parser().parse_args(
            ["--key", "kimi-key", "--kimi-model", "kimi-code/kimi-for-coding"]
        )
        commands = kimi_bridge.materialize_kimi_commands(args, self._tmp)

        for command in commands:
            command_args = shlex.split(command, posix=True)
            self.assertEqual(
                command_args[command_args.index("--model") + 1],
                "kimi-code/kimi-for-coding",
            )

    def test_project_profile_is_injected_into_all_agent_system_prompts(self):
        project = self._tmp / "project"
        profile_dir = agent_profile_dir(project, "agent:kimi")
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "IDENTITY.md").write_text("# IDENTITY\n我是 Kimi Reviewer。", encoding="utf-8")
        (profile_dir / "SOUL.md").write_text("# SOUL\n只根据证据下结论。", encoding="utf-8")
        args = kimi_bridge.build_parser().parse_args(
            ["--key", "kimi-key", "--project", str(project)]
        )

        commands = kimi_bridge.materialize_kimi_commands(args, self._tmp / "runtime")

        for command in commands:
            agent_text = self._agent_file_from(command).read_text(encoding="utf-8")
            self.assertIn(SYSTEM_PROMPT_PROFILE_HEADER, agent_text)
            self.assertIn("我是 Kimi Reviewer", agent_text)
            self.assertIn("只根据证据下结论", agent_text)

    def test_custom_command_override_is_respected(self):
        args = kimi_bridge.build_parser().parse_args(
            ["--key", "kimi-key", "--kimi-command", "kimi-wrapper --json"]
        )

        self.assertEqual(
            kimi_bridge.materialize_kimi_commands(args, self._tmp),
            ("kimi-wrapper --json", "kimi-wrapper --json", "kimi-wrapper --json"),
        )


class KimiStreamJsonTests(unittest.TestCase):
    def test_extracts_last_visible_assistant_message(self):
        output = "\n".join(
            [
                json.dumps({"role": "assistant", "content": "我先检查。", "tool_calls": [{}]}, ensure_ascii=False),
                json.dumps({"role": "tool", "content": "检查结果"}, ensure_ascii=False),
                json.dumps(
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "最终"},
                            {"type": "text", "text": "结论"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"role": "meta", "type": "session.resume_hint"}),
            ]
        )

        self.assertEqual(cli_bridge.extract_kimi_final_assistant(output), "最终\n结论")

    def test_plain_text_is_left_for_custom_command_compatibility(self):
        self.assertIsNone(cli_bridge.extract_kimi_final_assistant("普通文本输出"))
        result = cli_bridge.CliRunResult(0, "普通文本输出", "")
        self.assertIs(cli_bridge.normalize_runtime_result(result, runtime="kimi-code"), result)

    def test_normalize_runtime_result_ignores_tool_and_meta_events(self):
        result = cli_bridge.CliRunResult(
            0,
            "\n".join(
                [
                    json.dumps({"role": "tool", "content": "内部工具输出"}, ensure_ascii=False),
                    json.dumps({"role": "assistant", "content": "可见答案"}, ensure_ascii=False),
                    json.dumps({"role": "meta", "content": "resume"}),
                ]
            ),
            "diagnostic",
        )

        normalized = cli_bridge.normalize_runtime_result(result, runtime="kimi-code")

        self.assertEqual(normalized.stdout, "可见答案")
        self.assertEqual(normalized.stderr, "diagnostic")
        self.assertEqual(normalized.returncode, 0)


if __name__ == "__main__":
    unittest.main()
