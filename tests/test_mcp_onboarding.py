import json
import io
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
    monkeypatch.setattr(m, 'urlopen', lambda *a, **kw: io.BytesIO(b'[]'))
    repo, home = tmp_path / 'repo', tmp_path / 'home'
    for path in (
        repo / 'bridges/talk_terminal_mcp.py',
        repo / 'scripts/kimi_talk_mcp_launch.py',
        home / '.kimi-code/bin/kimi.exe',
        home / 'AppData/Local/Programs/WorkBuddy/WorkBuddy.exe',
        home / 'AppData/Local/Programs/Antigravity/Antigravity.exe',
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (home / '.codex').mkdir(parents=True)
    (home / '.codex/config.toml').write_text('[other]\nvalue = 5\n', encoding='utf-8')
    (home / '.dsh/profiles/desktop').mkdir(parents=True)
    (home / '.dsh/profiles/desktop/cordis.patch.yml').write_text('- id: other\n  value: 3\n', encoding='utf-8')
    (home / '.gemini/config').mkdir(parents=True)
    (home / '.gemini/config/mcp_config.json').write_text(
        json.dumps({'mcpServers': {'ambient_eye': {'command': 'ambient-eye'}}}) + '\n',
        encoding='utf-8',
    )
    (home / '.talk/keys').mkdir(parents=True)
    for name in ('codex', 'workbuddy', 'dsh', 'antigravity'):
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


@pytest.mark.parametrize('kind', ['desktop_exe', 'agy_exe', 'gemini_dir', 'agy_path'])
def test_detect_antigravity_variants(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(m.shutil, 'which', lambda cmd: '/test/agy' if kind == 'agy_path' and cmd == 'agy' else None)
    if kind == 'desktop_exe':
        p = tmp_path / 'AppData/Local/Programs/Antigravity/Antigravity.exe'
        p.parent.mkdir(parents=True)
        p.touch()
    elif kind == 'agy_exe':
        p = tmp_path / 'AppData/Local/agy/bin/agy.exe'
        p.parent.mkdir(parents=True)
        p.touch()
    elif kind == 'gemini_dir':
        (tmp_path / '.gemini/antigravity').mkdir(parents=True)
    detected = m.detect(tmp_path)
    assert detected['antigravity'] == {'detected': True, 'reason': 'found'}
    for other in ('codex', 'kimi', 'workbuddy', 'dsh'):
        assert not detected[other]['detected']


def test_check_no_write(setup_env):
    repo, home = setup_env
    before = {str(p): p.stat().st_mtime_ns for p in home.rglob('*') if p.is_file()}
    result = m.run(repo, home, False)
    assert len(result['planned']) == 5 and not result['configs_written'] and not result['errors']
    assert before == {str(p): p.stat().st_mtime_ns for p in home.rglob('*') if p.is_file()}
    assert not (repo / '.kimi-code').exists()


def test_apply_all_contents(setup_env):
    repo, home = setup_env
    assert len(m.run(repo, home, True)['configs_written']) == 5
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
    agy_doc = json.loads((home / '.gemini/config/mcp_config.json').read_text(encoding='utf-8'))
    assert agy_doc['mcpServers']['ambient_eye'] == {'command': 'ambient-eye'}
    agy = agy_doc['mcpServers']['talk']
    assert agy['command'] == entry['command']
    assert agy['args'] == entry['args']
    assert agy['env']['TALK_API_KEY'] == 'secret-antigravity'


def test_idempotent_mtime(setup_env):
    repo, home = setup_env
    first = m.run(repo, home, True)
    paths = [Path(x['path']) for x in first['configs_written']]
    times = [p.stat().st_mtime_ns for p in paths]
    second = m.run(repo, home, True)
    assert len(second['skipped']) == 5 and not second['configs_written'] and not second['errors']
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
    before_agy = (home / '.gemini/config/mcp_config.json').read_bytes()
    m.run(repo, home, True)
    backups = list((home / '.codex').glob('config.toml.bak-*'))
    assert len(backups) == 1 and backups[0].read_bytes() == before
    assert len(list((home / '.dsh/profiles/desktop').glob('cordis.patch.yml.bak-*'))) == 1
    agy_backups = list((home / '.gemini/config').glob('mcp_config.json.bak-*'))
    assert len(agy_backups) == 1 and agy_backups[0].read_bytes() == before_agy


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
    assert result['errors'] == []
    assert {'client': 'codex', 'reason': 'key_missing'} in result['skipped']
    assert 'secret-' not in json.dumps(result)


def test_empty_key_file_still_reported_as_error(setup_env, monkeypatch):
    repo, home = setup_env
    (home / '.talk/keys/agent_antigravity_t.key').write_text('   \n', encoding='utf-8')
    result = m.run(repo, home, True)
    assert result['errors'] == [{'client': 'antigravity', 'reason': 'ValueError'}]
    assert 'secret-' not in json.dumps(result)
    monkeypatch.setattr(sys, 'argv', ['mcp_onboarding', '--check', '--skip-members', '--repo', str(repo), '--home', str(home)])
    assert m.main() == 1


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


@pytest.mark.parametrize('url_key', ['url', 'serverUrl'])
def test_antigravity_preserves_http_mcp_config(setup_env, url_key):
    repo, home = setup_env
    path = home / '.gemini/config/mcp_config.json'
    original = json.dumps({'mcpServers': {'talk': {url_key: 'http://127.0.0.1:8000/mcp'}}}, indent=2) + '\n'
    path.write_text(original, encoding='utf-8')
    result = m.run(repo, home, True)
    assert not result['errors']
    assert path.read_text(encoding='utf-8') == original
    assert {'client': 'antigravity', 'path': str(path), 'reason': 'unchanged'} in result['skipped']


@pytest.mark.parametrize('url_key', ['url', 'serverUrl'])
def test_antigravity_http_mcp_config_skips_missing_key(setup_env, url_key):
    repo, home = setup_env
    (home / '.talk/keys/agent_antigravity_t.key').unlink()
    path = home / '.gemini/config/mcp_config.json'
    original = json.dumps({'mcpServers': {'talk': {url_key: 'http://127.0.0.1:8000/mcp'}}}, indent=2) + '\n'
    path.write_text(original, encoding='utf-8')
    result = m.run(repo, home, True)
    assert not result['errors']
    assert path.read_text(encoding='utf-8') == original
    assert {'client': 'antigravity', 'path': str(path), 'reason': 'unchanged'} in result['skipped']


@pytest.mark.parametrize('talk_entry', [
    {'url': ''},
    {'serverUrl': None},
    {'url': '   '},
    {'url': 123},
    {'url': 'http://127.0.0.1:8000/mcp', 'serverUrl': ''},
])
def test_invalid_http_url_rejected_fail_closed(setup_env, talk_entry):
    repo, home = setup_env
    path = home / '.gemini/config/mcp_config.json'
    original = json.dumps({'mcpServers': {'talk': talk_entry}}, indent=2) + '\n'
    path.write_text(original, encoding='utf-8')
    with pytest.raises(ValueError, match='invalid talk object'):
        m.json_update(original, {'command': 'python', 'args': [], 'env': {'TALK_API_KEY': 'k'}})
    result = m.run(repo, home, True)
    assert result['errors'] == [{'client': 'antigravity', 'reason': 'ValueError'}]
    assert path.read_text(encoding='utf-8') == original


def test_antigravity_creates_mcp_config_from_scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(m.shutil, 'which', lambda _: None)
    monkeypatch.setattr(m, 'urlopen', lambda *a, **kw: io.BytesIO(b'[]'))
    repo, home = tmp_path / 'repo', tmp_path / 'home'
    (repo / 'bridges/talk_terminal_mcp.py').parent.mkdir(parents=True)
    (repo / 'bridges/talk_terminal_mcp.py').touch()
    (home / 'AppData/Local/agy/bin').mkdir(parents=True)
    (home / 'AppData/Local/agy/bin/agy.exe').touch()
    (home / '.talk/keys').mkdir(parents=True)
    (home / '.talk/keys/agent_antigravity-t.key').write_text('secret-fresh', encoding='utf-8')
    target = home / '.gemini/config/mcp_config.json'
    assert not target.parent.exists()
    result = m.run(repo, home, True)
    assert not result['errors']
    assert result['configs_written'] == [{'client': 'antigravity', 'path': str(target)}]
    data = json.loads(target.read_text(encoding='utf-8'))
    assert data['mcpServers']['talk']['env']['TALK_API_KEY'] == 'secret-fresh'


@pytest.mark.parametrize('client', ['codex', 'workbuddy', 'dsh', 'antigravity'])
@pytest.mark.parametrize('separator', ['-', '_'])
def test_member_key_names(setup_env, client, separator):
    repo, home = setup_env
    legacy = home / f'.talk/keys/agent_{client}_t.key'
    selected = home / f'.talk/keys/agent_{client}{separator}t.key'
    if selected != legacy:
        legacy.rename(selected)
    result = m.run(repo, home, True)
    assert not result['errors']
    assert {x['client'] for x in result['configs_written']} == {'codex', 'kimi', 'workbuddy', 'dsh', 'antigravity'}


def test_missing_antigravity_key_reported(setup_env):
    repo, home = setup_env
    (home / '.talk/keys/agent_antigravity_t.key').unlink()
    result = m.run(repo, home, False)
    assert result['errors'] == []
    assert {'client': 'antigravity', 'reason': 'key_missing'} in result['skipped']
    assert all(item['client'] != 'antigravity' for item in result['planned'])
    assert 'secret-' not in json.dumps(result)


def test_missing_dsh_key_reported(setup_env):
    repo, home = setup_env
    (home / '.talk/keys/agent_dsh_t.key').unlink()
    result = m.run(repo, home, False)
    assert result['errors'] == []
    assert {'client': 'dsh', 'reason': 'key_missing'} in result['skipped']
    assert all(item['client'] != 'dsh' for item in result['planned'])
    assert 'secret-' not in json.dumps(result)


def test_members_present_and_missing_continue(setup_env, monkeypatch):
    repo, home = setup_env
    calls = []
    def response(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(json.dumps([{'id': member} for member in m.MEMBER_IDS]).encode())
    monkeypatch.setattr(m, 'urlopen', response)
    result = m.run(repo, home, False)
    assert result['members_ok'] == list(m.MEMBER_IDS) and result['member_missing'] == []
    assert calls == [('http://127.0.0.1:8000/api/members', 3)]
    monkeypatch.setattr(m, 'urlopen', lambda *a, **kw: io.BytesIO(b'[{"id":"agent:codex-t"}]'))
    result = m.run(repo, home, True)
    assert result['members_ok'] == ['agent:codex-t']
    assert result['member_missing'] == list(m.MEMBER_IDS[1:])
    assert len(result['configs_written']) == 5


def test_skip_members_does_not_request(setup_env, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('unexpected network request')
    monkeypatch.setattr(m, 'urlopen', fail)
    result = m.run(*setup_env, True, skip_members=True)
    assert result['member_status'] == 'skipped' and len(result['configs_written']) == 5
    monkeypatch.setattr(sys, 'argv', ['mcp_onboarding', '--check', '--skip-members', '--repo', str(setup_env[0]), '--home', str(setup_env[1])])
    assert m.main() == 0


@pytest.mark.parametrize('error', [TimeoutError('secret-network-key'), OSError('secret-network-key')])
def test_unavailable_safe_and_continues(setup_env, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(m, 'urlopen', fail)
    result = m.run(*setup_env, True)
    assert result['member_status'] == 'api_unavailable'
    assert not result['member_missing'] and len(result['configs_written']) == 5
    assert 'secret-' not in json.dumps(result)
