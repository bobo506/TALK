# Project Progress

Updated: 2026-09-11 (Asia/Shanghai)

## Latest

- #30同类工具调研已收取：优先验证“单次MCP调用持续等待至成果或300秒”，保留当前Desktop，区别于回合结束后的外部唤醒。当前wait_tasks已有程序轮询但上限30秒；新增服务端事件非首轮前提。仅调研/方案修订，未做长调用实验或改代码；详细报告.tmp/terminal-return-research/REPORT.md。

- Codex回传首片#28/#29已完成可行性核验：PASS_WITH_LIMITATIONS。准确结论为未验证当前Desktop原会话的受支持外部入口；本机daemon仅Unix受限不等于所有入口不存在。无功能代码、无模型/原会话调用。待用户选择保持Desktop人工续办，或接受单独设计TALK受管Codex入口；禁止另起宿主resume冒充原会话回传。当前分支codex/terminal-return-codex。

- 最新：用户授权先试Codex回传，强调信息连续不割裂。分支codex/terminal-return-codex从6bdf380建立，#28已交DeepSeek做受支持原会话接入验证；无确定入口不得新建替代会话或伪造适配。后续Kimi复核。当前尚未完成回传。

- 最新优先项：统一终端成果回传，仅设计未实施。适用Codex/Kimi/DSH，先验证原会话续接能力，再做通用通知与适配器。方案见spec/TERMINAL_RETURN_DRAFT.md。本轮MCP实测1322字符、每角色1实例且无last_error，确认输出修复已加载；未派发新任务。

- 页面第二项已完成并本地提交9a4c0d7：Kimi #23开发，DeepSeek #25独立审查PASS，39项Node、2项Python通过。任务完整对话移除重复详情栏，页面效果仍待用户验收；Codex没有做本轮浏览器验证。
- 角色列表输出修复已完成：DeepSeek #26开发，Kimi #27独立复核PASS，16/16定向Python测试通过，双方成果已收取。默认每角色最多一条最新实例摘要，不返回完整历史实例/last_error日志；实例数组形状保留，availability_note说明未核验心跳。
- 当前分支codex/task-chat-layout；本轮工具修复保存本地，不推送。第一项成果开关提交37d88c7，协作/额度规则提交9b86cfd。尚未合并main。
- DeepSeek默认deepseek-flash已通过#25/#26真实执行。#24过期型号预检失败为历史，不需重试。用户模型目录仍可同步去掉过期型号id，避免误选。

## 默认协作与消耗控制

- 前端Kimi开发/DeepSeek审查，后端反向；Codex只管范围、摘要、分歧、文档及Git收尾，不重复完整代码审查/自测。
- Codex默认不操作浏览器；页面由用户验收。工具结果先过滤，只输出状态或短报告；同一会话不重复读取简报/模块全文，恢复仅补读进度和变化。等待不读diff/日志/截图，长任务放慢状态查询。
- 昨日角色历史原始输出约64718 tokens且夹带旧日志，后来被截断；不能等同于实际计费或准确解释30%额度。此次在调用过滤之外落实工具端默认有界输出。

## 验证与边界

- 角色输出：Kimi独立运行tests.test_talk_task_tools 8/8、tests.test_talk_terminal_mcp 8/8；含大量历史实例+超长错误日志、两条来源、最新实例/空实例、catalog stdio兼容。DeepSeek沙箱管道限制导致的缺测已被独立审查补齐。
- 当前Codex TALK stdio工具路径已修正；旧pi扩展未改，当前不使用pi。在线状态仍沿用既有语义，历史idle/busy误报问题另列，不能仅凭available判断在线。
- 驻留旧代码的TALK MCP进程需要重连后加载修复；本轮未重启用户服务、未清理数据库历史、未改密钥。
- .tmp、预览、日志、数据库不提交。用户级DSH配置未由Codex修改。

## 下一步

1. 用户刷新页面验收完整对话：无右侧重复任务信息，点击任务返回详情；普通群聊成员与成果开关应正常。
2. 必要时重连TALK MCP加载输出修复。后续可单独处理心跳在线判断；旧pi路径有界化仅在恢复使用pi时考虑。
3. 会议轮次与原终端返回仍未实现，见既有BRAINSTORM_NEXT；本轮不继续新切片。
4. GitHub远端推送此前被审批拒绝，具体目的地授权仍待用户确认；不绕过，不自动重试。

恢复指令：`继续项目`。完整过程见PROGRESS_HISTORY.md。
