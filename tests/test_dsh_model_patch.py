import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridges.dsh_effort import set_patch_effort
from bridges.dsh_patch import patch_problem
from scripts import dsh_role_host as host


class DshModelPatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'workspace' / 'native-home'
        self.binding = dict(runner_id='runner:dsh-test', runtime='dsh', model_source='builtin',
                            provider_id='deepseek-official', connection_ref='native',
                            model_id='deepseek-flash', model_alias='deepseek-flash',
                            binding_fingerprint='test-fingerprint', default_effort='high',
                            effort_override='low')
        entry = {k: self.binding[k] for k in host.DIMENSIONS}
        entry.update(auth_type='native', target_api_key_env='DSH_TEST_API_KEY',
                     command_template='dsh --patch {native_home}/model-{model}.patch.yml',
                     tools_command_template='dsh --patch {native_home}/model-{model}.patch.yml')
        self.manager = object.__new__(host.DshRoleHost)
        self.manager.project = 'project'
        self.manager.member = 'agent:test'
        self.manager.store = SimpleNamespace(native_home_dir=lambda project, member: self.home)
        self.manager.runtime_config = {'dsh': {'enabled': True, 'connections': {'native': entry}}}
        self.manager.task_profile = 'tools'
        self.manager.workspace_context = None
        self.manager.execution_timeout_seconds = None
        self.manager.project_root = self.root
        self.manager.display_name = 'Test'
        self.manager._current_binding = lambda project, member, alias: self.binding

    def prepare(self):
        with patch.dict(os.environ, {'DSH_TEST_API_KEY': 'synthetic-secret'}), \
             patch.object(host.shutil, 'which', return_value='dsh'):
            return self.manager.build_entry_argv('dsh', self.binding['model_alias'])[0]

    def run_host_startup(self, *, expected_content=None, binding=None):
        role = {'member_id': 'agent:test', 'binding_state': 'bound',
                'runner': {'runtime': 'dsh', 'runner_id': 'runner:dsh-test'},
                'model': {'choice_id': 'choice', 'model_alias': 'deepseek-flash'}}
        binding = self.binding if binding is None else binding
        class Client:
            def request(inner, method, path, key=None):
                if path == '/api/members/me':
                    return {'kind': 'agent', 'id': 'agent:test', 'display_name': 'Test'} if key else {'kind': 'human'}
                if path.endswith('/roles'):
                    return [role]
                if path.endswith('/agents'):
                    return [{'member_id': 'agent:test', 'binding_state': 'bound', 'binding': binding}]
                raise AssertionError(path)
        key = self.root / 'role.key'
        key.write_text('fixture-role-key', encoding='utf-8')
        target = self.home / 'model-deepseek-flash.patch.yml'
        observed = []
        def serve(manager, *args, **kwargs):
            # This is the first opportunity for the real service loop to claim,
            # preflight or launch a bridge; build_entry_argv has not been called.
            content = target.read_text(encoding='utf-8')
            observed.append(content)
            if expected_content is None:
                self.assertIsNone(patch_problem(content))
                self.assertNotIn('synthetic-secret', content)
                self.assertNotIn('API_KEY', content)
            else:
                self.assertEqual(content, expected_content)
            raise host.Drained()
        args = ['--project', 'project', '--member', 'agent:test',
                '--project-root', str(self.root), '--state-dir', str(self.root / 'state'),
                '--base-url', 'http://127.0.0.1', '--operator-key-file', str(self.root / 'operator.key'),
                '--role-key-file', str(key), '--expected-choice-id', 'choice',
                '--expected-model-alias', 'deepseek-flash', '--apply']
        with patch.dict(os.environ, {'DSH_TEST_API_KEY': 'synthetic-secret'}), \
             patch.object(host, '_local_facts', return_value=(self.manager.runtime_config, None)), \
             patch.object(host.rsh, 'load_operator_key', return_value='fixture-operator-key'), \
             patch.object(host.rsh, 'TalkHostClient', return_value=Client()), \
             patch('scripts.dsh_role_setup.setup', return_value={'profile': 'tools'}), \
             patch.object(host.rsh.OwnershipStore, 'native_home_dir', return_value=self.home), \
             patch.object(host.DshRoleHost, 'build_entry_argv', side_effect=AssertionError('premature claim')), \
             patch.object(host.DshRoleHost, 'serve', autospec=True, side_effect=serve), \
             patch.object(host.DshRoleHost, 'publish_health_best_effort'), \
             patch.object(host.rsh.subprocess, 'Popen', side_effect=AssertionError('unexpected subprocess')):
            result = host.main(args)
        return result, observed

    def test_host_startup_creates_patch_before_service_loop_without_claim(self):
        self.assertFalse(self.home.exists())
        result, observed = self.run_host_startup()
        self.assertEqual(result, 0)
        self.assertEqual(len(observed), 1)

    def test_host_startup_preserves_existing_patch(self):
        self.home.mkdir(parents=True)
        target = self.home / 'model-deepseek-flash.patch.yml'
        target.write_bytes(b'user config\n')
        result, observed = self.run_host_startup(expected_content='user config\n')
        self.assertEqual(result, 0)
        self.assertEqual(observed, ['user config\n'])
        self.assertEqual(target.read_bytes(), b'user config\n')

    def test_host_startup_rejects_changed_binding_before_service(self):
        result, observed = self.run_host_startup(binding=dict(self.binding, model_alias='other'))
        self.assertEqual(result, 1)
        self.assertEqual(observed, [])
        self.assertFalse((self.home / 'model-deepseek-flash.patch.yml').exists())

    def test_prepare_creates_patch_before_command_validation(self):
        target = self.home / 'model-deepseek-flash.patch.yml'
        validate = host.validate_command
        def check_exists(*args, **kwargs):
            self.assertTrue(target.is_file())
            return validate(*args, **kwargs)
        with patch.object(host, 'validate_command', side_effect=check_exists):
            argv = self.prepare()
        self.assertIn(target.as_posix(), argv[argv.index('--command') + 1])
        content = target.read_text(encoding='utf-8')
        self.assertIn('provider: "deepseek-official"', content)
        self.assertIn('model: "deepseek-flash"', content)
        self.assertIn('reasoningEffort: low', content)
        self.assertIsNone(patch_problem(content))
        updated, mode = set_patch_effort(content, 'high')
        self.assertIn('reasoningEffort: high', updated)
        self.assertNotIn('synthetic-secret', content)
        self.assertNotIn('API_KEY', content)
        self.assertEqual(list(self.home.glob('.model-patch-*.tmp')), [])

    def test_existing_patch_is_preserved(self):
        self.home.mkdir(parents=True)
        target = self.home / 'model-deepseek-flash.patch.yml'
        target.write_bytes(b'user config\n')
        self.prepare()
        self.assertEqual(target.read_bytes(), b'user config\n')

    def test_defaults_and_unknown_provider(self):
        self.binding.update(effort_override=None, default_effort=None)
        self.prepare()
        self.assertIn('reasoningEffort: max', (self.home / 'model-deepseek-flash.patch.yml').read_text(encoding='utf-8'))
        other = self.root / 'other'
        host._ensure_model_patch(other, dict(self.binding, provider_id='another-provider', model_alias='another-model'), 'secret')
        data = (other / 'model-another-model.patch.yml').read_text(encoding='utf-8')
        self.assertIn('provider: "another-provider"', data)
        self.assertIn('model: "another-model"', data)
        self.assertNotIn('llm-deepseek', data)

    def test_binding_default_effort_is_used(self):
        self.binding.update(effort_override=None, default_effort='high')
        self.prepare()
        content = (self.home / 'model-deepseek-flash.patch.yml').read_text(encoding='utf-8')
        self.assertIn('reasoningEffort: high', content)

    def test_concurrent_existing_file_is_not_replaced(self):
        target = self.home / 'model-deepseek-flash.patch.yml'
        link = os.link
        def concurrent(source, destination):
            target.write_text('concurrent user config', encoding='utf-8')
            link(source, destination)
        with patch.object(host.os, 'link', side_effect=concurrent):
            self.prepare()
        self.assertEqual(target.read_text(encoding='utf-8'), 'concurrent user config')

    def test_path_escape_is_rejected(self):
        with self.assertRaises(host.rsh.HostError):
            host._ensure_model_patch(self.home, dict(self.binding, model_alias='../escape'), 'secret')
        self.assertFalse(self.home.exists())


if __name__ == '__main__':
    unittest.main()
