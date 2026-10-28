from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import native_setup_process as process_store


class NativeSetupProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.project, self.member = 'synthetic-project', 'agent:synthetic-member'

    def child(self, extra_flags=0):
        options = {'creationflags':subprocess.CREATE_NO_WINDOW|extra_flags} if sys.platform == 'win32' else {}
        child = subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)'],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**options)
        def close():
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
        self.addCleanup(close)
        return child

    def spawn(self):
        result=process_store.spawn_recorded(self.home,self.project,self.member,{'token':'synthetic-lock'},self.child)
        if hasattr(result[0],'job'):self.addCleanup(result[0].job.close)
        return result

    def test_codex_retry_stops_previous_authorization_and_releases_only_recorded_lock(self):
        from scripts.role_provision import acquire_lock, lock_path_for
        lock_path=lock_path_for(self.home/'codex-role-setup')
        lock=acquire_lock(lock_path)
        owned,generation=process_store.spawn_recorded(self.home,self.project,self.member,lock,self.child,
            lock_name='codex-role-setup')
        if hasattr(owned,'job'):self.addCleanup(owned.job.close)
        self.assertIsNone(owned.poll())
        self.assertTrue(lock_path.exists())
        process_store.stop_previous(self.home,self.project,self.member)
        self.assertIsNotNone(owned.poll())
        self.assertFalse(lock_path.exists())

    def test_recreated_controller_stops_original_before_creating_replacement(self):
        old, _ = self.spawn()
        self.assertIsNone(old.poll())
        process_store.stop_previous(self.home,self.project,self.member)
        self.assertIsNotNone(old.poll())
        replacement, generation = self.spawn()
        self.assertIsNone(replacement.poll())
        self.assertNotEqual(old.pid,replacement.pid)
        process_store.stop_previous(self.home,self.project,self.member)
        self.assertIsNotNone(replacement.poll())
        process_store.finish_record(self.home,self.project,self.member,generation,replacement)
        self.assertFalse(process_store._path(self.home).exists())

    def test_creation_time_mismatch_does_not_stop_live_process(self):
        child, _ = self.spawn()
        record = process_store._read(self.home,self.project,self.member)
        record['created_at'] -= 10
        process_store._write(self.home,record)
        with self.assertRaisesRegex(process_store.ProcessError,'identity_changed'):
            process_store.stop_previous(self.home,self.project,self.member)
        self.assertIsNone(child.poll())
        self.assertTrue(process_store._path(self.home).exists())

    def test_unknown_launch_receipt_blocks_replacement(self):
        record={'schema':'talk-native-setup-process-1','project_id':self.project,'member_id':self.member,
            'generation':'synthetic-generation','state':'launching','pid':None,'created_at':None}
        process_store._write(self.home,record)
        with self.assertRaisesRegex(process_store.ProcessError,'unverified'):
            process_store.stop_previous(self.home,self.project,self.member)

    def test_unconfirmed_stop_keeps_receipt(self):
        child,_=self.spawn()
        with patch.object(child,'terminate',side_effect=process_store.ProcessError('native_previous_process_stop_unconfirmed')):
            with self.assertRaisesRegex(process_store.ProcessError,'stop_unconfirmed'):
                process_store.stop_previous(self.home,self.project,self.member)
        self.assertTrue(process_store._path(self.home).exists())

    @unittest.skipUnless(sys.platform=='win32','Windows授权进程Job')
    def test_authorization_launcher_child_stops_before_replacement(self):
        import json
        from scripts.role_service_recovery import probe_pid
        marker=self.home/'synthetic-child.json'
        script=self.home/'synthetic-launcher.py'
        script.write_text('import subprocess,sys,time,json\nfrom pathlib import Path\n'
            'p=subprocess.Popen([sys.executable,"-B","-c","import time; time.sleep(60)"],creationflags=subprocess.CREATE_NO_WINDOW)\n'
            f'Path({str(marker)!r}).write_text(json.dumps({{"pid":p.pid}}))\n'
            'time.sleep(60)\n',encoding='utf-8')
        def spawn(flags):
            raw=subprocess.Popen([sys.executable,'-B',str(script)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW|flags)
            self.addCleanup(lambda: raw.wait(timeout=5))
            return raw
        process,_=process_store.spawn_recorded(self.home,self.project,self.member,{},spawn)
        self.addCleanup(process.job.close)
        deadline=time.monotonic()+5
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(marker.exists())
        child=json.loads(marker.read_text())['pid']
        self.assertEqual(probe_pid(child),'present')
        process_store.stop_previous(self.home,self.project,self.member)
        self.assertIsNotNone(process.poll())
        self.assertIn(probe_pid(child),('absent','exited'))

    def test_old_finalizer_cannot_delete_new_generation_receipt(self):
        child, old_generation = self.spawn()
        child.terminate();child.wait(timeout=5)
        record=process_store._read(self.home,self.project,self.member)
        record['generation']='0'*32
        process_store._write(self.home,record)
        process_store.finish_record(self.home,self.project,self.member,old_generation,child)
        self.assertEqual(process_store._read(self.home,self.project,self.member)['generation'],'0'*32)

    def test_failed_spawn_is_recoverable_without_unknown_child(self):
        with self.assertRaises(OSError):
            process_store.spawn_recorded(self.home,self.project,self.member,{},lambda flags: (_ for _ in ()).throw(OSError('synthetic')))
        process_store.stop_previous(self.home,self.project,self.member)
        self.assertFalse(process_store._path(self.home).exists())

    @unittest.skipUnless(sys.platform=='win32','Windows授权进程Job')
    def test_failed_job_creation_never_launches_child_and_can_retry(self):
        with patch.object(process_store,'_WindowsAuthorizationJob',side_effect=process_store.ProcessError('native_process_scope_unavailable')):
            with patch.object(self,'child') as spawn:
                with self.assertRaises(process_store.ProcessError):
                    self.spawn()
                spawn.assert_not_called()
        process_store.stop_previous(self.home,self.project,self.member)
        self.assertFalse(process_store._path(self.home).exists())

    @unittest.skipUnless(sys.platform=='win32','Windows授权进程Job')
    def test_controller_exit_closes_only_its_authorization_scope(self):
        import json
        from scripts.role_service_recovery import probe_pid
        controller=self.home/'controller.py'
        marker=self.home/'controller-receipt.json'
        root=Path(process_store.__file__).resolve().parents[1]
        controller.write_text('import os,subprocess,sys,json\nfrom pathlib import Path\n'
            f'sys.path.insert(0,{str(root)!r})\n'
            'from scripts import native_setup_process as store\n'
            f'home=Path({str(self.home)!r})\n'
            'p,g=store.spawn_recorded(home,"synthetic-project","agent:synthetic-member",{},lambda flags: subprocess.Popen([sys.executable,"-B","-c","import time; time.sleep(60)"],creationflags=subprocess.CREATE_NO_WINDOW|flags))\n'
            f'Path({str(marker)!r}).write_text(json.dumps({{"pid":p.pid}}))\n'
            'os._exit(0)\n',encoding='utf-8')
        result=subprocess.run([sys.executable,'-B',str(controller)],capture_output=True,timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        child=json.loads(marker.read_text())['pid']
        process_store.stop_previous(self.home,self.project,self.member)
        self.assertIn(probe_pid(child),('absent','exited'))
        self.assertFalse(process_store._path(self.home).exists())
