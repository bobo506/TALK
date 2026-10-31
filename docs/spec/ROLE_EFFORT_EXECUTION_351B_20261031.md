# 351-B 思考强度的执行贯通（Codex 动态宿主 + 旧小G入口）

日期：2026-10-31。接续 [351-A 设置与展示](ROLE_EFFORT_SETTING_351A_20261031.md)，本片只做**执行侧**。
生产状态：**未加载**；候选在 `.tmp/role-effort-detail-20261031/task-351B/`，基线是 351-A 冻结候选。

## 1. 目的

用户在角色详情页改的思考强度必须真正进入执行参数，覆盖两个既有 Codex 入口：

- **G-terra 等动态角色**：`scripts/codex_role_host.py` 启动的受管宿主；
- **旧小G（agent:codex）**：`codex-next` 旧入口（`codex_member_entry.py` + `native_driver.py`）。

不改模型、身份、权限、工具档位；运行器不接受时明确失败，不静默降级。

## 2. 取值规则（唯一口径）

`bridges/codex_effort.py::resolve_binding_effort(binding, fallback)`：

1. 公开绑定有 `effective_effort`（351-A 起下发）→ 用它；
2. `effort_options` 非空时必须在其中，否则 `codex_effort_unsupported`；
3. 有用户覆盖但能力来源未知 → `codex_effort_capability_unknown`（不把“无法校验”当“可以执行”）；
4. 旧服务/旧快照没有这些字段 → 用 `fallback`（native `config.toml` 的值），
   与 351-A 之前的真实行为一致。

## 3. 生效路径与时机

| 入口 | 解析时机 | 写入方式 | 生效范围 |
|---|---|---|---|
| 动态宿主（G-terra 等） | ①宿主启动时 ②**每个任务执行前**（bridge 重取） | `codex exec ... -c model_reasoning_effort="<档位>"` | 下一次执行；无需重启角色服务 |
| 旧小G（codex-next） | ①入口启动时 ②**每个任务执行前**（同一 bridge 重取） | `native_driver.py ... --effort <档位>` → `-c model_reasoning_effort="<档位>"` | 下一次执行 |

bridge 侧在 `bridges/codex_bridge.py::handle_queued_task` 的 `command_runner` 中，按任务读取
`GET /api/projects/{id}/roles` 的公开 `binding`，用 `apply_effort` 把档位写回命令：

- 认识 `-c model_reasoning_effort=...` 与 `--effort ...` 两种形态；
- 不认识的命令形态原样执行，并输出一行 `codex_effort_command_unrecognized` 诊断，不臆测参数位置；
- 读取失败/能力未知只输出 `codex_effort_lookup_failed` / `codex_effort_capability_unknown`，
  继续用启动时烘焙的值（可用性优先），不编造档位；
- 命令字符串用与 `cli_bridge.parse_command` 相同的 `shlex` 规则解析/重组，保持 Windows 路径与既有引号。

## 4. 会话轮换（不新增机制）

执行会话的可复用性由命令/配置指纹决定（`config_permission_fingerprint` = 适配器 argv 指纹）。
强度写回命令后命令文本变化 → 指纹变化 → 既有 `tainted` 规则生成 `new_session_tainted` 新窗，
**不会**把旧强度会话续用到新强度上。本片不新增会话清理、锁或归属操作，也不删除旧会话记录。

## 5. 旧小G入口（候选副本，不改生产入口）

`.tmp/legacy-role-page-control/codex-next/` 的入口属于生产运行材料，本片**只复制为候选**：

- `legacy/codex-next/native_driver.py`：新增 `--effort`（缺省 `xhigh`，保持历史行为），
  校验后写入 `model_reasoning_effort`；
- `legacy/codex-next/codex_member_entry.py`：入口启动时按公开绑定解析强度并传给驱动的
  任务/预检命令；`{model}` 模板占位保留（宿主模板规则不变）；
- `legacy/codex-next/native_login.py`：**未修改**，仅作候选目录完整性依赖。

加载时需把这三个文件按候选 hash 覆盖到旧入口目录，并重启旧入口一次；重启后强度仍会**逐任务**
重取，不需要每次改强度都重启。

## 6. 改动文件

| 文件 | 说明 |
|---|---|
| `bridges/codex_effort.py` | 新增：纯函数解析与命令改写，无 I/O |
| `bridges/codex_bridge.py` | 每任务读取公开绑定并写回命令；失败/未知留诊断 |
| `scripts/codex_role_host.py` | `_configuration` 返回 `(config, effort)`，argv 用解析值；不支持明确报错 |
| `tests/test_codex_effort.py` | 新增 19 项：解析/改写/每任务读取/诊断 |
| `tests/test_codex_new_role_host.py` | 新增 4 项：宿主解析与 argv；原断言改为 `(config, effort)` |
| `tests/test_codex_role_setup.py` | 两处 `_configuration` 打桩适配新返回形状 |
| `docs/spec/ROLE_EFFORT_EXECUTION_351B_20261031.md` | 本文件 |
| `docs/guides/USER_MANUAL.md` | 说明改动作用于下一次执行、旧入口加载后同样生效 |
| `legacy/codex-next/{native_driver,codex_member_entry,native_login}.py` | 候选副本（仓库外，见 manifest 单独清单） |

## 7. 验收（本片实测）

- `python -B -X utf8 -m unittest tests.test_codex_effort -q` → **19 passed**
- `python -B -X utf8 -m unittest tests.test_talk_runtime tests.test_project_role_bindings tests.test_runtime_diagnostics_sources tests.test_project_role_startup tests.test_codex_effort -q` → **Ran 139, OK**
- `python -B -X utf8 -m unittest tests.test_codex_new_role_host tests.test_codex_role_setup tests.test_codex_execution_session tests.test_terra_role_flow -q` → **Ran 58**，3 项失败与 351-A 基线**完全一致**（`verify_runtime_entry` 解释器路径、健康 PID 两项环境性既有失败），新增 4 项通过
- 旧入口候选自测（`evidence/test_legacy_effort.py`）→ **7/7 PASS**

未验证（如实记录）：

- 未用真实 Codex CLI 执行一次任务验证 `-c model_reasoning_effort` 的最终生效（需真实模型调用与授权）；
- 未做生产加载、未重启任何服务、未改动旧入口生产文件；
- 会话轮换依赖既有指纹规则，本片只证明“命令文本随强度变化”，未在真实会话上复现换窗。

## 8. 回退

同 351-A：恢复本片 7 个产品/测试/文档文件到 351-A 候选即可；旧入口候选副本若未加载则无影响，
已加载时恢复原三个文件并重启旧入口一次。新增模块 `bridges/codex_effort.py` 可直接移除
（无持久数据、无数据库列变更）。
