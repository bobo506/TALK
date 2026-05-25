# Project Progress

## Latest
Updated: 2026-05-26 01:22 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `DISCUSSION-FSM-TOKEN-SAFE-1` 已完成：按 `docs/p.drawio` 的提问/回答/同意/反例/人工决定思路，为 bridge 讨论协议加入有限状态控制与省 token 护栏。
- bridge 现在兼容旧 `<talk-action ...>`，并新增推荐的 `TALK_ACTION ...` 安全行协议；pi 默认 system prompt 只教授安全行协议，继续避开 `| / < / > / &` 等 Windows 高风险命令元字符。
- 新增 `final_to_human` 动作：达成共识后可把最终答案发给 human，并把 discussion 标为 `resolved`。
- agent-to-agent 讨论默认最多 3 个自动 turn，最近一条为 `disagree` 时最多额外 1 个 turn；超限后不再调用模型，直接 `@human:*` 升级并标记 `escalated`。
- agent-to-agent prompt 会注入极短讨论上下文，约束只围绕原始话题，避免再次跑到 docs、版本号、施工档等无关内容。
- bridge 会清理 `mark_stance`、`update`、`动作已记录...` 等孤立协议残片；模型只输出动作且来源是另一个 agent 时，不再额外发送默认回执触发对方 bridge。

### 3) Open Questions / Pending Confirmation
- 需要重启 codex bridge 与 pi bridge；正在运行的旧 bridge 进程不会自动加载新的协议解析、回合上限和 pi 默认 `--system-prompt`。
- `docs/p.drawio` 作为本次协议评估输入保留在工作区，未被本切片修改；当前仍是未跟踪文件。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Codex + pi 双 Agent 真实端到端讨论回合仍需在重启 bridge 后人工验收。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交本次 `DISCUSSION-FSM-TOKEN-SAFE-1` 切片。
2. 重启 codex bridge 与 pi bridge；如 server 仍是旧进程，也建议一并重启 TALK server。
3. 重新验收：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
4. 在 Hall 中确认：pi 不再露出 `mark_stance`，讨论不再跑到 docs/specmate 话题，Codex 不再跟随偏题，自动回合数受限，达成共识后能回给 human 或超限转人工。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，34 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions` passed，37 tests。
- 分批验证 passed：`tests.test_codex_bridge tests.test_groups tests.test_messages` 37 tests；`tests.test_files tests.test_healthz tests.test_instances tests.test_members_auth tests.test_tasks` 28 tests；`tests.test_encoding tests.test_setup` 6 tests；`tests.test_talk_client` 11 tests；`tests.test_sse` 6 tests。
- `tests.test_websocket` 聚合运行在当前环境超时；已用逐用例 30s 超时脚本验证 `WebSocketTests` 10 个用例全部单独 passed。
- `.venv\Scripts\python.exe -m unittest` 当前环境超时，未作为通过项记录。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/MODULE_bridges.md`
- `docs/MODULE_discussions.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
