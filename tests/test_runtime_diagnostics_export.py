"""276 统一诊断导出与阶段时间线的隔离测试。

只使用本任务临时根、假 Key/记录、隔离 SQLite 与 ASGI TestClient；不连接真实
TALK API、不读取生产 logs/runtime/talk.db、不启动模型或真实子进程。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

_OWN_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".tmp"
    / "runtime-diagnostics-export-v1"
    / "deepseek-backend"
    / "test-roots"
)
_OWN_ROOT.mkdir(parents=True, exist_ok=True)
_IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="export-import-", dir=str(_OWN_ROOT)))
_ORIGINAL_RUNTIME_LOG_DIR = os.environ.get("TALK_RUNTIME_LOG_DIR")
os.environ["TALK_RUNTIME_LOG_DIR"] = str(_IMPORT_ROOT / "runtime-logs")

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
from bridges import runtime_diagnostics as runtime_diag  # noqa: E402
from bridges.runtime_diagnostics_timeline import StageTimeline  # noqa: E402
from server.models import Member, Project, ProjectAgent, ProjectRole  # noqa: E402
from server.routes.runtime_diagnostics import (  # noqa: E402
    get_runtime_diagnostics_provider,
)
from server.runtime_diagnostics_export import (  # noqa: E402
    MAX_EXPORT_BYTES,
    build_export,
    parse_export_time,
)
from server.runtime_diagnostics_query import ScanLimits, Source  # noqa: E402
from server.runtime_diagnostics_query import RuntimeDiagnosticsError  # noqa: E402
from server.runtime_diagnostics_sources import (  # noqa: E402
    CursorCodec,
    RuntimeDiagnosticsProvider,
)

_ORIGINAL_MAIN_ENGINE = main.engine
_ORIGINAL_MAIN_STORAGE = getattr(main, "STORAGE_DIR", None)

HUMAN_KEY = "FAKE_EXPORT_HUMAN_KEY"
OTHER_HUMAN_KEY = "FAKE_EXPORT_OTHER_HUMAN_KEY"
AGENT_KEY = "FAKE_EXPORT_AGENT_KEY"
DISABLED_KEY = "FAKE_EXPORT_DISABLED_KEY"
PROJECT = "prj_export_a"
MEMBER = "agent:export-a"
ARCHIVED = "agent:export-b"
ROSTER = "agent:export-roster"
NOW = datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc)
SINCE = "2026-10-18T00:00:00Z"
UNTIL = "2026-10-20T00:00:00Z"


class _Clock:
    def __call__(self) -> datetime:
        return NOW


def _point(log_id: str, *, recorded_at: str, **overrides) -> dict:
    record = {
        "schema": "talk-runtime-diagnostics-1",
        "log_id": log_id,
        "recorded_at": recorded_at,
        "event": "task_cli_finished",
        "severity": "info",
        "stage": "task_cli",
        "project_id": PROJECT,
        "member_id": MEMBER,
        "instance_id": "ins_export_a1",
        "launch_id": "launch-export-a1",
        "pid": 123456,
        "runtime": "dsh",
        "task_id": 276,
        "message_id": 7001,
        "returncode": 0,
        "timeout": False,
        "cancel_category": None,
        "budgets": {
            "cli_timeout_seconds": 21600,
            "http_timeout_seconds": 15,
            "task_lease_seconds": 120,
        },
        "integrity": {
            "redacted": False,
            "redaction_kinds": [],
            "truncated": False,
            "truncated_fields": [],
            "write_complete": True,
        },
        "message": "TOP LEVEL MESSAGE IS NOT EXPORTED",
    }
    record.update(overrides)
    return record


def _exception(message: str = "raw failure at C:\\private\\app.py") -> dict:
    return {
        "relation": "primary",
        "type": "RuntimeError",
        "type_module": "builtins",
        "type_qualname": "RuntimeError",
        "message": message,
        "str_empty": False,
        "message_error": False,
        "frames": [
            {
                "file": "C:\\private\\app.py",
                "line": 44,
                "function": "run",
                "source": "PRIVATE SOURCE LINE",
            }
        ],
        "frames_total": 1,
        "frames_omitted": 0,
        "context_present": False,
        "context_suppressed": False,
        "has_explicit_cause": True,
        "cause_chain": [
            {
                "relation": "explicit_cause",
                "type": "OSError",
                "message": "cause at /srv/private/keys.txt",
                "frames_total": 0,
                "frames_omitted": 0,
                "frames": [],
            }
        ],
        "chain_depth": 1,
        "chain_truncated": False,
        "chain_cycle": False,
    }


def _transition(
    operation_id: str = "op-0123456789abcdef",
    *,
    status: str = "started",
    attempt: int | None = 2,
    started_at: str = "2026-10-18T10:00:00Z",
    finished_at: str | None = None,
    duration_ms: float | None = None,
) -> dict:
    return {
        "operation_id": operation_id,
        "status": status,
        "from_state": None if status == "started" else "task_cli",
        "to_state": "task_cli" if status == "started" else None,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "attempt": attempt,
    }


def _write_records(root: Path, records: list[dict], *, name: str = "events-00001.jsonl") -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / name).open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _append_line(root: Path, line: str, *, name: str = "events-00001.jsonl") -> None:
    with (root / name).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")


def _make_link(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=5,
        )


def _remove_link(link: Path) -> None:
    try:
        if os.path.islink(link):
            link.unlink()
        elif link.exists():
            os.rmdir(link)
    except OSError:
        pass


def _parse_ndjson(body: bytes) -> tuple[dict, list[dict]]:
    lines = body.splitlines()
    if not lines:
        raise AssertionError("empty NDJSON body")
    meta = json.loads(lines[0])
    events = [json.loads(line) for line in lines[1:]]
    if meta.get("record_count") != len(events):
        raise AssertionError("meta record_count does not match event lines")
    return meta, events


class ExportApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_logging_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        self.temp = Path(tempfile.mkdtemp(prefix="export-", dir=str(_OWN_ROOT)))
        self.engine = create_engine(
            "sqlite:///" + str(self.temp / "talk.db"),
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self._old_engine = db.engine
        self._old_main_engine = main.engine
        self._old_storage = db.STORAGE_DIR
        self._old_main_storage = getattr(main, "STORAGE_DIR", None)
        db.engine = self.engine
        main.engine = self.engine
        db.STORAGE_DIR = self.temp / "storage"
        if hasattr(main, "STORAGE_DIR"):
            main.STORAGE_DIR = self.temp / "storage"
        db.STORAGE_DIR.mkdir(exist_ok=True)
        SQLModel.metadata.create_all(self.engine)
        self._seed_database()
        self.root = self.temp / "runtime"
        self.root.mkdir()
        self.provider = self._provider()
        main.app.dependency_overrides[get_runtime_diagnostics_provider] = lambda: self.provider

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()
        self.engine.dispose()
        db.engine = self._old_engine
        main.engine = self._old_main_engine
        db.STORAGE_DIR = self._old_storage
        if self._old_main_storage is not None:
            main.STORAGE_DIR = self._old_main_storage
        logging.disable(self._old_logging_disable)
        shutil.rmtree(self.temp, ignore_errors=True)

    def _seed_database(self) -> None:
        with Session(self.engine) as session:
            session.add(Member(id="human:export", kind="human", display_name="Export Human", api_key=HUMAN_KEY))
            session.add(Member(id="human:export-other", kind="human", display_name="Other", api_key=OTHER_HUMAN_KEY))
            session.add(Member(id="human:disabled", kind="human", display_name="Disabled", api_key=DISABLED_KEY, disabled_at=NOW))
            session.add(Member(id=MEMBER, kind="agent", display_name="Export A", api_key=AGENT_KEY))
            session.add(Member(id=ARCHIVED, kind="agent", display_name="Export B", api_key="FAKE_EXPORT_B_KEY"))
            session.add(Member(id=ROSTER, kind="agent", display_name="Roster", api_key="FAKE_EXPORT_ROSTER_KEY"))
            session.add(Project(project_id=PROJECT, display_name="Export Project", maintainer_member_id="human:export"))
            session.add(Project(project_id="prj_export_c", display_name="Export C", maintainer_member_id="human:export"))
            session.add(ProjectRole(project_id=PROJECT, member_id=MEMBER, role_name="export-a", created_by="human:export"))
            session.add(ProjectRole(project_id=PROJECT, member_id=ARCHIVED, role_name="export-b", created_by="human:export", archived_at=NOW))
            session.add(ProjectRole(project_id="prj_export_c", member_id=MEMBER, role_name="export-c", created_by="human:export"))
            session.add(ProjectAgent(project_id=PROJECT, member_id=ROSTER, business_role="dev", capability_summary=[]))
            session.commit()

    def _provider(self, *, scan_limits: ScanLimits | None = None) -> RuntimeDiagnosticsProvider:
        config = {
            "runtime_diagnostics": {
                "sources": [
                    {"project_id": PROJECT, "member_id": MEMBER, "root": str(self.root)},
                    {
                        "project_id": PROJECT,
                        "member_id": ARCHIVED,
                        "root": str(self.temp / "archived"),
                    },
                ]
            }
        }
        return RuntimeDiagnosticsProvider.from_config(
            config,
            scan_limits=scan_limits,
            cursor_codec=CursorCodec(clock=_Clock(), ttl_seconds=600),
            clock=_Clock(),
        )

    def _client(self) -> TestClient:
        return TestClient(main.app)

    def _headers(self, key: str = HUMAN_KEY) -> dict[str, str]:
        return {"X-API-Key": key}

    def _url(self, *, project_id: str = PROJECT, member_id: str = MEMBER) -> str:
        return f"/api/projects/{project_id}/roles/{member_id}/runtime-logs/export"

    def _query(self, *, since: str = SINCE, until: str = UNTIL) -> dict[str, str]:
        return {"since": since, "until": until}

    # ------------------------------------------------------------------
    def test_headers_meta_and_old_records(self) -> None:
        _write_records(
            self.root,
            [
                _point("rtd-export-0000000003", recorded_at="2026-10-18T11:00:00Z"),
                _point("rtd-export-0000000001", recorded_at="2026-10-18T09:00:00Z"),
                _point("rtd-export-0000000002", recorded_at="2026-10-18T10:00:00Z"),
            ],
        )
        with self._client() as client:
            response = client.get(self._url(), params=self._query(), headers=self._headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "application/x-ndjson")
        self.assertEqual(
            response.headers["content-disposition"],
            'attachment; filename="talk-diagnostics_20261018T000000Z_20261020T000000Z.jsonl"',
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        meta, events = _parse_ndjson(response.content)
        self.assertEqual(meta["kind"], "meta")
        self.assertEqual(meta["schema"], "talk-diagnostics-export-1")
        self.assertEqual(meta["scope"], {"project_id": PROJECT, "member_id": MEMBER})
        self.assertEqual(meta["query"], {"since": "2026-10-18T00:00:00Z", "until": "2026-10-20T00:00:00Z"})
        self.assertEqual(meta["record_count"], 3)
        self.assertTrue(meta["complete"])
        self.assertFalse(meta["truncated"])
        self.assertEqual(meta["reasons"], [])
        self.assertTrue(meta["scan"]["complete"])
        self.assertEqual([event["log_id"] for event in events], [
            "rtd-export-0000000001",
            "rtd-export-0000000002",
            "rtd-export-0000000003",
        ])
        for event in events:
            self.assertEqual(event["kind"], "event")
            self.assertIsNone(event["phase"])
            self.assertIsNone(event["transition"])
            self.assertNotIn("message", event)
            self.assertNotIn("extra", event)

    def test_time_window_is_half_open_and_timezone_normalized(self) -> None:
        _write_records(
            self.root,
            [
                _point("rtd-window-0000000001", recorded_at="2026-10-17T23:59:59Z"),
                _point("rtd-window-0000000002", recorded_at="2026-10-18T00:00:00Z"),
                _point("rtd-window-0000000003", recorded_at="2026-10-18T12:00:00Z"),
                _point("rtd-window-0000000004", recorded_at="2026-10-19T00:00:00Z"),
            ],
        )
        with self._client() as client:
            response = client.get(
                self._url(),
                params={
                    "since": "2026-10-18T08:00:00+08:00",
                    "until": "2026-10-19T08:00:00+08:00",
                },
                headers=self._headers(),
            )
        self.assertEqual(response.status_code, 200)
        meta, events = _parse_ndjson(response.content)
        self.assertEqual(meta["query"]["since"], "2026-10-18T00:00:00Z")
        self.assertEqual(meta["query"]["until"], "2026-10-19T00:00:00Z")
        self.assertEqual([event["log_id"] for event in events], [
            "rtd-window-0000000002",
            "rtd-window-0000000003",
        ])

    def test_more_than_fifty_records_across_instances(self) -> None:
        records = []
        for index in range(75):
            records.append(
                _point(
                    f"rtd-many-{index:010d}",
                    recorded_at=f"2026-10-18T{(index % 24):02d}:{index % 60:02d}:00Z",
                    instance_id=f"ins_export_{index % 3}",
                    launch_id=f"launch-export-{index % 3}",
                )
            )
        _write_records(self.root, records)
        with self._client() as client:
            response = client.get(self._url(), params=self._query(), headers=self._headers())
        self.assertEqual(response.status_code, 200)
        meta, events = _parse_ndjson(response.content)
        self.assertEqual(meta["record_count"], 75)
        self.assertEqual(len(events), 75)
        self.assertTrue(meta["complete"])
        self.assertEqual(len({event["instance_id"] for event in events}), 3)
        keys = [(event["recorded_at"], event["log_id"]) for event in events]
        self.assertEqual(keys, sorted(keys))

    def test_permissions_and_archived_history_scope(self) -> None:
        _write_records(self.root, [_point("rtd-perm-0000000001", recorded_at="2026-10-18T10:00:00Z")])
        _write_records(
            self.temp / "archived",
            [
                _point(
                    "rtd-arch-0000000001",
                    recorded_at="2026-10-18T10:00:00Z",
                    member_id=ARCHIVED,
                )
            ],
        )
        with self._client() as client:
            self.assertEqual(client.get(self._url()).status_code, 401)
            self.assertEqual(client.get(self._url(), headers=self._headers("WRONG")).status_code, 401)
            self.assertEqual(client.get(self._url(), headers=self._headers(DISABLED_KEY)).status_code, 403)
            agent = client.get(self._url(), headers={"X-API-Key": AGENT_KEY})
            self.assertEqual(agent.status_code, 403)
            self.assertEqual(agent.json()["detail"], "log_read_forbidden")
            self.assertEqual(
                client.get(self._url(project_id="prj_missing"), headers=self._headers()).status_code,
                404,
            )
            missing_role = client.get(
                self._url(member_id="agent:missing"), headers=self._headers()
            )
            self.assertEqual(missing_role.status_code, 404)
            archived = client.get(
                self._url(member_id=ARCHIVED), params=self._query(), headers=self._headers()
            )
            self.assertEqual(archived.status_code, 200)
            _, events = _parse_ndjson(archived.content)
            self.assertEqual([event["log_id"] for event in events], ["rtd-arch-0000000001"])
            roster = client.get(
                self._url(member_id=ROSTER), params=self._query(), headers=self._headers()
            )
            self.assertEqual(roster.status_code, 503)
            self.assertEqual(roster.json()["detail"], "diagnostics_unavailable")
            unconfigured = client.get(
                self._url(project_id="prj_export_c"),
                params=self._query(),
                headers=self._headers(),
            )
            self.assertEqual(unconfigured.status_code, 503)
            self.assertEqual(unconfigured.json()["detail"], "diagnostics_unavailable")

    def test_old_list_and_detail_endpoints_still_work(self) -> None:
        _write_records(
            self.root,
            [
                _point(
                    "rtd-old-0000000001",
                    recorded_at="2026-10-18T10:00:00Z",
                    severity="error",
                    exception=_exception(),
                )
            ],
        )
        with self._client() as client:
            listing = client.get(
                self._url().removesuffix("/export"),
                params={"since": SINCE, "until": UNTIL},
                headers=self._headers(),
            )
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.json()["schema"], "talk-runtime-log-page-1")
            detail = client.get(
                self._url().removesuffix("/export") + "/rtd-old-0000000001/detail",
                headers=self._headers(),
            )
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["schema"], "talk-runtime-log-detail-1")
            self.assertEqual(detail.json()["record"]["log_id"], "rtd-old-0000000001")

    def test_nested_exception_and_null_exception(self) -> None:
        _write_records(
            self.root,
            [
                _point(
                    "rtd-exc-0000000001",
                    recorded_at="2026-10-18T10:00:00Z",
                    severity="error",
                    exception=_exception("root failure"),
                ),
                _point(
                    "rtd-exc-0000000002",
                    recorded_at="2026-10-18T11:00:00Z",
                    severity="warning",
                    exception=None,
                ),
            ],
        )
        with self._client() as client:
            response = client.get(self._url(), params=self._query(), headers=self._headers())
        self.assertEqual(response.status_code, 200)
        _, events = _parse_ndjson(response.content)
        self.assertEqual(events[0]["exception"]["message"], "root failure")
        self.assertEqual(events[0]["exception"]["frames"][0]["file_name"], "app.py")
        self.assertEqual(events[0]["exception"]["cause_chain"][0]["type"], "OSError")
        self.assertIsNone(events[1]["exception"])

    def test_redaction_transition_whitelist_and_no_raw_extra(self) -> None:
        secret = "sk-export-OPAQUE-1234567890"
        record = _point(
            "rtd-redact-0000000001",
            recorded_at="2026-10-18T10:00:00Z",
            severity="error",
            exception=_exception(
                f"Authorization: Bearer {secret} open C:\\private\\app.py /srv/secret"
            ),
            extra={
                "transition": _transition("op-abcdef0123456789"),
                "argv": ["--api-key", secret],
                "env": {"TOKEN": secret},
                "prompt": "PRIVATE PROMPT",
                "source_file": "C:\\private\\events-00001.jsonl",
            },
        )
        record["message"] = "TOP LEVEL MESSAGE MUST NOT LEAK"
        _write_records(self.root, [record])
        with self._client() as client:
            response = client.get(self._url(), params=self._query(), headers=self._headers())
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8")
        for forbidden in (
            secret,
            "PRIVATE PROMPT",
            "TOP LEVEL MESSAGE MUST NOT LEAK",
            r"C:\private",
            "/srv/secret",
            "PRIVATE SOURCE LINE",
            "argv",
            "owner_token",
            str(self.root),
        ):
            self.assertNotIn(forbidden, text)
        _, events = _parse_ndjson(response.content)
        event = events[0]
        self.assertNotIn("extra", event)
        self.assertEqual(event["transition"]["operation_id"], "op-abcdef0123456789")
        self.assertEqual(event["transition"]["attempt"], 2)
        self.assertNotIn("source", json.dumps(event["exception"], ensure_ascii=False))

    def test_transition_pair_and_projection_failure(self) -> None:
        _write_records(
            self.root,
            [
                _point(
                    "rtd-tr-0000000001",
                    recorded_at="2026-10-18T10:00:00Z",
                    extra={"transition": _transition("op-1111111111111111", status="started")},
                ),
                _point(
                    "rtd-tr-0000000002",
                    recorded_at="2026-10-18T10:00:01Z",
                    extra={
                        "transition": _transition(
                            "op-1111111111111111",
                            status="succeeded",
                            finished_at="2026-10-18T10:00:01Z",
                            duration_ms=12.5,
                            attempt=2,
                        )
                    },
                ),
                _point(
                    "rtd-tr-0000000003",
                    recorded_at="2026-10-18T10:00:02Z",
                    extra={"transition": {"operation_id": "bad", "status": "started"}},
                ),
            ],
        )
        with self._client() as client:
            response = client.get(self._url(), params=self._query(), headers=self._headers())
        self.assertEqual(response.status_code, 200)
        meta, events = _parse_ndjson(response.content)
        self.assertEqual(meta["record_count"], 2)
        self.assertFalse(meta["complete"])
        self.assertIn("projection_failed", meta["reasons"])
        first, second = events
        self.assertEqual(first["transition"]["status"], "started")
        self.assertIsNone(first["transition"]["finished_at"])
        self.assertIsNone(first["transition"]["duration_ms"])
        self.assertEqual(second["transition"]["status"], "succeeded")
        self.assertEqual(second["transition"]["duration_ms"], 12.5)
        self.assertEqual(second["transition"]["attempt"], 2)
        self.assertEqual(
            first["transition"]["operation_id"], second["transition"]["operation_id"]
        )

    def test_export_query_validation(self) -> None:
        with self._client() as client:
            cases = [
                {},
                {"since": SINCE},
                {"until": UNTIL},
                {"since": SINCE, "until": UNTIL, "limit": "20"},
                {"since": SINCE, "until": UNTIL, "severity": "error"},
                {"since": SINCE, "until": UNTIL, "ref": "rtd-x"},
                {"since": "2026-10-18T00:00:00", "until": UNTIL},
                {"since": "2026-10-19T00:00:00Z", "until": "2026-10-18T00:00:00Z"},
                {"since": "2026-08-01T00:00:00Z", "until": "2026-10-18T00:00:00Z"},
                {"since": "not-a-time", "until": UNTIL},
            ]
            for case in cases:
                with self.subTest(case=case):
                    response = client.get(self._url(), params=case, headers=self._headers())
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["detail"], "invalid_filter")
                    self.assertNotEqual(
                        response.headers.get("content-type", "").split(";")[0],
                        "application/x-ndjson",
                    )
            duplicate = client.get(
                self._url() + f"?since={SINCE}&since={SINCE}&until={UNTIL}",
                headers=self._headers(),
            )
            self.assertEqual(duplicate.status_code, 422)

    def test_empty_result_has_meta_only(self) -> None:
        with self._client() as client:
            response = client.get(self._url(), params=self._query(), headers=self._headers())
        self.assertEqual(response.status_code, 200)
        meta, events = _parse_ndjson(response.content)
        self.assertEqual(events, [])
        self.assertEqual(meta["record_count"], 0)
        self.assertTrue(meta["complete"])
        self.assertEqual(meta["scan"]["scanned_files"], 0)

    def test_real_timeline_records_project_end_to_end(self) -> None:
        writer = runtime_diag.RuntimeDiagnostics(
            member_id=MEMBER,
            instance_id="ins_export_real",
            root=self.root,
            project_id=PROJECT,
            launch_id="launch-export-real",
            runtime="dsh",
            clock=_Clock(),
        )
        operation = StageTimeline(writer, wall_clock=_Clock()).start(
            "task_model_preflight",
            phase="task_preflight",
            task_id=276,
            attempt=2,
            budgets={"cli_timeout_seconds": 5},
        )
        operation.finish("succeeded", returncode=0, timeout=False)
        body = build_export(
            Source(PROJECT, MEMBER, self.root),
            project_id=PROJECT,
            member_id=MEMBER,
            since=parse_export_time(SINCE),
            until=parse_export_time(UNTIL),
            generated_at=NOW,
        )
        meta, events = _parse_ndjson(body)
        self.assertTrue(meta["complete"])
        self.assertEqual(meta["record_count"], 2)
        self.assertEqual(events[0]["phase"], "task_preflight")
        self.assertEqual(events[0]["task_id"], 276)
        self.assertEqual(events[0]["transition"]["status"], "started")
        self.assertEqual(events[1]["transition"]["status"], "succeeded")
        self.assertEqual(events[1]["transition"]["attempt"], 2)
        self.assertEqual(
            events[0]["transition"]["operation_id"],
            events[1]["transition"]["operation_id"],
        )
        self.assertGreaterEqual(events[1]["transition"]["duration_ms"], 0)

    def test_malformed_line_and_duplicate_log_id_are_incomplete(self) -> None:
        first = _point("rtd-dup-0000000001", recorded_at="2026-10-18T10:00:00Z")
        second = _point("rtd-dup-0000000001", recorded_at="2026-10-18T10:00:01Z")
        _write_records(self.root, [first, second])
        _append_line(self.root, "{not json")
        with self._client() as client:
            response = client.get(self._url(), params=self._query(), headers=self._headers())
        self.assertEqual(response.status_code, 200)
        meta, events = _parse_ndjson(response.content)
        self.assertEqual(len(events), 2)
        self.assertFalse(meta["complete"])
        self.assertIn("malformed_records", meta["reasons"])
        self.assertIn("duplicate_log_id", meta["reasons"])
        self.assertEqual(meta["scan"]["malformed_lines"], 1)

    def test_symlink_entry_is_not_followed_and_is_incomplete(self) -> None:
        outside = self.temp / "outside"
        _write_records(outside, [_point("rtd-outside-0000000001", recorded_at="2026-10-18T10:00:00Z")])
        link = self.root / "linked"
        try:
            _make_link(link, outside)
        except (OSError, subprocess.SubprocessError) as exc:
            self.skipTest(f"cannot create test link: {type(exc).__name__}")
        try:
            with self._client() as client:
                response = client.get(self._url(), params=self._query(), headers=self._headers())
        finally:
            _remove_link(link)
        self.assertEqual(response.status_code, 200)
        meta, events = _parse_ndjson(response.content)
        self.assertEqual(events, [])
        self.assertFalse(meta["complete"])
        self.assertIn("unavailable_records", meta["reasons"])

    def test_concurrent_append_is_reported_as_source_changed(self) -> None:
        _write_records(
            self.root,
            [_point("rtd-change-0000000001", recorded_at="2026-10-18T10:00:00Z")],
        )
        path = self.root / "events-00001.jsonl"
        from server import runtime_diagnostics_query as query

        original = query._open_checked
        changed = {"done": False}

        def append_after_open(file, expected):
            fd, opened = original(file, expected)
            if not changed["done"]:
                _append_line(self.root, '{"schema":"late"}')
                changed["done"] = True
            return fd, opened

        with mock.patch.object(query, "_open_checked", side_effect=append_after_open):
            body = build_export(
                Source(PROJECT, MEMBER, self.root),
                project_id=PROJECT,
                member_id=MEMBER,
                since=parse_export_time(SINCE),
                until=parse_export_time(UNTIL),
                generated_at=NOW,
            )
        self.assertTrue(changed["done"])
        meta, _ = _parse_ndjson(body)
        self.assertFalse(meta["complete"])
        self.assertIn("source_changed", meta["reasons"])

    def test_scan_budget_is_incomplete(self) -> None:
        _write_records(
            self.root,
            [_point("rtd-budget-0000000001", recorded_at="2026-10-18T10:00:00Z")],
        )
        _write_records(
            self.root,
            [_point("rtd-budget-0000000002", recorded_at="2026-10-18T10:00:01Z")],
            name="events-00002.jsonl",
        )
        body = build_export(
            Source(PROJECT, MEMBER, self.root),
            project_id=PROJECT,
            member_id=MEMBER,
            since=parse_export_time(SINCE),
            until=parse_export_time(UNTIL),
            generated_at=NOW,
            limits=ScanLimits(max_files=1),
        )
        meta, _ = _parse_ndjson(body)
        self.assertFalse(meta["complete"])
        self.assertIn("scan_incomplete", meta["reasons"])

    def test_time_limit_is_explicit(self) -> None:
        _write_records(
            self.root,
            [_point("rtd-time-0000000001", recorded_at="2026-10-18T10:00:00Z")],
        )
        body = build_export(
            Source(PROJECT, MEMBER, self.root),
            project_id=PROJECT,
            member_id=MEMBER,
            since=parse_export_time(SINCE),
            until=parse_export_time(UNTIL),
            generated_at=NOW,
            limits=ScanLimits(max_seconds=0.0),
        )
        meta, _ = _parse_ndjson(body)
        self.assertFalse(meta["complete"])
        self.assertIn("time_limit", meta["reasons"])
        self.assertTrue(meta["truncated"])

    def test_nested_relink_during_scan_never_exports_outside_record(self) -> None:
        from server import runtime_diagnostics_query as query

        nested = self.root / "safe"
        nested.mkdir()
        _write_records(nested, [_point("rtd-inside-0000000001", recorded_at="2026-10-18T10:00:00Z")])
        saved = self.root / "original-safe"
        outside = self.temp / "outside-swap"
        _write_records(
            outside,
            [_point("rtd-outside-0000000002", recorded_at="2026-10-18T10:00:00Z")],
        )
        real_scandir = os.scandir
        swapped = {"done": False}
        probe = self.temp / "link-probe"
        try:
            _make_link(probe, outside)
            _remove_link(probe)
        except (OSError, subprocess.SubprocessError) as exc:
            self.skipTest(f"cannot create test link: {type(exc).__name__}")

        def racing_scandir(path):
            if Path(path) == nested and not swapped["done"]:
                nested.rename(saved)
                _make_link(nested, outside)
                swapped["done"] = True
            return real_scandir(path)

        try:
            with mock.patch.object(query.os, "scandir", side_effect=racing_scandir):
                try:
                    body = build_export(
                        Source(PROJECT, MEMBER, self.root),
                        project_id=PROJECT,
                        member_id=MEMBER,
                        since=parse_export_time(SINCE),
                        until=parse_export_time(UNTIL),
                        generated_at=NOW,
                    )
                except RuntimeDiagnosticsError as exc:
                    self.assertEqual(exc.status_code, 503)
                    return
            self.assertTrue(swapped["done"])
            self.assertNotIn(b"rtd-outside-0000000002", body)
            meta, _ = _parse_ndjson(body)
            self.assertFalse(meta["complete"])
        finally:
            _remove_link(nested)

    def test_record_and_byte_limits_keep_complete_lines(self) -> None:
        records = [
            _point(f"rtd-limit-{index:010d}", recorded_at=f"2026-10-18T10:0{index}:00Z")
            for index in range(6)
        ]
        _write_records(self.root, records)
        limited = build_export(
            Source(PROJECT, MEMBER, self.root),
            project_id=PROJECT,
            member_id=MEMBER,
            since=parse_export_time(SINCE),
            until=parse_export_time(UNTIL),
            generated_at=NOW,
            max_records=3,
        )
        meta, events = _parse_ndjson(limited)
        self.assertEqual(len(events), 3)
        self.assertEqual(meta["record_count"], 3)
        self.assertIn("record_limit", meta["reasons"])
        self.assertTrue(meta["truncated"])
        self.assertFalse(meta["complete"])

        byte_limited = build_export(
            Source(PROJECT, MEMBER, self.root),
            project_id=PROJECT,
            member_id=MEMBER,
            since=parse_export_time(SINCE),
            until=parse_export_time(UNTIL),
            generated_at=NOW,
            max_bytes=1800,
        )
        meta, events = _parse_ndjson(byte_limited)
        self.assertLess(len(events), 6)
        self.assertEqual(meta["record_count"], len(events))
        self.assertIn("byte_limit", meta["reasons"])
        self.assertTrue(meta["truncated"])
        self.assertFalse(meta["complete"])

    def test_unavailable_root_is_503(self) -> None:
        shutil.rmtree(self.root)
        with self._client() as client:
            response = client.get(self._url(), params=self._query(), headers=self._headers())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "diagnostics_unavailable")


def tearDownModule() -> None:
    main.app.dependency_overrides.clear()
    db.LOG_PATH = _ORIGINAL_LOG_PATH
    db.engine = _ORIGINAL_DB_ENGINE
    db.STORAGE_DIR = _ORIGINAL_STORAGE_DIR
    main.engine = _ORIGINAL_MAIN_ENGINE
    if _ORIGINAL_MAIN_STORAGE is not None:
        main.STORAGE_DIR = _ORIGINAL_MAIN_STORAGE
    if _ORIGINAL_RUNTIME_LOG_DIR is None:
        os.environ.pop("TALK_RUNTIME_LOG_DIR", None)
    else:
        os.environ["TALK_RUNTIME_LOG_DIR"] = _ORIGINAL_RUNTIME_LOG_DIR


if __name__ == "__main__":
    unittest.main()
