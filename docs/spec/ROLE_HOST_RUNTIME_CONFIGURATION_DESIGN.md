# 受管宿主运行器模板与执行预算：产品片B实施合同

状态：2026-10-17 08:45，260已派DeepSeek首次实施产品片B，Codex交付后复核并直接修正；259产品片A已发布ea21d81。用户确认继续5角色平移，当前宿主配置能力尚未验收/部署，未执行真实角色迁移。

## 范围与分工

DeepSeek只首次实现、自测和交付后暂停；Codex独立复核，有问题直接修正、针对性验证与Git/docs收尾，不往返派修。本片仅scripts/role_service_host.py及对应测试，不改bridge全局默认、旧手动入口、服务端API/DB、前端或真实部署配置。完整日志、删除、原生认证与5角色实际登记/启停另片。角色ID/Key/模型/绑定/身份档/历史保持，unknown/unverified及owner/stop守卫不放开。

## 运行器命令模板

1. 新增可重复 `--runtime-command-template RUNTIME TEMPLATE`（argparse action=append/nargs=2），使用新参数，不重载旧flag语法。HostManager接收对应runtime→template映射。RUNTIME只接受当前需要command_flag的codex/dsh/cli；未知、空白、kimi-code这类不使用command_flag的运行器或空模板稳定拒绝。
2. 同runtime同模板重复可去重；同runtime不同模板稳定拒绝runtime_template_conflict，禁止后值静默覆盖。显式模板必须包含字面量{model}；不合格模板不能回退全局。校验规则由CLI与程序化构造共享，构造时复制配置，避免外部dict修改影响已构造manager。
3. 选择优先级：该runtime显式模板 > 旧--cli-command-template全局回退 > 既有缺模板错误。旧全局参数保持单字符串语义及现有错误路径；没有新增参数的旧调用继续可用。kimi-code仍通过--kimi-model接精确alias，不需要模板；不得静默把codex模板用于dsh或反向混用。
4. 不执行/探测模板中的真实CLI、网络或模型；模板只是本机显式登记事实，不等于真实能力通过。不猜模型、CLI别名、原生profile或登录。alias原样接入现有配方及真实parser验证，不添加不被支持的模型flag。错误/公共结果不输出模板正文、完整argv、私有路径、凭据。

## 执行预算与显式自定义入口

1. 新增 `--cli-execution-timeout-seconds N`；内置受管配方有效默认21600秒，显式正整数可覆盖（如60、43200），不设3600或21600固定上限。程序化构造也验证；拒绝bool/零/负值/小数/NaN/Infinity及超出实际入口可表达范围的值，稳定错误且不写API/不spawn。
2. argparse未显式给该参数时保留None，用于区分默认与显式请求。内置配方路径将None解析成21600；每个真实bridge外层argv恰一个--timeout N（含kimi-code/codex/dsh/cli）。真实parser的timeout值须与该有效值相等，不受旧600默认或重复参数覆盖。
3. 预检/真实parser校验/最终Popen入参共用已构造的同一份argv与预算快照。公开宿主启动诊断仅新增有界数值/枚举（建议execution_timeout_seconds、execution_timeout_source、command_template_source），必要加入redact白名单；不得向服务端claim/report塞新协议字段，不输出命令/Key。记录/报告从预检事实读取，不能在spawn时重新取可变manager值产生前后不一致。
4. 显式--cli-executable属于既有自定义协议入口：保留旧cli_args/alias接线，不自动附加bridge专用--timeout，不宣称其被六小时管理。若同时显式给新预算参数或新per-runtime模板，稳定拒绝不支持，不能静默忽略；未给新参数时旧自定义入口继续工作，预算事实为unknown/not_applied。旧global-template+custom原兼容行为不扩改。
5. 不改变ready/stop/HTTP超时、任务租约、MCP客户端上限T、TALK读取等待W或主动等待；已运行实例不热改预算，不重启/打断在途任务。此片只闭合宿主内置配方通道，通用bridge默认600与其它旧手动入口待各自迁移，不宣称所有入口已统一六小时。

## 验证与交付

- 同一HostManager同时核codex与dsh，两套模板不串；覆盖per-runtime优先、全局回退、无模板原拒绝、重复同值/冲突、未知/不适用runtime、缺{model}、空白/带空格与Windows路径模板。CLI main接线和程序化构造都实测，别只测parse_args或独立helper。
- 所有内置配方真实parser接收默认21600与显式60/43200；从preflight.argv到最终spawn_hidden捕获参数及公开诊断数值一致、外层仅一个timeout。用假Key/假API/本人三档临时文件，禁止调用真实模型或等待六小时。
- 验自定义入口旧行为保持、新参数组合明确拒绝；非法配置先于私有凭据读取、网络写与spawn失败，公共错误不含原模板/argv/凭据；白名单不得放宽为透传任意键。
- 旧runtime-verified、身份/choice_source（含259 legacy_attach）、绑定/归档/能力、未知owner/关闭/所有权守卫回归。临时或内存SQLite先断言engine/storage隔离再建TestClient，假固定文本进程可用于原host回归；不启动真实宿主/CLI/模型。
- 原用例原始日志与本片新增证据完整落盘；保留失败记录，工具层只输出必要摘要。跑本片新增、原host及实际受影响的worker/角色相关测试，不重复无关全仓。原685自报不当本片证据。
- TALK交付为纯talk-delivery-1 JSON，自带实际任务号并先校验；代码/基线SHA、完成/未完成、测试命令与原始日志、限制和进度草稿齐备。原prepare-v1/v2/v3及各独立复核、product-attach/原证据不得覆盖。完成暂停，不开始真实迁移。

真实终端适配遵循TERMINAL_MCP的T/W/返回余量与取消/排队核验。本片不改终端配置、不启用主动等待，未知项如实待验，不能以真实parser通过冒充原生/模型/终端适配通过。
