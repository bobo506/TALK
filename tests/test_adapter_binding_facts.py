# -*- coding: utf-8 -*-
"""`scripts/adapter_binding_facts.py` 的针对性测试（C1 离线适配事实模块）。

覆盖本片验收矩阵（实施计划 §1）：

- **选择**：argv 优先、confirmed default 正例、无/未核/过期 provenance 阻断、
  缺 alias / 缺条目 / 解析失败安全返回；
- **硬契约**：硬字段缺失阻断、固定 alias 逐字核验（同 backend 不同 alias 也拒绝）、
  provider/model/声明冲突、泛用 K3 正例；
- **schema**：既有归一化的错误类型/非法枚举/空白/超长/extra/重复 capabilities/
  可疑凭据，以及 runner/binding ID 不一致；
- **scope**：跨 host/workspace/拼接歧义不同、重复稳定、发现标志与模型无关、
  不依赖 ledger、长度 ≤64、互斥/坏值/非布尔拒绝；
- **连接**：不透明正例、路径与可执行后缀负例；
- **隐私**：合成 canary 递归覆盖选择/声明/嵌套 sources/缺条目/解析失败，以及
  ready/blocked/sources/指纹/错误；
- **指纹**：稳定、公开事实/来源/alias/scope 漂移、仅改凭据配置不变、不导出整 config；
- **profiles**：K28 直接引用既有常量（猴子补丁行为证据）、K3 不继承 K28 alias、
  DSH/Codex 来源不足 blocked、profile 不可变；
- **导入/隔离**：独立子进程审计钩子证明导入与主链路没有文件/环境/网络/DB/进程副作用，
  且不导入 MCP 工具模块。

全部离线：测试只使用内存夹具与猴子补丁，不读真实 native 配置 / Key / 环境凭据，
不联网、不写库、不启动模型进程，也不依赖任何 `.tmp` 参考探针。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import adapter_binding_facts as facts  # noqa: E402
import kimi_k28_executor as k28  # noqa: E402
from server.models import (  # noqa: E402
    RUNNER_ID_PATTERN,
    RoleBindingInput,
    RunnerCreate,
    RunnerUpdate,
)

# 合成 canary：明显是夹具值，任何真实输出都不应回流它们。
CANARY_ALIAS = "canary-alias-7f3a91"
CANARY_PROVIDER = "canary-provider-4c2b"
CANARY_MODEL = "canary-model-9d5e"
CANARY_CREDENTIAL = "sk-canary0123456789abcdef0123456789abcdef"
CANARY_SOURCE_KEY = "canary-nested-source-key"
CANARY_EXTRA_FIELD = "canary-extra-field-name"

K3_ALIAS = "kimi-code/k3"


def make_config(
    *,
    default_model: str = K3_ALIAS,
    models: object = None,
    providers: object = None,
) -> dict:
    """内存配置夹具；只含合成值，不读任何真实 native 文件。"""
    if models is None:
        models = {
            k28.MODEL_ALIAS: {
                "provider": k28.PROVIDER_ID,
                "model": k28.MODEL_ID,
                "display_name": "K2.8 Preview",
                "capabilities": ["thinking", "tool_use"],
            },
            K3_ALIAS: {
                "provider": k28.PROVIDER_ID,
                "model": "k3",
                "display_name": "K3",
                "capabilities": ["tool_use"],
            },
        }
    if providers is None:
        providers = {
            k28.PROVIDER_ID: {"type": "kimi", "api_key": CANARY_CREDENTIAL},
        }
    return {"default_model": default_model, "providers": providers, "models": models}


def blob_of(payload: object) -> str:
    """递归扫描用：把任意产物序列化成一段可搜索文本。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def make_runner_fields(runner_id: str, **overrides: object) -> dict:
    fields = {
        "runner_id": runner_id,
        "runtime": "kimi-code",
        "display_name": "Kimi Code CLI",
        "adapter_status": "unverified",
        "adapter_note": None,
        "capabilities": ["tool_use"],
    }
    fields.update(overrides)
    return fields


def make_binding_fields(runner_id: str, **overrides: object) -> dict:
    fields = {
        "runner_id": runner_id,
        "model_source": k28.MODEL_SOURCE,
        "provider_id": k28.PROVIDER_ID,
        "connection_ref": k28.CONNECTION_REF,
        "model_id": k28.MODEL_ID,
        "model_alias": k28.MODEL_ALIAS,
        "model_display_name": "K2.8 Preview",
    }
    fields.update(overrides)
    return fields


def resolve_ready(config: dict, *, layer: str = "argv", profile=None, declared=None, **kwargs):
    """按 K28/K3 profile 跑一次选择；``layer`` 控制 alias 来源层。"""
    profile = profile or facts.adapter_profile(facts.K28_ADAPTER)
    explicit = None
    provenance = None
    if layer == "argv":
        explicit = profile.explicit_argv_alias
    elif layer == "native_default":
        provenance = facts.native_provenance_for(
            config, origin="native_profile_loaded", confirmed=True
        )
    elif layer == "none":
        pass
    else:  # pragma: no cover - 测试自身用法错误
        raise AssertionError(layer)
    selection = facts.resolve_model_selection(
        config=config,
        explicit_argv_alias=explicit,
        declared=declared,
        hard=kwargs.pop("hard", profile.hard),
        native_provenance=provenance,
        required_hard_fields=kwargs.pop("required_hard_fields", profile.required_hard_fields),
        **kwargs,
    )
    assert selection["status"] == "ready", selection
    return selection


def build_k28_entry(
    config: dict,
    *,
    host_scope: str = "drift-host",
    workspace_scope: str = "drift-ws",
    origin: str = "native_profile_loaded",
    layer: str = "argv",
    declared: object = None,
    profile=None,
    runner_overrides: object = None,
    binding_overrides: object = None,
    sources: object = None,
    extra_context: object = None,
) -> dict:
    """构造一次完整的 K28 ready 条目，供指纹/漂移/隐私断言复用。"""
    profile = profile or facts.adapter_profile(facts.K28_ADAPTER)
    selection = resolve_ready(config, layer=layer, profile=profile, declared=declared)
    runner_id = facts.runner_id_for(
        profile.runtime, host_scope=host_scope, workspace_scope=workspace_scope
    )["runner_id"]
    runner_fields = make_runner_fields(runner_id, runtime=profile.runtime)
    runner_fields.update(runner_overrides or {})
    binding_fields = {
        "runner_id": runner_id,
        **{name: meta["value"] for name, meta in selection["fields"].items()},
    }
    binding_fields.update(binding_overrides or {})
    context = {
        "host_scope": host_scope,
        "workspace_scope": workspace_scope,
        "origin": origin,
        "selection": selection,
    }
    context.update(extra_context or {})
    return facts.build_entry(
        adapter=profile.adapter,
        member_id=profile.member_id,
        project_id="prj_c1_fixture",
        runner_fields=runner_fields,
        binding_fields=binding_fields,
        sources=sources
        if sources is not None
        else {"model_alias": {"value": selection["alias"], "source": selection["alias_source"]}},
        source_context=context,
    )


class TestFieldTuples(unittest.TestCase):
    """字段元组必须从既有 schema 派生。"""

    def test_field_tuples_come_from_existing_schemas(self):
        self.assertEqual(facts.RUNNER_CREATE_FIELDS, tuple(RunnerCreate.model_fields))
        self.assertEqual(facts.RUNNER_UPDATE_FIELDS, tuple(RunnerUpdate.model_fields))
        self.assertEqual(facts.BINDING_WRITE_FIELDS, tuple(RoleBindingInput.model_fields))
        self.assertEqual(len(facts.RUNNER_CREATE_FIELDS), 6)
        self.assertEqual(len(facts.RUNNER_UPDATE_FIELDS), 4)
        self.assertEqual(len(facts.BINDING_WRITE_FIELDS), 7)


class TestRunnerIdScope(unittest.TestCase):
    """合同 §3：稳定 scope、规范摘要 ID、只读 ledger。"""

    def test_same_scope_is_stable_and_scopes_differ(self):
        first = facts.runner_id_for("kimi-code", host_scope="lab-host", workspace_scope="ws-1")
        second = facts.runner_id_for("kimi-code", host_scope="lab-host", workspace_scope="ws-1")
        self.assertEqual(first["runner_id"], second["runner_id"])
        self.assertEqual(first["digest"], second["digest"])
        others = {
            "host": facts.runner_id_for("kimi-code", host_scope="lab-host-2", workspace_scope="ws-1"),
            "workspace": facts.runner_id_for("kimi-code", host_scope="lab-host", workspace_scope="ws-2"),
            "runtime": facts.runner_id_for("codex", host_scope="lab-host", workspace_scope="ws-1"),
        }
        id_set = {first["runner_id"]} | {item["runner_id"] for item in others.values()}
        self.assertEqual(len(id_set), 4)

    def test_canonical_payload_and_digest_are_exact(self):
        result = facts.runner_id_for("kimi-code", host_scope="lab-host", workspace_scope="ws-1")
        expected_payload = '{"schema":"adapter-scope-v1","scope":["kimi-code","lab-host","ws-1"]}'
        self.assertEqual(result["canonical_payload"], expected_payload)
        expected_digest = hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()[:32]
        self.assertEqual(result["digest"], expected_digest)
        self.assertEqual(result["runner_id"], f"runner:kimi-code-{expected_digest}")

    def test_scope_concatenation_ambiguity_does_not_collide(self):
        left = facts.runner_id_for("kimi-code", host_scope="host-a", workspace_scope="b-c")
        right = facts.runner_id_for("kimi-code", host_scope="host-a-b", workspace_scope="c")
        self.assertNotEqual(left["runner_id"], right["runner_id"])
        joined = facts.runner_id_for("kimi-code", host_scope="host-a", workspace_scope="b-c")
        runtime_shifted = facts.runner_id_for("kimi-code-host-a", host_scope="b", workspace_scope="c")
        self.assertNotEqual(joined["runner_id"], runtime_shifted["runner_id"])
        none_tail = facts.runner_id_for(
            "kimi-code", host_scope="host-a", host_shared_runner=True
        )
        self.assertNotEqual(joined["runner_id"], none_tail["runner_id"])

    def test_host_shared_scope_uses_explicit_null_workspace(self):
        shared = facts.runner_id_for("kimi-code", host_scope="lab-host", host_shared_runner=True)
        self.assertEqual(shared["scope_mode"], "host_shared")
        self.assertIsNone(shared["workspace_scope"])
        self.assertEqual(
            shared["canonical_payload"],
            '{"schema":"adapter-scope-v1","scope":["kimi-code","lab-host",null]}',
        )
        self.assertIsNone(shared["scope"]["workspace_scope"])

    def test_missing_workspace_without_explicit_flag_is_rejected(self):
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.runner_id_for("kimi-code", host_scope="lab-host")
        self.assertEqual(ctx.exception.code, "E_SCOPE_MISSING")
        self.assertEqual(ctx.exception.field, "workspace_scope")

    def test_missing_host_scope_is_rejected(self):
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.runner_id_for("kimi-code", host_scope=None, workspace_scope="ws")
        self.assertEqual(ctx.exception.code, "E_SCOPE_MISSING")
        self.assertEqual(ctx.exception.field, "host_scope")

    def test_workspace_and_host_shared_flag_are_mutually_exclusive(self):
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.runner_id_for(
                "kimi-code",
                host_scope="lab-host",
                workspace_scope="ws-1",
                host_shared_runner=True,
            )
        self.assertEqual(ctx.exception.code, "E_SCOPE_INVALID")

    def test_flags_must_be_strict_booleans(self):
        for value in (1, 0, "true", "True", None, [], {}):
            with self.subTest(value=value):
                with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
                    facts.runner_id_for(
                        "kimi-code",
                        host_scope="lab-host",
                        workspace_scope="ws-1",
                        host_shared_runner=value,
                    )
                self.assertEqual(ctx.exception.code, "E_FLAG_NOT_BOOL")
                self.assertEqual(ctx.exception.field, "host_shared_runner")
        for value in (1, 0, "yes", None, object()):
            with self.subTest(value=value):
                with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
                    facts.runner_id_for(
                        "kimi-code",
                        host_scope="lab-host",
                        workspace_scope="ws-1",
                        multi_workspace_on_host=value,
                    )
                self.assertEqual(ctx.exception.code, "E_FLAG_NOT_BOOL")

    def test_discovery_state_does_not_change_identity(self):
        base = facts.runner_id_for("kimi-code", host_scope="lab-host", workspace_scope="ws-1")
        flipped = facts.runner_id_for(
            "kimi-code",
            host_scope="lab-host",
            workspace_scope="ws-1",
            multi_workspace_on_host=True,
        )
        self.assertEqual(base["runner_id"], flipped["runner_id"])
        self.assertFalse(flipped["discovery_state_used"])
        self.assertTrue(flipped["ledger_used"] is False)

    def test_model_or_alias_facts_never_enter_the_scope(self):
        # scope 只由 (runtime, host, workspace) 决定：同 scope 的 K3/K28 复用同一 runner。
        same_scope = facts.runner_id_for("kimi-code", host_scope="lab-host", workspace_scope="ws-1")
        again = facts.runner_id_for("kimi-code", host_scope="lab-host", workspace_scope="ws-1")
        self.assertEqual(same_scope["runner_id"], again["runner_id"])
        self.assertNotIn(k28.MODEL_ALIAS, same_scope["canonical_payload"])
        self.assertNotIn(k28.MODEL_ID, same_scope["canonical_payload"])

    def test_k3_and_k28_roles_share_one_runner_per_scope(self):
        k28_profile = facts.adapter_profile(facts.K28_ADAPTER)
        k3_profile = facts.adapter_profile(facts.K3_ADAPTER)
        self.assertNotEqual(k28_profile.member_id, k3_profile.member_id)
        self.assertEqual(k28_profile.runtime, k3_profile.runtime)
        k28_runner = facts.runner_id_for(
            k28_profile.runtime, host_scope="shared-host", workspace_scope="shared-ws"
        )
        k3_runner = facts.runner_id_for(
            k3_profile.runtime, host_scope="shared-host", workspace_scope="shared-ws"
        )
        self.assertEqual(k28_runner["runner_id"], k3_runner["runner_id"])

    def test_ledger_is_optional_read_only_and_never_written(self):
        ledger: dict = {}
        result = facts.runner_id_for(
            "kimi-code", host_scope="lab-host", workspace_scope="ws-1", ledger=ledger
        )
        self.assertEqual(ledger, {})
        self.assertTrue(result["ledger_used"])
        without_ledger = facts.runner_id_for(
            "kimi-code", host_scope="lab-host", workspace_scope="ws-1"
        )
        self.assertEqual(result["runner_id"], without_ledger["runner_id"])
        self.assertFalse(without_ledger["ledger_used"])

        matching = {result["runner_id"]: ("lab-host", "ws-1", "workspace")}
        self.assertEqual(
            facts.runner_id_for(
                "kimi-code", host_scope="lab-host", workspace_scope="ws-1", ledger=matching
            )["runner_id"],
            result["runner_id"],
        )
        before = dict(matching)
        self.assertEqual(matching, before)

        conflicting = {result["runner_id"]: ("other-host", "other-ws", "workspace")}
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.runner_id_for(
                "kimi-code", host_scope="lab-host", workspace_scope="ws-1", ledger=conflicting
            )
        self.assertEqual(ctx.exception.code, "E_SCOPE_COLLISION")
        self.assertEqual(conflicting, {result["runner_id"]: ("other-host", "other-ws", "workspace")})

        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.runner_id_for(
                "kimi-code", host_scope="lab-host", workspace_scope="ws-1", ledger=["not", "a", "map"]
            )
        self.assertEqual(ctx.exception.code, "E_LEDGER_INVALID")

    def test_bad_scope_values_are_rejected(self):
        for value in ("", "   "):
            with self.subTest(value=value):
                with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
                    facts.runner_id_for("kimi-code", host_scope=value, workspace_scope="ws-1")
                self.assertEqual(ctx.exception.code, "E_SCOPE_MISSING")
        for value in ("/abs/path", "a/b", "a\\b", "a b", "中文", "-lead", "a" * 129, "ta\tb"):
            with self.subTest(value=value):
                with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
                    facts.runner_id_for("kimi-code", host_scope=value, workspace_scope="ws-1")
                self.assertEqual(ctx.exception.code, "E_SCOPE_INVALID")
        for value in (123, ["x"], {"a": 1}):
            with self.subTest(value=value):
                with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
                    facts.runner_id_for("kimi-code", host_scope=value, workspace_scope="ws-1")
                self.assertEqual(ctx.exception.code, "E_SCOPE_INVALID")
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.runner_id_for("kimi-code", host_scope="lab", workspace_scope="  ")
        self.assertEqual(ctx.exception.code, "E_SCOPE_INVALID")

    def test_credential_like_scope_cannot_escape_into_id_or_error(self):
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.runner_id_for("kimi-code", host_scope=CANARY_CREDENTIAL, workspace_scope="ws-1")
        self.assertEqual(ctx.exception.code, "E_SCOPE_INVALID")
        self.assertNotIn(CANARY_CREDENTIAL, str(ctx.exception))

    def test_runtime_uses_existing_normalization(self):
        for value in ("Kimi-Code", "", "  ", 123, "kimi code", "a" * 33):
            with self.subTest(value=value):
                with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
                    facts.runner_id_for(value, host_scope="lab-host", workspace_scope="ws-1")
                self.assertEqual(ctx.exception.code, "E_RUNTIME_INVALID")

    def test_long_runtime_truncates_but_full_runtime_joins_digest(self):
        long_runtime = "r" * 31
        result = facts.runner_id_for(long_runtime, host_scope="lab-host", workspace_scope="ws-1")
        self.assertTrue(result["runtime_truncated"])
        self.assertLessEqual(len(result["runner_id"]), 64)
        self.assertTrue(RUNNER_ID_PATTERN.fullmatch(result["runner_id"]))
        self.assertIn(long_runtime[:24], result["runner_id"])
        sibling = facts.runner_id_for("r" * 24 + "x" * 7, host_scope="lab-host", workspace_scope="ws-1")
        self.assertNotEqual(result["runner_id"], sibling["runner_id"])
        short = facts.runner_id_for("dsh", host_scope="lab-host", workspace_scope="ws-1")
        self.assertFalse(short["runtime_truncated"])
        self.assertLessEqual(len(short["runner_id"]), 64)
        self.assertTrue(RUNNER_ID_PATTERN.fullmatch(short["runner_id"]))


class TestNativeProvenance(unittest.TestCase):
    """合同 §4：来源确认标记与 native default 的可核性。"""

    def test_confirmed_default_alias_is_usable(self):
        config = make_config(default_model=k28.MODEL_ALIAS)
        provenance = facts.native_provenance_for(
            config, origin="native_profile_loaded", confirmed=True
        )
        result = facts.native_default_alias(config, provenance=provenance)
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["alias"], k28.MODEL_ALIAS)
        self.assertEqual(result["origin"], "native_profile_loaded")

    def test_creating_a_digest_does_not_confirm_by_itself(self):
        config = make_config()
        provenance = facts.native_provenance_for(config, origin="native_profile_loaded")
        self.assertFalse(provenance["confirmed"])
        self.assertEqual(
            facts.native_default_alias(config, provenance=provenance)["status"], "unconfirmed"
        )
        # 内部 provenance 摘要覆盖整份内存配置，但绝不进入导出公开指纹。
        self.assertEqual(
            provenance["config_content_sha256"],
            hashlib.sha256(facts.canonical_json(config).encode("utf-8")).hexdigest(),
        )

    def test_missing_provenance_and_override_layer_are_unconfirmed(self):
        config = make_config()
        self.assertEqual(facts.native_default_alias(config)["status"], "unconfirmed")
        self.assertEqual(
            facts.native_default_alias(config)["reason"], "no_provenance_supplied"
        )
        self.assertEqual(
            facts.native_default_alias(config, provenance={})["status"], "unconfirmed"
        )
        override = facts.native_provenance_for(
            config, origin="override_layer", confirmed=True
        )
        result = facts.native_default_alias(config, provenance=override)
        self.assertEqual(result["status"], "unconfirmed")
        self.assertEqual(result["origin"], "override_layer")
        self.assertIsNone(result["alias"])
        self.assertIsNotNone(result["alias_sha256"])

    def test_stale_provenance_digest_is_unconfirmed(self):
        config = make_config()
        provenance = facts.native_provenance_for(
            config, origin="native_profile_loaded", confirmed=True
        )
        changed = make_config(
            providers={k28.PROVIDER_ID: {"type": "kimi", "api_key": "changed-synthetic-value"}}
        )
        result = facts.native_default_alias(changed, provenance=provenance)
        self.assertEqual(result["status"], "unconfirmed")
        self.assertEqual(result["reason"], "provenance_digest_mismatch")
        self.assertIsNone(result["alias"])

    def test_absent_default_model_cases(self):
        self.assertEqual(facts.native_default_alias({})["reason"], "no_default_model")
        self.assertEqual(facts.native_default_alias({"default_model": "   "})["status"], "absent")
        self.assertEqual(facts.native_default_alias(["not", "a", "table"])["status"], "absent")
        self.assertIsNone(facts.native_default_alias({})["alias"])

    def test_confirmed_flag_must_be_strict_bool(self):
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.native_provenance_for({}, origin="native_profile_loaded", confirmed="true")
        self.assertEqual(ctx.exception.code, "E_FLAG_NOT_BOOL")

    def test_unknown_origin_is_not_echoed(self):
        provenance = facts.native_provenance_for({}, origin=CANARY_ALIAS, confirmed=True)
        self.assertEqual(provenance["origin"], "unknown")
        self.assertNotIn(CANARY_ALIAS, blob_of(provenance))

    def test_read_alias_facts_reuses_real_parser_without_echo(self):
        config = make_config()
        found = facts.read_alias_facts(config, k28.MODEL_ALIAS)
        self.assertTrue(found["alias_present"])
        self.assertEqual(found["provider_id"], k28.PROVIDER_ID)
        self.assertEqual(found["model_id"], k28.MODEL_ID)
        self.assertEqual(found["model_display_name"], "K2.8 Preview")
        self.assertTrue(found["tool_use"])

        missing = facts.read_alias_facts(config, CANARY_ALIAS)
        self.assertEqual(missing["unavailable"], "alias_not_found")
        self.assertNotIn(CANARY_ALIAS, blob_of(missing))

        broken = facts.read_alias_facts({k28.MODEL_ALIAS: "not-a-table"}, CANARY_ALIAS)
        self.assertEqual(broken["unavailable"], "alias_not_found")
        broken_alias = facts.read_alias_facts(
            {"models": {CANARY_ALIAS: ["not", "a", "table"]}}, CANARY_ALIAS
        )
        self.assertEqual(broken_alias["unavailable"], "native_parser_rejected_config")
        self.assertNotIn(CANARY_ALIAS, blob_of(broken_alias))

        self.assertEqual(facts.read_alias_facts([], k28.MODEL_ALIAS)["unavailable"], "config_not_a_table")
        self.assertEqual(facts.read_alias_facts({}, 123)["unavailable"], "alias_missing")


class TestResolveModelSelection(unittest.TestCase):
    """合同 §4：选择顺序、硬契约与声明边界。"""

    def setUp(self):
        self.profile = facts.adapter_profile(facts.K28_ADAPTER)
        self.config = make_config(default_model=K3_ALIAS)

    def test_argv_alias_wins_over_confirmed_native_default(self):
        provenance = facts.native_provenance_for(
            self.config, origin="native_profile_loaded", confirmed=True
        )
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias=self.profile.explicit_argv_alias,
            hard=self.profile.hard,
            native_provenance=provenance,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["alias"], k28.MODEL_ALIAS)
        self.assertEqual(result["alias_source"], "argv_explicit_selection")
        self.assertEqual(result["fields"]["model_source"]["source"], "hard_contract")
        self.assertEqual(result["fields"]["model_source"]["value"], "builtin")
        self.assertEqual(result["fields"]["provider_id"]["source"], "native_parse")

    def test_confirmed_native_default_is_used_without_explicit_argv(self):
        config = make_config(default_model=k28.MODEL_ALIAS)
        provenance = facts.native_provenance_for(
            config, origin="native_profile_loaded", confirmed=True
        )
        result = facts.resolve_model_selection(
            config=config,
            explicit_argv_alias=None,
            hard=self.profile.hard,
            native_provenance=provenance,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["alias"], k28.MODEL_ALIAS)
        self.assertEqual(result["alias_source"], "native_default_confirmed")

    def test_unconfirmed_default_sources_are_blocked(self):
        for provenance in (None, {}, facts.native_provenance_for(self.config, origin="override_layer", confirmed=True)):
            with self.subTest(provenance=bool(provenance)):
                result = facts.resolve_model_selection(
                    config=self.config,
                    explicit_argv_alias=None,
                    hard=self.profile.hard,
                    native_provenance=provenance,
                    required_hard_fields=self.profile.required_hard_fields,
                )
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_UNCONFIRMED")
                self.assertEqual(result["blocked"][0]["field"], "model_alias")
                self.assertNotIn(K3_ALIAS, blob_of(result))

    def test_missing_default_model_is_blocked(self):
        result = facts.resolve_model_selection(
            config={"models": {}},
            explicit_argv_alias=None,
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_UNAVAILABLE")

    def test_same_backend_different_fixed_alias_is_rejected(self):
        # K3 与 K28 指向同一个 provider/model，但不是同一次调用别名。
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias=K3_ALIAS,
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_CONFLICT")
        self.assertEqual(result["blocked"][0]["field"], "model_alias")
        self.assertNotIn(K3_ALIAS, blob_of(result))

    def test_non_string_explicit_alias_is_blocked(self):
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias="   ",
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_UNAVAILABLE")

    def test_required_hard_fields_missing_block(self):
        trimmed = {
            key: value
            for key, value in self.profile.hard.items()
            if key not in ("provider_id", "connection_ref", "model_alias")
        }
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias=self.profile.explicit_argv_alias,
            hard=trimmed,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            {item["field"] for item in result["blocked"]},
            {"provider_id", "connection_ref", "model_alias"},
        )
        self.assertTrue(
            all(item["code"] == "E_SOURCE_UNAVAILABLE" for item in result["blocked"])
        )

    def test_missing_non_alias_required_fields_block(self):
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias=self.profile.explicit_argv_alias,
            hard={},
            required_hard_fields=("provider_id", "model_id"),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            {item["field"] for item in result["blocked"]}, {"provider_id", "model_id"}
        )

    def test_unknown_required_field_name_is_rejected(self):
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias=self.profile.explicit_argv_alias,
            hard={},
            required_hard_fields=(CANARY_EXTRA_FIELD,),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_FIELD_INVALID")
        self.assertEqual(result["blocked"][0]["field"], "required_hard_fields")
        self.assertNotIn(CANARY_EXTRA_FIELD, blob_of(result))

    def test_provider_and_model_mismatch_block(self):
        for field, value in (("provider_id", CANARY_PROVIDER), ("model_id", CANARY_MODEL)):
            with self.subTest(field=field):
                hard = dict(self.profile.hard)
                hard[field] = value
                result = facts.resolve_model_selection(
                    config=self.config,
                    explicit_argv_alias=self.profile.explicit_argv_alias,
                    hard=hard,
                    required_hard_fields=self.profile.required_hard_fields,
                )
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_CONFLICT")
                self.assertEqual(result["blocked"][0]["field"], field)
                self.assertNotIn(value, blob_of(result))

    def test_declared_alias_cannot_override_verified_selection(self):
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias=self.profile.explicit_argv_alias,
            declared={"model_alias": K3_ALIAS},
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_CONFLICT")
        self.assertEqual(result["blocked"][0]["field"], "model_alias")
        self.assertNotIn(K3_ALIAS, blob_of(result))

    def test_declared_conflict_with_hard_contract_blocks(self):
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias=self.profile.explicit_argv_alias,
            declared={"model_source": "custom_api"},
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_CONFLICT")
        self.assertEqual(result["blocked"][0]["field"], "model_source")

    def test_declared_type_error_blocks_with_field_name(self):
        result = facts.resolve_model_selection(
            config=self.config,
            explicit_argv_alias=self.profile.explicit_argv_alias,
            declared={"connection_ref": 123},
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_FIELD_INVALID")
        self.assertEqual(result["blocked"][0]["field"], "connection_ref")

    def test_bad_hard_or_declared_container_is_blocked(self):
        for kwargs, field in (({"hard": ["x"]}, "hard"), ({"declared": ["x"]}, "declared")):
            with self.subTest(field=field):
                result = facts.resolve_model_selection(
                    config=self.config,
                    explicit_argv_alias=self.profile.explicit_argv_alias,
                    **kwargs,
                )
                self.assertEqual(result["blocked"][0]["code"], "E_FIELD_INVALID")
                self.assertEqual(result["blocked"][0]["field"], field)

    def test_alias_entry_missing_is_safe(self):
        result = facts.resolve_model_selection(
            config={"default_model": K3_ALIAS, "models": {K3_ALIAS: {"provider": "p", "model": "m"}}},
            explicit_argv_alias=k28.MODEL_ALIAS,
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_UNAVAILABLE")
        self.assertEqual(result["blocked"][0]["reason_code"], "alias_not_found")
        self.assertNotIn(k28.MODEL_ALIAS, blob_of(result))

    def test_native_parser_failure_is_safe(self):
        config = {"models": {k28.MODEL_ALIAS: ["not", "a", "table"]}}
        result = facts.resolve_model_selection(
            config=config,
            explicit_argv_alias=k28.MODEL_ALIAS,
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["reason_code"], "native_parser_rejected_config")
        self.assertNotIn(k28.MODEL_ALIAS, blob_of(result))
        self.assertNotIn("not", blob_of(result["blocked"]))

    def test_non_mapping_config_is_safe(self):
        result = facts.resolve_model_selection(
            config=["not", "a", "table"],
            explicit_argv_alias=k28.MODEL_ALIAS,
            hard=self.profile.hard,
            required_hard_fields=self.profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["reason_code"], "config_not_a_table")

    def test_generic_k3_positive_uses_own_selection(self):
        profile = facts.adapter_profile(facts.K3_ADAPTER)
        config = make_config(default_model=K3_ALIAS)
        provenance = facts.native_provenance_for(
            config, origin="native_profile_loaded", confirmed=True
        )
        result = facts.resolve_model_selection(
            config=config,
            explicit_argv_alias=None,
            declared={"model_source": "builtin", "connection_ref": k28.CONNECTION_REF},
            hard=profile.hard,
            native_provenance=provenance,
            required_hard_fields=profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["alias"], K3_ALIAS)
        self.assertEqual(result["alias_source"], "native_default_confirmed")
        self.assertEqual(result["fields"]["model_source"]["source"], "declared")
        self.assertEqual(result["fields"]["connection_ref"]["source"], "declared")
        self.assertEqual(result["fields"]["model_id"]["value"], "k3")
        self.assertNotEqual(result["alias"], k28.MODEL_ALIAS)

    def test_generic_k3_without_confirmed_source_is_blocked(self):
        profile = facts.adapter_profile(facts.K3_ADAPTER)
        result = facts.resolve_model_selection(
            config=make_config(default_model=K3_ALIAS),
            explicit_argv_alias=None,
            declared={"model_source": "builtin", "connection_ref": k28.CONNECTION_REF},
            hard=profile.hard,
            required_hard_fields=profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_SOURCE_UNCONFIRMED")

    def test_declared_can_fill_machine_unavailable_fields(self):
        profile = facts.adapter_profile(facts.K3_ADAPTER)
        config = make_config(
            default_model=K3_ALIAS,
            models={K3_ALIAS: {"capabilities": ["tool_use"]}},
        )
        result = facts.resolve_model_selection(
            config=config,
            explicit_argv_alias=None,
            declared={
                "model_source": "builtin",
                "connection_ref": k28.CONNECTION_REF,
                "provider_id": k28.PROVIDER_ID,
                "model_id": "k3",
                "model_display_name": "K3 declared label",
            },
            hard={},
            native_provenance=facts.native_provenance_for(
                config, origin="native_profile_loaded", confirmed=True
            ),
            required_hard_fields=(),
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["fields"]["provider_id"]["source"], "declared")
        self.assertEqual(result["fields"]["model_id"]["source"], "declared")
        self.assertEqual(result["fields"]["model_display_name"]["value"], "K3 declared label")
        self.assertEqual(profile.explicit_argv_alias, None)

    def test_connection_ref_paths_and_suffixes_are_rejected(self):
        for value in (
            "C:/x/kimi-login",
            "bin/run.sh",
            "./relative",
            "kimi-login.cmd",
            "kimi-login.EXE",
            "tool.ps1",
            "..",
        ):
            with self.subTest(value=value):
                hard = dict(self.profile.hard)
                hard["connection_ref"] = value
                result = facts.resolve_model_selection(
                    config=self.config,
                    explicit_argv_alias=self.profile.explicit_argv_alias,
                    hard=hard,
                    required_hard_fields=self.profile.required_hard_fields,
                )
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["blocked"][0]["code"], "E_CONNECTION_REF_INVALID")

    def test_connection_ref_declared_negative_and_positive(self):
        profile = facts.adapter_profile(facts.K3_ADAPTER)
        config = make_config(default_model=K3_ALIAS)
        provenance = facts.native_provenance_for(
            config, origin="native_profile_loaded", confirmed=True
        )
        negative = facts.resolve_model_selection(
            config=config,
            explicit_argv_alias=None,
            declared={"model_source": "builtin", "connection_ref": "native-login.exe"},
            hard={"provider_id": k28.PROVIDER_ID, "model_id": "k3"},
            native_provenance=provenance,
            required_hard_fields=profile.required_hard_fields,
        )
        self.assertEqual(negative["status"], "blocked")
        self.assertEqual(negative["blocked"][0]["code"], "E_CONNECTION_REF_INVALID")
        positive = facts.resolve_model_selection(
            config=config,
            explicit_argv_alias=None,
            declared={"model_source": "builtin", "connection_ref": "native-managed-login"},
            hard={"provider_id": k28.PROVIDER_ID, "model_id": "k3"},
            native_provenance=provenance,
            required_hard_fields=profile.required_hard_fields,
        )
        self.assertEqual(positive["status"], "ready")
        self.assertEqual(positive["fields"]["connection_ref"]["value"], "native-managed-login")

    def test_declared_bad_enum_is_field_invalid(self):
        profile = facts.adapter_profile(facts.K3_ADAPTER)
        result = facts.resolve_model_selection(
            config=make_config(default_model=K3_ALIAS),
            explicit_argv_alias=None,
            declared={"model_source": "bogus", "connection_ref": k28.CONNECTION_REF},
            hard={"provider_id": k28.PROVIDER_ID, "model_id": "k3"},
            native_provenance=facts.native_provenance_for(
                make_config(default_model=K3_ALIAS), origin="native_profile_loaded", confirmed=True
            ),
            required_hard_fields=profile.required_hard_fields,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked"][0]["code"], "E_FIELD_INVALID")
        self.assertEqual(result["blocked"][0]["field"], "model_source")
        self.assertNotIn("bogus", blob_of(result))

    def test_blocked_results_never_carry_raw_aliases(self):
        result = facts.resolve_model_selection(
            config={"models": {CANARY_ALIAS: ["not", "a", "table"]}},
            explicit_argv_alias=CANARY_ALIAS,
            hard={},
            required_hard_fields=(),
        )
        self.assertEqual(result["status"], "blocked")
        for canary in (CANARY_ALIAS, CANARY_PROVIDER, CANARY_MODEL, CANARY_CREDENTIAL):
            self.assertNotIn(canary, blob_of(result))


class TestBuildEntry(unittest.TestCase):
    """合同 §2/§5：ready 白名单、runner 关联、连接收窄、blocked 不回候选。"""

    def setUp(self):
        self.profile = facts.adapter_profile(facts.K28_ADAPTER)
        self.config = make_config()
        self.selection = resolve_ready(self.config)
        self.runner_id = facts.runner_id_for(
            self.profile.runtime, host_scope="entry-host", workspace_scope="entry-ws"
        )["runner_id"]

    def _entry(self, **overrides):
        kwargs = {
            "adapter": self.profile.adapter,
            "member_id": self.profile.member_id,
            "project_id": "prj_entry",
            "runner_fields": make_runner_fields(self.runner_id),
            "binding_fields": make_binding_fields(self.runner_id),
            "sources": {"model_alias": {"value": k28.MODEL_ALIAS, "source": "argv_explicit_selection"}},
            "source_context": {
                "host_scope": "entry-host",
                "workspace_scope": "entry-ws",
                "origin": "native_profile_loaded",
                "selection": self.selection,
            },
        }
        kwargs.update(overrides)
        return facts.build_entry(**kwargs)

    def test_ready_entry_uses_schema_whitelists(self):
        entry = self._entry()
        self.assertEqual(entry["status"], "ready")
        self.assertEqual(entry["blocked"], [])
        self.assertEqual(
            list(entry),
            [
                "adapter",
                "member_id",
                "project_id",
                "sources",
                "status",
                "blocked",
                "runner",
                "binding",
                "public_config_identity",
                "source_fingerprint",
            ],
        )
        self.assertEqual(list(entry["runner"]), list(facts.RUNNER_CREATE_FIELDS))
        self.assertEqual(list(entry["binding"]), list(facts.BINDING_WRITE_FIELDS))
        self.assertEqual(entry["runner"]["runtime"], "kimi-code")
        self.assertEqual(entry["binding"]["model_alias"], k28.MODEL_ALIAS)
        self.assertEqual(entry["sources"], {"model_alias": {"source": "argv_explicit_selection"}})

    def test_runner_binding_id_mismatch_blocks_without_candidates(self):
        entry = self._entry(binding_fields=make_binding_fields("runner:other-0000"))
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_BINDING_ID_MISMATCH")
        for key in ("runner", "binding", "source_fingerprint", "public_config_identity"):
            self.assertNotIn(key, entry)
        self.assertNotIn("runner:other-0000", blob_of(entry))
        self.assertNotIn(self.runner_id, blob_of(entry))

    def test_invalid_runner_payload_reports_field_names_only(self):
        # 既有 schema 的 `model_validator(mode="after")` 在首个失败处抛出，
        # 因此每次只报告真正失败的那个字段名（不回流原值）。
        cases = {
            "display_name": {"display_name": ""},
            "adapter_status": {"adapter_status": CANARY_PROVIDER},
            "capabilities": {"capabilities": ["tool_use", "tool_use"]},
            "runner_id": {"runner_id": "Bad Runner"},
        }
        for field, overrides in cases.items():
            with self.subTest(field=field):
                runner_fields = make_runner_fields(self.runner_id)
                runner_fields.update(overrides)
                entry = self._entry(runner_fields=runner_fields)
                self.assertEqual(entry["status"], "blocked")
                self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_PAYLOAD_INVALID")
                self.assertEqual(entry["blocked"][0]["invalid_fields"], [field])
                blob = blob_of(entry)
                for value in (CANARY_PROVIDER, CANARY_CREDENTIAL, "tool_use", "Bad Runner"):
                    self.assertNotIn(value, blob)

    def test_extra_runner_field_is_not_echoed(self):
        runner_fields = make_runner_fields(self.runner_id)
        runner_fields[CANARY_EXTRA_FIELD] = CANARY_CREDENTIAL
        entry = self._entry(runner_fields=runner_fields)
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_PAYLOAD_INVALID")
        self.assertEqual(entry["blocked"][0]["invalid_fields"], ["<extra_field>"])
        self.assertNotIn(CANARY_EXTRA_FIELD, blob_of(entry))
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(entry))

    def test_invalid_binding_payload_is_blocked_without_values(self):
        entry = self._entry(
            binding_fields=make_binding_fields(self.runner_id, model_source=CANARY_MODEL)
        )
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_BINDING_PAYLOAD_INVALID")
        self.assertEqual(entry["blocked"][0]["invalid_fields"], ["model_source"])
        self.assertNotIn(CANARY_MODEL, blob_of(entry))

    def test_credential_like_binding_value_is_blocked_without_echo(self):
        entry = self._entry(
            binding_fields=make_binding_fields(self.runner_id, provider_id=CANARY_CREDENTIAL)
        )
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_BINDING_PAYLOAD_INVALID")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(entry))

    def test_connection_ref_narrowing_is_stricter_than_server_rule(self):
        # 现服务端规则接受该值（不解释为命令），本 helper 额外收窄。
        RoleBindingInput(**make_binding_fields(self.runner_id, connection_ref="kimi-login.cmd"))
        entry = self._entry(
            binding_fields=make_binding_fields(self.runner_id, connection_ref="kimi-login.cmd")
        )
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_CONNECTION_REF_INVALID")
        self.assertNotIn("kimi-login.cmd", blob_of(entry))
        for value in ("C:/x/login", "bin/run.sh", "..", "a" * 129, ""):
            with self.subTest(value=value):
                self.assertFalse(facts.is_opaque_connection_ref(value))
        for value in (k28.CONNECTION_REF, "native-login", "a.b_c-d", "A" * 128):
            with self.subTest(value=value):
                self.assertTrue(facts.is_opaque_connection_ref(value))

    def test_invalid_source_container_is_reported_without_candidates(self):
        entry = self._entry(runner_fields=["not", "a", "mapping"])
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_PAYLOAD_INVALID")
        entry = self._entry(binding_fields=None)
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_BINDING_PAYLOAD_INVALID")

    def test_target_labels_are_rejected_when_unsafe(self):
        for field, value in (
            ("member_id", ""),
            ("member_id", "  "),
            ("project_id", CANARY_CREDENTIAL),
            ("adapter", "line\nbreak"),
            ("adapter", 123),
        ):
            with self.subTest(field=field, value=repr(value)):
                kwargs = {"member_id": self.profile.member_id, "project_id": "prj", "adapter": "agent:x"}
                kwargs[field] = value
                with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
                    self._entry(**kwargs)
                self.assertEqual(ctx.exception.code, "E_TARGET_INVALID")
                if isinstance(value, str) and value.strip():
                    self.assertNotIn(value, str(ctx.exception))

    def test_unknown_adapter_profile_names_are_rejected_without_echo(self):
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.adapter_profile(CANARY_ALIAS)
        self.assertEqual(ctx.exception.code, "E_UNKNOWN_ADAPTER")
        self.assertNotIn(CANARY_ALIAS, str(ctx.exception))
        with self.assertRaises(facts.AdapterBindingFactsError):
            facts.adapter_profile(None)

    def test_entry_without_selection_is_blocked_without_fingerprint(self):
        with_sources = self._entry(
            source_context={"host_scope": "entry-host", "workspace_scope": "entry-ws"}
        )
        self.assertEqual(with_sources["status"], "blocked")
        self.assertNotIn("source_fingerprint", with_sources)
        self.assertNotIn("binding", with_sources)

        without_sources = self._entry(
            sources=None,
            source_context={"host_scope": "entry-host", "workspace_scope": "entry-ws"},
        )
        self.assertEqual(without_sources["status"], "blocked")
        self.assertEqual(without_sources["sources"], {})
        self.assertNotIn("source_fingerprint", without_sources)


class TestC1ClosureRegressions(unittest.TestCase):
    """命中 #206 原缺陷：使用真实 profile，核事实/载荷闭合及能力隐私边界。"""

    def setUp(self):
        self.selection = resolve_ready(make_config())
        self.runner_id = facts.runner_id_for(
            "kimi-code", host_scope="closure-host", workspace_scope="closure-ws"
        )["runner_id"]

    def entry(self, *, selection=None, binding_overrides=None, runner_overrides=None):
        binding = {
            "runner_id": self.runner_id,
            **{name: meta["value"] for name, meta in self.selection["fields"].items()},
        }
        binding.update(binding_overrides or {})
        return facts.build_entry(
            adapter=facts.K28_ADAPTER,
            member_id=facts.K28_ADAPTER,
            project_id="prj_closure_fixture",
            runner_fields=make_runner_fields(self.runner_id, **(runner_overrides or {})),
            binding_fields=binding,
            source_context={
                "selection": self.selection if selection is None else selection,
                "host_scope": "closure-host",
                "workspace_scope": "closure-ws",
            },
        )

    def assert_closed(self, entry):
        self.assertEqual(entry["status"], "blocked")
        for key in ("runner", "binding", "source_fingerprint", "public_config_identity"):
            self.assertNotIn(key, entry)

    def test_actual_k3_profile_explicit_alias_is_ready(self):
        profile = facts.adapter_profile(facts.K3_ADAPTER)
        result = facts.resolve_model_selection(
            config=make_config(), explicit_argv_alias=K3_ALIAS,
            hard=profile.hard, required_hard_fields=profile.required_hard_fields,
            declared={"model_source": "builtin", "connection_ref": "k3-native-fixture"},
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["fields"]["model_id"]["value"], "k3")

    def test_valid_binding_cannot_override_ready_selection(self):
        changes = {
            "model_source": "custom_api", "provider_id": "synthetic-provider",
            "connection_ref": "synthetic-connection", "model_id": "synthetic-model",
            "model_alias": "synthetic-alias", "model_display_name": "Synthetic display",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                entry = self.entry(binding_overrides={field: value})
                self.assert_closed(entry)
                self.assertEqual(entry["blocked"][0]["field"], field)

    def test_blocked_selection_cannot_be_promoted(self):
        blocked = facts.resolve_model_selection(
            config=make_config(), explicit_argv_alias=K3_ALIAS,
            hard=facts.adapter_profile(facts.K28_ADAPTER).hard,
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assert_closed(self.entry(selection=blocked))

    def test_malformed_ready_selection_is_blocked(self):
        for selection in ({"status": "ready"}, {}, "ready"):
            with self.subTest(kind=type(selection).__name__):
                self.assert_closed(self.entry(selection=selection))

    def test_selection_alias_must_match_binding(self):
        selection = json.loads(blob_of(self.selection))
        selection["alias"] = "synthetic-other-alias"
        entry = self.entry(selection=selection)
        self.assert_closed(entry)
        self.assertEqual(entry["blocked"][0]["field"], "model_alias")

    def test_invalid_selection_metadata_is_blocked(self):
        for metadata in ({"value": k28.MODEL_ID, "source": "invented"}, "model", {}):
            with self.subTest(kind=type(metadata).__name__):
                selection = json.loads(blob_of(self.selection))
                selection["fields"]["model_id"] = metadata
                self.assert_closed(self.entry(selection=selection))

    def test_projection_tuple_must_match_binding(self):
        changes = {
            "native": {"provider_id": "synthetic-provider", "model_id": "synthetic-model",
                       "model_display_name": "Synthetic display"},
            "hard_contract": {"model_source": "custom_api", "provider_id": "synthetic-provider",
                              "model_id": "synthetic-model", "connection_ref": "synthetic-conn",
                              "model_alias": "synthetic-alias"},
            "declared_contract": {"model_source": "custom_api", "connection_ref": "synthetic-conn"},
        }
        for container, fields in changes.items():
            for field, value in fields.items():
                with self.subTest(container=container, field=field):
                    selection = json.loads(blob_of(self.selection))
                    selection[container][field] = value
                    self.assert_closed(self.entry(selection=selection))

    def test_normalized_equivalent_binding_remains_ready(self):
        entry = self.entry(binding_overrides={"model_display_name": "  K2.8 Preview  "})
        self.assertEqual(entry["status"], "ready")
        self.assertEqual(entry["binding"]["model_display_name"], "K2.8 Preview")

    def test_native_capability_credential_is_blocked_without_echo(self):
        config = make_config()
        config["models"][k28.MODEL_ALIAS]["capabilities"] = ["tool_use", CANARY_CREDENTIAL]
        alias_facts = facts.read_alias_facts(config, k28.MODEL_ALIAS)
        self.assertIn("unavailable", alias_facts)
        selection = facts.resolve_model_selection(
            config=config, explicit_argv_alias=k28.MODEL_ALIAS,
            hard=facts.adapter_profile(facts.K28_ADAPTER).hard,
        )
        self.assertEqual(selection["status"], "blocked")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of([alias_facts, selection]))

    def test_public_capability_projection_filters_credential(self):
        identity = facts.public_config_identity(
            native={"capabilities": ["tool_use", CANARY_CREDENTIAL]}
        )
        self.assertIsNone(identity["projection"]["native"]["capabilities"])
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(identity))

    def test_runner_capability_credential_is_blocked_without_echo(self):
        entry = self.entry(runner_overrides={"capabilities": ["tool_use", CANARY_CREDENTIAL]})
        self.assert_closed(entry)
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(entry))

    def test_selection_capability_credential_is_blocked_without_echo(self):
        selection = json.loads(blob_of(self.selection))
        selection["native"]["capabilities"] = ["tool_use", CANARY_CREDENTIAL]
        entry = self.entry(selection=selection)
        self.assert_closed(entry)
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(entry))


class TestSourcesAndPrivacy(unittest.TestCase):
    """合同 §5：sources 白名单、canary 递归检查。"""

    def test_sanitize_sources_keeps_only_known_keys_and_enum(self):
        sanitized = facts.sanitize_sources(
            {
                "model_alias": {"value": CANARY_ALIAS, "source": "argv_explicit_selection", "nested": {"x": 1}},
                "runtime": {"source": "hard_contract"},
                "provider_id": {"source": CANARY_PROVIDER},
                "model_id": "not-a-mapping",
                CANARY_SOURCE_KEY: {"source": "argv_explicit_selection"},
                "bogus_key": {"value": CANARY_CREDENTIAL},
            }
        )
        self.assertEqual(
            sanitized,
            {
                "model_alias": {"source": "argv_explicit_selection"},
                "runtime": {"source": "hard_contract"},
                "provider_id": {"source": "unknown"},
                "model_id": {"source": "unknown"},
            },
        )
        blob = blob_of(sanitized)
        for canary in (CANARY_ALIAS, CANARY_PROVIDER, CANARY_CREDENTIAL, CANARY_SOURCE_KEY, "nested"):
            self.assertNotIn(canary, blob)
        self.assertEqual(facts.sanitize_sources(None), {})
        self.assertEqual(facts.sanitize_sources(["x"]), {})

    def test_ready_entry_keeps_alias_as_digest_outside_the_binding(self):
        config = make_config(
            models={
                CANARY_ALIAS: {
                    "provider": CANARY_PROVIDER,
                    "model": CANARY_MODEL,
                    "display_name": "Canary label",
                    "capabilities": ["tool_use"],
                }
            }
        )
        profile = facts.adapter_profile(facts.K28_ADAPTER)
        selection = facts.resolve_model_selection(
            config=config,
            explicit_argv_alias=CANARY_ALIAS,
            declared={
                "model_source": "builtin",
                "connection_ref": "canary-opaque-connection",
            },
            hard={},
            required_hard_fields=(),
        )
        self.assertEqual(selection["status"], "ready")
        runner_id = facts.runner_id_for(
            profile.runtime, host_scope="canary-host", workspace_scope="canary-ws"
        )["runner_id"]
        entry = facts.build_entry(
            adapter=profile.adapter,
            member_id=profile.member_id,
            project_id="prj_canary",
            runner_fields=make_runner_fields(runner_id),
            binding_fields={"runner_id": runner_id, **{k: v["value"] for k, v in selection["fields"].items()}},
            sources={"model_alias": {"value": CANARY_ALIAS, "source": "argv_explicit_selection"}},
            source_context={
                "host_scope": "canary-host",
                "workspace_scope": "canary-ws",
                "origin": "native_profile_loaded",
                "selection": selection,
            },
        )
        self.assertEqual(entry["status"], "ready")
        # 公开 schema 白名单内的 binding 允许携带已核公开值。
        self.assertEqual(entry["binding"]["model_alias"], CANARY_ALIAS)
        # 但指纹 / sources / 公开投影都不得出现原 alias、provider 或 model 明文。
        self.assertNotIn(CANARY_ALIAS, blob_of(entry["source_fingerprint"]))
        self.assertNotIn(CANARY_ALIAS, blob_of(entry["sources"]))
        self.assertNotIn(CANARY_ALIAS, blob_of(entry["public_config_identity"]))
        self.assertEqual(
            entry["source_fingerprint"]["nonsecret_inputs"]["selected_alias_sha256"],
            hashlib.sha256(CANARY_ALIAS.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            entry["public_config_identity"]["projection"]["selected_alias_sha256"],
            hashlib.sha256(CANARY_ALIAS.encode("utf-8")).hexdigest(),
        )
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(entry))

    def test_nested_source_canary_and_credential_are_dropped(self):
        entry = build_k28_entry(
            make_config(),
            sources={
                "model_alias": {"value": k28.MODEL_ALIAS, "source": "argv_explicit_selection"},
                CANARY_SOURCE_KEY: {"source": "native_parse", "value": CANARY_CREDENTIAL},
                "provider_id": {"source": "native_parse", "value": CANARY_PROVIDER},
            },
        )
        self.assertEqual(entry["status"], "ready")
        blob = blob_of(entry["sources"])
        self.assertNotIn(CANARY_SOURCE_KEY, blob)
        self.assertNotIn(CANARY_CREDENTIAL, blob)
        self.assertNotIn(CANARY_PROVIDER, blob)
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(entry))

    def test_blocked_paths_never_echo_canaries(self):
        profile = facts.adapter_profile(facts.K28_ADAPTER)
        canary_config = {
            "default_model": CANARY_ALIAS,
            "providers": {CANARY_PROVIDER: {"api_key": CANARY_CREDENTIAL}},
            "models": {
                CANARY_ALIAS: {
                    "provider": CANARY_PROVIDER,
                    "model": CANARY_MODEL,
                    "display_name": "Canary",
                    "capabilities": ["tool_use"],
                }
            },
        }
        scenarios = {
            "unconfirmed_default": facts.resolve_model_selection(
                config=canary_config,
                explicit_argv_alias=None,
                hard={},
                required_hard_fields=(),
            ),
            "fixed_alias_conflict": facts.resolve_model_selection(
                config=canary_config,
                explicit_argv_alias=CANARY_ALIAS,
                hard=profile.hard,
                required_hard_fields=profile.required_hard_fields,
            ),
            "declared_alias_conflict": facts.resolve_model_selection(
                config=canary_config,
                explicit_argv_alias=CANARY_ALIAS,
                declared={"model_alias": k28.MODEL_ALIAS},
                hard={},
                required_hard_fields=(),
            ),
            "provider_mismatch": facts.resolve_model_selection(
                config=canary_config,
                explicit_argv_alias=CANARY_ALIAS,
                hard={"provider_id": k28.PROVIDER_ID, "model_id": CANARY_MODEL},
                required_hard_fields=("provider_id", "model_id"),
            ),
            "missing_entry": facts.resolve_model_selection(
                config={"models": {}},
                explicit_argv_alias=CANARY_ALIAS,
                hard={"connection_ref": "opaque-ref"},
                required_hard_fields=("connection_ref",),
            ),
            "parser_failure": facts.resolve_model_selection(
                config={"models": {CANARY_ALIAS: ["not", "a", "table"]}},
                explicit_argv_alias=CANARY_ALIAS,
                hard={},
                required_hard_fields=(),
            ),
        }
        for name, payload in scenarios.items():
            with self.subTest(scenario=name):
                self.assertEqual(payload["status"], "blocked")
                blob = blob_of(payload)
                for canary in (CANARY_ALIAS, CANARY_PROVIDER, CANARY_MODEL, CANARY_CREDENTIAL):
                    self.assertNotIn(canary, blob)

    def test_blocked_build_entry_never_echoes_canaries(self):
        profile = facts.adapter_profile(facts.K28_ADAPTER)
        runner_id = facts.runner_id_for(
            profile.runtime, host_scope="canary-host", workspace_scope="canary-ws"
        )["runner_id"]
        for overrides in (
            {"runner_fields": {"display_name": "", "adapter_status": CANARY_PROVIDER}},
            {"binding_fields": {"provider_id": CANARY_CREDENTIAL}},
            {"binding_fields": {"runner_id": "runner:canary-0000", "model_display_name": CANARY_ALIAS}},
        ):
            with self.subTest(overrides=sorted(overrides)):
                runner_fields = make_runner_fields(runner_id)
                runner_fields.update(overrides.get("runner_fields", {}))
                binding_fields = make_binding_fields(runner_id)
                binding_fields.update(overrides.get("binding_fields", {}))
                entry = facts.build_entry(
                    adapter=profile.adapter,
                    member_id=profile.member_id,
                    project_id="prj_canary",
                    runner_fields=runner_fields,
                    binding_fields=binding_fields,
                    sources={
                        "model_alias": {
                            "value": CANARY_ALIAS,
                            "source": "argv_explicit_selection",
                        },
                        CANARY_SOURCE_KEY: {"value": CANARY_CREDENTIAL},
                    },
                    source_context=None,
                )
                self.assertEqual(entry["status"], "blocked")
                blob = blob_of(entry)
                for canary in (CANARY_ALIAS, CANARY_PROVIDER, CANARY_MODEL, CANARY_CREDENTIAL, CANARY_SOURCE_KEY):
                    self.assertNotIn(canary, blob)
                for key in ("runner", "binding", "source_fingerprint", "public_config_identity"):
                    self.assertNotIn(key, entry)

    def test_credential_like_public_inputs_are_dropped_from_fingerprint(self):
        fingerprint = facts.source_fingerprint(
            adapter=CANARY_CREDENTIAL,
            runtime=CANARY_CREDENTIAL,
            host_scope=CANARY_CREDENTIAL,
            workspace_scope=CANARY_CREDENTIAL,
            selected_alias=CANARY_ALIAS,
            alias_source="argv_explicit_selection",
            config_identity={"origin": CANARY_CREDENTIAL, "content_sha256": CANARY_CREDENTIAL},
        )
        inputs = fingerprint["nonsecret_inputs"]
        self.assertIsNone(inputs["adapter"])
        self.assertIsNone(inputs["runtime"])
        self.assertIsNone(inputs["host_scope"])
        self.assertIsNone(inputs["workspace_scope"])
        self.assertEqual(inputs["config_identity"], {"origin": "unknown", "content_sha256": None})
        self.assertEqual(inputs["alias_source"], "argv_explicit_selection")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(fingerprint))
        unknown_alias_source = facts.source_fingerprint(alias_source=CANARY_PROVIDER)
        self.assertEqual(
            unknown_alias_source["nonsecret_inputs"]["alias_source"], "unknown"
        )
        self.assertNotIn(CANARY_PROVIDER, blob_of(unknown_alias_source))

    def test_unknown_nested_native_hard_declared_keys_are_ignored(self):
        identity = facts.public_config_identity(
            selected_alias=CANARY_ALIAS,
            native={"provider_id": k28.PROVIDER_ID, CANARY_SOURCE_KEY: CANARY_CREDENTIAL},
            hard={"model_source": "builtin", CANARY_SOURCE_KEY: CANARY_CREDENTIAL},
            declared={"connection_ref": k28.CONNECTION_REF, CANARY_SOURCE_KEY: CANARY_CREDENTIAL},
            default_alias_confirmed=False,
        )
        projection = identity["projection"]
        self.assertEqual(list(projection["native"]), ["provider_id", "model_id", "model_display_name", "capabilities"])
        self.assertEqual(
            list(projection["hard"]),
            ["model_source", "provider_id", "connection_ref", "model_id", "model_alias_sha256"],
        )
        self.assertEqual(list(projection["declared"]), ["model_source", "connection_ref"])
        self.assertEqual(
            set(projection["native"]),
            set(facts.PUBLIC_CONFIG_NATIVE_FIELDS),
        )
        blob = blob_of(identity)
        self.assertNotIn(CANARY_SOURCE_KEY, blob)
        self.assertNotIn(CANARY_CREDENTIAL, blob)


class TestPublicIdentityAndFingerprint(unittest.TestCase):
    """合同 §5：公开投影与漂移指纹。"""

    def test_fingerprint_is_stable_for_same_public_facts(self):
        config = make_config()
        first = build_k28_entry(config)
        second = build_k28_entry(config)
        self.assertEqual(
            first["source_fingerprint"]["fingerprint"],
            second["source_fingerprint"]["fingerprint"],
        )
        self.assertEqual(
            first["public_config_identity"]["content_sha256"],
            second["public_config_identity"]["content_sha256"],
        )

    def test_fingerprint_changes_on_public_fact_drift(self):
        config = make_config()
        baseline = build_k28_entry(config)["source_fingerprint"]["fingerprint"]
        variants = {
            "scope": build_k28_entry(config, workspace_scope="other-ws")["source_fingerprint"],
            "host": build_k28_entry(config, host_scope="other-host")["source_fingerprint"],
            "origin": build_k28_entry(config, origin="override_layer")["source_fingerprint"],
            "alias_layer": build_k28_entry(
                make_config(default_model=k28.MODEL_ALIAS), layer="native_default"
            )["source_fingerprint"],
            "declared": build_k28_entry(
                config, declared={"model_source": "builtin"}
            )["source_fingerprint"],
        }
        for name, fingerprint in variants.items():
            with self.subTest(variant=name):
                self.assertNotEqual(baseline, fingerprint["fingerprint"])

        # provider/model 是硬契约常量，改动会直接阻断；可解析的公开事实漂移用
        # native display_name / capabilities 与 alias 条目其它公开字段验证。
        drift_models = {
            k28.MODEL_ALIAS: {
                "provider": k28.PROVIDER_ID,
                "model": k28.MODEL_ID,
                "display_name": "K2.8 Preview (drifted label)",
                "capabilities": ["tool_use"],
            },
            K3_ALIAS: {
                "provider": k28.PROVIDER_ID,
                "model": "k3",
                "display_name": "K3",
                "capabilities": ["tool_use"],
            },
        }
        native_drift = build_k28_entry(make_config(models=drift_models))
        self.assertNotEqual(
            build_k28_entry(config)["public_config_identity"]["content_sha256"],
            native_drift["public_config_identity"]["content_sha256"],
        )
        self.assertNotEqual(baseline, native_drift["source_fingerprint"]["fingerprint"])

    def test_public_fact_drift_also_changes_fingerprint_when_digest_matches(self):
        # 只改公开 fact、但 fingerprint 输入集合本身没变时，靠 config_identity 摘要体现漂移。
        config = make_config()
        baseline = build_k28_entry(config)
        drifted = build_k28_entry(
            make_config(
                models={
                    k28.MODEL_ALIAS: {
                        "provider": k28.PROVIDER_ID,
                        "model": k28.MODEL_ID,
                        "display_name": "K2.8 Preview",
                        "capabilities": ["thinking", "tool_use", "vision"],
                    },
                    K3_ALIAS: {
                        "provider": k28.PROVIDER_ID,
                        "model": "k3",
                        "display_name": "K3",
                        "capabilities": ["tool_use"],
                    },
                }
            )
        )
        self.assertNotEqual(
            baseline["public_config_identity"]["content_sha256"],
            drifted["public_config_identity"]["content_sha256"],
        )
        self.assertNotEqual(
            baseline["source_fingerprint"]["fingerprint"],
            drifted["source_fingerprint"]["fingerprint"],
        )
        self.assertEqual(
            baseline["source_fingerprint"]["nonsecret_inputs"]["selected_alias_sha256"],
            drifted["source_fingerprint"]["nonsecret_inputs"]["selected_alias_sha256"],
        )

    def test_alias_or_source_layer_drift_changes_fingerprint(self):
        argv_entry = build_k28_entry(make_config(default_model=k28.MODEL_ALIAS), layer="argv")
        default_entry = build_k28_entry(make_config(default_model=k28.MODEL_ALIAS), layer="native_default")
        self.assertNotEqual(
            argv_entry["source_fingerprint"]["fingerprint"],
            default_entry["source_fingerprint"]["fingerprint"],
        )
        self.assertEqual(
            argv_entry["source_fingerprint"]["nonsecret_inputs"]["alias_source"],
            "argv_explicit_selection",
        )
        self.assertEqual(
            default_entry["source_fingerprint"]["nonsecret_inputs"]["alias_source"],
            "native_default_confirmed",
        )
        # 仅默认来源已确认时 public projection 才有 default_alias_sha256。
        self.assertIsNone(
            argv_entry["public_config_identity"]["projection"]["default_alias_sha256"]
        )
        self.assertEqual(
            default_entry["public_config_identity"]["projection"]["default_alias_sha256"],
            hashlib.sha256(k28.MODEL_ALIAS.encode("utf-8")).hexdigest(),
        )

    def test_credential_only_change_keeps_public_projection(self):
        first = make_config(
            providers={k28.PROVIDER_ID: {"type": "kimi", "api_key": CANARY_CREDENTIAL}}
        )
        second = make_config(
            providers={
                k28.PROVIDER_ID: {
                    "type": "kimi",
                    "api_key": "sk-other0123456789abcdef0123456789abcdef",
                }
            }
        )
        first_entry = build_k28_entry(first)
        second_entry = build_k28_entry(second)
        self.assertEqual(
            first_entry["public_config_identity"], second_entry["public_config_identity"]
        )
        self.assertEqual(
            first_entry["source_fingerprint"]["fingerprint"],
            second_entry["source_fingerprint"]["fingerprint"],
        )
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(first_entry))
        self.assertNotIn("sk-other0123456789abcdef0123456789abcdef", blob_of(second_entry))

    def test_public_projection_does_not_export_the_whole_config(self):
        entry = build_k28_entry(
            make_config(providers={k28.PROVIDER_ID: {"type": "kimi", "api_key": CANARY_CREDENTIAL}})
        )
        projection = entry["public_config_identity"]["projection"]
        self.assertEqual(
            list(projection),
            [
                "schema",
                "selected_alias_sha256",
                "default_alias_sha256",
                "native",
                "hard",
                "declared",
            ],
        )
        blob = blob_of(entry["public_config_identity"])
        for leaked in ("providers", "api_key", "token", "password", CANARY_CREDENTIAL):
            self.assertNotIn(leaked, blob)
        self.assertEqual(
            entry["public_config_identity"]["content_sha256"],
            hashlib.sha256(facts.canonical_json(projection).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            entry["source_fingerprint"]["fingerprint"],
            hashlib.sha256(
                facts.canonical_json(entry["source_fingerprint"]["nonsecret_inputs"]).encode("utf-8")
            ).hexdigest()[:32],
        )

    def test_internal_provenance_digest_is_not_exported(self):
        config = make_config()
        provenance = facts.native_provenance_for(
            config, origin="native_profile_loaded", confirmed=True
        )
        internal = provenance["config_content_sha256"]
        entry = build_k28_entry(config)
        exported = entry["source_fingerprint"]["nonsecret_inputs"]["config_identity"][
            "content_sha256"
        ]
        self.assertEqual(exported, entry["public_config_identity"]["content_sha256"])
        self.assertNotEqual(internal, exported)
        self.assertNotIn(internal, blob_of(entry))
        self.assertEqual(entry["source_fingerprint"]["nonsecret_inputs"]["config_identity"]["origin"], "native_profile_loaded")

    def test_digest_lengths_and_schemas(self):
        entry = build_k28_entry(make_config())
        self.assertEqual(len(entry["public_config_identity"]["content_sha256"]), 64)
        self.assertEqual(len(entry["source_fingerprint"]["fingerprint"]), 32)
        self.assertEqual(entry["public_config_identity"]["schema"], facts.PUBLIC_CONFIG_SCHEMA)
        self.assertEqual(
            entry["source_fingerprint"]["schema"], facts.SOURCE_FINGERPRINT_SCHEMA
        )
        self.assertRegex(entry["public_config_identity"]["content_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(entry["source_fingerprint"]["fingerprint"], r"^[0-9a-f]{32}$")

    def test_projection_normalizes_invalid_values_to_null(self):
        identity = facts.public_config_identity(
            selected_alias="   ",
            native={
                "provider_id": CANARY_CREDENTIAL,
                "model_id": 123,
                "model_display_name": "  ",
                "capabilities": ["tool_use", "tool_use"],
            },
            hard={"model_source": "bogus", "connection_ref": "native-login.exe", "model_id": ""},
            declared={"model_source": "builtin", "connection_ref": k28.CONNECTION_REF},
            default_alias="alias",
            default_alias_confirmed=True,
        )
        projection = identity["projection"]
        self.assertIsNone(projection["selected_alias_sha256"])
        self.assertIsNone(projection["native"]["provider_id"])
        self.assertIsNone(projection["native"]["model_id"])
        self.assertIsNone(projection["native"]["model_display_name"])
        self.assertIsNone(projection["native"]["capabilities"])
        self.assertIsNone(projection["hard"]["model_source"])
        self.assertIsNone(projection["hard"]["connection_ref"])
        self.assertIsNone(projection["hard"]["model_id"])
        self.assertEqual(projection["declared"]["model_source"], "builtin")
        self.assertEqual(projection["declared"]["connection_ref"], k28.CONNECTION_REF)
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(identity))

    def test_default_alias_confirmed_flag_must_be_strict_bool(self):
        with self.assertRaises(facts.AdapterBindingFactsError) as ctx:
            facts.public_config_identity(default_alias="a", default_alias_confirmed="true")
        self.assertEqual(ctx.exception.code, "E_FLAG_NOT_BOOL")


class TestAdapterProfiles(unittest.TestCase):
    """合同 §4 表格：K28 同源常量、K3 独立、DSH/Codex 来源不足。"""

    def test_profiles_cover_expected_adapters(self):
        names = set(facts.ADAPTER_NAMES)
        self.assertEqual(
            names,
            {
                "agent:kimi-code-k28-preview",
                "agent:kimi",
                "agent:deepseek",
                "agent:codex",
            },
        )
        for name in facts.ADAPTER_NAMES:
            profile = facts.adapter_profile(name)
            self.assertEqual(profile.adapter, name)
            self.assertTrue(profile.runtime)

    def test_k28_profile_references_existing_constants(self):
        profile = facts.adapter_profile(facts.K28_ADAPTER)
        self.assertEqual(profile.runtime, k28.RUNTIME)
        self.assertEqual(profile.explicit_argv_alias, k28.MODEL_ALIAS)
        self.assertEqual(profile.hard["model_source"], k28.MODEL_SOURCE)
        self.assertEqual(profile.hard["provider_id"], k28.PROVIDER_ID)
        self.assertEqual(profile.hard["connection_ref"], k28.CONNECTION_REF)
        self.assertEqual(profile.hard["model_id"], k28.MODEL_ID)
        self.assertEqual(profile.hard["model_alias"], k28.MODEL_ALIAS)
        self.assertEqual(
            set(profile.required_hard_fields),
            {"model_source", "connection_ref", "provider_id", "model_id", "model_alias"},
        )

    def test_k28_profile_is_same_source_as_executor_constants(self):
        # 行为证据：改动既有常量会同步反映到 profile（不是抄字面量）。
        for attribute, replacement in (
            ("RUNTIME", "kimi-code-patched"),
            ("MODEL_ALIAS", "kimi-code/patched-alias"),
            ("MODEL_ID", "patched-model"),
            ("PROVIDER_ID", "managed:patched"),
            ("CONNECTION_REF", "patched-connection-ref"),
            ("MODEL_SOURCE", "custom_api"),
        ):
            with self.subTest(attribute=attribute):
                with patch.object(k28, attribute, replacement):
                    profile = facts.adapter_profile(facts.K28_ADAPTER)
                    if attribute == "MODEL_ALIAS":
                        self.assertEqual(profile.explicit_argv_alias, replacement)
                        self.assertEqual(profile.hard["model_alias"], replacement)
                    elif attribute == "RUNTIME":
                        self.assertEqual(profile.runtime, replacement)
                    else:
                        key = {
                            "MODEL_ID": "model_id",
                            "PROVIDER_ID": "provider_id",
                            "CONNECTION_REF": "connection_ref",
                            "MODEL_SOURCE": "model_source",
                        }[attribute]
                        self.assertEqual(profile.hard[key], replacement)
        # 常量未被本片改写。
        self.assertEqual(k28.MODEL_ALIAS, "kimi-code/kimi-for-coding")
        self.assertEqual(k28.RUNTIME, "kimi-code")

    def test_profiles_are_immutable(self):
        profile = facts.adapter_profile(facts.K28_ADAPTER)
        with self.assertRaises(FrozenInstanceError):
            profile.runtime = "codex"
        with self.assertRaises(TypeError):
            profile.hard["model_id"] = "patched"
        with self.assertRaises(TypeError):
            profile.hard["new_key"] = "value"
        self.assertIsInstance(profile.required_hard_fields, tuple)
        public = profile.as_public_dict()
        self.assertEqual(public["hard"]["provider_id"], k28.PROVIDER_ID)
        public["hard"]["provider_id"] = "mutated"
        self.assertEqual(profile.hard["provider_id"], k28.PROVIDER_ID)
        self.assertEqual(profile.scope_source, "caller_explicit_scope")
        self.assertFalse(hasattr(profile, "host_scope"))

    def test_k3_profile_does_not_inherit_k28_alias(self):
        profile = facts.adapter_profile(facts.K3_ADAPTER)
        self.assertIsNone(profile.explicit_argv_alias)
        self.assertEqual(profile.runtime, k28.RUNTIME)
        self.assertNotIn(k28.MODEL_ALIAS, profile.hard.values())
        self.assertEqual(profile.required_hard_fields, ())
        self.assertEqual(dict(profile.hard), {})

    def test_unverified_source_profiles_stay_blocked(self):
        config = make_config(default_model=k28.MODEL_ALIAS)
        provenance = facts.native_provenance_for(
            config, origin="native_profile_loaded", confirmed=True
        )
        for name in (facts.DSH_ADAPTER, facts.CODEX_ADAPTER):
            with self.subTest(adapter=name):
                profile = facts.adapter_profile(name)
                self.assertEqual(profile.hard, {})
                self.assertEqual(profile.explicit_argv_alias, None)
                result = facts.resolve_model_selection(
                    config=config,
                    explicit_argv_alias=None,
                    hard=profile.hard,
                    native_provenance=provenance,
                    required_hard_fields=profile.required_hard_fields,
                )
                self.assertEqual(result["status"], "blocked")
                self.assertTrue(
                    all(item["code"] == "E_SOURCE_UNAVAILABLE" for item in result["blocked"])
                )
                blob = blob_of(result)
                for pseudo in ("unknown", "K2.8 Preview", k28.MODEL_ID, k28.PROVIDER_ID):
                    self.assertNotIn(pseudo, blob)

    def test_no_load_native_config_call_in_the_chain(self):
        profile = facts.adapter_profile(facts.K28_ADAPTER)
        config = make_config()
        with patch.object(
            k28, "load_native_config", side_effect=AssertionError("must not read real config")
        ):
            selection = facts.resolve_model_selection(
                config=config,
                explicit_argv_alias=profile.explicit_argv_alias,
                hard=profile.hard,
                required_hard_fields=profile.required_hard_fields,
            )
            self.assertEqual(selection["status"], "ready")
            runner_id = facts.runner_id_for(
                profile.runtime, host_scope="iso-host", workspace_scope="iso-ws"
            )["runner_id"]
            entry = facts.build_entry(
                adapter=profile.adapter,
                member_id=profile.member_id,
                project_id="prj_iso",
                runner_fields=make_runner_fields(runner_id),
                binding_fields={
                    "runner_id": runner_id,
                    **{k: v["value"] for k, v in selection["fields"].items()},
                },
                sources={"model_alias": {"value": selection["alias"], "source": selection["alias_source"]}},
                source_context={
                    "host_scope": "iso-host",
                    "workspace_scope": "iso-ws",
                    "origin": "native_profile_loaded",
                    "selection": selection,
                },
            )
            self.assertEqual(entry["status"], "ready")


ISOLATION_SCRIPT = r'''
import json
import os
import sys

for entry in (sys.argv[1], sys.argv[2]):
    if entry not in sys.path:
        sys.path.insert(0, entry)

# 先导入重依赖：钩子只统计本模块导入与其后的主链路。
import dataclasses
import hashlib
import pathlib
import re
import types
import typing
import unicodedata

import pydantic
import server.models
import kimi_k28_executor

open_events = []
io_events = []
env_reads = []


def _hook(event, args):
    if event == "open":
        try:
            open_events.append([str(args[0]), str(args[1])])
        except Exception:
            open_events.append(["<unprintable>", "<unprintable>"])
    elif event.startswith(
        (
            "socket.",
            "subprocess.",
            "os.system",
            "os.exec",
            "os.spawn",
            "os.remove",
            "os.rename",
            "os.mkdir",
            "os.rmdir",
            "shutil.",
            "sqlite3.",
            "urllib.",
            "ftplib.",
            "http.client.",
        )
    ):
        io_events.append(event)


sys.addaudithook(_hook)

_real_environ = os.environ


class _SpyEnviron(dict):
    def __getitem__(self, key):
        env_reads.append(key)
        return dict.__getitem__(self, key)

    def get(self, key, *default):
        env_reads.append(key)
        return dict.get(self, key, *default)

    def __contains__(self, key):
        env_reads.append(key)
        return dict.__contains__(self, key)


os.environ = _SpyEnviron(_real_environ)

import adapter_binding_facts as facts

import_env_reads = list(env_reads)
import_open_events = list(open_events)
del env_reads[:]
del open_events[:]
del io_events[:]

runner_id = facts.runner_id_for(
    "kimi-code", host_scope="isolation-host", workspace_scope="isolation-ws"
)["runner_id"]
profile = facts.adapter_profile(facts.K28_ADAPTER)
config = {
    "default_model": "kimi-code/k3",
    "providers": {"managed:kimi-code": {"api_key": "sk-isolation-canary-0000000000000000"}},
    "models": {
        kimi_k28_executor.MODEL_ALIAS: {
            "provider": kimi_k28_executor.PROVIDER_ID,
            "model": kimi_k28_executor.MODEL_ID,
            "display_name": "K2.8 Preview",
            "capabilities": ["tool_use"],
        },
        "kimi-code/k3": {
            "provider": kimi_k28_executor.PROVIDER_ID,
            "model": "k3",
            "display_name": "K3",
            "capabilities": ["tool_use"],
        },
    },
}
selection = facts.resolve_model_selection(
    config=config,
    explicit_argv_alias=profile.explicit_argv_alias,
    hard=profile.hard,
    required_hard_fields=profile.required_hard_fields,
)
entry = facts.build_entry(
    adapter=profile.adapter,
    member_id=profile.member_id,
    project_id="prj_isolation",
    runner_fields={
        "runner_id": runner_id,
        "runtime": profile.runtime,
        "display_name": "Kimi Code CLI",
        "adapter_status": "unverified",
        "adapter_note": None,
        "capabilities": ["tool_use"],
    },
    binding_fields={
        "runner_id": runner_id,
        "model_source": selection["fields"]["model_source"]["value"],
        "provider_id": selection["fields"]["provider_id"]["value"],
        "connection_ref": selection["fields"]["connection_ref"]["value"],
        "model_id": selection["fields"]["model_id"]["value"],
        "model_alias": selection["fields"]["model_alias"]["value"],
        "model_display_name": selection["fields"]["model_display_name"]["value"],
    },
    sources={"model_alias": {"value": kimi_k28_executor.MODEL_ALIAS, "source": "argv_explicit_selection"}},
    source_context={
        "host_scope": "isolation-host",
        "workspace_scope": "isolation-ws",
        "origin": "native_profile_loaded",
        "selection": selection,
    },
)
facts.public_config_identity(
    selected_alias=kimi_k28_executor.MODEL_ALIAS,
    native={"provider_id": kimi_k28_executor.PROVIDER_ID},
    hard=dict(profile.hard),
    declared={"model_source": kimi_k28_executor.MODEL_SOURCE},
)
facts.source_fingerprint(
    adapter=profile.adapter,
    runtime=profile.runtime,
    host_scope="isolation-host",
    workspace_scope="isolation-ws",
    selected_alias=kimi_k28_executor.MODEL_ALIAS,
    alias_source="argv_explicit_selection",
    config_identity={"origin": "native_profile_loaded", "content_sha256": "0" * 64},
)
facts.sanitize_sources({"model_alias": {"value": "x", "source": "argv_explicit_selection"}})
facts.native_provenance_for(config, origin="native_profile_loaded", confirmed=True)
os.environ = _real_environ

result = {
    "selection_status": selection["status"],
    "entry_status": entry["status"],
    "runner_id": runner_id,
    "import_env_reads": import_env_reads,
    "import_open_events": import_open_events,
    "scenario_env_reads": list(env_reads),
    "scenario_open_events": list(open_events),
    "scenario_io_events": list(io_events),
    "mcp_modules": sorted(
        name
        for name in sys.modules
        if "talk_task_tools" in name
        or name == "mcp"
        or name.startswith("mcp.")
        or "talk_get_delivery" in name
        or "talk_delivery" in name
    ),
    "bridges_imported": "bridges" in sys.modules,
}
print(json.dumps(result))
'''


class TestIsolationAndImportSideEffects(unittest.TestCase):
    """导入与主链路的行为级隔离证据（独立子进程 + 审计钩子 + 环境读取探针）。"""

    def _run_isolation_probe(self) -> dict:
        with tempfile.TemporaryDirectory(prefix="c1-isolation-") as workdir:
            out_path = Path(workdir) / "stdout.txt"
            err_path = Path(workdir) / "stderr.txt"
            with out_path.open("w", encoding="utf-8") as out_handle, err_path.open(
                "w", encoding="utf-8"
            ) as err_handle:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        ISOLATION_SCRIPT,
                        str(PROJECT_ROOT),
                        str(PROJECT_ROOT / "scripts"),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=out_handle,
                    stderr=err_handle,
                    cwd=str(PROJECT_ROOT),
                    timeout=180,
                )
            self.assertEqual(completed.returncode, 0, err_path.read_text(encoding="utf-8"))
            payload = json.loads(out_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        return payload

    def test_import_and_chain_have_no_file_env_network_or_process_side_effects(self):
        payload = self._run_isolation_probe()
        self.assertEqual(payload["selection_status"], "ready")
        self.assertEqual(payload["entry_status"], "ready")
        self.assertTrue(payload["runner_id"].startswith("runner:"))

        # 主链路零文件打开、零环境读取、零 socket / 子进程 / DB 事件。
        self.assertEqual(payload["scenario_open_events"], [])
        self.assertEqual(payload["scenario_env_reads"], [])
        self.assertEqual(payload["scenario_io_events"], [])

        # 导入期只读取本模块自己的源码/字节码；不碰真实 native 配置、Key 或环境。
        self.assertEqual(payload["import_env_reads"], [])
        repo = str(PROJECT_ROOT).replace("\\", "/")
        self.assertTrue(payload["import_open_events"])
        for path, mode in payload["import_open_events"]:
            normalized = path.replace("\\", "/")
            self.assertTrue(normalized.startswith(repo), normalized)
            self.assertIn("adapter_binding_facts", normalized)
            if "__pycache__" in normalized:
                self.assertIn(mode, ("r", "wb"))
            else:
                self.assertEqual(mode, "r")

    def test_no_mcp_tool_module_is_imported(self):
        payload = self._run_isolation_probe()
        self.assertEqual(payload["mcp_modules"], [])
        self.assertFalse(payload["bridges_imported"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
