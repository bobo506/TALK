"""320 privacy/identity/error-category counterexamples, using isolated fixtures."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import Depends
from sqlmodel import Session

import tests.test_backend_diagnostics_export as base
from bridges.backend_diagnostics import ERROR_CODES
from server.backend_diagnostics import BackendRecorder, build_backend_export, project_members, project_routes
from server.models import Member, Project, ProjectRole, ProjectAgent
from server.routes import runtime_diagnostics as routes

LEAK = "LEAK_PATH_TOKEN_7f3a9"
PROJECT, ROLE = base.PROJECT, base.ROLE


class ApiPrivacyTests(unittest.TestCase):
    setUp = base.ApiTests.setUp
    close_journals = base.BackendTests.close_journals
    journal = base.BackendTests.journal
    export = base.BackendTests.export

    def middleware(self):
        with patch("server.logging_config.configure_logging"):
            from server.main import RequestLoggingMiddleware
        recorder = BackendRecorder(self.config, self.engine)
        self.addCleanup(recorder.close)
        self.app.state.backend_recorder = recorder
        self.app.add_middleware(RequestLoggingMiddleware)
        return recorder

    def test_invalid_human_404_and_agent_403_paths_do_not_enter_new_stream(self):
        self.middleware()
        path = f"/api/projects/{PROJECT}/roles/{LEAK}/runtime-logs/export"
        with patch("server.main.logger"):
            self.assertEqual(self.client.get(path, params=self.query, headers={"X-API-Key": "FAKE_HUMAN"}).status_code, 404)
            self.assertEqual(self.client.get(path, params=self.query, headers={"X-API-Key": "FAKE_AGENT"}).status_code, 403)
        # Check collection too: dropping malformed output alone would hide F1.
        raw = b"".join(p.read_bytes() for p in self.value["root"].rglob("events-*.jsonl"))
        self.assertNotIn(LEAK.encode(), raw)
        records = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual(len(records), 2)
        self.assertTrue(all("member_id" not in r["extra"]["backend_context"] for r in records))
        response = self.client.get(f"/api/projects/{PROJECT}/backend-logs/export", params=self.query,
            headers={"X-API-Key": "FAKE_HUMAN"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(LEAK.encode(), response.content)

    def test_real_role_and_historical_roster_prove_capture_identity(self):
        self.middleware()
        with Session(self.engine) as session:
            session.add(Member(id="agent:legacy", display_name="legacy", kind="agent", api_key="FAKE_LEGACY"))
            session.add(ProjectAgent(project_id=PROJECT, member_id="agent:legacy"))
            session.commit()
        @self.app.post("/api/projects/{project_id}/roles/{member_id}/fixture-mutate")
        def action(current=Depends(routes.require_log_reader)):
            return {"ok": True}
        for member in (ROLE, "agent:legacy"):
            response = self.client.post(f"/api/projects/{PROJECT}/roles/{member}/fixture-mutate", headers={"X-API-Key": "FAKE_HUMAN"})
            self.assertEqual(response.status_code, 200)
        raw = b"".join(p.read_bytes() for p in self.value["root"].rglob("events-*.jsonl"))
        contexts = [json.loads(line)["extra"]["backend_context"] for line in raw.splitlines()]
        self.assertEqual({c["member_id"] for c in contexts}, {ROLE, "agent:legacy"})

    def test_other_project_member_is_not_attested_or_exported(self):
        self.middleware()
        with Session(self.engine) as session:
            session.add(Project(project_id="prj_other", display_name="other", maintainer_member_id="human:backend"))
            session.add(Member(id="agent:elsewhere", display_name="elsewhere", kind="agent", api_key="FAKE_ELSEWHERE"))
            session.add(ProjectRole(project_id="prj_other", member_id="agent:elsewhere", role_name="other", created_by="human:backend"))
            session.commit()
        @self.app.post("/api/projects/{project_id}/roles/{member_id}/fixture-mutate")
        def action(current=Depends(routes.require_log_reader)):
            return {"ok": True}
        self.assertEqual(self.client.post(f"/api/projects/{PROJECT}/roles/agent:elsewhere/fixture-mutate",
            headers={"X-API-Key": "FAKE_HUMAN"}).status_code, 200)
        raw = b"".join(p.read_bytes() for p in self.value["root"].rglob("events-*.jsonl"))
        self.assertNotIn(b"agent:elsewhere", raw)
        # Forge a persisted value, bypassing the collection boundary as F2 did.
        self.journal().emit("api_request", context={"member_id": "agent:elsewhere"})
        response = self.client.get(f"/api/projects/{PROJECT}/backend-logs/export", params=self.query,
            headers={"X-API-Key": "FAKE_HUMAN"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"agent:elsewhere", response.content)
        self.assertIn("projection_failed", base.decode(response.content)[0]["reasons"])

    def test_http_export_uses_own_db_roles_and_app_templates(self):
        journal = self.journal()
        journal.emit("api_request", context={"route": "/private/"+LEAK})
        journal.emit("api_request", context={"member_id": LEAK})
        journal.emit("api_request", context={"route": "/api/projects/{project_id}/backend-logs/export"})
        response = self.client.get(f"/api/projects/{PROJECT}/backend-logs/export", params=self.query,
            headers={"X-API-Key": "FAKE_HUMAN"})
        self.assertEqual(response.status_code, 200)
        meta, records = base.decode(response.content)
        self.assertEqual(len(records), 1)
        self.assertNotIn(LEAK.encode(), response.content)
        self.assertIn("projection_failed", meta["reasons"])

    def test_obs1_disabled_legacy_503_but_enabled_missing_sources_partial(self):
        from server.runtime_diagnostics_sources import RuntimeDiagnosticsProvider
        self.app.dependency_overrides[routes.get_runtime_diagnostics_provider] = lambda: RuntimeDiagnosticsProvider.from_config({})
        path = f"/api/projects/{PROJECT}/roles/{ROLE}/runtime-logs/export"
        self.config["backend_diagnostics"]["enabled"] = False
        self.assertEqual(self.client.get(path, params=self.query, headers={"X-API-Key": "FAKE_HUMAN"}).status_code, 503)
        self.config["backend_diagnostics"]["enabled"] = True
        response = self.client.get(path, params=self.query, headers={"X-API-Key": "FAKE_HUMAN"})
        self.assertEqual(response.status_code, 200, response.text)
        meta, events = base.decode(response.content)
        self.assertEqual(events, [])
        self.assertFalse(meta["complete"])
        self.assertFalse(meta["role"]["available"])
        self.assertFalse(meta["backend"]["available"])


class ProjectionPrivacyTests(unittest.TestCase):
    setUp = base.BackendTests.setUp
    close_journals = base.BackendTests.close_journals
    journal = base.BackendTests.journal
    export = base.BackendTests.export

    def test_tampered_member_route_records_fail_project_and_role_projection(self):
        journal = self.journal()
        journal.emit("api_request", context={"member_id": ROLE, "route": "/api/projects/{project_id}/roles/{member_id}"})
        path = next(journal.writer.namespace.glob("events-*.jsonl"))
        original = json.loads(path.read_text().splitlines()[0])
        cases = [{"route": "/private/"+LEAK}, {"route": "/api/projects/{project_id}/"+LEAK},
            {"route": "/api/projects/{project_id}//roles/{member_id}"}, {"route": "/api/projects/{project_id}/../secret"},
            {"route": {"token": LEAK}}, {"member_id": LEAK}, {"member_id": "agent:unknown"}, {"member_id": [LEAK]}]
        records = [original]
        for i, case in enumerate(cases):
            record = json.loads(json.dumps(original))
            record["log_id"] = f"rtd-privacy-fixture-{i}"
            record["extra"]["backend_context"].update(case)
            records.append(record)
        path.write_text("".join(json.dumps(r)+"\n" for r in records), encoding="utf-8")
        for member in (None, ROLE):
            body = self.export(member_id=member)
            meta, events = base.decode(body)
            self.assertEqual(len(events), 1)
            self.assertIn("projection_failed", meta["reasons"])
            self.assertNotIn(LEAK.encode(), body)

    def test_missing_projection_policy_never_trusts_persisted_identity(self):
        self.journal().emit("api_request", context={"member_id": ROLE})
        body = build_backend_export(self.value, PROJECT, since=base.SINCE, until=base.UNTIL)
        meta, records = base.decode(body)
        self.assertEqual(records, [])
        self.assertIn("projection_failed", meta["reasons"])

    def test_finite_runtime_host_codes_and_unknown_prefix(self):
        journal = self.journal("runtime")
        codes = ("runtime_api_exited", "runtime_host_stop_timeout", "state_dir_insecure", "storage_unavailable", "cli_command_unresolved", "runtime_"+LEAK)
        for code in codes:
            journal.emit("runtime_exception", context={"error_code": code})
        body = self.export()
        contexts = [e["context"] for e in base.decode(body)[1]]
        self.assertEqual([c["error_code"] for c in contexts[:-1]], list(codes[:-1]))
        self.assertIn("error_code_digest", contexts[-1])
        self.assertNotIn(LEAK.encode(), body)

    def test_code_owned_runtime_host_literals_stay_in_finite_registry(self):
        root = Path(__file__).resolve().parents[1]
        for filename, error_class in (("scripts/talk_runtime.py", "RuntimeErrorCode"), ("scripts/role_service_host.py", "HostError")):
            tree = ast.parse((root/filename).read_text(encoding="utf-8"))
            codes = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == error_class and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)}
            # Also follow local assignments and conditional branches reaching an error call;
            # a direct-literal scan misses HostError(code, ...) in build_runtime_argv.
            for function in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
                assignments = {}
                for node in ast.walk(function):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                assignments.setdefault(target.id, []).append(node.value)
                    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                        assignments.setdefault(node.target.id, []).append(node.value)

                def literals(node, seen=frozenset()):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        return {node.value} if node.value else set()
                    if isinstance(node, ast.IfExp):
                        return literals(node.body, seen) | literals(node.orelse, seen)
                    if isinstance(node, ast.BoolOp):
                        return set().union(*(literals(value, seen) for value in node.values))
                    if isinstance(node, ast.Name) and node.id not in seen:
                        return set().union(*(literals(value, seen | {node.id}) for value in assignments.get(node.id, ())))
                    return set()

                for node in ast.walk(function):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == error_class and node.args:
                        codes.update(literals(node.args[0]))
            self.assertEqual(codes-ERROR_CODES, set())

    def test_actual_host_command_template_branches_preserve_known_codes(self):
        from scripts.role_service_host import HostError, build_runtime_argv
        journal = self.journal("runtime")
        expected = ("cli_command_unresolved", "cli_command_unresolved", "runtime_alias_unsupported")
        for runtime, code in zip(("dsh", "cli", "codex"), expected):
            with self.subTest(runtime=runtime):
                with self.assertRaises(HostError) as caught:
                    build_runtime_argv(runtime, model_alias="fake/model", command_template=None)
                self.assertEqual(caught.exception.code, code)
                journal.emit("runtime_exception", context={"error_code": caught.exception.code}, exc=caught.exception)
        contexts = [event["context"] for event in base.decode(self.export())[1]]
        self.assertEqual([context.get("error_code") for context in contexts], list(expected))
        self.assertTrue(all("error_code_digest" not in context for context in contexts))

    def test_actual_runtime_failure_preserves_known_code(self):
        from scripts.talk_runtime import TalkRuntime, RuntimeErrorCode
        key = self.root/"fake-human.key"
        key.write_text("FAKE_RUNTIME_HUMAN", encoding="utf-8")
        journal = self.journal("runtime")
        runtime = TalkRuntime({"project_id": PROJECT, "project_root": str(self.root), "state_dir": str(self.root/"state"),
            "operator_key_file": str(key), "base_url": "http://127.0.0.1:1"}, attach_api=True, diagnostics={"runtime": journal})
        with patch.object(runtime, "wait_api", side_effect=RuntimeErrorCode("runtime_api_exited")):
            with self.assertRaises(RuntimeErrorCode):
                runtime.serve()
        events = base.decode(self.export())[1]
        self.assertTrue(any(e["event"] == "backend_failed" and e["context"].get("error_code") == "runtime_api_exited" for e in events))
