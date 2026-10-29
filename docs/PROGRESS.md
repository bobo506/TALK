# Project Progress

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
- **旧角色兼容恢复（B1-a 已实现；B1-b 补齐换凭据，2026-10-29）**：小G`agent:codex`、小D`agent:deepseek`、小K`agent:kimi`为`origin=imported`、无创建操作。B1-a 以已提交`role_legacy_attach_operations`为锚点（`rmc_b0b68705cd2f`/`rmc_3a5435e0e283`/`rmc_80be012402f1`），`choice_snapshot`现读合成，`_require_provision_identity`与`require_completion_facts`加 recover 分支，`/agents`投影出`credential_version`/`recoverable`，**不写也不复用**创建操作。B1-a 实机点击失败（rotate-key 拒绝 imported），B1-b 因此补：rotate-key 的 legacy 分支（必须带`request_key`+`lease_token`，锚点+代际+仅本项目引用四道门），并让已证明退出的历史实例不阻断（`ignore_exited_instances`，managed 路径不变）。合成用例 15 项通过；真实点击待用户在小K 执行，需**先停止角色**，换 Key 后重新启动才生效。
- **DSH/WorkBuddy 强度接入只完成读取+回填**：WorkBuddy 的`models.json`有`reasoning.defaultEffort`（本机`max`），DSH 角色 patch 有`reasoningEffort: max`；但两类运行器没有模型配置写入器，无法“新建角色时写”，只能脚本回填。是否在角色启动时顺带刷新，待用户定。
- **角色页面余项**：3b已随官方强度落库完成主要部分（余 DSH/WorkBuddy 的写入时机）；3d删除清理闭环、3g（已改为“保留按钮+移位置”并完成）状态见路线图。
- 旧记录250/2767 failed未收取、286 paused、344/2990 failed未收取，保持不操作。历史主控/页面开发要求可能仍是旧值，不冒称已同步。

## 下一步恢复顺序

1. **验证 B1-b**：先在小K页面停止该角色，再点“绑定重置”，确认请求`succeeded`、作业三步（profile/key_file/preflight，前者可能 skipped）与完成回写全绿；随后启动并确认新 Key 生效。若失败按稳定错误码定位（`rotate_legacy_roster_reference_refused`=跨项目名册引用，`rotate_identity_in_use`=仍有在用实例/任务）。
2. G-terra授权及实际启停已通过，后续真实模型任务/任务链按明确授权验证，本轮用户要求不派任务。
3. 348凭据边界修复/复验与347剩余范围仍待完成，再由Codex正常身份处理历史收尾。
4. DSH/WorkBuddy 的写入时机（启动刷新 or 仅脚本）与3d删除清理闭环按完整可验流程拆包，需用户确认后开工。
5. 其余路线图条目见[路线图](spec/DEVELOPMENT_ROADMAP.md)，不自动开工。

重开窗口后恢复指令：`继续项目`。历史细节见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
