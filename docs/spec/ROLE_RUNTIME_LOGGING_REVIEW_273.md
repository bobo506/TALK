# 273日志查看/健康反馈方案：独立复核与直接修正

日期：2026-10-19（Asia/Shanghai）。首次方案：Kimi K3（agent:kimi / kimi-code/k3）；独立复核及直接修正：Codex。任务仅方案，不是API/页面实施。

## 原件与独立核验

- task273/result2839/agent:kimi/ins_23ea501725de，合法字符串任务号complete自报；与本地delivery.json一致。原正文SHA256为`cd552f6980376ec53e4e8caf02eb4fc8c9c954f8804c32f57334429d880f2945`，原9件及SHA在`.tmp/runtime-logging-parallel-1/independent-review/273-original/`，没有追改。
- 独立核17个冻结来源SHA及行号范围，并实读现有角色/实例/服务读权限、任务预检与页面重绘代码。公开角色/实例读取权限不等于新日志权限；现有无API/页面入口，不能把拟议能力当已实现。
- K3原32项静态检查和59项未来矩阵保留；静态关键词/样例通过不是运行测试或独立验收。其fixture-only投影在UNC、/srv路径、frame.function路径三个独立例中均未清除路径；不据此声称生产API漏洞（API尚不存在）。

## 直接修正

1. 分页重放首页规范化since/until/severity/query；后页不重新套当前时间。补独立服务端签名、cursor_epoch/expiry、scope/filter、来源版本及候选清单/内容指纹；首版追加/轮换/删除/替换等变化保守失效，不能只凭snapshot_until或第二次剩余文件扫描声称完整。来源暂不可达503与确证失效409分开。
2. detail拒绝所有查询参数（含detail=true）及重复单值参数；精确ref不套默认时间/severity，info/exception=null也能定位，不制造异常。
3. 自由文本出口统一覆盖message/type/file_name/function/原因链。修正样例投影的UNC、通用POSIX根和帧function净化，并补负例；明确其非生产扫描器、未知opaque秘密仍非完备保证。
4. 补领取前模型预检证据行及未来起止事件需求。272的190.352秒是创建至领取总时长，不能当模型耗时；queued不等于未工作，缺阶段证据仍未知，不伪写任务running。
5. 结合272/b40d59c说明宿主manager日志member=unknown，不能借当前owner混入角色页；本地ready/serve边界不证明report成功、OS存活或worker健康。首版只同机显式来源，多宿主桥及来源目录后续；并行准备遵守AGENTS隔离规则。

## 最终验证与正式产物

- 修正后36项本地静态/纯数据检查通过，17来源哈希一致；三个初始样例反例复测均通过。最终计数与初始失败、corrected副本保留在`.tmp/runtime-logging-parallel-1/independent-review/273/`。
- 67项未来验收矩阵（15正向/43边界负例/9健康反推断）均是not_run；不把矩阵条数当已执行测试。
- 正式[设计](ROLE_RUNTIME_LOG_VIEW_DESIGN.md)、[契约样例](ROLE_RUNTIME_LOG_VIEW_EXAMPLES.json)、[未来验收矩阵](ROLE_RUNTIME_LOG_VIEW_ACCEPTANCE.md)。原报告与原9件保持；本轮新增正式文档和本地自检，没有改产品代码、数据库或权限设置。
- 273已由原creator agent:codex正常收取，原结果2839保持。修正后的36项为Codex自检，不称K3再次独立回审；未派返修/新任务。

## 实施限制

两个GET端点、provider/稳定分页/签名与来源配置、页面及健康阶段补数均未实现；HTTP/Browser/生产联调未运行。human-only是未来新端点最小权限合同，不是当前已新增的读取授权。既有ready/owner/启停、原Key/模型/服务保持；全根容量治理与异常关机选择性自启动按原排期另片。
