# 281宿主运行证据方案复核

日期：2026-10-20 09:03（Asia/Shanghai）。281方案交付已由Codex独立实查并收取，原型不能直接进入产品。Codex只补正[本地A实现合同](ROLE_HOST_RUNTIME_EVIDENCE_DESIGN.md)，未修改原型或产品，也不把文档补正称为原型测试已修复；B服务端接收方案不批准实施。

## 来源、暂停与证据保全

- 原creator agent:codex、目标/作者agent:deepseek、项目prj_e8fe7066bbec、接单ins_a3d16c467fec、msg2888及Hall一致。结果合法talk-delivery-1/281，自报complete，全文与本地delivery.json完全相同；SHA8217945f7ad5b3d28b2c215538e50971d9680761aff5658e2caa2b5f5639a8cf，稳定引用复核ok。
- UTC00:56:18.673902该实例已idle/current_task_id=null；Codex随后只读核方案/脚本/证据并写独立复核目录，未向原执行者派返修、未并行改产品。UTC01:03:17.285773由原creator收取为completed，仅表示方案交付已收取，不表示新增宿主能力已实现/上线。
- 原193冻结源/文档SHA、产品基线197fe7a及跟踪文件干净均核实；archive逐一复制原成果及日志，复跑在reproduction副本，不覆盖原失败、自报或原型。正式文档由Codex补正，属于自检，不称他人独立复核。

## 实查与独立反例

原两套各8项单测在副本复跑16通过、零失败/错误/跳过。冻结gap/export探针本身主要输出事实，Codex另加断言：正常只有host_started/stopped、取消无host_stopped、report二次失败仍保句柄/活Popen、角色导出不含manager/unknown/任意extra、行/字节限额明确partial。私有ACL WinError 5及plain发布替身限制保持，不据此说私有存储通过。

独立8反例针对未改原件运行：7失败、1错误、零跳过。问题及处置：

| 问题 | 原件实际表现 | 本轮处置 |
|---|---|---|
| 序号错误上限 | manager_seq=10001被_count的10000限制拒绝；默认1秒一轮约2小时47分后新快照静默消失 | A合同序号/失败计数独立于查询行数，1..2^53-1；要求21600轮实现测试 |
| launch序号边界 | launch_process允许seq=0 | A合同与manager一致、必须正整数 |
| 采样开销 | 130轮调用observe 133次，未采样也执行 | A只在真正写terminal时观测；每次最多32 poll/256元数据检查，并验公平选择 |
| 失败伪装空集合 | observe抛错被换成held=0且truncated=false | A整体未知全null/true；缺失不能当精确0 |
| launch身份混用 | handle键launch-a、record.launch-b/其它项目仍产角色观测 | A核project/host/原键/原Popen PID/member/instance，不匹配不归因 |
| 同轮开始/完成冲突 | receiver以manager_seq唯一严格递增，同轮两条返回422 | B不采纳该水位；后续以独立事件序号/稳定ID处理，循环seq保关联 |
| 嵌套host伪造 | 外层已认证host、manager_run.host=other仍返回200 | B后续必须全层scope匹配，不批准现原型 |
| 幂等键跨host冲突 | 不同host使用相同batch_id返回409，存储字典仅按batch_id | B后续按project/host/run/batch命名空间且事务原子；现原型不批准 |

静态实查另补：原生Windows退出码可超有符号int32，A合同保平台真实范围；旧host业务入参不能因新增诊断严格正则而失败；未处理动作异常不能污染poll失败计数；finally不额外改变worker异常退出行为；新快照限频不代表旧异常事件或全根空间已治理。这些是实现验收要求，未冒称已经跑过产品分支。

## 可进入的下一片

仅A本地采集：既有schema上固定manager_run/launch_process，主循环真实边界、60秒采样、原Popen只读观测、取消/异常原因。固定四产品文件白名单，无HTTP/DB/认证/页面/配置变化，无生产启停/模型调用/清owner。received_at不填；新host凭据/接收/manager查询/跨宿主来源和全根治理留后续合同，不由原型自动授权。

实际隔离CLI核验1项：同一fixture默认--json摘要无extra，加--detail后可见manager_run。原设计只写--json不足，A合同已纠正。原接收原型不复用下载限额/并发事务/离线outbox的声明，相关能力留未验。

证据根.tmp/host-runtime-evidence-v1/independent-review/：archive.json、original-candidate、source-result-message、reproduction、negative-original.log/json、cli-summary/detail、verification、stable-result-reference、collect-receipt。原报告/原型和8反例保持原状；没有“补正后8反例全过”的结论。下一片由执行者依补正合同首次实现，自测后暂停，再由Codex独立实查。
