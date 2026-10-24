"""角色生命周期 R1-1：项目角色身份、命名、投影与读取合同测试。

覆盖实施计划 §3.2/§3.3/§3.4 与合同 §4.1.2、§5.2、§7.3、§14（I1/I2/I3/I21/I22/I53）：

- ``POST /api/projects/{id}/roles`` 服务端原子创建（TX-ALL）：六张表一次提交、Key 仅一次；
- ``role_name`` 空白 422 ``role_name_invalid``、纯中文合法、项目内唯一、跨项目同名并存；
- ``member_id`` 冲突只换随机后缀，**绝不复用**既有成员；归档后同名重建必然新身份；
- ``GET roles`` 的历史名册兼容投影与 ``model.choice_id`` 可信来源
  （``creation_operation`` / ``creation_operation_mismatch`` / ``legacy_manual``）；
- ``PATCH roles/{member_id}`` 只改项目内 ``role_name``（不动 ``members.display_name``）、
  介绍与 human-only 的 ``review_exempt``；未知字段 422、agent 403；
- ``GET roles/{member_id}/tasks`` 只读非终态摘要。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型、不读凭据。
本模块同时导出其余 R1-1 角色测试共用的 ``RoleApiTestCase`` 夹具基类。
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import quote

from sqlmodel import select

from server.models import (
    CHOICE_SOURCE_CREATION_OPERATION,
    CHOICE_SOURCE_LEGACY_ATTACH,
    CHOICE_SOURCE_LEGACY_ATTACH_MISMATCH,
    CHOICE_SOURCE_LEGACY_MANUAL,
    Member,
    Project,
    ProjectAgent,
    ProjectRole,
    ProjectRoleBinding,
    ProjectRoleDescription,
    ProjectRolePolicy,
    RoleCreationOperation,
    RoleLegacyAttachOperation,
    RunnerModelChoice,
)
from tests.test_support import RouteTestCase

RUNNER_ID = "runner:dsh-cli"
CHOICE_DEFAULTS = {
    "model_id": "deepseek-flash",
    "model_source": "builtin",
    "provider_id": "managed:deepseek",
    "connection_ref": "native-deepseek-managed-login",
    "model_alias": "deepseek-flash",
    "model_display_name": "DeepSeek Flash",
    "source_kind": "declared",
}


def encode(member_id: str) -> str:
    return quote(member_id, safe="")


class RoleApiTestCase(RouteTestCase):
    """R1-1 角色接口公共夹具：human / agent 成员、项目、运行器与模型选择。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:ann", api_key="ann-key", display_name="Ann")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        self.add_member("agent:other", api_key="other-key", display_name="Other")

    # ── helpers ──────────────────────────────────────────────────────

    def register_project(self, project_id: str = "prj_alpha", *, key: str = "bobo-key", **extra):
        body = {"project_id": project_id, "display_name": project_id}
        body.update(extra)
        with self.make_client() as client:
            return client.post("/api/projects", headers={"X-API-Key": key}, json=body)

    def sync_roster(self, project_id: str, agents: list[dict], *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/sync",
                headers={"X-API-Key": key},
                json={"agents": agents},
            )

    def register_runner(
        self,
        runner_id: str = RUNNER_ID,
        *,
        runtime: str = "dsh",
        adapter_status: str = "adapted",
        key: str = "bobo-key",
    ):
        with self.make_client() as client:
            return client.post(
                "/api/runners",
                headers={"X-API-Key": key},
                json={
                    "runner_id": runner_id,
                    "runtime": runtime,
                    "display_name": "DSH CLI",
                    "adapter_status": adapter_status,
                },
            )

    def create_choice(self, runner_id: str = RUNNER_ID, *, key: str = "bobo-key", **overrides):
        body = dict(CHOICE_DEFAULTS)
        body.update(overrides)
        with self.make_client() as client:
            return client.post(
                f"/api/runners/{runner_id}/model-choices",
                headers={"X-API-Key": key},
                json=body,
            )

    def seed_runner_and_choice(self, *, runner_id: str = RUNNER_ID) -> str:
        self.register_runner(runner_id)
        return self.create_choice(runner_id).json()["choice_id"]

    def create_role(
        self,
        project_id: str,
        *,
        role_name: str,
        runner_id: str = RUNNER_ID,
        choice_id: str,
        operation_key: str,
        role_description=None,
        key: str = "bobo-key",
        extra: dict | None = None,
    ):
        body = {
            "role_name": role_name,
            "runner_id": runner_id,
            "choice_id": choice_id,
            "operation_key": operation_key,
        }
        if role_description is not None:
            body["role_description"] = role_description
        if extra:
            body.update(extra)
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/roles",
                headers={"X-API-Key": key},
                json=body,
            )

    def get_roles(self, project_id: str = "prj_alpha", *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/roles", headers={"X-API-Key": key}
            )

    def patch_role(
        self,
        project_id: str,
        member_id: str,
        body: dict,
        *,
        key: str = "bobo-key",
    ):
        with self.make_client() as client:
            return client.patch(
                f"/api/projects/{project_id}/roles/{encode(member_id)}",
                headers={"X-API-Key": key},
                json=body,
            )

    def rotate_key(self, project_id: str, member_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/roles/{encode(member_id)}/rotate-key",
                headers={"X-API-Key": key},
            )

    def get_role_tasks(self, project_id: str, member_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/roles/{encode(member_id)}/tasks",
                headers={"X-API-Key": key},
            )

    def put_binding(self, project_id: str, member_id: str, binding, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.put(
                f"/api/projects/{project_id}/agents/{encode(member_id)}/binding",
                headers={"X-API-Key": key},
                json={"binding": binding},
            )

    def create_task(self, project_id: str, target_member_id: str, *, key: str = "bobo-key", **extra):
        body = {"target_member_id": target_member_id, "content": "do it", "project_id": project_id}
        body.update(extra)
        with self.make_client() as client:
            return client.post("/api/tasks", headers={"X-API-Key": key}, json=body)

    # ── row helpers ──────────────────────────────────────────────────

    def role_rows(self, project_id: str = "prj_alpha") -> list[ProjectRole]:
        with self.session() as session:
            return list(
                session.exec(
                    select(ProjectRole).where(ProjectRole.project_id == project_id)
                ).all()
            )

    def operation_rows(self, project_id: str = "prj_alpha") -> list[RoleCreationOperation]:
        with self.session() as session:
            return list(
                session.exec(
                    select(RoleCreationOperation).where(
                        RoleCreationOperation.project_id == project_id
                    )
                ).all()
            )

    def binding_rows(self, project_id: str = "prj_alpha") -> list[ProjectRoleBinding]:
        with self.session() as session:
            return list(
                session.exec(
                    select(ProjectRoleBinding).where(
                        ProjectRoleBinding.project_id == project_id
                    )
                ).all()
            )

    def policy_rows(self, project_id: str = "prj_alpha") -> list[ProjectRolePolicy]:
        with self.session() as session:
            return list(
                session.exec(
                    select(ProjectRolePolicy).where(
                        ProjectRolePolicy.project_id == project_id
                    )
                ).all()
            )

    def description_rows(self, project_id: str = "prj_alpha") -> list[ProjectRoleDescription]:
        with self.session() as session:
            return list(
                session.exec(
                    select(ProjectRoleDescription).where(
                        ProjectRoleDescription.project_id == project_id
                    )
                ).all()
            )

    def roster_rows(self, project_id: str = "prj_alpha") -> list[ProjectAgent]:
        with self.session() as session:
            return list(
                session.exec(
                    select(ProjectAgent).where(ProjectAgent.project_id == project_id)
                ).all()
            )

    def role_entry(self, member_id: str, project_id: str = "prj_alpha") -> dict:
        payload = self.get_roles(project_id).json()
        return next(entry for entry in payload if entry["member_id"] == member_id)

    def archive_role(self, project_id: str, member_id: str) -> None:
        """R1-1 无归档入口：测试直接构造归档事实（合同 §3.7 已登记该边界）。"""
        with self.session() as session:
            role = session.get(ProjectRole, (project_id, member_id))
            role.archived_at = datetime.now(timezone.utc)
            session.add(role)
            session.commit()

    def make_direct_member(self, member_id: str, *, api_key: str, display_name: str) -> None:
        with self.session() as session:
            session.add(
                Member(
                    id=member_id,
                    kind="agent",
                    display_name=display_name,
                    api_key=api_key,
                )
            )
            session.commit()


class ProjectRoleApiTests(RoleApiTestCase):
    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.register_project("prj_beta")
        self.choice_id = self.seed_runner_and_choice()

    # ── 创建 ────────────────────────────────────────────────────────

    def test_create_role_writes_six_facts_and_returns_key_once(self):
        created = self.create_role(
            "prj_alpha",
            role_name="后端开发",
            choice_id=self.choice_id,
            operation_key="op-key-0001",
            role_description="负责后端切片",
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertFalse(body["reused"])
        self.assertEqual(body["credential_version"], 1)
        member_id = body["member_id"]
        self.assertTrue(member_id.startswith("agent:prj-alpha.role-"))
        self.assertTrue(body["api_key"])
        role = body["role"]
        self.assertEqual(role["role_name"], "后端开发")
        self.assertEqual(role["origin"], "managed")
        self.assertEqual(role["identity"], "managed")
        self.assertTrue(role["identity_exclusive"])
        self.assertFalse(role["archived"])
        # R1-3：``service`` 不再是 R1-1 的恒 null，而是真实只读投影；新角色无状态行时
        # 如实报告默认 stopped / not_started，且不返回 token/argv/绝对路径。
        self.assertEqual(role["service"]["desired"], "stopped")
        self.assertEqual(role["service"]["observed"], "not_started")
        self.assertIsNone(role["service"]["current_launch"])
        self.assertFalse(role["service"]["can_start"])
        self.assertEqual(role["model"]["choice_id"], self.choice_id)
        self.assertEqual(role["model"]["choice_source"], "creation_operation")
        self.assertFalse(role["model"]["choice_binding_mismatch"])
        self.assertEqual(role["model"]["model_id"], "deepseek-flash")

        # Key 立即可用于鉴权（真实写入 members.api_key）。
        with self.make_client() as client:
            me = client.get("/api/members/me", headers={"X-API-Key": body["api_key"]})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["id"], member_id)

        with self.session() as session:
            member = session.get(Member, member_id)
            self.assertEqual(member.kind, "agent")
            self.assertEqual(member.display_name, "后端开发")
            role_row = session.get(ProjectRole, ("prj_alpha", member_id))
            self.assertEqual(role_row.credential_version, 1)
            self.assertEqual(role_row.identity_exclusive, 1)
            self.assertIsNotNone(role_row.key_issued_at)
            self.assertIsNone(role_row.archived_at)
        self.assertEqual(len(self.roster_rows()), 1)
        binding = self.binding_rows()[0]
        self.assertEqual(binding.runner_id, RUNNER_ID)
        self.assertEqual(binding.provider_id, "managed:deepseek")
        self.assertEqual(binding.connection_ref, "native-deepseek-managed-login")
        self.assertEqual(binding.model_alias, "deepseek-flash")
        self.assertEqual(len(self.operation_rows()), 1)
        self.assertEqual(len(self.description_rows()), 1)
        self.assertEqual(self.description_rows()[0].description, "负责后端切片")

    def test_create_requires_human_and_valid_payload(self):
        self.assertEqual(
            self.create_role(
                "prj_alpha",
                role_name="x",
                choice_id=self.choice_id,
                operation_key="op-key-0002",
                key="worker-key",
            ).status_code,
            403,
        )
        for role_name in ("", "   ", "\n", "名" * 65):
            with self.subTest(role_name=role_name):
                response = self.create_role(
                    "prj_alpha",
                    role_name=role_name,
                    choice_id=self.choice_id,
                    operation_key="op-key-0003",
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], "role_name_invalid")
        unknown = self.create_role(
            "prj_alpha",
            role_name="ok",
            choice_id=self.choice_id,
            operation_key="op-key-0004",
            extra={"decision_tier": "decision"},
        )
        self.assertEqual(unknown.status_code, 422)
        short_key = self.create_role(
            "prj_alpha",
            role_name="ok",
            choice_id=self.choice_id,
            operation_key="short",
        )
        self.assertEqual(short_key.status_code, 422)
        self.assertEqual(self.role_rows(), [])
        self.assertEqual(self.binding_rows(), [])

    def test_chinese_name_is_accepted_and_slug_falls_back(self):
        created = self.create_role(
            "prj_alpha",
            role_name="  中文角色  ",
            choice_id=self.choice_id,
            operation_key="op-key-0005",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["role"]["role_name"], "中文角色")
        self.assertRegex(created.json()["member_id"], r"^agent:prj-alpha\.role-[0-9a-f]{8}$")

    def test_unknown_project_runner_and_choice(self):
        missing_project = self.create_role(
            "prj_ghost",
            role_name="x",
            choice_id=self.choice_id,
            operation_key="op-key-0006",
        )
        self.assertEqual(missing_project.status_code, 404)
        self.assertEqual(
            self.create_role(
                "prj_alpha",
                role_name="x",
                runner_id="runner:ghost",
                choice_id=self.choice_id,
                operation_key="op-key-0007",
            ).status_code,
            404,
        )
        self.assertEqual(
            self.create_role(
                "prj_alpha",
                role_name="x",
                choice_id="rmc_000000000000",
                operation_key="op-key-0008",
            ).status_code,
            404,
        )

    def test_retired_runner_and_choice_are_refused_for_new_roles(self):
        self.register_runner("runner:old")
        retired_choice = self.create_choice("runner:old").json()["choice_id"]
        with self.make_client() as client:
            client.patch(
                "/api/runners/runner:old",
                headers={"X-API-Key": "bobo-key"},
                json={"adapter_status": "retired"},
            )
        refused_runner = self.create_role(
            "prj_alpha",
            role_name="x",
            runner_id="runner:old",
            choice_id=retired_choice,
            operation_key="op-key-0009",
        )
        self.assertEqual(refused_runner.status_code, 409)
        self.assertEqual(refused_runner.json()["detail"], "runner_retired")

        choice_id = self.choice_id
        with self.make_client() as client:
            client.patch(
                f"/api/runners/{RUNNER_ID}/model-choices/{choice_id}",
                headers={"X-API-Key": "bobo-key"},
                json={"retired_at": "2026-10-11T00:00:00+00:00"},
            )
        refused_choice = self.create_role(
            "prj_alpha",
            role_name="x",
            choice_id=choice_id,
            operation_key="op-key-0010",
        )
        self.assertEqual(refused_choice.status_code, 409)
        self.assertEqual(refused_choice.json()["detail"], "choice_retired")
        self.assertEqual(self.role_rows(), [])

    def test_choice_must_belong_to_requested_runner(self):
        self.register_runner("runner:other", runtime="codex")
        other_choice = self.create_choice("runner:other").json()["choice_id"]
        mismatched = self.create_role(
            "prj_alpha",
            role_name="x",
            choice_id=other_choice,
            operation_key="op-key-0011",
        )
        self.assertEqual(mismatched.status_code, 404)
        self.assertEqual(mismatched.json()["detail"], "choice_not_found")

    def test_duplicate_active_name_conflicts_but_other_project_is_fine(self):
        first = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0012",
        )
        self.assertEqual(first.status_code, 201)
        duplicate = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0013",
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["detail"], "role_name_conflict")
        other_project = self.create_role(
            "prj_beta",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0014",
        )
        self.assertEqual(other_project.status_code, 201)
        self.assertNotEqual(
            other_project.json()["member_id"], first.json()["member_id"]
        )
        self.assertEqual(len(self.role_rows("prj_alpha")), 1)
        self.assertEqual(len(self.role_rows("prj_beta")), 1)

    def test_archived_same_name_rebuild_gets_new_identity(self):
        first = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0015",
            role_description="老角色",
        )
        old_member_id = first.json()["member_id"]
        self.archive_role("prj_alpha", old_member_id)

        rebuilt = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0016",
        )
        self.assertEqual(rebuilt.status_code, 201)
        self.assertNotEqual(rebuilt.json()["member_id"], old_member_id)

        rows = {row.member_id: row for row in self.role_rows()}
        self.assertIsNotNone(rows[old_member_id].archived_at)
        self.assertEqual(rows[old_member_id].role_name, "dev")
        self.assertIsNone(rows[rebuilt.json()["member_id"]].archived_at)
        # 老角色的绑定/说明/历史保留。
        self.assertEqual(len(self.binding_rows()), 2)
        self.assertEqual(len(self.description_rows()), 1)
        self.assertEqual(len(self.operation_rows()), 2)
        # 老成员行保留且不被复用。
        with self.session() as session:
            self.assertIsNotNone(session.get(Member, old_member_id))
            self.assertEqual(
                session.get(ProjectRole, ("prj_alpha", old_member_id)).archived_at
                is not None,
                True,
            )

    def test_member_id_collision_retries_new_suffix_without_reuse(self):
        self.make_direct_member(
            "agent:prj-alpha.dev-deadbeef", api_key="existing-key", display_name="Existing"
        )
        with patch(
            "server.routes.projects.new_role_member_id_suffix",
            side_effect=["deadbeef", "cafebabe"],
        ):
            created = self.create_role(
                "prj_alpha",
                role_name="dev",
                choice_id=self.choice_id,
                operation_key="op-key-0017",
            )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["member_id"], "agent:prj-alpha.dev-cafebabe")
        with self.session() as session:
            existing = session.get(Member, "agent:prj-alpha.dev-deadbeef")
            self.assertEqual(existing.api_key, "existing-key")
            self.assertEqual(existing.display_name, "Existing")

    def test_member_id_allocation_failure_is_stable(self):
        with patch(
            "server.routes.projects.new_role_member_id_suffix",
            return_value="deadbeef",
        ):
            self.make_direct_member(
                "agent:prj-alpha.dev-deadbeef",
                api_key="existing-key",
                display_name="Existing",
            )
            created = self.create_role(
                "prj_alpha",
                role_name="dev",
                choice_id=self.choice_id,
                operation_key="op-key-0018",
            )
        self.assertEqual(created.status_code, 409)
        self.assertEqual(created.json()["detail"], "member_id_allocation_failed")
        self.assertEqual(self.role_rows(), [])
        self.assertEqual(self.operation_rows(), [])

    # ── 读取投影 ─────────────────────────────────────────────────────

    def test_role_list_key_shape_and_no_credentials(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0019",
        )
        raw = self.get_roles().text
        self.assertNotIn(created.json()["api_key"], raw)
        self.assertNotIn("owner_token", raw)
        self.assertNotIn("claim_token", raw)
        entry = self.get_roles().json()[0]
        self.assertEqual(
            set(entry),
            {
                "member_id",
                "role_name",
                "origin",
                "identity",
                "archived",
                "identity_exclusive",
                "runner",
                "model",
                "role_description",
                "binding_state",
                "service",
                "deletion",
            },
        )
        self.assertEqual(
            set(entry["model"]),
            {
                "choice_id",
                "choice_source",
                "choice_binding_mismatch",
                "model_id",
                "model_alias",
                "model_display_name",
            },
        )
        self.assertEqual(
            set(entry["runner"]), {"runner_id", "runtime", "display_name", "status"}
        )
        self.assertEqual(entry["binding_state"], "bound")
        self.assertEqual(entry["runner"]["runtime"], "dsh")

    def test_choice_projection_mismatch_and_legacy(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0020",
        )
        member_id = created.json()["member_id"]
        self.assertEqual(
            self.role_entry(member_id)["model"]["choice_id"], self.choice_id
        )

        # 手工改绑（六维失配）→ 不再返回旧 choice_id。
        rewritten = self.put_binding(
            "prj_alpha",
            member_id,
            {
                "runner_id": RUNNER_ID,
                "model_source": "custom_api",
                "provider_id": "managed:deepseek",
                "connection_ref": "other-connection",
                "model_id": "deepseek-flash",
                "model_alias": "deepseek-flash",
            },
        )
        self.assertEqual(rewritten.status_code, 200)
        entry = self.role_entry(member_id)
        self.assertIsNone(entry["model"]["choice_id"])
        self.assertEqual(
            entry["model"]["choice_source"], "creation_operation_mismatch"
        )
        self.assertTrue(entry["model"]["choice_binding_mismatch"])

        # 老名册（只 sync，无角色行/无操作行）→ legacy_manual，不按 model_id 猜。
        self.sync_roster(
            "prj_alpha",
            [
                {
                    "member_id": "agent:worker",
                    "identity_path": ".talk/agents/agent_worker/IDENTITY.md",
                }
            ],
        )
        legacy = self.role_entry("agent:worker")
        self.assertEqual(legacy["origin"], "imported")
        self.assertEqual(legacy["identity"], "legacy")
        self.assertFalse(legacy["identity_exclusive"])
        self.assertIsNone(legacy["model"]["choice_id"])
        self.assertEqual(legacy["model"]["choice_source"], "legacy_manual")
        self.assertFalse(legacy["model"]["choice_binding_mismatch"])
        self.assertEqual(legacy["role_name"], "Worker")

    def test_archived_role_still_listed_with_archived_flag(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0021",
        )
        member_id = created.json()["member_id"]
        self.archive_role("prj_alpha", member_id)
        entry = self.role_entry(member_id)
        self.assertTrue(entry["archived"])

    def test_roles_list_requires_project(self):
        self.assertEqual(self.get_roles("prj_ghost").status_code, 404)

    # ── 改名 / 介绍 / 豁免 ───────────────────────────────────────────

    def test_patch_role_name_only_touches_project_role(self):
        first = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0022",
        )
        member_id = first.json()["member_id"]
        second = self.create_role(
            "prj_beta",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0023",
        )
        other_member_id = second.json()["member_id"]

        renamed = self.patch_role("prj_alpha", member_id, {"role_name": "后端"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["role_name"], "后端")
        with self.session() as session:
            member = session.get(Member, member_id)
            self.assertEqual(member.display_name, "dev")
        # 其它项目角色不受影响。
        self.assertEqual(
            self.role_entry(other_member_id, "prj_beta")["role_name"], "dev"
        )

        # 项目内重名 → 409。
        third = self.create_role(
            "prj_alpha",
            role_name="ops",
            choice_id=self.choice_id,
            operation_key="op-key-0024",
        )
        conflict = self.patch_role(
            "prj_alpha", third.json()["member_id"], {"role_name": "后端"}
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "role_name_conflict")
        invalid = self.patch_role("prj_alpha", member_id, {"role_name": "  "})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["detail"], "role_name_invalid")
        unknown = self.patch_role(
            "prj_alpha", member_id, {"decision_tier": "decision"}
        )
        self.assertEqual(unknown.status_code, 422)

    def test_patch_description_round_trip_and_clear(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0025",
            role_description="初版说明",
        )
        member_id = created.json()["member_id"]
        updated = self.patch_role(
            "prj_alpha", member_id, {"role_description": "第二版\n说明"}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["role_description"], "第二版\n说明")
        cleared = self.patch_role("prj_alpha", member_id, {"role_description": None})
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()["role_description"])
        self.assertEqual(self.description_rows(), [])

    def test_review_exempt_is_human_only_and_persisted(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0026",
        )
        member_id = created.json()["member_id"]
        self.assertEqual(self.policy_rows(), [])

        granted = self.patch_role("prj_alpha", member_id, {"review_exempt": True})
        self.assertEqual(granted.status_code, 200)
        policies = self.policy_rows()
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0].review_exempt, 1)
        self.assertEqual(policies[0].source, "human_grant")
        self.assertEqual(policies[0].granted_by, "human:bobo")

        # agent 不能自授/自撤。
        self.assertEqual(
            self.patch_role(
                "prj_alpha", member_id, {"review_exempt": True}, key="worker-key"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.patch_role(
                "prj_alpha", member_id, {"role_name": "x"}, key="worker-key"
            ).status_code,
            403,
        )

        revoked = self.patch_role("prj_alpha", member_id, {"review_exempt": False})
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(self.policy_rows()[0].review_exempt, 0)

    def test_patch_unknown_role_is_404(self):
        self.assertEqual(
            self.patch_role("prj_alpha", "agent:ghost", {"role_name": "x"}).status_code,
            404,
        )

    # ── 多角色隔离 / 任务摘要 ────────────────────────────────────────

    def test_two_roles_same_model_are_isolated(self):
        first = self.create_role(
            "prj_alpha",
            role_name="dev-a",
            choice_id=self.choice_id,
            operation_key="op-key-0027",
        )
        second = self.create_role(
            "prj_alpha",
            role_name="dev-b",
            choice_id=self.choice_id,
            operation_key="op-key-0028",
        )
        self.assertNotEqual(first.json()["member_id"], second.json()["member_id"])
        self.assertNotEqual(first.json()["api_key"], second.json()["api_key"])
        self.patch_role(
            "prj_alpha", second.json()["member_id"], {"review_exempt": True}
        )
        first_entry = self.role_entry(first.json()["member_id"])
        second_entry = self.role_entry(second.json()["member_id"])
        self.assertEqual(first_entry["role_name"], "dev-a")
        self.assertEqual(second_entry["role_name"], "dev-b")
        self.assertEqual(
            first_entry["model"]["choice_id"], second_entry["model"]["choice_id"]
        )
        with self.session() as session:
            self.assertEqual(
                session.get(
                    ProjectRolePolicy, ("prj_alpha", second.json()["member_id"])
                ).review_exempt,
                1,
            )
            self.assertIsNone(
                session.get(
                    ProjectRolePolicy, ("prj_alpha", first.json()["member_id"])
                )
            )

    def test_role_tasks_returns_only_nonterminal_summaries(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0029",
        )
        member_id = created.json()["member_id"]
        self.assertEqual(self.get_role_tasks("prj_alpha", member_id).json(), [])

        task = self.create_task("prj_alpha", member_id)
        self.assertEqual(task.status_code, 201)
        task_id = task.json()["id"]
        listed = self.get_role_tasks("prj_alpha", member_id)
        self.assertEqual([row["id"] for row in listed.json()], [task_id])
        self.assertEqual(
            set(listed.json()[0]),
            {
                "id",
                "title",
                "status",
                "workflow_status",
                "target_member_id",
                "created_by",
                "created_at",
            },
        )

        with self.session() as session:
            from server.models import AgentTask

            row = session.get(AgentTask, task_id)
            row.status = "succeeded"
            session.add(row)
            session.commit()
        self.assertEqual(self.get_role_tasks("prj_alpha", member_id).json(), [])

    def test_role_tasks_requires_existing_role_and_project(self):
        self.assertEqual(
            self.get_role_tasks("prj_ghost", "agent:x").status_code, 404
        )
        self.assertEqual(
            self.get_role_tasks("prj_alpha", "agent:ghost").status_code, 404
        )

    def test_role_endpoints_are_readable_by_agents(self):
        created = self.create_role(
            "prj_alpha",
            role_name="dev",
            choice_id=self.choice_id,
            operation_key="op-key-0030",
        )
        self.assertEqual(self.get_roles(key="worker-key").status_code, 200)
        self.assertEqual(
            self.get_role_tasks(
                "prj_alpha", created.json()["member_id"], key="worker-key"
            ).status_code,
            200,
        )


class LegacyAttachChoiceSourceTests(RoleApiTestCase):
    """补录映射的投影口径（259）。

    ``GET roles`` 的 ``choice_id`` 只信**显式操作映射**并与**当前绑定**六维精确相等：
    补录映射存在且对得上 → ``legacy_attach``；存在但对不上 → ``legacy_attach_mismatch``
    且 ``choice_id=null``；创建与补录两类映射并存 → 冲突失配，不任选一条放行。这里直接
    写入存储事实（不经过补录接口），单独核验投影读取路径。
    """

    def setUp(self):
        super().setUp()
        self.choice_id = self.seed_runner_and_choice()
        self.register_project("prj_alpha")
        self.sync_roster(
            "prj_alpha",
            [{"member_id": "agent:worker"}, {"member_id": "agent:other"}],
        )
        with self.session() as session:
            for member_id in ("agent:worker", "agent:other"):
                session.add(
                    ProjectRole(
                        project_id="prj_alpha",
                        member_id=member_id,
                        role_name=f"role-{member_id.split(':')[1]}",
                        origin="imported",
                        identity_exclusive=0,
                        credential_version=1,
                        created_by="human:bobo",
                    )
                )
                session.add(
                    RoleLegacyAttachOperation(
                        operation_key=f"attach-projection-{member_id.split(':')[1]}",
                        request_fingerprint="a" * 64,
                        project_id="prj_alpha",
                        member_id=member_id,
                        runner_id=RUNNER_ID,
                        choice_id=self.choice_id,
                        derived_role_name=f"role-{member_id.split(':')[1]}",
                        committed_at=datetime.now(timezone.utc),
                        created_by="human:bobo",
                    )
                )
            # 只给 agent:worker 一条与选择六维完全一致的绑定。
            session.add(
                ProjectRoleBinding(
                    project_id="prj_alpha",
                    member_id="agent:worker",
                    runner_id=RUNNER_ID,
                    model_source="builtin",
                    provider_id="managed:deepseek",
                    connection_ref="native-deepseek-managed-login",
                    model_id="deepseek-flash",
                    model_alias="deepseek-flash",
                    updated_by="human:bobo",
                )
            )
            session.commit()

    def _row(self, member_id: str) -> dict:
        rows = {row["member_id"]: row for row in self.get_roles().json()}
        return rows[member_id]

    def test_explicit_mapping_with_matching_binding_is_legacy_attach(self):
        row = self._row("agent:worker")
        self.assertEqual(row["identity"], "imported")
        self.assertFalse(row["archived"])
        self.assertEqual(row["model"]["choice_source"], CHOICE_SOURCE_LEGACY_ATTACH)
        self.assertEqual(row["model"]["choice_id"], self.choice_id)
        self.assertFalse(row["model"]["choice_binding_mismatch"])

    def test_mapping_without_binding_is_mismatch_not_guessed(self):
        row = self._row("agent:other")
        self.assertIsNone(row["model"]["choice_id"])
        self.assertEqual(
            row["model"]["choice_source"], CHOICE_SOURCE_LEGACY_ATTACH_MISMATCH
        )
        self.assertTrue(row["model"]["choice_binding_mismatch"])
        self.assertEqual(row["binding_state"], "unconfigured")

    def test_dual_mapping_conflict_never_picks_one_side(self):
        with self.session() as session:
            session.add(
                RoleCreationOperation(
                    operation_key="dual-mapping-projection-0001",
                    request_fingerprint="d" * 64,
                    project_id="prj_alpha",
                    requested_role_name="role-worker",
                    runner_id=RUNNER_ID,
                    choice_id=self.choice_id,
                    member_id="agent:worker",
                    committed_at=datetime.now(timezone.utc),
                    created_by="human:bobo",
                )
            )
            session.commit()
        row = self._row("agent:worker")
        self.assertIsNone(row["model"]["choice_id"])
        self.assertEqual(
            row["model"]["choice_source"], CHOICE_SOURCE_LEGACY_ATTACH_MISMATCH
        )
        self.assertTrue(row["model"]["choice_binding_mismatch"])

    def test_existing_sources_are_unchanged_without_mapping(self):
        # 未补录的老名册成员（无角色行、无映射）保持 legacy / legacy_manual。
        self.add_member("agent:plain", api_key="plain-key", display_name="Plain")
        self.sync_roster(
            "prj_alpha",
            [
                {"member_id": "agent:worker"},
                {"member_id": "agent:other"},
                {"member_id": "agent:plain"},
            ],
        )
        plain = self._row("agent:plain")
        self.assertEqual(plain["identity"], "legacy")
        self.assertEqual(plain["origin"], "imported")
        self.assertEqual(plain["model"]["choice_source"], CHOICE_SOURCE_LEGACY_MANUAL)
        self.assertIsNone(plain["model"]["choice_id"])
        # 来源字面量是公开合同的一部分（宿主按同一口径准入）。
        self.assertEqual(CHOICE_SOURCE_CREATION_OPERATION, "creation_operation")
        self.assertEqual(CHOICE_SOURCE_LEGACY_ATTACH, "legacy_attach")
        self.assertEqual(
            CHOICE_SOURCE_LEGACY_ATTACH_MISMATCH, "legacy_attach_mismatch"
        )
        self.assertEqual(CHOICE_SOURCE_LEGACY_MANUAL, "legacy_manual")


if __name__ == "__main__":
    unittest.main()
