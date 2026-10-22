"""统一入口实际子进程测试专用；无数据库、原生模型或生产身份。"""
from fastapi import FastAPI
app=FastAPI()

@app.get('/api/members/me')
def me():return {'id':'human:runtime-fixture','kind':'human'}

@app.get('/api/projects/{project}/roles')
def roles(project):return []
