"""CDP transport tests with a loopback HTTP/WebSocket server."""
import json
import shutil
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from websockets.sync.server import serve
from websockets.exceptions import ConnectionClosed
from bridges.workbuddy_cdp import CdpError, prompt_once
from bridges import workbuddy_bridge
from scripts import workbuddy_acp_models

ROOT = str(Path.cwd())


class FakeCDP:
    def __init__(self, fail=None, missing=False, delay=0, outputs=None, invalid_ws=False,
                 execute_prompt=False, prompt_state='completed', prompt_content=None):
        self.fail, self.missing, self.delay = fail, missing, delay
        self.invalid_ws = invalid_ws
        self.execute_prompt, self.prompt_state, self.prompt_content = execute_prompt, prompt_state, prompt_content
        self.outputs = list(outputs or ['hello'])
        self.messages = []
        self.server = serve(self.handle, '127.0.0.1', 0, process_request=self.http)
        self.port = self.server.socket.getsockname()[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f'http://127.0.0.1:{self.port}'

    def http(self, conn, request):
        if request.path != '/json':
            return None
        targets = [] if self.missing else [{'type': 'page', 'url': 'file:///renderer/index.html',
                    'webSocketDebuggerUrl': (f'ws://example.com:{self.port}/devtools/page/1' if self.invalid_ws else f'ws://127.0.0.1:{self.port}/devtools/page/1')}]
        response = conn.respond(200, json.dumps(targets))
        response.headers['Content-Type'] = 'application/json'
        return response

    def handle(self, ws):
        try:
            for raw in ws:
                msg = json.loads(raw)
                self.messages.append(msg)
                expression = msg['params']['expression']
                kind = ('create' if 'conversations.create' in expression else
                        'config' if 'setPermissionMode' in expression else
                        'prompt' if 'runPrompt' in expression else 'delete')
                if self.delay and kind == 'prompt':
                    time.sleep(self.delay)
                value = {'ok': kind != self.fail}
                if kind == 'prompt' and value['ok']:
                    response = {'clientRequestId': 'client-1', 'requestId': 'request-1',
                                'state': self.prompt_state,
                                'content': self.prompt_content if self.prompt_content is not None else
                                           [{'type': 'text', 'text': self.outputs.pop(0)}],
                                'artifacts': [], 'requestedModel': {'id': 'm', 'name': 'Model'},
                                'responseModel': {'id': 'm'}}
                    if self.execute_prompt:
                        script = ('const response = ' + json.dumps(response) + ';\n'
                                  'global.window = new Proxy({}, {get: () => ({c: {runPrompt: async () => response}})});\n'
                                  '(async () => console.log(JSON.stringify(await eval(' + json.dumps(expression) + '))))();')
                        completed = subprocess.run(['node', '-e', script], capture_output=True, text=True,
                                                   encoding='utf-8', timeout=5, check=True)
                        value = json.loads(completed.stdout)
                    else:
                        value.update(text=response['content'][0]['text'], state=response['state'],
                                     responseModel=response['responseModel'])
                ws.send(json.dumps({'id': msg['id'], 'result': {'result': {'type': 'object', 'value': value}}}))
        except (ConnectionClosed, IndexError):
            pass

    def close(self):
        self.server.shutdown()
        self.thread.join(2)


class CdpTests(unittest.TestCase):
    def setUp(self):
        self.servers = []

    def tearDown(self):
        for server in self.servers:
            server.close()

    def fake(self, **kwargs):
        server = FakeCDP(**kwargs)
        self.servers.append(server)
        return server

    def call(self, server, **kwargs):
        return prompt_once('model-1', 'prompt text', mode='task', project_root=ROOT,
                           endpoint=server.endpoint, timeout=kwargs.pop('timeout', 3), **kwargs)

    def test_success_payload_and_cleanup(self):
        server = self.fake()
        result = self.call(server, effort='high')
        self.assertEqual(result['text'], 'hello')
        self.assertEqual(result['responseModel'], {'id': 'm'})
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(len(server.messages), 4)
        for msg in server.messages:
            self.assertEqual(msg['method'], 'Runtime.evaluate')
            self.assertTrue(msg['params']['awaitPromise'])
            self.assertTrue(msg['params']['returnByValue'])
        expressions = [m['params']['expression'] for m in server.messages]
        self.assertIn('"model-1"', expressions[0])
        self.assertIn('transport:"local"', expressions[0])
        self.assertIn('bypassPermissions', expressions[1])
        self.assertIn('setThoughtLevel("high")', expressions[1])
        self.assertIn('filter(x=>x && x.type==="text"', expressions[2])
        self.assertIn('conversations.delete', expressions[3])

    @unittest.skipUnless(shutil.which('node'), 'Node.js required to execute the CDP expression')
    def test_prompt_expression_with_real_response_shape(self):
        server = self.fake(execute_prompt=True, prompt_content=[
            {'type': 'text', 'text': 'O'}, {'type': 'other', 'text': 'ignored'},
            {'type': 'text', 'text': 'K'}])
        result = self.call(server)
        self.assertEqual(result['text'], 'OK')
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['responseModel'], {'id': 'm'})
        expression = server.messages[2]['params']['expression']
        self.assertNotIn('stopReason', expression)
        self.assertNotIn('usage', expression)

        for state, content in [('failed', [{'type': 'text', 'text': 'bad'}]),
                               ('completed', {'type': 'text', 'text': 'bad'})]:
            with self.subTest(state=state, content=content):
                failed = self.fake(execute_prompt=True, prompt_state=state, prompt_content=content)
                with self.assertRaises(CdpError) as caught:
                    self.call(failed)
                self.assertEqual(caught.exception.code, 'workbuddy_cdp_prompt_failed')
                self.assertIn('conversations.delete', failed.messages[-1]['params']['expression'])

    def test_failure_codes_and_cleanup(self):
        for stage in ('create', 'config', 'prompt'):
            with self.subTest(stage=stage):
                server = self.fake(fail=stage)
                with self.assertRaises(CdpError) as caught:
                    self.call(server)
                self.assertEqual(caught.exception.code, 'workbuddy_cdp_' + stage + '_failed')
                if stage != 'create':
                    self.assertIn('conversations.delete', server.messages[-1]['params']['expression'])

    def test_timeout(self):
        server = self.fake(delay=5)
        start = time.monotonic()
        with self.assertRaises(CdpError) as caught:
            self.call(server, timeout=2)
        self.assertEqual(caught.exception.code, 'workbuddy_cdp_timeout')
        self.assertLess(time.monotonic() - start, 3.0)
        self.assertIn('setTimeout', server.messages[0]['params']['expression'])

    def test_missing_invalid_and_unavailable(self):
        server = self.fake(missing=True)
        with self.assertRaises(CdpError) as caught:
            self.call(server)
        self.assertEqual(caught.exception.code, 'workbuddy_cdp_target_missing')
        for endpoint in ('http://example.com:9222', 'http://127.0.0.1:9222/path'):
            with self.assertRaises(CdpError) as caught:
                prompt_once('m', 't', mode='chat', project_root=ROOT, endpoint=endpoint)
            self.assertEqual(caught.exception.code, 'workbuddy_cdp_invalid_input')
        server.close()
        with self.assertRaises(CdpError) as caught:
            self.call(server)
        self.assertEqual(caught.exception.code, 'workbuddy_cdp_unavailable')

    def test_keep_and_plan(self):
        server = self.fake()
        prompt_once('m', 't', mode='plan', project_root=ROOT, endpoint=server.endpoint, keep_conversation=True)
        self.assertEqual(len(server.messages), 3)
        self.assertIn('setPermissionMode("plan")', server.messages[1]['params']['expression'])

    def test_repair_round(self):
        server = self.fake(outputs=['bad', 'fixed'])
        result = self.call(server, repair_validator=lambda text: text == 'fixed', repair_prompt='repair')
        self.assertEqual(result['text'], 'fixed')
        self.assertEqual(len(server.messages), 5)
        self.assertIn('repair', server.messages[3]['params']['expression'])
        self.assertIn('conversations.delete', server.messages[4]['params']['expression'])

    def test_reject_non_loopback_websocket_target(self):
        server = self.fake(invalid_ws=True)
        with self.assertRaises(CdpError) as caught:
            self.call(server)
        self.assertEqual(caught.exception.code, 'workbuddy_cdp_connect_failed')
        self.assertEqual(server.messages, [])

    def test_adapter_repairs_delivery_in_same_conversation(self):
        report = {'task_id':'624', 'conclusion':'complete', 'completed':['done'],
                  'unfinished':[], 'blocked':[], 'changed_files':[],
                  'baseline':{'ref':'base', 'diff_note':'none'},
                  'verification':[{'check':'test', 'result':'pass', 'evidence':'ok'}],
                  'limitations':[], 'progress_draft':{'summary':'done', 'next':'review'}}
        delivery = json.dumps(report)
        server = self.fake(outputs=['invalid', delivery])
        result = subprocess.run([sys.executable, '-m', 'scripts.workbuddy_cdp_prompt',
            '--model', 'workbuddy-cdp:m', '--mode', 'task', '--project-root', ROOT,
            '--endpoint', server.endpoint, '--delivery-contract', '--expect-task-id', '624'],
            input='task', capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), report)
        self.assertTrue(result.stderr.startswith('[workbuddy-cdp] {'))
        self.assertEqual(len(server.messages), 5)
        self.assertEqual(sum('conversations.create' in m['params']['expression'] for m in server.messages), 1)
        self.assertIn('conversations.delete', server.messages[-1]['params']['expression'])

    def test_bridge_and_registration(self):
        cmd = workbuddy_bridge.build_cdp_command('m', 'task', ROOT)
        cmd, mode = workbuddy_bridge.set_command_effort(cmd, 'high')
        self.assertEqual(mode, 'inserted')
        self.assertEqual(cmd[-2:], ['--effort', 'high'])
        payload = workbuddy_acp_models.choice_payload({'modelId':'m'}, 'cdp')
        self.assertEqual(payload['model_alias'], 'workbuddy-cdp:m')
        self.assertEqual(payload['connection_ref'], 'native-workbuddy-cdp')
        self.assertTrue(payload['model_display_name'].endswith('\uff08\u5185\u7f6e\u00b7\u684c\u9762\uff09'))
