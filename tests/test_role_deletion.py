"""Isolated HTTP deletion, fencing, history, leases and shared-identity protection."""
from datetime import datetime, timedelta, timezone
import json
import socket
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote
from sqlmodel import select
from server import models as m
from server.role_deletions import RoleDeletion, STEPS
from tests.test_project_roles import RoleApiTestCase


class RoleDeletionTests(RoleApiTestCase):
    def setUp(self):
        super().setUp()
        binding = patch("server.role_deletions._cleanup_binding_digest", return_value=None)
        binding.start();self.addCleanup(binding.stop)
        self.register_project()
        self.choice = self.seed_runner_and_choice()
        response = self.create_role("prj_alpha", role_name="delete-me", choice_id=self.choice,
                                    operation_key="op-delete-fixture", role_description="exclusive description")
        self.assertEqual(response.status_code, 201, response.text)
        self.role = response.json()
        self.member = self.role["member_id"]
        self.base = f"/api/projects/prj_alpha/roles/{quote(self.member,safe='')}"

    def call(self, suffix, body=None, *, key="bobo-key", method="POST"):
        with self.make_client() as client:
            return client.request(method, self.base+suffix, headers={"X-API-Key":key}, json=body)

    def delete(self, **kwargs):
        return self.call("/delete", {"confirm_member_id":self.member}, **kwargs)

    def claim(self, revision=1):
        response = self.call("/deletion/claim", {"revision":revision})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def report(self, receipt, *, outcome="complete", error=None, steps=None):
        if steps is None:
            steps={s:"complete" for s in STEPS}
            if outcome=="failed":steps["startup_config"]="failed"
        return self.call("/deletion/report", {"revision":receipt["revision"],"lease_token":receipt["lease_token"],
            "outcome":outcome,"steps":steps,"error_code":error})

    def test_permissions_confirmation_and_no_partial_mutation(self):
        self.assertEqual(self.delete(key="worker-key").status_code,403)
        self.assertEqual(self.call("/delete",{"confirm_member_id":"wrong"}).status_code,422)
        self.assertEqual(self.call("/delete",{}).status_code,422)
        with self.session() as session:
            self.assertIsNone(session.get(m.ProjectRole,("prj_alpha",self.member)).archived_at)

    def test_complete_deletes_config_preserves_history_and_readd_is_new_identity(self):
        message = self.add_message(from_id=self.member,to_ids='["human:bobo"]',message_type="text",content="old result")
        with self.session() as session:
            task=m.AgentTask(project_id="prj_alpha",target_member_id=self.member,created_by="human:bobo",content="old task",
                             status="succeeded",workflow_status="completed",result_message_id=message.id)
            session.add(task);session.commit();task_id=task.id
        result=self.delete();self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(result.json()["identity_disabled"])
        with self.make_client() as client:
            self.assertEqual(client.get("/api/members/me",headers={"X-API-Key":self.role["api_key"]}).status_code,401)
            agents=client.get("/api/projects/prj_alpha/agents",headers={"X-API-Key":"bobo-key"}).json()
            self.assertTrue(agents[0]["archived"])
            self.assertEqual(agents[0]["deletion"]["status"],"pending")
        receipt=self.claim()
        self.assertEqual(self.report(receipt).json()["status"],"complete")
        self.assertEqual(self.delete().json()["status"],"complete")
        with self.session() as session:
            for model in (m.ProjectAgent,m.ProjectRoleBinding,m.ProjectRoleDescription,m.ProjectRolePolicy):
                self.assertIsNone(session.get(model,("prj_alpha",self.member)))
            self.assertEqual(session.get(m.AgentTask,task_id).result_message_id,message.id)
            self.assertEqual(session.get(m.Message,message.id).content,"old result")
            self.assertIsNotNone(session.get(m.ProjectRole,("prj_alpha",self.member)).archived_at)
        self.assertFalse(any(r["member_id"]==self.member for r in self.get_roles().json()))
        replacement=self.create_role("prj_alpha",role_name="delete-me",choice_id=self.choice,operation_key="op-readd-deleted")
        self.assertEqual(replacement.status_code,201,replacement.text)
        self.assertNotEqual(replacement.json()["member_id"],self.member)

    def test_pending_and_completed_roles_cannot_be_recovered_or_synced_back(self):
        self.delete()
        self.assertEqual(self.sync_roster("prj_alpha",[{"member_id":self.member}]).status_code,409)
        self.assertEqual(self.create_role("prj_alpha",role_name="delete-me",choice_id=self.choice,
            role_description="exclusive description",operation_key="op-delete-fixture").status_code,409)
        self.assertEqual(self.call("/provision",{"operation_key":"op-delete-fixture"}).status_code,409)
        self.assertEqual(self.sync_roster("prj_alpha",[]).status_code,200)
        with self.session() as session:
            self.assertIsNotNone(session.get(m.ProjectAgent,("prj_alpha",self.member)))

    def test_shared_identity_preserves_other_project_and_key(self):
        self.register_project("prj_beta")
        with self.session() as session:
            role=session.get(m.ProjectRole,("prj_alpha",self.member));role.identity_exclusive=0;role.origin="imported"
            session.add(role);session.add(m.ProjectAgent(project_id="prj_beta",member_id=self.member));session.commit()
        response=self.delete();self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()["identity_disabled"])
        with self.make_client() as client:
            self.assertEqual(client.get("/api/members/me",headers={"X-API-Key":self.role["api_key"]}).status_code,200)
        with self.session() as session:
            self.assertIsNotNone(session.get(m.ProjectAgent,("prj_beta",self.member)))

    def test_paused_running_creator_and_uncollected_tasks_refuse(self):
        for creator,status,workflow,control in [(False,"queued","assigned","paused"),(False,"running","in_progress",None),
                (False,"succeeded","submitted",None),(True,"queued","assigned",None)]:
            with self.subTest(status=status,workflow=workflow,creator=creator):
                with self.session() as session:
                    task=m.AgentTask(project_id="prj_alpha",target_member_id="agent:worker" if creator else self.member,
                        created_by=self.member if creator else "human:bobo",content="protect",status=status,
                        workflow_status=workflow,control_status=control)
                    session.add(task);session.commit();task_id=task.id
                self.assertEqual(self.delete().json()["detail"],"role_has_active_tasks")
                with self.session() as session:
                    self.assertIsNone(session.get(RoleDeletion,("prj_alpha",self.member)))
                    session.delete(session.get(m.AgentTask,task_id));session.commit()

    def test_service_and_unknown_instance_never_auto_stopped(self):
        with self.session() as session:
            session.add(m.RoleServiceState(project_id="prj_alpha",member_id=self.member,owner_host="unknown-owner"));session.commit()
        self.assertEqual(self.delete().json()["detail"],"role_service_running")
        with self.session() as session:
            session.delete(session.get(m.RoleServiceState,("prj_alpha",self.member)))
            session.add(m.AgentInstance(id="ins_fixture",member_id=self.member,runtime="dsh",status="idle"));session.commit()
        self.assertEqual(self.delete().json()["detail"],"role_instance_active")

    def test_finished_failed_history_is_not_collectable_and_does_not_block_delete(self):
        message=self.add_message(from_id=self.member,to_ids='["human:bobo"]',message_type="text",content="original bridge failure")
        with self.session() as session:
            task=m.AgentTask(project_id="prj_alpha",target_member_id=self.member,created_by="human:bobo",content="failed history",
                status="failed",workflow_status="failed",control_status="active",finished_at=datetime.now(timezone.utc)-timedelta(days=8),
                result_message_id=message.id,last_error="original failure",reserved_slice_count=0)
            session.add(task);session.commit();task_id=task.id
        with self.make_client() as client:
            self.assertEqual(client.post(f"/api/tasks/{task_id}/collect-result",headers={"X-API-Key":"bobo-key"}).status_code,409)
        # The normal test API lifespan fills legacy task-tree NULL defaults.
        # Take the deletion baseline after that unrelated startup migration.
        with self.session() as session:
            original=session.get(m.AgentTask,task_id).model_dump(mode="json")
            result_before=session.get(m.Message,message.id).model_dump(mode="json")
        result=self.delete();self.assertEqual(result.status_code,200,result.text)
        receipt=self.claim();self.assertEqual(self.report(receipt).status_code,200)
        with self.session() as session:
            self.assertEqual(session.get(m.AgentTask,task_id).model_dump(mode="json"),original)
            self.assertEqual(session.get(m.Message,message.id).model_dump(mode="json"),result_before)

    def test_finished_failed_creator_global_history_is_preserved(self):
        with self.session() as session:
            task=m.AgentTask(project_id=None,target_member_id="agent:worker",created_by=self.member,content="legacy failed creator",
                status="failed",workflow_status="failed",finished_at=datetime.now(timezone.utc)-timedelta(hours=1))
            session.add(task);session.commit();task_id=task.id
        with self.make_client() as client:
            self.assertEqual(client.get("/healthz").status_code,200)
        with self.session() as session:
            original=session.get(m.AgentTask,task_id).model_dump(mode="json")
        result=self.delete();self.assertEqual(result.status_code,200,result.text)
        with self.session() as session:
            self.assertEqual(session.get(m.AgentTask,task_id).model_dump(mode="json"),original)

    def test_failed_task_without_terminal_proof_still_blocks_deletion(self):
        now=datetime.now(timezone.utc)
        cases=[{"finished_at":None},{"finished_at":now+timedelta(minutes=1)},
            {"lease_expires_at":now+timedelta(minutes=1)},{"lease_expires_at":now-timedelta(minutes=1)},
            {"claim_token":"still-owned"},{"reserved_slice_count":1},
            *[{"control_status":control} for control in ("paused","pause_requested","awaiting_human","cancel_requested","unknown")],
            {"status":"running"},{"status":"queued"},{"status":"succeeded"},
            {"workflow_status":"submitted"},{"workflow_status":"in_progress"},{"workflow_status":"accepted"}]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                values=dict(project_id="prj_alpha",target_member_id=self.member,created_by="human:bobo",content="guard failed",
                    status="failed",workflow_status="failed",control_status="active",finished_at=now-timedelta(hours=1))
                values.update(overrides)
                with self.session() as session:
                    task=m.AgentTask(**values);session.add(task);session.commit();task_id=task.id
                rejected=self.delete();self.assertEqual(rejected.status_code,409,rejected.text)
                self.assertEqual(rejected.json()["detail"],"role_has_active_tasks")
                with self.session() as session:
                    self.assertIsNone(session.get(RoleDeletion,("prj_alpha",self.member)))
                    session.delete(session.get(m.AgentTask,task_id));session.commit()

    def test_terminal_failed_history_does_not_hide_another_active_task(self):
        with self.session() as session:
            session.add(m.AgentTask(project_id="prj_alpha",target_member_id=self.member,created_by="human:bobo",content="old failed",
                status="failed",workflow_status="failed",finished_at=datetime.now(timezone.utc)-timedelta(days=1)))
            session.add(m.AgentTask(project_id=None,target_member_id=self.member,created_by="human:bobo",content="still queued"))
            session.commit()
        result=self.delete();self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(result.json()["detail"],"role_has_active_tasks")

    def test_pending_launch_provision_request_and_schedule_are_protected(self):
        rows=[m.RoleServiceLaunch(launch_id="launch-delete-fixture",project_id="prj_alpha",member_id=self.member,
                action="start",generation=1,expected_instance_id="ins_fixture",launch_expires_at=datetime.now(timezone.utc)+timedelta(minutes=1)),
              m.RoleProvisionRequestRow(request_key="request-delete-fixture",project_id="prj_alpha",member_id=self.member,
                kind="recover",payload={},request_fingerprint="fixture",status="leased",created_by="human:bobo"),
              m.AgentTaskSchedule(target_member_id=self.member,created_by="human:bobo",content="protect scheduled work",
                schedule_type="once",status="paused",next_run_at=datetime.now(timezone.utc))]
        for row,code in zip(rows,["role_service_running","role_provision_active","role_has_active_schedules"]):
            with self.session() as session:
                session.add(row);session.commit();session.refresh(row);primary=row.id if isinstance(row,m.AgentTaskSchedule) else None
            self.assertEqual(self.delete().json()["detail"],code)
            with self.session() as session:
                target=session.get(type(row),primary if primary else row.launch_id if isinstance(row,m.RoleServiceLaunch) else row.request_key)
                session.delete(target);session.commit()

    def test_simultaneous_claims_have_only_one_valid_lease(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        self.delete();gate=threading.Barrier(2)
        def claiming():
            gate.wait();return self.call("/deletion/claim",{"revision":1})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a,b=pool.submit(claiming),pool.submit(claiming)
            results=[a.result(timeout=20),b.result(timeout=20)]
        self.assertEqual(sorted(r.status_code for r in results),[200,409])

    def test_failed_cleanup_retry_is_durable_and_old_lease_rejected(self):
        self.delete();first=self.claim()
        self.assertEqual(self.call("/deletion/claim",{"revision":first["revision"]}).status_code,409)
        self.assertEqual(self.report(first,outcome="failed",error="cleanup_busy").json()["status"],"failed")
        retry=self.delete().json();self.assertEqual(retry["status"],"pending")
        self.assertEqual(retry["steps"],{})
        second=self.claim(retry["revision"])
        self.assertEqual(self.report(first).status_code,409)
        bad=dict(second,lease_token="wrong");self.assertEqual(self.report(bad).status_code,409)
        self.assertEqual(self.report(second).status_code,200)

    def test_crashed_worker_lease_can_resume_without_old_result_overwrite(self):
        self.delete();old=self.claim()
        with self.session() as session:
            row=session.get(RoleDeletion,("prj_alpha",self.member));row.lease_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            session.add(row);session.commit()
        new=self.claim(old["revision"])
        self.assertEqual(self.report(old).status_code,409)
        self.assertEqual(self.report(new).status_code,200)

    def test_incomplete_receipt_cannot_claim_success_or_leak_errors(self):
        self.delete();receipt=self.claim()
        self.assertEqual(self.report(receipt,steps={s:"pending" for s in STEPS}).status_code,422)
        self.assertEqual(self.report(receipt,steps={s:"preserved" for s in STEPS}).status_code,422)
        self.assertEqual(self.report(receipt,outcome="failed",error="C:/private-key-secret").status_code,422)
        public=self.call("/deletion",method="GET").json()
        for key in ("lease_token","lease_hash","credential_digest","api_key"):
            self.assertNotIn(key,public)

    def test_filesystem_alias_collision_refuses_before_tombstone(self):
        self.add_member(self.member.replace(":","_"),api_key="alias-key")
        self.assertEqual(self.delete().json()["detail"],"role_resource_ownership_unknown")

    def test_concurrent_task_creation_and_delete_are_serialized(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        gate=threading.Barrier(2)
        def deleting():
            gate.wait();return self.delete()
        def assigning():
            gate.wait();return self.create_task("prj_alpha",self.member)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a,b=pool.submit(deleting),pool.submit(assigning)
            removed,task=a.result(timeout=20),b.result(timeout=20)
        self.assertIn((removed.status_code,task.status_code),[(200,400),(200,409),(409,201)],
                      (removed.text,task.text))
        self.assertFalse(removed.status_code==200 and task.status_code==201)

    def test_real_http_runtime_cleanup_closes_loop_and_preserves_other_files(self):
        from scripts.talk_runtime import TalkRuntime
        from scripts.role_provision import key_file_path, profile_target_paths
        project=self._tmpdir/"project";project.mkdir()
        keys=self._tmpdir/"keys";keys.mkdir();state=self._tmpdir/"private-state";state.mkdir()
        config={"project_id":"prj_alpha","project_root":str(project),"key_root":str(keys),"state_dir":str(state),"hosts":[]}
        config_path=self._tmpdir/"runtime.json";config_path.write_text(json.dumps(config),encoding="utf-8")
        profile=profile_target_paths(project,self.member)["identity"];profile.parent.mkdir(parents=True);profile.write_text("isolated identity",encoding="utf-8")
        key=key_file_path(keys,self.member);key.write_text(self.role["api_key"],encoding="utf-8")
        other=keys/"other.key";other.write_text("other role secret",encoding="utf-8")
        with self.session() as session:
            p=session.get(m.Project,"prj_alpha");p.project_root_path=str(project);session.add(p);session.commit()
        self.assertEqual(self.delete().status_code,200)
        with self.make_client() as client:
            class Client:
                def request(_,method,path,body=None):
                    response=client.request(method,path,json=body,headers={"X-API-Key":"bobo-key"})
                    response.raise_for_status();return response.json()
            runtime=TalkRuntime(config,client=Client(),config_path=config_path)
            import hashlib
            digest=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            with patch("server.role_deletions._cleanup_binding_digest",return_value=digest):
                runtime.reconcile_deletions(runtime.roles())
            result=client.get(self.base+"/deletion",headers={"X-API-Key":"bobo-key"})
            self.assertEqual(result.json()["status"],"complete",result.text)
            self.assertEqual(client.get("/api/projects/prj_alpha/agents",headers={"X-API-Key":"bobo-key"}).json(),[])
        self.assertFalse(profile.exists());self.assertFalse(key.exists());self.assertEqual(other.read_text(encoding="utf-8"),"other role secret")


    def _shared_role(self):
        with self.session() as session:
            role=session.get(m.ProjectRole,("prj_alpha",self.member))
            role.origin="imported";role.identity_exclusive=0;session.add(role);session.commit()

    def test_off_roster_managed_identity_refuses_without_silent_credential_preservation(self):
        self.assertEqual(self.sync_roster("prj_alpha",[]).status_code,200)
        result=self.delete();self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(result.json()["detail"],"role_delete_identity_proof_required")
        with self.session() as session:
            self.assertIsNone(session.get(RoleDeletion,("prj_alpha",self.member)))
            self.assertIsNone(session.get(m.ProjectRole,("prj_alpha",self.member)).archived_at)
            self.assertIsNotNone(session.get(m.ProjectRoleBinding,("prj_alpha",self.member)))
        self.assertEqual(self.sync_roster("prj_alpha",[{"member_id":self.member}]).status_code,200)
        self.assertTrue(self.delete().json()["identity_disabled"])
        with self.make_client() as client:
            self.assertEqual(client.get("/api/members/me",headers={"X-API-Key":self.role["api_key"]}).status_code,401)

    def test_deleted_shared_identity_requires_scope_for_global_task_and_schedule(self):
        self._shared_role();self.assertEqual(self.delete().status_code,200)
        with self.make_client() as client:
            for path,body,key in [("/api/tasks",{"target_member_id":self.member,"content":"ambiguous"},"bobo-key"),
                    ("/api/tasks/schedules",{"target_member_id":self.member,"content":"ambiguous"},"bobo-key"),
                    ("/api/tasks",{"target_member_id":"agent:worker","content":"ambiguous"},self.role["api_key"])]:
                response=client.post(path,headers={"X-API-Key":key},json=body)
                self.assertEqual(response.status_code,409,response.text)
                self.assertEqual(response.json()["detail"],"task_project_scope_required")

    def test_deleted_shared_identity_cannot_claim_legacy_projectless_task(self):
        self._shared_role();self.delete()
        with self.session() as session:
            task=m.AgentTask(target_member_id=self.member,created_by="human:bobo",content="old bypass",control_status="active")
            session.add(task);session.commit();task_id=task.id
        with self.make_client() as client:
            response=client.post(f"/api/tasks/{task_id}/claim",headers={"X-API-Key":self.role["api_key"]},json={"lease_seconds":60})
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(response.json()["detail"],"task_project_scope_required")
        with self.session() as session:
            self.assertEqual(session.get(m.AgentTask,task_id).status,"queued")

    def test_shared_other_project_stays_usable_with_explicit_scope(self):
        self._shared_role();self.register_project("prj_beta")
        with self.session() as session:
            session.add(m.ProjectAgent(project_id="prj_beta",member_id=self.member))
            session.add(m.ProjectRole(project_id="prj_beta",member_id=self.member,role_name="other-project",origin="imported",created_by="human:bobo"));session.commit()
        self.delete()
        response=self.create_task("prj_beta",self.member)
        self.assertEqual(response.status_code,201,response.text)
        with self.make_client() as client:
            claim=client.post(f"/api/tasks/{response.json()['id']}/claim",headers={"X-API-Key":self.role["api_key"]},json={"lease_seconds":60})
            self.assertEqual(claim.status_code,200,claim.text)
        blocked=self.create_task("prj_alpha",self.member)
        self.assertIn(blocked.status_code,[400,409])

    def test_unclosed_global_task_blocks_project_deletion(self):
        self._shared_role();task=self.create_task(None,self.member)
        self.assertEqual(task.status_code,201,task.text)
        response=self.delete()
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()["detail"],"role_has_active_tasks")

    def test_deleted_global_schedule_cannot_resume_or_materialize(self):
        self._shared_role();self.delete()
        with self.session() as session:
            schedule=m.AgentTaskSchedule(target_member_id=self.member,created_by="human:bobo",content="old bypass",
                schedule_type="once",status="paused",next_run_at=datetime.now(timezone.utc))
            session.add(schedule);session.commit();sid=schedule.id
        with self.make_client() as client:
            resumed=client.patch(f"/api/tasks/schedules/{sid}",headers={"X-API-Key":"bobo-key"},json={"status":"active"})
            self.assertEqual(resumed.status_code,409,resumed.text)
        with self.session() as session:
            schedule=session.get(m.AgentTaskSchedule,sid);schedule.status="active";session.add(schedule);session.commit()
        with self.make_client() as client:
            result=client.post("/api/tasks/schedules/run-due",headers={"X-API-Key":"bobo-key"},json={})
            self.assertEqual(result.status_code,409,result.text)
        with self.session() as session:
            self.assertIsNone(session.exec(select(m.AgentTask).where(m.AgentTask.schedule_id==sid)).first())

    def test_schedule_create_and_delete_serialize(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        self._shared_role();gate=threading.Barrier(2)
        def scheduling():
            gate.wait()
            with self.make_client() as client:
                return client.post("/api/tasks/schedules",headers={"X-API-Key":"bobo-key"},json={"target_member_id":self.member,"content":"race"})
        def deleting():
            gate.wait();return self.delete()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a,b=pool.submit(scheduling),pool.submit(deleting)
            scheduled,removed=a.result(timeout=20),b.result(timeout=20)
        self.assertIn((scheduled.status_code,removed.status_code),[(201,409),(409,200)],(scheduled.text,removed.text))

    def test_legacy_roster_only_role_gets_valid_tombstone_and_preserves_shared_key(self):
        with self.session() as session:
            session.add(m.ProjectAgent(project_id="prj_alpha",member_id="agent:worker"));session.commit()
        with self.make_client() as client:
            response=client.post("/api/projects/prj_alpha/roles/agent%3Aworker/delete",
                headers={"X-API-Key":"bobo-key"},json={"confirm_member_id":"agent:worker"})
            self.assertEqual(response.status_code,200,response.text)
            self.assertFalse(response.json()["identity_disabled"])
            self.assertEqual(client.get("/api/members/me",headers={"X-API-Key":"worker-key"}).status_code,200)
        with self.session() as session:
            self.assertEqual(session.get(m.ProjectRole,("prj_alpha","agent:worker")).created_by,"human:bobo")

    def test_deleted_identity_cannot_invent_project_scope_but_other_legacy_roster_works(self):
        self._shared_role();self.register_project("prj_beta");self.delete()
        response=self.create_task("prj_beta",self.member)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()["detail"],"task_role_not_in_project")
        with self.session() as session:
            task=m.AgentTask(project_id="prj_beta",target_member_id=self.member,created_by="human:bobo",content="old bypass",control_status="active")
            session.add(task);session.commit();task_id=task.id
        with self.make_client() as client:
            claim=client.post(f"/api/tasks/{task_id}/claim",headers={"X-API-Key":self.role["api_key"]},json={"lease_seconds":60})
            self.assertEqual(claim.status_code,409,claim.text)
        with self.session() as session:
            session.add(m.ProjectAgent(project_id="prj_beta",member_id=self.member));session.commit()
        self.assertEqual(self.create_task("prj_beta",self.member).status_code,201)
        with self.make_client() as client:
            claim=client.post(f"/api/tasks/{task_id}/claim",headers={"X-API-Key":self.role["api_key"]},json={"lease_seconds":60})
            self.assertEqual(claim.status_code,200,claim.text)


    def historical_instance(self, **overrides):
        values = dict(id="ins_old_delete", member_id=self.member, project_id="prj_alpha", runtime="dsh",
            status="idle", host=socket.gethostname(), pid=2147483000,
            process_started_at=datetime.now(timezone.utc)-timedelta(days=2),
            last_seen_at=datetime.now(timezone.utc)-timedelta(days=1))
        values.update(overrides)
        with self.session() as session:
            session.add(m.AgentInstance(**values));session.commit()

    def test_historical_local_exited_instance_does_not_block_delete(self):
        self.historical_instance()
        with patch("scripts.role_service_recovery.recorded_process_state", return_value="absent"):
            with self.session() as session:
                self.assertEqual(m.prove_exclusive_identity("prj_alpha",self.member,session)["refusal"],"rotate_identity_in_use")
            result=self.delete()
        self.assertEqual(result.status_code,200,result.text)

    def test_historical_reused_pid_does_not_block_delete(self):
        self.historical_instance()
        with patch("scripts.role_service_recovery.recorded_process_state", return_value="pid_reused"):
            result=self.delete()
        self.assertEqual(result.status_code,200,result.text)

    def test_historical_local_online_status_also_requires_and_accepts_exit_proof(self):
        self.historical_instance(status="online")
        with patch("scripts.role_service_recovery.recorded_process_state",return_value="previous_boot"):
            result=self.delete()
        self.assertEqual(result.status_code,200,result.text)

    def test_real_absent_local_process_metadata_allows_historical_instance(self):
        self.historical_instance()
        result=self.delete()
        self.assertEqual(result.status_code,200,result.text)

    def test_old_heartbeat_is_not_proof_that_a_local_process_exited(self):
        self.historical_instance()
        for state in ("present","unknown"):
            with patch("scripts.role_service_recovery.recorded_process_state",return_value=state):
                self.assertEqual(self.delete().json()["detail"],"role_instance_active")

    def test_remote_missing_pid_or_unknown_status_remains_protected(self):
        for extra in ({"host":"another-machine"},{"host":None},{"pid":None},{"status":"unconfirmed"},{"current_task_id":"old-task"}):
            self.historical_instance(**extra)
            with patch("scripts.role_service_recovery.recorded_process_state",return_value="absent"):
                self.assertEqual(self.delete().json()["detail"],"role_instance_active")
            with self.session() as session:
                session.delete(session.get(m.AgentInstance,"ins_old_delete"));session.commit()

    def test_fresh_or_future_heartbeat_remains_protected_even_if_pid_absent(self):
        for delta in (timedelta(seconds=-1),timedelta(minutes=1)):
            self.historical_instance(last_seen_at=datetime.now(timezone.utc)+delta)
            with patch("scripts.role_service_recovery.recorded_process_state",return_value="absent"):
                self.assertEqual(self.delete().json()["detail"],"role_instance_active")
            with self.session() as session:
                session.delete(session.get(m.AgentInstance,"ins_old_delete"));session.commit()

    def test_cleanup_batch_yields_and_reclaims_without_another_delete_click(self):
        self.delete();first=self.claim()
        steps={"manager":"complete","profiles":"complete","credentials":"complete","private_state":"pending","startup_config":"pending"}
        yielded=self.report(first,outcome="pending",steps=steps)
        self.assertEqual(yielded.status_code,200,yielded.text)
        self.assertEqual(yielded.json()["status"],"pending")
        self.assertIsNone(yielded.json()["error_code"])
        second=self.claim(yielded.json()["revision"])
        self.assertEqual(self.report(first).status_code,409)
        self.assertEqual(self.report(second).json()["status"],"complete")

    def test_pending_receipt_cannot_mask_failed_or_unstarted_work(self):
        self.delete();receipt=self.claim()
        cases=[{s:"pending" for s in STEPS},{s:"complete" for s in STEPS},
            {**{s:"pending" for s in STEPS},"manager":"complete","profiles":"failed"}]
        for steps in cases:
            self.assertEqual(self.report(receipt,outcome="pending",steps=steps).status_code,422)
        self.assertEqual(self.report(receipt).status_code,200)


    def test_real_http_runtime_resumes_large_cleanup_until_role_disappears(self):
        import hashlib
        from scripts.talk_runtime import TalkRuntime
        from scripts.role_provision import key_file_path,profile_target_paths
        from scripts.role_service_host import _sanitize_token
        project=self._tmpdir/"project";project.mkdir()
        keys=self._tmpdir/"keys";keys.mkdir();state=self._tmpdir/"private-state";state.mkdir()
        config={"project_id":"prj_alpha","project_root":str(project),"key_root":str(keys),"state_dir":str(state),"hosts":[]}
        config_path=self._tmpdir/"runtime.json";config_path.write_text(json.dumps(config),encoding="utf-8")
        profile=profile_target_paths(project,self.member)["identity"];profile.parent.mkdir(parents=True);profile.write_text("synthetic identity",encoding="utf-8")
        key=key_file_path(keys,self.member);key.write_text(self.role["api_key"],encoding="utf-8")
        other=keys/"other.key";other.write_text("synthetic other identity",encoding="utf-8")
        cache=state/"workbuddy-native/prj_alpha"/_sanitize_token(self.member)/"home/cache/a/b/c";cache.mkdir(parents=True)
        for i in range(160):(cache/f"entry-{i}").write_text("synthetic cache",encoding="utf-8")
        with self.session() as session:
            p=session.get(m.Project,"prj_alpha");p.project_root_path=str(project);session.add(p);session.commit()
        self.assertEqual(self.delete().status_code,200)
        with self.make_client() as client:
            class Client:
                def request(_,method,path,body=None):
                    response=client.request(method,path,json=body,headers={"X-API-Key":"bobo-key"})
                    response.raise_for_status();return response.json()
            runtime=TalkRuntime(config,client=Client(),config_path=config_path)
            digest=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            seen=[]
            with patch("server.role_deletions._cleanup_binding_digest",return_value=digest),patch("scripts.role_delete.MAX_OPERATIONS",100):
                for _ in range(30):
                    runtime.reconcile_deletions(runtime.roles())
                    result=client.get(self.base+"/deletion",headers={"X-API-Key":"bobo-key"}).json();seen.append(result["status"])
                    if result["status"]=="complete":break
                    self.assertEqual(result["status"],"pending",result)
                    self.assertIsNone(result["error_code"])
            self.assertEqual(seen[-1],"complete",seen);self.assertIn("pending",seen)
            self.assertEqual(client.get("/api/projects/prj_alpha/roles",headers={"X-API-Key":"bobo-key"}).json(),[])
        self.assertFalse(cache.exists());self.assertFalse(profile.exists());self.assertFalse(key.exists());self.assertTrue(other.exists())


class DeletionBindingTests(RoleApiTestCase):
    def test_binding_requires_same_database_project_root_and_exact_config(self):
        import hashlib, sys
        import server.local_runtime as local
        from server.role_deletions import _cleanup_binding_digest
        project=self._tmpdir/"project";project.mkdir()
        self.register_project(project_root_path=str(project))
        config={"schema":"talk-runtime-config-1","version":1,"project_id":"prj_alpha", "project_root":str(project),
            "state_dir":str(self._tmpdir/"state"),"key_root":str(self._tmpdir/"keys"),
            "operator_key_file":str(self._tmpdir/"human.key"),"base_url":"http://127.0.0.1:1",
            "api_argv":[sys.executable,"--control-file","{control_file}"],"hosts":[]}
        path=self._tmpdir/"runtime.json";path.write_text(json.dumps(config),encoding="utf-8")
        pointer=self._tmpdir/"binding.json"
        metadata={"schema":"talk-local-runtime-1","database_file":str(self.db_path),"config_file":str(path)}
        pointer.write_text(json.dumps(metadata),encoding="utf-8")
        with patch.object(local,"ROOT",project),patch.object(local,"POINTER",pointer),self.session() as session:
            actual=_cleanup_binding_digest(session,"prj_alpha")
            expected=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            self.assertEqual(actual,expected)
            metadata["database_file"]=str(self._tmpdir/"other.db");pointer.write_text(json.dumps(metadata),encoding="utf-8")
            with patch("scripts.talk_runtime.load_config") as load:
                self.assertIsNone(_cleanup_binding_digest(session,"prj_alpha"));load.assert_not_called()
