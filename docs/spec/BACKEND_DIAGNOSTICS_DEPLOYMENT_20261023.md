# 后台/API统一脱敏日志：部署记录与原方案

## 2026-10-23 23:13：已获确认并应用配置，等待原终端重启API

用户明确回复“确认启用并正常重载”，本次部署已获授权，不再重复请求相同许可。代码8149be9已提交推送。部署前经原human身份核实无running任务、worker空闲、七个宿主serving，仅DeepSeek gen56/ins_a2b239105b97/PID10676为running/ready/idle且心跳新鲜，其余六角色stopped/无owner。

原统一runtime14584经普通stop/drain于UTC15:12:08完成stopped，原runtime及七宿主的包装器/解释器共14个原进程绑定均确认为absent，七角色全stopped/无owner/can_start。未强杀、未CAS或解除遗留归属。固定清单五宿主之外的两个WorkBuddy动态宿主也逐个核对，不以五份健康文件代替七宿主证明。

UTC15:13:08仅原子追加下方backend_diagnostics配置，旧SHA3654bdc3…bf7012d→新SHA`db98e42dd482627724825c28106697288862d7b7e6bdbb1d756fa2ec87a8543c`。解析前后差异仅该节；同DB、原runtime_diagnostics来源及runtime_log_retention完全保持。原字节副本在既有私有state目录以私有ACL保留，SHA核验一致；不复制到公开证据。产品设置只读构造校验通过，没有手动制造生产事件。

当前外部API尚待用户在原终端Ctrl+C后重跑原命令，已发送“已重新启动”操作问题。配置落盘不等于已加载，不声称三组件实际采集或本片生产验收通过。收到用户回复后，检查API、原统一后台/七宿主及worker实际加载、日志组件/归属/预算/权限和心跳，只普通start恢复DeepSeek，其余六保持停止。本次正常重载已获授权；未请求提前开启下一片。

证据：`.tmp/backend-diagnostics-export-v1/deployment/authorization.json`、`deployment-before.json`、`deployment-stop-precheck.json`、`deployment-stop-request.json`、`deployment-stopped.json`、`deployment-all-host-processes.json`、`deployment-config-applied.json`。helper只向原入口提出普通动作并记录核验，不写policy、日志事件或伪造关闭凭据。

以下为部署前原可审方案，保留其当时状态和批准配置。

## 可审结果

后台/API/配置worker的项目归属、异常结构及有界脱敏导出已实现。320独立复核发现的F1/F2/F3由Codex修正；321独立复验确认F1/F2/OBS1与F3主路径通过，另发现`cli_command_unresolved`漏登记。Codex补登记并扩展变量/条件赋值的有限错误码检查，新增真实dsh/cli/codex模板缺失分支用例；修前反例失败、修后29项针对性自检通过。该最后修正是Codex自检，未追加独立回审。320/321已收取，原partial结果2961/2962及失败证据保持。

本方案尚未执行。生产`config.toml`的SHA256仍为`3654bdc3c9a9c14d2435a9e6ada099de25e883e76c9e602a0e4cada73bf7012d`。只追加以下配置节；不调整现有五范围清理或角色/模型/Key/绑定：

```toml
[backend_diagnostics]
enabled = true
root = "D:/claude-test/TALK/logs/backend"
database_file = "D:/claude-test/TALK/talk.db"
projects = ["prj_e8fe7066bbec"]
```

该新根只分段，不自动删除；未注册到已有五范围30天/1GiB清理。历史覆盖始终明确为partial，不能补造上线前异常或开放私有原始输出。

## 确认后执行

1. 重新核对配置SHA、当前任务/领取、worker和实际运行角色；如有新活动等待安全空闲。部署前记录运行集合，目前最近实例只有DeepSeek为idle，其余六角色offline；不以此快照替代部署时检查。
2. 使用原统一入口`run.ps1 -Config D:\claude-test\TALK-private\talk-runtime.json -Action stop -Apply`正常退出原宿主/worker及运行角色。仅控制原Popen；遇占用/归属不释放即停止部署，不强杀、不解除owner、不CAS恢复。
3. 在配置SHA仍匹配时原子追加上方配置。解析差异须仅为`backend_diagnostics`这一节；只输出节名、绝对路径及SHA，不输出配置正文/Key。保留可回退的原版本，日志不删除。
4. 当前API由用户原终端运行，需用户在原终端Ctrl+C正常退出，再重跑原启动命令一次。外部API不由管理器接管，不使用reload-api或另起并行API替代。
5. API会沿已绑定原入口恢复统一宿主/worker。只通过普通start恢复部署前运行角色，原先停止者仍停止；本次重启也会加载已提交的70%会话规则，既有任务/历史决策不改。

## 加载验收与回退

核实同库/同项目与新根、API/统一后台/worker的真实启动/就绪/周期记录及当前lease，正常角色状态和心跳；检查human项目后台下载及角色合并下载的component/attribution、401/403、时间范围和明确partial原因。读取只投影允许结构，不暴露原生会话/原始输出；下载使用10秒扫描预算加返回余量，客户端单次HTTP至少15秒。生产不注入故障、不伪造旧事件，也不因零条就宣称完整。

如启用失败，将本次新增节关闭/回退后按同样正常入口重载，恢复原运行集合；不删除新日志或更改既有清理策略。未经本次正式部署确认，不写生产配置或启停服务。部署后的实际证据另行记录，代码自检不冒充生产验收。
