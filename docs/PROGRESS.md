# Project Progress

## 当前快照（2026-11-13 13:50，窄宿主归属证明复核通过，待部署）

- **727–729 完成**：`config["hosts"]` 窄宿主按完整 argv + health 身份识别；服务中 → `external_manager/orphan_host_serving`，非服务态 → `orphan_host_configured`，只观察、不接管、不终止、不重拉；标准 `*_role_host.py` 路径不变。
- **复核**：K2.8 729 approved（9 项 verification 全 pass、15 项对抗用例、0 阻断）；727/728/729 已收取，`submitted=[]`。
- **提交**：`59f5406`（仅 `scripts/talk_runtime.py`、`tests/test_talk_runtime.py`）；**runtime 仍是 02:28 加载的旧代码，改动未生效**，清单内窄宿主在新逻辑加载前仍会显示 `recovery_required`。
- **基线缺口**：`tests/talk_runtime_fixture.py` 缺 `/api/projects/{project}/role-storage-layouts`，`ActualBootstrapTests` 在 HEAD `7e0896f` 与候选均 `errors=2`（独立 worktree 复跑确认），与 727 无关；建议另开小片修夹具。
- **现状**：runtime `14544`、7 宿主 `serving`；Terra/K2.8 running/ready/idle；healthz ok；无待收取/进行中任务。
- **下一步**：待用户确认后重启 runtime 加载 `59f5406`，并做真实崩溃验证（只杀 runtime、保留窄宿主 → 应显示 `external_manager/orphan_host_serving`）；夹具缺口另片。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
