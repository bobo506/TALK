"""Isolated lease recovery tests; no real process or production database is used."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
import tempfile
import unittest

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from server.models import AgentInstance, AgentTask, AgentTaskClaim, AgentTaskComplete, Member
from server.routes.tasks import claim_task, complete_task, requeue_expired_tasks, _try_requeue_expired_task


class CrashTaskClaimRecoveryTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent.parent / '.tmp' / 'wd1-p2'
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        self.engine = create_engine(f"sqlite:///{Path(self.tmp.name) / 'test.db'}", connect_args={'check_same_thread': False, 'timeout': 10})
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add(Member(id='agent:test', kind='agent', display_name='test', api_key='fixture'))
            session.add(AgentInstance(id='dead', member_id='agent:test', runtime='fixture', status='offline', current_task_id='1'))
            session.add(AgentInstance(id='new', member_id='agent:test', runtime='fixture', status='idle'))
            session.add(AgentTask(id=1, root_task_id=1, control_status='active', target_member_id='agent:test', created_by='agent:test', content='fixture', status='running', workflow_status='in_progress', attempt=1, claimed_by='agent:test', instance_id='dead', claim_token='old-fixture', lease_expires_at=datetime.now(timezone.utc)-timedelta(seconds=5)))
            session.commit()

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def poll(self):
        with Session(self.engine) as session:
            return requeue_expired_tasks(current=session.get(Member, 'agent:test'), session=session)

    def claim(self):
        with Session(self.engine) as session:
            task = claim_task(1, AgentTaskClaim(instance_id='new'), current=session.get(Member, 'agent:test'), session=session)
            return task.claim_token, task.attempt

    def test_expired_dead_requeues_and_reclaims_rejecting_old_attempt(self):
        self.assertEqual([row.id for row in self.poll()], [1])
        with Session(self.engine) as session:
            task, instance = session.get(AgentTask, 1), session.get(AgentInstance, 'dead')
            self.assertEqual((task.status, task.workflow_status), ('queued', 'accepted'))
            self.assertEqual((task.claimed_by, task.instance_id, task.claim_token, task.lease_expires_at), (None, None, None, None))
            self.assertIn('lease expired', task.last_error)
            self.assertEqual((instance.status, instance.current_task_id), ('error', None))
        token, attempt = self.claim()
        self.assertEqual(attempt, 2)
        self.assertNotEqual(token, 'old-fixture')
        with Session(self.engine) as session:
            with self.assertRaises(HTTPException) as ctx:
                complete_task(1, AgentTaskComplete(status='succeeded', claim_token='old-fixture'), current=session.get(Member, 'agent:test'), session=session)
            self.assertEqual(ctx.exception.status_code, 409)

    def test_unexpired_dead_waits_then_requeues(self):
        with Session(self.engine) as session:
            task = session.get(AgentTask, 1)
            task.lease_expires_at = datetime.now(timezone.utc)+timedelta(minutes=2)
            session.commit()
        self.assertEqual(self.poll(), [])
        with self.assertRaises(HTTPException) as ctx:
            self.claim()
        self.assertEqual(ctx.exception.status_code, 409)
        with Session(self.engine) as session:
            task = session.get(AgentTask, 1)
            self.assertEqual((task.status, task.claim_token), ('running', 'old-fixture'))
            self.assertEqual(session.get(AgentInstance, 'dead').current_task_id, '1')
            task.lease_expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            session.commit()
        self.assertEqual([row.id for row in self.poll()], [1])

    def test_direct_claim_reaps_expired_and_live_unexpired_is_protected(self):
        with Session(self.engine) as session:
            instance = session.get(AgentInstance, 'dead')
            instance.status = 'busy'
            task = session.get(AgentTask, 1)
            task.lease_expires_at = datetime.now(timezone.utc)+timedelta(minutes=2)
            session.commit()
        self.assertEqual(self.poll(), [])
        with self.assertRaises(HTTPException):
            self.claim()
        with Session(self.engine) as session:
            task = session.get(AgentTask, 1)
            task.lease_expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            session.commit()
        token, attempt = self.claim()
        self.assertEqual(attempt, 2)
        self.assertNotEqual(token, 'old-fixture')
        with Session(self.engine) as session:
            self.assertEqual((session.get(AgentInstance, 'dead').status, session.get(AgentInstance, 'dead').current_task_id), ('error', None))

    def test_other_current_task_not_changed(self):
        with Session(self.engine) as session:
            instance = session.get(AgentInstance, 'dead')
            instance.current_task_id, instance.status, instance.last_error = '999', 'busy', 'other'
            session.commit()
        self.assertEqual([row.id for row in self.poll()], [1])
        with Session(self.engine) as session:
            instance = session.get(AgentInstance, 'dead')
            self.assertEqual((instance.current_task_id, instance.status, instance.last_error), ('999', 'busy', 'other'))

    def test_concurrent_compare_and_swap_only_one_succeeds(self):
        barrier = Barrier(2)
        def reap(_):
            with Session(self.engine) as session:
                task = session.get(AgentTask, 1)
                barrier.wait(timeout=10)
                won = _try_requeue_expired_task(task, datetime.now(timezone.utc), session)
                session.commit()
                return won
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(reap, range(2))), [False, True])
        with Session(self.engine) as session:
            self.assertEqual(session.get(AgentTask, 1).status, 'queued')
            self.assertEqual(session.get(AgentInstance, 'dead').status, 'error')

    def test_stale_snapshot_cannot_requeue_a_different_expired_attempt(self):
        with Session(self.engine, expire_on_commit=False) as stale:
            old = stale.get(AgentTask, 1)
            with Session(self.engine) as session:
                task = session.get(AgentTask, 1)
                task.claim_token, task.instance_id, task.attempt = 'new-fixture', 'new', 2
                task.lease_expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
                instance = session.get(AgentInstance, 'new')
                instance.status, instance.current_task_id = 'busy', '1'
                session.commit()
            self.assertFalse(_try_requeue_expired_task(old, datetime.now(timezone.utc), stale))
            stale.commit()
        with Session(self.engine) as session:
            task = session.get(AgentTask, 1)
            self.assertEqual((task.status, task.claim_token, task.instance_id), ('running', 'new-fixture', 'new'))
            self.assertEqual(session.get(AgentInstance, 'dead').status, 'offline')
            self.assertEqual(session.get(AgentInstance, 'new').current_task_id, '1')
