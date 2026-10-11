# -*- coding: utf-8 -*-
"""R1-2 定向补正（TALK #219）：F1–F8 的闭合证据。

覆盖范围
--------
- F1/F3：真实临时 TestClient API + 真实 ``run_provision`` 端到端 —— 本地副作用前捕获作业
  代际、凭据轮换后迟到回报被拒、重复 apply 幂等 no-op、部分失败按步骤恢复；
- F2：真实双连接锁顺序 —— 引用守卫在 ``BEGIN IMMEDIATE`` 物理写事务内，并发注销/离册零脏写；
- F4：前置检查严格化 —— 缺三档/不可读/角色响应失败/缺成员/非 bound/来源或指纹不符全部失败；
- F5：有所有权的锁 —— 真实子进程并发、活锁不被年龄抢占、旧 owner 不能删新锁、同档不同 Key 根串行；
- F6：Windows Key 文件真实 ACL —— 创建即私有、回读核验、权限失败绝不按成功上报；
- F7：接口弃用声明 —— 公开 JSON Schema / OpenAPI / MCP 说明可被消费者读取，旧值兼容；
- F8：根/祖先 junction 与跨角色档案路径一律拒绝。

全部用例使用隔离临时库/隔离文件树与假 Key，不触网、不访问真实 Key、不启动真实服务。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(ROOT), str(ROOT / "scripts")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import role_provision as rp  # noqa: E402
from server.models import ProjectAgent, ProjectRole, RoleProvisionJob  # noqa: E402
from tests.test_project_roles import RoleApiTestCase  # noqa: E402
from tests.test_role_provision import (  # noqa: E402
    BASE_URL,
    BINDING_PATH,
    MEMBER_ID,
    OPERATION_KEY,
    PROJECT_ID,
    ROLES_PATH,
    ROSTER_PATH,
    FakeTransport,
    RoleProvisionTestCase,
    _binding_out,
    _provision_job,
    _roles_item,
    _roster_row,
    happy_transport,
)

OPERATOR_KEY = "bobo-key"
PROJECT = "prj_rework"


def _transport(
    *,
    me_status: int = 200,
    me_id: str = MEMBER_ID,
    roster: object = None,
    roles: object = None,
    roles_status: int = 200,
    binding: object = None,
) -> FakeTransport:
    """可控的假传输：每个路由只注册一次，便于构造 F4 的失败反例。"""
    transport = FakeTransport()
    transport.add_path(
        "GET", rp._me_path(), rp.HttpResponse(me_status, {"id": me_id, "kind": "agent"})
    )
    transport.add_path(
        "GET",
        ROSTER_PATH,
        rp.HttpResponse(200, [_roster_row()] if roster is None else roster),
    )
    transport.add_path(
        "GET",
        ROLES_PATH,
        rp.HttpResponse(roles_status, [_roles_item()] if roles is None else roles),
    )
    transport.add_path(
        "GET",
        BINDING_PATH,
        rp.HttpResponse(200, _binding_out() if binding is None else binding),
    )
    transport.add_path("GET", rp._provision_path(PROJECT_ID, MEMBER_ID), rp.HttpResponse(200, _provision_job()))
    transport.add_path(
        "POST", rp._provision_path(PROJECT_ID, MEMBER_ID) + "/ack", rp.HttpResponse(200, _provision_job())
    )
    return transport


def _roles_payload(*, binding_state="bound", choice_source="creation_operation",
                   choice_id="rmc_canary", choice_mismatch=False,
                   runner_id="runner-canary", model_id="model-canary",
                   model_alias="alias-canary"):
    return [
        {
            "member_id": MEMBER_ID,
            "binding_state": binding_state,
            "runner": {"runner_id": runner_id},
            "model": {
                "model_id": model_id,
                "model_alias": model_alias,
                "choice_id": choice_id,
                "choice_source": choice_source,
                "choice_binding_mismatch": choice_mismatch,
            },
        }
    ]


def _provision_path(project_id: str, member_id: str) -> str:
    return rp._provision_path(project_id, member_id)


class _ClientTransport:
    """把 ``run_provision`` 的 HTTP 边界接到进程内 ``TestClient``（真实 API 端到端）。

    ``hook`` 在**请求发出前**调用，``after_hook`` 在拿到响应后、返回给脚本前调用
    （用于复现「本地检查完成之后、回报之前」发生的并发状态变化）。
    """

    def __init__(self, client, hook=None, after_hook=None) -> None:
        self.client = client
        self.hook = hook
        self.after_hook = after_hook
        self.events: list[dict] = []

    def request_json(self, method, url, *, api_key=None, body=None, timeout=None):
        parts = urlsplit(url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        if self.hook is not None:
            self.hook(self, method, path, api_key, body)
        response = self.client.request(
            method,
            path,
            headers={"X-API-Key": api_key} if api_key else {},
            json=body,
        )
        self.events.append(
            {
                "method": method,
                "path": path,
                "status": response.status_code,
                "ack_body": body if path.endswith("/ack") else None,
            }
        )
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001 - 无 body 的响应
            payload = None
        if self.after_hook is not None:
            self.after_hook(self, method, path, api_key, body, response.status_code)
        return rp.HttpResponse(response.status_code, payload)


class _Harness(RoleApiTestCase):
    def test_placeholder(self) -> None:  # pragma: no cover - 仅用于借用夹具
        pass


class _ApiCase(unittest.TestCase):
    """给 API 端到端用例提供 setUp/tearDown 的临时隔离库与项目/角色。"""

    def setUp(self) -> None:
        self.h = _Harness("test_placeholder")
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.h.register_project(PROJECT)
        self.choice_id = self.h.seed_runner_and_choice()
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-rework-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))

    def make_role(self, operation_key: str) -> dict:
        response = self.h.create_role(
            PROJECT,
            role_name=f"role-{operation_key}",
            choice_id=self.choice_id,
            operation_key=operation_key,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def role_row(self, member_id: str) -> ProjectRole:
        with self.h.session() as session:
            return session.get(ProjectRole, (PROJECT, member_id))

    def job_row(self, operation_key: str):
        with self.h.session() as session:
            return session.get(RoleProvisionJob, operation_key)

    def roster_paths_body(self, operation_key: str, member_id: str) -> dict:
        return {
            "operation_key": operation_key,
            **rp._roster_relative_paths(member_id),
        }

    def run_script(self, client, role: dict, operation_key: str, **overrides):
        project_root = overrides.pop("project_root", None) or (self._tmp / "project")
        project_root.mkdir(parents=True, exist_ok=True)
        key_root = overrides.pop("key_root", None) or (self._tmp / "secrets")
        transport = overrides.pop("transport", None) or _ClientTransport(client)
        environ = overrides.pop(
            "environ",
            {
                "TALK_ROLE_API_KEY": role["api_key"],
                "TALK_OPERATOR_API_KEY": OPERATOR_KEY,
            },
        )
        document, code = rp.run_provision(
            project_id=PROJECT,
            member_id=role["member_id"],
            operation_key=operation_key,
            project_root=project_root,
            key_root=key_root,
            repo_root=project_root,
            base_url="http://testserver",
            apply=True,
            transport=transport,
            environ=environ,
            **overrides,
        )
        return document, code, project_root, key_root, transport


# ══════════════════════════════════════════════════════════════════════
# F1 + F3：真实 API 端到端
# ══════════════════════════════════════════════════════════════════════


class GenerationEndToEndTests(_ApiCase):
    def test_rotation_between_local_checks_and_ack_is_rejected(self):
        operation_key = "rework-stale-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        provision_path = _provision_path(PROJECT, member_id)
        rotated: list[dict] = []

        with self.h.make_client() as client:
            def after_hook(transport, method, path, api_key, body, status):
                # 本地三步都已完成（最后一个本地读取是 binding GET）时，偷偷轮换凭据并续跑
                # 作业：这正是旧实现把「旧结果」套到「新 attempt」的窗口。
                if rotated or method != "GET" or not path.endswith("/binding"):
                    return
                response = client.post(
                    f"/api/projects/{PROJECT}/roles/{quote(member_id, safe='')}/rotate-key",
                    headers={"X-API-Key": OPERATOR_KEY},
                )
                self.assertEqual(response.status_code, 200, response.text)
                resumed = client.post(
                    provision_path,
                    headers={"X-API-Key": OPERATOR_KEY},
                    json={"operation_key": operation_key, "resume": True},
                )
                self.assertEqual(resumed.status_code, 200, resumed.text)
                rotated.append(
                    {
                        "credential_version": response.json()["credential_version"],
                        "resume_revision": resumed.json()["revision"],
                        "resume_attempts": {
                            step: value["attempts"]
                            for step, value in resumed.json()["steps"].items()
                        },
                    }
                )

            document, code, _root, key_root, transport = self.run_script(
                client, role, operation_key, transport=_ClientTransport(client, None, after_hook)
            )

            self.assertTrue(rotated, "钩子未触发：绑定读取未发生")
            self.assertEqual(rotated[0]["credential_version"], 2)

            # 本地三步都算出成功（这正是旧实现的“旧结果”），但服务端必须拒绝这套代际。
            self.assertEqual(document["steps"]["preflight"]["state"], "succeeded")
            self.assertEqual(document["conclusion"], "partial")
            self.assertNotEqual(document["conclusion"], "applied")
            self.assertEqual(document["ack"]["reason"], "ack_stale")
            self.assertEqual(document["error_code"], "ack_stale")
            self.assertEqual(document["ack"]["results"][0]["http_status"], 409)
            self.assertFalse(document["ack"]["sent"])

            job = client.get(
                provision_path,
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            ).json()
            self.assertNotEqual(job["status"], "succeeded")
            self.assertTrue(all(item["state"] == "pending" for item in job["steps"].values()))
            self.assertEqual(job["revision"], rotated[0]["resume_revision"])

            # 落盘的旧 Key 已失效；脚本没有自动再次轮换，也没有重发旧 Key。
            stored_key = rp._read_key_file(rp.key_file_path(key_root, member_id))
            self.assertIsNotNone(stored_key)
            self.assertEqual(
                client.get(
                    "/api/members/me", headers={"X-API-Key": stored_key}
                ).status_code,
                401,
            )
            self.assertEqual(self.role_row(member_id).credential_version, 2)

    def test_recovery_after_rotation_with_new_key_and_resume(self):
        operation_key = "rework-stale-0002"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        provision_path = _provision_path(PROJECT, member_id)

        with self.h.make_client() as client:
            # 第一次：正常成功（捕获代际 → 本地三步 → ACK）。
            first, _code, project_root, _keys, _tr = self.run_script(client, role, operation_key)
            self.assertEqual(first["conclusion"], "applied")
            self.assertTrue(first["ack"]["sent"])

            # 人类轮换凭据：旧 Key 与旧成功证明一起失效。
            rotated = client.post(
                f"/api/projects/{PROJECT}/roles/{quote(member_id, safe='')}/rotate-key",
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(rotated.status_code, 200, rotated.text)
            new_key = rotated.json()["api_key"]
            self.assertEqual(rotated.json()["credential_version"], 2)

            # 恢复：换一个全新 Key 根并提供新 Key；凭据相关步骤被服务端强制重开。
            fresh_key_root = self._tmp / "secrets-after-rotate"
            second, second_code, _pr, fresh_keys, _tr2 = self.run_script(
                client,
                role,
                operation_key,
                project_root=project_root,
                key_root=fresh_key_root,
                resume=True,
                environ={
                    "TALK_ROLE_API_KEY": new_key,
                    "TALK_OPERATOR_API_KEY": OPERATOR_KEY,
                },
            )
            self.assertEqual(second_code, 0, json.dumps(second, ensure_ascii=False))
            self.assertEqual(second["conclusion"], "applied")
            self.assertEqual(second["steps"]["key_file"]["state"], "succeeded")
            self.assertEqual(second["steps"]["preflight"]["state"], "succeeded")

            job = client.get(
                provision_path,
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            ).json()
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["credential_version"], 2)
            # profile 已成功过：定向续跑不重置它，attempts 不变。
            self.assertEqual(job["steps"]["profile"]["attempts"], 1)
            self.assertEqual(job["steps"]["key_file"]["attempts"], 2)
            self.assertEqual(job["steps"]["preflight"]["attempts"], 2)
            stored = rp._read_key_file(rp.key_file_path(fresh_keys, member_id))
            self.assertEqual(stored, new_key)

    def test_repeat_apply_after_success_is_noop(self):
        operation_key = "rework-repeat-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        provision_path = _provision_path(PROJECT, member_id)

        with self.h.make_client() as client:
            first, _code, project_root, key_root, _tr = self.run_script(
                client, role, operation_key
            )
            self.assertEqual(first["conclusion"], "applied")
            job_before = client.get(
                provision_path,
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            ).json()
            key_bytes = rp.key_file_path(key_root, member_id).read_bytes()
            profile_dir = project_root / ".talk" / "agents"
            profiles_before = {
                path.name: path.read_bytes() for path in profile_dir.rglob("*.md")
            }

            second, _sc, _pr, _kr, transport = self.run_script(
                client,
                role,
                operation_key,
                project_root=project_root,
                key_root=key_root,
            )
            self.assertEqual(second["conclusion"], "applied")
            self.assertEqual(second["ack"]["reason"], "not_required")
            self.assertEqual(second["ack"]["results"], [])
            self.assertFalse(second["ack"]["sent"])
            self.assertEqual(second["error_code"], None)
            # 不重建角色 / 不重发 Key / 不增加 attempt / 不新增 ACK。
            self.assertEqual(
                [
                    event
                    for event in transport.events
                    if event["method"] == "POST" and event["path"].endswith("/ack")
                ],
                [],
            )
            job_after = client.get(
                provision_path,
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            ).json()
            self.assertEqual(job_after, job_before)
            self.assertEqual(rp.key_file_path(key_root, member_id).read_bytes(), key_bytes)
            self.assertEqual(
                {path.name: path.read_bytes() for path in profile_dir.rglob("*.md")},
                profiles_before,
            )
            self.assertEqual(self.role_row(member_id).credential_version, 1)

    def test_partial_failure_then_resume_recovers_only_failed_steps(self):
        operation_key = "rework-partial-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        provision_path = _provision_path(PROJECT, member_id)

        with self.h.make_client() as client:
            # 第一次：没有 Key 来源 → key_file/preflight 失败，profile 成功。
            first, _fc, project_root, key_root, _tr = self.run_script(
                client,
                role,
                operation_key,
                environ={"TALK_OPERATOR_API_KEY": OPERATOR_KEY},
            )
            self.assertEqual(first["conclusion"], "partial")
            self.assertEqual(first["steps"]["profile"]["state"], "succeeded")
            self.assertEqual(first["steps"]["key_file"]["state"], "failed")
            self.assertEqual(first["steps"]["key_file"]["error_code"], "role_key_unknown")
            job_partial = client.get(
                provision_path,
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            ).json()
            self.assertEqual(job_partial["status"], "partial")
            self.assertEqual(job_partial["steps"]["profile"]["state"], "succeeded")
            self.assertEqual(job_partial["steps"]["key_file"]["state"], "failed")

            # 恢复：显式 --resume + 提供 Key。
            second, second_code, _pr, _kr, _tr2 = self.run_script(
                client,
                role,
                operation_key,
                project_root=project_root,
                key_root=key_root,
                resume=True,
            )
            self.assertEqual(second_code, 0, json.dumps(second, ensure_ascii=False))
            self.assertEqual(second["conclusion"], "applied")
            job_done = client.get(
                provision_path,
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            ).json()
            self.assertEqual(job_done["status"], "succeeded")
            self.assertEqual(job_done["steps"]["profile"]["attempts"], 1)
            self.assertEqual(job_done["steps"]["key_file"]["attempts"], 2)
            self.assertEqual(job_done["steps"]["preflight"]["attempts"], 2)
            stored = rp._read_key_file(rp.key_file_path(key_root, member_id))
            self.assertEqual(
                client.get(
                    "/api/members/me", headers={"X-API-Key": stored}
                ).status_code,
                200,
            )

    def test_removed_roster_before_resume_is_refused(self):
        """并发离册：作业存在但名册行已删 → 续跑必须被拒绝，且不产生任何写入。"""
        operation_key = "rework-roster-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        provision_path = _provision_path(PROJECT, member_id)

        with self.h.make_client() as client:
            job = client.post(
                provision_path,
                headers={"X-API-Key": OPERATOR_KEY},
                json={"operation_key": operation_key},
            ).json()
            with self.h.session() as session:
                session.delete(session.get(ProjectAgent, (PROJECT, member_id)))
                session.commit()
            resumed = client.post(
                provision_path,
                headers={"X-API-Key": OPERATOR_KEY},
                json={"operation_key": operation_key, "resume": True},
            )
            self.assertEqual(resumed.status_code, 409, resumed.text)
            self.assertEqual(resumed.json()["detail"], "provision_roster_missing")
            self.assertEqual(self.job_row(operation_key).revision, job["revision"])


class CrossRoleApiTests(_ApiCase):
    """F8：真实 API 上把 A 角色的三档路径登记给 B 角色必须被拒绝。"""

    def test_cross_role_roster_paths_refused_by_real_api(self):
        role_a = self.make_role("rework-cross-a-01")
        role_b = self.make_role("rework-cross-b-01")
        path_b = _provision_path(PROJECT, role_b["member_id"])
        with self.h.make_client() as client:
            response = client.post(
                path_b + "/roster-paths",
                headers={"X-API-Key": OPERATOR_KEY},
                json={
                    "operation_key": "rework-cross-b-01",
                    **rp._roster_relative_paths(role_a["member_id"]),
                },
            )
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(response.json()["detail"], "provision_roster_path_invalid")
            # 自己角色的路径仍然可以登记。
            own = client.post(
                path_b + "/roster-paths",
                headers={"X-API-Key": OPERATOR_KEY},
                json={
                    "operation_key": "rework-cross-b-01",
                    **rp._roster_relative_paths(role_b["member_id"]),
                },
            )
            self.assertEqual(own.status_code, 200, own.text)
        with self.h.session() as session:
            row_a = session.get(ProjectAgent, (PROJECT, role_a["member_id"]))
            row_b = session.get(ProjectAgent, (PROJECT, role_b["member_id"]))
            self.assertIsNone(row_a.identity_path)
            self.assertIsNone(row_a.soul_path)
            self.assertIsNone(row_a.user_path)
            self.assertEqual(
                row_b.identity_path,
                rp._roster_relative_paths(role_b["member_id"])["identity_path"],
            )


# ══════════════════════════════════════════════════════════════════════
# F2：写锁与可变引用
# ══════════════════════════════════════════════════════════════════════


class WriteLockConsistencyTests(RoleApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.register_project(PROJECT)
        self.choice_id = self.seed_runner_and_choice()

    def make_role(self, operation_key: str) -> dict:
        response = self.create_role(
            PROJECT,
            role_name=f"role-{operation_key}",
            choice_id=self.choice_id,
            operation_key=operation_key,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_delete_committed_before_write_guard_is_refused(self):
        """先提交注销，再调用写入入口：守卫读到的必须是物理最新事实（零脏写）。"""
        operation_key = "rework-guard-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        with self.make_client() as client:
            deleted = client.delete(f"/api/projects/{PROJECT}", headers={"X-API-Key": OPERATOR_KEY})
            self.assertEqual(deleted.status_code, 204, deleted.text)
            provision = client.post(
                _provision_path(PROJECT, member_id),
                headers={"X-API-Key": OPERATOR_KEY},
                json={"operation_key": operation_key},
            )
            self.assertEqual(provision.status_code, 404, provision.text)
            self.assertEqual(provision.json()["detail"], "project_not_found")
        with self.session() as session:
            self.assertIsNone(session.get(RoleProvisionJob, operation_key))
            # 角色行仍按 R1-1 语义保留（项目删除不级联），但**没有**产生任何作业写入。
            self.assertIsNotNone(session.get(ProjectRole, (PROJECT, member_id)))

    def test_guards_run_inside_physical_write_transaction(self):
        """补正 F2：三个写入入口的引用守卫都在 BEGIN IMMEDIATE 物理写事务内。"""
        import server.routes.projects as projects

        operation_key = "rework-guard-0002"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        observations: list[dict] = []
        real_guard = projects._require_provision_identity

        def observing_guard(project_id, target_member_id, key, session):
            real_guard(project_id, target_member_id, key, session)
            driver = session.connection().connection.driver_connection
            in_transaction = bool(getattr(driver, "in_transaction", False))
            blocked = None
            if in_transaction:
                other = sqlite3.connect(str(self.db_path), timeout=0)
                try:
                    other.execute("BEGIN IMMEDIATE")
                    blocked = False
                except sqlite3.OperationalError:
                    blocked = True
                finally:
                    other.close()
            observations.append(
                {"in_transaction": in_transaction, "other_writer_blocked": blocked}
            )

        with self.make_client() as client:
            with patch.object(
                projects, "_require_provision_identity", side_effect=observing_guard
            ):
                created = client.post(
                    _provision_path(PROJECT, member_id),
                    headers={"X-API-Key": OPERATOR_KEY},
                    json={"operation_key": operation_key},
                )
                self.assertEqual(created.status_code, 201, created.text)
                acked = client.post(
                    _provision_path(PROJECT, member_id) + "/ack",
                    headers={"X-API-Key": OPERATOR_KEY},
                    json={
                        "operation_key": operation_key,
                        "step": "profile",
                        "attempt": 1,
                        "revision": 1,
                        "credential_version": 1,
                        "state": "succeeded",
                        "error_code": None,
                    },
                )
                self.assertEqual(acked.status_code, 200, acked.text)
                paths = client.post(
                    _provision_path(PROJECT, member_id) + "/roster-paths",
                    headers={"X-API-Key": OPERATOR_KEY},
                    json={"operation_key": operation_key, **rp._roster_relative_paths(member_id)},
                )
                self.assertEqual(paths.status_code, 200, paths.text)

        self.assertEqual(len(observations), 3)
        for item in observations:
            self.assertTrue(item["in_transaction"], "守卫不在物理写事务内")
            self.assertTrue(item["other_writer_blocked"], "第二个写者未被写锁挡住")

    def test_roster_removed_before_roster_paths_is_refused_without_write(self):
        operation_key = "rework-guard-0003"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        with self.session() as session:
            session.delete(session.get(ProjectAgent, (PROJECT, member_id)))
            session.commit()
        with self.make_client() as client:
            response = client.post(
                _provision_path(PROJECT, member_id) + "/roster-paths",
                headers={"X-API-Key": OPERATOR_KEY},
                json={"operation_key": operation_key, **rp._roster_relative_paths(member_id)},
            )
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()["detail"], "provision_roster_missing")

    def test_disabled_member_before_ack_is_refused(self):
        from datetime import datetime, timezone

        from server.models import Member

        operation_key = "rework-guard-0004"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        with self.make_client() as client:
            created = client.post(
                _provision_path(PROJECT, member_id),
                headers={"X-API-Key": OPERATOR_KEY},
                json={"operation_key": operation_key},
            )
            self.assertEqual(created.status_code, 201)
            with self.session() as session:
                member = session.get(Member, member_id)
                member.disabled_at = datetime.now(timezone.utc)
                session.add(member)
                session.commit()
            acked = client.post(
                _provision_path(PROJECT, member_id) + "/ack",
                headers={"X-API-Key": OPERATOR_KEY},
                json={
                    "operation_key": operation_key,
                    "step": "profile",
                    "attempt": 1,
                    "revision": 1,
                    "credential_version": 1,
                    "state": "succeeded",
                    "error_code": None,
                },
            )
            self.assertEqual(acked.status_code, 409, acked.text)
            self.assertEqual(acked.json()["detail"], "provision_member_disabled")
        with self.session() as session:
            job = session.get(RoleProvisionJob, operation_key)
            self.assertEqual(job.revision, 1)
            self.assertEqual(job.steps["profile"]["state"], "pending")


# ══════════════════════════════════════════════════════════════════════
# F4：前置检查严格化
# ══════════════════════════════════════════════════════════════════════


class _ScriptHarness(RoleProvisionTestCase):
    """借用 ``RoleProvisionTestCase`` 夹具（不声明额外用例）。"""

    def test_noop(self) -> None:  # pragma: no cover - 仅用于实例化
        pass


class PreflightStrictnessTests(RoleProvisionTestCase):
    def _run_preflight(self, transport, *, seed: bool = True, seed_profiles: bool = True, **overrides):
        """直接调用 ``run_provision``；``seed*`` 控制是否补种 Key/身份档，便于构造缺失反例。"""
        if seed:
            self.key_root.mkdir(parents=True, exist_ok=True)
            if not self.key_file().is_file():
                rp._write_key_file(self.key_file(), "canary")
        if seed and seed_profiles:
            for path in rp.profile_target_paths(self.project_root, MEMBER_ID).values():
                if not path.is_file():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("# seeded\n", encoding="utf-8")
        return rp.run_provision(
            project_id=PROJECT_ID,
            member_id=overrides.pop("member_id", MEMBER_ID),
            operation_key=OPERATION_KEY,
            project_root=overrides.pop("project_root", self.project_root),
            key_root=overrides.pop("key_root", self.key_root),
            base_url=BASE_URL,
            apply=True,
            steps=overrides.pop("steps", "preflight"),
            transport=transport,
            environ=dict(overrides.pop("environ", {})),
            repo_root=self.repo,
            **overrides,
        )

    def test_local_profiles_missing_fails(self):
        transport = _transport()
        # 不补种身份档，也不自动补种 → preflight 必须失败。
        document, code = self._run_preflight(
            transport, seed=True, seed_profiles=False, environ=self.env_happy
        )
        self.assertEqual(code, 1)
        self.assertEqual(document["steps"]["preflight"]["state"], "failed")
        self.assertEqual(
            document["error_code"], "identity_mismatch", document["steps"]["preflight"]["detail"]
        )
        self.assertIn("profile_files=not_readable", document["steps"]["preflight"]["detail"])

    def test_local_profile_empty_fails(self):
        transport = _transport()
        self.key_root.mkdir(parents=True, exist_ok=True)
        rp._write_key_file(self.key_file(), "canary")
        for path in rp.profile_target_paths(self.project_root, MEMBER_ID).values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("   \n", encoding="utf-8")
        document, code = self._run_preflight(
            transport, seed=True, seed_profiles=False, environ=self.env_happy
        )
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")

    def test_roles_response_failure_fails(self):
        transport = _transport(roles=[], roles_status=500)
        document, code = self._run_preflight(transport, environ=self.env_happy)
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "http_error")

    def test_roles_missing_target_fails(self):
        transport = _transport(roles=[])
        document, code = self._run_preflight(transport, environ=self.env_happy)
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")

    def test_roles_binding_state_not_bound_fails(self):
        transport = _transport(roles=_roles_payload(binding_state="runner_retired"))
        document, code = self._run_preflight(transport, environ=self.env_happy)
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")
        self.assertIn("runner_retired", document["steps"]["preflight"]["detail"])

    def test_roles_choice_source_mismatch_fails(self):
        transport = _transport(
            roles=_roles_payload(
                choice_source="legacy_manual", choice_id=None, choice_mismatch=True
            )
        )
        document, code = self._run_preflight(transport, environ=self.env_happy)
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")
        self.assertIn("choice_source=legacy_manual", document["steps"]["preflight"]["detail"])

    def test_binding_projection_not_bound_fails(self):
        binding = _binding_out(binding_state="runner_retired")
        transport = _transport(binding=binding)
        document, code = self._run_preflight(transport, environ=self.env_happy)
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")

    def test_binding_fingerprint_missing_fails(self):
        transport = _transport(binding=_binding_out(binding_fingerprint=None))
        document, code = self._run_preflight(transport, environ=self.env_happy)
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")
        self.assertIn("binding_fingerprint", document["steps"]["preflight"]["detail"])

    def test_binding_alias_or_runner_mismatch_fails(self):
        document, code = self._run_preflight(
            _transport(binding=_binding_out(model_alias="alias-other")),
            environ=self.env_happy,
        )
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")

        document, code = self._run_preflight(
            _transport(binding=_binding_out(runner_id="runner-other")),
            environ=self.env_happy,
        )
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")

    def test_binding_connection_ref_missing_fails(self):
        binding = _binding_out()
        binding["binding"]["connection_ref"] = None
        document, code = self._run_preflight(
            _transport(binding=binding), environ=self.env_happy
        )
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")
        self.assertIn("connection_ref", document["steps"]["preflight"]["detail"])


# ══════════════════════════════════════════════════════════════════════
# F5：有所有权的锁
# ══════════════════════════════════════════════════════════════════════


class LockOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-lock-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))
        self.lock_path = self._tmp / "target.lock"

    def _spawn_lock_holder(self) -> subprocess.Popen:
        code = (
            "import sys, time\n"
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r})\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "import role_provision as rp\n"
            f"handle = rp.acquire_lock(__import__('pathlib').Path({str(self.lock_path)!r}))\n"
            f"open({str(self._tmp / 'child.ready')!r}, 'w', encoding='utf-8').write(handle['token'])\n"
            "time.sleep(120)\n"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(ROOT),
        )
        self.addCleanup(lambda: (child.poll() is None and child.kill(), child.wait()))
        deadline = time.time() + 30
        marker = self._tmp / "child.ready"
        while time.time() < deadline and not marker.exists():
            time.sleep(0.1)
        self.assertTrue(marker.exists(), "子进程未能拿到锁")
        return child

    def test_real_process_concurrency_is_mutually_exclusive(self):
        child = self._spawn_lock_holder()
        self.assertTrue(rp._process_is_alive(child.pid))
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.acquire_lock(self.lock_path, stale_seconds=0)
        self.assertEqual(ctx.exception.code, "provision_lock_busy")

        # 旧 owner 仍存活：即便把 mtime 改成很老，也不能按年龄抢占。
        old = 1_000_000.0
        os.utime(self.lock_path, (old, old))
        with self.assertRaises(rp.ProvisionError) as ctx2:
            rp.acquire_lock(self.lock_path, stale_seconds=0)
        self.assertEqual(ctx2.exception.code, "provision_lock_busy")

    def test_dead_owner_lock_is_reclaimable(self):
        child = self._spawn_lock_holder()
        child.kill()
        child.wait(timeout=30)
        deadline = time.time() + 15
        while time.time() < deadline and rp._process_is_alive(child.pid) is not False:
            time.sleep(0.1)
        self.assertIs(rp._process_is_alive(child.pid), False)
        old = 1_000_000.0
        os.utime(self.lock_path, (old, old))
        handle = rp.acquire_lock(self.lock_path, stale_seconds=900)
        self.assertTrue(handle["reclaimed"])
        self.assertTrue(rp.release_lock(self.lock_path, handle))

    def test_release_never_removes_another_generation(self):
        first = rp.acquire_lock(self.lock_path)
        record = json.loads(self.lock_path.read_text(encoding="utf-8"))
        self.assertEqual(record["token"], first["token"])
        # 模拟被回收后第二 owner 建的新锁。
        self.lock_path.write_text(
            json.dumps(
                {
                    "schema": rp.LOCK_SCHEMA,
                    "token": "second-generation",
                    "pid": 0x7FFFFFF0,
                    "started_at": "2020-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        self.assertFalse(rp.release_lock(self.lock_path, first))
        self.assertTrue(self.lock_path.exists())
        self.assertEqual(
            json.loads(self.lock_path.read_text(encoding="utf-8"))["token"],
            "second-generation",
        )
        self.assertEqual(rp.acquire_lock.__doc__ is not None, True)


# ══════════════════════════════════════════════════════════════════════
# F6：Windows Key 文件真实 ACL
# ══════════════════════════════════════════════════════════════════════


class WindowsAclTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-acl-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))

    @unittest.skipUnless(os.name == "nt", "Windows ACL 用例")
    def test_new_key_file_has_verified_private_acl(self):
        key_path = self._tmp / "agent.key"
        description = rp._write_key_file(key_path, "canary-key-1234567890")
        self.assertIn("windows_acl_verified", description)
        ok, detail = rp._windows_verify_private_acl(key_path)
        self.assertTrue(ok, detail)
        allowed = set(rp._windows_acl_sids())
        seen = set(detail.replace("acl=", "").split(","))
        self.assertEqual(seen, allowed)
        self.assertIn(rp._windows_current_user_sid(), seen)
        # 真实权限矩阵：不允许的宽主体（Authenticated Users / Users）不在允许集合里。
        self.assertNotIn("S-1-5-11", seen)
        self.assertNotIn("S-1-5-32-545", seen)
        # 文件仍可被本进程读取（私有 ACL 没有把当前用户自己挡在外面）。
        self.assertEqual(key_path.read_text(encoding="utf-8").strip(), "canary-key-1234567890")

    @unittest.skipUnless(os.name == "nt", "Windows ACL 用例")
    def test_inherited_wide_acl_fails_verification(self):
        key_path = self._tmp / "wide.key"
        key_path.write_text("canary\n", encoding="utf-8")
        ok, detail = rp._windows_verify_private_acl(key_path)
        self.assertFalse(ok, detail)
        self.assertNotEqual(detail, "acl=")

    @unittest.skipUnless(os.name == "nt", "Windows ACL 用例")
    def test_permission_failure_is_not_reported_as_success(self):
        key_path = self._tmp / "fail.key"
        with patch.object(
            rp, "_windows_create_file_with_private_acl", side_effect=rp._WindowsAclError("probe")
        ):
            with self.assertRaises(rp.ProvisionError) as ctx:
                rp._write_key_file(key_path, "canary")
        self.assertEqual(ctx.exception.code, "key_permissions_failed")
        self.assertFalse(key_path.exists())

    def test_key_step_reports_failure_when_acl_cannot_be_enforced(self):
        case = _ScriptHarness("test_noop")
        case.setUp()
        try:
            with patch.object(
                rp,
                "_enforce_private_permissions",
                side_effect=rp.ProvisionError("key_permissions_failed", "probe"),
            ):
                transport = happy_transport()
                document, code = case.run_script(
                    transport, env=case.env_happy, steps="key_file"
                )
            self.assertEqual(code, 1)
            self.assertEqual(document["steps"]["key_file"]["state"], "failed")
            self.assertEqual(document["error_code"], "key_permissions_failed")
        finally:
            case.tearDown()


# ══════════════════════════════════════════════════════════════════════
# F7：公开弃用声明
# ══════════════════════════════════════════════════════════════════════


class SchemaDeprecationTests(unittest.TestCase):
    def test_public_json_schema_marks_decision_tier_deprecated(self):
        from server.models import (
            GroupMemberOut,
            GroupMemberUpdate,
            ProjectAgentEntry,
            ProjectAgentOut,
        )

        for model in (GroupMemberOut, GroupMemberUpdate, ProjectAgentEntry, ProjectAgentOut):
            with self.subTest(model=model.__name__):
                prop = model.model_json_schema()["properties"]["decision_tier"]
                self.assertIs(prop.get("deprecated"), True, prop)

    def test_openapi_documents_deprecation(self):
        import server.main as main
        from fastapi.testclient import TestClient

        with TestClient(main.app) as client:
            schema = client.get("/openapi.json").json()
        components = schema["components"]["schemas"]
        for name in ("GroupMemberOut", "GroupMemberUpdate", "ProjectAgentEntry", "ProjectAgentOut"):
            prop = components[name]["properties"]["decision_tier"]
            self.assertIs(prop.get("deprecated"), True, (name, prop))

    def test_mcp_public_description_declares_deprecation(self):
        from bridges import talk_task_tools as tools

        schema = next(
            item for item in tools.TOOL_SCHEMAS if item["name"] == "talk_list_agents"
        )
        description = schema["description"]
        self.assertIn("decision_tier", description)
        self.assertIn("已弃用", description)
        self.assertIn(tools.DECISION_TIER_DEPRECATION_NOTE, description)
        self.assertIn("decision_tier_deprecated=true", description)

    def test_mcp_agent_entries_expose_machine_readable_flag(self):
        from bridges import talk_task_tools as tools

        canned = {
            "GET /api/projects/prj": {"development_requirements": None},
            "GET /api/projects/prj/agents": [
                {
                    "member_id": "agent:x",
                    "display_name": "X",
                    "business_role": "dev",
                    "decision_tier": "execution",
                    "capability_summary": [],
                    "availability": "idle",
                    "instances": [],
                    "binding": None,
                    "binding_state": None,
                }
            ],
            "GET /api/members": [{"id": "agent:x", "kind": "agent", "disabled_at": None}],
            "GET /api/members/me": {"id": "human:bobo", "kind": "human"},
        }

        def fake_request(method, path, **kwargs):
            return canned[f"{method} {path}"]

        with patch.object(tools, "_api_request", side_effect=fake_request), patch.object(
            tools, "_project_id", return_value="prj"
        ):
            result = tools.list_agents(project_id="prj")
        entry = result["agents"][0]
        self.assertEqual(entry["decision_tier"], "execution")
        self.assertIs(entry["decision_tier_deprecated"], True)

    def test_legacy_values_and_columns_still_compatible(self):
        from sqlalchemy import text
        from sqlmodel import Session, SQLModel, create_engine

        from server.models import GroupMemberUpdate, ProjectAgentEntry

        self.assertEqual(
            GroupMemberUpdate(role="member", decision_tier="decision").decision_tier,
            "decision",
        )
        entry = ProjectAgentEntry(member_id="agent:x", decision_tier="execution")
        self.assertEqual(entry.decision_tier, "execution")
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            columns = {
                row[1]
                for row in session.exec(
                    text("PRAGMA table_info(project_agents)")
                ).fetchall()
            }
            job_columns = {
                row[1]
                for row in session.exec(
                    text("PRAGMA table_info(role_provision_jobs)")
                ).fetchall()
            }
        self.assertIn("decision_tier", columns)
        self.assertIn("credential_version", job_columns)


# ══════════════════════════════════════════════════════════════════════
# F8：根/祖先 junction 与跨角色路径
# ══════════════════════════════════════════════════════════════════════


def _make_junction(link: Path, target: Path) -> bool:
    if os.name != "nt":
        return False
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0 and link.exists()


class PathIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-path-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))

    def test_project_root_junction_is_refused(self):
        real = self._tmp / "real-project"
        real.mkdir()
        link = self._tmp / "alias-project"
        if not _make_junction(link, real):
            self.skipTest("本机无法创建 junction")
        self.assertTrue(rp._is_reparse_point(link))
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.profile_target_paths(link, MEMBER_ID)
        self.assertEqual(ctx.exception.code, "symlink_refused")

        document, code = rp.run_provision(
            project_id=PROJECT_ID,
            member_id=MEMBER_ID,
            operation_key=OPERATION_KEY,
            project_root=link,
            key_root=self._tmp / "keys",
            repo_root=self._tmp / "real-project",
            apply=True,
            steps="profile",
            transport=happy_transport(),
            environ={},
        )
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "symlink_refused")
        self.assertEqual(list(real.rglob("*")), [])
        self.assertEqual(list(link.rglob("*")), [])

    def test_ancestor_junction_of_root_is_refused(self):
        real = self._tmp / "real"
        (real / "nested").mkdir(parents=True)
        link = self._tmp / "ancestor"
        if not _make_junction(link, real):
            self.skipTest("本机无法创建 junction")
        nested_root = link / "nested"
        self.assertFalse(rp._is_reparse_point(nested_root))
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.profile_target_paths(nested_root, MEMBER_ID)
        self.assertEqual(ctx.exception.code, "symlink_refused")
        self.assertEqual(list(real.rglob("*")), [d for d in [real / "nested"]])

    def test_subpath_junction_inside_project_is_refused(self):
        """目标路径中间段是 junction（``.talk/agents`` 指向外部）也必须拒绝。"""
        project = self._tmp / "plain-project"
        (project / ".talk").mkdir(parents=True)
        outside = self._tmp / "outside-agents"
        outside.mkdir()
        if not _make_junction(project / ".talk" / "agents", outside):
            self.skipTest("本机无法创建 junction")
        self.assertTrue(rp._is_reparse_point(project / ".talk" / "agents"))
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.profile_target_paths(project, MEMBER_ID)
        self.assertEqual(ctx.exception.code, "symlink_refused")
        self.assertEqual(list(outside.rglob("*")), [])
        document, code = rp.run_provision(
            project_id=PROJECT_ID,
            member_id=MEMBER_ID,
            operation_key=OPERATION_KEY,
            project_root=project,
            key_root=self._tmp / "keys-sub",
            repo_root=project,
            apply=True,
            steps="profile",
            transport=happy_transport(),
            environ={},
        )
        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "symlink_refused")
        self.assertEqual(list(outside.rglob("*")), [])

    def test_key_root_junction_is_refused(self):
        real = self._tmp / "real-keys"
        real.mkdir()
        link = self._tmp / "alias-keys"
        if not _make_junction(link, real):
            self.skipTest("本机无法创建 junction")
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.key_file_path(link, MEMBER_ID)
        self.assertEqual(ctx.exception.code, "symlink_refused")

    def test_cross_role_roster_paths_refused(self):
        from fastapi.testclient import TestClient

        import server.main as main
        from server.routes import projects as projects_route

        with self.assertRaises(ValueError):
            projects_route.normalize_provision_roster_paths(
                ".talk/agents/agent_other/IDENTITY.md",
                ".talk/agents/agent_other/SOUL.md",
                ".talk/agents/agent_other/USER.md",
                expected_member_dir="agent_self",
            )
        ok = projects_route.normalize_provision_roster_paths(
            ".talk/agents/agent_self/IDENTITY.md",
            ".talk/agents/agent_self/SOUL.md",
            ".talk/agents/agent_self/USER.md",
            expected_member_dir="agent_self",
        )
        self.assertEqual(ok["identity_path"], ".talk/agents/agent_self/IDENTITY.md")
        self.assertIsNotNone(TestClient(main.app))

    def test_plain_directories_are_still_accepted(self):
        real = self._tmp / "plain"
        target = self._tmp / "plain-project"
        target.mkdir()
        paths = rp.profile_target_paths(target, MEMBER_ID)
        self.assertEqual(len(paths), 3)
        self.assertEqual(list(real.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
