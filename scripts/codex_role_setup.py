"""新 Codex 角色的独立设备授权及公开模型配置；不读取或复制 auth.json。"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib
from types import SimpleNamespace

from bridges.codex_execution_native import CodexNative, LaunchSpec, SUPPORTED_VERSIONS
from scripts import role_service_host as host
from scripts import native_setup_process
from scripts.kimi_role_setup import _local_facts, _open_db, release_native_login, cancel_native_login
from scripts.role_provision import acquire_lock, release_lock, lock_path_for

ROOT = Path(__file__).resolve().parents[1]
EFFORTS = {'minimal', 'low', 'medium', 'high', 'xhigh'}
IDENTIFIER = re.compile(r'[A-Za-z0-9_.:/-]{1,128}\Z')
BASE_CONFIG = {'cli_auth_credentials_store': 'file', 'forced_login_method': 'chatgpt',
               'model_provider': 'openai'}


class SetupError(RuntimeError):
    pass


def _role(db, project, member):
    row = db.execute('''SELECT b.model_alias,b.model_id,b.provider_id,b.model_source,b.connection_ref,
        s.desired_state,s.observed_state,s.owner_host,s.process_launch_id
        FROM project_roles p JOIN project_role_bindings b
        ON b.project_id=p.project_id AND b.member_id=p.member_id
        JOIN runner_registry r ON r.runner_id=b.runner_id
        LEFT JOIN role_service_state s ON s.project_id=p.project_id AND s.member_id=p.member_id
        WHERE p.project_id=? AND p.member_id=? AND p.archived_at IS NULL
        AND r.runtime='codex' AND r.control_kind='managed_cli' ''', (project, member)).fetchone()
    if not row:
        raise SetupError('native_setup_not_supported')
    alias, model, provider, source, connection, desired, observed, owner, launch = row
    if (not isinstance(alias, str) or not IDENTIFIER.fullmatch(alias)
            or not isinstance(model, str) or not IDENTIFIER.fullmatch(model)
            or (provider, source, connection) != ('openai', 'builtin', 'native-codex-chatgpt-login')):
        raise SetupError('native_model_configuration_required')
    safely_failed = observed == 'failed' and not owner and not launch
    if ((desired not in (None, 'stopped') and not safely_failed)
            or observed not in (None, 'not_started', 'stopped', 'failed') or owner or launch):
        raise SetupError('native_role_busy')
    return alias, model, provider


def executable(config):
    recipe = config.get('codex')
    value = recipe.get('executable') if isinstance(recipe, dict) and recipe.get('enabled') is True else None
    if (not isinstance(value, str) or not Path(value).is_absolute()
            or Path(value).name.lower() not in ('codex.exe', 'codex') or not Path(value).is_file()):
        raise SetupError('native_cli_missing')
    return str(Path(value).resolve())


def environment(home):
    env = {name: value for name in host.CHILD_ENV_ALLOWLIST if (value := os.environ.get(name))}
    env.update({name: str(home) for name in host.NATIVE_HOME_ENV_VARS})
    env['CODEX_HOME'] = str(home / '.codex')
    return env


def require_version(exe, root, env):
    """只接受声明的协议版本；返回实际版本供启动/rollout 身份校验。"""
    try:
        result = subprocess.run([exe, '--version'], cwd=root, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding='utf-8', timeout=15, check=True,
            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        value = result.stdout.strip()
        if not value.startswith('codex-cli '):
            raise SetupError('native_cli_version_unsupported')
        version = value[len('codex-cli '):]
        if version not in SUPPORTED_VERSIONS:
            raise SetupError('native_cli_version_unsupported')
        return version
    except (OSError, subprocess.SubprocessError):
        raise SetupError('native_cli_version_unsupported') from None


def read_config(path):
    if not path.exists():
        return None
    if host._is_reparse_point(path) or not path.is_file() or path.stat().st_size > 65536:
        raise SetupError('native_model_configuration_required')
    with path.open('rb') as stream:
        value = tomllib.load(stream)
    if (set(value) - set(BASE_CONFIG) - {'model', 'model_reasoning_effort'}
            or any(value.get(k) != v for k, v in BASE_CONFIG.items())):
        raise SetupError('native_model_configuration_required')
    return value


def write_config(path, value):
    # Private, atomic publication; only the explicit public configuration is written.
    text = ''.join(k + ' = ' + json.dumps(v) + '\n' for k, v in value.items())
    host._publish_private_bytes(path, text.encode('utf-8'))


def begin_native_login(project, member, *, root=ROOT, popen=subprocess.Popen):
    config, database = _local_facts(root, project, member)
    exe = executable(config)
    db = _open_db(database)
    lock = transition = None
    try:
        db.execute('BEGIN IMMEDIATE')
        binding = _role(db, project, member)
        state = Path(config['state_dir'])
        home = host.ensure_private_dir(host.assert_inside_root(state,
            Path('native') / host._sanitize_token(project) / host._sanitize_token(member)))
        native = host.ensure_private_dir(host.assert_inside_root(home, Path('.codex')))
        transition_path = lock_path_for(home / 'native-setup-transition')
        transition = acquire_lock(transition_path)
        native_setup_process.stop_previous(home, project, member)
        lock_path = lock_path_for(home / 'codex-role-setup')
        lock = acquire_lock(lock_path)
        prior = read_config(native / 'config.toml')
        if prior is not None and prior.get('model') != binding[1]:
            raise SetupError('native_model_selection_changed')
        env = environment(home)
        version = require_version(exe, root, env)
        write_config(native / 'config.toml', prior or dict(BASE_CONFIG, model=binding[1]))
        db.rollback()
        options = {'startupinfo': host._hidden_startupinfo()} if os.name == 'nt' else {'start_new_session': True}
        base_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        process, generation = native_setup_process.spawn_recorded(home, project, member, lock,
            lambda flags: popen([exe, 'login', '--device-auth'], cwd=str(root), env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', bufsize=1,
                **({'creationflags': base_flags | flags} if os.name == 'nt' else {}), **options),
            lock_name='codex-role-setup')
        return SimpleNamespace(project=project, member=member, root=root, config=config,
            database=database, binding=binding, executable=exe, home=home, native_home=native,
            lock_path=lock_path, lock=lock, process=process, process_generation=generation, released=False,
            setup_runtime='codex', setup_version=version)
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


async def _model_effort(attempt):
    """Read account/model metadata only: no thread/start, turn/start or inference."""
    env = environment(attempt.home)
    spec = LaunchSpec(argv=[attempt.executable, '-a', 'never', '--strict-config', 'app-server', '--stdio'],
        env=env, home=attempt.native_home, model=attempt.binding[1], provider='openai',
        effort='', sandbox='read-only', approval='never', fingerprint='role-preparation')
    client = CodexNative(spec, attempt.root)
    try:
        await client.open()
        account = await client.rpc('account/read', {'refreshToken': False})
        if (account.get('account') or {}).get('type') != 'chatgpt':
            raise SetupError('native_authorization_failed')
        cursor = None
        seen = set()
        for _ in range(20):
            params = {'limit': 100, 'includeHidden': True}
            if cursor:
                params['cursor'] = cursor
            result = await client.rpc('model/list', params)
            rows = result.get('data')
            if not isinstance(rows, list):
                raise SetupError('native_model_catalog_unavailable')
            matches = [r for r in rows if isinstance(r, dict) and r.get('model') == attempt.binding[1]]
            if len(matches) == 1:
                entry = matches[0]
                # 新角色准备以官方当前目录为准，不继承名称标注或先前准备值。
                effort = entry.get('defaultReasoningEffort')
                supported = {r.get('reasoningEffort') for r in entry.get('supportedReasoningEfforts', []) if isinstance(r, dict)}
                if effort not in EFFORTS or effort not in supported:
                    raise SetupError('native_model_configuration_required')
                return effort
            cursor = result.get('nextCursor')
            if cursor is None:
                break
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise SetupError('native_model_catalog_unavailable')
            seen.add(cursor)
        raise SetupError('native_selected_model_unavailable')
    finally:
        await client.close()


def finish_native_login(attempt):
    effort = asyncio.run(asyncio.wait_for(_model_effort(attempt), timeout=60))
    db = _open_db(attempt.database)
    try:
        db.execute('BEGIN IMMEDIATE')
        if _role(db, attempt.project, attempt.member) != attempt.binding:
            raise SetupError('native_model_selection_changed')
        prior = read_config(attempt.native_home / 'config.toml')
        if prior is None or prior.get('model') != attempt.binding[1]:
            raise SetupError('native_model_configuration_required')
        write_config(attempt.native_home / 'config.toml', dict(prior, model_reasoning_effort=effort))
        db.rollback()
        # 2026-10-28：把官方 model/list 返回的默认强度挂到 attempt 上，供服务端落库展示。
        attempt.default_effort = effort
        return 'configured'
    finally:
        db.rollback()
        db.close()
        release_native_login(attempt)
