"""Initialize a portable instance without starting any services."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tomllib
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scripts import portable_paths as paths

# Fresh portable databases have no runner registry.  Seed only the CLI runners
# supported by this distribution (WorkBuddy ACP is closed); these rows describe
# registration facts, not installed/logged-in state.
RUNNER_SEEDS = (
    ("runner:codex-local", "codex", "Codex CLI"),
    ("runner:kimi-code-1aabe894a3c21096ad9c7f5211aa7e33", "kimi-code", "Kimi Code · K2.8 Preview 执行"),
    ("runner:dsh-deepseek-local", "dsh", "DeepSeek Harness CLI"),
)
MODEL_SEEDS = (
    ("runner:codex-local", "gpt-6.1-terra", "gpt-6.1-terra", "GPT-6.1 Terra", "openai", "native-codex-chatgpt-login"),
    ("runner:codex-local", "gpt-6-astra", "gpt-6-astra", "GPT-6 Astra", "openai", "native-codex-chatgpt-login"),
    ("runner:codex-local", "gpt-6.1-sol", "gpt-6.1-sol", "gpt-6.1-sol · xhigh", "openai", "native-codex-chatgpt-login"),
    ("runner:kimi-code-1aabe894a3c21096ad9c7f5211aa7e33", "kimi-for-coding", "kimi-code/kimi-for-coding", "K2.8 Preview", "managed:kimi-code", "native-kimi-code-managed-login"),
    ("runner:kimi-code-1aabe894a3c21096ad9c7f5211aa7e33", "k3", "kimi-code/k3", "K3", "managed:kimi-code", "native-kimi-code-managed-login"),
    ("runner:kimi-code-1aabe894a3c21096ad9c7f5211aa7e33", "k3.1-pro", "kimi-code/k3.1-pro", "K3.1 Pro", "managed:kimi-code", "native-kimi-code-managed-login"),
    ("runner:dsh-deepseek-local", "deepseek-flash", "deepseek-flash", "DeepSeek Flash · max", "deepseek-official", "native-dsh-user-env"),
)


def seed_runners(session, admin):
    """Insert canonical CLI runners/models once; preserve existing rows."""
    import hashlib
    from sqlmodel import select
    from server.models import RunnerRegistry, RunnerModelChoice

    created = {"runners": 0, "models": 0}
    for runner_id, runtime, display_name in RUNNER_SEEDS:
        if session.get(RunnerRegistry, runner_id) is None:
            session.add(RunnerRegistry(runner_id=runner_id, runtime=runtime, display_name=display_name,
                                       adapter_status="unverified", adapter_note=None, capabilities=[],
                                       control_kind="managed_cli", created_by=admin.id))
            created["runners"] += 1
    session.commit()
    for runner_id, model_id, alias, display, provider, connection in MODEL_SEEDS:
        if session.exec(select(RunnerModelChoice).where(
                RunnerModelChoice.runner_id == runner_id,
                RunnerModelChoice.model_id == model_id,
                RunnerModelChoice.model_source == "builtin",
                RunnerModelChoice.provider_id == provider,
                RunnerModelChoice.connection_ref == connection,
                RunnerModelChoice.model_alias == alias)).first() is not None:
            continue
        digest = hashlib.sha256(f"{runner_id}|{model_id}|{alias}|{provider}|{connection}".encode()).hexdigest()[:12]
        session.add(RunnerModelChoice(choice_id=f"rmc_{digest}", runner_id=runner_id, model_id=model_id,
                                      model_source="builtin", provider_id=provider, connection_ref=connection,
                                      model_alias=alias, model_display_name=display,
                                      source_kind="declared", capabilities=[], created_by=admin.id))
        created["models"] += 1
    session.commit()
    return created



def write_new(path, content):
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        return True
    except FileExistsError:
        return False


def bootstrap(root, port, project_name, apply):
    os.environ["TALK_HOME"] = str(root)
    os.environ["TALK_CONFIG"] = str(root / "config" / "config.toml")
    cfg = paths.config_path()
    keys = paths.keys_dir()
    db_path = paths.data_dir() / "talk.db"
    result = {"mode": "apply" if apply else "dry_run", "root": str(root), "config": str(cfg),
              "db": str(db_path), "keys": str(keys), "project": "pending", "admin": "pending"}
    if not apply:
        return result
    paths.ensure_portable_dirs()
    q = lambda value: json.dumps(str(value), ensure_ascii=False)
    config = (f'[server]\nhost = "127.0.0.1"\nport = {port}\npublic_url = "http://127.0.0.1:{port}"\n'
              'auth_mode = "trusted"\ntrusted_networks = ["loopback"]\n\n[storage]\n'
              f'db_path = {q(db_path)}\nstorage_dir = {q(paths.storage_dir())}\nupload_max_mb = 100\n'
              f'\n[logging]\npath = {q(paths.logs_dir() / "talk.log")}\n\n[backup]\ndir = {q(paths.backups_dir())}\n')
    result["config_status"] = "created" if write_new(cfg, config) else "existing"
    with cfg.open("rb") as stream:
        existing = tomllib.load(stream)
    actual_db = Path(existing["storage"]["db_path"])
    if not actual_db.is_absolute():
        actual_db = root / actual_db
    actual_db = actual_db.resolve()
    if not actual_db.is_relative_to(paths.data_dir().resolve()):
        raise RuntimeError("existing config DB must be inside the portable data directory")
    result["db"] = str(actual_db)
    port = int(existing["server"]["port"])
    if not 1 <= port <= 65535:
        raise ValueError("invalid configured port")
    base_url = f"http://127.0.0.1:{port}"
    # Relative paths in an existing config follow the portable root.
    os.chdir(root)
    from sqlmodel import Session, select
    from server.db import engine, init_db
    from server.models import Member, Project
    from scripts.create_admin import create_admin_member

    init_db()
    key_file = keys / "operator.key"
    with Session(engine) as session:
        admin = session.exec(select(Member).where(Member.kind == "human")).first()
        if admin is None:
            if not key_file.exists():
                write_new(key_file, secrets.token_urlsafe(32) + "\n")
            key = key_file.read_text(encoding="utf-8").strip()
            if not key:
                raise RuntimeError("operator key file is empty")
            admin = create_admin_member(session, member_id="human:operator", display_name="Operator", api_key=key)
            result["admin"] = "created"
        else:
            result["admin"] = "existing"
        # A runtime without the matching human key cannot be started safely.
        if not key_file.is_file():
            raise RuntimeError("existing human administrator has no operator key file; preserve it and configure the matching key")
        key = key_file.read_text(encoding="utf-8").strip()
        key_owner = session.exec(select(Member).where(Member.api_key == key, Member.kind == "human")).first()
        if not key_owner:
            raise RuntimeError("operator key file does not match an existing human administrator")
        project = session.exec(select(Project)).first()
        if project is None:
            if (paths.project_dir() / ".talk").exists():
                raise RuntimeError("existing project .talk cannot be associated safely with a new project")
            project = Project(project_id="prj_" + secrets.token_hex(6), display_name=project_name,
                              description="Portable TALK project", project_root_path=str(paths.project_dir()),
                              maintainer_member_id=admin.id)
            session.add(project)
            session.commit()
            session.refresh(project)
            project_status = "created"
        else:
            project_status = "existing"
        project_root = Path(project.project_root_path or paths.project_dir()).resolve()
        if not project_root.is_relative_to(paths.data_dir().resolve()):
            raise RuntimeError("existing project root must be inside the portable data directory")
        project_root.mkdir(parents=True, exist_ok=True)
        meta_dir = project_root / ".talk"
        meta_dir.mkdir(exist_ok=True)
        meta_path = meta_dir / "project.yaml"
        if meta_path.exists():
            import yaml
            with meta_path.open(encoding="utf-8") as stream:
                saved = yaml.safe_load(stream)
            if not isinstance(saved, dict) or saved.get("project_id") != project.project_id:
                raise RuntimeError("existing project metadata does not match the database project")
        metadata = {"version": 1, "project_id": project.project_id, "display_name": project.display_name,
                    "description": project.description or "", "talk_server": base_url,
                    "created_at": project.created_at.isoformat(), "maintainer": project.maintainer_member_id}
        # JSON is a YAML subset, and handles arbitrary Unicode and punctuation safely.
        write_new(meta_path, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        runtime = {"schema": "talk-runtime-config-1", "version": 1, "project_id": project.project_id,
                   "project_root": str(project_root), "base_url": base_url, "operator_key_file": str(key_file),
                   "key_root": str(keys), "state_dir": str(paths.state_dir()),
                   "api_argv": [str(paths.python_executable()), "-B", "-X", "utf8", "-m", "scripts.talk_api",
                                "--host", "127.0.0.1", "--port", str(port), "--control-file", "{control_file}"],
                   "hosts": [], "provision_worker": True}
        result["runtime_status"] = "created" if write_new(paths.config_dir() / "runtime.json", json.dumps(runtime, ensure_ascii=False, indent=2) + "\n") else "existing"
        result["project"] = {"id": project.project_id, "status": project_status, "root": str(project_root)}
        result["seed"] = seed_runners(session, admin)
    engine.dispose()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--project-name", default="TALK")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        print(json.dumps(bootstrap(args.root.resolve(), args.port, args.project_name, args.apply), ensure_ascii=False))
        return 0
    except Exception as exc:
        # SQL errors can include bound parameters, including credentials.
        detail = "database operation failed; existing files were preserved" if hasattr(exc, "statement") else str(exc)
        print(json.dumps({"ok": False, "error": type(exc).__name__, "detail": detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
