# Project Progress

## Latest
Updated: 2026-05-20 10:38 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `SSE-BACKFILL-1` 已完成：`GET /api/events` 已支持 `Last-Event-ID` header 与 `last_event_id` query 参数。
- SSE 重连后会先完成实时订阅，再按当前成员可见性补发 `message.id > last_event_id` 的历史消息快照，并对补发与实时队列中的同 id 事件做去重。
- 补发会过滤不可见消息；撤回消息按当前 `MessageOut` 快照语义补发为 `revoked=true` 且隐藏正文/文件快照字段。
- `docs/MODULE_websocket.md` 已同步本切片接口契约、当前实现与验收标准。

### 3) Open Questions / Pending Confirmation
- 当前环境仍未暴露精确 token/5 小时额度占比；后续继续按批次、工作时长、上下文接近上限与两项软停止信号控制连续开发。
- Browser runtime 初始化问题仍待从 Codex Desktop / Browser 后端侧恢复后补测。
- Group 重命名/删除控制、未读/关注状态、文档编辑锁、schedule API、Codex bridge task-queue integration 仍待实现。

### 4) Next Plan
1. 提交本次 `SSE-BACKFILL-1` 切片。
2. 下一候选切片：Group 重命名/删除 UI，或 Codex bridge task-queue integration。
3. Browser runtime 恢复后，补一次 Web UI SSE 真实浏览器烟测。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile server\main.py tests\test_sse.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed，6 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_sse tests.test_websocket tests.test_messages` passed，39 tests。
- `.venv\Scripts\python.exe -m unittest` passed，88 tests。
- `git diff --check` passed，仅有换行提示。

### 6) Changed Files
- `server/main.py`
- `tests/test_sse.py`
- `docs/MODULE_websocket.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
