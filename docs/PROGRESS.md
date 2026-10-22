# Project Progress

Updated: 2026-10-22 22:36（Asia/Shanghai，中断恢复核对）。WorkBuddy内置引擎独立CLI片代码、自检、309—311真实生产闭环和文档已完成；人工里程碑待确认，不自动开启宿主自启或其它片。

## 当前交付与身份

- 当前Codex身份`agent:codex / prj_e8fe7066bbec / lead`。用户明确本功能由当前会话自行开发/调试/自检，不派DeepSeek/Kimi开发，不称独立复核。WorkBuddy形态已明确批准为自带CodeBuddy Code引擎作为独立CLI，不代表控制原桌面窗口。
- 四类运行器DSH、Codex、Kimi Code、WorkBuddy内置独立CLI已接通同一基础合同/增量/新窗恢复、真实原生会话、可靠60%及条件10/11内核、API/MCP/普通领取和持久计数。只对已核验的本机版本/模型/权限组合成立，不能外推另一K2.8成员独立HOME或其它版本；TALK页面按用户要求不改。
- WorkBuddy新native/channel/bridge与单项目单成员host、服务配方已落地，产品`9ac1dbf`已推送。原WorkBuddy5.8.3内置CodeBuddy Code2.161.0，复用原身份Key和原模型来源`custom-local:kimi-k3`，独立HOME，不复制模型凭据或桌面会话。

## 验证与生产最终状态

- 联合相关Python **403项通过**；安装版配本机fake模型 **16次正式投递/17次模型请求**通过，覆盖同ID1→2、增量回想、force_new恢复、5900/10000续用、6000/10000后下一次新ID、受控缺数第1..10同ID/第11新ID。首轮计1、工具/预检不计、恢复指标不清零，非法/身份配置冲突不兜底。
- human:bobo已创建/收取309、310、311。309→310同原生ID`21ca2f60-7439-47da-82b8-a5a4c3d72fa7`、计数1→2，增量未重发暗号和基础仍答“青禾42 / 鹿鸣57”；311新ID`600b5ced-5e22-4db8-838e-62561b15733b`恢复“鹿鸣57”、计数1。三条均succeeded/completed，结果2936—2938已收取。真实用量31606/32039/31603，容量1000000；压力边界仍为受控证据。
- 原生/proof/投递账本双ID、请求ID与正文SHA一致；正式输入3、助手记录3、无工具，尝试3个confirmed、通道0。证据`.tmp/execution-session-workbuddy-v1/production/`含native-audit/final-verification与各阶段回执；当前片全部代码/验证称自检。
- 复用原全局`agent:workbuddy`及名称“WorkBuddy接入验证”，仅追加项目名册/imported角色、新运行器`runner:workbuddy-embedded-cli`和选择`rmc_150e9866f272`/绑定。原五名册业务字段保留，完整sync正常更新时间戳。运行器在实测及最终保护核对后标为adapted。
- API正常重载：launcher22340/child21996；原五角色服务行/绑定保持。临时WorkBuddy manager4708普通start(gen1)/stop(gen2)，最终stopped、无owner、可启动，空handles后正常drain退出。当前只有原DSH/Codex继续运行；三个Kimi仍停止，常规Kimi开发派发暂停。WorkBuddy原桌面进程未启停，不自动重启角色或解除所有权。
- 308条原任务逐行SHA、配置、286全文/暂停、原五服务/绑定、原Key文件mtime、WorkBuddy原models/settings/mcp SHA及mtime均保持；恰好三条新增验收任务。首次补录422/临时脚本not_started判断已按既成事实补齐，未重复建角色/任务，产品无修正。

## 边界和注意事项

- DSH293—297、Codex300—302及Kimi303—308的既有原生/收取证据保持；K2.8/K3共用kimi-code实现，无需两套适配。另一K2.8成员未单独实机，Kimi常规开发仍暂停。当前覆盖四类运行器的授权接入形态，人工里程碑待用户确认。
- 新WorkBuddy角色已停止，使用时先手动运行窄宿主再从普通入口启动，命令见[使用说明](guides/EXECUTION_SESSION_USAGE.md)。宿主统一启动、286、日志手动跨设备/全根留存和其它原排期保持；下一片须另行说明范围/验收并获确认，不自动派发/启停。
- WorkBuddy未配置MCP，不启用主动长等待；21600任务预算与MCP客户端T/W分开。GUI显示/手动续写/费用收益不在验证结论内。
- 一次诊断误输出原models数组，两项Key进入本次工具日志，已告知用户，未擅自轮换。已改固定字段白名单，生产验后205份本片产物精确扫描无凭据正文；不可复述原对象或声称工具日志已撤回。最终综合检查完成原值比对/原生writer退出检查后，在旧历史绝对路径链接断言处失败；修正仅检新增链接后的整体验证未执行，因自动审批工作区额度不足。恢复时未重读外部凭据，仅本地核验8份文档UTF-8及13个新增相对链接通过，不冒称整体验证生成成功回执。
- 精确额度百分比未读取，不臆测。新本地身份档及既有未跟踪产物保留，不混入提交。

## 恢复

22:36已只读核实309—311仍succeeded/completed且已收取、308条旧任务逐行SHA保持、原五服务行/配置/286保持，WorkBuddy仍gen2/stopped/无owner/pid为空。MCP当前身份仍agent:codex，本项目WorkBuddy bound/offline；当前身份非任务发起者，生产任务事实按本地只读数据库核验。剩余Git收尾仅8份文档，无产品改动、不重放原生产脚本。证据`production/resume-check.json`。

[WorkBuddy实现与验收](spec/EXECUTION_SESSION_WORKBUDDY_ADAPTATION.md)、[使用说明](guides/EXECUTION_SESSION_USAGE.md)、[完整历史](PROGRESS_HISTORY.md)。恢复指令：`继续项目`；先读本快照，不重放单次生产脚本，不恢复286或Kimi开发派发。当前片收尾后等用户验收/下一片明确确认。
