import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bridges import antigravity_bridge as ab
from bridges import antigravity_execution_native as native_mod
from bridges import cli_bridge
from bridges.antigravity_effort import AntigravityEffortUnavailable
from bridges.antigravity_execution_channel import run_execution_session_task
from bridges.antigravity_execution_native import text_digest
from bridges.dsh_execution_channel import ExecutionSessionRunError, _workspace_identity
from server.models import Project, ProjectAgent, ProjectRoleBinding, RunnerRegistry, resolve_role_effort
from tests.test_support import RouteTestCase


def _make_agy_stream(cid, *, model, cwd, reply="ok\n", total_tokens=100, context_window=1000):
    init_body = {"model": model, "cwd": str(cwd)}
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
                        "state": "DONE",
                        "step_type": "agent_response",
                        "text_delta": reply,
                        "usage": {"total_tokens": total_tokens},
                    },
                }
            ),
            json.dumps(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": cid,
                        "status": "SUCCESS",
                        "response": reply,
                        "num_turns": 1,
                        "usage": {"total_tokens": total_tokens},
                    },
                }
            ),
        ]
    )


def test_parser_uses_valid_argv_prompt_transport_and_none_default_model():
    args = ab.build_parser().parse_args([])
    assert args.prompt_transport == "argv"
    assert args.prompt_transport in cli_bridge.PROMPT_TRANSPORTS
    assert args.antigravity_model is None


def test_build_antigravity_command_profiles():
    review_cmd = ab.build_antigravity_command("agy", model="gemini-4-neon", effort="xhigh", profile="review")
    review_tokens = cli_bridge.parse_command(review_cmd)
    assert "--sandbox" in review_tokens
    assert "--dangerously-skip-permissions" not in review_tokens
    assert "--mode" in review_tokens and review_tokens[review_tokens.index("--mode") + 1] == "auto"
    assert "--model" in review_tokens and review_tokens[review_tokens.index("--model") + 1] == "gemini-4-neon-xhigh"
    assert "--effort" in review_tokens and review_tokens[review_tokens.index("--effort") + 1] == "xhigh"
    assert review_tokens[-1] == "-p"

    tools_cmd = ab.build_antigravity_command("agy", model="gemini-4-carbon", effort="medium", profile="tools")
    tools_tokens = cli_bridge.parse_command(tools_cmd)
    assert "--dangerously-skip-permissions" in tools_tokens
    assert "--sandbox" not in tools_tokens
    assert tools_tokens[tools_tokens.index("--model") + 1] == "gemini-4-carbon-medium"

    with pytest.raises(AntigravityEffortUnavailable):
        ab.build_antigravity_command("agy", model="gemini-4-carbon", effort="xhigh", profile="review")
    with pytest.raises(AntigravityEffortUnavailable):
        ab.build_antigravity_command("agy", model="gemini-4-neon", effort="", profile="review")


def test_make_effort_hook_preserves_carbon_command_and_is_atomic():
    class FakeClient:
        def __init__(self, binding):
            self.binding = binding

        async def _request_json(self, method, path):
            return [{"member_id": "agent:antigravity", "binding": self.binding}]

    # Carbon role launched via --antigravity-command (without --antigravity-model) MUST NOT be hijacked to Neon.
    carbon_cmd = ab.build_antigravity_command("agy", model="gemini-4-carbon", effort="high", profile="tools")
    parsed_args = ab.build_parser().parse_args(["--antigravity-command", carbon_cmd])
    parsed_args.task_command = carbon_cmd
    parsed_args.task_preflight_command = carbon_cmd
    parsed_args.task_command_template = carbon_cmd
    parsed_args.task_preflight_command_template = carbon_cmd

    # Valid Carbon override medium → stays Carbon.
    hook_ok = ab.make_effort_hook(
        FakeClient(
            {
                "model_id": "gemini-4-carbon",
                "effective_effort": "medium",
                "effort_override": "medium",
                "effort_options": ["low", "medium", "high"],
                "effort_source": "catalog",
            }
        ),
        parsed_args,
    )
    asyncio.run(hook_ok({"project_id": "prj_test"}))
    assert "--model gemini-4-carbon-medium" in parsed_args.task_command
    assert "gemini-4-neon" not in parsed_args.task_command

    # Invalid Carbon override xhigh → rejected fail-closed (never rewritten to neon-xhigh!).
    hook_bad = ab.make_effort_hook(
        FakeClient(
            {
                "model_id": "gemini-4-carbon",
                "effective_effort": "xhigh",
                "effort_override": "xhigh",
                "effort_options": ["low", "medium", "high", "xhigh"],
                "effort_source": "adapter",
            }
        ),
        parsed_args,
    )
    with pytest.raises(cli_bridge.TaskPreflightError, match="antigravity_effort_unavailable"):
        asyncio.run(hook_bad({"project_id": "prj_test"}))
    assert "--model gemini-4-carbon-high" in parsed_args.task_command

    # Atomic rewrite: if preflight command is unrecognized and no override is set, task_command must NOT be partially mutated.
    neon_cmd = ab.build_antigravity_command("agy", model="gemini-4-neon", effort="high", profile="tools")
    atomic_args = SimpleNamespace(
        name="antigravity",
        antigravity_model=None,
        task_command=neon_cmd,
        task_preflight_command="custom-unrecognized-tool",
        task_command_template=neon_cmd,
        task_preflight_command_template="custom-unrecognized-tool",
    )
    hook_atomic = ab.make_effort_hook(
        FakeClient(
            {
                "model_id": "gemini-4-neon",
                "effective_effort": "low",
                "effort_override": None,
                "effort_options": ["low", "medium", "high", "xhigh"],
                "effort_source": "catalog",
            }
        ),
        atomic_args,
    )
    asyncio.run(hook_atomic({"project_id": "prj_test"}))
    assert atomic_args.task_command == neon_cmd


def test_cli_bridge_normalize_runtime_result_for_antigravity():
    stream = _make_agy_stream(
        "65495240-12e6-49b8-989c-07c07cf90dfa",
        model="gemini-4-neon-high",
        cwd="D:/work",
        reply='{"schema":"talk-delivery-1"}\n',
    )
    raw = cli_bridge.CliRunResult(returncode=0, stdout=stream, stderr="", timed_out=False)
    normalized = cli_bridge.normalize_runtime_result(raw, runtime="antigravity")
    assert normalized.stdout == '{"schema":"talk-delivery-1"}'


def test_server_resolve_role_effort_respects_carbon_three_levels():
    neon = resolve_role_effort({"runtime": "antigravity", "model_id": "gemini-4-neon", "default_effort": "high"})
    assert neon["effort_source"] == "adapter"
    assert neon["effort_options"] == ["low", "medium", "high", "xhigh"]

    # Carbon without catalog supported_efforts MUST STILL only advertise low/medium/high (no xhigh!).
    carbon = resolve_role_effort({"runtime": "antigravity", "model_id": "gemini-4-carbon", "default_effort": "high"})
    assert carbon["effort_source"] == "adapter"
    assert carbon["effort_options"] == ["low", "medium", "high"]

    carbon_suffixed = resolve_role_effort({"runtime": "antigravity", "model_alias": "gemini-4-carbon-high"})
    assert carbon_suffixed["effort_options"] == ["low", "medium", "high"]


class TestAntigravityEffortApi(RouteTestCase):
    def test_put_effort_rejects_xhigh_for_carbon_without_catalog(self):
        self.add_member("human:test", api_key="human-key")
        self.add_member("agent:agy-carbon", api_key="agent-key")
        with self.session() as session:
            session.add(Project(project_id="prj_agy", display_name="Agy", maintainer_member_id="human:test"))
            session.add(ProjectAgent(project_id="prj_agy", member_id="agent:agy-carbon"))
            session.add(
                RunnerRegistry(
                    runner_id="runner:antigravity-local",
                    runtime="antigravity",
                    display_name="Antigravity CLI",
                    created_by="human:test",
                )
            )
            session.add(
                ProjectRoleBinding(
                    project_id="prj_agy",
                    member_id="agent:agy-carbon",
                    runner_id="runner:antigravity-local",
                    model_source="native_config",
                    provider_id="google-antigravity",
                    connection_ref="default",
                    model_id="gemini-4-carbon",
                    model_alias="gemini-4-carbon",
                    model_display_name="Gemini 4 Carbon",
                    default_effort="high",
                    supported_efforts=None,
                    updated_by="human:test",
                )
            )
            session.commit()
        with self.make_client() as client:
            bad = client.put(
                "/api/projects/prj_agy/roles/agent:agy-carbon/binding/effort",
                headers={"X-API-Key": "human-key"},
                json={"effort": "xhigh"},
            )
            self.assertEqual(bad.status_code, 422, bad.text)
            ok = client.put(
                "/api/projects/prj_agy/roles/agent:agy-carbon/binding/effort",
                headers={"X-API-Key": "human-key"},
                json={"effort": "medium"},
            )
            self.assertEqual(ok.status_code, 200, ok.text)
            binding_out = ok.json()["binding"]
            self.assertEqual(binding_out["effort_override"], "medium")
            self.assertEqual(binding_out["effort_options"], ["low", "medium", "high"])


def test_execution_channel_cross_task_fresh_native_reuse_rollover_and_cli_bridge_routing(tmp_path):
    """End-to-end test with runner=None (fresh AntigravityNative per task) AND cli_bridge.handle_queued_task."""
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    fake_exe = tmp_path / "agy.exe"
    fake_exe.write_bytes(b"binary")
    store_path = str(tmp_path / "sessions.sqlite")
    ws_id = _workspace_identity(workdir)
    fp = "c" * 64
    binding = {
        "state": "bound",
        "runtime": "antigravity",
        "runner_id": "runner:antigravity-local",
        "provider_id": "google-antigravity",
        "model_id": "gemini-4-neon",
        "binding_fingerprint": fp,
    }
    base_text = "BASE CONTRACT"
    base_sha = text_digest(base_text)
    command = cli_bridge.parse_command(
        ab.build_antigravity_command(str(fake_exe), model="gemini-4-neon", effort="high", profile="review")
    )

    class FakeClient:
        def __init__(self):
            self.claimed_ids = []
            self.completed = []
            self.sent = []

        async def get_execution_session_base(self, tid):
            return {
                "task_id": tid,
                "continuity_key": "agy-line-1",
                "project_id": "prj_test",
                "requester_id": "human:operator",
                "target_member_id": "agent:agy-neon",
                "base_contract_version": "1",
                "base_contract_sha256": base_sha,
                "binding_fingerprint": fp,
                "workspace_root": str(workdir),
                "workspace_identity": ws_id,
                "base_context": base_text,
            }

        async def claim_task(self, tid, **kwargs):
            self.claimed_ids.append(tid)
            return {**make_task(tid), "claim_token": "tok-1", "hall_group_id": "grp_task"}

        async def heartbeat_task(self, *args, **kwargs):
            return {"ok": True}

        async def send_message(self, content, **kwargs):
            self.sent.append(content)
            return {"id": 99}

        async def send_text(self, content, **kwargs):
            self.sent.append(content)
            return {"id": 99}

        async def complete_task(self, tid, **kwargs):
            self.completed.append((tid, kwargs))
            return {"id": tid, "status": kwargs.get("status")}

        async def list_messages(self, *args, **kwargs):
            return []

    def make_task(task_id, base_task_id=None):
        meta = {
            "schema": "talk-execution-session-request-1",
            "version": 1,
            "project_id": "prj_test",
            "target_member_id": "agent:agy-neon",
            "requester_id": "human:operator",
            "continuity_key": "agy-line-1",
            "runtime": "antigravity",
            "binding_fingerprint": fp,
            "workspace_root": str(workdir),
            "workspace_identity": ws_id,
            "base_contract_version": "1",
            "base_contract_sha256": base_sha,
        }
        if base_task_id is not None:
            meta["base_task_id"] = base_task_id
        return {
            "id": task_id,
            "attempt": 1,
            "project_id": "prj_test",
            "target_member_id": "agent:agy-neon",
            "created_by": "human:operator",
            "task_kind": "general",
            "parent_task_id": None,
            "content": f"task-{task_id}",
            "target_binding_snapshot": binding,
            "execution_session": meta,
            "execution_session_base_text": base_text if base_task_id is None else None,
        }

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
            self.pid = 77777
            self.returncode = rc
            self.stdout = FakeStream(out)
            self.stderr = FakeStream(b"")

        async def wait(self) -> int:
            return self.returncode

    turn_plans = [
        ("65495240-12e6-49b8-989c-07c07cf90df1", 100, 1000),  # Turn 1: 10%
        ("65495240-12e6-49b8-989c-07c07cf90df1", 900, 1000),  # Turn 2: reuses sid1, hits 90%
        ("65495240-12e6-49b8-989c-07c07cf90df2", 50, None),   # Turn 3: rolls over, unknown capacity
        ("65495240-12e6-49b8-989c-07c07cf90df3", 60, 1000),   # Turn 4: rolls over (new_context_unknown)
        ("65495240-12e6-49b8-989c-07c07cf90df3", 80, 1000),   # Turn 5: via cli_bridge.handle_queued_task
    ]
    spawned = []

    async def fake_exec(*argv, **kwargs):
        idx = len(spawned)
        spawned.append(list(argv))
        cid, tokens, cap = turn_plans[idx]
        payload = _make_agy_stream(
            cid,
            model="gemini-4-neon-high",
            cwd=workdir,
            reply=f"done-{idx + 1}\n",
            total_tokens=tokens,
            context_window=cap,
        )
        return FakeProc(payload.encode("utf-8"), rc=0)

    async def scenario():
        client = FakeClient()
        env_patch = {"ANTIGRAVITY_HOME": str(home)}
        with patch.dict("os.environ", env_patch, clear=False), \
             patch.object(native_mod, "check_antigravity", return_value={"version": "1.5.16", "allowed": True, "capabilities": {}, "warning": None}), \
             patch.object(native_mod.asyncio, "create_subprocess_exec", side_effect=fake_exec):
            # Turn 1 (fresh AntigravityNative, runner=None)
            o1 = await run_execution_session_task(
                task=make_task(101), client=client, member_id="agent:agy-neon", workdir=workdir,
                command=command, timeout=30, launch_id="launch-1", project_id="prj_test",
                binding_snapshot=binding, store_override=store_path, runner=None,
            )
            assert o1.completion_status == "succeeded" and o1.state["reused"] is False
            sid1 = o1.state["native_session_id"]

            # Turn 2 (fresh AntigravityNative verifies disk proof & reuses sid1 with --conversation!)
            o2 = await run_execution_session_task(
                task=make_task(102, base_task_id=101), client=client, member_id="agent:agy-neon", workdir=workdir,
                command=command, timeout=30, launch_id="launch-1", project_id="prj_test",
                binding_snapshot=binding, store_override=store_path, runner=None,
            )
            assert o2.completion_status == "succeeded" and o2.state["reused"] is True
            assert o2.state["native_session_id"] == sid1
            assert "--conversation" in spawned[1] and sid1 in spawned[1]

            # Turn 3 (previous turn hit 90% -> rotates)
            o3 = await run_execution_session_task(
                task=make_task(103, base_task_id=101), client=client, member_id="agent:agy-neon", workdir=workdir,
                command=command, timeout=30, launch_id="launch-1", project_id="prj_test",
                binding_snapshot=binding, store_override=store_path, runner=None,
            )
            assert o3.completion_status == "succeeded" and o3.state["reused"] is False
            assert o3.state["native_session_id"] != sid1

            # Turn 4 (previous turn had context_window=None -> new_context_unknown, NOT new_session_tainted!)
            o4 = await run_execution_session_task(
                task=make_task(104, base_task_id=101), client=client, member_id="agent:agy-neon", workdir=workdir,
                command=command, timeout=30, launch_id="launch-1", project_id="prj_test",
                binding_snapshot=binding, store_override=store_path, runner=None,
            )
            assert o4.completion_status == "succeeded" and o4.state["reused"] is False
            assert o4.state["reason_code"] != "new_session_tainted"

            # Turn 5: route end-to-end through cli_bridge.handle_queued_task!
            async def fake_preflight(*args, **kwargs):
                return cli_bridge.CliRunResult(returncode=0, stdout='{"decision":"ready"}', stderr="", timed_out=False)

            handled = await cli_bridge.handle_queued_task(
                make_task(105, base_task_id=101),
                client=client,
                member_id="agent:agy-neon",
                workdir=workdir,
                instance_id="ins_1",
                command=command,
                timeout=30,
                max_reply_chars=4000,
                runtime="antigravity",
                bridge_label="Antigravity bridge",
                prompt_transport="argv",
                command_runner=fake_preflight,
                execution_context={
                    "launch_id": "launch-1",
                    "project_id": "prj_test",
                    "store_override": store_path,
                },
            )
            assert handled is True
            assert len(client.completed) == 1
            completed_id, completed_kwargs = client.completed[0]
            assert completed_id == 105
            assert completed_kwargs["status"] == "succeeded"
            assert completed_kwargs["execution_session_state"]["reused"] is True
            assert "--conversation" in spawned[4]

            # Wrong runtime in binding must fail closed.
            bad_binding = {**binding, "runtime": "codex"}
            with pytest.raises(ExecutionSessionRunError, match="antigravity_binding_unusable"):
                await run_execution_session_task(
                    task=make_task(106), client=client, member_id="agent:agy-neon", workdir=workdir,
                    command=command, timeout=30, launch_id="launch-1", project_id="prj_test",
                    binding_snapshot=bad_binding, store_override=store_path, runner=None,
                )

    asyncio.run(scenario())
