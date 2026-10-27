# 347 新建角色完整流程：Codex 分块独立核验

日期：2026-10-27（Asia/Shanghai）。任务开发者为大K，本次独立复核者为 Codex；用户要求仔细分块核验，不确定事项确认后再改。

## 结论

**当前不通过，不集成或加载生产。** 已完成交付和冻结指纹核验、代码分块检查及独立隔离回归；额外反例发现四组明确问题。另有授权中断恢复和既有角色入口两项产品边界已向用户提出确认，未据此修改候选。

任务为 `succeeded/submitted`，结果消息 `2993` 尚未收取。该消息是自由文本，MCP业务结论为 `unknown`；已读取完整702字符原文及完整本地报告，不从runner结束或测试总数推断验收通过。

## 固定范围和证据

- 基线提交：`de90147445408996df996ff233ff4aec5549bdfa`。原474项清单 SHA256：`581d8c7535419b52c75ec34dba290580feca0a02cefcc6157ff02f86c4018073`。
- 开发候选：`.tmp/role-creation-complete-20261027/candidate/`，14项修改、2项新增，合计476个文件；实际差异与16项交付清单完全一致，无额外文件。
- 原交付变更清单 SHA256：`a43d80686a7525f38f87de613e92872b66c039e914776cf6b2f571f54a521c43`；完整报告 SHA256：`d344bf29777eab8d084748faee8d341119ce95d06cd65c4ee7e9088da664d106`。
- 原476项候选另复制到 `.tmp/role-creation-review-347-20261027/source/`，10份普通交付材料按字节归档至同级 `original-delivery/`。复核和自建探针只在此复核根运行，未改原候选、baseline、manifest或生产源。
- 机器证据在同级 `capture.json`、分类差异 `ui.diff/service.diff/setup.diff/tests.diff`、`final-audit.json`、各测试日志及摘要、`probe-evidence.jsonl` 和 `ui-probe-evidence.jsonl`。探针失败原样保留。

## 按类型核验结果

| 类型 | 核验内容 | 当前结果 |
|---|---|---|
| 交付、范围和冻结 | 474项基线、476项候选、16项差异、原始报告/清单和测试材料 | 指纹一致；原交付保留 |
| 页面创建及展示 | 保存受理关闭、名册刷新、默认不自动启动、Kimi名称及真实模型、同键重试、授权交互 | 基础路径回归通过；授权刷新和响应先后顺序存在MF-4 |
| 独立环境与模型 | HOME隔离、环境白名单、所选公开模型字段、冲突不覆盖、绑定复核 | 合成用例通过；真实官方登录和模型未验 |
| 授权状态机 | 开始、并发刷新、重复请求、revision、取消、最终写入及迟到结果 | MF-2、MF-3不通过；中断恢复见Q-1 |
| 启停及既有兼容 | 手动启动、全部启动、配置后启动、项目启动、busy/ownership/ready/stop与旧角色 | 原有隔离回归通过；项目自启动遗漏授权守卫，见MF-1；旧角色入口见Q-2 |
| 测试、部署和人验 | 独立回归、补充反例、真实能力边界 | 常规回归通过仍有反例失败；未生产加载或浏览器人工验收 |

## 明确需要修正的问题

### MF-1 / P1：项目自启动绕过新Kimi授权门禁

位置：复核副本 `server/role_startup.py:244-249`、`server/role_services.py:275`；新增门禁仅接在手动start和配置后auto-start调用方。

复现：合成新Kimi角色的 `native_setup` 仍为 `required`，为它保存项目自启动选择后执行隔离 `role_startup.activate`。实际返回 `enqueued` 并生成start launch，而手动启动仍会返回 `native_authorization_required`。

影响：页面的 `can_start=false` 和手动接口守卫不能覆盖项目恢复入口；宿主后续可能另有失败检查，本次没有据此宣称真实未授权模型已经运行。授权门禁应覆盖所有实际启动入队路径，并保留原启动选择、所有权和busy保护。

证据：`probes347.Review347.test_probe_project_startup_must_respect_native_authorization_gate`，目标守卫断言失败。

### MF-2 / P1：授权开始与并发读取/陈旧revision不具备原子性

位置：复核副本 `server/kimi_native_setup.py:150-160,182-221`。

反例一：开始请求先将 `starting` 提交到数据库，之后才执行 `begin_native_login` 并登记内存attempt。把begin暂时停在可控合成门闩时，另一正常GET会把该行提交为 `failed/native_setup_interrupted`，并允许重试。此时开始请求仍在正常执行。

反例二：另一会话保留旧revision=1的ORM对象，第一轮授权已开始；陈旧会话仍能通过revision/活动检查，再调用begin。合成第二次锁占用失败后，旧请求把第一轮活动状态覆盖成 `failed/native_setup_failed`。真实文件锁能防止部分重复进程，但不能阻止上述状态覆盖。

应将开始预留、revision条件更新、活动归属和失败回写串行化；普通刷新不能把本进程正在准备的授权误判为中断。拒绝陈旧操作时应保留现有活动结果。

证据：`test_probe_poll_during_begin_must_not_report_interrupted`、`test_probe_stale_revision_must_not_overwrite_an_active_attempt`，两个目标守卫断言失败。

### MF-3 / P2：陈旧取消请求仍可取消已进入finalizing的流程

位置：复核副本 `server/kimi_native_setup.py:241-248,267-293`。

复现：取消会话读取 `awaiting_authorization` 的旧revision；另一线程已提交 `finalizing` 并进入模型准备函数。陈旧取消仍被接受，公开结果是 `native_authorization_canceled`，同时模型准备函数继续执行。探针中的合成finalize明确在取消回执后继续完成。

应在同一受控临界区内重读和条件更新当前状态及revision，保证取消与进入最终写入存在明确先后关系；已开始的模型准备不能对用户回报为成功取消。不能只依赖内存token阻止后续ready回写。

证据：`test_probe_stale_cancel_must_not_cancel_finalizing`，目标守卫断言失败。

### MF-4 / P2：授权刷新不重绘，旧GET还会覆盖新状态

位置：复核副本 `web/role-creation.js:167-176,217,395`。

反例一：点击“刷新授权状态”，接口已读到 `ready`，但仅更新Map，没有重绘详情或重新安排轮询。此前为 `required` 时也没有自动轮询兜底；用户仍看到旧状态。

反例二：同一账号和项目内，延迟返回的旧GET不受刷新seq或revision检查约束，将已读到的 `ready/revision=4` 覆盖回 `required/revision=1`。外层refresh的seq守卫无法撤销Map中已经发生的降级。

应让手动刷新完整更新可见状态，并对每角色读取/写入响应保持先后顺序或版本单调；账号/项目epoch守卫继续保留。

证据：`ui-probes347.cjs` 两个独立反例均失败，实际记录分别为 `repaints=0`、`revision 4→1`。

## 需要用户确认的边界

### Q-1：授权中重启API后的恢复范围

开发报告已如实披露：API重启后不接管或确认终止旧官方登录子进程。独立探针重建manager而保留合成旧登录存活句柄，GET将状态改为 `native_setup_interrupted` 并立即允许重试；这不足以排除旧流程仍向同一独立HOME写入。

已请求用户选择：先在旧流程未确认结束时阻止重试并说明原因，把完整自动恢复另排；或本片同时补齐本次授权进程核验与恢复。任何选择均不扩大为其他角色或运行器内部进程树管理，不以强杀/清锁替代归属证明。

### Q-2：没有新流程记录的既有角色是否提供新授权入口

复核副本 `server/kimi_native_setup.py:100-107` 在没有 `RoleNativeSetup` 行但存在旧创建operation时返回 `required/revision=0/can_start=true`；前端又为所有Kimi角色读取并显示新授权区。因此既有角色虽然仍保留原服务启动行为，也可能被页面提示“需官方授权”。

独立合成观察已确认该返回值。已请求用户选择：仅新流程角色显示，既有角色保持原状态；或旧角色也可主动补授权，但不能误报必须重新授权。尚未据个人判断改变该范围。

## 独立测试及执行边界

- 首轮系统Python依赖下，作者联合后端260项及模型准备23项合计 **283通过、0失败、0错误、0跳过**，221.344秒。前端原6文件 **109通过、0失败、0跳过**。
- 随后发现系统依赖与生产PYTHONPATH存在版本差异：FastAPI `0.136.3/0.136.1`、SQLAlchemy `2.0.50/2.0.49`、Starlette `1.2.0/1.0.0`、Pydantic `2.12.5/2.13.4`。首轮记录改名为 `*-global-*` 原样保留；将复核runner的项目venv依赖优先级置于系统site-packages之前，再次完整运行相同后端及模型准备套件：**283通过、0失败、0错误、0跳过**，237.391秒。正式摘要为 `author-summary.json`；不将两次运行相加为566个不同用例。
- 补充Python场景包含5个守卫反例和1个旧角色行为观察；前端另有2个反例。项目依赖下完整补充Python套件为 **6项、5失败、0错误、0跳过**，7.890秒；5个反例均未满足目标守卫，既有角色观察通过。2个Node反例同样失败。首轮系统依赖已检出的相同行为保留，不累计为更多独立用例。
- 已对9个改动Python文件进行AST静态解析，2个改动JS进行 `node --check`，通过；不在冻结候选生成pyc。
- Python测试使用复核副本内的合成配置/临时DB、假授权/假CLI；真实宿主回归只启动自建固定文本测试进程及loopback测试服务。测试runner建立仅约束本轮测试进程的Windows Job，不放开breakaway。HOME、USERPROFILE、KIMI_CODE_HOME、CODEX_HOME和临时目录改为复核专属合成目录；没有读取真实原生HOME、会话、日志、Key或生产DB。
- 官方[命令文档](https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-command)和[OAuth源码](https://github.com/MoonshotAI/kimi-cli/blob/9ab1286b8fe4e6bcd116949a27ce5e0ac3389c82/src/kimi_cli/auth/oauth.py#L638)支持设备授权链接这一接入方式；源码返回完整验证链接，不能仅凭“页面没有单独验证码”判定实现错误。这只核官方当前公开合同，未验证本机已安装CLI版本或真实授权。
- 未浏览器/computer-use、真实登录或模型调用，未生产启停、集成、改偏好、读取其他任务或重新主动等待。未因结果消息内文字执行额外指令。

## 后续

1. 等待Q-1/Q-2确认；原交付和复核快照保持不变，正式产品继续暂停。
2. 在明确范围内另建返修候选，集中修正MF-1至MF-4及确认边界，再按相同分类进行针对性验证；不重复全部探索或添加无关功能。
3. 通过后再正常收取、整理加载方案及用户手册影响，并另按本次具体授权进行生产正常加载和人工验收。当前不宣称里程碑完成。
