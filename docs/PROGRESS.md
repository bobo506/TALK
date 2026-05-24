# Project Progress

## Latest
Updated: 2026-05-24 16:41 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
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
1. 提交本次 `OPENHANAKO-REF-1` 文档沉淀。
2. 继续当前范围冻结分支的 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
3. 验收通过后，再基于 OpenHanako 参考评估下一阶段多 Agent 自动讨论协议。

### 5) Verification
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
- `scripts/check-progress.ps1` 与 `scripts/check-git-ready.ps1` 当前工作树不存在，本轮无法运行这两个历史门禁脚本。

### 6) Changed Files
- `docs/LOCAL_LAB_DESIGN.md`
- `docs/MODULE_groups.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
