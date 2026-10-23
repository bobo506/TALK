# Project Progress

Updated: 2026-10-23 19:46（Asia/Shanghai）。318定向独立复验通过并已收取；317问题全部关闭，原partial及失败证据保留，其收取被自动审批拒绝、仍待明确授权。后台自动日志清理代码已提交0f67794，本轮进度随当前分支推送；生产尚未启用，正式配置/正常重载方案已准备，待用户确认。

## 当前授权与分工

- 用户批准后台每日检查/启动补检、30天保留/单根1GiB软预算，日常无需前台点击或逐次批准。Codex `agent:codex / prj_e8fe7066bbec / lead` 开发及修正，DeepSeek独立复核/定向复验；本次身份已由API核实。
- 项目页面开发要求仍旧文本，本次明确分工优先。Kimi开发暂停、286保护、默认派后结束/用户通知取件和下一新片先确认保持。
- 315→316→317实际同窗，计数1→2→3；317末占用60.171%。318真实decision=new_context_threshold，新session-e067e0e8-da90-4d91-9051-c9a986011b43、first_turn/count1，基础SHA与315一致，末占用31.7806%。后续相容复验优先续该窗，仍服从阈值/失效守卫，不增加自动等待。

## 代码验收与证据

- [已确认范围](spec/LOCAL_LOG_AUTO_RETENTION_REQUIREMENTS_20261023.md)、[实现合同](spec/LOCAL_LOG_AUTO_RETENTION_DESIGN_20261023.md)：Windows按句柄删除，关闭凭据/lease、显式根和精确任务/DB范围保护；非空任务、双向多层依赖、祖先及NULL未知control保护，未知旧run保留。
- API后台每日/启动补检、持久due/重试/停止，根互斥与SQLite非阻塞预约；关闭证据固定，删除前后核对，fsync intent→删除→结果，精确过期ref410。1GiB软预算不提前删近期/活跃/依赖未闭环日志；根policy协调新版writer的旧期限/容量删除。
- 318结果2959 complete/pass；独立132相关回归、27新增测试、5原反例、27复核侧反例及37旧失败项全部通过，F1—F5/P1关闭。33份冻结匹配、317原证据未改、TALK结果与本地JSON一致，见`.tmp/local-log-auto-retention-v1/coordination/318-acceptance.json`及`review-fix1/`。
- 318已于UTC11:41:02正式收取completed。317仍submitted：自动审批以此前“暂不收取”及本次用户只确认318为由拒绝，未重试/绕行；原partial不改，需明确授权才收取。
- 补做正式API lifespan/真实随机端口/隔离SQLite加载自检通过：自动删1个40天旧闭环事件；HTTP410/401/403、近期/活跃保护、daily due及退出worker停止通过。证据`coordination/api-smoke.log`和`api-smoke/result.json`，非生产加载/独立复验。
- 取件后只按复核建议澄清合同“新增事件/普通额外文件”边界，未改产品代码；未重跑已独立通过的全部测试。
- Git代码提交`0f67794f010692c48355b2316642f1f61fe5b07d`，18个明确文件/1442行新增；未包含生产config.toml、临时/私有产物。代码提交后跟踪文件干净，当前分支codex/terminal-return-codex，进度收尾与代码一并推送。

## 正式启用待确认

- [部署方案](spec/LOCAL_LOG_AUTO_RETENTION_DEPLOYMENT_20261023.md)及`coordination/deployment-config.patch`已准备并在内存验证：同一DB改绝对路径，五个现有来源root从成员子目录统一到原总根，项目/成员范围不变；启用30天/1GiB/每日策略。
- 当前API由用户原终端external运行，无法受管reload；需正常drain/重载宿主与角色、用户原终端重启API一次，并按原运行集合普通恢复。任务未结束不强停，不解除owner，不改Key/模型/绑定/历史。
- 新部署按AGENTS具体可审结果后确认；当前生产配置未改、未启停服务/角色、未写生产policy或执行日志删除。代码独立通过不等于生产已启用，未知/旧/无任务run不回填证明。

## 后续

- 完成本片部署验证/验收后再确认其它片；私有输出/后台日志统一导出、全入口21600、删除角色、自启动/退出等仍排队。主被动页面只保存意向，真实主动跟进/生效切换尚未完成，不提前开启。
- 历史见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
