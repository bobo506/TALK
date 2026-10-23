"""Kimi 共用适配自检：真实格式解析、计数规则、角色/模型/投递隔离。"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bridges.kimi_execution_native import KimiNative, KimiNativeError, LaunchSpec, read_session, text_digest, resolve_launch
from bridges.kimi_execution_channel import run_execution_session_task
from bridges.dsh_execution_channel import ExecutionSessionRunError, _workspace_identity
from bridges.execution_session_store import ExecutionSessionStore, StoreConflict


class FakeNative:
    def __init__(self, root):
        self.root, self.home = root, root / "home"
        self.home.mkdir()
        self.spec = LaunchSpec([], {}, self.home, "kimi-code/k3", "k3", "managed:kimi-code", 100000,
            "controlled", "fixed system", (), "f" * 64, "e" * 64)
        self.fingerprint = self.spec.fingerprint
        self.last_session_id = None
        self.used = 69900
        self.missing = self.fail_before = self.fail_after = self.cancel = self.foreign = False
        self.age = 0
        self.directives = []

    async def open(self): pass
    async def close(self): pass

    def directory(self, sid):
        return self.home / "sessions/wd_test" / sid

    def append(self, sid, kind, **kw):
        p = self.directory(sid) / "agents/main/wire.jsonl"
        with p.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"type": kind, "time": int((datetime.now(timezone.utc) - timedelta(seconds=self.age)).timestamp() * 1000), **kw}) + "\n")

    def create(self):
        sid = "session_" + str(uuid.uuid4())
        d = self.directory(sid)
        (d / "agents/main").mkdir(parents=True)
        (d / "state.json").write_text(json.dumps({"id": sid, "version": 2, "cwd": str(self.root),
            "archived": False, "lastTurnReason": "completed", "agents": {"main": {"homedir": str(d / "agents/main"), "type": "main"}}}), encoding="utf-8")
        self.append(sid, "metadata", protocol_version="1.5")
        self.append(sid, "profile.bind", agentId="main", profileName="controlled", modelAlias=self.spec.alias,
            systemPrompt="fixed system", activeToolNames=[], disallowedTools=[], subagents=[])
        return sid

    def snapshot(self, sid):
        return read_session(self.directory(sid), self.spec, self.root)

    async def query(self, sid): return self.snapshot(sid)

    async def deliver(self, sid, text, timeout, *, expected_sha256):
        if self.fail_before:
            raise KimiNativeError("test_failure_before")
        if sid is None:
            sid = self.create()
        elif self.snapshot(sid)[0]["native_sha256"] != expected_sha256:
            raise KimiNativeError("kimi_native_history_changed")
        self.last_session_id = sid
        self.directives.append((sid, text))
        self.user(sid, text)
        if self.foreign: self.user(sid, "foreign writer")
        # Injection/tool records must not be counted as user submissions.
        self.append(sid, "context.append_message", agentId="main", message={"role": "user", "origin": {"kind": "injection"}, "content": [{"type": "text", "text": "system reminder"}]})
        self.append(sid, "llm.request", agentId="main", modelAlias=self.spec.alias, model=self.spec.model, maxTokens=99999999)
        if not self.missing:
            self.append(sid, "token_counting.turn_recorded", agentId="main", tokens=self.used)
        if self.cancel: raise asyncio.CancelledError()
        if self.fail_after: raise KimiNativeError("test_failure_after")
        return {"status": "completed", "reply": "ok", "rerouted": False}

    def user(self, sid, text):
        mid = "msg_" + uuid.uuid4().hex
        parts = [{"type": "text", "text": text}]
        self.append(sid, "turn.prompt", agentId="main", promptId=mid, input=parts, origin={"kind": "user"})
        self.append(sid, "context.append_message", agentId="main", message={"id": mid, "role": "user", "content": parts, "origin": {"kind": "user"}})


class KimiExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.native = FakeNative(self.root)
        self.store_path = self.root / "state.sqlite3"
        self.base_text = "fixed base secret: BASEROOT"
        self.binding = {"state": "bound", "runtime": "kimi-code", "runner_id": "runner:kimi",
            "provider_id": "managed:kimi-code", "model_id": "k3", "model_alias": "kimi-code/k3", "binding_fingerprint": "a" * 64}
        self.member = "agent:kimi"
        self.line = "kimi:test"

    async def asyncTearDown(self): self.temp.cleanup()

    async def get_execution_session_base(self, task_id):
        return {"task_id": 1, "continuity_key": self.line, "project_id": "project:test",
            "requester_id": "agent:lead", "target_member_id": self.member,
            "binding_fingerprint": self.binding["binding_fingerprint"], "workspace_root": str(self.root),
            "workspace_identity": _workspace_identity(self.root), "base_contract_version": "1",
            "base_contract_sha256": text_digest(self.base_text), "base_context": self.base_text}

    def task(self, task_id, force=False):
        return {"id": task_id, "attempt": 1, "project_id": "project:test", "task_kind": "general",
            "created_by": "agent:lead", "target_member_id": self.member, "content": "increment " + str(task_id),
            "target_binding_snapshot": copy.deepcopy(self.binding),
            "execution_session": {"schema": "talk-execution-session-request-1", "version": 1,
                "project_id": "project:test", "target_member_id": self.member, "requester_id": "agent:lead",
                "continuity_key": self.line, "runtime": "kimi-code", "binding_fingerprint": self.binding["binding_fingerprint"],
                "workspace_root": str(self.root), "workspace_identity": _workspace_identity(self.root),
                "base_contract_version": "1", "base_contract_sha256": text_digest(self.base_text),
                "base_task_id": None if task_id == 1 else 1, "force_new": force}}

    async def run_task(self, task_id, force=False, task=None):
        return await run_execution_session_task(task=task or self.task(task_id, force), client=self,
            member_id=self.member, workdir=self.root, command=[], timeout=10, launch_id="launch:test",
            project_id="project:test", binding_snapshot=self.binding, runner=self.native, store_override=str(self.store_path))

    async def test_same_window_increment_and_force_new_restore(self):
        first, second = await self.run_task(1), await self.run_task(2)
        self.assertEqual(first.state["native_session_id"], second.state["native_session_id"])
        self.assertEqual(second.state["confirmed_count"], 2)
        self.assertNotIn(self.base_text, self.native.directives[1][1])
        third = await self.run_task(3, force=True)
        self.assertNotEqual(first.state["native_session_id"], third.state["native_session_id"])
        self.assertIn(self.base_text, self.native.directives[2][1])
        self.assertEqual(third.state["confirmed_count"], 1)

    async def test_threshold_exact_and_below(self):
        first = await self.run_task(1)
        below = await self.run_task(2)
        self.assertTrue(below.state["reused"])
        self.native.used = 70000
        third = await self.run_task(3)
        fourth = await self.run_task(4)
        self.assertEqual(third.state["native_session_id"], first.state["native_session_id"])
        self.assertNotEqual(fourth.state["native_session_id"], third.state["native_session_id"])
        self.assertEqual(fourth.state["confirmed_count"], 1)

    async def test_known_low_ignores_ten_round_limit(self):
        for i in range(1, 13):
            result = await self.run_task(i)
        self.assertEqual(result.state["confirmed_count"], 12)

    async def test_missing_only_ten_then_eleventh_new(self):
        self.native.missing = True
        first = await self.run_task(1)
        for i in range(2, 11):
            result = await self.run_task(i)
            self.assertEqual(first.state["native_session_id"], result.state["native_session_id"])
            self.assertEqual(result.state["confirmed_count"], i)
        new = await self.run_task(11)
        self.assertNotEqual(new.state["native_session_id"], first.state["native_session_id"])
        self.assertEqual(new.state["confirmed_count"], 1)

    async def test_recovered_measurement_does_not_reset_count(self):
        self.native.missing = True
        await self.run_task(1)
        await self.run_task(2)
        self.native.missing = False
        result = await self.run_task(3)
        self.assertEqual(result.state["confirmed_count"], 3)
        self.assertFalse(result.state["last_snapshot"]["used_tokens"] is None)

    async def test_aged_metric_uses_trusted_count(self):
        self.native.age = 22000
        await self.run_task(1)
        result = await self.run_task(2)
        self.assertTrue(result.state["reused"])
        self.assertEqual(result.state["confirmed_count"], 2)

    async def test_invalid_metric_must_not_use_ten_fallback(self):
        self.native.used = -1
        first = await self.run_task(1)
        second = await self.run_task(2)
        self.assertFalse(second.state["reused"])
        self.assertNotEqual(first.state["native_session_id"], second.state["native_session_id"])

    async def test_new_attempt_reserved_before_failure_and_not_replayed(self):
        self.native.fail_before = True
        with self.assertRaises(ExecutionSessionRunError): await self.run_task(1)
        self.assertIsNotNone(ExecutionSessionStore(self.store_path).get_attempt(1, 1))
        self.native.fail_before = False
        with self.assertRaisesRegex(ExecutionSessionRunError, "task_attempt_already_started"):
            await self.run_task(1)
        self.assertEqual(self.native.directives, [])

    async def test_model_failure_after_delivery_still_counts_and_taints(self):
        self.native.fail_after = True
        result = await self.run_task(1)
        self.assertEqual(result.state["confirmed_count"], 1)
        self.assertEqual(result.completion_status, "failed")
        self.assertEqual(result.state["window_status"], "tainted")
        self.assertEqual(ExecutionSessionStore(self.store_path).get_attempt(1, 1)["state"], "confirmed")

    async def test_cancel_after_delivery_counts_and_releases_channel(self):
        self.native.cancel = True
        with self.assertRaises(asyncio.CancelledError): await self.run_task(1)
        self.assertEqual(ExecutionSessionStore(self.store_path).get_attempt(1, 1)["state"], "confirmed")
        self.native.cancel = False
        next_result = await self.run_task(2)
        self.assertEqual(next_result.state["confirmed_count"], 1)

    async def test_foreign_user_taints_without_counting_extra_submission(self):
        await self.run_task(1)
        self.native.foreign = True
        result = await self.run_task(2)
        self.assertEqual(result.state["confirmed_count"], 2)
        self.assertEqual(result.state["window_status"], "tainted")
        self.assertEqual(result.completion_status, "failed")

    async def test_models_and_roles_never_share_native_window(self):
        first = await self.run_task(1)
        self.member = "agent:kimi-k28"
        self.binding.update(model_id="kimi-for-coding", model_alias="kimi-code/kimi-for-coding", binding_fingerprint="b" * 64)
        self.native.spec.alias, self.native.spec.model = "kimi-code/kimi-for-coding", "kimi-for-coding"
        second = await self.run_task(2)
        self.assertNotEqual(first.state["native_session_id"], second.state["native_session_id"])
        self.assertEqual(second.state["confirmed_count"], 1)

    async def test_changed_line_is_new_and_changed_identity_is_rejected(self):
        first = await self.run_task(1)
        self.line = "other:line"
        second = await self.run_task(2)
        self.assertNotEqual(first.state["native_session_id"], second.state["native_session_id"])
        task = self.task(3)
        task["created_by"] = "human:other"
        with self.assertRaisesRegex(ExecutionSessionRunError, "identity_mismatch"):
            await self.run_task(3, task=task)

    async def test_history_changed_between_tasks_is_not_reused(self):
        first = await self.run_task(1)
        self.native.user(first.state["native_session_id"], "outside submission")
        second = await self.run_task(2)
        self.assertFalse(second.state["reused"])

    async def test_native_permission_or_model_drift_rejected(self):
        first = await self.run_task(1)
        sid = first.state["native_session_id"]
        self.native.append(sid, "config.update", agentId="main", modelAlias="other-model")
        with self.assertRaisesRegex(KimiNativeError, "profile_changed"):
            self.native.snapshot(sid)
        second = await self.run_task(2)
        self.assertFalse(second.state["reused"])

    async def test_duplicate_delivery_and_pending_binding_are_one_time(self):
        await self.run_task(1)
        with self.assertRaisesRegex(ExecutionSessionRunError, "task_attempt_already_started"):
            await self.run_task(1)
        self.assertEqual(len(self.native.directives), 1)

    async def test_output_budget_never_used_as_context_capacity(self):
        first = await self.run_task(1)
        self.assertEqual(first.state["last_snapshot"]["context_window"], 100000)
        self.assertEqual(first.state["last_snapshot"]["used_tokens"], 69900)

    async def test_missing_capacity_fallback_and_corrupt_time_new_window(self):
        self.native.spec.capacity = None
        first = await self.run_task(1)
        result = await self.run_task(2)
        self.assertTrue(result.state["reused"])
        self.native.append(result.state["native_session_id"], "token_counting.turn_recorded", agentId="main", tokens=True)
        third = await self.run_task(3)
        self.assertNotEqual(first.state["native_session_id"], third.state["native_session_id"])

    async def test_native_failure_return_still_taints_counted_window(self):
        original = self.native.deliver
        async def failed(*args, **kwargs):
            result = await original(*args, **kwargs)
            result['status'] = 'failed'
            return result
        self.native.deliver = failed
        result = await self.run_task(1)
        self.assertEqual(result.state['confirmed_count'], 1)
        self.assertEqual(result.state['window_status'], 'tainted')

    async def test_sidecar_receipt_omits_assistant_body(self):
        original=self.native.deliver
        async def response(*args,**kwargs):
            result=await original(*args,**kwargs)
            result['reply']='PRIVATE_ASSISTANT_BODY_CANARY'
            return result
        self.native.deliver=response
        result=await self.run_task(1)
        self.assertEqual(result.reply,'PRIVATE_ASSISTANT_BODY_CANARY')
        store=ExecutionSessionStore(self.store_path)
        with store._read() as conn:
            ack=conn.execute('SELECT ack_json FROM deliveries').fetchone()[0]
        self.assertNotIn('PRIVATE_ASSISTANT_BODY_CANARY',ack)

    async def test_dual_delivery_proof_rejects_missing_or_changed_message(self):
        first = await self.run_task(1)
        directory = self.native.directory(first.state['native_session_id'])
        wire = directory / 'agents/main/wire.jsonl'
        original = wire.read_text(encoding='utf-8')
        rows = [json.loads(line) for line in original.splitlines()]
        for change in ('missing', 'changed'):
            altered = copy.deepcopy(rows)
            row = next(r for r in altered if r['type'] == 'context.append_message' and r['message'].get('id'))
            if change == 'missing': altered.remove(row)
            else: row['message']['content'][0]['text'] = 'another directive'
            wire.write_text('\n'.join(json.dumps(r) for r in altered) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(KimiNativeError, 'delivery_ambiguous'):
                self.native.snapshot(first.state['native_session_id'])
        wire.write_text(original, encoding='utf-8')

    async def test_unknown_wire_version_future_metrics_and_tool_drift(self):
        first = await self.run_task(1)
        sid = first.state['native_session_id']
        self.native.append(sid, 'token_counting.turn_recorded', agentId='main', tokens=1,
            time=int((datetime.now(timezone.utc)+timedelta(seconds=1)).timestamp()*1000))
        self.assertTrue(self.native.snapshot(sid)[0]['metrics_invalid'])
        self.native.append(sid, 'tools.set_active_tools', agentId='main', names=['Bash'])
        with self.assertRaisesRegex(KimiNativeError, 'profile_changed'):
            self.native.snapshot(sid)

    async def test_one_time_pending_bind_and_cross_channel_cannot_bind(self):
        store = ExecutionSessionStore(self.store_path)
        key='project:test|agent:kimi|home:test|runner:kimi'
        scope={'project_id':'project:test','target_member_id':'agent:kimi','native_home_namespace':'home:test',
            'runner_id':'runner:kimi','continuity_key':'line:test','base_contract_version':'1','base_contract_sha256':'a'*64}
        store.acquire_channel(scope_key=key,owner_token='owner',owner_pid=os.getpid(),ttl_seconds=180)
        window=store.create_window(scope=scope,scope_fingerprint='scope',native_session_id=None,
            session_generation=1,base_task_id=1)
        store.reserve_attempt(task_id=1,attempt=1,execution_id='exec',body_sha256='a'*64,
            window_id=window['window_id'],native_session_id=None,channel_key=key,owner_token='owner')
        kwargs=dict(task_id=1,attempt=1,window_id=window['window_id'],execution_id='exec',
            native_session_id='session_'+str(uuid.uuid4()),channel_key=key,owner_token='owner')
        with self.assertRaises(StoreConflict):store.bind_pending_native_session(**{**kwargs,'owner_token':'other'})
        store.bind_pending_native_session(**kwargs)
        with self.assertRaises(StoreConflict):store.bind_pending_native_session(**kwargs)
        store.release_channel(scope_key=key,owner_token='owner')


class KimiLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.home=self.root/'home';self.home.mkdir()
        self.skills=self.root/'skills';self.skills.mkdir()
        self.exe=self.root/'kimi.exe';self.exe.touch()
        self.profile=self.root/'agent.md'
        self.profile.write_text('---\nname: controlled\ntools: []\nsubagents: []\n---\nfixed system\n',encoding='utf-8')
        self.config=self.home/'config.toml'
        self.config.write_text('[models."kimi-code/k3"]\nprovider="managed:kimi-code"\nmodel="k3"\nmax_context_size=100000\n',encoding='utf-8')
        self.binding={'model_alias':'kimi-code/k3','model_id':'k3','provider_id':'managed:kimi-code'}
        self.argv=[str(self.exe),'--model','kimi-code/k3','--output-format','stream-json',
            '--agent-file',str(self.profile),'--skills-dir',str(self.skills),'-p']

    def tearDown(self):self.temp.cleanup()

    def resolve(self, argv=None):
        from types import SimpleNamespace
        with patch.dict(os.environ,{'KIMI_CODE_HOME':str(self.home)},clear=True), patch(
            'bridges.kimi_execution_native.subprocess.run',return_value=SimpleNamespace(stdout='2.0.2\n')):
            return resolve_launch(argv or self.argv,self.root,self.binding)

    def test_native_alias_capacity_and_no_credential_hash_retention(self):
        self.config.write_text(self.config.read_text()+'api_key="one-private-secret"\n',encoding='utf-8')
        first=self.resolve()
        self.config.write_text(self.config.read_text().replace('one-private-secret','two-private-secret'),encoding='utf-8')
        second=self.resolve()
        self.assertEqual(first.capacity,100000)
        self.assertEqual(first.config_fingerprint,second.config_fingerprint)
        self.assertEqual(first.model,'k3')

    def test_unknown_command_and_duplicate_option_rejected(self):
        for flag in ('--continue','--auto','--session'):
            with self.assertRaises(KimiNativeError): self.resolve(self.argv[:-1]+[flag,'-p'])
        with self.assertRaises(KimiNativeError):self.resolve(self.argv[:-1]+['--model','kimi-code/k3','-p'])

    def test_binding_profile_and_project_config_fail_closed(self):
        self.binding['model_id']='other'
        with self.assertRaisesRegex(KimiNativeError,'binding_mismatch'):self.resolve()
        self.binding['model_id']='k3'
        self.profile.write_text('---\nname: controlled\ntools: [UnknownTool]\nsubagents: []\n---\nfixed system\n',encoding='utf-8')
        with self.assertRaisesRegex(KimiNativeError,'permissions_unsupported'):self.resolve()

    def test_nonempty_skills_and_changed_config_rejected(self):
        spec=self.resolve()
        native=KimiNative(spec,self.root)
        self.config.write_text(self.config.read_text().replace('100000','200000'),encoding='utf-8')
        with self.assertRaisesRegex(KimiNativeError,'config_changed'):native.snapshot('session_'+str(uuid.uuid4()))
        (self.skills/'unexpected.md').write_text('new instructions')
        with self.assertRaisesRegex(KimiNativeError,'profile_unusable'):self.resolve()


class KimiBridgeLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_entry_loads_base_and_enters_kimi_execution_branch(self):
        from bridges import cli_bridge
        from unittest.mock import AsyncMock
        task={'id':1,'execution_session':{'runtime':'kimi-code'},'created_by':'agent:lead'}
        class Client:
            async def claim_task(self,*args,**kwargs):return task
        handler=AsyncMock(return_value=True)
        base=AsyncMock(return_value={'text':'verified base'})
        prepare=AsyncMock(return_value=(task,'history',False))
        with patch('bridges.dsh_execution_channel._load_base_contract',base), patch(
            'bridges.cli_bridge._prepare_task_before_claim',prepare), patch(
            'bridges.cli_bridge._handle_execution_session_claimed',handler), patch(
            'bridges.cli_bridge._start_task_heartbeat',return_value=None):
            result=await cli_bridge.handle_queued_task(task,client=Client(),member_id='agent:kimi',
                workdir=Path.cwd(),instance_id='instance',command=['kimi'],timeout=1,max_reply_chars=1000,
                runtime='kimi-code',execution_context={'project_id':'project:test'})
        self.assertTrue(result)
        base.assert_awaited_once()
        handler.assert_awaited_once()
        self.assertEqual(prepare.await_args.kwargs['preflight_base_context'],'verified base')

    async def test_runtime_dispatch_preserves_task_lease_cancel(self):
        from bridges import cli_bridge
        started=asyncio.Event();canceled=asyncio.Event()
        async def run(**kwargs):
            started.set()
            try:await asyncio.sleep(10)
            finally:canceled.set()
        async def lease():
            await started.wait()
            raise cli_bridge.TaskLeaseLostError('test lease lost')
        heartbeat=asyncio.create_task(lease())
        with patch('bridges.kimi_execution_channel.run_execution_session_task',run), patch(
            'bridges.dsh_execution_channel.run_execution_session_task',side_effect=AssertionError('wrong runtime')):
            handled=await cli_bridge._handle_execution_session_claimed({'id':1,'execution_session':{'runtime':'kimi-code'}},
                client=object(),member_id='agent:kimi',workdir=Path.cwd(),command=['kimi'],timeout=1,
                max_reply_chars=1000,bridge_label='test',claim_token='test',heartbeat_task=heartbeat,
                execution_context={},diagnostics=None,replay_context='')
            self.assertFalse(handled)
        await asyncio.gather(heartbeat,return_exceptions=True)
        self.assertTrue(canceled.is_set())


if __name__ == "__main__": unittest.main()
