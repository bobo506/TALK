"""Real isolated Windows deletion and project-wide guard counterexamples."""
import contextlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from bridges.backend_diagnostics import BackendJournal, MEMBER, project_root
from bridges.backend_log_retention import backend_receipt_valid
from bridges import runtime_log_retention as retention
from server.runtime_log_retention import RetentionService, task_guard


@contextlib.contextmanager
def allowed(*args):
    yield True


@unittest.skipUnless(os.name == 'nt', 'Checked-handle expiration is Windows-only')
class BackendRetentionTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[1]/'.tmp/backend-log-auto-retention-v1/tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.logs = self.base/'backend'
        self.project = 'project-one'
        self.root = project_root(self.logs, self.project)
        self.now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        self.engine = create_engine('sqlite:///'+str(self.base/'tasks.db'), connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE projects (project_id TEXT PRIMARY KEY)')
            conn.exec_driver_sql("INSERT INTO projects VALUES ('project-one')")
            conn.exec_driver_sql('CREATE TABLE agent_tasks (id INTEGER PRIMARY KEY, project_id TEXT, '
                'target_member_id TEXT, status TEXT, workflow_status TEXT, control_status TEXT, '
                'parent_task_id INTEGER, root_task_id INTEGER, execution_session JSON)')
            conn.exec_driver_sql('CREATE TABLE agent_task_relations (id INTEGER PRIMARY KEY, source_task_id INTEGER, '
                'target_task_id INTEGER, trigger_task_id INTEGER)')

    def writer(self, *, days=40, project=None, component='api', close=True):
        when = self.now-timedelta(days=days)
        journal = BackendJournal(self.logs, project or self.project, component, clock=lambda: when)
        self.addCleanup(journal.close)
        self.assertIsNotNone(journal.emit('backend_ready'))
        path = journal.writer._current_path
        os.utime(path, (when.timestamp(), when.timestamp()))
        if close:
            journal.close()
        return journal, path

    def task(self, task_id=1, project='project-one', member='agent:one', status='succeeded', workflow='completed', control='active', parent=None):
        with self.engine.begin() as conn:
            conn.exec_driver_sql('INSERT INTO agent_tasks VALUES (?,?,?,?,?,?,?,NULL,NULL)',
                (task_id, project, member, status, workflow, control, parent))

    def config(self, *, enabled=True):
        return {'storage': {'db_path': self.engine.url.database}, 'runtime_diagnostics': {'sources': []},
            'runtime_log_retention': {'enabled': True, 'backend_enabled': enabled},
            'backend_diagnostics': {'enabled': True, 'root': str(self.logs),
                'database_file': self.engine.url.database, 'projects': [self.project]}}

    def service(self, config=None):
        return RetentionService(self.engine, config or self.config(), clock=lambda: self.now, poll_seconds=.01)

    def test_closed_old_project_backend_expires_with_audit_and_daily_gate(self):
        journal, path = self.writer()
        receipt = retention.read_json(journal.writer.namespace/'closed.json')
        self.assertEqual(receipt['task_ids'], [])
        self.assertFalse(retention.receipt_valid(receipt, journal.writer.namespace, {(self.project, MEMBER)}))
        self.assertTrue(backend_receipt_valid(receipt, journal.writer.namespace, {(self.project, MEMBER)}))
        service = self.service()
        report = service.tick()[0]
        self.assertEqual(report['deleted_files'], 1, report)
        self.assertFalse(path.exists())
        self.assertTrue((journal.writer.namespace/'closed.json').exists())
        traces = retention.read_journal(journal.writer.namespace/'retention.jsonl')
        self.assertEqual(traces[0]['action'], 'auto_expire_intent')
        self.assertEqual(traces[1]['outcome'], 'deleted')
        self.assertEqual(service.tick()[0]['status'], 'not_due')

    def test_three_components_share_one_project_root_and_budget(self):
        paths = [self.writer(component=component)[1] for component in ('api', 'runtime', 'provision_worker')]
        report = self.service().tick()[0]
        self.assertEqual(report['deleted_files'], 3, report)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_flag_missing_or_disabled_never_touches_backend_root(self):
        _, path = self.writer()
        for value in (False, None):
            config = self.config(enabled=False)
            if value is None:
                config['runtime_log_retention'].pop('backend_enabled')
            with patch.object(retention, 'pinned', side_effect=AssertionError('source touched')):
                self.assertEqual(self.service(config).tick(), [])
        self.assertTrue(path.exists())
        self.assertFalse((self.root/'.retention-policy.json').exists())

    def test_legacy_or_invalid_backend_marker_is_protected(self):
        cases = ({'retention_scope': None}, {'backend_component': 'other'}, {'backend_component': []},
            {'instance_id': 'runtime-1'}, {'task_ids': [1]})
        for index, change in enumerate(cases):
            with self.subTest(change=change):
                journal, path = self.writer()
                receipt_path = journal.writer.namespace/'closed.json'
                receipt = retention.read_json(receipt_path)
                receipt.update(change)
                retention.write_json(receipt_path, receipt)
                self.now += timedelta(days=1)
                report = self.service().tick()[0]
                self.assertEqual(report['deleted_files'], 0, report)
                self.assertTrue(path.exists())

    def test_active_unclosed_and_recent_backend_is_protected_over_budget(self):
        active, active_path = self.writer(close=False)
        _, recent_path = self.writer(days=2)
        config = self.config()
        config['runtime_log_retention']['max_total_bytes'] = 1
        report = self.service(config).tick()[0]
        self.assertEqual(report['deleted_files'], 0)
        self.assertTrue(report['over_budget'])
        self.assertTrue(active_path.exists() and recent_path.exists())
        active.close()

    def test_live_lease_blocks_even_closed_backend(self):
        journal, path = self.writer()
        with retention.NativeFile(journal.writer.namespace/'run.lease', write=True):
            self.assertEqual(self.service().tick()[0]['deleted_files'], 0)
        self.assertTrue(path.exists())

    def test_unregistered_project_and_wrong_project_hash_protected(self):
        _, foreign = self.writer(project='project-other')
        journal, path = self.writer()
        receipt = retention.read_json(journal.writer.namespace/'closed.json')
        receipt['project_id'] = 'project-other'
        self.assertFalse(backend_receipt_valid(receipt, journal.writer.namespace, {('project-other', MEMBER)}))
        retention.write_json(journal.writer.namespace/'closed.json', receipt)
        report = self.service().tick()[0]
        self.assertEqual(report['deleted_files'], 0)
        self.assertTrue(foreign.exists() and path.exists())

    def test_missing_project_root_is_protected_without_creating_it(self):
        report = self.service().tick()[0]
        self.assertEqual(report['status'], 'protected')
        self.assertFalse(self.root.exists())

    def test_wrong_database_or_disabled_backend_does_not_delete(self):
        _, path = self.writer()
        for change in ({'database_file': str(self.base/'other.db')}, {'enabled': False}):
            config = self.config()
            config['backend_diagnostics'].update(change)
            report = self.service(config).tick()[0]
            self.assertEqual(report['reason'], 'backend_binding_unavailable')
        config = self.config()
        config['storage']['db_path'] = str(self.base/'wrong.db')
        self.assertFalse(self.service(config).enabled)
        self.assertTrue(path.exists())

    def test_project_tasks_from_different_roles_must_all_be_terminal(self):
        self.task(1)
        self.task(2, member='agent:two')
        with task_guard(self.engine, self.project, MEMBER, [], project_wide=True) as safe:
            self.assertTrue(safe)
        for update in ("status='running'", "workflow_status='submitted'", "control_status='paused'"):
            with self.engine.begin() as conn:
                conn.exec_driver_sql('UPDATE agent_tasks SET '+update+' WHERE id=2')
            with task_guard(self.engine, self.project, MEMBER, [], project_wide=True) as safe:
                self.assertFalse(safe)
            with self.engine.begin() as conn:
                conn.exec_driver_sql("UPDATE agent_tasks SET status='succeeded',workflow_status='completed',control_status='active'")

    def test_missing_project_and_wrong_scope_do_not_use_taskless_exception(self):
        for project, member, ids in (('missing', MEMBER, []), (self.project, 'agent:one', []), (self.project, MEMBER, [1])):
            with task_guard(self.engine, project, member, ids, project_wide=True) as safe:
                self.assertFalse(safe)
        with task_guard(self.engine, self.project, MEMBER, []) as safe:
            self.assertFalse(safe)

    def test_unfinished_or_paused_task_prevents_real_deletion(self):
        self.task(control='paused')
        _, path = self.writer()
        report = self.service().tick()[0]
        self.assertEqual(report['deleted_files'], 0)
        self.assertIn('unfinished_or_unknown_task_reference', report['protected_reasons'])
        self.assertTrue(path.exists())

    def test_foreign_parent_relation_and_missing_ancestor_protect_project(self):
        self.task(1, parent=2)
        for add_foreign in (False, True):
            if add_foreign:
                self.task(2, project='project-other')
            with task_guard(self.engine, self.project, MEMBER, [], project_wide=True) as safe:
                self.assertFalse(safe)
        with self.engine.begin() as conn:
            conn.exec_driver_sql('UPDATE agent_tasks SET parent_task_id=NULL WHERE id=1')
            conn.exec_driver_sql('INSERT INTO agent_task_relations VALUES (1,1,2,NULL)')
        with task_guard(self.engine, self.project, MEMBER, [], project_wide=True) as safe:
            self.assertFalse(safe)

    def test_project_task_graph_limit_protects(self):
        self.task(1)
        self.task(2)
        with patch.object(retention, 'MAX_TASKS', 1):
            with task_guard(self.engine, self.project, MEMBER, [], project_wide=True) as safe:
                self.assertFalse(safe)

    def test_invalid_database_task_identity_is_not_trusted(self):
        self.task(-1)
        with task_guard(self.engine, self.project, MEMBER, [], project_wide=True) as safe:
            self.assertFalse(safe)

    def test_database_reservation_blocks_task_resume_until_delete_finishes(self):
        self.task()
        with task_guard(self.engine, self.project, MEMBER, [], project_wide=True) as safe:
            self.assertTrue(safe)
            with self.engine.connect() as other:
                other.exec_driver_sql('PRAGMA busy_timeout=0')
                with self.assertRaises(Exception):
                    other.exec_driver_sql("UPDATE agent_tasks SET control_status='paused'")
                other.rollback()

    def test_background_start_catchup_requires_no_frontend(self):
        _, path = self.writer()
        service = self.service()
        service.start()
        try:
            deadline = time.monotonic()+4
            while path.exists() and time.monotonic() < deadline:
                time.sleep(.01)
        finally:
            service.stop()
        self.assertFalse(path.exists())
        self.assertFalse(service.thread.is_alive())

    def test_backend_and_role_root_overlap_is_protected(self):
        _, path = self.writer()
        config = self.config()
        config['runtime_diagnostics']['sources'] = [{'project_id': self.project, 'member_id': 'agent:one', 'root': str(self.root)}]
        reports = self.service(config).tick()
        self.assertEqual(reports[-1]['reason'], 'backend_root_unavailable_or_overlapping')
        self.assertTrue(path.exists())

    def test_backend_flag_must_be_boolean(self):
        config = self.config()
        config['runtime_log_retention']['backend_enabled'] = 'true'
        with self.assertRaises(ValueError):
            self.service(config)

    def test_source_extension_cannot_override_core_closure_facts(self):
        journal, path = self.writer(close=False)
        journal.writer._closed_receipt_extra = lambda: {'complete': True}
        journal.close()
        self.assertFalse((journal.writer.namespace/'closed.json').exists())
        self.assertEqual(self.service().tick()[0]['deleted_files'], 0)
        self.assertTrue(path.exists())

    def test_busy_database_protects_old_closed_backend(self):
        _, path = self.writer()
        with self.engine.connect() as owner:
            owner.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                report = self.service().tick()[0]
            finally:
                owner.rollback()
        self.assertEqual(report['deleted_files'], 0)
        self.assertEqual(report['status'], 'partial')
        self.assertTrue(path.exists())

    def test_two_explicit_projects_keep_separate_scope_and_root_budget(self):
        _, first = self.writer()
        _, second = self.writer(project='project-two')
        with self.engine.begin() as conn:
            conn.exec_driver_sql("INSERT INTO projects VALUES ('project-two')")
        config = self.config()
        config['backend_diagnostics']['projects'].append('project-two')
        reports = self.service(config).tick()
        self.assertEqual({row['project_id'] for row in reports}, {self.project, 'project-two'})
        self.assertEqual([row['deleted_files'] for row in reports], [1, 1])
        self.assertTrue(all(row['max_total_bytes'] == 1024**3 for row in reports))
        self.assertFalse(first.exists() or second.exists())


if __name__ == '__main__':
    unittest.main()
