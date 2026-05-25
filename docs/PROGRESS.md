# Project Progress

## Latest
Updated: 2026-05-25 11:41 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `PI-MINIMAL-PROMPT-1` 已完成：按项目管理者确认，将 pi bridge 的输入包装改为“用户原话优先”的极简 prompt，降低英文元指令抢占用户语境导致的语言跑偏。
- `bridges/cli_bridge.py` 中 pi 消息 prompt 现在以 `用户消息：` 开头，直接放去掉 `@agent:pi` 后的原话；pi 队列任务 prompt 以 `用户任务：` 开头，只有任务标题存在时才作为用户任务内容的一部分保留。
- pi prompt 后置一条极简中文边界：`你是 TALK 群聊里的 pi，按用户语言自然回复。默认不要声称能读取项目文件、执行命令、编辑文件或调用工具。不要输出 <Language: ...> 之类语言标签。`
- pi prompt 不再包含 `Sender:`、`TALK message id:`、`TALK task id:`、`Task creator:` 或 `TALK group id:`；但 bridge 回复仍保留原消息 `group_id`，Group Hall 回复路径不变。
- 非 pi runtime 的执行型 prompt 保持不变；Codex bridge 不受本次调整影响。
- `normalize_pi_reply_language(...)` 保留为异常兜底：中文请求得到非中文/语言标签时才替换；正常中文回复或用户明确要求英文时不干预。
- `docs/MODULE_bridges.md` 已同步 pi 极简 prompt 边界。

### 3) Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次极简 prompt 修复。
- 重启后建议在同一个 Group Hall 重新验收：`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 旧消息 `#39` / `#41` 已写入数据库，历史内容不会自动改写；本次修复只影响后续新回复。
- Codex + pi 双 Agent 同时运行的真实端到端回合仍需继续人工验收；本里程碑还需覆盖 Web UI 视觉/交互。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交本次 `PI-MINIMAL-PROMPT-1` 修复。
2. 用户重启 pi bridge 后，继续在 Group Hall 验收 pi 中文/英文语言跟随和能力边界。
3. 继续当前范围冻结分支的 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
4. 验收通过后，再基于 OpenHanako 参考评估下一阶段多 Agent 自动讨论协议。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，22 tests。
- 分组显式全量 passed，合计 120 tests：`tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_pi_bridge` 34 tests；`tests.test_files tests.test_groups tests.test_healthz tests.test_members_auth tests.test_messages` 40 tests；`tests.test_instances tests.test_tasks tests.test_talk_client` 27 tests；`tests.test_setup tests.test_sse tests.test_websocket` 19 tests。
- `.venv\Scripts\python.exe -u -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_files tests.test_groups tests.test_healthz tests.test_instances tests.test_members_auth tests.test_messages tests.test_pi_bridge tests.test_setup tests.test_sse tests.test_talk_client tests.test_tasks tests.test_websocket` 本轮单条运行 300 秒超时且无失败栈；分组运行同一模块集合全部通过。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
