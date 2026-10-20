"""B2a runtime log receive core: SQLite source registry and batch ingest.

Scope and safety boundary
=========================

This module is the **internal** transaction core for the three runtime-log
tables approved in the 283 correction.  It deliberately has no HTTP routes,
DTO serializers, query/export endpoints, configuration loader, filesystem
inbox/outbox, background worker or production database wiring.

The only accepted batch input is :class:`PreparedBatch`, whose records are
:class:`PreparedRecord` instances produced by a trusted, versioned server-side
projection adapter.  **HTTP must never pass arbitrary client JSON to this
module.**  B2b must first implement and verify the real writer-to-wire mapping
and the second projection gate; until then this core is off by default and is
only exercised against an explicitly injected isolated SQLite engine.  The
payload accepted here is therefore already-projected, bounded JSON, not an
untrusted raw JSONL record.  This module does not claim that the full writer
projection or external read safety has been implemented.

The core reads the existing ``members``/``projects``/``project_agents``/
``project_roles``/``agent_instances``/``role_service_launches`` facts directly
inside the same SQLite write transaction; it never accepts a cached principal
as a credential.  Raw API keys exist only in local variables for the duration
of a call.  They are never written to these three tables, receipts, source
snapshots or error messages.  The module never imports ``server.db`` or
``server.auth`` and has no import-time engine, table creation, directory
creation or configuration read.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import unicodedata
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

from sqlalchemy import event as sqlalchemy_event, func
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlmodel import Session, select

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


#: Version of the trusted projection shape.  B2b freezes the real writer
#: mapping against this value; a different version is a conflict, not silently
#: accepted.
PROJECTION_VERSION = "talk-runtime-log-projection-1"

#: Canonical batch-content schema (not an HTTP wire schema).
BATCH_SCHEMA = "talk-runtime-log-batch-1"

#: Persistent receipt schema.  It contains no payload, key, owner, path or SQL.
RECEIPT_SCHEMA = "talk-runtime-log-batch-receipt-1"

SUBJECT_ROLE = "role"
SUBJECT_MANAGER = "manager"
MANAGER_SUBJECT_ID = "manager"
MANAGER_EVENT_MEMBER_ID = "unknown"

ROLE_ATTRIBUTION_INSTANCE = "role_instance"
ROLE_ATTRIBUTION_LAUNCH = "role_launch"
MANAGER_ATTRIBUTION = "manager"

# Bounded metadata fields.  These are deliberately smaller than an arbitrary
# text column: they are identifiers, not message bodies.
MAX_SCOPE_FIELD_CHARS = 200
MAX_PROJECT_ID_CHARS = 200
MAX_HOST_CHARS = 200
MAX_WRITER_RUN_ID_CHARS = 200
MAX_BATCH_ID_CHARS = 200
MAX_LOG_ID_CHARS = 200
MAX_MANAGER_RUN_ID_CHARS = 200

# Bounded JSON payload shape.  The byte limits are the real product limits;
# depth/key/node limits stop pathological structures before json.dumps/allocation
# becomes unbounded.
MAX_PAYLOAD_DEPTH = 32
MAX_PAYLOAD_KEYS_PER_OBJECT = 512
MAX_PAYLOAD_NODES = 20000
MAX_PAYLOAD_KEY_CHARS = 256
MAX_PAYLOAD_STRING_CHARS = 256 * 1024

# Conservative fixed row/envelope overheads used by the logical byte budget.
# They cover bounded identifiers/timestamps and ordinary SQLite row overhead;
# payload bytes, stored receipt JSON and event-reference JSON are charged
# separately.  These are audit constants, not a promise about SQLite/WAL
# physical disk use.
SOURCE_ROW_OVERHEAD_BYTES = 2048
BATCH_ROW_OVERHEAD_BYTES = 1024
EVENT_ROW_OVERHEAD_BYTES = 2048

# Hard/upper contract values.  Injected limits may be lower for isolated
# tests or smaller deployments, but cannot silently raise the approved caps.
MAX_EVENTS_PER_BATCH_HARD = 200
MAX_BATCH_PAYLOAD_BYTES_HARD = 4 * 1024 * 1024
MAX_EVENT_PAYLOAD_BYTES_HARD = 256 * 1024
MAX_BATCHES_PER_SOURCE_HARD = 5000
MAX_BYTES_PER_SOURCE_HARD = 128 * 1024 * 1024

DEFAULT_MAX_SOURCES_TOTAL = 1000
DEFAULT_MAX_BATCHES_TOTAL = 20000
DEFAULT_MAX_BYTES_TOTAL = 512 * 1024 * 1024

SQLITE_SIGNED_INTEGER_MAX = 9223372036854775807


class RuntimeLogReceiveError(Exception):
    """Stable, safe failure from the receive core.

    ``status_code`` mirrors the intended HTTP status so B2b can map it without
    re-deriving semantics.  ``message`` is always a static, bounded description;
    it never contains an API key, payload, path, SQL statement or raw exception
    text.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = int(status_code)
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"{self.code}: {self.message}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "code": self.code,
            "message": self.message,
        }


# ── small validators ────────────────────────────────────────────────


def _fail(status_code: int, code: str, message: str) -> None:
    raise RuntimeLogReceiveError(status_code, code, message)


def _has_control_char(value: str) -> bool:
    # Cc/Cf/Cs/Co/Cn covers ASCII controls, format/zero-width characters,
    # surrogate code points, private-use and unassigned code points.  This is
    # intentionally stricter than a plain ord() < 0x20 test.
    return any(unicodedata.category(ch)[0] == "C" for ch in value)


def _validate_text(
    value: Any,
    field: str,
    *,
    max_chars: int,
    reject_path_separators: bool = False,
) -> str:
    if not isinstance(value, str):
        _fail(422, "invalid_request", f"{field} 必须是字符串")
    if not value:
        _fail(422, "invalid_request", f"{field} 不能为空")
    if len(value) > max_chars:
        _fail(422, "invalid_request", f"{field} 超出长度上限")
    if value.strip() != value:
        _fail(422, "invalid_request", f"{field} 不允许首尾空白")
    if _has_control_char(value):
        _fail(422, "invalid_request", f"{field} 不允许控制字符")
    if reject_path_separators and ("/" in value or "\\" in value):
        _fail(422, "invalid_scope", f"{field} 不允许客户端路径分隔符")
    return value


def _validate_optional_text(
    value: Any,
    field: str,
    *,
    max_chars: int,
) -> str | None:
    if value is None:
        return None
    return _validate_text(value, field, max_chars=max_chars)


def _validate_int(
    value: Any,
    field: str,
    *,
    minimum: int = 1,
    maximum: int = SQLITE_SIGNED_INTEGER_MAX,
) -> int:
    # type(...) is int deliberately rejects bool (``True`` is not batch_seq=1)
    # and every numeric/string coercion.
    if type(value) is not int:
        _fail(422, "invalid_request", f"{field} 必须是整数")
    if value < minimum or value > maximum:
        _fail(422, "invalid_request", f"{field} 超出允许范围")
    return value


def _validate_optional_int(value: Any, field: str, *, minimum: int = 1) -> int | None:
    if value is None:
        return None
    return _validate_int(value, field, minimum=minimum)


def _canonical_json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_scope_tuple(scope: "RuntimeLogSourceScope") -> list[str]:
    return [scope.project_id, scope.host, scope.subject_kind, scope.subject_id]


def _event_uid(source_id: str, writer_run_id: str, log_id: str) -> str:
    """Deterministic stable event identity.

    Batch id, ordinal, receipt time and payload are intentionally absent.
    """
    canonical = _canonical_json_text([source_id, writer_run_id, log_id])
    return "rle_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── limits and public value types ──────────────────────────────────


@dataclass(frozen=True)
class RuntimeLogLimits:
    """Injected logical limits for one receive core.

    Defaults are the approved B2a caps.  The source/global caps are configurable
    downward (or upward for the global caps) but the per-batch/source maxima are
    bounded by the approved contract.  Byte accounting uses canonical UTF-8
    payload bytes plus conservative fixed row/envelope overheads; it is a
    **logical budget**, not a guarantee about SQLite/WAL physical disk usage.
    """

    max_events_per_batch: int = MAX_EVENTS_PER_BATCH_HARD
    max_batch_payload_bytes: int = MAX_BATCH_PAYLOAD_BYTES_HARD
    max_event_payload_bytes: int = MAX_EVENT_PAYLOAD_BYTES_HARD
    max_batches_per_source: int = MAX_BATCHES_PER_SOURCE_HARD
    max_bytes_per_source: int = MAX_BYTES_PER_SOURCE_HARD
    max_sources_total: int = DEFAULT_MAX_SOURCES_TOTAL
    max_batches_total: int = DEFAULT_MAX_BATCHES_TOTAL
    max_bytes_total: int = DEFAULT_MAX_BYTES_TOTAL
    source_row_overhead_bytes: int = SOURCE_ROW_OVERHEAD_BYTES
    batch_row_overhead_bytes: int = BATCH_ROW_OVERHEAD_BYTES
    event_row_overhead_bytes: int = EVENT_ROW_OVERHEAD_BYTES
    # Wall-clock budget for lock acquisition and the write transaction.  The
    # injected engine's longer busy_timeout must not determine this budget.
    transaction_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        timeout = self.transaction_timeout_seconds
        if type(timeout) not in (int, float) or not 0 < timeout <= 5 or not math.isfinite(timeout):
            raise ValueError("transaction_timeout_seconds 必须在 0–5 秒内且大于 0")
        positive_fields = (
            "max_events_per_batch",
            "max_batch_payload_bytes",
            "max_event_payload_bytes",
            "max_batches_per_source",
            "max_bytes_per_source",
            "max_sources_total",
            "max_batches_total",
            "max_bytes_total",
        )
        for field_name in positive_fields:
            value = getattr(self, field_name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field_name} 必须是正整数")
        if self.max_events_per_batch > MAX_EVENTS_PER_BATCH_HARD:
            raise ValueError("max_events_per_batch 不能超过合同上限 200")
        if self.max_batch_payload_bytes > MAX_BATCH_PAYLOAD_BYTES_HARD:
            raise ValueError("max_batch_payload_bytes 不能超过合同上限 4MiB")
        if self.max_event_payload_bytes > MAX_EVENT_PAYLOAD_BYTES_HARD:
            raise ValueError("max_event_payload_bytes 不能超过合同上限 256KiB")
        if self.max_event_payload_bytes > self.max_batch_payload_bytes:
            raise ValueError("单条 payload 上限不能大于单批总量上限")
        if self.max_batches_per_source > MAX_BATCHES_PER_SOURCE_HARD:
            raise ValueError("max_batches_per_source 不能超过合同上限 5000")
        if self.max_bytes_per_source > MAX_BYTES_PER_SOURCE_HARD:
            raise ValueError("max_bytes_per_source 不能超过合同上限 128MiB")
        for field_name in (
            "source_row_overhead_bytes",
            "batch_row_overhead_bytes",
            "event_row_overhead_bytes",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} 必须是非负整数")


@dataclass(frozen=True)
class RuntimeLogSourceScope:
    """Immutable source scope.

    ``source_id`` is the deterministic hash of the canonical JSON tuple
    ``(project_id, host, subject_kind, subject_id)``.  For a role source,
    ``subject_id`` is the target agent member id; for a manager source it is the
    fixed literal ``manager``.  The scope is never a client filesystem path.
    """

    project_id: str
    host: str
    subject_kind: str
    subject_id: str

    def __post_init__(self) -> None:
        _validate_text(
            self.project_id,
            "project_id",
            max_chars=MAX_PROJECT_ID_CHARS,
            reject_path_separators=True,
        )
        _validate_text(
            self.host,
            "host",
            max_chars=MAX_HOST_CHARS,
            reject_path_separators=True,
        )
        if self.subject_kind not in (SUBJECT_ROLE, SUBJECT_MANAGER):
            _fail(422, "invalid_scope", "subject_kind 必须是 role 或 manager")
        _validate_text(
            self.subject_id,
            "subject_id",
            max_chars=MAX_SCOPE_FIELD_CHARS,
            reject_path_separators=True,
        )
        if self.subject_kind == SUBJECT_MANAGER and self.subject_id != MANAGER_SUBJECT_ID:
            _fail(422, "invalid_scope", "manager 来源的 subject_id 固定为 manager")
        if self.subject_kind == SUBJECT_ROLE and self.subject_id == MANAGER_SUBJECT_ID:
            _fail(422, "invalid_scope", "role 来源不能使用 manager 固定 subject_id")

    @property
    def source_id(self) -> str:
        canonical = _canonical_json_text(_canonical_scope_tuple(self))
        return "rls_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "host": self.host,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
        }


@dataclass(frozen=True)
class PreparedRecord:
    """One trusted, already-projected event.

    This type is intentionally internal to the server.  The fields are
    attribution metadata that the B2b adapter must derive from the real frozen
    writer record after applying its versioned projection.  ``payload`` is a
    JSON object, never a raw JSONL line or an arbitrary client object.
    """

    project_id: str
    host: str
    subject_kind: str
    member_id: str
    instance_id: str | None
    launch_id: str | None
    manager_run_id: str | None
    log_id: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class PreparedBatch:
    """Trusted batch passed by the future server-side projection adapter.

    The public HTTP layer must not construct this from an arbitrary request
    body.  ``source_revision`` is the exact revision the writer observed; it is
    rechecked inside the write transaction.
    """

    scope: RuntimeLogSourceScope
    source_revision: int
    writer_run_id: str
    batch_id: str
    batch_seq: int
    records: Sequence[PreparedRecord]
    projection_version: str = PROJECTION_VERSION


@dataclass(frozen=True)
class RuntimeLogEventReceipt:
    """Safe per-event receipt.  No payload, Key, owner or path is present."""

    event_uid: str
    log_id: str
    received_at: str
    received_seq: int
    content_sha256: str
    attribution_kind: str
    instance_id: str | None
    launch_id: str | None
    manager_run_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_uid": self.event_uid,
            "log_id": self.log_id,
            "received_at": self.received_at,
            "received_seq": self.received_seq,
            "content_sha256": self.content_sha256,
            "attribution_kind": self.attribution_kind,
            "instance_id": self.instance_id,
            "launch_id": self.launch_id,
            "manager_run_id": self.manager_run_id,
        }


@dataclass(frozen=True)
class RuntimeLogBatchReceipt:
    """Persistent accepted-batch receipt and its replayable events."""

    source_id: str
    project_id: str
    host: str
    subject_kind: str
    subject_id: str
    writer_run_id: str
    batch_id: str
    batch_seq: int
    content_sha256: str
    received_at: str
    accepted: bool
    replayed: bool
    events: tuple[RuntimeLogEventReceipt, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": RECEIPT_SCHEMA,
            "accepted": bool(self.accepted),
            "replayed": bool(self.replayed),
            "source_id": self.source_id,
            "project_id": self.project_id,
            "host": self.host,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "writer_run_id": self.writer_run_id,
            "batch_id": self.batch_id,
            "batch_seq": self.batch_seq,
            "content_sha256": self.content_sha256,
            "received_at": self.received_at,
            "events": [event.as_dict() for event in self.events],
        }


@dataclass(frozen=True)
class RuntimeLogSourceState:
    """Credential-free source view returned to the internal caller."""

    source_id: str
    project_id: str
    host: str
    subject_kind: str
    subject_id: str
    active: bool
    revision: int
    batch_count: int
    event_count: int
    bytes_used: int
    next_event_seq: int
    created_at: str
    updated_at: str
    revoked_at: str | None
    replayed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "project_id": self.project_id,
            "host": self.host,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "active": bool(self.active),
            "revision": self.revision,
            "batch_count": self.batch_count,
            "event_count": self.event_count,
            "bytes_used": self.bytes_used,
            "next_event_seq": self.next_event_seq,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revoked_at": self.revoked_at,
            "replayed": bool(self.replayed),
        }


# Internal immutable drafts.  Validation/canonicalization happens outside the
# write transaction; these snapshots are what enter it.
@dataclass(frozen=True)
class _EventDraft:
    log_id: str
    member_id: str
    instance_id: str | None
    launch_id: str | None
    manager_run_id: str | None
    attribution_kind: str
    payload_json: str
    payload_bytes: int
    content_sha256: str
    event_uid: str


@dataclass(frozen=True)
class _BatchDraft:
    scope: RuntimeLogSourceScope
    source_id: str
    source_revision: int
    writer_run_id: str
    batch_id: str
    batch_seq: int
    events: tuple[_EventDraft, ...]
    content_sha256: str
    total_payload_bytes: int


# ── the core ───────────────────────────────────────────────────────


class RuntimeLogReceiveCore:
    """Transactional source registry and batch receiver.

    Construction requires an explicit isolated SQLite ``engine`` (or an
    explicit ``session_factory`` returning a SQLAlchemy/SQLModel ``Session``),
    explicit ``limits`` and explicit ``clock``.  ``enabled`` defaults to
    ``False`` and every public method rejects before touching the database when
    the core is disabled.
    """

    def __init__(
        self,
        *,
        engine: Engine | None = None,
        session_factory: Callable[[], Session] | None = None,
        limits: RuntimeLogLimits,
        clock: Callable[[], datetime],
        enabled: bool = False,
    ) -> None:
        if (engine is None) == (session_factory is None):
            raise ValueError("必须且只能显式注入 engine 或 session_factory")
        if engine is not None and not isinstance(engine, Engine):
            raise ValueError("engine 必须是 SQLAlchemy Engine")
        if session_factory is not None and not callable(session_factory):
            raise ValueError("session_factory 必须可调用")
        if not isinstance(limits, RuntimeLogLimits):
            raise ValueError("limits 必须是 RuntimeLogLimits")
        if not callable(clock):
            raise ValueError("clock 必须可调用")
        if not isinstance(enabled, bool):
            raise ValueError("enabled 必须是 bool")
        self._engine = engine
        self._session_factory = session_factory
        self._limits = limits
        self._clock = clock
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def limits(self) -> RuntimeLogLimits:
        return self._limits

    # ── public source management ────────────────────────────────

    def register_source(
        self,
        *,
        raw_api_key: str,
        scope: RuntimeLogSourceScope,
        expected_revision: int | None = None,
    ) -> RuntimeLogSourceState:
        """Register a new role/manager source or idempotently replay it.

        Only a non-disabled human member that is the project's current
        ``maintainer_member_id`` may manage a source.  A role source additionally
        requires its target agent to exist and to be either an unarchived role
        or a legal legacy roster entry.  An archived ``ProjectRole`` is never
        bypassed through ``project_agents``.
        """
        self._require_enabled()
        if not isinstance(scope, RuntimeLogSourceScope):
            _fail(422, "invalid_scope", "scope 必须是 RuntimeLogSourceScope")
        # Revision 0 is accepted only as the explicit "source does not exist
        # yet" CAS value for a first registration.
        expected = _validate_optional_int(
            expected_revision, "expected_revision", minimum=0
        )

        with self._write_transaction() as session:
            caller = self._require_active_member(session, raw_api_key)
            project = self._require_project(session, scope.project_id)
            self._require_maintainer(caller, project)
            self._validate_subject_for_management(session, scope)

            source = self._get_source_for_scope(session, scope)
            if source is not None:
                if not bool(source.active):
                    _fail(409, "source_revoked", "来源已撤销，请走重新启用")
                if expected is not None and source.revision != expected:
                    _fail(409, "source_revision_conflict", "来源版本冲突")
                state = self._source_state(source, replayed=True)
                session.commit()
                return state

            if expected is not None and expected not in (0, 1):
                _fail(409, "source_revision_conflict", "来源尚不存在且版本不是 0/1")

            source_charge = self._source_charge(scope)
            self._check_new_source_quota(session, source_charge)

            now = self._clock_iso()
            row = RuntimeLogSource(
                source_id=scope.source_id,
                project_id=scope.project_id,
                host=scope.host,
                subject_kind=scope.subject_kind,
                subject_id=scope.subject_id,
                active=1,
                revision=1,
                batch_count=0,
                event_count=0,
                bytes_used=source_charge,
                next_event_seq=1,
                created_at=now,
                updated_at=now,
                revoked_at=None,
            )
            session.add(row)
            state = self._source_state(row, replayed=False)
            session.commit()
            return state

    def revoke_source(
        self,
        *,
        raw_api_key: str,
        scope: RuntimeLogSourceScope,
        expected_revision: int,
    ) -> RuntimeLogSourceState:
        """Revoke a source without deleting history or resetting counters.

        Revocation intentionally does not require the target role/roster to
        still be active: a maintainer must be able to retire a source after a
        role was archived.  The current maintainer Key and CAS revision are
        still rechecked in the write transaction.
        """
        self._require_enabled()
        if not isinstance(scope, RuntimeLogSourceScope):
            _fail(422, "invalid_scope", "scope 必须是 RuntimeLogSourceScope")
        expected = _validate_int(expected_revision, "expected_revision")

        with self._write_transaction() as session:
            caller = self._require_active_member(session, raw_api_key)
            project = self._require_project(session, scope.project_id)
            self._require_maintainer(caller, project)
            source = self._require_source_for_scope(session, scope)
            if source.revision != expected:
                _fail(409, "source_revision_conflict", "来源版本冲突")
            if not bool(source.active):
                state = self._source_state(source, replayed=True)
                session.commit()
                return state

            now = self._clock_iso()
            source.active = 0
            source.revision += 1
            source.revoked_at = now
            source.updated_at = now
            state = self._source_state(source, replayed=False)
            session.commit()
            return state

    def reactivate_source(
        self,
        *,
        raw_api_key: str,
        scope: RuntimeLogSourceScope,
        expected_revision: int,
    ) -> RuntimeLogSourceState:
        """Reactivate a revoked source while retaining all historical usage."""
        self._require_enabled()
        if not isinstance(scope, RuntimeLogSourceScope):
            _fail(422, "invalid_scope", "scope 必须是 RuntimeLogSourceScope")
        expected = _validate_int(expected_revision, "expected_revision")

        with self._write_transaction() as session:
            caller = self._require_active_member(session, raw_api_key)
            project = self._require_project(session, scope.project_id)
            self._require_maintainer(caller, project)
            self._validate_subject_for_management(session, scope)
            source = self._require_source_for_scope(session, scope)
            if source.revision != expected:
                _fail(409, "source_revision_conflict", "来源版本冲突")
            if bool(source.active):
                state = self._source_state(source, replayed=True)
                session.commit()
                return state

            now = self._clock_iso()
            source.active = 1
            source.revision += 1
            source.revoked_at = None
            source.updated_at = now
            state = self._source_state(source, replayed=False)
            session.commit()
            return state

    # ── public ingest ────────────────────────────────────────────

    def ingest_batch(
        self,
        *,
        raw_api_key: str,
        batch: PreparedBatch,
    ) -> RuntimeLogBatchReceipt:
        """Receive one trusted prepared batch atomically.

        Authorization, current source revision, role/roster/launch facts,
        batch/event dedupe, quota checks, sequence allocation and all three
        table writes happen inside one ``BEGIN IMMEDIATE`` SQLite write
        transaction.  The returned receipt exists only after a successful
        COMMIT; a lost response can be replayed with the same batch key.
        """
        self._require_enabled()
        draft = self._prepare_batch(batch)

        with self._write_transaction() as session:
            caller = self._require_active_member(session, raw_api_key)
            project = self._require_project(session, draft.scope.project_id)

            if draft.scope.subject_kind == SUBJECT_ROLE:
                if caller.kind != "agent" or caller.id != draft.scope.subject_id:
                    _fail(403, "not_source_role", "Key 不属于该来源角色")
                self._validate_role_target(session, draft.scope)
            else:
                self._require_maintainer(caller, project)

            source = self._require_source_for_scope(session, draft.scope)
            if not bool(source.active):
                _fail(409, "source_revoked", "来源已撤销")
            if source.revision != draft.source_revision:
                _fail(409, "source_revision_conflict", "来源版本冲突")

            # A pure replay of an already committed batch only needs current
            # authentication/source permission plus the stored receipt.  It
            # must survive later event-row deletion and must not re-check live
            # instance/launch rows for events that were already accepted.
            existing_batch = self._find_batch(session, draft)
            if existing_batch is not None:
                if existing_batch.content_sha256 != draft.content_sha256:
                    _fail(409, "batch_content_conflict", "批次键相同但内容不同")
                receipt = self._receipt_from_stored(existing_batch, source, draft, session)
                session.commit()
                return receipt

            # Recheck all identity facts inside the actual write transaction
            # after the source row was read; no cached principal is trusted.
            if draft.scope.subject_kind == SUBJECT_ROLE:
                self._validate_role_events(session, draft, source)
            else:
                self._validate_manager_events(draft, source)

            seq_batch = self._find_batch_by_seq(session, draft)
            if seq_batch is not None:
                _fail(409, "batch_seq_conflict", "同一 writer run 的 batch_seq 已被其它批次占用")

            reused: dict[str, RuntimeLogEvent] = {}
            new_events: list[_EventDraft] = []
            for event in draft.events:
                existing_event = self._find_event(session, draft, event)
                if existing_event is not None:
                    self._assert_same_event(existing_event, event)
                    if existing_event.event_uid != event.event_uid:
                        _fail(409, "storage_conflict", "存储事件标识不一致")
                    reused[event.log_id] = existing_event
                else:
                    new_events.append(event)

            now = self._clock_iso()
            next_seq = int(source.next_event_seq)
            if next_seq < 1:
                _fail(503, "storage_invalid", "来源序号状态无效")
            if new_events and next_seq + len(new_events) > SQLITE_SIGNED_INTEGER_MAX:
                _fail(507, "quota_source_events", "事件序号空间耗尽")

            event_receipts: list[RuntimeLogEventReceipt] = []
            new_event_seq: dict[str, int] = {}
            for event in draft.events:
                existing_event = reused.get(event.log_id)
                if existing_event is not None:
                    event_receipts.append(self._event_receipt_from_row(existing_event))
                    continue
                received_seq = next_seq + len(new_event_seq)
                new_event_seq[event.log_id] = received_seq
                event_receipts.append(
                    RuntimeLogEventReceipt(
                        event_uid=event.event_uid,
                        log_id=event.log_id,
                        received_at=now,
                        received_seq=received_seq,
                        content_sha256=event.content_sha256,
                        attribution_kind=event.attribution_kind,
                        instance_id=event.instance_id,
                        launch_id=event.launch_id,
                        manager_run_id=event.manager_run_id,
                    )
                )

            receipt = RuntimeLogBatchReceipt(
                source_id=source.source_id,
                project_id=draft.scope.project_id,
                host=draft.scope.host,
                subject_kind=draft.scope.subject_kind,
                subject_id=draft.scope.subject_id,
                writer_run_id=draft.writer_run_id,
                batch_id=draft.batch_id,
                batch_seq=draft.batch_seq,
                content_sha256=draft.content_sha256,
                received_at=now,
                accepted=True,
                replayed=False,
                events=tuple(event_receipts),
            )
            receipt_json = _canonical_json_text(receipt.as_dict())
            event_uids_json = _canonical_json_text(
                [item.event_uid for item in event_receipts]
            )
            charge = self._batch_charge(new_events, receipt_json, event_uids_json)
            self._check_batch_quota(session, source, charge)

            source.batch_count += 1
            source.event_count += len(new_events)
            source.bytes_used += charge
            source.next_event_seq = next_seq + len(new_events)
            source.updated_at = now

            session.add(
                RuntimeLogBatch(
                    source_id=source.source_id,
                    writer_run_id=draft.writer_run_id,
                    batch_id=draft.batch_id,
                    batch_seq=draft.batch_seq,
                    content_sha256=draft.content_sha256,
                    event_count=len(draft.events),
                    event_uids_json=event_uids_json,
                    receipt_json=receipt_json,
                    charged_bytes=charge,
                    received_at=now,
                )
            )
            for event in new_events:
                # All new rows in this batch share the transaction timestamp;
                # reused events keep their original first-commit timestamp.
                received_seq = new_event_seq[event.log_id]
                session.add(
                    RuntimeLogEvent(
                        event_uid=event.event_uid,
                        source_id=source.source_id,
                        writer_run_id=draft.writer_run_id,
                        log_id=event.log_id,
                        manager_run_id=event.manager_run_id,
                        member_id=event.member_id,
                        instance_id=event.instance_id,
                        launch_id=event.launch_id,
                        attribution_kind=event.attribution_kind,
                        payload_json=event.payload_json,
                        payload_bytes=event.payload_bytes,
                        content_sha256=event.content_sha256,
                        received_at=now,
                        received_seq=received_seq,
                    )
                )
            session.commit()
            # Receipt was fully built and committed above.  Only now may it be
            # returned to the caller.
            return receipt

    # ── transaction/session plumbing ─────────────────────────────

    def _new_session(self) -> Session:
        if self._session_factory is not None:
            session = self._session_factory()
            if not isinstance(session, Session):
                raise TypeError("session_factory 必须返回 SQLModel/SQLAlchemy Session")
            return session
        assert self._engine is not None
        return Session(self._engine)

    @contextmanager
    def _write_transaction(self) -> Iterator[Session]:
        session = self._new_session()
        owned_connection = None
        driver = None
        old_busy_timeout = None
        commit_guard = None
        deadline = time.monotonic() + self._limits.transaction_timeout_seconds
        try:
            self._ensure_sqlite(session)
            if session.in_transaction():
                _fail(503, "database_busy", "Session 已处于事务中，拒绝复用")
            bind = session.get_bind()
            if not isinstance(bind, Engine):
                _fail(503, "invalid_session_bind", "必须提供绑定 Engine 的全新 Session")
            # Keep the connection checked out through COMMIT and handler
            # cleanup.  Otherwise COMMIT could return it to the pool while a
            # temporary timeout/progress handler is still installed.
            owned_connection = bind.connect()
            session.bind = owned_connection
            connection = session.connection()
            driver = connection.connection.driver_connection
            if driver is None or bool(getattr(driver, "in_transaction", False)):
                _fail(503, "database_busy", "SQLite 连接已处于事务中，拒绝复用")
            old_busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            wait_ms = min(max(0, int(old_busy_timeout)), remaining_ms)
            connection.exec_driver_sql(f"PRAGMA busy_timeout={wait_ms}")
            driver.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)

            def check_commit_budget(_session: Session) -> None:
                if time.monotonic() >= deadline:
                    _fail(503, "transaction_timeout", "日志接收事务超时，请稍后重试")

            commit_guard = check_commit_budget
            sqlalchemy_event.listen(session, "before_commit", commit_guard)
            self._begin_immediate(session)
            check_commit_budget(session)
            yield session
        except RuntimeLogReceiveError:
            self._rollback_quietly(session)
            raise
        except (IntegrityError, sqlite3.IntegrityError):
            self._rollback_quietly(session)
            raise RuntimeLogReceiveError(
                409, "storage_conflict", "数据库唯一性或约束冲突"
            ) from None
        except (OperationalError, sqlite3.OperationalError) as exc:
            self._rollback_quietly(session)
            text = str(exc).lower()
            if "locked" in text or "busy" in text:
                raise RuntimeLogReceiveError(
                    503, "database_busy", "数据库忙，请稍后重试"
                ) from None
            if "interrupted" in text:
                raise RuntimeLogReceiveError(
                    503, "transaction_timeout", "日志接收事务超时，请稍后重试"
                ) from None
            raise RuntimeLogReceiveError(
                503, "database_error", "数据库操作失败"
            ) from None
        except (SQLAlchemyError, sqlite3.Error, OSError):
            self._rollback_quietly(session)
            raise RuntimeLogReceiveError(
                503, "database_error", "数据库操作失败"
            ) from None
        finally:
            if commit_guard is not None:
                sqlalchemy_event.remove(session, "before_commit", commit_guard)
            if driver is not None and old_busy_timeout is not None:
                try:
                    driver.set_progress_handler(None, 0)
                    driver.execute(f"PRAGMA busy_timeout={int(old_busy_timeout)}")
                except Exception:
                    # Never put a connection with uncertain temporary settings
                    # back in the pool for unrelated application operations.
                    if owned_connection is not None:
                        try:
                            owned_connection.invalidate()
                        except (SQLAlchemyError, OSError):
                            pass
            try:
                session.close()
            except Exception:
                # Closing a failed connection must not leak or mask the stable
                # error already selected above.
                pass
            if owned_connection is not None:
                try:
                    owned_connection.close()
                except (SQLAlchemyError, OSError):
                    pass

    @staticmethod
    def _rollback_quietly(session: Session) -> None:
        try:
            session.rollback()
        except Exception:
            pass

    @staticmethod
    def _begin_immediate(session: Session) -> None:
        """Take a real SQLite write lock before any authorization read.

        SQLAlchemy's logical transaction is not enough: pysqlite does not issue
        a real BEGIN before the first DML.  This mirrors the project's existing
        helper without importing ``server.db``.  No retry loop or sleep is
        performed; a busy database is surfaced as a stable 503.
        """
        connection = session.connection()
        driver = connection.connection.driver_connection
        if driver is not None and bool(getattr(driver, "in_transaction", False)):
            # Reusing an already-started transaction would make the following
            # authorization reads happen without a guaranteed write lock.  A
            # fresh session is required for the documented atomic boundary.
            _fail(503, "database_busy", "Session 已处于事务中，拒绝复用")
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    @staticmethod
    def _ensure_sqlite(session: Session) -> None:
        bind = session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", None) != "sqlite":
            _fail(503, "unsupported_database", "接收内核只支持 SQLite")

    def _require_enabled(self) -> None:
        if not self._enabled:
            _fail(503, "receive_core_disabled", "日志接收内核未启用")

    # ── authorization/fact rechecks ─────────────────────────────

    @staticmethod
    def _require_active_member(session: Session, raw_api_key: Any) -> Member:
        if not isinstance(raw_api_key, str) or not raw_api_key:
            _fail(401, "invalid_api_key", "无效的 API Key")
        if len(raw_api_key) > 4096:
            _fail(401, "invalid_api_key", "无效的 API Key")
        member = session.exec(
            select(Member).where(Member.api_key == raw_api_key)
        ).first()
        if member is None:
            _fail(401, "invalid_api_key", "无效的 API Key")
        if member.disabled_at is not None:
            _fail(403, "member_disabled", "成员已被禁用")
        return member

    @staticmethod
    def _require_project(session: Session, project_id: str) -> Project:
        project = session.get(Project, project_id)
        if project is None:
            _fail(404, "project_not_found", "项目不存在")
        return project

    @staticmethod
    def _require_maintainer(caller: Member, project: Project) -> None:
        if caller.kind != "human" or caller.id != project.maintainer_member_id:
            _fail(403, "not_maintainer", "只有项目维护者可以管理该来源")

    def _validate_subject_for_management(
        self, session: Session, scope: RuntimeLogSourceScope
    ) -> None:
        if scope.subject_kind == SUBJECT_MANAGER:
            return
        self._validate_role_target(session, scope)

    @staticmethod
    def _validate_role_target(session: Session, scope: RuntimeLogSourceScope) -> None:
        member = session.get(Member, scope.subject_id)
        if member is None:
            _fail(403, "target_not_agent", "目标角色成员不存在")
        if member.kind != "agent":
            _fail(403, "target_not_agent", "目标成员不是 agent")
        if member.disabled_at is not None:
            _fail(403, "role_member_disabled", "目标角色成员已被禁用")

        role = session.get(ProjectRole, (scope.project_id, scope.subject_id))
        if role is not None:
            if role.archived_at is not None:
                # Deliberately do not fall back to project_agents.  A historical
                # roster row must not resurrect an archived role.
                _fail(409, "role_archived", "目标项目角色已归档")
            return
        roster = session.get(ProjectAgent, (scope.project_id, scope.subject_id))
        if roster is None:
            _fail(403, "role_not_in_roster", "目标角色不在项目名册")

    @staticmethod
    def _get_source_for_scope(
        session: Session, scope: RuntimeLogSourceScope
    ) -> RuntimeLogSource | None:
        source = session.get(RuntimeLogSource, scope.source_id)
        if source is None:
            return None
        if (
            source.project_id != scope.project_id
            or source.host != scope.host
            or source.subject_kind != scope.subject_kind
            or source.subject_id != scope.subject_id
        ):
            _fail(409, "source_scope_conflict", "来源标识与存储范围不一致")
        return source

    def _require_source_for_scope(
        self, session: Session, scope: RuntimeLogSourceScope
    ) -> RuntimeLogSource:
        source = self._get_source_for_scope(session, scope)
        if source is None:
            _fail(404, "source_not_found", "来源未登记")
        return source

    # ── quota/accounting ────────────────────────────────────────

    def _source_charge(self, scope: RuntimeLogSourceScope) -> int:
        scope_bytes = len(
            _canonical_json_text(scope.as_dict()).encode("utf-8")
        )
        return (
            self._limits.source_row_overhead_bytes
            + scope_bytes
            + len(scope.source_id.encode("utf-8"))
        )

    def _check_new_source_quota(self, session: Session, source_charge: int) -> None:
        source_count = session.exec(
            select(func.count()).select_from(RuntimeLogSource)
        ).one()
        if int(source_count) >= self._limits.max_sources_total:
            _fail(507, "quota_source_count", "全局来源数量已达上限")
        if source_charge > self._limits.max_bytes_per_source:
            _fail(507, "quota_source_bytes", "来源计费空间不足")
        total_bytes = session.exec(
            select(func.coalesce(func.sum(RuntimeLogSource.bytes_used), 0))
        ).one()
        if int(total_bytes) + source_charge > self._limits.max_bytes_total:
            _fail(507, "quota_global_bytes", "全局日志字节预算不足")

    def _batch_charge(
        self,
        new_events: Sequence[_EventDraft],
        receipt_json: str,
        event_uids_json: str,
    ) -> int:
        # Event payload bytes and row overhead are charged only for genuinely
        # new events.  A repartitioned/reordered event reuses the original row
        # and is not billed again.  Every new batch still pays for its own
        # bounded receipt and event-reference envelope.
        event_bytes = sum(
            self._limits.event_row_overhead_bytes + event.payload_bytes
            for event in new_events
        )
        return (
            self._limits.batch_row_overhead_bytes
            + event_bytes
            + len(receipt_json.encode("utf-8"))
            + len(event_uids_json.encode("utf-8"))
        )

    def _check_batch_quota(
        self, session: Session, source: RuntimeLogSource, charge: int
    ) -> None:
        if int(source.batch_count) + 1 > self._limits.max_batches_per_source:
            _fail(507, "quota_source_batches", "来源批次数已达上限")
        if int(source.bytes_used) + charge > self._limits.max_bytes_per_source:
            _fail(507, "quota_source_bytes", "来源日志字节预算不足")

        batch_count = session.exec(
            select(func.count()).select_from(RuntimeLogBatch)
        ).one()
        if int(batch_count) + 1 > self._limits.max_batches_total:
            _fail(507, "quota_global_batches", "全局批次数已达上限")
        total_bytes = session.exec(
            select(func.coalesce(func.sum(RuntimeLogSource.bytes_used), 0))
        ).one()
        if int(total_bytes) + charge > self._limits.max_bytes_total:
            _fail(507, "quota_global_bytes", "全局日志字节预算不足")

    def _clock_iso(self) -> str:
        try:
            value = self._clock()
        except Exception:
            _fail(503, "clock_invalid", "服务端时钟不可用")
        if not isinstance(value, datetime):
            _fail(503, "clock_invalid", "服务端时钟返回无效时间")
        try:
            if value.tzinfo is None or value.utcoffset() is None:
                _fail(503, "clock_invalid", "服务端时钟必须带时区")
            # Preserve the actual timezone-aware wall-clock representation (not
            # only its instant): the injected service clock is authoritative.
            # No monotonicity is invented, so a wall-clock rollback is stored
            # exactly as returned.
            return value.isoformat()
        except RuntimeLogReceiveError:
            raise
        except Exception:
            _fail(503, "clock_invalid", "服务端时钟返回无效时间")
        raise AssertionError("unreachable")

    # ── batch preparation/validation (outside write txn) ───────

    def _prepare_batch(self, prepared: Any) -> _BatchDraft:
        if not isinstance(prepared, PreparedBatch):
            _fail(422, "invalid_request", "batch 必须是 PreparedBatch")
        if not isinstance(prepared.scope, RuntimeLogSourceScope):
            _fail(422, "invalid_scope", "scope 必须是 RuntimeLogSourceScope")
        if prepared.projection_version != PROJECTION_VERSION:
            _fail(422, "invalid_projection_version", "投影版本不受支持")
        source_revision = _validate_int(
            prepared.source_revision, "source_revision"
        )
        writer_run_id = _validate_text(
            prepared.writer_run_id,
            "writer_run_id",
            max_chars=MAX_WRITER_RUN_ID_CHARS,
        )
        batch_id = _validate_text(
            prepared.batch_id,
            "batch_id",
            max_chars=MAX_BATCH_ID_CHARS,
        )
        batch_seq = _validate_int(prepared.batch_seq, "batch_seq")

        if isinstance(prepared.records, (str, bytes)) or not isinstance(
            prepared.records, Sequence
        ):
            _fail(422, "invalid_request", "records 必须是记录序列")
        # Snapshot the sequence so a concurrent caller mutation cannot change
        # what was validated and what is later committed.
        records = tuple(prepared.records)
        if len(records) < 1:
            _fail(422, "invalid_request", "批次至少需要一条记录")
        if len(records) > self._limits.max_events_per_batch:
            _fail(422, "invalid_request", "批次事件数超过上限")

        scope = prepared.scope
        seen_log_ids: set[str] = set()
        drafts: list[_EventDraft] = []
        total_payload_bytes = 0
        for index, record in enumerate(records):
            if not isinstance(record, PreparedRecord):
                _fail(422, "invalid_request", "record 必须是 PreparedRecord")
            _validate_text(
                record.project_id,
                f"records[{index}].project_id",
                max_chars=MAX_PROJECT_ID_CHARS,
                reject_path_separators=True,
            )
            _validate_text(
                record.host,
                f"records[{index}].host",
                max_chars=MAX_HOST_CHARS,
                reject_path_separators=True,
            )
            if record.subject_kind not in (SUBJECT_ROLE, SUBJECT_MANAGER):
                _fail(422, "invalid_request", "record.subject_kind 无效")
            member_id = _validate_text(
                record.member_id,
                f"records[{index}].member_id",
                max_chars=MAX_SCOPE_FIELD_CHARS,
            )
            log_id = _validate_text(
                record.log_id,
                f"records[{index}].log_id",
                max_chars=MAX_LOG_ID_CHARS,
            )
            instance_id = _validate_optional_text(
                record.instance_id,
                f"records[{index}].instance_id",
                max_chars=MAX_SCOPE_FIELD_CHARS,
            )
            launch_id = _validate_optional_text(
                record.launch_id,
                f"records[{index}].launch_id",
                max_chars=MAX_SCOPE_FIELD_CHARS,
            )
            manager_run_id = _validate_optional_text(
                record.manager_run_id,
                f"records[{index}].manager_run_id",
                max_chars=MAX_MANAGER_RUN_ID_CHARS,
            )

            if (
                record.project_id != scope.project_id
                or record.host != scope.host
                or record.subject_kind != scope.subject_kind
            ):
                _fail(422, "invalid_attribution", "事件归因与来源不一致")

            if scope.subject_kind == SUBJECT_ROLE:
                if member_id != scope.subject_id:
                    _fail(422, "invalid_attribution", "角色事件 member 与来源不一致")
                if manager_run_id is not None:
                    _fail(422, "invalid_attribution", "角色来源不能上传 manager 事件")
                if instance_id is None:
                    _fail(422, "invalid_attribution", "角色事件必须有实例")
                attribution_kind = (
                    ROLE_ATTRIBUTION_LAUNCH
                    if launch_id is not None
                    else ROLE_ATTRIBUTION_INSTANCE
                )
            else:
                if member_id != MANAGER_EVENT_MEMBER_ID:
                    _fail(422, "invalid_attribution", "manager 事件的 member 固定为 unknown")
                if instance_id is not None or launch_id is not None:
                    _fail(422, "invalid_attribution", "manager 事件不能带角色实例或 launch")
                if manager_run_id is None:
                    _fail(422, "invalid_attribution", "manager 事件必须有 manager_run_id")
                self._validate_manager_payload_host(record.payload, scope.host)
                attribution_kind = MANAGER_ATTRIBUTION

            if log_id in seen_log_ids:
                _fail(409, "duplicate_event_in_batch", "同一批次包含重复 log_id")
            seen_log_ids.add(log_id)

            payload_json, payload_bytes, content_sha = self._canonicalize_payload(
                record.payload, index
            )
            total_payload_bytes += payload_bytes
            if total_payload_bytes > self._limits.max_batch_payload_bytes:
                _fail(413, "batch_payload_too_large", "批次规范化内容超出上限")
            drafts.append(
                _EventDraft(
                    log_id=log_id,
                    member_id=member_id,
                    instance_id=instance_id,
                    launch_id=launch_id,
                    manager_run_id=manager_run_id,
                    attribution_kind=attribution_kind,
                    payload_json=payload_json,
                    payload_bytes=payload_bytes,
                    content_sha256=content_sha,
                    event_uid=_event_uid(scope.source_id, writer_run_id, log_id),
                )
            )

        content_object = {
            "schema": BATCH_SCHEMA,
            "projection_version": prepared.projection_version,
            "source_id": scope.source_id,
            "writer_run_id": writer_run_id,
            "batch_id": batch_id,
            "batch_seq": batch_seq,
            "records": [
                {
                    "log_id": event.log_id,
                    "member_id": event.member_id,
                    "instance_id": event.instance_id,
                    "launch_id": event.launch_id,
                    "manager_run_id": event.manager_run_id,
                    "attribution_kind": event.attribution_kind,
                    "payload": json.loads(event.payload_json),
                }
                for event in drafts
            ],
        }
        content_text = _canonical_json_text(content_object)
        if len(content_text.encode("utf-8")) > self._limits.max_batch_payload_bytes:
            _fail(413, "batch_payload_too_large", "批次规范化内容超出上限")
        content_sha = _sha256_text(content_text)
        return _BatchDraft(
            scope=scope,
            source_id=scope.source_id,
            source_revision=source_revision,
            writer_run_id=writer_run_id,
            batch_id=batch_id,
            batch_seq=batch_seq,
            events=tuple(drafts),
            content_sha256=content_sha,
            total_payload_bytes=total_payload_bytes,
        )

    def _canonicalize_payload(
        self, payload: Any, index: int
    ) -> tuple[str, int, str]:
        if type(payload) is not dict:
            _fail(422, "invalid_payload", f"records[{index}].payload 必须是 JSON 对象")
        self._validate_json_shape(payload, index)
        try:
            text = _canonical_json_text(payload)
            encoded = text.encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            _fail(422, "invalid_payload", f"records[{index}].payload 不是合法 JSON")
        if len(encoded) > self._limits.max_event_payload_bytes:
            _fail(422, "event_payload_too_large", "单条 payload 超出上限")
        return text, len(encoded), _sha256_text(text)

    @staticmethod
    def _validate_json_shape(payload: dict[str, Any], index: int) -> None:
        nodes = 0
        stack: list[tuple[Any, int]] = [(payload, 0)]
        while stack:
            value, depth = stack.pop()
            nodes += 1
            if nodes > MAX_PAYLOAD_NODES:
                _fail(422, "invalid_payload", f"records[{index}].payload 结构过大")
            if isinstance(value, dict):
                if depth + 1 > MAX_PAYLOAD_DEPTH:
                    _fail(422, "invalid_payload", f"records[{index}].payload 嵌套过深")
                if len(value) > MAX_PAYLOAD_KEYS_PER_OBJECT:
                    _fail(422, "invalid_payload", f"records[{index}].payload 对象键过多")
                for key, child in value.items():
                    if type(key) is not str:
                        _fail(422, "invalid_payload", "payload 键必须是字符串")
                    if len(key) > MAX_PAYLOAD_KEY_CHARS or _has_control_char(key):
                        _fail(422, "invalid_payload", "payload 键不受支持")
                    stack.append((child, depth + 1))
            elif isinstance(value, list):
                if depth + 1 > MAX_PAYLOAD_DEPTH:
                    _fail(422, "invalid_payload", f"records[{index}].payload 嵌套过深")
                if len(value) > MAX_PAYLOAD_NODES:
                    _fail(422, "invalid_payload", "payload 数组过大")
                for child in value:
                    stack.append((child, depth + 1))
            elif isinstance(value, str):
                if len(value) > MAX_PAYLOAD_STRING_CHARS:
                    _fail(422, "invalid_payload", "payload 字符串过长")
            elif isinstance(value, bool) or value is None:
                continue
            elif isinstance(value, int):
                continue
            elif isinstance(value, float):
                if not math.isfinite(value):
                    _fail(422, "invalid_payload", "payload 不允许非有限数")
            else:
                _fail(422, "invalid_payload", "payload 含未知 JSON 类型")

    @staticmethod
    def _validate_manager_payload_host(payload: Any, source_host: str) -> None:
        if type(payload) is not dict:
            _fail(422, "invalid_payload", "manager payload 必须是 JSON 对象")
        manager_run = payload.get("manager_run")
        if type(manager_run) is not dict:
            _fail(422, "invalid_payload", "manager payload 缺少 manager_run")
        host = manager_run.get("host")
        if not isinstance(host, str) or host != source_host:
            _fail(422, "invalid_attribution", "manager_run.host 与来源不一致")

    # ── identity checks against existing tables ─────────────────

    def _validate_role_events(
        self, session: Session, draft: _BatchDraft, source: RuntimeLogSource
    ) -> None:
        for event in draft.events:
            instance = session.get(AgentInstance, event.instance_id)
            if instance is None:
                _fail(409, "instance_unknown", "角色事件实例不存在")
            if (
                instance.project_id != source.project_id
                or instance.member_id != source.subject_id
                or instance.host != source.host
            ):
                _fail(409, "instance_attribution_conflict", "实例归因与来源不一致")

            if event.launch_id is None:
                if instance.launch_id is not None:
                    _fail(409, "launch_attribution_conflict", "实例有关联 launch 但事件未提供")
                continue

            if instance.launch_id != event.launch_id:
                _fail(409, "launch_attribution_conflict", "实例 launch_id 与事件不一致")
            launch = session.get(RoleServiceLaunch, event.launch_id)
            if launch is None:
                _fail(409, "launch_unknown", "角色事件 launch 不存在")
            if launch.instance_id != instance.id:
                _fail(409, "launch_attribution_conflict", "launch.instance_id 与实例不一致")
            if (
                launch.project_id != source.project_id
                or launch.member_id != source.subject_id
                or launch.claim_host != source.host
            ):
                _fail(409, "launch_attribution_conflict", "launch 项目/member/host 与来源不一致")

    @staticmethod
    def _validate_manager_events(draft: _BatchDraft, source: RuntimeLogSource) -> None:
        # Shape checks were already performed outside the transaction.  The
        # manager host is rechecked from the frozen canonical payload inside the
        # write transaction as well.  There is deliberately no comparison
        # between manager_run_id and writer_run_id: they are independent IDs.
        for event in draft.events:
            if event.member_id != MANAGER_EVENT_MEMBER_ID:
                _fail(422, "invalid_attribution", "manager 事件的 member 固定为 unknown")
            if event.manager_run_id is None:
                _fail(422, "invalid_attribution", "manager 事件缺少 manager_run_id")
            if event.instance_id is not None or event.launch_id is not None:
                _fail(422, "invalid_attribution", "manager 事件不能带角色实例或 launch")
            try:
                payload = json.loads(event.payload_json)
            except (TypeError, ValueError, RecursionError):
                _fail(422, "invalid_payload", "manager payload 损坏")
            if type(payload) is not dict:
                _fail(422, "invalid_payload", "manager payload 必须是 JSON 对象")
            manager_run = payload.get("manager_run")
            if type(manager_run) is not dict or manager_run.get("host") != source.host:
                _fail(422, "invalid_attribution", "manager_run.host 与来源不一致")

    # ── row lookup/serialization helpers ────────────────────────

    @staticmethod
    def _find_batch(session: Session, draft: _BatchDraft) -> RuntimeLogBatch | None:
        return session.exec(
            select(RuntimeLogBatch).where(
                RuntimeLogBatch.source_id == draft.source_id,
                RuntimeLogBatch.writer_run_id == draft.writer_run_id,
                RuntimeLogBatch.batch_id == draft.batch_id,
            )
        ).first()

    @staticmethod
    def _find_batch_by_seq(
        session: Session, draft: _BatchDraft
    ) -> RuntimeLogBatch | None:
        return session.exec(
            select(RuntimeLogBatch).where(
                RuntimeLogBatch.source_id == draft.source_id,
                RuntimeLogBatch.writer_run_id == draft.writer_run_id,
                RuntimeLogBatch.batch_seq == draft.batch_seq,
            )
        ).first()

    @staticmethod
    def _find_event(
        session: Session, draft: _BatchDraft, event: _EventDraft
    ) -> RuntimeLogEvent | None:
        return session.exec(
            select(RuntimeLogEvent).where(
                RuntimeLogEvent.source_id == draft.source_id,
                RuntimeLogEvent.writer_run_id == draft.writer_run_id,
                RuntimeLogEvent.log_id == event.log_id,
            )
        ).first()

    @staticmethod
    def _assert_same_event(existing: RuntimeLogEvent, event: _EventDraft) -> None:
        same = (
            existing.payload_json == event.payload_json
            and existing.content_sha256 == event.content_sha256
            and existing.member_id == event.member_id
            and existing.instance_id == event.instance_id
            and existing.launch_id == event.launch_id
            and existing.manager_run_id == event.manager_run_id
            and existing.attribution_kind == event.attribution_kind
        )
        if not same:
            _fail(409, "event_content_conflict", "同一来源事件键的 payload 或归因不同")

    @staticmethod
    def _source_state(source: RuntimeLogSource, *, replayed: bool) -> RuntimeLogSourceState:
        return RuntimeLogSourceState(
            source_id=source.source_id,
            project_id=source.project_id,
            host=source.host,
            subject_kind=source.subject_kind,
            subject_id=source.subject_id,
            active=bool(source.active),
            revision=int(source.revision),
            batch_count=int(source.batch_count),
            event_count=int(source.event_count),
            bytes_used=int(source.bytes_used),
            next_event_seq=int(source.next_event_seq),
            created_at=source.created_at,
            updated_at=source.updated_at,
            revoked_at=source.revoked_at,
            replayed=replayed,
        )

    @staticmethod
    def _event_receipt_from_row(event: RuntimeLogEvent) -> RuntimeLogEventReceipt:
        return RuntimeLogEventReceipt(
            event_uid=event.event_uid,
            log_id=event.log_id,
            received_at=event.received_at,
            received_seq=int(event.received_seq),
            content_sha256=event.content_sha256,
            attribution_kind=event.attribution_kind,
            instance_id=event.instance_id,
            launch_id=event.launch_id,
            manager_run_id=event.manager_run_id,
        )

    def _receipt_from_stored(
        self, row: RuntimeLogBatch, source: RuntimeLogSource,
        draft: _BatchDraft, session: Session,
    ) -> RuntimeLogBatchReceipt:
        """Rebuild a sanitized replay receipt from the stored persistent JSON.

        Stored JSON is never returned as-is: only the known safe fields are
        copied, unknown keys are dropped, and the fixed envelope is checked
        against the batch row and the current source row.  This is the replay
        path after a lost response.
        """
        if not isinstance(row.receipt_json, str) or len(row.receipt_json) > MAX_BATCH_PAYLOAD_BYTES_HARD:
            _fail(503, "stored_receipt_invalid", "持久回执超出上限")
        try:
            raw = json.loads(row.receipt_json)
        except (TypeError, ValueError, RecursionError):
            _fail(503, "stored_receipt_invalid", "持久回执损坏")
        if type(raw) is not dict:
            _fail(503, "stored_receipt_invalid", "持久回执损坏")
        if raw.get("schema") != RECEIPT_SCHEMA or raw.get("accepted") is not True:
            _fail(503, "stored_receipt_invalid", "持久回执损坏")
        if (
            raw.get("source_id") != row.source_id
            or raw.get("writer_run_id") != row.writer_run_id
            or raw.get("batch_id") != row.batch_id
            or raw.get("batch_seq") != row.batch_seq
            or raw.get("content_sha256") != row.content_sha256
            or type(raw.get("batch_seq")) is not int
        ):
            _fail(503, "stored_receipt_invalid", "持久回执与批次行不一致")
        if (
            raw.get("project_id") != source.project_id
            or raw.get("host") != source.host
            or raw.get("subject_kind") != source.subject_kind
            or raw.get("subject_id") != source.subject_id
        ):
            _fail(503, "stored_receipt_invalid", "持久回执范围与来源不一致")
        batch_seq = raw["batch_seq"]
        batch_received_at = self._stored_receipt_datetime(raw.get("received_at"))
        if batch_received_at != row.received_at:
            _fail(503, "stored_receipt_invalid", "持久回执首次接收时间与批次不一致")
        raw_events = raw.get("events")
        if (not isinstance(raw_events, list) or not 1 <= len(raw_events) <= MAX_EVENTS_PER_BATCH_HARD
                or len(raw_events) != int(row.event_count) or len(raw_events) != len(draft.events)):
            _fail(503, "stored_receipt_invalid", "持久回执事件列表不完整")

        events: list[RuntimeLogEventReceipt] = []
        seen_uids: set[str] = set()
        seen_seqs: set[int] = set()
        for item, expected in zip(raw_events, draft.events):
            if type(item) is not dict:
                _fail(503, "stored_receipt_invalid", "持久回执损坏")
            event_uid = self._stored_receipt_text(
                item.get("event_uid"), "event_uid", 128
            )
            log_id = self._stored_receipt_text(item.get("log_id"), "log_id", MAX_LOG_ID_CHARS)
            event_received_at = self._stored_receipt_datetime(item.get("received_at"))
            content_sha = self._stored_receipt_text(
                item.get("content_sha256"), "content_sha256", 64
            )
            attribution = item.get("attribution_kind")
            received_seq = item.get("received_seq")
            if (
                len(content_sha) != 64
                or any(ch not in "0123456789abcdef" for ch in content_sha)
                or attribution not in (
                    ROLE_ATTRIBUTION_INSTANCE,
                    ROLE_ATTRIBUTION_LAUNCH,
                    MANAGER_ATTRIBUTION,
                )
                or type(received_seq) is not int
                or received_seq < 1
                or received_seq >= int(source.next_event_seq)
            ):
                _fail(503, "stored_receipt_invalid", "持久回执事件字段损坏")
            if event_uid in seen_uids or received_seq in seen_seqs:
                _fail(503, "stored_receipt_invalid", "持久回执事件重复")
            seen_uids.add(event_uid)
            seen_seqs.add(received_seq)
            # The immutable replay input already matched the batch SHA.  Bind
            # each receipt to that exact ordered event, not just to another
            # mutable JSON reference list in the same row.
            if (event_uid != expected.event_uid or log_id != expected.log_id
                    or content_sha != expected.content_sha256
                    or attribution != expected.attribution_kind
                    or item.get("instance_id") != expected.instance_id
                    or item.get("launch_id") != expected.launch_id
                    or item.get("manager_run_id") != expected.manager_run_id):
                _fail(503, "stored_receipt_invalid", "持久回执事件与原批次内容不一致")
            events.append(
                RuntimeLogEventReceipt(
                    event_uid=event_uid,
                    log_id=log_id,
                    received_at=event_received_at,
                    received_seq=received_seq,
                    content_sha256=content_sha,
                    attribution_kind=attribution,
                    instance_id=self._optional_receipt_text(
                        item.get("instance_id"), MAX_SCOPE_FIELD_CHARS
                    ),
                    launch_id=self._optional_receipt_text(
                        item.get("launch_id"), MAX_SCOPE_FIELD_CHARS
                    ),
                    manager_run_id=self._optional_receipt_text(
                        item.get("manager_run_id"), MAX_MANAGER_RUN_ID_CHARS
                    ),
                )
            )
            stored_event = self._find_event(session, draft, expected)
            if stored_event is not None and events[-1] != self._event_receipt_from_row(stored_event):
                _fail(503, "stored_receipt_invalid", "持久回执与已提交事件不一致")
        try:
            refs = json.loads(row.event_uids_json)
        except (TypeError, ValueError, RecursionError):
            _fail(503, "stored_receipt_invalid", "持久回执事件引用损坏")
        if not isinstance(refs, list) or refs != [event.event_uid for event in events]:
            _fail(503, "stored_receipt_invalid", "持久回执事件引用不一致")

        return RuntimeLogBatchReceipt(
            source_id=row.source_id,
            project_id=raw["project_id"],
            host=raw["host"],
            subject_kind=raw["subject_kind"],
            subject_id=raw["subject_id"],
            writer_run_id=row.writer_run_id,
            batch_id=row.batch_id,
            batch_seq=batch_seq,
            content_sha256=row.content_sha256,
            received_at=batch_received_at,
            accepted=True,
            replayed=True,
            events=tuple(events),
        )

    @staticmethod
    def _stored_receipt_datetime(value: Any) -> str:
        value = RuntimeLogReceiveCore._stored_receipt_text(value, "received_at", 64)
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("missing timezone")
        except (TypeError, ValueError, OverflowError):
            _fail(503, "stored_receipt_invalid", "持久回执接收时间无效")
        return value

    @staticmethod
    def _stored_receipt_text(value: Any, field: str, max_chars: int) -> str:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > max_chars
            or _has_control_char(value)
        ):
            _fail(503, "stored_receipt_invalid", f"持久回执 {field} 字段损坏")
        return value

    @classmethod
    def _optional_receipt_text(
        cls, value: Any, max_chars: int
    ) -> str | None:
        if value is None:
            return None
        return cls._stored_receipt_text(value, "optional", max_chars)
