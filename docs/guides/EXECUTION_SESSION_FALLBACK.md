# 缺上下文读数与窗口计数规则（备用已取消）

> 2026-11-03：按用户决定，缺数备用取消。可靠占比低于90%续窗，达到90%下一次投递前新窗；取不到可靠占比一律新窗（`new_context_unknown`）。旧60%/70%观测和10次备用只作历史兼容说明，不再生效。本文保留计数/分类接口的调用边界；实际用户入口见[会话复用使用说明](EXECUTION_SESSION_USAGE.md)。

## 当前判定顺序

1. 先检查同功能工作线、完整scope、首轮已确认及当前通道。不同功能/配置新窗；busy、有writer或无法独占时先wait。
2. 当前可靠占比低于90%续窗，即使已交办超过10次；达到或超过90%在下一次投递前新窗，即使只有1次。比较原始整数`used * 10 >= capacity * 9`，不使用UI取整值。
3. 指标未知（缺失、非法、过期、未来、错会话/模型/修订等）一律新窗，原因码`new_context_unknown`；不因`context_unavailability`、`window_count_state`或`fallback_clock`改变决定，也没有“最多10次”的备用上限。
4. 不按时间失效判断，只看本轮显式传入的可靠占比。新窗投递完整基础合同加本次增量，续窗只给增量和必要新Hall。

## 兼容参数与历史状态

`plan_execution_session`仍接受`context_unavailability`、`window_count_state`和`fallback_clock`，仅为兼容既有调用方；三者不参与换窗判定。缺数导致的新窗计划`window_count`为`status=not_required`、`reason_code=fallback_disabled`，字段保持齐全。

- 旧60%或70%规则保存的`threshold_met`布尔仍可读取，按原始token数重算为90%，不追改原始观测、计数或历史交付。
- `FALLBACK_LIMIT`、`UNAVAILABILITY_SCHEMA`及导出的分类常量保留；原备用判定相关私有函数自2026-11-03起不可达，仅作历史兼容，清理另片。
- `initialize_window_count`、`confirm_window_delivery`、`record_threshold_observation`仍可用于记录真实送达和可靠观测；计数不再影响换窗，规划也不会预增计数。
- 适配器仍可产出`talk-dsh-context-unavailability-1`用于诊断和留档，但内核不再用它决定续窗或换窗；不能据此宣称缺数可以续用。

## 分类与计数来源

`adapt_context_snapshot(...)`的known输出保持原`context_sample`；unknown仍为`None`，另有`context_unavailability`。分类只在有限原因、精确native ID/generation/revision和工作线配置身份匹配时可信，但即使可信也不改变当前换窗决定。

没有快照时可调用`build_metrics_unavailability(...)`生成诊断分类。`trusted_host`只代表调用层明确核验的事实，不提供跨进程认证。非法、不可信或矛盾字段不得改称缺数。

计数schema为`execution-session-window-count-1`、version为1，绑定native ID、generation及完整规范scope指纹。ACK必填`delivery_id/task_id/attempt/execution_id/body_sha256/native_session_id/session_generation/session_revision/outcome`；`delivered`、`canceled_after_delivery`、`timed_out_after_delivery`计入，送达后取消/超时不倒扣。相同回执幂等，冲突不可覆盖。

## 验证与未验证

- 六套共313项离线测试覆盖89.9%/90%/90.1%、超容量、大整数、旧60%/70%观测可读、缺数一律新窗及原通道/首轮/留档守卫。
- 真实90%高占用、生产加载和长期运行未验证；不得用离线测试外推真实比例通过。
- 若将来恢复任何备用或时间失效规则，须另立任务、更新规格并独立复核，不能沿用本页的历史行为。
