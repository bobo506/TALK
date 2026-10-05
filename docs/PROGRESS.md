# Project Progress

Updated: 2026-10-05 (Asia/Shanghai)，#153独立复核已收取，方案需修订；已派#154给Kimi定向修订P1–P7，派后结束等用户通知。

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

1. **当前#154：主被动开关方案定向修订（Kimi）。** #153/msg2655合法complete仅指复核完成，已收取completed；设计结论需修订（4中/3低），未实施。修订旧wait兼容/可靠API身份/取消表述/确定预算与退出契约/真实消费者/计数披露，版本耗尽仅低风险登记。Codex补充本入口#152/#153 created_by=human:bobo与指定agent:codex不匹配，不能宣称主控身份已自证。输出.tmp/controller-mode-c2-plan-fix/，原方案/复核不覆盖。完成后DeepSeek定向复核再决定实施；#152仍submitted暂未收取。
2. **后续前端小改动：角色页“参与任务”上方双横线仅保留一条。** 用户要求并入下一合适前端切片，不单独派片；尚未改UI，下一前端任务包必须带此项。
3. **用户明确当前仅桌面作为TALK任务发起客户端，现有执行程序继续使用。** 复用dsh_talk_mcp_launch.py/既有TALK MCP服务与npm bridge，不新增重复worker/member。S1b、直接exec/参数运输、内置CLI替换停止作为当前路线；已完成S1a只保留历史，不作为桌面MCP接入前置。
4. 已登记未开发：全局运行器库→项目角色绑定/添加编辑→手动启停/状态→项目加载时选择性自启动；默认检查角色/固定检查要求/自动转审；多工作区隔离与群聊阶段按路线图推进。只启动当前项目已配置且勾选的角色，软件安装不自动成为角色。
5. **主动长等待限制，默认被动收取。** 用户指出本次DeepSeek主动等任务，并进一步亲眼确认等待期间DeepSeek一直显示处于任务状态；这是桌面本轮持续活动的人工观察，与此前Codex主动等待的使用方式相似。源码确认MCP主循环顺序处理工具、wait同步阻塞且客户端取消不立即结束程序侧等待；300秒请求超过当前65秒客户端上限，同一MCP连接的后续查询会等待前项返回，这能解释反馈中的超时/排队机制，未做本次请求时序复现。DeepSeek桌面调度也沿用“派发后结束、用户通知完成再取件”，默认不主动长等或持续短轮询。pwsh两次0xC0000142仅保留原因未明的观察，不能确认为等待导致；不作为已通过核心接入的阻塞项。旧Hall消息2649–2653来源已记历史。

## Git与验证

- 用户持续授权向 `bobo506/TALK` 常规推送，不包含强推、删远程分支或改写历史。
- 桌面配置与指南收尾已由9e1bacb提交推送，配置/唯一备份在仓库外。验收记录2dbc0cf、等待说明36183b4及用户观察36ac16a已提交推送。#152派发与提示词911e117已推送。#153派发记录b7fe7ce已推送。本轮仅复核裁决/#154修订派发进度收尾，中文提交常规推送；实现尚未开始。
- 配置落地独立复核/受控写入/读回10检查已通过；本轮业务验收来源为用户实际桌面反馈，#151任务元数据另核实。未操作浏览器/读密钥/启停服务或重跑模型；因Hall成员权限不读取#151正文，不重复收取它。
- 本轮usage-gate返回continue，但session/weekly百分比null，不能据此声明精确用量；只派一个设计修订任务后结束。

## 证据与恢复入口

- C2-0原方案.tmp/controller-mode-c2-plan/report.md（hash e087793e…6c91144）与development.json（03d40926…0ea2b68d）；本地summary --expect-task-id 152有效partial，MCP msg2654代码块unknown。#153复核.tmp/controller-mode-c2-plan-review/review.md（90f2dfa0…963a499）与development.json（3568d88b…aa177e3），MCP msg2655有效complete且收取。#154修订输出约定.tmp/controller-mode-c2-plan-fix/（尚未交付）。
- 实际配置`C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml`（2275字节/hash245407f8…e2398d6）；同目录唯一备份尾缀`20261005-180915`（1045字节/hash4366d522…02b085）。实际执行日志`fix/logs/apply-target-20261005-codex-1.json`与独立读回`fix/logs/codex-post-apply-check.json`，fix即下述修正目录；实际落地见指南第5.3节，用户#151验收与环境反馈见第5.4节。
- 接入原件`.tmp/dsh-desktop-mcp-2/`（#147）；初审`.tmp/dsh-desktop-mcp-2-review/delivery.json`（#148）；修正`.tmp/dsh-desktop-mcp-2-fix/`（#149）；定向复核`.tmp/dsh-desktop-mcp-2-fix-review/`（#150）。原无效包`talk-delivery-1.json`保持，主控格式副本`decision/delivery-normalized.json`及normalization.json保留来源。
- 桌面MCP配置准备：`.tmp/dsh-desktop-mcp-1/`（#145/msg2642）；复核：`.tmp/dsh-desktop-mcp-1-review/review.json`（#146/msg2643，本地合法完整交付，MCP正文仍旧文本unknown）。安装版0.2.0-rc.2补丁数组/schema/HMR已独立核对；实际进程home已在接入时核对，GUI核心派发/收取已由用户#151人工验收；九工具全部动作未逐项验证。
- S1a原件：`.tmp/dsh-desktop-s1a/`；初审：`.tmp/dsh-desktop-s1a-review/`；当前修订：`.tmp/dsh-desktop-s1a-fix/report-revised.md`；定向复核：`.tmp/dsh-desktop-s1a-fix-review/`。
- 桌面调查：`.tmp/dsh-desktop-0/report-revised.md`、`.tmp/dsh-desktop-rereview-0/`；F2：`.tmp/remove-top-task-entry/`及review目录；正式用户回归步骤见ROLE_DESCRIPTION_ACCEPTANCE。
- 交付优先talk_get_delivery，同读preview与summary_text；必要时稳定引用补读。schema有效不等于验收。临时证据不随Git跟踪，核心事实/限制已写MODULE_bridges及历史。
- 启动见AGENTS；不为恢复上下文自动重启服务。完整历史在PROGRESS_HISTORY。

恢复指令：**继续项目**。当前#154已派给Kimi做C2-0定向修订，#153独立复核已收取，#152原报告/partial保留且暂未收取。用户通知#154完成后读取合法交付与修订映射，再派DeepSeek定向复核，确认后才正式设计落盘/开实现片。不要重复派#152–#154或主动轮询；下一前端实现片带双横线修正。桌面MCP#151核心验收保持，当前身份不匹配不是授权改凭据/主控指定。
