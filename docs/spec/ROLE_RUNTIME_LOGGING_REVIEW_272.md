# 272受管宿主持久诊断：独立复核与直接修正

日期：2026-10-19（Asia/Shanghai）。执行者DeepSeek；首次交付独立复核、问题修正及最终自检由Codex完成。两位执行者均已提交并暂停，未追加执行者返修/回审。

## 原交付与范围

- task272 / result2832 / agent:deepseek / ins_5f81829d3217；原报告为合法字符串任务号的complete自报，与本地delivery.json一致。原正文SHA256：`a0bd0147f6ad5858deb5952b9f5ce0624889c972c269d5de4bc63a685bee0c10`。
- 基线eec9094，首次产品改动仅scripts/role_service_host.py，新增scripts/role_service_host_diagnostics.py及tests/test_role_service_host_diagnostics.py；其余基线跟踪差异仅Codex已提交的进度文档。原文件精确副本、差异和SHA在`.tmp/runtime-logging-parallel-1/independent-review/272-original/`及original-index.json。
- 稳定RuntimeDiagnostics API/schema、server/web、claim/report合同、原Popen/owner与启停/预算守卫未改变。首次交付自报134项；不把自报或schema通过当成业务验收。

## 首次独立发现与修正

首批4项反例4失败；相对根反例另1失败。全部使用假Key、假进程与临时根，未读取生产凭据，不是已发现生产秘密泄露。

1. 动态child_environment返回的真实凭据快照未加入保护集合，裸opaque假秘密可进入spawn异常；改为预检返回后按实际child_env中敏感名称登记保护值，不遍历全宿主环境。
2. stop新领取的claim token与start旧token不同，活/已退出子进程两路径的report失败均可落入裸opaque假token；改为每次report前从实际回报参数登记本次claim/owner值。原异常对象、失败归属和句柄保持。
3. stdout/stderr目录及打开失败发生在spawn异常边界外，缺本地关联记录；补spawn_setup_failed，关闭已打开的第一条流并原样传播准备错误，不改记cli_missing、不伪报已spawn或释放归属。
4. 显式相对日志根在宿主与子进程cwd不同的情况下可能分流；策略解析时冻结为绝对路径，仍只传内置bridge真实支持参数，自定义入口argv保持。

另补第二条输出打开失败关闭第一条流、已知秘密沿原异常传播到serve外层仍受保护的针对性验证。修正后验证为Codex自检，不称外部独立回审。

## 验证与证据

- 最终6模块141项全部通过，0失败/错误/跳过：test_role_service_host、test_role_host_runtime_configuration、test_role_service_host_diagnostics、test_role_service_host_diagnostics_review、test_runtime_diagnostics、test_runtime_diagnostics_review。
- 命令：`python -X utf8 .tmp/runtime-logging-parallel-1/independent-review/run_checks.py final-regression-272-elevated tests.test_role_service_host tests.test_role_host_runtime_configuration tests.test_role_service_host_diagnostics tests.test_role_service_host_diagnostics_review tests.test_runtime_diagnostics tests.test_runtime_diagnostics_review`。最终原始日志/计数JSON保留同目录。
- 此前修正后日志相关67项通过，与141有重叠，不重复累计。原4失败及相对根1失败的日志保持；旧HTTP套件第一次导入时默认服务日志因沙箱拒绝而未进入测试，随后在导入main前改隔离日志与默认engine。受限轮在旧CLI宿主用例停滞，停止本轮自建测试进程后以正常权限完整跑通；未改测试断言来跳过原用例。
- 隔离随机回环HTTP、固定文本子进程及临时数据库/日志用于旧宿主回归；未访问/重启生产API或角色，未调用原生模型。已有测试文件未改。

## 结论与部署边界

272经独立复核后由Codex直接修正，最终自检通过并正常收取；原complete报告与失败记录保持。宿主preflight/claim/spawn/readiness/stop/report/poll/配置worker已接持久日志，具体launch与无单一角色的manager使用不同run。

`ready`记录表示本地观察本次预分配实例就绪，后续report仍可能失败；host_started/host_stopped为serve调用边界，不单独证明OS进程或接单循环健康。任务领取前模型预检的起止、公共权限查询/API/页面、健康补数和全根容量治理继续后续。

本次未重启长期宿主或五角色，新宿主代码尚未加载实机；271既有bridge日志加载证据不代替272宿主部署验收。没有新增公开日志ref字段，维护者仍用现有本地查询CLI。完整异常日志整项仍未完成。

## 2026-10-19 09:46宿主加载补验

上段保留原代码收取时边界。用户本次先正常关闭五角色，随后明确允许重启宿主；Codex实核五服务stopped、无owner/current_launch、旧bridge退出、任务空、原宿主空句柄后，逐个以drain信号正常退出，确认原manager/wrapper已退出且无同入口进程，再沿原配置隐藏启动新宿主。没有强杀、Popen接管、恢复API或角色/模型启动。

五个真实host_started记录的项目/runtime/PID、完整性及按ref回查通过；另核新进程、私有状态时间推进和配置/服务完全不变。DeepSeek 5240/rtd-844dfdc6e7-000001，旧K28 3540/rtd-ec3fc68d64-000001，页面K28 20148/rtd-f1aba574ee-000001，K3 8944/rtd-f1fe18c960-000001，Codex 16136/rtd-326554a689-000001。manager的member/instance为unknown，不能视为角色或队列健康证明。

首个操作检查器误预期instance=null，既有schema实际规范化为unknown；原失败单独保留，只修检查器并observe同一新宿主，未重复重启或改产品代码。证据`.tmp/runtime-logging-parallel-1/host-load272/`含preflight/源码SHA、逐个正常退出/spawn/ready及verified-all.json。五角色仍关闭，用户页面启动后的launch/readiness/report、bridge队列/周期心跳和新宿主接单尚未验证；本次只闭合宿主代码加载与manager日志，不扩大完整日志整项验收。
