"""Managed Codex host for one explicitly configured project/member.

Uses HostManager for all ownership, task, start and stop semantics. This adapter
only limits claim scope, declares the Codex entry/profile and publishes health.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from scripts import role_service_host as rsh


class Drained(Exception):
    pass


def manager_directory(state_dir, project, member):
    return rsh.assert_inside_root(Path(state_dir), Path('codex-dynamic') /
        rsh._sanitize_token(project) / rsh._sanitize_token(member))


def host_spec(config, role):
    """Pure public recipe. Identity and private Key are checked by the caller."""
    recipe = config.get('codex')
    if not isinstance(recipe, dict) or recipe.get('enabled') is not True:
        return None
    if role.get('archived') or role.get('binding_state') != 'bound':
        return None
    if ((role.get('runner') or {}).get('runtime') != 'codex'
            or (role.get('service') or {}).get('control_kind') != 'managed_cli'):
        return None
    if role.get('project_id', config['project_id']) != config['project_id']:
        return None
    member = role['member_id']
    model = role.get('model') or {}
    choice, alias = model.get('choice_id'), model.get('model_alias')
    if not isinstance(choice, str) or not choice or not isinstance(alias, str) or not alias:
        return None
    if not isinstance(recipe.get('executable'), str) or not Path(recipe['executable']).is_absolute():
        raise ValueError('codex_executable_required')
    profiles = recipe.get('task_profiles', {})
    profile = profiles.get(member, 'review')
    if profile not in ('review', 'tools'):
        raise ValueError('codex_task_profile_invalid')
    from scripts.role_provision import key_file_path
    key = key_file_path(Path(config['key_root']), member)
    private = manager_directory(config['state_dir'], config['project_id'], member)
    argv = [sys.executable, '-B', '-X', 'utf8', '-m', 'scripts.codex_role_host',
        '--project', config['project_id'], '--member', member,
        '--project-root', config['project_root'], '--state-dir', config['state_dir'],
        '--base-url', config['base_url'], '--operator-key-file', config['operator_key_file'],
        '--role-key-file', str(key), '--expected-choice-id', choice,
        '--expected-model-alias', alias, '--codex-executable', recipe['executable'], '--task-profile', profile, '--apply']
    return {'member_id': member, 'argv': argv,
        'health_file': str(private / 'manager-health.json'),
        'drain_file': str(private / 'drain.request')}


class CodexRoleHost(rsh.HostManager):
    def __init__(self, *args, project, member, display_name, task_profile, private, codex_executable, **kwargs):
        self.codex_executable = codex_executable
        self.project = project
        self.member = member
        self.display_name = display_name
        self.task_profile = task_profile
        self.private = Path(private)
        self.drain_requested = False
        self._health_degraded = False
        super().__init__(*args, **kwargs)

    def publish_health(self, state='serving'):
        rsh.ensure_private_dir(self.private)
        value = {'schema': 'talk-codex-manager-health-1', 'pid': os.getpid(),
            'project_id': self.project, 'member_id': self.member,
            'seen_at': datetime.now(timezone.utc).isoformat(), 'state': state,
            'draining': self.drain_requested}
        rsh._publish_private_bytes(self.private / 'manager-health.json',
            (json.dumps(value) + '\n').encode('utf-8'))

    def publish_health_best_effort(self, state='serving'):
        try:
            self.publish_health(state)
        except (rsh.HostError, OSError, ValueError):
            if not self._health_degraded:
                # Fixed, bounded diagnostic; filesystem errors may contain secrets.
                try:
                    print('codex_host_health_unavailable', file=sys.stderr)
                except (OSError, ValueError):
                    pass
            self._health_degraded = True
        else:
            self._health_degraded = False

    def claimable_actions(self, project_id):
        if project_id != self.project:
            return []
        self.drain_requested = self.drain_requested or (self.private / 'drain.request').is_file()
        if self.drain_requested and not self._handles:
            raise Drained()
        self.publish_health_best_effort()
        return [action for action in super().claimable_actions(project_id)
            if action.get('project_id') == self.project and action.get('member_id') == self.member
            and (not self.drain_requested or action.get('action') == 'stop')]

    def _current_binding(self, project_id, member_id, alias):
        response = self.client.request('GET', '/api/projects/' + rsh.urllib.parse.quote(project_id, safe='') + '/agents')
        rows = response.get('data') if isinstance(response, dict) else response
        if not isinstance(rows, list):
            raise rsh.HostError('binding_fingerprint_mismatch', '无法核实角色模型绑定')
        matches = [item for item in rows if isinstance(item, dict) and item.get('member_id') == member_id]
        if len(matches) != 1 or matches[0].get('binding_state') != 'bound':
            raise rsh.HostError('binding_fingerprint_mismatch', '角色模型绑定不可用')
        binding = matches[0].get('binding')
        if (not isinstance(binding, dict) or binding.get('model_alias') != alias
                or binding.get('runtime') != 'codex'
                or not isinstance(binding.get('provider_id'), str) or not binding['provider_id']
                or not isinstance(binding.get('model_id'), str) or not binding['model_id']):
            raise rsh.HostError('binding_fingerprint_mismatch', '角色模型绑定不完整或已改变')
        return binding

    def _configuration(self, alias):
        from scripts.codex_role_setup import read_config, EFFORTS
        home = self.store.native_home_dir(self.project, self.member)
        if rsh.lock_path_for(home / 'codex-role-setup').exists():
            raise rsh.HostError('codex_setup_in_progress', '请等待角色官方授权完成')
        binding = self._current_binding(self.project, self.member, alias)
        try:
            config = read_config(rsh.assert_inside_root(home, Path('.codex') / 'config.toml'))
            if (config is None or config.get('model') != binding['model_id']
                    or binding['provider_id'] != 'openai'
                    or config.get('model_reasoning_effort') not in EFFORTS):
                raise ValueError()
        except (OSError, ValueError, RuntimeError):
            raise rsh.HostError('codex_role_setup_required', '请先完成该角色的官方授权和模型准备') from None
        return config

    def build_entry_argv(self, runtime, model_alias):
        if runtime != 'codex':
            raise rsh.HostError('codex_runtime_only', '宿主仅服务当前 Codex 角色')
        import shlex
        from bridges import cli_bridge
        from cli.profiles import compose_system_prompt, load_profile
        from scripts.codex_role_setup import require_version, SetupError
        config = self._configuration(model_alias)
        try:
            require_version(self.codex_executable, self.project_root, self.child_environment(self.project, self.member))
        except SetupError:
            raise rsh.HostError('codex_version_unsupported', '当前 Codex CLI 版本未适配') from None
        profile = load_profile(self.project, self.member)
        def command(prompt, sandbox):
            return shlex.join([self.codex_executable, '-a', 'never', '--strict-config', 'exec',
                '--model', config['model'], '--sandbox', sandbox, '--color', 'never',
                '--skip-git-repo-check', '--ignore-rules',
                '-c', 'model_reasoning_effort=' + json.dumps(config['model_reasoning_effort']),
                '-c', 'base_instructions=' + json.dumps(compose_system_prompt(prompt, profile)), '-'])
        message = command(cli_bridge.TASK_RUNNER_SYSTEM_PROMPT, 'read-only')
        task = command(cli_bridge.TASK_RUNNER_SYSTEM_PROMPT,
            'workspace-write' if self.task_profile == 'tools' else 'read-only')
        precheck = command(cli_bridge.TASK_PREFLIGHT_SYSTEM_PROMPT, 'read-only')
        # HostManager validates and parses the shared python -m entry contract.
        argv = [sys.executable, '-m', 'bridges.codex_bridge',
            '--codex-command', message, '--codex-task-command', task,
            '--task-preflight-command', precheck, '--codex-execution-profile',
            'tools' if self.task_profile == 'tools' else 'discussion',
            '--timeout', str(self.execution_timeout_seconds or 86400),
            '--display-name', self.display_name, '--workdir', str(self.project_root.resolve())]
        return argv, 'codex_role_selection', 'explicit' if self.execution_timeout_seconds else 'builtin_default'

    def preflight(self, command, member_id, *, project_id, action='start', diagnostics=None):
        facts = super().preflight(command, member_id, project_id=project_id, action=action, diagnostics=diagnostics)
        self._configuration(command.get('model_alias'))
        return facts

    def child_environment(self, project_id, member_id):
        if (project_id, member_id) != (self.project, self.member):
            raise rsh.HostError('identity_mismatch', '宿主作用域不匹配')
        env = super().child_environment(project_id, member_id)
        home = self.store.native_home_dir(project_id, member_id)
        if any(Path(env[name]).resolve() != home for name in rsh.NATIVE_HOME_ENV_VARS):
            raise rsh.HostError('codex_isolation_override', '角色隔离环境不得覆盖')
        env['CODEX_HOME'] = str(home / '.codex')
        return env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'member', 'project-root', 'state-dir', 'base-url',
                 'operator-key-file', 'role-key-file', 'expected-choice-id', 'expected-model-alias', 'codex-executable'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--task-profile', choices=('review', 'tools'), default='review')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    private = manager_directory(args.state_dir, args.project, args.member)
    if not args.apply:
        print(json.dumps({'mode': 'dry_run', 'project_id': args.project, 'member_id': args.member}))
        return 0
    manager = None
    try:
        operator = rsh.load_operator_key(None, {
            rsh.OPERATOR_KEY_ENV: '', rsh.OPERATOR_KEY_FILE_ENV: args.operator_key_file})
        client = rsh.TalkHostClient(args.base_url, operator)
        if client.request('GET', '/api/members/me').get('kind') != 'human':
            raise rsh.HostError('identity_mismatch', '宿主需要human正常认证')
        response = client.request('GET', '/api/projects/' + args.project + '/roles')
        roles = response if isinstance(response, list) else response.get('data')
        if not isinstance(roles, list) or any(not isinstance(row, dict) for row in roles):
            raise rsh.HostError('identity_mismatch', '角色投影不可用')
        role = next((r for r in roles if r.get('member_id') == args.member), None)
        if (not role or role.get('archived') or role.get('binding_state') != 'bound'
                or (role.get('runner') or {}).get('runtime') != 'codex'
                or (role.get('model') or {}).get('choice_id') != args.expected_choice_id
                or (role.get('model') or {}).get('model_alias') != args.expected_model_alias):
            raise rsh.HostError('binding_fingerprint_mismatch', 'Codex角色或模型选择已改变')
        key_path = Path(args.role_key_file)
        role_key = key_path.read_text(encoding='utf-8').strip()
        identity = client.request('GET', '/api/members/me', key=role_key)
        if identity.get('id') != args.member or identity.get('kind') != 'agent':
            raise rsh.HostError('identity_mismatch', '角色Key与目标不匹配')
        manager = CodexRoleHost(client, project=args.project, member=args.member,
            display_name=role.get('role_name') or identity['display_name'], task_profile=args.task_profile,
            private=private, codex_executable=args.codex_executable, state_dir=Path(args.state_dir), operator_key=operator,
            role_key_file=key_path, project_root=Path(args.project_root), verified_runtimes=['codex'])
        while True:
            try:
                manager.serve(args.project, poll_interval=rsh.DEFAULT_POLL_INTERVAL_SECONDS,
                    once=False, max_rounds=None, provision_worker=None)
            except Drained:
                manager.publish_health_best_effort('stopped')
                return 0
            except (rsh.HostError, OSError, ValueError):
                # Keep the original Popen owners on transient host/health errors.
                # Never exit an owning manager to make an error look like a stop.
                if manager._handles:
                    time.sleep(rsh.DEFAULT_POLL_INTERVAL_SECONDS)
                    continue
                raise
            except KeyboardInterrupt:
                manager.drain_requested = True
                if not manager._handles:
                    manager.publish_health_best_effort('stopped')
                    return 0
                try:
                    manager.request_stop(args.project, args.member)
                except rsh.HostError:
                    pass
    except (rsh.HostError, OSError, ValueError) as exc:
        if manager is not None and manager._handles:
            raise
        print(json.dumps({'ok': False, 'error_code': getattr(exc, 'code', 'codex_host_config_invalid')}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
