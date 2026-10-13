"""角色生命周期 R1-4a：C2 请求驱动凭据恢复与终态重放顺序。

覆盖 REQUEST_CONTRACT §5.1、§7、§8、§9：

- 正向：create 终态后两轮 recover，各自最多一次原子轮换，重放省略 Key；
- §7.1 判定顺序：**先查已执行记录**再对新副作用做当前版本 CAS，即使当前版本已被
  后来的轮换推到 after 之后，正常重放也不能被拒；
- 精确取源：``body.request_key`` 必须命中**那一行**，不能任取首行、不能省略字段回旧路径；
- 竞争：新 recover 只能替代**租约失效**的旧 recover；旧 resume 不得夺回新意图资格；
  ``failed`` 后 resume 与终态重放的区分；
- 负向：过期/禁用租约、旁路轮换导致的代际不符各自零副作用。

全部用例使用进程内 ``TestClient`` 与隔离 SQLite；宿主为模拟，不写任何宿主文件。
"""

from __future__ import annotations

import logging
import threading
import unittest

from fastapi import HTTPException
from sqlmodel import select

from server.models import (
    Member,
    ProjectRole,
    RoleCredentialRotation,
    RoleProvisionJob,
    RoleRequestRotateRequest,
)
from server.routes.projects import rotate_project_role_key
from tests.test_project_roles import encode
from tests.test_role_creation_request_guard import CreateGuardTestCase

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


RECOVER_KEY = "op-recover-0001"
SECOND_RECOVER_KEY = "op-recover-0002"


class RecoveryTestCase(CreateGuardTestCase):
    """恢复流程公共辅助。"""

    def rotate(self, member_id: str, body: dict | None = None, *, project_id: str = "prj_alpha", key: str = "bobo-key"):
        with self.make_client() as client:
            url = f"/api/projects/{project_id}/roles/{encode(member_id)}/rotate-key"
            headers = {"X-API-Key": key}
            if body is None:
                return client.post(url, headers=headers)
            return client.post(url, headers=headers, json=body)

    def start_recover(
        self,
        member_id: str,
        *,
        request_key: str = RECOVER_KEY,
        expected_version: int,
        confirm: bool = True,
        project_id: str = "prj_alpha",
        key: str = "bobo-key",
    ):
        return self.create_intent(
            project_id=project_id,
            key=key,
            kind="recover",
            request_key=request_key,
            role_name=None,
            runner_id=None,
            choice_id=None,
            member_id=member_id,
            expected_credential_version=expected_version,
            confirm=confirm,
        )

    def make_provisioned_role(self, *, request_key: str = "op-intent-0001"):
        """create 意图 → claim → 创建 → 作业 → 三步 ACK → report(provisioned)。"""
        member_id, job, token = self.complete_pipeline(request_key=request_key)
        self.assertEqual(job["status"], "succeeded")
        revision = self.get_request(request_key).json()["revision"]
        reported = self.report(
            request_key, lease_token=token, expected_revision=revision, outcome="provisioned"
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        self.assertEqual(reported.json()["status"], "provisioned")
        return member_id, token

    def rotation_count(self, request_key: str) -> int:
        with self.session() as session:
            rows = session.exec(
                select(RoleCredentialRotation).where(
                    RoleCredentialRotation.intent_key == request_key
                )
            ).all()
            return len(list(rows))

    def role_credential_version(self, member_id: str) -> int:
        with self.session() as session:
            role = session.get(ProjectRole, ("prj_alpha", member_id))
            return int(role.credential_version)

    def current_api_key(self, member_id: str) -> str:
        with self.session() as session:
            return session.get(Member, member_id).api_key

    def bump_credential_version(self, member_id: str) -> None:
        """模拟“旁路轮换”：直接把角色当前凭据版本推高一代（不产生执行记录）。"""
        with self.session() as session:
            role = session.get(ProjectRole, ("prj_alpha", member_id))
            role.credential_version = int(role.credential_version) + 1
            session.add(role)
            session.commit()

    def reprovision_after_rotation(self, member_id: str, request_key: str, token: str) -> dict:
        """轮换后重开凭据相关步骤并重新 ACK，返回成功作业。"""
        provision = self.provision_role(
            member_id,
            request_key=request_key,
            lease_token=token,
            resume=True,
        )
        self.assertEqual(provision.status_code, 200, provision.text)
        job = provision.json()
        for step in ("key_file", "preflight"):
            ack = self.ack_step(
                member_id,
                job,
                step,
                request_key=request_key,
                lease_token=token,
            )
            self.assertEqual(ack.status_code, 200, ack.text)
            job = ack.json()
        return job


class RecoveryHappyPathTests(RecoveryTestCase):
    """两轮 recover 的完整正向闭环。"""

    def test_two_recovery_rounds_each_rotate_exactly_once(self):
        member_id, _token = self.make_provisioned_role()
        base_key = self.current_api_key(member_id)

        for index, (request_key, before) in enumerate(
            ((RECOVER_KEY, 1), (SECOND_RECOVER_KEY, 2)), start=1
        ):
            with self.subTest(round=index):
                created = self.start_recover(
                    member_id, request_key=request_key, expected_version=before
                )
                self.assertEqual(created.status_code, 201, created.text)
                claimed_response = self.claim(request_key)
                self.assertEqual(claimed_response.status_code, 200, claimed_response.text)
                claimed = claimed_response.json()
                self.assertEqual(claimed["status"], "created")
                self.assertEqual(claimed["member_id"], member_id)

                rotated = self.rotate(
                    member_id,
                    {
                        "request_key": request_key,
                        "lease_token": claimed["lease_token"],
                        "expected_credential_version": before,
                    },
                )
                self.assertEqual(rotated.status_code, 201, rotated.text)
                after = before + 1
                self.assertEqual(rotated.json()["credential_version"], after)
                self.assertFalse(rotated.json()["reused"])
                self.assertTrue(rotated.json()["api_key"])
                self.assertNotEqual(rotated.json()["api_key"], base_key)
                self.assertEqual(self.rotation_count(request_key), 1)
                self.assertEqual(self.role_credential_version(member_id), after)

                job = self.reprovision_after_rotation(
                    member_id, request_key, claimed["lease_token"]
                )
                self.assertEqual(job["status"], "succeeded")
                self.assertEqual(job["credential_version"], after)

                revision = self.get_request(request_key).json()["revision"]
                reported = self.report(
                    request_key,
                    lease_token=claimed["lease_token"],
                    expected_revision=revision,
                    outcome="provisioned",
                )
                self.assertEqual(reported.status_code, 200, reported.text)
                self.assertEqual(reported.json()["status"], "provisioned")
                self.assertEqual(reported.json()["credential_version"], after)

    def test_rotation_replay_omits_key_and_does_not_rotate_again(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        body = {
            "request_key": RECOVER_KEY,
            "lease_token": claimed["lease_token"],
            "expected_credential_version": 1,
        }
        first = self.rotate(member_id, body)
        self.assertEqual(first.status_code, 201, first.text)
        issued_key = first.json()["api_key"]

        replay = self.rotate(member_id, body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["reused"])
        self.assertNotIn("api_key", replay.json())
        self.assertEqual(replay.json()["credential_version"], 2)
        self.assertEqual(self.rotation_count(RECOVER_KEY), 1)
        self.assertEqual(self.current_api_key(member_id), issued_key)

    def test_replay_wins_even_when_current_version_moved_past_after(self):
        """§7.1：正常轮换重放不能被“before 与 current 比对”拒绝。"""
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        body = {
            "request_key": RECOVER_KEY,
            "lease_token": claimed["lease_token"],
            "expected_credential_version": 1,
        }
        self.assertEqual(self.rotate(member_id, body).status_code, 201)
        self.bump_credential_version(member_id)  # 当前版本已被旁路推到 3

        replay = self.rotate(member_id, body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["reused"])
        self.assertEqual(replay.json()["credential_version"], 2)
        self.assertNotIn("api_key", replay.json())
        self.assertEqual(self.rotation_count(RECOVER_KEY), 1)


class RecoverySourceTests(RecoveryTestCase):
    """来源选择与旧旁路关闭。"""

    def test_omitting_request_key_cannot_bypass_request_driven_recovery(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()

        omitted = self.rotate(member_id)
        self.assertEqual(omitted.status_code, 409)
        self.assertEqual(omitted.json()["detail"], "provision_lease_required")

        no_request_key = self.rotate(
            member_id, {"lease_token": claimed["lease_token"]}
        )
        self.assertEqual(no_request_key.status_code, 422)

        token_without_key = self.rotate(
            member_id,
            {"request_key": "", "lease_token": claimed["lease_token"]},
        )
        self.assertEqual(token_without_key.status_code, 422)
        self.assertEqual(self.rotation_count(RECOVER_KEY), 0)

    def test_manual_role_keeps_old_no_body_rotation(self):
        manual = self.create_role(operation_key="op-manual-0001")
        self.assertEqual(manual.status_code, 201)
        member_id = manual.json()["member_id"]
        old_key = manual.json()["api_key"]
        rotated = self.rotate(member_id)
        self.assertEqual(rotated.status_code, 200, rotated.text)
        self.assertIn("api_key", rotated.json())
        self.assertEqual(rotated.json()["credential_version"], 2)
        self.assertNotEqual(rotated.json()["api_key"], old_key)

    def test_terminal_recovery_source_is_selected_exactly_not_fallback(self):
        member_id, _token = self.make_provisioned_role()
        # 第一轮 recover 走到 provisioned（终态）。
        self.start_recover(member_id, request_key=RECOVER_KEY, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        self.reprovision_after_rotation(member_id, RECOVER_KEY, claimed["lease_token"])
        revision = self.get_request(RECOVER_KEY).json()["revision"]
        self.report(
            RECOVER_KEY,
            lease_token=claimed["lease_token"],
            expected_revision=revision,
            outcome="provisioned",
        )
        self.assertEqual(self.get_request(RECOVER_KEY).json()["status"], "provisioned")

        # 第二轮 recover 成为当前活动意图。
        self.start_recover(
            member_id, request_key=SECOND_RECOVER_KEY, expected_version=2
        )
        second_response = self.claim(SECOND_RECOVER_KEY)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        second = second_response.json()
        self.assertEqual(second["status"], "created")

        # 用第一轮的 request_key：必须按**那一行**判定为终态拒绝，不能退回第二行。
        stale = self.provision_role(
            member_id,
            request_key=RECOVER_KEY,
            lease_token=claimed["lease_token"],
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"], "role_request_status_conflict")

        # 用第二轮的 request_key：走同一原 operation_key，正常建作业。
        fresh = self.provision_role(
            member_id,
            request_key=SECOND_RECOVER_KEY,
            lease_token=second["lease_token"],
        )
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()["operation_key"], "op-intent-0001")

    def test_recover_requires_matching_expected_version(self):
        member_id, _token = self.make_provisioned_role()
        mismatch = self.start_recover(member_id, expected_version=7)
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(mismatch.json()["detail"], "role_request_credential_mismatch")

    def test_recover_rejects_imported_identity(self):
        self.add_member("agent:imported", api_key="imported-key", display_name="Imported")
        self.sync_roster(
            "prj_alpha",
            [{"member_id": "agent:imported", "business_role": "dev"}],
        )
        with self.session() as session:
            session.add(
                ProjectRole(
                    project_id="prj_alpha",
                    member_id="agent:imported",
                    role_name="legacy",
                    origin="imported",
                    identity_exclusive=0,
                    credential_version=1,
                    created_by="human:bobo",
                )
            )
            session.commit()
        imported = self.start_recover("agent:imported", expected_version=1)
        self.assertEqual(imported.status_code, 409)
        self.assertEqual(
            imported.json()["detail"], "provision_imported_identity_unsupported"
        )


class RecoveryContentionTests(RecoveryTestCase):
    """supersede / resume / 终态重放的竞争守卫。"""

    def test_new_recover_supersedes_only_invalid_lease(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, request_key=RECOVER_KEY, expected_version=1)

        # 未领取的 requested 是待执行，不能被自动替代。
        blocked = self.start_recover(
            member_id, request_key=SECOND_RECOVER_KEY, expected_version=1
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_role_conflict")

        self.claim(RECOVER_KEY)
        self.force_lease_expired(RECOVER_KEY)
        replaced = self.start_recover(
            member_id, request_key=SECOND_RECOVER_KEY, expected_version=1
        )
        self.assertEqual(replaced.status_code, 201, replaced.text)

        old = self.get_request(RECOVER_KEY).json()
        self.assertEqual(old["status"], "canceled")
        self.assertEqual(old["last_error_code"], "superseded")
        self.assertIsNotNone(old["finished_at"])
        # 旧行保留（永久保留，不物理删除）。
        self.assertIsNotNone(self.request_row(RECOVER_KEY))

        resumed = self.resume(RECOVER_KEY)
        self.assertEqual(resumed.status_code, 409)
        self.assertEqual(resumed.json()["detail"], "role_request_not_resumable")

    def test_old_resume_cannot_reclaim_after_new_intent(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, request_key=RECOVER_KEY, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        revision = self.get_request(RECOVER_KEY).json()["revision"]
        failed = self.report(
            RECOVER_KEY,
            lease_token=claimed["lease_token"],
            expected_revision=revision,
            outcome="failed",
            error_code="key_file_write_failed",
        )
        self.assertEqual(failed.status_code, 200, failed.text)
        self.assertEqual(failed.json()["status"], "failed")

        # failed 不占用名额：人类可以起一个新的恢复意图。
        created = self.start_recover(
            member_id, request_key=SECOND_RECOVER_KEY, expected_version=2
        )
        self.assertEqual(created.status_code, 201, created.text)

        resumed = self.resume(RECOVER_KEY)
        self.assertEqual(resumed.status_code, 409)
        self.assertEqual(resumed.json()["detail"], "role_request_role_conflict")

    def test_old_resume_cannot_reclaim_expired_new_intent(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, request_key=RECOVER_KEY, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        revision = self.get_request(RECOVER_KEY).json()["revision"]
        failed = self.report(
            RECOVER_KEY,
            lease_token=claimed["lease_token"],
            expected_revision=revision,
            outcome="failed",
            error_code="preflight_failed",
        )
        self.assertEqual(failed.status_code, 200, failed.text)

        created = self.start_recover(
            member_id, request_key=SECOND_RECOVER_KEY, expected_version=1
        )
        self.assertEqual(created.status_code, 201, created.text)
        second = self.claim(SECOND_RECOVER_KEY).json()
        self.force_lease_expired(SECOND_RECOVER_KEY)

        # 新意图租约虽已失效，旧 resume 也不得夺回资格（不允许替代任何其它活动行）。
        resumed = self.resume(
            RECOVER_KEY,
            expected_revision=self.get_request(RECOVER_KEY).json()["revision"],
        )
        self.assertEqual(resumed.status_code, 409)
        self.assertEqual(resumed.json()["detail"], "role_request_role_conflict")

        new_row = self.get_request(SECOND_RECOVER_KEY).json()
        self.assertEqual(new_row["status"], "created")
        self.assertEqual(new_row["member_id"], member_id)
        old_row = self.get_request(RECOVER_KEY).json()
        self.assertEqual(old_row["status"], "failed")
        self.assertIsNotNone(second["lease_token"])

    def test_resume_clears_terminal_report_and_blocks_old_replay(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        revision = self.get_request(RECOVER_KEY).json()["revision"]
        self.report(
            RECOVER_KEY,
            lease_token=claimed["lease_token"],
            expected_revision=revision,
            outcome="failed",
            error_code="preflight_failed",
        )

        resumed = self.resume(RECOVER_KEY, expected_revision=revision + 1)
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["status"], "created")
        self.assertEqual(resumed.json()["attempts"], 0)
        self.assertGreater(resumed.json()["revision"], revision + 1)

        # 已 resume：旧终态回报不得覆盖（旧代际 token 已随 resume 作废）。
        replay = self.report(
            RECOVER_KEY,
            lease_token=claimed["lease_token"],
            expected_revision=revision,
            outcome="failed",
            error_code="preflight_failed",
        )
        self.assertEqual(replay.status_code, 409)
        self.assertIn(
            replay.json()["detail"],
            {"role_request_stale_report", "role_request_lease_invalid"},
        )
        self.assertEqual(self.get_request(RECOVER_KEY).json()["status"], "created")


class RecoveryNegativeTests(RecoveryTestCase):
    """租约/代际负向：每一类都零副作用。"""

    def test_expired_lease_blocks_rotation(self):
        member_id, _token = self.make_provisioned_role()
        before_key = self.current_api_key(member_id)
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        self.force_lease_expired(RECOVER_KEY)

        blocked = self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_lease_invalid")
        self.assertEqual(self.role_credential_version(member_id), 1)
        self.assertEqual(self.current_api_key(member_id), before_key)
        self.assertEqual(self.rotation_count(RECOVER_KEY), 0)

    def test_disabled_host_blocks_rotation(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        self.host_disable(expected_version=1)

        blocked = self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "provision_host_disabled")
        self.assertEqual(self.role_credential_version(member_id), 1)
        self.assertEqual(self.rotation_count(RECOVER_KEY), 0)

    def test_wrong_expected_version_in_body_is_refused(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        blocked = self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 2,
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_credential_mismatch")
        self.assertEqual(self.rotation_count(RECOVER_KEY), 0)

    def test_unknown_request_key_is_refused(self):
        member_id, _token = self.make_provisioned_role()
        blocked = self.rotate(
            member_id,
            {
                "request_key": "op-ghost-9999",
                "lease_token": "whatever-token",
                "expected_credential_version": 1,
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "role_request_operation_mismatch")

    def test_completion_requires_current_generation(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        self.assertEqual(self.role_credential_version(member_id), 2)

        # 未重开作业：作业代际仍是 1，而角色当前是 2 → 不能完成。
        revision = self.get_request(RECOVER_KEY).json()["revision"]
        stale = self.report(
            RECOVER_KEY,
            lease_token=claimed["lease_token"],
            expected_revision=revision,
            outcome="provisioned",
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"], "role_request_credential_stale")
        self.assertEqual(self.get_request(RECOVER_KEY).json()["status"], "created")

        # 旁路把角色版本再推高一代：即使作业重开也不能用旧期望代际完成。
        self.reprovision_after_rotation(member_id, RECOVER_KEY, claimed["lease_token"])
        self.bump_credential_version(member_id)
        revision = self.get_request(RECOVER_KEY).json()["revision"]
        bypassed = self.report(
            RECOVER_KEY,
            lease_token=claimed["lease_token"],
            expected_revision=revision,
            outcome="provisioned",
        )
        self.assertEqual(bypassed.status_code, 409)
        self.assertEqual(bypassed.json()["detail"], "role_request_credential_stale")

    def test_recovery_write_entries_are_human_only(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        blocked = self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
            },
            key="worker-key",
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(self.rotation_count(RECOVER_KEY), 0)


class RecoveryJobGenerationTests(RecoveryTestCase):
    """恢复后作业代际与 ACK 的衔接。"""

    def test_provision_with_recover_source_reuses_original_operation_key(self):
        member_id, _token = self.make_provisioned_role()
        self.start_recover(member_id, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        resumed = self.provision_role(
            member_id, request_key=RECOVER_KEY, lease_token=claimed["lease_token"], resume=True
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        job = resumed.json()
        self.assertEqual(job["operation_key"], "op-intent-0001")
        self.assertEqual(job["credential_version"], 2)
        self.assertEqual(job["steps"]["key_file"]["state"], "pending")
        self.assertEqual(job["steps"]["preflight"]["state"], "pending")
        # profile 与凭据无关，保留原成功事实。
        self.assertEqual(job["steps"]["profile"]["state"], "succeeded")

        with self.session() as session:
            stored = session.get(RoleProvisionJob, "op-intent-0001")
            self.assertEqual(stored.credential_version, 2)
            self.assertEqual(stored.status, "running")


class ReworkReplayOrderTests(RecoveryTestCase):
    """F2/F5 返修（恢复侧）：意图重放不受轮换影响，报告精确重放按代际识别。"""

    def test_recover_intent_replay_survives_rotation(self):
        member, _token = self.make_provisioned_role()
        self.assertEqual(self.start_recover(member, expected_version=1).status_code, 201)
        claimed = self.claim(RECOVER_KEY).json()
        rotated = self.rotate(
            member,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        self.assertEqual(rotated.status_code, 201, rotated.text)
        self.assertEqual(self.role_credential_version(member), 2)

        replay = self.start_recover(member, expected_version=1)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["request_key"], RECOVER_KEY)
        self.assertEqual(replay.json()["status"], "created")
        self.assertEqual(self.rotation_count(RECOVER_KEY), 1)

    def test_same_key_with_different_member_payload_still_conflicts(self):
        member, _token = self.make_provisioned_role()
        self.assertEqual(self.start_recover(member, expected_version=1).status_code, 201)
        other = self.create_role(role_name="ops", operation_key="op-manual-0099")
        self.assertEqual(other.status_code, 201)
        conflict = self.start_recover(other.json()["member_id"], expected_version=1)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "role_request_key_conflict")

    def test_report_replay_rejected_after_credential_generation_moved(self):
        member, token = self.make_provisioned_role()
        # 原报告的精确重复提交先确认是只读 200 重放。
        report_revision = self.get_request("op-intent-0001").json()["revision"] - 1
        exact = self.report(
            "op-intent-0001",
            lease_token=token,
            expected_revision=report_revision,
            outcome="provisioned",
        )
        self.assertEqual(exact.status_code, 200, exact.text)
        self.assertTrue(exact.json()["replayed"])

        # 后续合法轮换把角色代际推到 2：旧报告的“精确重放”必须按旧代拒绝。
        self.start_recover(member, expected_version=1)
        claimed = self.claim(RECOVER_KEY).json()
        self.assertEqual(
            self.rotate(
                member,
                {
                    "request_key": RECOVER_KEY,
                    "lease_token": claimed["lease_token"],
                    "expected_credential_version": 1,
                },
            ).status_code,
            201,
        )
        self.assertEqual(self.role_credential_version(member), 2)

        replay = self.report(
            "op-intent-0001",
            lease_token=token,
            expected_revision=report_revision,
            outcome="provisioned",
        )
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(replay.json()["detail"], "role_request_stale_report")
        self.assertEqual(self.get_request("op-intent-0001").json()["status"], "provisioned")


class ConcurrentRotationTests(RecoveryTestCase):
    """隔离 SQLite WAL + 两个独立连接：同一 recover 意图最多轮换一次。"""

    def enable_wal(self) -> None:
        with self.engine.connect() as connection:
            mode = connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar()
        self.assertEqual(str(mode).lower(), "wal")

    def test_concurrent_rotation_of_same_intent_rotates_at_most_once(self):
        member_id, _token = self.make_provisioned_role()
        self.assertEqual(self.start_recover(member_id, expected_version=1).status_code, 201)
        claimed = self.claim(RECOVER_KEY).json()
        self.enable_wal()
        body = RoleRequestRotateRequest(
            request_key=RECOVER_KEY,
            lease_token=claimed["lease_token"],
            expected_credential_version=1,
        )
        barrier = threading.Barrier(2, timeout=30)
        results: list = [None, None]
        connection_ids: list = [None, None]

        def runner(index: int) -> None:
            session = self.session()
            try:
                connection_ids[index] = id(
                    session.connection().connection.driver_connection
                )
                human = session.get(Member, "human:bobo")
                barrier.wait()
                response = rotate_project_role_key(
                    "prj_alpha", member_id, body, current=human, session=session
                )
                results[index] = ("ok", response.status_code)
            except HTTPException as exc:
                results[index] = ("http", exc.status_code, exc.detail)
            except Exception as exc:  # noqa: BLE001 - 并发异常如实记录
                results[index] = ("error", type(exc).__name__, str(exc))
            finally:
                session.close()

        threads = [
            threading.Thread(target=runner, args=(index,)) for index in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=90)

        self.assertEqual(len(set(connection_ids)), 2, connection_ids)
        self.assertTrue(all(item is not None for item in results), results)
        self.assertTrue(all(item[0] == "ok" for item in results), results)
        self.assertEqual(sorted(item[1] for item in results), [200, 201], results)
        self.assertEqual(self.rotation_count(RECOVER_KEY), 1)
        self.assertEqual(self.role_credential_version(member_id), 2)

        replay = self.rotate(
            member_id,
            {
                "request_key": RECOVER_KEY,
                "lease_token": claimed["lease_token"],
                "expected_credential_version": 1,
            },
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["reused"])
        self.assertNotIn("api_key", replay.json())
        self.assertEqual(self.rotation_count(RECOVER_KEY), 1)


if __name__ == "__main__":
    unittest.main()
