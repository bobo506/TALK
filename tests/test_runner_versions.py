import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from server import runner_versions as versions
from server.auth import get_current_member
from server.db import get_session
from server.routes.runners import router


class VersionTests(unittest.TestCase):
    def setUp(self):
        versions.clear_cache()

    def test_parsing(self):
        for runtime, output, expected in [("codex", "codex-cli 0.164.0\n", "0.164.0"),
                                           ("kimi-code", "kimi version 2.0.2", "2.0.2"),
                                           ("dsh", "dsh 0.2.1-rc.5", "0.2.1-rc.5")]:
            self.assertEqual(versions.parse_version(runtime, output), expected)
        self.assertIsNone(versions.parse_version("codex", "codex 0.164.0"))
        self.assertIsNone(versions.parse_version("dsh", "1.2.3-beta.1"))

    def test_comparison(self):
        for detected, adapted, expected in [("0.165.0", "0.164.0", "newer"),
            ("0.163.0", "0.164.0", "older"), ("0.164.0", "0.164.0", "match"),
            ("0.2.1-rc.5", "0.2.1", "older"), ("0.2.1-rc.6", "0.2.1-rc.5", "newer"),
            ("invalid", "0.164.0", "unknown")]:
            self.assertEqual(versions.compare_versions(detected, adapted), expected)

    def test_probe_failures(self):
        with patch.object(versions.shutil, "which", return_value=None):
            self.assertEqual(versions.get_version("codex")["status"], "unknown")
        versions.clear_cache()
        with patch.object(versions.shutil, "which", return_value="codex"), patch.object(versions.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 3)):
            result = versions.get_version("codex")
            self.assertEqual((result["status"], result["detail"]), ("unknown", "探测超时"))
        versions.clear_cache()
        with patch.object(versions.shutil, "which", side_effect=OSError()):
            self.assertEqual(versions.get_version("codex")["status"], "unknown")

    def test_cache_and_clear(self):
        with patch.object(versions, "_probe", return_value=("0.164.0", "")) as probe:
            self.assertEqual(versions.get_version("codex")["status"], "match")
            versions.get_version("codex")
            self.assertEqual(probe.call_count, 1)
            versions.clear_cache()
            versions.get_version("codex")
            self.assertEqual(probe.call_count, 2)

    def test_authenticated_read_only_endpoint(self):
        app = FastAPI()
        app.include_router(router)
        class Session:
            def exec(self, query):
                return SimpleNamespace(all=lambda: [SimpleNamespace(runtime="codex", display_name="Codex"), SimpleNamespace(runtime="codex", display_name="Other"), SimpleNamespace(runtime="workbuddy", display_name="WorkBuddy")])
        app.dependency_overrides[get_session] = lambda: Session()
        client = TestClient(app)
        self.assertIn(client.get("/api/runners/versions").status_code, (401, 403, 422))
        app.dependency_overrides[get_current_member] = lambda: SimpleNamespace(kind="agent")
        with patch.object(versions, "_probe", return_value=("0.164.0", "")):
            response = client.get("/api/runners/versions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["runtime"] for r in response.json()], ["codex", "workbuddy"])
        self.assertEqual(client.post("/api/runners/versions").status_code, 405)
        # /{runner_id} PATCH remains the existing registry contract, not a versions writer.
        self.assertNotIn("patch", app.openapi()["paths"]["/api/runners/versions"])


if __name__ == "__main__":
    unittest.main()
