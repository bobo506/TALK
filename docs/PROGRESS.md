# Project Progress

Updated: 2026-10-05 (Asia/Shanghai)，#158 F-1修正交付已收到、格式有效但未验收；已派#159给Kimi定向复核实际增量，#156/#158未收取，业务代码未提交。

## 当前工作与身份

- 根目录 `D:/claude-test/TALK`；项目 `prj_e8fe7066bbec`；分支 `codex/terminal-return-codex`；最新功能提交 `f743962`（F2），前序B1/F1为 `c147d09`。配置准备提交 `2433d34`；#147基线 `2433d34`，#150定向复核实际基线 `46b9faf`。Codex为决策Agent，负责范围/裁决/正式文档/Git，执行与完整复核交执行Agent。
- 派发前必须读取最新 `development_requirements`；当前Codex建议/派发/验收，Kimi文字/设计/交互/前端，DeepSeek后端及其他，双方交叉复核。开发暂停后审查，禁止并行改码。
- 默认派发后结束，由用户通知完成再取件，不轮询；顶层任务用general最小参数，标题只写名称，服务端加真实编号，历史双号不回写。Codex不操作浏览器，页面效果由用户验收。

## 最近完成

- 项目设置独立页与长期唯一主控指定/解除（ROLE-SETTINGS-1，`eb45298`）、开发要求编辑/读取/派发快照已实现并人工验收；无租约，不改变既有派发权限。
- 角色说明B1/F1（`c147d09`）与顶部入口移除F2（`f743962`，资源20261005-role-desc-f2）均人工验收通过。#139/#140已收取；#140原partial仅文档版本补正，历史报告保留。隐藏旧控件#123/#124已审并提交，#122失败历史保留。
- DSH-DESKTOP-0调查#126–#129已收取；桌面内置CLI0.2.0-rc.2、当前npm0.1.5-rc.2并存。用户于2026-10-05确认桌面最新chat对应TALK #133，UI可显示该会话，不代表桌面续聊/进程home一致/并发写入安全已验证。
- S1a已完成：#141/msg2638执行，#142/msg2639独立复核发现p5误判（原partial保持），#143/msg2640报告补正，#144/msg2641定向复核pass。#141/#143/#144本轮收取completed，#142此前completed；原报告和日志保留，正式结论以修订与独立复核合看。
- 隔离home下version/help/headless dump成功，desktop profile被拒，临时补丁路径输出证明有效home落点，headless初始化4文件。原p5仅三个独立参数；单参数内嵌LF经当前桌面dsh.cmd截断，直接exec Electron exe/实际桥参数运输未测。
- 真实home仅采样元数据相同，profiles跳过node_modules、sessions/storages聚合指标；不能证明全文件字节级未写或逐条进程归因。变量keep21/最终25已核对，进程数5为未存证观察。这些不属于S1a当次自省验收范围；后续桌面MCP已另由用户#151核心闭环验收，现有npm bridge继续使用。

## 下一步与待办

1. **当前#159：受控等待重读错误修正定向复核（Kimi）。** #158/msg2660合法完整talk-delivery-1、自报complete，10完成/0未完成/0阻塞，尚submitted未收取。DeepSeek已暂停，自报统一poll/recheck运行期api_error出口，补elapsed/rounds与恰好一条统计、失败GET只计一次；JSONL专属failure_stage不进入工具返回。新增2测试，controlled_wait29、task_tools/terminal29、controller_mode31项自测通过，原探针False/0→True/1；尚待Kimi核查实际代码。当前HEAD6d0a5f3，本次相对修正前工具+49/-28、测试+189/0，terminal hash不变；主控只核对清单/hash/统计，不重复代码审查或测试。#159最小顶层queued/assigned，仅审F-1增量、共用poll出口兼容/计数、JSONL附加字段与必要定向测试，不重审原片全部已过项。#157复核工作此前已收取completed，其原partial/MCPunknown保留；#156仍未通过/未收取，业务3文件未提交，尚未重载MCP/桌面主动验收，不称开关已可用。
2. **后续前端小改动：角色页“参与任务”上方双横线仅保留一条。** 用户要求并入下一合适前端切片，不单独派片；尚未改UI，下一前端任务包必须带此项。
3. **用户明确当前仅桌面作为TALK任务发起客户端，现有执行程序继续使用。** 复用dsh_talk_mcp_launch.py/既有TALK MCP服务与npm bridge，不新增重复worker/member。S1b、直接exec/参数运输、内置CLI替换停止作为当前路线；已完成S1a只保留历史，不作为桌面MCP接入前置。
4. 已登记未开发：全局运行器库→项目角色绑定/添加编辑→手动启停/状态→项目加载时选择性自启动；默认检查角色/固定检查要求/自动转审；多工作区隔离与群聊阶段按路线图推进。只启动当前项目已配置且勾选的角色，软件安装不自动成为角色。
5. **主动长等待限制，默认被动收取。** 用户指出本次DeepSeek主动等任务，并进一步亲眼确认等待期间DeepSeek一直显示处于任务状态；这是桌面本轮持续活动的人工观察，与此前Codex主动等待的使用方式相似。源码确认MCP主循环顺序处理工具、wait同步阻塞且客户端取消不立即结束程序侧等待；300秒请求超过当前65秒客户端上限，同一MCP连接的后续查询会等待前项返回，这能解释反馈中的超时/排队机制，未做本次请求时序复现。DeepSeek桌面调度也沿用“派发后结束、用户通知完成再取件”，默认不主动长等或持续短轮询。pwsh两次0xC0000142仅保留原因未明的观察，不能确认为等待导致；不作为已通过核心接入的阻塞项。旧Hall消息2649–2653来源已记历史。

## Git与验证

- 用户持续授权向 `bobo506/TALK` 常规推送，不包含强推、删远程分支或改写历史。
- 桌面配置与指南收尾已由9e1bacb提交推送，配置/唯一备份在仓库外。验收记录2dbc0cf、等待说明36183b4及用户观察36ac16a已提交推送。#152派发与提示词911e117已推送。#153派发记录b7fe7ce已推送。#153复核裁决/#154派发9689062已推送。#154收件/#155派发650e662已推送。正式设计/R1–R5与收取记录599f59c已推送。#156派发2ad9fbf、#156收件/#157派发e01d78a、#157裁决/#158派发6d0a5f3均已推送。本轮仅同步#158收件与#159派发，明确暂存3份正式文档；业务3文件保持工作区待定向复核，不混入主控文档提交。
- 配置落地独立复核/受控写入/读回10检查已通过；本轮业务验收来源为用户实际桌面反馈，#151任务元数据另核实。未操作浏览器/读密钥/启停服务或重跑模型；因Hall成员权限不读取#151正文，不重复收取它。
- 开C2-A1前usage-gate返回continue，session/weekly百分比null，不能据此声明精确用量；默认本轮只开一个后端/MCP实现片并暂停待复核。

## 证据与恢复入口

- #158局部交付.tmp/controller-mode-c2-a1-fix/development.json 6776字节/hash608bdaeb…75d6a6a、notes.md 9598/hashb7a4c8c3…d6c6fe3f，msg2660结构化有效complete、摘要无省略。修正后talk_task_tools.py 101189/hasha98ac7a2…e5c3a85，测试67002/hash5745c5f3…4edac7e；snapshot-before两文件hash与#156冻结值一致，terminal/原#157探针hash不变。主控核对累计numstat为工具+752/-59、terminal+18/0；开发者累计+812/-59及#157未收取为笔误，以实测/正式状态为准，原件不改。新probe文本为控制台逐字转录，非自动原始日志。#159输出约定.tmp/controller-mode-c2-a1-fix-review/，结果正文仅完整裸JSON，完成暂停。
- #157独立复核.tmp/controller-mode-c2-a1-review/review.md 16477字节/hashafafef2e…a16ca8、development.json 4300/hashcc502792…1edb0bb，本地summary --expect-task-id157有效partial且无截断；msg2659完整补读3028字符/hashf7e56eba…638f6dc仍unknown。probe_recheck_error.py 3558/hash05aa2d98…67c5cb3、txt 179/hash0cc673f3…013ccad。独立复跑27+29+31项通过，重读失败探针不通过；#157已收取2026-10-05T14:24:03.464981（服务端记录）。#158局部交付约定.tmp/controller-mode-c2-a1-fix/，保留原件和修正前快照，正文仅完整裸JSON，源码实际修正完成后另派定向复核。
- C2-A1 #156：.tmp/controller-mode-c2-a1/development.json、notes.md、measure_payload.py；msg2658结构化有效complete且无省略。主控核对talk_task_tools.py 99644字节/hashbb59cf9b…ad85715、talk_terminal_mcp.py 8642/hash0a197814…8f0b2、新tests/test_talk_controlled_wait.py 57408/hashf8ec6040…d6fe45；完整hash/自测证据和限制已写#157包与本轮历史。regress-tasktools.txt/probe.txt均0字节，不能作原始日志。#157输出约定.tmp/controller-mode-c2-a1-review/，只审代码/写局部复核证据；不改业务代码/正式文档/配置、不启停服务或主动等待。
- C2-0原方案.tmp/controller-mode-c2-plan/report.md（hash e087793e…6c91144）与development.json（03d40926…0ea2b68d）；本地summary --expect-task-id 152有效partial，MCP msg2654代码块unknown。#153复核.tmp/controller-mode-c2-plan-review/review.md（90f2dfa0…963a499）与development.json（3568d88b…aa177e3），MCP msg2655有效complete且收取。#154修订.tmp/controller-mode-c2-plan-fix/report.md（20010d18…9ebed92）、revisions.md（2365a505…38ed665）、development.json（fb101a06…0842c14），msg2656合法complete。#155复核.tmp/controller-mode-c2-plan-fix-review/review.md（876f66a7…7596bcf）与development.json，msg2657合法complete且收取；正式合同CONTROLLER_MODE_DESIGN.md含Codex R1–R5回填，原件均保持。
- 实际配置`C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml`（2275字节/hash245407f8…e2398d6）；同目录唯一备份尾缀`20261005-180915`（1045字节/hash4366d522…02b085）。实际执行日志`fix/logs/apply-target-20261005-codex-1.json`与独立读回`fix/logs/codex-post-apply-check.json`，fix即下述修正目录；实际落地见指南第5.3节，用户#151验收与环境反馈见第5.4节。
- 接入原件`.tmp/dsh-desktop-mcp-2/`（#147）；初审`.tmp/dsh-desktop-mcp-2-review/delivery.json`（#148）；修正`.tmp/dsh-desktop-mcp-2-fix/`（#149）；定向复核`.tmp/dsh-desktop-mcp-2-fix-review/`（#150）。原无效包`talk-delivery-1.json`保持，主控格式副本`decision/delivery-normalized.json`及normalization.json保留来源。
- 桌面MCP配置准备：`.tmp/dsh-desktop-mcp-1/`（#145/msg2642）；复核：`.tmp/dsh-desktop-mcp-1-review/review.json`（#146/msg2643，本地合法完整交付，MCP正文仍旧文本unknown）。安装版0.2.0-rc.2补丁数组/schema/HMR已独立核对；实际进程home已在接入时核对，GUI核心派发/收取已由用户#151人工验收；九工具全部动作未逐项验证。
- S1a原件：`.tmp/dsh-desktop-s1a/`；初审：`.tmp/dsh-desktop-s1a-review/`；当前修订：`.tmp/dsh-desktop-s1a-fix/report-revised.md`；定向复核：`.tmp/dsh-desktop-s1a-fix-review/`。
- 桌面调查：`.tmp/dsh-desktop-0/report-revised.md`、`.tmp/dsh-desktop-rereview-0/`；F2：`.tmp/remove-top-task-entry/`及review目录；正式用户回归步骤见ROLE_DESCRIPTION_ACCEPTANCE。
- 交付优先talk_get_delivery，同读preview与summary_text；必要时稳定引用补读。schema有效不等于验收。临时证据不随Git跟踪，核心事实/限制已写MODULE_bridges及历史。
- 启动见AGENTS；不为恢复上下文自动重启服务。完整历史在PROGRESS_HISTORY。

恢复指令：**继续项目**。当前#159已派Kimi定向复核#158 F-1实际修正与共用poll错误出口，用户通知完成后talk_get_delivery读取完整交付并裁决；通过时合看#157对原片审查与本次定向结论，由Codex收取#156/#158/复核任务、同步模块/正式说明与Git收尾。不要重复派#152–#159或主动轮询；#157复核工作已收取，#156/#158仍submitted未验收，业务3文件未提交，#152–#155已收取。未允许自动启停/改mode/凭据/主控指定，代码测试完成也不等于MCP已重载或主动链路已验收。下一前端C2-B片带双横线修正。
