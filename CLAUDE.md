# TALK — AI 智能体聊天中转平台

家庭局域网内的轻量级 Agent ↔ Agent ↔ 人类 实时聊天与文件交换平台。

## 开发者指引

1. **先读** `docs/PROJECT_BRIEF.md`：了解项目全貌、技术栈、数据模型。
2. **再读你负责的模块文档**：根据任务，在 `PROJECT_BRIEF` 的模块索引中找到对应的 `MODULE_xxx.md`，只读那一份。
3. **不要读其它模块文档**：节省 token，保持专注。
4. **不确定时**：查看 `PROJECT_BRIEF` 的模块索引表，或询问项目管理者。

## 技术栈速查

- 后端：Python 3.11 + FastAPI + uvicorn + SQLModel
- 数据库：SQLite（WAL 模式）
- 前端：Vanilla JS + Tailwind CSS (CDN)
- 鉴权：`X-API-Key` header
- 配置：`config.toml`（由 `tomllib` 读取）

## 启动方式

```bash
pip install -r requirements.txt
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
```

API 文档：http://127.0.0.1:8000/docs

## 运维说明

- 健康检查：`GET /healthz`
- 结构化日志：默认写入 `logs/talk.log`，按天切割，配置见 `config.toml` 的 `[logging]`
- SQLite 在线备份：`python scripts/backup_db.py`
- 备份目录与保留份数：配置见 `config.toml` 的 `[backup]`

## 项目结构注意事项

- SDK 代码位于 `TALK/client/`；项目根目录下存在一个同名 `TALK` 子目录，这不是 bug
- 这是 `SDK-1` 落地后的当前结构，默认运行前提是 `cwd = 项目根`
- Python import 路径固定写成 `from TALK.client import TalkClient`
- 不要写成 `from client import X`，也不要假设 `client/` 是项目根级包

### 定时备份参考

Linux / cron：

```bash
0 3 * * * cd /path/to/TALK && python scripts/backup_db.py
```

Windows 任务计划器：

```powershell
powershell -Command "Set-Location 'C:\MY TOOLS\MY WORK\TALK'; & 'C:\Users\bobo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\backup_db.py"
```

### 部署入口

- Docker 快速部署：`docker compose up -d --build`
- systemd 模板：`deploy/talk.service`
- 家庭部署入口：`docs/QUICKSTART_USER.md`
- 完整部署文档：`docs/DEPLOY.md`
