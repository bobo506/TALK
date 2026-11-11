"""Offline reload-window tests; no API, real process or credentials."""
import asyncio
import unittest
import urllib.error
from unittest.mock import Mock, patch

import httpx

from bridges.cli_bridge import _retry_task_delivery_connect
from scripts.role_service_host import HostError, HostManager


def refused():
    try:
        raise urllib.error.URLError(ConnectionRefusedError("offline"))
    except urllib.error.URLError as cause:
        try:
            raise HostError("host_unreachable") from cause
        except HostError as error:
            return error


class ReloadRetryTests(unittest.TestCase):
    def setUp(self):
        self.manager = object.__new__(HostManager)
        self.manager.client = Mock()
        self.manager._host_budgets = Mock(return_value={})

    @patch("scripts.role_service_host.time.sleep")
    def test_claim_refused_recovers_but_ambiguous_timeout_is_not_replayed(self, sleep):
        self.manager.client.request.side_effect = [refused(), refused(), {"claim_token": "fake"}]
        result = self.manager._claim_with_retry("/claim", {"host": "test"})
        self.assertEqual(result["claim_token"], "fake")
        self.assertEqual(self.manager.client.request.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.manager.client.request.reset_mock()
        self.manager.client.request.side_effect = HostError("host_unreachable")
        with self.assertRaises(HostError):
            self.manager._claim_with_retry("/claim", {})
        self.assertEqual(self.manager.client.request.call_count, 1)

    @patch("scripts.role_service_host.time.sleep")
    def test_report_lost_receipt_replays_identical_payload_once(self, sleep):
        accepted = []
        calls = []
        def report(**payload):
            calls.append(payload)
            if not accepted:
                accepted.append(payload)
                raise HostError("host_unreachable")
            self.assertEqual(payload, accepted[0])
            return {"replayed": True}
        self.manager._report = report
        self.assertTrue(self.manager._report_safely(None, launch_id="x", outcome="ready")["replayed"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(sleep.call_count, 1)

    @patch("scripts.role_service_host.time.sleep")
    def test_report_retry_is_bounded_and_does_not_retry_business_errors(self, sleep):
        self.manager._report = Mock(side_effect=HostError("host_unreachable"))
        with self.assertRaises(HostError):
            self.manager._report_safely(None, launch_id="x")
        self.assertEqual(self.manager._report.call_count, 4)
        self.assertEqual(sleep.call_count, 3)
        self.manager._report = Mock(side_effect=HostError("http_409"))
        with self.assertRaises(HostError):
            self.manager._report_safely(None, launch_id="x")
        self.assertEqual(self.manager._report.call_count, 1)


class BridgeDeliveryRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_failure_recovery_and_no_retry_after_read_failure(self):
        calls = []
        async def operation():
            calls.append(1)
            if len(calls) < 3:
                raise httpx.ConnectError("offline")
            return {"id": 1}
        with patch("bridges.cli_bridge.asyncio.sleep", return_value=None):
            self.assertEqual(await _retry_task_delivery_connect(operation), {"id": 1})
        self.assertEqual(len(calls), 3)
        calls.clear()
        async def ambiguous():
            calls.append(1)
            raise httpx.ReadTimeout("response lost")
        with self.assertRaises(httpx.ReadTimeout):
            await _retry_task_delivery_connect(ambiguous)
        self.assertEqual(len(calls), 1)

    async def test_connect_retry_is_bounded(self):
        operation = Mock(side_effect=httpx.ConnectError("offline"))
        async def call():
            return operation()
        with patch("bridges.cli_bridge.asyncio.sleep", return_value=None):
            with self.assertRaises(httpx.ConnectError):
                await _retry_task_delivery_connect(call)
        self.assertEqual(operation.call_count, 4)


if __name__ == "__main__":
    unittest.main()
