"""Terra/0.164 首片：协议版本协商、独立 rollout 与合成协议证据。

只读取合成 JSONL/内存 RPC 形状；不调用真实 CLI、登录或模型。
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import uuid

from bridges.codex_execution_native import (CodexNative, CodexNativeError, LaunchSpec,
    read_rollout, resolve_launch, text_digest)


def _write_rollout(root: Path, session_id: str, cli_version: str = "0.164.0") -> Path:
    home = root / "home"
    sessions = home / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / f"rollout-{session_id}.jsonl"
    rows = [
        {"timestamp": "2026-10-28T00:00:00Z", "type": "session_meta",
         "payload": {"id": session_id, "cli_version": cli_version,
                     "cwd": str(root), "model_provider": "openai"}},
        # 0.164 的新增字段（activePermissionProfile 等）不得改变既有校验。
        {"timestamp": "2026-10-28T00:00:01Z", "type": "turn_context",
         "payload": {"model": "gpt-6.1-terra", "activePermissionProfile": "read-only"}},
        {"timestamp": "2026-10-28T00:00:02Z", "type": "event_msg",
         "payload": {"type": "thread_settings_applied", "thread_id": session_id,
                     "thread_settings": {"model": "gpt-6.1-terra", "cwd": str(root),
                                         "reasoning_effort": "low"}}},
        {"timestamp": "2026-10-28T00:00:03Z", "type": "event_msg",
         "payload": {"type": "user_message", "message": "synthetic"}},
        {"timestamp": "2026-10-28T00:00:04Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {
             "last_token_usage": {"total_tokens": 12}, "model_context_window": 1000}}},
    ]
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
                    encoding="utf-8")
    return path


class TerraProtocolTests(unittest.TestCase):
    def test_0_164_rollout_is_read_with_terra_low(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            sid = str(uuid.uuid4())
            path = _write_rollout(root, sid)
            snapshot, users = read_rollout(path, home=root / "home", session_id=sid,
                workdir=root, model="gpt-6.1-terra", provider="openai")
            self.assertEqual(snapshot["used_tokens"], 12)
            self.assertEqual(users[0][1], text_digest("synthetic"))

    def test_legacy_0_163_and_unknown_0_165_are_distinguished(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            sid = str(uuid.uuid4())
            path = _write_rollout(root, sid, "0.163.0")
            self.assertEqual(read_rollout(path, home=root / "home", session_id=sid,
                workdir=root, model="gpt-6.1-terra", provider="openai")[0]["used_tokens"], 12)
            path = _write_rollout(root, sid, "0.165.0")
            with self.assertRaisesRegex(CodexNativeError, "rollout_identity_mismatch"):
                read_rollout(path, home=root / "home", session_id=sid, workdir=root,
                             model="gpt-6.1-terra", provider="openai")

    def test_0_164_thread_response_ignores_additive_fields_and_checks_version(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            sid = str(uuid.uuid4())
            path = _write_rollout(root, sid)
            spec = LaunchSpec([], {}, root / "home", "gpt-6.1-terra", "openai", "low",
                              "read-only", "never", "f" * 64, "0.164.0")
            native = CodexNative(spec, root)
            result = {"thread": {"id": sid, "cwd": str(root), "modelProvider": "openai",
                                 "ephemeral": False, "path": str(path),
                                 "cliVersion": "0.164.0",
                                 "runtimeWorkspaceRoots": [], "activePermissionProfile": "read-only"},
                      "model": "gpt-6.1-terra", "reasoningEffort": "low",
                      "approvalPolicy": "never",
                      "sandbox": {"type": "readOnly", "networkAccess": False}}
            self.assertEqual(native._verify_thread(result, sid, attached=True), sid)
            result["thread"]["cliVersion"] = "0.165.0"
            with self.assertRaisesRegex(CodexNativeError, "thread_identity_mismatch"):
                native._verify_thread(result, sid, attached=True)

    def test_version_is_part_of_launch_fingerprint_and_unknown_fails(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            home = root / "home"
            home.mkdir()
            exe = root / "codex.exe"
            exe.write_bytes(b"synthetic, never executed")
            command = [str(exe), "-a", "never", "--strict-config", "exec",
                       "--model", "gpt-6.1-terra", "--sandbox", "read-only",
                       "-c", 'model_reasoning_effort="low"', "-"]
            binding = {"runtime": "codex", "runner_id": "r", "provider_id": "openai",
                       "model_id": "gpt-6.1-terra", "binding_fingerprint": "a" * 64}
            import os
            from unittest.mock import patch
            from types import SimpleNamespace
            with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                with patch("bridges.codex_execution_native.subprocess.run",
                           return_value=SimpleNamespace(stdout="codex-cli 0.164.0\n")):
                    one = resolve_launch(command, root, binding)
                with patch("bridges.codex_execution_native.subprocess.run",
                           return_value=SimpleNamespace(stdout="codex-cli 0.163.0\n")):
                    two = resolve_launch(command, root, binding)
                self.assertNotEqual(one.fingerprint, two.fingerprint)
                self.assertEqual((one.version, two.version), ("0.164.0", "0.163.0"))
                with patch("bridges.codex_execution_native.subprocess.run",
                           return_value=SimpleNamespace(stdout="codex-cli 0.165.0\n")):
                    with self.assertRaisesRegex(CodexNativeError, "version_unsupported"):
                        resolve_launch(command, root, binding)


if __name__ == "__main__":
    unittest.main()
