# 正常退出后台与确认结果

关闭浏览器页面不会停止TALK后台。请使用当前后台对应的原配置清单执行：

```powershell
python -B scripts/talk_runtime.py stop --config <原配置清单绝对路径> --apply --wait --wait-seconds 300
```

`--wait`等待这一代后台实际退出，`--wait-seconds`是本条命令的等待预算，默认300秒，允许大于0且不超过900秒；它不修改角色执行时限或后台停止预算。不带`--wait`的原命令继续只提交停止请求、立即返回。

退出码0且JSON中`stop_status=stopped`，表示本代健康状态已确认stopped、原后台进程已确证退出。仅看到停止请求成功、角色停止或健康文件stopped，仍不能独立证明原后台进程已经结束。

回执省略健康文件中的activation_id原值；后台代际核验仍在内部精确比对，不因省略输出而改变。nested shutdown.error_code只允许代码中固定的运行器/宿主错误类别，其它内容返回null，避免把路径、Key形状值或任意坏健康字段混入回执。

下面的stop_status表适用于已经进入等待的结果。参数不合法会退出2；初始健康缺失/损坏、身份非法、项目不符或原进程无法核实时，可能先退出1并返回`ok=false + error_code`，不会产生stop_status成功回执。blocked表示本次等待提前结束；原后台可能继续正常重试，用户可查看status或再次等待。

其它等待结果退出码为1：

| stop_status | 含义与处理 |
|---|---|
| blocked | 后台正常退出受到阻挡；查看shutdown.phase与error_code及原status输出，处理原失败后沿原后台继续。 |
| timeout | 本条命令的等待预算用完；后台继续按原生命周期处理。稍后可再次运行同一等待命令或查看status，不自动强杀/清锁。 |
| incomplete | 原后台进程已退出，但没有本代完整stopped证据；按可能残留处理，不能直接重启或清理未知归属。 |
| generation_changed | 健康文件已属于另一代后台；本次等待结束，不接管或停止新代。 |
| unverified | 健康文件或身份无法确认；保留现状，恢复可核验状态后再操作。 |

`status --config <原配置清单绝对路径>`新增的`shutdown`信息依次显示waiting_startup、waiting_worker、stopping_roles、draining_hosts、stopping_api、complete；pending_members是尚待处理的所属角色/宿主。旧健康文件缺少这些字段时，等待回执阶段为unknown，不能把缺字段当成退出成功。

后台只正常关闭自己持有的角色服务/宿主，最后关闭自己持有的API；`--attach-api`模式不会关闭外部API。所有权未知、阻挡或超时继续保留原进程句柄及失败事实，不强杀、CAS恢复、接管其它实例或关闭用户独立桌面。

忙任务保护加载后，角色关闭接口在同一写事务内检查已领取任务、残余领取和当前实例占用，遇阻返回409/`role_service_busy`，页面显示阻挡任务编号或“执行占用”，角色继续运行。请等待执行结束后重试关闭；这不会自动取消任务。关闭先接受时，同项目角色或所指定的受管实例不能再领取新任务，返回`role_service_stopping`。

后台普通退出遇同一阻挡会保留原进程与API，`stop --wait`回执为blocked，`shutdown.error_code=role_service_busy`；可选`shutdown.blocking_tasks`仅含固定code、最多20个正整数task_ids、task_count及instance_busy。只看到实例占用时编号为空，不把消息指针当作任务号。原后台会继续原有退出重试；任务正常结束后才可推进，等待命令本身提前返回不代表后台已退出。旧版本没有这些字段时仍按原有限回执处理。

此保护覆盖正式已领取任务及已报告占用。未领取preflight/普通消息的完整协同退出、原生进程子链退出证明和在途任务恢复仍需后续专片验证。

本功能需后台下一次正常加载新版代码后生效；新的CLI等待也能观察既有健康文件。代码/隔离验证不代表已停启当前生产服务，真实部署按本次明确加载安排执行。
