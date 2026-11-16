from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
CLIENTS = {'codex', 'kimi', 'workbuddy', 'dsh'}
MEMBERS = {f'agent:{name}-t' for name in CLIENTS}


def _launcher():
    home = Path(os.environ.get('TALK_CONFIG') or ROOT / 'config.toml').resolve().parent
    path = home / 'logs' / 'launcher' / 'boot-status.json'
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {'ready': False, 'error': '启动状态读取失败，请查看启动日志。'}
    if not isinstance(raw, dict) or type(raw.get('ready')) is not bool:
        return {'ready': False, 'error': '启动状态无效，请查看启动日志。'}
    def names(key, allowed):
        value = raw.get(key, [])
        return [v for v in value if isinstance(v, str) and v in allowed] if isinstance(value, list) else []
    timestamp = raw.get('ts', '')
    result = {
        'ts': timestamp if isinstance(timestamp, str) and re.fullmatch(r'[0-9T:+.Z-]{1,40}', timestamp) else '',
        'detected': names('detected', CLIENTS), 'members_ok': names('members_ok', MEMBERS),
        'member_missing': names('member_missing', MEMBERS),
        'configs_written': names('configs_written', CLIENTS), 'skipped': names('skipped', CLIENTS),
        'download': {'needed': False, 'text': '无需下载'}, 'ready': raw['ready'],
    }
    if not raw['ready']:
        result['error'] = '运行器检测或 MCP 接入失败，请查看启动日志。'
    return result


@router.get('/api/boot/status')
def boot_status():
    launcher = _launcher()
    ready = launcher is None or launcher['ready']
    if launcher is None:
        stages = [{'name': '启动服务', 'state': 'complete'}, {'name': '就绪', 'state': 'complete'}]
    else:
        stages = [
            {'name': '启动服务', 'state': 'complete'},
            {'name': '检测运行器', 'state': 'complete' if ready else 'error'},
            {'name': '接入 MCP', 'state': 'complete' if ready else 'error'},
            {'name': '启动自动角色', 'state': 'unknown', 'text': '状态未提供'},
            {'name': '检查更新/下载', 'state': 'complete', 'text': '无需下载'},
            {'name': '就绪', 'state': 'complete' if ready else 'error'},
        ]
    detected = launcher.get('detected', []) if launcher else []
    runners = {'detected': detected, 'none': not detected,
               'source': 'launcher' if launcher and 'detected' in launcher else 'unknown'}
    return {'service_ready': True, 'launcher': launcher, 'stages': stages, 'ready': ready, 'runners': runners}


@router.get('/loading', include_in_schema=False)
def loading_page():
    return FileResponse(ROOT / 'web' / 'loading.html', media_type='text/html')
