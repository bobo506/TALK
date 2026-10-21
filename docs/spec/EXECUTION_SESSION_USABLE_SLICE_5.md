# 会话机制第五片：完整可用纵向接线（292）

> 2026-10-22 01:06当前：292已独立实查/直接补正、正常加载并通过293→294真实同窗及295新窗恢复；60%/10次边界由安装版DSH+fake模型验证。当前DSH工程可用，待人工里程碑验收；旧MCP连接需重连，SDK/API已可用。详[292实查](EXECUTION_SESSION_USABLE_REVIEW_292.md)与[使用说明](../guides/EXECUTION_SESSION_USAGE.md)。以下旧阶段状态保留其日期语义。

2026-10-21 23:01（Asia/Shanghai）。用户明确要求同窗口、阈值换窗和十轮兜底均真正可用才算完成，未完成继续本功能。292已派DeepSeek首次实现，creator agent:codex、target agent:deepseek、project `prj_e8fe7066bbec`，Hall `group:task-221d84cd748544a89716bb183c51eb0d`，22:56:32创建queued/assigned。原始任务及创建回执在`.tmp/execution-session-usable-v1/coordination/`。

## 整体完成标准

1. 发起者按同功能/稳定工作线选择同一角色的原生会话，能提前换新；不是只让TALK任务使用相同标签。必须用不同TALK任务的真实native session ID证明续用。
2. 每次投递前检查身份、配置、通道与可靠原生占比；<60%续用，≥60%下一次真正新建不同session并恢复完整首轮，在途任务不被阈值强杀。
3. 仅单纯指标不可得、scope/window/完整计数和备用时钟可信时累计最多10次交办，第11次实际新窗；首轮计1，预检/工具/计划/未送达失败不计，重复ACK不重计，送达后失败不倒扣，读数恢复/再缺数不清零。可靠低占比可超过10次，非法/错身份/矛盾不兜底。
4. 首轮完整固定介绍，续轮仅增量和本次必要控制信息；新窗自动取回完整介绍。基础合同持久留存，协调方后续不用重复生成背景，bridge不补回固定内容或全量Hall历史。各任务账本、权限、Hall、交付与收取独立，可审计还原。
5. API、SDK及MCP有真实使用入口，实际送达/窗口状态可核；原生续接与查询、采集/规划/ACK/状态均被调用，不接受只有helper、方案或“下一片再接线”。使用说明与最终界面/工具保持一致。
6. 完成必要隔离回归、真实原生入口/会话验证与少量实际任务验收，明确区分可控阈值/缺数实验和真实模型证据；整体验收通过前持续标记未完成，不将本任务候选交付等同产品可用。

## 当前实现范围与架构约束

- 先真实接通当前既定DeepSeek/DSH链路，协议可扩展；其它运行器保持旧行为，能力未适配时明确反馈，不冒充已支持。原模型deepseek-flash/max、Key、HOME、绑定不变。
- 优先TALK侧受控一次性runner/临时overlay，显式create/resume，并保留每个TALK任务独立原生进程/MCP上下文。原默认headless无resume入口，不能只加无效参数；禁止把首任务残留的TALK_TASK_ID/Hall/工具权限带进下一任务。
- 候选原生prepare/query阶段不得调用模型；只有实际规划后正式投递。原生resume只读写本功能新建/可信登记的会话，不扫描接管旧生产session；历史由原生正常管理，不额外拼进新指令。
- 必要来源恢复仅限同一已核受管会话的配置/用量允许字段、原始seq/time和窗口证明，与当前registry/cut交叉核验；旧track默认严格性保持，不给缓存改时间或捏造来源。实际配置/权限未知不能只凭启动规格声明允许续用。
- 请求/基础合同建议使用可选execution_session元数据、稳定continuity_key、首轮base_context及后续base_task_id等受权限保护引用；最终API由候选实现明确。严格区分原始增量、固定项目要求、基础合同与审计快照，不按相同文本删正文。
- 实现真实窗口状态/锁/CAS/留档与原生送达ACK；query→规划→投递→计数归并在独占通道内，故障/未知送达标不可信，禁止自动模型重跑。service launch变化不接管旧PID或伪造归属/计数。
- 保原claim/lease、预检、review/test gate、权限及主动/被动模式；预检/repair每spawn隔离，不污染主会话。只有新增nullable字段/新表的正常迁移，不改旧历史数据。

## 冻结、白名单与分工

基线`21d308bc377a7e9dedcb959f34320e5e42dfccd9`。80份项目公开材料/57份原生公开文件共3,741,458字节逐SHA冻结。baseline/project、baseline/native、baseline/shims及coordination只读，执行者唯一可写deepseek/**，正式协调文档由Codex独占。

允许候选修改bridge/任务工具、现有会话内核及采集适配、server models/db/tasks、异步/同步SDK和必要宿主能力透传；允许新增受控native runner、channel、状态/传输及server任务元数据模块和对应测试。精确路径以coordination/request-content.txt冻结任务包为准；不跨界改web、其它产品或宿主统一启动。未经授权的额外文件需求先暂停说明。

页面development_requirements仍是旧交叉复核，快照原样保留；按最新AGENTS DeepSeek首次执行/自测/暂停，Codex首次独立实查、直接补正和自检、必要实机验证及集成，Kimi不派新任务。用户本次完整功能要求已明确292范围；同授权内必要修正不重复请求开发许可。

准备时复用旧恢复检查发现Kimi generation22→24已外部变化，未启停Kimi或回滚；固定当前基线，失败及差异保留于preparation-baseline-difference.json。配置/绑定/286全文仍保持；DeepSeek派前同实例ins_ffc603d6fc88/manager18856/bridge22812、gen28 running/idle。

## 必须跑通的验收

- 隔离测试Key/DB/HOME/端口，从真实MCP schema/dispatch或SDK→REST创建/引用→claim→候选bridge→原生runner协议→既有规划→ACK状态归并→任务结果读回，至少两条不同TALK任务；不只测纯helper。
- 同工作线59.9%真实协议输入续同native ID，60%下一次新ID；不同功能/force_new/合同或配置变化新ID；首轮完整、续轮无重复固定介绍、换新完整恢复。
- 缺指标的第1至10次真实送达同窗，第11次新窗；恢复指标不清零；可靠低占比超过10次仍续；非法/未来/身份/事件冲突不误兜底。
- 锁竞争、查询与投递间变更、未知送达、取消/超时、重复/冲突ACK、重启、repair、跨成员/错误base引用、越界/旧attempt及旧API兼容。按既有170/76/34及被改入口做针对性回归，不删除反例凑通过。
- 安装版原生库允许在隔离HOME配fake LLM/provider/假MCP作真正加载及create/resume/projection验证，清除敏感环境、不联网、不读生产历史。没有执行原生入口时必须明确未验；真实模型最小连续任务和生产加载由Codex独立实查后闭合，不能为撞60%烧大量token。
- 客户端T/显式W及返回余量、执行者21600和取消/同连接边界分开，未核T不启用主动长等待；本片不新增主动wait/唤回。

执行者禁止改正式源/Git/配置/Key/模型/HOME/生产DB/owner，禁止启停角色/API/宿主、动Kimi/其它角色、恢复/取消/收取286、Browser或真实模型/网络/其它Agent。隔离服务清理只针对自己持有进程，不按名字强杀。

## 交付与整体状态

交可运行候选、真实差异/基线SHA、实际API/schema/使用草稿、原始测试回执、失败和限制，talk-delivery-1实际task_id=292，workflow validate带expect-task-id，最终TALK正文完整裸JSON。交付后暂停，用户通知完成后Codex独立实查/直接补正，不将候选complete写成整体已上线。

本功能在真实同窗/60%换窗/十次兜底/完整与增量/使用说明和必要实机验收均闭合前，整体保持未完成。用户指定宿主统一启动问题延至本功能整体完成/验收之后，替代291收尾后即切换的旧排序；其它新功能不扩展。
