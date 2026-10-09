"""ROLE-BINDING-B3 MCP/工具消费：``talk_list_agents`` 只读绑定字段合同测试。

覆盖实施计划 §3.2 与 B3 任务包验收标准 1–8：

- 项目路径每个角色新增只读 ``binding`` / ``binding_state``，取自**同一次**
  ``GET /api/projects/{id}/agents`` 响应，不额外发绑定/身份请求；
- ``bound`` / ``partial`` / ``runner_missing`` / ``runner_retired`` / ``unconfigured``
  以及保留配置原样透传，不把异常状态压成 ``bound``；
- 旧后端缺新增键、非项目路径都诚实降级成 ``null``（不造 ``unconfigured`` / ``bound``）；
- 只输出 B1a 公开绑定字段，未知敏感键（凭据正文/凭据路径/实例日志）与任何
  ``binding_match*`` 都不带入角色摘要，也不从模型名/业务角色/实例推断绑定值；
- 目录仍是九个工具，inputSchema 与 B3 冻结基线逐对象一致，只允许
  ``talk_list_agents`` 中文描述补充只读绑定、null 降级与“配置不等于实际能力”；
- 集成证据：隔离 uvicorn 服务 + 独立 stdio 子进程分别调用目录与 ``talk_list_agents``；
- ``development_requirements`` 在整份响应里仍只出现一次，角色清单也只一次。

全部用例使用合成载荷或进程内隔离服务/临时库；不启动生产服务、不调用模型、不读 Key、
不改生产数据库/名册/.talk/安装配置，也不做主动长等待或真实模型能力测试。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import server.main as main
from bridges import talk_task_tools
from bridges.talk_task_tools import (
    ROLE_BINDING_PUBLIC_FIELDS,
    TOOL_SCHEMAS,
    dispatch_tool,
    role_binding_state_value,
    role_binding_summary,
)
from cli.talk import scaffold_project
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer
from tests.test_talk_task_tools import run_stdio_process

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_ENTRY = PROJECT_ROOT / "bridges" / "talk_terminal_mcp.py"
BASELINE_TOOL_MODULE = (
    PROJECT_ROOT
    / ".tmp"
    / "runner-role-binding-b3"
    / "baseline"
    / "bridges"
    / "talk_task_tools.py"
)

# 九个 Task Hall 工具的名字与顺序（与 B3 冻结基线一致，本片不新增/改名）。
PROJECT_TOOL_NAMES = (
    "talk_list_agents",
    "talk_delegate_task",
    "talk_get_task",
    "talk_list_tasks",
    "talk_wait_tasks",
    "talk_reply_task",
    "talk_cancel_task",
    "talk_collect_result",
    "talk_get_delivery",
)
# 冻结摘要只覆盖 names + inputSchema（不含任何工具描述文本）。
FROZEN_TOOL_CATALOG_SHA256 = (
    "a135482ce3338547eda22199d605b00a77801e71e28f0b2267abc428b2c58399"
)

RUNNER_ID = "runner:dsh-cli"
RUNNER_RUNTIME = "dsh"
RUNNER_DISPLAY_NAME = "DeepSeek Harness (CLI)"
MODEL_SOURCE = "builtin"
PROVIDER_ID = "managed:deepseek"
CONNECTION_REF = "native-deepseek-managed-login"
MODEL_ID = "deepseek-flash"
MODEL_ALIAS = "dsh/deepseek-flash"
MODEL_DISPLAY_NAME = "DeepSeek Flash"


def fingerprint_of(
    runner_id: str = RUNNER_ID,
    runtime: str = RUNNER_RUNTIME,
    model_source: str = MODEL_SOURCE,
    provider_id: str = PROVIDER_ID,
    connection_ref: str = CONNECTION_REF,
    model_id: str = MODEL_ID,
) -> str:
    payload = "|".join(
        [runner_id, runtime, model_source, provider_id, connection_ref, model_id]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def binding_payload(**overrides) -> dict:
    payload = {
        "runner_id": RUNNER_ID,
        "runtime": RUNNER_RUNTIME,
        "runner_display_name": RUNNER_DISPLAY_NAME,
        "runner_status": "adapted",
        "model_source": MODEL_SOURCE,
        "provider_id": PROVIDER_ID,
        "connection_ref": CONNECTION_REF,
        "model_id": MODEL_ID,
        "model_alias": MODEL_ALIAS,
        "model_display_name": MODEL_DISPLAY_NAME,
        "binding_state": "bound",
        "binding_fingerprint": fingerprint_of(),
        "updated_by": "human:bobo",
        "updated_at": "2026-10-09T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def agent_entry(member_id: str = "agent:worker", **overrides) -> dict:
    entry = {
        "member_id": member_id,
        "display_name": "Worker",
        "business_role": "dev",
        "decision_tier": "execution",
        "capability_summary": ["代码实现"],
        "availability": "idle",
        "instances": [],
    }
    entry.update(overrides)
    return entry


class FakeApi:
    """脚本化 ``_api_request``：按 (method, path) 返回合成载荷并记录调用顺序。

    未命中的路径直接失败，防止“悄悄多发一次请求/多写一次”被忽略。
    """

    def __init__(self, routes: dict[tuple[str, str], object]) -> None:
        self.routes = dict(routes)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, path, **kwargs):
        key = (method.upper(), path)
        self.calls.append(key)
        if key not in self.routes:
            raise AssertionError(f"unexpected TALK API request: {key}")
        value = self.routes[key]
        return value() if callable(value) else value

    @property
    def writes(self) -> list[tuple[str, str]]:
        return [call for call in self.calls if call[0] != "GET"]


def project_routes(
    project_id: str,
    agents: list[dict],
    *,
    requirements: str | None = None,
    member_ids: list[str] | None = None,
) -> dict[tuple[str, str], object]:
    return {
        ("GET", f"/api/projects/{project_id}"): {
            "project_id": project_id,
            "development_requirements": requirements,
        },
        ("GET", f"/api/projects/{project_id}/agents"): agents,
        ("GET", "/api/members"): [
            {"id": member_id, "kind": "agent", "disabled_at": None}
            for member_id in (member_ids or [agent["member_id"] for agent in agents])
        ],
        ("GET", "/api/members/me"): {"id": "human:bobo", "kind": "human"},
    }


def _load_baseline_tool_module():
    if not BASELINE_TOOL_MODULE.is_file():
        return None
    spec = importlib.util.spec_from_file_location(
        "talk_task_tools_b3_baseline", BASELINE_TOOL_MODULE
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ════════════════════════════════════════════════════════════════════
# 1–6：合成载荷下的字段透传、降级、隔离与请求边界
# ════════════════════════════════════════════════════════════════════


class RoleBindingPassthroughTests(unittest.TestCase):
    """只读透传：bound 与异常/未配置状态都如实表达，不从其它维度推断。"""

    def _list(self, agents: list[dict], **routes_kwargs) -> tuple[dict, FakeApi]:
        api = FakeApi(project_routes("prj_bind", agents, **routes_kwargs))
        with patch.multiple(
            "bridges.talk_task_tools", _api_request=api
        ):
            result = dispatch_tool("talk_list_agents", {"project_id": "prj_bind"})
        return result, api

    def test_bound_role_passes_all_public_fields_and_state(self):
        binding = binding_payload()
        result, _ = self._list(
            [agent_entry(binding=binding, binding_state="bound")]
        )
        agent = result["agents"][0]
        self.assertEqual(agent["binding_state"], "bound")
        # 只输出公开白名单键，形状稳定。
        self.assertEqual(set(agent["binding"]), set(ROLE_BINDING_PUBLIC_FIELDS))
        for field, value in binding.items():
            self.assertEqual(agent["binding"][field], value, field)
        # 指纹与六维内容一致（不是由代码重新计算的“匹配结论”）。
        self.assertEqual(agent["binding"]["binding_fingerprint"], fingerprint_of())

    def test_reserved_and_abnormal_states_are_not_compressed_to_bound(self):
        partial = binding_payload(
            provider_id=None,
            binding_state="partial",
            binding_fingerprint=None,
            runtime=None,
        )
        runner_missing = binding_payload(
            runtime=None,
            runner_display_name=None,
            runner_status=None,
            binding_state="runner_missing",
            binding_fingerprint=None,
        )
        runner_retired = binding_payload(
            runner_status="retired", binding_state="runner_retired"
        )
        result, _ = self._list(
            [
                agent_entry("agent:partial", binding=partial, binding_state="partial"),
                agent_entry(
                    "agent:runner-missing",
                    binding=runner_missing,
                    binding_state="runner_missing",
                ),
                agent_entry(
                    "agent:runner-retired",
                    binding=runner_retired,
                    binding_state="runner_retired",
                ),
                agent_entry("agent:unconfigured", binding=None, binding_state="unconfigured"),
            ]
        )
        by_id = {agent["member_id"]: agent for agent in result["agents"]}

        self.assertEqual(by_id["agent:partial"]["binding_state"], "partial")
        self.assertIsNone(by_id["agent:partial"]["binding"]["provider_id"])
        self.assertIsNone(by_id["agent:partial"]["binding"]["binding_fingerprint"])
        # 保留配置：异常状态下行内已存的值照存，不因为无效被清空。
        self.assertEqual(by_id["agent:partial"]["binding"]["runner_id"], RUNNER_ID)
        self.assertEqual(by_id["agent:partial"]["binding"]["model_id"], MODEL_ID)

        self.assertEqual(
            by_id["agent:runner-missing"]["binding_state"], "runner_missing"
        )
        self.assertEqual(
            by_id["agent:runner-missing"]["binding"]["runner_id"], RUNNER_ID
        )
        self.assertIsNone(by_id["agent:runner-missing"]["binding"]["runtime"])
        self.assertIsNone(
            by_id["agent:runner-missing"]["binding"]["binding_fingerprint"]
        )

        self.assertEqual(
            by_id["agent:runner-retired"]["binding_state"], "runner_retired"
        )
        self.assertEqual(
            by_id["agent:runner-retired"]["binding"]["runner_status"], "retired"
        )
        self.assertEqual(
            by_id["agent:runner-retired"]["binding"]["binding_fingerprint"],
            fingerprint_of(),
        )

        self.assertEqual(
            by_id["agent:unconfigured"]["binding_state"], "unconfigured"
        )
        self.assertIsNone(by_id["agent:unconfigured"]["binding"])

    def test_unconfigured_state_is_never_inferred_from_role_or_instance(self):
        """业务角色与实例 runtime/model 都不得被当成绑定值填充缺失配置。"""
        result, _ = self._list(
            [
                agent_entry(
                    business_role="kimi-code/kimi-for-coding",
                    instances=[
                        {
                            "id": "worker-1",
                            "member_id": "agent:worker",
                            "runtime": "kimi-code",
                            "status": "idle",
                            "last_seen_at": "2026-10-09T00:00:00Z",
                        }
                    ],
                    binding=None,
                    binding_state="unconfigured",
                )
            ]
        )
        agent = result["agents"][0]
        self.assertIsNone(agent["binding"])
        self.assertEqual(agent["binding_state"], "unconfigured")
        # 业务角色与实例 runtime 仍如实出现在各自字段里，但不会被当成绑定值填充。
        self.assertEqual(agent["business_role"], "kimi-code/kimi-for-coding")
        self.assertEqual(agent["instances"][0]["runtime"], "kimi-code")
        payload = json.dumps(agent, ensure_ascii=False)
        self.assertNotIn("runner_id", payload)
        self.assertNotIn(CONNECTION_REF, payload)
        self.assertNotIn(MODEL_ID, payload)

    def test_old_backend_missing_keys_degrade_to_null(self):
        """旧后端角色条目没有 binding / binding_state：两者均为 null，不造状态。"""
        stale = agent_entry()
        stale.pop("binding", None)
        stale.pop("binding_state", None)
        result, api = self._list([stale])
        agent = result["agents"][0]
        self.assertIsNone(agent["binding"])
        self.assertIsNone(agent["binding_state"])
        payload = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("unconfigured", payload)
        self.assertNotIn('"bound"', payload)
        # 降级不引入任何新请求或写请求。
        self.assertEqual(
            api.calls,
            [
                ("GET", "/api/projects/prj_bind"),
                ("GET", "/api/projects/prj_bind/agents"),
                ("GET", "/api/members"),
                ("GET", "/api/members/me"),
            ],
        )

    def test_unknown_sensitive_and_match_keys_are_not_forwarded(self):
        poisoned = binding_payload(
            api_key="sk-live-should-not-leak",
            credential_path="C:/Users/agent/keys/native.json",
            token="Bearer should-not-leak",
            note="internal instance log",
            binding_match="match",
            binding_match_actual="match",
            binding_match_config="match",
        )
        binding_state = poisoned.pop("binding_state")
        result, _ = self._list(
            [agent_entry(binding=poisoned, binding_state=binding_state)]
        )
        agent = result["agents"][0]
        self.assertEqual(set(agent["binding"]), set(ROLE_BINDING_PUBLIC_FIELDS))
        payload = json.dumps(result, ensure_ascii=False)
        for leaked in (
            "sk-live-should-not-leak",
            "credential_path",
            "native.json",
            "Bearer should-not-leak",
            "internal instance log",
            "binding_match",
            "match",
        ):
            self.assertNotIn(leaked, payload)
        # 公开字段本身仍然照常透传。
        self.assertEqual(agent["binding"]["connection_ref"], CONNECTION_REF)
        self.assertEqual(agent["binding"]["model_alias"], MODEL_ALIAS)

    def test_non_project_path_sets_both_null_without_extra_requests(self):
        api = FakeApi(
            {
                ("GET", "/api/members"): [
                    {"id": "agent:worker", "kind": "agent", "disabled_at": None}
                ],
                ("GET", "/api/instances"): [],
            }
        )
        with patch.multiple("bridges.talk_task_tools", _api_request=api):
            with patch.dict(os.environ, {"TALK_PROJECT_ID": ""}, clear=False):
                result = dispatch_tool("talk_list_agents", {})
        self.assertIsNone(result["project_id"])
        agent = result["agents"][0]
        self.assertIsNone(agent["binding"])
        self.assertIsNone(agent["binding_state"])
        # 全局路径读取边界保持：只有成员与实例两次读取，没有项目/绑定/身份请求。
        self.assertEqual(
            api.calls, [("GET", "/api/members"), ("GET", "/api/instances")]
        )
        self.assertEqual(api.writes, [])

    def test_project_path_request_budget_has_no_binding_get_and_no_writes(self):
        api = FakeApi(
            project_routes(
                "prj_bind",
                [agent_entry(binding=binding_payload(), binding_state="bound")],
            )
        )
        with patch.multiple("bridges.talk_task_tools", _api_request=api):
            dispatch_tool("talk_list_agents", {"project_id": "prj_bind"})
        self.assertEqual(
            api.calls,
            [
                ("GET", "/api/projects/prj_bind"),
                ("GET", "/api/projects/prj_bind/agents"),
                ("GET", "/api/members"),
                ("GET", "/api/members/me"),
            ],
        )
        self.assertEqual(api.writes, [])
        self.assertFalse([call for call in api.calls if call[1].endswith("/binding")])

    def test_development_requirements_still_appears_once(self):
        result, _ = self._list(
            [agent_entry(binding=binding_payload(), binding_state="bound")],
            requirements="1.开发要求快照文本",
        )
        self.assertEqual(result["development_requirements"], "1.开发要求快照文本")
        payload = json.dumps(result, ensure_ascii=False)
        self.assertEqual(payload.count("development_requirements"), 1)
        for agent in result["agents"]:
            self.assertNotIn("development_requirements", agent)

    def test_helpers_are_pure_passthrough(self):
        """辅助函数本身不造值：缺键 → null，缺状态 → null，非对象 → None。"""
        self.assertIsNone(role_binding_summary(None))
        self.assertIsNone(role_binding_summary("runner:dsh-cli"))
        summary = role_binding_summary({"runner_id": RUNNER_ID, "extra": "x"})
        self.assertEqual(set(summary), set(ROLE_BINDING_PUBLIC_FIELDS))
        self.assertEqual(summary["runner_id"], RUNNER_ID)
        self.assertIsNone(summary["binding_fingerprint"])
        self.assertIsNone(role_binding_state_value(None))
        self.assertIsNone(role_binding_state_value("   "))
        self.assertIsNone(role_binding_state_value(7))
        self.assertEqual(role_binding_state_value("bound"), "bound")
        self.assertEqual(role_binding_state_value("runner_retired"), "runner_retired")


# ════════════════════════════════════════════════════════════════════
# 5：目录与 inputSchema 冻结（只允许 talk_list_agents 描述变化）
# ════════════════════════════════════════════════════════════════════


class ToolSurfaceFreezeTests(unittest.TestCase):
    def _catalog_digest(self) -> str:
        payload = {
            "names": [tool["name"] for tool in TOOL_SCHEMAS],
            "schemas": [tool["inputSchema"] for tool in TOOL_SCHEMAS],
        }
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def test_nine_tools_and_input_schemas_match_frozen_digest(self):
        self.assertEqual(len(TOOL_SCHEMAS), 9)
        self.assertEqual(
            tuple(tool["name"] for tool in TOOL_SCHEMAS), PROJECT_TOOL_NAMES
        )
        self.assertEqual(self._catalog_digest(), FROZEN_TOOL_CATALOG_SHA256)

    def test_input_schemas_match_b3_baseline_object_by_object(self):
        baseline = _load_baseline_tool_module()
        if baseline is None:
            self.skipTest(
                "B3 冻结基线不存在（.tmp/runner-role-binding-b3/baseline），"
                "只保留摘要冻结断言"
            )
        self.assertEqual(
            [tool["name"] for tool in baseline.TOOL_SCHEMAS],
            [tool["name"] for tool in TOOL_SCHEMAS],
        )
        for current, frozen in zip(TOOL_SCHEMAS, baseline.TOOL_SCHEMAS):
            self.assertEqual(
                current["inputSchema"], frozen["inputSchema"], current["name"]
            )
            if current["name"] != "talk_list_agents":
                # 其它工具的描述也必须逐字保持。
                self.assertEqual(
                    current["description"], frozen["description"], current["name"]
                )

    def test_list_agents_description_documents_binding_scope(self):
        description = next(
            tool["description"]
            for tool in TOOL_SCHEMAS
            if tool["name"] == "talk_list_agents"
        )
        for token in (
            "binding",
            "binding_state",
            "unconfigured",
            "runner_missing",
            "runner_retired",
            "旧后端",
            "connection_ref",
            "binding_match",
            "null",
        ):
            self.assertIn(token, description)
        self.assertIn("不代表", description)
        # 目录里没有新增工具，也没有重名。
        names = [tool["name"] for tool in TOOL_SCHEMAS]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("talk_get_role_binding", names)


# ════════════════════════════════════════════════════════════════════
# 1–4 + 7：隔离真实服务的消费路径
# ════════════════════════════════════════════════════════════════════


class RoleBindingToolConsumerLiveTests(RouteTestCase):
    """隔离 uvicorn：角色摘要与项目角色 API 的同一次响应一致，且只读。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        self.add_member("agent:other", api_key="other-key", display_name="Other")
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_tools", "display_name": "Tool Project"},
            ).raise_for_status()
            client.post(
                "/api/projects/prj_tools/sync",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "agents": [
                        {"member_id": "agent:worker", "business_role": "dev"},
                        {"member_id": "agent:other", "business_role": "reviewer"},
                    ]
                },
            ).raise_for_status()
            client.post(
                "/api/runners",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "runner_id": RUNNER_ID,
                    "runtime": RUNNER_RUNTIME,
                    "display_name": RUNNER_DISPLAY_NAME,
                    "adapter_status": "adapted",
                },
            ).raise_for_status()
            client.put(
                f"/api/projects/prj_tools/agents/{quote('agent:worker', safe='')}/binding",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "binding": {
                        "runner_id": RUNNER_ID,
                        "model_source": MODEL_SOURCE,
                        "provider_id": PROVIDER_ID,
                        "connection_ref": CONNECTION_REF,
                        "model_id": MODEL_ID,
                        "model_alias": MODEL_ALIAS,
                        "model_display_name": MODEL_DISPLAY_NAME,
                    }
                },
            ).raise_for_status()

    @staticmethod
    def _environment(base_url: str) -> dict[str, str]:
        return {
            "TALK_BASE_URL": base_url,
            "TALK_API_KEY": "bobo-key",
            "TALK_MEMBER_ID": "human:bobo",
            "TALK_PROJECT_ID": "prj_tools",
        }

    def test_bound_and_unconfigured_roles_match_project_agents_api(self):
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url)
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})
            with self.make_client() as client:
                direct = client.get(
                    "/api/projects/prj_tools/agents",
                    headers={"X-API-Key": "bobo-key"},
                ).json()

        self.assertEqual(result["project_id"], "prj_tools")
        summary_by_id = {agent["member_id"]: agent for agent in result["agents"]}
        direct_by_id = {agent["member_id"]: agent for agent in direct}
        self.assertEqual(sorted(summary_by_id), ["agent:other", "agent:worker"])

        worker = summary_by_id["agent:worker"]
        self.assertEqual(worker["binding_state"], "bound")
        self.assertEqual(worker["binding_state"], direct_by_id["agent:worker"]["binding_state"])
        for field in ROLE_BINDING_PUBLIC_FIELDS:
            self.assertEqual(
                worker["binding"][field],
                direct_by_id["agent:worker"]["binding"][field],
                field,
            )
        self.assertEqual(worker["binding"]["binding_fingerprint"], fingerprint_of())
        self.assertEqual(worker["binding"]["model_alias"], MODEL_ALIAS)

        other = summary_by_id["agent:other"]
        self.assertIsNone(other["binding"])
        self.assertEqual(other["binding_state"], "unconfigured")
        self.assertEqual(
            other["binding_state"], direct_by_id["agent:other"]["binding_state"]
        )

    def test_project_path_uses_existing_reads_only(self):
        calls: list[tuple[str, str]] = []
        real_request = talk_task_tools._api_request

        def recording_request(method, path, **kwargs):
            calls.append((method.upper(), path))
            return real_request(method, path, **kwargs)

        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url)
            with patch.dict(os.environ, env, clear=False):
                with patch.multiple(
                    "bridges.talk_task_tools", _api_request=recording_request
                ):
                    dispatch_tool("talk_list_agents", {})
            with self.make_client() as client:
                after = client.get(
                    f"/api/projects/prj_tools/agents/{quote('agent:worker', safe='')}/binding",
                    headers={"X-API-Key": "bobo-key"},
                ).json()

        self.assertEqual(
            calls,
            [
                ("GET", "/api/projects/prj_tools"),
                ("GET", "/api/projects/prj_tools/agents"),
                ("GET", "/api/members"),
                ("GET", "/api/members/me"),
            ],
        )
        self.assertFalse([call for call in calls if call[1].endswith("/binding")])
        # 绑定行没有被消费路径改动（只读）。
        self.assertEqual(after["binding_state"], "bound")
        self.assertEqual(after["binding"]["model_id"], MODEL_ID)

    def test_project_development_requirements_once_with_binding_present(self):
        with self.make_client() as client:
            client.patch(
                "/api/projects/prj_tools",
                headers={"X-API-Key": "bobo-key"},
                json={"development_requirements": "1.开发要求快照文本"},
            ).raise_for_status()
        with LiveTalkServer(main.app) as base_url:
            env = self._environment(base_url)
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool("talk_list_agents", {})
        payload = json.dumps(result, ensure_ascii=False)
        self.assertEqual(payload.count("development_requirements"), 1)
        self.assertEqual(result["development_requirements"], "1.开发要求快照文本")
        for agent in result["agents"]:
            self.assertNotIn("development_requirements", agent)


# ════════════════════════════════════════════════════════════════════
# 8：独立 stdio 子进程证据（目录 + talk_list_agents 新字段）
# ════════════════════════════════════════════════════════════════════


class RoleBindingToolConsumerStdioTests(RouteTestCase):
    """新进程/隔离 stdio：目录仍是九个工具，list_agents 返回只读绑定字段。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:requester", api_key="requester-key", display_name="请求者")
        self.add_member("agent:worker", api_key="worker-key", display_name="开发角色")
        self.project_root = self._tmpdir / "绑定消费项目"
        self.project_root.mkdir()
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "requester-key"},
                json={"project_id": "prj_terminal_binding", "display_name": "绑定消费"},
            ).raise_for_status()
            client.post(
                "/api/projects/prj_terminal_binding/sync",
                headers={"X-API-Key": "requester-key"},
                json={"agents": [{"member_id": "agent:worker", "business_role": "dev"}]},
            ).raise_for_status()
            client.post(
                "/api/runners",
                headers={"X-API-Key": "requester-key"},
                json={
                    "runner_id": RUNNER_ID,
                    "runtime": RUNNER_RUNTIME,
                    "display_name": RUNNER_DISPLAY_NAME,
                    "adapter_status": "adapted",
                },
            ).raise_for_status()
            client.put(
                "/api/projects/prj_terminal_binding/agents/"
                f"{quote('agent:worker', safe='')}/binding",
                headers={"X-API-Key": "requester-key"},
                json={
                    "binding": {
                        "runner_id": RUNNER_ID,
                        "model_source": MODEL_SOURCE,
                        "provider_id": PROVIDER_ID,
                        "connection_ref": CONNECTION_REF,
                        "model_id": MODEL_ID,
                        "model_alias": MODEL_ALIAS,
                    }
                },
            ).raise_for_status()

    def run_terminal(self, base_url: str, *, requests):
        env = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith("TALK_")
        }
        env.update(TALK_API_KEY="requester-key", PYTHONUTF8="1")
        return run_stdio_process(
            [sys.executable, str(TERMINAL_ENTRY), "--project-root", str(self.project_root)],
            input_text="".join(
                json.dumps(request, ensure_ascii=False) + "\n" for request in requests
            ),
            env=env,
            cwd=self.project_root,
            timeout=30,
        )

    def test_stdio_catalog_and_list_agents_binding_are_read_only(self):
        with LiveTalkServer(main.app) as base_url:
            scaffold_project(
                self.project_root,
                display_name="绑定消费",
                project_id="prj_terminal_binding",
                server_url=base_url,
            )
            process = self.run_terminal(
                base_url,
                requests=[
                    {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "talk_list_agents", "arguments": {}},
                    },
                ],
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        lines = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(lines), 2)

        tools = lines[0]["result"]["tools"]
        self.assertEqual(len(tools), 9)
        self.assertEqual(
            [tool["name"] for tool in tools], list(PROJECT_TOOL_NAMES)
        )
        # 目录里的描述已含只读绑定说明（源码/新子进程生效；不代表宿主已重连加载）。
        list_description = next(
            tool["description"] for tool in tools if tool["name"] == "talk_list_agents"
        )
        self.assertIn("binding_state", list_description)

        payload = json.loads(lines[1]["result"]["content"][0]["text"])
        self.assertEqual(payload["project_id"], "prj_terminal_binding")
        agent = payload["agents"][0]
        self.assertEqual(agent["binding_state"], "bound")
        self.assertEqual(set(agent["binding"]), set(ROLE_BINDING_PUBLIC_FIELDS))
        self.assertEqual(agent["binding"]["runner_id"], RUNNER_ID)
        self.assertEqual(agent["binding"]["model_id"], MODEL_ID)
        self.assertEqual(agent["binding"]["connection_ref"], CONNECTION_REF)
        self.assertNotIn("requester-key", process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
