# Project Progress

Updated: 2026-10-13 19:36 (Asia/Shanghai)：235未通过、236待用户完成通知；已按用户要求把DSH headless提供商默认推理等级设为max，组合配置验证通过，实际新任务等级待核。server d5a7bbd保持，完整一键配置尚未可用，I-4后置。

## 当前状态

- 项目`D:/claude-test/TALK`，project_id=`prj_e8fe7066bbec`，分支`codex/terminal-return-codex`。server发布d5a7bbd，235交接HEAD ff40d89cbe85bda9b185d9ffb2a8a4f2bf2ef642；本轮仅提交复核/返修进度文档，回执worker-review/publication.json，未审宿主代码不提交。
- R0/R1-1/R1-2完成并有基础页面验收。R1-3服务35886b3、最终页面34e9df4发布、223–229已收取，本轮页面基础用户明确“验收通过”。列表仅当前服务状态，启停只在详情、详情无重复状态；缓存20261012-role-service-list-status保持。
- 230–232准备链及233/234server片均已收取。三表/共享规则/10新API/4旧入口已实现，见[正式请求合同](spec/ROLE_CREATION_PROVISION_REQUEST_CONTRACT.md)；server仅存意图/事实，不写宿主文件或spawn。
- server独立新79/旧166/原7全通过；WAL两连接/线程与提交前六表回滚证据已核，234→233已收取。原失败/partial保持，证据server-final-review，不外推多进程/生产迁移/性能。
- 235合法complete自报、msg2739完整5263字符/SHA 22847eb5774ab837cfda2ba7f39cf7daa766478eb055319567b01ecf6228fdfd，与本地逐结构一致，尚未收取。5个源/测试原字节副本、SHA、范围核对和独立结论在`.tmp/role-lifecycle-r1-4-worker-review/`；范围外源按LF/CRLF归一比较零差异。
- Codex独立原新增25全过、0fail/error/skip，作者旧11套件320仅核原日志/统计；新增6探针全失败、0error/skip。已确认关闭/只读入口绕过、慢配置阻塞stop、显式operator到三步丢失、create后disable仍写Key/metadata、异常轮次返回dict。TestClient/隔离库与假凭据真实临时文件，不操作生产服务/CLI/模型/Browser。

## 下一步与未完成

- **#236宿主同片返修**：DeepSeek开发/Codex独立复核，Hall group:task-f688956858ea43bd9de6086596cab9ce，queued/assigned仅派发快照；包/回执与F1–F5在worker-review，返修产物仅`.tmp/role-lifecycle-r1-4-worker-rework/`。统一关闭/只读、独立受控worker/预算与停止、内存operator贯通、当前租约/代际与新Key本人核验、本地失效即停、统一列表/错误/退出码。
- 沿235允许文件及必要正式回归，禁止修改server守卫/API、web/bridge/MCP/正式文档/生产配置/DB/名册/真实Key/CLI/模型/Git。原235/report/副本/失败日志只读；修后加载原探针另存日志，补实际隔离回环HTTP/WorkerTransport完整闭环，不能用假transport冒充默认传输。
- 236完成暂停，用户“236好了”后Codex实际复核；通过才收取236/235并发布宿主，再Codex完整创建/配置前端、DeepSeek独立复核及完整功能人工验收。外部桌面引导、归档/删除和退出清理仍后续原范围，I-4后置。
- 235有隔离假Key私有文件/DACL证据，默认真实回环传输未验证；无生产凭据/原生登录/模型/CLI启停、多角色隔离或主动等待验收。既有DB/假Key/固定文本进程/DOM证据不替代原生能力；生产启用/部署/迁移/重载未主动执行。
- human-only、项目与worker默认关闭、server/worker同机回环、页面不落角色Key、保存配置与启动分开；跨机Key/TLS、任意Key读取和D7明文列迁移不夹带。

## 协作与恢复

- 用户要求headless也设max：实际TALK启动器为`dsh.cmd --profile headless`，desktop中的agent-default-model max未被该profile读取。已在仓库外`C:/Users/Administrator/.dsh/profiles/headless/cordis.patch.yml`设置`llm-deepseek.config.reasoningEffort: max`并UTF-8备份；DSH CLI 0.1.5-rc.2的`--dump-config`合成结果max/启用，未发送模型请求或重启现有236。下一次新启动任务核实际等级，原high历史不追改；白名单证据`.tmp/dsh-headless-effort/`，个人配置/凭据不提交仓库。
- 本轮用户指定前端Codex/DeepSeek复核，后端宿主DeepSeek/Codex复核；Kimi不足临时安排保持，页面常规Kimi前端要求不自动改写。已核caller=agent:codex/kind=agent和最新development_requirements，availability不证明额度。
- 共享目录开发完成暂停后再审查，236开发期间协调方仅更新文档；默认派发后结束、用户通知“236好了”再取件，不默认Browser验页。持续直接修正授权不免独立复核与人工门禁。
- bobo506/TALK普通提交后推送持续授权，不强推/改远端历史；旧生产配置/身份/名册/Key与历史.tmp-tests/ACL残留保持、不混提交、不宣称全工作区干净。
- 230/231原unknown混排/partial、232设计complete及233/234业务partial均原样保留，收取表示补正链按实际server片闭合，不表示原稿都通过或R1-4全功能完成。完整历史见PROGRESS_HISTORY，恢复指令：`继续项目`。
