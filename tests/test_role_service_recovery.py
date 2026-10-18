"""人类异常恢复的真实数据库事务、权限、并发及旧回执隔离。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import threading

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from server.models import AgentInstance, AgentInstanceUpdate, AgentTask, Member, RoleServiceLaunch, RoleServiceRecovery, RoleServiceRecoveryRequest
from server.role_service_recovery import recover_stopped
from tests.test_role_services import RoleServiceTestCase, PROJECT_ID, OTHER_PROJECT_ID, HOST
from tests.test_project_roles import encode


class RoleServiceRecoveryTests(RoleServiceTestCase):
    def setUp(self):
        super().setUp()
        self.launch, self.claimed = self.start_and_claim()
        self.bind_instance(self.launch, self.claimed)
        self.assertEqual(self.ready_report(self.launch, self.claimed).status_code, 200)
        self.set_instance_last_seen(self.claimed["expected_instance_id"], 120)
        self.body = dict(operation_key="recovery-fixture-001", expected_generation=self.launch["generation"],
                         expected_process_launch_id=self.launch["launch_id"],
                         expected_instance_id=self.claimed["expected_instance_id"], expected_owner_host=HOST,
                         confirmation="old_processes_confirmed_stopped", reason="original_host_exited")

    def recover(self, body=None, *, key="bobo-key", project=PROJECT_ID, member=None):
        with self.make_client() as client:
            return client.post(f"/api/projects/{project}/roles/{encode(member or self.role_a)}/service/recover-stopped",
                               headers={"X-API-Key": key}, json=self.body if body is None else body)

    def plan(self, key="bobo-key"):
        with self.make_client() as client:
            return client.get(f"/api/projects/{PROJECT_ID}/roles/{encode(self.role_a)}/service/recovery-plan",
                              headers={"X-API-Key": key})

    def audits(self):
        with self.session() as session:
            return list(session.exec(select(RoleServiceRecovery)).all())

    def test_human_only_and_explicit_validated_confirmation(self):
        self.assertEqual(self.plan(self.role_a_key).status_code, 403)
        self.assertEqual(self.recover(key=self.role_a_key).status_code, 403)
        for changes in ({"confirmation": "yes"}, {"expected_generation": True},
                        {"unexpected": "fixture"}, {"reason": "arbitrary secret text"}):
            self.assertEqual(self.recover({**self.body, **changes}).status_code, 422)
        self.assertEqual(self.audits(), [])

    def test_plan_is_read_only_and_recovery_is_audited_without_forged_stop(self):
        before = self.state_row().model_dump()
        launch_before = self.launch_row(self.launch["launch_id"]).model_dump()
        plan = self.plan()
        self.assertEqual(plan.status_code, 200, plan.text)
        self.assertEqual(self.state_row().model_dump(), before)
        result = self.recover()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["generation"], before["generation"] + 1)
        state = self.state_row()
        self.assertEqual((state.desired_state, state.observed_state, state.last_result), ("stopped", "stopped", "stopped"))
        for field in ("process_launch_id", "owner_host", "pid", "observed_instance_id", "current_launch_id"):
            self.assertIsNone(getattr(state, field))
        self.assertEqual(self.launch_row(self.launch["launch_id"]).model_dump(), launch_before)
        with self.session() as session:
            instance = session.get(AgentInstance, self.claimed["expected_instance_id"])
            self.assertEqual(instance.status, "offline")
            self.assertLess(instance.last_seen_at, instance.updated_at)
        audit = self.audits()[0]
        self.assertEqual(audit.before_state["observed_state"], "running")
        self.assertEqual(audit.confirmed_by, "human:bobo")
        for secret in (self.claimed["owner_token"], self.claimed["claim_token"], "owner_token", "api_key"):
            self.assertNotIn(secret, result.text + plan.text + str(audit.before_state))

    def test_snapshot_conflicts_and_wrong_scope_do_not_write(self):
        before = self.state_row().model_dump()
        for field, value in (("expected_generation", 99), ("expected_owner_host", "wrong-host"),
                             ("expected_instance_id", "wrong-instance"), ("expected_process_launch_id", "wrong-launch")):
            with self.subTest(field=field):
                self.assertEqual(self.recover({**self.body, field: value}).status_code, 409)
        self.assertEqual(self.recover(project="missing-project").status_code, 404)
        self.assertEqual(self.recover(member="agent:other").status_code, 404)
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(self.audits(), [])

    def test_fresh_heartbeat_blocks_recovery(self):
        self.set_instance_last_seen(self.claimed["expected_instance_id"], 0)
        result = self.recover()
        self.assertEqual((result.status_code, result.json()["detail"]), (409, "recovery_recent_heartbeat"))
        self.assertEqual(self.audits(), [])

    def test_periodic_heartbeat_preserves_original_ready_time_and_state(self):
        before = self.state_row().model_dump()
        self.assertEqual(self.bind_instance(self.launch, self.claimed).status_code, 200)
        self.assertEqual(self.state_row().model_dump(), before)

    def test_target_tasks_block_even_in_another_project(self):
        self.register_project(OTHER_PROJECT_ID)
        for status in ("queued", "running"):
            with self.subTest(status=status), self.session() as session:
                task = AgentTask(target_member_id=self.role_a, created_by="human:bobo", content="fixture",
                                 status=status, project_id=OTHER_PROJECT_ID)
                session.add(task); session.commit()
                self.assertEqual(self.recover().json()["detail"], "recovery_tasks_active")
                session.delete(task); session.commit()
        self.assertEqual(self.audits(), [])

    def test_unexpired_pending_or_claimed_action_blocks(self):
        for status in ("pending", "claimed"):
            with self.subTest(status=status), self.session() as session:
                action = RoleServiceLaunch(launch_id="pending-fixture", project_id=PROJECT_ID,
                    member_id=self.role_a, action="stop", generation=42, state=status,
                    expected_instance_id=self.claimed["expected_instance_id"],
                    launch_expires_at=datetime.now(timezone.utc)+timedelta(seconds=60))
                session.add(action); session.commit()
                self.assertEqual(self.recover().json()["detail"], "recovery_action_active")
                session.delete(action); session.commit()

    def test_replay_does_not_clear_new_owner_and_old_reports_cannot_revive(self):
        first = self.recover()
        self.assertEqual(first.status_code, 200)
        new_launch, new_claim = self.start_and_claim()
        self.bind_instance(new_launch, new_claim)
        self.ready_report(new_launch, new_claim)
        before = self.state_row().model_dump()
        replay = self.recover()
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(replay.json()["recovery_id"], first.json()["recovery_id"])
        self.assertEqual(self.recover({**self.body, "expected_owner_host": "changed"}).json()["detail"], "recovery_conflict")
        self.assertEqual(self.ready_report(self.launch, self.claimed).status_code, 200, "旧回执只读重放")
        self.assertEqual(self.bind_instance(self.launch, self.claimed).json()["detail"], "instance_launch_recovered")
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(len(self.audits()), 1)

    def test_audit_insert_failure_rolls_back_state_and_instance(self):
        before = self.state_row().model_dump()
        with self.session() as session:
            session.execute(text("CREATE TRIGGER fail_recovery BEFORE INSERT ON role_service_recoveries "
                                 "BEGIN SELECT RAISE(ABORT, 'fixture fault'); END"))
            session.commit()
        with self.assertRaises(IntegrityError):
            self.recover()
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(self.audits(), [])
        with self.session() as session:
            self.assertEqual(session.get(AgentInstance, self.claimed["expected_instance_id"]).status, "idle")

    def test_state_write_failure_does_not_leave_audit(self):
        before = self.state_row().model_dump()
        with self.session() as session:
            session.execute(text("CREATE TRIGGER fail_recovery_state BEFORE UPDATE ON role_service_state "
                                 "BEGIN SELECT RAISE(ABORT, 'fixture fault'); END"))
            session.commit()
        with self.assertRaises(IntegrityError):
            self.recover()
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(self.audits(), [])

    def test_two_real_connections_allow_only_one_recovery(self):
        barrier = threading.Barrier(2)
        def run(number):
            with self.session() as session:
                operator = session.get(Member, "human:bobo")
                body = RoleServiceRecoveryRequest.model_validate({**self.body, "operation_key": f"race-operation-{number}"})
                barrier.wait(timeout=5)
                try:
                    recover_stopped(PROJECT_ID, self.role_a, body, operator, session)
                    return 200
                except HTTPException as error:
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(run, (1, 2))), [200, 409])
        self.assertEqual(len(self.audits()), 1)

    def test_expired_stop_cannot_report_into_recovered_generation(self):
        stopped = self.stop().json()
        claim = self.claim(stopped["launch_id"], {"host": HOST,
            "expected_instance_id": self.claimed["expected_instance_id"],
            "owner_token": self.claimed["owner_token"]}, key=self.role_a_key)
        self.assertEqual(claim.status_code, 200, claim.text)
        self.set_launch_expired(stopped["launch_id"])
        self.body["expected_generation"] = stopped["generation"]
        self.assertEqual(self.recover().status_code, 200)
        before = self.state_row().model_dump()
        late = self.report(stopped["launch_id"], dict(generation=stopped["generation"], action="stop",
            claim_token=claim.json()["claim_token"], owner_token=self.claimed["owner_token"],
            outcome="stopped", host=HOST, pid=4321, spawned=True), key=self.role_a_key)
        self.assertEqual(late.status_code, 409)
        self.assertEqual(self.state_row().model_dump(), before)

    def test_heartbeat_racing_recovery_either_blocks_release_or_is_rejected(self):
        from server.routes.instances import upsert_instance_status
        barrier = threading.Barrier(2)
        def run(operation):
            with self.session() as session:
                operator = session.get(Member, "human:bobo" if operation == "recover" else self.role_a)
                barrier.wait(timeout=5)
                try:
                    if operation == "recover":
                        recover_stopped(PROJECT_ID, self.role_a, RoleServiceRecoveryRequest(**self.body), operator, session)
                    else:
                        upsert_instance_status(self.claimed["expected_instance_id"],
                            AgentInstanceUpdate(runtime="dsh", status="idle"), operator, session)
                    return 200
                except HTTPException as error:
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, ("recover", "heartbeat")))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(len(self.audits()), int(results[0] == 200))
