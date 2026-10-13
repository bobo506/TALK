# 页面创建与宿主配置请求合同（R1-4a）

> 2026-10-13：server协议经233/234与Codex独立复核通过，宿主235/236经Codex接手补正及237独立复核通过，整链已收取。三表/共享守卫/10新接口/4旧入口、worker真实私有文件/三步/ACK/report已实现。**完整前端尚未接线，完整创建配置未验收。** 原草稿、partial/unknown及失败证据保持，不外推生产部署/原生能力。宿主使用见[worker指南](../guides/ROLE_REQUEST_WORKER.md)。
> 上游：[角色生命周期](ROLE_LIFECYCLE_DESIGN.md)、[配置作业](ROLE_PROVISION_CONTRACT.md)、[受管服务](ROLE_SERVICE_CONTRACT.md)。本合同只修订请求驱动的创建/恢复/配置路径；既有无请求来源的人工接口保持。

## 1. 用户流程与实施边界

人类选择运行器、模型、角色名称和介绍，点击“保存并配置”。页面提交人类意图，受信宿主取得一次性创建响应，在仓库外私有文件写入TALK Key，再真实执行身份档、Key文件和预检。页面只投影进度，不接收角色Key。宿主离线时显示“等待宿主”；配置完成后由人类另行启动服务。

本次代码实施沿已批准的一键配置方向：human-only、人工明确恢复、私有落盘、配置与启动分开。宿主持已有human operator凭据，不因此给agent创建/轮换权限。项目配置默认关闭，worker默认关闭；实际启用/凭据部署由人类操作。本轮仅编写隔离可验证代码，不修改生产配置或读取真实Key。

最小部署为server和worker同机回环，浏览器可来自LAN。跨机角色Key/租约令牌传输、TLS部署、Member凭据存储迁移、批量自动配置、原生登录/模型能力、删除/外部桌面/退出清理另属后续范围。保留宿主在线依赖的真实产品代价。

## 2. 数据事实

`role_provision_requests`保存意图，永久保留：

| 字段 | 约束 |
| --- | --- |
| `request_key` | 全局主键，沿既有8–128安全operation token；create时等于原创建operation_key，recover使用新键 |
| `project_id/kind` | kind仅create/recover |
| `payload/request_fingerprint/choice_snapshot` | create保存规范化四字段及既有创建指纹、选择的六维绑定快照；recover保存项目/成员/期望凭据版本的指纹，不保存Key |
| `member_id/origin_operation_key` | create成功同事务回填；recover提交时从实际原创建操作解析并保存，不能由调用者任意指定 |
| `expected_credential_version` | recover固定的轮换前期望版本，重放不能修改 |
| `status/revision/attempts` | requested/leased/created/provisioned/failed/canceled；revision每次有效变更+1，attempts每次领取+1 |
| 租约 | `lease_generation/lease_token_hash/lease_host/lease_claimed_at/lease_expires_at/lease_config_version`；token只存SHA256，不存明文；每次领取签发新token、世代+1 |
| 审计 | `last_error_code/created_by/created_at/updated_at/finished_at`；错误码仅稳定白名单，不落异常正文 |

`role_provision_host_config`：project_id主键，enabled默认false，host_label，lease_seconds默认900/范围30–1800，max_active_leases默认2/范围1–4，max_attempts默认3/范围1–10，config_version初始0、每次enable/disable CAS+1及审计。未建配置行的GET返回disabled/version0，enable必须expected_version=0。

`role_credential_rotations`：intent_key主键、项目/成员、before/after credential_version及操作者/时间。**只保存执行事实，不保存或重放Key**。

索引包括项目/状态、项目/origin_operation_key、项目/member_id以及活动同名create/活动同成员recover的部分唯一索引。写锁内还需跨kind占用检查：已有成员的create与recover不能同时执行同一角色；人工resume也重新检查占用。failed的旧行保留但不占用，后续恢复可以新建请求。

作业仍复用原创建operation_key及现有三步/版本结构；服务表、Member明文列、原创建操作与绑定语义不改。

## 3. 接口清单

新增10个入口，前缀`/api/projects/{project_id}`。GET需已有认证，所有POST仍仅human；写事务使用BEGIN IMMEDIATE并刷新锁前ORM事实。

| 方法与路径 | 请求及行为 |
| --- | --- |
| GET `/role-provision-host` | 只读公开配置投影 |
| POST `/role-provision-host/enable` | host_label、可选预算、expected_version；CAS启用 |
| POST `/role-provision-host/disable` | expected_version；CAS关闭，所有旧config_version租约失去写资格，再启用也不复活旧token |
| POST `/role-requests` | request_key、kind、confirm=true；create四字段，recover member_id/expected_credential_version；幂等/快照/占用检查 |
| GET `/role-requests` | 可选status/claimable/limit，过滤与投影按同一个now计算；不写库 |
| GET `/role-requests/{request_key}` | 只读请求与实际作业进度 |
| POST `/role-requests/{request_key}/claim` | host、expected_revision、可选lease_seconds；领取或失效后重领，返回一次性token及执行所需**非凭据**事实 |
| POST `/role-requests/{request_key}/report` | lease_token、expected_revision、outcome=provisioned/failed、可选error_code；不接受member_id/Key/路径/argv |
| POST `/role-requests/{request_key}/cancel` | expected_revision；仅未创建成员的requested/leased/failed可取消 |
| POST `/role-requests/{request_key}/resume` | expected_revision、confirm=true；failed或领取次数耗尽且租约无效的请求可人工续跑；重置attempts并失效旧代 |

变更4个既有入口：

| 路径 | 增量 |
| --- | --- |
| POST `/roles` | 可选lease_token；operation_key命中create意图时走首次创建守卫 |
| POST `/roles/{member_id}/rotate-key` | 可选body：request_key/lease_token/expected_credential_version；请求驱动角色必须带明确recover来源；无请求来源且无活动意图的旧human无body路径保持 |
| POST `/roles/{member_id}/provision` | 可选request_key/lease_token；精确选择当前请求来源，job仍用原operation_key |
| POST `/roles/{member_id}/provision/ack` | 可选request_key/lease_token；现有revision/attempt/credential_version语义和错误先后保持 |

新增body使用extra=forbid；kind互斥载荷、预算边界、稳定错误码由共享规则验证。recover只接受已有原创建操作的managed角色，不借恢复扩大imported/共享/在用边界。create新意图不得占用已被旧人工创建操作使用的operation_key；同request_key同规范化载荷返回原行，不重建、不刷新快照，异载荷409。意图重放先做纯载荷归一化，只有新键才查实时目录/角色版本；目录退役或已轮换不阻断旧意图读取。

不新增凭据读取、renew或作业侧cancel接口；不向既有只读GET要求租约。

## 4. 公共投影与发现

请求投影允许：request_key/project_id/kind/status/effective_status/revision/attempts、role_name/role_description/runner_id/choice_id、member_id/origin_operation_key/credential_version、lease_held/claimable/retry_exhausted/lease_host/claimed_at/expires_at、last_error_code/审计、provision_job的status/revision/credential_version及原三步公开状态。

status是存储事实；只有未创建且leased失效时effective_status=requested，created失联仍显示created。claimable表示未终态、项目启用、租约失效或不存在且未耗尽次数；用于worker发现requested、失效leased与失联created，不只查询原requested。次数耗尽明确retry_exhausted，由人工resume，不自动清零。created等待续跑不得伪装未创建。

claim响应另含规范化payload、choice_snapshot、当前credential_version、expected_binding_fingerprint、lease_generation/config_version及一次性lease_token。未创建时binding预期直接从请求choice快照计算；已有成员从原选择快照核验，不猜默认模型。该响应禁止角色Key；public GET/普通POST投影不含token/hash/绝对路径/roster路径/argv/异常正文。

## 5. 领取与写资格

有效租约同时满足：项目启用、领取时config_version仍等于当前值、请求处于允许的活动状态、未到期、token哈希命中当前签发世代。host_label是路由标签，认证仍靠human Key；租约用于防陈旧/误配，并非对持human Key的恶意宿主构造权限边界。

claim在写锁内校验expected_revision、标签、状态、占用、预算、有效并发数；有效租约不能被再次领取。过期、配置换代或人工resume后才能重领，签发新世代/token。成员不存在→leased；成员已存在→created（**recover领取后也是created**），不会重新创建。lease_seconds不能高于项目预算；失败/终态不能被worker自动复活。

所有请求驱动的create/rotate/provision/ACK/report分别在自己的写锁内复查资格。禁用先提交则后续写拒绝；创建先提交则成员事实保留，disable不回滚或删除成员。到期判断采用服务端UTC，GET不归并写库。旧本地工作即使返回成功，也不能凭失效token写新状态。

claim的稳定标签失配码为role_request_host_mismatch；参数存在按is not None处理。C1提供token但原operation_key无来源时返回provision_lease_required，不能落回旧人工创建。尚未创建同名与已创建同成员占用区分，后者以member_id锚定，PATCH改名不解除占用；claim/resume不得借supersede夺取另一活动意图。

### 5.1 永久来源与多次恢复

原operation_key可能同时关联一个终态create及多个历史recover。C3/C4必须按body.request_key**精确取一行**，再核项目、member_id、origin_operation_key、当前租约；禁止任取第一行，禁止因历史终态create而阻断合法新recover。

省略request_key时，若该原operation_key有**任何**请求来源行（包括终态），返回provision_lease_required，不能退回旧人工旁路。确实没有来源行且没有对应活动意图的旧路径保持；无来源却携带token/request_key必须拒绝。C2同样防省略request_key绕过已请求驱动的恢复。原脚本未来可通过明确人类新请求接入，不因过期/完成重新得到无守卫写权限。

## 6. 创建原子性与回放

新创建在同一TX-ALL中：读取create意图→规范化四字段逐项及指纹比对→项目/kind/启用/状态/有效租约→当前choice未下架且绑定六维等于意图快照→原有创建六表写入→请求leased变created并填真实member_id/origin_operation_key/revision+1→提交。任一步或行CAS失败整体回滚，无成员/操作残留。锁前ORM缓存不得代替锁内事实。

原创建操作已提交且载荷相同的回放保持200 reused、**不返Key**；不再被choice后来退役/改名/漂移阻断。回放只读，不复活终态/失效请求；如需对账推进必须同时满足当前写资格。异载荷回放沿operation_key_conflict；首次意图载荷替换用role_provision_payload_mismatch。req不存在的旧人工创建与回放保持R1-1合同。

## 7. 恢复原子性与重放顺序

recover意图的expected_credential_version固定。C2写锁内核请求归属和当前资格后，**先查该intent_key已执行记录，再做新轮换的当前版本CAS**：

1. 已执行且before版本与意图/提交body一致：返回200 reused=true/member_id/after版本，**省略api_key**，不再次轮换。即使当前版本已是after，也不能先用before与current比对把正常重放拒绝。
2. 未执行：body版本必须等于请求固定before及角色current；重新走原独占/在用拒绝守卫；换Key、角色版本+1、插入执行记录和请求revision+1同事务提交；一次201返回新Key。
3. 同一意图不能改期望版本或复用为另一成员；记录唯一性/版本竞争失败零副作用。human旧无body响应结构不改；新增请求驱动响应单独建schema，不把旧api_key必填模型整体放宽。

失去租约后重领可查已执行事实；重放不交回旧Key。宿主先核本机文件是否已是当前有效本人Key；有则续跑、不再次轮换；没有则manual_recovery_required，需人类**新意图**才可再次轮换。普通failed resume不删除执行记录，不自动生成第二次轮换。

同角色的活动create/recover在写锁内互斥。允许人类替代已有失效recover时，必须确认旧租约无效并原子supersede旧行，保留执行记录；没有租约的requested是待执行，不能仅因expires_at为空当过期随意替代。resume旧行与新recover竞争时重新检查占用，旧行不得夺回新意图资格。

## 8. 作业、ACK与完成

C3继续复用原创建operation_key；resume按现有规则重开失败步骤或新代际key_file/preflight。C4先执行既有角色/作业/step/state/revision/pending/attempt/credential_version/错误码规则，再检查本请求来源与有效租约，失败零写入。

宿主每步在副作用前捕获本次作业版本/attempt/凭据代际，实际执行并复核后再ACK；preflight必须先完成本人身份、三档/名册、bound与选择指纹核验。不能用后来读到的新版本给旧工作补证。丢ACK只读重查；未变的pending按同代际重新执行幂等工作，已经完成的步骤不伪造新ACK。

report(provisioned)写锁内核：请求已有真实成员且原创建操作的项目/成员/原键归属正确（create再核原指纹）；当前角色/成员/名册仍有效；作业三步全成功或合法skipped、status=succeeded，job版本等于角色current；本次请求执行预期代际未被旁路轮换。缺事实409，不采信任意member_id。created→provisioned对create/recover一致。

本次预期代际明确派生：create为首次创建的1；recover已有执行记录则为其after版本，否则为请求固定expected版本（本人当前Key已有效、无需轮换的续跑）。不能在report时用角色后来版本重新赋值，后续轮换须对应新的明确恢复请求。

report(failed)保留已创建成员和三步事实，仅落稳定错误码。终态同一次提交的精确重放可只读返回，不再次修改；异结果/旧代/已resume不许覆盖。终态不再有副作用写资格。实现明确保存或推导原report提交的revision/代际以区分真正回放。

report和请求驱动ACK的失败码使用models.ROLE_REQUEST_HOST_ERROR_CODES有限集合（包括manual_recovery_required及已发布配置宿主码）；未知字符串422/零写入，不把安全标识串当作无凭据。以后新增宿主码须明确登记集合。原无请求ACK的≤64安全码规则保持。report回放先验证错误载荷，再核outcome/report_revision/token/实际错误结果及报告期凭据版本；异错误结果、非法输入、后续轮换或resume不算精确回放。

## 9. 人工操作与失败路径

| 情形 | 行为 |
| --- | --- |
| 宿主离线 | requested等待，不取Key、不自动成功 |
| 领取失效 | 发现有效claimable并重领新世代；旧回报拒绝 |
| 创建201响应丢失 | 成员与请求created已原子提交；先检查本机当前有效Key，无则人工新recover；同键回放不返Key |
| created后宿主失联 | claimable发现created续跑，不重新创建 |
| 轮换提交后丢响应 | 执行记录保证最多一次；先核本机当前Key，无则manual_recovery_required |
| 次数耗尽 | retry_exhausted；人工resume可重置次数，不因未能report failed永久卡死 |
| cancel与create竞争 | 取消先提交→创建拒绝；创建先提交→cancel返回member_created，不假装删除 |
| disable后再enable | config_version换代；旧token不复活，只能新claim |
| failed人工resume | 无成员回requested；有成员回created；占用复查、清旧资格、世代+1 |

## 10. 宿主文件与执行（R1-4b已实现）

`scripts/role_provision_worker.py`消费claimable人类请求，包括失联created；worker默认关闭、单个处理，只允许回环基址。`--enable`仅只读计划，`--enable --apply`才领取/真实配置，所有执行入口保持该语义。可通过role_service_host.serve的默认关闭选项接入独立线程，配置不spawn角色CLI或接管Popen。

Key规范路径/DACL/guard/路径边界与原子写复用R1-2。新增私有credential.json仅记录member/version/source/intent/时间，不含Key；普通路径仍拒覆无效未知文件。专用恢复替换须当前意图/代际证明、新Key本人核验、角色锁，且来源记录证明目标为本人已知旧代文件；未知/异成员不覆盖。不要声称两文件一同原子提交。

Key已发布而元数据失败：不删除当前有效Key，记录失败；下次先以本人Key认证及当前角色版本核验重建同路径元数据，不能因旧元数据而再次轮换。Key响应到落盘间仅留内存，不入argv/env/日志/任务/交付/异常；锁和租约均仅按实际能力表述。

请求驱动步骤通过逐HTTP资格/取消/剩余预算守卫，覆盖帮助函数内的名册路径登记、预检及逐个ACK，不仅检查函数入口。失败已report的outcome=reported仍是业务失败，两CLI退出1。预算耗尽可能未能report，请求保留created，按真实租约/人工resume恢复。新增有限宿主码role_key_foreign_refused/key_provenance_write_failed/worker_io_budget_exceeded已登记，旧无请求脚本语义保持。

## 11. 切片与验收

server片233/234与宿主235–237已独立复核收取。server新79/旧166/原7和WAL两连接/线程回滚证据保持；宿主237独立50新/320旧/原6/检出3/独立13分别全过，包含实际隔离回环、子进程CLI与私有文件/DACL，重叠证据不叠加。下一片Codex完整前端+DeepSeek独立复核，交完整创建/配置功能人工验收；不先发布只读选择器半流程。

必须检出的负向：首次意图载荷/choice替换零创建；cancel/disable/过期后的创建/轮换/ACK零写入；旧代token与再启用不复活；原人工重放不返Key且目录变更不阻断；历史create+新recover正确选源；恢复重放顺序/并发只轮换一次；新recover与旧resume互斥；跳过原创建/三步/代际不能完成；created失联可发现；耗尽可人工恢复；所有公开投影严格不含Key/token/hash/路径/argv，错误与日志哨兵Key零命中。

正向覆盖create意图→claim→原子创建→真实版本作业及ACK→完成，以及create终态后两轮recover、一次响应丢失和人工resume。server阶段仅TestClient/隔离DB/假Key模拟宿主，后续真实文件和页面证据分别注明，不能宣称原生登录/模型/服务能力通过。沿相关旧创建/凭据/provision用例做回归；不机械跑全仓，不写只镜像实现的测试。

## 12. 对232原稿的协调方修订索引

| 原稿问题 | 本合同修订 |
| --- | --- |
| §6.6先current CAS后查已执行记录，正常轮换重放必失败 | §7先记录重放，再对新副作用CAS；新增响应省略Key，旧schema保持 |
| §6.4原键有多行却未选择，历史终态可能拒新recover | §5.1明确request_key精确取源，永久守卫无旧分支 |
| recover保持leased但report仅created；worker仍仅扫requested | §5已有成员claim即created；§4 claimable覆盖失联created |
| effective_status未列白名单，attempts耗尽只能failed resume | §4补投影/一致过滤，§9允许耗尽人工resume |
| 后续作业/轮换未逐项复查disable及跨kind占用 | §5 config_version fencing与共享资格、§2/§7跨kind互斥 |
| 先choice活态再创建回放会改变已批准目录退役回放语义 | §6已提交无Key只读回放保持原合同 |
| 来源文件部分发布恢复不明确 | §10先认证当前Key修复元数据，不自动轮换 |

原232的9项静态检查只证明现有源码事实，未验证这些新协议。正式实现以本合同为准；原草稿/交付/失败证据不追改。
