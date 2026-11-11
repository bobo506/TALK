"""Managed bridge startup retry tests without a live server or model."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from bridges.cli_bridge import _retry_managed_startup_connect, build_parser, run_bridge


class StartupReloadTests(unittest.IsolatedAsyncioTestCase):
    def make_args(self, managed=True):
        argv = ['--key', 'test-key', '--command', 'test-command', '--instance-id', 'instance-1',
                '--disable-runtime-logs', '--disable-task-queue']
        if managed:
            argv += ['--launch-id', 'launch-1', '--project-id', 'project-1']
        return build_parser().parse_args(argv)

    async def run_with(self, client, *, managed=True):
        with patch.dict(os.environ, {'TALK_ROLE_SERVICE_CONTROL_FILE': ''}), \
             patch('TALK.client.TalkClient', return_value=client), \
             patch('bridges.cli_bridge.asyncio.sleep', new_callable=AsyncMock) as sleep, \
             patch('bridges.cli_bridge.run_until_managed_stop', new_callable=AsyncMock,
                   return_value='transport_closed') as loop:
            try:
                await run_bridge(self.make_args(managed))
            finally:
                self.sleep_calls = sleep.call_count
                self.loop_calls = loop.await_count

    def make_client(self, status_effect=None, register_effect=None):
        client = Mock()
        client.timeout = 10
        client.register = AsyncMock(side_effect=register_effect)
        client._request_json = AsyncMock(side_effect=status_effect)
        client.report_instance_status = AsyncMock(side_effect=status_effect)
        client.close = AsyncMock()
        client.on_message = lambda callback: callback
        return client

    async def test_first_put_recovers_after_one_and_three_refusals(self):
        for failures in (1, 3):
            with self.subTest(failures=failures):
                accepted = {}
                calls = []
                async def put(method, path, *, json_body):
                    calls.append((method, path, dict(json_body)))
                    if len(calls) <= failures:
                        self.assertEqual(self.loop_calls if hasattr(self, 'loop_calls') else 0, 0)
                        raise httpx.ConnectError('offline')
                    accepted[path] = dict(json_body)
                self.loop_calls = 0
                client = self.make_client(put)
                await self.run_with(client)
                self.assertEqual(self.loop_calls, 1)
                self.assertEqual(client.register.await_count, 1)
                self.assertEqual(len(calls), failures + 2)  # includes normal offline report
                self.assertTrue(all(call == calls[0] for call in calls[:failures + 1]))
                self.assertEqual(list(accepted), ['/api/instances/instance-1'])
                self.assertEqual(calls[failures][2]['status'], 'idle')
                self.assertEqual(calls[-1][2]['status'], 'offline')

    async def test_continuous_failure_exits_without_starting_loop(self):
        client = self.make_client(httpx.ConnectError('offline'))
        with self.assertRaises(httpx.ConnectError):
            await self.run_with(client)
        self.assertEqual(client._request_json.await_count, 8)
        self.assertEqual(self.sleep_calls, 7)
        self.assertEqual(self.loop_calls, 0)

    async def test_business_error_and_read_timeout_are_not_retried(self):
        request = httpx.Request('PUT', 'http://localhost/api/instances/i')
        for error in (httpx.HTTPStatusError('bad request', request=request,
                                           response=httpx.Response(400, request=request)),
                      httpx.ReadTimeout('ambiguous')):
            with self.subTest(error=type(error).__name__):
                client = self.make_client(error)
                with self.assertRaises(type(error)):
                    await self.run_with(client)
                self.assertEqual(client._request_json.await_count, 1)
                self.assertEqual(self.sleep_calls, 0)
                self.assertEqual(self.loop_calls, 0)

    async def test_required_member_registration_retries_connection_only(self):
        for error in (httpx.ConnectTimeout('offline'), ConnectionResetError('offline')):
            with self.subTest(error=type(error).__name__):
                client = self.make_client(register_effect=[error, None])
                await self.run_with(client)
                self.assertEqual(client.register.await_count, 2)
                self.assertEqual(self.loop_calls, 1)

    async def test_stalled_request_cannot_exceed_shared_deadline(self):
        async def stalled():
            await asyncio.Event().wait()
        with self.assertRaises(TimeoutError):
            await _retry_managed_startup_connect(stalled, asyncio.get_running_loop().time() + 0.05)

    async def test_unmanaged_startup_does_not_retry(self):
        client = self.make_client(httpx.ConnectError('offline'))
        with self.assertRaises(httpx.ConnectError):
            await self.run_with(client, managed=False)
        self.assertEqual(client.report_instance_status.await_count, 1)
        self.assertEqual(self.sleep_calls, 0)
        self.assertEqual(self.loop_calls, 0)


if __name__ == '__main__':
    unittest.main()
