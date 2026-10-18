# 角色运行日志查看、接单健康反馈与权限边界设计

> 任务273：Kimi K3首次方案；2026-10-19经Codex独立复核后直接修正。原方案和失败样例保留。
> 性质：仅设计与纯数据样例，未实施页面、API、MCP、宿主桥接或数据库变更。
> 来源：原任务只读冻结快照`.tmp/runtime-logging-parallel-1/baseline`，基线`eec90941803a25c87dbec5a81c22633ffe4a5866`、产品1179bd0；原17个来源已独立核SHA与行号。Codex另结合已发布272/b40d59c补充宿主边界，未追改K3原交付。
> 结论边界：已有本地持久诊断记录与维护者查询，不等于已有网络查询、角色详情入口或“worker healthy”结论；完整异常日志整项仍未完成。

## 0. 设计结论先行

1. **入口与默认展示**：角色详情新增“运行诊断”区。只有用户显式打开后才查询；默认查询最近 24 小时、异常级别、最多 20 条，只显示有界摘要和稳定 `log_ref`，不在列表、任务结果或 MCP 返回完整 traceback。
2. **详情**：人类账号再按单条“查看详情”显式读取该 `log_ref` 的全部已记录堆栈帧和因果链。网络详情采用独立端点和白名单投影，不回传原始 JSONL、源码行、`extra`、绝对路径、Key、完整 argv、环境、配置或 stdout/stderr。
3. **最小权限**：首版两个新日志端点均为 **human-only**；Agent 均为 403，不因为本方案获得本人或他人日志读取权。现有 Agent 只读服务状态不变。若以后要开放 Agent 本人摘要，必须另片明确授权并实施“同项目 + 本人 + 精确记录归属”校验，不在首版夹带。
4. **作用域**：URL 中的 `project_id/member_id` 是权威范围；`instance_id/launch_id/task_id/log_ref` 只是在该范围内继续收窄。任何记录都必须与项目、角色精确匹配，不能靠当前实例、当前宿主或文件名反推归属，不能跨项目借记录。
5. **健康反馈**：分开呈现宿主归属、实例心跳、接单循环、历史领取证据，不合成一个绿色“健康”。空闲不证明可接单，进程活不证明 worker 健康，超时不证明死亡。当前没有接单循环周期心跳和宿主独立存活心跳时，对应项必须显示“未知/待核实”。
6. **查询实现**：现有 `query_records()` 可作为本地扫描基础，但不能直接序列化给 API：其原始结果含绝对 `root`，详情帧可能含绝对文件名；它也没有稳定分页、完整/不完整扫描区分下的网络语义和宿主路由。
7. **旧 ref 与过期**：完整扫描仍找不到时，只能说“未找到或已不可查”。现有 retention tombstone 不含逐 `log_ref` 删除索引，不能把未找到冒称“已过保留期”；`410 log_retention_expired` 仅作为未来有权威证据后的扩展。
8. **宿主边界**：当前只有本地维护者 CLI，没有日志查询 API、宿主查询桥接或日志来源目录。服务端不得对任何角色都回退扫描自己的默认根目录；无法解析日志来源时返回“暂不可用”，而不是空结果。
9. **冻结项**：`talk-runtime-diagnostics-1` 记录结构、现有本地 CLI、服务 ready/owner/启停守卫、现有服务及人工恢复API均不改。本文只给后续扩展建议；全根容量治理和不可逆清理策略另片处理。

## 1. 冻结快照中的事实与来源

### 1.1 已有能力

| 事实 | 设计含义 | 来源定位 |
| --- | --- | --- |
| bridge 已写入 `talk-runtime-diagnostics-1` JSONL；记录含项目、角色、实例、launch、任务、阶段、异常、预算和完整性字段 | 可复用持久记录，不需要为页面重造写入器 | `bridges/runtime_diagnostics.py` 532–741、707–859 |
| 每 run 独立目录，segment 追加、轮换；当前 run 有容量/保留处理，旧 run 默认保留 | 旧实例追溯应按记录身份查询，不应拼接文件路径；全根治理解耦 | `docs/guides/RUNTIME_EXCEPTION_LOGS.md` 29–71 |
| 公开错误只带 `log_ref`；完整异常不进聊天、实例状态或任务公开字段 | 页面默认也只放摘要和引用；不新增 MCP 堆栈入口 | 同上 73–87；`bridges/cli_bridge.py` 343–344、2730–2758 |
| 本地查询默认摘要，`--detail` 才显示净化后的帧与因果链 | “默认摘要、显式详情”与现有维护者语义一致 | `scripts/runtime_diagnostics.py` 26–62、93–137 |
| 查询只接受受控根与过滤条件，`--ref` 不当路径解析；拒绝符号链接并设扫描预算 | 可复用路径防御思想，但 API 还需输出投影和竞争窗口加固 | `bridges/runtime_diagnostics.py` 1264–1439 |
| 本地摘要包含 `source_file`；原始查询结果还含绝对 `root`；详情帧含 `file` | **不能直接把现有返回值交给 FastAPI response** | 同上 1432–1439、1458–1501、1553–1590 |
| 现有扫描默认 20 条、最多 200；5000 文件、128 MiB、10 秒预算；达到限制会标记 | API 可复用硬上限，但必须区分“还有下一页”“扫描不完整”“没有记录” | `scripts/runtime_diagnostics.py` 50–55；`bridges/runtime_diagnostics.py` 1316–1338、1349–1438 |
| 脱敏是启发式，未知 opaque 秘密仍可能残留；帧源码行也可能含本地绝对路径 | 网络输出须二次白名单和路径收敛，human-only 不等于可以原样回传 | `docs/guides/RUNTIME_EXCEPTION_LOGS.md` 114–125 |

### 1.2 当前页面与公开 API 事实

| 项目 | 当前行为 | 本方案如何复用 |
| --- | --- | --- |
| 角色详情 | `renderWorkspaceRoleDetails()` 每次重绘名称/任务容器；服务区只有启停和必要提示，详情不重复服务状态标签 | 新增独立静态“运行诊断”区，避免筛选、详情和焦点被 `replaceChildren()` 销毁；不改现有角色列表精简文案 | `web/workspace.js` 976–987、1375–1432；`web/index.html` 295–325 |
| 服务轮询 | 角色页活跃时按上下文轮询，离页/切项目/切账号作废旧响应 | 日志请求沿用项目 + 账号 + 角色 + 查询代次守卫，但不加入高频 2 秒日志扫描 | `web/workspace.js` 793–867、1330–1373 |
| 服务状态映射 | `running + ready` 才是启动成功；心跳失联是“运行状态待核实”；owner 未释放禁止重启 | 原样复用，不由日志或健康面板改变 ready/owner/启停 | `web/workspace.js` 879–940；`server/role_services.py` 1190–1344 |
| 项目角色/名册读取 | `GET /projects/{id}/roles`、`GET /projects/{id}/agents` 对任意已认证成员开放，只核项目存在 | 可供现有页面取上下文，**不能直接当成日志授权规则** | `server/routes/projects.py` 477–490、1241–1258 |
| 实例读取 | `GET /api/instances` 对任意已认证成员开放；项目只是可选过滤；实例 PUT 仅 Agent 本人 | 心跳事实可用，开放读取权限不可外推到日志；记录归属必须另核 | `server/routes/instances.py` 123–169、251–270 |
| 名册内嵌实例 | `GET /agents` 的批量实例查询只按 `member_id IN (...)`，未按项目过滤 | 前端健康行必须再精确匹配当前项目、launch、实例；不得拿同成员其它项目实例充数 | `server/routes/projects.py` 317–347、372–401 |
| 服务读取 | `GET /projects/{id}/role-services` 对任意已认证成员开放 | 可复用现有服务投影；日志新端点不沿用“任意已认证” | `server/routes/role_services.py` 125–139 |
| 服务写操作 | start/stop/start-all 是 human-only；服务端只写意图，不直接 spawn/kill | 日志查看不得触发启停、恢复、模型调用或新任务 | 同上 45–87、106–122 |
| launch claim/report | 目标 Agent 本人或 human 可参与，另有 host、世代和 token 守卫 | 不将 owner/claim token 给浏览器，也不把 claim/report 权限当作日志读取权 | `server/role_services.py` 833–897；`server/routes/role_services.py` 142–198 |
| 任务可见性 | human 可见全部；Agent 仅自己创建或自己的目标；单任务不可见时通常 404 | 不能用“知道 task_id”扩大日志范围，也不能通过日志返回任务正文 | `server/routes/tasks.py` 87–90、1770–1812 |

### 1.3 当前日志事件能提供什么

- `bridge_started/bridge_stopped`：只证明该事件在当时被写入，不等于此刻主进程仍活或已死（`bridges/cli_bridge.py` 4524–4534、4763–4771）。
- `managed_heartbeat_failure`：证明某次心跳失败；单次失败不等于进程退出（同上 4645–4674）。
- `queue_started/queue_stopped/queue_worker_exception`：证明队列 worker 的历史事件。异常在循环中被捕获后仍会继续下一轮，因此异常既不证明循环死亡，也不证明后续健康（同上 4180–4211、4351–4408）。
- `task_claimed/task_claim_conflict/task_claim_failed/task_completed`：证明历史领取或执行边界，不是未来接单能力探针（同上 3200–3248、3494–3508）。
- 现有服务投影用本次启动实例的 90 秒心跳做只读降级；它不会回写 owner，也不证明宿主 Popen 或接单循环（`server/role_services.py` 1190–1220；`docs/spec/ROLE_SERVICE_CONTRACT.md` 51–59）。

## 2. 作用域与不可推断规则

### 2.1 标识语义

| 标识 | 规则 |
| --- | --- |
| `project_id` | URL 权威范围。记录值必须完全相等；`null`、缺失或其它项目一律不纳入。不得因当前角色在某项目就回填旧记录的缺失项目。 |
| `member_id` | URL 权威角色。记录值必须完全相等；同 display name、同 runtime、同宿主均不能替代。 |
| `instance_id` | 可选精确过滤。当前实例只用于 UI 标记“当前”；历史实例仍可查，不把 offline 当日志失效。 |
| `launch_id` | 可选精确过滤。受管启动日志通常有值，旧手动运行可为 `null`；不能用当前 launch 替换记录原值。 |
| `task_id` | 可选精确过滤，仅缩小结果，不读取或返回任务正文，不改变任务可见性。 |
| `log_ref` | 不透明稳定引用，沿用 `^rtd-[A-Za-z0-9.-]{4,160}$` 校验；绝不拆成目录或文件名。 |
| `run_id` | 记录内部仍可用于本地维护者诊断；网络首版不输出，因为现格式含 PID，页面追溯不需要它。 |

### 2.2 查询组合

- 多条件一律 AND，不支持客户端提交 SQL、glob、路径或任意表达式。
- `log_ref` 精确查询仍先固定 URL 项目/角色，再在结果上二次核归属；不是“知道引用即可全局查”。
- `launch_id` 即使在数据库中属于其它项目，也只能得到无结果/范围错误，不能返回其记录或借此确认内容。
- 已归档角色、已禁用成员的历史日志：human 仍可依据保留的 `ProjectRole` 或 `ProjectAgent` 历史对查询；不能使用会拒绝归档/禁用的启动资格函数作日志授权。目标项目与角色对完全不存在时才 404。
- `project_id=null` 的旧记录不进入项目页面；维护者仍可使用现有本地 CLI 按角色/实例查，不借网络 API 放宽。
- 同一角色跨项目时，每个项目端点只看本项目记录。human 按现有权限可主动访问另一个项目自己的端点，这不等于允许在 A 项目响应里混入 B 项目记录。

## 3. 角色详情交互与中文文案

### 3.1 入口和默认行为

建议在 `index.html` 的 `role-description-panel` 与 `role-details-tasks-panel` 之间新增静态：

```text
运行诊断
[服务证据摘要] [最近异常摘要（尚未查询）]
[查看运行日志] [按日志引用查找]
```

- 选中角色后只展示已有服务证据，不自动扫描日志；点击“查看运行日志”才发默认查询，避免角色轮询放大磁盘 IO。
- 默认查询：最近 24 小时、`severity=error,warning`、按 `(recorded_at, log_id)` 倒序、20 条、仅摘要。
- 打开后面板保留“异常 / 全部事件”切换；“全部事件”才可看到 `queue_started` 等 info 记录。
- Agent 可继续看既有服务证据，但日志按钮禁用并显示无权限说明；不发起新日志请求。
- 不改角色列表、角色开关、绑定重置、参与任务或任何 ready/owner 文案和动作。

### 3.2 摘要列表

每条记录最多显示：

```text
10-18 20:46:12  ERROR · task_claim_failed · task_claim
TaskClaimError：领取请求失败，请稍后重试…
实例 ins_…92 · 启动 …a91c · 任务 #273
日志引用：rtd-031f55a209-000001  [复制引用] [查看详情]
```

约束：

- `message_preview` 服务端压成单行并最多 200 字符；前端 `textContent`，不解析 HTML、Markdown、URL 或命令。
- 列表不返回/渲染 `frames`、`cause_chain`、完整 `message`、`extra`、源码行或原始 JSON。
- “任务 #N”只在已有任务上下文可确定时作为普通导航；否则只显示编号，不额外调用无权限任务接口。
- 完整性标记：“已脱敏”“原始记录有截断”“写入完整”分别展示；`redacted=true` 不宣传为绝对无秘密。
- 当前实例由 `service.observed_instance_id` 精确匹配后标“当前实例”；其它标“历史实例”。没有匹配就不猜。

### 3.3 显式详情

- 每条摘要有独立“查看详情”；仅 human 可用。点击后按 `log_ref` 请求独立 detail 端点，不将详情预埋在列表响应。
- 详情用抽屉或 `<dialog>`，标题含时间、事件和引用；正文展示全部**已记录且经网络白名单投影**的堆栈帧、显式/隐式因果链、帧省略数、链截断/循环和完整性标志。
- 网络详情只给 `file_name + line + function`，不给原始 `file` 和源码行。需要源码行的维护者仍用本地 `scripts/runtime_diagnostics.py --detail`。
- 文本均用 `textContent`/`pre.textContent`；`related_log_id` 只在同项目同角色内再次精确查询，不能跳成全局搜索。
- 关闭详情、切换角色/项目/账号、离页时清除详情内容并作废旧请求；迟到响应不得写入新上下文。

### 3.4 筛选与分页

筛选项：

- 时间：最近 1 小时、24 小时、7 天、自定义；自定义必须带时区。列表最长跨度 31 天。
- 实例：全部可查实例、当前实例、从历史响应中出现的实例精确选择。
- 启动动作：精确 `launch_id` 输入/粘贴；不从输入值推路径。
- 级别、事件、阶段、任务编号；均为精确匹配，事件/阶段不做模糊搜索。
- 日志引用：独立精确查询，不与时间、分页或其它过滤静默叠加；冲突参数直接报错。

操作文案：

- 主按钮：“查询”；次按钮：“重置为最近 24 小时异常”。
- 有稳定下一页：“加载更早”；加载中：“正在读取日志…”，重复点击禁用。
- 扫描不完整时不发下一页游标，按钮替换为提示：“请缩小范围后重新查询”。
- 分页、筛选、详情请求都携带项目/账号/角色/过滤哈希/查询代次；任何上下文变化都丢弃迟到结果。

### 3.5 空态、异常态和降级文案

| 场景 | 中文文案与行为 |
| --- | --- |
| 完整扫描无异常 | “当前范围内未发现异常日志。” |
| 完整扫描无任何事件 | “当前范围内没有可查日志。” |
| 扫描达到预算 | “已显示本次扫描命中的记录；扫描达到上限，结果可能不完整。请缩小时间范围，或按实例、启动动作、日志引用查询。” 不给 `next_cursor`。 |
| 有 malformed/unreadable 记录 | “部分日志记录无法读取或解析，结果可能不完整；未将缺失记录当作无异常。” |
| 来源未配置/不可达 | “暂时无法读取该角色的日志来源；这不表示角色已停止或没有异常。” 不回退到服务端默认根。 |
| Agent 摘要/详情 | “当前 Agent 账号没有运行日志查看权限。” 不显示伪造空列表。 |
| 无权限详情（未来细分权限时） | “详细堆栈仅向有日志查看权限的人类账号开放。” |
| 完整扫描后 ref 未找到 | “未找到该日志引用；它可能已超出保留期、从未写入成功，或不属于当前项目与角色。” 不直接说“已过期”。 |
| 未来有权威过期证据 | “该日志已过保留期，详细内容不可再读取；保留期处置记录仍在。” 只有索引能证明时才用。 |
| 写日志降级、无可信 ref | “本条异常没有可信日志引用，详细日志可能未写入；不能据此推断没有异常。” |
| 旧实例 | “以下为历史实例日志；实例离线不代表日志已删除，也不代表当前服务状态。” |
| 日志记录缺项目归属 | 不混入项目结果；说明“未记录项目归属的早期日志不能在项目页面确认归属。” |
| 分页依据失效 | “日志分页依据已变化，请从第一页重新查询。” 不拼接两个过滤上下文。 |
| 服务查询失败 | “日志读取失败，请稍后重试；既有服务状态与启停操作不受影响。” 不自动重试放大扫描。 |

保留过期目前只能作为“可能性”展示。现有 tombstone 只记录 segment 文件、大小、时间和原因，不记录其中每个 `log_ref`，因此首版不能可靠产生“某引用已过期”的结论。

## 4. 健康反馈：证据、未知与后续补数

### 4.1 五类证据分离展示

| 页面行 | 当前可用证据 | 可展示结论 | 明确不能展示 |
| --- | --- | --- | --- |
| 受管宿主与原进程归属 | `ownership_held`、`current_launch`、启动/停止回执、`updated_at` | “归属未释放”“上次启动已就绪（历史回执）”“已收到停止回执（历史事实）” | `ownership_held=true` 不等于进程仍活；没有宿主独立心跳时不显示“宿主正常”。 |
| bridge 实例心跳 | 同项目、同 launch、同实例的 `last_seen_at/status`，以及现有 90 秒服务投影 | “近期有实例心跳”或“运行状态待核实”及证据时间 | 超时不证明死亡；旧实例心跳不证明本次启动；进程活不证明 worker 健康。 |
| 接单循环 | `queue_started/queue_stopped/queue_worker_exception` 的事件与时间 | “最近一次接单循环事件：…” | 没有周期 queue heartbeat 时一律“当前接单循环：未知”；`queue_started` 不证明当前仍在轮询，单次异常不证明已退出。 |
| 任务领取能力 | 历史 `task_claimed`、任务当前 `claimed_at/status/instance_id` | “最近领取记录：#N / 时间 / 实例”；无记录时“当前范围无领取记录” | 空闲不证明可接单，busy 不证明不可接下一单（还受锁与协议约束）；无记录不证明不能接单；不显示“接单能力正常”。 |
| 领取前模型预检 | 当前只有任务创建/领取时间，缺预检开始/结束及排队锁等待记录 | 无精确阶段证据时显示“领取前预检：未知”；未来只有同项目/角色/任务/实例的真实阶段事件才可显示“预检中” | queued不证明没有工作；创建到领取的总时间不等于模型预检耗时，不伪造running/已领取或改变租约。 |

附加规则：

- 不用一个总绿灯覆盖五类证据。页面可以有“诊断证据不足”提示，但不新增 `worker_healthy=true`。
- `last_error` 中有 ref 只说明对应错误曾有持久引用；没有 ref 可能是写日志降级，不表示无错误。
- `idle` 仅是实例自报状态；`pid` 也仅是诊断字段，不作为 OS 活进程或所有者证明。
- 服务端收到心跳的时间与事件自带 `recorded_at` 分列；时钟偏差时显示“按服务端接收时间”而非伪造精确在线秒数。
- 日志显示的历史事实不改变既有服务状态，不能触发自动恢复、重启、重派或租约变更。

### 4.2 当前缺数据，必须另片新增的项

1. **宿主独立心跳**：至少含宿主 manager 实例、原 launch/实例关联、单调序号、服务端接收时间、原 Popen 的只读观测时间。它只能增强宿主/进程证据，不能替代 worker 心跳。
2. **接单循环周期心跳**：每轮或有界间隔记录单调 `poll_seq`、最近轮询开始/完成/失败时间、连续失败数和服务端接收时间；不带任务正文。没有该数据前，本设计保留“未知”。
3. **领取能力的当前验证**：历史领取不是能力探针。如产品需要主动验证，须另片设计只读 preflight 或人类明确授权的受控 canary；本片绝不创建测试任务、调用模型或占用真实队列。
4. **日志来源目录**：需要 `(project, member, instance/launch) -> 受控来源` 的可靠映射与来源在线状态，才能跨宿主追踪旧实例。当前记录没有足以路由所有旧 ref 的中心索引。
5. **逐引用保留索引**：只有需要区分“已过期”和“从未存在/写失败/不在范围”时才另片新增；不在本片修改保留策略或倒推历史 tombstone。

这些补数不得借由 `ready` 或 `idle` 伪造，也不要求首版日志查看先改变现有记录 schema。

本轮272真实领取延迟190.352秒已只读核实，但没有预检起止时间，不能把整段时间归因于模型。后续需新增preflight_started/preflight_finished（或等价阶段记录）及实际关联/单调耗时，另区分等锁、轮询和模型调用；本方案只定义可见性要求，不实施bridge事件或任务状态变更。

## 5. 权限逐项核查与新增权限建议

### 5.1 现有权限可复用与不可复用

| 身份/能力 | 当前事实 | 对日志设计的决定 |
| --- | --- | --- |
| 未认证 | `/api/*` 通常要求 `X-API-Key`，无效 401，禁用成员 403 | 新端点沿用 `get_current_member`；401/403 时不扫描。 |
| human 项目/角色/服务读 | 当前已认证 human 可读项目角色、实例和服务投影，没有单独项目成员表限制 | 首版复用“human + 项目存在 + 历史角色对存在”作日志范围；不额外发明 maintainer 角色，也不放宽到 agent。 |
| agent 项目/角色/服务读 | 当前也可读这些公开投影，且服务写操作只读 | **不复用到日志**。首版新日志端点 403。 |
| agent 实例 PUT | 只能更新自己实例；项目/launch 关联有守卫 | 只允许继续上报，不授予读日志或查询他人实例日志的能力。 |
| human 服务写 | start/stop/start-all 可写意图 | 与日志查看完全分离；日志端点永远 GET，无副作用。 |
| launch claim/report | 目标 agent 或 human，需 host/token/世代等 | 不能复用为浏览器日志凭据；token 不进入新 API 请求、响应或页面存储。 |
| 任务/Hall 可见性 | human 全量，agent 仅自己相关任务/Hall | 不能因 ref 带 task_id 就返回任务内容或扩大日志范围；日志接口不查询 Hall 历史。 |
| business_role / decision_tier | 不作为现行权限判定 | 日志权限不看“lead/dev/reviewer”标签或旧分级。 |

### 5.2 首版新增端点权限

| 端点 | human | agent | 目标校验 |
| --- | --- | --- | --- |
| `GET /api/projects/{project_id}/roles/{member_id}/runtime-logs` | 允许 | 403 `log_read_forbidden` | 项目存在；`ProjectRole` 或 `ProjectAgent` 中存在该历史角色对；记录再逐条核 project/member。 |
| `GET /api/projects/{project_id}/roles/{member_id}/runtime-logs/{log_ref}/detail` | 允许，且必须显式点击 | 403 `log_read_forbidden` | 同上；完整扫描、精确 ref、逐字段白名单后才返回。 |

- 先鉴权，再解析目标，再扫描；Agent 不能用计时或错误差异探测 ref 是否存在。
- 对越权 ref 与不存在 ref 使用同一公开 `log_not_found`，不返回另一项目/角色的元数据。
- 归档/禁用不妨碍 human 读保留历史；但不要求目标仍 bound、managed_cli、ready 或可启动。
- 若未来需要 Agent 本人摘要，建议另片评审：当前项目名册有效、`current.id == member_id`、记录 project/member 精确一致、仅摘要、不含源码/详情；它不是本次授权。
- 不新增 MCP 查询工具。现有任务结果、实例状态和 `talk_get_delivery` 均不因此返回堆栈。

## 6. 最小只读查询合同（建议，尚不存在）

### 6.1 两个端点与参数

#### A. 摘要列表

`GET /api/projects/{project_id}/roles/{member_id}/runtime-logs`

| 参数 | 默认/限制 | 说明 |
| --- | --- | --- |
| `ref` | 可选；沿用现有 LOG_ID_RE | 精确引用查询；与 `cursor/since/until/instance_id/launch_id/task_id/event/stage/severity` 冲突时 422，不静默忽略。 |
| `since` / `until` | 默认分别为服务端当前时间减 24 小时、当前时间；必须为带时区 ISO 8601 | `since < until`，跨度最多 31 天；规范化为 UTC。精确`ref`分支不应用默认时间窗或默认severity；仅按URL scope和引用匹配，info事件也可定位。 |
| `instance_id` | ≤128 字符的既有安全标识 | 精确匹配，不接受路径/glob。 |
| `launch_id` | ≤128 字符的既有安全标识 | 精确匹配；旧记录为 null 时不以当前 launch 代替。 |
| `task_id` | 十进制正整数，受服务端安全整数上限约束 | 精确匹配；不返回任务正文。 |
| `event` / `stage` | 各 ≤64 字符，仅既有安全字符 | 精确匹配；不接受正则、子串或 SQL。 |
| `severity` | 默认 `error,warning`；允许 `error/warning/info` 的逗号列表 | 去重，空值和未知级别 422。 |
| `limit` | 默认 20，1..50 | 仅摘要条数；本地 CLI 的 1..200 不变。 |
| `cursor` | 第一页为空；之后必须原样回传 | 与`ref`互斥；绑定规范化query、scope、来源版本/清单指纹、snapshot_until、过期时间和上一排序键，并校验服务端签名。 |

禁止参数：`detail/path/file/root/log_dir/host/follow_symlinks/max_files/max_bytes/max_seconds/sql/where/glob` 以及任何未知键。缺省为 422，不能静默变成任意磁盘查询。

#### B. 单条详情

`GET /api/projects/{project_id}/roles/{member_id}/runtime-logs/{log_ref}/detail`

- 不接受任何查询参数，包括`detail=true`；未知或重复参数返回422。摘要列表也拒绝重复的单值参数，severity只在一个逗号列表内去重。
- info等非异常事件的`exception`可以为null，详情显示“该事件没有异常堆栈”；不制造异常或返回投影失败。
- `log_ref` 即使经 URL 编码也必须通过同一引用校验；`/`、`\\`、NUL、盘符、UNC、`..` 路径形态均不能进入文件系统逻辑。
- 只有完整扫描且精确命中唯一一条、scope 匹配时返回 200；扫描不完整不能退化成 404。

### 6.2 列表响应白名单

建议新 API envelope 使用 `talk-runtime-log-page-1`，它不改写持久记录的 `talk-runtime-diagnostics-1`：

```text
schema
scope { project_id, member_id }
query { since, until, instance_id, launch_id, task_id, event, stage, severity[] | null, ref }
records[] {
  log_id, recorded_at, event, severity, stage,
  project_id, member_id, instance_id, launch_id, task_id, related_log_id,
  exception { type, message_preview, frames_total, cause_depth } | null,
  returncode, timeout, cancel_category,
  budgets {
    cli_timeout_seconds, http_timeout_seconds, task_lease_seconds,
    task_heartbeat_interval_seconds, managed_heartbeat_interval_seconds,
    task_poll_interval_seconds, mcp_wait_seconds
  },
  integrity { redacted, truncated, write_complete }
}
page { limit, sort, snapshot_until, has_more, next_cursor }
scan {
  complete, truncated, scanned_files, scanned_bytes,
  malformed_lines, unavailable_sources
}
warnings[] // 仅稳定机器码，不携带内部异常或路径
```

显式排除：`root/_source_file/source_file/segment_file/run_id/pid/runtime/host/extra/message/frames/cause_chain/stdout/stderr/argv/env/config/token/key/owner_token/claim_token`。缺字段以 `null` 表示“未记录”，不从模板补值。

### 6.3 详情响应白名单

`talk-runtime-log-detail-1` 仅含 `schema/scope/record/scan`。`record` 在摘要字段基础上将 `exception` 扩为：

```text
exception {
  type, message, str_empty, message_error,
  frames_total, frames_omitted,
  frames[] { file_name, line, function },
  cause_chain[] {
    relation, type, message, frames_total, frames_omitted,
    frames[] { file_name, line, function }
  },
  chain_depth, chain_truncated, chain_cycle,
  has_explicit_cause, context_present, context_suppressed
}
integrity {
  redacted, redaction_kinds, truncated, truncated_fields,
  write_complete, capacity_soft_exceeded, event_size_soft_exceeded
}
```

- 不返回 `file`，只返回按 Windows/POSIX 两种分隔规则取出的 `file_name`；不返回源码 `source`。
- 所有自由文本（含message、type、file_name、function及因果链各同类字段）在出口执行二次秘密/路径净化；Windows盘符、UNC及任意POSIX根（/srv、/mnt、/data等）均纳入负例。无法安全投影则整条拒绝，不回退原始文本。样例净化器不是生产秘密扫描器，不宣称证明未知opaque秘密均已消除。
- 不返回 `extra`、顶层自由 `message`、manifest、完整配置、argv、环境、子进程输出或原始记录。
- 保留原记录已有的省略/截断标志；网络层不得再次静默截断。若白名单序列化异常或超出生成预算，返回稳定错误而非半成品。

### 6.4 错误码

| HTTP | 稳定码 | 使用条件 |
| --- | --- | --- |
| 401 | 现有认证错误 | 无 Key/无效 Key；不扫描。 |
| 403 | `log_read_forbidden` | Agent 调用任一新日志端点；禁用成员沿用现有 403。 |
| 404 | `project_not_found` / `role_not_found` | 项目或历史角色对不存在。 |
| 404 | `log_not_found` | **完整扫描**后无匹配，或越 scope 的 ref；不区分不存在与无权知道。 |
| 409 | `log_ref_conflict` | 同一 ref 命中多个不一致记录，拒绝任选一个。 |
| 409 | `stale_cursor` | 游标世代/有效期或已确认来源配置/清单失效；要求从第一页重查。scope/filter不匹配是422。 |
| 410 | `log_retention_expired` | 仅未来逐引用保留索引能明确证明时；首版通常不得返回。 |
| 422 | `invalid_log_ref` / `invalid_filter` / `invalid_cursor` / `conflicting_filters` | 引用、时间、枚举、limit、未知参数或组合不合法。 |
| 503 | `diagnostics_unavailable` | 来源未配置、不可读或宿主查询桥不可用；不得当作空结果。 |
| 503 | `diagnostics_scan_incomplete` | detail/ref 无法在有界扫描内作确定结论；不返回堆栈或 not-found。 |
| 503 | `diagnostics_projection_failed` | 无法安全完成白名单/脱敏投影；不返回原始记录和内部异常正文。 |

列表查询允许 `200 + records=[]/部分记录 + scan.complete=false`，因为响应明确是“不完整扫描结果”；detail 不允许用这种不确定状态冒充未找到。所有错误 `detail` 只含稳定码和固定短文本，不含根目录、异常字符串、SQL 或内部堆栈。

### 6.5 时间、条数与扫描预算

- 列表默认 24 小时、20 条；自定义最长 31 天；每页最多 50 条。
- 服务端每次扫描硬预算建议沿用现有查询上限：最多 5000 个候选文件、128 MiB、10 秒；客户端不能调大或调小这些内部值。后续若为 HTTP 降低预算，只改服务端实现常量，不改请求合同。
- `limit` 只限制返回条数，不是扫描完整性证明。达到 `limit` 不得直接写成 `scan.truncated=true`。
- `scan.complete=true` 要求：选定来源全部可达、候选扫描未触预算、没有无法解析/读取的候选记录。否则 `complete=false`，列表 `next_cursor=null`。
- detail/ref 需要在同一有界扫描内确认唯一记录；预算耗尽是“未知”，不是“不存在”，更不是“进程死亡”。
- 现有单条记录写盘上限约 1 MiB；网络层只投影白名单，不新增批量 detail 或导出端点。

### 6.6 分页稳定性（首版保守失效策略）

排序键固定为`(recorded_at DESC, log_id DESC)`。第一请求由服务端固定绝对since/until、severity、全部规范化过滤及snapshot_until，并在query中完整回显。后续页必须重放这份规范化query，不得重新按“当前时间减24小时”计算默认窗口；缺少首页明确回显的时间/过滤或不一致返回422 invalid_cursor。

游标为带服务端签名的不透明base64url载荷，含version/cursor_epoch/scope_hash/filter_hash/source_revision/inventory_hash/snapshot_until/last_recorded_at/last_log_id/expires_at。使用独立随机游标签名秘密，不复用API Key或owner/claim token；当前签名世代内的签名失效/篡改为422，每页重新鉴权和核作用域。公开非秘密cursor_epoch与本服务世代不符或游标已过期时409 stale_cursor，不扫描、不返回记录；世代标记不是授权凭据。载荷不含路径、配置、宿主地址或查询SQL，客户端不得修改排序锚点跳页。

provider需提供显式来源配置版本source_revision和受控候选清单inventory_hash。后者至少覆盖安全打开确认的文件身份、长度、读取内容摘要与修改/创建标识，内部路径只参与服务端摘要，不回传；每次有界扫描前后均重新核验同一清单。首版任何无法证明未变化的情况（含追加、创建、删除、轮换、替换、截短或来源配置变化）均返回409 stale_cursor，要求重新查询；不以“第二次剩余文件完整扫描”冒充原快照完整。首版因此不承诺在日志持续追加时继续旧分页；实现稳定文件水位/快照或有界结果缓存必须另行扩展和验证。

每页在固定扫描预算内取得该scope的完整候选、应用固定过滤/游标，稳定排序后取limit+1。只有扫描完整且来源/清单前后与签名游标匹配才给next_cursor；达到limit不是扫描不完整。无分页的首请求若扫描中变化或预算不足，允许200 + scan.complete=false + next_cursor=null；已有cursor无法继续一致读取时必须409，不静默拼接部分旧页。

来源暂不可达、无法安全打开时仍按503 diagnostics_unavailable处理，不伪称已证明来源改变；只有已确认来源配置/清单不一致或游标世代/有效期失效时才409。所有读取与指纹复核均计入同一文件/字节/时间预算，不能为签名/清单验证绕过上限。

以上是新provider/游标适配器必须实现的合同，现有query_records不具备这些能力。仅snapshot_until不能检测segment删除，不能直接沿用当前“到limit停止”的查询器来发布稳定分页。

### 6.7 旧 ref、路径与符号链接边界

- ref 只做整串比较，永不 `root / ref`、不 URL decode 成路径、不允许客户端指定根。
- 根只能来自服务端/宿主管理员的固定配置与已解析来源目录；不存在默认“扫服务端仓库根就能覆盖所有角色”的假设。
- 仅枚举受控根下的 `events-<数字>.jsonl`；根是符号链接、目录/文件是符号链接、解析后越出根，都跳过并标不完整。
- 当前 `is_symlink()+resolve()` 是基础防线，不能充分消除检查后被替换的竞态。网络实现需使用平台可用的 no-follow/openat/fstat 或等价防护，并处理 Windows reparse point；无法保证时宁可跳过并降级，不能跟随。
- 文件读取使用 UTF-8 有界替换策略；坏行计数并标不完整。任何 IO 错误都不把内部路径写进公开错误。
- `query_records()` 返回的 `root` 和 `record_summary_dict()` 的 `source_file` 只能在本地维护者层使用，网络层不得透传。

## 7. 出口脱敏与宿主桥接边界

### 7.1 网络出口必须是新白名单层

建议调用关系：

```text
浏览器
  -> FastAPI 新只读路由（认证、项目/角色校验、参数/游标校验）
  -> RuntimeDiagnosticsProvider（内部抽象，按已解析来源查询）
  -> 受控扫描器（固定根、预算、符号链接防护）
  -> 服务端再次核 project/member/ref scope
  -> 白名单 + 二次秘密/路径净化 + response model extra=forbid
  -> 浏览器 textContent
```

禁止：

- 直接 `return query_records(...)`；
- 直接 `return format_record_detail(...)`；
- 把 `TALK_RUNTIME_LOG_DIR` 或 `--log-dir` 暴露为 HTTP 参数；
- 依赖前端隐藏字段来保密；
- 因请求来自 human 就返回原始 JSONL。

所有自由文本都视为不可信存储输入。除既有 `sanitize_text` 外，还需专门覆盖 Windows 盘符、UNC、POSIX 绝对路径的路径净化；完整 argv/config 字段直接不取。脱敏仍是启发式，页面只能写“已执行脱敏”，不能写“保证无秘密”。

### 7.2 当前不存在的宿主能力

当前只有：

- bridge 在本地写日志；
- 维护者在同机执行 `scripts/runtime_diagnostics.py`；
- role service host 负责生命周期 claim/report。

272/b40d59c已实现宿主持久诊断代码，但尚未重启长期宿主。其manager级poll/worker记录member=unknown，不能借当前owner推归属并混入角色URL；首版角色日志覆盖bridge与精确launch记录，manager记录仍用本地维护者入口。宿主ready是本地观察，host_started/host_stopped是serve边界，不证明report成功、OS存活或worker健康。

当前没有：

- FastAPI 日志查询路由；
- `RuntimeDiagnosticsProvider` 的服务端实现；
- 宿主到服务端的通用日志查询/回传通道；
- 项目/角色/旧实例到日志宿主的可靠目录；
- 旧 ref 的跨宿主全局定位能力。

因此后续有两种诚实的实施拓扑：

1. **首版实施边界选同机显式来源**：管理员静态配置某角色的受控日志来源，服务端只查询该来源；所有未配置来源返回 `diagnostics_unavailable`。发布范围必须写清“仅同机已配置来源”，不能称全角色/跨宿主完成。
2. **后续宿主桥接片**：先实现受认证、受 scope/预算约束的宿主查询桥和来源目录，再开放多宿主查询。宿主根只取本地配置，服务端请求不得传路径；宿主返回后 FastAPI 仍须重新核 scope 和白名单。

不得让浏览器持有 agent Key、owner token 或 claim token；不得复用生命周期 report 通道夹带任意日志；不得在宿主不可达时扫描另一个项目或服务器的默认根冒充结果。

## 8. 实施顺序与文件冲突表

以下是未来实施建议，不是本次改动清单。

### 8.1 必须串行的主干

1. **实施基线核对**：本合同经273独立复核及Codex修正后发布；首版human-only、同机显式来源、详情不返回源码行、未找到不等于过期。实施前核对实际基线，扩为多宿主或改变权限须另片明确。
2. **只读投影与扫描适配**：新增服务端内部 provider/DTO/cursor/出口净化及纯临时根测试；不改写入器和现有 CLI 输出。
3. **API 路由**：在投影稳定后注册两个 GET 端点，完成 human/agent、scope、预算和错误码隔离 HTTP 测试。
4. **来源/宿主**：同机首片先完成显式来源配置和不可达降级；多宿主则先完成宿主查询桥和来源目录，未闭合前不得宣称多宿主可用。
5. **页面**：按冻结契约样例开发静态面板、摘要、详情和上下文守卫；与 API 串行合入公共入口。
6. **健康补数**：宿主心跳、queue heartbeat、主动领取能力验证分别是后续片；首版只按现有证据显示未知，不阻塞日志查看，也不冒称健康完成。
7. **文档与验收**：实现和隔离测试后，由 Codex 更新正式指南/模块/用户手册；真实页面、权限和宿主验收独立记录。

### 8.2 可并行条件

- 基于本合同，前端纯fixture交互与后端纯数据投影可在隔离工作区或各自.tmp候选目录并行准备；同一主目录仍只有一个产品代码写入者，公共入口由Codex串行集成。
- 只要涉及 `server/main.py`、`web/index.html`、`web/workspace.js` 或公共测试期望，就必须串行合入；不能两边同时改。
- 宿主查询桥与页面可基于同一冻结契约并行开发新文件，但 API 发布和跨宿主验收必须等宿主桥完成。
- queue heartbeat 属另一数据新增片，不与日志查询并行改 `bridges/cli_bridge.py`。

### 8.3 实际文件与冲突控制

| 文件/接口 | 建议动作 | 冲突与依赖 |
| --- | --- | --- |
| `server/runtime_diagnostics_query.py`（新） | provider 抽象、scope 校验、游标、白名单投影、扫描预算 DTO | 新文件可独立开发；不得导入私有配置或读取任意请求路径。 |
| `server/routes/runtime_diagnostics.py`（新） | 两个 GET 路由与稳定错误映射 | 依赖投影；human-only，不能复用任意已认证注释。 |
| `server/main.py` | 只注册新 router | 公共入口，必须串行；不改现有路由顺序语义。 |
| `server/models.py` | 首选不改；新 schema 放新模块。若项目坚持集中模型再另审 | 高冲突公共文件；任何 `extra=forbid` 新模型不能改变旧 schema。 |
| `bridges/runtime_diagnostics.py` | 复用扫描/净化；如需完整候选集和 no-follow 加固，在独立片中增强 | 272没有改该文件；公共API、持久SCHEMA和既有CLI行为冻结，后续增强扫描器必须作为独立受控改动串行集成。 |
| `scripts/runtime_diagnostics.py` | 首版不改 | 保留维护者本地入口；不能用 subprocess CLI 当作 API 宿主桥。 |
| `server/routes/role_services.py` / `server/role_services.py` | 首版不改，只读复用现有投影 | ready/owner/start/stop/recovery 高冲突；日志不得改六个 API 或状态机。 |
| `scripts/role_service_host.py` | 多宿主另片增加受控查询桥/来源上报 | 与 Popen/owner/stop 高冲突；不能与页面片混改，不能扩大进程权限。 |
| `web/role-diagnostics.js`（新） | 日志 UI 状态、查询、分页、详情、请求代次 | 可基于 fixture 并行；不允许把响应写 `innerHTML`。 |
| `web/role-diagnostics.css`（新） | 独立面板样式 | 避免直接争用 `workspace.css`。 |
| `web/index.html` | 加静态 panel 与新资源 | 公共前端入口，串行；缓存版本由实际实施片统一处理。 |
| `web/workspace.js` | 只在角色详情渲染钩子同步选中角色/可见性 | 高冲突；不大改服务轮询和角色列表。 |
| `web/app.js` | 首版计划不改 | 若确需导航清理，另列最小 diff；保留当前鉴权和详情同步。 |
| `tests/test_runtime_diagnostics_api.py`（新） | 临时 DB/根、假 Key、隔离 HTTP 权限与输出测试 | 不访问生产 DB/服务。 |
| `tests/workspace_role_diagnostics.test.cjs`（新） | DOM/VM 纯样例交互和迟到响应测试 | 不冒充真实 Browser/键盘验收。 |
| `docs/guides/RUNTIME_EXCEPTION_LOGS.md` / `MODULE_webui.md` / `USER_MANUAL.md` | 实施后由 Codex 更新 | 本次不修改正式文档；不能把方案写成已上线。 |
| `config.toml`、DB、生产日志根 | 本方案不改 | 来源配置和全根治理另片；不在日志查看片做不可逆清理。 |

## 9. 验收步骤与证据分级

### 9.1 本次方案已完成的真实检查

- 静态阅读上述冻结文件并记录行号；只读必要源码，不读取真实日志、生产 DB 或凭据。
- 使用 `contract-examples.json` 和 `fixtures/raw-runtime-records.jsonl` 做纯数据白名单/恶意字段检查。
- 使用 `check_design.py` 核对必需设计条目、公开样例无详情泄漏、扫描不完整无下一页、详情帧无路径/源码行、来源文件 SHA-256 与清单一致。
- 结果保留于`.tmp/runtime-logging-parallel-1/independent-review/273/corrected/evidence/static-check-results.json`；本地证据脚本不属于产品运行入口，这是本次自检，不是 Codex 独立复核，也不是产品测试。

### 9.2 未来实现后的隔离验收顺序

1. 在独立临时根生成两项目、两角色、两个实例/launch 和多个 run 的假 JSONL；所有 Key、CLI、HTTP 均为假件/隔离实现。
2. 启动隔离 FastAPI TestClient 或随机回环端口，配置仅指向临时日志根；确认生产 DB、真实 logs/runtime 和真实服务均未被触碰。
3. human 完成默认摘要、筛选、旧实例、旧 ref、详情、完整分页；Agent 403；无 Key 401。
4. 逐项执行 `acceptance-matrix.md` 的权限、路径、游标、预算、过期和脱敏负例，核对响应体与服务器测试日志均无秘密/绝对路径。
5. 模拟来源不可达、坏行、符号链接/reparse、扫描超时和写日志降级；确认不返回假空态、不假 404、不影响既有服务投影。
6. 前端用 DOM/VM 验证默认无堆栈、显式详情、空态/无权限/不完整文案、旧新实例、上下文切换和迟到响应；再单独记录“未做真实浏览器”。
7. 实现人明确区分：静态检查、隔离 API、DOM/VM、同机宿主、跨宿主、真实 Browser、人类页面验收，不能合并成一句“全部通过”。
8. 由项目管理者在实际发布后 Ctrl+F5，按角色详情逐项做人验；本方案不启动/停止真实角色，不代替该门禁。

详细矩阵见[验收矩阵](ROLE_RUNTIME_LOG_VIEW_ACCEPTANCE.md)，公开样例见[契约样例](ROLE_RUNTIME_LOG_VIEW_EXAMPLES.json)。原来源行号/17个冻结SHA及修正后的静态证据保留在.tmp/runtime-logging-parallel-1/independent-review/273/；原源码可从eec9094追溯。

## 10. 明确不在本方案内

- 不实施页面/API/MCP，不改当前角色列表精简文案。
- 不改变 ready、owner、claim/report、启停、人工恢复、自动恢复或租约。
- 不启动/停止服务，不调用模型，不创建健康探测任务，不读真实日志或生产凭据。
- 不补宿主心跳、queue heartbeat 或主动领取能力探针；只标出所需后续数据。
- 不制定全根目录容量治理、跨 run 自动删除、归档或其它不可逆清理策略。
- 不宣称完整异常日志整项、跨宿主查询、真实页面或 worker 健康已完成。
