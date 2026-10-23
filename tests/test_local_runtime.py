"""本机自动宿主与human关闭恢复：隔离数据库，不启动生产模型。"""
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
from scripts.role_service_host import HostError
from tests.test_role_services import RoleServiceTestCase, PROJECT_ID


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


class ActualBootstrapTests(unittest.TestCase):
    def test_actual_api_bootstrap_and_normal_restart_keep_one_independent_runtime(self):
        from scripts.role_service_recovery import probe_pid
        with tempfile.TemporaryDirectory(prefix="talk-local-runtime-") as folder:
            root=Path(folder); state=root/"state"; state.mkdir()
            key=root/"human.key";key.write_text("fixture-only",encoding="utf-8")
            with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
            config=root/"runtime.json"
            config.write_text(json.dumps({"schema":"talk-runtime-config-1","version":1,"project_id":"prj_fixture",
                "project_root":str(local.ROOT),"state_dir":str(state),"key_root":str(root/"keys"),
                "operator_key_file":str(key),"base_url":f"http://127.0.0.1:{port}","provision_worker":False,
                "api_argv":[sys.executable,"-m","scripts.talk_api","--control-file","{control_file}"],"hosts":[]}),encoding="utf-8")
            env=dict(os.environ,TALK_RUNTIME_FIXTURE_CONFIG=str(config)); children=[]
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
                wait_for(lambda:facts().get("state")=="running")
                original=facts()["pid"]
                self.assertEqual(facts()["api_mode"],"external")
                self.assertFalse(facts()["owns_original_popen"])
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
                 patch("scripts.role_service_recovery.local_proof",side_effect=side_effect):
                operator = session.get(Member,"human:bobo")
                with self.assertRaises(HTTPException):local.recover_local_human_stop(PROJECT_ID,self.role_a,operator,session)
                self.assertIsNotNone(session.get(RoleServiceState,(PROJECT_ID,self.role_a)).process_launch_id)
