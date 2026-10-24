# 删除人工验收返修的正常加载与两目标验证（2026-10-24）

状态：用户已正常重启原API，新runtime11200/六宿主与worker健康。WorkBuddy正式重试已complete并从角色接口移除；DeepSeek已恢复gen66/ins_203aa34895b9/ready/idle、同实例心跳推进90.105977秒。旧K2.8仍被历史250 failed/failed误当活动任务阻挡；Codex补正143自检通过，待DeepSeek定向复核及后续API正常加载。250原任务/结果保持，当前没有开启下一自启动片。

## 2026-10-25 00:39：WorkBuddy真实删除通过，旧K2.8发现失败历史兼容缺陷

用户已回报原终端正常重启API。UTC16:27:42核runtime11200（新PID）/六宿主serving/worker无错、API健康，完整非service公开投影/要求与before保持，旧WorkBuddy failed墓碑不创建宿主；角色均停止无owner。

正式旧K2.8删除通过原实例门后，被role_has_active_tasks拒绝，未创建墓碑/清绑定。只读公开任务元数据发现唯一250，2026-10-16已failed/failed/finished、lease空；collect-result只接受submitted，所以不能靠普通收取消除误拦。历史“不收取/追改250”保持，没有生产collect/cancel/resume或改库。两次公开250任务/结果逐字段一致。

因此先完成无关的另一目标：UTC16:30:05对agent:workbuddy的原failed墓碑正式重试，r3 pending，r4/5 cleaning及private_state pending被实际观测，UTC16:32:32.772268终态r6 complete，credentials preserved、identity_disabled=false，全部其它清理步骤complete。此为正常runtime多轮实际清理与正式回执，不是隔离用例或手工补证；角色接口已经不再返回WorkBuddy。

仅普通start恢复原DeepSeek，gen66/ins_203aa34895b9/PID8092 running/ready/idle，heartbeat前后90.105977秒，六宿主仍serving/worker无错；其它五个现存角色停止。两目标之外五角色完整公开配置/绑定/要求与before一致，286 queued/accepted/paused，K2.8仍原绑定/无deletion。

Codex现仅补正已终止失败历史分类，保留250原failed状态/结果，143项隔离相关自检通过，待冻结交DeepSeek独立复核；详[必要补正合同](ROLE_DELETE_FAILED_TASK_HISTORY_20261025.md)。新守卫尚未加载，329原代码/报告及旧快照不改。用户条件下一片仍已授权，但当前两个目标验证未全部完成，不提前开片。

## 2026-10-24 23:55：已正常退出，待原终端重启API

用户在紧接正常加载确认问题的上下文中回复：“验证好无误后你可以继续开下一个切片，你开发deepseek复核，我要离开下，回来再验收”。按本轮具体方案继续当前最小正常访问/加载与两个已指定目标的删除验证；同时仅在当前真实验证完成后，允许一个后续选择性项目自启动切片的开发/自测及DeepSeek独立复核。人工验收延后，不重复请求下一片确认，不扩为连续多个新功能或其它生产权限。

UTC15:51:24公开API/原运行器status预检：API healthz ok，runtime3852/external，worker空闲无错，无running任务，DeepSeek gen64/ins_eb493b140f6e是唯一running/ready/idle，另六角色停止/无owner。实际现存宿主是六个，WorkBuddy原用户删除已完成manager步骤，所以不再位于runtime宿主集合；不能照搬此前历史七宿主数量。目标原状态仍为K2.8 deletion=null、WorkBuddy failed/revision2/cleanup_budget。

UTC15:51:56.323382只从原入口提交一次普通stop；首个观察尚在stopping，原始观察保留，不当成已退出或必须修复故障。UTC15:52:54.929592最终核原runtime3852 absent，六宿主的12个原PID/创建时间绑定全部absent，七角色stopped/无owner、DeepSeek gen65；完整非service公开角色投影/开发要求与before一致，286仍queued/accepted/paused。没有强杀、CAS、配置改写或手动清理。

API仍由原终端运行：正常status明确api_mode=external/owns_original_popen=false，普通代码reload_api及CLI reload-api均对external返回runtime_api_not_owned（scripts/talk_runtime.py），不能借新脚本接管或另起第二个API。已发操作提示，请用户在原终端Ctrl+C后重跑原命令；本次暂停来自实际缺少重启动作，不是追加许可。初次沙箱预检因PermissionError未完成，随后原最小命令在已授权访问下正常执行；没有自动审批拒绝或绕行私有检查。

目前仍未加载新API/清理器、未再次delete/retry两目标、未恢复DeepSeek、未派下一任务。用户完成原终端重启后直接核新runtime/六宿主与旧墓碑保持，依次正式删除K2.8和重试WorkBuddy，跟进complete并恢复原DeepSeek/心跳/其它角色保护；全部通过后才实施已授权下一片。无需为同一正常加载或该条件下一片重复确认。

实际证据在 `.tmp/role-delete-user-fix1/deployment/`：authorization.json、lifecycle.py、before.json、stop-precheck.json、stop-request.json、drain-observation-*.json、drained.json。旧50/64/79快照及327/328/329原报告不改，不覆盖旧部署证据。

## 精确范围和最小访问

- 加载旧K2.8历史实例证明、预算自动分批、v3页面列表立即移除的既有修复，不开发新功能，不改日志/24小时默认/模型选择或其它角色配置。
- 删除目标仅 `agent:kimi-code-k28-preview`（Kimi Code · K2.8 Preview 执行）与 `agent:workbuddy`（WorkBuddy接入验证）。另两个独立身份 `agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c`、`agent:prj-e8fe7066bbec.workbuddy-k3-61b7e314`，以及Codex、DeepSeek、agent:kimi保持。
- 既有运行器通过原 `.venv/Scripts/python.exe -B -X utf8 -m scripts.talk_runtime status/stop --config D:/claude-test/TALK-private/talk-runtime.json` 正常消费启动清单，stop使用其原 `--apply` 入口。只提取运行元数据；不由协调helper另行打开/哈希清单、生产config.toml、pointer、私有state或原生会话日志。
- 原human凭据仅供正常API认证，不输出或哈希角色Key。精确目标的专属资源读取/清理由现有受信runtime按产品归属、lease、路径/句柄守卫执行；协调方不额外检查私有目录或手工删除文件。
- 不改DB/墓碑、不CAS、不强杀、不手工claim/report或伪造关闭证明；不手动sweep。286 queued/accepted/paused保持，Kimi不派开发。

## 确认后的顺序

1. 公开API重新确认human身份、七角色完整公开投影/绑定、服务与实例、无running任务；原runtime status确认worker无处理中请求/错误。恢复集合预期仅DeepSeek，必须是running/ready/idle且心跳新鲜；如出现其它运行角色或忙任务，先保留现场，不擅自扩大停启。
2. 从原统一入口普通stop/drain。按原PID/创建时间绑定证明runtime及其所有已有宿主正常退出，角色stopped/无owner。实际before为六宿主（原WorkBuddy manager已清理）；全部按实际记录核退出，不按历史固定数量推断。无法证明退出则停止加载，不强杀或解锁。
3. 原API属于external，由用户在原终端Ctrl+C后重跑原命令；不再后台启动第二个API。正常启动自动带起新版runtime/worker/所需宿主。刷新静态页面不能替代API与清理器重载。
4. 公开API与元数据核新API健康、新runtime PID/创建时间、worker无错。宿主集合以未归档且已绑定角色为准：原WorkBuddy failed墓碑不得重新创建宿主，预期先为其余六个；清理两目标完成后应只剩五个。不能照搬上轮“固定七宿主/全部deletion=null”的断言；按实际before投影逐角色验证。
5. 角色先保持停止，通过原human API对两个精确目标调用 `POST /api/projects/prj_e8fe7066bbec/roles/{URL编码member_id}/delete`，正文仅 `{"confirm_member_id":"<相同member_id>"}`。旧K2.8是首次被接受的删除；WorkBuddy是原failed墓碑的正式重试。同一时刻只提交一个目标并保留回执，不调用其它成员删除或创建新角色代替。
6. 对每个目标只GET其 `/deletion` 跟踪正式runtime回执。pending→cleaning→pending表示实际有进展的分批；持续到complete或明确failed。遇fresh/live/unknown实例、占用/归属/路径失败时保留原回执，不循环重复人类delete/retry、不扩大进程处置许可。资源清理失败仍不使角色回到常用列表。
7. 两目标本次处理结束后，仅普通start恢复步骤1原运行的DeepSeek，核新实例ready/idle及真实心跳推进；其它四个保留角色保持stopped/无owner。目标清理失败时也应在可正常运行的后台恢复DeepSeek，保留failed反馈，不让无关角色长期停着。
8. 对照其它五角色完整公开binding、runner/model/choice/角色说明及项目开发要求、286状态；两个导入/共享身份预期identity_disabled=false，共享登录/模型和其它项目不随删。公开历史任务/结果仍可查；不直接读取生产DB或Key来补摘要一致证明。
9. 核首页/JS/CSS为v3，用户刷新角色页应看不到两个已接受删除角色；资源未完成时单独显示进度或失败，完成后清理记录消失。浏览器视觉仍由用户实测，API/隔离DOM证据不冒充真人浏览器验收。

## 完成判据与失败处理

加载完成须新API/runtime/worker及所需宿主就绪、DeepSeek恢复并真实心跳推进、其它五角色保护与286保持。实际删除完成须两个精确目标的正式状态均complete，普通角色接口不再返回这两行，页面角色列表亦不再出现；pending/failed仅代表已逻辑移除，不能写成专属资源已清完。

没有真实complete则保留实际阶段和错误，不能用“新版已启动”替代删除成功。删除不可恢复旧角色配置；不反向恢复墓碑或旧配置来伪造回滚。原327/328/329结果、失败与快照均保持，部署证据另写 `.tmp/role-delete-user-fix1/deployment/`，不覆盖此前材料。

确认依据：[AGENTS.md](../../AGENTS.md)“每个新切片先确认”规定：“改变产品方向、扩大范围或涉及新的部署/权限/破坏性处置时，仍提交具体可审结果后确认。”本次已给出具体方案，用户最新回复要求验证并在通过后继续下一片，覆盖本轮方案的最小正常加载/已指定两目标验证及条件后续开发；不扩为读取生产配置/角色Key摘要、接管external API、强杀/CAS或其它无关功能。原终端重启属于仍需用户执行的实际操作，不是重复申请授权。

独立证据与限制见[本次修正和329收尾](ROLE_DELETE_USER_FIX_20261024.md)。
