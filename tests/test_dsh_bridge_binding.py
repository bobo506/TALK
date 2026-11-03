import argparse
import copy
import unittest
from unittest.mock import AsyncMock, patch

from bridges import cli_bridge, dsh_bridge


FIELDS = {
    "runner_id": "dsh", "runtime": "dsh", "model_source": "connection",
    "provider_id": "provider", "connection_ref": "connection:example",
    "model_id": "model", "model_alias": "dsh/model",
    "binding_fingerprint": "a" * 64,
}


class FakeClient:
    def __init__(self, binding):
        self.binding = binding
        self.error = False

    async def _request_json(self, method, path):
        if self.error:
            raise RuntimeError("sensitive server detail")
        return [{"member_id": "agent:test", "binding": self.binding}]


class BindingHookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.snapshot = {"schema_version": "role-binding-snapshot-1", "state": "bound", **FIELDS}
        self.binding = {"binding_state": "bound", **FIELDS}
        self.client = FakeClient(self.binding)
        self.args = argparse.Namespace(name="test", project_id="project")
        self.effort = AsyncMock()
        self.effort_patch = patch.object(dsh_bridge, "make_effort_hook", return_value=self.effort)
        self.effort_patch.start()
        self.addCleanup(self.effort_patch.stop)
        self.hook = dsh_bridge.make_before_task_hook(self.client, self.args)
        self.executed = []

    async def attempt(self, snapshot):
        task = {"target_binding_snapshot": snapshot}
        await cli_bridge.run_before_task(argparse.Namespace(before_task=self.hook), task)
        self.executed.append(task)

    async def rejected(self, snapshot):
        with self.assertRaisesRegex(cli_bridge.TaskPreflightError, "^dsh_task_binding_invalid$"):
            await self.attempt(snapshot)
        self.assertEqual(self.executed, [])
        self.effort.assert_not_awaited()

    async def test_matching_binding_calls_effort_and_allows_execution(self):
        await self.attempt(self.snapshot)
        self.assertEqual(len(self.executed), 1)
        self.effort.assert_awaited_once_with(self.executed[0])

    async def test_missing_invalid_or_unbound_snapshot(self):
        for snapshot in (None, {}, {**self.snapshot, "state": "unbound"},
                         {**self.snapshot, "schema_version": "wrong"}):
            with self.subTest(snapshot=snapshot):
                await self.rejected(snapshot)

    async def test_missing_or_mismatched_fields_fail_closed(self):
        for field in FIELDS:
            for value in (None, "", "different"):
                with self.subTest(field=field, value=value):
                    snapshot = copy.deepcopy(self.snapshot)
                    if value is None:
                        del snapshot[field]
                    else:
                        snapshot[field] = value
                    await self.rejected(snapshot)
        for field in FIELDS:
            with self.subTest(current_missing=field):
                binding = self.client.binding
                self.client.binding = {k: v for k, v in binding.items() if k != field}
                await self.rejected(self.snapshot)
                self.client.binding = binding

    async def test_unbound_missing_or_unreadable_current_binding(self):
        for binding in (None, {}, {**self.binding, "binding_state": "unbound"}):
            self.client.binding = binding
            await self.rejected(self.snapshot)
        self.client.error = True
        await self.rejected(self.snapshot)

    async def test_factory_installed_by_bridge(self):
        with patch.object(cli_bridge, "run_bridge", new_callable=AsyncMock):
            await dsh_bridge.run_bridge(self.args)
        self.assertIs(self.args.before_task_factory, dsh_bridge.make_before_task_hook)
