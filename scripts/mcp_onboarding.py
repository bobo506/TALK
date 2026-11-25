from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tomllib
from urllib.request import urlopen


def detect(home: Path) -> dict:
    checks = {
        'codex': (home / '.codex/config.toml').is_file(),
        'kimi': (home / '.kimi-code/bin/kimi.exe').is_file() or bool(shutil.which('kimi')),
        'workbuddy': (home / 'AppData/Local/Programs/WorkBuddy/WorkBuddy.exe').is_file(),
        'dsh': (home / '.dsh').is_dir(),
        'antigravity': (
            (home / 'AppData/Local/Programs/Antigravity/Antigravity.exe').is_file()
            or (home / 'AppData/Local/agy/bin/agy.exe').is_file()
            or (home / '.gemini/antigravity').is_dir()
            or bool(shutil.which('agy'))
        ),
    }
    return {name: {'detected': value, 'reason': 'found' if value else 'not_found'} for name, value in checks.items()}


def toml_update(original: str, entry: dict) -> str:
    parsed = tomllib.loads(original)
    servers = parsed.get('mcp_servers', {})
    if not isinstance(servers, dict) or not isinstance(servers.get('talk', {}), dict):
        raise ValueError('unsupported mcp_servers.talk structure')
    talk = servers.get('talk', {})
    env = talk.get('env', {})
    if not isinstance(env, dict):
        raise ValueError('unsupported talk env structure')
    if all(talk.get(k) == entry[k] for k in ('command', 'args')) and env.get('TALK_API_KEY') == entry['env']['TALK_API_KEY']:
        return original
    # Only change explicitly recognized single-line assignments in ordinary tables.
    # Reject inline/dotted definitions and multiline values rather than damage them.
    lines = original.splitlines(keepends=True)
    header = re.compile(r'^\s*\[([^\[\]]+)\]\s*(?:#.*)?(?:\r?\n)?$')
    section = ''
    result = []
    seen = set()
    for line in lines:
        m = header.match(line)
        if m:
            section = m.group(1).strip()
        match = re.match(r'^\s*(command|args|TALK_API_KEY)\s*=', line)
        target = (section == 'mcp_servers.talk' and match and match.group(1) in ('command', 'args')) or (section == 'mcp_servers.talk.env' and match and match.group(1) == 'TALK_API_KEY')
        if target:
            key = match.group(1)
            try:
                tomllib.loads(line)
            except tomllib.TOMLDecodeError as exc:
                raise ValueError('unsupported multiline TOML assignment') from exc
            value = entry['env'][key] if key == 'TALK_API_KEY' else entry[key]
            result.append(f'{key} = {json.dumps(value, ensure_ascii=False)}\n')
            seen.add(key)
        else:
            result.append(line)
    text = ''.join(result)
    # Appending tables already declared is invalid, so insert missing keys before the next table.
    for section_name, keys in [('mcp_servers.talk', ('command', 'args')), ('mcp_servers.talk.env', ('TALK_API_KEY',))]:
        missing = [k for k in keys if k not in seen]
        if not missing:
            continue
        block = ''.join(f'{k} = {json.dumps(entry["env"][k] if k == "TALK_API_KEY" else entry[k], ensure_ascii=False)}\n' for k in missing)
        pattern = re.compile(r'^\s*\[' + re.escape(section_name) + r'\]\s*(?:#.*)?$', re.M)
        match = pattern.search(text)
        if match:
            end = text.find('\n', match.end())
            end = len(text) if end == -1 else end + 1
            text = text[:end] + ('\n' if end == len(text) and not text.endswith('\n') else '') + block + text[end:]
        else:
            text = text.rstrip() + ('\n\n' if text.strip() else '') + f'[{section_name}]\n' + block
    try:
        merged = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError('unsupported TOML layout') from exc
    expected = dict(talk)
    expected.update(command=entry['command'], args=entry['args'], env={**env, **entry['env']})
    if merged.get('mcp_servers', {}).get('talk') != expected:
        raise ValueError('unsupported TOML layout')
    return text


def _json_talk_state(original: str) -> tuple[dict, dict, dict, bool]:
    data = json.loads(original) if original.strip() else {}
    if not isinstance(data, dict) or not isinstance(data.get('mcpServers', {}), dict):
        raise ValueError('invalid mcpServers object')
    servers = data.setdefault('mcpServers', {})
    existing = servers.get('talk', {})
    if not isinstance(existing, dict):
        raise ValueError('invalid talk object')
    # Preserve valid user-configured Streamable HTTP MCP entries instead of mixing url + command.
    # Reject blank, null, or non-string url/serverUrl values fail-closed.
    url_keys = [k for k in ('url', 'serverUrl') if k in existing]
    if url_keys:
        for key in url_keys:
            value = existing[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError('invalid talk object')
        return data, servers, existing, True
    if not isinstance(existing.get('env', {}), dict):
        raise ValueError('invalid talk object')
    return data, servers, existing, False


def json_update(original: str, entry: dict) -> str:
    data, servers, existing, is_http = _json_talk_state(original)
    if is_http:
        return original
    merged = {**existing, **entry, 'env': {**existing.get('env', {}), **entry['env']}}
    if existing == merged:
        return original
    servers['talk'] = merged
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


class KeyMissingError(Exception):
    pass


def read_member_key(home: Path, member_id: str) -> str:
    stem = member_id.replace(':', '_')
    for name in (stem, stem.replace('-', '_')):
        try:
            key = (home / '.talk/keys' / (name + '.key')).read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            continue
        if not key:
            raise ValueError('empty key file')
        return key
    raise KeyMissingError


def yaml_update(original: str, repo: Path, home: Path, python: str) -> str:
    if re.search(r'^\s*-?\s*id\s*:\s*[\"\']?mcp-talk[\"\']?\s*(?:#.*)?$', original, re.M):
        return original
    stripped = original.strip()
    if stripped == '[]':
        original = ''
    elif stripped and not re.match(r'^(?:\s*#.*\n|\s*\n)*\s*-\s', original):
        raise ValueError('unsupported YAML patch layout')
    key = read_member_key(home, 'agent:dsh-t')
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    block = ("- insert:\n    - id: mcp-talk\n      name: '@deepseek-ai/dsh-mcp-client'\n"
             "      config:\n        serverName: 'talk'\n        transport: 'stdio'\n"
             f"        command: {quote(python)}\n        args:\n          - '-X'\n          - 'utf8'\n"
             f"          - {quote(repo / 'bridges/talk_terminal_mcp.py')}\n          - '--project-root'\n          - {quote(repo)}\n"
             f"        cwd: {quote(repo)}\n        env:\n          PYTHONUTF8: '1'\n          TALK_API_KEY: {quote(key)}\n"
             "        failOnStartupError: false\n        toolCallTimeoutMs: 65000\n")
    return original + ('\n' if original and not original.endswith('\n') else '') + block


def write_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup = path.with_name(path.name + '.bak-' + stamp)
        suffix = 0
        while backup.exists():
            suffix += 1
            backup = path.with_name(path.name + '.bak-' + stamp + f'-{suffix}')
        shutil.copy2(path, backup)
    path.write_text(content, encoding='utf-8', newline='')


MEMBER_IDS = tuple(f'agent:{name}-t' for name in ('codex', 'kimi', 'workbuddy', 'dsh', 'antigravity'))


def check_members() -> dict:
    try:
        with urlopen('http://127.0.0.1:8000/api/members', timeout=3) as response:
            members = json.load(response)
        if not isinstance(members, list) or any(not isinstance(item, dict) or not isinstance(item.get('id'), str) for item in members):
            raise ValueError('invalid member response')
        ids = {item['id'] for item in members}
    except Exception:
        # Responses and exception text can contain secrets; report only a fixed status.
        return {'member_status': 'api_unavailable', 'members_ok': [], 'member_missing': []}
    return {'member_status': 'checked', 'members_ok': [i for i in MEMBER_IDS if i in ids],
            'member_missing': [i for i in MEMBER_IDS if i not in ids]}


def run(repo: Path, home: Path, apply: bool, skip_members: bool = False) -> dict:
    repo, home = repo.expanduser().resolve(), home.expanduser().resolve()
    detected = detect(home)
    venv = repo / '.venv/Scripts/python.exe'
    python = str(venv if venv.is_file() else Path(sys.executable).resolve())
    bridge = str(repo / 'bridges/talk_terminal_mcp.py')
    targets = {
        'codex': home / '.codex/config.toml',
        'kimi': repo / '.kimi-code/mcp.json',
        'workbuddy': home / '.workbuddy/mcp.json',
        'dsh': home / '.dsh/profiles/desktop/cordis.patch.yml',
        'antigravity': home / '.gemini/config/mcp_config.json',
    }
    output = {'detected': detected, 'configs_written': [], 'skipped': [], 'errors': []}
    output.update({'member_status': 'skipped', 'members_ok': [], 'member_missing': []} if skip_members else check_members())
    if not apply:
        output['planned'] = []
    for name, path in targets.items():
        if not detected[name]['detected']:
            output['skipped'].append({'client': name, 'reason': 'not_detected'})
            continue
        try:
            original = path.read_text(encoding='utf-8') if path.exists() else ''
            if name == 'dsh':
                updated = yaml_update(original, repo, home, python)
            elif name != 'codex' and _json_talk_state(original)[3]:
                updated = original
            else:
                launcher = str(repo / 'scripts/kimi_talk_mcp_launch.py') if name == 'kimi' else bridge
                env = {'TALK_KIMI_KEY_FILE': str(home / '.talk/agent-kimi.key')} if name == 'kimi' else {'TALK_API_KEY': read_member_key(home, f'agent:{name}-t')}
                if not all(env.values()):
                    raise ValueError('empty key file')
                args = [launcher, '--project-root', str(repo)]
                if name != 'kimi':
                    args = ['-X', 'utf8', *args]
                entry = {'command': python, 'args': args, 'env': env}
                updated = toml_update(original, entry) if name == 'codex' else json_update(original, entry)
            item = {'client': name, 'path': str(path)}
            if updated == original:
                output['skipped'].append({**item, 'reason': 'unchanged'})
            elif apply:
                write_changed(path, updated)
                output['configs_written'].append(item)
            else:
                output['planned'].append(item)
        except KeyMissingError:
            # Detected client without an issued terminal-identity key is unconfigured,
            # not a broken config file; skip it without failing boot readiness.
            output['skipped'].append({'client': name, 'reason': 'key_missing'})
        except (OSError, ValueError, TypeError) as exc:
            # Never include exception text: parser errors can contain configuration secrets.
            output['errors'].append({'client': name, 'reason': type(exc).__name__})
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--skip-members', action='store_true')
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('USERPROFILE') or Path.home()))
    args = parser.parse_args()
    result = run(args.repo, args.home, args.apply, args.skip_members)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
