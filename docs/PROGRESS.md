# Project Progress

Updated: 2026-10-28（Asia/Shanghai）。当前由大K承担辅助决策与任务分配。Terra首片代码已集成并发布PR #7；新runtime已正常换代，G-terra准备失败为`native_cli_missing`，待配置实际Codex可执行文件后复验。

## 当前身份与协作规则

- 当前大K `agent:prj-e8fe7066bbec.k-d4bf0429`负责决策、拆包、分配和复核，明确保留，不得删除。旧成员`k-4bf013b9`的残留资源另行按归属清理。
- 349/350由DeepSeek开发、大K复核并正常收取completed。首个完整切片完成后，后续新任务按用户约定转为Terra开发、DeepSeek复核，大K只做决策和分配，不自动开工。
- `AGENTS.md`已结构化精简并持续人工调整，当前强调：新片先确认、合理颗粒度、单一写入方、独立复核、集中返修、生产权限保护、默认被动。
- Git规则：完整功能切片验收收尾后可推送一次，切片内部多次分布作业和返修只做本地保存。结果消息正文必须且只能是完整`development.json`，不得添加“已完成”“交付路径”等前后说明；旧自由文本结果不追改。

## 已完成实现与发布

- **GPT-6.1 Terra目录**：官方`model/list`实测`model=gpt-6.1-terra`、显示`GPT-6.1 Terra`、默认强度`low`且非隐藏。human正常API登记`choice_id=rmc_54101bd4da53`，复用`builtin/openai/native-codex-chatgpt-login`，原Sol保留。
- **349/350 Terra首片**：349首次不通过的延迟启动状态门已由350修复；ready只恢复pending，`not_eligible/failed/enqueued/None`不再复活。共集成28个实现/测试/页面文件，SHA与fix1 candidate一致。集成后111项Node及原失败反例、正常pending和重复回调测试通过；Windows `ADMINI~1`短路径差异为baseline同现的环境限制，不冒充产品通过。
- **发布**：本地集成`8fa0f6e`，公开`4c5cb33`，[PR #7](https://github.com/bobo506/TALK/pull/7)仅含本切片34个代码/文档文件，不带其他内部提交，尚未合并。发布工作区`.tmp/terra-role-publication-20261028`保留。发布记录`7c129ca`，交付格式规范`e095f81`。
- **AGENTS公开PR #6**为早期版本，尚未合并或更新；当前分支后续规则以本地文件为准。
- 详[350复验与集成](spec/TERRA_ROLE_REVIEW_350_20261028.md)、[349首次复核](spec/TERRA_ROLE_REVIEW_349_20261028.md)。

## 当前运行现场

- 旧runtime `18116`已正常停止，`shutdown=complete`。用户随后用系统Python和venv依赖重启API，新runtime为 **PID `25440`**，2026-10-28 12:00:54启动，startup complete、worker无错、六宿主serving；大K角色自身仍显示`recovery_required`，不要据此解除归属或清理。
- 新建`G-terra agent:prj-e8fe7066bbec.g-terra-cf9bbd88`选择Terra，绑定bound，但`role_native_setups.status=failed`、`error_code=native_cli_missing`，revision 5；没有服务状态、launch或实例。说明当前缺少可执行的Codex CLI配置，不能把绑定或宿主serving当成角色ready。
- 旧`GPT agent:prj-e8fe7066bbec.gpt-79445c1f`仍offline、无实例、无`role_native_setups`准备记录；它创建于新准备链之前，不要连续点击启动或擅自删除，后续按旧角色兼容/重建流程处理。
- 用户曾遇任务列表全空，日志为`/api/tasks` 500 `sqlite3.OperationalError: unable to open database file`；任务数据未丢，MCP可返回347—350。完整换代后是否已恢复需重新验证，不能只看healthz或刷新页面。
- 当前API使用系统Python+`PYTHONPATH=D:/claude-test/TALK;D:/claude-test/TALK/.venv/Lib/site-packages`，避免venv exe低完整性。生产配置、原生HOME、Key和既有角色未擅自修改。

## 旧任务与未解决项

- **347/2993**：首次独立不通过结论保持，WorkBuddy等运行器和整体联调仍未完成；**348/2994**：两个凭据边界未修，分别为TALK身份变量误作提供商Key目标、明文Key进入argv。二者`created_by=agent:codex`，只能由Codex正常收取，349/350不能替代其验收。
- 角色页面其余6项：强度展示、文本框选复制、删除清理闭环、下拉框宽度、移除自动启动未完成提示、移除绑定重置区并统一详情。其他16项路线及可选/暂缓见[路线图](spec/DEVELOPMENT_ROADMAP.md)，不自动开工。
- 旧记录250/2767 failed未收取、286 paused、344/2990 failed未收取，保持不操作。历史主控/页面开发要求可能仍是旧值，不冒称已同步。

## 下一步恢复顺序

1. 配置并核对本机实际Codex CLI可执行文件（当前PATH为`codex-cli 0.164.0`），不要改绑定或复制其他角色认证。随后重试G-terra准备，必要时完成官方设备授权，验证官方low、正常start-ready-stop/drain。
2. 重新检查`/api/tasks`与任务列表是否恢复；若仍500，继续定位数据库访问问题，不通过刷新掩盖。
3. 新角色实际链路通过后，后续切片才按Terra开发、DeepSeek复核安排；其余页面项按完整可验流程拆包。
4. 348安全边界优先于347整体收尾，最终仍由Codex收取原2994/2993，不复制Codex Key、不私改任务归属。

重开窗口后恢复指令：`继续项目`。历史细节见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
