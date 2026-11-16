import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib

import pytest

from scripts import mcp_onboarding as m


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    monkeypatch.setattr(m.shutil, 'which', lambda _: None)
    repo, home = tmp_path / 'repo', tmp_path / 'home'
    for path in (repo / 'bridges/talk_terminal_mcp.py', repo / 'scripts/kimi_talk_mcp_launch.py', home / '.kimi-code/bin/kimi.exe', home / 'AppData/Local/Programs/WorkBuddy/WorkBuddy.exe'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (home / '.codex').mkdir(parents=True)
    (home / '.codex/config.toml').write_text('[other]\nvalue = 5\n', encoding='utf-8')
    (home / '.dsh/profiles/desktop').mkdir(parents=True)
    (home / '.dsh/profiles/desktop/cordis.patch.yml').write_text('- id: other\n  value: 3\n', encoding='utf-8')
    (home / '.talk/keys').mkdir(parents=True)
    for name in ('codex', 'workbuddy', 'dsh'):
        (home / f'.talk/keys/agent_{name}_t.key').write_text('secret-' + name, encoding='utf-8')
    return repo, home


def test_detect_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(m.shutil, 'which', lambda _: None)
    assert all(not x['detected'] and x['reason'] == 'not_found' for x in m.detect(tmp_path).values())


def test_detect_all(setup_env):
    assert all(x['detected'] and x['reason'] == 'found' for x in m.detect(setup_env[1]).values())


def test_detect_kimi_path(tmp_path, monkeypatch):
    monkeypatch.setattr(m.shutil, 'which', lambda _: '/test/kimi')
    assert m.detect(tmp_path)['kimi']['detected']


def test_check_no_write(setup_env):
    repo, home = setup_env
    before = {str(p): p.stat().st_mtime_ns for p in home.rglob('*') if p.is_file()}
    result = m.run(repo, home, False)
    assert len(result['planned']) == 4 and not result['configs_written'] and not result['errors']
    assert before == {str(p): p.stat().st_mtime_ns for p in home.rglob('*') if p.is_file()}
    assert not (repo / '.kimi-code').exists()


def test_apply_all_contents(setup_env):
    repo, home = setup_env
    assert len(m.run(repo, home, True)['configs_written']) == 4
    codex = tomllib.loads((home / '.codex/config.toml').read_text(encoding='utf-8'))
    assert codex['other']['value'] == 5
    entry = codex['mcp_servers']['talk']
    assert entry['env']['TALK_API_KEY'] == 'secret-codex' and entry['args'] == ['-X', 'utf8', str(repo / 'bridges/talk_terminal_mcp.py'), '--project-root', str(repo)]
    kimi = json.loads((repo / '.kimi-code/mcp.json').read_text(encoding='utf-8'))['mcpServers']['talk']
    assert kimi['args'] == [str(repo / 'scripts/kimi_talk_mcp_launch.py'), '--project-root', str(repo)]
    assert kimi['env']['TALK_KIMI_KEY_FILE'] == str(home / '.talk/agent-kimi.key')
    wb = json.loads((home / '.workbuddy/mcp.json').read_text(encoding='utf-8'))['mcpServers']['talk']
    assert wb['env']['TALK_API_KEY'] == 'secret-workbuddy' and wb['args'][2] == entry['args'][2]
    dsh = (home / '.dsh/profiles/desktop/cordis.patch.yml').read_text(encoding='utf-8')
    assert '- id: other' in dsh and '- insert:' in dsh and 'id: mcp-talk' in dsh
    assert f"command: '{entry['command']}'" in dsh
    assert f"- '-X'\n          - 'utf8'\n          - '{entry['args'][2]}'\n          - '--project-root'\n          - '{repo}'" in dsh
    assert "TALK_API_KEY: 'secret-dsh'" in dsh and 'failOnStartupError: false' in dsh


def test_idempotent_mtime(setup_env):
    repo, home = setup_env
    first = m.run(repo, home, True)
    paths = [Path(x['path']) for x in first['configs_written']]
    times = [p.stat().st_mtime_ns for p in paths]
    second = m.run(repo, home, True)
    assert len(second['skipped']) == 4 and not second['configs_written'] and not second['errors']
    assert times == [p.stat().st_mtime_ns for p in paths]


def test_merge_existing(setup_env):
    repo, home = setup_env
    (home / '.codex/config.toml').write_text('[mcp_servers.talk]\ncommand = "old"\nargs = ["old"]\nextra = true\n[mcp_servers.talk.env]\nOTHER = "keep"\nTALK_API_KEY = "old"\n', encoding='utf-8')
    (repo / '.kimi-code').mkdir()
    (repo / '.kimi-code/mcp.json').write_text(json.dumps({'extra': 2, 'mcpServers': {'other': {}, 'talk': {'enabled': True, 'env': {'KEEP': 'yes'}}}}), encoding='utf-8')
    assert not m.run(repo, home, True)['errors']
    data = tomllib.loads((home / '.codex/config.toml').read_text(encoding='utf-8'))['mcp_servers']['talk']
    assert data['extra'] and data['env']['OTHER'] == 'keep'
    data = json.loads((repo / '.kimi-code/mcp.json').read_text(encoding='utf-8'))
    assert data['extra'] == 2 and 'other' in data['mcpServers'] and data['mcpServers']['talk']['env']['KEEP'] == 'yes'


def test_no_key_output(setup_env, capsys):
    repo, home = setup_env
    assert 'secret-' not in json.dumps(m.run(repo, home, True))


def test_backup(setup_env):
    repo, home = setup_env
    before = (home / '.codex/config.toml').read_bytes()
    m.run(repo, home, True)
    backups = list((home / '.codex').glob('config.toml.bak-*'))
    assert len(backups) == 1 and backups[0].read_bytes() == before
    assert len(list((home / '.dsh/profiles/desktop').glob('cordis.patch.yml.bak-*'))) == 1


def test_existing_dsh_skipped(setup_env):
    repo, home = setup_env
    path = home / '.dsh/profiles/desktop/cordis.patch.yml'
    original = '- insert:\n    - id: mcp-talk\n      config: {}\n'
    path.write_text(original, encoding='utf-8')
    m.run(repo, home, True)
    assert path.read_text(encoding='utf-8') == original


def test_missing_key_reported_without_secret(setup_env):
    repo, home = setup_env
    (home / '.talk/keys/agent_codex_t.key').unlink()
    result = m.run(repo, home, True)
    assert result['errors'] == [{'client': 'codex', 'reason': 'key_missing'}]
    assert 'secret-' not in json.dumps(result)


def test_unsupported_toml_preserved(setup_env):
    repo, home = setup_env
    path = home / '.codex/config.toml'
    original = 'mcp_servers = { talk = { command = "old", args = [], env = {} } }\n'
    path.write_text(original, encoding='utf-8')
    result = m.run(repo, home, True)
    assert result['errors'] and path.read_text(encoding='utf-8') == original


def test_existing_json_same_semantics_unchanged(setup_env):
    repo, home = setup_env
    m.run(repo, home, True)
    path = repo / '.kimi-code/mcp.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    compact = json.dumps(data)
    path.write_text(compact, encoding='utf-8')
    m.run(repo, home, True)
    assert path.read_text(encoding='utf-8') == compact


@pytest.mark.parametrize('client', ['codex', 'workbuddy', 'dsh'])
@pytest.mark.parametrize('separator', ['-', '_'])
def test_member_key_names(setup_env, client, separator):
    repo, home = setup_env
    legacy = home / f'.talk/keys/agent_{client}_t.key'
    selected = home / f'.talk/keys/agent_{client}{separator}t.key'
    if selected != legacy:
        legacy.rename(selected)
    result = m.run(repo, home, True)
    assert not result['errors']
    assert {x['client'] for x in result['configs_written']} == {'codex', 'kimi', 'workbuddy', 'dsh'}


def test_missing_dsh_key_reported(setup_env):
    repo, home = setup_env
    (home / '.talk/keys/agent_dsh_t.key').unlink()
    result = m.run(repo, home, False)
    assert result['errors'] == [{'client': 'dsh', 'reason': 'key_missing'}]
    assert 'secret-' not in json.dumps(result)
