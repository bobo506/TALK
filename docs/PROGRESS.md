# Project Progress

Updated: 2026-10-17 14:07最新：旧K2.8单角色试迁移已正式验收通过。262固定回传由本轮受管实例完成并独立核验/收取；用户随后确认页面“关闭→刷新不自启→再启动ready”三步均通过，服务端generation7 stopped/generation8 ready吻合，原manager继续持有新进程。原ID/Key/模型绑定/既有历史保持，其余四角色未迁移/启停。c129a63停止修正/161回归沿用，本轮仅文档收尾，不开新角色迁移。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本轮MCP实读caller agent:codex/kind=agent，业务lead。页面development_requirements仍为旧Kimi前端/交叉复核文字，未自动修改。
- 用户2026-10-17最新分工优先：Codex派发→DeepSeek首次实现/自测交付后暂停→Codex独立复核首次实现→发现问题由Codex直接修正、验证及docs/Git收尾；不往返派修/默认追加外部回审。自修部分的验证为Codex自检，不称他人独立复核。
- 默认派后结束、用户通知后取件；共享目录一次一方改码。用户在260收尾后明确授权先试一个；261准备片已按通知收取并补正，根不操作Browser验证；原生CLI曾自行打开设备登录页，用户已完成专属认证。

## 当前单角色试迁移：旧K2.8已正式验收通过

- 唯一候选agent:kimi-code-k28-preview已保原ID/Key/模型绑定/身份档/既有历史完成受管迁移。新页面K2.8是另一身份，其余四角色未迁移/启停；用户明确允许共享runner改managed_cli而仍只启旧角色，原自动审批拒绝已按扩大范围解决，adapter_status保持unverified，不把共享标记当其它角色已迁移。
- 专属native登录、原alias探针、保ID补录已完成；c129a63补通用CLI受管控制文件监听/异步清理，9新增及CLI/Kimi/Codex共161相关回归通过，修正为Codex自检。本轮沿用未重跑；原stop_timeout/普通Ctrl+C原Popen正常恢复及原件/失败保留。修正后generation4 ready→generation5正常关闭释放归属→generation6再次ready真实通过。
- 用户通知262后独立核完整合法结构化task_id=262/complete、标记TALK_K28_MANAGED_ACK_20261017，实际由原角色/本轮ins_b20c4078c97b领取，结果2809作者/Hall匹配，UTC05:51:53.839623领取、05:52:02.817509完成。另核精确实例/launch/PID创建时刻及fresh原manager持有，任务后idle/current_task=null/无错误；原成员/Key文件mtime、全部binding/时间及角色行保持，历史计数仅增加本次262。Hall2810后UTC06:03:06.763702收取为succeeded/completed。
- 本轮人类随后明确回复页面“三步均通过”：关闭显示已关闭→刷新不自启→再启动ready。只读回查generation7 stop于UTC06:04:24.615810正常stopped，generation8 start于06:04:38.755614 ready；当前新instance ins_d86218c7cc0d、launch 4c72e06e-9ef9-45b2-a752-f520638c87e1。原manager诊断PID11920仍serving并持新Popen，OS创建时刻/私有公开记录吻合，原角色/绑定/Key保持；根未操作Browser或代替用户点击。
- 当前API api-launcher.py与单成员宿主常驻、旧角色running/ready，可由页面正常关闭/启动，无需手输服务命令或再次登录。角色关闭不结束宿主；宿主收工才用私有pilot/prj_e8fe7066bbec/agent_kimi-code-k28-preview/drain.request并先正常停角色、原handles空后退出。API私有api-service/stop.request正常退出，不另起8000/删除活动状态/由新进程凭PID认领。
- 单角色启停/接单/人类页面闭环通过，本轮完成收尾暂停，不开启其余角色或其它功能。其余四角色下轮逐个，DeepSeek及协调CLI最后；完整异常日志、255其它页面、删除、实际六小时/主动等待及固定后端模型版本仍待，不能外推最小回传已覆盖。
- 证据independent-review261/cutover/smoke262/{delivery.json,verification.json,live-verification.json,collection.json,human-page-acceptance.json,post-page-current-launch-public.json,baseline.json}；cutover/state.json标completed_and_human_accepted。原26开发件/副本、10根辅助代码及c129a63最终2源码冻结保持，私有Key/原生登录不入Git。

## 259补录及260宿主配置已发布，当前执行一角色真实验证

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

1. 本轮旧K2.8人工验收通过并完成收尾，暂停，不顺带启动其它角色。下轮继续其余四角色的逐角色预检和保ID迁移，逐项核公开绑定/本人Key/隔离登录/真实能力、正常退旧入口后再切换；DeepSeek和协调CLI最后，Desktop/MCP不凭PID接管。
2. 下一个角色仍须正常启动→关闭→再启动→最小接单/回传及必要人类页面验收，沿用原Key/模型/历史，不通过重建替代；本次共享标记允许不扩为本轮其它角色已获启动授权。当前原manager仅服务旧K2.8，不能直接让第二宿主认领其已有owner。
3. 255其它页面按[指南](guides/ROLE_AUTO_START_PAGE_ACCEPTANCE.md)另验；完整异常日志/删除及主动链路另片，不与迁移功能反复切换。

旧K2.8试迁移已完成：原生独立登录/探针、保ID补录、共享控制登记、真实启停/262接单、人类页面三步均通过。本轮仅6协调docs变更，沿用既有161回归，无新代码/角色启停/其它角色迁移或Browser操作；页面启停由用户实际完成并由服务端回执佐证。

## 已确认待实施与保留事实

- 258准备v3已收取/独立21项及5探针通过，原256/257 needs_changes报告不收取/不追改；v1 22/v2 25/v3 35原件及256—259审查证据保持。迁移事实只能重新核实，不能拿旧准备快照当当前状态。
- 完整异常日志须脱敏持久保存类型/消息/完整堆栈/因果链及项目/角色/实例/任务/阶段关联，跨重启可追查。父进程活着不代表接单循环健康；旧K2.8原记录只有task queue worker failed:，初因仍未知。详[日志与受管需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)。
- 全入口默认21600及可覆盖尚未全部落地：260仅受管宿主内置配方，通用bridge仍默认600、旧手动入口另片；252旧K2.8入口已发布79096ad，运行实例实际预算未核实。手动关闭完成→启动为恢复路径，不默认无限重启/随项目启动。
- [执行预算与删除需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：角色详情删除按钮待做，删除本项目配置/专属材料并保历史消息任务成果，一个K2.8删除不影响另一个；以后重新需要须创建新角色，共享模型/登录/其它项目保持。
- 254后端已收取发布98beb9c，原250失败/3600超时证据不追改；255独立95Node/26Python/14VM和8Node变异通过、发布019bb99，静态探针原隔离遗漏与后续根补验事实保留，不外推原DB零写。详历史及.tmp/role-auto-start-frontend/final255/。
- 253→248→246已收取、revision-2仅Windows10/files零模型准备通过，真实新Kimi/模型/退出/主动等待未验；251详情发起人标签已发布84b8010、视觉反馈仍待。
- 正式安装目录可设计private子目录保存部署生成的本机凭据，升级保留、不随源码/安装包分发；开发Git仓库仍隔离。当前内部Key根禁用规则不改，不移动TALK-private。
- 本轮未读取新的精确额度；此前usage-gate返回continue但session/weekly百分比null，不当0或臆测比例。完整历史见[开发历史](PROGRESS_HISTORY.md)，恢复可说“继续项目”。
