# -*- coding: utf-8 -*-
"""R1-2 定向补正（TALK #220）：G1–G4 的闭合证据；#221 H1 精确 409 错误码补正。

覆盖范围
--------
- G1：成功后的凭据轮换不再被当成「免 ACK 的旧成功」——未显式 ``--resume`` 时明确
  ``resume_required`` 且零本地副作用；显式 resume 后按新代际重开凭据相关步骤；只有
  **精确终态 + 当前事实吻合** 的 409 才降为 no-op，禁用/离册/归档等 409 一律拒绝。
- H1（#221）：409 降为 no-op 还必须**逐字命中白名单 ``provision_job_terminal``**；
  默认 ``UrlLibTransport`` 有界解析且只保留白名单码（不回显/落盘远端正文）。覆盖
  disabled→409→reenable→GET200、archived→409→restore→GET200 两个真实反例，未知/
  缺失/非法 409、版本/revision 变化拒绝，以及默认 HTTP 边界的有界解析审查测试。
- G2：陈旧锁回收与新占有之间有真正的 OS 互斥——两个/多个真实进程对同一死锁记录竞争
  时最多一位 owner；活 owner 的可见锁文件即使被外部删除，第二进程也无法抢占。
- G3：``GET /roles`` 与 ``GET .../binding`` 之间的连接漂移不再被报成「精确绑定通过」；
  比对创建操作所选 choice 的预期指纹与本次读取的绑定指纹。
- G4：Windows 正式 Key 文件用「同目录私有临时文件 + 原子替换」发布，中断/短写/Flush
  失败/回读失败后正式目标保持完整或不存在，同一 Key + 同一操作可续跑。

全部用例使用隔离临时库/隔离文件树与假 Key；只终止本测试自己启动的受控子进程，
不接触真实用户服务、真实 Key、生产数据库或浏览器。
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(ROOT), str(ROOT / "scripts")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import role_provision as rp  # noqa: E402
from server.models import Member, ProjectAgent, ProjectRole  # noqa: E402
from tests.test_role_provision import (  # noqa: E402
    MEMBER_ID,
    PROJECT_ID,
    RoleProvisionTestCase,
    _binding_out,
    happy_transport,
)
from tests.test_role_provision_rework import (  # noqa: E402
    OPERATOR_KEY,
    PROJECT,
    _ApiCase,
    _ClientTransport,
)


def _member_path(member_id: str, suffix: str = "") -> str:
    return f"/api/projects/{PROJECT}/roles/{quote(member_id, safe='')}{suffix}"


def _binding_path(member_id: str) -> str:
    return f"/api/projects/{PROJECT}/agents/{quote(member_id, safe='')}/binding"


def _ack_events(transport) -> list[dict]:
    return [event for event in transport.events if event["path"].endswith("/ack")]


# ══════════════════════════════════════════════════════════════════════
# G1：成功后的轮换与任意 409
# ══════════════════════════════════════════════════════════════════════


class G1StaleSuccessTests(_ApiCase):
    def test_rotation_then_apply_without_resume_requires_explicit_resume(self):
        operation_key = "followup-g1-rotate-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]

        with self.h.make_client() as client:
            first, first_code, project_root, _keys, _tr = self.run_script(
                client, role, operation_key
            )
            self.assertEqual(first_code, 0, json.dumps(first, ensure_ascii=False))
            self.assertEqual(first["conclusion"], "applied")
            self.assertTrue(first["ack"]["sent"])
            self.assertEqual(self.job_row(operation_key).status, "succeeded")
            self.assertEqual(self.job_row(operation_key).credential_version, 1)

            rotated = client.post(
                _member_path(member_id, "/rotate-key"),
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(rotated.status_code, 200, rotated.text)
            new_key = rotated.json()["api_key"]
            self.assertEqual(rotated.json()["credential_version"], 2)

            # 新 Key + 新 Key 根：三步本地都会算出成功，旧实现会报 exit0/applied/not_required。
            fresh_root = self._tmp / "secrets-g1"
            env = {
                "TALK_ROLE_API_KEY": new_key,
                "TALK_OPERATOR_API_KEY": OPERATOR_KEY,
            }
            second, second_code, _pr, _kr, transport = self.run_script(
                client,
                role,
                operation_key,
                project_root=project_root,
                key_root=fresh_root,
                environ=env,
            )
            self.assertEqual(second_code, 1)
            self.assertEqual(second["conclusion"], "failed")
            self.assertNotEqual(second["conclusion"], "applied")
            self.assertEqual(second["error_code"], "resume_required")
            self.assertEqual(second["ack"]["reason"], "resume_required")
            self.assertFalse(second["ack"]["sent"])
            self.assertEqual(_ack_events(transport), [])
            # 未显式恢复 → 零本地副作用：新 Key 根本没有落盘，服务端作业仍是旧快照。
            self.assertFalse(rp.key_file_path(fresh_root, member_id).is_file())
            stored = self.job_row(operation_key)
            self.assertEqual(stored.status, "succeeded")
            self.assertEqual(stored.credential_version, 1)

            # 显式 resume：服务端强制重开 key_file/preflight，按 v2 代际重新 ACK。
            resumed, resumed_code, _pr2, _kr2, _tr2 = self.run_script(
                client,
                role,
                operation_key,
                project_root=project_root,
                key_root=fresh_root,
                environ=env,
                resume=True,
            )
            self.assertEqual(
                resumed_code, 0, json.dumps(resumed, ensure_ascii=False)
            )
            self.assertEqual(resumed["conclusion"], "applied")
            self.assertTrue(resumed["ack"]["sent"])
            self.assertEqual(resumed["steps"]["key_file"]["state"], "succeeded")
            self.assertEqual(resumed["steps"]["preflight"]["state"], "succeeded")
            job = client.get(
                _member_path(member_id, "/provision"),
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            ).json()
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["credential_version"], 2)
            self.assertEqual(job["role_credential_version"], 2)
            self.assertEqual(
                rp._read_key_file(rp.key_file_path(fresh_root, member_id)), new_key
            )

    def test_terminal_409_with_unchanged_credential_is_still_noop(self):
        operation_key = "followup-g1-terminal-ok-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]

        with self.h.make_client() as client:
            first, first_code, project_root, key_root, _tr = self.run_script(
                client, role, operation_key
            )
            self.assertEqual(first_code, 0)
            self.assertEqual(first["conclusion"], "applied")

            # 原凭据不变 + 作业已 succeeded：服务端 409 provision_job_terminal，重读事实吻合。
            second, second_code, _pr, _kr, transport = self.run_script(
                client,
                role,
                operation_key,
                project_root=project_root,
                key_root=key_root,
                resume=True,
            )
            self.assertEqual(second_code, 0, json.dumps(second, ensure_ascii=False))
            self.assertEqual(second["conclusion"], "applied")
            self.assertEqual(second["job"]["action"], "terminal")
            self.assertEqual(second["ack"]["reason"], "not_required")
            self.assertEqual(second["ack"]["results"], [])
            self.assertEqual(_ack_events(transport), [])
            self.assertEqual(self.job_row(operation_key).credential_version, 1)

    def test_resume_409_from_disabled_member_is_refused_not_terminal(self):
        """复现 #219 反例：GET 看到 succeeded 之后目标被禁用，POST 409 不得改判成功。"""
        operation_key = "followup-g1-disabled-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        events: list[dict] = []

        with self.h.make_client() as client:
            first, first_code, _pr, _kr, _tr = self.run_script(
                client, role, operation_key
            )
            self.assertEqual(first_code, 0)
            self.assertTrue(first["ack"]["sent"])
            self.assertEqual(self.job_row(operation_key).status, "succeeded")

            def hook(transport, method, path, api_key, body):
                if (
                    method == "POST"
                    and path.endswith("/provision")
                    and isinstance(body, dict)
                    and body.get("resume")
                    and not events
                ):
                    with self.h.session() as session:
                        member = session.get(Member, member_id)
                        member.disabled_at = datetime.now(timezone.utc)
                        session.add(member)
                        session.commit()
                    events.append({"disabled_before_post": True})

            transport = _ClientTransport(client, hook=hook)
            doc, code, *_ = self.run_script(
                client, role, operation_key, resume=True, steps="profile", transport=transport
            )

            self.assertEqual(events, [{"disabled_before_post": True}], "钩子未触发")
            self.assertEqual(code, 1)
            self.assertEqual(doc["conclusion"], "failed")
            self.assertNotEqual(doc["conclusion"], "applied")
            self.assertEqual(doc["job"]["action"], "none")
            self.assertNotEqual(doc["job"]["action"], "terminal")
            self.assertEqual(doc["job"]["error_code"], "http_error")
            self.assertFalse(doc["ack"]["sent"])
            self.assertEqual(_ack_events(transport), [])
            # 真实服务端在禁用后确实返回 409（且不是 provision_job_terminal）。
            response = client.post(
                _member_path(member_id, "/provision"),
                headers={"X-API-Key": OPERATOR_KEY},
                json={"operation_key": operation_key, "resume": True},
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "provision_member_disabled")

    def test_resume_409_from_removed_roster_is_refused_not_terminal(self):
        operation_key = "followup-g1-roster-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]

        with self.h.make_client() as client:
            first, first_code, _pr, _kr, _tr = self.run_script(
                client, role, operation_key
            )
            self.assertEqual(first_code, 0)
            with self.h.session() as session:
                session.delete(session.get(ProjectAgent, (PROJECT, member_id)))
                session.commit()

            doc, code, *_ = self.run_script(
                client, role, operation_key, resume=True, steps="profile"
            )
            self.assertEqual(code, 1)
            self.assertEqual(doc["conclusion"], "failed")
            self.assertNotEqual(doc["job"]["action"], "terminal")
            self.assertEqual(doc["job"]["error_code"], "http_error")
            response = client.post(
                _member_path(member_id, "/provision"),
                headers={"X-API-Key": OPERATOR_KEY},
                json={"operation_key": operation_key, "resume": True},
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "provision_roster_missing")


# ══════════════════════════════════════════════════════════════════════
# H1（#221）：409 精确错误码 —— 只有 provision_job_terminal 才允许 no-op
# ══════════════════════════════════════════════════════════════════════

_ENSURE_OPERATION_KEY = "recovery-h1-ensure-0001"


def _job_payload(
    *,
    status: str = "succeeded",
    revision: int = 3,
    credential_version: int = 1,
    role_credential_version: object = None,
    step_state: str = "succeeded",
) -> dict:
    """可控 provision 作业响应：默认「未轮换的精确终态」。"""
    if role_credential_version is None:
        role_credential_version = credential_version
    return {
        "operation_key": _ENSURE_OPERATION_KEY,
        "status": status,
        "revision": revision,
        "credential_version": credential_version,
        "role_credential_version": role_credential_version,
        "expected_binding_fingerprint": "f" * 64,
        "steps": {
            step: {"state": step_state, "attempts": 1} for step in rp.STEP_ORDER
        },
    }


class _EnsureJobTransport:
    """按脚本队列驱动的 ``_ensure_job`` 假传输：断言方法顺序，不回显远端正文。"""

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def request_json(self, method, url, *, api_key=None, body=None, timeout=None):
        self.calls.append({"method": method.upper(), "url": url, "body": body})
        if not self.script:
            raise AssertionError(f"意外的额外请求：{method} {url}")
        step = self.script.pop(0)
        if step["method"] != method.upper():
            raise AssertionError(f"请求顺序不符：期望 {step['method']}，实际 {method}")
        return rp.HttpResponse(
            status=step["status"],
            payload=step.get("payload"),
            error_code=step.get("error_code"),
        )


class G1EnsureJobExact409Tests(unittest.TestCase):
    """``_ensure_job`` 的 409 判定：默认边界错误码 + 当前代际事实，两者缺一不可。"""

    def _ensure(self, script: list[dict]):
        transport = _EnsureJobTransport(script)
        info = rp._ensure_job(
            transport=transport,
            base_url="http://testserver",
            project_id=PROJECT_ID,
            member_id=MEMBER_ID,
            operation_key=_ENSURE_OPERATION_KEY,
            resume=True,
            resume_steps=None,
            operator_key=OPERATOR_KEY,
            timeout=5.0,
        )
        return info, transport

    def _assert_refused(self, script: list[dict], *, calls: int) -> rp.ProvisionError:
        transport = _EnsureJobTransport(script)
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp._ensure_job(
                transport=transport,
                base_url="http://testserver",
                project_id=PROJECT_ID,
                member_id=MEMBER_ID,
                operation_key=_ENSURE_OPERATION_KEY,
                resume=True,
                resume_steps=None,
                operator_key=OPERATOR_KEY,
                timeout=5.0,
            )
        self.assertEqual(ctx.exception.code, "http_error")
        self.assertIn("HTTP 409", ctx.exception.detail)
        self.assertEqual(len(transport.calls), calls)
        return ctx.exception

    def test_exact_terminal_code_from_default_boundary_field_is_noop(self):
        # 默认 UrlLibTransport 形状：payload 已丢弃，只留白名单 error_code。
        info, transport = self._ensure(
            [
                {"method": "GET", "status": 200, "payload": _job_payload()},
                {"method": "POST", "status": 409, "error_code": "provision_job_terminal"},
                {"method": "GET", "status": 200, "payload": _job_payload()},
            ]
        )
        self.assertEqual(info["action"], "terminal")
        self.assertEqual([call["method"] for call in transport.calls], ["GET", "POST", "GET"])

    def test_known_non_terminal_code_is_refused_without_fresh_get(self):
        error = self._assert_refused(
            [
                {"method": "GET", "status": 200, "payload": _job_payload()},
                {
                    "method": "POST",
                    "status": 409,
                    "payload": {"detail": "provision_member_disabled"},
                },
            ],
            calls=2,
        )
        self.assertIn("provision_member_disabled", error.detail)

    def test_unknown_and_empty_and_illegal_codes_are_refused(self):
        for label, post in (
            ("unknown", {"method": "POST", "status": 409, "payload": {"detail": "surprise"}}),
            ("empty", {"method": "POST", "status": 409}),
            (
                "illegal-shape",
                {"method": "POST", "status": 409, "payload": {"detail": {"code": "surprise"}}},
            ),
            (
                "non-whitelisted-error-code-field",
                {"method": "POST", "status": 409, "error_code": "surprise"},
            ),
        ):
            with self.subTest(label=label):
                script = [
                    {"method": "GET", "status": 200, "payload": _job_payload()},
                    post,
                ]
                self._assert_refused(script, calls=2)

    def test_terminal_code_but_changed_revision_is_refused(self):
        error = self._assert_refused(
            [
                {"method": "GET", "status": 200, "payload": _job_payload(revision=3)},
                {"method": "POST", "status": 409, "error_code": "provision_job_terminal"},
                {"method": "GET", "status": 200, "payload": _job_payload(revision=4)},
            ],
            calls=3,
        )
        self.assertIn("provision_job_terminal", error.detail)

    def test_terminal_code_but_rotated_credential_is_refused(self):
        self._assert_refused(
            [
                {
                    "method": "GET",
                    "status": 200,
                    "payload": _job_payload(credential_version=1, role_credential_version=1),
                },
                {"method": "POST", "status": 409, "error_code": "provision_job_terminal"},
                {
                    "method": "GET",
                    "status": 200,
                    "payload": _job_payload(credential_version=2, role_credential_version=2),
                },
            ],
            calls=3,
        )

    def test_terminal_code_but_pre_snapshot_not_succeeded_is_refused(self):
        self._assert_refused(
            [
                {"method": "GET", "status": 200, "payload": _job_payload(status="pending")},
                {"method": "POST", "status": 409, "error_code": "provision_job_terminal"},
            ],
            calls=2,
        )

    def test_terminal_code_but_rotation_before_post_is_refused(self):
        self._assert_refused(
            [
                {
                    "method": "GET",
                    "status": 200,
                    "payload": _job_payload(credential_version=1, role_credential_version=2),
                },
                {"method": "POST", "status": 409, "error_code": "provision_job_terminal"},
            ],
            calls=2,
        )


class UrlLibTransportErrorBodyTests(unittest.TestCase):
    """默认 HTTP 边界：可审查地验证「有界解析 + 固定白名单 + 绝不保留正文」。"""

    def _transport_response(self, body: bytes):
        error = HTTPError("http://testserver/api/x", 409, "Conflict", {}, io.BytesIO(body))
        with patch.object(rp, "urlopen", side_effect=error):
            return rp.UrlLibTransport(timeout=1.0).request_json(
                "POST", "http://testserver/api/x", api_key="canary-key"
            )

    def test_whitelisted_code_is_extracted_and_payload_dropped(self):
        response = self._transport_response(b'{"detail": "provision_job_terminal"}')
        self.assertEqual(response.status, 409)
        self.assertIsNone(response.payload)
        self.assertEqual(response.error_code, "provision_job_terminal")
        self.assertEqual(
            rp._whitelisted_response_error_code(response), "provision_job_terminal"
        )

    def test_detail_object_shape_is_supported(self):
        response = self._transport_response(
            b'{"detail": {"code": "provision_member_disabled"}}'
        )
        self.assertEqual(response.error_code, "provision_member_disabled")

    def test_arbitrary_remote_text_is_never_retained(self):
        body = (
            b'{"detail": "canary-secret-key-123", "api_key": "canary-secret-key-123",'
            b' "path": "C:\\\\Users\\\\secret\\\\agent.key"}'
        )
        response = self._transport_response(body)
        self.assertEqual(response.status, 409)
        self.assertIsNone(response.payload)
        self.assertIsNone(response.error_code)
        rendered = repr(response)
        self.assertNotIn("canary-secret-key-123", rendered)
        self.assertNotIn("agent.key", rendered)

    def test_non_json_and_oversized_bodies_yield_no_code(self):
        for body in (
            b"<html>proxy error: canary-secret-key-123</html>",
            b'{"detail": "provision_job_terminal"}' + b"x" * 5000,
        ):
            with self.subTest(size=len(body)):
                response = self._transport_response(body)
                self.assertIsNone(response.error_code)
                self.assertIsNone(response.payload)

    def test_read_is_bounded_to_the_documented_limit(self):
        class _RecordingBytesIO(io.BytesIO):
            def __init__(self, data: bytes) -> None:
                super().__init__(data)
                self.requests: list[int] = []

            def read(self, size: int = -1) -> bytes:
                self.requests.append(size)
                return super().read(size)

        fp = _RecordingBytesIO(b'{"detail": "provision_job_terminal"}')
        error = HTTPError("http://testserver/api/x", 409, "Conflict", {}, fp)
        with patch.object(rp, "urlopen", side_effect=error):
            response = rp.UrlLibTransport(timeout=1.0).request_json(
                "POST", "http://testserver/api/x"
            )
        self.assertEqual(fp.requests, [rp.ERROR_BODY_READ_LIMIT_BYTES])
        self.assertEqual(response.error_code, "provision_job_terminal")


class G1RealServerInterleaved409Tests(_ApiCase):
    """真实临时库 + 真实 API：409 后事实恢复也不能抹掉本次拒绝（#220 H1 反例）。"""

    def test_disabled_then_reenabled_post_409_is_refused_with_zero_side_effects(self):
        operation_key = "recovery-h1-disabled-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        state: dict = {"disabled": False, "reenabled": False}

        with self.h.make_client() as client:
            first, first_code, _pr, _kr, _tr = self.run_script(
                client, role, operation_key
            )
            self.assertEqual(first_code, 0, json.dumps(first, ensure_ascii=False))
            self.assertEqual(self.job_row(operation_key).status, "succeeded")

            def before(transport, method, path, api_key, body):
                if (
                    method == "POST"
                    and path.endswith("/provision")
                    and isinstance(body, dict)
                    and body.get("resume")
                ):
                    with self.h.session() as session:
                        member = session.get(Member, member_id)
                        member.disabled_at = datetime.now(timezone.utc)
                        session.add(member)
                        session.commit()
                    state["disabled"] = True

            def after(transport, method, path, api_key, body, status):
                if (
                    method == "POST"
                    and path.endswith("/provision")
                    and isinstance(body, dict)
                    and body.get("resume")
                ):
                    state["post_status"] = status
                    with self.h.session() as session:
                        member = session.get(Member, member_id)
                        member.disabled_at = None
                        session.add(member)
                        session.commit()
                    state["reenabled"] = True

            class _CapturingTransport(_ClientTransport):
                def request_json(self, *args, **kwargs):
                    response = super().request_json(*args, **kwargs)
                    if response.status == 409 and isinstance(response.payload, Mapping):
                        state.setdefault("post_detail", response.payload.get("detail"))
                    return response

            transport = _CapturingTransport(client, hook=before, after_hook=after)
            fresh_project = self._tmp / "h1-disabled-fresh"
            fresh_keys = self._tmp / "h1-disabled-keys"
            doc, code, *_ = self.run_script(
                client,
                role,
                operation_key,
                resume=True,
                steps="profile",
                project_root=fresh_project,
                key_root=fresh_keys,
                transport=transport,
            )

            self.assertTrue(state["disabled"] and state["reenabled"], state)
            self.assertEqual(state.get("post_status"), 409, state)
            self.assertEqual(state.get("post_detail"), "provision_member_disabled", state)
            # 事实已恢复：同一 operation 的真实 GET 现在就是 200/succeeded（旧实现据此改判）。
            recovered = client.get(
                _member_path(member_id, "/provision"),
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertEqual(recovered.json()["status"], "succeeded")

            self.assertEqual(code, 1, json.dumps(doc, ensure_ascii=False))
            self.assertEqual(doc["conclusion"], "failed")
            self.assertEqual(doc["job"]["action"], "none")
            self.assertNotEqual(doc["job"]["action"], "terminal")
            self.assertEqual(doc["job"]["error_code"], "http_error")
            self.assertIn("provision_member_disabled", doc["job"]["detail"])
            self.assertFalse(doc["ack"]["sent"])
            self.assertEqual(_ack_events(transport), [])
            # 零本地副作用：新工程根没有身份档，新 Key 根没有 Key。
            self.assertEqual(sorted(fresh_project.rglob("*.md")), [])
            self.assertFalse(rp.key_file_path(fresh_keys, member_id).exists())
            self.assertFalse(rp.profile_lock_path_for(fresh_project, member_id).exists())

    def test_archived_then_restored_post_409_is_refused(self):
        operation_key = "recovery-h1-archived-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        state: dict = {"restored": False}

        with self.h.make_client() as client:
            first, first_code, *_ = self.run_script(client, role, operation_key)
            self.assertEqual(first_code, 0)

            def before(transport, method, path, api_key, body):
                if (
                    method == "POST"
                    and path.endswith("/provision")
                    and isinstance(body, dict)
                    and body.get("resume")
                ):
                    with self.h.session() as session:
                        row = session.get(ProjectRole, (PROJECT, member_id))
                        row.archived_at = datetime.now(timezone.utc)
                        session.add(row)
                        session.commit()

            def after(transport, method, path, api_key, body, status):
                if (
                    method == "POST"
                    and path.endswith("/provision")
                    and isinstance(body, dict)
                    and body.get("resume")
                ):
                    state["post_status"] = status
                    with self.h.session() as session:
                        row = session.get(ProjectRole, (PROJECT, member_id))
                        row.archived_at = None
                        session.add(row)
                        session.commit()
                    state["restored"] = True

            class _CapturingTransport(_ClientTransport):
                def request_json(self, *args, **kwargs):
                    response = super().request_json(*args, **kwargs)
                    if response.status == 409 and isinstance(response.payload, Mapping):
                        state.setdefault("post_detail", response.payload.get("detail"))
                    return response

            transport = _CapturingTransport(client, hook=before, after_hook=after)
            fresh_project = self._tmp / "h1-archived-fresh"
            fresh_keys = self._tmp / "h1-archived-keys"
            doc, code, *_ = self.run_script(
                client,
                role,
                operation_key,
                resume=True,
                steps="profile",
                project_root=fresh_project,
                key_root=fresh_keys,
                transport=transport,
            )

            self.assertTrue(state["restored"], state)
            self.assertEqual(state.get("post_status"), 409, state)
            self.assertEqual(state.get("post_detail"), "role_archived", state)
            recovered = client.get(
                _member_path(member_id, "/provision"),
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertEqual(recovered.json()["status"], "succeeded")

            self.assertEqual(code, 1, json.dumps(doc, ensure_ascii=False))
            self.assertNotEqual(doc["job"]["action"], "terminal")
            self.assertEqual(doc["job"]["error_code"], "http_error")
            self.assertIn("role_archived", doc["job"]["detail"])
            self.assertFalse(doc["ack"]["sent"])
            self.assertEqual(sorted(fresh_project.rglob("*.md")), [])
            self.assertFalse(rp.key_file_path(fresh_keys, member_id).exists())


# ══════════════════════════════════════════════════════════════════════
# G2：陈旧回收 / 新占有的 OS 互斥
# ══════════════════════════════════════════════════════════════════════

_LOCK_CHILD = r'''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import role_provision as rp
base = Path(sys.argv[2]); name = sys.argv[3]; peers = sys.argv[4].split(",")
lock = base / "target.lock"
(base / ("ready-" + name)).write_text("1", encoding="utf-8")
deadline = time.time() + 30
while not all((base / ("ready-" + peer)).exists() for peer in peers):
    if time.time() > deadline:
        raise SystemExit(3)
    time.sleep(0.01)
result = {"name": name}
handle = None
try:
    handle = rp.acquire_lock(lock, 0)
    result.update(
        {
            "acquired": True,
            "reclaimed": handle["reclaimed"],
            "token": handle["token"],
            "pid": os.getpid(),
            "guard_held": rp.lock_guard_path_for(lock).exists(),
        }
    )
except rp.ProvisionError as exc:
    result.update({"acquired": False, "code": exc.code})
(base / ("result-" + name + ".json")).write_text(
    json.dumps(result, ensure_ascii=False), encoding="utf-8"
)
if handle is not None:
    while not (base / "stop").exists() and time.time() < deadline:
        time.sleep(0.02)
    rp.release_lock(lock, handle)
'''


class G2AtomicReclaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-followup-lock-"))
        self.addCleanup(
            lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True)
        )
        self.lock_path = self._tmp / "target.lock"
        self.procs: list[subprocess.Popen] = []

    def tearDown(self) -> None:
        (self._tmp / "stop").write_text("1", encoding="utf-8")
        for proc in self.procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - 仅清理
                proc.terminate()
                proc.wait(timeout=10)

    def _make_dead_lock(self) -> int:
        dead = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dead.wait(timeout=10)
        assert rp._process_is_alive(dead.pid) is False
        self.lock_path.write_text(
            json.dumps(
                {
                    "schema": rp.LOCK_SCHEMA,
                    "token": "followup-dead-token",
                    "pid": dead.pid,
                    "started_at": "2000-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        old = 1_000_000.0
        os.utime(self.lock_path, (old, old))
        return dead.pid

    def _spawn(self, names: list[str]) -> None:
        for name in names:
            log = open(self._tmp / f"{name}.log", "w", encoding="utf-8")
            self.addCleanup(log.close)
            self.procs.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        _LOCK_CHILD,
                        str(ROOT),
                        str(self._tmp),
                        name,
                        ",".join(names),
                    ],
                    stdout=log,
                    stderr=log,
                    cwd=str(ROOT),
                )
            )

    def _results(self, names: list[str]) -> dict[str, dict]:
        deadline = time.time() + 30
        while time.time() < deadline:
            if all((self._tmp / f"result-{name}.json").exists() for name in names):
                break
            time.sleep(0.02)
        return {
            name: json.loads(
                (self._tmp / f"result-{name}.json").read_text(encoding="utf-8")
            )
            for name in names
        }

    def _disk_token(self) -> str:
        return json.loads(self.lock_path.read_text(encoding="utf-8"))["token"]

    def test_two_real_reclaimers_of_same_dead_lock_yield_single_owner(self):
        self._make_dead_lock()
        self._spawn(["a", "b"])
        rows = self._results(["a", "b"])

        winners = [row for row in rows.values() if row["acquired"]]
        losers = [row for row in rows.values() if not row["acquired"]]
        self.assertEqual(len(winners), 1, rows)
        self.assertEqual(len(losers), 1, rows)
        self.assertTrue(winners[0]["reclaimed"], rows)
        self.assertEqual(losers[0]["code"], "provision_lock_busy")
        # 磁盘上的 owner 只可能是那位 winner；loser 存活/退出期间都没有持有任何代际。
        self.assertEqual(self._disk_token(), winners[0]["token"])
        self.assertTrue(rp.lock_guard_path_for(self.lock_path).exists())
        # winner 仍存活并持锁：loser 不是在 winner 释放后才轮到的。
        names = ["a", "b"]
        winner_index = names.index(winners[0]["name"])
        self.assertIsNone(
            self.procs[winner_index].poll(), "winner 未保持存活，竞争顺序不可信"
        )
        self.assertIs(rp._process_is_alive(winners[0]["pid"]), True)

    def test_multi_contender_dead_lock_has_at_most_one_owner(self):
        self._make_dead_lock()
        names = ["a", "b", "c", "d"]
        self._spawn(names)
        rows = self._results(names)

        winners = [row for row in rows.values() if row["acquired"]]
        self.assertEqual(len(winners), 1, rows)
        for row in rows.values():
            if not row["acquired"]:
                self.assertEqual(row["code"], "provision_lock_busy")
        self.assertEqual(self._disk_token(), winners[0]["token"])

    def test_live_owner_keeps_exclusive_even_if_disk_lock_is_removed(self):
        """复现 #219 反例的关键步：B 按旧判定 unlink 掉 A 的新活锁后仍不能占有。"""
        self._make_dead_lock()
        self._spawn(["a"])
        rows = self._results(["a"])
        self.assertTrue(rows["a"]["acquired"], rows)
        self.assertEqual(self._disk_token(), rows["a"]["token"])

        # 模拟第二个回收者按陈旧判定删除 A 的可见锁文件。
        os.remove(self.lock_path)
        self.assertFalse(self.lock_path.exists())

        # A 仍存活并持有守卫：B（本进程）必须被拒绝，A 的所有权没有被抢走。
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.acquire_lock(self.lock_path, 0)
        self.assertEqual(ctx.exception.code, "provision_lock_busy")

        # A 释放后 B 才能占有，且拿到的是全新代际。
        (self._tmp / "stop").write_text("1", encoding="utf-8")
        self.procs[0].wait(timeout=15)
        handle = rp.acquire_lock(self.lock_path, 0)
        try:
            self.assertNotEqual(handle["token"], rows["a"]["token"])
            self.assertEqual(self._disk_token(), handle["token"])
        finally:
            self.assertTrue(rp.release_lock(self.lock_path, handle))

    def test_dead_owner_after_guard_release_is_reopenable(self):
        """死 owner 之后守卫由 OS 自动释放，同一陈旧锁可以被重开。"""
        self._make_dead_lock()
        self._spawn(["a"])
        rows = self._results(["a"])
        self.assertTrue(rows["a"]["acquired"], rows)

        self.procs[0].kill()
        self.procs[0].wait(timeout=15)
        deadline = time.time() + 15
        while time.time() < deadline and rp._process_is_alive(rows["a"]["pid"]) is not False:
            time.sleep(0.05)
        self.assertIs(rp._process_is_alive(rows["a"]["pid"]), False)
        old = 1_000_000.0
        os.utime(self.lock_path, (old, old))
        handle = rp.acquire_lock(self.lock_path, 900)
        try:
            self.assertTrue(handle["reclaimed"])
            self.assertEqual(self._disk_token(), handle["token"])
        finally:
            self.assertTrue(rp.release_lock(self.lock_path, handle))

    def test_profile_lock_serializes_across_different_key_roots(self):
        project_root = self._tmp / "proj"
        project_root.mkdir()
        member_id = "agent:followup.role-g2-profile"
        profile_lock = rp.profile_lock_path_for(project_root, member_id)
        key_a = rp.lock_path_for(rp.key_file_path(self._tmp / "keys-a", member_id))
        key_b = rp.lock_path_for(rp.key_file_path(self._tmp / "keys-b", member_id))
        self.assertNotEqual(key_a, key_b)
        self.assertEqual(
            profile_lock,
            rp.profile_lock_path_for(project_root, member_id),
        )

        child_code = (
            "import sys, time\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r})\n"
            "import role_provision as rp\n"
            "from pathlib import Path\n"
            f"handle = rp.acquire_lock(Path({str(profile_lock)!r}), 0)\n"
            f"Path({str(self._tmp / 'profile.ready')!r}).write_text(handle['token'], encoding='utf-8')\n"
            "time.sleep(120)\n"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", child_code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(ROOT),
        )
        self.addCleanup(lambda: (child.poll() is None and child.kill(), child.wait()))
        deadline = time.time() + 30
        marker = self._tmp / "profile.ready"
        while not marker.exists() and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(marker.exists(), "子进程未拿到身份档锁")

        # 不同 Key 根不改变身份档锁路径：同 profile 的第二进程必须被拒绝。
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.acquire_lock(profile_lock, 0)
        self.assertEqual(ctx.exception.code, "provision_lock_busy")
        child.kill()
        child.wait(timeout=15)


# ══════════════════════════════════════════════════════════════════════
# G3：分次 GET 之间的连接漂移
# ══════════════════════════════════════════════════════════════════════


class _PreflightCase(RoleProvisionTestCase):
    def _run_preflight(self, transport, **overrides):
        self.key_root.mkdir(parents=True, exist_ok=True)
        if not self.key_file().is_file():
            rp._write_key_file(self.key_file(), "canary")
        for path in rp.profile_target_paths(self.project_root, MEMBER_ID).values():
            if not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# seeded\n", encoding="utf-8")
        return rp.run_provision(
            project_id=PROJECT_ID,
            member_id=MEMBER_ID,
            operation_key=rp_operation_key(),
            project_root=self.project_root,
            key_root=self.key_root,
            base_url="http://testserver",
            apply=True,
            steps="preflight",
            transport=transport,
            environ=dict(overrides.pop("environ", self.env_happy)),
            repo_root=self.repo,
            **overrides,
        )


def rp_operation_key() -> str:
    from tests.test_role_provision import OPERATION_KEY

    return OPERATION_KEY


class G3ChoiceFingerprintStrictnessTests(_PreflightCase):
    def test_choice_fingerprint_mismatch_fails(self):
        transport = happy_transport(binding=_binding_out(binding_fingerprint="a" * 64))
        document, code = self._run_preflight(transport)

        self.assertEqual(code, 1)
        self.assertEqual(document["steps"]["preflight"]["state"], "failed")
        self.assertEqual(document["error_code"], "identity_mismatch")
        self.assertIn("预期指纹", document["steps"]["preflight"]["detail"])

    def test_missing_choice_fingerprint_fails(self):
        transport = happy_transport()
        for route in transport.routes:
            for index, response in enumerate(route.responses):
                if isinstance(response, rp.HttpResponse) and isinstance(
                    response.payload, dict
                ):
                    response.payload.pop("expected_binding_fingerprint", None)
        document, code = self._run_preflight(transport)

        self.assertEqual(code, 1)
        self.assertEqual(document["error_code"], "identity_mismatch")
        self.assertIn("预期绑定指纹", document["steps"]["preflight"]["detail"])

    def test_matching_choice_fingerprint_passes(self):
        transport = happy_transport()
        document, code = self._run_preflight(transport)

        self.assertEqual(code, 0, json.dumps(document, ensure_ascii=False))
        self.assertEqual(document["conclusion"], "applied")
        self.assertIn(
            "choice_fingerprint=verified",
            document["steps"]["preflight"]["detail"],
        )


class G3BindingProjectionRaceTests(_ApiCase):
    def test_connection_drift_between_projections_is_not_reported_as_bound(self):
        """复现 #219 反例：GET roles 之后 PUT binding 只改 connection_ref。"""
        operation_key = "followup-g3-binding-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        events: list[dict] = []

        with self.h.make_client() as client:
            before = client.get(
                _binding_path(member_id),
                headers={"X-API-Key": role["api_key"]},
            ).json()["binding"]
            mutated = {
                key: before[key]
                for key in (
                    "runner_id",
                    "model_source",
                    "provider_id",
                    "connection_ref",
                    "model_id",
                    "model_alias",
                )
            }
            mutated["connection_ref"] = "native-alt-login"

            def after_hook(transport, method, path, api_key, body, status):
                if method == "GET" and path.endswith("/roles") and not events:
                    changed = client.put(
                        _binding_path(member_id),
                        headers={"X-API-Key": OPERATOR_KEY},
                        json={"binding": mutated},
                    )
                    events.append({"binding_update_status": changed.status_code})

            transport = _ClientTransport(client, after_hook=after_hook)
            document, code, *_ = self.run_script(
                client, role, operation_key, transport=transport
            )

            self.assertEqual(
                events, [{"binding_update_status": 200}], "绑定漂移钩子未生效"
            )
            self.assertEqual(code, 1)
            self.assertNotEqual(document["conclusion"], "applied")
            self.assertEqual(document["steps"]["preflight"]["state"], "failed")
            self.assertEqual(
                document["steps"]["preflight"]["error_code"], "identity_mismatch"
            )
            self.assertIn("预期指纹", document["steps"]["preflight"]["detail"])
            # 失败步骤按 failed 如实回报，绝不可能被回报成 succeeded。
            reported = {
                item["step"]: item["state"]
                for item in document["ack"]["results"]
                if item.get("sent")
            }
            self.assertEqual(reported.get("preflight"), "failed")
            stored = self.job_row(operation_key)
            self.assertNotEqual(stored.status, "succeeded")
            self.assertEqual(stored.status, "partial")

            now_roles = client.get(
                f"/api/projects/{PROJECT}/roles",
                headers={"X-API-Key": role["api_key"]},
            ).json()
            projected = next(
                item for item in now_roles if item["member_id"] == member_id
            )
            self.assertEqual(
                projected["model"]["choice_source"], "creation_operation_mismatch"
            )
            self.assertTrue(projected["model"]["choice_binding_mismatch"])
            # 预期指纹来自作业锚定的创建操作；当前绑定指纹已因连接漂移而不同。
            job = client.get(
                _member_path(member_id, "/provision"),
                params={"operation_key": operation_key},
                headers={"X-API-Key": OPERATOR_KEY},
            ).json()
            current_payload = client.get(
                _binding_path(member_id), headers={"X-API-Key": role["api_key"]}
            ).json()
            self.assertIsInstance(job["expected_binding_fingerprint"], str)
            self.assertNotEqual(
                job["expected_binding_fingerprint"],
                current_payload["binding"]["binding_fingerprint"],
            )


# ══════════════════════════════════════════════════════════════════════
# G4：中断安全的 Windows Key 发布
# ══════════════════════════════════════════════════════════════════════

_KEY_CRASH_CHILD = r'''
import ctypes, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import role_provision as rp
base = Path(sys.argv[2]); target = Path(sys.argv[3])
native = ctypes.WinDLL
def factory(name, *args, **kwargs):
    dll = native(name, *args, **kwargs)
    if name.lower() == "kernel32":
        def paused_write(*_args):
            (base / "paused").write_text("1", encoding="utf-8")
            while True:
                time.sleep(0.02)
        dll.WriteFile = paused_write
    return dll
ctypes.WinDLL = factory
rp._write_key_file(target, os.environ["FOLLOWUP_FAKE_ROLE_KEY"])
'''


def _key_temps(key_path: Path) -> list[Path]:
    return sorted(key_path.parent.glob(f".{key_path.name}.*.tmp"))


class G4KeyInterruptionTests(_ApiCase):
    @unittest.skipUnless(os.name == "nt", "Windows 私有 ACL / CreateFileW 用例")
    def test_crash_before_writefile_leaves_target_absent_then_resume_succeeds(self):
        operation_key = "followup-g4-key-crash-0001"
        role = self.make_role(operation_key)
        member_id = role["member_id"]
        key_root = self._tmp / "secrets-g4"
        key_root.mkdir(parents=True, exist_ok=True)
        key_path = rp.key_file_path(key_root, member_id)

        with self.h.make_client() as client:
            created = client.post(
                _member_path(member_id, "/provision"),
                headers={"X-API-Key": OPERATOR_KEY},
                json={"operation_key": operation_key},
            )
            self.assertEqual(created.status_code, 201, created.text)

            env = dict(os.environ)
            env["FOLLOWUP_FAKE_ROLE_KEY"] = role["api_key"]
            log = (key_root / "child.log").open("w", encoding="utf-8")
            self.addCleanup(log.close)
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _KEY_CRASH_CHILD,
                    str(ROOT),
                    str(key_root),
                    str(key_path),
                ],
                stdout=log,
                stderr=log,
                env=env,
                cwd=str(ROOT),
            )
            try:
                deadline = time.time() + 30
                marker = key_root / "paused"
                while not marker.exists() and proc.poll() is None and time.time() < deadline:
                    time.sleep(0.02)
                self.assertTrue(
                    marker.exists(),
                    "受控子进程未到达真实 CreateFile 之后的 WriteFile 屏障",
                )
                proc.terminate()
                proc.wait(timeout=15)
            finally:
                if proc.poll() is None:  # pragma: no cover - 兜底清理
                    proc.terminate()
                    proc.wait(timeout=15)

            # 中断后正式目标保持「不存在」；真实私有 ACL 只落在临时发布文件上。
            self.assertFalse(key_path.exists(), "中断留下了半截正式 Key 文件")
            temps = _key_temps(key_path)
            self.assertTrue(temps, "未观察到真实临时发布文件（CreateFileW 未执行？）")
            ok, detail = rp._windows_verify_private_acl(temps[0])
            self.assertTrue(ok, detail)

            # 同一 Key + 同一操作（resume）可以续跑：正式文件完整且 ACL 私有。
            document, code, *_ = self.run_script(
                client, role, operation_key, key_root=key_root, resume=True
            )
            self.assertEqual(code, 0, json.dumps(document, ensure_ascii=False))
            self.assertEqual(document["steps"]["key_file"]["state"], "succeeded")
            self.assertEqual(
                rp._read_key_file(key_path), role["api_key"].strip()
            )
            ok, detail = rp._windows_verify_private_acl(key_path)
            self.assertTrue(ok, detail)
            self.assertEqual(_key_temps(key_path), [])


class G4KeyPublishFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-followup-keyfail-"))
        self.addCleanup(
            lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True)
        )
        self.key_path = self._tmp / "agent_fail.key"

    @unittest.skipUnless(os.name == "nt", "Windows 私有 ACL / CreateFileW 用例")
    def test_replace_failure_reports_capability_blocked_without_target(self):
        with patch.object(rp.os, "replace", side_effect=OSError("injected")):
            with self.assertRaises(rp.ProvisionError) as ctx:
                rp._write_key_file(self.key_path, "canary-followup-key")
        self.assertEqual(ctx.exception.code, "key_permissions_failed")
        self.assertIn("原子提交", ctx.exception.detail)
        self.assertFalse(self.key_path.exists())
        self.assertEqual(_key_temps(self.key_path), [])

    @unittest.skipUnless(os.name == "nt", "Windows 私有 ACL / CreateFileW 用例")
    def test_short_write_failure_leaves_no_target_and_no_temp(self):
        original = rp._windows_create_file_with_private_acl

        def short_write(path, payload):
            original(path, payload[:1])
            raise rp._WindowsAclError("WriteFile short write")

        with patch.object(rp, "_windows_create_file_with_private_acl", short_write):
            with self.assertRaises(rp.ProvisionError) as ctx:
                rp._write_key_file(self.key_path, "canary-followup-key")
        self.assertEqual(ctx.exception.code, "key_permissions_failed")
        self.assertFalse(self.key_path.exists())
        self.assertEqual(_key_temps(self.key_path), [])

    @unittest.skipUnless(os.name == "nt", "Windows 私有 ACL / CreateFileW 用例")
    def test_flush_failure_leaves_no_target_and_no_temp(self):
        original = rp._windows_create_file_with_private_acl

        def flush_failure(path, payload):
            original(path, payload)
            raise rp._WindowsAclError("FlushFileBuffers failed")

        with patch.object(rp, "_windows_create_file_with_private_acl", flush_failure):
            with self.assertRaises(rp.ProvisionError) as ctx:
                rp._write_key_file(self.key_path, "canary-followup-key")
        self.assertEqual(ctx.exception.code, "key_permissions_failed")
        self.assertFalse(self.key_path.exists())
        self.assertEqual(_key_temps(self.key_path), [])

    @unittest.skipUnless(os.name == "nt", "Windows 私有 ACL / CreateFileW 用例")
    def test_temp_readback_mismatch_leaves_no_target_and_no_temp(self):
        original = rp._windows_create_file_with_private_acl

        def wrong_bytes(path, payload):
            original(path, payload + b"tampered\n")

        with patch.object(rp, "_windows_create_file_with_private_acl", wrong_bytes):
            with self.assertRaises(rp.ProvisionError) as ctx:
                rp._write_key_file(self.key_path, "canary-followup-key")
        self.assertEqual(ctx.exception.code, "key_write_failed")
        self.assertFalse(self.key_path.exists())
        self.assertEqual(_key_temps(self.key_path), [])

    @unittest.skipUnless(os.name == "nt", "Windows 私有 ACL / CreateFileW 用例")
    def test_replaced_target_readback_failure_removes_target(self):
        real_read_bytes = Path.read_bytes
        target = self.key_path

        def failing_read_bytes(self):
            if self == target:
                raise OSError("injected read failure")
            return real_read_bytes(self)

        with patch.object(Path, "read_bytes", failing_read_bytes):
            with self.assertRaises(rp.ProvisionError) as ctx:
                rp._write_key_file(target, "canary-followup-key")
        self.assertEqual(ctx.exception.code, "key_permissions_failed")
        self.assertFalse(target.exists(), "回读失败后正式目标仍存在（无法证明完整）")
        self.assertEqual(_key_temps(target), [])

    @unittest.skipUnless(os.name == "nt", "Windows 私有 ACL / CreateFileW 用例")
    def test_published_target_carries_private_acl(self):
        payload = "canary-followup-key-0123456789"
        rp._write_key_file(self.key_path, payload)
        self.assertEqual(self.key_path.read_text(encoding="utf-8").strip(), payload)
        ok, detail = rp._windows_verify_private_acl(self.key_path)
        self.assertTrue(ok, detail)
        self.assertIn("acl=", detail)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
