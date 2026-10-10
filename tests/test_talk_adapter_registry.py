# -*- coding: utf-8 -*-
"""C2 受信应用（``scripts/talk_adapter_registry.py``）单元与行为测试。

测试真实性约定
--------------
- 挂**真实** ``server.routes.runners`` / ``server.routes.projects`` /
  ``server.routes.members`` router + FastAPI ``TestClient`` + 内存 SQLite；
  不导入 ``server.main``（避免生产初始化），不虚构正常 HTTP 形状；
- 只用 ``dependency_overrides`` 隔离 DB；身份走真实 ``get_current_member``
  （真实 human/agent 403 边界与真实 401）；
- 模拟客户端**仅**用于异常/超时/竞争/坏形状/坏 schema 等分支；
- 隔离 Tmp：所有夹具都是合成值，不读真实 Key、本机 native 环境或生产 DB。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path_entry in (str(PROJECT_ROOT), str(PROJECT_ROOT / "scripts")):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

import adapter_binding_facts as facts  # noqa: E402
import kimi_k28_executor as k28  # noqa: E402
import talk_adapter_registry as registry  # noqa: E402
from server.db import get_session  # noqa: E402
from server.models import (  # noqa: E402
    Member,
    Project,
    ProjectAgent,
    ProjectRoleBinding,
    RunnerRegistry,
)
from server.routes import members as members_route  # noqa: E402
from server.routes import projects as projects_route  # noqa: E402
from server.routes import runners as runners_route  # noqa: E402

# ---------------------------------------------------------------------------
# 合成夹具（全部为明显夹具值；任何真实输出都不应回流 canary/凭据）
# ---------------------------------------------------------------------------

HUMAN_ID = "human:bobo"
HUMAN_KEY = "human-canary-key-0001"
AGENT_ID = "agent:kimi-code-k28-preview"
AGENT_KEY = "agent-canary-key-0002"
OUTSIDER_KEY = "outsider-canary-key-0003"
PROJECT_ID = "talk"
HOST_SCOPE = "c2-host"
WORKSPACE_SCOPE = "c2-ws"

CANARY_ALIAS = "canary-alias-2f19"
CANARY_PROVIDER = "canary-provider-77aa"
CANARY_MODEL = "canary-model-31bc"
CANARY_CREDENTIAL = "sk-canary0123456789abcdef0123456789abcdef"
CANARY_SOURCE_KEY = "canary-nested-source-key"

K3_ALIAS = "kimi-code/k3"


def blob_of(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


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
                "capabilities": ["tool_use"],
            },
            K3_ALIAS: {
                "provider": k28.PROVIDER_ID,
                "model": "k3",
                "display_name": "K3",
                "capabilities": ["tool_use"],
            },
        }
    if providers is None:
        providers = {k28.PROVIDER_ID: {"type": "kimi", "api_key": CANARY_CREDENTIAL}}
    return {"default_model": default_model, "providers": providers, "models": models}


def resolve_ready(config: dict | None = None, *, layer: str = "argv", profile=None):
    profile = profile or facts.adapter_profile(facts.K28_ADAPTER)
    explicit = None
    provenance = None
    if layer == "argv":
        explicit = profile.explicit_argv_alias
    elif layer == "native_default":
        provenance = facts.native_provenance_for(
            make_config() if config is None else config,
            origin="native_profile_loaded",
            confirmed=True,
        )
    selection = facts.resolve_model_selection(
        config=make_config() if config is None else config,
        explicit_argv_alias=explicit,
        declared=None,
        hard=profile.hard,
        native_provenance=provenance,
        required_hard_fields=profile.required_hard_fields,
    )
    assert selection["status"] == "ready", selection
    return selection


def runner_id_for(host: str = HOST_SCOPE, workspace: str = WORKSPACE_SCOPE, *, runtime: str | None = None) -> str:
    return facts.runner_id_for(
        runtime or k28.RUNTIME, host_scope=host, workspace_scope=workspace
    )["runner_id"]


def expected_runner_fields(
    runner_identifier: str, *, runtime: str | None = None, **overrides: object
) -> dict:
    fields = {
        "runner_id": runner_identifier,
        "runtime": runtime or k28.RUNTIME,
        "display_name": "Kimi Code CLI",
        "adapter_status": "unverified",
        "adapter_note": None,
        "capabilities": ["tool_use"],
    }
    fields.update(overrides)
    return fields


def expected_binding_fields(runner_identifier: str, selection=None, **overrides: object) -> dict:
    selection = selection or resolve_ready()
    fields = {
        "runner_id": runner_identifier,
        "model_source": selection["fields"]["model_source"]["value"],
        "provider_id": selection["fields"]["provider_id"]["value"],
        "connection_ref": selection["fields"]["connection_ref"]["value"],
        "model_id": selection["fields"]["model_id"]["value"],
        "model_alias": selection["fields"]["model_alias"]["value"],
        "model_display_name": selection["fields"]["model_display_name"]["value"],
    }
    fields.update(overrides)
    return fields


def target_entry(
    *,
    project_id: str = PROJECT_ID,
    member_id: str = AGENT_ID,
    adapter: str = facts.K28_ADAPTER,
    host: str = HOST_SCOPE,
    workspace: str | None = WORKSPACE_SCOPE,
    host_shared_runner: bool | None = None,
    runner_overrides: object = None,
    binding_overrides: object = None,
    runner_identifier: str | None = None,
    selection=None,
    sources: object = None,
    context_overrides: object = None,
    drop: object = None,
    include_selection: bool = True,
    extra: object = None,
) -> dict:
    """构造一条**来源事实**目标（内存来源，不是 plan 结果）。"""
    profile = facts.adapter_profile(adapter)
    selection = selection if selection is not None else resolve_ready()
    identifier = runner_identifier or runner_id_for(host, workspace or "", runtime=profile.runtime)
    entry: dict = {
        "project_id": project_id,
        "member_id": member_id,
        "adapter": adapter,
        "runner_fields": expected_runner_fields(
            identifier, runtime=profile.runtime, **(runner_overrides or {})
        ),
        "binding_fields": expected_binding_fields(identifier, selection, **(binding_overrides or {})),
        "sources": sources
        if sources is not None
        else {"model_alias": {"source": "argv_explicit_selection"}},
        "source_context": {
            "host_scope": host,
            "workspace_scope": workspace,
            "origin": "native_profile_loaded",
        },
    }
    if host_shared_runner is not None:
        entry["source_context"]["host_shared_runner"] = host_shared_runner
    if include_selection:
        entry["source_context"]["selection"] = selection
    entry["source_context"].update(context_overrides or {})
    for key in drop or ():
        entry.pop(key, None)
    entry.update(extra or {})
    return entry


def make_spec(*targets: dict, server: str = "http://testserver") -> dict:
    return {"schema": registry.SPEC_SCHEMA, "server": server, "targets": list(targets)}


# ---------------------------------------------------------------------------
# 客户端代理：真实 TestClient + 计数 + 脚本化注入（仅异常/超时/竞争/坏形状分支）
# ---------------------------------------------------------------------------


def json_response(status: int, payload: object) -> httpx.Response:
    return httpx.Response(status_code=status, json=payload)


def raw_response(status: int, body: bytes, content_type: str = "application/json") -> httpx.Response:
    return httpx.Response(
        status_code=status, content=body, headers={"content-type": content_type}
    )


class Scripted:
    """一条脚本化响应规则：命中后按 ``times`` 消耗，可选 ``after`` 副作用。"""

    def __init__(
        self,
        method: str,
        path_fragment: str,
        *,
        times: int = 1,
        response: httpx.Response | None = None,
        exc: BaseException | None = None,
        after=None,
        enabled: bool = True,
        excludes: tuple[str, ...] = (),
    ) -> None:
        self.method = method.upper()
        self.path_fragment = path_fragment
        self.remaining = times
        self.response = response
        self.exc = exc
        self.after = after
        self.fired = 0
        self.enabled = enabled
        self.excludes = tuple(excludes)

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def matches(self, method: str, url: str) -> bool:
        return (
            self.enabled
            and self.remaining > 0
            and method == self.method
            and self.path_fragment in url
            and not any(fragment in url for fragment in self.excludes)
        )

    def fire(self):
        self.remaining -= 1
        self.fired += 1
        if self.after is not None:
            self.after()
        if self.exc is not None:
            raise self.exc
        return self.response


class CountingClient:
    """薄包装：只暴露 ``base_url`` 与 ``request``，统计写入次数并可注入脚本响应。"""

    def __init__(self, inner, script: list[Scripted] | None = None) -> None:
        self._inner = inner
        self.script = list(script or [])
        self.calls: list[tuple[str, str]] = []
        self.write_calls: list[tuple[str, str]] = []

    @property
    def base_url(self):
        return self._inner.base_url

    def request(self, method: str, url: str, **kwargs):
        method = method.upper()
        self.calls.append((method, url))
        if method in {"POST", "PATCH", "PUT", "DELETE"}:
            self.write_calls.append((method, url))
        for rule in self.script:
            if rule.matches(method, url):
                return rule.fire()
        return self._inner.request(method, url, **kwargs)

    def writes(self, method: str | None = None) -> int:
        if method is None:
            return len(self.write_calls)
        return sum(1 for item in self.write_calls if item[0] == method)

    def paths(self, method: str) -> list[str]:
        return [url for item_method, url in self.calls if item_method == method]


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------


class RegistryTestCase(unittest.TestCase):
    server = "http://testserver"

    def setUp(self) -> None:
        super().setUp()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        self.app = FastAPI()
        self.app.include_router(members_route.router)
        self.app.include_router(runners_route.router)
        self.app.include_router(projects_route.router)

        def override_session():
            with Session(self.engine) as session:
                yield session

        self.app.dependency_overrides[get_session] = override_session
        self.raw_client = TestClient(self.app)
        with self.session() as session:
            session.add(
                Member(id=HUMAN_ID, kind="human", display_name="bobo", api_key=HUMAN_KEY)
            )
            session.add(
                Member(id=AGENT_ID, kind="agent", display_name="K28", api_key=AGENT_KEY)
            )
            session.add(
                Member(
                    id="agent:other",
                    kind="agent",
                    display_name="other",
                    api_key=OUTSIDER_KEY,
                )
            )
            session.add(
                Project(
                    project_id=PROJECT_ID,
                    display_name="talk",
                    maintainer_member_id=HUMAN_ID,
                )
            )
            session.add(ProjectAgent(project_id=PROJECT_ID, member_id=AGENT_ID))
            session.commit()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        super().tearDown()

    def session(self) -> Session:
        return Session(self.engine)

    def client(self, script: list[Scripted] | None = None) -> CountingClient:
        return CountingClient(self.raw_client, script)

    # -- 夹具 ------------------------------------------------------------
    def add_runner(self, runner_identifier: str, **overrides) -> None:
        fields = expected_runner_fields(runner_identifier, **overrides)
        now = datetime.now(timezone.utc)
        with self.session() as session:
            session.add(
                RunnerRegistry(
                    **fields,
                    created_by=HUMAN_ID,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

    def add_binding(self, binding_fields: dict, *, member_id: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        with self.session() as session:
            session.add(
                ProjectRoleBinding(
                    project_id=PROJECT_ID,
                    member_id=member_id or AGENT_ID,
                    **{key: binding_fields[key] for key in registry.BINDING_READ_FIELDS},
                    updated_by=HUMAN_ID,
                    updated_at=now,
                )
            )
            session.commit()

    def runner_rows(self) -> list[RunnerRegistry]:
        with self.session() as session:
            return list(session.query(RunnerRegistry).all())

    def binding_row(self):
        with self.session() as session:
            return (
                session.query(ProjectRoleBinding)
                .filter(
                    ProjectRoleBinding.project_id == PROJECT_ID,
                    ProjectRoleBinding.member_id == AGENT_ID,
                )
                .one_or_none()
            )

    def runner_readback_cases(self, identifier: str) -> dict:
        """写后最新 GET /api/runners 的坏分支矩阵（HTTP 失败/坏数组/坏 schema/缺行/
        runtime 冲突/retired/四字段冲突）。"""

        def item(**overrides) -> dict:
            fields = expected_runner_fields(identifier, **overrides)
            fields.update(
                {
                    "created_by": HUMAN_ID,
                    "created_at": "2026-10-10T00:00:00Z",
                    "updated_at": "2026-10-10T00:00:00Z",
                }
            )
            return fields

        bad_schema = item()
        bad_schema.pop("adapter_note")
        return {
            "http_failure": json_response(503, {"detail": "x"}),
            "bad_array": json_response(200, {"runners": []}),
            "bad_schema": json_response(200, [bad_schema]),
            "missing_row": json_response(200, []),
            "runtime_conflict": json_response(200, [item(runtime="dsh")]),
            "retired": json_response(200, [item(adapter_status="retired")]),
            "field_conflict": json_response(200, [item(display_name="Other display")]),
        }

    def assert_write_then_readback_fault_blocks_put(self, plan, spec, script, method: str):
        result, client = self.apply(plan, spec, client=self.client(script))
        entry = result["entries"][0]
        self.assertIn(entry["runner"]["outcome"], ("blocked", "unknown"))
        self.assertEqual(client.writes(method), 1)
        self.assertEqual(len(client.paths(method)), 1)
        self.assertEqual(client.writes("PUT"), 0)
        return entry

    def plan(self, spec: dict | None = None, *, client=None, credential: str = HUMAN_KEY, **kwargs):
        spec = spec if spec is not None else make_spec(target_entry())
        client = client if client is not None else self.client()
        return registry.plan_spec(
            spec, client=client, credential=credential, **kwargs
        ), client

    def apply(self, plan: dict, spec: dict | None = None, *, client=None, credential: str = HUMAN_KEY, **kwargs):
        spec = spec if spec is not None else make_spec(target_entry())
        client = client if client is not None else self.client()
        return (
            registry.apply_plan(
                plan=plan, spec=spec, client=client, credential=credential, **kwargs
            ),
            client,
        )

    def ready_plan(self, *, spec: dict | None = None, target: dict | None = None, accept_change: bool = False):
        spec = spec if spec is not None else make_spec(target or target_entry())
        plan, _ = self.plan(spec, accept_change=accept_change)
        self.assertEqual(plan["plan_status"], "complete", plan)
        return plan, spec


class FixedBaseClient(CountingClient):
    """服务地址与真实客户端不一致的探针（只用于服务地址重核失败分支）。"""

    def __init__(self, inner, base_url: str, script=None) -> None:
        super().__init__(inner, script)
        self._base_url = base_url

    @property
    def base_url(self):
        return self._base_url


# ---------------------------------------------------------------------------
# plan：只读、分类与阻断
# ---------------------------------------------------------------------------


class PlanReadOnlyTests(RegistryTestCase):
    def test_plan_issues_only_get_and_never_writes(self):
        plan, client = self.plan()
        self.assertEqual(plan["plan_status"], "complete")
        self.assertTrue(client.calls)
        self.assertEqual(client.writes(), 0)
        self.assertEqual([method for method, _ in client.calls], ["GET"] * len(client.calls))

    def test_plan_classifies_new_runner_and_unconfigured_binding_as_create(self):
        plan, _ = self.plan()
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "ready")
        self.assertEqual(entry["runner"]["action"], "create")
        self.assertEqual(entry["binding"]["action"], "create")
        self.assertEqual(entry["binding"]["binding_state"], "unconfigured")
        self.assertEqual(entry["sources"], {"model_alias": {"source": "argv_explicit_selection"}})
        self.assertIn("source_fingerprint", entry)
        self.assertEqual(plan["summary"]["runner_create"], 1)
        self.assertEqual(plan["summary"]["binding_create"], 1)

    def test_plan_is_no_op_when_runner_and_binding_already_match(self):
        identifier = runner_id_for()
        self.add_runner(identifier)
        self.add_binding(expected_binding_fields(identifier))
        plan, client = self.plan()
        entry = plan["entries"][0]
        self.assertEqual(entry["runner"]["action"], "no_op")
        self.assertEqual(entry["binding"]["action"], "no_op")
        self.assertEqual(entry["binding"]["binding_state"], "bound")
        self.assertFalse(entry["requires_accept"])
        self.assertEqual(plan["plan_status"], "complete")
        self.assertEqual(client.writes(), 0)

    def test_plan_reports_conflict_by_default_and_update_after_accept_change(self):
        identifier = runner_id_for()
        self.add_runner(identifier, display_name="Other display")
        self.add_binding(expected_binding_fields(identifier, model_id="other-model"))
        plan, _ = self.plan()
        entry = plan["entries"][0]
        self.assertEqual(entry["runner"]["action"], "conflict")
        self.assertEqual(entry["runner"]["conflict_fields"], ["display_name"])
        self.assertEqual(entry["binding"]["action"], "conflict")
        self.assertEqual(entry["binding"]["conflict_fields"], ["model_id"])
        self.assertTrue(entry["requires_accept"])
        self.assertEqual(plan["plan_status"], "partial")

        accepted, _ = self.plan(accept_change=True)
        accepted_entry = accepted["entries"][0]
        self.assertEqual(accepted_entry["runner"]["action"], "update")
        self.assertEqual(accepted_entry["binding"]["action"], "update")
        self.assertEqual(accepted["plan_status"], "complete")

    def test_partial_ready_is_not_summarised_as_complete(self):
        ready = target_entry()
        blocked = target_entry(
            project_id="missing-project",
        )
        plan, _ = self.plan(make_spec(ready, blocked))
        self.assertEqual(plan["entries"][0]["status"], "ready")
        self.assertEqual(plan["entries"][1]["status"], "blocked")
        self.assertEqual(plan["plan_status"], "partial")
        self.assertEqual(plan["summary"]["ready"], 1)
        self.assertEqual(plan["summary"]["blocked"], 1)

    def test_blocked_entry_carries_no_runner_binding_or_fingerprint(self):
        plan, _ = self.plan(make_spec(target_entry(project_id="missing-project")))
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        for key in ("runner", "binding", "expected", "source_fingerprint"):
            self.assertNotIn(key, entry)
        self.assertEqual(entry["blocked"][0]["code"], "E_STATE_UNREADABLE")

    def test_plan_ignores_prebaked_ready_and_fingerprint_from_spec(self):
        fake = target_entry(
            runner_identifier="runner:canary-00000000000000000000000000000000",
            extra={
                "status": "ready",
                "source_fingerprint": {"fingerprint": "0" * 32},
                "runner": {"action": "no_op"},
                "binding": {"action": "no_op"},
            },
        )
        plan, client = self.plan(make_spec(fake))
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        blob = blob_of(plan)
        self.assertNotIn("0" * 32, blob)
        self.assertEqual(client.writes(), 0)

    def test_plan_blocks_on_runner_runtime_conflict(self):
        identifier = runner_id_for()
        self.add_runner(identifier, runtime="dsh")
        plan, _ = self.plan()
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_RUNTIME_CONFLICT")
        self.assertEqual(entry["blocked"][0]["conflict_fields"], ["runtime"])

    def test_plan_blocks_on_retired_runner(self):
        identifier = runner_id_for()
        self.add_runner(identifier, adapter_status="retired")
        plan, _ = self.plan()
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_RETIRED")

    def _target_state_block(self, mutate):
        mutate()
        plan, client = self.plan()
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_TARGET_NOT_ELIGIBLE")
        self.assertEqual(client.writes(), 0)

    def test_plan_blocks_member_missing(self):
        def mutate():
            with self.session() as session:
                session.delete(session.get(Member, AGENT_ID))
                session.commit()

        self._target_state_block(mutate)

    def test_plan_blocks_member_disabled(self):
        def mutate():
            with self.session() as session:
                member = session.get(Member, AGENT_ID)
                member.disabled_at = datetime.now(timezone.utc)
                session.add(member)
                session.commit()

        self._target_state_block(mutate)

    def test_plan_blocks_not_in_roster(self):
        def mutate():
            with self.session() as session:
                row = session.get(ProjectAgent, (PROJECT_ID, AGENT_ID))
                session.delete(row)
                session.commit()

        self._target_state_block(mutate)

    def test_plan_blocks_not_agent(self):
        def mutate():
            with self.session() as session:
                member = session.get(Member, AGENT_ID)
                member.kind = "human"
                session.add(member)
                session.commit()

        self._target_state_block(mutate)

    def test_plan_blocks_on_bad_runner_array_shape(self):
        script = [Scripted("GET", "/api/runners", response=json_response(200, {"runners": []}))]
        plan, client = self.plan(client=self.client(script))
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_READ_FAILED")
        self.assertEqual(client.writes(), 0)

    def test_plan_blocks_on_incomplete_runner_schema(self):
        payload = [
            {
                "runner_id": runner_id_for(),
                "runtime": k28.RUNTIME,
                "display_name": "Kimi Code CLI",
                "adapter_status": "unverified",
                "capabilities": ["tool_use"],
                "created_by": HUMAN_ID,
                "created_at": "2026-10-10T00:00:00Z",
                "updated_at": "2026-10-10T00:00:00Z",
            }
        ]
        script = [Scripted("GET", "/api/runners", response=json_response(200, payload))]
        plan, _ = self.plan(client=self.client(script))
        self.assertEqual(plan["entries"][0]["status"], "blocked")
        self.assertEqual(plan["entries"][0]["blocked"][0]["code"], "E_RUNNER_READ_FAILED")

    def test_plan_blocks_on_runner_http_failure(self):
        script = [Scripted("GET", "/api/runners", response=json_response(503, {"detail": "x"}))]
        plan, _ = self.plan(client=self.client(script))
        self.assertEqual(plan["entries"][0]["status"], "blocked")
        self.assertEqual(plan["entries"][0]["blocked"][0]["code"], "E_RUNNER_READ_FAILED")

    def test_plan_blocks_when_binding_reads_other_project_or_member(self):
        script = [
            Scripted(
                "GET",
                "/binding",
                response=json_response(
                    200,
                    {
                        "project_id": "other-project",
                        "member_id": AGENT_ID,
                        "binding": None,
                        "binding_state": "unconfigured",
                    },
                ),
            )
        ]
        plan, _ = self.plan(client=self.client(script))
        self.assertEqual(plan["entries"][0]["status"], "blocked")
        self.assertEqual(plan["entries"][0]["blocked"][0]["code"], "E_STATE_DRIFT")

    def test_plan_blocks_when_agents_payload_is_not_an_array(self):
        script = [Scripted("GET", "/agents", response=json_response(200, {"agents": []}))]
        plan, _ = self.plan(client=self.client(script))
        self.assertEqual(plan["entries"][0]["status"], "blocked")
        self.assertEqual(plan["entries"][0]["blocked"][0]["code"], "E_STATE_UNREADABLE")

    def test_plan_blocks_when_project_missing(self):
        plan, _ = self.plan(make_spec(target_entry(project_id="nope")))
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["reason_code"], "http_404")

    def test_plan_status_blocked_when_every_entry_blocked(self):
        plan, _ = self.plan(make_spec(target_entry(project_id="nope")))
        self.assertEqual(plan["plan_status"], "blocked")
        self.assertEqual(plan["summary"]["ready"], 0)


# ---------------------------------------------------------------------------
# 目标 / scope / schema 校验
# ---------------------------------------------------------------------------


class PlanValidationTests(RegistryTestCase):
    def _blocked_codes(self, target: dict) -> list[str]:
        plan, _ = self.plan(make_spec(target))
        return [reason["code"] for reason in plan["entries"][0].get("blocked", [])]

    def test_unknown_adapter_is_blocked(self):
        target = {
            "project_id": PROJECT_ID,
            "member_id": "agent:unknown",
            "adapter": "agent:unknown",
            "runner_fields": None,
            "binding_fields": None,
            "sources": {},
            "source_context": {},
        }
        self.assertIn("E_UNKNOWN_ADAPTER", self._blocked_codes(target))

    def test_member_profile_mismatch_is_blocked(self):
        target = target_entry()
        target["member_id"] = "agent:other"
        self.assertIn("E_TARGET_MISMATCH", self._blocked_codes(target))

    def test_credential_like_target_label_is_rejected(self):
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.iter_targets(
                make_spec(
                    {
                        "project_id": CANARY_CREDENTIAL,
                        "member_id": AGENT_ID,
                        "adapter": facts.K28_ADAPTER,
                    }
                )
            )
        self.assertEqual(ctx.exception.code, "E_TARGET_INVALID")
        self.assertNotIn(CANARY_CREDENTIAL, str(ctx.exception))

    def test_blank_target_identifier_is_rejected(self):
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.iter_targets(
                make_spec({"project_id": "  ", "member_id": AGENT_ID, "adapter": facts.K28_ADAPTER})
            )
        self.assertEqual(ctx.exception.code, "E_TARGET_INVALID")

    def test_empty_target_list_is_rejected(self):
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.iter_targets({"server": self.server, "targets": []})
        self.assertEqual(ctx.exception.code, "E_TARGETS_EMPTY")

    def test_missing_workspace_scope_without_host_shared_is_blocked(self):
        target = target_entry(workspace=None, runner_identifier=runner_id_for())
        codes = self._blocked_codes(target)
        self.assertIn("E_SCOPE_MISSING", codes)

    def test_invalid_scope_token_is_blocked(self):
        target = target_entry(host="host/with/slash", runner_identifier=runner_id_for())
        codes = self._blocked_codes(target)
        self.assertIn("E_SCOPE_INVALID", codes)

    def test_non_boolean_scope_flag_is_blocked(self):
        target = target_entry(context_overrides={"host_shared_runner": "yes"})
        self.assertIn("E_FLAG_NOT_BOOL", self._blocked_codes(target))

    def test_scope_drift_from_explicit_context_is_blocked(self):
        target = target_entry(runner_identifier=runner_id_for(host="other-host"))
        self.assertIn("E_SCOPE_MISMATCH", self._blocked_codes(target))

    def test_runtime_mismatch_is_blocked(self):
        identifier = runner_id_for()
        target = target_entry(runner_identifier=identifier)
        target["runner_fields"]["runtime"] = "dsh"
        self.assertIn("E_RUNTIME_MISMATCH", self._blocked_codes(target))

    def test_missing_selection_result_is_blocked(self):
        target = target_entry(include_selection=False)
        self.assertIn("E_SELECTION_NOT_READY", self._blocked_codes(target))

    def test_source_insufficient_profile_is_blocked(self):
        target = {
            "project_id": PROJECT_ID,
            "member_id": "agent:deepseek",
            "adapter": "agent:deepseek",
            "runner_fields": None,
            "binding_fields": None,
            "sources": {},
            "source_context": {},
        }
        plan, _ = self.plan(make_spec(target))
        self.assertEqual(plan["entries"][0]["status"], "blocked")
        self.assertNotIn("expected", plan["entries"][0])

    def test_runner_schema_failure_is_blocked_without_values(self):
        target = target_entry(runner_overrides={"display_name": ""})
        codes = self._blocked_codes(target)
        self.assertIn("E_RUNNER_PAYLOAD_INVALID", codes)

    def test_credential_like_binding_field_is_blocked_and_not_echoed(self):
        target = target_entry(binding_overrides={"provider_id": CANARY_CREDENTIAL})
        plan, _ = self.plan(make_spec(target))
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertIn("E_BINDING_PAYLOAD_INVALID", [r["code"] for r in entry["blocked"]])
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(plan))

    def test_runner_binding_id_mismatch_is_blocked(self):
        target = target_entry()
        target["binding_fields"]["runner_id"] = "runner:other-0000000000000000000000000000000000"
        self.assertIn("E_RUNNER_BINDING_ID_MISMATCH", self._blocked_codes(target))

    def test_accept_change_flag_must_be_boolean(self):
        with self.assertRaises(registry.AdapterRegistryError):
            registry.build_plan(
                server=self.server,
                targets=registry.iter_targets(make_spec(target_entry())),
                source_provider=registry.spec_source_provider(make_spec(target_entry())),
                client=self.client(),
                credential=HUMAN_KEY,
                accept_change="yes",
            )

    def test_plan_server_mismatch_with_client_is_rejected(self):
        spec = make_spec(target_entry(), server="http://other-host")
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.plan_spec(spec, client=self.client(), credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_SERVER_MISMATCH")

    def test_server_address_must_be_root_http_url(self):
        for bad in ("ftp://x", "http://x/path", "http://u:p@x", "http://x?q=1", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(registry.AdapterRegistryError):
                    registry.normalize_server(bad)


# ---------------------------------------------------------------------------
# 隐私：合成 canary 递归检查
# ---------------------------------------------------------------------------


class PlanPrivacyTests(RegistryTestCase):
    def test_recursive_canary_check_on_ready_plan(self):
        target = target_entry(
            runner_overrides={"display_name": "Kimi Code CLI", "adapter_note": None},
            sources={
                "model_alias": {"source": "argv_explicit_selection", "value": CANARY_ALIAS},
                CANARY_SOURCE_KEY: {"source": "native_parse", "value": CANARY_CREDENTIAL},
            },
        )
        plan, client = self.plan(make_spec(target))
        self.assertEqual(plan["plan_status"], "complete")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(plan))
        self.assertNotIn(CANARY_SOURCE_KEY, blob_of(plan))
        self.assertEqual(client.writes(), 0)

    def test_canary_in_rejected_capabilities_is_not_echoed(self):
        target = target_entry(runner_overrides={"capabilities": ["tool_use", CANARY_CREDENTIAL]})
        plan, _ = self.plan(make_spec(target))
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(plan))

    def test_source_errors_do_not_echo_raw_provider_exception(self):
        def provider(_target):
            raise RuntimeError(f"boom {CANARY_CREDENTIAL}")

        spec = make_spec(target_entry())
        plan = registry.build_plan(
            server=self.server,
            targets=registry.iter_targets(spec),
            source_provider=provider,
            client=self.client(),
            credential=HUMAN_KEY,
        )
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(plan))
        self.assertNotIn("boom", blob_of(plan))

    def test_http_error_bodies_and_tracebacks_never_reach_output(self):
        script = [
            Scripted(
                "GET",
                "/api/runners",
                response=raw_response(500, f"{{'traceback': '{CANARY_CREDENTIAL}'}}".encode()),
            )
        ]
        plan, _ = self.plan(client=self.client(script))
        self.assertEqual(plan["entries"][0]["status"], "blocked")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(plan))
        self.assertNotIn("traceback", blob_of(plan))


class CredentialLoadingTests(unittest.TestCase):
    def test_env_channel_accepts_synthetic_value(self):
        value = registry.load_credential(key_env="C2_KEY", environ={"C2_KEY": "synthetic-key-1"})
        self.assertEqual(value, "synthetic-key-1")

    def test_no_source_is_rejected_without_auto_discovery(self):
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.load_credential(environ={registry.DEFAULT_KEY_ENV: "synthetic"})
        self.assertEqual(ctx.exception.code, "E_CREDENTIAL_SOURCE_MISSING")

    def test_both_sources_conflict(self):
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.load_credential(key_env="C2_KEY", key_file="x", environ={"C2_KEY": "v"})
        self.assertEqual(ctx.exception.code, "E_CREDENTIAL_SOURCE_CONFLICT")

    def test_key_file_outside_repo_is_accepted_and_value_not_echoed(self):
        with tempfile.TemporaryDirectory(prefix="c2-key-") as workdir:
            path = Path(workdir) / "key.txt"
            path.write_text(CANARY_CREDENTIAL + "\n", encoding="utf-8")
            value = registry.load_credential(key_file=str(path))
            self.assertEqual(value, CANARY_CREDENTIAL)

    def test_key_file_inside_repo_is_rejected(self):
        inside = PROJECT_ROOT / ".tmp" / "adapter-registry-c2" / "fake-key.txt"
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.load_credential(key_file=str(inside))
        self.assertEqual(ctx.exception.code, "E_KEY_FILE_IN_REPO")

    def test_missing_key_file_is_rejected_without_echoing_path(self):
        with tempfile.TemporaryDirectory(prefix="c2-key-") as workdir:
            missing = str(Path(workdir) / CANARY_ALIAS)
            with self.assertRaises(registry.AdapterRegistryError) as ctx:
                registry.load_credential(key_file=missing)
            self.assertEqual(ctx.exception.code, "E_KEY_FILE_UNREADABLE")
            self.assertNotIn(CANARY_ALIAS, str(ctx.exception))

    def test_multiline_credential_is_rejected(self):
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.load_credential(key_env="C2_KEY", environ={"C2_KEY": "a b"})
        self.assertEqual(ctx.exception.code, "E_CREDENTIAL_INVALID")


# ---------------------------------------------------------------------------
# apply：身份边界（human 必需，失败一律零写）
# ---------------------------------------------------------------------------


class ApplyIdentityTests(RegistryTestCase):
    def test_human_credential_applies_runner_and_binding(self):
        plan, spec = self.ready_plan()
        result, client = self.apply(plan, spec)
        self.assertTrue(result["identity"]["verified"])
        self.assertEqual(result["result_status"], "complete")
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "created")
        self.assertEqual(entry["binding"]["outcome"], "bound")
        self.assertEqual(entry["writes"], {"post_runner": 1, "patch_runner": 0, "put_binding": 1})
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 1)
        self.assertEqual(len(self.runner_rows()), 1)

    def test_agent_credential_is_blocked_with_zero_writes(self):
        plan, spec = self.ready_plan()
        result, client = self.apply(plan, spec, credential=AGENT_KEY)
        self.assertEqual(result["result_status"], "blocked")
        self.assertFalse(result["identity"]["verified"])
        self.assertEqual(result["entries"][0]["blocked"][0]["code"], "E_IDENTITY_UNVERIFIED")
        self.assertEqual(client.writes(), 0)
        self.assertEqual(self.runner_rows(), [])
        self.assertIsNone(self.binding_row())

    def test_invalid_credential_is_blocked_with_zero_writes(self):
        plan, spec = self.ready_plan()
        result, client = self.apply(plan, spec, credential="not-a-real-key")
        self.assertEqual(result["result_status"], "blocked")
        self.assertEqual(client.writes(), 0)
        self.assertEqual(
            result["entries"][0]["blocked"][0]["reason_code"], "http_401"
        )

    def test_identity_timeout_is_blocked_with_zero_writes(self):
        plan, spec = self.ready_plan()
        script = [Scripted("GET", "/api/members/me", exc=httpx.ReadTimeout("identity"))]
        result, client = self.apply(plan, spec, client=self.client(script))
        self.assertEqual(result["result_status"], "blocked")
        self.assertEqual(result["entries"][0]["blocked"][0]["reason_code"], "timeout")
        self.assertEqual(client.writes(), 0)

    def test_identity_block_never_leaks_credential(self):
        plan, spec = self.ready_plan()
        result, _ = self.apply(plan, spec, credential=AGENT_KEY)
        self.assertNotIn(AGENT_KEY, blob_of(result))


# ---------------------------------------------------------------------------
# apply：参数一致 / 来源重核 / block 计划条目（全部零写）
# ---------------------------------------------------------------------------


class ApplyParamAndDriftTests(RegistryTestCase):
    def test_server_argument_mismatch_raises_with_zero_writes(self):
        plan, spec = self.ready_plan()
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(
                plan=plan, spec=spec, client=client, credential=HUMAN_KEY,
                server="http://other-host",
            )
        self.assertEqual(ctx.exception.code, "E_SERVER_MISMATCH")
        self.assertEqual(client.writes(), 0)

    def test_client_base_url_mismatch_raises_with_zero_writes(self):
        plan, spec = self.ready_plan()
        client = FixedBaseClient(self.raw_client, "http://other-host")
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(plan=plan, spec=spec, client=client, credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_SERVER_MISMATCH")
        self.assertEqual(client.writes(), 0)

    def test_accept_change_must_match_plan(self):
        plan, spec = self.ready_plan()
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(
                plan=plan, spec=spec, client=client, credential=HUMAN_KEY,
                accept_change=True,
            )
        self.assertEqual(ctx.exception.code, "E_PLAN_PARAM_MISMATCH")
        self.assertEqual(client.writes(), 0)

    def test_spec_targets_must_match_plan(self):
        plan, _spec = self.ready_plan()
        other = make_spec(target_entry(member_id="agent:other"))
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(plan=plan, spec=other, client=client, credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_PLAN_PARAM_MISMATCH")
        self.assertEqual(client.writes(), 0)

    def test_source_drift_blocks_entry_with_zero_writes(self):
        plan, _spec = self.ready_plan()
        drifted = make_spec(target_entry(workspace="drifted-ws"))
        result, client = self.apply(plan, drifted)
        self.assertEqual(result["entries"][0]["status"], "blocked")
        self.assertEqual(result["entries"][0]["blocked"][0]["code"], "E_SOURCE_DRIFT")
        self.assertEqual(client.writes(), 0)

    def test_stale_plan_payload_is_detected(self):
        plan, spec = self.ready_plan()
        plan["entries"][0]["expected"]["runner"]["display_name"] = "Edited by hand"
        result, client = self.apply(plan, spec)
        self.assertEqual(result["entries"][0]["blocked"][0]["code"], "E_PLAN_STALE")
        self.assertEqual(client.writes(), 0)

    def test_blocked_plan_entry_is_never_applied(self):
        spec = make_spec(target_entry(project_id="missing-project"))
        plan, _ = self.plan(spec)
        self.assertEqual(plan["plan_status"], "blocked")
        result, client = self.apply(plan, spec)
        self.assertEqual(result["entries"][0]["status"], "blocked")
        self.assertEqual(result["entries"][0]["blocked"][-1]["code"], "E_PLAN_ENTRY_BLOCKED")
        self.assertEqual(client.writes(), 0)

    def test_invalid_plan_schema_is_rejected(self):
        plan, spec = self.ready_plan()
        plan["schema"] = "adapter-registry-plan-v0"
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(plan=plan, spec=spec, client=self.client(), credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_PLAN_INVALID")

    def test_hand_edited_plan_payload_is_rejected_before_any_write(self):
        plan, spec = self.ready_plan()
        plan["entries"][0]["expected"]["runner"]["display_name"] = ""
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(plan=plan, spec=spec, client=client, credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_PLAN_INVALID")
        self.assertEqual(ctx.exception.field, "expected.runner")
        self.assertEqual(client.writes(), 0)

    def test_empty_credential_is_rejected_before_any_request(self):
        plan, spec = self.ready_plan()
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(plan=plan, spec=spec, client=client, credential="   ")
        self.assertEqual(ctx.exception.code, "E_CREDENTIAL_INVALID")
        self.assertEqual(client.calls, [])


# ---------------------------------------------------------------------------
# apply：运行器 POST 分支（写后必须最新 GET 完整重判；失败断言 PUT=0）
# ---------------------------------------------------------------------------


class ApplyRunnerCreateTests(RegistryTestCase):
    def runner_item(self, identifier: str, **overrides) -> dict:
        fields = expected_runner_fields(identifier, **overrides)
        fields.update(
            {
                "created_by": HUMAN_ID,
                "created_at": "2026-10-10T00:00:00Z",
                "updated_at": "2026-10-10T00:00:00Z",
            }
        )
        return fields

    def _armed_confirm(self, response: httpx.Response | None = None, exc=None) -> tuple[Scripted, Scripted]:
        fault = Scripted("GET", "/api/runners", response=response, exc=exc, enabled=False)
        post = Scripted("POST", "/api/runners", after=fault.enable)
        return post, fault

    def test_post_201_confirmed_then_binding_put(self):
        plan, spec = self.ready_plan()
        result, client = self.apply(plan, spec)
        self.assertEqual(result["entries"][0]["runner"]["http_status"], 201)
        self.assertEqual(result["entries"][0]["runner"]["outcome"], "created")
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 1)

    def test_post_confirmation_http_failure_blocks_binding_put(self):
        plan, spec = self.ready_plan()
        post, fault = self._armed_confirm(json_response(503, {"detail": "x"}))
        result, client = self.apply(plan, spec, client=self.client([post, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "unknown")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_READ_FAILED")
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 0)
        self.assertIsNone(self.binding_row())

    def test_post_confirmation_bad_array_blocks_binding_put(self):
        plan, spec = self.ready_plan()
        post, fault = self._armed_confirm(json_response(200, {"runners": []}))
        result, client = self.apply(plan, spec, client=self.client([post, fault]))
        self.assertEqual(result["entries"][0]["runner"]["outcome"], "unknown")
        self.assertEqual(client.writes("PUT"), 0)

    def test_post_confirmation_bad_schema_blocks_binding_put(self):
        identifier = runner_id_for()
        item = self.runner_item(identifier)
        item.pop("adapter_note")
        plan, spec = self.ready_plan()
        post, fault = self._armed_confirm(json_response(200, [item]))
        result, client = self.apply(plan, spec, client=self.client([post, fault]))
        self.assertEqual(result["entries"][0]["runner"]["outcome"], "unknown")
        self.assertEqual(client.writes("PUT"), 0)

    def test_post_confirmation_missing_row_blocks_binding_put(self):
        plan, spec = self.ready_plan()
        post, fault = self._armed_confirm(json_response(200, []))
        result, client = self.apply(plan, spec, client=self.client([post, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "unknown")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_NOT_CONFIRMED")
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 0)

    def test_post_confirmation_runtime_conflict_blocks_binding_put(self):
        identifier = runner_id_for()
        plan, spec = self.ready_plan()
        post, fault = self._armed_confirm(
            json_response(200, [self.runner_item(identifier, runtime="dsh")])
        )
        result, client = self.apply(plan, spec, client=self.client([post, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "blocked")
        self.assertEqual(entry["runner"]["conflict_fields"], ["runtime"])
        self.assertEqual(client.writes("PUT"), 0)

    def test_post_confirmation_retired_blocks_binding_put(self):
        identifier = runner_id_for()
        plan, spec = self.ready_plan()
        post, fault = self._armed_confirm(
            json_response(200, [self.runner_item(identifier, adapter_status="retired")])
        )
        result, client = self.apply(plan, spec, client=self.client([post, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_RETIRED")
        self.assertEqual(client.writes("PUT"), 0)

    def test_post_confirmation_each_mutable_field_conflict_blocks_binding_put(self):
        identifier = runner_id_for()
        for field, value in (
            ("display_name", "Another display"),
            ("adapter_status", "adapted"),
            ("adapter_note", "changed note"),
            ("capabilities", ["tool_use", "thinking"]),
        ):
            with self.subTest(field=field):
                self.setUp()
                try:
                    plan, spec = self.ready_plan()
                    post, fault = self._armed_confirm(
                        json_response(200, [self.runner_item(identifier, **{field: value})])
                    )
                    result, client = self.apply(plan, spec, client=self.client([post, fault]))
                    entry = result["entries"][0]
                    self.assertEqual(entry["runner"]["outcome"], "blocked")
                    self.assertEqual(entry["runner"]["conflict_fields"], [field])
                    self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_CONFLICT")
                    self.assertEqual(client.writes("POST"), 1)
                    self.assertEqual(client.writes("PUT"), 0)
                finally:
                    self.tearDown()

    def test_post_409_with_matching_state_is_reclassified_and_proceeds(self):
        identifier = runner_id_for()
        plan, spec = self.ready_plan()
        post = Scripted(
            "POST",
            "/api/runners",
            response=json_response(409, {"detail": "exists"}),
            after=lambda: self.add_runner(identifier),
        )
        result, client = self.apply(plan, spec, client=self.client([post]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["write_outcome"], "http_error:409")
        self.assertEqual(entry["runner"]["outcome"], "created")
        self.assertEqual(entry["binding"]["outcome"], "bound")
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 1)

    def test_post_409_with_field_conflict_and_matching_row_proceeds(self):
        identifier = runner_id_for()
        plan, spec = self.ready_plan()
        # 竞争：POST 前该 runner 已被另一写者登记为完全不同内容 → 409 + 读回差异 → PUT=0
        post = Scripted(
            "POST",
            "/api/runners",
            response=json_response(409, {"detail": "exists"}),
            after=lambda: self.add_runner(identifier, display_name="Concurrent writer"),
        )
        result, client = self.apply(plan, spec, client=self.client([post]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_CONFLICT")
        self.assertEqual(entry["runner"]["conflict_fields"], ["display_name"])
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 0)

    def test_post_409_with_missing_row_blocks_binding_put(self):
        plan, spec = self.ready_plan()
        post = Scripted("POST", "/api/runners", response=json_response(409, {"detail": "exists"}))
        result, client = self.apply(plan, spec, client=self.client([post]))
        self.assertEqual(result["entries"][0]["blocked"][0]["code"], "E_RUNNER_NOT_CONFIRMED")
        self.assertEqual(client.writes("PUT"), 0)

    def test_post_409_readback_matrix_blocks_put(self):
        for label, response in self.runner_readback_cases(runner_id_for()).items():
            with self.subTest(case=label):
                self.setUp()
                try:
                    plan, spec = self.ready_plan()
                    fault = Scripted("GET", "/api/runners", response=response, enabled=False)
                    post = Scripted(
                        "POST",
                        "/api/runners",
                        response=json_response(409, {"detail": "exists"}),
                        after=fault.enable,
                    )
                    self.assert_write_then_readback_fault_blocks_put(
                        plan, spec, [post, fault], "POST"
                    )
                finally:
                    self.tearDown()

    def test_post_timeout_readback_matrix_blocks_put(self):
        for label, response in self.runner_readback_cases(runner_id_for()).items():
            with self.subTest(case=label):
                self.setUp()
                try:
                    plan, spec = self.ready_plan()
                    fault = Scripted("GET", "/api/runners", response=response, enabled=False)
                    post = Scripted(
                        "POST",
                        "/api/runners",
                        exc=httpx.ReadTimeout("post"),
                        after=fault.enable,
                    )
                    self.assert_write_then_readback_fault_blocks_put(
                        plan, spec, [post, fault], "POST"
                    )
                finally:
                    self.tearDown()

    def test_post_timeout_with_confirmed_readback_proceeds_without_retry(self):
        identifier = runner_id_for()
        plan, spec = self.ready_plan()
        post = Scripted(
            "POST",
            "/api/runners",
            exc=httpx.ReadTimeout("post"),
            after=lambda: self.add_runner(identifier),
        )
        result, client = self.apply(plan, spec, client=self.client([post]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["write_outcome"], "timeout")
        self.assertEqual(entry["runner"]["outcome"], "created")
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 1)

    def test_post_timeout_without_confirmation_blocks_put_without_retry(self):
        plan, spec = self.ready_plan()
        post = Scripted("POST", "/api/runners", exc=httpx.ReadTimeout("post"))
        result, client = self.apply(plan, spec, client=self.client([post]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "unknown")
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 0)
        self.assertEqual(len(client.paths("POST")), 1)


# ---------------------------------------------------------------------------
# apply：运行器 PATCH 分支（仅显式 accept-change）
# ---------------------------------------------------------------------------


class ApplyRunnerPatchTests(RegistryTestCase):
    def _conflict_plan(self):
        identifier = runner_id_for()
        self.add_runner(identifier, display_name="Other display")
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["plan_status"], "complete", plan)
        self.assertEqual(plan["entries"][0]["runner"]["action"], "update")
        return plan, spec, identifier

    def runner_item(self, identifier: str, **overrides) -> dict:
        fields = expected_runner_fields(identifier, **overrides)
        fields.update(
            {
                "created_by": HUMAN_ID,
                "created_at": "2026-10-10T00:00:00Z",
                "updated_at": "2026-10-10T00:00:00Z",
            }
        )
        return fields

    def test_patch_200_then_binding_put_applies(self):
        plan, spec, identifier = self._conflict_plan()
        result, client = self.apply(plan, spec, accept_change=True)
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "patched")
        self.assertEqual(entry["binding"]["outcome"], "bound")
        self.assertEqual(client.writes("PATCH"), 1)
        self.assertEqual(client.writes("PUT"), 1)
        self.assertEqual(self.runner_rows()[0].display_name, "Kimi Code CLI")

    def test_patch_without_accept_never_writes(self):
        identifier = runner_id_for()
        self.add_runner(identifier, display_name="Other display")
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        self.assertEqual(plan["entries"][0]["runner"]["action"], "conflict")
        result, client = self.apply(plan, spec)
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_CHANGE_NOT_ACCEPTED")
        self.assertEqual(client.writes(), 0)

    def test_patch_readback_fault_matrix_blocks_put(self):
        identifier = runner_id_for()
        cases = {
            "http_failure": json_response(503, {"detail": "x"}),
            "bad_array": json_response(200, {"runners": []}),
            "bad_schema": json_response(200, [{**self.runner_item(identifier), "capabilities": "tool_use"}]),
            "missing_row": json_response(200, []),
            "runtime_conflict": json_response(200, [self.runner_item(identifier, runtime="dsh")]),
            "retired": json_response(200, [self.runner_item(identifier, adapter_status="retired")]),
            "field_conflict": json_response(200, [self.runner_item(identifier, adapter_note="boom")]),
        }
        for label, response in cases.items():
            with self.subTest(case=label):
                self.setUp()
                try:
                    plan, spec, identifier = self._conflict_plan()
                    fault = Scripted("GET", "/api/runners", response=response, enabled=False)
                    arm = Scripted(
                        "PATCH",
                        "/api/runners",
                        response=json_response(200, {}),
                        after=fault.enable,
                    )
                    result, client = self.apply(
                        plan, spec, accept_change=True, client=self.client([arm, fault])
                    )
                    entry = result["entries"][0]
                    self.assertIn(entry["runner"]["outcome"], ("blocked", "unknown"))
                    self.assertEqual(client.writes("PATCH"), 1)
                    self.assertEqual(client.writes("PUT"), 0)
                finally:
                    self.tearDown()

    def test_patch_timeout_with_landed_write_is_confirmed(self):
        plan, spec, identifier = self._conflict_plan()
        patch = Scripted(
            "PATCH",
            "/api/runners",
            exc=httpx.ReadTimeout("patch"),
            after=lambda: self._set_display_name(identifier, "Kimi Code CLI"),
        )
        result, client = self.apply(plan, spec, accept_change=True, client=self.client([patch]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["write_outcome"], "timeout")
        self.assertEqual(entry["runner"]["outcome"], "patched")
        self.assertEqual(client.writes("PATCH"), 1)
        self.assertEqual(client.writes("PUT"), 1)

    def test_patch_timeout_without_landed_write_leaves_put_at_zero(self):
        plan, spec, identifier = self._conflict_plan()
        patch = Scripted("PATCH", "/api/runners", exc=httpx.ReadTimeout("patch"))
        result, client = self.apply(plan, spec, accept_change=True, client=self.client([patch]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["write_outcome"], "timeout")
        self.assertEqual(entry["runner"]["outcome"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_CONFLICT")
        self.assertEqual(client.writes("PATCH"), 1)
        self.assertEqual(client.writes("PUT"), 0)
        self.assertEqual(self.runner_rows()[0].display_name, "Other display")

    def test_patch_timeout_readback_matrix_blocks_put(self):
        for label, response in self.runner_readback_cases(runner_id_for()).items():
            with self.subTest(case=label):
                self.setUp()
                try:
                    plan, spec, identifier = self._conflict_plan()
                    fault = Scripted("GET", "/api/runners", response=response, enabled=False)

                    def landed(fault=fault, identifier=identifier) -> None:
                        self._set_display_name(identifier, "Kimi Code CLI")
                        fault.enable()

                    patch = Scripted(
                        "PATCH", "/api/runners", exc=httpx.ReadTimeout("patch"), after=landed
                    )
                    self.assert_write_then_readback_fault_blocks_put(
                        plan, spec, [patch, fault], "PATCH"
                    )
                finally:
                    self.tearDown()

    def _set_display_name(self, identifier: str, value: str) -> None:
        with self.session() as session:
            row = session.get(RunnerRegistry, identifier)
            row.display_name = value
            session.add(row)
            session.commit()


# ---------------------------------------------------------------------------
# apply：绑定七字段 / 阶梯 / PUT 读回 / 部分恢复
# ---------------------------------------------------------------------------


class ApplyBindingTests(RegistryTestCase):
    def _seed_matching_runner(self) -> str:
        identifier = runner_id_for()
        self.add_runner(identifier)
        return identifier

    def _ladder_block(self, mutate):
        plan, spec = self.ready_plan()
        mutate()
        result, client = self.apply(plan, spec)
        entry = result["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_TARGET_NOT_ELIGIBLE")
        self.assertEqual(client.writes(), 0)
        self.assertEqual(self.runner_rows(), [])

    def test_apply_blocks_member_missing(self):
        def mutate():
            with self.session() as session:
                session.delete(session.get(Member, AGENT_ID))
                session.commit()

        self._ladder_block(mutate)

    def test_apply_blocks_member_disabled(self):
        def mutate():
            with self.session() as session:
                member = session.get(Member, AGENT_ID)
                member.disabled_at = datetime.now(timezone.utc)
                session.add(member)
                session.commit()

        self._ladder_block(mutate)

    def test_apply_blocks_not_in_roster(self):
        def mutate():
            with self.session() as session:
                session.delete(session.get(ProjectAgent, (PROJECT_ID, AGENT_ID)))
                session.commit()

        self._ladder_block(mutate)

    def test_apply_blocks_not_agent(self):
        def mutate():
            with self.session() as session:
                member = session.get(Member, AGENT_ID)
                member.kind = "human"
                session.add(member)
                session.commit()

        self._ladder_block(mutate)

    def test_unconfigured_is_not_a_qualification_failure(self):
        plan, spec = self.ready_plan()
        self.assertEqual(plan["entries"][0]["binding"]["binding_state"], "unconfigured")
        result, _ = self.apply(plan, spec)
        self.assertEqual(result["entries"][0]["binding"]["outcome"], "bound")

    def test_binding_read_failure_blocks_with_zero_writes(self):
        plan, spec = self.ready_plan()
        script = [Scripted("GET", "/binding", response=json_response(503, {"detail": "x"}))]
        result, client = self.apply(plan, spec, client=self.client(script))
        entry = result["entries"][0]
        self.assertEqual(entry["blocked"][0]["code"], "E_BINDING_READ_FAILED")
        self.assertEqual(client.writes(), 0)

    def test_binding_response_project_or_member_mismatch_blocks_with_zero_writes(self):
        plan, spec = self.ready_plan()
        script = [
            Scripted(
                "GET",
                "/binding",
                response=json_response(
                    200,
                    {
                        "project_id": "other-project",
                        "member_id": AGENT_ID,
                        "binding": None,
                        "binding_state": "unconfigured",
                    },
                ),
            )
        ]
        result, client = self.apply(plan, spec, client=self.client(script))
        entry = result["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_STATE_DRIFT")
        self.assertEqual(client.writes(), 0)
        self.assertEqual(self.runner_rows(), [])

    def test_binding_seven_field_difference_defaults_to_conflict(self):
        identifier = self._seed_matching_runner()
        self.add_binding(expected_binding_fields(identifier, model_id="other-model-id"))
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        self.assertEqual(plan["entries"][0]["binding"]["action"], "conflict")
        self.assertEqual(plan["entries"][0]["binding"]["conflict_fields"], ["model_id"])
        result, client = self.apply(plan, spec)
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "no_op")
        self.assertEqual(entry["binding"]["outcome"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_CHANGE_NOT_ACCEPTED")
        self.assertEqual(client.writes(), 0)
        self.assertEqual(self.binding_row().model_id, "other-model-id")

    def test_binding_seven_field_difference_with_accept_updates_and_reads_back(self):
        identifier = self._seed_matching_runner()
        self.add_binding(expected_binding_fields(identifier, model_id="other-model-id"))
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["entries"][0]["binding"]["action"], "update")
        result, client = self.apply(plan, spec, accept_change=True)
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["outcome"], "bound")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertEqual(client.writes("POST") + client.writes("PATCH"), 0)
        self.assertEqual(self.binding_row().model_id, k28.MODEL_ID)
        verify, verify_client = self._verify(plan)
        self.assertEqual(verify["verify_status"], "verified")
        self.assertEqual(verify_client.writes(), 0)

    def test_binding_valid_no_op_writes_nothing(self):
        identifier = self._seed_matching_runner()
        self.add_binding(expected_binding_fields(identifier))
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        self.assertEqual(plan["entries"][0]["binding"]["action"], "no_op")
        result, client = self.apply(plan, spec)
        self.assertEqual(result["result_status"], "complete")
        self.assertEqual(result["entries"][0]["status"], "no_op")
        self.assertEqual(client.writes(), 0)

    def test_binding_same_fields_but_state_not_bound_blocks_put(self):
        identifier = self._seed_matching_runner()
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        self.assertEqual(plan["plan_status"], "complete")
        scripted = json_response(
            200,
            {
                "project_id": PROJECT_ID,
                "member_id": AGENT_ID,
                "binding": expected_binding_fields(identifier),
                "binding_state": "partial",
            },
        )
        fault = Scripted("GET", "/binding", response=scripted, enabled=False)
        arm = Scripted(
            "GET",
            "/agents",
            response=json_response(
                200, [{"member_id": AGENT_ID, "binding_state": "unconfigured"}]
            ),
            after=fault.enable,
            excludes=("/binding",),
        )
        result, client = self.apply(plan, spec, client=self.client([arm, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["outcome"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_BINDING_NOT_BOUND")
        self.assertEqual(client.writes("PUT"), 0)

    def test_partial_binding_row_is_conflict_then_updatable_with_accept(self):
        identifier = self._seed_matching_runner()
        fields = expected_binding_fields(identifier)
        fields["model_id"] = None
        self.add_binding(fields)
        spec = make_spec(target_entry(runner_identifier=identifier))

        plan, _ = self.plan(spec)
        entry = plan["entries"][0]
        self.assertEqual(entry["binding"]["binding_state"], "partial")
        self.assertEqual(entry["binding"]["action"], "conflict")
        self.assertIn("model_id", entry["binding"]["conflict_fields"])
        result, client = self.apply(plan, spec)
        self.assertEqual(result["entries"][0]["blocked"][0]["code"], "E_CHANGE_NOT_ACCEPTED")
        self.assertEqual(client.writes(), 0)

        accepted, _ = self.plan(spec, accept_change=True)
        self.assertEqual(accepted["entries"][0]["binding"]["action"], "update")
        result2, client2 = self.apply(accepted, spec, accept_change=True)
        self.assertEqual(result2["entries"][0]["binding"]["outcome"], "bound")
        self.assertEqual(client2.writes("PUT"), 1)
        self.assertEqual(self.binding_row().model_id, k28.MODEL_ID)

    def test_put_timeout_with_consistent_readback_is_bound(self):
        identifier = self._seed_matching_runner()
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        put = Scripted(
            "PUT",
            "/binding",
            exc=httpx.ReadTimeout("put"),
            after=lambda: self.add_binding(expected_binding_fields(identifier)),
        )
        result, client = self.apply(plan, spec, client=self.client([put]))
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["write_outcome"], "timeout")
        self.assertEqual(entry["binding"]["outcome"], "bound")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertEqual(result["result_status"], "complete")

    def test_put_timeout_with_inconsistent_readback_is_unknown_without_retry(self):
        identifier = self._seed_matching_runner()
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        put = Scripted(
            "PUT",
            "/binding",
            exc=httpx.ReadTimeout("put"),
            after=lambda: self.add_binding(
                expected_binding_fields(identifier, model_id="landed-other-model")
            ),
        )
        result, client = self.apply(plan, spec, client=self.client([put]))
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["outcome"], "unknown")
        self.assertEqual(len(client.paths("PUT")), 1)
        self.assertEqual(self.binding_row().model_id, "landed-other-model")

    def test_put_timeout_with_failed_readback_is_unknown(self):
        identifier = self._seed_matching_runner()
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        fault = Scripted("GET", "/binding", response=json_response(503, {"detail": "x"}), enabled=False)
        put = Scripted("PUT", "/binding", exc=httpx.ReadTimeout("put"), after=fault.enable)
        result, client = self.apply(plan, spec, client=self.client([put, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["outcome"], "unknown")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertIsNone(self.binding_row())

    def test_put_http_error_without_landing_is_unknown_without_retry(self):
        identifier = self._seed_matching_runner()
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        put = Scripted("PUT", "/binding", response=json_response(422, {"detail": "x"}))
        result, client = self.apply(plan, spec, client=self.client([put]))
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["outcome"], "unknown")
        self.assertEqual(entry["binding"]["write_outcome"], "http_error:422")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertIsNone(self.binding_row())

    def test_put_200_readback_inconsistent_is_unknown(self):
        identifier = self._seed_matching_runner()
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)
        fault = Scripted(
            "GET",
            "/binding",
            response=json_response(
                200,
                {
                    "project_id": PROJECT_ID,
                    "member_id": AGENT_ID,
                    "binding": expected_binding_fields(identifier, model_id="other-model-id"),
                    "binding_state": "bound",
                },
            ),
            enabled=False,
        )
        put = Scripted("PUT", "/binding", response=json_response(200, {}), after=fault.enable)
        result, client = self.apply(plan, spec, client=self.client([put, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["outcome"], "unknown")
        self.assertEqual(entry["blocked"][0]["code"], "E_BINDING_NOT_CONFIRMED")
        self.assertEqual(entry["binding"]["conflict_fields"], ["model_id"])

    def test_partial_success_then_rerun_recovers_only_pending_items(self):
        plan, spec = self.ready_plan()
        put = Scripted("PUT", "/binding", exc=httpx.ReadTimeout("put"))
        first, client1 = self.apply(plan, spec, client=self.client([put]))
        entry1 = first["entries"][0]
        self.assertEqual(entry1["runner"]["outcome"], "created")
        self.assertEqual(entry1["binding"]["outcome"], "unknown")
        self.assertEqual(first["result_status"], "failed")
        self.assertEqual(client1.writes("POST"), 1)
        self.assertEqual(len(client1.paths("PUT")), 1)
        self.assertEqual(len(self.runner_rows()), 1)  # 已成功条目不回滚
        self.assertIsNone(self.binding_row())
        self.assertTrue(entry1["recovery"]["resume"])

        second, client2 = self.apply(plan, spec)
        entry2 = second["entries"][0]
        self.assertEqual(entry2["runner"]["outcome"], "no_op")
        self.assertEqual(entry2["binding"]["outcome"], "bound")
        self.assertEqual(client2.writes("POST"), 0)
        self.assertEqual(client2.writes("PUT"), 1)
        self.assertEqual(second["result_status"], "complete")

        third, client3 = self.apply(plan, spec)
        self.assertEqual(third["result_status"], "complete")
        self.assertEqual(third["entries"][0]["status"], "no_op")
        self.assertEqual(client3.writes(), 0)

    def test_successful_runner_is_not_rolled_back_when_binding_blocks(self):
        identifier = runner_id_for()
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec)

        def concurrent_binding() -> None:
            self.add_runner(identifier)
            self.add_binding(
                expected_binding_fields(identifier, model_id="concurrent-model-id")
            )

        post = Scripted(
            "POST",
            "/api/runners",
            response=json_response(201, self.runner_item(identifier)),
            after=concurrent_binding,
        )
        result, client = self.apply(plan, spec, client=self.client([post]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "created")
        self.assertEqual(entry["binding"]["outcome"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_CHANGE_NOT_ACCEPTED")
        self.assertEqual(entry["status"], "partial")
        self.assertEqual(client.writes("PUT"), 0)
        self.assertEqual(len(self.runner_rows()), 1)
        self.assertEqual(self.binding_row().model_id, "concurrent-model-id")

    def runner_item(self, identifier: str, **overrides) -> dict:
        fields = expected_runner_fields(identifier, **overrides)
        fields.update(
            {
                "created_by": HUMAN_ID,
                "created_at": "2026-10-10T00:00:00Z",
                "updated_at": "2026-10-10T00:00:00Z",
            }
        )
        return fields

    def _verify(self, plan):
        client = self.client()
        return (
            registry.verify_plan(plan=plan, client=client, credential=HUMAN_KEY),
            client,
        )


# ---------------------------------------------------------------------------
# verify：只读核验
# ---------------------------------------------------------------------------


class VerifyTests(RegistryTestCase):
    def test_verify_after_apply_is_verified_and_read_only(self):
        plan, spec = self.ready_plan()
        self.apply(plan, spec)
        client = self.client()
        verify = registry.verify_plan(plan=plan, client=client, credential=HUMAN_KEY)
        self.assertEqual(verify["verify_status"], "verified")
        self.assertTrue(verify["entries"][0]["verified"])
        self.assertEqual(verify["entries"][0]["binding"]["binding_state"], "bound")
        self.assertEqual(client.writes(), 0)
        self.assertEqual([method for method, _ in client.calls], ["GET"] * len(client.calls))

    def test_verify_is_unverified_before_any_write(self):
        plan, _spec = self.ready_plan()
        client = self.client()
        verify = registry.verify_plan(plan=plan, client=client, credential=HUMAN_KEY)
        self.assertEqual(verify["verify_status"], "unverified")
        self.assertFalse(verify["entries"][0]["runner"]["present"])
        self.assertEqual(client.writes(), 0)

    def test_verify_reports_seven_field_differences(self):
        identifier = runner_id_for()
        self.add_runner(identifier)
        self.add_binding(expected_binding_fields(identifier, model_id="other-model-id"))
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        client = self.client()
        verify = registry.verify_plan(plan=plan, client=client, credential=HUMAN_KEY)
        record = verify["entries"][0]
        self.assertFalse(record["verified"])
        self.assertEqual(record["binding"]["seven_field_differences"], ["model_id"])
        self.assertFalse(record["binding"]["bound"])
        self.assertEqual(client.writes(), 0)

    def test_verify_blocked_plan_entry_is_unverified(self):
        spec = make_spec(target_entry(project_id="missing-project"))
        plan, _ = self.plan(spec)
        client = self.client()
        verify = registry.verify_plan(plan=plan, client=client, credential=HUMAN_KEY)
        self.assertEqual(verify["verify_status"], "unverified")
        self.assertEqual(verify["entries"][0]["blocked"][-1]["code"], "E_PLAN_ENTRY_BLOCKED")
        self.assertEqual(client.writes(), 0)

    def test_verify_rejects_server_mismatch(self):
        plan, _spec = self.ready_plan()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.verify_plan(
                plan=plan,
                client=self.client(),
                credential=HUMAN_KEY,
                server="http://other-host",
            )
        self.assertEqual(ctx.exception.code, "E_SERVER_MISMATCH")


# ---------------------------------------------------------------------------
# 隐私：apply / verify 输出
# ---------------------------------------------------------------------------


class ApplyPrivacyTests(RegistryTestCase):
    def test_apply_and_verify_outputs_never_contain_credentials(self):
        plan, spec = self.ready_plan()
        result, _ = self.apply(plan, spec)
        blob = blob_of(result)
        for canary in (HUMAN_KEY, AGENT_KEY, OUTSIDER_KEY):
            self.assertNotIn(canary, blob)
        client = self.client()
        verify = registry.verify_plan(plan=plan, client=client, credential=HUMAN_KEY)
        verify_blob = blob_of(verify)
        for canary in (HUMAN_KEY, AGENT_KEY, OUTSIDER_KEY):
            self.assertNotIn(canary, verify_blob)

    def test_identity_failure_result_never_contains_credential(self):
        plan, spec = self.ready_plan()
        result, _ = self.apply(plan, spec, credential="wrong-canary-key")
        self.assertNotIn("wrong-canary-key", blob_of(result))

    def test_blocked_entry_output_has_no_values_from_credentials(self):
        target = target_entry(binding_overrides={"provider_id": CANARY_CREDENTIAL})
        spec = make_spec(target)
        plan, _ = self.plan(spec)
        result, _ = self.apply(plan, spec)
        blob = blob_of(result)
        self.assertNotIn(CANARY_CREDENTIAL, blob)
        self.assertNotIn(HUMAN_KEY, blob)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


class CliTests(RegistryTestCase):
    def _write(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _run(self, argv, client):
        out = io.StringIO()
        err = io.StringIO()
        with mock.patch.object(registry, "_default_client", lambda server, timeout: client), \
                mock.patch.dict(os.environ, {"C2_KEY": HUMAN_KEY}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = registry.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_help_lists_all_three_subcommands(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ctx:
            registry.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        for command in ("plan", "apply", "verify"):
            self.assertIn(command, text)

    def test_plaintext_key_argument_is_not_supported(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            registry.main(["plan", "--key", "secret", "--spec", "x"])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_plan_apply_verify_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="c2-cli-") as workdir:
            spec_path = Path(workdir) / "spec.json"
            plan_path = Path(workdir) / "plan.json"
            self._write(spec_path, make_spec(target_entry()))

            code, out, err = self._run(
                ["plan", "--spec", str(spec_path), "--key-env", "C2_KEY", "--out", str(plan_path)],
                self.client(),
            )
            self.assertEqual(code, 0, err)
            self.assertTrue(plan_path.is_file())
            on_disk = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["schema"], registry.PLAN_SCHEMA)
            self.assertEqual(on_disk["plan_status"], "complete")
            self.assertNotIn(HUMAN_KEY, plan_path.read_text(encoding="utf-8"))

            code, out, err = self._run(
                ["apply", "--plan", str(plan_path), "--spec", str(spec_path), "--key-env", "C2_KEY"],
                self.client(),
            )
            self.assertEqual(code, 0, err)
            applied = json.loads(out)
            self.assertEqual(applied["schema"], registry.RESULT_SCHEMA)
            self.assertEqual(applied["result_status"], "complete")

            code, out, err = self._run(
                ["verify", "--plan", str(plan_path), "--key-env", "C2_KEY"], self.client()
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["verify_status"], "verified")

    def test_cli_apply_without_credential_source_exits_two(self):
        with tempfile.TemporaryDirectory(prefix="c2-cli-") as workdir:
            spec_path = Path(workdir) / "spec.json"
            plan_path = Path(workdir) / "plan.json"
            self._write(spec_path, make_spec(target_entry()))
            code, _, _ = self._run(
                ["plan", "--spec", str(spec_path), "--key-env", "C2_KEY", "--out", str(plan_path)],
                self.client(),
            )
            self.assertEqual(code, 0)
            err = io.StringIO()
            with mock.patch.object(
                registry, "_default_client", lambda server, timeout: self.client()
            ), contextlib.redirect_stderr(err):
                code = registry.main(["apply", "--plan", str(plan_path), "--spec", str(spec_path)])
            self.assertEqual(code, 2)
            self.assertIn("E_CREDENTIAL_SOURCE_MISSING", err.getvalue())

    def test_cli_plan_returns_one_for_blocked_plan(self):
        with tempfile.TemporaryDirectory(prefix="c2-cli-") as workdir:
            spec_path = Path(workdir) / "spec.json"
            plan_path = Path(workdir) / "plan.json"
            self._write(spec_path, make_spec(target_entry(project_id="missing-project")))
            code, _, _ = self._run(
                ["plan", "--spec", str(spec_path), "--key-env", "C2_KEY", "--out", str(plan_path)],
                self.client(),
            )
            self.assertEqual(code, 1)

    def test_cli_rejects_key_file_inside_repo(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = registry.main(
                [
                    "verify",
                    "--plan",
                    str(PROJECT_ROOT / "does-not-exist.json"),
                    "--key-file",
                    str(PROJECT_ROOT / "config.toml"),
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("E_KEY_FILE_IN_REPO", err.getvalue())


# ---------------------------------------------------------------------------
# 返修针对测试（F1–F5）：写回/读回边界、状态白名单、plan 元数据、CLI、accept-change
# ---------------------------------------------------------------------------


def readback_runner_item(identifier: str, **overrides) -> dict:
    """写后 GET /api/runners 的完整 RunnerOut 形状（合成，合法 JSON 日期）。"""
    fields = expected_runner_fields(identifier, **overrides)
    fields.update(
        {
            "created_by": HUMAN_ID,
            "created_at": "2026-10-10T00:00:00Z",
            "updated_at": "2026-10-10T00:00:00Z",
        }
    )
    return fields


class ReworkRunnerReadbackSchemaTests(RegistryTestCase):
    """F1：写后读回必须能完整实例化既有 RunnerOut（含日期），否则该条 PUT=0。"""

    def _faulty_readback(self, identifier: str, field: str, value: object) -> Scripted:
        item = readback_runner_item(identifier)
        item[field] = value
        return Scripted(
            "GET", "/api/runners", response=json_response(200, [item]), enabled=False
        )

    def _post_bad_readback(self, field: str, value: object):
        identifier = runner_id_for()
        plan, spec = self.ready_plan()
        fault = self._faulty_readback(identifier, field, value)

        def land() -> None:
            self.add_runner(identifier)
            fault.enable()

        post = Scripted(
            "POST",
            "/api/runners",
            response=json_response(201, readback_runner_item(identifier)),
            after=land,
        )
        return self.apply(plan, spec, client=self.client([post, fault]))

    def _patch_bad_readback(self, field: str, value: object):
        identifier = runner_id_for()
        self.add_runner(identifier, display_name="Previous registration")
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["plan_status"], "complete", plan)
        fault = self._faulty_readback(identifier, field, value)

        def land() -> None:
            self._set_display_name(identifier, "Kimi Code CLI")
            fault.enable()

        patch = Scripted(
            "PATCH", "/api/runners", response=json_response(200, {}), after=land
        )
        return self.apply(plan, spec, accept_change=True, client=self.client([patch, fault]))

    def _set_display_name(self, identifier: str, value: str) -> None:
        with self.session() as session:
            row = session.get(RunnerRegistry, identifier)
            row.display_name = value
            session.add(row)
            session.commit()

    def _assert_bad_readback_blocks_put(self, result, client, write_method: str) -> None:
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "unknown")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_READ_FAILED")
        self.assertEqual(client.writes(write_method), 1)
        self.assertEqual(len(client.paths(write_method)), 1)
        self.assertEqual(client.writes("PUT"), 0)
        self.assertEqual(entry["binding"]["write"], "none")
        self.assertNotEqual(result["result_status"], "complete")

    def test_post_readback_invalid_dates_block_binding_put(self):
        for field in ("created_at", "updated_at"):
            with self.subTest(field=field):
                self.setUp()
                try:
                    result, client = self._post_bad_readback(field, "not-a-datetime")
                    self._assert_bad_readback_blocks_put(result, client, "POST")
                finally:
                    self.tearDown()

    def test_patch_readback_invalid_dates_block_binding_put(self):
        for field in ("created_at", "updated_at"):
            with self.subTest(field=field):
                self.setUp()
                try:
                    result, client = self._patch_bad_readback(field, "not-a-datetime")
                    self._assert_bad_readback_blocks_put(result, client, "PATCH")
                finally:
                    self.tearDown()

    def test_post_readback_legal_json_dates_is_accepted(self):
        identifier = runner_id_for()
        plan, spec = self.ready_plan()
        fault = Scripted(
            "GET",
            "/api/runners",
            response=json_response(200, [readback_runner_item(identifier)]),
            enabled=False,
        )

        def land() -> None:
            self.add_runner(identifier)
            fault.enable()

        post = Scripted(
            "POST",
            "/api/runners",
            response=json_response(201, readback_runner_item(identifier)),
            after=land,
        )
        result, client = self.apply(plan, spec, client=self.client([post, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "created")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertEqual(result["result_status"], "complete")

    def test_patch_readback_legal_json_dates_is_accepted(self):
        identifier = runner_id_for()
        self.add_runner(identifier, display_name="Previous registration")
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        fault = Scripted(
            "GET",
            "/api/runners",
            response=json_response(200, [readback_runner_item(identifier)]),
            enabled=False,
        )

        def land() -> None:
            self._set_display_name(identifier, "Kimi Code CLI")
            fault.enable()

        patch = Scripted(
            "PATCH", "/api/runners", response=json_response(200, {}), after=land
        )
        result, client = self.apply(
            plan, spec, accept_change=True, client=self.client([patch, fault])
        )
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "patched")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertEqual(result["result_status"], "complete")


class ReworkWriteFailureStopsBindingTests(RegistryTestCase):
    """F2：明确失败的写 HTTP 不得升级为 created/patched/bound，也不得继续本条 PUT。"""

    def _post_failure(self, status: int):
        identifier = runner_id_for()
        plan, spec = self.ready_plan()
        fault = Scripted(
            "GET",
            "/api/runners",
            response=json_response(200, [readback_runner_item(identifier)]),
            enabled=False,
        )
        post = Scripted(
            "POST",
            "/api/runners",
            response=json_response(status, {"detail": "synthetic write rejection"}),
            after=fault.enable,
        )
        return self.apply(plan, spec, client=self.client([post, fault]))

    def _patch_failure(self, status: int):
        identifier = runner_id_for()
        self.add_runner(identifier, display_name="Previous registration")
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["plan_status"], "complete", plan)
        fault = Scripted(
            "GET",
            "/api/runners",
            response=json_response(200, [readback_runner_item(identifier)]),
            enabled=False,
        )
        patch = Scripted(
            "PATCH",
            "/api/runners",
            response=json_response(status, {"detail": "synthetic write rejection"}),
            after=fault.enable,
        )
        return self.apply(plan, spec, accept_change=True, client=self.client([patch, fault]))

    def _assert_explicit_failure_blocks_put(
        self, result, client, write_method: str, status: int
    ) -> None:
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["write_outcome"], f"http_error:{status}")
        self.assertEqual(entry["runner"]["outcome"], "failed")
        self.assertEqual(entry["blocked"][0]["code"], "E_WRITE_FAILED")
        # 观察事实仍保留：最新 GET 确实读到一致运行器。
        self.assertEqual(entry["runner"]["live_action"], "no_op")
        self.assertEqual(client.writes(write_method), 1)
        self.assertEqual(client.writes("PUT"), 0)
        self.assertEqual(entry["binding"]["write"], "none")
        self.assertNotEqual(result["result_status"], "complete")

    def test_post_explicit_http_failure_never_reports_created(self):
        for status in (401, 403, 422, 500):
            with self.subTest(status=status):
                self.setUp()
                try:
                    result, client = self._post_failure(status)
                    self._assert_explicit_failure_blocks_put(result, client, "POST", status)
                finally:
                    self.tearDown()

    def test_patch_explicit_http_failure_never_reports_patched(self):
        for status in (401, 403, 422, 500):
            with self.subTest(status=status):
                self.setUp()
                try:
                    result, client = self._patch_failure(status)
                    self._assert_explicit_failure_blocks_put(result, client, "PATCH", status)
                finally:
                    self.tearDown()

    def test_post_explicit_failure_with_failed_readback_is_unknown(self):
        plan, spec = self.ready_plan()
        fault = Scripted(
            "GET", "/api/runners", response=json_response(503, {"detail": "x"}), enabled=False
        )
        post = Scripted(
            "POST",
            "/api/runners",
            response=json_response(500, {"detail": "synthetic write rejection"}),
            after=fault.enable,
        )
        result, client = self.apply(plan, spec, client=self.client([post, fault]))
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["outcome"], "unknown")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_READ_FAILED")
        self.assertEqual(client.writes("PUT"), 0)
        self.assertNotEqual(result["result_status"], "complete")

    def test_put_explicit_failure_with_consistent_readback_is_not_bound(self):
        identifier = runner_id_for()
        self.add_runner(identifier)
        self.add_binding(expected_binding_fields(identifier, model_id="other-model-id"))
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["plan_status"], "complete", plan)
        fault = Scripted(
            "GET",
            "/binding",
            response=json_response(
                200,
                {
                    "project_id": PROJECT_ID,
                    "member_id": AGENT_ID,
                    "binding": expected_binding_fields(identifier),
                    "binding_state": "bound",
                },
            ),
            enabled=False,
        )
        put = Scripted(
            "PUT",
            "/binding",
            response=json_response(422, {"detail": "synthetic write rejection"}),
            after=fault.enable,
        )
        result, client = self.apply(
            plan, spec, accept_change=True, client=self.client([put, fault])
        )
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["write_outcome"], "http_error:422")
        self.assertEqual(entry["binding"]["outcome"], "unknown")
        self.assertEqual(entry["binding"]["binding_state"], "bound")  # 观察事实保留
        self.assertEqual(entry["blocked"][0]["code"], "E_WRITE_FAILED")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertNotEqual(result["result_status"], "complete")


class Method409Client(CountingClient):
    """把指定方法的写响应改写成 ``409``：真实请求已打到真实 router，可能已落库。

    可选 ``fault`` 规则在首次 ``409`` 之后启用，用于注入“写后读回失败”分支。
    """

    def __init__(
        self,
        inner,
        method: str,
        *,
        fault: Scripted | None = None,
        path_fragment: str = "/api/runners",
    ) -> None:
        super().__init__(inner, [fault] if fault is not None else [])
        self.method = method.upper()
        self.fault = fault
        self.path_fragment = path_fragment

    def request(self, method: str, url: str, **kwargs):
        response = super().request(method, url, **kwargs)
        if method.upper() == self.method and self.path_fragment in url:
            if self.fault is not None:
                self.fault.enable()
            return json_response(409, {"detail": "synthetic conflict"})
        return response


class Method409BoundaryTests(RegistryTestCase):
    """F2 定向补正：``409`` 同事实重分类只属于 ``POST`` 登记写。

    ``PATCH`` / ``PUT`` 返回明确失败的 ``409`` 时，即使真实写已落库、最新读回与期望
    一致，也只能保留观察事实，不得宣称 ``patched`` / ``bound``，也不得继续本条
    ``PUT``；``POST 409`` 的已批准正例仍然放行。
    """

    def method_409_client(
        self, method: str, *, fault: Scripted | None = None, path_fragment: str = "/api/runners"
    ) -> Method409Client:
        return Method409Client(
            self.raw_client, method, fault=fault, path_fragment=path_fragment
        )

    def _patch_409_plan(self):
        identifier = runner_id_for()
        self.add_runner(identifier, display_name="Previous registration")
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["plan_status"], "complete", plan)
        return identifier, plan, spec

    def test_post_409_same_fact_is_still_reclassified_and_binds(self):
        plan, spec = self.ready_plan()
        client = self.method_409_client("POST")
        result = registry.apply_plan(
            plan=plan, spec=spec, client=client, credential=HUMAN_KEY
        )
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["write_outcome"], "http_error:409")
        self.assertEqual(entry["runner"]["live_action"], "no_op")
        self.assertEqual(entry["runner"]["outcome"], "created")
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 1)
        self.assertEqual(entry["binding"]["outcome"], "bound")
        self.assertEqual(result["result_status"], "complete")

    def test_patch_409_consistent_readback_is_failure_and_stops_binding_put(self):
        identifier, plan, spec = self._patch_409_plan()
        client = self.method_409_client("PATCH")
        result = registry.apply_plan(
            plan=plan, spec=spec, client=client, credential=HUMAN_KEY, accept_change=True
        )
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["write_outcome"], "http_error:409")
        self.assertEqual(entry["runner"]["http_status"], 409)
        # 观察事实保留：真实 PATCH 已落库，最新读回与期望一致。
        self.assertEqual(entry["runner"]["live_action"], "no_op")
        self.assertEqual(
            self.runner_rows()[0].display_name,
            expected_runner_fields(identifier)["display_name"],
        )
        # 写结果不得升级：不是 patched，也不得继续本条 binding PUT。
        self.assertEqual(entry["runner"]["outcome"], "failed")
        self.assertEqual(entry["runner"]["blocked_reason"]["code"], "E_WRITE_FAILED")
        self.assertEqual(entry["blocked"][0]["code"], "E_WRITE_FAILED")
        self.assertEqual(client.writes("PATCH"), 1)
        self.assertEqual(client.writes("PUT"), 0)
        self.assertEqual(entry["binding"]["write"], "none")
        self.assertEqual(entry["binding"]["outcome"], "skipped")
        self.assertEqual(entry["writes"]["put_binding"], 0)
        self.assertEqual(result["result_status"], "failed")
        self.assertNotEqual(result["result_status"], "complete")

    def test_patch_409_with_failed_readback_is_unknown_without_binding_put(self):
        identifier, plan, spec = self._patch_409_plan()
        fault = Scripted(
            "GET", "/api/runners", response=json_response(503, {"detail": "x"}), enabled=False
        )
        client = self.method_409_client("PATCH", fault=fault)
        result = registry.apply_plan(
            plan=plan, spec=spec, client=client, credential=HUMAN_KEY, accept_change=True
        )
        entry = result["entries"][0]
        self.assertEqual(entry["runner"]["write_outcome"], "http_error:409")
        self.assertEqual(entry["runner"]["outcome"], "unknown")
        self.assertEqual(entry["blocked"][0]["code"], "E_RUNNER_READ_FAILED")
        self.assertEqual(client.writes("PATCH"), 1)
        self.assertEqual(client.writes("PUT"), 0)
        self.assertNotEqual(result["result_status"], "complete")
        self.assertIsNone(self.binding_row())

    def test_put_409_consistent_readback_is_not_bound_and_not_retried(self):
        identifier = runner_id_for()
        self.add_runner(identifier)
        self.add_binding(expected_binding_fields(identifier, model_id="other-model-id"))
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["plan_status"], "complete", plan)
        client = self.method_409_client("PUT", path_fragment="/binding")
        result = registry.apply_plan(
            plan=plan, spec=spec, client=client, credential=HUMAN_KEY, accept_change=True
        )
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["write_outcome"], "http_error:409")
        self.assertEqual(entry["binding"]["http_status"], 409)
        # 观察事实保留：真实 PUT 已落库，最新读回 bound 且七字段一致。
        self.assertEqual(entry["binding"]["live_action"], "no_op")
        self.assertEqual(entry["binding"]["binding_state"], "bound")
        self.assertEqual(
            self.binding_row().model_id, expected_binding_fields(identifier)["model_id"]
        )
        # 写结果不得升级为 bound，且 PUT 至多一次、不盲重试。
        self.assertEqual(entry["binding"]["outcome"], "unknown")
        self.assertEqual(entry["binding"]["blocked_reason"]["code"], "E_WRITE_FAILED")
        self.assertEqual(entry["blocked"][0]["code"], "E_WRITE_FAILED")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertEqual(entry["writes"]["put_binding"], 1)
        self.assertNotEqual(result["result_status"], "complete")

    def test_put_409_with_failed_readback_is_unknown_without_retry(self):
        identifier = runner_id_for()
        self.add_runner(identifier)
        self.add_binding(expected_binding_fields(identifier, model_id="other-model-id"))
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["plan_status"], "complete", plan)
        fault = Scripted(
            "GET", "/binding", response=json_response(503, {"detail": "x"}), enabled=False
        )
        client = self.method_409_client("PUT", fault=fault, path_fragment="/binding")
        result = registry.apply_plan(
            plan=plan, spec=spec, client=client, credential=HUMAN_KEY, accept_change=True
        )
        entry = result["entries"][0]
        self.assertEqual(entry["binding"]["write_outcome"], "http_error:409")
        self.assertEqual(entry["binding"]["outcome"], "unknown")
        self.assertEqual(entry["blocked"][0]["code"], "E_BINDING_READ_FAILED")
        self.assertEqual(client.writes("PUT"), 1)
        self.assertNotEqual(result["result_status"], "complete")


class ReworkPlanMetadataPrivacyTests(RegistryTestCase):
    """F3：未知服务状态与可篡改 plan 元数据都不得回流原值。"""

    def _binding_state_client(self, state: str):
        script = [
            Scripted(
                "GET",
                "/binding",
                response=json_response(
                    200,
                    {
                        "project_id": PROJECT_ID,
                        "member_id": AGENT_ID,
                        "binding": None,
                        "binding_state": state,
                    },
                ),
            )
        ]
        return self.client(script)

    def test_unknown_binding_state_blocks_plan_without_echo(self):
        plan, client = self.plan(client=self._binding_state_client(CANARY_CREDENTIAL))
        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked"][0]["code"], "E_BINDING_READ_FAILED")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(plan))
        self.assertEqual(client.writes(), 0)

    def test_unknown_binding_state_blocks_apply_with_zero_writes(self):
        plan, spec = self.ready_plan()
        result, client = self.apply(
            plan, spec, client=self._binding_state_client(CANARY_CREDENTIAL)
        )
        self.assertEqual(result["entries"][0]["blocked"][0]["code"], "E_BINDING_READ_FAILED")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(result))
        self.assertEqual(client.writes(), 0)

    def test_unknown_binding_state_marks_verify_unverified_without_echo(self):
        plan, _spec = self.ready_plan()
        client = self._binding_state_client(CANARY_CREDENTIAL)
        verify = registry.verify_plan(plan=plan, client=client, credential=HUMAN_KEY)
        self.assertEqual(verify["verify_status"], "unverified")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(verify))
        self.assertEqual(client.writes(), 0)

    def test_tampered_plan_index_shape_is_rejected_with_zero_writes(self):
        plan, spec = self.ready_plan()
        plan["entries"][0]["index"] = {"secret": CANARY_CREDENTIAL}
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(plan=plan, spec=spec, client=client, credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_PLAN_INVALID")
        self.assertEqual(client.writes(), 0)

    def test_tampered_plan_index_order_is_rejected(self):
        plan, spec = self.ready_plan()
        plan["entries"][0]["index"] = 7
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(plan=plan, spec=spec, client=client, credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_PLAN_INVALID")
        self.assertEqual(client.writes(), 0)

    def test_tampered_verify_index_is_rejected_read_only(self):
        plan, _spec = self.ready_plan()
        plan["entries"][0]["index"] = {"secret": CANARY_CREDENTIAL}
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.verify_plan(plan=plan, client=client, credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_PLAN_INVALID")
        self.assertEqual(client.writes(), 0)

    def test_tampered_blocked_code_is_rejected_with_zero_writes(self):
        spec = make_spec(target_entry(project_id="missing-project"))
        plan, _ = self.plan(spec)
        self.assertEqual(plan["plan_status"], "blocked")
        plan["entries"][0]["blocked"].append(
            {"code": CANARY_CREDENTIAL, "detail": CANARY_CREDENTIAL}
        )
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(plan=plan, spec=spec, client=client, credential=HUMAN_KEY)
        self.assertEqual(ctx.exception.code, "E_PLAN_INVALID")
        self.assertEqual(client.writes(), 0)

    def test_blocked_reason_metadata_is_rebuilt_without_echo(self):
        spec = make_spec(target_entry(project_id="missing-project"))
        plan, _ = self.plan(spec)
        plan["entries"][0]["blocked"].append(
            {
                "code": "E_STATE_UNREADABLE",
                "field": CANARY_CREDENTIAL,
                "reason_code": CANARY_CREDENTIAL,
                "detail": CANARY_CREDENTIAL,
                "conflict_fields": [CANARY_CREDENTIAL],
            }
        )
        result, client = self.apply(plan, spec)
        blob = blob_of(result)
        self.assertNotIn(CANARY_CREDENTIAL, blob)
        self.assertEqual(client.writes(), 0)
        rebuilt = result["entries"][0]["blocked"][1]
        self.assertEqual(rebuilt["code"], "E_STATE_UNREADABLE")
        self.assertIsNone(rebuilt["field"])
        self.assertNotIn("reason_code", rebuilt)
        self.assertNotIn("conflict_fields", rebuilt)
        self.assertEqual(result["entries"][0]["blocked"][-1]["code"], "E_PLAN_ENTRY_BLOCKED")


class ReworkCliBoundaryTests(RegistryTestCase):
    """F4：CLI 非法输入只回稳定错误码与已知参数名，不回显原 argv、不建客户端。"""

    def _guard_client(self):
        def factory(server, timeout):
            raise AssertionError("bad input must not create a client")

        return factory

    def _run(self, argv, *, patch_client=None):
        out, err = io.StringIO(), io.StringIO()
        client = self.client()
        factory = patch_client or (lambda server, timeout: client)
        with mock.patch.object(registry, "_default_client", factory), \
                mock.patch.dict(os.environ, {"C2_KEY": HUMAN_KEY}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = registry.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue(), client

    def test_invalid_subcommand_error_has_no_original_argv(self):
        code, out, err, client = self._run([CANARY_CREDENTIAL])
        self.assertEqual(code, 2)
        self.assertIn("E_CLI_USAGE", err)
        self.assertNotIn(CANARY_CREDENTIAL, out + err)
        self.assertNotIn("Traceback", out + err)
        self.assertEqual(client.writes(), 0)

    def test_invalid_timeout_error_has_no_original_value(self):
        for value in (CANARY_CREDENTIAL, "nan", "inf", "-inf", "0", "-1", "abc"):
            with self.subTest(value=value):
                code, out, err, client = self._run(
                    ["plan", "--spec", "missing.json", "--timeout", value, "--key-env", "C2_KEY"],
                    patch_client=self._guard_client(),
                )
                self.assertEqual(code, 2)
                self.assertIn("E_CLI_USAGE", err)
                self.assertNotIn(CANARY_CREDENTIAL, out + err)
                self.assertNotIn("Traceback", out + err)
                self.assertEqual(client.writes(), 0)

    def test_leftover_argv_path_is_not_echoed(self):
        code, out, err, client = self._run(
            ["plan", "--spec", CANARY_CREDENTIAL, "--key-env", "C2_KEY"],
            patch_client=self._guard_client(),
        )
        self.assertEqual(code, 2)
        self.assertIn("E_SPEC_INVALID", err)
        self.assertNotIn(CANARY_CREDENTIAL, out + err)
        self.assertEqual(client.writes(), 0)

    def test_json_root_array_or_null_is_a_stable_error(self):
        with tempfile.TemporaryDirectory(prefix="c2-cli-root-") as folder:
            for payload in ("[]", "null", '"text"'):
                with self.subTest(payload=payload):
                    path = Path(folder) / "spec.json"
                    path.write_text(payload, encoding="utf-8")
                    code, out, err, client = self._run(
                        ["plan", "--spec", str(path), "--key-env", "C2_KEY"],
                        patch_client=self._guard_client(),
                    )
                    self.assertEqual(code, 2)
                    self.assertIn("E_SPEC_INVALID", err)
                    self.assertNotIn(str(path), out + err)
                    self.assertNotIn("Traceback", out + err)
                    self.assertEqual(client.writes(), 0)

    def test_missing_spec_file_is_a_stable_error(self):
        code, out, err, client = self._run(
            ["plan", "--spec", "no-such-spec-file.json", "--key-env", "C2_KEY"],
            patch_client=self._guard_client(),
        )
        self.assertEqual(code, 2)
        self.assertIn("E_SPEC_INVALID", err)
        self.assertNotIn("no-such-spec-file.json", out + err)
        self.assertEqual(client.writes(), 0)

    def test_bad_server_port_is_a_stable_error(self):
        with tempfile.TemporaryDirectory(prefix="c2-cli-port-") as folder:
            spec_path = Path(folder) / "spec.json"
            spec_path.write_text(json.dumps(make_spec(target_entry())), encoding="utf-8")
            for server in (
                "http://testserver:0",
                "http://testserver:99999",
                "http://testserver:abc",
            ):
                with self.subTest(server=server):
                    code, out, err, client = self._run(
                        [
                            "plan",
                            "--spec",
                            str(spec_path),
                            "--server",
                            server,
                            "--key-env",
                            "C2_KEY",
                        ],
                        patch_client=self._guard_client(),
                    )
                    self.assertEqual(code, 2)
                    self.assertIn("E_SERVER_INVALID", err)
                    self.assertNotIn("Traceback", out + err)
                    self.assertEqual(client.writes(), 0)

    def test_unwritable_output_is_a_stable_error(self):
        with tempfile.TemporaryDirectory(prefix="c2-cli-out-") as folder:
            spec_path = Path(folder) / "spec.json"
            spec_path.write_text(json.dumps(make_spec(target_entry())), encoding="utf-8")
            code, out, err, client = self._run(
                [
                    "plan",
                    "--spec",
                    str(spec_path),
                    "--key-env",
                    "C2_KEY",
                    "--out",
                    folder,  # 目录不可作为输出文件
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("E_OUTPUT_FAILED", err)
            self.assertNotIn(folder, out + err)
            self.assertNotIn("Traceback", out + err)
            self.assertEqual(client.writes(), 0)


class ReworkAcceptChangeStrictBoolTests(RegistryTestCase):
    """F5：accept_change 只接受 None 或严格 bool；truthy 非布尔不得授予变更授权。"""

    def _conflict(self):
        identifier = runner_id_for()
        self.add_runner(identifier, display_name="Previous registration")
        spec = make_spec(target_entry(runner_identifier=identifier))
        plan, _ = self.plan(spec, accept_change=True)
        self.assertEqual(plan["plan_status"], "complete", plan)
        self.assertEqual(plan["entries"][0]["runner"]["action"], "update")
        return plan, spec

    def test_non_boolean_accept_change_is_rejected_with_zero_writes(self):
        for value in ("false", "true", "", 0, 1, [], {}, ()):
            with self.subTest(value=repr(value)):
                self.setUp()
                try:
                    plan, spec = self._conflict()
                    client = self.client()
                    with self.assertRaises(registry.AdapterRegistryError) as ctx:
                        registry.apply_plan(
                            plan=plan,
                            spec=spec,
                            client=client,
                            credential=HUMAN_KEY,
                            accept_change=value,
                        )
                    self.assertEqual(ctx.exception.code, "E_PLAN_INVALID")
                    self.assertEqual(client.writes(), 0)
                    self.assertEqual(self.runner_rows()[0].display_name, "Previous registration")
                finally:
                    self.tearDown()

    def test_boolean_true_matches_plan_and_patches_once(self):
        plan, spec = self._conflict()
        result, client = self.apply(plan, spec, accept_change=True)
        self.assertEqual(result["entries"][0]["runner"]["outcome"], "patched")
        self.assertEqual(client.writes("PATCH"), 1)
        self.assertEqual(result["result_status"], "complete")

    def test_none_uses_plan_flag(self):
        plan, spec = self._conflict()
        result, client = self.apply(plan, spec)
        self.assertEqual(result["entries"][0]["runner"]["outcome"], "patched")
        self.assertEqual(client.writes("PATCH"), 1)

    def test_strict_boolean_drift_from_plan_raises_with_zero_writes(self):
        plan, spec = self._conflict()  # plan accept_change=True
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.apply_plan(
                plan=plan, spec=spec, client=client, credential=HUMAN_KEY, accept_change=False
            )
        self.assertEqual(ctx.exception.code, "E_PLAN_PARAM_MISMATCH")
        self.assertEqual(client.writes(), 0)

    def test_plan_spec_rejects_non_boolean_accept_change(self):
        client = self.client()
        with self.assertRaises(registry.AdapterRegistryError) as ctx:
            registry.plan_spec(
                make_spec(target_entry()),
                client=client,
                credential=HUMAN_KEY,
                accept_change="false",
            )
        self.assertEqual(ctx.exception.code, "E_PLAN_INVALID")
        self.assertEqual(client.writes(), 0)


# ---------------------------------------------------------------------------
# 导入隔离（独立子进程 + 审计钩子 + 环境读取探针）
# ---------------------------------------------------------------------------

ISOLATION_SCRIPT = r'''
import json
import os
import sys

for entry in (sys.argv[1], sys.argv[2]):
    if entry not in sys.path:
        sys.path.insert(0, entry)

# 先导入重依赖：钩子只统计本模块导入与其后的主链路。
import argparse
import collections
import dataclasses
import enum
import hashlib
import pathlib
import re
import string
import types
import typing
import unicodedata
import urllib.parse

import httpx
import pydantic
import sqlmodel
import server.models
import kimi_k28_executor
import adapter_binding_facts

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

import talk_adapter_registry as registry

import_env_reads = list(env_reads)
import_open_events = list(open_events)
del env_reads[:]
del open_events[:]
del io_events[:]

profile = adapter_binding_facts.adapter_profile(adapter_binding_facts.K28_ADAPTER)
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
selection = adapter_binding_facts.resolve_model_selection(
    config=config,
    explicit_argv_alias=profile.explicit_argv_alias,
    hard=profile.hard,
    required_hard_fields=profile.required_hard_fields,
)
runner_id = adapter_binding_facts.runner_id_for(
    profile.runtime, host_scope="isolation-host", workspace_scope="isolation-ws"
)["runner_id"]
spec = {
    "server": "http://127.0.0.1:8000",
    "targets": [
        {
            "project_id": "prj_isolation",
            "member_id": profile.member_id,
            "adapter": profile.adapter,
            "runner_fields": {
                "runner_id": runner_id,
                "runtime": profile.runtime,
                "display_name": "Kimi Code CLI",
                "adapter_status": "unverified",
                "adapter_note": None,
                "capabilities": ["tool_use"],
            },
            "binding_fields": {
                "runner_id": runner_id,
                "model_source": selection["fields"]["model_source"]["value"],
                "provider_id": selection["fields"]["provider_id"]["value"],
                "connection_ref": selection["fields"]["connection_ref"]["value"],
                "model_id": selection["fields"]["model_id"]["value"],
                "model_alias": selection["fields"]["model_alias"]["value"],
                "model_display_name": selection["fields"]["model_display_name"]["value"],
            },
            "sources": {"model_alias": {"value": kimi_k28_executor.MODEL_ALIAS}},
            "source_context": {
                "host_scope": "isolation-host",
                "workspace_scope": "isolation-ws",
                "origin": "native_profile_loaded",
                "selection": selection,
            },
        }
    ],
}
targets = registry.iter_targets(spec)
provider = registry.spec_source_provider(spec)
entry = registry._build_source_entry(targets[0], provider(targets[0]))
credential_value = registry.load_credential(
    key_env="C2_ISOLATION_KEY", environ={"C2_ISOLATION_KEY": "synthetic"}
)
server = registry.normalize_server(spec["server"])
os.environ = _real_environ

print(
    json.dumps(
        {
            "entry_status": entry["status"],
            "selection_status": selection["status"],
            "server": server,
            "credential_length": len(credential_value),
            "import_env_reads": import_env_reads,
            "import_open_events": import_open_events,
            "scenario_env_reads": list(env_reads),
            "scenario_open_events": list(open_events),
            "scenario_io_events": list(io_events),
            "server_main_imported": "server.main" in sys.modules,
            "mcp_modules": sorted(
                name
                for name in sys.modules
                if name == "mcp"
                or name.startswith("mcp.")
                or "talk_task_tools" in name
                or "talk_delivery" in name
            ),
        }
    )
)
'''


class ImportIsolationTests(unittest.TestCase):
    def _run_probe(self) -> dict:
        with tempfile.TemporaryDirectory(prefix="c2-isolation-") as workdir:
            out_path = Path(workdir) / "stdout.txt"
            err_path = Path(workdir) / "stderr.txt"
            with out_path.open("w", encoding="utf-8") as out_handle, err_path.open(
                "w", encoding="utf-8"
            ) as err_handle:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        textwrap.dedent(ISOLATION_SCRIPT),
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
            return json.loads(out_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    def test_import_and_inmemory_chain_have_no_side_effects(self):
        payload = self._run_probe()
        self.assertEqual(payload["selection_status"], "ready")
        self.assertEqual(payload["entry_status"], "ready")
        self.assertEqual(payload["server"], "http://127.0.0.1:8000")
        self.assertEqual(payload["credential_length"], len("synthetic"))
        self.assertEqual(payload["scenario_open_events"], [])
        self.assertEqual(payload["scenario_env_reads"], [])
        self.assertEqual(payload["scenario_io_events"], [])
        self.assertEqual(payload["import_env_reads"], [])
        repo = str(PROJECT_ROOT).replace("\\", "/")
        self.assertTrue(payload["import_open_events"])
        for path, mode in payload["import_open_events"]:
            normalized = path.replace("\\", "/")
            self.assertTrue(normalized.startswith(repo), normalized)
            self.assertIn("talk_adapter_registry", normalized)
            if "__pycache__" in normalized:
                self.assertIn(mode, ("r", "wb"))
            else:
                self.assertEqual(mode, "r")

    def test_no_server_main_or_mcp_module_is_imported(self):
        payload = self._run_probe()
        self.assertFalse(payload["server_main_imported"])
        self.assertEqual(payload["mcp_modules"], [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
