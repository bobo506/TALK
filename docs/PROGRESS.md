# Project Progress

Updated: 2026-10-05 (Asia/Shanghai)，#157独立复核发现F-1重读错误缺包装/统计，复核工作已收取；已派#158给DeepSeek定向修正，#156未验收/收取，业务代码未提交。

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

1. **当前#158：受控等待重读错误统计定向修正（DeepSeek）。** #157 Kimi独立审#156实际代码，A–E/G/H通过，F-1中等问题：30秒项目重读GET失败时TalkToolError仍显式抛出，但缺elapsed/rounds包装与JSONL统计；HTTP500假时钟探针has_elapsed_rounds_wrapper=False、stats_records=0。Codex裁决需修正；#157复核执行已收取completed，不代表#156通过。#157本地包合法partial，msg2659因说明+JSON混排仍unknown自由文本，原件保留。#158最小顶层派发queued/assigned，当前HEAD e01d78a；仅talk_task_tools与controlled_wait测试及.tmp定向修正产物，修正前源码hash已核对保持#156冻结值，terminal保持不改。须运行期重读失败沿api_error显式报错，含真实elapsed/rounds、一次统计及失败GET计数，补HTTP错误/超时定向测试，保留其他行为；完成暂停后Kimi定向复核。#156仍submitted/未收取，3份业务文件未提交，尚未重载MCP/桌面主动验收，不称开关已可用。
2. **后续前端小改动：角色页“参与任务”上方双横线仅保留一条。** 用户要求并入下一合适前端切片，不单独派片；尚未改UI，下一前端任务包必须带此项。
3. **用户明确当前仅桌面作为TALK任务发起客户端，现有执行程序继续使用。** 复用dsh_talk_mcp_launch.py/既有TALK MCP服务与npm bridge，不新增重复worker/member。S1b、直接exec/参数运输、内置CLI替换停止作为当前路线；已完成S1a只保留历史，不作为桌面MCP接入前置。
4. 已登记未开发：全局运行器库→项目角色绑定/添加编辑→手动启停/状态→项目加载时选择性自启动；默认检查角色/固定检查要求/自动转审；多工作区隔离与群聊阶段按路线图推进。只启动当前项目已配置且勾选的角色，软件安装不自动成为角色。
5. **主动长等待限制，默认被动收取。** 用户指出本次DeepSeek主动等任务，并进一步亲眼确认等待期间DeepSeek一直显示处于任务状态；这是桌面本轮持续活动的人工观察，与此前Codex主动等待的使用方式相似。源码确认MCP主循环顺序处理工具、wait同步阻塞且客户端取消不立即结束程序侧等待；300秒请求超过当前65秒客户端上限，同一MCP连接的后续查询会等待前项返回，这能解释反馈中的超时/排队机制，未做本次请求时序复现。DeepSeek桌面调度也沿用“派发后结束、用户通知完成再取件”，默认不主动长等或持续短轮询。pwsh两次0xC0000142仅保留原因未明的观察，不能确认为等待导致；不作为已通过核心接入的阻塞项。旧Hall消息2649–2653来源已记历史。

## Git与验证

- 用户持续授权向 `bobo506/TALK` 常规推送，不包含强推、删远程分支或改写历史。
- 桌面配置与指南收尾已由9e1bacb提交推送，配置/唯一备份在仓库外。验收记录2dbc0cf、等待说明36183b4及用户观察36ac16a已提交推送。#152派发与提示词911e117已推送。#153派发记录b7fe7ce已推送。#153复核裁决/#154派发9689062已推送。#154收件/#155派发650e662已推送。正式设计/R1–R5与收取记录599f59c已推送。#156派发2ad9fbf、#156收件/#157派发e01d78a均已推送。本轮仅同步#157复核裁决/收取与#158派发，明确暂存3份正式文档；业务3文件保持工作区待修正复核，不混入主控文档提交。
- 配置落地独立复核/受控写入/读回10检查已通过；本轮业务验收来源为用户实际桌面反馈，#151任务元数据另核实。未操作浏览器/读密钥/启停服务或重跑模型；因Hall成员权限不读取#151正文，不重复收取它。
- 开C2-A1前usage-gate返回continue，session/weekly百分比null，不能据此声明精确用量；默认本轮只开一个后端/MCP实现片并暂停待复核。

## 证据与恢复入口

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

恢复指令：**继续项目**。当前#158已派DeepSeek只修F-1，用户通知完成后talk_get_delivery取完整摘要/修正前后增量，再派Kimi定向复核；通过后由Codex同步模块/正式说明与Git收尾。不要重复派#152–#158或主动轮询；#157复核工作已收取，#156仍submitted未验收，业务3文件未提交，#152–#155已收取。未允许自动启停/改mode/凭据/主控指定，代码测试完成也不等于MCP已重载或主动链路已验收。下一前端C2-B片带双横线修正。
