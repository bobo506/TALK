"""执行会话窗口的受限私有 sidecar：通道锁、窗口计数、快照与 ACK 审计。

设计约束（292）：

- 只使用本功能自己的 SQLite 文件（``$TALK_EXECUTION_SESSION_STORE`` 或
  ``<project>/.talk/execution-session-store.sqlite3``），不直接修改生产 TALK DB；
- 所有跨进程状态变更走 ``BEGIN IMMEDIATE`` + 行版本 CAS；通道锁有租约，
  进程崩溃后会自然过期，不把残留 owner 当成当前写入者；
- 只保存最小事实：native session id/generation/窗口计数/已核快照/送达回执/
  决策摘要；不保存 TALK Key、claim token、完整配置或会话正文；
- ``count_state`` 仍由 ``bridges.execution_sessions`` 纯内核生成与归并；本模块
  只做持久化和原子比较，不复制另一套 60%/10 次规则。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

STORE_SCHEMA = "talk-execution-session-store-1"
STORE_VERSION = 1
WINDOW_ORIGIN = "talk_execution_runner"
STORE_FILE_ENV = "TALK_EXECUTION_SESSION_STORE"

_ACTIVE = "active"
_PENDING_FIRST = "pending_first_turn"
_ROTATED = "rotated"
_TAINTED = "tainted"
_STATUSES = frozenset((_ACTIVE, _PENDING_FIRST, _ROTATED, _TAINTED))


class ExecutionSessionStoreError(RuntimeError):
    """sidecar 的稳定错误；不含正文/凭据。"""


class ChannelBusy(ExecutionSessionStoreError):
    pass


class StoreConflict(ExecutionSessionStoreError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def json_sha256(value: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def resolve_store_path(project_root: Path, *, override: str | None = None) -> Path:
    explicit = (override or os.environ.get(STORE_FILE_ENV) or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise ExecutionSessionStoreError(
                f"{STORE_FILE_ENV} 必须是绝对路径"
            )
        return path
    root = Path(project_root).expanduser().resolve()
    return root / ".talk" / "execution-session-store.sqlite3"


class ExecutionSessionStore:
    """一个进程内可重复使用的 sidecar 句柄（每次操作单独连接）。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    # ------------------------------------------------------------------
    # connection / schema
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path),
            timeout=10.0,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS channels (
                    scope_key TEXT PRIMARY KEY,
                    owner_token TEXT NOT NULL,
                    owner_pid INTEGER,
                    state TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS windows (
                    window_id TEXT PRIMARY KEY,
                    scope_key TEXT NOT NULL,
                    scope_fingerprint TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    continuity_key TEXT NOT NULL,
                    base_task_id INTEGER,
                    base_contract_version TEXT,
                    base_contract_sha256 TEXT,
                    native_session_id TEXT,
                    session_generation INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    config_inventory_hash TEXT,
                    count_state_json TEXT,
                    last_snapshot_json TEXT,
                    last_delivery_id TEXT,
                    taint_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    row_revision INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS ix_windows_scope
                    ON windows(scope_fingerprint, status);
                CREATE TABLE IF NOT EXISTS deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    window_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    execution_id TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL,
                    native_session_id TEXT,
                    session_generation INTEGER,
                    session_revision TEXT,
                    outcome TEXT NOT NULL,
                    turn_outcome TEXT,
                    counted INTEGER NOT NULL DEFAULT 0,
                    ack_json TEXT NOT NULL,
                    snapshot_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(task_id, attempt, execution_id)
                );
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    window_id TEXT NOT NULL,
                    native_session_id TEXT,
                    session_generation INTEGER,
                    session_revision TEXT,
                    used_tokens INTEGER,
                    capacity_tokens INTEGER,
                    source TEXT,
                    sampled_at TEXT,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    execution_id TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL,
                    window_id TEXT NOT NULL,
                    native_session_id TEXT NOT NULL,
                    channel_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, attempt)
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema', ?)",
                (STORE_SCHEMA,),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('version', ?)",
                (str(STORE_VERSION),),
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # channel lock / CAS
    # ------------------------------------------------------------------
    def acquire_channel(
        self,
        *,
        scope_key: str,
        owner_token: str,
        owner_pid: int | None,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> dict:
        if ttl_seconds < 1 or ttl_seconds > 86_400:
            raise ExecutionSessionStoreError("channel ttl_seconds 必须在 1..86400")
        current = now or _utc_now()
        expires = _iso(current)
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE scope_key = ?", (scope_key,)
            ).fetchone()
            if row is not None:
                existing_expiry = _parse_iso(row["lease_expires_at"])
                if (
                    row["owner_token"] != owner_token
                    and existing_expiry is not None
                    and existing_expiry > current
                ):
                    raise ChannelBusy("channel_busy")
                if row["owner_token"] != owner_token and conn.execute(
                    "SELECT 1 FROM attempts WHERE channel_key=? AND state='started' LIMIT 1",
                    (scope_key,),
                ).fetchone() is not None:
                    # A dead/expired parent does not prove its native writer has exited.
                    raise ChannelBusy("channel_writer_unconfirmed")
            lease_expires = _iso(
                current.replace(microsecond=current.microsecond)
            )
            from datetime import timedelta

            lease_expires = _iso(current + timedelta(seconds=ttl_seconds))
            conn.execute(
                """
                INSERT INTO channels(scope_key, owner_token, owner_pid, state,
                                     lease_expires_at, acquired_at, updated_at)
                VALUES(?, ?, ?, 'held', ?, ?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET
                    owner_token=excluded.owner_token,
                    owner_pid=excluded.owner_pid,
                    state='held',
                    lease_expires_at=excluded.lease_expires_at,
                    acquired_at=excluded.acquired_at,
                    updated_at=excluded.updated_at
                """,
                (
                    scope_key,
                    owner_token,
                    owner_pid,
                    lease_expires,
                    _iso(current),
                    _iso(current),
                ),
            )
            return {"status": "acquired", "owner_token": owner_token, "lease_expires_at": lease_expires}

    def renew_channel(
        self,
        *,
        scope_key: str,
        owner_token: str,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> dict:
        from datetime import timedelta

        current = now or _utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE scope_key = ?", (scope_key,)
            ).fetchone()
            if row is None or row["owner_token"] != owner_token:
                raise StoreConflict("channel_owner_mismatch")
            conn.execute(
                "UPDATE channels SET lease_expires_at=?, updated_at=? WHERE scope_key=?",
                (
                    _iso(current + timedelta(seconds=ttl_seconds)),
                    _iso(current),
                    scope_key,
                ),
            )
            return {"status": "renewed"}

    def release_channel(
        self, *, scope_key: str, owner_token: str, now: datetime | None = None
    ) -> dict:
        current = now or _utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE scope_key = ?", (scope_key,)
            ).fetchone()
            if row is None:
                return {"status": "absent"}
            if row["owner_token"] != owner_token:
                return {"status": "not_owner"}
            conn.execute(
                "DELETE FROM channels WHERE scope_key = ?", (scope_key,)
            )
            return {"status": "released"}

    # ------------------------------------------------------------------
    # windows
    # ------------------------------------------------------------------
    def assert_channel(self, *, scope_key: str, owner_token: str) -> None:
        with self._read() as conn:
            row=conn.execute("SELECT owner_token,lease_expires_at FROM channels WHERE scope_key=?",(scope_key,)).fetchone()
        if row is None or row['owner_token'] != owner_token:
            raise StoreConflict('channel_owner_mismatch')
        expiry=_parse_iso(row['lease_expires_at'])
        if expiry is None or expiry <= _utc_now():
            raise StoreConflict('channel_lease_expired')

    def get_attempt(self, task_id: int, attempt: int) -> dict | None:
        with self._read() as conn:
            row=conn.execute('SELECT * FROM attempts WHERE task_id=? AND attempt=?',(str(task_id),attempt)).fetchone()
        return dict(row) if row is not None else None

    def reserve_attempt(self, *, task_id: int, attempt: int, execution_id: str,
                        body_sha256: str, window_id: str, native_session_id: str | None,
                        channel_key: str, owner_token: str) -> None:
        self.assert_channel(scope_key=channel_key, owner_token=owner_token)
        with self._transaction() as conn:
            try:
                conn.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,\'started\',?)',
                    (str(task_id),attempt,execution_id,body_sha256,window_id,native_session_id or '',channel_key,_iso(_utc_now())))
            except sqlite3.IntegrityError as exc:
                raise StoreConflict('task_attempt_already_started') from exc

    def bind_pending_native_session(self, *, task_id: int, attempt: int, window_id: str,
                                    execution_id: str, native_session_id: str,
                                    channel_key: str, owner_token: str) -> None:
        """CLI 首轮结束后绑定真正原生 ID；只允许本人 pending 尝试的一次 CAS。"""
        if not native_session_id:
            raise StoreConflict('native_session_id_required')
        self.assert_channel(scope_key=channel_key, owner_token=owner_token)
        with self._transaction() as conn:
            lease = conn.execute('SELECT owner_token,lease_expires_at FROM channels WHERE scope_key=?',
                (channel_key,)).fetchone()
            expiry = _parse_iso(lease['lease_expires_at']) if lease is not None else None
            if lease is None or lease['owner_token'] != owner_token or expiry is None or expiry <= _utc_now():
                raise StoreConflict('channel_owner_mismatch')
            window = conn.execute('SELECT status,native_session_id,scope_json FROM windows WHERE window_id=?',
                (window_id,)).fetchone()
            if window is None or window['status'] != _PENDING_FIRST or window['native_session_id'] is not None:
                raise StoreConflict('pending_window_conflict')
            scope = json.loads(window['scope_json'])
            expected_channel = '|'.join(str(scope.get(k) or '') for k in
                ('project_id','target_member_id','native_home_namespace','runner_id'))
            if channel_key != expected_channel:
                raise StoreConflict('pending_channel_conflict')
            result = conn.execute('''UPDATE attempts SET native_session_id=?
                WHERE task_id=? AND attempt=? AND window_id=? AND execution_id=?
                AND channel_key=? AND state='started' AND native_session_id='' ''',
                (native_session_id,str(task_id),attempt,window_id,execution_id,channel_key))
            if result.rowcount != 1:
                raise StoreConflict('pending_attempt_conflict')

    def commit_confirmed_delivery(self, *, window_id: str, expected_row_revision: int,
                                 native_session_id: str, count_state: Mapping[str, Any],
                                 snapshot: Mapping[str, Any] | None, receipt: Mapping[str, Any],
                                 ack: Mapping[str, Any], inventory_hash: str | None,
                                 first_turn: bool, channel_key: str, owner_token: str) -> None:
        self.assert_channel(scope_key=channel_key, owner_token=owner_token)
        with self._transaction() as conn:
            attempt=conn.execute('SELECT * FROM attempts WHERE task_id=? AND attempt=?',
                (str(receipt['task_id']),receipt['attempt'])).fetchone()
            if attempt is None or any(attempt[k] != receipt[k] for k in ('execution_id','body_sha256','native_session_id')):
                raise StoreConflict('attempt_receipt_mismatch')
            if attempt['window_id'] != window_id or attempt['state'] != 'started':
                raise StoreConflict('attempt_state_conflict')
            self.record_delivery(window_id=window_id, receipt=receipt, ack=ack,
                snapshot=snapshot,counted=True,_conn=conn)
            result=conn.execute('''UPDATE windows SET native_session_id=?,status=?,count_state_json=?,
                last_snapshot_json=?,last_delivery_id=?,config_inventory_hash=?,updated_at=?,row_revision=row_revision+1
                WHERE window_id=? AND row_revision=? AND status=?''',
                (native_session_id,_ACTIVE,canonical_json(dict(count_state)),
                 canonical_json(dict(snapshot)) if snapshot is not None else None,receipt['delivery_id'],
                 inventory_hash,_iso(_utc_now()),window_id,expected_row_revision,
                 _PENDING_FIRST if first_turn else _ACTIVE))
            if result.rowcount != 1:
                raise StoreConflict('window_cas_conflict')
            conn.execute("UPDATE attempts SET state='confirmed' WHERE task_id=? AND attempt=?",
                (str(receipt['task_id']),receipt['attempt']))

    def get_active_window(self, scope_fingerprint: str) -> Optional[dict]:
        with self._read() as conn:
            row = conn.execute(
                """
                SELECT * FROM windows
                WHERE scope_fingerprint = ? AND status = ?
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (scope_fingerprint, _ACTIVE),
            ).fetchone()
        return _window_row(row) if row is not None else None

    def get_window(self, window_id: str) -> Optional[dict]:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM windows WHERE window_id = ?", (window_id,)
            ).fetchone()
        return _window_row(row) if row is not None else None

    def create_window(
        self,
        *,
        scope: Mapping[str, Any],
        scope_fingerprint: str,
        native_session_id: str | None,
        session_generation: int,
        base_task_id: int | None,
        config_inventory_hash: str | None = None,
        now: datetime | None = None,
    ) -> dict:
        current = now or _utc_now()
        window_id = f"win-{uuid.uuid4().hex}"
        with self._transaction() as conn:
            conn.execute(
                """
                UPDATE windows SET status = ?, updated_at = ?, row_revision = row_revision + 1
                WHERE scope_fingerprint = ? AND status IN (?, ?)
                """,
                (_ROTATED, _iso(current), scope_fingerprint, _ACTIVE, _PENDING_FIRST),
            )
            conn.execute(
                """
                INSERT INTO windows(
                    window_id, scope_key, scope_fingerprint, scope_json,
                    continuity_key, base_task_id, base_contract_version,
                    base_contract_sha256, native_session_id, session_generation,
                    status, provenance, config_inventory_hash,
                    count_state_json, last_snapshot_json, created_at, updated_at,
                    row_revision
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, 1)
                """,
                (
                    window_id,
                    f"{scope['project_id']}|{scope['target_member_id']}",
                    scope_fingerprint,
                    canonical_json(dict(scope)),
                    str(scope["continuity_key"]),
                    base_task_id,
                    str(scope["base_contract_version"]),
                    str(scope["base_contract_sha256"]),
                    native_session_id,
                    session_generation,
                    _ACTIVE if native_session_id else _PENDING_FIRST,
                    WINDOW_ORIGIN,
                    config_inventory_hash,
                    _iso(current),
                    _iso(current),
                ),
            )
        return self.get_window(window_id) or {}

    def rotate_window(
        self,
        *,
        window_id: str,
        reason: str,
        now: datetime | None = None,
    ) -> dict:
        current = now or _utc_now()
        with self._transaction() as conn:
            conn.execute(
                """
                UPDATE windows SET status=?, taint_reason=?, updated_at=?,
                    row_revision=row_revision+1
                WHERE window_id=? AND status IN (?, ?)
                """,
                (_ROTATED, reason[:120], _iso(current), window_id, _ACTIVE, _PENDING_FIRST),
            )
        return self.get_window(window_id) or {}

    def taint_window(
        self,
        *,
        window_id: str,
        reason: str,
        now: datetime | None = None,
    ) -> dict:
        current = now or _utc_now()
        with self._transaction() as conn:
            conn.execute(
                """
                UPDATE windows SET status=?, taint_reason=?, updated_at=?,
                    row_revision=row_revision+1
                WHERE window_id=? AND status != ?
                """,
                (_TAINTED, reason[:120], _iso(current), window_id, _ROTATED),
            )
        return self.get_window(window_id) or {}

    def finalize_first_delivery(
        self,
        *,
        window_id: str,
        expected_row_revision: int,
        native_session_id: str,
        count_state: Mapping[str, Any],
        snapshot: Mapping[str, Any] | None,
        delivery_id: str,
        now: datetime | None = None,
    ) -> dict:
        current = now or _utc_now()
        with self._transaction() as conn:
            result = conn.execute(
                """
                UPDATE windows SET native_session_id=?, status=?, count_state_json=?,
                    last_snapshot_json=?, last_delivery_id=?, updated_at=?,
                    row_revision=row_revision+1
                WHERE window_id=? AND row_revision=? AND status=?
                """,
                (
                    native_session_id,
                    _ACTIVE,
                    canonical_json(dict(count_state)),
                    canonical_json(dict(snapshot)) if snapshot is not None else None,
                    delivery_id,
                    _iso(current),
                    window_id,
                    expected_row_revision,
                    _PENDING_FIRST,
                ),
            )
            if result.rowcount != 1:
                raise StoreConflict("window_cas_conflict")
        return self.get_window(window_id) or {}

    def update_after_delivery(
        self,
        *,
        window_id: str,
        expected_row_revision: int,
        count_state: Mapping[str, Any],
        snapshot: Mapping[str, Any] | None,
        delivery_id: str,
        now: datetime | None = None,
    ) -> dict:
        current = now or _utc_now()
        with self._transaction() as conn:
            result = conn.execute(
                """
                UPDATE windows SET count_state_json=?, last_snapshot_json=?,
                    last_delivery_id=?, updated_at=?, row_revision=row_revision+1
                WHERE window_id=? AND row_revision=? AND status=?
                """,
                (
                    canonical_json(dict(count_state)),
                    canonical_json(dict(snapshot)) if snapshot is not None else None,
                    delivery_id,
                    _iso(current),
                    window_id,
                    expected_row_revision,
                    _ACTIVE,
                ),
            )
            if result.rowcount != 1:
                raise StoreConflict("window_cas_conflict")
        return self.get_window(window_id) or {}

    def set_inventory_hash(
        self,
        *,
        window_id: str,
        inventory_hash: str,
        now: datetime | None = None,
    ) -> dict:
        """只更新运行时插件清单指纹；失败不推翻已确认的送达计数。"""

        current = now or _utc_now()
        with self._transaction() as conn:
            conn.execute(
                "UPDATE windows SET config_inventory_hash=?, updated_at=? WHERE window_id=?",
                (str(inventory_hash), _iso(current), window_id),
            )
        return self.get_window(window_id) or {}

    def update_observation(
        self,
        *,
        window_id: str,
        expected_row_revision: int,
        count_state: Mapping[str, Any],
        observation: Mapping[str, Any] | None,
        now: datetime | None = None,
    ) -> dict:
        current = now or _utc_now()
        with self._transaction() as conn:
            result = conn.execute(
                """
                UPDATE windows SET count_state_json=?, updated_at=?,
                    row_revision=row_revision+1
                WHERE window_id=? AND row_revision=? AND status=?
                """,
                (
                    canonical_json(dict(count_state)),
                    _iso(current),
                    window_id,
                    expected_row_revision,
                    _ACTIVE,
                ),
            )
            if result.rowcount != 1:
                raise StoreConflict("window_cas_conflict")
            if observation is not None:
                conn.execute(
                    """
                    INSERT INTO observations(window_id, native_session_id,
                        session_generation, session_revision, used_tokens,
                        capacity_tokens, source, sampled_at, recorded_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        window_id,
                        observation.get("native_session_id"),
                        observation.get("session_generation"),
                        str(observation.get("session_revision")),
                        observation.get("used_tokens"),
                        observation.get("capacity_tokens"),
                        observation.get("source"),
                        observation.get("sampled_at"),
                        _iso(current),
                    ),
                )
        return self.get_window(window_id) or {}

    def record_delivery(
        self,
        *,
        window_id: str,
        receipt: Mapping[str, Any],
        ack: Mapping[str, Any],
        snapshot: Mapping[str, Any] | None,
        counted: bool,
        now: datetime | None = None,
        _conn: sqlite3.Connection | None = None,
    ) -> dict:
        """幂等写入回执审计；相同身份不同事实一律冲突，不覆盖。"""

        current = now or _utc_now()
        delivery_id = str(receipt["delivery_id"])
        # The sidecar is an audit/state store, not a transcript: never persist
        # the assistant text or directive body. A hash/length preserves audit
        # value without duplicating conversation content.
        audit_ack = {key: value for key, value in ack.items() if key != "assistant_text"}
        assistant_text = ack.get("assistant_text")
        if isinstance(assistant_text, str) and assistant_text:
            import hashlib

            audit_ack["assistant_text_sha256"] = hashlib.sha256(
                assistant_text.encode("utf-8")
            ).hexdigest()
            audit_ack["assistant_text_chars"] = len(assistant_text)
        with (self._transaction() if _conn is None else nullcontext(_conn)) as conn:
            row = conn.execute(
                "SELECT * FROM deliveries WHERE delivery_id = ?", (delivery_id,)
            ).fetchone()
            if row is not None:
                if (
                    str(row["task_id"]) != str(receipt["task_id"])
                    or int(row["attempt"]) != int(receipt["attempt"])
                    or row["execution_id"] != str(receipt["execution_id"])
                    or row["body_sha256"] != str(receipt["body_sha256"])
                    or row["native_session_id"] != str(receipt["native_session_id"])
                    or int(row["session_generation"]) != int(receipt["session_generation"])
                    or str(row["session_revision"]) != str(receipt["session_revision"])
                    or row["outcome"] != str(receipt["outcome"])
                    or bool(row["counted"]) != counted
                    or row["window_id"] != window_id
                    or canonical_json(json.loads(row["ack_json"])) != canonical_json(audit_ack)
                ):
                    raise StoreConflict("delivery_conflict")
                return {"status": "duplicate", "delivery_id": delivery_id}
            try:
                conn.execute(
                    """
                    INSERT INTO deliveries(delivery_id, window_id, task_id, attempt,
                        execution_id, body_sha256, native_session_id,
                        session_generation, session_revision, outcome, turn_outcome,
                        counted, ack_json, snapshot_json, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        delivery_id,
                        window_id,
                        str(receipt["task_id"]),
                        int(receipt["attempt"]),
                        str(receipt["execution_id"]),
                        str(receipt["body_sha256"]),
                        str(receipt["native_session_id"]),
                        int(receipt["session_generation"]),
                        str(receipt["session_revision"]),
                        str(receipt["outcome"]),
                        str(ack.get("turn_outcome") or ack.get("turnOutcome") or ""),
                        1 if counted else 0,
                        canonical_json(audit_ack),
                        canonical_json(dict(snapshot)) if snapshot is not None else None,
                        _iso(current),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreConflict("delivery_logical_conflict") from exc
        return {"status": "recorded", "delivery_id": delivery_id}

    def get_delivery(self, delivery_id: str) -> Optional[dict]:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM deliveries WHERE delivery_id = ?", (delivery_id,)
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["ack"] = json.loads(data.pop("ack_json"))
        snapshot = data.pop("snapshot_json")
        data["snapshot"] = json.loads(snapshot) if snapshot else None
        return data

    def count_deliveries(self) -> int:
        with self._read() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM deliveries").fetchone()
        return int(row["n"])

    def describe(self) -> dict:
        with self._read() as conn:
            windows = conn.execute("SELECT COUNT(*) AS n FROM windows").fetchone()["n"]
            deliveries = conn.execute(
                "SELECT COUNT(*) AS n FROM deliveries"
            ).fetchone()["n"]
            channels = conn.execute("SELECT COUNT(*) AS n FROM channels").fetchone()["n"]
        return {
            "schema": STORE_SCHEMA,
            "version": STORE_VERSION,
            "windows": int(windows),
            "deliveries": int(deliveries),
            "channels": int(channels),
        }


def _window_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("count_state_json", "last_snapshot_json"):
        raw = data.pop(key, None)
        data[key.removesuffix("_json")] = json.loads(raw) if raw else None
    data["scope"] = json.loads(data.pop("scope_json"))
    return data


def wait_timeout_seconds(value: Any, *, default: float = 30.0) -> float:
    """有界等待；不接受巨大/无限等待，避免桥接把任务永久占住。"""

    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    if seconds != seconds or seconds in (float("inf"), float("-inf")):
        return default
    return max(0.0, min(seconds, 300.0))
