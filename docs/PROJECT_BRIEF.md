# TALK — 项目简报

> 本文件是所有参与开发的 agent 的**必读公共上下文**。

## 当前实施状态（2026-10-22）

2026-10-22 18:52最新范围补正：用户明确按运行器适配，当前DSH、Codex、Kimi Code三种已完成当前链路，K2.8/K3共用实现；仍少WorkBuddy，整项未覆盖全运行器。WorkBuddy既往仅桌面MCP人工单任务流程通过，原生会话续接/真实指标/阈值与十轮兜底尚未适配，不能用包内CodeBuddy CLI/ACP替代桌面证明。本轮仅只读核对和记录；下一片范围/验收待用户确认，尚未实施或派发。详[当前进度](PROGRESS.md)和[既往WorkBuddy接入边界](guides/TERMINAL_MCP.md)。下方为此前阶段记录。

2026-10-22 18:02最新：用户进一步明确允许Kimi短文本生产验收闭环、禁止开发派发。K3的303→304、旧K2.8的306→307均真实同窗/计数1→2，305/308新窗恢复/计数1，六条已全部收取succeeded/completed；原生双SHA、模型/alias、六次正式请求与计数通过。原宿主临时启动并正常停止/drain，三个Kimi最终停止无owner；302条原任务逐行、配置/绑定/Key/权限、286及其它角色保持。DSH/Codex/Kimi共用会话功能的当前运行器链路已接通；另一K2.8独立HOME未单验，60%/10次仍为受控验证，人工里程碑待用户确认。常规Kimi开发派发暂停，下一片/宿主统一启动另行确认。详[Kimi适配](spec/EXECUTION_SESSION_KIMI_ADAPTATION.md)及[当前进度](PROGRESS.md)。下方为此前阶段记录。

2026-10-22 17:34最新：用户允许Kimi验收额度，但明确不给Kimi派发任务。Codex沿原K3及旧K2.8各直接三轮原生验证通过：同ID/计数1→2、续轮回想、新窗完整恢复；真实模型alias/容量/双SHA核验通过，6次原生请求、零TALK任务。原API正常加载18580→10600，302条任务逐行/五角色/配置绑定/286保持，三个Kimi仍停止。共用适配的338项自检及21轮本地假模型证据保持；生产任务派发/领取/收取按用户约束未做，不冒称已实测。详[Kimi适配](spec/EXECUTION_SESSION_KIMI_ADAPTATION.md)及[当前进度](PROGRESS.md)。下方为此前阶段记录。

2026-10-22 17:15当前：用户明确Kimi适配仍由当前Codex直接开发。K2.8/K3共用kimi-code实现、按角色/模型隔离；API/MCP及领取入口已接线，338项自检、真实CLI2.0.2+本地假模型21轮（含同窗/60%/受控缺数10→11/新窗恢复）通过。Kimi额度暂停保持，未生产加载/真实账号验收，DSH/Codex仍为当前已加载可用范围；TALK页面、302条既有任务、配置/绑定、五角色记录及286保持。详[Kimi适配](spec/EXECUTION_SESSION_KIMI_ADAPTATION.md)与[当前进度](PROGRESS.md)。下方为此前阶段记录。

2026-10-22 16:20最新：用户明确同窗机制应覆盖所有角色，并指定Codex适配由本会话直接开发。当前DSH与Codex已工程接通并实机验证：205项自检，300→301同原生会话/计数1→2、302新窗基础恢复均完成收取。Codex原宿主正常恢复和单角色重载，未解除归属；297条既有任务、配置/绑定及其它角色保持。TALK页面按用户要求不改；Kimi尚未适配且额度暂停，不能称全角色完成。当前桌面同名自派400守卫保持，真实测试由合法human入口创建/收取。详[Codex适配](spec/EXECUTION_SESSION_CODEX_ADAPTATION.md)、[使用说明](guides/EXECUTION_SESSION_USAGE.md)及[当前进度](PROGRESS.md)。下方为此前阶段记录。

2026-10-22 10:19最新：292首次交付已独立实查，Codex直接补正并集成19份源码/测试；原生阈值/缺数边界和SDK/MCP全链路隔离验证通过，293→294真实同窗/增量回想、295新窗完整恢复均成功收取。当前DeepSeek/DSH链路已工程接通可用，等待人工里程碑验收；用户重连后MCP296→297真实同窗/增量回想、计数1→2均已收取，SDK/API亦已可用。其它runtime/GUI可见性/费用收益不冒称通过；宿主统一启动修复仍在验收及下一片确认后。详[292实查与验收](spec/EXECUTION_SESSION_USABLE_REVIEW_292.md)、[使用说明](guides/EXECUTION_SESSION_USAGE.md)和[进度](PROGRESS.md)。 下方为此前记录。

2026-10-21 23:01最新：用户明确“同窗口、阈值换窗、十轮兜底真正可用才算完成，未完成继续本功能”，292已派DeepSeek完整纵向实现API/MCP/基础合同增量、原生续接、真实指标、规则与ACK状态及隔离验证。80项目/57原生材料冻结，交付后Codex独立实查/直接补正及必要实机验收；整项当前未完成，288–291仅阶段成果。宿主统一启动问题延至本功能整体可用/验收后，旧顺序被替代；详[292合同](spec/EXECUTION_SESSION_USABLE_SLICE_5.md)与[进度](PROGRESS.md)。下方为此前记录。

2026-10-21 22:32最新：291只读入口/挂载方案已独立实查，Codex补正工作线/指纹/分类/失败边界等六组缺口；原静态复跑、12项定点核验和30引用核对通过，22:30:41已收取completed/结果2897。原默认headless无resume接线，采集器/真实续用仍未启用；DeepSeek在线空闲，配置/286/其它角色保持。下一优先按用户要求为宿主统一启动链路，未派新片；详[291复核](spec/EXECUTION_SESSION_LIVE_ENTRY_REVIEW_291.md)、[正式方案](spec/DSH_CONTEXT_WIRING_DESIGN.md)及[进度](PROGRESS.md)。下方为此前记录。

2026-10-21 21:53最新：用户明确确认后，291已派DeepSeek只读核实DSH实机入口/版本、配置与插件证据及采集器挂载点，交付最小接线方案后暂停。基线67b1a58，30项目/57公开原生文件冻结；不启停/改配置/额外模型或真实加载，286和其它角色保持。DeepSeek已恢复且派前idle，宿主统一启动问题按用户要求在291收尾后优先处理；详[291合同](spec/EXECUTION_SESSION_LIVE_ENTRY_SLICE_4.md)与[进度](PROGRESS.md)。下方为此前记录。

2026-10-21 21:10最新：关闭状态页面已获用户确认通过；用户另行明确允许恢复原DeepSeek宿主并普通启动一次，现manager18856/bridge22812、gen28 running/ready/idle，同一实例真实心跳推进60.055873秒。配置/绑定、286暂停和其它四角色保持，无新任务或产品代码变更；API与角色宿主分别运行，仅恢复API不会自动恢复宿主。启动页面待用户确认，详[恢复记录](spec/DEEPSEEK_HOST_RESTORE_20261021.md)与[进度](PROGRESS.md)。下方为此前记录。

2026-10-21 19:46最新：用户确认后Codex直接修正DeepSeek异常退出导致的关闭中悬挂：过期stop只读投影为待核实、页面明确关闭超时并持续刷新，人工恢复只排除领取已撤销的明确paused根任务。128项自检通过；19:41原API正常重载，19:42:24 DeepSeek gen24→25单次人工恢复为已关闭，归属释放、未启动角色。286全文/暂停、其它四角色、配置绑定保持，无新任务派发；页面待Ctrl+F5验收。详[本片记录](spec/ROLE_SERVICE_STOP_TIMEOUT_FIX_20261021.md)和[进度](PROGRESS.md)。下方为此前记录。

2026-10-21 19:15最新：用户明确允许恢复原API并补收290。原API进程已不存在、端口空闲，无在途任务；按已核原启动器恢复为launcher7764/child10096，healthz正常，19:13:09已收取290 completed、原结果2896/SHA保持。配置、五角色归属与进程事实均不变，五个记录角色进程仍不存在，未恢复角色或派新任务。57cb119产品和280项离线验证保持，会话机制仍未加载；详[290复核](spec/EXECUTION_SESSION_FALLBACK_REVIEW_290.md)与[进度](PROGRESS.md)。下方为此前记录。

2026-10-21 07:18最新：290条件十次备用已首次独立实查、直接补正并离线集成，170内核/76适配/34Node共280项全过，原27件/19冻结保持。补缺数掩盖非法/来源异常、证明时钟、旧低读数覆盖高值及历史/回执安全校验；可靠60%仍优先，第10可发/第11新窗。API连接被拒绝，collect未成功，最近submitted/结果2896待恢复后核对收取；未加载/启停或真实ACK/存储接线。用户要求不派新任务，本轮仅保存当前成果，详[290复核](spec/EXECUTION_SESSION_FALLBACK_REVIEW_290.md)、[最终API](guides/EXECUTION_SESSION_FALLBACK.md)与[进度](PROGRESS.md)。下方为此前记录。

2026-10-20 23:59派发记录：用户批准再开发一片，290已派DeepSeek首次实现占比缺失时条件十次备用/窗口计数，创建queued/assigned；基线ad46037、19公开文件676,842字节冻结。先同功能/范围/通道、再可靠60%判断，只有单纯缺数且计数可信才第10次可发/第11次新窗，恢复读数不清零，非法/错身份/数据矛盾不兜底。只隔离候选，不改运行角色/采集器/配置或启停；184原基线保持，新兜底尚未实现/验收。额度百分比不可读，本轮只此片、派后结束，用户通知后Codex独立实查/直接修正；详[290合同](spec/EXECUTION_SESSION_FALLBACK_SLICE_3.md)与[进度](PROGRESS.md)。下方为此前记录。

2026-10-20 23:22最新：289采集接口/内核适配已首次独立实查、直接补正和集成收取completed，原2895/15原件和51冻结保持；Node34/Python44/既有288的106项共184全过。补来源cut/序号顺序、字段状态/版本、错误回显、原生读取/回调边界；四份新源/测试无生产导入，运行角色未加载、真实版本/home/插件/数值未知。未启停/模型/真实会话读取，下一片仅建议只读实机入口/配置和挂载核验，未确认/派发；手册仍无入口，详[289复核](spec/DSH_CONTEXT_METRICS_REVIEW_289.md)、[采集说明](guides/DSH_CONTEXT_METRICS.md)及[进度](PROGRESS.md)。下方为此前记录。

2026-10-20 22:45最新：用户确认继续DSH真实上下文指标接入，289已派DeepSeek首次实现原生projection采集器/Python适配及离线链路，基线15f77b2，22份项目材料和29份原生源冻结，创建queued/assigned。实际进程核为headless/argv、非ACP、外层21600，但不能关联冻结npm版本，home/插件/真实占用未知；只隔离产出、不读真实会话/配置/凭据，不加载/启停或模型探针。288已收尾保持，交付暂停后Codex独立实查/直接修正，默认用户通知取件；续用/MCP/生产加载仍后续。详[289合同](spec/DSH_CONTEXT_METRICS_SLICE_2.md)和[进度](PROGRESS.md)。下方为此前记录。

2026-10-20 22:20最新：288离线会话内核已由DeepSeek首次实现，经Codex独立实查、直接补正和自检后集成收取completed。新增统一规划模块/106项测试，11,994组整数阈值交叉核验通过；补当前通道显式独占、基础合同引用/留档、UTF-8校验与回执核对。真实DSH指标/原生会话/任务MCP接线尚未接通，生产无新模块导入，不启停或模型探针；下一片指标适配仅建议待确认。详[288复核](spec/EXECUTION_SESSION_CORE_REVIEW_288.md)、[调用说明](guides/EXECUTION_SESSION_KERNEL.md)及[进度](PROGRESS.md)。下方为此前记录。

2026-10-20 21:48最新：用户明确“那确定了，动手开发吧”，288已派DeepSeek首次实现会话选择/60%换窗/首轮完整与续轮增量的离线内核，基线48526a7、22份公开材料冻结，创建queued/assigned。仅隔离候选一产品模块/一测试，不改运行中bridge/API/MCP/配置或启停，真实DSH采集和续用接线另片确认；交付暂停后Codex独立实查/直接修正，默认用户通知取件。Kimi暂停、286/日志/21600待办保持，不能据派发称整项已上线；详[首片合同](spec/EXECUTION_SESSION_CORE_SLICE_1.md)和[进度](PROGRESS.md)。

2026-10-20 21:21最新：用户明确取消固定10轮，改用上下文占用达到窗口容量60%换新会话；派发者可提前换，新窗首轮完整、续轮增量保持。安装版DSH公开源码确认相关数值及UI投影路径，但TALK尚未采集、桌面实机值未读取；投递前检查/在途不强停及未知默认新窗为待细化工程建议，不冒称60%实测最优。已同步[机制与使用说明](spec/EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)和手册未上线标记；本轮仅文档，不派新片/实施/S0或模型，287已收取及其它待办保持。下方十轮设想只保历史。

2026-10-20 21:08最新：用户明确由派发者灵活选择执行会话，新窗首轮带完整任务介绍、续轮只发增量，达到上限换新窗恢复完整；要求同时减少协调输出与bridge重复拼装，并记入使用说明。10轮为用户初提且无实测依据，本轮建议保留作试用上限、可提前换，最终默认/配置与计数细节待确认。已记录[需求和使用说明草稿](spec/EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)，用户手册仅说明当前尚未上线及真实入口落地后补齐步骤；本轮只文档，无新派发/实现/S0取证，287已收取及其它待办保持。以下为此前阶段记录。

2026-10-20 20:27最新：287只读方案已首次独立实查、六组补正并收取completed，原2893 complete自报与11份产物保留。42冻结/14安装源码哈希、102引用、合成测量复现及9项独立纯函数/静态探针通过；Codex补正运行事实边界、重试/缺失usage口径、续接收益、代次/目录隔离和锁冲突。默认源码无跨任务续用接线，实际argv/profile/补丁/home及真实缓存效果仍未知；未改产品/生产、未启停或额外模型探针。下一片S0脱敏实机证据仅建议待确认，未派发；日志/21600/286/Kimi约束保持。详[287复核](spec/EXECUTION_SESSION_CACHE_REVIEW_287.md)与[进度](PROGRESS.md)。以下为此前阶段记录。

2026-10-20 20:01最新：用户在恢复项目后明确回复“可以，就先做这个”，批准先做执行会话/缓存只读核查。287已派`agent:deepseek`，产品基线510c9c4、42份公开材料冻结，创建`queued/assigned`；仅隔离产出现状/usage证据/最小方案及后续验收，禁止产品或生产修改、启停与额外模型探针。Codex在交付暂停后独立实查，默认用户通知取件；Kimi仍暂停，286不恢复。仅该方案片提前，日志/21600预算待办与实施另片确认保持；详[核查合同](spec/EXECUTION_SESSION_CACHE_AUDIT.md)、[后续排期](spec/DEVELOPMENT_ROADMAP.md)及[进度](PROGRESS.md)。下方17:52暂停为当时决定，已由本次单片确认局部替代。

2026-10-20 17:52最新决定：用户明确选择“暂不启动新切片”，DeepSeek会话/缓存证据只读核查不派发，也不改派预算统一或本地日志任务。此前建议及改序均未批准，待办保持；286继续中止、产物未集成。17:48已确认的每片先确认规则继续有效：说明目的、范围、验收后获明确确认才实施/派发，旧“原计划继续”及上片验收不自动授权下一片，已批准片内必要实查/修正/验证/收尾保持。详[确认规则](../AGENTS.md)、[后续排期](spec/DEVELOPMENT_ROADMAP.md)及[进度](PROGRESS.md)。

2026-10-20 17:25方向调整（优先于下方旧方案）：用户澄清桌面应用目标：日志保存在产生日志的设备，跨设备分析通过导出文件并手动转移即可；当前不继续联网集中上传/接收。286由创建者agent:codex调用既有pause-tree普通中止，控制状态paused，当前领取已撤销；原DeepSeek已回idle/无当前任务，服务未停。隔离产物233份约8.78MB保留原位，不收取/验收/集成。原284关闭内核及三张日志表保留，不删库/表、不启用接收；HTTP上传、跨机器来源及outbox移出当前排期。本轮只处理日志方向，桌面内部本地服务/数据库及聊天/账号同步架构保持，未派新任务。 详[当前需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)、[调整后的日志计划](spec/ROLE_RUNTIME_LOGGING_REMAINING_PLAN.md)与[进度](PROGRESS.md)。

2026-10-20 17:12：日志B2b-1首片286已派DeepSeek，基线5246776/175冻结公开源和指定文档、仅隔离候选白名单；实现真实writer上传对象/服务端严格PreparedBatch适配，HTTP/查询随后串行，生产接收保持关闭。创建queued/assigned，交付暂停后Codex独立实查/直接修正，默认用户通知取件，Kimi暂停派发。详[286合同](spec/ROLE_RUNTIME_LOG_UPLOAD_PROJECTION_B2B1.md)及[进度](PROGRESS.md)。

2026-10-20 17:03：用户明确确认DeepSeek“启动成功、绑定保持”的页面验收通过，00bdcff/170项及02c7692实机加载门禁闭合。回原日志B2b，先固定真实writer上传投影和服务端严格适配首片合同，HTTP/查询随后串行，尚未派发/启用生产。Kimi继续暂停新派发，详[切片合同](spec/ROLE_RUNTIME_LOG_UPLOAD_PROJECTION_B2B1.md)和[进度](PROGRESS.md)。

2026-10-20 16:40：用户明确同意仅加载DeepSeek状态修复，已沿原manager11612普通stop/start为gen23/新ins_00acba0f8a9b/12284，持续ready/idle/无错误，同一实例心跳推进60.059秒。API、全部manager及其它四角色/模型绑定保持，代码00bdcff/170项自检保持；待刷新角色页确认，不派B2b，Kimi继续暂停新派发。详[补正与实际加载](spec/QUEUE_POLL_STATUS_RECOVERY_FIX.md)及[进度](PROGRESS.md)。

2026-10-20 16:32：用户同意处理DeepSeek查询恢复后的error残留，Codex直接补正通用bridge，仅恢复本轮询自己的错误，保护busy/执行错误/后续状态，状态上报失败可重试；新增14项及原相关用例共170项自检通过。旧DeepSeek尚未加载，已备单角色普通stop/start方案，待部署确认；不动API/宿主/其它角色，285人验保持、B2b未派、Kimi暂停新派发。详[补正与加载方案](spec/QUEUE_POLL_STATUS_RECOVERY_FIX.md)及[进度](PROGRESS.md)。

2026-10-20 16:21：用户明确确认285页面“验收通过”，管理账号未入群查看完整对话/成果及只读行为的人验门禁闭合，8be3921加载及原验证保持。本轮仅记录验收、更新进度/Git；DeepSeek查询恢复后的error状态残留仍单独待处理，不启停角色、不派B2b，Kimi继续暂停新派发。详[285加载/验收记录](spec/CONVERSATION_ACCESS_LOAD_285.md)及[当前进度](PROGRESS.md)。

2026-10-20 15:53：用户同意后已正常加载285，仅human:bobo全局只读查看生效，原未加入Hall读200/发送403，页面人验待确认；配置/SQLite私有备份完成，284三张新日志表各0行、接收仍关闭，旧结构/业务记录/Key/绑定/归属保持。角色未重启，DeepSeek查询已恢复但断连error残留、就绪unknown，单独待处理；Kimi继续暂停新派发，不开B2b。详[285加载记录](spec/CONVERSATION_ACCESS_LOAD_285.md)和[当前进度](PROGRESS.md)。下列为此前阶段记录。

2026-10-20 15:28：285管理账号未入群只读查看已独立实查，9个新反例失败后Codex直接修正，联合162 Python/81 Node通过并集成收取；任务停止入口统一“中止任务”，保派发者复用编号能力。静态HTTP已核，生产权限配置未启用/API未重载；加载会新增284三张空日志表（接收仍关闭），待用户确认该具体加载及后续页面人验。用户明确Kimi额度用尽，AGENTS已记暂停Kimi新派发，后续首次执行先DeepSeek。详[285复核](spec/CONVERSATION_ACCESS_REVIEW_285.md)、[验收说明](guides/CONVERSATION_ACCESS_ACCEPTANCE_285.md)及[当前进度](PROGRESS.md)。

2026-10-20 14:48：284 SQLite三日志表/来源管理/接收事务核心已独立实查，回执绑定和事务超时问题由Codex直接修正，最终51项通过并集成收取；旧30表/480模型AST节点不变，默认关闭，未接HTTP/生产启用。256/257历史needs_changes保持，已确认258替代后收取旧结果。285仍执行；任务中止后是否沿用原编号由派发角色按需求决定，页面简化待285交付后串行处理。详[284复核](spec/ROLE_RUNTIME_LOG_RECEIVE_REVIEW_284.md)与[当前进度](PROGRESS.md)。以下为阶段快照。

2026-10-20 10:55：283方案已独立实查收取，原48过、9独立反例失败，原文件inbox不集成。Codex补正SQLite三表事务/来源/稳定事件标识/投影与ACK合同，用户已确认三表、来源登记撤销、接收和只读查询，默认关闭先隔离库验证。先收尾后派B2a表/事务核心，HTTP/查询接线串行；未改产品或生产，当前目录不迁。详[283复核](spec/ROLE_RUNTIME_LOG_RECEIVE_REVIEW_283.md)与[补正合同](spec/ROLE_RUNTIME_LOG_RECEIVE_DESIGN.md)。

2026-10-20 10:21加载更新：用户确认继续后，282实现6f3f9c5已正常重载五宿主、普通恢复四原运行角色；77.568秒间隔实机seq/60秒采样、精确原进程观测及60–90秒心跳推进通过。Codex桥接保持关闭，API原进程/config/绑定保持，无清owner/强杀/模型探针。页面状态已获用户明确验收通过；下一片B来源/接收/查询合同，之后C全根治理，仍按日志→全入口预算→会话复用。详[加载记录](spec/ROLE_HOST_RUNTIME_EVIDENCE_LOAD_282.md)。以下各段为当时快照。

2026-10-20 10:01：282经Codex独立实查发现6组11处边界失败后直接修正，169项相关用例、67秒隔离serve/15检查通过，五文件合入收取原partial；固定本地manager/launch证据，无API/DB/认证/页面/生产操作。现有长期宿主尚未重载，下一步先核正常加载条件/授权，B接收/跨宿主与C全根治理仍待，本轮不开后续片。详[282复核](spec/ROLE_HOST_RUNTIME_EVIDENCE_REVIEW_282.md)、[当前进度](PROGRESS.md)。

2026-10-20 09:07：282已按281补正A合同派DeepSeek隔离首次实现本地宿主循环/原Popen证据，创建queued/assigned，195冻结副本及四文件白名单固定；正式产品/生产/API/DB/认证/页面未改。交付暂停后Codex独立实查，默认用户通知取件，不据派发声称已实现；见[进度](PROGRESS.md)。

2026-10-20 09:03：281方案已独立实查并收取，原16探针复跑通过但8独立边界反例暴露问题；Codex仅补正A本地运行证据合同，不采纳B接收原型为实施合同。下一片仅本地采集，无HTTP/DB/认证/生产变更，不声称宿主心跳已实现；详[281复核](spec/ROLE_HOST_RUNTIME_EVIDENCE_REVIEW_281.md)与[A合同](spec/ROLE_HOST_RUNTIME_EVIDENCE_DESIGN.md)。

2026-10-20：用户确认按原排期并明确280页面验收通过；279真实日志加载和280代码/页面里程碑保持。281已派DeepSeek做宿主独立运行证据方案与隔离验证（创建queued/assigned），交付暂停后Codex独立实查，再固定实现合同及后续跨宿主/全根治理，预算和会话复用不提前。本轮不改产品或启停服务，不把方案当实现；详[日志剩余计划](spec/ROLE_RUNTIME_LOGGING_REMAINING_PLAN.md)与[进度](PROGRESS.md)。

2026-10-19 23:02：用户明确许可后279已正常重载API、原宿主关启4运行角色，真实轮询/完整下载/约150秒心跳通过，Codex保持关闭；原审批拒绝证据保留。280经Codex独立实查及289项Node通过、五源合入、九资源字节核验并收取；缺思考强度留空的绑定行现等用户Ctrl+F5人验。本批两片收尾，不开第三片，完整日志整项仍待后续治理。详[279复核](spec/ROLE_QUEUE_POLL_DIAGNOSTICS_REVIEW_279.md)、[280复核](spec/ROLE_BINDING_SUMMARY_FORMAT_REVIEW_280.md)与[进度](PROGRESS.md)。

2026-10-19 22:36：279经Codex独立实查后直接修正5处导出校验，290 Python及24 Node全过、零跳过，六源/测试已合入收取，原partial保留、合同更正12键。生产尚未加载：正常批量停止4角色被自动审批拒绝，原API/角色/配置不变，待用户明确本次加载停启许可。280未收取/合入，整项日志边界保持，详[279复核](spec/ROLE_QUEUE_POLL_DIAGNOSTICS_REVIEW_279.md)及[进度](PROGRESS.md)。

2026-10-19 22:13：用户追加绑定行统一格式，随后明确缺思考强度留空、不显示“未提供”。280已派K3隔离首次实现：按运行器/模型/可得强度排序、精确旧Kimi登记名只保运行器短名，绑定/状态/权限不变；创建queued/assigned，未称修好。279日志后端范围保持，两者交付暂停后Codex独立实查/直接修正并串行集成，默认用户通知后取件。详[280合同](spec/ROLE_BINDING_SUMMARY_FORMAT_REQUIREMENTS.md)及[进度](PROGRESS.md)。

2026-10-19 22:03：用户明确开发接单轮询诊断补数，279已派DeepSeek首次实现/自测并交付暂停，Codex独立检查及直接修正。范围仅真实周期/连续查询失败/恢复证据接入统一JSONL，候选隔离、原页面/权限/启停/模型调用保持；创建queued/assigned，不称实现通过。278页面人验与0e4c61d保持，默认用户通知279完成后取件；宿主独立心跳/跨宿主/全根治理另片。详[279合同](spec/ROLE_QUEUE_POLL_DIAGNOSTICS_DESIGN.md)和[进度](PROGRESS.md)。

2026-10-19 21:41记录：项目管理者明确“验收通过，汇总进度”。278的诊断区文字精简/页面样式统一和主任务列表20项分页验收闭合；代码79f882d已推送，原284项Node、1项真实HTTP联调与九静态资源证据保持。本轮只登记验收与汇总，不改产品、不派新任务或启停服务；完整异常日志整项仍有健康补数/跨宿主/全根治理，下一次恢复先梳理该项剩余最小切片。 详[278复核](spec/ROLE_DIAGNOSTICS_LAYOUT_REVIEW_278.md)与[进度](PROGRESS.md)。

2026-10-19 20:18：276/277首次交付经Codex独立实查，发现问题后直接修正并串行集成、收取；301项Python、270项Node及1项真实隔离HTTP联调通过。统一JSONL下载/逐次阶段节点/参与任务20条分页已本机加载；五宿主正常重载，四个原运行角色恢复ready/idle且心跳推进，Codex原关闭状态保持。配置/绑定/Key/历史保持，暂停等页面人工验收，完整日志整项及后续排期未提前完成。详[276/277复核](spec/ROLE_DIAGNOSTICS_EXPORT_REVIEW_276_277.md)与[进度](PROGRESS.md)。

2026-10-19 17:37最新：用户确认统一诊断文件导出替代页面运行情况/日志/异常明细：按角色与时间区间生成下载，一份JSONL包含逐次运行节点（含每次模型预检）时间/结果、普通日志及内嵌异常，补采缺失阶段但不补造旧数据；另加角色详情“参与的任务”分页，默认20条/页。**本轮仅记录，用户明确要求等其说“可以开始”后才安排任务，尚未派发/开发。** 正式要求见[需求新节](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)，当前门禁见[进度](PROGRESS.md)。下列275等为原首版历史事实，不据“页面看到了”记全部人验通过。

2026-10-19 11:35最新：275 Kimi K3页面首次交付经Codex独立复核，补充3反例失败后直接修正离页/退出清除及详情预算；95项Node和1项真实隔离HTTP联调通过，串行集成274并收取。五角色显式来源/API已加载，human摘要/旧ref/详情200、Agent403/无Key401及静态字节通过。Codex配置写入换行失误导致首次API启动失败，已修复恢复；原五宿主普通关启角色后均running/ready/idle且90秒心跳推进，故障及旧日志保持。当前等Ctrl+F5后角色→运行诊断页面人验，完整日志的健康补数/跨宿主/全根治理仍待，不开下一片。详[275复核](spec/ROLE_RUNTIME_LOG_VIEW_REVIEW_275.md)与[进度](PROGRESS.md)；下列较早记录为历史快照。

2026-10-18 20:48最新：用户完成重启后，五角色日志代码实机加载均核验通过，新实例/原宿主直接父链、ready/idle、90–120秒心跳推进、真实bridge/queue日志及引用查询逐一匹配；DeepSeek旧run正常停止记录与跨重启旧引用保留。仅只读核验，271/1179bd0及原模型绑定保持；本轮收尾暂停，宿主/权限查询与全根空间治理未派，整个日志排期仍未完成。详[进度](PROGRESS.md)。

2026-10-18 20:41最新：用户正常重启DeepSeek后首位日志加载实机通过，gen9/new实例ins_4643da0b3d34/18396归原manager18784，新鲜idle心跳推进180秒，真实bridge/queue启动日志及按引用查询匹配。其余四角色仍原实例、未操作且待加载；不派新片、不外推原生/六小时能力。271收取/代码1179bd0及列表精简保持，见[进度](PROGRESS.md)。

2026-10-18 20:04最新：271首次交付经Codex独立复核发现问题，暂停后直接修正，293项Python相关自检通过并正常收取；持久诊断基础/通用bridge及本地定位完成，宿主/查询页面/全根空间治理及真实部署仍待，五个长期进程未重启加载。用户授权的角色列表两段文案精简已合入，详情与服务守卫保持，26项Node/12项Python及静态HTTP字节通过，等Ctrl+F5页面复验。本轮收尾暂停，详[进度](PROGRESS.md)和[271复核记录](spec/ROLE_RUNTIME_LOGGING_REVIEW_271.md)。

2026-10-18 19:11最新：五角色恢复后“都显示启动成功”人验已收尾推送ba46253。原排期第2项的首片271已派DeepSeek：持久诊断基础/通用bridge、异常关联/脱敏/跨重启追溯与本地定位，宿主/公共查询和页面健康后续；首次queued/assigned，交付后暂停，Codex独立复核及直接修正。默认派后结束、用户通知取件，见[进度](PROGRESS.md)。

2026-10-18 19:09最新：用户明确“都显示启动成功”，五角色人工恢复后的运行状态页面复验通过；f881724及313项Python/真实心跳父链证据保持，不扩大为模型实跑或跨沙箱重启常驻验收。当前收尾并准备原排期第2项完整异常日志的基础与通用bridge首片，DeepSeek首次执行、Codex独立复核并直接修正；默认派后结束、用户通知后取件，见[进度](PROGRESS.md)。

2026-10-18 19:02最新：用户已明确同意人工恢复方案，Codex完成human-only计划/人工解除归属、独立审计及CLI并直接自检，相关313项Python通过。18:57五角色均沿原配置/Key/ID正常新启动，真实父链和周期心跳通过、全部running/ready且无活动任务；原模型绑定/历史保持，等待用户刷新角色页确认。跨Codex沙箱重启持续驻留仍未验，不自动释放归属；本片暂停人验，之后才恢复原完整异常日志片。详[当前进度](PROGRESS.md)、[恢复指南](guides/ROLE_SERVICE_RECOVERY.md)。下列较早时间记录保留为历史。

2026-10-18 14:55最新：用户继续宿主恢复，五manager/bridge旧进程逐个只读证实不存在、无在途/排队任务；12:05:49最后心跳与12:05:50沙箱服务停止事件吻合，完整退出链未证。现有协议缺原Popen消失后的人工处置入口，已准备[恢复草案](spec/ROLE_SERVICE_ORPHAN_RECOVERY_DESIGN.md)，新增人工解除权限待确认，尚未实施或启停。状态提示人验及原绑定/历史保持，详[进度](PROGRESS.md)。

2026-10-18 14:45最新：用户确认修复角色“启动成功”与真实进程不一致。Codex直接补受管bridge周期心跳、本次实例新鲜度只读投影及运行中持续刷新；失联显示“运行状态待核实”，不清归属、不重发启动。277项Python/60项Node相关验证通过，API已沿原启动器正常重载，五角色实际接口unknown且原绑定/服务持久记录保持；用户已反馈状态与详情提示符合预期，本片状态提示人验闭合，不扩大为运行能力验收。五角色本体尚未恢复，先解决宿主恢复条件，再按原排期推进完整异常日志；历史迁移验收保持。详[进度](PROGRESS.md)。

2026-10-18 13:21最新：用户要求269收取及重开窗口前汇总；269已由原human:bobo入口收取，原invalid正文不改，270补验/五角色历史验收保持。原API已从同入口恢复（launcher9988/uvicorn10320）；旧五角色宿主与bridge PID本次均不存在，未重启或接管。新窗口先核运行条件，再继续完整异常日志切片；详[进度](PROGRESS.md)。

2026-10-18 08:47最新：旧Codex独立浏览器登录CLI已exit0，但gpt-6.1-sol/xhigh原生接口明确不支持当前ChatGPT登录；两次探针失败及诊断已留存。账号公开列表有gpt-5.6-sol/xhigh，待用户选择，不自动换模型。尚未登记/补录/启动或创建新任务，已验四角色保持；详[进度](PROGRESS.md)。

2026-10-18 08:12最新：用户指定Codex直接迁移最后旧Codex CLI并确认gpt-6.1-sol/xhigh，旧启动记录不知。原本人Key来源/无旧bridge/未受管事实已核；独立CODEX_HOME已备，设备码被工作区禁用后改标准浏览器登录待CLI确认。新增可选独立任务命令接线，30项bridge/10项本地自检通过，尚无模型、登记/补录/启停或新任务；已验三个Kimi及DeepSeek保持，详[进度](PROGRESS.md)。

2026-10-17 23:52最新：用户确认DeepSeek页面三步均通过，gen4正常stop→gen5ready及新ins_d2b05a620405/16712仍归原manager12536已只读核验；原Key/全部绑定名册/其它服务保持。268原2822与收取保持、旧接单实例正常offline不重跑。DeepSeek迁移正式验收，三个Kimi和DeepSeek均完成，只剩旧Codex CLI，本轮收尾暂停，详[进度](PROGRESS.md)。

2026-10-17 22:25最新：用户确认原Kimi页面三步均通过，根只读核两轮正常启停及当前generation7/ins_619c2a3c3e52/10496仍由原manager17672持有，原Key/全部绑定名册/两K2.8服务保持；原Kimi迁移正式验收。267原回传/收取及266原件/18自检保持，正常关闭后的原接单实例offline不重跑。三个Kimi均已受管/人验，下一步DeepSeek准备、Codex CLI最后；本轮收尾暂停，不操作Browser或另启服务，见[进度](PROGRESS.md)。

2026-10-17 22:20最新：267/msg2821最小回传已独立核验收取，实际attempt1由原Kimi受管ins_b1c260cb0571完成，固定标记/作者/Hall/K3快照正确，原manager17672/924 idle无错，原Key/全部角色绑定名册及两K2.8服务保持。只读核验与收取，无启停/模型重触发/额外Hall回评；原Kimi迁移目前仅待页面三步人工验收，未推进下一角色，详[进度](PROGRESS.md)。

2026-10-17 22:11最新：原Kimi独立登录CLI exit0、精确K3无工具探针通过，原Key身份/命令tools档保持；产品API仅新增K3 choice并legacy-attach原agent:kimi，无重建/轮换。corrected专属manager17672完成generation1启动→generation2正常关闭释放→重读不自启→generation3/ins_b1c260cb0571/924 ready，两个K2.8保持。最小回传267已派、默认用户通知后核验，页面人验仍待；266原partial/41件及根18自检保持，首次操作标识422/协调状态断言假超时原件留存，详[进度](PROGRESS.md)。

2026-10-17 21:58最新：266准备已独立核验、Codex直接补正并收取，原2820 partial/41件保持。根修drain标记写入失败丢管理器及验证夹具，最终18项通过；用户确认原Kimi为K3，USER.md原命令Key内存GET身份通过，明确tools档/目录/旧3600，受管保既有21600。当前只为原agent:kimi发起独立原生登录待授权/CLI成功；精确K3探针、choice/保ID补录、受管启停/回传/人验尚未执行，两K2.8保持，详[进度](PROGRESS.md)。

2026-10-17 20:40最新：用户允许继续，266已派DeepSeek准备原agent:kimi保ID受管迁移，先核原模型/命令/可信Key与登记/精确runner-choice缺口，生成可审单成员入口；当前binding unconfigured，旧实例不作当前健康/原模型证明，不猜或重建。本片只读盘点/隔离准备，无生产写/登录/模型/服务切换；交付暂停后Codex复核直接修正。265已发布6481dce、两K2.8验收/现状保持，DeepSeek及Codex最后，默认用户通知266完成取件。详[进度](PROGRESS.md)及[历史](PROGRESS_HISTORY.md)。

2026-10-17 14:07最新：旧K2.8单角色试迁移已正式验收通过。262固定回传由本轮受管实例完成并独立核验/收取；用户随后确认页面“关闭→刷新不自启→再启动ready”三步均通过，服务端generation7 stopped/generation8 ready吻合，原manager继续持有新进程。原ID/Key/模型绑定/既有历史保持，其余四角色未迁移/启停。c129a63停止修正/161回归沿用，本轮仅文档收尾，不开新角色迁移。 详[进度](PROGRESS.md)。

2026-10-17 13:53最新：用户明确允许两个K2.8共用runner改managed_cli，但仍只启旧角色；标记已登记，adapter_status仍unverified。旧K2.8首次关闭暴露bridge未读停止文件，Codex直接补通用CLI停止监听，161项相关回归通过；原失败经独占控制台普通Ctrl+C/原manager正常回报恢复，无强杀。修正后同一manager启动→控制文件正常关闭/释放所有权→再启动ready通过，真实argv保21600/tools/原alias。最小任务262已派给旧角色，按默认通知后取件，尚未核接单结果；其它四角色未迁移/启停。 详[进度](PROGRESS.md)。

2026-10-17 13:26最新：旧K2.8原入口已正常退出，专属登录和原alias固定文本探针通过；root保原tools档/显示名/目录后23项相关验证通过。运行中的旧API缺259接口，已核独占终端且无在途任务后正常重启加载新版本；legacy-attach实际201成功，原ID/Key/绑定/历史保持。共享runner改managed_cli被自动审批拒绝，因为会同时扩大新页面K2.8的受管启动资格；已请用户明确允许这一个共享影响，未改标记/未启动角色。未同意前不绕过或重试，本轮仍只迁旧角色，详[进度](PROGRESS.md)。

2026-10-17 09:47最新：261准备片已收取，Codex独立复核后直接补正两辅助入口，最终21项相关验证通过；原MCP2804自由文本unknown/本地partial及失败原件保持。根已核Kimi CLI2.0.2，旧K2.8启动器仍运行；只建立候选隔离native目录，设备登录等待超时/专属config缺失，实际补录/升能力/受管启动均未执行。待用户在原终端Ctrl+C正常退出，再重新独立登录后继续原授权内的单角色切换。执行用pilot-one/independent-review261/corrected/，不使用原整DB哈希采集器，不把主文件hash不变/默认目录缺失当零写或从未受管证明。详[进度](PROGRESS.md)。

2026-10-17 09:20最新：用户要求先移一个，261已交DeepSeek仅旧agent:kimi-code-k28-preview的真实只读预检与可审执行包，交付暂停后Codex复核并在本次授权内实际切换。保原ID/Key/绑定/历史，不迁其它四角色；核旧入口空闲/正常退出与隔离登录，未验能力不盲升。当前serve无单成员过滤，执行包须保证只候选claim且同manager持有owner。仅准备，不先apply/启停或调用模型；260已发布42738d9、实际迁移仍未执行。默认通知“261好了”后取件，详[进度](PROGRESS.md)。

2026-10-17 09:10最新：260宿主产品片B已收取，Codex独立复核首次实现后直接修正配置校验/预算快照问题，74项相关验证通过，本轮发布。新增逐runtime模板、内置默认21600/显式覆盖及同argv预算诊断，保旧global/custom与身份/choice/能力/owner守卫，不改claim/report或MCP/T-W。[宿主合同](spec/ROLE_HOST_RUNTIME_CONFIGURATION_DESIGN.md)已更新；原2801 partial/失败/开发证据保留，自修验证不称外部独立复核。259已发布ea21d81；5角色真实平移、原生/登录/模型/常驻宿主与255人工仍待，下一步核实原Key/公开模型/真实能力后逐角色切换，详[进度](PROGRESS.md)。

2026-10-17 08:22最新：259保留身份补录产品片A已收取并本轮发布。Codex独立复核后直接修正双入口操作键隔离缺口及非空超长角色名静默换ID问题，162项相关回归+2项显式WAL并发探针通过；原partial/8源与失败证据保留，自修部分为Codex自检，不称外部独立复核。新增human-only legacy-attach、独立补录审计与精确legacy_attach来源，保原ID/Key/绑定/历史且不启动服务；详[补录合同](spec/ROLE_LEGACY_ATTACH_DESIGN.md)。5角色实际登记/迁移未执行，下一片宿主per-runtime模板/21600，再做真实逐角色切换；255人工/原生仍待。详[进度](PROGRESS.md)。

2026-10-17 07:45最新：258准备片经Codex实际代码复核、21项相关隔离测试和5项新增探针通过，Hall2795后已收取；原partial/旧256/257报告保留，5角色实际登记与页面启停未执行。259已派DeepSeek首次实施[保留身份补录产品片A](spec/ROLE_LEGACY_ATTACH_DESIGN.md)：human-only legacy-attach、原ID/Key/绑定/历史保留、独立补录来源与宿主精确准入；不伪造创建操作、不启动服务或升能力。完成后Codex复核并直接修正，宿主模板/21600及真实迁移另片；默认通知“259好了”后取件。详[进度](PROGRESS.md)。

2026-10-17 00:09最新协作约定：用户要求DeepSeek只负责首次执行，Codex派发并独立复核首次交付，发现问题直接由Codex修正、验证与收尾，不再反复派DeepSeek返修或回审。258按已派范围完成暂停，后续遵循新分工；共享目录单方改码、原始证据、必要测试与人工验收继续保留，自检不称他人独立复核。已同步[项目规则](../AGENTS.md#当前协作方式2026-10-17用户最新约定优先适用)与[进度](PROGRESS.md)，不追改历史任务/生产开发要求。5角色登记迁移仍未执行。

2026-10-17 00:04最新：257已去除旧身份经CREATE补录的错误步骤、修正实际凭据读取与秘密列采集，但根定向复核仍needs_changes：全局截前200实例会漏掉最新busy及其它目标，正文读取监测未接线仍报0。原257/msg2788 partial保留未收取；258已交DeepSeek仅在prepare-v3修正SQL最新/有界事实与证据口径，原v1 22/v2 25件不改。5角色尚未登记迁移，保ID补录产品能力及宿主模板/预算通道仍待，255人工/原生验收未通过。详[进度](PROGRESS.md)。

2026-10-16 23:15最新：256迁移准备初审needs_changes，原msg2785合法complete自报保留未收取。根用假Key/临时SQLite/真实创建schema复现两项P1：4旧成员被安排新建身份接口补录、凭据哈希/秘密列读取与零正文声明不符。257已交DeepSeek仅在prepare-v2修正，保原22件/根证据与860产品基线；目标仍为全部5角色保身份/模型/历史迁入页面启停，实际登记/迁移未执行。真实凭据来源、保ID补录能力及宿主模板/21600通道仍须闭合，不直接把缺文件交人类重建。详[进度](PROGRESS.md)。

2026-10-16 22:50最新授权：用户要求把当前全部5角色登记并切换页面启停，作为255真实自动启动验收前置。256已派DeepSeek准备可执行迁移首片，Codex后续独立复核；当前仅盘点/默认dry-run/逐角色配方与回退，不改生产/停旧入口。实查Codex/DeepSeek/Kimi无绑定、两个K2.8已绑定但唯一Kimi运行器unverified/unknown，受管状态为空，host配置开启不证明进程运行。保留身份/模型/历史，真实能力通过后逐个切换，DeepSeek与协调入口最后；完整日志/预算/删除另片。255代码已发布019bb99、人工及原生能力仍未通过，最新状态见[进度](PROGRESS.md)与[迁移需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)。

2026-10-16 22:33最新：255前端经DeepSeek独立实读、95Node/26Python/14VM及8项Node变异复核通过；根核11候选/842保护SHA及证据，Hall裁决2783后已收取，前端11源本轮提交发布，六资源20261016-role-auto-start。新create自动首次启动意图/旧缓存原样/配置与入队及实际状态分开均闭合，后端98beb9c保持；目前暂停等[页面人工验收](guides/ROLE_AUTO_START_PAGE_ACCEPTANCE.md)，真实原生能力另验。原MCP围栏自由文本保持unknown，根无损提取校验；原静态探针未显式绑定临时DB的范围遗漏已留痕并由根隔离补验，不能声称原DB完全未写。详[进度](PROGRESS.md)。

2026-10-16 22:05最新：用户授权下一片，Codex前端自动首次启动候选完成，255交DeepSeek独立只读复核。新create显式auto_start=true，旧缓存原键载荷保持，配置/入队/真实服务状态分开；11源冻结，95Node/26Python契约自测通过，六资源20261016-role-auto-start，源码尚未独立通过或提交。后端98beb9c通过事实保持，生产服务/能力/凭据不改，真实页面与原生能力仍待验；默认派发后结束，用户通知再取件，详[进度](PROGRESS.md)。

2026-10-16 16:40最新：254定向返修经Codex独立实际代码复核、63/63相关模块与原9/9 API/SQLite边界探针通过，F1/P1及F2/P2闭合，254已收取。250修正后8源本轮提交发布，原250 failed/报告及初次失败证据保留；前端auto_start载荷/文案、生产部署与真实受管能力仍待。用户最新指定后续DeepSeek替代K2.8，当前Codex/DeepSeek分工及AGENTS已同步，不改永久项目要求或既有任务。下一片前端Codex实施/DeepSeek复核，先完成当前功能，再做日志/旧角色迁移等已确认需求；详见[当前进度](PROGRESS.md)。

2026-10-16 15:28新确认：完整异常日志必须作为必要信息持久留存，旧角色后续保留身份/绑定/历史统一迁入TALK受管服务，逐个验收页面关闭→启动及接单回传。[正式需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)与手册待上线区已记录；日志脱敏/跨重启追溯、接单循环健康和所有权守卫保持。当前仅记需求，254已在用户重启后由新实例接单，原事务/测试返修范围不扩；先完成当前自动首次启动功能收尾，再分片实施日志和迁移，不并行改共享源码/能力配置或启停服务。

2026-10-16 15:06最新：250既有8源独立实读与121/151隔离测试通过，但9项新增API/SQLite边界复现P1：入队INSERT撤销外层事务后仍200/created并补写auto失败标记；另有external测试先PATCH后注册、实际测unknown的P2夹具缺口。254已交旧K2.8仅两文件定向返修，根停止审查供开发，默认用户通知“254好了”取件；250原failed/原报告/8源副本及失败证据保留，未验收/发布。253→248→246已收取、零模型准备通过事实保持；新角色真实能力/前端自动载荷/全角色6小时/删除/UI251视觉仍待。详见[当前进度](PROGRESS.md)。

2026-10-16 11:11最新：252旧K2.8预算独立复核通过并收取，5入口/模板/测试/指南文件默认21600秒及可覆盖参数本轮发布；开发者196与独立70项/针对性探针分别通过，候选与134保护源、250八源SHA一致。运行实例仍旧值，空闲重启才生效；其它角色统一6小时仍待独立实施，MCP等待不改。用户再次明确两个K2.8删除其中一个不影响另一个，今后需重新“创建角色”，例子已同步需求与操作手册，删除按钮未实现。指南基线SHA差异为CRLF/LF，原证据保留；旧分级叙述/PS5.1编码限制另记，重启建议Python入口。250仍failed未验、UI251仍待人工验收。

2026-10-16 11:04最新需求：用户明确所有TALK角色启动默认单次执行6小时（21600秒），仍可显式覆盖；另要求角色详情启动/关闭旁增加删除角色，删除本项目角色配置/专属凭据、保留历史任务与成果，需要时重新添加。[正式需求记录](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)与用户操作手册已同步，替代原删除方案保留完整绑定/说明/策略配置的方向。本轮仅记需求，通用代码仍600秒、其它启动入口未统一，删除未实施；252仍只复核旧K2.8原包，不并行扩码、不重启实例。

2026-10-16 10:50最新：用户明确选择旧K2.8默认单次CLI预算6小时，Codex已准备默认21600及check/render/launch --timeout、PowerShell -TimeoutSeconds可覆盖候选，196项离线测试与PS语法通过。252已派旧K2.8独立只读复核（不恢复250），5候选未独立通过/发布；当前运行实例仍旧值，之后空闲重启才生效。MCP读取等待/通用bridge600/HTTP15不改；250八源SHA保持未验，251页面仍待人工验收。默认等“252好了”取件。

2026-10-16最新：250后端运行约60分钟触发3600秒执行超时，原8源与本地报告/测试材料保留未独立验收，不提交/回滚或自动重派。251是另一项“详情只显示发起人”小修复核，已通过并收取；9个前端/缓存测试候选已合入，共享环境26页面契约/11导航、静态首页+六资源字节核验通过，版本20261016-task-initiator-label，待用户Ctrl+F5验收。后端代码SHA保持，自动启动未宣称上线；原MCP混排报告与错误哈希初稿保留，根按本地合法交付、真实代码/最终证据核定。当前旧K2.8已暂停，先收尾UI再独立审250，不把两任务混作重试。

最新（2026-10-16）：页面5de19e8已获用户本轮整体验收，配置成功自动打开一次角色开关目标保持。249方案经Codex独立五组隔离复核通过，249/247已收取，[正式自动启动实施合同](spec/ROLE_AUTO_START_DESIGN.md)发布待实现。248独立35/35单任务零模型通过，但新角色原生/孙进程与整体硬时限仍待补验，248/246未收取。用户已启动旧agent:kimi-code-k28-preview并明确下一切片改由Codex和旧K2.8协作，不派DeepSeek：250交旧K2.8实施后端8源/测试文件，Codex独立复核/文档与Git收尾，原永久开发要求不改。当前前端仍未接自动意图，生产/unknown/unverified不改，不把准备/入队当实际ready或模型版本证明；默认用户通知“250好了”后取件。

最新部署反馈：用户已真人登记模型并保存“Kimi k2.8”；2026-10-14 23:19明确授权后，宿主PC-202312301323/version1开启、该请求真实配置provisioned并进入角色列表。三档/仓库外私有Key/本人身份与元数据已核，worker仅处理这条请求后退出；未部署常驻/启动CLI/调用模型，Kimi仍unverified/unknown。等待人类刷新确认详情“配置已完成”，完整功能门禁及原生能力保持。

最新：#241后端由DeepSeek修正、Codex独立复核通过，241→240已收取，运行器筛选/Kimi公开模型登记/真实ID创建补正统一发布。根独立22新/166旧、真实ID隔离HTTP及生成器/64字符/worker私有假Key核验通过；240独立235Node/26Python/18新/9变异沿用且前端12源未变。原partial/失败保持，完整功能仍待[人工复验](guides/ROLE_CREATION_PAGE_ACCEPTANCE.md)。

创建允许合法已登记、未退役的运行器；Kimi空模型目录可由真人点击登记本项目已有bound K2.8公开维度，再使用actual choice保存意图。两个创建入口runner_id统一注册同源slug/64校验，未弱化其它凭据防护或改变生产ID/原绑定。生产目录准备仍需人类操作，unverified/unknown不代表原生控制就绪；先重载TALK服务并Ctrl+F5，缓存20261014-role-runner-options。

用户明确R1-4前端由Codex开发、DeepSeek独立复核；后端/宿主由DeepSeek承接、Codex独立复核，Codex接手修正仍由DeepSeek复核。230–239准备/server/宿主/前端链均已收取：[页面创建配置请求合同](spec/ROLE_CREATION_PROVISION_REQUEST_CONTRACT.md)的三表/共享守卫/A1–A10/C1–C4及默认关闭worker已落地。server独立新79/旧166/原7与WAL回滚证据保持；宿主独立新50/旧320/原6/检出3/独立13分别通过。完整创建/配置前端经Codex补正、239独立复核通过并整链收取发布；独立221项Node、26项Python页面契约、22新用例/27修正版审查/10变异与隔离实际HTTP/worker闭环通过，[页面验收](guides/ROLE_CREATION_PAGE_ACCEPTANCE.md)待人类执行，浏览器视觉及完整功能人工未验收，同机回环/默认关闭/human-only保持，不夹带跨机Key/TLS/D7或改写页面分工，真实原生能力仍未验。

235/236宿主初版缺口经返修及Codex定向修正、237独立复核闭合，237→236→235已收取。请求驱动逐HTTP资格/取消/预算守卫、一次性Key私有发布/元数据恢复、真实三步与失败已上报非零退出已验；原失败/complete自报/236 MCP围栏unknown保持。宿主使用见[worker指南](guides/ROLE_REQUEST_WORKER.md)，当前只代码与隔离证据，生产配置/凭据/服务不动。完整前端已接线并待人工验收；通过后外部/归档/退出继续同功能，I-4后置。

R1-3页面反馈经#227初版、Codex修正/#228复核及列表单状态补正/#229复核完成，227–229已收取。当前列表仅显示当前服务状态，启动/关闭按钮只在角色详情；全部启动仍在角色搜索旁，批量反馈独立成区，详情无服务状态标签，搜索重绘回归已闭合。#229独立197项前端用例逐文件进程内运行与24项Python页面契约通过，用户于2026-10-12明确[本轮页面基础验收通过](guides/ROLE_SERVICE_ACCEPTANCE.md)，对应版本34e9df4，R1-3页面门禁释放。后续R1-4，I-4后置；原生运行器/模型能力未因本次页面验收确认。

最新角色体系方向：取消固定“决策/执行”分级，保留只作用任务发起者 created_by 的主动/被动模式；项目按运行器→模型→名称/介绍新增独立角色，保存并配置身份，提供删除、全部启动、逐角色启动/关闭及宿主退出清理。角色生命周期 R0 已在2026-10-11经 #213→#214→#215 补正、Codex独立复核与定向合同澄清后发布：[正式合同](spec/ROLE_LIFECYCLE_DESIGN.md)、[实施计划](spec/ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md)。R1-1已由#216开发、#217补正并经Codex独立复核收取：后端目录、原子创建/凭据恢复、独立权限源和实例维度已落地，独立476项运行与WAL并发/实际写入故障证据通过；尚未执行生产角色配置、数据库迁移/重载。R1-2经218–221补正、Codex定向修复和222独立复核整链收取：三步配置作业、宿主身份档/私有Key/精确预检与bridge/页面固定分级迁移完成。Codex684项Python证据集合和222独立143项重点通过（不叠加）；[配置合同](spec/ROLE_PROVISION_CONTRACT.md)/[验收指南](guides/ROLE_PROVISION_ACCEPTANCE.md)已发布。用户已确认R1-2三项页面基础验收；R1-3经223/224返修、Codex两轮定向修正和225/226独立复核，受管CLI协议、常驻宿主与页面启停/全部启动已完成，226→225→224→223已收取。R1-3本轮页面基础人工验收已通过，真实原生启停仍未验；[服务合同](spec/ROLE_SERVICE_CONTRACT.md)/[验收指南](guides/ROLE_SERVICE_ACCEPTANCE.md)已同步。完整创建/配置页面、删除/外部桌面/退出清理继续R1-4。C1–C4原登记/绑定/快照/只读基础保持。原生登录、受管进程及页面后续单片推进，WorkBuddy控制/隔离与真实模型/主动等待未验；I-4后置。方向依据见[角色生命周期方向](spec/DEVELOPMENT_ROADMAP.md#2026-10-10-项目角色配置与服务生命周期最新确认方向待实施)。

发起者合同 v3 已发布；I-1 #172/#173 工具代码独立通过并收取，当前 Codex MCP 加载核验通过。I-2 #174/#175 固定主控页面退役经独立实际代码复核通过并收取，当前“项目设置”只显示开发要求与调度模式；页面不再依赖固定指定，协调责任按具体任务 created_by，模式只约束任务发起侧。资源 20261007-initiator-mode-ui，独立 Node149（同进程）/Python页面12及导航/符号探针通过；默认进程隔离因宿主 spawn EPERM 为 not_run。

I-1/I-2 同轮用户页面验收已于2026-10-07通过，人工门禁释放；I-0准备176/177已独立通过并收取，正式[身份切换与回退清单](guides/CODEX_TALK_IDENTITY_SWITCH.md)已发布。用户已明确授权实际切换：配置已备份并换既有agent:codex Key，API身份/名册和独立启动核验通过，重开后当前聊天MCP已实测agent:codex/kind=agent，新任务178的created_by=agent:codex，DeepSeek核验经Kimi179独立A-H复核通过，179/178均由Codex收取，当前入口被动闭环验收完成；179消息混排导致MCP unknown，已核本地合法报告与完整消息一致，原报告保留。项目passive/version6与effective null/not_bound保持，保存active仍仅意向；I-3A消费者[指南](guides/INITIATOR_MODE_CONSUMER.md)经180/181独立通过并发布，两项已收取；I-3B工具计数/timeout说明、角色hint与workspace注释及对应手册/MODULE_webui，经182开发、183既有断言补正、184独立A–F复核通过并发布，184/183/182均已收取；原182 partial与失败记录由后续证据闭合，原报告保持。独立页面7项+等待合同4项通过，用户于2026-10-07确认本片角色说明hint验收通过；I-3C桥接/集成规格经185/186独立复核通过，2026-10-08已按已审草稿发布，两项已收取，I-3文档同步闭合；175-O1测试维护、I-4真实主动链路与运行器/模型角色绑定继续后续。用户优先Kimi Code＋K2.8执行适配，本次DeepSeek开发、Codex复核；187入口经188/189补正与Codex独立82项测试（0跳过）及六项启动边界验证通过，189/188/187已收取。[Kimi K2.8执行入口](guides/KIMI_K28_EXECUTOR.md)已落地，原生bridge复用、模型alias/工具档/实际execution固定、本人/项目只读核验与Key脱敏通过；新成员已注册，独立仓库外Key与本地dev/execution身份档已准备；原agent:codex同步名册HTTP403后，2026-10-09人类已执行保留原三角色的同步包；MCP确认K2.8已入册dev/execution且kimi-code实例上报idle。离线检查/dry-run既有验证通过，最小接单/回传#195已由Codex独立核验并收取（约17秒领取、26秒完成），实际后端模型版本/开发能力与宿主主动等待T/W仍未验收；本轮开发/复核分工保持。I-3B新MCP说明的运行进程重载未核，不外推真实主动适配。当前状态见 [PROGRESS](PROGRESS.md)；以下日期较早的说明为阶段记录，与当前冲突时以本节为准。

此前B1–B4阶段记录：运行器/模型角色绑定设计#190–#192已复核发布[通用合同](spec/ROLE_MODEL_BINDING_DESIGN.md)与[实施计划](spec/ROLE_MODEL_BINDING_IMPLEMENTATION_PLAN.md)。B1a #193/#194两表/登记绑定API经独立124项通过收取；B1b #196任务不可变快照经独立177项及并发/回滚/原文探针通过收取，用户重启后授权[核心代验收](guides/TASK_BINDING_SNAPSHOT_ACCEPTANCE.md)与#199合法回传通过；实服绑定写入/变更未做。B3 #200角色名单只读binding/binding_state经独立106项与13探针、新进程真实匿名管道验证通过并收取，九工具/参数保持，用户重启后当前MCP描述与4角色绑定字段已只读核验加载（null/unconfigured），见[终端指南](guides/TERMINAL_MCP.md)。B4 #201/#202独立165项Node/12契约及原7反例通过收取，实服静态字节已核，[页面验收](guides/ROLE_BINDING_PAGE_ACCEPTANCE.md)待用户；实际证据B2、进程管理与八方向真实能力后置。按用户要求先完成当前角色绑定功能及验收，再进入下一功能；K2.8最小回传通过不代表实际模型版本或开发能力已验。

2026-10-10：用户确认适配收尾自动核验并登记/绑定，页面读取结果；#203–#205最终设计已复核收取，正式[收尾合同](spec/ADAPTER_BINDING_CLOSEOUT_DESIGN.md)与[C1–C4计划](spec/ADAPTER_BINDING_CLOSEOUT_IMPLEMENTATION_PLAN.md)已发布。#206 C1离线事实模块已通过；#207经#208/#209返修的C2受信plan/apply/verify工具独立153项模块测试与25边界探针通过，209→208→207已收取，明确写失败与POST专属409重分类边界闭合。C3 #210经#211修正来源/argv、显式目标/scope、申请包与事实结论四组问题，共享显式closeout入口及真实只读申请包独立167项测试/12探针通过，211→210已收取；本机K28两写包经用户明确同意后已由human:bobo受权应用，真实POST201/PUT200、角色读回bound、只读verify=verified，当前Codex MCP读回一致。临时校验器在联网前阻断首次PUT后，仅恢复剩余绑定，生产源码不变、原failed/回执保持。用户已核对C3 K28“已绑定”与固定alias；C4 #212状态化只读页面指引经Codex实际代码复核、默认隔离Node171项/四Python契约12项与独立边界检查通过并收取，资源版本20261010-adapter-closeout-c4，用户随后按[页面验收说明](guides/ROLE_BINDING_PAGE_ACCEPTANCE.md)回复“可以了”，C4页面整体人工验收通过、当前C1–C4角色绑定功能收尾闭合；bound只表示配置关联，不宣称后端模型版本/开发能力或主动等待已验；此阶段曾建议I-4真实主动链路；用户随后提出角色创建/接入与生命周期新方向，当前顺序见本节顶部，本次不开启新切片。使用与具体申请见[K28指南§11](guides/KIMI_K28_EXECUTOR.md)。

## 历史开发安排（2026-09-19，固定主控阶段）

用户最新确认优先：C1b改为角色页唯一指定项目主控、职责长期保存直到人工解除或更换，不采用会话租约/续租，保留现有任务权限。C1b-S1后端与MCP读取已由#110/#111开发/独立复核通过（716项全量测试），S2页面已完成开发与复核补测，待用户页面验收；旧会话合同仅历史归档。自动转审与多角色创建入口后续，见PROJECT_INTEGRATION最新节。

桌面Web容器与服务生命周期、工作区角色会话隔离、多终端主控能力验证、主被动按钮及任务命名的统一排期见 [DEVELOPMENT_ROADMAP.md](spec/DEVELOPMENT_ROADMAP.md)。保留原生Agent运行器，不将TALK重建为模型执行框架；N1 统一任务标题已完成开发与独立复核，页面待人工验收；L1-1入口准备已完成；Kimi Code 0.38.0在受信隔离目录完成一次真实委派、Codex独立验收和同会话收取（含人工唤回），DSH入口模板与预检经#70–#73开发复核完成，ACP薄驱动经#74–#79开发复核完成、零模型原生恢复及48项回归通过，真实模型单任务委派与同会话收取经#80–#84实测通过（人工验收/唤回），WorkBuddy桌面两模型经#90/#91完成用户操作下的单任务受控闭环（用户级MCP，多工作区/无人值守未验收）。项目级开发要求REQ-1后端/工具经#92开发、#93独立复核完成并收取（638项分批回归通过）：仅保存最新文本，MCP读取并将快照写入新任务；角色页编辑区REQ-2经#94–#97开发、返工与独立复审通过（Node78、Python49+95），用户按选定范围验收通过（跳过项见验收指南）；职责分工改为项目要求统一维护，仓库规范仍有效。ROLE-1角色说明统一与参与任务耗时经#98/#99完成独立复核，用户已于2026-09-18确认页面验收通过；MCP新字段及#99真实派发正文快照已在线核实。C1a主控模式意向/版本与只读状态经#100–#103完成开发、返工和独立复验，保存active不代表生效，C1b身份/生效合同与C2按钮未实现。后续按路线逐片推进。

## 2026-10-06 主被动调度（C2-A1/C2-B实现复核通过，页面/主动链路分开验收）

C2-0方案经#152/#153/#154/#155开发与独立复核，Codex回填定向结论后落盘[CONTROLLER_MODE_DESIGN.md](spec/CONTROLLER_MODE_DESIGN.md)。C2-A1由#156开发、#157独立审查、#158修正F-1、#159定向复核通过并已收取：显式opt-in受控wait、Key反查caller_identity、门禁/预算/模式变化退出与错误统计已实现；旧通用wait默认/最大600秒和九工具数量保持。运行中MCP须重连加载新实现，尚无真实主动链路验收；不引入ACK/租约或假造effective_mode。C2-B由#160开发/#161独立审查/#162修正/#163定向复核，模式面板与单分隔线实现通过并已收取，页面待人工验收；409重读失败有只读重试入口且暂禁旧版本保存。人工反馈修正#164经#165独立导航接线/生命周期与回归复核通过并收取：未保存模式选择离页丢弃、返回已确认saved，已保存状态行去版本而内部CAS保留，静态资源20261006-controller-mode-c2b-ux；用户已确认本轮两条反馈页面验收通过，功能9272020已推送。Codex当前连接新工具加载检查已通过，真实主动链路仍未验收。后续C2-C约定级消费者/指南与主动链路验收，取消/执行互斥及原生会话自动唤醒均未实现。所有终端适配必须遵守[工具超时与等待预算要求](guides/TERMINAL_MCP.md#终端适配必查工具超时与等待预算2026-10-06)：各自核验客户端时限，显式等待预算留返回余量；DeepSeek桌面65秒下选50秒，Codex保持用户现用300秒，不把通用默认600秒套用到所有终端。

## 已确认后续方向（2026-10-06，实施现状见2026-10-07节）

用户要求后续按任务发起者 `created_by` 确定协调责任：项目统一主被动只作用于发起侧，执行/复核角色正常完成已派任务；取消固定项目主控标签/选择入口，并同步工具核验与消费者合同。各Agent应使用自身API Key，当前Codex入口仍实测human:bobo，凭据切换及历史任务衔接尚未处理。另从各Agent运行端核验/上报模型名称，页面以模型名替代裸成员ID展示，内部身份ID保留；不能取到时如实降级。成员默认/自定义名称及重名规则留到完整角色页面设计。具体边界、兼容与顺序见[后续开发安排](spec/DEVELOPMENT_ROADMAP.md#2026-10-06-新增后续计划任务发起者调度与模型名称展示)。

上述方向不扩大已收尾#164/#165范围。设计#166–#171已通过并发布，I-1门禁与I-2页面退役已独立通过，当前状态见顶部；自身身份/消费者/真实链路与模型名称仍待后续，不直接继续固定主控时代的旧C2-C任务包。

## 最新产品约定（2026-09-08，待实现）

已验收的任务与界面，以及 TH-7a 普通终端入口均已进入 main。下一阶段群聊统一作为头脑风暴：支持人工或原 code 终端 Agent 主持，按会议周期隔离上下文，总结返回发起会议的原终端。完整约定见 [BRAINSTORM_NEXT.md](spec/BRAINSTORM_NEXT.md)；这项最新方向尚未实现，不应把现有 brainstorm 内部机制或八个任务工具误认为完整会议功能。

## 项目定位

TALK 是部署在**家庭局域网**的轻量级 AI 智能体聊天中转平台。核心能力：
- 多个 AI Agent 之间互相发送消息和文件包
- 人类用户通过 Web UI 用 `@` 向任意 Agent 下达任务
- 所有通信统一中转，消息持久化，便于回溯
- 任一接入 TALK MCP / client 的终端可把其他模型 Agent 当作跨模型子 Agent 委派任务，并从 TALK 获取澄清与结果

> 产品级 Hall 分为 **Task Halls**（一任务一 Hall、请求者↔执行者 1 对 1，当前优先）与 **Discussion Halls**（多角色讨论 / 评审，后续继续）。完整定位与混合终端模型见 [`spec/POSITIONING.md`](spec/POSITIONING.md)，Task Hall 合同见 [`spec/MODULE_tasks.md`](spec/MODULE_tasks.md)（2026-07-15 收敛）。

## 系统架构

```
 ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
 │  Browser UI │        │  Agent AI1  │        │  Agent AI2  │
 │  (human)    │        │  (poller)   │        │ (websocket) │
 └──────┬──────┘        └──────┬──────┘        └──────┬──────┘
        │ WebSocket           │ HTTP polling         │ WebSocket
        └─────────────────────┼──────────────────────┘
                              ▼
                  ┌────────────────────────┐
                  │   FastAPI Server       │
                  │   REST API + WS Hub    │
                  │   X-API-Key 鉴权       │
                  └────────────┬───────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  SQLite  +  Local FS    │
                  │  talk.db   storage/     │
                  └─────────────────────────┘
```

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11 + FastAPI + uvicorn |
| ORM | SQLModel (Pydantic + SQLAlchemy) |
| 数据库 | SQLite（WAL 模式），文件 `talk.db` |
| 文件存储 | 本地磁盘 `storage/files/` |
| 前端 | 单页 HTML + Vanilla JS + Tailwind CSS (CDN) |
| 测试 | Python `unittest`（M3-4 已落首轮后端自动化测试） |
| 鉴权 | `X-API-Key` header（WebSocket 用 `?token=`） |
| 配置 | `config.toml`（tomllib 读取） |

## 运维基线

- 健康检查：提供 `GET /healthz`，返回 `status / db / storage / uptime_sec / online_members`；任一子检查异常时返回 `503`
- 日志：使用标准库 `logging` 输出 JSON 结构化日志，默认写入 `logs/talk.log` 并按天切割；覆盖 HTTP 请求、WebSocket 连接/广播事件与异常堆栈
- 备份：提供 `scripts/backup_db.py`，基于 `sqlite3.Connection.backup()` 做 WAL 模式下的在线热备；默认写入 `backups/backup_YYYY-MM-DD.db` 并保留最近 7 份
- 配置：`config.toml` 新增 `[logging]` 与 `[backup]` 段，可分别调整日志路径、日志级别、备份目录和保留份数

## 数据模型（核心表）

```sql
CREATE TABLE members (
  id           TEXT PRIMARY KEY,       -- 'human:bobo' / 'agent:AI1'
  kind         TEXT NOT NULL,          -- 'human' | 'agent'
  display_name TEXT NOT NULL,
  api_key      TEXT UNIQUE NOT NULL,
  poll_hint    INTEGER,
  created_at   DATETIME NOT NULL
);

CREATE TABLE messages (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id     TEXT REFERENCES groups(id), -- NULL = legacy/global timeline；非空 = Group Hall 时间线
  from_id      TEXT NOT NULL REFERENCES members(id),
  to_ids       TEXT,                   -- JSON 数组；NULL = 广播；Group 内表示 mention/注意力路由
  type         TEXT NOT NULL,          -- 'text' | 'file'
  content      TEXT,                   -- type=text: 消息正文；type=file: 兼容字段（通常与 filename 相同）
  file_id      TEXT REFERENCES files(id), -- type=file 时必填
  caption      TEXT,                   -- type=file: 可选附言
  filename     TEXT,                   -- type=file: 冻结的文件名快照
  size_bytes   INTEGER,                -- type=file: 冻结的文件大小快照
  mime         TEXT,                   -- type=file: 冻结的 MIME 快照
  revoked_at   DATETIME,               -- 撤回时间；NULL = 未撤回
  revoked_by   TEXT REFERENCES members(id), -- 撤回者；当前仅允许发送者本人
  created_at   DATETIME NOT NULL
);

CREATE TABLE groups (
  id           TEXT PRIMARY KEY,       -- 'group:lab' 或自动生成 group:<uuid>
  name         TEXT NOT NULL,
  description  TEXT,
  created_by   TEXT NOT NULL REFERENCES members(id),
  created_at   DATETIME NOT NULL,
  updated_at   DATETIME NOT NULL
);

CREATE TABLE group_members (
  group_id     TEXT NOT NULL REFERENCES groups(id),
  member_id    TEXT NOT NULL REFERENCES members(id),
  role         TEXT NOT NULL,          -- owner | moderator | member
  created_at   DATETIME NOT NULL,
  PRIMARY KEY (group_id, member_id)
);

CREATE TABLE discussion_sessions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id        TEXT NOT NULL REFERENCES groups(id),
  created_by      TEXT NOT NULL REFERENCES members(id),
  topic           TEXT NOT NULL,
  participant_ids TEXT NOT NULL,       -- JSON 数组
  root_message_id INTEGER REFERENCES messages(id), -- 可选：本轮范围起点消息
  requester_id    TEXT REFERENCES members(id), -- 可选：当前范围提要求者
  assignee_id     TEXT REFERENCES members(id), -- 可选：当前范围被要求回复/执行者
  scope_text      TEXT,                -- 可选：当前请求范围文本
  status          TEXT NOT NULL,       -- active | resolved | escalated | canceled
  max_rounds      INTEGER NOT NULL,
  created_at      DATETIME NOT NULL,
  updated_at      DATETIME NOT NULL
);

CREATE TABLE discussion_turns (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id       INTEGER NOT NULL REFERENCES discussion_sessions(id),
  turn_index       INTEGER NOT NULL,   -- session 内顺序
  message_id       INTEGER NOT NULL REFERENCES messages(id),
  speaker_id       TEXT NOT NULL REFERENCES members(id),
  target_member_id TEXT REFERENCES members(id),
  turn_kind        TEXT NOT NULL,      -- demand | reply
  stance           TEXT NOT NULL,      -- question | answer | agree | optimize | disagree | escalate
  round_index      INTEGER NOT NULL,
  created_at       DATETIME NOT NULL
);

CREATE TABLE files (
  id           TEXT PRIMARY KEY,       -- uuid4
  filename     TEXT NOT NULL,
  mime         TEXT,
  size_bytes   INTEGER NOT NULL,
  sha256       TEXT NOT NULL,
  uploader_id  TEXT NOT NULL REFERENCES members(id),
  path         TEXT NOT NULL,
  created_at   DATETIME NOT NULL
);

CREATE TABLE agent_instances (
  id              TEXT PRIMARY KEY,       -- bridge 进程实例 id
  member_id       TEXT NOT NULL REFERENCES members(id), -- 所属 agent:* 成员
  runtime         TEXT NOT NULL,          -- codex | pi | dsh | ...
  status          TEXT NOT NULL,          -- starting | online | idle | busy | stopping | offline | error
  host            TEXT,
  pid             INTEGER,
  current_task_id TEXT,
  last_error      TEXT,
  created_at      DATETIME NOT NULL,
  updated_at      DATETIME NOT NULL,
  last_seen_at    DATETIME NOT NULL
);

CREATE TABLE agent_tasks (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  schedule_id       INTEGER REFERENCES agent_task_schedules(id), -- 可选来源 schedule
  project_id        TEXT REFERENCES projects(project_id), -- 可选项目归属；旧客户端兼容为空
  hall_group_id     TEXT UNIQUE REFERENCES groups(id), -- 自动生成的一任务一 Hall
  target_member_id  TEXT NOT NULL REFERENCES members(id), -- 接收任务的 agent:* 成员
  created_by        TEXT NOT NULL REFERENCES members(id), -- 任务创建者
  content           TEXT NOT NULL,          -- 任务正文
  title             TEXT,                   -- 可选短标题
  status            TEXT NOT NULL,          -- queued | running | succeeded | failed | canceled
  workflow_status   TEXT NOT NULL,          -- assigned | clarification_requested | accepted | in_progress | submitted | completed | failed | canceled
  claimed_by        TEXT REFERENCES members(id),
  instance_id       TEXT REFERENCES agent_instances(id),
  result_message_id INTEGER REFERENCES messages(id),
  last_error        TEXT,
  created_at        DATETIME NOT NULL,
  updated_at        DATETIME NOT NULL,
  claimed_at        DATETIME,
  finished_at       DATETIME,
  result_collected_at DATETIME,
  target_binding_snapshot JSON, -- 新任务13键配置；旧任务NULL、不回填
  target_binding_state TEXT     -- 新任务绑定状态；旧任务NULL=未记录
);

CREATE TABLE agent_task_schedules (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  target_member_id  TEXT NOT NULL REFERENCES members(id),
  created_by        TEXT NOT NULL REFERENCES members(id),
  content           TEXT NOT NULL,
  title             TEXT,
  schedule_type     TEXT NOT NULL,          -- once | interval
  status            TEXT NOT NULL,          -- active | paused | completed | canceled
  next_run_at       DATETIME NOT NULL,
  interval_seconds  INTEGER,
  last_run_at       DATETIME,
  last_task_id      INTEGER REFERENCES agent_tasks(id),
  created_at        DATETIME NOT NULL,
  updated_at        DATETIME NOT NULL
);
```

## 鉴权机制

- 所有 `/api/*` 请求必须携带 `X-API-Key: <token>` header
- WebSocket `/ws` 用 query `?token=<api_key>`
- 服务端按 key 反查 `members` 表确定身份
- `POST /api/members`（注册）例外，不要求鉴权
- `GET /api/members/me` 用于前端按 API Key 自动识别当前成员

## 当前前端交互约定

> 当前 Web UI 已实现任务 / 群聊 / 角色工作台（主任务归组、成果与流转优先、项目角色只读列表和交办入口）、独立 Task Hall、任务树控制、质量门禁摘要与里程碑人工验收入口；Discussion Halls、Members / Activity 独立页面仍按后续切片推进，见 `spec/MODULE_tasks.md`。

- Web UI 登录后会显示“全局消息流”和可进入的 Group Hall 切换条；全局流继续读取不带 `group_id` 的旧消息，Group Hall 读取 `GET /api/messages?group_id=<id>`
- Web UI 可创建 Group 并选择初始成员；创建后自动进入该 Group 的 Hall
- 在 Group Hall 中发送文本或文件消息时，前端会自动带上当前 `group_id`
- 在 Group Hall 中，成员在线条和 `@` 补全会收敛到当前 Group 成员；`@member_id` 只表示提醒/注意力路由，不改变同组可见性
- 文本消息与文件附言都使用“消息开头连续 `@member_id` 块”决定接收者
- 实际路由以服务端解析结果为准；前端只负责 `@` 自动补全与输入提示
- 无开头 mention 时按广播处理
- 中途出现的 `@` 仅作为正文提及展示，不承担路由语义
- 成员自动补全与 mention 校验均来自 `GET /api/members` 返回的数据，而不是前端写死角色前缀
- 文件消息卡片始终依赖消息快照渲染；若文件实体已过期删除，历史卡片仍保留，但下载会失败并提示“已过期”
- 发送者可在 `revoke_window_sec`（默认 120 秒）内撤回自己的消息；撤回后消息流改为灰色占位“XX 撤回了一条消息”，文件实体本身保留

## 用户手册维护约定

- TALK 的最终用户操作手册统一维护在 `docs/guides/USER_MANUAL.md`，面向系统已经部署完成后的普通使用者，只说明当前版本中真正可见、可操作的产品行为。
- 安装、启动、升级、备份和服务故障处理继续放在 `docs/guides/QUICKSTART_USER.md` 与 `docs/guides/DEPLOY.md`；Python 环境、SDK、bridge、测试命令和本地开发启动方式继续放在 `docs/guides/QUICKSTART_AGENT.md`、模块文档或开发者文档，不混入最终用户操作手册。
- 每个可能影响用户操作、页面文案、权限、状态含义、失败提示或恢复方式的开发切片，收尾时必须检查用户手册影响；已有用户入口时在同一切片更新手册，只有后端合同而尚无最终用户入口时不得写成“已经可用”。
- 未来能力继续先记录在对应模块合同和进度文档中，待页面或正式用户入口落地并完成真实验证后，再转写为非技术性的操作步骤。
- 每个可独立体验的里程碑在人工验收前，应按用户手册从头操作一遍；手册中的步骤、按钮名称、预期结果和当前版本边界都属于验收范围。
- 这套约定只属于 TALK 项目，不修改用户级全局 `project-framework` skill，避免影响其它项目。

## 项目目录结构

```
TALK/
├── CLAUDE.md              # 项目入口（自动加载）
├── config.toml            # 服务配置
├── requirements.txt       # Python 依赖
├── run.sh                 # 一键启动
├── server/
│   ├── main.py            # FastAPI 入口
│   ├── logging_config.py  # 结构化日志配置
│   ├── models.py          # SQLModel 数据模型 + API schemas
│   ├── db.py              # SQLite 初始化 + config 加载
│   ├── auth.py            # API Key 鉴权依赖
│   ├── ws_hub.py          # WebSocket 连接管理
│   └── routes/
│       ├── members.py     # 成员注册/列表
│       ├── groups.py      # Group / Hall 房间与成员关系
│       ├── instances.py   # Agent 运行实例状态
│       ├── tasks.py       # Agent 任务队列与调度基础
│       ├── messages.py    # 消息收发
│       └── files.py       # 文件上传下载（M2）
├── web/
│   ├── index.html         # 单页 UI
│   ├── app.js             # 前端逻辑
│   └── style.css          # 自定义样式
├── examples/
│   └── agent_poller.py    # 示例 Agent 轮询脚本
├── bridges/
│   ├── cli_bridge.py      # 通用 CLI bridge（local-lab Agent CLI 接入骨架）
│   ├── codex_bridge.py    # Codex CLI bridge 兼容入口
│   ├── kimi_bridge.py     # 官方 Kimi Code CLI bridge
│   └── pi_bridge.py       # pi CLI bridge 兼容入口
├── scripts/
│   └── backup_db.py       # SQLite 在线热备脚本
├── AGENTS.md              # Agent 角色与协作规则权威入口
├── tests/
│   ├── test_support.py    # 后端测试基类与隔离环境
│   └── test_*.py          # M3-4 首轮自动化测试
├── logs/                  # 结构化日志输出目录
├── backups/               # SQLite 备份输出目录
├── storage/files/         # 上传文件实体
├── docs/
│   ├── PROJECT_BRIEF.md   # 本文件
│   ├── PROGRESS.md        # 当前进度快照
│   ├── PROGRESS_HISTORY.md # 已完成切片历史记录
│   ├── spec/
│   │   ├── PRODUCT.md     # PM 完整产品文档
│   │   ├── SDK.md         # SDK 使用文档
│   │   ├── LOCAL_LAB_DESIGN.md  # 本地多 Agent 实验室设计
│   │   ├── INTERACTION_FRAMEWORK.md # Agent 交互框架
│   │   └── MODULE_*.md    # 模块 spec
│   └── guides/
│       ├── QUICKSTART.md      # 快速启动入口索引
│       ├── QUICKSTART_USER.md # 家庭用户快速启动
│       ├── QUICKSTART_AGENT.md # Agent 开发者快速启动
│       ├── USER_MANUAL.md     # 系统部署完成后的最终用户操作手册
│       └── DEPLOY.md          # 部署指南
└── talk.db                # SQLite 数据库（运行时生成）
```

## 模块索引

| 模块文档 | 负责范围 | 涉及文件 | 状态 |
|----------|----------|----------|------|
| [MODULE_members_auth.md](spec/MODULE_members_auth.md) | 成员注册 + API Key 鉴权 | `server/auth.py`, `server/routes/members.py` | M1 已实现，已补 `GET /api/members/me`、Agent 自注册与首轮自动化测试 |
| [MODULE_messages.md](spec/MODULE_messages.md) | 消息发送与拉取 | `server/routes/messages.py` | M2 已支持服务端 mention 路由解析、文件附言、历史分页、搜索、消息撤回与自动化测试 |
| [MODULE_groups.md](spec/MODULE_groups.md) | Group / Hall 房间与共享时间线作用域 | `server/routes/groups.py`, `server/routes/messages.py`, `server/models.py`, `web/`, `TALK/client/` | `GROUP-1 / HALL-1` 后端第一版已落地；Web UI 已接入 Group/Hall 切换与创建入口；SDK helper 已接入 |
| [MODULE_discussions.md](spec/MODULE_discussions.md) | 可记录多 Agent 讨论协议 | `server/routes/discussions.py`, `server/models.py`, `TALK/client/`, `bridges/` | `DISCUSSION-SCOPE-1` 已落地：session/turn 记录、请求者局部范围锚点、SDK helper、bridge TALK 动作协议与 pi 可选施工档 |
| [MODULE_websocket.md](spec/MODULE_websocket.md) | WebSocket / SSE 实时事件连接管理与推送 | `server/ws_hub.py`, `server/main.py`(WS/SSE端点) | WS 已实现；SSE 只读事件流第一版已落地 |
| [MODULE_files.md](spec/MODULE_files.md) | 文件上传下载 | `server/routes/files.py` | M2 已实现，已支持按保留期清理与首轮自动化测试 |
| [MODULE_webui.md](spec/MODULE_webui.md) | 浏览器端 Web UI | `web/index.html`, `web/app.js`, `web/style.css`, `web/workspace.js`, `web/workspace.css` | 已支持任务 / 群聊 / 角色导航、成果与分工流转，及 Group Hall 切换、Group 创建、Hall 发送与作用域化历史/轮询 |
| [MODULE_agent_example.md](spec/MODULE_agent_example.md) | 示例 Agent 轮询脚本 | `examples/agent_poller.py` | M2 已实现，支持文件收发、附言回执与 Agent 自注册 |
| [MODULE_bridges.md](spec/MODULE_bridges.md) | 外部 Agent bridge 接入 | `bridges/` | 通用 CLI bridge 第一版已落地，Codex / Kimi 保持专用入口，pi bridge 保留兼容 |
| [MODULE_instances.md](spec/MODULE_instances.md) | Agent 运行实例状态 | `server/routes/instances.py`, `server/models.py`, `TALK/client/` | 实例状态 API 第一版已落地，并已与任务领取/完成联动 |
| [MODULE_tasks.md](spec/MODULE_tasks.md) | Agent 任务队列、Task Hall 与跨终端委派 | `server/routes/tasks.py`, `server/models.py`, `TALK/client/`, `web/`, `bridges/` | TH-6a1 至 TH-6d 已落地任务树治理、有限授权 / 中断、澄清、runner 预检、Review / Test / 返工门禁、Blackboard 控制与里程碑人工验收；TH-6d 已于 2026-09-06 通过人工验收并完成根任务收尾，TH-7a 已新增普通终端 stdio MCP 入口与只读连接检查 |

补充说明：
- 文件消息现已内嵌 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段
- 文件实体默认按 `config.toml` 的 `file_retention_days` 保留；过期后会在服务启动时清理磁盘文件和 `files` 记录，但历史消息快照仍保留

## 公共依赖说明

所有后端模块共享以下基础设施（不属于任何单一模块）：
- `server/models.py` — ORM 模型 + API schemas（所有后端模块都会引用）
- `server/db.py` — 数据库引擎 + 配置加载 + `get_session` 依赖
- `config.toml` — 服务配置

修改这些公共文件时需评估对所有模块的影响。

## 2026-08-27 Kimi Runtime Addendum

- 项目管理者确认：固定 Kimi Reviewer 从 `agent:pi` + pi runtime 迁移为 `agent:kimi` + 官方 Kimi Code CLI；旧成员只保留历史消息与任务归属，不再启动。
- `bridges/kimi_bridge.py` 复用通用 bridge 的 TALK 消息、任务队列、租约与动作协议，使用 Kimi `stream-json` 的最后一条 Assistant 消息作为可见输出。
- Kimi 讨论与任务预检固定无工具；任务默认 Review 档只开放 `Read / Grep / Glob / Bash`，显式 `tools` 档才开放 `Edit / Write`，且三个运行档都禁止自行派生 subagent。Kimi prompt mode 不追加与 `-p` 冲突的 `--auto`，能力边界由上述工具白名单控制。
- Kimi Code CLI 会保留官方 session 记录；当前把它视为本地审计事实，不自动删除或续接。TH-6d 已使用新的 `agent:kimi` 拓扑跑通完整任务树 `#15/#16/#17/#18`，并于 2026-09-06 通过人工验收完成收尾。

## 2026-05-15 Agent Workflow Addendum

以下固定分级称呼为历史记录；2026-10-10已改为按任务分工，当前规则以 `AGENTS.md` 为准，代码字段兼容迁移待实施。

- `AGENTS.md` 是本项目 Agent 角色与协作边界的权威来源；每次项目开始必须先读取并确认当前角色。
- 当前角色：Codex 为决策 Agent；本地 bridge 使用 Kimi（官方 Kimi Code CLI）与 DeepSeek（DeepSeek Harness）作为执行 Agent，不启动 Claude Code。项目管理者可通过修改 `AGENTS.md` 调整后续 Agent 行为。
- 决策 Agent 在方向明确且无重大不确定项时，可自主连续开发多个切片；执行 Agent 每次只开发一个切片，完成后必须等待确认。
- 任意角色每完成一个可能影响功能的开发切片，都必须执行“汇总进度”，并记录验证、变更文件、待确认问题和下一步。
- `docs/PROGRESS.md` 只保存当前快照，保持长度可控；已完成切片完整记录归入 `docs/PROGRESS_HISTORY.md`。
- 上下文达到 80%-90% 时，必须先汇总进度、落盘、验证与提交，再清除上下文或输出 `继续项目` 恢复指令。
- 可独立体验的里程碑版本需要暂停继续开发，提交可验收版本，并用中文提供 GitHub/验收说明。

## 2026-05-13 Local Lab Addendum

- 新增 `docs/spec/LOCAL_LAB_DESIGN.md`，用于收敛本地多 Agent 实验室阶段的设计边界。
- local-lab 当前固定为 3 个 Agent：Codex 走专用 CLI bridge；Kimi 走官方 Kimi Code CLI bridge；DeepSeek 各类模型走 DeepSeek Harness `dsh --profile headless` + 通用 CLI bridge。Claude Code 暂不纳入本地拓扑，旧 `agent:pi` 只保留历史事实。
- `bridges/cli_bridge.py` 是通用 CLI 接入骨架：通过 TALK SDK 自注册、监听发给自己的文本任务、轮询任务队列、调用可配置本地 CLI 命令，并把结果回复到 TALK；`bridges/codex_bridge.py` 与 `bridges/kimi_bridge.py` 保留专用入口，`bridges/pi_bridge.py` 保留多 provider 兼容入口，DeepSeek Harness 通过通用 bridge 的 `argv` prompt transport 接入。
- `agent_instances` 表与 `/api/instances` 第一版已落地；Codex bridge 已接入 `idle / busy / error / offline` 状态上报。
- `agent_tasks` 表与 `/api/tasks` 第一版已落地：支持创建任务、按可见性列出任务、Agent 领取任务、完成/失败/取消任务，并联动 `agent_instances.current_task_id` 与实例状态；当前不由 TALK 自动启动 bridge 进程。
- `agent_task_schedules` 表与 `/api/tasks/schedules` 第一版已落地：支持一次性 / 周期性 schedule 记录、状态暂停/取消、显式 `run-due` 物化为 queued task；当前不内置后台调度循环。

## 2026-05-14 Group / Hall Addendum

- `groups` 与 `group_members` 表已落地，用于表达讨论房间与成员关系。
- `messages.group_id` 已落地：`NULL` 表示 legacy/global 消息流；非空表示消息属于某个 Group 的 Hall 时间线。
- `/api/groups` 第一版支持创建 Group、列出可见 Group、读取单个 Group、添加/更新成员角色、移除成员。
- Group Hall 语义：Group 内消息对所有 Group 成员可见；`to_ids` 在 Group 内只表示 mention/注意力路由，不限制同组成员读取 Hall。
- `GET /api/messages?group_id=<id>` 读取 Group Hall；不传 `group_id` 时继续读取旧全局消息流，避免旧 Web UI 被新房间消息污染。
- WebSocket 推送已支持显式目标成员列表；Group 消息实时推送给 Group 成员，非成员不会收到。
- Web UI 已接入 Group/Hall 切换条、新建 Group 面板、Hall 发送、Hall 历史/轮询作用域、Group 成员范围内 `@` 补全、在线成员显示和 Hall 内成员管理面板。
- SDK 已接入 Group helper：支持创建/列表/详情/成员增删改，并支持 `send_text` / `send_file` / `reply` / `fetch_history` 携带 `group_id`。
- SSE 只读事件流第一版已接入 `GET /api/events?token=<api_key>`：支持 `message / presence / revoke / ping` 事件，payload 复用现有 WS 事件语义。
- 当前 Web UI 尚未接入 SSE stream，多 Agent 讨论协议也尚未落地。

## 2026-04-23 Data Model Addendum

- `messages.reply_to INTEGER NULL REFERENCES messages(id)` was added for first-level reply/reference support.
- `reply_to` is a UI/reference relationship only; multi-agent demand/reply state and round control live in `discussion_turns.turn_kind` and `round_index`.
- Reply rendering is intentionally flat: only the direct parent summary is returned, with no recursive tree expansion.
- Message REST and WebSocket payloads may now include:
  - `reply_to.id`
  - `reply_to.from_id`
  - `reply_to.preview`
  - `reply_to.type`
  - `reply_to.revoked`
- `reply_to.preview` is precomputed server-side to avoid frontend N+1 fetches.
- Public `GET /api/config` now exposes frontend-safe runtime constants such as `revoke_window_sec`, `max_upload_bytes`, `ws_ping_interval`, `ws_ping_timeout`, and `file_retention_days`.

## 2026-04-23 Visibility Addendum

- `GET /api/messages` now enforces message visibility on the server side instead of trusting the caller's `to` filter.
- Clients can only retrieve messages that match the same delivery rules used by WebSocket broadcast:
  - sender can always see their own messages
  - everyone can see broadcast messages
  - recipients can see directed or group messages that include them
- `to=<member_id>` is now only a secondary filter on top of that visible set.
- `to=<other_member>` produces a safe pair view: broadcast, direct messages between the two members, and shared group messages where both are recipients.
- Search (`q`) is also restricted to the caller's visible set, so keyword queries cannot leak hidden messages.

## 2026-04-24 Onboarding Docs Addendum

- `docs/guides/QUICKSTART.md` 现已降为入口索引页，分别指向家庭用户与 Agent 开发者两份独立快速启动文档
- 新增 `docs/guides/QUICKSTART_USER.md`：面向家庭新手，只走 Docker Desktop + 浏览器路径
- 新增 `docs/guides/QUICKSTART_AGENT.md`：面向 Agent 开发者，只走 Python bare metal + SDK 路径
- `docs/spec/SDK.md` 的异步示例现已补齐 `asyncio.run(main())` 包装，可直接复制到 `.py` 文件运行
- 首次管理员引导页的 `api_key` 输入已支持浏览器端安全随机生成、显隐切换与一键复制，新手无需手动编造登录密钥


## 2026-10-07 I-1/I-2实施状态

发起者受控等待工具经DeepSeek #172开发、Kimi #173独立复核通过并收取；源码按具体任务created_by与项目核验协调资格，固定主控指定不再是受控执行依据，普通等待/服务端权限保持兼容。2026-10-07当前Codex MCP连接目录/运行时加载核验已通过，I-2页面经174/175独立复核通过并收取，用户本轮页面验收通过；当前聊天自身身份与178/179被动任务闭环已独立通过并收取，I-3A消费者指南经180/181独立通过已发布并收取，活跃文案/剩余规格及真实主动链路仍待后续，保存active仍只是意向。当前合同与实施顺序见CONTROLLER_MODE_DESIGN、INITIATOR_MODE_IMPLEMENTATION_PLAN及PROGRESS；旧已实现记录作为历史保留。
