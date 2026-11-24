import json
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import server.main as main


def test_status_without_launcher_and_loading(tmp_path):
    with patch.dict(os.environ, {'TALK_CONFIG': str(tmp_path / 'config.toml')}):
        client = TestClient(main.app)
        response = client.get('/api/boot/status')
        assert response.status_code == 200
        assert response.json()['launcher'] is None
        assert response.json()['runners'] == {'detected': [], 'none': True, 'source': 'unknown'}
        assert response.json()['ready'] and response.json()['service_ready']
        page = client.get('/loading')
        assert page.status_code == 200 and all(marker in page.text for marker in ('progressbar', 'runner-none', 'runner-detected', 'loading-steps', 'step-chip'))


def test_status_filters_sensitive_fields(tmp_path):
    path = tmp_path / 'logs/launcher/boot-status.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'ts':'2026-11-16T12:00:00+00:00', 'detected':['codex', 'secret-key'], 'members_ok':['agent:codex-t'], 'member_missing':[], 'configs_written':['codex', 'C:/private'], 'skipped':['kimi'], 'ready':True, 'download':{'needed':False, 'text':'无需下载'}, 'key':'secret-key', 'path':'C:/private'}), encoding='utf-8')
    with patch.dict(os.environ, {'TALK_CONFIG': str(tmp_path / 'config.toml')}):
        data = TestClient(main.app).get('/api/boot/status').json()
    assert data['launcher']['detected'] == ['codex']
    assert data['runners'] == {'detected': ['codex'], 'none': False, 'source': 'launcher'}
    assert data['launcher']['configs_written'] == ['codex']
    assert data['launcher']['download']['text'] == '无需下载'
    assert data['ready'] and len(data['stages']) == 6
    assert 'secret-key' not in str(data) and 'C:/private' not in str(data)


def test_invalid_and_failed_status(tmp_path):
    path = tmp_path / 'logs/launcher/boot-status.json'
    path.parent.mkdir(parents=True)
    with patch.dict(os.environ, {'TALK_CONFIG': str(tmp_path / 'config.toml')}):
        client = TestClient(main.app)
        for payload in ('{', json.dumps({'ready': False, 'error':'secret-key'})):
            path.write_text(payload, encoding='utf-8')
            data = client.get('/api/boot/status').json()
            assert not data['ready'] and 'secret-key' not in str(data)


def test_loading_allows_continue_when_launcher_warns():
    page = (Path(__file__).resolve().parents[1] / 'web/loading.html').read_text(encoding='utf-8')
    assert "data.service_ready===true && launcher && launcher.ready===false" in page
    assert '可继续使用' in page and '继续进入' in page
    assert 'finish(5000)' in page and 'continueButton.onclick' in page
    assert "if(!data.service_ready)" in page


def test_member_status_is_filtered(tmp_path):
    path = tmp_path / 'logs/launcher/boot-status.json'
    path.parent.mkdir(parents=True)
    with patch.dict(os.environ, {'TALK_CONFIG': str(tmp_path / 'config.toml')}):
        for value, expected in [('api_unavailable', 'api_unavailable'), ('secret', 'unknown')]:
            path.write_text(json.dumps({'ready': True, 'member_status': value}), encoding='utf-8')
            assert TestClient(main.app).get('/api/boot/status').json()['launcher']['member_status'] == expected


def test_status_with_utf8_bom(tmp_path):
    path = tmp_path / 'logs/launcher/boot-status.json'
    path.parent.mkdir(parents=True)
    payload = {'ts': '2026-11-16T12:00:00+00:00', 'ready': True,
               'detected': ['codex'], 'members_ok': ['agent:codex-t'],
               'member_status': 'checked'}
    path.write_text(json.dumps(payload), encoding='utf-8-sig')
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')
    with patch.dict(os.environ, {'TALK_CONFIG': str(tmp_path / 'config.toml')}):
        response = TestClient(main.app).get('/api/boot/status')
    assert response.status_code == 200
    data = response.json()
    assert data['ready'] is True and data['launcher']['ready'] is True
    for field, value in payload.items():
        assert data['launcher'][field] == value
    assert 'error' not in data['launcher'] and 'warning' not in data['launcher']
    assert all(stage['state'] != 'error' for stage in data['stages'])


def test_status_accepts_antigravity_and_ui_labels(tmp_path):
    path = tmp_path / 'logs/launcher/boot-status.json'
    path.parent.mkdir(parents=True)
    payload = {
        'ts': '2026-11-24T12:00:00+00:00',
        'ready': True,
        'detected': ['codex', 'antigravity', 'secret-token'],
        'members_ok': ['agent:antigravity-t', 'agent:unknown-t'],
        'member_missing': [],
        'configs_written': ['antigravity', 'C:/secret'],
        'skipped': ['codex'],
        'member_status': 'checked',
    }
    path.write_text(json.dumps(payload), encoding='utf-8')
    with patch.dict(os.environ, {'TALK_CONFIG': str(tmp_path / 'config.toml')}):
        data = TestClient(main.app).get('/api/boot/status').json()
    assert data['launcher']['detected'] == ['codex', 'antigravity']
    assert data['launcher']['members_ok'] == ['agent:antigravity-t']
    assert data['launcher']['configs_written'] == ['antigravity']
    assert data['runners'] == {'detected': ['codex', 'antigravity'], 'none': False, 'source': 'launcher'}
    assert 'secret-token' not in str(data) and 'C:/secret' not in str(data)
    root = Path(__file__).resolve().parents[1]
    assert "antigravity:'Antigravity'" in (root / 'web/loading.html').read_text(encoding='utf-8')
    assert 'antigravity: "Antigravity"' in (root / 'web/app.js').read_text(encoding='utf-8')
