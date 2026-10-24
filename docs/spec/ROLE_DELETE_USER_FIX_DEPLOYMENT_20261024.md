# 删除人工验收返修的正常加载与两目标验证（2026-10-24）

状态：329代码独立复核complete/2973，已于UTC15:42:57收取completed；实现4ef58bc已推送，产品无新增修改。本方案已准备，尚未重载API/runtime、未再次提交真实delete/retry。用户此前指定删除两角色的意图保持；本次新的正常重载按AGENTS要求另行确认。

## 精确范围和最小访问

- 加载旧K2.8历史实例证明、预算自动分批、v3页面列表立即移除的既有修复，不开发新功能，不改日志/24小时默认/模型选择或其它角色配置。
- 删除目标仅 `agent:kimi-code-k28-preview`（Kimi Code · K2.8 Preview 执行）与 `agent:workbuddy`（WorkBuddy接入验证）。另两个独立身份 `agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c`、`agent:prj-e8fe7066bbec.workbuddy-k3-61b7e314`，以及Codex、DeepSeek、agent:kimi保持。
- 既有运行器通过原 `.venv/Scripts/python.exe -B -X utf8 -m scripts.talk_runtime status/stop --config D:/claude-test/TALK-private/talk-runtime.json` 正常消费启动清单，stop使用其原 `--apply` 入口。只提取运行元数据；不由协调helper另行打开/哈希清单、生产config.toml、pointer、私有state或原生会话日志。
- 原human凭据仅供正常API认证，不输出或哈希角色Key。精确目标的专属资源读取/清理由现有受信runtime按产品归属、lease、路径/句柄守卫执行；协调方不额外检查私有目录或手工删除文件。
- 不改DB/墓碑、不CAS、不强杀、不手工claim/report或伪造关闭证明；不手动sweep。286 queued/accepted/paused保持，Kimi不派开发。

## 确认后的顺序

1. 公开API重新确认human身份、七角色完整公开投影/绑定、服务与实例、无running任务；原runtime status确认worker无处理中请求/错误。恢复集合预期仅DeepSeek，必须是running/ready/idle且心跳新鲜；如出现其它运行角色或忙任务，先保留现场，不擅自扩大停启。
2. 从原统一入口普通stop/drain。按原PID/创建时间绑定证明runtime及其所有已有宿主正常退出，角色stopped/无owner。当前原七宿主中WorkBuddy已因用户删除归档，不能用“仍在名册”就忽略已有旧进程；全部按实际before记录核退出。无法证明退出则停止加载，不强杀或解锁。
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

确认依据：[AGENTS.md](../../AGENTS.md)“每个新切片先确认”规定：“改变产品方向、扩大范围或涉及新的部署/权限/破坏性处置时，仍提交具体可审结果后确认。”本次代码修复与复核已完成；新的生产正常重载尚未批准，上轮许可不自动延伸。本次确认仅覆盖上述最小正常访问/加载和完成用户已指定的两个删除目标，不扩大下一功能。

独立证据与限制见[本次修正和329收尾](ROLE_DELETE_USER_FIX_20261024.md)。
