# Project Progress

## Latest
Updated: 2026-05-25 11:16 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `PI-LANGUAGE-REPLY-1` 验收期修复已完成：排查确认最近 Group Hall 消息 `#38 -> #39` 中，用户中文询问 pi 功能后 pi 回复 `<Language: ar>` 阿拉伯语；`#40 -> #41` 中用户明确“用中文回复”后 pi 仍回复英文，并误称自己能读文件、执行命令、编辑文件。
- 根因判断：Group Hall 路由与同 Hall 回复正常，问题集中在 pi 的默认 TALK prompt 语言约束不足，以及撤销强 system prompt 后缺少窄范围的语言/能力兜底。
- `bridges/cli_bridge.py` 已新增 `PI_CHAT_INSTRUCTIONS`：pi 仍作为自然聊天的 TALK chat member，但明确要求回复语言跟随用户输入；用户要求中文时使用简体中文；禁止输出 `<Language: ...>` 标签；能力介绍不得声称默认 bridge 模式具备读文件、执行命令、编辑文件或调用工具能力。
- `bridges/cli_bridge.py` 已新增只针对 pi 成功输出的中文兜底：当中文任务/能力问题得到明显非中文回复或带语言标签的回复时，替换为中文能力说明；真实 CLI 失败/超时不会被兜底遮盖。
- `tests/test_cli_bridge.py` 已覆盖 pi prompt 语言要求、能力边界、阿拉伯语语言标签兜底、英文指定不误替换，以及 Group Hall 中 pi 中文能力回复归一化。
- `docs/MODULE_bridges.md` 已同步 pi 当前边界：默认命令仍不使用 `--system-prompt`，语言跟随与中文能力兜底由 TALK bridge prompt/后处理提供。

### 3) Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次语言修复。
- 重启后建议在同一个 Group Hall 重新验收：`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 旧消息 `#39` / `#41` 已写入数据库，历史内容不会自动改写；本次修复只影响后续新回复。
- Codex + pi 双 Agent 同时运行的真实端到端回合仍需继续人工验收；本里程碑还需覆盖 Web UI 视觉/交互。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交本次 `PI-LANGUAGE-REPLY-1` 验收期修复。
2. 用户重启 pi bridge 后，继续在 Group Hall 验收 pi 中文/英文语言跟随和能力边界。
3. 继续当前范围冻结分支的 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
4. 验收通过后，再基于 OpenHanako 参考评估下一阶段多 Agent 自动讨论协议。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，22 tests。
- `.venv\Scripts\python.exe -u -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_files tests.test_groups tests.test_healthz tests.test_instances tests.test_members_auth tests.test_messages tests.test_pi_bridge tests.test_setup tests.test_sse tests.test_talk_client tests.test_tasks tests.test_websocket` passed，120 tests。
- `.venv\Scripts\python.exe -m unittest` 与 `.venv\Scripts\python.exe -m unittest -v` 曾分别在 120 秒/300 秒超时且未刷出失败栈；改用显式模块列表后全量 120 tests 通过，残余风险记录为 discovery/环境阻塞而非本次代码测试失败。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
