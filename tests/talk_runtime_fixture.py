"""统一入口实际子进程测试专用；无数据库、原生模型或生产身份。"""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app):
    config_file=os.environ.get('TALK_RUNTIME_FIXTURE_CONFIG')
    if config_file:
        from scripts.talk_runtime import load_config
        from server import local_runtime
        with patch.object(local_runtime,'configured_runtime',return_value=(Path(config_file),load_config(config_file))):
            local_runtime.ensure_local_runtime(None)
    yield

app=FastAPI(lifespan=lifespan)

@app.get('/api/members/me')
def me():return {'id':'human:runtime-fixture','kind':'human'}

@app.get('/api/projects/{project}/roles')
def roles(project):return []

@app.post('/api/projects/{project}/role-services/startup')
def startup(project,body:dict):
    # Empty synthetic project; no server DB, production binding, or real roles.
    return {'activation_id':body['activation_id'],'complete':True,'results':[],'retry_after_seconds':5}
