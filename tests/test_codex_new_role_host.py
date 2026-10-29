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
        self.assertEqual(argv[argv.index('--task-profile') + 1], 'review')
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

    def test_task_profile_requires_explicit_per_member_tools_setting(self):
        self.config['codex']['task_profiles'] = {'agent:new': 'tools'}
        spec = host.host_spec(self.config, self.role)
        argv = spec['argv']; self.assertEqual(argv[argv.index('--task-profile') + 1], 'tools')
        other = deepcopy(self.role); other['member_id'] = 'agent:other'
        argv = host.host_spec(self.config, other)['argv']
        self.assertEqual(argv[argv.index('--task-profile') + 1], 'review')
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
                with patch.object(manager, '_configuration', return_value=config), \
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

    def test_claim_scope_and_drain_keep_only_own_stop_and_owned_handles(self):
        manager = self.manager()
        manager._handles['owned'] = object()
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

    def test_health_failure_does_not_block_owned_stop_or_drop_handles(self):
        manager = self.manager()
        manager._handles['owned'] = object()
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
        with patch.object(host.rsh, 'load_operator_key', return_value='synthetic-human-key'), \
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
                Path(spec['drain_file']).write_text('drain', encoding='utf-8')
                self.assertEqual(process.wait(timeout=7), 0)
                self.assertEqual(json.loads(Path(spec['health_file']).read_text(encoding='utf-8'))['state'], 'stopped')
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
