# 存量角色保留身份补录：产品片A实施合同

状态：2026-10-17产品片A已完成，259首次交付经Codex独立复核后直接修正两项问题，162项相关回归及2项临时SQLite WAL并发探针通过，259已收取；本轮发布代码。全部现有角色实际补录/服务切换、原生能力与页面验收未执行。

## 范围与分工

Codex定义范围、复核并直接修正问题、验证及正式文档/Git收尾；DeepSeek仅首次实施、自测交付后暂停。一次一方改码，不再派同片返修/回审。本片只补服务端登记与宿主可信来源接线，不处理per-runtime模板、21600参数、完整日志、页面新交互、真实Key归档或实际服务切换。

## 接口与保留事实

新增human-only `POST /api/projects/{project_id}/roles/legacy-attach`，严格请求只含 `member_id`、`runner_id`、`choice_id`、`operation_key`；沿用既有operation_key格式/长度。拒绝api_key、auto_start等额外字段。不调用现有CREATE角色接口，不接受新成员或新Key。

首次仅接受当前项目名册已有、未禁用的agent，且该项目没有其ProjectRole行；项目不存在/成员不存在/非agent/离册/身份独占引用冲突按既有稳定错误语义拒绝。已有managed、已有imported或归档角色均拒绝，不借补录重新归档/恢复/改名。角色名取当前成员display_name（仅空白回落member_id）；非空名称超过64字等校验不合法时422/role_name_invalid且零新增，不能静默换成member_id。未归档同名冲突409，不自动加随机后缀。

请求须引用存在且未软下架的精确runner/choice，choice所属runner相符。既有绑定存在时六维必须与choice完全一致，保留原行每个字段（包括updated_at/updated_by）；缺绑定时可新增该显式选择的精确绑定。不推断模型、不替换原绑定，不修改runner能力状态。

必须逐项保留Member.id/api_key/kind/display_name/created_at/disabled_at、既有ProjectAgent全部字段、说明、策略、其它项目、历史任务/消息/成果。无名册不自动加入。补录不读写宿主Key文件，不返回/生成/轮换任何Key，不创建provision作业、service launch或自动启动。

## 原子补录、幂等与来源

采用独立 `RoleLegacyAttachOperation` / `role_legacy_attach_operations`：operation_key主键、请求指纹、project_id/member_id/runner_id/choice_id/derived_role_name、created_by/committed_at等必要公开审计，唯一(project_id,member_id)。不要向RoleCreationOperation伪造一次创建新身份的事实。

同一个真实SQLite写事务（BEGIN IMMEDIATE并在锁内重读引用）新增：

1. `project_roles`：同一member_id，origin=imported、identity_exclusive=0、credential_version=1（仅建立跟踪基线，未轮换/签发）、key_issued_at/key_rotated_at均NULL。
2. 仅在缺失时新增精确binding。
3. 已提交legacy-attach操作映射。

不得改既有角色权限/名册/说明/策略，失败整体回滚、没有独立提交pending行。旧库迁移只增表/索引，不自动回填生产角色、重建旧表或修改历史；init_db重复运行幂等。

新建与补录两入口均在自己的真实写事务内先检查另一类型已提交操作，任一类型占用同key，另一类型一律409/operation_key_conflict（跨项目与并发同样成立）。同类型operation_key+同请求返回200/reused=true，不重复写入或重置后续事实；异载荷/跨项目/跨成员同key冲突409。首次201/reused=false。响应仅公开role/member_id/reused等元数据，绝不返回Key。后续绑定变更或归档不能被重放恢复；投影须如实显示当前失配/归档并阻止不合格启动。

## 投影与宿主守卫

角色投影增加 `choice_source=legacy_attach`（精确已补录映射）及 `legacy_attach_mismatch`；创建角色继续creation_operation、原始未补录旧成员继续legacy_manual。只按显式操作映射+当前六维逐项相等给choice_id，失配为NULL/choice_binding_mismatch=true，不按model_id反查。不接受同一身份同时有创建与补录两类可信映射；冲突时如实拒绝/失配，不能任选一条通过。

宿主_role_facts只在精确choice_id存在、choice_source属于creation_operation/legacy_attach、无mismatch且现有归档/绑定/能力/归属守卫全部成立时继续。未登记、未核验、unknown/unverified、旧legacy_manual、任意未知来源继续拒绝；本片不把真实运行器升为managed/adapted，不启动真实进程。原创建流程、创建重放、轮换限制与所有权/stop路径保持。

## 验证与交付

- 使用真实router+隔离临时/内存SQLite、假Key，先断言engine/storage隔离再建TestClient；不得调用生产API或生产init_db。
- 首次/精确重放/异载荷/并发相同和不同key、两项目同名、缺成员/离册/禁用/非agent/独占冲突、已有/归档角色、runner/choice错误或retired、绑定六维失配、同名冲突均验证稳定响应与零残留。
- 每个写入点及提交前故障注入证明同事务整体回滚；假Member Key及历史/绑定/名册/说明/策略/其它项目逐字段前后不变，不仅比较长度或数量；旧库两次迁移不自动导入。
- 验legacy_attach可信投影与宿主来源准入、binding变更/映射冲突/未知来源拒绝、原creation路径回归；复用既有临时隔离fixture，禁止以“工具可发现”宣称原生/T-W验收。
- 做本片新增测试及受影响角色/生命周期/host模块必要回归，不无关全仓重复。交付纯talk-delivery-1 JSON，实际任务号校验，原需求/基线/差异/验证/限制齐备，完成暂停。

原准备件与独立证据保持：prepare-v1/v2/v3及independent-review256/257/258不覆盖。实际登记、真实CLI/模型/宿主启停与255人工验收待后续。

## 259复核、直接修正与验证记录

- 首次交付保留：独立复核发现创建入口缺反向补录key检查（P1），补录成功后可同key再创建另一身份；非空超长display_name被静默换为member_id（P2）。根新增6用例在原代码实跑4失败/0错误，原8候选及失败日志保留。
- Codex确认DeepSeek已交付暂停后仅修改projects路由与补录测试：双向写锁内操作键冲突、非法非空角色名422；另新增非空任务/消息/说明/策略/绑定及文件元数据/字节保留验证。修正后属于Codex自检与最终验收，不称他人独立复核，不再派同片返修。
- 最终162项：补录54、角色投影26、旧库迁移15、宿主34、创建幂等12、创建请求守卫21；0失败/错误/跳过。另2项显式journal_mode=wal的双入口并发探针分别锁定补录先成功和新建先成功，均只有一个操作提交、另一端409。8源compile与diff检查通过。
- 开发者685项为结构化自报，原本地目录没有完整测试原始日志；本轮不以该数字作独立验收或重复累计。原交付/代码字节/开发SHA证据与根失败、最终日志及收取回执位于.tmp/legacy-role-page-control/product-attach/independent-review259/。
- 验证入口：项目根执行 `python -m unittest tests.test_role_legacy_attach tests.test_project_roles tests.test_role_policy_migration tests.test_role_service_host tests.test_role_creation_idempotency tests.test_role_creation_request_guard`（临时库/假Key）。生产服务尚未由本片主动部署/重启，真实补录仍需后续宿主配方/凭据就绪和逐角色计划；不据本片宣称5角色已受管或可页面启停。

## 2026-10-29 恢复扩展（B1-a，用户选定）

- **问题**：已补录的 imported 角色（`origin=imported`、`identity_exclusive=0`、无创建操作）在页面没有“绑定重置”——恢复入口 `_normalize_recover_intent` 的三道门全部拒绝。
- **方案**：为**恢复**新增 legacy 来源分支，锚点是**已提交的** `role_legacy_attach_operations`；仍然**不写入、不复用** `role_creation_operations`（本条继续有效：补录不等于创建新身份）。
  - 恢复请求：`origin_operation_key` = 补录 operation_key；`choice_snapshot` 按补录记录的 `choice_id` 现读 `runner_model_choices` + `runner_registry` 合成；choice/runner 失配即拒绝，不按 model_id 反查。
  - 配置作业入口 `_require_provision_identity`：仅当“该成员无创建操作 + 传入键等于已提交补录锚点 + 存在指向该键的 recover 请求”时放行；create 与其它入口保持原拒绝。
  - 完成回写 `require_completion_facts`：无创建操作时只接受 recover 且操作键与补录锚点一致；create 仍必须有创建操作与指纹匹配。
  - `GET /api/projects/{p}/agents` 投影新增 `credential_version` 与 `recoverable`（服务端按同一套门禁计算），页面据此显示“绑定重置”。
- **验证**：`tests/test_role_legacy_recover.py` 5 项（放行、未补录仍拒绝、代际不符拒绝、恢复可开配置作业、投影字段）；`tests/workspace_role_creation.test.cjs` 新增旧角色按钮与 recover 载荷用例；相关回归见进度记录。
- **限制**：真实旧角色（小G/小D/小K）的页面恢复仍**未执行**——需重启 API 后由用户点击验证；worker 全链路的三步执行与完成回写只在合成用例中覆盖到建作业，未跑真实 CLI。

## 2026-10-29 凭据轮换扩展（B1-b，用户选定 C 方案）

### 问题（实机复核发现）

B1-a 交付后用户在小K（`agent:kimi`）点击“绑定重置”，页面无报错，但请求实际失败。
只读核对生产库与日志的链路：

| 时刻 | 事实 |
|---|---|
| 16:32:58 | 创建 recover 请求 201，`choice_snapshot` 按补录 `choice_id` 合成成功 |
| 16:33:00 | claim 200 |
| 16:33:00 | `POST /roles/agent:kimi/rotate-key` **409** |
| 16:33:00 | report failed，`role_provision_jobs` 零行 |

根因：worker 的恢复流程先核本机 Key，无可用 Key 时调用一次 `rotate-key` 换凭据；
而 `rotate-key` 只允许 `origin=managed` 且 `identity_exclusive=1` 的角色，imported
补录来源必然被拒。B1-a 只打通了“建请求 / 建作业 / 完成回写 / 投影按钮”，中间的
换凭据动作没有分支，真实点击因此必然失败。

同时确认：`C:/Users/Administrator/.talk/keys` 下没有 `agent_kimi.key`，只有空的
锁守卫；该角色能启动是因为宿主进程常驻并持有内存中的 Key，凭据从未落盘。这也是
“换一次并写入本机”具有实际价值的原因。

### 方案

1. `POST /roles/{member_id}/rotate-key` 增加**仅恢复用途**的 legacy 分支：
   - 角色为 imported 且存在**已提交**补录锚点时，改用锚点 `operation_key` 取证；
     无锚点仍返回 `rotate_not_managed_identity`。
   - `identity_exclusive=0` 在 legacy 分支下不再直接拒绝，改由
     `prove_exclusive_identity` 的实际引用证明把关。
   - legacy 分支**必须**携带 `request_key`（同时必须给 `lease_token`），无来源的手工
     轮换一律 `provision_lease_required`，不保留旁路。
   - 仍不写、不复用 `role_creation_operations`，不改 `origin` / `identity_exclusive`。
2. `prove_exclusive_identity` 新增 `ignore_exited_instances`（默认 False，managed 路径
   行为不变）。legacy 恢复轮换传 True：已证明退出的历史实例（本机 + 心跳过期 + 无
   在途任务 + `recorded_process_state` 判定 absent/exited/previous_boot/pid_reused）
   不再阻断换 Key；远端、新鲜、持有任务或无法核验的实例仍然拒绝。
3. 跨项目引用仍硬拒绝：`other_roster → rotate_legacy_roster_reference_refused`，
   `other_roles/bindings/descriptions → rotate_shared_identity_refused`。补录来源必须
   只在本项目被引用，服务端不做自动清理。

### 验证

- `tests/test_role_legacy_recover.py` 增至 15 项：新增换 Key 成功且重放不返 Key、
  无 `request_key` 拒绝、无补录锚点仍 `rotate_not_managed_identity`。
- 关联回归：`test_role_credential_recovery`、`test_role_rotation_exclusivity`、
  `test_role_legacy_attach`、`test_role_deletion`、`test_project_roles`。
- 真实点击待用户执行；本轮不自动重启角色服务，也不改用户的自启动选择。

### 限制

- 换 Key 后旧凭据立即失效；正在运行的实例必须关闭再启动才会读到新 Key（bridge 只在
  启动时把 `--key-file` 解析进内存）。本轮不实现“恢复后自动重启”。
- 轮换仍受“同一意图最多一次”约束；重放返回 `reused=true` 且不返 Key。
