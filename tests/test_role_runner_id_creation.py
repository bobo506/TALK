"""角色生命周期 R1-4 补正：创建/配置链 ``runner_id`` 与注册同源（真实运行器 ID 形状）。

背景（#240 独立复核发现、本片修正）：``scripts/adapter_binding_facts.py`` 生成的运行器 ID
形如 ``runner:<runtime[:24]>-<sha256[:32]>``，对 ``kimi-code`` 会产生 42 个连续 token 字符，
命中 ``server/models.py`` 的**凭据启发式** ``CREDENTIAL_LIKE_PATTERN = [A-Za-z0-9+/=_\\-]{40,}``。
注册入口 ``POST /api/runners`` 用 ``normalize_runner_id``（slug、≤64）接受该 ID，而创建入口
（``POST /roles`` 与 ``POST /role-requests``）曾用 ``normalize_safe_identifier_token``，
于是同一个已登记的真实 ID「登记成功、创建恒 422」。

本模块锁定的合同语义：

1. 角色创建/配置链的 ``runner_id`` 一律用注册同源的 ``normalize_runner_id``：真实形状、
   生成器形状与 ≤64 合法长 ID 一致通过；超长/大小写/非法字符按注册合同 422；
   未知但**合法**的 runner 仍是 404（不是靠“已登记豁免”放宽，也不是削弱全局启发式）；
2. 两个入口（R1-4 请求驱动 ``/role-requests`` 与 R1-1 直建 ``/roles``）规范化与指纹同源：
   同 ``operation_key``/``request_key`` 同载荷回放不重复身份、不返 Key，目录退役后已提交
   意图的精确重放保持；
3. 下游链路（claim → 请求来源创建 → 六表 → 作业 → 三步 ACK → report）也走真实 ID，
   不出现“改了两入口、下游又用 safe token 失败”；
4. 其他字段的凭据/语法防护不弱化：``choice_id``/模型维度/``error_code`` 仍走
   ``normalize_safe_identifier_token``；agent 目录/请求/直建仍 403；
   ``control_kind=unknown`` 的运行器仍不能被启动。

全部用例使用进程内 ``TestClient`` + 隔离 SQLite（``.tmp-tests`` 下临时目录）与仓库外
临时假 Key 根；不读真实 Key、不启模型/原生 CLI/Browser、不写生产 ``talk.db``/名册/配置。
"""

from __future__ import annotations

import io
import logging
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone

from sqlmodel import select

from scripts.adapter_binding_facts import runner_id_for
from server.models import (
    Member,
    ProjectAgent,
    ProjectRole,
    ProjectRoleBinding,
    RoleCreationOperation,
    RoleProvisionRequestRow,
    RunnerModelChoice,
    RunnerRegistry,
    is_safe_identifier_token,
    looks_like_credential,
    normalize_runner_id,
    normalize_safe_identifier_token,
)
from tests.test_project_roles import RoleApiTestCase
from tests.test_role_creation_request_guard import CreateGuardTestCase
from tests.test_role_provision_requests import (
    FORBIDDEN_SUBSTRINGS,
    PUBLIC_PROJECTION_KEYS,
    RoleRequestApiTestCase,
)
from tests.test_role_provision_worker import HOST_LABEL, WorkerTestCase

#: 生产真实形状（项目工具生成、已登记、adapter_status=unverified / control_kind=unknown）。
REAL_RUNNER_ID = "runner:kimi-code-1aabe894a3c21096ad9c7f5211aa7e33"
REAL_RUNTIME = "kimi-code"
REAL_DIMENSIONS = {
    "model_id": "kimi-for-coding",
    "model_source": "builtin",
    "provider_id": "managed:kimi-code",
    "connection_ref": "native-kimi-code-managed-login",
    "model_alias": "kimi-code/kimi-for-coding",
    "model_display_name": "K2.8 Preview",
}
#: 与全局凭据启发式同阈值：连续 ≥40 个 ``[A-Za-z0-9+/=_\-]`` 字符。
_TOKEN_RUN = re.compile(r"[A-Za-z0-9+/=_\-]{40,}")

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


def longest_token_run(value: str) -> int:
    return max((len(match.group(0)) for match in _TOKEN_RUN.finditer(value)), default=0)


class RunnerIdContractTests(unittest.TestCase):
    """纯规则层：注册同源归一 + 全局启发式**未**被削弱。"""

    def test_global_credential_heuristic_still_flags_real_runner_id(self):
        self.assertFalse(is_safe_identifier_token(REAL_RUNNER_ID))
        self.assertTrue(looks_like_credential(REAL_RUNNER_ID))
        self.assertGreaterEqual(longest_token_run(REAL_RUNNER_ID), 40)
        with self.assertRaises(ValueError):
            normalize_safe_identifier_token(REAL_RUNNER_ID, field="runner_id")
        # 修正只发生在 runner_id 消费者：注册归一仍接受同一 ID（未改全局启发式）。
        self.assertEqual(normalize_runner_id(REAL_RUNNER_ID), REAL_RUNNER_ID)

    def test_generator_style_id_is_same_shape_and_within_slug_contract(self):
        generated = runner_id_for(
            "kimi-code",
            host_scope="host-desktop-1",
            workspace_scope="claude-test-TALK",
        )["runner_id"]
        self.assertTrue(generated.startswith("runner:kimi-code-"))
        self.assertLessEqual(len(generated), 64)
        self.assertGreaterEqual(longest_token_run(generated), 40)
        self.assertEqual(normalize_runner_id(generated), generated)

    def test_slug_length_and_charset_boundary(self):
        max_ok = "runner:" + "a" * 24 + "-" + "b" * 32  # 恰好 64
        self.assertEqual(len(max_ok), 64)
        self.assertEqual(normalize_runner_id(max_ok), max_ok)
        too_long = "runner:" + "a" * 25 + "-" + "b" * 32  # 65
        self.assertEqual(len(too_long), 65)
        for bad in (too_long, "Runner:DSH", "runner:dsh cli", "runner:dsh@cli", "runner:bad\nslug", ""):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    normalize_runner_id(bad)

    def test_other_dimensions_keep_safe_token_rule(self):
        with self.assertRaises(ValueError):
            normalize_safe_identifier_token("rmc_" + "a" * 45, field="choice_id")
        with self.assertRaises(ValueError):
            normalize_safe_identifier_token("Bearer abcdef", field="choice_id")
        with self.assertRaises(ValueError):
            normalize_safe_identifier_token("https://user:pass@host/x", field="choice_id")


class RealRunnerFixtureMixin:
    """真实运行器 + 真实模型维度选择（unverified / unknown，登记事实不被改写）。"""

    def seed_real_runner_and_choice(self, *, adapter_status: str = "unverified") -> str:
        registered = self.register_runner(
            REAL_RUNNER_ID, runtime=REAL_RUNTIME, adapter_status=adapter_status
        )
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertEqual(registered.json()["control_kind"], "unknown")
        created = self.create_choice(REAL_RUNNER_ID, **REAL_DIMENSIONS)
        self.assertEqual(created.status_code, 201, created.text)
        return created.json()["choice_id"]


class RealRunnerApiTestCase(RoleRequestApiTestCase, RealRunnerFixtureMixin):
    """公共夹具（无测试方法）：隔离库 + 真实运行器/模型选择 + 两个入口的薄封装。"""

    def setUp(self):
        super().setUp()
        self.real_choice_id = self.seed_real_runner_and_choice()

    def real_intent(self, request_key: str = "op-intent-0001", **overrides):
        body = {
            "request_key": request_key,
            "runner_id": REAL_RUNNER_ID,
            "choice_id": self.real_choice_id,
            "role_name": "k28-请求链",
        }
        body.update(overrides)
        return self.create_intent(**body)

    def direct_create(self, **overrides):
        body = {
            "runner_id": REAL_RUNNER_ID,
            "choice_id": self.real_choice_id,
            "role_name": "k28-直建",
            "operation_key": "op-real-direct-01",
        }
        body.update(overrides)
        return self.create_role(**body)


class RealRunnerRequestIntentTests(RealRunnerApiTestCase):
    """R1-4 请求驱动创建入口：真实 ``runner_id`` 的接受 / 拒绝 / 防护边界。"""

    def test_real_runner_id_intent_is_accepted_and_projected_without_secrets(self):
        response = self.real_intent()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["status"], "requested")
        self.assertEqual(body["runner_id"], REAL_RUNNER_ID)
        self.assertEqual(body["choice_id"], self.real_choice_id)
        self.assertTrue(set(body).issubset(PUBLIC_PROJECTION_KEYS), sorted(set(body)))
        for forbidden in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(forbidden, response.text)

        row = self.request_row("op-intent-0001")
        self.assertIsNotNone(row)
        self.assertEqual(row.payload["runner_id"], REAL_RUNNER_ID)
        self.assertEqual(row.choice_snapshot["runner_id"], REAL_RUNNER_ID)
        self.assertEqual(row.choice_snapshot["runtime"], REAL_RUNTIME)
        self.assertEqual(row.choice_snapshot["model_id"], REAL_DIMENSIONS["model_id"])
        self.assertEqual(row.status, "requested")
        self.assertIsNone(row.lease_token_hash)

    def test_short_id_intent_still_works_next_to_real_id(self):
        short = self.create_intent()  # 既有短 ID（runner:dsh-cli）行为不变
        self.assertEqual(short.status_code, 201, short.text)
        real = self.real_intent(request_key="op-intent-0002")
        self.assertEqual(real.status_code, 201, real.text)

    def test_padded_real_runner_id_normalizes_like_registration(self):
        response = self.real_intent(runner_id=f"  {REAL_RUNNER_ID}  ")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["runner_id"], REAL_RUNNER_ID)
        self.assertEqual(self.request_row("op-intent-0001").payload["runner_id"], REAL_RUNNER_ID)

    def test_unknown_but_legal_runner_id_is_still_404(self):
        unknown = "runner:" + "f" * 40  # 合法 slug、≥40 连续字符、未登记
        self.assertEqual(normalize_runner_id(unknown), unknown)
        self.assertFalse(is_safe_identifier_token(unknown))
        response = self.real_intent(request_key="op-intent-0003", runner_id=unknown)
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["detail"], "runner_not_found")
        with self.session() as session:
            self.assertEqual(list(session.exec(select(RoleProvisionRequestRow)).all()), [])

    def test_illegal_runner_id_shapes_are_422_and_write_nothing(self):
        illegal = {
            "uppercase": "Runner:Kimi-Code",
            "space": "runner:dsh cli",
            "at-sign": "runner:dsh@cli",
            "overlong": "runner:" + "a" * 25 + "-" + "b" * 32,
            "inner-newline": "runner:bad\nslug",
            "empty": "",
        }
        for index, (label, value) in enumerate(illegal.items()):
            with self.subTest(shape=label):
                response = self.real_intent(
                    request_key=f"op-intent-bad-{index}", runner_id=value
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"], "role_request_payload_invalid")
        with self.session() as session:
            self.assertEqual(list(session.exec(select(RoleProvisionRequestRow)).all()), [])

    def test_choice_id_credential_guard_is_not_weakened(self):
        for index, choice_id in enumerate(
            ("rmc_" + "a" * 45, "Bearer abcdef", "https://user:pass@host/x")
        ):
            with self.subTest(choice_id=choice_id[:12]):
                response = self.real_intent(
                    request_key=f"op-intent-choice-{index}", choice_id=choice_id
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"], "role_request_payload_invalid")
        with self.session() as session:
            self.assertEqual(list(session.exec(select(RoleProvisionRequestRow)).all()), [])

    def test_operation_key_and_request_key_credential_guard_is_not_weakened(self):
        """``request_key``/``operation_key`` 仍是 8–128 安全 token（含凭据启发式）。"""
        long_key = "op" + "-" + "a" * 45
        intent = self.real_intent(request_key=long_key)
        self.assertEqual(intent.status_code, 422, intent.text)
        self.assertEqual(intent.json()["detail"], "role_request_payload_invalid")
        direct = self.direct_create(operation_key=long_key)
        self.assertEqual(direct.status_code, 422, direct.text)
        with self.session() as session:
            self.assertEqual(list(session.exec(select(RoleProvisionRequestRow)).all()), [])
            self.assertEqual(list(session.exec(select(RoleCreationOperation)).all()), [])

    def test_model_dimension_credential_guard_is_not_weakened(self):
        """模型目录登记维度（connection_ref/provider_id/model_id）仍走安全 token 规则。"""
        for index, overrides in enumerate(
            (
                {"connection_ref": "native-" + "a" * 45},
                {"provider_id": "managed-" + "b" * 45},
                {"model_id": "sk-" + "c" * 45},
            )
        ):
            with self.subTest(field=next(iter(overrides))):
                body = dict(REAL_DIMENSIONS)
                body.update(overrides)
                body["model_id"] = body["model_id"] + f"-{index}"
                with self.make_client() as client:
                    response = client.post(
                        f"/api/runners/{REAL_RUNNER_ID}/model-choices",
                        headers={"X-API-Key": "bobo-key"},
                        json=body,
                    )
                self.assertEqual(response.status_code, 422, response.text)
        with self.session() as session:
            rows = list(
                session.exec(
                    select(RunnerModelChoice).where(
                        RunnerModelChoice.runner_id == REAL_RUNNER_ID
                    )
                ).all()
            )
        # 真实运行器下只有夹具自己登记的那一条 choice，没有任何被放宽写入的维度。
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].connection_ref, REAL_DIMENSIONS["connection_ref"])
        self.assertEqual(rows[0].provider_id, REAL_DIMENSIONS["provider_id"])
        self.assertEqual(rows[0].model_id, REAL_DIMENSIONS["model_id"])

    def test_choice_of_another_runner_and_unknown_choice_are_404(self):
        self.register_runner("runner:other-cli", runtime="dsh")
        other = self.create_choice("runner:other-cli")
        mismatched = self.real_intent(
            request_key="op-intent-0004", choice_id=other.json()["choice_id"]
        )
        self.assertEqual(mismatched.status_code, 404, mismatched.text)
        self.assertEqual(mismatched.json()["detail"], "choice_not_found")
        missing = self.real_intent(request_key="op-intent-0005", choice_id="rmc_000000000000")
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(missing.json()["detail"], "choice_not_found")

    def test_retired_runner_and_retired_choice_conflict(self):
        with self.session() as session:
            runner = session.get(RunnerRegistry, REAL_RUNNER_ID)
            assert runner is not None
            runner.adapter_status = "retired"
            session.add(runner)
            session.commit()
        retired_runner = self.real_intent(request_key="op-intent-0006")
        self.assertEqual(retired_runner.status_code, 409, retired_runner.text)
        self.assertEqual(retired_runner.json()["detail"], "runner_retired")

        with self.session() as session:
            runner = session.get(RunnerRegistry, REAL_RUNNER_ID)
            assert runner is not None
            runner.adapter_status = "unverified"
            choice = session.get(RunnerModelChoice, self.real_choice_id)
            assert choice is not None
            choice.retired_at = datetime.now(timezone.utc)
            session.add(runner)
            session.add(choice)
            session.commit()
        retired_choice = self.real_intent(request_key="op-intent-0007")
        self.assertEqual(retired_choice.status_code, 409, retired_choice.text)
        self.assertEqual(retired_choice.json()["detail"], "choice_retired")

    def test_model_choice_and_request_writes_remain_human_only(self):
        self.assertEqual(self.real_intent(key="worker-key").status_code, 403)
        with self.make_client() as client:
            response = client.post(
                f"/api/runners/{REAL_RUNNER_ID}/model-choices",
                headers={"X-API-Key": "worker-key"},
                json={
                    "model_id": "kimi-for-coding",
                    "model_source": "builtin",
                    "provider_id": "managed:kimi-code",
                    "connection_ref": "native-kimi-code-managed-login",
                },
            )
        self.assertEqual(response.status_code, 403)
        with self.session() as session:
            self.assertEqual(list(session.exec(select(RoleProvisionRequestRow)).all()), [])
            self.assertEqual(len(list(session.exec(select(RunnerModelChoice)).all())), 2)


class RealRunnerDirectRoleTests(RealRunnerApiTestCase):
    """R1-1 直建入口：真实 ID 201、六表、Key 只一次、重放 200 不返 Key。"""

    def test_direct_role_creation_with_real_runner_id_writes_six_tables_once(self):
        response = self.direct_create()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        member_id = body["member_id"]
        self.assertTrue(body["api_key"])
        self.assertEqual(body["credential_version"], 1)
        self.assertFalse(body["reused"])
        self.assertEqual(body["role"]["runner"]["runner_id"], REAL_RUNNER_ID)
        self.assertEqual(body["role"]["runner"]["status"], "unverified")
        self.assertEqual(body["role"]["binding_state"], "bound")
        self.assertEqual(body["role"]["model"]["choice_id"], self.real_choice_id)

        with self.session() as session:
            self.assertIsNotNone(session.get(Member, member_id))
            role = session.get(ProjectRole, ("prj_alpha", member_id))
            self.assertIsNotNone(role)
            self.assertEqual(role.role_name, "k28-直建")
            self.assertIsNotNone(session.get(ProjectAgent, ("prj_alpha", member_id)))
            binding = session.get(ProjectRoleBinding, ("prj_alpha", member_id))
            self.assertIsNotNone(binding)
            self.assertEqual(binding.runner_id, REAL_RUNNER_ID)
            self.assertEqual(binding.model_id, REAL_DIMENSIONS["model_id"])
            self.assertEqual(binding.model_alias, REAL_DIMENSIONS["model_alias"])
            self.assertEqual(binding.model_source, REAL_DIMENSIONS["model_source"])
            self.assertEqual(binding.provider_id, REAL_DIMENSIONS["provider_id"])
            self.assertEqual(binding.connection_ref, REAL_DIMENSIONS["connection_ref"])
            operation = session.get(RoleCreationOperation, "op-real-direct-01")
            self.assertIsNotNone(operation)
            self.assertEqual(operation.runner_id, REAL_RUNNER_ID)
            self.assertEqual(operation.member_id, member_id)
            self.assertEqual(operation.choice_id, self.real_choice_id)

        replay = self.direct_create()
        self.assertEqual(replay.status_code, 200, replay.text)
        replay_body = replay.json()
        self.assertTrue(replay_body["reused"])
        self.assertNotIn("api_key", replay_body)
        self.assertEqual(replay_body["member_id"], member_id)
        self.assertEqual(self.raw_member_count(), 1)
        self.assertEqual(self.role_count(), 1)

    def test_direct_creation_rejects_unknown_and_illegal_runner_id(self):
        unknown = self.direct_create(
            runner_id="runner:" + "e" * 40, operation_key="op-real-direct-02"
        )
        self.assertEqual(unknown.status_code, 404, unknown.text)
        self.assertEqual(unknown.json()["detail"], "runner_not_found")
        for index, value in enumerate(
            ("Runner:Kimi-Code", "runner:dsh cli", "runner:dsh@cli", "r" * 65)
        ):
            with self.subTest(shape=value[:16]):
                response = self.direct_create(
                    runner_id=value, operation_key=f"op-real-direct-bad-{index}"
                )
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.raw_member_count(), 0)
        self.assertEqual(self.role_count(), 0)

    def test_unknown_control_real_runner_cannot_be_started(self):
        created = self.direct_create(operation_key="op-real-direct-03")
        self.assertEqual(created.status_code, 201, created.text)
        member_id = created.json()["member_id"]
        with self.make_client() as client:
            started = client.post(
                f"/api/projects/prj_alpha/roles/{member_id}/service/start",
                headers={"X-API-Key": "bobo-key"},
            )
        self.assertEqual(started.status_code, 409, started.text)
        self.assertEqual(started.json()["detail"], "control_kind_not_managed")
        with self.session() as session:
            runner = session.get(RunnerRegistry, REAL_RUNNER_ID)
            assert runner is not None
            self.assertEqual(runner.adapter_status, "unverified")
            self.assertEqual(runner.control_kind, "unknown")
            binding = session.get(ProjectRoleBinding, ("prj_alpha", member_id))
            assert binding is not None
            self.assertEqual(binding.runner_id, REAL_RUNNER_ID)
            self.assertEqual(binding.model_id, REAL_DIMENSIONS["model_id"])


class RealRunnerPipelineTests(CreateGuardTestCase, RealRunnerFixtureMixin):
    """请求来源完整链路 + 回放/退役语义，全部使用真实 ``runner_id``。"""

    ROLE_NAME = "k28-链路"

    def setUp(self):
        super().setUp()
        self.real_choice_id = self.seed_real_runner_and_choice()

    def seed_real_pipeline(self, request_key: str = "op-real-chain-01"):
        """意图 → claim → 请求来源创建；返回 ``(created_body, lease_token)``。"""
        self.enable_host()
        intent = self.create_intent(
            request_key=request_key,
            runner_id=REAL_RUNNER_ID,
            choice_id=self.real_choice_id,
            role_name=self.ROLE_NAME,
        )
        self.assertEqual(intent.status_code, 201, intent.text)
        claimed = self.claim(request_key).json()
        created = self.create_role(
            runner_id=REAL_RUNNER_ID,
            choice_id=self.real_choice_id,
            role_name=self.ROLE_NAME,
            operation_key=request_key,
            lease_token=claimed["lease_token"],
        )
        self.assertEqual(created.status_code, 201, created.text)
        return created.json(), claimed["lease_token"]

    def test_request_sourced_creation_job_ack_report_with_real_runner_id(self):
        request_key = "op-real-chain-01"
        created, token = self.seed_real_pipeline(request_key)
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

        reported = self.report(request_key, lease_token=token)
        self.assertEqual(reported.status_code, 200, reported.text)
        final = self.get_request(request_key).json()
        self.assertEqual(final["status"], "provisioned")
        self.assertEqual(final["member_id"], member_id)
        self.assertEqual(final["runner_id"], REAL_RUNNER_ID)
        self.assertIsNotNone(final["provision_job"])
        self.assertEqual(final["provision_job"]["status"], "succeeded")
        for forbidden in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(forbidden, reported.text)

        with self.session() as session:
            row = session.get(RoleProvisionRequestRow, request_key)
            assert row is not None
            self.assertEqual(row.status, "provisioned")
            self.assertEqual(row.payload["runner_id"], REAL_RUNNER_ID)
            self.assertEqual(row.choice_snapshot["runner_id"], REAL_RUNNER_ID)
            operation = session.get(RoleCreationOperation, request_key)
            assert operation is not None
            self.assertEqual(operation.runner_id, REAL_RUNNER_ID)
            binding = session.get(ProjectRoleBinding, ("prj_alpha", member_id))
            assert binding is not None
            self.assertEqual(binding.runner_id, REAL_RUNNER_ID)
            self.assertEqual(binding.model_alias, REAL_DIMENSIONS["model_alias"])

    def test_replay_before_and_after_retirement_keeps_one_identity(self):
        request_key = "op-real-chain-02"
        self.enable_host()
        first = self.create_intent(
            request_key=request_key,
            runner_id=REAL_RUNNER_ID,
            choice_id=self.real_choice_id,
            role_name=self.ROLE_NAME,
        )
        self.assertEqual(first.status_code, 201, first.text)
        # 未 claim 的同键同载荷重放：仍是 requested，不重复建意图。
        self.assertEqual(first.json()["status"], "requested")
        self.assertEqual(self.raw_member_count(), 0)

        claimed = self.claim(request_key).json()
        created = self.create_role(
            runner_id=REAL_RUNNER_ID,
            choice_id=self.real_choice_id,
            role_name=self.ROLE_NAME,
            operation_key=request_key,
            lease_token=claimed["lease_token"],
        )
        self.assertEqual(created.status_code, 201, created.text)
        member_id = created.json()["member_id"]
        token = claimed["lease_token"]
        revision_after_create = self.get_request(request_key).json()["revision"]

        replay = self.create_intent(
            request_key=request_key,
            runner_id=REAL_RUNNER_ID,
            choice_id=self.real_choice_id,
            role_name=self.ROLE_NAME,
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["member_id"], member_id)
        self.assertEqual(replay.json()["revision"], revision_after_create)
        self.assertEqual(self.raw_member_count(), 1)
        self.assertEqual(self.role_count(), 1)

        # 请求来源的直建入口同键回放：200 reused，不返 Key、不重复身份。
        replay_create = self.create_role(
            runner_id=REAL_RUNNER_ID,
            choice_id=self.real_choice_id,
            role_name=self.ROLE_NAME,
            operation_key=request_key,
            lease_token=token,
        )
        self.assertEqual(replay_create.status_code, 200, replay_create.text)
        self.assertTrue(replay_create.json()["reused"])
        self.assertNotIn("api_key", replay_create.json())

        # 目录退役/下架后：已提交意图的精确重放仍返回原行，不被实时目录状态阻断。
        self.retire_choice(self.real_choice_id)
        with self.session() as session:
            runner = session.get(RunnerRegistry, REAL_RUNNER_ID)
            assert runner is not None
            runner.adapter_status = "retired"
            session.add(runner)
            session.commit()
        after_retirement = self.create_intent(
            request_key=request_key,
            runner_id=REAL_RUNNER_ID,
            choice_id=self.real_choice_id,
            role_name=self.ROLE_NAME,
        )
        self.assertEqual(after_retirement.status_code, 200, after_retirement.text)
        self.assertEqual(after_retirement.json()["member_id"], member_id)
        self.assertEqual(after_retirement.json()["revision"], revision_after_create)
        self.assertEqual(self.raw_member_count(), 1)
        self.assertEqual(self.role_count(), 1)

    def test_new_intent_after_retirement_still_conflicts(self):
        request_key = "op-real-chain-03"
        self.enable_host()
        self.assertEqual(
            self.create_intent(
                request_key=request_key,
                runner_id=REAL_RUNNER_ID,
                choice_id=self.real_choice_id,
                role_name=self.ROLE_NAME,
            ).status_code,
            201,
        )
        self.retire_choice(self.real_choice_id)
        fresh = self.create_intent(
            request_key="op-real-chain-04",
            runner_id=REAL_RUNNER_ID,
            choice_id=self.real_choice_id,
            role_name=self.ROLE_NAME,
        )
        self.assertEqual(fresh.status_code, 409, fresh.text)
        self.assertEqual(fresh.json()["detail"], "choice_retired")


class RealRunnerWorkerTests(WorkerTestCase):
    """隔离 worker 三步 / ACK / report 闭环：真实 ``runner_id``（仓库外假 Key 根）。"""

    runner_id = REAL_RUNNER_ID

    def seed_runner_and_choice(self, *, runner_id: str = REAL_RUNNER_ID) -> str:
        registered = self.register_runner(
            REAL_RUNNER_ID, runtime=REAL_RUNTIME, adapter_status="unverified"
        )
        self.assertEqual(registered.status_code, 201, registered.text)
        created = self.create_choice(REAL_RUNNER_ID, **REAL_DIMENSIONS)
        self.assertEqual(created.status_code, 201, created.text)
        return created.json()["choice_id"]

    def create_intent(self, request_key: str, *, kind: str = "create", **extra):
        body = {
            "request_key": request_key,
            "kind": kind,
            "confirm": True,
            "role_name": "dev",
            "runner_id": self.runner_id,
            "choice_id": self.choice_id,
        }
        body.update(extra)
        with self.make_client() as client:
            return client.post(
                "/api/projects/prj_alpha/role-requests",
                headers={"X-API-Key": "bobo-key"},
                json=body,
            )

    def create_role_via_api(self, request_key: str, lease_token: str):
        with self.make_client() as client:
            return client.post(
                "/api/projects/prj_alpha/roles",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "role_name": "dev",
                    "runner_id": self.runner_id,
                    "choice_id": self.choice_id,
                    "operation_key": request_key,
                    "lease_token": lease_token,
                },
            )

    def test_worker_loop_with_real_runner_id_provisions_and_reports(self):
        self.assertEqual(self.enable_host().status_code, 200)
        intent = self.create_intent("op-intent-real-worker")
        self.assertEqual(intent.status_code, 201, intent.text)
        worker = self.make_worker()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = worker.process("op-intent-real-worker")
        self.assertEqual(result["outcome"], "provisioned", result)
        self.assertIsNone(result["error_code"])
        for step in ("profile", "key_file", "preflight"):
            self.assertIn(
                result["steps"][step]["state"], ("succeeded", "skipped"), result["steps"]
            )

        request = self.get_request("op-intent-real-worker")
        self.assertEqual(request["status"], "provisioned")
        self.assertEqual(request["member_id"], result["member_id"])
        self.assertEqual(request["runner_id"], REAL_RUNNER_ID)
        member_id = result["member_id"]

        # 真实私有 Key 文件内容 = 服务端签发的一次性 Key（假 Key，不读生产凭据）。
        key_path = self.key_file(member_id)
        self.assertTrue(key_path.is_file())
        self.assertTrue(self.role_api_key(member_id))

        # 创建流程不改运行器登记/控制事实，也不接管任何进程。
        with self.session() as session:
            runner = session.get(RunnerRegistry, REAL_RUNNER_ID)
            assert runner is not None
            self.assertEqual(runner.adapter_status, "unverified")
            self.assertEqual(runner.control_kind, "unknown")
            binding = session.get(ProjectRoleBinding, ("prj_alpha", member_id))
            assert binding is not None
            self.assertEqual(binding.runner_id, REAL_RUNNER_ID)
            self.assertEqual(binding.model_id, REAL_DIMENSIONS["model_id"])
            operation = session.get(RoleCreationOperation, "op-intent-real-worker")
            assert operation is not None
            self.assertEqual(operation.runner_id, REAL_RUNNER_ID)


if __name__ == "__main__":  # pragma: no cover - 手工运行入口
    unittest.main()
