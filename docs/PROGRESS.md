# Project Progress

## Latest

Updated: 2026-11-25 22:50 (+08:00)
Role: Antigravity 会话（协调 / 编码自测，搭配独立只读对抗复核子代理；按用户本轮显式授权执行）

**当前结论**：**Antigravity 适配 4 片（A–D：`4954e36` / `34bf051` / `4b1dab0` / `e2601c9`）已全部完成、独立对抗复核 `APPROVED` 并推送至 GitHub `origin/codex/terminal-return-codex`**（`3fe93e0..e2601c9`）。当前由用户自行重启 TALK 进入页面人工验收；同时已按 `project-framework` 将 2026-11-24 项目全面体检识别出的 **5 大类 / 15 项可改进点**及 **3 项推荐高性价比批次**完整沉淀至 `docs/spec/DEVELOPMENT_ROADMAP.md`。

### 1) Current Progress
- **Antigravity 适配（4 片串行规划 — 全部完成并已推送）**：
  - **切片 A（`4954e36`）**：`mcp_onboarding` 探测 Antigravity 并幂等写入 `~/.gemini/config/mcp_config.json`、`talk_desktop` / `boot_status` 白名单与前端横幅/加载页展示、`agent:antigravity-t` 终端身份过滤。
  - **切片 B（`34bf051`）**：实机 `agy 1.5.16` 协议/能力/版本探测、`bridges/antigravity_{effort,execution_native,execution_channel,bridge}.py`、`bridges/cli_bridge.py` 路由与 `stream-json` 正文抽取、磁盘会话证明与 90% 换窗、`/api/runners/versions` 与 Carbon 3 档硬约束（Neon/Hydrogen 4 档）。
  - **切片 C（`4b1dab0`）**：`scripts/antigravity_role_setup.py` / `scripts/antigravity_role_host.py`（`legacy` + `workspace-v1`）、全链路接入 `talk_runtime` / `role_service_host` / `role_host_resolution` / `role_service_recovery` / `role_delete` / `portable_bootstrap` / `workspace_paths`、服务端默认强度初始化与 Carbon 强夹紧、工作台运行器引导弹窗。
  - **切片 D（`e2601c9`）**：独立沙箱实机端到端验收（`agy 1.5.17`，10 步全绿）、修复受管宿主系统代理透传与诊断日志脱敏、同步更新 `README.md` 与 `docs/guides/USER_MANUAL.md`。
- **后续改进清单沉淀**：2026-11-24 项目体检的 5 大类 / 15 项可改进点已完整登记至 `docs/spec/DEVELOPMENT_ROADMAP.md` 顶部（仅登记，未开工）。
- **历史 `v0.1.0` 发布状态（2026-11-18）**：保持不变（https://github.com/bobo506/TALK/releases/tag/v0.1.0 ，详见 `docs/PROGRESS_HISTORY.md`）。

### 2) Open Questions / Pending Confirmation
- **人工验收门禁**：待用户自行重启 TALK 完成 Antigravity 实机页面验收（如复用已有 `talk.db`，需先执行 `python -B -X utf8 -m scripts.antigravity_role_setup --seed-db <talk.db> --apply`）。
- **后续改进项授权**：`docs/spec/DEVELOPMENT_ROADMAP.md` 中 15 项改进均未获开工授权，每次仅确认并串行推进 1 个依赖闭环。
- **历史已决定不处理项（2026-11-18 用户确认）**：`v0.1.0` 便携包构建扫描项、4 处源码默认值、`v0.1.0` tag 指向、公开仓库历史文档环境信息均不再处理（详见 `docs/PROGRESS_HISTORY.md`）。
- **已知遗留与保留项**：`scripts/talk_desktop.py` 历史 mojibake（未修）；本机部分测试受 key 继承 ACL 影响；仓库根 5 个既有未跟踪目录（`.codex/`、`.kimi-code/`、`.talk/agents/agent_workbuddy/`、`.workbuddy/`、`Microsoft/`）保持不动。

### 3) Next Plan
1. 等待用户自行重启 TALK 完成 Antigravity 3 模型（Neon / Carbon / Hydrogen）页面人工验收。
2. 从 `docs/spec/DEVELOPMENT_ROADMAP.md`「2026-11-24/25 项目全面体检与后续改进清单」中择项确认目的、范围、不变项与验收标准后串行推进：
   - **推荐首推 3 项高性价比批次**：
     1. **分支对齐 + 门面更新**：合并 `codex/terminal-return-codex` 至 `main` + 替换 `README.md` 两张滞后亮色截图（#8 + #12）；
     2. **离线与本机安全双补齐**：前端 4 个 CDN 库（Tailwind / highlight.js / DOMPurify / marked）本地化至 `web/vendor/` + `trusted` 本机免密模式补 `Origin` / `Sec-Fetch-Site` 同源校验中间件（#1 + #2）；
     3. **自动防回归基建**：轻量 GitHub Actions CI（核心 `pytest` + `ruff`）+ `requirements.lock` + `build_portable.py` 升级 Python / SHA-256 校验（#9 + #10）。
   - **其余已登记改进项（#3–#7、#11、#13–#15）**：
     - 安全深化：API Key 库内哈希化 + HTTP MCP 进程内直调（#3）；
     - 架构与数据库治理：8 个核心“巨石”文件按领域拆包（#4）、`server/db.py` `PRAGMA user_version` 版本化迁移（#5）、运行器能力探测移出 DB Session + SQLite `PRAGMA busy_timeout`（#6）、已下线群聊/会议/主动跟进/定时任务包袱清理（#7）；
     - 部署与文档整理：`Dockerfile` 升 3.12+ 并对齐 `talk_runtime`（#10）、`PROJECT_BRIEF.md` 与 `DEVELOPMENT_ROADMAP.md` 历史归档瘦身（#11）；
     - `v0.2+` 功能延伸：干净机器首启 + 便携包跨版本无痛升级脚本（#13）、主动模式跨终端泛化（#14）、协作效率看板（#15）。

### 4) Verification
- **本次推送与进度汇总（2026-11-25 22:50）**：推送前对 `origin/codex/terminal-return-codex..HEAD`（340,824 B）执行密钥正则扫描（0 命中）；`git push origin codex/terminal-return-codex` 退出码 `0`（`3fe93e0..e2601c9`）；本次文档修改通过 `git diff --check` 与相对链接校验。
- **Antigravity 切片 A–D 独立复核（全部 `APPROVED`）**：
  - 切片 D（`e2601c9`）：独立沙箱实机 `agy 1.5.17` 10 步 E2E 全绿 + 5 套 pytest **49 passed / 18 subtests** + `README.md`/`USER_MANUAL.md` 0 断链 + 7 组对抗探针；
  - 切片 C（`4b1dab0`）：13 套 pytest **189 passed / 147 subtests** + `test_real_recipe_table_and_alias_flags_unchanged` 1 passed + Node UI **89 pass**；
  - 切片 B（`34bf051`）：切片 B 4 套 **33 passed / 12 subtests** + 16 套回归 **572 passed / 260 subtests** + 9 组对抗探针；
  - 切片 A（`4954e36`）：5 套 **89 passed / 5 subtests** + `node --check` + 4 组对抗探针。
- **未验证**：生产服务重启加载、真实桌面浏览器页面点击人工验收、含 Antigravity CLI 的新版便携包构建与跨机首启。

### 5) Changed Files
- 本轮汇总（2026-11-25 22:50）：`docs/spec/DEVELOPMENT_ROADMAP.md`、`docs/PROGRESS_HISTORY.md`、`docs/PROGRESS.md`。
- Antigravity 切片 A–D（已推送 `4954e36..e2601c9`）：详见 `docs/PROGRESS_HISTORY.md`。

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`；后续改进明细见 `docs/spec/DEVELOPMENT_ROADMAP.md`；上下文交接见 `docs/HANDOFF_20261118.md`。
- 恢复：新窗口说「继续项目」，先读本文件与规则入口 `AGENTS.md`。
