# 285 管理账号查看权限正常加载记录

日期：2026-10-20（Asia/Shanghai）。用户明确选择“同意正常加载（推荐）”后，本次加载于15:45完成，15:48接口/数据核验通过。**仅`human:bobo`启用Group/Task Hall全局只读查看；16:21用户明确确认页面“验收通过”，本次未入群查看及只读行为的人验门禁闭合。** 日志接收保持关闭，没有派发新任务或调用模型。

## 授权、备份和正常重载

- 本人MCP身份`agent:codex/agent`、项目`prj_e8fe7066bbec`、业务角色lead；加载前全局queued/running均为空。原operator Key反查`human:bobo/human`，原本人Key反查`agent:codex/agent`，不创建或轮换身份。
- 配置及SQLite一致性备份置于仓库外私有备份目录，SQLite backup API完成后`quick_check=ok`；原配置字节与Git原提交一致。仓库内证据不含配置原文、数据库副本、Key或消息正文。
- `config.toml`仅追加`[conversation_access] observer_member_ids = ["human:bobo"]`，其余配置与备份解析等值；没有日志接收启用项、来源登记或上传动作。
- 原API launcher15792/uvicorn9808经原`stop.request`机制正常退出，端口释放后沿原脚本隐藏启动。新进程链wrapper19504→launcher5236→uvicorn13952及创建时间已核；不强杀、不启用自动重启。
- 五个原宿主管理进程及DeepSeek原桥接进程的创建时间一致。三个Kimi桥接在本次操作前已离线、服务为stopped，Codex桥接原为stopped，本轮均保持；没有重启角色或清除归属。

## 加载后验证

| 检查 | 结果 |
|---|---|
| 本人能力 | `human:bobo`为true；`agent:codex`为false，观察名单只有前者。 |
| 原未加入Task Hall | 285的原Hall历史GET 200，返回1条既有消息；非成员POST 403，无新消息。未为了验证创建任务、群或参与者。 |
| 未认证 | 缺少必填Header为既有422；提供无效Key为401。首次脚本误预期缺头401，核对`auth.py`后修正验证预期，产品鉴权未改。 |
| 既有数据 | 30张旧表的DDL/索引/外键声明保持；29张非心跳表逐行等值（projects仅排除last_seen_at），含members/Key、消息、任务、群名册、绑定、服务状态和launch/owner记录。实例身份列保持，状态/错误/心跳时间允许真实推进。 |
| 新日志表 | `runtime_log_sources/runtime_log_batches/runtime_log_events`各0行；旧30表加三表共33表。接收核心仍默认关闭，无HTTP接线或生产来源。 |
| 静态资源 | index/app/workspace真实HTTP200，与磁盘字节一致。无Browser视觉验证。 |

285所在Hall的`agent:codex`原本是成员，因此不将其在该Hall的读取当成“Agent越权读取被拒”的证据；本次核本人能力false，权限边界反例仍以此前162项Python/81项Node验证为依据。本轮没有产品代码变化，不重复运行无关测试。

## DeepSeek错误状态残留

API正常重载期间，原DeepSeek bridge12612/实例`ins_39ba69bf6dfe`在15:45:50记录一次连接失败。15:45:55的`queue_poll_recovered`显示poll_seq8332、recovered_failures=1、consecutive_failures=0；15:51:00的poll_seq8482仍成功，证明查询连接已恢复。

但实例仍上报原`ConnectError`错误状态，公开服务投影由ready降为unknown（“运行状态待核实”）。现有queue成功路径记录恢复证据，没有把之前的error改回idle；心跳继续带原状态。角色配置、原进程、世代、归属及数据库内原成功启动回执保持，**不能据此声称页面就绪状态也保持正常**。第二次加载验证捕获该差异，后续验证明确记录差异并逐行核原服务状态/launch未变，未伪造idle或恢复回执。

本次批准范围明确不重启角色，故未借加载重启DeepSeek；此残留问题待后续单独处理，不扩入日志B2b或自动恢复。Kimi额度暂停派发约束继续有效。

## 证据和后续

证据根`.tmp/admin-conversation-view-v1/independent-review/deploy285/`：`preflight.json`、`config-applied.json`、`config-git-scope.json`、正常停止/启动/ready回执、`verification.json`、首轮缺头预期失败及第二轮就绪差异、`deepseek-post-reload-poll.json`和受限加载脚本。原285/284交付与失败证据保持，备份内容仅留私有目录。

用户随后对[285页面验收说明](../guides/CONVERSATION_ACCESS_ACCEPTANCE_285.md)对应的验收问题明确答复“验收通过”：原管理账号未加入任务的完整对话/成果可读，未加入时发送/附件/回复不可用。新增`deploy285/human-acceptance.json`保留本次明确答复；加载时`verification.json`的pending标记为当时事实，不追改原证据。

285人验已闭合；DeepSeek错误状态残留仍待单独处理，不能将页面只读功能验收外推为角色状态验收。本次仅文档/进度/Git收尾，不重启角色或自动派发日志B2b。
