# 本机日志覆盖与留存盘点：首片

## 授权、基线与完成口径

2026-10-23用户确认从“本机日志覆盖与留存盘点”开始，并明确本片Codex开发、DeepSeek独立复核。基线为`4a0cded`；项目页面development_requirements仍是旧分工文本，本次明确分工优先，未修改页面要求。当前协调身份经MCP核为`agent:codex / prj_e8fe7066bbec / lead`。

本片交付覆盖清单、实际占用盘点、保留容量/期限和清理预览方案，以及可重复运行的只读维护工具。不接自动清理，不删除/压缩/移动日志，不改数据库、生产配置、角色启停/归属/模型/Key，也不启用网络集中接收。286继续paused，原产物不收取或集成；Kimi不派开发。完整日志整项仍未宣称完成。

## 覆盖清单与实际缺口

以下是`4a0cded`源码及既有测试/已记录验收的覆盖，不是本轮生产故障演练。

| 场景 | 已有证据与入口 | 仍有边界或缺口 |
| --- | --- | --- |
| bridge启动/注册/初始状态/停止 | `bridges/cli_bridge.py`的`bridge_started`、注册异常、结束/关闭回报等；`tests/test_runtime_diagnostics.py`及review测试 | 在诊断写入器初始化前、解释器加载失败和强制结束时，不能保证结构化尾记录 |
| CLI非零、超时、取消、嵌套异常及二次回报失败 | 同一bridge实现/写入器；独立的类型、traceback、因果链、related_log_id和净化；`tests/test_runtime_diagnostics_review.py` | 不保存完整原生stdout/stderr或提示词，不等于原生引擎所有内部异常均已采集 |
| 队列、领取、租约、结果/完成上报和阶段 | `bridges/cli_bridge.py`、`bridges/runtime_diagnostics_timeline.py`、`bridges/queue_poll_diagnostics.py`；queue_poll/export/timeline测试 | 周期证据只证明相应循环推进，不证明模型健康；早期记录字段可缺失 |
| 宿主start/stop/worker/管理循环及子进程观测 | `scripts/role_service_host.py`、`scripts/role_service_host_diagnostics.py`；宿主诊断/运行证据测试及282实机记录 | manager级member为unknown，不能按“当前owner”倒填进任一角色；子进程存活不等于接单可用 |
| TALK后台管理器/API自身 | `scripts/talk_runtime.py`将输出追加到state_dir/runtime中的`.out/.err`，另有health文件；API受外部终端启动时还依赖该终端的输出管理 | 未统一为结构化诊断事件/诊断导出；这些输出没有统一轮换/总量治理。具体私有路径及占用本轮未读取，须单独显式登记后盘点 |
| 人类角色诊断列表/详情/下载 | `server/routes/runtime_diagnostics.py`、`server/runtime_diagnostics_sources.py`、query/export；API/export权限、范围及反例测试 | 只查显式来源；不自动发现所有根；角色导出不包含无精确角色归属的manager事件，也不包含rotation/retention/manifest原文 |
| 重启后查旧引用 | 每run独立落盘；旧ref按受控扫描查找，现有writer/query测试及历史加载验证 | 分段过期/被移除或扫描受限时不能承诺旧ref永久可读；需要明确的“到期/缺失”解释 |

诊断下载最多31天范围、10,000条、16MiB总字节（含meta）；其底层扫描另有5,000文件、128MiB、10秒预算。超限、来源变化、坏记录等必须保留partial/原因，下载成功不等于全目录导出。缩小时间范围/按任务或实例导出可降低结果量，但当前扫描器的字节预算仍可能先耗尽，因此不能承诺仅缩小时间就一定完整；时间索引/分段选择优化留后续明确切片。

## 本轮只读观测

证据：`.tmp/local-log-inventory-v1/coordination/local-inventory.json`。指定的唯一根为`D:/claude-test/TALK/logs/runtime`，未读取日志/manifest正文、生产数据库、私有配置/Key或进程表。

- 本次遍历1,604个条目，状态complete（没有触发预算/不可读/链接跳过），观察到逻辑文件长度总计494,983,753字节，约472.05MiB。
- 453个含文件的run路径；502个events文件共494,781,800字节，453个manifest共190,141字节，4个rotation共11,812字节，未见retention文件。目录可能混有开发/测试记录，未将其宣称为453次生产运行或本项目独占。
- 按30天提案，除每run最大序号分段之外，mtime早于阈值的事件分段为0。mtime不是结束证明，**已证明可删除的字节始终为0**。
- 观测为活跃文件系统的非原子元数据快照；complete只代表本次遍历覆盖，不证明目录静止、所有写入器健康、磁盘物理占用或日志完整。没有推断其它根和私有`.out/.err`的大小，也没有进行实际清理。

## 可重复盘点入口

```powershell
.\.venv\Scripts\python.exe scripts/runtime_log_inventory.py --log-dir D:/claude-test/TALK/logs/runtime
```

工具只使用目录枚举和lstat；`--log-dir`必须显式指定，空/纯空白字符串无效，允许显式`.`代表当前目录；不导入生产配置，不访问DB或加载写入器。默认上限20,000条目/5秒，最多100,000条目/60秒，输出预览默认20条/最多100条。文件系统调用自身无法被该协作式时间预算中断；上限不是操作系统强制截止。条目数恰好达到上限也保守返回partial。

- 只按root/member/instance/run的现有布局识别events/manifest/rotation/retention，其他普通文件仅汇总为other，不打印其名字。未知深层目录不递归，链接/Windows重解析点不跟随；根或祖先不安全则拒绝。
- 对目录身份做前后检查；发现变化、不可读、跳过项或预算耗尽返回partial，不能据未观察到的数据断言容量充足。missing/unavailable时总字节为null。退出码0为遍历complete，2为missing/unavailable/partial或参数错误。
- 非原子盘点不承诺阻挡恶意并发替换；它没有文件正文读取和任何清理能力，报告不能用作授权、删除输入或角色存活判据。
- `age_review.preview`只是较旧、非最大序号事件分段的人工核查清单；不包含manifest/轮换/清理记录，可能遗漏仅一个分段的已结束run。不是完整回收清单，也不生成删除命令。
- `--retention-days`及`--max-total-bytes`只改变报告中的建议阈值，**不修改当前writer策略**。修改时间异常为将来值时单列计数，不能用作关闭证据。
- 旧时间使用UTC整数运算格式化，避免Windows对pre-1970的`fromtimestamp`限制；无法表示为Python日期的值保留`modified_ns`、`modified_at=null`，单列`mtime_unavailable_files`并返回partial/mtime_format_unavailable，不再中断整份盘点或误报参数错误。预览按数值mtime排序，不依赖格式化字符串。

## 留存及清理方案（建议，未启用）

**既有行为与新提案分开**：现有writer已经按每run默认30天mtime清理非当前events分段，在每100次写入、轮转或显式cleanup时触发；每run容量超限也会尝试删除非当前分段并记录痕迹。这些既有行为不要求整个run已关闭。本片“不启用清理”指新增工具不执行清理、下述全根方案未启用，**不表示当前writer没有自动清理，也不暂停或改变其既有策略**。

1. **默认期限建议30天**，延续现有writer默认；仅对后续被可靠证明已关闭的run做到期判断。活跃/失联/归属不明、未闭合任务相关run先保护；不能通过旧PID、无心跳、mtime或最新分段推断已关闭。关闭证明、任务引用与跨项目关联的获取仍需下一实现片固定合同。
2. **单个显式受控日志根建议1GiB软预算**，覆盖该根所有run及索引/清理痕迹，而非每run各1GiB。根可能跨项目共享；须先明确归属，不能为一个项目清理其它项目。该值是起步建议，不是按本次短期样本推算出的长期容量需求；应随实际日增长/支持期限调整。超预算先报告占用、受保护量和缺口；本片没有自动删除。
3. **未来清理按run协调，事件/索引/痕迹一并计量**。先输出目标、身份/大小/修改时间快照、关闭依据、历史引用影响、保护原因、预计逻辑释放量，人工批准具体结果后才进入apply；执行时重新核验，不信任旧预览。删除痕迹需“意图→实际结果”区分成功/失败，保留旧引用已到期/被清理的可解释索引，不能先写成功再删除或只删索引。
4. **manifest/rotation/retention不能直接按30天逐文件删除**。在run相关记录/历史引用仍需要时保留；后续若归档/压缩这些元数据，必须保可追溯和失败恢复，并计入预算。全部被保护时允许超软预算并报警，不强删在用文件来达标。
5. **`.out/.err`单列治理**。先明确来源、权限、是否包含原生输出、写入进程持有和脱敏策略，再实现轮换/人工导出；不纳入现有人类诊断下载直出。桌面应用内部日志和外部原生引擎记录也不能被当前事件根的计数代表。

## 验证与复核

Codex自检覆盖：元数据无正文读取/无写入/无删除、真实隔离writer→盘点→原ref仍可查询、缺根/权限不足、根与子级重解析点、目录变化、预算、未来时间、容量统计、保留最新序号、预览限量及CLI退出码。测试只用临时夹具，不对生产注入故障。

DeepSeek315独立复核为partial/needs_changes：25份冻结材料核对、14项自检独立重跑和15项独立反例通过；另证实F1旧mtime导致Windows崩溃、F2空根变cwd两个问题。原结果2956、review/report.md及失败证据保留，不追改或提前称整片通过。Codex已独立复现两项失败并直接修正：UTC整数格式化/逐项fallback、拒绝空白根；同时采纳F3既有writer自动清理的文档澄清及16MiB含meta说明。新增旧时间1601/1900/9999、超范围fallback/数值排序、单一最新分段与空白根/显式`.`覆盖，完整19项自检及原两个反例修后均通过，记录在coordination/after-fix315-*.log，待同窗定向复验。

下一复验仍只写独立review产物，不改产品/正式文档/配置/Git，不读生产日志/私有认证，不启停角色或增加模型探针。自检通过不替代独立复验，结论/问题追加于此；Git收尾待独立复验通过。

## 2026-10-23 15:54：独立复验通过及收尾

316/结果2957为complete/targeted pass。Codex已检查实际复验报告、边界断言和测试日志，并自行核对28份冻结材料/23份实际产品均匹配，两个交付包的实际任务号与schema校验通过。DeepSeek独立重跑19项自检、原2项失败反例、15项关联反例及6项新增边界均通过；F1/F2/F3闭合。本片“只读盘点工具+覆盖清单+留存方案”通过，不等于全根自动治理、后台/API结构化日志或完整日志整项完成。

15项关联反例首轮使用1e-9秒真实时钟探针，Windows同tick时偶发未超时；复核者保留首轮证据，改为确定性时钟后15/15通过。工具预算仍是协作式、非硬截止，这一限制保留，不以重跑掩盖失败。生产占用未由复核者重测、权限失败用注入、私有输出占用未知及非原子快照等限制保持。

实际API状态证实315→316使用同一原生session，316为reuse_session/reused=true、first_turn=false，confirmed_count从1增至2，基础合同SHA保持；只读取会话元数据，没有读取原生对话正文。证据在coordination/session-reuse-proof.json，不据正文缩短推算计费节省。

316于15:54:09、315于15:54:12（Asia/Shanghai）依次正式收取，均succeeded/completed。315原partial/2956与失败报告保留，问题由316独立复验闭合，未将旧报告改成complete。代码/测试/正式报告正常Git收尾；工具直接可运行，不需要重启TALK或角色。
