"""Source gating and local operator authentication on isolated databases."""
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import uvicorn
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from starlette.websockets import WebSocketDisconnect

import server.db as db
# Configure the app logger before main import, keeping all test output isolated.
_original_log_path = db.LOG_PATH
db.LOG_PATH = Path(tempfile.gettempdir()) / "talk-608-test.log"
import server.main as main
db.LOG_PATH = _original_log_path
from server.auth import ensure_local_operator, is_trusted_host
from server.models import Member, Project, ProjectRole
from bridges.runtime_diagnostics import RuntimeDiagnostics
from server.runtime_diagnostics_sources import RuntimeDiagnosticsProvider
from server.routes import runtime_diagnostics as diagnostics


class TrustedAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="trusted-608-")
        self.addCleanup(self.tmp.cleanup)
        self.engine = create_engine("sqlite:///" + str(Path(self.tmp.name) / "test.db"), connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        SQLModel.metadata.create_all(self.engine)
        self.patches = [patch.object(db, "engine", self.engine), patch.object(main, "engine", self.engine),
                        patch.object(db, "AUTH_MODE", "trusted"), patch.object(db, "TRUSTED_NETWORKS", ("loopback", "private"))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        with Session(self.engine) as session:
            session.add(Member(id="agent:test", kind="agent", display_name="Agent", api_key="agent-test-key"))
            session.commit()
            ensure_local_operator(session)

    def client(self, host="127.0.0.1"):
        return TestClient(main.app, client=(host, 50000))

    def test_rest_sources_keys_and_forwarded_header(self):
        for host in ("127.0.0.1", "10.1.2.3", "192.168.1.5", "::1"):
            with self.subTest(host=host):
                self.assertEqual(self.client(host).get("/api/members/me").json()["id"], "human:operator")
        for host in ("8.8.8.8", "testclient"):
            for headers in ({}, {"X-API-Key": "agent-test-key"}, {"X-Forwarded-For": "127.0.0.1"}):
                self.assertEqual(self.client(host).get("/api/members/me", headers=headers).status_code, 401)
        self.assertEqual(TestClient(main.app).get("/api/members/me").status_code, 401)
        self.assertEqual(self.client("10.1.2.3").get("/api/members/me", headers={"X-API-Key": "agent-test-key"}).json()["id"], "agent:test")
        self.assertEqual(self.client().get("/api/members/me", headers={"X-API-Key": "bad"}).status_code, 401)
        self.assertFalse(is_trusted_host(None))

    def test_public_registration_cannot_bypass_source_gate(self):
        payload = {"id": "agent:new", "display_name": "New", "api_key": "new-agent-key"}
        self.assertEqual(self.client("8.8.8.8").post("/api/members", json=payload).status_code, 401)
        self.assertEqual(self.client().post("/api/members", json=payload).status_code, 201)
        with patch.object(db, "AUTH_MODE", "key"):
            payload["id"] = "agent:other"
            payload["api_key"] = "other-agent-key"
            self.assertEqual(self.client("8.8.8.8").post("/api/members", json=payload).status_code, 201)

    def test_key_mode(self):
        with patch.object(db, "AUTH_MODE", "key"):
            missing = self.client().get("/api/members/me")
            self.assertEqual(missing.status_code, 422)
            self.assertEqual(missing.json()["detail"], "X-API-Key header required")
            for key in ("", "bad"):
                with self.subTest(key=key):
                    self.assertEqual(self.client().get("/api/members/me", headers={"X-API-Key": key}).status_code, 401)
            self.assertEqual(self.client("8.8.8.8").get("/api/members/me", headers={"X-API-Key": "agent-test-key"}).status_code, 200)

    def test_public_metadata_and_hidden_member(self):
        c = self.client("8.8.8.8")
        mode = c.get("/api/auth/mode")
        setup = c.get("/api/setup/status")
        self.assertEqual(mode.status_code, 200)
        self.assertEqual(set(mode.json()), {"mode", "operator_member_id", "requires_setup"})
        self.assertEqual(setup.status_code, 200)
        self.assertEqual(mode.json()["requires_setup"], setup.json()["needs_setup"])
        c = self.client()
        self.assertNotIn("human:operator", [m["id"] for m in c.get("/api/members").json()])
        self.assertEqual(c.get("/api/members/me").json()["id"], "human:operator")
        self.assertTrue(c.get("/api/members/me/permissions").json()["can_view_all_conversations"])
        self.assertFalse(c.get("/api/members/me/permissions", headers={"X-API-Key": "agent-test-key"}).json()["can_view_all_conversations"])

    def test_websocket_source_gate(self):
        with self.client().websocket_connect("/ws") as ws:
            self.assertEqual(ws.receive_json()["type"], "presence")
        for path in ("/ws", "/ws?token=agent-test-key"):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self.client("8.8.8.8").websocket_connect(path):
                    pass
            self.assertEqual(ctx.exception.code, 4001)
        for path in ("/api/events", "/api/events?token=agent-test-key"):
            self.assertEqual(self.client("8.8.8.8").get(path).status_code, 401)

    def test_sse_loopback_real_http(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, lifespan="off", log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            self.assertTrue(server.started)
            with httpx.stream("GET", f"http://127.0.0.1:{port}/api/events", timeout=5, trust_env=False) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn("event: presence", next(response.iter_lines()))
        finally:
            server.should_exit = True
            thread.join(10)
            self.assertFalse(thread.is_alive())

    def test_runtime_log_authentication(self):
        with Session(self.engine) as session:
            session.add(Project(project_id="project", display_name="Project", maintainer_member_id="human:operator"))
            session.add(ProjectRole(project_id="project", member_id="agent:test", role_name="test", created_by="human:operator"))
            session.commit()
        writer = RuntimeDiagnostics(root=Path(self.tmp.name) / "runtime", member_id="agent:test", project_id="project", instance_id="test")
        self.addCleanup(writer.close)
        writer.record_event("bridge_ready")
        provider = RuntimeDiagnosticsProvider.from_config({"runtime_diagnostics": {"sources": [
            {"project_id": "project", "member_id": "agent:test", "root": str(writer.root)}]}})
        main.app.dependency_overrides[diagnostics.get_runtime_diagnostics_provider] = lambda: provider
        self.addCleanup(main.app.dependency_overrides.clear)
        path = "/api/projects/project/roles/agent:test/runtime-logs"
        self.assertEqual(self.client().get(path).status_code, 200)
        for headers in ({}, {"X-API-Key": "agent-test-key"}):
            self.assertEqual(self.client("8.8.8.8").get(path, headers=headers).status_code, 401)
        with patch.object(db, "AUTH_MODE", "key"):
            self.assertEqual(self.client().get(path).status_code, 401)
            self.assertEqual(self.client().get(path, headers={"X-API-Key": ""}).status_code, 401)
