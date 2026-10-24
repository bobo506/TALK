"""Real Windows files and a real ordinary-drain child; all resources are temporary."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import role_delete as d
from scripts import role_provision as provision
from scripts import role_service_host as host
from scripts.talk_runtime import TalkRuntime
from bridges.runtime_log_retention import NativeFile


@unittest.skipUnless(os.name=="nt","Windows handle deletion")
class LocalDeletionTests(unittest.TestCase):
    def setUp(self):
        scratch=Path(__file__).resolve().parents[1]/".tmp-tests";scratch.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix="talk-delete-isolated-",dir=scratch);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project=self.root/"project";self.project.mkdir()
        self.keys=self.root/"keys";self.keys.mkdir();self.state=self.root/"state";self.state.mkdir()
        self.member="agent:delete-fixture";self.project_id="prj_fixture"
        self.config={"project_id":self.project_id,"project_root":str(self.project),"state_dir":str(self.state),
            "key_root":str(self.keys),"hosts":[],"base_url":"http://127.0.0.1:1"}
        self.path=self.root/"runtime.json";self.write_config()
        self.runtime=TalkRuntime(copy.deepcopy(self.config),config_path=self.path)
        self.receipt={"identity_disabled":True,"credential_digest":hashlib.sha256(b"isolated-role-key").hexdigest()}
        self.profile=provision.profile_target_paths(self.project,self.member)["identity"]
        self.profile.parent.mkdir(parents=True);self.profile.write_text("isolated identity",encoding="utf-8")
        self.key=provision.key_file_path(self.keys,self.member);self.key.write_text("isolated-role-key\n",encoding="utf-8")
        self.metadata=provision.credential_metadata_path(self.keys,self.member)
        self.metadata.write_text(json.dumps({"member_id":self.member}),encoding="utf-8")
        self.other=self.project/".talk/agents/agent_other/IDENTITY.md";self.other.parent.mkdir();self.other.write_text("keep",encoding="utf-8")
        self.record=self.state/"roles"/self.project_id/host._sanitize_token(self.member)/"launch_fixture.json"
        self.record.parent.mkdir(parents=True);self.record.write_text(json.dumps({"project_id":self.project_id,"member_id":self.member,"launch_id":"launch_fixture","pid":2147483000,"owner_token":"temporary"}),encoding="utf-8")
        self.control=self.state/"control/launch_fixture.ctl";self.control.parent.mkdir();self.control.write_text("private control",encoding="utf-8")

    def write_config(self):
        self.path.write_text(json.dumps(self.config),encoding="utf-8")

    def run_cleanup(self):
        return d.cleanup(self.runtime,self.member,self.receipt)

    def test_actual_files_config_and_private_state_removed_other_role_preserved(self):
        self.config["workbuddy"]={"key_files":{self.member:str(self.key),"agent:other":"other.key"},"models_home":"shared-models"}
        self.write_config();self.runtime.config=copy.deepcopy(self.config)
        result=self.run_cleanup();self.assertEqual(result["outcome"],"complete",result)
        for path in (self.profile,self.key,self.metadata,self.record,self.control):self.assertFalse(path.exists(),path)
        self.assertEqual(self.other.read_text(encoding="utf-8"),"keep")
        saved=json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["workbuddy"]["key_files"],{"agent:other":"other.key"})
        self.assertEqual(saved["workbuddy"]["models_home"],"shared-models")
        self.assertEqual(self.run_cleanup()["outcome"],"complete")

    def test_shared_identity_key_and_metadata_preserved(self):
        self.receipt={"identity_disabled":False,"credential_digest":None}
        result=self.run_cleanup();self.assertEqual(result["outcome"],"complete",result)
        self.assertEqual(result["steps"]["credentials"],"preserved")
        self.assertTrue(self.key.exists());self.assertTrue(self.metadata.exists());self.assertFalse(self.profile.exists())

    def test_locked_file_fails_honestly_and_retry_finishes(self):
        with NativeFile(self.profile):
            result=self.run_cleanup()
        self.assertEqual(result["outcome"],"failed");self.assertEqual(result["steps"]["profiles"],"failed")
        self.assertTrue(self.key.exists());self.assertEqual(self.run_cleanup()["outcome"],"complete")

    def test_wrong_key_is_preserved_until_correct_ownership(self):
        self.key.write_text("another-role-key",encoding="utf-8")
        result=self.run_cleanup();self.assertEqual(result["error_code"],"credential_mismatch")
        self.assertEqual(self.key.read_text(encoding="utf-8"),"another-role-key")
        self.key.write_text("isolated-role-key",encoding="utf-8")
        self.assertEqual(self.run_cleanup()["outcome"],"complete")

    def test_concurrent_provision_lock_prevents_resource_cleanup(self):
        locks=provision.acquire_provision_locks(self.project,self.keys,self.member)
        try:result=self.run_cleanup()
        finally:provision.release_provision_locks(locks)
        self.assertEqual(result["outcome"],"failed");self.assertTrue(self.profile.exists());self.assertTrue(self.key.exists())

    def test_config_concurrent_change_never_overwritten_and_retry_after_reload(self):
        changed={**self.config,"unrelated_setting":"keep-new-value"}
        self.path.write_text(json.dumps(changed),encoding="utf-8")
        result=self.run_cleanup();self.assertEqual(result["error_code"],"runtime_config_changed")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")),changed)
        self.runtime.config=changed;self.assertEqual(self.run_cleanup()["outcome"],"complete")

    def test_hardlink_and_junction_never_delete_outside_resource(self):
        outside=self.root/"outside.txt";outside.write_text("outside",encoding="utf-8")
        self.profile.unlink();os.link(outside,self.profile)
        result=self.run_cleanup();self.assertEqual(result["error_code"],"unsafe_resource")
        self.assertEqual(outside.read_text(encoding="utf-8"),"outside");self.profile.unlink()
        target=self.root/"outside";target.mkdir();(target/"keep.txt").write_text("keep",encoding="utf-8")
        junction=self.profile.parent/"linked-dir"
        # Native junction creation; deletion helper must reject rather than traverse it.
        result=subprocess.run(["cmd","/c","mklink","/J",str(junction),str(target)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0)
        try:
            self.assertEqual(self.run_cleanup()["outcome"],"failed")
            self.assertEqual((target/"keep.txt").read_text(encoding="utf-8"),"keep")
        finally:os.rmdir(junction)

    def test_external_manager_is_not_adopted_and_no_key_deleted(self):
        directory=self.state/"manager";directory.mkdir()
        health=directory/"health.json";health.write_text(json.dumps({"pid":123,"seen_at":"unknown"}),encoding="utf-8")
        self.runtime.config["hosts"]=[{"member_id":self.member,"health_file":str(health),"drain_file":str(directory/"drain.request"),"argv":[sys.executable]}]
        with patch("scripts.role_service_recovery.recorded_process_state",return_value="present"):
            result=self.run_cleanup()
        self.assertEqual(result["error_code"],"manager_not_stopped");self.assertTrue(self.profile.exists());self.assertTrue(self.key.exists())

    def test_original_real_child_drains_normally_before_cleanup(self):
        directory=self.state/"manager";directory.mkdir();marker=directory/"drain.request";health=directory/"health.json"
        code="import pathlib,time,sys; p=pathlib.Path(sys.argv[1]);\nwhile not p.exists(): time.sleep(.02)\n"
        child=subprocess.Popen([sys.executable,"-c",code,str(marker)],creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            health.write_text(json.dumps({"owned_launches":[]}),encoding="utf-8")
            spec={"member_id":self.member,"health_file":str(health),"drain_file":str(marker),"argv":[sys.executable]}
            self.runtime.hosts[self.member]={"process":child,"spec":spec}
            result=self.run_cleanup();self.assertEqual(result["outcome"],"complete",result)
            self.assertEqual(child.poll(),0);self.assertFalse(health.exists());self.assertFalse(marker.exists())
        finally:
            if child.poll() is None:marker.write_text("stop",encoding="utf-8");child.wait(timeout=5)

    def test_runtime_claim_report_uses_bound_role_and_one_cleanup_per_tick(self):
        calls=[]
        class Client:
            def request(_,method,path,body=None):
                calls.append((method,path,body))
                if method=="GET":return {"project_root_path":str(self.project)}
                digest=hashlib.sha256(json.dumps(self.runtime.config,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
                return {**self.receipt,"lease_token":"test-lease","revision":2,"cleanup_config_digest":digest} if path.endswith("/claim") else {}
        self.runtime.client=Client()
        self.runtime.reconcile_deletions([{"member_id":self.member,"archived":True,"deletion":{"status":"pending","revision":1}}])
        self.assertEqual(len(calls),3);self.assertEqual(calls[-1][2]["outcome"],"complete")
        self.assertNotIn("credential_digest",calls[-1][2]);self.assertNotIn("test-lease",json.dumps(calls[0]))

    def test_live_private_child_receipt_refuses_even_if_database_was_stopped(self):
        facts=json.loads(self.record.read_text(encoding="utf-8"));facts["pid"]=os.getpid()
        self.record.write_text(json.dumps(facts),encoding="utf-8")
        with patch("scripts.role_service_recovery.recorded_process_state",return_value="present"):
            result=self.run_cleanup()
        self.assertEqual(result["error_code"],"manager_not_stopped")
        self.assertTrue(self.profile.exists());self.assertTrue(self.key.exists())

    def test_runtime_requires_bound_config_before_any_file_cleanup(self):
        calls=[]
        class Client:
            def request(_,method,path,body=None):
                calls.append((method,path,body))
                if method=="GET":return {"project_root_path":str(self.project)}
                return {**self.receipt,"lease_token":"test-lease","revision":2,"cleanup_config_digest":None} if path.endswith("/claim") else {}
        self.runtime.client=Client()
        self.runtime.reconcile_deletions([{"member_id":self.member,"deletion":{"status":"pending","revision":1}}])
        self.assertEqual(calls[-1][2]["outcome"],"failed")
        self.assertEqual(calls[-1][2]["error_code"],"local_runtime_required")
        self.assertTrue(self.profile.exists());self.assertTrue(self.key.exists());self.assertTrue(self.record.exists())

    def test_live_cleanup_lease_is_not_claimed_again(self):
        from datetime import datetime,timezone,timedelta
        class Client:
            def request(*_args,**_kwargs):raise AssertionError("active lease must not be claimed")
        self.runtime.client=Client()
        self.runtime.reconcile_deletions([{"member_id":self.member,"deletion":{"status":"cleaning","revision":2,
            "lease_expires_at":(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()}}])

    def test_startup_config_publish_failure_preserves_original_bytes(self):
        self.config["workbuddy"]={"key_files":{self.member:str(self.key)},"models_home":"keep"}
        self.write_config();self.runtime.config=copy.deepcopy(self.config)
        original=self.path.read_bytes()
        with patch.object(host,"_windows_publish_temp_file",side_effect=OSError("isolated publish failure")):
            result=self.run_cleanup()
        self.assertEqual(result["outcome"],"failed");self.assertEqual(result["steps"]["startup_config"],"failed")
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(self.run_cleanup()["outcome"],"complete")
