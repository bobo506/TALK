# Project Progress

Updated: 2026-10-23 00:31（Asia/Shanghai）。用户批准的角色名称/铅笔改名、统一启动及DeepSeek状态片已由当前Codex自行开发、自检并实际加载；368项Python、67项Node和生产重载/182秒心跳通过，待页面人工验收。下一新片不自动开启。

## 当前交付与身份

- 当前职责 `agent:codex / prj_e8fe7066bbec / lead`。本片用户明确全部由当前Codex实施，未派DeepSeek/Kimi或子代理开发，全部验证称自检。Kimi常规开发暂停、286暂停、每个新切片先确认继续有效。
- 新角色项目名称已保存为 `WorkBuddy-k3`，成员 `agent:prj-e8fe7066bbec.workbuddy-k3-61b7e314`；原创建值/全局名称为 `workbuddy-k3`。旧 `agent:workbuddy / WorkBuddy接入验证` 为另一身份，保留且停止，不合并/删除。名册role_name为项目显示权威，详情标题旁有同风格方框铅笔，可修改/取消/提示重名，跨刷新持久，迟到名册不覆盖。
- 新 `run.ps1` / `scripts.talk_runtime` / `scripts.talk_api` 把API、配置worker与七成员宿主一起启动，原生角色仍按页面普通启动/关闭。Windows隐藏独立常驻、OS单例锁、原Popen持有、虚拟环境真实父链、正常全局停止/API重载和启动失败有界退避均已核；不安装开机计划，不接管PID，不自动解除owner。

## 生产最终状态与证据

- 入口实际Python PID23816，API子进程Popen11220；七宿主serving，worker正常轮询。私有清单 `D:/claude-test/TALK-private/talk-runtime.json` 只含命令/凭据路径，原生HOME/Key/登录/模型沿用。
- DeepSeek gen38 / ins_bd06a61dbca2 / bridge5680；Codex gen30 / ins_35c3b5b9bb33 / bridge7900；新WorkBuddy gen10 / ins_6aaee847cfc4 / bridge17768。三者running/ready/idle，最终API重载保原manager/bridge PID、实例与服务归属，182秒观察心跳推进。三个Kimi原生角色及旧WorkBuddy保持停止/no owner，其宿主仅待页面请求。
- 原DSH manager18856/bridge11704均已exited且exit0，最后实例ReadTimeout为10月22日22:05:40，manager健康22:06:08；最初退出原因未确证，不能宣称ReadTimeout杀死进程。仅旧DSH gen30/原launch/原实例按一次human CAS计划恢复到31，再普通启动。Windows恢复脚本允许OS确认exited，present/unknown仍拒绝；原Popen丢失不自动接管。
- 受管队列前两次连续传输异常保留诊断并重试，第三次或非传输/任务异常正常报错，成功恢复；原90秒心跳真实性守卫保持。补正前实查能复现短暂错误投影，补正后首轮102次/最终97次重载采样各1次传输短断、0次非运行状态。
- 最终检查另发现SDK首次HTTP回退游标0回放八月私信；Codex因此生成回复2953—2955，保留原记录。立即普通stop，原生清理超过20秒，退出后原manager普通stop重试正常收取原Popen；没有强杀/人工解除Codex归属。现受管bridge启用启动最新游标、WS连接间隙增量补取和去重，失败不回0，重连不跳过新消息；普通SDK默认语义保持。最终重载后均空闲、无继续回放，无新增TALK任务。
- 368项相关Python、67项Node通过；SDK真实HTTP/WS间隙与回退、受管状态、日志、宿主、worker、名称隔离及UI竞态均覆盖。隔离API独立常驻/重载/正常停止通过。五份正式静态文件HTTP字节一致。证据 `.tmp/role-host-name-health-fix/`，最终 `production-final-verification.json`、`api-reload-observed-states.json`，失败与补正过程均保留。
- 原314条任务逐行SHA/286全文暂停、名册/绑定/配置、原Key文件mtime、WorkBuddy模型/settings/MCP源及Codex原认证源SHA/mtime保持。只改新角色项目名及三运行角色普通启停/DSH一次恢复的服务事实。原四运行器会话证据293—314保持，K2.8/K3共用适配，不代表WorkBuddy桌面窗口或主动MCP等待通过。
- 提交前31份正式改动、71份本片产物和三条旧回放回复原值凭据匹配0；游标修正后没有继续增加回放回复。UTF-8/新文档链接/PowerShell语法/差异空白检查通过，证据final-artifact-check.json。

## 使用与人工验收

启动/状态/正常重载/退出用 [统一启动指南](guides/TALK_RUNTIME.md)。当前服务已运行，无需再次启动；`run.ps1 -Config D:/claude-test/TALK-private/talk-runtime.json -Action status` 可只读查看。直接uvicorn仍只启动API；本机静态配方依赖原 `.tmp/legacy-role-page-control`，不要删除。WorkBuddy新成员可自动发现，其它运行器新成员仍须精确宿主配方。

请用户人类账号Ctrl+F5→角色：核对WorkBuddy-k3与旧验证身份、标题铅笔改名/取消/重名/刷新、DeepSeek及另两角色状态。未使用Browser/computer-use，不将DOM/API通过称视觉/人工验收。最初DSH外部退出根因及跨电脑/关机恢复未外推；正常关闭后重新启动仍按普通入口与归属守卫。

本片主体代码提交 `1b8e10d`；收尾清理新增测试文件尾部空行，无行为变更，常规推送后暂停等人验。原异常日志其它排期及任何新片继续先确认，不恢复286或Kimi开发。详 [本片实查](spec/ROLE_HOST_NAME_HEALTH_FIX_20261023.md)、[历史](PROGRESS_HISTORY.md)。恢复指令：`继续项目`，先读此快照，不重放单次生产脚本。
