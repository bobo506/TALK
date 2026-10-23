"""292 runtime tests: sidecar lock/CAS, query/plan/deliver/ACK orchestration.

These tests use a controllable native/model stand-in (no subprocess, no model,
no network) but still exercise the real store, kernel, adapter, channel,
overlay/request protocol and ACK validation. Real installed-DSH evidence is
kept separately in deepseek/evidence/native-*.json.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from bridges.dsh_execution_channel import (
    ExecutionSessionRunError,
    run_execution_session_task,
)
from bridges.execution_session_store import (
    ChannelBusy,
    ExecutionSessionStore,
)
from tests.test_dsh_context_metrics import metric_known, metric_missing, make_snapshot

PROJECT = "prj_e8fe7066bbec"
TARGET = "agent:deepseek"
REQUESTER = "agent:codex"
CONTINUITY = "line:test"
BINDING = "a" * 64
PERMISSION = "b" * 64
NATIVE_HOME = "native-home:test"
RUNNER = "runner:test"
LAUNCH = "launch:test"
BASE_TEXT = "固定基础介绍：只用于 runtime 测试，不得在续轮重复。"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@dataclass
class FakeNative:
    mode: str = "known"
    used: int = 699_000
    capacity: int = 1_000_000
    malformed: bool = False
    timeout_before: bool = False
    query_unavailable: bool = False
    benign_close: bool = True
    foreign_append: bool = False
    cancel_delivery: bool = False
    sessions: dict = None

    def __post_init__(self):
        self.sessions = {} if self.sessions is None else self.sessions
        self.requests = []
        self.queries = 0
        self.deliveries = 0

    def _snapshot(self, request, revision: int) -> dict:
        now = datetime.now(timezone.utc)
        identity = request["identity"]
        snapshot = make_snapshot(
            projected=self.used + 16 if self.mode == "known" else 59900,
            pressure=self.used if self.mode == "known" else 59900,
            capacity=self.capacity,
            projected_metric=(
                metric_known(self.used + 16, 4, now - timedelta(seconds=7))
                if self.mode == "known"
                else metric_missing()
            ),
            pressure_metric=(
                metric_known(self.used, 3, now - timedelta(seconds=8))
                if self.mode == "known"
                else metric_missing()
            ),
            capacity_metric=metric_known(self.capacity, 2, now - timedelta(seconds=9)),
            projected_time=now - timedelta(seconds=7),
            pressure_time=now - timedelta(seconds=8),
            capacity_time=now - timedelta(seconds=9),
            config_time=now - timedelta(seconds=10),
            observed_at=now - timedelta(seconds=1),
            revision=revision,
            provider=identity["providerId"],
            model=identity["modelId"],
            binding=identity["modelBindingFingerprint"],
            permission=identity["configPermissionFingerprint"],
            capture_status="available" if self.mode == "known" else "partial",
            native_session_id=request["native"]["sessionId"],
            session_generation=request["native"]["sessionGeneration"],
        )
        snapshot["host"].update(
            {
                "project_id": identity["projectId"],
                "target_member_id": identity["targetMemberId"],
                "requester_id": identity["requesterId"],
                "continuity_key": identity["continuityKey"],
                "workspace_identity": identity["workspaceIdentity"],
                "native_home_namespace": identity["nativeHomeNamespace"],
                "runner_id": identity["runnerId"],
                "service_launch_id": identity["serviceLaunchId"],
                "provider_id": identity["providerId"],
                "model_id": identity["modelId"],
                "model_binding_fingerprint": identity["modelBindingFingerprint"],
                "config_permission_fingerprint": identity["configPermissionFingerprint"],
            }
        )
        snapshot["config"]["provider_id"]["value"] = identity["providerId"]
        snapshot["config"]["model_id"]["value"] = identity["modelId"]
        snapshot["config"]["model_binding_fingerprint"]["value"] = identity[
            "modelBindingFingerprint"
        ]
        snapshot["config"]["config_permission_fingerprint"]["value"] = identity[
            "configPermissionFingerprint"
        ]
        return snapshot

    async def __call__(self, command, prompt, *, cwd, timeout, prompt_transport):
        overlay = Path(command[command.index("--patch") + 1])
        request = json.loads((overlay.parent / "request.json").read_text(encoding="utf-8"))
        self.requests.append(request)
        mode = request["mode"]
        if mode == "query":
            self.queries += 1
            if self.query_unavailable:
                return SimpleNamespace(
                    returncode=0,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    _fake=None,
                )
            session = self.sessions.get(request["native"]["sessionId"])
            if session is None:
                result = {
                    "schema": "talk-dsh-execution-result-1",
                    "version": 1,
                    "status": "unavailable",
                    "mode": "query",
                    "reason_code": "session_unavailable",
                    "request_digest": request["requestDigest"],
                    "query": None,
                    "delivery": None,
                }
            else:
                previous = request["native"].get("previousCut")
                revision = session["revision"]
                snapshot = copy.deepcopy(session['snapshot'])
                snapshot['observed_at'] = _iso(datetime.now(timezone.utc))
                snapshot['session']['revision'] = revision
                snapshot['session']['session_seq'] = revision + 1
                snapshot['session']['projection']['cut'] = revision
                snapshot['session']['projection']['session_seq'] = revision + 1
                appended = []
                if isinstance(previous, int) and revision > previous:
                    appended = ["session/end-seed"] * (revision - previous)
                if self.foreign_append and isinstance(previous, int):
                    revision += 1
                    session["revision"] = revision
                    appended = ["session/end-seed", "user/message"]
                result = {
                    "schema": "talk-dsh-execution-result-1",
                    "version": 1,
                    "status": "ok",
                    "mode": "query",
                    "request_digest": request["requestDigest"],
                    "inventory_hash": "c" * 64,
                    "snapshot": snapshot,
                    "query": {
                        "native_session_id": request["native"]["sessionId"],
                        "session_generation": request["native"]["sessionGeneration"],
                        "session_revision": revision,
                        "session_seq": revision + 1,
                        "appended_event_types": appended,
                        "cwd": str(cwd),
                        "provider_id": request["identity"]["providerId"],
                        "model_id": request["identity"]["modelId"],
                        "lifecycle": "live",
                    },
                    "delivery": None,
                }
                if self.benign_close:
                    session["revision"] += 1
                    session["appended"].append("session/end-seed")
        else:
            self.deliveries += 1
            if self.cancel_delivery:
                raise asyncio.CancelledError()
            sid = request["native"]["sessionId"]
            action = request["native"]["action"]
            if action == "create":
                self.sessions[sid] = {"revision": 0, "appended": []}
            session = self.sessions.get(sid)
            if session is None:
                return SimpleNamespace(
                    returncode=0, stdout="", stderr="", timed_out=False, _fake=None
                )
            session["revision"] += 9
            revision = session["revision"]
            directive = request["directive"]
            first_turn = bool(directive["firstTurn"])
            outcome = "delivered"
            committed = True
            if self.timeout_before:
                outcome = "timed_out_before_delivery"
                committed = False
            delivery = {
                "delivery_id": directive["deliveryId"],
                "task_id": directive["taskId"],
                "attempt": directive["attempt"],
                "execution_id": directive["executionId"],
                "body_sha256": directive["sha256"],
                "native_session_id": sid,
                "session_generation": request["native"]["sessionGeneration"],
                "session_revision": revision,
                "first_turn": first_turn,
                "outcome": outcome,
                "turn_outcome": "completed",
                "turn_error": None,
                "directive_committed": committed,
                "directive_seq": 1,
                "assistant_text": "FAKE_RUNTIME_OK",
                "started_at": _iso(datetime.now(timezone.utc)),
                "completed_at": _iso(datetime.now(timezone.utc)),
            }
            result = {
                "schema": "talk-dsh-execution-result-1",
                "version": 1,
                "status": "ok",
                "mode": "deliver",
                "request_digest": request["requestDigest"],
                "inventory_hash": "c" * 64,
                "snapshot": self._snapshot(request, revision),
                "delivery": delivery,
            }
            session['snapshot'] = copy.deepcopy(result['snapshot'])
            if self.malformed:
                result["delivery"] = {"delivery_id": "wrong"}
        if self.malformed and mode == "query":
            result["request_digest"] = "0" * 64
        overlay.parent.joinpath("result.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
        return SimpleNamespace(
            returncode=0, stdout="", stderr="", timed_out=False, _fake=None
        )


class FakeClient:
    def __init__(self, base_text: str = BASE_TEXT) -> None:
        self.base_text = base_text
        self.sha = __import__("hashlib").sha256(base_text.encode()).hexdigest()

    async def get_execution_session_base(self, task_id: int):
        return {
            "task_id": 1,
            "continuity_key": CONTINUITY,
            "project_id": PROJECT,
            "requester_id": REQUESTER,
            "target_member_id": TARGET,
            "base_contract_version": "1",
            "base_contract_sha256": self.sha,
            "base_context": self.base_text,
            "binding_fingerprint": BINDING,
            "workspace_root": str(ROOT),
            "workspace_identity": WORKSPACE_ID,
        }


ROOT = Path(tempfile.gettempdir()) / "talk-292-runtime-root"
ROOT.mkdir(parents=True, exist_ok=True)
WORKSPACE_ID = __import__("hashlib").sha256(
    json.dumps(
        {
            "schema": "talk-execution-workspace-1",
            "version": 1,
            "fields": {"path_normcase": str(ROOT.resolve()).casefold()},
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()


def binding_snapshot() -> dict:
    return {
        "state": "bound",
        "runtime": "dsh",
        "runner_id": RUNNER,
        "provider_id": "deepseek-official",
        "model_id": "deepseek-flash",
        "model_source": "builtin",
        "binding_fingerprint": BINDING,
    }


def make_task(task_id: int, *, content: str, base_sha: str, force_new: bool = False):
    return {
        "id": task_id,
        "attempt": 0,
        "target_member_id": TARGET,
        "created_by": REQUESTER,
        "project_id": PROJECT,
        "task_kind": "general",
        "content": content,
        "title": f"Runtime {task_id}",
        "hall_group_id": f"group:runtime-{task_id}",
        "may_delegate": False,
        "review_policy": None,
        "target_binding_snapshot": binding_snapshot(),
        "execution_session": {
            "schema": "talk-execution-session-request-1",
            "version": 1,
            "continuity_key": CONTINUITY,
            "force_new": force_new,
            "project_id": PROJECT,
            "requester_id": REQUESTER,
            "target_member_id": TARGET,
            "runtime": "dsh",
            "binding_fingerprint": BINDING,
            "binding_state": "bound",
            "workspace_root": str(ROOT),
            "workspace_identity": WORKSPACE_ID,
            "base_task_id": None if task_id == 1 else 1,
            "base_contract_version": "1",
            "base_contract_sha256": base_sha,
            "baseline_change": None,
            "authorization_change": None,
            "acceptance_difference": None,
        },
    }


class RuntimeBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp.name) / "store.sqlite3"
        self.package_root = Path(self.temp.name) / "dsh-package"
        self.package_root.mkdir()
        (self.package_root / "package.json").write_text(
            json.dumps({"name": "@deepseek-ai/dsh", "version": "0.1.5-rc.2"}),
            encoding="utf-8",
        )
        self._old_home = os.environ.get("DSH_HOME")
        os.environ["DSH_HOME"] = str(Path(self.temp.name) / "dsh-home")
        self.client = FakeClient()
        self.base_sha = self.client.sha
        self.native = FakeNative()

    async def asyncTearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("DSH_HOME", None)
        else:
            os.environ["DSH_HOME"] = self._old_home
        self.temp.cleanup()

    async def run_task(
        self, task_id: int, *, content: str, native=None, force_new: bool = False,
        launch_id: str = LAUNCH,
    ):
        return await run_execution_session_task(
            task=make_task(
                task_id, content=content, base_sha=self.base_sha, force_new=force_new
            ),
            client=self.client,
            member_id=TARGET,
            workdir=ROOT,
            command=["node", "dsh-bin.js", "--profile", "headless"],
            timeout=120,
            launch_id=launch_id,
            project_id=PROJECT,
            binding_snapshot=binding_snapshot(),
            hall_history="",
            store_override=str(self.store_path),
            native_package_root=str(self.package_root),
            runner=native or self.native,
        )


class FirstAndReuseTests(RuntimeBase):
    async def test_first_full_then_incremental_reuse_same_native(self) -> None:
        first = await self.run_task(1, content="第一轮完整任务。")
        self.assertEqual(first.state["decision"], "new_no_candidate")
        self.assertFalse(first.state["reused"])
        self.assertEqual(first.state["confirmed_count"], 1)
        self.assertIn("task_increment_sha256", first.state)
        self.assertIn("hall_messages_sha256", first.state)
        native_id = first.state["native_session_id"]
        first_request = self.native.requests[-1]
        self.assertTrue(first_request["mode"] == "deliver")
        self.assertIn("TALK BASE CONTRACT", first_request["directive"]["text"])
        self.assertIn("第一轮完整任务", first_request["directive"]["text"])

        second = await self.run_task(2, content="第二轮只给增量。")
        self.assertTrue(second.state["reused"])
        self.assertEqual(second.state["native_session_id"], native_id)
        self.assertEqual(second.state["confirmed_count"], 2)
        second_request = self.native.requests[-1]
        self.assertNotIn("TALK BASE CONTRACT", second_request["directive"]["text"])
        self.assertIn("第二轮只给增量", second_request["directive"]["text"])
        self.assertIn("task_id: talk-2", second_request["directive"]["text"])

    async def test_force_new_and_continuity_change_rotate(self) -> None:
        first = await self.run_task(1, content="base")
        forced = await self.run_task(2, content="force", force_new=True)
        self.assertNotEqual(forced.state["native_session_id"], first.state["native_session_id"])
        self.assertEqual(forced.state["decision"], "new_force_new")


class ThresholdTests(RuntimeBase):
    async def test_699_reuses_and_70_rotates_next(self) -> None:
        self.native.used = 699_000
        first = await self.run_task(1, content="69.9")
        self.native.used = 700_000
        second = await self.run_task(2, content="70")
        self.assertTrue(second.state["reused"])
        self.assertEqual(second.state["native_session_id"], first.state["native_session_id"])
        self.assertEqual(second.state["context_status"], "known")

        third = await self.run_task(3, content="next")
        self.assertFalse(third.state["reused"])
        self.assertEqual(third.state["decision"], "new_context_threshold")
        self.assertNotEqual(third.state["native_session_id"], first.state["native_session_id"])
        self.assertIn(
            "TALK BASE CONTRACT", self.native.requests[-1]["directive"]["text"]
        )


class FallbackTests(RuntimeBase):
    async def test_missing_metrics_counts_10_then_rotates_11(self) -> None:
        self.native.mode = "missing"
        rows = []
        for index in range(1, 12):
            outcome = await self.run_task(index, content=f"missing {index}")
            rows.append(outcome.state)
        self.assertTrue(all(row["context_status"] == "unavailable" for row in rows))
        for index in range(1, 10):
            self.assertTrue(rows[index]["reused"], rows[index])
            self.assertEqual(rows[index]["confirmed_count"], index + 1)
        self.assertTrue(rows[9]["reused"])
        self.assertEqual(rows[9]["confirmed_count"], 10)
        self.assertFalse(rows[10]["reused"])
        self.assertEqual(rows[10]["confirmed_count"], 1)
        self.assertNotEqual(rows[10]["native_session_id"], rows[0]["native_session_id"])
        self.assertEqual(rows[10]["decision"], "new_fallback_exhausted")


class FailureAndLockTests(RuntimeBase):
    async def test_malformed_ack_taints_and_never_counts(self) -> None:
        self.native.malformed = True
        with self.assertRaises(ExecutionSessionRunError):
            await self.run_task(1, content="bad ack")
        store = ExecutionSessionStore(self.store_path)
        rows = store.describe()
        self.assertGreaterEqual(rows["windows"], 1)
        self.assertEqual(rows["deliveries"], 0)
        # Next task cannot reuse the unknown/tainted window.
        self.native.malformed = False
        second = await self.run_task(2, content="fresh")
        self.assertFalse(second.state["reused"])
        self.assertEqual(second.state["decision"], "new_no_candidate")

    async def test_timeout_before_delivery_not_counted(self) -> None:
        self.native.timeout_before = True
        with self.assertRaises(ExecutionSessionRunError):
            await self.run_task(1, content="timeout")
        store = ExecutionSessionStore(self.store_path)
        with store._read() as conn:  # noqa: SLF001 - test-only audit query
            counted = conn.execute(
                "SELECT COALESCE(SUM(counted), 0) AS n FROM deliveries"
            ).fetchone()["n"]
        self.assertEqual(int(counted), 0)

    async def test_cancelled_delivery_marks_window_tainted(self) -> None:
        self.native.cancel_delivery = True
        with self.assertRaises(asyncio.CancelledError):
            await self.run_task(1, content="cancelled")
        store = ExecutionSessionStore(self.store_path)
        with store._read() as conn:  # noqa: SLF001 - test-only audit query
            row = conn.execute(
                "SELECT status, taint_reason FROM windows ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(row["status"], "tainted")
        self.assertEqual(row["taint_reason"], "delivery_cancelled_unknown")

    async def test_channel_busy_then_lease_expiry(self) -> None:
        store = ExecutionSessionStore(self.store_path)
        now = datetime.now(timezone.utc)
        store.acquire_channel(
            scope_key="k",
            owner_token="owner-a",
            owner_pid=1,
            ttl_seconds=60,
            now=now,
        )
        with self.assertRaises(ChannelBusy):
            store.acquire_channel(
                scope_key="k",
                owner_token="owner-b",
                owner_pid=2,
                ttl_seconds=60,
                now=now,
            )
        acquired = store.acquire_channel(
            scope_key="k",
            owner_token="owner-b",
            owner_pid=2,
            ttl_seconds=60,
            now=now + timedelta(seconds=61),
        )
        self.assertEqual(acquired["status"], "acquired")
        released = store.release_channel(scope_key="k", owner_token="owner-b")
        self.assertEqual(released["status"], "released")

    async def test_service_launch_change_forces_new_native(self) -> None:
        first = await self.run_task(1, content="launch one")
        second = await self.run_task(2, content="launch two", launch_id="launch:other")
        self.assertFalse(second.state["reused"])
        self.assertNotEqual(second.state["native_session_id"], first.state["native_session_id"])

    async def test_foreign_append_since_query_taints_old_window(self) -> None:
        first = await self.run_task(1, content="base")
        self.native.foreign_append = True
        second = await self.run_task(2, content="changed elsewhere")
        self.assertFalse(second.state["reused"])
        self.assertNotEqual(second.state["native_session_id"], first.state["native_session_id"])

    async def test_duplicate_receipt_is_idempotent_in_store(self) -> None:
        store = ExecutionSessionStore(self.store_path)
        window = store.create_window(
            scope={
                "project_id": PROJECT,
                "target_member_id": TARGET,
                "continuity_key": CONTINUITY,
                "base_contract_version": "1",
                "base_contract_sha256": self.base_sha,
            },
            scope_fingerprint="f" * 64,
            native_session_id="session-22222222-2222-4222-8222-222222222222",
            session_generation=1,
            base_task_id=1,
        )
        receipt = {
            "delivery_id": "delivery-dup",
            "task_id": 1,
            "attempt": 0,
            "execution_id": "exec-dup",
            "body_sha256": "a" * 64,
            "native_session_id": "session-22222222-2222-4222-8222-222222222222",
            "session_generation": 1,
            "session_revision": 3,
            "outcome": "delivered",
            "first_turn": True,
        }
        first = store.record_delivery(
            window_id=window["window_id"],
            receipt=receipt,
            ack={"turnOutcome": "completed", "assistant_text": "PRIVATE_MODEL_TEXT"},
            snapshot=None,
            counted=True,
        )
        second = store.record_delivery(
            window_id=window["window_id"],
            receipt=receipt,
            ack={"turnOutcome": "completed", "assistant_text": "PRIVATE_MODEL_TEXT"},
            snapshot=None,
            counted=True,
        )
        self.assertEqual(first["status"], "recorded")
        self.assertEqual(second["status"], "duplicate")
        stored = store.get_delivery("delivery-dup")
        self.assertIsNotNone(stored)
        self.assertNotIn("PRIVATE_MODEL_TEXT", json.dumps(stored, ensure_ascii=False))
        self.assertIn("assistant_text_sha256", stored["ack"])
        with store._read() as conn:  # noqa: SLF001 - test-only audit query
            counted = conn.execute(
                "SELECT COALESCE(SUM(counted), 0) AS n FROM deliveries"
            ).fetchone()["n"]
        self.assertEqual(int(counted), 1)


from unittest.mock import patch
from bridges import dsh_execution_channel as channel, cli_bridge
from bridges.execution_session_store import StoreConflict

class IndependentRuntimeProbes(RuntimeBase):
    async def test_duplicate_task_attempt_does_not_call_model_again(self):
        await self.run_task(1,content='same directive')
        try:
            await self.run_task(1,content='same directive')
        except (channel.ExecutionSessionRunError, StoreConflict):
            pass
        self.assertEqual(self.native.deliveries,1,'same logical attempt invoked native model twice')

    async def test_unknown_resume_delivery_taints_window(self):
        first=await self.run_task(1,content='base')
        async def broken(command,prompt,**kwargs):
            request=json.loads(Path(command[-1]).with_name('request.json').read_text(encoding='utf-8'))
            if request['mode']=='deliver':
                raise OSError('delivery unknown')
            return await self.native(command,prompt,**kwargs)
        with self.assertRaises(channel.ExecutionSessionRunError):
            await self.run_task(2,content='second',native=broken)
        store=ExecutionSessionStore(self.store_path)
        with store._read() as conn:
            status=conn.execute('SELECT status FROM windows WHERE native_session_id=?',(first.state['native_session_id'],)).fetchone()[0]
        self.assertEqual(status,'tainted','unconfirmed resumed delivery retained reusable window')

    async def test_counted_receipt_conflicting_outcome_is_rejected(self):
        first=await self.run_task(1,content='base')
        store=ExecutionSessionStore(self.store_path)
        previous=store.get_delivery(first.state['delivery_id'])
        receipt={k:previous['ack'][k] for k in ['delivery_id','task_id','attempt','execution_id','body_sha256','native_session_id','session_generation','session_revision','outcome','first_turn']}
        receipt['outcome']='failed_before_delivery'
        with self.assertRaises(StoreConflict):
            store.record_delivery(window_id=previous['window_id'],receipt=receipt,ack=receipt,snapshot=None,counted=False)

    async def test_current_query_metrics_override_old_snapshot(self):
        await self.run_task(1,content='base')
        store=ExecutionSessionStore(self.store_path)
        with store._read() as conn:
            wid=conn.execute('SELECT window_id FROM windows').fetchone()[0]
        window=store.get_window(wid)
        fresh=copy.deepcopy(window['last_snapshot'])
        fresh['metrics']['pressure_tokens']['value']=600_000
        fresh['metrics']['projected_tokens']['value']=600_016
        query={'native_session_id':window['native_session_id'],'session_generation':1,'session_revision':window['count_state']['last_session_revision'],'snapshot':fresh}
        sample,_=channel._context_for_plan(window=window,query=query,scope_candidate=window['scope'],max_age_seconds=21600)
        self.assertIsNotNone(sample)
        self.assertEqual(sample['projected_tokens'],600_016,'planning still uses saved metrics rather than current query')

class IndependentLeaseProbe(unittest.IsolatedAsyncioTestCase):
    async def test_claim_lease_loss_cancels_native_run(self):
        canceled=asyncio.Event()
        started=asyncio.Event()
        async def run(**kwargs):
            started.set()
            try: await asyncio.sleep(10)
            finally: canceled.set()
        async def lease():
            await started.wait()
            raise cli_bridge.TaskLeaseLostError('test lease lost')
        heartbeat=asyncio.create_task(lease())
        with patch('bridges.dsh_execution_channel.run_execution_session_task',run):
            call=asyncio.create_task(cli_bridge._handle_execution_session_claimed({'id':1},client=object(),member_id=TARGET,workdir=ROOT,command=['dsh'],timeout=1,max_reply_chars=1000,bridge_label='test',claim_token='test',heartbeat_task=heartbeat,execution_context={},diagnostics=None,replay_context=''))
            try:
                await asyncio.wait_for(asyncio.shield(call),0.15)
            except asyncio.TimeoutError:
                self.fail('lease loss did not stop native run')
            finally:
                call.cancel()
                await asyncio.gather(call,heartbeat,return_exceptions=True)
        self.assertTrue(canceled.is_set())

class AdditionalRuntimeRegressionTests(RuntimeBase):
    async def test_reliable_low_can_exceed_ten(self):
        rows=[(await self.run_task(n,content=f'low {n}')).state for n in range(1,13)]
        self.assertEqual(len({x['native_session_id'] for x in rows}),1)
        self.assertEqual(rows[-1]['confirmed_count'],12)

    async def test_metrics_recovery_does_not_reset_count(self):
        rows=[]
        for n in range(1,12):
            self.native.mode='known' if n in {6,7} else 'missing'
            rows.append((await self.run_task(n,content=f'change {n}')).state)
        self.assertEqual([x['confirmed_count'] for x in rows[:10]],list(range(1,11)))
        self.assertNotEqual(rows[0]['native_session_id'],rows[10]['native_session_id'])

    async def test_atomic_commit_rolls_back_receipt_when_window_update_fails(self):
        original=ExecutionSessionStore.commit_confirmed_delivery
        def broken(store,**kwargs):
            with store._transaction() as conn:
                conn.execute("CREATE TRIGGER reject_delivery BEFORE UPDATE OF count_state_json ON windows BEGIN SELECT RAISE(ABORT, 'injected'); END")
            return original(store,**kwargs)
        with patch.object(ExecutionSessionStore,'commit_confirmed_delivery',broken):
            with self.assertRaises(channel.ExecutionSessionRunError):
                await self.run_task(1,content='atomic rollback')
        store=ExecutionSessionStore(self.store_path)
        self.assertEqual(store.count_deliveries(),0)
        with store._read() as conn:
            self.assertIsNone(conn.execute('SELECT count_state_json FROM windows').fetchone()[0])
        self.assertEqual(self.native.deliveries,1)
        with self.assertRaises(channel.ExecutionSessionRunError):
            await self.run_task(1,content='atomic rollback')
        self.assertEqual(self.native.deliveries,1)

    async def test_channel_lease_loss_cancels_delivery(self):
        started=asyncio.Event()
        stopped=asyncio.Event()
        async def native(command,prompt,**kwargs):
            started.set()
            try: await asyncio.sleep(10)
            finally: stopped.set()
        async def lost(*args,**kwargs):
            await started.wait()
            raise channel.ExecutionSessionRunError('channel_lease_lost')
        with patch.object(channel,'_renew_channel_loop',lost):
            with self.assertRaises(channel.ExecutionSessionRunError):
                await self.run_task(1,content='channel lease',native=native)
        self.assertTrue(stopped.is_set())

if __name__ == "__main__":
    unittest.main()
