"""DSH 新角色的单项目/单成员受管宿主；复用 HostManager 全部所有权语义。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import uuid

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


def _ensure_model_patch(home, binding, secret):
    """只在缺失时原子创建模型 patch，保留已有的用户配置。"""
    alias = binding["model_alias"]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", alias):
        raise rsh.HostError("dsh_model_alias_invalid", "模型别名不能作为 patch 文件名")
    home = Path(home)
    rsh.ensure_private_dir(home)
    target = home / ("model-" + alias + ".patch.yml")
    if rsh._is_reparse_point(target):
        raise rsh.HostError("state_dir_insecure", "模型 patch 不能是链接")
    if target.exists():
        if not target.is_file():
            raise rsh.HostError("state_dir_insecure", "模型 patch 不是文件")
        return
    provider = binding["provider_id"]
    lines = ["- id: agent-default-model", "  config:",
             "    provider: " + json.dumps(provider, ensure_ascii=False),
             "    model: " + json.dumps(alias, ensure_ascii=False)]
    # 仅 DeepSeek 的插件 ID 有已确认的映射；其他 provider 不猜测插件 ID。
    if provider == "deepseek-official":
        effort = binding.get("effort_override") or binding.get("default_effort") or "max"
        if not isinstance(effort, str) or effort not in ("off", "low", "high", "max"):
            raise rsh.HostError("dsh_effort_invalid", "DSH 推理强度不可用")
        lines += ["- id: llm-deepseek", "  config:",
                  "    reasoningEffort: " + effort]
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    if secret and secret.encode("utf-8") in payload:
        raise rsh.HostError("dsh_model_patch_invalid", "模型 patch 不能包含连接秘密")
    temporary = home / (".model-patch-" + uuid.uuid4().hex + ".tmp")
    try:
        rsh._publish_private_bytes(temporary, payload)
        try:
            # 硬链接原子地创建目标且不替换已存在的文件，避免检查后并发覆盖。
            os.link(temporary, target)
        except FileExistsError:
            if rsh._is_reparse_point(target) or not target.is_file():
                raise rsh.HostError("state_dir_insecure", "模型 patch 不是普通文件") from None
    finally:
        temporary.unlink(missing_ok=True)


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
        context = kwargs.get("workspace_context")
        if context is not None and (not isinstance(context, dict) or context.get("runner") != "dsh"
                or context.get("project_id") != project or context.get("member_id") != member):
            raise rsh.HostError("workspace_context_invalid", "workspace identity or runner mismatch")
        super().__init__(*args, **kwargs)
        if self.workspace_context is not None:
            self.private = Path(self.workspace_context["state"]["manager"])

    def publish_health(self, state="serving"):
        if getattr(self, "workspace_context", None) is not None:
            self._workspace_check_file(self.private / "manager-health.json", self.private)
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
        if self.workspace_context is not None:
            self._workspace_check_file(self.private / "drain.request", self.private)
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

    def prepare_model_patch(self, model_alias):
        """????????????????????? patch?"""
        home = self.store.native_home_dir(self.project, self.member)
        if rsh.lock_path_for(home / "dsh-role-setup").exists():
            raise rsh.HostError("dsh_setup_in_progress", "?????????????")
        binding = self._current_binding(self.project, self.member, model_alias)
        try:
            entry = resolve_connection(self.runtime_config, binding)
            secret = next(iter(connection_environment(entry, os.environ).values()))
            if self.workspace_context is not None:
                self._workspace_check_file(home / ("model-" + model_alias + ".patch.yml"), home)
            _ensure_model_patch(home, binding, secret)
        except ConnectionSetupError as exc:
            raise rsh.HostError(exc.code, "DSH ??????????") from None

    def build_entry_argv(self, runtime, model_alias):
        if runtime != "dsh":
            raise rsh.HostError("dsh_runtime_only", "宿主仅服务当前 DSH 角色")
        home = self.store.native_home_dir(self.project, self.member)
        native_home = home.as_posix()
        if rsh.lock_path_for(home / "dsh-role-setup").exists():
            raise rsh.HostError("dsh_setup_in_progress", "请等待角色连接配置检查完成")
        binding = self._current_binding(self.project, self.member, model_alias)
        try:
            entry = resolve_connection(self.runtime_config, binding)
            secret_env = connection_environment(entry, os.environ)
            secret = next(iter(secret_env.values()))
            self._active_secret = secret
            self._active_binding_fingerprint = binding["binding_fingerprint"]
            if self.workspace_context is not None:
                self._workspace_check_file(home / ("model-" + model_alias + ".patch.yml"), home)
            _ensure_model_patch(home, binding, secret)
            validate_command(entry, binding, self.task_profile, which=shutil.which, secret=secret,
                native_home=native_home)
            template = connection_command(entry, binding, self.task_profile, native_home=native_home)
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
    parser.add_argument("--workspace-context", default=None)
    parser.add_argument("--key-root", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    context = None
    try:
        if args.workspace_context is not None or args.key_root is not None:
            if args.workspace_context is None or args.key_root is None:
                raise rsh.HostError("workspace_context_invalid", "workspace context and key root required")
            context = rsh.validate_workspace_context(json.loads(args.workspace_context),
                project=args.project, member=args.member, project_root=Path(args.project_root),
                key_root=Path(args.key_root), role_key_file=Path(args.role_key_file))
            if context["runner"] != "dsh":
                raise rsh.HostError("workspace_context_invalid", "workspace runner mismatch")
    except (rsh.HostError, ValueError) as exc:
        print(json.dumps({"ok": False, "error_code": getattr(exc, "code", "workspace_context_invalid")}))
        return 1
    private = Path(context["state"]["manager"]) if context is not None else manager_directory(args.state_dir, args.project, args.member)
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
        if context is not None:
            layouts = client.request("GET", "/api/projects/" + args.project + "/role-storage-layouts")
            layouts = layouts if isinstance(layouts, list) else layouts.get("data") if isinstance(layouts, dict) else None
            if not isinstance(layouts, list) or any(not isinstance(row, dict) for row in layouts):
                raise rsh.HostError("workspace_context_invalid", "workspace layout unavailable")
            matching = [row for row in layouts if row.get("member_id") == args.member]
            if len(matching) != 1 or matching[0].get("storage_layout") != "workspace-v1":
                raise rsh.HostError("workspace_context_invalid", "workspace layout mismatch")
        key_path = Path(args.role_key_file)
        if context is not None:
            rsh.validate_workspace_context(context, project=args.project, member=args.member,
                project_root=Path(args.project_root), key_root=Path(args.key_root), role_key_file=key_path)
        role_key = key_path.read_text(encoding="utf-8").strip()
        identity = client.request("GET", "/api/members/me", key=role_key)
        if identity.get("id") != args.member or identity.get("kind") != "agent":
            raise rsh.HostError("identity_mismatch", "角色Key与目标不匹配")
        from scripts import dsh_role_setup
        try:
            if context is None:
                prepared = dsh_role_setup.setup(
                    args.project, args.member, root=Path(args.project_root),
                    which=shutil.which, environ=os.environ)
            else:
                # The legacy setup writes under state/native; validate the same binding and
                # templates against the trusted home before creating its native subdirectory.
                from scripts.kimi_role_setup import _open_db
                db = _open_db(_database)
                try:
                    binding = dsh_role_setup._role(db, args.project, args.member)
                finally:
                    db.close()
                entry = resolve_connection(runtime_config, binding)
                profiles = runtime_config["dsh"].get("task_profiles", {})
                if not isinstance(profiles, dict) or any(not isinstance(k, str) or not k or v not in ("review", "tools") for k, v in profiles.items()):
                    raise rsh.HostError("dsh_task_profile_invalid", "DSH 任务 profile 无效：配置格式错误")
                secret = next(iter(connection_environment(entry, os.environ).values()))
                for profile in ("review", "tools"):
                    validate_command(entry, binding, profile, which=shutil.which, secret=secret,
                        native_home=Path(context["home"]).as_posix())
                del secret
                prepared = {"profile": profiles.get(args.member, "tools")}
                if prepared["profile"] != args.task_profile:
                    raise rsh.HostError("dsh_task_profile_invalid", "DSH 任务 profile 无效：与角色配置不一致")
                rsh.validate_workspace_context(context, project=args.project, member=args.member,
                    project_root=Path(args.project_root), key_root=Path(args.key_root), role_key_file=key_path)
                native = Path(context["home"]) / ".dsh"
                rsh._assert_root_chain_has_no_reparse(native)
                rsh.ensure_private_dir(native)
        except dsh_role_setup.SetupError as exc:
            print(json.dumps({"ok": False, "error_code": exc.code}))
            return 1
        if prepared.get("profile") != args.task_profile:
            raise rsh.HostError("dsh_task_profile_invalid", "任务 profile 与角色配置不一致")
        manager = DshRoleHost(client, project=args.project, member=args.member,
            display_name=role.get("role_name") or identity["display_name"], task_profile=args.task_profile,
            private=private, runtime_config=runtime_config, state_dir=Path(args.state_dir), operator_key=operator,
            role_key_file=key_path, project_root=Path(args.project_root), verified_runtimes=["dsh"],
            role_key_root=Path(args.key_root) if args.key_root else None, workspace_context=context,
            workspace_project=args.project, workspace_member=args.member)
        manager.prepare_model_patch(args.expected_model_alias)
        while True:
            try:
                manager.serve(args.project, poll_interval=rsh.DEFAULT_POLL_INTERVAL_SECONDS,
                    once=False, max_rounds=None, provision_worker=None)
                if manager.workspace_context is not None and manager._workspace_draining and not manager._handles:
                    manager.drain_requested = True
                    manager.publish_health_best_effort("stopped")
                    return 0
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
