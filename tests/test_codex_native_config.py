"""Codex native config.toml 的结构化校验：允许已授权排版/信任，锁住关键约束。"""
import json
import os
from pathlib import Path
import tempfile
import unittest

from bridges.codex_native_config import NativeConfigChanged, read_config, validate_config

MODEL = 'gpt-6.1-sol'
BASE = (
    'model = "gpt-6.1-sol"\n'
    'model_reasoning_effort = "xhigh"\n'
    'cli_auth_credentials_store = "file"\n'
)


class NativeConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'config.toml'

    def write(self, text):
        self.path.write_text(text, encoding='utf-8')
        return self.path

    def read(self, text=None):
        if text is not None:
            self.write(text)
        return read_config(self.path, model=MODEL, root=self.root,
                           required={'cli_auth_credentials_store': 'file'})

    def assertRejected(self, text, reason, fields=()):
        self.write(text)
        with self.assertRaises(NativeConfigChanged) as caught:
            self.read()
        self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(caught.exception.fields, fields)

    def trust(self, path=None):
        value = str(self.root if path is None else path)
        return f'\n[projects.{json.dumps(value)}]\ntrust_level = "trusted"\n'

    def test_preset_plus_codex_project_trust_is_accepted(self):
        value = self.read(BASE + self.trust())
        self.assertEqual(value['model'], MODEL)
        self.assertEqual(list(value['projects'].values())[0]['trust_level'], 'trusted')

    def test_comments_whitespace_and_field_order_are_ignored(self):
        self.assertEqual(self.read(
            '# Codex writes this file after the first exec.\n'
            '\ncli_auth_credentials_store="file"   # role-local auth\n'
            'model_reasoning_effort = "xhigh"\n'
            'model="gpt-6.1-sol"\n' + self.trust())['model'], MODEL)

    def test_model_change_is_rejected(self):
        self.assertRejected(BASE.replace(MODEL, 'gpt-5.1') + self.trust(), 'model')

    def test_non_string_model_is_rejected(self):
        self.assertRejected(BASE.replace(f'"{MODEL}"', '7') + self.trust(), 'model')

    def test_file_auth_store_isolation_is_required(self):
        self.assertRejected(BASE.replace('"file"', '"keyring"') + self.trust(),
                            'required_field', ('cli_auth_credentials_store',))
        self.assertRejected(BASE.replace('cli_auth_credentials_store = "file"\n', '') + self.trust(),
                            'required_field', ('cli_auth_credentials_store',))

    def test_unknown_top_level_field_is_rejected(self):
        self.assertRejected(BASE + 'danger = true\n' + self.trust(),
                            'unknown_fields', ('danger',))

    def test_trust_outside_project_root_is_rejected(self):
        outside = self.root.parent / 'another-project'
        self.assertRejected(BASE + self.trust(outside), 'projects_outside_root',
                            ('projects.path',))

    def test_relative_project_trust_is_rejected(self):
        self.assertRejected(BASE + '\n[projects."."]\ntrust_level = "trusted"\n',
                            'projects_outside_root', ('projects.path',))

    def test_unknown_project_setting_is_rejected(self):
        self.assertRejected(
            BASE + self.trust().replace('trust_level = "trusted"',
                                        'trust_level = "trusted"\nsandbox = "danger-full-access"'),
            'unknown_fields', ('projects.sandbox',))

    def test_missing_trust_level_is_rejected(self):
        self.assertRejected(BASE + f'\n[projects.{json.dumps(str(self.root))}]\n',
                            'unsupported_value', ('projects.trust_level',))

    def test_sandbox_weakening_is_rejected(self):
        self.assertRejected(BASE + self.trust() + '[windows]\nsandbox = "disabled"\n',
                            'unsupported_value', ('windows.sandbox',))
        self.assertRejected(BASE.replace('model_reasoning_effort = "xhigh"\n',
                                         'model_reasoning_effort = "xhigh"\n'
                                         'sandbox_mode = "danger-full-access"\n'),
                            'unsupported_value', ('sandbox_mode',))

    def test_confirmed_sandbox_and_approval_values_are_accepted(self):
        value = self.read(
            BASE.replace('model_reasoning_effort = "xhigh"\n',
                         'model_reasoning_effort = "xhigh"\n'
                         'model_provider = "openai"\n'
                         'forced_login_method = "chatgpt"\n'
                         'approval_policy = "never"\n'
                         'sandbox_mode = "workspace-write"\n')
            + self.trust() + '[windows]\nsandbox = "elevated"\n')
        self.assertEqual((value['sandbox_mode'], value['windows']['sandbox']),
                         ('workspace-write', 'elevated'))

    def test_invalid_or_missing_file_is_rejected(self):
        with self.assertRaises(NativeConfigChanged) as caught:
            read_config(self.path, model=MODEL, root=self.root)
        self.assertEqual(caught.exception.reason, 'missing')
        self.assertRejected('<not toml>', 'invalid_toml')

    def test_structure_only_mode_accepts_unselected_model(self):
        self.write('cli_auth_credentials_store = "file"\n'
                   'forced_login_method = "chatgpt"\n'
                   'model_provider = "openai"\n' + self.trust())
        value = read_config(self.path, root=self.root,
                            required={'cli_auth_credentials_store': 'file',
                                      'forced_login_method': 'chatgpt',
                                      'model_provider': 'openai'})
        self.assertNotIn('model', value)

    def test_validate_config_does_not_mutate_input(self):
        value = {'model': MODEL, 'cli_auth_credentials_store': 'file'}
        before = dict(value)
        validate_config(value, model=MODEL, required={'cli_auth_credentials_store': 'file'})
        self.assertEqual(value, before)

    @unittest.skipUnless(os.name == 'nt', 'Windows path comparison is case-insensitive')
    def test_windows_path_comparison_is_case_insensitive(self):
        self.read(BASE + self.trust(str(self.root).upper()))
        self.assertEqual(len(self.read()['projects']), 1)


if __name__ == '__main__':
    unittest.main()
