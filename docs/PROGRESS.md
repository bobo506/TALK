# Project Progress

## 当前快照（2026-11-13 02:40，异常退出恢复 P0/P1/P2 完成并部署验证）

- **第 12 项修复全部完成并独立复核（717–726）**：
  - **P0（717/718）**：启动快照不再把 observed 心跳误判为手动意图；stale running（本机、pid/启动时间证明已死、身份一致、无任务/租约/活动 launch）先安全降级再按启动偏好选择性启动；禁用偏好 → `startup_not_selected`，活进程仍 `skipped_running`。
  - **P1a（719/720 + 725/726 修正）**：runtime 启动时对 `external_manager` 做 argv 归属证明；**仍在服务角色的宿主不终止**，标 `external_manager/orphan_host_serving`；非运行态才受控终止并重新拉起；证明失败 `recovery_required/orphan_host_unverified`，不静默接管。
  - **P1b（721/722）**：启动面板显示精确原因（`startup_manual_intent_present`/`startup_not_selected`、`recovery_required`、`bridge_process_exited` 等），未恢复被用户移除的通用旧文案。
  - **P2（723/724）**：过期租约+死实例的 requeue/instance 清理/CAS 验证，补最小修复；未过期不提前抢占。
- **真实崩溃验证**：
  - 全杀（含宿主）→ 重启：Terra/K2.8 **自动 running/ready**（Round A；最终 `ins_4cd512d3ddd3` gen78、`ins_eb9cf19698f7` gen74）。
  - 只杀 runtime/API、保留宿主：修正前 P1a 误杀服务中 Terra 宿主（已用 recover-stopped 恢复）；修正后服务中宿主不杀，标 `external_manager/orphan_host_serving`，角色保持运行。
- **已知限制**：P2 的“kill 时有运行任务”仅隔离测试验证，未做真实长任务 kill；P1b 文案视觉验收待用户；K2.8 旧 unmanaged 宿主在测试中已被替换，当前为受管实例。
- **部署**：runtime 已用新代码重启（P1a 生效）；API 随 runtime 加载 P0/P1b/P2；Terra/K2.8 running/ready、healthz ok、`submitted=[]`。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
