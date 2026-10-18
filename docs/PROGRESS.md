# Project Progress

Updated: 2026-10-18 19:09（Asia/Shanghai）。用户明确反馈“都显示启动成功”，五角色恢复后的运行状态页面复验通过；313项Python自检、真实父链/周期心跳及f881724已推送证据保持。当前收尾本片并准备原排期第2项“完整异常日志持久留存”的基础与通用bridge首片。

## 当前身份与授权

- project `prj_e8fe7066bbec`；桌面MCP `agent:codex`、业务lead，负责协调、复核、直接修正和收尾。页面development_requirements仍为旧分工，按AGENTS最新明确约定执行，未修改生产永久要求。
- 本恢复片经用户明确“同意”由Codex在执行端离线时直接实施/验证及逐角色恢复；代码验证均为Codex自检，不称外部独立复核。本轮共享目录单方改码，未派TALK任务或启动原生模型探针。

## 当前完成与验证

- 已新增human-only `GET .../service/recovery-plan`、`POST .../service/recover-stopped`、独立恢复审计及显式本地CLI。原宿主/bridge不存在且无替代进程、实例心跳过期、目标成员跨项目无活动任务、无有效在途启停，才能由人明确确认后解除遗留归属；SQLite写锁内重读及世代CAS，幂等重放不清新owner，故障整事务回滚，旧实例禁止复活。
- 每条恢复由human:bobo审计，随后使用原配置和入口正常新启动；不接管旧Popen，不重做登录或复制认证，原Key/ID/名称/模型绑定保持。恢复仅处置旧归属，原ready回执/报告指纹/时间不改；后续普通start的既有过期扫描可把旧launch.state置expired。
- 首次ready补仅starting可收敛，周期心跳不再覆盖初次started_at。相关10模块共313项Python测试通过（分组重叠不重复累计），含双SQLite连接竞争、心跳竞争、晚到旧stop、审计/状态故障回滚；Windows进程实际采集及五角色真实父链/连续30秒心跳另验。未使用Browser。
- API按原api-launcher正常停止并隐藏重载，当前实际launcher7020→API包装15048，原Popen持有及autorestart=false已核。正常init_db仅增恢复审计表，角色公开配置与原快照一致。

## 五角色真实运行快照（18:57）

| 角色 | 旧世代→人工解除→新启动 | 新manager / bridge PID | 当前实例 |
| --- | --- | --- | --- |
| DeepSeek / agent:deepseek | 5→6→7 | 18784 / 14944 | ins_067081e6a036 |
| 旧K28 / agent:kimi-code-k28-preview | 10→11→12 | 9296 / 9332 | ins_e35de45bc9f0 |
| 页面K28 / agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c | 7→8→9 | 12320 / 9624 | ins_b52fd666223f |
| 原Kimi K3 / agent:kimi | 7→8→9 | 17932 / 16228 | ins_e27eac1f7e2c |
| 原Codex / agent:codex | 9→10→11 | 3140 / 7616 | ins_c1a05e4834b9 |

- 五角色均running/ready、idle，bridge直接父进程为各自新manager，新manager持有新启动Popen；每位真实last_seen_at推进且started_at保持。runner仍unverified，不把监听恢复当新增模型能力验收。
- Codex保持npm0.163.0、gpt-6.1-sol/xhigh和独立native HOME；DeepSeek保持deepseek-flash/max，两个K28保持kimi-code/kimi-for-coding各自原档，原Kimi保持kimi-code/k3/tools。桌面MCP身份未迁走。
- 五次恢复审计、配置前后/真实PID父链/心跳及失败原件在`.tmp/role-service-recovery/implementation/`，总证明`restored-all.json`。原现场诊断及沙箱事件在上一级目录；详[恢复指南](guides/ROLE_SERVICE_RECOVERY.md)、[设计与结果](spec/ROLE_SERVICE_ORPHAN_RECOVERY_DESIGN.md)。

## 历史保持、已知限制与下一步

1. 五角色11:58迁移人工验收、74ee695/2612002失联提示补正及用户提示确认保持；269/msg2823原invalid报告及已收取、270/msg2824合法补验和收取时间保持，原正文/SHA及失败记录不追改。
2. 原五宿主最后心跳12:05:49与12:05:50 CodexSandboxService停止事件吻合；尚无逐进程退出链及请求者证明。此次恢复不等于跨Codex沙箱重启常驻已验，未安装系统服务/计划任务或绕开宿主生命周期；没有无限期自动解除归属授权。
3. 用户明确反馈“都显示启动成功”，五角色恢复后运行状态页面复验闭合；仅记录该反馈，不扩大为全部详情/按钮、模型实跑或跨宿主重启常驻验收。说明见[验收节](guides/ROLE_SERVICE_ACCEPTANCE.md)。原下一项“完整异常日志持久留存”先准备基础与通用bridge首片，由DeepSeek首次执行并暂停、Codex独立复核及直接修正，原2–18顺序保持；本次尚未派发时不虚构任务号。
4. 六小时实跑、固定后端版本、主动等待T/W、冷启动恢复、跨任务原生会话复用及255完整新建首次自动ready仍待，不外推既有结果。usage-gate本轮返回continue，但session/weekly百分比均null，不能据此推断精确用量；按单片批次控制。

恢复指令：继续项目。
