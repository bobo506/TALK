# Project Progress

Updated: 2026-10-23（Asia/Shanghai，321收尾）。321主要复验通过，残留P3漏登记由Codex补齐，29项定向自检通过；320/321已收取，原partial/失败保留。后台/API导出代码完成收尾、生产未启用/重载，具体部署方案待确认。70%阈值已独立提交5394f2a，其免验例外仅限该次调整；原五范围自动清理保持。

## 本次：统一换窗阈值70%

- [调整记录](spec/EXECUTION_SESSION_THRESHOLD_70_20261023.md)：四类运行器共用内核改为`used * 10 >= capacity * 7`；旧60%布尔观测按原始token数兼容重投影，不批量改历史/计数。当前说明及六份现有测试的阈值数据同步。
- 按用户本次明确要求，未运行测试、联调或独立复核；未改配置/启停服务，不宣称运行中的角色已加载。缺数10/11备用保持。321的任务包/55份冻结与后台导出候选不改，实际同窗决策按当时加载版本及回执解释。
- 本次12份阈值相关文件已独立提交并推送`5394f2a`；未将321候选代码纳入该提交。当时保留的正式进度文档随本片321一起收尾。

## 本片：后台/API统一脱敏导出

- [合同](spec/BACKEND_DIAGNOSTICS_EXPORT_20261023.md)：API/统一后台/配置worker的项目/角色归属、启停/异常结构与处理结果已接线；显式DB绑定/项目清单/本地根，默认关闭。原角色时间下载合并后台，另有项目后台human-only导出；原权限、模型/Key/绑定、286和原清理策略保持。
- 18新隔离、74原启停/worker/本机宿主、24原导出、38权限/健康/清理共154不同Python、25Node自检通过。Node两处过时夹具已修正，原失败保留；自检不叫独立复核。
- 真实隔离network-run-4：API+独立runtime+worker、受控失败、三组件18条/合并19条、401/403/敏感值不在文件/同项目、正常Popen退出0及三组件stopped通过。十份产品SHA实测前后相同，生产config SHA保持3654bdc3…bf7012d。
- 320原partial/msg2961及失败保留，本地/远端JSON一致、原42源/快照零漂移后才接手，DeepSeek已提交并idle。F1改认证Session核真实角色身份；F2按DB真实角色/代码路由模板拒绝持久非法值；F3有限runtime/host码登记及实际异常携code。OBS1澄清：联合导出正确启用后全缺200 partial，未启用保持旧来源缺失503。
- 新28（原18+10反例）、原导出/认证等35、runtime/本机宿主24共87针对性自检通过；新network-fix1-run-1三组件21/合并22、无效路径404/403不入流、真实角色正例、原Popen正常0退出，11源SHA前后相同、生产config不变。Node未改，320独立25通过保持，不无关重跑全量。
- 321原partial/2962：独立确认F1/F2/OBS1及F3主路径、28新/定向+15鉴权等通过；末项`cli_command_unresolved`漏登记由Codex补正，扩展变量/条件赋值检查和真实dsh/cli/codex失败路径，修前反例失败、修后29项自检通过。末项未追加独立回审，旧失败/55份及原42快照不改；本地/远端交付一致，接手前55份当前源/快照零漂移。新差异与最终材料在coordination/review-fix2.diff及manifest-final.json。
- 320/321均已收取completed，原msg2961/2962仍partial；321实际new_context_threshold新窗session-9dd192d4-1d3b-41bd-aa99-934648d7a106/count1，基础SHA同315，末37.9106%。按其当时加载的60%版本解释，不套用后来70%规则；未新派复核任务。
- 保留缺口：不导入私有.out/.err、原生会话/异常自由文本、未知项目全局请求；不能证明历史完整，整体固定partial/coverage_unverified，不造旧记录。新增后台根只分段、不加入既有清理范围。原config SHA3654bdc3…保持；代码收尾共32份/502689字节最终冻结，未生产加载。[具体启用方案](spec/BACKEND_DIAGNOSTICS_DEPLOYMENT_20261023.md)已准备，只追加一节/原入口正常drain/用户原终端重启API一次/恢复部署前运行集合，待明确确认。

## 当前身份与边界

- 当前Codex `agent:codex / prj_e8fe7066bbec / lead` 已由API身份核实，直接开发/修正与收尾；DeepSeek独立复核，页面旧development_requirements不覆盖本次明确分工。
- Kimi开发暂停、286保护、模型/Key/绑定/旧报告不追改、默认派后结束/用户通知取件及新片先确认保持。319等旧复核均已收取；本片另做独立代码复核，不新增主动等待/自动唤回。
- 相容时优先续DeepSeek原窗；320实际续319/count2，末63.5214%，321按当时60%规则实际换新窗/count1、完整恢复基础，末37.9106%。319当时new_no_candidate/未续318保持；用户后来70%调整另记，不追改旧决策。

## 已实现及正式加载

- [实现合同](spec/LOCAL_LOG_AUTO_RETENTION_DESIGN_20261023.md)、[部署记录](spec/LOCAL_LOG_AUTO_RETENTION_DEPLOYMENT_20261023.md)：Windows按核验句柄删除，run lease/关闭凭据/分段快照和精确project/member/任务图保护；空任务/活跃/未知/缺证或依赖未闭环不删，1GiB是软预算。
- 用户批准同DB绝对路径、五个原成员source统一writer总根及enabled/30天/1073741824/86400。原runtime普通drain后由用户原终端重启API，新runtime14584/七manager serving，仅普通start恢复原DSH gen54/ins_057877d1df52/PID8652，其余六个保持停止，无强杀/归属CAS。
- 实际后台首次UTC12:20:23.836218检查：complete/errors空/454 legacy_or_unclosed保护/deleted0、532532295字节（约508MiB）、capacity_scan complete、未超预算，持久next_check为2026-10-24 UTC12:20:23（本地20:20:23）。policy五对scope与配置一致，由API后台写入，核验helper没有触发sweep或手写state。
- 新bridge manifest/PID/身份及活跃lease验证通过，closed不存在；DSH实际新鲜心跳、运行状态已独立交叉核对。

## 独立验收与收取

- 318代码complete/pass：132相关回归/27新增/5原反例/27复核侧反例通过，F1—F5/P1关闭；结果2959已收取。317原partial/2958保留，用户明确授权后也已收取。
- 319部署complete/pass：39份冻结及实际SHA/字节、生产config/policy/state/manifest/lease、真实API健康/新旧进程时序和恢复状态、helper无sweep/无伪造等均通过；未发现产品修正项。结果2960于UTC12:52:34正式收取completed。
- Codex取件再核39份源/冻结、远端与本地交付相同，见`.tmp/local-log-auto-retention-v1/coordination/319-acceptance.json`；独立报告/证据在`review-deployment/`。取件未再改产品或重复全量测试。
- 复核者受Git沙箱限制未比较旧config全字段；Codex另读取Git旧对象4d3d781追加自检，旧SHA与批准基线一致，解析差异恰为批准字段，未输出/保存旧配置，见`319-config-supplement.json`。这是协调方补证，不改写原独立报告。
- 代码0f67794、配置9ad18ca、加载记录f108a7a已推送；本轮为319验收/收尾文档更新，产品代码和配置未改。

## 保留的限制与下一步

- 正式清理范围仅五个已登记project/member；WorkBuddy、manager unknown、私有.out/.err及其它项目/OS不在本片，不称完整日志整项完成。
- 真实摘要HTTP200/scope正确，但complete=false/truncated=true、unavailable_sources1，只是部分查询；后台容量盘点complete是不同结果。若要改善全量查询，另行确认切片。
- 30天长期运行/未来容量增长和生产到期删除/410尚未实跑，0删除为缺证旧run保护；不造closed或改mtime来制造生产结果，现有隔离删除/410证据保持。
- 私有输出/后台日志统一导出、全入口21600、删除角色、自启动/退出等仍排队；主被动页面只保存意向，实际主动跟进/生效切换尚未完成。下一项待明确范围及确认。
- 历史见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
