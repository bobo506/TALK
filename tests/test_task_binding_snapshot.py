"""ROLE-BINDING-B1b 任务目标角色绑定快照：迁移、唯一写入点、阶梯、一致性与不可变性。

覆盖实施计划 §2.6 的 B1–B18 与 B20（B19 回归由既有模块承担，见本片交付报告）：

- B1 旧形态库幂等增列、旧行 NULL、无新增回执列；
- B2/B3 普通带项目与无项目任务的快照内容与 13 键集合；
- B4 子任务按自身目标重新解析、不继承父任务快照；
- B5 schedule 物化批量两列非 NULL；
- B6 限定生产插入路径的唯一 ``AgentTask(`` 构造点静态检查；
- B7 单语句行为证据（``before_cursor_execute`` 事件：带项目 1 条 / 无项目 0 条）；
- B8 隔离假库 + 两连接受控交错：naive 多读可撕裂、单条 SQL 助手不撕裂；
- B9 commit 失败整批回滚：不留任务、Hall 或快照；
- B10/B11 快照写后不可变、配置变更只影响新任务；
- B12 离册 → 新任务 → 回册逐版本留证；
- B13/B14 全阶梯与 null 布局、``partial`` 不吞 ``runner_missing``；
- B15 旧任务 NULL 可读且不回填；
- B16 旧客户端不传新字段仍可创建；
- B17 不输出 ``binding_match*`` / ``read_receipt``；
- B18 只改 alias 时指纹相同但两版快照逐字节保留；
- B20 错误码保持、已有读事务旧视图、写事务自身写入、子任务授权预扣同次回滚。

B1a 的项目/名册/运行器/绑定 API 夹具直接复用已收取的
``tests.test_project_role_bindings``（以模块对象引用，不复制 HTTP 辅助代码）。

全部用例只在进程内 TestClient、隔离临时库与隔离假库上运行：不启动生产服务、不调用模型、
不读取任何 Key、不改生产 DB/名册/.talk/安装配置，也不改 bridges/MCP/SDK/web。
"""

from __future__ import annotations

import hashlib
import gc
import json
import shutil
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

import server.db as db
import server.main as main
import tests.test_project_role_bindings as b1a_fixtures
from server.models import (
    BINDING_FACTS_SQL,
    ROLE_BINDING_BOUND,
    ROLE_BINDING_MEMBER_DISABLED,
    ROLE_BINDING_MEMBER_MISSING,
    ROLE_BINDING_NOT_AGENT,
    ROLE_BINDING_NOT_IN_ROSTER,
    ROLE_BINDING_PARTIAL,
    ROLE_BINDING_RUNNER_MISSING,
    ROLE_BINDING_RUNNER_RETIRED,
    ROLE_BINDING_SNAPSHOT_SCHEMA_VERSION,
    ROLE_BINDING_UNCONFIGURED,
    TARGET_BINDING_SNAPSHOT_KEYS,
    AgentTask,
    AgentTaskOut,
    Group,
    Member,
    Project,
    ProjectAgent,
    ProjectRoleBinding,
    RunnerRegistry,
    TargetBindingSnapshotProjectMissing,
    binding_fingerprint,
    resolve_target_binding_snapshot,
)
from tests.test_support import RouteTestCase

BINDING_FIELDS = (
    "runner_id",
    "runtime",
    "model_source",
    "provider_id",
    "connection_ref",
    "model_id",
    "model_alias",
    "model_display_name",
    "binding_fingerprint",
)

PROJECT = "prj_snap"
MEMBER = "agent:worker"
RUNNER_ID = "runner:dsh-cli"
RUNNER_RUNTIME = "dsh"
MODEL_SOURCE = "builtin"
PROVIDER_ID = "managed:deepseek"
CONNECTION_REF = "native-deepseek-managed-login"
MODEL_ID = "deepseek-flash"
MODEL_ALIAS = "dsh/deepseek-flash"
MODEL_DISPLAY_NAME = "DeepSeek Flash"


def remove_tree(path: Path, *, attempts: int = 5) -> None:
    """删除隔离临时目录；Windows 上文件句柄可能短暂未释放，重试后放弃。"""
    for _ in range(attempts):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.2)


def expected_fingerprint(
    *,
    runner_id: str = RUNNER_ID,
    runtime: str = RUNNER_RUNTIME,
    model_source: str = MODEL_SOURCE,
    provider_id: str = PROVIDER_ID,
    connection_ref: str = CONNECTION_REF,
    model_id: str = MODEL_ID,
) -> str:
    """独立重算六维内容指纹（不调用被测助手，避免同源自证）。"""
    payload = "|".join(
        [runner_id, runtime, model_source, provider_id, connection_ref, model_id]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ════════════════════════════════════════════════════════════════════
# B1：旧形态库迁移
# ════════════════════════════════════════════════════════════════════


class TaskBindingSnapshotMigrationTests(unittest.TestCase):
    """旧库只加两列与一个索引；旧行 NULL；重复 ``init_db()`` 幂等且不回填。"""

    SNAPSHOT_COLUMNS = {"target_binding_snapshot", "target_binding_state"}
    FORBIDDEN_HINTS = ("receipt", "read_count", "fact_read", "match", "hash")

    def setUp(self):
        super().setUp()
        tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self._tmpdir = Path(tempfile.mkdtemp(prefix="talk-legacy-b1b-", dir=tmp_root))
        self.db_path = self._tmpdir / "legacy.db"
        self._write_legacy_database()
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self._old_engine = db.engine
        self._old_main_engine = main.engine
        db.engine = self.engine
        main.engine = self.engine
        self.addCleanup(self._restore_engines)

    def _restore_engines(self):
        db.engine = self._old_engine
        main.engine = self._old_main_engine
        self.engine.dispose()
        gc.collect()
        remove_tree(self._tmpdir, attempts=20)

    def _write_legacy_database(self):
        """写一个 B1b 之前形态的库：``agent_tasks`` 没有两个快照列。

        旧形态与既有迁移用例 ``tests/test_tasks.py::test_init_db_adds_task_hall_fields``
        一致：``claimed_by`` / ``instance_id`` 等更早的列已存在，本片只新增两列。
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE agent_tasks (
                    id INTEGER PRIMARY KEY,
                    target_member_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    content TEXT NOT NULL,
                    title TEXT,
                    status TEXT NOT NULL,
                    claimed_by TEXT,
                    instance_id TEXT,
                    result_message_id INTEGER,
                    last_error TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    claimed_at TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO agent_tasks (
                    id, target_member_id, created_by, content, status,
                    created_at, updated_at
                ) VALUES (
                    1, 'agent:worker', 'human:bobo', '升级前就存在的任务', 'queued',
                    '2026-01-01 00:00:00', '2026-01-01 00:00:00'
                )
                """
            )
            conn.commit()

    def _columns(self) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA table_info(agent_tasks)"
                ).fetchall()
            }

    def _indexes(self) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA index_list(agent_tasks)"
                ).fetchall()
            }

    def _legacy_row(self):
        with self.engine.connect() as conn:
            return conn.exec_driver_sql(
                "SELECT id, target_binding_snapshot, target_binding_state "
                "FROM agent_tasks WHERE id = 1"
            ).fetchone()

    def test_legacy_database_gains_two_columns_idempotently_without_backfill(self):
        self.assertNotIn("target_binding_snapshot", self._columns())
        self.assertNotIn("target_binding_state", self._columns())

        db.init_db()

        columns = self._columns()
        self.assertTrue(self.SNAPSHOT_COLUMNS.issubset(columns))
        # 除两列外没有任何新的“绑定/回执/计数/哈希”列（合同 §7.1、R3/D8）。
        self.assertEqual(
            {name for name in columns if "binding" in name}, self.SNAPSHOT_COLUMNS
        )
        for hint in self.FORBIDDEN_HINTS:
            self.assertEqual({name for name in columns if hint in name}, set(), hint)
        self.assertIn("ix_agent_tasks_target_binding_state", self._indexes())
        # 旧行保持 NULL：不回填、不推断成 unconfigured 或某个模型。
        self.assertEqual(self._legacy_row(), (1, None, None))

        after_first = set(columns)
        db.init_db()
        db.init_db()
        self.assertEqual(self._columns(), after_first)
        self.assertEqual(self._legacy_row(), (1, None, None))
        with self.engine.connect() as conn:
            self.assertEqual(
                conn.exec_driver_sql("SELECT COUNT(*) FROM agent_tasks").scalar_one(), 1
            )
            self.assertEqual(
                conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM project_role_bindings"
                ).scalar_one(),
                0,
            )
            self.assertEqual(
                conn.exec_driver_sql("SELECT COUNT(*) FROM runner_registry").scalar_one(),
                0,
            )

    def test_repeated_init_db_does_not_rewrite_existing_snapshot_values(self):
        db.init_db()
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                """
                UPDATE agent_tasks
                SET target_binding_state = 'no_project',
                    target_binding_snapshot = '{"schema_version":"role-binding-snapshot-1"}'
                WHERE id = 1
                """
            )
        db.init_db()
        db.init_db()
        with self.engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT target_binding_state, target_binding_snapshot "
                "FROM agent_tasks WHERE id = 1"
            ).fetchone()
        self.assertEqual(row[0], "no_project")
        self.assertEqual(
            row[1], '{"schema_version":"role-binding-snapshot-1"}'
        )


# ════════════════════════════════════════════════════════════════════
# 公共夹具：直接落库的项目/名册/运行器/绑定
# ════════════════════════════════════════════════════════════════════


class SnapshotSeedMixin:
    """快照解析用例的公共夹具：绕过 HTTP 直接构造事实行，精确控制阶梯输入。"""

    def seed_project(self, project_id: str = PROJECT, *, maintainer: str = "human:bobo"):
        with self.session() as session:
            session.add(
                Project(
                    project_id=project_id,
                    display_name=project_id,
                    maintainer_member_id=maintainer,
                )
            )
            session.commit()

    def seed_roster(self, project_id: str, member_id: str):
        with self.session() as session:
            session.add(ProjectAgent(project_id=project_id, member_id=member_id))
            session.commit()

    def seed_runner(
        self,
        runner_id: str = RUNNER_ID,
        *,
        runtime: str = RUNNER_RUNTIME,
        adapter_status: str = "adapted",
    ):
        with self.session() as session:
            session.add(
                RunnerRegistry(
                    runner_id=runner_id,
                    runtime=runtime,
                    display_name=f"Runner {runner_id}",
                    adapter_status=adapter_status,
                    created_by="human:bobo",
                )
            )
            session.commit()

    def seed_binding(
        self,
        member_id: str = MEMBER,
        *,
        project_id: str = PROJECT,
        **overrides,
    ):
        values = {
            "project_id": project_id,
            "member_id": member_id,
            "runner_id": RUNNER_ID,
            "model_source": MODEL_SOURCE,
            "provider_id": PROVIDER_ID,
            "connection_ref": CONNECTION_REF,
            "model_id": MODEL_ID,
            "model_alias": MODEL_ALIAS,
            "model_display_name": MODEL_DISPLAY_NAME,
            "updated_by": "human:bobo",
            "updated_at": datetime.now(timezone.utc),
        }
        values.update(overrides)
        with self.session() as session:
            session.add(ProjectRoleBinding(**values))
            session.commit()

    def resolve_snapshot(
        self,
        *,
        project_id: str | None = PROJECT,
        member_id: str = MEMBER,
    ) -> dict:
        with self.session() as session:
            return resolve_target_binding_snapshot(
                project_id=project_id,
                target_member_id=member_id,
                session=session,
            )

    def assert_snapshot_shape(self, snapshot: dict, state: str):
        self.assertEqual(tuple(snapshot), TARGET_BINDING_SNAPSHOT_KEYS)
        self.assertEqual(len(snapshot), 13)
        self.assertNotIn("read_receipt", snapshot)
        self.assertEqual(snapshot["schema_version"], ROLE_BINDING_SNAPSHOT_SCHEMA_VERSION)
        self.assertEqual(snapshot["state"], state)
        parsed = datetime.fromisoformat(snapshot["snapshot_at"])
        self.assertIsNotNone(parsed.tzinfo, snapshot["snapshot_at"])
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    def assert_all_binding_fields_null(self, snapshot: dict):
        for field in BINDING_FIELDS:
            self.assertIsNone(snapshot[field], field)


# ════════════════════════════════════════════════════════════════════
# B2/B3/B7/B13/B14/B17/B20：快照助手（隔离库，不经 HTTP）
# ════════════════════════════════════════════════════════════════════


class TargetBindingSnapshotResolverTests(SnapshotSeedMixin, RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        for member_id, key in (
            ("agent:worker", "worker-key"),
            ("agent:parked", "parked-key"),
            ("agent:other", "other-key"),
            ("agent:lonely", "lonely-key"),
            ("agent:rmissing", "rmissing-key"),
            ("agent:retired", "retired-key"),
            ("agent:bound", "bound-key"),
        ):
            self.add_member(member_id, api_key=key, display_name=member_id)
        with self.session() as session:
            parked = session.get(Member, "agent:parked")
            parked.disabled_at = datetime.now(timezone.utc)
            session.add(parked)
            session.commit()
        self.seed_project()
        for member_id in (
            MEMBER,
            "agent:parked",
            "agent:rmissing",
            "agent:retired",
            "agent:bound",
            "human:bobo",
        ):
            self.seed_roster(PROJECT, member_id)
        self.seed_runner()

    def capture_statements(self):
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", _capture)
        return statements, _capture

    def test_no_project_snapshot_executes_zero_statements(self):
        statements, capture = self.capture_statements()
        try:
            with self.session() as session:
                snapshot = resolve_target_binding_snapshot(
                    project_id=None, target_member_id=MEMBER, session=session
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        # 无项目分支不执行任何事实 SQL（合同 §7.3）：语句数 0，不是“1 条空查询”。
        self.assertEqual(statements, [])
        self.assert_snapshot_shape(snapshot, "no_project")
        self.assert_all_binding_fields_null(snapshot)
        self.assertIsInstance(snapshot["note"], str)
        self.assertTrue(snapshot["note"])

    def test_project_snapshot_executes_exactly_one_shared_helper_statement(self):
        statements, capture = self.capture_statements()
        try:
            with self.session() as session:
                snapshot = resolve_target_binding_snapshot(
                    project_id=PROJECT, target_member_id=MEMBER, session=session
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(len(statements), 1, statements)
        # 复用 B1a 的同一段 SQL（同一助手、同一常量、逐字符同文），不是第二份或补查询。
        # 驱动层参数占位符由 SQLAlchemy 渲染成 ``?``，因此按具名参数反推比对。
        self.assertEqual(
            statements[0].strip(),
            BINDING_FACTS_SQL.replace(":project_id", "?").replace(":member_id", "?").strip(),
        )
        self.assertEqual(
            hashlib.sha256(BINDING_FACTS_SQL.encode("utf-8")).hexdigest(),
            "a812ee474b4710f5eac29f773fb02f39dec70201c3fdd0abc66709f7b17f0f1e",
        )
        self.assert_snapshot_shape(snapshot, ROLE_BINDING_UNCONFIGURED)
        self.assert_all_binding_fields_null(snapshot)

    def test_bound_snapshot_matches_binding_row_and_fingerprint(self):
        self.seed_binding("agent:bound")
        snapshot = self.resolve_snapshot(member_id="agent:bound")
        self.assert_snapshot_shape(snapshot, ROLE_BINDING_BOUND)
        self.assertEqual(snapshot["runner_id"], RUNNER_ID)
        self.assertEqual(snapshot["runtime"], RUNNER_RUNTIME)
        self.assertEqual(snapshot["model_source"], MODEL_SOURCE)
        self.assertEqual(snapshot["provider_id"], PROVIDER_ID)
        self.assertEqual(snapshot["connection_ref"], CONNECTION_REF)
        self.assertEqual(snapshot["model_id"], MODEL_ID)
        self.assertEqual(snapshot["model_alias"], MODEL_ALIAS)
        self.assertEqual(snapshot["model_display_name"], MODEL_DISPLAY_NAME)
        self.assertEqual(snapshot["binding_fingerprint"], expected_fingerprint())
        self.assertIsNone(snapshot["note"])
        # 与 B1a 助手的指纹逐字一致（复用同一规则，不另算一套）。
        with self.session() as session:
            facts = b1a_fixtures.read_role_binding_facts(
                session, project_id=PROJECT, member_id="agent:bound"
            )
        self.assertEqual(snapshot["binding_fingerprint"], binding_fingerprint(facts))

    def test_every_ladder_state_keeps_its_contract_null_layout(self):
        # 无绑定行：有名册 → unconfigured；离册 → not_in_roster（序 3 优先于序 5）。
        unconfigured = self.resolve_snapshot(member_id=MEMBER)
        self.assert_snapshot_shape(unconfigured, ROLE_BINDING_UNCONFIGURED)
        self.assert_all_binding_fields_null(unconfigured)

        lonely = self.resolve_snapshot(member_id="agent:lonely")
        self.assert_snapshot_shape(lonely, ROLE_BINDING_NOT_IN_ROSTER)
        self.assert_all_binding_fields_null(lonely)

        # 身份缺失：members 没有该 member，但绑定行保留。
        self.seed_binding("agent:ghost")
        missing = self.resolve_snapshot(member_id="agent:ghost")
        self.assert_snapshot_shape(missing, ROLE_BINDING_MEMBER_MISSING)
        self.assertEqual(missing["runner_id"], RUNNER_ID)
        self.assertEqual(missing["runtime"], RUNNER_RUNTIME)
        self.assertEqual(missing["binding_fingerprint"], expected_fingerprint())

        # 被全局禁用。
        self.seed_binding("agent:parked")
        disabled = self.resolve_snapshot(member_id="agent:parked")
        self.assert_snapshot_shape(disabled, ROLE_BINDING_MEMBER_DISABLED)
        self.assertEqual(disabled["binding_fingerprint"], expected_fingerprint())

        # 已离册但绑定行保留（有值照存）。
        self.seed_binding("agent:other")
        offboard = self.resolve_snapshot(member_id="agent:other")
        self.assert_snapshot_shape(offboard, ROLE_BINDING_NOT_IN_ROSTER)
        self.assertEqual(offboard["model_alias"], MODEL_ALIAS)
        self.assertEqual(offboard["binding_fingerprint"], expected_fingerprint())

        # 非 agent 身份。
        self.seed_binding("human:bobo")
        not_agent = self.resolve_snapshot(member_id="human:bobo")
        self.assert_snapshot_shape(not_agent, ROLE_BINDING_NOT_AGENT)
        self.assertEqual(not_agent["binding_fingerprint"], expected_fingerprint())

        # partial：只由绑定行**存储必填五项**缺失触发；派生 runtime 仍给出、指纹为 null。
        self.seed_binding(MEMBER, model_id=None)
        partial = self.resolve_snapshot(member_id=MEMBER)
        self.assert_snapshot_shape(partial, ROLE_BINDING_PARTIAL)
        self.assertEqual(partial["runner_id"], RUNNER_ID)
        self.assertEqual(partial["runtime"], RUNNER_RUNTIME)
        self.assertEqual(partial["provider_id"], PROVIDER_ID)
        self.assertEqual(partial["model_alias"], MODEL_ALIAS)
        self.assertIsNone(partial["model_id"])
        self.assertIsNone(partial["binding_fingerprint"])

        # runner_missing：五个存储必填字段齐全，登记事实不可解析 → runtime 与指纹都 null。
        self.seed_binding("agent:rmissing", runner_id="runner:gone")
        runner_missing = self.resolve_snapshot(member_id="agent:rmissing")
        self.assert_snapshot_shape(runner_missing, ROLE_BINDING_RUNNER_MISSING)
        self.assertEqual(runner_missing["runner_id"], "runner:gone")
        self.assertIsNone(runner_missing["runtime"])
        self.assertIsNone(runner_missing["binding_fingerprint"])
        self.assertEqual(runner_missing["model_alias"], MODEL_ALIAS)

        # runner_retired：runtime 可解析 → 指纹照给。
        self.seed_runner("runner:old", runtime="codex", adapter_status="retired")
        self.seed_binding("agent:retired", runner_id="runner:old")
        retired = self.resolve_snapshot(member_id="agent:retired")
        self.assert_snapshot_shape(retired, ROLE_BINDING_RUNNER_RETIRED)
        self.assertEqual(retired["runtime"], "codex")
        self.assertEqual(
            retired["binding_fingerprint"],
            expected_fingerprint(runner_id="runner:old", runtime="codex"),
        )

    def test_partial_never_swallows_runner_missing(self):
        # 存储必填五项齐全 + 登记行缺失：必须是 runner_missing，不是 partial。
        self.seed_binding("agent:rmissing", runner_id="runner:gone")
        snapshot = self.resolve_snapshot(member_id="agent:rmissing")
        self.assertEqual(snapshot["state"], ROLE_BINDING_RUNNER_MISSING)
        # 同一行若再缺一个存储必填字段，则回到 partial（顺序仍是存储事实优先）。
        self.seed_binding("agent:retired", runner_id="runner:gone", connection_ref=None)
        partial = self.resolve_snapshot(member_id="agent:retired")
        self.assertEqual(partial["state"], ROLE_BINDING_PARTIAL)
        self.assertIsNone(partial["binding_fingerprint"])

    def test_alias_is_stored_in_every_state_and_never_invented(self):
        self.seed_binding("agent:other")
        for member_id, state in (
            ("agent:other", ROLE_BINDING_NOT_IN_ROSTER),
            ("agent:bound", ROLE_BINDING_BOUND),
        ):
            if state == ROLE_BINDING_BOUND:
                self.seed_binding("agent:bound")
            snapshot = self.resolve_snapshot(member_id=member_id)
            self.assertEqual(snapshot["state"], state)
            self.assertEqual(snapshot["model_alias"], MODEL_ALIAS)
        self.seed_binding("agent:rmissing", runner_id="runner:gone")
        gone = self.resolve_snapshot(member_id="agent:rmissing")
        self.assertEqual(gone["model_alias"], MODEL_ALIAS)
        # 不猜模型：没有任何行时所有绑定字段必须是 null。
        self.assert_all_binding_fields_null(self.resolve_snapshot(member_id=MEMBER))

    def test_unknown_project_raises_lookup_error_without_http_semantics(self):
        with self.session() as session:
            with self.assertRaises(TargetBindingSnapshotProjectMissing) as ctx:
                resolve_target_binding_snapshot(
                    project_id="prj_missing",
                    target_member_id=MEMBER,
                    session=session,
                )
        self.assertIsInstance(ctx.exception, LookupError)
        # 共用事实助手不固定 HTTP 错误码：异常不携带 status_code。
        self.assertFalse(hasattr(ctx.exception, "status_code"))

    def test_task_columns_and_output_add_only_the_two_readonly_snapshot_fields(self):
        table_columns = set(AgentTask.__table__.columns.keys())
        self.assertEqual(
            {name for name in table_columns if "binding" in name},
            {"target_binding_snapshot", "target_binding_state"},
        )
        out_fields = set(AgentTaskOut.model_fields)
        self.assertTrue(
            {"target_binding_snapshot", "target_binding_state"}.issubset(out_fields)
        )
        self.assertEqual(
            {name for name in out_fields if "binding" in name},
            {"target_binding_snapshot", "target_binding_state"},
        )
        self.assertEqual(
            {
                name
                for name in out_fields
                if "match" in name or "receipt" in name or "reported_" in name
            },
            set(),
        )
        self.assertEqual(
            {name for name in TARGET_BINDING_SNAPSHOT_KEYS if "receipt" in name}, set()
        )


# ════════════════════════════════════════════════════════════════════
# B8/B20：隔离假库 + 两连接受控交错
# ════════════════════════════════════════════════════════════════════


class TargetBindingSnapshotInterleaveTests(SnapshotSeedMixin, RouteTestCase):
    """真实两连接受控交错：naive 多读撕裂 vs 单条 SQL 助手不撕裂。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member(MEMBER, api_key="worker-key", display_name="Worker")
        with self.engine.connect() as conn:
            mode = conn.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one()
        self.assertEqual(str(mode).lower(), "wal")
        self.seed_project()
        self.seed_roster(PROJECT, MEMBER)
        self.seed_runner("runner:one", runtime="kimi-code", adapter_status="adapted")
        self.seed_runner("runner:two", runtime="dsh", adapter_status="unverified")
        self.seed_binding()
        self.move_binding_to_runner_one()

    def move_binding_to_runner_one(self):
        with self.session() as session:
            session.execute(
                text(
                    "UPDATE project_role_bindings SET runner_id='runner:one', model_id='model-one' "
                    "WHERE project_id=:p AND member_id=:m"
                ),
                {"p": PROJECT, "m": MEMBER},
            )
            session.execute(
                text(
                    "UPDATE runner_registry SET adapter_status='adapted' "
                    "WHERE runner_id='runner:one'"
                )
            )
            session.execute(
                text(
                    "UPDATE runner_registry SET adapter_status='unverified' "
                    "WHERE runner_id='runner:two'"
                )
            )
            session.commit()

    @staticmethod
    def _commit_state_one(session) -> None:
        """第二连接提交：绑定切到 runner:two，同时把 runner:one 置为 retired。"""
        session.execute(
            text(
                "UPDATE project_role_bindings SET runner_id='runner:two', model_id='model-two' "
                "WHERE project_id=:p AND member_id=:m"
            ),
            {"p": PROJECT, "m": MEMBER},
        )
        session.execute(
            text(
                "UPDATE runner_registry SET adapter_status='retired' "
                "WHERE runner_id='runner:one'"
            )
        )
        session.commit()

    @staticmethod
    def _naive_read(session) -> tuple[str, str, str]:
        """原方案（v2）思路：同一 Session 多次独立 SELECT，仅用于负对照。

        受控交错由调用方在两次 ``execute`` 之间注入，因此这里只提供单次调用形态，
        负对照用例内联展开两步读取。
        """
        runner_id = session.execute(
            text(
                "SELECT runner_id FROM project_role_bindings "
                "WHERE project_id=:p AND member_id=:m"
            ),
            {"p": PROJECT, "m": MEMBER},
        ).scalar_one()
        registry = (
            session.execute(
                text("SELECT runtime, adapter_status FROM runner_registry WHERE runner_id=:r"),
                {"r": runner_id},
            )
            .mappings()
            .one()
        )
        return runner_id, registry["runtime"], registry["adapter_status"]

    def test_naive_multi_read_tears_while_single_statement_snapshot_does_not(self):
        # 静止状态下的 naive 多读看不出问题（基线）。
        with Session(self.engine) as quiet:
            self.assertEqual(
                self._naive_read(quiet), ("runner:one", "kimi-code", "adapted")
            )
        # 负对照：同一交错的两次独立 SELECT 取到“从未同时存在”的组合。
        with Session(self.engine) as reader, Session(self.engine) as writer:
            naive_first = reader.execute(
                text(
                    "SELECT runner_id FROM project_role_bindings "
                    "WHERE project_id=:p AND member_id=:m"
                ),
                {"p": PROJECT, "m": MEMBER},
            ).scalar_one()
            self._commit_state_one(writer)
            naive_second = (
                reader.execute(
                    text(
                        "SELECT runtime, adapter_status FROM runner_registry "
                        "WHERE runner_id=:r"
                    ),
                    {"r": naive_first},
                )
                .mappings()
                .one()
            )
        self.assertEqual(naive_first, "runner:one")
        self.assertEqual(naive_second["adapter_status"], "retired")
        # (runner:one, retired) 从未同时存在：切换前 runner:one 是 adapted，
        # 切换后绑定已指向 runner:two 且 runner:one 才变 retired。
        self.assertNotIn(
            (naive_first, naive_second["adapter_status"]),
            {("runner:one", "adapted"), ("runner:two", "unverified")},
        )

        # 同一交错下，单条 SQL 助手永不撕裂。
        self.move_binding_to_runner_one()
        with self.session() as reader:
            before = resolve_target_binding_snapshot(
                project_id=PROJECT, target_member_id=MEMBER, session=reader
            )
            with self.session() as other_writer:
                self._commit_state_one(other_writer)
            after = resolve_target_binding_snapshot(
                project_id=PROJECT, target_member_id=MEMBER, session=reader
            )
        consistent_states = {
            (
                "runner:one",
                "kimi-code",
                expected_fingerprint(
                    runner_id="runner:one", runtime="kimi-code", model_id="model-one"
                ),
            ),
            (
                "runner:two",
                "dsh",
                expected_fingerprint(
                    runner_id="runner:two", runtime="dsh", model_id="model-two"
                ),
            ),
        }
        for snapshot in (before, after):
            self.assertIn(
                (
                    snapshot["runner_id"],
                    snapshot["runtime"],
                    snapshot["binding_fingerprint"],
                ),
                consistent_states,
                snapshot,
            )
        # 交错确实跨过一次提交（否则上面的断言会退化成只验证一个状态）。
        self.assertEqual(before["runner_id"], "runner:one")
        self.assertEqual(after["runner_id"], "runner:two")
        self.assertNotEqual(
            before["binding_fingerprint"], after["binding_fingerprint"]
        )

    def test_existing_read_transaction_keeps_its_own_view(self):
        conn = self.engine.connect()
        try:
            conn.exec_driver_sql("BEGIN")
            session = Session(bind=conn)
            try:
                first = resolve_target_binding_snapshot(
                    project_id=PROJECT, target_member_id=MEMBER, session=session
                )
                with self.session() as writer:
                    self._commit_state_one(writer)
                second = resolve_target_binding_snapshot(
                    project_id=PROJECT, target_member_id=MEMBER, session=session
                )
            finally:
                session.close()
        finally:
            conn.exec_driver_sql("ROLLBACK")
            conn.close()
        self.assertEqual(first["runner_id"], "runner:one")
        # 已有读事务沿用自身视图：另一连接提交后，本事务内仍读到旧状态。
        self.assertEqual(second["runner_id"], "runner:one")
        self.assertEqual(second["binding_fingerprint"], first["binding_fingerprint"])
        # 新事务（新读视图）看得到提交后的新值。
        fresh = self.resolve_snapshot()
        self.assertEqual(fresh["runner_id"], "runner:two")
        self.assertEqual(fresh["state"], ROLE_BINDING_BOUND)

    def test_write_transaction_sees_its_own_writes_and_rollback_restores(self):
        with self.session() as writer:
            writer.execute(
                text(
                    "UPDATE project_role_bindings SET runner_id='runner:two', model_id='model-two' "
                    "WHERE project_id=:p AND member_id=:m"
                ),
                {"p": PROJECT, "m": MEMBER},
            )
            own = resolve_target_binding_snapshot(
                project_id=PROJECT, target_member_id=MEMBER, session=writer
            )
            # 真实写事务内可见自身未提交写入（不是“提交后最新值”承诺）。
            self.assertEqual(own["runner_id"], "runner:two")
            self.assertEqual(own["runtime"], "dsh")
            writer.rollback()
        after = self.resolve_snapshot()
        self.assertEqual(after["runner_id"], "runner:one")
        self.assertEqual(after["runtime"], "kimi-code")


# ════════════════════════════════════════════════════════════════════
# B2–B5/B9–B12/B15/B16/B18/B20：HTTP 创建路径
# ════════════════════════════════════════════════════════════════════


class TargetBindingSnapshotCreationTests(b1a_fixtures.BindingApiTestCase):
    """普通/无项目/子任务/schedule 四条创建路径与快照生命周期。"""

    SNAPSHOT_ALIAS = "dsh/deepseek-flash"

    def _snapshot(self, task_id: int) -> dict:
        with self.session() as session:
            task = session.get(AgentTask, task_id)
            self.assertIsNotNone(task)
            return dict(task.target_binding_snapshot), task.target_binding_state

    def _task_row(self, task_id: int) -> AgentTask:
        with self.session() as session:
            return session.get(AgentTask, task_id)

    def _counts(self) -> tuple[int, int]:
        with self.session() as session:
            tasks = len(list(session.exec(select(AgentTask)).all()))
            halls = len(
                list(session.exec(select(Group).where(Group.type == "task")).all())
            )
            return tasks, halls

    def _bound_project(self, project_id: str, *, alias: str = MODEL_ALIAS):
        self.register_project(project_id)
        self.sync(
            project_id,
            [
                {
                    "member_id": "agent:worker",
                    "business_role": "dev",
                    "decision_tier": "execution",
                },
                {
                    "member_id": "agent:other",
                    "business_role": "dev",
                    "decision_tier": "execution",
                },
            ],
        )
        self.register_runner()
        self.put_binding(
            project_id, "agent:worker", self.binding_payload(model_alias=alias)
        )

    def test_bound_project_task_freezes_snapshot_outside_business_text(self):
        self._bound_project("prj_b1b")
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_b1b",
                    "target_member_id": "agent:worker",
                    "title": "Dispatch",
                    "content": "Freeze dispatch facts",
                },
            )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["target_binding_state"], ROLE_BINDING_BOUND)
        snapshot = body["target_binding_snapshot"]
        self.assertEqual(tuple(snapshot), TARGET_BINDING_SNAPSHOT_KEYS)
        self.assertEqual(snapshot["schema_version"], ROLE_BINDING_SNAPSHOT_SCHEMA_VERSION)
        self.assertNotIn("read_receipt", snapshot)
        self.assertEqual(snapshot["runner_id"], b1a_fixtures.RUNNER_ID)
        self.assertEqual(snapshot["runtime"], b1a_fixtures.RUNNER_RUNTIME)
        self.assertEqual(snapshot["model_source"], "builtin")
        self.assertEqual(snapshot["provider_id"], "managed:deepseek")
        self.assertEqual(snapshot["connection_ref"], b1a_fixtures.CONNECTION_REF)
        self.assertEqual(snapshot["model_id"], b1a_fixtures.MODEL_ID)
        self.assertEqual(snapshot["model_alias"], MODEL_ALIAS)
        self.assertEqual(snapshot["model_display_name"], "DeepSeek Flash")
        self.assertEqual(snapshot["binding_fingerprint"], b1a_fixtures.fingerprint_of())
        parsed = datetime.fromisoformat(snapshot["snapshot_at"])
        self.assertEqual(parsed.utcoffset(), timedelta(0))

        stored, state = self._snapshot(body["id"])
        self.assertEqual(state, ROLE_BINDING_BOUND)
        self.assertEqual(stored, snapshot)
        # 绑定标识符与快照 JSON 都不混入任务正文或 Task Hall 正文（合同 §5.3）。
        self.assertNotIn("runner_id", body["content"])
        self.assertNotIn("binding_fingerprint", body["title"])
        with self.session() as session:
            hall = session.get(Group, body["hall_group_id"])
        for text_field in (hall.description or "", hall.name or "", body["content"], body["title"]):
            self.assertNotIn("role-binding-snapshot", text_field)
            self.assertNotIn(snapshot["binding_fingerprint"], text_field)
            self.assertNotIn('"runner_id"', text_field)

    def test_task_without_project_freezes_no_project_snapshot(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:worker", "content": "No project"},
            )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["target_binding_state"], "no_project")
        snapshot = body["target_binding_snapshot"]
        self.assertEqual(tuple(snapshot), TARGET_BINDING_SNAPSHOT_KEYS)
        self.assertEqual(snapshot["state"], "no_project")
        for field in BINDING_FIELDS:
            self.assertIsNone(snapshot[field], field)
        stored, state = self._snapshot(body["id"])
        self.assertEqual(stored, snapshot)
        self.assertEqual(state, "no_project")

    def test_subtask_resolves_its_own_target_and_parent_snapshot_is_untouched(self):
        self._bound_project("prj_child", alias="dsh/worker-alias")
        self.put_binding(
            "prj_child",
            "agent:other",
            self.binding_payload(model_alias="dsh/other-alias", model_id="deepseek-pro"),
        )
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_child",
                    "target_member_id": "agent:worker",
                    "content": "Parent",
                    "may_delegate": True,
                },
            )
            self.assertEqual(root.status_code, 201, root.text)
            claimed = client.post(
                f"/api/tasks/{root.json()['id']}/claim",
                headers={"X-API-Key": "worker-key"},
                json={},
            )
            self.assertEqual(claimed.status_code, 200, claimed.text)
            child = client.post(
                "/api/tasks",
                headers={"X-API-Key": "worker-key"},
                json={
                    "parent_task_id": root.json()["id"],
                    "authorization_epoch": claimed.json()["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "Child",
                },
            )
        self.assertEqual(child.status_code, 201, child.text)
        child_body = child.json()
        self.assertEqual(child_body["project_id"], "prj_child")
        self.assertEqual(child_body["target_binding_state"], ROLE_BINDING_BOUND)
        self.assertEqual(
            child_body["target_binding_snapshot"]["model_alias"], "dsh/other-alias"
        )
        self.assertEqual(
            child_body["target_binding_snapshot"]["model_id"], "deepseek-pro"
        )
        # 子任务不继承父目标配置（D1），父任务快照保持原值。
        root_snapshot, root_state = self._snapshot(root.json()["id"])
        self.assertEqual(root_state, ROLE_BINDING_BOUND)
        self.assertEqual(root_snapshot["model_alias"], "dsh/worker-alias")
        self.assertEqual(root_snapshot["model_id"], b1a_fixtures.MODEL_ID)
        self.assertNotEqual(
            root_snapshot["binding_fingerprint"],
            child_body["target_binding_snapshot"]["binding_fingerprint"],
        )

    def test_schedule_materialization_writes_no_project_snapshots_for_every_task(self):
        run_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        with self.make_client() as client:
            for index in (1, 2):
                scheduled = client.post(
                    "/api/tasks/schedules",
                    headers={"X-API-Key": "bobo-key"},
                    json={
                        "target_member_id": "agent:worker",
                        "content": f"Scheduled {index}",
                        "run_at": run_at,
                    },
                )
                self.assertEqual(scheduled.status_code, 201, scheduled.text)
            materialized = client.post(
                "/api/tasks/schedules/run-due", headers={"X-API-Key": "bobo-key"}
            )
        self.assertEqual(materialized.status_code, 200, materialized.text)
        created_tasks = materialized.json()["created_tasks"]
        self.assertEqual(len(created_tasks), 2)
        for task in created_tasks:
            self.assertEqual(task["target_binding_state"], "no_project")
            snapshot = task["target_binding_snapshot"]
            self.assertEqual(tuple(snapshot), TARGET_BINDING_SNAPSHOT_KEYS)
            for field in BINDING_FIELDS:
                self.assertIsNone(snapshot[field], field)
            stored, state = self._snapshot(task["id"])
            self.assertEqual(state, "no_project")
            self.assertEqual(stored, snapshot)

    def test_cancelled_and_completed_tasks_keep_their_snapshot_bytes(self):
        self._bound_project("prj_frozen")
        with self.make_client() as client:
            live = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_frozen",
                    "target_member_id": "agent:worker",
                    "content": "Lifecycle",
                },
            )
            cancel_me = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_frozen",
                    "target_member_id": "agent:worker",
                    "content": "Cancel me",
                },
            )
            self.assertEqual(live.status_code, 201, live.text)
            self.assertEqual(cancel_me.status_code, 201, cancel_me.text)
            before = json.dumps(live.json()["target_binding_snapshot"], sort_keys=True)

            claimed = client.post(
                f"/api/tasks/{live.json()['id']}/claim",
                headers={"X-API-Key": "worker-key"},
                json={},
            )
            self.assertEqual(claimed.status_code, 200, claimed.text)
            heartbeat = client.post(
                f"/api/tasks/{live.json()['id']}/heartbeat",
                headers={"X-API-Key": "worker-key"},
                json={"claim_token": claimed.json()["claim_token"]},
            )
            self.assertEqual(heartbeat.status_code, 200, heartbeat.text)
            result = self.add_message(
                from_id="agent:worker",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id=live.json()["hall_group_id"],
                content="done",
            )
            completed = client.post(
                f"/api/tasks/{live.json()['id']}/complete",
                headers={"X-API-Key": "worker-key"},
                json={
                    "status": "succeeded",
                    "result_message_id": result.id,
                    "claim_token": claimed.json()["claim_token"],
                },
            )
            self.assertEqual(completed.status_code, 200, completed.text)
            canceled = client.post(
                f"/api/tasks/{cancel_me.json()['id']}/cancel",
                headers={"X-API-Key": "bobo-key"},
            )
            self.assertEqual(canceled.status_code, 200, canceled.text)
            # 生命周期结束后再改绑定：历史任务快照不受影响。
            self.put_binding(
                "prj_frozen",
                "agent:worker",
                self.binding_payload(model_alias="dsh/after-lifecycle"),
            )
            reread = client.get(
                f"/api/tasks/{live.json()['id']}", headers={"X-API-Key": "bobo-key"}
            )
            reread_cancel = client.get(
                f"/api/tasks/{cancel_me.json()['id']}",
                headers={"X-API-Key": "bobo-key"},
            )
        self.assertEqual(reread.status_code, 200, reread.text)
        self.assertEqual(reread_cancel.status_code, 200, reread_cancel.text)
        self.assertEqual(
            json.dumps(reread.json()["target_binding_snapshot"], sort_keys=True), before
        )
        self.assertEqual(
            json.dumps(reread_cancel.json()["target_binding_snapshot"], sort_keys=True),
            json.dumps(cancel_me.json()["target_binding_snapshot"], sort_keys=True),
        )
        self.assertEqual(reread.json()["target_binding_snapshot"]["model_alias"], MODEL_ALIAS)

    def test_binding_change_only_affects_new_tasks(self):
        self._bound_project("prj_drift")
        with self.make_client() as client:
            first = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_drift",
                    "target_member_id": "agent:worker",
                    "content": "Before change",
                },
            )
        self.put_binding(
            "prj_drift",
            "agent:worker",
            self.binding_payload(
                model_source="custom_api",
                provider_id="user:deepseek-openai",
                connection_ref="user-deepseek-conn-2",
                model_id="deepseek-chat",
                model_alias="dsh/deepseek-chat",
                model_display_name="DeepSeek Chat",
            ),
        )
        with self.make_client() as client:
            second = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_drift",
                    "target_member_id": "agent:worker",
                    "content": "After change",
                },
            )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        old_snapshot, _ = self._snapshot(first.json()["id"])
        new_snapshot, _ = self._snapshot(second.json()["id"])
        self.assertEqual(old_snapshot["model_id"], b1a_fixtures.MODEL_ID)
        self.assertEqual(old_snapshot["model_source"], "builtin")
        self.assertEqual(new_snapshot["model_id"], "deepseek-chat")
        self.assertEqual(new_snapshot["model_source"], "custom_api")
        self.assertEqual(new_snapshot["connection_ref"], "user-deepseek-conn-2")
        self.assertNotEqual(
            old_snapshot["binding_fingerprint"], new_snapshot["binding_fingerprint"]
        )

    def test_alias_only_change_keeps_fingerprint_but_keeps_both_versions(self):
        self._bound_project("prj_alias", alias="dsh/alias-v1")
        with self.make_client() as client:
            first = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_alias",
                    "target_member_id": "agent:worker",
                    "content": "alias v1",
                },
            )
        self.assertEqual(first.status_code, 201, first.text)
        first_fingerprint = first.json()["target_binding_snapshot"]["binding_fingerprint"]

        # 只改 alias：六维指纹必须不变（alias 不在指纹内）。
        second_put = self.put_binding(
            "prj_alias",
            "agent:worker",
            self.binding_payload(model_alias="dsh/alias-v2"),
        )
        self.assertEqual(second_put.status_code, 200, second_put.text)
        self.assertEqual(
            second_put.json()["binding"]["binding_fingerprint"], first_fingerprint
        )
        with self.make_client() as client:
            second = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_alias",
                    "target_member_id": "agent:worker",
                    "content": "alias v2",
                },
            )
        self.assertEqual(second.status_code, 201, second.text)
        second_fingerprint = second.json()["target_binding_snapshot"][
            "binding_fingerprint"
        ]
        self.assertEqual(second_fingerprint, first_fingerprint)

        # 再改一次绑定，两版快照都必须逐字节保留（含各自的 alias）。
        self.put_binding(
            "prj_alias",
            "agent:worker",
            self.binding_payload(model_alias="dsh/alias-v3"),
        )
        with self.make_client() as client:
            first_reread = client.get(
                f"/api/tasks/{first.json()['id']}", headers={"X-API-Key": "bobo-key"}
            )
            second_reread = client.get(
                f"/api/tasks/{second.json()['id']}", headers={"X-API-Key": "bobo-key"}
            )
        self.assertEqual(
            json.dumps(first_reread.json()["target_binding_snapshot"], sort_keys=True),
            json.dumps(first.json()["target_binding_snapshot"], sort_keys=True),
        )
        self.assertEqual(
            json.dumps(second_reread.json()["target_binding_snapshot"], sort_keys=True),
            json.dumps(second.json()["target_binding_snapshot"], sort_keys=True),
        )
        self.assertEqual(
            first_reread.json()["target_binding_snapshot"]["model_alias"], "dsh/alias-v1"
        )
        self.assertEqual(
            second_reread.json()["target_binding_snapshot"]["model_alias"], "dsh/alias-v2"
        )
        # 指纹相同 **不等于** 调用配置相同：alias 是原生调用选择参数。
        self.assertEqual(
            first_reread.json()["target_binding_snapshot"]["binding_fingerprint"],
            second_reread.json()["target_binding_snapshot"]["binding_fingerprint"],
        )
        self.assertNotEqual(
            first_reread.json()["target_binding_snapshot"]["model_alias"],
            second_reread.json()["target_binding_snapshot"]["model_alias"],
        )

    def test_offboard_then_rejoin_only_changes_new_tasks(self):
        self._bound_project("prj_roster")
        with self.make_client() as client:
            before = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_roster",
                    "target_member_id": "agent:worker",
                    "content": "in roster",
                },
            )
        self.assertEqual(before.status_code, 201, before.text)
        self.assertEqual(before.json()["target_binding_state"], ROLE_BINDING_BOUND)

        # 离册（全量替换名册，绑定行保留）：新任务如实报 not_in_roster 且行值照存。
        self.sync("prj_roster", [{"member_id": "agent:other"}])
        with self.make_client() as client:
            offboard = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_roster",
                    "target_member_id": "agent:worker",
                    "content": "offboard",
                },
            )
        self.assertEqual(offboard.status_code, 201, offboard.text)
        self.assertEqual(
            offboard.json()["target_binding_state"], ROLE_BINDING_NOT_IN_ROSTER
        )
        offboard_snapshot = offboard.json()["target_binding_snapshot"]
        self.assertEqual(offboard_snapshot["model_id"], b1a_fixtures.MODEL_ID)
        self.assertEqual(offboard_snapshot["binding_fingerprint"], b1a_fixtures.fingerprint_of())

        # 回册：同一行自动回到 bound，新任务取 bound；两个历史快照各自保留。
        self.sync(
            "prj_roster",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        with self.make_client() as client:
            rejoined = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_roster",
                    "target_member_id": "agent:worker",
                    "content": "rejoined",
                },
            )
            first_reread = client.get(
                f"/api/tasks/{before.json()['id']}", headers={"X-API-Key": "bobo-key"}
            )
            offboard_reread = client.get(
                f"/api/tasks/{offboard.json()['id']}", headers={"X-API-Key": "bobo-key"}
            )
        self.assertEqual(rejoined.status_code, 201, rejoined.text)
        self.assertEqual(rejoined.json()["target_binding_state"], ROLE_BINDING_BOUND)
        self.assertEqual(
            first_reread.json()["target_binding_state"], ROLE_BINDING_BOUND
        )
        self.assertEqual(
            offboard_reread.json()["target_binding_state"], ROLE_BINDING_NOT_IN_ROSTER
        )
        self.assertEqual(
            json.dumps(offboard_reread.json()["target_binding_snapshot"], sort_keys=True),
            json.dumps(offboard.json()["target_binding_snapshot"], sort_keys=True),
        )

    def test_legacy_task_with_null_snapshot_columns_stays_unrecorded(self):
        legacy = AgentTask(
            target_member_id="agent:worker",
            created_by="human:bobo",
            content="legacy task without snapshot",
            title="Legacy",
            status="queued",
            workflow_status="assigned",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        with self.session() as session:
            session.add(legacy)
            session.commit()
            session.refresh(legacy)
            legacy_id = legacy.id
        db.init_db()
        with self.make_client() as client:
            listed = client.get(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                params={"target_member_id": "agent:worker"},
            )
            fetched = client.get(
                f"/api/tasks/{legacy_id}", headers={"X-API-Key": "bobo-key"}
            )
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertIsNone(fetched.json()["target_binding_state"])
        self.assertIsNone(fetched.json()["target_binding_snapshot"])
        with self.session() as session:
            row = session.get(AgentTask, legacy_id)
        self.assertIsNone(row.target_binding_state)
        self.assertIsNone(row.target_binding_snapshot)

    def test_client_payload_cannot_write_snapshot_columns(self):
        with self.make_client() as client:
            attempted = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:worker",
                    "content": "try to inject a snapshot",
                    "target_binding_state": "bound",
                    "target_binding_snapshot": {
                        "schema_version": "role-binding-snapshot-1",
                        "state": "bound",
                        "runner_id": "runner:injected",
                    },
                },
            )
        # 旧客户端字段被忽略或 422；无论哪种，服务端都不得落库客户端值。
        self.assertIn(attempted.status_code, {201, 422})
        if attempted.status_code == 201:
            body = attempted.json()
            self.assertEqual(body["target_binding_state"], "no_project")
            self.assertEqual(body["target_binding_snapshot"]["state"], "no_project")
            self.assertIsNone(body["target_binding_snapshot"]["runner_id"])
            stored, state = self._snapshot(body["id"])
            self.assertEqual(state, "no_project")
            self.assertEqual(stored, body["target_binding_snapshot"])

    def test_commit_failure_leaves_no_task_no_hall_and_no_snapshot(self):
        self._bound_project("prj_rollback")
        real_session = Session(self.engine)
        failure = IntegrityError(
            "INSERT INTO agent_task_relations ...",
            {},
            Exception("forced relation conflict"),
        )
        main.app.dependency_overrides[db.get_session] = lambda: real_session
        try:
            with patch.object(real_session, "commit", side_effect=failure):
                with self.make_client() as client:
                    response = client.post(
                        "/api/tasks",
                        headers={"X-API-Key": "bobo-key"},
                        json={
                            "project_id": "prj_rollback",
                            "target_member_id": "agent:worker",
                            "content": "must roll back",
                        },
                    )
        finally:
            main.app.dependency_overrides.pop(db.get_session, None)
            real_session.close()
        self.assertEqual(response.status_code, 409, response.text)
        # 快照与任务/Hall/关系同一次 commit：构造失败整批回滚，不留孤儿。
        self.assertEqual(self._counts(), (0, 0))

    def test_child_authorization_reservation_rolls_back_with_the_same_transaction(self):
        self._bound_project("prj_child_rollback")
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_child_rollback",
                    "target_member_id": "agent:worker",
                    "content": "Root",
                    "may_delegate": True,
                },
            )
            self.assertEqual(root.status_code, 201, root.text)
            claimed = client.post(
                f"/api/tasks/{root.json()['id']}/claim",
                headers={"X-API-Key": "worker-key"},
                json={},
            )
            self.assertEqual(claimed.status_code, 200, claimed.text)
            root_snapshot = json.dumps(
                root.json()["target_binding_snapshot"], sort_keys=True
            )
            statements, capture = self.capture_statements()
            try:
                rejected = client.post(
                    "/api/tasks",
                    headers={"X-API-Key": "worker-key"},
                    json={
                        "parent_task_id": root.json()["id"],
                        "authorization_epoch": claimed.json()["authorization_epoch"],
                        "target_member_id": "agent:other",
                        "content": "exempt without authority",
                        "task_kind": "development",
                        "review_policy": "exempt",
                    },
                )
            finally:
                event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(rejected.status_code, 403, rejected.text)
        # 授权预扣的 UPDATE 与任务构造同次事务：拒绝后整批回滚。
        row = self._task_row(root.json()["id"])
        self.assertEqual(row.reserved_slice_count, 0)
        self.assertEqual(self._counts(), (1, 1))
        self.assertEqual(
            json.dumps(row.target_binding_snapshot, sort_keys=True), root_snapshot
        )
        # 不新增显式 BEGIN / BEGIN IMMEDIATE，也不提前 commit。
        for statement in statements:
            head = statement.strip().upper()
            self.assertFalse(head.startswith("BEGIN"), statement)
            self.assertFalse(head.startswith("COMMIT"), statement)

    def test_unknown_project_keeps_task_create_400_and_project_api_404(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_unknown",
                    "target_member_id": "agent:worker",
                    "content": "unknown project",
                },
            )
        self.assertEqual(created.status_code, 400, created.text)
        self.assertEqual(
            self.get_agents("prj_unknown").status_code, 404
        )
        self.assertEqual(
            self.get_binding("prj_unknown", "agent:worker").status_code, 404
        )
        self.assertEqual(self._counts(), (0, 0))


# ════════════════════════════════════════════════════════════════════
# B6：唯一生产写入点（限定 server/** 的静态检查）
# ════════════════════════════════════════════════════════════════════


class SnapshotWritePointStaticTests(unittest.TestCase):
    """限定生产插入路径：``server/**`` 内只有 ``_create_task_with_hall`` 构造 ``AgentTask``。

    该检查**不覆盖** ``tests/**``（测试夹具允许直接构造 ``AgentTask`` 准备数据），
    也不写“全仓库禁止 ``AgentTask(``”这类过宽禁令（计划 §2.6/B6）。
    """

    ROOT = Path(__file__).resolve().parent.parent

    def _function_block(self, source: str, header: str) -> str:
        start = source.index(header)
        lines = source[start:].splitlines(keepends=True)
        block = [lines[0]]
        for line in lines[1:]:
            if line.startswith("def ") or line.startswith("class ") or line.startswith("@"):
                break
            block.append(line)
        return "".join(block)

    def test_only_unique_write_point_constructs_agent_tasks_in_server(self):
        offenders: list[tuple[str, int, str]] = []
        for path in sorted((self.ROOT / "server").rglob("*.py")):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "AgentTask(" not in line:
                    continue
                if line.strip().startswith("class "):
                    continue
                offenders.append(
                    (path.relative_to(self.ROOT).as_posix(), lineno, line.strip())
                )
        self.assertEqual(len(offenders), 1, offenders)
        relative, _lineno, source_line = offenders[0]
        self.assertEqual(relative, "server/routes/tasks.py")
        self.assertEqual(source_line, "task = AgentTask(")

        tasks_source = (self.ROOT / "server/routes/tasks.py").read_text(encoding="utf-8")
        body = self._function_block(tasks_source, "def _create_task_with_hall(")
        # 唯一构造点就在该函数体内，并且两列作为构造参数写入。
        self.assertIn("task = AgentTask(", body)
        self.assertIn("target_binding_snapshot=binding_snapshot", body)
        self.assertIn('target_binding_state=binding_snapshot["state"]', body)
        # 解析点在函数最开头：早于 Group / GroupMember / AgentTask 的构造。
        self.assertIn("resolve_target_binding_snapshot(", body)
        self.assertLess(
            body.index("resolve_target_binding_snapshot("), body.index("Group(")
        )
        self.assertLess(body.index("resolve_target_binding_snapshot("), body.index("task = AgentTask("))
        # 解析助手只在唯一写入点调用一次；两个入口都走它。
        self.assertEqual(tasks_source.count("resolve_target_binding_snapshot("), 1)
        self.assertEqual(tasks_source.count("_create_task_with_hall("), 3)  # def + 2 调用
