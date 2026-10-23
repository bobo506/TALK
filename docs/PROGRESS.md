# Project Progress

Updated: 2026-10-23 20:30（Asia/Shanghai）。用户已重启API，生产后台首次检查complete：454个缺证旧run保护、删除0、约508MiB未超1GiB，next_check为次日。新API/七宿主正常，已普通start恢复唯一原running的DeepSeek，其余六个保持stopped。39份部署材料冻结，319已交DeepSeek独立部署复核，产品修改暂停；实际续318窗待回执，不称独立部署最终通过。

## 当前授权与分工

- 用户批准后台每日检查/启动补检、30天保留/单根1GiB软预算，日常无需前台点击或逐次批准。Codex `agent:codex / prj_e8fe7066bbec / lead` 开发及修正，DeepSeek独立复核/定向复验；本次身份已由API核实。
- 项目页面开发要求仍旧文本，本次明确分工优先。Kimi开发暂停、286保护、默认派后结束/用户通知取件和下一新片先确认保持。
- 315→316→317实际同窗，计数1→2→3；317末占用60.171%。318真实decision=new_context_threshold，新session-e067e0e8-da90-4d91-9051-c9a986011b43、first_turn/count1，基础SHA与315一致，末占用31.7806%。后续相容复验优先续该窗，仍服从阈值/失效守卫，不增加自动等待。

## 代码验收与证据

- [已确认范围](spec/LOCAL_LOG_AUTO_RETENTION_REQUIREMENTS_20261023.md)、[实现合同](spec/LOCAL_LOG_AUTO_RETENTION_DESIGN_20261023.md)：Windows按句柄删除，关闭凭据/lease、显式根和精确任务/DB范围保护；非空任务、双向多层依赖、祖先及NULL未知control保护，未知旧run保留。
- API后台每日/启动补检、持久due/重试/停止，根互斥与SQLite非阻塞预约；关闭证据固定，删除前后核对，fsync intent→删除→结果，精确过期ref410。1GiB软预算不提前删近期/活跃/依赖未闭环日志；根policy协调新版writer的旧期限/容量删除。
- 318结果2959 complete/pass；独立132相关回归、27新增测试、5原反例、27复核侧反例及37旧失败项全部通过，F1—F5/P1关闭。33份冻结匹配、317原证据未改、TALK结果与本地JSON一致，见`.tmp/local-log-auto-retention-v1/coordination/318-acceptance.json`及`review-fix1/`。
- 318已于UTC11:41:02收取completed；317原收取被自动审批拒绝后，用户明确“授权收取317，保留原结论”，已于UTC12:00:49正式收取completed，结果2958/conclusion partial不改。原拒绝/失败证据均保留，未绕行。
- 补做正式API lifespan/真实随机端口/隔离SQLite加载自检通过：自动删1个40天旧闭环事件；HTTP410/401/403、近期/活跃保护、daily due及退出worker停止通过。证据`coordination/api-smoke.log`和`api-smoke/result.json`，非生产加载/独立复验。
- 取件后只按复核建议澄清合同“新增事件/普通额外文件”边界，未改产品代码；未重跑已独立通过的全部测试。
- Git代码提交`0f67794f010692c48355b2316642f1f61fe5b07d`，18个明确文件/1442行新增；未包含生产config.toml、临时/私有产物。代码提交后跟踪文件干净，当前分支codex/terminal-return-codex，进度收尾与代码一并推送。

## 正式启用已加载：319独立部署复核中

- 用户确认“确认启用并正常重载”。检查无running任务、worker空闲、DeepSeek真实idle/心跳新鲜；原集合为DeepSeek running、其它六个stopped，完整快照`coordination/deployment-before.json`。原统一入口普通stop，原Popen逐项drain；UTC12:04:53 runtime stopped/随后进程absent，角色均无owner/can_start，无强杀或恢复CAS。
- UTC12:05:20原配置CAS核验后原子应用[批准方案](spec/LOCAL_LOG_AUTO_RETENTION_DEPLOYMENT_20261023.md)：同DB绝对路径、五条来源统一原总根且project/member不变、30天/1GiB/86400秒enabled。旧SHA b839cdea…→新3654bdc3…，其它配置完全相同；证据`deployment-config-applied.json`。
- 用户回复“已重新启动”后实核API health/DB/storage ok，新runtime14584、七manager serving。后台自行写根policy及state：UTC12:20:23.836218 complete/errors空/deleted0/legacy_or_unclosed保护454，observed532532295字节、capacity_scan complete、over_budget false，next_check1792844423.836218即次日UTC12:20:23；核验helper未调用sweep/手写控制证据。
- 仅普通start恢复DSH gen54/ins_057877d1df52/PID8652，running/ready/idle，实际心跳12:22:09→12:26:10；另六角色仍stopped/无owner。新bridge manifest身份/PID匹配、run.lease第二写句柄errno32、closed不存在，活跃写入器已加载，不靠停角色造凭据。
- 真实人类摘要HTTP200/scope正确/2条，但scan.complete=false/truncated=true、扫描133480910字节、unavailable_sources1，约8.078秒；只作为部分查询，不能说全量查询通过。辅助HTTP预算由误用host5秒改为日志扫描10秒+5秒余量15秒，未改产品预算或扫描逻辑。
- 证据`coordination/deployment-{loaded,restored,heartbeat,producer}.json`及`deployment-producer-check.log`；39份/339596字节冻结于deployment-baseline（12公开源/24证据/3精确生产元数据）。319已queued/assigned交DeepSeek独立核实际配置/后台保护/due/恢复和限制；只读精确控制JSON/新run元数据，不读事件正文/私有Key。沿base315/同continuity_key请求续318窗，实际回执待验，默认用户通知319后取件，不主动等待。
- 代码0f67794、进度4d3d781、批准配置/正常drain记录9ad18ca已推送；本轮只有正式加载文档增补，Python产品未改。生产配置/角色仍按授权保持；旧/未知run不回填证明，模型/Key/绑定/286及历史不追改。30天长期运行/未来删除/生产410未实跑，不外推。

## 后续

- 完成本片部署验证/验收后再确认其它片；私有输出/后台日志统一导出、全入口21600、删除角色、自启动/退出等仍排队。主被动页面只保存意向，真实主动跟进/生效切换尚未完成，不提前开启。
- 历史见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
