# Project Progress

Updated: 2026-10-13 19:59 (Asia/Shanghai)：236大部闭合，Codex接手剩余G1/G2已修正；独立复核#237已派DeepSeek。50新/320旧/原6/新增3分别通过，宿主代码尚未发布；完整一键配置与原生能力未验，I-4后置。

## 当前状态

- 项目`D:/claude-test/TALK`，project_id=`prj_e8fe7066bbec`，分支`codex/terminal-return-codex`。server发布d5a7bbd，接手源基线ca4f5e49951998e6793b15b2154bc6d99cb0ae7c；本轮只提交复核/接手/派审进度文档，回执worker-final-review/publication.json，待审宿主5文件不提交。
- R0/R1-1/R1-2完成并有基础页面验收。R1-3服务35886b3、最终页面34e9df4发布、223–229已收取，本轮页面基础用户明确“验收通过”。列表仅当前服务状态，启停只在详情、详情无重复状态；缓存20261012-role-service-list-status保持。
- 230–232准备链及233/234server片均已收取。三表/共享规则/10新API/4旧入口已实现，见[正式请求合同](spec/ROLE_CREATION_PROVISION_REQUEST_CONTRACT.md)；server仅存意图/事实，不写宿主文件或spawn。
- server独立新79/旧166/原7全通过；WAL两连接/线程与提交前六表回滚证据已核，234→233已收取。原失败/partial保持，证据server-final-review，不外推多进程/生产迁移/性能。
- 235/236未收取，原自报与失败不追改。236 msg2740说明+围栏JSON，MCP业务unknown；完整7689字符/SHA 650fe40784df1de1ffa0159f020e5b56b25f4f61988d067a461e6760ded33dfb，内嵌JSON与本地合法task236/complete一致，格式不冒充验收。
- 236独立44新/320旧/原6分别全过，确认模式/内存operator/租约资格与服务stop等大部闭合；新增3探针检出G1实际失败reported被CLI当成功、G2预检步骤内部取消/预算耗尽仍POST名册路径及3GET。原日志/235与236源副本保持，范围外源LF/CRLF归一零差异；证据`.tmp/role-lifecycle-r1-4-worker-final-review/`。
- Codex在DeepSeek交付暂停后按持续直接修正授权接手：仅请求驱动的逐HTTP资格/预算守卫，两个CLI将reported保留为业务失败退出码；50正式测试含追加6实际失败/步骤内与逐ACK边界用例。修后50新/320旧/原6/额外3分别全过、0fail/error/skip，未叠加重叠或作者证据；冻结candidate-snapshot/hash/diff/统计在candidate-verified.json，已暂停改码。

## 下一步与未完成

- **#237宿主独立复核**：Codex为最终修正开发者，DeepSeek独立复核，Hall group:task-d825fd7e75144926a27d12fb11a55f90，queued/assigned仅派发快照；包/回执final-review，复核产物仅`.tmp/role-lifecycle-r1-4-worker-cross-review/`。核实际候选与G1/G2及整体保护，原探针模块加载另存日志，不改业务/正式测试/原证据；发现问题交回Codex。
- 237完成暂停，用户“237好了”后Codex收件；独立通过才收取237/236/235并发布宿主，再Codex完整创建/配置前端、DeepSeek独立复核及完整功能人工验收。外部桌面引导、归档/删除和退出清理后续同范围，I-4后置。
- 50套件含实际隔离uvicorn+WorkerTransport/假Key私有文件/DACL/真实CLI operator文件来源/慢worker控制循环stop。无生产凭据/原生登录/模型/CLI启停、多角色隔离或主动等待验收；生产启用/部署/迁移/重载未执行。once/max_rounds的线程收尾有最长两段有界grace，完整退出清理仍后续，不外推硬网络期限/恶意TOCTOU防御。
- human-only、项目与worker默认关闭、server/worker同机回环、页面不落角色Key、保存配置与启动分开；跨机Key/TLS、任意Key读取和D7明文列迁移不夹带。

## 协作与恢复

- 用户要求headless也设max：实际TALK启动器为`dsh.cmd --profile headless`，desktop中的agent-default-model max未被该profile读取。已在仓库外`C:/Users/Administrator/.dsh/profiles/headless/cordis.patch.yml`设置`llm-deepseek.config.reasoningEffort: max`并UTF-8备份；DSH CLI 0.1.5-rc.2的`--dump-config`合成结果max/启用，未发送模型请求或重启现有236。下一次新启动任务核实际等级，原high历史不追改；白名单证据`.tmp/dsh-headless-effort/`，个人配置/凭据不提交仓库。
- 本轮用户指定前端Codex/DeepSeek复核，后端宿主DeepSeek/Codex复核；Kimi不足临时安排保持，页面常规Kimi前端要求不自动改写。已核caller=agent:codex/kind=agent和最新development_requirements，availability不证明额度。
- 共享目录开发完成暂停后再审查，237复核期间Codex仅维护文档；默认派发后结束、用户通知“237好了”再取件，不默认Browser验页。持续直接修正授权不免独立复核与人工门禁。
- bobo506/TALK普通提交后推送持续授权，不强推/改远端历史；旧生产配置/身份/名册/Key与历史.tmp-tests/ACL残留保持、不混提交、不宣称全工作区干净。
- 230/231原unknown混排/partial、232设计complete及233/234业务partial均原样保留，收取表示补正链按实际server片闭合，不表示原稿都通过或R1-4全功能完成。完整历史见PROGRESS_HISTORY，恢复指令：`继续项目`。
