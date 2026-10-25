# 正常退出后台与确认结果

关闭浏览器页面不会停止TALK后台。请使用当前后台对应的原配置清单执行：

```powershell
python -B scripts/talk_runtime.py stop --config <原配置清单绝对路径> --apply --wait --wait-seconds 300
```

`--wait`等待这一代后台实际退出，`--wait-seconds`是本条命令的等待预算，默认300秒，允许大于0且不超过900秒；它不修改角色执行时限或后台停止预算。不带`--wait`的原命令继续只提交停止请求、立即返回。

退出码0且JSON中`stop_status=stopped`，表示本代健康状态已确认stopped、原后台进程已确证退出。仅看到停止请求成功、角色停止或健康文件stopped，仍不能独立证明原后台进程已经结束。

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

本功能需后台下一次正常加载新版代码后生效；新的CLI等待也能观察既有健康文件。代码/隔离验证不代表已停启当前生产服务，真实部署按本次明确加载安排执行。
