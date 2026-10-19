"""接单轮询证据从真实持久记录到 human-only JSONL 下载的联合测试。

使用隔离 SQLite、假 Key、真实 ASGI TestClient、临时诊断根与假 TALK 客户端；
不连接真实服务、不读取生产日志/配置、不调用模型。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

_OWN_ROOT = Path(tempfile.mkdtemp(prefix="queue-poll-export-"))
_ORIGINAL_RUNTIME_LOG_DIR = os.environ.get("TALK_RUNTIME_LOG_DIR")
os.environ["TALK_RUNTIME_LOG_DIR"] = str(_OWN_ROOT / "runtime-logs")

import server.db as db  # noqa: E402

_ORIGINAL_LOG_PATH = db.LOG_PATH
_ORIGINAL_DB_ENGINE = db.engine
_ORIGINAL_STORAGE_DIR = db.STORAGE_DIR

db.LOG_PATH = _OWN_ROOT / "talk.log"
db.STORAGE_DIR = _OWN_ROOT / "storage"
db.engine = create_engine(
    "sqlite:///" + str(_OWN_ROOT / "import.db"),
    echo=False,
    connect_args={"check_same_thread": False},
)

import server.main as main  # noqa: E402
from bridges import cli_bridge  # noqa: E402
from bridges import queue_poll_diagnostics as qpd  # noqa: E402
from bridges import runtime_diagnostics as runtime_diag  # noqa: E402
from server.models import Member, Project, ProjectRole  # noqa: E402
from server.routes.runtime_diagnostics import (  # noqa: E402
    get_runtime_diagnostics_provider,
)
from server.runtime_diagnostics_export import (  # noqa: E402
    build_export,
    parse_export_time,
)
from server.runtime_diagnostics_query import ScanLimits, Source  # noqa: E402
from server.runtime_diagnostics_sources import (  # noqa: E402
    CursorCodec,
    RuntimeDiagnosticsProvider,
)

_ORIGINAL_MAIN_ENGINE = main.engine
_ORIGINAL_MAIN_STORAGE = getattr(main, "STORAGE_DIR", None)

HUMAN_KEY = "FAKE_QUEUE_POLL_HUMAN_KEY"
AGENT_KEY = "FAKE_QUEUE_POLL_AGENT_KEY"
PROJECT = "prj_qp_export"
MEMBER = "agent:qp-export"
NOW = datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc)
SINCE = "2026-10-18T00:00:00Z"
UNTIL = "2026-10-20T00:00:00Z"
EXPECTED_KEYS = {
    "poll_seq",
    "state",
    "started_at",
    "finished_at",
    "duration_ms",
    "last_success_at",
    "last_failure_at",
    "failure_streak_started_at",
    "consecutive_failures",
    "recovered_failures",
    "error_log_id",
    "interval_seconds",
}


class _Clock:
    def __call__(self) -> datetime:
        return NOW


def _point(log_id: str, *, recorded_at: str, **overrides) -> dict:
    record = {
        "schema": "talk-runtime-diagnostics-1",
        "log_id": log_id,
        "recorded_at": recorded_at,
        "event": "queue_poll_snapshot",
        "severity": "info",
        "phase": "queue",
        "stage": "queue_poll",
        "project_id": PROJECT,
        "member_id": MEMBER,
        "instance_id": "ins_qp_export_1",
        "launch_id": "launch-qp-export-1",
        "pid": 123456,
        "runtime": "dsh",
        "task_id": None,
        "message_id": None,
        "returncode": None,
        "timeout": None,
        "cancel_category": None,
        "budgets": {"task_poll_interval_seconds": 2},
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


def _queue_payload(
    *,
    seq: int = 1,
    state: str = "started",
    started_at: str = "2026-10-18T10:00:00+08:00",
    finished_at: str | None = None,
    duration_ms: float | None = None,
    last_success_at: str | None = None,
    last_failure_at: str | None = None,
    failure_streak_started_at: str | None = None,
    consecutive_failures: int = 0,
    recovered_failures: int = 0,
    error_log_id: str | None = None,
    interval_seconds: float = 30,
) -> dict:
    return {
        "poll_seq": seq,
        "state": state,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "failure_streak_started_at": failure_streak_started_at,
        "consecutive_failures": consecutive_failures,
        "recovered_failures": recovered_failures,
        "error_log_id": error_log_id,
        "interval_seconds": interval_seconds,
    }


def _write_records(root: Path, records: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "events-00001.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _parse_ndjson(body: bytes) -> tuple[dict, list[dict]]:
    lines = body.splitlines()
    if not lines:
        raise AssertionError("empty NDJSON body")
    meta = json.loads(lines[0])
    events = [json.loads(line) for line in lines[1:]]
    if meta.get("record_count") != len(events):
        raise AssertionError("meta record_count does not match event lines")
    return meta, events


class QueuePollExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_logging_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        self.temp = Path(tempfile.mkdtemp(prefix="queue-poll-export-case-"))
        self._old_engine = db.engine
        self._old_main_engine = main.engine
        self._old_storage = db.STORAGE_DIR
        self._old_main_storage = getattr(main, "STORAGE_DIR", None)
        self.engine = create_engine(
            "sqlite:///" + str(self.temp / "talk.db"),
            echo=False,
            connect_args={"check_same_thread": False},
        )
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
        main.app.dependency_overrides[get_runtime_diagnostics_provider] = (
            lambda: self.provider
        )

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
            session.add(
                Member(
                    id="human:qp-export",
                    kind="human",
                    display_name="QP Export Human",
                    api_key=HUMAN_KEY,
                )
            )
            session.add(
                Member(
                    id="agent:qp-export",
                    kind="agent",
                    display_name="QP Export Agent",
                    api_key=AGENT_KEY,
                )
            )
            session.add(
                Project(
                    project_id=PROJECT,
                    display_name="QP Export Project",
                    maintainer_member_id="human:qp-export",
                )
            )
            session.add(
                ProjectRole(
                    project_id=PROJECT,
                    member_id=MEMBER,
                    role_name="qp-export",
                    created_by="human:qp-export",
                )
            )
            session.commit()

    def _provider(self) -> RuntimeDiagnosticsProvider:
        config = {
            "runtime_diagnostics": {
                "sources": [
                    {"project_id": PROJECT, "member_id": MEMBER, "root": str(self.root)}
                ]
            }
        }
        return RuntimeDiagnosticsProvider.from_config(
            config,
            scan_limits=ScanLimits(),
            cursor_codec=CursorCodec(clock=_Clock(), ttl_seconds=600),
            clock=_Clock(),
        )

    def _client(self) -> TestClient:
        return TestClient(main.app)

    def _headers(self, key: str = HUMAN_KEY) -> dict[str, str]:
        return {"X-API-Key": key}

    def _url(self) -> str:
        return f"/api/projects/{PROJECT}/roles/{MEMBER}/runtime-logs/export"

    def _query(self) -> dict[str, str]:
        return {"since": SINCE, "until": UNTIL}

    def _export(self, client: TestClient):
        return client.get(self._url(), params=self._query(), headers=self._headers())

    def test_old_records_have_null_and_valid_pair_projects_strictly(self) -> None:
        started = _queue_payload(seq=7)
        finished = _queue_payload(
            seq=7,
            state="succeeded",
            started_at="2026-10-18T10:00:00+08:00",
            finished_at="2026-10-18T10:00:01+08:00",
            duration_ms=1000,
            last_success_at="2026-10-18T10:00:01+08:00",
        )
        records = [
            _point(
                "rtd-qp-valid-000001",
                recorded_at="2026-10-18T10:00:00Z",
                extra={
                    "queue_poll": started,
                    "argv": ["PRIVATE ARGV"],
                    "prompt": "PRIVATE PROMPT",
                    "source_file": "C:\\private\\events.jsonl",
                },
            ),
            _point(
                "rtd-qp-valid-000002",
                recorded_at="2026-10-18T10:00:01Z",
                extra={"queue_poll": finished},
            ),
            _point(
                "rtd-qp-old-000001",
                recorded_at="2026-10-18T10:00:02Z",
                event="queue_started",
                stage="queue_worker",
            ),
        ]
        _write_records(self.root, records)
        with self._client() as client:
            response = self._export(client)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"].split(";")[0], "application/x-ndjson"
        )
        text = response.content.decode("utf-8")
        for forbidden in (
            "PRIVATE ARGV",
            "PRIVATE PROMPT",
            "TOP LEVEL MESSAGE IS NOT EXPORTED",
            "C:\\private",
            "source_file",
            "argv",
        ):
            self.assertNotIn(forbidden, text)
        meta, events = _parse_ndjson(response.content)
        self.assertTrue(meta["complete"])
        self.assertEqual(meta["reasons"], [])
        self.assertEqual(len(events), 3)
        first, second, legacy = events
        self.assertEqual(set(first["queue_poll"]), EXPECTED_KEYS)
        self.assertEqual(first["queue_poll"]["started_at"], "2026-10-18T02:00:00Z")
        self.assertIsNone(first["queue_poll"]["finished_at"])
        self.assertEqual(second["queue_poll"]["finished_at"], "2026-10-18T02:00:01Z")
        self.assertEqual(second["queue_poll"]["duration_ms"], 1000)
        self.assertEqual(second["queue_poll"]["last_success_at"], "2026-10-18T02:00:01Z")
        self.assertIsNone(legacy["queue_poll"])
        self.assertEqual(legacy["event"], "queue_started")
        self.assertNotIn("extra", first)

    def test_poll_provenance_and_completion_timestamps(self) -> None:
        succeeded = _queue_payload(
            state="succeeded", finished_at="2026-10-18T10:00:01Z",
            duration_ms=1000, last_success_at="2026-10-18T10:00:01Z",
        )
        cases = [
            ({"interval_seconds": 99}, {}),
            ({}, {"event": "task_cli_finished"}),
            ({}, {"phase": "task"}),
            ({"last_success_at": "2026-10-18T09:00:00Z"}, {}),
            ({"state": "failed", "last_success_at": None,
              "last_failure_at": "2026-10-18T09:00:00Z",
              "failure_streak_started_at": "2026-10-18T09:00:00Z",
              "consecutive_failures": 1}, {}),
        ]
        for index, (fields, record_fields) in enumerate(cases):
            with self.subTest(index=index):
                _write_records(self.root, [
                    _point("rtd-qp-provenance-bad", recorded_at="2026-10-18T10:00:01Z",
                           extra={"queue_poll": {**succeeded, **fields}}, **record_fields),
                    _point("rtd-qp-provenance-old", recorded_at="2026-10-18T10:00:02Z",
                           event="queue_started"),
                ])
                with self._client() as client:
                    response = self._export(client)
                self.assertEqual(response.status_code, 200)
                meta, events = _parse_ndjson(response.content)
                self.assertFalse(meta["complete"])
                self.assertIn("projection_failed", meta["reasons"])
                self.assertEqual([e["log_id"] for e in events], ["rtd-qp-provenance-old"])

    def test_recovery_event_projects_once_with_ended_streak(self) -> None:
        recovery = _queue_payload(
            seq=3,
            state="succeeded",
            started_at="2026-10-18T10:00:02Z",
            finished_at="2026-10-18T10:00:03Z",
            duration_ms=1000,
            last_success_at="2026-10-18T10:00:03Z",
            last_failure_at="2026-10-18T10:00:01Z",
            failure_streak_started_at="2026-10-18T10:00:00Z",
            consecutive_failures=0,
            recovered_failures=2,
            error_log_id="rtd-qp-valid-000042",
        )
        _write_records(
            self.root,
            [
                _point(
                    "rtd-qp-recovery-0001",
                    recorded_at="2026-10-18T10:00:03Z",
                    event="queue_poll_recovered",
                    extra={"queue_poll": recovery},
                )
            ],
        )
        with self._client() as client:
            response = self._export(client)
        self.assertEqual(response.status_code, 200)
        meta, events = _parse_ndjson(response.content)
        self.assertTrue(meta["complete"])
        payload = events[0]["queue_poll"]
        self.assertEqual(payload["state"], "succeeded")
        self.assertEqual(payload["recovered_failures"], 2)
        self.assertEqual(payload["failure_streak_started_at"], "2026-10-18T10:00:00Z")
        self.assertEqual(payload["last_failure_at"], "2026-10-18T10:00:01Z")

    def test_invalid_queue_poll_records_are_projection_failures(self) -> None:
        valid = _queue_payload(seq=1)
        valid_finished = _queue_payload(
            seq=1,
            state="succeeded",
            finished_at="2026-10-18T10:00:01Z",
            duration_ms=1000,
            last_success_at="2026-10-18T10:00:01Z",
        )
        variants: list[tuple[str, str, dict, str]] = []

        def add(name: str, event: str, payload: dict, marker: str = "MALICIOUS") -> None:
            variants.append((name, event, payload, marker))

        unknown_key = dict(valid_finished)
        unknown_key["extra_key"] = marker = "PRIVATE_QUEUE_POLL_EXTRA"
        add("unknown_key", "queue_poll_snapshot", unknown_key, marker)
        missing = dict(valid_finished)
        missing.pop("state")
        add("missing_key", "queue_poll_snapshot", missing)
        wrong_bool = dict(valid_finished)
        wrong_bool["poll_seq"] = True
        add("bool_seq", "queue_poll_snapshot", wrong_bool)
        add("zero_seq", "queue_poll_snapshot", {**valid_finished, "poll_seq": 0})
        add("unknown_state", "queue_poll_snapshot", {**valid_finished, "state": "mystery"})
        add(
            "naive_time",
            "queue_poll_snapshot",
            {**valid_finished, "started_at": "2026-10-18T10:00:00"},
        )
        add(
            "started_with_finished",
            "queue_poll_snapshot",
            {
                **valid,
                "finished_at": "2026-10-18T10:00:01Z",
                "duration_ms": 1000,
            },
        )
        add(
            "started_streak_without_last_failure",
            "queue_poll_snapshot",
            {
                **valid,
                "consecutive_failures": 1,
                "failure_streak_started_at": "2026-10-18T10:00:00Z",
            },
        )
        add(
            "succeeded_without_duration",
            "queue_poll_snapshot",
            {**valid_finished, "duration_ms": None},
        )
        add(
            "failed_without_count",
            "queue_poll_snapshot",
            {
                **valid_finished,
                "state": "failed",
                "failure_streak_started_at": "2026-10-18T10:00:00Z",
                "last_failure_at": "2026-10-18T10:00:01Z",
                "consecutive_failures": 0,
            },
        )
        add(
            "recovered_flag_on_snapshot",
            "queue_poll_snapshot",
            {**valid_finished, "recovered_failures": 1},
        )
        add(
            "recovery_missing_last_failure",
            "queue_poll_recovered",
            {
                **valid_finished,
                "recovered_failures": 2,
                "failure_streak_started_at": "2026-10-18T10:00:00Z",
            },
        )
        add(
            "free_text_log_ref",
            "queue_poll_snapshot",
            {**valid_finished, "error_log_id": "private exception text"},
        )
        add(
            "bool_interval",
            "queue_poll_snapshot",
            {**valid_finished, "interval_seconds": True},
        )
        add(
            "nan_duration",
            "queue_poll_snapshot",
            {**valid_finished, "duration_ms": float("nan")},
        )
        add(
            "infinity_duration",
            "queue_poll_snapshot",
            {**valid_finished, "duration_ms": float("inf")},
        )
        add(
            "bool_consecutive",
            "queue_poll_snapshot",
            {**valid_finished, "consecutive_failures": True},
        )
        add(
            "recovery_wrong_state",
            "queue_poll_recovered",
            {
                **valid_finished,
                "state": "failed",
                "recovered_failures": 2,
                "failure_streak_started_at": "2026-10-18T10:00:00Z",
                "last_failure_at": "2026-10-18T10:00:01Z",
                "consecutive_failures": 1,
            },
        )

        records = [
            _point(
                "rtd-qp-good-000001",
                recorded_at="2026-10-18T10:00:00Z",
                extra={"queue_poll": valid},
            )
        ]
        for index, (name, event, payload, marker) in enumerate(variants, start=1):
            records.append(
                _point(
                    f"rtd-qp-bad-{index:06d}",
                    recorded_at=f"2026-10-18T10:00:{index:02d}Z",
                    event=event,
                    severity="error",
                    extra={"queue_poll": payload, "note": marker},
                )
            )
        _write_records(self.root, records)
        with self._client() as client:
            response = self._export(client)
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8")
        self.assertNotIn("PRIVATE_QUEUE_POLL_EXTRA", text)
        self.assertNotIn("private exception text", text)
        self.assertNotIn("MALICIOUS", text)
        meta, events = _parse_ndjson(response.content)
        self.assertEqual(meta["record_count"], 1)
        self.assertEqual(len(events), 1)
        self.assertFalse(meta["complete"])
        self.assertIn("projection_failed", meta["reasons"])
        self.assertEqual(events[0]["log_id"], "rtd-qp-good-000001")

    def test_worker_persisted_records_reach_authenticated_download(self) -> None:
        class Clock:
            def __init__(self) -> None:
                self.wall = NOW
                self.monotonic = 0.0

            def now(self):
                return self.wall

            def mono(self):
                return self.monotonic

            def advance(self, seconds: float) -> None:
                self.wall = self.wall + timedelta(seconds=seconds)
                self.monotonic += seconds

        class Client:
            def __init__(self) -> None:
                self.calls = 0

            async def requeue_expired_tasks(self):
                return []

            async def list_tasks(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    clock.advance(1)
                    raise RuntimeError("query failure for export")
                if self.calls == 2:
                    clock.advance(1)
                    return []
                raise asyncio.CancelledError

        clock = Clock()
        writer = runtime_diag.RuntimeDiagnostics(
            member_id=MEMBER,
            instance_id="ins_qp_export_worker",
            root=self.root,
            project_id=PROJECT,
            launch_id="launch-qp-export-worker",
            runtime="dsh",
            clock=clock.now,
        )
        args = SimpleNamespace(
            command="fake",
            task_command="fake",
            task_preflight_command="fake",
            timeout=5,
            max_reply_chars=300,
            runtime="dsh",
            bridge_label="fake",
            prompt_transport="argv",
            decision_tier=None,
            task_lease_seconds=30,
            task_heartbeat_interval=1,
            task_poll_interval=0,
            task_preflight_max_attempts=2,
        )

        async def scenario():
            try:
                await cli_bridge.run_task_queue_worker(
                    client=Client(),
                    member_id=MEMBER,
                    workdir=Path.cwd(),
                    instance_id="ins_qp_export_worker",
                    args=args,
                    run_lock=asyncio.Lock(),
                    report_status=None,
                    diagnostics=writer,
                )
            except asyncio.CancelledError:
                pass

        with patch.object(qpd, "utc_now", clock.now), patch.object(
            qpd, "monotonic_now", clock.mono
        ):
            asyncio.run(scenario())

        with self._client() as client:
            response = self._export(client)
            no_key = client.get(self._url(), params=self._query())
            wrong_key = client.get(
                self._url(), params=self._query(), headers=self._headers("WRONG")
            )
            agent = client.get(
                self._url(), params=self._query(), headers=self._headers(AGENT_KEY)
            )
            missing_project = client.get(
                "/api/projects/prj_missing/roles/" + MEMBER + "/runtime-logs/export",
                params=self._query(),
                headers=self._headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(no_key.status_code, 401)
        self.assertEqual(wrong_key.status_code, 401)
        self.assertEqual(agent.status_code, 403)
        self.assertEqual(agent.json()["detail"], "log_read_forbidden")
        self.assertEqual(missing_project.status_code, 404)
        meta, events = _parse_ndjson(response.content)
        self.assertTrue(meta["complete"])
        self.assertEqual(meta["reasons"], [])
        self.assertEqual(meta["scope"], {"project_id": PROJECT, "member_id": MEMBER})
        poll_events = [event for event in events if event["queue_poll"] is not None]
        self.assertGreaterEqual(len(poll_events), 2)
        failed = [
            event
            for event in poll_events
            if event["queue_poll"]["state"] == "failed"
        ]
        recovered = [event for event in events if event["event"] == "queue_poll_recovered"]
        exceptions = [event for event in events if event["event"] == "queue_worker_exception"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(
            failed[0]["queue_poll"]["error_log_id"], exceptions[0]["log_id"]
        )
        self.assertEqual(recovered[0]["queue_poll"]["recovered_failures"], 1)
        self.assertEqual(
            recovered[0]["queue_poll"]["error_log_id"], exceptions[0]["log_id"]
        )
        for event in events:
            if event["event"] in {"queue_started", "queue_worker_exception", "queue_stopped"}:
                self.assertIsNone(event["queue_poll"])
            self.assertNotIn("extra", event)

    def test_budget_and_invalid_query_contracts_unchanged(self) -> None:
        records = []
        for index in range(6):
            records.append(
                _point(
                    f"rtd-qp-limit-{index:06d}",
                    recorded_at=f"2026-10-18T10:00:0{index}Z",
                    extra={"queue_poll": _queue_payload(seq=index + 1)},
                )
            )
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
        self.assertIn("record_limit", meta["reasons"])
        self.assertFalse(meta["complete"])
        byte_limited = build_export(
            Source(PROJECT, MEMBER, self.root),
            project_id=PROJECT,
            member_id=MEMBER,
            since=parse_export_time(SINCE),
            until=parse_export_time(UNTIL),
            generated_at=NOW,
            max_bytes=1500,
        )
        byte_meta, byte_events = _parse_ndjson(byte_limited)
        self.assertLess(len(byte_events), 6)
        self.assertEqual(byte_meta["record_count"], len(byte_events))
        self.assertIn("byte_limit", byte_meta["reasons"])
        self.assertTrue(byte_meta["truncated"])
        self.assertFalse(byte_meta["complete"])
        with self._client() as client:
            cases = [
                {},
                {"since": SINCE},
                {"since": SINCE, "until": UNTIL, "limit": "20"},
                {"since": "2026-10-18T00:00:00", "until": UNTIL},
                {"since": "2026-10-19T00:00:00Z", "until": "2026-10-18T00:00:00Z"},
                {"since": "2026-08-01T00:00:00Z", "until": UNTIL},
            ]
            for case in cases:
                with self.subTest(case=case):
                    response = client.get(
                        self._url(), params=case, headers=self._headers()
                    )
                    self.assertEqual(response.status_code, 422)


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
    shutil.rmtree(_OWN_ROOT, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
