"""Isolated tests for first-time local workspace registration."""
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import server.db as db
from tests.test_auth_trusted import main
from server.auth import ensure_local_operator
from server import local_runtime
from server.models import Member, Project, ProjectRole, RoleProvisionHostConfig


class LocalWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="workspace-617-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.root = self.base / "demo"
        self.root.mkdir()
        self.engine = create_engine("sqlite:///" + str(self.base / "test.db"), connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        SQLModel.metadata.create_all(self.engine)
        self.template = {"schema":"talk-runtime-1", "project_id":"template", "project_root":str(self.base),
                         "base_url":"http://127.0.0.1:8000", "host":"testhost", "operator_key_file":"/reference-only",
                         "api_argv":[], "kimi":{}, "codex":{}, "dsh":{}, "workbuddy":{}}
        patches = [patch.object(db, "engine", self.engine), patch.object(main, "engine", self.engine),
                   patch.object(db, "AUTH_MODE", "trusted"), patch.object(db, "TRUSTED_NETWORKS", ("loopback", "private")),
                   patch.object(Path, "home", return_value=self.home),
                   patch.object(local_runtime, "configured_runtime", return_value=(self.base / "template.json", self.template)),
                   patch.object(local_runtime, "ensure_local_runtime", return_value="requested")]
        for item in patches:
            value = item.start()
            self.addCleanup(item.stop)
        self.ensure = value
        with Session(self.engine) as session:
            session.add(Member(id="agent:test", kind="agent", display_name="Agent", api_key="agent-test-key"))
            session.commit()
            ensure_local_operator(session)

    def call(self, root=None, host="127.0.0.1", headers=None):
        client = TestClient(main.app, client=(host, 50000))
        return client.post("/api/local/workspaces/ensure", json={"project_root":str(root or self.root)}, headers=headers or {})

    def test_create_repeat_and_no_roles(self):
        response = self.call()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["runtime_state"], "requested")
        self.assertTrue(data["needs_role"])
        project_id = data["project_id"]
        marker = yaml.safe_load((self.root / ".talk/project.yaml").read_text(encoding="utf-8"))
        pointer = json.loads((self.root / ".talk/runtime.local.json").read_text(encoding="utf-8"))
        runtime = json.loads(Path(pointer["config_file"]).read_text(encoding="utf-8"))
        self.assertEqual(marker["project_id"], project_id)
        self.assertEqual(pointer["database_file"], str((self.base / "test.db").resolve()))
        self.assertEqual(runtime["project_id"], project_id)
        self.assertEqual(runtime["state_dir"], str(self.home / ".talk/role-service-host/projects" / project_id))
        self.assertEqual(runtime["key_root"], str(self.home / ".talk/keys" / project_id))
        self.assertEqual(runtime["hosts"], [])
        self.assertTrue(runtime["provision_worker"])
        self.assertEqual(runtime["operator_key_file"], "/reference-only")
        self.assertEqual(self.call().json()["project_id"], project_id)
        self.assertEqual(self.ensure.call_count, 2)
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(Project)).all()), 1)
            self.assertEqual(session.get(RoleProvisionHostConfig, project_id).enabled, 1)
            self.assertEqual(session.exec(select(ProjectRole)).all(), [])
        self.assertFalse((self.home / ".talk/keys").exists())

    def test_conflicts_and_invalid_roots(self):
        talk = self.root / ".talk"
        talk.mkdir()
        (talk / "project.yaml").write_text("project_id: other\n", encoding="utf-8")
        self.assertEqual(self.call().status_code, 409)
        for path in (self.base / "missing", self.base / "test.db", Path(self.root.anchor), self.home):
            self.assertEqual(self.call(path).status_code, 422, str(path))
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Project)).all(), [])

    def test_auth(self):
        self.assertEqual(self.call(headers={"X-API-Key":"agent-test-key"}).status_code, 403)
        self.assertEqual(self.call(host="8.8.8.8").status_code, 401)
        with patch.object(db, "AUTH_MODE", "key"):
            self.assertIn(self.call().status_code, (401, 422))

    def test_file_failure_rolls_back_project_and_host(self):
        (self.root / ".talk").write_text("not a directory", encoding="utf-8")
        response = self.call()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "workspace_write_failed")
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Project)).all(), [])
            self.assertEqual(session.exec(select(RoleProvisionHostConfig)).all(), [])
        self.assertEqual(list((self.home / ".talk/runtimes").rglob("runtime.json")), [])

    def test_missing_template_and_human_key(self):
        with patch.object(local_runtime, "configured_runtime", return_value=None):
            response = self.call()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"], "runtime_template_unavailable")
        with Session(self.engine) as session:
            session.add(Member(id="human:test", kind="human", display_name="Human", api_key="human-test-key"))
            session.commit()
        with patch.object(db, "AUTH_MODE", "key"):
            response = self.call(headers={"X-API-Key": "human-test-key"})
            self.assertEqual(response.status_code, 200, response.text)

    def test_runtime_failure_reports_persisted_project(self):
        self.ensure.side_effect = RuntimeError("failure")
        response = self.call()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["runtime_state"], "disabled")
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(Project)).all()), 1)
        self.assertTrue((self.root / ".talk/project.yaml").is_file())

    def test_generated_binding_loads_with_real_runtime_loader(self):
        import sys
        from scripts.talk_runtime import load_config
        self.template.update(schema="talk-runtime-config-1", version=1, api_argv=[sys.executable, "{control_file}"],
                             operator_key_file=str(self.home / "operator.key"))
        for recipe in ("kimi", "codex", "dsh", "workbuddy"):
            self.template.pop(recipe, None)
        response = self.call()
        self.assertEqual(response.status_code, 200, response.text)
        pointer = json.loads((self.root / ".talk/runtime.local.json").read_text(encoding="utf-8"))
        self.assertEqual(load_config(pointer["config_file"])["project_id"], response.json()["project_id"])

    def test_concurrent_calls(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.call(), range(4)))
        self.assertTrue(all(x.status_code == 200 for x in results))
        self.assertEqual(len({x.json()["project_id"] for x in results}), 1)


class TerminalConfigureTests(unittest.TestCase):
    def test_first_start_and_marker_reuse(self):
        import argparse
        import os
        from bridges import talk_terminal_mcp as terminal
        with tempfile.TemporaryDirectory(prefix="terminal-617-") as directory:
            root = Path(directory)
            args = argparse.Namespace(project_root=root, project=None, server="http://127.0.0.1:8000", wait_stats_file=None)
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self): return b'{"project_id":"prj_test"}'
            with patch.dict(os.environ, {"TALK_WORKSPACE_AUTO_ENSURE": "1"}, clear=True), patch.object(terminal, "urlopen", return_value=Response()) as call:
                self.assertEqual(terminal.configure(args)[1], "prj_test")
                self.assertEqual(os.environ["TALK_API_KEY"], "")
                request = call.call_args.args[0]
                self.assertEqual(json.loads(request.data)["project_root"], str(root.resolve()))
                self.assertIsNone(request.get_header("X-api-key"))
                (root / ".talk").mkdir()
                (root / ".talk/project.yaml").write_text("project_id: prj_test\n", encoding="utf-8")
                os.environ.pop("TALK_PROJECT_ID")
                os.environ["TALK_API_KEY"] = "test-human"
                terminal.configure(args)
                self.assertEqual(call.call_count, 1)

    def test_first_start_without_key_reports_auth_failures(self):
        import argparse
        import io
        import os
        from urllib.error import HTTPError
        from bridges import talk_terminal_mcp as terminal
        with tempfile.TemporaryDirectory(prefix="terminal-619-") as directory:
            args = argparse.Namespace(project_root=Path(directory), project=None, server="http://127.0.0.1:8000", wait_stats_file=None)
            for status in (401, 403):
                error = HTTPError(args.server, status, "forbidden", {}, io.BytesIO(b'{}'))
                with self.subTest(status=status), patch.dict(os.environ, {"TALK_WORKSPACE_AUTO_ENSURE": "1"}, clear=True), patch.object(terminal, "urlopen", side_effect=error) as call:
                    with self.assertRaisesRegex(terminal.TalkToolError, "\u672c\u5730\u4fe1\u4efb\u6a21\u5f0f"):
                        terminal.configure(args)
                    self.assertIsNone(call.call_args.args[0].get_header("X-api-key"))

    def test_human_key_and_auth_failure(self):
        import argparse
        import io
        import os
        from urllib.error import HTTPError
        from bridges import talk_terminal_mcp as terminal
        with tempfile.TemporaryDirectory(prefix="terminal-617-") as directory:
            args = argparse.Namespace(project_root=Path(directory), project=None, server="http://127.0.0.1:8000", wait_stats_file=None)
            error = HTTPError(args.server, 403, "forbidden", {}, io.BytesIO(b'{}'))
            with patch.dict(os.environ, {"TALK_API_KEY":"test-human", "TALK_WORKSPACE_AUTO_ENSURE":"1"}, clear=True), patch.object(terminal, "urlopen", side_effect=error) as call:
                with self.assertRaisesRegex(terminal.TalkToolError, "操作者权限"):
                    terminal.configure(args)
                self.assertEqual(call.call_args.args[0].get_header("X-api-key"), "test-human")
