# 351-E/F DSH 与 WorkBuddy 的思考强度（官方来源与受管写入）

日期：2026-10-31。用户决议：DSH 下拉只开放 `max`；WorkBuddy 按官方模型清单。
（2026-11-01 用户确认 DSH 四档 `off/low/high/max` 全部开放，代码 `OPEN_EFFORTS` 已同步，见 §2、§5。）

## 1. 官方来源（本次核实结果）

| 运行器 | 权威来源 | 本机值 |
|---|---|---|
| DSH | 角色私有 patch `model-*.patch.yml` 的 `reasoningEffort`；**无枚举**（`ReasoningEffortId` 是 adapter 自定义字符串） | `max`；用户界面观察到 `off/low/high/max` |
| WorkBuddy | 用户级 `<models_home>/models.json` 每个模型的 `reasoning.defaultEffort` 与 `reasoning.supportedEfforts`（应用官方模型配置）；CLI 支持 `--effort` | `deepseek-flash`：默认 max、可选 high/max；`k3.1-pro`：默认 max、可选 low/high/max |

WorkBuddy 的 `--effort` 是从其 CLI bundle 与 `models.json` 契约核实到的，不改用户全局配置。

## 2. 实现

| 位置 | 改动 |
|---|---|
| `bridges/dsh_effort.py`（新） | `OBSERVED_EFFORTS=(off,low,high,max)`、`OPEN_EFFORTS=(off,low,high,max)`（2026-11-01 用户确认四档全开）；`set_patch_effort` 只替换已存在的 `reasoningEffort` 行（缺行拒绝，不新建键）；`apply_patch_effort` 临时文件 + `os.replace` |
| `bridges/dsh_bridge.py`（新） | DSH 入口包装层（与 Kimi/Codex 同构）：注册逐任务钩子 → 读公开绑定 → 只写已开放档位 → 交给通用桥接；参数契约与通用入口完全一致 |
| `scripts/role_service_host.py` | `RUNTIME_RECIPES["dsh"]` 入口改为 `bridges.dsh_bridge`（命令模板/超时契约不变） |
| `server/models.py` | `RUNNER_ADAPTER_EFFORT_VALUES["dsh"] = {"off","low","high","max"}`（2026-11-01 四档全开，页面来源标 adapter，不做成假 catalog） |
| `bridges/workbuddy_bridge.py` | 命令加 `--effort`（启动时取官方默认）；逐任务钩子按公开绑定改写 `--effort`（没有该参数时插到 `--model` 之后）；能力读取 `read_model_reasoning`（只读公开字段） |

## 3. 验收（本片实测）

- `python -B -X utf8 -m unittest tests.test_dsh_workbuddy_effort` → **12 OK**
- 桥接与强度回归：`cli_bridge + kimi_bridge + codex_bridge + dsh/workbuddy + kimi_effort + codex_effort + 能力落库` → **214 OK**
- `test_role_host_runtime_configuration` 与 DSH 入口无关的断言更新为 `bridges.dsh_bridge@`；
  该套件在本机候选内因“测试根必须在工作区外”的环境守卫整体失败，**基线同样失败**，非本片回归。

已验证（2026-10-31 晚，加载后实测）：DSH patch 由 off 改为 low、Kimi config.toml 由 high 改为 low、WorkBuddy 前置 --effort max 而正式任务 --effort high。生产已于 2026-10-31 23:05 加载。

## 4. 遗留

- 两个运行器的存量角色能力补齐已完成（WorkBuddy 读 models.json；DSH 由适配事实提供四档）。
- 真实执行证据与页面验收在加载后由用户操作验证。

## 5. 2026-11-02 启动门槛修复：小d（agent:deepseek）

**事故**：小d 每次启动都被 `deepseek_native_patch_changed` 挡下。遗留宿主
`.tmp/legacy-role-page-control/deepseek-next/deepseek_member_entry.py` 用「整份 patch 与确认
基线逐字节相等」做启动前检查，基线含 `reasoningEffort: max`；2026-11-01 18:48 任务 375
（强度实测）领取时，逐任务钩子按当时生效强度把同一行改成 `low`，此后每次启动都在预检阶段
失败（`spawned=0`，未创建进程/实例）。页面把强度改回 max 只写绑定 `effort_override`，不会
回写 patch，所以重试仍失败。

**修复**：新增 `bridges/dsh_patch.py` 做结构化校验，遗留入口改为调用它：

- `agent-default-model.config.provider` / `.model` 必须等于确认值（`deepseek-official` /
  `deepseek-flash`），缺段、重复段、标量 `config` 与不可识别结构一律 fail-closed；
- `llm-deepseek.config.reasoningEffort` 只要求存在且属于 `off/low/high/max`，具体值由绑定
  逐任务写入；注释、行尾、引号、行内注释与字段顺序变化不再阻断启动；
- 解析器零新依赖，只认 `- id: ...` 列表项 + 两级 `key: value` 的既有形态；
- 错误码保留 `deepseek_native_patch_changed`（语义仍是「模型覆盖文件不符合确认事实」）。

**验证**：`tests/test_dsh_patch_preflight.py` 11 项（确认基线、四档强度、书写差异、provider/
model 漂移、缺/重复段、结构反例）；与既有 `tests.test_dsh_workbuddy_effort` 合并 23 项 OK；
用宿主同款系统 Python 对遗留入口 `py_compile` + 真实导入，当前 patch 返回 `None`，模拟
`low` 放行、模拟 `model: deepseek-pro` 拒绝。

**加载与生效**：校验在宿主进程启动时加载。用户确认后已重启小d宿主：旧 15656 终止，
runtime 于 2026-11-02 00:38:01 拉起 18084 并 `serving`，新门槛已生效；其余六个宿主未动
（runtime 状态均为 serving），小d patch 保持 `max`。
