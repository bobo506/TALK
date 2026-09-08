# Project Progress

Updated: 2026-09-08 (Asia/Shanghai)

## 当前状态

- 当前 Codex 为决策 Agent。主工作区在 `codex/ui-workspace-v1`，PR #3（base `codex/task-hall`）：https://github.com/bobo506/TALK/pull/3 。本批完成用户验收反馈修复，等待复验，不开启新切片。
- 用户已验收任务 #19：DeepSeek 回复“验收通过”，确认成果后完成。#15/#16/#17/#18 仍为已完成、已验收基线。
- 新建/添加群成员按当前项目角色筛选，自己不进入邀请或 @ 候选，名称简短。右侧统一“群聊成员”，添加/管理按需展开。当前登录 QA Tester，bobo 是其他真人账号；旧 pi 不再作为项目邀请候选，历史数据保留。
- Codex 群聊失败源于 npm CLI 0.144.4 不支持所选 gpt-6-astra；默认优先 PATH 原生 codex.exe，现有 0.153.4 实测返回 TALK_CODEX_PROBE_OK。现有 Codex bridge 进程必须重启才能加载修改，群聊端到端回复仍待用户复验。
- UI 保留任务 / 群聊 / 角色导航、主任务归组、成果/下一步优先、任务要求折叠，以及桌面 80% 默认密度。资源版本 `20260908-members-2`。

## 验证与边界

- 本批 Node 20 项、Python 页面与 bridge 137 项通过，JS 语法与 diff 检查通过；没有重跑全量后端测试。
- 内置浏览器实测邀请候选、@ 自己排除与成员 ID 插入、管理展开/收起、添加表单可见性。1440px / 390px 没有横向溢出，控制台未捕获错误。
- 没有替用户发送群消息、创建群聊或增删真实成员，也没有重启用户运行中的 bridge。CLI 真实探针只请求固定文本，不使用工具。
- UI QA 见 `design-qa.md`；截图在 `.tmp/group-members-20260908/`，不提交截图、数据库、日志或临时文件。

## 独立下一切片

- 用户已授权复制分支并开发最小 TH-7：工作树 `.tmp/th7-terminal-v1`，分支 `codex/th7-terminal-v1`，提交 `5781ee6`，本地完成、未推送。
- 已有普通终端 MCP 入口和 `--check`，13 项测试通过；指南在该工作树的 `docs/guides/TERMINAL_MCP.md`。不要重复开发或混入 UI PR。
- UI 合并后再对齐 TH-7；若采用 squash，只迁移从 `6affa86` 起的 TH-7 增量，避免重带界面历史。

## 下一步

1. 用户刷新 `http://127.0.0.1:8000/?ui=members-final-2` 检查邀请、@ 和右侧群聊成员；在 Codex bridge 原终端 Ctrl+C 后重跑原启动命令，再 @ Codex 验证正常回复。DeepSeek/Kimi 无需因本次 Codex 修复重启。
2. 复验通过后整理 PR #3 及其前置分支链。此前核对 `codex/task-hall` 比 `main` 领先 64 个提交，旧 PR #2 head 是其祖先；尚未获授权自动合并或关闭 PR。
3. 收尾 UI 基线后再继续独立 TH-7。桌面客户端尚未开始。
4. 恢复指令：`继续项目`。先核对本工作区和独立 TH-7 工作树，保留已完成验收与修复。

## 启动与参考

- 服务：`.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000`。
- 活动角色：Codex / DeepSeek Harness / 官方 Kimi Code CLI。查看历史无需启动所有 bridge。
- 项目简报 `docs/PROJECT_BRIEF.md`；模块 `docs/spec/MODULE_webui.md`、`docs/spec/MODULE_bridges.md`；完整记录 `docs/PROGRESS_HISTORY.md`。
