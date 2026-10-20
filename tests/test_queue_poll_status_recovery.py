"""真实bridge查询断连后的状态恢复；隔离假客户端，不调用模型/生产API。"""
import asyncio
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridges import cli_bridge
from bridges import runtime_diagnostics as runtime_diag


class QueuePollStatusRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, *, managed=True, query_failure=True, fail_error=False,
                       fail_recovery=False, heartbeat_interval=60, worker=None, log_root=None):
        reports, attempts, clients = [], [], []
        finished = asyncio.Event()
        error_seen = False
        error_failed = False
        recovery_failed = False

        class Client:
            def __init__(self, *args, **kwargs):
                self.calls = 0
                self.closed = False
                clients.append(self)

            async def register(self, *args, **kwargs):
                pass

            def on_message(self, callback):
                return callback

            async def emit(self, payload):
                nonlocal error_seen, error_failed, recovery_failed
                attempts.append(dict(payload))
                if payload['status'] == 'error':
                    error_seen = True
                    if fail_error and not error_failed:
                        error_failed = True
                        raise OSError('private report failure fixture')
                if payload['status'] == 'idle' and error_seen and fail_recovery and not recovery_failed:
                    recovery_failed = True
                    raise OSError('private recovery failure fixture')
                reports.append(dict(payload))

            async def _request_json(self, method, path, *, json_body):
                assert (method, path) == ('PUT', '/api/instances/ins-status-test')
                await self.emit(json_body)

            async def report_instance_status(self, instance_id, **kwargs):
                await self.emit(kwargs)

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if query_failure and self.calls == 1:
                    raise ConnectionError('private query failure fixture')
                if self.calls >= 4:
                    finished.set()
                return []

            async def run(self):
                await asyncio.wait_for(finished.wait(), timeout=1)
                await asyncio.sleep(.035)

            async def close(self):
                self.closed = True

        async def controlled_worker(**kwargs):
            await worker(**kwargs)
            finished.set()
            await asyncio.Event().wait()

        args = cli_bridge.build_parser().parse_args([
            '--key', 'fixture-key', '--command', 'unused-fixture-command',
            '--name', 'status-fixture', '--instance-id', 'ins-status-test',
            '--task-poll-interval', '.005',
            *(['--disable-runtime-logs'] if log_root is None else ['--runtime-log-dir', str(log_root)]),
            *(['--launch-id', 'launch-status-test', '--project-id', 'prj-status-test'] if managed else []),
        ])
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ))
            stack.enter_context(patch('TALK.client.TalkClient', Client))
            stack.enter_context(patch.object(cli_bridge, 'MANAGED_INSTANCE_HEARTBEAT_INTERVAL', heartbeat_interval))
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(output))
            if worker:
                stack.enter_context(patch.object(cli_bridge, 'run_task_queue_worker', controlled_worker))
            await cli_bridge.run_bridge(args)
            count = len(attempts)
            await asyncio.sleep(.015)
            self.assertEqual(len(attempts), count, '退出后不得继续上报旧状态')
        self.assertTrue(clients[0].closed)
        self.assertEqual(reports[-1]['status'], 'offline')
        self.assertNotIn('private report failure fixture', output.getvalue())
        self.assertNotIn('private recovery failure fixture', output.getvalue())
        return reports, attempts

    async def test_managed_real_query_recovery_clears_error_and_heartbeat_stays_idle(self):
        reports, _ = await self.scenario(heartbeat_interval=.005)
        states = [row['status'] for row in reports]
        error = states.index('error')
        self.assertTrue(all(state == 'idle' for state in states[error + 1:-1]), states)
        self.assertIn('idle', states[error + 1:-1])
        for row in reports[error + 1:-1]:
            self.assertIsNone(row['current_task_id'])
            self.assertIsNone(row['last_error'])
            self.assertEqual((row['project_id'], row['launch_id']), ('prj-status-test', 'launch-status-test'))

    async def test_unmanaged_real_query_recovery_keeps_event_only_reporting(self):
        reports, _ = await self.scenario(managed=False)
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'idle', 'offline'])

    async def test_query_error_report_failure_does_not_kill_recovery_without_logs(self):
        reports, attempts = await self.scenario(fail_error=True)
        self.assertIn('error', [row['status'] for row in attempts])
        self.assertEqual([row['status'] for row in reports], ['idle', 'idle', 'offline'])

    async def test_recovery_report_failure_retries_on_next_successful_query(self):
        reports, attempts = await self.scenario(fail_recovery=True)
        self.assertEqual([row['status'] for row in attempts], ['idle', 'error', 'idle', 'idle', 'offline'])
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'idle', 'offline'])

    async def test_successful_idle_polls_do_not_add_status_requests(self):
        reports, _ = await self.scenario(query_failure=False)
        self.assertEqual([row['status'] for row in reports], ['idle', 'offline'])

    async def test_query_failure_does_not_overwrite_busy_task(self):
        async def worker(*, run_lock, report_status, report_query_error, recover_query_error, **kwargs):
            async with run_lock:
                await report_status('busy', current_task_id='42')
                await report_query_error('query disconnected')
                await recover_query_error()
        reports, _ = await self.scenario(worker=worker)
        self.assertEqual([row['status'] for row in reports], ['idle', 'busy', 'offline'])
        self.assertEqual(reports[1]['current_task_id'], '42')

    async def test_query_success_cannot_clear_execution_error_without_task_id(self):
        async def worker(*, report_status, report_query_error, recover_query_error, **kwargs):
            await report_status('error', last_error='execution failed')
            await report_query_error('query disconnected')
            await recover_query_error()
        reports, _ = await self.scenario(worker=worker)
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'offline'])
        self.assertEqual(reports[1]['last_error'], 'execution failed')

    async def test_later_task_status_invalidates_pending_query_recovery(self):
        async def worker(*, report_status, report_query_error, recover_query_error, **kwargs):
            await report_query_error('query disconnected')
            await report_status('busy', current_task_id='42')
            self.assertTrue(await recover_query_error())
        reports, _ = await self.scenario(worker=worker)
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'busy', 'offline'])

    async def test_recovery_waits_for_lock_holder_before_reporting_idle(self):
        async def worker(*, run_lock, report_query_error, recover_query_error, **kwargs):
            await report_query_error('query disconnected')
            async with run_lock:
                self.assertFalse(await recover_query_error())
            self.assertTrue(await recover_query_error())
            self.assertTrue(await recover_query_error())
        reports, _ = await self.scenario(worker=worker)
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'idle', 'offline'])

    async def test_matching_error_text_from_another_report_keeps_its_error(self):
        async def worker(*, report_status, report_query_error, recover_query_error, **kwargs):
            await report_query_error('same error text')
            await report_status('error', last_error='same error text')
            self.assertTrue(await recover_query_error())
        reports, _ = await self.scenario(worker=worker)
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'error', 'offline'])
        self.assertEqual(reports[2]['last_error'], 'same error text')

    async def test_repeated_query_errors_update_then_recover_once(self):
        async def worker(*, report_query_error, recover_query_error, **kwargs):
            await report_query_error('first failure')
            await report_query_error('second failure')
            self.assertTrue(await recover_query_error())
            self.assertTrue(await recover_query_error())
        reports, _ = await self.scenario(worker=worker)
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'error', 'idle', 'offline'])
        self.assertEqual(reports[2]['last_error'], 'second failure')

    async def test_offline_report_invalidates_pending_query_recovery(self):
        async def worker(*, report_status, report_query_error, recover_query_error, **kwargs):
            await report_query_error('query disconnected')
            await report_status('offline')
            self.assertTrue(await recover_query_error())
        reports, _ = await self.scenario(worker=worker)
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'offline', 'offline'])

    async def test_canceled_recovery_releases_lock_and_cannot_revive_offline(self):
        async def worker(*, client, report_status, report_query_error, recover_query_error, **kwargs):
            await report_query_error('query disconnected')
            original = client._request_json
            entered = asyncio.Event()
            async def block(method, path, *, json_body):
                entered.set()
                await asyncio.Event().wait()
            client._request_json = block
            recovery = asyncio.create_task(recover_query_error())
            await asyncio.wait_for(entered.wait(), timeout=1)
            recovery.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await recovery
            client._request_json = original
            await report_status('offline')
            self.assertTrue(await recover_query_error())
        reports, _ = await self.scenario(worker=worker)
        self.assertEqual([row['status'] for row in reports], ['idle', 'error', 'offline', 'offline'])

    async def test_failed_recovery_status_is_not_another_query_failure(self):
        with tempfile.TemporaryDirectory(prefix='queue-status-recovery-') as directory:
            root = Path(directory) / 'runtime'
            await self.scenario(fail_recovery=True, log_root=root)
            records = runtime_diag.query_records(root, limit=200)['records']
            recovered = [row for row in records if row['event'] == 'queue_poll_recovered']
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0]['extra']['queue_poll']['recovered_failures'], 1)
            self.assertEqual(sum(row['event'] == 'queue_worker_exception' for row in records), 1)
            self.assertEqual(sum(row['stage'] == 'queue_poll_status_recovery' for row in records), 1)
