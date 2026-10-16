# Project Progress

Updated: 2026-10-16 14:06 (Asia/Shanghai)：用户要求先汇总后重开窗口；已核246/248仍有验收尾项，下一步优先补248再按248→246收取。252已发布，250源保持未验。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本会话caller已实读agent:codex/kind=agent。当前用户指定Codex与旧agent:kimi-code-k28-preview协作，不派DeepSeek；永久development_requirements未改。
- 252由Codex实施、旧K2.8独立复核后已收取并发布。用户随后要求核246/248并同意继续下一步，再明确先汇总重开窗口；本轮尚未开始返修、没有新派任务或启动真实实例。继续时按已有授权由Codex补正、旧K2.8独立复核，不重复询问同一开发授权。

## 252预算补正已通过

- 旧K2.8入口/PS1与JSON模板/测试/局部指南5文件默认21600秒，check/render/launch --timeout可覆盖正整数秒并贯通报告、门禁与bridge argv。开发者196测试通过；252独立70项及针对性探针通过，不重叠累计；无真实6小时长任务、模型、重启或宿主T/W验收。
- msg2772为合法JSON围栏报告，MCP业务complete/task252匹配；稳定原文SHA与本地交付完全相同，核5候选patch/SHA、134保护源与250八源均未漂移，已于UTC 2026-10-16T03:09:30.779510收取completed。
- 指南基线原字节SHA与Git/before副本差异为CRLF/LF，根用Git blob重建CRLF恰等原账本，非内容漂移；原报告不改。报告误称“250开发候选”，实际核的是5预算文件，不是250后端。指南旧固定分级描述与PS5.1模板编码限制另记，推荐Python入口重启，详见.tmp/k28-timeout-six-hours/final/audit.json。
- 旧运行实例仍沿用3600，空闲停原入口后在TALK目录用原环境 python scripts/kimi_k28_executor.py launch --timeout 21600 重启才生效。其本人Key仍由原仓库外文件/环境解析；截至上次检查未重启，本轮也未重启或恢复失败任务。其他角色通用默认仍600，DeepSeek实核启动3600，不能说全部统一。

## 已确认后续需求

- [正式需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：所有TALK角色存量/新建、手动/受管/自动入口默认单次CLI执行21600，可显式覆盖；迁移须检查旧3600参数。不是服务寿命、排队到收尾总时长、MCP客户端或读取等待，其他入口尚未改。
- 角色详情启动/关闭旁增“删除角色”，删本项目角色配置/绑定/本人档/专属Key与恢复元数据，历史任务/消息/成果/归属保留。用户明确两个K2.8删其中一个不影响另一个，以后只能重新点“创建角色”添加新角色；共享模型/原生登录/其它项目不动。
- 用户手册“待上线”区及开发者启动指南已同步，替代旧§9.3/I20保留完整配置的归档方向；human-only、在途保护/所有权与跨项目隔离保持。删除按钮尚未开发，不能把本轮澄清当实际删除或全角色统一生效。

## 恢复后先补248（用户已同意继续，现按要求先收工）

- 刚核MCP：246/msg2751、248/msg2764均succeeded/submitted，业务complete只是合法自报，尚未收取；不是忘记确认。246原入口误处理全队列、缺task-id/异常任务结构仍放行等已交248返修，原文件和交付保留。
- 248 revision-1通过35项零模型检查，之前Codex独立35/35也通过，单任务隔离/fail-closed/直接子句柄回收已改善，但原包第5条要求整体deadline覆盖只读预检/领取/CLI/清理；实际amain先独立做只读预检，_execute_single_task第648–649行才重新计时，第772及finally清理/离线回报也需统一预算，不能宣称全流程硬上限。原任务/实际代码已重核，当前问题仍在。
- 原包第4条要求实际拥有的CLI回收并说明Windows边界；F3明确只清直接子进程、假CLI额外派生进程仍存活。不得把此边界说成整个进程树已清理；真实新Kimi入口准入仍保留，未启动真实CLI/模型，也未改unknown/unverified。
- 接手只在新revision目录保存补正，保留.tmp/k28-new-role-trial-prep/及revision-1/原稿/证据。本轮另存.tmp/handoff-20261016/revision-1-before-resume.json作恢复基线；不动250八个未验源。先用假时钟/慢预检验证同一全局截止，再用零模型CLI/本人句柄/派生进程与sentinel验证清理，不能按镜像名批量结束或用真实Key/模型冒充测试。
- 修正自测后读最新development_requirements，按本次Codex开发/旧K2.8独立复核派一个明确任务；以实际返回号为准，本轮没有创建后续任务号。独立通过后先收新复核，再按248→246收取，不追改原交付。默认派发结束、等用户完成通知再取件，不主动轮询。

## 保留事实与下一步

- 250于08:56→09:56约3600秒failed/failed，msg2767为执行超时；4server+4tests保存在.tmp/k28-autostart-slice/recovery-250/，8源SHA未改，仍未独立验收/收取/提交。自报121+151测试及JSON超长问题保留；252不修复或替代250，后端自动启动未上线。
- 251已收取并发布84b8010，详情仅“发起人 XXX”，六资源20261016-task-initiator-label，静态GET200字节一致；用户Ctrl+F5视觉验收仍待。页面业务5de19e8此前已整体人工通过，不外推本次小修或原生能力。
- 249/247方案已收取，正式ROLE_AUTO_START_DESIGN.md保持；248/246新角色入口未收取（整体硬预算/孙进程边界），新Kimi k2.8未启动，unknown/unverified控制边界不改。
- 最新优先级按用户“继续下一步”承接上节248补正；随后继续250保留源码独立审查。旧K2.8重启生效/UI251视觉反馈、全角色预算统一与删除按钮均仍待，不在修入口期间同时开工。重开窗口输入“继续项目”恢复本节；本次仅3份正式docs收尾，无产品改码/新派发/任务收取或实例操作。精确配额未读取，不臆测比例；252发布见.tmp/k28-timeout-six-hours/final/publication.json，本次交接见.tmp/handoff-20261016/publication.json。
