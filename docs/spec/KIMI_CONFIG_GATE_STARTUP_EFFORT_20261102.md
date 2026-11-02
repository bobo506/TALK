# Kimi 角色：配置启动门槛结构化 + 启动时强度对齐

日期：2026-11-02。范围：Kimi Code 三个角色（`agent:kimi`、`agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c`、
`agent:prj-e8fe7066bbec.k-d4bf0429`）的启动校验与强度对齐。不启停生产、不派任务。

## 1. 背景

2026-11-01 小d（DeepSeek）事故：宿主按「整份 patch 与确认基线逐字节相等」做启动门槛，而产品按任务
把强度写进同一文件，改一次强度角色就起不来（`deepseek_native_patch_changed`）。Kimi 的强度写在
角色 `config.toml` 的 `models.<alias>.default_effort`，与宿主读取的是同一份文件，因此需要确认：
**改强度永远不能成为启动失败原因**。

同时发现两处真实缺口：

- 小K、Kimi k2.8 跑的是 `.tmp` 下的遗留入口，启动时**完全不读** `config.toml`：模型段被改或丢失时
  照常启动，直到任务时才由桥接报 `kimi_model_config_missing` / `kimi_model_binding_mismatch`；
  产品宿主（`scripts/kimi_role_host.py`）则会启动即校验并提示 `kimi_role_setup_required`。
- 强度只在「任务开始前」写入（`cli_bridge.run_before_task`），消息与首个任务之前仍用 `config.toml`
  里的旧值。实测 `k-d4bf0429`：页面 override 是 `high`，配置里是 `low`（配置 11-01 18:59 写、绑定
  23:09 改为 high），要等下一个任务才对齐。

## 2. 改动

| 位置 | 改动 |
|---|---|
| `bridges/kimi_native_config.py`（新） | `read_config_text`（2 MB 上限）+ `config_problem`：用 `tomllib` 解析，只校验 `models.<alias>` 的 `provider`/`model`（兼容键 `name`）与绑定一致、`provider` 在 `providers` 中声明；`default_effort`、注释、空白、顺序**不参与**；结构不可读时 fail-closed 返回可读原因，不抛异常 |
| `scripts/kimi_role_host.py` | `build_entry_argv` 与 `preflight` 改用共享校验（`_config_problem`）；错误码与提示保持 `kimi_role_setup_required`，原因附在括号内；移除本地 `tomllib` |
| 遗留入口（本机 `.tmp`，gitignored） | `kimi_member_entry.py`、`next_member_entry.py` 新增 `_native_config_problem`：从 `/agents` 公开绑定取 `model_id`/`provider_id`，与角色 `config.toml` 结构化核对；不一致抛 `kimi_role_setup_required`（启动即失败，不再拖到任务期） |
| `bridges/cli_bridge.py` | 新增 `run_startup_hook(args, client)`：服务进入接单循环前调用一次可选的 `startup_factory`；失败只打一行 `[cli_bridge] startup_hook_failed: <类型>`，**不阻断启动** |
| `bridges/kimi_bridge.py` | 新增 `align_effort_at_startup` 并注册为 `startup_factory`：与逐任务钩子共用同一判定（用户覆盖 > 模型默认，且必须在公开清单内），启动时把生效强度写进本机 `config.toml` |

## 3. 不变项

- 启动门槛只认「与绑定一致的模型事实」：`provider` / `model` / provider 声明；强度值、注释、行尾、
  字段顺序都不参与，因此改强度永远不会挡启动。
- 强度写入权限与判定口径不变（仍走 `resolve_target_effort` + 公开清单）；启动对齐只是把同一动作
  提前执行一次。
- 其它运行器（DeepSeek / Codex / WorkBuddy）路径未改；`startup_factory` 未注册时行为完全不变。
- 不读取凭据正文：`providers` 只判断键是否存在，不输出值。

## 4. 验收（本机实测）

- `tests/test_kimi_native_config.py`（新，8 项）+ `tests/test_kimi_effort.py`（新增启动对齐/接线 7 项）
  与既有 Kimi 套件合并 **173 项 OK**（`test_kimi_native_config`、`test_kimi_effort`、`test_kimi_bridge`、
  `test_kimi_new_role_host`、`test_kimi_role_setup`、`test_kimi_execution_session`、`test_kimi_k28_executor`）。
- `tests.test_cli_bridge` **122 项 OK**；`tests.test_role_host_runtime_configuration` **40 项 OK**。
- 真实配置只读核验：三份角色 `config.toml` 均通过（纯校验、产品宿主 `_config_problem`、两个遗留入口
  `_native_config_problem` 四条路径都返回 `None`）；把 `default_effort` 改成 `low` 仍通过；改
  `provider`/`model` 被拒。
- `tests.test_kimi_talk_entry` 有 2 项既有失败（`tool_count` 10 ≠ 9），已用 `git stash` 在**不含本片改动**
  的基线上复现，不属本片回归。
- 环境说明：PID 相关的真实进程测试需用系统 Python 运行；`.venv\Scripts\python.exe` 是启动器，
  Popen PID 与子进程 PID 不同，会产生假失败（本片已按系统 Python 复跑）。
- **实机整链（2026-11-02 19:50，k2.8，用户授权）**：页面 override 改 `low` → 启动
  （gen 29 / `ins_026db48e7926`，launch `ready`，约 2.0s）→ **未跑任何任务**，`config.toml`
  该模型段已被启动对齐写成 `low`；普通消息 3130 收到回复 3131 `K28_STARTUP_OK`（消息路径不走
  任务钩子，证明对齐发生在启动期）→ override 改回 `high` → stop/start（gen 31 /
  `ins_bad3acdf7044`）→ 配置回到 `high` → stop（gen 32）。最终服务 `stopped`、override `high`、
  配置 `high`；launch 29/31 `ready`、30/32 `stopped`，无错误码；无 `startup_hook_failed` /
  `kimi_effort_*_failed` 诊断，无遗留 kimi 进程。

## 5. 生效条件与边界

- 宿主侧校验（产品宿主 + 两个遗留入口）在宿主进程启动时加载，**需重启对应宿主**才生效。
  本机已于 2026-11-02 19:43 重启三个宿主：`agent:kimi` 9648→12448、`Kimi k2.8` 14952→7732、
  `k-d4bf0429` 19392→3232，runtime 与健康文件均 `serving`；三个角色服务保持 `stopped`、
  无在管进程，未启停任何服务。
- 启动时强度对齐由桥接进程执行，**下一次角色启动**即生效，无需重启宿主。
- 遗留入口位于 `.tmp/`（gitignored），改动只在本机运行目录；判定逻辑已版本化到
  `bridges/kimi_native_config.py`。
- 本片作者自测；用户 2026-11-02 19:58 验收通过并推送（`acab0a0`），未另做独立复核；未启停角色服务（仅重启宿主加载新代码）。
