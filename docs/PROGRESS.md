# Project Progress

Updated: 2026-10-16 16:40 (Asia/Shanghai)：254独立复核通过并已收取，后端8源本轮提交发布；后续DeepSeek替代K2.8。前端auto_start接线仍待，未部署/启停真实服务。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本轮MCP实读caller agent:codex/kind=agent，业务lead，已读当前development_requirements。
- 用户最新要求后续DeepSeek代替旧agent:kimi-code-k28-preview；254按原包完成，不追改历史或项目永久开发要求。AGENTS同步：前端Codex实施/DeepSeek独立复核，后端/宿主DeepSeek实施/Codex独立复核，Codex负责正式docs/Git。
- 默认派发后结束等待、用户通知完成后取件；共享目录开发暂停后审查，一次一片。当前未新派下一任务。

## 250/254自动首次启动后端已独立通过

- 原250仍failed/failed、msg2767/原3600秒超时与不合规本地报告保留；不收取/追改250。修正后8源为server/{models,db,role_services,role_provision_requests}.py与tests/test_role_{auto_start,services,provision_requests,policy_migration}.py。
- 根已在250轮独立实读全部8源与合同、完成121/151隔离回归；254仅两白名单源定向修正，其余173源逐SHA不变，原8源副本/旧根失败证据保持。
- F1/P1闭合：保存点rollback后核driver真实事务仍在、同事务内已flush provisioned事实可读，才允许局部failed/auto_start_enqueue_failed；RAISE(ROLLBACK)/连接失效上抛500整体回滚，不另起事务补写。F2/P2先注册再PATCH200并核external_session，重复注册409零写，unknown用例保留。
- 本轮根独立63/63相关模块与原9/9 API/SQLite边界通过，0失败/错误/跳过；RAISE(ABORT)保留provisioned，RAISE(ROLLBACK)500/created/pending/revision3保持，去故障同token重试200/enqueued且恰1launch+1state；锚点/commit故障、双HTTP/WAL、人工意图及旧库迁移通过。8源py_compile/diff与175基线文件审查前后SHA通过。开发者273/9与根旧272分别保留，不重复累计。
- 交付msg2779 task_id=254校验通过，独立裁决msg2780；UTC08:40:06.478883收取，succeeded/completed。证据.tmp/k28-autostart-slice/independent-review254/{review.json,focused/,boundary-probes.json,lost-outer-transaction.json,freeze.json,collection.json,publication.json}。
- 仅后端代码验收与Git发布；前端尚未发auto_start，不将新页面保存配置声称已自动启动。没有生产DB/真实Key/CLI/模型/常驻服务启停、能力修改或Browser操作，unknown/unverified/实际ready守卫保持。

## 下一步：当前功能前端接线

- 按ROLE_AUTO_START_DESIGN.md对接新create显式auto_start、配置/入队/实际ready分开的页面反馈；Codex实施、DeepSeek独立复核及用户验收。旧请求/recover不补意图，人工关闭优先，幂等/指纹合同不变。
- 本轮后端切片先完成Git收尾后暂停汇总，不同时启动日志、角色迁移、全角色预算或删除功能。后续恢复仍先完成自动首次启动功能。

## 已确认后续需求（待实施）

- 完整异常日志需脱敏持久保存异常类/消息/完整堆栈/因果链与阶段/时间/项目/角色/实例/任务关联，跨重启可追查，公共入口有界摘要/引用；定位、轮换/容量方案实施时明确。旧K2.8原记录只有task queue worker failed:，最初触发原因未知；父进程存活不代表接单循环健康。
- 存量Codex/Kimi/DeepSeek/旧K2.8等保留member_id/绑定/历史，空闲正常停旧入口后迁入统一宿主，补真实配方/能力登记/owner和launch关联，逐个验真实启动/关闭/再启动/接单；不凭PID接管或放开unknown/unverified。详spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md。
- 全角色默认21600秒及可显式覆盖、角色详情删除按钮待实施；删除本项目角色配置/专属材料，历史任务/消息/成果保留，删除一个K2.8不影响另一个，再需要须重新创建；共享模型/原生登录/其它项目不动。详spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md。手动关闭完成→启动为恢复路径，自动重启/随项目启动另行设计。

## 保留事实

- 253→248→246已收取，revision-2本机零模型入口准备通过，详历史与.tmp/k28-new-role-trial-prep/revision-2/final253/。原稿/原失败/253 task_id格式整理来源保留；仅Windows10本地files专用runner，35/11独立验证通过，不冒充产品pipes。实际客户端T未知、W未启用，临时CLI600/整体900；真实新Kimi/模型/开发能力/原生退出及主动等待未验，不自动开真实新角色任务。
- 252旧K2.8六小时入口已发布79096ad，旧实例实际执行预算本轮未从启动日志核实，不声称21600实测。用户此前重启后254已接单只证明本次接单恢复；外部旧CLI尚无受管owner/launch，不能当成页面已可重启该实例。
- 251发起人标签发布84b8010、六资源20261016-task-initiator-label；静态字节已核，人工视觉反馈待。页面5de19e8此前整体通过，不外推本次小修或真实原生能力。
- 本轮只收254、发布已审8源与相关docs，不暂存其它未跟踪材料。精确配额未读取，不臆测比例；恢复说“继续项目”。
