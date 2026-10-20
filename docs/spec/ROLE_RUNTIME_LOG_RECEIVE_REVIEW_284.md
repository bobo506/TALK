# 284 SQLite日志接收内核复核与集成记录

日期：2026-10-20。结论：**DeepSeek首次交付经Codex独立实查发现问题；Codex直接修正、自检通过，B2a四文件已集成并收取。默认关闭，尚无HTTP接线或生产启用。** 本片依据[已批准合同](ROLE_RUNTIME_LOG_RECEIVE_DESIGN.md)，不代表完整跨宿主日志已经完成。

## 交付与独立实查

- 实际任务284，项目`prj_e8fe7066bbec`，发起者`agent:codex`、执行者及结果作者`agent:deepseek`，Hall `group:task-425cda60af724510862865e5366f8c37`。结果2891为合法`complete`自报，原文SHA256 `fb030fd68c1afedc725331f10fdedce513b8cd15d49101ced59b2d64f6833910`；本地JSON与消息值相同，稳定引用核验通过。原自报不改写成首次即通过。
- 取件时DeepSeek实例`ins_39ba69bf6dfe`上报`idle`、无当前任务，任务已`submitted`。Codex只在独立副本修正，没有返修派发或互派复核。
- 冻结基线`30e5eb8047b24b659ea24815d37e586a0f84f4c7`的82份源/指定文档逐SHA保持；237份原交付完整归档，最终逐SHA及文件集合核验不变。候选仅四项白名单，正式代码没有执行者直接写入。
- 原37项测试在独立工作区复跑全部通过，9.170秒。另建真实SQLite比较，30张旧表的列、外键、索引和DDL一致，仅多三张日志表；旧模型480个非import顶层节点和196个类/函数定义AST不变，旧import仅增加`CheckConstraint`。

## 发现的问题与直接修正

| 问题 | 独立证据 | 最终处理 |
|---|---|---|
| 持久回执只核基本形状和自身引用，不能证明它对应请求中的原事件 | 首轮7项反例：同时替换UID/引用、换log_id、换内容指纹、角色改manager归因、改批次首次时间、无效事件时间、超出来源序号，均错误返回成功 | 回执绑定已匹配批次SHA的有序事件草稿，核UID、log_id、指纹、实例/launch/manager归因、数量、时间和序号；事件行仍在时交叉核首次时间/序号等事实，损坏返回`503/stored_receipt_invalid` |
| 内核没有自己的锁等待/事务预算，实际受注入engine配置控制 | 第8个失败反例：注入2秒busy timeout，实测约2.203秒才失败 | 增加显式内部`transaction_timeout_seconds`，默认1秒、范围大于0且不超过5秒；SQLite等待不超过剩余预算或调用方更短等待值，SQL进度检查和提交前预算检查超时回滚 |
| 直接修正后的扩展探针发现底层SQLite中断异常可能绕过SQLAlchemy包装 | 扩展14项首轮13通过、1错误：真实SQL进度中断得到原始`sqlite3.OperationalError` | 同时映射SQLAlchemy/SQLite底层错误，返回静态安全错误；清理进度回调、还原连接busy timeout，持有连接直到清理完成再归还池 |

最终保留两份原测试文件，增加14项有业务含义的回归；原37+新14共**51项全部通过**，14.189秒。覆盖回执损坏、真实提交失败全回滚、解析后撤销来源、长SQL中断、迟到提交拒绝、连接设置恢复，以及原多store/WAL并发、去重、配额和归因验证。首次10项中的8失败、扩展首轮错误及原日志均保留。Codex修正后的结果称自检，不冒称另有独立复核者。

## 最终实现和边界

- `server/models.py`仅追加`RuntimeLogSource/RuntimeLogBatch/RuntimeLogEvent`及必要约束/import；新`server/runtime_log_receive_core.py`只接受服务端可信`PreparedBatch/PreparedRecord`，显式注入SQLite engine或返回全新Engine绑定Session的工厂、limits、clock，默认关闭。不导入`server.db/server.auth`，无配置或隐式建库副作用。
- 来源登记/撤销/重启用与接收均在受控SQLite写事务内重核实际Key、禁用、维护者/名册、来源版本；新接收核角色实例/launch双向归因，管理器核维护者与登记host。manager run和writer run保持独立；来源计数、稳定事件、批次回执和预算同事务提交。
- 已提交同批重放先重核当前认证/名册和来源，再验证持久回执；它不重新上传事件，不要求已接收事件的旧实例继续在线。事件行已清理时仍允许验证合法持久回执；这不是本片授权清理历史。
- 超时针对SQLite锁等待、SQL进度和提交前检查；不承诺强制抢占调用方session工厂/连接池等待、可信clock回调或操作系统底层I/O。它们需在后续HTTP接线中保持有界，不能把内核预算当外部客户端超时证明。
- 未实现真实writer逐字段投影/二次投影、HTTP/外部DTO、人类只读查询/游标/导出、来源配置启用、持久outbox、跨机器/TLS、物理SQLite/WAL回收。逻辑字节预算不承诺物理磁盘严格上限；旧local日志接口及宿主控制流保持。

## 集成、收取和下一步

仅集成四项产品/测试白名单。首次整合校验因CRLF/LF规范化导致原始SHA不同，在models写入后停止；修正协调脚本为核UTF-8文本等价及最终写入SHA，继续成功，原失败事实保留。正式四文件与51项测试工作区文本相同。

集成前只读核原API launcher15792/child9808均未启用`--reload`；没有重载API、建生产表、改配置/Key/owner或启停角色。B2a暂不提供可供页面验收的入口。UTC`2026-10-20T06:48:25.503354`实际收取284为`succeeded/completed`。

后续API重启会在既有`lifespan -> init_db -> SQLModel.metadata.create_all`路径新增三张空表；接收内核关闭不阻止建表。须在后续正常加载方案内核验并明确这项数据库变化，不能借其它页面加载无声越过本片的生产门禁。

证据位于`.tmp/runtime-log-sqlite-core-v1/independent-review/`：原始结果/稳定引用、`original-delivery/`、`prepare-verification.json`、原37/首轮反例/扩展反例/最终51日志、schema/AST、`integration-first-attempt.json`、`integration-verification.json`和`collect-receipt.json`。下一片为B2b真实writer投影与查询/HTTP接线；本轮先完成进度/Git，不自动派发后续。285仍按独立包执行，不在本片修改它的页面。
