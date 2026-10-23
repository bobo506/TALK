# 后台/API统一脱敏日志：待确认部署方案

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
