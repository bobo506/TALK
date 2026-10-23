# Project Progress

Updated: 2026-10-23 09:58（Asia/Shanghai）。本轮按用户验收反馈，优先修复重启电脑后角色启停卡住，并缩小改名按钮。当前代码/正式文档已完成，Git收尾随本轮提交；页面操作待用户复验。

## 当前职责与范围

- 当前Codex `agent:codex / prj_e8fe7066bbec / lead` 直接实施、自检与收尾，未派DeepSeek/Kimi或子代理，不称独立复核。下一无关切片先确认；Kimi常规开发暂停、286暂停保持。
- 按钮34×34→17×17，面积约原1/4；图标12px，与名称居中对齐。前端版本 `20261023-role-control-v4`，当前实际HTTP资源与源码SHA一致，真实视觉/点击交用户验收。

## 已完成与证据

- 已绑定本机清单/精确数据库后，从原终端启动API会恢复独立宿主与配置worker；原生角色仍按human启动/关闭，不批量启动模型。绑定文件 `.talk/runtime.local.json` Git忽略，不含Key；隔离数据库不能启动生产宿主。
- 启动超时GET不再永久starting；无owner可重试，已有owner保持。human明确点击关闭时，针对本机原宿主/实例/进程做双次证明及原恢复CAS审计；活进程/未知/活动任务/替代进程仍拒绝，后台/GET/Agent不解除归属。旧幂等关闭回执兼容与关闭后资格刷新已补。
- 本次三个遗留owner（Codex/DSH/新WorkBuddy）已逐项恢复。OS确认DSH旧PID被系统进程复用，使用本次开机/创建时间区分原进程，未接管或结束复用PID。旧K2.8原清单引用不存在的Key文件，正式反查原本人Key后只修正该宿主role-key-file路径；不复制/重签Key，不改模型/绑定。
- 相关115项Python回归通过；最后31项宿主/真实隔离API重启/本地恢复/PID专项和37项Node通过，语法/差异检查通过。七角色全部实际启动ready、实例心跳与普通关闭通过；三个代表角色35秒周期心跳推进。详[本片记录](spec/ROLE_START_REBOOT_FIX_20261023.md)，证据 `.tmp/role-start-reboot-fix/`。

## 最近现场与保护项

- 本轮最终核验：runtime12856为external API附加模式，七宿主serving；七原生角色均stopped/no owner/can_start=true，供页面逐一启动。宿主包装器4196与API包装器14684不在Job；解释器venv Job单字段不作外层归属证明。
- 314条原任务逐行SHA、286暂停、项目名称“小C/小D/小K”等、全部原模型/绑定与config.toml保持；消息最大ID2955保持，无旧私信回放。旧K2.8本人Key mtime保持；私有运行清单仅该Key文件路径纠正。
- 外部API仍由用户原终端管理；正常重启保留宿主，不能用reload-api接管外部API。需API也独立运行时按[统一启动](guides/TALK_RUNTIME.md)正常切换，不安装开机任务/服务。未实际再重启电脑或结束聊天后复查，不能将本轮采样称跨会话/开机驻留最终验收通过。

## 下一步与人验

- 请用户Ctrl+F5刷新，检查缩小后的改名按钮及七角色启动/关闭，确认已关闭后再次启动可用；原名称已保留。API已由用户正常重启加载核心修复，当前无需再重启角色或重做登录。
- 本轮基线 `adbeb5d`，本轮交付以Git提交为准。人验未通过时在本授权范围继续直接修正；无关新片先明确范围并确认。历史见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
