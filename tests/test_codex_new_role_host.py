"""New Codex role host: real HTTP/owned process, no model execution."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from scripts import codex_role_host as host
from scripts import talk_runtime as runtime
from scripts.role_provision import key_file_path
from tests.test_talk_runtime import Client, Process

ROOT = Path(__file__).resolve().parents[1]


class NewCodexRoleHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='codex-new-role-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'project').mkdir()
        (self.root / 'state').mkdir()
        self.config = {'schema': 'talk-runtime-config-1', 'version': 1, 'project_id': 'p',
            'project_root': str(self.root / 'project'), 'state_dir': str(self.root / 'state'),
            'key_root': str(self.root / 'keys'), 'operator_key_file': str(self.root / 'human.key'),
            'base_url': 'http://127.0.0.1:1', 'hosts': [], 'codex': {'enabled': True, 'executable': str(self.root / 'codex.exe')},
            'api_argv': [sys.executable, '-m', 'scripts.talk_api', '--control-file', '{control_file}']}
        self.role = {'project_id': 'p', 'member_id': 'agent:new', 'role_name': 'new Codex',
            'archived': False, 'binding_state': 'bound',
            'runner': {'runtime': 'codex', 'status': 'unverified'},
            'model': {'choice_id': 'rmc_new', 'model_alias': 'model-selected', 'model_id': 'model-selected'},
            'service': {'generation': 1, 'ownership_held': False, 'control_kind': 'managed_cli'}}
        self.client = Client()
        self.client.identity = {'id': 'agent:new', 'kind': 'agent', 'display_name': 'new Codex'}
        self.spawned = []
        def spawn(label, argv):
            process = Process(300 + len(self.spawned))
            self.spawned.append((label, argv, process))
            return process
        self.runtime = runtime.TalkRuntime(self.config, client=self.client, spawn=spawn)

    def key(self, member='agent:new'):
        key = key_file_path(Path(self.config['key_root']), member)
        key.parent.mkdir(parents=True, exist_ok=True)
        key.write_text('synthetic-role-key', encoding='utf-8')
        return key

    def test_new_role_is_discovered_after_boot_and_uses_current_identity_and_model(self):
        self.runtime.reconcile_hosts([])
        self.assertFalse(self.spawned)
        self.key()
        self.runtime.reconcile_hosts([self.role])
        self.runtime.reconcile_hosts([self.role])
        self.assertEqual(len(self.spawned), 1)
        argv = self.spawned[0][1]
        self.assertEqual(argv[argv.index('--member') + 1], 'agent:new')
        self.assertEqual(argv[argv.index('--expected-choice-id') + 1], 'rmc_new')
        self.assertEqual(argv[argv.index('--expected-model-alias') + 1], 'model-selected')
        self.assertEqual(argv[argv.index('--task-profile') + 1], 'tools')
        self.assertFalse(any(call[0] == 'POST' for call in self.client.calls))

    def test_public_roles_dto_shape_keeps_control_kind_in_service_not_runner(self):
        role = deepcopy(self.role)
        role.pop('project_id')
        self.assertNotIn('control_kind', role['runner'])
        self.assertIsNotNone(host.host_spec(self.config, role))

    def test_disabled_wrong_project_unbound_archived_and_nonmanaged_do_not_spawn(self):
        self.key()
        cases = []
        for field, value in [('project_id', 'other'), ('binding_state', 'unconfigured'), ('archived', True)]:
            role = deepcopy(self.role); role[field] = value; cases.append(role)
        role = deepcopy(self.role); role['service']['control_kind'] = 'external_desktop'; cases.append(role)
        for role in cases:
            self.assertIsNone(self.runtime.codex_spec(role))
        self.config['codex']['enabled'] = False
        self.assertIsNone(self.runtime.codex_spec(self.role))
        self.assertFalse(self.client.calls)
        self.assertFalse(self.spawned)

    def test_missing_or_wrong_person_key_never_creates_host(self):
        self.runtime.reconcile_hosts([self.role])
        self.assertEqual(self.runtime.statuses['agent:new']['state'], 'key_not_configured')
        self.key(); self.client.identity['id'] = 'agent:other'
        self.runtime.reconcile_hosts([self.role])
        self.assertEqual(self.runtime.statuses['agent:new']['state'], 'identity_mismatch')
        self.assertFalse(self.spawned)

    def test_explicit_old_host_takes_priority_and_is_not_replaced(self):
        directory = self.root / 'state' / 'old'; directory.mkdir()
        self.config['hosts'] = [{'member_id': 'agent:new', 'argv': [sys.executable, 'old.py'],
            'health_file': str(directory / 'health.json'), 'drain_file': str(directory / 'drain.request')}]
        self.runtime.reconcile_hosts([self.role])
        self.assertEqual(self.spawned[0][1], [sys.executable, 'old.py'])
        self.assertFalse(self.client.calls)

    def test_task_profile_defaults_to_tools_and_supports_explicit_review(self):
        spec = host.host_spec(self.config, self.role)
        argv = spec['argv']; self.assertEqual(argv[argv.index('--task-profile') + 1], 'tools')
        self.config['codex']['task_profiles'] = {'agent:new': 'review'}
        spec = host.host_spec(self.config, self.role)
        argv = spec['argv']; self.assertEqual(argv[argv.index('--task-profile') + 1], 'review')
        other = deepcopy(self.role); other['member_id'] = 'agent:other'
        argv = host.host_spec(self.config, other)['argv']
        self.assertEqual(argv[argv.index('--task-profile') + 1], 'tools')
        self.config['codex']['task_profiles']['agent:new'] = 'unrestricted'
        config = self.root / 'runtime.json'; config.write_text(json.dumps(self.config), encoding='utf-8')
        with self.assertRaisesRegex(runtime.RuntimeErrorCode, 'runtime_host_config_invalid'):
            runtime.load_config(config)

    def manager(self, member='agent:new'):
        return host.CodexRoleHost(self.client, project='p', member=member, display_name='Codex',
            task_profile='review', codex_executable=str(self.root / 'codex.exe'), private=host.manager_directory(self.config['state_dir'], 'p', member),
            state_dir=Path(self.config['state_dir']), project_root=self.root / 'project')

    def test_generated_bridge_argv_passes_real_host_preflight_parser(self):
        from scripts import codex_role_setup as setup
        from bridges import codex_bridge
        for profile, timeout in [('review', None), ('tools', 123)]:
            with self.subTest(profile=profile, timeout=timeout):
                manager = self.manager()
                manager.task_profile = profile
                manager.execution_timeout_seconds = timeout
                config = {'model': 'gpt-6.1-terra', 'model_reasoning_effort': 'low'}
                with patch.object(manager, '_configuration', return_value=(config, 'low')), \
                     patch.object(manager, 'child_environment', return_value={}), \
                     patch.object(setup, 'require_version'), \
                     patch('cli.profiles.load_profile', return_value={}), \
                     patch('cli.profiles.compose_system_prompt', return_value='synthetic instructions'):
                    argv, _, _ = manager.build_entry_argv('codex', 'gpt-6.1-terra')
                fingerprint = host.rsh.verify_runtime_entry('codex', argv)
                self.assertTrue(fingerprint.startswith('bridges.codex_bridge@'))
                self.assertGreater(host.rsh.parse_unit_count(argv, 'codex'), 0)
                parsed = codex_bridge.build_parser().parse_args(argv[3:])
                self.assertEqual(parsed.timeout, timeout or 86400)
                self.assertEqual(parsed.codex_execution_profile,
                                 'tools' if profile == 'tools' else 'discussion')
                for command in (parsed.codex_command, parsed.codex_task_command,
                                parsed.task_preflight_command):
                    self.assertIn("developer_instructions=", command)
                    self.assertNotIn("base_instructions", command)
                self.assertIn('windows.sandbox="unelevated"', parsed.codex_command)
                self.assertIn('windows.sandbox="unelevated"', parsed.task_preflight_command)
                expected_sandbox = 'elevated' if profile == 'tools' else 'unelevated'
                self.assertIn('windows.sandbox="' + expected_sandbox + '"', parsed.codex_task_command)
                self.assertEqual('--add-dir' in parsed.codex_task_command, profile == 'tools')
                self.assertNotIn('--add-dir', parsed.codex_command)
                self.assertNotIn('--add-dir', parsed.task_preflight_command)

    # ── 351-B：思考强度按公开绑定解析并写入执行命令 ───────────────────
    def test_configuration_resolves_effort_from_public_binding(self):
        from scripts import codex_role_setup as setup
        manager = self.manager()
        binding = {'runtime': 'codex', 'model_alias': 'gpt-6.1-terra', 'model_id': 'gpt-6.1-terra',
                   'provider_id': 'openai', 'binding_state': 'bound',
                   'default_effort': 'low', 'effective_effort': 'high', 'effort_override': 'high',
                   'effort_options': ['low', 'medium', 'high', 'xhigh'], 'effort_source': 'catalog'}
        config = {'model': 'gpt-6.1-terra', 'model_reasoning_effort': 'low'}
        with patch.object(manager, '_current_binding', return_value=binding), \
             patch.object(setup, 'read_config', return_value=config):
            resolved, effort = manager._configuration('gpt-6.1-terra')
        self.assertEqual(resolved, config)
        self.assertEqual(effort, 'high')

    def test_configuration_rejects_unsupported_override_instead_of_downgrading(self):
        from scripts import codex_role_setup as setup
        manager = self.manager()
        binding = {'runtime': 'codex', 'model_alias': 'gpt-6.1-terra', 'model_id': 'gpt-6.1-terra',
                   'provider_id': 'openai', 'effective_effort': 'ultra'}
        config = {'model': 'gpt-6.1-terra', 'model_reasoning_effort': 'low'}
        with patch.object(manager, '_current_binding', return_value=binding), \
             patch.object(setup, 'read_config', return_value=config):
            with self.assertRaises(host.rsh.HostError) as caught:
                manager._configuration('gpt-6.1-terra')
        self.assertEqual(caught.exception.code, 'codex_effort_unsupported')

    def test_old_service_binding_keeps_native_config_value(self):
        from scripts import codex_role_setup as setup
        manager = self.manager()
        binding = {'runtime': 'codex', 'model_alias': 'gpt-6.1-terra', 'model_id': 'gpt-6.1-terra',
                   'provider_id': 'openai'}
        config = {'model': 'gpt-6.1-terra', 'model_reasoning_effort': 'low'}
        with patch.object(manager, '_current_binding', return_value=binding), \
             patch.object(setup, 'read_config', return_value=config):
            _, effort = manager._configuration('gpt-6.1-terra')
        self.assertEqual(effort, 'low')

    def test_entry_argv_carries_resolved_effort_not_stale_config_value(self):
        from scripts import codex_role_setup as setup
        manager = self.manager()
        config = {'model': 'gpt-6.1-terra', 'model_reasoning_effort': 'low'}
        with patch.object(manager, '_configuration', return_value=(config, 'xhigh')), \
             patch.object(manager, 'child_environment', return_value={}), \
             patch.object(setup, 'require_version'), \
             patch('cli.profiles.load_profile', return_value={}), \
             patch('cli.profiles.compose_system_prompt', return_value='synthetic instructions'):
            argv, _, _ = manager.build_entry_argv('codex', 'gpt-6.1-terra')
        parsed = argv[argv.index('--codex-task-command') + 1]
        self.assertIn('model_reasoning_effort="xhigh"', parsed)
        self.assertNotIn('model_reasoning_effort="low"', parsed)

    def workspace_context(self):
        from server import workspace_paths as wp
        data = self.root / 'data'
        data.mkdir(exist_ok=True)
        args = (data, 'p', 'agent:new')
        return {'data_root': str(data), 'project_root': str(self.root / 'project'),
            'project_id': 'p', 'member_id': 'agent:new', 'layout': 'workspace-v1',
            'runner': 'codex', 'key': str(wp.key_path(*args, git_key_root=Path(self.config['key_root']))),
            'home': str(wp.native_home_dir(*args)), 'session': str(wp.execution_session_store_path(*args)),
            'logs': str(wp.logs_dir(*args)), 'state': {'records': str(wp.records_dir(*args)),
            'control': str(wp.control_dir(*args)), 'manager': str(wp.manager_dir(*args, 'codex'))}}

    def workspace_manager(self, context):
        return host.CodexRoleHost(self.client, project='p', member='agent:new', display_name='test',
            task_profile='review', private=self.root / 'unused-global',
            state_dir=Path(self.config['state_dir']), project_root=self.root / 'project',
            role_key_root=Path(self.config['key_root']), role_key_file=Path(context['key']),
            workspace_context=context, workspace_project='p', workspace_member='agent:new',
            workspace_data_root=self.root / 'data', codex_executable=str(self.root / 'codex.exe'))

    def test_workspace_home_environment_manager_health_and_drain(self):
        context = self.workspace_context()
        manager = self.workspace_manager(context)
        role_home = Path(context['home'])
        environment = manager.child_environment('p', 'agent:new')
        for variable in host.rsh.NATIVE_HOME_ENV_VARS:
            self.assertEqual(Path(environment[variable]), role_home)
        self.assertEqual(Path(environment['CODEX_HOME']), role_home / '.codex')
        self.assertFalse((role_home / '.codex').exists())
        self.assertEqual(manager.private, Path(context['state']['manager']))
        self.assertEqual(manager.private.parts[-3:], ('state', 'manager', 'codex'))
        manager.publish_health()
        self.assertEqual(json.loads((manager.private / 'manager-health.json').read_text(encoding='utf-8'))['member_id'], 'agent:new')
        (manager.private / 'drain.request').write_text('drain', encoding='utf-8')
        with self.assertRaises(host.Drained):
            manager.claimable_actions('p')
        self.assertFalse((self.root / 'unused-global').exists())

    def test_workspace_rejects_inconsistent_identity_runner_and_paths(self):
        context = self.workspace_context()
        for mutate in ('runner', 'member_id', 'home', 'manager'):
            bad = deepcopy(context)
            if mutate == 'manager':
                bad['state']['manager'] = str(self.root / 'other')
            else:
                bad[mutate] = 'other' if mutate != 'home' else str(self.root / 'other')
            with self.subTest(mutate=mutate), self.assertRaises(host.rsh.HostError) as caught:
                self.workspace_manager(bad)
            self.assertEqual(caught.exception.code, 'workspace_context_invalid')
        manager = self.workspace_manager(context)
        with self.assertRaises(host.rsh.HostError):
            manager.child_environment('p', 'agent:other')

    def test_main_legacy_without_context_never_queries_layout(self):
        self.key()
        layout_request = unittest.mock.Mock(side_effect=AssertionError('unexpected layout query'))
        class FakeClient:
            def request(inner, method, path, **kwargs):
                if path.endswith('/role-storage-layouts'):
                    return layout_request(method, path, **kwargs)
                if path == '/api/members/me':
                    return {'id': 'agent:new', 'kind': 'agent', 'display_name': 'test'} if kwargs.get('key') else {'kind': 'human'}
                return [self.role]
        def drain(manager, *args, **kwargs):
            self.assertIsNone(manager.workspace_context)
            expected_private = Path(self.config['state_dir']) / 'codex-dynamic' / 'p' / 'agent_new'
            self.assertEqual(manager.private, expected_private)
            expected_home = Path(self.config['state_dir']) / 'native' / 'p' / 'agent_new'
            environment = manager.child_environment('p', 'agent:new')
            for variable in host.rsh.NATIVE_HOME_ENV_VARS:
                self.assertEqual(Path(environment[variable]), expected_home)
            self.assertEqual(Path(environment['CODEX_HOME']), expected_home / '.codex')
            self.assertEqual(environment['TALK_ROLE_SERVICE_MANAGED'], '1')
            manager.publish_health()
            health = json.loads((expected_private / 'manager-health.json').read_text(encoding='utf-8'))
            self.assertEqual((health['member_id'], health['state'], health['draining']), ('agent:new', 'serving', False))
            (expected_private / 'drain.request').write_text('drain', encoding='utf-8')
            with self.assertRaises(host.Drained):
                manager.claimable_actions('p')
            raise host.Drained()
        spec = host.host_spec(self.config, self.role)
        argv = spec['argv'][spec['argv'].index('scripts.codex_role_host') + 1:]
        with patch.object(host.rsh, 'load_operator_key', return_value='synthetic'), \
             patch.object(host.rsh, 'TalkHostClient', return_value=FakeClient()), \
             patch.object(host.CodexRoleHost, 'serve', new=drain):
            self.assertEqual(host.main(argv), 0)
        layout_request.assert_not_called()
        health = json.loads(((Path(self.config['state_dir']) / 'codex-dynamic' / 'p' / 'agent_new') / 'manager-health.json').read_text(encoding='utf-8'))
        self.assertEqual((health['state'], health['draining']), ('stopped', True))

    def test_main_rejects_mismatched_layout_before_key_read(self):
        class FakeClient:
            def request(inner, method, path, **kwargs):
                if path == '/api/members/me':
                    return {'kind': 'human'}
                if path.endswith('/role-storage-layouts'):
                    return [{'member_id': 'agent:new', 'storage_layout': 'legacy'}]
                return [self.role]
        spec = host.host_spec(self.config, self.role)
        argv = spec['argv'][spec['argv'].index('scripts.codex_role_host') + 1:]
        context = self.workspace_context()
        argv[argv.index('--role-key-file') + 1] = context['key']
        argv += ['--workspace-context', json.dumps(context), '--key-root', self.config['key_root']]
        validate = host.rsh.validate_workspace_context
        def isolated_validate(value, **kwargs):
            kwargs['data_root'] = self.root / 'data'
            return validate(value, **kwargs)
        with patch.object(host.rsh, 'validate_workspace_context', side_effect=isolated_validate), \
             patch.object(host.rsh, 'load_operator_key', return_value='synthetic'), \
             patch.object(host.rsh, 'TalkHostClient', return_value=FakeClient()), \
             patch.object(Path, 'read_text', side_effect=AssertionError('role key must not be read')), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(host.main(argv), 1)
        self.assertEqual(json.loads(output.getvalue())['error_code'], 'workspace_context_invalid')

    def test_main_rejects_missing_layout_before_key_read(self):
        class FakeClient:
            def request(inner, method, path, **kwargs):
                if path == '/api/members/me':
                    return {'kind': 'human'}
                if path.endswith('/role-storage-layouts'):
                    return []
                return [self.role]
        spec = host.host_spec(self.config, self.role)
        argv = spec['argv'][spec['argv'].index('scripts.codex_role_host') + 1:]
        context = self.workspace_context()
        argv[argv.index('--role-key-file') + 1] = context['key']
        argv += ['--workspace-context', json.dumps(context), '--key-root', self.config['key_root']]
        validate = host.rsh.validate_workspace_context
        def isolated_validate(value, **kwargs):
            kwargs['data_root'] = self.root / 'data'
            return validate(value, **kwargs)
        with patch.object(host.rsh, 'validate_workspace_context', side_effect=isolated_validate), \
             patch.object(host.rsh, 'load_operator_key', return_value='synthetic'), \
             patch.object(host.rsh, 'TalkHostClient', return_value=FakeClient()), \
             patch.object(Path, 'read_text', side_effect=AssertionError('role key must not be read')), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(host.main(argv), 1)
        self.assertEqual(json.loads(output.getvalue())['error_code'], 'workspace_context_invalid')

    def test_main_forwards_valid_workspace_context_and_finishes_draining(self):
        context = self.workspace_context()
        key = Path(context['key'])
        key.parent.mkdir(parents=True, exist_ok=True)
        key.write_text('synthetic', encoding='utf-8')
        class FakeClient:
            def request(inner, method, path, **kwargs):
                if path == '/api/members/me':
                    return {'id': 'agent:new', 'kind': 'agent', 'display_name': 'test'} if kwargs.get('key') else {'kind': 'human'}
                if path.endswith('/role-storage-layouts'):
                    return [{'member_id': 'agent:new', 'storage_layout': 'workspace-v1'}]
                return [self.role]
        validate = host.rsh.validate_workspace_context
        def isolated_validate(value, **kwargs):
            kwargs['data_root'] = self.root / 'data'
            return validate(value, **kwargs)
        real_class = host.CodexRoleHost
        def isolated_manager(*args, **kwargs):
            kwargs['workspace_data_root'] = self.root / 'data'
            return real_class(*args, **kwargs)
        def drain(manager, *args, **kwargs):
            self.assertEqual(manager.private, Path(context['state']['manager']))
            manager.private.mkdir(parents=True, exist_ok=True)
            (manager.private / 'drain.request').write_text('drain', encoding='utf-8')
            self.assertTrue(manager._workspace_manager_tick('p'))
        spec = host.host_spec(self.config, self.role)
        argv = spec['argv'][spec['argv'].index('scripts.codex_role_host') + 1:]
        argv[argv.index('--role-key-file') + 1] = context['key']
        argv += ['--workspace-context', json.dumps(context), '--key-root', self.config['key_root']]
        with patch.object(host.rsh, 'validate_workspace_context', side_effect=isolated_validate), \
             patch.object(host.rsh, 'load_operator_key', return_value='synthetic'), \
             patch.object(host.rsh, 'TalkHostClient', return_value=FakeClient()), \
             patch.object(real_class, 'serve', new=drain), \
             patch.object(host, 'CodexRoleHost', side_effect=isolated_manager):
            self.assertEqual(host.main(argv), 0)
        health = json.loads((Path(context['state']['manager']) / 'manager-health.json').read_text(encoding='utf-8'))
        self.assertEqual((health['state'], health['draining']), ('stopped', True))

    def test_main_rejects_unpaired_workspace_arguments(self):
        spec = host.host_spec(self.config, self.role)
        argv = spec['argv'][spec['argv'].index('scripts.codex_role_host') + 1:] + ['--key-root', self.config['key_root']]
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(host.main(argv), 1)
        self.assertEqual(json.loads(output.getvalue())['error_code'], 'workspace_context_invalid')

    def test_claim_scope_and_drain_keep_only_own_stop_and_owned_handles(self):
        manager = self.manager()
        manager._handles['owned'] = {'record': {'project_id': 'p', 'member_id': 'agent:new'}}
        actions = [dict(project_id='p', member_id='agent:new', action='start'),
            dict(project_id='p', member_id='agent:new', action='stop'),
            dict(project_id='other', member_id='agent:new', action='start'),
            dict(project_id='p', member_id='agent:other', action='stop')]
        with patch.object(host.rsh.HostManager, 'claimable_actions', return_value=actions):
            self.assertEqual(manager.claimable_actions('other'), [])
            self.assertEqual(manager.claimable_actions('p'), actions[:2])
            (manager.private / 'drain.request').write_text('drain', encoding='utf-8')
            self.assertEqual(manager.claimable_actions('p'), [actions[1]])
            self.assertEqual(len(manager._handles), 1)
            manager._handles.clear()
            with self.assertRaises(host.Drained): manager.claimable_actions('p')

    def test_health_publishes_owned_launch_list_for_bounded_deletion(self):
        manager = self.manager()
        manager.publish_health()
        health = manager.private / 'manager-health.json'
        self.assertEqual(json.loads(health.read_text(encoding='utf-8'))['owned_launches'], [])
        manager._handles['launch-owned'] = {'process': object()}
        manager.publish_health()
        self.assertEqual(json.loads(health.read_text(encoding='utf-8'))['owned_launches'], ['launch-owned'])

    def test_health_failure_does_not_block_owned_stop_or_drop_handles(self):
        manager = self.manager()
        manager._handles['owned'] = {'record': {'project_id': 'p', 'member_id': 'agent:new'}}
        manager.drain_requested = True
        actions = [dict(project_id='p', member_id='agent:new', action='stop'),
            dict(project_id='p', member_id='agent:other', action='stop'),
            dict(project_id='p', member_id='agent:new', action='start')]
        with patch.object(manager, 'publish_health', side_effect=host.rsh.HostError('storage_unavailable', 'synthetic health failure')):
            with patch.object(host.rsh.HostManager, 'claimable_actions', return_value=actions):
                with patch('sys.stderr', new=io.StringIO()) as diagnostics:
                    self.assertEqual(manager.claimable_actions('p'), [actions[0]])
                    self.assertEqual(manager.claimable_actions('p'), [actions[0]])
                    self.assertEqual(diagnostics.getvalue(), 'codex_host_health_unavailable\n')
        self.assertEqual(len(manager._handles), 1)

    def test_health_failure_cannot_prevent_empty_drain(self):
        manager = self.manager()
        manager.drain_requested = True
        with patch.object(manager, 'publish_health', side_effect=OSError('synthetic health failure')):
            with patch('sys.stderr', new=io.StringIO()):
                with self.assertRaises(host.Drained):
                    manager.claimable_actions('p')
        self.assertFalse(manager._handles)

    def test_final_health_failure_does_not_turn_clean_drain_into_failure(self):
        self.key(); self.client.rows = [self.role]
        argv = host.host_spec(self.config, self.role)['argv']
        argv = argv[argv.index('scripts.codex_role_host') + 1:]
        request = self.client.request
        def with_layout(method, path, **kwargs):
            if path.endswith('/role-storage-layouts'):
                return [{'member_id': 'agent:new', 'storage_layout': 'legacy'}]
            return request(method, path, **kwargs)
        with patch.object(self.client, 'request', side_effect=with_layout), \
             patch.object(host.rsh, 'load_operator_key', return_value='synthetic-human-key'), \
             patch.object(host.rsh, 'TalkHostClient', return_value=self.client), \
             patch.object(host.CodexRoleHost, 'serve', side_effect=host.Drained), \
             patch.object(host.CodexRoleHost, 'publish_health', side_effect=OSError('synthetic health failure')), \
             patch('sys.stderr', new=io.StringIO()):
            self.assertEqual(host.main(argv), 0)

    def test_native_homes_remain_separate_and_are_not_copied_from_another_role(self):
        a, b = self.manager(), self.manager('agent:other')
        first = a.child_environment('p', 'agent:new')
        second = b.child_environment('p', 'agent:other')
        self.assertNotEqual(first['CODEX_HOME'], second['CODEX_HOME'])
        self.assertFalse(Path(first['CODEX_HOME']).exists())
        with self.assertRaises(host.rsh.HostError): a.child_environment('p', 'agent:other')

    def test_real_http_host_boots_and_drains_without_launching_a_model(self):
        role = deepcopy(self.role)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if self.path == '/api/members/me':
                    value = {'id': 'human:test', 'kind': 'human'} if self.headers.get('X-API-Key') == 'synthetic-human-key' else {'id': 'agent:new', 'kind': 'agent', 'display_name': 'Codex'}
                elif self.path.endswith('/roles'): value = [role]
                elif self.path.endswith('/role-storage-layouts'): value = [{'member_id': 'agent:new', 'storage_layout': 'legacy'}]
                else: value = {'data': []}
                body = json.dumps(value).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        Path(self.config['operator_key_file']).write_text('synthetic-human-key', encoding='utf-8')
        self.key(); self.config['base_url'] = 'http://127.0.0.1:' + str(server.server_port)
        self.config['project_root'] = str(ROOT)
        spec = host.host_spec(self.config, role)
        env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        with (self.root / 'out.log').open('w', encoding='utf-8') as output:
            process = subprocess.Popen(spec['argv'], cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 8
                while not Path(spec['health_file']).is_file() and time.monotonic() < deadline and process.poll() is None:
                    time.sleep(.025)
                self.assertIsNone(process.poll(), (self.root / 'out.log').read_text(encoding='utf-8'))
                health = json.loads(Path(spec['health_file']).read_text(encoding='utf-8'))
                self.assertEqual((health['project_id'], health['member_id'], health['pid'], health['state']), ('p', 'agent:new', process.pid, 'serving'))
                self.assertEqual(health['owned_launches'], [])
                Path(spec['drain_file']).write_text('drain', encoding='utf-8')
                self.assertEqual(process.wait(timeout=7), 0)
                stopped = json.loads(Path(spec['health_file']).read_text(encoding='utf-8'))
                self.assertEqual(stopped['state'], 'stopped')
                self.assertEqual(stopped['owned_launches'], [])
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
