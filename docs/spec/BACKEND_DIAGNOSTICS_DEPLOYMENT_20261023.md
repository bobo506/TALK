# 后台/API统一脱敏日志：部署记录与原方案

## 2026-10-24：322独立部署证据复核通过并收取

322 complete/pass，无产品修正项，结果2963已收取completed。取件核44份/895337字节源/快照零漂移、本地/远端交付JSON一致；原独立报告及限制保留于review-deployment，协调方验收在coordination/322-acceptance.json。独立47项硬检查通过；29测试中28通过、另1项测试体通过但私有ACL临时文件清理受限，不能写成29独立全过。独立实时进程元数据证明复核时新17 PID present/旧15 absent，不外推永久驻留。

报告中的配置/私有备份SHA未独立重算、生产下载仅冻结摘要解析、原生/DB/Key/私有state/日志正文未读取等权限限制保持。配置compare/replace非OS原子CAS、布尔字段证据表达、停前serving视图/固定5与另证7宿主、55/51条摘要无法逐条还原、lease仅存在性等P3观察不影响本次加载，但不作为未来自动删除的输入证明。未修改产品或重复无变化全量测试。

322实际new_no_candidate/count1、session-939f1561-b543-43c1-ab10-c7fff4c951fc，末31.9794%；不倒写为复用321。用户已将下一片新增后台根自动清理开发改回Codex/DeepSeek复核；此为新片，原部署通过不代表新根已受30天清理，也不代表完整日志整项或真实主被动完成。

## 2026-10-23 23:24：实际加载及协调方核验完成，待独立部署复核

用户已回复“已重新启动”。原终端API的healthz为ok/db ok/storage ok，新统一runtime4856/七宿主serving，worker空闲且无错误；新根生成三个run manifest，run.lease存在且无closed。只普通start恢复原DeepSeek至gen58/ins_211a91c1827a/PID860，running/ready/idle、同实例last_seen推进60.067982秒；其余六角色仍stopped/无owner。七成员及绑定全字段与部署前一致，项目开发要求未改，286仍paused。

真实human项目后台导出HTTP200，48,281字节/55条，三组件api/runtime/provision_worker齐全，项目与共享/角色归属检查通过；401/403分别符合未认证/Agent身份，导出不含核验使用的human/原DeepSeek Key。原角色合并下载HTTP200，63,521字节/69条，含51条后台事件，耗时约4.859秒；backend.scan complete、三组件齐全，但角色旧来源扫描133,481,203字节/536文件，保持scan_incomplete/source_changed/unavailable_records和truncated。后台历史仍固定backend_coverage_unverified/history_complete=false，不能据真实HTTP200称整个文件完整。

新配置SHA仍db98e42d…a8543c，未更改清理、模型、原Key或绑定。核验helper最初假定宿主argv直接携带Key文件/默认key_root，因原窄宿主显式覆写而停止；随后只解析原入口字面量KEY路径，核本人agent身份后成功验证403，没有修改/重建凭据或读取provider凭据。该中间错误是核验助手定位问题，不是产品下载失败。helper只读现有新日志/健康状态，未手动emit事件、注入故障或触发清理。

代码8149be9、配置/批准记录3f4be45均已提交推送。当前为协调方实际加载核验，尚未独立部署复核/人工体验验收，不代表完整日志整项或主被动功能完成；只将代码/安全元数据证据交DeepSeek只读审核，不扩大到生产Key/私有日志/数据库或原生会话访问。旧32份最终代码证据保持，新增部署材料单独冻结。

证据：deployment-loaded/restored/heartbeat.json、deployment-heartbeat-proof.json、deployment-exports.json、binding-preservation.json及task286-protection.json。以下23:13为当时等待点。

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
