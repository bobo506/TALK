"""角色生命周期 R1-1：运行器模型选择目录与控制能力合同测试。

覆盖实施计划 §3.2/§3.3（`GET/POST/PATCH .../model-choices`、`PATCH .../control-kind`）与
合同 §4.1.1、§5.1、§12、§14（I32/I33）：

- 稳定 ``choice_id``（``rmc_<12hex>``）与六维唯一键：同运行器同 ``model_id`` 的不同
  provider/connection/alias **可并存**；
- 同维度重复 POST → 200 复用同一 ``choice_id``，只更新显式提供的展示/来源字段；
- 选择维度不可变（409 ``choice_dimension_immutable``）、未知字段 422；
- ``retired_at`` 软下架只影响默认读取与新选择，不物理删除、不回写历史绑定；
- human-only 写入、agent 403；运行器不存在 404、退役 409 ``runner_retired``；
- 旧 ``GET /api/runners`` 只新增 ``control_kind``，旧键不减不改。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型、不读凭据。
"""

from __future__ import annotations

import re
import unittest

from sqlmodel import select

from server.models import RunnerModelChoice, RunnerRegistry
from tests.test_support import RouteTestCase

RUNNER_ID = "runner:dsh-cli"
CHOICE_ID_PATTERN = re.compile(r"^rmc_[0-9a-f]{12}\Z")


class RunnerModelChoiceTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")

    # ── helpers ──────────────────────────────────────────────────────

    def register_runner(
        self, runner_id: str = RUNNER_ID, *, adapter_status: str = "adapted", key: str = "bobo-key"
    ):
        with self.make_client() as client:
            return client.post(
                "/api/runners",
                headers={"X-API-Key": key},
                json={
                    "runner_id": runner_id,
                    "runtime": "dsh",
                    "display_name": "DSH CLI",
                    "adapter_status": adapter_status,
                },
            )

    def choice_payload(self, **overrides):
        body = {
            "model_id": "deepseek-flash",
            "model_source": "builtin",
            "provider_id": "managed:deepseek",
            "connection_ref": "native-deepseek-managed-login",
            "model_alias": "deepseek-flash",
            "model_display_name": "DeepSeek Flash",
            "source_kind": "declared",
            "capabilities": ["prompt-argv"],
        }
        body.update(overrides)
        return body

    def post_choice(self, body, *, runner_id: str = RUNNER_ID, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.post(
                f"/api/runners/{runner_id}/model-choices",
                headers={"X-API-Key": key},
                json=body,
            )

    def patch_choice(self, choice_id: str, body, *, runner_id: str = RUNNER_ID, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.patch(
                f"/api/runners/{runner_id}/model-choices/{choice_id}",
                headers={"X-API-Key": key},
                json=body,
            )

    def get_choices(self, *, runner_id: str = RUNNER_ID, key: str = "bobo-key", **params):
        with self.make_client() as client:
            return client.get(
                f"/api/runners/{runner_id}/model-choices",
                headers={"X-API-Key": key},
                params=params,
            )

    def patch_control_kind(self, body, *, runner_id: str = RUNNER_ID, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.patch(
                f"/api/runners/{runner_id}/control-kind",
                headers={"X-API-Key": key},
                json=body,
            )

    def choice_rows(self, runner_id: str = RUNNER_ID) -> list[RunnerModelChoice]:
        with self.session() as session:
            return list(
                session.exec(
                    select(RunnerModelChoice).where(
                        RunnerModelChoice.runner_id == runner_id
                    )
                ).all()
            )

    # ── 新建与稳定 choice_id ─────────────────────────────────────────

    def test_human_creates_choice_with_stable_id_and_shape(self):
        self.register_runner()
        created = self.post_choice(self.choice_payload())
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertRegex(body["choice_id"], CHOICE_ID_PATTERN)
        self.assertEqual(body["runner_id"], RUNNER_ID)
        self.assertEqual(body["model_alias"], "deepseek-flash")
        self.assertEqual(body["source_kind"], "declared")
        self.assertEqual(body["capabilities"], ["prompt-argv"])
        self.assertIsNone(body["retired_at"])
        self.assertEqual(body["created_by"], "human:bobo")
        self.assertEqual(
            set(body),
            {
                "choice_id",
                "runner_id",
                "model_id",
                "model_source",
                "provider_id",
                "connection_ref",
                "model_alias",
                "model_display_name",
                "source_kind",
                "capabilities",
                "retired_at",
                "created_by",
                "created_at",
                "updated_at",
            },
        )
        listed = self.get_choices()
        self.assertEqual([row["choice_id"] for row in listed.json()], [body["choice_id"]])

    def test_kind_check_and_agent_cannot_write(self):
        self.register_runner()
        self.assertEqual(
            self.post_choice(self.choice_payload(), key="worker-key").status_code, 403
        )
        created = self.post_choice(self.choice_payload())
        self.assertEqual(
            self.patch_choice(
                created.json()["choice_id"], {"model_display_name": "X"}, key="worker-key"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.patch_control_kind({"control_kind": "managed_cli"}, key="worker-key").status_code,
            403,
        )
        self.assertEqual(self.get_choices(key="worker-key").status_code, 200)
        rows = self.choice_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].choice_id, created.json()["choice_id"])

    def test_same_model_two_connections_coexist(self):
        """I32：同运行器同 model_id 的不同 provider/connection 必须并存。"""
        self.register_runner()
        first = self.post_choice(self.choice_payload())
        second = self.post_choice(
            self.choice_payload(
                provider_id="managed:kimi",
                connection_ref="native-kimi-managed-login",
                model_alias="kimi-for-coding",
            )
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(
            first.json()["choice_id"], second.json()["choice_id"]
        )
        self.assertEqual(len(self.choice_rows()), 2)

    def test_same_dimensions_reuse_same_choice_and_update_display(self):
        self.register_runner()
        first = self.post_choice(self.choice_payload())
        replay = self.post_choice(
            self.choice_payload(
                model_display_name="DeepSeek Flash (renamed)",
                capabilities=["prompt-argv", "stream-json"],
                source_kind="verified",
            )
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["choice_id"], first.json()["choice_id"])
        self.assertEqual(replay.json()["model_display_name"], "DeepSeek Flash (renamed)")
        self.assertEqual(replay.json()["capabilities"], ["prompt-argv", "stream-json"])
        self.assertEqual(replay.json()["source_kind"], "verified")
        self.assertEqual(len(self.choice_rows()), 1)

    def test_omitted_display_fields_are_preserved_on_reuse(self):
        self.register_runner()
        self.post_choice(self.choice_payload())
        replay = self.post_choice(
            {
                "model_id": "deepseek-flash",
                "model_source": "builtin",
                "provider_id": "managed:deepseek",
                "connection_ref": "native-deepseek-managed-login",
                "model_alias": "deepseek-flash",
            }
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["model_display_name"], "DeepSeek Flash")
        self.assertEqual(replay.json()["source_kind"], "declared")
        self.assertEqual(replay.json()["capabilities"], ["prompt-argv"])

    def test_empty_alias_is_its_own_dimension(self):
        self.register_runner()
        with_alias = self.post_choice(self.choice_payload())
        without_alias = self.post_choice(self.choice_payload(model_alias=None))
        self.assertEqual(without_alias.status_code, 201)
        self.assertEqual(without_alias.json()["model_alias"], "")
        self.assertNotEqual(
            with_alias.json()["choice_id"], without_alias.json()["choice_id"]
        )
        self.assertEqual(len(self.choice_rows()), 2)

    # ── 维度不可变 / 软下架 / 权限 ───────────────────────────────────

    def test_dimension_mutation_is_rejected(self):
        self.register_runner()
        choice_id = self.post_choice(self.choice_payload()).json()["choice_id"]
        for field, value in (
            ("model_id", "other-model"),
            ("model_source", "custom_api"),
            ("provider_id", "managed:other"),
            ("connection_ref", "other-connection"),
            ("model_alias", "other-alias"),
        ):
            with self.subTest(field=field):
                response = self.patch_choice(choice_id, {field: value})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["detail"], "choice_dimension_immutable")
        row = self.choice_rows()[0]
        self.assertEqual(row.model_id, "deepseek-flash")
        self.assertEqual(row.model_alias, "deepseek-flash")

    def test_patch_unknown_field_and_blank_values_are_422(self):
        self.register_runner()
        choice_id = self.post_choice(self.choice_payload()).json()["choice_id"]
        self.assertEqual(
            self.patch_choice(choice_id, {"capabilities_v2": []}).status_code, 422
        )
        self.assertEqual(
            self.patch_choice(choice_id, {"capabilities": ["a", "a"]}).status_code, 422
        )
        self.assertEqual(
            self.patch_choice(choice_id, {"source_kind": "ready"}).status_code, 422
        )

    def test_soft_retire_hides_from_default_listing_but_keeps_row(self):
        self.register_runner()
        choice_id = self.post_choice(self.choice_payload()).json()["choice_id"]
        retired = self.patch_choice(choice_id, {"retired_at": "2026-10-11T00:00:00+00:00"})
        self.assertEqual(retired.status_code, 200)
        self.assertIsNotNone(retired.json()["retired_at"])
        self.assertEqual(self.get_choices().json(), [])
        included = self.get_choices(include_retired=True)
        self.assertEqual([row["choice_id"] for row in included.json()], [choice_id])
        self.assertEqual(len(self.choice_rows()), 1)

    def test_retired_choice_is_not_re_pointed_by_repost(self):
        """I33：软下架后重复 POST 只复用原 choice_id，不新建、不重指。"""
        self.register_runner()
        choice_id = self.post_choice(self.choice_payload()).json()["choice_id"]
        self.patch_choice(choice_id, {"retired_at": "2026-10-11T00:00:00+00:00"})
        replay = self.post_choice(self.choice_payload())
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["choice_id"], choice_id)
        self.assertIsNotNone(replay.json()["retired_at"])
        self.assertEqual(len(self.choice_rows()), 1)

    def test_unknown_runner_and_retired_runner(self):
        self.assertEqual(self.get_choices().status_code, 404)
        self.assertEqual(
            self.get_choices(runner_id="runner:ghost").status_code, 404
        )
        self.register_runner(adapter_status="retired")
        self.assertEqual(self.post_choice(self.choice_payload()).status_code, 409)
        self.assertEqual(
            self.post_choice(self.choice_payload()).json()["detail"], "runner_retired"
        )
        self.assertEqual(self.choice_rows(), [])
        self.assertEqual(
            self.patch_choice(
                "rmc_000000000000", {"model_display_name": "X"}
            ).status_code,
            404,
        )

    def test_patch_choice_from_other_runner_is_404(self):
        self.register_runner()
        self.register_runner(runner_id="runner:other")
        choice_id = self.post_choice(self.choice_payload()).json()["choice_id"]
        self.assertEqual(
            self.patch_choice(
                choice_id, {"model_display_name": "X"}, runner_id="runner:other"
            ).status_code,
            404,
        )

    # ── control_kind ────────────────────────────────────────────────

    def test_control_kind_defaults_to_unknown_and_is_human_only(self):
        self.register_runner()
        with self.session() as session:
            row = session.get(RunnerRegistry, RUNNER_ID)
            self.assertEqual(row.control_kind, "unknown")
        with self.make_client() as client:
            listed = client.get("/api/runners", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(listed.json()[0]["control_kind"], "unknown")

        updated = self.patch_control_kind({"control_kind": "managed_cli"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["control_kind"], "managed_cli")
        self.assertEqual(
            self.patch_control_kind({"control_kind": "external_session"}).json()[
                "control_kind"
            ],
            "external_session",
        )
        self.assertEqual(
            self.patch_control_kind({"control_kind": "always_on"}).status_code, 422
        )
        self.assertEqual(
            self.patch_control_kind({"control_kind": "managed_cli", "x": 1}).status_code,
            422,
        )
        self.assertEqual(
            self.patch_control_kind(
                {"control_kind": "managed_cli"}, runner_id="runner:ghost"
            ).status_code,
            404,
        )
        # 既有 PATCH /api/runners/{id} 四字段白名单不受影响（control_kind 不在其中）。
        with self.make_client() as client:
            legacy = client.patch(
                f"/api/runners/{RUNNER_ID}",
                headers={"X-API-Key": "bobo-key"},
                json={"control_kind": "managed_cli"},
            )
        self.assertEqual(legacy.status_code, 422)


if __name__ == "__main__":
    unittest.main()
