# Project Progress

Updated: 2026-10-18 19:37（Asia/Shanghai）。本快照属于独立分支codex/role-list-copy：用户要求仅精简角色列表两处文案，已实现并通过26项Node/12项Python自检；尚未合入D:/claude-test/TALK或当前页面。原目录271仍按用户通知后取件，首次本轮只读确认running/in_progress；为保持共享目录单方写，未打断DeepSeek或修改其源码/HEAD。

## 本分支列表文案补正（待271暂停后合入）

- 用户明确限定角色列表：成功状态显示“启动成功”，隐藏“（原生登录未核验）”；列表隐藏“请先「关闭」并确认已停止，再重新启动。”。仅修改workspaceRoleServiceControls列表渲染，详情提示、原生登录事实、启停守卫和后端保留。workspace.js静态版本更新。
- 独立工作区C:/Users/Administrator/.codex/worktrees/role-list-copy/TALK，基线efe3587。原共享目录只读查询271运行状态，未停任务/服务、未改原目录源文件或提交。合入前保持该隔离边界，不能让用户现在刷新就认为已部署。
- 原有用例更新后26项Node和12项Python通过；首轮Python一条旧源码写法断言失败原件保留，修正后通过。证据本分支.tmp/role-list-copy/，均为Codex自检；未使用Browser，视觉人验待合入。

## 当前身份与授权

- project `prj_e8fe7066bbec`；桌面MCP `agent:codex`、业务lead，负责协调、复核、直接修正和收尾。页面development_requirements仍为旧分工，按AGENTS最新明确约定执行，未修改生产永久要求。
- 本恢复片经用户明确“同意”由Codex在执行端离线时直接实施/验证及逐角色恢复；代码验证均为Codex自检，不称外部独立复核。本轮共享目录单方改码，未派TALK任务或启动原生模型探针。

## 271完整异常日志首片：已派，待交付

- 实际任务271，标题“完整异常日志首片：持久诊断基础与通用 bridge 接入”，creator agent:codex，target agent:deepseek，Hall group:task-34ff3ea145f74e8a9af8bdfe4b790a2d；派发时模型快照bound/deepseek-flash，初始queued/assigned，未将其称为已完成或实际模型能力通过。
- 范围：独立持久诊断基础、通用CLI bridge关键异常/队列/CLI/回报失败关联，脱敏、轮换/留存/容量与跨进程重启追溯、本地受控定位入口及针对性自测。宿主/服务端查询/页面和健康呈现后续，未声称整个日志需求完成。
- 初始基线ba46253（产品f881724），协调方补编号收尾后写dispatch-ready.json供执行者核最终HEAD；其存在且编号/基线一致前执行者仅只读。产品由DeepSeek单方首次实现，完成暂停；Codex独立复核，有问题直接修正。禁止生产服务/原生模型/Key/绑定/历史动作，不自停或重载。
- 包/派发回执：.tmp/runtime-exception-logs/coordination/{task.md,dispatch.json,dispatch-ready.json}；预期交付.tmp/runtime-exception-logs/development/delivery.json及完整TALK结果JSON，task_id须字符串271，先validate/summary --expect-task-id 271；默认用户通知后取件。

## 已完成恢复片与验证

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
3. 用户明确反馈“都显示启动成功”，五角色恢复后运行状态页面复验闭合；仅记录该反馈，不扩大为全部详情/按钮、模型实跑或跨宿主重启常驻验收。说明见[验收节](guides/ROLE_SERVICE_ACCEPTANCE.md)。原下一项“完整异常日志持久留存”首片271已按上述范围派发；后续由DeepSeek完成暂停、Codex独立复核及直接修正，原2–18顺序保持。
4. 六小时实跑、固定后端版本、主动等待T/W、冷启动恢复、跨任务原生会话复用及255完整新建首次自动ready仍待，不外推既有结果。usage-gate本轮返回continue，但session/weekly百分比均null，不能据此推断精确用量；按单片批次控制。

恢复指令：继续项目。
