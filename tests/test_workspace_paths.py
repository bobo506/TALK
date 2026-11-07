import os
import stat
import subprocess
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
            self.assertEqual(doc['error_code'], 'key_root_mismatch')
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

    def test_derived_paths_and_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            role = w.role_dir(temp, 'p/中', 'm:1')
            paths = {
                w.native_home_dir: ('native-home',),
                w.execution_session_store_path: ('sessions', 'execution-session-store.sqlite3'),
                w.records_dir: ('state', 'records'),
                w.control_dir: ('state', 'control'),
                w.logs_dir: ('logs',),
            }
            for function, suffix in paths.items():
                self.assertEqual(function(temp, 'p/中', 'm:1'), role.joinpath(*suffix))
                for project, member in (('', 'm'), ('p', ''), ('p', 'x' * 100)):
                    with self.subTest(function=function.__name__, project=project, member=member):
                        with self.assertRaises(w.WorkspacePathError):
                            function(temp, project, member)
            for runner in ('codex', 'kimi', 'dsh', 'workbuddy'):
                self.assertEqual(w.manager_dir(temp, 'p/中', 'm:1', runner), role / 'state' / 'manager' / runner)
            for runner in ('', '../codex', 'Codex', 'x' * 200, None):
                with self.assertRaises(w.WorkspacePathError):
                    w.manager_dir(temp, 'p', 'm', runner)

    def test_workspace_error_mapping_and_worker(self):
        from scripts.role_provision import workspace_path_error_code
        from scripts.role_provision_worker import RoleProvisionWorker, WorkerError
        cases = {'key_root_inside_repo': 'key_root_inside_repo', 'key_root_mismatch': 'key_root_mismatch',
                 'path_unavailable': 'workspace_path_unavailable', 'link_refused': 'workspace_link_refused',
                 'shape_unknown': 'workspace_shape_unknown', 'invalid_id': 'workspace_id_invalid',
                 'component_too_long': 'workspace_id_invalid'}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            worker = RoleProvisionWorker.__new__(RoleProvisionWorker)
            worker.data_root, worker.repo_root, worker.project_root = root, root, root
            worker.project_id, worker.key_root, worker._storage_layout = 'p', root / 'external', 'workspace-v1'
            for raw, expected in cases.items():
                self.assertEqual(workspace_path_error_code(w.WorkspacePathError(raw)), expected)
                with patch('server.workspace_paths.deployment_shape', side_effect=w.WorkspacePathError(raw)):
                    with self.assertRaises(ProvisionError) as provision_error:
                        _workspace_key_target(root, 'p', 'm', root / 'external', root)
                    with self.assertRaises(WorkerError) as worker_error:
                        worker._paths('m')
                self.assertEqual(provision_error.exception.code, expected)
                self.assertEqual(worker_error.exception.code, expected)

    def test_worker_reports_existing_server_code_and_preserves_specific_result(self):
        from scripts.role_provision_worker import RoleProvisionWorker
        worker = RoleProvisionWorker.__new__(RoleProvisionWorker)
        worker._current_revision = Mock(return_value=3)
        worker.report = Mock(return_value={'status': 200, 'payload': {}})
        result = worker._finish_failed('request', 'lease', {}, 'workspace_link_refused')
        self.assertEqual(worker.report.call_args.kwargs['error_code'], 'http_error')
        self.assertEqual(result['error_code'], 'workspace_link_refused')
        self.assertEqual(result['report_error_code'], 'http_error')

    def test_key_layout_selection_never_falls_back(self):
        from scripts.role_provision import key_file_path
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, external = root / 'data', root / 'external'
            data.mkdir()
            external.mkdir()
            for git in (False, True):
                if git:
                    (data / '.git').mkdir()
                target = w.key_path(data, 'p', 'agent:test', git_key_root=external)
                legacy = key_file_path(external, 'agent:test')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('new', encoding='utf-8')
                legacy.write_text('legacy', encoding='utf-8')
                self.assertNotEqual(target, legacy)
                self.assertEqual(_workspace_key_target(data, 'p', 'agent:test', target.parent, data), target)
                target.unlink()
                self.assertEqual(w.key_path(data, 'p', 'agent:test', git_key_root=external), target)
                self.assertFalse(target.exists())
                self.assertEqual(legacy.read_text(encoding='utf-8'), 'legacy')

    @unittest.skipUnless(os.name == 'nt', 'real junction requires Windows')
    def test_real_junction_at_root_ancestor_and_leaf(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            inside, outside = base / 'inside', base / 'outside'
            inside.mkdir()
            outside.mkdir()
            sentinel = outside / 'sentinel'
            sentinel.write_text('unchanged', encoding='utf-8')
            for location in ('root', 'ancestor', 'leaf'):
                for destination in (inside, outside):
                    case = base / (location + '-' + destination.name)
                    case.mkdir()
                    if location == 'root':
                        link = case / 'root'
                        call = lambda: w.native_home_dir(link, 'p', 'm')
                    else:
                        role = w.role_dir(case, 'p', 'm')
                        if location == 'ancestor':
                            link = case / 'workspaces'
                            call = lambda: w.native_home_dir(case, 'p', 'm')
                        else:
                            role.mkdir(parents=True)
                            link = role / 'native-home'
                            call = lambda: w.native_home_dir(case, 'p', 'm')
                    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(destination)], capture_output=True)
                    if result.returncode:
                        self.skipTest('junction creation unavailable: exit ' + str(result.returncode))
                    try:
                        with self.assertRaises(w.WorkspacePathError) as error:
                            call()
                        self.assertEqual(error.exception.code, 'link_refused')
                        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'unchanged')
                    finally:
                        os.rmdir(link)


if __name__ == '__main__':
    unittest.main()
