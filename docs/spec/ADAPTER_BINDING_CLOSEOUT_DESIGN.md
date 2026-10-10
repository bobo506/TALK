# 适配收尾登记与角色绑定合同（BA-1）

2026-10-10：#203–#205 最终设计已由 Codex 独立复核通过；#206 C1 离线事实模块已通过，#207 经 #208/#209 返修的 C2 受信应用工具已独立复核并收取。C3 #210 经 #211 定向返修后，共享显式入口和真实只读申请包已独立通过并收取；用户于2026-10-10同意具体两写包后，K28受权生产登记、角色读回bound与只读verify已完成；用户已核对C3 K28已绑定/固定alias显示；C4 #212只读页面指引经Codex独立复核通过并收取，新增指引与窄屏人工验收待用户。bound仅表示配置关联有效，不证明实际后端版本或主动等待。本合同和配套实施计划是正式依据，忽略目录中的草稿/探针仅作为本机审查证据。原角色绑定合同的表、API、权限、六维绑定指纹和历史任务快照保持。

## 1. 目标与边界

用户在适配一个角色时核验运行器、模型与连接事实，受信的适配收尾入口据此登记运行器并关联项目角色；页面读取结果，避免重复人工填写同一组技术字段。来源不足时返回 blocked，补齐来源后重新 plan。

登记不首次注册成员、不同步名册、不创建凭据、不启动进程、不改变实际模型选择或启用主动等待。配置事实、实例上报与实际执行证据分别保留：配置 alias 或展示 K2.8 Preview 不能证明实际后端版本。

首期沿用 human 专用写入。DeepSeek 开发、Codex 独立复核按本次会话分工执行；每次一片，开发完成暂停，共享目录开发与复核不并行改码。

## 2. 复用现有接口和 schema

| 接口 | 实际形状与边界 |
|---|---|
| GET /api/members/me | 按本次凭据反查身份；apply 必须 kind=human |
| GET /api/runners | RunnerOut 数组，不是含 runners 的对象 |
| POST /api/runners | RunnerCreate；201/已存在409，写后重新读取 |
| PATCH /api/runners/{runner_id} | RunnerUpdate，只接受四个可修改字段 |
| GET /api/projects/{project_id}/agents | 角色数组 |
| GET /api/projects/{project_id} | ProjectOut，无 agents 键 |
| GET /api/projects/{project_id}/agents/{member_id}/binding | project_id、member_id、binding、binding_state |
| PUT 同一 binding 路径 | {"binding":RoleBindingInput}；human 写、last-write-wins、无 CAS |

字段集合从 server.models 的 model_fields 派生，校验复用已有 schema/归一化：

- RunnerCreate 六键：runner_id、runtime、display_name、adapter_status、adapter_note、capabilities。
- RunnerUpdate 四键：display_name、adapter_status、adapter_note、capabilities；ID/runtime 不可修改。
- RoleBindingInput 七键：runner_id、model_source、provider_id、connection_ref、model_id、model_alias、model_display_name。

GET binding 对 member_missing/member_disabled/not_in_roster/not_agent 仍可200，但这些状态阻止 apply。unconfigured 本身不表示目标无资格。GET 状态与 PUT 的404/422分开，不更改服务器语义。

ready 前实例化 RunnerCreate/RoleBindingInput，且 binding.runner_id 必须等于 runner.runner_id。产物由验证后的 model_dump 白名单生成；错误仅回稳定原因码、已知字段名，不回候选原值、ValidationError/解析器异常正文、配置正文或 HTTP raw body。

`build_entry` 还必须接收完整的 `resolve_model_selection` ready 结果，归一化后核对绑定六字段、选中 alias 与来源投影。缺失、blocked、不完整结果或任何冲突均阻断，不生成候选或指纹；schema 合法本身不代表来源已核。泛用 K3 不要求不存在的固定 provider/model 硬常量，仍须核选中条目及合法补充声明，不能借 K28 代填。

## 3. 稳定 scope 和标识

runtime 复用已有归一化。host_scope/workspace_scope 必须来自显式安装/适配上下文，不从 hostname、实例名、绝对路径或模型名推断。token 为去首尾空白后符合 ^[A-Za-z0-9][A-Za-z0-9._:@+~\-]{0,127}$ 的 ASCII 字符串；拒绝空、内部空白、路径、控制符、错误类型、超长。

host_scope 必填。workspace_scope 缺失仅在明确 host_shared_runner=True 时允许；二者互斥。标志严格为布尔值，缺省 workspace 以 JSON null 表示。

规范载荷：{"schema":"adapter-scope-v1","scope":[runtime,host_scope,workspace_scope]}。
规范 JSON：UTF-8、ensure_ascii=False、sort_keys=True、separators=(",",":")。
runner_id = "runner:" + runtime[:24] + "-" + sha256(规范载荷)[:32]。
完整 runtime 参与摘要；32 hex 为128位。结果还须满足原 runner_id 规则，长度≤64。

不同 host/workspace 派生不同 scope ID；同元组重复稳定。K3/K28 在相同 host/workspace/runtime 复用一个运行器，以不同 member 绑定。模型/alias 或发现状态变化不改 ID。不依赖台账、新 API；可选 ledger 只额外检查，不写入。

connection_ref 只接受 [A-Za-z0-9._-]{1,128} 不透明标识，拒绝 .exe/.cmd/.bat/.ps1/.sh 后缀；不解析为 URL、凭据路径或可执行命令。现服务端规则较宽，本 helper 收窄。

## 4. 选择顺序与来源确认

依次执行：

1. profile 要求的 hard 字段缺失即 E_SOURCE_UNAVAILABLE，不补推测值。
2. 最终显式 argv alias 优先；无显式选择才使用已确认有效来源的 native default_model。
3. hard.model_alias 存在时与最终 alias 逐字核验；相同 provider/model 不足以接受其它 alias。声明与已知事实冲突即 E_SOURCE_CONFLICT，没有 prefer_declared 覆盖开关。
4. 按选中 alias 复用 kimi_k28_executor.native_model_binding，取得对应公开元组，再核 hard 契约；声明仅补机器不可得公开字段，不能覆盖选中 alias 或已核元组。

default 确认由入口掌握有效配置、选择参数和覆盖层情况后明确提供 provenance。无标记、未核来源、摘要不匹配或覆盖层未知即 E_SOURCE_UNCONFIRMED。读取文件或创建摘要本身不证明生效。C1 只检验传入标记，不能把 fixture 自动声明为真实 confirmed；真实有效来源待 C3 验。

K28 的 explicit_model_alias/hard.model_alias 直接引用 kimi_k28_executor.MODEL_ALIAS；provider/model/connection_ref 引用现有常量；不改变 launch/build_bridge_argv 默认。泛用 K3 不继承 K28 固定 alias，其默认来源未核时 blocked。

| 角色 | 可用依据与后置项 |
|---|---|
| agent:kimi-code-k28-preview | runtime=kimi-code，固定 alias/硬常量与选中 native 条目核验；展示 K2.8 Preview，实际版本未知 |
| agent:kimi | runtime=kimi-code，自身实际选择与已确认 native 来源；不借 K28 代填 |
| agent:deepseek | runtime=dsh 已知，本片未核真实模型/连接来源，来源不足 blocked |
| agent:codex | runtime=codex 已知，本片未核真实模型/连接来源，来源不足 blocked |

来源不足 profile 可以存在，但不能产生可写绑定；不根据名称、业务角色或实例猜 builtin/custom_api/provider/model。

## 5. 白名单、隐私与漂移指纹

sources 仅保留已知公开字段名与 {"source":枚举}。枚举为 argv_explicit_selection/native_default_confirmed/native_parse/hard_contract/declared/fixture/unknown；丢弃 value 和未知/嵌套键。blocked 不输出 runner/binding 候选，不拼原 alias；ready 只展示通过 schema 的公开值。

source_fingerprint 用于 plan→apply 来源漂移检查，与原 binding_fingerprint 分开。格式 adapter-source-fingerprint-v1；算法 sha256(规范非秘密输入)[:32]。JSON 规则同§3，公开文字 NFKC+strip、大小写不折叠，alias 只以完整64 hex SHA256参与指纹输入。

输入固定为 schema、adapter、runtime、host_scope、workspace_scope、selected_alias_sha256、alias_source、config_identity={origin,content_sha256}。缺失值 null、未知来源 unknown，不能借此产生 ready。

发布澄清：config_identity.content_sha256 只对选中链路公开事实投影生成，不将整份 config/providers/凭据配置作为导出指纹输入。投影固定为：
{"schema":"adapter-public-config-v1","selected_alias_sha256":...,"default_alias_sha256":...,"native":{provider_id,model_id,model_display_name,capabilities},"hard":{model_source,provider_id,connection_ref,model_id,model_alias_sha256},"declared":{model_source,connection_ref}}。
上述 native/hard/declared 字段逐键固定，缺失为 null，存在值先经已有规则验证；capabilities 复用归一化。default_alias_sha256 仅默认来源已确认时有值，hard alias 仅放摘要；未知额外键、providers、api_key/token/密码、路径和环境变量不进入投影。

能力列表另复用 `looks_like_credential` 拒绝疑似凭据：native 事实、ready 条目中的 native/runner 能力均阻断且不回显；单独构造公开投影时非法能力置 null。此收窄只在 C1 模块执行，不改变既有服务器 schema。

相同公开事实指纹稳定；选中 alias、公开元组、hard/声明、scope 或来源变化改变指纹；仅凭据配置变化不作为本功能公开漂移结论。native provenance 匹配所需内部摘要仅在内存核验，与公开投影摘要分开，不写清单/日志。blocked 可以不生成指纹，不能为取得指纹而导出非法候选。

合成 canary 递归验证覆盖 ready/blocked/sources/指纹/错误、缺条目与解析失败，均不得回流原敏感候选。

## 6. plan / apply / verify

plan 无写：校验显式 server/project/member、来源、scope、schema，给出来源指纹、ready/blocked、预计新增/no_op/差异/冲突。部分 ready 不汇总为全部完成。

apply 先按凭据核 human，再重核服务地址和本次参数与清单一致、project/member 一致、目标资格、schema、当前来源指纹。漂移重新 plan。凭据仅本次受信进程取得，环境变量或显式仓库外 key_file 由 C2 读取，不写清单、仓库、聊天或命令行 key 参数，不创建/复制凭据。

逐条顺序：

1. 读资格与登记；不存在才 POST；runtime 不同/retired 阻断。四个可变字段全部归一化比较，相同才 no_op；差异默认冲突，明确 accept-change 后只 PATCH 四键。首次默认 unverified，不自动升级或复启 retired。
2. POST201/409/未知结果或超时、PATCH200/未知结果或超时后，均 GET /api/runners 完整重判：HTTP、数组形状、完整 schema、目标 ID、runtime、retired、四字段。写返回异常也停止并尽可能读回已观察状态；任何失败阻止本条绑定。
3. 只有 POST 登记的 409 允许按最新完整同事实重分类，不能仅查存在。PATCH/PUT 的 409 与其它明确 HTTP 失败均保留写失败；即使读回一致，也不能升级为本次写成功，PATCH 失败不得继续本条绑定 PUT。未知结果不盲重试写；读回仍不能确定时报告 unknown/失败，保留恢复索引。
4. 登记验证后最近一次 GET binding，比较七字段与 binding_state。相同且 bound 才有效 no_op；差异默认冲突，明确接受后 PUT。
5. PUT 后只读核 project/member、七字段与 bound；超时先读取，不盲重试。写结果与观察事实分别记录：明确 PUT 失败时，读回的 bound 只是观察状态，apply 不据此报告本次绑定写成功。按条目保留成功/失败/未完成，重跑只恢复需要处理条目。

## 7. 并发和调用入口

首期沿用现 API，无 CAS。单写者受信收尾、最近读差异检查与写后读回仍留下“最新读→PUT”的竞争窗口；不宣称原子防覆盖，不把本地锁当全局锁。强 CAS 或 agent 自写权限另行设计批准。

scripts/adapter_closeout.py::run_closeout 由 scripts/kimi_k28_executor.py 显式 closeout 子命令调用，未来适配入口复用。不得挂 launch、心跳、claim、MCP 初始化或后台定时执行。

入口接收已核事实与目标，先生成具体 plan/dry-run，再由已授权 human 受信应用并 verify；不绕注册、本人身份与名册门禁。设计通过本身不授权生产写；本机K28具体两写包已获用户同意并应用，后续目标仍须各自明确授权。

页面保留只读技术字段和必要收尾指引；多条已验证链路存在时再明确选择交互，首期不加重复填写技术字段的表单。C4 #212已实现随未配置/已绑定/失效/未知/旧服务状态变化的纯文本指引，复用原角色读取，不增加绑定写入、每角色请求或独立轮询。指引强调来源核验→显式plan→人类确认/受信human收尾→刷新；来源不足或未知覆盖层保持blocked，bound不扩大为运行结果证明。

## 8. 设计验收与功能完成条件

#203 原六问题与 #204 四剩余问题的原报告/失败/基线保持。#205 msg2707 合法自身号 partial，Codex核完整9237字符/三页/SHA及本地JSON一致，独立读参考实现与合同，重跑六组原问题、四组补正及额外独立四反例/正例。

开发探针重跑20个内存 harness、140进程内请求、47内存写；额外独立探针另记。设计验收生产HTTP/数据库写、真实profile/Key读取、模型、长wait与进程启动均0。协调方两次fixture错误只修review脚本并保留。205→204→203已收取归档最终设计链；原204 MCP unknown/自报/失败不追改。证据位于本机 .tmp/adapter-binding-design-final-fix-review/，正式运行与测试不得依赖该目录。

历史终端预算：DeepSeek桌面T65/W50秒、Codex用户现用W300秒；Kimi660000ms仅模板，实际T未核。本轮未验宿主T/W/取消/排队；外层工具交还预算独立。C1/C2不长等待，不把登记成功称主动等待适配通过。

按 C1→C2→C3→C4 一次一片。完成条件至少一条真实已核链路受信登记、角色读回 bound、页面入口/说明与人工验收；其它来源不足诚实 blocked，旧任务快照/凭据/native默认保持。当前功能完成后再排主被动I-4/B2/B5。当前C1–C4代码及至少一条K28真实登记/读回已通过；C3角色页已人工核对，C4新指引的最终页面人工验收尚未完成，仍在本功能门禁内。
