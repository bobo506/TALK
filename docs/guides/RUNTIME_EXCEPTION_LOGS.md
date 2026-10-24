# TALK 桥接运行时异常日志（维护者指南）

> 2026-10-24 14:25收尾：325对角色字段证据补正独立复验complete/2966已收取，无必须修正项；33份新/45份旧快照与逐字段binding/service核验通过，324原partial及历史不可恢复限制保留。后台清理已启用、日常自动检查，本轮无需重启。首次0删除/4保护=3旧缺证+1新API未关闭；30天长期/未来生产到期删除未实跑、1GiB软预算及286保护保持，不称完整日志整项完成。详[独立收尾记录](../spec/BACKEND_LOG_AUTO_RETENTION_DEPLOYMENT_20261024.md)。

> 2026-10-24 14:01：324部署独立复核机制/自动检查通过，角色字段采证遗漏导致原partial已收取。协调方已修采证helper、只读补采完整当前公开角色及原service/绑定一致性；不可恢复的旧展示/choice字段明确缺失，不造历史，待定向复验。清理已启用，产品/配置/服务本轮未改，日常无需操作；首次4保护正确为3旧缺证+1新API未关闭。详[补正记录](../spec/BACKEND_LOG_AUTO_RETENTION_DEPLOYMENT_20261024.md)。

> 2026-10-24 13:23实际加载：新API/runtime/七宿主及自动检查已核验，后台首次complete/无错误/删除0/保护4旧run/907191字节，下次本地10月25日13:21:30；只恢复DSH并验60.078633秒心跳，其余六停止。新三组件活跃lease由Windows冲突32证明，closed不存在，五旧范围/绑定/286保持。日常自动检查，无需前台清理。当前为协调方加载自检通过，待DeepSeek首次部署证据独立复核，旧缺证与未闭环任务仍保护、长期和未来生产到期删除尚待；详[加载记录](../spec/BACKEND_LOG_AUTO_RETENTION_DEPLOYMENT_20261024.md)。

> 2026-10-24 13:20：用户已确认本片清理启用并正常重载，原runtime/七宿主已正常退出，backend_enabled=true已应用、新SHA428c928e…e09825。当前待原终端正常重启TALK API，再核实际后台检查并恢复原DSH；配置落盘尚不代表加载通过，286和旧缺证run继续保护。详[加载记录](../spec/BACKEND_LOG_AUTO_RETENTION_DEPLOYMENT_20261024.md)。以下为批准前及历史阶段状态。

> 2026-10-24后台清理候选：323独立复核complete/已收取，无必须修正项，独立新22项及真实隔离API通过；组合104通过/1项ACL临时文件清理限制，Codex自检105通过。backend_enabled缺省false、专用关闭证明及共享项目任务保护已实现，生产开关仍未添加，SHA db98e42d…a8543c保持。仅增backend_enabled=true的[具体启用方案](../spec/BACKEND_LOG_AUTO_RETENTION_DEPLOYMENT_20261024.md)已预检，待明确确认后正常重载；日常无需前台操作。项目存在paused/未闭环任务（包括286）或旧run缺新关闭证明仍保留，不承诺启用后立刻删除。详[本片合同](../spec/BACKEND_LOG_AUTO_RETENTION_20261024.md)。

> 2026-10-24：322首次部署证据独立复核complete/pass并已收取，无产品修正项；真实加载/三组件导出及保护边界证据通过，原权限/ACL/P3限制保留。新后台根仍只分段，不自动删除；下一片已由用户确认改回Codex开发清理覆盖、DeepSeek复核，尚未实现或启用。详[322收尾记录](../spec/BACKEND_DIAGNOSTICS_DEPLOYMENT_20261023.md)。

> 2026-10-23 23:24：原API已由用户正常重启，后台/API/worker三组件实际采集及human下载、401/403通过；仅恢复原DSH并核实连续心跳。角色合并文件因旧来源扫描仍明确partial，后台历史也固定不完整。新后台根只分段、不自动清理；目前待独立部署证据复核及页面人工体验。下方23:13为当时等待点，详[实际加载记录](../spec/BACKEND_DIAGNOSTICS_DEPLOYMENT_20261023.md)。

> 2026-10-23 23:13：用户已确认启用，原统一宿主/角色普通退出后，仅追加下方backend_diagnostics配置（新SHA db98e42d…a8543c）。现等待原终端正常重启API，再核实际三组件采集并仅恢复DSH；配置落盘不等于加载验收通过。旧五范围自动清理不变，详[部署记录](../spec/BACKEND_DIAGNOSTICS_DEPLOYMENT_20261023.md)。下方321收尾是部署前状态。

> 2026-10-23 321收尾：F1/F2/OBS1及错误分类主路径独立复验通过，另发现的`cli_command_unresolved`漏登记由Codex补正，修前反例失败/修后29项定向自检通过；最后修正未追加独立回审。320/321均已收取，原partial与失败证据保留。代码完成收尾，生产仍未启用；待按[具体部署方案](../spec/BACKEND_DIAGNOSTICS_DEPLOYMENT_20261023.md)确认后正常加载。以下22:26为修正前阶段记录。

> 2026-10-23 22:26：后台/API导出320独立复核发现路径角色/持久路由校验和已知错误码缺陷，Codex已按报告修正，87项针对性自检及新真实隔离HTTP通过，待定向独立复验，生产仍未启用。无效路径值不作为角色身份，新流导出须核真实角色/应用模板；已正确开启联合导出时来源全缺为200 partial，未开启/未绑定保持旧来源缺失503。原320 partial/失败证据、旧五范围自动清理不改写。

> 2026-10-23后台/API统一导出候选已实现、自检通过，尚未独立复核/生产启用，详[本片合同](../spec/BACKEND_DIAGNOSTICS_EXPORT_20261023.md)。启用后仍从角色详情选择时间“生成/下载”，同一JSONL新增`backend_event`（API/统一后台/配置worker），后台共享事件明确标注，不伪造角色；也提供human-only项目后台接口`/api/projects/{project_id}/backend-logs/export?since=...&until=...`。旧输出/崩溃空档及未归属全局请求不能补全，文件会保守标为部分结果；只保留异常类型/调用栈，不含消息、请求正文/头、原生会话。新后台根未注册清理，不扩大下方已启用五范围策略。

候选部署配置（本机实际启用须通过独立复核及具体部署确认）：

```toml
[backend_diagnostics]
enabled = true
root = "D:/claude-test/TALK/logs/backend"
database_file = "D:/claude-test/TALK/talk.db"
projects = ["prj_e8fe7066bbec"]
```

该节缺失/关闭不采集新后台流；错库/空根/UNC/非法项目清单拒用。角色/worker/Key和原清理配置不用改变。配置生效需API与原统一后台正常重载；只改配置不会让旧进程自动加载，不能为了日志强杀服务或绕过owner保护。

> 2026-10-23自动清理片已正式启用：318代码与319首次部署独立复核通过并收取，首次后台完整检查保护454旧缺证run/删除0/约508MiB、次日due保存，DSH恢复、其它六角色仍停止，详[部署记录](../spec/LOCAL_LOG_AUTO_RETENTION_DEPLOYMENT_20261023.md)。规则见[合同](../spec/LOCAL_LOG_AUTO_RETENTION_DESIGN_20261023.md)：同DB绝对路径、writer总根/五个精确project/member范围，每日检查/启动补检，30天保留及1GiB软预算，日常无需页面操作。未知/缺证/空任务旧run保持；摘要partial不视为全量，30天长期/生产未来删除尚未实跑。不要删除policy/lease/closed/retention痕迹来触发清理或恢复旧策略。

> 2026-10-23本机盘点片：新增维护者只读入口`python scripts/runtime_log_inventory.py --log-dir <显式日志根>`，只统计元数据并输出旧分段核查预览，不能删除日志，也不证明run已关闭。315独立复核发现旧时间/空根缺陷后已修正，316定向独立复验通过，两任务均收取。默认30天/单根1GiB只是报告提案，未改writer或生产设置，现有writer每run自动清理策略继续保持，完整日志收尾未完成。使用限制及覆盖缺口见[本片报告](../spec/LOCAL_LOG_INVENTORY_AND_RETENTION_20261023.md)。工具无需重启服务；空白根会拒绝，旧时间可格式化，超出日期范围返回partial。2026-10-20用户已停止推进下方旧B联网接收路线，286继续暂停，跨设备分析通过导出文件手动转移。

> 2026-10-20 10:19加载更新：282实现6f3f9c5已沿既有排空入口正常重载五宿主、普通恢复四个原运行角色；77.568秒间隔的真实seq/60秒采样、精确launch原进程观测和60–90秒心跳推进均通过，Codex桥接保持关闭、API及绑定保持。页面状态已获用户明确验收通过；B接收/跨宿主来源及C全根治理未完成，详[加载记录](../spec/ROLE_HOST_RUNTIME_EVIDENCE_LOAD_282.md)及[282复核](../spec/ROLE_HOST_RUNTIME_EVIDENCE_REVIEW_282.md)。

> 2026-10-19 23:02加载更新：用户明确许可后279已在原4运行角色实际加载，真实queue_poll开始/成功与seq推进、完整JSONL下载、原父链和约150秒心跳均通过，Codex保持关闭。旧的“生产尚未加载/待许可”为当时门禁，原审批拒绝及失败证据保留。异常/恢复分支已有隔离验证，本轮没有生产故障演练；完整日志整项仍未全部完成，详[279复核](../spec/ROLE_QUEUE_POLL_DIAGNOSTICS_REVIEW_279.md)。

> 2026-10-19 279代码更新：接单查询新增queue_poll_snapshot/queue_poll_recovered及固定12键extra.queue_poll，统一诊断下载新增可空queue_poll。真实查询起止/序号/单调耗时、30秒有界快照、失败段/恢复证据已集成，290 Python/24 Node通过；旧记录缺值为null。当前生产尚未加载，批量停服被自动审批拒绝，待用户明确本次正常加载许可，不能据源码存在宣称实机采集通过。详[279复核](../spec/ROLE_QUEUE_POLL_DIAGNOSTICS_REVIEW_279.md)。以下旧版说明按各自历史范围保留。

> 状态：271/272已收取，五宿主与角色启动日志实机加载已验；274同机人类只读API经独立复核后由Codex直接修正，81项相关自检通过并收取。**274尚未配置生产来源或部署加载，275页面未合入，MCP未新增日志查询入口**。
> 本文件是维护者入口，不是普通用户页面说明，不能据此声称“完整异常日志整项完成”。

## 1. 本片实际落了什么

通用 CLI bridge（`bridges/cli_bridge.py`）在关键边界调用 `bridges/runtime_diagnostics.py`，把本机诊断记录写入 `logs/runtime/`。Codex / Kimi 专用入口继续复用同一个 `run_bridge` / 任务队列 / 消息处理实现，因此不需要另建写入器。

每条记录包含：

- 实际可得关联：`project_id`、`member_id`、`instance_id`、`pid`、`runtime`、`launch_id`、`task_id`、`message_id`、`stage`。未知字段保持 `null`，不按模板补值。
- 时间：ISO 8601，带本机时区偏移。
- 异常：类型、净化后的 `str(exc)`、全部可得 traceback 帧（文件/行号/函数，附净化后的源码行）、显式 `__cause__` 链和隐式 `__context__` 链；空消息也有类型和帧。
- 执行边界：CLI 返回码、超时/取消类别、实际 CLI 超时、HTTP 超时、任务租约与心跳间隔、队列轮询间隔；MCP 读取等待预算固定记录为未知（`null`），不修改也不猜测。
- 二次失败：独立记录，并用 `related_log_id` 指向本次任务/边界的首条错误。
- 完整性标志：`integrity.redacted`、`redaction_kinds`、`truncated`/`truncated_fields`、`write_complete`。

本片接入的边界：

- `run_bridge`：启动、注册、初始实例状态、受管实例心跳失败、正常受管停止、transport 异常、offline 状态回报失败、client close 失败、bridge 停止。
- 普通消息：CLI 非零、超时、取消、消息处理异常、状态回报二次失败。
- 队列任务：预检失败、领取失败/冲突、CLI 非零/超时/取消、租约丢失、结果发送失败、完成任务回报失败、任务完成结果。
- 任务队列：worker 启动、单轮异常、状态回报二次失败、正常/受管/异常停止。
- 任务终态兜底：预检连续失败后的 accept/claim/结果发送/完成回报失败。

不记录提示词、完整 argv、完整环境、配置快照、locals、原生认证或完整 stdout/stderr。CLI 失败只保留很短的第一条净化摘要；异常日志不保存子进程完整输出。

## 2. 实际落盘路径与默认值

默认根目录：

```text
<仓库根>/logs/runtime/
```

`logs/` 已被仓库 `.gitignore` 忽略，不会随 Git 提交。目录结构：

```text
logs/runtime/
├─ <安全 member 标识>/
│  └─ <安全 instance 标识>/
│     └─ <run_id>/
│        ├─ manifest.json       # 本次 run 的身份/策略/启动时间
│        ├─ events-00001.jsonl  # 主事件流
│        ├─ rotation.jsonl      # 轮换记录
│        └─ retention.jsonl     # 删除/到期清理记录
```

- 每次进程/实例启动都会生成新的 `run_id`，使用独立目录；不会清空旧 run、旧实例或其它角色目录。
- member/instance 名会转换为安全路径组件（非法字符替换并附加短 SHA-256 后缀）；写入前还校验目录不是符号链接、未越出受控根目录。
- 每个 segment 是独立 JSONL 文件；追加写入，轮换时新建文件，不覆盖旧 segment。
- 默认策略：

| 项 | 默认值 | 覆盖方式 |
|---|---|---|
| 根目录 | `<仓库根>/logs/runtime` | `TALK_RUNTIME_LOG_DIR` 或 `--runtime-log-dir` |
| segment 轮换大小 | 8 MiB | `TALK_RUNTIME_LOG_MAX_FILE_BYTES` 或 `--runtime-log-max-file-bytes` |
| 本 run 事件文件容量目标（软限制） | 256 MiB | `TALK_RUNTIME_LOG_MAX_BYTES` 或 `--runtime-log-max-bytes` |
| 本 run 旧 segment 留存 | 30 天 | `TALK_RUNTIME_LOG_RETENTION_DAYS` 或 `--runtime-log-retention-days` |
| 关闭本进程写入 | 不关闭 | `TALK_RUNTIME_LOG_DISABLED=1` 或 `--disable-runtime-logs` |

`--runtime-log-*` / `--disable-runtime-logs` 已加入通用parser，Codex/Kimi入口继承。272宿主也支持同名参数/环境变量及临时根注入；内置配方传递显式策略，自定义`--cli-executable`入口argv保持。相对根在宿主解析时冻结为绝对路径，默认开启。五长期宿主已于2026-10-19正常重载并实际写入host_started，角色launch/bridge启动日志与周期心跳已于09:56实核通过。

## 3. 轮换、容量与清理

- 写入下一条事件前，如果当前 segment 加上新记录会超过 `max_file_bytes`，就新建 `events-NNNNN.jsonl`；旧 segment 保留。
- 容量统计针对本run事件文件，不含manifest/轮换/清理痕迹文件，也不是全根目录硬上限；痕迹文件及旧run的总体空间治理仍待后续。每个 run 的总事件字节数超过 `max_bytes` 时，按最旧 segment 优先删除；如果只剩当前 segment 仍超限，记录中会有 `integrity.capacity_soft_exceeded=true` 和 `truncated=true`，不会静默假装完整。
- 删除前先向 `retention.jsonl` 写 tombstone（原因、文件名、大小、时间、保留天数/容量）；tombstone 写失败时不会继续删除，并输出可见降级。
- 轮换时向 `rotation.jsonl` 写 `action=rotate` 记录；正常长运行每 100 次写入会触发本 run 的到期清理。
- 清理只作用于**当前 run 自己的** `events-*.jsonl`，不会跨角色、跨实例删除；旧 run 目录默认保留，便于重启后追溯。当前没有“全根目录自动归档/批量清理”的维护命令；这是本片明确限制，部署时应另行规划保留空间和外部归档。

## 4. 稳定引用与公开错误

每条记录在写盘前分配稳定引用，例如：

```text
rtd-031f55a209-000001
```

引用在进程重启后仍可通过受控查询定位。日志引用不会包含密钥、提示词或路径信息。公开错误摘要 / `last_error` 只追加：

```text
[日志引用：rtd-...]
```

或 `log_ref=rtd-...`。完整异常消息、traceback 和因果链不进入聊天回复、实例状态或任务公开字段。若日志写入失败，就没有可信的持久引用；此时只输出净化后的“诊断日志降级”提示，不伪造引用。

## 5. 本地受控查询

维护者入口是 `scripts/runtime_diagnostics.py`，只扫描受控日志根目录下的 `events-*.jsonl`，不接受文件路径，也不会把 `--ref` 解析为路径。

```bash
# 默认摘要（不打印堆栈）
python scripts/runtime_diagnostics.py --ref rtd-031f55a209-000001

# 按角色/实例/任务定位
python scripts/runtime_diagnostics.py --role agent:deepseek --task 271 --limit 20
python scripts/runtime_diagnostics.py --instance agent:deepseek:... --event task_lease_lost

# 显式读取净化后的堆栈与因果链
python scripts/runtime_diagnostics.py --ref rtd-031f55a209-000001 --detail

# 机器可读
python scripts/runtime_diagnostics.py --ref rtd-031f55a209-000001 --detail --json
```

- 默认只输出：时间、event/severity/stage、身份/任务、异常类型与短消息预览、帧数、因果深度、关联引用、预算、完整性标志、相对来源文件。
- `--detail` 才输出 sanitized traceback 帧与 cause chain；仍不包含提示词、完整 argv、环境或 stdout/stderr。
- 查询默认限制20条、最多200条；目录枚举和读取均受文件数/时间预算约束，读取还受文件字节预算约束，达到上限明确提示“scan was limited”。只在有界候选集合内按文件新近排序，不能将被限制的查询当成全库无匹配。
- 非法引用、缺失根目录、非法 limit 返回非零短错误；不会回显路径或文件内容。
- 日志本身是本地明文文件，访问边界依赖宿主机文件权限；不要把日志目录放到可被普通用户读取的共享位置。

### 282：查看本地宿主循环与原进程观测

当前五长期宿主已正常加载，实机新记录及周期推进已核验；本机日志根为`logs/runtime`。其它部署仍需管理员先正常加载。将下面的`<宿主实际日志根>`替换为管理员确认的受控目录，在仓库根运行：

```text
python scripts/runtime_diagnostics.py --log-dir "<宿主实际日志根>" --event manager_round_snapshot --limit 20 --json --detail
python scripts/runtime_diagnostics.py --log-dir "<宿主实际日志根>" --event launch_process_snapshot --limit 20 --json --detail
```

必须带`--detail`才能看到extra里的固定对象，默认JSON摘要不含它。manager_run_id关联本次serve的启动/结束/快照，manager_seq仅随真实轮次推进，正常快照每60秒一组；started只表示开始，不能证明轮次完成。launch_process只表示原Popen的最近观测，alive不代表bridge、接单或模型可用。未观测、超限或无法确认时保持未知；旧记录不回填身份或时间。

manager记录保持member=unknown，不进入角色下载；角色下载也不透传新extra。此处是维护者本地查询，无新API/账号/Key或服务端received_at。刷新页面、只重载API或只重启bridge不能替代宿主加载；先核空闲/原归属及正常退出入口，按[282加载门禁](../spec/ROLE_HOST_RUNTIME_EVIDENCE_REVIEW_282.md)安排，不据旧PID接管或解除owner。

## 6. 脱敏规则与限制

写入前使用以下组合：

- 本次 bridge 内存中已知的 API Key（`args.key`，包括从 `--key-file` / `TALK_ROLE_API_KEY` 解析出的值）和调用点显式传入的提示词/任务文本，按原值替换。
- `Authorization` / `Proxy-Authorization` / `X-Api-Key` / `Cookie` 等 header、`Bearer` token、URL 查询参数、`token/key/password/secret` 等字段。
- 常见 opaque 前缀（`sk-`、`ghp_` 等）、JWT 形态、私钥块、URL userinfo。
- 嵌套 `extra` 字典/列表中敏感键的值；异常 cause/context 的每一层消息都会经过同一净化器。
- 提示词/已知秘密先在完整文本上净化，再取CLI短摘要；异常传播保留本次保护值，并处理repr/JSON转义。标准子进程异常的cmd/output直接省略，保类型、退出码/预算与调用帧。带空格的引号敏感字段及owner/session token也净化。
- 截断后仍保留明确的`truncated`标志；因果链深度上限也计入默认摘要的完整性标志。普通消息关联message_id，不冒充TALK task_id。

**限制**：这是启发式脱敏，不是秘密扫描器。未传入、未命中模式且不形似常见凭据的 opaque 值仍可能留在异常文本里；因此不要主动把真实凭据拼进异常消息、提示词或测试假件之外的日志输入。本片不读取全环境、认证文件或数据库来做脱敏。traceback 帧源码行也会净化，但仍可能含本地绝对路径；`--detail` 仅面向维护者。

## 7. I/O 降级与故障边界

- 根目录不可建、namespace 越界、写入失败、轮换/清理失败时，向 stderr 输出：

  ```text
  [runtime-diagnostics] 本地诊断日志降级：<reason> (<ExceptionType>)
  ```

  不回显异常正文，避免二次泄密；同一个降级原因只提示一次，不递归写日志、不无限重试。stderr本身不可写时也不替换原产品异常或再抛日志异常。
- 某条事件写入失败只会丢失该条记录；bridge 继续按照原有任务/消息语义运行。任务完成、实例状态、租约、取消和子进程停止逻辑不由诊断 I/O 结果决定。
- 异常处理路径先记录首条错误，再尝试状态/结果回报；二次失败独立写一条记录并通过 `related_log_id` 关联。状态回报失败不会替换原异常；`CancelledError` 和受管正常停止仍按原语义传播/退出。
- 受管实例心跳失败不停止 transport、不改变 owner、不自动重启角色；只在本地记录并输出含引用的简短 stderr 提示。
- 日志写入失败时原任务仍按原 claim/complete 流程处理（测试覆盖 claim_token 保持）。

## 8. 本片仍未覆盖 / 部署前提

仍未覆盖：

- 272五宿主正常重载及manager日志已核验；新宿主下角色launch/readiness、服务端running/ready与bridge心跳已实核；新宿主实际接单/模型及公开日志状态展示仍待，不能由host_started或queue_started推断接单健康。
- 274已实现human-only查询API代码；生产来源配置/加载、页面查看及页面健康/日志呈现仍待，当前维护者继续使用本地CLI。
- `server/logging_config.py` 与 bridge 诊断的统一；API 日志和 bridge JSONL 是两条链。
- 角色服务启动前的 Python 导入阶段、宿主管道输出、原生 CLI 自身 stderr、MCP 读取等待预算。
- 进程主循环存活 vs 接单循环可用的服务端健康字段；本片只写本地事实，不虚构服务端 `worker healthy`。
- 自动重启、退避、任务重派/恢复、租约策略变更。
- 全根目录旧 run 的自动归档/容量回收（当前只清理当前 run 的旧 segment）。
- 2026-10-18 20:41 DeepSeek首位实机加载通过：用户正常重启，新ins_4643da0b3d34/launch dedf3e82-06d2-44b7-b1fe-788b3e3b49c2；真实bridge_started/queue_started、持续心跳和本地引用查询通过。20:48其余四角色及再次换实例的DeepSeek全部核验通过：新实例/原宿主父链、连续心跳、真实启动/队列日志及引用查询吻合；上一代DeepSeek日志仍可查。当前五位加载已闭合，具体实例/证据见[当前进度](../PROGRESS.md)。

部署/使用前提：

- 新代码在正常宿主关闭→启动后生效，须先核角色空闲及原归属。执行任务中的角色不得自行停止本人或其它角色；重载API、改Key/模型/绑定不属于本片加载步骤。
- 需要可写的本机日志目录；显式目录必须由维护者配置并保证访问权限。
- 真实凭据不得用于负向测试；测试使用假件。
- 需要长期保留时，应由部署方按磁盘容量规划 `TALK_RUNTIME_LOG_MAX_BYTES` / 保留天数和外部归档；本片不承诺跨机器集中日志。

## 9. 针对性自测入口

```bash
python -m unittest tests.test_runtime_diagnostics
```

新增用例覆盖：空异常消息、显式/隐式因果链、known/opaque/header/URL/嵌套脱敏、轮换与 tombstone、双实例并发、重启后按旧引用查询、路径式引用拒绝、日志目录/写入失败降级、消息与队列的二次状态失败、CLI 非零/超时/取消、租约丢失、预检/领取错误、受管心跳失败、公开摘要与默认查询不泄露假凭据。

DeepSeek首次自报281项相关回归，4条stdio pipe用例因受限沙箱WinError 5未运行，原失败保留。Codex首次独立反例6项出现5失败/1错误，直接修正后相关9模块共293项Python回归全部通过，包含原先4条管道用例；初次独立复核与修正后自检分别记录，不称二次外部独立复核。详[271复核记录](../spec/ROLE_RUNTIME_LOGGING_REVIEW_271.md)。

## 10. 代码入口

- `bridges/runtime_diagnostics.py`：写入器、净化、异常链、轮换/清理、受控查询。
- `bridges/cli_bridge.py`：bridge / 消息 / 队列 / 任务 / 受管心跳边界接入。
- `scripts/runtime_diagnostics.py`：维护者本地查询入口。
- `tests/test_runtime_diagnostics.py`：本片隔离验证。

## 272宿主持久诊断（2026-10-19五宿主及角色启动日志已实机加载）

`scripts/role_service_host_diagnostics.py`复用同一基础API/schema，覆盖宿主claim/预检、输出准备/spawn、所有权保存/readiness、stop/control/timeout、report二次失败、poll恢复及配置worker。角色launch事件带真实项目/member/实例/launch，顶层PID为宿主、子进程PID在extra；manager事件member为unknown，不借用角色。预算按实际已知值记录，MCP等待仍未知。

保护值包括本次实际运营/本人Key、report新claim/owner、实际child_env快照中敏感名称的值；不扫描全环境或额外认证。输出文件准备失败原样传播并关闭部分打开流，不改变原业务/归属；已知日志/降级失败不替换原异常。启发式脱敏的原限制保持。

每个manager/launch使用独立run，仍可用现有CLI跨run按ref/member/instance查询。`ready`是本地就绪观察，不代表后续report成功；host_started/host_stopped是serve边界，不足以证明OS进程/worker健康。公开API/schema未扩展，日志ref仍只在本地；全根空间治理与权限页面后续。详[272复核记录](../spec/ROLE_RUNTIME_LOGGING_REVIEW_272.md)。

09:46实机核验：用户关闭五角色并明确授权Codex重启后台宿主后，五原宿主逐个正常drain退出、新宿主沿原命令启动；五host_started的项目/runtime/PID、完整写入及引用回查通过，并另查真实进程与私有状态持续更新。manager的member/instance均unknown，不混入角色视图。角色保持stopped、归属已释放，配置/服务快照不变，无强杀/接管/恢复API或模型调用；09:56用户已确认页面启动成功，后续launch/bridge/周期心跳补验结果见下段。证据`.tmp/runtime-logging-parallel-1/host-load272/verified-all.json`，本次不证明跨沙箱重启常驻或完整日志整项完成。

09:56角色启动补验：五服务running/ready、实例idle且归同一新manager直接持有；各launch_claimed/spawned/ready及bridge_started/queue_started共25条真实记录与身份/launch/PID/child_pid吻合，完整写入并按引用查回，ready/queue引用共10条通过维护者CLI；两次同实例心跳均推进约60秒。旧五个271队列引用和正常停止记录保留。证据`.tmp/runtime-logging-parallel-1/host-load272/role-start/`；本次只读、无新任务/模型调用，不声称已验证新宿主实际接单或六小时能力。

273日志查看/健康反馈[正式方案](../spec/ROLE_RUNTIME_LOG_VIEW_DESIGN.md)已收取。其36项静态检查/67项[设计矩阵](../spec/ROLE_RUNTIME_LOG_VIEW_ACCEPTANCE.md)为发布时基线；274后端和275页面已独立复核后直接修正并实机加载，见[274复核](../spec/ROLE_RUNTIME_LOG_VIEW_REVIEW_274.md)、[275复核](../spec/ROLE_RUNTIME_LOG_VIEW_REVIEW_275.md)。页面人工效果及健康补数仍待，本地CLI继续可用。

## 274/275同机查询API与页面（已加载，页面待人验）

新增两个human-only只读路径：

- `GET /api/projects/{project_id}/roles/{member_id}/runtime-logs`：默认最近24小时warning/error、20条，支持规范化筛选/分页或独立精确ref。
- `GET /api/projects/{project_id}/roles/{member_id}/runtime-logs/{log_ref}/detail`：显式详情，不接受任何query参数；info无异常时`exception=null`。

Agent返回403；人类还需存在项目/历史角色对，记录逐条核当前URL scope。网络详情只有净化后文件名/行号/函数及因果链，不给源码行或本地绝对路径；本地维护者CLI行为保持。

来源仅由管理员通过现有配置加载，缺省为空。275已在本机config.toml显式登记当前项目五个角色各自绝对根，包含旧/新实例、排除unknown的manager根；换部署机器须重新核对绝对目录，不能直接沿用本机路径。下列是**虚构示例**：

```toml
[[runtime_diagnostics.sources]]
project_id = "prj_example"
member_id = "agent:example"
root = "D:/TALK-logs"
```

每个project/member对唯一、root必须为本机绝对目录；共享根仍严格筛记录身份。未配/来源不可达返回503，没有默认根回退或HTTP路径参数；需正常加载API后才生效。扫描不完整不当作无异常，规范化分页依据已确认变化409、不可安全读取503；不从未找到推断过期。

274原43项/1跳过自报与失败保持；Codex修正后81项相关自检零跳过，含真实Windows换链和随机回环HTTP。275串行集成后95项Node、1项真实隔离HTTP联调及五角色实机权限/旧日志检查通过；API已正常加载。部署时配置换行失误的失败及修复、原宿主普通关启恢复、90秒新实例心跳证据见[275复核](../spec/ROLE_RUNTIME_LOG_VIEW_REVIEW_275.md)。

人类Ctrl+F5→角色→具体角色→运行诊断，点击“查看运行日志”才读取，摘要/独立ref与显式详情分开。默认可见本次真实断连留下的历史错误；不要据旧错误判新实例故障。页面视觉/窄屏/键盘人验、跨宿主、健康新增事件及全根治理仍待；API暂断后接单循环error的恢复收敛也需后续独立处理。
