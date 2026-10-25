"""Real runtime loop with synthetic API responses and deterministic wait budgets."""
import json
from pathlib import Path
import tempfile
import unittest
from scripts import talk_runtime as runtime

PATH='/api/projects/{project_id}/role-services/startup'
ROLE_PATH='/api/projects/{project_id}/roles'

def schema(supported):
    paths={ROLE_PATH:{'get':{}}}
    if supported:paths[PATH]={'post':{}}
    return {'openapi':'3.1.0','paths':paths}

class API:
    def __init__(self,document,*,error=None,pending=0):
        self.document=document;self.error=error;self.pending=pending;self.calls=[];self.posts=0
    def request(self,method,path,body=None):
        self.calls.append((method,path))
        if path=='/api/members/me':return {'kind':'human'}
        if path=='/openapi.json':
            if isinstance(self.document,Exception):raise self.document
            return self.document
        if method=='POST':
            self.posts+=1
            if self.error:raise self.error
            return {'activation_id':body['activation_id'],'complete':self.posts>self.pending,'retry_after_seconds':5}
        return []

class StartupCompatibilityTests(unittest.TestCase):
    def run_runtime(self,api):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);key=root/'human.key';key.write_text('synthetic-only')
        now=[0.0];rt=runtime.TalkRuntime({'project_id':'p','project_root':str(root),
            'state_dir':str(root/'state'),'operator_key_file':str(key),'base_url':'http://synthetic.invalid',
            'provision_worker':False,'hosts':[]},client=api,attach_api=True,clock=lambda:now[0])
        observed={};ticks=[0]
        def sleep(seconds):
            ticks[0]+=1
            self.assertLess(ticks[0],300)
            if rt.startup_thread:rt.startup_thread.join(2)
            now[0]+=seconds
        def hosts(roles):
            observed.update(at=now[0],posts=api.posts,state=rt.startup_state)
            rt.stopping=True
        rt.sleep=sleep;rt.reconcile_hosts=hosts;rt.reconcile_deletions=lambda roles:None
        rt._serve()
        health=json.loads((root/'state/runtime/health.json').read_text())
        return rt,observed,health

    def test_verified_old_api_releases_hosts_before_launch_deadline_without_post_or_fake_completion(self):
        api=API(schema(False),error=RuntimeError('HTTP404'))
        rt,seen,health=self.run_runtime(api)
        self.assertLess(seen['at'],120);self.assertEqual(seen['posts'],0)
        self.assertEqual(rt.startup_attempts,0);self.assertEqual(rt.startup_state,'unsupported')
        self.assertEqual(health['startup_state'],'unsupported')
        self.assertEqual(health['startup_error'],'startup_api_unsupported')
        self.assertEqual(api.calls.count(('GET','/openapi.json')),1)

    def test_supported_pending_api_keeps_gate_until_actual_completion(self):
        api=API(schema(True),pending=2)
        rt,seen,_=self.run_runtime(api)
        self.assertEqual(seen['posts'],3);self.assertEqual(seen['state'],'complete')
        self.assertEqual(rt.startup_support,'supported')
        self.assertEqual(api.calls.count(('GET','/openapi.json')),1)

    def test_declared_route_http_errors_do_not_masquerade_as_unsupported(self):
        for status in (404,403,409):
            with self.subTest(status=status):
                api=API(schema(True),error=RuntimeError('HTTP'+str(status)))
                rt,seen,_=self.run_runtime(api)
                self.assertEqual(rt.startup_state,'failed');self.assertEqual(rt.startup_support,'supported')
                self.assertEqual(seen['posts'],8);self.assertGreaterEqual(seen['at'],120)

    def test_unknown_or_malformed_schema_cannot_skip_the_startup_guard(self):
        for document in (RuntimeError('unreadable'),{'paths':{}},{'openapi':'3.1.0','paths':[]},
                         {'openapi':'3.1.0','paths':{}},
                         {'openapi':'3.1.0','paths':{ROLE_PATH:{'get':{}},PATH:{'post':None}}}):
            with self.subTest(document=document):
                api=API(document,error=RuntimeError('HTTP404'))
                rt,seen,_=self.run_runtime(api)
                self.assertIsNone(rt.startup_support);self.assertEqual(rt.startup_state,'failed')
                self.assertEqual(seen['posts'],8)

    def test_openapi_failure_with_successful_new_api_does_not_fake_unsupported(self):
        api=API(RuntimeError('schema-disabled'))
        rt,seen,_=self.run_runtime(api)
        self.assertEqual(rt.startup_state,'complete');self.assertIsNone(rt.startup_support)
        self.assertEqual(seen['posts'],1)
