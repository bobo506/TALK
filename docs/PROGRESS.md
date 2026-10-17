# Project Progress

Updated: 2026-10-17 16:15最新：用户报告新Kimi k2.8网页授权完成，但旧CLI91333实际900秒超时/exit1且config未保存，未误判成功；已重发正常独立登录81204并请求用户完成新链接。设备码TTL1800与CLI实际等待900不同，有效码/链接仅本机记录。263文案/准备已发布83978da，原生probe/服务启动尚未执行，其它角色保持当前状态。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本轮MCP实读caller agent:codex/kind=agent，业务lead。页面development_requirements仍为旧Kimi前端/交叉复核文字，未自动修改。
- 用户2026-10-17最新分工优先：Codex派发→DeepSeek首次实现/自测交付后暂停→Codex独立复核首次实现→发现问题由Codex直接修正、验证及docs/Git收尾；不往返派修/默认追加外部回审。自修部分的验证为Codex自检，不称他人独立复核。
- 默认派后结束、用户通知后取件；共享目录一次一方改码。用户在260收尾后明确授权先试一个；261准备片已按通知收取并补正，根不操作Browser验证；原生CLI曾自行打开设备登录页，用户已完成专属认证。

## 当前263已收取：文案完成，下一角色独立登录待用户

- 263/msg2812为合法partial，任务号匹配、DeepSeek已报idle/current_task=null并暂停。根冻结18开发件及3候选，实读实际diff/两脚本/原始验证；三前端仅去“原进程归属未释放”术语、已有断言及workspace.js查询版本20261017-role-stop-hint，权限/owner/按钮/请求不改。角色提示为“请先「关闭」并确认已停止，再重新启动。”，用户已确认对应关闭中→未启动（已关闭）。
- 本机补跑原node --test tests/workspace_role_services.test.cjs默认隔离23/23通过，开发环境spawn EPERM/无审批通道的限制与进程内23原证据保持，不当根环境永久阻塞。实际首页指向新查询版本、服务JS字节与候选一致；没有Browser验证，用户刷新可见。
- 辅助入口确实固定新候选/project/原显示名Kimi k2.8/默认review，保产品HostManager与原Popen/drain/隔离。发现open_gaps写死native目录不存在，目录存在时仍误报；原1反例失败0错误，仅independent-review263/corrected/副本改为实时exists口径。原7+根5共12项通过，含原main apply假件、中断后stop网络错误仍保同manager原句柄、空句柄正常退出、旧K28 start/stop均过滤及有界去重；根自修为自检，不追加DeepSeek返修/回审。
- 实际CIM核旧10152/11920都是旧成员专属pilot入口、无泛项目serve或新候选host。新候选原Key可信文件已由根窄读GET核本人/Kimi k2.8；原成员/创建/精确binding保持，现generation0/not_started/无owner/launch，无待办。它已managed/exclusive，禁止重复补录/CREATE/轮换Key；共享adapter_status仍unverified，不因按钮可用升级能力。
- 根在既有继续迁移授权内初始化本候选自己的产品native HOME/KIMI_CODE_HOME，未复制原认证；已发起正常设备登录CLI会话91333，码本机记录码，链接本机resume-login-session.json中的有效设备链接，CLI窗口1800秒（约UTC07:38:04开始）。异步请用户完成；当前未收到CLI成功，不能启动服务或调用模型。session存在时用write_stdin续读，过期/退出后按实际状态重新发起，不复用旧code或并开重复登录。
- Hall2813裁决文案/准备经补正可收，UTC2026-10-17T07:41:25.993704收取263 succeeded/completed，原partial/报告不改；这里只收准备，不称新角色迁移已完成。原包P6“另批”不覆盖当前明确授权：必要最小接单属于已授权迁移验证，无需重复请总体许可。DeepSeek已交付暂停，本阶段保留它的旧服务运行，迁移自身时最后正常退旧入口。
- 本轮未对旧K28启停：只读新快照显示其generation9/stopped/无owner，原窄manager11920仍在；保用户当前状态，不自动重启它。现有API继续由原api-launcher管理，不另起8000/按PID接管。新角色尚未请求start/stop、未模型probe、未生产配置/Key/能力变更；初始化native目录与登录是已发生的本机副作用，不称零写。
- 证据remaining-role-next/independent-review263/{review.json,collection.json,node-default-isolation.json,static-resource-verification.json,old-host-scope.json,original-diagnostic-negative.json,final-helper-tests.json,state.json,resume-login-session.json}；developer原18件/候选3件和旧261/262冻结保留。继续执行用corrected/入口，原包/开发件不改。

## 已完成与恢复所需事实

- 旧agent:kimi-code-k28-preview已正式验收并发布11bd14e：保原ID/Key/模型/历史完成专属登录/探针、保ID补录、受管启停、262接单与人类页面三步。262结果2809/复核2810已收取，任务由当轮ins_b20c4078c97b完成；人类随后页面generation7正常关闭/generation8再ready，当时ins_d86218c7cc0d、launch 4c72e06e-9ef9-45b2-a752-f520638c87e1；263收取阶段已只读见generation9关闭，保用户当前状态。这里只保恢复摘要，完整经过与失败见PROGRESS_HISTORY及pilot-one/independent-review261/cutover/。
- 旧K28常驻单成员manager诊断PID11920持原Popen，API由api-launcher.py持原Popen，二者不动；PID/磁盘记录仅诊断，不能新进程认领。角色页面关闭不结束宿主；宿主收工才用私有pilot/prj_e8fe7066bbec/agent_kimi-code-k28-preview/drain.request，先正常停角色、原handles空后退出。API私有api-service/stop.request正常退出，不另起8000或删活动状态。Key/原生登录在仓库外，不入Git。
- c129a63补通用CLI受管停止文件监听/异步清理，9新增及CLI/Kimi/Codex共161项相关回归通过，Codex修正后自检；首次stop_timeout和原控制台普通Ctrl+C/原Popen恢复、原26开发件/副本与10根辅助源冻结均保留。本轮不重跑/重复累计，不声称完整日志、固定后端版本、六小时或主动等待通过。
- 259保ID补录已发布ea21d81：human-only legacy-attach只补原名册但无ProjectRole的身份，保原Key/绑定/历史、不自动配置/启动，162相关回归+2WAL证据见历史。新页面K2.8已有managed登记，不能套该补录。
- 260宿主配置已发布42738d9：逐runtime模板、内置默认21600/可覆盖、真实parser/argv/诊断同一快照；custom旧兼容与身份/choice/owner/原生核验守卫保持，74相关验证见历史。共享runner control_kind已获明确批准改managed_cli，adapter_status仍unverified，不代替新角色独立登录/能力事实。完整合同见ROLE_HOST_RUNTIME_CONFIGURATION_DESIGN、ROLE_SERVICE_CONTRACT及ROLE_LEGACY_ATTACH_DESIGN。

## 下一步与人工门禁

1. 先核新登录81204实际退出与候选config（仅公开模型维度）；91333已结束不可续等，当前native-login-status.json可能仍为前次失败报告。新进程成功/新报告生成后再做无工具固定原alias probe，凭据不输出/复制/哈希。用户已完成的是旧网页会话，当前需新设备授权；实际CLI约15分钟等待，链接码TTL约30分钟，不能据后者假设进程仍在。
2. 原生探针通过后，只启动经审corrected/单成员host和该新页面Kimi k2.8，验当前launch/expected instance ready→正常关闭/归属释放→再启动→最小接单/回传及人类页面。当前已managed，不legacy-attach/CREATE/新Key，不改runner/绑定或旧K28现有状态，缺必要登录时保门禁；总体迁移许可已有。
3. 新角色验收后再逐个处理Kimi、DeepSeek、Codex：当前均binding unconfigured，先核原模型/命令/本人Key，不猜或重建替代，后两者最后，Desktop/MCP不按PID接管。完整日志/删除/T-W及255其它页面另片。

文案/迁移准备263已收取，本轮前端3源及协调docs收尾；新角色独立登录尚待，不把准备或共享标记当真实迁移通过。原生native目录初始化已发生，其它角色不由协调方启停；根不操作Browser。

## 已确认待实施与保留事实

- 258准备v3已收取/独立21项及5探针通过，原256/257 needs_changes报告不收取/不追改；v1 22/v2 25/v3 35原件及256—259审查证据保持。迁移事实只能重新核实，不能拿旧准备快照当当前状态。
- 完整异常日志须脱敏持久保存类型/消息/完整堆栈/因果链及项目/角色/实例/任务/阶段关联，跨重启可追查。父进程活着不代表接单循环健康；旧K2.8原记录只有task queue worker failed:，初因仍未知。详[日志与受管需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)。
- 全入口默认21600及可覆盖尚未全部落地：260仅受管宿主内置配方，通用bridge仍默认600、旧手动入口另片；252旧K2.8入口已发布79096ad，运行实例实际预算未核实。手动关闭完成→启动为恢复路径，不默认无限重启/随项目启动。
- [执行预算与删除需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：角色详情删除按钮待做，删除本项目配置/专属材料并保历史消息任务成果，一个K2.8删除不影响另一个；以后重新需要须创建新角色，共享模型/登录/其它项目保持。
- 254后端已收取发布98beb9c，原250失败/3600超时证据不追改；255独立95Node/26Python/14VM和8Node变异通过、发布019bb99，静态探针原隔离遗漏与后续根补验事实保留，不外推原DB零写。详历史及.tmp/role-auto-start-frontend/final255/。
- 253→248→246已收取、revision-2仅Windows10/files零模型准备通过，真实新Kimi/模型/退出/主动等待未验；251详情发起人标签已发布84b8010、视觉反馈仍待。
- 正式安装目录可设计private子目录保存部署生成的本机凭据，升级保留、不随源码/安装包分发；开发Git仓库仍隔离。当前内部Key根禁用规则不改，不移动TALK-private。
- 本轮未读取新的精确额度；此前usage-gate返回continue但session/weekly百分比null，不当0或臆测比例。完整历史见[开发历史](PROGRESS_HISTORY.md)，恢复可说“继续项目”。
