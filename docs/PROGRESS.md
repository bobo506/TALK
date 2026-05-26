# Project Progress

## Latest
Updated: 2026-05-26 18:16 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `BRIDGE-SAFE-EXTEND-1` 已完成：修复黑盒测试暴露的 bridge 输出安全、开头多 mention、非 Group agent 委托和轻扩展收口问题。
- bridge 现在把消息开头连续 `@member_id` 块视为路由头，传给 CLI 的任务正文会剥离整段路由头；正文中间的 `@agent:*` 仍保留。
- CLI 失败/超时时，聊天可见回复只显示简短失败提示，不再回显 `stderr / stdout / traceback / 本地路径`；任务 `last_error` 仍可记录详细错误。
- malformed 动作协议或内部控制语法残留不会展示到可见回复；`send_message` 目标必须是当前 Group 内存在的 `agent:*`。
- 普通轻扩展允许对方再回答 1 个 turn；随后收到回复的一方自动收口并将 discussion 标记为 `resolved`。`disagree` 场景仍保留 human 裁决路径。
- 文档已同步 `docs/MODULE_discussions.md`、`docs/MODULE_bridges.md`。

### 3) Open Questions / Pending Confirmation
- 本轮仍按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续由无项目记忆的黑盒测试 agent 复验自然对话效果。
- malformed 协议残留拦截采用“控制语法特征”隔离，不做自然语言意图分类；如果未来模型出现新型协议泄漏，可继续收敛规则。
- `docs/p.drawio` 作为本次协议评估输入保留在工作区，未被本切片修改；当前仍是未跟踪文件。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交 `BRIDGE-SAFE-EXTEND-1`。
2. 重启当前正在运行的 Codex / pi bridge，使新 bridge 逻辑生效。
3. 让无项目记忆测试 agent 复验：多 mention 不报路径错误、`TALK_ACTION` 残留不显示、缺失 agent 不代发、轻扩展只多一轮并收口。
4. 复验通过后，再拆下一批使用建议：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions` passed，52 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- `usage-gate guard --provider codex --json` decision=`continue`，session=82%，weekly=76%。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/MODULE_discussions.md`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
