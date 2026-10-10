# 通用角色运行器与模型绑定合同

> 状态：**设计已发布，B1a/B1b后端已实现并通过独立复核；B2尚未实现**（2026-10-09）。B1a 由 DeepSeek #193/#194 开发修正，Codex 独立 124 项相关测试与边界探针通过，两项已收取；[API 人工验收](../guides/ROLE_MODEL_BINDING_ACCEPTANCE.md)待用户执行，生产加载未验。
> B1b #196已由Codex独立177项及WAL双线程100提交/400快照、真实关系冲突/子授权回滚、SQLite JSON原文生命周期不变探针通过并收取，待[快照API人工验收](../guides/TASK_BINDING_SNAPSHOT_ACCEPTANCE.md)。未重载生产服务/执行生产迁移，未重跑881/pristine；原报告保持，证据本机.tmp/runner-role-binding-b1b-review/。
> 配套：[实施计划](ROLE_MODEL_BINDING_IMPLEMENTATION_PLAN.md)、[合成样例](ROLE_MODEL_BINDING_EXAMPLES.json)。先 B1a 登记/绑定，再 B1b 任务快照；下列原设计复核基线与证据保留为历史，B1a 实现范围见实施计划和验收指南。
> 实际源码基线 `10555ca2a54fdafa56300b999921d7831bb41518`；复核时 `HEAD=3436bbfca674150c9e2b82f6991e9234c31cbfa3`，其间仅协调方进度变化。
> Codex 直接执行原文 SQL：14 种状态均恰好 1 行/1 SQL、27 个唯一列别名；无项目 0 SQL、项目不存在仍保留请求事实；11 个样例快照固定 13 键，指纹核算通过。790 个冻结文件中仅两份进度有合法变化，原 #190 七稿、#191 十三稿保持。
> 发布补充澄清：按调用 API 保持项目不存在的错误码（项目接口 404、任务创建 400）；单条 SQL 读取同一数据库视图，已有事务沿用自身视图，不承诺读取时刻总为最新提交。隔离两连接 WAL 反例已独立核实。原草稿和报告不追改，本正式合同为实施依据。
> 本地复核索引：`.tmp/role-model-binding-design-final-fix-review/`（原稿快照、独立探针及结果）；这些本地证据不是生产或发行依赖。

## 1. 目标与非目标

### 1.1 目标

1. 让 TALK 能把「**全局运行器登记**」与「**项目角色绑定**」分开管理：登记回答“这台机器上已登记/已适配了哪些运行器及其接入状态”，绑定回答“本项目这个角色用哪个运行器、哪个模型来源、哪条连接、哪个模型”。
2. 让**新任务**在创建时冻结当时目标角色的运行器/模型绑定快照；历史任务与快照不追改。
3. 让「**配置值**」与「**实际运行可核实模型**」严格分开表达；无法核实一律如实为 `unknown`，不伪造。
4. 身份（`member_id`）、业务职责（`business_role`）、决策分级（`decision_tier`）、运行器、模型、来源、连接**七者分别处理**；模型名/来源不赋予任何权限。
5. **保留存储 ≠ 当前有效**：绑定行可因角色离册、成员未注册/被禁用/非 agent、运行器缺失或停用而“存着但不有效”，读取与快照必须如实报告有效性，不得默认 `bound`。

### 1.2 非目标（本合同明确不覆盖）

- 不设计完整进程/页面系统：**不**定义启动/停止、自动启动、桌面生命周期、原生会话恢复/续接、多工作区切换。
- 不读取、不搬运、不校验任何凭据正文；不解析原生配置里的密钥。
- 不把 `connection_ref` 变成可执行命令、文件路径、URL 或“连接可用性探测”。
- 不新增固定主控、租约、会话自动唤醒或任何权限提升路径。
- 不注册新角色、不改既有角色/名册/Key/原生默认模型/终端配置。
- 不承诺任何运行器能按任务切换模型——见 §9 的真实能力边界。
- **本片不定义实际运行证据的字段**：`reported_*`/`binding_match` 的字段与算法整体后置到 B2 另片（§8），本片禁止任何当前字段直接输出“实际匹配”。
- **不新增任务表持久字段用于“读取回执”**（R3 范围裁决）：读取方案、语句计数与版本哈希只作为**隔离验证证据**存在，不进快照、不进 `agent_tasks`、不进任何 API。

## 2. 三层身份：绑定行身份 / 配置内容指纹 / 历史任务快照

绑定体系里必须区分三个**互不替代**的概念，混用会产生错误合并与错误“版本”推断：

| 层 | 定义 | 稳定性 | 用途 | 不能当成 |
|---|---|---|---|---|
| **绑定行身份** | 主键 `(project_id, member_id)` | 稳定；行存在即身份存在 | 唯一定位“本项目这个角色”的绑定行 | 不能用模型名/指纹代替 |
| **配置内容指纹** `binding_fingerprint` | `sha256("runner_id\|runtime\|model_source\|provider_id\|connection_ref\|model_id")`；**仅当六个值在读取/写入时全部可解析**才给出，否则 `null` | 随内容变化；**纯内容寻址** | 审计、检测“同一角色配置变更”、跨行比较配置差异 | **不是行的自然身份键**：不同角色可以有相同指纹，**禁止按指纹合并/去重绑定行**；同一角色先后版本指纹不同，**不代表两条并存的角色行** |
| **历史任务快照** `target_binding_snapshot` | 任务创建时冻结的配置副本，含指纹与 alias | 写入后不可变 | 回答“派发当时配置是什么” | 不能被后续绑定变更或实例上报覆盖 |

**并存行 vs 先后版本**必须写清：

- 两个**不同角色**（不同 `member_id`）可以同时各有一行并可同时存在；它们的内容指纹可能相同（例如两个角色都用同一运行器/来源/连接/模型）——**仍是两行**，`GET` 返回两条，绝不合并。
- **同一角色**只有一行；对该行做第二次 `PUT` 是**先后版本**（内容指纹变化），不是新增并存行。旧任务的快照保留第一版，新任务取第二版（§7.4）。
- **指纹覆盖范围（R2 澄清）**：只含上表六个值，**不含** `model_alias` / `model_display_name` / `updated_by` / `updated_at`。
  - 但 **alias 不是展示层字段**：原生运行器把 `model_alias` 作为**调用选择参数**传给运行器（`bridges/kimi_bridge.py:95` 把 model alias 传 `--model`），因此它是**调用配置**的一部分；`model_display_name` 才是纯展示字段。
  - 因此必须显式承认：**六维内容指纹不代表完整调用配置**。`fingerprint` 相同**只说明这六个值相同**，**不等于** alias 未变、也不等于两次调用的原生参数相同。要判断“调用配置是否变化”必须同时比较快照里的 `model_alias`（以及后续 B2 的实际证据）。
  - alias 本身**永远不是** `model_id`，也不是“实际 `model_id`”。
  - 同一角色只换 alias 时：指纹不变，但那是**调用选择变更**，不是“展示层调整”，必须保留在快照里逐版本可读（§7.4 与 `ROLE_MODEL_BINDING_EXAMPLES.json` 的 alias 变更样例）。
- **派生的 `runtime`**：`runtime` 不在绑定行内存储，由 `runner_registry` 按 `runner_id` 派生（登记后不可改）。因此指纹要求“六个值可解析”：`runner_missing`（登记事实不可解析）时 `runtime` 不可解析 → 指纹为 `null`；`runner_retired`（登记行仍在且 `runtime` 可解析）→ 指纹正常给出。

## 3. 全局运行器登记

### 3.1 表 `runner_registry`

| 字段 | 类型 | 空值 | 语义与校验 |
|---|---|---|---|
| `runner_id` | TEXT PK | 非空 | 稳定 slug，人工指定；`^[a-z0-9][a-z0-9._:\-]{0,63}$`；例如 `runner:kimi-code-cli` |
| `runtime` | TEXT | 非空 | 运行器族标识；`^[a-z0-9][a-z0-9._\-]{0,31}$`；例如 `codex` / `kimi-code` / `dsh`。**登记后不可改**（本片） |
| `display_name` | TEXT | 非空 | 面向人展示名，≤ 64 码点；**仅展示**，不参与身份/权限，也不是调用参数 |
| `adapter_status` | TEXT | 非空，默认 `unverified` | 枚举见 §3.2 |
| `adapter_note` | TEXT | 可空 | ≤ 500 码点；自由说明，**不得写凭据正文**（§5） |
| `capabilities` | JSON | 非空，默认 `[]` | 字符串数组；定量规则见 §3.3 |
| `created_by` | TEXT | 非空 | 登记人 `member_id`（不加强外键，沿用 `project_agents.member_id` 先例） |
| `created_at` / `updated_at` | DATETIME | 非空 | UTC |

### 3.2 `adapter_status` 枚举（如实表达接入程度，不夸大）

| 值 | 含义 | 不能当成 |
|---|---|---|
| `adapted` | 已有真实接入/执行证据 | 不代表当前在线或可自动启动 |
| `discoverable` | 工具/入口可发现，未完成完整能力与等待预算验收 | 不代表可派单执行 |
| `unverified` | 仅登记，未验证（**默认**） | 不代表可用 |
| `retired` | 停用，不再用于新绑定 | 不删除历史绑定与历史快照 |

**登记 ≠ 加入项目 ≠ 允许启动。** 登记成功不自动把该运行器加入任何项目，也不启动任何进程。

### 3.3 `capabilities` 定量规则（服务端强制）

1. 元素必须是字符串；数组长度 **0 ≤ n ≤ 32**，`n > 32` → **422**（不静默截断）。
2. 每个元素先 `strip()`；归一化后为空（`""` / 全空白）→ **422**（不静默丢弃空白项，避免“写了但没生效”）。
3. 归一化后单条长度 **1 ≤ len ≤ 64 码点**；超长 → **422**。
4. 归一化后出现重复项 → **422**（不静默去重；写入值必须与请求语义一致）。比较按归一化后的精确字符串（区分大小写）。
5. 请求体出现未知字段 → **422**（本片新增的登记/绑定请求 schema 使用 `extra="forbid"`；既有 API 的宽松行为不变）。
6. 非法类型（数字/对象/嵌套数组）→ **422**。

`capabilities` 与 `adapter_status` 一样**只描述登记事实**，不参与任何权限、路由或执行判定。

### 3.4 API

- `GET /api/runners`：任意已认证成员可读；返回 `RunnerOut[]`。
- `POST /api/runners`：**仅 human**；201；body 为 §3.1 可写字段；`runner_id` 重复 → 409；未知字段/校验失败 → 422。
- `PATCH /api/runners/{runner_id}`：**仅 human**；只允许改 `display_name` / `adapter_status` / `adapter_note` / `capabilities`；请求体出现 `runner_id` 或 `runtime` → 422（本片不允许改，避免让已冻结快照与登记事实分叉）；未知字段 → 422。
- 本片**无 DELETE**；停用走 `adapter_status=retired`，历史绑定与历史快照保持。

`RunnerOut` = `runner_id, runtime, display_name, adapter_status, adapter_note, capabilities, created_by, created_at, updated_at`。

## 4. 项目角色绑定

### 4.1 表 `project_role_bindings`

主键 `(project_id, member_id)`；**独立于 `project_agents`**，因为名册 `POST /sync` 是全量替换（`server/routes/projects.py:432-478`，先 `session.delete(row)` 再插入），挂在该表上的手工配置会被抹掉（与 `project_role_descriptions` 的设计理由一致，`server/models.py:156-175`）。

| 字段 | 类型 | 空值 | 语义与校验 |
|---|---|---|---|
| `project_id` | TEXT PK | 非空 | 项目 ID |
| `member_id` | TEXT PK | 非空 | 角色身份（`agent:*`）；不加强外键，**成员离册/被删后行保留** |
| `runner_id` | TEXT | 非空（行存在时） | 必须存在于 `runner_registry` 且写入时 `adapter_status != retired`（读取时另按 §4.4 现算）；slug 规则同 §3.1 |
| `model_source` | TEXT | 非空（行存在时） | `builtin` \| `custom_api` |
| `provider_id` | TEXT | 非空（行存在时） | 安全 token，≤ 128；如 `managed:kimi-code`。**仅标识** |
| `connection_ref` | TEXT | 非空（行存在时） | 安全 token，≤ 128；如 `native-kimi-code-managed-login`。**仅标识，见 §5** |
| `model_id` | TEXT | 非空（行存在时） | 运行器/后端实际调用标识，≤ 128；如 `kimi-for-coding` |
| `model_alias` | TEXT | 可空 | 运行器侧配置别名，≤ 128；可含 `/`；如 `kimi-code/kimi-for-coding`。**是原生调用选择参数**（运行器把它作为 `--model` 等启动参数传入，`bridges/kimi_bridge.py:95`），**不是**展示字段、**不是** `model_id`，也不得当作“实际 `model_id`” |
| `model_display_name` | TEXT | 可空 | **纯展示名**，≤ 64；如 `K2.8 Preview`。**不得当作 `model_id`、调用参数或身份** |
| `updated_by` | TEXT | 非空 | 最后写入的 human |
| `updated_at` | DATETIME | 非空 | UTC |

**一个 `(project_id, member_id)` 只有一行绑定。** 同名 `model_id` 在不同 `model_source` / `connection_ref` 下是不同绑定内容；跨角色并存靠两行主键，同一角色先后变更靠同一行的版本变化（§2）。

### 4.2 字段校验（服务端强制，前端仅体验）

对 `provider_id` / `connection_ref` / `model_id` / `model_alias` 使用同一套「安全 token」规则：

- 允许：ASCII 字母、数字、`.` `_` `-` `:` `/` `@`。
- 拒绝：空白与任何控制字符、引号、`` ` ``、`;` `|` `&` `$` `\` `<` `>` `(` `)` `%` `{` `}`、换行/制表符。
- 拒绝**有限启发式**可疑凭据形态（不承诺覆盖全部真实 Key，见 §5.4）：`sk-` 前缀、`Bearer `、`://user:pass@`、连续 ≥ 40 位的 base64/hex 风格串。
- 长度上限：`provider_id`/`connection_ref`/`model_id`/`model_alias` ≤ 128；`model_display_name` ≤ 64；`runner_id` ≤ 64（§3.1 slug）。
- 超长 → 422；行存在时必填字段为 `null` 或全空白 → 422（归一化后为空不等于“清空”，沿用 `normalize_controller_member_id` 的语义，`server/models.py:292-305`）。
- 可选字段全空白 → 归一化为 `null`。
- 请求体未知字段 → 422（`extra="forbid"`）；`binding` 键整体缺失 → 422。
- `model_source` / `adapter_status` 等枚举非法值 → 422，且只做 `strip().lower()` 后比较，不做其它猜测。

### 4.3 API

- `GET /api/projects/{project_id}/agents`：在现有 `ProjectAgentOut` 上**附加**两个字段：
  - `binding`: `RoleBindingOut | null` —— `null` 表示**没有存储行**（旧角色默认降级，不伪造默认模型）；行存在时按存储值返回（即使当前无效），有效性写在 `binding_state`。
  - `binding_state`: 始终存在，按 §4.4 阶梯**读取时实时计算**；`binding: null` 时它回答“为什么没有可用绑定”（`unconfigured` / 身份类状态）。
- `GET /api/projects/{project_id}/agents/{member_id}/binding`：任意已认证成员可读；**项目不存在 → 404（原 API 错误语义保持，不改变）**；
  返回 `{"project_id", "member_id", "binding": RoleBindingOut|null, "binding_state": <§4.4 状态>}`。
  **成员已离册/已删除/被禁用/非 agent 时仍返回存储行与状态**（不 404、不自动清理），因为“存着但不有效”正是需要如实展示的事实。
- `PUT /api/projects/{project_id}/agents/{member_id}/binding`：**仅 human**。
  - 请求体 `{"binding": {...} | null}`；`binding` 为**必填键**：缺失 → 422；未知字段 → 422。
  - 显式 `null` = 解除绑定（删除该行）；对“无行”“成员不在名册”都**幂等返回 200**（与角色说明的 D7 语义一致，`server/routes/projects.py:383-394`）。
  - **项目不存在 → 404（原 API 错误语义保持，不改变）**。非空 `binding` 的**写入校验**（不新建角色、不改权限）：
    1. 项目不存在 → 404；
    2. 目标成员不存在 / 已被全局禁用 / `kind != "agent"` / 不在当前名册 `project_agents` → **404**（一律视为“目标不在有效名册”）；
    3. `runner_id` 不在登记表 → 422；`runner_id` 已 `retired` → 422；
    4. 字段校验（§4.2）失败 → 422。
  - **并发收敛（D3，首期 last-write-wins）**：写入用**单条 upsert**`INSERT ... ON CONFLICT(project_id, member_id) DO UPDATE SET ...`（SQLite），两个并发 `PUT` 不会因主键冲突报 409，最终收敛到后提交者。残余窗口：`runner_id` 有效性是 upsert 之前的读校验，若登记在同一瞬间被改为 `retired`，可能落一行引用 `retired` 运行器的绑定；该情况在读取/快照时如实报 `runner_retired`，**不会**被误报为 `bound`；未来引入版本 CAS 另开片（D-3）。
  - 响应如实描述**操作后库里的状态**（含归一化后的值）。
- 项目 `DELETE /api/projects/{project_id}` 时显式删除本项目绑定行（对齐 `project_role_descriptions` 的清理做法，`server/routes/projects.py:668-689`），并沿用「名册孤儿行不追改」的既有边界。

`RoleBindingOut`：

```
runner_id, runtime, runner_display_name, runner_status,
model_source, provider_id, connection_ref, model_id, model_alias, model_display_name,
binding_state, binding_fingerprint, updated_by, updated_at
```

- `runtime` / `runner_display_name` / `runner_status` 从登记表**读取时派生**，不在绑定行重复存储；登记事实不可解析时（§4.4 序 7）三者均为 `null`。
- `binding_state` 见 §4.4（读取时按当前事实计算，风格同 `resolve_controller_assignment_status`，`server/models.py:308-326`）。
- `binding_fingerprint` 按 §2 的内容规则计算：**六个值（含由登记表派生的 `runtime`）在读取时全部可解析**才给出，否则 `null`；**与有效性无关**（无效行只要内容可解析就有指纹，便于审计配置内容）；`runner_missing` 因 `runtime` 不可解析而为 `null`。

### 4.4 有效性阶梯（F3 核心，优先级严格按序，先命中先返回）

绑定行的“存储事实”与“当前是否有效”是两件事。读取与快照都按**同一张阶梯**计算：

| 序 | `binding_state` | 触发条件（读时现算） | 字段布局 | 是否有效 |
|---|---|---|---|---|
| 0 | `no_project` | 仅任务快照：任务 `project_id IS NULL` | 绑定字段全 `null` | 无上下文 |
| 1 | `member_missing` | `members` 无该 `member_id` | 有行则照存，无行全 `null` | 否 |
| 2 | `member_disabled` | `members.disabled_at` 非空 | 同上 | 否 |
| 3 | `not_in_roster` | 不在 `project_agents(project_id, member_id)`（离册） | 同上 | 否 |
| 4 | `not_agent` | `members.kind != "agent"` | 同上 | 否 |
| 5 | `unconfigured` | 无绑定行 | 全 `null` | 否 |
| 6 | `partial` | 有行但**存储必填字段**不完整/不合法（见 §4.5） | 有值照存，缺的 `null`，指纹 `null` | 否 |
| 7 | `runner_missing` | 登记事实不可解析：`runner_id` 不在 `runner_registry`，或登记行存在但 `runtime` 为空（后者仅可能出现在旧库/手工数据） | 行值照存；`runtime`/`runner_display_name`/`runner_status` 为 `null`；指纹 `null` | 否 |
| 8 | `runner_retired` | 登记 `adapter_status = retired`（且 `runtime` 可解析） | 行值照存；运行器字段来自登记表；指纹可解析则给出 | 否 |
| 9 | `bound` | 以上全部通过，且**六个值全部可解析** | 行值 + 派生运行器字段；指纹给出 | **是** |

规则与边界：

- **保留存储不等于有效**：离册（`POST /sync` 全量替换移除名册行）后绑定行**刻意保留**；此时 `binding_state=not_in_roster`，**不得**报 `bound`。
- **不自动删除、不猜模型**：任何状态都不自动清理行，也不用成员名/模型名/历史惯例猜出运行器或模型。
- **回册**：名册重新同步包含该成员后，同一行的读取状态自动回到 `bound`（若运行器仍有效）；不需要人工重建绑定，也不改动任何历史任务。
- **不改变既有任务创建/claim权限**：状态只是记录与展示；`_ensure_target_agent`（`server/routes/tasks.py:97-101`）仍只校验“存在且为 agent”，本片**不新增**任何因绑定状态而拒绝创建/领取的分支。
- **优先级说明**：身份/名册事实（1–4）先于绑定内容事实（5–8），与既有 `resolve_controller_assignment_status` 的 `member_missing → member_disabled → not_in_roster → not_agent → assigned` 一致；因此“离册且运行器也 retired”报告 `not_in_roster`（更根本的原因先报），而不是 `runner_retired`。
- **`project_exists = 0` 不是一种 `binding_state`**：项目不存在时由调用 API 保持原错误码：项目接口 **404**、任务创建 **400**（见 §11），事实读取不得凭空造出 `unconfigured`/`member_missing` 之类状态（R1）。

### 4.5 `partial` 与指纹的精确边界（R2）

| 字段 | 参与 `partial` 判定 | 判为“不可解析”（← 触发 `partial`）的条件 | 参与六维指纹 |
|---|---|---|---|
| `runner_id` | **是**（存储必填） | `NULL` / `strip()` 后为空 / 不匹配 §3.1 slug 规则（含 >64 码点） | 是 |
| `model_source` | **是**（存储必填） | `NULL` / 空 / `strip().lower()` 后 ∉ {`builtin`, `custom_api`} | 是 |
| `provider_id` | **是**（存储必填） | `NULL` / 空 / >128 码点 / 违反 §4.2 安全 token 规则 | 是 |
| `connection_ref` | **是**（存储必填） | 同上 | 是 |
| `model_id` | **是**（存储必填） | 同上 | 是 |
| `model_alias` | **否**（可选存储） | 不参与：写入侧由 §4.2 拦 422；旧库/手工行里非法或超长的值**照存**，不改变 `binding_state` | 否 |
| `model_display_name` | **否**（可选存储） | 同上（纯展示） | 否 |
| `runtime`（派生） | **否** | 派生字段**不参与** `partial`；登记行缺失或运行器事实不可解析一律走序 7 `runner_missing` | 是（需可解析） |

**为什么这样切**：`partial` 只回答“**这张绑定行本身**是否存够了内容”，不回答“运行器现在还在不在”。
因此 `runner_missing` **不会**被 `partial` 提前覆盖：登记表查不到 `runner_id` 时，五个存储必填字段仍可能齐全 → `partial` 判定为“齐全” → 落到序 7 报 `runner_missing`。

指纹与状态的关系（与 §7.2 表逐行一致）：

- `runner_missing` → `runtime = null`、`binding_fingerprint = null`；
- `partial` → 五个存储必填字段至少一个不可解析 → 六值不可能齐全 → 指纹恒 `null`；
- `runner_retired` → 登记行仍在且 `runtime` 可解析 → 六值齐全则有指纹（`runtime` 不可解析的旧库边界归序 7）；
- `bound` → 六值全部可解析 → 指纹给出；
- 身份/名册类状态（序 1–4）与 `unconfigured`：**与有效性无关**，只要行内容六值可解析就给指纹，无行则全 `null`。

## 5. 配置来源与连接引用边界（硬规则）

### 5.1 不透明标识符

`connection_ref` 与 `provider_id` 是**不透明标识符**：服务端**永不**据此读取文件、解析路径、拼接命令、发起网络请求、取用密钥或探测连接可用性。它们只回答“这条绑定指向哪条**仓库外**连接/来源的登记名”。

### 5.2 禁入范围（精确限定，F6）

**禁止进入**任何仓库文件、Task Hall 消息正文、任务标题、任务快照、日志正文的内容是：

1. **凭据正文**：API Key、访问令牌、密码、私钥、OAuth secret、会话 cookie；
2. **含密连接资料**：`scheme://user:pass@host` 形态的连接串、含令牌的 URL 查询串、可据以取到密钥的完整配置片段；
3. 任何可**还原**出上述内容的片段（例如完整 Key 的前后段拼接、密钥文件名 + 内容）。

**允许出现**（脱敏标识符，非凭据）于 API 响应、任务快照、文档、示例与审查证据：

- `runner_id`、`runtime`、`model_source`、`provider_id`、`connection_ref`、`model_id`、`model_alias`、`model_display_name`、`adapter_status`、`binding_state`、`binding_fingerprint`。

理由：这些字段只标识“哪条运行器/来源/连接/模型”，本身不含凭据；本合同、样例、未来配置与审查交付都需要它们才能被验证。原需求禁止的是**凭据正文**，不是全部安全元数据。

### 5.3 Task Hall / 任务标题 / 日志（R3 更正）

- **Task Hall / 任务标题**：服务端**不自动**把完整绑定**混入业务正文**——创建任务时不把 `target_binding_snapshot` 序列化进 `content`、标题或 Hall 正文；绑定事实通过任务快照/API/MCP 只读字段读取（保持任务正文聚焦业务内容）。
- **允许**：人类或**本次授权的审查交付**（TALK 任务结果消息、交付 JSON、设计稿、复核证据）在正文中包含 §5.2 允许列表里的**脱敏标识符**——这是审查与复核的既成事实（本片自身的交付 JSON 与证据即为其例），不属于“把完整绑定混入业务正文”。禁的只是**凭据正文**（§5.2 第 1–3 项）。
- **公开 API 返回**：允许返回 §5.2 列出的绑定标识符（角色页/工具需要），但**永不**返回凭据、凭据路径或“可用性探测结果”。
- **日志**：绑定相关日志只记 `project_id`、`member_id`、`binding_state`、`runner_id`；**不记** `provider_id` / `connection_ref` / `model_alias` / `model_display_name`，不记请求体原文，不记完整快照 JSON。
- `adapter_note` 与快照 `note` 字段是自由文本，同样受 §5.2 约束。

### 5.4 启发式校验的诚实边界

§4.2 的 `sk-` / `Bearer ` / `:pass@` / ≥40 连续 base64/hex 等形态检查是**有限启发式**：它只能挡住常见形态，**不承诺**识别任意真实 Key（例如自定义前缀、短令牌、被拆分/编码的密钥）。因此：

- 硬要求是**写入方不发送凭据**，服务端只是尽早 422 降低误入概率；
- 看到“疑似”而拒绝是**保守的**，看到“不疑似”而放行**不等于**已证明安全；
- 不得把本校验当作“已确认无密钥”的证明写进验收结论。

### 5.5 不实现的能力

本片**不实现**“连接可用性校验”“密钥有效性校验”“模型可信性校验”；合同不提供这类字段，避免把“无法核实”写成“已核实”。TALK 服务端**不**把 `model_display_name` / `provider_id` / `runtime` / `model_id` / `model_alias` 用于任何身份、权限或路由判定。
（说明：`model_alias` 被**原生运行器**用作启动调用参数，那是运行器侧的模型选择，不是 TALK 服务端的路由/权限判定；两者不要混淆。）

## 6. 身份与权限

- **身份**：`member_id`（`members.id`）是唯一身份键（`server/models.py:19-29`）。模型名、展示名、runtime、provider、connection、`binding_state` 都不改变身份，也不合并成员。
- **业务职责**：`business_role` 仍是项目自定义自由文本；本合同的绑定不写、不读、不覆盖它。
- **决策分级**：`decision_tier` 仍只来自名册/argv 注入；模型来源不提升分级。
- **写权限**：登记与绑定**仅 human**（复用 `_require_human`，`server/routes/projects.py:49-51`）。不新增任何 agent 写权限（D7 维持后置）。
- **读权限**：沿用当前合同——任意已认证成员可读项目与名册（`server/routes/projects.py:253-304`，`tests/test_projects.py:29-52`）。本片不收紧、不放宽。
- **不改变**任务创建/领取/完成权限、质量门禁、`may_delegate`/预算字段、受控等待门禁、`controller_*` 兼容字段。
- **不引入**固定主控、会话租约、自动唤醒或按模型授权的任何机制。

## 7. 任务绑定快照：取得点、一致性、不可变性

### 7.1 存储

`agent_tasks` 新增两列（幂等增量迁移，见 §10）：

| 列 | 类型 | 空值 | 语义 |
|---|---|---|---|
| `target_binding_snapshot` | JSON | 可空（**仅旧行为 NULL**） | 冻结对象；**新任务一律写入对象**（含 `no_project`） |
| `target_binding_state` | TEXT | 可空（**仅旧行为 NULL**） | 状态枚举；`NULL` = 该任务创建时此能力尚未启用（旧数据） |

快照 `schema_version = "role-binding-snapshot-1"`，对象字段：

```
schema_version, snapshot_at, state,
runner_id, runtime, model_source, provider_id, connection_ref,
model_id, model_alias, model_display_name, binding_fingerprint, note
```

- **R3 范围裁决**：**首期不新增 `read_receipt`**，也**不新增**任何“读取回执/自报语句计数”的持久字段或常量。快照对象里没有 `read_receipt`。
- 读取方案、实际执行的 SQL 条数、读取方案版本哈希**只作为隔离验证证据**存在（本地设计探针 `probe_fact_read.py` 与 B1b 的事件计数测试），**不进入**任务表、快照、API 或 schema；**不扩大 schema**。
- `read_receipt` 只出现在未实施的 v2 草稿里，**从未写入任何数据库**，因此删除它不需要迁移、不需要新增 `schema_version`；快照仍为 `role-binding-snapshot-1`。
- 单语句一致性由**行为证据**证明（SQLAlchemy `before_cursor_execute` 事件计数 + 两连接交错负对照），**不以任何自报常量或快照内常量作为证据**。
- `journal_mode`、`isolation` 等属于部署事实，**不在每次读取里探测**，只由 B1 的隔离测试固定断言。

### 7.2 状态与 null 布局

`state` 与 §4.4 阶梯完全一致，另加任务级的 `no_project`（§4.4 序 0）。**新任务一律写入非 NULL 的 `state` 与 `target_binding_snapshot`**，包括无项目任务与 schedule 物化任务。字段布局：

| `state` | runner/model 字段 | `runtime` | `binding_fingerprint` | 说明 |
|---|---|---|---|---|
| `no_project` | 全 `null` | `null` | `null` | 无项目上下文（含 schedule 物化） |
| `member_missing` / `member_disabled` / `not_in_roster` / `not_agent` | 有行照存；无行全 `null` | 有行且登记事实可解析时派生 | 六个值可解析则有（含派生 `runtime`） | 身份/名册失效，保留存储但记录失效原因 |
| `unconfigured` | 全 `null` | `null` | `null` | 有名册但未配置 |
| `partial` | 有值照存，缺的 `null` | 登记事实可解析则派生 | **`null`**（存储必填字段不齐 → 六值不齐） | 绑定行内容不完整/不合法 |
| `runner_missing` | 行值照存（含 `runner_id`） | **`null`** | **`null`**（`runtime` 不可解析） | 登记事实不可解析 |
| `runner_retired` | 行值照存 | 派生自登记表 | 六值可解析则有 | 已停用 |
| `bound` | 全部按绑定行原值 | 派生自登记表 | 六字段齐备则有 | 当前有效 |

**任何状态都不允许用成员名/模型名/历史惯例猜出一个运行器或模型填进去。**

`model_alias` 在所有状态下都**照存**（它是调用选择参数，不是展示字段）；因此“两个任务快照的 `binding_fingerprint` 相同”**不能**用来断言它们的调用配置相同——必须同时比较 `model_alias`（见 §2、`ROLE_MODEL_BINDING_EXAMPLES.json` 的 alias 变更样例）。

### 7.3 一致读取方案与线性化点（F1 核心 + R1 更正）

**v2 的缺陷（R1，已由 Codex 独立复现）**：v2 的 SQL 以 `project_role_bindings` 作 `FROM` 锚点，
在“已入册无绑定 / 禁用无绑定 / 未注册无绑定 / 非 agent 无绑定”四例都返回 **0 行**，无法满足 §4.4；
而且 `LEFT JOIN projects` 无法从 0 个 binding 行里生出结果；已配置例还漏 `model_source` / `provider_id` /
`connection_ref` / `model_id` / `model_alias` / `model_display_name` 六个快照字段。

**v1 的错误结论（已撤回，保留记录）**：v1 曾写“同一 SQLModel Session 内多次读取与插入同事务提交，因此不会撕裂”。
该断言**不成立**：`server/db.py:41` 只设 `check_same_thread=False`，没有 `BEGIN`/autocommit 配置；
在 pysqlite 的默认（deferred/legacy）事务控制下，一条独立 `SELECT` **不会**开启一个持续的读事务。

**修订方案（v3 采用）**：`read_role_binding_facts()`（B1a 提供）与 `resolve_target_binding_snapshot()`（B1b 复用）
用**一条 SQL**，以**单行请求参数 CTE** 作锚点无条件保留请求的 `(project_id, member_id)`，再各自独立 `LEFT JOIN`
项目/成员/名册/绑定/登记，**一次取齐**状态判定与全快照所需字段；因此**无绑定行时仍返回 1 行**。
**不允许**“0 行后再补第二条查询”，也**不允许**用早先 ORM 缓存/成员对象推断（R1）。

**最终事实读取 SQL（助手常量 `BINDING_FACTS_SQL`；合同、B1a/B1b 助手与隔离探针必须逐字符一致）**：

```sql
WITH requested(project_id, member_id) AS (
    SELECT :project_id AS project_id, :member_id AS member_id
)
SELECT
    req.project_id                                   AS requested_project_id,
    req.member_id                                    AS requested_member_id,
    p.project_id                                     AS project_id,
    (p.project_id IS NOT NULL)                       AS project_exists,
    m.id                                             AS member_id,
    (m.id IS NOT NULL)                               AS member_exists,
    m.kind                                           AS member_kind,
    m.disabled_at                                    AS member_disabled_at,
    pa.member_id                                     AS roster_member_id,
    (pa.member_id IS NOT NULL)                       AS in_roster,
    b.project_id                                     AS binding_project_id,
    b.member_id                                      AS binding_member_id,
    (b.project_id IS NOT NULL)                       AS binding_exists,
    b.runner_id                                      AS runner_id,
    r.runner_id                                      AS registry_runner_id,
    (r.runner_id IS NOT NULL)                        AS runner_exists,
    r.runtime                                        AS runtime,
    r.display_name                                   AS runner_display_name,
    r.adapter_status                                 AS runner_status,
    b.model_source                                   AS model_source,
    b.provider_id                                    AS provider_id,
    b.connection_ref                                 AS connection_ref,
    b.model_id                                       AS model_id,
    b.model_alias                                    AS model_alias,
    b.model_display_name                             AS model_display_name,
    b.updated_by                                     AS updated_by,
    b.updated_at                                     AS updated_at
FROM requested AS req
LEFT JOIN projects              AS p  ON p.project_id  = req.project_id
LEFT JOIN members               AS m  ON m.id          = req.member_id
LEFT JOIN project_agents        AS pa ON pa.project_id = req.project_id AND pa.member_id = req.member_id
LEFT JOIN project_role_bindings AS b  ON b.project_id  = req.project_id AND b.member_id  = req.member_id
LEFT JOIN runner_registry       AS r  ON r.runner_id   = b.runner_id;
```

SQL 硬约束（与本 SQL 一起实现）：

- **单条语句**：整段只有一个 `;`（结尾），不含子查询后再补查询；调用方一次 `session.execute(text(BINDING_FACTS_SQL), {...})`。
- **恰好 1 行**：五个 `LEFT JOIN` 的右表主键都是 `(project_id, member_id)` 或 `runner_id` 单键，因此结果恒为 1 行（`mappings().one()`），与是否存在绑定行无关。
- **列别名唯一**：上列 27 个别名互不重复（`runner_id` 与 `registry_runner_id`、`member_id` 与 `roster_member_id` 等分别命名），避免 `Mappings` 覆盖。
- **参数只有两个**：`:project_id`、`:member_id`（都来自请求，不来自 ORM 缓存）。
- **`project_exists = 0`** → 事实助手只返回不存在事实，**不产生任何 `binding_state`**。项目名册/绑定接口映射为 **404**；任务创建保留 `_ensure_project_exists` 的 **400**（`server/routes/tasks.py:104-106`），任务快照助手再次遇到此事实也按 **400**，不由共用读取助手统一抛 HTTP 错误。
- **无项目分支（`project_id is None`）**：不执行 SQL，直接 `state="no_project"`、字段全 `null`（语句数 **0**）。

- **一致视图与取得点**：单条 SQL 一次取得项目/成员/名册/绑定/登记事实，保证这些值来自同一数据库视图，避免多条 SELECT 混合前后版本。DBAPI 尚无持久事务时，视图在本条语句首次读取时取得；已在真实读/写事务内时，沿用该事务的视图并可见自身写入，不能无条件宣称“语句开始前最后一次提交”。任务快照记录本次解析实际读到的配置，而非提交时刻最新配置。SQLModel Session 的逻辑事务标记不能替代 DBAPI 事务事实。
- **写入与提交**：解析结果写入 `AgentTask(...)` 的 `target_binding_snapshot` / `target_binding_state`，与任务行、Task Hall 群、Hall 成员、关系记录**同一次 `session.commit()`** 落库（`server/routes/tasks.py:1644-1695` 的现有事务边界）；异常路径整批回滚，**不留“有任务无快照”**。
- **autoflush 与已存在事务**：使用 Core/文本列选择，避免 ORM 实体查询引发未预期的 autoflush；不以此前缓存对象代替事实 SQL。子任务授权预扣在 `server/routes/tasks.py:748-753` 已执行 UPDATE，是真实写事务，不是仍未发往数据库的 pending 写；此路径沿用已有事务，不另发 BEGIN、不提前 commit。若实现者改用 ORM 查询或改变 flush 顺序，须另行说明并验证读取视图及同次回滚边界。
- **不新增显式 `BEGIN` / `BEGIN IMMEDIATE`**：本片保持现有引擎与调用方事务。真实写事务已经存在时再 BEGIN 会失败，主动加锁也会改变并发写入、busy/超时/重试行为。显式 BEGIN 本身不提供“commit 时刻最新配置”保证；取得时点由 SQLite 事务视图规则决定。若未来要求提交时严格对照，需独立设计和验证。
- **时间窗口**：配置在快照解析后变化，不会追改已生成快照；旧任务照存，后续任务依据其自身读取视图重新解析。已有事务视图和自身写入边界也必须列入 B1b 隔离验证。
- **失败与重试**：`commit` 失败（如关系冲突 409）→ 整批回滚，任务不存在，下次请求重新解析（可能读到更新配置），不会留下半个快照。
- **测试义务（R3 更正）**：单语句性质由**行为**证明——隔离测试用 SQLAlchemy `before_cursor_execute` 事件统计 `resolve_target_binding_snapshot()` 期间的语句数并断言带项目分支 `== 1`、无项目分支 `== 0`，再用两连接交错负对照证明单语句不撕裂。**不**把任何自报常量当作证据。

### 7.4 不可变性（合同硬约束）

- 快照写入后**永不** `UPDATE`：`claim` / `heartbeat` / `complete` / `cancel` / 租约过期回收 / 重领 / `requeue-expired` / 质量子任务创建 **都不修改** `target_binding_snapshot` 与 `target_binding_state`。
- **配置变更只影响新任务**：绑定 `PUT` 只写 `project_role_bindings`，不得触碰任何 `agent_tasks` 行。
- **同期 alias 变更也必须逐版本留证**：alias 是调用选择参数（§2）。同一角色只改 `model_alias` 时六维指纹不变，但**新任务的快照必须写入新的 alias**，旧任务的快照保持旧 alias 逐字节不变；读取方不得因为“指纹相同”就认为两个任务的调用配置相同。
- **历史不追改**：不为旧任务回填快照，不因绑定变更或**名册离册/回册**重写历史任务归属或快照。
- 旧任务 NULL 语义：`target_binding_state IS NULL` = 未记录（`legacy_unrecorded`），读取方必须如实展示“未记录”，不得推断成 `unconfigured` 或某个模型。

### 7.5 唯一写入点（F2 核心更正 + R2 静态检查边界）

**更正**：v1 计划把解析写在 `create_task` 事务内，但 schedule 物化走的是 `_create_task_from_schedule` → `_create_task_with_hall`（`server/routes/tasks.py:1508-1536`），**绕过** `create_task`（1548-1695）。只在 `create_task` 写会让 schedule 物化任务的两列为 NULL，违反“新任务一律非 NULL”的合同。

**修订**：共用构造 `_create_task_with_hall`（`server/routes/tasks.py:1408`）是**唯一**的快照构造/写入点：

1. 在函数**最开头**（构造 `Group`/`GroupMember`/`AgentTask` 之前）调用 `resolve_target_binding_snapshot(project_id=project_id, target_member_id=target_member_id, session=session)`；
2. 把 `target_binding_snapshot` / `target_binding_state` 作为 `AgentTask(...)` 的构造参数一并写入；
3. 该函数只 `add` + `flush`（1493-1494），最终 `commit` 仍由调用方负责（`create_task` 1687、`run_due_task_schedules` 1837），因此快照与任务/Hall/关系天然同生共死；
4. 两个入口都自动覆盖：`create_task`（普通/子任务）与 `_create_task_from_schedule`（schedule 物化，`project_id=None` → `state=no_project`，字段全 `null`）;
5. `schedule` 批量物化时逐任务各自解析一次（各自单语句读），互不影响；同一批次的多次读取可能落在不同的已提交配置上，各自如实记录。

**唯一入口的机械保证（R2 限定检查范围）**：B1b 增加测试断言 `_create_task_with_hall` 的两处调用点（`tasks.py:1644`、`1509`）产生的新任务两列都非 NULL；
并做**限定在生产插入路径内**的静态检查：在 `server/**`（生产模块）里枚举 `AgentTask(` 构造点，断言除 `_create_task_with_hall` 外没有别的生产构造点绕过它。
**该检查不覆盖 `tests/**`**：测试 fixture 允许直接构造 `AgentTask` 来准备数据，不属于“生产插入路径”。
**不写**“全仓库禁止出现 `AgentTask(`”这类过宽禁令。

### 7.6 各创建路径的兼容

| 创建路径 | `project_id` | 快照解析 |
|---|---|---|
| 普通顶层任务（带项目） | 请求值 | 按该角色当前绑定解析，同事务写入；状态按 §4.4 |
| 普通顶层任务（无项目，旧客户端） | `null` | `state=no_project`，字段全 `null`（**两列仍非 NULL**） |
| 子任务 | 必须等于父任务（`server/routes/tasks.py:422-427`） | 按**子任务自身** `target_member_id` 在当前项目下重新解析（新任务新快照；D1 已裁决：不继承父目标角色配置） |
| schedule 物化 | 恒为 `null`（`server/routes/tasks.py:1508-1536`，`agent_task_schedules` 无 `project_id`） | `state=no_project`，字段全 `null`（**两列仍非 NULL**）；schedule 项目化留待后续独立片（D6） |
| 已排队/已领取任务 | — | 继续使用其创建时的快照；配置漂移不改变在途任务 |

**D1（已裁决）**：子任务**不继承**父任务快照，按自身目标角色重新取；不扩大任务权限。

### 7.7 排队/领取期间配置漂移

- 任务快照不变（§7.4），包括角色离册/回册。
- 运行器是否按快照执行属于后续能力；**首片不据此拒绝 claim**（D2：现有 bridge 无按任务选模型能力，强制拒绝会破坏既有执行链路，且“真实不匹配如何处置”尚未被用户确定为产品规则）。
- 差异必须**如实可读**：读取方能看到“派发时配置快照”与（B2 后）“实例自报实际运行器/模型”，两者分开显示，互不覆盖。

## 8. 配置值 vs 实际运行证据（F4：实际对照整体后置到 B2）

### 8.1 本片只做配置记录，不做实际对照

| 层 | 来源 | 本片（B1a/B1b） | 可信度 |
|---|---|---|---|
| 配置值 | 绑定行 / 任务快照 | `project_role_bindings` + `target_binding_snapshot` | 记录“当时如何配置”，**不代表实际运行** |
| 实际值 | 运行器自报实例状态 | **本片不定义字段、不输出对照** | 后片 B2 |

**本片硬约束**：B1/B3 的任何接口与页面**不得**输出 `binding_match` / `binding_match_actual` 等“实际匹配”结论；只允许展示配置快照与（未来）实际值本身，二者分开。

### 8.2 B2 必须另开设计片，且必须满足以下前置约束

当前 v1 设想的 `reported_runner_id / reported_model_source / reported_model_id / reported_model_alias / report_evidence_kind / reported_at` **不足以**支撑历史任务的“实际对照”，原因：

1. 缺**关联锚点**：这些字段挂在 `agent_instances` 上，而实例表既无 `project_id` 也无 `task_id`（`server/models.py:178-191`），`reported_*` 无法定位到具体 project/task/attempt；
2. 缺**连接维度**：没有 `provider_id` / `connection_ref`，同模型不同连接无法区分；
3. **原地覆盖**：`server/routes/instances.py:50-57` 每次上报覆盖同一实例行的最新值（`instance.runtime = body.runtime` 等），历史 attempt 的事实会被后续上报顶掉；
4. 例子把 **alias 当 model_id**：`kimi-code/k3` 是运行器侧 alias（且是调用选择参数），不是 `model_id`（`bridges/kimi_bridge.py:95`）。

因此 B2 的**设计前置合同**（不预设字段名，只约束不变量）：

- **R-B2-1 关联锚点**：每条实际上报必须携带可保存的 `project_id + task_id + attempt` 证据锚点（或等价的不可变证据记录），能被审计到“哪一次尝试”；
- **R-B2-2 维度完整**：比较维度至少覆盖 运行器（`runner_id`/`runtime`）、来源（`model_source`/`provider_id`）、连接（`connection_ref`）、模型（`model_id`，alias 只作展示/调用参数，不作比较基准）；**任一必要维度不可得**必须显式 `unknown`，不得只比 `model_id` 就下结论；
- **R-B2-3 不可变证据**：实际值必须是**按 attempt 留存的不可变证据**，不得用实例最新值派生历史 attempt 的结论；实例复用、重领、续接各留各的证据；
- **R-B2-4 unknown 降级**：无法取得或仅 `config_only`（只有配置值、没有运行期证据）→ **`actual_match = unknown`**，禁止渲染成“匹配”；
- **R-B2-5 命名分离**：配置对照（`binding_match_config`）与实际对照（`binding_match_actual`）在字段、API 与页面上分开命名与展示，任一方不得冒充另一方；
- **R-B2-6 证据类型**：`report_evidence_kind` 至少区分 `runtime_reported`（运行器回报本次使用）/ `config_only`（只知启动配置）/ `unknown`。

B2 未落地前，**不得**把“照常执行”写成用户已批准的产品规则；`mismatch` 的处置（是否阻止 claim/要求人工确认）仍是待决策项 D-2。

## 9. 真实能力边界（不宣称已验证）

- 各运行器能否在运行期按任务切换模型/连接：**无实现、未实测**（模型在启动 argv 固定，`bridges/kimi_bridge.py:95`）。
- `model_alias` 由原生运行器作为启动调用参数使用（同一处证据），因此它属于**调用配置**；但 TALK **没有**按任务改写该参数的能力。
- WorkBuddy 等外部宿主是否具备等价绑定字段或执行侧能力：仓库内无证据，`unknown`。
- 终端真实工具上限 T、显式等待 W、返回余量、取消/同连接排队：本设计片**不重测**。
- Kimi Code + K2.8（`agent:kimi-code-k28-preview`）的项目名册同步、运行器启动、真实接单：维持“待人类同步 / 延后验证”。
- **`agent:kimi` 的 L1-1（独立分配侧）身份限制**：本片只把它作为**历史证据**引用（#190/既有文档的记录）。本片**未重核**该项，因此**不得**把它当作“当前仍然缺失”的断言，也**不得**用 K2.8 的注册状态反向推翻它；两者互不作证（R2）。

## 10. 旧数据、旧客户端与迁移

- **只做增量迁移**：`runner_registry`、`project_role_bindings` 为新表（`SQLModel.metadata.create_all` 建表，`server/db.py:44-49`）；`agent_tasks` 用 `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` 增列（`server/db.py:74-165` 既有模式）。不重建表、不改列类型、不删除列。
- **不新增任务表列**（R3）：除 `target_binding_snapshot` / `target_binding_state` 外不加任何“回执/计数/哈希”列；本片**不扩大 schema**。
- **不回填虚构数据**：旧 `agent_tasks` 行的新列保持 NULL；不给旧绑定/旧角色补默认运行器或默认模型。
- **幂等**：迁移语句按列存在性判断，重复启动服务不重复执行；新增索引用 `CREATE INDEX IF NOT EXISTS`。
- **旧客户端**：
  - `POST /api/tasks` 请求体不变即可工作；快照由服务端解析，客户端**不需要**新增字段，也**不得**依赖它。
  - `AgentTaskOut` 新增字段是**附加**字段；旧客户端忽略未知字段。
  - `POST /api/projects/{id}/sync` 载荷与全量替换语义**不变**；绑定表不参与 sync 的删除范围（离册后绑定行保留并按 §4.4 报 `not_in_roster`）。
  - `GET /api/projects/{id}/agents` 新增 `binding` 与 `binding_state` 键为附加字段；`binding: null` 表示未配置，旧页面沿用现有展示。
  - ⚠ 实施注意：`tests/test_project_development_requirements.py:404-419` 对整份 `talk_list_agents` 载荷做 `payload.count("development_requirements") == 1` 的字面计数断言；新增字段不得复制既有键名、不得重复承载开发要求。
- **保留的兼容事实**：`agent_tasks.project_id` 仍可空；schedule 物化仍 `project_id=None`；`prj_*` 旧任务、旧消息、旧结果消息、旧收取流程完全不变。

## 11. 状态与错误码约定

| 场景 | 状态码 |
|---|---|
| 非 human 写登记/绑定 | 403 |
| 项目不存在（读/写绑定、读名册） | 404 |
| 任务创建的项目不存在（含快照解析再发现不存在） | 400；保留 `server/routes/tasks.py:104-106` |
| 非空绑定但目标不在有效名册（不存在/禁用/非 agent/未入册） | 404 |
| 注册重复 `runner_id` | 409 |
| 绑定引用的 `runner_id` 不存在 | 422 |
| 绑定引用 `retired` 运行器 | 422 |
| 必填字段缺失/空白/超长/非法字符/疑似凭据 | 422 |
| `binding` 键整体缺失 | 422 |
| 请求体未知字段 | 422 |
| `capabilities` 超量/空白/重复/超长（§3.3） | 422 |
| 解除绑定（无行/不在名册） | 200 幂等 |

**按调用 API 保持原错误码**：事实读取返回 `project_exists = 0` 时不构造任何绑定状态，也不在通用事实助手内固定 HTTP 状态码；项目接口沿用 404，任务创建沿用 400。

## 12. 范围裁决与待决策项

**本片采用的范围裁决（不重复上报人类，仅记录）**：

| 编号 | 裁决 | 落地位置 |
|---|---|---|
| D1 | 子任务按自身目标角色新取快照，不继承父目标配置；不扩任务权限 | §7.6 |
| D2 | B1 仅记录配置快照，不拒绝 claim；真实不匹配处置后置，不把照常执行当已定产品规则 | §7.7、§8 |
| D3 | 首期完整绑定写为 last-write-wins；并发新建冲突由单条 upsert 收敛，未来 CAS 另片 | §4.3 |
| D4 | 首期无 DELETE，`retired` 保留历史 | §3.4 |
| D5–D7 | 展示命名、schedule 项目化、agent 自改绑定继续后置；维持 human 写 | §3.3、§7.6、§6 |
| D8（#192 新增） | 首期**不新增** `read_receipt` 或任何读取回执持久字段；单语句一致性只由隔离验证证据与行为测试证明，不扩大 schema | §7.1、§7.3 |

**仍待人类决策（后置，不擅自确认）**：

| 编号 | 问题 | 本片推荐 | 影响 |
|---|---|---|---|
| D-2 | 配置 vs 实际 `mismatch` 是否阻止 claim / 要求人工确认 | 不阻止，只记录与展示；属 B2+人工决策 | §8 |
| D-5 | 产品展示名规则、默认名/重名、与模型名的关系 | 全部后置到完整角色页面设计 | 展示层 |
| D-6 | schedule 是否项目化并携带项目绑定快照 | 后置独立片（既定边界） | §7.6 |
| D-7 | 是否允许 agent 写自己的绑定 | 不允许；如需另开权限片并显式评审 | §6 |
| D-9（#192 新增） | 六维指纹不含 alias，而 alias 影响原生调用选择；是否需要把 alias 纳入独立“调用配置指纹” | 本片**不**新增第二指纹；先在快照里逐版本保留 alias，等 B2 决定 | §2、§7.4 |


## 适配收尾补充合同（2026-10-10）

用户确认适配阶段核验事实并受信登记/绑定，页面读取结果。#203–#205最终设计已独立复核收取，正式依据见[收尾合同](ADAPTER_BINDING_CLOSEOUT_DESIGN.md)与[C1–C4实施计划](ADAPTER_BINDING_CLOSEOUT_IMPLEMENTATION_PLAN.md)。实际收尾尚未实现；不重复增加人工填写技术字段表单，不改变本合同human写权限、六维binding_fingerprint、alias快照或实际模型证据边界。
