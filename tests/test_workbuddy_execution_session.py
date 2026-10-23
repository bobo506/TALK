"""WorkBuddy独立CLI：原生格式、双证明、隔离、计数及入口接线。"""
from __future__ import annotations
import asyncio
import copy
import json
import os
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from bridges.workbuddy_execution_native import WorkBuddyNative, WorkBuddyNativeError, public_model, resolve_launch, text_digest
from bridges.workbuddy_execution_channel import run_execution_session_task
from bridges.workbuddy_bridge import build_command
from bridges.dsh_execution_channel import ExecutionSessionRunError, _workspace_identity
from bridges.execution_session_store import ExecutionSessionStore


class FakeNative(WorkBuddyNative):
    async def open(self): pass

    async def deliver(self, sid, text, timeout, *, expected_sha256):
        if self.fail_before:
            raise WorkBuddyNativeError("controlled_before_delivery")
        sid = sid or str(uuid.uuid4())
        directory = self.home / "projects/controlled"
        directory.mkdir(parents=True, exist_ok=True)
        file = directory / (sid + ".jsonl")
        self.last_session_id = sid
        self.directives.append((sid, text))
        mid, rid = str(uuid.uuid4()), uuid.uuid4().hex
        stamp = int(datetime.now(timezone.utc).timestamp() * 1000) - self.age_ms
        user = {"type": "message", "id": mid, "sessionId": sid, "cwd": str(self.workdir), "timestamp": stamp,
                "role": "user", "content": [{"type": "input_text", "text": text}],
                "providerData": {"startsNewUserRequest": True, "conversationRequestId": rid}}
        used = self.used
        usage = {} if self.missing else {"inputTokens": used - 10, "outputTokens": 10, "totalTokens": used}
        assistant = {"type": "message", "id": str(uuid.uuid4()), "sessionId": sid, "cwd": str(self.workdir),
                     "timestamp": stamp, "role": "assistant", "status": "completed", "content": [],
                     "providerData": {"requestModelId": self.spec.model, "usage": usage}}
        with file.open("a", encoding="utf-8") as f:
            for row in (user, {"type": "file-history-snapshot"}, assistant):
                f.write(json.dumps(row) + "\n")
        events = [{"type": "system", "subtype": "init", "session_id": sid, "model": self.spec.model},
                  {"type": "user", "uuid": mid, "_requestId": rid, "session_id": sid, "isReplay": True,
                   "message": {"content": [{"type": "text", "text": text}]}},
                  {"type": "result", "session_id": sid, "_requestId": rid, "subtype": "success",
                   "modelUsage": {self.spec.model: {"contextWindow": 100000}}}]
        self._buffers = [bytearray("".join(json.dumps(r) + "\n" for r in events).encode()), bytearray()]
        self._record_proof(sid, text)
        if self.cancel:
            raise asyncio.CancelledError()
        if self.fail_after:
            raise WorkBuddyNativeError("controlled_after_delivery")
        return {"status": "completed", "reply": "ok", "rerouted": False}


class WorkBuddyExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        install = self.root / "install/WorkBuddy"
        install.mkdir(parents=True)
        self.exe = install / "WorkBuddy.exe"
        self.exe.write_bytes(b"controlled executable")
        entry = install / "resources/app.asar.unpacked/cli/bin/codebuddy"
        entry.parent.mkdir(parents=True)
        entry.write_text("controlled entry", encoding="utf-8")
        bundle = entry.parent.parent / "dist/codebuddy-lite-wb.mjs"
        bundle.parent.mkdir()
        bundle.write_text("controlled bundle", encoding="utf-8")
        self.home = self.root / "home"
        self.home.mkdir()
        self.models = self.root / "model-source"
        self.models.mkdir()
        self.model_file = self.models / "models.json"
        self.model_file.write_text(json.dumps([{"id": "unit", "name": "unit", "apiKey": "private-test-value",
            "maxInputTokens": 100000, "maxOutputTokens": 2000}]), encoding="utf-8")
        self.binding = {"state": "bound", "runtime": "workbuddy", "runner_id": "runner:workbuddy",
            "provider_id": "managed:workbuddy", "model_id": "unit", "model_alias": "custom-local:unit", "binding_fingerprint": "a" * 64}
        self.argv = build_command(self.exe, self.binding["model_alias"], tools="")
        env = {"CODEBUDDY_CONFIG_DIR": str(self.home), "WORKBUDDY_CONFIG_DIR": str(self.models),
               "ELECTRON_RUN_AS_NODE": "1", "CODEBUDDY_FORCE_LITE_WB_BUNDLE": "1"}
        self.env = patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.native = FakeNative(resolve_launch(self.argv, self.root, self.binding), self.root)
        self.native.used = 69900
        self.native.fail_before = self.native.fail_after = self.native.cancel = self.native.missing = False
        self.native.age_ms = 0
        self.native.directives = []
        self.store = self.root / "sidecar.sqlite3"
        self.base = "fixed base BASEROOT"
        self.member, self.line = "agent:workbuddy", "workbuddy:test"

    async def asyncTearDown(self):
        self.env.stop()
        self.temp.cleanup()

    async def get_execution_session_base(self, task_id):
        return {"task_id": 1, "continuity_key": self.line, "project_id": "project:test", "requester_id": "agent:lead",
            "target_member_id": self.member, "binding_fingerprint": self.binding["binding_fingerprint"],
            "workspace_root": str(self.root), "workspace_identity": _workspace_identity(self.root),
            "base_contract_version": "1", "base_contract_sha256": text_digest(self.base), "base_context": self.base}

    def task(self, i, force=False):
        return {"id": i, "attempt": 1, "project_id": "project:test", "task_kind": "general", "created_by": "agent:lead",
            "target_member_id": self.member, "content": "increment " + str(i), "target_binding_snapshot": copy.deepcopy(self.binding),
            "execution_session": {"schema": "talk-execution-session-request-1", "version": 1, "project_id": "project:test",
                "target_member_id": self.member, "requester_id": "agent:lead", "continuity_key": self.line,
                "runtime": "workbuddy", "binding_fingerprint": self.binding["binding_fingerprint"],
                "workspace_root": str(self.root), "workspace_identity": _workspace_identity(self.root),
                "base_contract_version": "1", "base_contract_sha256": text_digest(self.base),
                "base_task_id": None if i == 1 else 1, "force_new": force}}

    async def run_task(self, i, force=False, task=None):
        return await run_execution_session_task(task=task or self.task(i, force), client=self, member_id=self.member,
            workdir=self.root, command=[], timeout=10, launch_id="launch:test", project_id="project:test",
            binding_snapshot=self.binding, runner=self.native, store_override=str(self.store))

    async def test_same_window_increment_and_new_window_restore(self):
        first, second = await self.run_task(1), await self.run_task(2)
        self.assertEqual(first.state["native_session_id"], second.state["native_session_id"])
        self.assertEqual(second.state["confirmed_count"], 2)
        self.assertNotIn(self.base, self.native.directives[1][1])
        third = await self.run_task(3, force=True)
        self.assertNotEqual(first.state["native_session_id"], third.state["native_session_id"])
        self.assertIn(self.base, self.native.directives[2][1])

    async def test_exact_threshold_changes_next_window(self):
        first = await self.run_task(1)
        self.native.used = 70000
        second, third = await self.run_task(2), await self.run_task(3)
        self.assertEqual(first.state["native_session_id"], second.state["native_session_id"])
        self.assertNotEqual(second.state["native_session_id"], third.state["native_session_id"])

    async def test_missing_only_ten_then_eleven(self):
        self.native.missing = True
        first = await self.run_task(1)
        for i in range(2, 11):
            r = await self.run_task(i)
            self.assertEqual(r.state["native_session_id"], first.state["native_session_id"])
        self.assertEqual(r.state["confirmed_count"], 10)
        last = await self.run_task(11)
        self.assertNotEqual(first.state["native_session_id"], last.state["native_session_id"])
        self.assertEqual(last.state["confirmed_count"], 1)

    async def test_reliable_low_occupancy_can_exceed_ten(self):
        for i in range(1, 13): r = await self.run_task(i)
        self.assertEqual(r.state["confirmed_count"], 12)

    async def test_measurement_recovery_keeps_count(self):
        self.native.missing = True
        await self.run_task(1)
        await self.run_task(2)
        self.native.missing = False
        self.assertEqual((await self.run_task(3)).state["confirmed_count"], 3)

    async def test_invalid_metrics_cannot_use_fallback(self):
        await self.run_task(1)
        self.native.used = -1
        await self.run_task(2)
        self.native.used = 100
        self.assertFalse((await self.run_task(3)).state["reused"])

    async def test_duplicate_attempt_never_runs_twice(self):
        await self.run_task(1)
        with self.assertRaises(ExecutionSessionRunError): await self.run_task(1)
        self.assertEqual(len(self.native.directives), 1)

    async def test_failure_after_delivery_is_counted_and_tainted(self):
        self.native.fail_after = True
        r = await self.run_task(1)
        self.assertEqual(r.state["confirmed_count"], 1)
        self.assertEqual(r.completion_status, "failed")
        self.native.fail_after = False
        self.assertFalse((await self.run_task(2)).state["reused"])

    async def test_cancel_after_delivery_releases_channel(self):
        self.native.cancel = True
        with self.assertRaises(asyncio.CancelledError): await self.run_task(1)
        c = ExecutionSessionStore(self.store)._connect()
        try:
            self.assertEqual(c.execute("SELECT count(*) FROM channels").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT state FROM attempts").fetchone()[0], "confirmed")
        finally:
            c.close()

    async def test_changed_requester_rejected_before_native(self):
        t = self.task(1)
        t["created_by"] = "agent:other"
        with self.assertRaises(ExecutionSessionRunError): await self.run_task(1, task=t)
        self.assertEqual(self.native.directives, [])

    async def test_changed_workline_gets_new_window(self):
        first = await self.run_task(1)
        self.line = "workbuddy:other"
        second = await self.run_task(2)
        self.assertNotEqual(first.state["native_session_id"], second.state["native_session_id"])

    async def test_missing_or_changed_stdout_ack_rejected(self):
        await self.run_task(1)
        sid = self.native.last_session_id
        self.native._buffers[0] = bytearray(b"{}\n")
        with self.assertRaises(WorkBuddyNativeError): self.native._record_proof(sid, "increment 1")

    async def test_changed_native_user_not_reused(self):
        await self.run_task(1)
        sid = self.native.last_session_id
        p = self.native._path(sid)
        rows = [json.loads(x) for x in p.read_text().splitlines()]
        rows[0]["content"][0]["text"] = "foreign edit"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        with self.assertRaises(WorkBuddyNativeError): self.native.snapshot(sid)
        self.assertFalse((await self.run_task(2)).state["reused"])

    async def test_future_native_record_rejected(self):
        await self.run_task(1)
        self.native.age_ms = -60000
        with self.assertRaises(ExecutionSessionRunError): await self.run_task(2)

    async def test_capacity_comes_from_input_not_output_budget(self):
        r = await self.run_task(1)
        self.assertEqual(r.state["last_snapshot"]["context_window"], 100000)

    async def test_model_or_permission_source_drift_rejected(self):
        await self.run_task(1)
        value = json.loads(self.model_file.read_text())
        value[0]["maxInputTokens"] = 200000
        self.model_file.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(WorkBuddyNativeError): self.native.snapshot(self.native.last_session_id)

    def test_private_fields_never_returned(self):
        public = public_model(self.models, "custom-local:unit")
        self.assertNotIn("apiKey", public)
        self.assertNotIn("private-test-value", json.dumps(public))

    def test_unknown_and_duplicate_flags_rejected(self):
        for suffix in (["--model", "custom-local:unit"], ["--dangerously-skip-permissions"], ["--continue"]):
            with self.assertRaises(WorkBuddyNativeError): resolve_launch(self.argv[:-1] + suffix, self.root, self.binding)

    def test_binding_model_mismatch_rejected(self):
        with self.assertRaises(WorkBuddyNativeError): resolve_launch(self.argv, self.root, {**self.binding, "model_id": "other"})

    def test_project_model_override_rejected(self):
        directory = self.root / ".codebuddy"
        directory.mkdir()
        (directory / "models.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(WorkBuddyNativeError): resolve_launch(self.argv, self.root, self.binding)

    def test_inherited_subagent_model_override_rejected(self):
        with patch.dict(os.environ, {"CODEBUDDY_CODE_SUBAGENT_MODEL": "other"}):
            with self.assertRaises(WorkBuddyNativeError): resolve_launch(self.argv, self.root, self.binding)

    async def test_receipts_store_no_assistant_body(self):
        await self.run_task(1)
        text = self.native._proof_path(self.native.last_session_id).read_text()
        self.assertNotIn("increment", text)
        self.assertNotIn(self.base, text)
        self.assertNotIn("private-test-value", text)
        self.assertNotIn('"reply"', text)

    async def test_native_wrong_workspace_rejected(self):
        await self.run_task(1)
        path = self.native._path(self.native.last_session_id)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]["cwd"] = str(self.root / "elsewhere")
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        with self.assertRaises(WorkBuddyNativeError): self.native.snapshot(self.native.last_session_id)

    async def test_native_capacity_conflict_rejected_as_invalid(self):
        await self.run_task(1)
        sid = self.native.last_session_id
        path = self.native._proof_path(sid)
        row = json.loads(path.read_text())
        row["context_window"] = 9999
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        snap, _ = self.native.snapshot(sid)
        self.assertTrue(snap["metrics_invalid"])


class WorkBuddyBridgeTests(unittest.IsolatedAsyncioTestCase):
    def test_host_filters_other_roles_before_claim(self):
        from scripts.workbuddy_role_host import WorkBuddyRoleHost, Drained
        from scripts import role_service_host as rsh
        host = WorkBuddyRoleHost.__new__(WorkBuddyRoleHost)
        with tempfile.TemporaryDirectory() as tmp:
            host.target_project, host.target_member = "p", "m"
            host.drain_requested = False
            host.drain_file = Path(tmp) / "drain"
            host._handles = {"owned": object()}
            host.health = Mock()
            actions = [{"project_id": "p", "member_id": "m", "action": "start"},
                       {"project_id": "p", "member_id": "m", "action": "stop"},
                       {"project_id": "p", "member_id": "other", "action": "stop"},
                       {"project_id": "other", "member_id": "m", "action": "start"}]
            with patch.object(rsh.HostManager, "claimable_actions", return_value=actions):
                self.assertEqual(host.claimable_actions("p"), actions[:2])
                self.assertEqual(host.claimable_actions("other"), [])
                host.drain_requested = True
                self.assertEqual(host.claimable_actions("p"), actions[1:2])
                host._handles.clear()
                with self.assertRaises(Drained): host.claimable_actions("p")

    def test_host_dry_run_never_opens_client(self):
        from scripts import workbuddy_role_host as host
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "WorkBuddy.exe"
            exe.write_text("controlled")
            (root / "models.json").write_text("[]")
            with patch.object(host.rsh, "TalkHostClient", side_effect=AssertionError("dry-run network")):
                self.assertEqual(host.main(["serve", "--project", "p", "--member", "m", "--workbuddy-executable", str(exe),
                    "--workbuddy-models-home", str(root)]), 0)

    def test_host_apply_uses_actual_serve_signature_and_drains(self):
        from scripts import workbuddy_role_host as host
        client = Mock()
        client.request.return_value = {"kind": "human"}
        def serve(project_id, *, poll_interval, once, max_rounds, provision_worker):
            raise host.Drained()
        manager = SimpleNamespace(serve=serve, health=Mock())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "WorkBuddy.exe"
            exe.write_text("controlled")
            (root / "models.json").write_text("[]")
            with patch.object(host.rsh, "TalkHostClient", return_value=client), patch.object(host.rsh, "load_operator_key", return_value="fake"), patch.object(host, "WorkBuddyRoleHost", return_value=manager):
                self.assertEqual(host.main(["serve", "--project", "p", "--member", "m", "--workbuddy-executable", str(exe),
                    "--workbuddy-models-home", str(root), "--apply", "--runtime-verified", "workbuddy",
                    "--role-key-file", str(root / "role.key"), "--operator-key-file", str(root / "operator.key"),
                    "--workbuddy-display-name", "Original member name"]), 0)
            manager.health.assert_called_once_with("stopped")

    async def test_queue_selects_workbuddy_branch_and_loads_base(self):
        from bridges import cli_bridge
        task = {"id": 1, "execution_session": {"runtime": "workbuddy"}, "created_by": "agent:lead"}
        class Client:
            async def claim_task(self, *args, **kwargs): return task
        with patch("bridges.dsh_execution_channel._load_base_contract", AsyncMock(return_value={"text": "verified base"})) as base, patch.object(
                cli_bridge, "_prepare_task_before_claim", AsyncMock(return_value=(task, "history", False))), patch.object(
                cli_bridge, "_handle_execution_session_claimed", AsyncMock(return_value=True)) as handler, patch.object(
                cli_bridge, "_start_task_heartbeat", return_value=None):
            handled = await cli_bridge.handle_queued_task(task, client=Client(), member_id="agent:workbuddy", workdir=Path.cwd(),
                instance_id="instance", command=["workbuddy"], timeout=1, max_reply_chars=1000, runtime="workbuddy",
                execution_context={"project_id": "project:test"})
        self.assertTrue(handled)
        base.assert_awaited_once()
        handler.assert_awaited_once()

    def test_real_host_recipe_parses_and_preserves_timeout(self):
        from scripts.role_service_host import build_runtime_argv, verify_runtime_entry
        argv = build_runtime_argv("workbuddy", model_alias="custom-local:unit")
        self.assertIn("--workbuddy-model", argv)
        self.assertEqual(argv[argv.index("--timeout") + 1], "21600")
        self.assertTrue(verify_runtime_entry("workbuddy", argv))


if __name__ == "__main__": unittest.main()
