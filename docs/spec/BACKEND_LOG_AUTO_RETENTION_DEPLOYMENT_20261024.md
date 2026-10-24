# 新后台日志自动清理：正式启用方案

## 当前状态与可审差异

2026-10-24：本片Codex实现及自检完成，DeepSeek323独立复核complete，无必须修正项，原结果2964已收取。独立新22项和真实隔离API通过；组合105项独立104通过/1个ACL临时文件清理限制，Codex自检105通过。六项P3及历史证据保留，详[实现与复核合同](BACKEND_LOG_AUTO_RETENTION_20261024.md)。本方案尚未获正式启用确认，未改生产配置或服务。

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
