# Project Progress

## Latest

Updated: 2026-11-25 23:45 (+08:00)
Role: Antigravity 会话（按用户本轮明确授权执行编码自测、本机补建 `agent:antigravity-t` 与收尾，搭配独立只读对抗复核子代理）

**当前结论**：**桌面启动器体验修复切片已完成、独立对抗复核 `APPROVED` 并推送至 `origin/codex/terminal-return-codex`**：彻底修复 ① 未开通新终端 Key 导致的启动红字误报警并补齐 `logs/launcher/mcp-onboarding.log` 脱敏日志；② 关闭 TALK 窗口或点击“退出服务”后右下角 Chrome 托盘图标不退出、卡死 `SingleInstance` 无法再次启动的问题；并已按方案 B 在本机补建 `agent:antigravity-t`（私有 ACL 加固）及幂等接入 `~/.gemini/config/mcp_config.json`。当前待用户双击桌面 `TALK` 图标实机人工验收（含 Antigravity 3 模型页面验收）。

### 1) Current Progress
- **桌面启动器体验修复切片（已完成、独立复核 `APPROVED`）**：
  - **MCP 接入与脱敏日志**：`scripts/mcp_onboarding.py` 将 `KeyMissingError` 归为 `skipped`（空 Key / 配置损坏仍 fail-closed 进 `errors`）；`scripts/talk_desktop.py` 新增 `write_onboarding_log()`，按严格闭集白名单向 `logs/launcher/mcp-onboarding.log` 原子滚动写入最近 50 条脱敏诊断（含损坏 UTF-8 自恢复）。
  - **Chrome 托盘自动退出与零误杀隔离**：`scripts/talk_launcher.py` 原子更新 `Local State`（`background_mode.enabled=false`、`glic.launcher_enabled=false`）+ `--disable-features=Glic`；新增 64 位安全 Win32 窗口生命周期监视（首次见窗后关窗自动优雅退出、最小化绝不误关、枚举失败 fail-closed）、UTF-8 PowerShell 精确 `--user-data-dir` 孤儿托盘清理、先 `WM_CLOSE`/温和 `taskkill /T`（`exit_type=Normal` 清除托盘）后兜底 `/F`、以及便携版 `health_url` 补传。
  - **本机 Antigravity MCP 补齐**：生产 `talk.db` 新增 `agent:antigravity-t` 与 64B 私有 ACL `~/.talk/keys/agent_antigravity-t.key`，`~/.gemini/config/mcp_config.json` 已幂等接入 `talk`（保留 `ambient_eye`）。
- **Antigravity 适配（切片 A–D，`4954e36..e2601c9`）与全面体检 15 项路线图（`9083930`）**：均已完成并推送至 `origin/codex/terminal-return-codex`。
- **历史 `v0.1.0` 发布状态（2026-11-18）**：保持不变（https://github.com/bobo506/TALK/releases/tag/v0.1.0 ，详见 `docs/PROGRESS_HISTORY.md`）。

### 2) Open Questions / Pending Confirmation
- **人工验收门禁**：待用户双击桌面 `TALK` 图标实机验收：① 加载页无红字警告且 `logs/launcher/mcp-onboarding.log` 正常写入；② 关窗或点“退出服务”后右下角 Chrome 托盘图标自动消失且可立即重开，日常 Chrome 不受影响；③ Antigravity 3 模型（Neon / Carbon / Hydrogen）页面流程（复用已有 `talk.db` 时需先执行 `python -B -X utf8 -m scripts.antigravity_role_setup --seed-db <talk.db> --apply`）。
- **后续改进项授权**：`docs/spec/DEVELOPMENT_ROADMAP.md` 中 15 项改进均未获开工授权，每次仅确认并串行推进 1 个依赖闭环。
- **已知遗留与保留项**：`scripts/talk_desktop.py` 历史 mojibake（未修）；本机部分测试受 key 继承 ACL 影响；仓库根 5 个既有未跟踪目录（`.codex/`、`.kimi-code/`、`.talk/agents/agent_workbuddy/`、`.workbuddy/`、`Microsoft/`）保持不动。

### 3) Next Plan
1. 等待用户实机重启 TALK 完成本次桌面启动器修复与 Antigravity 3 模型页面人工验收。
2. 从 `docs/spec/DEVELOPMENT_ROADMAP.md`「2026-11-24/25 项目全面体检与后续改进清单」中择项确认目的、范围、不变项与验收标准后串行推进（推荐首推 3 批次：① 合并至 `main` + 替换 `README` 亮色截图 #8+#12；② 4 个 CDN 本地化 + `trusted` 同源校验 #1+#2；③ 轻量 CI + `requirements.lock` + `build_portable.py` 升级与校验 #9+#10）。

### 4) Verification
- **独立对抗复核（`6e3908bc-ebf0-421f-a5ed-1177de1862cb`）**：首审 `CHANGES_REQUESTED`（3×P1 + 2×P2）→ 集中返修并补全非阻断加固 → 定向复验 **`APPROVED`**（15/15 命令行对抗用例 + 64 位 `HWND` 探针全通过）。
- **自动化回归**：6 套 pytest（`test_talk_launcher` / `test_talk_desktop` / `test_mcp_onboarding` / `test_boot_status` / `test_local_shutdown` / `test_terminal_identity_filter`）**122 passed, 8 subtests passed, 0 failed**；`git diff --check` 退出码 `0`。
- **隔离沙箱实机 Chrome `158.0.8127.37` E2E（含中文路径 `D:\agent-sandbox\chrome-中文路径-20261125`）**：最小化 3.5–4.0s 不误关；关窗与服务停机均以 `exit_type=Normal` 自动退出、残留 PID=0、`SingleInstance` 锁立刻可重获。
- **本机 MCP 实测**：`mcp_onboarding` 连续两次 `--apply --skip-members` 幂等（第 1 次写入 `antigravity`，第 2 次全部 `unchanged`，0 报错，`ambient_eye` 保留）；`agent_antigravity-t.key` 私有 ACL 与 `agent_codex-t.key` 一致。
- **未验证**：用户真实桌面双击 `TALK.lnk` 实机点击关窗/“退出服务”及加载页验收、Antigravity 3 模型真实页面验收。

### 5) Changed Files
- 本轮桌面启动器体验修复切片：`scripts/mcp_onboarding.py`、`scripts/talk_desktop.py`、`scripts/talk_launcher.py`、`tests/test_mcp_onboarding.py`、`tests/test_talk_desktop.py`、`tests/test_talk_launcher.py`、`docs/PROGRESS_HISTORY.md`、`docs/PROGRESS.md`。
- Antigravity 切片 A–D（已推送 `4954e36..e2601c9`）：详见 `docs/PROGRESS_HISTORY.md`。

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`；后续改进明细见 `docs/spec/DEVELOPMENT_ROADMAP.md`；上下文交接见 `docs/HANDOFF_20261118.md`。
- 恢复：新窗口说「继续项目」，先读本文件与规则入口 `AGENTS.md`。
