# 工作区登记与重关联设计合同（660-W-D1）

状态：只读盘点与建议设计，尚未实现或验收。基线：`codex/terminal-return-codex`，`6ac900665790cec7220e6732f8a45d7254c839fc`。本稿的 API、字段、错误码和流程均为建议，非现有能力；文末裁决项确认后再拆任务。

## 1. 既定约束和当前事实

既定决策：工作区由发起任务的 Agent 终端目录及 `.talk/project.yaml` 的 `project_id` 确定；页面没有“创建工作区”入口。左上角可切换已加入的工作区，同一时刻只有一个活动视图；A 的任务切换至 B 后继续运行。登录后恢复上次工作区。项目、群、任务、消息及角色按项目关联，角色运行数据位于 `workspaces/<p>/`；项目唯一性、项目路由和 Key 按项目/成员隔离必须保留。以下区分决策与代码当前事实，缺口不是本片已修复项。

### 登记、指针和运行时

- `server/routes/projects.py:511` 的 `POST /api/projects` 仅 human，项目 ID 可由服务生成，`project_root_path` 可空；`server/routes/projects.py:482` 按 `expanduser`、绝对目录、`resolve`、`normcase` 校验并遍历其他项目防同路径，写前 `begin_immediate_write`（`server/routes/projects.py:519`）。`server/models.py:109` 项目 ID 为主键，`server/models.py:112` 的路径并未声明数据库唯一约束；字符串比较不是完整的物理目录身份保证，比较中不可解析的旧路径被跳过。`server/routes/projects.py:545` 人类列全部项目、Agent 只列其名册或角色关联的项目；`server/routes/projects.py:560` 的单项读取没有同样的名册过滤。`server/routes/projects.py:1210` 现有 human PATCH 可以直接修改根目录并重新检查路径，但不处理下面的指针及运行时配置；这是必须收口的现状，不能把它描述为安全重关联。
- `server/routes/local_workspaces.py:78` 的 human `POST /api/local/workspaces/ensure` 接受已有目录，按规范化路径找项目；存在 `.talk/project.yaml` 时须匹配找到的项目，否则报 `workspace_already_bound`（`server/routes/local_workspaces.py:112`）。无项目时其实现会生成项目和标记，并启用 host 配置、建立本机 runtime 配置及指针（`server/routes/local_workspaces.py:113`、`server/routes/local_workspaces.py:122`、`server/routes/local_workspaces.py:128`、`server/routes/local_workspaces.py:148`）；这是一条现有服务端行为，不代表页面应提供创建入口。已存在配置/指针不匹配时拒绝，写成后 runtime 启动失败也可能返回已登记但不可用（`server/routes/local_workspaces.py:141`、`server/routes/local_workspaces.py:174`）。`server/routes/local_workspaces.py:37` 的 Agent join 是加入现有项目的名册操作，不是重关联。
- CLI 初始化时生成或使用指定项目 ID 并写入 `.talk/project.yaml`（`cli/talk.py:112`、`cli/talk.py:127`、`cli/talk.py:139`），读取项目配置时定位根下的标记（`cli/talk.py:204`）；CLI 同步默认采用标记内项目 ID（`cli/talk.py:534`）。这些现状不赋予 Agent 修改服务器登记根的权限。
- `server/local_runtime.py:36` 项目查询从登记根读取 `.talk/runtime.local.json`，校验 schema、数据库路径、配置文件绝对路径，再通过配置核对项目 ID 和根；任何异常返回 `None`（`server/local_runtime.py:47`、`server/local_runtime.py:56`、`server/local_runtime.py:59`、`server/local_runtime.py:63`、`server/local_runtime.py:66`），不能仅据 `None` 猜出具体原因。`scripts/talk_runtime.py:207` 加载 runtime 配置时还检查根目录存在、配置路径为绝对路径、Key 根和 operator Key 不在项目根中（`scripts/talk_runtime.py:214`）；启动前又对比登记根（`scripts/talk_runtime.py:532`）。只读检测必须实现细粒度诊断，不可调用会启动进程的 `ensure_local_runtime`（`server/local_runtime.py:152`）。
- `server/workspace_paths.py:20` 使用带 `p-`/`m-` 前缀的小写 Base32 编码，最长 120 字节；`server/workspace_paths.py:94` 的真实落点是 `<data_root>/workspaces/<project_component(project_id)>/`，不是字面上的原始 ID。角色 profile、native HOME、会话和日志为其子路径（`server/workspace_paths.py:98`）。这些路径检查会拒绝符号链接和 Windows reparse point（`server/workspace_paths.py:40`），不应因根目录检测支持链接识别而放宽运行目录安全检查。`server/workspace_paths.py:72` 把 data root 的 `.git` 普通文件或目录视为 git 形态，缺失视为非 git；链接及不可判定报错。`server/workspace_paths.py:132` 的 git Key 根是传入根或 `~/.talk/keys`，不得位于 data root 内；非 git 使用 `<data_root>/keys/<project_component>/<member_component>.key`。git 形态下该函数本身不追加项目分量；`ensure` 配置了按项目分根的 `key_root`（`server/routes/local_workspaces.py:133`），运行时传入它（`scripts/talk_runtime.py:543`）。因此必须核验实际配置的项目隔离，不可一概断言默认 git 根天然按项目分层；不读 Key 内容。

### 页面与数据范围

- `web/index.html:102` 是项目下拉框；`web/app.js:667` 绑定切换，`web/app.js:877` 更改唯一 `activeProjectId`、清空视图状态并重载项目数据，没有在此切换流程调用停止任务/角色。`web/app.js:739` 按账号构造 localStorage 键，`web/app.js:747` 加载列表后恢复上次 ID，不存在时退到首个项目；这是同浏览器、同账号的恢复，并非跨设备保证。`web/app.js:938` 根据服务返回的项目填充选项；当前 human 项目列表范围是服务返回的全部项目，不能说代码已实现“只列已加入”。
- `web/app.js:815`、`web/app.js:1622` 分别用活动项目过滤任务、群，并在响应返回时复核项目/账号及请求序号（`web/app.js:821`、`web/app.js:1628`）；角色/Agent 请求以项目路径发起（`web/app.js:792`、`server/routes/projects.py:588`、`server/routes/projects.py:1639`）。`web/workspace.js:71` 的本地群过滤保留无项目的历史群条件，但当前项目查询本身按项目过滤（`server/routes/groups.py:163`）；不能外推所有历史记录都严格隔离。
- 直接带 `project_id` 的例子：`groups`（`server/models.py:78`）、`files`（`server/models.py:64`）、`agent_tasks`（`server/models.py:2479`）、`agent_task_schedules`（`server/models.py:2593`）、`agent_instances`（`server/models.py:185`）、`project_agents`（`server/models.py:137`）、`project_role_bindings`（`server/models.py:767`）、`project_roles`（`server/models.py:855`）及其他角色服务/操作表（`server/models.py:1557`）。并非所有表都直接带项目：`messages` 通过可空 `group_id` 关联群（`server/models.py:38`），无群消息不因此具备项目 ID；`group_members` 通过 group 关联（`server/models.py:91`），成员本身全局（`server/models.py:25`）。任务 Hall 创建时同时写群及任务项目（`server/routes/tasks.py:1567`），任务列表项目过滤见 `server/routes/tasks.py:1878`、`server/routes/tasks.py:1905`；消息的群读取受会话权限约束（`server/routes/messages.py:484`）。不得把历史空项目消息、群或任务自动归属、迁移或合并。

## 2. 身份、四类状态与只读判定

一次检测可返回多个问题，各问题 `code` 稳定、`severity`、`evidence_kind` 和可操作的非敏感说明；`unknown` 与 `ok` 必须分开。检查事实仅针对服务器所在机器和检测时刻，结果不构成可写授权。旧根缺失并不能仅凭缺失断言被移动。检测应只访问登记的根与用户明确提供的候选根，以及与该项目绑定的已知路径，不扫描父目录或磁盘；无需读取项目业务文件、数据库或 Key 正文。

| 类别和稳定码 | 判定依据与出口 | 代价、边界及推荐 |
|---|---|---|
| `workspace_duplicate` | 对所有可访问登记根打开目录句柄/跟随根路径最终对象，按平台支持的卷标识+文件 ID（POSIX `st_dev/st_ino` 或 Windows volume serial+file ID，等效 `samefile`）分组；不同 `project_id` 的句柄指向同一物理目录即重复。大小写、8.3 短名、symlink/junction 各路径指向同一对象应识别。检测返回冲突项目 ID；登记/提交时全局复核。 | `resolve`+`normcase` 便宜但文件系统大小写规则不同、短名/链接/网络卷有例外；物理 ID 更可靠但有网络文件系统不支持、卷/对象复用与竞争。未知/不支持返回 `workspace_identity_unknown`，不能宣称无冲突；不能用空标识相等。检测与提交之间必须重开复核，运行目录仍按原规则拒绝链接。 |
| `workspace_root_missing`、`workspace_root_inaccessible` | 绝对登记根访问明确 `ENOENT`/等效不存在为 missing；`EACCES`、挂载不可达、超时、无法确定原因等为 inaccessible，不把 `is_dir()==False` 作为删除证据。根为普通文件或格式非法返回 `workspace_root_invalid`；无登记根返回 `workspace_root_unconfigured`。 | 无扫描，廉价；挂载暂不可用与删除不可完全区分。错误保留匿名类别，不回显 OS 异常和私有路径。候选根检测可另指出候选缺失。 |
| `workspace_move_candidate`、`workspace_identity_unverified`、`workspace_marker_conflict` | 人工提供新绝对目录；检查其 `.talk/project.yaml` 的 `project_id` 是否等于当前项目并比较先前可靠物理身份。旧身份与候选身份一致表示同卷更名的强证据；仅相同标记是候选，不能证明同一物理实例（复制也带标记）；标记指向其他项目则冲突。旧目录存在且身份不同视为复制/迁移风险，显示而非自动判断移动。 | 路径字符串不能识别移动；卷+文件 ID 对同卷重命名有效、跨卷复制会变化，且文件系统可能复用 ID；标记跨卷保留但可复制/伪造，额外随机 UUID 仍会被复制；内容哈希昂贵且文件本来会变。推荐项目 ID 标记 + 保存的物理身份作为强弱证据，所有重关联仍由 human 二次确认；没基线的旧项目为 unverified，不伪装强匹配。标记不存在默认不允许写入或覆盖，见裁决 1。 |
| `workspace_binding_invalid`、`workspace_binding_unknown` | 对有声明绑定的项目，仅检查已知指针 schema、当前服务 DB 身份、配置文件归属、项目 ID/根与当前数据根的关系、工作区落点和 Key 根位置/归属是否符合约束；逐项返回 `pointer`、`runtime_config`、`workspace_storage`、`key_root` 子状态，不返回配置/Key 正文。确知不匹配为 invalid；缺权限、网络错误、无法证明归属为 unknown。没有配置应标记 `not_configured`，不得一律视为损坏；无角色时尚无角色目录可为 `not_provisioned`。 | 检查元数据和必要的配置标量即可，Key 文件只做受限存在性/位置检查；存在不能证明 Key 可用或正确。运行目录消失不表示可以重建或迁移；服务存活检测也不等于绑定有效。实际读取路径需防越权、防重解析点和异常超时，响应不包含 DB 路径、Key 路径及配置内容。 |

状态优先级仅供页面排序：冲突/重复、根缺失/不可访问、移动候选、绑定异常、未知；不得覆盖其余问题。物理 ID 比较依赖可信 OS 结果，出错一律 unknown；身份快照必须标识平台/卷和采集时间，不可跨机器、跨卷直接视为相等。若原根已变为另一个目录，不得覆盖此前快照；根为空或旧身份不可得时人类提供的候选只能是弱证据。候选输入即使带复制出的同一标记也不能自动证明真实性。

## 3. 检测 API、重关联 API 和页面合同

### 只读检测

- 建议 `GET /api/projects/{project_id}/workspace-diagnostics`：仅已鉴权且启用的 human/operator，Agent 403；无此项目 404。返回 `project_id`、`observed_at`、`root_status`、`identity_confidence`（`strong`/`marker_only`/`unknown`）、`issues[]`（`code`、`severity`、`component`、`evidence_kind`、安全说明）、`binding` 四子项，以及检测版本 `revision`。`revision` 是只对必要非敏感登记状态、身份快照和版本计算的不透明并发令牌，不含秘密。只读，无创建、刷新绑定、写入校验时间或启动行为。
- 建议 `POST /api/projects/{project_id}/workspace-relink-preview`，body `{candidate_root}`，仅 human；语义为只读计算，POST 仅为避免把本机路径放 URL/访问日志。返回上述诊断加候选与原根的可展示路径、冲突项目 ID、标记是否匹配、物理身份比较、忙状态、禁止提交原因与短时 `preview_token`。绝不缓存或持久化请求路径到普通日志；仅服务器同机 human 本地受信操作可提供路径，远程 human 的目录不可当作服务器目录。服务端按白名单解析 project.yaml 必需的 ID，严格限制文件大小、禁用 YAML 对象构造及路径穿越；不读取任意文件、Key 或配置全文回显。对目录链接先通过句柄解析并验证允许范围，无法保证安全则拒绝；不提供任意目录浏览或全盘搜索。
- 建议 `GET /api/workspace-diagnostics?limit=...&cursor=...` 给 human 管理列表；按项目 ID 稳定游标，默认 20、最多 100。重复判定覆盖全部可访问登记根而非仅当前页，不能因分页漏报；缺权限的路径不把“未发现”当“无冲突”。同一轮共享去重快照，列表返回 `observed_at` 与 `next_cursor`；数据变化时可能需重新开始，提交再检查。对耗时目录使用有界并发和单项截止，超时返回 unknown，不阻塞整个列表；限制同时检测数量。按需触发，禁止后台持续扫描。

### 主动重关联

页面在左上角工作区下拉附近提供“工作区设置”，在选中已有项目的设置页展示检测状态与“重新关联已有目录”。human 可输入**服务器所在机器**已有目录的绝对路径；浏览器通用目录选择器不能承诺提供服务器绝对路径，本片不设计上传/创建。项目列表和切换、上次项目恢复保持原有约束。预览显示项目名和 ID、旧根、新根、身份置信度、绑定检查与历史保留说明；两步动作分别为“检查目录”和“确认重新关联”，确认框再次列出项目及目标，明确不会移动文件、合并历史或启动任务。取消无写入。弱证据标注“无法证明为原目录”，仍须用户确认；目标标记冲突、重复、未知身份或忙时不提供提交。身份未能证明与其他登记目录不重复时必须拒绝写入，而不是把弱身份当作唯一性已通过。

建议 `POST /api/projects/{project_id}/workspace-relink`，body `{candidate_root, expected_revision, preview_token, operation_id, confirm: true}`；仅 human，token 绑定项目、候选目录物理身份、登记版本、检测摘要、操作人和短时有效期，签名或服务端保存，不能单靠前端确认。成功返回原 project_id、规范化新根、登记版本、`binding_state` 和操作结果；相同 operation_id + 相同请求重复返回原结果，不同请求返回 `workspace_operation_conflict`。预览失效/并发变更为 `workspace_preview_stale`（409）；重复或目标被其他项目占用为 `workspace_duplicate`（409）；标记不匹配为 `workspace_marker_conflict`（409）；无法验证为 `workspace_identity_unknown`（409）；忙为 `workspace_busy`（409）；不可访问为 `workspace_root_inaccessible`（422/503，取决于超时/系统不可用），无权限 403。消息用错误码映射中文，严禁输出配置、Key 或完整系统异常。

提交时必须在同一全局写协调域中重检：原项目版本、候选句柄身份与标记、所有已登记目录身份、运行状态与目标写入权限；对创建、现有 PATCH、`ensure` 及新入口统一使用同一物理身份校验和跨进程锁/事务，关闭普通 PATCH 直接改根的旁路（兼容旧调用返回稳定错误和迁移说明）；仅给新建登记保留原有授权规则，不改变 Agent join。无法证明任何**其他项目**的登记根不与候选相同（含其旧根不可访问）时禁止提交，人工处理例外需另行授权与设计；当前项目的旧根缺失不单独触发这一跨项目冲突条件。目标对象在检测后被替换、标记改变、锁失效或版本改变均失败；仅进程内锁不足以解决多进程竞争。提交时绑定目录句柄并对所有文件操作再验证路径及身份，不能只使用预览路径；必要的跨文件操作见第 4 节。

任何本项目角色服务正在启动/运行/停止、受管 runtime 正在运行、任务已领取/正在运行、写入操作进行中，或状态未知时，`workspace_busy` 禁止提交；不得自动停止、强杀、清锁、解除所有权或重派。仅非终态但未领取的排队任务本身不必阻止，须在同一协调域阻止并发领取/启动直至提交结束；无法做到则保守拒绝。检测与切换视图不停止任何项目的任务。其他项目是否运行不应阻止本项目，除非共享资源冲突。历史重复登记发现后只报告，先经单独决策消歧；不得选赢家或自动合并。

## 4. 数据、迁移、原子性与历史

建议新增一张以 `project_id` 为键的登记元数据表（或等价可迁移字段）：`revision`、可空的 `identity_platform`/卷 ID/文件 ID 快照及采集时间、状态版本；单独持久化最小操作记录保存 `operation_id`、请求摘要、阶段、结果以及恢复所需受限旧值。它们只支持诊断、CAS 和幂等，**不是**新的项目 ID 或跨机器身份凭据。必要时保存 marker 版本，不新增自动写入 `.talk` 标记的要求；只读 GET 的 `observed_at` 即时返回，不写 `last_checked_at`。迁移仅新增表/可空字段、索引及版本，旧项目空身份标为 unknown，不批量读取目录、不自动回填或编造身份；后续仅经明确授权的登记/重关联提交保存快照。数据迁移可回退到旧代码仍可读取的形式；已完成的重关联不会因为回滚 schema 自动撤销。

不做数据库重写：不重建项目/历史数据表、不批量更新旧记录，不改 `project_id`、消息、群、任务、角色、成员、附件、密钥及其归属；仅针对当前项目在事务内更新登记根与上述新元数据/操作记录。数据库迁移允许正常新增表和字段，不能把它误称为零 schema 变更。旧项目 `project_root_path=NULL` 按未配置处理，不分配新 ID；原本就缺的历史运行目录不得被宣称已保留完整。

同一 project_id、同一 data root 时 `workspaces/<project_component>/` 和项目/成员 Key 根保持原路径、原数据、原所有权；任务/消息/群/角色、实例、会话、配置与附件的所有历史记录保留。新目录必须是用户已准备的已有目录，代码文件、`.talk` 文件及其历史不被系统复制或删除；若用户自行搬移丢失了文件，系统不假称可恢复。运行目录与 Key 根不自动迁移、重建、轮换或读取密钥；机器/部署根改变而不能证明原落点、Key 根可用时拒绝完成，单列后续迁移方案，不把新空目录伪装成旧运行环境。角色 profile 索引为项目内相对路径（`server/models.py:137`）；新根缺少所需文件时显示绑定受影响，禁止暗自创建或覆盖。

重关联不仅是数据库改路径：原根指针、候选根指针、runtime 配置、当前数据库及 host 状态可能跨文件系统，不能承诺 SQLite 事务与文件原子提交。推荐先在隔离测试环境实现持久操作日志和阶段机：预检并保存受限恢复信息 → 按同一卷临时文件、fsync、原子替换写新 runtime 配置/新指针（仅允许属于此项目且版本/内容符合预期的文件；不覆盖冲突文件）→ 重检并 CAS 提交登记根与记录 → 标记已完成。旧根存在时保留旧指针作只读证据，不删除；指针仍要与登记根和配置匹配才可用。每次副作用前检查目录句柄及目标文件版本；目录不能安全写入或配置不属于该项目时在第一处写入前失败。补偿只恢复本操作确知创建/替换且版本未变化的文件，绝不覆盖用户并发修改；不能安全补偿则保持 `recovery_required`，阻止该项目启动及重关联，明确告知人工处理，不声称原子成功或静默重试。崩溃重启时按操作日志识别未完成状态，先只读诊断并呈现恢复需求；任何修复动作需 human 明确选择并确认。不得依赖只在内存中记录操作或在失败后无条件删文件。重试同一 operation_id 的完成结果可读，不重复副作用；未知中间态不得自动重放。

失败时数据库未提交且补偿完整则旧登记仍有效，返回明确失败；提交后如无法完成最终核验，报告 `recovery_required` 和实际阶段，不报告完全回滚。并发锁、目录替换、崩溃恢复的具体平台能力要通过后续实现验证；若不能实现这些保证，写入片不得发布为可用。禁止直接靠旧 PATCH 修改根绕过该合同。

## 5. 测试计划与验收

使用隔离临时 DB、data root、HOME、配置和测试端口；以下是后续需实现的用例，非本片已执行结果。

1. 单元：正常路径和空/文件/不存在/拒绝访问；两项目大小写、短路径、symlink、junction 指向同目录均检测重复，文件 ID 不支持、复用/不可信、网络盘不可访问为 unknown；分平台临时目录真实创建、重命名、链接及权限操作，Windows junction/8.3 和 POSIX 链接分别在对应平台运行，条件不满足明确 skip。禁止依赖现有生产目录。
2. 候选移动：同卷真实 rename 后身份一致；跨卷复制或模拟不同卷且标记相同只显示弱候选；两份复制品不当成同一物理目录；旧路径被替换、目标无标记/异项目标记、历史无快照、权限拒绝分别返回指定状态；不扫描未提交的路径。
3. 绑定：临时合成 pointer/config，覆盖项目 ID、DB 引用、project root、Key 根在项目内、git/非 git data root、无角色目录、丢失运行目录与权限不可读；验证不存在、无配置、未知三者区别，日志/响应无 Key、私有配置或 DB 正文；GET 不写文件、不启动服务。
4. 接口：human、可信 operator、Agent 和禁用成员分别测试；原有 Agent join 与项目路由回归；未登记根、重复登记、分页跨页重复、同时出现多问题、超时及列表限额；预览/取消无副作用。两项目并发提交同一物理目录、登记与 relink 竞争、旧 PATCH/ensure 绕过、新目标在预览后被替换、并发启动/领取和 CAS 过期均只有合法者成功。重复 operation_id 同请求幂等、异请求冲突。注入每个阶段写失败、进程中断和恢复冲突，核验数据库及文件状态与 `recovery_required`；无真实 Key。
5. 页面：单项目选中→设置→检查→二次确认→结果；目标重复、标记冲突、未知、忙、权限拒绝及网络错误不提交；旧 ID 与群/任务/角色记录仍在，切换 A→B 后 A 任务继续，刷新恢复 B，延迟响应不污染 B；仅 human 可见操作入口，Agent 无法通过 API 绕过。自动化页面使用已有测试体系与模拟服务，里程碑另做真实浏览器验证和真实临时目录操作；无环境时标记未验证，不以静态检查替代。

## 6. 建议切片与验收边界

以下是依赖顺序，不构成开工授权。每片须先明确文件白名单、独立验证根、身份/开发要求、测试命令及独立复核人；预计文件数仅为拆包目标，模型/迁移、测试和接口如超过应按可验收依赖重新分包，不能为了数量牺牲闭环。

1. **只读诊断内核**：约 2–4 个源/测试文件，物理身份、四类状态、链接与错误映射；用临时目录及合成配置验收，不接写入。独立价值：可由调用方离线复用并区分 unknown。
2. **只读 API**：复用内核，单项目、候选预览、分页/权限/大小限制；接口测试证明无副作用及跨页冲突。可独立作为排查能力验收，不提供提交按钮。
3. **重关联存储与事务内核**：迁移、幂等日志、持久阶段机和故障注入；以隔离测试直接调用内核证明并发、崩溃与补偿。不是公开入口；若共享守卫尚未完成，不可开放写入。
4. **受保护的提交入口与登记收口**：统一新旧登记、PATCH、ensure 的唯一性与忙守卫，接入重关联；接口端到端验收并发/旁路/权限/保历史。须在一个串行闭环内完成，避免先开放不完整入口。
5. **页面入口与真实场景**：设置页、预览、二次确认和错误提示；与已完成的 API 联测，真实浏览器/临时目录人工验收，验证工作区切换、恢复和任务持续。同步检查用户手册与相应模块文档。

不做：自动重派 344；自动修复/自动重新关联；扫描整盘或推断缺失目录位置；创建工作区页面；未经明确授权合并历史或项目；删除/搬移旧目录、角色运行数据、Key；自动启停角色或服务；读取/展示 Key 正文；跨机器 Key/运行数据迁移；给历史无项目消息强行归属。

## 7. 风险与需裁决问题（推荐均为设计默认，尚未获批准）

1. **候选缺 `.talk/project.yaml` 能否重关联？** 推荐默认拒绝，提示先由拥有该工作区的发起终端恢复/提供原标记，再重新检查。理由：无标记且无物理身份连续性无法证明项目归属；允许人工认领或建立标记需另一项明示授权与防冲突合同。
2. **仅标记匹配、物理身份变化时能否人工确认？** 推荐允许在全局唯一性可验证、原项目无活动且二次确认后提交，明确标为弱证据。理由：跨卷搬迁必然可能改变文件 ID，但复制标记无法证明是原实例；冲突或唯一性未知必须拒绝。
3. **任一其他登记根不可访问时，是否阻止重关联？** 推荐阻止，给出不可确认的项目 ID 和恢复建议。理由：无法排除目标与不可访问登记是同一物理目录；牺牲可用性换取不破坏项目唯一性，异常豁免另行设计。
4. **重新关联时是否重写本机指针与 runtime 配置？** 推荐仅对可证明属于当前项目、可安全 CAS 的文件作最小改写，否则拒绝并提示绑定失效；不启动服务、不改 Key 和角色目录。理由：仅改 DB 会导致现有 runtime 根校验失败；跨文件失败需要持久恢复状态。
5. **谁能操作，以及运行时忙状态的范围？** 推荐只允许经现有认证的 human/operator，远程目录输入限服务端同机受信入口；运行或不确定时禁止提交，排队任务允许但提交期间须阻止领取。理由：路径操作影响本机与全部项目历史，保守处理保护在跑任务与所有权。是否将 human 权限进一步收窄为特定项目维护者需产品裁决。
