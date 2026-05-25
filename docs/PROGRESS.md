# Project Progress

## Latest
Updated: 2026-05-25 12:21 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `PI-SYSTEM-PROMPT-BOUNDARY-1` 已完成：按项目管理者确认，将 pi 的身份/能力边界从用户 prompt 中移到默认 `pi --system-prompt`，避免 `TALK...` 等包装文本被 pi 当成用户没说完的正文。
- `bridges/pi_bridge.py` 默认命令恢复极短中文 `--system-prompt`，同时继续保留 `--no-context-files --no-tools --no-session --thinking off`。
- `bridges/cli_bridge.py` 的 pi 消息 prompt 现在只返回去掉 `@agent:pi` 后的用户原文，例如 `@agent:pi 你好` 精确传给 pi 为 `你好`。
- pi 队列任务 prompt 默认只传 `content`；如存在 `title`，传 `标题：<title>\n\n<content>`，把标题作为用户任务文本而非 bridge 元信息。
- pi prompt 不再包含 `用户消息`、`用户任务`、`回复要求`、`Sender:`、`TALK message id:`、`TALK task id:`、`Task creator:`、`TALK group id:` 或 `Project root:`；但 bridge 回复仍保留原消息 `group_id`，Group Hall 回复路径不变。
- 非 pi runtime 的执行型 prompt 保持不变；Codex bridge 不受本次调整影响。
- `normalize_pi_reply_language(...)` 保留为异常兜底：中文请求得到非中文/语言标签时才替换；正常中文回复或用户明确要求英文时不干预。
- `docs/MODULE_bridges.md` 已同步 pi system prompt 分离边界。

### 3) Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次 system prompt 分离修复。
- 重启后建议在同一个 Group Hall 重新验收：`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 旧消息 `#39` / `#41` 已写入数据库，历史内容不会自动改写；本次修复只影响后续新回复。
- 如果用户本机通过 `TALK_PI_COMMAND` 或 `--pi-command` 自定义 pi 命令，需要自行带上等价 `--system-prompt` 和隔离参数。
- Codex + pi 双 Agent 同时运行的真实端到端回合仍需继续人工验收；本里程碑还需覆盖 Web UI 视觉/交互。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交本次 `PI-SYSTEM-PROMPT-BOUNDARY-1` 修复。
2. 用户重启 pi bridge 后，继续在 Group Hall 验收 pi 中文/英文语言跟随和能力边界。
3. 继续当前范围冻结分支的 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
4. 验收通过后，再基于 OpenHanako 参考评估下一阶段多 Agent 自动讨论协议。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，23 tests。
- 分组显式全量 passed，合计 121 tests：`tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_pi_bridge` 35 tests；`tests.test_files tests.test_groups tests.test_healthz tests.test_members_auth tests.test_messages` 40 tests；`tests.test_instances tests.test_tasks tests.test_talk_client` 27 tests；`tests.test_setup tests.test_sse tests.test_websocket` 19 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
