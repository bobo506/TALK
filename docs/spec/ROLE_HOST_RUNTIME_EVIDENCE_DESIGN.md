# 宿主本地运行证据实现合同（281复核补正）

日期：2026-10-20。281是方案/隔离验证任务，原交付msg2888与complete自报保留，不等于产品已实现。Codex独立实查及反例后固定本合同；后续实现以本文件为准，不直接照搬原型。完整日志仍按A本地采集→B来源/接收/查询→C全根治理推进，再预算统一、会话复用。

## 范围与已知缺口

现有HostManager.serve有host_started/stopped、poll_failed/recovered、动作/worker异常，没有正常周期证据；279 queue_poll来自bridge，不能证明宿主管理循环推进。现有角色诊断GET/DTO/导出只有精确project/member scope，无manager接收接口或received_at。

下一片A只补本地记录，不增网络请求、DB/HTTP/DTO/页面/认证/配置。manager记录沿旧写入器保member=unknown，不混入角色下载；launch记录只用原内存Popen及匹配启动事实，不按PID/磁盘记录/当前owner重建归属。Popen存活只说明原进程尚在，不代表bridge、领取或模型可用。

## 循环与生命周期

1. 每次实际serve生成独立mgr-加32位十六进制manager_run_id；不写owner/DB，不当所有权凭据。真实每轮开始时递增manager_seq，初值1；无后台定时器、无睡眠期间自增。循环阻塞只能留下已开始证据，不会出现伪完成。
2. 沿真实begin/finish边界采样，采样间隔固定60秒，按单调时钟决定。首次写started与完成；稳态每60秒至多一组。poll失败段首个完成立即写，连续失败每60秒至多一个完成；计数覆盖全部真实失败轮。真实恢复立即写一次succeeded及recovered_failures，可无同轮started；取消同理可只有terminal记录。不能为了配对补造开始事件。
3. state=succeeded表示整轮走完且本轮claimable_actions读成功；不是动作成功或健康总分。state=failed仅表示整轮走完且该次poll为可恢复失败，计数/时间也是这些已结束失败轮的事实，不冒充HTTP返回瞬间。动作的可恢复失败沿现有action_failed，不计入poll连续失败。
4. 未处理Exception沿原路径传播，不为填满快照把动作异常算poll失败；当前轮未走完，保开始记录及host_stopped/exception，不生成succeeded。KeyboardInterrupt/SystemExit/CancelledError等取消保原对象/退出码和控制流，当前未完成轮可记canceled。睡眠或正常worker收尾时发生取消/异常，不重复结束上一已完成轮。
5. 保原正常worker收尾位置、窗口和行为，不因finally新增异常路径worker等待/stop/kill。仅将host_stopped诊断放finally，恰好尝试一次，新增manager_run_id、stop_reason=once|max_rounds|normal|canceled|exception。异常日志仍用旧安全包装；不改变原outcomes、返回/抛出及句柄。原host_started/stopped字段保留。
6. 写入/校验/时钟/观测/初始化失败只让新证据缺失或未知，不使serve或业务动作失败。不能对旧host参数施加新业务校验；诊断值不合规时限长清洗为unknown或放弃该条，不拒绝原操作。时钟异常/非有限值不能填0伪造耗时。不能递归记日志覆盖原异常。

## 固定extra合同

保持talk-runtime-diagnostics-1顶层和transition/queue_poll不变，新增两个独立对象，不放自由文本/路径/argv/凭据/输出。经过既有redactor、嵌套/事件大小/轮换规则。

extra.manager_run固定16键：manager_run_id、host、manager_seq、state、started_at、finished_at、duration_ms、last_success_at、last_failure_at、failure_streak_started_at、consecutive_failures、recovered_failures、poll_interval_seconds、sample_interval_seconds、actions_seen、process。

| 字段 | 固定语义/校验 |
|---|---|
| manager_run_id / host | 本次运行ID；host是有界诊断标签，沿现有host事实、非认证/权限 |
| manager_seq | 严格整数，1..2^53-1，拒bool；不得复用10000条查询上限。launch_process同范围 |
| state | started/succeeded/failed/canceled，必须str |
| started_at / finished_at | 真实带时区ISO；started的finished_at=null，terminal非空。墙钟回拨允许，不能据墙钟排序推耗时 |
| duration_ms | started=null；terminal有限非负单调耗时，上限31天毫秒；异常时不造值 |
| last_success_at / last_failure_at | 最近已完成成功/失败轮墙钟；对应state必须等于本轮finished_at。不是远端接收时间 |
| failure_streak_started_at | 活动失败段或恢复记录保真实首轮完成时间，否则null |
| consecutive_failures / recovered_failures | 严格非负整数，≤2^53-1，拒bool；succeeded连续数必须0；仅恢复succeeded可有recovered>0，且必须有原失败段时间；其它recovered=0。不按10000截断或伪造真实次数 |
| poll_interval_seconds | 本次serve原实参，有限非负，不能改变实际轮询预算 |
| sample_interval_seconds | 固定60；不是客户端可控放大采样频率的配置 |
| actions_seen | 真实本轮poll返回条数，非负整数≤2^53-1；started=0，不代表执行成功数 |
| process | 固定held/alive/exited/unknown/truncated五键，见下 |

process完整时四计数是非负整数，held=alive+exited+unknown；计数均拒bool。不采样的started记录不做Popen观测，四计数全部null、truncated=true。整体观测失败或无法确定项目内总数时同样全null/true，不能返回精确0/0/0/0/false假装没有进程。部分观测而项目内总数可确定时，未观察的进程计入unknown且truncated=true。旧记录没有新对象保持unknown；坏新对象不能当完整/正常。

extra.launch_process固定6键：manager_run_id、manager_seq、launch_id、state、observed_at、exit_code。state=alive|exited|unknown；observed_at为实际只读poll时刻；仅exited有退出码。退出码严格整数，保原平台数值：-2^31..2^32-1，允许Windows无符号错误码，不能转成bool或伪造0。launch_id必须与原handle键/record一致，身份放既有顶层精确project/member/instance/launch；不复制任意record字段。child PID可与原spawned事件关联，不假称原型已在本事件写入child_pid。

## 原Popen观测与开销

- 仅在实际要写terminal采样、失败首条/周期、恢复或取消时观测；不得在每个未采样finish调用observe，也不在started再次poll。默认上限每条terminal观测32个Popen、至多检查256个handle条目；元数据也需有界。不得为计数遍历/复制无界全部句柄。
- 观察前核原内存record.project_id=当前serve项目、record.host=本manager、handle键=record.launch_id、record.pid=原Popen.pid，以及合法member/instance。明确其它项目的条目跳过；不匹配或身份缺失不得产生角色记录。仅使用仍持有的原句柄，不新增磁盘/OS身份查询、不拿PID打开别的进程。
- 完整有界元数据可知项目内held；超扫描限额、未知项目或整体观测失败则四计数null/true。已核scope的少量launch观测仍可写，不能冒充完整聚合。每个launch只写一次/采样轮；选择顺序不能让稳定前32条永久饿死后面的已核launch。具体有界轮转实现可在白名单内选择并验证。
- poll()抛错、返回bool/非整数/越界退出码时为unknown，禁止把类型转换后的值当真实退出码。读取只用poll，不wait/terminate/kill，不删除句柄或改业务服务状态/owner/租约。
- 60秒只约束新增快照，不声称旧poll_failed等异常事件已限频。新记录最多约(2+32)条/分钟≈48960条/天；5个launch约10080条/天。实际字节依既有轮换/截断，不能声称全根容量已治理，也不承诺一次10000条导出覆盖全天。

## 接收与查询后续门禁（B，未批准实现）

A不填received_at，不把recorded_at、mtime、本地查询或generated_at冒充服务端接收；无接收事实保持缺失。维护者可用既有本地CLI读取新增固定对象：scripts/runtime_diagnostics.py --log-dir 隔离根 --event manager_round_snapshot --limit 20 --json --detail。仅--json走摘要投影，不能声称必定含extra；正式日志根由维护者明确指定，本轮不读生产。

281的host新凭据/enrollment、POST manager-batches、GET manager-records和DB表只是提案，不是既有能力，也不是本合同对公共API/认证/DB的批准。后续先结合现有来源与角色服务认证裁定是否确需新增host凭据，不能仅因原型选择就固定新身份类型。

接收提案的已证实缺陷须先闭合：

1. manager_seq是循环编号，同轮started/terminal共用，不能当独立记录唯一序号或严格递增水位。后续应使用本run独立事件序号/稳定事件ID，允许合法同轮多状态；不要将采样seq缺口标为日志遗失。
2. body.host、每条manager_run.host、认证绑定project/host必须全部相同；不得仅校验外层。manager/launch来源与scope仍分开。
3. 幂等/冲突键至少含project+host+run+batch；不同host同batch_id不能互相冲突或泄漏接收元数据。认证、校验、去重、写入、序号/水位与received_at必须在同一事务中确定，原型分散锁不证明并发原子性。
4. 新读取/导出必须有项目+host授权和时间/行数/字节/分页预算；原型全量内存GET不证明现有partial/ref保护已复用。离线文件不变也不证明真实outbox重试/持久性完成。

服务端真实接收时间仅在真实受认证接收并校验、实际存储成功时产生，重放返回原时间；来源/存储、重放、撤销、稳定ref和旧记录兼容必须另片固定。B/C和日志整项均未完成。

## A实现白名单与验收

候选产品白名单仅scripts/role_service_host.py、scripts/role_service_host_loop_evidence.py（新）、tests/test_role_service_host_loop_evidence.py（新）、tests/test_role_service_host_diagnostics.py（只追加）。正式文档/Git由Codex维护。无server/通用写入器/页面/生产变化；首次实现仍DeepSeek隔离、自测后暂停，Codex独立实查/直接修正。

必要验证包含：真实serve正常/once/max_rounds、可恢复poll失败/恢复、动作异常、sleep/worker收尾取消与异常原对象传播；10000边界与至少21600轮假时钟；固定60秒限频、未采样无Popen观测、阻塞无假心跳；回拨/坏时钟；跨项目/错launch/错pid/缺身份/整体观测失败；>32/>256及公平选择；真实自建Popen存活/正常及Windows非零退出；诊断禁用/初始化/写入/report二次失败；旧数据unknown、manager不进角色导出、本地CLI用--detail见新对象。隔离证据不能替正式实机/60秒常驻/跨宿主验收，原ACL WinError 5/plain替身限制须保留。
