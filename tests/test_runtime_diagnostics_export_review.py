"""276 独立复核的取消与真实导出边界回归（全部使用假记录/客户端）。"""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_runtime_diagnostics_export as f
from tests import test_runtime_diagnostics_timeline as stages
from bridges import cli_bridge
from server import runtime_diagnostics_export as export


class _Writer(stages._FakeWriter):
    def sanitize_public_text(self, text, **kwargs):
        return str(text)


class ReviewTests(unittest.TestCase):
    def test_last_projection_crossing_deadline_is_incomplete(self):
        clock = [0.0]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            f._write_records(root, [f._point('rtd-review-00000001', recorded_at='2026-10-18T10:00:00Z')])
            original = export._project_event
            def slow_projection(*args):
                result = original(*args)
                clock[0] = 11.0
                return result
            with mock.patch.object(export.time, 'monotonic', side_effect=lambda: clock[0]), mock.patch.object(export, '_project_event', side_effect=slow_projection):
                body = export.build_export(f.Source(f.PROJECT, f.MEMBER, root), project_id=f.PROJECT, member_id=f.MEMBER, since=f.parse_export_time(f.SINCE), until=f.parse_export_time(f.UNTIL))
            meta, _ = f._parse_ndjson(body)
            self.assertFalse(meta['complete'])
            self.assertTrue(meta['truncated'])
            self.assertIn('time_limit', meta['reasons'])

    def test_terminal_failure_cancellation_preserves_exception_and_finishes_stage(self):
        for method, stage in [('accept_task', 'task_accept'), ('claim_task', 'task_claim'), ('send_text', 'task_result_send'), ('complete_task', 'task_complete')]:
            with self.subTest(method=method):
                client = stages._BridgeClient()
                writer = _Writer()
                cancellation = asyncio.CancelledError('review cancellation')
                async def cancel(*args, **kwargs):
                    raise cancellation
                setattr(client, method, cancel)
                with self.assertRaises(asyncio.CancelledError) as raised:
                    asyncio.run(cli_bridge._fail_task_after_preflight_limit({'id':276, 'created_by':'human:test'}, client=client, instance_id='ins_review', attempts=3, error=cli_bridge.TaskPreflightError('invalid preflight'), lease_seconds=30, diagnostics=writer))
                self.assertIs(raised.exception, cancellation)
                statuses = [r['extra']['transition']['status'] for r in writer.records if r['stage'] == stage]
                self.assertEqual(statuses, ['started', 'canceled'])

    def test_terminal_accept_network_failure_finishes_stage(self):
        client = stages._BridgeClient()
        writer = _Writer()
        failure = OSError('fake network failure')
        async def fail(*args, **kwargs):
            raise failure
        client.accept_task = fail
        with self.assertRaises(OSError) as raised:
            asyncio.run(cli_bridge._fail_task_after_preflight_limit({'id':276}, client=client, instance_id='ins_review', attempts=3, error=cli_bridge.TaskPreflightError('invalid'), lease_seconds=30, diagnostics=writer))
        self.assertIs(raised.exception, failure)
        self.assertEqual([r['extra']['transition']['status'] for r in writer.records], ['started', 'failed'])

    def test_actual_ten_thousand_record_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            f._write_records(root, [f._point(f'rtd-review-{i:010d}', recorded_at='2026-10-18T10:00:00Z') for i in range(10001)])
            body = export.build_export(f.Source(f.PROJECT, f.MEMBER, root), project_id=f.PROJECT, member_id=f.MEMBER, since=f.parse_export_time(f.SINCE), until=f.parse_export_time(f.UNTIL), limits=f.ScanLimits(max_seconds=60))
            meta, events = f._parse_ndjson(body)
            self.assertEqual(len(events), 10000)
            self.assertEqual(events[0]['log_id'], 'rtd-review-0000000000')
            self.assertEqual(events[-1]['log_id'], 'rtd-review-0000009999')
            self.assertIn('record_limit', meta['reasons'])
            self.assertFalse(meta['complete'])

    def test_actual_sixteen_mib_cap_preserves_all_frames_of_included_events(self):
        exception = f._exception('fake failure')
        exception['frames'] = [{'file':'frame.py', 'line':i, 'function':'function_' + 'x'*400} for i in range(300)]
        exception['frames_total'] = 300
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            f._write_records(root, [f._point(f'rtd-frames-{i:010d}', recorded_at='2026-10-18T10:00:00Z', exception=exception) for i in range(160)])
            body = export.build_export(f.Source(f.PROJECT, f.MEMBER, root), project_id=f.PROJECT, member_id=f.MEMBER, since=f.parse_export_time(f.SINCE), until=f.parse_export_time(f.UNTIL), limits=f.ScanLimits(max_seconds=60))
            meta, events = f._parse_ndjson(body)
            self.assertLessEqual(len(body), 16*1024*1024)
            self.assertTrue(0 < len(events) < 160)
            self.assertIn('byte_limit', meta['reasons'])
            self.assertFalse(meta['complete'])
            self.assertTrue(all(len(e['exception']['frames']) == 300 for e in events))
