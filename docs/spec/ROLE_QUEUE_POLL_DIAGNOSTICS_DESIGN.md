# 接单轮询诊断补数：实施合同

确认日期：2026-10-19（Asia/Shanghai）。用户在了解用途后明确“好的，那开发吧”。279已独立实查、Codex直接修正并集成收取，290 Python/24 Node通过；生产尚未加载，批量停服被自动审批拒绝，待明确加载许可。不代表完整日志整项完成，详[279复核](ROLE_QUEUE_POLL_DIAGNOSTICS_REVIEW_279.md)。

## 范围与证据含义

- 在通用 CLI bridge 的 `run_task_queue_worker` 补接单查询的周期记录、连续失败计数及首次再次成功的恢复事件，接入现有 human-only JSONL 诊断下载。
- 一次轮询指实际执行过期任务回收（若客户端支持）、查询 queued 任务及原有结果筛选/排序。成功只证明该次发现过程完成；在进入锁等待、模型预检或执行任务之前结束计时。无任务也算查询成功。
- 查询失败与锁等待、模型预检、任务执行、状态回报失败分别记录。后四者不得计入连续查询失败；现有异常/因果链与二次失败记录保持。
- 不增加任何网络查询、模型调用、canary 或测试任务。沿原轮询频率、重试、领取/租约/状态回报和取消边界；不自动恢复服务、重派任务或清空角色 `last_error`。
- 本片只补本地记录和下载证据。服务端接收心跳时间、宿主独立心跳、当前领取能力验证、跨宿主来源及全根清理均后续；不增加健康总灯或修改已验收页面。

## 事件及持久结构

- 周期边界事件使用 `queue_poll_snapshot`；首次失败后的真实查询成功使用 `queue_poll_recovered`。原 `queue_started/queue_stopped/queue_worker_exception` 及任务阶段事件保留。
- 在实际轮询开始/结束边界采样，记录当前阶段和最近成功/失败；首次轮询必须可观察。成功空闲路径每30秒最多一组开始/结束快照，使用单调时钟限频，不逐轮写两条，也不启动独立定时器伪造轮询推进。失败、恢复、停止证据不受成功快照限频影响。
- 每次真正开始查询时递增进程内 `poll_seq`，同一轮开始/结束相同；新 worker 从1开始，关联现有 project/member/instance/launch/run，不跨实例续算。未开始的轮询不得计数。
- 连续失败仅在查询发现阶段抛出普通异常时加1，并保留首次失败时间和原始异常引用；每次失败仍有完整脱敏异常证据。下一次查询成功立即记录一次恢复，携带恢复前失败次数及首/末失败时间；之后连续失败归0，无新失败不重复恢复。
- `asyncio.CancelledError` 单独保留取消/停止事实，不算查询失败或恢复。长时间执行模型/持锁不生成新查询成功；旧记录缺字段保持未知。
- 采用现有 `talk-runtime-diagnostics-1` 的 `extra.queue_poll`，不更改持久根 schema、已有 transition 或旧事件含义。该对象固定且仅含下列12键（原正文13为计数笔误，表格未变；冻结合同和原交付不改）：

| 键 | 类型及意义 |
| --- | --- |
| `poll_seq` | 严格正整数，同一 worker 的真实轮询序号 |
| `state` | `started/succeeded/failed/canceled` 之一 |
| `started_at` | 本轮实际开始时间，带时区 |
| `finished_at` | 本轮实际结束时间，started 时为 null |
| `duration_ms` | 本轮单调耗时，有限非负数；未完成为 null |
| `last_success_at` | 最近实际查询成功时间，未有则 null |
| `last_failure_at` | 最近实际查询失败时间，未有则 null |
| `failure_streak_started_at` | 活动失败段的首次失败时间；恢复事件保留刚结束的失败段，其后正常快照为 null |
| `consecutive_failures` | 严格非负整数；成功/恢复后为0 |
| `recovered_failures` | 严格非负整数；仅恢复事件填写刚恢复的次数，其它为0 |
| `error_log_id` | 当前/最近失败段原始异常的合法诊断引用，未知为 null；不能含异常自由文本 |
| `interval_seconds` | 本片内部成功采样间隔30，严格数字且拒绝 bool |

时间用真实带时区时间；耗时和限频用单调时钟，不从墙钟倒推。诊断写入失败不得打断查询/取消或把失败写入包装为成功落盘；沿已有日志降级机制如实保留限制。

## 导出与兼容边界

- 在统一导出每条 event 增加可空 `queue_poll`，仅从 `extra.queue_poll` 严格投影上述固定类型和键集合；缺失为 null，不透传任意 extra。`phase=queue`。
- 非法字段、未知键、bool 冒充数字、NaN/Infinity、无时区时间或状态/起止不一致不得原样导出；按既有投影失败机制明确不完整，不把坏记录静默算完整。
- queue_poll仅允许两个既定事件及queue阶段、interval_seconds固定30；成功last_success_at/失败last_failure_at必须等于同轮finished_at的同一瞬间，不要求墙钟先后顺序，以保留回拨事实。
- 保持 `talk-diagnostics-export-1`、meta、原字段、排序、半开时区范围/31天、10000条/16MiB、单次扫描和现有文件/字节/时间预算、明确 partial、human-only、作用域及脱敏边界。旧两GET、DTO、配置和页面不改。

## 实施与验收

- DeepSeek 首次实现和必要自测，交付后暂停；Codex 独立实查，问题由 Codex 直接修正并自检。项目页面仍为旧交叉复核要求，本次按用户/AGENTS 2026-10-18约定，生产要求不修改。
- 冻结产品基线 `0e4c61d865fcd9e97dc3ef1c5fa86d0f81146203`；执行者仅在 `.tmp/queue-poll-diagnostics-v1/deepseek/` 写候选/运行副本/证据，不写正式源码或文档、不操作 Git/生产服务。
- 候选可写产品：`bridges/cli_bridge.py`、新增 `bridges/queue_poll_diagnostics.py`、`server/runtime_diagnostics_export.py`。可新增测试：`tests/test_queue_poll_diagnostics.py`、`tests/test_queue_poll_diagnostics_worker.py`、`tests/test_queue_poll_diagnostics_export.py`。不改既有测试断言，跨界先暂停说明。
- 覆盖真实 worker 调用链：空闲周期限频、真实序号/开始/完成、连续失败后恢复且不重复、回收/列表/筛选失败、任务/预检失败不污染查询计数、锁/模型长等待无假推进、取消、无 diagnostics、写入/二次上报失败、不同实例隔离、墙钟回拨与单调耗时。
- 用假 Key/CLI、隔离 SQLite/日志根及真实 ASGI 或随机回环 HTTP 验证新字段由实际持久记录进入下载，异常引用/脱敏、未知及恶意 extra、旧记录兼容、401/403/scope/partial/预算保护。不得读取生产DB/日志/凭据或调用真实模型。
- 适当回归既有 CLI bridge、managed stop、runtime diagnostics/timeline、导出及导出页面读取合同；保留原始成功/失败、命令及计数。测试可通过假时钟推进，不做30秒/6小时实等。
- 交付完整 `talk-delivery-1` 裸 JSON，真实任务号；同时交 candidate、仅白名单路径的 integration.patch、SHA 清单、运行日志、集成说明和进度草稿。格式校验不代表验收；本片生产加载及实机验证在独立复核之后另行核条件。
