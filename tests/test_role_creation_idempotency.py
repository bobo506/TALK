"""角色生命周期 R1-1：创建幂等、TX-ALL 原子性与凭据恢复（合同 §7.2/§7.7）。

覆盖实施计划 §3.4/§3.6 的 T-R1-a…T-R1-f：

- T-R1-a 六个写入点分别注入异常：单事务整体回滚，六表零残留、**没有操作行**，
  随后同 key 同载荷重试成功；
- T-R1-b 独立连接写入部分行后不提交即放弃（模拟进程被杀）：主连接读不到任何部分事实；
- T-R1-c 并发同 key 同载荷：恰好一个 201（含 Key）、一个 200 ``reused``（不含 Key）；
- T-R1-d 并发同 key 异载荷：一个成功、一个 ``409 operation_key_conflict``，无第二个身份；
- T-R1-e 响应丢失恢复：重放 200 不返 Key，``rotate-key`` 后新 Key 可用、旧 Key 立即 401；
- T-R1-f 归档后同名重建：必然新 ``member_id``，旧角色历史保留。

**真实连接**并发（不是只 mock 函数）：两个线程各持自己的 ``TestClient`` 直打 HTTP。
全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型。
"""

from __future__ import annotations

import sqlite3
import re
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest import mock

from sqlalchemy import event, text
from sqlmodel import select

from server.models import (
    Member,
    Project,
    ProjectAgent,
    ProjectRole,
    ProjectRoleBinding,
    ProjectRoleDescription,
    RoleCreationOperation,
)
from server.routes import projects as projects_route
from tests.test_project_roles import RoleApiTestCase

SIX_TABLES = (
    "members",
    "project_roles",
    "project_agents",
    "project_role_bindings",
    "project_role_descriptions",
    "role_creation_operations",
)

# 夹具成员固定 4 人（human:bobo / human:ann / agent:worker / agent:other），其余五表必须为 0。
BASELINE_COUNTS = {
    "members": 4,
    "project_roles": 0,
    "project_agents": 0,
    "project_role_bindings": 0,
    "project_role_descriptions": 0,
    "role_creation_operations": 0,
}


class _InjectedFailure(RuntimeError):
    pass


class RoleCreationIdempotencyTests(RoleApiTestCase):
    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.register_project("prj_beta")
        self.choice_id = self.seed_runner_and_choice()

    # ── helpers ──────────────────────────────────────────────────────

    def payload(self, *, role_name: str = "dev", operation_key: str = "op-key-1000", **extra):
        body = {
            "role_name": role_name,
            "runner_id": "runner:dsh-cli",
            "choice_id": self.choice_id,
            "operation_key": operation_key,
        }
        body.update(extra)
        return body

    def post_role(self, body: dict, *, project_id: str = "prj_alpha"):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/roles",
                headers={"X-API-Key": "bobo-key"},
                json=body,
            )

    def table_counts(self) -> dict[str, int]:
        with self.session() as session:
            return {
                table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                for table in SIX_TABLES
            }

    # ── T-R1-a 逐步故障注入 ──────────────────────────────────────────

    def test_stepwise_fault_injection_rolls_back_all_six_tables(self):
        injection_targets = (
            ("Member", Member),
            ("ProjectRole", ProjectRole),
            ("ProjectAgent", ProjectAgent),
            ("ProjectRoleBinding", ProjectRoleBinding),
            ("ProjectRoleDescription", ProjectRoleDescription),
            ("RoleCreationOperation", RoleCreationOperation),
        )
        real_add = projects_route._tx_add_role_fact
        for name, target in injection_targets:
            with self.subTest(step=name):
                operation_key = f"op-key-{name.lower()}"
                body = self.payload(
                    role_name=f"role-{name.lower()}",
                    operation_key=operation_key,
                    role_description="说明",
                )
                before = self.table_counts()

                def boom(session, row, *, _target=target):
                    if isinstance(row, _target):
                        raise _InjectedFailure(f"injected failure at {_target.__name__}")
                    return real_add(session, row)

                with mock.patch(
                    "server.routes.projects._tx_add_role_fact", boom
                ):
                    failed = self.post_role(body)
                self.assertEqual(failed.status_code, 500)
                self.assertEqual(failed.json()["detail"], "role_creation_failed")

                # 六表零残留：没有部分身份、也没有操作行（不存在 pending 概念）。
                self.assertEqual(self.table_counts(), before)
                with self.session() as session:
                    columns = {
                        row[1]
                        for row in session.execute(
                            text("PRAGMA table_info(role_creation_operations)")
                        ).fetchall()
                    }
                self.assertNotIn("status", columns)
                self.assertNotIn("error_code", columns)

                # 同 key 同载荷重试 = 首次执行，必须成功且事实完整。
                retried = self.post_role(body)
                self.assertEqual(retried.status_code, 201)
                member_id = retried.json()["member_id"]
                with self.session() as session:
                    self.assertIsNotNone(session.get(Member, member_id))
                    self.assertIsNotNone(
                        session.get(ProjectRole, ("prj_alpha", member_id))
                    )
                    self.assertIsNotNone(
                        session.get(ProjectAgent, ("prj_alpha", member_id))
                    )
                    self.assertIsNotNone(
                        session.get(ProjectRoleBinding, ("prj_alpha", member_id))
                    )
                    self.assertIsNotNone(
                        session.get(RoleCreationOperation, operation_key)
                    )

    # ── T-R1-b 事务中途放弃（模拟宕机） ──────────────────────────────

    def test_abandoned_transaction_leaves_no_partial_facts(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO members (id, kind, display_name, api_key, created_at) "
                "VALUES (?, 'agent', 'ghost', 'ghost-key', ?)",
                ("agent:prj-alpha.ghost-deadbeef", now),
            )
            conn.execute(
                "INSERT INTO project_roles (project_id, member_id, role_name, origin, "
                "identity_exclusive, credential_version, created_by, created_at, updated_at) "
                "VALUES ('prj_alpha', 'agent:prj-alpha.ghost-deadbeef', 'ghost', 'managed', "
                "1, 1, 'human:bobo', ?, ?)",
                (now, now),
            )
            # 不提交即关闭连接：等价于进程被杀后的 SQLite 原子回滚。
        finally:
            conn.close()

        with self.session() as session:
            self.assertIsNone(session.get(Member, "agent:prj-alpha.ghost-deadbeef"))
            self.assertIsNone(
                session.get(
                    ProjectRole, ("prj_alpha", "agent:prj-alpha.ghost-deadbeef")
                )
            )
        self.assertEqual(self.table_counts(), BASELINE_COUNTS)

        # 同 key 重放即首次执行。
        created = self.post_role(self.payload(operation_key="op-key-abandoned"))
        self.assertEqual(created.status_code, 201)

    # ── T-R1-c / T-R1-d 并发 ────────────────────────────────────────

    def _concurrent_post(self, bodies: list[dict]) -> list:
        barrier = threading.Barrier(len(bodies))

        def call(body: dict):
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    "/api/projects/prj_alpha/roles",
                    headers={"X-API-Key": "bobo-key"},
                    json=body,
                )

        with ThreadPoolExecutor(max_workers=len(bodies)) as executor:
            return list(executor.map(call, bodies))

    def test_concurrent_same_key_same_payload_yields_one_creation_one_replay(self):
        body = self.payload(operation_key="op-key-concurrent")
        responses = self._concurrent_post([dict(body), dict(body)])
        codes = sorted(response.status_code for response in responses)
        self.assertEqual(codes, [200, 201])

        created = next(r for r in responses if r.status_code == 201).json()
        replayed = next(r for r in responses if r.status_code == 200).json()
        self.assertFalse(created["reused"])
        self.assertTrue(created["api_key"])
        self.assertTrue(replayed["reused"])
        self.assertNotIn("api_key", replayed)
        self.assertEqual(created["member_id"], replayed["member_id"])

        with self.session() as session:
            operations = list(session.exec(select(RoleCreationOperation)).all())
        self.assertEqual(len(operations), 1)
        self.assertEqual(
            [row.member_id for row in operations], [created["member_id"]]
        )
        # members 表只有夹具 4 人 + 新角色 1 人。
        self.assertEqual(self.table_counts()["members"], 5)
        self.assertEqual(len(self.role_rows()), 1)

    def test_concurrent_same_key_different_payload_conflicts(self):
        responses = self._concurrent_post(
            [
                self.payload(role_name="dev-a", operation_key="op-key-different"),
                self.payload(role_name="dev-b", operation_key="op-key-different"),
            ]
        )
        codes = sorted(response.status_code for response in responses)
        self.assertEqual(codes, [201, 409])
        conflict = next(r for r in responses if r.status_code == 409)
        self.assertEqual(conflict.json()["detail"], "operation_key_conflict")
        self.assertEqual(len(self.role_rows()), 1)
        self.assertEqual(self.table_counts()["members"], 5)

    # ── 幂等语义：重放不因目录下架/改名而阻断 ────────────────────────

    def test_replay_after_choice_retirement_and_role_rename(self):
        body = self.payload(operation_key="op-key-replay-retired", role_name="dev")
        created = self.post_role(body)
        self.assertEqual(created.status_code, 201)
        member_id = created.json()["member_id"]

        with self.make_client() as client:
            client.patch(
                f"/api/runners/runner:dsh-cli/model-choices/{self.choice_id}",
                headers={"X-API-Key": "bobo-key"},
                json={"retired_at": "2026-10-11T00:00:00+00:00"},
            )
        self.patch_role("prj_alpha", member_id, {"role_name": "改名后"})

        replayed = self.post_role(body)
        self.assertEqual(replayed.status_code, 200)
        self.assertTrue(replayed.json()["reused"])
        self.assertNotIn("api_key", replayed.json())
        self.assertEqual(replayed.json()["member_id"], member_id)
        self.assertEqual(replayed.json()["role"]["role_name"], "改名后")
        self.assertEqual(
            replayed.json()["role"]["model"]["choice_id"], self.choice_id
        )

    def test_same_key_other_project_is_conflict(self):
        body = self.payload(operation_key="op-key-cross-project")
        self.assertEqual(self.post_role(body).status_code, 201)
        other = self.post_role(body, project_id="prj_beta")
        self.assertEqual(other.status_code, 409)
        self.assertEqual(other.json()["detail"], "operation_key_conflict")
        self.assertEqual(len(self.role_rows("prj_beta")), 0)

    def test_no_operation_in_progress_code_exists(self):
        body = self.payload(operation_key="op-key-no-pending")
        self.assertEqual(self.post_role(body).status_code, 201)
        body["role_name"] = "other"
        conflict = self.post_role(body)
        self.assertEqual(conflict.status_code, 409)
        self.assertNotEqual(conflict.json()["detail"], "operation_in_progress")

    # ── T-R1-e 响应丢失恢复 ─────────────────────────────────────────

    def test_lost_response_then_replay_then_rotate(self):
        body = self.payload(operation_key="op-key-lost-response")
        created = self.post_role(body)
        self.assertEqual(created.status_code, 201)
        first_key = created.json()["api_key"]
        member_id = created.json()["member_id"]

        replayed = self.post_role(body)
        self.assertEqual(replayed.status_code, 200)
        self.assertNotIn("api_key", replayed.json())

        rotated = self.rotate_key("prj_alpha", member_id)
        self.assertEqual(rotated.status_code, 200)
        new_key = rotated.json()["api_key"]
        self.assertEqual(rotated.json()["credential_version"], 2)
        self.assertNotEqual(new_key, first_key)

        with self.make_client() as client:
            self.assertEqual(
                client.get(
                    "/api/members/me", headers={"X-API-Key": first_key}
                ).status_code,
                401,
            )
            self.assertEqual(
                client.get(
                    "/api/members/me", headers={"X-API-Key": new_key}
                ).status_code,
                200,
            )
        with self.session() as session:
            self.assertEqual(session.get(Member, member_id).api_key, new_key)
            self.assertEqual(
                session.get(
                    ProjectRole, ("prj_alpha", member_id)
                ).credential_version,
                2,
            )

    # ── T-R1-f 归档后同名重建 ────────────────────────────────────────

    def test_archived_name_can_be_rebuilt_with_new_identity(self):
        first = self.post_role(
            self.payload(operation_key="op-key-archive-1", role_name="dev")
        )
        self.assertEqual(first.status_code, 201)
        old_member_id = first.json()["member_id"]
        self.archive_role("prj_alpha", old_member_id)

        rebuilt = self.post_role(
            self.payload(operation_key="op-key-archive-2", role_name="dev")
        )
        self.assertEqual(rebuilt.status_code, 201)
        self.assertNotEqual(rebuilt.json()["member_id"], old_member_id)
        self.assertEqual(len(self.operation_rows()), 2)
        with self.session() as session:
            self.assertIsNotNone(
                session.get(ProjectRole, ("prj_alpha", old_member_id)).archived_at
            )
            self.assertIsNone(
                session.get(
                    ProjectRole, ("prj_alpha", rebuilt.json()["member_id"])
                ).archived_at
            )


    # ── 实际 SQL 写入之后的故障注入（不是 session.add 队列阶段） ──────

    def test_fault_after_actual_sql_write_rolls_back_all_six_tables(self):
        """在 ``after_cursor_execute`` 观察**真实 INSERT 已执行**之后再抛异常。

        区别于 T-R1-a 的 ``session.add`` 阶段注入：这里故障发生时该表已经真的执行了
        ``INSERT`` 语句，用来证明“修后 TX-ALL 仍整体回滚”，而不是只证明“还没写”。
        """
        for target in SIX_TABLES:
            with self.subTest(target=target):
                before = self.table_counts()
                executed: list[str] = []

                def inject(
                    conn,
                    cursor,
                    statement,
                    parameters,
                    context,
                    executemany,
                    *,
                    _target=target,
                    _executed=executed,
                ):
                    match = re.match(r"INSERT INTO ([a-z_]+)", statement, re.I)
                    if match and match.group(1) in SIX_TABLES:
                        _executed.append(match.group(1))
                        if match.group(1) == _target:
                            raise _InjectedFailure(
                                f"fault after actual SQL INSERT into {_target}"
                            )

                event.listen(self.engine, "after_cursor_execute", inject)
                try:
                    body = self.payload(
                        role_name=f"sql-fault-{target}",
                        operation_key=f"op-key-sql-{target}",
                        role_description="说明",
                    )
                    failed = self.post_role(body)
                finally:
                    event.remove(self.engine, "after_cursor_execute", inject)

                self.assertEqual(failed.status_code, 500)
                self.assertEqual(failed.json()["detail"], "role_creation_failed")
                # 证据：注入点之前确实发生过真实 SQL 写入。
                self.assertIn(target, executed)
                self.assertEqual(self.table_counts(), before)

                retried = self.post_role(body)
                self.assertEqual(retried.status_code, 201)

    # ── F3 补正：TX-ALL 写锁内复查真实项目 ───────────────────────────

    def test_project_unregistered_after_precheck_yields_404_without_facts(self):
        """注销先提交：创建在写锁内复查真实项目 → 404 且六表零新增。

        复现独立探针（extra-probes-api.json）：首次 ``_get_project`` 之后由第二个
        ``TestClient`` 经**正式 DELETE 项目 API** 注销（204），创建请求随后到达。
        修前仍 201 并产生新身份而项目行不存在；修后 TX-ALL 内的事实 SQL 命中 404。
        """
        before = self.table_counts()
        real_get_project = projects_route._get_project
        deleted: list[int] = []
        counts_after_delete: list[dict] = []
        armed = [True]

        def read_then_unregister(project_id, session):
            project = real_get_project(project_id, session)
            if not armed[0]:
                return project
            armed[0] = False
            with self.make_client() as client:
                removed = client.delete(
                    f"/api/projects/{project_id}",
                    headers={"X-API-Key": "bobo-key"},
                )
            deleted.append(removed.status_code)
            # 注销 API 自身会清理本项目绑定/说明行（既有清理语义）：以**注销之后**
            # 为基线，验证创建请求没有再新增任何六表事实。
            counts_after_delete.append(self.table_counts())
            return project

        with mock.patch.object(
            projects_route, "_get_project", read_then_unregister
        ):
            response = self.post_role(
                self.payload(role_name="orphan role", operation_key="op-key-orphan")
            )

        self.assertEqual(deleted, [204])
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "project not found")
        self.assertNotIn("member_id", response.json())
        self.assertEqual(counts_after_delete, [self.table_counts()])
        self.assertEqual(self.table_counts(), before)
        with self.session() as session:
            self.assertIsNone(session.get(Project, "prj_alpha"))

    def test_creation_holding_write_lock_serializes_project_unregister(self):
        """创建先持锁：注销必须在写锁上排队，随后保持既有注销清理语义。"""
        real_allocate_key = projects_route._allocate_role_api_key
        entered = threading.Event()
        release = threading.Event()
        started = threading.Event()
        delete_was_blocked = False

        def gated_allocate_key(session):
            entered.set()
            release.wait(timeout=15)
            return real_allocate_key(session)

        def create():
            return self.post_role(
                self.payload(role_name="locked role", operation_key="op-key-locked")
            )

        def unregister():
            started.set()
            with self.make_client() as client:
                return client.delete(
                    "/api/projects/prj_alpha", headers={"X-API-Key": "bobo-key"}
                )

        with mock.patch.object(
            projects_route, "_allocate_role_api_key", gated_allocate_key
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                create_future = executor.submit(create)
                delete_future = None
                try:
                    entered_ok = entered.wait(timeout=15)
                    if entered_ok:
                        # 创建已通过写锁内的项目复查并停在写入阶段。
                        delete_future = executor.submit(unregister)
                        self.assertTrue(started.wait(timeout=15))
                        time.sleep(0.6)
                        delete_was_blocked = not delete_future.done()
                finally:
                    release.set()
                created = create_future.result(timeout=30)
                removed = (
                    delete_future.result(timeout=30)
                    if delete_future is not None
                    else None
                )

        self.assertTrue(entered_ok, "创建未进入 TX-ALL 写入阶段")
        self.assertTrue(delete_was_blocked, "注销未被创建持有中的写锁串行化")
        self.assertEqual(created.status_code, 201)
        self.assertIsNotNone(removed)
        self.assertEqual(removed.status_code, 204)
        with self.session() as session:
            self.assertIsNone(session.get(Project, "prj_alpha"))


if __name__ == "__main__":
    unittest.main()
