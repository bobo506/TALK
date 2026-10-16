# Project Progress

Updated: 2026-10-16 15:13 (Asia/Shanghai)：用户重启旧K2.8后254已在15:09由新实例领取、心跳推进，继续原包返修。旧实例14:57队列异常仅泛化错误，最初原因未定；本轮只读诊断/记录，不打断或重派。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；当前会话caller已实读agent:codex/kind=agent，业务lead。沿用户明确本轮Codex与旧agent:kimi-code-k28-preview协作，不派DeepSeek，永久development_requirements不改。
- 用户本轮“继续”授权按顺序独立审250。Codex负责独立实际代码复核/裁决及正式docs/Git，旧K2.8负责254定向返修；根审查已暂停，不并行改源码。默认等用户“254好了”后取件，不主动轮询。

## 248入口准备已闭合（253→248→246均completed）

- 本机可用准备件为.tmp/k28-new-role-trial-prep/revision-2/；原246/248稿、revision-1/原失败与原交付保留。9候选逐SHA与开发冻结清单一致，152源码/脚本/测试资源及280原件逐SHA均0漂移，包含250八源。
- 单一Deadline从amain入口覆盖预检/注册/竞争复查/命令生成/领取/CLI至Job回收/offline/终态读取/close；清理只用同一end余额，不再后置重置预算。CLI以JOB_LIST原子建入本次私有Windows Job，限定stdio句柄继承/KILL_ON_JOB_CLOSE/无breakaway，失败不回退到无Job；正常/错误/超时/取消均回收Job成员与派生进程，独立sentinel存活。
- 253独立实读代码，并隔离输出重跑35/35回归（17.44秒）与11/11新增探针；慢预检与预检+注册约6秒，慢offline/快照/close约8.015秒受8秒总预算约束，4种假CLI+孙进程场景active_after=0。根核独立驱动与实际证据/保护SHA，通过本次准备验收；不叠加开发者/旧轮测试，不无故重跑。
- 253原msg2774把task_id误填talk-delivery-1，MCP原invalid保持。原本地strip后的SHA=50090146b5b02f644536853130dfc5d7bbaf23ec67842efcb6b71d25d78187aa与稳定MCP正文一致。协调方仅在final253/review-normalized.json整理task_id=253，其他九字段相同，expect-task-id校验通过，normalization-audit.json留痕；不是复核者重新提交，不追改原文。Codex基于独立材料裁决，Hall决策msg2776。
- UTC2026-10-16 06:48:30/32/34按253→248→246收取，三项workflow_status=completed；回执final253/collection-receipts.json。原253格式错误与246/248自报不因收取被重写成原稿已正确；实际准入准备以revision-2和253独立证据为准。
- 本次仅零模型/假API+假CLI准备通过；Windows10+本地files专用runner，产品bridge未改，不冒充产品pipes。同步OS/磁盘阻塞不是硬实时保证，不承诺broker代创建/恶意逃逸。真实客户端T未知、W未启用，未启动真实新Kimi/模型/worker/服务、未领取真实任务；unknown/unverified保持。临时CLI600/整体900沿原包，全角色21600另片。候选存本机.tmp未纳入产品发布包，原README冻结开发时状态，验收以本节及final253记录为准。

## 250独立复核需修正，254已派

- 原250仍failed/failed、msg2767（3600秒执行超时）；原本地交付verification[1].check超长，原结果/报告不追改，不收取/提交/回滚或自动恢复250。原8源与recovery-250账本完全相符，根在.tmp/k28-autostart-slice/independent-review250/before/保存8个逐字节副本；独立审查开始/派发前175源SHA零漂移，基线60f468c88cd5340a39c6143dc68c6ca6687c64ee。
- 根独立实读全部8源差异/合同/测试，实际121/121+151/151隔离回归（0失败/错误/跳过）、8源py_compile/diff与共享指纹AST不变通过；新增9项实际API/SQLite边界8通过1失败，后仅重现同一失败1项，不重复累计。证据本机independent-review250/{review.md,review.json,static-audit.json,batch1/,batch2/,boundary-probes-initial.json,lost-outer-transaction.json}。
- **F1/P1阻塞**：role_provision_requests.py:1493–1502入队宽泛catch后savepoint.rollback未证明外层SQLite事务有效；launch INSERT触发RAISE(ROLLBACK)撤销全部事务时，后续Core失败状态写会另起事务并commit，实际HTTP200/status=created/auto_start_status=failed，配置终态未落库。应500、旧created/pending/revision/lease等保持且无state/launch/anchor；不能新事务补写。去故障原token/revision实测可重试200/enqueued/恰1launch。原RAISE(ABORT)局部回滚应继续200/provisioned+auto failed；不得依据异常字符串分类或盲重试。
- **F2/P2夹具**：test_external_session在运行器注册前PATCH且不核404，随后注册默认unknown，未实际覆盖external。应先注册再设置、核PATCH200与实际类型。根用真实external路径已独立通过，需修测试，不放宽业务门控。入队后锚点写失败/commit失败回滚、双HTTP/WAL只入队一次、manual start+stop前置优先、auto claimed原owner保留、true意图退役目录精确重放、6种旧请求状态迁移等独立探针已通过。
- 派发前再读最新development_requirements/caller=agent:codex/kind=agent，旧K2.8无running/queued任务；实例最新上报error/current_task_id=null（UTC06:57:48），本机PID14308存在，不能据此说在线正常/已接单。254最小四参数独立顶层派旧agent:kimi-code-k28-preview，Hall group:task-8eed20fe57e346c49781b4a9360d2306，初始queued/assigned；本轮未重启/轮询。
- 254只准改server/role_provision_requests.py和tests/test_role_auto_start.py，证据写development/revision-1/，其它173源及原副本/根证据保持；原需求/实际基线/精确F1/F2/272旧证据/9边界/原代码负向与新代码验证要求/纯JSON本次实际任务号交付入包。开发者完成暂停，根再独立审修正差异和必要模块/故障验证；通过才收254并收尾产品源码，原250失败历史保留。不提前新派前端或真实新角色任务。

## 254重启后已接单，旧入口接单异常另记

- 用户报告旧K2.8重启后已接单，MCP/只读DB确认254 running/in_progress，新实例agent:kimi-code-k28-preview:3243afbc-674e-48b0-96e8-f5cb0fb9af45 / PID12532，UTC07:09:08.214304领取，心跳持续推进。本轮不停止/重新派发，不重启任何实例，不改共享源码。
- 旧实例8ddd72cf…/PID14308最后UTC06:57:48.398775为error、current_task_id=null，last_error恰为task queue worker failed:（后面无异常文本）。派发前进程存在只说明主进程在；当前记录不能证明当时队列仍正常运行。
- 静态诊断发现队列异常仅记录str(exc)，未保存异常类/堆栈；run_bridge创建后台队列task后仅等待client.run，没有独立监控worker退出，error上报本身若失败可令worker退出而父进程留存。以上是可能的卡接单机制，尚未证明本次worker确已退出/阻塞/长时间持锁，最初触发是超时/连接还是其它亦未知，不能把推断写成确定根因。
- 诊断证据.tmp/k28-runtime-diagnostic-20261016/diagnostic.json；本轮只读确切旧实例错误与当前254必要字段，未读Key/USER/native配置或输出完整日志。接单恢复/异常记录与worker监督另列后续缺口，不在254改码期间修。重启实际执行预算未从日志核实，不声称21600已实测生效。

## 保留事实与下一步

- 首要等“254好了”读取交付（254已由新实例领取，不重复派发）；需同时闭合普通保存点失败与外层事务丢失分类。250自动启动后端未验收/上线，前端auto_start载荷/文案亦未接线；249/247正式ROLE_AUTO_START_DESIGN.md保持，勿改合同迁就故障。
- 253→248→246已收取，revision-2本机零模型入口准备通过；真实新Kimi/模型/开发能力/实际客户端T-W/原生退出未验，unknown/unverified保持。真实小型新角色任务需明确任务与执行授权，默认不自动开启。
- 252旧K2.8六小时入口已发布79096ad；旧运行实例上次仍3600，空闲按原环境python scripts/kimi_k28_executor.py launch --timeout 21600重启才生效，本轮未重启，不声称真实六小时或宿主主动等待通过。
- 全角色默认21600与删除角色按钮仍待实施，详[正式需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)。删除本项目角色配置/专属接入材料，历史任务/消息/成果/归属保留，两个K2.8删除一个不影响另一个，再需要重新“创建角色”；共享模型/原生登录/其它项目不动，手册待上线区保持。
- 251已收取发布84b8010，详情仅“发起人 XXX”、六资源20261016-task-initiator-label；静态字节已核，人工视觉反馈仍待。页面业务5de19e8此前已整体通过，不外推本次小修或原生能力。
- 本轮根无产品改码，仅相关5份正式docs记录独立复核/返修派发并提交推送。254派发后可能只改其白名单两源，不能将工作区现有差异误暂存；其余173源保护与Git回执见independent-review250/publication.json。精确配额本轮未读取，不臆测比例。重开说“继续项目”先查本节，不重复根272测试或同时开启别的功能。
