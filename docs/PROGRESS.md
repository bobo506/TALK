# Project Progress

## Latest
Updated: 2026-05-26 15:17 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `DISCUSSION-SCOPE-1` 已完成：为多 Agent 自动交流加入“请求者局部范围”约束，回复必须围绕当前直接提问/派活者的请求。
- `discussion_sessions` 新增可选范围锚点：`root_message_id / requester_id / assignee_id / scope_text`；旧记录允许为空，`init_db()` 会为既有 SQLite 表补列和索引。
- bridge 现在优先沿 `reply_to` / `root_message_id` 复用 discussion scope；已 `resolved / escalated / canceled` 的 scope 不再因普通 agent 回复继续触发模型续聊。
- agent-to-agent prompt 会传入控制上下文和消息原文，要求模型服从当前 scope 且不要把内部 ID/字段展示到可见回复；若可见回复泄漏内部字段，bridge 会替换为确认范围的简短回复。
- agent 普通可见回复若属于 active discussion，即使没有显式 `mark_stance`，也会按 `answer` 记录 turn。
- 文档已同步 `docs/PROJECT_BRIEF.md`、`docs/MODULE_discussions.md`、`docs/MODULE_bridges.md`。

### 3) Open Questions / Pending Confirmation
- 本轮按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续由无项目记忆的黑盒测试 agent 验收自然对话效果。
- 范围越界识别当前主要依赖结构化 scope、prompt 约束和内部字段泄漏拦截；未做复杂自然语言分类。
- `docs/p.drawio` 作为本次协议评估输入保留在工作区，未被本切片修改；当前仍是未跟踪文件。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交 `DISCUSSION-SCOPE-1`。
2. 准备黑盒验收任务单，让无项目记忆测试 agent 验证“打招呼不发散”“agent 给 agent 派活不偏题”“内部字段不泄漏”。
3. 验收通过后，再拆下一批使用建议：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py server\db.py TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\cli_bridge.py tests\test_discussions.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge` passed，38 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。

### 6) Changed Files
- `server/models.py`
- `server/routes/discussions.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `tests/test_discussions.py`
- `tests/test_cli_bridge.py`
- `docs/PROJECT_BRIEF.md`
- `docs/MODULE_discussions.md`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
