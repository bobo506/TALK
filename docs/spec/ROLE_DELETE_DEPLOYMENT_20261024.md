# 删除角色功能的正常加载方案（2026-10-24）

状态：本机新版已正常加载，协调方加载/恢复与中断后复查通过。runtime3852、七宿主正常，仅恢复原DeepSeek gen64/ins_eb493b140f6e；同实例心跳前后推进6938.368393秒。删除路由及七角色deletion=null投影正常，七角色完整binding与286保护保持。327/328代码独立核验均已收取；本轮未提交任何生产删除，浏览器人验仍待完成。实现c61a4c4/302b637、原默认24小时4d6f4dd已随新后台加载。

## 范围

正常重载API、统一runtime和角色宿主管理器，加载已核验的删除功能，以及此前已完成的默认24小时代码。API启动通过既有init_db/create_all增量创建role_deletions表，不重写历史任务、消息、名册或绑定；页面采用role-delete-v2脚本。

沿用原DB、启动清单、凭据与日志留存配置，无新增开关或配置改写。通过既有受信human入口和原凭据文件操作，不输出配置/Key正文。短时API中断需要用户在原终端重跑原API启动命令。

本次不发删除请求、不创建验收角色、不派模型任务。七个现有角色/模型/Key绑定保留，286保持queued/accepted/paused，Kimi不派开发；既有日志留存按原策略正常运行，不手动sweep。

## 确认后的顺序与验收

1. 读取公开任务/实例/服务与worker，确认无running任务、DeepSeek idle、worker无处理中请求；记录原运行角色集合与七角色公开配置。真实执行先等结束。
2. 使用原统一入口普通stop/drain runtime及其宿主，逐项核原PID/创建时间绑定退出、角色stopped/无owner。不能正常退出则保留现场；不强杀、不接管、不CAS解除归属。
3. 用户在原终端Ctrl+C后重跑原API启动命令。旧runtime必须一并正常退出；只重启API或刷新页面不足以更新保留的旧管理器。
4. 核新API健康、runtime/worker就绪、七宿主serving、角色仍停止；公开角色响应含deletion/archived投影，无本次意外新增墓碑。只查公开响应及必要的进程/加载元数据，不读生产DB正文或原生日志。
5. 普通start仅恢复步骤1记录的原运行角色。最近公开实例是DeepSeek idle、其它六offline，恢复集合以当时服务实核为准；核新实例心跳真实推进，其它原停止角色保持停止/无owner。
6. 对照七角色binding全字段、公开角色/模型/choice投影、开发要求和286；角色凭据仅由原受信运行器正常认证，不另行直接读取或哈希。按自动审批收窄后的权限，不单独读取/哈希生产配置，不直接读取私有日志留存状态；保留未直接比较摘要的边界。新manager采用此前24小时默认代码，显式CLI覆盖仍按326已确认口径，不改生产参数。
7. 用户刷新页面确认“删除角色”入口和确认弹窗能取消，仍不提交实际删除。浏览器人验未做前如实标记；本次加载不等于生产角色删除端到端验收。

加载成功需真实API/runtime/worker/宿主就绪、原运行角色恢复且心跳推进、保护项一致。失败保留状态，按普通停启排查；不造回执或手工改墓碑/数据库。未发删除时新增空表可保留，无需破坏性回滚。独立沙箱ACL/子进程/junction限制与327原partial保留，详[实施及复核记录](ROLE_DELETE_IMPLEMENTATION_20261024.md)。

## 确认依据

[AGENTS.md](../../AGENTS.md)“每个新切片先确认”明确：“改变产品方向、扩大范围或涉及新的部署/权限/破坏性处置时，仍提交具体可审结果后确认。”用户已在328收尾后明确“确认”，随后又选择“授权上述最小访问并继续”。本次加载及最小访问已授权，不重复询问，不扩为生产配置/角色Key检查或真实删除。

## 2026-10-24 22:18：新版加载与中断后复查通过

用户在原终端完成正常API重启后，UTC12:21:12核新runtime3852（UTC12:20:41启动）及七宿主serving、worker空闲/无错，API healthz为ok/db ok/storage ok。新公开OpenAPI含删除路由，七个角色均有deletion=null且archived=false；公开角色查询成功也证实新表/投影可用，不直接读取生产数据库。加载核验时七角色均停止/无owner。

仅通过原human入口普通start恢复重载前唯一运行的DeepSeek，gen63→64、ins_eb493b140f6e/PID1804，running/ready/idle；其余六保持stopped/无owner/can_start。UTC12:22:11保存首次恢复快照。用户随后报告“刚刚断了。继续看下”，UTC14:17:39复查原runtime3852、相同七宿主与同一DeepSeek实例仍正常，API uptime7020秒；同实例last_seen_at从12:21:56.173760推进至14:17:34.542153，差6938.368393秒。此为两次真实端点观察，不声称期间逐秒监控或24小时长跑通过，未再启停。

UTC14:18重新调用TALK列表核七角色全部公开binding字段与重载前一致，身份仍agent:codex/prj_e8fe7066bbec/lead；公开角色/runner/model/choice/说明/项目要求也与原快照一致。286始终queued/accepted/paused。此前TALK工具报Automatic approval review failed: workspace out of credits，是自动审批未完成、动作未执行，不是服务不安全判定；本次同一原工具重试成功，未绕过检查。初次页面资源检查也未形成证据，本次重试才实际完成。

首页、workspace.js、workspace.css三个公开GET均HTTP200且字节SHA与当前已核验工作区一致；首页脚本为20261024-role-delete-v2。没有使用浏览器自动化或提交删除确认，页面视觉/取消确认弹窗仍待用户验收，生产角色删除端到端未做。

此前326默认86400秒代码随本次新runtime/宿主管理器加载；不为验时限另派模型任务，不声称所有运行器真实24小时长跑或旧显式覆盖均已实测。没有生产配置改写、删除请求/claim/report、手动sweep、强杀或CAS。按收窄后的最小授权，既有运行器读取原启动清单仅供原生status/stop；没有继续被拒的配置/Key摘要检查，也未直接检查私有日志policy/state。未保存/输出凭据正文；不把未完成的摘要检查写成字节一致证明。

本轮协调方加载自检通过，不冒称新增独立部署复核。327/328代码独立结果及原环境/P3限制保持，不另派任务。下一无关功能仍先说明范围/验收并确认。当前可刷新页面体验删除入口，真实删除前仍由用户指定目标并确认。

最终证据：minimal-loaded.json、minimal-restored.json、minimal-heartbeat.json、public-binding-preservation.json、public-assets.json；前序授权/普通退出证据和自动审批限制原样保留。final-checks.json逐项审计通过，manifest-deployment.json封存18份/243404字节部署JSON；42份产品/测试、64份新快照、50份原快照、327原35份及328新21份审查材料全部匹配，源侧仅合同/需求/模块说明/手册四份预期文档更新。

## 2026-10-24 20:19：已批准正常加载，原后台普通退出，待用户原终端重启API

用户已回复“确认”；自动审批随后拒绝了预检中的角色Key摘要检查与生产配置摘要读取，认为不属于原边界。已停止并禁用原预检helper，未继续这些检查；用户进一步明确选择“授权上述最小访问并继续”，仅让既有统一运行器读取原talk-runtime.json作正常status/stop，原human凭据只供正常API认证，不另行检查生产config.toml、角色Key、pointer或私有会话日志，不输出正文。

最小helper为coordination/deploy_role_delete_minimal.py，语法检查通过。通过原运行器status和公开API核原runtime4888/external、七宿主serving、worker空闲无错、无running任务，只有DeepSeek gen62/ins_723f2b7d12a6/PID7916 running/ready/idle，另外六停止；286 queued/accepted/paused。原后台普通stop于UTC12:16:59.123305提交，DeepSeek随后gen63/stopped/无owner，后台逐一drain宿主。中间三次观察仍在退出，保留drain-observation-1/2/3，不当作失败修复或最终通过。

UTC12:19:06.111375最终核原runtime4888与七宿主的14个PID/创建时间绑定全部absent；七角色均stopped/无owner/can_start，原公开角色/runner/model/choice/说明/项目要求/286投影一致。未强杀、未CAS、未改配置、未删除任何角色、未调用sweep。本轮受信入口会正常消费原凭据做认证；不宣称另行验证了配置或Key字节摘要。

现已请用户在原API终端Ctrl+C后重跑原启动命令。该API是external，Codex不接管或关闭它；收到“已重启”后核新runtime/七宿主/worker与删除公开路由和deletion=null投影，再普通恢复原DeepSeek并验证连续心跳，其余六保持停止。加载许可已明确，不重复询问；尚不能称新版已加载或24小时已运行生效。浏览器人验与生产删除端到端未做。

证据在.tmp/role-delete-v1/deployment/的authorization.json、minimal-authorization.json、precheck-limits.json、minimal-before.json、minimal-stop-precheck.json、minimal-stop-request.json、minimal-drained.json。原被拒绝的deploy_role_delete.py已加启动禁止，后续只用最小helper；不得为摘要缺口改走间接读取。
