# Project Progress

## Latest
Updated: 2026-05-25 16:10 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `DISCUSSION-PROTOCOL-1` 已完成：新增可记录多 Agent 讨论 session/turn 数据模型与 API，正文仍以 Group Hall `messages` 为真相源，turn 只引用 `message_id`。
- 新增 `server/routes/discussions.py`，支持创建/读取/更新 discussion、追加/查询 ordered turns；非 Group 成员不可创建或读取，同一 turn 只能引用当前成员本人在同一 Group Hall 的消息。
- SDK 已新增 async/sync discussion helper：创建、列表、读取、状态更新、追加 turn、查询 turns。
- bridge 已支持 `talk-action` 动作协议：`send_message` 可同 Hall 代发 `@agent:*` 并建档，`mark_stance` 可记录 `answer/agree/optimize/disagree`，两条不同 agent 连续 `disagree` 后会自动 `@human:*` 请求最终判断。
- pi 默认仍是讨论档，保留 `--no-context-files --no-tools --no-session --thinking off`；新增 `--pi-execution-profile tools`，仅显式启用时允许 pi CLI 子进程使用 `read,grep,find,ls,bash,edit,write`。
- 新增 `docs/MODULE_discussions.md`，并同步 `PROJECT_BRIEF`、`MODULE_groups.md`、`MODULE_bridges.md`。

### 3) Open Questions / Pending Confirmation
- 需要用户重启 codex/pi bridge；正在运行的旧 bridge 不会加载 `talk-action` 协议和 pi 新 system prompt。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Codex + pi 双 Agent 真实端到端讨论回合仍需人工验收。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交本次 `DISCUSSION-PROTOCOL-1` 切片。
2. 重启 bridge 后，在 Group Hall 人工验收：让 Codex 给 pi 转交下一步计划，pi 回复同意/优化/分歧。
3. 后续可补 Web UI discussion 面板，显示 session、turn 顺序、stance 和升级仲裁提示。
4. 再评估是否把 discussion 与任务队列、文档锁、SSE 流式输出联动。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py server\main.py TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\cli_bridge.py bridges\pi_bridge.py tests\test_discussions.py tests\test_cli_bridge.py tests\test_pi_bridge.py tests\test_talk_client.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge tests.test_pi_bridge` passed，30 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge tests.test_groups tests.test_messages` passed，37 tests。
- `.venv\Scripts\python.exe -m unittest` passed，128 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。

### 6) Changed Files
- `server/models.py`
- `server/routes/discussions.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_discussions.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_talk_client.py`
- `docs/PROJECT_BRIEF.md`
- `docs/MODULE_discussions.md`
- `docs/MODULE_groups.md`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
