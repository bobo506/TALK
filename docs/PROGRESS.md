# Project Progress

Updated: 2026-10-25 18:52（Asia/Shanghai）。用户原命令启动后，API已加载335补正，实际Chrome小D详情自启动勾选框可见且由用户保存true/revision1，另四false；控件缺失/保存问题已真实闭合。原后台11280及原12PID仍未换代，下一代自动启动尚未验证；保留用户选择，不再要求API重启，不自动停启或开下一片。

## 当前事实

- UTC10:50:58公开API uptime76秒，/agents startup与/roles一致；实际用户Chrome human bobo/小D详情“随项目自动启动”checkbox可见且checked，截图ui-fix1/user-restart-20261025-1850/visible.jpg。
- 小D enabled=true/revision1/updated_at UTC10:50:31由用户保存，另四false/revision0；Agent未勾选/PUT，必须保留当前选择，不能用旧全false计划覆盖。所有last_activation仍null，尚无新runtime代自动执行回执。
- 原runtime11280仍UTC04:33:28启动，原12PID及创建时间均相同、五宿主serving，startup_state=failed/HostError是旧代状态；DSH gen76/ins_aa6223b0735e运行/idle，其它四停止。用户仅报告原命令启动，未确认后台stop/serve，事实只支持API更新，不支持后台已换代。
- 五完整binding/角色公开配置（不含服务/自启动状态）及250/286整份公开任务与18:34前相同，无running任务；250failed/2767未收取、286queued/accepted/paused，原332/333/334/335历史保持。
- 335 complete/2981已收取，19份42557字节原报告归档；197新/旧63/116/162与原332至334材料保持，产品仍d3c9c96，无新产品/测试改动。独立CreatePipe环境限制及原失败保留，不追加非阻断复核。
- 原Agent stop/drain被自动审批在执行前拒绝，未停机或绕过；本次仍只读CLI/公开API/已知PID/实际页面，没有勾选、启停、配置正文/角色Key/DB/侧账本/private state/HOME/native/log读取，前次一次例外不复用。

## 下一步

1. 控件缺失与保存已实看通过，不再要求用户刷新/重启已更新API。正常后台重启时才执行本代自动启动；当前后台仍旧，真实自动执行/完整后台加载未验。
2. 后续后台重载须尊重用户最新小Dtrue：先观察自动启动回执和ready，已就绪不重复手动start；其它四false/停止，五绑定/250/286保持。用户可按已给手动步骤正常stop→确认stopped→serve，API无需再重启。
3. 不自动重试被拒绝的stop、不强杀/CAS/清锁，不追改任务或默认覆盖选择。下一无关切片先确认；用户后续后台操作完成再只读核验。

详[加载与页面实证记录](spec/PROJECT_ROLE_AUTO_START_DEPLOYMENT_20261025.md)、[控件返修](spec/PROJECT_ROLE_AUTO_START_UI_FIX_20261025.md)和[历史](PROGRESS_HISTORY.md)。
