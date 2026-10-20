# Project Progress

Updated: 2026-10-20 14:48（Asia/Shanghai）。284三日志表/来源管理/接收事务核心已独立实查、Codex直接修正并集成收取，最终51项通过，默认关闭，未接HTTP/生产启用。256/257保留历史needs_changes，核258替代后已收取旧结果。用户明确中止后是否沿用原任务号由派发角色按任务方向决定；页面简化待285交付后串行处理。本轮先完成284进度/Git，不自动开B2b。

## 284已实查、直接修正并集成收取（默认关闭）

- 详[284复核](spec/ROLE_RUNTIME_LOG_RECEIVE_REVIEW_284.md)。task284/project prj_e8fe7066bbec/creator agent:codex/target及原作者agent:deepseek/Hall group:task-425cda60af724510862865e5366f8c37一致；msg2891合法complete仅自报，raw SHA fb030fd68c1afedc725331f10fdedce513b8cd15d49101ced59b2d64f6833910；本地JSON等值/稳定引用ok，UTC06:48:25.503354收取succeeded/completed，原自报不改。
- DS交付后idle/无当前任务；82冻结源和237原件逐SHA保全，复核/修正仅independent-review/worktree。30旧表列/索引/FK/DDL、480旧模型非import顶层AST节点保持，仅新增三表和CheckConstraint import。
- 原37独立复跑通过；首轮10反例8失败（7项回执损坏仍成功、锁等待随engine），扩展14首轮13通过/1底层SQLite中断错误。Codex直接修正回执与原有序批次/事件交叉校验、默认1秒/最大5秒SQLite事务预算及连接清理、安全映射；最终原37+新增14共51通过/零错误，自己的修正称自检，无返修/互派回审。
- 四白名单正式集成：models追加三表、新runtime_log_receive_core.py及两测试。默认关闭，显式engine或全新Engine绑定Session工厂/clock/limits，无server.db/global CONFIG导入；来源管理/CAS、实际认证及角色/launch、去重/配额/序号/回执同事务。内部payload只接受可信投影，不是外部raw JSON入口。
- 未接HTTP/查询/真实writer映射/配置启用/宿主/outbox/跨机器/物理回收。API15792/9808无reload标志，未重载/迁生产库或启停。后续API重启会经init_db/create_all新增三张空表，必须纳入正常加载核验，不能把接收关闭说成不建表。首次集成因CRLF/LF原始SHA校验停止，协调脚本改核UTF-8文本等价后继续；四正式文件与51项测试工作区文本一致。证据.tmp/runtime-log-sqlite-core-v1/independent-review/，原失败和原件保持。

## 当前285（管理账号未入群全局只读查看，尚未上线）

- 用户明确仅自己的管理账号可看所有Group/Task Hall，不扩大所有human。现有operator Key只读确认human:bobo与项目maintainer一致，未查Browser；拟用默认空的conversation_access.observer_member_ids名单，仅合法未禁用human观察者越过读成员门禁，部署建议只human:bobo，当前生产配置未改。
- 覆盖本人能力接口、app/workspace进入/恢复/历史/成果、消息与撤回实时/SSE补发，账号切换失效；未加入只读，发送/附件/回复/mention/任务守卫及名册不变。禁止models/db/auth/host/角色/Key/生产/284范围写；首次交付后Codex独立实查、问题直接修正。
- 实际task285，UTC03:34:10.219198，project prj_e8fe7066bbec/creator agent:codex/target agent:kimi（kimi-code/k3），Hall group:task-9c2fef8c38f24b628bf15aa438eed7c4。基线e4c45a07ee0a9320245658c37e4f9a9a4272400e，89冻结源，.tmp/admin-conversation-view-v1/baseline只读、kimi/候选隔离、coordination/独占。
- 用户人工暂停后返回，UTC05:52:26.843842正常resume-tree以slice_budget=0恢复，epoch0→1/非委派不变，原K3实例ins_5a0d307d038c第2次接单。先核bridge13844/parent9728无子进程，无强杀/owner解除/任务重建。证据.tmp/resume-task285/；已有文件/记录保留，新attempt不等原生调用原地续跑。
- 本轮末仅核必要任务元数据，285仍running/in_progress/attempt2、result_message_id=null；实例上报idle不能替代任务事实，尚未取交付，默认用户通知完成后取件。
- 本次284集成了不重叠的models/新核心/新测试及协调文档；以后核285冻结清单时须将该批已核差异单列，不能误归执行者越界或覆盖三张新日志表。页面同文件小修待285交付暂停后串行处理。

## 已确认的任务中止/编号规则及待落地页面小修

- “暂停整棵任务树”改为“中止任务”，去掉“授权继续一批”；按讨论统一一个停止入口，移除重复风险暂停/整树终止按钮。中止仍撤销本次执行并阻止该树推进，保留任务号/文件/记录，不能改成无条件永久cancel。页面尚未修改，不插改285任务包。
- 最新用户澄清允许沿用编号：方向不变、停止后继续，由派发角色决定复用原任务；原任务不对/换方向，不沿用并另建。上一轮助手“一律永久取消、必须新建”建议已撤回。后端pause/resume/checkpoint/cancel、SDK和原权限合同保持，不自动恢复人工暂停的任务。
- 处理时同步必要说明/失效helper/缓存引用，保里程碑验收与整树范围，不能把“中止任务”解释为仅影响当前子任务。AGENTS同文件串行规则适用，待285交付暂停后处理/验证及页面人验。
- 已核风险checkpoint是立即撤销claim、awaiting_human/risk_boundary，不自动识别风险/等步骤结束；cancel-tree取消所有非终态任务且原树不可恢复，不回滚已有文件/历史。旧普通根页面resume提交1–3但服务端要求0的缺陷，由本次移除页面按钮消除入口；后端普通根恢复仍必须0。

## 256/257历史收尾

- 原256 needs_changes（旧身份误走CREATE、秘密列/凭据读取声明错误），257 needs_changes（全局截前200实例漏最新busy、读取监测未接线）；258以21项独立测试+5探针闭合准备问题，并于UTC2026-10-16T23:43:25.199230收取。后续产品/迁移已另片完成，不重新执行旧计划。
- 本轮核v1 22/v2 25文件SHA、两原review、258替代及msg2785/2788稳定引用；UTC06:45:26.757493/06:45:29.893749收取256/257为completed。只表示历史结果已收到，不把原complete/partial或needs_changes改为approved。证据.tmp/legacy-role-page-control/legacy-close-20261020/。

## 下一步与不变项

- 本轮284收尾提交/推送后暂停，不自动开新片。B2b为真实冻结writer版本化投影、受认证HTTP接收和human-only只读查询/游标/导出接线；来源生产启用、正常加载及真实跨机器另验。283已批准三表/登记撤销/接收查询，默认关闭先隔离，不重复请同一开发许可。
- 283方案原48通过、9独立反例失败，文件inbox不集成；仅补正合同后收取。证据.tmp/runtime-log-source-query-design-v1/independent-review/及[283复核](spec/ROLE_RUNTIME_LOG_RECEIVE_REVIEW_283.md)保持，B以[补正合同](spec/ROLE_RUNTIME_LOG_RECEIVE_DESIGN.md)为准。
- 日志B的持久outbox/严格ACK及实机跨机器、C全根治理仍待；C先盘点/dry-run，不自动删旧数据。日志整项完成后统一全入口执行预算21600并保显式覆盖，再会话复用。
- 当前TALK目录不改；main/独立worktree总目录布局仅以后新项目，不迁目录/开群聊分支。旧local日志scope/ref/cursor/导出partial与脱敏、角色/Key/模型/owner/启停守卫保持。

## 已验基础与协作

- 282实现6f3f9c5，169项相关自检/67秒隔离过；五宿主正常加载、四角色ready/idle、77.568秒周期/原进程及60–90秒心跳推进、用户页面验收均过，加载记录1e43502已推送，详[加载记录](spec/ROLE_HOST_RUNTIME_EVIDENCE_LOAD_282.md)。过去PID只作证据，未来先重核。
- 279真实轮询/完整下载/约150秒心跳保持，280绑定行197fe7a与278页面人验保持；模型/六小时/跨宿主/生产异常/跨沙箱驻留/冷启动不从alive推断。Codex桥接仍关闭。
- 本人MCP agent:codex/agent、lead，project prj_e8fe7066bbec；DeepSeek/Kimi K3首次执行自测暂停，Codex首次独立实查、问题直接修正自检、集成/进度/Git。AGENTS/用户最新约定优先于页面旧交叉要求，不派K2.8新任务。
- 默认派后结束、用户通知取件，不自动等待/唤回；不做Browser验证。精确用量比例未提供，不臆测百分比。

恢复指令：继续项目。
