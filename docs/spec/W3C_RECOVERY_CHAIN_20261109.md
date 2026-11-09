# W3c-2 恢复链：诊断、修复与真实 E2E（2026-11-09）

状态：**W3c-2a 完成并验证**。诊断由协调者执行（586 K2.8 复核 approved）；修复 588 → 593（K2.8 592/594 复核 approved）。

## 一、诊断结论（临时项目 B，runtime B attach-api）

| 场景 | 操作 | 结果 |
|---|---|---|
| a | running 角色 → `stop --wait` runtime → 重启 → 再 start | `stopped/complete`；角色转 stopped（gen 2）；重启后 start 直接 ready（`ins_a7481863fa9f`）；API 稳定窗口内未复现 `host_unreachable` |
| b | 仅 kill 宿主（bridge 存活） | runtime `recovery_required`、`ownership_held=true`；start 409 `already_running`；stop launch `pending` 无人领取 → **永久死锁**（重启 runtime 也不能自愈：孤儿 bridge 直连心跳使 `recovery_recent_heartbeat` 恒成立） |
| b 恢复 | kill bridge + 等 90s 实例过期 → stop | `idempotent_stopped`、ownership 释放；start ready（`ins_9873e32715d5`） |
| c | kill bridge（宿主存活） | 宿主回报 `bridge_process_exited` 并释放（ownership false、can_start true）；再次 start ready（`ins_507b88a7a19d`） |
| d | stop 后立即 delete | 409 `role_instance_active`（90s 新鲜心跳保护）；等 >90s 后 delete 5 步 complete；残留 `native-home/.dsh`、`profiles/.provision.lock.guard`、`keys/*.key.lock.guard`（既有债务） |

诊断证据：`.tmp/w3c2-dual-20261109/w3c2-scenario-a.json|b.json|b2.json`、`.tmp/w3c2-diag/scenario-cd.json`、`.tmp/w3c2-review/review.json`。

## 二、修复（W3c-2a：孤儿 bridge 受控清理）

- `244f226`（588，592 approved）：`TalkRuntime._terminate_orphan_bridge()` 在 `reconcile_hosts` 的 `ownership_held` 分支调用；仅当 manager health 存在且 pid ∈ `EXITED_PROCESS_STATES`、`not self.stopping`、实例 status=idle 且无 current_task、同机/同项目、pid 存活时，用 Windows `OpenProcess` 句柄 + 句柄创建时间比对 + `TerminateProcess` 终止；二次查询确认；异常记事件不中断 reconcile；`recovery_required` 语义不变。
- `6a6d0c5`（593，594 approved）：真实 E2E 发现 1.53s 的“记录启动时间早于真实创建”被 `recorded_process_state` 的 +1s 容差判成 `pid_reused`，导致永不清理；Windows 分支移除该 1s 前置门槛，改由句柄创建时间比对、容差 5s；非 Windows 保留原门槛。

## 三、真实 E2E（runtime B 新代码，临时项目 B）

1. 启动 runtime B → `startup_state=complete`；角色 ready `ins_48280c199d53`（bridge 6288）。
2. **kill 宿主 7536** → runtime 在 **~6 秒内**终止孤儿 bridge 6288（2s 采样：4s 存活、6s 消失），宿主状态 `recovery_required`。
3. 等 90s 实例过期 → stop 返回 `idempotent_stopped`（gen 6）→ start ready `ins_d981d84a3696`（gen 7）。
4. 清理：stop/delete 角色 5 步 complete、删除项目 B、停 runtime B、移除 `workspaces/<pB>` 与 `keys-b`；仅剩 `prj_e8fe7066bbec`。

## 四、残余（非阻断，待后续片）

1. ~~**人工显式恢复入口**（586 必须修 2）~~ **W3c-3 已完成（2026-11-09，599/600 approved）**：human 显式“重置”，见第六节。
2. **终止后轮询语义**：仍用 `recorded_process_state(pid, process_started_at)`，1.5s 偏差会立即判 `pid_reused` 并记 `terminated`，不能单凭事件证明进程已退出；可选改为 `WaitForSingleObject`/`GetExitCodeProcess` 真实存活确认。
3. **delete 90s 窗口**：bridge 退出后实例行仍 idle，删除需等 90s 新鲜度过期；可在“进程已证退出”时跳过（可选）。
4. **`host_unreachable`** 未复现：仅覆盖 API 稳定窗口；需 API reload 窗口专项复现。
5. `keys/*.key.lock.guard`、空 `native-home` 残留属既有 legacy 债务。

## 五、部署说明

`scripts/talk_runtime.py` 属 runtime 进程代码，生产 runtime A（pid 3704）需下次重启才带上本修复；E2E 已在临时项目 B 的 runtime（新代码进程）验证同一路径。W3c-3 新增 API 路由，需**受控 reload 生产 API** 才对外生效。

## 六、W3c-3：忙孤儿人工受控终止与恢复（2026-11-09，599 开发 / 600 K2.8 approved）

- **入口**：`POST /api/projects/{project_id}/roles/{member_id}/service/recover-orphan`，仅 human、仅本机 runtime 已绑定；请求 `operation_key`、`expected_generation`、`confirm_task_interrupt`、`reason`。
- **证明链**：身份事实（launch/instance/owner_host/pid/process_started_at 一致）→ 同机 hostname → manager 健康文件身份 + `recorded_process_state` 非 present → bridge 句柄创建时间与 `process_started_at` 偏差 ≤5s → argv 经 `CommandLineToArgvW` 解析且命中内置 bridge 模块白名单与 `--project-id/--name/--instance-id/--launch-id`。自定义 bridge 入口无法归因时**安全拒绝**（`orphan_process_unverified`）。
- **终止**：`OpenProcess` + 二次创建时间比对 + `TerminateProcess` + `WaitForSingleObject(5s)` + `GetExitCodeProcess`；`already_exited`（absent/exited）直接进入恢复。
- **安全合同（方案 A）**：终止前的一切拒绝零终止、零 DB 写入；终止已发起但退出未确认 → 409 `orphan_terminate_failed`、`termination_initiated=true`、`exit_confirmed=false`、零 DB 写入，重试按 `already_exited` 继续恢复。证明与终止在 `BEGIN IMMEDIATE` 事务内执行，慢机写锁最长约 10–20s（含本机 CIM 查询）。
- **任务语义**：该成员在**本项目内**的 queued/running 任务存在时，未确认 → 409 `orphan_tasks_active`（尚未终止）；确认后任务置 `failed`、`last_error=orphan_terminated_by_human`、释放 claim/lease、不重派、不通知、跨项目不动。未被他实例领取的同项目 queued 任务也会一并记失败（成员级口径）。
- **真实 E2E**（隔离栈：独立 API 8011 + 库副本 + 同根临时 runtime B，生产未动）：复现 start 409 `already_running` / stop launch 永久 `pending` / `ownership_held=true`；无活动任务时 200 真实终止存活 bridge（`exit_code=1`）→ gen1→2 → start ready；忙任务时首次 409 `orphan_tasks_active` → 确认后终止 + 中断记账 → gen3→4 → start ready。证据 `.tmp/w3c3-e2e/E2E_SUMMARY.json`。
- **复核遗留（非阻断）**：`instance.current_task_id` 终止后未清（已核查消费者不受影响）；queued 任务成员级语义需补测；`operation_key` 缺 pattern；写锁时长需文档化；自定义入口拒绝范围。
