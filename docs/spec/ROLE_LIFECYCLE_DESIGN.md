# 项目角色创建、原生接入与服务生命周期合同（R0 正式实施合同 v4）

> 2026-10-17增量实施：259已完成[存量身份补录产品片A](ROLE_LEGACY_ATTACH_DESIGN.md)，新增human-only legacy-attach及独立补录审计，沿用原ID/Key并与创建入口双向隔离操作键；投影来源扩展见§5.2。未执行5角色真实补录/迁移或原生验收，原创建、轮换与受管所有权边界保持。

> 状态：**R0 v4、R1-1 与 R1-2 已独立复核通过**（2026-10-11）。R1-2 经218–221补正、Codex定向修复及222独立复核整链收取，配置作业/宿主脚本与固定分级迁移已实现，最终协议见[配置合同](ROLE_PROVISION_CONTRACT.md)。页面一键配置、受管启停、删除/退出仍属R1-3/R1-4；真实运行器能力未验。R1-2三项页面基础已获用户明确“验收通过”，不外推真实配置/运行器能力；原交付/失败保持。
> 正式位置：`docs/spec/ROLE_LIFECYCLE_DESIGN.md`；配套实施计划见同目录 `ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md`。
> 修订基线：`5b18c8e7c2eb85fb6737d7c9c89713adf6021ef7`（#215 派发时实际 HEAD，工作区干净，正式源码未变）。
> 本稿承接 #213 原稿与 #214 F1–F6 修订稿；原 213 草稿（`e7ff4694d26b3b3750623e25b1a595645e8c5e29`）与其原结果 msg2717、失败/验收回执、#214 修订稿与 msg2718 **全部保持不动**；本稿是完整修订版，不是覆盖。
> R0 发布时仅修改合同、计划和相关进度；不改变当时正式代码/测试/配置/数据库。R0 源码基线为 `36aaf288bd75d8dfd7065a61282d5aeef362663f`（相对原派发基线仅协调进度变化）。首片 R1-1 按用户既有开发授权实施，其后各片仍逐片派发、独立复核与验收。

直接需求来源：#213 任务包（`.tmp/project-role-lifecycle-design-dispatch/task-package.txt`）、#213 复核报告（`.tmp/role-lifecycle-r0-review/review.json` F1–F6）、#214 补正任务包与复核报告（`.tmp/role-lifecycle-r0-rework-review/review.json` R1–R5）、#215 补正任务包（`.tmp/role-lifecycle-r0-final-dispatch/task-package.txt`）。既有方向与本合同冲突时，以用户 2026-10-10 最新确认方向为准。

**本稿相对 #214 修订稿的五处实质修正**（原索引及原消息保留在本机 `.tmp/project-role-lifecycle-design-final/`，正式合同不依赖这些文件运行）：

| 编号 | #214 修订稿问题 | 本稿修正落点 |
| --- | --- | --- |
| R1 | 两阶段 TX1/TX2 留下可永久 `pending` 的窗口；§7.2 与 §7.3 对 `pending` 重放的规定互相矛盾；`failed` 并发重试无执行权规则 | §4.1.3 取消独立 TX1，改为**单一写事务 TX-ALL**；§7.2 重写并给出 TX1 后宕机 / TX2 中宕机 / 失败标记前宕机 / 两个 failed 恢复并发四类场景的精确结果；§7.7 故障注入与并发测试 |
| R2 | 权限读路径直接读持久 policy，离册角色仍享 `review_exempt`，等于扩权 | §8.4 读路径同时要求名册行有效 + 成员为启用 agent + `ProjectRole`（若存在）未归档；§8.5 迁移/sync 两次/移除/回册/归档行为对比与测试 |
| R3 | `rotate-key` 只核未归档就改全局凭据，漏旧名册引用与在用事实；与“服务端不留明文”口径冲突 | §7.5 `rotate-key` 限定 managed 独占身份 + 事务内完整引用证明（含旧 `ProjectAgent` 名册路径），稳定拒绝码；同一证明复用于可选 global-disable；§7.4 澄清明文列口径 |
| R4 | claim 生成了 token 但 report 不携带/不核验；缺 action/`expected_instance_id`/`launch_expires_at`；实例可任意换 `launch_id` 重新贴本次标签 | §4.1.5/§4.1.6 schema 补齐；§10.2 claim/report 携带并核验 token + 领取身份 + host + project + generation + deadline；§10.4 实例 launch 关联不可变 |
| R5 | 迁移矩阵把 `cli/talk.py scan_agents` 放 R1-1，与第一片 server 范围矛盾；claim 守卫归属不清；`GET roles` 的 `model.choice_id` 无可信来源 | §6.1 矩阵、§5.2 投影、实施计划 §3.2/§3.6/§3.7 统一；`choice_id` 明确来自创建操作映射并与当前绑定校验一致，否则 `null`/失配 |

**#214 已闭合且本稿保留的部分**（不重写）：F1–F6 六项（创建幂等语义、managed/imported 区分与拒绝优先、宿主 claim/report 骨架、独立策略表、模型目录连接维度与软下架、交付格式与模块引用纪律），以及模型目录连接维度唯一键、软下架 `retired_at`、固定分级取消矩阵、用户界面与原生登录边界。

---

## 1. 目标与非目标

### 1.1 目标

1. TALK 维护“已适配运行器 + 其可用模型选择”的登记事实，项目按 **运行器 → 模型选择 → 人工角色名称/介绍** 新增角色，并一键完成 TALK 身份、凭据、本地身份档、模型绑定、项目入册与启动前检查。
2. 同一运行器同一模型（不同连接）可重复创建多个**互相独立**的角色：独立 `member_id`、独立 TALK API Key、独立身份档/上下文；项目内角色名可重复出现于不同项目，且不因角色改名波及全局成员或其它项目。
3. 取消角色固定“决策/执行”分级，迁移覆盖数据、接口、身份档、提示词、启动校验、页面与相关测试；旧任务原文/快照不改写，原任务权限与独立复核保留。
4. 提供项目级“全部启动”、逐角色“启动/关闭服务/删除”；页面只展示人工名称、运行器、模型、介绍与服务启动结果（失败可看原因），任务空闲/执行中状态留在任务列表。
5. 区分“保存配置”与“启动服务”，区分 TALK 服务/桌面宿主退出与浏览器关页；明确进程/会话所有权，禁止只靠 PID 判定所有权。
6. **创建动作在服务端同库内原子且可幂等重放**；跨宿主文件步骤由持久作业恢复；凭据在任一失败点都有明确、可审阅的恢复路径（F1）。
7. **删除默认只作用于本项目角色**；全局成员禁用须以“本流程独占且无其它活跃引用”为证明；删除不引入自动整树强制取消（F2）。
8. **启动成功必须有该次启动专属的新就绪证明**，与世代/实例/宿主绑定，旧世代迟到上报不得污染新状态（F3）。

### 1.2 非目标（本合同不覆盖）

- **不重做** 已有 C1–C4 能力：`runner_registry` / `project_role_bindings` 两表、登记/绑定写读接口、任务 13 键绑定快照、只读消费工具与页面绑定投影。本合同在其上做加法，不改其语义与形状。
- **不重写** 全部终端与桌面容器；不把 TALK 变成模型执行框架，不接管原生推理循环。
- **不在本片解决崩溃清理**：宿主异常退出/断电/被强杀后的残留服务清理只登记为已知边界，不宣称已解决。
- **不改发起者主被动规则**：主被动只约束任务 `created_by` 发起侧，执行者/复核者不读模式（[INITIATOR_MODE_CONSUMER.md](../guides/INITIATOR_MODE_CONSUMER.md) §0）。
- **不实现** 自动登录官方订阅账号、不收集订阅用户名/密码、不臆测原生配置目录/认证可复用、不宣称 WorkBuddy 等桌面会话可无人值守反向控制。
- **不验证** 真实后端模型版本/额度/任务能力；`bound`、`启动成功` 都不等于这些已验证。
- **不引入** 删除角色时自动 `cancel-tree`、自动强杀、自动撤销共享身份凭据（见 §15 待授权后置边界 D1/D2）。

---

## 2. 事实基线与当前缺口（只读核验）

### 2.1 已有能力（合同复用，不改语义）

| 事实 | 证据（实际源码） | 指纹（sha256 前 16 位） |
| --- | --- | --- |
| `Member`：全局身份，`id` 主键、`kind`、`display_name`、`api_key` 唯一、`disabled_at` 软删 | `server/models.py:21-31` | `9b45ecc287a1796a` |
| `ProjectAgent`：按 `(project_id, member_id)` 的项目名册，含 `identity_path/soul_path/user_path/memory_pointer/business_role/decision_tier/capability_summary`；名册 sync 是**全量替换（先删后插）** | `server/models.py:132-155`；`server/routes/projects.py:643-682` | `9b45ecc287a1796a` / `dbbc97616b31e520` |
| `ProjectRoleDescription`：按 `(project_id, member_id)` 的角色说明，**独立于名册表**（sync 不抹掉） | `server/models.py:158-177`；`server/routes/projects.py:425-510` | 同上 |
| `RunnerRegistry`：全局运行器登记事实，`runner_id`/`runtime` 登记后不可改；`adapter_status` 只表示接入程度；`capabilities` 不参与权限/路由/执行判定；无 DELETE，停用走 `adapter_status=retired` | `server/models.py:420-445`；`server/routes/runners.py:1-130` | `9b45ecc287a1796a` / `fc5df561156313a2` |
| `ProjectRoleBinding`：按 `(project_id, member_id)` 的运行器/模型绑定行，独立于名册表；六维存储事实为 `runner_id`（派生 `runtime`）+ `model_source`/`provider_id`/`connection_ref`/`model_id`；`model_alias` 是**调用选择参数**，`model_display_name` 是纯展示 | `server/models.py:448-475` | 同上 |
| 六维内容指纹 `sha256(runner_id\|runtime\|model_source\|provider_id\|connection_ref\|model_id)`（不含 alias/display） | `server/models.py:680-711` | 同上 |
| 绑定读取阶梯 `member_missing→member_disabled→not_in_roster→not_agent→unconfigured→partial→runner_missing→runner_retired→bound`；写入 `PUT` 仅 human、last-write-wins、目标须在名册且未禁用 | `server/models.py:360-381,733-766`；`server/routes/projects.py:169-189,555-640` | 同上 |
| 任务绑定快照固定 13 键 `schema_version/snapshot_at/state/runner_id/runtime/model_source/provider_id/connection_ref/model_id/model_alias/model_display_name/binding_fingerprint/note` | `server/models.py:386-401` | 同上 |
| `AgentInstance`：bridge 上报实例 `id/member_id/runtime/status/host/pid/current_task_id/last_error`；`status ∈ {starting,online,idle,busy,stopping,offline,error}`；`PUT /api/instances/{instance_id}` 仅 agent、跨成员 403；`GET` 支持 `member_id`/`status` 过滤 | `server/models.py:180-193,1544-1583`；`server/routes/instances.py:25-78`；[MODULE_instances.md](MODULE_instances.md)（本任务唯一被读的模块文档） | `9b45ecc287a1796a` / `679d4b8a57c54c0c` |
| `AgentInstanceUpdate` 可选字段（`host/pid/current_task_id/last_error`）默认 `None`，路由对全部字段**无条件赋值** | `server/models.py:1547-1569`；`server/routes/instances.py:50-57` | 同上 |
| 角色页现有绑定投影（只读白名单字段 + 十态区分 + 未知不伪装） | `web/workspace.js:678-790` | `43099b2cfc044944` |
| 项目角色说明面板、角色列表与草稿纪律 | `web/workspace.js:354-616,618-676` | 同上 |
| 全局禁用语义：`Member.disabled_at` 非空即**全局**拒绝该 Key（不是项目级） | `server/auth.py:31-36` | — |
| 任务目标校验只核 `kind == "agent"`（**不查项目名册、不查归档**） | `server/routes/tasks.py:99-103`，调用点 `:1575`（create_task）、`:1770`（schedule） | `92d8107ae502f894` |
| 分级唯一**行为性**读取：`_can_exempt_review` 读 `ProjectAgent.decision_tier == "decision"` | `server/routes/tasks.py:111-121` | 同上 |
| 整树取消 `POST /{task_id}/cancel-tree`：取消**整棵树**全部非终态任务并把关联实例置 `idle` | `server/routes/tasks.py:1020-1055,2167-2200` | 同上 |
| 单任务取消 `POST /{task_id}/cancel`：仅发起者、仅 `queued`（未领取）任务 | `server/routes/tasks.py:2531-2560` | 同上 |
| 任务领取 `claim`/心跳/完成的 lease + claim_token CAS 先例 | `server/routes/tasks.py:1113-1122,1301-1344,2563-2690` | 同上 |
| 分级迁移前兼容事实：库列、接口字段、名册 sync、页面输出仍存在，但除 `tasks.py:121` 外均为存储/展示/模板，不是权限判定 | `server/db.py:274-281,306-317,336-339,363`；`server/models.py:93-95,150,1335,1387-1399,2181-2212,2416-2450`；`server/routes/groups.py:99,217-223`；`server/routes/projects.py:675`；`server/hall_types.py:20` | `82ee365b6741e16f` / `9b45ecc287a1796a` |
| Kimi K2.8 受控启动入口：离线检查 → 只读身份核验 → 固定 argv → 进程内 `asyncio.run(bridge)` | `scripts/kimi_k28_executor.py:1148-1237`，argv 构造 `:429-464` | `697bd39650a8ed60` |
| DSH 现有执行入口走通用 bridge（argv 传输、命令由入口决定），**不经过 `server/` 进程管理** | `bridges/cli_bridge.py`（argv/prompt 组装）；`rg 'Popen\|create_subprocess\|\.kill\(\|terminate\(\|psutil\|subprocess' server/` 无匹配 | — |
| 宿主侧脚本确有进程管理能力（`subprocess.Popen` + `terminate/kill`），但不在 `server/` | `scripts/dsh_talk_precheck.py:189-200`；`scripts/kimi_talk_precheck.py:267-278`；`scripts/dsh_acp_drive.py:159-185,427-432` | 见 `source_fingerprints.json` |
| `server/`（Web 服务）**没有任何进程启停能力** | 同上 `rg` 无匹配 | — |
| C2 收尾受信 plan/apply/verify 只做运行器登记 + 绑定写入，**不建成员、不建角色、不启进程** | `scripts/talk_adapter_registry.py:8-32`；`scripts/adapter_closeout.py:1-32` | `0698dd7999021169` / `161338b8b497e54c` |

> 措辞更正（F6）：原草稿写“全仓无进程管理”，实际应限定为 **`server/`（TALK Web 服务）无进程管理**；宿主侧 `scripts/` 已存在受控进程启停代码。本合同不在 `server/` 内引入进程管理。

### 2.2 当前缺口（本合同必须处理）

| # | 缺口 | 证据 |
| --- | --- | --- |
| G1 | `RunnerRegistry` 没有“可用模型选择”目录，登记 ≠ 完整原生模型清单 | `server/models.py:420-445`；`scripts/adapter_binding_facts.py:201-226` 只有 4 个适配 profile，无模型列表 |
| G2 | 没有“角色”身份记录：角色 = 成员 + 名册行 + 绑定行 + 说明行，缺人工角色名、创建操作归属与生命周期 | `server/models.py:132-177,448-475` |
| G3 | 新角色无创建接口：`Member` 需自注册/自带 Key，项目名册 sync 全量替换且要求预先存在的 profile 目录 | `server/routes/members.py:42-91`；`server/routes/projects.py:643-691`；`cli/talk.py:256-331` |
| G4 | `ProjectAgent.decision_tier` 仍是**实际权限输入**；且它挂在会被 sync 全量替换的名册表上 | `server/routes/tasks.py:111-121`；`server/routes/projects.py:643-682` |
| G5 | bridge 仍解析/注入/上报分级：argv、prompt、环境变量、讨论收口人选择、诊断 dump | `bridges/cli_bridge.py:113-147,905-910,958-971,2060-2061,2193-2200,2303-2310,2365-2371,3201,3541,3593,3687-3692` |
| G6 | 名册/群/页面/sync 仍读写 `decision_tier`（存储/展示，非判定） | `server/routes/groups.py:99,217-223`；`server/routes/projects.py:675`；`web/workspace.js:75-90`；`server/hall_types.py:20` |
| G7 | `Member.display_name` 是全局名，角色名无项目维度 | `server/models.py:26`；`web/workspace.js:48-54` |
| G8 | `AgentInstance` 无项目维度，实例 ID 全局主键；多项目同名成员无法按项目隔离运行状态 | `server/models.py:180-193`；`server/routes/instances.py:25-78` |
| G9 | 无服务生命周期协议：无 desired/observed、无启动动作、无 claim/report、无所有权 token、无该次启动就绪证明 | `server/routes/instances.py:25-62`；`server/` 无进程管理代码 |
| G10 | 绑定不改变实际 CLI 模型调用选择：`model_alias` 只是记录，启动 argv 由各自入口决定 | `server/models.py:455-457`；`scripts/kimi_k28_executor.py:429-464` 硬编码 alias |
| G11 | 一级页面缺“全部启动/启动/关闭服务/删除”，无服务结果投影与加载态 | `web/workspace.js:618-676` |
| G12 | 无创建幂等记录：同 key 重放无法证明原身份，响应丢失/宿主写 Key 失败后不可恢复 | `server/models.py` 无 operation 表；`server/routes/members.py:42-91` |
| G13 | 无独立于固定分级的权限持久源：任何挂在 `project_agents` 上的字段都会被 sync 抹掉 | `server/routes/projects.py:661-679` |
| G14 | 实例上报字段全量覆盖，旧心跳省略字段会抹 NULL；项目字段可被静默改写 | `server/models.py:1547-1569`；`server/routes/instances.py:50-57` |
| G15 | 删除角色会影响全局凭据与整棵任务树，且归档后仍可被派发 | `server/auth.py:31-36`；`server/routes/tasks.py:99-103,1020-1055,2167-2200` |

### 2.3 命名与路径核验纪律

本文件所有路径均由 `rg`/目录列举实际定位后引用；未在仓库中存在的文件一律不写入结论。被引文件 SHA256 另存 `source_fingerprints.json`（28 个原被引文件 + 本稿新增源码锚点）。**模块文档只读 `MODULE_instances.md`**；原草稿对 bridges 模块文档的引用已改为实际源码证据（F6）。

---

## 3. 概念模型

```
运行器(runner)                全局登记：RunnerRegistry（已适配产品/适配程度/控制能力）
  └── 模型选择(choice)        全局登记：runner_model_choices（连接维度唯一，稳定 choice_id）
项目角色(role)                项目内身份：project_roles（人工名称 + 生命周期归属）
  ├── 创建操作(operation)     服务端：role_creation_operations（幂等键 + 请求指纹 + 身份分配）
  ├── 成员(member)            Member（全局唯一 id + 独立 API Key）
  ├── 名册行(roster)          ProjectAgent（项目入册、身份档路径；sync 全量替换）
  ├── 模型绑定(binding)       ProjectRoleBinding（复用，runner_id + 模型六字段）
  ├── 角色说明(desc)          ProjectRoleDescription（复用）
  ├── 权限策略(policy)        project_role_policies（独立于名册的 review_exempt 持久源）
  └── 服务状态(service)       role_service_state / role_service_launches（desired/observed/世代/启动动作）
实例(instance)                AgentInstance（新增 project_id 维度、进程身份提示）
```

关键区分（本合同全篇遵守）：

- **配置事实**（登记、选择、绑定、角色、名册、策略）≠ **实例上报**（在线/空闲/忙碌）≠ **服务启动结果**（本流程受管启动动作成功/失败）≠ **实际执行证据**（真实模型版本/额度/任务能力）。四者分别存储、分别展示，任何一层都不外推下一层。
- **全局原生接入/登录**（运行器级）与 **项目角色身份配置**（项目级）分开：前者由用户在本机原生客户端完成，TALK 只提供入口与就绪检查，不代替也不收集订阅凭据。
- **角色身份**（TALK `member_id` + Key）与 **共享模型账号**（原生订阅/登录）不同：同一原生账号下可有多个独立 TALK 角色，是否共享原生认证/会话目录按运行器能力逐项核验，默认按隔离处理。
- **managed 独占身份**与**imported/共享身份**分开：只有前者可能随角色删除而全局禁用，且仍需显式授权与引用计数证明（§9）。

---

## 4. 数据模型设计

### 4.1 新增表

#### 4.1.1 `runner_model_choices`（运行器模型选择目录，F5 修正）

原草稿用 `runner_models(runner_id, model_id)` 联合主键 + upsert，会在同一 `model_id` 存在多个 `model_source`/`provider_id`/`connection_ref`（以及不同 `model_alias`）时用第二个连接覆盖第一个，而现有绑定六维事实明确区分这些维度。本稿改为**稳定选择 ID + 覆盖连接维度的唯一键**。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `choice_id` | TEXT | 主键 | 服务端生成的稳定不透明 ID，形如 `rmc_<12hex>`；**创建后永不重新指向另一组选择维度**，不复用 |
| `runner_id` | TEXT | 非空，索引 | 引用 `runner_registry.runner_id`；**不加外键级联**，运行器退役时选择行保留并按读取阶梯如实报告 |
| `model_id` | TEXT | 非空 | 运行器内稳定的模型标识；复用 `normalize_safe_identifier_token` |
| `model_source` | TEXT | 非空 | 复用既有 `MODEL_SOURCES`（`server/models.py:355-357`） |
| `provider_id` | TEXT | 非空 | 复用安全 token 规则 |
| `connection_ref` | TEXT | 非空 | 不透明标识，复用安全 token 规则 |
| `model_alias` | TEXT | 非空，默认 `''` | 原生调用选择参数；空串 = 该运行器不支持/不指定显式 alias。**属于选择维度**，改变即产生新 `choice_id` |
| `model_display_name` | TEXT NULL | ≤64 | 纯展示名，不参与指纹、不参与唯一键 |
| `source_kind` | TEXT | 非空，`declared`/`native_config`/`verified` | **来源等级**：人工声明 / 从原生配置只读读出 / 已核验。只描述来源，不表示可用 |
| `capabilities` | JSON | 默认 `[]` | 模型级能力标签，只作展示与后续能力矩阵，不参与权限/路由 |
| `retired_at` | TIMESTAMP NULL | — | **软下架**（F5/F6 已采纳：本片即定义，不物理删除）；非空 = 不再允许新角色选择，历史绑定不受影响 |
| `created_by` / `created_at` / `updated_at` | — | 非空 | 审计；`created_by` 不加外键（沿用 `runner_registry.created_by` 先例） |

- **唯一键（选择身份）**：`UNIQUE(runner_id, model_id, model_source, provider_id, connection_ref, model_alias)`。因此同 `runner_id` + 同 `model_id` 的不同 `provider_id`/`connection_ref`/`model_alias` **可并存**。
- **写入语义**：`POST` 先按唯一键查找；命中则只允许更新 `model_display_name`/`capabilities`/`source_kind`/`retired_at`，若请求试图改动任一选择维度 → `409 choice_dimension_immutable`（客户端应改为新建选择）。未命中则分配新 `choice_id` 并插入。并发插入撞唯一键 → 重查一次，仍冲突按 409。
- **不可变传播**：角色创建时把选择行的六个选择事实 + `runner_id` **复制**到 `project_role_bindings`（§4.2）。此后目录改名/改 alias/软下架/退役**不会**回写绑定行，不静默更换老角色的连接或 alias。
- **语义边界**：目录行只说明“TALK 登记过该选择”，不代表模型在线、可用、版本正确、额度充足或已获授权；`source_kind` 只记录来源等级，**不是能力验证**。
- **读取过滤**：`GET` 默认过滤 `retired_at IS NULL`；`?include_retired=true` 如实返回全部（供页面区分“已下架”与“从未登记”）。

#### 4.1.2 `project_roles`（项目角色身份与生命周期归属）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `project_id` | TEXT | 联合主键 | 项目 |
| `member_id` | TEXT | 联合主键 | 该角色的全局成员；**不加外键**（成员可能先于角色建/后于角色删） |
| `role_name` | TEXT | 非空，1–64 码点 | 人工角色名；**项目内唯一且仅在未归档时占用**（§4.4 部分唯一索引） |
| `origin` | TEXT | 非空，`managed`/`imported` | `managed`=经新流程创建；`imported`=历史名册登记补录（兼容旧项目） |
| `identity_exclusive` | INTEGER | 非空，默认 0 | 创建时记录：该成员是否由本流程独占（创建时全局仅此一条角色行）。仅 `managed + identity_exclusive=1 + 删除时活跃引用数=1` 才允许全局禁用成员（§9） |
| `credential_version` | INTEGER | 非空，默认 1 | 凭据版本；每次轮换 +1（§7.5） |
| `key_issued_at` / `key_rotated_at` | TIMESTAMP NULL | — | 凭据发行/轮换审计；**不存明文 Key** |
| `created_by` | TEXT | 非空 | 创建人（human） |
| `created_at` / `updated_at` | — | 非空 | 审计 |
| `archived_at` | TIMESTAMP NULL | — | 删除角色时**软归档**：保留历史归属，不物理删除成员/任务/消息 |

- **不做**：不在本表重复存 `runner_id`/`model_id`（绑定表是唯一事实来源），避免双源漂移。
- **兼容**：不存在本表行的历史名册角色仍出现在角色列表，`origin` 读取侧投影为 `imported` 且**不具备**生命周期操作；补录后才可管理。

#### 4.1.3 `role_creation_operations`（创建幂等与身份分配，F1 + R1 修正：进第一片）

原草稿把 `operation_key` 放在 R1-2 的 `role_provision_jobs` 且 `project_roles` 无该字段，导致第一片“逐步落库失败不回滚”后同 key 重放无法证明原身份（F1）。#214 修订稿引入 TX1/TX2 两阶段，但 TX1 独立提交的 `pending` 行在宕机后没有任何收敛路径，且 §7.2 与 §7.3 对 `pending` 重放的规定互相矛盾（R1）。本稿把**服务端同库部分**的幂等与身份分配收敛为**单一写事务（TX-ALL）**：没有独立提交的中间状态，因此不存在可永久 `pending` 的窗口。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `operation_key` | TEXT | 主键 | **调用方显式提供**的不透明幂等键（8–128 安全 token，推荐 `uuid4`）。**禁止**由名称/模型派生（派生键会把“删除后重建同名”误认成旧请求） |
| `request_fingerprint` | TEXT | 非空 | `sha256` 规范化请求载荷（见 §7.2） |
| `project_id` | TEXT | 非空，索引 | 目标项目 |
| `requested_role_name` | TEXT | 非空 | 归一化后的角色名 |
| `runner_id` / `choice_id` | TEXT | 非空 | 目标运行器与模型选择 |
| `member_id` | TEXT | 非空，索引 | 本操作提交时分配的身份；**行存在即代表提交完成**，不存在“分配中/NULL”状态 |
| `committed_at` | TIMESTAMP | 非空 | 提交时刻（与全部身份事实同一事务写入） |
| `created_by` / `created_at` / `updated_at` | — | 非空 | 审计 |

- **无状态列**：本表**没有** `status`/`error_code` 列。行 = 已提交操作；失败 = 没有行。这是 R1 的核心修正：不再存在任何需要人肉回收的 `pending`/`failed` 残行。失败原因只进服务端日志（稳定错误码 + `operation_key`），不落库、不参与幂等判定。
- **唯一约束**：`operation_key` 主键；另有 `UNIQUE(project_id, member_id)`（一个身份只对应一个创建操作），供 §5.2 的 `choice_id` 反查使用。
- **单写事务 TX-ALL**（§7.2）：一次 `BEGIN IMMEDIATE` 写事务内完成“读操作行 → 分配身份 → 写全部身份事实 → 写操作行”，统一 `COMMIT`。SQLite 单写者 + 主键/唯一约束保证并发同 key 只有一个赢家，输家读回已提交行。
- 该表**不是**跨宿主作业表；身份档文件与宿主 Key 文件属跨宿主步骤，由 R1-2 的 `role_provision_jobs` 承接（§7.6）。

#### 4.1.4 `project_role_policies`（独立于固定分级的权限持久源，F4 修正）

原草稿把 `review_exempt` 加到 `project_agents`，但名册 sync 是**先删后插**（`server/routes/projects.py:661-679`），旧客户端 payload 不含该字段 → 权限回落到默认 0。本稿把权限源放到**独立于名册表**的策略表（与 `project_role_descriptions`、`project_role_bindings` 同一先例）。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `project_id` / `member_id` | TEXT | 联合主键 | 归属角色；**不加外键**，离册/删成员后行保留（“离册保留、回册恢复”） |
| `review_exempt` | INTEGER | 非空，默认 0 | 复核豁免（对应原 `decision_tier=decision`）。0/1 |
| `source` | TEXT | 非空，`migration_decision_tier`/`human_grant`/`default` | 权限来源，可审计 |
| `granted_by` | TEXT NULL | — | 授予人（human）；迁移来源时为 NULL |
| `granted_at` / `updated_at` | TIMESTAMP NULL | — | 审计 |

- **一次性迁移**（§8.3）：表首次创建时，按当时 `project_agents.decision_tier='decision'` 写入 `review_exempt=1, source='migration_decision_tier'`。用独立迁移标记（`schema_migrations` 或同名标记行）保证 `init_db()` 重复执行**不重跑**、**不覆盖**后续人工修改。
- 新角色创建流程**不写本表** → 默认 `review_exempt=0`，不获得豁免。
- `_can_exempt_review`（`server/routes/tasks.py:111-121`）改为读本表（§8.4）。

#### 4.1.5 `role_service_state`（角色服务生命周期状态，R1-3 实现，本片定义）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `project_id` / `member_id` | TEXT | 联合主键 | 归属角色 |
| `desired_state` | TEXT | 非空，`stopped`/`running` | 人类意图（保存配置 ≠ 启动；默认 `stopped`） |
| `observed_state` | TEXT | 非空，`not_started`/`starting`/`running`/`stopping`/`stopped`/`failed`/`unknown` | 宿主证据收敛后的受管状态；`unknown` = 无法证明所有权/进程身份（§10.7），页面按“未知（不伪装）”展示 |
| `manager_kind` | TEXT | 非空 | 本次由谁管理：`cli_process`/`external_session`/`host_desktop` |
| `control_kind` | TEXT | 非空 | 运行器控制能力快照（§10.3），写入时从 `runner_registry.control_kind` 复制 |
| `generation` | INTEGER | 非空，默认 0 | 启动/停止世代号；每次启动/停止动作 +1，用**条件更新**互斥 |
| `current_launch_id` | TEXT NULL | — | 当前进行中的 `role_service_launches.launch_id` |
| `observed_instance_id` | TEXT NULL | — | 最近一次被本次启动证明就绪的实例 ID（`start` 就绪时写入）；`stop` 动作的 `expected_instance_id` 取自该值，无实例时用 `none_<12hex>`（§10.2） |
| `owner_host` / `process_launch_id` | TEXT NULL | — | 受管进程原 start 的领取宿主与动作 ID；start claim 时建立。stop 不覆盖此归属，即使 `current_launch_id` 已变为 stop。正常停服成功后清空；无法证明已停时保留供诊断，不重新认领 |
| `pid` | INTEGER NULL | — | 仅**诊断提示**，不用于所有权判定 |
| `process_started_at` | TIMESTAMP NULL | — | 进程启动时间提示，与 `pid` 组合用于宿主侧身份核对，**单独不足以判定** |
| `last_result` | TEXT NULL | — | 最近一次**启动动作**结果：`success`/`failed`/`stopped`（人工关闭记 `stopped`，**不是** `failed`） |
| `last_error_code` | TEXT NULL | — | 稳定错误码（§10.6） |
| `last_error_message` | TEXT NULL | ≤300 | 脱敏短说明，禁止写 Key/token/命令正文 |
| `started_at` / `stopped_at` / `updated_at` / `updated_by` | — | — | 审计 |

#### 4.1.6 `role_service_launches`（每次启动/停止动作的 CAS/幂等记录，R1-3 实现，本片定义）

R4 修正：动作必须显式区分 `start`/`stop`；`expected_instance_id` 由服务端在创建动作时**预分配**（不允许 NULL 让宿主随手上报一个同成员旧实例）；`launch_expires_at` 是本表一等列（#214 稿只被引用、未在 schema 出现）；claim 要持久化**领取人身份**与 host，report 必须回传并核验 claim token。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `launch_id` | TEXT | 主键 | 服务端生成的动作 ID（`uuid4`） |
| `project_id` / `member_id` | TEXT | 非空，索引 | 归属角色 |
| `action` | TEXT | 非空，`start`/`stop` | **动作类型**（R4）：`start` 求就绪 `ready`，`stop` 求 `stopped`；二者不再共用无语义动作 |
| `generation` | INTEGER | 非空 | 本动作所属世代；与 `role_service_state.generation` 严格对应 |
| `state` | TEXT | 非空，`pending`/`claimed`/`reported`/`expired` | 动作状态机 |
| `expected_instance_id` | TEXT | **非空** | start 预分配全新且不在库中存在的 `ins_<12hex>`；stop 沿用原 start 的实例 ID。无受管进程且可证明已停时直接幂等返回 stopped，不伪造占位实例；所有权未知则拒绝 `unknown_owner` |
| `target_start_launch_id` | TEXT NULL | — | stop 必填并指向 `role_service_state.process_launch_id`；与同 member/project 的原 start 记录绑定，不能拿新 stop token 认领旧进程 |
| `launch_expires_at` | TIMESTAMP | **非空** | 动作截止时刻（claim + report 都必须在 `claimed_at ≤ report_time ≤ launch_expires_at` 内）；缺列是 #214 的直接缺陷 |
| `claim_member_id` | TEXT NULL | — | 领取者身份（必须等于调用者；report 时二次核对，防止换人回报） |
| `claim_host` | TEXT NULL | — | 领取时宿主自报的稳定标识；与 `owner_host` 同源，不单独作为授权 |
| `claim_token_hash` / `owner_token_hash` | TEXT NULL | — | claim token 按动作新发；owner token **只在 start claim 生成**，stop 沿用原 start 的哈希并要求宿主提交已持有的明文，绝不重新发行原进程所有权（§10.2） |
| `first_instance_seen_at` / `report_fingerprint` | TIMESTAMP NULL / TEXT NULL | — | 服务端首次接收匹配的新就绪实例时间；回报载荷指纹用于验证同一回报重放，不允许靠相同 outcome 冒充同一载荷 |
| `claimed_at` / `reported_at` | TIMESTAMP NULL | — | 领取/回报时刻，用于时间窗校验 |
| `instance_id` | TEXT NULL | — | 就绪证明实际命中的实例（`start` 回报 `ready` 时等于 `expected_instance_id`） |
| `outcome` | TEXT NULL | `ready`/`failed`/`stopped` | 宿主回报结果（`start` 只允许 `ready`/`failed`；`stop` 只允许 `stopped`/`failed`） |
| `error_code` | TEXT NULL | — | 稳定错误码 |
| `created_at` / `updated_at` | — | 非空 | 审计 |

- **过期规则**：`launch_expires_at` 到期且未 `reported` → 服务端把该 launch 标 `expired`；**仅当** `role_service_state.current_launch_id == launch.launch_id` **且** `role_service_state.generation == launch.generation` 时才把 `observed_state` 收敛为 `failed`（`start`）/`unknown`（`stop`），`last_error_code='readiness_timeout'`（`start`）或 `stop_timeout`（`stop`）。过期旧动作**不得**污染新世代服务状态（R4）。
- **旧世代规则**：回报的 `generation` 与 `role_service_state.generation` 不一致，或 `current_launch_id != launch_id` → `409 stale_report`，只写审计，不改变状态（§10.5）。

### 4.2 已有表的加法改动（只增列/只加索引，不删列、不改类型）

| 表 | 新增 | 兼容策略 |
| --- | --- | --- |
| `runner_registry` | `control_kind TEXT NOT NULL DEFAULT 'unknown'`（`managed_cli`/`external_session`/`unknown`） | 旧行 `unknown`，页面按“未声明控制能力”展示，不自动视为可启动 |
| `agent_instances` | `project_id TEXT NULL`（+ 索引）、`process_started_at TIMESTAMP NULL`、`launch_id TEXT NULL`（+ 索引） | 旧行 `NULL`；`NULL` 表示“该实例未声明项目/无启动动作关联”，**不**回填猜测值。`launch_id` **一旦非空不可改写**（R4，§10.4）；不新增 `generation` 列，世代由不可变 launch 推导 |
| `project_agents` | **无新增**（`decision_tier` 列原值保留不动，只停止作为判定输入） | 名册契约不变；旧客户端 payload 继续可写 |
| `project_role_descriptions` | 无 | 复用不变 |
| `project_role_bindings` | 无 | 复用不变（模型选择事实的唯一事实来源；六维指纹与 13 键快照语义不变） |
| `group_members` | 无 | `decision_tier` 列原值保留，不再作为任何判定输入 |

迁移实现方式沿用 `server/db.py` 既有模式：`SQLModel.metadata.create_all` 建新表，`PRAGMA table_info` 判列存在后 `ALTER TABLE ... ADD COLUMN`（幂等、不重建表、不改数据），索引用 `CREATE INDEX IF NOT EXISTS`（先例 `server/db.py:306-317,340-359`）。部分唯一索引用 `CREATE UNIQUE INDEX IF NOT EXISTS`。

### 4.3 不变量

1. `project_role_bindings (project_id, member_id)` 的六个选择事实必须来自一次真实存在的 `runner_model_choices` 行（创建时复制）；不一致即 `partial`/拒绝，不静默改写；目录后续变更**不回写**绑定行。
2. 一个 `member_id` 在同一项目内最多对应一个未归档 `project_roles` 行；跨项目可由不同角色复用同一全局成员（历史 `imported` 场景），但**新流程创建的角色不复用成员**（`member_id` 冲突一律重取随机后缀，绝不复用不明旧成员）。
3. `role_service_state.observed_state` 只能由宿主上报或服务端按明确规则收敛；页面不得自行推导“已启动”。`success`/`ready` 必须同时具备：该次 `launch_id`（`action='start'`）、`expected_instance_id` 命中的**新**实例上报、世代一致、`claimed_at ≤ report_time ≤ launch_expires_at`。`stop` 只由 `action='stop'` 的回报收敛，且停止回报不得覆盖更新世代的结果。
4. 角色归档后：名册行移除、绑定行保留只读、说明保留、策略行保留但**权限休眠**（§8.4）、历史任务/消息/快照不改写；`Member.disabled_at` **仅在 §7.5 独占证明通过且显式请求时**设置。
5. `review_exempt` 只在 `project_role_policies` 中持久；但**策略事实 ≠ 当前可用权限**：读路径必须同时满足“当前 `ProjectAgent` 名册行存在 + 成员为未禁用 agent + 若存在 `ProjectRole` 则未归档”（R2，§8.4）。任何 sync/离册/归档路径都不得把 `decision_tier` 当作权限来源。
6. 创建角色的服务端写集合在**同一数据库事务（TX-ALL）**内原子提交；任一失败不得留下部分服务端事实，也不得留下 `pending` 行（§7.2）。
7. 凭据轮换/全局禁用前必须在**同一写事务**内证明身份独占：除本角色自身外的全部兼容引用路径活跃引用计数为 **0**，且无在用实例/服务/任务（R3，§7.5）。
8. 公共读取面（角色列表、成员列表、页面、日志、交付包）永不返回 `api_key`、`owner_token`、`claim_token` 或 Key 文件路径（§7.8）。

### 4.4 索引清单（新增）

- `UNIQUE INDEX ux_runner_model_choices_dim ON runner_model_choices (runner_id, model_id, model_source, provider_id, connection_ref, model_alias)`
- `INDEX ix_runner_model_choices_runner ON runner_model_choices (runner_id, retired_at)`
- `UNIQUE INDEX ux_project_roles_active_name ON project_roles (project_id, role_name) WHERE archived_at IS NULL`（SQLite 支持部分索引；归档后同名可重建）
- `INDEX ix_project_roles_member ON project_roles (member_id)`
- `INDEX ix_role_creation_operations_member ON role_creation_operations (member_id)`
- `UNIQUE INDEX ux_role_creation_operations_identity ON role_creation_operations (project_id, member_id)`（§5.2 `choice_id` 反查 + 一身份一操作）
- `INDEX ix_agent_instances_project_id ON agent_instances (project_id)`
- `INDEX ix_agent_instances_launch_id ON agent_instances (launch_id)`
- `UNIQUE INDEX ux_role_service_launches_generation ON role_service_launches (project_id, member_id, generation)`（同世代只有一个动作，start/stop 各自递增世代）
- `INDEX ix_role_service_launches_state_expiry ON role_service_launches (state, launch_expires_at)`（过期收敛扫描）

---

## 5. 接口设计（最小集）

统一沿用既有约定：`X-API-Key` 鉴权；human-only 写入口返回 403；`extra="forbid"`；未知资源 404；非法输入 422；除“创建/轮换一次性返回新 Key”外不返回任何凭据正文。所有稳定错误码为固定英文小写下划线串，便于测试锁定。

### 5.1 运行器与模型选择目录

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/runners` | 任意已认证 | **保持现有形状**（仅附加 `control_kind`），不内嵌模型；避免破坏 C3/C4 与页面 |
| `GET` | `/api/runners/{runner_id}/model-choices` | 任意已认证 | 返回选择目录数组（默认过滤 `retired_at`）；运行器不存在 404；空目录返回 `[]`（页面区分“未登记”与“登记为空”） |
| `POST` | `/api/runners/{runner_id}/model-choices` | **human** | 新建/复用一个选择（按选择维度唯一键 upsert）；`runner_id` 不存在 → 404；`retired` → 409 `runner_retired`；试图改动既有选择的维度 → 409 `choice_dimension_immutable` |
| `PATCH` | `/api/runners/{runner_id}/model-choices/{choice_id}` | **human** | 只允许改 `model_display_name`/`capabilities`/`source_kind`/`retired_at`；改选择维度 → 409；未知字段 422 |
| `PATCH` | `/api/runners/{runner_id}/control-kind` | **human** | 设置 `control_kind`；独立入口避免与既有 `PATCH /api/runners/{id}` 四字段白名单冲突 |

本片不提供选择物理删除（只软下架）。

### 5.2 项目角色

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/projects/{project_id}/roles` | 任意已认证 | 角色列表投影：`member_id`、`role_name`、`origin`、`archived`、`identity_exclusive`、`runner`（display/runtime/state）、`model`（`choice_id`/`choice_source`/display/alias/id）、`role_description`、`service`（desired/observed/last_action/last_result/error/native_login）、`identity`（`managed`/`imported`/`legacy`）。**不返回** Key、`owner_token`、`claim_token`、绝对路径、argv。`model.choice_id` 的可信来源见下方“投影来源” |
| `POST` | `/api/projects/{project_id}/roles` | **human** | 创建角色（保存配置，**不启动**）：`role_name`、`runner_id`、`choice_id`、`role_description?`、`operation_key`（必填）。返回创建结果 + **一次性** `api_key`。幂等与冲突语义见 §7.2 |
| `PATCH` | `/api/projects/{project_id}/roles/{member_id}` | **human** | 改 `role_name` / `role_description` / `review_exempt`（R2：豁免只能由 human 经此入口授予/撤销）；**默认不改** `members.display_name`（已采纳方向，不再作为待决项） |
| `POST` | `/api/projects/{project_id}/roles/{member_id}/rotate-key` | **human** | 凭据轮换：仅限本流程 `managed` 且事务内证明独占的身份；生成新 Key 并**一次性返回**，`credential_version+1`，旧 Key 在同一事务内失效（§7.5） |
| `GET` | `/api/projects/{project_id}/roles/{member_id}/tasks` | 任意已认证 | 只读：该角色在项目内的非终态任务清单（删除前置检查的任务处理入口索引；不改任务） |
| `DELETE` | `/api/projects/{project_id}/roles/{member_id}` | **human** | 删除角色（软归档）；在途任务或运行中服务默认拒绝。顺序、竞态与全局禁用条件见 §9 |

**`model.choice_id` 投影来源（显式创建/补录操作映射，不靠model_id猜测）**

角色表**不存** `choice_id`，绑定表也**不加**新列（保持 C1–C4 与 13 键快照语义不变）。投影按下列优先级解析，并在响应中显式给出 `choice_source`：

| 情形 | `choice_source` | `choice_id` | 判定规则 |
| --- | --- | --- | --- |
| 本流程创建的角色 | `creation_operation` | 创建操作的 `choice_id` | 按 `(project_id, member_id)` 读 `role_creation_operations`；若命中，再校验该 `choice_id` 当前行的六维事实（`runner_id`+`model_source`/`provider_id`/`connection_ref`/`model_id`/`model_alias`）与当前 `project_role_bindings` 行**完全一致** |
| 创建操作命中但绑定已被手工改写 | `creation_operation_mismatch` | `null` | 六维事实不一致时**不**返回旧 `choice_id`（避免用过期选择冒充当前绑定），置 `null` 并置 `model.choice_binding_mismatch=true` |
| 已显式补录的存量角色 | `legacy_attach` | 补录操作的 `choice_id` | 按(project_id,member_id)读取role_legacy_attach_operations，且选择行与当前绑定六维精确相等 |
| 补录映射失配，或同身份同时出现创建/补录映射 | `legacy_attach_mismatch` | `null` | choice_binding_mismatch=true，不任选一条通过 |
| 历史名册/手工绑定（无创建或补录操作行） | `legacy_manual` | `null` | 如实置null，不按model_id反查或猜测 |

- **不做**“按 `(runner_id, model_id)` 六维反查目录取行”的猜测：同一 `model_id` 可并存多个连接，反查会命中歧义（这正是 F5 修正的维度）。宁可为 `null` 也不猜。
- 该字段纯投影；不影响 `project_role_bindings` 的六维事实、任务 13 键快照与 `binding_fingerprint`。

### 5.3 服务生命周期（R1-3 实现，本片定义完整契约）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/projects/{project_id}/roles/{member_id}/service/start` | **human** | 请求启动；CAS 递增 `generation` 并建 `action='start'`、`state='pending'` 的 launch（服务端**预分配** `expected_instance_id` 与 `launch_expires_at`），返回 `{launch_id, generation, action:'start', expected_instance_id, launch_expires_at}`；**不返回任何 token** |
| `POST` | `/api/role-service-launches/{launch_id}/claim` | **该角色的 agent 成员**（或 human 宿主） | 宿主领取动作；请求体 `{host, expected_instance_id, owner_token?}`，其中实例 ID 须匹配；start 无 owner_token，stop **必须**携带原 start 的 owner_token 并核对原 host；CAS 只允许 `pending`→`claimed` 且未过期；返回 `{owner_token, claim_token, claimed_at, launch_expires_at, command:{action, runtime, runner_id, model_alias, project_root, member_id}}`（start 返回两个 token；stop 只返回新 claim_token，owner_token 沿用宿主原持有值） |
| `POST` | `/api/role-service-launches/{launch_id}/report` | 同上 | 宿主回报 `{generation, action, claim_token, owner_token, outcome, instance_id?, pid?, process_started_at?, host, error_code?}`；CAS 校验 **launch+世代+action+领取身份+host+claim_token 哈希+时间窗**；`start` 只收 `ready`/`failed`，`stop` 只收 `stopped`/`failed` |
| `POST` | `/api/projects/{project_id}/roles/{member_id}/service/stop` | **human** | 请求关闭；CAS 递增世代并建 `action='stop'`、`state='pending'` 的 launch（`target_start_launch_id` 指原 start，实例 ID 沿用原 start；无受管进程且已停则幂等返回；所有权未知则拒绝）；人工关闭成功记 `stopped`，**不记失败** |
| `POST` | `/api/projects/{project_id}/role-services/start-all` | **human** | 全部启动：**跳过已运行/启动中角色**，返回逐角色结果与部分失败清单；失败可只重试失败子集（`member_ids` 过滤） |
| `GET` | `/api/projects/{project_id}/role-services` | 任意已认证 | 只读状态投影（供页面轮询/刷新）；**不含** owner_token/claim_token/argv/绝对路径 |

服务动作的执行者是**宿主侧服务管理器**（§10.1）。服务端只记录 `desired_state`、世代与宿主回报的 `observed_state`；服务端自身**不** spawn/kill 进程。

### 5.4 实例上报扩展

| 方法 | 路径 | 变更 | 兼容 |
| --- | --- | --- | --- |
| `PUT` | `/api/instances/{instance_id}` | body 新增可选 `project_id`、`launch_id`、`process_started_at`；改为**只赋值请求中显式出现的字段**（`model_fields_set`） | 旧 bridge 不传 → 新建行为 `NULL`；**已存在行省略字段保持原值**；项目已声明后不可静默改写（§10.4） |
|  |  | `launch_id` 只允许“`NULL`→某值”或“同值重复”；已存在非空 `launch_id` 改为另一值 → `409 instance_launch_immutable` | 旧实例**不能**被重新贴上本次 `launch_id` 冒充就绪（R4，§10.4） |
| `GET` | `/api/instances` | 新增可选 `project_id` 过滤 | 旧调用不传 → 现有行为 |

---

## 6. 取消固定“决策/执行”分级：迁移合同

原则：**先停用判定、再兼容保留、最后才谈清理**；本 R0 **不物理删列**，也不靠隐藏控件宣称完成。旧任务原文、任务快照、历史消息一律不改写。

### 6.1 迁移范围矩阵

| 层 | 现状证据 | 目标动作 | 所属片 |
| --- | --- | --- | --- |
| 数据-权限源 | `server/routes/tasks.py:111-121` 读 `project_agents.decision_tier` | 新建 `project_role_policies` 并一次性从旧值回填；此后只读 `review_exempt` | R1-1 |
| 数据-`project_agents.decision_tier` | `server/models.py:150`；`server/db.py:312-313,336-339` | 保留列与旧值；sync 继续可写；**不再作为任何判定输入** | R1-1（读路径） |
| 数据-`group_members.decision_tier` | `server/models.py:95`；`server/db.py:280-281,363` | 保留列与旧值；不再作为任何判定输入；群成员接口字段标注 deprecated | R1-1（读路径） |
| 接口-名册 sync（服务端） | `server/models.py:2181-2212`；`server/routes/projects.py:665-679` | `ProjectAgentEntry.decision_tier` 保持可选兼容字段：接受旧值并原样存储（旧客户端不 500），不要求、不判定 | R1-1（服务端输入兼容） |
| 接口-名册 sync（CLI） | `cli/talk.py:256-293,299-323` | `scan_agents` 不再因缺失/冲突分级报错；**不列入 R1-1**（保持第一片为 `server/` 范围），随 bridge/页面片收尾 | R1-2 |
| 接口-输出 | `server/models.py:1335,1387-1399,2416-2450`；`web/workspace.js:75-90` | 输出字段保留但标注历史兼容；不再出现在页面主显示 | R1-2（页面） |
| 身份档 | `.talk/groups.yaml` 每成员 `decision_tier` | 兼容阶段继续读取不报错；bridge 不再据此注入或上报；提示用户后续可删除该键（本片不代删文件） | R1-2 |
| 提示词/模板 | `bridges/cli_bridge.py:1227-1228,2060-2061,2193-2200,2303-2310,2365-2371`；`server/hall_types.py:20` | 删除“决策 Agent/执行 Agent”注入；改为任务职责说明 | R1-2 |
| 启动校验 | `bridges/cli_bridge.py:113-147,3541,3687-3692`；`scripts/kimi_k28_executor.py:444-464,1229-1235`；`scripts/adapter_closeout.py:398-426` | `--decision-tier` 变为**已弃用兼容参数**（接受、忽略、不再回读 groups.yaml、不再因缺失回退 `execution`）；固定 K28 入口移除固定执行分级合同与漂移阻断；`TALK_DECISION_TIER` 不再注入 | R1-2 |
| 讨论收口人 | `bridges/cli_bridge.py:905-910` | 不再按分级选人；收口人按发起者/显式 `escalate_to_human` 与既有 stance 规则 | R1-2 |
| 权限 | `server/routes/tasks.py:111-121` | `_can_exempt_review` 改读 `project_role_policies.review_exempt` | R1-1 |
| 页面 | `web/workspace.js`（绑定/角色区）；`web/app.js` 若有分级展示 | 主显示不再出现分级；不保留“隐藏但可被 XSS/旧接口调用”的伪迁移 | R1-2 |
| 测试 | `tests/test_groups.py`、`tests/test_cli_bridge.py`、`tests/test_talk_cli.py`、`tests/test_kimi_k28_executor.py`、`tests/test_adapter_closeout.py`、`tests/test_project_*` | 新增“无分级依赖”断言；旧断言改为兼容语义 | 各片 |

### 6.2 阶段划分（按片可执行，F4 修正）

| 阶段 | 内容 | 数据影响 | 回滚方式 | 授权状态 |
| --- | --- | --- | --- | --- |
| **R0（本稿）** | 只交付两份合同与证据，**不改任何代码/数据** | 无 | 无 | 本次已授权（文档） |
| **阶段 A** | 由 R1-1（后端读路径）与 R1-2（bridge/提示词/启动校验/页面）两片组成；停用全部行为性判定，旧列/旧字段/旧参数保留但不再参与任何权限、路由、执行或提示 | 只**新增**表与一次性迁移行；不改写既有列/行 | 代码回退即恢复旧行为；新增表可留存不读 | R1-1/R1-2 已实现并独立复核；未操作生产迁移/重载 |
| **阶段 B** | 确认无生产消费者后，清理页面字段与接口字段、归档旧列 | 物理删列/清字段 | 需备份 | **未授权，本 R0 不进入** |

**对原草稿事实口径的更正（F4）**：原稿在阶段 A 处写“判定路径全部切换……数据零改写”，且在 R1-1 处写“server 行为分级清零”。准确口径是：

- R0 阶段**没有任何判定被切换**，也没有任何数据改写；R0 只是文档。
- 阶段 A 的“服务端行为性判定清零”= 切换 `server/` 内**唯一的行为性读取** `server/routes/tasks.py:111-121`；`server/` 其余 `decision_tier` 出现位置（`db.py` 列定义/索引、`models.py` ORM 与兼容 schema、`routes/groups.py:99,217-223` 群成员读写、`routes/projects.py:675` 名册 sync 入参存储、`hall_types.py:20` 可读模板文案）均**不是任务权限判定**，按片分别处理（模板文案属 R1-2）。
- “数据零改写”只对**既有列/行**成立；阶段 A 会**新增**迁移行（`project_role_policies` 的一次性回填），必须如实登记为新增而非改写。

### 6.3 失效旧配置处理

- 数据库旧值：只作为 `review_exempt` 的**一次性**迁移来源，保留原位，不删除、不改写。
- `.talk/groups.yaml` 旧键：兼容阶段读取不报错；用户可自行删除，TALK 不代删。
- `--decision-tier` 旧 argv：接受并忽略；显式传入与本地配置冲突**不再报错**（因为不再读取本地配置）。
- 旧任务包/快照中的分级文本：不改写，按历史事实解释。

### 6.4 可验证完成标准（逐片）

**R1-1（后端片）**

1. 全仓 `rg 'decision_tier'` 在 `server/` 中的**行为性**使用为零：唯一允许出现的位置是①列/索引定义与幂等迁移、②兼容输入/输出字段声明与序列化、③一次性迁移回填逻辑、④注释/文档/测试历史说明。`server/routes/tasks.py` 不再出现对 `decision_tier` 的读取。
2. `tasks.py` 复核豁免读路径为 §8.4 的四条件合取（策略行 `review_exempt=1` **且** 当前 `ProjectAgent` 名册行存在 **且** 成员为未禁用 agent **且** `ProjectRole` 若存在则未归档）；旧库迁移后，原 `decision_tier='decision'` 成员豁免行为不变，其它成员不获得新权限，离册成员**不**享受豁免。
3. 迁移两次幂等：`init_db()` 连跑两次，策略表迁移行只出现一次，不改既有表/行。
4. 全量 sync 两次（旧客户端 payload 不含 `review_exempt`）后，在册成员豁免权限不变；改旧 `decision_tier` 不重授/不撤销。
5. 新建角色无策略行 → 不获得豁免；离册 → 权限休眠；回册 → 按原策略行恢复；归档 → 权限休眠（策略行保留）。
6. **创建 TX-ALL 原子性**：在 TX-ALL 的每一个写步骤注入异常，断言 `members`/`project_roles`/`project_agents`/`project_role_bindings`/`project_role_descriptions`/`role_creation_operations` 六处均无残留；同 key 重试成功；不存在 `pending` 行（§7.7）。
7. **凭据轮换独占证明**：`rotate-key` 对 imported/共享、仅旧名册引用、在用实例/服务/任务、并发新增引用的场景全部给出稳定拒绝码；独占身份轮换成功且旧 Key 立即失效（§7.5）。
8. **归档守卫落点**：`server/routes/tasks.py` 的创建守卫（`_ensure_target_agent`）与领取守卫（`claim_task`）都在 R1-1 实现并测试；R1-1 无归档入口，用直接构造归档数据的测试覆盖（R5）。
9. `PUT /api/instances` 的 `launch_id` 不可改写；`expected_instance_id` 不匹配的上报不产生就绪（§10.4）。

**R1-2（bridge/页面片）**

6. bridge 不再生成“决策 Agent/执行 Agent”文本，不再注入 `TALK_DECISION_TIER`，不再读 `.talk/groups.yaml` 的分级。
7. K28 启动入口不再因分级漂移阻断；同一条 argv 在有无 `--decision-tier` 时行为一致。
8. 页面主显示无分级字段；旧字段若仍在接口，必须明确标注 deprecated 且有测试锁定“改了分级不影响任何权限”。
9. 旧任务原文/快照字节不变（抽样比对 sha256），历史消息/任务归属不变。

---

## 7. 一键配置：保存与启动分开（F1 修正）

### 7.1 责任边界

- **服务端同库原子部分（R1-1）**：Member / `project_roles` / 名册行 / 绑定行 / 角色说明 / 创建操作记录。全部在**同一个写事务（TX-ALL）**内提交，无独立提交的中间态。
- **跨宿主步骤（R1-2）**：本地身份档文件、宿主密钥库文件、启动前检查。由持久作业 `role_provision_jobs` 恢复，**不**假定与数据库同事务。

### 7.2 服务端单写事务创建与幂等（R1-1，R1 修正）

**协议选择**：本稿采用 #215 给出的第一个方向——“**单写事务里原子写操作状态 + 写全部身份事实 + 写 `committed`**”，不采用带执行世代/租约的两阶段恢复。理由：两阶段方案里那行**独立提交的 `pending`** 本身就是永不收敛的窗口；若要带租约回收，还要再定义“谁有权回收、回收时旧执行者是否还活着”，而本流程的服务端写集合全部在同一 SQLite 库、同一进程内，没有必须保留的跨库/跨 HTTP 中间态，单事务已经足够且更可测。

**TX-ALL 步骤**（一次 `BEGIN IMMEDIATE` 写事务）：

1. 校验 human 身份、请求结构、`operation_key` 和名称/介绍长度，计算指纹。事务内先查已提交操作（步骤 3），**命中时不因目录后来下架或角色改名/归档而重建或拒绝原请求**；只回原身份的当前只读投影、不回 Key。未命中才在同一写事务内复查项目、runner、choice 存在且可选，并确认 choice 属于请求 runner。
2. 计算 `request_fingerprint = sha256(canonical({project_id, role_name_normalized, runner_id, choice_id, role_description_or_empty, fingerprint_version}))`。
3. 事务内 `SELECT role_creation_operations WHERE operation_key=?`：
   - **命中**：指纹不一致 → `409 operation_key_conflict`；指纹一致 → `200 {role, member_id, reused:true}`，**不返回 Key**。直接结束，不写任何东西。
   - **未命中**：继续第 4 步。
4. 分配 `member_id`（§7.3；主键冲突重取随机后缀）与 `api_key`。
5. 同一事务内写全部事实：`members`、`project_roles`、`project_agents`（名册行）、`project_role_bindings`（从选择行复制六维 + `runner_id`）、可选 `project_role_descriptions`、`role_creation_operations`（`member_id` + `committed_at`）。
6. `COMMIT` → `201 {role, member_id, api_key, reused:false, credential_version:1}`（Key 仅此一次）。

**异常路径**：第 4–6 步任意异常 → `ROLLBACK` → 六张表**零残留**，操作表**没有行**；返回 4xx/5xx + 稳定错误码，并把 `(operation_key, error_code)` 写服务端日志。客户端可用**同 key 同载荷**直接重试，等价于首次调用。

**并发与幂等**：`BEGIN IMMEDIATE` 让写事务互斥；后到者要么在第 3 步读到已提交行（`reused`），要么在第 5 步撞 `operation_key` 主键 / `UNIQUE(project_id, member_id)` → 回滚 → 重读 → `reused`。因此**不可能出现“两个身份”，也不可能让旧执行者覆盖新提交**：旧执行者若在别人已提交后才完成自己的插入，其插入必然违反唯一约束而整体回滚。

**#215 点名的四类宕机/并发场景在本协议下的精确结果**

| #215 场景 | #214 两阶段下的问题 | 本协议结果 |
| --- | --- | --- |
| TX1 后宕机（操作行已独立提交 `pending`，身份未写） | 永久 `pending`；且 §7.2 要求重放 409、§7.3 又要求重试 TX2，直接矛盾 | **不存在 TX1**：没有独立提交的中间态。宕机 = 事务未提交 → 无操作行、无身份，重放即首次执行 |
| TX2 中宕机 | 事务回滚，但可能来不及写 `failed`，留下 `pending` | 单事务由 SQLite 原子回滚；进程被强杀也不会留下半写事实或 `pending` 行；重放成功 |
| 失败标记前宕机（回滚后、置 `failed` 前） | 永久 `pending` | **没有“失败标记”阶段**：失败即无行，不存在需要回收的失败态 |
| 两个 `failed` 恢复并发 | 主键冲突只让第二个插入失败，不保证已提交事实与失败行串行化，执行权不明 | **不存在 `failed` 行**。两个同 key 并发 = 两个 TX-ALL；`BEGIN IMMEDIATE` + 唯一约束决定唯一赢家，输家重读命中已提交行 → `200 reused`；任一时刻最多一个身份 |

- 三条不变量：**永不永久 `pending`**、**永不双身份**、**旧执行者永不覆盖新提交**。
- **凭据丢响应的轮换恢复保留**（§7.4/§7.5）：提交后响应丢失或宿主写 Key 文件失败，仍由 human `rotate-key` 生成新 Key 一次性返回。
- **同 key 异载荷**：`409 operation_key_conflict`，不建任何新事实。
- **归档后同名重建**：部分唯一索引只约束未归档行，归档后同名可创建，且**必然获得新 `member_id`**；旧归档行的名称、历史、绑定、说明保留。

### 7.3 命名、身份与凭据分配规则（R1-1 落地）

- `operation_key` 由调用方显式提供（8–128 安全 token，推荐 `uuid4`）；**禁止**由名称/模型派生——派生键会把“删除后重建同名”误认成旧请求。
- `role_name` 先 `strip()`；空白 → `422 role_name_invalid`；1–64 Unicode 码点，纯中文合法；**项目内唯一且仅在未归档时占用**，不做全局唯一。
- `member_id`：`agent:<project_slug>.<role_slug>-<8hex>`；slug 由 `role_name` 归一化（NFKC、小写、非 `[a-z0-9]` 折叠为 `-`、截断；**全中文/空 slug 回退 `role`**），`8hex = secrets.token_hex(4)`。主键冲突 → **重取后缀**（最多 8 次）→ `member_id_allocation_failed`；**绝不复用**已存在成员。
- `api_key = secrets.token_urlsafe(32)`；唯一列冲突重试（最多 8 次）→ `api_key_generation_failed`。服务端**不保存明文 Key 供再次读取**（§7.8）；本片**不**把 `Member.api_key` 升级为哈希列（见 §15.2 D7）。
- `project_roles.identity_exclusive` 在创建事务内计算：该 `member_id` 在 `project_roles` 中仅此一行（未归档）时为 1，否则 0。它是后续轮换/全局禁用独占证明的**持久标记**，一旦为 1 即受 §7.5 的引用守卫保护。
- `request_fingerprint` 参与项固定为 `{project_id, role_name_normalized, runner_id, choice_id, role_description_or_empty, fingerprint_version}`；`role_description` **进入指纹**（同 key 改介绍 = 异载荷 → 409），并在 TX-ALL 内写 `project_role_descriptions`。

### 7.4 凭据保管与失败点恢复（F1，R1 收敛后）

现有事实：`Member.api_key` 是**明文列**、唯一索引（`server/models.py:21-31`），`MemberOut` 不返回 Key（`server/models.py:1220-1226`）；agent 自注册要求自带 Key（`server/routes/members.py:42-91`）。

本设计：角色创建由**服务端生成**随机 Key，只在创建（或轮换）响应中**返回一次**；服务端**不保存明文 Key 供再次读取**，后续 `GET` 一律不返回。**口径澄清（R3）**：这**不**改变 `Member.api_key` 的明文认证存储列，本片**不**做凭据哈希迁移；禁止的只是“**额外**的重放存储”与“GET 再次取明文”。

| 失败点 | 当时状态 | 可恢复交付机制 |
| --- | --- | --- |
| 预检失败 / TX-ALL 回滚 | 六张表零残留，无操作行 | 修正输入后**同 key 同载荷**重试（等价首次），或换新 key 重发 |
| TX-ALL 提交后、HTTP 响应未到宿主 | 成员与 Key 已存在，宿主**不知道** Key | human 调 `rotate-key`（§7.5）生成**新** Key 并一次性返回；旧 Key 同事务失效；返回 `credential_version+1` |
| 响应到达、宿主写 Key 文件失败/中断 | 同上 | 同上 `rotate-key` |
| Key 文件已写、`GET /api/members/me` 身份不匹配 | 宿主持有一个失效/错误 Key | 先核对 `member_id`；确认后 `rotate-key`，再重跑身份核验 |
| Key 文件已写且身份核验通过 | 步骤完成 | R1-2 作业记录宿主 ACK（`role_provision_jobs`），不再重复发行 |

**明确拒绝的方案（待授权后置边界 D3）**：把生成的明文 Key 加密存库以便“重放也返回同一 Key”。理由：仓库无密钥管理/加密基础设施，留存明文或自造加密都会扩大静态凭据面；且“同一 Key 可重复取回”本身是新的凭据读取入口，需要单独授权。

- **不可按随机 member 冲突复用不明旧成员**：见 §7.3；冲突只换后缀，不认领既有行。
- **公共面不露凭据**（§7.8）。

### 7.5 凭据轮换与独占引用证明（R3 修正）

`POST /api/projects/{project_id}/roles/{member_id}/rotate-key`（human）**不是**通用“全局凭据管理”入口，而是“**尚未完成配置的 managed 独占身份的凭据恢复**”。它必须在**同一写事务（`BEGIN IMMEDIATE`）**内完成“证明独占 → 换 Key → 递增 `credential_version`”，证明与写入之间不存在可被并发引用插入的窗口。

**前置资格（不满足即拒绝，不进入证明）**

| 条件 | 不满足时的稳定拒绝码 |
| --- | --- |
| 目标 `(project_id, member_id)` 有 `project_roles` 行且 `archived_at IS NULL` | `404 role_not_found`（无行）/ `409 role_archived`（已归档） |
| `project_roles.origin == 'managed'` | `409 rotate_not_managed_identity`（imported/共享身份不走本流程全局凭据） |
| 目标成员 `kind == 'agent'` 且 `disabled_at IS NULL` | `409 rotate_member_not_agent` / `409 rotate_member_disabled` |
| 创建事实 `identity_exclusive=1`，且实时引用证明也通过 | `409 rotate_shared_identity_refused` |

**独占引用证明 `_prove_exclusive_identity(project_id, member_id, session)`（事务内计算，返回引用清单）**

必须枚举**全部兼容引用路径**，不能只用新表自证。计数口径（目标 `(project_id, member_id)` 自身的那一行不算引用）：

| 引用类别 | 数据来源 | 说明 |
| --- | --- | --- |
| 其它项目角色 | `project_roles WHERE member_id=? AND archived_at IS NULL AND project_id<>?` | 新表引用 |
| **旧 ProjectAgent 名册（兼容路径）** | `project_agents WHERE member_id=? AND project_id<>?` | **R3 明确要求不能漏**：未采用新角色表的项目名册行同样是活跃引用 |
| 旧名册同项目行的存在性 | `project_agents WHERE member_id=? AND project_id=?` | 必须存在（否则名册已被 sync 移除，身份处于离册态） |
| 绑定/说明跨项目 | `project_role_bindings` / `project_role_descriptions WHERE member_id=? AND project_id<>?` | 关联在用事实 |
| 群成员（跨项目或全局群） | `group_members JOIN groups`，`groups.project_id IS NULL OR groups.project_id<>?` | 全局群或其它项目群会因全局禁用/换 Key 受影响 |
| 在用实例 | `agent_instances WHERE member_id=? AND status IN ('starting','online','idle','busy','stopping')` | 运行中服务 |
| 在用服务状态 | `role_service_state WHERE member_id=? AND (desired_state='running' OR observed_state IN ('starting','running','stopping'))` | 运行中受管服务 |
| 在途任务 | `agent_tasks WHERE (target_member_id=? OR created_by=?) AND status IN ('queued','running')` | 执行侧与发起侧都可能使用该 Key |

- 判定：上表前五类“引用”总数必须为 **0**（即除本角色自身外无任何活跃引用），且后三类“在用”必须全部为空。否则拒绝，并返回**分类清单**（不含凭据）。

| 拒绝场景 | 稳定拒绝码 |
| --- | --- |
| imported/共享身份 | `rotate_not_managed_identity` |
| 存在其它项目角色引用 | `rotate_shared_identity_refused` |
| 仅存在旧 `project_agents` 名册引用（未采用新角色表） | `rotate_legacy_roster_reference_refused` |
| 名册行已被 sync 移除（离册态） | `rotate_identity_off_roster` |
| 存在运行中实例/服务或在途任务 | `rotate_identity_in_use` |
| 群成员在其它/全局群 | `rotate_group_reference_refused` |

**成功路径**：单事务内 `UPDATE members SET api_key=<新随机>`；`UPDATE project_roles SET credential_version=credential_version+1, key_rotated_at=now`；响应**一次性**返回新 Key。旧 Key 立即失效（`api_key` 唯一列）。响应丢失时重跑轮换即可（任一时刻只有一个有效 Key，不存在“两个 Key 并存”窗口）。

**并发引用新增场景（R3 明确要求）**：

1. 引用新增写路径（名册 sync、绑定写入、角色创建、任务创建、群成员写入）与 `rotate-key` 都由 SQLite 单写者串行化。
2. `rotate-key` 在 `BEGIN IMMEDIATE` 内**先证明后写入**：并发引用若先提交，证明会看到它并拒绝；若后到，则它在 `rotate-key` 提交前无法写入（写锁），提交后才写入——此时身份已轮换为独占身份，见下一条。
3. **新受管身份的项目引用守卫**：`identity_exclusive=1` 的新身份只归属创建项目。R1-1 在名册 sync、绑定/说明写入、任务创建（含发起者与目标、子任务的实际根项目、计划任务派生）以及群创建/成员新增这些写路径检查：引用项目须等于身份项目；跨项目或全局引用拒绝 `409 identity_exclusive_reference_refused`。校验与新增写入在同一写事务中，不能只在事务外预检。**历史无 ProjectRole 或 imported/非独占成员保留旧行为**；不禁止历史共享身份。由 `server/models.py` 共享查询函数供各路由复用，确切源范围为七文件（含 `server/routes/groups.py`）。
4. **同一完整证明复用于删除侧的可选全局禁用**（F2/R3）：`DELETE /roles/{member_id}?disable_member=true` 调用同一个 `_prove_exclusive_identity`；证明不通过一律拒绝（`shared_identity_disable_refused` / `global_disable_requires_exclusive`），绝不因为“删除了本项目角色”就顺手全局禁用共享凭据。
5. **默认拒绝 imported/共享与在用服务/实例/任务轮换**；本流程不做全局凭据管理。R1-1 尚无 `role_service_state` 表，该项记为“服务协议未实施”，**不查询不存在的表、不生成虚假服务证据**；实例与任务仍必须实查并拒绝在用身份。未来服务表存在后，同一证明必须补查其中的在用事实；首片测试可构造未来表核验这个兼容分支。该能力边界见 §15.2 D7。

### 7.6 跨宿主作业（R1-2，承接 F1 的宿主部分）

`role_provision_jobs`（R1-2 新增）：

| 字段 | 说明 |
| --- | --- |
| `operation_key` | 主键；**复用** R1-1 创建操作的 key，作为跨宿主步骤的恢复锚点 |
| `project_id` / `member_id` | 目标角色 |
| `status` | `pending`/`running`/`succeeded`/`partial`/`failed` |
| `steps` | JSON：`profile`（身份档）/`key_file`（宿主密钥库）/`preflight`（启动前检查），每步 `{state, attempts, error_code, updated_at}` |
| `resume_of` | 定向重试时指向原 key |
| `revision` | 作业CAS世代，状态变更/续跑递增 |
| `credential_version` | 本次作业角色凭据版本快照；ACK同时核当前版本 |
| `created_by` / `created_at` / `updated_at` | 审计 |

- 宿主步骤各自幂等：身份档“已存在则跳过，不覆盖用户手改内容（除非显式 `overwrite_profile`）”；Key 文件“已存在且身份核验通过则跳过”。
- 作业只记录**宿主步骤**；服务端身份已在 R1-1 原子完成，作业不得重建成员或重新发行 Key（需要时走 `rotate-key`）。
- 不自动注册到所有项目：步骤只作用于显式 `project_id`。
- 最终响应补充 `role_credential_version/expected_binding_fingerprint`；轮换后显式续跑，旧成功不代表新Key有效。四个作业/ACK/本人档案入口human-only。OS永久guard保护完整记录原子发布，已死过期才回收；Windows私有DACL/原子Key替换、mkdir前静态链接检查见[配置合同](ROLE_PROVISION_CONTRACT.md)。

### 7.7 故障注入与并发测试（R1-1 必含，不是“失败表写可重试”）

R1 要求“不能只在失败表写可重试”，因此 R1-1 的 `tests/test_role_creation_idempotency.py` **必须**包含下列可执行用例（计划 §3.2/§3.6-6 同步列出）：

| 用例 | 注入/并发方式 | 断言 |
| --- | --- | --- |
| T-R1-a 逐步故障注入 | 分别在第 5 步的 6 个写入点 monkeypatch 抛异常（Member / ProjectRole / ProjectAgent / ProjectRoleBinding / ProjectRoleDescription / operation 行） | 每次：六表零残留、无 `pending` 行、返回稳定码；随后同 key 同载荷重试返回 201 且事实完整 |
| T-R1-b 事务中途放弃（模拟宕机） | 用独立连接进入写事务并写入部分行后**不提交**直接关闭/丢弃（模拟进程被杀） | 主连接读不到任何部分事实、读不到操作行；同 key 重试成功 |
| T-R1-c 并发同 key | 两个线程/连接同时对同 key 同载荷发 `POST roles` | 恰好一个 201（含 Key）、一个 200（`reused:true`，不含 Key）；库中该 key 只有一行、该 `(project_id, member_id)` 只有一个成员 |
| T-R1-d 并发同 key 异载荷 | 两并发请求同 key、不同 `role_name` | 一个成功、一个 `409 operation_key_conflict`；无第二个身份 |
| T-R1-e 响应丢失恢复 | 201 后丢弃响应，再用同 key 重放 | 重放 200 `reused`、**不返回 Key**；`rotate-key` 后新 Key 可用、旧 Key 401 |
| T-R1-f 归档后同名重建 | 归档角色 A → 用新 key 建同名 | 成功且新 `member_id`；A 的名称/绑定/说明/历史保留 |

### 7.8 凭据不泄露面（可测试）

- 响应白名单：`GET /api/projects/{id}/roles`、`GET /api/projects/{id}/role-services`、`GET /api/members`（`MemberOut` 无 Key 字段）、页面渲染均不含 `api_key`/`owner_token`/`claim_token`/`key_file_path`/绝对路径/argv。
- 日志与交付：沿用既有凭据形态脱敏；`last_error_message` ≤300 且禁止写 Key/token/命令正文。
- 测试锁定：创建/轮换响应含 Key 且仅此一次；重放响应不含 Key；上述只读接口的键集合白名单断言。

---

## 8. 权限持久源与分级读路径切换（F4）

### 8.1 设计选择与理由

最小方案二选一：

- (a) 在 `project_agents` 增 `review_exempt` 并改造 sync 保留该字段；
- (b) 新建独立 `project_role_policies(project_id, member_id)`。

**选择 (b)**。理由：`project_agents` 的 sync 契约是全量替换（`server/routes/projects.py:650-682`），要保留字段就必须改 sync 语义或要求所有旧客户端回传该字段——两者都会扩大兼容风险；而仓库已有两处先例（`project_role_descriptions`、`project_role_bindings`）正是为规避 sync 全量替换而独立建表（`server/models.py:158-177,448-475`）。独立表天然跨 sync、跨离册重入稳定，且不需要改变任何旧客户端。

### 8.2 权限语义

- `review_exempt=1` ⇔ 原 `decision_tier='decision'` 的“可豁免复核”行为，**不新增**任何权限。
- 授予/撤销只能由 human 经显式入口（`PATCH /api/projects/{id}/roles/{member_id}` 的 `review_exempt` 字段）完成；agent 不可自授。
- 新角色默认无策略行 → 不豁免。
- 不扩大 human/agent 既有授权：human 仍可豁免；agent 仍不可自授；`_can_exempt_review` 的人类分支（`server/routes/tasks.py:116-117`）与 `project_id is None` 分支（`:118-119`）**保持不变**，这两个分支不参与 §8.4 的名册/角色门控。
- **R2 关键澄清：保留策略事实 ≠ 当前可用权限**。`project_role_policies` 行是“该角色曾获得/被授予的豁免事实”，必须在 `sync`、离册、归档后**保留**（否则回册就丢失）；但“当前是否可用”必须由 §8.4 的读路径按当前身份状态现算。二者分离是本条款的全部要点。

### 8.3 一次性迁移

1. 建表后检查迁移标记；无标记则：
   - `INSERT INTO project_role_policies (project_id, member_id, review_exempt, source, granted_at) SELECT project_id, member_id, 1, 'migration_decision_tier', now FROM project_agents WHERE decision_tier='decision'`；
   - 写入迁移标记（独立标记表或固定 key 行）。
2. `init_db()` 重复执行：标记存在 → 跳过，**不覆盖**任何后续人工修改。
3. 之后 `decision_tier` 的任何变化（sync、群成员接口、手工 SQL）都**不**影响 `review_exempt`。
4. 离册重入：策略行按 `(project_id, member_id)` 保留 → 回册后按原策略行恢复权限（与角色说明同一既有语义）；离册期间权限**休眠**（§8.4）。
5. 迁移只改“策略来源”，**不**扩大权限：迁移行只在原 `decision_tier='decision'` 的名册行上产生；不带 `review_exempt` 的旧客户端 sync 不会新增或删除策略行。

### 8.4 读路径切换（R2 修正）

R2 的问题：#214 稿的读路径 `policy is not None and policy.review_exempt == 1` 只看持久策略行。`sync` 全量替换会把角色移出名册，但策略行按设计保留，于是**离册角色仍然享受豁免**——这等于扩大了旧权限，与“保持旧权限/不扩权”矛盾。

R1-1 的目标读路径是**四条件合取**（顺序与短路如下）：

```text
# 现状（server/routes/tasks.py:111-121）
if current.kind == "human": return True          # 分支不变
if project_id is None:     return False          # 分支不变
profile = session.get(ProjectAgent, (project_id, current.id))
return profile is not None and profile.decision_tier == "decision"

# R1-1 目标
if current.kind == "human": return True          # 分支不变
if project_id is None:     return False          # 分支不变

# ① 成员当前必须是启用中的 agent（auth 已拦 disabled；此处显式化，便于测试锁定）
if current.kind != "agent" or current.disabled_at is not None:
    return False
# ② 当前 ProjectAgent 名册行必须存在（sync 移除即失效；保留旧读路径的语义）
if session.get(ProjectAgent, (project_id, current.id)) is None:
    return False
# ③ 若存在 ProjectRole，则必须未归档；不存在（老名册）时兼容放行
role = session.get(ProjectRole, (project_id, current.id))
if role is not None and role.archived_at is not None:
    return False
# ④ 最后才读持久策略
policy = session.get(ProjectRolePolicy, (project_id, current.id))
return policy is not None and policy.review_exempt == 1
```

- ③ 的兼容规则：**未建 `ProjectRole` 的老名册**（只 `talk sync` 过、没走过新角色表）走 ①②④，行为与迁移前一致，不因“没有新表行”而被降权。
- human 与 `project_id is None` 两个分支**不扩大**：human 仍恒可豁免；无项目上下文仍不豁免。
- 因此“离册 → 权限休眠（策略行仍在但不生效）”“回册 → 按原策略行恢复”“归档 → 权限休眠”“旧 `decision_tier` 修改 → 不重授/不撤权”四件事同时成立，且不需要改 sync 契约或要求旧客户端回传新字段。

### 8.5 迁移与 sync 行为对比（R2 要求）

| 步骤 | 操作 | 名册行 | `project_roles` | 策略行 | 豁免结果（§8.4 读路径） | 数据改写 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 迁移前旧库 | 有（`decision_tier='decision'`） | 无（老库无此表行） | 无 | 有（旧读路径读分级） | 无 |
| 1 | `init_db()` 第一次 | 不变 | 不变 | 新增 1 行 `review_exempt=1, source='migration_decision_tier'` | 有 | 只新增策略行 |
| 2 | `init_db()` 第二次 | 不变 | 不变 | 不变（标记命中，不重跑） | 有 | 无 |
| 3 | 旧客户端 `sync` 第一次（payload 无 `review_exempt`） | 全量重建，仍在册 | 不变 | 不变 | 有 | 名册行重建（既有语义），策略行不动 |
| 4 | 旧客户端 `sync` 第二次 | 同上 | 不变 | 不变 | 有 | 同上 |
| 5 | 改旧 `decision_tier='execution'` | 变化 | 不变 | 不变 | **仍有**（不撤权） | 只改旧列 |
| 6 | 改旧 `decision_tier='decision'` | 变化 | 不变 | 不变 | **仍无新授权**（不重授） | 只改旧列 |
| 7 | `sync` 移除该成员（离册） | 删除 | 不变（未归档） | 保留 | **无（休眠）** | 只删名册行 |
| 8 | `sync` 重新加入（回册） | 重建 | 不变 | 保留 | **恢复有** | 只新增名册行 |
| 9 | 归档角色（`archived_at` 非空） | 已移除 | 归档 | 保留 | **无（休眠）** | 角色行归档 |
| 10 | 新建角色（同名不同 member） | 新增 | 新增 | **不写** | **无** | 新增角色事实 |
| 11 | 老名册项目（无 `ProjectRole` 行）sync 两次 | 保留 | 无 | 曾写入 | 有（③ 兼容放行） | 无 |

对应测试（`tests/test_role_policy_migration.py`）：步骤 1–2 幂等、3–4 权限不变、5–6 不重授/不撤、7–8 休眠与恢复、9 归档休眠、10 新角色不获豁免、11 老名册兼容；另断言 human 分支与 `project_id=None` 分支行为不变。

---

## 9. 删除、归档与任务边界（F2 修正）

> 2026-10-16 用户补正确认：删除按钮放在角色详情“启动/关闭”旁，删除本项目角色及其配置/专属接入凭据，历史任务与成果保留，再需要只能重新添加。详见[新需求](ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)。本节 §9.3 第⑤步及 I20 中“保留绑定/说明/策略配置”的旧方向由新需求替代，不能只做可恢复配置的归档；human-only、共享项目隔离、在途保护与所有权要求继续有效。当前仅记需求，删除功能未实施。

### 9.1 身份类型与影响面

| 类型 | 判定 | 删除时的默认行为 |
| --- | --- | --- |
| `managed` + `identity_exclusive=1` | 新流程创建，且创建时全局仅此一条角色行 | 归档本角色；**仅当**显式 `disable_member=true` **且**删除事务内 §7.5 `_prove_exclusive_identity` 通过（全部兼容引用路径计数为 0、无在用实例/服务/任务）才禁用全局成员 |
| `managed` 但已非独占 | 同一成员后来被其它项目/角色引用 | 只归档本角色；**拒绝**全局禁用（`global_disable_requires_exclusive`） |
| `imported` / 共享 | 历史名册补录，可能跨项目复用 | 只归档本角色；**拒绝**全局禁用（`shared_identity_disable_refused`）；保留凭据供其它项目继续使用 |

- 全局禁用即 `Member.disabled_at`，经 `server/auth.py:31-36` 会让该 Key 在**所有**项目失效，因此必须走与 `rotate-key` **完全相同**的独占证明（§7.5，含旧 `ProjectAgent` 名册引用路径），不能只数新角色表。
- 删除侧的独占证明与轮换一致：只有当引用计数为 0（除本角色自身）时，禁用才是“只影响本角色”；任一兼容引用存在即拒绝。
- 默认（未显式请求）只移除本项目角色：删名册行 + 归档角色行，不动全局成员。

### 9.2 删除前置检查（默认拒绝）

1. `desired_state='running'` 或 `observed_state ∈ {starting, running, stopping}` → `409 role_service_running`，先停服。
2. 存在非终态任务（`queued`/`running`）指向该角色 → `409 role_has_active_tasks`，并返回任务清单入口（`GET /roles/{member_id}/tasks`）。human 用既有任务入口逐个处理。

**本合同明确不引入**：自动 `cancel-tree`、自动强杀、自动丢弃在途结果。`cancel-tree`（`server/routes/tasks.py:2167-2200`）会取消**整棵树**并重置关联实例，会干预其它角色，因此**不得**作为角色删除的实现路径。真正需要“自动强制取消整棵树”的语义记为待授权后置边界 D1。

### 9.3 顺序与竞态

正常删除顺序（human 显式操作）：

```text
① 前置检查（服务未运行 + 无在途任务）
② [可选] 停止本角色受管服务（只停止 owner_token/owner_host 匹配的本次启动）
③ [可选] 处理在途任务：用既有单任务/任务树入口（本角色相关任务），不使用整树强制取消
④ 单事务归档：设置 project_roles.archived_at；删除 project_agents 名册行；[可选且满足 §9.1 条件] 设置 members.disabled_at
⑤ 保留：project_role_bindings（只读）、project_role_descriptions、project_role_policies、role_service_state/launch 记录、历史任务/消息/快照
```

- **派发禁入**：`_ensure_target_agent`（`server/routes/tasks.py:99-103`）扩展为——当任务带 `project_id` 时，若 `project_roles(project_id, target_member_id).archived_at` 非空 → `400 task_role_archived`。任务树内的子任务（携带 `parent_task_id`）继承根任务的项目上下文并同样检查。
  - 边界：不带 `project_id` 的历史/全局任务不新增项目级检查，保持旧行为；该边界如实登记。
- **领取禁入**：`claim`（`server/routes/tasks.py:2563-2574`）在既有 `target_member_id != current.id` 检查后，增加“该角色在本任务的 `project_id` 下未归档”检查 → `409 role_archived`。已提交结果与被取消任务的历史保留不变。
- **竞态**：归档事务与任务创建/领取各自在**写事务**内做检查（SQLite 单写者）。若任务创建先提交，归档的前置检查（步骤①）会看到非终态任务并拒绝；若归档先提交，创建/领取检查拒绝。残余窗口（两事务交错）由“归档在提交前重查一次非终态任务”收敛，并列为 R1-4 必须覆盖的测试场景。
- **不影响其它角色**：归档只写本 `(project_id, member_id)` 行与对应名册行；任何跨角色操作（尤其整树取消）都被排除。

---

## 10. 服务生命周期、宿主执行闭环与所有权（F3 修正）

### 10.1 执行架构

- **宿主侧服务管理器**（本地进程，随“启动 TALK”的宿主/桌面容器运行）负责 spawn/kill/等待就绪，并通过 §5.3 协议领取启动、回报观测结果。
- **服务端**负责：期望状态、世代、启动动作记录、观测状态收敛、审计、权限、页面投影；**不** spawn 进程（`server/` 现状无进程管理代码，`scripts/` 的进程代码属宿主侧先例）。
- 启动 = 宿主按角色配置组装 argv（运行器入口 + 项目根 + `--name`/`--key`/`--project` + 模型 alias 等）并 spawn；**绑定不自动改变实际 CLI 模型**（缺口 G10）——argv 的模型选择由本流程显式携带，且必须与绑定一致，否则启动前检查失败。

### 10.2 完整最小宿主协议（claim/report，R4 修正）

R4 的四个缺陷在本协议中逐一闭合：token 生成了但 report 不携带/不核验；claim 未列输入、未持久化 `claim_host`/`expected_instance_id`；`expected_instance_id` 可空且实例可任意换 `launch_id`；`start`/`stop` 共用动作且缺 `launch_expires_at`。**授权不来自 body 里的 host 自报**，而来自“领取人身份 + claim/owner token 哈希 + 服务端预分配事实 + 世代 + 截止时刻”。

```text
human start → 同库事务 CAS 递增 generation，desired=running，observed=starting；
              创建 start launch，预分配全新 expected_instance_id 与截止时刻。
human stop  → 同库事务 CAS 递增 generation，desired=stopped，observed=stopping；
              创建 stop launch，target_start_launch_id=process_launch_id，
              expected_instance_id=原 start 的 ID；保留原进程归属。

host claim body {host, expected_instance_id, owner_token?}
  → 校验角色成员/human身份、当前 launch/generation、pending、未过期与实例 ID；
    start：生成 owner_token + claim_token，存哈希；固定 process_launch_id/owner_host。
    stop：先校验 target_start_launch_id、原 owner_token 哈希与原 claim_host；
          只有原管理宿主可领取，生成新 claim_token，不生成新 owner_token。
  → 绑定领取人/host/claimed_at；start 返回两个 token，stop 只返 claim_token。

host spawn/stop → report body {generation, action, claim_token, owner_token,
                              outcome, instance_id?, pid?, process_started_at?, host, error_code?}
  → 校验 claim token + owner token（stop 对原 start）+ caller + host + role/project；
    校验 action、generation、current_launch_id、claimed 与 claimed_at≤now≤deadline；
    start 收 ready/failed；stop 收 stopped/failed。
  → 存完整回报指纹/时间与状态；随后按 §10.3 统一收敛，report alone 不判启动成功。

bridge PUT expected_instance_id，body {project_id, launch_id, ...}
  → start 的 launch 关联首次建立后不可清空/替换；实例必须全新预分配、member/project/host匹配。
  → idle/busy 新心跳在领取后且截止前到达，记录 first_instance_seen_at；
    只在 §10.3 的合法 ready 回报及实例证明全部齐备时判启动成功。
    正常后续心跳保留原 start 的 launch_id，stop 不给实例重新贴标签。
```

- **动作语义**：start 只接受 ready/failed；stop 只接受 stopped/failed，停止目标必须是原 `process_launch_id` 所属进程。无进程且有已停证明直接幂等返回；归属未知拒绝 unknown_owner。动作不匹配返回 launch_action_mismatch。
- **停止观测闭环（R4）**：`stop`+`stopped` → `observed_state='stopped'`、`last_result='stopped'`、清空 `current_launch_id`、`process_launch_id` 与受管进程归属（人工关闭**不记失败**）；`stop`+`failed` → `last_result='failed'` + 错误码，`observed_state` 保持可证明现状（进程仍在则 `running`，无法证明则 `unknown`）。
- **授权边界**：human 设置 `desired_state` 与发起启动/停止；该角色的 agent 只能领取/回报**属于自己**的 launch 并上报自己的实例。agent 始终**不能**修改 `desired_state`（`server/routes/instances.py` 现有“仅 agent 上报自己实例”的规则保持不变）。
- **token 不进公共输出**：owner token 只在 start claim 返回一次，claim token 每动作返回一次；stop 以宿主原持有 owner token 证明归属。库里只存哈希，公共 GET/页面/日志不返回。

### 10.3 就绪判定（不是只看 PID，也不冒称模型能力）

`action='start'` 的“启动成功”需**同时**满足：

1. 启动前检查通过（CLI 入口存在、Key 身份匹配、模型 alias 可解析）；
2. 该 launch：`action='start'`、`state='reported'`、`outcome='ready'`、`reported_at <= launch_expires_at`；
3. 存在实例行 `id == launch.expected_instance_id`（服务端预分配，**不允许**用另一个恰好同 member 的实例顶替）：`member_id` 一致、`project_id == 角色项目`、`launch_id == 该 launch_id`（不可变关联，§10.4）、`status ∈ {idle, busy}`、`last_seen_at` 在新鲜度 TTL 内；
4. `launch.generation == role_service_state.generation` 且 `role_service_state.current_launch_id == launch_id`，`desired_state=running`；服务端记录的 `first_instance_seen_at` 满足 `claimed_at≤first_instance_seen_at≤launch_expires_at`，证明和合法 ready 回报均在截止前齐备。

**时间窗（R4 补齐）**：`launch.claimed_at ≤ report_time ≤ launch.launch_expires_at`，且就绪实例的 `last_seen_at ≥ launch.claimed_at`（必须是本次动作之后的**新**心跳，旧心跳不算）。#214 稿写的“上报时间 > claim_expires_at 之前”不成立，已删除。

**“就绪须是本次预期新实例”的落地**：服务端在 start 时预分配 `expected_instance_id`，宿主必须用该 ID 上报（bridge 以 `--instance-id`/等价参数接收）；旧实例即使持续心跳，其 `launch_id` 指向更早的 launch（或为 `NULL`），既不能改标签（§10.4 `instance_launch_immutable`）也不满足条件 3 → 不产生就绪，最终按 §10.5 超时收敛为失败。

明确**不**作为成功条件：模型版本正确、额度充足、任务能力可用、原生登录态长期有效。这些分别登记为未验证，直到有真实证据。

**非登录就绪 ≠ 服务可用**（F3）：投影分三个独立字段——

| 字段 | 取值 | 来源 |
| --- | --- | --- |
| `preflight.native_login` | `verified`/`unverified`/`not_applicable` | 真实证据；无法核验时为 `unverified`，**不得**当作 ready |
| `preflight.model_alias` | `resolved`/`unresolved` | argv 组装检查 |
| `readiness.service` | `ready`/`failed`/`unknown` | 上述四条 |

`last_result='success'` 只表示“本流程受管服务就绪”；`native_login=unverified` 时页面不得显示无保留的“服务可用”。

### 10.4 实例归属、项目不可变与 launch 关联不可变（R4）

- `PUT /api/instances/{instance_id}` 改为**只赋值请求中显式出现的字段**（Pydantic `model_fields_set`）：
  - 新建行：未提供字段 → `NULL`（旧新增允许 `NULL`，语义为“未声明”）；
  - 已存在行：未提供字段 → **保持原值**，不再被旧心跳抹成 `NULL`（`server/routes/instances.py:50-55` 当前对全部字段无条件赋值，这是 G14 的根因）。
- 项目不可变：若已存在行的 `project_id` 非空，则请求的 `project_id` 必须缺省或等于原值；试图改为另一项目或清空 → `409 instance_project_immutable`。首次声明前允许 `NULL`。
- `project_id` 非空时，服务端校验该 `member_id` 在该项目有**未归档**角色/名册行；否则 `422 instance_project_not_in_roster`。
- **launch 关联不可变（R4）**：`launch_id` 只允许新预分配实例首次关联或同值重复；已存在非空值改为另一值**或显式清空**均返回 `409 instance_launch_immutable`。已有 legacy 实例不能被原地升级为本次新实例。首次关联还须满足：该 launch 的 `expected_instance_id == instance_id`、`member_id`/`project_id` 一致、`state='claimed'`、`action='start'`、未过期。这样**旧实例无法被重新贴上本次 `launch_id`** 来冒充就绪。
- **R1-1 的阶段边界**：只预留 launch 列及不可变规则，不建服务表。新建/首次绑定非空 launch 统一拒绝 `422 instance_launch_not_supported`；用夹具预置的非空值可同值重复/省略保持，但不能改写/清空。R1-3 才启用上面的真实 launch 存在/领取/实例匹配校验，不用裸字符串代替启动证据。
- **世代不落实例列**：实例只存 `launch_id`；`generation` 由不可变 launch 行推导（`launch.generation`），因此不需要给 `agent_instances` 盲目加一个会被旧心跳覆盖的 `generation` 列。
- **首次关联 / 旧心跳省略的具体定义**：
  - 首次关联（新实例、`launch_id` 为空）：允许带 `launch_id` 建行，做上述校验；
  - 旧 bridge 心跳（不传 `launch_id`）：已存在行 `launch_id` **保持原值**；新建行为 `NULL`（“未声明启动动作”），**不**参与任何就绪判定。

### 10.5 CAS、幂等与过期回报（R4）

- `generation` 条件更新保证同一角色同一时刻只有一个启动/停止动作生效；后到者 `409 generation_conflict`，不重复 spawn。
- `report` 幂等：先核原领取身份、host 与 claim/owner token，再比对完整载荷指纹。同一已完成回报可返回原 receipt（不写当前状态，截止后重放也只读原 receipt）；不同载荷返回 report_conflict。未完成动作在超时或新世代后首次回报为 stale_report，绝不覆盖新动作。
- **旧回报不得覆盖新动作（R4）**：report 的核心 CAS 条件包含 `launch_id + generation + action + state='claimed'`，且前置校验要求 `role_service_state.current_launch_id == launch_id`。新动作一旦开始，`current_launch_id`/`generation` 即改变，旧动作的迟到回报必然 `409 stale_report`，只写审计、不改状态。
- 到期收敛：start 若截止前未形成“合法 ready 回报 + 匹配新实例”双证据，必须记 readiness_timeout，**包括已回报 ready 但缺实例**；reported 不能让 starting 永久悬挂。stop 未有合法 stopped 回报记 stop_timeout/unknown。只有仍匹配 current_launch_id/generation 的动作可改角色状态，旧记录仅写自身超时审计。
- 停止闭环（R4）：见 §10.2 的“停止观测闭环”条；`stop` 的 `stopped`/`failed` 都有明确投影，且旧回报不能改新动作结果。

### 10.6 稳定错误码（服务生命周期）

`generation_conflict`、`already_running`、`launch_not_found`、`launch_not_pending`、`launch_expired`、`launch_action_mismatch`、`expected_instance_mismatch`、`stale_report`、`report_conflict`、`report_unauthorized`、`claim_expired`、`readiness_timeout`、`native_login_unverified`、`model_alias_unresolved`、`cli_missing`、`identity_mismatch`、`unknown_owner`、`stop_timeout`、`instance_project_immutable`、`instance_launch_immutable`、`instance_project_not_in_roster`。

### 10.7 所有权与进程身份（不能只靠 PID）

- 宿主将原 start owner token、start launch ID、project/member、host及活进程句柄持久关联；stop 验原 start 所有权后才执行，不用新 stop claim token 认领原进程。停止/退出按 `process_launch_id` 指向的原 start 记录核验；current_launch_id 切到 stop 不改变原进程归属。
- PID 只作诊断。**不使用 PID 单独判定或杀进程**：宿主须持有活进程句柄（或等价物），并在停止前核对 `(pid, process_started_at)` 与本地记录一致；不一致或无法证明 → 报 `unknown_owner`、`observed_state='unknown'`，**不杀**。
- 跨项目同名进程、用户手动打开的外部程序一律不碰；共享宿主场景以 `claim_host` 区分。
- 重启后 PID 复用：无法按 token + 本地记录证明归属即报 `unknown`。

### 10.8 退出边界

| 场景 | 行为 |
| --- | --- |
| 关闭浏览器页面 | **不**停任何服务（页面 ≠ TALK 宿主） |
| 宿主/TALK 桌面正常退出 | 关闭本宿主管理的角色服务（`process_launch_id` 指向的原 start 所有权、host 与活进程身份匹配），正常停机带超时；超时报 `stop_timeout`，是否强杀由 human 二次确认 |
| 宿主异常退出/崩溃/断电 | **本 R0 不解决**：只登记“可能残留”，提供只读状态与人工清理入口；不宣称自动清理 |
| 重启后 PID 复用 | 不以 PID 认领进程；只按 token + 宿主侧记录认领，无法证明即报 `unknown` |

### 10.9 逐角色与批量操作

- **全部启动**：先取当前 `observed_state`，**跳过** `running/starting`，其余逐个启动，返回逐角色结果；部分失败不整体回滚，失败清单可定向重试。
- **单独停服**：只影响该角色；按所有权优雅停止，超时按 §10.8 处理，**不默默强杀**。
- **删除**：见 §9；不卸载运行器、不退出共享原生账号、不删除其它角色。

---

## 11. 页面投影契约

### 11.1 主显示（角色列表/详情）

仅：**人工角色名称**、**运行器**、**模型**、**介绍**、**服务启动成功/失败**（失败可看原因）。
不再主显示：`member_id`、`decision_tier`、原始配置字段、argv、Key。

### 11.2 服务结果投影（内部状态 ≠ 页面文案）

| 内部 `observed_state`/`last_result` | 页面文案 | 备注 |
| --- | --- | --- |
| `not_started` | 未启动 | 中性，不是失败 |
| `stopped`（人工关闭） | 未启动（已关闭） | **不记失败**，清空上次成功 |
| `starting` | 启动中…（按钮加载态） | 短加载态，可轮询收敛 |
| `running` + 就绪 | 启动成功 | 仅表示本流程启动成功，不表示模型能力；`native_login=unverified` 时附“原生登录未核验” |
| `running` 但未就绪超时 | 启动失败（原因：未就绪） | |
| `failed` | 启动失败（原因码/短说明） | 可重试 |
| 未知/旧服务不支持 | 未知（不伪装） | 沿用既有“未知 ≠ 未配置”纪律（`web/workspace.js:678-790`） |

### 11.3 任务状态

空闲/执行中**留在任务列表**（现有 `workspaceWorkSummary`，`web/workspace.js:88-91`），不进入角色服务结果。

---

## 12. 原生接入与运行器控制能力分类

- **全局原生接入/登录**与**项目角色身份配置**分开：TALK 引导官方原生登录（如 Kimi 原生 `/login`、WorkBuddy 官方登录页），只提供“打开软件/前往登录/检查就绪”入口，不收集订阅用户名密码。
- 运行器新增 `control_kind`，如实区分：
  - `managed_cli`：TALK 宿主可启动/停止的 CLI 进程（如 Kimi Code CLI、DSH headless、Codex CLI）。
  - `external_session`：需要原生应用登录并由其自身会话承载（如桌面形态）；无可靠控制接口时页面明确“需人工打开/登录”，不显示“启动成功”。
  - `unknown`：未声明，页面不提供启动按钮。
- **原生配置目录/认证是否可复用不得臆测**：K28 入口已核实“不转发配置选择器、固定 alias”（`scripts/adapter_closeout.py`、`scripts/adapter_binding_facts.py`），但 DSH/Codex/WorkBuddy 的认证目录复用**未核验**，按未验证登记。
- WorkBuddy 已有人工单任务证据（#90/#91）**不证明**无人值守反向控制或多角色隔离。

---

## 13. 运行器能力矩阵（来源、版本依据、实现/验证状态）

> 状态口径：**已实现**=仓库有代码；**已验证**=有独立复核的真实证据；**未验证**=无真实宿主证据。不得把模板值或工具发现当作宿主适配通过。本片**不为填表消耗模型或制造真实等待任务**。

| 运行器 | 来源/入口 | 版本依据 | 已实现 | 已验证 | 未验证 | 最小后续验证 | 能力不足时降级 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | `bridges/codex_bridge.py` + 用户外部启动 | 用户当前使用版本，未见版本探测代码 | 通用 bridge 复用、实例上报、`--decision-tier` 兼容参数 | 单任务闭环/身份切换历史上有人工验收 | 受管启动/停止、崩溃清理、模型 alias 选择、原生登录复用 | 在隔离项目用受管入口启停一次并核就绪协议 | `external_session`：只提供人工打开/登录步骤 |
| Kimi Code（K3 泛用） | `bridges/kimi_bridge.py` | 入口无版本固定 | 专用 bridge、工具档、`--kimi-model` | 0.38.0 历史真实闭环（人工唤回） | 受管启停、多角色隔离、版本探测 | 同 K28：核 CLI 存在/模型 alias/身份 | 无受管入口时按人工启动登记 |
| Kimi Code + K2.8 Preview | `scripts/kimi_k28_executor.py` | 固定 alias 常量（非运行版本探测） | 离线检查、只读身份核验、`launch` 进程内启动、closeout 登记/绑定 | #195 最小接单/回传经独立核验 | 实际后端模型版本、额度、宿主主动等待 T/W、受管停止 | 受管启停 + 就绪协议 + 停止清理 | 只登记配置，不宣称服务能力 |
| DeepSeek Harness（DSH） | 通用 bridge `--runtime dsh --prompt-transport argv --command "dsh.cmd --profile headless"`；`scripts/dsh_talk_precheck.py`（config/dump）、`scripts/dsh_acp_drive.py`（ACP） | `0.2.0-rc.2` 桌面调查为历史事实；CLI 版本未探测 | 通用 bridge 接入、预检组合树、ACP 零模型会话恢复 | 真实模型单任务闭环（历史上人工验收） | 受管启停、`DSH_HOME`/认证目录复用、多角色隔离、崩溃清理 | 受管启停 + 独立 `DSH_HOME` 隔离核验 | 按 `external_session` 提供人工步骤 |
| WorkBuddy（+Kimi / +DeepSeek） | 用户级 MCP，无仓库内受管入口 | 5.5.6 桌面（历史记录） | 仅文档/MCP 配置模板 | #90/#91 有人值守单任务闭环 | 无人值守启动、反向控制、多角色隔离、认证复用 | 无受管接口前只做人工步骤登记 | 明确标注“无可靠控制接口” |

**等待预算（T/W/返回余量）单独登记**：沿用 [TERMINAL_MCP.md](../guides/TERMINAL_MCP.md#终端适配必查工具超时与等待预算2026-10-06) 与 [INITIATOR_MODE_CONSUMER.md](../guides/INITIATOR_MODE_CONSUMER.md) §3 的已核事实（DeepSeek 桌面 T=65s/W=50；Codex W=300 为用户现用值；Kimi 模板值非运行事实）。**取消/排队边界**单独记录，不把工具发现当适配通过。本片真实能力保持 `not_run`。

---

## 14. 隔离与边界场景表

| # | 场景 | 期望行为 | 关联 |
| --- | --- | --- | --- |
| I1 | 同运行器同模型建两个角色 | 两个独立 `member_id`/Key/身份档/上下文；角色名可不同，互不覆盖 | REQ-3.1 |
| I2 | 两个项目使用同名角色 | 项目内唯一即可；`members.display_name` 改名不影响其它项目 | REQ-3.1c |
| I3 | 重命名角色 | 默认只改项目内 `role_name`，不动全局成员；其它项目引用不受影响 | F6 |
| I4 | 一个角色在项目 A 运行、项目 B 同名 | 运行状态按 `(project_id, member_id)` 隔离；停止 A 不影响 B | REQ-3.6 |
| I5 | 同一原生账号 | 共享订阅不自动共享 TALK 身份；会话/认证目录隔离按运行器能力，默认隔离 | REQ-3.7 |
| I6 | 用户手动打开的外部程序 | 宿主退出不关闭；只清理原 start 的 `owner_token_hash` + `claim_host` 匹配的受管服务 | REQ-3.6 |
| I7 | 浏览器关页 | 不触发任何停服 | REQ-3.6 |
| I8 | 并发两次“全部启动” | `generation` 条件更新；第二次跳过或返回进行中，不重复 spawn | F3 |
| I9 | 启动中途宿主崩溃 | 状态可能停在 `starting`；重启后按 token 无法证明即报 `unknown`，不自动当成功 | REQ-3.6 |
| I10 | PID 被复用 | 不按 PID 认领或杀进程；只按 token + 宿主记录 + `(pid, process_started_at)` 核对 | F3 |
| I11 | 删除运行中角色 | 默认拒绝（`role_service_running`）；先停服再删 | F2 |
| I12 | 迁移旧库 | 只增表/列/索引 + 一次性策略迁移行；`decision` 成员经 `review_exempt` 保留原豁免；旧任务/快照字节不变 | F4 |
| I13 | 旧客户端读新接口 | `GET /api/runners` 形状不变（仅附加 `control_kind`）；新增字段为附加，旧客户端忽略未知键 | C1–C4 |
| I14 | 运行器退役 | 目录/绑定行保留，读取阶梯如实报告；不自动删角色或撤 Key | C1–C4 |
| I15 | 凭据泄露面 | Key 只在创建/轮换响应出现一次；日志/交付/页面/任务正文不落 Key | F1 |
| **I16** | 同 key 异载荷重放 | `409 operation_key_conflict`，不建任何新事实 | F1 |
| **I17** | 并发同 key 重放 | 恰好一个 201（含 Key）、一个 200 `reused`（不含 Key）；不产生第二个身份（R1） | F1/R1 |
| **I18** | TX-ALL 任一步失败 | 单事务整体回滚，六表零残留、**无操作行**；同 key 同载荷可重试（R1） | F1/R1 |
| **I19** | 创建响应丢失 / 宿主写 Key 失败 | human 走 `rotate-key` 得到新 Key 并一次性返回；旧 Key 失效；重放**不**返回 Key | F1 |
| **I20** | 归档后重建同名角色 | 部分唯一索引放行；新角色获得新 `member_id`；旧角色历史/绑定/说明保留 | F1 |
| **I21** | 空名/纯中文名 | 空白 → 422 `role_name_invalid`；纯中文合法，slug 兜底 `role` + 随机后缀 | F1 |
| **I22** | 随机 `member_id` 冲突 | 重取随机后缀，最多 8 次；**绝不复用**已存在的不明成员 | F1 |
| **I23** | 共享 imported 成员被两个项目引用 | 删除其中一个项目角色只归档本项目行；**不**禁用全局成员 | F2 |
| **I24** | 删除时存在他人子任务 | 默认拒绝；不使用 `cancel-tree`；由 human 用既有任务入口处理，其它角色任务不受影响 | F2 |
| **I25** | 归档后派发/领取 | 新任务 `400 task_role_archived`；领取 `409 role_archived`；已提交结果保留 | F2 |
| **I26** | 旧实例持续心跳但本次 spawn 失败 | 只有匹配本次 `launch_id` 的新就绪证明才算成功；旧心跳不救场，最终 `readiness_timeout` | F3 |
| **I27** | 旧世代迟到回报 | `409 stale_report`，只记审计，不覆盖新世代结果 | F3 |
| **I28** | 错 host/project 上报 | 项目不符/未在名册 → `422 instance_project_not_in_roster`；host 不匹配 → 不认领 | F3 |
| **I29** | 旧心跳省略字段 | 已存在行省略字段保持原值；不再被抹成 `NULL`；项目字段不可静默切换/清空 | F3 |
| **I30** | PID 复用 + 可能误杀 | 无活句柄/身份核对不符 → `unknown_owner`，**不杀** | F3 |
| **I31** | 旧库迁移两次 + sync 两次 + 改旧 `decision_tier` | 豁免权限始终不变；策略行只迁移一次；新角色不获豁免 | F4 |
| **I32** | 同 runner 同 model 两 provider/connection | 两条选择行并存，`choice_id` 不同；两个角色各绑其一并存 | F5 |
| **I33** | 目录改动（改名/改 alias/软下架） | 不回写旧绑定；老角色连接/alias 不变；`retired_at` 只影响新选择过滤 | F5 |
| **I34** | 任务 13 键绑定快照 | 键集合与语义完全不变，不重构 C1–C4 | F5 |
| **I35** | TX1 后宕机（旧两阶段） | **不存在该状态**：无独立提交；宕机后无操作行、无身份，重放即首次执行（R1） | R1 |
| **I36** | TX-ALL 执行中宕机/被强杀 | SQLite 原子回滚，无半写事实、无 `pending` 行；重放成功（R1） | R1 |
| **I37** | 失败标记前宕机 | **没有失败标记阶段**：失败即无行，无待回收状态（R1） | R1 |
| **I38** | 两个 failed 恢复并发 | **不存在 failed 行**；两并发同 key 由写锁 + 唯一约束决定唯一赢家，输家读回 `reused`（R1） | R1 |
| **I39** | 离册后仍持策略行 | 权限**休眠**：读路径因名册行缺失拒绝豁免；回册后按原策略行恢复（R2） | R2 |
| **I40** | 归档后仍持策略行 | 权限休眠：`ProjectRole.archived_at` 非空 → 读路径拒绝（R2） | R2 |
| **I41** | 老名册项目（无 `ProjectRole`） | 走 ①②④ 兼容放行，行为与迁移前一致（R2） | R2 |
| **I42** | 改旧 `decision_tier` | 既不重授也不撤权（R2） | R2 |
| **I43** | 共享成员两项目 + `rotate-key` | `409 rotate_shared_identity_refused`；**不**改全局 Key（R3） | R3 |
| **I44** | 仅旧 `ProjectAgent` 名册引用 | `409 rotate_legacy_roster_reference_refused`，不因“新表无引用”而误判独占（R3） | R3 |
| **I45** | 角色运行中/有在途任务 + `rotate-key` | `409 rotate_identity_in_use`；先停服/清任务（R3） | R3 |
| **I46** | 轮换与引用新增并发 | 写锁串行化；`identity_exclusive=1` 后跨项目引用新增 `409 identity_exclusive_reference_refused`（R3） | R3 |
| **I47** | report 不带/错 token 或换人回报 | `409 report_unauthorized`，不改状态；body host 自报不构成授权（R4） | R4 |
| **I48** | claim 声明错 `expected_instance_id` | `409 expected_instance_mismatch`；未领取成功即无法 spawn 授权（R4） | R4 |
| **I49** | 旧实例上报本次 `launch_id` | `409 instance_launch_immutable`；旧实例不能被重新贴标签冒充就绪（R4） | R4 |
| **I50** | stop 动作领取/执行/回报 | 核原 start owner token/host/句柄；stopped 不记失败；failed 保留可证明进程现状并显示错误（不盲目记已停） | R4 |
| **I51** | 旧回报在新动作之后到达 | `409 stale_report`（CAS 含 `current_launch_id`），不覆盖新动作结果（R4） | R4 |
| **I52** | 旧 launch 超时但角色已重新启动 | 只标该 launch `expired`，**不**改新世代的 `observed_state`（R4） | R4 |
| **I54** | stop 被其它宿主领取 | 缺原 owner token/host 不符 → unknown_owner，不能生成新 token 认领原进程 | 澄清 |
| **I55** | 已回报 ready 但实例证明未到 | 截止后 readiness_timeout，不永久 starting | 澄清 |
| **I56** | R1-1 首次写非空 launch | 422 instance_launch_not_supported；已有非空值清空/替换409 | 澄清 |
| **I57** | managed 新身份加入跨项目/全局群或任务 | 引用守卫同事务拒绝；旧 imported 成员语义不变 | 澄清 |
| **I53** | `GET roles` 的 `model.choice_id` | 创建操作映射且与当前绑定六维一致 → 返回；失配/老名册 → `null` + `choice_source` 标注（R5） | R5 |

---

## 15. 已采纳方向与待授权后置边界（替代原 P1–P8 前置批准，F6）

### 15.1 已按用户已授权方向纳入合同（**无需再次请求批准**）

| 原编号 | 事项 | 本稿采纳结论 | 落点 |
| --- | --- | --- | --- |
| P1 | 重命名项目角色是否同步全局 `members.display_name` | **否**：只改项目内 `role_name`，保持创建时全局名快照；需要同步时另做显式按钮 | §5.2 PATCH |
| P2 | 复核豁免如何替代旧 `decision_tier=decision` | 新建独立 `project_role_policies.review_exempt`，一次性迁移回填；后续由 human 显式授予/撤销 | §8 |
| P3 | 服务管理器位置 | **宿主侧本地进程**拥有进程与所有权；服务端只存期望/世代/观测 | §10.1 |
| P4 | `member_id` 命名 | 稳定不透明 `agent:<project_slug>.<role_slug>-<8hex>`，创建后不改、不复用 | §7.2 |
| P5 | 删除有在途任务的角色 | 默认**拒绝**；**不**自动 `cancel-tree`、不静默丢结果；human 用既有任务入口处理 | §9.2 |
| P6 | 模型目录下架方式 | 第一片即定义 `retired_at` **软下架**，不物理删除；旧绑定不受影响 | §4.1.1 |
| P7 | 同原生账号多角色是否共享会话目录 | **默认隔离**；仅在对应运行器实测通过后逐项放开 | §12 |
| P8 | 第一片是否含分级迁移 | **含服务端读路径切换**（仅 `tasks.py:111-121`），bridge/终端/页面独立成片 | §6.2、实施计划 R1-2 |
| 新增 | 分片顺序 | R1-1 后端数据地基 → R1-2 配置作业 + bridge/页面 → R1-3 受管服务生命周期 → R1-4 外部会话/删除/退出 → I-4 后置 | 实施计划 §2 |
| 新增 | 会话与凭据隔离 | 每角色独立 `member_id`/Key/身份档；共享原生认证默认隔离 | §3、§12 |

### 15.2 待授权后置边界（**不得夹带**，需单独明确授权）

| # | 边界 | 具体影响 | 可审阅推荐 | 不依赖它的补正是否已完成 |
| --- | --- | --- | --- | --- |
| D1 | 删除角色时**自动强制取消整棵任务树** | 会干预同一棵树内其它角色的任务、重置关联实例；与“不默默强杀/不丢结果”冲突 | **不引入**；保留默认拒绝 + human 逐任务处理。若未来确需，另立合同并定义“仅本角色任务”的局部取消协议 | 是（§9 已闭合拒绝路径） |
| D2 | 对 **imported/共享** 身份禁用全局成员或撤销凭据 | 会同时中断其它项目的活跃引用（`server/auth.py:31-36` 全局生效） | **不做**；只归档本项目角色并保留凭据。若要“共享身份也能全局停用”，需定义影响面评估与人工确认门 | 是（§9.1 已闭合独占条件） |
| D3 | 留存明文 Key 以便同 key 重放再次取回 | 扩大静态凭据面；新增凭据读取入口 | **不留存**；恢复统一走 `rotate-key`。若必须“同一 Key 可再次取回”，需单独授权并配套密钥管理方案 | 是（§7.4/§7.5 已闭合恢复与独占证明） |
| D4 | 扩大 human/agent 既有授权（如允许 agent 自建角色/自授豁免） | 直接改变权限模型 | **不做**；创建/删除/启停/轮换/授权仍 human-only | 是（§5、§8.2） |
| D5 | 复用原生认证/会话目录 | 未核验，可能破坏多角色隔离 | 默认隔离；逐运行器实测后放开 | 是（§12） |
| D6 | **阶段 B** 物理清理 `decision_tier` 列/接口字段/页面字段 | 破坏性数据/接口变更 | 本 R0 不进入；确认无生产消费者后另立切片 | 是（§6.2） |
| D7 | 把 `rotate-key` 扩为**全局凭据管理**（改所有项目共用的 Key）或把 `Member.api_key` 迁移为哈希列 | 影响所有引用该成员的项目与会话，属凭据存储模型变更 | **不做**；`rotate-key` 只做“managed 独占身份 + 未在用”的凭据恢复，`api_key` 明文列保持（§7.4/§7.5）。若确需，另立合同并定义影响面与迁移 | 是（§7.5 已闭合恢复与拒绝码） |

> 一般实现选择（字段命名、索引细节、错误码细分、页面加载态细节）**不上升为人类前置批准**，由开发者在实施计划与代码评审中决定。

---

## 16. 文档发布与链接

- 本合同修订稿预定发布为 `docs/spec/ROLE_LIFECYCLE_DESIGN.md`；配套实施计划为 `docs/spec/ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md`。
- 相对链接按**最终位置**设计（同目录 `DEVELOPMENT_ROADMAP.md`、`ROLE_MODEL_BINDING_DESIGN.md`、`MODULE_instances.md`、`ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md`；上级目录 `../guides/TERMINAL_MCP.md`、`../guides/INITIATOR_MODE_CONSUMER.md`、`../guides/TASK_WORKFLOW.md`）。
- 模块文档只引 `MODULE_instances.md`（本任务唯一被读模块），其余事实一律引实际源码位置与指纹。
- 草稿位于 `.tmp/project-role-lifecycle-design-final/` 时这些链接**不指向本地临时文件**，以最终发布位置为准；链接目标存在性在 `verification.json` 中按最终路径核验。
- 发布前需 Codex 独立核实际代码与合同；发布后旧版本按既有约定归档，本 R0 不自行改正式文档。
- 原 213 草稿、原结果 msg2717、#214 修订稿与 msg2718 及其失败/验收回执**保持原样**，本修订稿不覆盖、不改写。
- 配套索引：`R1_R5_CLOSURE_INDEX.md`（本稿 R1–R5）与 `F1_F6_CLOSURE_INDEX.md`（原 F1–F6，含 R5 修正后的引用校正）。
