"""Real isolated HTTP, creator flow, finite budgets and guarded collection."""
import copy
import hashlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from sqlmodel import select
from sqlalchemy import event

from bridges import initiator_followup as follow
from bridges import talk_task_tools as tools
from bridges.mcp_wait_context import CURRENT_WAIT, WaitContext, WaitCancelled
from server.models import AgentTask, Message, Project
from server.db import begin_immediate_write
from server.routes import tasks as routes
from tests.test_support import RouteTestCase

PROJECT='prj_follow_test'
BUDGET={'client_timeout_seconds':10,'wait_seconds':2,'total_seconds':30,'return_margin_seconds':5}
ENV={'TALK_BASE_URL':'http://synthetic.invalid','TALK_API_KEY':'lead-key','TALK_PROJECT_ID':PROJECT,
     'TALK_FOLLOWUP_CLIENT_TIMEOUT_SECONDS':'10','TALK_FOLLOWUP_WAIT_SECONDS':'2',
     'TALK_FOLLOWUP_TOTAL_SECONDS':'30','TALK_FOLLOWUP_RETURN_MARGIN_SECONDS':'5'}


class InitiatorFlowTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        for member,key in [('human:qa','qa-key'),('agent:lead','lead-key'),('agent:worker','worker-key'),('agent:other','other-key')]:
            self.add_member(member,api_key=key)
        self.client=self.make_client();self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.assertEqual(self.client.post('/api/projects',headers={'X-API-Key':'qa-key'},
            json={'project_id':PROJECT,'display_name':'follow'}).status_code,201)
        self.mode('active')
        self.calls=[]
        self.patch_api=patch.object(tools,'_api_request',side_effect=self.api);self.patch_api.start();self.addCleanup(self.patch_api.stop)
        self.env=patch.dict(os.environ,ENV);self.env.start();self.addCleanup(self.env.stop)
        self.manager=follow.Followups(tools)
        self.patch_manager=patch.object(follow,'_MANAGER',self.manager);self.patch_manager.start();self.addCleanup(self.patch_manager.stop)

    def mode(self,value):
        p=self.client.get(f'/api/projects/{PROJECT}',headers={'X-API-Key':'qa-key'}).json()
        result=self.client.patch(f'/api/projects/{PROJECT}/controller-mode',headers={'X-API-Key':'qa-key'},
            json={'mode':value,'expected_version':p['controller_mode_version']})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()['controller_mode_version']

    def api(self,method,path,*,json_body=None,params=None,**kwargs):
        self.calls.append((method,path,copy.deepcopy(json_body)))
        response=self.client.request(method,path,headers={'X-API-Key':'lead-key'},json=json_body,params=params)
        if response.status_code>=400:
            raise tools.TalkApiHttpError(str(response.json().get('detail')),status=response.status_code)
        return response.json()

    def create(self,target='agent:worker'):
        return tools.dispatch_tool('talk_delegate_task',{'project_id':PROJECT,'target_member_id':target,'content':'synthetic task'})

    def complete(self,task,content='unstructured report; MUST NOT be automatic acceptance'):
        key='worker-key' if task['target_member_id']=='agent:worker' else 'other-key'
        headers={'X-API-Key':key}
        claimed=self.client.post(f"/api/tasks/{task['id']}/claim",headers=headers,json={})
        self.assertEqual(claimed.status_code,200,claimed.text)
        message=self.client.post('/api/messages',headers=headers,json={'type':'text','content':content,'group_id':task['hall_group_id']})
        self.assertEqual(message.status_code,201,message.text)
        result=self.client.post(f"/api/tasks/{task['id']}/complete",headers=headers,
            json={'status':'succeeded','claim_token':claimed.json()['claim_token'],'result_message_id':message.json()['id']})
        self.assertEqual(result.status_code,200,result.text)
        return message.json()

    def current(self,task_id):
        return self.client.get(f'/api/tasks/{task_id}',headers={'X-API-Key':'lead-key'}).json()

    def next(self,task):
        return self.manager.call({'action':'next','followup_id':task['initiator_followup']['followup_id']})

    def collect_args(self,delivery):
        return {'action':'collect','followup_id':delivery['followup_id'],'reference':delivery['reference'],
                'verification_summary':'Creator inspected the synthetic delivery and its test evidence.',
                'evidence_refs':['tests/test_initiator_followup.py: isolated evidence']}

    def test_active_dispatch_delivery_verification_collection_closes_only_receipt_flow(self):
        task=self.create();self.assertEqual(task['initiator_followup']['state'],'watching')
        message=self.complete(task)
        delivery=self.next(task)
        self.assertEqual(delivery['next_action'],'verify_delivery_before_collection')
        self.assertEqual(delivery['delivery']['delivery_conclusion']['value'],'unknown')
        self.assertEqual(delivery['reference']['content_sha256'],hashlib.sha256(message['content'].encode()).hexdigest())
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')
        bad=self.collect_args(delivery);bad.pop('evidence_refs')
        with self.assertRaisesRegex(follow.FollowupError,'evidence_refs'):self.manager.call(bad)
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')
        receipt=self.manager.call(self.collect_args(delivery))
        self.assertFalse(receipt['collection_is_acceptance'])
        self.assertEqual(receipt['collection']['task']['workflow_status'],'completed')
        self.assertEqual(self.next(task)['stop_reason'],'all_results_collected')

    def test_passive_dispatch_has_no_flow_and_start_does_not_read_tasks(self):
        self.mode('passive');task=self.create()
        self.assertNotIn('initiator_followup',task);self.assertFalse(self.manager.flows)
        self.calls.clear()
        result=self.manager.call({'action':'start','project_id':PROJECT,'task_ids':[task['id']],'budget':BUDGET})
        self.assertEqual(result['state'],'passive')
        self.assertEqual([c[1] for c in self.calls],['/api/members/me',f'/api/projects/{PROJECT}'])

    def test_invalid_ids_are_rejected_before_http_or_flow_creation(self):
        for ids in (None,[],[True],[1.0],['1'],[0],[-1],[1,None],list(range(1,22))):
            self.calls.clear()
            with self.assertRaises(follow.FollowupError):
                self.manager.call({'action':'start','project_id':PROJECT,'task_ids':ids,'budget':BUDGET})
            self.assertFalse(self.calls)

    def test_cross_owner_or_project_batch_never_publishes_partial_flow(self):
        self.env.stop()
        # Create two ordinary tasks without auto enrollment, then corrupt only a synthetic scope.
        with patch.dict(os.environ,{'TALK_FOLLOWUP_CLIENT_TIMEOUT_SECONDS':'','TALK_FOLLOWUP_WAIT_SECONDS':'',
            'TALK_FOLLOWUP_TOTAL_SECONDS':'','TALK_FOLLOWUP_RETURN_MARGIN_SECONDS':''}):
            a=self.create();b=self.create()
        for field,value in [('created_by','agent:other'),('project_id','prj_other')]:
            with self.session() as session:
                row=session.get(AgentTask,b['id']);row.created_by='agent:lead';row.project_id=PROJECT
                setattr(row,field,value);session.add(row);session.commit()
            result=self.manager.start(PROJECT,[a['id'],b['id']],BUDGET)
            self.assertIn(result['stop_reason'],('task_scope_changed','task_scope_unavailable'))
            self.assertFalse(self.manager.flows)

    def test_mode_change_stops_next_and_never_cancels_task(self):
        task=self.create();before=self.current(task['id']);self.mode('passive')
        self.assertEqual(self.next(task)['stop_reason'],'mode_changed')
        self.assertEqual(before,self.current(task['id']))

    def test_mode_flip_back_to_active_still_invalidates_version(self):
        task=self.create();self.mode('passive');self.mode('active')
        self.assertEqual(self.next(task)['stop_reason'],'mode_changed')

    def test_mode_change_prevents_next_automatic_review_dispatch(self):
        task=self.create();self.complete(task);self.next(task);self.mode('passive')
        self.calls.clear()
        with self.assertRaisesRegex(follow.FollowupError,'mode_changed'):self.create('agent:other')
        self.assertFalse(any(c[0]=='POST' for c in self.calls))

    def test_active_legacy_collect_cannot_skip_the_verification_declaration(self):
        task=self.create();self.complete(task);self.next(task)
        with self.assertRaisesRegex(follow.FollowupError,'requires_verification'):
            tools.dispatch_tool('talk_collect_result',{'task_id':task['id']})
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')

    def test_mode_changed_between_verification_and_post_is_atomically_rejected(self):
        task=self.create();self.complete(task);delivery=self.next(task)
        original=self.api
        def api(method,path,**kwargs):
            if path.endswith('/collect-followup-result'):self.mode('passive')
            return original(method,path,**kwargs)
        with patch.object(tools,'_api_request',side_effect=api):
            with self.assertRaisesRegex(follow.FollowupError,'collection_guard_rejected'):
                self.manager.call(self.collect_args(delivery))
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')

    def test_changed_message_in_gap_is_atomically_rejected(self):
        task=self.create();message=self.complete(task);delivery=self.next(task)
        original=self.api
        def api(method,path,**kwargs):
            if path.endswith('/collect-followup-result'):
                with self.session() as session:
                    row=session.get(Message,message['id']);row.content='changed after verification';session.add(row);session.commit()
            return original(method,path,**kwargs)
        with patch.object(tools,'_api_request',side_effect=api):
            with self.assertRaisesRegex(follow.FollowupError,'collection_guard_rejected'):self.manager.call(self.collect_args(delivery))
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')

    def test_task_human_checkpoint_stops_followup_without_collection(self):
        task=self.create();self.complete(task)
        with self.session() as session:
            row=session.get(AgentTask,task['id']);row.control_status='awaiting_human';session.add(row);session.commit()
        self.assertEqual(self.next(task)['stop_reason'],'task_control_changed')
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')

    def test_total_budget_is_monotonic_and_not_renewed_by_next(self):
        now=[10.0];self.manager.clock=lambda:now[0]
        task=self.create();flow=self.manager.get(task['initiator_followup']['followup_id']);deadline=flow.deadline
        now[0]=deadline+1
        self.assertEqual(self.next(task)['stop_reason'],'total_budget_exhausted')
        self.assertEqual(flow.deadline,deadline)

    def test_next_timeout_does_not_complete_or_requeue_task(self):
        task=self.create();flow=self.manager.get(task['initiator_followup']['followup_id'])
        flow.budget=follow.Budget(10,.05,30,5)
        before=self.current(task['id']);result=self.next(task)
        self.assertIn(result.get('wait_outcome'),('timeout',))
        self.assertEqual(before,self.current(task['id']))

    def test_client_cancel_only_stops_read_flow(self):
        task=self.create();before=self.current(task['id']);context=WaitContext();context.cancelled.set()
        token=CURRENT_WAIT.set(context)
        try:
            with self.assertRaises(WaitCancelled):self.next(task)
        finally:CURRENT_WAIT.reset(token)
        self.assertEqual(self.manager.get(task['initiator_followup']['followup_id']).reason,'client_cancelled')
        self.assertEqual(before,self.current(task['id']))

    def test_explicit_stop_interrupts_busy_next_without_waiting_for_it(self):
        task=self.create();fid=task['initiator_followup']['followup_id']
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(self.next,task)
            deadline=time.monotonic()+2
            while self.manager.get(fid).state!='waiting' and time.monotonic()<deadline:time.sleep(.005)
            stopped=self.manager.call({'action':'stop','followup_id':fid})
            self.assertEqual(stopped['stop_reason'],'creator_stopped')
            self.assertEqual(future.result(timeout=2)['stop_reason'],'creator_stopped')
        self.assertEqual(self.current(task['id'])['status'],'queued')

    def test_review_delegation_joins_same_finite_batch(self):
        task=self.create();self.complete(task);self.next(task)
        flow=self.manager.get(task['initiator_followup']['followup_id']);deadline=flow.deadline
        review=self.create('agent:other')
        self.assertEqual(review['initiator_followup']['followup_id'],flow.id)
        self.assertEqual(flow.ids,[task['id'],review['id']]);self.assertEqual(flow.deadline,deadline)

    def test_review_delivery_is_not_starved_by_uncollected_original(self):
        task=self.create();self.complete(task);original=self.next(task)
        self.assertEqual(self.next(task)['next_action'],'verify_pending_deliveries')
        review=self.create('agent:other');self.complete(review,'Independent synthetic review evidence')
        reviewed=self.next(task)
        self.assertEqual(reviewed['reference']['task_id'],review['id'])
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')
        self.manager.call(self.collect_args(reviewed))
        self.manager.call(self.collect_args(original))
        self.assertEqual(self.next(task)['stop_reason'],'all_results_collected')

    def test_mode_changed_in_dispatch_gap_creates_no_extra_task(self):
        task=self.create();self.complete(task);self.next(task)
        before=len(self.client.get('/api/tasks',headers={'X-API-Key':'lead-key'}).json())
        original=self.api
        def api(method,path,**kwargs):
            if path=='/api/tasks/followup' and method=='POST':self.mode('passive')
            return original(method,path,**kwargs)
        with patch.object(tools,'_api_request',side_effect=api):
            with self.assertRaises(tools.TalkApiHttpError):self.create('agent:other')
        self.assertEqual(before,len(self.client.get('/api/tasks',headers={'X-API-Key':'lead-key'}).json()))

    def test_old_backend_never_falls_back_to_unguarded_collection(self):
        task=self.create();self.complete(task);delivery=self.next(task)
        original=self.api
        def api(method,path,**kwargs):
            if path.endswith('/collect-followup-result'):
                raise tools.TalkApiHttpError('missing old backend route',status=404)
            return original(method,path,**kwargs)
        self.calls.clear()
        with patch.object(tools,'_api_request',side_effect=api):
            with self.assertRaisesRegex(follow.FollowupError,'backend_followup_unsupported'):
                self.manager.call(self.collect_args(delivery))
        self.assertFalse(any(c[1].endswith('/collect-result') for c in self.calls))
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')

    def test_collection_5xx_after_commit_is_unknown_and_never_blindly_retried(self):
        task=self.create();self.complete(task);delivery=self.next(task)
        original=self.api;posts=[]
        def api(method,path,**kwargs):
            result=original(method,path,**kwargs)
            if path.endswith('/collect-followup-result'):
                posts.append(path)
                raise tools.TalkApiHttpError('response failed after commit',status=500)
            return result
        with patch.object(tools,'_api_request',side_effect=api):
            with self.assertRaisesRegex(follow.FollowupError,'outcome_unconfirmed'):
                self.manager.call(self.collect_args(delivery))
        self.assertEqual(len(posts),1)
        self.assertEqual(self.current(task['id'])['workflow_status'],'completed')

    def test_dispatch_5xx_after_commit_is_unknown_with_no_duplicate_post(self):
        original=self.api;posts=[]
        def api(method,path,**kwargs):
            result=original(method,path,**kwargs)
            if method=='POST' and path=='/api/tasks/followup':
                posts.append(path)
                raise tools.TalkApiHttpError('response failed after commit',status=500)
            return result
        with patch.object(tools,'_api_request',side_effect=api):
            with self.assertRaisesRegex(follow.FollowupError,'outcome_unconfirmed'):self.create()
        self.assertEqual(len(posts),1)
        self.assertEqual(len(self.client.get('/api/tasks',headers={'X-API-Key':'lead-key'}).json()),1)

    def test_changed_identity_stops_entire_flow_before_task_reads(self):
        task=self.create();original=self.api;self.calls.clear()
        def api(method,path,**kwargs):
            if path=='/api/members/me':return {'id':'agent:other','kind':'agent'}
            return original(method,path,**kwargs)
        with patch.object(tools,'_api_request',side_effect=api):
            self.assertEqual(self.next(task)['stop_reason'],'identity_changed')
        self.assertFalse(any(c[1].startswith('/api/tasks') for c in self.calls))

    def test_wal_mode_writer_serializes_before_active_create_and_collect_guards(self):
        task=self.create();message=self.complete(task)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('PRAGMA journal_mode=WAL').scalar(),'wal')
        for operation in ('create','collect'):
            version=self.mode('active')
            if operation=='create':
                path='/api/tasks/followup'
                body={'project_id':PROJECT,'target_member_id':'agent:other','content':'guarded review',
                      'expected_mode_version':version,'followup_task_ids':[task['id']]}
            else:
                path=f"/api/tasks/{task['id']}/collect-followup-result"
                body={'expected_mode_version':version,'expected_result_message_id':message['id'],
                      'expected_content_sha256':hashlib.sha256(message['content'].encode()).hexdigest()}
            attempted=threading.Event()
            def before_cursor(conn,cursor,statement,parameters,context,executemany):
                if statement=='BEGIN IMMEDIATE':attempted.set()
            with self.session() as writer:
                begin_immediate_write(writer)
                project=writer.get(Project,PROJECT);project.controller_mode='passive';project.controller_mode_version+=1
                writer.add(project);writer.flush()
                event.listen(self.engine,'before_cursor_execute',before_cursor)
                try:
                    with ThreadPoolExecutor(1) as pool:
                        future=pool.submit(self.client.post,path,headers={'X-API-Key':'lead-key'},json=body)
                        try:
                            self.assertTrue(attempted.wait(2));self.assertFalse(future.done())
                        finally:writer.commit()
                        response=future.result(timeout=5)
                finally:event.remove(self.engine,'before_cursor_execute',before_cursor)
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(response.json()['detail'],'followup_mode_changed')
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')
        self.assertEqual(len(self.client.get('/api/tasks',headers={'X-API-Key':'lead-key'}).json()),1)

    def test_bad_budget_stops_before_task_creation(self):
        for values in [{'TALK_FOLLOWUP_CLIENT_TIMEOUT_SECONDS':'NaN'}, {'TALK_FOLLOWUP_WAIT_SECONDS':'9'},
                       {'TALK_FOLLOWUP_RETURN_MARGIN_SECONDS':'1'}, {'TALK_FOLLOWUP_TOTAL_SECONDS':'-1'}]:
            before=len(self.client.get('/api/tasks',headers={'X-API-Key':'lead-key'}).json())
            with patch.dict(os.environ,values):
                with self.assertRaises(follow.FollowupError):self.create()
            self.assertEqual(before,len(self.client.get('/api/tasks',headers={'X-API-Key':'lead-key'}).json()))

    def test_atomic_route_creator_and_manual_legacy_are_separate(self):
        task=self.create();message=self.complete(task)
        body={'expected_result_message_id':message['id'],'expected_content_sha256':hashlib.sha256(message['content'].encode()).hexdigest(),
              'expected_mode_version':1}
        for key,status in [('qa-key',403),('other-key',403)]:
            result=self.client.post(f"/api/tasks/{task['id']}/collect-followup-result",headers={'X-API-Key':key},json=body)
            self.assertIn(result.status_code,(403,404),result.text)
        self.mode('passive')
        result=self.client.post(f"/api/tasks/{task['id']}/collect-followup-result",headers={'X-API-Key':'lead-key'},json=body)
        self.assertEqual(result.status_code,409)
        # Human-triggered legacy receipt keeps its original permission and semantics.
        result=self.client.post(f"/api/tasks/{task['id']}/collect-result",headers={'X-API-Key':'lead-key'})
        self.assertEqual(result.status_code,200,result.text)


    def test_explicit_start_without_environment_enrolls_review_and_rework_in_same_budget(self):
        with patch.dict(os.environ,{k:'' for k in ENV if k.startswith('TALK_FOLLOWUP_')}):
            now=[100.0];self.manager.clock=lambda:now[0]
            task=self.create();self.assertNotIn('initiator_followup',task)
            started=self.manager.call({'action':'start','project_id':PROJECT,'task_ids':[task['id']],'budget':BUDGET})
            flow=self.manager.get(started['followup_id']);deadline=flow.deadline
            self.complete(task);self.manager.call({'action':'next','followup_id':flow.id})
            now[0]=104;self.calls.clear()
            review=self.create('agent:other');rework=self.create('agent:worker')
            self.assertEqual(review['initiator_followup']['followup_id'],flow.id)
            self.assertEqual(rework['initiator_followup']['followup_id'],flow.id)
            self.assertEqual(flow.ids,[task['id'],review['id'],rework['id']])
            self.assertEqual(flow.deadline,deadline);self.assertEqual(flow.budget,follow.Budget.parse(BUDGET))
            posts=[c for c in self.calls if c[0]=='POST']
            self.assertEqual([p[1] for p in posts],['/api/tasks/followup']*2)
            self.assertEqual(posts[0][2]['followup_task_ids'],[task['id']])
            self.assertEqual(posts[1][2]['followup_task_ids'],[task['id'],review['id']])
            self.assertTrue(all(p[2]['expected_mode_version']==flow.version for p in posts))

    def test_explicit_start_without_environment_expired_flow_rejects_new_post(self):
        with patch.dict(os.environ,{k:'' for k in ENV if k.startswith('TALK_FOLLOWUP_')}):
            now=[100.0];self.manager.clock=lambda:now[0];task=self.create()
            started=self.manager.call({'action':'start','project_id':PROJECT,'task_ids':[task['id']],'budget':BUDGET})
            flow=self.manager.get(started['followup_id']);now[0]=flow.deadline+1;self.calls.clear()
            with self.assertRaises(follow.FollowupError):self.create('agent:other')
            self.assertEqual(flow.reason,'total_budget_exhausted')
            self.assertFalse(any(c[0]=='POST' for c in self.calls))

    def test_explicit_start_without_environment_changed_identity_rejects_post(self):
        with patch.dict(os.environ,{k:'' for k in ENV if k.startswith('TALK_FOLLOWUP_')}):
            task=self.create();started=self.manager.call({'action':'start','project_id':PROJECT,'task_ids':[task['id']],'budget':BUDGET})
            flow=self.manager.get(started['followup_id']);original=self.api;self.calls.clear()
            def api(method,path,**kwargs):
                if path=='/api/members/me':return {'id':'agent:other','kind':'agent'}
                return original(method,path,**kwargs)
            with patch.object(tools,'_api_request',side_effect=api):
                with self.assertRaisesRegex(follow.FollowupError,'identity_changed'):self.create('agent:other')
            self.assertEqual(flow.reason,'identity_changed')
            self.assertFalse(any(c[0]=='POST' for c in self.calls))

    def test_explicit_start_without_environment_mode_flip_rejects_post(self):
        with patch.dict(os.environ,{k:'' for k in ENV if k.startswith('TALK_FOLLOWUP_')}):
            task=self.create();started=self.manager.call({'action':'start','project_id':PROJECT,'task_ids':[task['id']],'budget':BUDGET})
            flow=self.manager.get(started['followup_id']);self.mode('passive');self.calls.clear()
            with self.assertRaisesRegex(follow.FollowupError,'mode_changed'):self.create('agent:other')
            self.assertEqual(flow.reason,'mode_changed')
            self.assertFalse(any(c[0]=='POST' for c in self.calls))

    def test_stop_before_collection_dispatch_keeps_result_uncollected(self):
        task=self.create();self.complete(task);delivery=self.next(task)
        flow=self.manager.get(delivery['followup_id']);original=self.manager.reference
        def stop_after_reference(value):
            result=original(value);self.manager.stop(flow,'creator_stopped');return result
        self.calls.clear()
        with patch.object(self.manager,'reference',side_effect=stop_after_reference):
            result=self.manager.call(self.collect_args(delivery))
        self.assertEqual(result['state'],'stopped');self.assertEqual(result['stop_reason'],'creator_stopped')
        self.assertFalse(any(c[0]=='POST' for c in self.calls))
        self.assertEqual(self.current(task['id'])['workflow_status'],'submitted')

    def collect_with_concurrent_stop(self,fail_after_commit=False):
        task=self.create();self.complete(task);delivery=self.next(task)
        flow=self.manager.get(delivery['followup_id']);entered=threading.Event();release=threading.Event();original=self.api
        def api(method,path,**kwargs):
            if method=='POST' and path.endswith('/collect-followup-result'):
                entered.set()
                if not release.wait(3):raise AssertionError('test release was not signaled')
                value=original(method,path,**kwargs)
                if fail_after_commit:raise tools.TalkApiHttpError('synthetic response failed after commit',status=500)
                return value
            return original(method,path,**kwargs)
        self.calls.clear()
        with patch.object(tools,'_api_request',side_effect=api):
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(self.manager.call,self.collect_args(delivery))
                try:
                    self.assertTrue(entered.wait(3))
                    stopped=self.manager.call({'action':'stop','followup_id':flow.id})
                    self.assertEqual(stopped['stop_reason'],'creator_stopped')
                    self.assertFalse(future.done())
                finally:release.set()
                if fail_after_commit:
                    with self.assertRaisesRegex(follow.FollowupError,'outcome_unconfirmed'):future.result(timeout=5)
                else:
                    result=future.result(timeout=5)
                    self.assertEqual(result['state'],'stopped');self.assertEqual(result['next_action'],'notify_user')
                    self.assertEqual(result['collection']['task']['workflow_status'],'completed')
                    self.assertIn(task['id'],flow.collected)
        self.assertEqual(flow.state,'stopped');self.assertEqual(flow.reason,'creator_stopped')
        self.assertEqual(self.current(task['id'])['workflow_status'],'completed')
        self.assertEqual(len([c for c in self.calls if c[0]=='POST']),1)
        self.assertEqual(self.manager.call({'action':'next','followup_id':flow.id})['state'],'stopped')

    def test_stop_during_collection_keeps_terminal_state_and_actual_receipt(self):
        self.collect_with_concurrent_stop()

    def test_stop_during_failed_collection_keeps_original_stop_reason(self):
        self.collect_with_concurrent_stop(fail_after_commit=True)
