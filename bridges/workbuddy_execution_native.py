"""WorkBuddy 内置 CodeBuddy Code lite 2.161.0 的独立 CLI 会话接口。

不控制桌面窗口，不复制账号配置；模型目录和会话存储分别显式指定。
送达证明来自 stdout 用户回执和原生 JSONL 的同 ID/请求 ID/SHA，
本适配自己的 proof 文件只保留最小回执，不保存正文或认证。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

VERSION = "2.161.0"
MAX_BYTES = 64 * 1024 * 1024
SESSION_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAX_INTEGER = 9_007_199_254_740_991


class WorkBuddyNativeError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(path: str | Path) -> Path:
    raw = str(path)
    if os.name == "nt" and raw.startswith("\\\\?\\"):
        raw = "\\\\" + raw[8:] if raw.startswith("\\\\?\\UNC\\") else raw[4:]
    return Path(raw).resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        canonical(path).relative_to(canonical(root))
        return True
    except (OSError, ValueError):
        return False


def _json(path: Path):
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise WorkBuddyNativeError("workbuddy_file_limit")
    return json.loads(data)


def public_model(home: Path, alias: str) -> dict:
    """固定字段白名单；绝不返回原始配置对象或凭据字段。"""
    value = _json(home / "models.json")
    rows = value if isinstance(value, list) else value.get("models", []) if isinstance(value, dict) else []
    found = [r for r in rows if isinstance(r, dict) and "custom-local:" + str(r.get("id")) == alias]
    if len(found) != 1:
        raise WorkBuddyNativeError("workbuddy_model_missing_or_ambiguous")
    return {k: found[0].get(k) for k in ("id", "name", "vendor", "url", "maxInputTokens", "maxOutputTokens",
                                         "supportsToolCall", "supportsImages", "supportsReasoning", "reasoning")}


def _integer(value, *, positive=False):
    return type(value) is int and (value > 0 if positive else value >= 0) and value <= MAX_INTEGER


@dataclass
class LaunchSpec:
    argv: list[str]
    env: dict[str, str]
    home: Path
    models_home: Path
    model: str
    model_config: dict
    fingerprint: str
    inventory: dict


def _inventory(argv, home, models_home, model):
    executable, entry = canonical(argv[0]), canonical(argv[1])
    bundle = entry.parent.parent / "dist/codebuddy-lite-wb.mjs"
    # app.asar virtual entry maps to app.asar.unpacked for Python filesystem reads.
    if not entry.is_file():
        entry = Path(str(entry).replace("app.asar/", "app.asar.unpacked/").replace("app.asar\\", "app.asar.unpacked\\"))
        bundle = entry.parent.parent / "dist/codebuddy-lite-wb.mjs"
    if not executable.is_file() or not entry.is_file() or not bundle.is_file():
        raise WorkBuddyNativeError("workbuddy_install_missing")
    return {"argv": argv, "home": str(home).casefold(), "models_home": str(models_home).casefold(),
            "model": public_model(models_home, model), "executable_mtime_ns": executable.stat().st_mtime_ns,
            "model_source_mtime_ns": (models_home / "models.json").stat().st_mtime_ns,
            "model_source_bytes": (models_home / "models.json").stat().st_size,
            "entry_sha256": hashlib.sha256(entry.read_bytes()).hexdigest(),
            "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest()}


def resolve_launch(command: Sequence[str], workdir: Path, binding: Mapping[str, Any]) -> LaunchSpec:
    argv = list(map(str, command))
    if len(argv) < 4 or Path(argv[0]).name.lower() != "workbuddy.exe" or Path(argv[1]).name != "codebuddy":
        raise WorkBuddyNativeError("workbuddy_command_unsupported")
    if canonical(argv[1]).parts[-3:] != ("cli", "bin", "codebuddy"):
        raise WorkBuddyNativeError("workbuddy_entry_unsupported")
    # A real installed WorkBuddy sibling; no arbitrary executable/entry pairing.
    if canonical(argv[0]).parent != canonical(argv[1]).parents[3].parent:
        raise WorkBuddyNativeError("workbuddy_install_identity_mismatch")
    if argv[-1:] == ["-p"]:
        argv.pop()
    flags = {}
    index = 2
    while index < len(argv):
        flag = argv[index]
        if flag == "--strict-mcp-config":
            if flag in flags:
                raise WorkBuddyNativeError("workbuddy_duplicate_flag")
            flags[flag] = True
            index += 1
        elif flag in {"--model", "--permission-mode", "--tools", "--mcp-config", "--setting-sources"} and index + 1 < len(argv):
            if flag in flags:
                raise WorkBuddyNativeError("workbuddy_duplicate_flag")
            flags[flag] = argv[index + 1]
            index += 2
        else:
            raise WorkBuddyNativeError("workbuddy_command_unsupported")
    model = flags.get("--model")
    if (not isinstance(model, str) or not model.startswith("custom-local:")
            or model != binding.get("model_alias") or model[13:] != binding.get("model_id")
            or binding.get("provider_id") != "managed:workbuddy"):
        raise WorkBuddyNativeError("workbuddy_model_identity_mismatch")
    if (flags.get("--permission-mode") != "default" or flags.get("--tools") not in {"", "default"}
            or flags.get("--setting-sources") != "" or flags.get("--strict-mcp-config") is not True
            or json.loads(flags.get("--mcp-config", "null")) != {"mcpServers": {}}):
        raise WorkBuddyNativeError("workbuddy_profile_unsupported")
    env = dict(os.environ)
    home, models_home = canonical(env.get("CODEBUDDY_CONFIG_DIR", "")), canonical(env.get("WORKBUDDY_CONFIG_DIR", ""))
    if not env.get("CODEBUDDY_CONFIG_DIR") or not env.get("WORKBUDDY_CONFIG_DIR") or not home.is_dir():
        raise WorkBuddyNativeError("workbuddy_home_missing")
    if env.get("ELECTRON_RUN_AS_NODE") != "1" or env.get("CODEBUDDY_FORCE_LITE_WB_BUNDLE") != "1":
        raise WorkBuddyNativeError("workbuddy_lite_environment_missing")
    if any((k.startswith(("CODEBUDDY_", "WORKBUDDY_")) and "MODEL" in k)
           or k == "ANTHROPIC_API_KEY" for k in env):
        raise WorkBuddyNativeError("workbuddy_model_override")
    _check_project_models(workdir)
    inventory = _inventory(argv, home, models_home, model)
    return LaunchSpec(argv, env, home, models_home, model, inventory["model"], digest(inventory), inventory)


def _check_project_models(workdir):
    if any((Path(workdir) / name / "models.json").exists() for name in (".codebuddy", ".workbuddy")):
        raise WorkBuddyNativeError("workbuddy_project_model_override")


def _text(parts):
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list) or any(not isinstance(p, dict) or p.get("type") not in {"text", "input_text"} for p in parts):
        raise WorkBuddyNativeError("workbuddy_user_content_ambiguous")
    return "".join(str(p.get("text", "")) for p in parts)


class WorkBuddyNative:
    def __init__(self, spec: LaunchSpec, workdir: Path):
        self.spec, self.home, self.fingerprint, self.workdir = spec, spec.home, spec.fingerprint, canonical(workdir)
        self.last_session_id = None
        self.process = None
        self._streams = []
        self._buffers = [bytearray(), bytearray()]

    async def open(self):
        process = await asyncio.create_subprocess_exec(*self.spec.argv[:2], "--version", env=self.spec.env,
            cwd=self.workdir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 15)
        except BaseException:
            process.kill()
            await process.wait()
            raise
        if process.returncode != 0 or output.decode().strip() != VERSION:
            raise WorkBuddyNativeError("workbuddy_version_unsupported")

    def _path(self, sid):
        if not isinstance(sid, str) or not SESSION_RE.fullmatch(sid):
            raise WorkBuddyNativeError("workbuddy_session_id_invalid")
        found = list((self.home / "projects").glob("*/" + sid + ".jsonl"))
        if len(found) != 1 or not _inside(found[0], self.home):
            raise WorkBuddyNativeError("workbuddy_session_missing_or_ambiguous")
        return found[0]

    def _proof_path(self, sid):
        if not SESSION_RE.fullmatch(sid):
            raise WorkBuddyNativeError("workbuddy_session_id_invalid")
        path = self.home / "talk-execution-proofs" / (sid + ".jsonl")
        if not _inside(path, self.home):
            raise WorkBuddyNativeError("workbuddy_proof_path_escape")
        return path

    def snapshot(self, sid):
        _check_project_models(self.workdir)
        if digest(_inventory(self.spec.argv, self.home, self.spec.models_home, self.spec.model)) != self.fingerprint:
            raise WorkBuddyNativeError("workbuddy_config_changed")
        path = self._path(sid)
        data = path.read_bytes()
        if len(data) > MAX_BYTES or not data.endswith(b"\n"):
            raise WorkBuddyNativeError("workbuddy_native_cut_invalid")
        rows = [json.loads(line) for line in data.splitlines()]
        users, ids, assistant = [], set(), None
        current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        for index, row in enumerate(rows):
            if row.get("type") != "message":
                continue
            if row.get("sessionId") != sid or canonical(row.get("cwd", "")) != self.workdir:
                raise WorkBuddyNativeError("workbuddy_session_identity_mismatch")
            mid = row.get("id")
            if not isinstance(mid, str) or mid in ids or not _integer(row.get("timestamp"), positive=True) or row["timestamp"] > current_ms:
                raise WorkBuddyNativeError("workbuddy_native_record_invalid")
            ids.add(mid)
            provider = row.get("providerData") or {}
            if row.get("role") == "user" and provider.get("startsNewUserRequest") is True:
                users.append((index, text_digest(_text(row.get("content")))))
            if row.get("role") == "assistant":
                if provider.get("requestModelId") != self.spec.model:
                    raise WorkBuddyNativeError("workbuddy_native_model_mismatch")
                assistant = row
        proof_file = self._proof_path(sid)
        proof_bytes = proof_file.read_bytes() if proof_file.is_file() else b""
        if len(proof_bytes) > MAX_BYTES or (proof_bytes and not proof_bytes.endswith(b"\n")):
            raise WorkBuddyNativeError("workbuddy_proof_cut_invalid")
        proofs = [json.loads(line) for line in proof_bytes.splitlines()]
        formal = [r for r in rows if r.get("type") == "message" and r.get("role") == "user" and (r.get("providerData") or {}).get("startsNewUserRequest") is True]
        if len(proofs) != len(formal):
            raise WorkBuddyNativeError("workbuddy_delivery_proof_missing")
        for row, proof in zip(formal, proofs):
            if (proof.get("user_id") != row["id"] or proof.get("request_id") != row["providerData"].get("conversationRequestId")
                    or proof.get("body_sha256") != text_digest(_text(row["content"])) or proof.get("fingerprint") != self.fingerprint):
                raise WorkBuddyNativeError("workbuddy_delivery_proof_mismatch")
        usage = (assistant.get("providerData", {}).get("usage") or {}) if assistant else {}
        used = usage.get("totalTokens")
        capacity = self.spec.model_config.get("maxInputTokens")
        missing = used is None or capacity is None
        invalid = (used is not None and not _integer(used)) or (capacity is not None and not _integer(capacity, positive=True))
        if all(k in usage for k in ("inputTokens", "outputTokens", "totalTokens")):
            invalid |= any(not _integer(usage[k]) for k in ("inputTokens", "outputTokens", "totalTokens"))
            if not invalid:
                invalid |= usage["inputTokens"] + usage["outputTokens"] != used
        if proofs and proofs[-1].get("context_window") is not None:
            invalid |= proofs[-1]["context_window"] != capacity
        source_time = datetime.fromtimestamp(assistant["timestamp"] / 1000, timezone.utc).isoformat() if assistant else None
        return {"native_session_id": sid, "session_revision": len(rows), "native_sha256": hashlib.sha256(data).hexdigest(),
                "observed_at": now_iso(), "used_tokens": used, "context_window": capacity,
                "source_time": source_time, "metrics_missing": missing, "metrics_invalid": bool(invalid),
                "terminal_reason": "completed" if assistant and assistant.get("status") == "completed" else "unknown"}, users

    async def query(self, sid):
        return self.snapshot(sid)

    def _record_proof(self, sid, text):
        events = [json.loads(line) for line in bytes(self._buffers[0]).splitlines() if line.strip().startswith(b"{")]
        init = [r for r in events if r.get("type") == "system" and r.get("subtype") == "init"]
        if len(init) != 1 or init[0].get("session_id") != sid or init[0].get("model") != self.spec.model:
            raise WorkBuddyNativeError("workbuddy_native_init_mismatch")
        acks = [r for r in events if r.get("type") == "user" and r.get("isReplay") is True]
        if len(acks) != 1 or acks[0].get("session_id") != sid or text_digest(_text(acks[0].get("message", {}).get("content"))) != text_digest(text):
            raise WorkBuddyNativeError("workbuddy_user_ack_invalid")
        ack = acks[0]
        rows = [json.loads(line) for line in self._path(sid).read_bytes().splitlines()]
        found = [r for r in rows if r.get("id") == ack.get("uuid") and r.get("role") == "user"]
        if (len(found) != 1 or found[0].get("sessionId") != sid or canonical(found[0].get("cwd", "")) != self.workdir
                or text_digest(_text(found[0].get("content"))) != text_digest(text)
                or found[0].get("providerData", {}).get("conversationRequestId") != ack.get("_requestId")):
            raise WorkBuddyNativeError("workbuddy_persisted_ack_invalid")
        results = [r for r in events if r.get("type") == "result"]
        if len(results) > 1 or any(r.get("session_id") != sid or r.get("_requestId") != ack.get("_requestId") for r in results):
            raise WorkBuddyNativeError("workbuddy_result_identity_mismatch")
        result = results[0] if results else {}
        models = result.get("modelUsage", {})
        if any(name != self.spec.model for name in models):
            raise WorkBuddyNativeError("workbuddy_native_model_mismatch")
        proof = {"user_id": ack["uuid"], "request_id": ack["_requestId"], "body_sha256": text_digest(text),
                 "fingerprint": self.fingerprint, "context_window": models.get(self.spec.model, {}).get("contextWindow")}
        target = self._proof_path(sid)
        target.parent.mkdir(exist_ok=True)
        with target.open("ab") as f:
            f.write((json.dumps(proof, sort_keys=True) + "\n").encode())
            f.flush()
            os.fsync(f.fileno())
        return result

    async def deliver(self, sid, text, timeout, *, expected_sha256):
        first = sid is None
        if not first and self.snapshot(sid)[0]["native_sha256"] != expected_sha256:
            raise WorkBuddyNativeError("workbuddy_native_history_changed")
        sid = str(uuid.uuid4()) if first else sid
        self.last_session_id = sid
        if first and list((self.home / "projects").glob("*/" + sid + ".jsonl")):
            raise WorkBuddyNativeError("workbuddy_native_id_collision")
        argv = self.spec.argv + ["-p", "--session-id" if first else "--resume", sid,
            "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--replay-user-messages"]
        self._buffers = [bytearray(), bytearray()]
        self.process = await asyncio.create_subprocess_exec(*argv, cwd=self.workdir, env=self.spec.env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}))
        async def read(stream, index):
            while chunk := await stream.read(65536):
                self._buffers[index].extend(chunk)
                if len(self._buffers[index]) > MAX_BYTES:
                    raise WorkBuddyNativeError("workbuddy_output_limit")
        self._streams = [asyncio.create_task(read(self.process.stdout, 0)), asyncio.create_task(read(self.process.stderr, 1))]
        body = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]},
                "session_id": sid, "parent_tool_use_id": None}
        interrupted = None
        try:
            async with asyncio.timeout(timeout):
                self.process.stdin.write((json.dumps(body, ensure_ascii=False) + "\n").encode())
                await self.process.stdin.drain()
                self.process.stdin.close()
                await asyncio.gather(*self._streams)
                await self.process.wait()
        except BaseException as exc:
            interrupted = exc
        finally:
            await asyncio.shield(self.close())
        result = self._record_proof(sid, text)
        if interrupted is not None:
            raise interrupted
        ok = self.process.returncode == 0 and result.get("subtype") == "success" and not result.get("is_error")
        return {"status": "completed" if ok else "failed", "reply": str(result.get("result") or ""), "rerouted": False}

    async def close(self):
        if self.process is not None and self.process.returncode is None:
            if os.name == "nt":
                killer = await asyncio.create_subprocess_exec("taskkill", "/PID", str(self.process.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                await asyncio.wait_for(killer.wait(), 10)
            else:
                import signal
                os.killpg(self.process.pid, signal.SIGTERM)
            await asyncio.wait_for(self.process.wait(), 10)
        for task in self._streams:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._streams, return_exceptions=True)
