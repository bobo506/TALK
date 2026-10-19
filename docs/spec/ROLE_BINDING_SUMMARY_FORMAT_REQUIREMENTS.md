# 角色列表绑定行统一格式

确认日期：2026-10-19（Asia/Shanghai）。用户要求角色列表绑定行统一为“已绑定 · 运行器名称 · 模型名称 · 思考强度”，随后明确：获取不到思考强度时留空，不显示“未提供”。280已由Codex独立实查通过、合入并收取，289项Node及九静态资源HTTP字节通过；当前等Ctrl+F5页面人验。详[280复核](ROLE_BINDING_SUMMARY_FORMAT_REVIEW_280.md)。

## 显示与数据边界

- 只改角色列表的 `workspaceRoleBindingSummary` 及必要辅助函数；保持现有“绑定：”前缀和中点分隔。有效绑定按状态、运行器短名、模型名、可得思考强度排列。
- 思考强度没有明确值时省略这一项和对应分隔符，不显示“未提供”“未知”“默认”等占位，不猜Kimi强度，不将 `thinking/always_thinking` 能力标签当作强度。
- 现有公开binding没有独立思考强度字段；Codex、DeepSeek已有 `model_display_name` 尾段明确写出 ` · xhigh`、` · max`。仅拆分展示名末尾以中点分隔的已知强度字面量（none/minimal/low/medium/high/xhigh/max/ultra，匹配忽略大小写，显示保留原值），前段须非空；未知后缀保留为模型名，不据别名/成员名/运行实例或native配置猜值。模型仍按展示名→alias→id原顺序降级，不修改绑定数据。
- 运行器使用原登记名的紧凑展示；保留自定义名称。当前三个Kimi共用旧登记名 `Kimi Code · K2.8 Preview 执行`，其中K3的实际模型字段为K3。对 `runtime=kimi-code` 且精确匹配这一已知旧系统名称（及不带“执行”的版本）的情况，列表运行器短名统一为 `Kimi Code`，模型始终用当前binding模型；不把旧K2.8标签拼到K3运行器段，也不改运行器/角色永久名称或绑定。
- 其它运行器原有“只去同模型重复尾段”的规则保持；自定义运行器包含中点等情况不被笼统截断。所有输出继续用textContent；未知字段、凭据、日志不进入绑定行。
- 未配置、partial、离册、退役、未知/缺失字段等状态区分及旧服务降级保持；不能因新格式把未知/无效显示成已绑定。详情不恢复已移除的属性表，服务按钮/草稿/选中/搜索、任务分页和诊断下载行为保持。

## 五角色应有结果（只读示例）

- Codex：`绑定：已绑定 · Codex CLI · gpt-6.1-sol · xhigh`
- DeepSeek：`绑定：已绑定 · DeepSeek Harness CLI · DeepSeek Flash · max`
- K3：`绑定：已绑定 · Kimi Code · K3`
- 两个K2.8：`绑定：已绑定 · Kimi Code · K2.8 Preview`

以上值来自当前API公开binding，本片不宣称实际模型/强度调用验收；没有额外强度不强行凑四段。

## 隔离、实现与交付

- 用户明确授权本页面小修，与279日志后端片隔离。冻结产品基线 `9285fd696dfc8f466d729b6b73f9a31740ef2fda`；279候选目录及正式后端完全禁止写入/读取其未交付产物。Codex独占协调文档/Git；两个执行者交付暂停并核范围后，串行集成。
- Kimi K3（agent:kimi / kimi-code/k3）首次实现及必要自测，交付暂停；Codex独立实查，问题由Codex直接修正并自检。页面旧交叉复核文本不改，按用户/AGENTS最新协作方式。
- K3仅可在 `.tmp/role-binding-summary-v1/kimi-k3/` 写候选、运行副本和证据。候选白名单：`web/workspace.js`、`web/index.html`；`tests/workspace_role_binding.test.cjs`仅更新必要预期并覆盖实际五角色/缺强度/自定义名等；`tests/workspace_initiator_mode_ui.test.cjs`与`tests/workspace_role_diagnostics_export.test.cjs`只同步资源版本断言，不改其余逻辑/保护断言。其它跨界先暂停。
- index现有本地静态资源版本统一改为 `20261019-role-binding-summary-v1`，不改资源顺序/依赖、样式或DOM；只为缓存失效更新引用，不改相应未变资源文件。
- 复用现有Node VM/DOM测试验证真实角色行、五角色结果、无强度不占位/无尾分隔、未知后缀和缺字段、自定义名称/文本转义、状态与原详情/搜索/只读边界。必要回归既有workspace相关测试及资源引用合同，无Browser/生产写/API/模型/服务动作。
- 交付实际候选、仅白名单差异的integration.patch、SHA/来源清单、集成说明、原始验证证据和进度草稿；完整talk-delivery-1裸JSON作为实际任务结果正文，实际任务号，先本地validate。测试/格式校验不等产品验收，正式合入与静态加载核验由Codex后续处理。
