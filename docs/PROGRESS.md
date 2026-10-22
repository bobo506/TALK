# Project Progress

Updated: 2026-10-22 16:30（Asia/Shanghai）。用户要求汇总进度。Codex适配已完成实现、自检、正常加载和真实任务验证，代码提交fe64bc7已推送；当前DSH/Codex可用，全角色目标仍剩Kimi。本片暂停等用户确认，不自动开下一片。TALK页面保持。

## 当前交付

- 身份agent:codex/agent、项目prj_e8fe7066bbec/lead。用户指定本片自行开发，不派DeepSeek/Kimi，全部修改/验证称Codex自检。基线28a69d9，源码/授权及证据在.tmp/execution-session-codex-v1/。
- DSH已由292接通（原结果2898/SHA ef617e7fb6f02ac692fbd803c3d9176b9e0c80d74e1ca35d095cfb46eed3f19b保持）；当前再接通Codex0.163.0：同功能先验、可靠<60%续用/≥60%下次新窗、仅单纯缺数且可信计数时10次/第11换窗，首轮完整/续轮增量/新窗恢复。
- 新增Codex原生stdio及通道，复用规划/store/计数/合同；API支持bound/codex、bridge按runtime分派。读取最近请求last_token_usage.total_tokens和原生容量，保留来源时间；真实UserMessage+SHA才ACK，预检/工具/设置回执不计数，重复/未知送达/配置冲突均有守卫。
- 补延迟落盘、新版UserMessage、Windows扩展路径及正常resume配置回执；修隔离预检索要旧暗号。205项相关Python自检全过，含DSH既有链路。60%和10/11是受控原生格式/假模型边界，真实模型低占用。详[Codex实现与验收](spec/EXECUTION_SESSION_CODEX_ADAPTATION.md)。
- 实机300→301同原生ID01a162a3-eee4-7f63-b8d7-54ee978f0e71、计数1→2，301未重发暗号仍回复“海星84 / 银杏73”；302新ID01a162a6-bdc5-7a30-978e-82fd55d2e9a6、计数1、恢复“银杏73”，均完成收取。容量475000，301结束24443。298原首轮已收取；299停预检后由原请求者取消，原失败不追改，无正式投递。
- 当前桌面MCP和目标均agent:codex，自派400正常拒绝且未建任务；实机改由本片已授权human:bobo普通SDK/API创建及原请求者收取，不改MCP身份/权限。MCP双runtime接线隔离已验，不冒称桌面自派成功。

## 上片实测运行与保护项

- 原Codexmanager19564，正常恢复/单角色重载后generation21、实例ins_e98e909598ec，running/ready/idle；原gpt-6.1-sol/xhigh、独立登录/Key/HOME/绑定/权限保持，未解除owner。API原launcher正常重载，20664/子20500。
- 297条既有任务哈希、配置/绑定、其它角色及286全文/暂停保持；Codex原入口/DSH通道/规划内核/store/原native_driver和manager入口6份原源哈希不变。四个正式尝试298/300/301/302均confirmed，299不计，无在途任务或Codex通道。
- DeepSeek仍原manager18856、generation30、实例ins_7a91214893c6；本片未给其派开发任务或启停。原DSH293→294同窗、295换窗、MCP296→297同文件两轮的证据保留。
- Kimi额度暂停且尚未适配，不派Kimi或其它K2.8；286仍queued/control_status=paused，不恢复/取消/收取/集成，233候选保留。日志手动跨设备/全根留存及全入口21600待办保持。
- [使用说明](guides/EXECUTION_SESSION_USAGE.md)记录DSH/Codex支持边界及同名自派限制；GUI/费用收益未验且用户明确页面不改。精确额度占比不可读，不臆测；MCP上限T未重测，不启用主动长等待/自动唤回。

## Git与本次汇总

- 功能提交fe64bc7（接通Codex原生会话复用与上下文换窗）已推送origin/codex/terminal-return-codex；7份代码/测试SHA与205项自检时一致，提交后本地/远程跟踪提交一致。
- 本次仅更新本快照和历史记录，核对Git及文档；汇总前已跟踪文件干净，既有未跟踪产物保留。未重复模型调用、派任务、启停服务或重新核实运行PID；上节运行事实为上片验收快照，恢复时须先只读核对。
- 完整实施与验证记录见[历史进度](PROGRESS_HISTORY.md)及[Codex实现与验收](spec/EXECUTION_SESSION_CODEX_ADAPTATION.md)。本次汇总不代表用户已完成人工验收。

## 下一步

- 等用户确认本片；全角色目标剩余Kimi，适配范围和额度/实机安排须另行确认。宿主随TALK统一启动问题继续后置，不因本片完成自动派发或改变优先级。
- 不重复发300–302或重跑任何已用单次生产脚本。恢复先读本快照及Codex验收说明，再按最新授权推进。

恢复指令：继续项目（先核本片确认；TALK页面不改、Kimi/286暂停；不自动开启下一角色或宿主新片）。
