# 后台自动日志清理：待确认的正式启用方案

## 已完成的代码验收

2026-10-23用户通知318完成后，Codex核验33份冻结、原317证据未改、318结果2959与本地JSON一致；DeepSeek独立132回归/27新测试/5原反例/27复核侧反例通过，F1—F5/P1全部关闭。318已收取。取件后仅按复核建议澄清合同“新增事件”措辞，未再改产品代码。

额外真实API加载自检通过：正式lifespan启动后台worker，真实隔离SQLite任务闭环，自动删除40天旧事件，详情HTTP410，未认证401/agent403，近期/活跃保留，持久daily due，API关闭worker正常停止。测试端口59899，非生产8000；记录在`.tmp/local-log-auto-retention-v1/coordination/api-smoke/`。这不替代生产验证。

## 只读核对的部署事实

- 当前storage.db_path为`./talk.db`，解析到现有`D:/claude-test/TALK/talk.db`；本片enabled门禁要求绝对路径。
- 当前只有五个已登记来源范围，分别为DeepSeek、Codex和三个Kimi成员，project均为`prj_e8fe7066bbec`。其root指向各成员子目录，而writer的根是`D:/claude-test/TALK/logs/runtime`。
- 全根清理按member/instance/run三层布局遍历，policy也必须在writer根生效；不能直接在成员子目录开启，否则无法正确遍历/协调writer。拟将五个root统一为原总根，保留这五对(project,member)，不新增WorkBuddy/其它成员范围。
- 当前统一宿主running，API为external（由用户原终端运行）。无法通过受管reload-api重载外部API，不按PID强杀/接管它。
- 当前无runtime_log_retention配置，生产仍未启用；未写root policy、未删除生产日志、未启停角色/宿主/API。

## 准备好的配置差异

`.tmp/local-log-auto-retention-v1/coordination/deployment-config.patch`只包含以下差异，内存中已解析验证与原配置相比恰为这些字段；没有保存完整私有配置副本：

1. storage.db_path改为同一文件的绝对路径`D:/claude-test/TALK/talk.db`，不复制/迁移DB。
2. 五条已登记runtime_diagnostics.sources的root改为`D:/claude-test/TALK/logs/runtime`，项目/成员不改；provider仍按精确project/member过滤，新增的其它成员目录不因此获授权。
3. 新增：

```toml
[runtime_log_retention]
enabled = true
retention_days = 30
max_total_bytes = 1073741824
interval_seconds = 86400
```

原配置SHA256为`b839cdea0ddfe0dd97e91af7ced2825da4557c7af8c2ed307095568d8d7bdc3f`，仅用作未来防止覆盖期间变更的CAS基线；实际应用前须重新核对。这里只准备差异，尚未应用。

## 确认后按正常流程加载

1. 核各角色任务/持有状态并记住原running/stopped集合；有工作未结束时不强停或解除owner。
2. 通过原统一入口正常停止并drain宿主/角色，确保旧producer不再执行旧期限/容量删除。使用原归属/Popen流程，不用旧PID判定或强制CAS。
3. 应用上述最小配置，保留其它配置、模型/Key/绑定/历史。用户在启动API的原终端Ctrl+C后重新运行原命令一次；新版API将按既有绑定启动新宿主。
4. 普通start恢复原先运行的角色，原本停止的保持停止。验证新writer lease/关闭证据、根policy、后台持久due/摘要、五范围隔离与角色健康。
5. 生产没有已关闭且超过30天的可信run时，删除0个也是正确结果；不修改历史时间/伪造closed来制造删除证据。旧/未知/空任务run仍保护，1GiB软预算不能越过它们。
6. 记录实际加载与保护结果，必要独立部署复验优先沿318的同一原生会话请求，仍服从60%/失效守卫；不据一次启动声称30天长期容量验证完成。

## 确认及回退边界

本方案涉及生产配置和服务重载，按AGENTS“涉及新的部署/权限/破坏性处置时，仍提交具体可审结果后确认”要求，在用户确认前不执行。日常自动清理不要求用户逐次批准；这里是本片首次部署确认，不是新增前台流程。

若加载失败，停用新worker并恢复本次配置字段；不删除已写policy/lease/关闭/审计痕迹来强行恢复旧删除，不回填历史，不强制解除owner，按实际失败证据处置。启用后的writer会保守服从已有根policy，即使worker停用也不自动重开旧破坏性策略。

317原partial保留；自动审批拒绝其收取，理由是旧“暂不收取”要求及用户本次仅确认318。只有另获明确授权才处理该待收取状态，报告/失败内容始终不改。此事不阻止318代码验收通过。
