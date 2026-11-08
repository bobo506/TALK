# W3c-1 双工作区隔离验收：阻塞发现（2026-11-09）

状态：**未通过/不能作为纯验收完成**。本片没有改产品代码；发现的是 4 处“单项目 = TALK 仓库根”的硬绑定，第二个工作区（另一项目根）的运行时从启动到清理都不成立。

## 结论

现有模型下，一个 TALK 实例只能为「项目根 = TALK 仓库根」的项目运行角色：

| # | 阻塞点 | 代码位置 | 实测现象 |
|---|---|---|---|
| F1 | 本机 runtime 绑定要求 `project_root` == TALK 仓库根；只在该条件下写 `.talk/runtime.local.json` | `server/local_runtime.py:22-53`（`bind_local_runtime` / `configured_runtime`） | 项目 B 的 runtime 调 startup 返回 **409 `startup_local_runtime_unbound`**，健康长期 `startup_state=failed`、`startup_error=HostError`（8 次重试） |
| F2 | runtime 起宿主用 `cwd=project_root` + `-m scripts.*`，不注入 PYTHONPATH | `scripts/talk_runtime.py:322-327` | 宿主 `host-*.err`：`ModuleNotFoundError: No module named 'scripts'`；3 次后 `manager_failed` |
| F3 | 宿主 `_local_facts` 只读 `<project_root>/.talk/runtime.local.json`，要求 `project_id`/`project_root` 精确匹配 | `scripts/kimi_role_setup.py:53-72`（dsh host 入口 `scripts/dsh_role_host.py:229`） | 手工补 PYTHONPATH 后仍 `dsh_host_config_invalid`；补齐 B 根指针后才继续 |
| F4 | 角色子进程环境是白名单，不含 PYTHONPATH；桥用 `-m bridges.*`、cwd 为角色工作目录 | `scripts/role_service_host.py`（`child_environment` / `CHILD_ENV_ALLOWLIST`） | dsh 桥 `bridges.dsh_bridge` 起不来 → 角色 start **`bridge_process_exited`**；角色 `logs/<launch>.err` 同样是 `No module named 'bridges'` |
| F5 | 角色删除的 cleanup 凭据要求同一本机绑定 + 项目根精确匹配 | `server/role_deletions.py:52-70`、`scripts/talk_runtime.py:799-805` | 项目 B 角色删除回执 **`failed` / `local_runtime_required`**（manager=failed，其余 pending），临时项目 B 无法按产品流程删除 |

F1/F5 是同一个“单项目绑定”在启动与删除两端的表现；F2/F3/F4 是“进程必须从 TALK 仓库根运行”的三种表现。

## 复现（本次实际执行）

1. `POST /api/projects` 建临时项目 B（root `D:\claude-test\TALK\.tmp\w3c-dual-20261109\workspace`，`prj_7e3fcc639c70`）→ 成功，`workspaces/<pB>/` 与 `workspace.json` 由 worker 正常生成。
2. 复制 runtime A 清单为 B（`project_id=p2`、独立 `state_dir`/`key_root`、`hosts=[]`、`--attach-api`）→ `load_config` 通过；runtime B 起（外部 API 模式）。
3. 项目 A/B 各建一个 dsh `workspace-v1` 角色（role-requests → worker provisioned）→ 均成功；A 角色 start 到 running/ready（`ins_c243b0b0a775`）。
4. B 角色 start：宿主 `ModuleNotFoundError: scripts` → `manager_failed`；补 `PYTHONPATH` 后 `dsh_host_config_invalid`；补 B 根 `.talk/runtime.local.json` 后桥 `ModuleNotFoundError: bridges` → `bridge_process_exited`。
5. 清理：A 临时角色 stop → delete 5 步 complete；B 临时角色 stop 后删除返回 `local_runtime_required`，项目 B 保留为复现现场。

## 证据

- `.tmp/w3c-dual-20261109/evidence.json`：项目/角色/服务投影、runtime B health/capability、workspace.json、宿主与角色日志尾部。
- `.tmp/w3c-dual-20261109/state-b/runtime/host-agent_prj-7e3fcc639c70.w3c-dual-b-d8fa33d3.err|out`
- `workspaces/p-obzguxzxmuzwmy3dgyztsyzxga/roles/<m>/logs/2208439e-...err`
- 启动/删除脚本与轮询记录：`.tmp/w3c-dual-20261109/*.py`、`state.json`。

## 影响

- W3c-1（双工作区 A 停 B 不停）在当前代码上不可验收；W3c-2 的“非仓库根项目恢复链”同样不可用（startup 先失败）。
- 单项目（TALK 自身）的 workspace-v1 角色启停、删除、隔离逻辑此前已验收，不受本发现影响。
- 临时项目 B 与已归档角色、失败删除行仍留在库中（UI 会多一个“W3c 双工作区验收 B”项目），需要修复后用产品流程删除，或经用户授权做带备份的库清理。

## 修复方向（待项目管理者选择）

- **A. 完整多项目运行底座（对齐 P3）**：本机绑定按项目注册，`configured_runtime(project_id)` 解析；任意项目根可写绑定；宿主/桥进程与 cwd 解耦；DB/端口分片与资源预算一并做。范围最大。
- **B. 最小“外部项目根可运行”**：①绑定从单文件改为按项目解析（读项目根下的 `.talk/runtime.local.json`，`attach-api` 也写）；②宿主/桥用绝对模块路径或不依赖 cwd 的引导，子进程环境补受控 `PYTHONPATH`；③`_local_facts` 接受 runtime 显式传入的清单路径（保留指针回退）；④删除 cleanup 用同一按项目解析。约 5 个文件 + 回归测试，完成后再重跑 W3c-1。
- **C. 收缩范围**：承认“一实例一项目”的现行模型，把双工作区整体移到 P3；W3c-1 改判为“单项目多角色隔离”已覆盖 + 文档标注限制。

建议 B：它能让 W3c-1 具备可验收前提，又不把 P3 的分片/预算一起拉进来。
