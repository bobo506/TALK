"""Synthetic runtime health, bounded async HTTP, and strict local boot proof."""
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch
from fastapi import HTTPException
from server import role_startup
from scripts import talk_runtime as runtime,role_service_recovery as recovery

class StartupRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.private=self.root/'runtime';self.private.mkdir()
        self.client=Mock();self.now=0
        self.runtime=runtime.TalkRuntime({'project_id':'p','project_root':str(self.root),'state_dir':str(self.root)},
            client=self.client,attach_api=True,clock=lambda:self.now)

    def test_startup_io_keeps_health_responsive_and_does_not_overlap_or_replay(self):
        started=threading.Event();done=threading.Event()
        def request(*args):
            started.set();done.wait(2)
            return {'activation_id':self.runtime.activation_id,'complete':True}
        self.client.request.side_effect=request
        self.runtime.startup_tick();self.assertTrue(started.wait(1));self.runtime.startup_tick()
        before=time.monotonic();self.runtime.health();self.assertLess(time.monotonic()-before,1)
        health=json.loads((self.private/'health.json').read_text())
        self.assertTrue(health['worker_in_flight']);self.assertEqual(health['activation_id'],self.runtime.activation_id)
        self.assertEqual(health['project_id'],'p')
        done.set();self.runtime.startup_thread.join(1);self.runtime.startup_tick()
        self.assertEqual(self.client.request.call_count,1);self.assertEqual(self.runtime.startup_state,'complete')

    def test_failures_have_eight_round_bound_and_stable_generation(self):
        self.client.request.side_effect=RuntimeError('fixture-secret')
        for _ in range(8):
            self.runtime.startup_tick();self.runtime.startup_thread.join(1);self.now=self.runtime.startup_next
        self.runtime.startup_tick();self.runtime.health()
        value=json.loads((self.private/'health.json').read_text())
        self.assertEqual(value['startup_state'],'failed');self.assertEqual(value['startup_attempts'],8)
        self.assertNotIn('fixture-secret',json.dumps(value))
        calls=self.client.request.call_args_list
        self.assertEqual(len(calls),8);self.assertEqual(len({c.args[2]['activation_id'] for c in calls}),1)
        self.assertEqual(self.runtime.hosts,{})

    def test_live_api_lease_wait_is_respected_without_busy_retry(self):
        self.client.request.return_value={'activation_id':self.runtime.activation_id,'complete':False,'retry_after_seconds':119}
        self.runtime.startup_tick();self.runtime.startup_thread.join(1)
        self.assertEqual(self.runtime.startup_next,119)
        self.now=118;self.runtime.startup_tick();self.assertEqual(self.client.request.call_count,1)
        self.now=119;self.runtime.startup_tick();self.runtime.startup_thread.join(1)
        self.assertEqual(self.client.request.call_count,2)

    def test_stop_publishes_stopping_before_waiting_and_prevents_another_round(self):
        done=threading.Event();started=threading.Event()
        def request(*args):started.set();done.wait(2);return {}
        self.client.request.side_effect=request
        self.runtime.startup_tick();self.assertTrue(started.wait(1))
        def release():
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                try:
                    health=json.loads((self.private/'health.json').read_text())
                    if health['stopping']:done.set();return
                except (OSError,ValueError):pass
                time.sleep(.01)
        thread=threading.Thread(target=release);thread.start()
        self.runtime.stop();thread.join(1);self.runtime.startup_tick()
        self.assertTrue(done.is_set())
        self.assertEqual(len([c for c in self.client.request.call_args_list if c.args[0]=='POST']),1)
        self.assertEqual(json.loads((self.private/'health.json').read_text())['state'],'stopped')

    def test_serve_keeps_publishing_health_and_gates_hosts_and_worker_until_startup_finishes(self):
        key=self.root/'fixture.key';key.write_text('synthetic-human')
        self.runtime.config.update(operator_key_file=str(key),base_url='http://isolated.invalid',provision_worker=False)
        done=threading.Event();started=threading.Event();ticks=[]
        def request(method,path,body=None):
            if path=='/api/members/me':return {'kind':'human'}
            if path.endswith('/role-services/startup'):
                started.set();done.wait(2)
                return {'activation_id':self.runtime.activation_id,'complete':True}
            return []
        self.client.request.side_effect=request
        self.runtime.reconcile_hosts=Mock();self.runtime.reconcile_deletions=Mock();self.runtime.worker_tick=Mock()
        def sleep(_):
            ticks.append(1)
            if len(ticks)==3:
                self.assertTrue(started.is_set())
                self.runtime.reconcile_hosts.assert_not_called();self.runtime.worker_tick.assert_not_called()
                health=json.loads((self.private/'health.json').read_text());self.assertEqual(health['state'],'running')
                done.set()
            if self.runtime.reconcile_hosts.call_count:self.runtime.stopping=True
            if len(ticks)>100:raise AssertionError('fixture did not complete')
            time.sleep(.01)
        self.runtime.sleep=sleep
        self.runtime._serve()
        self.assertTrue(done.is_set());self.runtime.reconcile_hosts.assert_called_once()

    def test_verified_runtime_rejects_mismatch_stale_stopping_failed_or_unknown_pid(self):
        session=Mock();now=datetime.now(timezone.utc)
        health={'schema':'talk-runtime-health-1','project_id':'p','pid':os.getpid(),
            'activation_id':'a'*32,'started_at':(now-timedelta(seconds=2)).isoformat(),
            'seen_at':now.isoformat(),'state':'running','stopping':False,'startup_state':'processing'}
        path=self.private/'health.json'
        with patch('server.local_runtime.configured_runtime',return_value=(self.root/'config.json',{'project_id':'p','state_dir':str(self.root)})),\
             patch.object(recovery,'recorded_process_state',return_value='present') as probe,\
             patch.object(recovery,'system_boot_time',return_value=now.timestamp()-1):
            path.write_text(json.dumps(health));self.assertEqual(role_startup.verified_runtime('p','a'*32,session)[1]['pid'],os.getpid())
            for change in ({'activation_id':'b'*32},{'project_id':'other'},{'seen_at':(now-timedelta(seconds=40)).isoformat()},
                           {'stopping':True},{'state':'stopped'},{'startup_state':'failed'},{'pid':True}):
                path.write_text(json.dumps({**health,**change}))
                with self.assertRaises(HTTPException):role_startup.verified_runtime('p','a'*32,session)
            path.write_text(json.dumps(health));probe.return_value='unknown'
            with self.assertRaises(HTTPException):role_startup.verified_runtime('p','a'*32,session)
        with patch('server.local_runtime.configured_runtime',return_value=None):
            with self.assertRaises(HTTPException):role_startup.verified_runtime('p','a'*32,session)

    def test_fast_preboot_proof_retains_pid_identity_inventory_and_health_guards(self):
        import socket
        now=datetime.now(timezone.utc);cutoff=now-timedelta(seconds=5)
        health=self.root/'manager.json';entry=self.root/'host.py';entry.write_text('# fixture')
        record={'project_id':'p','member_id':'agent:x','pid':321,'seen_at':(now-timedelta(seconds=10)).isoformat()}
        plan={'project_id':'p','member_id':'agent:x','expected_owner_host':socket.gethostname(),
            'expected_instance_id':'old-instance','expected_process_launch_id':'old-launch','process_pid':123,
            'instance_last_seen_at':record['seen_at']}
        health.write_text(json.dumps(record))
        with patch.object(recovery,'recorded_process_state',return_value='previous_boot') as probe:
            proof=recovery.local_proof(plan,health,entry,inventory=lambda:[],_preboot_at=cutoff)
            self.assertTrue(proof['both_stopped'])
            with self.assertRaises(recovery.HostError):recovery.local_proof(plan,health,entry,inventory=lambda:[])
            probe.return_value='unknown'
            with self.assertRaises(recovery.HostError):recovery.local_proof(plan,health,entry,inventory=lambda:[],_preboot_at=cutoff)
            probe.return_value='previous_boot'
            with self.assertRaises(recovery.HostError):recovery.local_proof(plan,health,entry,inventory=lambda:[{'CommandLine':None}],_preboot_at=cutoff)
            record['seen_at']=now.isoformat();health.write_text(json.dumps(record))
            with self.assertRaises(recovery.HostError):recovery.local_proof(plan,health,entry,inventory=lambda:[],_preboot_at=cutoff)
