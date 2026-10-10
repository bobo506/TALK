# 适配收尾登记实施计划（C1–C4）

2026-10-10：依据 ADAPTER_BINDING_CLOSEOUT_DESIGN.md。#203–#205最终设计已复核收取；#206 C1离线实现、#207→#208→#209 C2受信应用工具已独立复核收取。C3真实来源接线/受权登记与C4页面验收待后续，真实登记尚未实施。B1a/B1b/B3/B4现有代码和权限保持；当前先完成角色绑定收尾，不切其它功能。

## 1. C1：离线事实模块

当前已通过：DeepSeek交付、Codex独立审查发现三组问题，按用户“你先自己修吧”定向修复；98项新模块测试与59项K28、15项runner、40项角色绑定回归共212项，零失败/跳过。冻结原代码的14项针对测试命中22处失败断言；独立16组边界探针原码10失败、修后全通过。原交付、自报与失败证据保持，最终修复为Codex自测/定向复验，不声称另一个Agent审查了Codex改动。详细记录见进度历史及本机 `.tmp/adapter-binding-facts-c1-review/`。

只新增 scripts/adapter_binding_facts.py、tests/test_adapter_binding_facts.py；正式源码/测试不得导入 .tmp 探针或依赖忽略文件。可参考思路，实际行为测试必须调用新模块。

模块接受内存配置对象和显式上下文，复用 server.models schema/归一化与 kimi_k28_executor.native_model_binding。C1不调用 load_native_config 找真实文件，不读环境/Key，不访问网络/DB，不写文件或启动进程；真实配置加载由C3显式入口负责。导入不得初始化服务或调用主程序。

建议接口（允许必要内部函数）：

- RUNNER_CREATE_FIELDS/RUNNER_UPDATE_FIELDS/BINDING_WRITE_FIELDS 从 model_fields 派生。
- runner_id_for(runtime, *, host_scope, workspace_scope=None, host_shared_runner=False, multi_workspace_on_host=False, ledger=None)：严格scope/布尔类型、规范摘要ID、只读ledger。
- is_opaque_connection_ref(value)。
- native_provenance_for(config, *, origin, confirmed=False) / native_default_alias(config, *, provenance=None)：仅内存核验，不因调用自动confirmed。
- read_alias_facts(config, alias) / resolve_model_selection(*, config, explicit_argv_alias, declared, hard, native_provenance=None, required_hard_fields=())。
- sanitize_sources(sources) / public_config_identity(...) / source_fingerprint(...)：正式合同§5公开投影与安全错误。
- build_entry(*, adapter, member_id, project_id, runner_fields, binding_fields, sources, source_context=None)：schema、runner关联、连接收窄；source_context必须包含完整ready选择结果并闭合绑定六字段/alias/来源投影，无结果不得ready；ready公开白名单、blocked不回候选。
- adapter_profile(name)：不可变profile含runtime/显式alias/hard/required_hard_fields，scope调用方显式传入；K28同源常量，K3独立，DSH/Codex来源不足blocked。

正式发布澄清优先于205参考探针：确切scope载荷、仅公开投影导出指纹、内部provenance与公开摘要分开、confirmed默认不自动成立、C1只接收配置对象。不能照搬草稿中与离线范围矛盾的文件读取要求。

| 测试组 | 必要行为 |
|---|---|
| 选择 | argv优先；confirmed default正例；无/未核/过期provenance阻断；缺alias/条目/解析失败安全返回 |
| 硬契约 | 相同backend不同固定alias拒绝；硬字段缺失/provider/model/声明冲突拒绝；泛用K3正例 |
| schema | 原错误类型/非法枚举/空白/超长/extra/重复capabilities/可疑凭据；runner/binding ID不同、选择结果与载荷/投影冲突拒绝 |
| scope | 跨host/workspace/拼接歧义不同；重复/发现标志/多模型稳定；不依赖ledger；长度64；互斥/坏值/非布尔拒绝 |
| 连接 | 合法不透明正例、路径/可执行后缀负例 |
| 隐私 | 合成canary在alias/provider/model/声明/来源/解析错误及native/runner能力；递归检查ready/blocked/sources/指纹/错误无原值；未知嵌套丢弃 |
| 指纹 | 稳定及公开事实/来源/alias/scope漂移；仅改凭据配置不改公开投影；不导出整config |
| profiles | K28直接引用常量；K3独立；DSH/Codex缺来源blocked |
| 导入/隔离 | 无文件/环境/网络/DB/模型/进程副作用，干净检出不依赖.tmp |

新 unittest全绿0skip，涉及的既有K28回归、语法/UTF-8、git diff --check；准确记录命令/退出码/计数/限制。不为旧全量失败扩大范围。C1完成不代表任何角色已绑定。

## 2. C2：受信应用CLI/helper

已实现并复核通过：仅新增 `scripts/talk_adapter_registry.py` 与 `tests/test_talk_adapter_registry.py`；#207初稿由#208修正五项问题，#209闭合409方法边界，三项已按209→208→207收取。原失败、自报和冻结源码保留，不改写初稿验收结论。

- helper 提供 `build_plan` / `plan_spec` / `apply_plan` / `verify_plan`；CLI 提供 `plan --spec --out`、`apply --plan --spec`、`verify --plan`。凭据显式选 `--key-env` 或仓库外 `--key-file`，无隐式来源或明文 Key 参数；apply 必须反查 human 身份。
- plan/verify 只读，apply 重核服务/目标、资格、schema、来源指纹和显式接受差异；来源清单自带 ready/指纹不采信。当前传入内存事实不代表真实 native 已生效，C3负责有效来源与覆盖层确认。
- 登记写后完整 `RunnerOut` 校验（含日期）、目标/runtime/retired/四个可变字段重判；绑定核 project/member、七字段及合法 `binding_state=bound`。部分成功保留恢复索引，零盲写重试。
- 仅 POST409 同事实重分类可继续绑定；PATCH/PUT409或其它明确写失败即使最新GET一致也保留失败，PATCH失败的本条PUT为0。写结果与观察事实分开。
- 未知状态和plan元数据严格白名单；CLI参数/IO/坏JSON错误不回显敏感候选；`accept_change` 必须严格bool，字符串 `"false"` 不授权变更。

Codex本轮独立运行C2完整153项，0失败/错误/跳过；原22边界与3方法409探针共25/25通过。前轮独立98 C1＋15 runner＋40项目绑定＋59 K28共212项通过、0跳过，804旧保护文件逐SHA未变，本轮不重复计为新跑。夹具挂真实router、TestClient与内存SQLite，正式代码/测试不依赖 `.tmp/`。完整证据本机 `.tmp/adapter-registry-c2-method-fix-review/`；未执行生产登记、真实Key/native读取或宿主长等待，无CAS竞争窗口保留。

## 3. C3：明确收尾接线与真实验收

共享 adapter_closeout.py::run_closeout 加K28显式closeout子命令，届时任务明确文件范围。显式加载native有效来源，核选择/覆盖层/scope，先输出可审阅补登记dry-run与离线接线证据；真实应用再交人类确认，由human凭据受权进程执行。

读回、恢复、原profile/Key/名册/旧快照保护留证。至少一条真实链路bound后才能说绑定完成；其它来源不足blocked。不得挂launch/心跳/claim或首次自动注册。

## 4. C4：必要页面指引和同一功能收尾

保留只读字段，补适配收尾指引/诚实未配置说明；多链路选择交互需明确需求。页面由执行/复核者提供证据，用户验收，Codex默认不浏览器操作。

最终交付启动/收尾入口、验收步骤、外置凭据取得方式、完成/限制；当前功能完成后再排I-4/B2/B5。

## 5. 交付与暂停

执行者完成一片暂停，完整talk-delivery-1 JSON使用本次实际号作为结果消息正文，不加前置说明；包含基线、实际差异、测试日志、完成/未完成/blocked、限制与进度草稿。Codex独立核代码/证据、正式进度和Git收尾，默认派发结束，用户通知完成后取件。
