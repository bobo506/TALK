# Project Progress

## Latest

Updated: 2026-11-18 00:57 (+08:00)

**当前结论**：今天全部切片收口（HEAD `2290ae0`）：换肤 4 片、图标、ACL 健壮性、Codex 版本（第 12）、终端过滤（第 13）、便携包构建+冒烟+交接、退出按钮迁移、退出停整机+托盘、启动器自动带 runtime（#862，已复核）。**只剩人工验收**（重启验证自动启动/整机退出/托盘）与 **Release**（`gh auth login` 后发布 `v0.1.0`）。

### 1) Current Progress
- 路线图 13 项：第 1–7、12、13 完成；第 8 并入换肤；第 9 用户已清理；第 11 交接文档完成；**第 10 构建+冒烟完成，Release 待 `gh auth login`**。
- 换肤 1–4：`2517fd4`+`f9d0ac2`、`409a629`、`537634e`、`a7423f7`；图标 `c47b316`；ACL `5ce37c3`；Codex 版本 `faa57bc`；终端过滤 `6c6fed7`；便携包 `c8bc206`；按钮迁移 `9fa801d`；整机退出/托盘 `1fb21ab`。
- 角色：Terra、K2.8 running；Astra stopped（未勾自动启动，符合预期）；任务 #862 由 Terra 执行中。
- 生产：API 约 00:36、runtime 约 00:38 启动；此前“重启后 Astra 仍在跑”已确认是旧进程未停，不是自动启动。
- 便携包：`D:\backups\portable-final-20261117\TALK-portable-0.1.0.zip`（24,932,084 B / 1474 文件 / sha256 `edac9d69…`），隔离沙箱 bootstrap+HTTP 冒烟通过。

### 2) Open Questions / Pending Confirmation
- #862 未复核：启动器自动带 runtime 后，需确认不会与已运行的 runtime 冲突、失败不阻断窗口。
- 真实整机退出未实测：点“退出服务”后 runtime/角色/API/Chrome 托盘是否全部退出；有任务时 409 提示是否正常。
- Release 阻塞：`gh auth login` 未执行；发布前建议用新 Key 逻辑重建最终 zip。
- 已知遗留：`scripts/talk_desktop.py` 历史 mojibake（未修，避免扩大）；本机部分测试受 key 继承 ACL 影响（基线同样复现）。

### 3) Next Plan
1. 等 #862 完成 → K2.8 复核 → 提交推送；
2. 用户完整重启 → 验证自动启动（仅 Terra/K2.8）与“退出服务”停整机、托盘消失；
3. `gh auth login` → 重建便携包 → 发 `v0.1.0` Release（zip 资产，不进 git）；
4. 按需处理路线图剩余可选项（如 diagnostics 页表格/筛选）。

### 4) Verification
- 已通过：换肤各片 `pytest tests/test_talk_desktop.py`/`test_boot_status.py`；图标 25+3；ACL 41+9；Codex 版本 59+26；终端过滤 26+3；整机退出/托盘 53 项（K2.8 #861）。
- 冒烟：解压 → `portable_bootstrap` 生成 config/data/data/keys/operator.key/project；临时端口 `/loading`、`/manifest.webmanifest`、`/icons/favicon.ico`、`/` 均 200。
- 未验证：真实整机退出与托盘退出、启动器自动 runtime（#862 完成后）；Release 未发布。

### 5) Changed Files
- 今日主要：`web/*`（换肤/图标/manifest）、`server/routes/boot_status.py`、`server/routes/local_shutdown.py`、`server/routes/projects.py`、`scripts/talk_desktop.py`、`scripts/talk_launcher.py`、`scripts/talk_runtime.py`、`scripts/portable_paths.py`、`scripts/build_portable.py`、`bridges/codex_execution_native.py`、`scripts/codex_role_host.py`、`scripts/codex_role_setup.py`、`scripts/role_provision.py`、`scripts/role_service_host.py`、`tests/*`、`docs/*`。
- 工作区未提交：`scripts/talk_desktop.py`（#862）。

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`；上下文交接见 `docs/HANDOFF_20261118.md`。
- 恢复：新窗口说「继续项目」，先读本文件与交接快照。
