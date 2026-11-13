# Project Progress

## 当前快照（2026-11-13 14:22，窄宿主归属证明已部署并通过真实崩溃验证）

- **真实崩溃复现通过**：14:16 只杀 runtime `1484` + API `8500`、保留 7 宿主；新 runtime `10712` 把 K2.8 窄宿主 `14140` 标为 `external_manager/orphan_host_serving`、DeepSeek `13084` 标为 `external_manager/orphan_host_configured`、Terra 标为 `external_manager/orphan_host_serving`；无 `recovery_required`。
- **角色未中断**：Terra `ins_75d2582d5aad`/`8472`、K2.8 `ins_2d680caadfcf`/`11240` 全程 running/ready；healthz ok；任务 0。
- **已恢复干净受管状态**：14:20:43 runtime `6664`，7 宿主全部 owned `serving`（DeepSeek `2868`、K2.8 `13772`、Astra `15736`、Terra `12548`、hy4 `14600`、大K `15580`、w-d `12352`）；Terra gen82/`ins_b8a390d9a761`、K2.8 gen80/`ins_2eb973afae92` 均 running/ready/idle。
- **提交**：`59f5406`（代码）、`1e2cd0b`/`055c24d`（文档）；本次崩溃验证记录另提交。727/728/729 已收取。
- **仍待**：`tests/talk_runtime_fixture.py` 缺 `/api/projects/{project}/role-storage-layouts` 的基线夹具缺口（建议另片）；P1b 启动原因文案目检；P2“长任务运行中 kill”。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
