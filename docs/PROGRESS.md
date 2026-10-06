# Project Progress

Updated: 2026-10-06 (Asia/Shanghai)，重开窗口恢复并完成Codex当前连接加载检查。C2-A1代码独立复核通过并已提交推送，#152–#159已收取；九工具、新字段、短预算命中、人类身份门禁拒绝及后续查询已实测，真实主动链路未验收；用户通知#161完成，独立复核partial发现F-1/F-2；复核成果已收取，#160尚未业务验收/收取，已派#162给Kimi定向修正。

## 当前身份与协作

- 根目录 `D:/claude-test/TALK`；项目 `prj_e8fe7066bbec`；分支 `codex/terminal-return-codex`。Codex为决策Agent，负责范围/裁决/文档/Git；Kimi文字/设计/交互/前端、DeepSeek后端/其他，双方交叉复核。新派发前读取当前development_requirements，不按旧快照猜分工。
- 默认派发后结束，由用户通知完成再取件，不主动轮询；开发暂停后独立审查，不并行改业务码。顶层任务最小参数，标题只写名称由服务端加单一真实编号，旧双号不回写。Codex不操作浏览器，页面效果由用户验收。

## 重开窗口交接

- 稳定功能提交 `9ee0ac0`，此前进度补记提交 `4a67871`、重开窗口交接提交 `11977a8`，均已推送到 `origin/codex/terminal-return-codex`；本次交接开工时工作区干净，HEAD与该远程跟踪引用一致。当前分支未配置upstream，常规推送显式指定 `origin codex/terminal-return-codex`。
- 当前Codex连接目录共九工具，wait暴露 `controlled_wait`；项目list_agents返回 `caller_identity={member_id: human:bobo, kind: human, note: null}`，模式passive/version0，指定agent:codex/version13/assigned，effective仍null/not_bound。以#159历史完成任务、显式5秒预算验证false路径立即matched（程序elapsed0.016秒、1轮/1HTTP）；true路径按G4拒绝human凭据，随后list_agents成功。当前连接加载检查通过，不外推DeepSeek桌面已刷新或300秒等待/取消/API错误/真实主动链路通过。
- 用户确认C2-B范围后，按最新开发要求以最小顶层参数派#160“项目设置调度模式界面与角色分隔线清理”给agent:kimi，派发返回queued/assigned，未进一步轮询。任务包基线795dc19，副本.tmp/controller-mode-c2-b-dispatch/task.md；交付目录.tmp/controller-mode-c2-b/。DeepSeek #161已交付并收取，业务partial保留。#162已派Kimi定向修正F-1/F-2，返回queued/assigned；修正前快照/包在.tmp/controller-mode-c2-b-fix-dispatch/，交付目录.tmp/controller-mode-c2-b-fix/。完成后再派DeepSeek定向复核；默认派发后结束、用户通知完成。

## 最近完成

- C2-A1：#156开发；#157实际审查A–E/G/H通过、F-1重读错误缺包装/统计；#158只修F-1；#159独立定向审修正与共用poll出口、计数/日志兼容通过。Codex合看后确认工具实现通过，F-1关闭，#156/#158/#159已收取；#157此前已收取。格式/流程状态不单独作为验收证据，原#157本地partial/MCPunknown保留。
- 新工具合同：controlled_wait严格bool/default false，旧等待请求/返回/default与max600保持；true用Key身份/G1–G7/显式有限正预算、30秒重读、deadline与HTTP余量、mode/controller变化退出；caller_identity项目三键/失败不阻断/非项目null；运行期poll/recheck API错误含真实elapsed/rounds、恰好一次JSONL，失败GET计一次。九工具/query_stats四键不变，failure_stage仅JSONL。
- #159独立复跑controlled_wait29、task_tools/terminal29、controller_mode31项通过，新旧探针通过。不是重新全量审查，也未重跑216项全库/旧ACP沙箱失败；ACP本轮整套未取得通过。客户端取消无检测源、同连接排队、sockettimeout非端到端硬截止、总预算仅提示词约定，effective_mode仍null/not_bound。
- 2026-10-06用户明确要求每个终端适配都考虑超时报错。AGENTS必读项与TERMINAL_MCP通用要求已写：核验实际客户端上限T，显式单次等待W并留余量，记录正常到期/API错误/客户端超时/取消和后续查询证据；等待到期不自动续等。DeepSeek桌面65秒下W50，Codex保持用户现用W300，其它终端按实际T确定；仅调用策略/适配要求，本轮未修改真实客户端配置/通用600默认或新增宿主预算自动读取/限长。
- 前序角色页项目设置/开发要求/主控指定与角色说明B1/F1/F2已人工验收；DeepSeek桌面MCP经#151用户验收核心派发/交付/原会话收取通过，继续既有npm DSH与Kimi执行服务。内置CLI替换路线暂停；桌面chat对应旧任务不作为运行器切换依据。

## 当前验收与下一步

1. **Codex当前连接C2-A1加载检查通过，真实主动链路未验收。** 新目录/身份字段与历史任务短预算读取、预期G4拒绝及后续查询已实测，证据见上方；当前Key是human，不能驱动受控等待，不改凭据/指定/模式绕过。DeepSeek桌面刷新与长等待、正常到期/API错误/客户端取消排队边界未在本轮验证；各终端继续按TERMINAL_MCP预算要求分别验收。
2. **C2-B #161业务partial，#162定向修正待交付，#160未收取。** #161/msg2663合法完整自身任务号匹配，11完成/3未完成/0阻塞；主体A/B/D及C/E其余通过，独立Node150/Python12/集成15复现，409恢复探针6/7失败1项。F-1：409后GET失败文案指向隐藏重试按钮，需实际可达GET恢复入口；F-2：design-qa缺:has旧浏览器降级事实，补记录即可。Codex采纳两项并已收取复核成果（业务partial不改），派#162给Kimi只修两项，保留原失败证据/修前快照。#162交付后读完整摘要和实际增量，另派DeepSeek定向复核恢复探针/新增断言/必要回归；通过后再收取开发成果、同步模块/手册与业务Git并请用户页面验收。浏览器视觉/键盘、真实HTTP竞态仍未测；不并行改业务码。
3. C2-C约定消费者/指南与真实主动链路仍后续，须实际显式带入终端预算（DeepSeek50/Codex300），逐动作核验身份/模式/指定与总预算。配置保存active仍不代表执行生效/唤醒/互斥；不通过改凭据/指定来绕过true门禁。C2-A2版本耗尽为低风险可选，C2-D真正取消未开发。
4. 长期队列：全局运行器库→项目角色绑定/添加编辑→手动启停/状态→项目加载时选择性自启动；默认检查角色/固定要求/自动转审；多工作区隔离与群聊按路线图推进。只启动项目已配置且勾选角色，不自动启动所有已安装软件。

## 证据与Git收尾

- 收尾前HEAD `47e8fff3beb1da43a150032922a52c3112d163a3`，#156开工599f59c；中间主控提交仅正式文档。C2-A1已由 `9ee0ac0` 提交并常规推送，包含已审3业务文件、6份合同/规范/指南和3份进度文档，diff --check/源码hash/明确暂存12文件检查通过；本轮补记稳定功能提交号与加载待验状态。用户持续授权bobo506/TALK常规推送，不包括强推/删除/历史改写。
- 已审源码：talk_task_tools.py 101189字节/hasha98ac7a2878938c47337bc00cfa4364d275cfe185021a9efea1f6ac23e5c3a85；terminal8642/hash0a197814da98673956982788343b78db61e04e9946e527b361aeb5427d08f0b2；新测试67002/hash5745c5f31399d338caa4542e8684432ce9435c78dfe55939152fe5fe14edac7e。修正增量工具+49/-28、测试+189；累计实际工具+752/-59、terminal+18，新测试在收尾前按未跟踪口径另计，现已纳入 `9ee0ac0`。开发报告累计+812/-59和#157未收取笔误以实测/正式状态为准，原件不改。
- #159目录.tmp/controller-mode-c2-a1-fix-review/：review.md 7172字节/hashcd5f971479a76cfcbbadf87e491be7a0fa3de1d92b554361369e6cd1d1c35d36；development.json4651/hashe8b05faa68f409ea3886822df9f4143aba1919ab518db063229dbb594190639f，msg2661合法complete无省略。#158目录.tmp/controller-mode-c2-a1-fix/含修正前快照；#157目录.tmp/controller-mode-c2-a1-review/；#156目录.tmp/controller-mode-c2-a1/。原件/探针保持，新probe文本为逐字转录非自动原始日志，独立复跑证据优先。
- 收取时间（服务端记录，未补时区）：#159/msg2661 `2026-10-06T00:52:47.520546`；#158/msg2660 `00:52:50.346496`；#156/msg2658 `00:52:53.446218`；#157/msg2659此前 `2026-10-05T14:24:03.464981`。设计#152–#155也已收取，不能重复派发/收取。
- 桌面实际配置C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml与唯一备份尾缀20261005-180915在仓库外，原六项设置保留；指南DSH_DESKTOP_TALK_MCP第5.3–5.5节记录实际落地/人工验收/新预算要求。上次300秒wait超过65秒及同步排队机制已确认，pwsh0xC0000142原因未明，缩短预算不表示已解决DLL故障。
- 无新Web操作步骤；终端开发指南更新工具合同/重连与预算要求，USER_MANUAL日常页面流程不变。真实模型/长等待/浏览器/宿主660秒未测，未重载真实MCP或改运行配置/数据库/服务/实际mode/主控指定/权限。

恢复指令：**继续项目**。#152–#159当前相关任务已收取，C2-A1代码独立复核通过，加载与真实主动验收仍分开；Codex当前连接新字段/目录及短预算加载检查已通过，C2-B #160未收取，#161已收取且业务partial保留，#162已派Kimi修正F-1/F-2，用户通知#162完成后读取交付并安排DeepSeek定向复核。终端适配先读TERMINAL_MCP预算要求；默认派发后结束，不自动唤醒/轮询或改运行配置。完整历史在PROGRESS_HISTORY。
