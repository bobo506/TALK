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
    def test_pid_reuse_and_previous_boot_do_not_mean_the_old_process_is_alive(self):
        seen="2026-10-23T00:00:00Z"
        epoch=datetime(2026,10,23,tzinfo=timezone.utc).timestamp()
        self.assertEqual(recovery.recorded_process_state(1,seen,probe=lambda p:"present",boot_time=epoch+100),"previous_boot")
        self.assertEqual(recovery.recorded_process_state(1,seen,probe=lambda p:"present",created_at=epoch+100),"pid_reused")
        for status in ("present","unknown"):
            self.assertEqual(recovery.recorded_process_state(1,seen,probe=lambda p:status),status)
            self.assertEqual(recovery.recorded_process_state(1,seen,probe=lambda p:status,boot_time=epoch-100),status)

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

    @staticmethod
    def host_command(module, *, project="p", member="agent:x", serve=False, extra=()):
        parts = ["python", "-B", "-X", "utf8", "-m", module]
        if serve:
            parts.append("serve")
        parts += ["--project", project, "--member", member, *extra]
        return subprocess.list2cmdline(parts)

    def assert_replacement(self, command):
        with self.subTest(command=command), self.assertRaises(HostError) as raised:
            self.proof(inventory=lambda: [{"CommandLine": command}])
        self.assertEqual(raised.exception.code, "recovery_replacement_process_present")

    def assert_not_blocking(self, command):
        with self.subTest(command=command):
            self.assertTrue(self.proof(inventory=lambda: [{"CommandLine": command}])["both_absent"])

    def test_real_dynamic_module_launch_contract_blocks_replacement(self):
        # Real Kimi/Codex commands have no --instance; WorkBuddy really uses serve.
        for module, serve in (("scripts.kimi_role_host", False),
                              ("scripts.codex_role_host", False),
                              ("scripts.workbuddy_role_host", True)):
            self.assert_replacement(self.host_command(
                module, serve=serve,
                extra=("--project-root", r"C:\fixture\project",
                       "--state-dir", r"C:\fixture\state")))

    def test_quoted_windows_script_and_module_contracts_block(self):
        with tempfile.TemporaryDirectory(prefix="talk-host path ") as folder:
            entry = Path(folder) / "fixture host.py"
            entry.write_text("# fixture\n", encoding="utf-8")
            self.entry = entry
            self.assert_replacement(subprocess.list2cmdline(
                ["python", "-B", "-X", "utf8", str(entry), "--project", "p", "--member", "agent:x"]))
            self.assert_replacement(
                r'python -B -X utf8 "C:\Program Files\TALK\scripts\kimi_role_host.py" '
                r'--project p --member agent:x')
            self.assert_replacement(
                r'python -B -X utf8 scripts/codex_role_host.py --project=p --member=agent:x')
            self.assert_replacement(subprocess.list2cmdline(
                ["python", "-B", "-X", "utf8", f"..\\fixtures\\{entry.name}", "--apply"]))
            self.assert_replacement(subprocess.list2cmdline(
                ["python", "-B", "-X", "utf8",
                 r"C:\Program Files\TALK\scripts\workbuddy_role_host.py", "serve",
                 "--project", "p", "--member", "agent:x"]))

    def test_other_role_project_and_unrelated_module_do_not_block(self):
        for command in (
                self.host_command("scripts.kimi_role_host", project="other-project"),
                self.host_command("scripts.codex_role_host", member="agent:other"),
                self.host_command("scripts.workbuddy_role_host", serve=True,
                                  project="other-project", member="agent:other"),
                "python -m scripts.role_service_recovery apply --project p --member agent:x",
                "python -m bridges.cli_bridge --project p --member agent:x",
                "python -m pytest -q",
                subprocess.list2cmdline(["python", r"C:\deleted\unrelated.py", "--flag"]),
        ):
            self.assert_not_blocking(command)

    def test_unknown_or_incomplete_host_identity_is_refused(self):
        for command in (
                "python -m scripts.kimi_role_host",
                "python -m scripts.kimi_role_host --project p",
                "python -m scripts.kimi_role_host --member agent:x",
                "python -m scripts.kimi_role_host --project p --member",
                "python -m scripts.role_service_host serve",
                "python -m scripts.role_service_host --project p --project-id other --member agent:x",
                "python -m scripts.kimi_role_host --project p --member agent:other --member agent:x",
                r'python -B -X utf8 "C:\fixture\kimi_role_host.py" --apply',
        ):
            with self.subTest(command=command), self.assertRaises(HostError) as raised:
                self.proof(inventory=lambda: [{"CommandLine": command}])
            self.assertEqual(raised.exception.code, "recovery_process_inventory_unknown")

    def test_members_list_equals_forms_and_fixed_entry_boundaries(self):
        for command in (
                "python -m scripts.role_service_host serve --project=p "
                "--members=agent:other,agent:x",
                "python -m scripts.kimi_role_host --project p --member=agent:x",
                subprocess.list2cmdline(["python.exe", str(self.entry), "--project", "p",
                                         "--member", "agent:x"]),
                # A configured fixed entry is pinned to this member; its exact
                # script match stays blocking even if generic args look foreign.
                subprocess.list2cmdline(["python.exe", str(self.entry), "--project", "other",
                                         "--member", "agent:other"]),
        ):
            self.assert_replacement(command)
        self.assert_not_blocking(
            "python -m scripts.role_service_host serve --project=p --members=agent:other")

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
