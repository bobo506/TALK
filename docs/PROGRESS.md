# Project Progress

Updated: 2026-10-26 10:21（Asia/Shanghai）。338忙任务退出保护已实际正常加载，部署自检完成；页面人工验收待用户刷新确认。

## 已完成

- 代码3203044已推送，338/2984独立核验收取completed，无必须修正；原自由文本MCP业务unknown及环境限制保留。
- 用户本次明确授权实际加载；原runtime4956一次普通stop首次blocked/host_stop_timeout，原后台正常重试最终shutdown complete/error空、11原PID全absent、五角色stopped/无owner。未强杀/CAS/清锁或重复stop，原失败回执保持。
- 用户原终端重启API后，API自动带新runtime18784/UTC02:17:38，五宿主serving、startup complete/worker无错、shutdown idle。未重复serve/手动start/PUT偏好。
- 小D保用户true/rev1自动gen82/ins_b65106fc9fdb/PID18580 ready/idle，同实例真实心跳推进90.075601秒；其它四false/rev0/not_selected/stopped/无owner。
- 新APIuptime168秒；八处关键源码SHA匹配338冻结且保存早于新API启动，重启后HTTP页面/app.js/workspace.js逐字节匹配，缓存20261025-role-busy-stop-v1。

## 保护与验收口径

- 五完整binding/角色配置/项目要求/自启动选择及250/286整份公开响应与加载前相同；250failed/2767未收取、286queued/accepted/paused保持，无running任务。
- 275新与旧冻结、332至338原归档零错配。产品/正式测试未改，无生产配置正文/Key摘要/DB/private/HOME/native/session/log读取；原入口与human凭据仅正常用途消费。
- 忙时禁止关闭/有限编号/关闭接受后claim拒绝，已有338独立17核心Python/31Node及正常权限19/221证据。本轮未造生产忙态，不把静态HTTP核验称真人页面验收；原19合并4E/Node EPERM及350中17旧失败保留。
- 用户明确：TALK执行中/运行器忙则挡退出，空闲正常关闭自身服务与运行器入口；运行器内部子进程由运行器负责。原生进程树新增切片已撤回，不作为后续门槛；不外推强制取消或真实断电恢复。

## 下一步

1. 用户刷新页面，确认小D仍显示启动成功、其它四保持停止。当前API与后台已完成更新，不需要再次重启。
2. 不为可选覆盖再停第二次或追加DeepSeek复核；本次正常停启许可已执行。当前仅本地文档/Git收尾，纯文档不单独推送。
3. 页面人验后，再按原排期明确下一个新功能最小范围，不重复338或重开已撤回的子进程树切片。

详[实际加载记录](spec/ROLE_BUSY_STOP_DEPLOYMENT_20261026.md)、[本片合同](spec/ROLE_BUSY_STOP_GUARD_20261025.md)、[退出指南](guides/RUNTIME_SHUTDOWN.md)及[历史](PROGRESS_HISTORY.md)。证据.tmp/role-busy-stop-v1/deployment-20261026/。
