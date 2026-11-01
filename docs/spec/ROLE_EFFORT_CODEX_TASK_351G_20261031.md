# 351-G Codex 逐任务思考强度（接入真实接单路径）

日期：2026-11-01。根因：真实接单走 `cli_bridge.run_task_queue_worker`，不会调用
`codex_bridge.handle_queued_task` 的兼容包装，所以 351-B 的"每任务重取强度"从未生效，
页面改强度后仍沿用启动时烘焙值（小G、Terra 都如此）。

## 修复

| 位置 | 改动 |
|---|---|
| `bridges/codex_bridge.py` | 新增 `make_effort_hook`：每个任务（预检+正式执行）前从 `/agents` 读公开绑定，解析 `effective_effort`，从**启动模板**重新生成两条命令（`-c model_reasoning_effort=` 与 `--effort` 两种形态）；`run_bridge` 保存模板并注册 `before_task_factory` |
| `bridges/cli_bridge.py` | 钩子调用移入预检 `try`：钩子抛 `TaskPreflightError` 时按预检失败处理（不再静默沿用旧值） |
| `tests/test_codex_task_effort.py` | 9 项：两种命令形态、模板化不累积、真实队列路径、失败策略 |

失败策略：用户显式覆盖且解析失败/命令形态不认识 → 任务失败并写明原因；没有覆盖（仅模型默认）
→ 保留启动值 + 一行诊断。

## 实测（加载后，未重启角色）

启动时绑定：小G `high`、Terra `xhigh`；启动后改为 `low` 再派任务：

| 角色 | 预检证据 | 正式任务证据 | 结果 |
|---|---|---|---|
| 小G（旧入口） | 23:04:33–38 `--effort low` | rollout 23:04:47 `effort=low`；任务 390 23:04:56 成功 | ✅ |
| Terra（动态宿主） | rollout 23:04:35 `effort=low` | rollout 23:06:32 `effort=low`；任务 391 23:08:29 成功 | ✅ |

对比：改值前 Terra 的 rollout 是 `high`（启动值），改值后同一角色持续运行即为 `low`，无需重启。

## 边界

- 加载这次修复需要重启一次 runtime（已完成）；之后页面改强度对下一次任务生效，无需重启。
- 普通消息回合仍用启动时的强度（设计如此，不属于任务执行）。
- 生产提交：`6b3b01e`；测试 9 项 + 回归 171 项通过。
