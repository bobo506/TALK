# TALK 桥接运行时异常日志（维护者指南）

> 状态：271基础/通用bridge已收取且五角色已加载；2026-10-19任务272宿主持久诊断经Codex独立复核、直接修正及141项相关自检后已收取，**长期宿主尚未重启加载272**。仍没有新增页面、API或MCP查询入口。
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

`--runtime-log-*` / `--disable-runtime-logs` 已加入通用parser，Codex/Kimi入口继承。272宿主也支持同名参数/环境变量及临时根注入；内置配方传递显式策略，自定义`--cli-executable`入口argv保持。相对根在宿主解析时冻结为绝对路径，默认开启。现有长期宿主未重载，不能据此称真实宿主已写入新日志。

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

- 272宿主接入代码已完成；长期宿主真实重载/加载验证及公开日志状态展示仍待，不能把271的bridge加载等同宿主已部署。
- API 查询权限、页面查看、页面上的健康/日志呈现。
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

## 272宿主持久诊断（2026-10-19代码通过，尚未加载实机）

`scripts/role_service_host_diagnostics.py`复用同一基础API/schema，覆盖宿主claim/预检、输出准备/spawn、所有权保存/readiness、stop/control/timeout、report二次失败、poll恢复及配置worker。角色launch事件带真实项目/member/实例/launch，顶层PID为宿主、子进程PID在extra；manager事件member为unknown，不借用角色。预算按实际已知值记录，MCP等待仍未知。

保护值包括本次实际运营/本人Key、report新claim/owner、实际child_env快照中敏感名称的值；不扫描全环境或额外认证。输出文件准备失败原样传播并关闭部分打开流，不改变原业务/归属；已知日志/降级失败不替换原异常。启发式脱敏的原限制保持。

每个manager/launch使用独立run，仍可用现有CLI跨run按ref/member/instance查询。`ready`是本地就绪观察，不代表后续report成功；host_started/host_stopped是serve边界，不足以证明OS进程/worker健康。公开API/schema未扩展，日志ref仍只在本地；全根空间治理与权限页面后续。详[272复核记录](../spec/ROLE_RUNTIME_LOGGING_REVIEW_272.md)。

273日志查看/健康反馈[正式方案](../spec/ROLE_RUNTIME_LOG_VIEW_DESIGN.md)已复核修正收取，含human-only同机显式来源、规范化分页/失效、旧ref与预检证据未知语义。36项静态检查及样例复测不等于API/页面已上线；67项[未来矩阵](../spec/ROLE_RUNTIME_LOG_VIEW_ACCEPTANCE.md)仍not_run，本地CLI继续作为当前定位入口。
