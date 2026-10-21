# DSH上下文采集与内核适配调用说明

2026-10-21 23:01更新：用户要求完整可用后才完成，292已授权并派发真实纵向接线，原生续接、采集、API/MCP及ACK状态一起实施，详[292合同](../spec/EXECUTION_SESSION_USABLE_SLICE_5.md)。当前整项仍未完成，采集器未加载；本指南现有离线API/守卫继续适用，不能据此声称已可实际续用。宿主统一启动修复延至本功能整体可用/验收后。

2026-10-21 22:32更新：291入口/挂载核验已独立实查、补正并收取completed；后续实施依据改为[接线方案](../spec/DSH_CONTEXT_WIRING_DESIGN.md)及[复核记录](../spec/EXECUTION_SESSION_LIVE_ENTRY_REVIEW_291.md)。DeepSeek宿主已恢复，采集器仍未加载；默认headless当前没有跨任务resume接线。下方API/既有离线验证保持，不能把方案当真实采集或续用上线。

289已完成首次实现、独立实查、直接补正和离线验证。当前代码未加载到运行角色，真实上下文数值仍未知，不能把本文当作已经可用的用户操作入口。机制见[总体需求](../spec/EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)，验收证据见[289复核](../spec/DSH_CONTEXT_METRICS_REVIEW_289.md)。

290已完成不可得分类与窗口计数的独立实查、直接补正和离线集成，详[备用调用说明](EXECUTION_SESSION_FALLBACK.md)。unknown仍保持`context_sample=None`，新增`context_unavailability`贯通统一入口；显式非法数据和来源矛盾优先阻止备用。真实挂载/采集/任务接线未启用，API经用户允许恢复后，290已于2026-10-21 19:13补收completed；角色服务未恢复，采集器仍未加载。

## 模块与调用顺序

| 模块 | 入口 | 职责 |
| --- | --- | --- |
| `bridges/dsh_context_capture.mjs` | `createContextCapture(dependencies)`、`mountContextCapture(ctx, options)` | 读取指定live session的原生projection，跟踪来源并输出快照 |
| `bridges/dsh_context_metrics.py` | `adapt_context_snapshot(...)` | 校验快照、来源、时间及预期作用域，生成288的`context_sample`或unknown |
| `bridges/execution_sessions.py` | `plan_execution_session(...)` | 使用合法指标决定续用/新窗/等待/拒绝；详[内核说明](EXECUTION_SESSION_KERNEL.md) |

未来接线须先核实际DSH版本、有效插件和原生home，确认宿主/会话/模型及配置绑定，再在原生上下文可用时挂载。当前只对已冻结`@deepseek-ai/dsh@0.1.5-rc.2`的接口合同进行了验证；快照中的`frozen_version`和`expected_state_version=4`是兼容依据，不是当前进程已加载字节的证明。

采集器只使用`sessionProjections.snapshot(session, ["contextPressure"])`、`onChanged`、`sessions.get`及指定事件的`eventAt`/路由元数据，不扫描文件、不导出checkpoint或整个聊天。原生`snapshot()`可能materialize全部注册unit并在内存折叠已有日志/更新缓存；采集器不直接改写会话/投影、不做文件、网络、进程或模型调用。

## 原生采集器

`mountContextCapture(ctx)`从现有Cordis上下文取得`sessions`和`sessionProjections`，注册`session/event`及`session/disposed`监听。工厂入口可显式注入同一组服务与订阅函数，便于宿主组合和测试。监听必须返回可解除函数。

```js
import { mountContextCapture } from "./bridges/dsh_context_capture.mjs";

// 未来原生插件内调用；此代码不会由当前bridge自动执行。
const capture = mountContextCapture(ctx, { clock: Date.now });
const handle = capture.track(verifiedRequest);
const snapshot = capture.read(handle, {
  now: Date.now(),
  sessionGeneration: verifiedRequest.sessionGeneration,
  previousCut: lastAcceptedCut,
});
// 将snapshot交给可信调用层；本模块不发送或持久保存它。
capture.untrack(handle);
capture.dispose();
```

`verifiedRequest`的必填字符串：`nativeSessionId`、`projectId`、`targetMemberId`、`requesterId`、`continuityKey`、`workspaceIdentity`、`workspacePath`、`nativeHomeNamespace`、`runnerId`、`serviceLaunchId`、`providerId`、`modelId`、`modelBindingFingerprint`和`configPermissionFingerprint`；另需正整数`sessionGeneration`及`hostAttestation={verified:true, source:"宿主标签"}`。

`workspacePath`与native header的cwd精确比较。真实目录身份/别名解析及home/launch/runner/配置关联仍由调用层核验，不能把字符串相同当作本模块已解析真实路径。按ID精确取会话，不用“最新文件”、标题或mtime挑选；同ID对象替换、代次变化、关闭或cut倒退均不能继续当作当前。

应在待观察的原生配置和用量事件出现前track。挂载前已有值无法证明来源时刻，输出unverified；不会读取历史来补造来源，也不会拿观察时刻给旧值刷新时间。监听来源须是绑定后的已提交事件；旧回调、事件缺口、冲突重复或未提交序号阻止可靠采集。原生身份/投影读取失败返回unknown并隐藏异常原文，输入参数不合法则抛只含字段/原因的`CaptureError`。

## 快照与适配

快照schema为`talk-dsh-context-snapshot-1`、版本1，producer为`dsh_context_capture/1.0.0`。最小内容包括host关联、session/cut、原生provider/model、各指标状态及来源`seq/time`。指标状态区分known、missing、invalid、unverified和unknown；缺失不同于0，非法值不作为低占比。

- `projected_tokens`表示预计下一请求上下文；`pressure_tokens`表示最近请求prompt侧用量；`context_window`为容量。
- `observed_at`是本次读取时刻；各字段source time来自对应已提交事件。字段值不变时保留旧来源，不靠读取动作刷新。
- 原生provider/model来自`request/context`，配置/权限指纹由调用层确认；不冒充实际后端模型版本。当前严格比对原生路由与预期值，若TALK目录标识与原生provider/model不同，后续接线必须建立可核关联，不能随意改绑定或scope来绕过。
- 分子与容量独立更新；同一snapshot cut不表示同一个请求的原子观测。当前值来自registry精确cut，不使用cachedSnapshot/持久缓存作为当前事实。

```python
from bridges.dsh_context_metrics import adapt_context_snapshot

adapted = adapt_context_snapshot(
    snapshot,
    expected_scope=verified_expected_scope,
    now=explicit_now,
    max_age_seconds=explicit_max_age,
    trusted_host={"verified": True, "source": "受控宿主标签"},
)
# 同时把context_sample和context_unavailability交给统一规划入口。
# 备用还需可信完整计数与显式fallback_clock；裸None仍新窗，忙通道先wait。
```

`expected_scope`含`project_id/target_member_id/requester_id/continuity_key/workspace_identity/runner_id/native_home_namespace/service_launch_id/provider_id/model_id/model_binding_fingerprint/config_permission_fingerprint`及`native_session_id/session_generation/session_revision`。调用者须由可信当前事实独立组装预期值，不能直接从不可信快照复制后当作核验。

`trusted_host`是调用方显式确认来源，不是跨进程认证；schema/producer标签不能单独证明可信。只支持当前producer版本，未知版本保unknown。`now`和`max_age_seconds`必须显式提供，没有产品默认秒数；无效时间预算抛`ValueError`，无效快照返回unknown及原因。

Python适配核对来源序号均不晚于cut，顺序须满足当前配置→容量→压力→预计值；同序号必须同事件时间。原生字段虽独立更新，仍须能证明属于当前配置；无法证明即unknown。使用量/容量及压力来源必须在预算内，未来不接受；过期不能生成可靠指标，仅在其它来源/身份均合法时可分类为单纯不可得，另按可信计数和备用时钟判定。仅projected字段确实missing时才考虑pressure；missing状态若带显式值/来源属于矛盾输入，不得借此隐藏非法优先字段。

合法适配返回known和原始整数样本，不生成UI取整百分比；当前280项离线验证覆盖59.9%续用、60%新窗、条件备用、错误身份新窗完整和忙通道等待。基础合同引用/正文回取仍遵守288规则。读取/适配不发送消息、不创建或恢复会话、不取实际锁或修改TALK任务。

## 验证与当前限制

可执行：`node tests/test_dsh_context_capture.mjs`、`python -B -X utf8 tests/test_dsh_context_metrics.py`、`python -B -X utf8 tests/test_execution_sessions.py`；分别34、76、170项通过，共280项、零跳过。Python包含实际执行Node采集测试替身输出并送入适配器及288的跨语言验证；不依赖`.tmp`冻结副本或交付证据文件。原Node逐文件`--test` runner曾被沙箱拒绝spawn，保留原失败回执，直接运行同一node:test文件通过。

真实版本关联、有效插件/native home、采集器挂载/宿主传输和真实数值尚未核验；原生会话续用、MCP增量交办/存档、页面、锁/ACK/幂等及生产加载也未完成。当前headless客户端工具超时未知，不把bridge21600秒当工具预算；没有主动等待/取消排队适配验收。真实入口落地同片更新[用户手册](USER_MANUAL.md)并人工验收。
