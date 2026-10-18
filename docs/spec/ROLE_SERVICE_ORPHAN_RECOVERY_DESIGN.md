# 受管角色原宿主消失后的人工恢复

状态：2026-10-18用户明确“同意”本方案及Codex直接实施、验证后逐个恢复五角色；18:57五角色已通过产品入口恢复并正常新启动/真实周期心跳核验。相关313项Python验证通过，均为Codex自检；当前页面人验待。下列原准备事实保留，实施入口见[使用指南](../guides/ROLE_SERVICE_RECOVERY.md)。

## 原准备事实与恢复缺口（14:55历史）

- 当前项目`prj_e8fe7066bbec`，caller实核为`agent:codex`；最新页面开发要求仍为旧分工，实际按AGENTS用户最新约定执行。五角色绑定仍为bound，执行端离线。
- 五个manager与五个bridge的旧PID均经Windows只读查询返回不存在（OpenProcess错误87）；访问拒绝或查询失败不当作不存在。项目当前running/queued任务均为0。逐角色事实见`.tmp/role-service-recovery/diagnosis.json`，它仅为准备证据，实际操作前必须重采，不能把旧检查当持续有效。
- 五个manager-health最后seen_at均在本地12:05:49，仍写serving，且各manager输出/错误日志均无退出异常内容。Windows Application记录234565在12:05:50.1836385，提供者CodexSandboxService.OpenAI.Codex，内容为“The Codex sandbox service was asked to stop.”。系统上次启动为2026-10-16 21:37:18，排除本次时间窗电脑重启。共同退出与沙箱服务停止高度吻合，但尚无每个进程的退出事件/退出码，不能断言精确终止链或是谁请求停止。
- 现有`HostManager.execute_stop`必须持有原Popen；新管理器只有磁盘证明时返回unknown_owner。服务端没有异常退出后的人工解除入口，直接启动会被原归属/运行中守卫拒绝。不能把PID不存在作为认领旧Popen的依据，不能手改数据库或伪造stop报告恢复。

## 已确认的具体选择与实施

新增**human明确确认原进程已停止后解除遗留归属**的产品入口，单角色、显式操作、独立审计。它是对异常退出处置的新增权限和状态转换，不能冒称既有普通stop协议已允许。服务端只接受人的明确处置意图；本地OS采集只是处置依据，不能包装成远端服务端自动证明。

已新增`POST /api/projects/{project_id}/roles/{member_id}/service/recover-stopped`和`GET .../service/recovery-plan`，以及显式`scripts/role_service_recovery.py plan/apply`。沿用现有项目角色控制的人类鉴权边界；agent调用403。普通start/stop/claim/report及GET行为保持，现有owner核验不放宽。

请求包含操作唯一键、`expected_generation`、`expected_process_launch_id`、`expected_instance_id`、`expected_owner_host`、明确确认值与处置原因。所有字段都针对本次候选，不能通配或由“全部启动”隐式触发。公共响应、审计和诊断不得带owner/claim token、Key或原生命令/认证内容。

## 操作前提与拒绝条件

1. 本地只读计划精确核项目/member/原start/当前世代/实例及原host，分别检查原manager、bridge确实不存在，核无替代管理器或重复bridge。PID仍存在、权限不足、信息缺失、不匹配或未知均拒绝；不终止或收养任何进程。
2. 在SQLite实际写锁内重读当前状态及相关事实：原归属仍存在，世代/原start/实例/host与请求一致，目标实例关联精确且近期90秒内没有心跳，无该成员在任何项目的queued/running任务，无未到截止的pending/claimed启停动作。条件改变即409，不能把准备快照当事务中的事实。
3. 操作者必须显式确认“原宿主及执行进程已停止”；本片不提供自动释放、定时回收、过期即解除或agent代替human确认。人类确认不能伪称原宿主亲自回报了stopped。
4. 旧PID查询与数据库事务不能组成同一OS原子事务；人类确认和两次紧邻复核仍有残余窗口。实施前报告该边界；发现任一新心跳、活动进程或新动作就中止，不自动重试或覆盖。

## 原子结果与审计

- 独立新增恢复审计记录，保存操作键/请求指纹、目标原start/实例/世代/host、人类操作者、确认理由/时间与前后非秘密状态。仅新增表，旧启动/停止动作、结果正文和历史任务不追改。
- 与审计同一事务CAS递增世代，记录人工恢复的已停止状态，按正常stopped状态的一致字段释放原process_launch_id/owner_host等归属、清除当前进程诊断。当前实例可如实标记人工已确认离线；在途任务已被前提拒绝，不私自完成/取消任务。
- 不伪造一个原宿主stop/claim/report，不发还原owner token，不替原Popen建立句柄。原ready回执与失败记录保留；同操作键/同载荷幂等返回既有恢复结果，异载荷冲突，重放不能清除后来新启动的归属。
- 旧ready回执保持只读重放，已恢复的旧实例PUT拒绝`instance_launch_recovered`，不能复活已停止/新世代。恢复事务不改旧launch；后续普通start的既有过期扫描可把旧已报告启动的state置expired，原outcome/报告指纹/时间及任务正文不追改。
- 恢复入口本身只标记人工处置，不spawn。成功后才允许按既有human start→原受管host→新Popen/新launch/预分配实例的正常链路启动。

## 原恢复候选范围（14:55历史）

| 角色 | 待重核世代 | 原manager PID（现已不存在） | 原bridge PID（现已不存在） |
| --- | ---: | ---: | ---: |
| agent:deepseek | 5 | 12536 | 16712 |
| agent:kimi-code-k28-preview | 10 | 11920 | 18124 |
| agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c | 7 | 17908 | 15220 |
| agent:kimi | 7 | 17672 | 10496 |
| agent:codex | 9 | 16156 | 18204 |

五角色的原start/实例ID已保存在只读核验包；实际请求必须按实时值逐角色匹配。实际按先恢复DeepSeek、再恢复三个Kimi、Codex CLI最后的顺序完成。桌面协调聊天仍为agent:codex，不迁走桌面MCP。

## 实施与验证门禁

- 用户已确认本方案，由Codex在执行端离线条件下直接完成本恢复补正和针对性自检；不假称有外部首次交付/独立复核。先实现产品API/审计及显式CLI，生产应用前完成隔离验证和可审执行包。
- 必测agent403、错误项目/角色/host/start/实例/世代、近期心跳、活动/排队任务、在途动作、OS查询未知/权限拒绝/进程存在、双连接并发仅一方成功、审计或状态写入故障整事务回滚、幂等重放不清新owner、旧报告/实例不复活、普通启停与现有归属守卫回归。
- 验证通过并重采现场后，按用户确认的本方案逐角色执行人工恢复，再使用原已验Key/ID/模型绑定/原生HOME和入口正常启动；不重做登录、复制认证、换模型或升能力。每个角色记录新manager/launch/实例/Popen及周期心跳后再进入下一位。
- 本片恢复本次运行；宿主跨Codex沙箱服务重启持续驻留的部署方式仍须单独核验，不能把隐藏窗口当作独立生命周期证明。完整异常日志原排期保持，本恢复问题闭合后再派下一开发片。

## 本轮实施与真实恢复结果

- 产品新增独立恢复表/DTO、共享候选与事务守卫、两条human-only路由及显式CLI；CLI对本机host、原manager/bridge消失、替代入口/原实例/launch进程、计划/健康文件/源码变化多次复核，Windows短路径规范化，查询未知不冒充不存在。服务端只接受人类明确处置，不宣称远端自动完成OS证明。
- API沿原已验启动器正常重载；首次就绪收敛补仅starting可进入，周期心跳不再改写初次started_at。真实恢复为五条human:bobo审计，每条递增世代并随后正常start再递增；原manager不接管，新manager各自持有新Popen。
- 2026-10-18 18:57：DeepSeek gen7/manager18784/bridge14944；旧K28 gen12/9296/9332；页面K28 gen9/12320/9624；原Kimi K3 gen9/17932/16228；原Codex gen11/3140/7616。全部running/ready、idle无任务，逐一核真实30秒心跳及OS直接父链；原Key身份/元数据及全部公开角色/绑定配置保持。
- 313项Python相关测试已通过（分组有重叠，不重复累计），真实现场恢复证明另计；未使用Browser、未派模型任务。页面当前五角色运行状态待用户反馈；本次五条人工恢复不扩大为无限期自动解除归属授权。
- 首次反例及消费者失败均保留：Windows8.3入口识别、旧K28原Key路径、Kimi中文dry-run编码及首个健康文件一轮滞后。分别修正并验证；未以重复恢复/start掩盖失败。详`.tmp/role-service-recovery/implementation/`及历史进度。
