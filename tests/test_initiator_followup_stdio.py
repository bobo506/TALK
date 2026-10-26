"""Real interactive pipes + isolated API. A files fallback cannot prove cancellation."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from sqlmodel import select

import server.main as main
from server.models import AgentTask
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

ROOT=Path(__file__).resolve().parents[1]


class InteractiveClient:
    def __init__(self,base,root):
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TALK_API_KEY='lead-key',
            TALK_PROJECT_ID='prj_stdio',TALK_FOLLOWUP_CLIENT_TIMEOUT_SECONDS='10',TALK_FOLLOWUP_WAIT_SECONDS='4',
            TALK_FOLLOWUP_TOTAL_SECONDS='40',TALK_FOLLOWUP_RETURN_MARGIN_SECONDS='5',TMP=str(root),TEMP=str(root))
        self.err=(root/'mcp.stderr').open('w',encoding='utf-8')
        self.process=subprocess.Popen([sys.executable,'-B','-X','utf8',str(ROOT/'bridges/talk_terminal_mcp.py'),
            '--project-root',str(root),'--project','prj_stdio','--server',base],cwd=root,env=env,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,text=True,encoding='utf-8',bufsize=1)
        self.queue=queue.Queue();self.saved={}
        def reader():
            for line in self.process.stdout:
                if line.strip():self.queue.put(json.loads(line))
        self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()

    def send(self,value):
        self.process.stdin.write(json.dumps(value)+'\n');self.process.stdin.flush()

    def call(self,id_,name,args):
        self.send({'jsonrpc':'2.0','id':id_,'method':'tools/call','params':{'name':name,'arguments':args}})

    def receive(self,id_,timeout=10):
        if id_ in self.saved:return self.saved.pop(id_)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=self.queue.get(timeout=max(.001,deadline-time.monotonic()))
            if value.get('id')==id_:return value
            self.saved[value.get('id')]=value
        raise AssertionError('MCP response timeout')

    @staticmethod
    def payload(value):
        assert not value['result'].get('isError'),value
        return json.loads(value['result']['content'][0]['text'])

    def close(self):
        if not self.process.stdin.closed:self.process.stdin.close()
        try:self.process.wait(timeout=8)
        finally:
            if self.process.poll() is None:self.process.kill();self.process.wait(timeout=5)
            self.process.stdout.close();self.err.close();self.reader.join(timeout=1)


class FollowupStdioTests(RouteTestCase):
    def record(self, case, **facts):
        root=Path(os.environ.get('TALK_ISOLATED_TEST_ROOT',str(self._tmpdir)))
        with (root/'stdio-evidence.jsonl').open('a',encoding='utf-8') as output:
            output.write(json.dumps({'case':case,'host':'isolated Python interactive JSON-RPC client',
                'client_timeout_seconds':10,'wait_seconds':4,'return_margin_seconds':5,**facts})+'\n')

    def setUp(self):
        super().setUp()
        for member,key in [('human:qa','qa-key'),('agent:lead','lead-key'),('agent:worker','worker-key')]:self.add_member(member,api_key=key)
        self.client=self.make_client();self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.client.post('/api/projects',headers={'X-API-Key':'qa-key'},json={'project_id':'prj_stdio','display_name':'stdio'}).raise_for_status()
        self.mode('active')
        self.server=LiveTalkServer(main.app);self.base=self.server.__enter__();self.addCleanup(self.server.__exit__,None,None,None)
        root=self._tmpdir/'client';root.mkdir()
        (root/'.talk').mkdir()
        (root/'.talk'/'project.yaml').write_text('project_id: prj_stdio\n',encoding='utf-8')
        self.mcp=InteractiveClient(self.base,root);self.addCleanup(self.mcp.close)
        self.mcp.send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
        self.assertEqual(self.mcp.receive(1)['result']['serverInfo']['version'],'3.0.0')

    def mode(self,mode):
        p=self.client.get('/api/projects/prj_stdio',headers={'X-API-Key':'qa-key'}).json()
        self.client.patch('/api/projects/prj_stdio/controller-mode',headers={'X-API-Key':'qa-key'},
            json={'mode':mode,'expected_version':p['controller_mode_version']}).raise_for_status()

    def dispatch(self):
        self.mcp.call(2,'talk_delegate_task',{'project_id':'prj_stdio','target_member_id':'agent:worker','content':'test only'})
        task=self.mcp.payload(self.mcp.receive(2));return task,task['initiator_followup']['followup_id']

    def test_wait_does_not_queue_ping_query_or_duplicate_wait_and_cancel_is_read_only(self):
        task,fid=self.dispatch()
        self.mcp.call(3,'talk_follow_tasks',{'action':'next','followup_id':fid})
        started=time.monotonic()
        self.mcp.send({'jsonrpc':'2.0','id':4,'method':'ping'})
        self.assertEqual(self.mcp.receive(4,2)['result'],{})
        self.mcp.call(5,'talk_get_task',{'task_id':task['id']})
        self.assertEqual(self.mcp.payload(self.mcp.receive(5,2))['task']['status'],'queued')
        query_elapsed=time.monotonic()-started
        self.assertLess(query_elapsed,2)
        self.mcp.call(6,'talk_follow_tasks',{'action':'next','followup_id':fid})
        self.assertTrue(self.mcp.receive(6,2)['result']['isError'])
        start=time.monotonic()
        self.mcp.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':3}})
        canceled=self.mcp.receive(3,2)
        self.assertEqual(canceled['result']['_meta']['error_code'],'request_cancelled')
        cancel_elapsed=time.monotonic()-start
        self.assertLess(cancel_elapsed,2)
        self.record('query_and_cancel',query_elapsed_seconds=query_elapsed,cancel_elapsed_seconds=cancel_elapsed,
            duplicate_wait_rejected=True,executor_status='queued')
        self.mcp.call(7,'talk_get_task',{'task_id':task['id']})
        self.assertEqual(self.mcp.payload(self.mcp.receive(7,2))['task']['status'],'queued')

    def test_eof_ends_wait_without_task_cancel_or_long_process_queue(self):
        task,fid=self.dispatch()
        self.mcp.call(3,'talk_follow_tasks',{'action':'next','followup_id':fid})
        self.mcp.send({'jsonrpc':'2.0','id':4,'method':'ping'});self.mcp.receive(4,2)
        started=time.monotonic()
        self.mcp.process.stdin.close();self.mcp.process.wait(timeout=7)
        self.record('eof',process_exit_seconds=time.monotonic()-started)
        with self.session() as session:
            row=session.get(AgentTask,task['id']);self.assertEqual(row.status,'queued');self.assertIsNone(row.result_message_id)

    def test_mode_changed_during_wait_stops_without_collect_or_cancel(self):
        task,fid=self.dispatch()
        self.mcp.call(3,'talk_follow_tasks',{'action':'next','followup_id':fid})
        self.mcp.send({'jsonrpc':'2.0','id':4,'method':'ping'});self.mcp.receive(4,2)
        started=time.monotonic();self.mode('passive')
        result=self.mcp.payload(self.mcp.receive(3,3))
        self.assertEqual(result['stop_reason'],'mode_changed')
        self.record('mode_change',stop_elapsed_seconds=time.monotonic()-started,stop_reason=result['stop_reason'])
        with self.session() as session:self.assertEqual(session.get(AgentTask,task['id']).status,'queued')

    def test_real_single_wait_expires_inside_client_budget_and_connection_continues(self):
        task,fid=self.dispatch()
        started=time.monotonic()
        self.mcp.call(3,'talk_follow_tasks',{'action':'next','followup_id':fid})
        result=self.mcp.payload(self.mcp.receive(3,10))
        elapsed=time.monotonic()-started
        self.assertEqual(result['wait_outcome'],'timeout')
        self.assertGreaterEqual(elapsed,3.7)
        self.assertLess(elapsed,5.5)  # W=4, T=10, configured margin=5.
        self.record('timeout',elapsed_seconds=elapsed,wait_outcome=result['wait_outcome'])
        self.mcp.send({'jsonrpc':'2.0','id':4,'method':'ping'})
        self.assertEqual(self.mcp.receive(4,2)['result'],{})
        self.mcp.call(5,'talk_get_task',{'task_id':task['id']})
        self.assertEqual(self.mcp.payload(self.mcp.receive(5))['task']['status'],'queued')

    def test_full_interactive_delivery_and_guarded_receipt(self):
        task,fid=self.dispatch()
        self.mcp.call(3,'talk_follow_tasks',{'action':'next','followup_id':fid})
        h={'X-API-Key':'worker-key'}
        claimed=self.client.post(f"/api/tasks/{task['id']}/claim",headers=h,json={}).json()
        message=self.client.post('/api/messages',headers=h,json={'type':'text','content':'fixed synthetic delivery',
            'group_id':task['hall_group_id']}).json()
        self.client.post(f"/api/tasks/{task['id']}/complete",headers=h,json={'status':'succeeded',
            'claim_token':claimed['claim_token'],'result_message_id':message['id']}).raise_for_status()
        result=self.mcp.payload(self.mcp.receive(3,4))
        self.assertEqual(result['next_action'],'verify_delivery_before_collection')
        self.assertEqual(result['delivery']['delivery_conclusion']['value'],'unknown')
        self.mcp.call(4,'talk_follow_tasks',{'action':'collect','followup_id':fid,'reference':result['reference'],
            'verification_summary':'Synthetic expected fixed output inspected independently by test.',
            'evidence_refs':['tests/test_initiator_followup_stdio.py']})
        collected=self.mcp.payload(self.mcp.receive(4,3))
        self.assertEqual(collected['collection']['task']['workflow_status'],'completed')
        self.assertFalse(collected['collection_is_acceptance'])
        self.record('delivery_and_receipt',workflow_status=collected['collection']['task']['workflow_status'],
            business_conclusion=result['delivery']['delivery_conclusion']['value'],collection_is_acceptance=False)

    def test_legacy_controlled_wait_has_real_cancel_detection_on_this_entry(self):
        task,fid=self.dispatch()
        self.mcp.call(3,'talk_wait_tasks',{'project_id':'prj_stdio','task_ids':[task['id']],
            'controlled_wait':True,'timeout_seconds':4})
        self.mcp.send({'jsonrpc':'2.0','id':4,'method':'ping'});self.mcp.receive(4,2)
        started=time.monotonic()
        self.mcp.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':3}})
        self.assertEqual(self.mcp.receive(3,2)['result']['_meta']['error_code'],'request_cancelled')
        self.record('legacy_wait_cancel',elapsed_seconds=time.monotonic()-started,executor_status='queued')
        with self.session() as session:self.assertEqual(session.get(AgentTask,task['id']).status,'queued')
