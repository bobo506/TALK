"""统一启动入口的原句柄、动态角色、重载和停止边界；不调用原生模型。"""
from __future__ import annotations
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import talk_runtime as runtime


class Process:
    def __init__(self,pid): self.pid,self.returncode=pid,None
    def poll(self): return self.returncode
    def wait(self,timeout=None): self.returncode=0;return 0


class Client:
    def __init__(self): self.rows=[];self.calls=[];self.identity={"id":"agent:new","kind":"agent","display_name":"created"}
    def request(self,method,path,body=None,**kwargs):
        self.calls.append((method,path,body))
        if path=="/api/members/me":return self.identity if kwargs else {"kind":"human"}
        if method=="POST":
            for row in self.rows:row["service"]={"ownership_held":False}
            return {}
        return {"data":self.rows}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="talk-runtime-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/"project";self.project.mkdir()
        self.state=self.root/"state";self.state.mkdir();self.private=self.state/"runtime";self.private.mkdir()
        self.config={"schema":"talk-runtime-config-1","version":1,"project_id":"prj_fixture",
            "project_root":str(self.project),"state_dir":str(self.state),"key_root":str(self.root/"keys"),
            "operator_key_file":str(self.root/"human.key"),"base_url":"http://127.0.0.1:1",
            "api_argv":[sys.executable,"-m","scripts.talk_api","--control-file","{control_file}"],"hosts":[]}
        self.path=self.root/"runtime.json"
        self.client=Client();self.spawned=[];self.now=0
        def spawn(label,argv):
            p=Process(100+len(self.spawned));self.spawned.append((label,argv,p));return p
        self.runtime=runtime.TalkRuntime(self.config,client=self.client,spawn=spawn,clock=lambda:self.now,sleeper=self.advance)
    def advance(self,seconds):self.now+=seconds
    def write_config(self):self.path.write_text(json.dumps(self.config),encoding="utf-8")
    def spec(self,member="agent:one"):
        d=self.state/member.replace(":","_");d.mkdir(exist_ok=True)
        return {"member_id":member,"argv":[sys.executable,"fixture.py"],"health_file":str(d/"health.json"),"drain_file":str(d/"drain.request")}
    def role(self,member="agent:one",**service):return {"member_id":member,"service":service}
    def test_config_rejects_remote_inline_key_and_path_escape(self):
        self.write_config();self.assertEqual(runtime.load_config(self.path)["project_id"],"prj_fixture")
        for key,value,code in [("base_url","http://example.org:8000","loopback"),("key_root",str(self.project/"keys"),"inside_project"),("api_argv",[sys.executable,"--key","fixture","{control_file}"],"argv")]:
            old=self.config[key];self.config[key]=value;self.write_config()
            with self.assertRaisesRegex(runtime.RuntimeErrorCode,code):runtime.load_config(self.path)
            self.config[key]=old
        s=self.spec();s["health_file"]=str(self.root/"escape.json");self.config["hosts"]=[s];self.write_config()
        with self.assertRaisesRegex(runtime.RuntimeErrorCode,"path_escape"):runtime.load_config(self.path)
    def test_singleton_uses_live_os_lock_and_releases(self):
        with runtime.launcher_lock(self.private):
            with self.assertRaisesRegex(runtime.RuntimeErrorCode,"already_running"):
                with runtime.launcher_lock(self.private):pass
        with runtime.launcher_lock(self.private):pass
    def test_old_runtime_pid_reuse_is_not_live_status_or_stop_authority(self):
        self.write_config()
        (self.private/"health.json").write_text('{"pid":123,"seen_at":"2026-10-01T00:00:00Z"}',encoding="utf-8")
        with patch.object(runtime,"recorded_process_state",return_value="previous_boot"), patch("builtins.print") as output:
            runtime.main(["status","--config",str(self.path)])
            self.assertFalse(json.loads(output.call_args.args[0])["process_present"])
            with self.assertRaisesRegex(runtime.RuntimeErrorCode,"runtime_not_running"):
                runtime.main(["stop","--config",str(self.path),"--apply"])
        self.assertFalse((self.private/"stop.request").exists())
    def test_redirector_ancestry_never_accepts_unrelated_pid_or_cycle(self):
        self.assertTrue(runtime.is_owned_descendant(1,3,{3:2,2:1}))
        self.assertTrue(runtime.is_owned_descendant(1,1,{}))
        self.assertFalse(runtime.is_owned_descendant(1,3,{3:2,2:3}))
        self.assertFalse(runtime.is_owned_descendant(1,3,{3:4,4:0}))
    def test_dry_run_never_spawns_or_reads_operator_key(self):
        self.write_config()
        with patch.object(runtime.subprocess,"Popen") as popen:
            self.assertEqual(runtime.main(["serve","--config",str(self.path)]),0)
        popen.assert_not_called()
    def test_boot_only_starts_manager_and_never_requests_role_start(self):
        self.config["hosts"]=[self.spec()]
        self.runtime.reconcile_hosts([self.role(generation=3,ownership_held=False)])
        self.runtime.reconcile_hosts([self.role(generation=3,ownership_held=False)])
        self.assertEqual(len(self.spawned),1)
        self.assertEqual(self.client.calls,[])
        self.assertEqual(self.runtime.statuses["agent:one"]["state"],"starting")
    def test_external_manager_or_unknown_owner_is_never_adopted(self):
        s=self.spec();self.config["hosts"]=[s]
        Path(s["health_file"]).write_text('{"pid":123}',encoding="utf-8")
        with patch.object(runtime,"recorded_process_state",return_value="present"):
            self.runtime.reconcile_hosts([self.role(ownership_held=True)])
        self.assertEqual(self.runtime.statuses["agent:one"]["state"],"external_manager")
        with patch.object(runtime,"recorded_process_state",return_value="exited"):
            self.runtime.reconcile_hosts([self.role(ownership_held=True)])
        self.assertEqual(self.runtime.statuses["agent:one"]["state"],"recovery_required")
        self.assertFalse(self.spawned);self.assertFalse(self.runtime.hosts)
    def test_reused_manager_pid_does_not_block_but_old_owner_still_requires_human_stop(self):
        spec=self.spec();self.config["hosts"]=[spec]
        Path(spec["health_file"]).write_text('{"pid":123}',encoding="utf-8")
        with patch.object(runtime,"recorded_process_state",return_value="previous_boot"):
            self.runtime.reconcile_hosts([self.role(ownership_held=True)])
            self.assertEqual(self.runtime.statuses["agent:one"]["state"],"recovery_required")
            self.assertFalse(self.spawned)
            self.runtime.reconcile_hosts([self.role(ownership_held=False)])
            self.assertEqual(len(self.spawned),1)
    def test_manager_failures_back_off_and_stop_after_three_until_generation_changes(self):
        self.config["hosts"]=[self.spec()];role=self.role(generation=3,ownership_held=False)
        for count in range(3):
            self.runtime.reconcile_hosts([role]);self.spawned[-1][2].returncode=1
            self.runtime.reconcile_hosts([role]);self.now+=40
        self.runtime.reconcile_hosts([role]);self.assertEqual(len(self.spawned),3)
        self.assertEqual(self.runtime.statuses["agent:one"]["attempts"],3)
        self.runtime.reconcile_hosts([self.role(generation=4,ownership_held=False)])
        self.assertEqual(len(self.spawned),4)
    def test_os_spawn_failure_is_bounded_without_releasing_owner(self):
        self.config["hosts"]=[self.spec()];role=self.role(generation=1,ownership_held=False)
        with patch.object(self.runtime,"spawn",side_effect=OSError("fixture spawn error")) as spawn:
            for _ in range(5):self.runtime.reconcile_hosts([role]);self.now+=40
        self.assertEqual(spawn.call_count,3)
        self.assertEqual(self.client.calls,[])
    def test_dynamic_workbuddy_uses_exact_identity_key_and_separate_home(self):
        keys=Path(self.config["key_root"]);keys.mkdir();key=runtime.key_file_path(keys,"agent:new");key.write_text("fixture-secret",encoding="utf-8")
        self.config["workbuddy"]={"executable":str(self.root/"WorkBuddy.exe"),"models_home":str(self.root/"models")}
        role={"member_id":"agent:new","role_name":"Renamed project role","binding_state":"bound","runner":{"runtime":"workbuddy"},"service":{}}
        self.runtime.reconcile_hosts([role])
        argv=self.spawned[0][1]
        self.assertIn(str(key),argv);self.assertNotIn("fixture-secret",argv)
        self.assertEqual(argv[argv.index("--workbuddy-display-name")+1],"created")
        self.assertIn("agent_new",self.runtime.hosts["agent:new"]["spec"]["health_file"])
    def test_identity_mismatch_cannot_spawn_and_does_not_block_other_host(self):
        keys=Path(self.config["key_root"]);keys.mkdir();runtime.key_file_path(keys,"agent:new").write_text("fixture-secret",encoding="utf-8")
        self.config["workbuddy"]={"executable":"unused","models_home":"unused"};self.config["hosts"]=[self.spec()]
        self.client.identity["id"]="agent:other"
        self.runtime.reconcile_hosts([{"member_id":"agent:new","binding_state":"bound","runner":{"runtime":"workbuddy"}},self.role()])
        self.assertEqual(self.runtime.statuses["agent:new"]["state"],"identity_mismatch")
        self.assertEqual(len(self.spawned),1)
    def test_worker_io_does_not_block_reconciliation_or_overlap(self):
        done=threading.Event();started=threading.Event();calls=[]
        class Worker:
            def run_round(self):calls.append(1);started.set();done.wait(2)
        self.runtime.worker=Worker()
        self.runtime.worker_tick();self.assertTrue(started.wait(1));self.runtime.worker_tick()
        self.config["hosts"]=[self.spec()];self.runtime.reconcile_hosts([self.role()])
        self.assertEqual(len(self.spawned),1);self.assertEqual(len(calls),1)
        done.set();self.runtime.worker_thread.join(1)
    def test_api_reload_keeps_original_manager_popen(self):
        self.config["hosts"]=[self.spec()];self.runtime.reconcile_hosts([self.role()]);owned=self.runtime.hosts["agent:one"]
        self.runtime.api=Process(77);self.runtime.api_control_file=self.private/"owned.stop"
        with patch.object(self.runtime,"wait_api"):
            self.runtime.reload_api()
        self.assertIs(self.runtime.hosts["agent:one"],owned)
        self.assertIsNone(owned["process"].poll())
        self.assertEqual(self.spawned[-1][0],"api")
        self.assertFalse((self.private/"owned.stop").exists())
    def test_attached_api_readiness_and_shutdown_do_not_spawn_or_stop_external_api(self):
        attached = runtime.TalkRuntime(self.config, client=self.client, spawn=self.runtime.spawn_override, attach_api=True)
        attached.wait_api()
        attached.stop()
        self.assertIsNone(attached.api)
        self.assertEqual(self.spawned, [])
        value = json.loads((self.private/"health.json").read_text(encoding="utf-8"))
        self.assertFalse(value["owns_original_popen"])
        self.assertEqual(value["api_mode"], "external")
    def test_shutdown_uses_ordinary_stop_then_drain_then_api(self):
        s=self.spec()
        self.config["hosts"]=[s];self.runtime.reconcile_hosts([self.role()]);self.client.rows=[self.role(can_stop=True,ownership_held=True)]
        Path(s["health_file"]).write_text('{"owned_launches":[]}',encoding="utf-8")
        self.runtime.api=Process(77);self.runtime.api_control_file=self.private/"api.stop"
        self.runtime.stop()
        self.assertTrue(any(c[0]=="POST" and c[1].endswith("/service/stop") for c in self.client.calls))
        self.assertEqual(self.runtime.api.poll(),0)
        self.assertFalse(Path(s["drain_file"]).exists())
    def test_failed_stop_retains_owned_handles_and_leaves_api_running(self):
        self.config["hosts"]=[self.spec()];self.runtime.reconcile_hosts([self.role()]);owned=self.runtime.hosts["agent:one"]
        self.client.rows=[self.role(ownership_held=True,can_stop=False)];self.runtime.api=Process(77)
        with self.assertRaisesRegex(runtime.RuntimeErrorCode,"role_stop_timeout"):self.runtime.stop()
        self.assertIs(self.runtime.hosts["agent:one"],owned);self.assertIsNone(self.runtime.api.poll())


class ActualApiControlTests(unittest.TestCase):
    def test_real_child_exits_via_private_marker_without_console(self):
        with tempfile.TemporaryDirectory(prefix="talk-api-control-") as folder:
            marker=Path(folder)/"api.stop"
            with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
            # FastAPI's built-in app is enough: no production DB, routes or models.
            command=[sys.executable,"-B","-m","scripts.talk_api","--app","fastapi:FastAPI","--port",str(port),"--control-file",str(marker)]
            p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                **({"creationflags":subprocess.CREATE_NO_WINDOW} if sys.platform=="win32" else {}))
            try:
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    with socket.socket() as s:
                        if s.connect_ex(("127.0.0.1",port))==0:break
                    if p.poll() is not None:self.fail("isolated API exited during startup")
                    time.sleep(.05)
                else:self.fail("isolated API did not bind")
                marker.write_text("stop",encoding="utf-8")
                self.assertEqual(p.wait(timeout=8),0)
            finally:
                if p.poll() is None:p.terminate();p.wait(timeout=8)


if __name__=="__main__":unittest.main()
