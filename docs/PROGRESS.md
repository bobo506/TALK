# Project Progress

Updated: 2026-09-10 (Asia/Shanghai)

## Latest

- 本轮仅完成第一项“查看成果再次点击收起”，等待用户验收；第二项“完整对话移除右侧重复任务信息栏”未改，按用户要求一项一项来。
- 当前Codex为决策Agent，负责派发/复核/文档；用户本轮指定官方Kimi Code实际开发，使用tools任务profile。DeepSeek仍跟随DSH保存的默认模型，无任务级模型选择。
- 实际代码开发链路：TALK #21在600秒后失败留下局部改动；Codex复核后派发同一切片续办#22，Kimi成功返回，Codex独立验证并收取为completed。#21失败记录保留；#22不是第二项功能。
- 当前分支 `codex/ui-result-toggle`，从main/8197ce9开始；功能基线f223739。本轮改动保存于此独立分支，尚未合并main。远端收尾状态见下方，不要重复派发#22。

## 已完成与验证

- 成果按钮显示“查看成果 / 收起成果”，支持加载中关闭、再次展开；上下文切换与关闭使旧请求失效。补aria属性，保持原权限和文件/撤回/错误呈现。
- Codex独立执行32项Node、2项Python页面测试、两份JS语法和diff检查通过；没有重跑全量后端。
- 真实页面#19展开/收起/再展开、Enter/Space、刷新保持状态、#19与#9切换、空项目往返及#20无权限提示通过。当前浏览器实际379×577，宽屏与真实账号切换未补测；异步竞态与账号变化由行为测试覆盖。详情见design-qa.md。
- Kimi修改5份代码/测试文件；Codex同步用户手册、webui模块和进度记录。临时预览、.tmp、数据库、日志、密钥、用户配置不提交。未启停用户服务。

## 当前验收与下一步

1. 刷新 http://127.0.0.1:8000/ ，用已有账号选一个有权限且已有成果的任务，连续操作“查看成果 → 收起成果 → 查看成果”；切换任务/项目后应恢复收起。已启动服务无需重启。
2. 用户验收第一项后，再单独预览/派发Kimi处理完整对话右侧重复信息栏；本轮不自动继续。
3. 角色列表历史idle/busy心跳误报在线仍未修复，派发前核对真实bridge。Kimi本次长任务达到600秒后不会自动恢复；短续办成功，执行超时与恢复策略尚未改进。
4. 会议方向继续见docs/spec/BRAINSTORM_NEXT.md：同项目同团队复用群、一群一活动轮、人工/原终端主持、明确汇总结束并返回原终端。尚未实现；任务#20的草案须先解决legacy scope与引用兼容。
5. 普通群聊完整连续上下文、回复自动提醒、服务管理/桌面客户端仍未完成，不与本轮小修混做。

## 启动与交接

- 项目根D:/claude-test/TALK；服务 `.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000`。本地角色Codex / 官方Kimi Code / DeepSeek Harness。
- TALK本地stdio MCP已实测，以human:bobo派发。桥接命令与配置见docs/guides/TERMINAL_MCP.md及现有启动指南；密钥不入库。
- #20 DeepSeek只读试运行已completed；#22 Kimi开发成果已completed。不要把#21失败当作未完成而重复整项。
- 第一项受测版本已本地提交 `37d88c7`。gh查询PR返回HTTP401；推送 `origin/codex/ui-result-toggle` 被自动审批拒绝，原因为未明确授权向具体远端 `https://github.com/bobo506/TALK.git` 发送非公开代码/文档。未推送、未创建PR、未绕过；等待用户明确授权该目的地。人工验收前不合并main。
- 旧.tmp/th7-terminal-v1等工作树保留，不在旧基线上续开发。完整历史见PROGRESS_HISTORY.md。恢复指令：`继续项目`。
