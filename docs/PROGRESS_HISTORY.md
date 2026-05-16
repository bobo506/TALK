# 开发历史 · TALK

<!--
项目根：c:\MY TOOLS\MY WORK\TALK
最后更新：2026-05-16 20:24，连续开发批次刹车规则已补充
最新条目在顶部。条目数 > 30 时，最旧条目自动归档到 PROGRESS_archive.md
-->

## 2026-05-16 20:24 (Asia/Shanghai)
### Current Progress
- `WORKFLOW-BATCH-GUARD-1` 已完成：已在全局 `project-framework` skill 与 TALK `AGENTS.md` 中加入连续开发批次刹车规则。
- 决策 Agent 每次恢复默认最多连续推进 2 个明确切片；若都是小型文档/配置切片，可最多 3 个。
- 涉及前端真实交互、数据库/协议、部署/权限或跨模块协作时，默认 1 个切片后暂停汇总。
- 决策 Agent 连续工作约 60-90 分钟后，不应开启新切片，应先完成当前切片的必要验证、汇总进度、提交/推送，并输出下一步建议。
- 软停止信号仅保留两项：后续任务需要重新读取另一个模块文档，或 Agent 明显开始依赖“回忆前文”才能继续判断。
- 若环境提供 5 小时额度或 token 用量占比，仍保留达到或超过 90% 时必须完成当前切片收尾的规则；若环境未暴露精确占比，不臆测百分比。
### Open Questions / Pending Confirmation
- 当前环境仍未暴露精确 token/5 小时额度占比；后续继续按批次、工作时长、上下文接近上限与两项软停止信号控制连续开发。
- Browser runtime 初始化问题仍待从 Codex Desktop / Browser 后端侧恢复后补测。
### Next Plan
1. 提交并推送全局 `project-framework` skill 更新。
2. 提交并推送 TALK 本地规则与进度更新。
3. 下一功能候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
### Verification
- `$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\project-framework` passed。
- `git diff --check` in `C:\Users\Administrator\.codex\skills\project-framework` passed，仅有换行提示。
- `git diff --check` in TALK passed，仅有换行提示。
### Changed Files
- `C:\Users\Administrator\.codex\skills\project-framework\SKILL.md`
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-16 19:26 (Asia/Shanghai)
### Current Progress
- `WORKFLOW-GUARD-1` 已完成：已在 `AGENTS.md` 中补充 Browser 验证失败诊断规则与 token/额度占比收尾规则。
- Browser 失败诊断确认：`node_repl` 可执行，`browser-client.mjs` 可 import，但 `setupAtlasRuntime(...)` 阻塞超时，失败点在 Codex Browser 运行时初始化/后端连接，不是 TALK 页面代码。
- 规则明确：若 `node_repl` 与 import 正常但 Browser runtime 初始化阻塞，应记录限制，改用静态检查、后端测试、必要的临时隔离服务验证，并提示项目管理者从 Codex Desktop / Browser 后端侧恢复后补测。
- token/额度规则明确：若运行环境提供 5 小时额度或 token 用量占比，达到或超过 90% 时不得开启新切片，必须先完成当前切片收尾、汇总进度、提交/推送并输出 `继续项目`。
- 当前工具上下文未暴露 5 小时额度或 token 用量占比，Agent 不应臆测具体百分比，继续沿用上下文 80%-90% 接近上限规则。
### Open Questions / Pending Confirmation
- 需要项目管理者在 Codex Desktop 侧重启/恢复 in-app Browser 或检查 Browser/Chrome 后端后，再补 Web UI 真实浏览器验证。
- 若未来 Codex 暴露精确 token/额度占比，可进一步把该信号纳入自动化提醒或进度模板。
### Next Plan
1. 提交并推送本次流程规则补充切片。
2. Browser 恢复可用后，补 Web UI SSE 兜底真实页面烟测。
3. 下一功能候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
### Verification
- `node_repl` 最小执行 `nodeRepl.write("node_repl ok")` passed。
- `browser-client.mjs` import passed，导出 `setupAtlasRuntime`。
- `setupAtlasRuntime(...)` 30 秒超时；使用 `Promise.race` 的 5 秒超时探针也未返回，说明初始化过程阻塞。
- `git diff --check` 待提交前执行。
### Changed Files
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-16 19:04 (Asia/Shanghai)
### Current Progress
- `WEB-SSE-UI-1` 已完成：Web UI 已接入 `GET /api/events?token=...` SSE 事件流作为实时兜底。
- 浏览器优先使用 WebSocket；如果当前浏览器不支持 WebSocket，或 WebSocket 断开/报错，会打开 SSE 并显示 `SSE 已连接 / SSE 兜底中 / SSE 重连中 · 轮询兜底` 状态。
- WebSocket 恢复后会主动关闭 SSE，避免同一浏览器同时占用两条实时通道。
- SSE 与 WS 共用前端实时事件处理逻辑，统一处理 `message / revoke / presence`，`ping` 事件只用于保持连接。
- HTTP 轮询仍保留为断线与事件缺口补漏通道，不承担在线成员状态。
- `docs/MODULE_webui.md` 已同步接口依赖、当前实现、验收标准和本切片 addendum。
### Open Questions / Pending Confirmation
- Codex in-app Browser 插件本轮连接两次超时，未完成真实浏览器前端烟测；临时隔离服务已关闭并清理。
- SSE `Last-Event-ID` replay/backfill 尚未实现；客户端仍需用历史接口和 HTTP 轮询补漏。
### Next Plan
1. 提交并推送本次 Web UI SSE 兜底切片。
2. 下一候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
3. 如浏览器插件恢复可用，补一轮真实 Web UI SSE 兜底烟测。
### Verification
- `node --check web\app.js` passed。
- `git diff --check` passed，仅有换行提示。
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed，3 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_websocket` passed，10 tests。
- `.venv\Scripts\python.exe -m unittest` passed，85 tests。
- Browser 插件连接两次超时；临时隔离服务已关闭并清理。
### Changed Files
- `web/app.js`
- `web/index.html`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 18:25 (Asia/Shanghai)
### Current Progress
- `DOC-LANG-1` 已完成：已在 `AGENTS.md` 中加入 TALK 文档语言约定。
- 项目文档中的描述性内容应尽量使用中文。
- 代码标识、API 路径、命令、配置键、协议名、库名、错误码、commit hash 等技术字面量可以保留原始写法。
- 该规则覆盖需求说明、设计说明、进度记录、验收说明、变更摘要和面向人阅读的解释文字。
### Open Questions / Pending Confirmation
- 本规则切片没有新增待确认问题。
### Next Plan
1. 提交并推送本次文档规则切片。
2. 明天用 `继续项目` 恢复。
### Verification
- 本次文档规则更新前，`git status --short` 为空。
- `git diff --check` 已通过，仅有换行提示。
### Changed Files
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
## 2026-05-15 18:21 (Asia/Shanghai)
### Current Progress
- End-of-day TALK summary completed.
- Confirmed TALK worktree was clean before this summary update.
- Confirmed today's implementation commit `bfb28a3 feat: add group sdk ui and sse events` exists locally and had been pushed earlier to GitHub branch `codex/local-lab-codex-bridge`.
- Confirmed today's workflow/documentation commit `d9a10d5 更新 Agent 协作规则与进度拆分` exists locally and had been pushed earlier to GitHub branch `codex/local-lab-codex-bridge`.
- Confirmed standalone `project-framework` skill repository was updated and pushed at `7756b08 更新项目连续性管理规则`.
- Current recovery instruction for the next session: say `继续项目`.
### Open Questions / Pending Confirmation
- Web UI SSE integration is still the recommended next implementation slice.
- Remaining pending areas: SSE replay/backfill, Group rename/delete UI, document-edit lock API, schedule API, Codex bridge task-queue integration, and environmental deployment/onboarding verification.
### Next Plan
1. Resume tomorrow with `继续项目`.
2. Prefer Web UI SSE fallback/integration unless project priority changes.
### Verification
- `git status --short` was clean before this summary update.
- `git log -3 --oneline` showed `d9a10d5`, `bfb28a3`, and `99578f3`.
- Prior verification for the completed code slice: full `.venv\Scripts\python.exe -m unittest` passed with `85` tests; `node --check web\app.js` passed; `git diff --check` passed with line-ending warnings only.
### Changed Files
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 18:02 (Asia/Shanghai)
### Current Progress
- `PROJECT-FRAMEWORK-RULES-1` completed: updated the local `project-framework` skill with the new project-management workflow rules.
- Added role authority rules: `AGENTS.md` is the source of truth; Codex is currently the decision Agent and Claude is currently the execution Agent for TALK.
- Added development cadence rules: decision Agents may continue through multiple clear slices; execution Agents must complete one slice, summarize progress, then wait for confirmation.
- Added required per-slice summary behavior for all Agent roles, plus local git/GitHub submission expectations and Chinese GitHub-facing descriptions.
- Added context handoff/clear flow: summarize, persist, verify, and submit before clearing context or opening a new window; otherwise output `继续项目`.
- Added milestone acceptance gate: pause at independently usable milestones and provide a Chinese acceptance package before continuing.
- Split progress management so `docs/PROGRESS.md` stays short and completed slice history lives in `docs/PROGRESS_HISTORY.md`.
- Synced TALK docs in `AGENTS.md`, `docs/PROJECT_BRIEF.md`, and this progress set.
### Open Questions / Pending Confirmation
- GitHub push/PR behavior is conditional on available remote credentials and should be handled by the active Agent at submission time.
### Next Plan
1. Commit this workflow/documentation slice after verification.
2. Resume implementation from the current candidate list when requested.
### Verification
- `$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\project-framework` passed.
- `git diff --check` passed with line-ending warnings only.
### Changed Files
- `C:\Users\Administrator\.codex\skills\project-framework\SKILL.md`
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 历史迁移（来自 PROGRESS.md）

### 2026-05-15 11:04 (Asia/Shanghai)
#### Current Progress
- `SSE-1` completed: added read-only `GET /api/events?token=...` as a Server-Sent Events stream for clients that cannot or should not hold a WebSocket.
- SSE authentication uses the existing API key member resolution path; invalid tokens return `401`.
- The stream emits `presence`, `message`, `revoke`, and idle `ping` events; `message` and `revoke` include SSE `id:` set to the message id.
- `server/ws_hub.py` now fans out realtime updates to both WebSocket connections and per-member SSE queues, drops the oldest queued SSE event when a member queue is full, and counts online members across the WebSocket/SSE union.
- Added live streaming tests for invalid token rejection, presence/message delivery, and revoke delivery.
- Synced `docs/MODULE_websocket.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- Web UI has not integrated the new SSE stream yet; this slice only provides the backend event contract.
- SSE `Last-Event-ID` replay/backfill is not implemented; clients should still use message history APIs after reconnect when they need gap recovery.
#### Next Plan
- Continue with one of: Web UI SSE fallback/integration, SSE `Last-Event-ID` replay/backfill, Group rename/delete UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_websocket` passed with `10` tests.
- Full `.venv\Scripts\python.exe -m unittest` passed with `85` tests.
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `server/main.py`
- `server/ws_hub.py`
- `tests/test_sse.py`
- `tests/test_support.py`
- `docs/MODULE_websocket.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-15 10:52 (Asia/Shanghai)
#### Current Progress
- `WEB-GROUP-MEMBERS-1` completed: active Group Hall now exposes a members panel from the top room strip.
- Human users can add members not yet in the Group, update member roles among `owner / moderator / member`, and remove other members.
- Agent users retain a read-only member list in the UI; server-side permission remains authoritative.
- Successful member changes replace the active Group snapshot and immediately refresh room metadata, scoped presence, and `@` autocomplete.
- Static asset cache-busting updated to `20260515-group-members`.
- Synced `docs/MODULE_webui.md`, `docs/MODULE_groups.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- No new open questions from this slice.
#### Next Plan
- Choose the next slice from: SSE stream event contract, Group rename/delete UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_groups tests.test_messages` passed with `26` tests.
- Chrome headless smoke test against an isolated temporary TALK server verified login, Group creation, members panel open, member add, role update, member removal, and no horizontal overflow at desktop and 500px widths.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/MODULE_webui.md`
- `docs/MODULE_groups.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-15 10:37 (Asia/Shanghai)
#### Current Progress
- `SDK-GROUP-1` completed: async SDK now exposes `create_group`, `list_groups`, `get_group`, `upsert_group_member`, and `remove_group_member`.
- Sync SDK parity added for the same Group helpers; sync `reply()` was also exposed for parity with the async client.
- Message helpers now support Hall scope: `send_text`, `send_file`, `reply`, and `fetch_history` can carry `group_id`.
- Added live SDK coverage that creates a Group, updates/removes a member, sends a Hall message, reads Hall history as an Agent, and verifies the Hall message does not leak into legacy/global history.
- Synced `docs/SDK.md`, `docs/MODULE_groups.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- No new open questions from this slice.
#### Next Plan
- Choose the next slice from: SSE stream event contract, Group member management UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed with `10` tests.
- Full `.venv\Scripts\python.exe -m unittest` passed with `82` tests.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_talk_client.py`
- `docs/SDK.md`
- `docs/MODULE_groups.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-14 16:33 (Asia/Shanghai)
#### Current Progress
- `WEB-GROUP-1` completed: Web UI now exposes a real Group/Hall room strip above the workspace tools.
- Added global timeline / Group Hall switching, `GET /api/groups` loading, active Group persistence per user, and disabled entries for Groups the current user cannot enter.
- Added a lightweight new Group panel with name, optional ID, optional description, and initial member checkboxes; creation succeeds through `POST /api/groups` and automatically enters the new Hall.
- Hall scope now flows through the browser: history and polling include `group_id`, text/file send payloads include `group_id`, WebSocket events are appended only when they belong to the active room, and switching rooms clears reply state.
- Hall UX now scopes online members and `@` autocomplete to the current Group members and uses a placeholder that states Hall mentions are reminders rather than visibility restrictions.
- Synced `docs/PROJECT_BRIEF.md`, `docs/MODULE_webui.md`, `docs/MODULE_groups.md`, and this progress file.
#### Open Questions / Pending Confirmation
- Group member management after creation, Group rename/delete, unread/attention state, SDK helpers, SSE stream integration, and multi-Agent discussion protocol remain future slices.
#### Next Plan
- Commit this Web UI Group/Hall follow-up if accepted.
- Then continue with one of: SDK group helpers, Group member management UI, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- Chrome headless smoke test against an isolated temporary TALK server/database/storage verified login, Group creation with `agent:codex`, Hall message send, Hall-specific placeholder, and that switching back to global hides the Hall message.
- `.venv\Scripts\python.exe -m unittest tests.test_groups tests.test_messages` passed with `26` tests.
- `git diff --check` passed with line-ending warnings only.
- Full `.venv\Scripts\python.exe -m unittest` passed with `81` tests.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/PROJECT_BRIEF.md`
- `docs/MODULE_webui.md`
- `docs/MODULE_groups.md`
- `docs/PROGRESS.md`

### 2026-05-14 16:03 (Asia/Shanghai)
#### Current Progress
- Project role boundary updated: Codex is now authorized as a decision Agent and can maintain relevant project/module/progress/decision docs directly.
- Group/Hall docs synced after `GROUP-1 / HALL-1`: added `docs/MODULE_groups.md`.
- Updated `docs/PROJECT_BRIEF.md` with `groups`, `group_members`, `messages.group_id`, `server/routes/groups.py`, the module index entry, and the 2026-05-14 Group/Hall addendum.
#### Open Questions / Pending Confirmation
- None for documentation sync.
#### Next Plan
- Commit the current Web UI + Group/Hall backend + documentation set when accepted.
- Then choose the next slice: Web UI Group/Hall navigation, SDK group helpers, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/MODULE_groups.md`
- `docs/PROGRESS.md`

### 2026-05-14 15:54 (Asia/Shanghai)
#### Current Progress
- `GROUP-1 / HALL-1` backend first slice completed from the confirmed contract.
- Added `groups` and `group_members` tables, `messages.group_id`, startup migration/index creation, `/api/groups` creation/list/detail/member add/update/remove APIs, and group-scoped message send/history behavior.
- Group Hall visibility now treats `to_ids` as mention/attention inside a Group: all Group members can read the Hall timeline, while non-members are rejected and old unscoped message history remains legacy/global only.
#### Open Questions / Pending Confirmation
- Documentation sync for `docs/PROJECT_BRIEF.md` and a new/updated Group/Hall module doc still needs explicit approval.
- Web UI Group/Hall navigation and SDK helpers are not implemented yet.
#### Next Plan
- If approved, sync Group/Hall docs and commit the current work.
- Otherwise continue with one follow-up slice: Web UI Group/Hall navigation, SDK group helpers, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_groups` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_messages` passed with `23` tests.
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
- `.venv\Scripts\python.exe -m unittest` passed with `81` tests.
#### Changed Files
- `server/models.py`
- `server/db.py`
- `server/main.py`
- `server/routes/groups.py`
- `server/routes/messages.py`
- `server/ws_hub.py`
- `tests/test_groups.py`
- `tests/test_messages.py`
- `tests/test_support.py`
- `docs/PROGRESS.md`

### 2026-05-14 15:15 (Asia/Shanghai)
#### Current Progress
- Resumed from `WEB-VISUAL-2` and reviewed the current Web UI diff instead of starting a new backend slice.
- Verified the real login page and authenticated chat page with Chrome headless at desktop and 500px widths.
- Fixed a CSS cascade bug where `.drop-hint` overrode Tailwind `.hidden`, causing the drag/drop overlay to stay visible over the composer when no file was being dragged.
#### Open Questions / Pending Confirmation
- `docs/USER.md` remains an untracked local credential note; it should not be committed as-is.
#### Next Plan
- Decide how to handle `docs/USER.md`, then commit the accepted Web UI visual changes.
- After Web UI is committed, choose the next backend/product slice: schedule API, Group/Hall, SSE, document-edit lock API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `git diff --check` passed with line-ending warnings only.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- Chrome headless screenshots verified real login and authenticated chat pages; `#drop-hint` computed as `display: none` at 1440px and 500px.
#### Changed Files
- `web/style.css`
- `docs/PROGRESS.md`

### 2026-05-14 11:35 (Asia/Shanghai)
#### Current Progress
- `WEB-VISUAL-2` completed from the approved `image_gen` visual direction: the chat page now uses a `header + workspace-tools + messages + composer` structure.
- Online members and history/search controls are grouped into one workspace tools panel; the message timeline and composer now read as a single chat work area.
- The left channel/conversation area shown in the visual mockup remains deferred until the Group/Hall model exists, so the current page does not expose fake navigation.
#### Open Questions / Pending Confirmation
- Real authenticated chat-page acceptance still depends on manual review in the user's browser session or a dedicated non-private test account.
#### Next Plan
- If the layout is accepted, commit the Web UI visual changes; then return to backend model work, likely Group/Hall or SSE, so future navigation/sidebar UI has real data behind it.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- `GET http://127.0.0.1:8000/` returned `200`.
- Chrome headless screenshot checks completed for the real login page and a temporary chat-shell preview at desktop and 500px widths.
#### Changed Files
- `web/index.html`
- `web/style.css`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 11:10 (Asia/Shanghai)
#### Current Progress
- `WEB-VISUAL-1` completed: login/setup now uses a unified dark card treatment with Chinese copy, branded mark, clearer fields, and primary/secondary button hierarchy.
- Chat workspace styling was refreshed across header, presence strip, search toolbar, timeline background, message bubbles, reply/file cards, and bottom composer.
- Added responsive safeguards for narrow screens: constrained auth card width, wrapping toolbar controls, composer min-width fixes, and stronger long-message wrapping.
#### Open Questions / Pending Confirmation
- Real authenticated chat-page visual acceptance still depends on manual review or a provided non-private test login key; Codex in-app browser automation continues to time out when connecting.
#### Next Plan
- Review the visual result in a normal browser session; if accepted, commit and push `WEB-VISUAL-1`.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- Chrome headless screenshot checks completed for the real login page and a temporary chat-shell preview using the current served `style.css`.
- Codex in-app browser automation retry still timed out while connecting.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:55 (Asia/Shanghai)
#### Current Progress
- Re-ran full backend regression after the Web UI polish changes; all `74` unit tests passed.
- Confirmed the local TALK service health endpoint still returns `status=ok`.
#### Open Questions / Pending Confirmation
- Visual acceptance still depends on browser/manual review; automated in-app browser control was previously timing out in this environment.
#### Next Plan
- Commit and push the Web UI polish changes if the current UI review scope is accepted.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- `GET http://127.0.0.1:8000/healthz` returned `status=ok`.
- In-app browser automation retry against `http://127.0.0.1:8000/` timed out while connecting.
#### Changed Files
- `docs/PROGRESS.md`

### 2026-05-14 10:49 (Asia/Shanghai)
#### Current Progress
- `CHAT-UI-1` completed from browser review comments: search toolbar, composer controls, drag/drop hint, logout, remove-file, cancel-reply, and send/file labels are now Chinese.
- Search toolbar now separates primary search from secondary clear/load-more actions; composer now has a defined container and distinct file/input/send controls.
- Empty message timeline now shows a Chinese empty-state explanation instead of a visually unexplained blank area.
#### Open Questions / Pending Confirmation
- Visual acceptance still depends on manual refresh because Codex in-app browser automation is still timing out when connecting to the browser runtime.
#### Next Plan
- If the chat UI review is accepted, commit and push the Web UI polish changes.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:15 (Asia/Shanghai)
#### Current Progress
- `SETUP-UX-2` follow-up completed: added cache-busting query strings for `/style.css` and `/app.js`, placed the create-admin button contrast styles directly in HTML classes, and replaced raw Clipboard API permission errors with Chinese copy-fallback guidance.
- If browser copy permission is denied, the setup key field is focused and selected so the user can press `Ctrl+C` manually.
#### Open Questions / Pending Confirmation
- Whether to replace the current API-key-first login model with a human password flow is a product/auth decision. Recommended direction is dual-mode auth: human password login with hashed password plus generated API keys for Agent/SDK use.
#### Next Plan
- If approved, design `AUTH-2`: password-based human login without breaking existing `X-API-Key` Agent authentication.
#### Verification
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:01 (Asia/Shanghai)
#### Current Progress
- `SETUP-UX-2` completed from browser diff comments: added a visible `管理员 ID` format hint, changed `显示名称` to `昵称`, added client-side `human:*` validation, and restyled `创建管理员` as a compact bordered primary button.
- Synced `docs/MODULE_webui.md` to reflect the updated first-admin setup labels and ID-format hint.
#### Open Questions / Pending Confirmation
- In-app browser automation currently times out while connecting to the browser runtime, so the page needs a manual refresh or later browser recheck for visual confirmation.
#### Next Plan
- Continue with the next local-lab slice after UI review is accepted: schedule API, Group/Hall room model, SSE stream contract, document-edit lock API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `GET http://127.0.0.1:8000/` returned `200`.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-13 16:07 (Asia/Shanghai)
#### Current Progress
- `TASK-1` completed: added `AgentTask` / `AgentTaskCreate` / `AgentTaskClaim` / `AgentTaskComplete` / `AgentTaskOut`, `/api/tasks`, database indexes, async SDK helpers, sync SDK wrappers, and documentation.
- Task API first slice supports creating queued tasks for existing `agent:*` members, listing visible tasks, Agent-only claim, and Agent-only completion as `succeeded` / `failed` / `canceled`.
- Task claim and completion now update linked `AgentInstance`: claim sets `busy` and `current_task_id`; success/cancel returns to `idle`; failure sets `error` and `last_error`.
- Project rule updated in `AGENTS.md`: development execution Agents may directly update `docs/PROGRESS.md` after actual code, test, or documentation work.
- Documentation synced across project brief, SDK, local-lab design, instances module, and new tasks module.
#### Open Questions / Pending Confirmation
- Schedule API is still not implemented: delayed / recurring trigger shape remains open.
- Retry, task timeout recovery, stale `running` cleanup, requeue/cancel UI, and Codex bridge task-queue consumption remain future work.
#### Next Plan
- Choose the next local-lab slice: schedule API, Group/Hall room model, SSE stream contract, document-edit lock API, or Codex bridge task-queue integration.
- If continuing scheduler work, define whether schedules create one-off tasks at trigger time and how failed scheduled tasks should be retried or surfaced.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_tasks` passed with `7` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client.TalkClientTests.test_task_helpers` passed.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
#### Changed Files
- `AGENTS.md`
- `server/models.py`
- `server/routes/tasks.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_tasks.py`
- `tests/test_talk_client.py`
- `docs/PROJECT_BRIEF.md`
- `docs/MODULE_instances.md`
- `docs/MODULE_tasks.md`
- `docs/LOCAL_LAB_DESIGN.md`
- `docs/SDK.md`
- `docs/PROGRESS.md`

### 2026-05-13 15:47 (Asia/Shanghai)
#### Current Progress
- `INSTANCE-1` completed: added `AgentInstance` / `AgentInstanceUpdate` / `AgentInstanceOut`, `/api/instances`, database indexes, SDK helpers, and module documentation.
- Codex bridge now reports its runtime instance state with a stable optional `--instance-id`; task handling updates status to `busy`, success returns to `idle`, failures become `error`, and shutdown reports `offline`.
- Added coverage for instance API permissions, ownership protection, filters, invalid status validation, and SDK helpers.
#### Open Questions / Pending Confirmation
- Task and schedule API semantics are still not implemented: task table shape, retry behavior, process ownership, and scheduler/bridge responsibility split remain open.
- Group / Hall / SSE / document-lock implementation details remain pending after this instance-status foundation.
#### Next Plan
- Choose the next local-lab slice: scheduler task API, Group/Hall room model, SSE stream contract, or document-edit lock API.
- When scheduler work starts, decide whether TALK launches bridge processes or only routes tasks to already-running instances.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_instances tests.test_talk_client tests.test_codex_bridge` passed with `19` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `66` tests.
- Isolated bridge instance smoke passed: `idle -> busy -> idle -> offline`, reply content `TALK_BRIDGE_INSTANCE_SMOKE_OK`.
#### Changed Files
- `server/models.py`
- `server/routes/instances.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `bridges/codex_bridge.py`
- `tests/test_instances.py`
- `tests/test_talk_client.py`
- `docs/MODULE_instances.md`
- `docs/MODULE_bridges.md`
- `docs/LOCAL_LAB_DESIGN.md`
- `docs/PROJECT_BRIEF.md`
- `docs/SDK.md`
- `docs/PROGRESS.md`

### 2026-05-13 15:24 (Asia/Shanghai)
#### Current Progress
- Created an ignored local `.venv` from `requirements.txt`; dependency imports resolved consistently there (`pydantic 2.13.4`, `pydantic-core 2.46.4`, `fastapi 0.136.1`, `websockets 15.0.1`).
- Full regression passed: `.venv\Scripts\python.exe -m unittest` ran `60` tests successfully.
- Real Codex bridge smoke test passed with isolated temporary TALK server/database/storage: `human:smoke` sent `@agent:codex`, the bridge invoked real `codex exec --sandbox read-only`, and the reply used `reply_to` with content `TALK_BRIDGE_SMOKE_OK`.
#### Open Questions / Pending Confirmation
- Codex bridge remains MVP-level and still needs instance status, streaming, file/material handling, and document-lock integration.
- The `pi` framework path for DeepSeek / Kimi still needs local verification.
#### Next Plan
- Choose the next implementation slice: bridge instance status, Group/Hall model, SSE streaming contract, or document-edit lock API.
- Continue the local-lab protocol design before broad service-model changes.

### 2026-05-13 15:10 (Asia/Shanghai)
#### Current Progress
- Added `docs/LOCAL_LAB_DESIGN.md` as the thin local-lab design note.
- Added `bridges/codex_bridge.py` as the Codex bridge MVP: direct text message in, configurable `codex exec` invocation, `reply_to` answer out.
- Added `docs/MODULE_bridges.md` and updated `docs/PROJECT_BRIEF.md` to register the new bridge module.
- Added `tests/test_codex_bridge.py` covering bridge routing, prompt construction, reply formatting, and subprocess stdin piping.
#### Open Questions / Pending Confirmation
- Real TALK server smoke test for Codex bridge remains pending.
- Full test suite is blocked by the local `.codex_pydeps` pydantic / pydantic-core mismatch.
#### Next Plan
- Clean or rebuild the Python dependency environment, then run full tests.
- Start TALK locally, run the Codex bridge, and verify one `@agent:codex` browser-to-bridge-to-reply loop.
- After the smoke test, continue with Group / Hall / SSE / instance-scheduler design and implementation.

### 2026-05-12 17:36 (Asia/Shanghai)
#### Current Progress
- Product decisions confirmed: DeepSeek / Kimi will use the locally installed `pi` framework; TALK should add Groups, Hall shared timeline mode, SSE streaming, and instance/scheduling API layers.
- A document editing coordination protocol is now required so multiple Agents do not edit the same document at the same time.
- Existing communication specs were checked. Current TALK supports member identity, API-key auth, server-side leading-mention routing, broadcast/direct/group-style `to_ids`, REST polling, WebSocket events, file exchange, replies, and SDK callbacks, but not a formal discussion protocol or document lock protocol.
- Temporary role decision: until the next progress summary, Codex may act as both decision Agent and execution Agent because the dedicated decision Agent is unavailable.
#### Open Questions / Pending Confirmation
- Document editing coordination still needs exact rules for lock scope, timeout, stale-lock recovery, conflict handling, and UI/API visibility.
- The local `pi` framework needs a quick workstation-level verification before bridge implementation.
#### Next Plan
- Write the next-phase local-lab design note covering bridge layout, `pi` integration, Groups, Hall, SSE, instance/scheduler APIs, and document-edit coordination.
- Define the first moderator-led multi-Agent discussion protocol before implementation.
- Implement the minimum local-lab path after the protocol and data model changes are stable.

### 2026-04-24 23:11 (Asia/Shanghai)
#### Current Progress
- `DOC-2` completed: fixed the remaining mojibake deployment section in `CLAUDE.md`, added explicit UTF-8 write rules plus SDK import-path notes to `AGENTS.md` / `CLAUDE.md`, and added `tests/test_encoding.py` as an encoding regression guard.
- Full regression still passes with `54` tests, including `3` new encoding-guard cases.
- The intended usage model is now explicit: TALK is a local home-LAN multi-Agent lab used on demand while the local computer is on, not a 24/7 permanently running service.
- The planned backend mix is now explicit: `Claude Code` / `Codex` through local CLI bridges, and `Kimi` / `DeepSeek` through API bridges.
- The next product direction is now explicit: moderator-led AI discussion with automatic transcript retention and support for passing shared documents/materials during the discussion.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/QUICKSTART_USER.md` has not yet been run end-to-end by a first-time non-project user, so there may still be hidden onboarding assumptions.
- The discussion phase still needs a concrete protocol for moderator behavior, round limits, material-sharing rules, and summary output.
#### Next Plan
- Write the next-phase design note for local experimental mode and one-command startup.
- Define a unified bridge contract for mixed CLI/API Agent backends.
- Define the first moderator-led discussion protocol with transcript retention, bounded rounds, and material passing.
- Implement the minimum local-lab path first, then return to lower-priority deployment validation tasks.

### 2026-04-24 22:01 (Asia/Shanghai)
#### Current Progress
- `DOC-1` completed: split onboarding into `docs/QUICKSTART_USER.md` and `docs/QUICKSTART_AGENT.md`, and reduced `docs/QUICKSTART.md` to a short index page.
- `QUICKSTART_USER` now follows a family-user path with Docker Desktop, explicit browser verification, `config.toml` before/after examples, LAN IP lookup, and ordered troubleshooting.
- `QUICKSTART_AGENT` now follows a Python bare-metal + SDK path with PowerShell/bash command pairs, real example repo URLs, and a full runnable Agent sample.
- `docs/DEPLOY.md` now includes prerequisites for Docker Compose, Linux `systemd`, and bare metal deployment.
- `docs/SDK.md` async examples now all include `asyncio.run(main())`, and `SETUP-1` now supports browser-side key generation, reveal/hide, and one-click copy in the first-admin UI.
- Related docs were synced after implementation, and full regression still passes with `51` unit tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/QUICKSTART_USER.md` has not yet been run end-to-end by a first-time non-project user, so there may still be hidden onboarding assumptions.
- The task card asks for a second clean-session newcomer dry run and readability feedback; that external acceptance has not been performed yet in this environment.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/DEPLOY.md`.
- Run one real browser smoke test for `SETUP-1` on a fresh DB and confirm the first-run form, generated key, automatic sign-in, and second-open login behavior match the task card.
- Run one clean-session newcomer walkthrough against `docs/QUICKSTART_USER.md`, collect friction points, and trim any remaining expert assumptions.

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
