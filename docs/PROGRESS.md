# Project Progress

## Latest

Updated: 2026-11-18 15:30 (+08:00)

**当前结论**：全部切片收口、人工验收通过、`v0.1.0` 已发布。**发布后复查发现首版包带出了内部开发文档（机器名/内网 IP/本机路径，无密钥），已重建干净包并覆盖 v0.1.0 资产**：19,647,501 B / 1257 文件 / sha256 `4c91a3b6…0374`，GitHub 侧 digest 一致、下载 200。无进行中任务、无待收取、无阻塞项。

### 1) Current Progress
- 路线图 13 项：第 1–7、12、13 完成；第 8 并入换肤；第 9 用户已清理；第 11 交接文档完成；**第 10 构建+冒烟完成，v0.1.0 已发布（资产已替换为干净包）**。
- 关键提交：换肤 `2517fd4`/`f9d0ac2`/`409a629`/`537634e`/`a7423f7`；图标 `c47b316`；ACL `5ce37c3`；Codex 版本 `faa57bc`；终端过滤 `6c6fed7`；便携包 `c8bc206`；按钮迁移 `9fa801d`；整机退出/托盘 `1fb21ab`；启动器自动 runtime `2290ae0`；文档收口 `baed1fe`/`82776cc`/`9b99d05`。
- 角色：Terra、K2.8 serving（idle）；Astra stopped（未勾自动启动，符合预期）；无 running 任务，`submitted` 对账为空。
- 生产：runtime `10136` 自 11-18 00:38 运行，API 8000 存活；未在 agent 侧启停。
- 便携包（发布资产）：`D:\backups\portable-clean-20261118\TALK-portable-0.1.0.zip`（19,647,501 B / 1257 文件 / sha256 `4c91a3b6…0374`）；文档只留 `docs/guides/` 3 篇用户向说明并已脱敏；内部 docs 暂存 `D:\backups\portable-clean-20261118\docs-removed`。

### 2) Open Questions / Pending Confirmation
- 无阻塞项。`v0.1.0` 已发布：https://github.com/bobo506/TALK/releases/tag/v0.1.0
- 待跟进（未授权开工）：`scripts/build_portable.py` 的 `ALLOW` 仍含 `docs`，且“开发路径”检查豁免 `docs` 目录——下次构建会再次带入内部文档；需 Terra 开片改为用户向文档白名单，并增加机器名/内网 IP/`C:\Users\<user>` 扫描。
- 包内残留（代码默认值，未改以免与仓库源码不一致）：`scripts/kimi_k28_executor.py:70` 默认 `D:/claude-test/TALK`、`scripts/talk_desktop.py:90` 回退 `../TALK-private`、`scripts/codex_role_host.py:41` 回退 `C:/Users/Administrator`、`examples/agent_poller.py:18` 示例 IP。
- 已知遗留：`scripts/talk_desktop.py` 历史 mojibake（未修，避免扩大）；本机部分测试受 key 继承 ACL 影响（基线同样复现）。
- 杂项：仓库根误落未跟踪 `Microsoft\Windows\PowerShell\ModuleAnalysisCache`（PowerShell 分析缓存），未清理。

### 3) Next Plan
1. 派 Terra 一片修 `build_portable.py` 的文档白名单与个人信息扫描（防复发）；
2. 可选：把 Release 说明归档到 `docs/releases/v0.1.0.md`；
3. 可选：清理 `Microsoft\` 误落缓存（移入隔离区）。

### 4) Verification
- 已通过（历史）：换肤 `pytest tests/test_talk_desktop.py`/`test_boot_status.py`；图标 25+3；ACL 41+9；Codex 版本 59+26；终端过滤 26+3；整机退出/托盘 53 项（K2.8 #861）；#862 30 passed + 5 subtests（K2.8 #865 approved）。
- 本轮冒烟（11-18）：首版包与干净包各跑一次——解压 → `portable_bootstrap --apply` 生成 config/runtime/data/`data/keys/operator.key`/默认项目/管理员 → 临时端口 `/`、`/loading`、`/healthz`、`/manifest.webmanifest`、`/icons/favicon.ico`、`/api/projects` 全 200。
- 包内容审查（11-18）：1476→1257 文件；首版 58 个 docs 含机器名/内网 IP/本机路径（无密钥、无 DB、无 config.toml）；干净包仅留 3 篇用户向文档并脱敏，重扫剩余命中仅 4 处代码默认值（见 §2）。
- 人工验收：用户确认通过（自动启动 / 整机退出 / 托盘消失）。
- Release（11-18）：`gh release view` 返回 `isDraft=false`、`isPrerelease=false`；`targetCommitish=82776cc…`；替换后资产 `size=19647501`、`state=uploaded`、`digest=sha256:4c91a3b6…0374` 与本地一致；下载链接 HTTP 200 且 `content-length` 相同。

### 5) Changed Files
- 今日主要：`web/*`（换肤/图标/manifest）、`server/routes/boot_status.py`、`server/routes/local_shutdown.py`、`server/routes/projects.py`、`scripts/talk_desktop.py`、`scripts/talk_launcher.py`、`scripts/talk_runtime.py`、`scripts/portable_paths.py`、`scripts/build_portable.py`、`bridges/codex_execution_native.py`、`scripts/codex_role_host.py`、`scripts/codex_role_setup.py`、`scripts/role_provision.py`、`scripts/role_service_host.py`、`tests/*`、`docs/*`。
- 本轮仅改文档：`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`、`docs/HANDOFF_20261118.md`；工作区无未提交代码。

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`；上下文交接见 `docs/HANDOFF_20261118.md`。
- 恢复：新窗口说「继续项目」，先读本文件与交接快照。
