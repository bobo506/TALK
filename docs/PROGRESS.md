# Project Progress

## 当前快照（2026-11-13 15:22，P1b 文案人工验收通过）

- **P1b 验收通过**：用户目检角色详情「随项目自动启动」面板：Terra/K2.8 勾选、DeepSeek/Astra/hy4/大K/w-d 未勾选、提示语正确、归档角色不显示、旧通用文案不存在；skipped/failed 原因行按设计仅在对应状态出现，当前 `not_selected`/`enqueued` 不显示。
- **fixture 缺口已修复**：`tests/talk_runtime_fixture.py` 增加 `/api/projects/{project}/role-storage-layouts` 只读端点；`ActualBootstrapTests` 2/2 OK（23.4s），三模块 101 项 OK（105.5s，长 TEMP）；runtime `6664` 未受影响。
- **窄宿主归属证明已部署并通过真实崩溃验证**：14:16 只杀 runtime/API、保留 7 宿主；K2.8 标为 `external_manager/orphan_host_serving`、DeepSeek 标为 `orphan_host_configured`、Terra 保持 serving，无 `recovery_required`；Terra/K2.8 角色与实例未中断。
- **已恢复干净受管状态**：runtime `6664`，7 宿主全部 owned `serving`；Terra gen82/`ins_b8a390d9a761`、K2.8 gen80/`ins_2eb973afae92` 均 running/ready/idle；任务 0。
- **提交**：`59f5406`（代码）、`b650567`（fixture）、`1e2cd0b`/`055c24d`/`c660c33`/`bb5724f`（文档）；本次验收记录另提交。
- **仍待**：P2“长任务运行中 kill”真实场景。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
