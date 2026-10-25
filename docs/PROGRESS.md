# Project Progress

Updated: 2026-10-25 19:09（Asia/Shanghai）。按用户要求汇总进度，只读刷新现状；未新开发、派发、测试或启停服务。选择性自启动的代码复核、API补正、实际页面控件和保存已闭合，后台换代后的真实自动启动仍待验证。

## 已完成

- 日志自动清理已部署；执行默认时限固定24小时，无页面配置。两个指定旧角色（旧K2.8 Preview、WorkBuddy接入验证）删除已真实complete，331收尾保持。
- 项目角色选择性自启动已实现：初始默认false，可逐角色选择，保存影响下一次真实后台启动；本代人工停止不自动重拉，页面刷新不触发。
- 334及335独立复核通过并收取。角色页面原/agents缺startup导致控件隐藏，2产品5行已修；用户重启API后真实Chrome详情控件已可见，保存/公开回读已确认。
- 335原19份42557字节交付、197新及旧63/116/162、原332/333/334材料保持。当前产品d3c9c96，无后续产品/正式测试改动；原沙箱限制和失败历史保留。

## 当前实际状态

- UTC11:08:50只读复核：runtime11280仍12:33启动的旧进程，running/present、worker空闲/无错；DSH gen76/ins_aa6223b0735e running/ready，其它四角色停止。旧代startup_state=failed不代表新代码失败。
- 小D自启动true/revision1，由用户18:50:31保存；另四false/revision0，所有last_activation仍null。Agent未勾选/PUT，必须保留用户选择，不回写全false。
- 控件缺失/保存已真实解决；后台尚未换代，不能宣称真实自动启动或完整运行验收已完成。页面证据ui-fix1/user-restart-20261025-1850/visible.jpg，本轮只读状态ui-fix1/summary-status-20261025-1908.json。
- 五完整binding/角色公开配置及250/286最后完整核验为18:50未变：250failed/2767未收取，286queued/accepted/paused。原Agent stop/drain审批执行前拒绝，未停机或绕过；本轮没有重试或读额外私有资料。

## 下一步

1. 只需在一次正常后台重启后验证：小D按已保存true自动启动并ready/心跳推进，其它四保持停止；已自动ready就不重复手动start。API已更新，无需再次重启。
2. 用户可按已给手动步骤正常stop→确认stopped→serve。Agent不擅自重试被拒绝的停机，不强杀/CAS/清锁，不改配置/模型/Key/绑定/250/286，不覆盖用户选择。
3. 本片不再追加非阻断复核；下一无关功能先确认。用户完成后台操作后继续只读核验，本次汇总/Git收尾后结束。

详[加载与页面实证](spec/PROJECT_ROLE_AUTO_START_DEPLOYMENT_20261025.md)、[控件返修](spec/PROJECT_ROLE_AUTO_START_UI_FIX_20261025.md)和[历史](PROGRESS_HISTORY.md)。
