# Project Progress

Updated: 2026-10-16 11:04 (Asia/Shanghai)：用户确认所有角色启动默认6小时及删除角色清配置/留历史任务，需求与操作手册已记录；本轮只文档，252原包待复核，250源保留未验。

## 当前事实

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex，caller实读agent:codex/kind=agent。当前用户授权Codex与旧agent:kimi-code-k28-preview协作，不派DeepSeek；永久development_requirements未改。
- 页面业务5de19e8此前已获整体验收。本次小修仅详情顶部“负责人…·…发起”改为“发起人 <created_by展示名>”，本人也显姓名；角色页/列表/分工/权限/真实target不改。六资源20261016-task-initiator-label，静态无需重启。
- 250于08:56:19→09:56:20（UTC+8）failed/failed，msg2767为桥接timed_out文案，与入口3600秒预算吻合；没有向TALK提交有效结构化结果。250不是251的前序重试链：251是用户后来提出的独立页面小修复核，失败前已排队。
- 250本地留下4 server+4 tests（7跟踪修改、1新增），原样UTF-8副本及8源SHA见.tmp/k28-autostart-slice/recovery-250/。本地自报complete/121+151 unittest日志不等于独立通过，JSON还有verification[1].check超长（220>120），原报告/失败状态均保留，250未收取。
- 旧K2.8实例完成251后idle/无current_task，消息2768确认暂停；2770明确失败后保持暂停、旧继续指令不作恢复250授权。252只授权预算候选的独立只读复核，不恢复250写入。Codex合入UI及本片修改前后8后端SHA一致，没有提交、回滚或更改250代码。

## 新确认需求已记录（待实施）

- [ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：所有TALK角色（存量/新建、手动/受管/自动启动）统一默认单次CLI预算21600秒，可显式覆盖更长；旧3600启动参数需同步检查。不是MCP读取/客户端/服务寿命或排队到收尾总时长，本轮没改任何默认或重启实例。
- 角色详情“启动/关闭”旁新增“删除角色”：从当前项目移除，清理角色配置/绑定/本人档/专属Key及恢复元数据；历史任务/消息/成果与归属保留，之后只能重新添加并获新身份。替代旧§9.3/I20保留配置的归档方向；human-only、在途先处理、共享资源/其它项目隔离保持，删除功能未实施。
- 用户操作手册以明确“待上线”区记录两项，开发者启动指南及生命周期合同/计划入口同步，未提前写成当前可点击步骤。252的5候选及250八源继续原样保护，不向正在复核者追加开发，不新派任务。当前DeepSeek进程只读实核--timeout3600、K3记录PID未运行；这不是所有角色已统一的证明。

## 252执行预算候选待独立复核

- 用户因250超时提出提高执行上限，并明确默认6小时。Codex仅修改旧K2.8独立入口、PowerShell/JSON模板、对应测试与局部指南5文件：默认21600，check/render/launch可用--timeout指定正整数秒，模板-TimeoutSeconds同值转发；检查报告/门禁/argv一致。通用bridge默认600、HTTP15与TALK读取等待不变。
- 196 unittest零失败/错误/跳过，覆盖默认6小时、43200/86400覆盖、非法值先拒与dry-run；PowerShell AST零错误/两条转发一致，diff检查通过。初次新增测试fixture缺USERPROFILE导致1错误，临时用户目录修正后通过，原失败记录保留。无真实模型/启动/六小时实跑或主动等待验收。
- 候选基线84b8010、134跟踪源码保护与250八源SHA、原5文件/patch/测试见.tmp/k28-timeout-six-hours/。候选未提交发布；实际运行实例仍旧启动值，不热更新或自动恢复失败任务。
- 派发前实读caller agent:codex/kind=agent、最新development_requirements与旧K2.8 idle/无current_task（上报非心跳实证），按本次明确Codex开发/K2.8复核分工派252，Hall group:task-1163bdf2e0c84a1c8b7561cc98aa33be，快照queued。仅review目录可写，不动源码/正式docs/生产/250；默认结束等用户“252好了”再取件，不主动等待。

## 251页面小修已完成

- 251/msg2769给出通过，原MCP为前言+JSON而业务unknown，保持原文；本地合法251 JSON与提取正文verification等关键字段一致，仅completed一处说明措辞差异。独立源码/11Node/26Python/5VM材料与实际候选核同后已收取completed（UTC2026-10-16T02:35:56.323335）。
- 原review/check_shas.log使用字节哈希混比规范文本哈希，错误初稿保留；根复核按manifest规范文本核9个base/candidate/共享源及patch，全对，174保护源中候选白名单外0业务差异，末轮tree_check/diff_check相符。后端状态描述不作250验收证据。
- 9候选文件已合入共享源：app.js一行、index.html六缓存与7既有测试版本替换。共享实际环境重新26 unittest/11 Node与语法/diff检查通过，真实日志handler指向本片.tmp，不写生产日志；隔离候选5VM证据沿用、不重复合计。
- 首页+六资源GET200、字节与已核源一致、六版本一致，见.tmp/task-initiator-label/final/static-check.json；未Browser，真实视觉交用户。251源与4相关docs精确提交推送，250在途源/私有/db不入提交；准确版本见该final/publication.json。

## 保留范围与下一步

- 用户明确插入的预算补正优先：252通知后取件、核独立证据与SHA，无问题再提交推送本片5文件并提供空闲重启说明。当前不要停止正在复核的旧K2.8。251仍待Ctrl+F5→任务详情核“发起人 XXX”，不把预算选项回复当页面验收。
- 随后Codex独立审250保留代码/真实测试与执行超时材料，必要修正按持续授权接手并另独立复核；不自动重派相同小时任务、不恢复旧K2.8写入，不把本地complete说成已通过。后端自动启动未验收，页面创建尚未接auto_start，真实受管/模型版本/原生/主动等待未验。
- 249/247方案已收取、正式ROLE_AUTO_START_DESIGN.md保持；248/246新角色入口未收取（整体硬预算/孙进程边界），不作为新角色真实准入。用户已启动的是旧K2.8，TALK受管能力unverified/control unknown不改。
- 全角色预算统一与角色删除列入后续独立片，不能把本轮需求记录当已开发/已生效。恢复“继续项目”先承接252预算复核/发布、UI验收及250独立审查，再按已确认需求安排；默认用户通知后取件，不轮询、不重复派发。精确配额本轮未读取，不臆测消耗比例。
