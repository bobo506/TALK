# 351-E/F DSH 与 WorkBuddy 的思考强度（官方来源与受管写入）

日期：2026-10-31。用户决议：DSH 下拉只开放 `max`；WorkBuddy 按官方模型清单。

## 1. 官方来源（本次核实结果）

| 运行器 | 权威来源 | 本机值 |
|---|---|---|
| DSH | 角色私有 patch `model-*.patch.yml` 的 `reasoningEffort`；**无枚举**（`ReasoningEffortId` 是 adapter 自定义字符串） | `max`；用户界面观察到 `off/low/high/max` |
| WorkBuddy | 用户级 `<models_home>/models.json` 每个模型的 `reasoning.defaultEffort` 与 `reasoning.supportedEfforts`（应用官方模型配置）；CLI 支持 `--effort` | `deepseek-flash`：默认 max、可选 high/max；`k3.1-pro`：默认 max、可选 low/high/max |

WorkBuddy 的 `--effort` 是从其 CLI bundle 与 `models.json` 契约核实到的，不改用户全局配置。

## 2. 实现

| 位置 | 改动 |
|---|---|
| `bridges/dsh_effort.py`（新） | `OBSERVED_EFFORTS=(off,low,high,max)`、`OPEN_EFFORTS=(max,)`；`set_patch_effort` 只替换已存在的 `reasoningEffort` 行（缺行拒绝，不新建键）；`apply_patch_effort` 临时文件 + `os.replace` |
| `bridges/dsh_bridge.py`（新） | DSH 入口包装层（与 Kimi/Codex 同构）：注册逐任务钩子 → 读公开绑定 → 只写已开放档位 → 交给通用桥接；参数契约与通用入口完全一致 |
| `scripts/role_service_host.py` | `RUNTIME_RECIPES["dsh"]` 入口改为 `bridges.dsh_bridge`（命令模板/超时契约不变） |
| `server/models.py` | `RUNNER_ADAPTER_EFFORT_VALUES["dsh"] = {"max"}`：页面只列 max，来源标 adapter（不做成假 catalog） |
| `bridges/workbuddy_bridge.py` | 命令加 `--effort`（启动时取官方默认）；逐任务钩子按公开绑定改写 `--effort`（没有该参数时插到 `--model` 之后）；能力读取 `read_model_reasoning`（只读公开字段） |

## 3. 验收（本片实测）

- `python -B -X utf8 -m unittest tests.test_dsh_workbuddy_effort` → **12 OK**
- 桥接与强度回归：`cli_bridge + kimi_bridge + codex_bridge + dsh/workbuddy + kimi_effort + codex_effort + 能力落库` → **214 OK**
- `test_role_host_runtime_configuration` 与 DSH 入口无关的断言更新为 `bridges.dsh_bridge@`；
  该套件在本机候选内因“测试根必须在工作区外”的环境守卫整体失败，**基线同样失败**，非本片回归。

未验证：未用真实 DSH/WorkBuddy 任务核对 CLI 是否按新值执行；未加载生产。

## 4. 遗留

- 两个运行器的存量角色还要做一次能力补齐（WorkBuddy 读 models.json；DSH 落 max）。
- 真实执行证据与页面验收在加载后由用户操作验证。
