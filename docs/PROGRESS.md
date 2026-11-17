# Project Progress

## Latest

Updated: 2026-11-17 10:30 (+08:00)

**当前结论**：生产 API 已重启并验证通过——`/mcp` 生效（initialize 返回 `talk_tools_mcp`）、加载页显示 6 个步骤 chips + 轨道动画 + “本机已安装 Codex、KimiCode、WorkBuddy、DSH”，主页面提示条为青绿色“可接入使用”，真实截图 `docs/mockups/live/`。Terra/K2.8/Astra 均 running。启动误报/加载页/BOM/乱码修复已复核并提交（`41bbcf9`）；换肤切片 1 已完成（`2517fd4` + `f9d0ac2`）。

### 1) Current Progress
- 路线图 13 项：第 1–7 已完成；第 8 项（运行器提示）并入换肤切片 1 完成；第 9→13 项待推进（第 9 单目录收拢、第 10 Release、第 11 交接文档、第 12 Codex 版本适配、第 13 终端身份隐藏）。
- 换肤切片 1 已完成（`2517fd4` + 加载页 chips/轨道 `f9d0ac2`）；切片 2（任务区：任务列表/任务 Hall/输入框/弹窗）待开工；切片 3（角色/设置/诊断页）、切片 4（亮色主题边角统一）后续。
- 角色：Terra（codex）、K2.8（kimi-code）、Astra（codex，仅咨询）均 running；Terra 命令/读写能力已验收。
- 2026-11-17 09:50 事故修复：`.talk` 残留 `CodexSandboxUsers` ACE → keys 继承 → host `key_permissions_failed`；runtime 因临时文件继承 ACE 崩溃。已按 `PROGRESS_HISTORY.md` 备份并重置私有 ACL、手动重启 runtime（pid 12516），三角色 running。
- 换肤切片 1 交付：`web/theme-tokens.css`（两套 tokens）、`web/style.css` 外壳、`web/loading.html`、`web/theme.js`（默认 midnight、旧值迁移、无闪烁）、`web/index.html`/`web/app.js`（两种提示条 + 设置区）、`server/routes/boot_status.py`（`runners`）。
- 运行环境：Codex CLI 钉 `0.164.0`；Kimi Code CLI `2.0.2`；Terra runner 与仓库根目录完整性标签为 **Medium**（手动修复，重建/升级后需复查）。

### 2) Open Questions / Pending Confirmation
- 切片 2 范围（任务区换肤）需按惯例先确认。
- 生产 `8000` 未重启：新 UI 静态文件可从磁盘加载，但 `/api/boot/status` 的 `runners` 字段与 `/mcp` 需重启 API 才生效；重启需用户授权。
- 已知限制：换肤截图为临时空库实例，真实项目数据密度/布局需重启后目检；加载页实际样式较效果图简化（无步骤 chips/完整轨道动画），如需更接近效果图可在切片 2/3 追加。
- 已知遗留：`scripts/dsh_role_host.py` 第 191/194/203 行既有乱码（docstring + 错误文案），未修。
- 已知环境限制：`test_runtime_log_authentication` 在 Terra 沙箱运行环境返回 503；管理员上下文 1 passed in 3.01s。

### 3) Next Plan
- 切片 2：任务区换肤——任务列表、任务 Hall 消息气泡、输入框、状态标签、任务相关弹窗统一到 tokens，明暗两套截图验收。
- 分工：**Terra 开发、K2.8 复核**；协调者只做范围/授权/判断与收尾。
- 后续：切片 3（角色/设置/诊断页）→ 切片 4（亮色边角）→ 路线图第 9 项起。

### 4) Verification
- `pytest tests/test_boot_status.py -q`：3 passed；`test_talk_desktop.py`：23 passed + 3 subtests；`test_mcp_http.py`：32 passed；`node --check web/app.js`、`web/theme.js` 通过。
- 隔离实例（端口 8321）：tokens 覆盖脚本比对无缺失；`runners` 过滤非法名（evil-bot/42）正确；`/loading` 200；Edge 无头抓 4 张真实截图（加载页明暗、主页两种提示条）。
- 复核发现的 `join("?")` 与 `style.css` 注释乱码已修复；`web/` 下无 `????`。
- 未验证：生产 `8000` 未重启（`/mcp`、新 boot 状态未生效）；真实项目数据下页面未目检。

### 5) Changed Files
- 换肤切片 1：新增 `web/theme-tokens.css`；修改 `web/style.css`、`web/loading.html`、`web/theme.js`、`web/index.html`、`web/app.js`、`server/routes/boot_status.py`、`tests/test_boot_status.py`；截图 `docs/mockups/after/`。
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
