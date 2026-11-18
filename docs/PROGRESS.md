# Project Progress

## Latest

Updated: 2026-11-18 20:40 (+08:00)

**当前结论**：全部切片收口、人工验收通过、`v0.1.0` 已发布（资产 19,621,867 B / 1254 文件 / sha256 `56f488ce…d9f1`，不含 docs、README 与行为一致）。今日第三件收尾：**面向下载者的产品页补齐**——`README.md` 重写为中文产品页（截图、协作优势、9 项亮点、快速开始、备份/换机、FAQ、限制、MIT 许可），新增 `LICENSE`（MIT），GitHub 仓库简介/主页/10 个 topics 已设置，用户手册群聊章节同步改为"已下线"。无进行中任务、无待收取、无阻塞项。

### 1) Current Progress
- 路线图 13 项：第 1–7、12、13 完成；第 8 并入换肤；第 9 用户已清理；第 11 交接文档完成；**第 10 构建+冒烟完成，v0.1.0 已发布（资产为不含 docs、README 与行为一致的包）**。
- 关键提交：换肤 `2517fd4`/`f9d0ac2`/`409a629`/`537634e`/`a7423f7`；图标 `c47b316`；ACL `5ce37c3`；Codex 版本 `faa57bc`；终端过滤 `6c6fed7`；便携包 `c8bc206`；按钮迁移 `9fa801d`；整机退出/托盘 `1fb21ab`；启动器自动 runtime `2290ae0`；文档收口 `baed1fe`/`82776cc`/`9b99d05`/`6465885`/`ecb70c9`；构建排除 docs `40b5ebf`；文档纠偏与三次替换（本轮）。
- 角色：Terra、K2.8 serving（idle）；Astra stopped（未勾自动启动，符合预期）；无 running 任务，`submitted` 对账为空。
- 生产：runtime `10136` 自 11-18 00:38 运行，API 8000 存活；未在 agent 侧启停。
- 便携包（发布资产）：`D:\backups\portable-r3-20261118\TALK-portable-0.1.0.zip`（19,621,867 B / 1254 文件 / sha256 `56f488ce…d9f1`），不含 `docs/`，`README-PORTABLE.txt` 已按实际行为重写；早期三版包留档于 `portable-release-`、`portable-clean-`、`portable-r2-20261118`。
- 产品页（下载者入口）：`README.md` 重写（118 行，中文；顶部英文摘要；3 张截图；「为什么用 TALK」3 条；9 项亮点；快速开始；数据/Key/备份；局域网；FAQ；源码/Docker；文档索引；限制；MIT）；新增 `LICENSE`（MIT, Copyright 2026 bobo506）；GitHub 仓库 description/homepage/10 topics 已设置；`USER_MANUAL` 群聊章节改为"已下线"。

### 2) Open Questions / Pending Confirmation
- 无阻塞项。`v0.1.0` 已发布：https://github.com/bobo506/TALK/releases/tag/v0.1.0
- **已决定不处理（2026-11-18 用户）**：以下四项均不影响下载包的使用与后续维护升级，不再跟进——
  1. `build_portable.py` 未扫描主机名/内网 IP/`C:\Users\<user>`（`docs/` 已整体排除，包内已无此类内容）；
  2. 包内 4 处代码默认值（`kimi_k28_executor.py:70` 的 `D:/claude-test/TALK`、`talk_desktop.py:90` 的 `../TALK-private`、`codex_role_host.py:41` 的 `C:/Users/Administrator`、`agent_poller.py:18` 示例 IP）——属仓库源码固有内容，改会与源码不一致；
  3. tag `v0.1.0` 指向 `82776cc`（构建脚本与文档修复前）：只影响“从该 tag 重新构建”，不影响下载资产，维护构建一律用 `main`/当前分支；
  4. 公开仓库当前树里仍可读到机器名（5 个文件）、内网 IP（12 个文件）、`C:\Users\...`（25 个文件）、`D:\claude-test`（54 个文件），历史中另有 598 个演示数据库——均为文档/开发记录，下载包不含；用户确认不影响使用，不清理（不清 docs、不重写历史）。
- 已知遗留：`scripts/talk_desktop.py` 历史 mojibake（未修，避免扩大）；本机部分测试受 key 继承 ACL 影响（基线同样复现）。
- 杂项：仓库根误落未跟踪 `Microsoft\Windows\PowerShell\ModuleAnalysisCache`（PowerShell 分析缓存），未清理。

### 3) Next Plan
1. 无可执行待办；如需新功能按 `docs/spec/DEVELOPMENT_ROADMAP.md` 另行确认开工。
2. 可选：把 Release 说明归档到 `docs/releases/v0.1.0.md`；清理 `Microsoft\` 误落缓存。

### 4) Verification
- 已通过（历史）：换肤 `pytest tests/test_talk_desktop.py`/`test_boot_status.py`；图标 25+3；ACL 41+9；Codex 版本 59+26；终端过滤 26+3；整机退出/托盘 53 项（K2.8 #861）；#862 30 passed + 5 subtests（K2.8 #865 approved）。
- 构建改动：`pytest tests/test_build_portable.py` **8 passed**（`40b5ebf`、本轮 README 修正后复跑仍 8 passed）。
- 本轮冒烟（11-18）：四版包各跑一次——解压 → `portable_bootstrap --apply` 生成 config/runtime/data/`data/keys/operator.key`/默认项目/管理员 → 临时端口 `/`、`/loading`、`/healthz`、`/manifest.webmanifest`、`/icons/favicon.ico`、`/api/projects` 全 200。
- 文档纠偏核对（11-18）：逐条对照代码确认——Key 默认 `data/keys`（`portable_paths.py:20`）、关窗不停服务（`talk_desktop.py:309`）、退出服务按钮在 header（`web/index.html:112`）、浏览器 Chrome→Edge→默认（`talk_desktop.py` `find_browser`）；6 份文档重写/修正、无断链。
- 包内容审查（11-18）：1476 → 1257 → 1254 → **1254（README 修正版）**；首版 58 个 docs 含机器名/内网 IP/本机路径（无密钥、无 DB、无 config.toml）；最终包重扫只剩 4 处代码默认值（见 §2），令牌/私钥 0 命中。
- 人工验收：用户确认通过（自动启动 / 整机退出 / 托盘消失）。
- 产品页核对（11-18）：README 无断链/缺图（3 张截图均已在仓库）；主动模式按用户要求只写"当前仅 DSH 验证通过"；同模型多角色依据 `USER_MANUAL:347` 与 `EXECUTION_SESSION_KIMI_ADAPTATION` 的双 K2.8 实例；群聊章节与 UI 核对一致（`web/index.html` 仅"任务 / 角色"两个标签）。
- Release（11-18）：`isDraft=false`、`isPrerelease=false`；`targetCommitish=82776cc…`；最终资产 `size=19621867`、`state=uploaded`、`digest=sha256:56f488ce…d9f1` 与本地一致；下载 HTTP 200 / `content-length` 相同。

### 5) Changed Files
- 今日主要：`web/*`（换肤/图标/manifest）、`server/routes/boot_status.py`、`server/routes/local_shutdown.py`、`server/routes/projects.py`、`scripts/talk_desktop.py`、`scripts/talk_launcher.py`、`scripts/talk_runtime.py`、`scripts/portable_paths.py`、`scripts/build_portable.py`、`bridges/codex_execution_native.py`、`scripts/codex_role_host.py`、`scripts/codex_role_setup.py`、`scripts/role_provision.py`、`scripts/role_service_host.py`、`tests/*`、`docs/*`。
- 本轮：`README.md`（重写为产品页）、`LICENSE`（新增 MIT）、`docs/guides/USER_MANUAL.md`（群聊章节改"已下线"、导航说明、调度模式示例）、`docs/guides/QUICKSTART*.md`、`docs/guides/PORTABLE_*.md`、`scripts/build_portable.py`（README 文案）、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`、`docs/HANDOFF_20261118.md`；无产品逻辑改动。

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`；上下文交接见 `docs/HANDOFF_20261118.md`。
- 恢复：新窗口说「继续项目」，先读本文件与交接快照。
