# 存量角色保留身份补录：产品片A实施合同

状态：2026-10-17，用户已授权全部现有角色转页面受管；258仅迁移准备独立通过。本文规定下一产品片，不代表已实现、已登记或已完成真实启停。

## 范围与分工

Codex定义范围、复核并直接修正问题、验证及正式文档/Git收尾；DeepSeek仅首次实施、自测交付后暂停。一次一方改码，不再派同片返修/回审。本片只补服务端登记与宿主可信来源接线，不处理per-runtime模板、21600参数、完整日志、页面新交互、真实Key归档或实际服务切换。

## 接口与保留事实

新增human-only `POST /api/projects/{project_id}/roles/legacy-attach`，严格请求只含 `member_id`、`runner_id`、`choice_id`、`operation_key`；沿用既有operation_key格式/长度。拒绝api_key、auto_start等额外字段。不调用现有CREATE角色接口，不接受新成员或新Key。

首次仅接受当前项目名册已有、未禁用的agent，且该项目没有其ProjectRole行；项目不存在/成员不存在/非agent/离册/身份独占引用冲突按既有稳定错误语义拒绝。已有managed、已有imported或归档角色均拒绝，不借补录重新归档/恢复/改名。角色名取当前成员display_name（空值回落member_id），未归档同名冲突409，不自动加随机后缀。

请求须引用存在且未软下架的精确runner/choice，choice所属runner相符。既有绑定存在时六维必须与choice完全一致，保留原行每个字段（包括updated_at/updated_by）；缺绑定时可新增该显式选择的精确绑定。不推断模型、不替换原绑定，不修改runner能力状态。

必须逐项保留Member.id/api_key/kind/display_name/created_at/disabled_at、既有ProjectAgent全部字段、说明、策略、其它项目、历史任务/消息/成果。无名册不自动加入。补录不读写宿主Key文件，不返回/生成/轮换任何Key，不创建provision作业、service launch或自动启动。

## 原子补录、幂等与来源

采用独立 `RoleLegacyAttachOperation` / `role_legacy_attach_operations`：operation_key主键、请求指纹、project_id/member_id/runner_id/choice_id/derived_role_name、created_by/committed_at等必要公开审计，唯一(project_id,member_id)。不要向RoleCreationOperation伪造一次创建新身份的事实。

同一个真实SQLite写事务（BEGIN IMMEDIATE并在锁内重读引用）新增：

1. `project_roles`：同一member_id，origin=imported、identity_exclusive=0、credential_version=1（仅建立跟踪基线，未轮换/签发）、key_issued_at/key_rotated_at均NULL。
2. 仅在缺失时新增精确binding。
3. 已提交legacy-attach操作映射。

不得改既有角色权限/名册/说明/策略，失败整体回滚、没有独立提交pending行。旧库迁移只增表/索引，不自动回填生产角色、重建旧表或修改历史；init_db重复运行幂等。

同operation_key+同请求返回200/reused=true，不重复写入或重置后续事实；异载荷/跨项目/跨成员或与既有创建操作同key冲突409。首次201/reused=false。响应仅公开role/member_id/reused等元数据，绝不返回Key。后续绑定变更或归档不能被重放恢复；投影须如实显示当前失配/归档并阻止不合格启动。

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
