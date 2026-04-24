# TALK — AI 智能体聊天中转平台

家庭局域网内的轻量级 Agent ↔ Agent ↔ 人类 实时聊天与文件交换平台。

## 开发者指引

1. **先读** `docs/PROJECT_BRIEF.md` — 了解项目全貌、技术栈、数据模型
2. **再读你负责的模块文档** — 根据你的任务，在 PROJECT_BRIEF 的模块索引中找到对应的 `MODULE_xxx.md`，只读那一份
3. **不要读其它模块的文档** — 节省 token，保持专注
4. **不确定时** — 查看 PROJECT_BRIEF 的模块索引表，或询问项目管理者

## Agent 角色与协作约束

- Agent 的默认角色是**开发执行**，负责按已确认需求实现代码，不负责替代项目管理者做产品决策
- 开发过程中只要存在任何不确定项，都必须先向项目管理者确认，再继续开发
- “不确定项”包括：需求理解不明确、实现路径有多种可选方案、Agent 认为存在更优替代方案、可能影响现有行为或接口的改动
- 除 `docs/PROGRESS.md` 外，其它项目文档默认不得擅自修改；如需改动，必须先得到项目管理者明确许可
- 一旦项目管理者明确确认某项需求/实现决策，并允许同步文档，Agent 应在相关代码落地后及时更新对应文档，使文档与当前实现保持一致
- 文档更新范围应限制在与本次已确认改动直接相关的模块文档和公共简报，不得顺手扩写无关内容
- `docs/PROGRESS.md` 是本项目唯一进度文档，更新该文档时必须通过 `project-daily-progress` 的相关工作流执行，不得手工直接修改

## 编码约定

- 所有文件写入操作必须显式指定 `encoding='utf-8'`
- Windows 环境下 Python 默认编码可能是 GBK；如果省略编码参数，中文内容可能被写成乱码
- Python 写文件示例：`open(path, "w", encoding="utf-8")`

## 项目结构注意事项

- SDK 代码位于 `TALK/client/`；项目根目录下存在一个同名 `TALK` 子目录，这不是 bug
- 这是 `SDK-1` 落地后的当前结构，默认运行前提是 `cwd = 项目根`
- Python import 路径固定写成 `from TALK.client import TalkClient`
- 不要写成 `from client import X`，也不要假设 `client/` 是项目根级包

## 技术栈速查

- 后端：Python 3.11 + FastAPI + uvicorn + SQLModel
- 数据库：SQLite（WAL 模式）
- 前端：Vanilla JS + Tailwind CSS (CDN)
- 鉴权：X-API-Key header
- 配置：config.toml（由 tomllib 读取）

## 启动方式

```bash
pip install -r requirements.txt
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
```

API 文档：http://127.0.0.1:8000/docs
