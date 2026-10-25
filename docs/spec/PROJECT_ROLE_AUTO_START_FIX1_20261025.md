# 项目角色选择性自启动：332集中修正（2026-10-25）

332的正式任务结果是2978/failed，原因为channel_busy；不收取、不改成成功。DeepSeek已先通过原Hall消息2977提交独立报告，REVIEW/checks证实3项必须修正、4条独立失败断言。以该真实独立产物接手修正，不能把消息交付伪造为任务正式提交。33份/99053字节原报告、探针和日志已逐项归档coordination/332-original-review/，原63份/3613416字节冻结保持。

## 集中修正

1. MF-1：runtime先用独立短超时（3秒）客户端读取OpenAPI。只有结构可信、存在原角色API而确实缺startup POST时，才标记终态unsupported并及时开放原宿主；不发送8次404，不伪称自动启动complete。路由存在但404/403/409、OpenAPI不可读/不可信时不冒充旧API，原新接口pending/冷恢复门控与限次退避保持。unsupported不能通过服务端activation验证。
2. MF-2：already_running正向要求已知boot cutoff和process_started_at，且后者在当前boot内。缺证进入原受保护恢复/失败路径，不把快速重启旧心跳当ready，不解除旧owner。
3. MF-3：过期扫描后、入队前再核runtime/lease，入队后紧邻提交再次核对；失效时同事务回滚launch和generation。未领取旧start收敛前同样核对，原人工选择/generation/归档/删除守卫保持。跨OS健康文件与SQLite不宣称绝对原子；尽量缩短事务内末次检查与提交间隔，正常runtime停止仍先失效writer再等待在途IO。

仅2产品（scripts/talk_runtime.py、server/role_startup.py）及关联正式测试/合成API夹具改动。没有新加载/启停生产、修改配置/Key/绑定/任务250/286或旧结果。

## 验证

223项关联Python通过；10项兼容/原探针通过，包含其中5项官方新兼容用例的重合与5项原独立探针，并集228项。原4条失败断言不改断言已过；新API pending对照继续保留门控。另34项定向组与关联组重合，不相加。UI未改，原58项Node证据保留，不为数字重跑。真实Windows合成后台启停包含在223中，不外推真实断电/原生模型/浏览器。

## channel_busy的只读结论及恢复边界

本轮用户只明确批准一次最小元数据核查，已执行：指定侧账本内本项目DSH通道owner_pid15992/stateheld，lease在UTC01:59:25过期，原owner现absent；332/attempt1仍started（创建UTC01:41:24）。内核即使租约过期，遇未闭环native writer仍会拒绝新任务。因此不能仅归因补充消息与正式任务重叠，也不能靠反复重派解决。

检查使用RO/query_only、仅指定列/项目通道，不调用会写schema的Store构造器，不读取token、原生会话ID/正文、Key/日志。脚本合成验证通过，结果在.tmp/project-role-autostart-fix1/channel-metadata-readonly.json。该一次许可已用，不沿用为修改账本或额外读取。

已准备一次性协调恢复脚本`.tmp/project-role-autostart-fix1/recover_332_attempt.py`，10项合成检查通过（未确认/活进程/unknown/作用域或代际变化/额外started/事务故障均拒绝或回滚，成功和幂等通过）。尚未获写入许可、尚未对生产执行。拟仅在human明确确认旧原生模型进程已结束后，锁内核对原scope hash/PID/lease/updated_at及唯一332/attempt1，再把该attempt记interrupted、关联旧window记tainted，并同事务写专用审计；通道行不删不改，主TALK任务/结果不改，旧窗口不复用。仅父bridge PID不存在不足以替代human对旧native writer的确认，不能默默放宽保护。确认不足则保持阻挡。

本轮只读与拟恢复许可分开，后者已向用户提出明确确认请求。未再次派发一个已知会被旧通道挡住的复验；待安全恢复后，发一次覆盖MF-1至3的定向复验，不再通过额外可执行消息安排重复整片首审。原332失败、2977独立failed、原日志和沙箱限制永久保留。
