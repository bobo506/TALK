# Project Progress

Updated: 2026-10-16 14:25 (Asia/Shanghai)：248 revision-2补正及零模型自测完成，253已交旧K2.8独立只读复核；开发候选冻结，248/246尚未收取，250八源保持未验。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本会话caller已实读agent:codex/kind=agent。当前用户指定Codex与旧agent:kimi-code-k28-preview协作，不派DeepSeek；永久development_requirements未改。
- 已按上轮用户“继续下一步”授权承接248补正：本轮Codex开发仅写新revision-2，旧K2.8独立复核任务253已派。共享候选停止修改；协调方只维护正式进度/Git。默认结束等待，用户通知“253好了”后取件，不主动轮询或另开切片。

## 252预算补正已通过

- 旧K2.8入口/PS1与JSON模板/测试/局部指南5文件默认21600秒，check/render/launch --timeout可覆盖正整数秒并贯通报告、门禁与bridge argv。开发者196测试通过；252独立70项及针对性探针通过，不重叠累计；无真实6小时长任务、模型、重启或宿主T/W验收。
- msg2772为合法JSON围栏报告，MCP业务complete/task252匹配；稳定原文SHA与本地交付完全相同，核5候选patch/SHA、134保护源与250八源均未漂移，已于UTC 2026-10-16T03:09:30.779510收取completed。
- 指南基线原字节SHA与Git/before副本差异为CRLF/LF，根用Git blob重建CRLF恰等原账本，非内容漂移；原报告不改。报告误称“250开发候选”，实际核的是5预算文件，不是250后端。指南旧固定分级描述与PS5.1模板编码限制另记，推荐Python入口重启，详见.tmp/k28-timeout-six-hours/final/audit.json。
- 旧运行实例仍沿用3600，空闲停原入口后在TALK目录用原环境 python scripts/kimi_k28_executor.py launch --timeout 21600 重启才生效。其本人Key仍由原仓库外文件/环境解析；截至上次检查未重启，本轮也未重启或恢复失败任务。其他角色通用默认仍600，DeepSeek实核启动3600，不能说全部统一。

## 已确认后续需求

- [正式需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：所有TALK角色存量/新建、手动/受管/自动入口默认单次CLI执行21600，可显式覆盖；迁移须检查旧3600参数。不是服务寿命、排队到收尾总时长、MCP客户端或读取等待，其他入口尚未改。
- 角色详情启动/关闭旁增“删除角色”，删本项目角色配置/绑定/本人档/专属Key与恢复元数据，历史任务/消息/成果/归属保留。用户明确两个K2.8删其中一个不影响另一个，以后只能重新点“创建角色”添加新角色；共享模型/原生登录/其它项目不动。
- 用户手册“待上线”区及开发者启动指南已同步，替代旧§9.3/I20保留完整配置的归档方向；human-only、在途保护/所有权与跨项目隔离保持。删除按钮尚未开发，不能把本轮澄清当实际删除或全角色统一生效。

## 248 revision-2候选完成，253独立复核中

- 原248/msg2764与246/msg2751保持succeeded/submitted未收取；原完整任务/失败/自报及revision-1均保留。候选在.tmp/k28-new-role-trial-prep/revision-2/；基线efbe9a1322dc58e878a5c361c4d4979fa618e76d，开始快照152源码/脚本/测试资源与280个revision-1原件/证据，结束逐SHA均0漂移，含250八源。
- 原预检后重新计时/收尾独立预算已在候选修正：amain只建一次Deadline，预检、注册、实例竞争复查、命令生成与handle共用work_end；Job回收、offline、终态快照、close只拿同一end剩余预算，无余额则不发新请求。异步预算含系统调度余量，不宣称同步OS/磁盘任意阻塞下硬实时零超差。
- 原仅直接CLI回收改为本次私有Windows Job：CreateProcess以JOB_LIST原子建入，限定stdio句柄继承、KILL_ON_JOB_CLOSE且不允许breakaway；正常根退出/错误/取消/超时均收Job后代，无Job则拒绝启动。只清本人Job，不按名称/外部PID处理；files专用runner不冒充产品pipes，不保证外部broker/恶意逃逸。产品源码/unknown/unverified不改。
- 最终开发者重新运行35/35回归与11/11新增探针全部通过，不与原248旧证据累计。新增涵盖假时钟、8秒预算/2秒清理的慢预检约6秒、预检+注册约6秒、慢offline/快照/close约8.016秒；正常/错误/超时/取消的假CLI和孙进程都active_after=0，独立sentinel存活，Job属性失效时不spawn。没有真实模型/CLI/服务/claim或实际T/W验收。详developer-summary.json与evidence/。
- 派发前再读最新development_requirements/caller=agent:codex/kind=agent，并核旧K2.8无running/queued任务（旧实例idle上报仍可能滞后）。253四参数独立顶层派旧agent:kimi-code-k28-preview，Hall group:task-280a593b442149049675084c215ca975；随包含原需求/实际基线/9候选SHA/差异/验证/限制与只读验收，候选已冻结。msg2773纠正任务包短基线efbe9a12笔误为efbe9a1、完整值同上；回执显示in_progress，后续未轮询。独立材料仅.tmp/k28-single-entry-revision2-review/。
- 默认等“253好了”读取交付摘要并按实际代码/证据裁决。通过后先收253，再按248→246收取，不追改原报告；然后回250独立审查。当前不收取/部署，不启动真实新Kimi、不重启旧实例，不实现全角色21600或删除按钮。

## 保留事实与下一步

- 250于08:56→09:56约3600秒failed/failed，msg2767为执行超时；4server+4tests保存在.tmp/k28-autostart-slice/recovery-250/，8源SHA未改，仍未独立验收/收取/提交。自报121+151测试及JSON超长问题保留；252不修复或替代250，后端自动启动未上线。
- 251已收取并发布84b8010，详情仅“发起人 XXX”，六资源20261016-task-initiator-label，静态GET200字节一致；用户Ctrl+F5视觉验收仍待。页面业务5de19e8此前已整体人工通过，不外推本次小修或原生能力。
- 249/247方案已收取，正式ROLE_AUTO_START_DESIGN.md保持；248/246新角色入口未收取（revision-2预算/Job补正候选待253独立复核），新Kimi k2.8未启动，unknown/unverified控制边界不改。
- 最新优先级等253独立复核；通过后收253→248→246，随后继续250保留源码独立审查。旧K2.8重启生效/UI251视觉反馈、全角色预算统一与删除按钮均仍待，不在修入口期间同时开工。重开窗口输入“继续项目”恢复本节；本次临时准备补正与253派发已完成，仅3份正式docs提交收尾；无产品改码/任务收取或生产实例操作。精确配额未读取，不臆测比例；252发布见.tmp/k28-timeout-six-hours/final/publication.json，前轮交接见.tmp/handoff-20261016/publication.json，本次253派发与Git见.tmp/k28-new-role-trial-prep/revision-2/dispatch.json及publication.json。
