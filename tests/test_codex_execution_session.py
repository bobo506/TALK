"""Codex 会话适配自检：原生文件解析、共享规则、未知送达与重复调用。

测试仅使用独立 HOME/sidecar；假模型写真实格式 rollout，实际解析器负责
身份、最近用量和送达证明。实机原生证据另存，不把本测试称真实模型验收。
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import uuid
import os
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bridges.codex_execution_channel import run_execution_session_task
from bridges.codex_execution_native import CodexNative, CodexNativeError, LaunchSpec, canonical_path, read_rollout, resolve_launch, text_digest
from bridges.dsh_execution_channel import ExecutionSessionRunError, _workspace_identity
from bridges.execution_session_store import ExecutionSessionStore


class FakeNative:
    def __init__(self, root):
        self.home = root / "home"
        self.home.mkdir()
        self.root = root
        self.fingerprint = "f" * 64
        self.paths = {}
        self.used, self.capacity = 69900, 100000
        self.missing = False
        self.fail_before = self.fail_after = self.cancel = self.foreign = self.rerouted = False
        self.directives = []
        self.opens = 0
        self.age = 0

    async def open(self):
        self.opens += 1

    async def close(self):
        pass

    def append(self, sid, kind, payload):
        with self.paths[sid].open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"timestamp": (datetime.now(timezone.utc)-timedelta(seconds=self.age)).isoformat(),
                                    "type": kind, "payload": payload}, ensure_ascii=False) + "\n")

    async def create(self):
        sid = str(uuid.uuid4())
        path = self.home / "sessions" / ("rollout-" + sid + ".jsonl")
        path.parent.mkdir(exist_ok=True)
        path.write_text("", encoding="utf-8")
        self.paths[sid] = path
        self.append(sid, "session_meta", {"id": sid, "cwd": str(self.root), "model_provider": "openai", "cli_version": "0.163.0"})
        return sid

    def snapshot(self, sid):
        return read_rollout(self.paths[sid], home=self.home, session_id=sid, workdir=self.root,
                            model="gpt-6.1-sol", provider="openai")

    async def query(self, sid):
        return self.snapshot(sid)

    async def deliver(self, sid, text, timeout, *, expected_sha256):
        if self.snapshot(sid)[0]["native_sha256"] != expected_sha256:
            raise CodexNativeError("codex_native_history_changed")
        if self.fail_before:
            raise CodexNativeError("failure_before_delivery")
        self.directives.append((sid, text))
        self.append(sid, "turn_context", {"model": "gpt-6.1-sol"})
        self.append(sid, "event_msg", {"type": "item_completed", "thread_id": sid,
            "turn_id": str(uuid.uuid4()), "item": {"type": "UserMessage", "content": [{"type": "text", "text": text}]}})
        if self.foreign:
            self.append(sid, "event_msg", {"type": "item_completed", "thread_id": sid,
                "turn_id": str(uuid.uuid4()), "item": {"type": "UserMessage", "content": [{"type": "text", "text": "foreign writer"}]}})
        if not self.missing:
            self.append(sid, "event_msg", {"type": "token_count", "info": {
                "last_token_usage": {"total_tokens": self.used},
                "total_token_usage": {"total_tokens": 999999999},
                "model_context_window": self.capacity}})
        if self.cancel:
            raise asyncio.CancelledError()
        if self.fail_after:
            raise CodexNativeError("failure_after_delivery")
        return {"status": "completed", "reply": "ok", "rerouted": self.rerouted}


class CodexExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.native = FakeNative(self.root)
        self.store_path = self.root / "state.sqlite3"
        self.base_text = "基础介绍只在新原生会话投递。"
        self.base_sha = text_digest(self.base_text)
        self.binding = {"state": "bound", "runtime": "codex", "runner_id": "runner:codex",
                        "provider_id": "openai", "model_id": "gpt-6.1-sol", "binding_fingerprint": "a" * 64}

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def get_execution_session_base(self, task_id):
        return {"task_id": 1, "continuity_key": "codex:test", "project_id": "project:test",
                "requester_id": "agent:lead", "target_member_id": "agent:codex",
                "binding_fingerprint": "a" * 64, "workspace_root": str(self.root),
                "workspace_identity": _workspace_identity(self.root), "base_contract_version": "1",
                "base_contract_sha256": self.base_sha, "base_context": self.base_text}

    def task(self, task_id, force=False):
        return {"id": task_id, "attempt": 1, "project_id": "project:test", "task_kind": "general",
            "created_by": "agent:lead", "target_member_id": "agent:codex", "content": "增量" + str(task_id),
            "target_binding_snapshot": self.binding,
            "execution_session": {"schema": "talk-execution-session-request-1", "version": 1,
                "project_id": "project:test", "requester_id": "agent:lead", "target_member_id": "agent:codex",
                "runtime": "codex", "continuity_key": "codex:test", "force_new": force,
                "binding_fingerprint": "a" * 64, "workspace_root": str(self.root),
                "workspace_identity": _workspace_identity(self.root), "base_task_id": None if task_id == 1 else 1,
                "base_contract_version": "1", "base_contract_sha256": self.base_sha}}

    async def run_task(self, task_id, *, force=False, launch="launch:one"):
        return await run_execution_session_task(task=self.task(task_id, force), client=self, member_id="agent:codex",
            workdir=self.root, command=["test-only"], timeout=120, launch_id=launch,
            project_id="project:test", binding_snapshot=self.binding,
            store_override=str(self.store_path), runner=self.native)

    def count(self):
        with ExecutionSessionStore(self.store_path)._read() as conn:
            return conn.execute("SELECT coalesce(sum(counted),0) FROM deliveries").fetchone()[0]

    async def test_real_rollout_shape_first_full_then_incremental_and_force_new(self):
        first = await self.run_task(1)
        second = await self.run_task(2)
        self.assertEqual(first.state["native_session_id"], second.state["native_session_id"])
        self.assertTrue(second.state["reused"])
        self.assertEqual(second.state["confirmed_count"], 2)
        self.assertIn(self.base_text, self.native.directives[0][1])
        self.assertNotIn(self.base_text, self.native.directives[1][1])
        self.assertEqual(second.state["last_snapshot"]["used_tokens"], 69900)
        third = await self.run_task(3, force=True)
        self.assertNotEqual(first.state["native_session_id"], third.state["native_session_id"])
        self.assertEqual(third.state["confirmed_count"], 1)
        self.assertIn(self.base_text, self.native.directives[-1][1])

    async def test_699_then_70_rotates_next_task_not_during_turn(self):
        first = await self.run_task(1)
        self.native.used = 70000
        second = await self.run_task(2)
        self.assertEqual(first.state["native_session_id"], second.state["native_session_id"])
        third = await self.run_task(3)
        self.assertFalse(third.state["reused"])
        self.assertEqual(third.state["decision"], "new_context_threshold")

    async def test_missing_data_reuses_ten_rotates_eleventh(self):
        self.native.missing = True
        results = [await self.run_task(i) for i in range(1, 12)]
        self.assertTrue(all(x.state["native_session_id"] == results[0].state["native_session_id"] for x in results[:10]))
        self.assertEqual([x.state["confirmed_count"] for x in results[:10]], list(range(1, 11)))
        self.assertNotEqual(results[-1].state["native_session_id"], results[0].state["native_session_id"])
        self.assertEqual(results[-1].state["decision"], "new_fallback_exhausted")

    async def test_reliable_low_can_exceed_ten(self):
        results = [await self.run_task(i) for i in range(1, 13)]
        self.assertTrue(all(x.state["native_session_id"] == results[0].state["native_session_id"] for x in results))
        self.assertEqual(results[-1].state["confirmed_count"], 12)

    async def test_missing_then_recovery_does_not_clear_count(self):
        self.native.missing = True
        await self.run_task(1)
        self.native.missing = False
        second = await self.run_task(2)
        third = await self.run_task(3)
        self.assertEqual(second.state["confirmed_count"], 2)
        self.assertEqual(third.state["confirmed_count"], 3)
        self.assertEqual(third.state["context_status"], "known")

    async def test_duplicate_attempt_never_calls_model_twice(self):
        await self.run_task(1)
        with self.assertRaisesRegex(ExecutionSessionRunError, "task_attempt_already_started"):
            await self.run_task(1)
        self.assertEqual(len(self.native.directives), 1)

    async def test_failure_before_delivery_never_counts_or_reuses_unknown_window(self):
        self.native.fail_before = True
        with self.assertRaises(ExecutionSessionRunError):
            await self.run_task(1)
        self.assertEqual(self.count(), 0)
        self.native.fail_before = False
        result = await self.run_task(2)
        self.assertFalse(result.state["reused"])

    async def test_failure_after_delivery_counts_once_and_taints(self):
        self.native.fail_after = True
        result = await self.run_task(1)
        self.assertEqual(result.completion_status, "failed")
        self.assertEqual(result.state["confirmed_count"], 1)
        self.assertEqual(result.state["window_status"], "tainted")
        self.assertEqual(self.count(), 1)

    async def test_cancel_after_delivery_keeps_count_and_propagates(self):
        self.native.cancel = True
        with self.assertRaises(asyncio.CancelledError):
            await self.run_task(1)
        self.assertEqual(self.count(), 1)

    async def test_foreign_write_between_tasks_forces_new_window(self):
        first = await self.run_task(1)
        self.native.append(first.state["native_session_id"], "event_msg", {"type": "user_message", "message": "foreign"})
        second = await self.run_task(2)
        self.assertFalse(second.state["reused"])

    async def test_foreign_write_during_turn_is_failed_and_tainted(self):
        self.native.foreign = True
        result = await self.run_task(1)
        self.assertEqual(result.completion_status, "failed")
        self.assertEqual(result.state["window_status"], "tainted")

    async def test_launch_change_starts_new_window(self):
        first = await self.run_task(1)
        second = await self.run_task(2, launch="launch:other")
        self.assertNotEqual(first.state["native_session_id"], second.state["native_session_id"])

    async def test_expired_sample_uses_trusted_count_without_faking_source_time(self):
        self.native.age = 21601
        first = await self.run_task(1)
        second = await self.run_task(2)
        self.assertEqual(first.state["native_session_id"], second.state["native_session_id"])
        self.assertEqual(second.state["confirmed_count"], 2)
        self.assertEqual(second.state["context_status"], "unavailable")
        age=datetime.now(timezone.utc)-datetime.fromisoformat(second.state["last_snapshot"]["pressure_tokens_source_time"])
        self.assertGreater(age.total_seconds(),21600)

    async def test_invalid_metrics_cannot_use_ten_turn_fallback(self):
        first = await self.run_task(1)
        self.native.used = -1
        second = await self.run_task(2)
        self.assertEqual(second.state["confirmed_count"], 2)
        self.assertEqual(second.state["window_status"], "tainted")
        self.native.used = 100
        third = await self.run_task(3)
        self.assertFalse(third.state["reused"])
        self.assertNotEqual(first.state["native_session_id"], third.state["native_session_id"])

    async def test_native_instruction_seed_and_tools_are_not_counted_as_user_directives(self):
        sid=await self.native.create()
        self.native.append(sid,'response_item',{'role':'user','type':'message','content':[{'type':'input_text','text':'# AGENTS.md instructions and environment'}]})
        self.native.append(sid,'event_msg',{'type':'tool_result','body':'tool output'})
        before=self.native.snapshot(sid)[0]
        await self.native.deliver(sid,'formal directive',10,expected_sha256=before['native_sha256'])
        snapshot,users=self.native.snapshot(sid)
        self.assertEqual(len(users),1)
        self.assertEqual(users[0][1],text_digest('formal directive'))

    async def test_quota_only_notification_does_not_erase_reliable_usage(self):
        result=await self.run_task(1)
        sid=result.state['native_session_id']
        self.native.append(sid,'event_msg',{'type':'token_count','info':None})
        snapshot,_=self.native.snapshot(sid)
        self.assertEqual(snapshot['used_tokens'],69900)
        self.assertFalse(snapshot['metrics_missing'])

    async def test_wrong_native_model_or_path_is_rejected(self):
        sid=await self.native.create()
        self.native.append(sid,'turn_context',{'model':'another-model'})
        with self.assertRaisesRegex(CodexNativeError,'model_mismatch'):
            self.native.snapshot(sid)
        with self.assertRaisesRegex(CodexNativeError,'path_invalid'):
            read_rollout(self.root/'outside.jsonl',home=self.native.home,session_id=sid,
                         workdir=self.root,model='gpt-6.1-sol',provider='openai')

    async def test_fingerprint_ignores_per_task_snapshot_time(self):
        executable=self.root/'codex.exe';executable.write_bytes(b'test-only')
        command=[str(executable),'-a','never','--strict-config','exec','--model','gpt-6.1-sol',
                 '--sandbox','read-only','-c','model_reasoning_effort="xhigh"','-']
        with patch.dict(os.environ,{'CODEX_HOME':str(self.native.home)}),patch('bridges.codex_execution_native.subprocess.run',return_value=SimpleNamespace(stdout='codex-cli 0.163.0\n')):
            one=resolve_launch(command,self.root,{**self.binding,'captured_at':'first'})
            two=resolve_launch(command,self.root,{**self.binding,'captured_at':'second'})
            self.assertEqual(one.fingerprint,two.fingerprint)


class ResumeMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.fake=FakeNative(self.root);self.sid=await self.fake.create()
        self.settings={'model':'gpt-6.1-sol','cwd':str(self.root),'model_provider_id':'openai','reasoning_effort':'xhigh'}
        self.fake.append(self.sid,'event_msg',{'type':'thread_settings_applied','thread_id':self.sid,'thread_settings':self.settings})
        spec=LaunchSpec([],{},self.fake.home,'gpt-6.1-sol','openai','xhigh','read-only','never','f'*64)
        self.native=CodexNative(spec,self.root);self.native._paths[self.sid]=self.fake.paths[self.sid]
        self.started=0

    async def asyncTearDown(self):
        self.temp.cleanup()

    def rpc(self,mode):
        async def call(method,params,timeout=30):
            if method=='thread/resume':
                if mode=='foreign':self.fake.append(self.sid,'event_msg',{'type':'user_message','message':'foreign'})
                settings={**self.settings,'model':'foreign-model'} if mode=='changed' else self.settings
                self.fake.append(self.sid,'event_msg',{'type':'thread_settings_applied','thread_id':self.sid,'thread_settings':settings})
                path=str(self.fake.paths[self.sid])
                if os.name=='nt':path='\\\\?\\'+path
                return {'thread':{'id':self.sid,'cwd':str(self.root),'modelProvider':'openai','ephemeral':False,'path':path},
                        'model':'gpt-6.1-sol','reasoningEffort':'xhigh','approvalPolicy':'never','sandbox':{'type':'readOnly','networkAccess':False}}
            self.assertEqual(method,'turn/start');self.started+=1
            self.native._events.put_nowait({'method':'turn/completed','params':{'threadId':self.sid,'turn':{'id':'turn-one','status':'completed'}}})
            return {'turn':{'id':'turn-one'}}
        return call

    async def test_verified_resume_settings_and_windows_prefix_are_benign(self):
        self.native.rpc=self.rpc('same')
        before=self.native.snapshot(self.sid)[0]
        result=await self.native.deliver(self.sid,'one directive',10,expected_sha256=before['native_sha256'])
        self.assertEqual(result['status'],'completed');self.assertEqual(self.started,1)
        self.assertEqual(canonical_path(self.native._paths[self.sid]),self.fake.paths[self.sid])

    async def test_foreign_append_is_blocked_before_model_call(self):
        self.native.rpc=self.rpc('foreign')
        before=self.native.snapshot(self.sid)[0]
        with self.assertRaisesRegex(CodexNativeError,'history_changed'):
            await self.native.deliver(self.sid,'one directive',10,expected_sha256=before['native_sha256'])
        self.assertEqual(self.started,0)


    async def test_changed_settings_are_blocked_before_model_call(self):
        self.native.rpc=self.rpc('changed')
        before=self.native.snapshot(self.sid)[0]
        with self.assertRaisesRegex(CodexNativeError,'history_changed'):
            await self.native.deliver(self.sid,'one directive',10,expected_sha256=before['native_sha256'])
        self.assertEqual(self.started,0)


class ContinuationPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_continuation_boundary_keeps_real_clarification_and_does_not_claim(self):
        from bridges import cli_bridge
        class Client:
            def __init__(self):self.requests=[]
            async def fetch_history(self,**kwargs):return []
            async def send_text(self,*args,**kwargs):return {'id':2}
            async def request_task_clarification(self,task_id,**kwargs):self.requests.append(task_id);return {'id':task_id}
        for runtime,base_id,forced,expected in [('codex',1,False,True),('codex',1,True,False),('codex',None,False,False),('kimi-code',1,False,True),('kimi-code',1,True,False),('dsh',1,False,False)]:
            with self.subTest(runtime=runtime,base_id=base_id,force_new=forced):
                client=Client();prompts=[]
                async def run(command,prompt,**kwargs):
                    prompts.append(prompt)
                    return cli_bridge.CliRunResult(returncode=0,stdout='TALK_TASK_PREFLIGHT {"action":"clarify","question":"请选择新部署端口。"}',stderr='')
                task={'id':8,'created_by':'human:bobo','target_member_id':'agent:codex','hall_group_id':'task:8',
                      'content':'继续上轮方案，并部署到尚未指定的新端口。','workflow_status':'assigned',
                      'execution_session':{'runtime':runtime,'base_task_id':base_id,'force_new':forced}}
                ready,_,advanced=await cli_bridge._prepare_task_before_claim(task,client=client,member_id='agent:codex',
                    workdir=Path.cwd(),preflight_command=['test-only'],timeout=5,runtime=runtime,
                    prompt_transport='stdin',command_runner=run,preflight_base_context='冻结基础规则')
                self.assertIsNone(ready);self.assertTrue(advanced);self.assertEqual(client.requests,[8])
                self.assertEqual('[[执行会话续轮预检边界]]' in prompts[0],expected)
                self.assertEqual(task['content'],'继续上轮方案，并部署到尚未指定的新端口。')



if __name__ == "__main__":
    unittest.main()
