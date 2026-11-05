import json
import contextlib
import io
import os
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from bridges import workbuddy_acp as acp
from bridges.workbuddy_bridge import build_acp_command, set_command_effort
from bridges.workbuddy_execution_native import resolve_launch, WorkBuddyNativeError
from scripts.workbuddy_acp_models import choice_payload, register

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, code, obj):
        raw=json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_DELETE(self): self.server.deletes += 1; self.reply(500 if self.server.delete_fail else 200,{})
    def do_GET(self):
        if self.path == '/api/members/me': self.reply(200,{'kind':'human'})
        else: self.reply(200,[])
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0')); obj=json.loads(self.rfile.read(n) or b'{}')
        if self.path.startswith('/api/runners/'):
            self.server.payload=obj; return self.reply(200,{'choice_id':'choice-1'})
        if self.path.endswith('/connect'):
            if self.server.bad_auth: return self.reply(401,{})
            return self.reply(200,{'connectionId':'PRIVATE_CONNECTION','sessionToken':'PRIVATE_TOKEN'})
        method=obj.get('method'); params=obj.get('params',{}); ident=obj.get('id')
        if not method:
            self.server.replies.append(obj); return self.reply(200,{})
        if self.server.slow: time.sleep(.2)
        result={}; events=[]
        if method=='session/new':
            self.server.new_count+=1
            sid='active' if self.server.new_count % 2 else ('active' if self.server.same else 'talk')
            result={'sessionId':sid,'models':{'availableModels':[{'modelId':'m','name':'Model','_meta':{'credits':0.1}},{'modelId':'custom-local:x'}]}}
            events.append({'method':'session/update','params':{'sessionId':'active','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'PRIVATE_DESKTOP'}}}})
        elif method=='session/set_config_option':
            self.server.writes.append((method,params['sessionId']))
            result={'configOptions':[{'id':params['configId'],'currentValue':'wrong' if self.server.bad_config in (True, params['configId']) else params['value']}]}
        elif method=='session/prompt':
            self.server.prompt_text=params['prompt'][0]['text']
            index = len([x for x in self.server.writes if x[0] == 'session/prompt'])
            script = self.server.script[index] if index < len(self.server.script) else {}
            if self.server.requests:
                events.extend([{'jsonrpc':'2.0','id':901,'method':'session/request_permission','params':{}}, {'jsonrpc':'2.0','id':902,'method':'unknown/request','params':{}}])
            self.server.writes.append((method,params['sessionId']))
            events.extend([{'method':'session/update','params':{'sessionId':'active','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'PRIVATE_DESKTOP'}}}}, {'method':'session/update','params':{'sessionId':'talk','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':script.get('output', self.server.output)}}}}, {'method':'session/update','params':{'sessionId':'talk','update':{'sessionUpdate':'usage_update','_meta':{'usage':{'credits':0.1}}}}}]); result={'stopReason':script.get('stopReason','end_turn')}
        if method == 'session/prompt' and script.get('drip_interval'):
            event = {'method':'session/update','params':{'sessionId':'talk','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'x'}}}}
            chunk = ('data: ' + json.dumps(event) + '\n\n').encode()
            final = ('data: ' + json.dumps({'jsonrpc':'2.0','id':ident,'result':result}) + '\n\n').encode()
            count = script.get('drip_count', 25)
            fragmented = script.get('fragmented', False)
            if fragmented:
                chunk = b'x'
                final = b'\n\n' + final
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Content-Length',str(len(chunk)*count+len(final)+(1 if fragmented else 0))); self.end_headers()
            try:
                if fragmented: self.wfile.write(b':')
                for _ in range(count):
                    self.wfile.write(chunk); self.wfile.flush(); time.sleep(script['drip_interval'])
                self.wfile.write(final)
            except OSError: pass
            return
        events.append({'jsonrpc':'2.0','id':ident,'result':result})
        raw=(('data: bad-json\n\n' if self.server.bad_sse else ''.join('data: '+json.dumps(event)+'\n\n' for event in events))).encode()
        self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Content-Length',str(len(raw))); self.end_headers()
        try: self.wfile.write(raw)
        except OSError: pass

class Tests(unittest.TestCase):
    def setUp(self):
        self.s=ThreadingHTTPServer(('127.0.0.1',0),Handler); self.s.new_count=0; self.s.same=False; self.s.bad_config=False; self.s.bad_auth=False; self.s.bad_sse=False; self.s.slow=False; self.s.writes=[]; self.s.output="OK"; self.s.delete_fail=False; self.s.deletes=0; self.s.requests=False; self.s.replies=[]
        self.s.script=[]
        self.thread=threading.Thread(target=self.s.serve_forever,daemon=True); self.thread.start(); self.endpoint='http://127.0.0.1:'+str(self.s.server_port)
    def tearDown(self): self.s.shutdown(); self.s.server_close(); self.thread.join()
    def prompt(self, **kwargs): return acp.prompt_once('m','hello',mode='chat',project_root=Path.cwd(),endpoint=self.endpoint,**kwargs)
    def test_isolation(self):
        result=self.prompt(); self.assertEqual(result['text'],'OK'); self.assertEqual(result['usage'],{'credits':.1}); self.assertEqual(result['stopReason'],'end_turn'); self.assertEqual(self.s.writes,[('session/set_config_option','talk'),('session/set_config_option','talk'),('session/prompt','talk')])
    def test_hard_deadline_first_drip(self):
        self.s.script = [{'drip_interval': .2, 'drip_count': 25}]
        start = time.monotonic()
        with self.assertRaises(acp.AcpError) as cm:
            self.prompt(timeout=1.2)
        elapsed = time.monotonic() - start
        print(f'T1 elapsed={elapsed:.3f}s', file=sys.stderr)
        self.assertEqual(cm.exception.code, 'workbuddy_acp_timeout')
        self.assertLessEqual(elapsed, 1.7)

    def test_hard_deadline_fragmented_sse_line(self):
        # A byte drip keeps the HTTP read alive while iter_lines yields nothing.
        self.s.script = [{'drip_interval': .2, 'drip_count': 25, 'fragmented': True}]
        start = time.monotonic()
        with self.assertRaises(acp.AcpError) as cm:
            self.prompt(timeout=1.2)
        self.assertEqual(cm.exception.code, 'workbuddy_acp_timeout')
        self.assertLessEqual(time.monotonic() - start, 1.7)

    def test_hard_deadline_repair_drip(self, fragmented=False):
        from bridges.cli_bridge import CliRunResult, normalize_task_delivery
        from scripts.workbuddy_acp_prompt import has_valid_delivery
        self.s.script = [{'output':'bad'}, {'drip_interval': .2, 'drip_count': 25, 'fragmented': fragmented}]
        stderr = io.StringIO()
        start = time.monotonic()
        # Exercise the same branch with a short budget; production reserve remains 60s.
        with patch.object(acp, '_REPAIR_MIN_SECONDS', 0), contextlib.redirect_stderr(stderr):
            result = self.prompt(timeout=2.2, repair_validator=lambda output: has_valid_delivery(output, 448), repair_prompt='repair')
        elapsed = time.monotonic() - start
        print(f'T2 elapsed={elapsed:.3f}s', file=sys.stderr)
        self.assertLessEqual(elapsed, 2.7)
        self.assertEqual(result['text'], 'bad')
        self.assertIn('repair=timeout', stderr.getvalue())
        self.assertEqual([sid for method,sid in self.s.writes if method=='session/prompt'], ['talk', 'talk'])
        normalized = normalize_task_delivery(CliRunResult(0, result['text'], ''), task_id=448)
        self.assertEqual(json.loads(normalized)['conclusion'], 'partial')

    def test_hard_deadline_repair_fragmented_drip(self):
        self.test_hard_deadline_repair_drip(fragmented=True)

    def test_repair_timeout_exception_classification(self):
        from bridges.cli_bridge import CliRunResult, normalize_task_delivery
        original = acp._Client.rpc
        for error in (acp.AcpError('workbuddy_acp_timeout'), acp.httpx.ReadTimeout('read')):
            with self.subTest(error=type(error).__name__):
                self.s.writes.clear()
                self.s.script = [{'output': 'bad'}]
                def rpc(client, method, *args, **kwargs):
                    if method == 'session/prompt' and any(m == 'session/prompt' for m, _ in self.s.writes):
                        raise error
                    return original(client, method, *args, **kwargs)
                stderr = io.StringIO()
                with patch.object(acp._Client, 'rpc', rpc), contextlib.redirect_stderr(stderr):
                    result = self.prompt(repair_validator=lambda _: False, repair_prompt='repair')
                self.assertEqual(result['text'], 'bad')
                self.assertIn('repair=timeout', stderr.getvalue())
                self.assertNotIn('repair=failed', stderr.getvalue())
                self.assertEqual(json.loads(normalize_task_delivery(CliRunResult(0, result['text'], ''), task_id=448))['conclusion'], 'partial')

    def test_deadline_during_first_validation_returns_fallback(self):
        from bridges.cli_bridge import CliRunResult, normalize_task_delivery
        self.s.script = [{'output': 'bad'}]
        entered = threading.Event()
        release = threading.Event()
        def validator(_):
            entered.set()
            release.wait(5)
            return False
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                result = self.prompt(timeout=1.5, repair_validator=validator, repair_prompt='repair')
        finally:
            release.set()
        self.assertTrue(entered.is_set())
        self.assertEqual(result['text'], 'bad')
        self.assertIn('repair=timeout', stderr.getvalue())
        self.assertEqual(json.loads(normalize_task_delivery(CliRunResult(0, result['text'], ''), task_id=448))['conclusion'], 'partial')

    def test_repair_paths(self):
        validator = lambda text: text == 'valid'
        for first, second, timeout, expected, count in [('bad', 'valid', 600, 'valid', 2), ('valid', 'bad', 600, 'valid', 1), ('bad', 'bad2', 600, 'bad', 2), ('bad', 'valid', 1, 'bad', 1)]:
            with self.subTest(first=first, second=second, timeout=timeout):
                self.s.writes.clear(); self.s.script=[{'output':first}, {'output':second}]
                result=self.prompt(timeout=timeout, repair_validator=validator, repair_prompt='repair')
                self.assertEqual(result['text'],expected)
                self.assertEqual([sid for method,sid in self.s.writes if method=='session/prompt'], ['talk']*count)
                if count == 2: self.assertAlmostEqual(result['usage']['credits'], .2)
    def test_repair_non_end_turn_and_default(self):
        self.s.script=[{'output':'bad','stopReason':'max_tokens'}]
        with self.assertRaises(acp.AcpError): self.prompt(repair_validator=lambda _: False, repair_prompt='repair')
        self.assertEqual(len([x for x in self.s.writes if x[0]=='session/prompt']),1)
        self.s.writes.clear(); self.s.script=[{'output':'bad'}, {'output':'valid'}]
        self.assertEqual(self.prompt()['text'],'bad')
        self.assertEqual(len([x for x in self.s.writes if x[0]=='session/prompt']),1)
        self.s.writes.clear()
        result = acp.prompt_once('m', 'hello', mode='plan', project_root=Path.cwd(), endpoint=self.endpoint)
        self.assertEqual(result['text'], 'bad')
        self.assertEqual(len([x for x in self.s.writes if x[0]=='session/prompt']),1)
    def test_shim_valid_delivery_without_repair(self):
        from tests.test_workbuddy_delivery import report
        from bridges.cli_bridge import CliRunResult, normalize_task_delivery
        cmd = [sys.executable, '-B', '-m', 'scripts.workbuddy_acp_prompt', '--model', 'm', '--mode', 'task', '--project-root', str(Path.cwd()), '--endpoint', self.endpoint, '--delivery-contract', '--expect-task-id', '443']
        for conclusion, embedded in [('complete', True), ('partial', True), ('complete', False)]:
            with self.subTest(conclusion=conclusion, embedded=embedded):
                value = report()
                value['conclusion'] = conclusion
                if conclusion == 'partial':
                    value['unfinished'] = ['pending']
                good = json.dumps(value, ensure_ascii=False)
                raw = f'\u524d\u8a00 {good} \u540e\u8bb0' if embedded else good
                self.s.writes.clear()
                self.s.script = [{'output': raw}, {'output': 'unexpected repair'}]
                result = subprocess.run(cmd, input=b'hello', capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = result.stdout.decode('utf-8').rstrip('\n')
                self.assertEqual(output, raw)
                self.assertEqual(len([x for x in self.s.writes if x[0] == 'session/prompt']), 1)
                normalized = normalize_task_delivery(CliRunResult(0, output, ''), task_id=443)
                self.assertEqual(json.loads(normalized)['conclusion'], conclusion)

    def test_shim_repair_exit_zero(self):
        from tests.test_workbuddy_delivery import report
        from bridges.cli_bridge import CliRunResult, normalize_task_delivery
        good=json.dumps(report(),ensure_ascii=False)
        cmd=[sys.executable,'-B','-m','scripts.workbuddy_acp_prompt','--model','m','--mode','task','--project-root',str(Path.cwd()),'--endpoint',self.endpoint,'--delivery-contract','--expect-task-id','443']
        for second, expected in [(good,good), ('bad2','bad')]:
            self.s.writes.clear(); self.s.script=[{'output':'bad'}, {'output':second}]
            p=subprocess.run(cmd,input=b'hello',capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stdout.decode('utf-8').rstrip('\n'),expected)
            normalized = normalize_task_delivery(CliRunResult(0,p.stdout.decode('utf-8'),''),task_id=443)
            self.assertEqual(json.loads(normalized)['conclusion'], 'complete' if second == good else 'partial')
            self.assertEqual(len([x for x in self.s.writes if x[0]=='session/prompt']),2)
    def test_duplicate(self):
        self.s.same=True
        with self.assertRaises(acp.AcpError) as cm: self.prompt()
        self.assertEqual(cm.exception.code,'workbuddy_acp_session_bind_failed'); self.assertFalse(self.s.writes)
    def test_unapplied(self):
        self.s.bad_config=True
        with self.assertRaises(acp.AcpError) as cm: self.prompt()
        self.assertEqual(cm.exception.code,'workbuddy_acp_model_not_applied')
    def test_mode_unapplied(self):
        self.s.bad_config='mode'
        with self.assertRaises(acp.AcpError) as cm: self.prompt()
        self.assertEqual(cm.exception.code,'workbuddy_acp_mode_not_applied')
        self.assertFalse(any(method == 'session/prompt' for method, _ in self.s.writes))
    def test_failures(self):
        for attr,code in [('bad_auth','workbuddy_acp_connect_failed'),('bad_sse','workbuddy_acp_initialize_failed'),('slow','workbuddy_acp_timeout')]:
            setattr(self.s,attr,True)
            with self.assertRaises(acp.AcpError) as cm: self.prompt(timeout=.05 if attr == 'slow' else 2)
            self.assertEqual(cm.exception.code,code); self.assertNotIn('PRIVATE',str(cm.exception)); setattr(self.s,attr,False)
    def test_discovery(self):
        acp._endpoint=None
        with patch.dict(os.environ,{},clear=True), patch.object(acp,'_candidate_ports',return_value=[1,self.s.server_port]): self.assertEqual(acp.discover_endpoint(),self.endpoint)
        with patch.dict(os.environ,{'TALK_WORKBUDDY_ACP_ENDPOINT':'http://example.com:123'}):
            with self.assertRaises(acp.AcpError): acp.discover_endpoint()
        with patch.dict(os.environ,{'TALK_WORKBUDDY_ACP_ENDPOINT':self.endpoint}): self.assertEqual(acp.discover_endpoint(),self.endpoint)
        acp._endpoint=None
    def test_discovery_netstat_fallback(self):
        acp._endpoint=None
        net = f"TCP 127.0.0.1:1 0.0.0.0:0 localized 99\nTCP 127.0.0.1:{self.s.server_port} 0.0.0.0:0 localized 10\nTCP 0.0.0.0:999 0.0.0.0:0 localized 10"
        with patch.dict(os.environ, {}, clear=True), patch.object(acp.subprocess, 'check_output', side_effect=['?????', net]):
            self.assertEqual(acp.discover_endpoint(), self.endpoint)
        self.assertEqual(self.s.deletes, 1); acp._endpoint=None
    def test_disconnect_failure(self):
        self.s.delete_fail=True
        self.assertEqual(self.prompt()['text'], 'OK')
    def test_server_requests(self):
        self.s.requests=True
        self.assertEqual(self.prompt()['text'], 'OK')
        self.assertEqual(self.s.replies[0]['result'], {'outcome':{'outcome':'cancelled'}})
        self.assertEqual(self.s.replies[1]['error']['code'], -32601)
    def test_utf8_and_no_leak(self):
        self.s.output='\u4e2d\u6587\u56de\u590d'
        cmd=[sys.executable,'-B','-m','scripts.workbuddy_acp_prompt','--model','\u4e2d\u6587\u6a21\u578b','--mode','chat','--project-root',str(Path.cwd()),'--endpoint',self.endpoint]
        p=subprocess.run(cmd,input='\u4e2d\u6587\u63d0\u793a SECRET PROMPT'.encode('utf-8'),capture_output=True,env={**os.environ,'PYTHONIOENCODING':'cp936'})
        self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stdout,'\u4e2d\u6587\u56de\u590d\n'.encode('utf-8')); self.assertEqual(self.s.prompt_text, '\u4e2d\u6587\u63d0\u793a SECRET PROMPT')
        for forbidden in (b'PRIVATE', b'SECRET PROMPT', '\u4e2d\u6587\u63d0\u793a'.encode('utf-8'), b'connectionId', b'sessionToken'):
            self.assertNotIn(forbidden,p.stdout); self.assertNotIn(forbidden,p.stderr)
    def test_effort_values(self):
        from bridges.codex_effort import apply_effort
        cmd=build_acp_command('m','task',str(Path.cwd()))
        for value in ('low','high','max','enabled'):
            inserted, mode=set_command_effort(cmd,value); self.assertEqual(mode,'inserted'); self.assertEqual(inserted[-2:],['--effort',value])
            replaced, mode=set_command_effort(inserted,value); self.assertEqual(mode,'replaced'); self.assertEqual(replaced[-1],value)
            self.assertEqual(apply_effort(inserted,value)[0][-1],value)
        self.assertEqual(set_command_effort(cmd,'unknown'),(cmd,'unchanged'))
    def test_role_host_aliases(self):
        from scripts.workbuddy_role_host import WorkBuddyRoleHost, rsh
        host=object.__new__(WorkBuddyRoleHost); host.executable=Path('WorkBuddy.exe'); host.models_home=Path('missing'); host.project_root=Path.cwd(); host.display_name='test'
        with patch.object(rsh.HostManager,'build_entry_argv',return_value=([], 'template','budget')):
            for alias in ('custom-local:x','workbuddy-acp:x'):
                self.assertIn('--workbuddy-executable',host.build_entry_argv('workbuddy',alias)[0])
            for runtime,alias in [('other','workbuddy-acp:x'),('workbuddy','other:x'),('workbuddy','workbuddy-acp:'),('workbuddy','custom-local:')]:
                with self.assertRaises(rsh.HostError): host.build_entry_argv(runtime,alias)
    def test_host_dry_run_without_models(self):
        import tempfile
        from scripts.workbuddy_role_host import main, rsh
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'WorkBuddy.exe'; exe.write_bytes(b'')
            with patch('builtins.print'):
                self.assertEqual(main(['serve','--project','p','--member','m','--workbuddy-executable',str(exe),'--workbuddy-models-home',str(Path(d)/'missing')]),0)
            exe.unlink()
            with self.assertRaises(rsh.HostError): main(['serve','--project','p','--member','m','--workbuddy-executable',str(exe),'--workbuddy-models-home',str(Path(d)/'missing')])
    def test_list(self):
        rows=acp.list_models(self.endpoint); self.assertEqual(len(rows),1); self.assertEqual(rows[0]['_meta']['credits'],.1)
    def test_shim(self):
        cmd=[sys.executable,'-B','-X','utf8','-m','scripts.workbuddy_acp_prompt','--model','m','--mode','chat','--project-root',str(Path.cwd()),'--endpoint',self.endpoint]
        p=subprocess.run(cmd,input='SECRET PROMPT',text=True,capture_output=True); self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stdout,'OK\n'); self.assertNotIn('SECRET PROMPT',p.stderr); self.assertNotIn('PRIVATE',p.stderr)
        p=subprocess.run(cmd,input='',text=True,capture_output=True); self.assertEqual(p.returncode,2)
    def test_register(self):
        payload=choice_payload({'modelId':'m','name':'Model'}); self.assertEqual(payload['model_alias'],'workbuddy-acp:m')
        rows=register(self.endpoint,'SECRETKEY',['m'],'runner:workbuddy-embedded-cli',[{'modelId':'m','name':'Model'}]); self.assertEqual(rows[0]['choice_id'],'choice-1'); self.assertEqual(self.s.payload,payload)
    def test_bridge_and_native(self):
        cmd=build_acp_command('m','task',str(Path.cwd())); rewritten,mode=set_command_effort(cmd,'max'); self.assertEqual(mode,'inserted'); self.assertEqual(rewritten[-2:],['--effort','max'])
        with self.assertRaises(WorkBuddyNativeError) as cm: resolve_launch([],Path.cwd(),{'model_alias':'workbuddy-acp:m'})
        self.assertEqual(cm.exception.reason_code,'workbuddy_builtin_execution_session_unsupported')
if __name__=='__main__': unittest.main()
