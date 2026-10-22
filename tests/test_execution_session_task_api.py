"""292 task API tests: strict metadata, base reference, state, compatibility."""

from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timezone
from pathlib import Path

from server.models import (
    Project,
    ProjectAgent,
    ProjectRoleBinding,
    RunnerRegistry,
)
from tests.test_support import RouteTestCase

PROJECT = "prj_292_api"
REQUESTER = "agent:codex"
TARGET = "agent:deepseek"
OTHER = "human:other"
BASE_TEXT = "这是固定基础介绍：项目背景、角色职责与固定规范只保存一次。"
BASE_SHA = hashlib.sha256(BASE_TEXT.encode("utf-8")).hexdigest()


class ExecutionSessionTaskApiTests(RouteTestCase):
    def test_codex_and_kimi_bindings_can_create_and_reference_base(self):
        with self.session() as session:
            runner=session.get(RunnerRegistry,'runner:api-dsh')
            runner.runtime='codex'
            binding=session.get(ProjectRoleBinding,(PROJECT,TARGET))
            binding.provider_id='openai'; binding.model_id='gpt-6.1-sol'; binding.model_alias='gpt-6.1-sol'
            session.add(runner);session.add(binding);session.commit()
        first=self._create(execution_session=self._base_request())
        self.assertEqual(first.status_code,201,first.text)
        self.assertEqual(first.json()['execution_session']['runtime'],'codex')
        follow=self._base_request(); follow.pop('base_context'); follow['base_task_id']=first.json()['id']
        second=self._create(execution_session=follow)
        self.assertEqual(second.status_code,201,second.text)
        self.assertEqual(second.json()['execution_session']['base_contract_sha256'],first.json()['execution_session']['base_contract_sha256'])
        with self.session() as session:
            runner=session.get(RunnerRegistry,'runner:api-dsh');runner.runtime='kimi-code'
            session.add(runner);session.commit()
        kimi=self._create(execution_session=self._base_request())
        self.assertEqual(kimi.status_code,201,kimi.text)
        self.assertEqual(kimi.json()['execution_session']['runtime'],'kimi-code')
        follow['base_task_id']=kimi.json()['id']
        continued=self._create(execution_session=follow)
        self.assertEqual(continued.status_code,201,continued.text)
        self.assertEqual(continued.json()['execution_session']['base_contract_sha256'],kimi.json()['execution_session']['base_contract_sha256'])

    def test_requirements_snapshot_is_private_and_changed_requirements_require_new_base(self):
        from server.models import AgentTask
        with self.session() as session:
            project=session.get(Project,PROJECT)
            project.development_requirements='当前要求 A'
            session.add(project);session.commit()
        first=self._create(execution_session=self._base_request()).json()
        base=self.client.get(f"/api/tasks/{first['id']}/execution-session-base",headers=self._headers()).json()
        self.assertEqual(base['base_context'].count('当前要求 A'),1)
        self.assertNotIn('execution_session_audit',first)
        with self.session() as session:
            saved=session.get(AgentTask,first['id'])
            self.assertEqual(saved.execution_session_audit['project_development_requirements'],'当前要求 A')
            project=session.get(Project,PROJECT)
            project.development_requirements='当前要求 B'
            session.add(project);session.commit()
        continuation=self._base_request()
        continuation.pop('base_context')
        continuation['base_task_id']=first['id']
        rejected=self._create(execution_session=continuation)
        self.assertEqual(rejected.status_code,422,rejected.text)
        with self.session() as session:
            self.assertEqual(session.get(AgentTask,first['id']).execution_session_audit['project_development_requirements'],'当前要求 A')

    def test_state_rejects_boolean_version_nested_text_and_nonfinite_values(self):
        from server.execution_session_tasks import normalize_execution_session_state, ExecutionSessionValidationError
        state={'schema':'talk-execution-session-state-1','version':1,'status':'failed','decision':'unconfirmed'}
        for change in ({'version':True},{'decision':{'body':'private'}},{'confirmed_count':True},
                       {'last_snapshot':{'used_tokens':float('nan')}}):
            with self.subTest(change=change), self.assertRaises(ExecutionSessionValidationError):
                normalize_execution_session_state({**state,**change})

    def setUp(self):
        super().setUp()
        self.add_member(REQUESTER, api_key="codex-key")
        self.add_member(TARGET, api_key="deepseek-key")
        self.add_member(OTHER, api_key="other-key")
        self.workspace = self._tmpdir / "workspace"
        self.workspace.mkdir()
        now = datetime.now(timezone.utc)
        with self.session() as session:
            session.add(
                Project(
                    project_id=PROJECT,
                    display_name="292 API",
                    project_root_path=str(self.workspace),
                    maintainer_member_id=REQUESTER,
                    created_at=now,
                    last_seen_at=now,
                )
            )
            session.add(
                ProjectAgent(
                    project_id=PROJECT,
                    member_id=TARGET,
                    business_role="dev",
                    decision_tier="execution",
                    capability_summary=[],
                    updated_at=now,
                )
            )
            session.add(
                RunnerRegistry(
                    runner_id="runner:api-dsh",
                    runtime="dsh",
                    display_name="API DSH",
                    adapter_status="adapted",
                    capabilities=[],
                    control_kind="managed_cli",
                    created_by=REQUESTER,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                ProjectRoleBinding(
                    project_id=PROJECT,
                    member_id=TARGET,
                    runner_id="runner:api-dsh",
                    model_source="builtin",
                    provider_id="deepseek-official",
                    connection_ref="isolated",
                    model_id="deepseek-flash",
                    model_alias="deepseek-flash",
                    model_display_name="DeepSeek Flash",
                    updated_by=REQUESTER,
                    updated_at=now,
                )
            )
            session.commit()
        self.client = self.make_client()

    def _headers(self, key: str = "codex-key") -> dict:
        return {"X-API-Key": key}

    def _create(
        self,
        *,
        content: str = "本次增量",
        execution_session=None,
        requester_key: str = "codex-key",
        target: str = TARGET,
        task_kind: str = "general",
    ):
        payload = {
            "target_member_id": target,
            "content": content,
            "title": "292",
            "project_id": PROJECT,
            "task_kind": task_kind,
        }
        if execution_session is not None:
            payload["execution_session"] = execution_session
        return self.client.post(
            "/api/tasks", headers=self._headers(requester_key), json=payload
        )

    def _base_request(self, **overrides):
        payload = {
            "schema": "talk-execution-session-request-1",
            "version": 1,
            "continuity_key": "api/feature/one",
            "base_context": BASE_TEXT,
        }
        payload.update(overrides)
        return payload

    def test_create_base_and_read_protected_contract(self):
        response = self._create(execution_session=self._base_request())
        self.assertEqual(response.status_code, 201, response.text)
        task = response.json()
        self.assertEqual(task["execution_session"]["base_contract_sha256"], BASE_SHA)
        self.assertNotIn("base_context", task["execution_session"])
        self.assertIsNone(task["execution_session_state"])

        base = self.client.get(
            f"/api/tasks/{task['id']}/execution-session-base",
            headers=self._headers(),
        )
        self.assertEqual(base.status_code, 200, base.text)
        body = base.json()
        self.assertEqual(body["base_context"], BASE_TEXT)
        self.assertEqual(body["base_contract_sha256"], BASE_SHA)
        self.assertEqual(body["continuity_key"], "api/feature/one")

        forbidden = self.client.get(
            f"/api/tasks/{task['id']}/execution-session-base",
            headers=self._headers("other-key"),
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_continuation_uses_base_reference_without_duplicate_text(self):
        first = self._create(execution_session=self._base_request()).json()
        continuation = self._create(
            content="第二轮增量",
            execution_session={
                "schema": "talk-execution-session-request-1",
                "version": 1,
                "continuity_key": "api/feature/one",
                "base_task_id": first["id"],
            },
        )
        self.assertEqual(continuation.status_code, 201, continuation.text)
        task = continuation.json()
        meta = task["execution_session"]
        self.assertEqual(meta["base_task_id"], first["id"])
        self.assertEqual(meta["base_contract_sha256"], BASE_SHA)
        self.assertNotIn("base_context", meta)

        base = self.client.get(
            f"/api/tasks/{task['id']}/execution-session-base",
            headers=self._headers("deepseek-key"),
        )
        self.assertEqual(base.status_code, 200)
        self.assertEqual(base.json()["base_context"], BASE_TEXT)

    def test_strict_rejections_do_not_create_tasks(self):
        cases = [
            self._create(
                execution_session={
                    "schema": "talk-execution-session-request-1",
                    "version": 1,
                    "continuity_key": "api/feature/one",
                }
            ),
            self._create(
                execution_session=self._base_request(extra="x"),
            ),
            self._create(
                execution_session=self._base_request(force_new="yes"),
            ),
            self._create(
                execution_session=self._base_request(base_task_id=1, base_context=BASE_TEXT),
            ),
            self._create(execution_session=self._base_request(task_kind="review")),
        ]
        for response in cases:
            self.assertEqual(response.status_code, 422, response.text)
        with self.session() as session:
            count = session.execute(
                __import__("sqlalchemy").text("SELECT COUNT(*) FROM agent_tasks")
            ).scalar()
        self.assertEqual(int(count), 0)

    def test_cross_requester_and_non_base_reference_are_rejected(self):
        first = self._create(execution_session=self._base_request()).json()
        second = self._create(
            content="second",
            execution_session={
                "schema": "talk-execution-session-request-1",
                "version": 1,
                "continuity_key": "api/feature/one",
                "base_task_id": first["id"],
            },
        ).json()
        cross_requester = self._create(
            execution_session={
                "schema": "talk-execution-session-request-1",
                "version": 1,
                "continuity_key": "api/feature/one",
                "base_task_id": first["id"],
            },
            requester_key="other-key",
        )
        self.assertEqual(cross_requester.status_code, 422)
        non_base = self._create(
            execution_session={
                "schema": "talk-execution-session-request-1",
                "version": 1,
                "continuity_key": "api/feature/one",
                "base_task_id": second["id"],
            }
        )
        self.assertEqual(non_base.status_code, 422)

    def test_complete_state_is_validated_and_queryable(self):
        task = self._create(execution_session=self._base_request()).json()
        claim = self.client.post(
            f"/api/tasks/{task['id']}/claim",
            headers=self._headers("deepseek-key"),
            json={"instance_id": None, "lease_seconds": 60},
        )
        self.assertEqual(claim.status_code, 200, claim.text)
        token = claim.json()["claim_token"]
        state = {
            "schema": "talk-execution-session-state-1",
            "version": 1,
            "status": "completed",
            "decision": "new_no_candidate",
            "native_session_id": "session-11111111-1111-4111-8111-111111111111",
            "confirmed_count": 1,
            "task_id": task["id"],
            "attempt": 1,
            "execution_id": "exec-x",
            "base_contract_version": "1",
            "base_contract_sha256": BASE_SHA,
            "limitations": "no body/credentials",
        }
        completed = self.client.post(
            f"/api/tasks/{task['id']}/complete",
            headers=self._headers("deepseek-key"),
            json={
                "status": "succeeded",
                "result_message_id": None,
                "claim_token": token,
                "execution_session_state": state,
            },
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["execution_session_state"]["decision"], "new_no_candidate")
        fetched = self.client.get(
            f"/api/tasks/{task['id']}", headers=self._headers()
        ).json()
        self.assertEqual(fetched["execution_session_state"]["confirmed_count"], 1)

        # Unknown state keys and state on a non-execution task are rejected.
        second = self._create(execution_session=self._base_request()).json()
        claim2 = self.client.post(
            f"/api/tasks/{second['id']}/claim",
            headers=self._headers("deepseek-key"),
            json={"instance_id": None, "lease_seconds": 60},
        ).json()
        bad = self.client.post(
            f"/api/tasks/{second['id']}/complete",
            headers=self._headers("deepseek-key"),
            json={
                "status": "succeeded",
                "claim_token": claim2["claim_token"],
                "execution_session_state": {**state, "body": "secret"},
            },
        )
        self.assertEqual(bad.status_code, 422, bad.text)

        plain = self._create(content="old style").json()
        claim3 = self.client.post(
            f"/api/tasks/{plain['id']}/claim",
            headers=self._headers("deepseek-key"),
            json={"instance_id": None, "lease_seconds": 60},
        ).json()
        not_allowed = self.client.post(
            f"/api/tasks/{plain['id']}/complete",
            headers=self._headers("deepseek-key"),
            json={
                "status": "succeeded",
                "claim_token": claim3["claim_token"],
                "execution_session_state": state,
            },
        )
        self.assertEqual(not_allowed.status_code, 422, not_allowed.text)

    def test_old_task_without_metadata_is_compatible(self):
        response = self._create(content="旧任务行为")
        self.assertEqual(response.status_code, 201)
        task = response.json()
        self.assertIsNone(task["execution_session"])
        self.assertIsNone(task["execution_session_state"])
        missing = self.client.get(
            f"/api/tasks/{task['id']}/execution-session-base",
            headers=self._headers(),
        )
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
