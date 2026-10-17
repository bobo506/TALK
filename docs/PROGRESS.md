# Project Progress

Updated: 2026-10-17 09:20 (Asia/Shanghai)：用户要求保险起见先移一个，261已交DeepSeek仅旧K2.8真实只读预检/可审执行包，交付暂停后Codex复核并实际切换。260已发布42738d9；尚未真实迁移任何角色。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本轮MCP实读caller agent:codex/kind=agent，业务lead。页面development_requirements仍为旧Kimi前端/交叉复核文字，未自动修改。
- 用户2026-10-17最新分工优先：Codex派发→DeepSeek首次实现/自测交付后暂停→Codex独立复核首次实现→发现问题由Codex直接修正、验证及docs/Git收尾；不往返派修/默认追加外部回审。自修部分的验证为Codex自检，不称他人独立复核。
- 默认派后结束、用户通知后取件；共享目录一次一方改码。用户在260收尾后明确授权先试一个；本轮261先准备候选执行包，默认派后结束、通知完成再取件，不操作Browser。

## 当前261：仅旧K2.8单角色试迁移，预检/执行包准备中

- 用户最新要求“保险点先移一个看看”，本轮仅候选agent:kimi-code-k28-preview，不迁其它四角色或自动换候选，不把新页面Kimi k2.8混为同一身份。该候选已有精确模型绑定/choice，原本人Key路径metadata存在；Kimi默认Key缺失、DeepSeek及协调入口保留到最后。
- 新鲜公开只读盘点仍只有Kimi runner unverified/unknown、service_state/launches空；旧实例最后报idle/task空是2026-10-16陈旧上报，不能证明当前空闲/退出/可控。host enabled=1不证明常驻manager运行。根默认权限列TALK-private顶层遇WinError5，仅metadata探测失败，未读凭据，不称自动审批拒绝。
- 261仅在.tmp/legacy-role-page-control/pilot-one/developer/做首次真实只读预检、实际CLI帮助/版本核对、原入口/原生隔离登录核验及默认dry-run可回滚执行包；如需辅助代码必须保原HostManager守卫并隔离测试。禁止未审先apply/登记/能力提升/启停/模型调用或改产品源码。只读GET认证确需原Key时可窄读内存使用并如实记录，不输出/哈希/复制Key，不读DB秘密列、不自动复制原生认证目录。
- 当前serve按项目领取，--members仅start-all；执行包须解决只候选claim/长期持有同一Popen/正常关闭，不能顺带启动新K2.8或其它角色，不能以--once结束manager后凭PID接管。共享runner影响须明确，真实能力未验不能盲升managed/verified；身份、绑定、历史与隔离HOME保持。
- Codex复核执行包后按同一用户授权实际切换：核旧入口空闲并正常退出→保ID legacy-attach→实证能力后最小登记→21600启动/精确owner及launch ready→关闭/再启动/最小接单回传→用户页面验收。若缺原生登录或退出事实，给具体角色/字段/核实步骤，不要求重建/重签或凭陈旧PID结束进程。
- 261 Hall group:task-cbf35f4ba1144e16b4e60f20881b42ef，UTC2026-10-17T01:20:33.703048初始queued/assigned，尚未轮询。基线42738d9/864跟踪SHA，根只维护5协调docs；公开事实、完整任务/初始回执及保护清单见pilot-one/coordination/。usage-gate实际continue但两用量百分比null，不当0。默认用户通知“261好了”后取件。

## 当前：259补录及260宿主配置代码完成，实际迁移待执行

- 用户要求全部现有5角色平移，保原member_id/Key/模型绑定/身份档及任务消息成果历史，两个K2.8各自保留，不通过重新创建替代迁移。
- [259补录合同](spec/ROLE_LEGACY_ATTACH_DESIGN.md)已落地human-only legacy-attach：原子增加imported/nonexclusive项目角色、必要缺失绑定和独立补录审计，沿用原Key；既有绑定/名册/说明/策略/历史保留，不生成新身份/Key或配置作业，不自动启动。精确legacy_attach来源及mismatch投影，宿主仅扩可信来源，其余能力/owner守卫保持。
- 259独立发现操作键反向隔离与非法非空名称回落两问题后由Codex直接修正：6原探针4失败保留，最终162相关回归+2显式WAL双入口并发探针通过，Hall2798后已收取、发布ea21d81。原2797 partial、8候选/开发证据保留；开发685只是自报，本地无完整原始日志，不作独立证据。详product-attach/independent-review259/与历史。
- [260宿主合同](spec/ROLE_HOST_RUNTIME_CONFIGURATION_DESIGN.md)现已实现可重复--runtime-command-template RUNTIME TEMPLATE；只接受codex/dsh/cli，同值去重/异值拒绝，显式runtime优先、旧全局回退，kimi-code保持原生模型参数。--cli-execution-timeout-seconds缺省None、内置有效21600，正整数显式覆盖；四配方实际外层argv恰一个--timeout，真实parser/预检/最终spawn/诊断共用预算事实。
- 显式--cli-executable维持旧cli_args/alias及旧global兼容，不自动追加bridge预算，预算None/not_applied；显式新模板或预算与custom组合稳定拒绝。模板只是配置，不代替runtime-verified/真实原生能力验收；不改claim/report协议、ready/stop/HTTP/MCP/T-W/租约或现有实例。
- 原260/msg2801为合法partial，MCP succeeded/submitted且DeepSeek报idle后冻结3候选字节、885开发证据及853保护文件。Codex首次独立复核发现F1/P2：超长数字int转换抛ValueError、合法长前导零误拒，False/0/空字符串非集合被当缺省；F2/P2：组装/核验后重读manager使预算来源或诊断数值偏离argv。
- 新增6方法在原产品上出现17子测试失败/3错误（不是20个独立测试），原日志保留。Codex只改host和新增测试：模板先验集合类型；数字先去前导零/按文本判范围再转int；组装时捕获预算与来源，预检从核验argv取预算。未派返修或额外回审。
- 修正后Codex自检运行74项（40配置/34原宿主），0失败/错误/跳过；12种runtime×默认/60/43200组合在预检中改变配置仍保持最终argv/真实parser/诊断一致。74次TestClient与11次回环服务启动前均断言临时DB/storage隔离；仅假Key/固定文本进程，无真实CLI/模型。3候选compile/diff通过，原host测试、853保护文件及885开发证据SHA一致。
- 开发原日志实查新增34/host34/worker50/role_services59成功，作为开发自测独立列示，不与根74重复合计。Hall2802裁决accepted_after_codex_corrections；UTC2026-10-17T01:09:51.256720收取260为succeeded/completed，原partial结果不改。
- 证据.tmp/legacy-role-page-control/product-host-config/independent-review260/{delivery-summary.json,review.json,original-negative.log,fixed-regressions.log,final-tests.json,candidate-manifest.json,source-validation.json,collection.json,publication.json}。实际产品改动2源（host与新增配置测试），另8正式docs；原候选与失败记录完整保留。

## 下一步与人工门禁

1. 在原授权内核实5角色的原本人Key来源、实际公开runner/model与宿主运行事实，准备真实逐角色平移。目标Key根缺文件不等于需重建身份/轮换Key；不猜模型，不把旧PID/陈旧心跳或host配置enabled当可控/空闲证明。
2. 真实能力通过后正常退旧入口，保原ID补录，再逐角色验启动→关闭→再启动→最小接单/回传。DeepSeek自身及协调CLI最后切换；当前Codex Desktop/MCP不按未知PID强行接管，不放开unknown/unverified、归属或stop所有权守卫。
3. 255前后端代码已发布，但人工页面/真实原生仍待。加载019bb99前端及98beb9c后端后Ctrl+F5，在项目→角色按[验收指南](guides/ROLE_AUTO_START_PAGE_ACCEPTANCE.md)验创建自动首次启动、配置/入队/实际ready区分、关闭后刷新不再启动。使用既有人类账号/Key，具体启动方式/入口/限制见指南。

本轮没有真实补录/迁移、生产API/DB/config写入、真实Key正文读取、能力升级、服务启停或模型调用；参数和隔离进程测试不证明真实六小时长任务、原生登录/模型或终端T-W通过。260宿主代码已收尾；当前只准备261单角色切换包，不同时扩完整日志/删除/通用预算。

## 已确认待实施与保留事实

- 258准备v3已收取/独立21项及5探针通过，原256/257 needs_changes报告不收取/不追改；v1 22/v2 25/v3 35原件及256—259审查证据保持。迁移事实只能重新核实，不能拿旧准备快照当当前状态。
- 完整异常日志须脱敏持久保存类型/消息/完整堆栈/因果链及项目/角色/实例/任务/阶段关联，跨重启可追查。父进程活着不代表接单循环健康；旧K2.8原记录只有task queue worker failed:，初因仍未知。详[日志与受管需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)。
- 全入口默认21600及可覆盖尚未全部落地：260仅受管宿主内置配方，通用bridge仍默认600、旧手动入口另片；252旧K2.8入口已发布79096ad，运行实例实际预算未核实。手动关闭完成→启动为恢复路径，不默认无限重启/随项目启动。
- [执行预算与删除需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：角色详情删除按钮待做，删除本项目配置/专属材料并保历史消息任务成果，一个K2.8删除不影响另一个；以后重新需要须创建新角色，共享模型/登录/其它项目保持。
- 254后端已收取发布98beb9c，原250失败/3600超时证据不追改；255独立95Node/26Python/14VM和8Node变异通过、发布019bb99，静态探针原隔离遗漏与后续根补验事实保留，不外推原DB零写。详历史及.tmp/role-auto-start-frontend/final255/。
- 253→248→246已收取、revision-2仅Windows10/files零模型准备通过，真实新Kimi/模型/退出/主动等待未验；251详情发起人标签已发布84b8010、视觉反馈仍待。
- 正式安装目录可设计private子目录保存部署生成的本机凭据，升级保留、不随源码/安装包分发；开发Git仓库仍隔离。当前内部Key根禁用规则不改，不移动TALK-private。
- 本轮未读取新的精确额度；此前usage-gate返回continue但session/weekly百分比null，不当0或臆测比例。完整历史见[开发历史](PROGRESS_HISTORY.md)，恢复可说“继续项目”。
