"""Isolated scanner, pagination, degradation and projection tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import server.runtime_diagnostics_query as query
from server.runtime_diagnostics_sources import (
    CursorCodec,
    RuntimeDiagnosticsProvider,
)

_OWN_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".tmp"
    / "runtime-log-view-v1"
    / "deepseek-backend"
    / "test-roots"
)
_NOW = datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc)


def _make_directory_link(link: Path, target: Path) -> str:
    """Create a symlink or, on Windows, a real junction (reparse point)."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        if os.name != "nt":
            raise
    result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise OSError("cannot create junction")
    return "junction"


class _Clock:
    def __init__(self, value: datetime = _NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _record(
    log_id: str,
    *,
    project_id: str = "prj_fake_a",
    member_id: str = "agent:fake-a",
    event: str = "task_claim_failed",
    severity: str = "error",
    recorded_at: str = "2026-10-18T19:00:00+00:00",
    stage: str | None = "task_claim",
    task_id: int | None = 273,
    instance_id: str | None = "ins_fake_current",
    launch_id: str | None = "launch-fake-a",
    exception: dict | None = None,
    **overrides,
) -> dict:
    record = {
        "schema": "talk-runtime-diagnostics-1",
        "log_id": log_id,
        "recorded_at": recorded_at,
        "event": event,
        "severity": severity,
        "phase": "claim",
        "stage": stage,
        "project_id": project_id,
        "member_id": member_id,
        "instance_id": instance_id,
        "launch_id": launch_id,
        "pid": 424242,
        "runtime": "dsh",
        "task_id": task_id,
        "message_id": 777,
        "returncode": None,
        "timeout": False,
        "cancel_category": None,
        "budgets": {
            "cli_timeout_seconds": 21600,
            "http_timeout_seconds": 15,
            "task_lease_seconds": 120,
            "task_heartbeat_interval_seconds": 5,
            "managed_heartbeat_interval_seconds": 30,
            "task_poll_interval_seconds": 3,
            "mcp_wait_seconds": 50,
        },
        "integrity": {
            "redacted": True,
            "redaction_kinds": ["known_value", "secret_field"],
            "truncated": False,
            "truncated_fields": [],
            "write_complete": True,
        },
        "run_id": "20261018T190000000000Z-424242-deadbeef",
        "segment_file": "events-00001.jsonl",
    }
    if exception is None:
        exception = {
            "relation": "primary",
            "type": "TaskClaimError",
            "message": "claim failed",
            "str_empty": False,
            "message_error": False,
            "frames": [
                {
                    "file": "C:\\private\\cli_bridge.py",
                    "line": 3214,
                    "function": "handle_queued_task",
                    "source": "SECRET SOURCE LINE",
                }
            ],
            "frames_total": 1,
            "frames_omitted": 0,
            "cause_chain": [],
            "chain_depth": 0,
            "chain_truncated": False,
            "chain_cycle": False,
            "has_explicit_cause": False,
            "context_present": False,
            "context_suppressed": False,
        }
    record["exception"] = exception
    record.update(overrides)
    return record


class RuntimeQueryBase(unittest.TestCase):
    def setUp(self) -> None:
        _OWN_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = Path(
            tempfile.mkdtemp(prefix="query-", dir=str(_OWN_ROOT))
        )
        self.root = self.temp / "logs"
        self.root.mkdir()
        self.clock = _Clock()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def write_records(self, records: list[dict], name: str = "events-00001.jsonl") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def provider(
        self,
        *,
        root: Path | None = None,
        limits: query.ScanLimits | None = None,
        codec: CursorCodec | None = None,
        clock: _Clock | None = None,
    ) -> RuntimeDiagnosticsProvider:
        active_clock = clock or self.clock
        codec = codec or CursorCodec(clock=active_clock, ttl_seconds=600)
        config = {
            "runtime_diagnostics": {
                "sources": [
                    {
                        "project_id": "prj_fake_a",
                        "member_id": "agent:fake-a",
                        "root": str(root or self.root),
                    }
                ]
            }
        }
        return RuntimeDiagnosticsProvider.from_config(
            config,
            scan_limits=limits,
            cursor_codec=codec,
            clock=active_clock,
        )

    def spec(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        severity: tuple[str, ...] | None = ("error", "warning"),
        limit: int = 20,
        cursor: str | None = None,
        provided: frozenset[str] | None = None,
        ref: str | None = None,
        **filters,
    ) -> query.QuerySpec:
        return query.QuerySpec(
            ref=ref,
            since=since,
            until=until,
            instance_id=filters.get("instance_id"),
            launch_id=filters.get("launch_id"),
            task_id=filters.get("task_id"),
            event=filters.get("event"),
            stage=filters.get("stage"),
            severity=severity,
            limit=limit,
            cursor=cursor,
            provided=(
                provided
                if provided is not None
                else frozenset({"since", "until", "severity"})
            ),
        )

    def assertCode(self, code: str, status_code: int, call) -> None:
        with self.assertRaises(query.RuntimeDiagnosticsError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.status_code, status_code)


class ProjectionTests(RuntimeQueryBase):
    def test_summary_whitelist_scrubs_paths_and_internal_fields(self) -> None:
        exception = _record("rtd-0000000001")["exception"]
        exception["type"] = "C:\\private\\TaskClaimError"
        exception["message"] = (
            "open C:\\private\\app.py and \\\\server\\share\\x.py "
            "and /srv/app/main.py failed; api_key=FAKE_SECRET"
        )
        exception["frames"] = [
            {
                "file": "C:\\private\\app.py",
                "line": 12,
                "function": "C:\\private\\func",
                "source": "SECRET SOURCE",
            },
            {
                "file": "\\\\server\\share\\mod.py",
                "line": 3,
                "function": "run",
                "source": "SECRET SOURCE",
            },
            {
                "file": "/srv/app/lib.py",
                "line": 4,
                "function": "load",
                "source": "SECRET SOURCE",
            },
        ]
        record = _record(
            "rtd-0000000001",
            exception=exception,
            message="TOP LEVEL SECRET",
            extra={"argv": ["FAKE_ARG"], "env": {"KEY": "FAKE_ENV"}},
        )
        self.write_records([record])
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(since=_NOW - timedelta(hours=24), until=_NOW, limit=20),
        )
        self.assertEqual(len(page.records), 1)
        body = json.dumps(page.model_dump(by_alias=True), ensure_ascii=False)
        summary = page.records[0]
        self.assertIsNotNone(summary.exception)
        self.assertIn("[PATH]", summary.exception.message_preview)
        self.assertNotIn("C:\\", body)
        self.assertNotIn("\\\\server", body)
        self.assertNotIn("/srv", body)
        self.assertNotIn("SECRET SOURCE", body)
        self.assertNotIn("TOP LEVEL SECRET", body)
        self.assertNotIn("FAKE_ARG", body)
        self.assertNotIn("FAKE_ENV", body)
        self.assertNotIn("pid", body)
        self.assertNotIn("run_id", body)
        self.assertNotIn("segment_file", body)
        self.assertNotIn("root", body)
        summary_keys = set(summary.model_dump(by_alias=True))
        self.assertEqual(
            summary_keys,
            {
                "log_id",
                "recorded_at",
                "event",
                "severity",
                "stage",
                "project_id",
                "member_id",
                "instance_id",
                "launch_id",
                "task_id",
                "related_log_id",
                "exception",
                "returncode",
                "timeout",
                "cancel_category",
                "budgets",
                "integrity",
            },
        )

    def test_detail_has_no_source_lines_and_multilevel_causes_are_scrubbed(self) -> None:
        exception = _record("rtd-0000000002")["exception"]
        exception["message"] = "primary at /mnt/data/x.py"
        exception["frames"] = [
            {
                "file": "C:\\private\\cli_bridge.py",
                "line": 3214,
                "function": "C:\\private\\run",
                "source": "SOURCE MUST NOT LEAK",
            }
        ]
        exception["cause_chain"] = [
            {
                "relation": "explicit_cause",
                "type": "OSError",
                "message": "cause at \\\\server\\share\\y.py",
                "frames_total": 1,
                "frames_omitted": 0,
                "frames": [
                    {
                        "file": "/srv/app/fake.py",
                        "line": 9,
                        "function": "read",
                        "source": "CAUSE SOURCE",
                    }
                ],
            },
            {
                "relation": "implicit_context",
                "type": "RuntimeError",
                "message": "third at /data/third.py",
                "frames_total": 0,
                "frames_omitted": 0,
                "frames": [],
            },
        ]
        exception["chain_depth"] = 2
        self.write_records(
            [_record("rtd-0000000002", exception=exception)]
        )
        provider = self.provider()
        detail = provider.get_detail(
            "prj_fake_a", "agent:fake-a", "rtd-0000000002"
        )
        record = detail.record
        self.assertIsNotNone(record.exception)
        self.assertEqual(record.exception.frames[0].file_name, "cli_bridge.py")
        self.assertEqual(record.exception.frames[0].line, 3214)
        self.assertEqual(record.exception.frames[0].function, "[PATH]")
        self.assertFalse(hasattr(record.exception.frames[0], "source"))
        self.assertEqual(len(record.exception.cause_chain), 2)
        self.assertEqual(record.exception.cause_chain[0].frames[0].file_name, "fake.py")
        self.assertIn("[PATH]", record.exception.cause_chain[0].message)
        record_keys = set(record.model_dump(by_alias=True))
        self.assertEqual(
            record_keys,
            {
                "log_id",
                "recorded_at",
                "event",
                "severity",
                "stage",
                "project_id",
                "member_id",
                "instance_id",
                "launch_id",
                "task_id",
                "related_log_id",
                "exception",
                "returncode",
                "timeout",
                "cancel_category",
                "budgets",
                "integrity",
            },
        )
        exception_keys = set(record.exception.model_dump(by_alias=True))
        self.assertEqual(
            exception_keys,
            {
                "type",
                "message",
                "str_empty",
                "message_error",
                "frames_total",
                "frames_omitted",
                "frames",
                "cause_chain",
                "chain_depth",
                "chain_truncated",
                "chain_cycle",
                "has_explicit_cause",
                "context_present",
                "context_suppressed",
            },
        )
        body = json.dumps(detail.model_dump(by_alias=True), ensure_ascii=False)
        for forbidden in (
            "C:\\",
            "\\\\server",
            "/srv",
            "/mnt",
            "/data",
            "SOURCE MUST NOT LEAK",
            "CAUSE SOURCE",
            '"source"',
        ):
            self.assertNotIn(forbidden, body)

    def test_info_detail_exception_is_null(self) -> None:
        record = _record(
            "rtd-0000000003",
            event="queue_started",
            severity="info",
            stage="queue_worker",
        )
        record["exception"] = None
        self.write_records([record])
        provider = self.provider()
        detail = provider.get_detail(
            "prj_fake_a", "agent:fake-a", "rtd-0000000003"
        )
        self.assertIsNone(detail.record.exception)
        self.assertEqual(detail.record.severity, "info")
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(
                since=_NOW - timedelta(hours=24),
                until=_NOW,
                severity=("info",),
                event="queue_started",
            ),
        )
        self.assertEqual(len(page.records), 1)

    def test_unsafe_file_name_causes_projection_failure(self) -> None:
        exception = _record("rtd-0000000004")["exception"]
        exception["frames"] = [
            {"file": "C:relative.py", "line": 1, "function": "x", "source": ""}
        ]
        self.write_records([_record("rtd-0000000004", exception=exception)])
        provider = self.provider()
        self.assertCode(
            "diagnostics_projection_failed",
            503,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000004"
            ),
        )


class FilterAndRefTests(RuntimeQueryBase):
    def setUp(self) -> None:
        super().setUp()
        self.write_records(
            [
                _record(
                    "rtd-0000000011",
                    recorded_at="2026-10-18T19:00:00+00:00",
                    event="task_claim_failed",
                    severity="error",
                    task_id=273,
                    instance_id="ins_current",
                ),
                _record(
                    "rtd-0000000012",
                    recorded_at="2026-10-18T18:00:00+00:00",
                    event="managed_heartbeat_failure",
                    severity="warning",
                    task_id=None,
                    instance_id="ins_old",
                ),
                _record(
                    "rtd-0000000013",
                    recorded_at="2026-10-18T17:00:00+00:00",
                    event="queue_started",
                    severity="info",
                    stage="queue_worker",
                    task_id=None,
                    instance_id="ins_current",
                ),
                _record(
                    "rtd-0000000014",
                    recorded_at="2026-09-01T00:00:00+00:00",
                    event="queue_started",
                    severity="info",
                    stage="queue_worker",
                    task_id=None,
                ),
                _record(
                    "rtd-0000000015",
                    project_id="prj_fake_b",
                    recorded_at="2026-10-18T19:30:00+00:00",
                    event="task_claim_failed",
                ),
                _record(
                    "rtd-0000000016",
                    project_id=None,
                    recorded_at="2026-10-18T19:35:00+00:00",
                ),
                _record(
                    "rtd-0000000017",
                    member_id="unknown",
                    recorded_at="2026-10-18T19:36:00+00:00",
                    extra={"member_id": "agent:fake-a"},
                ),
            ]
        )

    def test_default_window_and_severity(self) -> None:
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(since=_NOW - timedelta(hours=24), until=_NOW),
        )
        self.assertEqual(
            [record.log_id for record in page.records],
            ["rtd-0000000011", "rtd-0000000012"],
        )
        self.assertEqual(page.query.severity, ["error", "warning"])
        self.assertTrue(page.scan.complete)
        self.assertFalse(page.page.has_more)

    def test_exact_ref_ignores_default_time_and_severity(self) -> None:
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(ref="rtd-0000000014", since=None, until=None, severity=None),
        )
        self.assertEqual([record.log_id for record in page.records], ["rtd-0000000014"])
        self.assertIsNone(page.query.since)
        self.assertIsNone(page.query.until)
        self.assertIsNone(page.query.severity)
        self.assertEqual(page.query.ref, "rtd-0000000014")
        self.assertIsNone(page.page.next_cursor)

    def test_filters_are_and_and_exact(self) -> None:
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(
                since=_NOW - timedelta(hours=24),
                until=_NOW,
                instance_id="ins_old",
                event="managed_heartbeat_failure",
                stage=None,
                severity=("warning",),
            ),
        )
        self.assertEqual([record.log_id for record in page.records], ["rtd-0000000012"])
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(
                since=_NOW - timedelta(hours=24),
                until=_NOW,
                task_id=273,
                severity=("error",),
            ),
        )
        self.assertEqual([record.log_id for record in page.records], ["rtd-0000000011"])

    def test_cross_scope_record_is_never_returned(self) -> None:
        provider = self.provider()
        self.assertCode(
            "log_not_found",
            404,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000015"
            ),
        )
        self.assertCode(
            "log_not_found",
            404,
            lambda: provider.list_logs(
                "prj_fake_a",
                "agent:fake-a",
                self.spec(ref="rtd-0000000015", since=None, until=None, severity=None),
            ),
        )

    def test_missing_project_and_manager_unknown_are_not_inferred(self) -> None:
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(since=_NOW - timedelta(hours=24), until=_NOW),
        )
        ids = {record.log_id for record in page.records}
        self.assertNotIn("rtd-0000000016", ids)
        self.assertNotIn("rtd-0000000017", ids)
        self.assertCode(
            "log_not_found",
            404,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000016"
            ),
        )
        self.assertCode(
            "log_not_found",
            404,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000017"
            ),
        )

    def test_duplicate_ref_is_conflict(self) -> None:
        duplicate = _record(
            "rtd-0000000011",
            recorded_at="2026-10-18T19:00:00+00:00",
            exception={
                **_record("rtd-0000000011")["exception"],
                "message": "different body",
            },
        )
        with (self.root / "events-00001.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(duplicate) + "\n")
        provider = self.provider()
        self.assertCode(
            "log_ref_conflict",
            409,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000011"
            ),
        )

    def test_incomplete_scan_does_not_masquerade_as_not_found(self) -> None:
        with (self.root / "events-00001.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("not-json\n")
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(since=_NOW - timedelta(hours=24), until=_NOW),
        )
        self.assertFalse(page.scan.complete)
        self.assertEqual(page.scan.malformed_lines, 1)
        self.assertIsNone(page.page.next_cursor)
        self.assertIn("records_unreadable", page.warnings)
        self.assertCode(
            "diagnostics_scan_incomplete",
            503,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000011"
            ),
        )


class PaginationTests(RuntimeQueryBase):
    def setUp(self) -> None:
        super().setUp()
        self.write_records(
            [
                _record(
                    f"rtd-000000002{i}",
                    recorded_at=f"2026-10-18T1{9 - i}:00:00+00:00",
                )
                for i in range(5)
            ]
        )

    def _page(self, provider: RuntimeDiagnosticsProvider, cursor: str | None = None, limit: int = 2):
        return provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(
                since=_NOW - timedelta(hours=24),
                until=_NOW,
                limit=limit,
                cursor=cursor,
                provided=frozenset(
                    {"since", "until", "severity", "cursor"}
                    if cursor is not None
                    else {"since", "until", "severity"}
                ),
            ),
        )

    def test_three_pages_are_stable_and_complete(self) -> None:
        provider = self.provider()
        page1 = self._page(provider)
        self.assertEqual(len(page1.records), 2)
        self.assertTrue(page1.page.has_more)
        self.assertIsNotNone(page1.page.next_cursor)
        first_query = page1.query
        page2 = self._page(provider, page1.page.next_cursor)
        self.assertEqual(len(page2.records), 2)
        self.assertEqual(page2.query, first_query)
        page3 = self._page(provider, page2.page.next_cursor)
        self.assertEqual(len(page3.records), 1)
        self.assertFalse(page3.page.has_more)
        ids = [record.log_id for page in (page1, page2, page3) for record in page.records]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            ids,
            [
                "rtd-0000000020",
                "rtd-0000000021",
                "rtd-0000000022",
                "rtd-0000000023",
                "rtd-0000000024",
            ],
        )
        for page in (page1, page2, page3):
            self.assertTrue(page.scan.complete)

    def test_tampered_and_mismatched_cursors_are_rejected(self) -> None:
        provider = self.provider()
        page1 = self._page(provider)
        token = page1.page.next_cursor
        assert token is not None
        body, signature = token.split(".")
        tampered = body + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
        self.assertCode(
            "invalid_cursor", 422, lambda: self._page(provider, tampered)
        )
        # Missing replay of the frozen query window is invalid_cursor.
        self.assertCode(
            "invalid_cursor",
            422,
            lambda: provider.list_logs(
                "prj_fake_a",
                "agent:fake-a",
                self.spec(
                    since=None,
                    until=None,
                    severity=("error", "warning"),
                    limit=2,
                    cursor=token,
                    provided=frozenset({"cursor"}),
                ),
            ),
        )
        self.assertCode(
            "invalid_cursor",
            422,
            lambda: self._page(provider, token, limit=3),
        )

    def test_restart_expiry_and_source_revision_are_stale(self) -> None:
        provider = self.provider()
        page1 = self._page(provider)
        token = page1.page.next_cursor
        assert token is not None

        new_generation = self.provider(
            codec=CursorCodec(clock=self.clock, ttl_seconds=600)
        )
        self.assertCode(
            "stale_cursor", 409, lambda: self._page(new_generation, token)
        )

        expired = self.provider()
        self.clock.value = _NOW + timedelta(seconds=601)
        self.assertCode(
            "stale_cursor", 409, lambda: self._page(expired, token)
        )

        self.clock.value = _NOW
        other_root = self.temp / "other-root"
        other_root.mkdir()
        changed = self.provider(root=other_root)
        self.assertCode(
            "stale_cursor", 409, lambda: self._page(changed, token)
        )


class SourceChangeTests(RuntimeQueryBase):
    def test_append_delete_rotate_replace_are_stale(self) -> None:
        for variant in ("append", "delete", "rotate", "replace", "truncate"):
            with self.subTest(variant=variant):
                case_root = self.temp / f"case-{variant}"
                case_root.mkdir()
                original = [
                    _record(
                        f"rtd-000000003{i}",
                        recorded_at=f"2026-10-18T1{9 - i}:00:00+00:00",
                    )
                    for i in range(3)
                ]
                (case_root / "events-00001.jsonl").write_text(
                    "".join(json.dumps(item) + "\n" for item in original),
                    encoding="utf-8",
                )
                case_provider = self.provider(root=case_root)
                page1 = case_provider.list_logs(
                    "prj_fake_a",
                    "agent:fake-a",
                    self.spec(
                        since=_NOW - timedelta(hours=24),
                        until=_NOW,
                        limit=1,
                    ),
                )
                self.assertIsNotNone(page1.page.next_cursor)
                token = page1.page.next_cursor
                assert token is not None
                path = case_root / "events-00001.jsonl"
                if variant == "append":
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write(
                            json.dumps(
                                _record(
                                    "rtd-0000000039",
                                    recorded_at="2026-10-18T19:30:00+00:00",
                                )
                            )
                            + "\n"
                        )
                elif variant == "delete":
                    path.unlink()
                elif variant == "rotate":
                    (case_root / "events-00002.jsonl").write_text(
                        json.dumps(
                            _record(
                                "rtd-0000000038",
                                recorded_at="2026-10-18T19:40:00+00:00",
                            )
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                elif variant == "replace":
                    path.write_text(
                        json.dumps(
                            _record(
                                "rtd-0000000037",
                                recorded_at="2026-10-18T19:45:00+00:00",
                            )
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                else:
                    with path.open("r+b") as stream:
                        stream.truncate(10)
                self.assertCode(
                    "stale_cursor",
                    409,
                    lambda p=case_provider, t=token: p.list_logs(
                        "prj_fake_a",
                        "agent:fake-a",
                        self.spec(
                            since=_NOW - timedelta(hours=24),
                            until=_NOW,
                            limit=1,
                            cursor=t,
                            provided=frozenset(
                                {"since", "until", "severity", "cursor"}
                            ),
                        ),
                    ),
                )

    def test_budget_limits_return_partial_page_without_cursor(self) -> None:
        for index in range(3):
            records = [
                _record(
                    f"rtd-000000004{index}",
                    recorded_at=f"2026-10-18T1{9 - index}:00:00+00:00",
                )
            ]
            (self.root / f"events-0000{index + 1}.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )
        provider = self.provider(limits=query.ScanLimits(max_files=1))
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(since=_NOW - timedelta(hours=24), until=_NOW),
        )
        self.assertFalse(page.scan.complete)
        self.assertTrue(page.scan.truncated)
        self.assertIsNone(page.page.next_cursor)
        self.assertIn("scan_limited", page.warnings)
        self.assertCode(
            "diagnostics_scan_incomplete",
            503,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000040"
            ),
        )

    def test_non_event_files_are_ignored(self) -> None:
        self.write_records([_record("rtd-0000000080")])
        fake = json.dumps(_record("rtd-0000000081", severity="fatal"))
        for name in ("manifest.json", "rotation.jsonl", "retention.jsonl"):
            (self.root / name).write_text(fake + "\n", encoding="utf-8")
        (self.root / "events-x.jsonl").write_text(fake + "\n", encoding="utf-8")
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(
                since=_NOW - timedelta(hours=24),
                until=_NOW,
                severity=("error", "warning"),
            ),
        )
        self.assertTrue(page.scan.complete)
        self.assertEqual([item.log_id for item in page.records], ["rtd-0000000080"])
        self.assertCode(
            "log_not_found",
            404,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000081"
            ),
        )

    def test_empty_complete_scan_is_not_an_error(self) -> None:
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(since=_NOW - timedelta(hours=24), until=_NOW),
        )
        self.assertTrue(page.scan.complete)
        self.assertEqual(page.records, [])
        self.assertIsNone(page.page.next_cursor)
        self.assertEqual(page.warnings, [])
        self.assertCode(
            "log_not_found",
            404,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000999"
            ),
        )

    def test_unreachable_root_is_503_not_not_found(self) -> None:
        provider = self.provider()
        shutil.rmtree(self.root)
        self.assertCode(
            "diagnostics_unavailable",
            503,
            lambda: provider.list_logs(
                "prj_fake_a",
                "agent:fake-a",
                self.spec(since=_NOW - timedelta(hours=24), until=_NOW),
            ),
        )
        self.assertCode(
            "diagnostics_unavailable",
            503,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000001"
            ),
        )

    def test_root_symlink_is_unavailable(self) -> None:
        target = self.temp / "target"
        target.mkdir()
        (target / "events-00001.jsonl").write_text(
            json.dumps(_record("rtd-0000000050")) + "\n", encoding="utf-8"
        )
        link = self.temp / "link-root"
        try:
            _make_directory_link(link, target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"platform cannot create directory link: {type(exc).__name__}")
        provider = self.provider(root=link)
        self.assertCode(
            "diagnostics_unavailable",
            503,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000050"
            ),
        )

    def test_ancestor_junction_is_unavailable(self) -> None:
        outside = self.temp / "outside-ancestor"
        (outside / "sub").mkdir(parents=True)
        (outside / "sub" / "events-00001.jsonl").write_text(
            json.dumps(_record("rtd-0000000055")) + "\n", encoding="utf-8"
        )
        link = self.temp / "ancestor-link"
        try:
            _make_directory_link(link, outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"platform cannot create directory link: {type(exc).__name__}")
        provider = self.provider(root=link / "sub")
        self.assertCode(
            "diagnostics_unavailable",
            503,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000055"
            ),
        )

    def test_nested_symlink_is_skipped_and_marks_incomplete(self) -> None:
        outside = self.temp / "outside"
        outside.mkdir()
        (outside / "events-00001.jsonl").write_text(
            json.dumps(_record("rtd-0000000060", member_id="agent:other")) + "\n",
            encoding="utf-8",
        )
        try:
            _make_directory_link(self.root / "linked", outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"platform cannot create directory link: {type(exc).__name__}")
        (self.root / "events-00001.jsonl").write_text(
            json.dumps(_record("rtd-0000000061")) + "\n", encoding="utf-8"
        )
        provider = self.provider()
        page = provider.list_logs(
            "prj_fake_a",
            "agent:fake-a",
            self.spec(since=_NOW - timedelta(hours=24), until=_NOW),
        )
        self.assertFalse(page.scan.complete)
        self.assertIn("source_entries_skipped", page.warnings)
        self.assertEqual(
            [record.log_id for record in page.records], ["rtd-0000000061"]
        )
        self.assertCode(
            "diagnostics_scan_incomplete",
            503,
            lambda: provider.get_detail(
                "prj_fake_a", "agent:fake-a", "rtd-0000000060"
            ),
        )

    def test_open_race_is_detected_without_using_replacement_content(self) -> None:
        path = self.write_records([_record("rtd-0000000070")])
        real_open = query._open_checked

        def racing_open(candidate: Path, expected):
            # Simulate a writer replacing the file after enumeration but before
            # the safe open.  The identity/size check must reject it.
            candidate.write_text(
                json.dumps(
                    _record(
                        "rtd-0000000071",
                        exception={
                            **_record("rtd-0000000071")["exception"],
                            "message": "REPLACEMENT SECRET C:\\private\\race.py",
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            return real_open(candidate, expected)

        provider = self.provider()
        with mock.patch.object(query, "_open_checked", side_effect=racing_open):
            page = provider.list_logs(
                "prj_fake_a",
                "agent:fake-a",
                self.spec(since=_NOW - timedelta(hours=24), until=_NOW),
            )
        self.assertFalse(page.scan.complete)
        self.assertNotIn("rtd-0000000071", [item.log_id for item in page.records])
        self.assertNotIn("REPLACEMENT SECRET", json.dumps(page.model_dump(by_alias=True)))


if __name__ == "__main__":
    unittest.main()
