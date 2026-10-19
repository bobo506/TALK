# 279接单轮询诊断补数复核

日期：2026-10-19（Asia/Shanghai）。首次交付由Codex独立实查后发现5项校验缺口，Codex直接修正并自检、集成及收取。**生产尚未加载**：正常批量停4角色被自动审批拒绝，待用户明确本次加载许可。280前端未纳入。

## 交付与独立实查

- task279/general，creator agent:codex，target/claimed_by agent:deepseek、instance ins_f3684f706645；result2886作者及Task Hall匹配，正文SHA256为`1c9779a72ee03e10b03a4be208a04dc20cd3c51fda7e3486b542a0f00d1bd423`，与本地合法交付一致。原partial、302通过/5沙箱错误/1跳过报告保持；UTC14:34:17.193394由原creator收取completed，不等于生产验收。
- 核189冻结源、六候选/patch SHA及白名单；额外cli/三源SHA与原908清单一致。双方新鲜idle/current_task_id=null且无queued/running后串行集成，Codex独占正式文档/Git，不读取或收取280未通知的交付。
- 每worker真实查询开始递增poll_seq，只计原回收/列表/筛选排序，成功早于锁/模型预检/执行。首次可观察、单调时钟30秒有界成功采样；连续查询失败保首末时间/次数/原始异常ref，下一次真实成功恢复一次。取消/模型等待不假报查询推进，旧异常/二次失败及服务状态/领取租约保持。
- extra.queue_poll和导出固定12键。Codex原合同正文13为计数笔误，表格一直12；现改正式合同/注释，不补未定义字段，原冻结合同/交付不追改。

## 独立发现与直接修正

原候选5独立ASGI反例全部失败，错误记录仍被算完整：非30间隔、无关event、错误phase、成功last_success_at或失败last_failure_at不等本轮finished_at。Codex确认暂停后直接收紧两个查询event/queue阶段/固定30秒与同一完成时刻校验，state严格字符串；永久ASGI回归覆盖五变体，坏记录明确projection_failed/partial。时间不要求墙钟先后顺序，保回拨事实和单调耗时。修正部分如实称Codex自检，未冒称他人独立复核。

## 验证

- 14正式Python套件285项、独立反例5项及Node下载合同24项全部通过，零失败/错误/跳过。新增单元11、真实worker11、ASGI导出6；原CLI120、managed stop9、core27、timeline16、export19/review5、API11/review11、query23、sources9、diagnostics review7通过。
- 真实worker→RuntimeDiagnostics JSONL→human-only ASGI下载覆盖失败/恢复/ref/旧null/脱敏/401/403/scope/坏extra/预算/partial，原随机回环HTTP也通过。原5项沙箱错误及1跳过本轮闭合。
- HTTP首轮继承SOCKS代理缺socksio失败，保原日志；只在测试子进程移除代理后API11通过，未安装依赖或改生产网络/测试断言。Node日志名、预检包装切分及证据汇总根路径首跑错误保留，属复核脚本问题而非产品缺陷。
- 六正式文件SHA等于已测隔离副本；旧schema/transition、API参数/权限/scope/配置、启停/领取/租约、排序/半开时区/31天、10000条/16MiB及单扫描/文件字节时间预算/partial保持。
- 证据根`.tmp/queue-poll-diagnostics-v1/independent-review/`：archive.json、原候选/报告/patch、source-result-message.json、original-probes/、corrected/、api-recheck/、node/、final-validation.json、integrated.json、collect-receipt.json、deployment-approval-rejected.json和live-unchanged.json。

## 生产边界

只读预检核原API4820/16632与五原宿主真实归属/新鲜健康、无在途任务及配置。UTC14:35:18再核4个原角色仍原世代/实例running、Codex原stopped，API/宿主/配置不变。原API没有--reload，源码合入不触发加载。

自动审批拒绝批量普通stop4角色，理由是开发授权未明确包含这次实际停服。命令在创建进程前被拒绝，无stop/marker或其它生产动作；未重试或拆分绕过。代码可审并已集成，待用户明确本次停启许可后重核前置、正常重载API并普通关启原4角色，保原关闭Codex与原宿主/归属，不强停/解除owner/改模型；核真实queue_poll下载和周期心跳后补记加载验收。

不扩大为宿主独立心跳、跨宿主/全根治理、模型/领取能力、主动等待、六小时、冷启动或跨沙箱驻留验收。
