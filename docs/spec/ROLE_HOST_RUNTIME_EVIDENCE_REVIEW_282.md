# 282宿主本地运行证据复核与集成

日期：2026-10-20 10:01（Asia/Shanghai）。DeepSeek首次交付经Codex独立实查发现问题，确认暂停后由Codex直接修正并自检。修正版已串行合入，169项相关用例及67秒真实隔离循环通过，已收取。**现有长期宿主未重载，未完成生产加载验收；B接收/查询、C全根治理仍待。**

## 交付来源与保全

- 原creator agent:codex、目标/作者agent:deepseek、项目prj_e8fe7066bbec、接单ins_a3d16c467fec、Task Hall及msg2889一致。合法talk-delivery-1/282，自报partial，与本地delivery.json全文相同，SHA28759b6eed3cc0db19b35510eb95550b5cd964bcebf8c2f820a2245ab48c2e80。稳定引用复核ok，UTC02:01:25.578048收取completed，原partial及失败不改。
- DeepSeek UTC01:47:51.880027已idle/current_task_id=null。195冻结文件SHA及正式产品基线9c24534未变；期间003bc2a仅为用户要求的手册/进度，不混入产品差异。归档原四候选、patch、报告和evidence；复跑/修正只在independent-review/worktree，未向原执行者派返修或回审。
- 原integration.patch可apply --check。独立AST核既有diagnostics测试的原类/方法无修改，只有追加六项；测试用隔离配置和跟踪web副本，无生产配置/Key/DB读取。原ACL WinError 5、普通写替身、固定日期失败及原67.078秒证据完整保留。

## 独立实查与直接修正

原43项新增/追加用例复跑通过，但Codex独立6组边界测试暴露11处子断言失败：

| 问题 | 原交付表现 | Codex修正 |
|---|---|---|
| 启动run关联 | host_stopped/快照有manager_run_id，host_started没有 | 同一serve启动/结束/快照统一实际run ID |
| 坏单调时钟 | NaN/Inf/回拨仍写duration_ms=null的terminal | 无真实有效耗时则放弃terminal；started不冒充完成 |
| 首败时刻未知 | 后续失败记录consecutive>0但失败段起点null | 不补造首败时间，不发布不满足固定合同的对象；真实成功结束未知段 |
| 超256饥饿 | 固定扫描前256，后续原句柄长期无观测 | 有界持续迭代位置，每次最多256元数据/32 poll，稳定集合能轮到后面的原句柄；变动时失效重建 |
| 身份/非法PID | 路径形member/instance/launch或PID0仍写角色记录 | 严格有界ID/正整数PID及原键/record/原Popen匹配，非法只留未知聚合 |
| host显示截断 | 清洗/截断后的host用于scope，长原标签被排除并显示空集合 | 原标签核scope、日志标签单独清洗，不改变原业务入参 |

另补固定16+5对象严格投影、未知/计数/时间/恢复不变式；只拷贝原launch的七项身份事实，在poll前冻结，不能由可变record改写归因或透传owner。新增真实sys.exit(-1)用例，Windows返回4294967295保持原值；这些修正均为Codex自检，不称为他人独立复核。

原导出回归固定查询窗口已过，writer却读真实当前墙钟，导致零记录。Codex额外只在tests/test_runtime_diagnostics_export.py的该用例给writer与StageTimeline注入已有固定_Clock；原条数、阶段、配对、权限等断言不变。此为第五个测试文件维护，不扩大产品API或委派白名单。

## 最终验证

- 原43项：独立复跑43通过。原6组反例11处失败、修后6组全过；原始失败日志保留。
- 获准的隔离环境中，真实私有ACL/原子发布两探针通过；随后宿主、诊断/复核、通用持久日志及导出完整相关集合167项通过、零失败/错误/跳过。没有修改私有ACL发布或权限规则，没有用普通写替身冒充原路径。
- 追加真实Windows退出值及poll前身份快照两用例后，新模块/追加诊断集合51项通过。与上一集合按完整用例ID去重共169项，零失败/错误/跳过；不是把重复运行次数相加。
- 实际隔离serve 67.079秒、68真实轮；seq=[1,1,61,61]两组started/succeeded，同一run；原短命Popen alive→exited(0)，host_stopped一次/max_rounds，启动/结束run匹配、terminal耗时有效，共15项检查全过。假客户端零网络，不是生产宿主或模型/六小时验收。
- 集成五文件字节与已测副本SHA逐一一致，所有候选Python经AST解析；原195冻结文件及原交付不改。无前端/HTTP/DB/认证/来源配置变更，不重跑未变前端。

## 实现范围与使用边界

scripts/role_service_host.py接真实serve边界；新scripts/role_service_host_loop_evidence.py负责独立run/序号、固定60秒采样、失败/恢复/取消、原句柄只读观测。固定事件manager_round_snapshot与launch_process_snapshot，extra形状见[合同](ROLE_HOST_RUNTIME_EVIDENCE_DESIGN.md)。start/stop/ready/owner/租约、原动作结果/异常/worker收尾与启动配方保持，无后台假心跳、自动恢复或模型探针。

manager级member=unknown，角色导出不混入它；新对象只在本地持久日志，旧服务端allow-list不透传它们。received_at不填；CLI须--json --detail。旧数据不回填身份/时间；进程alive不等于bridge/领取/模型可用。常态新证据有界不代表既有异常事件已限频或全根容量已治理。

## 加载与人工验收门禁

本轮没有启停角色、重载API/长期宿主、清owner或重建归属。正在运行的manager已导入旧代码，单纯刷新页面、重载API或只重启bridge不足以加载本片。先核原宿主/句柄/空闲及可用的正常退出入口，再固定一次正常重载方案；既有279一次停启许可不能当本片宿主重启授权。不能拿旧PID接管或为了加载绕过归属守卫。

管理员完成经确认的正常加载后，可用原日志根在本机验证（不需新账号/Key，本地文件权限仍由管理员负责）：

1. 检查新host_started/host_stopped及manager_round_snapshot的manager_run_id一致；开始只证明进入循环。
2. 空闲正常运行超过65秒，再用维护者CLI按事件查询，应见真实seq推进与60秒采样；看launch_process_snapshot的精确launch及原进程观测。未观测/超限明确未知，不判默认健康。
3. 普通角色启停、模型绑定与原状态保护保持；没有故障条件就不在生产故意制造取消/异常。异常/回拨/ACL/report二次失败已由隔离测试覆盖。
4. 验收只闭合A加载；不据此验收B服务端接收/跨宿主来源、C全根治理或日志整项。本片收尾暂停，不自动开B/C。

维护者查询说明见[运行日志指南](../guides/RUNTIME_EXCEPTION_LOGS.md)。证据根.tmp/host-runtime-evidence-impl-v1/independent-review/：archive/原件/source-result、原43与negative失败、corrected-negative、acl-permission-probe、corrected-related167、corrected-final-loop51、real-serve-65s原JSONL/summary、integrated、stable-reference、collect-receipt。正式修正按[协作约定](../../AGENTS.md)如实称自检。
