"""角色生命周期 R1-4a：C1 首次创建守卫与 C3/C4 请求来源接线。

覆盖 REQUEST_CONTRACT §5.1、§6、§8：

- 正向：create 意图 → claim → **原子**首次创建（六表 + 请求 created）→ 原 operation_key
  作业 → 三步 ACK → report(provisioned)；
- 负向：首次载荷/choice 替换零创建；缺租约、disabled、过期租约、选择下架各自零写入；
  省略 ``request_key`` 不能退回旧人工旁路；ACK 保持原有错误顺序与凭据代际；
  三步未完成或代际不符不能完成；跨 kind 同角色占用；
- 兼容：没有请求来源的旧人工创建/回放路径保持 R1-1 合同（含目录退役后回放不返 Key）。

全部用例使用进程内 ``TestClient`` 与隔离 SQLite；宿主为模拟，不写任何宿主文件。
"""

from __future__ import annotations

import logging
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlmodel import select

from server.models import (
    Member,
    ProjectAgent,
    ProjectRole,
    ProjectRoleBinding,
    ProjectRoleDescription,
    RoleCreationOperation,
    RoleProvisionJob,
    RunnerModelChoice,
)
from tests.test_project_roles import RUNNER_ID, encode
from tests.test_role_provision_requests import RoleRequestApiTestCase

_saved_root_level: int | None = None
_saved_handler_levels: list[int] = []


def setUpModule():
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


class CreateGuardTestCase(RoleRequestApiTestCase):
    """C1/C3/C4 与请求来源的公共辅助。"""

    def role_creation_operation_count(self) -> int:
        with self.session() as session:
            return len(list(session.exec(select(RoleCreationOperation)).all()))

    def project_role_count(self) -> int:
        with self.session() as session:
            return len(list(session.exec(select(ProjectRole)).all()))

    def retire_choice(self, choice_id: str) -> None:
        with self.session() as session:
            choice = session.get(RunnerModelChoice, choice_id)
            assert choice is not None
            choice.retired_at = datetime.now(timezone.utc)
            session.add(choice)
            session.commit()

    def assert_zero_creation(self) -> None:
        self.assertEqual(self.raw_member_count(), 0)
        self.assertEqual(self.project_role_count(), 0)
        self.assertEqual(self.role_creation_operation_count(), 0)

    def provision_role(
        self,
        member_id: str,
        *,
        operation_key: str = "op-intent-0001",
        request_key: str | None = None,
        lease_token: str | None = None,
        resume: bool = False,
        steps: list[str] | None = None,
        project_id: str = "prj_alpha",
        key: str = "bobo-key",
    ):
        body: dict = {"operation_key": operation_key, "resume": resume}
        if steps is not None:
            body["steps"] = steps
        if request_key is not None:
            body["request_key"] = request_key
        if lease_token is not None:
            body["lease_token"] = lease_token
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/roles/{encode(member_id)}/provision",
                headers={"X-API-Key": key},
                json=body,
            )

    def ack_step(
        self,
        member_id: str,
        job: dict,
        step: str,
        *,
        operation_key: str = "op-intent-0001",
        request_key: str | None = None,
        lease_token: str | None = None,
        state: str = "succeeded",
        error_code: str | None = None,
        revision: int | None = None,
        attempt: int | None = None,
        credential_version: int | None = None,
        project_id: str = "prj_alpha",
        key: str = "bobo-key",
    ):
        body = {
            "operation_key": operation_key,
            "step": step,
            "attempt": attempt if attempt is not None else job["steps"][step]["attempts"],
            "revision": revision if revision is not None else job["revision"],
            "credential_version": (
                credential_version
                if credential_version is not None
                else job["credential_version"]
            ),
            "state": state,
        }
        if error_code is not None:
            body["error_code"] = error_code
        if request_key is not None:
            body["request_key"] = request_key
        if lease_token is not None:
            body["lease_token"] = lease_token
        with self.make_client() as client:
            return client.post(
                f"/api/projects/{project_id}/roles/{encode(member_id)}/provision/ack",
                headers={"X-API-Key": key},
                json=body,
            )

    def complete_pipeline(
        self, *, request_key: str = "op-intent-0001"
    ) -> tuple[str, dict, str]:
        """意图 → claim → 创建 → 作业 → 三步 ACK；返回 ``(member_id, job, token)``。"""
        created, token = self.seed_created_role_via_pipeline(request_key=request_key)
        member_id = created["member_id"]
        provision = self.provision_role(
            member_id, operation_key=request_key, request_key=request_key, lease_token=token
        )
        self.assertEqual(provision.status_code, 201, provision.text)
        job = provision.json()
        for step in ("profile", "key_file", "preflight"):
            ack = self.ack_step(
                member_id,
                job,
                step,
                operation_key=request_key,
                request_key=request_key,
                lease_token=token,
            )
            self.assertEqual(ack.status_code, 200, ack.text)
            job = ack.json()
        return member_id, job, token


class CreateGuardNegativeTests(CreateGuardTestCase):
    """首次创建的负向：任一步失败都零残留。"""

    def test_payload_replacement_creates_nothing(self):
        self.enable_host()
        self.create_intent(role_description="原始说明")
        token = self.claim("op-intent-0001").json()["lease_token"]
        replaced = self.create_role(
            role_description="替换后的说明", lease_token=token
        )
        self.assertEqual(replaced.status_code, 409)
        self.assertEqual(replaced.json()["detail"], "role_provision_payload_mismatch")
        self.assert_zero_creation()

    def test_choice_replacement_creates_nothing(self):
        other_choice = self.create_choice(model_id="deepseek-pro").json()["choice_id"]
        self.enable_host()
        self.create_intent()
        token = self.claim("op-intent-0001").json()["lease_token"]
        replaced = self.create_role(
            choice_id=other_choice, lease_token=token
        )
        self.assertEqual(replaced.status_code, 409)
        self.assertEqual(replaced.json()["detail"], "role_provision_payload_mismatch")
        self.assert_zero_creation()

    def test_missing_lease_token_is_refused(self):
        self.enable_host()
        self.create_intent()
        self.claim("op-intent-0001")
        refused = self.create_role()
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["detail"], "provision_lease_required")
        self.assert_zero_creation()

    def test_disable_between_claim_and_create_blocks_creation(self):
        self.enable_host()
        self.create_intent()
        token = self.claim("op-intent-0001").json()["lease_token"]
        self.host_disable(expected_version=1)
        blocked = self.create_role(lease_token=token)
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "provision_host_disabled")
        self.assert_zero_creation()

    def test_expired_lease_blocks_creation(self):
        self.enable_host()
        self.create_intent()
        token = self.claim("op-intent-0001").json()["lease_token"]
        self.force_lease_expired("op-intent-0001")
        blocked = self.create_role(lease_token=token)
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_lease_invalid")
        self.assert_zero_creation()

    def test_retired_choice_blocks_first_creation(self):
        self.enable_host()
        self.create_intent()
        token = self.claim("op-intent-0001").json()["lease_token"]
        self.retire_choice(self.choice_id)
        blocked = self.create_role(lease_token=token)
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_choice_unavailable")
        self.assert_zero_creation()

    def test_cancelled_request_blocks_creation(self):
        self.enable_host()
        self.create_intent()
        claimed = self.claim("op-intent-0001").json()
        self.cancel("op-intent-0001", expected_revision=claimed["revision"])
        blocked = self.create_role(lease_token=claimed["lease_token"])
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_status_conflict")
        self.assert_zero_creation()


class CreateGuardPositiveTests(CreateGuardTestCase):
    """C1/C3/C4 的正向闭环与兼容回放。"""

    def test_full_pipeline_create_provision_ack_and_report(self):
        member_id, job, token = self.complete_pipeline()
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["credential_version"], 1)

        request_body = self.get_request("op-intent-0001").json()
        self.assertEqual(request_body["status"], "created")
        self.assertEqual(request_body["member_id"], member_id)
        self.assertEqual(request_body["origin_operation_key"], "op-intent-0001")
        self.assertEqual(request_body["provision_job"]["status"], "succeeded")
        for step in ("profile", "key_file", "preflight"):
            self.assertEqual(
                request_body["provision_job"]["steps"][step]["state"], "succeeded"
            )

        reported = self.report(
            "op-intent-0001",
            lease_token=token,
            expected_revision=request_body["revision"],
            outcome="provisioned",
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        final = reported.json()
        self.assertEqual(final["status"], "provisioned")
        self.assertFalse(final["replayed"])
        self.assertEqual(final["credential_version"], 1)

        again = self.get_request("op-intent-0001").json()
        self.assertEqual(again["status"], "provisioned")
        self.assertFalse(again["claimable"])
        self.assertIsNotNone(again["finished_at"])

    def test_committed_replay_ignores_later_choice_retirement(self):
        created, token = self.seed_created_role_via_pipeline()
        self.retire_choice(self.choice_id)
        replay = self.create_role(lease_token=token)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["reused"])
        self.assertNotIn("api_key", replay.json())
        self.assertEqual(replay.json()["member_id"], created["member_id"])

    def test_manual_creation_without_any_request_is_unchanged(self):
        manual = self.create_role(operation_key="op-manual-0001")
        self.assertEqual(manual.status_code, 201)
        self.assertIn("api_key", manual.json())
        replay = self.create_role(operation_key="op-manual-0001")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["reused"])
        self.assertNotIn("api_key", replay.json())

    def test_provision_and_ack_require_request_source_once_one_exists(self):
        created, token = self.seed_created_role_via_pipeline()
        member_id = created["member_id"]
        # 省略 request_key：该原键已有来源行，禁止退回旧人工旁路。
        omitted = self.provision_role(member_id, operation_key="op-intent-0001")
        self.assertEqual(omitted.status_code, 409)
        self.assertEqual(omitted.json()["detail"], "provision_lease_required")

        with_token_only = self.provision_role(
            member_id, operation_key="op-intent-0001", lease_token=token
        )
        self.assertEqual(with_token_only.status_code, 409)
        self.assertEqual(with_token_only.json()["detail"], "provision_lease_required")

        provision = self.provision_role(
            member_id, request_key="op-intent-0001", lease_token=token
        )
        self.assertEqual(provision.status_code, 201, provision.text)
        job = provision.json()
        for step in ("profile", "key_file"):
            ack = self.ack_step(
                member_id,
                job,
                step,
                request_key="op-intent-0001",
                lease_token=token,
            )
            self.assertEqual(ack.status_code, 200, ack.text)
            job = ack.json()
        failed = self.ack_step(
            member_id,
            job,
            "preflight",
            request_key="op-intent-0001",
            lease_token=token,
            state="failed",
            error_code="native_login_unverified",
        )
        self.assertEqual(failed.status_code, 200, failed.text)

        # ACK 省略 request_key：既有 step/state/revision/pending/attempt/credential/error_code
        # 规则先全部跑完，最后才因缺来源被拒绝；失败零写入。
        resumed = self.provision_role(
            member_id,
            request_key="op-intent-0001",
            lease_token=token,
            resume=True,
            steps=["preflight"],
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        job = resumed.json()
        self.assertEqual(job["steps"]["preflight"]["state"], "pending")

        tail_omitted = self.ack_step(
            member_id, job, "preflight", operation_key="op-intent-0001"
        )
        self.assertEqual(tail_omitted.status_code, 409)
        self.assertEqual(tail_omitted.json()["detail"], "provision_lease_required")
        with self.session() as session:
            stored = session.get(RoleProvisionJob, "op-intent-0001")
            self.assertEqual(stored.steps["preflight"]["state"], "pending")
            self.assertEqual(stored.revision, job["revision"])

    def test_ack_keeps_original_error_order_before_source_check(self):
        member_id, job, token = self.complete_pipeline()
        stale = self.ack_step(
            member_id,
            job,
            "profile",
            operation_key="op-intent-0001",
            request_key="op-intent-0001",
            lease_token=token,
            revision=job["revision"] + 5,
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"], "provision_revision_conflict")

        with self.session() as session:
            stored = session.get(RoleProvisionJob, "op-intent-0001")
            self.assertEqual(stored.status, "succeeded")
            self.assertEqual(stored.revision, job["revision"])

    def test_incomplete_steps_cannot_complete_request(self):
        created, token = self.seed_created_role_via_pipeline()
        member_id = created["member_id"]
        provision = self.provision_role(
            member_id, request_key="op-intent-0001", lease_token=token
        )
        job = provision.json()
        ack = self.ack_step(
            member_id,
            job,
            "profile",
            request_key="op-intent-0001",
            lease_token=token,
        )
        self.assertEqual(ack.status_code, 200)

        revision = self.get_request("op-intent-0001").json()["revision"]
        incomplete = self.report(
            "op-intent-0001",
            lease_token=token,
            expected_revision=revision,
            outcome="provisioned",
        )
        self.assertEqual(incomplete.status_code, 409)
        self.assertEqual(
            incomplete.json()["detail"], "role_request_completion_incomplete"
        )
        self.assertEqual(self.get_request("op-intent-0001").json()["status"], "created")

    def test_cross_kind_occupancy_blocks_recover_while_create_active(self):
        created, _token = self.seed_created_role_via_pipeline()
        blocked = self.create_intent(
            kind="recover",
            request_key="op-recover-0001",
            role_name=None,
            runner_id=None,
            choice_id=None,
            member_id=created["member_id"],
            expected_credential_version=1,
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_role_conflict")

    def test_provision_rejects_request_operation_mismatch(self):
        member_id, _job, token = self.complete_pipeline()
        other = self.create_role(
            role_name="ops", operation_key="op-manual-0002"
        )
        self.assertEqual(other.status_code, 201)
        mismatched = self.provision_role(
            member_id,
            operation_key="op-manual-0002",
            request_key="op-intent-0001",
            lease_token=token,
        )
        self.assertEqual(mismatched.status_code, 409)
        self.assertIn(
            mismatched.json()["detail"],
            {"role_request_operation_mismatch", "provision_operation_mismatch"},
        )


class MembershipProjectionTests(CreateGuardTestCase):
    """创建后的名册/绑定事实与请求投影一致。"""

    def test_created_role_is_in_roster_and_binding_matches_snapshot(self):
        created, _token = self.seed_created_role_via_pipeline()
        member_id = created["member_id"]
        with self.session() as session:
            member = session.get(Member, member_id)
            role = session.get(ProjectRole, ("prj_alpha", member_id))
        self.assertIsNotNone(member)
        self.assertIsNotNone(role)
        self.assertEqual(role.origin, "managed")
        self.assertEqual(role.credential_version, 1)
        self.assertEqual(member.api_key, created["api_key"])

        roles = self.get_roles().json()
        projected = [item for item in roles if item["member_id"] == member_id]
        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0]["role_name"], "dev")
        self.assertEqual(projected[0]["model"]["choice_id"], self.choice_id)


class ReworkOccupancyTests(CreateGuardTestCase):
    """F4 返修：跨 kind 占用以稳定成员锚点判定，改名不能绕过；旧 resume 不夺新请求。"""

    def test_renamed_role_still_blocks_same_member_recover(self):
        created, _token = self.seed_created_role_via_pipeline()
        member_id = created["member_id"]
        renamed = self.patch_role("prj_alpha", member_id, {"role_name": "renamed-dev"})
        self.assertEqual(renamed.status_code, 200, renamed.text)

        blocked = self.create_intent(
            kind="recover",
            request_key="op-recover-0001",
            role_name=None,
            runner_id=None,
            choice_id=None,
            member_id=member_id,
            expected_credential_version=1,
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_role_conflict")
        self.assertIsNone(self.request_row("op-recover-0001"))

    def test_uncreated_create_intent_still_protects_name(self):
        self.enable_host()
        self.assertEqual(self.create_intent().status_code, 201)
        # 尚未创建的 create 意图对同名仍占用（同名保护不因未创建而消失）。
        duplicate = self.create_intent(request_key="op-intent-0002", role_name="dev")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["detail"], "role_request_role_conflict")


class ReworkSourceGuardTests(CreateGuardTestCase):
    """F6 返修：携带租约却无请求来源必须拒绝，不退回旧人工创建。"""

    def test_lease_token_without_matching_intent_is_refused(self):
        self.enable_host()
        self.create_intent()
        token = self.claim("op-intent-0001").json()["lease_token"]

        refused = self.create_role(operation_key="op-typo-0099", lease_token=token)
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["detail"], "provision_lease_required")
        self.assert_zero_creation()

        # 空串同样按“参数存在”拒绝，不依赖 truthiness。
        blank = self.create_role(operation_key="op-typo-0100", lease_token="")
        self.assertEqual(blank.status_code, 409)
        self.assertEqual(blank.json()["detail"], "provision_lease_required")
        self.assert_zero_creation()

        # 确实无 token / 无来源的旧人工路径与已提交回放保持不变。
        manual = self.create_role(operation_key="op-manual-0101")
        self.assertEqual(manual.status_code, 201, manual.text)
        replay = self.create_role(operation_key="op-manual-0101")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["reused"])
        self.assertNotIn("api_key", replay.json())

    def test_request_driven_ack_rejects_unknown_error_code(self):
        created, token = self.seed_created_role_via_pipeline()
        member_id = created["member_id"]
        provision = self.provision_role(
            member_id, request_key="op-intent-0001", lease_token=token
        )
        job = provision.json()
        for step in ("profile", "key_file"):
            ack = self.ack_step(
                member_id, job, step, request_key="op-intent-0001", lease_token=token
            )
            self.assertEqual(ack.status_code, 200, ack.text)
            job = ack.json()

        sentinel = "sentinelOnlyKey_Private123"  # 仅隔离库假凭据，不打印值
        refused = self.ack_step(
            member_id,
            job,
            "preflight",
            request_key="op-intent-0001",
            lease_token=token,
            state="failed",
            error_code=sentinel,
        )
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["detail"], "provision_error_code_invalid")
        self.assertNotIn(sentinel, refused.text)
        with self.session() as session:
            stored = session.get(RoleProvisionJob, "op-intent-0001")
            self.assertEqual(stored.steps["preflight"]["state"], "pending")
            self.assertEqual(stored.revision, job["revision"])

        accepted = self.ack_step(
            member_id,
            job,
            "preflight",
            request_key="op-intent-0001",
            lease_token=token,
            state="failed",
            error_code="native_login_unverified",
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)


class CreateAtomicityTests(CreateGuardTestCase):
    """提交前故障注入：六表 + 请求事实必须整体回滚，无 Key / 操作残留。"""

    def test_failure_before_commit_rolls_back_everything(self):
        self.enable_host()
        self.assertEqual(self.create_intent().status_code, 201)
        claimed = self.claim("op-intent-0001").json()
        before = self.get_request("op-intent-0001").json()

        with patch(
            "server.routes.projects.apply_create_intent_created",
            side_effect=RuntimeError("injected failure before commit"),
        ):
            failed = self.create_role(
                operation_key="op-intent-0001", lease_token=claimed["lease_token"]
            )
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(failed.json()["detail"], "role_creation_failed")
        self.assertNotIn("api_key", failed.text)

        with self.session() as session:
            self.assertEqual(
                len(list(session.exec(select(ProjectRole)).all())), 0
            )
            self.assertEqual(len(list(session.exec(select(ProjectAgent)).all())), 0)
            self.assertEqual(
                len(list(session.exec(select(ProjectRoleBinding)).all())), 0
            )
            self.assertEqual(
                len(list(session.exec(select(ProjectRoleDescription)).all())), 0
            )
            self.assertEqual(
                len(list(session.exec(select(RoleCreationOperation)).all())), 0
            )
        self.assertEqual(self.raw_member_count(), 0)

        after = self.get_request("op-intent-0001").json()
        self.assertEqual(after["status"], "leased")
        self.assertIsNone(after["member_id"])
        self.assertIsNone(after["origin_operation_key"])
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["attempts"], before["attempts"])
        self.assertTrue(after["lease_held"])
        row = self.request_row("op-intent-0001")
        self.assertEqual(row.status, "leased")
        self.assertIsNone(row.member_id)
        self.assertIsNone(row.origin_operation_key)
        self.assertEqual(row.lease_generation, 1)


if __name__ == "__main__":
    unittest.main()
