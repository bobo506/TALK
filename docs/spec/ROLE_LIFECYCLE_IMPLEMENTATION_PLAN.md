# 项目角色创建与服务生命周期：实施计划（R0 正式实施计划 v4）

> 状态：**R0 v4、R1-1、R1-2与R1-3代码已独立通过**（2026-10-12）。R1-2基础页面人工验收通过；R1-3经#223/#224返修、Codex两轮定向修正及#225/#226独立复核，整链已收取，受管CLI/API/页面启停基础完成，当前暂停等待R1-3页面人工验收。真实原生能力未验，R1-4/I-4后置。
> 正式位置：`docs/spec/ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md`；合同见同目录 [ROLE_LIFECYCLE_DESIGN.md](ROLE_LIFECYCLE_DESIGN.md)。
> 修订基线：`5b18c8e7c2eb85fb6737d7c9c89713adf6021ef7`（#215 派发时实际 HEAD，工作区干净，正式源码未变）。
> R0发布时仅修改文档；原213–226草稿、结果与失败保持。R1-1至R1-3代码已独立通过；未执行生产角色配置、数据库迁移/重载或原生运行器操作。R1-3实际进程证据仅为隔离固定文本子进程。
> #215 修正点（详见 `R1_R5_CLOSURE_INDEX.md`）：R1-1 创建改为**单写事务 TX-ALL**（无 `pending`/`failed` 残行）；权限读路径加名册/角色门控（R2）；`rotate-key` 加独占证明（R3）；宿主协议补齐 action/token/`expected_instance_id`/`launch_expires_at`（R4）；第一片保持 `server/` 范围、`cli/talk.py scan_agents` 移 R1-2、claim 守卫归属写清、`choice_id` 投影来源定死（R5）。

---

## 1. 依赖与前置

```
R1-1 后端数据地基
      运行器模型选择目录（choice_id）+ 项目角色身份 + 创建幂等/身份分配（原子）
      + 独立权限策略表（review_exempt 迁移）+ 服务端分级读路径切换 + 实例项目维度
  └── R1-2 一键配置宿主作业（身份档/Key 文件/启动前检查）+ 分级迁移收尾（bridge/提示词/启动校验/页面）
        └── R1-3 CLI 受管服务生命周期（宿主协议 claim/report + 世代/就绪 + 服务端状态/权限 + 页面启停）
              └── R1-4 外部桌面会话 + 删除/归档/退出边界 + 页面完整交互
                    └── I-4 发起者真实主动链路（**后置，不取消**）
```

硬依赖：

- R1-1 的**选择目录**是 R1-2 创建角色选择模型、R1-3 组装 argv 的前置；R1-1 的**创建原子性 + 操作表**是任何一键配置可重放的前提（F1）。
- R1-1 的**权限策略表**是分级迁移完成的判据（F4）：权限源必须先独立于名册表，才谈 bridge/页面收尾。
- R1-1 的实例 `project_id` 与 `launch_id` 列是 R1-3 就绪证明的前置（F3）。
- R1-4 的删除边界依赖 R1-3 的所有权与任务处理入口。
- 每片沿用既有节奏：**开发完成即暂停**，交本次独立复核；复核通过并收取后才开下一片；共享目录开发/复核期间不并行改码。

环境前提：Windows + Python（`.venv`）；测试统一用进程内 TestClient + 隔离临时库，不启动生产服务、不调用模型、不读 Key、不改生产数据库/名册/.talk/安装配置。

---

## 2. 切片总览

| 切片 | 范围 | 是否触碰 bridge/终端 | 交付形态 | 依赖 |
| --- | --- | --- | --- | --- |
| **R1-1** | 模型选择目录（`choice_id`）、项目角色身份、**创建幂等与身份分配原子提交**、独立权限策略表 + 分级读路径切换、实例项目维度 | **否** | 后端 + 迁移 + 测试 | 无 |
| R1-2 | 一键配置宿主作业（`role_provision_jobs` + 宿主脚本）、分级迁移收尾（bridge/提示词/启动校验/页面只读） | 是（提示词/启动参数），不重写终端 | 后端 + 脚本 + 前端只读 + 测试 | R1-1 |
| R1-3 | CLI 受管服务生命周期（宿主协议 + 服务端状态/权限 + 页面启停） | 是（受管 CLI 启停） | 宿主脚本 + 后端 + 前端 + 测试 | R1-2 |
| R1-4 | 外部桌面会话引导、**删除/归档/退出边界**、页面完整交互 | 是（外部会话只做引导） | 后端 + 前端 + 文档 + 测试 | R1-3 |
| I-4 | 发起者真实主动链路（受控等待消费者落地与真实验收） | 是（MCP/消费者） | 另立合同 | R1-4 后另排 |

批次刹车：R1-1 完成后暂停；R1-2 因涉及协议/权限/前端，默认单片后暂停；R1-3 涉及进程与部署，单片后暂停。R1-4 涉及删除/退出边界，单片后暂停。

---

## 3. 第一片 R1-1 详细设计（可独立审阅）

### 3.1 目标

在不改 bridge、不改终端、不做进程启停的前提下，把“角色生命周期”的**数据与后端接口地基**、**创建幂等与凭据恢复闭环**以及“固定分级不再作为权限源”的**服务端读路径**落地，使后续切片可以在稳定契约上继续。

### 3.2 确切文件与改动

| 文件 | 改动 |
| --- | --- |
| `server/models.py` | 新增 ORM：`RunnerModelChoice`（设计 §4.1.1）、`ProjectRole`（§4.1.2）、`RoleCreationOperation`（§4.1.3）、`ProjectRolePolicy`（§4.1.4）；`RunnerRegistry` 增 `control_kind`；`AgentInstance` 增 `project_id`/`process_started_at`/`launch_id`。新增 schema：`RunnerModelChoiceCreate`/`RunnerModelChoiceUpdate`/`RunnerModelChoiceOut`、`RunnerControlKindUpdate`、`ProjectRoleCreate`/`ProjectRoleUpdate`/`ProjectRoleOut`/`ProjectRoleListItem`、`RoleCredentialRotateOut`；`AgentInstanceUpdate`/`AgentInstanceOut` 增 `project_id`/`launch_id`/`process_started_at`；`RunnerOut` 增 `control_kind`（附加字段，不删/不改既有键） |
| `server/db.py` | 幂等迁移：新表随 `SQLModel.metadata.create_all` 建；`control_kind`/`project_id`/`process_started_at`/`launch_id` 按列存在性 `ALTER TABLE ... ADD COLUMN`；新增索引与部分唯一索引（设计 §4.4）；**一次性**从 `project_agents.decision_tier='decision'` 回填 `project_role_policies(review_exempt=1, source='migration_decision_tier')`，用迁移标记保证重复 `init_db()` 不重跑、不覆盖人工修改 |
| `server/routes/runners.py` | `GET /api/runners/{runner_id}/model-choices`、`POST /api/runners/{runner_id}/model-choices`（human，按选择维度唯一键 upsert）、`PATCH /api/runners/{runner_id}/model-choices/{choice_id}`（human，只改展示/来源/软下架）、`PATCH /api/runners/{runner_id}/control-kind`（human） |
| `server/routes/projects.py` | `GET /api/projects/{project_id}/roles`（`model.choice_id` 按设计 §5.2 投影来源解析）、`POST /api/projects/{project_id}/roles`（human，**TX-ALL** 单事务写 member/role/roster/binding/description + 操作行）、`PATCH /api/projects/{project_id}/roles/{member_id}`（human，改 `role_name`/`role_description`/`review_exempt`）、`POST /api/projects/{project_id}/roles/{member_id}/rotate-key`（human，独占证明见设计 §7.5）、`GET /api/projects/{project_id}/roles/{member_id}/tasks`（只读）；名册 sync、绑定/说明写入加新独占身份项目引用守卫（设计 §7.5，事务内校验，旧成员兼容） |
| `server/routes/instances.py` | `PUT` 接受并校验可选 `project_id`/`launch_id`/`process_started_at`；改为**只赋值请求显式出现的字段**；项目已声明后拒绝改写/清空；`launch_id` 非空后不可改写/清空；首片新非空关联422 instance_launch_not_supported，真实关联验证R1-3才开放；`GET` 支持 `project_id` 过滤 |
| `server/routes/groups.py` | 群创建（含创建者）/成员新增在同一写事务核新 managed 独占身份的项目归属，拒绝跨项目/全局引用；历史 imported/无角色成员不变 |
| `server/routes/tasks.py` | ① `_can_exempt_review` 改为设计 §8.4 的四条件读路径；② 创建守卫 `_ensure_target_agent` 增加“任务带 `project_id` 时目标角色未归档”；③ 新 managed 独占身份的任务引用守卫（created_by/target、实际根项目、计划任务路径，同事务）；④ **领取守卫** `claim_task` 增加“该角色在本任务 `project_id` 下未归档”（R5：守卫与创建守卫同在 R1-1，二者都列在此表并各有测试） |
| `tests/test_runner_model_choices.py`（新） | 选择目录读写、同 model 两连接并存、维度不可变、软下架过滤、权限、幂等 |
| `tests/test_project_roles.py`（新） | 角色创建/命名（空/中文）/重名/多角色隔离/归档后同名重建/归属/`member_id` 冲突不复用/`GET roles` 的 `choice_id` 来源（命中、失配 `null`、老名册 `null`） |
| `tests/test_role_creation_idempotency.py`（新） | **R1 故障注入与并发**：逐步注入（T-R1-a）、事务中途放弃模拟宕机（T-R1-b）、并发同 key（T-R1-c）、并发同 key 异载荷（T-R1-d）、响应丢失后 rotate-key（T-R1-e）、归档后同名重建（T-R1-f）；断言无部分事实、无 `pending`、不返 Key |
| `tests/test_role_rotation_exclusivity.py`（新，R3） | 独占身份轮换成功；共享两项目/仅旧名册引用/离册/在用实例/在用服务/在途任务/跨项目群引用分别命中稳定拒绝码；并发引用新增由写锁与 `identity_exclusive` 守卫收敛 |
| `tests/test_role_policy_migration.py`（新） | 迁移回填、迁移两次幂等、sync 两次权限不变、改旧 `decision_tier` 不重授/不撤、**离册休眠/回册恢复/归档休眠**（设计 §8.5 步骤 7–9）、老名册兼容、新角色不获豁免 |
| `tests/test_instances_project_dimension.py`（新） | 实例 `project_id`/`launch_id` 读写、省略字段保持原值、项目不可变、**launch 关联不可变**、名册校验、过滤 |

**明确不在 R1-1**：`role_service_state`、`role_service_launches`、任何进程启停、bridge/提示词改动、K28 入口改动、删除/归档入口（合同 §9 定义，实现放 R1-4）、页面 UI。

### 3.3 精确接口契约（R1-1）

```text
GET  /api/runners/{runner_id}/model-choices[?include_retired=true]
  200 → [ {choice_id, runner_id, model_id, model_source, provider_id,
           connection_ref, model_alias, model_display_name, source_kind,
           capabilities, retired_at, created_by, created_at, updated_at}, ... ]
  404 → runner not found

POST /api/runners/{runner_id}/model-choices        （human-only）
  body {model_id, model_source, provider_id, connection_ref,
        model_alias?, model_display_name?, source_kind?, capabilities?}
  201 新建 choice_id / 200 命中同选择维度（只更新展示/来源字段）
  403 agent / 404 runner 不存在 / 409 runner_retired / 409 choice_dimension_immutable / 422

PATCH /api/runners/{runner_id}/model-choices/{choice_id}   （human-only）
  body {model_display_name?, capabilities?, source_kind?, retired_at?}
  200 RunnerModelChoiceOut；改选择维度 → 409 choice_dimension_immutable；403/404/422

PATCH /api/runners/{runner_id}/control-kind （human-only）
  body {control_kind: "managed_cli"|"external_session"|"unknown"}
  200 RunnerOut（含新 control_kind）；403/404/422

GET  /api/projects/{project_id}/roles
  200 → [ {member_id, role_name, origin, archived, identity_exclusive,
           runner: {runner_id, runtime, display_name, status},
           model: {choice_id, choice_source, choice_binding_mismatch,
                   model_id, model_alias, model_display_name},
           role_description, binding_state,
           service: null}, ... ]     // R1-1 无服务状态 → service=null
   // choice_id 只来自创建操作映射并与当前绑定六维校验一致；否则 null
   // （choice_source ∈ creation_operation / creation_operation_mismatch / legacy_manual，设计 §5.2）
  404 → project not found；不返回 Key/owner_token/绝对路径/argv

POST /api/projects/{project_id}/roles        （human-only）
  body {role_name, runner_id, choice_id, role_description?, operation_key}
  201 → {role, member_id, api_key, reused:false, credential_version:1}   // api_key 仅此一次
  200 → {role, member_id, reused:true}                                   // 同 key 同指纹重放，不发 Key
  404 project/runner/choice 不存在
  409 operation_key_conflict / role_name_conflict / runner_retired / choice_retired
  422 role_name_invalid / 未知字段
  // 并发同 key：一个 201、一个 200 reused；**没有 operation_in_progress 状态**

PATCH /api/projects/{project_id}/roles/{member_id}   （human-only）
  body {role_name?, role_description?, review_exempt?}   // 不改 members.display_name
  200 → ProjectRoleListItem；404；409 role_name_conflict；422

POST /api/projects/{project_id}/roles/{member_id}/rotate-key  （human-only）
  200 → {member_id, api_key, credential_version}     // api_key 仅此一次
  404 role_not_found（无角色行）
  409 role_archived / rotate_not_managed_identity / rotate_member_not_agent
      / rotate_member_disabled / rotate_shared_identity_refused
      / rotate_legacy_roster_reference_refused / rotate_identity_off_roster
      / rotate_identity_in_use / rotate_group_reference_refused
      / identity_exclusive_reference_refused                    // 设计 §7.5

GET  /api/projects/{project_id}/roles/{member_id}/tasks
  200 → [非终态任务摘要]，只读，不改任务

PUT  /api/instances/{instance_id}
  body 新增可选 project_id / launch_id / process_started_at；只赋值显式出现的字段
  403 跨成员 / 409 instance_project_immutable / 409 instance_launch_immutable
      / 422 instance_project_not_in_roster
GET  /api/instances?project_id=...     // 附加过滤，缺省行为不变
```

稳定错误码（R1-1）：`operation_key_conflict`、`role_name_conflict`、`role_name_invalid`、`choice_not_found`、`choice_retired`、`choice_dimension_immutable`、`runner_retired`、`member_id_allocation_failed`、`api_key_generation_failed`、`instance_project_immutable`、`instance_launch_immutable`、`instance_project_not_in_roster`、`task_role_archived`、`role_archived`、`identity_exclusive_reference_refused`，以及上方 `rotate_*` 系列。

### 3.4 命名、身份与凭据分配规则（R1-1 落地）

- `role_name`：1–64 Unicode 码点，先 `strip()`，空白归 `422 role_name_invalid`；**项目内唯一且仅在未归档时占用**；不做全局唯一。
- `member_id`：`agent:<project_slug>.<role_slug>-<8hex>`，slug 由 `role_name` 归一化（NFKC、小写、非 `[a-z0-9]` 折叠为 `-`、截断；**全中文/空 slug 回退 `role`**）；`8hex = secrets.token_hex(4)`；主键冲突 → **重取后缀**（最多 8 次）→ `member_id_allocation_failed`；**绝不复用**已存在成员。
- `api_key`：`secrets.token_urlsafe(32)`；唯一列冲突重试（最多 8 次）→ `api_key_generation_failed`。
- **单写事务 TX-ALL**（设计 §7.2）：一次 `BEGIN IMMEDIATE` 事务内完成“读操作行 → 分配身份 → 写 `Member` + `ProjectRole` + `ProjectAgent`（名册，`business_role=NULL`、`decision_tier=NULL`）+ `ProjectRoleBinding`（从选择行复制六维 + `runner_id`）+ 可选 `ProjectRoleDescription` + 写 `RoleCreationOperation(member_id, committed_at)`”；任一步失败整体回滚，**六表零残留且没有操作行**。**不建 TX1、不写 `pending`/`failed` 状态列**（R1）。
- **重放语义**：同 key + 同指纹 → 返回既有角色、`reused=true`、**不发 Key**；同 key + 异指纹 → `409 operation_key_conflict`；并发同 key → 写锁 + 唯一约束决定唯一赢家，另一个读回 `reused`。**没有 `pending`/`failed`/`operation_in_progress` 状态**。
- **凭据恢复**：TX-ALL 提交后响应丢失或宿主写 Key 失败 → human `rotate-key`（**managed 独占证明通过**，设计 §7.4/§7.5）生成新 Key 并一次性返回，旧 Key 同事务失效。保留现有 Member.api_key 明文认证列，只禁止额外重放存储/GET再次读取；不提供重放取 Key。
- **归档后同名重建**：部分唯一索引 `WHERE archived_at IS NULL` 放行；新角色必得新 `member_id`。
- **R1-1 必含故障注入与并发测试**（设计 §7.7）：逐步注入、事务中途放弃模拟宕机、并发同 key、并发同 key 异载荷、响应丢失恢复、归档后同名重建；断言“无部分事实、无 `pending`、不返 Key、不双身份”。

### 3.5 权限策略与分级读路径切换（R1-1 落地）

- 新建 `project_role_policies(project_id, member_id, review_exempt, source, granted_by, granted_at, updated_at)`，**独立于 `project_agents`**。
- 一次性迁移：仅当迁移标记不存在时回填 `decision_tier='decision'` → `review_exempt=1, source='migration_decision_tier'`；写标记。
- `_can_exempt_review` 改为设计 §8.4 的**四条件读路径**：human 分支不变 → `project_id is None` 分支不变 → ① 成员为未禁用 agent → ② 当前 `ProjectAgent` 名册行存在 → ③ 若有 `ProjectRole` 则未归档（老名册无行时兼容放行）→ ④ 才读 `policy.review_exempt == 1`。**保留策略事实 ≠ 当前可用权限**（R2）。
- `decision_tier` 列、接口字段、sync 入参保持可写（旧客户端不破），但 `server/` 内**不再有任何行为性读取**。
- 本片只改服务端；bridge/prompt/启动校验/页面的彻底停用放 R1-2。

### 3.6 R1-1 验收标准

1. `python -m unittest tests.test_runner_model_choices tests.test_project_roles tests.test_role_creation_idempotency tests.test_role_rotation_exclusivity tests.test_role_policy_migration tests.test_instances_project_dimension` 全通过。
2. 既有 `tests.test_project_role_bindings`、`tests.test_projects`、`tests.test_tasks`、`tests.test_project_role_descriptions`、`tests.test_groups` 全通过（回归不破既有 C1–C4 语义）。
3. 老形态库执行 `init_db()` 两次幂等：只新增表/列/索引，不重建表、不改既有行；策略迁移行只出现一次。
4. 同运行器同模型两 provider/connection：两条 `runner_model_choices` 并存（`choice_id` 不同）；两个角色各绑其一，绑定六维事实分别正确。
5. 同项目重复 `role_name` → 409 `role_name_conflict`；不同项目同名 → 均成功；归档后同名重建 → 成功且新 `member_id`。
6. 同 `operation_key` 重放 → 返回既有角色、`reused=true`、不新建成员、**不再返回 Key**；同 key 异载荷 → 409 `operation_key_conflict`；**并发同 key → 一个 201（含 Key）、一个 200 `reused`（不含 Key），库中该 key 只有一行**；不存在 `operation_in_progress` 码（R1）。
7. **TX-ALL 故障注入**：在第 5 步 6 个写入点分别注入异常，以及“独立连接写入部分行后不提交即放弃”（模拟宕机）——每次断言六表零残留、**无 `pending` 行**、返回稳定码，随后同 key 同载荷重试成功（R1）。
8. `rotate-key` 对**独占 managed 身份**成功、旧 Key 立即 401、新 Key 可用、`credential_version` 递增；对 imported/共享、仅旧 `ProjectAgent` 名册引用、离册、在用实例/服务/在途任务、跨项目群引用分别返回设计 §7.5 的稳定拒绝码（R3）。
9. `PATCH` 改 `role_name` 后 `members.display_name` 不变、其它项目角色不变。
10. 迁移库中 `decision_tier='decision'` 成员的复核豁免行为与改动前一致；其它成员不获得豁免；`sync` 两次后不变；改旧 `decision_tier` 不重授/不撤；**离册休眠、回册恢复、归档休眠、老名册（无 `ProjectRole`）兼容放行**（设计 §8.5，R2）。
11. 实例省略字段保持原值；项目不可换/清空；已有 launch 非空值不能改/清空；首片新非空关联422（服务协议未实现）。以夹具预置非空 launch 测不可变，不能为此创建生产 launch 或把任意字符串视为就绪。
12. `GET /api/runners` 响应键集合与改动前完全一致（仅新增 `control_kind`，旧键不减不改名/语义）。
13. `rg 'decision_tier'` 在 `server/` 中不再出现于任何判定分支（仅剩列定义、兼容 schema、迁移、注释、群成员存储与模板文案）；`_can_exempt_review` 不读 `decision_tier`。
14. 改动文件保护校验：非本片文件 sha256 不变（见 `verification.json`）。
15. **归档守卫**：`_ensure_target_agent`（创建）与 `claim_task`（领取）在 `project_id` 上下文下都拒绝已归档角色（`task_role_archived` / `role_archived`），用直接构造归档数据的测试覆盖（R5；R1-1 无归档入口）。
16. **`GET roles` 的 `model.choice_id`**：创建操作命中且与当前绑定六维一致 → 返回该 `choice_id`；绑定被手工改写 → `null` + `choice_binding_mismatch=true`；老名册/手工绑定 → `null` + `choice_source='legacy_manual'`（R5）。
17. 新独占身份跨项目/全局群与任务、旧名册引用新增，事务内守卫均拒绝；历史成员原路径不变。轮换在用证明包含 target 与 created_by。
18. 服务表未实施时不查询不存在的表；构造未来表核验在用服务分支。操作重放在目录下架后仍回原身份，不返Key。

### 3.6.1 R1-1 实施与独立验证记录（2026-10-11）

- #216 后端实现经 #217 定向补正，Codex 核实际代码后独立通过，并按 217→216 收取。原 #216 自报与第一次审查 needs_rework 保持，收取表示补正链闭合。
- 同一 SQLite 写事务覆盖实例归属校验/写入与六类引用守卫；TX-ALL 在已提交操作重放判定后用事实 SQL 复查项目。真实 WAL 双连接确认实例竞争一方 200、另一方 409，六类守卫持有写锁，项目注销先行则创建 404 且六表无新增。
- 独立必要 13 模块 278 项、附带 12 模块 196 项、任务 Hall 两项共 476 项实际运行通过，零失败/错误/跳过（包含继承类复跑）；三项原子化手段中和各预期失败、正式代码各通过，作为单独对照。六表实际 INSERT 后故障注入、迁移幂等/人工改权、原绑定/快照及公共无密合同通过。
- 原两个任务 Hall 测试的沙箱 WinError 5 记录保留；本次在受权的隔离临时数据库、随机回环端口及固定文本 Python 子进程环境补测通过，不涉及原生模型或生产服务。
- 796 非片跟踪文件与 294 原产物指纹保持；补正只改五源/三测试。实际代码/旧审查/原报告/独立日志与回执见本机 `.tmp/role-lifecycle-r1-1-final-review/`，运行代码不依赖这些产物。
- 本轮后端批次收尾后暂停，页面一键配置、身份档/Key 文件、分级提示词迁移与真实服务生命周期不在本片。可在项目根使用 `.venv/Scripts/python.exe -X utf8 -m unittest` 运行 §3.6 所列隔离测试；无需读取或使用生产 Key。页面核心流程待后续里程碑统一验收。

### 3.7 R1-1 已知限制（如实登记）

- 无服务启停、无就绪判定、无所有权/退出清理（`role_service_state`/`role_service_launches` 只在合同定义，R1-3 实现）。
- 无宿主侧一键配置（身份档/Key 文件/启动前检查）——`POST roles` 只完成服务端原子部分；跨宿主步骤 R1-2。
- 无删除/归档入口实现（合同 §9 已定契约，入口在 R1-4）。
- bridge 仍解析/注入 `decision_tier`（R1-2 处理）；页面仍按旧方式展示。
- `task_role_archived`/`role_archived` 守卫（创建 + 领取两处）在 R1-1 落地，但归档入口在 R1-4，故 R1-1 只做守卫与测试、不产生归档数据（R5）。
- `cli/talk.py scan_agents` 的分级兼容清理**不在 R1-1**（保持第一片为 `server/` 七源范围（新增 groups.py 引用守卫）），随 R1-2 的 bridge/页面片一起收尾（R5）。
- 本片**不**做 `Member.api_key` 哈希迁移，也**不**做全局凭据管理（设计 §15.2 D7）；`rotate-key` 只是独占身份的凭据恢复。
- 真实运行器能力（版本/额度/登录/隔离）未测，保持 `not_run`。写锁沿用 SQLite 默认等待预算；未做吞吐压测或生产多 worker 压测。
- 项目注销沿用既有清理边界：清理绑定/说明，未扩展清理名册、角色/创建操作/策略历史或全局成员/凭据。

---

## 4. R1-2 已完成与后续切片

### R1-2 一键配置作业与分级迁移收尾

- 已新增 `role_provision_jobs` 与 `scripts/role_provision.py`；默认离线dry-run（无 `--dry-run` 参数），apply才写身份档/仓库外Key。复用原operation_key，不重建身份/重发Key。最终[配置合同](ROLE_PROVISION_CONTRACT.md)/[验收指南](../guides/ROLE_PROVISION_ACCEPTANCE.md)已发布。
- 服务端四个human-only入口：作业创建/读取、ACK、本人档案路径登记。凭据版本/revision/attempt CAS、轮换后显式重开、精确409白名单、choice指纹及原子Key/锁发布已验证。
- 分级迁移收尾：`bridges/cli_bridge.py`（移除分级注入、`--decision-tier` 弃用兼容、不再注入 `TALK_DECISION_TIER`、讨论收口人规则调整）、**`cli/talk.py`（`scan_agents` 不再因缺失/冲突分级报错——由 R1-1 移入本片，R5）**、`scripts/kimi_k28_executor.py`、`scripts/adapter_closeout.py`、`server/hall_types.py`、`web/workspace.js`（主显示去分级）。
- 独立验收：Codex最终684项Python证据集合通过；#222另重点143项通过，零失败/错误/跳过，不叠加；原Node59项未变沿用。junction缺失父目录零副作用、原221负向敏感性、Windows实际owner PID与中断恢复闭合，固定分级不再影响行为/提示。
- 业务14源/20测试；本次仅调整两处源码正式合同引用，无执行逻辑变化。页面一键配置/启停/删除尚未实现；文件symlink权限受限not_run，恶意动态路径替换防护与实际运行器能力未验。§3.7保留R1-1当时限制，当前配置/分级状态以本节为准。

### R1-3 CLI 受管服务生命周期

- 已新增 `role_service_state`/`role_service_launches`（设计 §4.1.5/§4.1.6）；宿主脚本 `scripts/role_service_host.py serve`常驻持有/执行，start/stop/start-all只写请求，status只读；claim/report、所有权token、就绪轮询、活句柄与实际OS `(pid, process_started_at)`核对已验。
- 服务端：设计 §5.3 六个入口；权限 human-only 写、agent 只领取/回报自己的 launch；只存期望/世代/观测，不 spawn 进程。
- 能力矩阵：页面按`managed_cli`与服务投影允许请求；宿主另核三档/本人Key/choice与绑定指纹、真实入口argv及能力登记，未经原生核验配方稳定拒绝。按钮可用不自证实际模型/隔离能力。
- 验收：跳过已运行、逐角色结果、部分失败定向重试、单独停服不影响他人、`generation` 并发互斥、**本次 `expected_instance_id` + `launch_id` + 世代 + 时间窗（`claimed_at ≤ report ≤ launch_expires_at`）四条件就绪**、report 必须携带并核验 claim/owner token + 领取身份 + host、旧世代/旧动作迟到 `stale_report`、旧心跳不救场、`start`/`stop` 动作分离与停止 `stopped`/`failed` 回报闭环、实例项目与 launch 关联不可变、旧 launch 超时不污染新世代、PID 复用不误认领/不误杀；**真实运行器验证保持 `not_run`**。
- #223/#224原失败与partial经Codex修正、#225/#226独立复核闭合，任务整链已收取。最终独立host28项/服务55项全通过，真实回环4项、旧源码负向5/6检出；Codex最终探针及原始日志互证。正式[服务合同](ROLE_SERVICE_CONTRACT.md)/[人工验收指南](../guides/ROLE_SERVICE_ACCEPTANCE.md)已同步。当前暂停人工页面验收，不开始R1-4。

### R1-4 外部桌面会话、删除与退出边界

- `external_session` 角色的页面引导（人工打开/登录）与“未知/未声明”展示。
- 删除/归档入口：设计 §9 前置检查（服务运行/在途任务拒绝）、单事务归档、可选全局禁用走与 `rotate-key` **同一** `_prove_exclusive_identity` 独占证明（设计 §7.5）、`task_role_archived`/`role_archived` 守卫在真实归档路径上的竞态测试。
- 宿主机正常退出清理、异常退出边界如实登记。
- 页面：主显示五项 + 服务结果投影 + 三字段就绪（native_login/model_alias/service）+ 加载态；任务状态留任务列表。

### I-4（后置，不取消）

发起者主动真实链路按既有 [INITIATOR_MODE_CONSUMER.md](../guides/INITIATOR_MODE_CONSUMER.md) 与 C2 合同另行排片，承接全部 T/W/取消/排队边界与真实宿主验收；**本计划不将其并入角色生命周期切片**，也不因本功能推迟而取消。

---

## 5. 验证与测试策略（全片通用）

- **单元/契约**：进程内 TestClient + `tests/test_support.RouteTestCase` 隔离临时库；`python -m unittest tests.<module>`。
- **迁移**：构造旧形态库 → `init_db()` 两次 → 断言列/索引新增、数据不变、策略迁移只一次；再 `sync` 两次 → 权限不变；再覆盖设计 §8.5 的离册/回册/归档/改旧 `decision_tier` 行。
- **幂等/事务（R1）**：同 key 重放/异载荷/并发；TX-ALL 逐步注入失败与事务中途放弃断言无部分事实、无 `pending`；`rotate-key` 后旧 Key 401。
- **凭据独占（R3）**：共享/旧名册/离册/在用/并发引用新增的稳定拒绝码；独占成功路径与 `identity_exclusive` 守卫。
- **权限**：agent 调用 human-only 入口 403；human 调用实例上报 403；跨成员实例 403（既有）；agent 不可自授豁免。
- **隔离**：跨项目同名角色、跨项目实例过滤、跨角色绑定互不影响；同 model 两连接并存。
- **实例边界（R4）**：省略字段保持原值、项目不可变、`launch_id` 不可变、`expected_instance_id` 命中校验、错误 host/project/token/世代/超时拒绝。
- **不做的**：不重跑未变业务大套件、不调用真实模型、不启停生产服务、不做浏览器操作、不为填能力矩阵制造真实等待任务。
- **前端片**：按仓库既有做法用 Node 同进程契约测试 + 静态检查；浏览器人工验收交由用户。

---

## 6. 交付与门禁

- 每片完成后按 [TASK_WORKFLOW.md](../guides/TASK_WORKFLOW.md) 出具 `talk-delivery-1` 结构化交付（真实任务号、实际基线、变更文件、验证、限制、进度草稿）。
- 开发完成即暂停，交本次独立复核；复核者须独立检查实际代码，不只采信开发者结论。
- 正式文档发布（`docs/spec/ROLE_LIFECYCLE_DESIGN.md`、`docs/spec/ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md`）由协调方在复核通过后执行；本计划不自行发布。
- **产品裁决口径（F6 修正）**：原计划要求“P1–P8 在对应切片开工前由人类确认”。本修订稿已把 P1–P8 全部按用户已授权方向与保守实现选择**纳入合同**（设计 §15.1），**不再要求重复批准**；真正改变权限/自动取消/全局凭据存储等事项记为**待授权后置边界 D1–D7**（设计 §15.2），不得夹带进任何切片。
- **R1-3 真实能力口径（R4）**：宿主 claim/report 协议与停止闭环在本合同内定义完整，但 R1-3 的真实运行器验证仍为 `not_run`；纸面合同不冒称适配通过。
