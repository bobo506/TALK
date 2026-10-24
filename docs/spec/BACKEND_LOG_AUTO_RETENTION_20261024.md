# 新增后台日志自动清理覆盖

## 授权与范围

用户已确认下一片为新增API/统一后台/runtime/配置worker日志的自动清理覆盖，2026-10-24明确仍由Codex开发、自测，DeepSeek独立复核，替代临时DeepSeek首次开发安排。基线9b21a51；322部署证据复核已通过并收取2963，无产品修正项，原320/321 partial及322权限/P3限制保留。

本片仅新后台日志源，保现有五角色清理、30天/1GiB/每日检查及启动补检、原项目/角色/模型/Key/绑定/286。日常无需页面操作。不扩展WorkBuddy角色原生日志/其它未知根/私有.out或.err，不联网上传，不开发主被动，不追改或解除历史任务。

## 独立开关与根

原`runtime_log_retention.enabled`总开关保持。新增布尔`runtime_log_retention.backend_enabled`，缺省false；本片代码与测试不修改生产配置或重载服务。只有总开关与新开关均true、原绝对SQLite DB绑定正确且backend_diagnostics本身有效启用时，才注册新后台来源；错库/未绑定/不可读根不清理。

```toml
[runtime_log_retention]
enabled = true
backend_enabled = true # 正式启用必须在复核后另行确认
retention_days = 30
max_total_bytes = 1073741824
interval_seconds = 86400
```

新源根沿现有`backend_diagnostics.root`和显式项目列表，实际受控根为`<root>/<完整项目ID的SHA256>`。同一项目的api/runtime/provision_worker三个组件共享该子根及1GiB软预算；多个显式项目各用各自项目子根预算，不声称整个物理父目录共享1GiB。未知项目子根不注册/不删除。与旧角色根相同、祖先或后代重叠时保护新源，避免覆盖旧根policy/扩大删除范围；缺根不为清理擅自创建，后续周期再尝试。

## 关闭证据与共享项目保护

backend:project是存储命名空间，不注册角色或伪造任务。后台日志没有完整逐任务引用，不能直接放宽旧角色“空task_ids不删”的规则。

新_BackendWriter正常close时，在原持有run lease的关闭流程内追加代码声明的`retention_scope=talk-backend-project-retention-1`和有限backend_component。通用writer的关闭扩展缺省为空，不改变原角色凭据；扩展不得覆盖任何原关闭事实，否则不发布关闭凭据。旧后台run缺该新证明继续保护，不补写/回填，不以旧322的lease存在性当删除证明。

后台专用验证同时要求：原关闭schema/complete/精确project/member/run/instance/分段证明有效；member严格为backend:project、task_ids严格为空；新scope声明正确、组件有限且匹配component-PID实例形态；项目ID哈希与实际子根一致。仅该适配器允许taskless关闭；旧角色默认验证仍要求非空真实任务引用。

删除使用原Windows精确句柄内核：pin完整目录链、拒绝reparse/未知路径，独占run lease、读pin closed证明，逐批/逐段重查闭合分段身份与旧mtime，fsync intent后按句柄删除，再追加真实结果。原预算、审计、部分失败/软超限及恢复语义不放宽。

后台专用任务保护在同一个SQLite BEGIN IMMEDIATE保留事务内确认项目存在，查询该项目全部任务，再按原双向任务图核祖先/子孙/关系/原生base引用。项目内任一任务未终态、未收取、paused/异常控制、关联缺失/跨项目/引用数据非法，或查询超过1024任务/约100ms预算，均保护共享后台run。无任务项目仅在项目真实存在且完整查询确认空集时可清理。事务持有至精确删除结束，不改任务数据；DB忙即保护。

这是保守的项目共享策略：当前286仍paused，因此本项目已关闭后台日志也会受保护；本片不能据此自动解除286或承诺实际生产有删除。超过1024任务/复杂关系时同样可能长期保留并报告保护，不能伪称预算已达标。未来更精确的后台任务覆盖需另片明确，不在本片猜测归属。

## 自动运行与兼容

沿用原RetentionService线程和生命周期，启动补检、持久daily due、停止事件及有界正常退出。旧角色源先按原路径处理；新后台源独立分组/验证，源配置不可用会留下保护结果，不启用旧writer自删。后台writer继续只分段/软容量提示；新关闭标记本身不启用删除。近期、活跃、旧缺证明、未知项目、跨根/并发变化及依赖未闭环均不删。

新根仅自动删除合格events分段，manifest/closed/lease/rotation/retention审计继续保存计入预算。原角色详情的到期410保持；本片不添加后台单条详情端点。后台下载历史覆盖始终不完整；不得把清理后的零条当作完整无异常。

## 自检与交付状态

已实现通用关闭扩展、后台专用证明/验证、显式开关和项目任务保护；新增22项真实隔离Windows/SQLite测试。首轮把Project主键误写为id，被测试检出并保护性拒绝删除；已更正为project_id，原first-tests.log保留。最终105项联合回归全部通过（22新、27原清理、29后台导出/隐私、27原writer），见coordination/final-regression.log；Codex自检不称独立复核。

真实隔离API采用随机端口51817、正式lifespan启动worker：后台到期闭合与原角色到期分段自动删除，近期/活跃/旧缺证明保留，401/403/后台human200与原角色410正常，关闭后worker/server退出，新API run生成新关闭标记。最终结果见coordination/api-smoke/result.json及api-smoke-final.log。无生产DB/Key/日志/配置写入，无前台清理动作，无造生产closed/policy或改生产mtime。

正式启用需要独立复核完成后提交具体配置及普通重载方案确认。旧322通过不代替本片新删除能力验收，当前生产backend_enabled仍缺省关闭。

## 323独立复核与收尾（2026-10-24）

323原交付complete/result2964，DeepSeek已提交并idle/无当前任务；Codex取件重核30份source/snapshot、852486字节和快照目录exactness均一致，本地/远端完整JSON一致后收取completed。取件未修改产品或重复无关全量回归，原报告及失败材料保留，证据在.tmp/backend-log-auto-retention-v1/coordination/323-acceptance.json及review/。

独立22项新测试22/22、补充taskless/paused286/submitted/不存在与空项目反例、真实隔离API端口60498均通过；独立组合105项为104通过及1个已知私有ACL临时文件cleanup PermissionError，测试体断言通过，不改写为独立105全过。Codex冻结自检105/105及端口51817证据保持。无必须修正项。

六项P3及权限限制保留：配置/缺根/重叠保护结果未持久化；旧角色根不可读会阻止服务整体注册；独立ACL清理受限；smoke的production_changed常量自身不构成生产不变证明；workflow completed/canceled是收取代理；不相连的project_id=NULL旧任务不属于项目图。复核者未读取生产配置正文/DB/Key/私有state/原生会话/日志，生产不变只解析冻结invariant和进程启动时间，未生产HTTP重跑或启用。

323实际续322的session-939f1561-b543-43c1-ab10-c7fff4c951fc，confirmed_count=2，decision=reuse_missing_metrics_fallback；决策时缺数，按可信计数备用，不伪称读到了百分比。末尾快照526519/1000000=52.6519%，基础SHA同315；本次不追加复核用户免验的70%片。

协调方只读启用预检通过：原config SHA仍db98e42d…a8543c，仅新增backend_enabled=true后的候选SHA428c928e…e09825，解析其它字段完全相同，原五来源与项目根存在且不重叠。尚未写生产配置/重载/调用sweep。具体[部署方案](BACKEND_LOG_AUTO_RETENTION_DEPLOYMENT_20261024.md)已准备，仍待本次新删除能力的明确启用确认。

## 323独立复核与收尾（2026-10-24）

323原交付complete/result2964，DeepSeek已提交并idle/无当前任务；Codex取件重核30份source/snapshot、852486字节和快照目录exactness均一致，本地/远端完整JSON一致后收取completed。取件未修改产品或重复无关全量回归，原报告及失败材料保留，证据在.tmp/backend-log-auto-retention-v1/coordination/323-acceptance.json及review/。

独立22项新测试22/22、补充taskless/paused286/submitted/不存在与空项目反例、真实隔离API端口60498均通过；独立组合105项为104通过及1个已知私有ACL临时文件cleanup PermissionError，测试体断言通过，不改写为独立105全过。Codex冻结自检105/105及端口51817证据保持。无必须修正项。

六项P3及权限限制保留：配置/缺根/重叠保护结果未持久化；旧角色根不可读会阻止服务整体注册；独立ACL清理受限；smoke的production_changed常量自身不构成生产不变证明；workflow completed/canceled是收取代理；不相连的project_id=NULL旧任务不属于项目图。复核者未读取生产配置正文/DB/Key/私有state/原生会话/日志，生产不变只解析冻结invariant和进程启动时间，未生产HTTP重跑或启用。

323实际续322的session-939f1561-b543-43c1-ab10-c7fff4c951fc，confirmed_count=2，decision=reuse_missing_metrics_fallback；决策时缺数，按可信计数备用，不伪称读到了百分比。末尾快照526519/1000000=52.6519%，基础SHA同315；本次不追加复核用户免验的70%片。

协调方只读启用预检通过：原config SHA仍db98e42d…a8543c，仅新增backend_enabled=true后的候选SHA428c928e…e09825，解析其它字段完全相同，原五来源与项目根存在且不重叠。尚未写生产配置/重载/调用sweep。具体[部署方案](BACKEND_LOG_AUTO_RETENTION_DEPLOYMENT_20261024.md)已准备，仍待本次新删除能力的明确启用确认。
