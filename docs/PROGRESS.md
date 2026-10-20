# Project Progress

Updated: 2026-10-20 14:05（Asia/Shanghai）。285恢复后仍running/in_progress、attempt2、无结果；用户要求“暂停整棵任务树”改名“中止任务”、移除“授权继续一批”页面按钮。与285同改web/app.js，按AGENTS同文件串行约束待其交付暂停后处理，尚未修改产品。284独立包保持、尚未按用户通知取件；默认用户通知交付后实查。

## 已确认的下一项页面小修（待285交付暂停后串行处理）

- 用户明确将“暂停整棵任务树”改名为“中止任务”，移除“授权继续一批”按钮（实际页面现文案为“授权继续一批”）。本次明确的是名称和页面入口调整，不自动改成cancel-tree、不删除后端resume-tree/SDK合同，不自动中止任何现有任务。
- 处理时同步必要的操作说明/失效页面helper及缓存引用，保原权限、整树作用范围和里程碑验收入口；名称简化不能误称仅影响当前子任务或能原地续跑。没有确认删除“在风险边界暂停”或“终止整棵任务树”，先解释实际行为，不扩大改动。
- 实查checkpoint当前立即撤销claim、转awaiting_human/risk_boundary，不会自动检测风险或等待执行至某个边界；cancel-tree取消所有非终态任务且控制canceled，原树不可恢复，但不回滚文件/删除已有记录。
- UTC06:04:20.802276任务285仍running/in_progress/attempt2、K3原实例、result_message_id=null；其隔离候选白名单包含web/app.js。AGENTS要求“需要修改同一文件…先串行”“跨线路集成前两方均暂停”，因此本轮仅记录已授权小修与解释，不插改285范围、不派第三片或中断其执行；完成285取件审查后再落地此小修并验证/人验。

## 当前285（用户新增查看权限修复，隔离执行中、尚未上线）

- 用户页面点“查看对话”被未加入提示拦截，要求能查看所有对话；范围确认明确选择“仅我的管理账号（推荐）”。原operator Key只读反查human:bobo/未输出凭据、与当前项目maintainer一致；这是管理入口事实，未做Browser身份验证。其它human/Agent不获全局查看权，不新建管理员体系或数据库字段。
- 根因：groups元数据允许human全览，app/workspace入口和messages GET仍按成员拒绝；仅改前端不足。方案用显式conversation_access.observer_member_ids名单（默认空），仅名单内已鉴权human且未禁用可全局查看Group/Task Hall；计划只配置human:bobo，当前生产配置未写。
- 权限接口只读本人能力；前端不凭ID前缀/旧缓存放权，换账号/登出和旧响应须失效。覆盖入口、历史分页/搜索、成果、Group消息/撤回实时及SSE断线补发；非成员查看为只读，发送/附件/回复/mention/任务/成员守卫保持，不自动加GroupMember。
- 实际task285“管理账号未入群查看对话权限修复”，UTC2026-10-20T03:34:10.219198，project prj_e8fe7066bbec/creator agent:codex/target agent:kimi（kimi-code/k3），Hall group:task-9c2fef8c38f24b628bf15aa438eed7c4。queued/assigned仅创建快照；完成后由用户通知取件，不主动等待。
- 用户手动暂停后返回；UTC05:52:26.843842以原agent:codex身份正常POST /api/tasks/285/resume-tree，slice_budget=0/authorization_ttl_seconds=5400。manual_pause/queued/accepted/无claim→active，epoch0→1，非委派/预算0/无委派到期保持；UTC05:52:31.963744原K3实例ins_5a0d307d038c已running/in_progress、attempt2。恢复前Win32_Process核bridge13844/parent9728且无子进程；未启停/解除owner、重建任务或删除原文件。证据.tmp/resume-task285/，原任务范围和隔离目录不变。
- 干净e4c45a07ee0a9320245658c37e4f9a9a4272400e、89冻结源/指定文档SHA；.tmp/admin-conversation-view-v1/baseline/只读，只有kimi/可写候选/sandbox/合成config与DB/证据。coordination/保存身份事实、原包/manifest/开发要求/回执；只两份正式进度为例外。
- 产品候选仅新server/conversation_access.py、routes/members.py/messages.py、main.py、web/app.js/workspace.js/index.html；相关新/旧测试白名单固定。不改models/db/auth/host/角色/Key/生产配置或284目录，与284产品白名单无重叠；用户明确新提出的权限修复另片，不顺带开群聊功能。
- 必须合成SQLite/ASGI真实路由与WS/SSE、Node真实入口接线/只读发送/账号切换等正反验证；无Browser/8000/原生模型/生产读取启停。首次实现自测交付暂停，Codex独立实查并直接修正；配置/正常加载/页面人验在复核后安排，当前仍未修复上线。

## 当前284（首次实现，尚未集成）

- “SQLite日志接收三表与事务核心”，创建UTC2026-10-20T02:59:03.023710，project prj_e8fe7066bbec/creator agent:codex/target agent:deepseek，Hall group:task-425cda60af724510862865e5366f8c37。queued/assigned仅派发快照；取件时核实际状态，不推断已完成。
- 干净30e5eb8047b24b659ea24815d37e586a0f84f4c7、82冻结源/指定文档SHA一致；.tmp/runtime-log-sqlite-core-v1/baseline/只读，只有deepseek/可写。coordination/保存manifest、完整任务、派前身份/要求及回执；三份协调文档为例外。
- 候选仅server/models.py追加RuntimeLogSource/Batch/Event三表及必要约束、新server/runtime_log_receive_core.py及两新核心/并发测试。默认关闭、显式engine/clock/limits，无server.db/global CONFIG导入；来源登记撤销/CAS、事务内真实成员及双向实例launch、批次/事件独立去重、重放/首次时间、容量/序号/回执同事务提交。
- 要求真实SQLite/WAL多store/多连接并发、冲突/禁用/轮换/撤销序列、异常/提交失败全回滚、响应丢失后重放/重启、UTF-8及全局配额证据。内部payload只接受后续服务端可信投影，不等于已实现raw writer映射/外部读安全；HTTP/查询/配置/宿主/outbox/生产禁改。
- 执行者首次实现/自测、完整裸talk-delivery-1按实际284校验后暂停；Codex独立实查、直接修正与集成，不返修/互派回审。默认用户通知后取件，不主动等待/自动派后续。

## 283复核与已确认方向

- [283复核](spec/ROLE_RUNTIME_LOG_RECEIVE_REVIEW_283.md)、[补正实施合同](spec/ROLE_RUNTIME_LOG_RECEIVE_DESIGN.md)。task283/creator agent:codex/target及作者agent:deepseek/project prj_e8fe7066bbec/Hall/ins_39ba69bf6dfe一致；原msg2890合法complete仅方案自报，原文SHA eafec2b0b993b2f8b50ef6cf4b485f8ddc65f26865b1e2600cd499f4fa950bc2，稳定引用ok；本地JSON值相同、排版/尾换行有差异。UTC02:53:51.162402已收取completed。
- DeepSeek取件时UTC02:42:40.844391已idle/无当前任务；79冻结SHA和非例外正式源保持，755dd60仅三份协调文档。162原件归档，复跑/反例只在independent-review/worktree，原候选/报告/失败不改，无返修/互派复核。
- 原48测试独立重跑48过/零失败错误跳过/0.844秒/server.db未导入；真实冻结writer隔离输出确认writer_run与manager_run独立、unknown实例及实际字段。
- 9反例全部失败：真实上传映射缺失、两run混同、换批重复、实例launch双向缺核、提交前撤销失效、两个store并发突破配额、中文UTF-8超页、损坏存储raw透传、无效outbox ACK删pending。首次探针页预算fixture缺五键而未到目标，保留首次6fail/3error；修正探针自身后9fail/0error，不冒称原型已修。
- Codex只补正设计：事件身份不含batch/ordinal、显式真实writer投影、三表事务统一权限重核/来源计数/事件/回执、二次投影与UTF-8预算、来源登记/撤销及首次空宿主、严格ACK。自己的补正称自检，产品/HTTP/DB/认证/配置/页面/宿主均未改。
- 用户已明确选择“按此范围开发（推荐）”，覆盖新增3张日志表、来源登记撤销、批次接收和只读查询；默认关闭、先隔离库验证，不需要为同一范围重复确认。先B2a表/事务/内核，再B2b投影与查询HTTP接线；生产启用/迁库/重载另验。
- 证据.tmp/runtime-log-source-query-design-v1/independent-review/：archive/source-result-message/original-delivery/worktree、original-48、两轮negative日志/JSON、stable-reference/collect-receipt/implementation-approval。无生产配置/Key/DB/日志/原生会话读取，零网络/模型/启停。

## 下一步与不变项

- 283收尾30e5eb8已推送，284已派DeepSeek隔离首次实现B2a三表/接收事务/来源登记撤销内核及自测；仅models追加日志表、新核心/新测试，HTTP/新配置/来源生产启用暂不接线。交付暂停后Codex独立实查、直接修正和集成。
- received完整writer投影、human-only查询/导出和host持久outbox/真实跨机器仍待；281/283原型均不等产品。C先只读盘点/dry-run，不默认跨run删除。日志整项完成后统一全入口预算21600且保显式覆盖，再会话复用。
- 用户明确当前TALK目录不改；main/独立worktree总目录布局仅针对以后新项目。本轮不迁目录、不创建群聊分支，不改变当前功能排期。
- 原角色/Key/模型/owner/启停、旧local scope/ref/cursor/导出partial与脱敏保持。B2a不把内部payload接口当可接受任意客户端JSON的公开接收口；B2b投影门禁须先闭合才能上线。

## 临时断网与任务树暂停；285已正常恢复，页面缺陷待修

- 暂停撤销整树claim，运行项回queued/accepted，保Hall/结果/磁盘文件；正常联网时bridge收到claim失效后取消本地命令，恢复会新attempt，不是原生模型上下文冻结续跑。独立根任务需逐棵暂停，断网本身不等于已下达暂停；服务端paused/idle不单独证明原生进程已退出。
- 实查发现普通非委派根的页面恢复参数不匹配：web/app.js resumeTaskTreeFromBlackboard固定提示/提交slice_budget=1..3，server/routes/tasks.py resume_task_tree对may_delegate=false要求0。284/285原派发回执均false。暂停入口可用，当前不要依赖此按钮恢复普通任务；285已按正确参数从正常API恢复。
- 11:38咨询时未操作；13:52用户返回后仅恢复285，并确认K3已重新接单。284未恢复/取件，角色/服务/owner/配置未动；用户14:05已选择移除页面恢复按钮、暂停改名，待285后串行处理，不自动加到285范围。恢复是新attempt，保已有文件与记录，不保证原生调用原地续跑。

## 已验基础与协作

- 282实现6f3f9c5，169项相关自检/67秒隔离过；五宿主正常加载、四角色ready/idle、77.568秒周期/原进程及60–90秒心跳、用户页面验收均过，加载记录1e43502已推送。API原进程和绑定保持，Codex桥接关闭；详[加载记录](spec/ROLE_HOST_RUNTIME_EVIDENCE_LOAD_282.md)。过去PID只作证据，未来先重核。
- 279真实轮询/完整下载/约150秒心跳保持；280绑定行197fe7a已用户人验，278人验保持。新宿主模型/六小时/跨宿主/生产异常/跨沙箱驻留/冷启动不从alive推断。
- 本人MCP agent:codex/agent、lead，项目prj_e8fe7066bbec；DeepSeek/Kimi K3首次执行自测暂停，Codex首次独立实查、问题直接修正自检、集成与进度Git。页面旧交叉要求保持，AGENTS/用户最新约定优先，不派K2.8新任务。
- 默认派后结束、用户通知取件，不自动等待/唤回；不做Browser验证。精确用量比例未提供，不臆测百分比。

恢复指令：继续项目。
