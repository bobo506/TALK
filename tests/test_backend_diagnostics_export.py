"""Isolated backend collection, export, scope/auth and lifecycle counterexamples."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from bridges.backend_diagnostics import BackendJournal, MEMBER, exception_structure, project_root, settings
from server.backend_diagnostics import BackendRecorder, build_backend_export, merge_role_export
from server.db import get_session
from server.models import Member, Project, ProjectRole
from server.routes import runtime_diagnostics as routes
from server.runtime_diagnostics_export import build_export, MAX_EXPORT_BYTES
from server.runtime_diagnostics_query import ScanLimits, Source
from bridges.runtime_diagnostics import RuntimeDiagnostics

NOW = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)
SINCE, UNTIL = NOW-timedelta(hours=1), NOW+timedelta(hours=1)
PROJECT = "prj_backend_test"
ROLE = "agent:backend-test"
SECRET = "FAKE_BARE_PRIVATE_VALUE_984671"


def decode(body):
    values = [json.loads(line) for line in body.splitlines()]
    assert values[0]["record_count"] == len(values)-1
    return values[0], values[1:]


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="talk-backend-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.journals = []
        self.addCleanup(self.close_journals)
        self.value = {"root": self.root/"backend", "projects": (PROJECT,)}
        self.allowed_members = frozenset({ROLE, "agent:other"})
        self.allowed_routes = frozenset({"/api/projects/{project_id}/roles/{member_id}", "/api/projects/{project_id}/boom"})

    def close_journals(self):
        for journal in self.journals:
            journal.close()

    def journal(self, component="api", project=PROJECT):
        journal = BackendJournal(self.value["root"], project, component,
            known_secrets=(SECRET,), clock=lambda: NOW)
        self.journals.append(journal)
        return journal

    def export(self, **kwargs):
        kwargs.setdefault("allowed_members", self.allowed_members)
        kwargs.setdefault("allowed_routes", self.allowed_routes)
        return build_backend_export(self.value, PROJECT, since=SINCE, until=UNTIL, **kwargs)

    def test_explicit_database_binding_and_disabled_paths(self):
        dbfile = self.root/"test.db"
        config = {"backend_diagnostics": {"enabled": True, "root": str(self.value["root"]),
            "database_file": str(dbfile), "projects": [PROJECT]}}
        self.assertIsNotNone(settings(config, database_file=str(dbfile)))
        self.assertIsNone(settings(config, database_file=str(self.root/"other.db")))
        self.assertIsNone(settings(config, database_file=":memory:"))
        for key, value in (("root", ""), ("root", "relative"), ("projects", [PROJECT, PROJECT]),
                ("projects", ["../escape"]), ("enabled", "true"), ("database_file", "relative")):
            with self.subTest(key=key, value=value):
                invalid = {"backend_diagnostics": {**config["backend_diagnostics"], key: value}}
                self.assertIsNone(settings(invalid, database_file=str(dbfile)))
        self.assertFalse(self.value["root"].exists())

    def test_collect_and_export_only_structural_exception(self):
        journal = self.journal()
        try:
            try:
                raise ValueError(SECRET+" /private/account Authorization: Bearer private-token")
            except ValueError as cause:
                raise RuntimeError("password=another-private-value") from cause
        except RuntimeError as error:
            journal.emit("api_exception", exc=error, context={"method": "POST", "stage": "request",
                "route": "/api/projects/{project_id}/roles/{member_id}", "request_id": "a"*32,
                "member_id": ROLE, "status": 500, "argv": [SECRET], "headers": SECRET,
                "body": SECRET, "error_code": SECRET, "request_key": SECRET})
        disk = b"".join(path.read_bytes() for path in journal.writer.namespace.glob("events-*.jsonl"))
        body = self.export()
        for raw in (disk, body):
            for secret in (SECRET, "another-private-value", "private-token", "/private/account"):
                self.assertNotIn(secret.encode(), raw)
        meta, events = decode(body)
        self.assertEqual(events[0]["component"], "api")
        self.assertEqual(events[0]["exception"]["type"], "RuntimeError")
        self.assertEqual(events[0]["exception"]["cause_chain"][0]["type"], "ValueError")
        self.assertTrue(events[0]["exception"]["frames"])
        self.assertNotIn("member_id", events[0])
        self.assertEqual(events[0]["context"]["member_id"], ROLE)
        self.assertFalse(meta["complete"])
        self.assertIn("backend_coverage_unverified", meta["reasons"])

    def test_exception_str_is_never_called_and_cycles_bounded(self):
        class Error(Exception):
            def __str__(self):
                raise AssertionError("must not call")
        error = Error()
        error.__cause__ = error
        result = exception_structure(error)
        self.assertTrue(result["chain_truncated"])
        self.assertEqual(result["cause_chain"], [])

    def test_closed_api_recorder_cannot_reopen_a_run(self):
        engine = create_engine("sqlite:///"+str(self.root/"closed.db"))
        self.addCleanup(engine.dispose)
        config = {"backend_diagnostics": {"enabled": True, "root": str(self.value["root"]),
            "database_file": engine.url.database, "projects": [PROJECT]}}
        recorder = BackendRecorder(config, engine)
        recorder.close()
        recorder.lifecycle("backend_heartbeat", stage="serve")
        self.assertFalse(self.value["root"].exists())

    def test_project_and_role_filter_do_not_mix(self):
        self.journal().emit("api_request", context={"member_id": ROLE})
        self.journal("runtime").emit("backend_ready")
        self.journal("provision_worker").emit("worker_result", context={"member_id": "agent:other", "outcome": "failed"})
        self.journal(project="prj_another").emit("backend_failed")
        meta, events = decode(self.export(member_id=ROLE))
        self.assertEqual({e["project_id"] for e in events}, {PROJECT})
        self.assertEqual(len(events), 2)
        self.assertIn("provision_worker", meta["coverage"]["components_missing"])
        self.assertEqual(len(decode(self.export())[1]), 3)

    def test_new_streams_cannot_claim_complete_historical_coverage(self):
        for component in ("api", "runtime", "provision_worker"):
            self.journal(component).emit("backend_ready")
        meta, _ = decode(self.export())
        self.assertEqual(meta["coverage"]["components_missing"], [])
        self.assertFalse(meta["complete"])
        self.assertTrue(meta["scan"]["complete"])

    def test_window_half_open_and_rotation_do_not_delete(self):
        journal = self.journal()
        journal.writer.policy = type(journal.writer.policy)(root=journal.writer.root,
            retention_days=0, max_file_bytes=500, max_bytes=500)
        for _ in range(5):
            journal.emit("api_request", context={"method": "GET"})
        files = list(journal.writer.namespace.glob("events-*.jsonl"))
        self.assertGreater(len(files), 1)
        self.assertEqual(journal.writer.cleanup_expired(), [])
        self.assertEqual(files, list(journal.writer.namespace.glob("events-*.jsonl")))
        body = build_backend_export(self.value, PROJECT, since=SINCE, until=NOW)
        self.assertEqual(decode(body)[1], [])

    def test_limits_mark_partial_without_raw_failed_projection(self):
        journal = self.journal()
        for _ in range(4):
            journal.emit("api_request")
        meta, events = decode(self.export(max_records=2))
        self.assertEqual(len(events), 2)
        self.assertIn("record_limit", meta["reasons"])
        meta, events = decode(self.export(limits=ScanLimits(max_bytes=1)))
        self.assertFalse(meta["complete"])
        self.assertTrue(meta["truncated"])
        path = next(journal.writer.namespace.glob("events-*.jsonl"))
        record = json.loads(path.read_text().splitlines()[0])
        record["extra"] = {"backend_exception": {"frames": SECRET}, "env": SECRET}
        path.write_text(json.dumps(record)+"\n", encoding="utf-8")
        body = self.export()
        self.assertNotIn(SECRET.encode(), body)
        self.assertIn("projection_failed", decode(body)[0]["reasons"])

    def test_role_merge_keeps_role_data_when_backend_missing_or_budget_spent(self):
        role_writer = RuntimeDiagnostics(root=self.root/"role", member_id=ROLE,
            project_id=PROJECT, instance_id="fixture", clock=lambda: NOW)
        self.addCleanup(role_writer.close)
        role_writer.record_event("bridge_ready")
        body = build_export(Source(PROJECT, ROLE, role_writer.root), project_id=PROJECT,
            member_id=ROLE, since=SINCE, until=UNTIL)
        for remaining in (0, 1):
            combined = merge_role_export(body, self.value, PROJECT, ROLE, since=SINCE,
                until=UNTIL, remaining_seconds=remaining)
            meta, events = decode(combined)
            self.assertEqual(len(events), 1)
            self.assertIn("backend_unavailable", meta["reasons"])
            self.assertFalse(meta["complete"])
        self.journal().emit("api_request")
        combined = merge_role_export(body, self.value, PROJECT, ROLE, since=SINCE,
            until=UNTIL, remaining_seconds=5)
        meta, events = decode(combined)
        self.assertEqual(len(events), 2)
        self.assertEqual(meta["scope"], {"project_id": PROJECT, "member_id": ROLE})
        self.assertLessEqual(len(combined), MAX_EXPORT_BYTES)

    def test_worker_failure_and_disabled_mode_use_real_entry(self):
        from scripts.role_provision_worker import RoleProvisionWorker, WorkerError
        journal = self.journal("provision_worker")
        worker = RoleProvisionWorker(project_id=PROJECT, host_label="fixture", project_root=self.root,
            operator_key=SECRET, enabled=True, apply=True, transport=object(), diagnostics=journal)
        worker.list_claimable = lambda: (_ for _ in ()).throw(WorkerError("http_error", SECRET))
        result = worker.run_round()
        self.assertEqual(result[0]["error_code"], "http_error")
        worker.close_diagnostics()
        body = self.export()
        events = decode(body)[1]
        self.assertIn("worker_exception", {e["event"] for e in events})
        self.assertTrue(any(e["event"] == "worker_result" and e["context"].get("error_code") == "http_error"
            and e["severity"] == "error" for e in events))
        self.assertIn("backend_stopped", {e["event"] for e in events})
        self.assertNotIn(SECRET.encode(), body)
        disabled = RoleProvisionWorker(project_id=PROJECT, host_label="fixture", enabled=False, transport=object())
        with patch("bridges.backend_diagnostics.runtime_journals", side_effect=AssertionError("created journal")):
            self.assertEqual(disabled.run_round()[0]["error_code"], "worker_disabled")
            disabled.close_diagnostics()

    def test_runtime_start_failure_and_host_exit_preserve_ownership(self):
        from scripts.talk_runtime import TalkRuntime
        journal = self.journal("runtime")
        config = {"project_id": PROJECT, "project_root": str(self.root), "state_dir": str(self.root/"state"),
            "operator_key_file": str(self.root/SECRET/"missing.key"), "hosts": []}
        runtime = TalkRuntime(config, diagnostics={"runtime": journal})
        with self.assertRaises(FileNotFoundError):
            runtime.serve()
        body = self.export()
        self.assertIn("backend_failed", {e["event"] for e in decode(body)[1]})
        self.assertNotIn(SECRET.encode(), body)
        self.assertTrue(journal.writer._closed)

        journal2 = self.journal("runtime")
        class Process:
            pid = 8765
            returncode = None
            def poll(self):
                return self.returncode
        process = Process()
        spec = {"member_id": ROLE, "argv": ["never-executed", SECRET],
            "health_file": str(self.root/"health.json"), "drain_file": str(self.root/"drain")}
        config["hosts"] = [spec]
        runtime = TalkRuntime(config, diagnostics={"runtime": journal2}, spawn=lambda *_: process)
        runtime.reconcile_hosts([{"member_id": ROLE, "service": {}}])
        process.returncode = 17
        runtime.reconcile_hosts([{"member_id": ROLE, "service": {"ownership_held": True}}])
        self.assertNotIn(ROLE, runtime.hosts)
        events = decode(self.export())[1]
        exits = [e for e in events if e["event"] == "host_exited"]
        self.assertEqual(exits[0]["context"]["returncode"], 17)
        self.assertEqual(exits[0]["context"]["member_id"], ROLE)
        self.assertNotIn(SECRET.encode(), self.export())


class ApiTests(unittest.TestCase):
    close_journals = BackendTests.close_journals
    journal = BackendTests.journal
    export = BackendTests.export

    def setUp(self):
        BackendTests.setUp(self)
        self.engine = create_engine("sqlite:///"+str(self.root/"api.db"), connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add(Project(project_id=PROJECT, display_name="test", maintainer_member_id="human:backend"))
            session.add(Member(id="human:backend", display_name="human", kind="human", api_key="FAKE_HUMAN"))
            session.add(Member(id=ROLE, display_name="agent", kind="agent", api_key="FAKE_AGENT"))
            session.add(ProjectRole(project_id=PROJECT, member_id=ROLE, role_name="test", created_by="human:backend"))
            session.commit()
        self.config = {"backend_diagnostics": {"enabled": True, "root": str(self.value["root"]),
            "database_file": self.engine.url.database, "projects": [PROJECT]}}
        self.config_patch = patch("server.db.CONFIG", self.config)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.app = FastAPI()
        self.app.include_router(routes.router)
        def get_db():
            with Session(self.engine) as session:
                yield session
        self.app.dependency_overrides[get_session] = get_db
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.query = {"since": SINCE.isoformat(), "until": UNTIL.isoformat()}

    def test_auth_before_disk_and_missing_parameters(self):
        path = f"/api/projects/{PROJECT}/backend-logs/export"
        with patch("server.backend_diagnostics.build_backend_export", side_effect=AssertionError("disk touched")):
            self.assertEqual(self.client.get(path, params=self.query).status_code, 401)
            self.assertEqual(self.client.get(path, params=self.query, headers={"X-API-Key": "FAKE_AGENT"}).status_code, 403)
            self.assertEqual(self.client.get(path, params={}, headers={"X-API-Key": "FAKE_HUMAN"}).status_code, 422)
            self.assertEqual(self.client.get(path.replace(PROJECT, "not-here"), params=self.query,
                headers={"X-API-Key": "FAKE_HUMAN"}).status_code, 404)

    def test_project_export_and_database_mismatch(self):
        self.journal().emit("api_request")
        path = f"/api/projects/{PROJECT}/backend-logs/export"
        response = self.client.get(path, params=self.query, headers={"X-API-Key": "FAKE_HUMAN"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(len(decode(response.content)[1]), 1)
        self.config["backend_diagnostics"]["database_file"] = str(self.root/"other.db")
        with patch("server.backend_diagnostics.build_export", side_effect=AssertionError("disk touched")):
            response = self.client.get(path, params=self.query, headers={"X-API-Key": "FAKE_HUMAN"})
        self.assertEqual(response.status_code, 503)

    def test_real_middleware_uses_route_template_and_db_binding(self):
        with patch("server.logging_config.configure_logging"):
            from server.main import RequestLoggingMiddleware
        recorder = BackendRecorder(self.config, self.engine)
        self.addCleanup(recorder.close)
        self.app.state.backend_recorder = recorder
        self.app.add_middleware(RequestLoggingMiddleware)
        @self.app.get("/api/projects/{project_id}/boom")
        def boom(current=Depends(routes.require_log_reader)):
            raise ValueError(SECRET)
        with patch("server.main.logger"):
            response = self.client.get(f"/api/projects/{PROJECT}/boom", params={"token": SECRET},
                headers={"X-API-Key": "FAKE_HUMAN", "X-Request-ID": SECRET})
        self.assertEqual(response.status_code, 500)
        # API journal's real wall clock need not equal the deterministic fixture clock.
        body = build_backend_export(self.value, PROJECT, since=datetime.now(timezone.utc)-timedelta(minutes=1),
            until=datetime.now(timezone.utc)+timedelta(minutes=1), allowed_routes=self.allowed_routes)
        self.assertNotIn(SECRET.encode(), body)
        events = decode(body)[1]
        self.assertEqual(events[0]["event"], "api_exception")
        self.assertEqual(events[0]["context"]["route"], "/api/projects/{project_id}/boom")
        self.assertEqual(events[0]["exception"]["type"], "ValueError")

    def test_combined_role_http_uses_same_auth_scope_and_partial_contract(self):
        from server.runtime_diagnostics_sources import RuntimeDiagnosticsProvider
        role_writer = RuntimeDiagnostics(root=self.root/"role", member_id=ROLE, project_id=PROJECT,
            instance_id="fixture", clock=lambda: NOW)
        self.addCleanup(role_writer.close)
        role_writer.record_event("bridge_ready")
        provider = RuntimeDiagnosticsProvider.from_config({"runtime_diagnostics": {"sources": [
            {"project_id": PROJECT, "member_id": ROLE, "root": str(role_writer.root)}]}})
        self.app.dependency_overrides[routes.get_runtime_diagnostics_provider] = lambda: provider
        self.journal().emit("api_request", context={"member_id": ROLE})
        self.journal("runtime").emit("backend_ready")
        response = self.client.get(f"/api/projects/{PROJECT}/roles/{ROLE}/runtime-logs/export",
            params=self.query, headers={"X-API-Key": "FAKE_HUMAN"})
        self.assertEqual(response.status_code, 200, response.text)
        meta, events = decode(response.content)
        self.assertEqual(meta["schema"], "talk-diagnostics-export-1")
        self.assertEqual(len(events), 3)
        self.assertFalse(meta["complete"])
        self.assertTrue(meta["backend"]["available"])

    def test_known_role_without_role_source_can_export_backend_with_explicit_gap(self):
        from server.runtime_diagnostics_sources import RuntimeDiagnosticsProvider
        self.app.dependency_overrides[routes.get_runtime_diagnostics_provider] = lambda: RuntimeDiagnosticsProvider.from_config({})
        self.journal("runtime").emit("backend_ready")
        response = self.client.get(f"/api/projects/{PROJECT}/roles/{ROLE}/runtime-logs/export",
            params=self.query, headers={"X-API-Key": "FAKE_HUMAN"})
        self.assertEqual(response.status_code, 200, response.text)
        meta, events = decode(response.content)
        self.assertEqual(meta["role"], {"available": False})
        self.assertEqual(len(events), 1)
        self.assertIn("unavailable_records", meta["reasons"])
        self.assertFalse(meta["complete"])

    def test_actual_lifespan_closes_journals_and_records_start_shutdown_failure(self):
        with patch("server.logging_config.configure_logging"):
            from server import main
        @asynccontextmanager
        async def underlying(app):
            yield
        async def exercise():
            with patch.object(main, "engine", self.engine), patch.object(main, "_server_lifespan", underlying):
                with self.assertRaises(ValueError):
                    async with main.lifespan(self.app):
                        raise ValueError(SECRET)
        asyncio.run(exercise())
        body = build_backend_export(self.value, PROJECT, since=datetime.now(timezone.utc)-timedelta(minutes=1),
            until=datetime.now(timezone.utc)+timedelta(minutes=1))
        events = decode(body)[1]
        self.assertEqual([e["event"] for e in events], ["backend_starting", "backend_ready", "backend_stopping", "backend_failed"])
        self.assertIsNone(self.app.state.backend_recorder)
        self.assertNotIn(SECRET.encode(), body)

    def test_health_failures_are_shared_api_events_without_private_error_text(self):
        with patch("server.logging_config.configure_logging"):
            from server import main
        recorder = BackendRecorder(self.config, self.engine)
        self.addCleanup(recorder.close)
        self.app.state.backend_recorder = recorder
        with patch.object(main, "app", self.app), patch.object(main, "logger"), \
                patch.object(main, "_check_db_health", side_effect=RuntimeError(SECRET)), \
                patch.object(main, "_check_storage_health", side_effect=OSError(SECRET)):
            self.assertEqual(main.healthz().status_code, 503)
        body = build_backend_export(self.value, PROJECT, since=datetime.now(timezone.utc)-timedelta(minutes=1),
            until=datetime.now(timezone.utc)+timedelta(minutes=1))
        events = decode(body)[1]
        self.assertEqual({e["context"]["subsystem"] for e in events}, {"database", "storage"})
        self.assertTrue(all(e["attribution"] == "project_shared" for e in events))
        self.assertNotIn(SECRET.encode(), body)


if __name__ == "__main__":
    unittest.main()
