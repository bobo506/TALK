# Project Progress

Updated: 2026-10-23 20:06（Asia/Shanghai）。用户已明确授权正式启用/正常重载及收取317；317已收取completed，原partial不改。旧统一宿主/七manager已正常drain退出、角色均stopped/无owner；仅DeepSeek原先running。已按批准差异应用生产配置、只读构造预检通过；等待用户在原终端重启API，随后核后台实际生效并仅恢复DeepSeek。无需再次询问本片部署授权。

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

## 正式启用进行中：待用户重启API

- 用户确认“确认启用并正常重载”。检查无running任务、worker空闲、DeepSeek真实idle/心跳新鲜；原集合为DeepSeek running、其它六个stopped，完整快照`coordination/deployment-before.json`。原统一入口普通stop，原Popen逐项drain；UTC12:04:53 runtime stopped/随后进程absent，角色均无owner/can_start，无强杀或恢复CAS。
- UTC12:05:20原配置CAS核验后原子应用[批准方案](spec/LOCAL_LOG_AUTO_RETENTION_DEPLOYMENT_20261023.md)：同DB绝对路径、五条来源统一原总根且project/member不变、30天/1GiB/86400秒enabled。旧SHA b839cdea…→新3654bdc3…，其它配置完全相同；证据`deployment-config-applied.json`。
- 实际配置构造RetentionService只读预检pass：1根/5范围/策略正确、未建线程/未连接DB/未sweep，证据`deployment-preflight.json`。当前旧API仍使用重启前配置；未写生产policy或执行日志删除，不能称worker已生效。
- 已请求用户在启动API的原终端Ctrl+C正常退出并重跑原命令，选择“已重新启动”。该API为external，未按PID接管/强杀。收到回复后核新版API/宿主、根policy/due/保护摘要，再通过普通start只恢复DeepSeek，其余六个保持stopped；模型/Key/绑定/286及历史保持。
- 代码及进度0f67794/4d3d781已推送；本轮生产配置与上述部署进度提交保存。用户重启前不派DeepSeek复核任务（角色目前正常停止），加载后必要独立复验优先沿318同原生窗口请求。

## 后续

- 完成本片部署验证/验收后再确认其它片；私有输出/后台日志统一导出、全入口21600、删除角色、自启动/退出等仍排队。主被动页面只保存意向，真实主动跟进/生效切换尚未完成，不提前开启。
- 历史见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
