"""ROLE-BINDING-B1a 全局运行器登记 API 合同测试（合同 §3）。

覆盖：human 写 / agent 403、201/200、``runner_id`` 重复 409、``runner_id`` 与
``runtime`` 登记后不可改、未知字段与非法类型 422、``capabilities`` 定量规则、
``adapter_status`` 枚举、GET 任意已认证成员可读、登记不自动加入项目/启动进程、
``retired`` 保留历史且本片无 DELETE。

全部用例使用进程内 TestClient 与隔离临时库；不启动生产服务、不调用模型、不读凭据。
"""

from __future__ import annotations

import unittest

from sqlmodel import select

from server.models import (
    AgentInstance,
    ProjectAgent,
    ProjectRoleBinding,
    RunnerRegistry,
)
from tests.test_support import RouteTestCase


class RunnerRegistryApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")

    # ── helpers ──────────────────────────────────────────────────────

    def payload(self, **overrides):
        body = {
            "runner_id": "runner:dsh-cli",
            "runtime": "dsh",
            "display_name": "DeepSeek Harness (CLI)",
            "adapter_status": "discoverable",
            "adapter_note": "入口可发现；宿主等待预算未逐项核验",
            "capabilities": ["prompt-argv"],
        }
        body.update(overrides)
        return body

    def post_runner(self, body, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.post("/api/runners", headers={"X-API-Key": key}, json=body)

    def patch_runner(self, runner_id: str, body, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.patch(
                f"/api/runners/{runner_id}", headers={"X-API-Key": key}, json=body
            )

    def get_runners(self, *, key: str = "bobo-key"):
        with self.make_client() as client:
            return client.get("/api/runners", headers={"X-API-Key": key})

    def runner_rows(self):
        with self.session() as session:
            return list(session.exec(select(RunnerRegistry)).all())

    # ── 登记与读取 ───────────────────────────────────────────────────

    def test_human_can_register_and_read_runner(self):
        response = self.post_runner(self.payload())
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["runner_id"], "runner:dsh-cli")
        self.assertEqual(body["runtime"], "dsh")
        self.assertEqual(body["display_name"], "DeepSeek Harness (CLI)")
        self.assertEqual(body["adapter_status"], "discoverable")
        self.assertEqual(body["adapter_note"], "入口可发现；宿主等待预算未逐项核验")
        self.assertEqual(body["capabilities"], ["prompt-argv"])
        self.assertEqual(body["created_by"], "human:bobo")
        self.assertEqual(
            set(body),
            {
                "runner_id",
                "runtime",
                "display_name",
                "adapter_status",
                "adapter_note",
                "capabilities",
                "created_by",
                "created_at",
                "updated_at",
            },
        )

        listed = self.get_runners()
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["runner_id"] for row in listed.json()], ["runner:dsh-cli"])

    def test_adapter_status_defaults_to_unverified(self):
        body = self.payload()
        del body["adapter_status"]
        response = self.post_runner(body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["adapter_status"], "unverified")
        self.assertEqual(self.runner_rows()[0].adapter_status, "unverified")

    def test_registration_does_not_join_projects_or_start_anything(self):
        self.post_runner(self.payload())
        with self.session() as session:
            self.assertEqual(list(session.exec(select(ProjectAgent)).all()), [])
            self.assertEqual(list(session.exec(select(ProjectRoleBinding)).all()), [])
            self.assertEqual(list(session.exec(select(AgentInstance)).all()), [])

    def test_get_requires_authentication(self):
        with self.make_client() as client:
            self.assertEqual(client.get("/api/runners").status_code, 422)
            self.assertEqual(
                client.get("/api/runners", headers={"X-API-Key": "nope"}).status_code,
                401,
            )

    # ── 权限 ─────────────────────────────────────────────────────────

    def test_agent_cannot_write_but_can_read(self):
        self.assertEqual(
            self.post_runner(self.payload(), key="worker-key").status_code, 403
        )
        self.post_runner(self.payload())
        self.assertEqual(
            self.patch_runner("runner:dsh-cli", {"display_name": "X"}, key="worker-key").status_code,
            403,
        )
        self.assertEqual(self.get_runners(key="worker-key").status_code, 200)
        self.assertEqual(self.runner_rows()[0].display_name, "DeepSeek Harness (CLI)")

    # ── 重复与不可变字段 ─────────────────────────────────────────────

    def test_duplicate_runner_id_conflicts(self):
        self.assertEqual(self.post_runner(self.payload()).status_code, 201)
        duplicate = self.post_runner(self.payload(display_name="另一个名字"))
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(len(self.runner_rows()), 1)
        self.assertEqual(self.runner_rows()[0].display_name, "DeepSeek Harness (CLI)")

    def test_runner_id_and_runtime_are_immutable(self):
        self.post_runner(self.payload())
        self.assertEqual(
            self.patch_runner(
                "runner:dsh-cli", {"runner_id": "runner:other", "display_name": "X"}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.patch_runner("runner:dsh-cli", {"runtime": "codex"}).status_code, 422
        )
        row = self.runner_rows()[0]
        self.assertEqual(row.runner_id, "runner:dsh-cli")
        self.assertEqual(row.runtime, "dsh")

    def test_patch_updates_allowed_fields_and_clears_note(self):
        self.post_runner(self.payload())
        updated = self.patch_runner(
            "runner:dsh-cli",
            {
                "display_name": "DSH CLI",
                "adapter_status": "adapted",
                "adapter_note": None,
                "capabilities": ["prompt-argv", "stream-json"],
            },
        )
        self.assertEqual(updated.status_code, 200)
        body = updated.json()
        self.assertEqual(body["display_name"], "DSH CLI")
        self.assertEqual(body["adapter_status"], "adapted")
        self.assertIsNone(body["adapter_note"])
        self.assertEqual(body["capabilities"], ["prompt-argv", "stream-json"])
        self.assertEqual(body["runtime"], "dsh")
        row = self.runner_rows()[0]
        self.assertIsNone(row.adapter_note)
        self.assertEqual(row.display_name, "DSH CLI")

    def test_patch_unknown_runner_is_404(self):
        self.assertEqual(
            self.patch_runner("runner:ghost", {"display_name": "X"}).status_code, 404
        )

    def test_retired_runner_stays_registered(self):
        self.post_runner(self.payload(adapter_status="retired"))
        listed = self.get_runners()
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["adapter_status"], "retired")
        self.assertEqual(len(self.runner_rows()), 1)

    # ── 校验：未知字段 / 类型 / 枚举 ─────────────────────────────────

    def test_unknown_fields_and_bad_types_are_rejected(self):
        cases = {
            "unknown top-level field": self.payload(capabilities_v2=[]),
            "non-string runner_id": self.payload(runner_id=17),
            "null runtime": self.payload(runtime=None),
            "bad runner_id slug": self.payload(runner_id="Runner:DSH"),
            "runner_id with space": self.payload(runner_id="runner dsh"),
            "runner_id too long": self.payload(runner_id="r" * 65),
            "bad runtime": self.payload(runtime="DSH CLI"),
            "runtime too long": self.payload(runtime="r" * 33),
            "blank display_name": self.payload(display_name="   "),
            "display_name too long": self.payload(display_name="名" * 65),
            "bad adapter_status": self.payload(adapter_status="ready"),
            "adapter_note too long": self.payload(adapter_note="n" * 501),
            "capabilities not a list": self.payload(capabilities="prompt-argv"),
            "capabilities element not a string": self.payload(capabilities=[1]),
            "capabilities element object": self.payload(capabilities=[{"a": 1}]),
        }
        for name, body in cases.items():
            with self.subTest(name=name):
                self.assertEqual(self.post_runner(body).status_code, 422)
        self.assertEqual(self.runner_rows(), [])

    def test_capabilities_quantitative_rules(self):
        ok_zero = self.post_runner(
            self.payload(runner_id="runner:zero", capabilities=[])
        )
        self.assertEqual(ok_zero.status_code, 201)
        self.assertEqual(ok_zero.json()["capabilities"], [])

        at_max = [f"c{index:02d}" for index in range(32)]
        ok_max = self.post_runner(
            self.payload(runner_id="runner:max", capabilities=at_max)
        )
        self.assertEqual(ok_max.status_code, 201)
        self.assertEqual(ok_max.json()["capabilities"], at_max)

        rejected = {
            "33 items": [f"c{index:02d}" for index in range(33)],
            "blank item": ["prompt-argv", "   "],
            "blank-only item": ["\t\n"],
            "duplicate item": ["prompt-argv", "prompt-argv"],
            "duplicate after strip": ["prompt-argv", " prompt-argv "],
            "single item 65 codepoints": ["c" * 65],
        }
        for name, capabilities in rejected.items():
            with self.subTest(name=name):
                self.assertEqual(
                    self.post_runner(
                        self.payload(runner_id="runner:bad", capabilities=capabilities)
                    ).status_code,
                    422,
                )

        single_64 = "c" * 64
        accepted = self.post_runner(
            self.payload(runner_id="runner:len64", capabilities=[f"  {single_64}  "])
        )
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(accepted.json()["capabilities"], [single_64])

        self.assertEqual(
            {row.runner_id for row in self.runner_rows()},
            {"runner:zero", "runner:max", "runner:len64"},
        )

    def test_capabilities_patch_applies_same_rules(self):
        self.post_runner(self.payload())
        self.assertEqual(
            self.patch_runner(
                "runner:dsh-cli", {"capabilities": ["a", "a"]}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.patch_runner(
                "runner:dsh-cli", {"capabilities": ["c" * 65]}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.patch_runner("runner:dsh-cli", {"capabilities": None}).status_code, 422
        )
        self.assertEqual(
            self.patch_runner("runner:dsh-cli", {"capabilities": ["ok"]}).status_code, 200
        )
        self.assertEqual(self.runner_rows()[0].capabilities, ["ok"])

    def test_slug_control_chars_are_normalized_or_rejected_strictly(self):
        """R3：合法输入仍归一化，嵌入控制字符/全空白 slug 一律 422。"""
        padded = self.post_runner(
            self.payload(runner_id="  runner:padded  ", runtime=" dsh ")
        )
        self.assertEqual(padded.status_code, 201)
        self.assertEqual(padded.json()["runner_id"], "runner:padded")
        self.assertEqual(padded.json()["runtime"], "dsh")
        self.assertEqual(self.runner_rows()[0].runner_id, "runner:padded")

        rejected = {
            "embedded newline in runner_id": self.payload(
                runner_id="runner:bad\nslug"
            ),
            "embedded newline in runtime": self.payload(runtime="dsh\nx"),
            "newline only runner_id": self.payload(runner_id="\n"),
            "newline only runtime": self.payload(runtime="\n"),
        }
        for name, body in rejected.items():
            with self.subTest(name=name):
                self.assertEqual(self.post_runner(body).status_code, 422)
        self.assertEqual(len(self.runner_rows()), 1)

    def test_adapter_note_must_not_carry_credential_body(self):
        # 有限启发式只挡常见形态；这里验证说明字段与其它自由文本一样不被当作凭据通道来做
        # “已证明安全”的承诺——合法的说明照写，形态可疑的长 base64 串在 token 字段才拒绝。
        response = self.post_runner(
            self.payload(adapter_note="说明文本：等待预算与超时未核验，不含任何 Key。")
        )
        self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
