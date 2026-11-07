"""Isolated fake host tests for DSH and WorkBuddy workspace contexts."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import dsh_role_host as dsh, workbuddy_role_host as wb
from scripts import role_service_host as rsh
from server import workspace_paths as wp


class WorkspaceHostsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='w3b-host-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'; self.data.mkdir()
        self.project = self.root / 'project'; self.project.mkdir()
        self.keys = self.root / 'keys'
        self.state = self.root / 'state'
        self.exe = self.root / 'workbuddy.exe'; self.exe.write_text('fake', encoding='utf-8')
        self.client = Mock()

    def context(self, runner, member='agent:one'):
        args = (self.data, 'p', member)
        return {'data_root': str(self.data), 'project_root': str(self.project),
            'project_id': 'p', 'member_id': member, 'layout': 'workspace-v1', 'runner': runner,
            'key': str(wp.key_path(*args, git_key_root=self.keys)), 'home': str(wp.native_home_dir(*args)),
            'session': str(wp.execution_session_store_path(*args)), 'logs': str(wp.logs_dir(*args)),
            'state': {'records': str(wp.records_dir(*args)), 'control': str(wp.control_dir(*args)),
                      'manager': str(wp.manager_dir(*args, runner))}}

    def manager(self, runner, context):
        member = context['member_id']
        common = dict(state_dir=self.state, project_root=self.project, role_key_root=self.keys,
            role_key_file=Path(context['key']), workspace_context=context, workspace_project='p',
            workspace_member=member, workspace_data_root=self.data)
        if runner == 'dsh':
            return dsh.DshRoleHost(self.client, project='p', member=member, display_name='test',
                task_profile='tools', private=self.root/'unused', runtime_config={}, **common)
        return wb.WorkBuddyRoleHost(self.client, project_id='p', member_id=member,
            executable=self.exe, models_home=self.root, display_name='test', **common)

    def test_workspace_environment_health_drain_and_role_isolation(self):
        for runner in ('dsh', 'workbuddy'):
            with self.subTest(runner=runner):
                context = self.context(runner)
                manager = self.manager(runner, context)
                if runner == 'dsh':
                    manager._active_connection = object(); manager._active_binding_fingerprint = 'fake'
                with patch.object(dsh, 'connection_environment', return_value={}):
                    env = manager.child_environment('p', 'agent:one')
                for name in rsh.NATIVE_HOME_ENV_VARS:
                    self.assertEqual(Path(env[name]), Path(context['home']))
                if runner == 'dsh':
                    self.assertEqual(Path(env['DSH_HOME']), Path(context['home']) / '.dsh')
                    manager.publish_health()
                else:
                    with patch.object(rsh.HostManager, 'build_entry_argv', return_value=([], 'fake', 'fake')):
                        argv, _, _ = manager.build_entry_argv('workbuddy', 'custom-local:fake')
                    self.assertEqual(Path(argv[argv.index('--workbuddy-native-home') + 1]), Path(context['home']) / '.codebuddy')
                    manager.health()
                self.assertEqual(manager.private, Path(context['state']['manager']))
                self.assertEqual(manager.private.parts[-3:], ('state', 'manager', runner))
                self.assertEqual(json.loads((manager.private/'manager-health.json').read_text(encoding='utf-8'))['member_id'], 'agent:one')
                (manager.private/'drain.request').write_text('drain', encoding='utf-8')
                with self.assertRaises(dsh.Drained if runner == 'dsh' else wb.Drained):
                    manager.claimable_actions('p')
                other = self.manager(runner, self.context(runner, 'agent:two'))
                self.assertNotEqual(manager.private, other.private)
                self.assertNotEqual(manager.store.native_home_dir('p', 'agent:one'), other.store.native_home_dir('p', 'agent:two'))
                self.assertFalse((other.private/'drain.request').exists())

    def test_invalid_context_rejected_before_writes(self):
        for runner in ('dsh', 'workbuddy'):
            for field in ('runner', 'member_id', 'home', 'manager', 'layout'):
                context = self.context(runner); bad = deepcopy(context)
                if field == 'manager': bad['state']['manager'] = str(self.root/'outside')
                else: bad[field] = str(self.root/'outside') if field == 'home' else 'wrong'
                with self.subTest(runner=runner, field=field), self.assertRaises(rsh.HostError) as caught:
                    self.manager(runner, bad)
                self.assertEqual(caught.exception.code, 'workspace_context_invalid')
            self.assertFalse((self.root/'outside').exists())

    def argv(self, runner):
        common = ['--project', 'p', '--member', 'agent:one', '--project-root', str(self.project),
            '--state-dir', str(self.state), '--base-url', 'http://127.0.0.1:1',
            '--operator-key-file', str(self.root/'human.key'), '--role-key-file', str(self.root/'role.key'), '--apply']
        if runner == 'dsh':
            return common + ['--expected-choice-id', 'choice', '--expected-model-alias', 'alias']
        return ['serve'] + common + ['--workbuddy-executable', str(self.exe), '--workbuddy-models-home', str(self.root),
            '--workbuddy-display-name', 'test', '--runtime-verified', 'workbuddy']

    def test_legacy_no_layout_query(self):
        (self.root/'role.key').write_text('fake', encoding='utf-8')
        for runner in ('dsh', 'workbuddy'):
            layout = Mock(side_effect=AssertionError('unexpected layout query'))
            role = {'member_id':'agent:one', 'binding_state':'bound', 'runner':{'runtime':'dsh','runner_id':'runner:dsh-fake'},
                    'model':{'choice_id':'choice','model_alias':'alias'}}
            class Client:
                def request(inner, method, path, **kwargs):
                    if path.endswith('/role-storage-layouts'): return layout(method, path, **kwargs)
                    if path == '/api/members/me':
                        return {'id':'agent:one','kind':'agent','display_name':'test'} if kwargs.get('key') else {'kind':'human'}
                    return [role]
                def close(inner): pass
            module = dsh if runner == 'dsh' else wb
            cls = dsh.DshRoleHost if runner == 'dsh' else wb.WorkBuddyRoleHost
            def drain(manager, *args, **kwargs):
                self.assertIsNone(manager.workspace_context)
                expected = self.state / ('dsh-dynamic' if runner == 'dsh' else 'workbuddy-native') / 'p' / 'agent_one'
                self.assertEqual(manager.private, expected)
                raise module.Drained()
            with patch.object(rsh, 'load_operator_key', return_value='fake'), patch.object(rsh, 'TalkHostClient', return_value=Client()), \
                 patch.object(dsh, '_local_facts', return_value=({}, None)), \
                 patch('scripts.dsh_role_setup.setup', return_value={'profile':'tools'}), patch.object(cls, 'serve', new=drain):
                self.assertEqual(module.main(self.argv(runner)), 0)
            layout.assert_not_called()

    def test_missing_or_mismatched_layout_rejected_before_key_or_manager(self):
        for runner in ('dsh', 'workbuddy'):
            context = self.context(runner); argv = self.argv(runner)
            argv[argv.index('--role-key-file')+1] = context['key']
            argv += ['--workspace-context', json.dumps(context), '--key-root', str(self.keys)]
            role = {'member_id':'agent:one', 'binding_state':'bound', 'runner':{'runtime':'dsh','runner_id':'runner:dsh-fake'},
                    'model':{'choice_id':'choice','model_alias':'alias'}}
            for rows in ([], [{'member_id':'agent:one','storage_layout':'legacy'}]):
                class Client:
                    def request(inner, method, path, **kwargs):
                        if path == '/api/members/me': return {'kind':'human'}
                        if path.endswith('/role-storage-layouts'): return rows
                        return [role]
                validate = rsh.validate_workspace_context
                def checked(value, **kwargs):
                    kwargs['data_root'] = self.data
                    return validate(value, **kwargs)
                module = dsh if runner == 'dsh' else wb
                with self.subTest(runner=runner, rows=rows), patch.object(rsh, 'validate_workspace_context', side_effect=checked), \
                     patch.object(rsh, 'load_operator_key', return_value='fake'), patch.object(rsh, 'TalkHostClient', return_value=Client()), \
                     patch.object(dsh, '_local_facts', return_value=({}, None)), patch.object(Path, 'read_text', side_effect=AssertionError('key read')), \
                     patch('sys.stdout', new_callable=io.StringIO) as out:
                    if runner == 'dsh':
                        self.assertEqual(module.main(argv), 1)
                        self.assertEqual(json.loads(out.getvalue())['error_code'], 'workspace_context_invalid')
                    else:
                        with self.assertRaises(rsh.HostError) as caught: module.main(argv)
                        self.assertEqual(caught.exception.code, 'workspace_context_invalid')
                self.assertFalse(Path(context['state']['manager']).exists())

    def test_missing_context_arguments_rejected(self):
        for runner in ('dsh', 'workbuddy'):
            argv = self.argv(runner) + ['--workspace-context', '{}']
            if runner == 'dsh':
                with patch('sys.stdout', new_callable=io.StringIO) as out:
                    self.assertEqual(dsh.main(argv), 1)
                self.assertEqual(json.loads(out.getvalue())['error_code'], 'workspace_context_invalid')
            else:
                with self.assertRaises(rsh.HostError) as caught: wb.main(argv)
                self.assertEqual(caught.exception.code, 'workspace_context_invalid')
    def test_main_valid_context_passes_to_manager_and_drains(self):
        for runner in ('dsh', 'workbuddy'):
            context = self.context(runner)
            Path(context['key']).parent.mkdir(parents=True, exist_ok=True)
            Path(context['key']).write_text('fake', encoding='utf-8')
            argv = self.argv(runner)
            argv[argv.index('--role-key-file')+1] = context['key']
            argv += ['--workspace-context', json.dumps(context), '--key-root', str(self.keys)]
            role = {'member_id':'agent:one', 'binding_state':'bound', 'runner':{'runtime':'dsh','runner_id':'runner:dsh-fake'},
                    'model':{'choice_id':'choice','model_alias':'alias'}}
            class Client:
                def request(inner, method, path, **kwargs):
                    if path == '/api/members/me':
                        return {'id':'agent:one','kind':'agent','display_name':'test'} if kwargs.get('key') else {'kind':'human'}
                    if path.endswith('/role-storage-layouts'): return [{'member_id':'agent:one','storage_layout':'workspace-v1'}]
                    return [role]
                def close(inner): pass
            real_validate = rsh.validate_workspace_context
            def checked(value, **kwargs):
                kwargs['data_root'] = self.data
                return real_validate(value, **kwargs)
            module = dsh if runner == 'dsh' else wb
            cls = dsh.DshRoleHost if runner == 'dsh' else wb.WorkBuddyRoleHost
            def isolated(*args, **kwargs):
                kwargs['workspace_data_root'] = self.data
                return cls(*args, **kwargs)
            def drain(manager, *args, **kwargs):
                self.assertEqual(manager.private, Path(context['state']['manager']))
                manager.private.mkdir(parents=True, exist_ok=True)
                (manager.private/'drain.request').write_text('drain', encoding='utf-8')
                self.assertTrue(manager._workspace_manager_tick('p'))
            db = Mock()
            with self.subTest(runner=runner), patch.object(rsh, 'validate_workspace_context', side_effect=checked), \
                 patch.object(rsh, 'load_operator_key', return_value='fake'), patch.object(rsh, 'TalkHostClient', return_value=Client()), \
                 patch.object(dsh, '_local_facts', return_value=({'dsh':{}}, 'fake-db')), \
                 patch('scripts.kimi_role_setup._open_db', return_value=db), patch('scripts.dsh_role_setup._role', return_value={}), \
                 patch.object(dsh, 'resolve_connection', return_value={}), patch.object(dsh, 'connection_environment', return_value={'fake':'fake'}), \
                 patch.object(dsh, 'validate_command') as validate_command, patch('scripts.dsh_role_setup.setup') as legacy_setup, \
                 patch.object(cls, 'serve', new=drain), patch.object(module, cls.__name__, side_effect=isolated):
                self.assertEqual(module.main(argv), 0)
                legacy_setup.assert_not_called()
                if runner == 'dsh':
                    self.assertEqual(validate_command.call_count, 2)
                    for call in validate_command.call_args_list:
                        self.assertEqual(call.kwargs['native_home'], Path(context['home']).as_posix())
                    self.assertTrue((Path(context['home'])/'.dsh').is_dir())
                    self.assertFalse((self.state/'native').exists())
            health = json.loads((Path(context['state']['manager'])/'manager-health.json').read_text(encoding='utf-8'))
            self.assertEqual((health['state'], health['draining']), ('stopped', True))
