"""Selective startup: real isolated SQLite/API and synthetic cold-boot proofs only."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import select
from server import models as m,role_startup as startup
from scripts import role_service_recovery as local
from tests.test_role_services import RoleServiceTestCase,PROJECT_ID,OTHER_PROJECT_ID,HOST,RUNNER_ID
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

    def bind_cdp(self):
        with self.session() as session:
            binding=session.get(m.ProjectRoleBinding,(PROJECT_ID,self.role_a))
            binding.connection_ref='native-workbuddy-cdp';binding.model_alias='workbuddy-cdp:model'
            session.add(binding);session.commit()

    def test_cdp_unavailable_does_not_block_other_role(self):
        created=self.create_role(PROJECT_ID,role_name='second',choice_id=self.choice_id,operation_key='op-second-0001')
        self.assertEqual(created.status_code,201,created.text)
        other=created.json()['member_id']
        with self.session() as session:
            role=session.get(m.ProjectRole,(PROJECT_ID,other));role.storage_layout='legacy';session.add(role);session.commit()
        self.bind_cdp();self.preference(True);self.preference(True,member=other)
        with patch('server.role_services.cdp_endpoint_available',return_value=False) as probe:
            response=self.activate()
        self.assertEqual(response.status_code,200,response.text)
        results={row['member_id']:row for row in response.json()['results']}
        self.assertEqual((results[self.role_a]['status'],results[self.role_a]['error_code']),('failed','workbuddy_cdp_unavailable'))
        self.assertEqual(results[other]['status'],'enqueued')
        self.assertIsNone(self.state_row());self.assertEqual(self.launch_rows(),[])
        self.assertEqual(len(self.launch_rows(other)),1);probe.assert_called_once_with()

    def test_cdp_available_project_startup_enqueues(self):
        self.bind_cdp();self.preference(True)
        with patch('server.role_services.cdp_endpoint_available',return_value=True) as probe:
            result=self.result()
        self.assertEqual(result['status'],'enqueued');self.assertEqual(len(self.launch_rows()),1)
        probe.assert_called_once_with()

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

    def cold_dynamic(self,runtime,*,seen_seconds=20):
        """Reproduce a preboot owner whose runner is a dynamic Kimi/Codex/WorkBuddy host."""
        from scripts.role_service_host import _sanitize_token
        self.preference(True)
        launch,claim=self.start_and_claim(host=socket.gethostname())
        self.bind_instance(launch,claim,host=socket.gethostname())
        self.assertEqual(self.ready_report(launch,claim,host=socket.gethostname()).status_code,200)
        old=startup._now()-timedelta(seconds=seen_seconds)
        with self.session() as session:
            row=session.get(m.RoleServiceLaunch,launch['launch_id']);row.created_at=old;session.add(row)
            state=session.get(m.RoleServiceState,(PROJECT_ID,self.role_a));state.process_started_at=old;session.add(state)
            instance=session.get(m.AgentInstance,claim['expected_instance_id'])
            instance.last_seen_at=old;instance.runtime=runtime;session.add(instance)
            runner=session.get(m.RunnerRegistry,RUNNER_ID);runner.runtime=runtime;session.add(runner);session.commit()
        directory={'kimi-code':'kimi-dynamic','codex':'codex-dynamic','workbuddy':'workbuddy-native'}[runtime]
        root=Path(self.coldtemp.name)/('dynamic-'+directory);root.mkdir(parents=True,exist_ok=True)
        health=(root/directory/_sanitize_token(PROJECT_ID)/_sanitize_token(self.role_a)
                /'manager-health.json')
        health.parent.mkdir(parents=True,exist_ok=True)
        health.write_text(json.dumps({'schema':'talk-dynamic-manager-health-1',
            'project_id':PROJECT_ID,'member_id':self.role_a,'pid':321,
            'seen_at':old.isoformat()}),encoding='utf8')
        # Keep workbuddy present for Kimi/Codex: config existence alone is not identity.
        self.config={'project_id':PROJECT_ID,'state_dir':str(root),'hosts':[],
                     'workbuddy':{'executable':'unused','models_home':'unused'}}
        if runtime=='kimi-code':
            self.config['kimi']={'enabled':True}
        elif runtime=='codex':
            self.config['codex']={'enabled':True,'executable':'unused'}
        self.launch,self.claim,self.dynamic_health=launch,claim,health
        return launch,claim,health

    def cold_probes(self):
        # Only synthetic PID inventory and synthetic boot epoch; exercise real local_proof.
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch.object(local,'recorded_process_state',return_value='previous_boot'))
        stack.enter_context(patch.object(local,'process_inventory',return_value=[]))
        return stack

    def real_dynamic_command(self, module, serve=False, member=None):
        parts = ['python', '-B', '-X', 'utf8', '-m', f'scripts.{module}']
        if serve:
            parts.append('serve')
        parts += ['--project', PROJECT_ID, '--member', member or self.role_a,
                  '--project-root', r'C:\fixture\project',
                  '--state-dir', r'C:\fixture\state',
                  '--base-url', 'http://127.0.0.1:9']
        return subprocess.list2cmdline(parts)

    def assert_real_cold_replacement_refused(self, runtime, module, serve=False):
        launch, claim, _ = self.cold_dynamic(runtime)
        command = self.real_dynamic_command(module, serve)
        with self.cold_probes() as stack:
            stack.enter_context(patch.object(local, 'process_inventory',
                return_value=[{'CommandLine': command}]))
            result = self.result()
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['error_code'], 'recovery_replacement_process_present')
        self.assertTrue(self.state_row().process_launch_id)
        self.assertEqual(len(self.launch_rows()), 1)
        self.assertEqual(self.launch_rows()[0].launch_id, launch['launch_id'])

    def test_real_dynamic_kimi_module_replacement_is_refused(self):
        self.assert_real_cold_replacement_refused('kimi-code', 'kimi_role_host')

    def test_real_dynamic_codex_module_replacement_is_refused(self):
        self.assert_real_cold_replacement_refused('codex', 'codex_role_host')

    def test_real_dynamic_workbuddy_module_replacement_is_refused(self):
        self.assert_real_cold_replacement_refused('workbuddy', 'workbuddy_role_host', serve=True)

    def test_real_dynamic_host_for_other_member_does_not_block(self):
        self.cold_dynamic('kimi-code')
        command = self.real_dynamic_command('kimi_role_host', member='agent:other')
        with self.cold_probes() as stack:
            stack.enter_context(patch.object(local, 'process_inventory',
                return_value=[{'CommandLine': command}]))
            result = self.result()
        self.assertEqual(result['status'], 'enqueued', result)
        self.assertNotEqual(self.state_row().current_launch_id, self.launch['launch_id'])

    def test_real_dynamic_host_with_incomplete_identity_is_unknown(self):
        self.cold_dynamic('kimi-code')
        with self.cold_probes() as stack:
            stack.enter_context(patch.object(local, 'process_inventory',
                return_value=[{'CommandLine': 'python -m scripts.kimi_role_host'}]))
            result = self.result()
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['error_code'], 'recovery_process_inventory_unknown')
        self.assertTrue(self.state_row().process_launch_id)

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

    def test_dynamic_kimi_preboot_recovers_and_enqueues(self):
        launch,claim,_=self.cold_dynamic('kimi-code')
        with self.cold_probes():result=self.result()
        self.assertEqual(result['status'],'enqueued',result)
        state=self.state_row();self.assertEqual(state.generation,launch['generation']+2)
        self.assertNotEqual(state.current_launch_id,launch['launch_id'])

    def test_dynamic_codex_preboot_recovers_and_enqueues(self):
        launch,claim,_=self.cold_dynamic('codex')
        with self.cold_probes():result=self.result()
        self.assertEqual(result['status'],'enqueued',result)
        state=self.state_row();self.assertEqual(state.generation,launch['generation']+2)
        self.assertNotEqual(state.current_launch_id,launch['launch_id'])

    def test_dynamic_workbuddy_preboot_recovers_and_enqueues(self):
        launch,claim,_=self.cold_dynamic('workbuddy')
        with self.cold_probes():result=self.result()
        self.assertEqual(result['status'],'enqueued',result)
        state=self.state_row();self.assertEqual(state.generation,launch['generation']+2)
        self.assertNotEqual(state.current_launch_id,launch['launch_id'])

    def test_dynamic_unknown_runner_never_falls_back_to_workbuddy(self):
        self.cold_dynamic('kimi-code')
        with self.session() as session:
            instance=session.get(m.AgentInstance,self.claim['expected_instance_id'])
            instance.runtime='mystery';session.add(instance)
            runner=session.get(m.RunnerRegistry,RUNNER_ID);runner.runtime='mystery';session.add(runner)
            session.commit()
        with self.cold_probes():result=self.result()
        self.assertEqual(result['error_code'],'local_recovery_runner_unsupported')
        self.assertTrue(self.state_row().process_launch_id)
        self.assertEqual(len(self.launch_rows()),1)

    def test_dynamic_binding_change_cannot_use_new_runner_for_old_owner(self):
        self.cold_dynamic('kimi-code')
        with self.session() as session:
            runner=session.get(m.RunnerRegistry,RUNNER_ID);runner.runtime='workbuddy';session.add(runner)
            session.commit()
        with self.cold_probes():result=self.result()
        self.assertEqual(result['error_code'],'local_recovery_binding_changed')
        self.assertTrue(self.state_row().process_launch_id)

    def test_dynamic_missing_health_is_unverified(self):
        self.cold_dynamic('kimi-code')
        self.dynamic_health.unlink()
        with self.cold_probes():result=self.result()
        self.assertEqual(result['error_code'],'local_recovery_unverified')
        self.assertTrue(self.state_row().process_launch_id)

    def test_dynamic_wrong_health_identity_is_refused(self):
        self.cold_dynamic('kimi-code')
        record=json.loads(self.dynamic_health.read_text(encoding='utf8'))
        record['member_id']='agent:other'
        self.dynamic_health.write_text(json.dumps(record),encoding='utf8')
        with self.cold_probes():result=self.result()
        self.assertEqual(result['error_code'],'recovery_manager_identity_mismatch')
        self.assertTrue(self.state_row().process_launch_id)

    def test_dynamic_live_manager_is_refused(self):
        from contextlib import ExitStack
        self.cold_dynamic('kimi-code')
        with ExitStack() as stack:
            stack.enter_context(self.cold_probes())
            stack.enter_context(patch.object(local,'recorded_process_state',return_value='present'))
            result=self.result()
        self.assertEqual(result['error_code'],'recovery_process_not_absent')
        self.assertTrue(self.state_row().process_launch_id)

    def test_dynamic_recent_health_is_not_previous_boot(self):
        self.cold_dynamic('kimi-code')
        record=json.loads(self.dynamic_health.read_text(encoding='utf8'))
        record['seen_at']=startup._now().isoformat()
        self.dynamic_health.write_text(json.dumps(record),encoding='utf8')
        with self.cold_probes():result=self.result()
        self.assertEqual(result['error_code'],'recovery_not_previous_boot')
        self.assertTrue(self.state_row().process_launch_id)

    def test_dynamic_replacement_process_is_refused(self):
        launch,claim,_=self.cold_dynamic('kimi-code')
        with self.cold_probes() as stack:
            stack.enter_context(patch.object(local,'process_inventory',return_value=[
                {'CommandLine':'python -m scripts.kimi_role_host --instance '
                 + claim['expected_instance_id']}]))
            result=self.result()
        self.assertEqual(result['error_code'],'recovery_replacement_process_present')
        self.assertTrue(self.state_row().process_launch_id)

    def test_fixed_host_priority_does_not_depend_on_dynamic_recipe(self):
        launch,claim,dynamic_health=self.cold_dynamic('kimi-code')
        dynamic_health.unlink()
        root=Path(self.coldtemp.name)/'fixed-priority';root.mkdir(parents=True,exist_ok=True)
        health=root/'manager.json';entry=root/'host.py'
        entry.write_text('# isolated fixed fixture',encoding='utf8')
        old=startup._now()-timedelta(seconds=20)
        health.write_text(json.dumps({'project_id':PROJECT_ID,'member_id':self.role_a,
            'pid':321,'seen_at':old.isoformat()}),encoding='utf8')
        self.config={'project_id':PROJECT_ID,'state_dir':str(Path(self.coldtemp.name)),
                     'hosts':[{'member_id':self.role_a,'health_file':str(health),
                               'argv':['python',str(entry)]}],
                     'kimi':{'enabled':True},'workbuddy':{'executable':'unused','models_home':'unused'}}
        with self.cold_probes():result=self.result()
        self.assertEqual(result['status'],'enqueued',result)
        self.assertNotEqual(self.state_row().current_launch_id,launch['launch_id'])

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
