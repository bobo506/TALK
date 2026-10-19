"""274首次交付独立反例：仅假记录、自有临时根和隔离ASGI。"""
from datetime import datetime, timezone
import json
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'.tmp/runtime-log-view-v1/independent-review274/regression-roots'
OUT.mkdir(parents=True,exist_ok=True)
import server.runtime_diagnostics_query as q
import server.runtime_diagnostics_sources as sources
from server.routes import runtime_diagnostics as routes

NOW=datetime(2026,10,18,20,0,tzinfo=timezone.utc)

def record(message='FAKE OUTSIDE SCOPE CONTENT'):
    return {'schema':'talk-runtime-diagnostics-1','log_id':'rtd-123456abcd-000001','recorded_at':'2026-10-18T19:00:00Z','project_id':'prj_fake','member_id':'agent:fake','event':'fake_error','severity':'error','exception':{'type':'RuntimeError','message':message,'frames':[],'cause_chain':[]},'integrity':{'write_complete':True,'truncated':False,'redacted':False}}

def spec():
    return q.QuerySpec(ref=None,since=datetime(2026,10,18,0,tzinfo=timezone.utc),until=NOW,instance_id=None,launch_id=None,task_id=None,event=None,stage=None,severity=('error','warning'),limit=20)

def make_link(link,target):
    try:os.symlink(target,link,target_is_directory=True)
    except OSError:
        if os.name!='nt':raise
        subprocess.run(['cmd.exe','/c','mklink','/J',str(link),str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=5)

class ReviewProbes(unittest.TestCase):
    def test_cold_default_provider_finishes(self):
        command=[sys.executable,'-X','utf8','-c','import server.runtime_diagnostics_sources as s; s.CONFIG={}; s.get_default_provider(); print("provider_ready")']
        try:
            result=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',timeout=8)
        except subprocess.TimeoutExpired:
            self.fail('cold provider initialization blocked beyond 8 seconds')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('provider_ready',result.stdout)

    def test_nested_directory_swap_never_returns_external_record(self):
        base=Path(tempfile.mkdtemp(prefix='junction-race-',dir=OUT))
        root=base/'controlled';root.mkdir()
        nested=root/'safe';nested.mkdir()
        saved=root/'original-safe'
        outside=base/'outside-controlled-root';outside.mkdir()
        (outside/'events-00001.jsonl').write_text(json.dumps(record(),ensure_ascii=False)+'\n',encoding='utf-8')
        real_scandir=os.scandir
        swapped=False
        def racing_scandir(path):
            nonlocal swapped
            if Path(path)==nested and not swapped:
                self.assertTrue(nested.resolve().is_relative_to(base.resolve()))
                self.assertTrue(saved.absolute().is_relative_to(base.resolve()))
                nested.rename(saved)
                make_link(nested,outside)
                swapped=True
            return real_scandir(path)
        provider=sources.RuntimeDiagnosticsProvider([q.Source('prj_fake','agent:fake',root)],cursor_codec=sources.CursorCodec(clock=lambda:NOW),clock=lambda:NOW)
        try:
            with mock.patch.object(q.os,'scandir',side_effect=racing_scandir):
                try:page=provider.list_logs('prj_fake','agent:fake',spec())
                except q.RuntimeDiagnosticsError as exc:
                    self.assertEqual(exc.status_code,503)
                    return
            self.assertTrue(swapped)
            self.assertEqual(page.records,[],'record read through swapped nested directory escaped configured source')
        finally:
            if swapped:
                # Remove only our link/junction. Never recurse into its target.
                if os.path.islink(nested):nested.unlink()
                else:os.rmdir(nested)

    def test_growing_file_read_stays_inside_byte_budget(self):
        base=Path(tempfile.mkdtemp(prefix='growing-read-',dir=OUT))
        path=base/'events-00001.jsonl'
        path.write_text('{}\n',encoding='utf-8')
        original=q._open_checked
        grown=False
        def append_after_open(file,expected):
            nonlocal grown
            fd,opened=original(file,expected)
            if not grown:
                with path.open('a',encoding='utf-8') as stream:stream.write('X'*(2*1024*1024))
                grown=True
            return fd,opened
        limit=2048
        with mock.patch.object(q,'_open_checked',side_effect=append_after_open):
            outcome=q.scan_source(q.Source('prj_fake','agent:fake',base),limits=q.ScanLimits(max_bytes=limit))
        self.assertTrue(grown)
        self.assertLessEqual(outcome.scanned_bytes,limit,'scanner read beyond its actual byte budget')

    def test_unicode_posix_paths_are_scrubbed_everywhere(self):
        value=record('failed to open /数据/私人/凭据.json')
        value['exception']['frames']=[{'file':'safe.py','line':1,'function':'/目录/函数'}]
        summary=q.project_summary(value,('prj_fake','agent:fake')).model_dump_json()
        detail=q.project_detail(value,('prj_fake','agent:fake')).model_dump_json()
        self.assertNotIn('/数据/私人/凭据.json',summary)
        self.assertNotIn('/数据/私人/凭据.json',detail)
        self.assertNotIn('/目录/函数',detail)

    def test_unreadable_cursor_source_is_unavailable_not_stale(self):
        base=Path(tempfile.mkdtemp(prefix='cursor-io-',dir=OUT))
        rows=[record('fake one'),record('fake two')]
        rows[1]['log_id']='rtd-123456abcd-000002'
        (base/'events-00001.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        provider=sources.RuntimeDiagnosticsProvider([q.Source('prj_fake','agent:fake',base)],cursor_codec=sources.CursorCodec(clock=lambda:NOW),clock=lambda:NOW)
        first=replace(spec(),limit=1)
        page=provider.list_logs('prj_fake','agent:fake',first)
        self.assertIsNotNone(page.page.next_cursor)
        followup=replace(first,cursor=page.page.next_cursor,provided=frozenset({'since','until','severity'}))
        with mock.patch.object(q,'_open_checked',side_effect=PermissionError('FAKE denied')):
            with self.assertRaises(q.RuntimeDiagnosticsError) as caught:provider.list_logs('prj_fake','agent:fake',followup)
        self.assertEqual(caught.exception.status_code,503)

    def test_summary_preview_stays_within_200(self):
        value=q.project_summary(record('x'*300),('prj_fake','agent:fake'))
        self.assertLessEqual(len(value.exception.message_preview),200)

    def test_unreadable_source_does_not_claim_confirmed_change(self):
        base=Path(tempfile.mkdtemp(prefix='unreadable-source-',dir=OUT))
        (base/'events-00001.jsonl').write_text(json.dumps(record())+'\n',encoding='utf-8')
        provider=sources.RuntimeDiagnosticsProvider([q.Source('prj_fake','agent:fake',base)],cursor_codec=sources.CursorCodec(clock=lambda:NOW),clock=lambda:NOW)
        with mock.patch.object(q,'_open_checked',side_effect=PermissionError('FAKE denied')):
            page=provider.list_logs('prj_fake','agent:fake',spec())
        self.assertFalse(page.scan.complete)
        self.assertGreater(page.scan.unavailable_sources,0)
        self.assertNotIn('source_changed',page.warnings)

    def test_integrity_markers_are_not_silently_lost(self):
        value=record();value['integrity']['truncated_fields']=['fake']*101
        with self.assertRaises(q.ProjectionFailure):q.project_detail(value,('prj_fake','agent:fake'))

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from server.models import Member
        app=FastAPI();app.include_router(routes.router)
        app.dependency_overrides[routes.require_log_reader]=lambda:Member(id='human:fake',kind='human',api_key='FAKE_TEST_ONLY')
        app.dependency_overrides[routes.get_session]=lambda:object()
        class FakeProvider:
            def now(self):return NOW
            def list_logs(self,*args):raise AssertionError('invalid query reached provider')
        app.dependency_overrides[routes.get_runtime_diagnostics_provider]=lambda:FakeProvider()
        return TestClient(app,raise_server_exceptions=False)

    def test_huge_integer_query_is_422(self):
        with mock.patch.object(routes,'_require_target'),self._client() as client:
            for field in ('limit','task_id'):
                with self.subTest(field=field):
                    response=client.get('/api/projects/prj_fake/roles/agent:fake/runtime-logs',params={field:'9'*5000})
                    self.assertEqual(response.status_code,422)

    def test_timezone_boundary_query_is_422(self):
        with mock.patch.object(routes,'_require_target'),self._client() as client:
            response=client.get('/api/projects/prj_fake/roles/agent:fake/runtime-logs',params={'since':'0001-01-01T00:00:00+23:00'})
            self.assertEqual(response.status_code,422)

    def test_timezone_overflow_record_is_malformed(self):
        self.assertIsNone(q.parse_recorded_at('0001-01-01T00:00:00+23:00'))
