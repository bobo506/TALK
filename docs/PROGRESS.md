# Project Progress

Updated: 2026-10-06 (Asia/Shanghai)。人工反馈修正#164经#165独立复核通过，均已收取；离页复位/状态行去版本已落实，正式说明已同步，待用户页面再验；本轮版本见Git收尾提交。

## 当前身份与协作

- 项目D:/claude-test/TALK，prj_e8fe7066bbec，分支codex/terminal-return-codex。Codex决策角色负责范围/裁决/正式文档/Git；派发前仍读最新development_requirements，当前Kimi前端/交互文字设计、DeepSeek后端/其它，双方交叉复核。
- 默认派发后结束，用户通知后取件；开发暂停再审查，禁止并行改业务码。Codex不操作浏览器，真实页面交用户验收；本轮不新派任务。

## 当前里程碑：C2-B-UX修正通过，待页面验收

- #164 Kimi实现：离开项目设置（任务/群聊/具体角色/项目账号等）放弃模式未保存选择；返回选中项与已保存模式一致，同页重绘不吞选择。离页不PATCH/自动保存/弹确认，保存在途迟到结果如实入账；仅清模式草稿，不影响其它编辑区。
- “已保存设置：被动/主动”不再显示括号和版本，内部controller_mode_version/expected_version、安全整数/CAS/响应核实保留；409重读失败reloadNeeded/可见GET-only重试/暂禁旧版本保存等恢复纪律不变。
- #165 DeepSeek独立实际源码/导航事件接线/生命周期及直接回归通过，0功能缺陷；Codex核对完整交付与对象一致性后接受。状态提示区无dirty/错误时留白为非阻塞打磨，不扩业务；radio/已保存行/保存禁用已明确真实配置。
- 正式USER_MANUAL/模块/设计合同同步离页行为与去版本、QA独立证据；手册草稿“同值可能不冲突”已纠正：陈旧版本即使同值也409，只有合法当前版本同值可成功；选值等于本地saved时前端不发PATCH。旧.tmp原件/历史错误记录不追改。
- 静态资源20261006-controller-mode-c2b-ux四处一致；现有服务无需重启，浏览器Ctrl+F5。入口角色→项目设置→调度模式，现有human密钥可保存，agent只读。active仍仅意向，实际执行仍null/not_bound；固定主控尚未移除，新发起者方案仅后续计划。

## 验证与限制

- #165独立Node模式30/30、十二份workspace178/178（--test-isolation=none）、原恢复7/7、新恢复12/12、集成15/15、新导航接线探针33/33、Python四页面契约12/12及语法通过。默认隔离spawn EPERM未执行用例，不外推Kimi默认模式自报为独立确认；不重复98后端/全库/C2-A1。
- 新探针加载真实workspace.js与app.js导航函数，用真实事件处理器驱动7类入口、在途/迟到/A→B→A/账号切换；仍是DOM存根，无自动化浏览器视觉/键盘/:has外观/真实HTTP竞态证据。边界Agent只读需现成agent密钥，409后GET失败需受控故障，可列人工未测。
- 收尾前11文件hash/bytes与派发快照一致；审查期间仅主控文档提交51c3035，之后新增计划8ce30c2也仅文档。Codex仅同步QA/正式说明，源码/测试与已审对象保持，统一差异检查、明确暂存15文件后中文提交常规推送origin codex/terminal-return-codex。

## 交付与恢复索引

- #164/msg2666、#165/msg2667完整合法talk-delivery-1/自身号匹配/complete，workflow completed。收取时间（服务端原记录未补时区）：#165 2026-10-06T10:45:05.197670；#164 2026-10-06T10:45:08.837644，不重复收取。
- 开发.tmp/controller-mode-c2-b-ux/{development.json,implementation.md,manual_draft.md}；独立.tmp/controller-mode-c2-b-ux-review/{development.json,review.md,probe_wiring.cjs}；派发包/11文件快照.tmp/controller-mode-c2-b-ux-review-dispatch/。原#160–#163也已收取，细节见PROGRESS_HISTORY。
- 本轮功能收尾基线HEAD8ce30c2feefcb0c35ea25075650c3e9d97ec7483，原功能946490f；本轮提交以Git收尾版本为准，不为了自引用hash再造业务改动。

## 后续计划与门禁

1. 用户验收：已保存被动→点主动不保存→分别切任务/群聊/具体角色再返，应回被动；反向同理。显式保存后往返保持已保存值，状态行无版本；停留同页面未保存选择不丢。通过前不开新功能切片。
2. 已登记未实施：以任务发起者created_by确定协调归属，项目统一主被动只影响发起侧，执行/复核正常完成；后续取消固定主控标签/选择并同步工具约束与合同。各Agent应使用自身API Key，Codex目前仍实测human:bobo，未切换；历史任务不追改。C2-C旧固定主控消费者合同须先修订，再依最新项目要求拆片，不按旧包直接推进。
3. 从各Agent运行端获取并上报可核实模型名称，页面用模型名替代裸ID展示，内部ID保持身份/关联键；无信息如实降级，来源/切换更新/同模型多成员区分后续明确。成员默认/自定义名称规则留完整角色页面设计。详见DEVELOPMENT_ROADMAP新增计划，尚无模型字段或已确认型号。
4. 等待按实际终端预算：DeepSeek桌面65秒上限下显式50秒，Codex保持用户现用300秒。九工具/controlled_wait/caller_identity加载及短预算历史命中、human G4拒绝/后续查询已检查，不等于真实主动链路/长等待/取消已验收；不自动唤醒外部会话、不改运行配置。C2-A2耗尽/C2-D取消、全角色/运行器管理/隔离/群聊等保留后续。

恢复指令：继续项目。当前#164/#165已收取，待用户两条反馈页面验收；不持续等待、不重复取历史结果。
