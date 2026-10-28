#!/usr/bin/env python3
"""由本机用户交互式准备单个受管 Kimi 角色，不复制登录凭据。"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib

from scripts import role_service_host as host
from scripts.role_provision import acquire_lock, release_lock, lock_path_for

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"[A-Za-z0-9:._-]{1,128}\Z")
MODEL_ALIAS = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
MODEL_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
PUBLIC_MODEL_FIELDS = {"provider", "model", "max_context_size", "max_output_size", "capabilities", "support_efforts", "display_name", "default_effort"}


class SetupError(Exception):
    pass


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SetupError("本机运行配置格式不正确。")
    return data


def _local_facts(root: Path, project: str, member: str):
    if not isinstance(project, str) or not isinstance(member, str) or not IDENTIFIER.fullmatch(project) or not IDENTIFIER.fullmatch(member):
        raise SetupError("项目或角色标识不合法。")
    pointer = _read_json(root / ".talk" / "runtime.local.json")
    if pointer.get("schema") != "talk-local-runtime-1":
        raise SetupError("找不到本机项目运行配置。")
    if not all(isinstance(pointer.get(k), str) and pointer[k] for k in ("config_file", "database_file")):
        raise SetupError("本机运行配置或数据库不可用。")
    config_path = Path(pointer["config_file"])
    database = Path(pointer["database_file"])
    if not config_path.is_absolute() or not database.is_absolute() or not database.is_file():
        raise SetupError("本机运行配置或数据库不可用。")
    config = _read_json(config_path)
    if (config.get("schema") != "talk-runtime-config-1" or config.get("project_id") != project
            or not isinstance(config.get("project_root"), str) or not isinstance(config.get("state_dir"), str)
            or not Path(config["project_root"]).is_absolute()
            or Path(config["project_root"]).resolve() != root.resolve()
            or not Path(config.get("state_dir", "")).is_absolute()):
        raise SetupError("本机运行配置与该项目不匹配。")
    return config, database


def _role(db: sqlite3.Connection, project: str, member: str) -> tuple[str, str, str]:
    row = db.execute("""
        SELECT b.model_alias, b.model_id, b.provider_id, b.model_source, b.connection_ref, s.desired_state,
               s.observed_state, s.owner_host, s.process_launch_id
        FROM project_roles p
        JOIN project_role_bindings b ON b.project_id=p.project_id AND b.member_id=p.member_id
        JOIN runner_registry r ON r.runner_id=b.runner_id
        LEFT JOIN role_service_state s ON s.project_id=p.project_id AND s.member_id=p.member_id
        WHERE p.project_id=? AND p.member_id=? AND p.archived_at IS NULL
          AND r.runtime='kimi-code' AND r.control_kind='managed_cli'
    """, (project, member)).fetchone()
    if not row:
        raise SetupError("角色不存在、已归档，或不是受管 Kimi 角色。")
    alias, model, provider, source, connection, desired, observed, owner, launch = row
    if (not isinstance(alias, str) or not MODEL_ALIAS.fullmatch(alias)
            or not isinstance(model, str) or not MODEL_ID.fullmatch(model)
            or provider != "managed:kimi-code" or source != "builtin"
            or connection != "native-kimi-code-managed-login"):
        raise SetupError("当前只支持 Kimi Code 官方登录和有效的模型选择。")
    safely_failed = observed == "failed" and not owner and not launch
    if ((desired not in (None, "stopped") and not safely_failed)
            or observed not in (None, "not_started", "stopped", "failed") or owner or launch):
        raise SetupError("请先关闭该角色，等待服务完全停止后再配置。")
    return alias, model, provider


def _open_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)
    db.execute("PRAGMA busy_timeout=5000")
    return db


def _validated_model(entry, binding: tuple[str, str, str]) -> dict:
    alias, model, provider = binding
    if not isinstance(entry, dict) or entry.get("model") != model or entry.get("provider") != provider:
        raise SetupError("本机 Kimi 用户配置与角色所选模型不一致，请先核对模型。")
    if set(entry) - PUBLIC_MODEL_FIELDS:
        raise SetupError("模型含不支持自动准备的配置项，请人工核对。")
    public = {"provider": provider, "model": model}
    for key in ("max_context_size", "max_output_size"):
        value = entry.get(key)
        if value is not None:
            if type(value) is not int or value <= 0:
                raise SetupError("本机模型容量配置不合法。")
            public[key] = value
    for key in ("capabilities", "support_efforts"):
        value = entry.get(key)
        if value is not None:
            if not isinstance(value, list) or len(value) > 64 or any(not isinstance(v, str) or len(v) > 100 for v in value):
                raise SetupError("本机模型能力配置不合法。")
            public[key] = value
    for key in ("display_name", "default_effort"):
        value = entry.get(key)
        if value is not None:
            if not isinstance(value, str) or len(value) > 200:
                raise SetupError("本机模型描述配置不合法。")
            public[key] = value
    return public


def _public_model(path: Path, binding: tuple[str, str, str]) -> dict:
    if not path.is_file() or host._is_reparse_point(path):
        raise SetupError("本机 Kimi 用户配置没有找到所选模型，请先在 Kimi Code 中配置该模型。")
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    models = data.get("models")
    if not isinstance(models, dict):
        raise SetupError("本机 Kimi 模型配置格式无效。")
    return _validated_model(models.get(binding[0]), binding)


def _source_if_present(path: Path, binding: tuple[str, str, str]):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    if not path.is_file() or host._is_reparse_point(path) or info.st_size > 2 * 1024 * 1024:
        raise SetupError("本机 Kimi 用户配置不可用。")
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    models = data.get("models", {})
    if not isinstance(models, dict):
        raise SetupError("本机 Kimi 模型配置格式无效。")
    if binding[0] not in models:
        return None
    return _validated_model(models[binding[0]], binding)


def _existing_alias(config_path: Path, alias: str) -> bool:
    try:
        config_path.stat()
    except FileNotFoundError:
        return False
    if not config_path.is_file() or host._is_reparse_point(config_path) or config_path.stat().st_size > 2 * 1024 * 1024:
        raise SetupError("角色 Kimi 配置不可用。")
    with config_path.open("rb") as stream:
        parsed = tomllib.load(stream)
    models = parsed.get("models", {})
    if not isinstance(models, dict):
        raise SetupError("角色 Kimi 模型配置格式无效。")
    return alias in models


def _append_model(config_path: Path, binding: tuple[str, str, str], model, *, allow_login_generated=False) -> str:
    alias, _, provider = binding
    if not config_path.is_file() or host._is_reparse_point(config_path):
        raise SetupError("Kimi 登录未生成可用配置，请检查登录结果。")
    raw = config_path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise SetupError("角色 Kimi 配置过大。")
    parsed = tomllib.loads(raw.decode("utf-8"))
    providers = parsed.get("providers")
    models = parsed.get("models", {})
    if not isinstance(providers, dict) or not isinstance(providers.get(provider), dict) or not isinstance(models, dict):
        raise SetupError("Kimi 官方登录尚未配置完成。")
    existing = models.get(alias)
    if callable(model):
        model = model()
    if existing is not None:
        try:
            actual = _validated_model(existing, binding)
        except SetupError:
            raise SetupError("角色中已存在不同的同名模型，未覆盖。") from None
        if model is not None and actual != model:
            raise SetupError("角色同名模型的上下文或能力配置不一致，未覆盖。")
        if model is None and not allow_login_generated:
            raise SetupError("无法核对已有模型配置，请先在本机 Kimi Code 配置所选模型。")
        return "existing"
    if model is None:
        raise SetupError("登录未提供所选模型，请先在本机 Kimi Code 配置该模型。")
    lines = [f'\n[models.{json.dumps(alias, ensure_ascii=False)}]']
    for key, value in model.items():
        lines.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")
    updated = raw + ("\n".join(lines) + "\n").encode("utf-8")
    tomllib.loads(updated.decode("utf-8"))
    temp = None
    try:
        if os.name == "nt":
            temp = host._windows_publish_temp_file(config_path, updated)
        else:
            with tempfile.NamedTemporaryFile(dir=config_path.parent, prefix=".kimi-model-", delete=False) as stream:
                temp = Path(stream.name)
                os.chmod(temp, 0o600)
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
        if config_path.read_bytes() != raw:
            raise SetupError("角色配置在操作期间发生变化，未覆盖；请重试。")
        os.replace(temp, config_path)
        temp = None
    finally:
        if temp is not None:
            with contextlib.suppress(OSError):
                temp.unlink(missing_ok=True)
    return "added"


def setup(project: str, member: str, *, root: Path = ROOT, run=subprocess.run) -> None:
    config, database = _local_facts(root, project, member)
    executable = shutil.which("kimi")
    if not executable:
        raise SetupError("本机找不到 Kimi Code CLI。")
    db = _open_db(database)
    lock = None
    lock_path = None
    try:
        db.execute("BEGIN IMMEDIATE")
        binding = _role(db, project, member)
        # 如角色登录后仍缺模型，才读取用户配置中的所选公开模型描述。
        original_home = os.environ.get("KIMI_CODE_HOME")
        source = (Path(original_home).expanduser() if original_home else Path.home() / ".kimi-code") / "config.toml"
        state_dir = Path(config["state_dir"])
        relative = Path("native") / host._sanitize_token(project) / host._sanitize_token(member)
        home = host.ensure_private_dir(host.assert_inside_root(state_dir, relative))
        kimi_home = host.ensure_private_dir(host.assert_inside_root(home, Path(".kimi-code")))
        lock_path = lock_path_for(home / "kimi-role-setup")
        lock = acquire_lock(lock_path)
        was_present = _existing_alias(kimi_home / "config.toml", binding[0])
        db.rollback()

        print("请在本机完成 Kimi Code 设备登录。角色使用独立登录，不会复制其他角色的认证。", flush=True)
        env = {name: value for name in host.CHILD_ENV_ALLOWLIST if (value := os.environ.get(name))}
        env.update({name: str(home) for name in host.NATIVE_HOME_ENV_VARS})
        env["KIMI_CODE_HOME"] = str(kimi_home)
        result = run([executable, "login"], cwd=str(root), env=env, check=False)
        if result.returncode != 0:
            raise SetupError("Kimi 登录未完成；请按提示重试。")
        db.execute("BEGIN IMMEDIATE")
        if _role(db, project, member) != binding:
            raise SetupError("角色模型在登录期间发生变化，未写入模型；请重试。")
        outcome = _append_model(kimi_home / "config.toml", binding, lambda: _source_if_present(source, binding), allow_login_generated=not was_present)
        db.rollback()
        print("登录命令已完成，所选模型配置已" + ("存在" if outcome == "existing" else "准备") + "。请返回 TALK 启动角色；开发工具由宿主配置管理。")
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()
        if lock is not None:
            release_lock(lock_path, lock)


class NativeLoginAttempt:
    """一次页面授权持有的本机事实；对象不进入 API、日志或数据库。"""
    def __init__(self, *, project, member, root, config, database, binding, source, executable, home,
                 kimi_home, was_present, lock_path, lock, process, process_generation=None):
        self.project = project
        self.member = member
        self.root = root
        self.config = config
        self.database = database
        self.binding = binding
        self.source = source
        self.executable = executable
        self.home = home
        self.kimi_home = kimi_home
        self.was_present = was_present
        self.lock_path = lock_path
        self.lock = lock
        self.process = process
        self.process_generation = process_generation
        self.released = False


def begin_native_login(project: str, member: str, *, root: Path = ROOT, popen=subprocess.Popen) -> NativeLoginAttempt:
    """在角色专属 HOME 启动官方登录；只返回内存句柄，不读取或复制凭据。"""
    config, database = _local_facts(root, project, member)
    executable = shutil.which("kimi")
    if not executable:
        raise SetupError("本机找不到 Kimi Code CLI。")
    db = _open_db(database)
    lock = None
    lock_path = None
    transition = None
    transition_path = None
    try:
        db.execute("BEGIN IMMEDIATE")
        binding = _role(db, project, member)
        original_home = os.environ.get("KIMI_CODE_HOME")
        source = (Path(original_home).expanduser() if original_home else Path.home() / ".kimi-code") / "config.toml"
        state_dir = Path(config["state_dir"])
        relative = Path("native") / host._sanitize_token(project) / host._sanitize_token(member)
        home = host.ensure_private_dir(host.assert_inside_root(state_dir, relative))
        kimi_home = host.ensure_private_dir(host.assert_inside_root(home, Path(".kimi-code")))
        transition_path = lock_path_for(home / 'native-setup-transition')
        transition = acquire_lock(transition_path)
        from scripts import native_setup_process
        native_setup_process.stop_previous(home, project, member)
        lock_path = lock_path_for(home / "kimi-role-setup")
        lock = acquire_lock(lock_path)
        was_present = _existing_alias(kimi_home / "config.toml", binding[0])
        db.rollback()
        env = {name: value for name in host.CHILD_ENV_ALLOWLIST if (value := os.environ.get(name))}
        env.update({name: str(home) for name in host.NATIVE_HOME_ENV_VARS})
        env["KIMI_CODE_HOME"] = str(kimi_home)
        options = {}
        if os.name == "nt":
            options.update({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                            "startupinfo": host._hidden_startupinfo()})
        else:
            options["start_new_session"] = True
        base_flags=options.pop('creationflags',0)
        process, process_generation = native_setup_process.spawn_recorded(home, project, member, lock,
            lambda extra_flags: popen([executable, "login"], cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1, **({'creationflags':base_flags|extra_flags} if os.name=='nt' else {}), **options))
        return NativeLoginAttempt(project=project, member=member, root=root, config=config,
            database=database, binding=binding, source=source, executable=executable,
            home=home, kimi_home=kimi_home, was_present=was_present,
            lock_path=lock_path, lock=lock, process=process, process_generation=process_generation)
    except Exception:
        if lock is not None:
            release_lock(lock_path, lock)
        raise
    finally:
        if transition is not None:
            release_lock(transition_path, transition)
        if db.in_transaction:
            db.rollback()
        db.close()


def finish_native_login(attempt: NativeLoginAttempt) -> str:
    """官方进程成功退出后，复核绑定并只准备所选模型的公开字段。"""
    db = _open_db(attempt.database)
    try:
        db.execute("BEGIN IMMEDIATE")
        binding = _role(db, attempt.project, attempt.member)
        if binding != attempt.binding:
            raise SetupError("角色模型在登录期间发生变化，未写入模型；请重试。")
        outcome = _append_model(attempt.kimi_home / "config.toml", binding,
            lambda: _source_if_present(attempt.source, binding), allow_login_generated=not attempt.was_present)
        db.rollback()
        return outcome
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()
        release_native_login(attempt)


def release_native_login(attempt: NativeLoginAttempt) -> None:
    if not attempt.released:
        if attempt.process_generation is not None:
            from scripts.native_setup_process import finish_record
            finish_record(attempt.home, attempt.project, attempt.member, attempt.process_generation, attempt.process)
        release_lock(attempt.lock_path, attempt.lock)
        attempt.released = True


def cancel_native_login(attempt: NativeLoginAttempt) -> None:
    """只取消本次官方登录的专属进程组，不触碰角色服务或其它进程。"""
    try:
        if attempt.process.poll() is None:
            attempt.process.terminate()
            try:
                attempt.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                attempt.process.kill()
                attempt.process.wait(timeout=5)
    finally:
        if attempt.process.poll() is not None:
            release_native_login(attempt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--member", required=True)
    args = parser.parse_args(argv)
    try:
        setup(args.project, args.member)
    except (SetupError, OSError, ValueError, TypeError, AttributeError, sqlite3.Error, host.HostError) as exc:
        print(str(exc) if isinstance(exc, SetupError) else "角色配置未完成，请检查本机环境后重试。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
