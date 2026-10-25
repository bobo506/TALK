"""Busy-stop contract through isolated HTTP and real SQLite writer locks."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from unittest.mock import patch

from sqlmodel import select

import server.db as db
from server.models import AgentTask, AgentInstance, RoleServiceLaunch, RoleServiceState
from server.routes import tasks as routes
from server import role_services
from tests.test_role_services import RoleServiceTestCase, PROJECT_ID


class BusyStopTests(RoleServiceTestCase):
    def setUp(self):
        super().setUp()
        self.launch, self.owner = self.start_and_claim()
        self.instance = self.owner['expected_instance_id']
        self.assertEqual(self.bind_instance(self.launch, self.owner).status_code, 200)
        self.assertEqual(self.ready_report(self.launch, self.owner).status_code, 200)

    def create_task(self, **changes):
        body = dict(project_id=PROJECT_ID, target_member_id=self.role_a, content='PRIVATE-TASK-BODY')
        body.update(changes)
        with self.make_client() as client:
            response = client.post('/api/tasks', headers={'X-API-Key': 'bobo-key'}, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def task_claim(self, task_id, instance=True):
        with self.make_client() as client:
            return client.post(f'/api/tasks/{task_id}/claim', headers={'X-API-Key': self.role_a_key},
                               json={'instance_id': self.instance} if instance else {})

    def insert_task(self, **changes):
        body = dict(target_member_id=self.role_a, created_by='human:bobo', content='PRIVATE-TASK-BODY',
                    project_id=PROJECT_ID, status='running', instance_id=self.instance)
        body.update(changes)
        with self.session() as session:
            task = AgentTask(**body)
            session.add(task); session.commit(); session.refresh(task)
            task_id = task.id
        # Explicitly prepare the synthetic legacy row before the stop snapshot;
        # TestClient lifespan normally performs these compatibility migrations.
        db.init_db()
        return task_id

    def snapshot(self):
        with self.session() as session:
            return {cls.__name__: [r.model_dump(mode='json') for r in session.exec(select(cls)).all()]
                    for cls in (AgentTask, AgentInstance, RoleServiceLaunch, RoleServiceState)}

    def test_claimed_task_refuses_stop_without_any_row_mutation_then_completion_allows_stop(self):
        task_id = self.create_task()
        claimed = self.task_claim(task_id)
        self.assertEqual(claimed.status_code, 200, claimed.text)
        before = self.snapshot()
        denied = self.stop()
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(denied.json(), {'detail': {'code': 'role_service_busy', 'task_ids': [task_id],
                                                   'task_count': 1, 'instance_busy': True}})
        self.assertEqual(before, self.snapshot())
        # Persist the actual HTTP response for the actual web formatter/render pipeline.
        if os.environ.get('TALK_ISOLATED_TEST_ROOT'):
            path = Path(os.environ['TALK_ISOLATED_TEST_ROOT']) / 'api-busy-response.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(denied.json()), encoding='utf-8')
        with self.make_client() as client:
            completed = client.post(f'/api/tasks/{task_id}/complete', headers={'X-API-Key': self.role_a_key},
                                    json={'status': 'canceled', 'claim_token': claimed.json()['claim_token']})
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(self.stop().status_code, 200)

    def test_expired_or_residual_claim_blocks_including_missing_instance(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        for index, fields in enumerate([
            {'lease_expires_at': past}, {'status': 'queued', 'claim_token': 'PRIVATE-TOKEN'},
            {'status': 'failed', 'lease_expires_at': past}, {'instance_id': None}, {'instance_id': ''},
        ]):
            task_id = self.insert_task(**fields)
            before = self.snapshot()
            denied = self.stop()
            self.assertEqual(denied.status_code, 409, denied.text)
            self.assertEqual(denied.json()['detail']['task_count'], index + 1)
            self.assertIn(task_id, denied.json()['detail']['task_ids'])
            self.assertEqual(before, self.snapshot())

    def test_queued_paused_and_terminal_without_claims_do_not_block(self):
        self.insert_task(status='queued', workflow_status='accepted', control_status='paused', instance_id=None)
        self.insert_task(status='queued', instance_id=self.instance)
        for status in ('succeeded', 'failed', 'canceled'):
            self.insert_task(status=status)
        self.assertEqual(self.stop().status_code, 200)

    def test_other_known_instance_and_other_member_are_not_blockers(self):
        self.insert_task(instance_id='other-instance')
        self.insert_task(target_member_id='agent:unrelated')
        self.assertEqual(self.stop().status_code, 200)

    def test_global_and_other_project_on_same_instance_block(self):
        ids = [self.insert_task(project_id=None), self.insert_task(project_id='prj_other')]
        result = self.stop()
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()['detail']['task_ids'], ids)

    def test_instance_occupancy_without_task_row_is_not_a_fake_task_reference(self):
        for status, pointer in [('busy', None), ('idle', '777'), ('idle', 'message-private')]:
            with self.session() as session:
                instance = session.get(AgentInstance, self.instance)
                instance.status, instance.current_task_id = status, pointer
                session.add(instance); session.commit()
            before = self.snapshot()
            result = self.stop()
            self.assertEqual(result.status_code, 409, result.text)
            self.assertEqual(result.json()['detail'], {'code': 'role_service_busy', 'task_ids': [],
                                                       'task_count': 0, 'instance_busy': True})
            self.assertEqual(before, self.snapshot())

    def test_bounded_references_and_human_permission(self):
        ids = [self.insert_task(claim_token='PRIVATE-TOKEN') for _ in range(25)]
        denied = self.stop()
        self.assertEqual(denied.json()['detail']['task_ids'], ids[:20])
        self.assertEqual(denied.json()['detail']['task_count'], 25)
        self.assertNotIn('PRIVATE', denied.text)
        self.assertEqual(self.stop(key=self.role_a_key).status_code, 403)

    def test_stop_first_blocks_claim_with_or_without_instance(self):
        ids = [self.create_task(), self.create_task(),
               self.insert_task(project_id=None, status='queued', workflow_status='assigned', instance_id=None)]
        self.assertEqual(self.stop().status_code, 200)
        for task_id, instance in [(ids[0], True), (ids[1], False), (ids[2], True)]:
            before = self.snapshot()
            claim = self.task_claim(task_id, instance)
            self.assertEqual(claim.status_code, 409, claim.text)
            self.assertEqual(claim.json()['detail'], 'role_service_stopping')
            self.assertEqual(before, self.snapshot())

    def test_unmanaged_global_legacy_claim_is_unchanged(self):
        task_id = self.insert_task(project_id=None, status='queued', workflow_status='assigned', instance_id=None)
        # No task or supplied instance associates this legacy global request with a managed service.
        self.assertEqual(self.stop().status_code, 200)
        self.assertEqual(self.task_claim(task_id, False).status_code, 200)

    def test_expired_requeue_commit_relocks_and_observes_stop_before_reclaim(self):
        task_id = self.create_task()
        self.assertEqual(self.task_claim(task_id).status_code, 200)
        with self.session() as session:
            task = session.get(AgentTask, task_id)
            task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(task); session.commit()
        original = routes.begin_immediate_write
        calls = []
        def writer(session):
            calls.append(True)
            if len(calls) == 2:
                # Another real connection wins in the gap after expired requeue commit.
                self.assertEqual(self.stop().status_code, 200)
            original(session)
            self.assertTrue(session.connection().connection.driver_connection.in_transaction)
        with patch.object(routes, 'begin_immediate_write', side_effect=writer):
            result = self.task_claim(task_id)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(result.json()['detail'], 'role_service_stopping')
        with self.session() as session:
            task = session.get(AgentTask, task_id)
            self.assertEqual(task.status, 'queued')
            self.assertIsNone(task.claim_token)

    def test_real_wal_writers_enforce_both_orderings(self):
        with self.engine.connect() as conn:
            self.assertEqual(conn.exec_driver_sql('PRAGMA journal_mode=WAL').scalar(), 'wal')
        # Hold the first writer after its real BEGIN IMMEDIATE. The other writer
        # reaches its lock attempt before release; this verifies both serial orders.
        for first in ('claim', 'stop'):
            with self.subTest(first=first):
                task_id = self.create_task()
                entered, release, attempted = Event(), Event(), Event()
                original_claim, original_stop = routes.begin_immediate_write, role_services._write_begin
                def wrapper(original, action):
                    def call(session):
                        if action != first: attempted.set()
                        original(session)
                        if action == first:
                            entered.set()
                            if not release.wait(5): raise AssertionError('writer not released')
                    return call
                # Lifespan DB migrations finish before either guarded request.
                with self.make_client() as claim_client, self.make_client() as stop_client:
                    def run(action):
                        if action == 'claim':
                            return claim_client.post(f'/api/tasks/{task_id}/claim',
                                headers={'X-API-Key': self.role_a_key}, json={'instance_id': self.instance})
                        return stop_client.post(f'/api/projects/{PROJECT_ID}/roles/{self.role_a}/service/stop',
                                                headers={'X-API-Key': 'bobo-key'})
                    with patch.object(routes, 'begin_immediate_write', side_effect=wrapper(original_claim, 'claim')), \
                         patch.object(role_services, '_write_begin', side_effect=wrapper(original_stop, 'stop')), \
                         ThreadPoolExecutor(2) as pool:
                        a = pool.submit(run, first)
                        self.assertTrue(entered.wait(5))
                        b = pool.submit(run, 'stop' if first == 'claim' else 'claim')
                        try: self.assertTrue(attempted.wait(5))
                        finally: release.set()
                        results = {first: a.result(timeout=10), ('stop' if first == 'claim' else 'claim'): b.result(timeout=10)}
                self.assertEqual(results[first].status_code, 200, results[first].text)
                self.assertEqual(results['stop' if first == 'claim' else 'claim'].status_code, 409)
                if first == 'claim':
                    # Complete through the normal runner API before the next ordering.
                    with self.make_client() as client:
                        result = client.post(f'/api/tasks/{task_id}/complete', headers={'X-API-Key': self.role_a_key},
                            json={'status': 'canceled', 'claim_token': results['claim'].json()['claim_token']})
                    self.assertEqual(result.status_code, 200, result.text)
