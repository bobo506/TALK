"""Relink API tests using an isolated database and synthetic binding files."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine

import server.db as db
import server.main as main
from server import workspace_relink as relink
from server.db import get_session
from server.models import (AgentTask, Member, Project, RoleServiceState,
                           WorkspaceOperation, WorkspaceRelinkPreview)


class RelinkApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.old = self.base / 'old'
        self.new = self.base / 'new'
        for root in (self.old, self.new):
            (root / '.talk').mkdir(parents=True)
        self.config = self.base / 'runtime.json'
        self.config.write_text(json.dumps({'project_id': 'p', 'project_root': str(self.old), 'private': 'SAMPLE_SECRET'}), encoding='utf-8')
        self.pointer = {'schema': 'talk-local-runtime-1', 'database_file': str(self.base / 'db'), 'config_file': str(self.config)}
        (self.old / '.talk' / 'runtime.local.json').write_text(json.dumps(self.pointer), encoding='utf-8')
        self.engine = create_engine('sqlite:///' + (self.base / 'test.sqlite').as_posix(), connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([Member(id='human:p', kind='human', display_name='H', api_key='test-key'),
                             Member(id='agent:p', kind='agent', display_name='A', api_key='agent-key'),
                             Project(project_id='p', display_name='P', project_root_path=str(self.old), maintainer_member_id='human:p')])
            session.commit()
        def override():
            with Session(self.engine) as session:
                yield session
        main.app.dependency_overrides[get_session] = override
        self.addCleanup(main.app.dependency_overrides.pop, get_session, None)
        patch = mock.patch.object(db, 'AUTH_MODE', 'key')
        patch.start()
        self.addCleanup(patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.headers = {'X-API-Key': 'test-key'}

    def preview(self, root=None, project='p'):
        return self.client.post(f'/api/projects/{project}/workspace-relink-preview', headers=self.headers,
                                json={'candidate_root': str(root or self.new)})

    def submit(self, token, *, op='op', root=None, revision=1, project='p', headers=None):
        return self.client.post(f'/api/projects/{project}/workspace-relink', headers=headers or self.headers,
                                json={'preview_token': token, 'candidate_root': str(root or self.new),
                                      'expected_revision': revision, 'operation_id': op})

    def test_success_and_idempotent_retry(self):
        sentinel = self.base / 'unrelated.txt'
        sentinel.write_text('unchanged', encoding='utf-8')
        old_pointer = (self.old / '.talk' / 'runtime.local.json').read_bytes()
        with Session(self.engine) as session:
            session.add(AgentTask(project_id='p', target_member_id='agent:p', created_by='human:p', content='historical', status='queued'))
            session.add(RoleServiceState(project_id='p', member_id='agent:p', desired_state='stopped', observed_state='stopped'))
            session.commit()
        def history():
            with self.engine.connect() as connection:
                return {name: connection.execute(text('SELECT * FROM ' + name)).all()
                        for name in ('agent_tasks', 'messages', 'members', 'project_agents', 'role_service_state')}
        before = history()
        with mock.patch('server.local_runtime.ensure_local_runtime') as ensure:
            preview = self.preview()
            self.assertEqual(preview.status_code, 200)
            body = preview.json()
            response = self.submit(body['preview_token'])
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['stage'], 'completed')
            expected_root = os.path.normcase(os.path.normpath(str(self.new)))
            self.assertEqual(response.json()['project_root'], expected_root)
            with Session(self.engine) as session:
                row = session.get(WorkspaceRelinkPreview, body['preview_token'])
                row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                session.add(row)
                session.commit()
            retry = self.submit(body['preview_token'])
            self.assertEqual(retry.status_code, 200)
            self.assertEqual(retry.json()['revision'], 2)
            self.assertEqual(retry.json()['project_root'], expected_root)
            expected_response = {'operation_id': 'op', 'project_id': 'p', 'revision': 2,
                                 'stage': 'completed', 'project_root': expected_root}
            self.assertEqual(response.json(), expected_response)
            self.assertEqual(retry.json(), expected_response)
            self.assertEqual(self.submit(body['preview_token'], op='other').json()['detail'], 'workspace_preview_stale')
            self.assertEqual(self.submit(body['preview_token'], revision=2).json()['detail'], 'workspace_operation_conflict')
            ensure.assert_not_called()
        self.assertEqual(before, history())
        with Session(self.engine) as session:
            self.assertEqual(session.get(Project, 'p').project_root_path, str(self.new))
        self.assertTrue((self.old / '.talk' / 'runtime.local.json').exists())
        self.assertEqual((self.old / '.talk' / 'runtime.local.json').read_bytes(), old_pointer)
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'unchanged')
        self.assertEqual(json.loads((self.new / '.talk' / 'runtime.local.json').read_text(encoding='utf-8')), self.pointer)
        self.assertEqual(json.loads(self.config.read_text(encoding='utf-8'))['project_root'], str(self.new))
        for response in (preview, response, retry):
            self.assertNotIn('test-key', response.text)
            self.assertNotIn('SAMPLE_SECRET', response.text)
            self.assertNotIn('agent-key', response.text)
            for private_path in (self.base / 'db', self.base / 'test.sqlite', self.config,
                                 self.old / '.talk' / 'runtime.local.json',
                                 self.new / '.talk' / 'runtime.local.json'):
                self.assertNotIn(json.dumps(str(private_path))[1:-1], response.text)
            self.assertNotIn('database_file', response.text)
            self.assertNotIn('config_file', response.text)
            self.assertNotIn('SAMPLE_SECRET', response.text)
        self.assertNotIn(json.dumps(str(self.base))[1:-1], preview.text)

    def test_stale_and_permission(self):
        token = self.preview().json()['preview_token']
        for bad in (None, 'wrong'):
            self.assertEqual(self.submit(bad).json()['detail'], 'workspace_preview_stale')
        self.assertEqual(self.submit(token, revision=2).json()['detail'], 'workspace_preview_stale')
        self.assertEqual(self.submit(token, root=self.old).json()['detail'], 'workspace_preview_stale')
        self.assertEqual(self.submit(token, headers={'X-API-Key': 'agent-key'}).status_code, 403)
        self.assertEqual(self.submit(token, headers={'X-API-Key': 'invalid'}).status_code, 401)
        with Session(self.engine) as session:
            session.add(Member(id='human:disabled', kind='human', display_name='Disabled', api_key='disabled-key', disabled_at=datetime.now(timezone.utc)))
            session.commit()
        self.assertEqual(self.submit(token, headers={'X-API-Key': 'disabled-key'}).status_code, 403)
        self.assertEqual(self.client.post('/api/projects/p/workspace-relink', json={}).status_code, 422)
        with Session(self.engine) as session:
            row = session.get(WorkspaceRelinkPreview, token)
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(row)
            session.commit()
        self.assertEqual(self.submit(token).json()['detail'], 'workspace_preview_stale')

    def test_blocked_preview_and_busy(self):
        self.assertEqual(self.preview(self.base / 'missing').status_code, 409)
        with Session(self.engine) as session:
            self.assertEqual(session.query(WorkspaceRelinkPreview).count(), 0)
        token = self.preview().json()['preview_token']
        with Session(self.engine) as session:
            session.add(RoleServiceState(project_id='p', member_id='agent:p', observed_state='unknown'))
            session.commit()
        self.assertEqual(self.submit(token).json()['detail'], 'workspace_busy')
        with Session(self.engine) as session:
            self.assertIsNone(session.get(WorkspaceRelinkPreview, token).used_at)
            session.delete(session.get(RoleServiceState, ('p', 'agent:p')))
            session.add(AgentTask(project_id='p', target_member_id='agent:p', created_by='human:p', content='test', status='running'))
            session.commit()
        self.assertEqual(self.submit(token).json()['detail'], 'workspace_busy')
        with Session(self.engine) as session:
            task = session.query(AgentTask).filter_by(project_id='p').one()
            task.status, task.claimed_by = 'queued', 'agent:p'
            session.add(task)
            session.commit()
        self.assertEqual(self.submit(token).json()['detail'], 'workspace_busy')

    def test_conflict_and_patch(self):
        token = self.preview().json()['preview_token']
        (self.new / '.talk' / 'runtime.local.json').write_text('{}', encoding='utf-8')
        self.assertEqual(self.submit(token).json()['detail'], 'workspace_file_conflict')
        response = self.client.patch('/api/projects/p', headers=self.headers, json={'project_root_path': str(self.new)})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail'], 'workspace_relink_required')
        response = self.client.patch('/api/projects/p', headers=self.headers, json={'project_root_path': None})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail'], 'workspace_relink_required')

    def test_binding_validation(self):
        token = self.preview().json()['preview_token']
        self.config.write_text(json.dumps({'project_id': 'wrong', 'project_root': str(self.old)}), encoding='utf-8')
        self.assertEqual(self.submit(token).json()['detail'], 'workspace_binding_invalid')
        self.assertFalse((self.new / '.talk' / 'runtime.local.json').exists())

    def test_compensation_and_recovery(self):
        token = self.preview().json()['preview_token']
        original = self.config.read_bytes()
        with mock.patch('server.workspace_registry.save_identity', side_effect=RuntimeError('synthetic')):
            response = self.submit(token)
        self.assertEqual(response.json()['detail'], 'workspace_write_failed')
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse((self.new / '.talk' / 'runtime.local.json').exists())
        with Session(self.engine) as session:
            self.assertEqual(session.get(Project, 'p').project_root_path, str(self.old))
            self.assertEqual(session.get(WorkspaceOperation, 'op').stage, 'failed')
        token = self.preview().json()['preview_token']
        with mock.patch('server.workspace_registry.save_identity', side_effect=RuntimeError('synthetic')), \
             mock.patch('server.workspace_relink_files.rollback_write', side_effect=RuntimeError('synthetic')):
            response = self.submit(token, op='recovery')
        self.assertEqual(response.json()['detail'], 'workspace_recovery_required')
        with Session(self.engine) as session:
            self.assertEqual(session.get(WorkspaceOperation, 'recovery').stage, 'recovery_required')

    def test_nonterminal_idempotency_and_conflict(self):
        from server import workspace_operations as ops
        with Session(self.engine) as session:
            ops.begin_operation(session, 'existing', 'p', str(self.old), str(self.new), 1)
            session.commit()
        response = self.submit(None, op='existing')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['stage'], 'started')
        self.assertEqual(self.submit(None, op='existing', revision=2).json()['detail'], 'workspace_operation_conflict')
        self.assertEqual(self.submit(None, op='new').json()['detail'], 'workspace_busy')

    def test_cross_project_and_identity_change(self):
        token = self.preview().json()['preview_token']
        other = self.base / 'other'
        other.mkdir()
        with Session(self.engine) as session:
            session.add(Project(project_id='other', display_name='Other', project_root_path=str(other), maintainer_member_id='human:p'))
            session.commit()
        self.assertEqual(self.submit(token, project='other').json()['detail'], 'workspace_preview_stale')
        with mock.patch('server.routes.workspace_diagnostics.relink.candidate_snapshot', return_value={'identity': ['changed'], 'pointer_digest': None}):
            self.assertEqual(self.submit(token).json()['detail'], 'workspace_preview_stale')

    def test_duplicate_ensure(self):
        with Session(self.engine) as session:
            session.add(Project(project_id='duplicate', display_name='Duplicate', project_root_path=str(self.old), maintainer_member_id='human:p'))
            session.commit()
        with mock.patch('server.local_runtime.configured_runtime', return_value=('synthetic', {})), \
             mock.patch('server.local_runtime.ensure_local_runtime') as ensure:
            response = self.client.post('/api/local/workspaces/ensure', headers=self.headers,
                                        json={'project_root': str(self.old)})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail'], 'workspace_duplicate')
        ensure.assert_not_called()

    def test_actor_and_revision_changes(self):
        from server import workspace_registry as registry
        token = self.preview().json()['preview_token']
        with Session(self.engine) as session:
            session.add(Member(id='human:other', kind='human', display_name='Other', api_key='other-test-key'))
            registry.ensure_registration(session, 'p')
            session.commit()
        response = self.submit(token, headers={'X-API-Key': 'other-test-key'})
        self.assertEqual(response.json()['detail'], 'workspace_preview_stale')
        with Session(self.engine) as session:
            registration = registry.get_registration(session, 'p')
            registration.revision += 1
            session.add(registration)
            session.commit()
        self.assertEqual(self.submit(token).json()['detail'], 'workspace_preview_stale')

    def test_role_and_sqlite_busy_matrix(self):
        token = self.preview().json()['preview_token']
        for desired, observed in [('running', 'stopped'), ('stopped', 'running'),
                                  ('stopped', 'starting'), ('stopped', 'stopping'),
                                  ('stopped', 'unknown'), ('stopped', 'failed')]:
            with self.subTest(desired=desired, observed=observed):
                with Session(self.engine) as session:
                    role = session.get(RoleServiceState, ('p', 'agent:p'))
                    if role is None:
                        role = RoleServiceState(project_id='p', member_id='agent:p')
                    role.desired_state, role.observed_state = desired, observed
                    session.add(role)
                    session.commit()
                self.assertEqual(self.submit(token).json()['detail'], 'workspace_busy')
        with Session(self.engine) as session:
            session.delete(session.get(RoleServiceState, ('p', 'agent:p')))
            session.commit()
        with mock.patch('server.routes.workspace_diagnostics.begin_immediate_write',
                        side_effect=OperationalError('synthetic', {}, Exception('database is locked'))):
            self.assertEqual(self.submit(token).json()['detail'], 'workspace_busy')
        with Session(self.engine) as session:
            self.assertIsNone(session.get(WorkspaceRelinkPreview, token).used_at)

    def test_marker_change_after_preview(self):
        token = self.preview().json()['preview_token']
        (self.new / '.talk' / 'project.yaml').write_text('project_id: other\n', encoding='utf-8')
        self.assertEqual(self.submit(token).json()['detail'], 'workspace_preview_stale')

    def test_missing_candidate_talk_directory(self):
        (self.new / '.talk').rmdir()
        token = self.preview().json()['preview_token']
        self.assertEqual(self.submit(token).status_code, 200)
        self.assertEqual(json.loads((self.new / '.talk' / 'runtime.local.json').read_text(encoding='utf-8')), self.pointer)


if __name__ == '__main__':
    unittest.main()
