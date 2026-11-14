import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import codex_role_setup, kimi_role_setup
from server import kimi_native_setup as setup
from server.models import (Project, ProjectRole, ProjectRoleBinding, RoleCreationOperation,
                           RoleNativeSetup, RoleProvisionJob, RoleServiceState, RunnerRegistry)
from server.workspace_paths import native_home_dir

PROJECT, MEMBER = 'prj_test', 'agent:test'


class NativeRootsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='talk-native-roots-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        env_patch = patch.dict(os.environ, {'KIMI_CODE_HOME': str(self.base / 'source-home')})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.project_root = self.base / 'data' / 'project'
        (self.project_root / '.talk').mkdir(parents=True)
        self.config_path = self.base / 'runtime.json'
        self.database = self.base / 'roles.db'
        self.config = {'schema': 'talk-runtime-config-1', 'project_id': PROJECT,
                       'project_root': str(self.project_root), 'state_dir': str(self.base / 'state')}
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        (self.project_root / '.talk' / 'runtime.local.json').write_text(json.dumps({
            'schema': 'talk-local-runtime-1', 'config_file': str(self.config_path),
            'database_file': str(self.database)}), encoding='utf-8')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript('''
                CREATE TABLE project_roles (project_id TEXT, member_id TEXT, archived_at TEXT, storage_layout TEXT);
                CREATE TABLE project_role_bindings (project_id TEXT, member_id TEXT, runner_id TEXT,
                    model_alias TEXT, model_id TEXT, provider_id TEXT, model_source TEXT, connection_ref TEXT);
                CREATE TABLE runner_registry (runner_id TEXT, runtime TEXT, control_kind TEXT);
                CREATE TABLE role_service_state (project_id TEXT, member_id TEXT, desired_state TEXT,
                    observed_state TEXT, owner_host TEXT, process_launch_id TEXT);
            ''')
            db.execute('INSERT INTO project_roles VALUES (?, ?, NULL, ?)', (PROJECT, MEMBER, 'workspace-v1'))

    def prepare_binding(self, runtime, layout='workspace-v1'):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('UPDATE project_roles SET storage_layout=?', (layout,))
            db.execute('DELETE FROM runner_registry')
            db.execute('DELETE FROM project_role_bindings')
            db.execute('INSERT INTO runner_registry VALUES (?, ?, ?)', ('runner', runtime, 'managed_cli'))
            provider, connection = (('openai', 'native-codex-chatgpt-login') if runtime == 'codex'
                                    else ('managed:kimi-code', 'native-kimi-code-managed-login'))
            db.execute('INSERT INTO project_role_bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (PROJECT, MEMBER, 'runner', 'test/model', 'model', provider, 'builtin', connection))

    def begin(self, runtime, *, data_root, layout='workspace-v1'):
        self.prepare_binding(runtime, layout)
        module = codex_role_setup if runtime == 'codex' else kimi_role_setup
        popen = Mock(return_value=SimpleNamespace())
        def spawn(home, project, member, lock, callback, **kwargs):
            return callback(0), None
        with ExitStack() as stack:
            stack.enter_context(patch.object(module, 'acquire_lock', return_value=object()))
            stack.enter_context(patch.object(module, 'release_lock'))
            stack.enter_context(patch('scripts.native_setup_process.stop_previous'))
            stack.enter_context(patch('scripts.native_setup_process.spawn_recorded', side_effect=spawn))
            if runtime == 'codex':
                stack.enter_context(patch.object(module, 'executable', return_value='codex.exe'))
                stack.enter_context(patch.object(module, 'require_version', return_value='test'))
                stack.enter_context(patch.object(module, 'write_config'))
            else:
                stack.enter_context(patch.object(module.shutil, 'which', return_value='kimi.exe'))
            attempt = module.begin_native_login(PROJECT, MEMBER, root=self.project_root,
                                               data_root=data_root, popen=popen)
            self.assertEqual(popen.call_args.kwargs['cwd'], str(self.project_root))
            self.assertEqual(Path(popen.call_args.kwargs['env']['HOME']), attempt.home)
            if runtime == 'kimi-code':
                with patch.object(module, '_append_model', return_value='existing'):
                    self.assertEqual(module.finish_native_login(attempt), 'existing')
            return attempt

    def test_portable_login_and_legacy_home(self):
        for runtime in ('codex', 'kimi-code'):
            with self.subTest(runtime=runtime), patch.dict(os.environ, {'TALK_HOME': str(self.base)}):
                attempt = self.begin(runtime, data_root=self.base)
                self.assertEqual(attempt.home, native_home_dir(self.base, PROJECT, MEMBER))
                self.assertFalse((self.project_root / 'workspaces').exists())
                self.assertFalse((self.base / '.talk').exists())
                legacy = self.begin(runtime, data_root=self.base, layout='legacy')
                self.assertTrue(legacy.home.is_relative_to(self.base / 'state' / 'native'))

    def test_default_data_root_matches_project_root(self):
        with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != 'TALK_HOME'}, clear=True):
            for runtime in ('codex', 'kimi-code'):
                with self.subTest(runtime=runtime):
                    attempt = self.begin(runtime, data_root=None)
                    self.assertEqual(attempt.home, native_home_dir(self.project_root, PROJECT, MEMBER))

    def test_manager_passes_database_project_root_and_portable_data_root(self):
        row = RoleNativeSetup(project_id=PROJECT, member_id=MEMBER, choice_id='choice',
                              created_by='human:test', revision=1, status='failed')
        role = SimpleNamespace(archived_at=None, storage_layout='workspace-v1', credential_version=1)
        binding = SimpleNamespace(runner_id='runner')
        runner = SimpleNamespace(runtime='codex', control_kind='managed_cli')
        operation = SimpleNamespace(operation_key='op', choice_id='choice')
        job = SimpleNamespace(status='succeeded', credential_version=1)
        project = SimpleNamespace(project_root_path=str(self.project_root))
        values = {Project: project, ProjectRole: role, ProjectRoleBinding: binding,
                  RunnerRegistry: runner, RoleProvisionJob: job, RoleServiceState: None,
                  RoleNativeSetup: row}
        session = Mock()
        session.get.side_effect = lambda model, key: values[model]
        attempt = SimpleNamespace(process=SimpleNamespace())
        manager = setup.NativeSetupManager()
        with patch.dict(os.environ, {'TALK_HOME': str(self.base)}), \
             patch.object(setup, '_operation', return_value=operation), \
             patch.object(setup, '_selection_current', return_value=True), \
             patch.object(codex_role_setup, 'begin_native_login', return_value=attempt) as begin, \
             patch.object(setup.threading, 'Thread'):
            output = manager._start_locked(PROJECT, MEMBER, 1, 'human:test', session)
            self.assertEqual(output.status, 'starting')
            begin.assert_called_once_with(PROJECT, MEMBER, root=self.project_root, data_root=self.base)

    def test_ready_and_start_fact_use_data_root(self):
        role = SimpleNamespace(storage_layout='workspace-v1')
        project = SimpleNamespace(project_root_path=str(self.project_root))
        row = RoleNativeSetup(project_id=PROJECT, member_id=MEMBER, choice_id='choice',
                              created_by='human:test', revision=1, status='ready')
        session = Mock()
        session.get.side_effect = lambda model, key: {Project: project, ProjectRole: role,
                                                       RoleNativeSetup: row}[model]
        home = native_home_dir(self.base, PROJECT, MEMBER) / '.codex'
        home.mkdir(parents=True)
        (home / 'config.toml').write_text('model = "model"\n', encoding='utf-8')
        with patch.dict(os.environ, {'TALK_HOME': str(self.base)}), \
             patch.object(setup, '_role_runtime', return_value='codex'), \
             patch.object(setup, '_selection_current', return_value=True):
            self.assertEqual(setup.native_login_fact(PROJECT, MEMBER, session), (True, True))
            self.assertEqual(setup._out(row, session).status, 'ready')
            setup.require_native_setup_for_start(PROJECT, MEMBER, session)
            (home / 'config.toml').unlink()
            self.assertEqual(setup.native_login_fact(PROJECT, MEMBER, session), (True, False))
            self.assertEqual(setup._out(row, session).error_code, 'native_model_configuration_required')

    def test_relative_stored_project_root_is_ignored(self):
        session = Mock()
        session.get.return_value = SimpleNamespace(project_root_path='relative/path')
        with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != 'TALK_HOME'}, clear=True):
            self.assertEqual(setup._roots(PROJECT, session, self.project_root),
                             (self.project_root, self.project_root))


if __name__ == '__main__':
    unittest.main()
