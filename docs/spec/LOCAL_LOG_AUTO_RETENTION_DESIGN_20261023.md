# 本机日志后台自动清理：实现及验收合同

## 授权与基线

2026-10-23用户确认：后台每天检查/启动补检，30天保留、单个显式日志根1GiB软预算；无需前台逐次操作。用户明确“可以开工”。Codex开发、自检；DeepSeek独立复核，发现问题后Codex修正并交定向复验。基线282ac47，Kimi开发暂停、286保护及下一新片先确认保持。项目页面development_requirements旧分工不改，本次明确分工优先。

本片包含实际自动删除实现与隔离验证，生产配置/已有角色尚未变更或重启。不能把代码通过、自检通过或后台线程存在等同于生产已启用；独立复核与正常加载后另提供实际证据。

## 关闭与范围证据

- `RuntimeDiagnostics`成功建立目录后持有Windows `run.lease`可写文件句柄，禁止共享写/删除，直到close或进程结束。异常退出仅释放OS句柄，不产生完整closed凭据，因此不能单靠进程退出清理。
- 每次成功写事件记录task_id集合和分段序号范围，非法/未知任务ID、超出1024个任务/4096个分段或写入失败会使关闭证据不完整。close在同一线程锁内停止后续写入，生成`closed.json`，记录项目/成员/实例/run、关闭时间、日志前缀、任务ID和剩余事件分段的设备/inode/大小/mtime/序号范围，然后释放lease。仅旧日志、缺凭据、无可信lease的run保持保护。
- 清理根只能取服务端显式`runtime_diagnostics.sources`，同一物理/长路径根合并已配置(project,member)范围。closed中的项目/成员/实例路径、run和事件文件名必须匹配；不接受客户端路径、PID或未经登记的根。无精确成员归属的manager记录不会被倒填为任一角色。
- 整个run的关闭时间、各待删事件分段mtime均须早于保留阈值，并与关闭快照一致；未登记的`events-*.jsonl`、链接/重解析点或已声明文件变化会保护。普通额外文件（如notes.txt）保留，但不阻断符合条件的事件分段清理；不宣称发现任意新增文件都会停止清理。任务ID集合必须非空、全部存在且同项目/执行成员，runner终态、workflow已完成/取消、control_status明确active；空任务、NULL/未知控制状态保持保护。manager/idle等无任务run本片不另设删除豁免。
- 从这些任务双向遍历parent/root、原生续窗base_task_id和关系/trigger依赖；所有可达任务必须同项目、明确已闭环，关联角色可以不同。缺失/未结束/paused/未知任务均保护，包含本任务指向的祖先及多层依赖；已闭环循环通过visited去重。最多1024个可达任务、协作式100ms检查预算，超限保护；仅依赖公开结构化关联，不猜测任务正文中的自然语言依赖。

## 自动执行与互斥

API lifespan启动`RetentionService`后台线程，不依赖页面保持打开。enabled时必须有非空、绝对路径storage.db_path并与当前持久SQLite engine精确匹配；缺失/相对/内存/另一DB均先关闭worker且不接触来源。启动立即检查持久化due时间，到期才执行；默认一天一次，失败或批次受限最多5分钟后重试。停服务设Event并有界等待线程退出，不中断角色或重建owner。电脑/TALK关闭期间不另加系统调度器，下次启动补检。

根级`.retention.lock`可写句柄阻止多API进程同时执行；run级同样取得lease排除仍在写的producer。目录祖先逐级拒绝链接并持有Windows目录句柄，文件以OPEN_REPARSE_POINT打开、检查实际最终长路径/类型/身份，不按枚举出来的路径unlink。删除使用`SetFileInformationByHandle`标记**已核验句柄**并关闭；该句柄禁止共享写/删除，因此在检查与删除之间不能被普通改写/替换。

每run在删除期间取得SQLite非阻塞BEGIN IMMEDIATE预约，只读查询任务公开状态，防止任务检查后发生重领/恢复/关联变化。业务行不修改，busy时保留并重试，原busy_timeout恢复。关闭凭据全程持有禁止共享写/删除的读句柄；事务前、事务内每次删除前及批次后均核验目录/全部分段。无intent的缺失或新增事件记auto_expire_protected并partial，不静默complete。单事务目标最多10个删除，协作式约250ms预算（单次OS文件调用不能被硬中断），单轮默认100个/10秒、目录20,000条目。预算不足、变化或失败均partial；不是强制OS截止。

run lease约束合作writer；目录句柄禁止替换目录但不能禁止不合作程序新增文件。最后一刻的外部新增可在事后复查中发现并标partial，已完成的精确句柄删除无法回滚，不宣称跨文件原子删除。

## 保留、容量及原writer协调

默认30天、1GiB都可配置。1GiB是软预算：超限不越过最近30天、活跃、任务引用或未知证据保护。记录观察字节、扫描完整性、是否超预算及保护原因数量；部分扫描不足以断言预算充足。

启用后的根写入`.retention-policy.json`。新版writer对该根的已登记范围停止旧的每run期限/容量删除，保留分段轮换，容量超出只记软超限，避免旧256MiB策略提前删近期分段。策略文件不可读时保守停止旧删除；在首次启用前没有该标记的根继续原行为。关闭后台worker后已有策略标记仍保守保护这些writer，不自动恢复旧的破坏性清理；如要迁回旧策略须另行明确迁移。

manifest、closed、lease、rotation及删除痕迹不按30天直接删除，供追溯并计入全根占用；软预算可能因为这些元数据/未知旧run而无法降到阈值，不能伪称已达标。私有`.out/.err`、桌面内部日志、其它未知根和网络接收不在本片。

## 审计、失败与历史引用

每个分段先fsync `retention.jsonl`中的auto_expire_intent，再按句柄删除，成功后追加auto_expire_result/deleted；失败记failed，不先写成功。若删除后写结果中断，原intent保留，下次在相同closed证据/任务保护/互斥下确认缺失，补missing_after_intent，不将不明缺失冒充本次成功。已记录结果不重复追加。每run痕迹有8MiB读写上限，超限保留，不绕开审计删除。

`.retention-state.json`保存下次检查和最近一轮摘要。人类详情或精确ref查询缺失时，对已登记根做有界到期证据查询：closed范围/日志前缀/分段序号及project/member匹配的成功/核对缺失结果返回HTTP410 `log_expired`；其它缺失保持404；证据受限返回503，不伪造到期。旧报告/任务/消息正文不改，不读取原生认证或完整对话。

## 启用与部署边界

为避免现有测试/未登记部署隐式清理，worker必须显式启用；默认缺省不运行。正式配置示例（来源仍使用已核验的runtime_diagnostics.sources）：

```toml
[runtime_log_retention]
enabled = true
retention_days = 30
max_total_bytes = 1073741824
interval_seconds = 86400
```

这是一项部署设置，日常不需要前台操作。当前未写生产config.toml/私有清单、未重启API或角色。正常加载时先保证新版producer/宿主写入器进入可核验版本，再启用后台并正常加载API；未知旧run保留，不能为让清理发生伪造closed或回填历史。当前强句柄删除后端只支持Windows，权限/短名展开/本机根验证不满足时失败保护，不宣称其它OS通过。

## 本片验证与限制

首轮127项Codex自检通过不代表独立通过。317独立复核为partial，发现F1检查/删除窗口、F2祖先任务遗漏、F3缺DB绑定放行、F4空任务及F5回归夹具/环境缺口；原报告/失败证据保留于`.tmp/local-log-auto-retention-v1/review/`。

Codex修正后在317同一review/tmp环境变量根重跑132项通过（含27项自动清理/SQLite/后台测试），证据`coordination/fix-regression-2.log`；317原始5个反例的协调方副本亦全部通过，见`coordination/recheck-317-findings.log`。旧测试在删除临时目录前显式关闭writer/manager日志句柄，junction创建不再使用PIPE；未削弱产品ACL/私有记录发布核验。

318 DeepSeek定向独立复验为complete/pass，132相关回归、27新增测试、原5反例、37个旧失败项及27个复核侧反例全部通过；本环境真实HostStore私有发布也通过。23产品/合同、10证据共33份冻结匹配，317原报告/失败证据保持，318结果2959与本地交付一致。Codex取件核验见`coordination/318-acceptance.json`，独立报告/日志在`review-fix1/`。318已收取；317原收取曾被自动审批拒绝，用户随后明确授权后于UTC12:00:49正常收取completed，原partial/2958不改。

Codex另外用真实随机端口API、正式lifespan、隔离SQLite/来源做加载补验：启动时后台自动删除一个40天旧且任务闭环的分段，HTTP详情410，未认证401、agent403，近期/活跃分段保留，持久next_check约一天，API退出时worker停止。仅本轮fixture，无生产副作用，见`coordination/api-smoke.log`及`api-smoke/result.json`；这项是加载自检，不冒称DeepSeek独立生产验证。

首次测试默认Temp使用8.3用户路径，在当前沙箱内原生父目录打开/展开受限，按失败保护无删除；夹具改为项目内独立临时根后真实句柄删除通过。不能外推所有短路径/ACL环境通过。扩大回归发现两个既有夹具缺口（baseline已传start_from_latest而FakeClient未接受、本机HTTP误走环境SOCKS代理），仅修夹具参数/测试客户端trust_env，产品参数和环境代理保持；原失败证据保留。

关闭时间/mtime使用本机时钟，近期/将来时间保留；协作式预算和非原子容量快照限制如上。旧run保护不会追补自动清理能力；历史元数据保留可能持续占用。代码已独立复验通过，生产功能最终验收仍待[部署门禁](LOCAL_LOG_AUTO_RETENTION_DEPLOYMENT_20261023.md)。本片默认30天/1GiB已获用户批准，315阶段曾为提案；不因独立报告沿用“提案”一词而把本片授权倒退或误称生产已启用。
