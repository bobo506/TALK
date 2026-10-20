# 缺上下文读数时的窗口计数与备用规则

290的离线实现已完成首次独立实查、直接补正和自检，见[复核记录](../spec/EXECUTION_SESSION_FALLBACK_REVIEW_290.md)。本说明面向后续接线开发者。当前没有真实投递、ACK、存储或原生续用入口；运行角色尚未加载本机制。

## 判定顺序

1. 先检查同功能工作线、完整scope、首轮已确认及当前通道。不同功能/配置新窗；busy、有writer或无法独占时先wait。
2. 当前可靠占比低于60%续窗，即使超过10次；达到60%下一次新窗，即使只有1次。比较原始整数`used * 5 >= capacity * 3`。
3. 仅指标单纯不可得、分类与精确窗口关联、完整计数可信且最后可靠观测未达到60%时，使用10次备用。已确认9次允许第10次；已确认10次则下一次新窗。

新窗完整基础合同加本次增量，续窗仅增量和必要新Hall；任务、授权和交付分别留档。备用不改变通道、权限、范围或基础合同守卫。

## 分类来源和时间

`adapt_context_snapshot(...)`的known输出保持原`context_sample`；unknown仍为`None`，另有`context_unavailability`，schema为`talk-dsh-context-unavailability-1`、version为1。不能仅凭None或`fallback_eligible=True`续窗。

| 来源 | 可能备用的原因 |
| --- | --- |
| 已核快照适配器 | `tokens_missing`、`capacity_missing`、`used_sample_expired`、`capacity_sample_expired`、`pressure_sample_expired` |
| 可信宿主的显式能力声明 | `metrics_not_provided`、`no_usage_sample`、`runtime_unsupported` |

所有原因仍须精确核对native ID、generation、revision、工作线和配置身份。非法/不可信/矛盾字段、错误producer/schema、未来时间、来源超cut或顺序矛盾不得改称缺数。适配器先检查所有已存在的来源；缺容量也不能掩盖非法projected或错误来源。统一规划还会检查原始样本，过期不能掩盖显式非法数值。

没有快照时可使用`build_metrics_unavailability(reason_code=..., expected_scope=..., observed_at=..., trusted_host=..., producer_supported=...)`。该helper只允许表内三种宿主原因。`trusted_host`是调用层明确核验的事实，不提供跨进程认证，也不能用它将错误快照重新包装成missing。

备用规划必须传入独立的`fallback_clock={"now": explicit_now, "max_age_seconds": explicit_budget}`，没有默认预算。证明来自未来、已经过期、缺时钟或时钟无效均新窗；年龄恰等于预算有效。当前可靠指标按样本自身时间校验，不依赖备用时钟。

## 纯状态接口

```python
from bridges.execution_sessions import (
    initialize_window_count, confirm_window_delivery,
    record_threshold_observation, plan_execution_session,
)

# first_ack来自未来宿主的真实首轮送达确认，不能用计划伪造。
created = initialize_window_count(
    scope=verified_scope,
    native_session_id=verified_native_id,
    first_delivery=first_ack,
    previous_state=None,
)
state = created["state"]  # 成功首轮计1；须检查status后再接收state。

plan = plan_execution_session(
    scope=verified_scope,
    base_contract=base_contract,
    task=current_task,
    candidate=verified_candidate,
    execution_channel=verified_channel,
    context_sample=adapted["context_sample"],
    context_unavailability=adapted["context_unavailability"],
    window_count_state=state,
    fallback_clock={"now": explicit_now, "max_age_seconds": explicit_budget},
    new_messages=necessary_new_messages,
)

# 可靠观测与送达是两件事；没有投递也须保留高占比事实。
intent = plan["window_count"].get("observation_intent")
if intent:
    observed = record_threshold_observation(
        state=state, scope=verified_scope,
        observation=intent["observation"], now=explicit_now,
    )
    # 未来宿主须检查结果、原子持久化，再允许任何后续规划。

# 仅真正进入同一原生窗口后归并；本函数不会发送指令。
confirmed = confirm_window_delivery(
    state=current_persisted_state,
    scope=verified_scope,
    delivery=actual_delivery_ack,
)
```

每个结果须检查`status`、`reason_code`和`errors`；不是所有返回值都包含可替换的state。规划不会修改输入或预增次数，`proposed_ordinal`仅表示允许尝试第几次。

计数schema为`execution-session-window-count-1`、version为1，绑定native ID、generation及完整规范scope指纹，包括基础合同版本/哈希、launch、runtime/home、模型绑定和权限。计数与完整连续的`deliveries`对应，首条必须为首轮；任务号变化、读数恢复和再次缺数不清零。缺状态、零计数但首轮已确认、历史不完整、重复身份、倒序revision或错scope不能备用。

ACK必填`delivery_id/task_id/attempt/execution_id/body_sha256/native_session_id/session_generation/session_revision/outcome`，首轮另传`first_turn=True`。后续默认false。正文SHA对应实际进入窗口的UTF-8正文。

- `delivered`、`canceled_after_delivery`、`timed_out_after_delivery`计入；送达后取消/超时不倒扣。
- `failed/rejected/preflight/dry_run/planned/repeated_planning/tool_call/internal_step/canceled_before_delivery/timed_out_before_delivery`不计入。
- 同delivery或同task/attempt/execution的相同正文回执幂等；身份相同而正文/窗口不同报conflict，不能覆盖。重试不得伪造新execution当作同一确认。
- 数字revision不得回退，历史本身也不得倒序。不透明字符串revision只有完全相同才继续，无法证明先后时拒绝备用。

`record_threshold_observation(..., now=...)`不增加交办数，按原始整数计算阈值；拒绝未来观测、时间倒退及同revision/同来源时刻的冲突值。较新的可靠低占比可以替换旧高占比；裸未知不能将已知高占比清为false。规划中所有观测意图仍属于旧窗口，即使计划动作是新窗。

## 后续宿主必须完成的部分

纯函数无法证明调用者提交的是最新、完整的历史。未来宿主必须从新窗出生起保存每个真实ACK，在同一独占/CAS边界内归并计数和可靠观测，并在下一次规划前提交成功。遗漏首次高占比观测的持久化可能错误延长备用，不能笼统声称“不持久化只会更保守”；写入失败或历史覆盖未知时应撤销备用资格，不再提供该状态，走新窗或等待。

当前没有实现上述锁、CAS、存储、真实发送/ACK或旧窗口迁移；不允许凭记忆补造完整计数。采集加载、原生创建/续用、协调端增量生成、任务/MCP/API/页面仍待后续切片确认。10次不保证执行过程中上下文低于60%，也不承诺费用或缓存收益。

正式测试不依赖本机`.tmp`：内核170项、适配76项、既有Node采集34项共280项全部通过、零跳过。真实用户入口上线时仍须更新[用户手册](USER_MANUAL.md)并进行人工验收。
