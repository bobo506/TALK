# 开发历史 · TALK

<!--
项目根：c:\MY TOOLS\MY WORK\TALK
最后更新：2026-04-13 拆分自原 PROGRESS.md
最新条目在顶部。条目数 > 30 时，最旧条目自动归档到 PROGRESS_archive.md
-->

## 2026-04-12

**完成**

- **M1 MVP 代码全部落地并通过 API 端到端验证**：按 [§9 目录结构](PRODUCT.md) 创建 `server/`、`web/`、`examples/` 完整代码骨架
- `server/models.py`：SQLModel 定义 members/messages/files 三张表 + Pydantic 请求/响应 schemas，`from` 关键字用 `Field(alias="from")` 解决
- `server/db.py`：用 `tomllib` 读取 `config.toml`，创建 SQLite engine（WAL 模式），提供 `get_session` 依赖
- `server/auth.py`：`X-API-Key` header → Member 查表鉴权依赖
- `server/ws_hub.py`：单例 Hub 维护 member_id → WebSocket 连接池，按 to_ids 精准推送或全量广播
- `server/routes/members.py`：POST 注册（自动推导 kind + 唯一性校验）、GET 列表
- `server/routes/messages.py`：POST 发消息（落库 + WS 广播）、GET 拉消息（since 游标 + to 过滤 + limit）
- `server/main.py`：FastAPI lifespan 初始化 DB，挂载 REST 路由 + WS 端点 + StaticFiles
- `web/`：暗色主题单页 UI（Tailwind CDN），含 @ 自动补全下拉框、WS 实时接收 + HTTP 轮询 3s 降级双通道、localStorage 保存登录态
- `examples/agent_poller.py`：纯 stdlib（无第三方依赖）Agent 脚本，自动注册 → 轮询 → 回声应答
- `config.toml` + `requirements.txt` + `run.sh` 基础设施
- **API 端到端验证通过**：注册 human:bobo + agent:AI1 + agent:AI2 → 定向消息 + 广播消息 → AI1 拉到所有消息 / AI2 只拉到广播 → TestBot Agent 自动注册+轮询+回复 → 中文 UTF-8 存储正确 → OpenAPI `/docs` 200 OK
- **建立全局项目文档结构规范**：创建 `~/.claude/CLAUDE.md`（文档结构标准 + MODULE 统一模板 + 模块拆分原则 + Agent 路由规则）
- **TALK 项目文档重构为 "1+N" 结构**：
  - `talk.md` → `docs/PRODUCT.md`（PM 完整产品文档，位置标准化）
  - 新建 `CLAUDE.md`（项目级路由入口，指引 agent 先读 PROJECT_BRIEF 再读对应 MODULE）
  - 新建 `docs/PROJECT_BRIEF.md`（~100 行公共上下文：架构图 + 技术栈 + 数据模型 + 模块索引表）
  - 新建 6 份 MODULE spec：`MODULE_members_auth` / `MODULE_messages` / `MODULE_websocket` / `MODULE_files` / `MODULE_webui` / `MODULE_agent_example`，每份含目标、范围、接口契约、约束、现状、待改进、验收标准
- **改进 progress skill**：触发词增加"继续项目"，§3.4 强化为必须用 AskUserQuestion 等待用户指示才能行动
- **清理记忆文件**：删除已过期的 `project_sql_exam.md`，更新 `user_sql_background.md` 去除考试上下文
- 为 TALK 补充**部署拓扑**章节 [§4.1](PRODUCT.md)：画出"拓扑 A 同机多 Agent"和"拓扑 B 跨机多 Agent"两张 ASCII 图，明确从 A 切到 B 只需 3 处配置修改（`host` / 防火墙 / Agent base_url），**零代码改动**
- 新增 [§5.1 关键配置项](PRODUCT.md)：`config.toml` 的 6 个字段（`host / port / public_url / upload_max_mb / storage_dir / db_path`）及默认值，并在备注里留下"默认 `127.0.0.1` 的安全理由"
- [§12 验证步骤](PRODUCT.md) 补了第 9 步：跨机部署端到端验证流程
- Plan 文件与 [TALK/talk.md](PRODUCT.md) 双份同步，保持两份文档内容一致
- 创建并落地 `project-progress` skill：[SKILL.md](C:\Users\bobo\.claude\skills\progress\SKILL.md) 211 行，含两种操作分发（summarize/resume）、三源素材采集、同日合并、首次初始化、计划自动迁移、历史归档、auto-resume hook 文档化
- 首次运行本 skill 并生成本进度文件 `docs/PROGRESS.md`
- **改进 skill 项目根裁定逻辑**（SKILL.md 从 211 行 → 256 行）：把原本 "git → cwd" 的 2 级回退换成 **5 级 Tier 算法**：Tier1 git 根 → Tier2 IDE 打开文件的最近项目祖先 → Tier3 cwd 自带项目标记 → Tier4 cwd 是多项目父目录时 AskUserQuestion 让用户选 → Tier5 回退 cwd 并显式警告。定义统一的 8 种"项目标记"（`.git/` / README / package.json / pyproject.toml / Cargo.toml / go.mod / requirements.txt / **已存在的 `docs/PROGRESS.md`**）。新增 §1.3 透明度约束，要求 Tier 2/3 命中时在输出开头标注来源，Tier 4 必须询问，Tier 5 必须警告
- **M2 文件上传下载 API 完成**：`server/routes/files.py` 实现 `POST /api/files` 与 `GET /api/files/{file_id}`，支持鉴权、sha256、`upload_max_mb` 限流、磁盘落盘、404 与超限处理；`server/models.py` 新增 `FileOut`
- **M2 Web UI 文件收发完成**：`web/` 补齐文件按钮、拖拽上传、待发送文件面板、文件消息气泡与下载按钮；前端发送 `type=file` 消息时将 `content` 固定写为文件名
- **M2 示例 Agent 文件收发完成**：`examples/agent_poller.py` 支持 `--send-file` + `--send-to` 启动参数发送文件，并在收到文件消息后下载到 `examples/downloads/<agent_name>/`
- **今日验证完成**：文件 API 在隔离环境下通过上传/下载/404/超限验证；示例 Agent 在临时本地服务中通过文件发送与下载验证；前端静态资源路由可正常访问

**决策**

- Server 默认 `host = 127.0.0.1`：安全优先。开箱即用只允许本机访问；用户显式改 `0.0.0.0` 时自然会意识到需要同步加固防火墙和 API Key
- 不自动修改 `~/.claude/settings.json` 安装 auto-resume hook：settings 是共享配置，改动风险高，按工作习惯先确认再动
- skill 的进度文件统一放 `<项目根>/docs/PROGRESS.md`（非项目根下），归档文件同目录的 `PROGRESS_archive.md`
- 项目根裁定规则（未来需要改进 skill）：当前 cwd 是多项目的父目录时，`git rev-parse` + cwd 回退不够用，应额外参考 IDE 打开文件的最近项目祖先
- Python `from` 关键字冲突：MessageOut 模型用 `Field(alias="from", serialization_alias="from")` + `populate_by_name=True` 解决，API 输出保持 `"from"` 不带下划线
- `POST /api/members` 不要求鉴权（注册是引导流程，无先有 key 的鸡蛋问题）；`GET /api/members` 暂不鉴权（供 UI @ 补全用，M3 再收紧）
- `examples/agent_poller.py` 纯 stdlib 实现（urllib.request + json），零第三方依赖，便于任意环境即跑
- Web UI 采用 WS 实时 + HTTP 轮询 3s 双通道降级策略：WS 断开后自动靠轮询兜底
- 文档结构采用 "1+N" 模式：全局规范放 `~/.claude/CLAUDE.md`，项目路由放项目根 `CLAUDE.md`，agent 只读 PROJECT_BRIEF + 自己的 MODULE
- CLAUDE.md vs Skill 边界：规则/标准放 CLAUDE.md（自动加载），复杂流程放 Skill（触发执行）
- Claude 角色定位为项目管理者/产品经理，代码开发分配给其他 agent
- `type=file` 消息的 `content` 字段用于保存文件名，供 Web UI 与 Agent 接收端直接展示；本阶段不支持"文件 + 额外文字附言"同发

## 2026-04-11

**完成**

- 确定 TALK 项目方向：家庭局域网内的 AI Agent 聊天中转平台，支持 Agent ↔ Agent 和 人 ↔ Agent 通过 `@` 定向交互
- 通过 4 轮关键决策问答冻结技术栈：**Python + FastAPI** / **SQLite 全部持久化** / **HTTP 轮询 + WebSocket 可选** / **X-API-Key 鉴权**
- 撰写产品文档初版 [talk.md](PRODUCT.md)，覆盖 13 个章节：产品背景、角色场景、F1–F4 功能需求、系统架构、技术选型、数据模型（含 SQL schema）、API 设计（REST + WebSocket）、关键流程（轮询/发消息/文件传输）、项目目录结构、非功能需求、M1/M2/M3 里程碑、端到端验证、待定议题
- Plan 文件 [prancy-soaring-eagle.md](C:\Users\bobo\.claude\plans\prancy-soaring-eagle.md) 完成并经用户批准
- 调研确认无任何既有 skill 可响应"汇总今日进度/继续开发"关键词
- 设计并通过 3 轮 AskUserQuestion 敲定 `project-progress` skill 方案：
  - 进度文件位置：`<项目根>/docs/PROGRESS.md`
  - 素材来源：git + 对话上下文 + `.claude/plans/` 三源融合
  - 默认内置：同日去重合并、首次自动初始化、文件头元信息
  - 已选增强：plan 文件联动、后续计划自动迁移、历史 >30 归档、auto-resume hook（文档化）
- 建立 [C:\Users\bobo\.claude\skills\project-progress\](C:\Users\bobo\.claude\skills\project-progress\) 目录

**决策**

- TALK 的 MVP 范围排除：公网部署、E2E 加密、多房间、消息撤回、Agent 自身 LLM 能力
- SQLite 够用，不上 PostgreSQL —— 家庭局域网单机场景零运维优先
- 前端不引入构建链（无 Vue/React/Vite），Vanilla JS + Tailwind CDN 即可
- 消息 `to_ids` 用 JSON 数组 + `NULL` 表广播的单表设计，避免引入额外 mention 关联表
- `id` 单调递增兼做 `since` 游标，实现 Agent 至少一次送达、不丢不重
