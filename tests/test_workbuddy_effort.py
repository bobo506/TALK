import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from bridges.workbuddy_acp import probe_effort_options
from server import workbuddy_effort as cache
from server.models import resolve_role_effort

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def answer(self, obj, content='application/json'):
        raw=json.dumps(obj).encode() if content == 'application/json' else ('data: '+json.dumps(obj)+'\n\n').encode()
        self.send_response(200); self.send_header('Content-Type',content); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_DELETE(self):
        self.server.deleted += 1; self.answer({})
    def do_POST(self):
        obj=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path.endswith('/connect'): return self.answer({'connectionId':'secret','sessionToken':'secret'})
        method=obj['method']; params=obj['params']; result={}
        if method=='session/new':
            self.server.count+=1; result={'sessionId':str(self.server.count)}
        elif method=='session/set_config_option':
            self.server.writes.append(params)
            values=['enabled','max','low','high'] if params['value']=='deepseek-v4.1-flash' else ['enabled','high']
            result={'configOptions':[{'id':'model','currentValue':params['value']},{'id':'thought_level','options':[{'value':v} for v in values]}]}
        elif method=='session/prompt': raise AssertionError('unexpected prompt')
        self.answer({'jsonrpc':'2.0','id':obj['id'],'result':result},'text/event-stream')

class ProbeTests(unittest.TestCase):
    def test_models_and_session_isolation(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler); server.count=0; server.writes=[]; server.deleted=0
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            endpoint='http://127.0.0.1:'+str(server.server_port)
            self.assertEqual(probe_effort_options('deepseek-v4.1-flash',endpoint=endpoint),['low','high','max'])
            self.assertEqual(probe_effort_options('hy4free',endpoint=endpoint),['high'])
            self.assertEqual([x['sessionId'] for x in server.writes],['2','4'])
            self.assertTrue(all(x['configId']=='model' for x in server.writes)); self.assertEqual(server.deleted,2)
        finally: server.shutdown(); server.server_close(); thread.join()
    def setUp(self): cache._cache.clear()
    def test_cache_success_and_failure_expiry(self):
        with patch.object(cache.time,'monotonic') as clock, patch.object(cache,'probe_effort_options',side_effect=[['high'],['low'],RuntimeError(),['max']]) as probe:
            clock.return_value=0; self.assertEqual(cache.options_for_model('workbuddy-acp:a'),['high'])
            clock.return_value=599; self.assertEqual(cache.options_for_model('workbuddy-acp:a'),['high'])
            clock.return_value=600; self.assertEqual(cache.options_for_model('workbuddy-acp:a'),['low'])
            self.assertEqual(cache.options_for_model('workbuddy-acp:b'),[])
            clock.return_value=659; self.assertEqual(cache.options_for_model('workbuddy-acp:b'),[])
            clock.return_value=660; self.assertEqual(cache.options_for_model('workbuddy-acp:b'),['max']); self.assertEqual(probe.call_count,4)
    def test_describe_model_cached_errors_and_expiry(self):
        class ProbeError(Exception):
            code = 'workbuddy_acp_runtime_unavailable'
        model = 'workbuddy-acp:a'
        with patch.object(cache.time, 'monotonic') as clock, patch.object(cache, 'probe_effort_options', side_effect=[ProbeError(), ['high'], RuntimeError()]) as probe:
            clock.return_value = 10
            self.assertEqual(cache.describe_model(model), ([], None))
            self.assertEqual(probe.call_count, 0)
            self.assertEqual(cache.options_for_model(model), [])
            self.assertEqual(cache.describe_model(model), ([], 'workbuddy_acp_runtime_unavailable'))
            clock.return_value = 70
            self.assertEqual(cache.describe_model(model), ([], None))
            self.assertEqual(cache.options_for_model(model), ['high'])
            self.assertEqual(cache.describe_model(model), (['high'], None))
            clock.return_value = 670
            self.assertEqual(cache.options_for_model(model), [])
            self.assertEqual(cache.describe_model(model), ([], 'workbuddy_acp_probe_failed'))
            self.assertEqual(cache.describe_model('not-acp'), ([], None))

    def test_different_models_probe_concurrently(self):
        started = threading.Event()
        release = threading.Event()
        results = {}

        def probe(model):
            if model == 'a':
                started.set()
                if not release.wait(5):
                    raise RuntimeError('slow probe timed out')
            return [model]

        def call(model):
            results[model] = cache.options_for_model('workbuddy-acp:' + model)

        with patch.object(cache, 'probe_effort_options', side_effect=probe):
            slow = threading.Thread(target=call, args=('a',))
            slow.start()
            try:
                self.assertTrue(started.wait(2))
                fast = threading.Thread(target=call, args=('b',))
                before = time.monotonic()
                fast.start()
                fast.join(1)
                self.assertFalse(fast.is_alive(), 'model B blocked behind model A')
                self.assertLess(time.monotonic() - before, 1)
                self.assertEqual(results['b'], ['b'])
            finally:
                release.set()
                slow.join(5)
                if 'fast' in locals():
                    fast.join(5)
            self.assertFalse(slow.is_alive())
            self.assertEqual(results['a'], ['a'])

    def test_same_model_single_flight(self):
        started = threading.Event()
        release = threading.Event()
        second_started = threading.Event()
        results = []

        def probe(model):
            started.set()
            if not release.wait(5):
                raise RuntimeError('probe timed out')
            return ['high']

        def call(second=False):
            if second:
                second_started.set()
            results.append(cache.options_for_model('workbuddy-acp:a'))

        with patch.object(cache, 'probe_effort_options', side_effect=probe) as mock_probe:
            first = threading.Thread(target=call)
            second = threading.Thread(target=call, args=(True,))
            first.start()
            try:
                self.assertTrue(started.wait(2))
                second.start()
                self.assertTrue(second_started.wait(2))
                second.join(0.1)
                self.assertTrue(second.is_alive())
            finally:
                release.set()
                first.join(5)
                if second.ident is not None:
                    second.join(5)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(results, [['high'], ['high']])
            self.assertEqual(mock_probe.call_count, 1)
            self.assertEqual(cache._inflight, {})

    def test_runtime_and_catalog_priority(self):
        with patch.object(cache,'probe_effort_options',return_value=['high']):
            self.assertEqual(cache.runtime_options_for_facts({'runtime':'workbuddy','model_alias':'custom-local:x'}),(None,None))
            self.assertEqual(cache.runtime_options_for_facts({'runtime':'codex','model_alias':'workbuddy-acp:x'}),(None,None))
            options,source=cache.runtime_options_for_facts({'runtime':'workbuddy','model_alias':'workbuddy-acp:x'})
            self.assertEqual((options,source),(['high'],'adapter'))
            self.assertEqual(resolve_role_effort({'supported_efforts':'["low"]'},options)['effort_options'],['low'])
            self.assertEqual(resolve_role_effort({},options)['effort_options'],['high'])

from tests.test_project_role_bindings import BindingApiTestCase
from server.models import ProjectRoleBinding, RunnerModelChoice

class WorkbuddyApiTests(BindingApiTestCase):
    def test_cdp_choices_projection_validation_and_mismatch(self):
        p = 'prj_wb_cdp_effort'
        self.register_project(p); self.sync(p, [{'member_id':'agent:worker'}, {'member_id':'agent:other'}]); self.register_runner(runtime='workbuddy')
        for member, mid, levels in [('agent:worker','hy4free',['high']), ('agent:other','deepseek-v4.1-flash',['low','high','max'])]:
            payload = self.binding_payload(provider_id='managed:workbuddy', connection_ref='native-workbuddy-cdp', model_id=mid, model_alias='workbuddy-cdp:' + mid)
            self.assertEqual(self.put_binding(p, member, payload).status_code, 200)
            with self.session() as session:
                session.add(RunnerModelChoice(choice_id='choice-' + mid, created_by='human:bobo', **{k:payload[k] for k in ('runner_id','model_source','provider_id','connection_ref','model_id','model_alias')}, capabilities=['effort:' + x for x in levels] + ['effort_default:high']))
                session.commit()
        with patch.object(cache, 'probe_effort_options', side_effect=AssertionError('ACP probe used')):
            for member, levels in [('agent:worker',['high']), ('agent:other',['low','high','max'])]:
                binding = self.get_binding(p, member).json()['binding']
                self.assertEqual((binding['effort_options'],binding['default_effort'],binding['effective_effort'],binding['effort_source']), (levels,'high','high','adapter'))
                self.assertEqual(self.agent_by_id(p,member)['binding']['effort_options'],levels)
            self.assertEqual(self.put_effort_override(p,'agent:worker','low').status_code,422)
            self.assertEqual(self.set_effort(p,'agent:worker','low').status_code,422)
            for value in ['low','high','max']:
                response = self.put_effort_override(p,'agent:other',value)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['binding']['effective_effort'], value)
            self.assertEqual(self.put_effort_override(p,'agent:other',None).json()['binding']['effective_effort'],'high')
            with self.session() as session:
                facts = {'runtime':'workbuddy','runner_id':'runner:dsh-cli','model_source':'builtin','provider_id':'managed:workbuddy','connection_ref':'native-workbuddy-cdp','model_id':'hy4free','model_alias':'workbuddy-cdp:hy4free'}
                for dimension in ('runner_id','model_source','provider_id','connection_ref','model_id','model_alias'):
                    altered = dict(facts); altered[dimension] += '-wrong'
                    self.assertEqual(cache.cdp_effort_for_facts(session, altered), ([],None,'workbuddy_cdp_choice_not_found'))
    def test_binding_failure_is_projected_and_catalog_takes_priority(self):
        p = 'prj_wb_failure'
        self.register_project(p); self.sync(p, [{'member_id': 'agent:worker'}]); self.register_runner(runtime='workbuddy')
        self.put_binding(p, 'agent:worker', self.binding_payload(model_alias='workbuddy-acp:hy4free'))
        class ProbeError(Exception):
            code = 'workbuddy_acp_runtime_unavailable'
        cache._cache.clear()
        with patch.object(cache, 'probe_effort_options', side_effect=ProbeError()) as probe:
            with self.make_client() as client:
                path = f'/api/projects/{p}/agents/agent:worker/binding'
                response = client.get(path, headers={'X-API-Key': 'bobo-key'}).json()['binding']
                self.assertIsNone(response['effort_error'])
                self.assertEqual(probe.call_count, 0)
                response = client.get(path + '?refresh_effort=true', headers={'X-API-Key': 'bobo-key'}).json()['binding']
                self.assertEqual((response['effort_options'], response['effort_error']), ([], 'workbuddy_acp_runtime_unavailable'))
                self.assertEqual(probe.call_count, 1)
            self.assertEqual(self.agent_by_id(p, 'agent:worker')['binding']['effort_error'], 'workbuddy_acp_runtime_unavailable')
            with self.session() as session:
                row = session.get(ProjectRoleBinding, (p, 'agent:worker')); row.supported_efforts = '["low"]'; session.add(row); session.commit()
            binding = self.get_binding(p, 'agent:worker').json()['binding']
            self.assertEqual(binding['effort_options'], ['low'])
            self.assertIsNone(binding['effort_error'])
        cache._cache.clear()

    def test_binding_views_and_validation(self):
        p='prj_wb_effort'
        self.register_project(p); self.sync(p,[{'member_id':'agent:worker'}]); self.register_runner(runtime='workbuddy')
        self.put_binding(p,'agent:worker',self.binding_payload(model_alias='workbuddy-acp:hy4free'))
        with patch.object(cache,'probe_effort_options',return_value=['high']):
            cache._cache.clear()
            with self.make_client() as client:
                binding=client.get(f'/api/projects/{p}/agents/agent:worker/binding?refresh_effort=true', headers={'X-API-Key':'bobo-key'}).json()['binding']
            self.assertEqual((binding['effort_options'],binding['effort_source']),(['high'],'adapter'))
            self.assertEqual(self.agent_by_id(p,'agent:worker')['binding']['effort_options'],['high'])
            with self.make_client() as client:
                roles=client.get(f'/api/projects/{p}/roles',headers={'X-API-Key':'bobo-key'}).json()
            self.assertEqual(next(x for x in roles if x['member_id']=='agent:worker')['model']['model_alias'],'workbuddy-acp:hy4free')
            self.assertEqual(self.put_effort_override(p,'agent:worker','low').status_code,422)
            self.assertEqual(self.put_effort_override(p,'agent:worker','high').status_code,200)
            self.assertEqual(self.put_effort_override(p,'agent:worker',None).status_code,200)
            with self.session() as session:
                row=session.get(ProjectRoleBinding,(p,'agent:worker')); row.supported_efforts='["low"]'; session.add(row); session.commit()
            self.assertEqual(self.get_binding(p,'agent:worker').json()['binding']['effort_source'],'catalog')
            self.assertEqual(self.put_effort_override(p,'agent:worker','high').status_code,422)
        cache._cache.clear()
        with self.session() as session:
            row=session.get(ProjectRoleBinding,(p,'agent:worker')); row.supported_efforts=None; session.add(row); session.commit()
        with patch.object(cache,'probe_effort_options',side_effect=RuntimeError()):
            response=self.put_effort_override(p,'agent:worker','high')
            self.assertEqual((response.status_code,response.json()['detail']),(409,'effort_capability_unknown'))
            self.assertEqual(self.put_effort_override(p,'agent:worker','turbo').status_code,422)
