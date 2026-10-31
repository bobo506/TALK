# 351-C 官方能力清单落库（与 Kimi 执行侧核实结论）

日期：2026-10-31。接续 351-A/B，本片只做**能力清单持久化**；执行侧另见 §4。
生产状态：**未加载**；候选 `.tmp/role-effort-detail-20261031/task-351C/`，基线是 351-B 冻结候选。

## 1. 目的

351-A 起，页面可选项优先取绑定里的 `supported_efforts`（来源 `catalog`）。但准备流程虽然读到了
官方支持清单，只落库了默认值（`default_effort`），清单被丢弃，于是所有角色都退回运行器适配事实
（`adapter`）或禁用。本片把清单按同一份官方来源落库。

## 2. 改动

| 位置 | 改动 |
|---|---|
| `scripts/codex_role_setup.py` | `_model_effort` 把 `model/list` 的 `supportedReasoningEfforts` 规范成适配器顺序后挂到 `attempt.supported_efforts`（官方没给就不设置） |
| `scripts/kimi_role_setup.py` | 新增纯函数 `canonical_support_efforts`（只在已知字面量内、固定顺序）；`finish_native_login` 读模型条目的 `support_efforts` 挂到 attempt；原有 `default_effort` 行为不变 |
| `server/kimi_native_setup.py` | `_record_default_effort(..., supported=None)` 同时写 `default_effort` 与 `supported_efforts`；清单用 `serialize_supported_efforts` 规范化，缺失写 NULL 且**清理旧清单**；绑定行不存在时静默跳过 |
| `tests/test_effort_capability_recording.py` | 新增：默认+清单一起落库、未知档丢弃、缺失不猜并清旧值、缺绑定行跳过、Kimi 解析纯函数 |
| `tests/test_codex_role_setup.py` | 既有分页用例补断言清单顺序；新增未知档丢弃用例 |

不变的语义：

- 两个新列仍不参与六维指纹、绑定有效性与启停；
- `default_effort` 仍是“模型默认”，用户覆盖值 `effort_override` 不被本片触碰；
- 没有官方清单时保持 NULL，不拿通用枚举冒充 catalog。

## 3. 验收（本片实测）

- `python -B -X utf8 -m unittest tests.test_effort_capability_recording tests.test_codex_role_setup tests.test_kimi_role_setup -q` → **Ran 44, OK**
- `python -B -X utf8 -m unittest tests.test_effort_capability_recording tests.test_codex_role_setup tests.test_kimi_role_setup tests.test_codex_effort tests.test_talk_runtime tests.test_project_role_bindings -q` → **Ran 131, OK**
- `python -B -X utf8 -m unittest tests.test_kimi_native_setup -q` → **Ran 8, OK**

未验证：未对既有角色重新执行准备流程（真实登录），因此**存量角色仍无 catalog 清单**；补齐需要
按角色重新准备或单独的能力补齐操作（会触碰角色原生目录，需单独授权窗口）。

## 4. Kimi 执行侧核实结论（351-D 的前置）

- 本机 `kimi --help` 只有 `-m/--model`，**没有按次传入思考强度的参数**；
- Kimi 的强度来自模型配置（`config.toml` 里 `models.<alias>.default_effort`）与模型条目能力；
- 因此“像 Codex 那样在命令里加 `-c model_reasoning_effort=`”对 Kimi 不成立。

由此 351-D 只有两种诚实选择：

1. **受管改写角色配置**：每次执行前把生效强度原子写入该角色自己的 `config.toml`
   的 `models.<alias>.default_effort`（只改一个键、保留其它字段、与准备流程共用锁），
   执行后不自动回滚（配置即状态）；风险是与准备流程并发、以及“改了原生配置”的副作用；
2. **保持禁用**：Kimi 控件继续显示“能力未知/不可设”，直到官方 CLI 支持按次参数。

本片不擅自选 1（属于新的写原生配置机制，需要用户明确授权），先如实记录供决策。

## 5. 回退

恢复本片 4 个文件到 351-B 候选即可；数据库两列不变（本片只多写 `supported_efforts` 的值，
可清空回 NULL）。
