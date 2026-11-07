# W3b 部署与验收说明（2026-11-08）

状态：**代码完成、终轮全量回归零新增失败、未部署**。W3a 已于 2026-11-07 12:05 随运行时重启进入生产（新角色为 `workspace-v1`，可建不可跑）。本说明供用户部署与验收使用。

## 一、部署范围与前置

- W3a + W3b **同一窗口**部署。
- 备份 `talk.db`（连同 `-wal`/`-shm`）到独立目录；部署后核对 `project_roles`/`role_provision_requests` 的 `storage_layout` 列与旧行值。
- 磁盘：C 盘剩余建议 ≥5 GB；`~/.talk/role-service-host/runtime/api.err`（约 1.6 GB）与 `api.out`（约 0.5 GB）可清理。
- **清理测试残留**（否则 workspace-v1 provision 会报 `profile_root_invalid`）：
  - `D:\claude-test\TALK\workspaces\prj_alpha`（project_root 指向 `.tmp-tests` 的测试项目）；
  - `workspaces` 及子目录 ACL 中的 `CodexSandboxOffline` 项（保留 当前用户/SYSTEM/Administrators）。
- 清理 547 报告的历史孤儿测试进程（`talk_runtime`/`talk_api` fixture，端口 50515/51882）。

## 二、部署步骤

1. 正常停止运行时：`run.ps1 -Action stop -Apply -Config D:\claude-test\TALK-private\talk-runtime.json`。
2. 备份 `talk.db`。
3. 确认工作区在目标 HEAD（`git log -1`，应含 W3b 全部提交）。
4. 启动：`run.ps1 -Action serve -Apply -Config ...`；确认 `/healthz` 200、runtime health `startup_state=complete`、`<state>/runtime/capability.json` 已生成。
5. 手动 start 需要的角色服务（Terra、k2.8；astra 暂未重建）。
6. **默认门关闭验证**：新建一个 workspace-v1 角色 → 点启动应返回 `409 workspace_runtime_not_ready`；legacy 角色启停与改动前一致。

## 三、开闸（默认不做）

仅当确认要启用新布局角色时：

1. 给 API/runtime 进程显式设置 `TALK_WORKSPACE_RUNTIME_ENABLED=1` 并重启运行时（不是请求体参数，客户端无法伪造）。
2. 开闸后验证：`capability.json` 的 schema/`supported_layouts`/`pid` 存活；manager health 的 `capability` 与本次 launch 的 instance/generation/launch 一致；缺证据/旧 manager 必须被拒。
3. 任何一项不符 → 取消环境变量并重启，回到关闭态。

## 四、验收清单（真实浏览器 + 真实 CLI）

1. legacy 角色启动/停止与改动前一致（含自动启动反馈）。
2. 新建 workspace-v1 角色：provision 成功（无 `profile_root_invalid`）；默认门关闭时启动 409；页面提示符合预期。
3. 开闸后：该角色启动 ready；`workspaces/<P>/roles/<M>/` 下 `native-home`、`sessions`、`state/{records,control,manager}`、`logs` 落点正确；同项目第二个角色不共享这些目录。
4. 同项目角色 A stop 后 B 继续运行，runtime 不整体停止。
5. 恢复（可选）：终止 A 的 manager 后走本地恢复，验证只恢复 A、拒绝伪造/过期证据。
6. 重建 astra（模型选 `GPT-6 Astra`）：建好后先做三行回答测试；若仍只回 `1.`，记录并转修 `bridges/codex_execution_native.py` 的 `item/completed` 采集。

## 五、回退

- 取消 `TALK_WORKSPACE_RUNTIME_ENABLED` 并重启 → 门回到关闭态。
- 代码回退：`git revert` 或回到 `945c074`；数据库用备份恢复（`storage_layout` 列可保留，旧行为按 `legacy`）。

## 六、已知限制

- 168 项基线历史测试失败（非 W3b 引入，基线同败）。
- `ActualBootstrapTests` 两条在 Windows 文件锁下不收敛（基线同因，环境限制）。
- `talk_delegate_task` 工具 schema 的澄清轮数默认 1/上限 2 与服务端 3/5 不一致（已知缺陷，待单独小片修）。
- 真实 CLI、双工作区隔离、并发路径替换（TOCTOU）未在本机验证，属 W3c 真实验收范围。
