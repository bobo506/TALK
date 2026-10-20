# 283日志来源、接收与查询方案独立复核

日期：2026-10-20。结论：方案产物已检查，原48项在独立副本复跑通过；新增9个独立反例全部失败。Codex仅补正[实施提案](ROLE_RUNTIME_LOG_RECEIVE_DESIGN.md)，原文件inbox/原型不能直接集成。用户已明确确认三表/来源登记撤销/接收与查询范围，默认关闭并隔离验证；B产品/跨机器/生产未实现。本片自己的方案补正称自检，不冒称他人复核或“修后9反例已全过”。

## 交付、身份与基线

- 原task283/project prj_e8fe7066bbec/creator agent:codex/target及结果作者agent:deepseek，Hall group:task-5ba13f2d6bf94892b4103dadb95b85ef，接单ins_39ba69bf6dfe一致。msg2890合法talk-delivery-1，自报complete只代表方案；原文SHA eafec2b0b993b2f8b50ef6cf4b485f8ddc65f26865b1e2600cd499f4fa950bc2，与本地delivery的JSON值一致，文本因排版/尾换行不完全相同。
- 取件时DeepSeek UTC02:42:40.844391已idle/current_task_id=null；当前MCP身份agent:codex/agent。交付后暂停实查，无并行产品写入或追加返修/回审。
- 原冻结1e4350238e1435e4abb71b72e8663173e8a4240d、79源/指定文档SHA保持；当前755dd60仅三份授权协调文档差异，产品未漂移。原成果含14自报路径及测试临时证据，归档162个文件，原候选/报告/原始失败不改。

## 实际核验

- 本地合法结构化摘要与任务号/来源核对；源码实查含来源配置、human-only路由、既有project/instance/launch/角色字段和原型接收/扫描/分页/outbox。
- 独立worktree复制冻结源与原候选，重跑原48测试：48过、零失败/错误/跳过，0.844秒，server.db未导入。原生产配置/Key/DB/日志/原生会话未读，零网络/模型/启停；只有隔离根写入。
- 真实冻结RuntimeDiagnostics在隔离根产生manager记录，证实顶层writer run与extra.manager_run_id不同、manager实例为unknown哨兵、存在pid/runtime/segment_file和integrity细项；不是手工fixture捏造接口兼容。

| 独立反例 | 原方案/原型表现 | 补正方向 |
|---|---|---|
| 实际写入器记录 | 原样交接收到unknown_field；没有显式上传映射 | 固定版本化投影，逐字段处理实际格式及哨兵；用真实writer样本验收 |
| 两种run ID | 实际writer_run放批次会被错误判host_mismatch | writer run与serve manager run独立，不改写原标识 |
| 同事件重分批 | 同source/writer/log换batch_id后得到两条和不同event_uid | 事件身份去掉batch/ordinal，事件去重与批次回执分别持久化 |
| 实例/launch双向映射 | 新launch指向同实例即可通过，实例本身仍关联旧launch | 同时核instance.launch_id与launch.instance_id等完整元组 |
| 提交前撤销 | 校验后/写入前禁用仍提交 | 与认证库在同一受限写事务重核后原子提交 |
| 两store并发容量 | 上限1时两个独立store各自私锁，两个批次都成功 | 数据库事务/唯一约束和来源计数，不能靠对象私锁 |
| UTF-8页预算 | 按字符串字符数计费，中文响应超过字节上限仍成功 | 对实际UTF-8编码及封装计字节 |
| 已存记录损坏 | 修改隔离records后，读取直接透传新增payload_secret/extra.argv | 读取二次白名单/校验/脱敏，损坏明确partial/失败 |
| outbox错误回执 | accepted=false/错scope的字典仍删除pending | 精确有效持久ACK才可移除，错误/中断保留 |

首次9反例运行有6失败/3错误，其中页预算反例自身未补齐exception五键，未到目标逻辑。保留首次日志；补齐fixture字段并将两个预期成功却被拒绝的分支改为明确断言后，9项均失败、零error/skip。原型未改，修正的是独立探针自身，不把错误输入的失败算作产品缺陷证明。

## 其它设计缺口与取舍

- 原B2白名单既不改配置入口也没有明确根启用路径，源撤销只有fixture集合；“既有host事实”还不能覆盖首次空宿主。必须固定显式来源登记/撤销及默认关闭，不能通过实例启动探针补事实。
- 原事件白名单省略transition/queue_poll、真实预算/完整异常，不能称完整跨宿主日志。received导出/manager其它事件可分片，但须列依赖，不让上传者静默丢弃。
- 文件inbox中时间在写文件前取得，原合同却称提交/fsync后取得；manifest/COMMITTED耐久及认证库一致性没有证据，单进程声明也没能覆盖同进程多store。仅增加锁无法证明跨DB/文件的一次提交。
- 补正建议复用原主体、以现有SQLite三张专用日志表统一来源计数/事件/回执及认证重核。该设计取代文件inbox推荐，属于新增数据库/公共协议的实质范围，须先用户确认；并未实施三张表或改生产库。
- received查询与local默认分开，旧GET/ref/cursor不改；新标识与raw writer无损关联、二次投影、容量/并发/全局来源预算、B3严格ACK均在补正提案固定。真正HTTP/DB/跨机器/持久outbox/加载与C仍待。

## 保全与后续

证据根.tmp/runtime-log-source-query-design-v1/independent-review/：source-result-message、archive（162原件SHA/79源）、original-delivery、worktree、original-48.stdout/stderr及副本evidence、negative_probes、negative-original和negative-original-corrected-fixture的原日志/JSON。后续保留稳定结果引用/收取回执及文档检查，不把原型修成产品后覆盖原件。

稳定引用SHA复核ok，UTC2026-10-20T02:53:51.162402已收取283/completed，原complete自报/失败不改。Codex提出三表/新接收与读取/来源管理的可审范围后，用户明确“按此范围开发（推荐）”，本次实施范围已确认；先完成本片Git收尾，再固定B2a三表/事务核心白名单派发，HTTP/查询接线依赖后续串行切片。当前TALK目录不改，用户的main/worktree布局只针对以后新项目，不创建分支或改变群聊排期。
