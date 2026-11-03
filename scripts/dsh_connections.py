"""Explicit, secret-free DSH connection configuration validation."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import string

ENV_NAME = re.compile(r'TALK_DSH_CONNECTION_[A-Z0-9_]+_API_KEY\Z')
TARGET_ENV_NAME = re.compile(r'[A-Z][A-Z0-9_]*_API_KEY\Z')
SAFE_TOKEN = re.compile(r'[A-Za-z0-9._:/@\-]+\Z')
DIMENSIONS = ('runner_id', 'runtime', 'model_source', 'provider_id', 'connection_ref', 'model_id', 'model_alias')
PROFILES = ('review', 'tools')
PUBLIC_MAPPING_FIELDS = frozenset(DIMENSIONS + ('auth_type', 'api_key_env', 'target_api_key_env', 'command_template', 'tools_command_template'))


class ConnectionSetupError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _fail(code):
    raise ConnectionSetupError(code)


def _check_argv(parts, secret=None):
    if not parts:
        _fail('dsh_command_invalid')
    for part in parts:
        lower = part.lower()
        if (re.match(r'^--?(?:api[-_]?key|key|token|authorization)(?:=|:|$)', lower)
                or re.match(r'^authorization(?:\s*:|$)', lower)
                or re.match(r'^(?:-h|--header[= ])\s*authorization\s*:', lower)
                or re.match(r'^[a-z_][a-z0-9_]*(?:api_?key|token|authorization)=', lower)
                or (secret and secret in part)):
            _fail('dsh_command_invalid')


def _template_parts(template):
    if not isinstance(template, str) or not template:
        _fail('dsh_command_invalid')
    try:
        parsed = list(string.Formatter().parse(template))
        if any(spec or conversion for _, field, spec, conversion in parsed if field is not None):
            _fail('dsh_command_invalid')
        fields = [field for _, field, _, _ in parsed if field is not None]
        if set(fields) != {'model', 'model_id'}:
            _fail('dsh_command_invalid')
        parts = shlex.split(template, posix=True)
    except ValueError:
        _fail('dsh_command_invalid')
    _check_argv(parts)
    return parts


def resolve_connection(config, binding):
    recipe = config.get('dsh') if isinstance(config, dict) else None
    if not isinstance(recipe, dict) or recipe.get('enabled') is not True:
        _fail('dsh_connection_required')
    if not isinstance(binding, dict):
        _fail('dsh_connection_mismatch')
    ref = binding.get('connection_ref')
    connections = recipe.get('connections')
    entry = connections.get(ref) if isinstance(connections, dict) and isinstance(ref, str) else None
    if not isinstance(entry, dict):
        _fail('dsh_connection_required')
    if any(field not in PUBLIC_MAPPING_FIELDS for field in entry):
        _fail('dsh_connection_mismatch')
    for field in DIMENSIONS:
        expected = binding.get(field)
        if not isinstance(expected, str) or not SAFE_TOKEN.fullmatch(expected) or entry.get(field) != expected:
            _fail('dsh_connection_mismatch')
    target = entry.get('target_api_key_env')
    if (entry.get('auth_type') != 'api_key'
            or not ENV_NAME.fullmatch(str(entry.get('api_key_env') or ''))
            or not TARGET_ENV_NAME.fullmatch(str(target or ''))
            or target.startswith('TALK_')):
        _fail('dsh_connection_mismatch')
    for field in ('command_template', 'tools_command_template'):
        if field in entry:
            _template_parts(entry[field])
    return dict(entry)


def connection_command(entry, binding, profile):
    if profile not in PROFILES:
        _fail('dsh_task_profile_invalid')
    template = entry.get('command_template' if profile == 'review' else 'tools_command_template')
    _template_parts(template)
    return template.replace('{model_id}', binding['model_id'])


def connection_environment(entry, environ=None):
    source = os.environ if environ is None else environ
    value = source.get(entry['api_key_env'])
    if not isinstance(value, str) or not value.strip():
        _fail('dsh_connection_secret_missing')
    return {entry['target_api_key_env']: value}


def validate_command(entry, binding, profile='tools', *, which=shutil.which, secret=None):
    command = connection_command(entry, binding, profile).replace('{model}', binding['model_alias'])
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        _fail('dsh_command_invalid')
    _check_argv(parts, secret)
    if not which(parts[0]):
        _fail('native_cli_missing')
    return parts


def validate_dsh_config(config):
    recipe = config.get('dsh')
    if recipe is None:
        return
    if (not isinstance(recipe, dict) or type(recipe.get('enabled')) is not bool
            or any(field not in {'enabled', 'task_profiles', 'connections'} for field in recipe)
            or not isinstance(recipe.get('task_profiles', {}), dict)
            or any(not isinstance(member, str) or not member or profile not in PROFILES
                   for member, profile in recipe.get('task_profiles', {}).items())
            or not isinstance(recipe.get('connections'), dict)):
        _fail('runtime_host_config_invalid')
    if recipe['enabled']:
        for ref, entry in recipe['connections'].items():
            if not isinstance(ref, str) or not ref or not isinstance(entry, dict) or entry.get('connection_ref') != ref:
                _fail('runtime_host_config_invalid')
            try:
                resolve_connection(config, entry)
            except ConnectionSetupError:
                _fail('runtime_host_config_invalid')
