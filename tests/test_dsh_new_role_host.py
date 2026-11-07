import json
from pathlib import Path
import tempfile
import unittest

from scripts import dsh_role_host as host


class DshHostTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {
            'project_id': 'prj_test',
            'project_root': str(self.root / 'project'),
            'state_dir': str(self.root / 'state'),
            'key_root': str(self.root / 'keys'),
            'base_url': 'http://127.0.0.1:8000',
            'operator_key_file': str(self.root / 'operator.key'),
            'dsh': {'enabled': True, 'task_profiles': {'agent:test': 'tools'}},
        }
        self.role = {
            'project_id': 'prj_test',
            'member_id': 'agent:test',
            'archived': False,
            'binding_state': 'bound',
            'runner': {'runtime': 'dsh', 'runner_id': 'runner:dsh-test'},
            'service': {'control_kind': 'managed_cli'},
            'model': {'choice_id': 'choice', 'model_alias': 'alias'},
            'role_name': 'Test DSH',
        }

    def test_manager_directory_isolation(self):
        path = host.manager_directory(self.config['state_dir'], 'prj_test', 'agent:test')
        self.assertEqual(path, (self.root / 'state' / 'dsh-dynamic' / 'prj_test' / 'agent_test').resolve())
        self.assertEqual(len(host.manager_directory(self.config['state_dir'], 'prj_test', 'agent:other').parts), len(path.parts))

    def test_host_spec_defaults_to_tools_and_review_override(self):
        spec = host.host_spec(self.config, self.role)
        self.assertIsNotNone(spec)
        self.assertIn('--task-profile', spec['argv'])
        self.assertEqual(spec['argv'][spec['argv'].index('--task-profile') + 1], 'tools')
        self.assertTrue(spec['health_file'].endswith('manager-health.json'))
        self.config['dsh']['task_profiles'] = {'agent:test': 'review'}
        self.assertEqual(host.host_spec(self.config, self.role)['argv'][
            spec['argv'].index('--task-profile') + 1], 'review')

    def test_host_spec_rejects_disabled_invalid_and_unbound(self):
        self.config['dsh']['enabled'] = False
        self.assertIsNone(host.host_spec(self.config, self.role))
        self.config['dsh']['enabled'] = True
        self.role['binding_state'] = 'unbound'
        self.assertIsNone(host.host_spec(self.config, self.role))
        self.role['binding_state'] = 'bound'
        self.role['service']['control_kind'] = 'other'
        self.assertIsNone(host.host_spec(self.config, self.role))
        self.role['service']['control_kind'] = 'managed_cli'
        self.role['runner']['runner_id'] = 'runner:codex-test'
        self.assertIsNone(host.host_spec(self.config, self.role))
        self.role['runner']['runner_id'] = 'runner:dsh-test'
        self.config['dsh']['task_profiles'] = {'agent:test': 'unknown'}
        with self.assertRaises(ValueError):
            host.host_spec(self.config, self.role)

    def test_health_contains_owned_launches(self):
        private = self.root / 'state' / 'dsh-dynamic' / 'prj_test' / 'agent_test'
        fake = object.__new__(host.DshRoleHost)
        fake.project = 'prj_test'
        fake.member = 'agent:test'
        fake.private = private
        fake.drain_requested = False
        fake._health_degraded = False
        fake.workspace_context = None
        fake._handles = {'a': {'record': {}}, 'b': {'record': {}}}
        host.DshRoleHost.publish_health(fake, 'serving')
        value = json.loads((private / 'manager-health.json').read_text(encoding='utf-8'))
        self.assertEqual(value['schema'], 'talk-dsh-manager-health-1')
        self.assertEqual(value['state'], 'serving')
        self.assertEqual(value['owned_launches'], ['a', 'b'])
        self.assertEqual(value['project_id'], 'prj_test')
        self.assertEqual(value['member_id'], 'agent:test')


if __name__ == '__main__':
    unittest.main()
