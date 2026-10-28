import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from server import role_startup
from server.models import RoleNativeSetup
from tests import test_kimi_native_setup as fixtures
from tests.test_role_services import PROJECT_ID


class NativeSetupRegressions(fixtures.KimiNativeSetupTests):
    def test_regression_get_during_begin_preserves_starting(self):
        entered, release, read_done = threading.Event(), threading.Event(), threading.Event()
        values, errors = [], []
        attempt = SimpleNamespace(process=fixtures.FakeProcess(),released=False)
        def begin(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('synthetic gate')
            return attempt
        def start():
            try:
                with self.session() as session:
                    self.manager.start(PROJECT_ID,self.role_a,1,'human:bobo',session)
            except Exception as exc:
                errors.append(exc)
        def get():
            values.append(self._get())
            read_done.set()
        with patch('scripts.kimi_role_setup.begin_native_login',side_effect=begin),patch.object(self.manager,'_monitor'):
            starter=threading.Thread(target=start);starter.start()
            self.assertTrue(entered.wait(5))
            reader=threading.Thread(target=get);reader.start()
            try:
                self.assertFalse(read_done.wait(.05))
            finally:
                release.set();starter.join(5);reader.join(5)
        self.assertEqual(errors,[])
        self.assertTrue(read_done.is_set())
        self.assertEqual(values[0].status,'starting')

    def test_regression_stale_start_cannot_overwrite_active_attempt(self):
        attempt=SimpleNamespace(process=fixtures.FakeProcess(),released=False)
        with self.session() as stale:
            cached=stale.get(RoleNativeSetup,(PROJECT_ID,self.role_a))
            with patch('scripts.kimi_role_setup.begin_native_login',return_value=attempt) as begin,patch.object(self.manager,'_monitor'):
                with self.session() as session:
                    self.manager.start(PROJECT_ID,self.role_a,1,'human:bobo',session)
                with self.assertRaisesRegex(HTTPException,'native_setup_revision_conflict'):
                    self.manager.start(PROJECT_ID,self.role_a,1,'human:bobo',stale)
                self.assertEqual(begin.call_count,1)
        self.assertEqual(self._get().status,'starting')

    def test_regression_stale_cancel_is_rejected_after_finalizing(self):
        gate,entered,release,done=(threading.Event() for _ in range(4))
        def finish(attempt):
            entered.set();release.wait(5);done.set()
        self._start_manager(fixtures.FakeProcess(['https://kimi.example/auth\n'],gate=gate),finish=finish)
        waiting=self._wait_status('awaiting_authorization')
        try:
            with self.session() as stale:
                cached=stale.get(RoleNativeSetup,(PROJECT_ID,self.role_a))
                gate.set();self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(HTTPException,'native_setup_revision_conflict'):
                    self.manager.cancel(PROJECT_ID,self.role_a,waiting.revision,stale)
        finally:
            release.set();self.assertTrue(done.wait(5))

    def test_regression_cancel_before_finalizing_never_runs_finish(self):
        entered,release=threading.Event(),threading.Event()
        original=self.manager._current
        def paused(key,token):
            value=original(key,token)
            entered.set();release.wait(5)
            return value
        try:
            with patch.object(self.manager,'_current',side_effect=paused):
                row,finish=self._start_manager(fixtures.FakeProcess())
                self.assertTrue(entered.wait(5))
                attempt=self.manager._attempts[(PROJECT_ID,self.role_a)][1]
                with patch('scripts.kimi_role_setup.cancel_native_login'):
                    with self.session() as session:
                        canceled=self.manager.cancel(PROJECT_ID,self.role_a,row.revision,session)
                release.set()
                deadline=time.monotonic()+3
                while not attempt.released and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertTrue(attempt.released)
            self.assertEqual(canceled.error_code,'native_authorization_canceled')
            self.assertEqual(finish.call_count,0)
        finally:
            release.set()

    def test_regression_legacy_no_enrollment_does_not_require_login(self):
        with self.session() as session:
            session.delete(session.get(RoleNativeSetup,(PROJECT_ID,self.role_a)))
            session.commit()
        result=self._get()
        self.assertEqual(result.status,'not_required')
        self.assertFalse(result.requires_user_action)
        self.assertFalse(result.can_start)
        self.assertEqual(self.start().status_code,200)

    def test_regression_project_startup_obeys_authorization_gate(self):
        from datetime import datetime,timezone
        with self.session() as session:
            role_startup.set_preference(PROJECT_ID,self.role_a,True,self.human_member(),session)
        health={'pid':12345,'started_at':datetime.now(timezone.utc).isoformat()}
        with patch.object(role_startup,'verified_runtime',return_value=({},health,None)):
            with self.session() as session:
                result=role_startup.activate(PROJECT_ID,'synthetic-native-gate',self.human_member(),session)
        item=next(r for r in result['results'] if r['member_id']==self.role_a)
        self.assertNotEqual(item['status'],'enqueued')
        self.assertEqual(item['error_code'],'native_authorization_required')


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(NativeSetupRegressions(name) for name in loader.getTestCaseNames(NativeSetupRegressions)
        if name.startswith('test_regression_'))
