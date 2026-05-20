# Project Progress

## Latest
Updated: 2026-05-20 23:16 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `TASK-SCHEDULE-1` 已完成：新增 `agent_task_schedules` 表与 `/api/tasks/schedules` API 第一版。
- Schedule 支持一次性与周期性计划、可见性过滤、暂停/取消状态更新，以及显式 `POST /api/tasks/schedules/run-due` 物化到 `queued` task。
- `agent_tasks` 新增可选 `schedule_id`，用于追踪 schedule 物化出的任务。
- SDK 已新增 async/sync schedule helper。
- `docs/MODULE_tasks.md` 与 `docs/PROJECT_BRIEF.md` 已同步数据模型、接口契约、边界和验收点。

### 3) Open Questions / Pending Confirmation
- Group 删除 / 归档语义仍需项目管理者确认：历史 Hall 消息应保留、归档还是随 Group 删除。
- Schedule 当前仅记录并显式物化，不内置后台调度循环；后续需决定由 bridge 轮询、系统定时脚本，还是服务端后台 worker 触发。
- 未读/关注状态、文档编辑锁仍待实现。

### 4) Next Plan
1. 提交本次 `TASK-SCHEDULE-1` 切片。
2. 下一候选切片：文档编辑锁协议，或将任务 / schedule 状态接入 Hall / Group Web UI。
3. Group 删除 / 归档语义需项目管理者确认后再做。

### 5) Verification
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/slice-usage-gate.ps1 -Agent codex` returned `continue`。
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\tasks.py server\db.py tests\test_tasks.py tests\test_talk_client.py TALK\client\talk_client.py TALK\client\talk_client_sync.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks tests.test_talk_client` passed，22 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，97 tests。
- `git diff --check` passed（仅换行提示）。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-progress.ps1 -Strict -RequireHistory` passed。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-git-ready.ps1` passed。

### 6) Changed Files
- `server/models.py`
- `server/routes/tasks.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_tasks.py`
- `tests/test_talk_client.py`
- `docs/MODULE_tasks.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
