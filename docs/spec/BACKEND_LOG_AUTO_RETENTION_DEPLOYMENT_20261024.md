# 新后台日志自动清理：正式启用方案

## 本片收尾：325定向复验通过并收取（2026-10-24 14:25）

325 complete/result2966已收取completed，无P1/P2或必须修正项。独立23项检查零失败：33份/760220字节新源与快照、原45份/634741字节快照、预期2helper+2guide漂移、5产品/5测试保持、真实公开schema与反例、当前7完整投影/service、原before service提取、7角色14字段binding与runner/model映射、原324 partial及历史缺口均通过。协调方取件再核全部新源/新旧快照及目录exactness、本地远端完整JSON一致，未再改产品或无关重跑；见coordination/325-acceptance.json及325-collection.json。

本片实现323通过、正常启用与部署机制324已确认，F-R1证据补正由325独立通过；代码702d47a、配置f030c6d及实际加载记录da4e4fb已推送。新backend_enabled=true与原五范围清理保持，日常自动检查，无需人工清理或再次重启。本轮仅收取与文档/Git收尾，不新增配置/权限/启停或下一个切片。

325实际reuse_session续324/session-adc88ac8-3adb-44b5-904f-35eefccdcd86、confirmed_count=2，known指标决策、基础SHA同315，末485807/1000000=48.5807%，不追写324为同窗。

限制继续保留：324原partial/2965不覆盖；9个旧展示/choice字段未记录且不可恢复，两次当前读取不冒充部署前后。325未独立访问生产角色/绑定API，其比对依据冻结公开JSON；当前要求/286只在采集断言与summary、更新verify未对旧null基线重跑均为P3，不追加修复循环。生产30天长期/未来真正到期删除、286删除分支尚未实跑，旧缺证/活跃和未闭环任务继续保护，1GiB仍是软预算；323六P3与独立104+1 ACL限制保持。不将本片写成完整日志整项或真实主被动完成。

## 324独立复核partial与角色证据补正（2026-10-24 14:01）

324原2965已收取completed，结论partial/needs_changes保留。45份/634741字节取件源/快照一致、本地远端完整JSON一致；DeepSeek已idle/无当前任务。独立确认普通drain/单字段配置/17新PID和17旧PID/首检policy-state与86400日周期/真实三活跃lease冲突32及旧关闭lease对照/原DSH心跳均通过，但F-R1（P2）指出coordinator采错字段导致7角色display_name/business_role/decision_tier/binding均null，恢复结果又漏存desired/readiness_service/can_start/can_stop，不能只凭pass布尔当全字段证据。

Codex未修改产品、配置或服务，仅修正coordination/deploy_retention.py按真实ProjectRoleListItem保存runner/model等公开静态字段；新增role_projection_evidence.py按公开Pydantic schema筛除未知凭据/argv、缺required字段或bound却缺runner/model即拒绝；verify_retention_deployment.py以后同时保存完整公开service。原45份快照及324报告不改，补采只写coordination/role-evidence-fix1/，不重跑旧脚本覆盖历史证据。

UTC06:00:17前后通过原human入口两次只读角色API采集7个完整公开投影，真实28个旧空字段反例复现、缺runner拒绝/未知Key与argv不入证据反例均过。DSH仍gen60/ins_fd018306ec1c、desired/observed=running/readiness=ready、can_start=false/can_stop=true/owner=true；其余六desired/observed=stopped、can_start=true/can_stop=false/无owner。原before.json完整service可直接提取desired/readiness/can_start等历史值，不是事后回填。七角色所有公开binding字段与既有322磁盘binding-preservation.json的before/after、323取件前TALK工具响应、当前TALK公开bindings均逐字段相等，runner/model投影与binding映射也逐字段核对通过；要求和286保持。

必须保留的历史边界：323前TALK响应是从本聊天保留值事后落盘，不能冒充当时磁盘冻结，已有更早322磁盘记录提供独立一致性佐证。部署前完整ProjectRoleListItem确实未保存，role_name/origin/identity/archived/identity_exclusive/role_description和model.choice_id/choice_source/choice_binding_mismatch的当时值无法恢复；本片不再宣称这些展示/choice字段“前后完全相同”，仅报告当前完整值与可恢复的binding/service事实。两次当前读取也不冒充部署前后读取。

原“4旧run”简写现纠正为3个旧缺证closed+1个新API未关闭run，0删除/4保护结果本身正确。324实际new_no_candidate新窗session-adc88ac8-3adb-44b5-904f-35eefccdcd86/count1、基础SHA同315、末29.9676%，不能称续323；相容优先原窗仍服从守卫。补正属于协调方自检，待DeepSeek定向复验，不提前写独立通过或开启新片；历史P3/ACL/286与长期边界保持。

## 实际加载核验通过（2026-10-24 13:23）

用户已回复“已重新启动”。新API11520健康ok，新runtime4888及全部七宿主serving，worker无错误；只普通start恢复原DSH至gen60/ins_fd018306ec1c/PID11164、running/ready/idle，同一实例真实心跳推进60.078633秒，其余六角色停止/无owner/can_start。模型/绑定/开发要求/286 paused与部署前不变。

正式API后台于UTC05:21:30.240394自动执行首次检查：status=complete、errors空，deleted_files=0、protected_runs=4（scope_or_incomplete_evidence=3、legacy_or_unclosed=1）；观察907191字节、capacity_scan=complete、over_budget=false。实际持久next_check=1792905690.240394，即2026-10-25 UTC05:21:30/本地13:21:30。policy精确为本项目/backend:project，原五角色policy完全保持；核验脚本未调用sweep或写这些文件。

新api/runtime/provision_worker三个manifest项目/member/组件/PID/启动时间匹配，进程均present，lease文件存在且只读句柄打开均遇Windows共享冲突32，证明活跃写租约持有；closed均不存在，符合尚未正常退出。新关闭声明只能在今后正常close生成，未为了验收再重启或伪造证明。首次检查早于runtime新run建立，因此protected_runs=4是当时扫描快照，不谎称覆盖随后全部6个run。

证据新增deployment-loaded/restored/heartbeat.json及deployment-backend-runs.json，配置仍428c928e…e09825。协调方生产加载自检通过，下一步按既有用户授权交DeepSeek只读独立复核这些证据；不扩大为新功能或生产故障演练。零删除是旧缺证/未关闭保护，286仍paused的项目任务保护继续有效，但本次未走到该删除分支，不能伪称生产286保护分支已触发。长期30天运行/未来实际到期删除尚待，不把本片称完整日志整项完成。

## 当前恢复点：配置已应用，待用户原终端重启API

2026-10-24 13:19：用户明确回复“确认启用并正常重载”。human:bobo实核无running任务/worker空闲，只有DSH gen58/ins_211a91c1827a/PID860运行且idle，其余六停止。原runtime4856沿普通stop/drain退出；七宿主的14个包装器/解释器进程绑定均absent，七角色均stopped/无owner，无强杀或归属CAS。

UTC05:19:40仅增加runtime_log_retention.backend_enabled=true，原SHA db98e42d…a8543c变为候选428c928edb7044e8cc7741c09a3f18a908bd8eed3365d66b109bd0f182e09825；完整解析其余字段相同，同DB/五原source/角色绑定/开发要求/286 paused保持。原字节已备份原仓库外私有部署目录，未输出Key/配置正文，未调用生产sweep或造closed/mtime。

证据在.tmp/backend-log-auto-retention-v1/deployment/的authorization.json、deployment-before.json、deployment-stop-precheck.json、deployment-drain-proof.json、deployment-invariants-before/stopped.json、deployment-config-applied.json。原脚本沙箱读取私有runtime配置被PermissionError拒绝后，按用户明确部署授权经提升执行；未发生自动审批拒绝或绕过授权。配置已落盘不等于运行采集/清理已加载。

下一步仅请用户在启动TALK API的原终端Ctrl+C正常退出并重跑原命令。回复后沿coordination/verify_retention_deployment.py只读核新API/runtime/七宿主、正式后台policy/state与due/保护结果，再通过deploy_retention.py restore普通恢复原DSH，核连续心跳；其余六保持停止。286和旧缺证run继续保护，不额外请求同一部署许可。

## 当前状态与可审差异

2026-10-24准备时：本片Codex实现及自检完成，DeepSeek323独立复核complete，无必须修正项，原结果2964已收取。独立新22项和真实隔离API通过；组合105项独立104通过/1个ACL临时文件清理限制，Codex自检105通过。六项P3及历史证据保留，详[实现与复核合同](BACKEND_LOG_AUTO_RETENTION_20261024.md)。当时尚未获正式启用确认；后续获确认及实际操作见上方恢复点。

代码、测试及本方案已随702d47a推送现有分支，生产配置不在该提交；本次仅追加已批准单字段配置与加载等待记录。

只在现有config.toml的runtime_log_retention节增加一行：

```diff
 [runtime_log_retention]
+backend_enabled = true
 enabled = true
 retention_days = 30
 max_total_bytes = 1073741824
 interval_seconds = 86400
```

只读准备脚本为.tmp/backend-log-auto-retention-v1/coordination/prepare_deployment.py，输出deployment-proposal.json；不保存完整配置/Key，不执行sweep或生命周期操作。

- 原配置SHA256：db98e42dd482627724825c28106697288862d7b7e6bdbb1d756fa2ec87a8543c。
- 单字段候选SHA256：428c928edb7044e8cc7741c09a3f18a908bd8eed3365d66b109bd0f182e09825；其它解析字段完全一致。
- 同DB仍D:/claude-test/TALK/talk.db，原五角色source与backend_diagnostics均保持。后台受控子根为logs/backend/10d7ce12e3ffe9b9616ebe9f142fe2b60f1c5b6a48a712d59dbe16d350ac2e9b，现有根存在且无祖先/后代重叠。
- 三组件api/runtime/provision_worker共享该项目子根1GiB软预算；每天检查及启动补检，30天保留，日常无需前台操作。原角色、模型、Key、绑定、权限和286不变。

## 获确认后的正常加载步骤

1. 在本片独立deployment目录保存新的运行快照，核human实际身份、任务无running、worker空闲、原运行角色idle且心跳新鲜；恢复集合以这次快照为准，当前最后核验仅DSH运行，其余六停止。状态变化或忙碌先保护，不沿用旧快照强行停服。
2. 通过原统一runtime入口正常drain，不强杀、不CAS解除归属。核原runtime及全部七宿主的包装器/解释器14个PID与创建时间绑定已absent/exited、七角色均stopped/无owner。外部API仍归用户原终端。
3. 重新核配置原SHA和单字段解析差异，旧完整字节备份只进原仓库外私有部署目录；受控临时文件fsync、再次比较原字节再replace，不声称这是OS级原子CAS。若任何不变项改变则停止套用本候选。
4. 请用户在原终端Ctrl+C正常退出TALK API，重新运行原启动命令一次。核新API/runtime/七宿主及worker健康，沿普通start只恢复步骤1确认运行的角色，核真实新鲜心跳；其它角色保持停止。
5. 只读核新后台子根由正式RetentionService生成的policy/state、启动检查/下次due/保护与删除结果；核三组件新run及活跃lease，不手写closed/policy/state或改mtime，不直接调用生产sweep。新关闭声明随以后正常退出生成，不能把活跃lease存在当作闭合删除证明。核角色绑定/权限/286与原清理范围保持，下载仍按partial解释。

若加载失败，先保留证据并正常停启处理；关闭新开关可停止未来后台清理，但不能恢复已经删除的到期events。任何进一步破坏性处置/归属解除仍另行确认。

## 实际验收边界

当前286仍paused，项目共享任务保护会保留本项目闭合后台run；任何未完成/未收取/未知或超任务预算也保护。旧后台run没有新声明，继续保留不回填。因此启用成功不承诺立刻删除，也不承诺软预算永远满足；零删除可能是正确保护结果。

生产30天长期运行及未来真正到期删除尚未实跑，不造证据。隔离测试已经验证删除、锁/任务保护、401/403/200及旧角色410；正式加载后只报告当时实际结果。完整日志整项和真实主被动切换不据本片宣称完成。
