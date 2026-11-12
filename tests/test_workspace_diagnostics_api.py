"""HTTP integration tests against an isolated in-memory database and test roots."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import server.db as db
import server.local_runtime as runtime
import server.main as main
import server.workspace_diagnostics as core
from server.db import get_session
from server.models import Member, Project


class WorkspaceDiagnosticsApiTests(unittest.TestCase):
    def setUp(self):
        base = Path('.tmp/wd1-impl2')
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / 'root'
        self.root.mkdir()
        self.other = self.base / 'other'
        self.other.mkdir()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            s.add_all([Member(id='human:test', kind='human', display_name='Human', api_key='human-test-key'),
                       Member(id='human:operator', kind='human', display_name='Operator', api_key='operator-test-key'),
                       Member(id='human:disabled', kind='human', display_name='Disabled', api_key='disabled-test-key', disabled_at=datetime.now(timezone.utc)),
                       Member(id='agent:test', kind='agent', display_name='Agent', api_key='agent-test-key'),
                       Project(project_id='project-a', display_name='A', project_root_path=str(self.root), maintainer_member_id='human:test')])
            s.commit()
        def session_override():
            with Session(self.engine) as s:
                yield s
        main.app.dependency_overrides[get_session] = session_override
        self.addCleanup(main.app.dependency_overrides.pop, get_session, None)
        self.mode = mock.patch.object(db, 'AUTH_MODE', 'key')
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.headers = {'X-API-Key': 'human-test-key'}
        self.url = '/api/projects/project-a/workspace-diagnostics'
        self.preview_url = '/api/projects/project-a/workspace-relink-preview'

    def project(self, pid, path):
        with Session(self.engine) as s:
            s.add(Project(project_id=pid, display_name=pid, project_root_path=str(path) if path is not None else None, maintainer_member_id='human:test'))
            s.commit()

    def set_root(self, path):
        with Session(self.engine) as s:
            p = s.get(Project, 'project-a')
            p.project_root_path = str(path) if path is not None else None
            s.add(p)
            s.commit()

    def marker(self, root, pid):
        (root / '.talk').mkdir(exist_ok=True)
        (root / '.talk' / 'project.yaml').write_text('project_id: ' + pid + '\nprivate_value: SAMPLE_PRIVATE_VALUE\n', encoding='utf-8')

    def get(self, key='human-test-key', url=None):
        return self.client.get(url or self.url, headers={'X-API-Key': key})

    def preview(self, path, key='human-test-key', url=None):
        return self.client.post(url or self.preview_url, headers={'X-API-Key': key}, json={'candidate_root': str(path)})

    def test_permissions_and_validation(self):
        for key, expected in [('human-test-key', 200), ('operator-test-key', 200), ('agent-test-key', 403), ('disabled-test-key', 403), ('invalid-key', 401)]:
            with self.subTest(key=key):
                self.assertEqual(self.get(key).status_code, expected)
                self.assertEqual(self.preview(self.root, key).status_code, expected)
        self.assertEqual(self.get(url='/api/projects/no-such/workspace-diagnostics').status_code, 404)
        self.assertEqual(self.preview(self.root, url='/api/projects/no-such/workspace-relink-preview').status_code, 404)
        malformed = self.client.post(self.preview_url, headers=self.headers, json='PRIVATE_MALFORMED_BODY')
        self.assertEqual(malformed.status_code, 422)
        self.assertNotIn('PRIVATE_MALFORMED_BODY', malformed.text)
        for bad in ['', '  ', 'relative/path', 'x' * 32768, str(self.root) + '\x00x']:
            with self.subTest(bad=repr(bad[:20])):
                response = self.preview(bad)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(bad if bad else 'impossible', response.text)

    def test_root_states_and_unknown_identity(self):
        self.assertEqual(self.get().json()['root_status'], 'ok')
        self.set_root(self.base / 'missing')
        self.assertEqual(self.get().json()['root_status'], 'missing')
        file = self.base / 'file'
        file.write_text('content', encoding='utf-8')
        self.set_root(file)
        self.assertEqual(self.get().json()['root_status'], 'invalid')
        self.set_root(None)
        self.assertEqual(self.get().json()['root_status'], 'unconfigured')
        self.set_root(self.root)
        with mock.patch.object(core, '_identity', return_value=None):
            result = self.get().json()
        self.assertEqual(result['identity_confidence'], 'unknown')
        self.assertIn('workspace_identity_unknown', [x['code'] for x in result['issues']])
        self.assertEqual(result['duplicate_check'], 'unknown')

    def test_trusted_operator_read_only(self):
        with mock.patch.object(db, 'AUTH_MODE', 'trusted'), mock.patch('server.routes.workspace_diagnostics.is_trusted_host', return_value=True):
            self.assertEqual(self.client.get(self.url).status_code, 200)
            with Session(self.engine) as session:
                operator = session.get(Member, 'human:operator')
                session.delete(operator)
                session.commit()
            self.assertEqual(self.client.get(self.url).status_code, 401)
            with Session(self.engine) as session:
                self.assertIsNone(session.get(Member, 'human:operator'))

    def test_duplicates_and_unknown(self):
        self.project('project-b', self.root / '..' / 'root')
        self.project('project-c', self.other)
        self.project('project-unknown', self.base / 'missing')
        result = self.get().json()
        self.assertEqual(result['duplicate_projects'], ['project-b'])
        self.assertEqual(result['duplicate_check'], 'unknown')
        self.assertIn('project-unknown', result['duplicate_unknown_projects'])
        other = self.get(url='/api/projects/project-c/workspace-diagnostics').json()
        self.assertEqual(other['duplicate_projects'], [])

    def test_preview_matrix(self):
        def checked(path):
            response = self.preview(path)
            result = response.json()
            if result['blocked_reasons']:
                self.assertEqual(response.status_code, 409)
                self.assertTrue(result['code'].startswith('workspace_'))
                self.assertNotIn('preview_token', result)
            else:
                self.assertEqual(response.status_code, 200)
                self.assertIn('preview_token', result)
            return result
        self.marker(self.root, 'project-a')
        alias = self.root / '..' / 'root'
        got = checked(alias)
        self.assertEqual((got['code'], got['match_confidence']), ('workspace_move_candidate', 'strong'))
        copy = self.base / 'copy'
        shutil.copytree(self.root, copy)
        self.assertEqual(checked(copy)['code'], 'marker_only')
        with mock.patch.object(core, '_identity', return_value=None):
            weak = checked(copy)
        self.assertEqual((weak['code'], weak['match_confidence']), ('workspace_identity_unverified', 'unknown'))
        self.marker(copy, 'project-b')
        got = checked(copy)
        self.assertEqual(got['code'], 'workspace_marker_conflict')
        self.assertIn('workspace_marker_conflict', [r['code'] for r in got['blocked_reasons']])
        got = checked(self.base / 'absent')
        self.assertEqual(got['code'], 'workspace_root_missing')
        self.assertIn('workspace_root_missing', [r['code'] for r in got['blocked_reasons']])
        real_stat = Path.stat
        def fake_stat(path, *args, **kwargs):
            if path == self.other:
                raise PermissionError(13, 'private local details')
            return real_stat(path, *args, **kwargs)
        with mock.patch.object(Path, 'stat', fake_stat):
            got = checked(self.other)
        self.assertEqual(got['code'], 'workspace_root_inaccessible')
        self.assertIn('workspace_root_inaccessible', [r['code'] for r in got['blocked_reasons']])
        self.project('project-b', self.other)
        got = checked(self.other)
        self.assertEqual(got['code'], 'workspace_duplicate')
        self.assertEqual(got['conflict_project_ids'], ['project-b'])
        self.assertIn({'code': 'workspace_duplicate', 'project_ids': ['project-b']}, got['blocked_reasons'])
        moved = self.base / 'moved'
        self.root.rename(moved)
        got = checked(moved)
        self.assertEqual((got['code'], got['match_confidence']), ('workspace_identity_unverified', 'unknown'))

    def test_read_only_and_safe_response(self):
        self.marker(self.root, 'project-a')
        (self.root / 'data.txt').write_text('untouched', encoding='utf-8')
        def snapshot(root):
            return sorted((str(p.relative_to(root)), p.is_dir(), None if p.is_dir() else p.read_bytes()) for p in root.rglob('*'))
        def database():
            with self.engine.connect() as conn:
                names = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))]
                return {n: [tuple(row) for row in conn.execute(text('SELECT * FROM "' + n + '"'))] for n in names}
        before = (snapshot(self.root), snapshot(self.other), database())
        with mock.patch.object(runtime, 'ensure_local_runtime') as ensure:
            get = self.get()
            post = self.preview(self.other)
            ensure.assert_not_called()
        after = (snapshot(self.root), snapshot(self.other), database())
        self.assertEqual(before[:2], after[:2])
        for name in before[2]:
            if name == 'workspace_relink_previews':
                self.assertEqual(len(after[2][name]), len(before[2][name]) + 1)
            else:
                self.assertEqual(before[2][name], after[2][name], name)
        self.assertFalse((self.other / '.talk').exists())
        get_json, post_json = get.json(), post.json()
        self.assertIn('preview_token', post_json)
        self.assertIn('expires_at', post_json)
        post_json['preview_token'] = '<redacted>'
        # Preserve complete response shapes while removing machine-specific IDs.
        for data in (get_json, post_json):
            data['revision'] = '<redacted opaque revision>'
            if data['identity']:
                data['identity']['volume_id'] = '<redacted>'
                data['identity']['file_id'] = '<redacted>'
        samples = {
            'GET /api/projects/project-a/workspace-diagnostics': {'request': {}, 'response': get_json},
            'POST /api/projects/project-a/workspace-relink-preview': {'request': {'candidate_root': '<temporary absolute path>'}, 'response': post_json},
        }
        Path('.tmp/wd1-impl2/api-samples.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding='utf-8')
        for response in (get, post):
            self.assertEqual(response.status_code, 200)
            text_body = response.text
            for forbidden in ('human-test-key', 'SAMPLE_PRIVATE_VALUE', str(self.base), 'api_key', 'development_requirements', 'machine'):
                self.assertNotIn(forbidden, text_body)

    def test_untrusted_marker_path_is_not_reflected(self):
        self.marker(self.other, 'C:/sensitive/private/path')
        result = self.preview(self.other)
        self.assertEqual(result.json()['code'], 'workspace_marker_conflict')
        self.assertIsNone(result.json()['candidate_marker']['project_id'])
        self.assertNotIn('sensitive/private/path', result.text)

    @unittest.skipUnless(os.name == 'nt', 'Windows junction requires Windows')
    def test_junction_alias(self):
        import subprocess
        alias = self.base / 'junction'
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(self.root)], capture_output=True)
        if result.returncode:
            self.skipTest('junction creation unsupported')
        self.addCleanup(lambda: os.rmdir(alias) if alias.exists() else None)
        self.assertEqual(self.preview(alias).json()['code'], 'workspace_move_candidate')
        self.project('project-b', alias)
        self.assertIn('project-b', self.get().json()['duplicate_projects'])

    @unittest.skipUnless(os.name == 'nt', 'Windows 8.3 requires Windows')
    def test_short_name_alias(self):
        import ctypes
        root = self.base / 'long workspace name for short alias'
        root.mkdir()
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(str(root), buffer, len(buffer))
        if not length or length >= len(buffer) or os.path.normcase(buffer.value) == os.path.normcase(str(root)):
            self.skipTest('8.3 short name unavailable on this volume')
        self.set_root(root)
        self.assertEqual(self.preview(buffer.value).json()['code'], 'workspace_move_candidate')


if __name__ == '__main__':
    unittest.main()
