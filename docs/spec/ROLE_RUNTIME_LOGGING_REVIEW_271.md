# 271 完整异常日志首片复核与直接修正

2026-10-18。首次执行DeepSeek，首次交付独立复核及直接修正Codex；遵循AGENTS于2026-10-17明确分工。

## 原交付与边界

- task271/creator agent:codex/target agent:deepseek，实际ins_067081e6a036领取，Hall group:task-34ff3ea145f74e8a9af8bdfe4b790a2d。结果2825由agent:deepseek提交，合法字符串task_id/complete自报，与本地交付JSON一致；源消息SHA256为377f2eca54047bc5c732b68ed7facef8d054a9bc98ed1f51605c27aa2bc9dd8a。
- 原基线efe3587，原五文件/交付包、原diff、SHA及全部失败保留于.tmp/runtime-exception-logs/independent-review271/；original首份文本快照有换行转换，original-byte-exact通过原SHA验证还原原始字节，未覆盖首份快照或开发者结果。
- DeepSeek于UTC11:36:41.139420提交并暂停后，Codex才开始共享目录修改。原自报27项新测/281相关回归、4管道环境阻断保持，不采自报为独立验收。

## 首次独立复核问题

6项隔离反例首轮为5失败、1错误，证据probes-first.log：

1. CLI先取第一行/截500字符，再脱敏。多行或长提示词变成不能精确匹配的片段，可能进入日志及公开last_error。改为完整文本先脱敏，再取短摘要，保上游脱敏标志。
2. 标准CalledProcessError/TimeoutExpired的str包含完整cmd；改为省略cmd/output，只保类型、退出码/timeout及调用帧，外围包装消息中也保护本次命令字符串。
3. 预检已附保护值，但异常传播至外层时未继续使用；repr/JSON转义后也匹配不到原多行文本。改为沿cause/context收集明确内存保护值并覆盖转义形式；本次claim令牌作为任务诊断保护值，不改变协议值。
4. 带空格的引号password字段和owner_token无法被原正则覆盖。补完整引号字段及owner/session token，不读取全环境或认证文件。
5. 文件日志与stderr都不可写时，降级打印会再抛异常。改为控制台降级失败不替换原错误、不递归日志。
6. 查询先枚举排序全根目录才开始预算。改为目录枚举即受文件数/时间约束，读取保持独立预算，受限结果明确标记。

另据代码补正：普通消息记录message_id并将task_id置null；任务CLI日志保实际租约预算；队列新轮询前清空上次任务关联；因果链达到深度上限时默认完整性标志明确不完整。原Windows短路径测试断言改为比较resolve后的同一物理路径，原失败保留。

## 修正后验证与收取

- 相关9模块293项Python全部通过，未过滤原4条Windows管道用例：runtime_diagnostics、runtime_diagnostics_review、cli_bridge、codex_bridge、kimi_bridge、pi_bridge、cli_managed_stop、managed_instance_liveness、kimi_k28_executor。7项复核回归包含原6反例和因果深度标志。
- 该293为Codex直接修正后的自检，不称他人独立回审；原首次交付独立复核未通过的事实保留。日志证明bridge-regression-fixed.log；首轮Windows8.3路径断言失败另存diagnostics-fixed.log。
- 271经原creator agent:codex工具收取，UTC2026-10-18T12:00:57.625512，succeeded/completed，结果仍2825，原正文/自报/历史失败未改。
- 未使用Browser、真实模型/网络探针或生产数据库写入；除正常收取外无服务控制。当前五个长期进程未重启，日志代码尚未加载到它们，不能将静态/隔离验证当线上生效。

## 本片完成范围与后续

持久诊断基础、通用bridge关键边界、明确本地定位、脱敏/轮换/本run保留及重启追溯已完成。默认本run事件容量为软目标，旧run与痕迹文件未实施全根目录硬上限治理；宿主显式接入、API/页面查询权限、真实健康呈现与正常部署尚待后续，整个“完整异常日志”排期项没有宣告完成。

同轮用户授权的角色列表精简已从独立7713d2b候选合入当前目录：仅列表去原生登录附注和重复关闭后重启提示，详情及owner守卫保留。26项Node/12项Python UI验证及实际静态HTTP字节核验通过；页面人验待。两片源码范围独立，271暂停前未碰共享目录前端或其HEAD。

## 20:41部署追记（不追改20:04验收历史）

用户正常重启DeepSeek后，首位新实例ins_4643da0b3d34/18396/gen9归原manager18784，旧PID退出；真实周期心跳推进180秒，启动和接单循环日志落盘及rtd-40162b2fa6-000002引用查询通过。仅DeepSeek实际加载；其余四角色未操作/待，未制造生产异常或跑模型。证据见.tmp/runtime-exception-logs/deepseek-real-load/。
