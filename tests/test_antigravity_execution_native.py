import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from bridges import antigravity_execution_native as native_mod
from bridges.antigravity_execution_native import (
    AntigravityNative,
    AntigravityNativeError,
    MAX_SAFE_INTEGER,
    check_antigravity,
    clear_antigravity_probe_cache,
    detect_capabilities,
    discover_antigravity_models,
    extract_antigravity_final_reply,
    find_antigravity_executable,
    parse_antigravity_version,
    parse_stream_json_events,
    resolve_launch,
)


VALID_HELP = """\
Usage of agy.exe:
  --conversation          Resume a previous conversation by ID
  --disable-slash-commands Disable slash commands
  --effort                Reasoning effort (low|medium|high|xhigh|max)
  --mode                  Execution mode (accept-edits, auto, plan)
  --model                 Model for the current CLI session
  --output-format         Output format for print mode (text, json, stream-json)
  --print                 Run a single prompt non-interactively
  --print-timeout         Optional time limit for print mode
Available subcommands:
  models          List available models
"""

SAMPLE_CID = "65495240-12e6-49b8-989c-07c07cf90dfa"


def make_stream_json(
    *,
    cid: str = SAMPLE_CID,
    model: str = "gemini-4-hydrogen-low",
    cwd: str = "D:/work",
    response: str = "OK\n",
    status: str = "SUCCESS",
    total_tokens: int = 10625,
    context_window: int | None = None,
) -> str:
    init_body = {
        "model": model,
        "cwd": cwd,
        "tools": ["view_file"],
        "permission_mode": "request-review",
    }
    if context_window is not None:
        init_body["context_window"] = context_window
    return "\n".join(
        [
            json.dumps({"event": "init", "conversation_id": cid, "init": init_body}),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": cid,
                        "step_index": 1,
                        "state": "ACTIVE",
                        "step_type": "agent_response",
                        "text_delta": "OK",
                    },
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": cid,
                        "step_index": 1,
                        "state": "DONE",
                        "step_type": "agent_response",
                        "text_delta": "\n",
                        "usage": {
                            "input_tokens": max(0, total_tokens - 5),
                            "output_tokens": 5,
                            "thinking_tokens": 0,
                            "total_tokens": total_tokens,
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": cid,
                        "status": status,
                        "response": response,
                        "num_turns": 1,
                        "usage": {"total_tokens": total_tokens},
                    },
                }
            ),
        ]
    )


def setup_function():
    clear_antigravity_probe_cache()


def test_version_parsing_and_capabilities():
    assert parse_antigravity_version("1.5.16\n") == (1, 5, 16)
    with pytest.raises(AntigravityNativeError) as exc:
        parse_antigravity_version("no version")
    assert exc.value.reason_code == "antigravity_version_unparseable"

    caps = detect_capabilities(VALID_HELP)
    assert all(caps.values())
    missing = detect_capabilities(VALID_HELP.replace("--conversation", "--other"))
    assert not missing["--conversation"]


def test_check_antigravity_version_bounds_and_cache(tmp_path):
    fake_exe = tmp_path / "agy.exe"
    fake_exe.write_bytes(b"binary")

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv[1:])
        if argv[1] == "--version":
            return subprocess.CompletedProcess(argv, 0, stdout="1.5.16\n", stderr="")
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr=VALID_HELP)

    with patch.object(native_mod.subprocess, "run", side_effect=fake_run):
        first = check_antigravity(str(fake_exe), cwd=tmp_path)
        second = check_antigravity(str(fake_exe), cwd=tmp_path)
    assert first["allowed"] is True and first["warning"] is None
    assert second == first
    assert len(calls) == 2

    clear_antigravity_probe_cache()

    def newer_run(argv, **kwargs):
        if argv[1] == "--version":
            return subprocess.CompletedProcess(argv, 0, stdout="1.9.0\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout=VALID_HELP, stderr="")

    with patch.object(native_mod.subprocess, "run", side_effect=newer_run):
        newer = check_antigravity(str(fake_exe), cwd=tmp_path)
    assert newer["allowed"] is True
    assert newer["warning"] == "antigravity_version_untested"

    clear_antigravity_probe_cache()

    def old_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="1.4.9\n", stderr="")

    with patch.object(native_mod.subprocess, "run", side_effect=old_run):
        with pytest.raises(AntigravityNativeError) as exc:
            check_antigravity(str(fake_exe), cwd=tmp_path)
    assert exc.value.reason_code == "antigravity_version_unsupported"


def test_parse_stream_json_events_and_edge_cases():
    sample = make_stream_json()
    parsed = parse_stream_json_events(sample)
    assert parsed["parsed"] is True
    assert parsed["conversation_id"] == SAMPLE_CID
    assert parsed["model"] == "gemini-4-hydrogen-low"
    assert parsed["status"] == "SUCCESS"
    assert parsed["response"] == "OK\n"
    assert parsed["used_tokens"] == 10625
    assert parsed["context_window"] is None
    assert parsed["metrics_invalid"] is False
    assert extract_antigravity_final_reply(sample) == "OK"
    assert extract_antigravity_final_reply("plain text output") is None

    # Failed stream-json with empty response returns None so error stdout is not erased.
    err_stream = make_stream_json(response="", status="ERROR")
    assert extract_antigravity_final_reply(err_stream) is None

    # Mismatched conversation_id between events (including step_update) fails closed.
    bad_cid = sample.replace(SAMPLE_CID, "11111111-1111-4111-8111-111111111111", 1)
    with pytest.raises(AntigravityNativeError) as exc:
        parse_stream_json_events(bad_cid)
    assert exc.value.reason_code == "antigravity_session_id_mismatch"

    # When metrics_invalid triggers on a later step, stale earlier tokens & capacity MUST be cleared.
    corrupt_second = "\n".join(
        [
            json.dumps(
                {
                    "event": "init",
                    "conversation_id": SAMPLE_CID,
                    "init": {"model": "gemini-4-neon-high", "context_window": 200000},
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": SAMPLE_CID,
                        "step_type": "agent_response",
                        "state": "DONE",
                        "usage": {"total_tokens": 5000},
                    },
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": SAMPLE_CID,
                        "step_type": "agent_response",
                        "state": "DONE",
                        "usage": {"total_tokens": True},
                    },
                }
            ),
        ]
    )
    bad_metrics = parse_stream_json_events(corrupt_second)
    assert bad_metrics["metrics_invalid"] is True
    assert bad_metrics["used_tokens"] is None
    assert bad_metrics["context_window"] is None

    # Overflow above MAX_SAFE_INTEGER is flagged invalid.
    overflow = json.dumps(
        {
            "event": "step_update",
            "step_update": {
                "step_type": "agent_response",
                "state": "DONE",
                "usage": {"total_tokens": MAX_SAFE_INTEGER + 1},
            },
        }
    )
    assert parse_stream_json_events(overflow)["metrics_invalid"] is True

    # Step usage without total_tokens falls back to single-turn result.usage.
    partial_step = "\n".join(
        [
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "step_type": "agent_response",
                        "state": "DONE",
                        "usage": {"input_tokens": 100},
                    },
                }
            ),
            json.dumps(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": SAMPLE_CID,
                        "status": "SUCCESS",
                        "response": "ok",
                        "num_turns": 1,
                        "usage": {"total_tokens": 120},
                    },
                }
            ),
        ]
    )
    assert parse_stream_json_events(partial_step)["used_tokens"] == 120


def test_resolve_launch_validation_and_security(tmp_path):
    fake_exe = tmp_path / "agy" / "bin" / "agy.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_bytes(b"binary")
    binding = {
        "runner_id": "runner:antigravity-local",
        "provider_id": "google-antigravity",
        "model_id": "gemini-4-neon",
        "binding_fingerprint": "a" * 64,
    }
    cmd = [
        str(fake_exe),
        "--mode",
        "auto",
        "--sandbox",
        "--disable-slash-commands",
        "--output-format",
        "stream-json",
        "--print-timeout",
        "0",
        "--model",
        "gemini-4-neon-xhigh",
        "--effort",
        "xhigh",
        "-p",
    ]
    spec = resolve_launch(cmd, tmp_path, binding, check_cli=False)
    assert spec.base_model == "gemini-4-neon"
    assert spec.cli_model == "gemini-4-neon-xhigh"
    assert spec.effort == "xhigh"

    # Bare "agy" resolves through LOCALAPPDATA fallback when not on PATH.
    bare_spec = resolve_launch(
        ["agy", *cmd[1:]],
        tmp_path,
        binding,
        env={"PATH": "", "LOCALAPPDATA": str(tmp_path)},
        check_cli=False,
    )
    assert Path(bare_spec.argv[0]) == fake_exe.resolve()

    # Effort flag contradicting model suffix must be rejected.
    bad_effort = [*cmd[:-2], "low", "-p"]
    with pytest.raises(AntigravityNativeError) as exc:
        resolve_launch(bad_effort, tmp_path, binding, check_cli=False)
    assert exc.value.reason_code == "antigravity_effort_mismatch"

    # Binding mismatch (Carbon binding vs Neon command) must be rejected.
    carbon_binding = {**binding, "model_id": "gemini-4-carbon"}
    with pytest.raises(AntigravityNativeError) as exc:
        resolve_launch(cmd, tmp_path, carbon_binding, check_cli=False)
    assert exc.value.reason_code == "antigravity_model_binding_mismatch"

    # Uncontrolled --settings / --agent / --project flags must be rejected fail-closed.
    for extra in (["--settings", '{"sandbox":false}'], ["--agent", "admin"], ["--project", "other"]):
        with pytest.raises(AntigravityNativeError) as exc:
            resolve_launch([cmd[0], *extra, *cmd[1:]], tmp_path, binding, check_cli=False)
        assert exc.value.reason_code == "antigravity_command_unsupported"

    # Mutually exclusive --sandbox + --dangerously-skip-permissions must be rejected.
    with pytest.raises(AntigravityNativeError) as exc:
        resolve_launch([cmd[0], "--dangerously-skip-permissions", *cmd[1:]], tmp_path, binding, check_cli=False)
    assert exc.value.reason_code == "antigravity_command_unsupported"

    # Invalid --mode value must be rejected.
    bad_mode = [cmd[0], "--mode", "unsafe-mode", *cmd[3:]]
    with pytest.raises(AntigravityNativeError) as exc:
        resolve_launch(bad_mode, tmp_path, binding, check_cli=False)
    assert exc.value.reason_code == "antigravity_command_unsupported"


def test_antigravity_native_disk_proof_resume_cwd_check_and_close_timeout(tmp_path):
    fake_exe = tmp_path / "agy.exe"
    fake_exe.write_bytes(b"binary")
    workdir = tmp_path / "work"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    binding = {
        "runner_id": "runner:antigravity-local",
        "provider_id": "google-antigravity",
        "model_id": "gemini-4-hydrogen",
        "binding_fingerprint": "b" * 64,
    }
    cmd = [
        str(fake_exe),
        "--mode",
        "auto",
        "--sandbox",
        "--output-format",
        "stream-json",
        "--model",
        "gemini-4-hydrogen-low",
        "--effort",
        "low",
        "-p",
    ]
    spec = resolve_launch(cmd, workdir, binding, env={"ANTIGRAVITY_HOME": str(home)}, check_cli=False)
    spawned_argvs = []

    class FakeStream:
        def __init__(self, data: bytes):
            self._data = data
            self._sent = False

        async def read(self, n: int) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return self._data

    class FakeProc:
        def __init__(self, out: bytes, rc: int = 0):
            self.pid = 99999
            self.returncode = rc
            self.stdout = FakeStream(out)
            self.stderr = FakeStream(b"")

        async def wait(self) -> int:
            return self.returncode

    async def fake_exec(*argv, **kwargs):
        spawned_argvs.append(list(argv))
        return FakeProc(make_stream_json(cwd=str(workdir)).encode("utf-8"), rc=0)

    async def scenario():
        with patch.object(native_mod.asyncio, "create_subprocess_exec", side_effect=fake_exec):
            runner1 = AntigravityNative(spec, workdir)
            r1 = await runner1.deliver(None, "turn-1", 30)
            assert r1["status"] == "completed" and r1["reply"] == "OK"
            assert runner1.last_session_id == SAMPLE_CID
            snap1, users1 = runner1.snapshot(SAMPLE_CID)
            assert len(users1) == 1 and users1[0][0] == 0

            # Brand-new AntigravityNative instance must verify Turn 1 via disk proof and resume cleanly.
            runner2 = AntigravityNative(spec, workdir)
            queried_snap, _ = await runner2.query(SAMPLE_CID)
            assert queried_snap["native_sha256"] == snap1["native_sha256"]
            r2 = await runner2.deliver(SAMPLE_CID, "turn-2", 30, expected_sha256=snap1["native_sha256"])
            assert r2["status"] == "completed"
            snap2, users2 = runner2.snapshot(SAMPLE_CID)
            assert len(users2) == 2 and users2[1][0] == snap1["session_revision"]
            assert snap2["session_revision"] > snap1["session_revision"]

        # Mismatched init.cwd must be rejected fail-closed.
        async def bad_cwd_exec(*argv, **kwargs):
            return FakeProc(make_stream_json(cwd=str(tmp_path / "wrong")).encode("utf-8"), rc=0)

        with patch.object(native_mod.asyncio, "create_subprocess_exec", side_effect=bad_cwd_exec):
            runner3 = AntigravityNative(spec, workdir)
            with pytest.raises(AntigravityNativeError) as exc:
                await runner3.deliver(None, "turn-bad-cwd", 30)
            assert exc.value.reason_code == "antigravity_workspace_mismatch"

        # close() MUST NOT swallow TimeoutError when process refuses to exit.
        class HungProc:
            pid = 88888
            returncode = None

            async def wait(self):
                await asyncio.sleep(60)

        def _timeout_wait(coro, _timeout):
            coro.close()
            raise asyncio.TimeoutError()

        runner4 = AntigravityNative(spec, workdir)
        runner4.process = HungProc()
        with patch.object(native_mod.asyncio, "create_subprocess_exec", return_value=FakeProc(b"", rc=0)), \
             patch.object(native_mod.asyncio, "wait_for", side_effect=_timeout_wait):
            with pytest.raises(asyncio.TimeoutError):
                await runner4.close()

    asyncio.run(scenario())
    assert "--conversation" not in spawned_argvs[0]
    assert spawned_argvs[0][-2:] == ["-p", "turn-1"]
    assert "--conversation" in spawned_argvs[1]
    assert SAMPLE_CID in spawned_argvs[1]
    assert spawned_argvs[1][-2:] == ["-p", "turn-2"]


def test_local_installed_agy_readonly_probe():
    """If agy CLI is installed on this host, verify real read-only --version/--help/models."""
    exe = find_antigravity_executable()
    if not exe:
        pytest.skip("agy CLI not installed on this host")
    info = check_antigravity(exe, use_cache=False)
    assert info["allowed"] is True
    assert all(info["capabilities"].values())
    models = discover_antigravity_models(exe)
    by_id = {m["model_id"]: m for m in models}
    assert set(by_id) == {"gemini-4-neon", "gemini-4-carbon", "gemini-4-hydrogen"}
    assert by_id["gemini-4-neon"]["supported_efforts"] == ["low", "medium", "high", "xhigh"]
    assert by_id["gemini-4-carbon"]["supported_efforts"] == ["low", "medium", "high"]
    assert by_id["gemini-4-hydrogen"]["supported_efforts"] == ["low", "medium", "high", "xhigh"]
