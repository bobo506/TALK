# 全入口默认执行时限24小时：本片合同

确认日期：2026-10-24（Asia/Shanghai）。用户明确：“不用，对这个切片功能，我们简化到当前默认写死为24个小时吧”。

当前状态：2026-10-24 17:53，326/2970已独立核验、集成并收取completed。候选149项和正式集成同149项通过，原冻结合同/候选保留；生产未加载新值，受管入口需先正常重载后台管理器再启动角色。详[核验与运行边界](EXECUTION_TIMEOUT_24H_20261024_REVIEW.md)。下方白名单为派发时合同，取件后必要的协调说明补正单列，不追改原冻结副本。

## 目的与范围

- 将TALK自带CLI任务执行入口的代码默认值统一为86400秒（24小时），同步自带启动/合同/部署示例模板，覆盖通用bridge、Codex、DSH、Kimi Code、WorkBuddy内置CLI及受管启动配方。
- 不新增页面配置项、配置存储或新API。已有命令行时限参数保留兼容，不另造配置机制；未显式给值时使用代码固定的24小时默认值。自带模板的旧600/21600默认值须同步，不能只改常量而被模板覆盖。
- 这里的时限按现有实现约束一次CLI调用，不改变任务排队、等人工澄清、等待成果收取和多阶段任务的计时合同；不宣称任务已有跨全部阶段的24小时硬截止。
- 不修改MCP客户端工具上限、单次TALK等待、HTTP、ready/stop、租约、上下文证明有效期或会话复用阈值；不机械替换所有600/21600。这些预算继续按[终端预算要求](../guides/TERMINAL_MCP.md#终端适配必查工具超时与等待预算2026-10-06)各自生效。本片不接入新终端、不启用主动等待，不以工具可发现宣称主动等待适配通过。

## 分工与实施边界

- 按现有协作约定，DeepSeek首次实现/必要自测，交付后暂停；Codex独立核验，发现问题由Codex直接修正、自检并集成收尾。Kimi开发仍暂停。
- 写根仅`.tmp/execution-timeout24h-v1/deepseek/`；候选文件按仓库相对路径写在其`candidate/`，证据与报告另存本写根。正式产品、测试、文档、冻结基线与协调目录不允许执行者改动。
- 候选产品白名单：`bridges/cli_bridge.py`、`scripts/role_service_host.py`、`scripts/kimi_k28_executor.py`、`deploy/bridges.example.json`、`deploy/kimi-code/k28-executor.launch.template.ps1`、`deploy/kimi-code/k28-executor.contract.template.json`。继承默认值的包装器只需核验，若发现另有必要改动，报告具体证据，不自行扩白名单。
- 候选测试白名单：现有`tests/test_role_host_runtime_configuration.py`、`tests/test_kimi_k28_executor.py`，以及新增`tests/test_execution_timeout_defaults.py`。可在候选树复制只读依赖以运行测试；复制依赖必须与冻结副本逐字节相同，不算新增修改权限。
- 候选用户/开发说明白名单：`docs/guides/USER_MANUAL.md`、`docs/guides/QUICKSTART_AGENT.md`、`docs/guides/KIMI_K28_EXECUTOR.md`。只改当前执行预算、页面不可配置、下次启动加载的必要说明，不追改历史报告。
- 不读取生产配置正文、DB、Key、私有state/身份档、原生日志或会话，不访问生产HTTP，不操作服务或角色、生产任务/286、owner/租约，不做原生模型调用或全机扫描。身份、模型/绑定/权限及原日志清理保持。
- 已运行进程继续使用原启动参数。代码交付/验证不等于已加载；正常加载须在可审代码与验证之后按既有部署约定处理，本轮不启停或热改生产。

## 验收

1. 通用bridge及Codex、pi兼容入口、Kimi Code、WorkBuddy包装器的真实parser默认timeout为86400；DSH走通用入口。受管配方各runtime最终argv恰有一个外层`--timeout 86400`，真实下游parser及预算报告一致。新角色普通受管启动沿同一配方取得相同值。
2. K2.8入口check/render/launch默认值、检查/报告/预览与最终argv一致；PowerShell/JSON模板及部署示例均为86400。保留现有显式值与非法值拒绝语义，不为该片重写校验器。
3. 用隔离假CLI/短预算验证现有正常结束、超时收尾与取消保护仍可运行；不等待24小时、不发真实模型请求。优先复用相关既有测试，只补跨入口默认值和模板一致性的有效检查，不新增镜像实现测试。
4. 核验MCP等待/客户端/HTTP/ready/stop及21600上下文证明等无关预算未变，记录代码/模板依据与未重核的真实宿主边界；不将执行时限调整称作主动MCP适配。
5. 提交变更清单、基线与候选SHA、实际测试命令/结果/限制，以及符合talk-delivery-1且task_id正确的结构化交付。失败和未验证项如实保留，交付即暂停，不提交Git、不派其它角色、不自行部署。

## 冻结与任务记录

- 基线源Git HEAD：`6c2d7a1`；本合同及本轮协调文档属于已授权的工作区文档增量。最终冻结文件列表、源/快照字节与SHA以`.tmp/execution-timeout24h-v1/coordination/manifest.json`为准，源/快照派前必须零漂移。
- 新工作线独立基础合同，不借用日志复核base315强续不相容会话；最终原生会话决策以运行回执为准。
- 默认派后结束，由用户通知完成后取件，保留单写者与独立复核约束；本片未授权下一功能。
