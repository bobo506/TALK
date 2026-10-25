"""退出阶段与实际CLI等待：仅合成配置/进程，不访问生产服务或模型。"""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import talk_runtime as runtime
from tests import test_talk_runtime as fixtures


class ShutdownProgressTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    advance = fixtures.RuntimeTests.advance
    spec = fixtures.RuntimeTests.spec
    role = fixtures.RuntimeTests.role

    def health(self):
        return json.loads((self.private / 'health.json').read_text(encoding='utf-8'))

    def test_owned_hosts_are_stopped_before_owned_api_and_health_finishes(self):
        spec = self.spec()
        self.config['hosts'] = [spec]
        self.runtime.reconcile_hosts([self.role()])
        self.client.rows = [self.role(can_stop=True, ownership_held=True)]
        Path(spec['health_file']).write_text('{"owned_launches":[]}', encoding='utf-8')
        self.runtime.api = fixtures.Process(77)
        self.runtime.api_control_file = self.private / 'api.stop'
        phases = []
        original = self.runtime.health
        def capture(state='running'):
            phases.append((self.runtime.shutdown_phase, state))
            original(state)
        with patch.object(self.runtime, 'health', side_effect=capture):
            self.runtime.stop()
        final = self.health()
        self.assertEqual(final['state'], 'stopped')
        self.assertEqual(final['shutdown']['phase'], 'complete')
        self.assertEqual(final['shutdown']['pending_members'], [])
        self.assertTrue(final['shutdown']['completed_at'])
        self.assertEqual(final['hosts']['agent:one']['state'], 'stopped')
        self.assertLess(phases.index(('draining_hosts', 'stopping')), phases.index(('stopping_api', 'stopping')))
        self.assertEqual(self.runtime.api.poll(), 0)

    def test_role_block_keeps_original_handles_and_publishes_waiting_members(self):
        self.config['hosts'] = [self.spec()]
        self.runtime.reconcile_hosts([self.role()])
        owned = self.runtime.hosts['agent:one']
        self.client.rows = [self.role(can_stop=False, ownership_held=True)]
        self.runtime.api = fixtures.Process(77)
        with self.assertRaisesRegex(runtime.RuntimeErrorCode, 'runtime_role_stop_timeout'):
            self.runtime.stop()
        self.assertIs(self.runtime.hosts['agent:one'], owned)
        self.assertIsNone(owned['process'].poll())
        self.assertIsNone(self.runtime.api.poll())
        self.assertEqual(self.health()['shutdown']['phase'], 'stopping_roles')
        self.assertEqual(self.health()['shutdown']['pending_members'], ['agent:one'])

    def test_host_timeout_keeps_marker_and_api_with_live_progress(self):
        spec = self.spec()
        self.config['hosts'] = [spec]
        self.runtime.reconcile_hosts([self.role()])
        self.client.rows = [self.role(ownership_held=False)]
        Path(spec['health_file']).write_text('{"owned_launches":[]}', encoding='utf-8')
        process = self.runtime.hosts['agent:one']['process']
        def timeout_wait(timeout):
            self.advance(timeout)
            raise subprocess.TimeoutExpired('synthetic', timeout)
        process.wait = timeout_wait
        self.runtime.api = fixtures.Process(77)
        with self.assertRaisesRegex(runtime.RuntimeErrorCode, 'runtime_host_stop_timeout'):
            self.runtime.stop()
        self.assertGreaterEqual(self.now, 25)
        self.assertEqual(self.health()['shutdown']['phase'], 'draining_hosts')
        self.assertIsNone(self.runtime.api.poll())
        self.assertTrue(Path(spec['drain_file']).exists())
        process.returncode = 0
        self.runtime.api_control_file = self.private / 'api.stop'
        self.runtime.stop()
        self.assertFalse(Path(spec['drain_file']).exists())
        self.assertEqual(self.health()['hosts']['agent:one']['state'], 'stopped')

    def test_worker_timeout_reports_its_phase_without_touching_roles(self):
        owner = self
        class Thread:
            def is_alive(self): return True
            def join(self, timeout): owner.advance(timeout)
        self.runtime.worker_thread = Thread()
        with self.assertRaisesRegex(runtime.RuntimeErrorCode, 'runtime_worker_stop_timeout'):
            self.runtime.stop()
        self.assertEqual(self.health()['shutdown']['phase'], 'waiting_worker')
        self.assertFalse(any(c[0] == 'POST' for c in self.client.calls))

    def test_api_timeout_keeps_original_process_and_never_reports_complete(self):
        self.runtime.api = fixtures.Process(77)
        self.runtime.api_control_file = self.private / 'api.stop'
        with patch.object(self.runtime.api, 'wait', side_effect=subprocess.TimeoutExpired('fixture-api', 30)):
            with self.assertRaisesRegex(runtime.RuntimeErrorCode, 'runtime_api_stop_timeout'):
                self.runtime.stop()
        self.assertEqual(self.health()['shutdown']['phase'], 'stopping_api')
        self.assertIsNone(self.health()['shutdown']['completed_at'])
        self.assertIsNone(self.runtime.api.poll())

    def test_shutdown_loop_retains_blocked_reason_then_recovers_without_abandoning(self):
        (self.root / 'human.key').write_text('fixture-only', encoding='utf-8')
        self.runtime.attach_api = True
        self.config['provision_worker'] = False
        self.runtime.stopping = True
        original = self.runtime.stop
        seen = []
        def stop():
            if not seen:
                seen.append(True)
                self.runtime.shutdown_phase = 'draining_hosts'
                raise runtime.RuntimeErrorCode('runtime_host_stop_timeout')
            original()
        def advance(seconds):
            seen.append(self.health())
            self.advance(seconds)
        with patch.object(self.runtime, 'stop', side_effect=stop), patch.object(self.runtime, 'sleep', side_effect=advance):
            self.runtime._serve()
        blocked = next(x for x in seen if isinstance(x, dict))
        self.assertEqual(blocked['state'], 'stop_blocked')
        self.assertEqual(blocked['shutdown']['error_code'], 'runtime_host_stop_timeout')
        self.assertEqual(self.health()['shutdown']['phase'], 'complete')
        self.assertIsNone(self.health()['shutdown']['error_code'])
        self.assertIsNone(self.health()['worker_error'])


class StopWaitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='talk-stop-wait-')
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name)
        self.now = 0
        self.value = {'project_id': 'prj_fixture', 'pid': 123, 'started_at': runtime.utcnow(),
                      'seen_at': runtime.utcnow(), 'activation_id': 'fixture-activation', 'state': 'stopping'}
        self.expected = dict(self.value)
        self.write()

    def write(self):
        (self.private / 'health.json').write_text(json.dumps(self.value), encoding='utf-8')

    def sleep(self, seconds): self.now += seconds

    def wait(self, seconds=1):
        return runtime.wait_for_stop(self.private, self.expected, seconds, clock=lambda: self.now, sleeper=self.sleep)

    def test_stopped_health_requires_original_process_exit(self):
        self.value['state'] = 'stopped'; self.write()
        with patch.object(runtime, 'recorded_process_state', side_effect=['present', 'absent']):
            self.assertEqual(self.wait()['stop_status'], 'stopped')
        self.assertGreater(self.now, 0)

    def test_live_or_unknown_process_cannot_be_reported_stopped(self):
        self.value['state'] = 'stopped'; self.write()
        for state in ('present', 'unknown'):
            with self.subTest(state=state), patch.object(runtime, 'recorded_process_state', return_value=state):
                self.assertEqual(self.wait(.05)['stop_status'], 'timeout')

    def test_dead_runtime_without_stopped_health_is_incomplete(self):
        for state in ('absent', 'exited', 'previous_boot', 'pid_reused'):
            with self.subTest(state=state), patch.object(runtime, 'recorded_process_state', return_value=state):
                self.assertEqual(self.wait()['stop_status'], 'incomplete')

    def test_changed_generation_is_never_adopted_or_probed(self):
        for key, value in [('pid', 456), ('started_at', '2026-10-25T01:00:00+00:00'),
                           ('activation_id', 'replacement'), ('project_id', 'other')]:
            with self.subTest(key=key):
                self.value = {**self.expected, key: value}; self.write()
                with patch.object(runtime, 'recorded_process_state') as probe:
                    self.assertEqual(self.wait()['stop_status'], 'generation_changed')
                    probe.assert_not_called()

    def test_legacy_stopped_format_has_unknown_phase_and_can_confirm_exit(self):
        self.value['state'] = 'stopped'; self.write()
        with patch.object(runtime, 'recorded_process_state', return_value='absent'):
            result = self.wait()
        self.assertEqual(result['stop_status'], 'stopped')
        self.assertEqual(result['shutdown'], {'phase': 'unknown', 'error_code': None})

    def test_blocked_result_and_deadline_do_not_write_files_or_reissue_stop(self):
        self.value.update(state='stop_blocked', shutdown={'phase': 'draining_hosts', 'error_code': 'runtime_host_stop_timeout'})
        self.write(); before = (self.private / 'health.json').read_bytes()
        with patch.object(runtime, 'recorded_process_state', return_value='present'):
            result = self.wait()
        self.assertEqual(result['stop_status'], 'blocked')
        self.assertEqual(result['shutdown']['error_code'], 'runtime_host_stop_timeout')
        self.assertEqual((self.private / 'health.json').read_bytes(), before)
        self.assertFalse((self.private / 'stop.request').exists())

    def test_invalid_health_and_untrusted_details_are_not_echoed(self):
        for value in ([], {'pid': True}, {**self.expected, 'started_at': 'invalid'}):
            (self.private / 'health.json').write_text(json.dumps(value), encoding='utf-8')
            self.assertEqual(self.wait()['stop_status'], 'unverified')
        self.value.update(state='stop_blocked', shutdown={'phase': ['invalid'], 'error_code': 'C:/private/secret'})
        self.write()
        with patch.object(runtime, 'recorded_process_state', return_value='present'):
            result = self.wait()
        self.assertNotIn('private', json.dumps(result))
        self.assertEqual(result['shutdown']['phase'], 'unknown')

    def test_invalid_budgets_never_read_health(self):
        with patch.object(Path, 'read_text') as read:
            for seconds in (True, 0, -1, 901, float('inf'), float('nan'), '1'):
                with self.subTest(seconds=seconds), self.assertRaisesRegex(runtime.RuntimeErrorCode, 'wait_budget_invalid'):
                    self.wait(seconds)
            read.assert_not_called()

    def test_cli_invalid_wait_arguments_fail_before_config_access(self):
        for args in (['status', '--wait'], ['stop', '--wait-seconds', '1'], ['stop', '--wait', '--wait-seconds', 'nan'],
                     ['stop', '--wait', '--wait-seconds', '0']):
            with self.subTest(args=args), patch.object(runtime, 'load_config') as load, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit): runtime.main([*args, '--config', 'unused'])
                load.assert_not_called()

    def test_cli_dead_runtime_reports_incomplete_without_writing_another_request(self):
        private = self.private / 'runtime'; private.mkdir()
        (private / 'health.json').write_text(json.dumps(self.value), encoding='utf-8')
        config = {'state_dir': str(self.private), 'project_id': 'prj_fixture'}
        with patch.object(runtime, 'load_config', return_value=config), \
             patch.object(runtime.rsh, 'ensure_private_dir'), \
             patch.object(runtime, 'recorded_process_state', return_value='absent'), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runtime.main(['stop', '--config', 'unused', '--apply', '--wait']), 1)
        self.assertEqual(json.loads(output.getvalue())['stop_status'], 'incomplete')
        self.assertFalse((private / 'stop.request').exists())


class ActualStopCliTests(unittest.TestCase):
    def test_real_cli_timeout_keeps_fixture_alive_and_later_confirms_its_exit(self):
        with tempfile.TemporaryDirectory(prefix='talk-stop-timeout-cli-') as folder:
            root = Path(folder); project = root / 'project'; project.mkdir()
            private = root / 'state/runtime'; private.mkdir(parents=True)
            config = root / 'runtime.json'
            config.write_text(json.dumps({'schema': 'talk-runtime-config-1', 'version': 1, 'project_id': 'prj_fixture',
                'project_root': str(project), 'state_dir': str(root / 'state'), 'key_root': str(root / 'keys'),
                'operator_key_file': str(root / 'unused.key'), 'base_url': 'http://127.0.0.1:1',
                'api_argv': [sys.executable, '{control_file}'], 'hosts': []}), encoding='utf-8')
            release = root / 'release'
            script = '''import json,os,sys,time
from pathlib import Path
from datetime import datetime,timezone
private,release=Path(sys.argv[1]),Path(sys.argv[2])
now=datetime.now(timezone.utc).isoformat()
data={'pid':os.getpid(),'started_at':now,'seen_at':now,'project_id':'prj_fixture',
      'activation_id':'synthetic-timeout','state':'stopping','shutdown':{'phase':'waiting_worker'}}
health=private/'health.json'
health.write_text(json.dumps(data),encoding='utf-8')
while not release.exists():time.sleep(.02)
data['state']='stopped';health.write_text(json.dumps(data),encoding='utf-8')
'''
            flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            child = subprocess.Popen([sys.executable, '-B', '-c', script, str(private), str(release)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
            try:
                deadline = time.monotonic() + 5
                while not (private / 'health.json').exists():
                    if time.monotonic() >= deadline: self.fail('synthetic shutdown fixture did not publish')
                    time.sleep(.02)
                def cli(name):
                    output = root / name
                    with output.open('w', encoding='utf-8') as stream:
                        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'scripts.talk_runtime', 'stop',
                            '--config', str(config), '--apply', '--wait', '--wait-seconds', '.05'], cwd=runtime.ROOT,
                            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, timeout=8, **flags)
                    return result.returncode, json.loads(output.read_text(encoding='utf-8'))
                code, data = cli('timeout.json')
                self.assertEqual(code, 1, data)
                self.assertEqual(data['stop_status'], 'timeout')
                self.assertIsNone(child.poll())
                self.assertFalse((private / 'stop.request').exists())
                release.write_text('normal fixture completion', encoding='utf-8'); child.wait(timeout=5)
                code, data = cli('completed.json')
                self.assertEqual(code, 0, data)
                self.assertEqual(data['stop_status'], 'stopped')
                self.assertFalse((private / 'stop.request').exists())
            finally:
                if child.poll() is None:
                    release.write_text('synthetic cleanup', encoding='utf-8'); child.wait(timeout=5)

    def test_real_attached_runtime_wait_confirms_exit_and_leaves_api_running(self):
        with tempfile.TemporaryDirectory(prefix='talk-shutdown-cli-') as folder:
            root = Path(folder); project = root / 'project'; project.mkdir()
            state = root / 'state'; state.mkdir()
            (project / 'config.toml').write_text('[storage]\ndb_path="fixture.db"\n', encoding='utf-8')
            key = root / 'human.key'; key.write_text('fixture-only', encoding='utf-8')
            with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            config = root / 'runtime.json'
            config.write_text(json.dumps({'schema': 'talk-runtime-config-1', 'version': 1, 'project_id': 'prj_fixture',
                'project_root': str(project), 'state_dir': str(state), 'key_root': str(root / 'keys'),
                'operator_key_file': str(key), 'base_url': f'http://127.0.0.1:{port}', 'provision_worker': False,
                'api_argv': [sys.executable, '-m', 'scripts.talk_api', '--control-file', '{control_file}'], 'hosts': []}), encoding='utf-8')
            env = dict(os.environ, PYTHONPATH=str(runtime.ROOT)); env.pop('TALK_RUNTIME_FIXTURE_CONFIG', None)
            flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            api_marker = root / 'api.stop'
            api = subprocess.Popen([sys.executable, '-B', '-m', 'scripts.talk_api', '--app', 'tests.talk_runtime_fixture:app',
                '--port', str(port), '--control-file', str(api_marker)], cwd=runtime.ROOT, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
            child = None
            health = state / 'runtime/health.json'
            try:
                child = subprocess.Popen([sys.executable, '-B', '-m', 'scripts.talk_runtime', 'serve', '--config', str(config),
                    '--apply', '--attach-api'], cwd=runtime.ROOT, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
                deadline = time.monotonic() + 18
                while time.monotonic() < deadline:
                    try:
                        if json.loads(health.read_text(encoding='utf-8')).get('startup_state') == 'complete': break
                    except (OSError, ValueError): pass
                    self.assertIsNone(child.poll(), 'synthetic runtime exited before readiness')
                    time.sleep(.1)
                else: self.fail('synthetic runtime did not become ready')
                output = root / 'stop.json'
                with output.open('w', encoding='utf-8') as stream:
                    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'scripts.talk_runtime', 'stop',
                        '--config', str(config), '--apply', '--wait', '--wait-seconds', '12'], cwd=runtime.ROOT, env=env,
                        stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, timeout=15, **flags)
                raw = output.read_text(encoding='utf-8')
                self.assertEqual(result.returncode, 0, raw)
                self.assertTrue(raw.strip(), 'synthetic CLI must return a completion receipt')
                data = json.loads(raw)
                self.assertEqual(data['stop_status'], 'stopped')
                self.assertEqual(data['shutdown']['phase'], 'complete')
                self.assertEqual(child.wait(timeout=1), 0)
                self.assertIsNone(api.poll(), 'attached external API must stay running')
            finally:
                if child and child.poll() is None:
                    health.parent.mkdir(parents=True, exist_ok=True)
                    (health.parent / 'stop.request').write_text('synthetic cleanup', encoding='utf-8')
                    try: child.wait(timeout=10)
                    except subprocess.TimeoutExpired: child.terminate(); child.wait(timeout=5)
                if api.poll() is None:
                    api_marker.write_text('synthetic cleanup', encoding='utf-8'); api.wait(timeout=10)


if __name__ == '__main__': unittest.main()
