"""角色生命周期 R1-4c-a：新角色配置成功后自动首次启动（AUTO_START_DESIGN）。

覆盖 ``docs/spec/ROLE_AUTO_START_DESIGN.md`` §3–§5：

- 新 create 意图（``auto_start=true``）+ 真实 ``require_completion_facts`` 全绿 +
  首次有效 ``report(provisioned)`` → 恰好 1 个 pending start launch + ``enqueued``
  锚点；自动审计身份是 ``system:auto-start``（不冒充 human）；
- 旧请求 / 旧客户端（无字段）/ ``auto_start=false`` / recover → 零 launch；
- 人工意图优先：stop-before-report、先手动 start 都被守卫拒绝（``not_eligible`` +
  ``auto_start_manual_intent_present``），不覆盖人工世代；
- ``unknown`` / ``external_session`` 运行器 → ``not_eligible`` +
  ``auto_start_control_kind_not_managed``，不产生 pending launch；
- 重复 / 迟到回报纯读重放，零新增 launch；worker 重试 claim 409；
- 真实 SQLite 触发器：launch INSERT 失败 → SAVEPOINT 回滚、配置仍 ``provisioned``、
  ``failed/auto_start_enqueue_failed``、零残留；外层写失败 → 整体回滚 500，去掉
  触发器后同 token 重试恰好 1 个 launch；入队触发器撤销整个外层事务
  （``RAISE(ROLLBACK)``）→ 500、无 auto 状态补写、旧事实保持，去故障重试
  恰好 1 个 launch；双连接在提交前看不见半提交事实；
- 共享入队核心（``enqueue_auto_start_launch``）直接测试：不 commit、守卫翻译、
  已有状态行时 CAS 后失败可完整回滚到保存点；
- 宿主离线：pending launch 120 秒过期收敛为 ``readiness_timeout``，
  ``auto_start_status`` 保持 ``enqueued``（投递事实不倒写）；
- 投影只增 4 个白名单字段，不回显 ``auto_start_intent`` 原始 int。

全部用例使用进程内 TestClient 与隔离临时库；不启动真实宿主/CLI/模型，不读真实 Key。
"""

from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import text
from sqlmodel import Session, select

from server.models import (
    ROLE_AUTO_START_ACTOR,
    ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED,
    ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED,
    ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT,
    ROLE_SERVICE_LAUNCH_EXPIRED,
    ROLE_SERVICE_OBSERVED_FAILED,
    ROLE_SERVICE_OBSERVED_STARTING,
    ROLE_SERVICE_OBSERVED_STOPPED,
    ROLE_SERVICE_ERROR_READINESS_TIMEOUT,
    ROLE_SERVICE_ERROR_UNKNOWN_OWNER,
    ProjectRole,
    ProjectRoleBinding,
    RoleNativeSetup,
    RoleProvisionRequestRow,
    RoleServiceLaunch,
    RoleServiceState,
    RunnerRegistry,
)
from server.role_provision_requests import _set_auto_start, enqueue_pending_auto_start
from server.role_services import (
    enqueue_auto_start_launch,
    expire_due_launches,
)
from server.db import begin_immediate_write
from tests.test_role_provision_requests import RoleRequestApiTestCase
from tests.test_project_roles import RUNNER_ID

MANAGED_RUNNER = RUNNER_ID
UNKNOWN_RUNNER = "runner:unknown-cli"
EXTERNAL_RUNNER = "runner:external-cli"
REQUEST_KEY = "op-auto-0001"


def encode(member_id: str) -> str:
    return quote(member_id, safe="")


class AutoStartApiTestCase(RoleRequestApiTestCase):
    """R1-4c-a 公共夹具：把角色驱动到“配置成功待回报”状态。"""

    # ── 小工具 ───────────────────────────────────────────────────────

    def patch_control_kind(self, runner_id: str, control_kind: str):
        with self.make_client() as client:
            return client.patch(
                f"/api/runners/{runner_id}/control-kind",
                headers={"X-API-Key": "bobo-key"},
                json={"control_kind": control_kind},
            )

    def make_managed(self, runner_id: str = MANAGED_RUNNER):
        response = self.patch_control_kind(runner_id, "managed_cli")
        self.assertEqual(response.status_code, 200, response.text)

    def service_start(self, member_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/prj_alpha/roles/{encode(member_id)}/service/start",
                headers={"X-API-Key": key},
            )

    def service_stop(self, member_id: str, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/prj_alpha/roles/{encode(member_id)}/service/stop",
                headers={"X-API-Key": key},
            )

    def launch_claim(self, launch_id: str, body: dict, *, key: str):
        with self.make_client() as client:
            return client.post(
                f"/api/role-service-launches/{launch_id}/claim",
                headers={"X-API-Key": key},
                json=body,
            )

    def provision_job(self, member_id: str, operation_key: str, lease_token: str):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/prj_alpha/roles/{encode(member_id)}/provision",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "operation_key": operation_key,
                    "request_key": operation_key,
                    "lease_token": lease_token,
                },
            )

    def ack_step(
        self,
        member_id: str,
        *,
        operation_key: str,
        step: str,
        revision: int,
        lease_token: str,
    ):
        with self.make_client() as client:
            return client.post(
                f"/api/projects/prj_alpha/roles/{encode(member_id)}/provision/ack",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "operation_key": operation_key,
                    "request_key": operation_key,
                    "lease_token": lease_token,
                    "step": step,
                    "attempt": 1,
                    "revision": revision,
                    "credential_version": 1,
                    "state": "succeeded",
                },
            )

    def drive_to_created(self, *, auto_start=True, runner_id: str = MANAGED_RUNNER,
                         choice_id: str | None = None, request_key: str = REQUEST_KEY):
        """意图 → claim → C1 原子创建；返回 ``(created_body, lease_token)``。"""
        self.enable_host()
        body: dict = {
            "request_key": request_key,
            "auto_start": auto_start,
            "runner_id": runner_id,
            "choice_id": choice_id or self.choice_id,
        }
        if auto_start is None:
            body.pop("auto_start")
        intent = self.create_intent(**body)
        self.assertEqual(intent.status_code, 201, intent.text)
        claimed = self.claim(request_key).json()
        created = self.create_role(
            operation_key=request_key,
            lease_token=claimed["lease_token"],
            runner_id=runner_id,
            choice_id=choice_id or self.choice_id,
        )
        self.assertEqual(created.status_code, 201, created.text)
        return created.json(), claimed["lease_token"]

    def finish_job_and_report(self, member_id: str, lease_token: str,
                              *, request_key: str = REQUEST_KEY):
        """建作业 → 三步 ACK 全绿 → report(provisioned)；返回 report 响应。"""
        job = self.provision_job(member_id, request_key, lease_token)
        self.assertEqual(job.status_code, 201, job.text)
        for step, revision in (("profile", 1), ("key_file", 2), ("preflight", 3)):
            ack = self.ack_step(
                member_id,
                operation_key=request_key,
                step=step,
                revision=revision,
                lease_token=lease_token,
            )
            self.assertEqual(ack.status_code, 200, ack.text)
        current = self.get_request(request_key).json()
        return self.report(
            request_key,
            lease_token=lease_token,
            expected_revision=current["revision"],
            outcome="provisioned",
        )

    def happy_path(self, *, auto_start=True, runner_id: str = MANAGED_RUNNER,
                   choice_id: str | None = None, request_key: str = REQUEST_KEY,
                   manage: bool = True):
        if manage:
            self.make_managed(runner_id)
        created, token = self.drive_to_created(
            auto_start=auto_start, runner_id=runner_id, choice_id=choice_id,
            request_key=request_key,
        )
        member_id = created["member_id"]
        reported = self.finish_job_and_report(member_id, token, request_key=request_key)
        return created, token, reported

    # ── 直读事实 ─────────────────────────────────────────────────────

    def launch_rows(self, member_id: str) -> list[RoleServiceLaunch]:
        with self.session() as session:
            return list(
                session.exec(
                    select(RoleServiceLaunch).where(
                        RoleServiceLaunch.project_id == "prj_alpha",
                        RoleServiceLaunch.member_id == member_id,
                    )
                ).all()
            )

    def state_row(self, member_id: str) -> RoleServiceState | None:
        with self.session() as session:
            return session.get(RoleServiceState, ("prj_alpha", member_id))

    def raw_counts(self) -> dict:
        with self.session() as session:
            return {
                "launches": len(list(session.exec(select(RoleServiceLaunch)).all())),
                "states": len(list(session.exec(select(RoleServiceState)).all())),
            }


class AutoStartHappyPathTests(AutoStartApiTestCase):
    """AUTO_START_DESIGN §3/§5：唯一一次成功入队的端到端链路。"""

    def test_create_auto_start_provisioned_enqueues_exactly_one_launch(self):
        created, _token, reported = self.happy_path()
        member_id = created["member_id"]

        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertEqual(body["status"], "provisioned")
        self.assertFalse(body["replayed"])
        # 意图/投递事实投影：enqueued 只是已投递，不等于 ready。
        self.assertTrue(body["auto_start"])
        self.assertEqual(body["auto_start_status"], "enqueued")
        self.assertIsNone(body["auto_start_error_code"])
        launch_id = body["auto_start_launch_id"]
        self.assertTrue(launch_id)

        # 恰好 1 个 pending start launch；真实 binding/control_kind/CAS 语义。
        launches = self.launch_rows(member_id)
        self.assertEqual(len(launches), 1)
        launch = launches[0]
        self.assertEqual(launch.launch_id, launch_id)
        self.assertEqual(launch.action, "start")
        self.assertEqual(launch.state, "pending")
        self.assertEqual(launch.generation, 1)
        self.assertTrue(launch.expected_instance_id.startswith("ins_"))

        # 自动入队形成非零世代；审计身份是 system:auto-start，不冒充 human。
        state = self.state_row(member_id)
        self.assertIsNotNone(state)
        self.assertEqual(state.generation, 1)
        self.assertEqual(state.desired_state, "running")
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_STARTING)
        self.assertEqual(state.control_kind, "managed_cli")
        self.assertEqual(state.current_launch_id, launch_id)
        self.assertEqual(state.updated_by, ROLE_AUTO_START_ACTOR)
        # 真实启动还需宿主 claim/report/实例就绪；pending 不是工作证明。
        role = None
        with self.session() as session:
            role = session.get(ProjectRole, ("prj_alpha", member_id))
        self.assertEqual(role.credential_version, 1)

    def test_exact_replay_and_conflicting_outcome_add_zero_launches(self):
        created, token, reported = self.happy_path()
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        revision = reported.json()["revision"]
        before = self.launch_rows(member_id)
        self.assertEqual(len(before), 1)

        replay = self.report(
            REQUEST_KEY,
            lease_token=token,
            expected_revision=revision - 1,  # report 前的 revision
            outcome="provisioned",
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["replayed"])
        after = self.launch_rows(member_id)
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].launch_id, before[0].launch_id)
        self.assertEqual(
            self.get_request(REQUEST_KEY).json()["auto_start_launch_id"],
            before[0].launch_id,
        )

        conflicted = self.report(
            REQUEST_KEY,
            lease_token=token,
            expected_revision=revision - 1,
            outcome="failed",
            error_code="profile_write_failed",
        )
        self.assertEqual(conflicted.status_code, 409)
        self.assertEqual(conflicted.json()["detail"], "role_request_stale_report")
        self.assertEqual(len(self.launch_rows(member_id)), 1)

    def test_native_setup_ready_resumes_pending_auto_start_once(self):
        with self.session() as session:
            runner = session.get(RunnerRegistry, RUNNER_ID)
            runner.runtime = "codex"
            session.add(runner)
            session.commit()
        from unittest.mock import patch
        with patch("server.kimi_native_setup.schedule_auto_native_setup") as scheduled:
            created, _token, reported = self.happy_path()
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertTrue(body["auto_start"])
        self.assertEqual(body["auto_start_status"], "pending")
        self.assertIsNone(body["auto_start_launch_id"])
        self.assertEqual(body["auto_start_error_code"], "native_authorization_required")
        self.assertEqual(self.launch_rows(member_id), [])
        scheduled.assert_called_once_with("prj_alpha", member_id)

        with self.session() as session:
            setup = session.get(RoleNativeSetup, ("prj_alpha", member_id))
            self.assertEqual(setup.status, "required")
            setup.status = "ready"
            session.add(setup)
            session.commit()

        enqueue_pending_auto_start("prj_alpha", member_id)
        current = self.get_request(REQUEST_KEY).json()
        self.assertEqual(current["auto_start_status"], "enqueued")
        self.assertTrue(current["auto_start_launch_id"])
        launches = self.launch_rows(member_id)
        self.assertEqual(len(launches), 1)
        self.assertEqual(launches[0].launch_id, current["auto_start_launch_id"])

        # 重复回调/刷新不得投递第二次。
        enqueue_pending_auto_start("prj_alpha", member_id)
        self.assertEqual(len(self.launch_rows(member_id)), 1)

    def test_ready_callback_only_revives_pending_not_terminal_states(self):
        with self.session() as session:
            runner = session.get(RunnerRegistry, RUNNER_ID)
            runner.runtime = "codex"
            session.add(runner)
            session.commit()
        from unittest.mock import patch
        with patch("server.kimi_native_setup.schedule_auto_native_setup"):
            created, _token, reported = self.happy_path()
        member_id = created["member_id"]
        self.assertEqual(reported.json()["auto_start_status"], "pending")
        for status, code in (
            ("not_eligible", "auto_start_config_disabled"),
            ("failed", "auto_start_enqueue_failed"),
            ("enqueued", None),
            (None, None),
        ):
            with self.subTest(status=status):
                with self.session() as session:
                    request = session.get(RoleProvisionRequestRow, REQUEST_KEY)
                    request.auto_start_status = status
                    request.auto_start_error_code = code
                    request.auto_start_launch_id = None
                    session.add(request)
                    setup = session.get(RoleNativeSetup, ("prj_alpha", member_id))
                    setup.status = "ready"
                    session.add(setup)
                    session.commit()
                enqueue_pending_auto_start("prj_alpha", member_id)
                self.assertEqual(self.launch_rows(member_id), [],
                    f"{status!r} must not be revived by a later ready callback")
                current = self.get_request(REQUEST_KEY).json()
                self.assertEqual(current["auto_start_status"], status)
                self.assertIsNone(current["auto_start_launch_id"])

    def test_worker_retry_claim_after_terminal_is_status_conflict(self):
        created, token, reported = self.happy_path()
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        retried = self.claim(REQUEST_KEY)
        self.assertEqual(retried.status_code, 409)
        self.assertEqual(retried.json()["detail"], "role_request_status_conflict")
        self.assertEqual(len(self.launch_rows(member_id)), 1)

    def test_auto_enqueued_stop_expires_pending_launch_and_advances_generation(self):
        created, _token, reported = self.happy_path()
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        launch_id = reported.json()["auto_start_launch_id"]
        launch = self.launch_rows(member_id)[0]

        stopped = self.service_stop(member_id)
        self.assertEqual(stopped.status_code, 200, stopped.text)
        # 既有所有权/世代合同：自动入队后的 stop 与人工 start 后一致。
        self.assertEqual(stopped.json()["generation"], 2)

        after = self.launch_rows(member_id)
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].state, ROLE_SERVICE_LAUNCH_EXPIRED)
        self.assertEqual(after[0].error_code, ROLE_SERVICE_ERROR_UNKNOWN_OWNER)
        state = self.state_row(member_id)
        self.assertEqual(state.generation, 2)
        self.assertEqual(state.desired_state, "stopped")
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_STOPPED)

        # 迟到 claim 被既有 launch_expired 拒绝，绝不重新拉起。
        late = self.launch_claim(
            launch_id,
            {"host": "host-alpha", "expected_instance_id": launch.expected_instance_id},
            key=created["api_key"],
        )
        self.assertEqual(late.status_code, 409)
        self.assertEqual(late.json()["detail"], "launch_expired")
        self.assertEqual(len(self.launch_rows(member_id)), 1)

    def test_host_offline_expiry_keeps_enqueued_status(self):
        created, _token, reported = self.happy_path()
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        # 宿主离线：120 秒后 pending launch 被过期扫描收敛（真实实现函数）。
        future = datetime.now(timezone.utc) + timedelta(seconds=121)
        with self.session() as session:
            expired = expire_due_launches(
                session, now=future, project_id="prj_alpha", member_id=member_id
            )
            session.commit()
        self.assertEqual(expired, 1)
        state = self.state_row(member_id)
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_FAILED)
        self.assertEqual(state.last_error_code, ROLE_SERVICE_ERROR_READINESS_TIMEOUT)
        # 启动失败不倒写配置/投递事实。
        projection = self.get_request(REQUEST_KEY).json()
        self.assertEqual(projection["status"], "provisioned")
        self.assertEqual(projection["auto_start_status"], "enqueued")
        self.assertTrue(projection["auto_start_launch_id"])


class AutoStartIntentMatrixTests(AutoStartApiTestCase):
    """AUTO_START_DESIGN §3：意图缺省/false/旧请求/recover 零启动。"""

    def test_legacy_request_without_field_never_starts(self):
        created, _token, reported = self.happy_path(auto_start=None)
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertFalse(body["auto_start"])
        self.assertIsNone(body["auto_start_status"])
        self.assertIsNone(body["auto_start_launch_id"])
        self.assertEqual(len(self.launch_rows(member_id)), 0)
        self.assertIsNone(self.state_row(member_id))
        row = self.request_row(REQUEST_KEY)
        self.assertEqual(row.auto_start_intent, 0)

    def test_explicit_false_never_starts(self):
        created, _token, reported = self.happy_path(auto_start=False)
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertFalse(body["auto_start"])
        self.assertIsNone(body["auto_start_status"])
        self.assertEqual(len(self.launch_rows(member_id)), 0)
        row = self.request_row(REQUEST_KEY)
        self.assertEqual(row.auto_start_intent, 0)

    def test_failed_report_never_starts_or_retries(self):
        self.enable_host()
        intent = self.create_intent(request_key=REQUEST_KEY, auto_start=True)
        self.assertEqual(intent.status_code, 201, intent.text)
        claimed = self.claim(REQUEST_KEY).json()
        reported = self.report(
            REQUEST_KEY,
            lease_token=claimed["lease_token"],
            expected_revision=claimed["revision"],
            outcome="failed",
            error_code="preflight_failed",
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertEqual(body["status"], "failed")
        # 配置 failed：绝不产生 launch，意图停在 pending，不后台重试。
        self.assertEqual(body["auto_start_status"], "pending")
        self.assertIsNone(body["auto_start_launch_id"])
        self.assertEqual(self.raw_counts(), {"launches": 0, "states": 0})

    def test_canceled_request_never_starts(self):
        self.enable_host()
        self.assertEqual(
            self.create_intent(request_key=REQUEST_KEY, auto_start=True).status_code,
            201,
        )
        canceled = self.cancel(REQUEST_KEY)
        self.assertEqual(canceled.status_code, 200, canceled.text)
        self.assertEqual(canceled.json()["status"], "canceled")
        self.assertEqual(self.raw_counts(), {"launches": 0, "states": 0})

    def test_recover_intent_rejects_auto_start_field(self):
        created, _token, _ = self.happy_path(request_key="op-auto-recover-src")
        member_id = created["member_id"]
        # 用旧角色的成员做 recover；auto_start 非 None 一律 422 互斥载荷。
        for value in (True, False):
            response = self.create_intent(
                request_key="op-auto-recover-1",
                kind="recover",
                role_name=None,
                runner_id=None,
                choice_id=None,
                member_id=member_id,
                expected_credential_version=1,
                auto_start=value,
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(
                response.json()["detail"], "role_request_payload_invalid"
            )
        # recover 本身不带该字段时可以创建（恢复只修复，不自动启动）。
        ok = self.create_intent(
            request_key="op-auto-recover-1",
            kind="recover",
            role_name=None,
            runner_id=None,
            choice_id=None,
            member_id=member_id,
            expected_credential_version=1,
        )
        self.assertEqual(ok.status_code, 201, ok.text)
        self.assertFalse(ok.json()["auto_start"])
        self.assertIsNone(ok.json()["auto_start_status"])


class ManualIntentFirstTests(AutoStartApiTestCase):
    """AUTO_START_DESIGN §3：任何已发生的人工服务动作优先于自动启动。"""

    def test_stop_before_report_blocks_auto_start(self):
        # 配置完成回报**之前**人工关闭：新角色无状态行 → 人工 stop 落 gen1。
        self.enable_host()
        intent = self.create_intent(request_key=REQUEST_KEY, auto_start=True)
        self.assertEqual(intent.status_code, 201, intent.text)
        claimed = self.claim(REQUEST_KEY).json()
        created = self.create_role(
            operation_key=REQUEST_KEY, lease_token=claimed["lease_token"]
        )
        self.assertEqual(created.status_code, 201, created.text)
        member_id = created.json()["member_id"]

        stopped = self.service_stop(member_id)
        self.assertEqual(stopped.status_code, 200, stopped.text)
        state = self.state_row(member_id)
        self.assertEqual(state.generation, 1)
        self.assertEqual(state.updated_by, "human:bobo")
        self.assertEqual(state.observed_state, ROLE_SERVICE_OBSERVED_STOPPED)

        reported = self.finish_job_and_report(member_id, claimed["lease_token"])
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        # 配置仍如实 provisioned；自动启动如实未入队。
        self.assertEqual(body["status"], "provisioned")
        self.assertEqual(body["auto_start_status"], "not_eligible")
        self.assertEqual(
            body["auto_start_error_code"],
            ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT,
        )
        self.assertIsNone(body["auto_start_launch_id"])
        self.assertEqual(len(self.launch_rows(member_id)), 0)
        # 人工事实不被覆盖：世代仍为 1，updated_by 仍是 human。
        state = self.state_row(member_id)
        self.assertEqual(state.generation, 1)
        self.assertEqual(state.updated_by, "human:bobo")
        self.assertEqual(state.desired_state, "stopped")

    def test_manual_start_before_report_blocks_second_generation(self):
        self.make_managed()
        created, token = self.drive_to_created()
        member_id = created["member_id"]
        started = self.service_start(member_id)
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["generation"], 1)
        # 人工 start 已产生 1 个 pending launch。
        self.assertEqual(len(self.launch_rows(member_id)), 1)

        reported = self.finish_job_and_report(member_id, token)
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertEqual(body["auto_start_status"], "not_eligible")
        self.assertEqual(
            body["auto_start_error_code"],
            ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT,
        )
        self.assertIsNone(body["auto_start_launch_id"])
        # 不覆盖、不加第二个世代、不产生第二个动作。
        state = self.state_row(member_id)
        self.assertEqual(state.generation, 1)
        self.assertEqual(state.updated_by, "human:bobo")
        self.assertEqual(len(self.launch_rows(member_id)), 1)


class NotEligibleCapabilityTests(AutoStartApiTestCase):
    """AUTO_START_DESIGN §3/§6.3：运行器不可受管如实拒绝，不伪造 ready。"""

    def _unmanaged_pipeline(self, runner_id: str):
        self.register_runner(runner_id)
        choice = self.create_choice(runner_id).json()["choice_id"]
        created, token, reported = self.happy_path(
            runner_id=runner_id, choice_id=choice, manage=False
        )
        return created, token, reported

    def test_unknown_control_kind_is_not_eligible_without_launch(self):
        # 不 PATCH control-kind：登记默认 unknown（生产目录真实形态）。
        created, _token, reported = self._unmanaged_pipeline(UNKNOWN_RUNNER)
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertEqual(body["auto_start_status"], "not_eligible")
        self.assertEqual(
            body["auto_start_error_code"],
            ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED,
        )
        self.assertIsNone(body["auto_start_launch_id"])
        # 绝不挂一个没人能领取的 pending launch 等超时。
        self.assertEqual(len(self.launch_rows(member_id)), 0)
        self.assertIsNone(self.state_row(member_id))

    def test_external_session_control_kind_is_not_eligible(self):
        # 先注册再 PATCH：此前对未注册运行器 PATCH 得 404 被忽略，
        # 用例实际退回 unknown 分支，并未覆盖 external_session。
        self.register_runner(EXTERNAL_RUNNER)
        patched = self.patch_control_kind(EXTERNAL_RUNNER, "external_session")
        self.assertEqual(patched.status_code, 200, patched.text)
        with self.session() as session:
            runner = session.get(RunnerRegistry, EXTERNAL_RUNNER)
            self.assertIsNotNone(runner)
            self.assertEqual(runner.control_kind, "external_session")
        created, _token, reported = self._unmanaged_pipeline(EXTERNAL_RUNNER)
        member_id = created["member_id"]
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertEqual(body["auto_start_status"], "not_eligible")
        self.assertEqual(
            body["auto_start_error_code"],
            ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED,
        )
        self.assertIsNone(body["auto_start_launch_id"])
        self.assertEqual(len(self.launch_rows(member_id)), 0)
        self.assertIsNone(self.state_row(member_id))

    def test_missing_binding_is_not_eligible(self):
        # 角色有运行器但绑定缺失（真实守卫 ROLE_SERVICE_ERROR_ROLE_BINDING_MISSING
        # 如实翻译）：直接驱动共享入队核心验证稳定码映射。
        created, _token, _ = self.happy_path()
        member_id = created["member_id"]
        with self.session() as session:
            binding = session.get(ProjectRoleBinding, ("prj_alpha", member_id))
            session.delete(binding)
            session.commit()
        with self.session() as session:
            begin_immediate_write(session)
            launch_id, code = enqueue_auto_start_launch(
                "prj_alpha", member_id, session=session, now=datetime.now(timezone.utc)
            )
            session.rollback()
        self.assertIsNone(launch_id)
        self.assertEqual(
            code, ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED
        )


class EnqueueCoreTransactionTests(AutoStartApiTestCase):
    """共享入队核心的直接测试：不 commit、失败翻译、保存点回滚语义。"""

    def test_core_never_commits_by_itself(self):
        """共享核心绝不 commit：未显式提交前，第二个连接看不见任何写入。"""
        self.make_managed()
        created, _token = self.drive_to_created()
        member_id = created["member_id"]
        self.assertEqual(self.raw_counts(), {"launches": 0, "states": 0})

        session = Session(self.engine)
        try:
            begin_immediate_write(session)
            launch_id, code = enqueue_auto_start_launch(
                "prj_alpha", member_id, session=session, now=datetime.now(timezone.utc)
            )
            self.assertIsNotNone(launch_id)
            self.assertIsNone(code)
            # 核心没有自己的提交点：第二个连接仍读到旧事实（无 state、无 launch）。
            self.assertEqual(self.raw_counts(), {"launches": 0, "states": 0})
            session.rollback()
        finally:
            session.close()
        # 回滚后依然零写入：调用方完全控制事务边界。
        self.assertEqual(self.raw_counts(), {"launches": 0, "states": 0})

    def test_core_maps_conflict_to_stable_code_without_httpexception(self):
        """共享核心对外的自动入口：冲突/守卫失败只回稳定码，不抛 HTTPException。"""
        from server.role_services import _enqueue_start_launch, load_role_service_context

        self.make_managed()
        created, _token = self.drive_to_created()
        member_id = created["member_id"]
        with self.session() as session:
            begin_immediate_write(session)
            ctx = load_role_service_context("prj_alpha", member_id, session)
            # 传一个**过期的预期世代**：CAS 必须失败（rowcount=0），核心如实抛
            # 世代冲突 HTTPException，由自动入口翻译为稳定码。
            with self.assertRaises(Exception) as raised:
                _enqueue_start_launch(
                    ctx, "prj_alpha", member_id, session=session,
                    now=datetime.now(timezone.utc), actor_id=ROLE_AUTO_START_ACTOR,
                    expected_generation=7,
                )
            session.rollback()
        from fastapi import HTTPException

        self.assertIsInstance(raised.exception, HTTPException)
        self.assertEqual(raised.exception.detail, "generation_conflict")
        self.assertEqual(self.raw_counts(), {"launches": 0, "states": 0})

    def test_core_rolls_back_partial_state_inside_savepoint(self):
        """D2：已有 gen=1 状态行时，CAS 1→2 后 launch 失败 → 保存点回滚到 gen=1。"""
        # 不跑完整 report（避免自动入队先建状态行）：C1 创建角色后人工关闭，
        # 得到 gen=1、无所有权的既有状态行（stop-before-report 等价物）。
        self.make_managed()
        created, _token = self.drive_to_created()
        member_id = created["member_id"]
        stopped = self.service_stop(member_id)
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(len(self.launch_rows(member_id)), 0)

        with self.engine.connect() as conn:
            conn.exec_driver_sql(
                "CREATE TRIGGER boom_partial BEFORE INSERT ON role_service_launches "
                "BEGIN SELECT RAISE(ABORT, 'boom_partial'); END"
            )
            conn.commit()
        try:
            with self.session() as session:
                begin_immediate_write(session)
                savepoint = session.begin_nested()
                with self.assertRaises(Exception):
                    enqueue_auto_start_launch(
                        "prj_alpha", member_id, session=session,
                        now=datetime.now(timezone.utc),
                    )
                savepoint.rollback()
                session.rollback()
        finally:
            with self.engine.connect() as conn:
                conn.exec_driver_sql("DROP TRIGGER IF EXISTS boom_partial")
                conn.commit()
        # 部分 state 更新被保存点完整回滚：世代不变、零 launch、无新增状态行。
        state = self.state_row(member_id)
        self.assertEqual(state.generation, 1)
        self.assertEqual(state.desired_state, "stopped")
        self.assertEqual(len(self.launch_rows(member_id)), 0)

    def test_set_auto_start_uses_core_update_without_orm_drift(self):
        """_set_auto_start 走 Core UPDATE；同事务内随后的 ORM flush 不误回写。"""
        created, token, _ = self.happy_path()
        member_id = created["member_id"]
        with self.session() as session:
            begin_immediate_write(session)
            row = session.get(RoleProvisionRequestRow, REQUEST_KEY)
            _set_auto_start(
                session,
                REQUEST_KEY,
                status="not_eligible",
                code=ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT,
                now=datetime.now(timezone.utc),
            )
            # 同事务内其它 ORM 写（模拟外层后续动作）不能覆盖 Core UPDATE。
            row.lease_host = "host-desktop-1"
            session.add(row)
            session.flush()
            got = session.execute(
                text(
                    "SELECT auto_start_status, auto_start_error_code "
                    "FROM role_provision_requests WHERE request_key=:k"
                ),
                {"k": REQUEST_KEY},
            ).one()
            session.rollback()
        self.assertEqual(
            tuple(got),
            ("not_eligible", ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT),
        )


class ReportFailureInjectionTests(AutoStartApiTestCase):
    """真实 SQLite 触发器注入：走完整 HTTP report 链路的故障边界。"""

    def _create_trigger(self, name: str, sql: str) -> None:
        with self.engine.connect() as conn:
            conn.exec_driver_sql(f"CREATE TRIGGER {name} {sql}")
            conn.commit()

    def _drop_trigger(self, name: str) -> None:
        with self.engine.connect() as conn:
            conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {name}")
            conn.commit()

    def test_launch_insert_failure_rolls_back_savepoint_only(self):
        """D1：launch INSERT 失败 → 外层 200、配置仍 provisioned、failed、零残留。"""
        created, token = self.drive_to_created()
        member_id = created["member_id"]
        self.make_managed()
        job = self.provision_job(member_id, REQUEST_KEY, token)
        self.assertEqual(job.status_code, 201, job.text)
        for step, revision in (("profile", 1), ("key_file", 2), ("preflight", 3)):
            ack = self.ack_step(
                member_id, operation_key=REQUEST_KEY, step=step,
                revision=revision, lease_token=token,
            )
            self.assertEqual(ack.status_code, 200, ack.text)

        self._create_trigger(
            "boom_launch_insert",
            "BEFORE INSERT ON role_service_launches "
            "BEGIN SELECT RAISE(ABORT, 'boom_launch_insert'); END",
        )
        try:
            current = self.get_request(REQUEST_KEY).json()
            reported = self.report(
                REQUEST_KEY,
                lease_token=token,
                expected_revision=current["revision"],
                outcome="provisioned",
            )
        finally:
            self._drop_trigger("boom_launch_insert")

        # 入队失败不倒写配置失败：report 如实成功，配置仍 provisioned。
        self.assertEqual(reported.status_code, 200, reported.text)
        body = reported.json()
        self.assertEqual(body["status"], "provisioned")
        self.assertEqual(body["status"], "provisioned")
        self.assertEqual(body["auto_start_status"], "failed")
        self.assertEqual(
            body["auto_start_error_code"], ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED
        )
        self.assertIsNone(body["auto_start_launch_id"])
        # 保存点回滚零残留：无半截 state 行、无 launch。
        self.assertEqual(len(self.launch_rows(member_id)), 0)
        self.assertIsNone(self.state_row(member_id))
        # 精确重放（保存点后同一次提交）仍是只读：仍 failed、仍 0 launch。
        replay = self.report(
            REQUEST_KEY,
            lease_token=token,
            expected_revision=current["revision"],
            outcome="provisioned",
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(len(self.launch_rows(member_id)), 0)

    def test_lost_outer_transaction_propagates_500_without_side_effects(self):
        """F1：入队触发器 RAISE(ROLLBACK) 撤销整个外层事务 → 500、无补写、重试 1 launch。"""
        created, token = self.drive_to_created()
        member_id = created["member_id"]
        self.make_managed()
        job = self.provision_job(member_id, REQUEST_KEY, token)
        self.assertEqual(job.status_code, 201, job.text)
        for step, revision in (("profile", 1), ("key_file", 2), ("preflight", 3)):
            ack = self.ack_step(
                member_id, operation_key=REQUEST_KEY, step=step,
                revision=revision, lease_token=token,
            )
            self.assertEqual(ack.status_code, 200, ack.text)
        current = self.get_request(REQUEST_KEY).json()

        # BEFORE INSERT 触发器 RAISE(ROLLBACK)：SQLite 撤销整个外层写事务。
        self._create_trigger(
            "destroy_outer",
            "BEFORE INSERT ON role_service_launches "
            "BEGIN SELECT RAISE(ROLLBACK, 'destroy_outer'); END",
        )
        try:
            failed = self.report(
                REQUEST_KEY,
                lease_token=token,
                expected_revision=current["revision"],
                outcome="provisioned",
            )
        finally:
            self._drop_trigger("destroy_outer")

        # 外层事务已损坏：必须 500 整体回滚，不能吞掉失效事务再 200/补写。
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(failed.json()["detail"], "role_request_report_failed")
        # 旧事实保持：created/pending、原 revision、无 launch/state/锚点、无 auto 补写。
        after = self.get_request(REQUEST_KEY).json()
        self.assertEqual(after["status"], current["status"])
        self.assertEqual(after["revision"], current["revision"])
        self.assertEqual(after["auto_start_status"], "pending")
        self.assertIsNone(after["auto_start_launch_id"])
        self.assertIsNone(after["auto_start_error_code"])
        self.assertEqual(len(self.launch_rows(member_id)), 0)
        self.assertIsNone(self.state_row(member_id))

        # 去故障后同 token/同 revision 重试：200/enqueued、恰好 1 launch。
        retried = self.report(
            REQUEST_KEY,
            lease_token=token,
            expected_revision=current["revision"],
            outcome="provisioned",
        )
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(retried.json()["auto_start_status"], "enqueued")
        self.assertEqual(len(self.launch_rows(member_id)), 1)
        # 精确重放（同一次提交）零新增。
        replay = self.report(
            REQUEST_KEY,
            lease_token=token,
            expected_revision=current["revision"],
            outcome="provisioned",
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(len(self.launch_rows(member_id)), 1)

    def test_outer_write_failure_rolls_back_and_retry_delivers_one_launch(self):
        """D4：外层写失败 → 整体回滚 500；去掉触发器后同 token 重试恰好 1 个 launch。"""
        created, token = self.drive_to_created()
        member_id = created["member_id"]
        self.make_managed()
        job = self.provision_job(member_id, REQUEST_KEY, token)
        self.assertEqual(job.status_code, 201, job.text)
        for step, revision in (("profile", 1), ("key_file", 2), ("preflight", 3)):
            ack = self.ack_step(
                member_id, operation_key=REQUEST_KEY, step=step,
                revision=revision, lease_token=token,
            )
            self.assertEqual(ack.status_code, 200, ack.text)
        current = self.get_request(REQUEST_KEY).json()

        self._create_trigger(
            "boom_outer",
            "BEFORE UPDATE ON role_provision_requests "
            "BEGIN SELECT RAISE(ROLLBACK, 'boom_outer'); END",
        )
        try:
            failed = self.report(
                REQUEST_KEY,
                lease_token=token,
                expected_revision=current["revision"],
                outcome="provisioned",
            )
        finally:
            self._drop_trigger("boom_outer")
        # 外层提交失败如实 500，不承诺数据库失败仍 200。
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(failed.json()["detail"], "role_request_report_failed")
        # 整体回滚零残留：请求行停留原状态，launch/state 均未出现。
        after = self.get_request(REQUEST_KEY).json()
        self.assertEqual(after["status"], current["status"])
        self.assertEqual(after["revision"], current["revision"])
        self.assertEqual(after["auto_start_status"], current["auto_start_status"])
        self.assertIsNone(after["auto_start_launch_id"])
        self.assertEqual(len(self.launch_rows(member_id)), 0)
        self.assertIsNone(self.state_row(member_id))

        # 同 token/同 revision 安全重试：恰好 1 个 launch + 锚点。
        retried = self.report(
            REQUEST_KEY,
            lease_token=token,
            expected_revision=current["revision"],
            outcome="provisioned",
        )
        self.assertEqual(retried.status_code, 200, retried.text)
        body = retried.json()
        self.assertEqual(body["status"], "provisioned")
        self.assertEqual(body["auto_start_status"], "enqueued")
        self.assertTrue(body["auto_start_launch_id"])
        launches = self.launch_rows(member_id)
        self.assertEqual(len(launches), 1)
        self.assertEqual(launches[0].launch_id, body["auto_start_launch_id"])

    def test_uncommitted_facts_invisible_to_second_connection(self):
        """D3：外层提交前另一连接只读到旧事实；提交后读到 provisioned + 1 launch。"""
        created, token = self.drive_to_created()
        member_id = created["member_id"]
        self.make_managed()
        job = self.provision_job(member_id, REQUEST_KEY, token)
        self.assertEqual(job.status_code, 201, job.text)
        for step, revision in (("profile", 1), ("key_file", 2), ("preflight", 3)):
            ack = self.ack_step(
                member_id, operation_key=REQUEST_KEY, step=step,
                revision=revision, lease_token=token,
            )
            self.assertEqual(ack.status_code, 200, ack.text)
        revision = self.get_request(REQUEST_KEY).json()["revision"]

        def second_connection_facts() -> tuple:
            conn = sqlite3.connect(self.db_path)
            try:
                status = conn.execute(
                    "SELECT status, revision FROM role_provision_requests "
                    "WHERE request_key=?",
                    (REQUEST_KEY,),
                ).fetchone()
                launches = conn.execute(
                    "SELECT COUNT(*) FROM role_service_launches"
                ).fetchone()[0]
                states = conn.execute(
                    "SELECT COUNT(*) FROM role_service_state"
                ).fetchone()[0]
                return status, launches, states
            finally:
                conn.close()

        session = Session(self.engine)
        try:
            begin_immediate_write(session)
            row = session.get(RoleProvisionRequestRow, REQUEST_KEY)
            now = datetime.now(timezone.utc)
            row.status = "provisioned"
            row.report_outcome = "provisioned"
            row.report_revision = revision
            row.lease_expires_at = now
            row.revision = int(row.revision or 1) + 1
            row.updated_at = now
            row.finished_at = now
            session.add(row)
            session.flush()
            # 真实实现：保存点内共享核心入队（与 report 成功分支同一路径）。
            savepoint = session.begin_nested()
            launch_id, code = enqueue_auto_start_launch(
                "prj_alpha", member_id, session=session, now=now
            )
            self.assertIsNotNone(launch_id)
            self.assertIsNone(code)
            savepoint.commit()
            _set_auto_start(
                session, REQUEST_KEY, status="enqueued", code=None, now=now,
                launch_id=launch_id,
            )
            # ★ 提交前：第二个连接必须看不到任何半提交事实。
            before = second_connection_facts()
            self.assertEqual(before[0][:1], ("created",))
            self.assertEqual(before[1:], (0, 0))
            session.commit()
            # ★ 提交后：第二个连接读到完整事实（无半提交）。
            after = second_connection_facts()
            self.assertEqual(after[0][:1], ("provisioned",))
            self.assertEqual(after[1:], (1, 1))
        finally:
            session.close()
        projection = self.get_request(REQUEST_KEY).json()
        self.assertEqual(projection["auto_start_status"], "enqueued")
        self.assertEqual(len(self.launch_rows(member_id)), 1)


class ProjectionAndPermissionTests(AutoStartApiTestCase):
    """投影白名单与 human-only 边界（AUTO_START_DESIGN §2/§5）。"""

    def test_projection_exposes_four_readonly_fields_only(self):
        self.enable_host()
        intent = self.create_intent(request_key=REQUEST_KEY, auto_start=True)
        self.assertEqual(intent.status_code, 201, intent.text)
        body = intent.json()
        self.assertTrue(body["auto_start"])
        self.assertEqual(body["auto_start_status"], "pending")
        self.assertIsNone(body["auto_start_launch_id"])
        self.assertIsNone(body["auto_start_error_code"])
        # 原始 int 与任何凭据形态不回显。
        self.assertNotIn("auto_start_intent", body)
        self.assertNotIn("lease_token", body)
        listed = self.list_requests().json()
        self.assertEqual(set(listed[0].keys()), set(body.keys()))

    def test_agent_cannot_write_intent_or_service(self):
        denied = self.create_intent(request_key=REQUEST_KEY, auto_start=True, key="worker-key")
        self.assertEqual(denied.status_code, 403)
        created, _token, _ = self.happy_path()
        member_id = created["member_id"]
        start = self.service_start(member_id, key="worker-key")
        self.assertEqual(start.status_code, 403)
        stop = self.service_stop(member_id, key="worker-key")
        self.assertEqual(stop.status_code, 403)


if __name__ == "__main__":
    unittest.main()
