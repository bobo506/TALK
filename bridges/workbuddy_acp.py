"""Local WorkBuddy ACP client. Credentials and stream contents stay in memory."""
from __future__ import annotations
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx

PREFIX = "workbuddy-acp:"
_endpoint = None

class AcpError(Exception):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)

def is_acp_alias(value):
    return isinstance(value, str) and value.startswith(PREFIX) and len(value) > len(PREFIX)

def parse_acp_alias(value):
    if not is_acp_alias(value):
        raise AcpError("workbuddy_acp_invalid_model")
    return value[len(PREFIX):]

def acp_alias(model_id):
    if not isinstance(model_id, str) or not model_id or model_id.startswith(PREFIX):
        raise AcpError("workbuddy_acp_invalid_model")
    return PREFIX + model_id

def _validate_endpoint(endpoint):
    try:
        u = urlsplit(endpoint)
        if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost') or not u.port or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
            raise ValueError()
        return endpoint.rstrip('/')
    except (ValueError, TypeError):
        raise AcpError('workbuddy_acp_runtime_unavailable') from None

def _candidate_ports():
    try:
        task = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq WorkBuddy.exe', '/FO', 'CSV', '/NH'], text=True, errors='replace', stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        import csv
        pids = {row[1] for row in csv.reader(task.splitlines()) if len(row) > 1 and row[0].lower() == 'workbuddy.exe'}
    except (OSError, subprocess.SubprocessError):
        pids = set()
    try:
        net = subprocess.check_output(['netstat', '-ano'], text=True, errors='replace', stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        ports = []
        for line in net.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == 'TCP' and parts[1].startswith('127.0.0.1:') and parts[2] == '0.0.0.0:0' and (not pids or parts[4] in pids):
                ports.append(int(parts[1].rsplit(':', 1)[1]))
        return list(dict.fromkeys(ports))
    except (OSError, subprocess.SubprocessError, ValueError):
        return []

def discover_endpoint():
    global _endpoint
    override = os.environ.get('TALK_WORKBUDDY_ACP_ENDPOINT')
    if override:
        return _validate_endpoint(override)
    if _endpoint:
        return _endpoint
    for port in _candidate_ports():
        endpoint = f'http://127.0.0.1:{port}'
        try:
            with httpx.Client(trust_env=False, timeout=0.8) as client:
                response = client.post(endpoint + '/api/v1/acp/connect', headers={'X-CodeBuddy-Request':'1'}, json={})
                data = response.json()
                if response.status_code == 200 and isinstance(data, dict) and data.get('connectionId') and data.get('sessionToken'):
                    headers = {'X-CodeBuddy-Request':'1', 'acp-connection-id':data['connectionId'], 'acp-session-token':data['sessionToken'], 'Accept':'application/json, text/event-stream'}
                    try:
                        client.delete(endpoint + '/api/v1/acp', headers=headers)
                    except httpx.HTTPError:
                        pass
                    _endpoint = endpoint
                    return endpoint
        except (httpx.HTTPError, ValueError, TypeError):
            continue
    raise AcpError('workbuddy_acp_runtime_unavailable')

class _Client:
    def __init__(self, endpoint, timeout):
        self.endpoint = _validate_endpoint(endpoint) if endpoint else discover_endpoint()
        self.client = httpx.Client(trust_env=False, timeout=timeout)
        self.headers = {'X-CodeBuddy-Request':'1', 'Accept':'application/json, text/event-stream'}
        self.counter = 0
        self.connected = False
    def connect(self):
        try:
            r = self.client.post(self.endpoint + '/api/v1/acp/connect', headers=self.headers, json={})
            r.raise_for_status(); data = r.json()
            if not data.get('connectionId') or not data.get('sessionToken'):
                raise ValueError()
            self.headers.update({'acp-connection-id':data['connectionId'], 'acp-session-token':data['sessionToken']})
            self.connected = True
        except httpx.TimeoutException:
            raise AcpError('workbuddy_acp_timeout') from None
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            raise AcpError('workbuddy_acp_connect_failed') from None
    def disconnect(self):
        try:
            if self.connected:
                r = self.client.delete(self.endpoint + '/api/v1/acp', headers=self.headers)
                r.raise_for_status()
        except httpx.HTTPError:
            raise AcpError('workbuddy_acp_disconnect_failed') from None
        finally:
            self.client.close()
    def rpc(self, method, params, code, session=None):
        self.counter += 1; request_id = self.counter
        chunks = []; usage = None; result = None; found = False
        try:
            with self.client.stream('POST', self.endpoint + '/api/v1/acp', headers=self.headers, json={'jsonrpc':'2.0','id':request_id,'method':method,'params':params}) as response:
                response.raise_for_status()
                content_type = response.headers.get('content-type', '')
                if 'text/event-stream' not in content_type:
                    raise ValueError()
                data_lines = []
                def handle(raw):
                    nonlocal result, found, usage
                    obj = json.loads(raw)
                    if not isinstance(obj, dict): raise ValueError()
                    if obj.get('method') and 'id' in obj:
                        reply = {'jsonrpc':'2.0','id':obj['id']}
                        if obj['method'] == 'session/request_permission':
                            reply['result'] = {'outcome':{'outcome':'cancelled'}}
                        else:
                            reply['error'] = {'code':-32601,'message':'Method not found'}
                        rr = self.client.post(self.endpoint + '/api/v1/acp', headers=self.headers, json=reply)
                        rr.raise_for_status()
                    elif obj.get('method') == 'session/update':
                        p = obj.get('params') or {}
                        if session is not None and p.get('sessionId') == session:
                            update = p.get('update') or {}
                            if update.get('sessionUpdate') == 'agent_message_chunk':
                                content = update.get('content') or {}
                                if content.get('type') == 'text' and isinstance(content.get('text'), str): chunks.append(content['text'])
                            if update.get('sessionUpdate') == 'usage_update':
                                usage = (update.get('_meta') or {}).get('usage')
                    elif obj.get('id') == request_id:
                        if 'error' in obj or not isinstance(obj.get('result'), dict): raise ValueError()
                        result = obj['result']; found = True
                for line in response.iter_lines():
                    if not line:
                        if data_lines:
                            handle('\n'.join(data_lines)); data_lines = []
                    elif line.startswith('data:'):
                        data_lines.append(line[5:].lstrip())
                    elif not line.startswith((':', 'event:', 'id:', 'retry:')):
                        raise ValueError()
                if data_lines: handle('\n'.join(data_lines))
                if not found: raise ValueError()
                return result, ''.join(chunks), usage
        except httpx.TimeoutException:
            raise AcpError('workbuddy_acp_timeout') from None
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError):
            raise AcpError(code) from None
    def initialize(self):
        self.rpc('initialize', {'protocolVersion':1,'clientCapabilities':{'fs':{'readTextFile':False,'writeTextFile':False},'terminal':False},'clientInfo':{'name':'TALK','version':'1'}}, 'workbuddy_acp_initialize_failed')
    def new(self, root):
        return self.rpc('session/new', {'cwd':str(root),'mcpServers':[]}, 'workbuddy_acp_session_failed')[0]
    def configure(self, session, key, value):
        code = 'workbuddy_acp_' + key + '_not_applied'
        result = self.rpc('session/set_config_option', {'sessionId':session,'configId':key,'value':value}, code)[0]
        options = result.get('configOptions') or []
        if not any(x.get('id') == key and x.get('currentValue') == value for x in options if isinstance(x, dict)):
            raise AcpError(code)

def _root(project_root):
    path = Path(project_root).resolve()
    if not path.is_dir(): raise AcpError('workbuddy_acp_invalid_project_root')
    return path

def prompt_once(model_id, text, *, mode, project_root, effort=None, timeout=600, endpoint=None):
    if not model_id or mode not in ('chat','plan','task') or not isinstance(text,str) or not text.strip():
        raise AcpError('workbuddy_acp_invalid_input')
    root = _root(project_root); started = time.monotonic(); client = _Client(endpoint, timeout)
    try:
        client.connect(); client.initialize()
        first = client.new(root).get('sessionId'); second = client.new(root).get('sessionId')
        if not isinstance(first, str) or not first or not isinstance(second, str) or not second or first == second:
            raise AcpError('workbuddy_acp_session_bind_failed')
        client.configure(second, 'model', model_id)
        client.configure(second, 'mode', 'bypassPermissions' if mode == 'task' else 'plan')
        if effort: client.configure(second, 'thought_level', effort)
        if mode == 'task':
            safe_root = str(root).replace('"', '`"')
            text = f'项目根目录为 {root}。进程默认 cwd 不是本项目。所有 Shell 命令先执行 Set-Location -LiteralPath "{safe_root}"（cmd 使用 cd /d "{root}"）；文件工具使用绝对路径，不要读写项目根之外。\n\n' + text
        result, output, usage = client.rpc('session/prompt', {'sessionId':second,'prompt':[{'type':'text','text':text}]}, 'workbuddy_acp_prompt_failed', second)
        if result.get('stopReason') != 'end_turn': raise AcpError('workbuddy_acp_prompt_failed')
        return {'text':output,'usage':usage,'stopReason':result['stopReason'],'modelId':model_id,'sessionId':second,'elapsed':time.monotonic()-started}
    finally:
        try:
            client.disconnect()
        except AcpError:
            # Never replace a completed result or an earlier failure.
            pass

def list_models(endpoint=None, include_custom=False):
    client = _Client(endpoint, 30)
    try:
        client.connect(); client.initialize(); result = client.new(Path.cwd())
        models = (result.get('models') or {}).get('availableModels') or []
        return [{k: m[k] for k in ('modelId','name','description','_meta') if k in m} for m in models if isinstance(m,dict) and isinstance(m.get('modelId'),str) and (include_custom or not m['modelId'].startswith('custom-local:'))]
    finally:
        client.disconnect()


def probe_effort_options(model_id, *, timeout=60, endpoint=None):
    """Probe model capabilities without prompting; failures raise AcpError.

    Only the second new session is configured. Unknown or unavailable options
    return an empty list, and the model-default value is excluded.
    """
    if not isinstance(model_id, str) or not model_id.strip():
        raise AcpError('workbuddy_acp_invalid_model')
    client = _Client(endpoint, timeout)
    try:
        client.connect(); client.initialize()
        first = client.new(Path.cwd()).get('sessionId')
        second = client.new(Path.cwd()).get('sessionId')
        if not isinstance(first, str) or not first or not isinstance(second, str) or not second or first == second:
            raise AcpError('workbuddy_acp_session_bind_failed')
        result = client.rpc('session/set_config_option', {'sessionId': second, 'configId': 'model', 'value': model_id}, 'workbuddy_acp_model_not_applied')[0]
        configs = result.get('configOptions') or []
        if not any(isinstance(x, dict) and x.get('id') == 'model' and x.get('currentValue') == model_id for x in configs):
            raise AcpError('workbuddy_acp_model_not_applied')
        values = set()
        for config in configs:
            if isinstance(config, dict) and config.get('id') == 'thought_level':
                for option in config.get('options') or []:
                    if isinstance(option, dict) and isinstance(option.get('value'), str):
                        values.add(option['value'])
        return [v for v in ('off', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra') if v in values]
    finally:
        try:
            client.disconnect()
        except AcpError:
            pass
