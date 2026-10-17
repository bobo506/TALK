# Project Progress

Updated: 2026-10-17 13:53最新：用户明确允许两个K2.8共用runner改managed_cli，但仍只启旧角色；标记已登记，adapter_status仍unverified。旧K2.8首次关闭暴露bridge未读停止文件，Codex直接补通用CLI停止监听，161项相关回归通过；原失败经独占控制台普通Ctrl+C/原manager正常回报恢复，无强杀。修正后同一manager启动→控制文件正常关闭/释放所有权→再启动ready通过，真实argv保21600/tools/原alias。最小任务262已派给旧角色，按默认通知后取件，尚未核接单结果；其它四角色未迁移/启停。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本轮MCP实读caller agent:codex/kind=agent，业务lead。页面development_requirements仍为旧Kimi前端/交叉复核文字，未自动修改。
- 用户2026-10-17最新分工优先：Codex派发→DeepSeek首次实现/自测交付后暂停→Codex独立复核首次实现→发现问题由Codex直接修正、验证及docs/Git收尾；不往返派修/默认追加外部回审。自修部分的验证为Codex自检，不称他人独立复核。
- 默认派后结束、用户通知后取件；共享目录一次一方改码。用户在260收尾后明确授权先试一个；261准备片已按通知收取并补正，根不操作Browser验证；原生CLI曾自行打开设备登录页，用户已完成专属认证。

## 当前单角色试迁移：启停已通过，262等待用户通知后收取

- 唯一候选仍为agent:kimi-code-k28-preview；新页面K2.8是另一身份，其它四角色不迁移/启停。用户已明确回复“允许修改共享标记，仍只启动旧角色”，原自动审批拒绝保留；随后共享control_kind→managed_cli成功，adapter_status仍unverified，模型绑定和原Key不变。不把共享标记当另一个角色已迁移或应自动启动。
- 已完成的旧入口正常退出、专属native登录、原alias探针及human-only保ID补录沿用前次证据。当前API仍由api-launcher.py持有原Popen、同venv/项目/127.0.0.1:8000/无reload，api-service/stop.request正常退出，不重复启动8000。
- 首次真实start generation1 ready，但stop generation2在20秒后stop_timeout：控制文件已正确写入，bridges.cli_bridge没有监听。原宿主仍持原Popen/owner，未强杀。核控制台仅8988/15832/2040及创建时刻/无任务后普通Ctrl+C，bridge正常清理、原manager请求并完成generation3 stopped/释放归属，再drain退出；不凭PID接管进程。
- Codex按已授权验收修正直接补bridges/cli_bridge.py及tests/test_cli_managed_stop.py：仅受管project/launch及匹配绝对控制路径启用监听；缺失/不可读/错误标记不误停，精确shutdown标记取消连接/消息并沿原路径取消任务worker、上报offline/close，旧手动入口保持。9项新增测试包含真实run_bridge清理假件、错误路径/内容、连接异常与外部取消；连同CLI/Kimi/Codex套件共161项全过。原实现生命周期反例超时、初期Windows夹具换行失败及原件均留存；修正为Codex自检，未追加DeepSeek返修/回审。
- 修正后新单成员manager（诊断PID11920）同一原Popen持有链：generation4/ins_87973da87bd6 ready→generation5正常控制文件关闭stopped/ownership=false→generation6/ins_b20c4078c97b ready，正常关闭不使用控制台信号。同manager关闭后仍常驻、可再启动；当前launch a7692ba4-21cc-4b2b-8f95-de42f39cd144、真实bridge PID15760创建UTC05:50:34.929962、argv实核21600/tools/kimi-code/kimi-for-coding及key-file无明文Key参数。
- UTC05:51:40派发最小接单任务262，Hall group:task-1faabbaba3d743bb9187e8282df23357，初始queued/assigned。派前实读caller agent:codex及最新旧development_requirements；262仅固定标记TALK_K28_MANAGED_ACK_20261017的结构化回传，不读写文件/运行工具/开发，原ID/Key/绑定/既有历史保持。按默认派后结束、用户通知“262好了”再读交付，不轮询，不提前宣称实际接单/回传通过。
- 单成员宿主继续常驻，只领取旧角色start/stop，原manager持有当前Popen；私有health位于.talk/role-service-host/pilot/prj_e8fe7066bbec/agent_kimi-code-k28-preview，health/PID仅诊断，正常页面关闭不结束宿主。drain.request仅用于宿主收工：先页面正常关闭角色，宿主无句柄后退出；不要删除活动状态或由新进程认领旧owner。首manager的已完成drain已归档，旧日志保持。
- 当前只是受管启停通过，完整迁移仍待262结果核验和人类页面验收；原生固定探针/161假件不证明实际后端版本、六小时长任务、主动等待或完整异常日志。生产子进程输出留存仍是后续已确认需求，不因本次补停止而宣称完成。
- 证据pilot-one/independent-review261/cutover/{shared-marker-user-authorization.json,state.json,manager-normal-stop-recovery.json,current-launch-public.json,smoke-dispatch.json,smoke-pre-dispatch.json,stop-fix/}；HTTP register/start/stop及逐阶段快照在其上一级。原自动拒绝、26开发件/副本、10根源码冻结保持，stop-fix/另存原bridge、负例、161日志及最终两源码副本。

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

1. 用户通知262完成后，先talk_get_delivery核任务号/完整结构化结论与固定标记，再核真实claimed instance为本轮ins_b20c4078c97b、原模型执行/回传证据，确认后收取；失败则Codex直接修正，不转回DeepSeek。当前不主动等待或轮询结果。
2. 262通过后交用户验收：打开http://127.0.0.1:8000，用既有人类账号/Key进入项目→角色，选旧Kimi Code · K2.8 Preview 执行，核启动成功/ready，关闭待“未启动（已关闭）”，刷新不自启，再启动并核新实例；不要顺带启动新页面K2.8或其它角色。当前宿主和API已启动，无需手动重新执行服务命令。人类验收通过后再排其余角色；DeepSeek及协调CLI最后。
3. 255创建自动首次启动等页面另按[指南](guides/ROLE_AUTO_START_PAGE_ACCEPTANCE.md)验创建/入队/实际ready及关闭后刷新不重启；完整异常日志/删除及主动链路另片，不在本轮扩改。

已实际完成专属登录、原生模型探针、API正常重载、保ID补录、明确授权后的共享控制标记和旧角色真实受管启停；最小TALK任务已派未核结果。仅2产品源码/6协调docs本轮收尾，未改数据库协议、模型绑定、原Key或其它角色。无需再次登录/批准已完成的共享标记变更，不能把先前失败页/旧验证码继续当当前待办。

## 已确认待实施与保留事实

- 258准备v3已收取/独立21项及5探针通过，原256/257 needs_changes报告不收取/不追改；v1 22/v2 25/v3 35原件及256—259审查证据保持。迁移事实只能重新核实，不能拿旧准备快照当当前状态。
- 完整异常日志须脱敏持久保存类型/消息/完整堆栈/因果链及项目/角色/实例/任务/阶段关联，跨重启可追查。父进程活着不代表接单循环健康；旧K2.8原记录只有task queue worker failed:，初因仍未知。详[日志与受管需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)。
- 全入口默认21600及可覆盖尚未全部落地：260仅受管宿主内置配方，通用bridge仍默认600、旧手动入口另片；252旧K2.8入口已发布79096ad，运行实例实际预算未核实。手动关闭完成→启动为恢复路径，不默认无限重启/随项目启动。
- [执行预算与删除需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：角色详情删除按钮待做，删除本项目配置/专属材料并保历史消息任务成果，一个K2.8删除不影响另一个；以后重新需要须创建新角色，共享模型/登录/其它项目保持。
- 254后端已收取发布98beb9c，原250失败/3600超时证据不追改；255独立95Node/26Python/14VM和8Node变异通过、发布019bb99，静态探针原隔离遗漏与后续根补验事实保留，不外推原DB零写。详历史及.tmp/role-auto-start-frontend/final255/。
- 253→248→246已收取、revision-2仅Windows10/files零模型准备通过，真实新Kimi/模型/退出/主动等待未验；251详情发起人标签已发布84b8010、视觉反馈仍待。
- 正式安装目录可设计private子目录保存部署生成的本机凭据，升级保留、不随源码/安装包分发；开发Git仓库仍隔离。当前内部Key根禁用规则不改，不移动TALK-private。
- 本轮未读取新的精确额度；此前usage-gate返回continue但session/weekly百分比null，不当0或臆测比例。完整历史见[开发历史](PROGRESS_HISTORY.md)，恢复可说“继续项目”。
