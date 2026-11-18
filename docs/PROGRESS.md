# Project Progress

## Latest

Updated: 2026-11-18 15:00 (+08:00)

**当前结论**：全部切片收口，人工验收通过，**`v0.1.0` Release 已于 11-18 14:57 发布**（tag `v0.1.0` 指向 `82776cc`，资产 `TALK-portable-0.1.0.zip` 上传后 GitHub 侧 sha256 与本地完全一致）。无进行中任务、无待收取、无阻塞项；剩余仅可选项。

### 1) Current Progress
- 路线图 13 项：第 1–7、12、13 完成；第 8 并入换肤；第 9 用户已清理；第 11 交接文档完成；**第 10 构建+冒烟完成，本地资产为 11-18 新包，Release 待 `gh auth login`**。
- 关键提交：换肤 `2517fd4`/`f9d0ac2`/`409a629`/`537634e`/`a7423f7`；图标 `c47b316`；ACL `5ce37c3`；Codex 版本 `faa57bc`；终端过滤 `6c6fed7`；便携包 `c8bc206`；按钮迁移 `9fa801d`；整机退出/托盘 `1fb21ab`；启动器自动 runtime `2290ae0`；文档收口 `baed1fe`。
- 角色：Terra、K2.8 serving（idle）；Astra stopped（未勾自动启动，符合预期）；无 running 任务，`submitted` 对账为空。
- 生产：runtime `10136` 自 11-18 00:38 运行，API 8000 存活；未在 agent 侧启停。
- 便携包（最新）：`D:\backups\portable-release-20261118\TALK-portable-0.1.0.zip`（25,027,275 B / 1476 文件 / sha256 `b37f651a…f0c7`），含 #862 与整机退出；隔离沙箱 bootstrap+HTTP 冒烟通过。

### 2) Open Questions / Pending Confirmation
- 无阻塞项。`v0.1.0` 已发布：https://github.com/bobo506/TALK/releases/tag/v0.1.0
- 已知遗留：`scripts/talk_desktop.py` 历史 mojibake（未修，避免扩大）；本机部分测试受 key 继承 ACL 影响（基线同样复现）。
- 杂项：仓库根误落未跟踪 `Microsoft\Windows\PowerShell\ModuleAnalysisCache`（PowerShell 分析缓存），未清理。

### 3) Next Plan
1. 按需处理路线图剩余可选项（如 diagnostics 页表格/筛选），需另行确认开工；
2. 可选：把 Release 说明归档到 `docs/releases/v0.1.0.md`；
3. 可选：清理 `Microsoft\` 误落缓存（移入隔离区）。

### 4) Verification
- 已通过（历史）：换肤 `pytest tests/test_talk_desktop.py`/`test_boot_status.py`；图标 25+3；ACL 41+9；Codex 版本 59+26；终端过滤 26+3；整机退出/托盘 53 项（K2.8 #861）；#862 30 passed + 5 subtests（K2.8 #865 approved）。
- 本轮冒烟（11-18）：新包解压 1476 文件 → `portable_bootstrap --port 8931 --apply` 生成 config/runtime/data/`data/keys/operator.key`/默认项目/管理员 → 临时端口 `/`、`/loading`、`/healthz`、`/manifest.webmanifest`、`/icons/favicon.ico`、`/api/projects` 全 200；包内关键源码与 HEAD 逐字节一致。
- 人工验收：用户确认通过（自动启动 / 整机退出 / 托盘消失）。
- Release（11-18 14:57）：`gh release view` 返回 `isDraft=false`、`isPrerelease=false`；`targetCommitish=82776cc…` 即 HEAD；资产 `size=25027275`（与本地逐字节数量一致）、`state=uploaded`、GitHub 侧 `digest=sha256:b37f651a…f0c7` 与本地哈希相同。无未验证项。

### 5) Changed Files
- 今日主要：`web/*`（换肤/图标/manifest）、`server/routes/boot_status.py`、`server/routes/local_shutdown.py`、`server/routes/projects.py`、`scripts/talk_desktop.py`、`scripts/talk_launcher.py`、`scripts/talk_runtime.py`、`scripts/portable_paths.py`、`scripts/build_portable.py`、`bridges/codex_execution_native.py`、`scripts/codex_role_host.py`、`scripts/codex_role_setup.py`、`scripts/role_provision.py`、`scripts/role_service_host.py`、`tests/*`、`docs/*`。
- 本轮仅改文档：`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`、`docs/HANDOFF_20261118.md`；工作区无未提交代码。

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`；上下文交接见 `docs/HANDOFF_20261118.md`。
- 恢复：新窗口说「继续项目」，先读本文件与交接快照。
