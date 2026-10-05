"""ROLE-DESC-B1 项目角色说明：持久化与 REST 读写合同。

覆盖设计 ``.tmp/role-description-0/design.md``（R1）§3.2–§3.3 与 §7 验收清单中属于后端的内容：

- 保存 / 读取 / 覆盖 / 清空恢复默认，重复 null 清理幂等；
- 空白归一（Python ``str.isspace()`` 语义，N4）与 2000 Unicode 码点边界、
  **超长全空白按恢复默认而非 422**（D8 校验顺序）；
- agent 403、不在册非 null 写入 404、不在册 null 清理 200；
- 跨项目隔离、名册 sync 不覆盖说明、GET 与 sync 响应字段一致；
- 换行与 XSS 字面量原样保留；
- 项目删除显式清理新表行（且不追改既有 ``project_agents`` 孤儿行）；
- 说明不改变 ``business_role`` / ``decision_tier`` / 主控指定 / 任务权限。

本片不覆盖前端 F1/F2；也不启用长期服务，全部用进程内 TestClient。
"""

import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import event
from sqlmodel import Session, create_engine, select

import server.db as db
import server.main as main
from server.models import (
    PROJECT_ROLE_DESCRIPTION_MAX_CHARS,
    Project,
    ProjectAgent,
    ProjectRoleDescription,
    normalize_role_description,
)
from tests.test_support import RouteTestCase

DESCRIPTION = "负责后端实现与接口合同。\n第二行：独立复核后再进入下一片。"
DESCRIPTION_UPDATED = "更新后的说明：负责后端、主控工具与回归验证。"
XSS_DESCRIPTION = (
    "<img src=x onerror=alert(1)>\n"
    "<script>alert('xss')</script>\r\n"
    "结尾：换行与标签都按字面文本保存。"
)
MAX_CHARS = PROJECT_ROLE_DESCRIPTION_MAX_CHARS


def encode(member_id: str) -> str:
    return quote(member_id, safe="")


class RoleDescriptionApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:ann", api_key="ann-key", display_name="Ann")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        self.add_member("agent:other", api_key="other-key", display_name="Other")

    # ── helpers ──────────────────────────────────────────────────────

    def register(self, project_id: str):
        with self.make_client() as client:
            return client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": project_id, "display_name": project_id},
            )

    def sync(self, project_id: str, agents: list[dict], *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/sync",
                headers={"X-API-Key": key},
                json={"agents": agents},
            )

    def put_description(
        self,
        project_id: str,
        member_id: str,
        payload,
        *,
        key: str = "bobo-key",
        raw_body: dict | None = None,
    ):
        body = raw_body if raw_body is not None else {"description": payload}
        with self.make_client() as client:
            return client.put(
                f"/api/projects/{project_id}/agents/{encode(member_id)}/description",
                headers={"X-API-Key": key},
                json=body,
            )

    def get_agents(self, project_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/agents",
                headers={"X-API-Key": key},
            )

    def delete_project(self, project_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.delete(
                f"/api/projects/{project_id}",
                headers={"X-API-Key": key},
            )

    def description_rows(self, project_id: str) -> list[ProjectRoleDescription]:
        with self.session() as session:
            return list(
                session.exec(
                    select(ProjectRoleDescription).where(
                        ProjectRoleDescription.project_id == project_id
                    )
                ).all()
            )

    def roles_of(self, project_id: str) -> list[tuple[str, str, str]]:
        with self.session() as session:
            rows = session.exec(
                select(ProjectAgent)
                .where(ProjectAgent.project_id == project_id)
                .order_by(ProjectAgent.member_id)
            ).all()
            return [
                (row.member_id, row.business_role or "", row.decision_tier or "")
                for row in rows
            ]

    def agent_payload(self, project_id: str, member_id: str) -> dict:
        for agent in self.get_agents(project_id).json():
            if agent["member_id"] == member_id:
                return agent
        raise AssertionError(f"{member_id} not in project roster response")

    # ── 归一化单元事实（D8 顺序 + N4 空白集合） ──────────────────────

    def test_normalize_blank_semantics_follow_python_isspace(self):
        """N4：空白集合按 Python ``str.isspace()``，不是 JS ``trim()``。"""
        for blank in (
            "",
            "   \n\t  ",
            "\u3000\u00a0",  # 全角空格 + NBSP
            "\u001c\u001d\u001e\u001f\u0085",  # JS trim 会漏掉的文件/下一行分隔符
            "\u2028\u2029",  # 行/段分隔符
            "\u202f\u205f\u2000\u200a",
        ):
            with self.subTest(blank=repr(blank)):
                self.assertIsNone(normalize_role_description(blank))

        self.assertIsNone(normalize_role_description(None))
        # U+FEFF 在 Python 中不是空白：JS trim() 会误判为空白，后端按 Python 语义保留。
        self.assertEqual(normalize_role_description("\ufeff"), "\ufeff")
        # 非空白原文原样保留（不 strip、不折叠换行）。
        self.assertEqual(normalize_role_description(" 正文 "), " 正文 ")

    def test_normalize_checks_blank_before_length(self):
        """D8：超长全空白 → None（恢复默认），超长非空白 → ValueError（422）。"""
        self.assertIsNone(normalize_role_description(" " * (MAX_CHARS * 3)))
        self.assertIsNone(normalize_role_description("\u3000" * (MAX_CHARS + 500)))
        with self.assertRaises(ValueError):
            normalize_role_description("要" * (MAX_CHARS + 1))
        # 恰好达到上限仍然接受。
        self.assertEqual(len(normalize_role_description("要" * MAX_CHARS)), MAX_CHARS)

    # ── 保存 / 读取 / 覆盖 / 清空 ────────────────────────────────────

    def test_save_read_overwrite_and_clear_round_trip(self):
        self.register("prj_rd")
        self.sync(
            "prj_rd",
            [{"member_id": "agent:worker", "business_role": "dev", "decision_tier": "execution"}],
        )

        # 无自定义记录：null（前端据此回退默认文案）。
        self.assertIsNone(self.agent_payload("prj_rd", "agent:worker")["role_description"])
        self.assertEqual(self.description_rows("prj_rd"), [])

        saved = self.put_description("prj_rd", "agent:worker", DESCRIPTION)
        self.assertEqual(saved.status_code, 200)
        body = saved.json()
        self.assertEqual(body["project_id"], "prj_rd")
        self.assertEqual(body["member_id"], "agent:worker")
        self.assertEqual(body["description"], DESCRIPTION)
        self.assertEqual(body["updated_by"], "human:bobo")
        self.assertIsNotNone(body["updated_at"])

        self.assertEqual(
            self.agent_payload("prj_rd", "agent:worker")["role_description"],
            DESCRIPTION,
        )
        with self.session() as session:
            row = session.get(ProjectRoleDescription, ("prj_rd", "agent:worker"))
            self.assertEqual(row.description, DESCRIPTION)
            self.assertEqual(row.updated_by, "human:bobo")

        overwritten = self.put_description("prj_rd", "agent:worker", DESCRIPTION_UPDATED)
        self.assertEqual(overwritten.status_code, 200)
        self.assertEqual(overwritten.json()["description"], DESCRIPTION_UPDATED)
        self.assertEqual(
            self.agent_payload("prj_rd", "agent:worker")["role_description"],
            DESCRIPTION_UPDATED,
        )
        self.assertEqual(len(self.description_rows("prj_rd")), 1)

        cleared = self.put_description("prj_rd", "agent:worker", None)
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["description"], None)
        self.assertIsNone(cleared.json()["updated_at"])
        self.assertIsNone(cleared.json()["updated_by"])
        self.assertIsNone(self.agent_payload("prj_rd", "agent:worker")["role_description"])
        self.assertEqual(self.description_rows("prj_rd"), [])

        # 重复 null 清理幂等，仍 200 + description=null。
        again = self.put_description("prj_rd", "agent:worker", None)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["description"], None)
        self.assertEqual(self.description_rows("prj_rd"), [])

        # 清空后可以重新保存。
        resaved = self.put_description("prj_rd", "agent:worker", DESCRIPTION)
        self.assertEqual(resaved.status_code, 200)
        self.assertEqual(resaved.json()["description"], DESCRIPTION)

    def test_blank_variants_restore_default(self):
        self.register("prj_blank")
        self.sync("prj_blank", [{"member_id": "agent:worker"}])
        self.put_description("prj_blank", "agent:worker", DESCRIPTION)

        for blank in ("", "   \n\t  ", "\u3000", "\u0085\u001c", "\u00a0"):
            with self.subTest(blank=repr(blank)):
                response = self.put_description("prj_blank", "agent:worker", blank)
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json()["description"])
                self.assertEqual(self.description_rows("prj_blank"), [])
                self.assertIsNone(
                    self.agent_payload("prj_blank", "agent:worker")["role_description"]
                )
                # 再次写入，供下一轮空白变体继续验证“清空已有记录”。
                self.put_description("prj_blank", "agent:worker", DESCRIPTION)

        self.put_description("prj_blank", "agent:worker", None)
        self.assertEqual(self.description_rows("prj_blank"), [])

    def test_length_boundary_counts_unicode_code_points(self):
        self.register("prj_len")
        self.sync("prj_len", [{"member_id": "agent:worker"}])

        at_limit = "要" * MAX_CHARS
        accepted = self.put_description("prj_len", "agent:worker", at_limit)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["description"], at_limit)

        over_limit = "要" * (MAX_CHARS + 1)
        rejected = self.put_description("prj_len", "agent:worker", over_limit)
        self.assertEqual(rejected.status_code, 422)
        # 被拒绝的请求不落库：边界值保持不变。
        self.assertEqual(
            self.agent_payload("prj_len", "agent:worker")["role_description"], at_limit
        )

        # 补充平面字符按码点计数（😀 = U+1F600，1 个码点 / 2 个 UTF-16 码元）。
        emoji_at_limit = "😀" * MAX_CHARS
        emoji_accepted = self.put_description("prj_len", "agent:worker", emoji_at_limit)
        self.assertEqual(emoji_accepted.status_code, 200)
        self.assertEqual(len(emoji_accepted.json()["description"]), MAX_CHARS)
        emoji_over = self.put_description(
            "prj_len", "agent:worker", "😀" * (MAX_CHARS + 1)
        )
        self.assertEqual(emoji_over.status_code, 422)

        # D8：超长全空白不是 422，而是“恢复默认”。
        long_blank = self.put_description("prj_len", "agent:worker", " " * (MAX_CHARS * 3))
        self.assertEqual(long_blank.status_code, 200)
        self.assertIsNone(long_blank.json()["description"])
        self.assertEqual(self.description_rows("prj_len"), [])

        wide_blank = self.put_description(
            "prj_len", "agent:worker", "\u3000" * (MAX_CHARS + 500)
        )
        self.assertEqual(wide_blank.status_code, 200)
        self.assertIsNone(wide_blank.json()["description"])

    # ── 权限与 404 / 422 ─────────────────────────────────────────────

    def test_agent_can_read_but_not_write(self):
        self.register("prj_perm")
        self.sync("prj_perm", [{"member_id": "agent:worker"}])
        self.put_description("prj_perm", "agent:worker", DESCRIPTION)

        # D10：REST 层 agent 可读（与 business_role 同级），这是如实陈述的既有限度。
        readable = self.get_agents("prj_perm", key="worker-key")
        self.assertEqual(readable.status_code, 200)
        self.assertEqual(readable.json()[0]["role_description"], DESCRIPTION)

        for payload in (DESCRIPTION_UPDATED, None):
            with self.subTest(payload=payload):
                denied = self.put_description(
                    "prj_perm", "agent:worker", payload, key="worker-key"
                )
                self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            self.agent_payload("prj_perm", "agent:worker")["role_description"],
            DESCRIPTION,
        )

    def test_non_roster_write_404_and_clear_is_idempotent_200(self):
        self.register("prj_roster")
        self.sync("prj_roster", [{"member_id": "agent:worker"}])

        # 不在册成员：非 null 写入 404，且不落库。
        denied = self.put_description("prj_roster", "agent:other", DESCRIPTION)
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self.description_rows("prj_roster"), [])

        # 不在册成员：null 清理恒 200 + description=null。
        cleared = self.put_description("prj_roster", "agent:other", None)
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["description"], None)
        self.assertEqual(cleared.json()["member_id"], "agent:other")

        # 离册保留：成员被移出名册后说明行保留；重新入册后自动恢复（D11 预期行为）。
        self.put_description("prj_roster", "agent:worker", DESCRIPTION)
        self.sync("prj_roster", [])
        self.assertEqual(self.get_agents("prj_roster").json(), [])
        self.assertEqual(len(self.description_rows("prj_roster")), 1)

        self.sync("prj_roster", [{"member_id": "agent:worker"}])
        self.assertEqual(
            self.agent_payload("prj_roster", "agent:worker")["role_description"],
            DESCRIPTION,
        )

        # 离册状态下：null 清理仍幂等 200；非 null 写入仍是 404 且不会新建记录。
        self.sync("prj_roster", [])
        off_roster_clear = self.put_description("prj_roster", "agent:worker", None)
        self.assertEqual(off_roster_clear.status_code, 200)
        self.assertEqual(off_roster_clear.json()["description"], None)
        self.assertEqual(self.description_rows("prj_roster"), [])

        still_denied = self.put_description("prj_roster", "agent:worker", DESCRIPTION)
        self.assertEqual(still_denied.status_code, 404)
        self.assertEqual(self.description_rows("prj_roster"), [])

    def test_missing_or_invalid_description_key_is_422(self):
        self.register("prj_body")
        self.sync("prj_body", [{"member_id": "agent:worker"}])
        self.put_description("prj_body", "agent:worker", DESCRIPTION)

        missing = self.put_description("prj_body", "agent:worker", None, raw_body={})
        self.assertEqual(missing.status_code, 422)

        invalid = self.put_description(
            "prj_body", "agent:worker", None, raw_body={"description": 123}
        )
        self.assertEqual(invalid.status_code, 422)

        # 422 不影响既有值。
        self.assertEqual(
            self.agent_payload("prj_body", "agent:worker")["role_description"],
            DESCRIPTION,
        )

    def test_unknown_project_is_404(self):
        self.assertEqual(
            self.put_description("prj_ghost", "agent:worker", DESCRIPTION).status_code,
            404,
        )
        self.assertEqual(
            self.put_description("prj_ghost", "agent:worker", None).status_code, 404
        )

    def test_role_description_is_filled_with_one_batch_query(self):
        """D3：GET /agents 只用一条 ``project_role_descriptions`` 批量查询，不按成员 N+1。"""
        self.register("prj_batch")
        self.sync(
            "prj_batch",
            [
                {"member_id": "agent:other"},
                {"member_id": "agent:worker"},
                {"member_id": "agent:ghost"},  # 未注册成员也在名册里，不能因此多查库
            ],
        )
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", _capture)
        try:
            listed = self.get_agents("prj_batch")
        finally:
            event.remove(self.engine, "before_cursor_execute", _capture)

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 3)
        matched = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT")
            and "project_role_descriptions" in statement
        ]
        self.assertEqual(len(matched), 1, matched)

    # ── sync / GET 一致性与隔离 ──────────────────────────────────────

    def test_sync_keeps_description_and_get_sync_agree(self):
        self.register("prj_sync")
        roster = [
            {"member_id": "agent:other", "business_role": "reviewer"},
            {"member_id": "agent:worker", "business_role": "dev"},
        ]
        self.sync("prj_sync", roster)
        self.put_description("prj_sync", "agent:worker", DESCRIPTION)

        # 全量替换名册（含改角色）不会覆盖手工说明。
        synced = self.sync(
            "prj_sync",
            [
                {"member_id": "agent:worker", "business_role": "lead", "decision_tier": "decision"},
                {"member_id": "agent:other", "business_role": "tester"},
            ],
        )
        self.assertEqual(synced.status_code, 200)
        listed = self.get_agents("prj_sync")

        by_member_sync = {entry["member_id"]: entry for entry in synced.json()}
        by_member_get = {entry["member_id"]: entry for entry in listed.json()}
        self.assertEqual(set(by_member_sync), {"agent:worker", "agent:other"})
        for member_id, payload in by_member_sync.items():
            with self.subTest(member_id=member_id):
                self.assertEqual(
                    payload["role_description"], by_member_get[member_id]["role_description"]
                )
        self.assertEqual(by_member_sync["agent:worker"]["role_description"], DESCRIPTION)
        self.assertIsNone(by_member_sync["agent:other"]["role_description"])
        self.assertEqual(by_member_sync["agent:worker"]["business_role"], "lead")
        self.assertEqual(by_member_sync["agent:worker"]["decision_tier"], "decision")

    def test_descriptions_are_isolated_per_project(self):
        self.register("prj_a")
        self.register("prj_b")
        for project_id in ("prj_a", "prj_b"):
            self.sync(project_id, [{"member_id": "agent:worker"}])

        self.put_description("prj_a", "agent:worker", "A 项目的说明")
        self.put_description("prj_b", "agent:worker", "B 项目的说明")

        self.assertEqual(
            self.agent_payload("prj_a", "agent:worker")["role_description"], "A 项目的说明"
        )
        self.assertEqual(
            self.agent_payload("prj_b", "agent:worker")["role_description"], "B 项目的说明"
        )

        self.put_description("prj_a", "agent:worker", None)
        self.assertIsNone(self.agent_payload("prj_a", "agent:worker")["role_description"])
        self.assertEqual(
            self.agent_payload("prj_b", "agent:worker")["role_description"], "B 项目的说明"
        )
        self.assertEqual(
            [(row.project_id, row.member_id) for row in self.description_rows("prj_b")],
            [("prj_b", "agent:worker")],
        )

    def test_newlines_and_xss_literals_are_preserved_verbatim(self):
        self.register("prj_raw")
        self.sync("prj_raw", [{"member_id": "agent:worker"}])

        saved = self.put_description("prj_raw", "agent:worker", XSS_DESCRIPTION)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["description"], XSS_DESCRIPTION)

        fetched = self.agent_payload("prj_raw", "agent:worker")["role_description"]
        self.assertEqual(fetched, XSS_DESCRIPTION)
        self.assertIn("<script>", fetched)
        self.assertIn("\r\n", fetched)
        self.assertEqual(fetched.count("\n"), XSS_DESCRIPTION.count("\n"))

    # ── 项目删除与行为不变项 ─────────────────────────────────────────

    def test_project_delete_removes_description_rows_only(self):
        self.register("prj_del")
        self.register("prj_keep")
        for project_id in ("prj_del", "prj_keep"):
            self.sync(
                project_id,
                [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
            )
        self.put_description("prj_del", "agent:worker", DESCRIPTION)
        self.put_description("prj_del", "agent:other", "另一个角色的说明")
        self.put_description("prj_keep", "agent:worker", "保留项目的说明")

        deleted = self.delete_project("prj_del")
        self.assertEqual(deleted.status_code, 204)

        self.assertEqual(self.description_rows("prj_del"), [])
        self.assertEqual(
            [(row.project_id, row.member_id) for row in self.description_rows("prj_keep")],
            [("prj_keep", "agent:worker")],
        )
        # D9 明确不追改既有 project_agents 孤儿行：删除项目后旧名册行仍在。
        self.assertEqual(len(self.roles_of("prj_del")), 2)
        self.assertEqual(self.get_agents("prj_del").status_code, 404)
        self.assertEqual(
            self.agent_payload("prj_keep", "agent:worker")["role_description"],
            "保留项目的说明",
        )

    def test_description_does_not_change_roles_controller_or_task_authority(self):
        self.register("prj_side")
        self.sync(
            "prj_side",
            [
                {
                    "member_id": "agent:worker",
                    "business_role": "lead",
                    "decision_tier": "decision",
                    "capability_summary": ["后端"],
                }
            ],
        )
        assigned = self.make_client()
        with assigned as client:
            controller = client.patch(
                "/api/projects/prj_side/controller-assignment",
                headers={"X-API-Key": "bobo-key"},
                json={"member_id": "agent:worker", "expected_version": 0},
            )
        self.assertEqual(controller.status_code, 200)
        self.assertEqual(controller.json()["controller_member_id"], "agent:worker")

        with self.make_client() as client:
            task = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:worker",
                    "content": "角色说明不得改变任务权限",
                    "project_id": "prj_side",
                    "may_delegate": True,
                },
            )
        self.assertEqual(task.status_code, 201)
        task_id = task.json()["id"]

        roles_before = self.roles_of("prj_side")
        task_before = task.json()
        authority_keys = (
            "may_delegate",
            "max_delegation_depth",
            "max_running_descendants",
            "max_running_per_target",
            "max_nonterminal_descendants",
            "control_status",
            "authorization_epoch",
            "authorized_slice_budget",
            "reserved_slice_count",
            "task_kind",
            "status",
            "workflow_status",
        )

        self.put_description("prj_side", "agent:worker", DESCRIPTION)
        self.put_description("prj_side", "agent:worker", None)

        self.assertEqual(self.roles_of("prj_side"), roles_before)

        with self.make_client() as client:
            project_after = client.get(
                "/api/projects/prj_side", headers={"X-API-Key": "bobo-key"}
            ).json()
            task_after = client.get(
                f"/api/tasks/{task_id}", headers={"X-API-Key": "bobo-key"}
            ).json()

        self.assertEqual(project_after["controller_member_id"], "agent:worker")
        self.assertEqual(
            project_after["controller_assignment_version"],
            controller.json()["controller_assignment_version"],
        )
        self.assertEqual(project_after["controller_mode"], controller.json()["controller_mode"])
        self.assertEqual(project_after["controller_assignment_status"], "assigned")
        for key in authority_keys:
            with self.subTest(key=key):
                self.assertEqual(task_after[key], task_before[key])


class RoleDescriptionSchemaTests(unittest.TestCase):
    """新表由 ``create_all`` 创建：老库升级幂等，不重建、不丢既有数据。"""

    def setUp(self):
        super().setUp()
        tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self._tmpdir = Path(tempfile.mkdtemp(prefix="talk-legacy-rd-", dir=tmp_root))
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
        # Windows 下连接池未释放会锁住 sqlite 文件，先 dispose 再删除临时目录。
        self.engine.dispose()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_legacy_database(self):
        """本片之前形态的老库：完全没有 project_role_descriptions 表。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE projects (
                    project_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    project_root_path TEXT,
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

    def _tables(self) -> set[str]:
        with self.engine.connect() as conn:
            return {
                row[0]
                for row in conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

    def test_create_all_adds_table_and_repeats_idempotently(self):
        self.assertNotIn("project_role_descriptions", self._tables())

        db.init_db()
        db.init_db()  # 重复初始化必须幂等

        self.assertIn("project_role_descriptions", self._tables())
        with Session(self.engine) as session:
            legacy = session.get(Project, "prj_legacy")
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy.display_name, "Legacy Project")
            self.assertEqual(legacy.description, "升级前就存在的项目")

        # 主键 (project_id, member_id)：同项目同成员一行，跨项目同成员可并存。
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            session.add(
                ProjectRoleDescription(
                    project_id="prj_legacy",
                    member_id="agent:worker",
                    description="说明",
                    updated_by="human:bobo",
                    updated_at=now,
                )
            )
            session.add(
                ProjectRoleDescription(
                    project_id="prj_other",
                    member_id="agent:worker",
                    description="另一个项目的说明",
                    updated_by="human:bobo",
                    updated_at=now,
                )
            )
            session.commit()

        with Session(self.engine) as session:
            row = session.get(ProjectRoleDescription, ("prj_legacy", "agent:worker"))
            other = session.get(ProjectRoleDescription, ("prj_other", "agent:worker"))
            self.assertEqual(row.description, "说明")
            self.assertEqual(other.description, "另一个项目的说明")


if __name__ == "__main__":
    unittest.main()
