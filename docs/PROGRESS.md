# Project Progress

Updated: 2026-10-20 16:32（Asia/Shanghai）。用户同意先处理DeepSeek错误状态残留，Codex直接补正通用bridge，仅恢复本轮询自己的error，保护任务busy/执行错误/后续状态。新增14项及原相关用例共170项全过。代码完成，旧DeepSeek尚未加载，待确认仅该角色普通stop/start；285人验保持，B2b未派、Kimi继续暂停新派发。

## 当前补正：查询恢复状态（代码完成，待单角色正常加载）

- 详[补正和加载方案](spec/QUEUE_POLL_STATUS_RECOVERY_FIX.md)。基线54101f8，本人agent:codex/agent、lead；DeepSeek无当前任务，项目/全局queued及running为空，执行者无在途开发，Codex单方补正、自检，不新派任务。
- 查询失败/恢复以状态锁及本地来源版本限定；任务/消息/offline更新使旧恢复失效，上报失败保留重试，状态失败不污染查询失败计数，正常成功无额外请求，取消及非受管无心跳保持。
- 原5反例3失败/1错误/1通过；首次修正漏诊断辅助参数剩1失败，已修正、原日志保留。最终14新例及原心跳/轮询/CLI/正常停止共170过、0跳过、3.813秒，自检证据.tmp/queue-poll-status-recovery/。
- 仅cli_bridge、新测试和必要文档；服务端/DB/权限/配置/Key/模型/任务协议保持。只读原DeepSeek gen21/ins_39ba69bf6dfe/12612、manager11612、can_stop及无在途已核，error/unknown仍未加载恢复。方案仅普通stop/start该角色，保原manager/其它角色/API，无强杀/清owner/模型/新任务；按AGENTS部署门禁待确认实际加载。

## 当前285：开发、加载及页面验收已闭合

- 详[285复核](spec/CONVERSATION_ACCESS_REVIEW_285.md)、[加载/验收说明](guides/CONVERSATION_ACCESS_ACCEPTANCE_285.md)。用户要求仅自己的管理账号无需加入即可查看所有Group/Task Hall；计划名单只human:bobo，既有operator入口已确认该身份/项目维护者，不扩大所有human或Agent，不新建管理员表/自动入群。
- task285/project prj_e8fe7066bbec/creator agent:codex/target及原作者agent:kimi（kimi-code/k3）/Hall group:task-9c2fef8c38f24b628bf15aa438eed7c4一致。msg2892合法complete仅自报，raw SHA 735f7475d98a154a72c4c735b2dc5cefc5cdce8237b1f7e207a8213d96297563，JSON围栏保留、提取后与本地JSON等值/稳定引用ok；UTC07:23:44.622679收取succeeded/completed，原报告不改。
- 原89冻结文件与748原产物保持，18份交付关键文件归档；原基线e4c45a07ee0a9320245658c37e4f9a9a4272400e，原件.tmp/admin-conversation-view-v1/kimi/，独立复核/修正仅independent-review/worktree。原包漏cli三文件，从精确原Git基线补齐并核与sandbox相同；284已发布模型/文档差异单列，未覆盖三日志表。
- 原109项Python/29项Node复跑过；新7 Node+2 Python共9反例全失败，暴露退出/旧权限请求/登录失败、回复及旧发送按钮、SSE多页撤销/禁用。Codex直接修正后再补账号/撤回/上传及按钮动态检查，共新增13 Node/2 Python。联合验证162 Python（285相关111+284的51）和81 Node全部通过；自己的修正称自检，未派返修/互派复核。
- 产品7文件：新conversation_access、members/messages/main及app/workspace/index。默认空观察名单、仅合法human，已认证本人能力；历史/成果/Group消息撤回实时/SSE补发统一读权限；非成员只读、发送/成员/任务/后端撤回与legacy/direct规则保持。登录/退出/请求代次失效、异步房间切换和每页资格重核已覆盖；13新增Node含3个任务控制动态场景。两旧VM夹具补DOM依赖、缓存断言按两资源更新，原失败保留。
- 用户明确同意正常加载后，配置/SQLite私有一致性备份通过；配置仅加human:bobo观察名单。旧API15792/9808正常停止，新wrapper19504→launcher5236→uvicorn13952已核。本人能力human true/Agent false，原未加入285 Hall读200/发送403，无新消息/自动入群；三张日志表各0行，日志接收无接线、仍关闭。30旧表结构及29非心跳表记录保持（projects排last_seen_at），实例身份、Key/绑定/归属保持。详[285加载记录](spec/CONVERSATION_ACCESS_LOAD_285.md)。
- 五宿主及DeepSeek原进程未变；Kimi三个桥接在操作前已离线，Codex原停止状态保持。DeepSeek短断连后15:45:55已恢复查询，15:51:00仍成功，但error/ConnectError状态残留导致公开ready→unknown，未伪造idle或重启角色。此残留单独待处理，不能称全部角色页面状态正常。
- 证据.tmp/admin-conversation-view-v1/independent-review/：原始结果/归档/89冻结、原109/29、首轮9失败、扩展/联合162与81、集成、静态HTTP、load-plan-facts/load-plan/收取。用户本轮明确答复“验收通过”，确认原管理账号未加入任务的完整对话/成果可读、未加入时发送/附件/回复不可用；记录deploy285/human-acceptance.json。未执行Browser、模型、新任务或角色启停，不将此验收外推为DeepSeek错误状态已恢复。

## 任务中止/编号规则（页面已落地）

- 统一“中止任务”，调用既有pause-tree、影响当前根及未完成子任务，保留记录/文件/任务号。移除批次授权、风险暂停、整树终止三个重复按钮和失效resume helper；里程碑人工验收及原权限/后端pause/resume/checkpoint/cancel/SDK合同保持。
- 派发角色在重新安排工作时决定：方向不变可复用原任务号重新执行，需要换方向则关闭旧任务另建。不自动恢复人工暂停；新attempt不等于原生调用冻结续跑。原285暂停后以slice_budget=0恢复为attempt2的证据.tmp/resume-task285/保持。
- 用户将来在正常任务上可顺带验按钮；没有为验证创建/中止额外任务。新静态版本为20261020-conversation-controls-v2，仅app/workspace更新，其余六资源保持。

## 临时派发与当前职责

- 用户2026-10-20明确Kimi额度用尽，先不给任何Kimi角色新派发，直到用户恢复；285按现交付收尾。AGENTS已写临时优先约束，不停服/删角色/改绑定或重试额度。
- 后续首次执行先交agent:deepseek，一次一片；Codex独立实查、问题直接修正自检、集成/进度/Git。不派K2.8新任务，不改页面旧development_requirements或冒称更新。
- 本人MCP agent:codex/agent、lead，project prj_e8fe7066bbec；默认派后结束、用户通知取件，不自动等待/唤回；不做Browser验证。精确用量比例未提供，不臆测百分比。

## 已完成基础与后续

- 284已发布df437b8：三日志表/来源管理/接收事务内核默认关闭，30旧表/480旧AST保持；原37过、首轮10反例8失败保留，直接修正后51过并收取。详[284复核](spec/ROLE_RUNTIME_LOG_RECEIVE_REVIEW_284.md)。本次用户批准285加载时已创建三张生产空表，各0行；日志接收未启用。
- 256/257历史needs_changes保持，258已闭合准备问题；本轮此前核22/25原件及原review/稳定引用后收取旧结果，不执行旧迁移计划、不将原complete/partial改为approved。证据.tmp/legacy-role-page-control/legacy-close-20261020/。
- 282本地A实现6f3f9c5、169测试/67秒隔离及五宿主正常加载、77.568秒实机周期/原进程/心跳、页面人验保持；279真实轮询下载、280绑定行与278页面人验保持。Codex桥接仍关闭，旧PID只作历史事实。
- 285人验已通过。DeepSeek错误状态补正代码/170项自检已完成，下一步确认并正常加载单个DeepSeek、核新实例/两次心跳及页面。之后按原计划回日志B2b（真实writer版本化投影、受认证HTTP接收、人类只读查询），再持久outbox/跨机器及C全根治理；日志整项后统一全入口预算21600，再会话复用。本轮不自动派新片。
- 当前TALK目录不改，main/独立worktree布局仅未来新项目；不迁目录/开群聊分支。旧local scope/ref/cursor/导出partial与脱敏、角色/Key/模型/owner/启停守卫保持，C先盘点/dry-run不自动删旧数据。

恢复指令：继续项目。
