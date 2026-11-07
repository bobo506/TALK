"""统一启动入口的原句柄、动态角色、重载和停止边界；不调用原生模型。"""
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from datetime import datetime
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

    def test_capability_published_after_successful_start_and_atomically_replaced_on_restart(self):
        self.config["provision_worker"] = False
        Path(self.config["operator_key_file"]).write_text("fixture", encoding="utf-8")
        self.runtime.attach_api = True
        self.runtime.started_at = "2026-11-07T00:00:00+00:00"
        restarted = runtime.TalkRuntime(self.config, client=self.client, attach_api=True)
        restarted.started_at = "2026-11-07T00:01:00+00:00"
        target = self.private / "capability.json"
        target.write_text("old", encoding="utf-8")
        real_replace = os.replace
        replacements = []
        def replace(source, destination):
            if Path(destination) == target:
                replacements.append((Path(source).parent, target.read_text(encoding="utf-8")))
            return real_replace(source, destination)
        with patch.object(runtime.os, "replace", side_effect=replace), \
             patch.object(self.runtime, "wait_api"), patch.object(self.runtime, "health"), \
             patch.object(self.runtime, "stop"), patch.object(restarted, "wait_api"), \
             patch.object(restarted, "health"), patch.object(restarted, "stop"):
            self.runtime.stopping = True
            self.runtime._serve()
            first = json.loads(target.read_text(encoding="utf-8"))
            restarted.stopping = True
            restarted._serve()
        second = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(set(first), {"schema", "runtime_protocol", "supported_layouts", "pid", "started_at", "written_at"})
        self.assertEqual(first["schema"], "talk-runtime-capability-1")
        self.assertEqual(first["runtime_protocol"], "talk-runtime-1")
        self.assertEqual(first["supported_layouts"], ["legacy", "workspace-v1"])
        self.assertEqual(first["pid"], os.getpid())
        self.assertEqual(first["started_at"], self.runtime.started_at)
        datetime.fromisoformat(first["started_at"].replace("Z", "+00:00"))
        datetime.fromisoformat(second["written_at"].replace("Z", "+00:00"))
        self.assertEqual(len(replacements), 2)
        self.assertEqual(replacements[0], (self.private, "old"))
        self.assertEqual(json.loads(replacements[1][1]), first)
        self.assertEqual(second["started_at"], restarted.started_at)

    def test_capability_publish_failure_is_nonfatal_and_failed_start_does_not_publish(self):
        self.config["provision_worker"] = False
        Path(self.config["operator_key_file"]).write_text("fixture", encoding="utf-8")
        self.runtime.attach_api = True
        self.runtime.stopping = True
        with patch.object(self.runtime, "wait_api"), patch.object(self.runtime, "health"), \
             patch.object(self.runtime, "stop") as stop, \
             patch.object(runtime.rsh, "_publish_private_bytes", side_effect=OSError("failure")), \
             patch("builtins.print") as warning:
            self.runtime._serve()
        stop.assert_called_once()
        warning.assert_called_once_with("runtime_capability_write_failed", file=sys.stderr)
        with patch.object(self.runtime, "wait_api", side_effect=RuntimeError("not ready")), \
             patch.object(self.runtime, "health"), patch.object(self.runtime, "_stop_api"), \
             patch.object(self.runtime, "publish_capability") as publish:
            with self.assertRaises(RuntimeError):
                self.runtime._serve()
        publish.assert_not_called()
    def test_dsh_effort_refresh_reads_patch_and_posts_once(self):
        native = self.state / "native" / "prj_fixture" / "agent_dsh"
        native.mkdir(parents=True)
        (native / "model-deepseek-flash.patch.yml").write_text(
            "model:\n  reasoningEffort: MAX\n", encoding="utf-8"
        )
        self.runtime.refresh_dsh_efforts([
            {"member_id": "agent:dsh", "runner": {"runtime": "dsh"}},
            {"member_id": "agent:codex", "runner": {"runtime": "codex"}},
            {"member_id": "agent:other", "runner": {"runtime": "dsh"}},
        ])
        posts = [
            call
            for call in self.client.calls
            if call[0] == "POST" and "binding/default-effort" in call[1]
        ]
        self.assertEqual(
            posts,
            [
                (
                    "POST",
                    "/api/projects/prj_fixture/roles/agent%3Adsh/binding/default-effort",
                    {"default_effort": "max"},
                )
            ],
        )

    def test_dsh_effort_refresh_skips_roles_without_patch(self):
        self.runtime.refresh_dsh_efforts([
            {"member_id": "agent:nopatch", "runner": {"runtime": "dsh"}},
        ])
        self.assertEqual(
            [
                call
                for call in self.client.calls
                if "binding/default-effort" in call[1]
            ],
            [],
        )

    def test_dsh_effort_refresh_failure_does_not_raise(self):
        native = self.state / "native" / "prj_fixture" / "agent_dsh"
        native.mkdir(parents=True)
        (native / "model-x.patch.yml").write_text("reasoningEffort: high\n", encoding="utf-8")
        original = self.runtime.request
        def boom(*args, **kwargs):
            raise RuntimeError("offline")
        self.runtime.request = boom
        try:
            self.runtime.refresh_dsh_efforts([
                {"member_id": "agent:dsh", "runner": {"runtime": "dsh"}},
            ])
        finally:
            self.runtime.request = original

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
    def test_workspace_v1_is_refused_before_dynamic_or_configured_spawn(self):
        workspace = self.role("agent:workspace", generation=1, ownership_held=False)
        workspace["storage_layout"] = "workspace-v1"
        self.config["hosts"] = [self.spec("agent:workspace"), self.spec()]
        self.runtime.reconcile_hosts([workspace, self.role(generation=1, ownership_held=False)])
        self.assertEqual([item[0] for item in self.spawned], ["host-agent_one"])
        self.assertEqual(self.runtime.statuses["agent:workspace"], {
            "state": "workspace_runtime_not_ready",
            "error_code": "workspace_runtime_not_ready",
            "error_message": "角色已准备，运行时隔离待启用",
        })
        self.assertNotIn("agent:workspace", self.runtime.hosts)
        self.assertEqual(self.client.calls, [])

    def test_workspace_specs_use_authoritative_role_paths_and_reject_overrides(self):
        from server import workspace_paths as wp
        data = self.root / "data"
        data.mkdir()
        self.config.update(codex={"enabled": True, "executable": sys.executable},
                           kimi={"enabled": True}, dsh={"enabled": True},
                           workbuddy={"executable": "fixture", "models_home": "fixture"})
        for runner, method, recipe in (("codex", "codex_spec", "codex"),
                                       ("kimi-code", "kimi_spec", "kimi"),
                                       ("dsh", "dsh_spec", "dsh"),
                                       ("workbuddy", "workbuddy_spec", "workbuddy")):
            with self.subTest(runner=runner), patch.object(runtime, "ROOT", data):
                role = {"member_id": "agent:new", "project_id": self.runtime.project,
                        "storage_layout": "workspace-v1", "binding_state": "bound",
                        "runner": {"runtime": runner, "runner_id": "runner:dsh-test"},
                        "service": {"control_kind": "managed_cli"},
                        "model": {"choice_id": "choice", "model_alias": "alias"}}
                def request(method, path, body=None, **kwargs):
                    if path.endswith("/role-storage-layouts"):
                        return [{"member_id": "agent:new", "storage_layout": "workspace-v1"}]
                    if path.endswith("/roles"):
                        return [role]
                    if path == "/api/members/me":
                        return self.client.identity
                    return {"project_root_path": str(self.project)}
                key = wp.key_path(data, self.runtime.project, "agent:new")
                key.parent.mkdir(parents=True, exist_ok=True)
                key.write_text("fixture-secret", encoding="utf-8")
                with patch.object(self.client, "request", side_effect=request):
                    spec = getattr(self.runtime, method)(role)
                    ctx = spec["workspace_context"]
                    self.assertEqual(json.loads(spec["argv"][spec["argv"].index("--workspace-context") + 1]), ctx)
                    self.assertEqual(spec["argv"][spec["argv"].index("--key-root") + 1], self.config["key_root"])
                    args = (data, self.runtime.project, "agent:new")
                    self.assertEqual(ctx["key"], str(key))
                    self.assertEqual(ctx["home"], str(wp.native_home_dir(*args)))
                    self.assertEqual(ctx["session"], str(wp.execution_session_store_path(*args)))
                    self.assertEqual(ctx["state"]["records"], str(wp.records_dir(*args)))
                    self.assertEqual(ctx["state"]["control"], str(wp.control_dir(*args)))
                    self.assertEqual(ctx["state"]["manager"], str(wp.manager_dir(*args, recipe)))
                    self.assertEqual(ctx["logs"], str(wp.logs_dir(*args)))
                    self.assertEqual(spec["argv"][spec["argv"].index("--role-key-file") + 1], str(key))
                    for field in ("role_key_file", "native_home", "session_store"):
                        self.config[recipe][field] = str(self.root / "wrong")
                        with self.assertRaisesRegex(ValueError, "workspace_override_mismatch"):
                            getattr(self.runtime, method)(role)
                        del self.config[recipe][field]
                    self.config[recipe]["key_files"] = {"agent:new": str(self.root / "wrong")}
                    with self.assertRaisesRegex(ValueError, "workspace_override_mismatch"):
                        getattr(self.runtime, method)(role)
                    del self.config[recipe]["key_files"]
                    other = dict(role, member_id="agent:other")
                    def other_request(method, path, body=None, **kwargs):
                        if path.endswith("/role-storage-layouts"):
                            return [{"member_id": "agent:other", "storage_layout": "workspace-v1"}]
                        if path.endswith("/roles"):
                            return [other]
                        return {"project_root_path": str(self.project)}
                    with patch.object(self.client, "request", side_effect=other_request):
                        other_ctx = self.runtime.workspace_role_context(other)
                    for field in ("key", "home", "session", "state", "logs"):
                        self.assertNotEqual(ctx[field], other_ctx[field])

    def test_workspace_context_rejects_forged_role_layout_and_project_root(self):
        role = {"member_id": "agent:new", "storage_layout": "workspace-v1",
                "runner": {"runtime": "codex"}, "binding_state": "bound"}
        def facts(authoritative_role, layout="workspace-v1", root=None):
            def request(method, path, body=None):
                if path.endswith("/role-storage-layouts"):
                    return [{"member_id": "agent:new", "storage_layout": layout}]
                if path.endswith("/roles"):
                    return [authoritative_role]
                return {"project_root_path": str(root or self.project)}
            return request
        with patch.object(runtime, "ROOT", self.root):
            for authority, layout, root in ((dict(role, binding_state="unbound"), "workspace-v1", None),
                                            (role, "legacy", None), (role, "workspace-v1", self.root)):
                with self.subTest(layout=layout, root=root), patch.object(self.runtime, "request", side_effect=facts(authority, layout, root)):
                    with self.assertRaises(ValueError):
                        self.runtime.workspace_role_context(role)

    def test_workspace_git_key_and_missing_key_never_fall_back_to_legacy(self):
        from server import workspace_paths as wp
        data = self.root / "git-data"
        data.mkdir()
        (data / ".git").write_text("gitdir: fixture", encoding="utf-8")
        role = {"member_id": "agent:new", "storage_layout": "workspace-v1", "binding_state": "bound",
                "runner": {"runtime": "codex"}, "service": {"control_kind": "managed_cli"},
                "model": {"choice_id": "choice", "model_alias": "alias"}}
        self.config["codex"] = {"enabled": True, "executable": sys.executable}
        legacy = runtime.key_file_path(Path(self.config["key_root"]), "agent:new")
        legacy.parent.mkdir()
        legacy.write_text("fixture-secret", encoding="utf-8")
        def request(method, path, body=None, **kwargs):
            if path.endswith("/role-storage-layouts"):
                return [{"member_id": "agent:new", "storage_layout": "workspace-v1"}]
            if path.endswith("/roles"):
                return [role]
            if path == "/api/members/me":
                self.fail("missing workspace key must not use legacy identity")
            return {"project_root_path": str(self.project)}
        with patch.object(runtime, "ROOT", data), patch.object(self.client, "request", side_effect=request):
            ctx = self.runtime.workspace_role_context(role)
            self.assertEqual(ctx["key"], str(wp.key_path(data, self.runtime.project, "agent:new", git_key_root=legacy.parent)))
            self.assertNotEqual(Path(ctx["key"]), legacy)
            self.assertIsNone(self.runtime.codex_spec(role))
            self.assertEqual(self.runtime.statuses["agent:new"]["state"], "key_not_configured")

    def test_legacy_runner_specs_preserve_existing_recipes_and_key_override(self):
        from scripts import codex_role_host, kimi_role_host, dsh_role_host
        self.config.update(codex={"enabled": True, "executable": sys.executable},
                           kimi={"enabled": True}, dsh={"enabled": True},
                           workbuddy={"executable": "fixture", "models_home": "fixture"})
        key = runtime.key_file_path(Path(self.config["key_root"]), "agent:new")
        key.parent.mkdir()
        key.write_text("fixture-secret", encoding="utf-8")
        for runner, method, module in (("codex", "codex_spec", codex_role_host),
                                        ("kimi-code", "kimi_spec", kimi_role_host),
                                        ("dsh", "dsh_spec", dsh_role_host)):
            role = {"member_id": "agent:new", "storage_layout": "legacy", "binding_state": "bound",
                    "runner": {"runtime": runner, "runner_id": "runner:dsh-test"},
                    "service": {"control_kind": "managed_cli"},
                    "model": {"choice_id": "choice", "model_alias": "alias"}}
            with self.subTest(runner=runner):
                self.assertEqual(getattr(self.runtime, method)(role), module.host_spec(self.config, role))
        override = self.root / "override.key"
        override.write_text("fixture-secret", encoding="utf-8")
        self.config["workbuddy"]["key_files"] = {"agent:new": str(override)}
        role = {"member_id": "agent:new", "storage_layout": "legacy", "binding_state": "bound",
                "runner": {"runtime": "workbuddy"}}
        spec = self.runtime.workbuddy_spec(role)
        self.assertEqual(spec["argv"][spec["argv"].index("--role-key-file") + 1], str(override))
        self.assertNotIn("workspace_context", spec)

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
    def test_api_reload_falls_back_to_force_stop_when_graceful_times_out(self):
        self.runtime.api = Process(77)
        self.runtime.api_control_file = self.private / "owned.stop"
        self.runtime.api_control_file.write_text("talk-runtime-stop\n", encoding="utf-8")
        calls = {"count": 0}
        def wait(timeout=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise subprocess.TimeoutExpired("fixture-api", timeout)
            self.runtime.api.returncode = 1
            return 0
        self.runtime.api.wait = wait
        terminated = []
        self.runtime.api.terminate = lambda: terminated.append("terminate")
        with patch.object(self.runtime, "wait_api"):
            self.runtime.reload_api()
        self.assertEqual(terminated, ["terminate"])
        self.assertEqual(self.spawned[-1][0], "api")
        self.assertFalse((self.private / "owned.stop").exists())

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
