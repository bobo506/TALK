"""角色生命周期 R1-4a：请求驱动创建/恢复协议 A1–A10 与共享夹具。

覆盖 ``docs/spec/ROLE_CREATION_PROVISION_REQUEST_CONTRACT.md`` §3–§5、§9：

- A1–A3 宿主配置只读投影与 enable/disable 的 CAS 与预算边界；
- A4 意图幂等（同键同载荷返回原行且不刷新快照）、异载荷 409、kind 互斥载荷、
  旧人工创建操作键冲突、跨 kind 同角色占用；
- A5 claim 的世代/预算/并发/失效重领，以及 ``lease_token`` 唯一一次性投递；
- A7/A8 只读发现（覆盖失效 leased 与失联 created）与严格白名单投影；
- A9/A10 cancel 与人工 resume（含 ``member_created`` 与耗尽续跑）；
- A6 report 的终态只读重放与异结果/旧代拒绝。

全部用例使用进程内 ``TestClient`` 与隔离 SQLite；不启生产服务、不读真实凭据、
不写宿主文件（本片宿主为模拟）。
"""

from __future__ import annotations

import logging
import threading
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlmodel import select

from server.models import (
    Member,
    ProjectRole,
    RoleProvisionRequestRow,
    RunnerModelChoice,
)
from server.role_provision_requests import claim_request
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


#: 公共投影允许出现的键（严格白名单，逐字对齐合同 §4）。
PUBLIC_PROJECTION_KEYS = {
    "request_key",
    "project_id",
    "kind",
    "status",
    "effective_status",
    "revision",
    "attempts",
    "role_name",
    "role_description",
    "runner_id",
    "choice_id",
    "member_id",
    "origin_operation_key",
    "credential_version",
    "lease_held",
    "claimable",
    "retry_exhausted",
    "lease_host",
    "claimed_at",
    "expires_at",
    "last_error_code",
    # R1-4c-a 只读投影增量（AUTO_START_DESIGN §6.4）。
    "auto_start",
    "auto_start_status",
    "auto_start_launch_id",
    "auto_start_error_code",
    "created_by",
    "created_at",
    "updated_at",
    "finished_at",
    "provision_job",
}

FORBIDDEN_SUBSTRINGS = ("api_key", "lease_token_hash", "token_hash", "argv", "C:\\")


class RoleRequestApiTestCase(RoleApiTestCase):
    """A1–A10 公共夹具：项目、运行器/选择 + 全部新入口的薄封装。"""

    def setUp(self):
        super().setUp()
        self.register_project("prj_alpha")
        self.choice_id = self.seed_runner_and_choice()

    # ── 入口封装 ─────────────────────────────────────────────────────

    def host_get(self, project_id: str = "prj_alpha", *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/role-provision-host",
                headers={"X-API-Key": key},
            )

    def host_enable(
        self,
        *,
        project_id: str = "prj_alpha",
        host_label: str = "host-desktop-1",
        expected_version: int = 0,
        key: str = "bobo-key",
        **extra,
    ):
        body = {"host_label": host_label, "expected_version": expected_version}
        body.update(extra)
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/role-provision-host/enable",
                headers={"X-API-Key": key},
                json=body,
            )

    def host_disable(
        self, *, project_id: str = "prj_alpha", expected_version: int, key: str = "bobo-key"
    ):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/role-provision-host/disable",
                headers={"X-API-Key": key},
                json={"expected_version": expected_version},
            )

    def create_intent(
        self, *, project_id: str = "prj_alpha", key: str = "bobo-key", **body
    ):
        payload = {
            "request_key": "op-intent-0001",
            "kind": "create",
            "confirm": True,
            "role_name": "dev",
            "runner_id": RUNNER_ID,
            "choice_id": self.choice_id,
        }
        payload.update(body)
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/role-requests",
                headers={"X-API-Key": key},
                json=payload,
            )

    def claim(
        self,
        request_key: str,
        *,
        project_id: str = "prj_alpha",
        host: str = "host-desktop-1",
        expected_revision: int | None = None,
        lease_seconds: int | None = None,
        key: str = "bobo-key",
    ):
        if expected_revision is None:
            expected_revision = self.get_request(request_key, project_id=project_id).json()[
                "revision"
            ]
        body = {"host": host, "expected_revision": expected_revision}
        if lease_seconds is not None:
            body["lease_seconds"] = lease_seconds
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/role-requests/{request_key}/claim",
                headers={"X-API-Key": key},
                json=body,
            )

    def cancel(
        self,
        request_key: str,
        *,
        project_id: str = "prj_alpha",
        expected_revision: int | None = None,
        key: str = "bobo-key",
    ):
        if expected_revision is None:
            expected_revision = self.get_request(request_key, project_id=project_id).json()[
                "revision"
            ]
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/role-requests/{request_key}/cancel",
                headers={"X-API-Key": key},
                json={"expected_revision": expected_revision},
            )

    def resume(
        self,
        request_key: str,
        *,
        project_id: str = "prj_alpha",
        expected_revision: int | None = None,
        confirm: bool = True,
        key: str = "bobo-key",
    ):
        if expected_revision is None:
            expected_revision = self.get_request(request_key, project_id=project_id).json()[
                "revision"
            ]
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/role-requests/{request_key}/resume",
                headers={"X-API-Key": key},
                json={"expected_revision": expected_revision, "confirm": confirm},
            )

    def report(
        self,
        request_key: str,
        *,
        project_id: str = "prj_alpha",
        lease_token: str,
        expected_revision: int | None = None,
        outcome: str = "provisioned",
        error_code: str | None = None,
        key: str = "bobo-key",
    ):
        if expected_revision is None:
            expected_revision = self.get_request(request_key, project_id=project_id).json()[
                "revision"
            ]
        body = {
            "lease_token": lease_token,
            "expected_revision": expected_revision,
            "outcome": outcome,
        }
        if error_code is not None:
            body["error_code"] = error_code
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/role-requests/{request_key}/report",
                headers={"X-API-Key": key},
                json=body,
            )

    def list_requests(
        self, *, project_id: str = "prj_alpha", key: str = "bobo-key", **params
    ):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/role-requests",
                headers={"X-API-Key": key},
                params=params,
            )

    def get_request(
        self, request_key: str, *, project_id: str = "prj_alpha", key: str = "bobo-key"
    ):
        with self.make_client() as client:
            return client.get(
                f"/api/projects/{project_id}/role-requests/{request_key}",
                headers={"X-API-Key": key},
            )

    def create_role(
        self, *, project_id: str = "prj_alpha", key: str = "bobo-key", **body
    ):
        payload = {
            "role_name": "dev",
            "runner_id": RUNNER_ID,
            "choice_id": self.choice_id,
            "operation_key": "op-intent-0001",
        }
        payload.update(body)
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/roles",
                headers={"X-API-Key": key},
                json=payload,
            )

    # ── 直读事实 ─────────────────────────────────────────────────────

    def request_row(self, request_key: str) -> RoleProvisionRequestRow | None:
        with self.session() as session:
            return session.get(RoleProvisionRequestRow, request_key)

    def force_lease_expired(self, request_key: str) -> None:
        with self.session() as session:
            row = session.get(RoleProvisionRequestRow, request_key)
            assert row is not None
            row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
            session.add(row)
            session.commit()

    def raw_member_count(self) -> int:
        """非夹具成员数（夹具固定 4 人）。"""
        with self.session() as session:
            return len(list(session.exec(select(Member)).all())) - 4

    def role_count(self) -> int:
        with self.session() as session:
            return len(list(session.exec(select(ProjectRole)).all()))

    def enable_host(self, **kwargs):
        response = self.host_enable(**kwargs)
        assert response.status_code == 200, response.text
        return response.json()

    def seed_created_role_via_pipeline(self, *, request_key: str = "op-intent-0001"):
        """意图 → claim → 原子创建；返回 ``(created_body, lease_token)``。"""
        self.enable_host()
        assert self.create_intent(request_key=request_key).status_code == 201
        claimed = self.claim(request_key).json()
        created = self.create_role(
            operation_key=request_key, lease_token=claimed["lease_token"]
        )
        assert created.status_code == 201, created.text
        return created.json(), claimed["lease_token"]


class HostConfigTests(RoleRequestApiTestCase):
    """A1–A3：只读投影、CAS 启用/关闭与预算边界。"""

    def test_get_without_config_row_is_disabled_version_zero(self):
        response = self.host_get()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["enabled"])
        self.assertEqual(body["config_version"], 0)
        self.assertIsNone(body["host_label"])
        self.assertEqual(body["lease_seconds"], 900)
        self.assertEqual(body["max_active_leases"], 2)
        self.assertEqual(body["max_attempts"], 3)

    def test_enable_disable_cas_and_version_generation(self):
        enabled = self.enable_host(expected_version=0, lease_seconds=120)
        self.assertTrue(enabled["enabled"])
        self.assertEqual(enabled["config_version"], 1)
        self.assertEqual(enabled["lease_seconds"], 120)

        # 旧版本号再 enable 不静默覆盖。
        conflict = self.host_enable(expected_version=0)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "provision_host_version_conflict")

        disabled = self.host_disable(expected_version=1)
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["config_version"], 2)
        self.assertFalse(disabled.json()["enabled"])

        stale = self.host_enable(expected_version=1)
        self.assertEqual(stale.status_code, 409)

        again = self.host_enable(expected_version=2)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["config_version"], 3)

    def test_enable_rejects_out_of_range_budget(self):
        for field, value in (
            ("lease_seconds", 10),
            ("lease_seconds", 3600),
            ("max_active_leases", 0),
            ("max_active_leases", 9),
            ("max_attempts", 0),
            ("max_attempts", 11),
        ):
            with self.subTest(field=field, value=value):
                response = self.host_enable(expected_version=0, **{field: value})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json()["detail"], "provision_host_config_invalid"
                )

    def test_host_write_entries_are_human_only(self):
        self.assertEqual(self.host_enable(key="worker-key").status_code, 403)
        self.assertEqual(self.host_disable(expected_version=0, key="worker-key").status_code, 403)


class IntentTests(RoleRequestApiTestCase):
    """A4：幂等、异载荷冲突、kind 互斥载荷与跨 kind 占用。"""

    def test_same_key_same_payload_returns_original_row(self):
        first = self.create_intent()
        self.assertEqual(first.status_code, 201)
        second = self.create_intent()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["revision"], first.json()["revision"])
        self.assertEqual(second.json()["created_at"], first.json()["created_at"])
        with self.session() as session:
            rows = list(session.exec(select(RoleProvisionRequestRow)).all())
        self.assertEqual(len(rows), 1)

    def test_same_key_different_payload_conflicts(self):
        self.assertEqual(self.create_intent().status_code, 201)
        conflict = self.create_intent(role_description="换一份说明")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "role_request_key_conflict")

    def test_create_intent_cannot_claim_manual_operation_key(self):
        manual = self.create_role(operation_key="op-intent-0001")
        self.assertEqual(manual.status_code, 201)
        conflict = self.create_intent(request_key="op-intent-0001")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "operation_key_conflict")

    def test_kind_payloads_are_mutually_exclusive(self):
        bad_create = self.create_intent(member_id="agent:x", expected_credential_version=1)
        self.assertEqual(bad_create.status_code, 422)
        bad_recover = self.create_intent(
            kind="recover", request_key="op-intent-0002", role_name="dev"
        )
        self.assertEqual(bad_recover.status_code, 422)
        bad_kind = self.create_intent(kind="clone", request_key="op-intent-0003")
        self.assertEqual(bad_kind.status_code, 422)
        self.assertEqual(bad_kind.json()["detail"], "role_request_kind_invalid")

    def test_confirm_is_required(self):
        response = self.create_intent(confirm=False)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"], "role_request_confirm_required"
        )

    def test_active_name_occupancy_and_failed_row_stops_occupying(self):
        self.assertEqual(self.create_intent(request_key="op-intent-0001").status_code, 201)
        duplicate = self.create_intent(
            request_key="op-intent-0002", role_name="dev"
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["detail"], "role_request_role_conflict")

        # 取消（终态）后旧行保留但不再占用。
        cancelled = self.cancel("op-intent-0001")
        self.assertEqual(cancelled.status_code, 200)
        retry = self.create_intent(request_key="op-intent-0002", role_name="dev")
        self.assertEqual(retry.status_code, 201)
        with self.session() as session:
            self.assertIsNotNone(session.get(RoleProvisionRequestRow, "op-intent-0001"))


class ClaimTests(RoleRequestApiTestCase):
    """A5：领取、失效重领、预算/并发与 human-only。"""

    def test_claim_issues_single_use_token_and_generation(self):
        self.enable_host()
        self.create_intent()
        first = self.claim("op-intent-0001")
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual(body["status"], "leased")
        self.assertEqual(body["lease_generation"], 1)
        self.assertEqual(body["attempts"], 1)
        self.assertTrue(body["lease_held"])
        self.assertFalse(body["claimable"])
        self.assertIn("lease_token", body)
        self.assertNotIn("api_key", body)
        self.assertIn("choice_snapshot", body)
        self.assertIsNotNone(body["expected_binding_fingerprint"])

        # 有效租约不能被再次领取。
        again = self.claim("op-intent-0001", expected_revision=body["revision"])
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"], "role_request_lease_conflict")

    def test_claim_requires_enabled_project_and_correct_revision(self):
        self.create_intent()
        disabled = self.claim("op-intent-0001", expected_revision=1)
        self.assertEqual(disabled.status_code, 409)
        self.assertEqual(disabled.json()["detail"], "provision_host_disabled")

        self.enable_host()
        stale = self.claim("op-intent-0001", expected_revision=99)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"], "role_request_revision_conflict")

    def test_expired_lease_can_be_reclaimed_with_new_generation(self):
        self.enable_host()
        self.create_intent()
        first = self.claim("op-intent-0001").json()
        self.force_lease_expired("op-intent-0001")
        second = self.claim("op-intent-0001", expected_revision=first["revision"]).json()
        self.assertEqual(second["lease_generation"], 2)
        self.assertNotEqual(second["lease_token"], first["lease_token"])
        self.assertEqual(second["attempts"], 2)

    def test_disable_then_enable_does_not_revive_old_token(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        self.host_disable(expected_version=1)
        self.enable_host(expected_version=2)
        rejected = self.create_role(
            operation_key="op-intent-0001", lease_token=claimed["lease_token"]
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.json()["detail"], "role_request_lease_invalid")
        self.assertEqual(self.raw_member_count(), 0)

    def test_attempt_budget_then_resume_clears_exhaustion(self):
        self.enable_host(max_attempts=1)
        self.create_intent()
        self.claim("op-intent-0001")
        self.force_lease_expired("op-intent-0001")
        listing = self.list_requests(claimable="true").json()
        self.assertEqual([item["request_key"] for item in listing], [])
        single = self.get_request("op-intent-0001").json()
        self.assertTrue(single["retry_exhausted"])
        self.assertFalse(single["claimable"])

        refused = self.claim("op-intent-0001", expected_revision=single["revision"])
        self.assertEqual(refused.status_code, 409)

        resumed = self.resume("op-intent-0001", expected_revision=single["revision"])
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["attempts"], 0)
        self.assertEqual(resumed.json()["status"], "requested")
        self.assertFalse(resumed.json()["retry_exhausted"])
        self.assertTrue(resumed.json()["claimable"])

    def test_active_lease_budget_is_enforced(self):
        self.enable_host(max_active_leases=1)
        self.create_intent()
        self.create_intent(request_key="op-intent-0002", role_name="ops")
        self.assertEqual(self.claim("op-intent-0001").status_code, 200)
        busy = self.claim("op-intent-0002", expected_revision=1)
        self.assertEqual(busy.status_code, 409)
        self.assertEqual(busy.json()["detail"], "provision_host_busy")

        # 释放第一个租约后，第二个可以领取。
        self.force_lease_expired("op-intent-0001")
        self.assertEqual(self.claim("op-intent-0002", expected_revision=1).status_code, 200)

    def test_lease_seconds_cannot_exceed_project_budget(self):
        self.enable_host(lease_seconds=60)
        self.create_intent()
        too_long = self.claim("op-intent-0001", expected_revision=1, lease_seconds=120)
        self.assertEqual(too_long.status_code, 422)
        self.assertEqual(
            too_long.json()["detail"], "role_request_lease_seconds_invalid"
        )
        ok = self.claim("op-intent-0001", expected_revision=1, lease_seconds=30)
        self.assertEqual(ok.status_code, 200)

    def test_claim_write_entries_are_human_only(self):
        self.enable_host()
        self.create_intent()
        self.assertEqual(
            self.claim("op-intent-0001", expected_revision=1, key="worker-key").status_code,
            403,
        )
        self.assertEqual(self.create_intent(key="worker-key").status_code, 403)


class DiscoveryTests(RoleRequestApiTestCase):
    """A7/A8：只读发现、失效 leased 的 effective_status 与投影白名单。"""

    def test_list_filters_and_projection_whitelist(self):
        self.enable_host()
        self.create_intent()
        self.create_intent(request_key="op-intent-0002", role_name="ops")
        listing = self.list_requests().json()
        self.assertEqual(len(listing), 2)
        for item in listing:
            self.assertEqual(set(item.keys()), PUBLIC_PROJECTION_KEYS)
            self.assertTrue(item["claimable"])
            self.assertEqual(item["effective_status"], "requested")

        claimed = self.claim("op-intent-0001").json()
        self.force_lease_expired("op-intent-0001")
        refreshed = self.get_request("op-intent-0001").json()
        self.assertEqual(refreshed["status"], "leased")
        self.assertEqual(refreshed["effective_status"], "requested")
        self.assertTrue(refreshed["claimable"])

        only_requested = self.list_requests(status="requested").json()
        self.assertEqual(
            [item["request_key"] for item in only_requested], ["op-intent-0002"]
        )
        # status 是存储事实（leased），effective_status 才是失效后的 requested。
        only_leased = self.list_requests(status="leased").json()
        self.assertEqual(
            [item["request_key"] for item in only_leased], ["op-intent-0001"]
        )
        self.assertEqual(only_leased[0]["effective_status"], "requested")
        claimable_only = self.list_requests(claimable="true").json()
        self.assertEqual(len(claimable_only), 2)
        self.assertEqual(
            self.list_requests(claimable="false").json(), []
        )
        self.assertEqual(self.list_requests(status="bogus").status_code, 422)
        self.assertEqual(self.list_requests(limit=0).status_code, 422)

    def test_created_request_stays_created_when_host_disappears(self):
        _, token = self.seed_created_role_via_pipeline()
        self.force_lease_expired("op-intent-0001")
        body = self.get_request("op-intent-0001").json()
        self.assertEqual(body["status"], "created")
        self.assertEqual(body["effective_status"], "created")
        self.assertTrue(body["claimable"])
        self.assertFalse(body["lease_held"])
        self.assertNotIn("lease_token", body)

    def test_missing_request_and_project_are_404(self):
        self.assertEqual(self.get_request("op-ghost-0001").status_code, 404)
        self.assertEqual(self.host_get(project_id="prj_ghost").status_code, 404)
        self.assertEqual(
            self.get_request("op-ghost-0001", project_id="prj_ghost").status_code, 404
        )
        self.assertEqual(
            self.list_requests(project_id="prj_ghost").status_code, 404
        )


class CancelAndResumeTests(RoleRequestApiTestCase):
    """A9/A10：取消边界与人工续跑。"""

    def test_cancel_before_creation_succeeds_and_blocks_creation(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        cancelled = self.cancel("op-intent-0001", expected_revision=claimed["revision"])
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], "canceled")
        self.assertEqual(cancelled.json()["finished_at"] is not None, True)

        rejected = self.create_role(
            operation_key="op-intent-0001", lease_token=claimed["lease_token"]
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(self.raw_member_count(), 0)
        self.assertEqual(self.role_count(), 0)

    def test_cancel_after_creation_reports_member_created(self):
        self.seed_created_role_via_pipeline()
        refused = self.cancel("op-intent-0001")
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["detail"], "member_created")

    def test_resume_refuses_without_confirm_and_when_not_eligible(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        no_confirm = self.resume(
            "op-intent-0001", expected_revision=claimed["revision"], confirm=False
        )
        self.assertEqual(no_confirm.status_code, 422)
        self.assertEqual(no_confirm.json()["detail"], "role_request_confirm_required")

        # 活动租约 + 未失败 + 次数未耗尽：不可人工夺权。
        active = self.resume("op-intent-0001", expected_revision=claimed["revision"])
        self.assertEqual(active.status_code, 409)
        self.assertEqual(active.json()["detail"], "role_request_not_resumable")


class ReportTests(RoleRequestApiTestCase):
    """A6：失败回报、终态只读重放与异结果拒绝。"""

    def test_failed_report_then_exact_replay_then_conflicting_outcome(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        reported = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="profile_write_failed",
        )
        self.assertEqual(reported.status_code, 200)
        body = reported.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["last_error_code"], "profile_write_failed")
        self.assertFalse(body["replayed"])

        replay = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="profile_write_failed",
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replayed"])

        conflicted = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="provisioned",
        )
        self.assertEqual(conflicted.status_code, 409)
        self.assertEqual(conflicted.json()["detail"], "role_request_stale_report")

    def test_report_rejects_stale_token_and_bad_error_code(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        bad_token = self.report(
            "op-intent-0001",
            lease_token="not-the-token",
            expected_revision=claimed["revision"],
            outcome="failed",
        )
        self.assertEqual(bad_token.status_code, 409)
        self.assertEqual(bad_token.json()["detail"], "role_request_lease_invalid")

        bad_code = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="bad code with spaces",
        )
        self.assertEqual(bad_code.status_code, 422)

        code_on_success = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="provisioned",
            error_code="whatever",
        )
        self.assertEqual(code_on_success.status_code, 422)

    def test_provisioned_report_requires_real_facts(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        incomplete = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="provisioned",
        )
        self.assertEqual(incomplete.status_code, 409)
        self.assertEqual(
            incomplete.json()["detail"], "role_request_completion_incomplete"
        )
        # 资格失败零写入：请求仍是 leased，成员仍是 0。
        self.assertEqual(self.get_request("op-intent-0001").json()["status"], "leased")
        self.assertEqual(self.raw_member_count(), 0)


class RoutersHaveNoSecretsTests(RoleRequestApiTestCase):
    """所有公开投影与错误正文都不回显 Key / token 哈希 / 路径 / argv。"""

    def test_public_responses_never_leak_credentials(self):
        created, token = self.seed_created_role_via_pipeline()
        api_key = created["api_key"]
        self.assertTrue(api_key)

        bodies = [
            self.get_request("op-intent-0001").text,
            self.list_requests().text,
            self.host_get().text,
        ]
        for text in bodies:
            self.assertNotIn(api_key, text)
            self.assertNotIn(token, text)
            for marker in FORBIDDEN_SUBSTRINGS:
                self.assertNotIn(marker, text)

        replayed = self.create_role(
            operation_key="op-intent-0001", lease_token=token
        )
        self.assertEqual(replayed.status_code, 200)
        self.assertTrue(replayed.json()["reused"])
        self.assertNotIn("api_key", replayed.json())


class ReworkHostLabelTests(RoleRequestApiTestCase):
    """F1 返修：claim 必须在写锁内按规范化 host 比对当前 ``config.host_label``。"""

    def test_wrong_host_is_refused_with_zero_change(self):
        self.enable_host(host_label="host-desktop-1")
        self.assertEqual(self.create_intent().status_code, 201)
        before = self.get_request("op-intent-0001").json()

        refused = self.claim("op-intent-0001", host="unassigned-host")
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["detail"], "role_request_host_mismatch")
        self.assertNotIn("lease_token", refused.text)

        after = self.get_request("op-intent-0001").json()
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["attempts"], before["attempts"])
        self.assertEqual(after["lease_held"], before["lease_held"])
        self.assertEqual(after["expires_at"], before["expires_at"])
        row = self.request_row("op-intent-0001")
        self.assertIsNone(row.lease_token_hash)
        self.assertEqual(row.lease_generation, 0)
        self.assertIsNone(row.lease_host)

        # 规范化后相同的标签（含首尾空白）仍可领取；human Key 认证与既有 fencing 不降。
        accepted = self.claim("op-intent-0001", host="  host-desktop-1  ")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertTrue(accepted.json()["lease_token"])

    def test_blank_host_is_rejected_as_invalid(self):
        self.enable_host()
        self.create_intent()
        refused = self.claim("op-intent-0001", host="   ")
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["detail"], "provision_host_config_invalid")


class ReworkIntentReplayTests(RoleRequestApiTestCase):
    """F2 返修：A4 先做纯载荷归一化/指纹与既有键重放，实时事实不阻断正常重放。"""

    def test_create_intent_replay_survives_choice_retirement(self):
        self.enable_host()
        first = self.create_intent()
        self.assertEqual(first.status_code, 201)
        with self.session() as session:
            choice = session.get(RunnerModelChoice, self.choice_id)
            choice.retired_at = datetime.now(timezone.utc)
            session.add(choice)
            session.commit()

        replay = self.create_intent()
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["revision"], first.json()["revision"])
        self.assertEqual(replay.json()["created_at"], first.json()["created_at"])
        self.assertEqual(replay.json()["status"], "requested")
        # 零更新：冻结快照与租约事实都保持原样。
        row = self.request_row("op-intent-0001")
        self.assertEqual(row.choice_snapshot["choice_id"], self.choice_id)
        self.assertIsNone(row.lease_token_hash)
        self.assertEqual(row.revision, first.json()["revision"])


class ReworkErrorCodeWhitelistTests(RoleRequestApiTestCase):
    """F3 返修：report 错误码只接受有限稳定白名单，未知（含假凭据）422 零写入。"""

    def test_unknown_error_code_is_refused_and_never_exposed(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        sentinel = "sentinelOnlyKey_Private123"  # 仅隔离库假凭据，不打印值
        self.add_member("human:secret-sentinel", api_key=sentinel)

        refused = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code=sentinel,
        )
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["detail"], "role_request_payload_invalid")
        self.assertNotIn(sentinel, refused.text)

        public = self.get_request("op-intent-0001", key="worker-key")
        self.assertEqual(public.status_code, 200)
        self.assertNotIn(sentinel, public.text)
        self.assertNotIn(sentinel, self.list_requests(key="worker-key").text)

        # 零写入：仍是 leased，未落任何 last_error_code。
        row = self.get_request("op-intent-0001").json()
        self.assertEqual(row["status"], "leased")
        self.assertIsNone(row["last_error_code"])
        self.assertIsNone(self.request_row("op-intent-0001").report_outcome)

        # 未来未知码同样拒绝（白名单需按合同维护，不泛化接受）。
        future = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="some_future_host_code",
        )
        self.assertEqual(future.status_code, 422)
        self.assertIsNone(self.request_row("op-intent-0001").report_outcome)

        # 白名单内的既有稳定码正常落库。
        accepted = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="manual_recovery_required",
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["last_error_code"], "manual_recovery_required")


class ReworkReportReplayTests(RoleRequestApiTestCase):
    """F5 返修：精确终态重放必须包含规范化后的实际错误结果与报告期代际。"""

    def test_report_replay_requires_same_error_result(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        first = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="manual_recovery_required",
        )
        self.assertEqual(first.status_code, 200, first.text)
        before = self.get_request("op-intent-0001").json()

        mismatch = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="role_key_stale",
        )
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(mismatch.json()["detail"], "role_request_stale_report")

        after = self.get_request("op-intent-0001").json()
        self.assertEqual(after["status"], "failed")
        self.assertEqual(after["last_error_code"], "manual_recovery_required")
        self.assertEqual(after["revision"], before["revision"])

        exact = self.report(
            "op-intent-0001",
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="manual_recovery_required",
        )
        self.assertEqual(exact.status_code, 200, exact.text)
        self.assertTrue(exact.json()["replayed"])


class ConcurrentClaimTests(RoleRequestApiTestCase):
    """隔离 SQLite WAL + 两个独立连接：并发 claim 只能有一次真实领取。"""

    def enable_wal(self) -> None:
        with self.engine.connect() as connection:
            mode = connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar()
        self.assertEqual(str(mode).lower(), "wal")

    def race(self, targets: list) -> tuple[list, list]:
        """两个独立 DBAPI 连接 + barrier 同时进入写事务；返回 (结果, 连接标识)。"""
        barrier = threading.Barrier(len(targets), timeout=30)
        results: list = [None] * len(targets)
        connection_ids: list = [None] * len(targets)

        def runner(index: int, target) -> None:
            session = self.session()
            try:
                connection_ids[index] = id(
                    session.connection().connection.driver_connection
                )
                barrier.wait()
                results[index] = ("ok", target(session))
            except HTTPException as exc:
                results[index] = ("http", exc.status_code, exc.detail)
            except Exception as exc:  # noqa: BLE001 - 并发异常如实记录，不掩盖
                results[index] = ("error", type(exc).__name__, str(exc))
            finally:
                session.close()

        threads = [
            threading.Thread(target=runner, args=(index, target))
            for index, target in enumerate(targets)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=90)
        return results, connection_ids

    def test_concurrent_claim_same_key_has_single_winner(self):
        self.enable_host(max_active_leases=2)
        self.assertEqual(self.create_intent().status_code, 201)
        revision = self.get_request("op-intent-0001").json()["revision"]
        self.enable_wal()

        results, connection_ids = self.race(
            [
                lambda session: claim_request(
                    "prj_alpha",
                    "op-intent-0001",
                    host="host-desktop-1",
                    expected_revision=revision,
                    lease_seconds=None,
                    session=session,
                )
                for _ in range(2)
            ]
        )
        self.assertEqual(len(set(connection_ids)), 2, connection_ids)
        winners = [item for item in results if item[0] == "ok"]
        self.assertEqual(len(winners), 1, results)
        losers = [item for item in results if item[0] != "ok"]
        self.assertTrue(all(item[0] == "http" for item in losers), results)
        self.assertTrue(all(item[1] == 409 for item in losers), results)

        row = self.request_row("op-intent-0001")
        self.assertEqual(row.attempts, 1)
        self.assertEqual(row.revision, revision + 1)
        self.assertEqual(row.lease_generation, 1)
        self.assertEqual(row.status, "leased")

    def test_concurrent_claim_respects_project_lease_budget(self):
        self.enable_host(max_active_leases=1)
        self.assertEqual(self.create_intent().status_code, 201)
        self.assertEqual(
            self.create_intent(request_key="op-intent-0002", role_name="ops").status_code,
            201,
        )
        self.enable_wal()

        results, connection_ids = self.race(
            [
                lambda session, request_key=request_key: claim_request(
                    "prj_alpha",
                    request_key,
                    host="host-desktop-1",
                    expected_revision=1,
                    lease_seconds=None,
                    session=session,
                )
                for request_key in ("op-intent-0001", "op-intent-0002")
            ]
        )
        self.assertEqual(len(set(connection_ids)), 2, connection_ids)
        winners = [item for item in results if item[0] == "ok"]
        self.assertEqual(len(winners), 1, results)
        losers = [item for item in results if item[0] != "ok"]
        self.assertEqual(len(losers), 1, results)
        self.assertEqual(losers[0][0], "http", results)
        self.assertEqual(losers[0][1], 409, results)
        self.assertEqual(losers[0][2], "provision_host_busy", results)

        with self.session() as session:
            leased = list(
                session.exec(
                    select(RoleProvisionRequestRow).where(
                        RoleProvisionRequestRow.status == "leased"
                    )
                ).all()
            )
        self.assertEqual(len(leased), 1)
        self.assertEqual(leased[0].attempts, 1)


class AutoStartReplayMatrixTests(RoleRequestApiTestCase):
    """R1-4c-a：同 ``request_key`` 重放时 auto_start 规范布尔值的严格比较矩阵。

    共享四字段 payload / 创建指纹 / ``RoleCreationOperation`` 全部不变；auto_start
    独立落列参与同键比较（AUTO_START_DESIGN §2/§4.3）。旧行默认 0，与旧客户端
    缺省重放兼容。
    """

    def test_same_key_auto_start_boolean_matrix(self):
        cases = [
            # (首次 create 的 auto_start, 重放的 auto_start, 期望状态码)
            (None, None, 200),
            (None, False, 200),
            (None, True, 409),
            (False, None, 200),
            (False, False, 200),
            (False, True, 409),
            (True, None, 409),
            (True, False, 409),
            (True, True, 200),
        ]
        for index, (first, replay, expected) in enumerate(cases):
            with self.subTest(first=first, replay=replay):
                key = f"op-matrix-{index:04d}"
                body: dict = {"request_key": key, "role_name": f"dev-{index}"}
                if first is not None:
                    body["auto_start"] = first
                first_response = self.create_intent(**body)
                self.assertEqual(first_response.status_code, 201, first_response.text)
                self.assertEqual(
                    first_response.json()["auto_start"], bool(first)
                )
                self.assertEqual(
                    first_response.json()["auto_start_status"],
                    "pending" if first else None,
                )

                replay_body: dict = {"request_key": key, "role_name": f"dev-{index}"}
                if replay is not None:
                    replay_body["auto_start"] = replay
                replay_response = self.create_intent(**replay_body)
                self.assertEqual(
                    replay_response.status_code, expected, replay_response.text
                )
                if expected == 200:
                    self.assertTrue(replay_response.json()["auto_start"] == bool(first))
                else:
                    self.assertEqual(
                        replay_response.json()["detail"], "role_request_key_conflict"
                    )

    def test_auto_start_intent_passes_c1_and_exact_replay_still_reused(self):
        """C1 守卫不被误拒：payload/指纹不变，auto_start 意图可完整走完 C1。"""
        self.enable_host()
        intent = self.create_intent(request_key="op-auto-c1", auto_start=True)
        self.assertEqual(intent.status_code, 201, intent.text)
        claimed = self.claim("op-auto-c1").json()
        created = self.create_role(
            operation_key="op-auto-c1", lease_token=claimed["lease_token"]
        )
        self.assertEqual(created.status_code, 201, created.text)
        # 同键同四字段同租约的精确重放仍是只读 reused（auto_start 不进共享指纹）。
        replay = self.create_role(
            operation_key="op-auto-c1", lease_token=claimed["lease_token"]
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["reused"])
        projection = self.get_request("op-auto-c1").json()
        self.assertTrue(projection["auto_start"])
        self.assertEqual(projection["auto_start_status"], "pending")

    def test_recover_rejects_auto_start_field(self):
        """recover 携带 auto_start（True/False 均非 None）→ 422 互斥载荷。"""
        created, _token = self.seed_created_role_via_pipeline()
        member_id = created["member_id"]
        for value in (True, False):
            response = self.create_intent(
                request_key="op-auto-recover-x",
                kind="recover",
                role_name=None,
                runner_id=None,
                choice_id=None,
                member_id=member_id,
                expected_credential_version=1,
                auto_start=value,
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "role_request_payload_invalid")


if __name__ == "__main__":
    unittest.main()
