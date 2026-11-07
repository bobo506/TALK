import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from server import workspace_paths as w
from cli.profiles import resolve_workspace_profile_reference
from scripts.role_provision import _workspace_key_target, HttpResponse, ProvisionError


class WorkspacePathsTests(unittest.TestCase):
    def test_encoding(self):
        a = w.project_component('A/中:*')
        self.assertEqual(a, w.project_component('A/中:*'))
        self.assertRegex(a, r'^p-[a-z2-7]+$')
        self.assertNotEqual(a, w.project_component('a/中:*'))
        for value in ('', 'x' * 100):
            with self.assertRaises(w.WorkspacePathError):
                w.member_component(value)

    def test_shapes_keys_and_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = w.project_component('p')
            path = w.key_path(root, 'p', 'm')
            self.assertEqual(path, root / 'keys' / project / (w.member_component('m') + '.key'))
            self.assertEqual(_workspace_key_target(root, 'p', 'm', path.parent, root), path)
            with self.assertRaises(ProvisionError):
                _workspace_key_target(root, 'p', 'm', root / 'keys', root)
            (root / '.git').mkdir()
            self.assertEqual(w.deployment_shape(root), 'git')
            with self.assertRaises(ProvisionError):
                _workspace_key_target(root, 'p', 'm', path.parent, root)
            (root / '.git').rmdir()
            (root / '.git').write_text('gitdir: elsewhere', encoding='utf-8')
            self.assertEqual(w.deployment_shape(root), 'git')
            self.assertFalse(w.is_within(root.parent / (root.name + '-sibling'), root))
            with patch.object(Path, 'lstat', side_effect=PermissionError('denied')):
                with self.assertRaises(w.WorkspacePathError):
                    w.deployment_shape(root)

    def test_provision_guard_integration(self):
        from scripts.role_provision import run_provision
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / 'project'
            project.mkdir()
            key = w.key_path(root, 'project-id', 'agent:test')
            canary_key = 'workspace-v1-canary-0123456789abcdef'
            transport = Mock()
            def fake_request(method, url, **request_kwargs):
                if url.endswith('/api/members/me'):
                    return HttpResponse(200, {'id': 'agent:test'})
                if method == 'GET':
                    return HttpResponse(200, {
                        'revision': 1,
                        'status': 'pending',
                        'credential_version': 1,
                        'role_credential_version': 1,
                        'steps': {step: {'state': 'pending', 'attempts': 0} for step in ('profile', 'key_file', 'preflight')},
                    })
                return HttpResponse(200, {'revision': request_kwargs['body']['revision'] + 1})
            transport.request_json.side_effect = fake_request
            kwargs = dict(project_id='project-id', member_id='agent:test', operation_key='operation-123', project_root=project, repo_root=root, data_root=root, storage_layout='workspace-v1', apply=False, steps='profile,key_file', environ={'TALK_ROLE_API_KEY': canary_key, 'TALK_OPERATOR_API_KEY': 'operator-canary-0123456789abcdef'}, transport=transport)
            doc, code = run_provision(key_root=key.parent, **kwargs)
            self.assertEqual(code, 0, doc)
            self.assertEqual(doc['key_file_path'], str(key))
            doc, code = run_provision(key_root=key.parent, **{**kwargs, 'apply': True})
            self.assertEqual(code, 0, doc)
            self.assertIsNone(doc['error_code'])
            self.assertEqual(doc['conclusion'], 'applied')
            self.assertEqual(key.read_text(encoding='utf-8').strip(), canary_key)
            profiles = w.profiles_dir(root, 'project-id', 'agent:test')
            for name in ('IDENTITY.md', 'SOUL.md', 'USER.md'):
                self.assertTrue((profiles / name).is_file())
            doc, code = run_provision(key_root=root / 'other', **kwargs)
            self.assertEqual(code, 1)
            self.assertEqual(doc['error_code'], 'key_root_inside_repo')
            (root / '.git').mkdir()
            doc, code = run_provision(key_root=key.parent, **kwargs)
            self.assertEqual(code, 1)
            self.assertEqual(doc['error_code'], 'key_root_inside_repo')

    def test_migration_twice_with_old_rows(self):
        from sqlmodel import Session, create_engine
        from server import db
        from server.models import ProjectRole, RoleProvisionRequestRow
        with tempfile.TemporaryDirectory() as temp:
            engine = create_engine('sqlite:///' + str(Path(temp) / 'isolated.db'))
            with patch.object(db, 'engine', engine):
                db.init_db()
                with Session(engine) as session:
                    session.add(ProjectRole(project_id='p', member_id='m', role_name='r', created_by='tester'))
                    session.add(RoleProvisionRequestRow(request_key='request', project_id='p', kind='recover', request_fingerprint='fingerprint', created_by='tester'))
                    session.commit()
                with engine.begin() as conn:
                    for table in ('project_roles', 'role_provision_requests'):
                        conn.exec_driver_sql(f'ALTER TABLE {table} DROP COLUMN storage_layout')
                db.init_db()
                db.init_db()
                with engine.connect() as conn:
                    for table in ('project_roles', 'role_provision_requests'):
                        self.assertEqual(conn.exec_driver_sql(f'SELECT storage_layout FROM {table}').scalar_one(), 'legacy')
            engine.dispose()

    def test_marker_error_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            original = Path.lstat
            def failing_marker(path):
                if path == root / '.git':
                    raise PermissionError('denied')
                return original(path)
            with patch.object(Path, 'lstat', failing_marker):
                with self.assertRaises(w.WorkspacePathError):
                    w.deployment_shape(root)
            try:
                (root / 'workspaces').symlink_to(Path(outside), target_is_directory=True)
            except OSError:
                self.skipTest('symlink creation unavailable on this host')
            with self.assertRaises(w.WorkspacePathError):
                w.workspace_root(root, 'p')

    def test_missing_data_root_and_simulated_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(w.WorkspacePathError):
                w.deployment_shape(root / 'missing')
            original = Path.lstat
            def symlink_stat(path):
                if path == root / 'workspaces':
                    return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
                return original(path)
            with patch.object(Path, 'lstat', symlink_stat):
                with self.assertRaises(w.WorkspacePathError):
                    w.workspace_root(root, 'p')

    def test_profile_references(self):
        with tempfile.TemporaryDirectory() as temp:
            ref = 'workspace-v1:roles/' + w.member_component('m') + '/profiles/IDENTITY.md'
            self.assertEqual(resolve_workspace_profile_reference(temp, 'p', 'm', 'workspace-v1', ref), w.profiles_dir(temp, 'p', 'm') / 'IDENTITY.md')
            for bad in (ref.replace('IDENTITY.md', '../IDENTITY.md'), 'workspace-v1:/etc/passwd', ref.replace('IDENTITY.md', 'BAD.md'), ref.replace(w.member_component('m'), w.member_component('other'))):
                with self.assertRaises(w.WorkspacePathError):
                    w.resolve_profile_reference(temp, 'p', 'm', 'workspace-v1', bad)
            with self.assertRaises(w.WorkspacePathError):
                w.resolve_profile_reference(temp, 'p', 'm', 'legacy', ref)


if __name__ == '__main__':
    unittest.main()
