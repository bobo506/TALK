from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts import dsh_role_setup as setup


class DshRoleSetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        (self.root / '.talk').mkdir()
        self.state = Path(self.temp.name) / 'state'
        self.database = Path(self.temp.name) / 'test.sqlite'
        self.config_path = Path(self.temp.name) / 'config.json'
        self.binding = dict(runner_id='runner:dsh-test', runtime='dsh', model_source='registry',
                            provider_id='provider', connection_ref='conn', model_id='model', model_alias='alias')
        self.entry = dict(self.binding, auth_type='api_key', api_key_env='TALK_DSH_CONNECTION_X_API_KEY',
                          target_api_key_env='DEEPSEEK_API_KEY', command_template='dsh {model} {model_id}',
                          tools_command_template='dsh --tools {model} {model_id}')
        self.config = dict(schema='talk-runtime-config-1', project_id='project', project_root=str(self.root),
                           state_dir=str(self.state), dsh=dict(enabled=True, connections={'conn': self.entry}))
        (self.root / '.talk' / 'runtime.local.json').write_text(json.dumps(dict(schema='talk-local-runtime-1',
            config_file=str(self.config_path), database_file=str(self.database))), encoding='utf-8')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript('''CREATE TABLE project_roles(project_id TEXT,member_id TEXT,archived_at TEXT);
                CREATE TABLE runner_registry(runner_id TEXT,runtime TEXT,control_kind TEXT);
                CREATE TABLE project_role_bindings(project_id TEXT,member_id TEXT,runner_id TEXT,model_source TEXT,
                    provider_id TEXT,connection_ref TEXT,model_id TEXT,model_alias TEXT);
                INSERT INTO project_roles VALUES('project','agent:test',NULL);
                INSERT INTO runner_registry VALUES('runner:dsh-test','dsh','managed_cli');
                INSERT INTO project_role_bindings VALUES('project','agent:test','runner:dsh-test','registry',
                    'provider','conn','model','alias');''')
        self.env = {'TALK_DSH_CONNECTION_X_API_KEY': 'synthetic-secret'}

    def run_setup(self, which=lambda name: name, env=None):
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        return setup.setup('project', 'agent:test', root=self.root, which=which,
                           environ=self.env if env is None else env)

    def assert_failure(self, code, **kwargs):
        with self.assertRaises(setup.SetupError) as caught:
            self.run_setup(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(self.state.exists())

    def test_success_and_explicit_profiles(self):
        result = self.run_setup()
        self.assertEqual(result['profile'], 'tools')
        self.assertTrue((self.state / 'native' / 'project' / 'agent_test' / '.dsh').is_dir())
        for profile in ('review', 'tools'):
            self.config['dsh']['task_profiles'] = {'agent:test': profile}
            self.assertEqual(self.run_setup()['profile'], profile)

    def test_missing_connection_and_mismatch(self):
        del self.config['dsh']['connections']['conn']
        self.assert_failure('dsh_connection_required')
        self.config['dsh']['connections']['conn'] = self.entry
        self.entry['model_id'] = 'other'
        self.assert_failure('dsh_connection_mismatch')

    def test_missing_binding_model_and_runner(self):
        for sql, code in [("UPDATE project_role_bindings SET model_id=NULL", 'native_model_configuration_required'),
                          ("DELETE FROM project_role_bindings", 'native_setup_not_supported')]:
            with self.subTest(sql=sql):
                with closing(sqlite3.connect(self.database)) as db, db:
                    db.execute(sql)
                self.assert_failure(code)

    def test_missing_cli_secret_and_tools(self):
        self.assert_failure('native_cli_missing', which=lambda _: None)
        self.assert_failure('dsh_connection_secret_missing', env={})
        del self.entry['tools_command_template']
        self.assert_failure('dsh_command_invalid')

    def test_reserved_and_credentials(self):
        self.entry['target_api_key_env'] = 'TALK_API_KEY'
        self.assert_failure('dsh_connection_mismatch')
        self.entry['target_api_key_env'] = 'DEEPSEEK_API_KEY'
        self.entry['tools_command_template'] += ' --api-key=bad'
        self.assert_failure('dsh_command_invalid')
        self.entry['tools_command_template'] = 'dsh {model} {model_id} synthetic-secret'
        self.assert_failure('dsh_command_invalid')

    def test_invalid_profile_and_control_kind(self):
        self.config['dsh']['task_profiles'] = {'agent:test': 'unknown'}
        self.assert_failure('dsh_task_profile_invalid')
        self.config['dsh']['task_profiles'] = {}
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE runner_registry SET control_kind='other'")
        self.assert_failure('native_setup_not_supported')


if __name__ == '__main__':
    unittest.main()
