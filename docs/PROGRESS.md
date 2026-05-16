# Project Progress

## Latest
Updated: 2026-05-16 19:04 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `WEB-SSE-UI-1` 已完成：Web UI 已接入 `GET /api/events?token=...` SSE 事件流作为实时兜底。
- 浏览器优先使用 WebSocket；当前浏览器不支持 WS、WS 断开或报错时会打开 SSE，WS 恢复后主动关闭 SSE。
- SSE 与 WS 共用前端实时事件处理逻辑，统一处理 `message / revoke / presence`；HTTP 轮询仍保留为事件缺口补漏通道。

### 3) Open Questions / Pending Confirmation
- Codex in-app Browser 插件本轮连接超时，未完成真实浏览器前端烟测；已用静态检查、SSE/WS 回归和全量后端测试覆盖主要风险。
- SSE `Last-Event-ID` replay/backfill 尚未实现；当前仍依赖历史接口与 HTTP 轮询补漏。
- Group 重命名/删除控制、未读/关注状态、文档编辑锁、schedule API、Codex bridge task-queue integration 仍待实现。

### 4) Next Plan
1. 提交并推送本次 Web UI SSE 兜底切片。
2. 下一候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
3. 如浏览器插件恢复可用，补一轮真实 Web UI SSE 兜底烟测。

### 5) Verification
- `node --check web\app.js` passed。
- `git diff --check` passed，仅有换行提示。
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed，3 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_websocket` passed，10 tests。
- `.venv\Scripts\python.exe -m unittest` passed，85 tests。
- Browser 插件连接两次超时；临时隔离服务已关闭并清理。

### 6) Changed Files
- `web/app.js`
- `web/index.html`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
