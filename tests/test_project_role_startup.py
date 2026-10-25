"""Selective startup: real isolated SQLite/API and synthetic cold-boot proofs only."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import socket
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import select
from server import models as m,role_startup as startup
from scripts import role_service_recovery as local
from tests.test_role_services import RoleServiceTestCase,PROJECT_ID,OTHER_PROJECT_ID,HOST
from tests.test_project_roles import encode

ACTIVATION='a'*32

class ProjectStartupTests(RoleServiceTestCase):
    def setUp(self):
        super().setUp()
        self.cutoff=datetime.now(timezone.utc)-timedelta(seconds=10)
        self.health={'pid':123,'activation_id':ACTIVATION,'started_at':(startup._now()+timedelta(hours=1)).isoformat()}
        self.config={'hosts':[]}
        self.coldtemp=tempfile.TemporaryDirectory();self.addCleanup(self.coldtemp.cleanup)
        p=patch.object(startup,'verified_runtime',side_effect=lambda *a:(self.config,self.health,self.cutoff))
        p.start();self.addCleanup(p.stop)

    def preference(self,enabled,**kwargs):
        with self.make_client() as client:
            return client.put(f'/api/projects/{kwargs.get("project",PROJECT_ID)}/roles/{encode(kwargs.get("member",self.role_a))}/startup',
                headers={'X-API-Key':kwargs.get('key','bobo-key')},json={'enabled':enabled})

    def activate(self,activation=ACTIVATION,key='bobo-key',**extra):
        with self.make_client() as client:
            return client.post(f'/api/projects/{PROJECT_ID}/role-services/startup',
                headers={'X-API-Key':key},json={'activation_id':activation,**extra})

    def result(self,**kwargs):
        response=self.activate(**kwargs)
        self.assertEqual(response.status_code,200,response.text)
        return next(r for r in response.json()['results'] if r['member_id']==self.role_a)

    def test_default_false_persist_idempotent_and_reads_do_not_start(self):
        role=next(r for r in self.get_roles().json() if r['member_id']==self.role_a)
        self.assertEqual(role['startup']['enabled'],False)
        self.assertEqual(role['startup']['revision'],0)
        self.assertEqual(self.preference(False).json()['revision'],0)
        first=self.preference(True).json();second=self.preference(True).json()
        self.assertEqual(first,second)
        self.assertEqual(self.launch_rows(),[])
        self.assertTrue(next(r for r in self.get_roles().json() if r['member_id']==self.role_a)['startup']['enabled'])
        self.assertEqual(self.preference(False).json()['revision'],2)
        self.assertEqual(self.launch_rows(),[])

    def test_human_only_strict_boolean_no_caller_evidence_and_project_isolation(self):
        self.assertEqual(self.preference(True,key=self.role_a_key).status_code,403)
        self.assertEqual(self.activate(key=self.role_a_key).status_code,403)
        for value in (1,'true',None,[]):self.assertEqual(self.preference(value).status_code,422)
        self.assertEqual(self.activate(pid=1).status_code,422)
        self.assertEqual(self.activate(activation='../wrong').status_code,422)
        self.register_project(OTHER_PROJECT_ID)
        self.assertEqual(self.preference(True,project=OTHER_PROJECT_ID).status_code,404)

    def test_selected_enqueues_once_and_manual_stop_is_not_reversed(self):
        self.preference(True)
        first=self.result();self.assertEqual(first['status'],'enqueued')
        state=self.state_row();launch_id=state.current_launch_id
        self.assertEqual(self.stop().status_code,200)
        stopped=self.state_row();self.assertEqual(stopped.observed_state,'stopped')
        self.assertEqual(self.result()['launch_id'],launch_id)
        self.assertEqual(self.state_row().model_dump(),stopped.model_dump())
        self.assertEqual(len(self.launch_rows()),1)
        new=self.result(activation='b'*32)
        self.assertEqual(new['status'],'enqueued');self.assertNotEqual(new['launch_id'],launch_id)
        self.assertNotEqual(self.launch_row(new['launch_id']).expected_instance_id,self.launch_row(launch_id).expected_instance_id)

    def test_unselected_never_starts_and_empty_cycle_does_not_expand_later(self):
        self.assertEqual(self.result()['status'],'not_selected')
        self.preference(True)
        self.assertEqual(self.result()['status'],'not_selected')
        self.assertEqual(self.launch_rows(),[])
        with self.session() as session:
            session.delete(session.get(m.ProjectAgent,(PROJECT_ID,self.role_a)));session.commit()
        self.assertTrue(self.activate(activation='c'*32).json()['complete'])
        with self.session() as session:
            session.add(m.ProjectAgent(project_id=PROJECT_ID,member_id=self.role_a));session.commit()
        self.assertEqual(self.activate(activation='c'*32).json()['results'],[])

    def snapshot(self):
        with self.session() as session:
            startup._snapshot(PROJECT_ID,ACTIVATION,session.get(m.Member,'human:bobo'),session,self.health)

    def test_manual_generation_and_choice_changes_win_over_saved_snapshot(self):
        self.preference(True);self.snapshot();self.preference(False)
        self.assertEqual(self.result()['error_code'],'startup_choice_changed')
        self.assertEqual(self.launch_rows(),[])
        self.snapshot_new('d'*32)
        self.assertEqual(self.start().status_code,200)
        self.assertEqual(self.result(activation='d'*32)['error_code'],'startup_manual_intent_present')
        self.assertEqual(len(self.launch_rows()),1)

    def snapshot_new(self,activation):
        with self.session() as session:
            startup._snapshot(PROJECT_ID,activation,session.get(m.Member,'human:bobo'),session,self.health)

    def test_fresh_ready_service_never_duplicates_even_when_unselected(self):
        launch,claim=self.start_and_claim();self.bind_instance(launch,claim)
        self.assertEqual(self.ready_report(launch,claim,process_started_at=startup._now().isoformat()).status_code,200)
        self.assertEqual(self.result()['status'],'already_running')
        self.assertEqual(len(self.launch_rows()),1)

    def test_current_boot_unclaimed_intent_stays_under_manual_control(self):
        self.start()
        self.assertEqual(self.result()['error_code'],'startup_existing_intent')
        self.assertEqual(self.state_row().observed_state,'starting')

    def test_manual_stop_or_choice_before_first_snapshot_also_wins(self):
        self.preference(True);self.start()
        self.health['started_at']=startup._now().isoformat()
        self.stop()
        self.assertEqual(self.result()['error_code'],'startup_manual_intent_present')
        self.assertEqual(self.state_row().observed_state,'stopped')
        self.preference(False)
        self.assertEqual(self.result(activation='f'*32)['error_code'],'startup_choice_changed')

    def test_unclaimed_preboot_intent_converges_to_stopped_when_unselected(self):
        launch=self.start().json()
        with self.session() as session:
            row=session.get(m.RoleServiceLaunch,launch['launch_id']);row.created_at=self.cutoff-timedelta(seconds=3)
            session.add(row);session.commit()
        self.assertEqual(self.result()['status'],'not_selected')
        self.assertEqual(self.state_row().observed_state,'stopped')
        self.assertEqual(self.launch_row(launch['launch_id']).state,'expired')

    def test_preboot_expired_unclaimed_start_converges_but_unknown_stop_does_not(self):
        launch=self.start().json()
        with self.session() as session:
            row=session.get(m.RoleServiceLaunch,launch['launch_id']);row.created_at=self.cutoff-timedelta(seconds=3)
            row.state='expired';session.add(row)
            state=session.get(m.RoleServiceState,(PROJECT_ID,self.role_a));state.observed_state='failed';session.add(state);session.commit()
        self.assertEqual(self.result()['status'],'not_selected');self.assertEqual(self.state_row().observed_state,'stopped')
        self.preference(True)
        with self.session() as session:
            state=session.get(m.RoleServiceState,(PROJECT_ID,self.role_a));state.observed_state='stopping';session.add(state);session.commit()
        self.assertEqual(self.result(activation='b'*32)['error_code'],'startup_recovery_required')
        self.assertEqual(len(self.launch_rows()),1)

    def test_role_archived_between_preboot_stop_commit_and_enqueue_is_revalidated(self):
        self.preference(True);launch=self.start().json()
        with self.session() as session:
            row=session.get(m.RoleServiceLaunch,launch['launch_id']);row.created_at=self.cutoff-timedelta(seconds=3)
            session.add(row);session.commit()
        original=startup._idempotent_stopped
        def archive_after_stop(*args,**kwargs):
            response=original(*args,**kwargs)
            with self.session() as session:
                role=session.get(m.ProjectRole,(PROJECT_ID,self.role_a));role.archived_at=startup._now()
                session.add(role);session.commit()
            return response
        with patch.object(startup,'_idempotent_stopped',side_effect=archive_after_stop):
            self.assertEqual(self.result()['status'],'failed')
        self.assertEqual(self.state_row().observed_state,'stopped');self.assertEqual(len(self.launch_rows()),1)

    def test_claim_lease_reentry_expiry_and_late_writer_conflict(self):
        self.preference(True);self.snapshot();key=(PROJECT_ID,ACTIVATION,self.role_a)
        with self.session() as session:
            first=startup._claim(key,session);self.assertIsNone(startup._claim(key,session))
            row=session.get(m.RoleStartupActivation,key);row.lease_expires_at=startup._now()-timedelta(seconds=1)
            session.add(row);session.commit();second=startup._claim(key,session)
            self.assertNotEqual(first,second)
            with self.assertRaises(HTTPException):startup._locked_entry(key,first,session)
            startup._apply(key,second,session.get(m.Member,'human:bobo'),session)
        self.assertEqual(self.result()['status'],'enqueued');self.assertEqual(len(self.launch_rows()),1)

    def test_failed_launch_insert_rolls_back_generation_and_receipt(self):
        self.preference(True)
        with self.session() as session:
            session.exec(text("CREATE TRIGGER fail_startup BEFORE INSERT ON role_service_launches BEGIN SELECT RAISE(ABORT,'fixture'); END"));session.commit()
        self.assertEqual(self.result()['status'],'failed')
        self.assertEqual(self.launch_rows(),[]);self.assertIsNone(self.state_row())

    def test_archived_disabled_removed_and_binding_change_do_not_start(self):
        self.preference(True)
        with self.session() as session:
            role=session.get(m.ProjectRole,(PROJECT_ID,self.role_a));role.archived_at=startup._now();session.add(role);session.commit()
        self.assertEqual(self.result()['status'],'failed');self.assertEqual(self.launch_rows(),[])

    def test_disabled_and_changed_control_kind_remain_blocked(self):
        self.preference(True)
        with self.session() as session:
            member=session.get(m.Member,self.role_a);member.disabled_at=startup._now();session.add(member);session.commit()
        self.assertEqual(self.result()['status'],'failed')
        with self.session() as session:
            member=session.get(m.Member,self.role_a);member.disabled_at=None;session.add(member)
            binding=session.get(m.ProjectRoleBinding,(PROJECT_ID,self.role_a))
            runner=session.get(m.RunnerRegistry,binding.runner_id);runner.control_kind='unknown';session.add(runner);session.commit()
        self.assertEqual(self.result(activation='b'*32)['status'],'failed');self.assertEqual(self.launch_rows(),[])

    def test_deletion_clears_preference_and_snapshot_cannot_resurrect_role(self):
        self.preference(True);self.snapshot()
        with patch('server.role_deletions._cleanup_binding_digest',return_value=None),self.make_client() as client:
            response=client.post(f'/api/projects/{PROJECT_ID}/roles/{encode(self.role_a)}/delete',
                headers={'X-API-Key':'bobo-key'},json={'confirm_member_id':self.role_a})
        self.assertEqual(response.status_code,200,response.text)
        with self.session() as session:self.assertIsNone(session.get(m.ProjectRoleStartup,(PROJECT_ID,self.role_a)))
        self.assertEqual(self.result()['status'],'skipped');self.assertEqual(self.launch_rows(),[])

    def test_two_real_connections_only_enqueue_one_launch(self):
        self.preference(True);barrier=threading.Barrier(2)
        def run():
            with self.session() as session:
                operator=session.get(m.Member,'human:bobo');barrier.wait(3)
                return startup.activate(PROJECT_ID,ACTIVATION,operator,session)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(self.result()['status'],'enqueued');self.assertEqual(len(self.launch_rows()),1)
        self.assertTrue(any(r['complete'] for r in results))

    def cold(self,selected=False,*,seen_seconds=20):
        self.preference(selected)
        launch,claim=self.start_and_claim(host=socket.gethostname())
        self.bind_instance(launch,claim,host=socket.gethostname())
        self.assertEqual(self.ready_report(launch,claim,host=socket.gethostname()).status_code,200)
        old=startup._now()-timedelta(seconds=seen_seconds)
        with self.session() as session:
            row=session.get(m.RoleServiceLaunch,launch['launch_id']);row.created_at=old;session.add(row)
            state=session.get(m.RoleServiceState,(PROJECT_ID,self.role_a));state.process_started_at=old;session.add(state)
            instance=session.get(m.AgentInstance,claim['expected_instance_id']);instance.last_seen_at=old;session.add(instance);session.commit()
        root=Path(self.coldtemp.name)/'cold-startup';root.mkdir(exist_ok=True)
        health=root/'manager.json';entry=root/'host.py';entry.write_text('# isolated fixture',encoding='utf8')
        health.write_text(json.dumps({'project_id':PROJECT_ID,'member_id':self.role_a,'pid':321,'seen_at':old.isoformat()}),encoding='utf8')
        self.config={'hosts':[{'member_id':self.role_a,'health_file':str(health),'argv':['python',str(entry)]}]}
        return launch,claim,health

    def cold_probes(self):
        # Only synthetic PID inventory and synthetic boot epoch; exercise real local_proof.
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch.object(local,'recorded_process_state',return_value='previous_boot'))
        stack.enter_context(patch.object(local,'process_inventory',return_value=[]))
        return stack

    def test_fast_reboot_selected_recovers_and_enqueues_fresh_instance_atomically(self):
        launch,claim,_=self.cold(True)
        # Public projection may still call the <90s old DB heartbeat ready. A real
        # previous-boot identity must take precedence over that freshness label.
        with self.cold_probes():result=self.result()
        self.assertEqual(result['status'],'enqueued',result)
        state=self.state_row();self.assertEqual(state.generation,launch['generation']+2)
        self.assertNotEqual(state.current_launch_id,launch['launch_id'])
        with self.session() as session:
            row=session.get(m.RoleStartupActivation,(PROJECT_ID,ACTIVATION,self.role_a))
            self.assertIsNotNone(row.recovery_id)
            self.assertEqual(session.get(m.AgentInstance,claim['expected_instance_id']).status,'offline')

    def test_fast_reboot_unselected_is_stopped_and_paused_root_is_unchanged(self):
        self.cold(False)
        with self.session() as session:
            task=m.AgentTask(project_id=PROJECT_ID,target_member_id=self.role_a,created_by='human:bobo',content='paused',status='queued',control_status='paused')
            session.add(task);session.flush();task.root_task_id=task.id;session.add(task);session.commit();session.refresh(task)
            taskid=task.id;before=task.model_dump()
        # Initialize legacy task defaults before comparing startup's own write effects.
        with self.make_client():pass
        with self.session() as session:before=session.get(m.AgentTask,taskid).model_dump()
        with self.cold_probes():result=self.result()
        self.assertEqual(result['status'],'not_selected',result)
        self.assertEqual(self.state_row().observed_state,'stopped')
        with self.session() as session:self.assertEqual(session.get(m.AgentTask,taskid).model_dump(),before)

    def test_current_boot_or_unknown_process_or_active_task_never_recovers(self):
        self.cold(True,seen_seconds=120)
        with patch.object(local,'recorded_process_state',return_value='unknown'),patch.object(local,'process_inventory',return_value=[]):
            self.assertEqual(self.result()['error_code'],'recovery_process_not_absent')
        self.assertTrue(self.state_row().process_launch_id)

        with self.session() as session:
            task=m.AgentTask(project_id=PROJECT_ID,target_member_id=self.role_a,created_by='human:bobo',content='active',status='running')
            session.add(task);session.commit();session.refresh(task);taskid=task.id
        with self.cold_probes():self.assertEqual(self.result(activation='e'*32)['error_code'],'recovery_tasks_active')
        with self.session() as session:
            session.delete(session.get(m.AgentTask,taskid))
            state=session.get(m.RoleServiceState,(PROJECT_ID,self.role_a));state.process_started_at=startup._now();state.observed_state='unknown'
            session.add(state);session.commit()
        with self.cold_probes():self.assertEqual(self.result(activation='f'*32)['error_code'],'recovery_not_previous_boot')

    def test_terminal_task_residual_claim_and_wrong_instance_host_block_cold_recovery(self):
        _,claim,_=self.cold(True,seen_seconds=120)
        with self.session() as session:
            task=m.AgentTask(project_id=PROJECT_ID,target_member_id=self.role_a,created_by='human:bobo',content='residual',status='failed',workflow_status='failed',claim_token='synthetic-residual')
            session.add(task);session.commit();session.refresh(task);taskid=task.id
        with self.cold_probes():self.assertEqual(self.result()['error_code'],'recovery_tasks_active')
        with self.session() as session:
            session.delete(session.get(m.AgentTask,taskid))
            instance=session.get(m.AgentInstance,claim['expected_instance_id']);instance.host='other-host';session.add(instance);session.commit()
        with self.cold_probes():self.assertEqual(self.result(activation='b'*32)['error_code'],'recovery_identity_mismatch')
        self.assertTrue(self.state_row().process_launch_id)

    def test_recovery_commit_is_replay_safe_after_api_interruption(self):
        self.cold(True,seen_seconds=120);self.snapshot();key=(PROJECT_ID,ACTIVATION,self.role_a)
        with self.session() as session,self.cold_probes():
            digest=startup._claim(key,session)
            startup._cold_recover(key,digest,session.get(m.Member,'human:bobo'),session,self.config,self.cutoff)
            row=session.get(m.RoleStartupActivation,key);row.lease_expires_at=startup._now()-timedelta(seconds=1)
            session.add(row);session.commit()
        self.assertEqual(self.result()['status'],'enqueued')
        with self.session() as session:self.assertEqual(len(session.exec(select(m.RoleServiceRecovery)).all()),1)

    def test_preboot_heartbeat_exception_is_not_exposed_to_public_manual_recovery(self):
        self.cold(False)
        with self.make_client() as client:
            response=client.get(f'/api/projects/{PROJECT_ID}/roles/{encode(self.role_a)}/service/recovery-plan',headers={'X-API-Key':'bobo-key'})
        self.assertEqual(response.json()['detail'],'recovery_recent_heartbeat')

    def test_ready_requires_process_start_time_and_known_boot(self):
        _,claim,_=self.cold(True)
        with self.session() as session:
            state=session.get(m.RoleServiceState,(PROJECT_ID,self.role_a));state.process_started_at=None
            session.add(state);session.commit()
        self.assertEqual(self.result()['error_code'],'recovery_identity_mismatch')
        self.assertTrue(self.state_row().process_launch_id)
        self.assertEqual(len(self.launch_rows()),1)
        self.cutoff=None
        self.assertEqual(self.result(activation='d'*32)['error_code'],'startup_boot_unverified')
        self.assertTrue(self.state_row().process_launch_id)

    def test_runtime_invalidation_after_expiry_scan_prevents_enqueue(self):
        self.preference(True);valid={'value':True};original=startup.expire_due_launches
        def verify(*args):
            if not valid['value']:raise HTTPException(409,'startup_runtime_unverified')
            return self.config,self.health,self.cutoff
        def expire(*args,**kwargs):
            result=original(*args,**kwargs);valid['value']=False;return result
        with patch.object(startup,'verified_runtime',side_effect=verify),patch.object(startup,'expire_due_launches',side_effect=expire):
            result=self.result()
        self.assertEqual((result['status'],result['error_code']),('failed','startup_runtime_unverified'))
        self.assertEqual(self.launch_rows(),[]);self.assertIsNone(self.state_row())

    def test_runtime_invalidation_after_enqueue_rolls_back_launch_and_generation(self):
        self.preference(True);valid={'value':True};original=startup._enqueue_start_launch
        def verify(*args):
            if not valid['value']:raise HTTPException(409,'startup_runtime_unverified')
            return self.config,self.health,self.cutoff
        def enqueue(*args,**kwargs):
            result=original(*args,**kwargs);valid['value']=False;return result
        with patch.object(startup,'verified_runtime',side_effect=verify),patch.object(startup,'_enqueue_start_launch',side_effect=enqueue):
            result=self.result()
        self.assertEqual((result['status'],result['error_code']),('failed','startup_runtime_unverified'))
        self.assertEqual(self.launch_rows(),[]);self.assertIsNone(self.state_row())

    def test_runtime_invalidation_also_rolls_back_preboot_stop(self):
        launch=self.start().json()
        with self.session() as session:
            row=session.get(m.RoleServiceLaunch,launch['launch_id']);row.created_at=self.cutoff-timedelta(seconds=3)
            session.add(row);session.commit()
        original=startup.expire_due_launches;valid={'value':True};before=self.state_row().model_dump()
        def verify(*args):
            if not valid['value']:raise HTTPException(409,'startup_runtime_unverified')
            return self.config,self.health,self.cutoff
        def expire(*args,**kwargs):
            result=original(*args,**kwargs);valid['value']=False;return result
        with patch.object(startup,'verified_runtime',side_effect=verify),patch.object(startup,'expire_due_launches',side_effect=expire):
            self.assertEqual(self.result()['error_code'],'startup_runtime_unverified')
        self.assertEqual(self.state_row().model_dump(),before)
        self.assertEqual(self.launch_row(launch['launch_id']).state,'pending')
