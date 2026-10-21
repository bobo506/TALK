# 291独立实查与接线方案补正

2026-10-21。291原始结果2897为合法talk-delivery-1 complete自报，runner succeeded/submitted；两页稳定引用SHA256为`05e73b742932d6138f683510f0406d9b8ea81416e8997fb1d1cb103e5240a40d`，重建后与本地JSON语义一致。格式通过不等于业务验收；以下为Codex独立实查及直接补正，自改部分称自检。

## 身份、暂停与原件

- MCP实际agent:codex/agent、业务lead；项目`prj_e8fe7066bbec`。DeepSeek原实例`ins_ffc603d6fc88`交付后idle/current_task_id为空；实机再次核manager18856/bridge22812、gen28 running/ready，running任务0，配置/绑定、286整行及暂停、其它四角色保持。
- 原始9份文件共134,871字节先逐SHA留存于`.tmp/execution-session-live-entry-s0/independent-review291/original/`，原件不修改。30项目/57原生冻结件保持，未派返修、互审、Kimi或其它新任务。
- 只读冻结公开源和脱敏投影，不扩读真实配置、环境、凭据、会话正文或日志数据库，不启停/加载/模型调用。

## 独立发现及处理

| 问题 | 原稿位置/证据 | 补正 |
|---|---|---|
| 工作线与task/attempt混淆 | MOUNT_AND_WIRING_PLAN:160、253将continuity_key示例/来源绑定任务或attempt；与同功能跨task续用要求冲突 | 稳定协调工作线与一次spawn/run身份分开，窗口计数不随task重置。 |
| 指纹编码及来源不充分 | 原稿180-184无字段边界拼接，并重造绑定摘要；ab+c与a+bc哈希前相同 | 规范JSON/字段版本边界；沿用可核的已有绑定来源，有效配置/权限未知不准以启动规格声明冒充可续。 |
| 合法过期被一律阻断 | 原稿217；实际adapter 88-97、289-335允许合法source_expired有限分类 | 保持290条件分类，合法过期与未来/非法/错来源分开；仍要求完整计数及备用时钟。 |
| 宿主可声明原因超出实际API | 原稿218把capacity_missing列入无快照宿主声明；实际734-751仅三类 | capacity_missing必须由adapter验证快照后分类；无快照helper严格维持三类原因。 |
| 失败隔离承诺互相冲突 | 原稿203-212、280、307称不影响任务，316又允许boot失败；loader185-194会抛激活错误，headless128先等待loader | 分开spawn前生成失败、运行中采集失败和插件加载/激活失败；不自动模型重跑，未验前默认关闭/禁止生产启用。 |
| 挂载示例盘符错误及实施歧义 | 原稿81为C:/claude-test，真实仓库D:/claude-test；track camelCase/hostAttestation、输出回调顺序、终态覆盖和路径组件边界需明确 | 正式方案修正真实工作区来源，明确字段/监听/终态/传输信任边界，不依赖字符串路径前缀或输出自证。 |

原稿“当前headless无原生续用”的核心发现成立：冻结`dsh-headless/lib/startup.js:20-40`仅task参数，`lib/index.js:127-167`新UUID/create/followup/exit；`agent-loop`虽有resume但当前入口未接。挂载可行性只对已核默认源码提供候选，实际用户插件树及真正加载仍未验，不扩为所有DSH入口无resume。

正式后续依据为[接线方案补正版](DSH_CONTEXT_WIRING_DESIGN.md)，原9份交付、complete自报及原失败/限制保持，未追改历史结果。

## 验证及限制

- 本地workflow validate带expect-task-id=291通过；两页MCP结果SHA及本地语义匹配。
- 原static_probe以独立输出路径复跑通过：30/30项目、57/57原生冻结SHA，93/93源码锚点，4/4反向匹配，55/55安装树磁盘文件一致。它们是静态检查，不能称为挂载/模型集成测试。
- 独立12项定点核验通过：实际宿主helper三类原因及capacity_missing拒绝、三类合法过期分类、未来/错scope/非法原因阻断、原始拼接歧义和规范结构分隔。另核30个引用的SHA与行范围、loader激活失败边界；这是既有纯分类API和静态源码复核，未执行合成挂载链。
- collector的mount/track/read/untrack、native session创建/事件/projection与headless时序已独立读源码；字段、来源、cut/seq及解除监听仍须后续实现时做隔离合成验收。当前没有真实挂载、live指标、原生续用或ACK持久化。
- 本片只有方案/文档补正，没有产品代码变化，不重跑无关280项。文档另核UTF-8、新增本地链接、差异和原件/冻结SHA；所有证据位于`.tmp/execution-session-live-entry-s0/independent-review291/`，不提交临时原件或清理旧产物。

## 收取与后续

正式补正与自检后已于22:30:41正常收取291为completed，原结果2897保持；UTC回执`2026-10-21T14:30:41.377787`，见证据目录collect-receipt.json。用户要求的下一优先项是宿主统一启动链路，实施前明确范围及验收；本次不提前派发或更改服务。采集实现、原生续接入口与人工里程碑仍分别待后续确认。
