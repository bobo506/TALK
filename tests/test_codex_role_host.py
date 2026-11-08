"""Verify generated Codex commands without launching a model or a host."""
import json
from pathlib import Path
import shlex
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bridges import cli_bridge, codex_bridge
from scripts import codex_role_host as host
from scripts import codex_role_setup


class CodexCommandTests(unittest.TestCase):
    def test_generated_commands_preserve_arguments_for_both_profiles(self):
        manager = SimpleNamespace(
            project='synthetic-project', member='synthetic-member',
            codex_executable='synthetic-codex', project_root=Path.cwd(),
            display_name='synthetic', execution_timeout_seconds=None,
            _configuration=Mock(return_value=({'model': 'synthetic-model'}, 'low')),
            child_environment=Mock(return_value={}),
        )
        temp_dir = Path('synthetic-temp')
        profile_data = {'synthetic': True}
        with patch.object(codex_role_setup, 'require_version'), \
             patch('cli.profiles.load_profile', return_value=profile_data), \
             patch('cli.profiles.compose_system_prompt', side_effect=lambda prompt, profile: prompt), \
             patch.object(host, 'task_temp_directory', return_value=temp_dir):
            for profile in ('tools', 'review'):
                manager.task_profile = profile
                argv, _, _ = host.CodexRoleHost.build_entry_argv(manager, 'codex', 'synthetic-model')
                parsed = codex_bridge.build_parser().parse_args(argv[3:])
                cases = (
                    ('message', parsed.codex_command, 'read-only', cli_bridge.TASK_RUNNER_SYSTEM_PROMPT),
                    ('task', parsed.codex_task_command,
                     'workspace-write' if profile == 'tools' else 'read-only', cli_bridge.TASK_RUNNER_SYSTEM_PROMPT),
                    ('precheck', parsed.task_preflight_command, 'read-only', cli_bridge.TASK_PREFLIGHT_SYSTEM_PROMPT),
                )
                for name, command, sandbox, prompt in cases:
                    with self.subTest(profile=profile, command=name):
                        writable = sandbox == 'workspace-write'
                        expected = [
                            'synthetic-codex', '-a', 'never', '--strict-config', '--disable', 'apps',
                            '--disable', 'remote_plugin', '--disable', 'plugins', 'exec',
                            '--model', 'synthetic-model', '--sandbox', sandbox, '--color', 'never',
                            '--skip-git-repo-check', '--ignore-rules',
                            '-c', 'windows.sandbox="' + ('elevated' if writable else 'unelevated') + '"',
                            '-c', 'model_reasoning_effort=' + json.dumps('low'),
                            '-c', 'developer_instructions=' + json.dumps(prompt),
                        ]
                        if writable:
                            expected += ['--add-dir', str(temp_dir)]
                        expected.append('-')
                        self.assertEqual(shlex.split(command), expected)


if __name__ == '__main__':
    unittest.main()
