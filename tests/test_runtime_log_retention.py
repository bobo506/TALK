import contextlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from bridges import runtime_log_retention as retention
from bridges.runtime_diagnostics import RuntimeDiagnostics, DiagnosticsPolicy


@contextlib.contextmanager
def allowed(*_):
    yield True


@contextlib.contextmanager
def denied(*_):
    yield False


@unittest.skipUnless(os.name == "nt", "Deletion backend is explicitly Windows-only")
class RetentionTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1] / ".tmp/local-log-auto-retention-v1/tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "logs"
        self.root.mkdir()
        self.now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        self.scopes = {("project-one", "agent:one")}

    def writer(self, *, days=40, project="project-one", member="agent:one", task=315, close=True):
        when = self.now - timedelta(days=days)
        writer = RuntimeDiagnostics(member_id=member, project_id=project, instance_id="instance-one",
                                    policy=DiagnosticsPolicy.create(root=self.root), clock=lambda: when)
        self.addCleanup(writer.close)
        ref = writer.record_event("bridge_started", stage="bridge", task_id=task)
        path = writer._current_path
        self.assertIsNotNone(ref)
        os.utime(path, (when.timestamp(), when.timestamp()))
        if close:
            writer.close()
        return writer, path, ref

    def sweep(self, **kwargs):
        return retention.sweep(self.root, self.scopes, kwargs.pop("guard", allowed), now=self.now, **kwargs)

    def test_real_closed_old_run_expires_and_reference_is_explained(self):
        writer, path, ref = self.writer()
        result = self.sweep()
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(result["deleted_files"], 1)
        self.assertFalse(path.exists())
        self.assertTrue((writer.namespace / "manifest.json").exists())
        self.assertTrue((writer.namespace / "closed.json").exists())
        self.assertTrue(retention.expired_reference(self.root, "project-one", "agent:one", ref))
        self.assertFalse(retention.expired_reference(self.root, "project-other", "agent:one", ref))
        traces = retention.read_journal(writer.namespace / "retention.jsonl")
        self.assertEqual(traces[0]["action"], "auto_expire_intent")
        self.assertEqual(traces[1]["outcome"], "deleted")

    def test_active_unclosed_and_legacy_runs_are_protected(self):
        writer, path, _ = self.writer(close=False)
        result = self.sweep()
        self.assertEqual(result["deleted_files"], 0)
        self.assertTrue(path.exists())
        writer.close()
        (writer.namespace / "closed.json").unlink()
        self.now += timedelta(days=2)
        self.assertEqual(self.sweep()["deleted_files"], 0)
        self.assertTrue(path.exists())

    def test_live_lease_blocks_even_with_closed_receipt(self):
        writer, path, _ = self.writer()
        with retention.NativeFile(writer.namespace / "run.lease", write=True):
            result = self.sweep()
        self.assertEqual(result["deleted_files"], 0)
        self.assertTrue(path.exists())

    def test_recent_and_unknown_project_or_member_protected_even_over_capacity(self):
        paths = [self.writer(days=2)[1], self.writer(project="project-other")[1],
                 self.writer(member="agent:other")[1]]
        result = self.sweep(max_total_bytes=1)
        self.assertTrue(result["over_budget"])
        self.assertEqual(result["deleted_files"], 0)
        self.assertTrue(all(p.exists() for p in paths))

    def test_task_references_must_be_safe_and_marker_tracks_ids(self):
        writer, path, _ = self.writer(task="315")
        receipt = retention.read_json(writer.namespace / "closed.json")
        self.assertEqual(receipt["task_ids"], [315])
        self.assertEqual(self.sweep(guard=denied)["deleted_files"], 0)
        self.assertTrue(path.exists())

    def test_no_task_reference_protects_even_closed_old_run(self):
        _, path, _ = self.writer(task=None)
        self.assertEqual(self.sweep()["deleted_files"], 0)
        self.assertTrue(path.exists())

    def test_directory_changes_during_task_reservation_protect_and_audit(self):
        for change in ("add", "remove"):
            with self.subTest(change=change):
                writer, path, _ = self.writer()
                @contextlib.contextmanager
                def mutate(*_):
                    if change == "add":
                        (writer.namespace / "events-99999.jsonl").write_bytes(b"{}\n")
                    else:
                        path.unlink()
                    yield True
                result = self.sweep(guard=mutate)
                self.assertEqual(result["status"], "partial", result)
                self.assertEqual(result["deleted_files"], 0)
                if change == "add":
                    self.assertTrue(path.exists())
                traces = retention.read_journal(writer.namespace / "retention.jsonl")
                self.assertEqual(traces[-1]["action"], "auto_expire_protected")
                self.now += timedelta(minutes=6)

    def test_external_addition_during_final_expire_is_partial(self):
        writer, path, _ = self.writer()
        original = retention.NativeFile.expire
        def mutate(handle, expected):
            (writer.namespace / "events-99999.jsonl").write_bytes(b"{}\n")
            return original(handle, expected)
        with mock.patch.object(retention.NativeFile, "expire", mutate):
            result = self.sweep()
        self.assertEqual(result["status"], "partial")
        self.assertFalse(path.exists())  # Completed exact deletion is honestly audited.
        self.assertEqual(result["deleted_files"], 1)

    def test_incomplete_evidence_or_changed_file_protects(self):
        writer, path, _ = self.writer(task="unknown-task")
        self.assertFalse(retention.read_json(writer.namespace / "closed.json")["complete"])
        other, changed, _ = self.writer()
        changed.write_bytes(b"changed after close")
        result = self.sweep()
        self.assertEqual(result["deleted_files"], 0)
        self.assertTrue(path.exists())
        self.assertTrue(changed.exists())

    def test_daily_due_startup_catchup_and_no_repeated_results(self):
        writer, path, _ = self.writer()
        first = self.sweep()
        before = (writer.namespace / "retention.jsonl").read_bytes()
        self.assertEqual(self.sweep()["status"], "not_due")
        self.now += timedelta(days=2)
        result = self.sweep()
        self.assertEqual(result["deleted_files"], 0)
        self.assertEqual(before, (writer.namespace / "retention.jsonl").read_bytes())
        self.assertEqual(first["deleted_files"], 1)

    def test_duplicate_sweeper_lock_and_stopping(self):
        _, path, _ = self.writer()
        with retention.NativeFile(self.root / ".retention.lock", write=True, create=True):
            self.assertEqual(self.sweep()["deleted_files"], 0)
        stop = threading.Event()
        stop.set()
        self.assertEqual(self.sweep(stop=stop)["deleted_files"], 0)
        self.assertTrue(path.exists())

    def test_bad_budgets_rejected_and_guard_failure_protects(self):
        _, path, _ = self.writer()
        for policy in ({"max_seconds": float("nan")}, {"max_deletions":True}, {"interval_seconds":0}):
            with self.assertRaises(ValueError):
                self.sweep(**policy)
        for root in ("", " ", None):
            with self.assertRaises(ValueError):
                retention.sweep(root, self.scopes, allowed, now=self.now)
        @contextlib.contextmanager
        def broken(*_):
            raise RuntimeError("database unavailable")
            yield
        result = self.sweep(guard=broken)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(path.exists())
        self.assertIn("evidence_changed_or_io_failed", result["protected_reasons"])

    def test_delete_failure_has_no_false_success_and_retries(self):
        writer, path, ref = self.writer()
        with mock.patch.object(retention.NativeFile, "expire", side_effect=OSError("fake")):
            result = self.sweep()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["deleted_files"], 0)
        self.assertTrue(path.exists())
        self.assertFalse(retention.expired_reference(self.root, "project-one", "agent:one", ref))
        self.now += timedelta(minutes=6)
        self.assertEqual(self.sweep()["deleted_files"], 1)

    def test_changed_identity_between_plan_and_delete_is_protected(self):
        _, path, _ = self.writer()
        original = retention.NativeFile.expire
        def expire(handle, expected):
            return original(handle, [*expected[:2], expected[2]+1, expected[3]])
        with mock.patch.object(retention.NativeFile, "expire", expire):
            self.assertEqual(self.sweep()["deleted_files"], 0)
        self.assertTrue(path.exists())

    def test_checked_handle_denies_replacement_and_write(self):
        _, path, _ = self.writer()
        with retention.NativeFile(path, delete=True) as handle:
            with self.assertRaises(OSError):
                path.unlink()
            with self.assertRaises(OSError):
                path.write_bytes(b"replacement")
            handle.expire(retention.identity(os.fstat(handle.fd)))
        self.assertFalse(path.exists())

    def test_global_policy_stops_old_active_run_capacity_and_age_deletion(self):
        self.sweep()  # Publishes the explicitly enabled root policy.
        when = self.now - timedelta(days=40)
        writer = RuntimeDiagnostics(member_id="agent:one", project_id="project-one", instance_id="global-policy",
            policy=DiagnosticsPolicy.create(root=self.root, max_bytes=700, max_file_bytes=500), clock=lambda: when)
        self.addCleanup(writer.close)
        for i in range(8):
            writer.record_event("fixture", stage="bridge", message="x"*100)
        segments = list(writer.namespace.glob("events-*.jsonl"))
        self.assertGreater(len(segments), 1)
        for path in segments:
            os.utime(path, (when.timestamp(), when.timestamp()))
        self.assertEqual(writer.cleanup_expired(), [])
        self.assertTrue(all(path.exists() for path in segments))

    def test_missing_result_after_delete_is_reconciled_without_duplicate_audit(self):
        writer, path, ref = self.writer()
        original = retention.journal
        def journal(path, value):
            if value.get("outcome") == "deleted":
                raise OSError("result write interrupted")
            return original(path, value)
        with mock.patch.object(retention, "journal", side_effect=journal):
            self.assertEqual(self.sweep()["status"], "partial")
        self.assertFalse(path.exists())
        self.now += timedelta(minutes=6)
        self.sweep()
        self.assertTrue(retention.expired_reference(self.root, "project-one", "agent:one", ref))
        self.assertEqual(retention.read_journal(writer.namespace / "retention.jsonl")[-1]["outcome"],
                         "missing_after_intent")

    def test_junction_root_or_nested_cannot_delete_target(self):
        import subprocess
        writer, path, _ = self.writer()
        link = self.root / "junction"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(writer.namespace)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            result = self.sweep()
            self.assertEqual(result["deleted_files"], 0)
            self.assertTrue(path.exists())
            result = retention.sweep(link, self.scopes, allowed, now=self.now)
            self.assertEqual(result["deleted_files"], 0)
        finally:
            os.rmdir(link)

    def test_expired_reference_provider_is_410_and_scope_is_not_forged(self):
        from server.runtime_diagnostics_sources import RuntimeDiagnosticsProvider
        from server.runtime_diagnostics_query import RuntimeDiagnosticsError
        writer, path, ref = self.writer()
        self.sweep()
        config = {"runtime_diagnostics": {"sources": [
            {"root": str(self.root), "project_id": "project-one", "member_id": "agent:one"}]}}
        provider = RuntimeDiagnosticsProvider.from_config(config)
        with self.assertRaises(RuntimeDiagnosticsError) as error:
            provider.get_detail("project-one", "agent:one", ref)
        self.assertEqual(error.exception.status_code, 410)
        self.assertEqual(error.exception.code, "log_expired")

    def test_real_background_worker_deletes_without_foreground_and_stops(self):
        import time
        from sqlalchemy import create_engine
        from server.runtime_log_retention import RetentionService
        engine = create_engine("sqlite:///"+str(Path(self.temp.name)/"worker.db"),
                               connect_args={"check_same_thread":False})
        self.addCleanup(engine.dispose)
        _, path, _ = self.writer()
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE agent_tasks (id INTEGER PRIMARY KEY, project_id TEXT, "
                "target_member_id TEXT, status TEXT, workflow_status TEXT, control_status TEXT, "
                "parent_task_id INTEGER, root_task_id INTEGER, execution_session JSON)")
            conn.exec_driver_sql("CREATE TABLE agent_task_relations (id INTEGER PRIMARY KEY, source_task_id INTEGER, "
                "target_task_id INTEGER, trigger_task_id INTEGER)")
            conn.exec_driver_sql("INSERT INTO agent_tasks VALUES "
                "(315,'project-one','agent:one','succeeded','completed','active',NULL,NULL,NULL)")
        config = {"runtime_log_retention": {"enabled":True}, "storage":{"db_path":engine.url.database},
                  "runtime_diagnostics":{"sources":[
            {"project_id":"project-one","member_id":"agent:one","root":str(self.root)}]}}
        service = RetentionService(engine, config, clock=lambda:self.now, poll_seconds=.01)
        service.start()
        try:
            until = time.monotonic()+3
            while path.exists() and time.monotonic() < until:
                time.sleep(.01)
        finally:
            service.stop()
        self.assertFalse(path.exists())
        self.assertFalse(service.thread.is_alive())


class TaskGuardTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        temp_root = Path(__file__).resolve().parents[1] / ".tmp/local-log-auto-retention-v1/tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine("sqlite:///" + str(Path(self.temp.name)/"tasks.db"))
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE agent_tasks (id INTEGER PRIMARY KEY, project_id TEXT, "
                                 "target_member_id TEXT, status TEXT, workflow_status TEXT, control_status TEXT, "
                                 "parent_task_id INTEGER, root_task_id INTEGER, execution_session JSON)")
            conn.exec_driver_sql("CREATE TABLE agent_task_relations (id INTEGER PRIMARY KEY, source_task_id INTEGER, "
                                 "target_task_id INTEGER, trigger_task_id INTEGER)")
            conn.exec_driver_sql("INSERT INTO agent_tasks (id,project_id,target_member_id,status,workflow_status,control_status) "
                                 "VALUES (1,'p','agent:a','succeeded','completed','active')")

    def test_terminal_state_scope_and_no_task_changes(self):
        from server.runtime_log_retention import task_guard
        with task_guard(self.engine, "p", "agent:a", [1]) as safe:
            self.assertTrue(safe)
        for project, member, ids in (("other", "agent:a", [1]), ("p", "agent:b", [1]), ("p", "agent:a", [2])):
            with task_guard(self.engine, project, member, ids) as safe:
                self.assertFalse(safe)
        for workflow, control in (("submitted", "active"), ("completed", "paused"),
                                  ("completed", None), ("completed", "unknown")):
            with self.engine.begin() as conn:
                conn.exec_driver_sql("UPDATE agent_tasks SET workflow_status=?,control_status=?", (workflow, control))
            with task_guard(self.engine, "p", "agent:a", [1]) as safe:
                self.assertFalse(safe)

    def test_read_check_reserves_task_state_against_race(self):
        from server.runtime_log_retention import task_guard
        with task_guard(self.engine, "p", "agent:a", [1]) as safe:
            self.assertTrue(safe)
            with self.engine.connect() as other:
                other.exec_driver_sql("PRAGMA busy_timeout=0")
                with self.assertRaises(Exception):
                    other.exec_driver_sql("UPDATE agent_tasks SET workflow_status='assigned'")
        with self.engine.begin() as conn:
            conn.exec_driver_sql("UPDATE agent_tasks SET workflow_status='assigned'")

    def test_unfinished_children_native_continuations_and_relations_protect_base(self):
        from server.runtime_log_retention import task_guard
        for field, value in (("parent_task_id", 1), ("root_task_id", 1),
                             ("execution_session", '{"base_task_id":1}')):
            with self.engine.begin() as conn:
                conn.exec_driver_sql("DELETE FROM agent_tasks WHERE id=2")
                conn.exec_driver_sql(f"INSERT INTO agent_tasks (id,project_id,target_member_id,status,workflow_status,{field}) "
                                     "VALUES (2,'p','agent:b','running','in_progress',?)", (value,))
            with task_guard(self.engine, "p", "agent:a", [1]) as safe:
                self.assertFalse(safe)
        with self.engine.begin() as conn:
            conn.exec_driver_sql("UPDATE agent_tasks SET execution_session=NULL WHERE id=2")
            conn.exec_driver_sql("INSERT INTO agent_task_relations VALUES (1,1,2,NULL)")
        with task_guard(self.engine, "p", "agent:a", [1]) as safe:
            self.assertFalse(safe)

    def test_ancestors_missing_transitive_and_cycles(self):
        from server.runtime_log_retention import task_guard
        for field, value in (("parent_task_id", 2), ("root_task_id", 2),
                             ("execution_session", '{"base_task_id":2}')):
            with self.subTest(field=field):
                with self.engine.begin() as conn:
                    conn.exec_driver_sql("UPDATE agent_tasks SET parent_task_id=NULL,root_task_id=NULL,execution_session=NULL")
                    conn.exec_driver_sql(f"UPDATE agent_tasks SET {field}=? WHERE id=1", (value,))
                with task_guard(self.engine, "p", "agent:a", [1]) as safe:
                    self.assertFalse(safe)  # Missing ancestor is unknown.
                with self.engine.begin() as conn:
                    conn.exec_driver_sql("INSERT INTO agent_tasks VALUES "
                        "(2,'p','agent:b','running','in_progress','active',NULL,NULL,NULL)")
                with task_guard(self.engine, "p", "agent:a", [1]) as safe:
                    self.assertFalse(safe)
                with self.engine.begin() as conn:
                    conn.exec_driver_sql("UPDATE agent_tasks SET status='succeeded',workflow_status='completed',parent_task_id=1 WHERE id=2")
                with task_guard(self.engine, "p", "agent:a", [1]) as safe:
                    self.assertTrue(safe)  # Fully closed cycle terminates.
                with self.engine.begin() as conn:
                    conn.exec_driver_sql("INSERT INTO agent_tasks VALUES "
                        "(3,'p','agent:b','running','in_progress','active',NULL,NULL,NULL)")
                    conn.exec_driver_sql("UPDATE agent_tasks SET root_task_id=3 WHERE id=2")
                with task_guard(self.engine, "p", "agent:a", [1]) as safe:
                    self.assertFalse(safe)  # Transitive unfinished ancestor.
                with self.engine.begin() as conn:
                    conn.exec_driver_sql("DELETE FROM agent_tasks WHERE id IN (2,3)")

    def test_disabled_worker_does_not_touch_sources_and_invalid_config_rejected(self):
        from server.runtime_log_retention import RetentionService
        with mock.patch.object(retention, "pinned", side_effect=AssertionError("touch source")):
            service = RetentionService(self.engine, {})
            service.start()
            service.stop()
            self.assertIsNone(service.thread)
        for section in ({"enabled":"yes"}, {"enabled":True,"retention_dayz":30},
                        {"enabled":True,"retention_days":float("nan")}):
            with self.assertRaises(ValueError):
                RetentionService(self.engine, {"runtime_log_retention":section,
                    "storage":{"db_path":self.engine.url.database}})

    def test_other_database_cannot_act_on_configured_sources(self):
        from server.runtime_log_retention import RetentionService
        config = {"runtime_log_retention":{"enabled":True}, "storage":{"db_path":"other.db"},
                  "runtime_diagnostics":{"sources":[{"root":"D:/must-not-touch", "project_id":"p", "member_id":"agent:a"}]}}
        with mock.patch.object(retention, "pinned", side_effect=AssertionError("production sources")):
            service = RetentionService(self.engine, config)
            service.start()
        self.assertFalse(service.enabled)
        self.assertIsNone(service.thread)

    def test_missing_memory_or_relative_database_binding_cannot_touch_sources(self):
        from sqlalchemy import create_engine
        from server.runtime_log_retention import RetentionService
        memory = create_engine("sqlite:///:memory:")
        self.addCleanup(memory.dispose)
        for engine, storage in ((self.engine, None), (self.engine, {}), (self.engine, {"db_path":""}),
                (self.engine, {"db_path":"relative.db"}), (memory, {"db_path":self.engine.url.database})):
            config = {"runtime_log_retention":{"enabled":True}, "storage":storage,
                "runtime_diagnostics":{"sources":[{"root":"D:/must-not-touch", "project_id":"p", "member_id":"agent:a"}]}}
            with mock.patch.object(retention, "pinned", side_effect=AssertionError("source touched")):
                service = RetentionService(engine, config)
                service.start()
            self.assertFalse(service.enabled)
            self.assertIsNone(service.thread)


if __name__ == "__main__":
    unittest.main()
