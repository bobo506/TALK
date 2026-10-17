# Project Progress

Updated: 2026-10-17 15:09最新：用户要求去掉“原进程归属未释放：”并明确可开始其余角色迁移。263已派DeepSeek首次执行：仅3前端路径简化提示/刷新workspace资源版本及下一位新页面Kimi k2.8只读迁移准备；默认用户通知后取件。下一候选已是managed，不重复补录/重建；本片不启停/登录/模型调用，其余角色先核真实绑定/原Key，DeepSeek和协调CLI最后。旧K2.8正式验收通过事实保持。

## 当前身份与分工

- TALK / prj_e8fe7066bbec / codex/terminal-return-codex；本轮MCP实读caller agent:codex/kind=agent，业务lead。页面development_requirements仍为旧Kimi前端/交叉复核文字，未自动修改。
- 用户2026-10-17最新分工优先：Codex派发→DeepSeek首次实现/自测交付后暂停→Codex独立复核首次实现→发现问题由Codex直接修正、验证及docs/Git收尾；不往返派修/默认追加外部回审。自修部分的验证为Codex自检，不称他人独立复核。
- 默认派后结束、用户通知后取件；共享目录一次一方改码。用户在260收尾后明确授权先试一个；261准备片已按通知收取并补正，根不操作Browser验证；原生CLI曾自行打开设备登录页，用户已完成专属认证。

## 当前263：简化提示与下一角色迁移准备已派

- 用户确认提示应表达“关闭后等确认停止再启动”，要求去掉“原进程归属未释放：”；角色提示目标为“请先「关闭」并确认已停止，再重新启动。”，批量提示同样去内部术语。仅文字与workspace.js资源查询版本，不改变ownership/canStart/canStop/权限/请求或停止守卫。
- 用户明确可开始迁移其余角色，取代先前只试旧角色的本轮范围；仍逐个保原ID/Key/模型/既有历史。当前只准备下一位agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c（Kimi k2.8），它已是managed/exclusive且绑定精确Kimi choice，不能legacy-attach/重建或套旧K28的tools/显示名。共享managed_cli已登记，adapter_status仍unverified，不等于新角色本人Key/隔离原生能力已通过。
- 实际只读公开列核2显式角色：旧K28 imported，新K28 managed；其余Kimi/DeepSeek/Codex名册仍在但binding_state unconfigured。无任何在途任务。只核明确信息，不从旧心跳或缺目录推断空闲/从未受管；后3角色模型/原命令/本人Key源尚需查明，DeepSeek和协调CLI最后、Desktop/MCP不按PID接管。
- 263/Task Hall group:task-7414c8d0769e4455bc28c4ce03663a27，UTC2026-10-17T07:07:56.479414初始queued/assigned，交agent:deepseek首次执行后暂停。只允许web/workspace.js、web/index.html、tests/workspace_role_services.test.cjs及remaining-role-next/developer/；正式docs由Codex维护。共享源码开发期间根不审读/改码，完成后独立核实际差异/证据，有问题直接修，不追加DeepSeek返修/回审。
- 迁移准备须固定新候选claim前过滤、同manager/原Popen/私有drain/KIMI_CODE_HOME隔离，保本角色“Kimi k2.8”与自己任务档，未声明处如实为产品默认review；原本人Key仅可信原产物窄读认证，不从DB秘密列抄/重签。只读matrix/可审步骤/隔离假件，不能登录/doctor/模型调用/native目录写、生产API/DB写、改能力/补录/启停或接单，交付partial须明确缺口。
- usage-gate本次continue，captured_at=2026-10-17T07:07:01.505738Z、两百分比null，不当0/臆测用量；wrapper改变cwd导致首次相对输出路径失败，改绝对路径重读保存成功。当前不主动等待/轮询，用户通知“263好了”后收取。基线865跟踪SHA、3实现/6协调docs白名单与完整派发/公开盘点见remaining-role-next/coordination/，旧261/262证据保持。

## 已完成与恢复所需事实

- 旧agent:kimi-code-k28-preview已正式验收并发布11bd14e：保原ID/Key/模型/历史完成专属登录/探针、保ID补录、受管启停、262接单与人类页面三步。262结果2809/复核2810已收取，任务由当轮ins_b20c4078c97b完成；人类随后页面generation7正常关闭/generation8再ready，现ins_d86218c7cc0d、launch 4c72e06e-9ef9-45b2-a752-f520638c87e1。这里只保恢复摘要，完整经过与失败见PROGRESS_HISTORY及pilot-one/independent-review261/cutover/。
- 旧K28常驻单成员manager诊断PID11920持原Popen，API由api-launcher.py持原Popen，二者不动；PID/磁盘记录仅诊断，不能新进程认领。角色页面关闭不结束宿主；宿主收工才用私有pilot/prj_e8fe7066bbec/agent_kimi-code-k28-preview/drain.request，先正常停角色、原handles空后退出。API私有api-service/stop.request正常退出，不另起8000或删活动状态。Key/原生登录在仓库外，不入Git。
- c129a63补通用CLI受管停止文件监听/异步清理，9新增及CLI/Kimi/Codex共161项相关回归通过，Codex修正后自检；首次stop_timeout和原控制台普通Ctrl+C/原Popen恢复、原26开发件/副本与10根辅助源冻结均保留。本轮不重跑/重复累计，不声称完整日志、固定后端版本、六小时或主动等待通过。
- 259保ID补录已发布ea21d81：human-only legacy-attach只补原名册但无ProjectRole的身份，保原Key/绑定/历史、不自动配置/启动，162相关回归+2WAL证据见历史。新页面K2.8已有managed登记，不能套该补录。
- 260宿主配置已发布42738d9：逐runtime模板、内置默认21600/可覆盖、真实parser/argv/诊断同一快照；custom旧兼容与身份/choice/owner/原生核验守卫保持，74相关验证见历史。共享runner control_kind已获明确批准改managed_cli，adapter_status仍unverified，不代替新角色独立登录/能力事实。完整合同见ROLE_HOST_RUNTIME_CONFIGURATION_DESIGN、ROLE_SERVICE_CONTRACT及ROLE_LEGACY_ATTACH_DESIGN。

## 下一步与人工门禁

1. 默认用户通知263完成后获取完整交付，确认DeepSeek暂停，再独立检查3前端路径/原始测试与下一候选可审包；先收尾该文案与准备片，发现问题由Codex直接修正/验证。当前不审读进行中的候选，不按任务创建宣称文案已生效。
2. 在本次“可开始迁移其它角色”授权内，复核后继续新页面Kimi k2.8本人Key/身份档/原生隔离/原alias核验；它已有创建登记，不重复legacy-attach。真实就绪后才固定新角色宿主启动→关闭→再启动→最小接单/回传与人工页面；缺登录或原Key来源时提出精确缺口，不重复请求总体迁移许可。
3. 新角色验收后再逐个处理agent:kimi、agent:deepseek、agent:codex，后两者最后；不得猜未配置绑定/命令或用重建替代平移。旧K28原manager/当前owner不动，所有停止保原Popen守卫，Desktop/MCP不按PID接管。完整日志/删除/T-W及255其它页面另片。

旧K28试迁移已完成并发布11bd14e；当前263首次执行已派，文案与下一候选准备尚未验收。根本轮只维护协调docs/只读盘点，未改3前端实现路径、登录/能力/绑定/角色启停或其它生产事实，不将准备/绑定/共享标记当真实迁移完成。

## 已确认待实施与保留事实

- 258准备v3已收取/独立21项及5探针通过，原256/257 needs_changes报告不收取/不追改；v1 22/v2 25/v3 35原件及256—259审查证据保持。迁移事实只能重新核实，不能拿旧准备快照当当前状态。
- 完整异常日志须脱敏持久保存类型/消息/完整堆栈/因果链及项目/角色/实例/任务/阶段关联，跨重启可追查。父进程活着不代表接单循环健康；旧K2.8原记录只有task queue worker failed:，初因仍未知。详[日志与受管需求](spec/ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)。
- 全入口默认21600及可覆盖尚未全部落地：260仅受管宿主内置配方，通用bridge仍默认600、旧手动入口另片；252旧K2.8入口已发布79096ad，运行实例实际预算未核实。手动关闭完成→启动为恢复路径，不默认无限重启/随项目启动。
- [执行预算与删除需求](spec/ROLE_EXECUTION_AND_DELETE_REQUIREMENTS.md)：角色详情删除按钮待做，删除本项目配置/专属材料并保历史消息任务成果，一个K2.8删除不影响另一个；以后重新需要须创建新角色，共享模型/登录/其它项目保持。
- 254后端已收取发布98beb9c，原250失败/3600超时证据不追改；255独立95Node/26Python/14VM和8Node变异通过、发布019bb99，静态探针原隔离遗漏与后续根补验事实保留，不外推原DB零写。详历史及.tmp/role-auto-start-frontend/final255/。
- 253→248→246已收取、revision-2仅Windows10/files零模型准备通过，真实新Kimi/模型/退出/主动等待未验；251详情发起人标签已发布84b8010、视觉反馈仍待。
- 正式安装目录可设计private子目录保存部署生成的本机凭据，升级保留、不随源码/安装包分发；开发Git仓库仍隔离。当前内部Key根禁用规则不改，不移动TALK-private。
- 本轮未读取新的精确额度；此前usage-gate返回continue但session/weekly百分比null，不当0或臆测比例。完整历史见[开发历史](PROGRESS_HISTORY.md)，恢复可说“继续项目”。
