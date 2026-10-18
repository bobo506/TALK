# Project Progress

Updated: 2026-10-18 11:07（Asia/Shanghai）。用户授权先修新版兼容再恢复Codex切换；兼容及保ID登记/正常受管启停已完成。原模型gpt-6.1-sol/xhigh/独立登录保持，186相关回归+12本地边界通过；原宿主16156当前gen5/ins_f9818ce92522/7572 ready。最小269已由human:bobo创建，默认用户通知完成后核验/经原请求入口收取；Codex页面人验待。已验四角色保持，尚未称五角色全验收。

## 当前身份与授权

- project prj_e8fe7066bbec，实际桌面MCP caller agent:codex/kind agent、业务lead；最新开发要求已实读留档，按用户本角色直接实施及恢复切换授权执行，不改生产永久要求或旧任务。当前桌面聊天/MCP未迁走或停用。
- 共享目录仅Codex开发/诊断/收尾。本轮186+12为Codex自检，不称他人独立复核。默认派后结束等待、用户通知取件；不操作Browser、不启主动等待，不开其它功能。

## 当前：原Codex受管启停通过，269待验

- CLI保持用户已授权升级的npm稳定0.163.0；直接使用该安装的vendor/.../bin/codex.exe，固定gpt-6.1-sol/xhigh/read-only/approval never，禁multi-agent/apps/plugins。新版使用developer_instructions及--strict-config；开发指令独有token实际精确匹配，证明注入生效，旧base_instructions不再进入本角色命令。通用默认命令生成器的历史行为未扩改，本角色用三个显式命令。
- 延迟定位到HostManager过滤后丢失父进程已有代理环境。仅用TALK_CODEX_NATIVE_标记在原生启动前还原原有8种代理变量，TALK bridge标准代理环境保持原样；值只在内存，不写盘/输出，不改系统代理/provider/认证。实际独有token探针13.656秒，消息12.187秒，均无WebSocket回退/未知字段警告；前轮122.094秒及失败原件保持，不承诺所有网络/模型调用同耗时。
- 三通道实际验证：预检accept及任务固定输出通过；初始消息MCP调用因never审批被拒（原件保持、无发送）。消息改用产品既有TALK_ACTION结构化协议，真parser+真execute_talk_actions+本地假client校验群成员及发送通过。所有原生通道均不加载TALK MCP；保沙箱与审批限制，未宽放权限。未变预检/任务复用首轮实际输出，未重复消耗或虚报新耗时；最后12项本地边界通过。
- 原TALK Key从全局config.toml既有talk.env源内存GET验证本人后，同值物化D:/claude-test/TALK-private/keys/agent_codex.key；未轮换/新建身份，不读DB秘密列或原生auth正文。产品API仅新增runner:codex-local（managed_cli、adapter仍unverified/能力空）及choice rmc_b0b68705cd2f（builtin/openai/native-codex-chatgpt-login/gpt-6.1-sol），legacy-codex-20261018保ID补录原agent:codex，名称/业务lead/名册/历史保持。
- 专属宿主launcher7328→实际manager16156，started_at UTC03:00:50.810375；私有目录C:/Users/Administrator/.talk/role-service-host/codex-next/prj_e8fe7066bbec/agent_codex/，原生仍native/prj_e8fe7066bbec/agent_codex/.codex。只领取本人/项目动作，保原Popen所有权，不从PID/诊断文件接管。真实父子7572→16156及实际21600/本人Key文件/三命令/模型参数已核。
- 首次gen1启动在Codex专用入口提前configure、args.key=None时退出；35秒验证先未闭合，原manager继续处理到就绪超时，失败/子进程日志保留。根删除wrapper中的提前导出，让共享入口先resolve_bridge_api_key再配置环境；新增真实双入口/文件+env+argv优先级及缺文件fail-closed测试，Codex/CLI/host共186通过。API不需重启，其它角色不受影响。
- 原manager正常gen2 stop释放首次失败归属后，修正版gen3 ready→gen4正常stop/旧进程退出/归属释放→只读重查不自启→gen5 ready通过。当前launch6278b283-9a15-4e74-9e01-0f06494d4919/ins_f9818ce92522/7572，仍由原manager16156持有，无强停或手改服务状态。实际服务ready不扩大后端固定版本、六小时实跑或完整新建自动启动结论。
- 最小任务269（269-原Codex受管实例最小接单回传），created_by human:bobo、target agent:codex，Hall group:task-967df63d427b46bc90ca60b5777cbe88，UTC03:05:49.140643。产品禁止自委派，故按授权使用既有人类操作Key创建；最新要求随正文保留。要求自身task_id/合法talk-delivery-1、completed唯一TALK_CODEX_MANAGED_ACK_20261018，不改文件/服务/调用工具。只有queued/assigned派发事实，未读结果或收取，不猜成功。
- 恢复证据.tmp/legacy-role-page-control/codex-next/coordination/：resume-migration-baseline/pre-compatibility、12本地测试、两transport canary、channel-verification初次拒绝/v2及native-channel-verification、登记前/后、host-launcher、firststart失败、key-file-entry-regression、fixedstart/healthystop/closedobserve/restart、managed-process-proof、pre-smoke名册/事实、smoke-delegation及managed-migration-stage/state。现有11源manifest及本轮产品两源SHA均保留；临时脚本只供当前迁移，不代表正式应用打包完成。
- TERMINAL_MCP已核：本原生三通道无TALK MCP/T/W，不启主动等待；当前桌面既有T660配置/W300不当新增宿主等待验收。完整异常日志、固定后端版本、六小时、冷启动及255完整新建自动ready人验仍待。

## 下一步

1. 按默认等用户通知“269好了”，再读取实际任务/合法交付/作者/Hall/领取实例及原Key/其它服务；不能因queued或ready称接单通过。
2. 269创建者是human:bobo，核验通过后必须使用原人类操作Key POST /api/tasks/269/collect-result；桌面agent:codex不是creator，不能用其MCP collect。完成后只验原Codex页面：关闭等“未启动”→刷新不自启→再启动ready。待用户人验再正式闭合最后角色迁移。
3. 18项其余顺序保持；已验四角色/267/268不重跑，完整日志/预算/会话复用等仍另片。

## 已验收角色与恢复事实

- DeepSeek已人验闭合b8f1ab5：原manager12536/launcher5424，gen5/launch4b20135f-e650-4d1d-8731-0b831a5f6458/ins_d2b05a620405/16712，deepseek-flash/max/21600，独立DSH_HOME/原用户级provider源只内存注入；管理目录私有deepseek-next/prj_e8fe7066bbec/agent_deepseek/。268原2822/收取保持，旧接单实例offline正常，不重跑。
- 三个Kimi均已人验：原Kimi K3 manager17672/gen7/ins_619c2a3c3e52/10496、私有kimi-next/；旧K28 manager11920/gen10与页面新Kimi manager17908/gen7、私有pilot/。保原Popen正常停后空句柄退出，不从PID/文件接管；API仍原api-launcher，不另起8000。
- 265代码6481dce/140回归、266/267/268证据及旧失败记录保持。完整日志、固定后端版本/六小时/主动等待及255完整新建首次启动人验未通过。恢复指令：继续项目。
