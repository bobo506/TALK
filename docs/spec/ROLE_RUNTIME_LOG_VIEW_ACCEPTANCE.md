# 273 日志查看与健康反馈：验收步骤和隔离负向测试矩阵

> 本文件保留273发布时的未来验收合同，不是当前全部已通过清单。274/275实施与联调证据分别见[274复核](ROLE_RUNTIME_LOG_VIEW_REVIEW_274.md)、[275复核](ROLE_RUNTIME_LOG_VIEW_REVIEW_275.md)；本表尚未逐编号核销，人工页面验收及后续健康能力仍待，不得用测试总数声称矩阵全部通过。

## 1. 测试 fixture 与隔离要求

- 临时目录结构：两个项目 `prj_a/prj_b`；角色 `agent:a/agent:b`；各两个实例和两个 launch；每个实例至少两个 run。
- 数据类型：info/error/warning、显式/隐式 cause、帧省略、链截断、写完整/截断标志、正常记录、坏 JSON 行、无项目归属旧记录。
- 所有凭据使用明显的 `FAKE_*` 假值；命令为不会联网/启动模型的假 CLI；DB、日志根、静态资源和 HTTP 全部使用独立临时根或 TestClient。
- 负例另放符号链接、Windows reparse point（平台支持时）、伪路径 ref、跨项目同 ref、重复 ref、过期游标和超大扫描集合。
- 每个测试结束只清理由该测试自己创建的临时根；不指定真实 logs/runtime，不访问生产 DB/凭据，不启停真实服务，不调用模型或浏览器。

## 2. 未来隔离正向验收

| ID | 层 | 操作 | 必须观察到的结果 |
| --- | --- | --- | --- |
| P-01 | API | human 请求默认摘要 | 默认 24 小时、error+warning、最多 20 条；只有摘要白名单和 ref，无 frames/cause_chain。 |
| P-02 | API | human 切换“全部事件” | 可查 info 的 queue_started 等；不影响默认异常筛选。 |
| P-03 | API | 组合实例 + launch + event + 时间过滤 | 所有条件 AND；返回记录与 URL project/member 精确一致。 |
| P-04 | API | 查当前实例后查历史实例 | 历史记录仍可读取；实例 offline 不删除日志、不改当前服务状态。 |
| P-05 | API | 精确查旧 ref | 不受默认 24 小时限制；完整扫描唯一命中后返回对应旧记录。 |
| P-06 | API | human 打开单条详情 | 返回全部已记录帧和 cause/context 链；只有 file_name/line/function，无源码行。 |
| P-07 | API | 重放首页规范化query，来源不变时连续读三页 | since/until/severity/snapshot_until固定，无重复；追加/轮换等来源变化改按N-38失效，不承诺继续旧页。 |
| P-08 | API | 完整扫描但无匹配 | 列表 200、records=[]、scan.complete=true、next_cursor=null；显示对应空态。 |
| P-09 | API | 归档角色/禁用成员的历史对仍存在，human 查历史日志 | 允许只读历史，不要求 ready/bound/managed_cli，不允许任何写动作。 |
| P-10 | UI | 打开“运行诊断” | 选中角色时不自动扫描；点击后才发默认请求；原角色开关/绑定重置/任务列表不变。 |
| P-11 | UI | 摘要复制 ref、打开/关闭详情 | ref 可复制；详情只在显式点击后出现，关闭即清空；全部 textContent。 |
| P-12 | UI | 快速切项目/账号/角色并制造迟到响应 | 旧响应不得回填；详情/筛选/分页按新上下文重置，无跨角色残留。 |
| P-13 | UI | 对比五类证据 | 宿主、实例心跳、接单循环、领取证据、领取前预检分列；缺数据为未知，无总绿灯。 |
| P-14 | UI | 注入 idle + queue_started + 无 queue heartbeat | 仍显示“当前接单循环：未知”；空闲不证明可接单。 |
| P-15 | UI | 注入心跳超时和启动回执 | 显示“运行状态待核实/历史回执”，不显示已死亡或当前健康。 |

## 3. 权限与作用域负向矩阵

| ID | 攻击/故障输入 | 预期 |
| --- | --- | --- |
| N-01 | 无 X-API-Key 或无效 Key | 401；扫描器调用次数为 0。 |
| N-02 | 已禁用成员 Key | 沿用现有 403；扫描器调用次数为 0。 |
| N-03 | Agent 请求本人摘要 | 403 `log_read_forbidden`；不是“本人自动放行”，不扫描。 |
| N-04 | Agent 请求本人详情或他人摘要/详情 | 均 403；无记录元数据和时序侧信道式深扫。 |
| N-05 | A 项目 URL + B 项目记录同 member/ref | 404 `log_not_found` 或无该记录；B 内容、路径、异常类型均不泄漏。 |
| N-06 | A 角色 URL + 同项目 B 角色记录 | 不返回；ref 不成为跨角色通行证。 |
| N-07 | URL scope 正确但 launch/task/instance 过滤属于其它范围 | 只得到无结果或稳定过滤错误；绝不放宽 URL scope。 |
| N-08 | 旧记录 project_id=null，但 member/instance 与当前角色相同 | 不混入项目结果；不回填当前项目。 |
| N-09 | 目标角色从未在项目角色/名册历史中存在 | 404 `role_not_found`；不扫全根寻找同名 member。 |
| N-10 | human 直接访问 B 项目自己的端点 | 按现有人类项目读权限处理，但响应只能含 B 范围；与 N-05 的跨项目混读分开断言。 |
| N-11 | 在请求中加入 owner_token/claim_token/agent Key | 未知参数 422；凭据不进入日志、响应或页面存储； token 不是授权依据。 |
| N-12 | 以 business_role=lead/dev 或 decision_tier=decision 的 Agent 请求 | 仍 403；旧标签不扩权。 |

## 4. 路径、符号链接与出口泄漏矩阵

| ID | 攻击/故障输入 | 预期 |
| --- | --- | --- |
| N-13 | ref 为 `../../etc/passwd`、盘符、UNC、反斜杠、NUL、编码 slash | 422 `invalid_log_ref`；不作为路径打开任何文件。 |
| N-14 | 加 `root/log_dir/path/file/host/follow_symlinks` 参数 | 422；不能改变管理员固定来源。 |
| N-15 | 日志根自身是符号链接 | 拒绝该来源并返回不可用/不完整；不跟随。 |
| N-16 | 中间目录或 events 文件是符号链接，指向其它项目/秘密文件 | 跳过并标不完整；无目标文件内容。 |
| N-17 | 平台支持时使用 reparse point 或检查后替换文件 | no-follow/openat/fstat 等防护生效；无法保证则跳过降级，不跟随竞态。 |
| N-18 | 放置 `events-x.jsonl`、manifest、rotation、retention 和普通文本 | 非约定事件文件不读取；tombstone 不当作事件返回。 |
| N-19 | 原始结果含绝对 root、source_file、run_id、pid | 网络响应全部不含；不是直接序列化 query_records。 |
| N-20 | 帧 file 同时含 Windows/POSIX 绝对路径 | 只输出 basename 形式的 file_name；无 drive/UNC/home 路径；无 source 源码行。 |
| N-21 | 记录含 extra、argv、env、配置、stdout/stderr、owner/claim token、假 API Key | 这些字段/值不进入摘要、详情、错误响应或测试服务端日志。 |
| N-22 | 异常 message 含假秘密和绝对路径 | 二次净化后输出；无法安全投影时 503，不回退原文。 |
| N-23 | integrity.redacted=true 但含未知形态 FAKE opaque | human-only 边界与“脱敏非绝对保证”提示仍在；不能宣称秘密扫描完备。 |

## 5. 分页、预算、旧 ref 与降级矩阵

| ID | 攻击/故障输入 | 预期 |
| --- | --- | --- |
| N-24 | limit=0、51、负数、非数字；未知 severity/event 过滤 | 422；limit 默认 20、最大 50；不改变扫描预算。 |
| N-25 | 时间无时区、since>=until、跨度超过 31 天 | 422；精确 ref 不套默认 24 小时。 |
| N-26 | ref 与 cursor/时间/其它过滤同时传 | 422 `conflicting_filters`；不静默忽略任一条件。 |
| N-27 | 游标被篡改、跨项目/角色/过滤复用 | 422 `invalid_cursor` 或 409 `stale_cursor`；重新鉴权，不返回页数据。 |
| N-28 | 达到文件/字节/时间预算，但已命中部分列表记录 | 200 可给部分摘要，scan.complete=false、next_cursor=null；UI 明示“不完整”，不能称空库。 |
| N-29 | detail/ref 在预算耗尽前无法完成唯一性判断 | 503 `diagnostics_scan_incomplete`；不得返回 404，也不得把超时当死亡。 |
| N-30 | 同一 ref 出现两条不一致记录 | 409 `log_ref_conflict`；不按先到先得。 |
| N-31 | 完整扫描后 ref 不存在，且只有 segment tombstone | 404 `log_not_found`，文案仅为“可能过期/未写入/不在范围”；不得返回 410。 |
| N-32 | 未来无逐 ref 删除证据却请求“已过期”状态 | 不能生成 410；只有权威索引实现后才单独测 410。 |
| N-33 | malformed JSON、非 dict 行、读取失败 | 计数并 scan.complete=false；不静默当成无异常，不暴露内部路径/异常。 |
| N-34 | 宿主/来源不可达，服务端本地默认根恰有同 ref | 不得回退扫描；503 `diagnostics_unavailable`，杜绝跨来源串日志。 |
| N-35 | 日志写入降级、公开错误无 ref | UI 显示“可能未写入”，不伪造 ref、不推断无异常。 |
| N-36 | 列表已达到 limit 但未触扫描预算 | limit 本身不令 scan.truncated=true；完整候选下可正常给 next_cursor。 |
| N-37 | 后续cursor请求重算默认当前时间或省略首页规范化过滤 | 422 invalid_cursor；只有重放固定query才可继续。 |
| N-38 | 两页间追加/轮换/删除/替换/截短segment，或清单在扫描中改变 | 已有cursor一律409 stale_cursor；首页不能一致读取则complete=false且无cursor，不把剩余文件完整扫描当原快照完整。 |
| N-39 | UNC、/srv、/mnt、/data路径出现在message/type/file_name/function/原因链 | 所有自由文本二次净化或拒绝；不能只检查主异常message或常见POSIX前缀。 |
| N-40 | 按精确ref查询超过24小时的info且exception=null记录 | 不应用默认时间/severity；完整唯一命中200，详情无异常堆栈，不生成假异常。 |
| N-41 | detail=true、重复单值参数或游标未签名/被改排序键 | 422；不使用未验证游标驱动扫描或跳页。 |
| N-42 | 游标过期、服务重启或来源配置版本变化 | 409 stale_cursor；重新第一页，不拼旧新来源。 |
| N-43 | manager日志member=unknown而extra提到当前角色 | 不回填角色归属或混入角色日志；当前本地维护者仍可查manager run。 |


## 6. 健康语义反向断言

| ID | 输入 | 禁止结论与必须结论 |
| --- | --- | --- |
| H-01 | ownership_held=true，无宿主心跳 | 禁止“进程 alive”；必须“归属未释放/宿主当前状态未知”。 |
| H-02 | 实例 idle 且心跳新鲜，queue_started 较旧 | 禁止“可接单/worker healthy”；接单循环仍未知。 |
| H-03 | 实例 last_seen_at 超过 90 秒 | 禁止“已死亡”；必须“运行状态待核实”，owner/启停不变。 |
| H-04 | queue_worker_exception 后有后续事件 | 禁止仅凭异常称循环死亡；显示历史异常和后续各自时间。 |
| H-05 | queue_started 后无任何新事件 | 禁止“正在健康轮询”；显示“当前接单循环：未知”。 |
| H-06 | 从未出现 task_claimed | 禁止“不可接单”；只显示当前范围无领取记录/能力未验证。 |
| H-07 | 历史 task_claimed 成功 | 禁止“当前领取能力正常”；只显示历史领取证据。 |
| H-08 | 日志查询超时/来源离线 | 禁止推断进程死亡、无异常或无日志；显示来源/扫描不确定。 |
| H-09 | 任务queued，缺预检起止；后来领取时间已知 | 禁止“尚未工作”或将排队总时长当模型耗时；预检为未知，只有实际关联阶段事件才显示预检中，不伪写running。 |

## 7. 真实验收步骤（仅未来实现通过后）

1. Codex 先独立核对实际 diff、公共文件冲突和两个端点未改变既有 API/schema，再运行隔离矩阵；执行者自测不称独立复核。
2. 在同机受支持拓扑用隔离服务做一次 human 摘要/详情和 Agent 403；若有多宿主声明，再逐宿主验证旧实例和离线降级，不能用同机结果外推。
3. 页面自动化只覆盖 DOM/VM 时，明确记录未覆盖视觉、焦点、键盘和真实网络；不得以静态 HTML 示意冒充上线。
4. 正式发布后由项目管理者 Ctrl+F5：角色 -> 选角色 -> 运行诊断 -> 查看运行日志 -> 筛选历史实例 -> 按 ref 查详情；确认默认无堆栈、详情显式、所有中文状态准确。
5. 项目管理者再用 Agent 账号确认无权限，并核对角色启动/关闭/owner/ready 未变化；真实启停和模型能力不属于本日志验收，不为此额外操作。
6. 分别记录静态核对、隔离实现、真实 Browser、人验和未覆盖项；全根容量治理、queue heartbeat、宿主独立心跳和主动领取能力另片验收。

## 8. 本次本地方案自检记录（非产品入口）

本次运行（脚本位于本工作区的忽略证据目录，非产品或新克隆仓库的正式入口）：

```bash
python .tmp/runtime-logging-parallel-1/independent-review/273/corrected/check_design.py
```

预期只读冻结源码和本目录 fixture，验证：

- 公开样例字段白名单、默认摘要无详情、扫描不完整无下一页；
- 纯数据投影丢弃 extra/argv/env/config/token，绝对帧路径只保留 file_name；
- 设计包含 human/agent、旧 ref、过期未知、符号链接、健康未知和宿主边界；
- `source-locations.json` 中每个冻结来源的 SHA-256 与 baseline manifest 一致；
- 验收 ID 唯一且覆盖权限、路径、预算、健康四组。

结果以 `evidence/static-check-results.json` 为准。该检查不执行 FastAPI、产品 JS、真实浏览器或真实宿主，不是独立复核。
