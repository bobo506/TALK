# Project Progress

## Latest
Updated: 2026-05-25 16:21 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `DISCUSSION-PROTOCOL-1-HOTFIX-1` 已完成：修复 bridge 在 `/api/discussions` 返回 404 时直接抛 `TalkNotFoundError` 的问题。
- 根因：bridge 已加载 `talk-action` 协议，但 TALK server 可能仍是旧进程或尚未接入新路由，`client.list_discussions(...)` 404 未被降级处理。
- 现在 discussion API 不可用时，bridge 会跳过 discussion session/turn 记录，但继续执行 `send_message` 代发和可见回复，避免“问 pi / 问 codex”流程中断。
- 新增单元测试覆盖 discussion API 缺失时的降级代发路径。

### 3) Open Questions / Pending Confirmation
- 仍建议重启 TALK server、codex bridge、pi bridge，让 `/api/discussions` 与新 `talk-action` 协议都运行在同一版本；热修复只保证旧 server 404 时不崩，但不会记录 discussion turn。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Codex + pi 双 Agent 真实端到端讨论回合仍需人工验收。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交本次 hotfix。
2. 重启 TALK server、codex bridge、pi bridge 后，重试：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
3. 如 server 已重启到新版本，检查 `/api/discussions` 是否记录 session/turn；如未重启，至少应完成代发而不再抛 404。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_discussions tests.test_pi_bridge` passed，31 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
