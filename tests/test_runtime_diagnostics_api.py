"""Isolated HTTP permission, target-scope and leakage tests for the new GET API."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

_OWN_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".tmp"
    / "runtime-log-view-v1"
    / "deepseek-backend"
    / "test-roots"
)
_OWN_ROOT.mkdir(parents=True, exist_ok=True)
_IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="api-import-", dir=str(_OWN_ROOT)))
_ORIGINAL_RUNTIME_LOG_DIR = os.environ.get("TALK_RUNTIME_LOG_DIR")
os.environ["TALK_RUNTIME_LOG_DIR"] = str(_IMPORT_ROOT / "runtime-logs")

# Import server.db first, patch the DB/log/storage targets, then import main.
# This mirrors the coordination isolation reference and keeps configure_logging
# away from the production log file.
import server.db as db  # noqa: E402

_ORIGINAL_LOG_PATH = db.LOG_PATH
_ORIGINAL_DB_ENGINE = db.engine
_ORIGINAL_STORAGE_DIR = db.STORAGE_DIR

db.LOG_PATH = _IMPORT_ROOT / "talk.log"
db.STORAGE_DIR = _IMPORT_ROOT / "storage"
db.engine = create_engine(
    "sqlite:///" + str(_IMPORT_ROOT / "import.db"),
    echo=False,
    connect_args={"check_same_thread": False},
)

import server.main as main  # noqa: E402
from server.models import Member, Project, ProjectAgent, ProjectRole  # noqa: E402
from server.routes.runtime_diagnostics import (  # noqa: E402
    get_runtime_diagnostics_provider,
)
from server.runtime_diagnostics_sources import (  # noqa: E402
    CursorCodec,
    RuntimeDiagnosticsProvider,
)

_ORIGINAL_MAIN_ENGINE = main.engine

HUMAN_KEY = "FAKE_HUMAN_KEY_FOR_API_ONLY"
AGENT_KEY = "FAKE_AGENT_KEY_FOR_API_ONLY"
DISABLED_KEY = "FAKE_DISABLED_KEY_FOR_API_ONLY"
OTHER_HUMAN_KEY = "FAKE_SECOND_HUMAN_KEY"
_NOW = datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc)


class _Clock:
    def __call__(self) -> datetime:
        return _NOW


def _record(
    log_id: str,
    *,
    project_id: str = "prj_fake_a",
    member_id: str = "agent:fake-a",
    severity: str = "error",
    event: str = "task_claim_failed",
    recorded_at: str = "2026-10-18T19:00:00+00:00",
    task_id: int | None = 274,
    **overrides,
) -> dict:
    record = {
        "schema": "talk-runtime-diagnostics-1",
        "log_id": log_id,
        "recorded_at": recorded_at,
        "event": event,
        "severity": severity,
        "stage": "task_claim",
        "project_id": project_id,
        "member_id": member_id,
        "instance_id": "ins_fake_api",
        "launch_id": "launch-fake-api",
        "pid": 987654,
        "runtime": "dsh",
        "task_id": task_id,
        "message_id": 1001,
        "returncode": None,
        "timeout": False,
        "cancel_category": None,
        "budgets": {"cli_timeout_seconds": 21600, "http_timeout_seconds": 15},
        "integrity": {
            "redacted": True,
            "redaction_kinds": ["known_value"],
            "truncated": False,
            "truncated_fields": [],
            "write_complete": True,
        },
        "run_id": "run-secret-value",
        "segment_file": "events-00001.jsonl",
        "message": "TOP LEVEL MESSAGE MUST NOT LEAK",
        "extra": {
            "argv": ["--api-key", "FAKE_ARG_KEY"],
            "env": {"FAKE_ENV_KEY": "FAKE_ENV_VALUE"},
            "owner_token": "FAKE_OWNER_TOKEN",
        },
        "exception": {
            "relation": "primary",
            "type": "TaskClaimError",
            "message": "open C:\\private\\cli_bridge.py and /srv/app/x.py failed",
            "str_empty": False,
            "message_error": False,
            "frames": [
                {
                    "file": "C:\\private\\cli_bridge.py",
                    "line": 3214,
                    "function": "handle_queued_task",
                    "source": "SOURCE LINE MUST NOT LEAK",
                },
                {
                    "file": "\\\\server\\share\\mod.py",
                    "line": 2,
                    "function": "request",
                    "source": "SECOND SOURCE",
                },
            ],
            "frames_total": 2,
            "frames_omitted": 0,
            "cause_chain": [
                {
                    "relation": "explicit_cause",
                    "type": "OSError",
                    "message": "cause at /mnt/data/secret.py",
                    "frames_total": 0,
                    "frames_omitted": 0,
                    "frames": [],
                }
            ],
            "chain_depth": 1,
            "chain_truncated": False,
            "chain_cycle": False,
            "has_explicit_cause": True,
            "context_present": False,
            "context_suppressed": False,
        },
    }
    record.update(overrides)
    return record


def _info_record(log_id: str, **overrides) -> dict:
    record = _record(
        log_id,
        severity="info",
        event="queue_started",
        task_id=None,
        **overrides,
    )
    record["exception"] = None
    return record


class _SpyProvider:
    def __init__(self, inner: RuntimeDiagnosticsProvider) -> None:
        self.inner = inner
        self.calls = 0

    def now(self) -> datetime:
        return self.inner.now()

    def list_logs(self, *args, **kwargs):
        self.calls += 1
        return self.inner.list_logs(*args, **kwargs)

    def get_detail(self, *args, **kwargs):
        self.calls += 1
        return self.inner.get_detail(*args, **kwargs)


class RuntimeLogApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(
            tempfile.mkdtemp(prefix="api-", dir=str(_OWN_ROOT))
        )
        self.engine = create_engine(
            "sqlite:///" + str(self.temp / "talk.db"),
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self._old_engine = db.engine
        self._old_main_engine = main.engine
        self._old_storage = db.STORAGE_DIR
        db.engine = self.engine
        main.engine = self.engine
        db.STORAGE_DIR = self.temp / "storage"
        db.STORAGE_DIR.mkdir(exist_ok=True)
        SQLModel.metadata.create_all(self.engine)
        self._seed_database()
        self.roots = {
            "main": self.temp / "root-main",
            "archived": self.temp / "root-archived",
            "project_b": self.temp / "root-b",
        }
        for root in self.roots.values():
            root.mkdir()
        self._write_sources()
        self.core = self._provider()
        self.spy = _SpyProvider(self.core)
        main.app.dependency_overrides[get_runtime_diagnostics_provider] = (
            lambda: self.spy
        )

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()
        self.engine.dispose()
        db.engine = self._old_engine
        main.engine = self._old_main_engine
        db.STORAGE_DIR = self._old_storage
        shutil.rmtree(self.temp, ignore_errors=True)

    def _seed_database(self) -> None:
        with Session(self.engine) as session:
            session.add(Member(id="human:fake", kind="human", display_name="Fake Human", api_key=HUMAN_KEY))
            session.add(Member(id="human:other", kind="human", display_name="Other Human", api_key=OTHER_HUMAN_KEY))
            session.add(Member(id="human:disabled", kind="human", display_name="Disabled", api_key=DISABLED_KEY, disabled_at=_NOW))
            session.add(Member(id="agent:fake-a", kind="agent", display_name="Fake A", api_key=AGENT_KEY))
            session.add(
                Member(
                    id="agent:fake-b",
                    kind="agent",
                    display_name="Fake B",
                    api_key="FAKE_B_KEY",
                    disabled_at=_NOW,
                )
            )
            session.add(
                Project(
                    project_id="prj_fake_a",
                    display_name="Project A",
                    maintainer_member_id="human:fake",
                )
            )
            session.add(
                Project(
                    project_id="prj_fake_b",
                    display_name="Project B",
                    maintainer_member_id="human:fake",
                )
            )
            session.add(
                Project(
                    project_id="prj_fake_c",
                    display_name="Project C",
                    maintainer_member_id="human:fake",
                )
            )
            session.add(
                ProjectRole(
                    project_id="prj_fake_a",
                    member_id="agent:fake-a",
                    role_name="fake-a",
                    created_by="human:fake",
                )
            )
            session.add(
                ProjectRole(
                    project_id="prj_fake_a",
                    member_id="agent:fake-b",
                    role_name="fake-b",
                    created_by="human:fake",
                    archived_at=_NOW,
                )
            )
            session.add(
                ProjectRole(
                    project_id="prj_fake_b",
                    member_id="agent:fake-a",
                    role_name="fake-b-project",
                    created_by="human:fake",
                )
            )
            session.add(
                ProjectRole(
                    project_id="prj_fake_c",
                    member_id="agent:fake-a",
                    role_name="fake-c",
                    created_by="human:fake",
                )
            )
            session.add(
                ProjectAgent(
                    project_id="prj_fake_a",
                    member_id="agent:fake-a",
                    business_role="dev",
                    capability_summary=[],
                )
            )
            session.add(
                ProjectAgent(
                    project_id="prj_fake_a",
                    member_id="agent:fake-roster",
                    business_role="dev",
                    capability_summary=[],
                )
            )
            session.commit()

    def _write_sources(self) -> None:
        main_records = [
            _record("rtd-api-0000000001", recorded_at="2026-10-18T19:00:00+00:00"),
            _record(
                "rtd-api-0000000002",
                severity="warning",
                event="managed_heartbeat_failure",
                recorded_at="2026-10-18T18:00:00+00:00",
                task_id=None,
            ),
            _info_record(
                "rtd-api-0000000003",
                recorded_at="2026-09-01T00:00:00+00:00",
            ),
            _record(
                "rtd-api-cross0001",
                project_id="prj_fake_b",
                recorded_at="2026-10-18T19:30:00+00:00",
            ),
            _record(
                "rtd-api-role0001",
                member_id="agent:fake-b",
                recorded_at="2026-10-18T19:40:00+00:00",
            ),
        ]
        with (self.roots["main"] / "events-00001.jsonl").open("w", encoding="utf-8") as stream:
            for record in main_records:
                stream.write(json.dumps(record) + "\n")
        archived = _record(
            "rtd-api-arch0001",
            project_id="prj_fake_a",
            member_id="agent:fake-b",
            recorded_at="2026-10-18T17:00:00+00:00",
        )
        with (self.roots["archived"] / "events-00001.jsonl").open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(archived) + "\n")
        project_b = _record(
            "rtd-api-b0000001",
            project_id="prj_fake_b",
            member_id="agent:fake-a",
            recorded_at="2026-10-18T16:00:00+00:00",
        )
        with (self.roots["project_b"] / "events-00001.jsonl").open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(project_b) + "\n")

    def _provider(self) -> RuntimeDiagnosticsProvider:
        config = {
            "runtime_diagnostics": {
                "sources": [
                    {
                        "project_id": "prj_fake_a",
                        "member_id": "agent:fake-a",
                        "root": str(self.roots["main"]),
                    },
                    {
                        "project_id": "prj_fake_a",
                        "member_id": "agent:fake-b",
                        "root": str(self.roots["archived"]),
                    },
                    {
                        "project_id": "prj_fake_b",
                        "member_id": "agent:fake-a",
                        "root": str(self.roots["project_b"]),
                    },
                ]
            }
        }
        return RuntimeDiagnosticsProvider.from_config(
            config,
            cursor_codec=CursorCodec(clock=_Clock(), ttl_seconds=600),
            clock=_Clock(),
        )

    def _client(self) -> TestClient:
        return TestClient(main.app)

    def _headers(self, key: str = HUMAN_KEY) -> dict[str, str]:
        return {"X-API-Key": key}

    def _url(self, project_id: str = "prj_fake_a", member_id: str = "agent:fake-a") -> str:
        return f"/api/projects/{project_id}/roles/{member_id}/runtime-logs"

    def test_no_key_invalid_key_and_disabled_are_401_or_403_without_scan(self) -> None:
        with self._client() as client:
            response = client.get(self._url())
            self.assertEqual(response.status_code, 401)
            response = client.get(self._url(), headers=self._headers("FAKE_WRONG_KEY"))
            self.assertEqual(response.status_code, 401)
            response = client.get(self._url(), headers=self._headers(DISABLED_KEY))
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.spy.calls, 0)

    def test_agent_is_forbidden_without_scan(self) -> None:
        with self._client() as client:
            response = client.get(self._url(), headers=self._headers(AGENT_KEY))
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["detail"], "log_read_forbidden")
            response = client.get(
                self._url() + "/rtd-api-0000000001/detail",
                headers=self._headers(AGENT_KEY),
            )
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.spy.calls, 0)

    def test_project_and_role_404_without_scan(self) -> None:
        with self._client() as client:
            response = client.get(
                "/api/projects/prj_missing/roles/agent:fake-a/runtime-logs",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "project_not_found")
            response = client.get(
                "/api/projects/prj_fake_a/roles/agent:missing/runtime-logs",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "role_not_found")
        self.assertEqual(self.spy.calls, 0)

    def test_human_default_summary_and_archived_role_history(self) -> None:
        with self._client() as client:
            response = client.get(self._url(), headers=self._headers())
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["schema"], "talk-runtime-log-page-1")
            self.assertEqual(body["scope"], {"project_id": "prj_fake_a", "member_id": "agent:fake-a"})
            self.assertEqual(body["query"]["severity"], ["error", "warning"])
            self.assertEqual(
                [item["log_id"] for item in body["records"]],
                ["rtd-api-0000000001", "rtd-api-0000000002"],
            )
            self.assertTrue(body["scan"]["complete"])
            self.assertIsNone(body["page"]["next_cursor"])
            for item in body["records"]:
                self.assertNotIn("frames", item)
                self.assertNotIn("cause_chain", item)
                self.assertNotIn("message", item)
            archived = client.get(
                self._url(member_id="agent:fake-b"), headers=self._headers()
            )
            self.assertEqual(archived.status_code, 200)
            self.assertEqual(
                [item["log_id"] for item in archived.json()["records"]],
                ["rtd-api-arch0001"],
            )

    def test_detail_info_and_path_scrubbing(self) -> None:
        with self._client() as client:
            info = client.get(
                self._url() + "/rtd-api-0000000003/detail?",
                headers=self._headers(),
            )
            self.assertEqual(info.status_code, 200)
            self.assertIsNone(info.json()["record"]["exception"])
            error = client.get(
                self._url() + "/rtd-api-0000000001/detail",
                headers=self._headers(),
            )
            self.assertEqual(error.status_code, 200)
            record = error.json()["record"]
            self.assertEqual(record["exception"]["frames"][0]["file_name"], "cli_bridge.py")
            self.assertEqual(record["exception"]["frames"][1]["file_name"], "mod.py")
            body = json.dumps(error.json(), ensure_ascii=False)
            for forbidden in (
                "C:\\",
                "\\\\server",
                "/srv",
                "/mnt",
                "SOURCE LINE MUST NOT LEAK",
                "TOP LEVEL MESSAGE MUST NOT LEAK",
                "FAKE_ARG_KEY",
                "FAKE_ENV_VALUE",
                "FAKE_OWNER_TOKEN",
                "987654",
                "run-secret-value",
                str(self.roots["main"]),
            ):
                self.assertNotIn(forbidden, body)
            self.assertNotIn('"source"', body)

    def test_unknown_duplicate_detail_query_and_ref_validation(self) -> None:
        with self._client() as client:
            response = client.get(self._url() + "?owner_token=x", headers=self._headers())
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "invalid_filter")
            response = client.get(
                self._url() + "?root=C%3A%5Cprivate", headers=self._headers()
            )
            self.assertEqual(response.status_code, 422)
            response = client.get(self._url() + "?limit=20&limit=20", headers=self._headers())
            self.assertEqual(response.status_code, 422)
            response = client.get(
                self._url() + "/rtd-api-0000000001/detail?detail=true",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 422)
            response = client.get(
                self._url() + "/..%2F..%2Fetc%2Fpasswd/detail",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "invalid_log_ref")
            response = client.get(
                self._url() + "?ref=rtd-api-0000000001&since=2026-10-17T00:00:00Z",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "conflicting_filters")
            response = client.get(
                self._url() + "?since=2026-10-17T00:00:00", headers=self._headers()
            )
            self.assertEqual(response.status_code, 422)
            response = client.get(self._url() + "?limit=51", headers=self._headers())
            self.assertEqual(response.status_code, 422)
            response = client.get(self._url() + "?severity=debug", headers=self._headers())
            self.assertEqual(response.status_code, 422)

    def test_time_span_and_query_ref_path_are_rejected(self) -> None:
        with self._client() as client:
            response = client.get(
                self._url()
                + "?since=2026-08-01T00:00:00Z&until=2026-10-18T00:00:00Z",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "invalid_filter")
            response = client.get(
                self._url()
                + "?since=2026-10-18T20:00:00Z&until=2026-10-18T19:00:00Z",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 422)
            response = client.get(
                self._url() + "?ref=..%2F..%2Fetc%2Fpasswd",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "invalid_log_ref")
            response = client.get(
                self._url() + "?task_id=0", headers=self._headers()
            )
            self.assertEqual(response.status_code, 422)

    def test_unconfigured_source_is_503(self) -> None:
        with self._client() as client:
            response = client.get(
                self._url(project_id="prj_fake_c"), headers=self._headers()
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"], "diagnostics_unavailable")
            # A current ProjectAgent roster-only pair is a valid target; lack of
            # a source is 503, not 404 role_not_found.
            response = client.get(
                self._url(member_id="agent:fake-roster"), headers=self._headers()
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"], "diagnostics_unavailable")

    def test_cross_project_cross_role_and_duplicate_ref(self) -> None:
        with self._client() as client:
            response = client.get(
                self._url() + "/rtd-api-cross0001/detail", headers=self._headers()
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "log_not_found")
            response = client.get(
                self._url() + "/rtd-api-role0001/detail", headers=self._headers()
            )
            self.assertEqual(response.status_code, 404)
            response = client.get(
                self._url(project_id="prj_fake_b")
                + "/rtd-api-0000000001/detail",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 404)
            # Same-project other role sees its own record, never A's.
            response = client.get(
                self._url(member_id="agent:fake-b")
                + "/rtd-api-0000000001/detail",
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 404)
            # A human can open project B's own endpoint and only gets B scope.
            response = client.get(
                self._url(project_id="prj_fake_b"), headers=self._headers()
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                [item["log_id"] for item in response.json()["records"]],
                ["rtd-api-b0000001"],
            )
            duplicate = _record(
                "rtd-api-0000000001",
                recorded_at="2026-10-18T19:00:00+00:00",
                exception={
                    **_record("rtd-api-0000000001")["exception"],
                    "message": "different duplicate",
                },
            )
            with (self.roots["main"] / "events-00001.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(duplicate) + "\n")
            response = client.get(
                self._url() + "/rtd-api-0000000001/detail", headers=self._headers()
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "log_ref_conflict")

    def test_http_pagination_replays_canonical_query(self) -> None:
        with self._client() as client:
            response = client.get(self._url() + "?limit=1", headers=self._headers())
            self.assertEqual(response.status_code, 200)
            page1 = response.json()
            self.assertIsNotNone(page1["page"]["next_cursor"])
            query = page1["query"]
            response = client.get(
                self._url(),
                headers=self._headers(),
                params={
                    "limit": 1,
                    "since": query["since"],
                    "until": query["until"],
                    "severity": ",".join(query["severity"]),
                    "cursor": page1["page"]["next_cursor"],
                },
            )
            self.assertEqual(response.status_code, 200)
            page2 = response.json()
            self.assertEqual(page2["query"], query)
            self.assertEqual(
                [item["log_id"] for item in page2["records"]],
                ["rtd-api-0000000002"],
            )
            tampered = page1["page"]["next_cursor"]
            body, signature = tampered.split(".")
            tampered = body + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
            response = client.get(
                self._url(),
                headers=self._headers(),
                params={
                    "limit": 1,
                    "since": query["since"],
                    "until": query["until"],
                    "severity": ",".join(query["severity"]),
                    "cursor": tampered,
                },
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "invalid_cursor")

    def test_random_loopback_port_http_is_isolated(self) -> None:
        try:
            import httpx
            import uvicorn
        except ImportError as exc:
            self.skipTest(f"loopback dependencies unavailable: {type(exc).__name__}")
        config = uvicorn.Config(
            main.app,
            host="127.0.0.1",
            port=0,
            log_level="critical",
            access_log=False,
            lifespan="off",
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        if not server.started:
            server.should_exit = True
            thread.join(5)
            self.fail("isolated uvicorn did not start")
        try:
            port = server.servers[0].sockets[0].getsockname()[1]
            self.assertNotEqual(port, 8000)
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(timeout=5) as client:
                health = client.get(base + "/healthz")
                if health.status_code == 503 and not health.text:
                    # This sandbox intercepts loopback TCP with an empty 503
                    # before the ASGI app sees the request (a minimal uvicorn
                    # app reproduces it).  Record the physical loopback path as
                    # not_run instead of pretending the assertion passed.
                    self.skipTest(
                        "sandbox intercepts loopback HTTP with empty 503 before app"
                    )
                self.assertEqual(health.status_code, 200)
                unauthorized = client.get(base + self._url())
                self.assertEqual(unauthorized.status_code, 401)
                response = client.get(base + self._url(), headers=self._headers())
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["schema"], "talk-runtime-log-page-1")
        finally:
            server.should_exit = True
            thread.join(10)


def tearDownModule() -> None:
    """Restore import-time patches so a full-suite run is not contaminated."""
    main.app.dependency_overrides.clear()
    db.LOG_PATH = _ORIGINAL_LOG_PATH
    db.engine = _ORIGINAL_DB_ENGINE
    db.STORAGE_DIR = _ORIGINAL_STORAGE_DIR
    main.engine = _ORIGINAL_MAIN_ENGINE
    if _ORIGINAL_RUNTIME_LOG_DIR is None:
        os.environ.pop("TALK_RUNTIME_LOG_DIR", None)
    else:
        os.environ["TALK_RUNTIME_LOG_DIR"] = _ORIGINAL_RUNTIME_LOG_DIR


if __name__ == "__main__":
    unittest.main()
