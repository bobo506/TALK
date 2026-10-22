"""Kimi Code 2.0.2 的受控原生 prompt/resume 接口，K2.8/K3 共用。

只读取本通道创建的原生会话。额度/认证不在此处理；不改 HOME、模型或
Agent 权限。首次 ID 由 CLI 创建后确认，绝不将本地占位符冒充原生 ID。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

SUPPORTED_VERSION = "2.0.2"
SESSION_RE = re.compile(r"^session_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAX_WIRE_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024


class KimiNativeError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.reason_code = code


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return not path.is_symlink()
    except (ValueError, OSError):
        return False


def _public_config(value):
    # Credential values are neither retained nor hashed into the inventory.
    if isinstance(value, dict):
        return {k: _public_config(v) for k, v in value.items()
            if not any(s in k.lower().replace("_", "") for s in ("apikey", "token", "secret", "password", "customheaders"))}
    if isinstance(value, list):
        return [_public_config(v) for v in value]
    return value


def _load_config(home: Path, workdir: Path):
    result, inventory = {}, {}
    # Project-level model/config overrides are not guessed or merged here.
    if (workdir / ".kimi-code/config.toml").exists():
        raise KimiNativeError("kimi_project_config_unsupported")
    for name in ("config.toml", "mcp.json"):
        path = home / name
        if path.exists():
            if not _inside(path, home) or path.stat().st_size > 2 * 1024 * 1024:
                raise KimiNativeError("kimi_config_unusable")
            raw = path.read_text(encoding="utf-8")
            data = tomllib.loads(raw) if name.endswith("toml") else json.loads(raw)
            inventory[name] = _public_config(data)
            if name == "config.toml":
                result = data
    return result, inventory


@dataclass
class LaunchSpec:
    argv: list[str]
    env: dict[str, str]
    home: Path
    alias: str
    model: str
    provider: str
    capacity: int | None
    profile_name: str
    system_prompt: str
    tools: tuple[str, ...]
    fingerprint: str
    config_fingerprint: str


def resolve_launch(command: Sequence[str], workdir: Path, binding: Mapping[str, Any]) -> LaunchSpec:
    argv = list(map(str, command))
    if not argv:
        raise KimiNativeError("kimi_command_unsupported")
    executable = Path(shutil.which(argv[0]) or argv[0]).resolve()
    if executable.name.lower() not in {"kimi", "kimi.exe"} or not executable.is_file():
        raise KimiNativeError("kimi_native_executable_required")
    flags = {}
    i = 1
    while i < len(argv):
        flag = argv[i]
        if flag == "-p" and i == len(argv) - 1:
            i += 1
            continue
        if flag not in {"--model", "--output-format", "--agent-file", "--skills-dir"} or flag in flags or i + 1 >= len(argv):
            raise KimiNativeError("kimi_command_unsupported")
        flags[flag] = argv[i + 1]
        i += 2
    if set(flags) != {"--model", "--output-format", "--agent-file", "--skills-dir"} or argv[-1] != "-p" or flags["--output-format"] != "stream-json":
        raise KimiNativeError("kimi_command_unsupported")
    env = dict(os.environ)
    if any(k.startswith("KIMI_MODEL_") and v for k, v in env.items()):
        raise KimiNativeError("kimi_model_environment_unsupported")
    raw_home = env.get("KIMI_CODE_HOME", "")
    if not raw_home or not Path(raw_home).is_absolute() or not Path(raw_home).is_dir():
        raise KimiNativeError("kimi_home_required")
    home = Path(raw_home).resolve()
    config, inventory = _load_config(home, workdir)
    alias = flags["--model"]
    model = config.get("models", {}).get(alias)
    if not isinstance(model, dict):
        raise KimiNativeError("kimi_model_config_missing")
    model_name = model.get("model") or model.get("name")
    provider = model.get("provider") or model.get("protocol")
    if alias != binding.get("model_alias") or model_name != binding.get("model_id") or provider != binding.get("provider_id"):
        raise KimiNativeError("kimi_model_binding_mismatch")
    capacity = model.get("max_context_size", model.get("maxContextSize"))
    if capacity is not None and (type(capacity) is not int or capacity <= 0):
        raise KimiNativeError("kimi_capacity_invalid")
    skills, profile = Path(flags["--skills-dir"]).resolve(), Path(flags["--agent-file"]).resolve()
    if not skills.is_dir() or any(skills.iterdir()) or not profile.is_file() or profile.stat().st_size > 1024 * 1024:
        raise KimiNativeError("kimi_profile_unusable")
    raw_profile = profile.read_text(encoding="utf-8")
    parts = raw_profile.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise KimiNativeError("kimi_profile_unusable")
    meta = yaml.safe_load(parts[1])
    from bridges.kimi_bridge import KIMI_REVIEW_TOOLS, KIMI_FULL_TOOLS
    tools = meta.get("tools")
    if not isinstance(tools, list) or tuple(tools) not in {(), KIMI_REVIEW_TOOLS, KIMI_FULL_TOOLS} or meta.get("subagents") != []:
        raise KimiNativeError("kimi_profile_permissions_unsupported")
    version = subprocess.run([str(executable), "--version"], capture_output=True, text=True,
        encoding="utf-8", timeout=15, check=True,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    if version.stdout.strip() != SUPPORTED_VERSION:
        raise KimiNativeError("kimi_version_unsupported")
    config_hash = digest(inventory)
    return LaunchSpec([str(executable), *argv[1:]], env, home, alias, str(model_name), str(provider), capacity,
        meta["name"], parts[2].strip(), tuple(tools), digest({"version": SUPPORTED_VERSION,
            "executable": str(executable), "profile": raw_profile, "skills": str(skills),
            "home": str(home), "model": alias, "config": config_hash}), config_hash)


def _content_text(parts):
    if not isinstance(parts, list) or any(not isinstance(p, dict) or p.get("type") != "text" or not isinstance(p.get("text"), str) for p in parts):
        raise KimiNativeError("kimi_prompt_content_unsupported")
    return "".join(p["text"] for p in parts)


def read_session(directory: Path, spec: LaunchSpec, workdir: Path):
    sid = directory.name
    if not SESSION_RE.fullmatch(sid) or not _inside(directory, spec.home / "sessions"):
        raise KimiNativeError("kimi_session_path_invalid")
    state_path, wire = directory / "state.json", directory / "agents/main/wire.jsonl"
    if not _inside(state_path, directory) or not _inside(wire, directory) or state_path.stat().st_size > 1024 * 1024 or wire.stat().st_size > MAX_WIRE_BYTES:
        raise KimiNativeError("kimi_session_unreadable")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if (state.get("id") != sid or state.get("version") != 2 or state.get("archived") is not False
            or Path(state.get("cwd", "")).resolve() != workdir.resolve()
            or set(state.get("agents", {})) != {"main"}
            or Path(state["agents"]["main"].get("homedir", "")).resolve() != wire.parent.resolve()):
        raise KimiNativeError("kimi_session_identity_mismatch")
    raw = wire.read_bytes()
    if not raw.endswith(b"\n"):
        raise KimiNativeError("kimi_wire_incomplete")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    if not rows or rows[0].get("type") != "metadata" or rows[0].get("protocol_version") != "1.5":
        raise KimiNativeError("kimi_wire_protocol_unsupported")
    users, prompts, messages = [], {}, {}
    used = source_time = None
    invalid = False
    profile_seen = False
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("type"), str):
            raise KimiNativeError("kimi_wire_invalid")
        kind = row["type"]
        if row.get("agentId", "main") != "main":
            raise KimiNativeError("kimi_foreign_agent")
        if kind == "profile.bind":
            profile_seen = True
            if (row.get("profileName") != spec.profile_name or row.get("modelAlias") != spec.alias
                    or row.get("systemPrompt") != spec.system_prompt
                    or row.get("activeToolNames") != list(spec.tools) or row.get("subagents") != []
                    or row.get("disallowedTools") != []):
                raise KimiNativeError("kimi_profile_changed")
        elif kind == "config.update":
            expected = {"modelAlias": spec.alias, "profileName": spec.profile_name, "systemPrompt": spec.system_prompt, "disallowedTools": []}
            if any(k in row and row[k] != v for k, v in expected.items()):
                raise KimiNativeError("kimi_profile_changed")
        elif kind in {"tools.reset_active_tools", "profile.unbind"}:
            raise KimiNativeError("kimi_profile_changed")
        elif kind == "tools.set_active_tools" and row.get("names") != list(spec.tools):
            raise KimiNativeError("kimi_profile_changed")
        elif kind == "llm.request" and (row.get("modelAlias") != spec.alias or row.get("model") != spec.model):
            raise KimiNativeError("kimi_native_model_mismatch")
        elif kind == "turn.prompt" and row.get("origin", {}).get("kind") == "user":
            prompt_id = row.get("promptId")
            if not isinstance(prompt_id, str) or prompt_id in prompts:
                raise KimiNativeError("kimi_prompt_identity_invalid")
            prompts[prompt_id] = (index, text_digest(_content_text(row.get("input"))))
        elif kind == "context.append_message":
            message = row.get("message", {})
            if message.get("role") == "user" and message.get("origin", {}).get("kind") == "user":
                mid = message.get("id")
                if not isinstance(mid, str) or mid in messages:
                    raise KimiNativeError("kimi_prompt_identity_invalid")
                messages[mid] = text_digest(_content_text(message.get("content")))
        elif kind in {"token_counting.measured", "token_counting.turn_recorded", "token_counting.truncated", "token_counting.rebased"}:
            tokens, stamp = row.get("tokens"), row.get("time")
            if type(tokens) is not int or tokens < 0 or type(stamp) is not int or stamp <= 0 or stamp > int(datetime.now(timezone.utc).timestamp() * 1000):
                invalid = True
            else:
                used, source_time = tokens, datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat()
    if not profile_seen or set(prompts) != set(messages):
        raise KimiNativeError("kimi_native_delivery_ambiguous")
    for mid, (index, sha) in prompts.items():
        if messages[mid] != sha:
            raise KimiNativeError("kimi_native_delivery_ambiguous")
        users.append((index, sha))
    # maxTokens in llm.request is an OUTPUT budget, never a context capacity.
    return {"schema": "talk-kimi-context-snapshot-1", "native_session_id": sid,
        "session_revision": len(rows), "native_sha256": hashlib.sha256(raw).hexdigest(),
        "state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(), "observed_at": now_iso(),
        "source_time": source_time, "used_tokens": used, "context_window": spec.capacity,
        "metrics_missing": used is None or spec.capacity is None, "metrics_invalid": invalid,
        "terminal_reason": state.get("lastTurnReason")}, users


class KimiNative:
    def __init__(self, spec: LaunchSpec, workdir: Path):
        self.spec, self.home, self.fingerprint, self.workdir = spec, spec.home, spec.fingerprint, workdir
        self.process = None
        self.last_session_id = None
        self._streams = []

    async def open(self):
        pass

    def _directories(self):
        return {p.resolve() for p in (self.home / "sessions").glob("*/session_*") if p.is_dir()}

    def _directory(self, sid):
        if not isinstance(sid, str) or not SESSION_RE.fullmatch(sid):
            raise KimiNativeError("kimi_session_id_invalid")
        found = list((self.home / "sessions").glob("*/" + sid))
        if len(found) != 1:
            raise KimiNativeError("kimi_session_missing_or_ambiguous")
        return found[0]

    def snapshot(self, sid):
        _, inventory = _load_config(self.home, self.workdir)
        if digest(inventory) != self.spec.config_fingerprint:
            raise KimiNativeError("kimi_config_changed")
        return read_session(self._directory(sid), self.spec, self.workdir)

    async def query(self, sid):
        # No process, model, or native history write is needed for this query.
        return self.snapshot(sid)

    async def deliver(self, sid, text, timeout, *, expected_sha256):
        if sid is not None and self.snapshot(sid)[0]["native_sha256"] != expected_sha256:
            raise KimiNativeError("kimi_native_history_changed")
        before = self._directories()
        argv = self.spec.argv[:-1]
        if sid is not None:
            at = argv.index("--agent-file")
            argv = argv[:at] + argv[at + 2:]
            argv += ["--session", sid]
        argv += ["-p", text]
        if os.name == "nt" and len(subprocess.list2cmdline(argv)) >= 32760:
            raise KimiNativeError("kimi_windows_command_line_limit")
        self.last_session_id = sid
        self.process = await asyncio.create_subprocess_exec(*argv, cwd=self.workdir, env=self.spec.env,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}))
        async def read(stream):
            data = bytearray()
            while chunk := await stream.read(65536):
                data.extend(chunk)
                if len(data) > MAX_OUTPUT_BYTES:
                    raise KimiNativeError("kimi_output_limit")
            return bytes(data)
        self._streams = [asyncio.create_task(read(self.process.stdout)), asyncio.create_task(read(self.process.stderr))]
        output = b""
        try:
            async with asyncio.timeout(timeout):
                output, _ = await asyncio.gather(*self._streams)
                await self.process.wait()
        finally:
            await asyncio.shield(self.close())
            # Locate only fresh native sessions from this spawn. Exact directive
            # SHA disambiguates a concurrent unrelated terminal's new session.
            if sid is None:
                matches = []
                for directory in self._directories() - before:
                    try:
                        snapshot, users = read_session(directory, self.spec, self.workdir)
                        if [sha for _, sha in users] == [text_digest(text)]:
                            matches.append(directory.name)
                    except (KimiNativeError, OSError, ValueError, KeyError):
                        continue
                if len(matches) == 1:
                    self.last_session_id = matches[0]
        if self.last_session_id is None:
            raise KimiNativeError("kimi_new_session_unconfirmed")
        from bridges.cli_bridge import extract_kimi_final_assistant
        text_output = output.decode("utf-8")
        hints = [json.loads(line).get("session_id") for line in text_output.splitlines()
            if line.strip().startswith("{") and json.loads(line).get("type") == "session.resume_hint"]
        if hints and hints != [self.last_session_id]:
            raise KimiNativeError("kimi_resume_hint_mismatch")
        snapshot, _ = self.snapshot(self.last_session_id)
        ok = self.process.returncode == 0 and snapshot["terminal_reason"] == "completed"
        return {"status": "completed" if ok else "failed", "reply": extract_kimi_final_assistant(text_output) or "", "rerouted": False}

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
