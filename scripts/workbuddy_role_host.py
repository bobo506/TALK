"""WorkBuddy内置CLI单角色宿主。缺省dry-run，--apply后才消费普通启停动作。"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from scripts import role_service_host as rsh


class Drained(Exception):
    pass


class WorkBuddyRoleHost(rsh.HostManager):
    def __init__(self, client, *, project_id, member_id, executable, models_home, display_name, **kwargs):
        self.target_project, self.target_member = project_id, member_id
        self.executable, self.models_home = Path(executable).resolve(), Path(models_home).resolve()
        self.display_name = display_name
        self.drain_requested = False
        super().__init__(client, **kwargs)
        self.private = rsh.ensure_private_dir(rsh.assert_inside_root(self.store.state_dir,
            Path("workbuddy-native") / rsh._sanitize_token(project_id) / rsh._sanitize_token(member_id)))
        self.drain_file = self.private / "drain.request"
        self.started_at = datetime.now(timezone.utc).isoformat()

    def health(self, state="serving"):
        payload={"schema":"talk-workbuddy-manager-health-1", "project_id":self.target_project,
            "member_id":self.target_member, "pid":os.getpid(), "started_at":self.started_at,
            "seen_at":datetime.now(timezone.utc).isoformat(), "state":state,
            "draining":self.drain_requested or self.drain_file.is_file(), "owned_launches":list(self._handles),
            "note":"Diagnostic only; never adopt a Popen from this file."}
        rsh._publish_private_bytes(self.private/"manager-health.json",json.dumps(payload).encode())

    def claimable_actions(self, project_id):
        if project_id != self.target_project:
            return []
        draining=self.drain_requested or self.drain_file.is_file()
        self.health()
        if draining and not self._handles:
            raise Drained()
        return [row for row in super().claimable_actions(project_id)
            if row.get("project_id")==self.target_project and row.get("member_id")==self.target_member
            and (not draining or row.get("action")=="stop")]

    def build_entry_argv(self, runtime, model_alias):
        if runtime != "workbuddy" or not str(model_alias).startswith("custom-local:"):
            raise rsh.HostError("workbuddy_binding_unsupported")
        argv,template,budget=super().build_entry_argv(runtime,model_alias)
        argv += ["--workbuddy-executable",str(self.executable),"--workbuddy-models-home",str(self.models_home),
                 "--workdir",str(self.project_root),"--display-name",self.display_name]
        return argv,template,budget

    def child_environment(self, project_id, member_id):
        if (project_id,member_id)!=(self.target_project,self.target_member):
            raise rsh.HostError("workbuddy_scope_mismatch")
        return super().child_environment(project_id,member_id)


def build_parser():
    parser=rsh.build_arg_parser()
    parser.description="WorkBuddy embedded CLI single-role host (not desktop control)"
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--workbuddy-executable",required=True)
    parser.add_argument("--workbuddy-models-home",required=True)
    parser.add_argument("--workbuddy-display-name",default=None)
    return parser


def main(argv=None):
    args=build_parser().parse_args(argv)
    if args.mode!="serve" or not args.project or not args.member or args.members:
        raise rsh.HostError("workbuddy_single_role_required")
    if (args.cli_executable or args.cli_arg or args.cli_command_template or args.runtime_command_template
            or args.alias_flag or args.child_env or args.provision_worker or args.provision_worker_apply):
        raise rsh.HostError("workbuddy_entry_override_rejected")
    exe=Path(args.workbuddy_executable).resolve();models=Path(args.workbuddy_models_home).resolve()
    if not exe.is_file() or exe.name.lower()!="workbuddy.exe" or not (models/"models.json").is_file():
        raise rsh.HostError("workbuddy_source_missing")
    plan={"schema":"talk-workbuddy-host-plan-1","mode":"apply" if args.apply else "dry_run",
        "project_id":args.project,"member_id":args.member,"executable":str(exe),"models_home":str(models),
        "desktop_control":False,"default_execution_seconds":rsh.DEFAULT_CLI_EXECUTION_TIMEOUT_SECONDS}
    if not args.apply:
        print(json.dumps(plan,ensure_ascii=False));return 0
    if args.runtime_verified != ["workbuddy"] or not args.role_key_file or not args.operator_key_file or not args.workbuddy_display_name:
        raise rsh.HostError("workbuddy_verified_credentials_required")
    operator=rsh.load_operator_key(None,{rsh.OPERATOR_KEY_ENV:"",rsh.OPERATOR_KEY_FILE_ENV:args.operator_key_file})
    client=rsh.TalkHostClient(args.base_url,operator)
    manager=WorkBuddyRoleHost(client,project_id=args.project,member_id=args.member,executable=exe,models_home=models,display_name=args.workbuddy_display_name,
        host=args.host,state_dir=Path(args.state_dir),operator_key=operator,role_key_file=Path(args.role_key_file),
        verified_runtimes=["workbuddy"],project_root=Path(args.project_root),
        execution_timeout_seconds=rsh.normalize_execution_timeout(args.cli_execution_timeout_seconds),
        ready_timeout=args.ready_timeout,stop_timeout=args.stop_timeout)
    try:
        if client.request("GET","/api/members/me").get("kind")!="human":
            raise rsh.HostError("workbuddy_operator_not_human")
        while True:
            try:
                manager.serve(args.project,poll_interval=args.poll_interval,once=False,max_rounds=None,provision_worker=None)
            except Drained:
                manager.health("stopped");return 0
            except BaseException:
                manager.drain_requested=True
                for handle in list(manager._handles.values()):
                    try:client.request("POST",f"/api/projects/{args.project}/roles/{args.member}/service/stop")
                    except Exception:pass
                if manager._handles:
                    # Keep original ownership and let the product process stop path finish.
                    continue
                manager.health("stopped")
                raise
    finally:
        if hasattr(client,"close"):
            client.close()


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except rsh.HostError as exc:
        print(json.dumps({"ok":False,"error_code":exc.code}));raise SystemExit(1)
