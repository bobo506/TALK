# Project Progress

## 当前快照（2026-11-13 14:10，窄宿主归属证明已部署）

- **727–729 已部署**：`59f5406` 于 14:06:20 由新 runtime `1484` 加载（API child `8500`、`api_mode=owned`、startup complete）。
- **运行态**：7 个宿主全部 `serving`（deepseek `13084`、K2.8 `14140`、Astra `780`、Terra `16128`、hy4 `15564`、大K `8684`、w-d `12008`）；Terra gen80/`ins_75d2582d5aad`、K2.8 gen78/`ins_2d680caadfcf` 均 running/ready/idle；healthz ok；`submitted/assigned/in_progress=0`。
- **能力**：`config["hosts"]` 窄宿主按完整 argv + health 身份识别；服务中 → `external_manager/orphan_host_serving`，非服务态 → `orphan_host_configured`，只观察、不接管、不终止、不重拉；标准 `*_role_host.py` 路径不变。
- **待验证**：真实崩溃复现（只杀 runtime/API、保留窄宿主）尚未做；`external_manager` 路径仍是代码/单测/复核证据，未在真实崩溃中观察。
- **已知缺口**：`tests/talk_runtime_fixture.py` 缺 `/api/projects/{project}/role-storage-layouts`，`ActualBootstrapTests` 在 HEAD `7e0896f` 与候选均 `errors=2`；建议另开小片修夹具。
- **提交**：`59f5406`（代码）、`1e2cd0b`（文档）；727/728/729 已收取。
- **下一步**：维护窗口做真实崩溃复现；修 fixture 缺口；P1b 文案目检、P2 长任务 kill 仍未做。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
