# Project Progress

## Latest

Updated: 2026-11-16 21:15 (+08:00)

**当前结论**：第 7 项“GUI 加载页 + boot 状态接口”已完成（Terra 开发、K2.8 复核 approved with limitations，`9928882`）。第 5 项按“已实现”跳过；第 6 项已完成（`f6ee423`）。第 3 项 `/mcp` 已在库（`2be7a3f`）；生产 `8000` 仍运行旧代码，`/mcp` 尚未对外生效。

### 1) Current Progress
- 路线图 13 项：第 1（角色 Key 恢复）、第 2（四终端 MCP 接入）、第 3（HTTP `/mcp`）、第 4（启动器自动接入 MCP）、第 5（角色自动启动，已实现跳过）、第 6（GUI 合并启动 + 退出服务）、第 7（加载页）已完成；第 8→13 项待推进。
- 角色：Terra（codex，`gpt-6.1-terra`）、K2.8（kimi-code，`kimi-for-coding`）、Astra（codex，仅咨询）均 running；Terra 命令/读写能力已验收（#796/#797）。
- 第 7 项交付：`web/loading.html`（主题动画/进度条/失败重试）、`server/routes/boot_status.py`（`GET /api/boot/status` 只读、字段白名单）、`server/main.py`（`/loading` 路由）、`scripts/talk_desktop.py`（写 `logs/launcher/boot-status.json`、窗口 URL `/loading?desktop=1`）、`tests/test_boot_status.py`（3 项）。
- 第 6 项交付：`server/routes/local_shutdown.py`（仅 `human:operator` loopback 停机）、`talk_desktop.py` 关窗不停服务、页面“退出服务”。
- 运行环境：Codex CLI 钉 `0.164.0`；Kimi Code CLI `2.0.2`；Terra runner 与仓库根目录完整性标签为 **Medium**（手动修复，重建/升级后需复查）。

### 2) Open Questions / Pending Confirmation
- 第 8 项（无运行器提示）范围与验收需按惯例先确认。
- 已知限制：第 7 项真实浏览器动画/跳转/重试未实测；自动角色启动状态接口标为未知；`download` 阶段恒为“无需下载”，待第 10 项接真实数据。
- 已知遗留：`scripts/dsh_role_host.py` 第 191/194/203 行有**既有**中文乱码（docstring + 两条错误文案），非本切片引入，未修复。
- 已知环境限制：`test_runtime_log_authentication` 在 Terra 沙箱运行环境返回 503；管理员上下文单独运行 1 passed in 3.01s。

### 3) Next Plan
- 第 8 项：启动时对四类运行器自动接入；**仅当用户使用四类之外的 agent 时**提示“请安装 DSH / WorkBuddy / Codex / KimiCode 之一作为分配或执行角色”，未接入不阻塞启动。
- 分工：**Terra 开发、K2.8 复核**；协调者只做范围/授权/判断与收尾。
- 后续顺序：第 9 项（单目录收拢）→ 10→13。

### 4) Verification
- `pytest tests/test_boot_status.py -q`：3 passed；`test_talk_desktop.py`：23 passed + 3 subtests；`test_mcp_http.py`：32 passed。
- 隔离 API（端口 18123）：`GET /loading` 200 且含 progressbar；`/api/boot/status` 无文件/有文件/损坏/非法四种形状均符合预期；生产 8000 未触碰。
- 乱码修复：`talk_desktop.py` 两处 boot-status 文案已改正，`scripts/`、`web/`、`server/` 下仅剩 `dsh_role_host.py` 的既有乱码（已登记）。
- 未验证：真实浏览器视觉/交互、真实桌面窗口关闭；生产 `8000` 未重启（`/mcp` 未生效）。

### 5) Changed Files
- 第 7 项：新增 `web/loading.html`、`server/routes/boot_status.py`、`tests/test_boot_status.py`；修改 `server/main.py`、`scripts/talk_desktop.py`、`tests/test_talk_desktop.py`。
- 第 6 项：新增 `server/routes/local_shutdown.py`、`tests/test_local_shutdown.py`；修改 `scripts/talk_desktop.py`、`scripts/talk_api.py`、`server/main.py`、`web/index.html`、`web/app.js`、`tests/test_talk_desktop.py`。
- 第 4 项：新增 `scripts/mcp_onboarding.py`、`tests/test_mcp_onboarding.py`；修改 `scripts/talk_desktop.py`、`tests/test_talk_desktop.py`。
- 第 3 项：新增 `server/routes/mcp.py`、`bridges/talk_tool_registry.py`、`bridges/talk_call_context.py`、`tests/test_mcp_http.py`；修改 `server/main.py`、`bridges/talk_task_tools.py`、`bridges/initiator_followup.py`。
- 提交：`9928882`（第 7 项）；`f6ee423`（第 6 项）；`c033683`、`c73587f`（第 4 项）；`2be7a3f`（第 3 项）。

## Recent Notes
- 归档/备份：`D:\backups\codex-sandbox-rebuild-20261116-1345`、`D:\backups\talk-acl-20261116-0035`、`D:\backups\talk-legacy-convert-20261116-1025`；诊断日志 `D:\agent-trash\talk-diag\codex-spawn.log`。
- 临时目录：仓库根仍有 `.tmp-acceptance`（历史）与 `.tmp-tests`（含 `mcp-799-archive`）；均未跟踪，未清理。
- 恢复：说“继续项目”。
- 环境事件（2026-11-14 22:51）：系统 Python `Lib` 被便携运行时覆盖；已补 `python312.zip` 与 4 个 `.pyd`，依赖在 `Python312\talk-deps`。全局 `pip` 未装回。
- 运行器环境（2026-11-15）：Codex CLI 临时钉 `0.164.0`；Kimi Code CLI 2.0.2（`~/.kimi-code/bin/kimi.exe` 与 `%APPDATA%\npm\kimi.exe`）。新版本适配见路线图第 12 项。
- 事故相关：桌面误删清单 `D:\desktop-deleted-20261114.txt`；本机沙箱/服务重建记录见 `PROGRESS_HISTORY.md` 2026-11-16 各段。
