# -*- coding: utf-8 -*-
"""C3 适配收尾共享入口（``scripts/adapter_closeout.py``）单元与行为测试。

测试真实性约定
--------------
- 挂**真实** ``server.routes.runners`` / ``server.routes.projects`` / ``server.routes.members``
  router + FastAPI ``TestClient`` + 内存 SQLite；不导入 ``server.main``；
- 身份走真实 ``get_current_member``（真实 human/agent 边界）；
- native 来源用两种边界：真实临时 ``config.toml``（验证加载/覆盖层/路径优先级）与
  显式注入的内存记录（验证 plan/apply/verify 分支），两者都不读本机真实 native 配置、
  真实 Key 或生产 DB；
- 模拟客户端仅用于异常/超时/写失败等分支。
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
import adapter_closeout as closeout  # noqa: E402
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
# 合成夹具（全部是明显夹具值；真实输出不应回流 canary/凭据）
# ---------------------------------------------------------------------------

HUMAN_ID = "human:bobo"
HUMAN_KEY = "human-canary-key-0001"
AGENT_ID = k28.MEMBER_ID
AGENT_KEY = "agent-canary-key-0002"
PROJECT_ID = "talk"
EMPTY_PROJECT_ID = "empty-project"
HOST_SCOPE = "c3-host"
WORKSPACE_SCOPE = "c3-ws"
SERVER = "http://testserver"

K3_ALIAS = "kimi-code/k3"
CANARY_CREDENTIAL = "sk-canary0123456789abcdef0123456789abcdef"
CANARY_NESTED = "canary-nested-2f19"

NATIVE_TOML = """\
default_model = "kimi-code/k3"

[models."kimi-code/kimi-for-coding"]
provider = "managed:kimi-code"
model = "kimi-for-coding"
display_name = "K2.8 Preview"
capabilities = ["tool_use"]

[models."kimi-code/k3"]
provider = "managed:kimi-code"
model = "k3"
display_name = "K3"
capabilities = ["tool_use"]

[providers."managed:kimi-code"]
type = "kimi"
api_key = "sk-canary0123456789abcdef0123456789abcdef"
"""


def make_config(
    *,
    model_id: str = k28.MODEL_ID,
    alias_present: bool = True,
    display_name: str = "K2.8 Preview",
    capabilities: object = None,
    provider: str = k28.PROVIDER_ID,
) -> dict:
    """内存 native 配置夹具；只含合成值，不读任何真实文件。"""
    if capabilities is None:
        capabilities = ["tool_use"]
    models: dict = {
        K3_ALIAS: {
            "provider": k28.PROVIDER_ID,
            "model": "k3",
            "display_name": "K3",
            "capabilities": ["tool_use"],
        }
    }
    if alias_present:
        models[k28.MODEL_ALIAS] = {
            "provider": provider,
            "model": model_id,
            "display_name": display_name,
            "capabilities": capabilities,
        }
    return {
        "default_model": K3_ALIAS,
        "providers": {k28.PROVIDER_ID: {"type": "kimi", "api_key": CANARY_CREDENTIAL}},
        "models": models,
        "unexpected": {"canary": CANARY_NESTED},
    }


def native_public(*, path_origin: str = "explicit_argument") -> dict:
    return {
        "config_source": {
            "path_origin": path_origin,
            "priority": list(closeout.PATH_PRIORITY),
            "shadowed_selectors": [],
            "documented_by": "kimi_k28_executor.default_kimi_config_path",
            "parsed": True,
            "runtime_selected": True,
            "selector_forwarded_to_runtime": False,
        },
        "override_layer": {
            "status": "none",
            "checked_env_vars": [closeout.CONFIG_PATH_SELECTOR_ENV, *closeout.INERT_ENV_VARS],
            "unproven_env_var_count": 0,
        },
        "argv_selection": {"status": "ok"},
        "native_entry": {"alias_present": True},
    }


def confirmed_loader(config: object = None, **kwargs):
    cfg = make_config() if config is None else config

    def loader() -> dict:
        return closeout.native_source_record(
            config=cfg,
            status="confirmed",
            origin="native_profile_loaded",
            public=native_public(**kwargs),
        )

    return loader


def blocked_loader(*, code: str = "E_CLOSEOUT_NATIVE_MISSING", field: str = "config_path"):
    def loader() -> dict:
        return closeout.native_source_record(
            status="blocked",
            origin="unknown",
            public=native_public(),
            blocked=[{"code": code, "field": field, "detail": "fixture blocked"}],
        )

    return loader


def blob_of(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def expected_runner_id(*, host: str = HOST_SCOPE, workspace: str = WORKSPACE_SCOPE) -> str:
    return facts.runner_id_for(
        k28.RUNTIME, host_scope=host, workspace_scope=workspace
    )["runner_id"]


# ---------------------------------------------------------------------------
# 客户端代理：真实 TestClient + 计数 + 脚本化注入（仅异常/写失败分支）
# ---------------------------------------------------------------------------


def json_response(status: int, payload: object) -> httpx.Response:
    return httpx.Response(status_code=status, json=payload)


class Scripted:
    def __init__(self, method: str, path_fragment: str, *, times: int = 1, response=None):
        self.method = method.upper()
        self.path_fragment = path_fragment
        self.remaining = times
        self.response = response
        self.fired = 0

    def matches(self, method: str, url: str) -> bool:
        return (
            self.remaining > 0
            and method == self.method
            and self.path_fragment in url
        )

    def fire(self):
        self.remaining -= 1
        self.fired += 1
        return self.response


class CountingClient:
    """薄包装：只暴露 ``base_url`` 与 ``request``，统计写入并可注入脚本响应。"""

    def __init__(self, inner, script=None) -> None:
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


class CloseoutTestCase(unittest.TestCase):
    server = SERVER

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
                Project(
                    project_id=PROJECT_ID,
                    display_name="talk",
                    maintainer_member_id=HUMAN_ID,
                )
            )
            session.add(ProjectAgent(project_id=PROJECT_ID, member_id=AGENT_ID))
            session.add(
                Project(
                    project_id=EMPTY_PROJECT_ID,
                    display_name="empty",
                    maintainer_member_id=HUMAN_ID,
                )
            )
            session.commit()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        super().tearDown()

    def session(self) -> Session:
        return Session(self.engine)

    def client(self, script=None) -> CountingClient:
        return CountingClient(self.raw_client, script)

    # -- 目标与入口封装 ---------------------------------------------------
    def target(
        self,
        *,
        project_id: str = PROJECT_ID,
        member_id: str = AGENT_ID,
        adapter: str = facts.K28_ADAPTER,
        server: str | None = SERVER,
    ) -> dict:
        return {
            "server": server,
            "project_id": project_id,
            "member_id": member_id,
            "adapter": adapter,
        }

    def plan(
        self,
        *,
        action: str = "plan",
        loader=None,
        client=None,
        credential: object = HUMAN_KEY,
        target: object = None,
        host: object = HOST_SCOPE,
        workspace: object = WORKSPACE_SCOPE,
        host_shared: object = False,
        accept_change: object = False,
        server: object = SERVER,
    ):
        client = client if client is not None else self.client()
        document = closeout.run_closeout(
            action,
            target=self.target() if target is None else target,
            host_scope=host,
            workspace_scope=workspace,
            host_shared_runner=host_shared,
            native_loader=confirmed_loader() if loader is None else loader,
            client=client,
            credential=credential,
            accept_change=accept_change,
            server=server,
        )
        return document, client

    def ready_plan(self, **kwargs):
        document, client = self.plan(**kwargs)
        self.assertEqual(document["closeout_status"], "ready", document)
        self.assertEqual(document["plan"]["plan_status"], "complete", document)
        return document, client

    def apply(
        self,
        document,
        *,
        loader=None,
        client=None,
        credential: object = HUMAN_KEY,
        host_scope: object = HOST_SCOPE,
        workspace_scope: object = WORKSPACE_SCOPE,
        target: object = None,
        **kwargs,
    ):
        """apply 夹具：按本入口合同补齐**显式** host/workspace scope。

        合同要求 apply 不得从已审计划静默补 scope，因此共享夹具必须显式传入；
        需要验证"缺失 scope 即零写阻断"的用例显式传 ``host_scope=None`` /
        ``workspace_scope=None``。
        """
        client = client if client is not None else self.client()
        result = closeout.run_closeout(
            "apply",
            plan=document,
            client=client,
            credential=credential,
            native_loader=confirmed_loader() if loader is None else loader,
            server=SERVER,
            target=target,
            host_scope=host_scope,
            workspace_scope=workspace_scope,
            **kwargs,
        )
        return result, client

    def verify(self, document, *, client=None, credential: object = HUMAN_KEY):
        client = client if client is not None else self.client()
        return closeout.run_closeout(
            "verify", plan=document, client=client, credential=credential, server=SERVER
        ), client

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


# ---------------------------------------------------------------------------
# native 有效来源：真实临时配置的只读加载
# ---------------------------------------------------------------------------


class NativeSourceLoaderTests(unittest.TestCase):
    def write_config(self, workdir, text: str = NATIVE_TOML) -> Path:
        path = Path(workdir) / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_config_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            record = closeout.load_effective_native_source(
                config_path=str(Path(workdir) / "absent.toml"), environ={}
            )
        self.assertEqual(record["status"], "blocked")
        self.assertIn("E_CLOSEOUT_NATIVE_MISSING", blob_of(record["blocked"]))
        self.assertIsNone(record["config"])

    def test_parse_error_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            path = Path(workdir) / "config.toml"
            path.write_text("this is not toml = = =\n", encoding="utf-8")
            record = closeout.load_effective_native_source(
                config_path=str(path), environ={}
            )
        self.assertEqual(record["status"], "blocked")
        self.assertIn("E_CLOSEOUT_NATIVE_PARSE_FAILED", blob_of(record["blocked"]))

    def test_valid_config_is_confirmed_and_public_has_no_path_or_secret(self):
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            path = self.write_config(workdir)
            # 合同（本片 F1 修正）：显式路径只有在**与运行入口实际解析到的文件同一**时才可确认。
            # 旧断言允许任意显式路径直接 confirmed，与"读到文件不等于生效来源"矛盾。
            record = closeout.load_effective_native_source(
                config_path=str(path), environ={"KIMI_CODE_HOME": workdir}
            )
            blob = blob_of(record["public"])
            self.assertNotIn(str(path), blob)
            self.assertNotIn(str(path).replace("\\", "/"), blob)
        self.assertEqual(record["status"], "confirmed")
        self.assertEqual(record["origin"], "native_profile_loaded")
        self.assertEqual(record["public"]["config_source"]["path_origin"], "explicit_argument")
        self.assertTrue(record["public"]["config_source"]["parsed"])
        self.assertTrue(record["public"]["config_source"]["runtime_selected"])
        self.assertNotIn("config_content_sha256", blob)
        self.assertNotIn(CANARY_CREDENTIAL, blob)
        self.assertNotIn("api_key", blob)

    def test_unselected_explicit_config_is_blocked(self):
        """F1：显式路径不等于当前运行入口实际选中的文件时，读到也不得 confirmed。"""
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            directory = Path(workdir)
            effective_home = directory / "effective-home"
            effective_home.mkdir()
            (effective_home / "config.toml").write_text(NATIVE_TOML, encoding="utf-8")
            decoy = directory / "unselected.toml"
            decoy.write_text(
                NATIVE_TOML.replace("kimi-for-coding", "different-model"), encoding="utf-8"
            )
            env = {"KIMI_CODE_HOME": str(effective_home)}
            decoy_record = closeout.load_effective_native_source(
                config_path=str(decoy), environ=env
            )
            selected_record = closeout.load_effective_native_source(environ=env)
            self.assertEqual(selected_record["status"], "confirmed")
            self.assertEqual(
                selected_record["public"]["config_source"]["path_origin"],
                "env:KIMI_CODE_HOME",
            )
            self.assertNotEqual(selected_record["config"], decoy_record["config"])
        self.assertEqual(decoy_record["status"], "blocked")
        self.assertIn(
            "E_CLOSEOUT_SOURCE_UNSELECTED", blob_of(decoy_record["blocked"])
        )
        self.assertFalse(decoy_record["public"]["config_source"]["runtime_selected"])
        self.assertNotIn(str(decoy), blob_of(decoy_record["public"]))

    def test_explicit_path_equal_to_runtime_selection_is_confirmed(self):
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            path = self.write_config(workdir)
            env = {"KIMI_CODE_HOME": workdir}
            explicit = closeout.load_effective_native_source(
                config_path=str(path), environ=env
            )
        self.assertEqual(explicit["status"], "confirmed")
        self.assertTrue(explicit["public"]["config_source"]["runtime_selected"])
        self.assertEqual(
            explicit["public"]["config_source"]["effective_path_origin"],
            "env:KIMI_CODE_HOME",
        )

    def test_unknown_override_env_blocks_confirmation(self):
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            path = self.write_config(workdir)
            record = closeout.load_effective_native_source(
                config_path=str(path),
                environ={"KIMI_CODE_HOME": workdir, "KIMI_MODEL": "canary-override"},
            )
        self.assertEqual(record["status"], "blocked")
        self.assertIn("E_CLOSEOUT_OVERRIDE_UNKNOWN", blob_of(record["blocked"]))
        self.assertEqual(record["public"]["override_layer"]["status"], "unknown")
        self.assertNotIn("canary-override", blob_of(record))

    def test_inert_env_var_does_not_block(self):
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            path = self.write_config(workdir)
            record = closeout.load_effective_native_source(
                config_path=str(path),
                environ={"KIMI_CODE_HOME": workdir, "TALK_KIMI_COMMAND": "kimi --other"},
            )
        self.assertEqual(record["status"], "confirmed")

    def test_env_home_selector_is_recorded_when_no_explicit_path(self):
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            self.write_config(workdir)
            record = closeout.load_effective_native_source(
                config_path=None, environ={"KIMI_CODE_HOME": str(workdir)}
            )
        self.assertEqual(record["status"], "confirmed")
        self.assertEqual(
            record["public"]["config_source"]["path_origin"], "env:KIMI_CODE_HOME"
        )


class ArgvEvidenceTests(unittest.TestCase):
    def test_k28_argv_matches_fixed_alias(self):
        evidence = closeout.argv_selection_evidence(facts.K28_ADAPTER)
        self.assertEqual(evidence["status"], "ok")
        self.assertTrue(evidence["public"]["matches_fixed_alias"])
        self.assertEqual(evidence["public"]["decision_tier"], "execution")
        self.assertFalse(evidence["public"]["starts_process"])
        self.assertEqual(evidence["public"]["native_cli_probe"], "not_run")
        self.assertNotIn(str(PROJECT_ROOT), blob_of(evidence))

    def test_alias_constant_drift_is_blocked(self):
        with mock.patch.object(k28, "MODEL_ALIAS", "kimi-code/other-alias"):
            evidence = closeout.argv_selection_evidence(facts.K28_ADAPTER)
        self.assertEqual(evidence["status"], "blocked")

    def test_controlled_command_drift_is_blocked(self):
        """F1：只核 alias 不够，受控 command 被替换必须 blocked。"""
        argv = k28.build_bridge_argv()
        argv[argv.index("--kimi-command") + 1] = "other-command {model}"
        with mock.patch.object(k28, "build_bridge_argv", return_value=argv):
            evidence = closeout.argv_selection_evidence(facts.K28_ADAPTER)
        self.assertEqual(evidence["status"], "blocked")
        self.assertFalse(evidence["public"]["command_matches_controlled"])
        self.assertTrue(evidence["public"]["matches_fixed_alias"])

    def test_decision_tier_drift_is_blocked(self):
        """F1：执行分级被改成 decision 必须 blocked。"""
        argv = k28.build_bridge_argv()
        argv[argv.index("--decision-tier") + 1] = "decision"
        with mock.patch.object(k28, "build_bridge_argv", return_value=argv):
            evidence = closeout.argv_selection_evidence(facts.K28_ADAPTER)
        self.assertEqual(evidence["status"], "blocked")
        self.assertFalse(evidence["public"]["decision_tier_matches"])
        self.assertEqual(evidence["public"]["decision_tier"], "decision")

    def test_config_selector_in_argv_is_blocked(self):
        """F1：桥接 argv 若夹带配置路径选择器，入口假定的生效来源不再成立。"""
        argv = [*k28.build_bridge_argv(), "--native-config", "C:/tmp/other.toml"]
        with mock.patch.object(k28, "build_bridge_argv", return_value=argv):
            evidence = closeout.argv_selection_evidence(facts.K28_ADAPTER)
        self.assertEqual(evidence["status"], "blocked")
        self.assertTrue(evidence["public"]["config_selector_forwarded"])

    def test_generic_adapter_is_not_applicable(self):
        evidence = closeout.argv_selection_evidence(facts.K3_ADAPTER)
        self.assertEqual(evidence["status"], "not_applicable")


# ---------------------------------------------------------------------------
# plan / dry-run：只读、公开证据与阻断
# ---------------------------------------------------------------------------


class PlanReadOnlyTests(CloseoutTestCase):
    def test_plan_reads_identity_roster_registry_binding_and_never_writes(self):
        document, client = self.ready_plan()
        self.assertEqual(client.writes(), 0)
        self.assertTrue(client.paths("GET"))
        joined = " ".join(client.paths("GET"))
        self.assertIn("/api/runners", joined)
        self.assertIn(f"/api/projects/{PROJECT_ID}/agents", joined)
        self.assertIn("/binding", joined)
        self.assertEqual(document["schema"], closeout.PLAN_SCHEMA)
        self.assertEqual(document["plan"]["schema"], registry.PLAN_SCHEMA)

    def test_plan_reports_public_native_evidence_and_scope(self):
        document, _ = self.ready_plan()
        native = document["native_source"]
        self.assertEqual(native["status"], "confirmed")
        self.assertEqual(
            native["argv_selection"]["matches_fixed_alias"], True
        )
        self.assertEqual(native["native_entry"]["model_id"], k28.MODEL_ID)
        self.assertEqual(native["native_entry"]["provider_id"], k28.PROVIDER_ID)
        scope = document["scope"]
        self.assertEqual(scope["host_scope"], HOST_SCOPE)
        self.assertEqual(scope["workspace_scope"], WORKSPACE_SCOPE)
        self.assertEqual(scope["runner_id"], expected_runner_id())
        self.assertEqual(scope["source"], "caller_explicit_scope")

    def test_plan_projection_lists_create_actions_and_recovery_index(self):
        document, _ = self.ready_plan()
        proposed = document["proposed"]
        self.assertEqual(proposed["counts"]["runner_create"], 1)
        self.assertEqual(proposed["counts"]["binding_create"], 1)
        self.assertEqual(len(proposed["items"]), 1)
        self.assertTrue(document["recovery_index"][0]["resume"])

    def test_dry_run_matches_plan_and_is_read_only(self):
        plan, _ = self.ready_plan()
        dry, client = self.plan(action="dry-run")
        self.assertEqual(dry["action"], "dry-run")
        self.assertEqual(dry["closeout_status"], "ready")
        self.assertEqual(client.writes(), 0)
        self.assertEqual(
            dry["plan"]["entries"][0]["expected"], plan["plan"]["entries"][0]["expected"]
        )

    def test_plan_blocked_when_member_not_in_roster(self):
        document, client = self.plan(target=self.target(project_id=EMPTY_PROJECT_ID))
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_TARGET_NOT_ELIGIBLE", blob_of(document["plan"]["entries"]))
        self.assertEqual(client.writes(), 0)

    def test_plan_blocked_when_project_missing(self):
        document, _ = self.plan(target=self.target(project_id="no-such-project"))
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_STATE_UNREADABLE", blob_of(document["plan"]["entries"]))

    def test_plan_without_client_is_blocked_not_crash(self):
        document = closeout.run_closeout(
            "plan",
            target=self.target(),
            host_scope=HOST_SCOPE,
            workspace_scope=WORKSPACE_SCOPE,
            native_loader=confirmed_loader(),
            client=None,
            credential=HUMAN_KEY,
            server=SERVER,
        )
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_CLIENT_MISSING", blob_of(document["blocked"]))

    def test_plan_requires_credential(self):
        document, _ = self.plan(credential=None)
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_CREDENTIAL_INVALID", blob_of(document["blocked"]))

    def test_plan_rejects_non_bool_accept_change(self):
        document, client = self.plan(accept_change="false")
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_FLAG_NOT_BOOL", blob_of(document["blocked"]))
        self.assertEqual(client.writes(), 0)


# ---------------------------------------------------------------------------
# scope：显式上下文与严格阻断
# ---------------------------------------------------------------------------


class ScopeTests(CloseoutTestCase):
    def test_missing_host_scope_is_blocked(self):
        document, client = self.plan(host=None)
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_SCOPE_MISSING", blob_of(document["native_source"]["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_missing_workspace_scope_is_blocked(self):
        document, _ = self.plan(workspace=None)
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_SCOPE_MISSING", blob_of(document["native_source"]["blocked"]))

    def test_invalid_scope_token_is_blocked(self):
        document, _ = self.plan(host="bad scope/with path")
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_SCOPE_INVALID", blob_of(document["native_source"]["blocked"]))

    def test_host_shared_runner_conflicts_with_workspace_scope(self):
        document, _ = self.plan(host_shared=True)
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_SCOPE_INVALID", blob_of(document["native_source"]["blocked"]))

    def test_non_bool_scope_flag_is_blocked(self):
        document, _ = self.plan(host_shared="yes")
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_FLAG_NOT_BOOL", blob_of(document["native_source"]["blocked"]))

    def test_host_shared_runner_without_workspace_is_ready(self):
        document, _ = self.ready_plan(workspace=None, host_shared=True)
        self.assertIsNone(document["scope"]["workspace_scope"])
        self.assertEqual(document["scope"]["scope_mode"], "host_shared")

    def test_scope_change_changes_runner_id_and_fingerprint(self):
        first, _ = self.ready_plan()
        second, _ = self.ready_plan(host="c3-host-2")
        self.assertNotEqual(
            first["scope"]["runner_id"], second["scope"]["runner_id"]
        )
        self.assertNotEqual(
            first["plan"]["entries"][0]["source_fingerprint"]["fingerprint"],
            second["plan"]["entries"][0]["source_fingerprint"]["fingerprint"],
        )


# ---------------------------------------------------------------------------
# native 阻断与泛用 profile 不代填
# ---------------------------------------------------------------------------


class NativeBlockingTests(CloseoutTestCase):
    def test_missing_native_source_blocks_plan(self):
        document, client = self.plan(loader=blocked_loader())
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_NATIVE_MISSING", blob_of(document))
        self.assertEqual(client.writes(), 0)

    def test_override_layer_unknown_blocks_plan(self):
        document, _ = self.plan(
            loader=blocked_loader(code="E_CLOSEOUT_OVERRIDE_UNKNOWN", field="override_layer")
        )
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_OVERRIDE_UNKNOWN", blob_of(document["native_source"]["blocked"]))

    def test_argv_mismatch_blocks_plan(self):
        with mock.patch.object(k28, "MODEL_ALIAS", "kimi-code/other-alias"):
            document, client = self.plan()
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_ARGV_MISMATCH", blob_of(document["native_source"]["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_argv_command_drift_blocks_plan(self):
        """F1：受控 command 被替换时，即使 alias 仍匹配也不得 ready。"""
        argv = k28.build_bridge_argv()
        argv[argv.index("--kimi-command") + 1] = "other-command {model}"
        with mock.patch.object(k28, "build_bridge_argv", return_value=argv):
            document, client = self.plan()
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn(
            "E_CLOSEOUT_ARGV_COMMAND_MISMATCH",
            blob_of(document["native_source"]["blocked"]),
        )
        self.assertEqual(client.writes(), 0)

    def test_argv_decision_tier_drift_blocks_plan(self):
        """F1：执行分级被改成 decision 时不得 ready。"""
        argv = k28.build_bridge_argv()
        argv[argv.index("--decision-tier") + 1] = "decision"
        with mock.patch.object(k28, "build_bridge_argv", return_value=argv):
            document, client = self.plan()
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn(
            "E_CLOSEOUT_ARGV_COMMAND_MISMATCH",
            blob_of(document["native_source"]["blocked"]),
        )
        self.assertEqual(client.writes(), 0)

    def test_unselected_explicit_native_config_blocks_plan(self):
        """F1：--native-config 指向未被运行入口选中的文件时，plan 必须 blocked。"""
        with tempfile.TemporaryDirectory(prefix="c3-native-") as workdir:
            directory = Path(workdir)
            effective_home = directory / "effective-home"
            effective_home.mkdir()
            (effective_home / "config.toml").write_text(NATIVE_TOML, encoding="utf-8")
            decoy = directory / "unselected.toml"
            decoy.write_text(NATIVE_TOML, encoding="utf-8")
            with mock.patch.dict(os.environ, {"KIMI_CODE_HOME": str(effective_home)}):
                document, client = self.plan(
                    loader=lambda: closeout.load_effective_native_source(
                        config_path=str(decoy), environ=dict(os.environ)
                    )
                )
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn(
            "E_CLOSEOUT_SOURCE_UNSELECTED", blob_of(document["native_source"]["blocked"])
        )
        self.assertFalse(
            document["native_source"]["config_source"]["runtime_selected"]
        )
        self.assertEqual(client.writes(), 0)

    def test_missing_alias_entry_blocks_plan(self):
        document, _ = self.plan(loader=confirmed_loader(make_config(alias_present=False)))
        self.assertEqual(document["closeout_status"], "blocked")
        blocked = blob_of(document["native_source"]["blocked"])
        self.assertTrue("E_CLOSEOUT_ALIAS_MISSING" in blocked or "E_SOURCE_UNAVAILABLE" in blocked)

    def test_conflicting_model_id_blocks_plan(self):
        document, _ = self.plan(loader=confirmed_loader(make_config(model_id="other-model")))
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_SOURCE_CONFLICT", blob_of(document["native_source"]["blocked"]))

    def test_credential_shaped_provider_blocks_and_is_not_echoed(self):
        document, _ = self.plan(
            loader=confirmed_loader(make_config(provider=CANARY_CREDENTIAL))
        )
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertNotIn(CANARY_CREDENTIAL, blob_of(document))

    def test_k3_profile_is_blocked_without_k28_fill(self):
        document, client = self.plan(
            target=self.target(member_id=facts.K3_ADAPTER, adapter=facts.K3_ADAPTER)
        )
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertNotIn(k28.MODEL_ALIAS, blob_of(document["plan"]))
        self.assertEqual(client.writes(), 0)

    def test_dsh_profile_is_blocked(self):
        document, _ = self.plan(target=self.target(member_id="agent:deepseek", adapter="agent:deepseek"))
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertNotIn(k28.MODEL_ALIAS, blob_of(document["plan"]))

    def test_unknown_adapter_is_blocked(self):
        document, _ = self.plan(target=self.target(member_id="agent:ghost", adapter="agent:ghost"))
        self.assertEqual(document["closeout_status"], "blocked")

    def test_member_adapter_mismatch_is_blocked(self):
        document, _ = self.plan(target=self.target(member_id=facts.K3_ADAPTER))
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_TARGET_MISMATCH", blob_of(document["plan"]["entries"]))

    def test_missing_project_id_is_blocked(self):
        document, _ = self.plan(target={"server": SERVER, "project_id": None, "member_id": AGENT_ID})
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_TARGET_INVALID", blob_of(document["blocked"]))


# ---------------------------------------------------------------------------
# apply / verify：正常分支与身份边界
# ---------------------------------------------------------------------------


class ApplyNormalTests(CloseoutTestCase):
    def test_plan_apply_verify_roundtrip(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document)
        self.assertEqual(result["closeout_status"], "complete", result)
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 1)
        rows = self.runner_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].runner_id, expected_runner_id())
        self.assertEqual(rows[0].runtime, k28.RUNTIME)
        self.assertEqual(rows[0].adapter_status, "unverified")
        binding = self.binding_row()
        self.assertEqual(binding.model_alias, k28.MODEL_ALIAS)
        self.assertEqual(binding.model_id, k28.MODEL_ID)

        verified, verify_client = self.verify(document)
        self.assertEqual(verified["closeout_status"], "verified", verified)
        self.assertEqual(verify_client.writes(), 0)

    def test_second_apply_is_no_op(self):
        document, _ = self.ready_plan()
        self.apply(document)
        second_plan, _ = self.ready_plan()
        self.assertEqual(second_plan["plan"]["summary"]["runner_no_op"], 1)
        self.assertEqual(second_plan["plan"]["summary"]["binding_no_op"], 1)
        result, client = self.apply(second_plan)
        self.assertEqual(result["closeout_status"], "complete")
        self.assertEqual(client.writes(), 0)

    def test_apply_with_agent_credential_writes_nothing(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document, credential=AGENT_KEY)
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertEqual(client.writes(), 0)
        self.assertEqual(self.runner_rows(), [])

    def test_apply_without_plan_is_blocked(self):
        result, client = self.apply(None)
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_PLAN_REQUIRED", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_apply_without_credential_writes_nothing(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document, credential="")
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertEqual(client.writes(), 0)

    def test_apply_scope_mismatch_with_reviewed_plan_is_blocked(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document, host_scope="other-host")
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_SCOPE_MISMATCH", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)


class ApplyGateTests(CloseoutTestCase):
    """F2：apply 的显式目标与显式 scope 必须先与已审计划逐项闭合，否则零写拒绝。"""

    def test_explicit_project_mismatch_blocks_before_any_write(self):
        document, _ = self.ready_plan()
        result, client = self.apply(
            document, target=self.target(project_id=EMPTY_PROJECT_ID)
        )
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_TARGET_MISMATCH", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)
        self.assertEqual(self.runner_rows(), [])
        self.assertIsNone(self.binding_row())

    def test_explicit_member_mismatch_without_project_blocks(self):
        document, _ = self.ready_plan()
        target = self.target(project_id=None, member_id="agent:other")
        result, client = self.apply(document, target=target)
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_TARGET_MISMATCH", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_explicit_adapter_mismatch_without_project_blocks(self):
        document, _ = self.ready_plan()
        target = self.target(project_id=None, adapter="agent:other")
        result, client = self.apply(document, target=target)
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_TARGET_MISMATCH", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_explicit_server_mismatch_blocks(self):
        document, _ = self.ready_plan()
        result, client = self.apply(
            document, target=self.target(server="http://other-server:8000")
        )
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_TARGET_MISMATCH", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_omitted_target_fields_are_derived_from_reviewed_plan(self):
        document, _ = self.ready_plan()
        target = {"server": None, "project_id": None, "member_id": None, "adapter": None}
        result, client = self.apply(document, target=target)
        self.assertEqual(result["closeout_status"], "complete", result)
        self.assertEqual(result["target"]["project_id"], PROJECT_ID)
        self.assertEqual(result["target"]["member_id"], AGENT_ID)
        self.assertEqual(client.writes(), 2)

    def test_apply_without_explicit_host_scope_blocks(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document, host_scope=None)
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_SCOPE_MISSING", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_apply_without_explicit_workspace_scope_blocks(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document, workspace_scope=None)
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_SCOPE_MISSING", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_apply_host_shared_mismatch_blocks(self):
        document, _ = self.ready_plan()
        result, client = self.apply(
            document, workspace_scope=None, host_shared_runner=True
        )
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_SCOPE_MISMATCH", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_apply_workspace_scope_mismatch_blocks(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document, workspace_scope="other-ws")
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_SCOPE_MISMATCH", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_apply_non_bool_host_shared_is_rejected(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document, host_shared_runner="yes")
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_FLAG_NOT_BOOL", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_agent_gated_apply_reports_native_source_not_run(self):
        """F4：人类门禁在来源加载前拒绝，native 结论必须是 not_run，不是 confirmed。"""
        document, _ = self.ready_plan()
        self.assertEqual(document["native_source"]["status"], "confirmed")
        result, client = self.apply(document, credential=AGENT_KEY)
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertEqual(result["native_source"]["status"], "not_run")
        self.assertFalse(result["native_source"]["config_source"]["parsed"])
        self.assertEqual(client.writes(), 0)

    def test_apply_limits_do_not_claim_read_only(self):
        document, _ = self.ready_plan()
        self.assertTrue(any("只读" in item for item in document["limits"]))
        result, client = self.apply(document)
        self.assertEqual(result["closeout_status"], "complete")
        self.assertFalse(
            any("只读" in item and "apply" in item for item in result["limits"])
        )
        self.assertTrue(
            any("POST/PATCH/PUT" in item for item in result["limits"])
        )
        self.assertEqual(client.writes(), 2)


# ---------------------------------------------------------------------------
# 来源漂移：plan→apply 必须重新读取实际有效来源
# ---------------------------------------------------------------------------


class SourceDriftTests(CloseoutTestCase):
    def test_public_fact_drift_blocks_apply_and_requires_replan(self):
        document, _ = self.ready_plan()
        drifted = confirmed_loader(make_config(display_name="K2.8 Preview (drifted)"))
        result, client = self.apply(document, loader=drifted)
        self.assertEqual(result["closeout_status"], "blocked", result)
        entry = result["result"]["entries"][0]
        self.assertIn("E_SOURCE_DRIFT", blob_of(entry["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_hard_contract_conflict_blocks_apply(self):
        document, _ = self.ready_plan()
        drifted = confirmed_loader(make_config(model_id="kimi-for-coding-v2"))
        result, client = self.apply(document, loader=drifted)
        self.assertEqual(result["closeout_status"], "blocked", result)
        self.assertIn("E_SOURCE_CONFLICT", blob_of(result["native_source"]["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_source_becoming_blocked_blocks_apply(self):
        document, _ = self.ready_plan()
        result, client = self.apply(document, loader=blocked_loader())
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CLOSEOUT_NATIVE_MISSING", blob_of(result["native_source"]["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_apply_reloads_source_instead_of_reusing_plan(self):
        calls = {"count": 0}
        base = confirmed_loader()

        def counting_loader() -> dict:
            calls["count"] += 1
            return base()

        document, _ = self.plan(loader=counting_loader)
        self.assertEqual(calls["count"], 1)
        result, _ = self.apply(document, loader=counting_loader)
        self.assertEqual(result["closeout_status"], "complete")
        self.assertEqual(calls["count"], 2)

    def test_fingerprint_changes_when_alias_source_changes(self):
        first, _ = self.ready_plan()
        second, _ = self.ready_plan(
            loader=confirmed_loader(make_config(display_name="K2.8 Preview (new)"))
        )
        self.assertNotEqual(
            first["plan"]["entries"][0]["source_fingerprint"]["fingerprint"],
            second["plan"]["entries"][0]["source_fingerprint"]["fingerprint"],
        )


# ---------------------------------------------------------------------------
# 差异默认冲突 / 显式 accept-change
# ---------------------------------------------------------------------------


class ChangeControlTests(CloseoutTestCase):
    def seed_conflicting_runner(self) -> None:
        now = datetime.now(timezone.utc)
        with self.session() as session:
            session.add(
                RunnerRegistry(
                    runner_id=expected_runner_id(),
                    runtime=k28.RUNTIME,
                    display_name="Old Executor Display",
                    adapter_status="unverified",
                    adapter_note=None,
                    capabilities=["tool_use"],
                    created_by=HUMAN_ID,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

    def test_existing_difference_defaults_to_conflict(self):
        self.seed_conflicting_runner()
        document, client = self.plan()
        self.assertEqual(document["closeout_status"], "partial")
        item = document["proposed"]["items"][0]
        self.assertEqual(item["runner"]["action"], "conflict")
        self.assertTrue(item["requires_accept_change"])
        self.assertEqual(client.writes(), 0)

    def test_apply_without_accept_change_is_blocked(self):
        self.seed_conflicting_runner()
        document, _ = self.plan()
        result, client = self.apply(document)
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_CHANGE_NOT_ACCEPTED", blob_of(result["result"]["entries"][0]["blocked"]))
        self.assertEqual(client.writes(), 0)

    def test_apply_with_accept_change_patches_runner(self):
        self.seed_conflicting_runner()
        document, _ = self.plan(accept_change=True)
        self.assertEqual(document["closeout_status"], "ready")
        result, client = self.apply(document)
        self.assertEqual(result["closeout_status"], "complete", result)
        self.assertEqual(client.writes("PATCH"), 1)
        rows = self.runner_rows()
        self.assertEqual(rows[0].display_name, k28.DISPLAY_NAME)

    def test_accept_change_string_is_rejected_without_writes(self):
        self.seed_conflicting_runner()
        document, _ = self.plan(accept_change=True)
        result, client = self.apply(document, accept_change="false")
        self.assertEqual(result["closeout_status"], "blocked")
        self.assertIn("E_FLAG_NOT_BOOL", blob_of(result["blocked"]))
        self.assertEqual(client.writes(), 0)


# ---------------------------------------------------------------------------
# 写失败：不盲重试、保留恢复索引
# ---------------------------------------------------------------------------


class WriteFailureTests(CloseoutTestCase):
    def test_runner_post_failure_is_not_retried_and_blocks_binding(self):
        document, _ = self.ready_plan()
        client = self.client([Scripted("POST", "/api/runners", response=json_response(500, {"detail": "x"}))])
        result, client = self.apply(document, client=client)
        entry = result["result"]["entries"][0]
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 0)
        self.assertEqual(client.writes(), 1)
        self.assertIn("E_WRITE_FAILED", blob_of(entry["blocked"]))
        self.assertEqual(
            result["recovery_index"][0]["reason"], "E_WRITE_FAILED"
        )

    def test_binding_put_failure_is_reported_once(self):
        document, _ = self.ready_plan()
        client = self.client([Scripted("PUT", "/binding", response=json_response(500, {"detail": "x"}))])
        result, client = self.apply(document, client=client)
        entry = result["result"]["entries"][0]
        self.assertEqual(client.writes("POST"), 1)
        self.assertEqual(client.writes("PUT"), 1)
        self.assertIn("E_WRITE_FAILED", blob_of(entry["blocked"]))
        self.assertIsNone(self.binding_row())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class ClientConstructionTests(unittest.TestCase):
    def test_default_client_is_direct_and_does_not_read_env_proxy(self):
        client = closeout._default_client("http://127.0.0.1:8000", 5.0)
        try:
            self.assertFalse(client.trust_env)
        finally:
            client.close()

    def test_help_documents_the_explicit_proxy_opt_in(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            closeout.main(["plan", "--help"])
        self.assertIn("--env-proxy", out.getvalue())


class CliTests(CloseoutTestCase):
    def _plan_argv(self, spec_path: Path | None = None) -> list[str]:
        argv = [
            "plan",
            "--server",
            SERVER,
            "--project-id",
            PROJECT_ID,
            "--host-scope",
            HOST_SCOPE,
            "--workspace-scope",
            WORKSPACE_SCOPE,
            "--key-env",
            "C3_KEY",
        ]
        if spec_path is not None:
            argv += ["--out", str(spec_path)]
        return argv

    def test_help_lists_subcommands(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ctx:
            closeout.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        for command in ("plan", "dry-run", "apply", "verify", "package"):
            self.assertIn(command, out.getvalue())

    def test_plaintext_key_argument_is_not_supported(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            closeout.main(["plan", "--key", "secret", "--project-id", PROJECT_ID])
        self.assertEqual(ctx.exception.code, 2)
        self.assertNotIn("secret", err.getvalue())

    def test_cli_plan_apply_verify_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="c3-cli-") as workdir:
            plan_path = Path(workdir) / "closeout-plan.json"
            code, out, err = self._run_with_loader(self._plan_argv(plan_path))
            self.assertEqual(code, 0, err)
            self.assertTrue(plan_path.is_file())
            on_disk = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["schema"], closeout.PLAN_SCHEMA)
            self.assertEqual(on_disk["closeout_status"], "ready")
            self.assertNotIn(HUMAN_KEY, plan_path.read_text(encoding="utf-8"))

            code, out, err = self._run_with_loader(
                [
                    "apply",
                    "--plan",
                    str(plan_path),
                    "--host-scope",
                    HOST_SCOPE,
                    "--workspace-scope",
                    WORKSPACE_SCOPE,
                    "--key-env",
                    "C3_KEY",
                ]
            )
            self.assertEqual(code, 0, err)
            applied = json.loads(out)
            self.assertEqual(applied["schema"], closeout.RESULT_SCHEMA)
            self.assertEqual(applied["closeout_status"], "complete")

            code, out, err = self._run_with_loader(
                ["verify", "--plan", str(plan_path), "--key-env", "C3_KEY"]
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["closeout_status"], "verified")

    def _run_with_loader(self, argv):
        """CLI 默认 loader 会读本机真实配置；这里替换成合成只读边界。"""
        original = closeout._boundary

        def patched(**kwargs):
            kwargs["loader"] = confirmed_loader()
            kwargs["native_config_path"] = None
            kwargs["environ"] = None
            return original(**kwargs)

        out = io.StringIO()
        err = io.StringIO()
        with mock.patch.object(closeout, "_boundary", patched), \
                mock.patch.object(closeout, "_default_client", lambda server, timeout, **kwargs: self.client()), \
                mock.patch.dict(os.environ, {"C3_KEY": HUMAN_KEY}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = closeout.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_cli_plan_returns_one_when_blocked(self):
        code, _, _ = self._run_with_loader(
            [
                "plan",
                "--server",
                SERVER,
                "--project-id",
                EMPTY_PROJECT_ID,
                "--host-scope",
                HOST_SCOPE,
                "--workspace-scope",
                WORKSPACE_SCOPE,
                "--key-env",
                "C3_KEY",
            ]
        )
        self.assertEqual(code, 1)

    def test_cli_missing_credential_exits_two(self):
        err = io.StringIO()
        with mock.patch.object(closeout, "_default_client", lambda server, timeout, **kwargs: self.client()), \
                contextlib.redirect_stderr(err):
            code = closeout.main(
                [
                    "plan",
                    "--server",
                    SERVER,
                    "--project-id",
                    PROJECT_ID,
                    "--host-scope",
                    HOST_SCOPE,
                    "--workspace-scope",
                    WORKSPACE_SCOPE,
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("E_CREDENTIAL_SOURCE_MISSING", err.getvalue())

    def test_cli_rejects_key_file_inside_repo(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = closeout.main(
                ["verify", "--plan", str(PROJECT_ROOT / "absent.json"), "--key-file", str(PROJECT_ROOT / "config.toml")]
            )
        self.assertEqual(code, 2)
        self.assertIn("E_KEY_FILE_IN_REPO", err.getvalue())

    def test_cli_bad_json_exits_two(self):
        with tempfile.TemporaryDirectory(prefix="c3-cli-") as workdir:
            path = Path(workdir) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            err = io.StringIO()
            with mock.patch.object(closeout, "_default_client", lambda server, timeout, **kwargs: self.client()), \
                    mock.patch.dict(os.environ, {"C3_KEY": HUMAN_KEY}), \
                    contextlib.redirect_stderr(err):
                code = closeout.main(["verify", "--plan", str(path), "--key-env", "C3_KEY"])
            self.assertEqual(code, 2)
            self.assertLess(len(err.getvalue()), 200)

    def test_cli_bad_root_type_exits_two(self):
        with tempfile.TemporaryDirectory(prefix="c3-cli-") as workdir:
            path = Path(workdir) / "root.json"
            path.write_text("[]", encoding="utf-8")
            err = io.StringIO()
            with mock.patch.object(closeout, "_default_client", lambda server, timeout, **kwargs: self.client()), \
                    mock.patch.dict(os.environ, {"C3_KEY": HUMAN_KEY}), \
                    contextlib.redirect_stderr(err):
                code = closeout.main(["verify", "--plan", str(path), "--key-env", "C3_KEY"])
            self.assertEqual(code, 2)

    def test_cli_package_writes_application_without_credentials(self):
        with tempfile.TemporaryDirectory(prefix="c3-cli-") as workdir:
            plan_path = Path(workdir) / "closeout-plan.json"
            package_path = Path(workdir) / "application.json"
            code, _, err = self._run_with_loader(self._plan_argv(plan_path))
            self.assertEqual(code, 0, err)
            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = closeout.main(
                    ["package", "--plan", str(plan_path), "--out", str(package_path)]
                )
            self.assertEqual(code, 0, err)
            text = package_path.read_text(encoding="utf-8")
            package = json.loads(text)
            self.assertEqual(package["schema"], closeout.APPLICATION_SCHEMA)
            self.assertTrue(package["approval_required"])
            self.assertNotIn(HUMAN_KEY, text)
            self.assertNotIn("api_key", text)
            self.assertNotIn(str(PROJECT_ROOT), text)


class ApplicationPackageTests(CloseoutTestCase):
    def test_package_lists_expected_writes_commands_and_recovery(self):
        document, _ = self.ready_plan()
        package = closeout.build_application_package(document)
        self.assertEqual(package["schema"], closeout.APPLICATION_SCHEMA)
        self.assertEqual(package["expected_writes"]["total_writes"], 2)
        self.assertEqual(package["expected_writes"]["runner_create"], 1)
        self.assertEqual(package["expected_writes"]["binding_create"], 1)
        entry = package["expected_entries"][0]
        self.assertEqual(entry["runner_action"], "create")
        self.assertEqual(entry["binding_action"], "create")
        self.assertEqual(
            entry["planned_writes"],
            [
                "POST /api/runners",
                "PUT /api/projects/{project_id}/agents/{member_id}/binding",
            ],
        )
        for key in ("plan_read_only", "apply_human", "verify_read_only", "package_read_only"):
            self.assertIn(key, package["commands"])
            self.assertIn("scripts/adapter_closeout.py", package["commands"][key])
        self.assertIn("kimi_k28_executor.py closeout", package["commands"]["plan_read_only_k28_entry"])
        self.assertTrue(package["read_back_steps"])
        self.assertTrue(package["verify_steps"])
        self.assertTrue(package["recovery_steps"])
        self.assertTrue(package["approval_required"])
        self.assertEqual(package["excluded"][0], "凭据值")
        self.assertNotIn(HUMAN_KEY, blob_of(package))
        self.assertNotIn("api_key", blob_of(package))

    def test_package_carries_unconfigured_reasons_for_blocked_plan(self):
        document, _ = self.plan(loader=blocked_loader())
        package = closeout.build_application_package(document)
        self.assertTrue(package["unconfigured_reasons"])
        self.assertIn("E_CLOSEOUT_NATIVE_MISSING", blob_of(package["unconfigured_reasons"]))
        self.assertEqual(package["expected_writes"]["total_writes"], 0)

    def test_package_rejects_a_foreign_document(self):
        with self.assertRaises(closeout.CloseoutError) as ctx:
            closeout.build_application_package({"schema": "something-else"})
        self.assertEqual(ctx.exception.code, "E_CLOSEOUT_PACKAGE_UNAVAILABLE")

    def test_package_drops_unknown_nested_metadata(self):
        """F3：target/scope 的未知嵌套键必须白名单投影，不回原值。"""
        document, _ = self.ready_plan()
        canary = "sk-review-canary-hidden-76543210"
        for field in ("target", "scope", "native_source"):
            with self.subTest(field=field):
                bad = json.loads(blob_of(document))
                bad[field]["untrusted_nested"] = {"api_key": canary}
                package = closeout.build_application_package(bad)
                blob = blob_of(package)
                self.assertNotIn(canary, blob)
                self.assertNotIn("untrusted_nested", blob)

    def test_package_drops_credential_shaped_known_field(self):
        document, _ = self.ready_plan()
        canary = "sk-review-canary-hidden-76543210"
        bad = json.loads(blob_of(document))
        bad["target"]["member_id"] = canary
        package = closeout.build_application_package(bad)
        self.assertNotIn(canary, blob_of(package))
        self.assertNotIn("member_id", package["target"])

    def test_package_rejects_credential_shaped_plan_entry(self):
        document, _ = self.ready_plan()
        bad = json.loads(blob_of(document))
        bad["plan"]["entries"][0]["adapter"] = "sk-review-canary-hidden-76543210"
        with self.assertRaises(closeout.CloseoutError) as ctx:
            closeout.build_application_package(bad)
        self.assertEqual(ctx.exception.code, "E_CLOSEOUT_PACKAGE_UNAVAILABLE")

    def test_package_recomputes_writes_from_validated_plan_entries(self):
        """F3：summary 归零、proposed 清空都不改变真实写计数。"""
        document, _ = self.ready_plan()
        bad = json.loads(blob_of(document))
        for key in ("runner_create", "runner_update", "binding_create", "binding_update"):
            bad["plan"]["summary"][key] = 0
        bad["proposed"]["items"] = []
        bad["proposed"]["counts"] = {}
        package = closeout.build_application_package(bad)
        self.assertEqual(package["expected_writes"]["total_writes"], 2)
        self.assertEqual(package["expected_writes"]["runner_create"], 1)
        self.assertEqual(package["expected_writes"]["binding_create"], 1)
        self.assertEqual(len(package["expected_entries"]), 1)
        self.assertEqual(
            package["metadata_consistency"]["source_of_truth"], "plan.entries"
        )
        self.assertFalse(package["metadata_consistency"]["recorded_summary_matches"])
        self.assertTrue(
            package["metadata_consistency"]["display_metadata_is_not_write_authorization"]
        )
        result, client = self.apply(bad)
        self.assertEqual(result["closeout_status"], "complete")
        self.assertEqual(client.writes(), package["expected_writes"]["total_writes"])

    def test_package_commands_follow_scope_mode_and_never_emit_none(self):
        document, _ = self.ready_plan()
        package = closeout.build_application_package(document)
        plan_command = package["commands"]["plan_read_only"]
        apply_command = package["commands"]["apply_human"]
        self.assertIn(f"--host-scope {HOST_SCOPE}", plan_command)
        self.assertIn(f"--workspace-scope {WORKSPACE_SCOPE}", plan_command)
        self.assertIn(f"--workspace-scope {WORKSPACE_SCOPE}", apply_command)
        self.assertIn(f"--project-id {PROJECT_ID}", apply_command)
        self.assertNotIn("None", plan_command)
        self.assertNotIn("None", apply_command)
        self.assertIn("来源选择", package["commands"]["source_selection"])

    def test_package_commands_keep_host_shared_scope(self):
        document, _ = self.ready_plan(workspace=None, host_shared=True)
        package = closeout.build_application_package(document)
        for key in ("plan_read_only", "apply_human"):
            command = package["commands"][key]
            self.assertIn("--host-shared-runner", command)
            self.assertNotIn("--workspace-scope", command)
            self.assertNotIn("None", command)

    def test_package_carries_public_source_context_without_paths(self):
        document, _ = self.ready_plan()
        package = closeout.build_application_package(document)
        context = package["source_context"]
        self.assertEqual(context["status"], "confirmed")
        self.assertEqual(context["config_source"]["path_origin"], "explicit_argument")
        self.assertFalse(context["config_source"]["selector_forwarded_to_runtime"])
        blob = blob_of(package)
        self.assertNotIn("config_content_sha256", blob)
        self.assertNotIn(str(PROJECT_ROOT), blob)

    def test_package_short_error_for_plan_without_entries(self):
        with self.assertRaises(closeout.CloseoutError) as ctx:
            closeout.build_application_package({"schema": closeout.PLAN_SCHEMA})
        self.assertEqual(ctx.exception.code, "E_CLOSEOUT_PACKAGE_UNAVAILABLE")
        self.assertLess(len(str(ctx.exception)), 120)


# ---------------------------------------------------------------------------
# 隐私：canary 不回流
# ---------------------------------------------------------------------------


class PrivacyTests(CloseoutTestCase):
    def test_plan_does_not_leak_config_paths_or_credentials(self):
        with tempfile.TemporaryDirectory(prefix="c3-privacy-") as workdir:
            path = Path(workdir) / "config.toml"
            path.write_text(NATIVE_TOML, encoding="utf-8")
            loader = lambda: closeout.load_effective_native_source(  # noqa: E731
                config_path=str(path), environ={}
            )
            document, _ = self.plan(loader=loader)
            blob = blob_of(document)
            self.assertNotIn(str(path), blob)
            self.assertNotIn(str(path).replace("\\", "/"), blob)
        self.assertNotIn(CANARY_CREDENTIAL, blob)
        self.assertNotIn("api_key", blob)
        self.assertNotIn("config_content_sha256", blob)
        self.assertNotIn(CANARY_NESTED, blob)

    def test_blocked_plan_does_not_echo_raw_values(self):
        document, _ = self.plan(
            loader=confirmed_loader(make_config(provider=CANARY_CREDENTIAL))
        )
        blob = blob_of(document)
        self.assertNotIn(CANARY_CREDENTIAL, blob)
        self.assertNotIn(CANARY_NESTED, blob)

    def test_application_package_excludes_secrets_and_paths(self):
        document, _ = self.ready_plan()
        package = closeout.build_application_package(document)
        blob = blob_of(package)
        self.assertNotIn(HUMAN_KEY, blob)
        self.assertNotIn(AGENT_KEY, blob)
        self.assertNotIn("api_key", blob)
        self.assertIn("凭据值", package["excluded"])

    def test_apply_result_does_not_echo_credential(self):
        document, _ = self.ready_plan()
        result, _ = self.apply(document)
        self.assertNotIn(HUMAN_KEY, blob_of(result))

    def test_application_package_recursive_canary_not_leaked(self):
        """F3：产物/计划/CLI package 递归 canary 覆盖。"""
        document, _ = self.ready_plan()
        canary = "sk-review-canary-hidden-76543210"
        bad = json.loads(blob_of(document))
        bad["plan"]["entries"][0]["unexpected"] = {"api_key": canary}
        bad["plan"]["summary"]["note"] = canary
        bad["proposed"]["items"][0]["note"] = canary
        bad["limits"].append(canary)
        bad["native_source"]["blocked"] = [
            {"code": "E_CLOSEOUT_NATIVE_MISSING", "field": canary, "detail": canary}
        ]
        package = closeout.build_application_package(bad)
        self.assertNotIn(canary, blob_of(package))
        self.assertNotIn("api_key", blob_of(package))

    def test_bad_action_raises_stable_error(self):
        with self.assertRaises(closeout.CloseoutError) as ctx:
            closeout.run_closeout("frobnicate")
        self.assertEqual(ctx.exception.code, "E_CLOSEOUT_ACTION_INVALID")


# ---------------------------------------------------------------------------
# 导入隔离（子进程探针）
# ---------------------------------------------------------------------------

ISOLATION_SCRIPT = '''
import json
import os
import sys

for entry in (sys.argv[1], sys.argv[2]):
    if entry not in sys.path:
        sys.path.insert(0, entry)

# 先导入重依赖：钩子只统计本模块（adapter_closeout）导入与其后的主链路。
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
import talk_adapter_registry

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
    def get(self, key, *default):
        env_reads.append(key)
        return dict.get(self, key, *default)

    def __getitem__(self, key):
        env_reads.append(key)
        return dict.__getitem__(self, key)

    def __contains__(self, key):
        env_reads.append(key)
        return dict.__contains__(self, key)


os.environ = _SpyEnviron(_real_environ)

import adapter_closeout as closeout

import_env_reads = list(env_reads)
import_open_events = list(open_events)
del env_reads[:]
del open_events[:]
del io_events[:]

blocked = closeout.run_closeout(
    "plan",
    target={"server": "http://127.0.0.1:8000", "project_id": "prj_isolation",
            "member_id": "agent:kimi-code-k28-preview", "adapter": "agent:kimi-code-k28-preview"},
    host_scope="isolation-host",
    workspace_scope="isolation-ws",
    client=None,
    credential="synthetic",
)
record = closeout.native_source_record(status="blocked")
os.environ = _real_environ

print(json.dumps({
    "closeout_status": blocked["closeout_status"],
    "record_status": record["status"],
    "import_env_reads": import_env_reads,
    "import_open_events": import_open_events,
    "scenario_env_reads": list(env_reads),
    "scenario_open_events": list(open_events),
    "scenario_io_events": list(io_events),
    "server_main_imported": "server.main" in sys.modules,
    "bridges_imported": any(name.startswith("bridges") for name in sys.modules),
    "mcp_modules": sorted(
        name for name in sys.modules
        if name == "mcp" or name.startswith("mcp.")
        or "talk_task_tools" in name or "talk_delivery" in name
    ),
}))
'''


class ImportIsolationTests(unittest.TestCase):
    def _run_probe(self) -> dict:
        with tempfile.TemporaryDirectory(prefix="c3-isolation-") as workdir:
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

    def test_import_and_blocked_plan_have_no_side_effects(self):
        payload = self._run_probe()
        self.assertEqual(payload["closeout_status"], "blocked")
        self.assertEqual(payload["record_status"], "blocked")
        self.assertEqual(payload["import_env_reads"], [])
        self.assertEqual(payload["scenario_env_reads"], [])
        self.assertEqual(payload["scenario_open_events"], [])
        self.assertEqual(payload["scenario_io_events"], [])
        repo = str(PROJECT_ROOT).replace("\\", "/")
        self.assertTrue(payload["import_open_events"])
        for path, mode in payload["import_open_events"]:
            normalized = path.replace("\\", "/")
            self.assertTrue(normalized.startswith(repo), normalized)
            if "__pycache__" in normalized:
                self.assertIn(mode, ("r", "wb"))
            else:
                self.assertEqual(mode, "r")

    def test_no_server_main_bridges_or_mcp_imported(self):
        payload = self._run_probe()
        self.assertFalse(payload["server_main_imported"])
        self.assertFalse(payload["bridges_imported"])
        self.assertEqual(payload["mcp_modules"], [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
