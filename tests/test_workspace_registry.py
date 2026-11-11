"""Storage contract tests using synthetic projects and isolated SQLite databases."""
import ast
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect
from sqlmodel import Session, create_engine

import server.db as db
from server.models import Member, Project
from server.workspace_registry import (
    WorkspaceRegistryError, ensure_registration, get_registration, save_identity,
)


IDENTITY = {"platform": "nt", "volume_id": 42, "file_id": 123,
            "collected_at": "2026-01-01T12:00:00+08:00", "machine": "ignored"}


class WorkspaceRegistryTests(unittest.TestCase):
    def setUp(self):
        base = Path('.tmp/wd1-impl3a')
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.engine = create_engine('sqlite:///' + (Path(self.tmp.name) / 'test.sqlite').as_posix())
        self.addCleanup(self.engine.dispose)
        with patch.object(db, 'engine', self.engine):
            db.init_db()
        with Session(self.engine) as session:
            session.add(Member(id='human:test', kind='human', display_name='Test', api_key='synthetic'))
            session.add(Project(project_id='p1', display_name='One', maintainer_member_id='human:test'))
            session.commit()

    def assert_code(self, code, function, *args):
        with self.assertRaises(WorkspaceRegistryError) as error:
            function(*args)
        self.assertEqual(str(error.exception), code)
        self.assertEqual(error.exception.code, code)

    def test_old_database_migration_and_no_backfill(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE workspace_registrations')
        def snapshot():
            with self.engine.connect() as conn:
                tables = [r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                schema = {t: conn.exec_driver_sql(f'PRAGMA table_info("{t}")').fetchall() for t in tables}
                rows = {t: conn.exec_driver_sql(f'SELECT * FROM "{t}"').fetchall() for t in tables}
                return tables, schema, rows
        before = snapshot()
        with patch.object(db, 'engine', self.engine):
            db.init_db()
            db.init_db()
        after = snapshot()
        self.assertEqual(set(after[0]) - set(before[0]), {'workspace_registrations'})
        self.assertNotIn('workspace_operations', after[0])
        for table in before[0]:
            self.assertEqual(before[1][table], after[1][table], table)
            self.assertEqual(before[2][table], after[2][table], table)
        self.assertEqual(len(after[2]['projects']), 1)
        self.assertEqual(after[2]['workspace_registrations'], [])
        indexes = inspect(self.engine).get_indexes('workspace_registrations')
        self.assertEqual([i['name'] for i in indexes], ['ix_workspace_registrations_updated_at'])
        print(f'MIGRATION old_tables={len(before[0])} new_tables={len(after[0])}; existing_schema_and_rows=unchanged; projects=1->1; registrations=0; indexes={[i["name"] for i in indexes]}')
        print('FIELDS ' + repr(after[1]['workspace_registrations']))

    def test_create_cas_conflict_clear_and_rollback(self):
        with Session(self.engine) as s:
            self.assertIsNone(get_registration(s, 'p1'))
            row = ensure_registration(s, 'p1')
            self.assertEqual((row.revision, row.identity_platform, row.identity_file_id), (1, None, None))
            s.commit()
            row = save_identity(s, 'p1', IDENTITY, 1)
            self.assertEqual((row.revision, row.identity_platform, row.identity_volume_id, row.identity_file_id), (2, 'nt', 42, 123))
            self.assertEqual(row.identity_collected_at, datetime(2026, 1, 1, 4))
            s.commit()
            print('CAS success expected=1 revision=2; second expected=1 -> workspace_revision_conflict')
            self.assert_code('workspace_revision_conflict', save_identity, s, 'p1', None, 1)
            self.assertEqual((get_registration(s, 'p1').revision, get_registration(s, 'p1').identity_file_id), (2, 123))
            self.assertEqual(ensure_registration(s, 'p1').revision, 2)
            row = save_identity(s, 'p1', None, 2)
            self.assertEqual((row.revision, row.identity_platform, row.identity_volume_id, row.identity_file_id, row.identity_collected_at), (3, None, None, None, None))
            s.rollback()
            self.assertEqual((get_registration(s, 'p1').revision, get_registration(s, 'p1').identity_file_id), (2, 123))
        with Session(self.engine) as s:
            save_identity(s, 'p1', None, 2)
            s.commit()
        with Session(self.engine) as s:
            self.assertEqual((get_registration(s, 'p1').revision, get_registration(s, 'p1').identity_platform), (3, None))

    def test_invalid_identities_do_not_write(self):
        with Session(self.engine) as s:
            ensure_registration(s, 'p1')
            s.commit()
            before = get_registration(s, 'p1').model_dump()
            for field, bad in [('platform', 'posix; DROP TABLE projects'), ('platform', None),
                               ('volume_id', True), ('volume_id', -1), ('volume_id', 2**63), ('volume_id', '1'),
                               ('file_id', False), ('file_id', -1), ('file_id', 2**63), ('file_id', '1'),
                               ('collected_at', '2026-01-01T00:00:00'), ('collected_at', datetime.now()),
                               ('collected_at', 'invalid')]:
                with self.subTest(field=field, bad=bad):
                    self.assert_code('workspace_identity_invalid', save_identity, s, 'p1', {**IDENTITY, field: bad}, 1)
                    self.assertEqual(get_registration(s, 'p1').model_dump(), before)
            self.assert_code('workspace_identity_invalid', save_identity, s, 'p1', [], 1)
            self.assertEqual(get_registration(s, 'p1').model_dump(), before)
            s.commit()

    def test_missing_project_and_unregistered_revision(self):
        with Session(self.engine) as s:
            self.assert_code('workspace_project_not_found', ensure_registration, s, 'missing')
            self.assert_code('workspace_project_not_found', save_identity, s, 'missing', IDENTITY, 1)
            self.assertIsNone(get_registration(s, 'missing'))
            self.assert_code('workspace_revision_conflict', save_identity, s, 'p1', IDENTITY, 1)
            self.assertIsNone(get_registration(s, 'p1'))

    def test_no_io_in_registry_module(self):
        source = Path('server/workspace_registry.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual(modules, {'datetime', 'collections.abc', 'sqlalchemy', 'sqlalchemy.dialects.sqlite', 'sqlmodel', 'server.models'})
        self.assertFalse(any(isinstance(node, ast.Import) for node in ast.walk(tree)))
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'open', 'exec', 'eval', '__import__'} for node in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
