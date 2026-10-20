# 日志来源、接收与查询实施提案（283复核补正）

日期：2026-10-20。状态：**用户已批准SQLite三表、来源登记/撤销、批次接收和只读查询；B2a三表/来源管理/事务内核已独立实查、Codex修正自检51项通过并集成收取，默认关闭。B2b投影/HTTP/只读查询尚未接线，生产未启用。** 详[284复核](ROLE_RUNTIME_LOG_RECEIVE_REVIEW_284.md)。原283设计/原型及48项自测完整保留，不能直接作为实现合同，详[283复核](ROLE_RUNTIME_LOG_RECEIVE_REVIEW_283.md)。A本地采集及282加载/人验保持。

15:45后续状态：用户明确同意285正常加载时创建本片三张生产空表，已备份/正常加载并核各0行；仅建表，接收仍关闭，无来源登记或HTTP接线，详[285加载记录](CONVERSATION_ACCESS_LOAD_285.md)。

## 目的与推荐取舍

完整日志仍按A本地采集→B来源/接收/查询→C全根治理→全入口执行预算→会话复用。B要让远端日志真正到达服务端，区分写入端时间与接收时间，并提供有来源边界的只读查询；给旧同机根增加host标签不足以产生接收事实。

保留原方案的受认证接收方向，复用已有角色Key和项目维护者human Key，不新增主机账号/凭据。**建议将服务端的来源计数、批次回执、事件存储放入现有SQLite的三张新增专用表，以一个受限事务提交。** 不采纳原文件inbox原型为产品：对象私锁、目录rename和独占seq目录不能共同保证权限、配额、去重、回执的一次提交，尤其没有与实际认证库的一致事务。

这是对283“文件inbox且不加表”推荐的实质调整。Codex提出具体三表/来源登记撤销/接收查询、默认关闭和隔离验证范围后，用户明确“按此范围开发（推荐）”；本次数据库/协议范围已获授权，不因原型存在推断授权。三张表只保存日志及无凭据的来源事实，不修改现有角色/任务/归属数据，不把来源登记当永久主机身份。生产配置启用、API正常加载及真实跨机器拓扑分别验收。

## 身份、来源及读取

- 角色写入：现有未禁用agent Key，精确project/member及未归档角色名册；已关联实例必须同时核instance.project/member/host/launch和launch.project/member/host/instance，双向一致。旧无launch实例只能明确降为instance归因，不补造launch。
- manager写入：项目维护者现有human Key，project/host来源登记和内嵌manager_run.host一致；member=unknown、角色instance/launch缺失。来源host是维护者及既有实例/launch事实支持的标签，不是密码学主机身份；不从当前owner倒填manager所属角色。
- **首次空宿主问题**：旧“host曾在角色实例中出现”无法覆盖首次启动或尚未启动任何角色的宿主。B2必须明确维护者显式登记/撤销受控日志来源的入口；只登记project/host/subject及版本，不生成Key、不探测/启动进程。未登记保持source_unconfigured，不能把缺日志报成健康。登记/撤销公共接口同属待确认范围。
- 写入事务重新反查现有Key、禁用/角色归档/凭据版本、来源版本及实例/launch。以该写事务为提交边界；认证、来源撤销和日志写入均由同一SQLite库的事务序列确定。CPU解析/脱敏先在事务外完成；事务内只做有界重核、去重、配额和写入，不做网络/模型/文件扫描。
- 读取保持human-only；旧local角色权限、scope不变。新增received角色按project/member/host，manager按project/host且仅维护者读。存量历史来源可在撤销后保留只读并明确警告，不通过当前在线/owner过滤历史。新读取必须逐条二次核scope、格式和白名单，不能信任存储中已有的任意JSON。

## 原始记录到上传对象的显式映射

接收协议不是原JSONL的无条件透传。实施时须固定版本化上传投影函数与测试，先用**真实冻结写入器输出**验证映射，再做接收验证；raw record中的额外字段不能只靠删掉报错字段来“兼容”。

| 标识/字段 | 合同 |
|---|---|
| writer_run_id | 既有顶层run_id，来自实际写入器；原值保留，上传对象明确命名 |
| manager_run_id | extra.manager_run/launch_process中的实际serve标识；独立于writer_run_id；合法started/terminal可共用manager_seq |
| event identity | project/host/subject_kind/subject_id/writer_run_id/log_id组成的不可变来源键；batch_id/ordinal不属于事件身份 |
| pid/runtime | 有界诊断事实；pid是写日志进程，不拿它接管或当子进程PID；子PID沿已核spawned关联 |
| manager instance | 本地unknown哨兵明确映射为无角色实例，不编造实例；原写入器run不改成manager run |
| integrity/budgets/exception | 逐项固定现有真实字段、类型、限制及脱敏；包含真实integrity细项、预算来源字符串和安全frames/cause_chain；不能把原型七预算/三完整性键当现有完整格式 |
| extra | 单独白名单投影既有transition/queue_poll和282 manager_run/launch_process；其余任意extra不透传，不能默默丢掉已确认日志类型 |
| message/segment/path/argv/env | 现有不公开内容继续不公开；上传投影明确剔除的本地存储字段与未知字段错误分开；不上传segment_file/内部路径/原生输出/凭据 |

具体wire字段、错误码和DTO须在B2包中以逐字段表/样本冻结，不能凭原283表直接编码。manager除循环快照外的启动/结束/失败/恢复事件也要列出阶段范围：若第一片不接收，明确保本地且列后续，上传者不能把它们混入已批准批次再静默忽略。

## 三张日志专用表与原子性

1. **Source**：不可变project/host/subject scope、登记/撤销状态、版本、已用字节/事件/批次数及下一来源内接收序号。字段不含路径、Key、owner或原生会话；版本用于cursor失效。
2. **Batch**：按来源+writer_run_id+batch_id唯一；固定规范化内容指纹、有界有序event_uid列表/回执、首次真实received_at、batch_seq及提交结果。重复同内容返回原回执；同键不同内容409。
3. **Event**：按不可变来源事件键唯一，并生成稳定event_uid；安全版本化payload及首次received_at/received_seq。相同事件换批次/顺序不重复计费或入库；同事件键同内容重用原事件与首次时间，不同内容409且整批回滚。

批次去重、事件去重、版本/双向身份重核、容量判断、序号、payload和回执必须在一次写事务内成功或全部回滚。独立服务对象/并发连接共享数据库唯一约束与事务，不能仅依赖某个Python对象锁；无成功COMMIT不给accepted回执。崩溃在提交前零半批可见，提交后响应丢失可查回原回执。重复Key/内容冲突及认证失败不能泄漏其它来源的回执。

received_at取事务中即将提交的真实服务端墙钟，只有COMMIT成功的时间才对外生效；不声称“COMMIT完成后才取值并已原子写在同一事务”。事务内延迟有界，失败时间不对外作为已接收时间。保recorded_at原值，两者都不冒充文件mtime/查询/generated_at；服务端时钟回拨不改写旧时间，排序/续页有稳定来源序号与事件键，无重复或遗漏。manager_seq缺口不代表日志丢失；batch_seq缺口只说明传输观察，不能独自证明源日志完整性。

## 兼容、预算与失败

- 旧local来源配置、角色GET/导出、page-1、旧ref/cursor与排序保持原行为。新received接口另用版本化DTO/签名cursor；默认不跨origin混合，不让新数据改变旧ref命中。received内旧log_id多命中报歧义，新event_uid精确定位。
- 新cursor绑定scope/完整filter/limit、来源版本、稳定接收快照与最后排序键；改变scope/filter拒绝，源撤销/版本变化明确失效。B2固定使用稳定快照或明确409策略，不临时混用。
- 先沿原提案的请求4MiB/最多200记录、投影单条256KiB、单页最多50默认20/2MiB、31天范围、10秒处理与查询预算；**全部字节按最终UTF-8实际编码及响应封装计算**。完整栈/原因链须复用既有安全上限，新增字段有独立限制。事务执行时间另设更短有界目标，超时回滚并明确可重试，不长时间锁库执行外部动作。
- 每来源128MiB/5000批次只可作为首片暂定可配置上限，计入实际规范化存储、回执/索引开销的保守预算，不能按客户端body自报；新增源还须有全局有界上限，禁止通过创建大量来源绕过容量。SQLite文件自身/WAL/空间回收另由C制定，B2不得自动删旧数据。
- 413输入超限、403/401认证、409冲突/游标、429并发受限、503超时/不可用、507容量拒绝均为明确结果。扫描/投影/损坏限制必须partial或失败；不按成功空页掩盖缺源/未接收/损坏，不直接返回raw行。

## 后续最小切片及门禁

**用户已确认的B2服务端范围**：新增三张日志表、显式来源登记/撤销、受认证批次接收及有界received列表/详情；默认关闭。建议白名单为server/models.py（只追加日志表）、新server/runtime_log_receive.py、runtime_log_received_query.py、runtime_log_received_models.py、server/routes/runtime_diagnostics.py（只追加新路由）和对应新测试。是否拆登记/存储核心与HTTP接线两片，在任务包按共享文件依赖串行固定。

不修改server/auth.py、既有业务表、旧日志接口、长期host/bridge、角色/模型/Key/归属、现有配置值或生产DB。接收配置默认未启用；测试只用隔离合成SQLite/配置。首次实现由DeepSeek、自测交付暂停，Codex独立实查并直接修正。新增DB/API已通过本次用户确认门禁。先派B2a：仅追加三表、接收事务/来源登记撤销内核及对应隔离测试，不加HTTP/外部DTO/配置或接收原始JSONL；B2b再串行固定真实上传投影和查询/HTTP接线，不并写共享文件。B2a内部payload只接收服务端可信投影产物，不能在B2b让客户端任意JSON绕过投影；首片不冒称上传兼容/外部读取已完成。

B3再做host侧持久outbox/明确投影/上传与正常加载：成功回执必须精确匹配schema、accepted=true、来源/writer/batch/指纹及持久结果才可移除pending；任意字典、accepted=false、错scope/错指纹不算ACK。重启、响应丢失、重分批、配额/超时/撤销、重试耗尽与本地留存均提供真实隔离证据。真实跨机器/TLS拓扑、生产received_at与页面导出另验，逻辑两来源fixture不替代实机。
