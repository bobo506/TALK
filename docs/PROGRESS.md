# Project Progress


> 2026-10-29 本轮更新：小K宿主凭据路径已被后续操作统一，既有恢复于20:30成功；下方19:25停止/路径分歧为历史快照。本轮修正页面定时器 Illegal invocation 导致等待不更新，104项测试通过；新请求真实页面验收待恢复浏览器确认框。见 [修复记录](spec/BINDING_RESET_TIMER_FIX_20261029.md)。
> 2026-10-29 晚补充（DeepSeek）：B1 后端**已闭环**——补上作业侧预期绑定指纹的补录回落（B1-d，`3a8091b`）后，20:30/20:44/20:45 三次恢复全部 `provisioned`，作业 `legacy-kimi-k3-20261017` 推进为 `succeeded`（`profile/key_file=skipped`、`preflight=succeeded`、revision 6），`credential_version` 保持 2，无多余轮换；用户确认小K 可正常启动与关闭。页面定时器修复与本文档其余改动由 GPT 完成、DeepSeek 代为提交。第 3 项仅剩 **3d 删除后资源清理提示闭环**。
> 2026-10-29 21:30（DeepSeek）：**3d 已完成**。删除被接受后角色立即离开列表；清理失败时角色回到列表（行内“删除未完成”），原因显示在详情“删除角色”按钮下方；删除独立清理面板与“重试清理”；再点删除即重试。旧大K 的失败行已由用户点重试清掉（`complete`，21:05）。版本 `20261029-role-delete-inline-v1`；全量 354 项 Node / 338 通过（16 项既有失败）。路线图第 3 项已全部完成，**可推送**，等用户确认；真实浏览器人验待。
> 2026-10-29 21:55（DeepSeek）：WorkBuddy 删除**已完成**（五步全 complete、roster 与 service 行删除、native 目录移除，21:48），3d 实机验收通过。大K 按用户授权执行 `recover-stopped`（generation 3→4，服务重置 stopped、旧宿主归属解除、实例置离线），宿主恢复 serving，启动/关闭/绑定重置可用。另修：同一成员已有更晚成功请求时，更早的失败请求不再弹“未完成”并清出本地跟踪（小K 刷新反复提示的根因，版本 `20261029-role-stale-request-v1`）；同时补正 3d 改版后的资源版本断言（3d 提交时全量跑在版本号更新前，遗留两处未覆盖）。
> 2026-10-29 22:45（DeepSeek）：外观模式完成。顶部左侧项目下拉框右边新增“自动/白天/夜间”三段控件：自动按 08:00–18:00 白天、其余夜间，跨边界与回到页面时自动重算；手动选择记在本机。四个样式文件 256 处颜色字面量收敛为语义变量，夜间整体换色（背景/面板/文字/边框/按钮/强调），首屏内联脚本避免闪白。版本 `20261029-theme-day-night-v1`；Node 全量 360 项 / 344 通过（16 项既有失败与基线一致），theme_mode 5 项通过；夜间实机四视图亮背景残留检测为 0。
> 2026-10-30 00:30（DeepSeek）：DSH 强度启动回填与 reload 卡死修复。新增仅 human 的 `POST /roles/{m}/binding/default-effort`（只改强度、不建不解绑定，未知值 422/无绑定 404）；强度枚举收敛到 `DEFAULT_EFFORT_VALUES` 共用；runtime 启动时读取 DSH 角色 `native/<member>/model-*.patch.yml` 的 `reasoningEffort` 回填一次。另修 `reload-api`：宿主长期保持 WebSocket 会让 uvicorn 优雅关闭一直等，导致旧 API 不退、reload 标记无限重试；现超时后终止旧子进程再启动。今晚因此发生一次 API 中断，靠重启 runtime 恢复；教训记入本文件。
Updated: 2026-10-29 19:25（Asia/Shanghai）。本轮由 WorkBuddy 交付 B1 恢复链的 B1-b/B1-c 两个修正并补测（`39bf7e7`、`4fcfc45`），**整链仍未通过一次真实端到端验证**；服务当前停止，小K 因宿主与 worker 的 Key 目录不一致处于 `manager_failed`。用户已要求转交其他角色接续，完整交接见[HANDOFF_20261029.md](HANDOFF_20261029.md)。

## 本轮未验收与阻塞（接手先读）

- **B1 全链未通过**：请求创建、claim、`rotate-key`（Key 真落盘）、建作业、profile/key_file 已实证；
  `preflight` 与完成回写未走通。B1-c 修了 preflight 两处，**但尚未在任何进程上加载验证**。
- **小K 起不来**：宿主 argv 指向 `TALK-private\keys\agent_kimi.key`（32字节、10-17、已失效），
  worker 写的是 `.talk\keys\agent_kimi.key`（44字节、10-29、有效）；宿主报 `Invalid API key` 8 次。
  属 B1-b 的副作用，Key 路径统一方案（A 同步文件 / B 统一配置 / C 反向设 key_root）待定。
- **服务停止**：`runtime state=stopped`、8000 无监听、宿主全部 stopped，需在正常 PowerShell 启动。
- **`/api/tasks?project_id=...` 出现一次 500**，未定位。
- 本地领先远程约 59 个提交，未推送。

## B1-c 现场事实（2026-10-29 18:36 实测后）

- B1-b 生效：小K 恢复在 17:36:07 成功调用 `rotate-key` **201**，`agent_kimi.key` 与 `credential.json` 已落盘，`credential_version=2`（与 DB `api_key` 一致、身份为 `agent:kimi`）。
- 但配置作业 `preflight` 失败 `identity_mismatch`：`expected_binding_fingerprint` 对无创建操作的请求返回 None；`preflight` 的绑定来源白名单只认 `creation_operation`（补录角色投影为 `legacy_attach`）。
- B1-c 已修两处（指纹回落请求快照、来源白名单加 `legacy_attach`），`test_role_legacy_recover`/`test_role_provision_requests`/`test_role_provision_jobs` 共 80 项通过。
- **生效前提：必须重启整个后台（runtime/宿主）**，因为 preflight 在 worker 进程内；只重启 API 不够。

## B1-b 现场事实（2026-10-29 下午）

- 小K`agent:kimi`16:33的真实恢复请求为`failed`：claim后调`rotate-key`被409拒绝，`role_provision_jobs`零行。原B1-a只打通建请求/建作业/完成回写，换凭据动作无分支。
- 根因链：`C:/Users/Administrator/.talk/keys`下无`agent_kimi.key`（仅空锁守卫）→ worker判absent → 调rotate → 仅managed独占身份可换。该角色能启动是因为宿主常驻持有内存Key，凭据从未落盘。
- 三个旧角色均只在`prj_e8fe7066bbec`名册，无跨项目引用；小K有9条8-9月的`idle`残留实例（进程早已退出），原先会以`rotate_identity_in_use`阻断换Key。

## 当前身份与协作规则

- 本会话实核身份agent:codex；本片按用户最新明确授权本人修复，不冒认上轮大K身份。Git/GitHub操作全部交DeepSeek；本轮未执行Git或派发，本片改动待后续提交。

- 当前大K `agent:prj-e8fe7066bbec.k-d4bf0429`负责决策、拆包、分配和复核，明确保留，不得删除。旧成员`k-4bf013b9`的残留资源另行按归属清理。
- 349/350由DeepSeek开发、大K复核并正常收取completed。首个完整切片完成后，后续新任务按用户约定转为Terra开发、DeepSeek复核，大K只做决策和分配，不自动开工。
- 本日角色页面切片由用户直接指定DeepSeek单独开发、明确免去独立复核、由用户本人页面验收；这是本次明确授权，不改变上面的默认分工。
- `AGENTS.md`已结构化精简并持续人工调整，当前强调：新片先确认、合理颗粒度、单一写入方、独立复核、集中返修、生产权限保护、默认被动。
- Git规则：完整功能切片验收收尾后可推送一次，切片内部多次分布作业和返修只做本地保存。结果消息正文必须且只能是完整`development.json`，不得添加“已完成”“交付路径”等前后说明；旧自由文本结果不追改。

## 已完成实现与发布

- **角色页面三项精简（2026-10-28 晚，用户已验收）**：移除“上次自动启动未完成”提示；创建弹窗运行器/模型各占整行；角色列表文字可框选复制（拖选不导航、选区期间暂缓重绘）。同片返修两轮：下拉文字竖直裁切（定高38px挤16px内容区）、创建弹窗内部滚动条（`max-height`缺0.8界面缩放补偿）。改动5个产品文件+6个测试文件+4份文档，本地提交，未推送。报告与截图见`.tmp/role-list-select-20261028/`。
- **官方思考强度（2026-10-29 凌晨，用户已确认强度显示生效）**：`project_role_bindings` 新增可空 `default_effort`（仅展示，不参与六维指纹与有效性），准备完成时由 Codex 官方`model/list` / Kimi 模型条目写回；绑定行第四段只读该字段，取不到整项省略；创建弹窗模型下拉只显示模型名。存量已回填：codex`xhigh`、kimi`high`、G-terra`low`、大K`high`、Kimi k2.8`max`、DSH`max`；旧GPT与WorkBuddy为空（前者配置无强度，后者绑定模型`kimi-k3`不在当前`models.json`）。
- **角色详情按钮行（2026-10-29 凌晨）**：`绑定重置`移到角色开关操作行第4位（启动/关闭、删除角色之后），去掉按钮下方说明段落；G-terra 截图确认四个按钮齐全。旧角色（小G/小D/小K）仍无该按钮，见下方未解决项。
- **GPT-6.1 Terra目录**：官方`model/list`实测`model=gpt-6.1-terra`、显示`GPT-6.1 Terra`、默认强度`low`且非隐藏。human正常API登记`choice_id=rmc_54101bd4da53`，复用`builtin/openai/native-codex-chatgpt-login`，原Sol保留。
- **349/350 Terra首片**：349首次不通过的延迟启动状态门已由350修复；ready只恢复pending，`not_eligible/failed/enqueued/None`不再复活。共集成28个实现/测试/页面文件，SHA与fix1 candidate一致。集成后111项Node及原失败反例、正常pending和重复回调测试通过；Windows `ADMINI~1`短路径差异为baseline同现的环境限制，不冒充产品通过。
- **发布**：本地集成`8fa0f6e`，公开`4c5cb33`，PR #7仅含本切片34个代码/文档文件，不带其他内部提交，尚未合并。发布工作区`.tmp/terra-role-publication-20261028`保留。发布记录`7c129ca`，交付格式规范`e095f81`。
- **AGENTS公开PR #6**为早期版本，尚未合并或更新；当前分支后续规则以本地文件为准。
- 详[350复验与集成](spec/TERRA_ROLE_REVIEW_350_20261028.md)、[349首次复核](spec/TERRA_ROLE_REVIEW_349_20261028.md)。

## 当前运行现场

- 本日晚实测：`/healthz` 200（db/storage ok），8000端口监听PID `9660`，`uptime_sec≈3992`（约19:54重启），与12:00记录的PID `25440`已不同；`/api/tasks`未带Key返回422（路由正常，不再是500），未用真实凭据验证列表内容。
- 大K角色自身仍显示`recovery_required`，不要据此解除归属或清理。
- G-terra官方授权及模型准备完成，Terra/low。最终实例`ins_e28faeceedf8`/PID11340 idle；宿主16440正常换代1784，runtime13920与其他宿主PID不变。此前native_cli_missing失败已过时，本轮实际启停通过。
- 旧`GPT agent:prj-e8fe7066bbec.gpt-79445c1f`仍offline、无实例、无`role_native_setups`准备记录；不要连续点击启动或擅自删除。
- 当前API用系统Python+`PYTHONPATH=D:/claude-test/TALK;D:/claude-test/TALK/.venv/Lib/site-packages`，避免venv exe低完整性。生产配置、原生HOME、Key和既有角色未擅自修改。

## 旧任务与未解决项

- **347/2993**整体仍未完成；**348/2994**两个DSH凭据拒绝边界仍缺修复/复验证据。之前Codex仅补CLI运行配置，本轮仅修Codex启动前缀，均不是348安全修复。原创建者agent:codex，尚未收取；正常收取与业务验收通过须区分。
- **旧角色兼容恢复（B1-a/b/c/d 已完成并实机闭环，2026-10-29 晚）**：小G`agent:codex`、小D`agent:deepseek`、小K`agent:kimi`为`origin=imported`、无创建操作。B1-a 以已提交`role_legacy_attach_operations`为锚点，`choice_snapshot`现读合成；B1-b 补 rotate-key legacy 分支；B1-c 放行 preflight 的补录来源；B1-d 让作业侧预期绑定指纹回落请求快照。20:30/20:44/20:45 三次恢复全部`provisioned`，作业推进为`succeeded`，`credential_version`保持 2，用户确认小K 启停正常。
- **DSH/WorkBuddy 强度接入只完成读取+回填**：WorkBuddy 的`models.json`有`reasoning.defaultEffort`（本机`max`），DSH 角色 patch 有`reasoningEffort: max`；两类运行器没有模型配置写入器，无法“新建角色时写”，只能脚本回填。是否在角色启动时顺带刷新，待用户定。旧 WorkBuddy 角色已删除，用户计划重建后再看。
- **角色页面余项**：3d 删除清理闭环已完成（`da001a8`）并实机验收；外观模式（白天/夜间）已完成并推送（`bc3bba7`）。
- 旧记录250/2767 failed未收取、286 paused、344/2990 failed未收取，保持不操作。历史主控/页面开发要求可能仍是旧值，不冒称已同步。

## 下一步恢复顺序

1. **347/2993 与 348/2994 的历史收尾**：整体仍未完成；348 两个 DSH 凭据拒绝边界仍缺修复/复验证据。原创建者为 `agent:codex`，收取需按其身份与权限执行；用户可决定是否重新派发。
2. **DSH/WorkBuddy 强度写入时机**：待用户在“启动时刷新”与“仅脚本回填”之间决定；WorkBuddy 旧角色已删除，重建后再看。
3. **缓存清理**：用户已明确优先级不高，暂缓；盘点结论见下（可安全清理约 40MB，大头是各 CLI 状态目录，不能按缓存删）。
4. 路线图其余条目（会话窗口换新、任务列表按真实对话窗口、运行器新版本提示、主被动跟进、定时任务项目化、工作区登记）见[路线图](spec/DEVELOPMENT_ROADMAP.md)，不自动开工。

重开窗口后恢复指令：`继续项目`。历史细节见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
