# Project Progress

## 当前快照（2026-11-13 10:25，遗留宿主收口完成）

- **收口结果**：02:28 重启后遗留的两个外部窄宿主已由本代 runtime 重新拉起为自有宿主（`serving`），不再是 `recovery_required/orphan_host_unverified`。
  - K2.8：旧宿主 `2944` 终止 → 新宿主 `444`（runtime 14544 子进程）→ 正常 start gen76，实例 `ins_529c8c6abc32`、桥 `10624`，running/ready/idle。
  - DeepSeek：旧宿主 `7448` 终止 → 新宿主 `4308`；角色服务保持 stopped，无桥进程。
  - Terra 未受影响：宿主 `14548`、实例 `ins_4cd512d3ddd3`、running/ready/idle。
- **现状**：runtime `14544` running/startup complete，7 个宿主全部 `serving`；healthz ok；`submitted/assigned/in_progress` 均为 0。
- **更正**：上一快照“K2.8 旧 unmanaged 宿主已替换为受管实例”只对实例成立；宿主仍是清单配置的 `.tmp` 窄宿主（外部进程），本轮才真正收口。
- **残余**：宿主仍依赖 `.tmp/legacy-role-page-control`（部署依赖）；下次崩溃重启后仍会被判 `orphan_host_unverified`，根治需另开代码片识别清单内窄宿主 argv。P1b 文案目检、P2 真实长任务 kill 仍未做。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
