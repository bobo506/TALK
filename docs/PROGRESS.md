# Project Progress

Updated: 2026-10-28 晚（Asia/Shanghai）。大K仍负责决策与分配。本日两个闭环：349/350 Terra首片已集成发布[PR #7](https://github.com/bobo506/TALK/pull/7)（未合并）；角色页面三项精简+创建弹窗两轮修正已由用户页面验收通过、本地提交未推送。G-terra 与 348 均卡在官方登录授权。

## 当前身份与协作规则

- 当前大K `agent:prj-e8fe7066bbec.k-d4bf0429`负责决策、拆包、分配和复核，明确保留，不得删除。旧成员`k-4bf013b9`的残留资源另行按归属清理。
- 349/350由DeepSeek开发、大K复核并正常收取completed。首个完整切片完成后，后续新任务按用户约定转为Terra开发、DeepSeek复核，大K只做决策和分配，不自动开工。
- 本日角色页面切片由用户直接指定DeepSeek单独开发、明确免去独立复核、由用户本人页面验收；这是本次明确授权，不改变上面的默认分工。
- `AGENTS.md`已结构化精简并持续人工调整，当前强调：新片先确认、合理颗粒度、单一写入方、独立复核、集中返修、生产权限保护、默认被动。
- Git规则：完整功能切片验收收尾后可推送一次，切片内部多次分布作业和返修只做本地保存。结果消息正文必须且只能是完整`development.json`，不得添加“已完成”“交付路径”等前后说明；旧自由文本结果不追改。

## 已完成实现与发布

- **角色页面三项精简（2026-10-28 晚，用户已验收）**：移除“上次自动启动未完成”提示；创建弹窗运行器/模型各占整行；角色列表文字可框选复制（拖选不导航、选区期间暂缓重绘）。同片返修两轮：下拉文字竖直裁切（定高38px挤16px内容区）、创建弹窗内部滚动条（`max-height`缺0.8界面缩放补偿）。改动5个产品文件+6个测试文件+4份文档，本地提交，未推送。报告与截图见`.tmp/role-list-select-20261028/`。
- **GPT-6.1 Terra目录**：官方`model/list`实测`model=gpt-6.1-terra`、显示`GPT-6.1 Terra`、默认强度`low`且非隐藏。human正常API登记`choice_id=rmc_54101bd4da53`，复用`builtin/openai/native-codex-chatgpt-login`，原Sol保留。
- **349/350 Terra首片**：349首次不通过的延迟启动状态门已由350修复；ready只恢复pending，`not_eligible/failed/enqueued/None`不再复活。共集成28个实现/测试/页面文件，SHA与fix1 candidate一致。集成后111项Node及原失败反例、正常pending和重复回调测试通过；Windows `ADMINI~1`短路径差异为baseline同现的环境限制，不冒充产品通过。
- **发布**：本地集成`8fa0f6e`，公开`4c5cb33`，PR #7仅含本切片34个代码/文档文件，不带其他内部提交，尚未合并。发布工作区`.tmp/terra-role-publication-20261028`保留。发布记录`7c129ca`，交付格式规范`e095f81`。
- **AGENTS公开PR #6**为早期版本，尚未合并或更新；当前分支后续规则以本地文件为准。
- 详[350复验与集成](spec/TERRA_ROLE_REVIEW_350_20261028.md)、[349首次复核](spec/TERRA_ROLE_REVIEW_349_20261028.md)。

## 当前运行现场

- 本日晚实测：`/healthz` 200（db/storage ok），8000端口监听PID `9660`，`uptime_sec≈3992`（约19:54重启），与12:00记录的PID `25440`已不同；`/api/tasks`未带Key返回422（路由正常，不再是500），未用真实凭据验证列表内容。
- 大K角色自身仍显示`recovery_required`，不要据此解除归属或清理。
- 新建`G-terra agent:prj-e8fe7066bbec.g-terra-cf9bbd88`绑定bound，但`role_native_setups.status=failed`、`error_code=native_cli_missing`，revision 5；没有服务状态、launch或实例。不能把绑定或宿主serving当成角色ready。
- 旧`GPT agent:prj-e8fe7066bbec.gpt-79445c1f`仍offline、无实例、无`role_native_setups`准备记录；不要连续点击启动或擅自删除。
- 当前API用系统Python+`PYTHONPATH=D:/claude-test/TALK;D:/claude-test/TALK/.venv/Lib/site-packages`，避免venv exe低完整性。生产配置、原生HOME、Key和既有角色未擅自修改。

## 旧任务与未解决项

- **347/2993**：首次独立不通过结论保持，WorkBuddy等运行器和整体联调仍未完成；**348/2994**：用户口述（本会话未独立核实）Codex已修一轮——受管Codex配方固定npm包内0.164.0、补齐运行配置缺失的codex段，`native_cli_missing`已解决，现卡在官方登录授权。两项`created_by=agent:codex`，只能由Codex正常身份收取。
- **角色页面余项3个**：强度展示的可信来源（3b）、删除后资源清理提示闭环（3d）、移除“绑定重置”区并统一详情（3g）。3c/3e/3f已随本片完成并验收。
- 旧记录250/2767 failed未收取、286 paused、344/2990 failed未收取，保持不操作。历史主控/页面开发要求可能仍是旧值，不冒称已同步。

## 下一步恢复顺序

1. Codex侧完成Terra的官方设备授权/登录，随后真实创建角色并验证官方low与start-ready-stop/drain；这属环境与授权步骤，不由绑定或serving推断。
2. 348/347由Codex正常身份收取收尾；两项凭据边界按用户口述已修，需独立核验后才能记通过。
3. 角色页面余下3项（3b/3d/3g）按完整可验流程拆包，需用户明确确认后开工，不因本片验收自动授权。
4. 其余路线图条目见[路线图](spec/DEVELOPMENT_ROADMAP.md)，不自动开工。

重开窗口后恢复指令：`继续项目`。历史细节见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
