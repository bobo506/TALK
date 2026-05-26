# Project Progress

## Latest
Updated: 2026-05-27 00:06 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- 已在分支 `codex/scenario-1-scope-fix` 完成场景 1 针对性调整：收口阈值改为只统计实质 turn，避免把打招呼/在线确认当成议题讨论轮次。
- `discussion_turns.stance` 白名单新增 `greeting / closure`；bridge 会把明确的打招呼/在线确认类短消息记录为 `greeting`，自动收口消息记录为 `closure`。
- `greeting / closure` 被视为非实质 turn，不计入普通收口或分歧升级阈值；`disagree` 仍保留 human 裁决路径。
- `_send_agent_scope_closure()` 保留硬兜底 `resolved` 状态更新，但收口话术改为按 agent id 稳定挑选，避免不同 agent 复读同一句固定机器话。
- 文档已同步 `docs/MODULE_discussions.md`、`docs/MODULE_bridges.md`。

### 3) Open Questions / Pending Confirmation
- 本轮仍按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续可由无项目记忆的黑盒测试 agent 复验场景 1。
- `greeting` 识别采用保守规则：任务范围像打招呼/在线确认，且回复较短、包含问候/在线确认特征时才标记为非实质 turn；其它回复仍默认 `answer`。
- `docs/p.drawio` 作为本次协议评估输入保留在工作区，未被本切片修改；当前仍是未跟踪文件。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交 `SCENARIO1-GREETING-TURNS-1`。
2. 项目管理者重启 server / Codex bridge / pi bridge 后，优先复验黑盒场景 1：打招呼不应过早收口，也不应复读固定收口话术。
3. 若场景 1 通过，再继续处理测试文档中的下一类问题。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions tests.test_pi_bridge` passed，57 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` first run hit existing WebSocket fallback timing timeout once; immediate rerun passed，11 tests。
- `usage-gate guard --provider codex --json` decision=`pause_before_next_slice`，weekly=84%，本轮提交后不再开启新切片。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `server/models.py`
- `tests/test_cli_bridge.py`
- `tests/test_discussions.py`
- `docs/MODULE_discussions.md`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
