# Project Progress

## Latest
Updated: 2026-05-15 18:25 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `DOC-LANG-1` 已完成：已在 `AGENTS.md` 中加入 TALK 文档语言约定。
- 项目文档中的描述性内容应尽量使用中文；代码标识、命令、API 路径、配置键、协议名、库名、错误码、commit hash 等技术字面量可保留原始写法。
- 该规则适用于需求说明、设计说明、进度记录、验收说明、变更摘要和面向人阅读的解释文字。

### 3) Open Questions / Pending Confirmation
- Web UI 尚未接入 SSE stream；SSE 目前只提供实时只读事件，还没有 `Last-Event-ID` replay/backfill。
- Group 重命名/删除控制、未读/关注状态、文档编辑锁、schedule API、Codex bridge task-queue integration 仍待实现。
- Docker、Linux 部署路径和首次用户 dry run 仍属于未验证的环境任务。

### 4) Next Plan
1. 提交并推送本次文档规则切片。
2. 明天用 `继续项目` 恢复。
3. 推荐下一实现切片：Web UI SSE fallback/integration。

### 5) Verification
- 本次文档规则更新前，`git status --short` 为空。
- `git diff --check` 已通过，仅有换行提示。

### 6) Changed Files
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
