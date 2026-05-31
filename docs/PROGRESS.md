# Project Progress

## Latest
Updated: 2026-05-31 19:41 (Asia/Shanghai) — docs 目录整理：spec / guides 分层

### 1) Current Agent Role
- Codex：按本轮用户明确授权执行文档整理切片
- 角色依据：用户要求实现已确认的 docs 文档目录整理方案

### 2) Current Progress
- 已将 `docs/` 从平铺结构整理为锚点文档 + 高频分类目录。
- `docs/PROJECT_BRIEF.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md` 保持在 `docs/` 根目录，保证 agent 恢复流程稳定。
- 新增 `docs/spec/`，承载产品说明、模块 spec、SDK/API 契约和阶段设计文档。
- 新增 `docs/guides/`，承载快速启动、用户/Agent 指南和部署说明。
- 暂未创建 `iterations/`、`validation/`、`milestones/` 空目录，等产生真实文档后再建。

### 3) Path Updates
- `PRODUCT.md`、`SDK.md`、`LOCAL_LAB_DESIGN.md`、`MODULE_*.md` 已移入 `docs/spec/`。
- `QUICKSTART.md`、`QUICKSTART_USER.md`、`QUICKSTART_AGENT.md`、`DEPLOY.md` 已移入 `docs/guides/`。
- 已同步更新 `PROJECT_BRIEF` 模块索引、目录树、README 入口链接、AGENTS/CLAUDE 模块文档指引和历史进度中的旧路径引用。

### 4) Verification
- Run: `rg` 旧路径模式搜索
- Result: 未发现计划关注的旧路径模式残留
- Run: Markdown 本地链接校验
- Result: 通过
- Run: `git diff --check`
- Result: 通过；仅有既有 Windows 换行提示
- Not run: 后端测试，本切片仅移动和修正文档

### 5) Changed Files
- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
- `docs/spec/*`
- `docs/guides/*`

### 6) Next Plan
1. 继续原 5.5 P0 后续：重启 pi bridge + pi-kimi bridge 后跑黑盒测试，验证身份幻觉、消息风暴、重复发起是否已修复。
2. 后续出现真实迭代计划、技术验证报告或里程碑验收材料时，再分别创建对应目录。

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
