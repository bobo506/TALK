# 351-D Kimi 执行侧：受管改写角色配置（经用户授权选定方案 A）

日期：2026-10-31。接续 351-C。生产状态：**本轮随后与 351-C 一起加载**（用户明确选择）。
候选 `.tmp/role-effort-detail-20261031/task-351D/`，基线为 351-C 冻结候选。

## 1. 背景与约束

核实结论（`kimi --help`）：Kimi CLI 只有 `-m/--model`，**没有按次传思考强度的参数**；
强度来自角色 `config.toml` 的 `[models."<alias>"] default_effort`。用户选定**方案 A**：
每个任务执行前由 bridge 把生效强度原子写进该角色自己的配置。

## 2. 实现

| 位置 | 改动 |
|---|---|
| `bridges/kimi_effort.py`（新） | `resolve_target_effort`（只按公开绑定取目标值，能力未知/不在清单 → None）；`set_model_default_effort`（只改目标模型段的一个键，其余字节不动，不新建段）；`apply_role_config_effort`（临时文件 + `os.replace` 原子替换，失败不改原文件） |
| `bridges/cli_bridge.py` | 新增 `run_before_task` 与 `before_task_factory`：工厂在拿到 client 后构造逐任务钩子；未注册时是空操作，其它运行器行为不变 |
| `bridges/kimi_bridge.py` | 注册 `make_effort_hook`：每个任务前读 `/agents` 公开绑定 → 解析目标强度 → 写角色 `config.toml`；读取失败/能力未知只留一行诊断并保留原配置 |
| `tests/test_kimi_effort.py` | 15 项：取值规则、只改目标键、缺键插入、缺段拒绝、原子写、同值不重写、钩子在有/无 `KIMI_CODE_HOME`、同步/异步钩子 |

## 3. 语义与安全

- 目标值优先级与 351-A/B 一致：用户覆盖 > 模型默认；不在公开清单内 → 不写；
- 只写 `KIMI_CODE_HOME/config.toml`（角色私有目录，由宿主注入并校验隔离），不读凭据、不启动模型；
- 只替换目标模型段的 `default_effort` 行，保留 provider/token/其它模型段原样；
- 单 worker 串行执行，同角色不会并发写；准备流程只在服务停止时运行，冲突面小；
- 清空用户覆盖后，下一次执行会把配置写回模型默认（`effective_effort` 回落）。

## 4. 验收（本片实测）

- `python -B -X utf8 -m unittest tests.test_kimi_effort` → **15 OK**
- 桥接回归 `test_cli_bridge + test_codex_bridge + test_kimi_bridge + test_kimi_effort` → **178 OK**
- C/B 相关回归 `能力落库 + Codex 准备 + Kimi 准备 + 351-B 强度 + 运行时 + Kimi 钩子` → **100 OK**

未验证：没有用真实 Kimi 模型跑任务核对强度是否被 CLI 采用；未在真实角色配置上执行（本片随后加载，
加载后可用下一次任务验证）。

## 5. 回退

恢复本片 5 个文件到 351-C 候选即可；角色配置若已被改写，恢复其原文（加载时会先备份角色配置
或由准备流程重新写回模型默认）。
