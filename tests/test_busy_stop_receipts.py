"""Finite busy references cross HTTP client, runtime health and waited CLI."""
import io
import json
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from bridges.stop_blockers import safe_stop_blockers
from scripts import role_service_host as host
from scripts import talk_runtime as runtime
from tests import test_talk_runtime as fixtures
from tests import test_runtime_shutdown as shutdown

BUSY = {'code': 'role_service_busy', 'task_ids': [42], 'task_count': 1, 'instance_busy': True}


class BlockerSanitizationTests(unittest.TestCase):
    def test_accepts_only_fixed_code_bounded_positive_integers_and_bool(self):
        raw = {**BUSY, 'task_ids': [True, -1, 0, 'secret', 2**53, 42, 42, *range(1, 40)],
               'task_count': 'PRIVATE-KEY', 'instance_busy': 'PRIVATE-PATH', 'token': 'PRIVATE-TOKEN'}
        safe = safe_stop_blockers(raw)
        self.assertEqual(safe, {'code': 'role_service_busy', 'task_ids': [42, *range(1, 20)],
                                'task_count': 20, 'instance_busy': False})
        self.assertNotIn('PRIVATE', json.dumps(safe))
        self.assertEqual(safe_stop_blockers(BUSY), BUSY)

    def test_unknown_malformed_empty_and_bad_count_never_echo(self):
        for raw in [None, [], {'code': 'secret'}, {**BUSY, 'task_ids': 'secret'},
                    {**BUSY, 'task_ids': [], 'task_count': 0, 'instance_busy': False}]:
            self.assertIsNone(safe_stop_blockers(raw))
        for bad in (True, -1, 2**53, 'secret', None):
            safe = safe_stop_blockers({**BUSY, 'task_count': bad})
            self.assertEqual(safe['task_count'], 1)

    def test_host_http_error_preserves_safe_references_and_fixed_error(self):
        payload = {'detail': {**BUSY, 'token': 'PRIVATE-KEY', 'text': 'PRIVATE-PATH'}}
        error = urllib.error.HTTPError('http://127.0.0.1:1/fixture', 409, 'fixture', {},
                                       io.BytesIO(json.dumps(payload).encode()))
        client = host.TalkHostClient('http://127.0.0.1:1', 'FIXTURE-ONLY')
        with patch.object(host.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaises(host.HostError) as caught: client.request('POST', '/fixture')
        self.assertEqual(caught.exception.code, 'role_service_busy')
        self.assertEqual(caught.exception.stop_blockers, BUSY)
        self.assertNotIn('PRIVATE', str(caught.exception))

    def test_other_host_http_errors_keep_original_string_code(self):
        error = urllib.error.HTTPError('http://127.0.0.1:1/fixture', 409, 'fixture', {},
                                       io.BytesIO(b'{"detail":"already_stopped"}'))
        with patch.object(host.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaises(host.HostError) as caught:
                host.TalkHostClient('http://127.0.0.1:1', 'FIXTURE-ONLY').request('POST', '/fixture')
        self.assertEqual(caught.exception.code, 'already_stopped')
        self.assertFalse(hasattr(caught.exception, 'stop_blockers'))


class BusyRuntimeTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    advance = fixtures.RuntimeTests.advance
    spec = fixtures.RuntimeTests.spec
    role = fixtures.RuntimeTests.role

    def test_busy_keeps_original_process_and_api_then_retry_clears_references(self):
        self.config['hosts'] = [self.spec()]
        self.runtime.reconcile_hosts([self.role()])
        owned = self.runtime.hosts['agent:one']
        self.client.rows = [self.role(can_stop=True, ownership_held=True)]
        self.runtime.api = fixtures.Process(77)
        error = host.HostError('role_service_busy', 'fixed')
        error.stop_blockers = {**BUSY, 'activation_id': 'PRIVATE-IDENTITY'}
        original = self.client.request
        def request(method, path, *args, **kwargs):
            if method == 'POST': raise error
            return original(method, path, *args, **kwargs)
        with patch.object(self.client, 'request', side_effect=request):
            with self.assertRaises(host.HostError): self.runtime.stop()
        self.assertIs(owned, self.runtime.hosts['agent:one'])
        self.assertIsNone(owned['process'].poll())
        self.assertIsNone(self.runtime.api.poll())
        self.assertFalse(Path(owned['spec']['drain_file']).exists())
        # Same production exception boundary publishes blocked health.
        self.runtime.shutdown_error = error.code
        self.runtime.health('stop_blocked')
        value = json.loads((self.private / 'health.json').read_text(encoding='utf-8'))
        self.assertEqual(value['shutdown']['phase'], 'stopping_roles')
        self.assertEqual(value['shutdown']['blocking_tasks'], BUSY)
        self.assertNotIn('PRIVATE', json.dumps(value['shutdown']))
        self.client.rows = []
        Path(owned['spec']['health_file']).write_text('{"owned_launches":[]}', encoding='utf-8')
        self.runtime.api_control_file = self.private / 'api.stop'
        self.runtime.stop()
        value = json.loads((self.private / 'health.json').read_text(encoding='utf-8'))
        self.assertEqual(value['state'], 'stopped')
        self.assertNotIn('blocking_tasks', value['shutdown'])
        self.assertIsNone(value['shutdown']['error_code'])

    def test_idle_and_other_errors_do_not_publish_stale_or_raw_blockers(self):
        for code in (None, 'runtime_role_stop_timeout', 'PRIVATE-CODE'):
            self.runtime.shutdown_blockers = {**BUSY, 'key': 'PRIVATE-KEY'}
            self.runtime.shutdown_error = code
            self.runtime.health()
            value = json.loads((self.private / 'health.json').read_text(encoding='utf-8'))
            self.assertNotIn('blocking_tasks', value['shutdown'])


class BusyWaitTests(unittest.TestCase):
    setUp = shutdown.StopWaitTests.setUp
    write = shutdown.StopWaitTests.write
    sleep = shutdown.StopWaitTests.sleep
    wait = shutdown.StopWaitTests.wait

    def test_blocked_wait_exposes_only_safe_task_references(self):
        self.value.update(state='stop_blocked', shutdown={'phase': 'stopping_roles',
            'error_code': 'role_service_busy', 'blocking_tasks': {**BUSY, 'key': 'PRIVATE-KEY'}})
        self.write()
        with patch.object(runtime, 'recorded_process_state', return_value='present'):
            result = self.wait()
        self.assertEqual(result['stop_status'], 'blocked')
        self.assertEqual(result['shutdown']['blocking_tasks'], BUSY)
        self.assertNotIn('activation', json.dumps(result))
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_bad_or_unrelated_health_does_not_smuggle_blockers(self):
        for code, refs in [('PRIVATE', BUSY), ('runtime_role_stop_timeout', BUSY),
                           ('role_service_busy', {'code': 'PRIVATE', 'task_ids': [42]})]:
            self.value.update(state='stop_blocked', shutdown={'phase': 'stopping_roles',
                'error_code': code, 'blocking_tasks': refs})
            self.write()
            with patch.object(runtime, 'recorded_process_state', return_value='present'):
                result = self.wait()
            self.assertNotIn('blocking_tasks', result['shutdown'])
            self.assertNotIn('PRIVATE', json.dumps(result))
