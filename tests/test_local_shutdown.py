from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from server.db import get_session
from server.routes import local_shutdown


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(local_shutdown.router)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE agent_tasks (id INTEGER PRIMARY KEY, status TEXT, project_id TEXT)'))
    def get_test_session():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = get_test_session
    app.state.engine = engine
    monkeypatch.delenv('TALK_RUNTIME_CONFIG', raising=False)
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
        assert response.json() == {'status': 'stopping', 'runtime': False}
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


def test_running_tasks_refuse_all_shutdown_actions(client, monkeypatch, tmp_path):
    marker = tmp_path / 'marker'
    monkeypatch.setenv('TALK_API_CONTROL_FILE', str(marker))
    monkeypatch.setenv('TALK_RUNTIME_CONFIG', str(tmp_path / 'runtime.json'))
    calls = []
    monkeypatch.setattr(local_shutdown.subprocess, 'Popen', lambda *a, **kw: calls.append((a, kw)))
    with client.app.state.engine.begin() as connection:
        connection.execute(text("INSERT INTO agent_tasks VALUES (1, 'queued', 'a'), (2, 'running', 'a'), (3, 'running', 'b')"))
    response = client.post('/api/local/shutdown')
    assert response.status_code == 409
    assert response.json()['detail'] == {'code': 'tasks_running', 'task_ids': [2, 3], 'message': '有任务执行中，请等待结束后再退出服务'}
    assert not marker.exists()
    assert not calls


def test_runtime_stop_spawn_and_marker(client, monkeypatch, tmp_path):
    marker = tmp_path / 'marker'
    config = str(tmp_path / 'runtime.json')
    monkeypatch.setenv('TALK_API_CONTROL_FILE', str(marker))
    monkeypatch.setenv('TALK_RUNTIME_CONFIG', config)
    calls = []
    def spawn(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(wait=lambda: 0)
    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target
            assert daemon
        def start(self):
            self.target()
    monkeypatch.setattr(local_shutdown.subprocess, 'Popen', spawn)
    monkeypatch.setattr(local_shutdown.threading, 'Thread', ImmediateThread)
    response = client.post('/api/local/shutdown')
    assert response.status_code == 202
    assert response.json() == {'status': 'stopping', 'runtime': True}
    argv, options = calls[0]
    assert argv == [local_shutdown.sys.executable, '-B', '-X', 'utf8', '-m', 'scripts.talk_runtime', 'stop', '--config', config, '--apply', '--wait']
    assert options['cwd'] == local_shutdown.Path(local_shutdown.__file__).resolve().parents[2]
    assert options['close_fds'] is True
    if local_shutdown.os.name == 'nt':
        assert options['creationflags'] == local_shutdown.subprocess.DETACHED_PROCESS | local_shutdown.subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert options['start_new_session'] is True
    assert marker.read_text(encoding='utf-8') == 'stop'


def test_runtime_spawn_failure_does_not_write(client, monkeypatch, tmp_path):
    marker = tmp_path / 'marker'
    monkeypatch.setenv('TALK_API_CONTROL_FILE', str(marker))
    monkeypatch.setenv('TALK_RUNTIME_CONFIG', str(tmp_path / 'runtime.json'))
    def fail(*args, **kwargs):
        raise OSError('private detail')
    monkeypatch.setattr(local_shutdown.subprocess, 'Popen', fail)
    response = client.post('/api/local/shutdown')
    assert response.status_code == 409
    assert response.json() == {'detail': 'shutdown_unavailable'}
    assert not marker.exists()
