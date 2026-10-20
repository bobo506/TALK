# Project Progress

Updated: 2026-10-21 07:18（Asia/Shanghai）。290已完成首次独立实查、直接补正和离线集成，280项通过。collect时TALK API连接被拒绝，任务账本收取尚待补做。用户中断后明确“不要派发新任务先”；本轮只保存290，不开新片或启停服务。

## 当前状态

- 本人agent:codex/agent、lead、project `prj_e8fe7066bbec`；DeepSeek首次交付后idle/current_task为空，Codex才串行修改。页面仍旧交叉复核文本，按AGENTS最新分工；Kimi暂停新派发。
- 290 creator agent:codex、target agent:deepseek，Hall `group:task-57de85e8ddd64baeae1006f1cadfbf63`。最近可读succeeded/submitted、结果2896；完整自报与本地JSON一致。collect失败WinError10061，不将其写成completed，不重复派发。
- 产品基线ad46037，取件HEAD2d9d7f8。27原件（含4缓存）和19公开冻结SHA保持，原失败/开发自报不追改。证据`.tmp/execution-session-fallback-v1/independent-review290/`；正式变化为两Python模块/两测试和相关说明，临时目录不提交或清理。
- [290复核](spec/EXECUTION_SESSION_FALLBACK_REVIEW_290.md)：独立发现缺数掩盖非法/来源错误、未来缺数证明、旧低值覆盖高观测、回执类型异常和历史顺序问题，直接补正并保留首轮失败。最终内核170、适配76、既有Node34共280项全过，零跳过；原184用例包含其中，不重复相加。

## 已落地机制及边界

- 先同功能/工作线、scope、首轮确认及当前通道；可靠原始占比<60%续窗、>=60%下一次新窗，可靠指标可得时超过10次也不因计数强制换窗。busy/有writer/无法独占仍wait。
- 仅明确单纯缺数、分类/时间/窗口身份可核且首轮起完整计数可信时，已确认9次可发第10次、10次后下一次新窗。裸None、未知/错误分类、未来或过期证明、非法/矛盾来源、错scope或无可靠历史不备用；最后可靠高占比不能由旧低值/未知覆盖。
- 真实进入窗口的正式交办及完整首轮才计；规划/预检/工具/未发失败不计，ACK幂等/冲突不覆盖，送达后取消不倒扣。换task/指标恢复/再次缺数不清零。
- [备用API](guides/EXECUTION_SESSION_FALLBACK.md)含分类、计数/ACK/观测和显式fallback_clock/now；[总需求](spec/EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)、[内核指南](guides/EXECUTION_SESSION_KERNEL.md)、[采集指南](guides/DSH_CONTEXT_METRICS.md)及[用户手册](guides/USER_MANUAL.md)已同步。新窗完整、续窗增量和合同引用/权限保持。
- 仅离线纯函数，无真实ACK/锁/CAS/存储。未来宿主须原子持久化可靠观测与完整送达历史；漏存高占比可能错误延长备用，不能称纯函数本身保证完整性。字符串revision仅完全相同可继续。
- 采集器未加载，实际版本/home/插件/上下文数值未知；原生创建/续用、协调端增量生成、任务/MCP/API/页面及生产加载仍未接通。无真实配置/profile/会话/凭据/日志DB读取、CLI/ACP/模型/Browser调用或主动等待，不改生产角色/Key/绑定/owner。

## 恢复顺序与未完成项

1. 保持不派新任务。TALK API恢复后，只读核290仍为原结果2896且未收取，再正常collect；若仍拒绝连接，记录实际状态，不自行重启服务。已保存collect失败回执。
2. Git按本轮最终HEAD核已保存与推送；本片验证/说明已落盘，账本collect未成功要继续如实保留。
3. 新切片仍先说明目的/范围/不变项/验收并获明确确认。实机入口/版本/插件/home与挂载核验继续只是建议，未新授权/派发；真实接线与人工验收后续安排。
- 精确session/weekly额度百分比不可读，不臆测剩余；用户授权本轮只再一片。headless客户端工具T/取消排队仍未核，bridge21600和旧桌面65秒不是当前工具预算证据。
- 288/289已收取和287/285/282/279/280/278既有结果/人验保持。286仍paused、233候选不恢复/收取/集成，284关闭内核/三表保持；日志跨设备手动转移、全根留存和全入口21600待办不变。

恢复指令：继续项目（先补核290收取；不要重复派发或自动开启新片）。
