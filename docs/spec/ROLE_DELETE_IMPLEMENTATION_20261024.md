# 删除角色切片（2026-10-24）

用户已确认本片，并指定 Codex 开发、自测，DeepSeek 独立核验。以 ROLE_EXECUTION_AND_DELETE_REQUIREMENTS 的删除需求为准，取代旧生命周期设计保留可恢复配置的设想。

范围：角色详情删除入口与确认；同一写事务检查服务、实例、未闭环任务/定时任务及配置请求，建立不可恢复的项目角色墓碑并清除绑定/说明/策略。独占身份按既有 prove_exclusive_identity 证明后吊销专属 Key；共享/导入身份保留全局身份及其它项目访问。

本机统一后台持原 Popen 普通 drain 空闲宿主，按精确项目/成员目录与安全文件句柄清理身份档、专属凭据、启动配置及私有生命周期元数据。未知归属、链接、占用或失败保留未完成状态，允许显式重试。操作与清理回执持久化；租约防迟到覆盖，后台崩溃可续处理。完整清理前不显示删除成功。

保留历史任务、结果、消息及原身份归属；保留共享运行器、模型及原生登录。重新添加通过创建新身份，不恢复旧角色。部署前只测试隔离角色；不删除生产角色，不读生产配置正文/Key/DB/私有日志，不启停生产，286 保持 paused。日志、24 小时默认和其它新功能不扩入本片。

验收：真实隔离 API 的权限/活动任务/归属/并发/重试/防恢复/历史保持；Windows 临时目录的实际安全删除、占用失败、链接/共享保护和其它角色不变；真实页面 JS 的确认、请求、进度/失败/重试与上下文隔离；相关生命周期回归。自检后冻结源码与安全证据，Codex 暂停改码，交 DeepSeek 独立核验；页面视觉及生产加载另按既有人工验收/确认约定。

## 实施事实与边界

- 新表 `role_deletions` 保存最小清理状态；公共 `deletion` 附加投影不含 Key、凭据摘要、token、路径和 argv。只有 human 可提交删除/清理回执，operator claim 一次性发租约 token，库中只存哈希。
- 本机清理 claim 的配置摘要来自 `server.local_runtime.configured_runtime` 的精确 DB 绑定；后台再次比对当前配置摘要及注册项目根。无绑定或配置变化只报失败，不触碰文件；测试使用合成绑定，不读取生产配置正文。
- 清理单轮 120 秒 / 4096 次文件操作上限，普通宿主 drain 最多 25 秒且计入该预算；HTTP 使用原 5 秒客户端，租约 180 秒留出返回余量。已清理内容幂等跳过；失败须页面显式重试，崩溃遗留 cleaning 过期后可续；活租约不抢占、不每两秒重复 claim。
- 精确删除 `.talk/agents/<member>` 档案、已证明独占的 Key/credential metadata、`state_dir/{roles,native,workbuddy-native}/<project>/<member>` 及角色控制文件、精确启动 host/key_files 映射。活跃/未知私有原生进程记录也拒绝；不按 PID 接管或结束进程。Windows 逐层句柄固定目录，拒绝 reparse/hardlink/UNC、路径别名和跨角色重复资源。专属原生 HOME 可删除，共享原生登录和模型目录不作为目标。
- 永久 OS `.guard` 文件仅有互斥标记字节，不含可恢复配置或凭据，按既有 provision 锁协议保留以防 ABA；历史诊断日志仍由原留存策略管理。旧创建/补录/轮换与请求保留公开审计事实，墓碑禁止旧创建重放、recover、sync/绑定/说明/身份档写入恢复旧角色。
- 新建角色沿原创建接口生成新 ID；清理未完成也不会把旧配置恢复为可用。共享/imported 身份不吊销其它项目的全局 Key，本项目接入和档案仍清理。
- 当前未生产加载、未删除任何生产角色。上线需正常重载 API 与统一后台，不能只刷新页面；旧后端缺 deletion 字段时页面隐藏删除入口。

## 328 独立复验与收取（2026-10-24 20:00）

正式结果2972的任务号、作者agent:deepseek、Task Hall及完整正文与本地report/checks/delivery一致。工具业务结论仍是unknown（自由文本），本节通过结论依据逐项证据验收，不由runner succeeded推断。

64份/2581366字节源/新快照、原50份/2074815字节快照及原35份/230325字节审查材料取件重新逐项比对零错配。328的21份/487816字节普通报告、脚本与日志另存coordination/328-original-review/，不扫描隔离凭据或私有state。此后本合同/需求记录/用户手册仅补验收与加载说明，冻结快照不改，产品/测试仍匹配fix1。

| 独立执行 | 实际结果 | 边界 |
| --- | --- | --- |
| P2-1～P2-4、旧名册墓碑/OBS-2 | 全部通过，无必须修正项 | 独立API增补11项、本机增补21项通过 |
| Node页面JS/DOM | 68/68通过 | 进程内运行，未浏览器视觉人验 |
| 45项定向Python | 37通过、4失败、4错误 | ACL发布、CreatePipe、子进程/teardown环境限制 |
| 265项完整Python | 253通过、5失败、7错误 | 包含上述45项；同类环境限制，不称独立全过 |

P2-1/P2-2关键拒绝反例使用原ACL；两处明确替代仅用于成功配置发布与真实Popen的marker发布。OBS-1成功字段/失败原字节已补验。Codex原265Python+68Node全部通过不替代独立限制，原327 partial和失败记录不改。

328实际reuse_session续327同一session-13d42eaa-9929-4cde-9380-999435d9de22，confirmed_count=2、context_status=known，末623015/1000000=62.3015%。328于UTC11:59:28.441075、327于UTC11:59:37.359508分别收取completed，原消息2972/2971及业务结论保持。

非阻断P3保留：旧代码/直接构造的failed或pending墓碑若revoke_identity=false，existing-row重试不会重证；本片未生产部署，也未授权迁移此类旧行，不为此新增返修。真实私有ACL marker、junction、浏览器/生产加载边界保留。复核者未实查生产保护；Codex本次另以公开接口核实286仍queued/accepted/paused、七角色完整binding与派前一致、DeepSeek idle/无任务。

当前代码核验闭合，未生产加载或删除任何现有角色。[正常加载方案](ROLE_DELETE_DEPLOYMENT_20261024.md)已准备，须先确认；原始证据见review-fix1/、coordination/328-received.json、328-collected.json及328-original-review/manifest.json。

## Codex 首轮自检（历史记录）

29项新增Python、147项关联回归和68项Node检查通过，共244项不同检查；最后针对性组合30项含1项既有关联投影断言。关联组合初次169项中168通过、1项严格公开字段白名单需加入新deletion字段，更新后单项复跑通过；原失败不追改。真实Windows清理、普通drain子进程和隔离HTTP完整闭环包含在新增项内。生产角色、配置正文、私有日志和真实模型均未用作夹具。

安全自检摘要为 `.tmp/role-delete-v1/selfcheck.json`，原始首轮/关联与最终日志保留；冻结清单为 `manifest-v1.json`，源码/证据快照在 `baseline-v1/`。独立复核只写 `review/`，Codex暂停产品修改；尚无独立通过结论和生产部署许可。

## 327 独立结果与 Codex 修正（后经 328 定向复验）

327正式结果2971为自由文本partial；MCP业务字段仍unknown，不据runner succeeded称通过。50份/2074815字节原源/快照取件零漂移，原报告、35份/230325字节审查材料及失败记录保持在review/和coordination/327-original-review/。DSH实际new_no_candidate新窗/count1，末421001/1000000=42.1001%。独立176组合165通过/4失败/7错误，受私有ACL发布、CreatePipe和子进程DLL初始化沙箱限制；另API15通过、Node进程内68通过、替代ACL本地组合13通过/1跳过，不能合称独立244全过。

Codex已接手下列同片修正，不改原报告：

- P2-1：所有宿主health均须明确`owned_launches=[]`；原Popen已退出、外部manager已不存在也不能忽略未关闭子进程列表。原owner缺health拒绝，普通drain后复查；先删drain再删health，失败保留重试凭据。
- P2-2：文件目标默认只接受普通文件；Key、凭据metadata、control、health/drain被替换为目录时拒绝，绝不递归。只有专属档案与私有目录显式启用tree删除。
- P2-3：存在真实删除墓碑的共享身份，新增/领取任务必须明确项目，且仍在该项目名册，已删除项目仍拒绝；其它项目的旧名册身份兼容。未发生删除的旧全局成员行为保持。定时任务当前没有项目列，故对该身份拒绝新增/恢复/物化全局定时任务，不猜测归属；原全局未闭环任务也会阻止删除。创建、领取、schedule写入/物化守卫均与写入同事务，不改历史任务、不全局禁用共享Key。
- P2-4：managed+identity_exclusive若共用独占证明未通过，明确409 `role_delete_identity_proof_required`，不降格为shared/preserved成功。离册者先核对并恢复名册，随后按原证明吊销Key；不放宽轮换证明。
- 补检：旧名册但无ProjectRole的删除墓碑补记真实human创建者，避免NOT NULL失败；重试清空旧steps，关闭OBS-2的旧步骤闪现。

OBS-1明确口径：成功发布保持其它解析字段/角色映射，JSON空白和行尾可归一化；发布失败原配置字节保持。其余P3、DSH环境限制、未浏览器人验/未生产加载等继续保留。原反例的协调方修正前组合43项有13项失败与1项夹具created_by遗漏错误，修正后44项通过；新增无关项目范围反例进入最终组合。原失败不追改，最终结果与修正版冻结另列fix1文件，不覆盖baseline-v1。

19:22最终组合265项Python全部通过/零跳过，含45项删除定向、原生命周期/任务队列/绑定快照关联回归；Node68项通过。结果在coordination/fix1-final.log和fix1-node.log。当时修正自检333项不能替代独立复验，产品重新冻结，等待DeepSeek同工作线复验，原327仍partial/未收取；后续结果与收取事实见上方328记录。
