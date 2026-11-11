import os
import socket
import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from server.models import ProjectRoleBinding
from server.workbuddy_cdp import cdp_endpoint_available
from tests.test_role_services import PROJECT_ID, RoleServiceTestCase


@contextmanager
def local_server(status=200, delay=0, stall=False):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    port = listener.getsockname()[1]
    release = threading.Event()
    requests = []

    def serve():
        try:
            with listener.accept()[0] as client:
                client.settimeout(2)
                requests.append(client.recv(4096))
                if stall:
                    release.wait(2)
                elif not release.wait(delay):
                    client.sendall(f"HTTP/1.1 {status} Test\r\nConnection: close\r\n\r\n".encode("ascii"))
        except OSError:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", requests
    finally:
        release.set()
        thread.join(3)
        listener.close()


class ProbeTests(unittest.TestCase):
    def test_real_http_status_and_request(self):
        for status, expected in ((200, True), (500, False)):
            with self.subTest(status=status), local_server(status) as (endpoint, requests):
                with patch.dict(os.environ, {"TALK_WORKBUDDY_CDP_ENDPOINT": endpoint}):
                    self.assertEqual(cdp_endpoint_available(), expected)
                self.assertEqual(requests, [f"GET /json/version HTTP/1.1\r\nHost: {endpoint[7:]}\r\nConnection: close\r\n\r\n".encode("ascii")])

    def test_stalled_server_respects_budget(self):
        with local_server(stall=True) as (endpoint, _), patch.dict(os.environ, {"TALK_WORKBUDDY_CDP_ENDPOINT": endpoint}):
            started = time.monotonic()
            self.assertFalse(cdp_endpoint_available(timeout=0.15))
            self.assertLess(time.monotonic() - started, 0.3)

    def test_closed_port(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with patch.dict(os.environ, {"TALK_WORKBUDDY_CDP_ENDPOINT": f"http://127.0.0.1:{port}"}):
            self.assertFalse(cdp_endpoint_available())

    def test_invalid_endpoints_never_contact_network(self):
        endpoints = ("http://example.com:9222", "http://192.168.1.1:9222", "http://127.0.0.1.example.com:9222", "http://user@127.0.0.1:9222", "https://127.0.0.1:9222", "http://127.0.0.1:9222/path", "http://127.0.0.1:9222/?a=1", "http://127.0.0.1:9222/#x", "http://127.0.0.1", "http://127.0.0.1:bad")
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint), patch.dict(os.environ, {"TALK_WORKBUDDY_CDP_ENDPOINT": endpoint}), patch("server.workbuddy_cdp.socket.create_connection") as connect:
                self.assertFalse(cdp_endpoint_available())
                connect.assert_not_called()

    def test_localhost_override(self):
        with local_server() as (endpoint, _), patch.dict(os.environ, {"TALK_WORKBUDDY_CDP_ENDPOINT": endpoint.replace("127.0.0.1", "localhost")}):
            self.assertTrue(cdp_endpoint_available())


class GateTests(RoleServiceTestCase):
    def bind(self, connection, alias):
        with self.session() as session:
            binding = session.get(ProjectRoleBinding, (PROJECT_ID, self.role_a))
            binding.connection_ref = connection
            binding.model_alias = alias
            session.add(binding)
            session.commit()

    def test_unavailable_no_write_for_connection_and_alias(self):
        for connection, alias in (("native-workbuddy-cdp", "other"), ("other", "workbuddy-cdp:model")):
            self.bind(connection, alias)
            with patch("server.role_services.cdp_endpoint_available", return_value=False) as probe:
                response = self.start()
            self.assertEqual((response.status_code, response.json()["detail"]), (409, "workbuddy_cdp_unavailable"))
            probe.assert_called_once()
            self.assertIsNone(self.state_row())
            self.assertEqual(self.launch_rows(), [])

    def test_unavailable_keeps_manual_error_precedence_for_running_role(self):
        self.assertEqual(self.start().status_code, 200)
        before = self.state_row().model_dump()
        self.bind("native-workbuddy-cdp", "workbuddy-cdp:model")
        with patch("server.role_services.cdp_endpoint_available", return_value=False) as probe:
            response = self.start()
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "workbuddy_cdp_unavailable"))
        probe.assert_called_once_with()
        self.assertEqual(self.state_row().model_dump(), before)
        self.assertEqual(len(self.launch_rows()), 1)

    def test_available_starts(self):
        self.bind("native-workbuddy-cdp", "workbuddy-cdp:model")
        with patch("server.role_services.cdp_endpoint_available", return_value=True) as probe:
            response = self.start()
        self.assertEqual(response.status_code, 200, response.text)
        probe.assert_called_once()
        self.assertEqual(len(self.launch_rows()), 1)

    def test_real_slow_local_cdp_starts(self):
        self.bind("native-workbuddy-cdp", "workbuddy-cdp:model")
        with local_server(delay=0.2) as (endpoint, requests), patch.dict(os.environ, {"TALK_WORKBUDDY_CDP_ENDPOINT": endpoint}):
            response = self.start()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(self.launch_rows()), 1)

    def test_other_bindings_do_not_probe(self):
        for connection, alias in (("native-workbuddy-acp", "workbuddy-acp:model"), ("custom-local", "custom:model")):
            self.bind(connection, alias)
            with patch("server.role_services.cdp_endpoint_available", side_effect=AssertionError("unexpected probe")):
                response = self.start()
            self.assertIn(response.status_code, (200, 409))

    def test_start_all_reports_error_without_writes(self):
        self.bind("native-workbuddy-cdp", "workbuddy-cdp:model")
        with patch("server.role_services.cdp_endpoint_available", return_value=False):
            response = self.start_all()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["results"][0]
        self.assertEqual((result["status"], result["error_code"]), ("failed", "workbuddy_cdp_unavailable"))
        self.assertIsNone(self.state_row())
        self.assertEqual(self.launch_rows(), [])
