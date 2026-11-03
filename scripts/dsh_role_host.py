"""DSH 新角色的单项目/单成员受管宿主；复用 HostManager 全部所有权语义。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import time

from scripts import role_service_host as rsh
from scripts.dsh_connections import (
    DIMENSIONS,
    ConnectionSetupError,
    connection_command,
    connection_environment,
    resolve_connection,
    validate_command,
)
from scripts.kimi_role_setup import _local_facts


class Drained(Exception):
    pass


def manager_directory(state_dir, project, member):
    return rsh.assert_inside_root(Path(state_dir), Path("dsh-dynamic") /
        rsh._sanitize_token(project) / rsh._sanitize_token(member))


def host_spec(config, role):
    """公开宿主配方；连接维度和本人 Key 在启动前再次核验。"""
    recipe = config.get("dsh")
    if not isinstance(recipe, dict) or recipe.get("enabled") is not True:
        return None
    if role.get("archived") or role.get("binding_state") != "bound":
        return None
    if ((role.get("runner") or {}).get("runtime") != "dsh"
            or not str((role.get("runner") or {}).get("runner_id") or "").startswith("runner:dsh-")
            or (role.get("service") or {}).get("control_kind") != "managed_cli"):
        return None
    if role.get("project_id", config["project_id"]) != config["project_id"]:
        return None
    member = role["member_id"]
    model = role.get("model") or {}
    choice, alias = model.get("choice_id"), model.get("model_alias")
    if not isinstance(choice, str) or not choice or not isinstance(alias, str) or not alias:
        return None
    profiles = recipe.get("task_profiles", {})
    profile = profiles.get(member, "tools")
    if profile not in ("review", "tools"):
        raise ValueError("dsh_task_profile_invalid")
    from scripts.role_provision import key_file_path
    key = key_file_path(Path(config["key_root"]), member)
    private = manager_directory(config["state_dir"], config["project_id"], member)
    argv = [sys.executable, "-B", "-X", "utf8", "-m", "scripts.dsh_role_host",
        "--project", config["project_id"], "--member", member,
        "--project-root", config["project_root"], "--state-dir", config["state_dir"],
        "--base-url", config["base_url"], "--operator-key-file", config["operator_key_file"],
        "--role-key-file", str(key), "--expected-choice-id", choice,
        "--expected-model-alias", alias, "--task-profile", profile, "--apply"]
    return {"member_id": member, "argv": argv,
        "health_file": str(private / "manager-health.json"),
        "drain_file": str(private / "drain.request")}


class DshRoleHost(rsh.HostManager):
    def __init__(self, *args, project, member, display_name, task_profile, private, runtime_config, **kwargs):
        self.project = project
        self.member = member
        self.display_name = display_name
        self.task_profile = task_profile
        self.private = Path(private)
        self.runtime_config = runtime_config
        self.drain_requested = False
        self._health_degraded = False
        self._active_connection = None
        self._active_secret = None
        self._active_binding_fingerprint = None
        super().__init__(*args, **kwargs)

    def publish_health(self, state="serving"):
        rsh.ensure_private_dir(self.private)
        value = {"schema": "talk-dsh-manager-health-1", "pid": os.getpid(),
            "project_id": self.project, "member_id": self.member,
            "seen_at": datetime.now(timezone.utc).isoformat(), "state": state,
            "draining": self.drain_requested, "owned_launches": list(self._handles)}
        rsh._publish_private_bytes(self.private / "manager-health.json",
            (json.dumps(value) + "\n").encode("utf-8"))

    def publish_health_best_effort(self, state="serving"):
        try:
            self.publish_health(state)
        except (rsh.HostError, OSError, ValueError):
            if not self._health_degraded:
                try:
                    print("dsh_host_health_unavailable", file=sys.stderr)
                except (OSError, ValueError):
                    pass
            self._health_degraded = True
        else:
            self._health_degraded = False

    def claimable_actions(self, project_id):
        if project_id != self.project:
            return []
        self.drain_requested = self.drain_requested or (self.private / "drain.request").is_file()
        if self.drain_requested and not self._handles:
            raise Drained()
        self.publish_health_best_effort()
        return [action for action in super().claimable_actions(project_id)
            if action.get("project_id") == self.project and action.get("member_id") == self.member
            and (not self.drain_requested or action.get("action") == "stop")]

    def _current_binding(self, project_id, member_id, alias):
        response = self.client.request("GET", "/api/projects/" + rsh.urllib.parse.quote(project_id, safe="") + "/agents")
        rows = response.get("data") if isinstance(response, dict) else response
        if not isinstance(rows, list):
            raise rsh.HostError("binding_fingerprint_mismatch", "无法核实角色模型绑定")
        matches = [item for item in rows if isinstance(item, dict) and item.get("member_id") == member_id]
        if len(matches) != 1 or matches[0].get("binding_state") != "bound":
            raise rsh.HostError("binding_fingerprint_mismatch", "角色模型绑定不可用")
        binding = matches[0].get("binding")
        if (not isinstance(binding, dict)
                or not str(binding.get("runner_id") or "").startswith("runner:dsh-")
                or binding.get("model_alias") != alias
                or binding.get("runtime") != "dsh"
                or not isinstance(binding.get("binding_fingerprint"), str)
                or not binding["binding_fingerprint"]
                or any(not isinstance(binding.get(field), str) or not binding[field] for field in DIMENSIONS)):
            raise rsh.HostError("binding_fingerprint_mismatch", "角色模型绑定不完整或已改变")
        return binding

    def build_entry_argv(self, runtime, model_alias):
        if runtime != "dsh":
            raise rsh.HostError("dsh_runtime_only", "宿主仅服务当前 DSH 角色")
        home = self.store.native_home_dir(self.project, self.member)
        if rsh.lock_path_for(home / "dsh-role-setup").exists():
            raise rsh.HostError("dsh_setup_in_progress", "请等待角色连接配置检查完成")
        binding = self._current_binding(self.project, self.member, model_alias)
        try:
            entry = resolve_connection(self.runtime_config, binding)
            secret_env = connection_environment(entry, os.environ)
            secret = secret_env[entry["target_api_key_env"]]
            self._active_secret = secret
            self._active_binding_fingerprint = binding["binding_fingerprint"]
            validate_command(entry, binding, self.task_profile, which=shutil.which, secret=secret)
            template = connection_command(entry, binding, self.task_profile)
        except ConnectionSetupError as exc:
            raise rsh.HostError(exc.code, "DSH 连接或模型映射不可用") from None
        self._active_connection = entry
        argv = rsh.build_runtime_argv("dsh", model_alias=model_alias,
            command_template=template, execution_timeout=self.execution_timeout_seconds)
        argv += ["--display-name", self.display_name, "--workdir", str(self.project_root.resolve())]
        return argv, "server_connection", "explicit" if self.execution_timeout_seconds else "builtin_default"

    def child_environment(self, project_id, member_id):
        if (project_id, member_id) != (self.project, self.member):
            raise rsh.HostError("identity_mismatch", "宿主作用域不匹配")
        env = super().child_environment(project_id, member_id)
        home = self.store.native_home_dir(project_id, member_id)
        if any(Path(env[name]).resolve() != home for name in rsh.NATIVE_HOME_ENV_VARS):
            raise rsh.HostError("dsh_isolation_override", "角色隔离环境不得覆盖")
        env["DSH_HOME"] = str(home / ".dsh")
        if self._active_connection is None:
            raise rsh.HostError("dsh_connection_required", "缺少显式 DSH 连接映射")
        expected = self._active_binding_fingerprint
        if not isinstance(expected, str) or not expected:
            raise rsh.HostError("binding_fingerprint_mismatch", "缺少宿主绑定的冻结指纹")
        env["TALK_DSH_EXPECTED_BINDING_FINGERPRINT"] = expected
        try:
            env.update(connection_environment(self._active_connection))
        except ConnectionSetupError as exc:
            raise rsh.HostError(exc.code, "DSH 连接秘密未配置") from None
        return env

    def _host_sensitive_values(self):
        values = list(super()._host_sensitive_values())
        secret = getattr(self, "_active_secret", None)
        if isinstance(secret, str) and secret and secret not in values:
            values.append(secret)
        return tuple(values)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("project", "member", "project-root", "state-dir", "base-url",
                 "operator-key-file", "role-key-file", "expected-choice-id", "expected-model-alias"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--task-profile", choices=("review", "tools"), default="tools")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    private = manager_directory(args.state_dir, args.project, args.member)
    if not args.apply:
        print(json.dumps({"mode": "dry_run", "project_id": args.project, "member_id": args.member}))
        return 0
    manager = None
    try:
        runtime_config, _database = _local_facts(Path(args.project_root), args.project, args.member)
        operator = rsh.load_operator_key(None, {
            rsh.OPERATOR_KEY_ENV: "", rsh.OPERATOR_KEY_FILE_ENV: args.operator_key_file})
        client = rsh.TalkHostClient(args.base_url, operator)
        if client.request("GET", "/api/members/me").get("kind") != "human":
            raise rsh.HostError("identity_mismatch", "宿主需要human正常认证")
        response = client.request("GET", "/api/projects/" + args.project + "/roles")
        roles = response if isinstance(response, list) else response.get("data")
        if not isinstance(roles, list) or any(not isinstance(row, dict) for row in roles):
            raise rsh.HostError("identity_mismatch", "角色投影不可用")
        role = next((r for r in roles if r.get("member_id") == args.member), None)
        if (not role or role.get("archived") or role.get("binding_state") != "bound"
                or (role.get("runner") or {}).get("runtime") != "dsh"
                or not str((role.get("runner") or {}).get("runner_id") or "").startswith("runner:dsh-")
                or (role.get("model") or {}).get("choice_id") != args.expected_choice_id
                or (role.get("model") or {}).get("model_alias") != args.expected_model_alias):
            raise rsh.HostError("binding_fingerprint_mismatch", "DSH角色或模型选择已改变")
        key_path = Path(args.role_key_file)
        role_key = key_path.read_text(encoding="utf-8").strip()
        identity = client.request("GET", "/api/members/me", key=role_key)
        if identity.get("id") != args.member or identity.get("kind") != "agent":
            raise rsh.HostError("identity_mismatch", "角色Key与目标不匹配")
        from scripts import dsh_role_setup
        try:
            prepared = dsh_role_setup.setup(
                args.project, args.member, root=Path(args.project_root),
                which=shutil.which, environ=os.environ)
        except dsh_role_setup.SetupError as exc:
            print(json.dumps({"ok": False, "error_code": exc.code}))
            return 1
        if prepared.get("profile") != args.task_profile:
            raise rsh.HostError("dsh_task_profile_invalid", "任务 profile 与角色配置不一致")
        manager = DshRoleHost(client, project=args.project, member=args.member,
            display_name=role.get("role_name") or identity["display_name"], task_profile=args.task_profile,
            private=private, runtime_config=runtime_config, state_dir=Path(args.state_dir), operator_key=operator,
            role_key_file=key_path, project_root=Path(args.project_root), verified_runtimes=["dsh"])
        while True:
            try:
                manager.serve(args.project, poll_interval=rsh.DEFAULT_POLL_INTERVAL_SECONDS,
                    once=False, max_rounds=None, provision_worker=None)
            except Drained:
                manager.publish_health_best_effort("stopped")
                return 0
            except (rsh.HostError, OSError, ValueError, ConnectionSetupError):
                if manager._handles:
                    time.sleep(rsh.DEFAULT_POLL_INTERVAL_SECONDS)
                    continue
                raise
            except KeyboardInterrupt:
                manager.drain_requested = True
                if not manager._handles:
                    manager.publish_health_best_effort("stopped")
                    return 0
                try:
                    manager.request_stop(args.project, args.member)
                except rsh.HostError:
                    pass
    except (rsh.HostError, OSError, ValueError, ConnectionSetupError) as exc:
        if manager is not None and manager._handles:
            raise
        print(json.dumps({"ok": False, "error_code": getattr(exc, "code", "dsh_host_config_invalid")}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
