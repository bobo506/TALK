# Project Progress

## Latest

Updated: 2026-11-16 20:55 (+08:00)

**当前结论**：第 6 项“GUI 关窗不停服务 + 页面退出服务”已完成（Terra 开发、K2.8 复核 approved，`f6ee423`）。第 5 项按“已实现”跳过（`auto_start` 意图 + 启动恢复已存在）。第 3 项 `/mcp` 已在库（`2be7a3f`）；生产 `8000` 仍运行旧代码，`/mcp` 尚未对外生效。

### 1) Current Progress
- 路线图 13 项：第 1（角色 Key 恢复）、第 2（四终端 MCP 接入）、第 3（HTTP `/mcp`）、第 4（启动器自动接入 MCP）、第 5（角色自动启动，已实现跳过）、第 6（GUI 合并启动 + 退出服务）已完成；第 7→13 项待推进。
- 角色：Terra（codex，`gpt-6.1-terra`）、K2.8（kimi-code，`kimi-for-coding`）、Astra（codex，仅咨询）均 running；Terra 命令/读写能力已验收（#796/#797）。
- 第 6 项交付：`scripts/talk_desktop.py`（关窗不停服务，失败仍清理）、`scripts/talk_api.py`（控制文件路径入 env）、`server/routes/local_shutdown.py`（仅 `human:operator` loopback；403/409 边界）、`web/index.html`+`web/app.js`（“退出服务”按钮）、`tests/test_local_shutdown.py`（4 项）。
- 第 4 项交付：`scripts/mcp_onboarding.py`（检测/key 发现/幂等生成/只读成员检查）、`tests/test_mcp_onboarding.py`（24 项）、`talk_desktop.py` 启动前调用。
- `/mcp` 交付：`server/routes/mcp.py`、`bridges/talk_tool_registry.py`、`bridges/talk_call_context.py`、`tests/test_mcp_http.py`（32 项）。
- 运行环境：Codex CLI 钉 `0.164.0`；Kimi Code CLI `2.0.2`；Terra runner 与仓库根目录完整性标签为 **Medium**（手动修复，重建/升级后需复查）。

### 2) Open Questions / Pending Confirmation
- 第 7 项（GUI 加载页）范围与验收需按惯例先确认。
- 已知限制：第 4 项不创建成员、真实 HOME `--apply` 未执行；第 6 项真实浏览器点击/桌面窗口未实测（按钮经静态与单测验证）。
- 已知环境限制：`test_runtime_log_authentication` 在 Terra 沙箱运行环境返回 503；管理员上下文单独运行 1 passed in 3.01s。

### 3) Next Plan
- 第 7 项：GUI 加载页——启动时显示主题动画/文案 + 进度条，展示“启动服务→检测运行器→接入 MCP（已有跳过）→自动角色→就绪”，完成后进入主页面。
- 分工：**Terra 开发、K2.8 复核**；协调者只做范围/授权/判断与收尾。
- 后续顺序：第 8 项（无运行器提示）→ 9→13。

### 4) Verification
- `pytest tests/test_talk_desktop.py -q`：20 passed + 3 subtests；`pytest tests/test_local_shutdown.py -q`：4 passed；`test_auth_trusted.py`：回归通过（合计 31 passed + 9 subtests）。
- 真实隔离停机：临时 API（端口 62372）无 Key POST `/api/local/shutdown` 两次均 202，控制文件写入 `stop`，进程约 1 秒退出码 0；生产 8000 未触碰。
- 乱码修复：`web/app.js` 异常分支提示已改正，`web/` 下无 `????` 残留；`node --check` 通过。
- 未验证：真实桌面窗口关闭/按钮点击未实测；生产 `8000` 未重启（`/mcp` 未生效）。

### 5) Changed Files
- 第 6 项：修改 `scripts/talk_desktop.py`、`scripts/talk_api.py`、`server/main.py`、`web/index.html`、`web/app.js`、`tests/test_talk_desktop.py`；新增 `server/routes/local_shutdown.py`、`tests/test_local_shutdown.py`。
- 第 4 项：新增 `scripts/mcp_onboarding.py`、`tests/test_mcp_onboarding.py`；修改 `scripts/talk_desktop.py`、`tests/test_talk_desktop.py`。
- 第 3 项：新增 `server/routes/mcp.py`、`bridges/talk_tool_registry.py`、`bridges/talk_call_context.py`、`tests/test_mcp_http.py`；修改 `server/main.py`、`bridges/talk_task_tools.py`、`bridges/initiator_followup.py`。
- 提交：`f6ee423`（第 6 项）；`c033683`、`c73587f`（第 4 项）；`2be7a3f`（第 3 项）。

## Recent Notes
- 归档/备份：`D:\backups\codex-sandbox-rebuild-20261116-1345`、`D:\backups\talk-acl-20261116-0035`、`D:\backups\talk-legacy-convert-20261116-1025`；诊断日志 `D:\agent-trash\talk-diag\codex-spawn.log`。
- 临时目录：仓库根仍有 `.tmp-acceptance`（历史）与 `.tmp-tests`（含 `mcp-799-archive`）；均未跟踪，未清理。
- 恢复：说“继续项目”。
- 环境事件（2026-11-14 22:51）：系统 Python `Lib` 被便携运行时覆盖；已补 `python312.zip` 与 4 个 `.pyd`，依赖在 `Python312\talk-deps`。全局 `pip` 未装回。
- 运行器环境（2026-11-15）：Codex CLI 临时钉 `0.164.0`；Kimi Code CLI 2.0.2（`~/.kimi-code/bin/kimi.exe` 与 `%APPDATA%\npm\kimi.exe`）。新版本适配见路线图第 12 项。
- 事故相关：桌面误删清单 `D:\desktop-deleted-20261114.txt`；本机沙箱/服务重建记录见 `PROGRESS_HISTORY.md` 2026-11-16 各段。
