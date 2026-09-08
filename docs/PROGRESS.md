# Project Progress

Updated: 2026-09-08 (Asia/Shanghai)

## Latest

- 本批分支整合已完成：本地主工作区在 `main`，功能基线为 `f223739`（PR #5 合并），其后只有本次交接文档提交。Codex 为决策 Agent；本轮结束，不开启新切片。
- 已验收 UI 经 PR #3 合入 task-hall（`3e2483d`），整条前置链经 PR #4 合入 main（`541e668`）；旧 PR #2 自动标记 merged。原 `5781ee6` 在稳定基线上 cherry-pick 为 `2a1d007`，经 PR #5 单独合入 main（`f223739`）。
- 用户确认 Codex 群聊实际回复正常，前述界面问题全部修正；任务 #15/#16/#17/#18 与 #19 均已人工验收完成。
- 下一阶段产品方向已确认：群聊统一头脑风暴、人工 / 终端 Agent 主持、按会议周期隔离、总结返回发起会议的原终端。完整约定见 [BRAINSTORM_NEXT.md](spec/BRAINSTORM_NEXT.md)，尚未实现。

## 已完成与验证

- 界面保留任务 / 群聊 / 角色导航、简短名称、当前项目邀请筛选、群成员单列表、桌面 80% 默认密度。Codex 普通终端可定位 Desktop 原生 CLI，启动时输出实际路径。
- 稳定基线：383 项非 WebSocket Python 测试、10 项逐一独立进程 WebSocket 测试、20 项 Node 测试通过。
- 首次完整单进程 discover 在 WebSocket 连接状态检查长时间阻塞；停止的仅是本轮测试子进程，随后拆分验证全部通过。未声称单进程全套通过，未修改功能或终止用户 bridge。
- TH-7a 集成后 13 项终端 / 任务工具测试通过，覆盖配置、stdio 目录、只读检查及隔离服务中的委派→提交→查询→收取。以现有 QA 身份从其它工作目录对真实服务执行 --check，返回 ok=true，项目及三角色正确。
- GitHub 两次功能合并后均比较文件树，与对应受测版本一致；未重复运行未改动的测试。真实服务没有新增任务、发送群消息或增删成员。
- TH-7a 是八个任务 MCP 工具与连接检查，尚未安装到用户具体终端客户端，也未完成该客户端真实模型任务验收。指南：[TERMINAL_MCP.md](guides/TERMINAL_MCP.md)。

## 下一步与已知边界

1. 新窗口在 `D:/claude-test/TALK` 的 main 继续。先读本快照、PROJECT_BRIEF 和 BRAINSTORM_NEXT，再规划会议轮次与原终端往返的最小切片。
2. 已确认规则：同项目同团队复用群，一个群同时一轮；无活动轮时人工 @所有人 开新轮，活动轮中属于追问；明确汇总结束，迟到回复及旧消息引用不能串轮。终端主持者就是用户原对话中的 Agent，不能产生两个独立主持人。
3. 当前普通群聊仍缺少完整连续上下文，回复按钮还不会自动提醒角色；新确认的会议语义及终端回传未实现。不要误认为合并 TH-7a 后这些能力已经具备。
4. 后续页面变化先给可查看预览。服务自动启动 / 管理和桌面客户端尚未实现；DeepSeek 模型由 Harness profile 切换，无需新角色。
5. 旧分支和 `.tmp/th7-terminal-v1` 工作树保留作原始切片记录。该旧工作树仍停在 5781ee6，已被新基线吸收，不要在那里继续开发或重复合并。

## 启动与交接

- 服务：`.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000`。入口 `http://127.0.0.1:8000/`；查看历史不要求所有 bridge 在线。
- 活动角色为 Codex / 官方 Kimi Code / DeepSeek Harness。实际运行服务仍沿用现有启动命令。
- 独立终端只读检查：先通过环境变量提供已有成员的 TALK_API_KEY，再执行 `.venv\Scripts\python.exe -X utf8 bridges/talk_terminal_mcp.py --project-root . --check`。不要把密钥提交到仓库。
- .tmp、真实数据库、日志、截图与旧工作树没有提交或清理。完整合并记录见 PROGRESS_HISTORY。
- 恢复指令：`继续项目`。本轮用户要求自行新开窗口，不自动创建其它任务。
