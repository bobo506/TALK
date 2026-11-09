"""本机自动宿主与human关闭恢复：隔离数据库，不启动生产模型。"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import create_engine
from server import local_runtime as local
from server.role_host_resolution import (RecoveryHostError, entry_from_argv,
    resolve_recovery_host)
from scripts.role_service_host import HostError
from tests.test_role_services import RoleServiceTestCase, PROJECT_ID, RUNNER_ID


class BootstrapTests(unittest.TestCase):
    def test_other_database_never_loads_manifest_or_spawns(self):
        with tempfile.TemporaryDirectory() as folder:
            pointer = Path(folder)/"runtime.local.json"
            pointer.write_text(json.dumps({"schema":"talk-local-runtime-1", "database_file":str(Path(folder)/"production.db"),
                                           "config_file":str(Path(folder)/"absent-private.json")}), encoding="utf-8")
            with patch.object(local, "POINTER", pointer), patch.object(local.subprocess, "Popen") as spawn:
                self.assertEqual(local.ensure_local_runtime(create_engine("sqlite:///:memory:")), "disabled")
            spawn.assert_not_called()

    def test_api_owned_runtime_is_not_duplicated_and_free_lock_launches_hosts_only(self):
        from scripts import talk_runtime as runtime
        with tempfile.TemporaryDirectory() as folder:
            config = {"state_dir":folder}
            private = Path(folder)/"runtime"; private.mkdir()
            with patch.object(local, "configured_runtime", return_value=(Path(folder)/"private.json", config)), \
                 patch("scripts.role_service_host.ensure_private_dir", side_effect=lambda p:p), \
                 patch.object(local.subprocess, "Popen") as spawn:
                with runtime.launcher_lock(private):
                    self.assertEqual(local.ensure_local_runtime(None), "already_running")
                spawn.assert_not_called()
                self.assertEqual(local.ensure_local_runtime(None), "requested")
                self.assertIn("--attach-api", spawn.call_args.args[0])
                self.assertNotIn("--key", spawn.call_args.args[0])


class RecoveryHostResolutionTests(unittest.TestCase):
    """Pure resolver: fixed hosts first, dynamic source identical to startup."""

    def test_dsh_resolution_and_disabled_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {"state_dir": folder, "hosts": [], "dsh": {"enabled": True}}
            kw = dict(config=config, project_id="prj_1", member_id="agent:one",
                      original_runtime="dsh", current_runtime="dsh", control_kind="managed_cli")
            resolved = resolve_recovery_host(**kw)
            self.assertEqual(resolved.host_entry.name, "dsh_role_host.py")
            self.assertEqual(resolved.health_file.parts[-3:], ("prj_1", "agent_one", "manager-health.json"))
            config["dsh"]["enabled"] = False
            with self.assertRaisesRegex(RecoveryHostError, "local_recovery_host_unconfigured"):
                resolve_recovery_host(**kw)

    def test_fixed_host_both_entry_contracts_and_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); member = "agent:one"; project = "prj_1"
            health = root / "fixed-health.json"; health.write_text("{}", encoding="utf-8")
            config = {"project_id": project, "project_root": str(root),
                      "state_dir": str(root / "state"), "hosts": [
                          {"member_id": member, "health_file": str(health),
                           "argv": [sys.executable, "-m", "scripts.kimi_role_host"]}],
                      "kimi": {"enabled": True}, "workbuddy": {"executable": "unused"}}
            host = resolve_recovery_host(config=config, project_id=project, member_id=member,
                original_runtime="kimi-code", current_runtime="kimi-code",
                control_kind="managed_cli")
            self.assertEqual(host.source, "fixed")
            self.assertEqual(host.health_file, health)
            self.assertEqual(host.host_entry.name, "kimi_role_host.py")
            script = root / "custom-host.py"; script.write_text("# fixture", encoding="utf-8")
            config["hosts"] = [{"member_id": member, "health_file": str(health),
                                "argv": [sys.executable, str(script)]}]
            host = resolve_recovery_host(config=config, project_id=project, member_id=member,
                original_runtime="workbuddy", current_runtime="workbuddy",
                control_kind="managed_cli")
            self.assertEqual((host.source, host.host_entry), ("fixed", script))

    def test_dynamic_health_paths_match_startup_manager_directories(self):
        from scripts import codex_role_host, kimi_role_host
        from scripts.role_service_host import _sanitize_token
        with tempfile.TemporaryDirectory() as folder:
            project, member = "prj_1", "agent:one"
            config = {"project_id": project, "state_dir": folder, "hosts": [],
                      "kimi": {"enabled": True}, "codex": {"enabled": True},
                      "workbuddy": {"executable": "unused"}}
            kimi = resolve_recovery_host(config=config, project_id=project, member_id=member,
                original_runtime="kimi-code", current_runtime="kimi-code",
                control_kind="managed_cli")
            self.assertEqual(kimi.health_file,
                Path(kimi_role_host.manager_directory(folder, project, member)) / "manager-health.json")
            codex = resolve_recovery_host(config=config, project_id=project, member_id=member,
                original_runtime="codex", current_runtime="codex", control_kind="managed_cli")
            self.assertEqual(codex.health_file,
                Path(codex_role_host.manager_directory(folder, project, member)) / "manager-health.json")
            workbuddy = resolve_recovery_host(config=config, project_id=project, member_id=member,
                original_runtime="workbuddy", current_runtime="workbuddy",
                control_kind="managed_cli")
            self.assertEqual(workbuddy.health_file,
                Path(folder) / "workbuddy-native" / _sanitize_token(project)
                / _sanitize_token(member) / "manager-health.json")
            self.assertEqual(workbuddy.host_entry.name, "workbuddy_role_host.py")

    def test_unknown_incomplete_or_changed_binding_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            base = {"project_id": "prj_1", "state_dir": folder, "hosts": [],
                    "workbuddy": {"executable": "unused"}}
            cases = [
                ({"project_id": "prj_1", "state_dir": folder, "hosts": [],
                  "workbuddy": {"executable": "unused"}},
                 "mystery", "mystery", "managed_cli", "local_recovery_runner_unsupported"),
                (base, None, "kimi-code", "managed_cli", "local_recovery_runner_unverified"),
                (base, "kimi-code", "workbuddy", "managed_cli", "local_recovery_binding_changed"),
                (base, "kimi-code", "kimi-code", "unknown", "local_recovery_binding_changed"),
                (base, "kimi-code", "kimi-code", "managed_cli", "local_recovery_host_unconfigured"),
                ({**base, "workbuddy": {}}, "workbuddy", "workbuddy", "managed_cli",
                 "local_recovery_host_unconfigured"),
            ]
            for config, original, current, control, code in cases:
                with self.subTest(code=code):
                    with self.assertRaisesRegex(RecoveryHostError, code):
                        resolve_recovery_host(config=config, project_id="prj_1",
                            member_id="agent:one", original_runtime=original,
                            current_runtime=current, control_kind=control)

    def test_bad_fixed_entry_identity_duplicate_and_no_entry_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); member = "agent:one"; health = str(root / "h.json")
            base = {"project_id": "prj_1", "project_root": str(root),
                    "state_dir": str(root / "state"), "hosts": []}
            cases = [
                ([{"member_id": member, "health_file": health,
                   "argv": [sys.executable, "-m", "not_scripts.host"]}],
                 "local_recovery_entry_unverified"),
                ([{"member_id": member, "health_file": health, "argv": [sys.executable]}],
                 "local_recovery_entry_unverified"),
                ([{"member_id": member, "health_file": health, "argv": [sys.executable, "h.py"],
                   "project_id": "other"}], "local_recovery_identity_mismatch"),
                ([{"member_id": member, "health_file": "" , "argv": [sys.executable, "h.py"]}],
                 "local_recovery_host_unconfigured"),
                ([{"member_id": member, "health_file": health, "argv": [sys.executable, "h.py"]},
                  {"member_id": member, "health_file": health, "argv": [sys.executable, "h.py"]}],
                 "local_recovery_host_ambiguous"),
            ]
            for hosts, code in cases:
                with self.subTest(code=code):
                    with self.assertRaisesRegex(RecoveryHostError, code):
                        resolve_recovery_host(config={**base, "hosts": hosts},
                            project_id="prj_1", member_id=member,
                            original_runtime=None, current_runtime=None, control_kind=None)
            self.assertIsNone(entry_from_argv([sys.executable, "-m", "not_scripts.host"], root))


class ActualBootstrapTests(unittest.TestCase):
    def test_actual_api_bootstrap_and_normal_restart_keep_one_independent_runtime(self):
        self.exercise_bootstrap()

    @unittest.skipUnless(os.name=="nt","Windows detached entry")
    def test_explicit_detached_entry_has_no_console_and_preserves_restart(self):
        self.exercise_bootstrap(detached=True)

    def exercise_bootstrap(self,detached=False):
        from scripts.role_service_recovery import probe_pid
        with tempfile.TemporaryDirectory(prefix="talk-local-runtime-") as folder:
            root=Path(folder); state=root/"state"; state.mkdir()
            project_root=root/"project";project_root.mkdir()
            # Child processes do not inherit the parent test's Python patches.
            # Runtime diagnostics must only ever open this synthetic config.
            (project_root/"config.toml").write_text('[storage]\ndb_path="fixture.db"\n',encoding="utf-8")
            key=root/"human.key";key.write_text("fixture-only",encoding="utf-8")
            with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
            config=root/"runtime.json"
            config.write_text(json.dumps({"schema":"talk-runtime-config-1","version":1,"project_id":"prj_fixture",
                "project_root":str(project_root),"state_dir":str(state),"key_root":str(root/"keys"),
                "operator_key_file":str(key),"base_url":f"http://127.0.0.1:{port}","provision_worker":False,
                "api_argv":[sys.executable,"-m","scripts.talk_api","--control-file","{control_file}"],"hosts":[]}),encoding="utf-8")
            env=dict(os.environ,TALK_RUNTIME_FIXTURE_CONFIG=str(config),PYTHONPATH=str(local.ROOT)); children=[]
            if detached:env.pop("TALK_RUNTIME_FIXTURE_CONFIG",None)
            health=state/"runtime/health.json"
            def wait_for(predicate):
                deadline=time.monotonic()+18
                while time.monotonic()<deadline:
                    if predicate():return
                    time.sleep(.1)
                self.fail("isolated bootstrap did not converge")
            def facts():
                try:return json.loads(health.read_text(encoding="utf-8"))
                except (OSError,ValueError):return {}
            def start_api(index):
                marker=root/f"api-{index}.stop"
                command=[sys.executable,"-B","-m","scripts.talk_api","--app","tests.talk_runtime_fixture:app",
                    "--port",str(port),"--control-file",str(marker)]
                child=subprocess.Popen(command,cwd=local.ROOT,env=env,stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    **({"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}))
                children.append((child,marker));return child,marker
            try:
                first,marker=start_api(1)
                if detached:
                    def listening():
                        with socket.socket() as sock:return sock.connect_ex(("127.0.0.1",port))==0
                    wait_for(listening)
                    subprocess.run([sys.executable,"-B","-m","scripts.talk_runtime","serve","--config",str(config),
                        "--apply","--attach-api","--detach"],cwd=local.ROOT,env=env,check=True,
                        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                wait_for(lambda:facts().get("state")=="running" and facts().get("startup_state")=="complete")
                original=facts()["pid"]
                self.assertEqual(facts()["api_mode"],"external")
                self.assertFalse(facts()["owns_original_popen"])
                if os.name=="nt":
                    probe=subprocess.run([sys.executable,"-B",str(local.ROOT/"tests/windows_console_probe.py"),str(original)],
                        capture_output=True,text=True,check=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
                    self.assertEqual(json.loads(probe.stdout),{"console":False,"visible":False})
                marker.write_text("normal API restart",encoding="utf-8");self.assertEqual(first.wait(timeout=8),0)
                if os.name=="nt":self.assertEqual(probe_pid(original),"present")
                second,_=start_api(2)
                from urllib.request import urlopen
                def api_ready():
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/api/members/me",timeout=.3):return True
                    except OSError:return False
                wait_for(api_ready)
                self.assertEqual(facts()["pid"],original)
                (state/"runtime/stop.request").write_text("normal runtime stop",encoding="utf-8")
                wait_for(lambda:facts().get("state")=="stopped")
                self.assertIsNone(second.poll(),"stopping attached runtime must leave external API running")
            finally:
                if health.exists():
                    (state/"runtime/stop.request").write_text("test cleanup",encoding="utf-8")
                    wait_for(lambda:facts().get("state")=="stopped")
                for child,marker in children:
                    if child.poll() is None:
                        marker.write_text("test cleanup",encoding="utf-8");child.wait(timeout=10)


class LocalStopTests(RoleServiceTestCase):
    def setUp(self):
        super().setUp()
        launch, claimed = self.start_and_claim()
        self.bind_instance(launch, claimed)
        self.assertEqual(self.ready_report(launch, claimed).status_code, 200)
        self.set_instance_last_seen(claimed["expected_instance_id"], 120)
        (self._tmpdir/"fixture-health.json").write_text('{"pid":99999999}', encoding="utf-8")

    def bound(self):
        return (Path("unused.json"), {"project_id":self.body_project, "hosts":[{
            "member_id":self.role_a, "health_file":str(self._tmpdir/"fixture-health.json"), "argv":["python", "fixture-host.py"]}]})

    def test_human_stop_recovers_exact_stale_owner_with_audit(self):
        from server.models import Member, RoleServiceRecovery, RoleServiceState
        from sqlmodel import select
        self.body_project = PROJECT_ID
        with self.session() as session, patch.object(local,"configured_runtime",return_value=self.bound()), \
             patch.object(local,"ensure_local_runtime",return_value="disabled"), \
             patch("scripts.role_service_recovery.local_proof",return_value={"both_stopped":True}) as proof:
            operator = session.get(Member,"human:bobo")
            self.assertTrue(local.recover_local_human_stop(PROJECT_ID,self.role_a,operator,session))
            state = session.get(RoleServiceState,(PROJECT_ID,self.role_a))
            self.assertIsNone(state.process_launch_id)
            audits = session.exec(select(RoleServiceRecovery)).all()
            self.assertEqual(len(audits),1); self.assertEqual(audits[0].confirmed_by,"human:bobo")
            self.assertEqual(proof.call_count,2)

    def test_live_unknown_or_changed_local_evidence_cannot_release_owner(self):
        from server.models import Member, RoleServiceState
        self.body_project = PROJECT_ID
        for side_effect in (HostError("recovery_process_not_absent"), [{"sha":"a"},{"sha":"b"}]):
            with self.session() as session, patch.object(local,"configured_runtime",return_value=self.bound()), \
                 patch.object(local,"ensure_local_runtime",return_value="disabled"), \
                 patch("scripts.role_service_recovery.local_proof",side_effect=side_effect):
                operator = session.get(Member,"human:bobo")
                with self.assertRaises(HTTPException):local.recover_local_human_stop(PROJECT_ID,self.role_a,operator,session)
                self.assertIsNotNone(session.get(RoleServiceState,(PROJECT_ID,self.role_a)).process_launch_id)


class DynamicLocalStopTests(RoleServiceTestCase):
    """Human stop must resolve the dynamic host used by the original instance."""

    def setUp(self):
        super().setUp()
        self.host_name = socket.gethostname()
        launch, claimed = self.start_and_claim(host=self.host_name)
        self.bind_instance(launch, claimed, host=self.host_name)
        self.assertEqual(self.ready_report(launch, claimed, host=self.host_name).status_code, 200)
        self.launch, self.claimed = launch, claimed
        self.set_instance_last_seen(claimed["expected_instance_id"], 120)
        self.temp = tempfile.TemporaryDirectory(prefix="talk-dynamic-stop-")
        self.addCleanup(self.temp.cleanup)
        self.state_dir = Path(self.temp.name)

    def prepare(self, runtime):
        from server.models import AgentInstance, ProjectRoleBinding, RunnerRegistry
        from scripts.role_service_host import _sanitize_token
        with self.session() as session:
            runner = session.get(RunnerRegistry, RUNNER_ID)
            runner.runtime = runtime
            binding = session.get(ProjectRoleBinding, (PROJECT_ID, self.role_a))
            binding.runner_id = RUNNER_ID
            instance = session.get(AgentInstance, self.claimed["expected_instance_id"])
            instance.runtime = runtime
            session.add_all([runner, binding, instance])
            session.commit()
        # Deliberately keep a workbuddy recipe present even for Kimi/Codex:
        # its mere existence must never select workbuddy-native/{project}/{member}.
        config = {"schema": "talk-runtime-config-1", "project_id": PROJECT_ID,
                  "state_dir": str(self.state_dir), "hosts": [],
                  "workbuddy": {"executable": "unused", "models_home": "unused"}}
        if runtime == "kimi-code":
            config["kimi"] = {"enabled": True}
            directory = "kimi-dynamic"
        elif runtime == "codex":
            config["codex"] = {"enabled": True, "executable": "unused"}
            directory = "codex-dynamic"
        else:
            directory = "workbuddy-native"
        health = (self.state_dir / directory / _sanitize_token(PROJECT_ID)
                  / _sanitize_token(self.role_a) / "manager-health.json")
        health.parent.mkdir(parents=True)
        seen = datetime.now(timezone.utc) - timedelta(seconds=120)
        health.write_text(json.dumps({"schema": "talk-dynamic-manager-health-1",
            "project_id": PROJECT_ID, "member_id": self.role_a, "pid": 99999999,
            "seen_at": seen.isoformat(), "state": "stopped"}), encoding="utf-8")
        return config, health

    def stop_through_api(self, runtime):
        from server.models import RoleServiceRecovery, RoleServiceState
        from sqlmodel import select
        config, _ = self.prepare(runtime)
        # Isolate the unrelated TestClient lifespan runtime spawn; the recovery
        # route still reads configured_runtime and the real local proof.
        with patch.object(local, "configured_runtime", return_value=(Path("unused.json"), config)), \
             patch.object(local, "ensure_local_runtime", return_value="disabled"), \
             patch("server.routes.role_services.require_local_runtime", return_value="requested"), \
             patch("scripts.role_service_recovery.recorded_process_state", return_value="absent"), \
             patch("scripts.role_service_recovery.process_inventory", return_value=[]):
            response = self.stop()
        self.assertEqual(response.status_code, 200, response.text)
        with self.session() as session:
            state = session.get(RoleServiceState, (PROJECT_ID, self.role_a))
            self.assertIsNone(state.process_launch_id)
            self.assertEqual(len(session.exec(select(RoleServiceRecovery)).all()), 1)

    def test_dynamic_kimi_human_stop_uses_kimi_health_not_workbuddy(self):
        self.stop_through_api("kimi-code")

    def test_dynamic_codex_human_stop_uses_codex_health_not_workbuddy(self):
        self.stop_through_api("codex")

    def test_dynamic_workbuddy_human_stop_uses_workbuddy_health(self):
        self.stop_through_api("workbuddy")

    def test_live_dynamic_manager_is_not_released_by_human_stop(self):
        from server.models import RoleServiceRecovery, RoleServiceState
        from sqlmodel import select
        config, _ = self.prepare("kimi-code")
        # Isolate the unrelated TestClient lifespan runtime spawn; the recovery
        # route still reads configured_runtime and the real local proof.
        with patch.object(local, "configured_runtime", return_value=(Path("unused.json"), config)), \
             patch.object(local, "ensure_local_runtime", return_value="disabled"), \
             patch("server.routes.role_services.require_local_runtime", return_value="requested"), \
             patch("scripts.role_service_recovery.recorded_process_state", return_value="present"), \
             patch("scripts.role_service_recovery.process_inventory", return_value=[]):
            response = self.stop()
        self.assertEqual(response.status_code, 200, response.text)
        with self.session() as session:
            state = session.get(RoleServiceState, (PROJECT_ID, self.role_a))
            self.assertIsNotNone(state.process_launch_id)
            self.assertEqual(session.exec(select(RoleServiceRecovery)).all(), [])

    def test_recent_dynamic_heartbeat_keeps_ownership(self):
        from server.models import RoleServiceRecovery, RoleServiceState
        from sqlmodel import select
        config, _ = self.prepare("kimi-code")
        self.set_instance_last_seen(self.claimed["expected_instance_id"], 0)
        # Isolate the unrelated TestClient lifespan runtime spawn; the recovery
        # route still reads configured_runtime and the real local proof.
        with patch.object(local, "configured_runtime", return_value=(Path("unused.json"), config)), \
             patch.object(local, "ensure_local_runtime", return_value="disabled"), \
             patch("server.routes.role_services.require_local_runtime", return_value="requested"), \
             patch("scripts.role_service_recovery.recorded_process_state", return_value="absent"), \
             patch("scripts.role_service_recovery.process_inventory", return_value=[]):
            response = self.stop()
        self.assertEqual(response.status_code, 200, response.text)
        with self.session() as session:
            state = session.get(RoleServiceState, (PROJECT_ID, self.role_a))
            self.assertIsNotNone(state.process_launch_id)
            self.assertEqual(session.exec(select(RoleServiceRecovery)).all(), [])

    def test_missing_dynamic_health_is_not_released(self):
        from server.models import RoleServiceRecovery, RoleServiceState
        from sqlmodel import select
        config, health = self.prepare("kimi-code")
        health.unlink()
        # Isolate the unrelated TestClient lifespan runtime spawn; the recovery
        # route still reads configured_runtime and the real local proof.
        with patch.object(local, "configured_runtime", return_value=(Path("unused.json"), config)), \
             patch.object(local, "ensure_local_runtime", return_value="disabled"), \
             patch("server.routes.role_services.require_local_runtime", return_value="requested"), \
             patch("scripts.role_service_recovery.recorded_process_state", return_value="absent"), \
             patch("scripts.role_service_recovery.process_inventory", return_value=[]):
            response = self.stop()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"], "local_recovery_unverified")
        with self.session() as session:
            state = session.get(RoleServiceState, (PROJECT_ID, self.role_a))
            self.assertIsNotNone(state.process_launch_id)
            self.assertEqual(session.exec(select(RoleServiceRecovery)).all(), [])

    def test_wrong_dynamic_health_identity_is_not_released(self):
        from server.models import RoleServiceRecovery, RoleServiceState
        from sqlmodel import select
        config, health = self.prepare("kimi-code")
        record = json.loads(health.read_text(encoding="utf-8"))
        record["member_id"] = "agent:other"
        health.write_text(json.dumps(record), encoding="utf-8")
        # Isolate the unrelated TestClient lifespan runtime spawn; the recovery
        # route still reads configured_runtime and the real local proof.
        with patch.object(local, "configured_runtime", return_value=(Path("unused.json"), config)), \
             patch.object(local, "ensure_local_runtime", return_value="disabled"), \
             patch("server.routes.role_services.require_local_runtime", return_value="requested"), \
             patch("scripts.role_service_recovery.recorded_process_state", return_value="absent"), \
             patch("scripts.role_service_recovery.process_inventory", return_value=[]):
            response = self.stop()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"], "recovery_manager_identity_mismatch")
        with self.session() as session:
            state = session.get(RoleServiceState, (PROJECT_ID, self.role_a))
            self.assertIsNotNone(state.process_launch_id)
            self.assertEqual(session.exec(select(RoleServiceRecovery)).all(), [])

    def test_real_dynamic_module_replacement_is_not_released(self):
        """Codex's reported gap: real -m hosts carry no fabricated --instance."""
        from server.models import RoleServiceRecovery, RoleServiceState
        from sqlmodel import select
        for runtime, module, serve in (("kimi-code", "kimi_role_host", False),
                                       ("codex", "codex_role_host", False),
                                       ("workbuddy", "workbuddy_role_host", True)):
            with self.subTest(runtime=runtime):
                config, _ = self.prepare(runtime)
                parts = ["python", "-B", "-X", "utf8", "-m", f"scripts.{module}"]
                if serve:
                    parts.append("serve")
                parts += ["--project", PROJECT_ID, "--member", self.role_a,
                          "--project-root", r"C:\fixture\project",
                          "--state-dir", r"C:\fixture\state",
                          "--base-url", "http://127.0.0.1:9"]
                command = subprocess.list2cmdline(parts)
                with patch.object(local, "configured_runtime",
                                  return_value=(Path("unused.json"), config)), \
                     patch.object(local, "ensure_local_runtime", return_value="disabled"), \
                     patch("server.routes.role_services.require_local_runtime",
                           return_value="requested"), \
                     patch("scripts.role_service_recovery.recorded_process_state",
                           return_value="absent"), \
                     patch("scripts.role_service_recovery.process_inventory",
                           return_value=[{"CommandLine": command}]):
                    response = self.stop()
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["detail"],
                                 "recovery_replacement_process_present")
                with self.session() as session:
                    state = session.get(RoleServiceState, (PROJECT_ID, self.role_a))
                    self.assertIsNotNone(state.process_launch_id)
                    self.assertEqual(session.exec(select(RoleServiceRecovery)).all(), [])

    def test_replacement_dynamic_process_is_not_released(self):
        from server.models import RoleServiceRecovery, RoleServiceState
        from sqlmodel import select
        config, _ = self.prepare("kimi-code")
        inventory = [{"CommandLine": "python -m scripts.kimi_role_host --instance "
                      + self.claimed["expected_instance_id"]}]
        # Isolate the unrelated TestClient lifespan runtime spawn; the recovery
        # route still reads configured_runtime and the real local proof.
        with patch.object(local, "configured_runtime", return_value=(Path("unused.json"), config)), \
             patch.object(local, "ensure_local_runtime", return_value="disabled"), \
             patch("server.routes.role_services.require_local_runtime", return_value="requested"), \
             patch("scripts.role_service_recovery.recorded_process_state", return_value="absent"), \
             patch("scripts.role_service_recovery.process_inventory", return_value=inventory):
            response = self.stop()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"], "recovery_replacement_process_present")
        with self.session() as session:
            state = session.get(RoleServiceState, (PROJECT_ID, self.role_a))
            self.assertIsNotNone(state.process_launch_id)
            self.assertEqual(session.exec(select(RoleServiceRecovery)).all(), [])


class WorkspaceManagerProtocolTests(unittest.TestCase):
    def test_manifest_protocol_matrix(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "runtime" / "capability.json"
            target.parent.mkdir()
            valid = {"schema": "talk-runtime-capability-1", "runtime_protocol": "talk-runtime-1",
                     "manager_protocol": "talk-manager-1", "supported_layouts": ["workspace-v1"],
                     "pid": os.getpid(), "started_at": "2026-11-07T00:00:00Z",
                     "written_at": "2026-11-07T00:00:00Z"}
            missing = dict(valid); missing.pop("manager_protocol")
            for manifest, accepted in [(valid, True), (missing, False),
                    ({**valid, "runtime_protocol": "talk-runtime-2"}, False),
                    ({**valid, "manager_protocol": "talk-manager-2"}, False)]:
                with self.subTest(manifest=manifest):
                    target.write_text(json.dumps(manifest), encoding="utf-8")
                    with patch.object(local, "configured_runtime", return_value=(None, {"state_dir": folder})):
                        self.assertEqual(local.workspace_runtime_capability(None) is not None, accepted)

    def test_manager_binding_matrix(self):
        from server.role_host_resolution import workspace_capability_matches
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "manager-health.json"
            role = {"project_id": "p", "member_id": "m", "runner": "dsh"}
            binding = {"instance_id": "i", "generation": 1, "launch_id": "l"}
            cap = {"schema": "talk-role-capability-1", "manager_protocol": "talk-manager-1",
                   "supported_layouts": ["workspace-v1"], "role": role, "binding": binding}
            kwargs = {"manager_protocol": "talk-manager-1", **role, **binding}
            variants = [({}, False), (cap, True), ({**cap, "schema": "wrong"}, False),
                        ({**cap, "manager_protocol": "wrong"}, False),
                        ({**cap, "supported_layouts": ["legacy"]}, False)]
            for key in role:
                variants.append(({**cap, "role": {**role, key: "wrong"}}, False))
            for key in binding:
                variants.append(({**cap, "binding": {**binding, key: "wrong"}}, False))
            variants.append(({**cap, "binding": {**binding, "generation": True}}, False))
            for value, expected in variants:
                with self.subTest(capability=value):
                    target.write_text(json.dumps({"capability": value}), encoding="utf-8")
                    self.assertEqual(workspace_capability_matches(target, **kwargs), expected)

class ProjectBindingTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import text
        self.temp = tempfile.TemporaryDirectory(prefix="project-binding-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "config.toml").write_text('[storage]\ndb_path="fixture.db"\n', encoding="utf-8")
        self.project = self.root / "project"
        self.project.mkdir()
        self.config_path = self.root / "manifest.json"
        self.config_path.write_text('{}', encoding="utf-8")
        self.config = {"project_id": "p1", "project_root": str(self.project), "state_dir": str(self.root / "state")}
        self.engine = create_engine("sqlite:///" + (self.repo / "fixture.db").as_posix())
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE projects (project_id TEXT PRIMARY KEY, project_root_path TEXT)"))
            connection.execute(text("INSERT INTO projects VALUES (:p, :r)"), {"p": "p1", "r": str(self.project)})
        self.pointer = self.project / ".talk" / "runtime.local.json"
        self.repo_pointer = self.repo / ".talk" / "runtime.local.json"
        self.repo_pointer.parent.mkdir()
        self.repo_pointer.write_text("unchanged", encoding="utf-8")
        with patch.object(local, "ROOT", self.repo):
            local.bind_local_runtime(self.config_path, self.config)

    def test_project_pointer_and_fail_closed_validation(self):
        from sqlalchemy import text
        from scripts import talk_runtime
        value = json.loads(self.pointer.read_text(encoding="utf-8"))
        self.assertEqual(value, {"schema": "talk-local-runtime-1", "database_file": str((self.repo / "fixture.db").resolve()), "config_file": str(self.config_path.resolve())})
        self.assertEqual(self.repo_pointer.read_text(encoding="utf-8"), "unchanged")
        with patch.object(talk_runtime, "load_config", return_value=self.config):
            self.assertEqual(local.configured_runtime(self.engine, "p1"), (self.config_path.resolve(), self.config))
            self.assertIsNone(local.configured_runtime(self.engine, "wrong"))
            for key, bad in [("schema", "bad"), ("database_file", str(self.root / "wrong.db")), ("config_file", str(self.root / "missing.json")), ("config_file", "relative.json")]:
                with self.subTest(key=key, bad=bad):
                    self.pointer.write_text(json.dumps({**value, key: bad}), encoding="utf-8")
                    self.assertIsNone(local.configured_runtime(self.engine, "p1"))
            self.pointer.write_text(json.dumps(value), encoding="utf-8")
            for bad_config in [{**self.config, "project_id": "wrong"}, {**self.config, "project_root": str(self.repo)}]:
                with patch.object(talk_runtime, "load_config", return_value=bad_config):
                    self.assertIsNone(local.configured_runtime(self.engine, "p1"))
            with self.engine.begin() as connection:
                connection.execute(text("UPDATE projects SET project_root_path=:r WHERE project_id='p1'"), {"r": str(self.repo)})
            self.assertIsNone(local.configured_runtime(self.engine, "p1"))
            with self.engine.begin() as connection:
                connection.execute(text("UPDATE projects SET project_root_path=:r WHERE project_id='p1'"), {"r": str(self.project)})
            self.pointer.unlink()
            self.assertIsNone(local.configured_runtime(self.engine, "p1"))

    def test_relative_project_root_is_rejected_even_when_it_resolves_to_valid_binding(self):
        from sqlalchemy import text
        from scripts import talk_runtime
        relative = "project"
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE projects SET project_root_path=:r WHERE project_id='p1'"), {"r": relative})
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.object(talk_runtime, "load_config", return_value=self.config) as load:
                self.assertIsNone(local.configured_runtime(self.engine, "p1"))
                load.assert_not_called()
        finally:
            os.chdir(original_cwd)

    def test_legacy_and_project_capability_are_separate(self):
        from scripts import talk_runtime
        from datetime import timezone
        state = Path(self.config["state_dir"]) / "runtime"
        state.mkdir(parents=True)
        capability = {"schema": "talk-runtime-capability-1", "runtime_protocol": "talk-runtime-1", "manager_protocol": "talk-manager-1", "supported_layouts": ["workspace-v1"], "pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat(), "written_at": datetime.now(timezone.utc).isoformat()}
        (state / "capability.json").write_text(json.dumps(capability), encoding="utf-8")
        with patch.object(talk_runtime, "load_config", return_value=self.config), patch.object(local, "POINTER", self.repo_pointer):
            self.assertEqual(local.workspace_runtime_capability(self.engine, "p1"), capability)
            self.assertIsNone(local.workspace_runtime_capability(self.engine, "missing"))
            self.repo_pointer.write_text(self.pointer.read_text(encoding="utf-8"), encoding="utf-8")
            with patch.object(local, "ROOT", self.repo):
                with self.assertRaisesRegex(ValueError, "local_runtime_project_mismatch"):
                    local.configured_runtime(self.engine)
                legacy = {**self.config, "project_root": str(self.repo)}
                with patch.object(talk_runtime, "load_config", return_value=legacy):
                    self.assertEqual(local.configured_runtime(self.engine), (self.config_path.resolve(), legacy))

    def test_project_binding_uses_real_config_validation(self):
        valid = {**self.config, "schema": "talk-runtime-config-1", "version": 1,
                 "base_url": "http://127.0.0.1:1", "operator_key_file": str(self.root / "human.key"),
                 "key_root": str(self.root / "keys"), "api_argv": [sys.executable, "{control_file}"], "hosts": []}
        self.config_path.write_text(json.dumps(valid), encoding="utf-8")
        self.assertEqual(local.configured_runtime(self.engine, "p1"), (self.config_path.resolve(), valid))
        self.config_path.write_text(json.dumps({**valid, "version": 2}), encoding="utf-8")
        self.assertIsNone(local.configured_runtime(self.engine, "p1"))

    def test_startup_and_deletion_request_the_given_project(self):
        from types import SimpleNamespace
        from server.role_startup import verified_runtime
        from server.role_deletions import _cleanup_binding_digest
        session = unittest.mock.Mock()
        session.get_bind.return_value = self.engine
        session.get.return_value = SimpleNamespace(project_root_path=str(self.project))
        with patch.object(local, "configured_runtime", return_value=(self.config_path, self.config)) as lookup:
            self.assertIsNotNone(_cleanup_binding_digest(session, "p1"))
            lookup.assert_called_once_with(self.engine, "p1")
        with patch.object(local, "configured_runtime", return_value=None) as lookup:
            with self.assertRaises(HTTPException) as error:
                verified_runtime("p1", "activation", session)
            self.assertEqual(error.exception.detail, "startup_local_runtime_unbound")
            lookup.assert_called_once_with(self.engine, "p1")

    def test_main_binds_attached_and_owned_runtime(self):
        from contextlib import nullcontext
        from scripts import talk_runtime
        with patch.object(talk_runtime, "load_config", return_value=self.config), \
             patch.object(talk_runtime.rsh, "ensure_private_dir"), \
             patch.object(talk_runtime, "launcher_lock", return_value=nullcontext()), \
             patch.object(talk_runtime.signal, "signal"), \
             patch.object(talk_runtime, "TalkRuntime") as runtime, \
             patch.object(local, "bind_local_runtime") as bind:
            for extra in ([], ["--attach-api"]):
                self.assertEqual(talk_runtime.main(["serve", "--config", str(self.config_path), "--apply", *extra]), 0)
            self.assertEqual(bind.call_count, 2)
            bind.assert_called_with(str(self.config_path), self.config)
            self.assertEqual(runtime.return_value.serve.call_count, 2)

    def test_spawn_and_child_environment_import_paths(self):
        from scripts import talk_runtime
        from scripts.role_service_host import HostManager
        private = self.root / "state" / "runtime"
        private.mkdir(parents=True)
        runtime = talk_runtime.TalkRuntime(self.config, client=unittest.mock.Mock())
        with patch.dict(os.environ, {"PYTHONPATH": "parent-path", "TALK_TEST_SECRET_SENTINEL": "hidden"}), patch.object(talk_runtime.subprocess, "Popen") as spawn:
            runtime.spawn("fixture", ["fixture"])
            self.assertEqual(spawn.call_args.kwargs["env"]["PYTHONPATH"], str(talk_runtime.ROOT) + os.pathsep + "parent-path")
            manager = HostManager(None, state_dir=self.root / "host", child_env={"PYTHONPATH": "override"})
            env = manager.child_environment("p1", "agent:fixture")
            self.assertEqual(env["PYTHONPATH"], str(talk_runtime.ROOT))
            self.assertNotIn("TALK_TEST_SECRET_SENTINEL", env)
