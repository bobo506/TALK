# 347 返修第二块：Codex 新角色准备与动态宿主

2026-10-27，Codex开发并自检；用户已确认采用官方默认思考强度并已落实，本块开发/自检完成。接续全运行器新角色准备范围，尚未生产集成或人工验收。

## 范围与行为

- 新建Codex角色配置成功后进入统一准备门禁；手动启动、项目自启动都须通过。没有新流程记录的旧角色保持原行为，不追溯要求登录。保存时不抢先自动启动尚未准备的新角色。
- 仅在该角色独立HOME下运行官方`codex login --device-auth`，`CODEX_HOME`固定为该角色的`.codex`目录。配置使用`cli_auth_credentials_store="file"`和`forced_login_method="chatgpt"`，不读取、复制其它角色或桌面的认证缓存，不回退到环境API Key。
- 页面向人类展示官方设备授权网址及一次性验证码；Codex网址限`https://auth.openai.com/codex/device`，原生输出不原样入库或展示。中断、取消、成功等终态清除授权网址和设备码；角色Key不能读取此接口。
- 复用上一块专属授权进程回执与Windows Job。重试先停止并确认旧授权流程退出，再启动替代；回执锁名支持Kimi/Codex白名单，未知归属不启动替代。管理范围仍只限本次授权自建进程。
- 官方登录进程成功退出后，仅通过原生app-server的`account/read`确认ChatGPT登录类型，`model/list`确认所选`model_id`存在。用户已确认使用官方模型目录返回的默认思考强度：每次新角色准备都读取该模型的`defaultReasoningEffort`，校验目录支持列表和当前原生适配器支持范围，再保存供实际执行使用；不从展示名称或原准备配置继承xhigh。官方默认值缺失或不受支持时明确失败，不选择其它强度。不改成其它模型，不创建thread或发起turn。
- 配置只保存公开的模型、提供商、认证存储方式和思考强度。写入前再次核查当前角色资格、模型绑定及停止状态，绑定变化拒绝写入。
- 新增单角色Codex动态宿主，复用现有HostManager的领取、实例、健康、停止和归属语义；限定项目/成员作用域，Key仍正常认证。静态旧宿主优先，不替换现有角色宿主。新角色默认review，只有逐成员显式配置才可tools；任务命令显式使用所选模型与沙箱，预检保持只读。
- 本机运行清单增加可选`codex`配方：显式`enabled`、原生CLI绝对路径`executable`和逐成员`task_profiles`。本轮只实现和合成验证此合同，没有写入真实本机清单。

## 官方合同与版本边界

- [OpenAI Docs：设备码登录和凭据存储](https://learn.chatgpt.com/docs/auth)：设备码方式需用户在ChatGPT安全设置或工作区权限中启用，并在官方页面输入验证码；不采用复制认证缓存方案。
- [OpenAI Docs：app-server账号与模型目录](https://learn.chatgpt.com/docs/app-server)：依据返回的模型和思考强度检查，不硬编码文档示例模型。
- 当前TALK既有原生适配器只支持`codex-cli 0.163.0`。本块沿用该边界，版本不符明确失败，不更新CLI。文档描述不作为本机已安装版本或账号能力的证据。
- 本块未增加终端MCP配置，不把动态宿主启动等同于当前客户端MCP等待、取消或排队适配通过。

## 冻结、测试及交付

- 工作根`.tmp/role-creation-codex-20261027/`；只改candidate，由上一块479项冻结另建副本。父manifest SHA256为`3f572a5a8705e1b62b748505bb3908fca81317b788f7edabc5d61f06f8b7f5e2`。
- 首版候选14项文件变化，新增5项，共484项`frozen-v1`；`delivery/final-manifest.json` SHA256为`1cc1efbf108293d5c25b256504e272eaf9872c43de8474b4a4d84f896697312e`，差异`delivery/codex.patch`。该版保留，答复后的最终规则在下方新副本实现。
- 首版候选联合331 Python、117 Node通过；冻结副本联合 **331 Python通过、0失败/错误/跳过，242.235秒**，前端 **117 Node通过、0失败/取消/跳过**。摘要`delivery/frozen-author-summary.json`，日志`frozen-author-independent-tests.log`、`frontend-frozen-tests.log`。这是用户答复前的首版记录，最终规则的验证见下。
- 最终`delivery/final-verification.json`核对父基线/上块冻结各479项、本块候选/冻结各484项、原347基线474/原候选476/首次复核476/原交付10份，均无漂移；合成配置已移除。只声明清单路径校验，不把生成测试目录冒称完全为空。测试只使用合成配置、私有临时库、假CLI/RPC、loopback及自建固定文本进程。
- 中途测试失败保留：新增Python夹具未显式关闭SQLite连接而影响临时目录清理、宿主测试仍断言Kimi环境变量、非人类页面测试对空面板取内容；修正相应夹具/断言后定向通过，不称过程始终全过。

## 用户确认后的默认强度规则

用户明确答复“使用官方模型目录返回的默认思考强度”。TALK公开绑定仍保留既有`gpt-6.1-sol · xhigh`等展示名称，不追改旧角色；新角色准备和执行参数按官方返回值确定。新角色创建页和准备详情明确说明官方默认规则，准备详情优先显示规范model_id，避免把旧名称中的xhigh展示成新角色本次执行参数。

- 从首版484项冻结另建`.tmp/role-creation-codex-default-20261027/`；只改新candidate的4项文件：模型准备实现、对应Python测试、新角色页面及对应Node测试。首版冻结不回改。
- 新484项冻结manifest SHA256为`6e543560e74043ce533efbb1dfc4b8c4d73635d7176d5479444de22e90415844`，清单`delivery/final-manifest.json`，差异`delivery/default-effort.patch`。
- 新增/调整验证覆盖：即便原配置为xhigh仍采用官方默认、实际落盘为返回值、分页读取、默认缺失不回退、不支持的默认拒绝、页面规则及旧名称不误导。
- 最终冻结副本联合 **333 Python通过，0失败/错误/跳过，254.718秒**；前端 **118 Node通过，0失败/取消/跳过**。摘要`delivery/frozen-author-summary.json`，日志`frozen-author-independent-tests.log`、`frontend-frozen-tests.log`；包含并复用前序用例，不与331/117重复累加。
- `delivery/final-verification.json`核验新候选/新冻结/父基线/前版Codex冻结各484项、核心冻结479项、原347的474基线/476候选/476首次复核/10份交付，均无漂移；合成配置移除。本块实现及自检闭合，整体347及真实登录/模型/生产加载不由这些结果推定完成。

## 后续与限制

本块完成后，DSH的已有模型连接服务端引用、动态宿主及WorkBuddy等其余新角色准备仍须逐块接入，然后整体联调、正常收取347、准备加载和人工验收。原347/2993尚未收取；原347交付、核心首块冻结及首次独立不通过的事实保留。

本轮没有读取真实Key、原生HOME、私有会话/日志或生产数据库，没有真实登录/模型调用，没有生产源码集成、启停、绑定/偏好修改或公共仓库推送。单块自检不代表全运行器或真实端到端验收完成。
