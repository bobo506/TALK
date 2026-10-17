# Project Progress

Updated: 2026-10-17 13:26 (Asia/Shanghai)：旧K2.8已退出、隔离登录/原模型探针通过并保ID补录；共享runner改managed_cli被自动审批拒绝，已请求用户明确授权共享影响，尚未启动角色。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本轮MCP实读caller agent:codex/kind=agent，业务lead。页面development_requirements仍为旧Kimi前端/交叉复核文字，未自动修改。
- 用户2026-10-17最新分工优先：Codex派发→DeepSeek首次实现/自测交付后暂停→Codex独立复核首次实现→发现问题由Codex直接修正、验证及docs/Git收尾；不往返派修/默认追加外部回审。自修部分的验证为Codex自检，不称他人独立复核。
- 默认派后结束、用户通知后取件；共享目录一次一方改码。用户在260收尾后明确授权先试一个；261准备片已按通知收取并补正，根不操作Browser验证；原生CLI曾自行打开设备登录页，用户已完成专属认证。

## 当前单角色试迁移：旧K2.8已保ID补录，共享控制标记等待明确授权

- 用户已确认旧入口原终端Ctrl+C退出；root于UTC2026-10-17T05:07:23.5937979Z复查旧PID8528不存在。第二次专属设备登录session39261成功，CLI回显Logged in to managed:kimi-code、exit0，角色独立config已生成，未复制原认证目录。
- 隔离native配置包含原alias kimi-code/kimi-for-coding，provider managed:kimi-code/model kimi-for-coding/显示K2.8 Preview及能力维度匹配。root用无工具/无子代理的独立原生Popen做固定文本探针，UTC05:13:28完成，exit0/5.296秒、assistant正文精确匹配标记；不推断实际后端版本固定为K2.8或主动等待通过。
- 发现原宿主默认把旧角色tools任务档降成review且改默认展示；root在单成员corrected/入口保留旧TASK_TOOL_PROFILE=tools、原DISPLAY_NAME与工作目录，不扩到其它角色。原parser反例profile=review/display_name=null/workdir=.已留痕；新增两项后最终23项相关测试全过，原21项及3失败是先前准备阶段记录，不叠加计数。
- 第一次legacy-attach请求HTTP405、未写角色：实际8000 API仍旧进程、无--reload，未加载259接口。root核精确API进程/创建时间/venv及独占控制台链12312/14812/3208、全库queued/running=0，普通Ctrl+C正常退出后，以同venv/项目/127.0.0.1:8000/无reload配置隐藏启动API；OpenAPI确认新增接口已加载。未强杀或接管角色。
- 当前API由root api-launcher.py持有原Popen/独立进程组，私有控制目录C:/Users/Administrator/.talk/role-service-host/api-service，health.json仅诊断，stop.request由原launcher发CTRL_BREAK正常退出；没有自动重启。不要重复启动第二个8000服务或凭PID认领；源码在本机independent-review261/，保持证据目录以便恢复。
- UTC05:21:57 human-only legacy-attach实际成功201/reused=false，独立operation_key=pilot-legacy-attach-k28-20261017-v1。旧member_id/原Key身份及文件mtime、全部已有绑定/其时间、目标任务历史计数/ID范围、其它角色显式配置均保持；仅新增imported/nonexclusive项目角色和独立补录审计，无新Member/新Key/配置作业或自动启动。
- 下一步PATCH共享runner runner:kimi-code-1aabe894a3c21096ad9c7f5211aa7e33/control-kind为managed_cli被自动审批在进程启动前拒绝，未发PATCH；理由是它还绑定新页面K2.8，该共享能力变更会让另一个未获本轮试迁移授权的角色也获得受管启动资格。已异步请用户选择是否允许这一个共享标记变更；不能绕过或换入口执行同一动作，未收到同意前不重试。
- 当前control_kind仍unknown/adapter_status仍unverified；候选service generation0/desired stopped/observed not_started/无owner或launch，can_start=false。尚未启动任何受管角色或发送最小接单任务。其它四角色未迁移/启停；共享标记若获同意，本轮仍只由固定project/member宿主领取旧角色，另一个K2.8不得顺带启动。
- 本轮实际补录不是完整迁移验收：审批同意后最小登记共享control_kind（不改adapter_status/模型）→隐藏启动经审单成员宿主→精确owner/project/launch ready与21600及原tools档→关闭→再启动→最小接单/回传→用户页面验收。已有总体迁移批准不被误用为共享影响已批准，按本次自动审批要求补明确范围。
- root cutover证据pilot-one/independent-review261/{native-login-success.json,native-probe.json,profile-preservation-negative.json,api-normal-stop.json,api-version-ready.json,apply-attach-*.json,http-audit-*.json,cutover/state.json,cutover/automatic-approval-rejection.json}；10份根代码已冻结cutover/source/与code-manifest.json。原26开发件、初次失败及本地partial/MCP自由文本unknown保持。

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

1. 等待用户明确是否允许修改两个K2.8共用runner的control_kind；自动审批已因共享影响拒绝，未经同意不重试。获准后只启旧K2.8，验关闭/再启动/最小接单；不同意则保留补录、暂停实际切换。其它四角色仍待这一个验收后再排。目标Key根缺文件不等于需重建身份/轮换Key；不猜模型，不把旧PID/陈旧心跳或host配置enabled当可控/空闲证明。
2. 旧K2.8完成受管闭环并经用户验收后，再排其余角色的公开绑定/能力预检、正常退出旧入口、保ID补录及启动→关闭→再启动→最小接单/回传。DeepSeek自身及协调CLI最后切换；当前Codex Desktop/MCP不按未知PID强行接管，不放开unknown/unverified、归属或stop所有权守卫。
3. 255前后端代码已发布，但人工页面/真实原生仍待。加载019bb99前端及98beb9c后端后Ctrl+F5，在项目→角色按[验收指南](guides/ROLE_AUTO_START_PAGE_ACCEPTANCE.md)验创建自动首次启动、配置/入队/实际ready区分、关闭后刷新不再启动。使用既有人类账号/Key，具体启动方式/入口/限制见指南。

当前已发生候选私有登录、一次独立原生模型探针、API正常重载及保ID补录；尚未登记共享能力、启动角色或执行TALK接单测试。原生最小探针不证明真实六小时长任务、模型版本/开发质量或终端T-W通过。260宿主代码已收尾；当前旧K2.8已保ID补录，实际启动等待共享运行器标记影响的明确授权，不同时扩完整日志/删除/通用预算。

## 已确认待实施与保留事实

- 258准备v3已收取/独立21项及5探针通过，原256/257 needs_changes报告不收取/不追改；v1 22/v2 25/v3 35原件及256—259审查证据保持。迁移事实只能重新核实，不能拿旧准备快照当当前状态。
- 完整异常日志须脱敏持久保存类型/消息/完整堆栈/因果链及项目/角色/实例/任务/阶段关联，跨重启可追查。父进程活着不代表接单循环健康；旧K2.8原记录只有task queue worker failed:，初因仍未知。详[日志与受管需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)。
- 全入口默认21600及可覆盖尚未全部落地：260仅受管宿主内置配方，通用bridge仍默认600、旧手动入口另片；252旧K2.8入口已发布79096ad，运行实例实际预算未核实。手动关闭完成→启动为恢复路径，不默认无限重启/随项目启动。
- [执行预算与删除需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：角色详情删除按钮待做，删除本项目配置/专属材料并保历史消息任务成果，一个K2.8删除不影响另一个；以后重新需要须创建新角色，共享模型/登录/其它项目保持。
- 254后端已收取发布98beb9c，原250失败/3600超时证据不追改；255独立95Node/26Python/14VM和8Node变异通过、发布019bb99，静态探针原隔离遗漏与后续根补验事实保留，不外推原DB零写。详历史及.tmp/role-auto-start-frontend/final255/。
- 253→248→246已收取、revision-2仅Windows10/files零模型准备通过，真实新Kimi/模型/退出/主动等待未验；251详情发起人标签已发布84b8010、视觉反馈仍待。
- 正式安装目录可设计private子目录保存部署生成的本机凭据，升级保留、不随源码/安装包分发；开发Git仓库仍隔离。当前内部Key根禁用规则不改，不移动TALK-private。
- 本轮未读取新的精确额度；此前usage-gate返回continue但session/weekly百分比null，不当0或臆测比例。完整历史见[开发历史](PROGRESS_HISTORY.md)，恢复可说“继续项目”。
