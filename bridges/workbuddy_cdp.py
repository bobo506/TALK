"""Local WorkBuddy desktop CDP transport; no conversation data is logged."""
from __future__ import annotations

import asyncio
import json
import math
import inspect
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import websockets
from bridges.workbuddy_acp import AcpError, _validate_endpoint


class CdpError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _endpoint(value):
    try:
        return _validate_endpoint(value)
    except AcpError:
        raise CdpError('workbuddy_cdp_invalid_input') from None


def _js(value):
    return json.dumps(value, ensure_ascii=True)


async def _target_url(endpoint, deadline):
    def remaining():
        return max(0.001, deadline - time.monotonic())

    try:
        async with httpx.AsyncClient(timeout=remaining(), trust_env=False, follow_redirects=False) as client:
            response = await client.get(endpoint + '/json')
            response.raise_for_status()
            targets = response.json()
    except httpx.TimeoutException:
        raise CdpError('workbuddy_cdp_timeout') from None
    except (httpx.HTTPError, ValueError):
        raise CdpError('workbuddy_cdp_unavailable') from None
    if not isinstance(targets, list):
        raise CdpError('workbuddy_cdp_target_missing')
    target = next((t for t in targets if isinstance(t, dict) and t.get('type') == 'page'
                   and 'renderer/index.html' in str(t.get('url', ''))), None)
    if not target or not isinstance(target.get('webSocketDebuggerUrl'), str):
        raise CdpError('workbuddy_cdp_target_missing')
    url = target['webSocketDebuggerUrl']
    try:
        parsed, base = urlsplit(url), urlsplit(endpoint)
        if (parsed.scheme != 'ws' or parsed.hostname not in ('localhost', '127.0.0.1')
                or parsed.port != base.port or parsed.username or parsed.password):
            raise ValueError()
    except (TypeError, ValueError):
        raise CdpError('workbuddy_cdp_connect_failed') from None
    return url


async def _run(model_id, text, mode, root, effort, deadline, endpoint, keep, validator, repair_prompt):
    def remaining():
        return max(0.001, deadline - time.monotonic())

    url = await _target_url(endpoint, deadline)
    token = 'talk_' + uuid.uuid4().hex
    counter = 0
    try:
        ws_options = {'proxy': None} if 'proxy' in inspect.signature(websockets.connect).parameters else {}
        async with websockets.connect(url, open_timeout=remaining(), close_timeout=min(0.05, remaining()),
                                      max_size=16 * 1024 * 1024, **ws_options) as ws:
            async def evaluate(expr, error):
                nonlocal counter
                counter += 1
                request_id = counter
                await ws.send(json.dumps({'id': request_id, 'method': 'Runtime.evaluate', 'params': {
                    'expression': expr, 'awaitPromise': True, 'returnByValue': True}}))
                while True:
                    message = json.loads(await ws.recv())
                    if message.get('id') != request_id:
                        continue
                    result = message.get('result', {})
                    if 'error' in message or 'exceptionDetails' in result:
                        raise CdpError(error)
                    value = result.get('result', {}).get('value')
                    if not isinstance(value, dict) or not value.get('ok'):
                        raise CdpError(error)
                    return value

            # The page owns a deadline timer, including when Python times out or disconnects.
            # If create resolves after the deadline, the newly created conversation is deleted.
            create = f'''(async()=>{{
                const key={_js(token)}, expires=Date.now()+{int(remaining()*1000)};
                let c;
                try {{ c=await window.wb.conversations.create({{cwd:{_js(root)},title:"TALK",transport:"local",mode:"craft",model:{_js(model_id)}}});
                    if (!c || !c.info || !c.info.id) return {{ok:false}};
                    const id=c.info.id;
                    if (Date.now() >= expires) {{ await window.wb.conversations.delete(id); return {{ok:false}}; }}
                    const entry={{c,id}}; window[key]=entry;
                    if (!{str(keep).lower()}) entry.timer=setTimeout(async()=>{{try{{await window.wb.conversations.delete(id)}}catch(e){{}} delete window[key]}},Math.max(0,expires-Date.now()));
                    return {{ok:true}};
                }} catch(e) {{ if(c && c.info && c.info.id && !{str(keep).lower()}) try{{await window.wb.conversations.delete(c.info.id)}}catch(_){{}} return {{ok:false}}; }}
            }})()'''
            await evaluate(create, 'workbuddy_cdp_create_failed')
            try:
                config = f'''(async()=>{{try{{const c=window[{_js(token)}].c;
                    await c.configManager.setPermissionMode({_js('bypassPermissions' if mode == 'task' else 'plan')});
                    {'await c.configManager.setThoughtLevel(' + _js(effort) + ');' if effort else ''}
                    return {{ok:true}};}}catch(e){{return {{ok:false}}}}}})()'''
                await evaluate(config, 'workbuddy_cdp_config_failed')
                async def prompt(message):
                    expression = f'''(async()=>{{try{{const r=await window[{_js(token)}].c.runPrompt([{{type:"text",text:{_js(message)}}}],{{emitUserMessage:true}});
                        if(!r || r.state!=="completed" || !Array.isArray(r.content)) return {{ok:false}};
                        return {{ok:true,text:r.content.filter(x=>x && x.type==="text" && typeof x.text==="string").map(x=>x.text).join(""),state:r.state,responseModel:r.responseModel ?? null}};
                    }}catch(e){{return {{ok:false}}}}}})()'''
                    return await evaluate(expression, 'workbuddy_cdp_prompt_failed')
                result = await prompt(text)
                if validator and repair_prompt and not validator(result['text']):
                    try:
                        repaired = await prompt(repair_prompt)
                        if validator(repaired['text']):
                            result = repaired
                    except CdpError:
                        pass
                return result
            finally:
                if not keep:
                    # A bounded best effort; the page timer remains armed if this fails.
                    try:
                        await asyncio.wait_for(evaluate(f'''(async()=>{{try{{const e=window[{_js(token)}]; if(e){{await window.wb.conversations.delete(e.id);clearTimeout(e.timer);delete window[{_js(token)}]}} return {{ok:true}}}}catch(_){{return {{ok:false}}}}}})()''', 'workbuddy_cdp_prompt_failed'), timeout=remaining())
                    except Exception:
                        pass
    except CdpError:
        raise
    except (OSError, websockets.exceptions.WebSocketException, ValueError, KeyError):
        raise CdpError('workbuddy_cdp_connect_failed') from None


def prompt_once(model_id, text, *, mode, project_root, effort=None, timeout=600, endpoint=None,
                keep_conversation=False, repair_validator=None, repair_prompt=None):
    started = time.monotonic()
    if (not isinstance(model_id, str) or not model_id.strip() or not isinstance(text, str) or not text.strip()
            or mode not in ('chat', 'plan', 'task') or (effort is not None and effort not in ('low', 'high', 'max'))
            or isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0):
        raise CdpError('workbuddy_cdp_invalid_input')
    try:
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise ValueError()
    except (TypeError, ValueError, OSError):
        raise CdpError('workbuddy_cdp_invalid_input') from None
    address = _endpoint(endpoint or os.environ.get('TALK_WORKBUDDY_CDP_ENDPOINT') or 'http://127.0.0.1:9222')
    async def run():
        try:
            return await asyncio.wait_for(_run(model_id, text, mode, str(root), effort, started + timeout,
                                               address, keep_conversation, repair_validator, repair_prompt), timeout)
        except asyncio.TimeoutError:
            raise CdpError('workbuddy_cdp_timeout') from None
    result = asyncio.run(run())
    return {**result, 'modelId': model_id, 'elapsed': time.monotonic() - started}


def list_models(timeout=10, endpoint=None):
    """Read the desktop model catalog within one bounded loopback CDP request."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise CdpError('workbuddy_cdp_invalid_input')
    address = _endpoint(endpoint or os.environ.get('TALK_WORKBUDDY_CDP_ENDPOINT') or 'http://127.0.0.1:9222')
    deadline = time.monotonic() + timeout

    async def run():
        url = await _target_url(address, deadline)
        remaining = max(0.001, deadline - time.monotonic())
        options = {'proxy': None} if 'proxy' in inspect.signature(websockets.connect).parameters else {}
        try:
            async with websockets.connect(url, open_timeout=remaining, close_timeout=min(0.05, remaining), max_size=16 * 1024 * 1024, **options) as ws:
                expression = '''(async()=>{try{const r=await window.wb.models.list(); if(!r || !Array.isArray(r.items)) return {ok:false}; return {ok:true,models:r.items.map(m=>({model_id:m.id,name:m.name,supported_efforts:m.reasoning?.supportedEfforts ?? [],default_effort:m.reasoning?.defaultEffort ?? null}))}}catch(e){return {ok:false}}})()'''
                await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {'expression': expression, 'awaitPromise': True, 'returnByValue': True}}))
                while True:
                    message = json.loads(await ws.recv())
                    if message.get('id') != 1:
                        continue
                    result = message.get('result', {})
                    value = result.get('result', {}).get('value')
                    if 'error' in message or 'exceptionDetails' in result or not isinstance(value, dict) or not value.get('ok') or not isinstance(value.get('models'), list):
                        raise CdpError('workbuddy_cdp_models_failed')
                    return value['models']
        except CdpError:
            raise
        except (OSError, websockets.exceptions.WebSocketException, ValueError, KeyError, TypeError):
            raise CdpError('workbuddy_cdp_connect_failed') from None

    async def bounded():
        try:
            return await asyncio.wait_for(run(), timeout)
        except asyncio.TimeoutError:
            raise CdpError('workbuddy_cdp_timeout') from None
    return asyncio.run(bounded())
