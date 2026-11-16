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
