# 原宿主消失后的人工恢复

适用：原受管宿主及bridge已退出，页面显示“运行状态待核实”或“关闭超时（状态待核实）”，旧归属仍在，普通启动因归属保护而拒绝。此入口是用户于2026-10-18批准的异常处置，保留普通stop必须由原Popen管理器处理的边界。实现合同见[人工恢复设计](../spec/ROLE_SERVICE_ORPHAN_RECOVERY_DESIGN.md)。

## 权限与前提

- 只有既有human操作Key可读取恢复计划或确认处置，agent调用403；Key从已有仓库外文件读取，不能放进命令行或交付。
- 在原物理宿主运行；CLI核本机hostname与原owner_host、项目/成员和manager-health精确对应。检查旧manager/bridge均不存在，未知/权限拒绝/PID仍存在均停止；检查替代宿主、同实例或原launch进程，不能靠旧PID或文件认领进程。
- 服务端在真实写锁内核原start/实例/host/世代、90秒内无心跳、目标成员没有任何项目的实际活跃queued/running任务、没有未到截止的pending/claimed启停动作。仅明确paused且queued、自身根/无parent、claimed_by/instance/claim_token/lease全为空的任务不阻挡恢复，任务本身保持暂停；running、暂停过渡、身份未知/子任务或残余领取仍拒绝。人类明确确认原进程已经停止，才记录独立审计并释放归属。
- OS检查和HTTP事务无法组成一个跨进程原子事务。CLI多次紧邻复核并检测计划/健康文件/入口源码变化，遇新事实中止；这不等于服务端自行证明OS进程退出。

## 先计划，再明确确认

在项目根运行，替换占位值；使用新操作唯一键和一个尚不存在的计划文件。`--host-entry`是该角色已审的原单角色宿主脚本，`--manager-health-file`是其原私有健康文件。

```powershell
python -X utf8 scripts/role_service_recovery.py plan --operator-key-file OPERATOR_KEY_FILE --project PROJECT_ID --member MEMBER_ID --manager-health-file MANAGER_HEALTH_FILE --host-entry HOST_ENTRY --operation-key UNIQUE_OPERATION_KEY --plan-file NEW_PLAN_JSON
```

`plan`只读服务端和OS，写一份本地计划，不发启停/恢复请求。计划含精确世代/start/实例/host、原PID诊断及本地证据指纹，不含Key、token或原生认证内容。核对人类确认依据后，显式执行：

```powershell
python -X utf8 scripts/role_service_recovery.py apply --operator-key-file OPERATOR_KEY_FILE --plan-file NEW_PLAN_JSON --confirm-stopped
```

缺确认不执行；旧计划任何关键事实变化即拒绝。输出恢复审计ID、原/新世代、确认者与时间。此动作只标记人类确认已停止，不spawn或杀进程。恢复后的默认结果是“未启动（已关闭）”；是否随后启动须依本次授权，不能自动启动。另获启动授权时，再按该角色既有宿主入口及页面/普通start启动：新管理器只持有本次新Popen，生成新launch/预分配实例，不续接旧归属。

## 服务端入口与审计

- `GET /api/projects/{project_id}/roles/{member_id}/service/recovery-plan`：human-only，只读可恢复候选及所需预期字段，不含token/argv/绝对路径。
- `POST /api/projects/{project_id}/roles/{member_id}/service/recover-stopped`：human-only；唯一键、预期世代/start/实例/host及固定确认值/原因必填。原因固定为`original_host_exited`，不接受可能误粘贴凭据的任意文本。
- 新增`role_service_recoveries`表：与状态CAS、实例标记offline同事务；原心跳时间保留，旧启动/停止动作及回执/任务原文不改。写入失败全部回滚。
- 相同操作键及载荷重放只返回原审计，不再解除后来新启动的归属；异载荷`recovery_conflict`。已恢复的旧实例再PUT返回`instance_launch_recovered`，旧ready回执仅保留只读重放，不复活旧世代。

## 拒绝后的处理

近期心跳、活动任务或未过期动作：等待其正常完成或先查清现场，不重试覆盖。世代/证据变化：保留旧计划，重新只读盘点。进程存在、权限不足、清单未知或替代宿主：先处理原宿主运行状态，不杀其它进程。恢复已成功但启动检查尚未完成：读取已保存的审计与原start请求，观察同一动作，不重复提交恢复或start。

恢复后核新manager、Popen父链、launch/实例、idle及至少一次真实周期心跳，确认原Key/绑定/模型/名称保持；页面状态另由用户验收。周期心跳不会改写首次就绪时间。宿主跨Codex沙箱服务停止后的持续驻留仍须单独验证，本入口不提供自动清理或自动接管。

2026-10-21补正：GET只读投影会把当前代次过期stop显示为关闭超时待核实，不依赖manager再次请求，也不自动释放归属。实际DeepSeek单次恢复与128项验证见[本次记录](../spec/ROLE_SERVICE_STOP_TIMEOUT_FIX_20261021.md)。
