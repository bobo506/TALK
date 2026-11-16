from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from server.db import get_session
from server.routes import local_shutdown


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(local_shutdown.router)
    app.dependency_overrides[get_session] = lambda: None
    monkeypatch.setattr(local_shutdown.db, 'AUTH_MODE', 'trusted')
    monkeypatch.setattr(local_shutdown.db, 'TRUSTED_NETWORKS', ('loopback',))
    monkeypatch.setattr(local_shutdown, 'resolve_transport_member', lambda *args: SimpleNamespace(
        id='human:operator', kind='human', disabled_at=None))
    return TestClient(app)


def test_operator_and_repeat(client, monkeypatch, tmp_path):
    marker = tmp_path / 'private-marker'
    monkeypatch.setenv('TALK_API_CONTROL_FILE', str(marker))
    for _ in range(2):
        response = client.post('/api/local/shutdown')
        assert response.status_code == 202
        assert response.json() == {'status': 'stopping'}
        assert str(marker) not in response.text
        assert marker.read_text(encoding='utf-8') == 'stop'


def test_key_and_non_loopback_are_forbidden(client, monkeypatch, tmp_path):
    marker = tmp_path / 'marker'
    monkeypatch.setenv('TALK_API_CONTROL_FILE', str(marker))
    assert client.post('/api/local/shutdown', headers={'X-API-Key': 'agent-key'}).status_code == 403
    remote = TestClient(client.app, client=('192.168.1.12', 1234))
    assert remote.post('/api/local/shutdown').status_code == 403
    assert not marker.exists()


def test_unavailable_and_unrecognized(client, monkeypatch):
    monkeypatch.delenv('TALK_API_CONTROL_FILE', raising=False)
    response = client.post('/api/local/shutdown')
    assert response.status_code == 409
    assert response.json() == {'detail': 'shutdown_unavailable'}
    monkeypatch.setattr(local_shutdown, 'resolve_transport_member', lambda *args: None)
    assert client.post('/api/local/shutdown').status_code == 403


def test_unwritable_control_hides_path(client, monkeypatch, tmp_path):
    marker = tmp_path / 'missing' / 'private-marker'
    monkeypatch.setenv('TALK_API_CONTROL_FILE', str(marker))
    response = client.post('/api/local/shutdown')
    assert response.status_code == 409
    assert str(marker) not in response.text
