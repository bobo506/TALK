# 新建Kimi角色宿主接入与创建反馈补正

用户在页面创建K3.1 Pro角色“大K”后反馈只有“等待宿主”且无法操作。本次是该创建流程缺陷修复，由Codex处理必要接线；不另派模型验证，不更换用户已建角色，不擅自派无关开发。

实际请求role-dfd08e33de03c6212ffc722f2bf9e53c于UTC08:05:37.602741提交，08:05:40.131680已provisioned。member=agent:prj-e8fe7066bbec.k-4bf013b9，choice=rmc_04e11ae89092。自动start gen1/ee3a6c9c-938a-4c61-9f81-6bbd2637de0d从未被claim，08:07:40到期、readiness_timeout/无owner。后台18784健康且worker无错，但只有原五宿主；reconcile_hosts仅为未列成员生成WorkBuddy配方，新建Kimi无接入。原静态Kimi宿主精确锁定旧成员，不能替换其身份去处理新成员。

实现范围：增加显式启用、精确project/member/choice/alias的通用Kimi单角色宿主，复用原HostManager/Popen/claim/stop与隔离HOME规则；由统一runtime按真实角色与本人Key生成并持有新宿主。原显式配方优先，不迁移旧五宿主、不复用旧身份权限/原生会话，不复制任何凭据。页面补充等待阶段的刷新/关闭说明，创建完成后显示实际服务结果与查看角色入口，跟进在途启动直至ready/失败，保human/CAS/原请求不重建。

独立worktree C:/Users/Administrator/.codex/worktrees/kimi-role-host-fix/TALK，原D:/claude-test/TALK的339源码/295冻结和正式测试保持。339只读状态已确认succeeded/submitted/2985、UTC07:59:15交付；本次未读取报告/收取/修改339，不据runner状态称独立通过。新修正仅在隔离worktree合成测试，先形成可审查结果；生产runtime/API/其它角色不在开发阶段重启。正式加载需按最终具体方案正常关闭/恢复，不强杀/CAS/清锁，不重复创建“大K”。

保护250failed/2767未收取、286paused、用户六角色的实际绑定/模式/自启动选择和现有任务；K3.1配置登记已经用户授权完成，不借本片扩大native/HOME/session/log或Key读取。实际原生模型能力沿用户要求由后续真实开发任务使用，不添加单独模型验证；代码流程回归不消费真实模型。


当前自检：新宿主/运行时27项通过（含9新增），真实合成HTTP与原Popen进程证实正确身份启动宿主及正常drain，不调用模型。页面创建/真实模块接线40项通过（含3新）。首轮真实HTTP发现TalkHostClient包装列表边界1F已修；实际/roles公开DTO回放另补service.control_kind而非runner字段。189关联首次21F/2E保留：worker合成Key根落进被测worktree触发原守卫，另旧页面资源断言6/8在未改D盘基线同样失败；移至被测worktree外合成根并补正过期资源契约后190项关联全过，不放宽产品守卫，不冒称原失败通过。

清单新增kimi.enabled显式开关及逐成员task_profiles（默认review、tools需明确）；默认不启用、旧静态配方优先。实际加载尚未执行；原生独立HOME/登录/版本不会被新宿主伪装成通过，不复制其它角色凭据。大K原身份/choice及失败启动记录保留，最终加载后应沿普通start重试，无第二个角色/强杀/CAS清锁。


只读配置规划已用实际“大K”公开DTO回放，host_spec可生成精确成员/choice/alias配方，尚未修改生产runtime清单或执行启动。浏览器只读入口因本机kernel assets路径错误未能打开，未操作页面；实际视觉/人验待最终加载后完成，40Node是DOM接线证据。原D339的295份10454599字节源/冻结及旧归档再次零错配，仅原四协调文档已知差异。
