"""Portable bootstrap isolation and recovery checks."""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PortablePhase1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="portable-phase1-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "bundle"
        self.keys = self.base / "external-keys"
        self.env = dict(os.environ, TALK_HOME=str(self.root), TALK_CONFIG=str(self.root / "config/config.toml"),
                        TALK_KEYS_DIR=str(self.keys), PYTHONPATH=str(ROOT))

    def run_bootstrap(self, *options):
        return subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "scripts.portable_bootstrap",
                               "--root", str(self.root), "--port", "19437", *options],
                              cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True)

    def test_dry_run_apply_and_idempotence(self):
        dry = self.run_bootstrap()
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse(self.root.exists())
        self.assertFalse(self.keys.exists())
        first = self.run_bootstrap("--apply")
        self.assertEqual(first.returncode, 0, first.stderr)
        summary = json.loads(first.stdout)
        self.assertEqual(summary["admin"], "created")
        self.assertEqual(summary["project"]["status"], "created")
        key = self.keys / "operator.key"
        self.assertTrue(key.is_file())
        self.assertNotIn(key.read_text(encoding="utf-8").strip(), first.stdout)
        self.assertFalse((self.root / "keys").exists())
        for name in ("storage", "logs", "backups", "state", "workspaces", "project"):
            self.assertTrue((self.root / "data" / name).is_dir())
        files = [self.root / "config/config.toml", self.root / "config/runtime.json",
                 self.root / "data/project/.talk/project.yaml", key]
        original = [p.read_bytes() for p in files]
        db = self.root / "data/talk.db"
        with closing(sqlite3.connect(db)) as conn:
            counts = (conn.execute("select count(*) from members where kind='human'").fetchone()[0],
                      conn.execute("select count(*) from projects").fetchone()[0])
        second = self.run_bootstrap("--apply")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["project"]["status"], "existing")
        self.assertEqual(original, [p.read_bytes() for p in files])
        with closing(sqlite3.connect(db)) as conn:
            self.assertEqual(counts, (conn.execute("select count(*) from members where kind='human'").fetchone()[0],
                                      conn.execute("select count(*) from projects").fetchone()[0]))
        self.assertEqual(counts, (1, 1))
        runtime = json.loads(files[1].read_text(encoding="utf-8"))
        self.assertEqual(runtime["api_argv"][0], sys.executable)
        self.assertEqual(runtime["base_url"], "http://127.0.0.1:19437")
        # Every generated machine path is derived from the explicit fixture or interpreter.
        text = b"\n".join(original[:3]).decode("utf-8").replace("\\\\", "\\")
        for forbidden in ("D:\\claude-test", "C:\\Users\\Administrator"):
            if forbidden.lower() not in str(self.base).lower() and forbidden.lower() not in sys.executable.lower():
                self.assertNotIn(forbidden.lower(), text.lower())

    def test_talk_config_subprocess(self):
        applied = self.run_bootstrap("--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        code = "import json,server.db as d; print(json.dumps([str(d._CFG_PATH),d.DB_PATH]))"
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=self.env,
                                text=True, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [str(self.root / "config/config.toml"), str(self.root / "data/talk.db")])

    def test_binding_uses_selected_config_and_relative_home(self):
        config_path = self.root / "config/config.toml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('[storage]\ndb_path = "data/relative.db"\n', encoding="utf-8")
        code = r'''import json, os
from pathlib import Path
from unittest.mock import patch
from server import local_runtime as local
root_config = (local.ROOT / "config.toml").resolve()
original = Path.open
def checked(path, *args, **kwargs):
    if path.resolve() == root_config:
        raise AssertionError("repository config accessed")
    return original(path, *args, **kwargs)
project = Path(os.environ["TALK_HOME"]) / "project"
with patch.object(Path, "open", checked):
    local.bind_local_runtime(project / "runtime.json", {"project_root": str(project)})
print(json.dumps(json.loads((project / ".talk/runtime.local.json").read_text(encoding="utf-8"))))
'''
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=self.env,
                                text=True, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["database_file"]), self.root / "data/relative.db")

    def test_binding_development_default_uses_root(self):
        code = r'''import io, json, sys
from pathlib import Path
from unittest.mock import patch
from server import local_runtime as local
original = Path.open
def fake(path, *args, **kwargs):
    if path == local.ROOT / "config.toml":
        return io.BytesIO(b'[storage]\ndb_path = "data/dev.db"\n')
    return original(path, *args, **kwargs)
project = Path(sys.argv[1])
with patch.object(Path, "open", fake):
    local.bind_local_runtime(project / "runtime.json", {"project_root": str(project)})
print(json.dumps(json.loads((project / ".talk/runtime.local.json").read_text(encoding="utf-8"))))
'''
        env = {k: v for k, v in self.env.items() if k not in ("TALK_CONFIG", "TALK_HOME")}
        result = subprocess.run([sys.executable, "-B", "-c", code, str(self.root)], cwd=ROOT, env=env,
                                text=True, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["database_file"]), ROOT / "data/dev.db")

    def test_portable_runtime_project_startup_and_stop(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        bootstrap = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "scripts.portable_bootstrap",
                                    "--root", str(self.root), "--port", str(port), "--apply"],
                                   cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
        project = json.loads(bootstrap.stdout)["project"]["id"]
        # A distribution contains the static assets at its own root.
        (self.root / "web").mkdir()
        for asset in (ROOT / "web").iterdir():
            if asset.is_file():
                shutil.copyfile(asset, self.root / "web" / asset.name)
        runtime_config = self.root / "config/runtime.json"
        cmd = [sys.executable, "-B", "-X", "utf8", "-m", "scripts.talk_runtime"]
        log_path = self.base / "runtime.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(cmd + ["serve", "--config", str(runtime_config), "--apply"],
                                       cwd=ROOT, env=self.env, stdout=log, stderr=subprocess.STDOUT)
            try:
                health_path = self.root / "data/state/runtime/health.json"
                deadline = time.monotonic() + 60
                health = {}
                while time.monotonic() < deadline:
                    api_log = self.root / "data/state/runtime/api.err"
                    diagnostic = log_path.read_text(encoding="utf-8")
                    if api_log.exists():
                        diagnostic += api_log.read_text(encoding="utf-8", errors="replace")
                    self.assertIsNone(process.poll(), diagnostic)
                    try:
                        health = json.loads(health_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        pass
                    if health.get("startup_state") == "complete":
                        break
                    time.sleep(.25)
                self.assertEqual(health.get("startup_state"), "complete", str(health))
                pointer = json.loads((self.root / "data/project/.talk/runtime.local.json").read_text(encoding="utf-8"))
                self.assertEqual(Path(pointer["database_file"]), self.root / "data/talk.db")
                data = json.dumps({"activation_id": health["activation_id"], "workspace_runtime_guard": True}).encode()
                request = urllib.request.Request(f"http://127.0.0.1:{port}/api/projects/{project}/role-services/startup",
                                                 data=data, headers={"Content-Type": "application/json",
                                                 "X-API-Key": (self.keys / "operator.key").read_text(encoding="utf-8").strip()})
                with urllib.request.urlopen(request, timeout=15) as response:
                    body = json.load(response)
                    self.assertEqual(response.status, 200)
                self.assertTrue(body["complete"])
                self.assertEqual(body["activation_id"], health["activation_id"])
                print(f"portable e2e: bootstrap ok; isolated port {port}; startup HTTP 200 complete; binding DB matches", flush=True)
            finally:
                if process.poll() is None and health_path.exists():
                    stopped = subprocess.run(cmd + ["stop", "--config", str(runtime_config), "--apply", "--wait", "--wait-seconds", "45"],
                                             cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True, timeout=55)
                    self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
                    self.assertEqual(json.loads(stopped.stdout)["stop_status"], "stopped")
                process.wait(timeout=15)
                if process.returncode == 0:
                    print("portable e2e: runtime and owned API stopped", flush=True)

    def test_existing_key_is_preserved(self):
        self.keys.mkdir()
        key = self.keys / "operator.key"
        key.write_text("existing-fixture-key\n", encoding="utf-8")
        applied = self.run_bootstrap("--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(key.read_text(encoding="utf-8"), "existing-fixture-key\n")

    def test_refuses_foreign_database(self):
        config = self.root / "config/config.toml"
        config.parent.mkdir(parents=True)
        foreign = self.base / "foreign.db"
        foreign.write_text("do not touch", encoding="utf-8")
        config.write_text('[server]\nport = 19437\n[storage]\ndb_path = ' +
                          json.dumps(str(foreign)) + '\n', encoding="utf-8")
        result = self.run_bootstrap("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inside the portable data directory", result.stderr)
        self.assertEqual(foreign.read_text(encoding="utf-8"), "do not touch")

    def test_refuses_conflicting_project_metadata(self):
        applied = self.run_bootstrap("--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        meta = self.root / "data/project/.talk/project.yaml"
        original = '{"project_id":"prj_other"}\n'
        meta.write_text(original, encoding="utf-8")
        rerun = self.run_bootstrap("--apply")
        self.assertNotEqual(rerun.returncode, 0)
        self.assertIn("does not match", rerun.stderr)
        self.assertEqual(meta.read_text(encoding="utf-8"), original)

    @unittest.skipUnless(os.name == "nt", "Windows batch parsing")
    def test_batch_reads_configured_port(self):
        applied = self.run_bootstrap("--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        line = next(line for line in (ROOT / "start.bat").read_text(encoding="utf-8").splitlines()
                    if line.startswith("for /f"))
        script = self.base / "port test.bat"
        script.write_text("@echo off\n" + line + "\necho port:%PORT%\n", encoding="utf-8")
        env = dict(self.env, PYTHON=sys.executable)
        result = subprocess.run(["cmd", "/c", str(script)], env=env, cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("port:19437", result.stdout)

    def test_scripts(self):
        for name, action in (("start.bat", "serve"), ("stop.bat", "stop"), ("status.bat", "status")):
            text = (ROOT / name).read_text(encoding="utf-8").lower()
            for expected in ('cd /d "%~dp0"', "talk_config", "scripts.talk_runtime", action):
                self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
