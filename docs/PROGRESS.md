# Project Progress

## Latest
Updated: 2026-05-25 16:51 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `WEB-REPLY-COMPACT-1 / PI-CMD-METACHAR-HOTFIX-1` 已完成：优化多 Agent 讨论中的引用展示，并修复 pi 默认 prompt 在 Windows `pi.cmd` 启动链下被误解释为命令的问题。
- Web UI 现在在双方互相回复时把引用条显示为 `A 回复 B`，不再展开完整预览；若当前消息发给 B、但引用第三方 C，仍保留原完整引用框。
- `web/index.html` 静态资源版本号已更新到 `20260525-reply-compact`，便于浏览器刷新到新 CSS/JS。
- pi 默认 system prompt 已移除原始 `<talk-action ...>` 示例、竖线枚举和 Windows 高风险命令元字符，避免出现 `'optimize' 不是内部或外部命令`。
- `tests/test_pi_bridge.py` 新增默认 prompt 不包含 `| / < / > / &` 的回归断言。

### 3) Open Questions / Pending Confirmation
- 需要重启 pi bridge，正在运行的旧 pi 进程不会自动加载新的默认 `--system-prompt`。
- Web UI 侧刷新页面即可拿到新的 `index.html` 资源版本；如果浏览器仍缓存旧页面，可强制刷新。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Codex + pi 双 Agent 真实端到端讨论回合仍需人工验收。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交本次 compact reply 与 pi prompt hotfix。
2. 重启 pi bridge；如 server 仍是旧进程，也建议一并重启 TALK server 与 codex bridge，确保 discussion API / bridge 协议同版。
3. 重新验收：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
4. 在 Hall 中确认：codex 能代发给 pi、pi 不再报 `optimize` 命令错误、双方互相回复时引用条变为短文本。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_cli_bridge` passed，28 tests。
- `node --check web\app.js` passed。
- `.venv\Scripts\python.exe -m unittest` passed，129 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
- Browser / in-app browser：已打开 `http://127.0.0.1:8000/` 并确认页面加载 `style.css?v=20260525-reply-compact` 与 `app.js?v=20260525-reply-compact`；受当前 browser 安全/只读执行环境限制，未能构造临时消息样例做视觉断言。

### 6) Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `web/app.js`
- `web/style.css`
- `web/index.html`
- `docs/MODULE_bridges.md`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
