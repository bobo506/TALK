# Project Progress

## Latest
Updated: 2026-04-24 19:25 (Asia/Shanghai)

### 1) Current Progress
- `SETUP-1` completed: added unauthenticated `GET /api/setup/status`, CLI bootstrap script `scripts/create_admin.py`, Web UI first-run admin creation flow, and setup coverage in `tests/test_setup.py`.
- `QUICKSTART` and `DEPLOY` now document first-run bootstrap via the Web UI and `python scripts/create_admin.py`, including the Docker path `docker compose exec talk python scripts/create_admin.py`.
- The old onboarding blocker is removed at the code level: first human account creation no longer requires opening `/docs` and manually calling `POST /api/members`.
- `SDK-1` completed: added `TALK/client/` with async `TalkClient`, sync `TalkClientSync`, HTTP exception mapping, WebSocket-first event flow, reconnect plus HTTP polling fallback, message dedupe, and SDK docs/demo.
- `MSG-4` completed: added first-level message reply support across database, REST, WebSocket, Web UI, and SDK; reply summaries now travel with history and live events.
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `deploy/talk.service`, `README.md`, `docs/QUICKSTART.md`, and `docs/DEPLOY.md` for Docker, systemd, and bare-metal deployment paths.
- `SEC-1` completed: `GET /api/messages` now enforces visibility in SQL, aligns with WebSocket delivery semantics, and treats `to` as a narrowing filter rather than an access-control boundary.
- Regression coverage expanded again; full `python -m unittest` is now green with `51` tests, including `3` new setup-specific cases.

### 2) Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- The new first-run setup flow has test coverage, but a real browser smoke test for “empty DB -> create admin -> auto login -> reopen -> normal login form” is still pending.

### 3) Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/DEPLOY.md`.
- Run one real browser smoke test for `SETUP-1` on a fresh DB and confirm the first-run form, automatic sign-in, and second-open login behavior match the task card.
- Collect first-run feedback from a non-project user against `docs/QUICKSTART.md` and remove any remaining setup friction.

## History

### 2026-04-24 19:25 (Asia/Shanghai)
#### Current Progress
- `SETUP-1` completed: added unauthenticated `GET /api/setup/status`, CLI bootstrap script `scripts/create_admin.py`, Web UI first-run admin creation flow, and setup coverage in `tests/test_setup.py`.
- `QUICKSTART` and `DEPLOY` now document first-run bootstrap via the Web UI and `python scripts/create_admin.py`, including the Docker path `docker compose exec talk python scripts/create_admin.py`.
- The old onboarding blocker is removed at the code level: first human account creation no longer requires opening `/docs` and manually calling `POST /api/members`.
- Regression coverage expanded again; full `python -m unittest` is now green with `51` tests, including `3` new setup-specific cases.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- The new first-run setup flow has test coverage, but a real browser smoke test for “empty DB -> create admin -> auto login -> reopen -> normal login form” is still pending.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/DEPLOY.md`.
- Run one real browser smoke test for `SETUP-1` on a fresh DB and confirm the first-run form, automatic sign-in, and second-open login behavior match the task card.
- Collect first-run feedback from a non-project user against `docs/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 20:39 (Asia/Shanghai)
#### Current Progress
- `SDK-1` completed: added `TALK/client/` with async `TalkClient`, sync `TalkClientSync`, HTTP exception mapping, WebSocket-first event flow, reconnect plus HTTP polling fallback, message dedupe, and SDK docs/demo.
- `MSG-4` completed: added first-level message reply support across database, REST, WebSocket, Web UI, and SDK; reply summaries now travel with history and live events.
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `deploy/talk.service`, `README.md`, `docs/QUICKSTART.md`, and `docs/DEPLOY.md` for Docker, systemd, and bare-metal deployment paths.
- `SEC-1` completed: `GET /api/messages` now enforces visibility in SQL, aligns with WebSocket delivery semantics, and treats `to` as a narrowing filter rather than an access-control boundary.
- Regression coverage expanded across SDK and message flows; full `python -m unittest` is green with `48` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- First human account creation still relies on `/docs` plus `POST /api/members`; there is still no dedicated first-run bootstrap flow.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/DEPLOY.md`.
- Decide whether to turn first human account creation into a dedicated bootstrap flow, or explicitly accept `/docs` as the administrator-only setup path for now.
- Collect first-run feedback from a non-project user against `docs/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 20:38 (Asia/Shanghai)
#### Current Progress
- `SEC-1` completed: `GET /api/messages` now enforces message visibility in SQL and matches WebSocket delivery semantics instead of trusting the caller's `to` filter.
- `to=<member_id>` is now only a narrowing filter on the caller's visible set; `to=<other_member>` returns a safe pair view without exposing third-party private messages.
- Added regression coverage in `tests/test_messages.py` for third-party private message isolation, `to` filter escape attempts, broadcast visibility, pair-view filtering, and search visibility boundaries.
- Added startup indexes for `messages.from_id` and `messages.to_ids`, and updated `docs/MODULE_messages.md`, `docs/PROJECT_BRIEF.md`, and `docs/SDK.md` to document the new server-enforced visibility contract.
- Full regression check passed: `python -m unittest` is green with `48` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- First human account creation still relies on `/docs` plus `POST /api/members`; there is still no dedicated first-run bootstrap flow.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/DEPLOY.md`.
- Decide whether to turn first human account creation into a dedicated bootstrap flow, or explicitly accept `/docs` as the administrator-only setup path for now.
- Collect first-run feedback from a non-project user against `docs/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:59 (Asia/Shanghai)
#### Current Progress
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and `deploy/talk.service` to support Docker and systemd deployment paths.
- Added human-facing deployment docs: `README.md` as the root entry, `docs/QUICKSTART.md` for first install/login/use, and `docs/DEPLOY.md` for Docker, systemd, bare-metal, reverse proxy, backup, and restore workflows.
- `CLAUDE.md` now points operators to the new deployment entry docs and templates.
- Docker docs now include writable path bootstrap steps for a clean machine: `storage/`, `logs/`, `backups/`, and `talk.db`.
- Regression check passed: `python -m unittest` remains green with `43` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup were not verified here.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- Outside `DEPLOY-1`, one known product-side gap remains: `GET /api/messages` history visibility still relies on the caller using the expected `to=<member_id>` view and is not yet fully tightened to WebSocket-level visibility semantics.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/DEPLOY.md`.
- Collect first-run feedback from a non-project user against `docs/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:57 (Asia/Shanghai)
#### Current Progress
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and `deploy/talk.service` to support Docker and systemd deployment paths.
- Added human-facing deployment docs: `README.md` as the root entry, `docs/QUICKSTART.md` for first install/login/use, and `docs/DEPLOY.md` for Docker, systemd, bare-metal, reverse proxy, backup, and restore workflows.
- `CLAUDE.md` now points operators to the new deployment entry docs and templates.
- Docker docs now include writable path bootstrap steps for a clean machine: `storage/`, `logs/`, `backups/`, and `talk.db`.
- Regression check passed: `python -m unittest` remains green with `43` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup were not verified here.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/DEPLOY.md`.
- Collect first-run feedback from a non-project user against `docs/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:48 (Asia/Shanghai)
#### Current Progress
- `MSG-4` completed: backend now supports first-level message replies via `messages.reply_to`, server-side validation, REST history reply summaries, and WebSocket payload parity.
- Web UI now supports reply composition, inline reply strips, jump-to-origin highlight, revoked-origin placeholder handling, and runtime config loading from public `GET /api/config`.
- `SDK-1` follow-up completed: `TALK/client/talk_client.py` now supports `reply_to` and `client.reply(message_id, text=...)`.
- Docs updated for `MODULE_messages`, `MODULE_webui`, and `PROJECT_BRIEF` addenda covering reply semantics and `/api/config`.
- Automated verification passed: `python -m unittest` is green with `43` total tests, including new reply/config coverage in `tests/test_messages.py` and the SDK reply shortcut test.
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- Confirm the next product card after `MSG-4`; current reply support is intentionally flat and does not attempt nested thread rendering.
- If the next task stays in messaging, the highest-risk follow-up is tightening history visibility filtering in `GET /api/messages` so HTTP history matches WebSocket visibility more strictly.
- If manual UX acceptance is required, run the local browser flow for reply creation, jump-to-origin, revoke-after-reply, and `/api/config`-driven upload limit behavior.

### 2026-04-23 19:25 (Asia/Shanghai)
#### Current Progress
- `SDK-1` ?????????? `TALK/client/`????? `TalkClient`?????? `TalkClientSync`?????? `register/send_text/send_file/revoke/download_file/me/list_members/fetch_history/run` ??????
- SDK ??????? WebSocket ?????JSON `ping/pong` ??????????????? HTTP `since` ??????????? N ? `message.id` ???????? WS `from_field` ? REST `from` ?????
- ?? `examples/agent_sdk_demo.py`?????? `24` ????????? `agent:<name>`????? `ping` ??????? `pong`?????????? Agent??
- ?? `docs/SDK.md` ?? SDK API ?????? `docs/MODULE_agent_example.md` ?? SDK ?????`server/routes/files.py` ?? `HTTP_413_REQUEST_ENTITY_TOO_LARGE` ?? `HTTP_413_CONTENT_TOO_LARGE`?
- ?? `tests/test_talk_client.py` ? 6 ? `unittest` ???????/?????????????WS ????????????????? handler????????????? `36` ? `unittest`?`python -m unittest` ???
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- ?????????? SDK ?????????????? `reply_to` / ?????????????????????????????
- ?????? Agent ????????????????????????????????? Agent ???????/?????
- ???????????????????????? `docs/PROGRESS.md`????????????????

### 2026-04-22 23:29 (Asia/Shanghai)
#### Current Progress
- `WS-1` 已完成：WebSocket 心跳 `ping/pong`、空闲超时断开、入站 `send`、WS/REST 共用消息创建链路与鉴权重构均已落地。
- `FILE-1` 已完成：文件上传接入 `sha256` 秒传去重，采用 A 方案保留多条记录共享实体路径，并修正共享实体的过期清理逻辑。
- `OPS-1` 已完成：新增 `/healthz`、结构化日志、在线热备脚本、日志/备份配置段与运维文档，手动验收与自动化测试均通过。
- `MSG-3` 已完成：支持消息撤回、撤回态历史回放、WS `revoke` 实时同步、Web UI 撤回按钮与撤回占位渲染，文件消息撤回后实体保留。
- 当前全量自动化测试共 `30` 个 `unittest` 用例，`python -m unittest` 已全绿。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 继续推进下一个已确认任务卡，优先选择新的业务能力点，而不是重复打磨已通过验收的模块。
- 低优先清理两个工程尾项：`413` 弃用告警，以及前端撤回窗口时长与后端配置的统一读取方式。
- 保持后续任务的代码、模块文档与 `docs/PROGRESS.md` 同步更新。

### 2026-04-22 22:06 (Asia/Shanghai)
#### Current Progress
- 在现有 `tests/` 骨架上继续扩完 `M3-4`：新增 `tests/test_websocket.py` 4 个 `unittest` 用例，覆盖无效 token 拒绝、首次 presence 快照、上下线 presence 变更、实时消息推送、`since` 对齐去重，以及断线后通过 HTTP `since` 补历史。
- 扩充 `tests/test_files.py` 4 个上传链路用例，覆盖成功上传落盘/落库、上传鉴权拒绝、超限文件拒绝、上传后 `type=file` 消息对 `filename / size_bytes / mime` 的快照冻结。
- 为了让基于 FastAPI `TestClient` 的自动化测试可直接运行，`requirements.txt` 已补入 `httpx>=0.27,<1`。
- 测试基类已补应用注入与隔离能力：`tests/test_support.py` 现在会把临时 SQLite 引擎注入 `server.main`，并在每个用例前后清空 `hub` 连接状态，避免 WS 单测串扰。
- 已同步更新 `docs/MODULE_websocket.md` 与 `docs/MODULE_files.md` 的当前实现现状和验收标准，反映本轮新增自动化覆盖。
- 当前全量自动化测试为 `15` 个 `unittest` 用例，已通过 `python -m unittest` 全量验证。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 如继续补 `M3-4`，优先补 WebSocket 广播路径与“同一成员多连接”场景，补齐 `MODULE_websocket` 里仍未打勾的验收项。
- 低优先处理进度文档收口：按既定建议评估是否把 `docs/PROGRESS.md` 的历史段进一步收敛到双文件结构。
- 后续每完成一项功能，继续同步对应模块文档与 `docs/PROGRESS.md`，避免进度积压。

### 2026-04-21 23:29 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
- `M3-4` 已启动首轮自动化测试：新增 `tests/` 目录与 7 个 `unittest` 用例，覆盖成员自注册、消息 mention/分页/搜索，以及文件过期清理与下载错误分支；整套测试已跑通。
- 今日开发先收口到这里；相关模块文档与项目简报已对齐到当前状态，包含 `tests/` 测试骨架与已覆盖的后端行为范围。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在现有 `tests/` 骨架上继续扩 `M3-4`，优先补 WebSocket/presence 与文件上传链路的自动化覆盖。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 23:08 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
- `M3-4` 已启动首轮自动化测试：新增 `tests/` 目录与 7 个 `unittest` 用例，覆盖成员自注册、消息 mention/分页/搜索，以及文件过期清理与下载错误分支；整套测试已跑通。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在现有 `tests/` 骨架上继续扩 `M3-4`，优先补 WebSocket/presence 与文件上传链路的自动化覆盖。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 23:00 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 第二批核心功能已收口，下一步优先切到第三批里的 `M3-4` 单元测试，把这轮成员注册、消息分页/搜索、文件过期行为收敛成可重复执行的自动化测试。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 22:14 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 继续推进第二批剩余项，优先做 `MEM-1` 真实链路手工验收，确认 Agent 首次注册、重复启动和冲突 key 行为都符合预期。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 21:52 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在 `MSG-2` 基础上继续实现 `MSG-1` 消息搜索，并优先复用现有消息列表渲染与分页交互。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 在浏览器端最终验收前，继续把 M3 剩余体验项收敛在低风险的前端和 WebSocket 变更范围内。

### 2026-04-21 21:48 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 按既定路线进入第二批，优先实现 `MSG-2` 历史分页，再评估与 `MSG-1` 消息搜索的接口复用。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 在浏览器端最终验收前，继续把 M3 剩余体验项收敛在低风险的前端和 WebSocket 变更范围内。

### 2026-04-21 19:58 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
#### Open Questions / Pending Confirmation
- 文件生命周期策略尚未确定：当前实现会长期保留 `files` 表记录和 `storage/files/<file_id>` 实体；如引入删除/清理，需要先确认“历史文件消息是否必须永久可下载”以及删除后的预期行为。
#### Next Plan
- 等待项目管理者确认文件生命周期策略，优先建议先明确“已被消息引用的文件是否永久保留”这一条基线规则。
- 策略确认后，按决策实现对应的文件保留/清理方案，并补充 API/前端在文件缺失场景下的用户可见行为。
- 在本轮已确认改动稳定后，同步更新 `docs/MODULE_messages.md`、`docs/MODULE_webui.md` 与 `docs/MODULE_files.md` 的实现状态描述。

### 2026-04-14 00:12 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 接收者表达已统一为 `@mention` 模式：文本正文与文件附言都只解析“消息开头连续 mention 块”作为接收者；无开头 mention 时按广播处理；无效 mention 会在发送前红色提示并阻止发送。
- 相关文档已同步到当前实现：`AGENTS.md`、`docs/PROJECT_BRIEF.md`、`docs/MODULE_members_auth.md`、`docs/MODULE_messages.md`、`docs/MODULE_files.md`、`docs/MODULE_webui.md`、`docs/MODULE_agent_example.md`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 评估是否将当前“前端解析开头 mention 后写入 `to`”的规则下沉到后端，收敛为服务端统一解析逻辑，避免不同客户端各自实现一套。
- 继续处理 Web UI 可用性问题，优先考虑消息列表性能（虚拟滚动/分页）和文件生命周期策略（删除/清理）。
- 如需继续完善文档，补齐 `MODULE_files.md` 以外的状态细节，并在后续每轮确认后的实现落地后同步更新。

### 2026-04-13 00:00 (Asia/Shanghai)
#### Current Progress
- M2 核心能力已基本落地：文件上传下载 API、Web UI 文件收发、示例 Agent 文件收发已完成。
- 文件 API、静态资源路由和示例 Agent 的基础链路已在隔离环境中验证通过。
- 浏览器端 Web UI 仍待整链路手动验收。

#### Open Questions / Pending Confirmation
- 下一步优先做 `/api/me` 还是继续细化 Web UI。
- 是否安装 auto-resume hook 到 `~/.claude/settings.json`。

#### Next Plan
- 先完成浏览器端整链路验收，再决定 `/api/me` 与 Web UI 细化的优先级。
