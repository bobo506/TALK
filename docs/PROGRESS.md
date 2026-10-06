# Project Progress

Updated: 2026-10-06 (Asia/Shanghai)。C2-B原实现/独立复核通过并收取，功能提交946490f已推送；用户人工验收提出离页未保存选择复位和状态行去版本要求，已派#164给Kimi定向修正，完成后DeepSeek独立复核。

## 当前身份与协作

- 根目录D:/claude-test/TALK，项目prj_e8fe7066bbec，分支codex/terminal-return-codex。Codex决策角色负责范围/裁决/正式文档/Git；Kimi文字/设计/交互/前端，DeepSeek后端/其它，双方交叉复核。派前仍须读取最新development_requirements，不能按旧记录猜分工。
- 默认派发后结束，用户通知完成后再取件；开发暂停后审查，禁止并行改业务码。顶层最小参数/标题不手写编号。Codex不操作浏览器，页面由用户验收。

## 当前切片：C2-B人工反馈修正#164待交付

- 用户本轮选择第二种消歧方案：离开项目设置（任务/群聊/具体角色等）放弃模式未保存点选，返回选已确认保存模式；停留当前面板重绘不丢点选。状态行改已保存设置：被动/主动，去括号和版本，仅删展示，内部CAS版本保护保留。#164已派agent:kimi，queued/assigned；基线946490fc34601d1b5e38830a29eaef385b105529，任务包.tmp/controller-mode-c2-b-ux-dispatch/task.md，交付.tmp/controller-mode-c2-b-ux/。原行为和手册尚待本片落实后同步，不能称新反馈已修好。
- Kimi #160开发，DeepSeek #161独立原片审查发现F-1冲突后GET失败时重试按钮隐藏/F-2入库QA缺:has降级事实；Kimi #162定向修正，DeepSeek #163独立增量/直接回归复核agree。Codex合看#161主体A/B/D及C/E其余和#163修正结论，确认实现通过、两项关闭，不以格式/runner状态单独判验收。
- 项目设置右侧依次为开发要求/项目主控/调度模式；被动/主动选择必须显式保存，已保存设置与实际执行分行。human可保存、agent只读；active仍仅意向，实际执行仍尚无生效的主动调度，不自动唤醒/互斥。
- 专用controller-mode CAS、成功核实/旧服务/安全版本与账号项目隔离保持；409只GET重读，失败reloadNeeded使重试可见且只GET、按钮与入口暂禁旧版本保存；成功读取更新版本后明确手动保存。参与任务只留面板级一条线；静态资源四处版本20261006-controller-mode-c2b-f1一致，无需服务重启，仅强刷新静态资源。
- USER_MANUAL已加入调度模式与冲突两分支恢复步骤，Web UI模块/项目简报/设计状态/路线图同步；design-qa记录:has旧浏览器样式降级与独立证据。原#162实施说明称集成探针核实重试调用的措辞，由收尾QA/历史澄清：探针只查id接线，实际调用目标由#163源码核对确认，原报告不追改。

## 验证与限制

- #163独立复跑Node九文件153/153（含新增模式23项）、原恢复探针7/7、新恢复12/12、集成15/15、Python四页面契约12/12及语法/版本检查通过，开工/结束源码hash与快照一致。Node复核用--test-isolation=none；默认隔离spawn EPERM未独立确认，Kimi两模式自报通过不外推为独立证据。
- 浏览器桌面80%/窄屏视觉、radio实机键盘/:has旧浏览器外观、真实HTTP竞态/端到端未测，留用户页面验收。98后端为#160开发者自测、定向修正/复核未重跑；未改后端/API/数据库/MCP/运行配置。P3-2重试GET在途短暂未保存提示非阻塞，本片不扩UX。
- 源码9文件（QA以外）收尾前仍与#163快照一致；Codex仅追加正式说明/QA证据归属和进度，差异检查后统一提交推送。原片收尾提交946490fc34601d1b5e38830a29eaef385b105529已常规推送，本次反馈开工工作区干净；持续授权origin bobo506/TALK常规推送，无upstream时显式origin codex/terminal-return-codex，不强推/改历史。

## 交付与恢复索引

- #160/msg2662、#163/msg2665合法完整结构化complete；#161/msg2663原partial已收取保留。#162/msg2664原混排MCPunknown保留，本地development.json合法complete，稳定引用全文5047字符/sha a6c5de382289e0bded52bdafa271f842d888afe208ff722f619b976b39e10645，提取JSON与本地包一致，经独立实际代码复核确认修正。
- 收取时间（服务端原记录未补时区）：#163 2026-10-06T03:59:09.896485；#162 03:59:11.904748；#160 03:59:13.849989。#161此前02:58:18.859405。全部workflow completed，不能重复派发/收取。
- 原开发.tmp/controller-mode-c2-b/；原独立审查.tmp/controller-mode-c2-b-review/；修正.tmp/controller-mode-c2-b-fix/；定向复核.tmp/controller-mode-c2-b-fix-review/；修前文本.tmp/controller-mode-c2-b-fix-dispatch/pre_fix/，修后10文件sha/bytes快照.tmp/controller-mode-c2-b-fix-review-dispatch/source_manifest.json。原报告/失败证据不改，当前索引已足够恢复，无需重读全部历史Hall。

## 后续计划与门禁

1. 用户通知#164完成后读完整合法交付与实际增量，再另派DeepSeek独立检查离页边界/保存在途/迟到/同页重绘不丢点选、文案简化与内部CAS不变、原恢复路径直接回归；开发完成暂停，禁止并行改码。通过后同步模式合同/模块/用户手册及QA、正式进度与Git，请用户验收两条新反馈。第3项权限/异常恢复为边界验收：有管理员提供现有agent密钥才测只读，没有可跳过；409后GET再失败需要受控故障，普通用户可标人工未测，不强求断网/造账号，已有独立代码/探针证据与人工未测区分。验收完成前不开C2-C。
2. C2-C约定消费者/指南与真实主动链路尚未开发，须显式匹配各终端预算（DeepSeek桌面65秒上限下wait50秒；Codex保持用户现用300秒）。Codex当前连接已通过九工具/controlled_wait/caller_identity及短预算历史命中和human G4拒绝/后续查询加载检查；不等于长等待/取消/真实主动链路已验收，DeepSeek桌面目录刷新未外推。
3. 主控Key入口此前实测human:bobo、模式passive、指定agent:codex，不能驱动受控等待，不改凭据/指定绕过门禁；effective_mode仍null/not_bound。C2-A2版本耗尽低风险可选，C2-D真正取消未开发。全局运行器库→项目角色绑定/选择性启停与自启动、工作区隔离/群聊仍后续，不自动启动全部软件。

恢复指令：继续项目。先读本快照，当前#164人工反馈修正待交付，之后交叉复核及页面再验；完整历史见PROGRESS_HISTORY，已完成任务不重复收取，未经用户要求不持续等待或改运行配置。
