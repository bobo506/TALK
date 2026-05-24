# Project Progress

## Latest
Updated: 2026-05-24 21:53 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `CODEX-BRIDGE-MIXED-ENCODING-1` 验收期修复已完成：修复 Codex 回复中 `taskkill` 噪声已被过滤后，正文“在线。”仍显示为 `鍦ㄧ嚎銆` 一类 mojibake 的问题。
- 根因是同一段 stdout 同时包含 Windows 代码页的 `taskkill` 行和 UTF-8 的 Codex 正文行；上一版按整段输出选择编码，会因进程清理行而把正文行误按 GBK 解码。
- `decode_subprocess_output(...)` 已改为逐行选择最合适编码，避免不同来源的输出行互相影响。
- `tests/test_cli_bridge.py` 已补充混合编码行回归测试：GBK 的 Windows 清理提示与 UTF-8 的 `codex 在线。` 可以在同一 stdout 中正确解码。
- `CODEX-BRIDGE-OUTPUT-1` 验收期修复已完成：修复 Codex 在 Group Hall 回复“在线”前混入 Windows 进程终止提示且中文乱码的问题。
- 现场排查确认：最新 Codex 回复已写回 Group Hall，说明 `group_id` 修复生效；但消息内容包含乱码的 `taskkill` PID 成功提示，这是 Windows 进程清理输出按错误编码解码后混进了 bridge 回复。
- `bridges/cli_bridge.py` 已新增子进程输出解码兜底：优先 UTF-8，若出现替换字符则在 Windows 下尝试系统代码页 / `gbk` / `cp936`。
- `format_cli_reply(...)` 现在会过滤 Windows `taskkill` 中英文进程清理提示，避免 Codex CLI 退出清理噪声出现在前端聊天中。
- `tests/test_cli_bridge.py` 已补充 GBK 解码与 `taskkill` 噪声过滤回归测试。
- `GROUP-BRIDGE-REPLY-1` 验收期修复已完成：修复 Group Hall 中 `@agent:codex` / `@agent:pi` 后 bridge 已收到消息但回复失败的问题。
- 现场排查确认：新建 group 中的消息已写入 `messages.group_id`，且 `to_ids` 分别指向 `agent:codex` / `agent:pi`；两个 bridge 都已领取到消息，但实例状态进入 `error`，`last_error` 为 `cannot_reply_to_different_group`。
- 根因是通用 CLI bridge 在 `reply_to` 原消息时没有把原消息的 `group_id` 带回，导致服务端认为这是跨 group 回复并拒绝写入。
- `bridges/cli_bridge.py` 已抽出 `handle_incoming_message(...)`，统一处理 ACK、CLI 调用、最终回复和状态上报，并在 Group Hall 消息中保留原始 `group_id`。
- bridge 生成的 CLI prompt 现在包含 `TALK group id`，让外部 Agent 能感知当前消息来自哪个 Hall。
- `tests/test_cli_bridge.py` 已补充 Group Hall prompt 与同 group 回复回归测试。
- `docs/MODULE_bridges.md` 已同步 Codex / pi 在 Group Hall 中的当前边界：直接 `@agent:*` 可以处理，回复会写回原 Hall；HTTP fallback 的 Agent group cursor 仍是后续计划。
- `OPENHANAKO-REF-1` 文档沉淀已完成：将 `liliMozi/openhanako` 中对 TALK 有参考价值的多 Agent 频道群聊设计记录到项目文档。
- `docs/LOCAL_LAB_DESIGN.md` 已新增 OpenHanako 参考笔记：保留 Group Hall 作为真相源、`@mention` 只作提醒/调度、Agent 需要显式 `reply/pass`、后续需要 Agent group cursor 与调度保护参数。
- `docs/MODULE_groups.md` 已补充 Group/Hall 后续协议参考：继续使用 SQLite 的 `groups / group_members / messages`，不照搬 Markdown 文件存储、Electron/Node Hub 和主动人格/记忆系统。
- 当前验收分支范围仍保持冻结：本次只记录下一阶段参考，不把自动多 Agent 讨论协议纳入当前 Codex + pi + Web UI 联合验收。
- `PI-BRIDGE-CHAT-1` 验收期修复已完成：收敛 pi bridge 的默认聊天模式，降低普通前端消息回复慢、回复过长和误输出项目状态报告的概率。
- `bridges/pi_bridge.py` 默认命令已加入 `--no-context-files --no-tools --no-session --thinking off`，并通过 `--system-prompt` 把 pi 固定为 TALK 中的简洁聊天 Agent。
- 通用 bridge 新增“一句话”兜底：当用户任务明确包含“一句话 / one sentence / single sentence”等约束时，成功回复会被收敛为第一句或第一行再发回 TALK。
- `docs/MODULE_bridges.md` 已同步 pi 默认命令的新边界，并提醒覆盖 `TALK_PI_COMMAND` / `--pi-command` 时需自行保留这些收敛参数。
- `WEB-MENTION-ENTER-1` 验收期修复已完成：修复前端在 `@` 补全下拉打开时按 Enter 会先发送裸 `@`，从而出现 `invalid recipient mention: @` 的问题。
- 当 mention 下拉框可见时，消息输入框的发送快捷键会让出 Enter，不再触发 `sendMessage()`。
- mention 补全现在支持未高亮任何条目时直接按 Enter 选择首个候选；鼠标点击候选时会阻止输入框 blur，保证补全文本稳定写回。
- `web/index.html` 已更新 `app.js` cache bust 参数，浏览器刷新后会加载本次前端修复。
- `BRIDGE-WINDOWS-CMD-1` 验收期修复已完成：修复 Windows 下 bridge 直接调用 `codex` / `pi` 找不到命令的问题。
- `PI-BRIDGE-1` 已完成：新增 `bridges/pi_bridge.py`，默认注册 `agent:pi`，默认 runtime 为 `pi`，默认调用 `pi --print --mode text`。
- 本机已确认 `pi --help` 与 `pi --version` 可执行，版本为 `0.74.1`。

### 3) Open Questions / Pending Confirmation
- 需要用户再次重启 Codex bridge；当前正在运行的 Codex bridge 仍加载旧的整段解码逻辑，下一条回复仍可能把“在线。”显示成 mojibake。
- 需要用户重启 Codex bridge；当前正在运行的 Codex bridge 仍加载旧代码，下一次回复仍可能带出旧的乱码噪声。
- 如果 pi bridge 也尚未在 `GROUP-BRIDGE-REPLY-1` 后重启，则也需要一并重启；正在运行的旧 bridge 进程不会自动获得本次修复。
- 旧的失败消息（本次现场看到的 group 消息 id 20 / 21）不会自动重试；重启 bridge 后请在同一个 Group Hall 重新发送新的 `@agent:codex` / `@agent:pi` 消息验收。
- Group Hall 的实时触发当前依赖 WebSocket 推送；Agent group cursor / HTTP fallback 轮询仍留到当前验收通过后的下一阶段设计。
- OpenHanako 参考只作为下一阶段设计素材；是否实现 Agent group cursor、`reply/pass` 决策协议和自动讨论调度器，需等当前验收完成后再确认。
- 需用户重启 pi bridge 后在前端实测：`@agent:pi 只用一句话回复：你在线吗？` 应返回简短一句，不再输出项目状态报告。
- 如果用户本机通过 `TALK_PI_COMMAND` 或 `--pi-command` 自定义了 pi 命令，需要把 `--no-context-files --no-tools --no-session --thinking off --system-prompt ...` 等收敛参数带回自定义命令，否则会绕过本次默认修复。
- 需用户刷新前端页面后，重新验证 `@` 下拉选择 `agent:codex` / `agent:pi` 不再出现 `invalid recipient mention: @`。
- Codex bridge 是否已经正常回复仍需人工验收；若前端仍不显示在线，优先检查 Codex bridge 进程是否已用最新代码重启。
- 真实 pi 模型调用仍依赖本机 `pi` 的 provider/API key 配置；本轮未消耗真实模型请求，只验证 CLI 入口与桥接参数。
- Codex + pi 双 Agent 同时运行的真实端到端回合尚未执行；下一步应进入人工验收或补一个双桥 smoke 脚本。
- 本里程碑验收必须同时覆盖 Web UI：此前 Web UI 第一版质量不达标，后续已按 `image_gen` 视觉稿方向重做并记录在 `docs/MODULE_webui.md` 的 `WEB-VISUAL-2 Addendum`，需要和双 Agent bridge 一起验收。
- Group 删除 / 归档语义仍需项目管理者确认：历史 Hall 消息应保留、归档还是随 Group 删除。
- Schedule 当前仅记录并显式物化，不内置后台调度循环；后续需决定由 bridge 轮询、系统定时脚本，还是服务端后台 worker 触发。
- 未读/关注状态、文档编辑锁仍待实现。

### 4) Next Plan
1. 提交本次 `CODEX-BRIDGE-MIXED-ENCODING-1` 验收期修复。
2. 用户重启 Codex bridge 后，在同一个 Group Hall 重新发送 `@agent:codex 你好`，确认回复不再包含 `taskkill` 乱码或 `鍦ㄧ嚎` 这类 mojibake。
3. 继续当前范围冻结分支的 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
4. 验收通过后，再基于 OpenHanako 参考评估下一阶段多 Agent 自动讨论协议。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_encoding` passed，18 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge` passed，25 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，114 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
- `scripts/check-progress.ps1` 与 `scripts/check-git-ready.ps1` 当前工作树不存在，本轮无法运行这两个历史门禁脚本。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
