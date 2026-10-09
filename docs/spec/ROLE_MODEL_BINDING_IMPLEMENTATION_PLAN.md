# 实施计划：通用角色运行器与模型绑定

> 状态：**B1a 后端已实现、独立复核通过并收取；B1b 尚未实施**（2026-10-09）。依据 [正式合同](ROLE_MODEL_BINDING_DESIGN.md)；设计 #190–#192 和开发 #193 的原始交付/失败记录保持，#194 定向修正闭合问题。
> B1a 经 Codex 独立 124 项相关测试及原失败边界探针通过，193/194 已收取，等待 [API 人工验收](../guides/ROLE_MODEL_BINDING_ACCEPTANCE.md)。本轮未重载生产服务、迁移生产库或调用模型；人工门禁释放后再派 B1b。未重跑全量 881 项或环境失败的 pristine 对照。
> 设计独立验证与本地证据索引见合同开头；单条 SQL 原文与 #192 草稿一致。实际运行证据 B2、页面、进程管理和真实宿主能力仍各自待后续。

## 0. 拆片总览（v3：B1 拆为 B1a + B1b）

| 片 | 范围 | 依赖 | 当前状态 |
|---|---|---|---|
| **B1a** | 存储与契约面：`runner_registry` + `project_role_bindings` 两表、幂等增量迁移、全局登记 API、角色绑定 API、`GET /agents` 附加 `binding`/`binding_state`（含 §4.4 有效性阶梯）、**单语句事实读取助手 `read_role_binding_facts`**、校验与错误码 | 本合同 §3–§6、§10 被批准 | ✅ 后端复核/收取通过；待人工 API 验收 |
| **B1b** | 任务侧：`agent_tasks` 两列 + 唯一写入点（`_create_task_with_hall`）复用 B1a 的单语句事实读取、快照状态阶梯、不可变性 | B1a 的同名助手与状态枚举 | ⏳ 设计通过；B1a 人工验收后派 |
| B2 | **实际运行证据 + 配置/实际对照**：字段、attempt 证据锚点、`binding_match_config` / `binding_match_actual` | **必须另开设计片**（见 §3.1 的 R-B2-1…6）；B1a/B1b 只提供配置侧 | ❌ 本设计不定义字段 |
| B3 | MCP/工具消费：`talk_list_agents` 只读暴露 `binding`/`binding_state`；不新增工具、不输出任何 match | B1a | ⏳ B1a 已收取，本片尚未派发 |
| B4 | 页面：角色页只读展示运行器/来源/连接标识/模型与 `unknown` 降级 | B1a（+B2 才有实际值） | ⏳ 待 B1a；产品展示名 D-5 未决 |
| B5 | 手动启停 / 随项目自动启动 / 桌面生命周期 | 进程所有权合同（未批准）+ B1a | ❌ 本设计不承诺 |
| B6 | schedule 项目化并携带项目绑定快照 | B1a/B1b + 独立合同 | ❌ 后置 |
| B7 | 不匹配处置开关（D-2 决策后） | B2 + 人工决策 | ❌ 依赖决策 |
| B8 | WorkBuddy 等其它运行器的字段/执行侧适配 | 外部宿主核实 | ❌ 未核实 |

**为什么拆**：v1 把“登记 + 绑定 + 迁移 + 任务快照”压成一个 B1，验收面过大，且其中的任务快照部分依赖 F1 的一致读取方案与 F2 的唯一写入点。拆开后 B1a 只有两表、两套 API 与**一个单语句事实读取助手**（可独立验收），B1b 只动任务创建路径（改动面小、可用事件计数与交错测试直接验收）。

---

## 1. B1a：登记 + 绑定 + 迁移（后端已实现，待人工验收）

### 1.1 目标（可机械验收）

1. 新增全局运行器登记表与 API（仅 human 可写）。
2. 新增项目角色绑定表与 API（仅 human 可写；读取沿用当前已认证成员读合同）。
3. 读取时的有效性阶梯（§4.4）如实报告离册/未注册/被禁用/非 agent/运行器缺失或停用；**保留存储不等于有效**。
4. 提供**单条 SQL** 的事实读取助手 `read_role_binding_facts(session, project_id, member_id)`：**无绑定行时仍返回 1 行**，一次取齐状态判定与全快照字段（R1）。
5. 老库/旧客户端继续可用，无破坏性变更、无虚构回填。

### 1.2 改动文件（预期清单，实施时以实际 diff 为准）

| 文件 | 改动 |
|---|---|
| `server/models.py` | 新增 `RunnerRegistry`、`ProjectRoleBinding` ORM；新增 schema（`RunnerCreate/RunnerUpdate/RunnerOut`、`RoleBindingUpdate/RoleBindingOut`，均 `extra="forbid"`）；枚举常量 `MODEL_SOURCES` / `RUNNER_ADAPTER_STATUSES` / `ROLE_BINDING_STATES`；新增助手：安全 token 归一化/校验、`binding_fingerprint`、`resolve_role_binding_state`（阶梯 §4.4 + `partial` 边界 §4.5）、**单语句事实读取 `BINDING_FACTS_SQL` + `read_role_binding_facts`（§2.3 的同一段 SQL）** |
| `server/db.py` | 新表索引 `CREATE INDEX IF NOT EXISTS`；新表由 `SQLModel.metadata.create_all` 建立；**不改引擎参数（§7.3）** |
| `server/routes/runners.py`（新） | `GET/POST /api/runners`、`PATCH /api/runners/{runner_id}`（`capabilities` 定量校验 §3.3） |
| `server/routes/projects.py` | `_project_agent_outs` 批量附加 `binding`/`binding_state`（避免 N+1，复用现有一次 `IN (...)` 查询风格，`server/routes/projects.py:145-218`）；新增 `GET/PUT /api/projects/{project_id}/agents/{member_id}/binding`；`PUT` 用单条 upsert（§4.3）；项目删除时清理绑定行（`:668-689`） |
| `server/main.py` | 挂载新 router |
| `tests/test_runners.py`（新） | 登记权限/校验/幂等/枚举/capabilities 定量 |
| `tests/test_project_role_bindings.py`（新） | 绑定读写、校验、有效性阶梯、并存行与版本、指纹规则、sync/删除兼容、upsert 并发收敛、**单语句事实读取覆盖无绑定四例** |

**不在 B1a**：`bridges/**`、`web/**`、`TALK/client/**`、任何启停/自动启动代码、任何真实模型调用、任何 `agent_tasks` 改动。

### 1.3 具体接口

见 `ROLE_MODEL_BINDING_DESIGN.md` §3.4 / §4.3。B1a 必须实现的最小集合：

```
GET    /api/runners
POST   /api/runners
PATCH  /api/runners/{runner_id}
GET    /api/projects/{project_id}/agents                  # 响应附加 binding + binding_state
GET    /api/projects/{project_id}/agents/{member_id}/binding
PUT    /api/projects/{project_id}/agents/{member_id}/binding
```

项目不存在时的 404 语义**保持原样**（含事实读取返回 `project_exists = 0` 的情形，见合同 §11）。

### 1.4 迁移策略

- 新表：`SQLModel.metadata.create_all(engine)` 自动建（`server/db.py:44-49`），无需手写 DDL。
- 索引：`runner_registry(runtime)`、`project_role_bindings(project_id)`、`project_role_bindings(runner_id)` 按需 `CREATE INDEX IF NOT EXISTS`。
- **B1a 不新增 `agent_tasks` 列**（那属于 B1b）。
- 在旧形态库上重复 `init_db()` 必须幂等（参照 `tests/test_project_development_requirements.py:220-320`、`tests/test_project_controller_assignment.py:1209-1293`）。

### 1.5 事务边界与并发

| 操作 | 事务边界 | 并发语义 |
|---|---|---|
| `PUT binding` | 单 session：校验读（项目/成员/名册/登记）→ **单条 upsert**（`INSERT ... ON CONFLICT(project_id,member_id) DO UPDATE`）→ `commit()` | last-write-wins（D3）；并发新建同一 `(project_id, member_id)` 不会互相 409，由 upsert 收敛到后提交者 |
| `GET binding` / `GET agents` | 只读；行事实用**单条 SQL** 联查（§4.4 阶梯所需全部事实），不 `UPDATE`、不自动清理、**不做第二条补查询** | 读到的是某一个已提交状态，不撕裂 |
| `runner_id` 有效性 | upsert 之前的读校验 | 残余窗口：登记恰在同瞬间改 `retired` → 可能落一行引用 retired 运行器的绑定；读取时如实报 `runner_retired`，不误报 `bound`（§4.3） |

### 1.6 验收标准（B1a）

1. 六个接口按 §1.3 可用；写接口 agent 调用 403；读接口任意已认证成员可用。
2. 同名 `model_id` 在不同角色行（不同 `member_id`）或不同来源/连接下产生**不同指纹或不同行**；两个不同角色内容完全相同时指纹相同但仍是**两行**（不合并）。
3. 同一角色先后两次 `PUT` 是**同一行的版本变化**（指纹变化），不产生第二行。
4. 未配置角色返回 `binding: null` + `binding_state="unconfigured"`（不伪造默认运行器/模型）。
5. 有效性阶梯：`member_missing` / `member_disabled` / `not_in_roster` / `not_agent` / `partial` / `runner_missing` / `runner_retired` / `bound` 各自可构造，优先级按 §4.4 严格命中；`partial` 只由绑定行存储必填字段触发（§4.5），**不吞掉** `runner_missing`。
6. 离册（`POST /sync` 全量替换移除名册行）后绑定行**保留**且 `binding_state="not_in_roster"`；回册后自动回到 `bound`。
7. **事实读取无绑定分支**：已入册无绑定 / 禁用无绑定 / 未注册无绑定 / 非 agent 无绑定**四例都返回恰好 1 行**（不是 0 行），且 `binding_exists = 0`、身份/名册/项目字段齐全（R1）。
8. 禁止字符/超长/疑似凭据 → 422；不存在的 `runner_id` → 422；`retired` → 422；未知字段 → 422；`capabilities` 超量/空白/重复/超长 → 422；项目不存在 → 404。
9. 老库迁移幂等；不产生虚构模型数据。
10. 现有测试无新增失败（回归）。
11. 改动文件不越出 §1.2 清单；仓库内无密钥；未改 bridge/web/SDK；UTF-8 显式写入，`git diff --check` 干净。

### 1.7 必要测试矩阵（B1a）

| # | 用例 | 断言要点 | 参考 |
|---|---|---|---|
| A1 | 旧形态库 → `init_db()` | 新表存在；再跑一次幂等 | `tests/test_project_controller_assignment.py:1209-1293` |
| A2 | 登记：human 建/改 | 201/200；`runtime`/`runner_id` 不可改（422）；重复 409；未知字段 422 | 新 |
| A3 | 登记：agent 写 | 403；读 200 | `server/routes/projects.py:49-51` 模式 |
| A4 | `capabilities` 定量 | 33 条→422；空白项→422；重复项→422；单条 65 码点→422；合法 0/32 条→200 | 新 |
| A5 | 绑定：完整 builtin | `PUT` → 200；`GET /agents` 出现 `binding`，`binding_state="bound"` | 新 |
| A6 | **并存行**（F5） | 两个不同 `member_id` 同时各一行；其中一个与另一个同 `model_id` 不同 `connection_ref` → 两行、两指纹；行主键数 == 2 | 新 |
| A7 | **同角色先后版本**（F5） | 同一 `(project_id, member_id)` 连续两次 `PUT` → 仍 1 行、指纹变化、`updated_at` 更新；无第二行 | 新 |
| A8 | **同指纹不同角色**（F5） | 两行内容完全相同 → 指纹相同但 `GET` 仍返回 2 条、互不合并 | 新 |
| A9 | 绑定：必填缺失/空白/超长/非法字符/疑似凭据/未知字段 | 全部 422 | `server/models.py:241-305` 风格 |
| A10 | 绑定：`runner_id` 不存在 / retired | 422 | 新 |
| A11 | 绑定：目标不存在/禁用/非 agent/未入册 | 404；`binding: null` 清除对无行/不在名册幂等 200 | `tests/test_project_role_descriptions.py:309-346` |
| A12 | **离册 → 回册**（F3） | sync 移除→行保留+`not_in_roster`；sync 加回→`bound`；两阶段行数恒为 1 | 新 |
| A13 | **状态优先级组合**（F3） | 离册且 runner retired → `not_in_roster`（序 3 优先于序 8）；禁用且离册 → `member_disabled`；无行且离册 → `not_in_roster` | 新 |
| A14 | 绑定写不影响其它维度 | `business_role`/`decision_tier`/`controller_*`/任务权限不变 | `tests/test_project_role_descriptions.py:512-590` |
| A15 | `POST /sync` 全量替换 | 名册被替换但绑定行保留 | `tests/test_projects.py:287-305` |
| A16 | 项目删除 | 绑定行被清理；名册孤儿行不追改 | `server/routes/projects.py:668-689` |
| A17 | **upsert 并发收敛**（D3） | 两 session 并发对同一不存在的 `(project_id, member_id)` 写入 → 无 IntegrityError/409，最终 1 行且等于后提交者 | 新 |
| A18 | 载荷计数保护 | `talk_list_agents` 响应新增 `binding`/`binding_state` 后 `development_requirements` 仍只出现 1 次 | `tests/test_project_development_requirements.py:404-419`（B3 相关，B1a 先加冒烟断言） |
| A19 | **R1 事实读取：无绑定四例** | 已入册无绑定/禁用无绑定/未注册无绑定/非 agent 无绑定：`read_role_binding_facts` 各返回**恰好 1 行**，`project_exists=1`、`binding_exists=0`；已注册三例 `member_exists=1`，未注册例 `member_exists=0`，身份/名册字段正确 | 新（对合同 §7.3 SQL） |
| A20 | **R1 事实读取：离册有/无绑定 + 项目不存在 + bound 全字段** | 离册有绑定→`not_in_roster` 且行值照存；离册无绑定→`not_in_roster`；项目不存在→`project_exists=0`（走 404）；bound→27 列全齐、六个快照字段非空 | 新（同上） |
| A21 | **单语句性质（行为证据）** | SQLAlchemy `before_cursor_execute` 事件计数：带项目分支**恰好 1 条** SQL；`project_id=None` 分支 **0 条**；不得出现第二条补查询 | 新 |
| A22 | 回归 | `test_projects.py`、`test_project_role_descriptions.py`、`test_project_development_requirements.py` 全绿 | 既有 |

---

## 2. B1b：任务绑定快照（设计通过，B1a 后派）

### 2.1 目标（可机械验收）

1. `agent_tasks` 幂等增列 `target_binding_snapshot`(JSON) / `target_binding_state`(TEXT)。
2. **唯一写入点**：`_create_task_with_hall` 内、构造 `AgentTask` 之前解析（F2）；普通/子任务/schedule 三条路径**两列一律非 NULL**。
3. **单语句一致读取**（F1/R1）：**复用 B1a 的 `read_role_binding_facts`**（同一段 SQL、同一 helper，不复制第二份），取得点按 SQLite 事务视图规则，单条 SQL 内全部事实一致；与任务/Hall 同一次 commit。
4. 写入后不可变；配置与名册变更只影响新任务；旧任务 NULL 保持“未记录”。
5. **不新增任何读取回执字段/常量**（R3、D8）。

### 2.2 改动文件（预期清单）

| 文件 | 改动 |
|---|---|
| `server/models.py` | `AgentTask` 增两列；`AgentTaskOut` 增同名字段；`resolve_target_binding_snapshot(project_id, target_member_id, session)`（内部**调用 B1a 的 `read_role_binding_facts`** + 阶梯 + 快照构造，**无 read_receipt**） |
| `server/db.py` | `agent_tasks` 幂等增列；`CREATE INDEX IF NOT EXISTS ix_agent_tasks_target_binding_state`；**不加任何回执/计数列** |
| `server/routes/tasks.py` | `_create_task_with_hall`（`:1408`）**函数最开头**构造快照并作为 `AgentTask(...)` 参数写入；**不改** `create_task` 的权限/校验分支、不改 claim/complete/heartbeat |
| `tests/test_task_binding_snapshot.py`（新） | 快照各状态、单语句一致性（事件计数 + 两连接交错）、唯一写入点（限定生产路径）、三条创建路径非 NULL、不可变性、alias 变更留证 |

**不在 B1b**：任何按快照拒绝 claim/创建的分支；任何 `reported_*`/`binding_match` 字段；任何读取回执持久字段；任何 bridge/web 改动。

### 2.3 一致读取方案（机械要求）

```python
def resolve_target_binding_snapshot(*, project_id, target_member_id, session):
    if project_id is None:
        return build_snapshot(None, "no_project")     # 不执行 SQL：语句数 == 0
    row = read_role_binding_facts(session, project_id=project_id, member_id=target_member_id)  # B1a 的单语句助手
    state = resolve_role_binding_state(row)           # §4.4 阶梯 + §4.5 partial 边界
    return build_snapshot(row, state)
```

`read_role_binding_facts()`（B1a）实现为**一次** `session.execute(text(BINDING_FACTS_SQL), {"project_id": ..., "member_id": ...}).mappings().one()`。

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

- `project_id is None` → 不执行 SQL，直接 `state="no_project"`，字段全 `null`（仍是同一套构造，仍写非 NULL 两列）。
- 必须**单条语句**：隔离测试用 SQLAlchemy `before_cursor_execute` 事件统计 `resolve_target_binding_snapshot` 期间的语句数，断言带项目分支 `== 1`、无项目分支 `== 0`；并断言**没有**“先查绑定行、0 行再补第二条查询”的路径（R1）。
- `project_exists = 0` → 不构造任何绑定状态；事实助手不固定 HTTP 错误码。项目名册/绑定 API 映射 **404**，任务快照助手保留任务创建的 **400**（合同 §11、`server/routes/tasks.py:104-106`）。
- 使用 Core/文本列选择，避免 ORM autoflush。子任务授权预扣已执行 UPDATE，沿用其真实事务；不另发 BEGIN 或提前 commit。改查询/flush 顺序须验证视图及回滚边界（合同 §7.3）。
- **不**新增 `BEGIN`/`BEGIN IMMEDIATE`；**不**改 `server/db.py:41` 引擎参数。
- **不**写 `read_receipt`、不写“语句计数常量”、不新增任何列（R3）。

### 2.4 不可变性

- 已有任务的快照两列在 `claim` / `heartbeat` / `complete` / `cancel` / `requeue-expired` / 重领路径中**不被更新**；API 响应可读回原快照，质量子任务只构造子任务自身快照；绑定 `PUT` 只碰 `project_role_bindings`。
- 不为旧任务回填；`target_binding_state IS NULL` 读取方展示“未记录”。
- **alias 变更逐版本留证**：同一角色只改 `model_alias` 时指纹不变，但新任务快照必须存新 alias，旧任务快照逐字节不变（合同 §2、§7.4）。

### 2.5 验收标准（B1b）

1. 三条创建路径（普通带项目 / 普通无项目 / 子任务 / schedule 物化，共四种情况）新任务两列**均非 NULL**，`state` 分别为 §4.4 对应值或 `no_project`。
2. 单语句一致性：带项目分支事件计数 `== 1`、无项目分支 `== 0`；真实两连接交错压力下，快照状态永不出现“从未同时存在的组合”（负对照必须能复现撕裂）。
3. 快照与任务/Hall 同一次 commit；构造失败/关系冲突回滚后不留任务行也不留快照。
4. 绑定变更、离册、回册后：旧任务快照逐字节不变；新任务取新值；**只改 alias 时同样逐字节保留新旧两版**。
5. 旧任务行两列 NULL 可读，不被回填。
6. `target_binding_snapshot` JSON 键集合 = 合同 §7.1 的 13 个键，**不含** `read_receipt`。
7. 现有测试无新增失败；`git diff --check` 干净。

### 2.6 必要测试矩阵（B1b）

| # | 用例 | 断言要点 | 参考 |
|---|---|---|---|
| B1 | 迁移 | 两列存在；旧行 NULL；重复 `init_db()` 幂等；**无新增回执列** | `server/db.py:74-165` |
| B2 | 普通任务带项目 `bound` | `POST /api/tasks` 后任务两列非 NULL，快照字段与绑定行一致；快照键集合不含 `read_receipt` | 新 |
| B3 | **普通任务无项目** | 两列非 NULL；`state=no_project`；字段全 null；**语句计数 0** | 新 |
| B4 | **子任务**（D1） | 父/子各自快照独立；按子任务 target 重新解析；父快照不被覆盖 | `server/routes/tasks.py:386-441` |
| B5 | **schedule 物化批量**（F2） | 一次 `run-due` 物化 N 个任务 → 全部两列非 NULL、`state=no_project`、不报错 | `tests/test_tasks.py:3023-3082` |
| B6 | **唯一写入点（限定生产插入路径）** | 静态检查只在 `server/**` 内枚举 `AgentTask(` 构造点，断言只有 `_create_task_with_hall`（**测试 fixture 不纳入**，不写全仓库禁令）；两处调用点（`:1644`、`:1509`）都拿到非 NULL 两列 | 新 |
| B7 | **单语句读断言（行为证据）** | SQLAlchemy `before_cursor_execute` 事件计数：带项目分支恰好 1 条 SQL；无项目分支 0 条；**不以任何自报常量代替** | 新 |
| B8 | **真实两连接交错（F1）** | 用隔离假库 + 两连接：naive 多读可复现撕裂；同交错下 `resolve_target_binding_snapshot` 永不撕裂；无已有持久事务时提交在视图取得前→新值、之后→旧值；已有事务依其视图读取 | `.tmp/role-model-binding-design-fix/probe_f1_consistency.py` 的同一实验结构（改成 pytest 隔离库） |
| B9 | **同次提交原子性** | 人为让 commit 失败（关系冲突）→ 回滚后无任务行、无 Hall 行 | `server/routes/tasks.py:1686-1693` |
| B10 | 不可变性 | 改绑定 + claim + complete 后快照 JSON 逐字节不变 | 新 |
| B11 | 配置变更只影响新任务 | 绑定 `PUT` 后旧任务快照不变、新任务取新值 | 新 |
| B12 | **离册 → 新任务 → 回册**（F3） | 离册时新任务 `state=not_in_roster` 且行值照存；回册后新任务 `bound`；两个历史任务快照各自保留 | 新 |
| B13 | 身份/名册组合 | `member_missing` / `member_disabled` / `not_agent` 各自 `state` 与 null 布局正确 | 新 |
| B14 | `partial` / `runner_missing` / `runner_retired`（**R2 统一**） | `partial` 仅由**绑定行存储必填五项**缺失/不合法触发（缺失项→`null`，指纹 `null`），**派生 `runtime` 不参与**；`runner_missing` → `state=runner_missing`、`runtime=null`、**`binding_fingerprint=null`**；`runner_retired` 且六值可解析 → `binding_fingerprint` 非 null；三者互不吞并（`runner_missing` 不得被 `partial` 抢先） | 新 |
| B15 | 旧任务兼容 | NULL 状态可读、不被回填 | 新 |
| B16 | 旧客户端请求 | 不带新字段的 `POST /api/tasks` 仍 201；响应新增字段不影响解析 | `tests/test_tasks.py:173-220` |
| B17 | **禁止实际对照字段** | `AgentTaskOut` / `GET agents` 不含 `binding_match*`；以 schema 键集合断言 | 新 |
| B18 | **alias 仅变更也要逐版本留证**（R2） | 同一角色两次 `PUT` 只改 `model_alias` → 指纹**不变**；task-1 快照 alias=旧值、task-2 快照 alias=新值，两者逐字节保留；断言不得把“指纹相同”写成“调用配置相同” | 新 |
| B20 | **错误码与已有事务**（发布澄清） | 不存在项目：项目接口 404、任务创建仍 400；共用事实助手不抛固定 HTTP 错误。隔离 WAL 两连接验证已有读事务保持旧视图、写事务可见自身写入；子任务授权 UPDATE 不重复 BEGIN、不提前 commit，冲突同次回滚 | 合同 §7.3、§11；本地 `transaction-view-proof.json` |
| B19 | 回归 | `test_tasks.py`、`test_instances.py`、`test_projects.py`、`test_project_development_requirements.py` 全绿 | 既有 |

### 2.7 风险与缓解

| 风险 | 缓解 |
|---|---|
| 退回“同 Session 多读一致”的错误假设 | §7.3 写死单语句方案；B7（事件计数）/B8（两连接交错）机械断言；**不用自报常量当证据**（R3） |
| 退回“以绑定行为 FROM 锚点”的 0 行缺陷 | 合同 §7.3 写死单行请求参数 CTE 锚点；A19/A20 断言无绑定四例仍返回 1 行；探针逐字符执行合同 SQL（R1） |
| autoflush 或已有事务视图使读取时点与误述不符 | 用 Core/文本单语句并验证已有事务视图；子任务授权预扣已发 UPDATE，保持其事务与回滚边界（B20） |
| schedule 路径漏写两列 | 唯一写入点放 `_create_task_with_hall`；B5/B6 断言（静态检查只限生产路径） |
| 离册后误报 `bound` | §4.4 阶梯 + A12/A13/B12/B13 |
| `partial` 吞掉 `runner_missing` | §4.5 明确 `partial` 只读绑定行存储必填五项，派生 `runtime` 不参与；B14 专门断言 |
| 把 alias 当展示层，导致“指纹相同=配置未变”的误判 | 合同 §2/§4.1/§7.4 明确 alias 是调用选择参数；B18 与样例 `same_role_alias_change` 断言逐版本留证 |
| 任务快照 JSON 在 SQLite 无结构约束 | 构造时校验固定 13 键；旧数据 NULL 保持未记录。`partial` 只描述绑定行存储必填五项，不用来掩盖损坏快照；损坏快照须如实报告解析异常 |
| 迁移在旧库失败 | 按列存在性判断、只 ADD COLUMN；旧行 NULL；B1 |
| 误把“登记”当“可用” | `adapter_status` 默认 `unverified`；文案规范 |
| 越界输出“实际匹配” | B1 不含 `binding_match*` 字段（B17）；B2 另片 |
| 把读取回执当一致性证明 | 首期**不新增**任何回执字段/常量；一致性只由事件计数与交错测试证明（R3、D8） |

---

## 3. 后续片排期（只排期，不承诺能力）

### 3.1 B2 实际运行证据与对照（**必须另开设计片**）

- 前置不变量见 `ROLE_MODEL_BINDING_DESIGN.md` §8.2（R-B2-1 关联锚点 / R-B2-2 维度完整 / R-B2-3 不可变证据 / R-B2-4 unknown 降级 / R-B2-5 命名分离 / R-B2-6 证据类型）。
- 已知障碍：`agent_instances` 无 `project_id`/`task_id`（G8）且原地覆盖（`server/routes/instances.py:50-57`），因此**不能**用实例最新值派生历史 attempt 结论；`kimi-code/k3` 是 alias（且是原生调用选择参数）不是 `model_id`。
- 本片**不**定字段、**不**排期到 B1；B1/B3 不得输出任何 `binding_match*`。

### 3.2 B3 MCP/工具消费

- `bridges/talk_task_tools.py`：`talk_list_agents` 每个 agent 增加只读 `binding`/`binding_state`（不含凭据、不含 match）。
- 不新增工具、不改既有工具名/参数；保持九工具目录（`docs/spec/MODULE_tasks.md:242`）。
- 必须守护 `development_requirements` 单次出现断言（A18）。
- 工具描述变更需 MCP 客户端**重连**后才生效，未重连前不得声称宿主已加载。

### 3.3 B4 页面

- `web/workspace.js` / `web/workspace.css`：角色列表与详情只读展示 `runtime` / 来源 / `model_id` / 可选 alias / 可选展示名 / 连接标识 / `binding_state`；
  未配置显示“未配置”，离册显示“已离册（保留配置）”，未上报显示“模型未上报”，三者严格区分；**不展示“实际匹配”**（B2 未落地前）。
- 产品展示名规则（D-5）未决 → 只展示已有值，不定名称规则、不批量改名。

### 3.4 B5–B8

- B5 依赖尚未批准的「进程所有权合同」，本设计不提供启动接口或状态机。
- B6 schedule 项目化、B7 不匹配开关、B8 其它运行器：分别等待独立合同 / D-2 决策 / 外部宿主事实。

---

## 4. 实施交付与收尾约束

- 每次只派一个已确认切片，B1a 验收收取后再派 B1b；共享目录开发暂停后独立复核。
- 执行者交付本次实际任务号一致的结构化包，包含实际差异、测试证据、未完成与限制；协调方独立核实，不只采信自报。
- 正式进度与 Git 由 Codex 收尾；按已授权常规推送，不改写远程历史。
- B1a/B1b 通过不等于目标八方向或真实模型能力通过；真实宿主 T/W、取消/排队、K2.8 接单继续分别验收。
- 本计划当前仅为已审实施依据，仓库尚无这里规划的表、API 或快照字段实现。
