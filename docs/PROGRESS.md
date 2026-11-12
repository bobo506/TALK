# Project Progress

## 当前快照（2026-11-12 23:40，异常退出审计完成，待修复）

- **第 12 项审计（生产空闲窗口受控 kill）**：先设 Terra 启动偏好开、K2.8 关；强制 kill runtime 树后重启。结论：
  - 选择性自启动**部分生效**：K2.8（偏好关）被跳过；但原因是 `startup_manual_intent_present`（陈旧 `desired=running`），随后 observed=failed。
  - **无自动恢复**：Terra 陈旧 `running` + 死 pid 使启动激活停在 `recovery_required`/unknown，`start-all` 返回 `skipped_running`；需人工 `stop` 后再 `start-all` 才恢复（Terra gen73、K2.8 gen72，running/ready）。
  - **旧宿主残留**：9160/12484/11592/14260 在 runtime 死后仍存活，被新 runtime 记为 `external_manager`，需人工终止。
  - 首次 `taskkill /F /T` 未杀死 runtime（exit -1），需显式 Stop-Process。
- **服务已恢复**：healthz ok、Terra `ins_6cdc22ab7640`、K2.8 `ins_f3b7ddd2419e`，启动偏好均已恢复 enabled。
- **建议修复（未开工，待确认）**：P0 启动时按进程身份识别 stale running 并降级/选择性启动；P1 孤儿宿主归属核验与可见恢复入口；P1 偏好与手动意图冲突的提示、`last_activation` 原因展示；P2 kill 时有运行任务的 claim/lease 恢复验证。
- **证据**：`.tmp/e2e-crash/findings.md` 与同目录 JSON。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
