"""Picker API tests: no test launches a real desktop process."""
import logging
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
import server.db as db
from server.auth import get_current_member
from server.db import get_session
from server.main import app
from server.models import Member
from server.routes import local_workspaces as picker


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []
    def emit(self, record):
        self.messages.append(record.getMessage())


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.member = SimpleNamespace(kind='human')
        app.dependency_overrides[get_current_member] = lambda: self.member
        self.addCleanup(app.dependency_overrides.pop, get_current_member, None)
        self.client = TestClient(app, client=('127.0.0.1', 12345))
        self.addCleanup(self.client.close)
        self.run = mock.patch.object(picker.subprocess, 'run').start()
        self.addCleanup(mock.patch.stopall)
        self.platform = mock.patch.object(picker, '_picker_windows', return_value=True).start()
        self.run.return_value = SimpleNamespace(returncode=0, stdout=b'')

    def post(self, body=None):
        return self.client.post('/api/local/workspaces/pick-directory', json=body or {})

    def test_picker_script_topmost_owner(self):
        script = picker._PICKER_SCRIPT
        for fragment in ("New-Object System.Windows.Forms.Form", "$owner.TopMost = $true",
                         "$owner.ShowInTaskbar = $false", "$owner.FormBorderStyle = 'None'",
                         "$owner.StartPosition = 'CenterScreen'", "$owner.Width = 1",
                         "$owner.Height = 1", "$owner.Opacity = 0", "$owner.Show()",
                         "$owner.Activate()", "$dialog.ShowDialog($owner)",
                         "$owner.Close()", "$owner.Dispose()", "$dialog.Dispose()",
                         "$env:TALK_PICKER_INITIAL_DIR", "System.Text.UTF8Encoding($false)",
                         "exit 12"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)
        self.assertLess(script.index('$owner.Show()'), script.index('$owner.Activate()'))
        self.assertLess(script.index('$owner.Activate()'), script.index('$dialog.ShowDialog($owner)'))
        self.assertLess(script.index('finally {'), script.index('$owner.Close()'))

    def test_selection_cancel_and_no_path_logging(self):
        capture = Capture(); logging.getLogger().addHandler(capture)
        self.addCleanup(logging.getLogger().removeHandler, capture)
        path = 'C:\\目录\\private-test'
        self.run.return_value.stdout = path.encode('utf-8')
        r = self.post({'initial_dir': path})
        self.assertEqual((r.status_code, r.json()), (200, {'path': path}))
        args, kwargs = self.run.call_args
        self.assertEqual(kwargs['env']['TALK_PICKER_INITIAL_DIR'], path)
        self.assertNotIn('TALK_API_KEY', kwargs['env'])
        self.assertNotIn(path, str(args)); self.assertEqual(kwargs['timeout'], 120)
        self.assertIn('-STA', args[0]); self.assertNotIn(path, ' '.join(capture.messages))
        self.run.return_value.stdout = b''
        r = self.post(); self.assertEqual((r.status_code, r.json()), (200, {'path': None}))
        print('mock picker: human path=200; cancel=200/null; path absent from log')

    def test_agent_and_non_loopback(self):
        self.member.kind = 'agent'
        r = self.post(); self.assertEqual((r.status_code, r.json()['detail']), (403, 'human_required'))
        self.member.kind = 'human'
        with TestClient(app, client=('192.168.1.20', 1)) as remote:
            self.assertEqual(remote.post('/api/local/workspaces/pick-directory', json={}).status_code, 403)
        self.run.assert_not_called(); print('mock picker: agent=403; remote=403')

    def test_invalid_initial(self):
        for value in ('relative', 'C:relative', 'C:\\bad\0name', 'C:\\' + 'a' * 32768, 123, None, '\\\\server'):
            with self.subTest(value=str(value)[:20]):
                r = self.client.post('/api/local/workspaces/pick-directory', json={'initial_dir': value})
                self.assertEqual((r.status_code, r.json()['detail']), (422, 'workspace_picker_input_invalid'))
        self.run.assert_not_called(); print('mock picker: invalid input=422')

    def test_busy_timeout_unavailable_failed(self):
        picker._picker_lock.acquire()
        try:
            r = self.post(); self.assertEqual((r.status_code, r.json()['detail']), (409, 'workspace_picker_busy'))
        finally: picker._picker_lock.release()
        self.run.side_effect = subprocess.TimeoutExpired('fixed', 120)
        r = self.post(); self.assertEqual((r.status_code, r.json()['detail']), (504, 'workspace_picker_timeout'))
        self.run.side_effect = None; self.platform.return_value = False
        r = self.post(); self.assertEqual((r.status_code, r.json()['detail']), (503, 'workspace_picker_unavailable'))
        self.platform.return_value = True; self.run.return_value.returncode = 12
        r = self.post(); self.assertEqual((r.status_code, r.json()['detail']), (503, 'workspace_picker_unavailable'))
        self.run.return_value.returncode = 1
        r = self.post(); self.assertEqual((r.status_code, r.json()['detail']), (500, 'workspace_picker_failed'))
        print('mock picker: busy=409 timeout=504 unavailable=503 failed=500')

    def test_concurrent_picker(self):
        entered, release = threading.Event(), threading.Event()
        def run(*args, **kwargs):
            entered.set(); self.assertTrue(release.wait(5))
            return SimpleNamespace(returncode=0, stdout=b'')
        self.run.side_effect = run
        responses = []
        thread = threading.Thread(target=lambda: responses.append(self.post()))
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            r = self.post(); self.assertEqual((r.status_code, r.json()['detail']), (409, 'workspace_picker_busy'))
        finally:
            release.set(); thread.join(10)
        self.assertFalse(thread.is_alive()); self.assertEqual(responses[0].status_code, 200)
        self.assertEqual(self.run.call_count, 1); print('mock picker: concurrent=409; first=200; subprocess calls=1')


class PickerAuthenticationTests(unittest.TestCase):
    def test_real_key_and_trusted_authentication(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine('sqlite:///' + (Path(tmp) / 'picker.sqlite').as_posix(),
                                   connect_args={'check_same_thread': False})
            try:
                SQLModel.metadata.create_all(engine)
                with Session(engine) as session:
                    session.add_all([Member(id='human:test', kind='human', display_name='H', api_key='human-test'),
                                     Member(id='agent:test', kind='agent', display_name='A', api_key='agent-test')])
                    session.commit()
                def session_override():
                    with Session(engine) as session:
                        yield session
                app.dependency_overrides[get_session] = session_override
                with mock.patch.object(picker, '_picker_windows', return_value=True), \
                     mock.patch.object(picker.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'')) as run, \
                     mock.patch.object(db, 'AUTH_MODE', 'key'), mock.patch.object(db, 'TRUSTED_NETWORKS', ['loopback']), \
                     TestClient(app, client=('127.0.0.1', 1)) as client:
                    self.assertEqual(client.post('/api/local/workspaces/pick-directory', headers={'X-API-Key': 'human-test'}, json={}).status_code, 200)
                    self.assertEqual(client.post('/api/local/workspaces/pick-directory', headers={'X-API-Key': 'agent-test'}, json={}).status_code, 403)
                    with mock.patch.object(db, 'AUTH_MODE', 'trusted'):
                        self.assertEqual(client.post('/api/local/workspaces/pick-directory', json={}).status_code, 200)
                    self.assertEqual(run.call_count, 2)
                    print('mock picker: key human=200 agent=403; trusted operator=200')
            finally:
                app.dependency_overrides.pop(get_session, None)
                engine.dispose()


if __name__ == '__main__': unittest.main()
