"""Prepare an isolated DSH home after validating its local role binding."""
from pathlib import Path
import re
import shutil
import sqlite3

from scripts import dsh_connections as connections
from scripts import role_service_host as host
from scripts.kimi_role_setup import _local_facts, _open_db
from server.workspace_paths import native_home_dir

ROOT = Path(__file__).resolve().parents[1]


class SetupError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _role(db, project, member):
    row = db.execute('''SELECT b.runner_id, r.runtime, b.model_source, b.provider_id,
        b.connection_ref, b.model_id, b.model_alias, r.control_kind
        FROM project_roles p JOIN project_role_bindings b
          ON b.project_id=p.project_id AND b.member_id=p.member_id
        JOIN runner_registry r ON r.runner_id=b.runner_id
        WHERE p.project_id=? AND p.member_id=? AND p.archived_at IS NULL''',
        (project, member)).fetchone()
    if not row or not isinstance(row[0], str) or not re.fullmatch(r'runner:dsh-.+', row[0]) or row[1] != 'dsh' or row[7] != 'managed_cli':
        raise SetupError('native_setup_not_supported')
    binding = dict(zip(connections.DIMENSIONS, row[:7]))
    if any(not isinstance(binding[k], str) or not connections.SAFE_TOKEN.fullmatch(binding[k]) for k in connections.DIMENSIONS):
        raise SetupError('native_model_configuration_required')
    return binding


def setup(project, member, *, root=ROOT, which=shutil.which, environ=None):
    try:
        config, database = _local_facts(Path(root), project, member)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise SetupError('native_local_configuration_invalid') from None
    except Exception as exc:
        # _local_facts has its own public error type; do not expose its input.
        from scripts.kimi_role_setup import SetupError as LocalError
        if isinstance(exc, LocalError):
            raise SetupError('native_local_configuration_invalid') from None
        raise
    try:
        db = _open_db(database)
        try:
            binding = _role(db, project, member)
            layout = db.execute('SELECT storage_layout FROM project_roles WHERE project_id=? AND member_id=?',
                                (project, member)).fetchone()
            if not layout or layout[0] not in ('legacy', 'workspace-v1'):
                raise SetupError('native_setup_not_supported')
        finally:
            db.close()
        entry = connections.resolve_connection(config, binding)
        profiles = config['dsh'].get('task_profiles', {})
        if not isinstance(profiles, dict) or any(not isinstance(k, str) or not k or v not in connections.PROFILES for k, v in profiles.items()):
            raise SetupError('dsh_task_profile_invalid')
        profile = profiles.get(member, 'tools')
        secret_env = connections.connection_environment(entry, environ)
        secret = next(iter(secret_env.values()))
        if layout[0] == 'workspace-v1':
            native = native_home_dir(root, project, member) / '.dsh'
        else:
            state = Path(config['state_dir'])
            relative = Path('native') / host._sanitize_token(project) / host._sanitize_token(member) / '.dsh'
            native = host.assert_inside_root(state, relative)
        native_home = native.parent.as_posix()
        # Both templates must be safe and resolvable, including the default tools profile.
        for name in connections.PROFILES:
            connections.validate_command(entry, binding, name, which=which, secret=secret,
                native_home=str(native_home))
        del secret, secret_env
        host.ensure_private_dir(native)
        return {'profile': profile, 'native_dir': str(native)}
    except connections.ConnectionSetupError as exc:
        raise SetupError(exc.code) from None
    except (sqlite3.Error, OSError, host.HostError) as exc:
        raise SetupError('native_setup_failed') from None
