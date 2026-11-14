"""WorkBuddy portable detection and conditional registry integration."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from scripts.portable_bootstrap import workbuddy_recipe

ROOT = Path(__file__).resolve().parent.parent


class WorkBuddyPortableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="workbuddy-portable-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "bundle"
        self.profile = self.base / "profile"
        self.profile.mkdir()
        self.env = dict(os.environ, USERPROFILE=str(self.profile),
                        LOCALAPPDATA=str(self.base / "local"),
                        PROGRAMFILES=str(self.base / "program"),
                        **{"PROGRAMFILES(X86)": str(self.base / "program86"),
                           "WORKBUDDY_EXE": "", "TALK_HOME": str(self.root),
                           "TALK_CONFIG": str(self.root / "config/config.toml"),
                           "TALK_KEYS_DIR": str(self.base / "keys"), "PYTHONPATH": str(ROOT)})

    def apply(self):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "scripts.portable_bootstrap",
                                 "--root", str(self.root), "--port", "19437", "--apply"],
                                cwd=ROOT, env=self.env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def rows(self):
        with closing(sqlite3.connect(self.root / "data/talk.db")) as conn:
            runner = conn.execute("select runner_id, runtime, display_name, control_kind, adapter_status, capabilities from runner_registry where runner_id=?", ("runner:workbuddy-embedded-cli",)).fetchall()
            models = conn.execute("select model_id, model_alias, model_display_name, model_source, provider_id, connection_ref, capabilities from runner_model_choices where runner_id=? order by model_id", ("runner:workbuddy-embedded-cli",)).fetchall()
            models = [(*row[:-1], json.loads(row[-1])) for row in models]
        return runner, models

    def test_detect_seed_and_repeat(self):
        exe = self.base / "WorkBuddy.exe"
        exe.touch()
        (self.profile / ".workbuddy").mkdir()
        (self.profile / ".workbuddy" / "models.json").touch()
        self.env["WORKBUDDY_EXE"] = str(exe)
        first = self.apply()
        runtime_path = self.root / "config/runtime.json"
        self.assertEqual(json.loads(runtime_path.read_text(encoding="utf-8"))["workbuddy"],
                         {"executable": str(exe), "models_home": str(self.profile / ".workbuddy")})
        runner, models = self.rows()
        self.assertEqual(len(runner), 1)
        self.assertEqual(runner[0][:5], ("runner:workbuddy-embedded-cli", "workbuddy", "WorkBuddy 内置CLI", "managed_cli", "unverified"))
        self.assertEqual(json.loads(runner[0][5]), [])
        self.assertEqual(models, [
            ("deepseek-v4.1-flash", "workbuddy-cdp:deepseek-v4.1-flash", "DeepSeek-V4.1-Flash（内置·桌面）", "builtin", "managed:workbuddy", "native-workbuddy-cdp", ["effort:low", "effort:high", "effort:max", "effort_default:high"]),
            ("glm-5.3-flash", "workbuddy-cdp:glm-5.3-flash", "GLM-5.3-Flash（内置·桌面）", "builtin", "managed:workbuddy", "native-workbuddy-cdp", ["effort:low", "effort:high", "effort:max", "effort_default:high"]),
            ("hy4free", "workbuddy-cdp:hy4free", "Hy4（内置·桌面）", "builtin", "managed:workbuddy", "native-workbuddy-cdp", ["effort:high", "effort_default:high"]),
        ])
        from sqlmodel import Session, create_engine
        from server.workbuddy_effort import cdp_effort_for_facts
        engine = create_engine(f"sqlite:///{(self.root / 'data/talk.db').as_posix()}")
        try:
            with Session(engine) as session:
                for model_id, alias, _, source, provider, connection, _ in models:
                    facts = {"runtime": "workbuddy", "runner_id": runner[0][0],
                             "model_id": model_id, "model_alias": alias, "model_source": source,
                             "provider_id": provider, "connection_ref": connection}
                    options = ["high"] if model_id == "hy4free" else ["low", "high", "max"]
                    self.assertEqual(cdp_effort_for_facts(session, facts), (options, "high", None))
        finally:
            engine.dispose()
        self.assertEqual(first["seed"]["runners"], 4)
        before = runtime_path.read_bytes()
        second = self.apply()
        self.assertEqual(second["seed"], {"runners": 0, "models": 0, "host": 0})
        self.assertEqual(runtime_path.read_bytes(), before)
        self.assertEqual(self.rows(), (runner, models))

    def test_absent_then_custom_recipe_preserved_and_seeded(self):
        self.apply()
        path = self.root / "config/runtime.json"
        runtime = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("workbuddy", runtime)
        self.assertEqual(self.rows(), ([], []))
        custom = {"executable": str(self.base / "custom.exe"), "models_home": str(self.base / "custom-home"), "key_files": {}}
        runtime["workbuddy"] = custom
        path.write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        exe = self.base / "detected.exe"
        exe.touch()
        (self.profile / ".workbuddy").mkdir()
        (self.profile / ".workbuddy" / "models.json").touch()
        self.env["WORKBUDDY_EXE"] = str(exe)
        self.apply()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["workbuddy"], custom)
        self.assertEqual(tuple(map(len, self.rows())), (1, 3))

    def test_existing_config_gains_missing_recipe(self):
        self.apply()
        exe = self.base / "detected.exe"
        exe.touch()
        (self.profile / ".workbuddy").mkdir()
        self.env["WORKBUDDY_EXE"] = str(exe)
        self.apply()
        self.assertNotIn("workbuddy", json.loads((self.root / "config/runtime.json").read_text(encoding="utf-8")))
        self.assertEqual(self.rows(), ([], []))
        (self.profile / ".workbuddy" / "models.json").touch()
        self.apply()
        runtime = json.loads((self.root / "config/runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(runtime["workbuddy"]["executable"], str(exe))
        self.assertEqual(tuple(map(len, self.rows())), (1, 3))

    def test_locations_and_rejections(self):
        with patch.dict(os.environ, self.env, clear=True):
            os.environ["WORKBUDDY_EXE"] = "relative.exe"
            (self.profile / ".workbuddy").mkdir()
            self.assertIsNone(workbuddy_recipe())
            (self.profile / ".workbuddy" / "models.json").touch()
            os.environ["WORKBUDDY_EXE"] = str(self.base / "missing.exe")
            self.assertIsNone(workbuddy_recipe())
            for variable, parts in (("LOCALAPPDATA", ("Programs", "WorkBuddy", "WorkBuddy.exe")),
                                    ("PROGRAMFILES", ("WorkBuddy", "WorkBuddy.exe")),
                                    ("PROGRAMFILES(X86)", ("WorkBuddy", "WorkBuddy.exe"))):
                exe = Path(os.environ[variable]).joinpath(*parts)
                exe.parent.mkdir(parents=True)
                exe.touch()
                self.assertEqual(workbuddy_recipe()["executable"], str(exe))
                exe.unlink()
            exe = self.base / "present.exe"
            exe.touch()
            os.environ["WORKBUDDY_EXE"] = str(exe)
            (self.profile / ".workbuddy" / "models.json").unlink()
            self.assertIsNone(workbuddy_recipe())
            (self.profile / ".workbuddy").rmdir()
            self.assertIsNone(workbuddy_recipe())


if __name__ == "__main__":
    unittest.main()
