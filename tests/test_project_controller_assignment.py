"""C1b-S1 项目长期主控指定：后端 API、MCP 只读输出与生命周期。

覆盖：
- 老库幂等增列迁移（``controller_member_id`` / ``controller_assignment_version``）：不重建表、
  不删改既有数据，旧项目保持“未指定 / 0”，不自动指定 lead / Codex；
- 专用入口 ``PATCH /api/projects/{id}/controller-assignment``：human 可写 / agent 只读、
  跨项目隔离、不存在项目 404、``member_id`` 必填键与显式 null、``expected_version`` 严格整数
  与 SQLite 有符号 64 位上界；
- 候选校验：已注册、未禁用、在项目名册中的 agent（不要求在线）；所有失败都不改库；
- 版本规则：实际变化 +1、同值幂等、陈旧同值仍 409、已占用不可直接覆盖、清空后另选、
  版本耗尽得到可控 409 而不是溢出 500；
- CAS 落在数据库写入层：并发指定至多一个成功、与并发解除正确竞争、陈旧 session 不能覆盖；
- 生命周期：名册 sync 移除 / 成员禁用 / 成员行缺失 / 重开数据库都不自动清除或转移指定，
  读取时如实报告状态，恢复名册或启用后回到 ``assigned``；
- 旁路防护：项目创建 / 普通 PATCH / 重注册 / sync / profile 写入 / controller-mode 都不能写指定；
- MCP ``talk_list_agents`` 顶层只读 ``controller_assignment``：复用同一次项目 GET、非项目 null、
  旧后端 unsupported、未知状态 unknown、不新增工具、不宣称在线 / ACK / 生效；
- 任务路径回归：指定不改变派发与创建任务权限，写入本身不创建任务 / 实例 / 消息。
"""

import gc
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlmodel import Session, create_engine, select

import server.db as db
import server.main as main
from bridges import talk_task_tools
from bridges.talk_task_tools import (
    CONTROLLER_ASSIGNMENT_EFFECTIVE_STATUS_UNSUPPORTED,
    CONTROLLER_ASSIGNMENT_STATUS_UNKNOWN,
    TOOL_SCHEMAS,
    TalkToolError,
    controller_assignment_summary,
    dispatch_tool,
)
from server.models import (
    SQLITE_SIGNED_INTEGER_MAX,
    AgentInstance,
    AgentTask,
    Member,
    Message,
    Project,
    ProjectAgent,
)
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

PROJECT_TOOL_NAMES = (
    "talk_list_agents",
    "talk_delegate_task",
    "talk_get_task",
    "talk_list_tasks",
    "talk_wait_tasks",
    "talk_reply_task",
    "talk_cancel_task",
    "talk_collect_result",
    "talk_get_delivery",
)


def tool_description(name: str) -> str:
    return next(tool["description"] for tool in TOOL_SCHEMAS if tool["name"] == name)


class ControllerAssignmentTestCase(RouteTestCase):
    """C1b-S1 测试共用夹具：两个 human + 三个 agent。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:carol", api_key="carol-key", display_name="Carol")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")
        self.add_member("agent:kimi", api_key="kimi-key", display_name="Kimi")
        self.add_member("agent:loner", api_key="loner-key", display_name="Loner")

    def register(
        self,
        project_id: str = "prj_ctl",
        *,
        roster=("agent:codex", "agent:kimi"),
        **extra,
    ):
        with self.make_client() as client:
            created = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": project_id, "display_name": project_id, **extra},
            )
            if created.status_code == 201 and roster:
                synced = client.post(
                    f"/api/projects/{project_id}/sync",
                    headers={"X-API-Key": "bobo-key"},
                    json={"agents": [{"member_id": member_id} for member_id in roster]},
                )
                assert synced.status_code == 200, synced.text
            return created

    def assign(
        self,
        project_id: str = "prj_ctl",
        payload=None,
        *,
        key: str = "bobo-key",
    ):
        body = {"member_id": "agent:codex", "expected_version": 0} if payload is None else payload
        with self.make_client() as client:
            return client.patch(
                f"/api/projects/{project_id}/controller-assignment",
                headers={"X-API-Key": key} if key else {},
                json=body,
            )

    def patch_mode(self, project_id: str = "prj_ctl", payload=None, *, key: str = "bobo-key"):
        body = {"mode": "active", "expected_version": 0} if payload is None else payload
        with self.make_client() as client:
            return client.patch(
                f"/api/projects/{project_id}/controller-mode",
                headers={"X-API-Key": key} if key else {},
                json=body,
            )

    def get_project(self, project_id: str = "prj_ctl", *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}",
                headers={"X-API-Key": key} if key else {},
            )

    def stored_state(self, project_id: str = "prj_ctl") -> tuple[str | None, int]:
        with self.session() as session:
            project = session.get(Project, project_id)
            return project.controller_member_id, project.controller_assignment_version


class ControllerAssignmentApiTests(ControllerAssignmentTestCase):
    """专用入口的权限、校验、候选、版本规则、清空/另选与跨项目隔离。"""

    def test_new_project_defaults_to_unassigned_zero(self):
        created = self.register()
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertIsNone(body["controller_member_id"])
        self.assertEqual(body["controller_assignment_version"], 0)
        self.assertEqual(body["controller_assignment_status"], "unassigned")

        fetched = self.get_project().json()
        self.assertIsNone(fetched["controller_member_id"])
        self.assertEqual(fetched["controller_assignment_version"], 0)
        self.assertEqual(fetched["controller_assignment_status"], "unassigned")

        with self.make_client() as client:
            listed = client.get("/api/projects", headers={"X-API-Key": "bobo-key"}).json()
        self.assertIsNone(listed[0]["controller_member_id"])
        self.assertEqual(listed[0]["controller_assignment_version"], 0)

    def test_registration_cannot_inject_controller_fields(self):
        """项目创建请求里的主控字段按未知字段忽略：老项目不会因此被自动指定。"""
        created = self.register(
            roster=(),
            controller_member_id="agent:codex",
            controller_assignment_version=7,
            controller_assignment_status="assigned",
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertIsNone(body["controller_member_id"])
        self.assertEqual(body["controller_assignment_version"], 0)
        self.assertEqual(body["controller_assignment_status"], "unassigned")
        self.assertEqual(self.stored_state(), (None, 0))

    def test_agent_can_read_but_cannot_write(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)

        with self.make_client() as client:
            read = client.get("/api/projects/prj_ctl", headers={"X-API-Key": "kimi-key"})
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json()["controller_member_id"], "agent:codex")
        self.assertEqual(read.json()["controller_assignment_version"], 1)

        for key in ("codex-key", "kimi-key"):
            with self.subTest(key=key):
                forbidden = self.assign(
                    payload={"member_id": "agent:kimi", "expected_version": 1}, key=key
                )
                self.assertEqual(forbidden.status_code, 403, forbidden.text)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

    def test_missing_or_invalid_key_is_rejected(self):
        self.register()
        no_key = self.assign(key="")
        self.assertEqual(no_key.status_code, 422)  # 缺少必填 header
        bad_key = self.assign(key="nope")
        self.assertEqual(bad_key.status_code, 401)
        self.assertEqual(self.stored_state(), (None, 0))

    def test_unknown_project_returns_404(self):
        response = self.assign(project_id="prj_ghost")
        self.assertEqual(response.status_code, 404)

    def test_member_id_key_is_required_and_must_be_string_or_explicit_null(self):
        self.register()
        invalid_payloads = (
            {"expected_version": 0},  # 缺 member_id 键
            {"member_id": "", "expected_version": 0},  # 空串不是“解除”
            {"member_id": "   ", "expected_version": 0},
            {"member_id": 123, "expected_version": 0},
            {"member_id": ["agent:codex"], "expected_version": 0},
            {"member_id": {"id": "agent:codex"}, "expected_version": 0},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.assign(payload=payload)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.stored_state(), (None, 0))

        # 显式 null 是合法“解除”：未指定时是 200 空操作，不增版本。
        cleared = self.assign(payload={"member_id": None, "expected_version": 0})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(cleared.json()["controller_member_id"])
        self.assertEqual(cleared.json()["controller_assignment_version"], 0)
        self.assertEqual(self.stored_state(), (None, 0))

    def test_expected_version_strict_integer_and_sqlite_range(self):
        self.register()
        invalid_versions = (
            {"member_id": "agent:codex"},  # 缺 expected_version
            {"member_id": "agent:codex", "expected_version": None},
            {"member_id": "agent:codex", "expected_version": True},
            {"member_id": "agent:codex", "expected_version": False},
            {"member_id": "agent:codex", "expected_version": 1.0},
            {"member_id": "agent:codex", "expected_version": "0"},
            {"member_id": "agent:codex", "expected_version": -1},
            {"member_id": "agent:codex", "expected_version": 2**63},
            {"member_id": "agent:codex", "expected_version": 2**63 + 1},
            {"member_id": "agent:codex", "expected_version": 10**30},
        )
        for payload in invalid_versions:
            with self.subTest(payload=payload):
                response = self.assign(payload=payload)
                self.assertNotEqual(response.status_code, 500, response.text)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.stored_state(), (None, 0))

        # 上界本身是合法版本值：当前库 0，因此是正常 409，而不是 422/500。
        boundary = self.assign(
            payload={"member_id": "agent:codex", "expected_version": SQLITE_SIGNED_INTEGER_MAX}
        )
        self.assertEqual(boundary.status_code, 409, boundary.text)
        self.assertIn(f"expected_version={SQLITE_SIGNED_INTEGER_MAX}", boundary.json()["detail"])
        self.assertEqual(self.stored_state(), (None, 0))

        # 越界请求不影响库，正常 CAS 仍成功。
        normal = self.assign(payload={"member_id": "agent:codex", "expected_version": 0})
        self.assertEqual(normal.status_code, 200, normal.text)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

    def test_candidate_must_be_registered_agent_in_roster_and_enabled(self):
        self.register(roster=("agent:codex",))
        with self.make_client() as client:
            disabled = client.patch(
                "/api/members/agent:loner",
                headers={"X-API-Key": "bobo-key"},
                json={"disabled": True},
            )
        self.assertEqual(disabled.status_code, 200)

        rejected = (
            ("agent:ghost", "member not found"),
            ("human:carol", "not an agent member"),
            ("human:bobo", "not an agent member"),
            ("agent:kimi", "not in the project roster"),  # 已注册 agent，但不在名册
            ("agent:loner", "is disabled"),  # 既不在名册又被禁用
        )
        for member_id, expected_detail in rejected:
            with self.subTest(member_id=member_id):
                response = self.assign(payload={"member_id": member_id, "expected_version": 0})
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn(expected_detail, response.json()["detail"])
        self.assertEqual(self.stored_state(), (None, 0))

    def test_assignment_succeeds_offline_and_reports_assigned(self):
        """候选只要求已注册 / 未禁用 / 在名册：没有实例、离线也能指定。"""
        self.register(roster=("agent:codex",))
        with self.session() as session:
            self.assertEqual(session.exec(select(AgentInstance)).all(), [])

        response = self.assign()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["controller_member_id"], "agent:codex")
        self.assertEqual(body["controller_assignment_version"], 1)
        self.assertEqual(body["controller_assignment_status"], "assigned")
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

        # 只读端（agent 身份）看到同一份事实；返回体不宣称在线 / ACK / 生效。
        with self.make_client() as client:
            fetched = client.get("/api/projects/prj_ctl", headers={"X-API-Key": "kimi-key"}).json()
        self.assertEqual(fetched["controller_member_id"], "agent:codex")
        self.assertEqual(fetched["controller_assignment_version"], 1)
        self.assertEqual(fetched["controller_assignment_status"], "assigned")
        # 项目读取只暴露保存值与配置有效性：没有在线 / ACK / 租约 / 生效字段。
        for forbidden in (
            "effective_mode",
            "ack",
            "acknowledged",
            "lease",
            "heartbeat",
            "online",
        ):
            self.assertNotIn(forbidden, fetched)

    def test_same_value_request_is_idempotent(self):
        self.register()
        first = self.assign(payload={"member_id": "agent:codex", "expected_version": 0})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["controller_assignment_version"], 1)

        repeated = self.assign(payload={"member_id": "agent:codex", "expected_version": 1})
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["controller_member_id"], "agent:codex")
        self.assertEqual(repeated.json()["controller_assignment_version"], 1)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

        repeated_again = self.assign(payload={"member_id": "agent:codex", "expected_version": 1})
        self.assertEqual(repeated_again.status_code, 200)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

    def test_stale_version_conflicts_even_when_value_matches(self):
        self.register()
        self.assertEqual(
            self.assign(payload={"member_id": "agent:codex", "expected_version": 0}).status_code,
            200,
        )
        stale_same = self.assign(payload={"member_id": "agent:codex", "expected_version": 0})
        self.assertEqual(stale_same.status_code, 409, stale_same.text)
        self.assertIn("version conflict", stale_same.json()["detail"])
        self.assertIn("current_version=1", stale_same.json()["detail"])

        future = self.assign(payload={"member_id": "agent:codex", "expected_version": 9})
        self.assertEqual(future.status_code, 409)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

    def test_existing_assignment_cannot_be_overwritten_directly(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)  # agent:codex / 1

        overwrite = self.assign(payload={"member_id": "agent:kimi", "expected_version": 1})
        self.assertEqual(overwrite.status_code, 409, overwrite.text)
        self.assertIn("already has a controller assignment", overwrite.json()["detail"])
        self.assertIn("agent:codex", overwrite.json()["detail"])
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

        # 陈旧版本 + 换人同样 409，且不改库。
        stale_overwrite = self.assign(payload={"member_id": "agent:kimi", "expected_version": 0})
        self.assertEqual(stale_overwrite.status_code, 409)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

    def test_clear_then_assign_another_member(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)  # agent:codex / 1

        cleared = self.assign(payload={"member_id": None, "expected_version": 1})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(cleared.json()["controller_member_id"])
        self.assertEqual(cleared.json()["controller_assignment_version"], 2)
        self.assertEqual(cleared.json()["controller_assignment_status"], "unassigned")
        self.assertEqual(self.stored_state(), (None, 2))

        # 清空后可以另选别人。
        swapped = self.assign(payload={"member_id": "agent:kimi", "expected_version": 2})
        self.assertEqual(swapped.status_code, 200, swapped.text)
        self.assertEqual(swapped.json()["controller_member_id"], "agent:kimi")
        self.assertEqual(swapped.json()["controller_assignment_version"], 3)
        self.assertEqual(swapped.json()["controller_assignment_status"], "assigned")
        self.assertEqual(self.stored_state(), ("agent:kimi", 3))

        # 陈旧清空请求不会撤销新指定。
        stale_clear = self.assign(payload={"member_id": None, "expected_version": 2})
        self.assertEqual(stale_clear.status_code, 409)
        self.assertEqual(self.stored_state(), ("agent:kimi", 3))

    def test_clear_when_unassigned_is_noop_but_stale_clear_conflicts(self):
        self.register()
        noop = self.assign(payload={"member_id": None, "expected_version": 0})
        self.assertEqual(noop.status_code, 200, noop.text)
        self.assertEqual(noop.json()["controller_assignment_version"], 0)
        self.assertEqual(self.stored_state(), (None, 0))

        self.assertEqual(self.assign().status_code, 200)  # 版本 1
        stale_clear = self.assign(payload={"member_id": None, "expected_version": 0})
        self.assertEqual(stale_clear.status_code, 409)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

    def test_version_exhaustion_returns_controllable_conflict(self):
        """版本已达 SQLite 上界时，实际变化必须是可控 409，而不是绑定溢出 500。"""
        self.register()
        with self.session() as session:
            session.execute(
                update(Project)
                .where(Project.project_id == "prj_ctl")
                .values(controller_assignment_version=SQLITE_SIGNED_INTEGER_MAX)
                .execution_options(synchronize_session=False)
            )
            session.commit()

        exhausted = self.assign(
            payload={"member_id": "agent:codex", "expected_version": SQLITE_SIGNED_INTEGER_MAX}
        )
        self.assertEqual(exhausted.status_code, 409, exhausted.text)
        self.assertIn("exhausted", exhausted.json()["detail"])
        self.assertEqual(self.stored_state(), (None, SQLITE_SIGNED_INTEGER_MAX))

        # 同值重试在耗尽版本上仍是合法空操作（不需要 +1）。
        with self.session() as session:
            session.execute(
                update(Project)
                .where(Project.project_id == "prj_ctl")
                .values(controller_member_id="agent:codex")
                .execution_options(synchronize_session=False)
            )
            session.commit()
        noop = self.assign(
            payload={"member_id": "agent:codex", "expected_version": SQLITE_SIGNED_INTEGER_MAX}
        )
        self.assertEqual(noop.status_code, 200, noop.text)
        self.assertEqual(noop.json()["controller_assignment_version"], SQLITE_SIGNED_INTEGER_MAX)
        self.assertEqual(self.stored_state(), ("agent:codex", SQLITE_SIGNED_INTEGER_MAX))

        # 耗尽版本上的清空同样得到可控 409。
        clear = self.assign(
            payload={"member_id": None, "expected_version": SQLITE_SIGNED_INTEGER_MAX}
        )
        self.assertEqual(clear.status_code, 409, clear.text)
        self.assertIn("exhausted", clear.json()["detail"])

    def test_cross_project_isolation(self):
        self.register("prj_ctl")
        self.register("prj_other")

        self.assertEqual(self.assign("prj_ctl").status_code, 200)
        self.assertEqual(self.stored_state("prj_other"), (None, 0))

        other = self.assign("prj_other", {"member_id": "agent:kimi", "expected_version": 0})
        self.assertEqual(other.status_code, 200, other.text)
        self.assertEqual(self.stored_state("prj_ctl"), ("agent:codex", 1))
        self.assertEqual(self.stored_state("prj_other"), ("agent:kimi", 1))

        # 一个项目的陈旧版本不影响另一个项目；也已占用不互相影响。
        self.assertEqual(
            self.assign("prj_ctl", {"member_id": "agent:kimi", "expected_version": 0}).status_code,
            409,
        )
        cleared = self.assign("prj_other", {"member_id": None, "expected_version": 1})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(self.stored_state("prj_ctl"), ("agent:codex", 1))
        self.assertEqual(self.stored_state("prj_other"), (None, 2))

    def test_assignment_write_creates_no_tasks_instances_or_messages(self):
        self.register()
        with self.session() as session:
            tasks_before = len(session.exec(select(AgentTask)).all())
            instances_before = len(session.exec(select(AgentInstance)).all())
            messages_before = len(session.exec(select(Message)).all())

        response = self.assign()
        self.assertEqual(response.status_code, 200)
        cleared = self.assign(payload={"member_id": None, "expected_version": 1})
        self.assertEqual(cleared.status_code, 200)

        with self.session() as session:
            self.assertEqual(len(session.exec(select(AgentTask)).all()), tasks_before)
            self.assertEqual(len(session.exec(select(AgentInstance)).all()), instances_before)
            self.assertEqual(len(session.exec(select(Message)).all()), messages_before)
        self.assertEqual(self.stored_state(), (None, 2))

    def test_assignment_does_not_change_task_permissions(self):
        """保留既有任务权限：主控存在与否都不新增派发/领取门禁。"""
        self.register()
        with self.make_client() as client:
            before = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:kimi", "content": "指定前的普通派发"},
            )
        self.assertEqual(before.status_code, 201, before.text)

        self.assertEqual(self.assign().status_code, 200)  # 主控 = agent:codex

        with self.make_client() as client:
            to_non_controller = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:kimi", "content": "指定后仍可派给非主控"},
            )
            to_controller = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "派给主控本人"},
            )
            from_agent = client.post(
                "/api/tasks",
                headers={"X-API-Key": "kimi-key"},
                json={"target_member_id": "agent:codex", "content": "agent 委派链路不变"},
            )
        for response in (to_non_controller, to_controller, from_agent):
            self.assertEqual(response.status_code, 201, response.text)

        with self.session() as session:
            self.assertEqual(len(session.exec(select(AgentTask)).all()), 4)


class ControllerAssignmentRaceTests(ControllerAssignmentTestCase):
    """并发 / 独立 session：CAS 必须由数据库写入层保证，而不是先读后写。"""

    def setUp(self):
        super().setUp()
        # WAL 让并发读写不互相阻塞，避免测试受 rollback journal 读锁影响。
        db.init_db()

    def register(self, project_id: str) -> None:
        response = super().register(project_id)
        self.assertEqual(response.status_code, 201)

    def race(self, project_id: str, payloads: list[dict], expected_version: int):
        results: list[tuple[dict, int, dict]] = []
        barrier = threading.Barrier(len(payloads))

        def call(payload: dict) -> None:
            barrier.wait(timeout=20)
            response = self.assign(
                project_id,
                {"member_id": payload["member_id"], "expected_version": expected_version},
            )
            results.append((payload, response.status_code, response.json()))

        threads = [threading.Thread(target=call, args=(payload,)) for payload in payloads]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(len(results), len(payloads), f"并发请求未全部返回: {results}")
        return results

    def test_two_concurrent_assignments_have_at_most_one_winner(self):
        for index in range(6):
            project_id = f"prj_race_assign_{index}"
            self.register(project_id)
            results = self.race(
                project_id,
                [{"member_id": "agent:codex"}, {"member_id": "agent:kimi"}],
                expected_version=0,
            )

            statuses = sorted(status for _payload, status, _body in results)
            self.assertEqual(statuses, [200, 409], f"第 {index} 轮: {results}")
            winner = next(payload for payload, status, _b in results if status == 200)
            loser = next(body for _p, status, body in results if status == 409)
            self.assertTrue(
                "version conflict" in loser["detail"]
                or "already has a controller assignment" in loser["detail"],
                loser["detail"],
            )
            self.assertEqual(
                self.stored_state(project_id), (winner["member_id"], 1), f"第 {index} 轮: {results}"
            )

    def test_concurrent_assignment_and_clear_compete_correctly(self):
        for index in range(6):
            project_id = f"prj_race_clear_{index}"
            self.register(project_id)
            results = self.race(
                project_id,
                [{"member_id": "agent:codex"}, {"member_id": None}],
                expected_version=0,
            )

            for payload, status, body in results:
                self.assertIn(status, (200, 409), f"{payload}: {body}")
            # 初始未指定：解除只会是合法空操作，因此指定必须真实落库一次。
            self.assertEqual(self.stored_state(project_id), ("agent:codex", 1), results)
            changed = [
                body
                for _p, status, body in results
                if status == 200 and body["controller_member_id"] == "agent:codex"
            ]
            self.assertEqual(len(changed), 1, results)
            self.assertEqual(changed[0]["controller_assignment_version"], 1)

    def test_concurrent_clears_have_one_effective_update(self):
        for index in range(6):
            project_id = f"prj_race_two_clears_{index}"
            self.register(project_id)
            self.assertEqual(self.assign(project_id).status_code, 200)  # agent:codex / 1

            results = self.race(
                project_id,
                [{"member_id": None}, {"member_id": None}],
                expected_version=1,
            )
            statuses = sorted(status for _payload, status, _body in results)
            self.assertEqual(statuses, [200, 409], f"第 {index} 轮: {results}")
            self.assertEqual(self.stored_state(project_id), (None, 2))

    def test_stale_reader_session_cannot_overwrite_newer_version(self):
        self.register("prj_stale")
        with self.session() as stale_session:
            stale_project = stale_session.get(Project, "prj_stale")
            stale_version = stale_project.controller_assignment_version

            winner = self.assign(
                "prj_stale", {"member_id": "agent:codex", "expected_version": stale_version}
            )
            self.assertEqual(winner.status_code, 200)
            self.assertEqual(winner.json()["controller_assignment_version"], stale_version + 1)

            loser = self.assign(
                "prj_stale", {"member_id": "agent:kimi", "expected_version": stale_version}
            )
            self.assertEqual(loser.status_code, 409)
            stale_session.expire_all()
            self.assertEqual(
                (stale_project.controller_member_id, stale_project.controller_assignment_version),
                ("agent:codex", stale_version + 1),
            )

    def test_conditional_write_predicate_is_enforced_by_database(self):
        """写入层谓词：陈旧版本 / 已占用的条件 UPDATE 命中 0 行，不会覆盖新值。"""
        self.register("prj_predicate")
        self.assertEqual(self.assign("prj_predicate").status_code, 200)  # agent:codex / 1

        with self.session() as session:
            stale = session.execute(
                update(Project)
                .where(
                    Project.project_id == "prj_predicate",
                    Project.controller_assignment_version == 0,
                    Project.controller_member_id.is_(None),
                )
                .values(
                    controller_member_id="agent:kimi",
                    controller_assignment_version=Project.controller_assignment_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            session.commit()
            self.assertEqual(stale.rowcount, 0)

            occupied = session.execute(
                update(Project)
                .where(
                    Project.project_id == "prj_predicate",
                    Project.controller_assignment_version == 1,
                    Project.controller_member_id.is_(None),
                )
                .values(
                    controller_member_id="agent:kimi",
                    controller_assignment_version=Project.controller_assignment_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            session.commit()
            self.assertEqual(occupied.rowcount, 0)

        self.assertEqual(self.stored_state("prj_predicate"), ("agent:codex", 1))


class ControllerAssignmentLifecycleTests(ControllerAssignmentTestCase):
    """名册 sync / 成员禁用 / 成员行缺失 / 重开数据库都不自动清除或转移长期指定。"""

    def sync_roster(self, project_id: str, members: list[str]):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": member_id} for member_id in members]},
            )

    def set_disabled(self, member_id: str, disabled: bool):
        with self.make_client() as client:
            return client.patch(
                f"/api/members/{member_id}",
                headers={"X-API-Key": "bobo-key"},
                json={"disabled": disabled},
            )

    def status(self, project_id: str = "prj_ctl") -> str:
        return self.get_project(project_id).json()["controller_assignment_status"]

    def test_roster_sync_removal_keeps_assignment_and_reports_not_in_roster(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)
        self.assertEqual(self.status(), "assigned")

        removed = self.sync_roster("prj_ctl", ["agent:kimi"])
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))
        body = self.get_project().json()
        self.assertEqual(body["controller_member_id"], "agent:codex")
        self.assertEqual(body["controller_assignment_status"], "not_in_roster")

        # 名册缺失期间不能被别的 agent 顶替；human 仍可显式解除。
        blocked = self.assign(payload={"member_id": "agent:kimi", "expected_version": 1})
        self.assertEqual(blocked.status_code, 409)
        cleared = self.assign(payload={"member_id": None, "expected_version": 1})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(cleared.json()["controller_assignment_status"], "unassigned")

    def test_re_adding_to_roster_restores_assigned_without_rewrite(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)
        self.assertEqual(self.sync_roster("prj_ctl", ["agent:kimi"]).status_code, 200)
        self.assertEqual(self.status(), "not_in_roster")

        self.assertEqual(self.sync_roster("prj_ctl", ["agent:codex", "agent:kimi"]).status_code, 200)
        self.assertEqual(self.status(), "assigned")
        # 状态恢复不依赖重新写入：版本与成员保持原值。
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

    def test_member_disable_keeps_assignment_and_reports_disabled(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)

        disabled = self.set_disabled("agent:codex", True)
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))
        self.assertEqual(self.status(), "member_disabled")

        # 被禁用成员不能被“新指定”。
        with self.make_client() as client:
            fresh = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_disabled", "display_name": "prj_disabled"},
            )
        self.assertEqual(fresh.status_code, 201)
        self.assertEqual(self.sync_roster("prj_disabled", ["agent:codex"]).status_code, 200)
        rejected = self.assign("prj_disabled", {"member_id": "agent:codex", "expected_version": 0})
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertEqual(self.stored_state("prj_disabled"), (None, 0))

        # human 仍可解除；重新启用后可以重新指定该成员。
        cleared = self.assign(payload={"member_id": None, "expected_version": 1})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(self.set_disabled("agent:codex", False).status_code, 200)
        self.assertEqual(
            self.assign(payload={"member_id": "agent:codex", "expected_version": 2}).status_code,
            200,
        )
        self.assertEqual(self.status(), "assigned")

    def test_missing_member_row_reports_member_missing_and_can_be_cleared(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)

        with self.session() as session:
            member = session.get(Member, "agent:codex")
            session.delete(member)
            session.commit()

        self.assertEqual(self.stored_state(), ("agent:codex", 1))
        self.assertEqual(self.status(), "member_missing")

        cleared = self.assign(payload={"member_id": None, "expected_version": 1})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(cleared.json()["controller_member_id"])
        self.assertEqual(cleared.json()["controller_assignment_status"], "unassigned")

    def test_non_agent_controller_row_reports_not_agent(self):
        """手工/历史写入的非 agent 指定如实报告，不冒充有效主控。"""
        self.register(roster=("agent:codex", "human:carol"))
        with self.session() as session:
            session.execute(
                update(Project)
                .where(Project.project_id == "prj_ctl")
                .values(controller_member_id="human:carol")
                .execution_options(synchronize_session=False)
            )
            session.commit()

        body = self.get_project().json()
        self.assertEqual(body["controller_member_id"], "human:carol")
        self.assertEqual(body["controller_assignment_status"], "not_agent")

    def test_assignment_survives_database_reopen_and_reinit(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)

        # 模拟服务重启：释放连接、重新按同一文件建引擎、重跑幂等迁移。
        reopened = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        old_engine = db.engine
        db.engine = reopened
        main.engine = reopened
        try:
            db.init_db()
            with Session(reopened) as session:
                project = session.get(Project, "prj_ctl")
                self.assertEqual(project.controller_member_id, "agent:codex")
                self.assertEqual(project.controller_assignment_version, 1)
            with self.make_client() as client:
                body = client.get(
                    "/api/projects/prj_ctl", headers={"X-API-Key": "bobo-key"}
                ).json()
            self.assertEqual(body["controller_member_id"], "agent:codex")
            self.assertEqual(body["controller_assignment_version"], 1)
            self.assertEqual(body["controller_assignment_status"], "assigned")
        finally:
            db.engine = old_engine
            main.engine = self.engine
            reopened.dispose()


class ControllerAssignmentBypassTests(ControllerAssignmentTestCase):
    """普通项目入口 / sync / profile 写入都不能旁路设置主控或版本。"""

    def test_project_patch_and_reregistration_cannot_touch_assignment(self):
        self.register()
        self.assertEqual(self.assign().status_code, 200)  # agent:codex / 1

        with self.make_client() as client:
            patched = client.patch(
                "/api/projects/prj_ctl",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "display_name": "改名",
                    "controller_member_id": "agent:kimi",
                    "controller_assignment_version": 99,
                    "controller_assignment_status": "assigned",
                },
            )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["display_name"], "改名")
        self.assertEqual(patched.json()["controller_member_id"], "agent:codex")
        self.assertEqual(patched.json()["controller_assignment_version"], 1)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

        # CLI `talk init` 重复注册只会拿到 409，不改写指定。
        reregister = self.register(controller_member_id="agent:kimi")
        self.assertEqual(reregister.status_code, 409)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

        # 版本没有被旁路推进：正确版本仍可正常清空。
        cleared = self.assign(payload={"member_id": None, "expected_version": 1})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(self.stored_state(), (None, 2))

    def test_sync_and_profile_write_do_not_touch_assignment(self):
        self.register(project_root_path=str(self._tmpdir / "root"))
        self.assertEqual(self.assign().status_code, 200)

        with self.make_client() as client:
            synced = client.post(
                "/api/projects/prj_ctl/sync",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "agents": [
                        {
                            "member_id": "agent:codex",
                            "business_role": "lead",
                            "decision_tier": "decision",
                            "controller_member_id": "agent:kimi",
                            "controller_assignment_version": 42,
                        },
                        {"member_id": "agent:kimi"},
                    ]
                },
            )
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

        with self.make_client() as client:
            profile = client.put(
                "/api/projects/prj_ctl/agents/agent%3Acodex/profile",
                headers={"X-API-Key": "bobo-key"},
                json={"identity": "# Codex\n工程执行者"},
            )
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))

        # 职责指定与 business_role / decision_tier 分开：sync 写入的标签不影响指定。
        with self.session() as session:
            roster = session.get(ProjectAgent, ("prj_ctl", "agent:codex"))
            self.assertEqual(roster.business_role, "lead")
            self.assertEqual(roster.decision_tier, "decision")
            project = session.get(Project, "prj_ctl")
            self.assertEqual(project.controller_member_id, "agent:codex")
        body = self.get_project().json()
        self.assertEqual(body["controller_member_id"], "agent:codex")
        self.assertEqual(body["controller_assignment_status"], "assigned")

    def test_controller_mode_cas_is_independent_from_assignment(self):
        self.register()
        mode = self.patch_mode(payload={"mode": "active", "expected_version": 0})
        self.assertEqual(mode.status_code, 200, mode.text)
        self.assertEqual(mode.json()["controller_mode"], "active")
        self.assertEqual(mode.json()["controller_mode_version"], 1)
        # C1a 兼容：模式版本推进不影响独立的主控指定版本。
        self.assertEqual(mode.json()["controller_assignment_version"], 0)
        self.assertEqual(self.stored_state(), (None, 0))

        self.assertEqual(self.assign().status_code, 200)
        body = self.get_project().json()
        self.assertEqual(body["controller_mode"], "active")
        self.assertEqual(body["controller_mode_version"], 1)
        self.assertEqual(body["controller_member_id"], "agent:codex")
        self.assertEqual(body["controller_assignment_version"], 1)
        self.assertIsNone(body.get("effective_mode"))

        # 指定版本陈旧/正确都与模式版本各自独立判定。
        stale_mode = self.patch_mode(payload={"mode": "passive", "expected_version": 0})
        self.assertEqual(stale_mode.status_code, 409)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))
        # 模式写入不能推进指定版本，指定版本仍是 1：陈旧指定请求仍冲突。
        stale_assign = self.assign(payload={"member_id": None, "expected_version": 0})
        self.assertEqual(stale_assign.status_code, 409)
        self.assertEqual(self.stored_state(), ("agent:codex", 1))
        normal_mode = self.patch_mode(payload={"mode": "passive", "expected_version": 1})
        self.assertEqual(normal_mode.status_code, 200, normal_mode.text)
        self.assertEqual(normal_mode.json()["controller_mode_version"], 2)
        self.assertEqual(normal_mode.json()["controller_assignment_version"], 1)


class ControllerAssignmentToolTests(ControllerAssignmentTestCase):
    """MCP ``talk_list_agents`` 顶层只读 controller_assignment。"""

    def setUp(self):
        super().setUp()
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        with self.make_client() as client:
            for project_id in ("prj_tools", "prj_other"):
                created = client.post(
                    "/api/projects",
                    headers={"X-API-Key": "bobo-key"},
                    json={"project_id": project_id, "display_name": project_id},
                )
                self.assertEqual(created.status_code, 201)
                synced = client.post(
                    f"/api/projects/{project_id}/sync",
                    headers={"X-API-Key": "bobo-key"},
                    json={"agents": [{"member_id": "agent:worker"}]},
                )
                self.assertEqual(synced.status_code, 200)

    def set_controller(self, project_id: str, member_id, expected_version: int):
        with self.make_client() as client:
            response = client.patch(
                f"/api/projects/{project_id}/controller-assignment",
                headers={"X-API-Key": "bobo-key"},
                json={"member_id": member_id, "expected_version": expected_version},
            )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def _environment(base_url: str, api_key: str, member_id: str) -> dict[str, str]:
        return {
            "TALK_BASE_URL": base_url,
            "TALK_API_KEY": api_key,
            "TALK_MEMBER_ID": member_id,
            "TALK_PROJECT_ID": "prj_tools",
        }

    def test_list_agents_reports_assignment_member_version_and_status(self):
        self.set_controller("prj_tools", "agent:worker", 0)
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        assignment = result["controller_assignment"]
        self.assertEqual(result["project_id"], "prj_tools")
        self.assertTrue(assignment["supported"])
        self.assertEqual(assignment["member_id"], "agent:worker")
        self.assertEqual(assignment["version"], 1)
        self.assertEqual(assignment["status"], "assigned")
        self.assertIn("不代表在线", assignment["note"])
        # 角色条目仍是原样，不重复写主控字段。
        for agent in result["agents"]:
            self.assertNotIn("controller_member_id", agent)
            self.assertNotIn("controller_assignment_status", agent)

    def test_assignment_matches_project_get_and_reuses_one_request(self):
        self.set_controller("prj_tools", "agent:worker", 0)
        requests: list[tuple[str, str]] = []
        real_request = talk_task_tools._api_request

        def counting_request(method, path, **kwargs):
            requests.append((method.upper(), path))
            return real_request(method, path, **kwargs)

        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                with patch.object(talk_task_tools, "_api_request", counting_request):
                    result = dispatch_tool("talk_list_agents", {})
                with self.make_client() as client:
                    direct = client.get(
                        "/api/projects/prj_tools", headers={"X-API-Key": "bobo-key"}
                    ).json()

        assignment = result["controller_assignment"]
        self.assertEqual(assignment["member_id"], direct["controller_member_id"])
        self.assertEqual(assignment["version"], direct["controller_assignment_version"])
        self.assertEqual(assignment["status"], direct["controller_assignment_status"])
        project_gets = [
            path for method, path in requests if method == "GET" and path == "/api/projects/prj_tools"
        ]
        self.assertEqual(len(project_gets), 1, requests)
        # 同一份项目响应里的 C1a 与 REQ-1 字段不回归。
        self.assertEqual(result["controller_mode"]["requested_mode"], direct["controller_mode"])
        self.assertEqual(
            result["development_requirements"], direct["development_requirements"]
        )

    def test_non_project_path_reports_null(self):
        with LiveTalkServer(main.app) as base_url:
            env = dict(self._environment(base_url, "bobo-key", "human:bobo"), TALK_PROJECT_ID="")
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        self.assertIsNone(result["project_id"])
        self.assertIsNone(result["controller_assignment"])
        self.assertIsNone(result["controller_mode"])

    def test_other_project_reports_its_own_assignment(self):
        self.set_controller("prj_tools", "agent:worker", 0)
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                other = dispatch_tool("talk_list_agents", {"project_id": "prj_other"})

        assignment = other["controller_assignment"]
        self.assertEqual(other["project_id"], "prj_other")
        self.assertTrue(assignment["supported"])
        self.assertIsNone(assignment["member_id"])
        self.assertEqual(assignment["version"], 0)
        self.assertEqual(assignment["status"], "unassigned")

    def test_old_backend_without_fields_is_marked_unsupported(self):
        """旧后端缺主控字段：明确 unsupported，不回退猜测成“未指定”或“已指定”。"""
        real_request = talk_task_tools._api_request

        def legacy_request(method, path, **kwargs):
            payload = real_request(method, path, **kwargs)
            if path == "/api/projects/prj_tools" and isinstance(payload, dict):
                payload = {
                    key: value
                    for key, value in payload.items()
                    if key
                    not in {
                        "controller_member_id",
                        "controller_assignment_version",
                        "controller_assignment_status",
                    }
                }
            return payload

        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                with patch.object(talk_task_tools, "_api_request", legacy_request):
                    result = dispatch_tool("talk_list_agents", {})

        assignment = result["controller_assignment"]
        self.assertFalse(assignment["supported"])
        self.assertIsNone(assignment["member_id"])
        self.assertIsNone(assignment["version"])
        self.assertEqual(assignment["status"], CONTROLLER_ASSIGNMENT_EFFECTIVE_STATUS_UNSUPPORTED)
        self.assertEqual(assignment["status"], "unsupported")
        self.assertIn("旧后端", assignment["note"])

    def test_project_read_failure_is_reported_not_faked(self):
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "bobo-key", "human:bobo")
            with patch.dict(os.environ, env, clear=False):
                with self.assertRaises(TalkToolError) as caught:
                    dispatch_tool("talk_list_agents", {"project_id": "prj_ghost"})
        self.assertIn("404", str(caught.exception))

    def test_summary_never_claims_online_ack_or_effective(self):
        assigned = controller_assignment_summary(
            {
                "project_id": "p",
                "controller_member_id": "agent:codex",
                "controller_assignment_version": 3,
                "controller_assignment_status": "assigned",
            }
        )
        self.assertTrue(assigned["supported"])
        self.assertEqual(assigned["status"], "assigned")
        # 只读对象字段固定：没有 online / ack / lease / effective 之类的“已生效”字段。
        self.assertEqual(
            set(assigned.keys()),
            {"project_id", "supported", "member_id", "version", "status", "note"},
        )
        self.assertEqual(assigned["note"], talk_task_tools.CONTROLLER_ASSIGNMENT_NOTE)
        self.assertIn("不代表在线", assigned["note"])
        self.assertIn("没有会话 token", assigned["note"])

        degraded = controller_assignment_summary({"project_id": "p"})
        self.assertFalse(degraded["supported"])
        self.assertEqual(degraded["status"], "unsupported")
        self.assertIsNone(degraded["member_id"])
        self.assertIsNone(degraded["version"])

        # 后端给了成员但状态不可识别：只报 unknown，不假定有效。
        unknown = controller_assignment_summary(
            {
                "project_id": "p",
                "controller_member_id": "agent:codex",
                "controller_assignment_version": 2,
            }
        )
        self.assertTrue(unknown["supported"])
        self.assertEqual(unknown["status"], CONTROLLER_ASSIGNMENT_STATUS_UNKNOWN)

        # 成员为 null 时无需额外信息即可如实判定未指定。
        unassigned = controller_assignment_summary(
            {
                "project_id": "p",
                "controller_member_id": None,
                "controller_assignment_version": 0,
                "controller_assignment_status": "not-a-status",
            }
        )
        self.assertEqual(unassigned["status"], "unassigned")

    def test_tool_surface_unchanged_and_description_documents_readonly(self):
        self.assertEqual(len(TOOL_SCHEMAS), 9)
        self.assertEqual(tuple(tool["name"] for tool in TOOL_SCHEMAS), PROJECT_TOOL_NAMES)
        description = tool_description("talk_list_agents")
        self.assertIn("controller_assignment", description)
        self.assertIn("assigned 只表示", description)
        self.assertIn("不代表在线", description)
        self.assertIn("unsupported", description)
        self.assertIn("human 显式清空", description)
        self.assertIn("不改变派发", description)

    def test_assignment_is_read_only_for_agents(self):
        """agent 身份经 MCP 读取指定不做任何写入；工具仍是原样 9 个入口。"""
        self.set_controller("prj_tools", "agent:worker", 0)
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url, "worker-key", "agent:worker")
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})

        self.assertEqual(result["controller_assignment"]["member_id"], "agent:worker")
        self.assertEqual(result["controller_assignment"]["version"], 1)
        self.assertEqual(self.stored_state("prj_tools"), ("agent:worker", 1))


class ControllerAssignmentMigrationTests(unittest.TestCase):
    """老库（projects 表没有 controller_member_id / controller_assignment_version）安全升级。"""

    def setUp(self):
        super().setUp()
        self._tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        self._tmp_root.mkdir(parents=True, exist_ok=True)
        self._old_engine = db.engine
        self._old_main_engine = main.engine
        self._setup_legacy(with_mode=True, include_requirements=True)
        self.addCleanup(self._restore_engines)

    def _setup_legacy(self, *, with_mode: bool, include_requirements: bool) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="talk-c1b-legacy-", dir=self._tmp_root))
        self.db_path = self._tmpdir / "legacy.db"
        self._write_legacy_database(
            with_mode=with_mode, include_requirements=include_requirements
        )
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        db.engine = self.engine
        main.engine = self.engine

    def _restore_engines(self):
        db.engine = self._old_engine
        main.engine = self._old_main_engine
        # Windows 下 sqlite 文件可能被未回收的连接短暂持有：dispose + 重试删除，避免残留临时库。
        self.engine.dispose()
        for _attempt in range(5):
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            if not self._tmpdir.exists():
                break
            gc.collect()
            time.sleep(0.2)
        self.assertFalse(self._tmpdir.exists(), f"临时测试目录未清理: {self._tmpdir}")

    def _write_legacy_database(self, *, with_mode: bool, include_requirements: bool) -> None:
        """写本片之前形态的 projects 表：可能停在 REQ-1 或 C1a 之前。"""
        requirements_column = (
            "development_requirements TEXT," if include_requirements else ""
        )
        mode_columns = (
            "controller_mode TEXT NOT NULL DEFAULT 'passive',"
            "controller_mode_version INTEGER NOT NULL DEFAULT 0,"
            if with_mode
            else ""
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""
                CREATE TABLE projects (
                    project_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    project_root_path TEXT,
                    {requirements_column}
                    {mode_columns}
                    maintainer_member_id TEXT NOT NULL,
                    created_at TIMESTAMP,
                    last_seen_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, display_name, description, project_root_path,
                    maintainer_member_id, created_at, last_seen_at
                ) VALUES (
                    'prj_legacy', 'Legacy Project', '升级前就存在的项目',
                    'D:/legacy/root', 'human:bobo',
                    '2026-01-01 00:00:00', '2026-01-02 00:00:00'
                )
                """
            )
            conn.commit()

    def _columns(self, table: str) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }

    def _seed_member(self):
        with Session(self.engine) as session:
            session.add(
                Member(
                    id="human:bobo",
                    kind="human",
                    display_name="Bobo",
                    api_key="bobo-key",
                )
            )
            session.commit()

    def test_legacy_database_upgrades_and_repeats_idempotently(self):
        self.assertNotIn("controller_member_id", self._columns("projects"))
        self.assertNotIn("controller_assignment_version", self._columns("projects"))

        db.init_db()
        db.init_db()  # 幂等：重复初始化不重建表、不覆盖数据

        self.assertIn("controller_member_id", self._columns("projects"))
        self.assertIn("controller_assignment_version", self._columns("projects"))
        with Session(self.engine) as session:
            legacy = session.get(Project, "prj_legacy")
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy.display_name, "Legacy Project")
            self.assertEqual(legacy.description, "升级前就存在的项目")
            self.assertEqual(legacy.project_root_path, "D:/legacy/root")
            self.assertIsNone(legacy.controller_member_id)
            self.assertEqual(legacy.controller_assignment_version, 0)
            self.assertEqual(legacy.controller_mode, "passive")
            self.assertEqual(len(session.exec(select(Project)).all()), 1)

    def test_oldest_legacy_database_gets_all_migrations(self):
        """停在 REQ-1 / C1a 之前的更老库：多批迁移可以在同一次升级里共存。"""
        self._restore_engines()
        self._setup_legacy(with_mode=False, include_requirements=False)

        self.assertNotIn("development_requirements", self._columns("projects"))
        db.init_db()
        self.assertIn("development_requirements", self._columns("projects"))
        self.assertIn("controller_mode", self._columns("projects"))
        self.assertIn("controller_member_id", self._columns("projects"))
        self.assertIn("controller_assignment_version", self._columns("projects"))
        with Session(self.engine) as session:
            legacy = session.get(Project, "prj_legacy")
            self.assertIsNone(legacy.controller_member_id)
            self.assertEqual(legacy.controller_assignment_version, 0)
            self.assertEqual(legacy.controller_mode_version, 0)
            self.assertEqual(len(session.exec(select(Project)).all()), 1)

    def test_legacy_project_round_trips_through_api_and_keeps_assignment(self):
        db.init_db()
        self._seed_member()
        with TestClient(main.app) as client:
            listed = client.get("/api/projects", headers={"X-API-Key": "bobo-key"})
            self.assertEqual(listed.status_code, 200)
            body = listed.json()[0]
            self.assertIsNone(body["controller_member_id"])
            self.assertEqual(body["controller_assignment_version"], 0)
            self.assertEqual(body["controller_assignment_status"], "unassigned")

            # 老项目没有名册：先 sync 再指定。
            synced = client.post(
                "/api/projects/prj_legacy/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": "agent:codex"}]},
            )
            self.assertEqual(synced.status_code, 200, synced.text)
            with Session(self.engine) as session:
                session.add(
                    Member(
                        id="agent:codex",
                        kind="agent",
                        display_name="Codex",
                        api_key="codex-key",
                    )
                )
                session.commit()

            assigned = client.patch(
                "/api/projects/prj_legacy/controller-assignment",
                headers={"X-API-Key": "bobo-key"},
                json={"member_id": "agent:codex", "expected_version": 0},
            )
            self.assertEqual(assigned.status_code, 200, assigned.text)
            self.assertEqual(assigned.json()["controller_assignment_version"], 1)

            db.init_db()  # 再次初始化不重置已升级数据
            after = client.get("/api/projects/prj_legacy", headers={"X-API-Key": "bobo-key"}).json()
            self.assertEqual(after["controller_member_id"], "agent:codex")
            self.assertEqual(after["controller_assignment_version"], 1)
            self.assertEqual(after["controller_assignment_status"], "assigned")


if __name__ == "__main__":
    unittest.main()
