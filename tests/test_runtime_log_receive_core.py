"""B2a isolated tests for the runtime log receive core.

All databases/tables are real SQLite databases created from the frozen
``server.models`` definitions.  No test imports ``server.db``/``server.auth``
or touches the production configuration, database, storage or logs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from server.models import (
    AgentInstance,
    Member,
    Project,
    ProjectAgent,
    ProjectRole,
    RoleServiceLaunch,
    RuntimeLogBatch,
    RuntimeLogEvent,
    RuntimeLogSource,
)
from server.runtime_log_receive_core import (
    PROJECTION_VERSION,
    PreparedBatch,
    PreparedRecord,
    RuntimeLogBatchReceipt,
    RuntimeLogLimits,
    RuntimeLogReceiveCore,
    RuntimeLogReceiveError,
    RuntimeLogSourceScope,
)


_OWN_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".tmp"
    / "runtime-log-sqlite-core-v1"
    / "deepseek"
    / "test-roots"
)

_MAINTAINER_KEY = "FAKE_MAINTAINER_KEY_FOR_CORE_TESTS_ONLY"
_ROLE_KEY = "FAKE_ROLE_KEY_FOR_CORE_TESTS_ONLY"
_OTHER_HUMAN_KEY = "FAKE_OTHER_HUMAN_KEY_FOR_CORE_TESTS_ONLY"
_ROLE2_KEY = "FAKE_ROLE2_KEY_FOR_CORE_TESTS_ONLY"
_BASE_TIME = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, value: datetime = _BASE_TIME) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class CoreFixture(unittest.TestCase):
    """Temporary real SQLModel schema + real transaction fixtures."""

    def setUp(self) -> None:
        _OWN_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = Path(tempfile.mkdtemp(prefix="core-", dir=str(_OWN_ROOT)))
        self.db_path = self.temp / "talk.db"
        self.engine = self._make_engine(timeout=10)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        SQLModel.metadata.create_all(self.engine)
        self.clock = MutableClock()
        self.limits = RuntimeLogLimits()
        self.core = self._core()
        self._next_launch_generation = 2

    def tearDown(self) -> None:
        try:
            self.engine.dispose()
        finally:
            shutil.rmtree(self.temp, ignore_errors=True)

    def _make_engine(self, *, timeout: float = 10):
        return create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False, "timeout": timeout},
        )

    def _core(
        self,
        *,
        limits: RuntimeLogLimits | None = None,
        clock: Callable[[], datetime] | None = None,
        enabled: bool = True,
        engine=None,
    ) -> RuntimeLogReceiveCore:
        return RuntimeLogReceiveCore(
            engine=engine or self.engine,
            limits=limits or self.limits,
            clock=clock or self.clock,
            enabled=enabled,
        )

    # ── real model fixtures ─────────────────────────────────────

    def seed_base(self) -> None:
        now = _BASE_TIME
        with Session(self.engine) as session:
            session.add_all(
                [
                    Member(
                        id="human:boss",
                        kind="human",
                        display_name="Boss",
                        api_key=_MAINTAINER_KEY,
                    ),
                    Member(
                        id="human:other",
                        kind="human",
                        display_name="Other",
                        api_key=_OTHER_HUMAN_KEY,
                    ),
                    Member(
                        id="agent:role",
                        kind="agent",
                        display_name="Role",
                        api_key=_ROLE_KEY,
                    ),
                    Project(
                        project_id="prj_demo",
                        display_name="Demo",
                        maintainer_member_id="human:boss",
                    ),
                    ProjectRole(
                        project_id="prj_demo",
                        member_id="agent:role",
                        role_name="dev",
                        created_by="human:boss",
                    ),
                    ProjectAgent(project_id="prj_demo", member_id="agent:role"),
                    AgentInstance(
                        id="ins_1",
                        member_id="agent:role",
                        runtime="dsh",
                        status="idle",
                        project_id="prj_demo",
                        launch_id="launch_1",
                        host="host-a",
                    ),
                    RoleServiceLaunch(
                        launch_id="launch_1",
                        project_id="prj_demo",
                        member_id="agent:role",
                        action="start",
                        generation=1,
                        expected_instance_id="ins_1",
                        launch_expires_at=now + timedelta(hours=1),
                        claim_host="host-a",
                        instance_id="ins_1",
                    ),
                ]
            )
            session.commit()

    def add_role_target(
        self,
        *,
        member_id: str,
        key: str,
        project_id: str = "prj_demo",
        role_name: str = "dev2",
        archived: bool = False,
        roster: bool = True,
        disabled: bool = False,
    ) -> None:
        with Session(self.engine) as session:
            session.add(
                Member(
                    id=member_id,
                    kind="agent",
                    display_name=member_id,
                    api_key=key,
                    disabled_at=_BASE_TIME if disabled else None,
                )
            )
            if role_name:
                session.add(
                    ProjectRole(
                        project_id=project_id,
                        member_id=member_id,
                        role_name=role_name,
                        created_by="human:boss",
                        archived_at=_BASE_TIME if archived else None,
                    )
                )
            if roster:
                session.add(ProjectAgent(project_id=project_id, member_id=member_id))
            session.commit()

    def add_instance(
        self,
        *,
        instance_id: str,
        launch_id: str | None,
        host: str = "host-a",
        member_id: str = "agent:role",
        project_id: str = "prj_demo",
        launch_claim_host: str | None = None,
        launch_instance_id: str | None = None,
        launch_project_id: str | None = None,
        launch_member_id: str | None = None,
        launch_action: str = "start",
        launch_generation: int | None = None,
    ) -> None:
        if launch_generation is None:
            launch_generation = self._next_launch_generation
            self._next_launch_generation += 1
        with Session(self.engine) as session:
            session.add(
                AgentInstance(
                    id=instance_id,
                    member_id=member_id,
                    runtime="dsh",
                    status="idle",
                    project_id=project_id,
                    launch_id=launch_id,
                    host=host,
                )
            )
            if launch_id is not None:
                session.add(
                    RoleServiceLaunch(
                        launch_id=launch_id,
                        project_id=launch_project_id or project_id,
                        member_id=launch_member_id or member_id,
                        action=launch_action,
                        generation=launch_generation,
                        expected_instance_id=launch_instance_id or instance_id,
                        launch_expires_at=_BASE_TIME + timedelta(hours=1),
                        claim_host=(
                            launch_claim_host if launch_claim_host is not None else host
                        ),
                        instance_id=launch_instance_id or instance_id,
                    )
                )
            session.commit()

    def role_scope(
        self,
        *,
        member_id: str = "agent:role",
        host: str = "host-a",
        project_id: str = "prj_demo",
    ) -> RuntimeLogSourceScope:
        return RuntimeLogSourceScope(
            project_id=project_id,
            host=host,
            subject_kind="role",
            subject_id=member_id,
        )

    def manager_scope(
        self, *, host: str = "host-a", project_id: str = "prj_demo"
    ) -> RuntimeLogSourceScope:
        return RuntimeLogSourceScope(
            project_id=project_id,
            host=host,
            subject_kind="manager",
            subject_id="manager",
        )

    def register(self, scope: RuntimeLogSourceScope, key: str = _MAINTAINER_KEY):
        return self.core.register_source(raw_api_key=key, scope=scope)

    def role_record(
        self,
        *,
        log_id: str = "log-1",
        payload: dict[str, Any] | None = None,
        instance_id: str | None = "ins_1",
        launch_id: str | None = "launch_1",
        member_id: str = "agent:role",
        project_id: str = "prj_demo",
        host: str = "host-a",
        manager_run_id: str | None = None,
    ) -> PreparedRecord:
        return PreparedRecord(
            project_id=project_id,
            host=host,
            subject_kind="role",
            member_id=member_id,
            instance_id=instance_id,
            launch_id=launch_id,
            manager_run_id=manager_run_id,
            log_id=log_id,
            payload=payload if payload is not None else {"message": "hello", "n": 1},
        )

    def manager_record(
        self,
        *,
        log_id: str = "mlog-1",
        manager_run_id: str = "mgr-run-1",
        host: str = "host-a",
        payload: dict[str, Any] | None = None,
    ) -> PreparedRecord:
        return PreparedRecord(
            project_id="prj_demo",
            host=host,
            subject_kind="manager",
            member_id="unknown",
            instance_id=None,
            launch_id=None,
            manager_run_id=manager_run_id,
            log_id=log_id,
            payload=(
                payload
                if payload is not None
                else {"manager_run": {"host": "host-a"}, "manager_seq": 1}
            ),
        )

    def batch(
        self,
        *,
        scope: RuntimeLogSourceScope,
        records: list[PreparedRecord],
        revision: int = 1,
        writer_run_id: str = "writer-run-1",
        batch_id: str = "batch-1",
        batch_seq: int = 1,
        projection_version: str = PROJECTION_VERSION,
    ) -> PreparedBatch:
        return PreparedBatch(
            scope=scope,
            source_revision=revision,
            writer_run_id=writer_run_id,
            batch_id=batch_id,
            batch_seq=batch_seq,
            records=records,
            projection_version=projection_version,
        )

    # ── assertions / DB helpers ────────────────────────────────

    def assert_error(self, code: str, call: Callable[[], Any]) -> RuntimeLogReceiveError:
        with self.assertRaises(RuntimeLogReceiveError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(_MAINTAINER_KEY, str(caught.exception))
        self.assertNotIn(_ROLE_KEY, str(caught.exception))
        self.assertNotIn("SELECT", str(caught.exception))
        return caught.exception

    def count_rows(self, table: str) -> int:
        with self.engine.connect() as connection:
            return int(
                connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
            )

    def source_row(self, scope: RuntimeLogSourceScope) -> RuntimeLogSource:
        with Session(self.engine) as session:
            row = session.get(RuntimeLogSource, scope.source_id)
            assert row is not None
            session.expunge(row)
            return row

    def event_rows(self) -> list[RuntimeLogEvent]:
        with Session(self.engine) as session:
            rows = list(session.exec(select(RuntimeLogEvent)).all())
            for row in rows:
                session.expunge(row)
            return rows

    def table_counts(self) -> tuple[int, int, int]:
        return (
            self.count_rows("runtime_log_sources"),
            self.count_rows("runtime_log_batches"),
            self.count_rows("runtime_log_events"),
        )


class ImportAndSchemaTests(CoreFixture):
    def test_import_has_no_db_auth_or_global_engine_side_effect(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        code = (
            "import sys\n"
            "import server.runtime_log_receive_core as core\n"
            "assert 'server.db' not in sys.modules, 'server.db imported'\n"
            "assert 'server.auth' not in sys.modules, 'server.auth imported'\n"
            "assert not hasattr(core, 'engine')\n"
            "print('IMPORT_OK')\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
        stdout_path = self.temp / "import.stdout.txt"
        stderr_path = self.temp / "import.stderr.txt"
        # Use regular files rather than pipes: the DSH Windows sandbox may deny
        # anonymous pipe creation even though ordinary workspace file I/O works.
        with (
            open(stdout_path, "w", encoding="utf-8") as stdout_file,
            open(stderr_path, "w", encoding="utf-8") as stderr_file,
        ):
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=str(project_root),
                env=env,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=60,
            )
        stdout = stdout_path.read_text(encoding="utf-8")
        stderr = stderr_path.read_text(encoding="utf-8")
        self.assertEqual(completed.returncode, 0, stderr)
        self.assertIn("IMPORT_OK", stdout)

    def test_real_models_create_only_three_new_tables(self) -> None:
        tables = set(SQLModel.metadata.tables)
        self.assertEqual(
            {name for name in tables if name.startswith("runtime_log_")},
            {"runtime_log_sources", "runtime_log_batches", "runtime_log_events"},
        )
        self.assertIn("disabled_at", {c.name for c in Member.__table__.columns})
        self.assertIn("archived_at", {c.name for c in ProjectRole.__table__.columns})
        self.assertIn("launch_id", {c.name for c in AgentInstance.__table__.columns})
        self.assertIn("claim_host", {c.name for c in RoleServiceLaunch.__table__.columns})

        with self.engine.connect() as connection:
            self.assertEqual(
                str(
                    connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
                ).lower(),
                "wal",
            )
            batch_indexes = {
                row[1]: bool(row[2])
                for row in connection.exec_driver_sql(
                    "PRAGMA index_list('runtime_log_batches')"
                ).fetchall()
            }
            event_indexes = {
                row[1]: bool(row[2])
                for row in connection.exec_driver_sql(
                    "PRAGMA index_list('runtime_log_events')"
                ).fetchall()
            }
            source_indexes = {
                row[1]: bool(row[2])
                for row in connection.exec_driver_sql(
                    "PRAGMA index_list('runtime_log_sources')"
                ).fetchall()
            }
        self.assertTrue(batch_indexes.get("ux_runtime_log_batches_key"))
        self.assertTrue(batch_indexes.get("ux_runtime_log_batches_seq"))
        self.assertTrue(event_indexes.get("ux_runtime_log_events_key"))
        self.assertTrue(event_indexes.get("ux_runtime_log_events_received_seq"))
        self.assertTrue(source_indexes.get("ux_runtime_log_sources_scope"))

    def test_default_disabled_and_explicit_session_factory(self) -> None:
        self.seed_base()
        factory_core = RuntimeLogReceiveCore(
            session_factory=lambda: Session(self.engine),
            limits=self.limits,
            clock=self.clock,
        )
        self.assertFalse(factory_core.enabled)
        scope = self.role_scope()
        self.assert_error(
            "receive_core_disabled",
            lambda: factory_core.register_source(
                raw_api_key=_MAINTAINER_KEY, scope=scope
            ),
        )
        enabled = RuntimeLogReceiveCore(
            session_factory=lambda: Session(self.engine),
            limits=self.limits,
            clock=self.clock,
            enabled=True,
        )
        state = enabled.register_source(raw_api_key=_MAINTAINER_KEY, scope=scope)
        self.assertTrue(state.active)
        receipt = enabled.ingest_batch(
            raw_api_key=_ROLE_KEY,
            batch=self.batch(scope=scope, records=[self.role_record()]),
        )
        self.assertTrue(receipt.accepted)

    def test_disabled_core_rejects_before_any_write(self) -> None:
        self.seed_base()
        scope = self.role_scope()
        disabled = self._core(enabled=False)
        self.assert_error(
            "receive_core_disabled",
            lambda: disabled.register_source(raw_api_key=_MAINTAINER_KEY, scope=scope),
        )
        prepared = self.batch(scope=scope, records=[self.role_record()])
        self.assert_error(
            "receive_core_disabled",
            lambda: disabled.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared),
        )
        self.assertEqual(self.table_counts(), (0, 0, 0))


class SourceRegistryTests(CoreFixture):
    def setUp(self) -> None:
        super().setUp()
        self.seed_base()
        self.scope = self.role_scope()

    def test_register_auth_maintainer_and_cas_replay(self) -> None:
        self.assert_error(
            "invalid_api_key",
            lambda: self.core.register_source(raw_api_key="bad-key", scope=self.scope),
        )
        self.assert_error(
            "not_maintainer",
            lambda: self.core.register_source(raw_api_key=_ROLE_KEY, scope=self.scope),
        )
        self.assert_error(
            "not_maintainer",
            lambda: self.core.register_source(
                raw_api_key=_OTHER_HUMAN_KEY, scope=self.scope
            ),
        )

        state = self.core.register_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=0,
        )
        self.assertTrue(state.active)
        self.assertEqual(state.revision, 1)
        self.assertFalse(state.replayed)
        self.assertEqual(state.batch_count, 0)
        self.assertEqual(state.next_event_seq, 1)
        self.assertEqual(self.count_rows("runtime_log_sources"), 1)
        self.assertNotIn(_MAINTAINER_KEY, json.dumps(state.as_dict()))

        replay = self.register(self.scope)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.revision, 1)
        self.assertEqual(self.count_rows("runtime_log_sources"), 1)

        self.assert_error(
            "source_revision_conflict",
            lambda: self.core.register_source(
                raw_api_key=_MAINTAINER_KEY, scope=self.scope, expected_revision=99
            ),
        )

        revoked = self.core.revoke_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=1,
        )
        self.assertFalse(revoked.active)
        self.assertEqual(revoked.revision, 2)
        self.assertIsNotNone(revoked.revoked_at)
        self.assert_error(
            "source_revision_conflict",
            lambda: self.core.revoke_source(
                raw_api_key=_MAINTAINER_KEY,
                scope=self.scope,
                expected_revision=1,
            ),
        )
        again = self.core.revoke_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=2,
        )
        self.assertTrue(again.replayed)
        self.assertEqual(again.revision, 2)

        self.assert_error(
            "source_revoked",
            lambda: self.register(self.scope),
        )
        revoked_batch = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="revoked-log")],
            batch_id="b-revoked",
            revision=1,
        )
        self.assert_error(
            "source_revoked",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=revoked_batch
            ),
        )

        active = self.core.reactivate_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=2,
        )
        self.assertTrue(active.active)
        self.assertEqual(active.revision, 3)
        self.assertIsNone(active.revoked_at)
        replayed_active = self.core.reactivate_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=3,
        )
        self.assertTrue(replayed_active.replayed)
        self.assertEqual(replayed_active.revision, 3)
        stale_batch = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="stale-log")],
            batch_id="b-stale",
            revision=2,
        )
        self.assert_error(
            "source_revision_conflict",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=stale_batch
            ),
        )
        self.assertEqual(self.table_counts(), (1, 0, 0))

    def test_source_key_rotation_disable_and_scope_validation(self) -> None:
        self.register(self.scope)
        with Session(self.engine) as session:
            member = session.get(Member, "human:boss")
            assert member is not None
            member.api_key = "ROTATED_MAINTAINER_KEY"
            session.add(member)
            session.commit()

        self.assert_error(
            "invalid_api_key",
            lambda: self.core.register_source(
                raw_api_key=_MAINTAINER_KEY, scope=self.scope
            ),
        )
        replayed = self.core.register_source(
            raw_api_key="ROTATED_MAINTAINER_KEY", scope=self.scope
        )
        self.assertTrue(replayed.replayed)

        with Session(self.engine) as session:
            member = session.get(Member, "human:boss")
            assert member is not None
            member.disabled_at = _BASE_TIME
            session.add(member)
            session.commit()
        self.assert_error(
            "member_disabled",
            lambda: self.core.register_source(
                raw_api_key="ROTATED_MAINTAINER_KEY", scope=self.scope
            ),
        )

        def _path_scope() -> RuntimeLogSourceScope:
            return RuntimeLogSourceScope(
                project_id="prj_demo",
                host="host-a",
                subject_kind="role",
                subject_id="agent:role/with/path",
            )

        def _manager_literal_scope() -> RuntimeLogSourceScope:
            return RuntimeLogSourceScope(
                project_id="prj_demo",
                host="host-a",
                subject_kind="manager",
                subject_id="not-manager",
            )

        self.assert_error("invalid_scope", _path_scope)
        self.assert_error("invalid_scope", _manager_literal_scope)

    def test_archived_role_never_falls_back_to_roster(self) -> None:
        self.add_role_target(
            member_id="agent:archived",
            key="KEY_ARCHIVED",
            role_name="archived-role",
            archived=True,
            roster=True,
        )
        self.assert_error(
            "role_archived",
            lambda: self.register(self.role_scope(member_id="agent:archived")),
        )

        self.add_role_target(
            member_id="agent:legacy",
            key="KEY_LEGACY",
            role_name="",
            roster=True,
        )
        state = self.register(self.role_scope(member_id="agent:legacy"))
        self.assertTrue(state.active)

        self.add_role_target(
            member_id="agent:disabled",
            key="KEY_DISABLED",
            role_name="disabled-role",
            roster=True,
            disabled=True,
        )
        self.assert_error(
            "role_member_disabled",
            lambda: self.register(self.role_scope(member_id="agent:disabled")),
        )

    def test_scope_bounds_control_chars_and_bool_revision(self) -> None:
        def overlong_host() -> RuntimeLogSourceScope:
            return RuntimeLogSourceScope(
                project_id="prj_demo",
                host="h" * 201,
                subject_kind="role",
                subject_id="agent:role",
            )

        def control_host() -> RuntimeLogSourceScope:
            return RuntimeLogSourceScope(
                project_id="prj_demo",
                host="host\ninjected",
                subject_kind="role",
                subject_id="agent:role",
            )

        self.assert_error("invalid_request", overlong_host)
        self.assert_error("invalid_request", control_host)
        self.assert_error(
            "invalid_request",
            lambda: self.core.register_source(
                raw_api_key=_MAINTAINER_KEY,
                scope=self.scope,
                expected_revision=True,
            ),
        )
        self.assertEqual(self.table_counts(), (0, 0, 0))

    def test_manager_source_needs_no_instance_or_role(self) -> None:
        state = self.register(self.manager_scope())
        self.assertTrue(state.active)
        self.assertEqual(state.subject_kind, "manager")
        self.assertEqual(state.subject_id, "manager")
        # An agent Key still cannot manage a source.
        self.assert_error(
            "not_maintainer",
            lambda: self.core.register_source(
                raw_api_key=_ROLE_KEY, scope=self.manager_scope(host="host-b")
            ),
        )

        # A brand-new project/host with no role, roster or instance entry can
        # still have an explicit manager source.  This is the first-empty-host
        # case, not an inferred host.
        with Session(self.engine) as session:
            session.add(
                Project(
                    project_id="prj_empty",
                    display_name="Empty",
                    maintainer_member_id="human:boss",
                )
            )
            session.commit()
        empty_scope = self.manager_scope(
            host="host-first-empty", project_id="prj_empty"
        )
        empty_state = self.register(empty_scope)
        self.assertTrue(empty_state.active)
        receipt = self.core.ingest_batch(
            raw_api_key=_MAINTAINER_KEY,
            batch=self.batch(
                scope=empty_scope,
                records=[
                    PreparedRecord(
                        project_id="prj_empty",
                        host="host-first-empty",
                        subject_kind="manager",
                        member_id="unknown",
                        instance_id=None,
                        launch_id=None,
                        manager_run_id="mgr-empty",
                        log_id="empty-manager-log",
                        payload={
                            "manager_run": {"host": "host-first-empty"},
                            "event": "started",
                        },
                    )
                ],
                batch_id="b-empty-host",
            ),
        )
        self.assertTrue(receipt.accepted)
        self.assertEqual(receipt.events[0].manager_run_id, "mgr-empty")

    def test_global_source_cap_is_not_reset_by_revoke(self) -> None:
        tight = RuntimeLogLimits(
            max_sources_total=1,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        core = self._core(limits=tight)
        core.register_source(raw_api_key=_MAINTAINER_KEY, scope=self.scope)
        self.assert_error(
            "quota_source_count",
            lambda: core.register_source(
                raw_api_key=_MAINTAINER_KEY, scope=self.manager_scope()
            ),
        )
        core.revoke_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=1,
        )
        self.assert_error(
            "quota_source_count",
            lambda: core.register_source(
                raw_api_key=_MAINTAINER_KEY, scope=self.manager_scope()
            ),
        )
        self.assertEqual(self.count_rows("runtime_log_sources"), 1)

    def test_source_revoke_after_role_archive_is_allowed(self) -> None:
        self.register(self.scope)
        with Session(self.engine) as session:
            role = session.get(ProjectRole, ("prj_demo", "agent:role"))
            assert role is not None
            role.archived_at = _BASE_TIME
            session.add(role)
            session.commit()
        state = self.core.revoke_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=1,
        )
        self.assertFalse(state.active)


class RoleIngestTests(CoreFixture):
    def setUp(self) -> None:
        super().setUp()
        self.seed_base()
        self.scope = self.role_scope()
        self.source = self.register(self.scope)

    def test_role_batch_receipt_dedup_repartition_and_conflicts(self) -> None:
        first = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="log-1", payload={"message": "一"}),
                self.role_record(log_id="log-2", payload={"message": "二"}),
            ],
        )
        receipt = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=first)
        self.assertIsInstance(receipt, RuntimeLogBatchReceipt)
        self.assertTrue(receipt.accepted)
        self.assertFalse(receipt.replayed)
        self.assertEqual([event.received_seq for event in receipt.events], [1, 2])
        self.assertEqual(len({event.event_uid for event in receipt.events}), 2)
        self.assertNotIn("message", json.dumps(receipt.as_dict(), ensure_ascii=False))
        self.assertNotIn(_ROLE_KEY, json.dumps(receipt.as_dict(), ensure_ascii=False))

        row = self.source_row(self.scope)
        self.assertEqual(row.batch_count, 1)
        self.assertEqual(row.event_count, 2)
        self.assertEqual(row.next_event_seq, 3)
        bytes_after_first = row.bytes_used
        self.assertEqual(self.table_counts(), (1, 1, 2))

        replay = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=first)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.received_at, receipt.received_at)
        self.assertEqual(
            [event.event_uid for event in replay.events],
            [event.event_uid for event in receipt.events],
        )
        self.assertEqual(
            [event.received_at for event in replay.events],
            [event.received_at for event in receipt.events],
        )
        self.assertEqual(self.source_row(self.scope).bytes_used, bytes_after_first)

        changed = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="log-1", payload={"message": "changed"}),
                self.role_record(log_id="log-2", payload={"message": "二"}),
            ],
        )
        self.assert_error(
            "batch_content_conflict",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=changed),
        )
        self.assertEqual(self.table_counts(), (1, 1, 2))

        same_seq = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="log-3")],
            batch_id="batch-2",
            batch_seq=1,
        )
        self.assert_error(
            "batch_seq_conflict",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=same_seq),
        )
        self.assertEqual(self.table_counts(), (1, 1, 2))

        self.clock.value = self.clock.value + timedelta(minutes=5)
        reordered = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="log-2", payload={"message": "二"}),
                self.role_record(log_id="log-1", payload={"message": "一"}),
            ],
            batch_id="batch-reordered",
            batch_seq=7,
        )
        reordered_receipt = self.core.ingest_batch(
            raw_api_key=_ROLE_KEY, batch=reordered
        )
        self.assertFalse(reordered_receipt.replayed)
        self.assertEqual(
            [event.event_uid for event in reordered_receipt.events],
            [receipt.events[1].event_uid, receipt.events[0].event_uid],
        )
        self.assertEqual(
            [event.received_at for event in reordered_receipt.events],
            [receipt.events[1].received_at, receipt.events[0].received_at],
        )
        self.assertNotEqual(reordered_receipt.received_at, receipt.received_at)
        reordered_replay = self.core.ingest_batch(
            raw_api_key=_ROLE_KEY, batch=reordered
        )
        self.assertTrue(reordered_replay.replayed)
        self.assertEqual(reordered_replay.received_at, reordered_receipt.received_at)
        self.assertEqual(
            [event.received_at for event in reordered_replay.events],
            [receipt.events[1].received_at, receipt.events[0].received_at],
        )
        row = self.source_row(self.scope)
        self.assertEqual(row.batch_count, 2)
        self.assertEqual(row.event_count, 2)
        self.assertEqual(row.next_event_seq, 3)
        self.assertGreater(row.bytes_used, bytes_after_first)

        conflict_event = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="log-1", payload={"message": "different"}),
                self.role_record(log_id="log-4"),
            ],
            batch_id="batch-conflict",
            batch_seq=8,
        )
        self.assert_error(
            "event_content_conflict",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=conflict_event
            ),
        )
        # Whole-batch rollback: neither the conflicting new event nor the batch
        # was persisted, and source counters/sequence are unchanged.
        self.assertEqual(self.table_counts(), (1, 2, 2))
        row = self.source_row(self.scope)
        self.assertEqual(row.batch_count, 2)
        self.assertEqual(row.event_count, 2)
        self.assertEqual(row.next_event_seq, 3)
        bytes_after_conflict = row.bytes_used

        # Same event key, same payload, different attribution is a conflict
        # too, even though the payload content SHA is identical.
        self.add_instance(instance_id="ins_attr", launch_id="launch_attr")
        attribution_conflict = self.batch(
            scope=self.scope,
            records=[
                self.role_record(
                    log_id="log-1",
                    payload={"message": "一"},
                    instance_id="ins_attr",
                    launch_id="launch_attr",
                )
            ],
            batch_id="batch-attribution-conflict",
            batch_seq=9,
        )
        self.assert_error(
            "event_content_conflict",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=attribution_conflict
            ),
        )
        self.assertEqual(self.table_counts(), (1, 2, 2))
        self.assertEqual(self.source_row(self.scope).bytes_used, bytes_after_conflict)

        other_writer = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="log-1", payload={"message": "一"})],
            writer_run_id="writer-run-2",
            batch_id="batch-writer-2",
            batch_seq=1,
        )
        other_receipt = self.core.ingest_batch(
            raw_api_key=_ROLE_KEY, batch=other_writer
        )
        self.assertNotEqual(
            other_receipt.events[0].event_uid, receipt.events[0].event_uid
        )
        self.assertEqual(other_receipt.events[0].received_seq, 3)

    def test_role_identity_launch_and_archived_rechecks(self) -> None:
        bad_project = self.batch(
            scope=self.scope,
            records=[self.role_record(project_id="prj_other")],
            batch_id="b-bad-project",
        )
        self.assert_error(
            "invalid_attribution",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=bad_project),
        )

        # Instance host mismatch.
        self.add_instance(instance_id="ins_wrong_host", launch_id=None, host="host-b")
        bad_host = self.batch(
            scope=self.scope,
            records=[self.role_record(instance_id="ins_wrong_host", launch_id=None)],
            batch_id="b-bad-host",
        )
        self.assert_error(
            "instance_attribution_conflict",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=bad_host),
        )

        # Instance project/member mismatch.
        self.add_instance(
            instance_id="ins_wrong_project",
            launch_id=None,
            project_id="prj_other",
            member_id="agent:role",
        )
        bad_instance_project = self.batch(
            scope=self.scope,
            records=[
                self.role_record(instance_id="ins_wrong_project", launch_id=None)
            ],
            batch_id="b-bad-instance-project",
        )
        self.assert_error(
            "instance_attribution_conflict",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=bad_instance_project
            ),
        )

        # Instance launch id and launch.instance_id must agree.
        self.add_instance(instance_id="ins_2", launch_id="launch_2")
        mismatched_launch = self.batch(
            scope=self.scope,
            records=[
                self.role_record(instance_id="ins_2", launch_id="launch_1")
            ],
            batch_id="b-launch-mismatch",
        )
        self.assert_error(
            "launch_attribution_conflict",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=mismatched_launch
            ),
        )

        self.add_instance(
            instance_id="ins_3",
            launch_id="launch_3",
            launch_instance_id="ins_1",
        )
        launch_instance_mismatch = self.batch(
            scope=self.scope,
            records=[self.role_record(instance_id="ins_3", launch_id="launch_3")],
            batch_id="b-launch-instance-mismatch",
        )
        self.assert_error(
            "launch_attribution_conflict",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=launch_instance_mismatch
            ),
        )

        self.add_instance(
            instance_id="ins_4",
            launch_id="launch_4",
            launch_claim_host="host-elsewhere",
        )
        bad_launch_host = self.batch(
            scope=self.scope,
            records=[self.role_record(instance_id="ins_4", launch_id="launch_4")],
            batch_id="b-launch-host",
        )
        self.assert_error(
            "launch_attribution_conflict",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=bad_launch_host
            ),
        )

        linked_no_record_launch = self.batch(
            scope=self.scope,
            records=[self.role_record(instance_id="ins_1", launch_id=None)],
            batch_id="b-linked-no-launch",
        )
        self.assert_error(
            "launch_attribution_conflict",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=linked_no_record_launch
            ),
        )

        # A genuinely old instance with no launch association is downgraded to
        # role_instance, but only because the instance itself has no launch.
        self.add_instance(instance_id="ins_old", launch_id=None)
        old = self.batch(
            scope=self.scope,
            records=[
                self.role_record(
                    log_id="old-log",
                    instance_id="ins_old",
                    launch_id=None,
                )
            ],
            batch_id="b-old",
            batch_seq=2,
        )
        old_receipt = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=old)
        self.assertEqual(
            old_receipt.events[0].attribution_kind, "role_instance"
        )
        self.assertIsNone(old_receipt.events[0].launch_id)

        # Role source cannot upload manager attribution.
        manager_on_role = self.batch(
            scope=self.scope,
            records=[
                self.role_record(
                    log_id="role-manager",
                    instance_id="ins_old",
                    launch_id=None,
                    manager_run_id="mgr-1",
                )
            ],
            batch_id="b-role-manager",
            batch_seq=3,
        )
        self.assert_error(
            "invalid_attribution",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=manager_on_role
            ),
        )

        with Session(self.engine) as session:
            role = session.get(ProjectRole, ("prj_demo", "agent:role"))
            assert role is not None
            role.archived_at = _BASE_TIME
            session.add(role)
            session.commit()
        archived = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="archived-log")],
            batch_id="b-archived",
            batch_seq=4,
        )
        self.assert_error(
            "role_archived",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=archived),
        )

    def test_same_log_id_across_host_project_and_run_is_isolated(self) -> None:
        first = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="shared-log", payload={"message": "shared"})
            ],
            batch_id="b-host-a",
        )
        receipt_a = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=first)

        # Same role/member/project, different host/source.
        self.add_instance(
            instance_id="ins_host_b",
            launch_id="launch_host_b",
            host="host-b",
        )
        host_b_scope = self.role_scope(host="host-b")
        self.register(host_b_scope)
        receipt_b = self.core.ingest_batch(
            raw_api_key=_ROLE_KEY,
            batch=self.batch(
                scope=host_b_scope,
                records=[
                    self.role_record(
                        log_id="shared-log",
                        payload={"message": "shared"},
                        instance_id="ins_host_b",
                        launch_id="launch_host_b",
                        host="host-b",
                    )
                ],
                batch_id="b-host-b",
            ),
        )
        self.assertNotEqual(
            receipt_a.events[0].event_uid, receipt_b.events[0].event_uid
        )
        self.assertEqual(receipt_b.events[0].received_seq, 1)

        # Same host and writer but a different project/source.  A different
        # role agent is used to keep the fixture's project-role keys disjoint.
        with Session(self.engine) as session:
            session.add(
                Project(
                    project_id="prj_other",
                    display_name="Other",
                    maintainer_member_id="human:boss",
                )
            )
            session.add(
                Member(
                    id="agent:role-other",
                    kind="agent",
                    display_name="Other Role",
                    api_key="OTHER_ROLE_KEY",
                )
            )
            session.add(
                ProjectRole(
                    project_id="prj_other",
                    member_id="agent:role-other",
                    role_name="dev-other",
                    created_by="human:boss",
                )
            )
            session.add(ProjectAgent(project_id="prj_other", member_id="agent:role-other"))
            session.add(
                AgentInstance(
                    id="ins_other_project",
                    member_id="agent:role-other",
                    runtime="dsh",
                    status="idle",
                    project_id="prj_other",
                    launch_id="launch_other_project",
                    host="host-a",
                )
            )
            session.add(
                RoleServiceLaunch(
                    launch_id="launch_other_project",
                    project_id="prj_other",
                    member_id="agent:role-other",
                    action="start",
                    generation=1,
                    expected_instance_id="ins_other_project",
                    launch_expires_at=_BASE_TIME + timedelta(hours=1),
                    claim_host="host-a",
                    instance_id="ins_other_project",
                )
            )
            session.commit()
        other_scope = self.role_scope(
            member_id="agent:role-other", project_id="prj_other"
        )
        self.register(other_scope)
        receipt_other = self.core.ingest_batch(
            raw_api_key="OTHER_ROLE_KEY",
            batch=self.batch(
                scope=other_scope,
                records=[
                    self.role_record(
                        log_id="shared-log",
                        payload={"message": "shared"},
                        member_id="agent:role-other",
                        project_id="prj_other",
                        instance_id="ins_other_project",
                        launch_id="launch_other_project",
                    )
                ],
                batch_id="b-other-project",
            ),
        )
        self.assertNotEqual(
            receipt_a.events[0].event_uid, receipt_other.events[0].event_uid
        )
        self.assertEqual(receipt_other.events[0].received_seq, 1)

        # Same source and log id but a different writer run is also isolated.
        receipt_run = self.core.ingest_batch(
            raw_api_key="OTHER_ROLE_KEY",
            batch=self.batch(
                scope=other_scope,
                records=[
                    self.role_record(
                        log_id="shared-log",
                        payload={"message": "shared"},
                        member_id="agent:role-other",
                        project_id="prj_other",
                        instance_id="ins_other_project",
                        launch_id="launch_other_project",
                    )
                ],
                writer_run_id="other-writer",
                batch_id="b-other-run",
                batch_seq=2,
            ),
        )
        self.assertNotEqual(
            receipt_other.events[0].event_uid, receipt_run.events[0].event_uid
        )

    def test_committed_batch_replay_survives_event_row_cleanup(self) -> None:
        prepared = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="survives-cleanup")],
            batch_id="b-survives-cleanup",
        )
        first = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)
        with Session(self.engine) as session:
            launch = session.get(RoleServiceLaunch, "launch_1")
            instance = session.get(AgentInstance, "ins_1")
            assert launch is not None and instance is not None
            session.delete(launch)
            session.delete(instance)
            session.commit()
        replay = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.received_at, first.received_at)
        self.assertEqual(
            [event.received_at for event in replay.events],
            [event.received_at for event in first.events],
        )

    def test_role_key_rotation_and_disable_are_rechecked(self) -> None:
        prepared = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="rotate-role")],
            batch_id="b-rotate-role",
        )
        with Session(self.engine) as session:
            member = session.get(Member, "agent:role")
            assert member is not None
            member.api_key = "ROTATED_ROLE_KEY"
            session.add(member)
            session.commit()
        self.assert_error(
            "invalid_api_key",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared),
        )
        receipt = self.core.ingest_batch(
            raw_api_key="ROTATED_ROLE_KEY", batch=prepared
        )
        self.assertTrue(receipt.accepted)

        with Session(self.engine) as session:
            member = session.get(Member, "agent:role")
            assert member is not None
            member.disabled_at = _BASE_TIME
            session.add(member)
            session.commit()
        second = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="rotate-role-2")],
            batch_id="b-rotate-role-2",
            batch_seq=2,
        )
        self.assert_error(
            "member_disabled",
            lambda: self.core.ingest_batch(
                raw_api_key="ROTATED_ROLE_KEY", batch=second
            ),
        )

    def test_role_key_must_match_source_and_role_cannot_manage_source(self) -> None:
        other = self.batch(
            scope=self.scope,
            records=[self.role_record()],
            batch_id="b-other-key",
        )
        self.assert_error(
            "not_source_role",
            lambda: self.core.ingest_batch(
                raw_api_key=_MAINTAINER_KEY, batch=other
            ),
        )
        self.add_role_target(
            member_id="agent:role2",
            key=_ROLE2_KEY,
            role_name="dev2",
        )
        self.assert_error(
            "not_source_role",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE2_KEY, batch=other
            ),
        )


class ManagerIngestTests(CoreFixture):
    def setUp(self) -> None:
        super().setUp()
        self.seed_base()
        self.scope = self.manager_scope()
        self.source = self.register(self.scope)

    def test_manager_batch_uses_independent_writer_and_manager_ids(self) -> None:
        records = [
            self.manager_record(
                log_id="mlog-started",
                manager_run_id="serve-run-1",
                payload={
                    "manager_run": {"host": "host-a"},
                    "manager_seq": 1,
                    "event": "started",
                },
            ),
            self.manager_record(
                log_id="mlog-terminal",
                manager_run_id="serve-run-1",
                payload={
                    "manager_run": {"host": "host-a"},
                    "manager_seq": 1,
                    "event": "terminal",
                },
            ),
        ]
        receipt = self.core.ingest_batch(
            raw_api_key=_MAINTAINER_KEY,
            batch=self.batch(
                scope=self.scope,
                records=records,
                writer_run_id="top-level-writer-run",
                batch_id="manager-batch",
                batch_seq=9,
            ),
        )
        self.assertTrue(receipt.accepted)
        self.assertEqual(
            [event.manager_run_id for event in receipt.events],
            ["serve-run-1", "serve-run-1"],
        )
        self.assertEqual(
            [event.instance_id for event in receipt.events], [None, None]
        )
        self.assertEqual([event.received_seq for event in receipt.events], [1, 2])
        rows = self.event_rows()
        self.assertEqual({row.member_id for row in rows}, {"unknown"})
        self.assertEqual({row.writer_run_id for row in rows}, {"top-level-writer-run"})
        self.assertEqual({row.manager_run_id for row in rows}, {"serve-run-1"})

        # Out-of-order batch_seq and a gap are accepted; they do not imply log
        # loss.  A different manager/writer id pair is also accepted.
        later = self.core.ingest_batch(
            raw_api_key=_MAINTAINER_KEY,
            batch=self.batch(
                scope=self.scope,
                records=[
                    self.manager_record(
                        log_id="mlog-later",
                        manager_run_id="serve-run-2",
                        payload={"manager_run": {"host": "host-a"}, "manager_seq": 8},
                    )
                ],
                writer_run_id="writer-run-other",
                batch_id="manager-batch-2",
                batch_seq=2,
            ),
        )
        self.assertFalse(later.replayed)
        self.assertEqual(later.events[0].manager_run_id, "serve-run-2")

    def test_manager_attribution_and_host_rejections(self) -> None:
        wrong_member = self.batch(
            scope=self.scope,
            records=[
                PreparedRecord(
                    project_id="prj_demo",
                    host="host-a",
                    subject_kind="manager",
                    member_id="agent:role",
                    instance_id=None,
                    launch_id=None,
                    manager_run_id="mgr-1",
                    log_id="bad-member",
                    payload={"manager_run": {"host": "host-a"}},
                )
            ],
            batch_id="b-bad-member",
        )
        self.assert_error(
            "invalid_attribution",
            lambda: self.core.ingest_batch(
                raw_api_key=_MAINTAINER_KEY, batch=wrong_member
            ),
        )

        with_instance = self.batch(
            scope=self.scope,
            records=[
                PreparedRecord(
                    project_id="prj_demo",
                    host="host-a",
                    subject_kind="manager",
                    member_id="unknown",
                    instance_id="ins_1",
                    launch_id=None,
                    manager_run_id="mgr-1",
                    log_id="bad-instance",
                    payload={"manager_run": {"host": "host-a"}},
                )
            ],
            batch_id="b-bad-instance",
        )
        self.assert_error(
            "invalid_attribution",
            lambda: self.core.ingest_batch(
                raw_api_key=_MAINTAINER_KEY, batch=with_instance
            ),
        )

        missing_manager = self.batch(
            scope=self.scope,
            records=[
                PreparedRecord(
                    project_id="prj_demo",
                    host="host-a",
                    subject_kind="manager",
                    member_id="unknown",
                    instance_id=None,
                    launch_id=None,
                    manager_run_id=None,
                    log_id="missing-manager",
                    payload={"manager_run": {"host": "host-a"}},
                )
            ],
            batch_id="b-missing-manager",
        )
        self.assert_error(
            "invalid_attribution",
            lambda: self.core.ingest_batch(
                raw_api_key=_MAINTAINER_KEY, batch=missing_manager
            ),
        )

        wrong_payload_host = self.batch(
            scope=self.scope,
            records=[
                self.manager_record(
                    log_id="bad-payload-host",
                    payload={"manager_run": {"host": "host-b"}},
                )
            ],
            batch_id="b-payload-host",
        )
        self.assert_error(
            "invalid_attribution",
            lambda: self.core.ingest_batch(
                raw_api_key=_MAINTAINER_KEY, batch=wrong_payload_host
            ),
        )

        wrong_record_host = self.batch(
            scope=self.scope,
            records=[
                PreparedRecord(
                    project_id="prj_demo",
                    host="host-b",
                    subject_kind="manager",
                    member_id="unknown",
                    instance_id=None,
                    launch_id=None,
                    manager_run_id="mgr-1",
                    log_id="bad-record-host",
                    payload={"manager_run": {"host": "host-b"}},
                )
            ],
            batch_id="b-record-host",
        )
        self.assert_error(
            "invalid_attribution",
            lambda: self.core.ingest_batch(
                raw_api_key=_MAINTAINER_KEY, batch=wrong_record_host
            ),
        )

        # An agent (even the source role) cannot ingest as manager.
        self.add_role_target(
            member_id="agent:role2", key=_ROLE2_KEY, role_name="dev2"
        )
        valid = self.batch(
            scope=self.scope,
            records=[self.manager_record(log_id="manager-valid")],
            batch_id="b-manager-valid",
        )
        self.assert_error(
            "not_maintainer",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE2_KEY, batch=valid),
        )
        self.assertEqual(self.table_counts(), (1, 0, 0))


class FailuresAndQuotaTests(CoreFixture):
    def setUp(self) -> None:
        super().setUp()
        self.seed_base()
        self.scope = self.role_scope()
        self.register(self.scope)

    def test_clock_failures_rollback(self) -> None:
        for clock in (
            lambda: None,
            lambda: datetime(2026, 10, 20, 12, 0),  # naive
            lambda: (_ for _ in ()).throw(RuntimeError("clock exploded")),
        ):
            core = self._core(clock=clock)
            prepared = self.batch(
                scope=self.scope,
                records=[self.role_record(log_id="clock-log")],
                batch_id="b-clock",
            )
            self.assert_error(
                "clock_invalid",
                lambda: core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared),
            )
            self.assertEqual(self.table_counts(), (1, 0, 0))
            self.assertEqual(self.source_row(self.scope).next_event_seq, 1)

    def test_wall_clock_rollback_is_preserved(self) -> None:
        self.clock.value = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        first = self.core.ingest_batch(
            raw_api_key=_ROLE_KEY,
            batch=self.batch(
                scope=self.scope,
                records=[self.role_record(log_id="clock-first")],
                batch_id="b-clock-first",
                batch_seq=1,
            ),
        )
        self.clock.value = datetime(2026, 10, 20, 11, 0, tzinfo=timezone.utc)
        second = self.core.ingest_batch(
            raw_api_key=_ROLE_KEY,
            batch=self.batch(
                scope=self.scope,
                records=[self.role_record(log_id="clock-second")],
                batch_id="b-clock-second",
                batch_seq=2,
            ),
        )
        self.assertLess(second.received_at, first.received_at)

        # The injected clock's offset is preserved, not silently rewritten.
        self.clock.value = datetime(
            2026,
            10,
            20,
            13,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        )
        third = self.core.ingest_batch(
            raw_api_key=_ROLE_KEY,
            batch=self.batch(
                scope=self.scope,
                records=[self.role_record(log_id="clock-third")],
                batch_id="b-clock-third",
                batch_seq=3,
            ),
        )
        self.assertEqual(
            datetime.fromisoformat(third.received_at),
            datetime(2026, 10, 20, 13, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        rows = {
            row.log_id: row.received_at for row in self.event_rows()
        }
        self.assertEqual(rows["clock-first"], first.events[0].received_at)
        self.assertEqual(rows["clock-second"], second.events[0].received_at)
        self.assertEqual(rows["clock-third"], third.events[0].received_at)
        self.assertEqual(self.source_row(self.scope).event_count, 3)

    def test_injected_constraint_failure_rolls_back_entire_batch(self) -> None:
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER fail_core_event BEFORE INSERT ON runtime_log_events "
                "WHEN NEW.log_id = 'log-fail' "
                "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
            )
        prepared = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="log-ok"),
                self.role_record(log_id="log-fail"),
            ],
            batch_id="b-trigger",
        )
        with self.assertRaises(RuntimeLogReceiveError) as caught:
            self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)
        self.assertIn(caught.exception.status_code, (409, 503))
        self.assertEqual(self.table_counts(), (1, 0, 0))
        row = self.source_row(self.scope)
        self.assertEqual(row.batch_count, 0)
        self.assertEqual(row.event_count, 0)
        self.assertEqual(row.next_event_seq, 1)

        with self.engine.connect() as connection:
            connection.exec_driver_sql("DROP TRIGGER fail_core_event")

    def test_busy_database_is_stable_and_never_retries(self) -> None:
        holder = self._make_engine(timeout=0)
        with holder.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            busy_core = self._core(engine=self._make_engine(timeout=0))
            prepared = self.batch(
                scope=self.scope,
                records=[self.role_record(log_id="busy-log")],
                batch_id="b-busy",
            )
            error = self.assert_error(
                "database_busy",
                lambda: busy_core.ingest_batch(
                    raw_api_key=_ROLE_KEY, batch=prepared
                ),
            )
            self.assertEqual(error.status_code, 503)
            connection.rollback()
        holder.dispose()
        self.assertEqual(self.table_counts(), (1, 0, 0))

    def test_commit_success_replay_after_restart_and_receipt_whitelist(self) -> None:
        prepared = self.batch(
            scope=self.scope,
            records=[
                self.role_record(
                    log_id="persist-log",
                    payload={"message": "保留", "fake_secret": "DO_NOT_LEAK"},
                )
            ],
            batch_id="b-persist",
        )
        first = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)
        self.assertNotIn("DO_NOT_LEAK", json.dumps(first.as_dict(), ensure_ascii=False))

        # Simulate a lost response: discard the core/engine and replay with a
        # fresh core bound to a fresh engine.  The original receipt must come
        # back with only replayed=true changed.
        self.engine.dispose()
        restarted_engine = self._make_engine(timeout=10)
        restarted = RuntimeLogReceiveCore(
            engine=restarted_engine,
            limits=self.limits,
            clock=self.clock,
            enabled=True,
        )
        replay = restarted.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.received_at, first.received_at)
        self.assertEqual(
            [event.event_uid for event in replay.events],
            [event.event_uid for event in first.events],
        )
        restarted_engine.dispose()

        # Inject unknown keys into the stored receipt JSON.  Replay must rebuild
        # only the safe whitelist and must not return those keys.
        with Session(self.engine) as session:
            batch_row = session.exec(
                select(RuntimeLogBatch).where(RuntimeLogBatch.batch_id == "b-persist")
            ).first()
            assert batch_row is not None
            raw = json.loads(batch_row.receipt_json)
            raw["payload_secret"] = "DO_NOT_LEAK"
            raw["events"][0]["payload_secret"] = "DO_NOT_LEAK"
            batch_row.receipt_json = json.dumps(raw, ensure_ascii=False)
            session.add(batch_row)
            session.commit()
        cleaned = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)
        serialized = json.dumps(cleaned.as_dict(), ensure_ascii=False)
        self.assertNotIn("DO_NOT_LEAK", serialized)
        self.assertNotIn("payload_secret", serialized)

    def test_corrupt_stored_receipt_is_rejected_without_new_writes(self) -> None:
        prepared = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="corrupt-receipt")],
            batch_id="b-corrupt-receipt",
        )
        self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)
        with Session(self.engine) as session:
            row = session.exec(
                select(RuntimeLogBatch).where(
                    RuntimeLogBatch.batch_id == "b-corrupt-receipt"
                )
            ).first()
            assert row is not None
            row.receipt_json = '{"not":"a valid receipt"}'
            session.add(row)
            session.commit()
        self.assert_error(
            "stored_receipt_invalid",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared),
        )
        self.assertEqual(self.count_rows("runtime_log_batches"), 1)
        self.assertEqual(self.count_rows("runtime_log_events"), 1)
        self.assertEqual(self.source_row(self.scope).event_count, 1)

    def test_source_quota_and_utf8_bytes(self) -> None:
        # Bytes, not characters: a Chinese payload whose UTF-8 body exceeds the
        # limit must be rejected even when its character count is smaller.
        chinese = "中" * 100
        payload = {"message": chinese}
        text_bytes = len(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        self.assertGreater(text_bytes, 200)
        tight = RuntimeLogLimits(
            max_event_payload_bytes=200,
            max_batch_payload_bytes=4 * 1024 * 1024,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        core = self._core(limits=tight)
        prepared = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="utf8-log", payload=payload)],
            batch_id="b-utf8",
        )
        self.assert_error(
            "event_payload_too_large",
            lambda: core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared),
        )
        self.assertEqual(self.table_counts(), (1, 0, 0))

        # Event-count and total-batch limits.
        one_event = RuntimeLogLimits(
            max_events_per_batch=1,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        two_records = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="quota-1"),
                self.role_record(log_id="quota-2"),
            ],
            batch_id="b-two",
        )
        self.assert_error(
            "invalid_request",
            lambda: self._core(limits=one_event).ingest_batch(
                raw_api_key=_ROLE_KEY, batch=two_records
            ),
        )
        small_batch = RuntimeLogLimits(
            max_batch_payload_bytes=80,
            max_event_payload_bytes=80,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        wide = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="quota-3", payload={"m": "x" * 60}),
                self.role_record(log_id="quota-4", payload={"m": "y" * 60}),
            ],
            batch_id="b-wide",
        )
        self.assert_error(
            "batch_payload_too_large",
            lambda: self._core(limits=small_batch).ingest_batch(
                raw_api_key=_ROLE_KEY, batch=wide
            ),
        )
        self.assertEqual(self.table_counts(), (1, 0, 0))

    def test_per_source_batch_and_byte_quota_retained_across_revoke(self) -> None:
        first = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="quota-batch-1")],
            batch_id="b-quota-1",
        )
        self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=first)
        row = self.source_row(self.scope)
        used = row.bytes_used
        self.assertGreater(used, 0)

        batch_cap = RuntimeLogLimits(
            max_batches_per_source=1,
            max_bytes_per_source=self.limits.max_bytes_per_source,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        second = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="quota-batch-2")],
            batch_id="b-quota-2",
            batch_seq=2,
        )
        self.assert_error(
            "quota_source_batches",
            lambda: self._core(limits=batch_cap).ingest_batch(
                raw_api_key=_ROLE_KEY, batch=second
            ),
        )
        self.assertEqual(self.table_counts(), (1, 1, 1))

        byte_cap = RuntimeLogLimits(
            max_bytes_per_source=used,
            max_batches_per_source=5000,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        self.assert_error(
            "quota_source_bytes",
            lambda: self._core(limits=byte_cap).ingest_batch(
                raw_api_key=_ROLE_KEY, batch=second
            ),
        )

        revoked = self.core.revoke_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=1,
        )
        self.assertEqual(revoked.bytes_used, used)
        active = self.core.reactivate_source(
            raw_api_key=_MAINTAINER_KEY,
            scope=self.scope,
            expected_revision=revoked.revision,
        )
        self.assertEqual(active.bytes_used, used)
        self.assertEqual(active.batch_count, 1)
        self.assertEqual(active.event_count, 1)
        self.assertEqual(active.next_event_seq, 2)
        second_active = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="quota-batch-2")],
            batch_id="b-quota-2",
            batch_seq=2,
            revision=active.revision,
        )
        self.assert_error(
            "quota_source_bytes",
            lambda: self._core(limits=byte_cap).ingest_batch(
                raw_api_key=_ROLE_KEY, batch=second_active
            ),
        )

    def test_global_batch_and_byte_quota(self) -> None:
        first = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="global-1")],
            batch_id="b-global-1",
        )
        self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=first)
        used = self.source_row(self.scope).bytes_used

        global_batches = RuntimeLogLimits(
            max_batches_total=1,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        second = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="global-2")],
            batch_id="b-global-2",
            batch_seq=2,
        )
        self.assert_error(
            "quota_global_batches",
            lambda: self._core(limits=global_batches).ingest_batch(
                raw_api_key=_ROLE_KEY, batch=second
            ),
        )

        global_bytes = RuntimeLogLimits(
            max_bytes_total=used,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        self.assert_error(
            "quota_global_bytes",
            lambda: self._core(limits=global_bytes).ingest_batch(
                raw_api_key=_ROLE_KEY, batch=second
            ),
        )
        self.assertEqual(self.table_counts(), (1, 1, 1))

    def test_actual_default_event_count_and_byte_boundaries(self) -> None:
        # 200 events are accepted; 201 are rejected before any write.
        two_hundred = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id=f"bulk-{index}", payload={"index": index})
                for index in range(200)
            ],
            batch_id="b-200",
        )
        receipt = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=two_hundred)
        self.assertEqual(len(receipt.events), 200)
        self.assertEqual(self.source_row(self.scope).event_count, 200)
        self.assertEqual(self.source_row(self.scope).next_event_seq, 201)

        two_hundred_one = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id=f"too-many-{index}", payload={"index": index})
                for index in range(201)
            ],
            batch_id="b-201",
            batch_seq=2,
        )
        self.assert_error(
            "invalid_request",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=two_hundred_one
            ),
        )
        self.assertEqual(self.count_rows("runtime_log_batches"), 1)
        self.assertEqual(self.count_rows("runtime_log_events"), 200)

        # A single canonical payload over the real 256KiB event limit.
        huge_event = self.batch(
            scope=self.scope,
            records=[
                self.role_record(
                    log_id="too-large-event",
                    payload={"m": "x" * (256 * 1024)},
                )
            ],
            batch_id="b-huge-event",
            batch_seq=2,
        )
        self.assert_error(
            "event_payload_too_large",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=huge_event
            ),
        )

        # Actual canonical payload sum over the real 4MiB batch limit.
        huge_batch = self.batch(
            scope=self.scope,
            records=[
                self.role_record(
                    log_id=f"too-large-batch-{index}",
                    payload={"m": "y" * (250 * 1024)},
                )
                for index in range(17)
            ],
            batch_id="b-huge-batch",
            batch_seq=2,
        )
        self.assert_error(
            "batch_payload_too_large",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=huge_batch
            ),
        )
        self.assertEqual(self.count_rows("runtime_log_batches"), 1)
        self.assertEqual(self.count_rows("runtime_log_events"), 200)

    def test_duplicate_log_id_and_invalid_payloads(self) -> None:
        duplicate = self.batch(
            scope=self.scope,
            records=[
                self.role_record(log_id="dup"),
                self.role_record(log_id="dup", payload={"x": 2}),
            ],
            batch_id="b-dup",
        )
        self.assert_error(
            "duplicate_event_in_batch",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=duplicate),
        )

        deep_payload: dict[str, Any] = {}
        cursor = deep_payload
        for _ in range(40):
            child: dict[str, Any] = {}
            cursor["nested"] = child
            cursor = child
        for bad_payload in (
            [1, 2, 3],
            {"x": float("nan")},
            {"x": float("inf")},
            {1: "non-string-key"},
            deep_payload,
        ):
            prepared = self.batch(
                scope=self.scope,
                records=[self.role_record(log_id="bad", payload=bad_payload)],
                batch_id="b-bad",
            )
            self.assert_error(
                "invalid_payload",
                lambda prepared=prepared: self.core.ingest_batch(
                    raw_api_key=_ROLE_KEY, batch=prepared
                ),
            )

        empty = self.batch(
            scope=self.scope,
            records=[],
            batch_id="b-empty",
        )
        self.assert_error(
            "invalid_request",
            lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=empty),
        )
        overlong_log = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="l" * 201)],
            batch_id="b-long-log",
        )
        self.assert_error(
            "invalid_request",
            lambda: self.core.ingest_batch(
                raw_api_key=_ROLE_KEY, batch=overlong_log
            ),
        )

        for kwargs in (
            {"batch_seq": True},
            {"writer_run_id": "x" * 201},
            {"batch_id": "x" * 201},
            {"revision": True},
            {"projection_version": "other-projection-version"},
        ):
            prepared = self.batch(
                scope=self.scope,
                records=[self.role_record(log_id="input-bad")],
                **kwargs,
            )
            code = (
                "invalid_request"
                if kwargs.get("batch_seq") is True
                or "writer_run_id" in kwargs
                or "batch_id" in kwargs
                or "revision" in kwargs
                else "invalid_projection_version"
            )
            self.assert_error(
                code,
                lambda prepared=prepared: self.core.ingest_batch(
                    raw_api_key=_ROLE_KEY, batch=prepared
                ),
            )

        self.assertEqual(self.table_counts(), (1, 0, 0))


class ScopeAndUidTests(unittest.TestCase):
    def test_source_id_is_deterministic_and_scope_sensitive(self) -> None:
        role = RuntimeLogSourceScope(
            project_id="prj_demo",
            host="host-a",
            subject_kind="role",
            subject_id="agent:role",
        )
        same = RuntimeLogSourceScope(
            project_id="prj_demo",
            host="host-a",
            subject_kind="role",
            subject_id="agent:role",
        )
        self.assertEqual(role.source_id, same.source_id)
        seen = {role.source_id}
        for scope in (
            RuntimeLogSourceScope(
                project_id="prj_other",
                host="host-a",
                subject_kind="role",
                subject_id="agent:role",
            ),
            RuntimeLogSourceScope(
                project_id="prj_demo",
                host="host-b",
                subject_kind="role",
                subject_id="agent:role",
            ),
            RuntimeLogSourceScope(
                project_id="prj_demo",
                host="host-a",
                subject_kind="manager",
                subject_id="manager",
            ),
        ):
            self.assertNotIn(scope.source_id, seen)
            seen.add(scope.source_id)


class ReceiptIntegrityTests(CoreFixture):
    def setUp(self):
        super().setUp()
        self.seed_base()
        self.scope = self.role_scope()
        self.register(self.scope)
        self.prepared = self.batch(scope=self.scope, records=[self.role_record()])
        self.first = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=self.prepared)

    def corrupt_and_replay(self, mutate, *, change_refs=False):
        before = self.source_row(self.scope)
        with Session(self.engine) as session:
            row = session.exec(select(RuntimeLogBatch)).one()
            raw = json.loads(row.receipt_json)
            mutate(raw)
            row.receipt_json = json.dumps(raw)
            if change_refs:
                row.event_uids_json = json.dumps([x['event_uid'] for x in raw['events']])
            session.add(row)
            session.commit()
        self.assert_error('stored_receipt_invalid', lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=self.prepared))
        after = self.source_row(self.scope)
        self.assertEqual((before.bytes_used, before.next_event_seq), (after.bytes_used, after.next_event_seq))
        self.assertEqual(self.table_counts(), (1, 1, 1))

    def test_uid_and_reference_cannot_be_replaced_together(self):
        self.corrupt_and_replay(lambda raw: raw['events'][0].update(event_uid='rle_' + '0' * 64), change_refs=True)

    def test_log_id_must_match_immutable_event_identity(self):
        self.corrupt_and_replay(lambda raw: raw['events'][0].update(log_id='another-log'))

    def test_event_fingerprint_must_match_replayed_content(self):
        self.corrupt_and_replay(lambda raw: raw['events'][0].update(content_sha256='0' * 64))

    def test_role_receipt_cannot_change_into_manager_attribution(self):
        self.corrupt_and_replay(lambda raw: raw['events'][0].update(attribution_kind='manager', instance_id=None, launch_id=None, manager_run_id='other-manager'))

    def test_batch_first_received_time_must_match_durable_row(self):
        self.corrupt_and_replay(lambda raw: raw.update(received_at='2026-01-01T00:00:00+00:00'))

    def test_event_received_time_must_be_timezone_aware_datetime(self):
        self.corrupt_and_replay(lambda raw: raw['events'][0].update(received_at='not-a-datetime'))

    def test_event_first_received_time_must_match_existing_event_row(self):
        self.corrupt_and_replay(lambda raw: raw['events'][0].update(received_at='2026-01-01T00:00:00+00:00'))

    def test_event_sequence_cannot_point_outside_committed_source_range(self):
        self.corrupt_and_replay(lambda raw: raw['events'][0].update(received_seq=123456789))


class TransactionBoundaryTests(CoreFixture):
    def setUp(self):
        super().setUp()
        self.seed_base()
        self.scope = self.role_scope()
        self.register(self.scope)

    def test_busy_lock_wait_is_bounded_independently_of_injected_engine(self):
        prepared = self.batch(scope=self.scope, records=[self.role_record()])
        engine = self._make_engine(timeout=2)
        core = self._core(engine=engine)
        with self.engine.connect() as blocker:
            blocker.exec_driver_sql('BEGIN IMMEDIATE')
            start = time.monotonic()
            try:
                self.assert_error('database_busy', lambda: core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared))
            finally:
                elapsed = time.monotonic() - start
                blocker.rollback()
                engine.dispose()
        self.assertLess(elapsed, 1.5, f'core inherited engine lock wait: {elapsed:.3f}s')
        self.assertEqual(self.table_counts(), (1, 0, 0))

    def test_real_commit_failure_rolls_back_counters_rows_and_sequence(self):
        prepared = self.batch(scope=self.scope, records=[self.role_record()])
        before = self.source_row(self.scope)
        def fail_commit(connection):
            raise OSError('synthetic commit failure')
        event.listen(self.engine, 'commit', fail_commit)
        try:
            self.assert_error('database_error', lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared))
        finally:
            event.remove(self.engine, 'commit', fail_commit)
        self.assertEqual(self.table_counts(), (1, 0, 0))
        after = self.source_row(self.scope)
        self.assertEqual((before.bytes_used, before.next_event_seq), (after.bytes_used, after.next_event_seq))
        receipt = self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)
        self.assertEqual(receipt.events[0].received_seq, 1)

    def test_revoke_committed_after_prepare_is_seen_before_receive_commit(self):
        prepared = self.batch(scope=self.scope, records=[self.role_record()])
        original = self.core._prepare_batch
        def prepare_then_revoke(batch):
            draft = original(batch)
            self.core.revoke_source(raw_api_key=_MAINTAINER_KEY, scope=self.scope, expected_revision=1)
            return draft
        self.core._prepare_batch = prepare_then_revoke
        self.assert_error('source_revoked', lambda: self.core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared))
        self.assertEqual(self.table_counts(), (1, 0, 0))

    def test_transaction_budget_rejects_late_commit_and_restores_connection_settings(self):
        engine = self._make_engine(timeout=2)
        limits = replace(self.limits, transaction_timeout_seconds=0.05)
        def slow_clock():
            time.sleep(0.08)
            return self.clock()
        core = self._core(engine=engine, limits=limits, clock=slow_clock)
        before = self.source_row(self.scope)
        try:
            self.assert_error('transaction_timeout', lambda: core.ingest_batch(raw_api_key=_ROLE_KEY, batch=self.batch(scope=self.scope, records=[self.role_record()])))
            with engine.connect() as connection:
                self.assertEqual(connection.exec_driver_sql('PRAGMA busy_timeout').scalar_one(), 2000)
                # The expired transaction's progress callback must not remain
                # attached to this pooled connection for unrelated queries.
                total = connection.exec_driver_sql('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000) SELECT sum(x) FROM n').scalar_one()
                self.assertEqual(total, 5000050000)
        finally:
            engine.dispose()
        self.assertEqual(self.table_counts(), (1, 0, 0))
        after = self.source_row(self.scope)
        self.assertEqual((before.bytes_used, before.next_event_seq), (after.bytes_used, after.next_event_seq))

    def test_long_sql_is_interrupted_and_entire_batch_rolled_back(self):
        core = self._core(limits=replace(self.limits, transaction_timeout_seconds=0.05))
        fired = []
        def expensive_statement(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith('INSERT INTO runtime_log_batches'):
                fired.append(True)
                cursor.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<10000000) SELECT sum(x) FROM n')
        event.listen(self.engine, 'before_cursor_execute', expensive_statement)
        try:
            self.assert_error('transaction_timeout', lambda: core.ingest_batch(raw_api_key=_ROLE_KEY, batch=self.batch(scope=self.scope, records=[self.role_record()])))
        finally:
            event.remove(self.engine, 'before_cursor_execute', expensive_statement)
        self.assertTrue(fired)
        self.assertEqual(self.table_counts(), (1, 0, 0))
        self.assertEqual(self.source_row(self.scope).next_event_seq, 1)

    def test_transaction_budget_rejects_invalid_values(self):
        for value in [True, 0, -1, 6, 10**1000, float('nan'), float('inf'), '1']:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    replace(self.limits, transaction_timeout_seconds=value)




if __name__ == "__main__":
    unittest.main()
