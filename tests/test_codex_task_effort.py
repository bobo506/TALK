"""351-G：Codex 逐任务强度刷新（真实队列路径 + 两种命令形态 + 失败策略）。"""

from __future__ import annotations

import argparse
import asyncio
import unittest
from pathlib import Path

from bridges import cli_bridge, codex_bridge

TASK = {"id": 1, "project_id": "prj_1", "content": "hi", "status": "queued", "workflow_status": "accepted"}


def binding(effort="low", options=("low", "medium", "high", "xhigh"), override=None, source="catalog"):
    return {
        "effective_effort": effort,
        "effort_override": override,
        "effort_options": list(options),
        "effort_source": source,
    }


class FakeClient:
    def __init__(self, bindings):
        self.bindings = bindings
        self.calls = []

    async def _request_json(self, method, path, **kwargs):
        self.calls.append((method, path))
        return {"data": [{"member_id": "agent:codex", "binding": self.bindings}]}

    async def requeue_expired_tasks(self):
        return []

    async def list_tasks(self, **kwargs):
        return [dict(TASK)]


def make_args(shape="config"):
    if shape == "config":
        task = 'codex exec -c model_reasoning_effort="xhigh" -'
        preflight = 'codex exec -c model_reasoning_effort="xhigh" --preflight -'
    elif shape == "flag":
        task = "native_driver.py --mode task --effort xhigh --model m"
        preflight = "native_driver.py --mode preflight --effort xhigh --model m"
    else:
        task = "native_driver.py --mode task --model m"
        preflight = "native_driver.py --mode preflight --model m"
    return argparse.Namespace(
        name="codex",
        command=task,
        task_command=task,
        task_command_template=task,
        task_preflight_command=preflight,
        task_preflight_command_template=preflight,
        timeout=5,
        max_reply_chars=100,
        runtime="codex",
        bridge_label="Codex bridge",
        prompt_transport="stdin",
        task_lease_seconds=30,
        task_heartbeat_interval=5,
        task_poll_interval=1,
    )


class RewriteTests(unittest.TestCase):
    def test_config_shape_sets_both_commands(self):
        args = make_args("config")
        codex_bridge._rewrite_effort_commands(args, "low")
        self.assertIn('model_reasoning_effort="low"', args.task_command)
        self.assertIn('model_reasoning_effort="low"', args.task_preflight_command)

    def test_flag_shape_sets_both_commands(self):
        args = make_args("flag")
        codex_bridge._rewrite_effort_commands(args, "medium")
        self.assertIn("--effort medium", args.task_command)
        self.assertIn("--effort medium", args.task_preflight_command)

    def test_unknown_shape_is_refused(self):
        args = make_args("plain")
        with self.assertRaises(cli_bridge.TaskPreflightError):
            codex_bridge._rewrite_effort_commands(args, "low")

    def test_rewrite_is_from_template_not_cumulative(self):
        args = make_args("config")
        codex_bridge._rewrite_effort_commands(args, "low")
        first = args.task_command
        codex_bridge._rewrite_effort_commands(args, "high")
        self.assertIn('"high"', args.task_command)
        self.assertNotIn('"low"', args.task_command)
        self.assertEqual(first.count("model_reasoning_effort"), 1)


class HookPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def run_hook(self, args, bindings):
        hook = codex_bridge.make_effort_hook(FakeClient(bindings), args)
        await hook(dict(TASK))
        return args

    async def test_hook_uses_latest_binding(self):
        args = await self.run_hook(make_args("config"), binding(effort="low"))
        self.assertIn('model_reasoning_effort="low"', args.task_command)

    async def test_override_with_unsupported_value_fails(self):
        args = make_args("config")
        with self.assertRaises(cli_bridge.TaskPreflightError):
            await self.run_hook(args, binding(effort="ultra", options=("low", "high"), override="ultra"))

    async def test_no_override_keeps_startup_value_on_unknown_capability(self):
        args = make_args("config")
        await self.run_hook(args, binding(effort="ultra", options=("low", "high"), source=None))
        self.assertIn('model_reasoning_effort="xhigh"', args.task_command)

    async def test_override_with_unrecognized_command_fails(self):
        args = make_args("plain")
        with self.assertRaises(cli_bridge.TaskPreflightError):
            await self.run_hook(args, binding(effort="low", override="low"))


class WorkerPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_queue_worker_passes_refreshed_commands(self):
        captured = {}

        async def fake_handle(task, **kwargs):
            captured.update(kwargs)
            raise asyncio.CancelledError

        args = make_args("config")
        args.before_task = codex_bridge.make_effort_hook(FakeClient(binding(effort="low")), args)

        async def scenario():
            original = cli_bridge.handle_queued_task
            cli_bridge.handle_queued_task = fake_handle
            try:
                await cli_bridge.run_task_queue_worker(
                    client=FakeClient(binding(effort="low")),
                    member_id="agent:codex",
                    workdir=Path.cwd(),
                    instance_id="agent:codex:test",
                    args=args,
                    run_lock=asyncio.Lock(),
                    report_status=None,
                )
            except asyncio.CancelledError:
                pass
            finally:
                cli_bridge.handle_queued_task = original

        await scenario()
        self.assertIn('model_reasoning_effort="low"', captured["command"])
        self.assertEqual(captured["command"].count("model_reasoning_effort"), 1)
        self.assertIn('model_reasoning_effort="low"', captured["preflight_command"])


if __name__ == "__main__":
    unittest.main()
