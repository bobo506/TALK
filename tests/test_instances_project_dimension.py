"""角色生命周期 R1-1：实例项目维度与安全增量更新（合同 §5.4 / §10.4）。

覆盖实施计划 §3.2/§3.6 与合同 I29/I56：

- ``PUT /api/instances/{id}`` 只赋值请求中**显式出现**的字段：旧心跳省略可选字段时
  保持原值，不再被抹成 ``NULL``；
- ``project_id`` 一旦非空不可改写/清空（``409 instance_project_immutable``）；
  首次声明要求名册行存在且角色未归档（``422 instance_project_not_in_roster``）；
- ``launch_id`` 一旦非空不可改写/清空（``409 instance_launch_immutable``）；
  R1-3 起首次非空关联走真实 launch 校验（未知 launch ``409 launch_not_found``），
  R1-1 的阶段占位拒绝 ``instance_launch_not_supported`` 已按合同 §10.4 替换；
  夹具预置值仍可同值重复/省略保持；
- ``GET /api/instances?project_id=`` 附加过滤，旧参数与跨成员 403 行为不变；
- 公共输出不含任何凭据/路径字段。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

from sqlmodel import select

from server.models import AgentInstance, ProjectRole
from tests.test_support import RouteTestCase

PROJECT_ID = "prj_alpha"


class InstanceProjectDimensionTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        self.add_member("agent:other", api_key="other-key", display_name="Other")
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": PROJECT_ID, "display_name": "Alpha"},
            )
            client.post(
                f"/api/projects/{PROJECT_ID}/sync",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "agents": [
                        {
                            "member_id": "agent:worker",
                            "identity_path": ".talk/agents/agent_worker/IDENTITY.md",
                        }
                    ]
                },
            )

    # ── helpers ──────────────────────────────────────────────────────

    def put_instance(self, instance_id: str, body: dict, *, key: str = "worker-key"):
        with self.make_client() as client:
            return client.put(
                f"/api/instances/{instance_id}",
                headers={"X-API-Key": key},
                json=body,
            )

    def get_instances(self, *, key: str = "bobo-key", **params):
        with self.make_client() as client:
            return client.get(
                "/api/instances", headers={"X-API-Key": key}, params=params
            )

    def instance_row(self, instance_id: str) -> AgentInstance:
        with self.session() as session:
            return session.get(AgentInstance, instance_id)

    def seed_instance(self, **overrides) -> None:
        values = {
            "id": "seeded-1",
            "member_id": "agent:worker",
            "runtime": "dsh",
            "status": "idle",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_seen_at": datetime.now(timezone.utc),
        }
        values.update(overrides)
        with self.session() as session:
            session.add(AgentInstance(**values))
            session.commit()

    # ── 项目维度 ────────────────────────────────────────────────────

    def test_first_project_declaration_requires_roster(self):
        refused = self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "project_id": PROJECT_ID},
            key="other-key",
        )
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(
            refused.json()["detail"], "instance_project_not_in_roster"
        )

        accepted = self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "project_id": PROJECT_ID},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["project_id"], PROJECT_ID)
        self.assertEqual(accepted.json()["launch_id"], None)
        self.assertEqual(accepted.json()["process_started_at"], None)

    def test_archived_role_cannot_be_declared(self):
        with self.session() as session:
            session.add(
                ProjectRole(
                    project_id=PROJECT_ID,
                    member_id="agent:worker",
                    role_name="worker",
                    origin="imported",
                    identity_exclusive=0,
                    credential_version=1,
                    created_by="human:bobo",
                    archived_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        refused = self.put_instance(
            "worker-archived",
            {"runtime": "dsh", "status": "idle", "project_id": PROJECT_ID},
        )
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(
            refused.json()["detail"], "instance_project_not_in_roster"
        )

    def test_project_is_immutable_once_set(self):
        self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "project_id": PROJECT_ID},
        )
        rewritten = self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "project_id": "prj_beta"},
        )
        self.assertEqual(rewritten.status_code, 409)
        self.assertEqual(rewritten.json()["detail"], "instance_project_immutable")
        cleared = self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "project_id": None},
        )
        self.assertEqual(cleared.status_code, 409)
        self.assertEqual(cleared.json()["detail"], "instance_project_immutable")
        self.assertEqual(self.instance_row("worker-1").project_id, PROJECT_ID)
        # 同值重复是允许的。
        same = self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "project_id": PROJECT_ID},
        )
        self.assertEqual(same.status_code, 200)

    def test_project_filter_and_legacy_filters(self):
        self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "project_id": PROJECT_ID},
        )
        self.put_instance(
            "other-1",
            {"runtime": "pi", "status": "busy"},
            key="other-key",
        )
        self.assertEqual(
            [row["id"] for row in self.get_instances(project_id=PROJECT_ID).json()],
            ["worker-1"],
        )
        self.assertEqual(
            {row["id"] for row in self.get_instances().json()},
            {"worker-1", "other-1"},
        )
        self.assertEqual(
            [row["id"] for row in self.get_instances(status="busy").json()],
            ["other-1"],
        )
        self.assertEqual(
            [row["id"] for row in self.get_instances(member_id="agent:worker").json()],
            ["worker-1"],
        )

    # ── 增量更新语义 ────────────────────────────────────────────────

    def test_omitted_fields_preserve_existing_values(self):
        created = self.put_instance(
            "worker-1",
            {
                "runtime": "dsh",
                "status": "idle",
                "host": "host-a",
                "pid": 4321,
                "current_task_id": "77",
                "last_error": "boom",
                "project_id": PROJECT_ID,
                "process_started_at": "2026-10-11T00:00:00+00:00",
            },
        )
        self.assertEqual(created.status_code, 200)

        heartbeat = self.put_instance("worker-1", {"runtime": "dsh", "status": "busy"})
        self.assertEqual(heartbeat.status_code, 200)
        body = heartbeat.json()
        self.assertEqual(body["status"], "busy")
        self.assertEqual(body["host"], "host-a")
        self.assertEqual(body["pid"], 4321)
        self.assertEqual(body["current_task_id"], "77")
        self.assertEqual(body["last_error"], "boom")
        self.assertEqual(body["project_id"], PROJECT_ID)
        self.assertIsNotNone(body["process_started_at"])
        row = self.instance_row("worker-1")
        self.assertEqual(row.host, "host-a")
        self.assertEqual(row.project_id, PROJECT_ID)

    def test_explicit_null_still_clears(self):
        self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "host": "host-a", "pid": 1},
        )
        cleared = self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "host": None, "pid": None},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()["host"])
        self.assertIsNone(cleared.json()["pid"])

    # ── launch 关联 ────────────────────────────────────────────────

    def test_first_non_empty_launch_requires_a_real_claimed_launch(self):
        """R1-3 替换 R1-1 的阶段拒绝：首次关联必须是**本次新建**且命中真实 launch。

        R1-1 曾统一 ``422 instance_launch_not_supported``；R1-3 接通真实
        launch 存在/领取/实例匹配校验后：

        - 新实例（本次请求建行）带未知 launch → ``409 launch_not_found``；
        - **已存在**的实例（含 legacy 行）不允许重新贴标签 → ``409 instance_launch_immutable``
          （合同 §10.4 / I49）。
        """
        response = self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "launch_id": "launch-x"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "launch_not_found")

        self.seed_instance()
        relabel = self.put_instance(
            "seeded-1",
            {"runtime": "dsh", "status": "idle", "launch_id": "launch-x"},
        )
        self.assertEqual(relabel.status_code, 409)
        self.assertEqual(relabel.json()["detail"], "instance_launch_immutable")
        self.assertIsNone(self.instance_row("seeded-1").launch_id)

    def test_preset_non_empty_launch_is_immutable(self):
        self.seed_instance(launch_id="launch-preset-1", project_id=PROJECT_ID)
        repeated = self.put_instance(
            "seeded-1",
            {
                "runtime": "dsh",
                "status": "idle",
                "launch_id": "launch-preset-1",
            },
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["launch_id"], "launch-preset-1")

        omitted = self.put_instance("seeded-1", {"runtime": "dsh", "status": "busy"})
        self.assertEqual(omitted.status_code, 200)
        self.assertEqual(omitted.json()["launch_id"], "launch-preset-1")

        replaced = self.put_instance(
            "seeded-1",
            {"runtime": "dsh", "status": "idle", "launch_id": "launch-other"},
        )
        self.assertEqual(replaced.status_code, 409)
        self.assertEqual(replaced.json()["detail"], "instance_launch_immutable")
        cleared = self.put_instance(
            "seeded-1",
            {"runtime": "dsh", "status": "idle", "launch_id": None},
        )
        self.assertEqual(cleared.status_code, 409)
        self.assertEqual(cleared.json()["detail"], "instance_launch_immutable")
        self.assertEqual(self.instance_row("seeded-1").launch_id, "launch-preset-1")

    # ── 权限与输出面 ────────────────────────────────────────────────

    def test_cross_member_takeover_and_human_report_unchanged(self):
        self.put_instance("worker-1", {"runtime": "dsh", "status": "idle"})
        takeover = self.put_instance(
            "worker-1", {"runtime": "pi", "status": "idle"}, key="other-key"
        )
        self.assertEqual(takeover.status_code, 403)
        human = self.put_instance(
            "human-1", {"runtime": "manual", "status": "idle"}, key="bobo-key"
        )
        self.assertEqual(human.status_code, 403)

    def test_public_output_has_no_credential_fields(self):
        response = self.put_instance(
            "worker-1",
            {"runtime": "dsh", "status": "idle", "project_id": PROJECT_ID},
        )
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "id",
                "member_id",
                "runtime",
                "status",
                "host",
                "pid",
                "current_task_id",
                "last_error",
                "created_at",
                "updated_at",
                "last_seen_at",
                "project_id",
                "launch_id",
                "process_started_at",
            },
        )
        raw = self.get_instances().text
        for forbidden in ("api_key", "owner_token", "claim_token", "argv"):
            self.assertNotIn(forbidden, raw)

    def test_invalid_status_and_missing_auth_unchanged(self):
        self.assertEqual(
            self.put_instance(
                "worker-1", {"runtime": "dsh", "status": "sleeping"}
            ).status_code,
            422,
        )
        with self.make_client() as client:
            self.assertEqual(client.get("/api/instances").status_code, 422)
            self.assertEqual(
                client.get(
                    "/api/instances", headers={"X-API-Key": "nope"}
                ).status_code,
                401,
            )


class InstanceProjectAtomicityTests(InstanceProjectDimensionTests):
    """F1 补正：首次 ``project_id`` 声明在**真实 SQLite 写锁**内原子。

    复现独立探针的竞争：一个已有 ``project_id IS NULL`` 的实例、两个都在名册内的
    项目、两个真实连接分别在**校验之后**写。修前两个请求都 200 并互相覆盖；修后
    写锁让后到者在守卫之前等待，读到已提交事实后返回稳定
    ``409 instance_project_immutable``。

    探针的 ``Barrier`` 放在校验之后：修后第一个写者持锁、第二个写者阻塞在写锁上，
    若沿用“双方都到 Barrier”的写法必然死锁。因此这里改为**有界事件**：观察第二个
    连接确实被阻塞后再释放第一个写者，全程带超时，不出现挂死。
    """

    def setUp(self):
        super().setUp()
        with self.make_client() as client:
            self.assertEqual(
                client.post(
                    "/api/projects",
                    headers={"X-API-Key": "bobo-key"},
                    json={"project_id": "prj_beta", "display_name": "Beta"},
                ).status_code,
                201,
            )
            self.assertEqual(
                client.post(
                    "/api/projects/prj_beta/sync",
                    headers={"X-API-Key": "bobo-key"},
                    json={
                        "agents": [
                            {
                                "member_id": "agent:worker",
                                "identity_path": ".talk/agents/agent_worker/IDENTITY.md",
                            }
                        ]
                    },
                ).status_code,
                200,
            )
        self.journal_mode = self.enable_wal()

    # ── helpers ──────────────────────────────────────────────────────

    def enable_wal(self) -> str:
        with self.engine.connect() as connection:
            mode = connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar()
            connection.commit()
        return str(mode).lower()

    def try_write_lock_from_independent_connection(self) -> dict:
        """独立真实连接尝试 ``BEGIN IMMEDIATE``：持锁者存在时应被 SQLite 拒绝。"""
        connection = sqlite3.connect(
            str(self.db_path), timeout=0.3, isolation_level=None
        )
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                return {"blocked": True, "error": str(exc)}
            connection.execute("ROLLBACK")
            return {"blocked": False, "error": None}
        finally:
            connection.close()

    def put_declaration(self, instance_id: str, project_id: str, *, key: str = "worker-key"):
        with self.make_client() as client:
            return client.put(
                f"/api/instances/{instance_id}",
                headers={"X-API-Key": key},
                json={
                    "runtime": "dsh",
                    "status": "idle",
                    "project_id": project_id,
                },
            )

    # ── 真实双连接竞争 ───────────────────────────────────────────────

    def test_first_project_declaration_race_serializes_on_real_write_lock(self):
        self.assertEqual(self.journal_mode, "wal")
        self.seed_instance()  # agent:worker 的已有实例，project_id 仍为 NULL

        import server.routes.instances as instances_route

        original = instances_route._project_declaration_allowed
        entered = threading.Event()
        release = threading.Event()
        entered_projects: list[str] = []
        counter_lock = threading.Lock()
        probe: dict = {}

        def gated(project_id, member_id, session):
            with counter_lock:
                entered_projects.append(project_id)
                is_first = len(entered_projects) == 1
            if is_first:
                entered.set()
                release.wait(timeout=15)
            return original(project_id, member_id, session)

        with patch.object(instances_route, "_project_declaration_allowed", gated):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(self.put_declaration, "seeded-1", "prj_alpha")
                second = None
                try:
                    entered_ok = entered.wait(timeout=15)
                    if entered_ok:
                        # 第一个写者已持锁并停在守卫内部：独立真实连接取不到写锁。
                        probe = self.try_write_lock_from_independent_connection()
                        second = executor.submit(
                            self.put_declaration, "seeded-1", "prj_beta"
                        )
                        time.sleep(0.6)
                    with counter_lock:
                        observed_while_held = list(entered_projects)
                finally:
                    release.set()
                responses = [first.result(timeout=30)]
                if second is not None:
                    responses.append(second.result(timeout=30))

        self.assertTrue(entered_ok, "首个写者未进入项目声明校验")
        self.assertTrue(
            probe.get("blocked"),
            f"守卫执行时未持有实际写锁：{probe.get('error')}",
        )
        self.assertEqual(
            observed_while_held,
            ["prj_alpha"],
            "第二个连接在首个写者持锁时进入了校验，说明校验不在写锁内",
        )
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        winner = next(r for r in responses if r.status_code == 200)
        loser = next(r for r in responses if r.status_code == 409)
        self.assertEqual(loser.json()["detail"], "instance_project_immutable")
        self.assertEqual(winner.json()["project_id"], "prj_alpha")
        self.assertEqual(self.instance_row("seeded-1").project_id, "prj_alpha")
        # 后到者失败不破坏事实：同值重放仍然 200。
        self.assertEqual(
            self.put_declaration("seeded-1", "prj_alpha").status_code, 200
        )

    def test_concurrent_same_project_declaration_is_idempotent(self):
        self.assertEqual(self.journal_mode, "wal")
        self.seed_instance()
        barrier = threading.Barrier(2)

        def declare():
            with self.make_client() as client:
                barrier.wait(timeout=15)
                return client.put(
                    "/api/instances/seeded-1",
                    headers={"X-API-Key": "worker-key"},
                    json={
                        "runtime": "dsh",
                        "status": "idle",
                        "project_id": "prj_alpha",
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = [
                future.result(timeout=30)
                for future in (executor.submit(declare), executor.submit(declare))
            ]
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(self.instance_row("seeded-1").project_id, "prj_alpha")

    def test_omitted_and_null_declaration_keep_immutability_after_race(self):
        self.assertEqual(self.journal_mode, "wal")
        self.seed_instance()
        self.assertEqual(
            self.put_declaration("seeded-1", "prj_alpha").status_code, 200
        )
        # 省略字段保留原值。
        omitted = self.put_instance("seeded-1", {"runtime": "dsh", "status": "busy"})
        self.assertEqual(omitted.status_code, 200)
        self.assertEqual(omitted.json()["project_id"], "prj_alpha")
        # 显式 null 仍是不可清空。
        cleared = self.put_instance(
            "seeded-1", {"runtime": "dsh", "status": "idle", "project_id": None}
        )
        self.assertEqual(cleared.status_code, 409)
        self.assertEqual(cleared.json()["detail"], "instance_project_immutable")
        self.assertEqual(self.instance_row("seeded-1").project_id, "prj_alpha")


if __name__ == "__main__":
    unittest.main()
