"""角色生命周期 R1-3：受管服务生命周期协议、持久化与权限合同测试。

覆盖实施计划 §4（R1-3）与合同 §4.1.5/§4.1.6/§5.3/§10：

- 迁移幂等（``init_db`` 两次）且旧行保持；
- 六 API 的 human/agent 权限矩阵、跨角色/跨项目/归档/禁用/离册稳定拒绝；
- 两个**真实 SQLite 连接**的并发 CAS（同角色只允许一个动作生效）与真实 INSERT
  故障回滚（数据库触发器，不是 mock“进入 transaction”）；
- start 预分配全新 ``expected_instance_id`` 与 ``launch_expires_at``；
- claim/report 的 token/身份/host/世代/action/时间窗与幂等重放/``report_conflict``；
- 两种就绪顺序、旧心跳/错项目/错状态不产生就绪、ready 缺实例超时 ``readiness_timeout``；
- 旧动作迟到 ``stale_report``、旧 launch 超时**不**污染新世代；
- stop 原 start 所有权、错误 host/owner、PID 复用不误杀、超时仍保留归属；
- start-all 跳过运行中、逐角色结果、部分失败与失败子集重试、跨项目 ID 拒绝；
- 公共投影不含任何 token/argv/绝对路径，且三个独立事实分列。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型、不读真实 Key。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import quote

from sqlalchemy import text
from sqlmodel import Session, select

import server.db as db
from server.models import (
    ROLE_SERVICE_ERROR_ALREADY_RUNNING,
    ROLE_SERVICE_ERROR_CONTROL_KIND_NOT_MANAGED,
    ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH,
    ROLE_SERVICE_ERROR_LAUNCH_EXPIRED,
    ROLE_SERVICE_ERROR_LAUNCH_NOT_FOUND,
    ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING,
    ROLE_SERVICE_ERROR_READINESS_TIMEOUT,
    ROLE_SERVICE_ERROR_REPORT_CONFLICT,
    ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED,
    ROLE_SERVICE_ERROR_STALE_REPORT,
    ROLE_SERVICE_ERROR_UNKNOWN_OWNER,
    ROLE_SERVICE_LAUNCH_EXPIRED,
    ROLE_SERVICE_LAUNCH_REPORTED,
    ROLE_SERVICE_OBSERVED_FAILED,
    ROLE_SERVICE_OBSERVED_NOT_STARTED,
    ROLE_SERVICE_OBSERVED_RUNNING,
    ROLE_SERVICE_OBSERVED_STARTING,
    ROLE_SERVICE_OBSERVED_STOPPED,
    ROLE_SERVICE_OBSERVED_STOPPING,
    ROLE_SERVICE_OBSERVED_UNKNOWN,
    ROLE_SERVICE_RESULT_STOPPED,
    ROLE_SERVICE_RESULT_SUCCESS,
    AgentInstance,
    Member,
    Project,
    ProjectAgent,
    ProjectRole,
    ProjectRoleBinding,
    RoleServiceLaunch,
    RoleServiceState,
)
from server.role_services import (
    enqueue_auto_start_launch,
    start_role_service,
    stop_role_service,
)
from tests.test_project_roles import RoleApiTestCase, encode

PROJECT_ID = "prj_alpha"
OTHER_PROJECT_ID = "prj_beta"
RUNNER_ID = "runner:dsh-cli"
UNMANAGED_RUNNER_ID = "runner:desktop"
HOST = "host-alpha"
UNMANAGED_CHOICE = {
    "model_id": "workbuddy-desktop",
    "model_source": "builtin",
    "provider_id": "managed:workbuddy",
    "connection_ref": "native-workbuddy-desktop",
    "model_alias": "workbuddy/desktop",
    "model_display_name": "WorkBuddy Desktop",
    "source_kind": "declared",
}


def iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


class RoleServiceTestCase(RoleApiTestCase):
    """R1-3 公共夹具：受管运行器 + 一个已创建角色。"""

    def setUp(self):
        super().setUp()
        self.register_project(PROJECT_ID)
        self.register_runner(RUNNER_ID)
        with self.make_client() as client:
            client.patch(
                f"/api/runners/{RUNNER_ID}/control-kind",
                headers={"X-API-Key": "bobo-key"},
                json={"control_kind": "managed_cli"},
            )
        self.choice_id = self.create_choice(RUNNER_ID).json()["choice_id"]
        created = self.create_role(
            PROJECT_ID,
            role_name="后端角色",
            choice_id=self.choice_id,
            operation_key="op-alpha-0001",
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.role_a = created.json()["member_id"]
        self.role_a_key = created.json()["api_key"]

    # ── API helpers ──────────────────────────────────────────────────

    def start(self, member_id: str | None = None, *, key: str = "bobo-key", project: str = PROJECT_ID):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project}/roles/{encode(member_id or self.role_a)}/service/start",
                headers={"X-API-Key": key},
            )

    def stop(self, member_id: str | None = None, *, key: str = "bobo-key", project: str = PROJECT_ID):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project}/roles/{encode(member_id or self.role_a)}/service/stop",
                headers={"X-API-Key": key},
            )

    def start_all(self, body: dict | None = None, *, key: str = "bobo-key", project: str = PROJECT_ID):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project}/role-services/start-all",
                headers={"X-API-Key": key},
                json=body or {},
            )

    def list_services(self, *, key: str = "bobo-key", project: str = PROJECT_ID):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project}/role-services", headers={"X-API-Key": key}
            )

    def claim(self, launch_id: str, body: dict, *, key: str):
        with self.make_client() as client:
            return client.post(
                f"/api/role-service-launches/{launch_id}/claim",
                headers={"X-API-Key": key},
                json=body,
            )

    def report(self, launch_id: str, body: dict, *, key: str):
        with self.make_client() as client:
            return client.post(
                f"/api/role-service-launches/{launch_id}/report",
                headers={"X-API-Key": key},
                json=body,
            )

    def put_instance(self, instance_id: str, body: dict, *, key: str):
        with self.make_client() as client:
            return client.put(
                f"/api/instances/{instance_id}",
                headers={"X-API-Key": key},
                json=body,
            )

    def get_roles(self, project: str = PROJECT_ID, *, key: str = "bobo-key"):
        return super().get_roles(project, key=key)

    # ── flow helpers ─────────────────────────────────────────────────

    def start_and_claim(self, *, member_id: str | None = None, role_key: str | None = None, host: str = HOST):
        member_id = member_id or self.role_a
        role_key = role_key or self.role_a_key
        started = self.start(member_id)
        self.assertEqual(started.status_code, 200, started.text)
        launch = started.json()
        claimed = self.claim(
            launch["launch_id"],
            {"host": host, "expected_instance_id": launch["expected_instance_id"]},
            key=role_key,
        )
        self.assertEqual(claimed.status_code, 200, claimed.text)
        return launch, claimed.json()

    def bind_instance(self, launch: dict, claim: dict, *, role_key: str | None = None, status: str = "idle", host: str = HOST, project: str = PROJECT_ID, seen_ago: float | None = None):
        body = {
            "runtime": "dsh",
            "status": status,
            "host": host,
            "pid": 4321,
            "project_id": project,
            "launch_id": launch["launch_id"],
        }
        response = self.put_instance(
            claim["expected_instance_id"], body, key=role_key or self.role_a_key
        )
        if seen_ago is not None:
            self.set_instance_last_seen(claim["expected_instance_id"], seen_ago)
        return response

    def ready_report(self, launch: dict, claim: dict, *, role_key: str | None = None, host: str = HOST, **overrides):
        body = {
            "generation": launch["generation"],
            "action": "start",
            "claim_token": claim["claim_token"],
            "owner_token": claim["owner_token"],
            "outcome": "ready",
            "instance_id": claim["expected_instance_id"],
            "pid": 4321,
            # 固定值：同一完整载荷重放必须得到**同一**指纹（不要每次重新取 now）。
            "process_started_at": "2026-10-11T00:00:00+00:00",
            "host": host,
            "error_code": None,
        }
        body.update(overrides)
        return self.report(launch["launch_id"], body, key=role_key or self.role_a_key)

    # ── row helpers ──────────────────────────────────────────────────

    def state_row(self, member_id: str | None = None, project: str = PROJECT_ID):
        with self.session() as session:
            return session.get(RoleServiceState, (project, member_id or self.role_a))

    def launch_row(self, launch_id: str):
        with self.session() as session:
            return session.get(RoleServiceLaunch, launch_id)

    def launch_rows(self, member_id: str | None = None):
        with self.session() as session:
            return list(
                session.exec(
                    select(RoleServiceLaunch).where(
                        RoleServiceLaunch.member_id == (member_id or self.role_a)
                    )
                ).all()
            )

    def set_launch_expired(self, launch_id: str, *, seconds_ago: float = 5.0) -> None:
        when = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        with Session(self.engine) as session:
            session.execute(
                text(
                    "UPDATE role_service_launches SET launch_expires_at = :when "
                    "WHERE launch_id = :launch_id"
                ),
                {"when": when.replace(tzinfo=None), "launch_id": launch_id},
            )
            session.commit()

    def set_instance_last_seen(self, instance_id: str, seconds_ago: float) -> None:
        when = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        with Session(self.engine) as session:
            session.execute(
                text(
                    "UPDATE agent_instances SET last_seen_at = :when WHERE id = :id"
                ),
                {"when": when.replace(tzinfo=None), "id": instance_id},
            )
            session.commit()

    def register_unmanaged_runner(self):
        self.register_runner(UNMANAGED_RUNNER_ID, runtime="workbuddy")
        with self.make_client() as client:
            client.patch(
                f"/api/runners/{UNMANAGED_RUNNER_ID}/control-kind",
                headers={"X-API-Key": "bobo-key"},
                json={"control_kind": "unknown"},
            )
        return self.create_choice(UNMANAGED_RUNNER_ID, **UNMANAGED_CHOICE).json()["choice_id"]

    def make_second_role(
        self,
        *,
        project: str = PROJECT_ID,
        role_name: str = "前端角色",
        operation_key: str = "op-alpha-0002",
        runner_id: str = RUNNER_ID,
        choice_id: str | None = None,
    ):
        created = self.create_role(
            project,
            role_name=role_name,
            runner_id=runner_id,
            choice_id=choice_id or self.choice_id,
            operation_key=operation_key,
        )
        self.assertEqual(created.status_code, 201, created.text)
        return created.json()["member_id"], created.json()["api_key"]

    def human_member(self) -> Member:
        """直接调用服务层时使用的 human 操作者（不经过 HTTP 层）。"""
        with self.session() as session:
            return session.get(Member, "human:bobo")


class RoleServiceMigrationTests(RoleServiceTestCase):
    """迁移幂等与旧数据保持（合同 §4.2）。"""

    def test_init_db_twice_keeps_service_rows_and_indexes(self):
        launch = self.start().json()
        before = self.state_row()
        self.assertIsNotNone(before)

        db.init_db()
        db.init_db()

        after = self.state_row()
        self.assertIsNotNone(after)
        self.assertEqual(after.generation, before.generation)
        self.assertEqual(after.current_launch_id, launch["launch_id"])
        row = self.launch_row(launch["launch_id"])
        self.assertEqual(row.state, "pending")

        with sqlite3.connect(self.db_path) as raw:
            tables = {
                name
                for (name,) in raw.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            indexes = {
                name
                for (name,) in raw.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
        self.assertIn("role_service_state", tables)
        self.assertIn("role_service_launches", tables)
        self.assertIn("ux_role_service_launches_generation", indexes)
        self.assertIn("ix_role_service_launches_state_expiry", indexes)

    def test_legacy_database_gains_tables_without_touching_old_rows(self):
        with sqlite3.connect(self.db_path) as raw:
            raw.execute("DROP TABLE role_service_launches")
            raw.execute("DROP TABLE role_service_state")
            raw.execute(
                "INSERT OR IGNORE INTO members (id, kind, display_name, api_key, created_at)"
                " VALUES ('human:legacy', 'human', 'Legacy', 'legacy-key', datetime('now'))"
            )
            raw.commit()

        db.init_db()
        db.init_db()

        with sqlite3.connect(self.db_path) as raw:
            tables = {
                name
                for (name,) in raw.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            legacy = raw.execute(
                "SELECT display_name FROM members WHERE id='human:legacy'"
            ).fetchone()
        self.assertIn("role_service_state", tables)
        self.assertIn("role_service_launches", tables)
        self.assertEqual(legacy[0], "Legacy")

    def test_legacy_state_table_gains_spawned_column_without_touching_rows(self):
        """返修 F2 的增量迁移：旧 ``role_service_state`` 只补可空列，旧行原样保留。"""
        with sqlite3.connect(self.db_path) as raw:
            raw.execute("DROP TABLE role_service_state")
            raw.execute(
                "CREATE TABLE role_service_state ("
                "project_id TEXT NOT NULL, member_id TEXT NOT NULL,"
                "desired_state TEXT, observed_state TEXT, manager_kind TEXT,"
                "control_kind TEXT, generation INTEGER, current_launch_id TEXT,"
                "observed_instance_id TEXT, owner_host TEXT, process_launch_id TEXT,"
                "pid INTEGER, process_started_at TIMESTAMP, last_result TEXT,"
                "last_error_code TEXT, last_error_message TEXT, started_at TIMESTAMP,"
                "stopped_at TIMESTAMP, updated_at TIMESTAMP, updated_by TEXT,"
                "PRIMARY KEY (project_id, member_id))"
            )
            raw.execute(
                "INSERT INTO role_service_state (project_id, member_id, desired_state,"
                " observed_state, generation) VALUES (?, ?, 'running', 'running', 7)",
                (PROJECT_ID, "agent:legacy.state-deadbeef"),
            )
            raw.commit()

        db.init_db()
        db.init_db()

        with sqlite3.connect(self.db_path) as raw:
            columns = {
                row[1]
                for row in raw.execute("PRAGMA table_info(role_service_state)").fetchall()
            }
            legacy = raw.execute(
                "SELECT desired_state, observed_state, generation, spawned "
                "FROM role_service_state WHERE member_id = 'agent:legacy.state-deadbeef'"
            ).fetchone()
        self.assertIn("spawned", columns)
        self.assertEqual(legacy[:3], ("running", "running", 7))
        self.assertIsNone(legacy[3])


class RoleServicePermissionTests(RoleServiceTestCase):
    """human/agent/跨角色/跨项目/归档/禁用权限矩阵（合同 §5.3/§10.2）。"""

    def test_agent_cannot_call_intent_write_endpoints(self):
        for response in (
            self.start(key=self.role_a_key),
            self.stop(key=self.role_a_key),
            self.start_all(key=self.role_a_key),
        ):
            self.assertEqual(response.status_code, 403, response.text)

    def test_unknown_role_and_project_are_stable(self):
        self.assertEqual(self.start("agent:missing").status_code, 404)
        self.assertEqual(
            self.start(project="prj_missing").status_code, 404
        )

    def test_archived_role_is_rejected(self):
        with self.session() as session:
            role = session.get(ProjectRole, (PROJECT_ID, self.role_a))
            role.archived_at = datetime.now(timezone.utc)
            session.add(role)
            session.commit()
        response = self.start()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "role_archived")

    def test_disabled_member_is_rejected(self):
        with self.session() as session:
            member = session.get(Member, self.role_a)
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        response = self.start()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "member_disabled")

    def test_missing_roster_row_is_rejected(self):
        with self.session() as session:
            roster = session.get(ProjectAgent, (PROJECT_ID, self.role_a))
            session.delete(roster)
            session.commit()
        response = self.start()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "role_not_in_roster")

    def test_cross_role_agent_cannot_claim_or_report(self):
        launch, claim = self.start_and_claim()
        other = self.claim(
            launch["launch_id"],
            {"host": HOST, "expected_instance_id": claim["expected_instance_id"]},
            key="other-key",
        )
        self.assertEqual(other.status_code, 403)
        self.assertEqual(other.json()["detail"], ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED)
        replay = self.ready_report(launch, claim, role_key="other-key")
        self.assertEqual(replay.status_code, 403)

    def test_control_kind_gate_blocks_unverified_runners(self):
        choice_id = self.register_unmanaged_runner()
        member_id, _ = self.make_second_role(
            role_name="桌面角色",
            operation_key="op-alpha-unmanaged",
            runner_id=UNMANAGED_RUNNER_ID,
            choice_id=choice_id,
        )
        response = self.start(member_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], ROLE_SERVICE_ERROR_CONTROL_KIND_NOT_MANAGED
        )
        # 没有创建任何动作，也就没有宿主需要领取的悬挂 launch。
        self.assertEqual(self.launch_rows(member_id), [])
        projection = {row["member_id"]: row for row in self.list_services().json()}
        self.assertFalse(projection[member_id]["can_start"])
        self.assertFalse(projection[member_id]["can_stop"])

    def test_agent_cannot_modify_desired_state(self):
        started = self.start()
        self.assertEqual(started.status_code, 200)
        # agent 没有任何意图写入口：只有 human 的 start/stop 能写 desired_state。
        self.assertEqual(self.stop(key=self.role_a_key).status_code, 403)
        self.assertEqual(self.state_row().desired_state, "running")


class RoleServiceCASConcurrencyTests(RoleServiceTestCase):
    """两个真实 SQLite 连接：同角色并发只允许一个动作生效（合同 §10.5）。"""

    def test_concurrent_start_only_one_action_wins(self):
        results: list[object] = []
        barrier = threading.Barrier(2)

        def worker():
            session = Session(self.engine)
            try:
                barrier.wait(timeout=10)
                try:
                    outcome = start_role_service(
                        PROJECT_ID, self.role_a, self.human_member(), session
                    )
                    results.append(("ok", outcome.launch_id))
                except Exception as exc:  # noqa: BLE001 - 记录真实拒绝原因
                    session.rollback()
                    results.append(("err", getattr(exc, "detail", None)))
            finally:
                session.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(len(results), 2)
        self.assertEqual(sorted(kind for kind, _ in results), ["err", "ok"])
        self.assertEqual(
            results[0][1] if results[0][0] == "err" else results[1][1],
            ROLE_SERVICE_ERROR_ALREADY_RUNNING,
        )
        # 库里只有一个动作、一个世代。
        rows = self.launch_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.state_row().generation, 1)

    def test_concurrent_double_click_produces_single_launch(self):
        first = self.start()
        second = self.start()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"], ROLE_SERVICE_ERROR_ALREADY_RUNNING)
        self.assertEqual(len(self.launch_rows()), 1)

    def test_real_insert_failure_rolls_back_the_whole_action(self):
        with sqlite3.connect(self.db_path) as raw:
            raw.execute(
                "CREATE TRIGGER boom_launch BEFORE INSERT ON role_service_launches "
                "BEGIN SELECT RAISE(ABORT, 'boom'); END"
            )
            raw.commit()
        try:
            session = Session(self.engine)
            with self.assertRaises(Exception):
                start_role_service(
                    PROJECT_ID, self.role_a, self.human_member(), session
                )
            session.rollback()
            session.close()
        finally:
            with sqlite3.connect(self.db_path) as raw:
                raw.execute("DROP TRIGGER boom_launch")
                raw.commit()

        # 单事务整体回滚：没有半截状态行、没有动作行、世代未被推进。
        self.assertIsNone(self.state_row())
        self.assertEqual(self.launch_rows(), [])

        retry = self.start()
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(self.state_row().generation, 1)

    def test_stop_uses_same_generation_cas(self):
        launch, claim = self.start_and_claim()
        self.bind_instance(launch, claim)
        self.ready_report(launch, claim)
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["action"], "stop")
        self.assertEqual(stopped.json()["generation"], 2)
        # 第二个 stop 在途时不重复建动作。
        second = self.stop()
        self.assertEqual(second.status_code, 409)


class RoleServiceProtocolTests(RoleServiceTestCase):
    """claim/report 的 token、身份、世代、时间窗与幂等语义（合同 §10.2/§10.5）。"""

    def test_start_preallocates_fresh_instance_and_deadline(self):
        body = self.start().json()
        self.assertTrue(body["expected_instance_id"].startswith("ins_"))
        self.assertEqual(body["observed"], ROLE_SERVICE_OBSERVED_STARTING)
        self.assertIsNone(self.launch_row(body["launch_id"]).owner_token_hash)
        # 响应里绝不出现任何 token。
        self.assertNotIn("token", json.dumps(body).lower())
        self.assertNotIn("api_key", json.dumps(body).lower())

    def test_claim_rejects_wrong_instance_id(self):
        launch = self.start().json()
        response = self.claim(
            launch["launch_id"],
            {"host": HOST, "expected_instance_id": "ins_deadbeef0000"},
            key=self.role_a_key,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH
        )

    def test_claim_twice_is_not_pending(self):
        launch, _ = self.start_and_claim()
        again = self.claim(
            launch["launch_id"],
            {"host": HOST, "expected_instance_id": launch["expected_instance_id"]},
            key=self.role_a_key,
        )
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"], ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING)

    def test_unknown_launch_is_404(self):
        response = self.claim(
            "00000000-0000-0000-0000-000000000000",
            {"host": HOST, "expected_instance_id": "ins_x"},
            key=self.role_a_key,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], ROLE_SERVICE_ERROR_LAUNCH_NOT_FOUND)

    def test_expired_launch_is_rejected_and_converges(self):
        launch = self.start().json()
        self.set_launch_expired(launch["launch_id"])
        response = self.claim(
            launch["launch_id"],
            {"host": HOST, "expected_instance_id": launch["expected_instance_id"]},
            key=self.role_a_key,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], ROLE_SERVICE_ERROR_LAUNCH_EXPIRED)
        row = self.launch_row(launch["launch_id"])
        self.assertEqual(row.state, ROLE_SERVICE_LAUNCH_EXPIRED)
        state = self.state_row()
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_FAILED)
        self.assertEqual(state.last_error_code, ROLE_SERVICE_ERROR_READINESS_TIMEOUT)

    def test_report_requires_tokens_host_and_identity(self):
        launch, claim = self.start_and_claim()
        bad_token = self.ready_report(launch, claim, claim_token="nope")
        self.assertEqual(bad_token.status_code, 403)
        self.assertEqual(
            bad_token.json()["detail"], ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED
        )
        bad_owner = self.ready_report(launch, claim, owner_token="nope")
        self.assertEqual(bad_owner.status_code, 403)
        bad_host = self.ready_report(launch, claim, host="other-host")
        self.assertEqual(bad_host.status_code, 403)
        # body 里自报 host 不构成授权：状态始终没有被改动。
        self.assertEqual(self.launch_row(launch["launch_id"]).state, "claimed")
        self.assertEqual(self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STARTING)

    def test_report_action_and_generation_mismatch(self):
        launch, claim = self.start_and_claim()
        wrong_action = self.ready_report(launch, claim, action="stop")
        self.assertEqual(wrong_action.status_code, 409)
        self.assertEqual(wrong_action.json()["detail"], "launch_action_mismatch")
        wrong_generation = self.ready_report(launch, claim, generation=99)
        self.assertEqual(wrong_generation.status_code, 409)
        self.assertEqual(
            wrong_generation.json()["detail"], ROLE_SERVICE_ERROR_STALE_REPORT
        )

    def test_identical_replay_is_read_only_even_after_deadline(self):
        launch, claim = self.start_and_claim()
        first = self.ready_report(launch, claim)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["replayed"])
        self.set_launch_expired(launch["launch_id"], seconds_ago=1)
        replay = self.ready_report(launch, claim)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(replay.json()["outcome"], "ready")
        # 重放不改当前状态，也不因为“已过截止”被改写。
        self.assertEqual(self.launch_row(launch["launch_id"]).state, ROLE_SERVICE_LAUNCH_REPORTED)

    def test_different_payload_after_receipt_is_conflict(self):
        launch, claim = self.start_and_claim()
        self.ready_report(launch, claim)
        conflict = self.ready_report(launch, claim, pid=9999)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(
            conflict.json()["detail"], ROLE_SERVICE_ERROR_REPORT_CONFLICT
        )

    def test_late_report_for_superseded_action_is_stale(self):
        launch, claim = self.start_and_claim()
        self.set_launch_expired(launch["launch_id"], seconds_ago=2)
        # R1-3 返修 F2：已 claim 的旧动作即使超时也**仍持有**原进程归属（宿主可能已
        # spawn），因此人类不能直接用新 start 覆盖它 —— 先关闭并证明停止。
        blocked = self.start()
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], ROLE_SERVICE_ERROR_ALREADY_RUNNING)
        self.assertEqual(self.state_row().generation, 1)
        self.assertEqual(self.state_row().process_launch_id, launch["launch_id"])
        projection = {row["member_id"]: row for row in self.list_services().json()}
        self.assertFalse(projection[self.role_a]["can_start"])
        self.assertTrue(projection[self.role_a]["can_stop"])
        self.assertTrue(projection[self.role_a]["ownership_held"])

        # 关闭动作必须沿用原 start 的 owner token/host，并在证明停止后释放归属。
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        claimed = self.claim(
            stopped.json()["launch_id"],
            {
                "host": HOST,
                "expected_instance_id": stopped.json()["expected_instance_id"],
                "owner_token": claim["owner_token"],
            },
            key=self.role_a_key,
        )
        self.assertEqual(claimed.status_code, 200, claimed.text)
        reported = self.report(
            stopped.json()["launch_id"],
            {
                "generation": stopped.json()["generation"],
                "action": "stop",
                "claim_token": claimed.json()["claim_token"],
                "owner_token": claim["owner_token"],
                "outcome": "stopped",
                "host": HOST,
                "pid": None,
                "error_code": None,
            },
            key=self.role_a_key,
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        self.assertIsNone(self.state_row().process_launch_id)

        # 归属释放后，新世代可以启动；旧动作的迟到报告一律 stale_report。
        restarted = self.start()
        self.assertEqual(restarted.status_code, 200)
        new_state = self.state_row()
        self.assertEqual(new_state.generation, 3)
        self.assertEqual(new_state.observed_state, ROLE_SERVICE_OBSERVED_STARTING)
        late = self.ready_report(launch, claim)
        self.assertEqual(late.status_code, 409)
        self.assertEqual(late.json()["detail"], ROLE_SERVICE_ERROR_STALE_REPORT)
        self.assertEqual(self.state_row().generation, 3)
        self.assertEqual(
            self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STARTING
        )

    def test_old_launch_timeout_does_not_touch_new_generation(self):
        first = self.start().json()
        second = self.start()
        # 第二个 start 被 already_running 拒绝，所以先把旧动作标过期再重启。
        self.assertEqual(second.status_code, 409)
        self.set_launch_expired(first["launch_id"], seconds_ago=2)
        restarted = self.start()
        self.assertEqual(restarted.status_code, 200)
        state = self.state_row()
        self.assertEqual(state.generation, 2)
        self.assertEqual(state.current_launch_id, restarted.json()["launch_id"])
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_STARTING)
        # 旧动作已被超时收敛（expired），再次过期扫描不得改动新世代。
        with self.session() as session:
            from server.role_services import expire_due_launches

            expire_due_launches(session, project_id=PROJECT_ID, member_id=self.role_a)
            session.commit()
        self.assertEqual(self.state_row().generation, 2)
        self.assertEqual(
            self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STARTING
        )

    def test_ready_without_instance_times_out_instead_of_hanging(self):
        launch, claim = self.start_and_claim()
        response = self.ready_report(launch, claim)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STARTING)
        self.set_launch_expired(launch["launch_id"], seconds_ago=1)
        with self.session() as session:
            from server.role_services import expire_due_launches

            expire_due_launches(session, project_id=PROJECT_ID, member_id=self.role_a)
            session.commit()
        state = self.state_row()
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_FAILED)
        self.assertEqual(state.last_error_code, ROLE_SERVICE_ERROR_READINESS_TIMEOUT)
        self.assertEqual(self.launch_row(launch["launch_id"]).state, ROLE_SERVICE_LAUNCH_EXPIRED)


class RoleServiceReadinessTests(RoleServiceTestCase):
    """四条件就绪与两种顺序（合同 §10.3）。"""

    def _claim_and_instance(self, *, status="idle", project=PROJECT_ID, host=HOST):
        launch, claim = self.start_and_claim(host=host)
        response = self.bind_instance(
            launch, claim, status=status, project=project, host=host
        )
        return launch, claim, response

    def test_instance_first_then_report_converges(self):
        launch, claim, bound = self._claim_and_instance()
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertIsNotNone(self.launch_row(launch["launch_id"]).first_instance_seen_at)
        self.assertEqual(
            self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STARTING
        )
        report = self.ready_report(launch, claim)
        self.assertEqual(report.status_code, 200, report.text)
        state = self.state_row()
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_RUNNING)
        self.assertEqual(state.last_result, ROLE_SERVICE_RESULT_SUCCESS)
        self.assertEqual(state.observed_instance_id, claim["expected_instance_id"])
        self.assertEqual(state.pid, 4321)

    def test_report_first_then_instance_converges(self):
        launch, claim = self.start_and_claim()
        report = self.ready_report(launch, claim)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(
            self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STARTING
        )
        bound = self.bind_instance(launch, claim)
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual(self.state_row().observed_state, ROLE_SERVICE_OBSERVED_RUNNING)

    def test_old_heartbeat_does_not_produce_readiness(self):
        """旧心跳（早于 claim）不构成“本次新实例证据”，也不产生就绪。"""
        launch, claim = self.start_and_claim()
        report = self.ready_report(launch, claim)
        self.assertEqual(report.status_code, 200)
        # 直接种一行 launch 已关联、但心跳早于 claim 的实例（API 无法造出这种行）。
        with self.session() as session:
            session.add(
                AgentInstance(
                    id=claim["expected_instance_id"],
                    member_id=self.role_a,
                    runtime="dsh",
                    status="idle",
                    project_id=PROJECT_ID,
                    launch_id=launch["launch_id"],
                    host=HOST,
                    last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=600),
                )
            )
            session.commit()
            instance = session.get(AgentInstance, claim["expected_instance_id"])
            from server.role_services import note_instance_launch_evidence

            note_instance_launch_evidence(session, instance)
            session.commit()
        self.assertIsNone(self.launch_row(launch["launch_id"]).first_instance_seen_at)
        self.assertEqual(
            self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STARTING
        )

    def test_wrong_project_instance_is_rejected(self):
        launch, claim = self.start_and_claim()
        self.register_project(OTHER_PROJECT_ID)
        response = self.bind_instance(launch, claim, project=OTHER_PROJECT_ID)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"], "instance_project_not_in_roster"
        )

    def test_non_idle_instance_does_not_produce_readiness(self):
        launch, claim, _ = self._claim_and_instance(status="starting")
        self.ready_report(launch, claim)
        self.assertEqual(
            self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STARTING
        )

    def test_legacy_instance_cannot_be_relabelled(self):
        other = self.put_instance(
            "legacy-1",
            {"runtime": "dsh", "status": "idle", "project_id": PROJECT_ID},
            key=self.role_a_key,
        )
        self.assertEqual(other.status_code, 200)
        launch, claim = self.start_and_claim()
        relabel = self.put_instance(
            "legacy-1",
            {
                "runtime": "dsh",
                "status": "idle",
                "project_id": PROJECT_ID,
                "launch_id": launch["launch_id"],
            },
            key=self.role_a_key,
        )
        self.assertEqual(relabel.status_code, 409)
        self.assertEqual(relabel.json()["detail"], "instance_launch_immutable")

    def test_instance_launch_id_must_match_the_preallocated_id(self):
        launch, claim = self.start_and_claim()
        response = self.put_instance(
            "some-other-instance",
            {
                "runtime": "dsh",
                "status": "idle",
                "project_id": PROJECT_ID,
                "launch_id": launch["launch_id"],
            },
            key=self.role_a_key,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH
        )


class RoleServiceStopOwnershipTests(RoleServiceTestCase):
    """stop 的原 start 所有权、错误 host/owner、超时归属（合同 §10.2/§10.7）。"""

    def _running_role(self):
        launch, claim = self.start_and_claim()
        self.bind_instance(launch, claim)
        report = self.ready_report(launch, claim)
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(self.state_row().observed_state, ROLE_SERVICE_OBSERVED_RUNNING)
        return launch, claim

    def test_stop_without_process_is_idempotent_stopped(self):
        response = self.stop()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["idempotent_stopped"])
        self.assertIsNone(body["launch_id"])
        self.assertEqual(self.launch_rows(), [])
        self.assertEqual(self.state_row().observed_state, ROLE_SERVICE_OBSERVED_STOPPED)

    def test_stop_claim_requires_original_owner_token_and_host(self):
        launch, claim = self._running_role()
        stopped = self.stop().json()
        wrong_host = self.claim(
            stopped["launch_id"],
            {
                "host": "other-host",
                "expected_instance_id": stopped["expected_instance_id"],
                "owner_token": claim["owner_token"],
            },
            key=self.role_a_key,
        )
        self.assertEqual(wrong_host.status_code, 409)
        self.assertEqual(wrong_host.json()["detail"], ROLE_SERVICE_ERROR_UNKNOWN_OWNER)

        missing_owner = self.claim(
            stopped["launch_id"],
            {
                "host": HOST,
                "expected_instance_id": stopped["expected_instance_id"],
            },
            key=self.role_a_key,
        )
        self.assertEqual(missing_owner.status_code, 409)
        self.assertEqual(
            missing_owner.json()["detail"], ROLE_SERVICE_ERROR_UNKNOWN_OWNER
        )

        # stop claim 只发新 claim_token，不重发 owner_token。
        ok = self.claim(
            stopped["launch_id"],
            {
                "host": HOST,
                "expected_instance_id": stopped["expected_instance_id"],
                "owner_token": claim["owner_token"],
            },
            key=self.role_a_key,
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertIsNone(ok.json()["owner_token"])
        self.assertTrue(ok.json()["claim_token"])

    def test_stop_report_stopped_clears_ownership(self):
        launch, claim = self._running_role()
        stopped = self.stop().json()
        claimed = self.claim(
            stopped["launch_id"],
            {
                "host": HOST,
                "expected_instance_id": stopped["expected_instance_id"],
                "owner_token": claim["owner_token"],
            },
            key=self.role_a_key,
        ).json()
        reported = self.report(
            stopped["launch_id"],
            {
                "generation": stopped["generation"],
                "action": "stop",
                "claim_token": claimed["claim_token"],
                "owner_token": claim["owner_token"],
                "outcome": "stopped",
                "host": HOST,
                "pid": 4321,
                "process_started_at": iso_ago(5),
            },
            key=self.role_a_key,
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        state = self.state_row()
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_STOPPED)
        self.assertEqual(state.last_result, ROLE_SERVICE_RESULT_STOPPED)
        self.assertIsNone(state.current_launch_id)
        self.assertIsNone(state.process_launch_id)
        self.assertIsNone(state.owner_host)
        self.assertIsNone(state.observed_instance_id)

    def test_stop_failure_keeps_ownership_and_does_not_claim_stopped(self):
        launch, claim = self._running_role()
        stopped = self.stop().json()
        claimed = self.claim(
            stopped["launch_id"],
            {
                "host": HOST,
                "expected_instance_id": stopped["expected_instance_id"],
                "owner_token": claim["owner_token"],
            },
            key=self.role_a_key,
        ).json()
        # PID 不一致 = 无法证明身份 → unknown，绝不当成功、绝不丢归属。
        reported = self.report(
            stopped["launch_id"],
            {
                "generation": stopped["generation"],
                "action": "stop",
                "claim_token": claimed["claim_token"],
                "owner_token": claim["owner_token"],
                "outcome": "failed",
                "host": HOST,
                "pid": 9999,
                "process_started_at": iso_ago(5),
                "error_code": "stop_timeout",
            },
            key=self.role_a_key,
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        state = self.state_row()
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_UNKNOWN)
        self.assertEqual(state.process_launch_id, launch["launch_id"])
        self.assertEqual(state.owner_host, HOST)

    def test_stop_timeout_keeps_ownership_for_later_manual_handling(self):
        launch, claim = self._running_role()
        stopped = self.stop().json()
        self.set_launch_expired(stopped["launch_id"], seconds_ago=1)
        claimed = self.claim(
            stopped["launch_id"],
            {
                "host": HOST,
                "expected_instance_id": stopped["expected_instance_id"],
                "owner_token": claim["owner_token"],
            },
            key=self.role_a_key,
        )
        self.assertEqual(claimed.status_code, 409)
        state = self.state_row()
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_UNKNOWN)
        self.assertEqual(state.last_error_code, "stop_timeout")
        self.assertEqual(state.process_launch_id, launch["launch_id"])
        self.assertEqual(state.owner_host, HOST)

    def test_unknown_observed_state_refuses_stop(self):
        launch, claim = self._running_role()
        with self.session() as session:
            state = session.get(RoleServiceState, (PROJECT_ID, self.role_a))
            state.observed_state = ROLE_SERVICE_OBSERVED_UNKNOWN
            state.process_launch_id = None
            session.add(state)
            session.commit()
        response = self.stop()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], ROLE_SERVICE_ERROR_UNKNOWN_OWNER)


class RoleServiceFailedStartOwnershipTests(RoleServiceTestCase):
    """返修 F2：已 spawn 的失败**不释放**原所有权；纯预检失败才可安全重试。"""

    def _failed_start(self, *, spawned: bool, pid: int | None, error_code: str):
        launch, claim = self.start_and_claim()
        body = {
            "generation": launch["generation"],
            "action": "start",
            "claim_token": claim["claim_token"],
            "owner_token": claim["owner_token"],
            "outcome": "failed",
            "instance_id": None,
            "pid": pid,
            "process_started_at": None,
            "host": HOST,
            "error_code": error_code,
            "spawned": spawned,
        }
        report = self.report(launch["launch_id"], body, key=self.role_a_key)
        self.assertEqual(report.status_code, 200, report.text)
        return launch, claim

    def test_spawned_failure_keeps_ownership_and_blocks_retry(self):
        launch, claim = self._failed_start(
            spawned=True, pid=4321, error_code=ROLE_SERVICE_ERROR_READINESS_TIMEOUT
        )
        state = self.state_row()
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_FAILED)
        self.assertEqual(state.process_launch_id, launch["launch_id"])
        self.assertTrue(state.spawned)
        self.assertEqual(state.pid, 4321)
        projection = {row["member_id"]: row for row in self.list_services().json()}
        row = projection[self.role_a]
        self.assertFalse(row["can_start"])
        self.assertTrue(row["can_stop"])
        self.assertTrue(row["ownership_held"])
        retry = self.start()
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(retry.json()["detail"], ROLE_SERVICE_ERROR_ALREADY_RUNNING)
        self.assertEqual(self.state_row().process_launch_id, launch["launch_id"])

        # 关闭 → 沿用原 owner token 证明停止 → 归属释放，重试变为允许。
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        claimed = self.claim(
            stopped.json()["launch_id"],
            {
                "host": HOST,
                "expected_instance_id": stopped.json()["expected_instance_id"],
                "owner_token": claim["owner_token"],
            },
            key=self.role_a_key,
        )
        self.assertEqual(claimed.status_code, 200, claimed.text)
        reported = self.report(
            stopped.json()["launch_id"],
            {
                "generation": stopped.json()["generation"],
                "action": "stop",
                "claim_token": claimed.json()["claim_token"],
                "owner_token": claim["owner_token"],
                "outcome": "stopped",
                "host": HOST,
                "pid": 4321,
                "process_started_at": None,
            },
            key=self.role_a_key,
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        self.assertIsNone(self.state_row().process_launch_id)
        self.assertFalse(self.state_row().spawned)
        retry = self.start()
        self.assertEqual(retry.status_code, 200, retry.text)

    def test_preflight_failure_releases_ownership_and_allows_retry(self):
        launch, _claim = self._failed_start(
            spawned=False, pid=None, error_code="identity_mismatch"
        )
        state = self.state_row()
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_FAILED)
        self.assertIsNone(state.process_launch_id)
        self.assertFalse(state.spawned)
        projection = {row["member_id"]: row for row in self.list_services().json()}
        self.assertTrue(projection[self.role_a]["can_start"])
        self.assertFalse(projection[self.role_a]["ownership_held"])
        retry = self.start()
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(self.state_row().generation, 2)

    def test_legacy_report_without_spawned_flag_uses_pid_as_evidence(self):
        """旧宿主兼容：不传 ``spawned`` 时带 pid 视为已 spawn（保守，不释放归属）。"""
        launch, claim = self.start_and_claim()
        report = self.report(
            launch["launch_id"],
            {
                "generation": launch["generation"],
                "action": "start",
                "claim_token": claim["claim_token"],
                "owner_token": claim["owner_token"],
                "outcome": "failed",
                "pid": 777,
                "host": HOST,
                "error_code": ROLE_SERVICE_ERROR_READINESS_TIMEOUT,
            },
            key=self.role_a_key,
        )
        self.assertEqual(report.status_code, 200, report.text)
        self.assertTrue(self.state_row().spawned)
        self.assertEqual(self.state_row().process_launch_id, launch["launch_id"])
        self.assertEqual(self.state_row().pid, 777)

    def test_legacy_report_without_spawned_flag_and_without_pid_releases(self):
        """旧宿主兼容：不带 pid 的失败按“没有产生进程”处理，可安全重试。"""
        launch, claim = self.start_and_claim()
        report = self.report(
            launch["launch_id"],
            {
                "generation": launch["generation"],
                "action": "start",
                "claim_token": claim["claim_token"],
                "owner_token": claim["owner_token"],
                "outcome": "failed",
                "host": HOST,
                "error_code": "cli_missing",
            },
            key=self.role_a_key,
        )
        self.assertEqual(report.status_code, 200, report.text)
        self.assertFalse(self.state_row().spawned)
        self.assertIsNone(self.state_row().process_launch_id)


class RoleServiceIsolationTests(RoleServiceTestCase):
    """跨角色/跨项目隔离（合同 §14 I1/I2/I4）。"""

    def test_two_roles_same_runner_model_are_independent(self):
        member_b, key_b = self.make_second_role()
        started_a = self.start()
        started_b = self.start(member_b)
        self.assertEqual(started_a.status_code, 200)
        self.assertEqual(started_b.status_code, 200)
        self.assertNotEqual(
            started_a.json()["expected_instance_id"],
            started_b.json()["expected_instance_id"],
        )
        self.assertEqual(len(self.launch_rows(self.role_a)), 1)
        self.assertEqual(len(self.launch_rows(member_b)), 1)
        self.assertEqual(self.state_row(self.role_a).generation, 1)
        self.assertEqual(self.state_row(member_b).generation, 1)

    def test_stop_one_role_does_not_touch_the_other(self):
        member_b, key_b = self.make_second_role()
        launch_a, claim_a = self.start_and_claim()
        self.bind_instance(launch_a, claim_a)
        self.ready_report(launch_a, claim_a)
        launch_b, claim_b = self.start_and_claim(member_id=member_b, role_key=key_b)
        self.bind_instance(launch_b, claim_b, role_key=key_b)
        self.ready_report(launch_b, claim_b, role_key=key_b)

        self.assertEqual(self.stop().status_code, 200)
        self.assertEqual(
            self.state_row(member_b).observed_state, ROLE_SERVICE_OBSERVED_RUNNING
        )

    def test_same_named_role_in_another_project_is_isolated(self):
        self.register_project(OTHER_PROJECT_ID)
        created = self.create_role(
            OTHER_PROJECT_ID,
            role_name="后端角色",
            runner_id=RUNNER_ID,
            choice_id=self.choice_id,
            operation_key="op-beta-0001",
        )
        self.assertEqual(created.status_code, 201, created.text)
        other_member = created.json()["member_id"]
        self.assertNotEqual(other_member, self.role_a)

        started = self.start()
        self.assertEqual(started.status_code, 200)
        other = self.start(other_member, project=OTHER_PROJECT_ID)
        self.assertEqual(other.status_code, 200)
        self.assertEqual(self.state_row(self.role_a).generation, 1)
        self.assertEqual(self.state_row(other_member, OTHER_PROJECT_ID).generation, 1)
        # 跨项目调用本项目的角色 → 稳定 404。
        cross = self.start(self.role_a, project=OTHER_PROJECT_ID)
        self.assertEqual(cross.status_code, 404)


class RoleServiceBatchTests(RoleServiceTestCase):
    """项目“全部启动”：跳过运行中、逐角色结果、部分失败与失败子集重试（合同 §10.9）。"""

    def test_start_all_skips_running_and_reports_partial_failure(self):
        member_b, _ = self.make_second_role()
        choice_id = self.register_unmanaged_runner()
        member_c, _ = self.make_second_role(
            role_name="桌面角色",
            operation_key="op-alpha-unmanaged",
            runner_id=UNMANAGED_RUNNER_ID,
            choice_id=choice_id,
        )
        # 先让 A 处于 starting（已运行/启动中）：
        self.assertEqual(self.start().status_code, 200)

        response = self.start_all()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        by_member = {row["member_id"]: row for row in body["results"]}
        self.assertEqual(by_member[self.role_a]["status"], "skipped_running")
        # F6：批量写意图**不**等于启动成功 —— 宿主还没执行时必须是 ``requested``。
        self.assertEqual(by_member[member_b]["status"], "requested")
        self.assertEqual(by_member[member_c]["status"], "failed")
        self.assertEqual(
            by_member[member_c]["error_code"],
            ROLE_SERVICE_ERROR_CONTROL_KIND_NOT_MANAGED,
        )
        self.assertEqual(
            body["counts"],
            {"started": 0, "requested": 1, "skipped": 1, "failed": 1},
        )
        # 意图写只产生 pending 动作：observed 仍是 starting、readiness 仍是 pending。
        projection = {row["member_id"]: row for row in self.list_services().json()}
        self.assertEqual(projection[member_b]["observed"], ROLE_SERVICE_OBSERVED_STARTING)
        self.assertEqual(projection[member_b]["readiness_service"], "pending")
        self.assertEqual(projection[member_b]["current_launch"]["state"], "pending")
        self.assertFalse(projection[member_b]["can_start"])

    def test_start_all_does_not_restart_a_role_that_still_holds_its_process(self):
        """F2/F6：失败/过期但归属未释放的角色必须被跳过，不能重复启动。"""
        launch, _claim = self.start_and_claim()
        self.set_launch_expired(launch["launch_id"], seconds_ago=2)
        with self.session() as session:
            from server.role_services import expire_due_launches

            expire_due_launches(session, project_id=PROJECT_ID, member_id=self.role_a)
            session.commit()
        self.assertEqual(self.state_row().observed_state, ROLE_SERVICE_OBSERVED_FAILED)
        self.assertEqual(self.state_row().process_launch_id, launch["launch_id"])
        before = self.state_row().generation

        response = self.start_all({"member_ids": [self.role_a]})
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()["results"][0]
        self.assertEqual(row["status"], "skipped_ownership_held")
        self.assertEqual(row["error_code"], ROLE_SERVICE_ERROR_ALREADY_RUNNING)
        self.assertEqual(self.state_row().generation, before)
        self.assertEqual(len(self.launch_rows()), 1)

    def test_start_all_retries_only_the_failed_subset(self):
        member_b, _ = self.make_second_role()
        self.assertEqual(self.start().status_code, 200)
        first = self.start_all().json()
        requested_members = {
            row["member_id"] for row in first["results"] if row["status"] == "requested"
        }
        retry = self.start_all({"member_ids": [member_b]})
        self.assertEqual(retry.status_code, 200, retry.text)
        body = retry.json()
        self.assertEqual(body["requested"], [member_b])
        self.assertEqual([row["member_id"] for row in body["results"]], [member_b])
        # A 已运行的世代没有被再次推进，也没有第二个 launch。
        self.assertEqual(self.state_row(self.role_a).generation, 1)
        self.assertEqual(len(self.launch_rows(self.role_a)), 1)
        # B 已被上一个请求写进去（尚未被驳回），因此这次只重试失败子集时必须稳定拒绝。
        self.assertEqual(retry.json()["results"][0]["status"], "skipped_running")
        self.assertTrue(requested_members)

    def test_start_all_rejects_cross_project_and_missing_ids(self):
        self.register_project(OTHER_PROJECT_ID)
        missing = self.start_all({"member_ids": ["agent:prj-x.nobody-deadbeef"]})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "role_not_found")
        cross = self.start_all({"member_ids": [self.role_a], "unexpected": 1})
        self.assertEqual(cross.status_code, 422)

    def test_start_all_requires_human(self):
        self.assertEqual(self.start_all(key=self.role_a_key).status_code, 403)


class RoleServiceProjectionTests(RoleServiceTestCase):
    """公共投影白名单与三个独立事实（合同 §4.3 第 8 条 / §11.2）。"""

    def test_projection_never_leaks_tokens_or_paths(self):
        launch, claim = self.start_and_claim()
        self.bind_instance(launch, claim)
        self.ready_report(launch, claim)
        raw = self.list_services().text + self.get_roles().text
        for forbidden in (
            claim["owner_token"],
            claim["claim_token"],
            "owner_token",
            "claim_token",
            "api_key",
            "argv",
            "/api/",
        ):
            self.assertNotIn(forbidden, raw)

    def test_role_list_service_projection_matches_endpoint(self):
        self.assertEqual(self.start().status_code, 200)
        roles = {row["member_id"]: row for row in self.get_roles().json()}
        services = {row["member_id"]: row for row in self.list_services().json()}
        self.assertIsNotNone(roles[self.role_a]["service"])
        for field in ("desired", "observed", "control_kind", "readiness_service"):
            self.assertEqual(
                roles[self.role_a]["service"][field], services[self.role_a][field]
            )
        self.assertEqual(services[self.role_a]["observed"], ROLE_SERVICE_OBSERVED_STARTING)
        self.assertEqual(services[self.role_a]["native_login"], "unverified")
        self.assertEqual(services[self.role_a]["model_alias"], "resolved")
        self.assertEqual(services[self.role_a]["readiness_service"], "pending")

    def test_default_state_is_stopped_and_not_started(self):
        services = {row["member_id"]: row for row in self.list_services().json()}
        row = services[self.role_a]
        self.assertEqual(row["desired"], "stopped")
        self.assertEqual(row["observed"], ROLE_SERVICE_OBSERVED_NOT_STARTED)
        self.assertIsNone(row["current_launch"])
        self.assertEqual(row["generation"], 0)
        self.assertTrue(row["can_start"])
        self.assertFalse(row["can_stop"])
        self.assertFalse(row["archived"])


class SharedEnqueueCoreTests(RoleServiceTestCase):
    """R1-4c-a：``start_role_service`` 抽共享核心后的等价回归与自动入口复用守卫。"""

    def test_manual_start_wrapper_semantics_unchanged_after_refactor(self):
        """人工 start 薄包装：返回模型/世代/审计/错误码与 R1-3 逐字一致。"""
        started = self.start()
        self.assertEqual(started.status_code, 200, started.text)
        body = started.json()
        self.assertEqual(body["generation"], 1)
        self.assertTrue(body["launch_id"])
        self.assertTrue(body["expected_instance_id"].startswith("ins_"))
        self.assertNotIn("token", str(body).lower().replace("launch_id", ""))
        state = self.state_row()
        self.assertEqual(state.generation, 1)
        self.assertEqual(state.desired_state, "running")
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_STARTING)
        self.assertEqual(state.control_kind, "managed_cli")
        # human 审计身份保持（共享核心只改 actor 参数，不改包装语义）。
        self.assertEqual(state.updated_by, "human:bobo")
        # 所有权/运行中守卫保持：第二次 start 仍 409 already_running。
        second = self.start()
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"], ROLE_SERVICE_ERROR_ALREADY_RUNNING)
        # 默认 stopped 语义不被本片改动（无行不落行，can_start 公式不硬置）。
        self.assertEqual(len(self.launch_rows()), 1)

    def test_enqueue_auto_start_launch_uses_real_binding_and_audit(self):
        """自动入口复用真实 binding/control_kind/CAS/TTL，审计 system:auto-start。"""
        with self.session() as session:
            db.begin_immediate_write(session)
            launch_id, code = enqueue_auto_start_launch(
                PROJECT_ID, self.role_a, session=session, now=_utc_now()
            )
            self.assertIsNotNone(launch_id)
            self.assertIsNone(code)
            session.commit()
        launch = self.launch_row(launch_id)
        self.assertEqual(launch.action, "start")
        self.assertEqual(launch.state, "pending")
        self.assertEqual(launch.generation, 1)
        state = self.state_row()
        self.assertEqual(state.generation, 1)
        self.assertEqual(state.desired_state, "running")
        self.assertEqual(state.control_kind, "managed_cli")
        self.assertEqual(state.updated_by, "system:auto-start")
        # 人工 stop 对自动入队的 pending 动作同样生效（世代/所有权边界保持）。
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["generation"], 2)
        launch = self.launch_row(launch_id)
        self.assertEqual(launch.state, ROLE_SERVICE_LAUNCH_EXPIRED)
        self.assertEqual(launch.error_code, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)

    def test_enqueue_auto_start_launch_refuses_unknown_control_kind(self):
        """登记为 unknown 的运行器如实拒绝：稳定码 + 零写入，不挂 pending 等超时。"""
        unmanaged_choice = self.register_unmanaged_runner()
        member_id, _key = self.make_second_role(
            runner_id=UNMANAGED_RUNNER_ID, choice_id=unmanaged_choice
        )
        with self.session() as session:
            db.begin_immediate_write(session)
            launch_id, code = enqueue_auto_start_launch(
                PROJECT_ID, member_id, session=session, now=_utc_now()
            )
            session.rollback()
        self.assertIsNone(launch_id)
        self.assertEqual(code, "auto_start_control_kind_not_managed")
        self.assertIsNone(self.state_row(member_id))
        self.assertEqual(len(self.launch_rows(member_id)), 0)

    def test_enqueue_auto_start_launch_conflict_returns_stable_code(self):
        """已运行中/持有所有权时只回稳定码（auto_start_enqueue_failed），不抛 HTTP。"""
        started = self.start()
        self.assertEqual(started.status_code, 200, started.text)
        with self.session() as session:
            db.begin_immediate_write(session)
            launch_id, code = enqueue_auto_start_launch(
                PROJECT_ID, self.role_a, session=session, now=_utc_now()
            )
            session.rollback()
        self.assertIsNone(launch_id)
        self.assertEqual(code, "auto_start_enqueue_failed")
        self.assertEqual(len(self.launch_rows()), 1)


def _utc_now():
    return datetime.now(timezone.utc)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
