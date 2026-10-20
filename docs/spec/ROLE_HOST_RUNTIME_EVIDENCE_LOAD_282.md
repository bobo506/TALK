# 282宿主正常加载与实机验证

日期：2026-10-20 10:19（Asia/Shanghai）。实现版本6f3f9c5。用户在“先核正常重载方式，再安排实机验收”的说明后明确“好的，那继续”，本次按该授权完成五个长期宿主正常重载及四个原运行角色恢复。A本地采集的加载和实机检查通过；页面状态用户已明确验收通过，本片先完成进度/Git收尾，B来源/接收/查询与C全根治理另片。

## 操作前提与实际路径

- MCP本人agent:codex/agent、项目prj_e8fe7066bbec、lead；queued/running任务为空，四bridge均idle且无当前任务。页面旧交叉复核开发要求原文保持，本轮由Codex直接核验和操作，未派开发任务。
- 逐个核原宿主的创建时间、精确入口、私有健康文件、持有launch及bridge直接父进程；五份原启动配方dry-run均通过。原API launcher15792/child9808保持运行，本片无需API重载。
- 普通产品stop停止DeepSeek、旧K2.8、页面K2.8和K3，原宿主各自收尾原Popen并释放归属。复核五角色stopped、无当前launch/归属、宿主原句柄为空及旧bridge退出后，才设置既有drain.request。
- 五原宿主逐个排空正常退出，核原入口进程全部消失后，才沿原精确命令隐藏启动一次；每个新host_started均有独立合法manager_run_id及可回查的完整日志引用。没有强杀、PID接管、恢复API或人工清owner。
- 五新宿主空载及健康文件推进复核通过后，通过普通start恢复原四角色；正常生成新launch/实例与归属。Codex桥接始终stopped、generation18，只有其空宿主重载。

## 两轮实机证据

第一轮UTC02:17:35.784922，最终轮UTC02:18:53.352975，相隔77.568秒。每个宿主同一run的成功周期序号和采样时间均推进，terminal对象满足固定16+5键合同，采样间隔固定60秒。

| 角色 | 原→新manager PID | 新bridge PID / 实例 | generation | 成功seq | 心跳推进 |
|---|---|---|---|---|---|
| DeepSeek | 16796→11612 | 12612 / ins_39ba69bf6dfe | 21 | 171→284 | 90.096秒 |
| 旧K2.8 | 9204→20396 | 17100 / ins_1719a2292f59 | 24 | 171→227 | 90.059秒 |
| 页面K2.8 | 12976→19228 | 2800 / ins_6fb574360b75 | 21 | 170→227 | 60.066秒 |
| K3 | 17540→9728 | 13844 / ins_5a0d307d038c | 21 | 114→170 | 90.111秒 |
| Codex | 5668→11768 | 桥接保持关闭 | 18保持 | 114→171 | 空宿主健康文件推进 |

四角色均running/ready/idle、无当前任务。每个launch_process_snapshot的project/member/instance/launch及run精确匹配当前实际启动，state=alive/exit_code=null；同launch的spawned.extra.child_pid等于实例PID，OS直接父进程等于新manager。最终四个宿主process均held=alive=1、exited=unknown=0、truncated=false；Codex空宿主四计数0、truncated=false。日志无扫描截断或坏行，manager保持member=unknown。

顶层pid是写日志的宿主，子进程PID由同launch的spawned关联。第一次临时核验误用子进程PID比较顶层，修正脚本并补启动记录/OS父链交叉检查；另一次在个别宿主60秒采样点前过早复验，随后在77.568秒间隔取得完整通过结果。两次均未改产品或原日志，说明保存在证据目录，不冒称首次全过。

角色配置/绑定、config.toml、入口及启动配方SHA保持；API原进程和健康状态保持，任务仍为空。未调用原生模型、制造生产异常或重复无变更的169项代码回归。故障/取消/坏时钟等分支沿用[独立复核及自检](ROLE_HOST_RUNTIME_EVIDENCE_REVIEW_282.md)的隔离证据。

## 证据与人工确认

本地证据根：.tmp/host-runtime-evidence-impl-v1/independent-review/deploy282/。包含preflight/manifest、四次普通stop/普通start回执、hosts下排空/原进程退出/新spawn/ready/引用回查、live-first/live-final/live-records、verification-script-correction及采样提前复验说明；执行脚本为上级load282.py。凭据仅内存读取，未输出或写入交付记录。

无需额外启动或新账号，沿用现有页面和本人登录。已请用户刷新角色列表确认四个执行角色启动成功、模型绑定保持、Codex停止；用户明确回复“验收通过，继续原计划”，本片人工门禁闭合。管理员本机可按[日志指南](../guides/RUNTIME_EXCEPTION_LOGS.md#282查看本地宿主循环与原进程观测)使用logs/runtime及--json --detail查询新事件。

本片只闭合A在当前同机拓扑的实际加载和周期采集。角色下载仍不透传新extra或manager记录，received_at保持缺失；没有验收新宿主实际接单/模型调用、六小时运行、跨宿主查询、故障演练、跨沙箱驻留或冷启动，不将这些能力由alive推断为通过。下一片先固定B来源、scope、接收时间及查询合同；日志整项完成后才做全入口预算统一和会话复用。
