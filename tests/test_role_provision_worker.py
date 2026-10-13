"""角色生命周期 R1-4b：默认关闭的宿主请求 worker 的真实文件/HTTP 闭环测试。

覆盖 ``docs/spec/ROLE_CREATION_PROVISION_REQUEST_CONTRACT.md`` §10 与宿主片交付清单：

- 正向：隔离 server（进程内 ``TestClient``，**不启动生产服务**）+ 假 human/角色 Key，
  单角色人类意图 → 真实 ``claim``/``create`` → 真实私有 Key 文件 + ``credential.json``
  → 本人核验/三步 ACK → ``report(provisioned)``；完成后一次显式 recover 续跑；
- 负向：worker 关闭零写、非回环/跨机重定向拒发凭据、错 host/过期/config 换代拒后续、
  双 worker 同目标锁互斥、201 丢响应需人工恢复、轮换同意图不重复、未知旧文件不覆盖、
  已知旧代允许专用替换、Key 已发布 metadata 失败可修复、预检失败不报成功、
  配置不 spawn、IO 超时不堵 R1-3 控制循环、哨兵 Key/token 零命中。

真实文件只写本片自建虚拟项目与假凭据：``key_root`` 在系统临时目录（仓库之外），
``project_root`` 在 ``.tmp-tests/<case>/proj``。
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import uvicorn
from sqlmodel import select

import server.main as main
import scripts.role_service_host as role_service_host
from server.models import Member, ProjectRole, RoleProvisionRequestRow
from scripts import role_provision as rp
from scripts import role_provision_worker as rpw
from scripts.role_provision_worker import (
    PUBLIC_KEYS,
    LeaseInvalidated,
    RoleProvisionWorker,
    WorkerError,
    WorkerStopped,
    WorkerTransport,
    _LoopbackRedirectHandler,
    assert_loopback_base_url,
    coerce_outcomes,
    loopback_host,
    redact,
)
from scripts.role_service_host import HostManager, TalkHostClient
from tests.test_project_roles import RUNNER_ID, RoleApiTestCase

_saved_root_level: int | None = None
_saved_handler_levels: list[int] = []


def setUpModule():
    """本模块只做行为断言；把 JSON 访问日志降到 WARNING，便于保存可读原始证据。"""
    global _saved_root_level, _saved_handler_levels
    root = logging.getLogger()
    _saved_root_level = root.level
    _saved_handler_levels = [handler.level for handler in root.handlers]
    root.setLevel(logging.WARNING)
    for handler in root.handlers:
        handler.setLevel(logging.WARNING)


def tearDownModule():
    root = logging.getLogger()
    if _saved_root_level is not None:
        root.setLevel(_saved_root_level)
    for handler, level in zip(root.handlers, _saved_handler_levels):
        handler.setLevel(level)


SENTINEL_OPERATOR = "operator-sentinel-key-1"
SENTINEL_ROLE_KEY = "role-sentinel-key-should-never-leak"
HOST_LABEL = "host-desktop-1"


class _ClientTransport:
    """把进程内 ``TestClient`` 适配成 ``role_provision`` 的同形状传输。"""

    def __init__(self, case: "WorkerTestCase"):
        self.case = case
        self.calls: list[str] = []

    def request_json(self, method, url, *, api_key=None, body=None, timeout=None):
        parts = urllib.parse.urlsplit(str(url))
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        self.calls.append(f"{method.upper()} {parts.path}")
        headers = {"X-API-Key": str(api_key)} if api_key else {}
        with self.case.make_client() as client:
            response = client.request(method.upper(), path, headers=headers, json=body)
        payload = None
        if response.content:
            try:
                payload = response.json()
            except ValueError:
                payload = None
        code = None
        if response.status_code >= 400 and isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail in rp.REQUEST_ENDPOINT_ERROR_WHITELIST:
                code = detail
        return rp.HttpResponse(
            status=response.status_code, payload=payload, error_code=code
        )


class _RecordingTransport(_ClientTransport):
    def request_json(self, *args, **kwargs):
        raise AssertionError("worker 处于关闭/只读模式时不得发起 HTTP")


class _FlakyAckTransport(_ClientTransport):
    """让前 ``fail_times`` 次单步 ACK 的响应「丢失」，用于验证受控续跑。"""

    def __init__(self, case: "WorkerTestCase", *, fail_times: int = 1):
        super().__init__(case)
        self.remaining = int(fail_times)

    def request_json(self, method, url, *, api_key=None, body=None, timeout=None):
        if (
            method.upper() == "POST"
            and str(url).endswith("/provision/ack")
            and self.remaining > 0
        ):
            self.remaining -= 1
            return rp.HttpResponse(status=0, payload=None)
        return super().request_json(
            method, url, api_key=api_key, body=body, timeout=timeout
        )


class WorkerTestCase(RoleApiTestCase):
    """R1-4b 公共夹具：启用宿主配置的隔离项目 + 仓库外假 Key 根。"""

    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.choice_id = self.seed_runner_and_choice()
        self.project_root = self._tmpdir / "proj"
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.key_root = Path(tempfile.mkdtemp(prefix="talk-worker-keys-"))
        self.addCleanup(lambda: shutil.rmtree(self.key_root, ignore_errors=True))
        self.transport = _ClientTransport(self)
        # operator（human）凭据：夹具里 human:bobo 的真实 api_key 是 bobo-key。
        self.environ = {"TALK_OPERATOR_API_KEY": "bobo-key"}

    # ── 服务端事实 ───────────────────────────────────────────────────

    def enable_host(self, *, expected_version: int = 0, host_label: str = HOST_LABEL):
        with self.make_client() as client:
            return client.post(
                "/api/projects/prj_alpha/role-provision-host/enable",
                headers={"X-API-Key": "bobo-key"},
                json={"host_label": host_label, "expected_version": expected_version},
            )

    def disable_host(self, *, expected_version: int):
        with self.make_client() as client:
            return client.post(
                "/api/projects/prj_alpha/role-provision-host/disable",
                headers={"X-API-Key": "bobo-key"},
                json={"expected_version": expected_version},
            )

    def create_intent(self, request_key: str, *, kind: str = "create", **extra):
        body = {
            "request_key": request_key,
            "kind": kind,
            "confirm": True,
            "role_name": "dev",
            "runner_id": RUNNER_ID,
            "choice_id": self.choice_id,
        }
        body.update(extra)
        with self.make_client() as client:
            return client.post(
                "/api/projects/prj_alpha/role-requests",
                headers={"X-API-Key": "bobo-key"},
                json=body,
            )

    def get_request(self, request_key: str) -> dict:
        with self.make_client() as client:
            return client.get(
                f"/api/projects/prj_alpha/role-requests/{request_key}",
                headers={"X-API-Key": "bobo-key"},
            ).json()

    def claim_request(self, request_key: str, *, host: str = HOST_LABEL):
        revision = self.get_request(request_key)["revision"]
        with self.make_client() as client:
            return client.post(
                f"/api/projects/prj_alpha/role-requests/{request_key}/claim",
                headers={"X-API-Key": "bobo-key"},
                json={"host": host, "expected_revision": revision},
            )

    def create_role_via_api(self, request_key: str, lease_token: str):
        with self.make_client() as client:
            return client.post(
                "/api/projects/prj_alpha/roles",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "role_name": "dev",
                    "runner_id": RUNNER_ID,
                    "choice_id": self.choice_id,
                    "operation_key": request_key,
                    "lease_token": lease_token,
                },
            )

    def force_lease_expired(self, request_key: str) -> None:
        with self.session() as session:
            row = session.get(RoleProvisionRequestRow, request_key)
            assert row is not None
            row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
            session.add(row)
            session.commit()

    def role_count(self) -> int:
        with self.session() as session:
            return len(list(session.exec(select(ProjectRole)).all()))

    def role_api_key(self, member_id: str) -> str:
        with self.session() as session:
            member = session.get(Member, member_id)
            assert member is not None
            return str(member.api_key)

    # ── worker 夹具 ──────────────────────────────────────────────────

    def make_worker(self, **overrides) -> RoleProvisionWorker:
        kwargs = {
            "project_id": "prj_alpha",
            "host_label": HOST_LABEL,
            "base_url": "http://127.0.0.1:8000",
            "project_root": self.project_root,
            "key_root": self.key_root,
            "transport": self.transport,
            "enabled": True,
            "apply": True,
            "environ": self.environ,
        }
        kwargs.update(overrides)
        return RoleProvisionWorker(**kwargs)

    def key_file(self, member_id: str) -> Path:
        return rp.key_file_path(self.key_root, member_id)

    def metadata_file(self, member_id: str) -> Path:
        return rp.credential_metadata_path(self.key_root, member_id)

    def assert_key_root_empty(self) -> None:
        self.assertEqual(list(self.key_root.iterdir()), [])


# ---------------------------------------------------------------------------
# 默认关闭 / 只读计划
# ---------------------------------------------------------------------------


class DisabledAndPlanTests(WorkerTestCase):
    def test_disabled_worker_is_zero_http_and_zero_write(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker(
            enabled=False, apply=True, transport=_RecordingTransport(self)
        )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            document = worker.serve(once=True)
        self.assertEqual(document["mode"], "disabled")
        self.assertEqual(document["outcomes"][0]["error_code"], "worker_disabled")
        self.assert_key_root_empty()
        self.assertEqual(self.role_count(), 0)

    def test_default_apply_false_only_reads_a_plan(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        before = self.get_request("op-intent-0001")
        worker = self.make_worker(apply=False)
        document = worker.serve(once=True)
        self.assertEqual(document["mode"], "dry-run")
        planned = document["outcomes"][0]
        self.assertEqual(planned["count"], 1)
        self.assertEqual(planned["requests"][0]["request_key"], "op-intent-0001")
        after = self.get_request("op-intent-0001")
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["status"], "requested")
        self.assert_key_root_empty()
        self.assertNotIn("POST", " ".join(self.transport.calls))

    def test_disabled_project_host_yields_no_claimable_request(self):
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        self.assertEqual(worker.run_round(), [])
        self.assert_key_root_empty()
        self.assertEqual(self.role_count(), 0)


# ---------------------------------------------------------------------------
# 回环 / 重定向守卫
# ---------------------------------------------------------------------------


class TransportGuardTests(WorkerTestCase):
    def test_non_loopback_base_url_refused_before_any_credentials(self):
        self.assertIsNone(loopback_host("http://10.0.0.5:8000"))
        self.assertIsNone(loopback_host("http://0.0.0.0:8000"))
        self.assertIsNone(loopback_host("ftp://127.0.0.1:8000"))
        self.assertEqual(loopback_host("http://127.0.0.1:8000"), "127.0.0.1")
        with self.assertRaises(WorkerError) as ctx:
            assert_loopback_base_url("http://10.0.0.5:8000")
        self.assertEqual(ctx.exception.code, "worker_base_url_not_loopback")
        with self.assertRaises(WorkerError):
            RoleProvisionWorker(
                project_id="prj_alpha",
                host_label=HOST_LABEL,
                base_url="http://192.168.1.9:8000",
                project_root=self.project_root,
                key_root=self.key_root,
                enabled=True,
                apply=True,
            )
        # 定向请求到异机 URL 也在发任何内容之前拒绝。
        transport = WorkerTransport("http://127.0.0.1:8000")
        with self.assertRaises(WorkerError) as ctx:
            transport.request_json("GET", "http://192.168.1.9:8000/api/members/me")
        self.assertEqual(ctx.exception.code, "worker_base_url_not_loopback")

    def test_cross_host_redirect_is_refused_and_same_host_drops_credentials(self):
        handler = _LoopbackRedirectHandler("127.0.0.1")
        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/x", headers={"X-API-Key": "secret-key"}
        )
        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(
                request, None, 302, "Found", {}, "http://192.168.1.9:8000/api/x"
            )
        followed = handler.redirect_request(
            request, None, 302, "Found", {}, "http://127.0.0.1:8000/api/y"
        )
        self.assertIsNotNone(followed)
        self.assertIsNone(followed.get_header("X-api-key"))


# ---------------------------------------------------------------------------
# 正向闭环
# ---------------------------------------------------------------------------


class CreateLoopTests(WorkerTestCase):
    def test_full_create_loop_writes_real_files_and_reports_provisioned(self):
        self.assertEqual(self.enable_host().status_code, 200)
        self.assertEqual(self.create_intent("op-intent-0001").status_code, 201)
        worker = self.make_worker()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = worker.process("op-intent-0001")

        self.assertEqual(result["outcome"], "provisioned", result)
        self.assertIsNone(result["error_code"])
        self.assertEqual(result["kind"], "create")
        for step in ("profile", "key_file", "preflight"):
            self.assertIn(
                result["steps"][step]["state"], ("succeeded", "skipped"), result["steps"]
            )

        request = self.get_request("op-intent-0001")
        self.assertEqual(request["status"], "provisioned")
        self.assertEqual(request["member_id"], result["member_id"])
        member_id = result["member_id"]

        # 真实私有 Key 文件：内容等于服务端签发的一次性 Key，权限私有。
        key_path = self.key_file(member_id)
        self.assertTrue(key_path.is_file())
        self.assertEqual(rp._read_key_file(key_path), self.role_api_key(member_id))
        if os.name == "nt":
            # Windows：真实验证最终 Key 文件的私有 DACL（失败即 not_run/fail，不退回宽权限）。
            acl_ok, acl_detail = rp._windows_verify_private_acl(key_path)
            self.assertTrue(acl_ok, acl_detail)

        # 真实元数据：只含 member/version/source/intent/时间，不含 Key。
        metadata = rp.read_credential_metadata(self.key_root, member_id)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["member_id"], member_id)
        self.assertEqual(metadata["credential_version"], 1)
        self.assertEqual(metadata["source"], "create")
        raw = self.metadata_file(member_id).read_text(encoding="utf-8")
        self.assertNotIn(self.role_api_key(member_id), raw)
        self.assertNotIn("api_key", raw)

        # 真实身份档三步文件。
        agents_root = self.project_root / ".talk" / "agents"
        for name in ("IDENTITY.md", "SOUL.md", "USER.md"):
            self.assertTrue(list(agents_root.rglob(name)), name)

        # 没有启动任何服务进程：request 投影里服务仍是未启动。
        self.assertIsNone(request["provision_job"]["resume_of"])

    def test_second_run_is_noop_and_explicit_recover_continuation(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        first = worker.process("op-intent-0001")
        self.assertEqual(first["outcome"], "provisioned", first)
        member_id = first["member_id"]

        # 重复处理：请求已终态，不重新 claim，写零副作用。
        second = worker.process("op-intent-0001")
        self.assertEqual(second["outcome"], "skipped")
        self.assertEqual(second["error_code"], "role_request_lease_conflict")

        # 一次显式 recover：本机 Key 仍有效 → 续跑、不轮换、不重取旧 Key。
        version_before = self.get_request("op-intent-0001")["credential_version"]
        created = self.create_intent(
            "op-recover-0001",
            kind="recover",
            member_id=member_id,
            expected_credential_version=version_before,
            role_name=None,
            runner_id=None,
            choice_id=None,
        )
        self.assertEqual(created.status_code, 201, created.text)
        recovered = worker.process("op-recover-0001")
        self.assertEqual(recovered["outcome"], "provisioned", recovered)
        self.assertIsNone(recovered.get("rotation"))
        self.assertEqual(
            self.get_request("op-recover-0001")["credential_version"], version_before
        )


# ---------------------------------------------------------------------------
# 负向：资格/租约/恢复
# ---------------------------------------------------------------------------


class RefusalTests(WorkerTestCase):
    def test_wrong_host_label_is_refused_and_writes_nothing(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker(host_label="another-host")
        result = worker.process("op-intent-0001")
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "role_request_host_mismatch")
        self.assert_key_root_empty()
        self.assertEqual(self.role_count(), 0)
        self.assertEqual(self.get_request("op-intent-0001")["status"], "requested")

    def test_config_generation_change_invalidates_old_lease(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        claimed = self.claim_request("op-intent-0001").json()
        self.disable_host(expected_version=1)
        self.enable_host(expected_version=2)
        created = rp.create_role_for_request(
            transport=self.transport,
            base_url="http://127.0.0.1:8000",
            project_id="prj_alpha",
            payload=claimed["payload"],
            request_key="op-intent-0001",
            lease_token=claimed["lease_token"],
            operator_key="bobo-key",
            timeout=15.0,
        )
        self.assertEqual(created["status"], 409)
        self.assertEqual(created["error_code"], "role_request_lease_invalid")
        self.assertEqual(self.role_count(), 0)
        self.assert_key_root_empty()

    def test_created_with_lost_response_needs_human_recovery(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        claimed = self.claim_request("op-intent-0001").json()
        created = self.create_role_via_api("op-intent-0001", claimed["lease_token"])
        self.assertEqual(created.status_code, 201)
        member_id = created.json()["member_id"]
        self.force_lease_expired("op-intent-0001")

        worker = self.make_worker()
        result = worker.process("op-intent-0001")
        self.assertEqual(result["outcome"], "reported")
        self.assertEqual(result["error_code"], "manual_recovery_required")
        self.assertEqual(self.get_request("op-intent-0001")["status"], "failed")
        # 不重取旧 Key、不轮换：本机没有 Key 文件，服务端版本保持 1。
        self.assertFalse(self.key_file(member_id).exists())
        self.assertEqual(self.get_request("op-intent-0001")["credential_version"], 1)

    def test_recover_rotation_replay_without_local_key_needs_human_recovery(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        first = worker.process("op-intent-0001")
        self.assertEqual(first["outcome"], "provisioned", first)
        member_id = first["member_id"]

        recover_key = "op-recover-0001"
        created = self.create_intent(
            recover_key,
            kind="recover",
            member_id=member_id,
            expected_credential_version=1,
            role_name=None,
            runner_id=None,
            choice_id=None,
        )
        self.assertEqual(created.status_code, 201, created.text)

        # 模拟「轮换已提交但 201 响应丢失」：手工领取并轮换一次（丢弃一次性 Key）。
        stale_key = rp._read_key_file(self.key_file(member_id))
        claimed = self.claim_request(recover_key).json()
        rotation = rp.rotate_role_key_for_request(
            transport=self.transport,
            base_url="http://127.0.0.1:8000",
            project_id="prj_alpha",
            member_id=member_id,
            request_key=recover_key,
            lease_token=claimed["lease_token"],
            expected_credential_version=1,
            operator_key="bobo-key",
            timeout=15.0,
        )
        self.assertEqual(rotation["status"], 201)
        self.assertTrue(rotation["api_key"])
        # 本机旧 Key 已失效，但**未被**覆盖成交付前的新 Key（响应丢失即未落盘）。
        self.assertEqual(rp._read_key_file(self.key_file(member_id)), stale_key)
        self.assertEqual(self.get_request(recover_key)["credential_version"], 2)

        # 旧租约失联后重领：同意图再次轮换只拿 200 reused，不返 Key；本机仍无有效 Key
        # → 需人类**新意图**，绝不自动再次轮换。
        self.force_lease_expired(recover_key)
        replay = worker.process(recover_key)
        self.assertEqual(replay["outcome"], "reported", replay)
        self.assertEqual(replay["error_code"], "manual_recovery_required")
        self.assertEqual(replay["rotation"]["reused"], True)
        self.assertEqual(self.get_request(recover_key)["credential_version"], 2)
        self.assertEqual(rp._read_key_file(self.key_file(member_id)), stale_key)

    def test_cancelled_request_refuses_later_writes(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        claimed = self.claim_request("op-intent-0001").json()
        revision = self.get_request("op-intent-0001")["revision"]
        with self.make_client() as client:
            cancelled = client.post(
                "/api/projects/prj_alpha/role-requests/op-intent-0001/cancel",
                headers={"X-API-Key": "bobo-key"},
                json={"expected_revision": revision},
            )
        self.assertEqual(cancelled.status_code, 200)
        created = rp.create_role_for_request(
            transport=self.transport,
            base_url="http://127.0.0.1:8000",
            project_id="prj_alpha",
            payload=claimed["payload"],
            request_key="op-intent-0001",
            lease_token=claimed["lease_token"],
            operator_key="bobo-key",
            timeout=15.0,
        )
        self.assertEqual(created["status"], 409)
        self.assertEqual(self.role_count(), 0)
        self.assert_key_root_empty()
        worker = self.make_worker()
        self.assertEqual(worker.process("op-intent-0001")["outcome"], "skipped")

    def test_recover_checks_local_key_under_role_lock(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        first = worker.process("op-intent-0001")
        self.assertEqual(first["outcome"], "provisioned", first)
        member_id = first["member_id"]
        self.create_intent(
            "op-recover-0001",
            kind="recover",
            member_id=member_id,
            expected_credential_version=1,
            role_name=None,
            runner_id=None,
            choice_id=None,
        )
        original = rp.acquire_provision_locks
        order: list[str] = []

        def recording(*args, **kwargs):
            order.append("locked")
            return original(*args, **kwargs)

        with patch("scripts.role_provision_worker.acquire_provision_locks", side_effect=recording):
            recovered = worker.process("op-recover-0001")
        self.assertEqual(order, ["locked"])
        self.assertEqual(recovered["outcome"], "provisioned", recovered)
        # 本机 Key 仍有效 → 不轮换、不重取旧 Key。
        self.assertIsNone(recovered.get("rotation"))
        self.assertEqual(rp._read_key_file(self.key_file(member_id)), self.role_api_key(member_id))

    def test_duplicate_target_lock_is_mutually_exclusive(self):
        target = rp.key_file_path(self.key_root, "agent:locked")
        lock_path = rp.lock_path_for(target)
        first = rp.acquire_lock(lock_path, 900.0)
        try:
            with self.assertRaises(rp.ProvisionError) as ctx:
                rp.acquire_lock(lock_path, 900.0)
            self.assertEqual(ctx.exception.code, "provision_lock_busy")
        finally:
            rp.release_lock(lock_path, first)
        third = rp.acquire_lock(lock_path, 900.0)
        rp.release_lock(lock_path, third)

    def test_unknown_old_key_file_is_not_overwritten(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        member_id = "agent:foreign-target"
        # 预置一个来源不明的旧 Key 文件（无元数据）→ 专用替换必须拒绝。
        rp._write_key_file(self.key_file(member_id), "foreign-old-key")
        worker = self.make_worker()
        with self.assertRaises(WorkerError) as ctx:
            worker.publish_key(
                member_id,
                SENTINEL_ROLE_KEY,
                source="create",
                request_key="op-intent-0001",
                kind="create",
                credential_version=1,
                expected_old_version=None,
            )
        self.assertEqual(ctx.exception.code, "role_key_foreign_refused")
        self.assertEqual(rp._read_key_file(self.key_file(member_id)), "foreign-old-key")

    def test_known_old_generation_allows_dedicated_replacement(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        member_id = "agent:known-old"
        # 本人已知旧代：Key 文件 + 元数据版本 3。
        rp._write_key_file(self.key_file(member_id), SENTINEL_ROLE_KEY)
        rp.write_credential_metadata(
            self.key_root, member_id, credential_version=3, source="create",
            intent="op-intent-0001", intent_kind="create",
        )
        worker = self.make_worker()
        result = worker.publish_key(
            member_id,
            "new-role-key-after-rotation",
            source="recover",
            request_key="op-recover-0001",
            kind="recover",
            credential_version=4,
            expected_old_version=3,
        )
        self.assertTrue(result["key_published"])
        self.assertIsNone(result["error_code"])
        self.assertEqual(
            rp._read_key_file(self.key_file(member_id)), "new-role-key-after-rotation"
        )
        self.assertEqual(
            rp.read_credential_metadata(self.key_root, member_id)["credential_version"], 4
        )

        # 未知旧代（元数据版本不匹配）拒绝覆盖，旧文件保持原样。
        with self.assertRaises(WorkerError) as ctx:
            worker.publish_key(
                member_id,
                "another-key",
                source="recover",
                request_key="op-recover-0002",
                kind="recover",
                credential_version=5,
                expected_old_version=99,
            )
        self.assertEqual(ctx.exception.code, "role_key_foreign_refused")
        self.assertEqual(
            rp._read_key_file(self.key_file(member_id)), "new-role-key-after-rotation"
        )


# ---------------------------------------------------------------------------
# 负向：Key/元数据、预检、锁、停止、spawn
# ---------------------------------------------------------------------------


class KeyAndStepTests(WorkerTestCase):
    def test_key_published_metadata_failure_keeps_key_and_repairs_next_run(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        claimed = self.claim_request("op-intent-0001").json()
        created = self.create_role_via_api("op-intent-0001", claimed["lease_token"])
        self.assertEqual(created.status_code, 201)
        member_id = created.json()["member_id"]
        api_key = created.json()["api_key"]
        with patch(
            "scripts.role_provision_worker.write_credential_metadata",
            side_effect=rp.ProvisionError("key_provenance_write_failed"),
        ):
            published = worker.publish_key(
                member_id,
                api_key,
                source="create",
                request_key="op-intent-0001",
                kind="create",
                credential_version=1,
                expected_old_version=None,
            )
        self.assertEqual(published["error_code"], "key_provenance_write_failed")
        self.assertTrue(self.key_file(member_id).is_file())
        self.assertEqual(rp._read_key_file(self.key_file(member_id)), api_key)
        self.assertFalse(self.metadata_file(member_id).exists())

        # Key 已发布：下一次以本人当前 Key 认证 + 服务端当前版本修复元数据（不再轮换）。
        error = worker.repair_metadata(
            member_id, request_key="op-intent-0001", kind="create", server_version=1
        )
        self.assertIsNone(error)
        metadata = rp.read_credential_metadata(self.key_root, member_id)
        self.assertEqual(metadata["credential_version"], 1)
        self.assertEqual(metadata["source"], "existing_key")

    def test_preflight_failure_is_not_reported_as_success(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        original = rp.run_request_provision

        def forced(**kwargs):
            document, code = original(**kwargs)
            document["steps"]["preflight"] = {
                "state": "failed",
                "attempts": 1,
                "error_code": "preflight_failed",
                "detail": "forced",
            }
            document["conclusion"] = "partial"
            document["error_code"] = "preflight_failed"
            return document, 1

        with patch(
            "scripts.role_provision_worker.run_request_provision", side_effect=forced
        ):
            result = worker.process("op-intent-0001")
        self.assertEqual(result["outcome"], "reported")
        self.assertEqual(result["error_code"], "preflight_failed")
        request = self.get_request("op-intent-0001")
        self.assertEqual(request["status"], "failed")
        self.assertEqual(request["last_error_code"], "preflight_failed")

    def test_lost_ack_is_reread_and_retried_without_faking_success(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        transport = _FlakyAckTransport(self, fail_times=1)
        worker = self.make_worker(transport=transport)
        result = worker.process("op-intent-0001")
        self.assertEqual(result["outcome"], "provisioned", result)
        self.assertEqual(transport.remaining, 0)
        self.assertEqual(self.get_request("op-intent-0001")["status"], "provisioned")
        for step in ("profile", "key_file", "preflight"):
            self.assertIn(result["steps"][step]["state"], ("succeeded", "skipped"))

    def test_target_lock_busy_is_reported_stably(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        original = rp.acquire_lock
        calls = {"n": 0}

        def guarded(lock_path, stale_seconds=900.0):
            calls["n"] += 1
            if calls["n"] == 2:  # 第二把（Key 目标锁）模拟被另一个 worker 持有
                raise rp.ProvisionError("provision_lock_busy", "锁由并发执行持有")
            return original(lock_path, stale_seconds)

        with patch("scripts.role_provision.acquire_lock", side_effect=guarded):
            result = worker.process("op-intent-0001")
        self.assertEqual(result["outcome"], "reported")
        self.assertEqual(result["error_code"], "provision_lock_busy")
        self.assertEqual(self.get_request("op-intent-0001")["status"], "failed")

    def test_stop_request_is_stage_bounded(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        worker.request_stop()
        result = worker.process("op-intent-0001")
        self.assertEqual(result["outcome"], "stopped")
        self.assertEqual(result["error_code"], "worker_stopped")
        self.assert_key_root_empty()

    def test_worker_never_spawns_and_holds_no_popen_ownership(self):
        source = Path(
            __import__("scripts.role_provision_worker", fromlist=["x"]).__file__
        ).read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertFalse(hasattr(RoleProvisionWorker, "execute_start"))
        self.assertFalse(hasattr(RoleProvisionWorker, "_handles"))
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        with patch("subprocess.Popen", side_effect=AssertionError("must not spawn")):
            result = worker.process("op-intent-0001")
        self.assertEqual(result["outcome"], "provisioned", result)


# ---------------------------------------------------------------------------
# R1-3 集成 / 输出安全
# ---------------------------------------------------------------------------


class _ExplodingWorker:
    def run_round(self):
        raise TimeoutError("config IO timeout")


class HostIntegrationTests(WorkerTestCase):
    def test_worker_timeout_does_not_block_service_control_loop(self):
        client = TalkHostClient("http://127.0.0.1:8000", "bobo-key")
        manager = HostManager(
            client,
            host=HOST_LABEL,
            state_dir=self._tmpdir / "host-state",
            operator_key="bobo-key",
            project_root=self.project_root,
        )
        with patch.object(manager, "claimable_actions", return_value=[]):
            outcomes = manager.serve(
                "prj_alpha", once=True, provision_worker=_ExplodingWorker()
            )
        self.assertTrue(
            any(
                item.get("action") == "provision-worker"
                and item.get("outcome") == "failed"
                for item in outcomes
            ),
            outcomes,
        )

    def test_worker_outcomes_are_whitelisted_public_output(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        result = worker.process("op-intent-0001")
        self.assertTrue(set(result) <= PUBLIC_KEYS, set(result) - PUBLIC_KEYS)
        self.assertNotIn("lease_token", json.dumps(result))
        self.assertNotIn("api_key", json.dumps(result))

    def test_secret_sentinels_never_leak_into_outputs(self):
        self.enable_host()
        self.create_intent("op-intent-0001")
        worker = self.make_worker()
        captured: dict[str, str] = {}
        original_claim = worker.claim

        def recording_claim(request_key, expected_revision):
            claimed = original_claim(request_key, expected_revision)
            captured["token"] = str(claimed.get("lease_token"))
            return claimed

        stream = io.StringIO()
        with patch.object(worker, "claim", side_effect=recording_claim):
            with redirect_stdout(stream), redirect_stderr(stream):
                result = worker.process("op-intent-0001")
        member_id = result["member_id"]
        role_key = self.role_api_key(member_id)
        serialized = json.dumps(result, ensure_ascii=False) + stream.getvalue()
        self.assertNotIn(captured["token"], serialized)
        self.assertNotIn(role_key, serialized)
        self.assertNotIn(SENTINEL_ROLE_KEY, serialized)
        self.assertNotIn("bobo-key", serialized)
        # argv：CLI 没有明文 Key 通道；env：角色 Key 绝不进环境变量。
        option_strings = {
            option
            for action in rpw.build_parser()._actions
            for option in action.option_strings
        }
        self.assertNotIn("--operator-key", option_strings)
        self.assertIn("--operator-key-file", option_strings)
        environment = " ".join(f"{k}={v}" for k, v in os.environ.items())
        self.assertNotIn(role_key, environment)
        self.assertNotIn(captured["token"], environment)
        self.assertNotIn(role_key, " ".join(self.transport.calls))
        self.assertNotIn(captured["token"], " ".join(self.transport.calls))
        self.assertEqual(result["outcome"], "provisioned", result)


# ---------------------------------------------------------------------------
# R1-4b 返修 F1/F2/F5：宿主接线、独立受控执行、统一轮次形状
# ---------------------------------------------------------------------------


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ReworkHostWiringTests(WorkerTestCase):
    """宿主接线必须与 worker 自身同语义：关闭零 HTTP，只读零 claim/零写。"""

    def host_manager(self) -> HostManager:
        client = TalkHostClient("http://127.0.0.1:8000", "bobo-key")
        return HostManager(
            client,
            host=HOST_LABEL,
            state_dir=self._tmpdir / "host-state",
            operator_key="bobo-key",
            project_root=self.project_root,
        )

    def test_host_wiring_disabled_worker_is_zero_http_and_zero_write(self):
        self.enable_host()
        self.create_intent("op-rework-disabled")
        worker = self.make_worker(enabled=False, transport=_RecordingTransport(self))
        manager = self.host_manager()
        with patch.object(manager, "claimable_actions", return_value=[]):
            outcomes = manager.serve("prj_alpha", once=True, provision_worker=worker)
        self.assertEqual(self.role_count(), 0)
        self.assert_key_root_empty()
        self.assertEqual(self.get_request("op-rework-disabled")["status"], "requested")
        self.assertTrue(
            any(
                item.get("action") == "provision-worker"
                and item.get("error_code") == "worker_disabled"
                for item in outcomes
            ),
            outcomes,
        )

    def test_host_wiring_read_only_never_claims_or_writes(self):
        self.enable_host()
        self.create_intent("op-rework-plan")
        before = self.get_request("op-rework-plan")
        worker = self.make_worker(apply=False)
        manager = self.host_manager()
        with patch.object(manager, "claimable_actions", return_value=[]):
            outcomes = manager.serve("prj_alpha", once=True, provision_worker=worker)
        after = self.get_request("op-rework-plan")
        self.assertEqual(self.role_count(), 0)
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["status"], "requested")
        self.assert_key_root_empty()
        self.assertNotIn("POST", " ".join(self.transport.calls))
        self.assertTrue(
            any(
                item.get("action") == "provision-worker"
                and item.get("outcome") == "planned"
                for item in outcomes
            ),
            outcomes,
        )

    def test_slow_real_worker_does_not_block_control_loop_stop(self):
        self.enable_host()
        self.create_intent("op-rework-slow")
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
        worker = self.make_worker()
        original_claim = worker.claim

        def slow_claim(request_key, expected_revision):
            entered.set()
            release.wait(10)
            return original_claim(request_key, expected_revision)

        def fast_detail(_request_key):
            # 只绕开 TestClient 首次启动延迟，让「慢」精确落在 claim 这一步。
            return {
                "request_key": "op-rework-slow",
                "kind": "create",
                "status": "requested",
                "revision": 1,
                "member_id": None,
                "claimable": True,
            }

        manager = self.host_manager()

        def actions(_project_id):
            return (
                [{"action": "stop", "member_id": "agent:isolated"}]
                if entered.is_set()
                else []
            )

        def fake_stop(_action):
            stopped.set()
            return {"action": "stop", "outcome": "stopped"}

        errors: list[str] = []

        def serve():
            try:
                manager.serve(
                    "prj_alpha",
                    poll_interval=0.01,
                    max_rounds=5,
                    provision_worker=worker,
                )
            except Exception as exc:  # noqa: BLE001 - 测试只关心是否外抛
                errors.append(type(exc).__name__)

        with (
            patch.object(worker, "claim", side_effect=slow_claim),
            patch.object(worker, "get_request", side_effect=fast_detail),
            patch.object(manager, "claimable_actions", side_effect=actions),
            patch.object(manager, "execute_stop", side_effect=fake_stop),
        ):
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            try:
                self.assertTrue(entered.wait(3), "worker never entered the slow call")
                received_before_release = stopped.wait(0.5)
            finally:
                release.set()
                thread.join(20)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(
            received_before_release, "control-loop stop was blocked by the slow worker"
        )

    def test_run_round_shapes_and_exit_codes_are_uniform(self):
        worker = self.make_worker()
        with patch.object(worker, "list_claimable", side_effect=WorkerError("http_error")):
            failed = worker.run_round()
        self.assertIsInstance(failed, list)
        self.assertEqual(failed[0]["error_code"], "http_error")
        self.assertEqual(failed[0]["outcome"], "failed")

        stopped = self.make_worker()
        stopped.request_stop()
        self.assertEqual(
            [item["outcome"] for item in stopped.run_round()], ["stopped"]
        )

        disabled = self.make_worker(enabled=False, transport=_RecordingTransport(self))
        self.assertEqual(
            [item["error_code"] for item in disabled.run_round()], ["worker_disabled"]
        )

        # 边界收敛：历史 dict 返回值不再被按键名遍历，字符串不再被拆成字符列表。
        self.assertEqual(len(coerce_outcomes({"outcome": "failed"})), 1)
        self.assertEqual(coerce_outcomes("failed")[0]["error_code"], "http_error")
        self.assertEqual(coerce_outcomes(None), [])


class ReworkExitCodeTests(WorkerTestCase):
    """F5：CLI 退出码与错误形状必须保留。"""

    def test_worker_cli_returns_nonzero_for_failed_outcome(self):
        stream = io.StringIO()
        with (
            patch.object(
                rpw.RoleProvisionWorker,
                "serve",
                return_value={
                    "mode": "apply",
                    "outcomes": [{"outcome": "failed", "error_code": "http_error"}],
                },
            ),
            redirect_stdout(stream),
        ):
            code = rpw.main(
                ["--project", "prj_alpha", "--host", HOST_LABEL, "--enable", "--apply"]
            )
        self.assertEqual(code, 1)
        self.assertNotIn("lease_token", stream.getvalue())

    def test_host_cli_returns_nonzero_for_failed_worker_outcome(self):
        stream = io.StringIO()
        with (
            patch.object(
                role_service_host.HostManager,
                "serve",
                return_value=[
                    {
                        "action": "provision-worker",
                        "outcome": "failed",
                        "error_code": "http_error",
                    }
                ],
            ),
            patch.object(role_service_host, "load_operator_key", return_value="bobo-key"),
            redirect_stdout(stream),
        ):
            code = role_service_host.main(
                [
                    "serve",
                    "--project",
                    "prj_alpha",
                    "--state-dir",
                    str(self._tmpdir / "host-state-cli"),
                    "--project-root",
                    str(self.project_root),
                ]
            )
        self.assertEqual(code, 1)
        self.assertNotIn("bobo-key", stream.getvalue())

    def test_host_cli_does_not_advertise_a_plaintext_key_option(self):
        options = {
            option
            for action in role_service_host.build_arg_parser()._actions
            for option in action.option_strings
        }
        self.assertNotIn("--operator-key", options)
        self.assertIn("--operator-key-file", options)
        # F5：无效的新增选项必须删除，保留的轮次上限必须真正生效。
        self.assertNotIn("--provision-worker-poll-interval", options)
        self.assertIn("--provision-worker-max-rounds", options)
        self.assertNotIn("--json", {o for a in rpw.build_parser()._actions for o in a.option_strings})


# ---------------------------------------------------------------------------
# R1-4b 返修 F4：副作用前的租约/世代复查与新 Key 身份核验
# ---------------------------------------------------------------------------


class ReworkLeaseBoundaryTests(WorkerTestCase):
    def test_disable_after_create_stops_local_publication(self):
        self.enable_host()
        self.create_intent("op-rework-disable")
        case = self

        class DisableAfterCreate(_ClientTransport):
            fired = False

            def request_json(self, method, url, **kwargs):
                response = super().request_json(method, url, **kwargs)
                if (
                    method.upper() == "POST"
                    and url.endswith("/roles")
                    and response.status == 201
                    and not self.fired
                ):
                    self.fired = True
                    case.assertEqual(case.disable_host(expected_version=1).status_code, 200)
                return response

        worker = self.make_worker(transport=DisableAfterCreate(self))
        result = worker.process("op-rework-disable")
        request = self.get_request("op-rework-disable")
        self.assertIsNotNone(request["member_id"], "真实已创建成员必须保留")
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_code"], "role_request_lease_invalid")
        self.assertFalse((result.get("report") or {}).get("sent"))
        self.assertFalse(self.key_file(request["member_id"]).exists())
        self.assertFalse(self.metadata_file(request["member_id"]).exists())
        self.assertEqual(request["status"], "created")
        self.assert_key_root_empty()

    def test_expired_lease_after_create_stops_local_publication(self):
        self.enable_host()
        self.create_intent("op-rework-expire")
        case = self

        class ExpireAfterCreate(_ClientTransport):
            fired = False

            def request_json(self, method, url, **kwargs):
                response = super().request_json(method, url, **kwargs)
                if (
                    method.upper() == "POST"
                    and url.endswith("/roles")
                    and response.status == 201
                    and not self.fired
                ):
                    self.fired = True
                    case.force_lease_expired("op-rework-expire")
                return response

        worker = self.make_worker(transport=ExpireAfterCreate(self))
        result = worker.process("op-rework-expire")
        member_id = self.get_request("op-rework-expire")["member_id"]
        self.assertIsNotNone(member_id)
        self.assertEqual(result["error_code"], "role_request_lease_invalid")
        self.assertFalse(self.key_file(member_id).exists())
        self.assertFalse(self.metadata_file(member_id).exists())
        self.assert_key_root_empty()

    def test_config_generation_change_after_create_stops_publication(self):
        self.enable_host()
        self.create_intent("op-rework-generation")
        case = self

        class BumpAfterCreate(_ClientTransport):
            fired = False

            def request_json(self, method, url, **kwargs):
                response = super().request_json(method, url, **kwargs)
                if (
                    method.upper() == "POST"
                    and url.endswith("/roles")
                    and response.status == 201
                    and not self.fired
                ):
                    self.fired = True
                    case.assertEqual(case.disable_host(expected_version=1).status_code, 200)
                    case.assertEqual(case.enable_host(expected_version=2).status_code, 200)
                return response

        worker = self.make_worker(transport=BumpAfterCreate(self))
        result = worker.process("op-rework-generation")
        member_id = self.get_request("op-rework-generation")["member_id"]
        self.assertIsNotNone(member_id)
        self.assertEqual(result["error_code"], "role_request_lease_invalid")
        self.assertFalse(self.key_file(member_id).exists())
        self.assert_key_root_empty()

    def test_real_resume_invalidates_stale_claim_snapshot(self):
        """人工 resume 清掉旧资格后，worker 的只读复查必须拒绝继续本地工作。"""
        self.enable_host()
        self.create_intent("op-rework-resume")
        first = self.claim_request("op-rework-resume").json()
        self.force_lease_expired("op-rework-resume")
        self.claim_request("op-rework-resume")
        self.force_lease_expired("op-rework-resume")
        self.claim_request("op-rework-resume")
        self.force_lease_expired("op-rework-resume")
        revision = self.get_request("op-rework-resume")["revision"]
        with self.make_client() as client:
            resumed = client.post(
                "/api/projects/prj_alpha/role-requests/op-rework-resume/resume",
                headers={"X-API-Key": "bobo-key"},
                json={"expected_revision": revision, "confirm": True},
            )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["status"], "requested")

        worker = self.make_worker()
        with self.assertRaises(LeaseInvalidated) as ctx:
            worker._verify_lease("op-rework-resume", first)
        self.assertEqual(ctx.exception.code, "role_request_lease_invalid")
        self.assert_key_root_empty()

    def test_lease_invalidation_between_steps_refuses_ack(self):
        self.enable_host()
        self.create_intent("op-rework-mid")
        worker = self.make_worker()
        case = self

        def disabling_profile(**_kwargs):
            case.assertEqual(case.disable_host(expected_version=1).status_code, 200)
            return {
                "state": "succeeded",
                "attempts": 1,
                "error_code": None,
                "detail": "forced",
            }

        with patch(
            "scripts.role_provision._run_profile_step", side_effect=disabling_profile
        ):
            result = worker.process("op-rework-mid")
        request = self.get_request("op-rework-mid")
        self.assertEqual(result["outcome"], "failed", result)
        self.assertEqual(result["error_code"], "role_request_lease_invalid")
        self.assertFalse((result.get("report") or {}).get("sent"))
        self.assertEqual(request["status"], "created")
        self.assertNotIn("provisioned", json.dumps(request))

    def test_io_budget_expiry_refuses_ack_and_report(self):
        self.enable_host()
        self.create_intent("op-rework-budget")
        worker = self.make_worker(io_budget_seconds=1.0)

        def slow_profile(**_kwargs):
            time.sleep(1.5)
            return {
                "state": "succeeded",
                "attempts": 1,
                "error_code": None,
                "detail": "forced",
            }

        with patch("scripts.role_provision._run_profile_step", side_effect=slow_profile):
            result = worker.process("op-rework-budget")
        self.assertEqual(result["outcome"], "failed", result)
        self.assertEqual(result["error_code"], "worker_io_budget_exceeded")
        self.assertFalse((result.get("report") or {}).get("sent"))
        self.assertEqual(self.get_request("op-rework-budget")["status"], "created")

    def test_stage_cancel_between_steps_refuses_ack(self):
        self.enable_host()
        self.create_intent("op-rework-cancel")
        worker = self.make_worker()

        def cancelling_profile(**_kwargs):
            worker.cancel_stage()
            return {
                "state": "succeeded",
                "attempts": 1,
                "error_code": None,
                "detail": "forced",
            }

        with patch(
            "scripts.role_provision._run_profile_step", side_effect=cancelling_profile
        ):
            result = worker.process("op-rework-cancel")
        self.assertEqual(result["outcome"], "stopped", result)
        self.assertEqual(result["error_code"], "worker_stopped")
        self.assertNotIn("ack", result)
        self.assertEqual(self.get_request("op-rework-cancel")["status"], "created")

    def test_new_key_identity_is_verified_before_publication(self):
        self.enable_host()
        self.create_intent("op-rework-identity")
        worker = self.make_worker()

        def mismatching(*_args, **_kwargs):
            return "mismatch", "agent:someone-else"

        with patch("scripts.role_provision_worker._role_key_verdict", side_effect=mismatching):
            result = worker.process("op-rework-identity")
        self.assertEqual(result["error_code"], "identity_mismatch")
        self.assertIn(result["outcome"], ("failed", "reported"))
        member_id = self.get_request("op-rework-identity")["member_id"]
        self.assertIsNotNone(member_id)
        self.assertFalse(self.key_file(member_id).exists(), "未核验的新 Key 不得发布")
        self.assertFalse(self.metadata_file(member_id).exists())
        self.assert_key_root_empty()


# ---------------------------------------------------------------------------
# 隔离真实回环 HTTP：临时 uvicorn + WorkerTransport 端到端（F3/F4/传输守卫）
# ---------------------------------------------------------------------------


class _HeaderRecorder(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server 约定名
        self.server.seen_headers.append(dict(self.headers))  # type: ignore[attr-defined]
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D102 - 测试里静音
        return


class _Redirector(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server 约定名
        self.send_response(302)
        self.send_header("Location", self.server.target_url)  # type: ignore[attr-defined]
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):  # noqa: D102 - 测试里静音
        return


def _start_http_server(handler) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server._talk_thread = thread  # type: ignore[attr-defined]
    return server


class RequestIoBoundaryTests(WorkerTestCase):
    """帮助函数内部的后续请求也遵守取消/预算，已上报的业务失败仍非零退出。"""

    def failed_document(self):
        self.enable_host()
        self.create_intent("op-cli-real-failure")
        worker = self.make_worker()
        with patch.object(
            rp, "_run_preflight_step",
            return_value=rp._step(rp.STATE_FAILED, 1, "preflight_failed", "isolated prerequisite unavailable"),
        ):
            document = worker.serve(once=True)
        self.assertEqual(self.get_request("op-cli-real-failure")["status"], "failed")
        self.assertEqual(document["outcomes"][0]["outcome"], "reported")
        return document

    def test_worker_cli_fails_after_real_failed_report(self):
        document = self.failed_document()
        stream = io.StringIO()
        with patch.object(rpw.RoleProvisionWorker, "serve", return_value=document), redirect_stdout(stream):
            code = rpw.main(["--project", "prj_alpha", "--enable", "--apply", "--once"])
        self.assertEqual(code, rpw.EXIT_FAILED)
        self.assertNotIn("bobo-key", stream.getvalue())

    def test_host_cli_fails_after_real_failed_report(self):
        document = self.failed_document()
        stream = io.StringIO()
        with (
            patch.object(role_service_host.HostManager, "serve", return_value=document["outcomes"]),
            patch.object(role_service_host, "load_operator_key", return_value="bobo-key"),
            redirect_stdout(stream),
        ):
            code = role_service_host.main([
                "serve", "--project", "prj_alpha", "--state-dir", str(self._tmpdir / "host-cli-state"),
                "--project-root", str(self.project_root),
            ])
        self.assertEqual(code, role_service_host.EXIT_FAILED)
        self.assertNotIn("bobo-key", stream.getvalue())

    def mid_request(self, mode):
        self.enable_host()
        self.create_intent("op-mid-request-boundary")
        now = [0.0]
        worker = None

        class MidStepTransport(_ClientTransport):
            triggered = False

            def __init__(self, case):
                super().__init__(case)
                self.after = []

            def request_json(self, method, url, **kwargs):
                if self.triggered:
                    self.after.append(method)
                response = super().request_json(method, url, **kwargs)
                if not self.triggered and method == "GET" and url.endswith("/projects/prj_alpha/agents"):
                    self.triggered = True
                    if mode == "cancel":
                        worker.cancel_stage()
                    else:
                        now[0] = 100.0
                return response

        transport = MidStepTransport(self)
        worker = self.make_worker(transport=transport, clock=lambda: now[0], io_budget_seconds=10)
        result = worker.process("op-mid-request-boundary")
        self.assertTrue(transport.triggered)
        self.assertEqual(transport.after, [])
        self.assertEqual(self.get_request("op-mid-request-boundary")["status"], "created")
        self.assertEqual(result["outcome"], "stopped" if mode == "cancel" else "failed")

    def test_cancel_during_preflight_stops_roster_registration(self):
        self.mid_request("cancel")

    def test_budget_expiry_during_preflight_stops_roster_registration(self):
        self.mid_request("budget")

    def mid_ack(self, mode):
        self.enable_host()
        self.create_intent("op-mid-ack-boundary")
        now = [0.0]
        worker = None

        class MidAckTransport(_ClientTransport):
            def __init__(self, case):
                super().__init__(case)
                self.triggered = False
                self.after = []

            def request_json(self, method, url, **kwargs):
                if self.triggered:
                    self.after.append(method)
                response = super().request_json(method, url, **kwargs)
                if not self.triggered and method == "POST" and url.endswith("/provision/ack"):
                    self.triggered = True
                    if mode == "cancel":
                        worker.cancel_stage()
                    else:
                        now[0] = 100.0
                return response

        transport = MidAckTransport(self)
        worker = self.make_worker(transport=transport, clock=lambda: now[0], io_budget_seconds=10)
        result = worker.process("op-mid-ack-boundary")
        self.assertTrue(transport.triggered)
        self.assertEqual(transport.after, [])
        self.assertEqual(self.get_request("op-mid-ack-boundary")["status"], "created")
        self.assertEqual(result["outcome"], "stopped" if mode == "cancel" else "failed")

    def test_cancel_after_first_ack_stops_remaining_acks(self):
        self.mid_ack("cancel")

    def test_budget_expiry_after_first_ack_stops_remaining_acks(self):
        self.mid_ack("budget")


class ReworkLiveLoopbackTests(WorkerTestCase):
    """真实回环 HTTP + 真实 ``WorkerTransport``：本测试自带临时 uvicorn，不跑生产配置。"""

    def setUp(self):
        super().setUp()
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(
            main.app,
            host="127.0.0.1",
            port=self.port,
            log_level="critical",
            lifespan="on",
        )
        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(target=self.server.run, daemon=True)
        self.server_thread.start()
        self._wait_live_server()

    def tearDown(self):
        self.server.should_exit = True
        self.server_thread.join(timeout=20)
        super().tearDown()

    def _wait_live_server(self):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.1)
        raise AssertionError("隔离 uvicorn 服务未能在 20 秒内启动")

    def live_worker(self, **overrides) -> RoleProvisionWorker:
        kwargs = {
            "project_id": "prj_alpha",
            "host_label": HOST_LABEL,
            "base_url": self.base_url,
            "project_root": self.project_root,
            "key_root": self.key_root,
            "enabled": True,
            "apply": True,
            "operator_key": "bobo-key",
            "environ": {},
            "timeout_seconds": 15.0,
        }
        kwargs.update(overrides)
        return RoleProvisionWorker(**kwargs)

    def test_real_loopback_worker_transport_full_create_ack_report(self):
        self.enable_host()
        self.create_intent("op-live-0001")
        worker = self.live_worker()
        self.assertIsInstance(worker.transport, WorkerTransport)
        result = worker.process("op-live-0001")
        self.assertEqual(result["outcome"], "provisioned", result)
        self.assertIsNone(result["error_code"])
        self.assertTrue(result["ack"]["sent"], result)
        for step in ("profile", "key_file", "preflight"):
            self.assertIn(result["steps"][step]["state"], ("succeeded", "skipped"))

        request = self.get_request("op-live-0001")
        self.assertEqual(request["status"], "provisioned")
        member_id = request["member_id"]
        self.assertEqual(result["member_id"], member_id)
        key_path = self.key_file(member_id)
        self.assertTrue(key_path.is_file(), "真实回环传输必须落盘私有 Key")
        self.assertEqual(rp._read_key_file(key_path), self.role_api_key(member_id))
        if os.name == "nt":
            acl_ok, acl_detail = rp._windows_verify_private_acl(key_path)
            self.assertTrue(acl_ok, acl_detail)
        metadata = rp.read_credential_metadata(self.key_root, member_id)
        self.assertEqual(metadata["source"], "create")
        self.assertNotIn("bobo-key", json.dumps(result))

    def test_host_cli_operator_key_file_end_to_end_with_empty_secret_env(self):
        self.enable_host()
        self.create_intent("op-live-cli-0001")
        operator_file = self._tmpdir / "operator.key"
        operator_file.write_text("bobo-key\n", encoding="utf-8")
        stream = io.StringIO()
        env = {key: value for key, value in os.environ.items() if key != "TALK_OPERATOR_API_KEY"}
        env["TALK_OPERATOR_API_KEY"] = ""
        with patch.dict(os.environ, env, clear=True), redirect_stdout(stream):
            code = role_service_host.main(
                [
                    "serve",
                    "--project",
                    "prj_alpha",
                    "--base-url",
                    self.base_url,
                    "--host",
                    HOST_LABEL,
                    "--operator-key-file",
                    str(operator_file),
                    "--key-root",
                    str(self.key_root),
                    "--project-root",
                    str(self.project_root),
                    "--state-dir",
                    str(self._tmpdir / "host-state-live"),
                    "--provision-worker",
                    "--provision-worker-apply",
                    "--provision-worker-max-rounds",
                    "1",
                    "--poll-interval",
                    "0.01",
                ]
            )
        output = stream.getvalue()
        self.assertEqual(code, 0, output)
        request = self.get_request("op-live-cli-0001")
        self.assertEqual(request["status"], "provisioned", output)
        member_id = request["member_id"]
        self.assertTrue(self.key_file(member_id).is_file())
        self.assertEqual(rp._read_key_file(self.key_file(member_id)), self.role_api_key(member_id))
        self.assertNotIn("bobo-key", output)

    def test_same_host_other_port_redirect_does_not_forward_credentials(self):
        recorder = _start_http_server(_HeaderRecorder)
        recorder.seen_headers = []  # type: ignore[attr-defined]
        redirector = _start_http_server(_Redirector)
        redirector.target_url = (  # type: ignore[attr-defined]
            f"http://127.0.0.1:{recorder.server_address[1]}/api/y"
        )
        try:
            transport = WorkerTransport(
                f"http://127.0.0.1:{redirector.server_address[1]}", timeout=5.0
            )
            response = transport.request_json(
                "GET",
                f"http://127.0.0.1:{redirector.server_address[1]}/api/x",
                api_key=SENTINEL_OPERATOR,
            )
            self.assertEqual(response.status, 200)
            self.assertEqual(len(recorder.seen_headers), 1)  # type: ignore[attr-defined]
            forwarded = recorder.seen_headers[0]  # type: ignore[attr-defined]
            self.assertNotIn("X-Api-Key", forwarded)
            self.assertNotIn(SENTINEL_OPERATOR, json.dumps(forwarded))
        finally:
            for server in (redirector, recorder):
                server.shutdown()
                server.server_close()

    def test_cross_host_redirect_refuses_credentials_over_real_http(self):
        redirector = _start_http_server(_Redirector)
        redirector.target_url = "http://10.11.12.13:9/api/y"  # type: ignore[attr-defined]
        try:
            transport = WorkerTransport(
                f"http://127.0.0.1:{redirector.server_address[1]}", timeout=5.0
            )
            with self.assertRaises(WorkerError) as ctx:
                transport.request_json(
                    "GET",
                    f"http://127.0.0.1:{redirector.server_address[1]}/api/x",
                    api_key=SENTINEL_OPERATOR,
                )
            self.assertEqual(ctx.exception.code, "worker_redirect_refused")
        finally:
            redirector.shutdown()
            redirector.server_close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
