# 执行会话离线内核调用说明

任务288已经实现并经独立实查、补正和自检后入库。本模块只生成计划，当前bridge/API/MCP没有导入它；此文面向后续接线开发者，不能作为已上线的操作入口。用户机制见[需求](../spec/EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)，复核与证据见[288记录](../spec/EXECUTION_SESSION_CORE_REVIEW_288.md)。

## 入口与事实来源

`bridges.execution_sessions.plan_execution_session(...)`接受显式输入，返回普通JSON对象，不读环境/文件/数据库，不启动运行器，不发送消息。实际工作区、授权、模型绑定、通道独占、原生会话及指标都由接线层核验后传入；布尔确认不是本模块自身查证的结论。

| 参数 | 内容 |
| --- | --- |
| `scope` | 当前项目、目标、发起者、工作线、真实工作区及运行配置身份 |
| `base_contract` | 基础合同`version`、UTF-8正文`sha256`，可选`text` |
| `task` | 当前任务自己的身份、目标、权限和增量正文 |
| `execution_channel` | 当前目标通道的`state=ready/busy`、`active_writer`和`execution_channel_exclusive` |
| `selection` | `new`显式新窗；`reuse`请求续用指定候选；`auto`只检查传入候选，不搜索历史 |
| `candidate` | 显式选定的原生会话快照，或`None` |
| `context_sample` | 与候选/模型/修订关联且有显式时间预算的上下文数值，或`None` |
| `new_messages` | 本次必要新Hall消息字符串数组；不放历史全文 |

所有计划都先检查当前`execution_channel`，包括无候选首轮、显式新窗和候选跨作用域的情况。缺失、状态未知、busy、有writer或独占未确认时返回`wait`，没有可执行正文。当前通道事实不能从旧候选继承。存在候选时还要检查候选自身的状态和通道事实；本模块不获取实际锁。

`scope`必填字符串：`project_id`、`target_member_id`、`requester_id`、`continuity_key`、`workspace_identity`、`runtime`、`runner_id`、`native_home_namespace`、`provider_id`、`model_id`、`model_binding_fingerprint`、`config_permission_fingerprint`、`service_launch_id`、`base_contract_version`、`base_contract_sha256`。另需`workspace_verified=True`和正整数`session_generation`。值采用规范JSON比较，不能仅将路径转小写就声称工作区已核验。

同窗口的`session_generation`保持稳定；不同任务的`task_id/attempt/execution_id`可以不同。同工作线可续用，项目/角色/发起者/工作区/运行器/home/配置/launch/会话代次/基础合同变化不续用。模型绑定指纹仅代表配置事实。

`task`必填`task_id`、非负整数`attempt`、`execution_id`、`goal`、`authorization`和`body`；可选`baseline_change`、`authorization_change`、`acceptance_difference`。权限用字符串或非空字符串数组明确提供。增量须足以结合基础合同还原本次实际要求；若此前已经变更的基线/权限仍有效，接线方须保留必要的有效差异，不能依赖未留档的旧聊天或“同上”。模块不会替调用方推断这些事实。

## 候选与上下文样本

候选字段：`native_session_id`、同结构的`scope`、`state=ready/busy/tainted/closed`、`execution_channel_exclusive`、`active_writer`、`first_turn_confirmed`和`session_revision`。首轮未确认送达时不能省略基础正文。新窗计划的原生会话ID为`None`，不冒充已经创建成功。

样本字段：`native_session_id`、`session_generation`、`session_revision`、`provider_id`、`model_id`、`model_binding_fingerprint`、`projected_tokens`、`pressure_tokens`、`context_window`、`sampled_at`、`now`、`max_age_seconds`。三个数值也支持DSH的camelCase字段名；同一字段同时提供两种写法视为歧义。

- 优先`projected_tokens`；只有字段完全缺失才考虑`pressure_tokens`。优先字段存在但非法时保持未知，不回退成低占比。
- token数是非负整数，容量是正整数，均不超过`2**53-1`；不接受bool、浮点数、数值字符串或非有限数。
- 时间为带时区ISO字符串、带时区datetime或整数epoch秒；最大年龄是显式非负整数秒，无产品默认值。错会话/模型/修订、缺失、过期或未来样本为未知。
- 接线方须分别核实分子和容量的来源可关联当前候选、模型配置和修订，才能组织上述样本。仅给一份旧投影补当前时间或会话标签不能证明其有效；token-meter各字段独立更新，不能据这个统一输入对象宣称同次请求原子采样。
- 用原始整数`used * 5 >= capacity * 3`比较。59.9%可续，60%及以上下一次投递前新窗；不使用UI取整值，没有10轮后备。
- 已有候选指标未知时，在通道可用前提下生成新窗完整计划；无候选首轮不需要旧指标。不强停正在运行的任务。

## 基础正文与引用留档

基础合同正文在接线层按版本/哈希保存一次。续窗规划可只传`version/sha256`，不会在投递或archive中复制基础正文。每个任务独立保留合同引用、本次增量、新消息及投递哈希/长度。

新窗必须提供与引用匹配的`text`。如果只传引用却需要新窗，返回`reject_base_text_required`且没有投递正文；接线层按引用取回完整基础正文，重新规划。不能把这个返回当作已新建或已经发送。传入正文时无论新/续窗都校验其SHA，不静默接受错误正文。

```python
from bridges.execution_sessions import (
    plan_execution_session,
    reconstruct_full_requirements,
)

# snapshot和合同存储由未来接线层提供；当前没有实现这些采集/保存动作。
plan = plan_execution_session(
    scope=snapshot["scope"],
    base_contract=base_ref,  # {"version": ..., "sha256": ...}
    task=snapshot["task"],
    execution_channel=snapshot["execution_channel"],
    selection=snapshot["selection"],
    candidate=snapshot["candidate"],
    context_sample=snapshot["context_sample"],
    new_messages=snapshot["new_messages"],
)
# 需要完整首轮时，按base_ref从受控存储取正文后重新规划。
# 只有new_session/reuse_session才提供delivery；wait/reject不能发送。

full_requirements = reconstruct_full_requirements(
    plan["archive"], base_contract=stored_full_base
)  # 仅在有archive时调用；显式正文须匹配引用，投递哈希/长度也须一致。
```

`new_session`对应`full`：完整基础正文＋本次增量＋必要新Hall；`reuse_session`对应`incremental`：只含增量和必要新Hall。不会用正则删除任务中与基础介绍相同的合法字句。原生历史由运行器维护，不能把archive重建的全文作为续轮正文再发一次。

`reconstruct_full_requirements`只使用传入的留档和完整基础合同，不自行读取存储。返回完整要求供审查；若合同不匹配、增量/消息被改动、投递模式/哈希/长度不符则抛`ValueError`。输入对象不被修改。摘要/错误不得回显Key或私有原始配置；本模块的错误只给字段与通用原因。

## 验证与尚未完成项

运行`python -B -X utf8 tests/test_execution_sessions.py`：106项标准库离线测试通过。独立整数阈值交叉核验11,994组通过。

尚未接通真实DSH指标采集、原生会话创建/恢复、锁/投递幂等/ACK、MCP增量派发/存档、页面或生产加载；也未验证原生桌面同窗和费用/缓存改善。用户已确认的[第二片289](../spec/DSH_CONTEXT_METRICS_SLICE_2.md)负责原生projection采集接口及规范化适配，已派发、尚无验收结论，当前内核和运行中角色不改。其余接线仍须另片确认；实际使用入口落地时，同片更新[用户手册](USER_MANUAL.md)并完成人工验收。
