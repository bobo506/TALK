from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import tempfile
import subprocess
import unittest
from unittest.mock import Mock, patch

from scripts import role_service_recovery as recovery
from scripts.role_service_host import HostError


class RoleServiceRecoveryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.health = Path(self.temp.name)/"manager-health.json"
        self.entry = Path(self.temp.name)/"host.py"
        self.entry.write_text("# fixture\n", encoding="utf-8")
        self.health.write_text(json.dumps(dict(project_id="p", member_id="agent:x", pid=1234,
            seen_at=(datetime.now(timezone.utc)-timedelta(seconds=120)).isoformat())), encoding="utf-8")
        self.target = dict(project_id="p", member_id="agent:x", expected_owner_host=socket.gethostname(),
            expected_generation=3, expected_process_launch_id="old-launch", expected_instance_id="old-instance",
            process_pid=4321, process_started_at="2026-10-11T00:00:00Z",
            instance_last_seen_at="2026-10-11T00:00:00Z", checked_at="2026-10-11T00:02:00Z")

    def proof(self, **kwargs):
        return recovery.local_proof(self.target, self.health, self.entry,
                                    probe=kwargs.get("probe", lambda _: "absent"),
                                    inventory=kwargs.get("inventory", lambda: []))

    def test_unknown_access_or_existing_process_never_means_absent(self):
        for state in ("unknown", "present"):
            with self.subTest(state=state), self.assertRaises(HostError):
                self.proof(probe=lambda _: state)
        kernel = Mock()
        kernel.OpenProcess.return_value = 0
        with patch.object(recovery.ctypes, "WinDLL", return_value=kernel), \
                patch.object(recovery.ctypes, "get_last_error", return_value=5):
            self.assertEqual(recovery.probe_pid(1234), "unknown")
        with patch.object(recovery.ctypes, "WinDLL", return_value=kernel), \
                patch.object(recovery.ctypes, "get_last_error", return_value=87):
            self.assertEqual(recovery.probe_pid(1234), "absent")

    def test_windows_confirmed_exited_object_is_stopped_but_not_absent(self):
        proof=self.proof(probe=lambda _: "exited")
        self.assertTrue(proof["both_stopped"])
        self.assertFalse(proof["both_absent"])
        for live_pid in (1234,4321):
            with self.subTest(live_pid=live_pid),self.assertRaises(HostError):
                self.proof(probe=lambda pid: "present" if pid==live_pid else "exited")

    @unittest.skipUnless(recovery.os.name=="nt","Windows command-line grammar")
    def test_windows_inventory_handles_json_and_escaped_quotes(self):
        args=['C:/Program Files/Python/python.exe','-c','print("a")',"value's",'{"message":"quoted \\\"text\\\""}']
        self.assertEqual(recovery.process_argv(subprocess.list2cmdline(args)),args)

    def test_replacement_host_bridge_or_unknown_inventory_blocks(self):
        for command in (f'python.exe "{self.entry}" --apply',
                        'python.exe -m bridges.cli_bridge --instance-id old-instance',
                        'python.exe -m scripts.role_service_host serve', None):
            with self.subTest(command=command), self.assertRaises(HostError):
                self.proof(inventory=lambda: [{"CommandLine": command}])

    def test_own_cli_arguments_do_not_look_like_another_manager(self):
        self.assertTrue(self.proof(inventory=lambda: [{"CommandLine":
            f'python.exe scripts/role_service_recovery.py apply --host-entry "{self.entry}"'}])["both_absent"])

    def test_wrong_identity_or_recent_manager_health_blocks(self):
        health = json.loads(self.health.read_text(encoding="utf-8"))
        for changes in ({"member_id": "other"}, {"seen_at": datetime.now(timezone.utc).isoformat()}):
            self.health.write_text(json.dumps({**health, **changes}), encoding="utf-8")
            with self.assertRaises(HostError): self.proof()

    def test_apply_rechecks_and_never_posts_changed_or_unconfirmed_plan(self):
        client = Mock()
        def respond(method, path, *args):
            if path == "/api/members/me": return {"kind": "human"}
            if method == "GET": return dict(self.target)
            return {"observed": "stopped"}
        client.request.side_effect = respond
        with patch.object(recovery, "probe_pid", return_value="absent"), \
                patch.object(recovery, "process_inventory", return_value=[]):
            plan = recovery.create_plan(client, "p", "agent:x", self.health, self.entry, "test-operation")
            with self.assertRaises(HostError): recovery.apply_plan(client, plan)
            self.entry.write_text("# changed\n", encoding="utf-8")
            with self.assertRaises(HostError): recovery.apply_plan(client, plan, confirm_stopped=True)
            self.assertFalse(any(call.args[0] == "POST" for call in client.request.call_args_list))
            self.entry.write_text("# fixture\n", encoding="utf-8")
            self.assertEqual(recovery.apply_plan(client, plan, confirm_stopped=True), {"observed": "stopped"})
            self.assertEqual(sum(call.args[0] == "POST" for call in client.request.call_args_list), 1)
