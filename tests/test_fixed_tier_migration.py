# -*- coding: utf-8 -*-
"""固定“决策/执行”分级迁移（R1-2 part C）的跨层反例测试。

本模块只证明一件事：旧 ``decision_tier`` / ``--decision-tier`` 字段与 argv 仍然
被接受，但**不再改变任何行为**。覆盖四层：

- ``bridges/cli_bridge.py``：prompt 文本、子进程环境、讨论收口；
- ``cli/talk.py``：``.talk/groups.yaml`` 的缺失/冲突/未知分级仍可加载；
- ``scripts/kimi_k28_executor.py``：contract / 离线检查 / 只读身份预检；
- ``scripts/adapter_closeout.py``：argv 公开证据与 plan/apply/verify。

同时确认移除分级门禁后，原有的真实安全门禁（项目绑定、成员身份、业务角色、
固定模型 alias）仍然拒绝对应错误输入。

全部离线：不调用真实模型、不访问生产服务、不写生产数据。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(PROJECT_ROOT), str(PROJECT_ROOT / "scripts")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import adapter_binding_facts as facts  # noqa: E402
import adapter_closeout as closeout  # noqa: E402
import kimi_k28_executor as k28  # noqa: E402
from bridges import cli_bridge  # noqa: E402
from cli import talk  # noqa: E402
from tests.test_adapter_closeout import CloseoutTestCase  # noqa: E402

TIER_VALUES = ("decision", "execution", None, "unknown-tier")

FIXTURE_CONFIG = """
default_model = "kimi-code/k3"

[providers."managed:kimi-code"]
type = "kimi"
base_url = "https://api.kimi.com/coding/v1"

[models."kimi-code/kimi-for-coding"]
provider = "managed:kimi-code"
model = "kimi-for-coding"
display_name = "K2.8 Preview"
capabilities = [ "thinking", "tool_use" ]

[models."kimi-code/k3"]
provider = "managed:kimi-code"
model = "k3"
display_name = "K3"
capabilities = [ "thinking", "tool_use" ]
"""


# ---------------------------------------------------------------------------
# A. cli_bridge：prompt / 环境 / 讨论收口
# ---------------------------------------------------------------------------


class CliBridgeTierMigrationTests(unittest.TestCase):
    def test_prompts_identical_and_free_of_fixed_tier_text(self):
        message = {
            "id": 9,
            "from": "human:qa",
            "content": "@agent:codex 请自查",
            "group_id": "group:lab",
        }
        task = {"id": 3, "created_by": "human:qa", "title": "T", "content": "C"}
        builders = {
            "message": lambda tier: cli_bridge.build_cli_prompt(
                message,
                member_id="agent:codex",
                workdir=Path("."),
                runtime="codex",
                decision_tier=tier,
            ),
            "task": lambda tier: cli_bridge.build_cli_task_prompt(
                task,
                member_id="agent:codex",
                workdir=Path("."),
                runtime="codex",
                decision_tier=tier,
            ),
            "preflight": lambda tier: cli_bridge.build_cli_task_preflight_prompt(
                task,
                member_id="agent:codex",
                workdir=Path("."),
                runtime="codex",
                decision_tier=tier,
            ),
        }
        for label, builder in builders.items():
            with self.subTest(builder=label):
                prompts = {str(tier): builder(tier) for tier in TIER_VALUES}
                self.assertEqual(len(set(prompts.values())), 1, prompts)
                for text in prompts.values():
                    self.assertNotIn("决策 Agent", text)
                    self.assertNotIn("执行 Agent", text)
                    self.assertNotIn("TALK_DECISION_TIER", text)

    def test_bridge_never_injects_talk_decision_tier_into_child_env(self):
        observed: dict[str, object] = {}

        class FakeClient:
            def __init__(self):
                self.replies = []

            async def get_group(self, group_id):
                return {
                    "type": "free",
                    "members": [
                        {"member_id": "human:qa"},
                        {"member_id": "agent:pi"},
                    ],
                }

            async def list_discussions(self, *, group_id=None):
                return []

            async def fetch_history(self, *, group_id=None, since=None, limit=50):
                return []

            async def reply(self, message_id, *, text, to=None, group_id=None):
                self.replies.append((message_id, text, to, group_id))
                return {"id": 100}

        async def fake_run_cli_command(command, prompt, *, cwd, timeout, prompt_transport="stdin"):
            observed["tier_env"] = os.environ.get("TALK_DECISION_TIER")
            observed["prompt"] = prompt
            return cli_bridge.CliRunResult(returncode=0, stdout="ok", stderr="")

        async def scenario():
            client = FakeClient()
            original = cli_bridge.run_cli_command
            cli_bridge.run_cli_command = fake_run_cli_command
            try:
                with mock.patch.dict(
                    os.environ,
                    {"TALK_DECISION_TIER": "decision"},
                    clear=False,
                ):
                    await cli_bridge.handle_incoming_message(
                        {
                            "id": 1,
                            "from": "human:qa",
                            "to": ["agent:pi"],
                            "group_id": "group:lab",
                            "type": "text",
                            "content": "@agent:pi 你好",
                        },
                        client=client,
                        member_id="agent:pi",
                        workdir=Path.cwd(),
                        command=["pi", "run"],
                        timeout=5,
                        max_reply_chars=100,
                        runtime="pi",
                        bridge_label="pi bridge",
                        decision_tier="decision",
                    )
            finally:
                cli_bridge.run_cli_command = original
            return client

        client = asyncio.run(scenario())

        self.assertIsNone(observed["tier_env"])
        self.assertNotIn("决策 Agent", str(observed["prompt"]))
        self.assertNotIn("执行 Agent", str(observed["prompt"]))
        self.assertNotIn("TALK_DECISION_TIER", str(observed["prompt"]))
        self.assertEqual(len(client.replies), 1)

    def test_configure_talk_tool_environment_clears_inherited_tier(self):
        args = SimpleNamespace(
            key="unit-key",
            base_url="http://127.0.0.1:9",
            project=None,
            decision_tier="decision",
        )
        with mock.patch.dict(os.environ, {"TALK_DECISION_TIER": "execution"}, clear=False):
            cli_bridge.configure_talk_tool_environment(args, "agent:pi")
            self.assertNotIn("TALK_DECISION_TIER", os.environ)

    def test_no_resolve_decision_tier_helper_remains(self):
        self.assertFalse(hasattr(cli_bridge, "resolve_decision_tier"))

    def test_parser_still_accepts_legacy_tier_flag(self):
        parser = cli_bridge.build_parser()
        plain = parser.parse_args(["--key", "k", "--command", "run"])
        self.assertIsNone(plain.decision_tier)
        for value in ("decision", "execution"):
            parsed = parser.parse_args(
                ["--key", "k", "--command", "run", "--decision-tier", value]
            )
            self.assertEqual(parsed.decision_tier, value)

    def test_discussion_closeout_uses_initiator_not_tier(self):
        class FakeClient:
            def __init__(self, requester: str):
                self.requester = requester
                self.updated = []

            async def get_discussion(self, discussion_id):
                return {"id": discussion_id, "requester_id": self.requester}

            async def list_discussion_turns(self, discussion_id):
                return []

            async def update_discussion(self, discussion_id, *, status, end_reason=None):
                self.updated.append((discussion_id, status, end_reason))

        async def close(requester: str, member_id: str):
            client = FakeClient(requester)
            await cli_bridge._resolve_if_discussion_initiator(
                client,
                discussion_id=5,
                group_id="group:lab",
                member_id=member_id,
                stance="decision",
            )
            return client.updated

        # 发起者本人收口；分级不再参与，任何成员名（含历史 decision 成员）都按发起者判定
        self.assertEqual(asyncio.run(close("agent:lead", "agent:lead")), [(5, "resolved", "consensus")])
        self.assertEqual(asyncio.run(close("agent:pi", "agent:lead")), [])
        self.assertEqual(asyncio.run(close("agent:lead", "agent:pi")), [])

    def test_disagreement_escalation_targets_human_not_tier_member(self):
        class FakeClient:
            def __init__(self):
                self.sent = []
                self.turns = [
                    {"speaker_id": "agent:a", "stance": "disagree"},
                    {"speaker_id": "agent:b", "stance": "disagree"},
                ]
                self.updated = []

            async def list_discussion_turns(self, discussion_id):
                return self.turns

            async def get_group(self, group_id):
                return {
                    "members": [
                        {"member_id": "human:bobo"},
                        {"member_id": "agent:lead", "decision_tier": "decision"},
                        {"member_id": "agent:b"},
                    ]
                }

            async def send_text(self, text, to=None, reply_to=None, group_id=None):
                self.sent.append((text, to))
                return {"id": 7}

            async def append_discussion_turn(self, *args, **kwargs):
                return {"id": 1}

            async def update_discussion(self, discussion_id, *, status, end_reason=None):
                self.updated.append((discussion_id, status, end_reason))

        async def scenario():
            client = FakeClient()
            await cli_bridge._maybe_escalate_disagreement(
                client,
                discussion_id=5,
                group_id="group:lab",
                reply_to=3,
            )
            return client

        client = asyncio.run(scenario())

        self.assertEqual([to for _text, to in client.sent], [["human:bobo"]])
        self.assertEqual(client.updated, [(5, "escalated", None)])


# ---------------------------------------------------------------------------
# B. cli/talk.py：groups.yaml 分级不再是行为来源
# ---------------------------------------------------------------------------


class GroupsYamlTierMigrationTests(unittest.TestCase):
    def _project(self, members: list[dict]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="talk-tier-groups-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        (root / ".talk" / "agents" / "agent_codex").mkdir(parents=True)
        (root / ".talk" / "groups.yaml").write_text(
            yaml.safe_dump(
                {"groups": [{"id": "group:a", "members": members}]},
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return root

    def test_missing_conflicting_and_unknown_tiers_all_load(self):
        cases = {
            "missing": [{"member_id": "agent:codex", "business_role": "dev"}],
            "unknown": [
                {"member_id": "agent:codex", "decision_tier": "legacy-unknown"}
            ],
            "conflicting": [
                {"member_id": "agent:codex", "decision_tier": "decision"},
                {"member_id": "agent:codex", "decision_tier": "execution"},
            ],
        }
        for label, members in cases.items():
            with self.subTest(case=label):
                root = self._project(members)
                entries = talk.scan_agents(root)
                self.assertEqual([e["member_id"] for e in entries], ["agent:codex"])

    def test_conflicting_tier_is_echo_only(self):
        root = self._project(
            [
                {
                    "member_id": "agent:codex",
                    "decision_tier": "decision",
                    "business_role": "lead",
                    "capabilities": ["a"],
                },
                {
                    "member_id": "agent:codex",
                    "decision_tier": "execution",
                    "business_role": "reviewer",
                    "capabilities": ["b"],
                },
            ]
        )

        entry = talk.scan_agents(root)[0]

        # 历史字段只回显首个声明值；业务角色/能力仍按原语义聚合
        self.assertEqual(entry["decision_tier"], "decision")
        self.assertEqual(entry["business_role"], "lead / reviewer")
        self.assertEqual(entry["capability_summary"], ["a", "b"])


# ---------------------------------------------------------------------------
# C. scripts/kimi_k28_executor.py：contract / 检查 / 身份预检
# ---------------------------------------------------------------------------


class K28TierMigrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-tier-k28-"))
        self.addCleanup(lambda: shutil.rmtree(self._tmp, ignore_errors=True))
        self.config_path = self._tmp / "config.toml"
        self.config_path.write_text(FIXTURE_CONFIG, encoding="utf-8")
        self.key_file = self._tmp / "outside-repo.key"

    def _run_check(self, **overrides):
        kwargs = {
            "project_root": PROJECT_ROOT,
            "kimi_config": self.config_path,
            "key_file": self.key_file,
            "environ": {},
        }
        kwargs.update(overrides)
        return k28.run_check(**kwargs)

    @staticmethod
    def _check_names(report: dict) -> list[str]:
        return sorted(check["name"] for check in report["checks"])

    def test_offline_check_identical_for_all_tier_inputs(self):
        baseline = self._run_check()
        self.assertTrue(baseline["ok"], baseline["problems"])
        baseline_names = self._check_names(baseline)
        self.assertNotIn("decision_tier_binding", baseline_names)

        for tier in TIER_VALUES:
            with self.subTest(decision_tier=tier):
                report = self._run_check(decision_tier=tier)
                self.assertEqual(report["ok"], baseline["ok"])
                self.assertEqual(self._check_names(report), baseline_names)

    def test_offline_check_identical_without_legacy_argv_flag(self):
        baseline = self._run_check()
        plain_argv = k28.build_bridge_argv(decision_tier=None)
        self.assertNotIn("--decision-tier", plain_argv)
        with mock.patch.object(k28, "build_bridge_argv", return_value=plain_argv):
            without_flag = self._run_check()
        self.assertEqual(without_flag["ok"], baseline["ok"])
        self.assertEqual(self._check_names(without_flag), self._check_names(baseline))

    def test_contract_has_no_tier_gate(self):
        contract = k28.build_contract(
            project_root=PROJECT_ROOT, kimi_config=self.config_path, environ={}
        )
        self.assertEqual(contract["runner"]["controlled_command"], k28.CONTROLLED_KIMI_COMMAND)
        # 历史字段可以保留，但不存在任何 gate 检查名
        rendered = json.dumps(contract, ensure_ascii=False)
        self.assertNotIn("decision_tier_binding", rendered)
        self.assertFalse(hasattr(k28, "resolve_argv_decision_tier"))

    def test_identity_preflight_ignores_tier_but_keeps_real_gates(self):
        def getter_for(roster):
            def _get(url, *, api_key, timeout):
                if url.endswith("/api/members/me"):
                    return {"id": k28.MEMBER_ID, "kind": "agent"}
                return roster

            return _get

        for tier in TIER_VALUES:
            with self.subTest(tier=tier):
                entry = {"member_id": k28.MEMBER_ID, "business_role": k28.BUSINESS_ROLE}
                if tier is not None:
                    entry["decision_tier"] = tier
                report = k28.identity_preflight(
                    base_url="http://127.0.0.1:9",
                    api_key="unit-key",
                    get_json=getter_for([entry]),
                )
                self.assertTrue(report["ok"], report["problems"])

        wrong_role = k28.identity_preflight(
            base_url="http://127.0.0.1:9",
            api_key="unit-key",
            get_json=getter_for(
                [{"member_id": k28.MEMBER_ID, "business_role": "reviewer"}]
            ),
        )
        self.assertFalse(wrong_role["ok"])

        wrong_member = k28.identity_preflight(
            base_url="http://127.0.0.1:9",
            api_key="unit-key",
            get_json=getter_for(
                [{"member_id": "agent:someone-else", "business_role": k28.BUSINESS_ROLE}]
            ),
        )
        self.assertFalse(wrong_member["ok"])

    def test_offline_check_still_rejects_wrong_project_binding(self):
        wrong = Path(tempfile.mkdtemp(prefix="talk-tier-wrong-project-"))
        self.addCleanup(lambda: shutil.rmtree(wrong, ignore_errors=True))
        (wrong / ".talk").mkdir(parents=True)
        (wrong / ".talk" / "project.yaml").write_text(
            "version: 1\nproject_id: prj_not_this_project\n", encoding="utf-8"
        )
        report = self._run_check(project_root=wrong)
        names = {check["name"]: check for check in report["checks"]}
        self.assertFalse(report["ok"])
        self.assertFalse(names["project_binding"]["ok"])

    def test_offline_check_still_rejects_alias_drift(self):
        self.config_path.write_text(
            'default_model = "kimi-code/k3"\n\n'
            '[models."kimi-code/k3"]\nprovider = "managed:kimi-code"\nmodel = "k3"\n'
            'capabilities = [ "tool_use" ]\n',
            encoding="utf-8",
        )
        report = self._run_check()
        names = {check["name"]: check for check in report["checks"]}
        self.assertFalse(report["ok"])
        self.assertFalse(names["native_model_alias"]["ok"])


# ---------------------------------------------------------------------------
# D. scripts/adapter_closeout.py：公开证据与 plan/apply/verify
# ---------------------------------------------------------------------------


class CloseoutTierMigrationTests(CloseoutTestCase):
    def test_argv_public_evidence_has_no_tier_keys(self):
        argv = k28.build_bridge_argv()
        argv[argv.index("--decision-tier") + 1] = "decision"
        with mock.patch.object(k28, "build_bridge_argv", return_value=argv):
            evidence = closeout.argv_selection_evidence(facts.K28_ADAPTER)

        self.assertEqual(evidence["status"], "ok")
        for key in ("decision_tier", "decision_tier_expected", "decision_tier_matches"):
            self.assertNotIn(key, evidence["public"])
            self.assertNotIn(key, closeout._NATIVE_ARGV_KEYS)

    def test_plan_apply_verify_ready_with_decision_tier_argv(self):
        argv = k28.build_bridge_argv()
        argv[argv.index("--decision-tier") + 1] = "decision"
        with mock.patch.object(k28, "build_bridge_argv", return_value=argv):
            document, _ = self.ready_plan()
            result, _ = self.apply(document)
            verified, _ = self.verify(document)

        self.assertEqual(result["closeout_status"], "complete", result)
        self.assertEqual(verified["closeout_status"], "verified", verified)

    def test_plan_apply_verify_ready_without_decision_tier_argv(self):
        plain = k28.build_bridge_argv()
        stripped = [
            item
            for index, item in enumerate(plain)
            if item != "--decision-tier"
            and (index == 0 or plain[index - 1] != "--decision-tier")
        ]
        self.assertNotIn("--decision-tier", stripped)
        with mock.patch.object(k28, "build_bridge_argv", return_value=stripped):
            document, _ = self.ready_plan()
            result, _ = self.apply(document)
            verified, _ = self.verify(document)

        self.assertEqual(result["closeout_status"], "complete", result)
        self.assertEqual(verified["closeout_status"], "verified", verified)

    def test_plan_argv_selection_identical_for_tier_variants(self):
        variants = []
        for tier in ("decision", "execution", None):
            if tier is None:
                argv = k28.build_bridge_argv(decision_tier=None)
            else:
                argv = k28.build_bridge_argv()
                argv[argv.index("--decision-tier") + 1] = tier
            with mock.patch.object(k28, "build_bridge_argv", return_value=argv):
                document, _ = self.plan()
            self.assertEqual(document["closeout_status"], "ready", document)
            variants.append(document["native_source"]["argv_selection"])

        self.assertEqual(variants[0], variants[1])
        self.assertEqual(variants[0], variants[2])
        self.assertNotIn("decision_tier", json.dumps(variants[0], ensure_ascii=False))

    def test_fixed_alias_mismatch_still_blocks_plan(self):
        with mock.patch.object(k28, "MODEL_ALIAS", "kimi-code/other-alias"):
            document, client = self.plan()
        self.assertEqual(document["closeout_status"], "blocked")
        self.assertEqual(client.writes(), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
