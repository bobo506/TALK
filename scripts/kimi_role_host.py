"""Managed Kimi host for one explicitly configured project/member.

Uses HostManager for all ownership, task, start and stop semantics. This adapter
only limits claim scope, declares the Kimi entry/profile and publishes health.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from bridges.kimi_native_config import KimiConfigError, config_problem, read_config_text
from scripts import role_service_host as rsh


class Drained(Exception):
    pass


def manager_directory(state_dir, project, member):
    return rsh.assert_inside_root(Path(state_dir), Path('kimi-dynamic') /
        rsh._sanitize_token(project) / rsh._sanitize_token(member))


def host_spec(config, role):
    """Pure public recipe. Identity and private Key are checked by the caller."""
    recipe = config.get('kimi')
    if not isinstance(recipe, dict) or recipe.get('enabled') is not True:
        return None
    if role.get('archived') or role.get('binding_state') != 'bound':
        return None
    if ((role.get('runner') or {}).get('runtime') != 'kimi-code'
            or (role.get('service') or {}).get('control_kind') != 'managed_cli'):
        return None
    if role.get('project_id', config['project_id']) != config['project_id']:
        return None
    member = role['member_id']
    model = role.get('model') or {}
    choice, alias = model.get('choice_id'), model.get('model_alias')
    if not isinstance(choice, str) or not choice or not isinstance(alias, str) or not alias:
        return None
    profiles = recipe.get('task_profiles', {})
    profile = profiles.get(member, 'review')
    if profile not in ('review', 'tools'):
        raise ValueError('kimi_task_profile_invalid')
    from scripts.role_provision import key_file_path
    key = key_file_path(Path(config['key_root']), member)
    private = manager_directory(config['state_dir'], config['project_id'], member)
    argv = [sys.executable, '-B', '-X', 'utf8', '-m', 'scripts.kimi_role_host',
        '--project', config['project_id'], '--member', member,
        '--project-root', config['project_root'], '--state-dir', config['state_dir'],
        '--base-url', config['base_url'], '--operator-key-file', config['operator_key_file'],
        '--role-key-file', str(key), '--expected-choice-id', choice,
        '--expected-model-alias', alias, '--task-profile', profile, '--apply']
    return {'member_id': member, 'argv': argv,
        'health_file': str(private / 'manager-health.json'),
        'drain_file': str(private / 'drain.request')}


class KimiRoleHost(rsh.HostManager):
    def __init__(self, *args, project, member, display_name, task_profile, private, **kwargs):
        self.project = project
        self.member = member
        self.display_name = display_name
        self.task_profile = task_profile
        self.private = Path(private)
        self.drain_requested = False
        self._health_degraded = False
        context = kwargs.get('workspace_context')
        if context is not None and (not isinstance(context, dict) or context.get('runner') != 'kimi-code'
                or context.get('project_id') != project or context.get('member_id') != member):
            raise rsh.HostError('workspace_context_invalid', 'workspace identity or runner mismatch')
        super().__init__(*args, **kwargs)
        if self.workspace_context is not None:
            self.private = Path(self.workspace_context['state']['manager'])

    def publish_health(self, state='serving'):
        if self.workspace_context is not None:
            self._workspace_check_file(self.private / 'manager-health.json', self.private)
        rsh.ensure_private_dir(self.private)
        value = {'schema': 'talk-kimi-manager-health-1', 'pid': os.getpid(),
            'project_id': self.project, 'member_id': self.member,
            'seen_at': datetime.now(timezone.utc).isoformat(), 'state': state,
            'draining': self.drain_requested, 'owned_launches': list(self._handles)}
        rsh._publish_private_bytes(self.private / 'manager-health.json',
            (json.dumps(value) + '\n').encode('utf-8'))

    def publish_health_best_effort(self, state='serving'):
        try:
            self.publish_health(state)
        except (rsh.HostError, OSError, ValueError):
            if not self._health_degraded:
                # Fixed, bounded diagnostic; filesystem errors may contain secrets.
                try:
                    print('kimi_host_health_unavailable', file=sys.stderr)
                except (OSError, ValueError):
                    pass
            self._health_degraded = True
        else:
            self._health_degraded = False

    def claimable_actions(self, project_id):
        if project_id != self.project:
            return []
        if self.workspace_context is not None:
            self._workspace_check_file(self.private / 'drain.request', self.private)
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
                or binding.get('runtime') != 'kimi-code'
                or not isinstance(binding.get('provider_id'), str) or not binding['provider_id']
                or not isinstance(binding.get('model_id'), str) or not binding['model_id']):
            raise rsh.HostError('binding_fingerprint_mismatch', '角色模型绑定不完整或已改变')
        return binding

    def _config_problem(self, home, alias, model_id, provider_id):
        """结构化核对角色 config.toml；``default_effort`` 不参与（由 TALK 按绑定写入）。"""
        config = rsh.assert_inside_root(home, Path('.kimi-code') / 'config.toml')
        if rsh._is_reparse_point(config) or not config.is_file():
            raise KimiConfigError('配置文件不可用')
        return config_problem(read_config_text(config), alias, model_id, provider_id)

    def build_entry_argv(self, runtime, model_alias):
        if runtime != 'kimi-code':
            raise rsh.HostError('kimi_runtime_only', '本宿主只服务当前Kimi角色')
        home = self.store.native_home_dir(self.project, self.member)
        if rsh.lock_path_for(home / 'kimi-role-setup').exists():
            raise rsh.HostError('kimi_setup_in_progress', '请等待角色原生登录完成')
        binding = self._current_binding(self.project, self.member, model_alias)
        try:
            problem = self._config_problem(home, model_alias, binding['model_id'], binding['provider_id'])
        except (OSError, ValueError) as exc:
            problem = str(exc) or '配置文件不可读'
        if problem:
            raise rsh.HostError(
                'kimi_role_setup_required',
                '请先在本机完成该角色的Kimi登录和模型配置（%s）' % problem,
            ) from None
        argv, template, timeout = super().build_entry_argv(runtime, model_alias)
        argv += ['--display-name', self.display_name, '--workdir', str(self.project_root.resolve()),
            '--kimi-task-profile', self.task_profile]
        return argv, template, timeout

    def preflight(self, command, member_id, *, project_id, action='start', diagnostics=None):
        facts = super().preflight(command, member_id, project_id=project_id, action=action, diagnostics=diagnostics)
        roles = self.client.request('GET', '/api/projects/' + rsh.urllib.parse.quote(project_id, safe='') + '/roles')
        roles = roles if isinstance(roles, list) else roles.get('data') if isinstance(roles, dict) else None
        role = next((item for item in roles or [] if isinstance(item, dict) and item.get('member_id') == member_id), None)
        selected = (role or {}).get('model') or {}
        alias = command.get('model_alias')
        if (not role or not isinstance(selected, dict) or role.get('archived') or role.get('binding_state') != 'bound'
                or selected.get('model_alias') != alias or not isinstance(selected.get('model_id'), str)
                or not selected['model_id']):
            raise rsh.HostError('binding_fingerprint_mismatch', '角色模型选择已改变，请重新启动')
        binding = self._current_binding(project_id, member_id, alias)
        if binding['model_id'] != selected['model_id']:
            raise rsh.HostError('binding_fingerprint_mismatch', '角色模型绑定已改变，请重新启动')
        try:
            home = self.store.native_home_dir(project_id, member_id)
            problem = self._config_problem(home, alias, selected['model_id'], binding['provider_id'])
        except (OSError, ValueError) as exc:
            problem = str(exc) or '配置文件不可读'
        if problem:
            raise rsh.HostError(
                'kimi_role_setup_required',
                '角色本机模型与所选模型不一致，请重新配置（%s）' % problem,
            ) from None
        return facts

    def child_environment(self, project_id, member_id):
        if (project_id, member_id) != (self.project, self.member):
            raise rsh.HostError('identity_mismatch', '宿主作用域不匹配')
        env = super().child_environment(project_id, member_id)
        home = self.store.native_home_dir(project_id, member_id)
        if any(Path(env[name]).resolve() != home for name in rsh.NATIVE_HOME_ENV_VARS):
            raise rsh.HostError('kimi_isolation_override', '角色隔离环境不得覆盖')
        env['KIMI_CODE_HOME'] = str(home / '.kimi-code')
        return env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'member', 'project-root', 'state-dir', 'base-url',
                 'operator-key-file', 'role-key-file', 'expected-choice-id', 'expected-model-alias'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--task-profile', choices=('review', 'tools'), default='review')
    parser.add_argument('--workspace-context', default=None)
    parser.add_argument('--key-root', default=None)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    context = None
    try:
        if args.workspace_context is not None or args.key_root is not None:
            if args.workspace_context is None or args.key_root is None:
                raise rsh.HostError('workspace_context_invalid', 'workspace context and key root required')
            context = rsh.validate_workspace_context(json.loads(args.workspace_context),
                project=args.project, member=args.member, project_root=Path(args.project_root),
                key_root=Path(args.key_root), role_key_file=Path(args.role_key_file))
            if context['runner'] != 'kimi-code':
                raise rsh.HostError('workspace_context_invalid', 'workspace runner mismatch')
    except (rsh.HostError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error_code': getattr(exc, 'code', 'workspace_context_invalid')}))
        return 1
    private = (Path(context['state']['manager']) if context is not None
               else manager_directory(args.state_dir, args.project, args.member))
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
                or (role.get('runner') or {}).get('runtime') != 'kimi-code'
                or (role.get('model') or {}).get('choice_id') != args.expected_choice_id
                or (role.get('model') or {}).get('model_alias') != args.expected_model_alias):
            raise rsh.HostError('binding_fingerprint_mismatch', 'Kimi角色或模型选择已改变')
        if context is not None:
            layouts = client.request('GET', '/api/projects/' + args.project + '/role-storage-layouts')
            layouts = layouts if isinstance(layouts, list) else layouts.get('data') if isinstance(layouts, dict) else None
            if not isinstance(layouts, list) or any(not isinstance(row, dict) for row in layouts):
                raise rsh.HostError('workspace_context_invalid', 'workspace layout unavailable')
            matching = [row for row in layouts if row.get('member_id') == args.member]
            if len(matching) != 1 or matching[0].get('storage_layout') not in ('legacy', 'workspace-v1'):
                raise rsh.HostError('workspace_context_invalid', 'workspace layout invalid')
            is_workspace = matching[0]['storage_layout'] == 'workspace-v1'
            if is_workspace != (context is not None):
                raise rsh.HostError('workspace_context_invalid', 'workspace layout mismatch')
        key_path = Path(args.role_key_file)
        if context is not None:
            rsh.validate_workspace_context(context, project=args.project, member=args.member,
                project_root=Path(args.project_root), key_root=Path(args.key_root), role_key_file=key_path)
        role_key = key_path.read_text(encoding='utf-8').strip()
        identity = client.request('GET', '/api/members/me', key=role_key)
        if identity.get('id') != args.member or identity.get('kind') != 'agent':
            raise rsh.HostError('identity_mismatch', '角色Key与目标不匹配')
        manager = KimiRoleHost(client, project=args.project, member=args.member,
            display_name=role.get('role_name') or identity['display_name'], task_profile=args.task_profile,
            private=private, state_dir=Path(args.state_dir), operator_key=operator,
            role_key_file=key_path, project_root=Path(args.project_root), verified_runtimes=['kimi-code'],
            role_key_root=Path(args.key_root) if args.key_root else None, workspace_context=context,
            workspace_project=args.project, workspace_member=args.member)
        while True:
            try:
                manager.serve(args.project, poll_interval=rsh.DEFAULT_POLL_INTERVAL_SECONDS,
                    once=False, max_rounds=None, provision_worker=None)
                if manager.workspace_context is not None and manager._workspace_draining and not manager._handles:
                    manager.drain_requested = True
                    manager.publish_health_best_effort('stopped')
                    return 0
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
        print(json.dumps({'ok': False, 'error_code': getattr(exc, 'code', 'kimi_host_config_invalid')}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
