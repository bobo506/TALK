# Project Progress

## Latest
Updated: 2026-06-07 21:52 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前分支：`codex/web-ui-feature`，基于 `codex/local-lab-codex-bridge`。

### 2) Current Progress
- `WEB-WORKBENCH-REDESIGN-1` 已完成第一版：按 Product Design 方向把 Web UI 从横向工具条聊天页重构为“多 Agent 协作工作台”。
- 主界面改为左侧 `Hall 控制台` + 右侧消息时间线：左侧承载全局 / Group Hall 切换、新建 Group、成员面板和在线成员状态；右侧承载历史搜索、消息流和 composer。
- 保留现有 DOM id 与前端行为契约，不改 API，不引入框架或构建链。
- 视觉系统从单一深蓝收敛为中性暗色工作台，辅以 teal / indigo / amber 状态色，保留 8px 控件圆角与密集操作布局。
- 顺手修正 highlight.js 浏览器脚本路径，避免 `lib/common.min.js` 在浏览器中触发 `require is not defined`。
- 静态资源版本号更新为 `20260607-workbench-redesign`。

### 3) Open Questions / Pending Confirmation
- 本轮是页面结构与视觉基线第一版，尚未新增 discussion session/turn、任务队列或实例状态面板等新功能入口。
- 左侧 Hall 列表在 Group 很多时会独立滚动；后续可继续做分组、未读/关注状态或归档入口。
- 当前 Browser 验证使用本地已有 human API Key 登录，仅做视觉和布局检查；未做完整发消息/建群/成员管理回归。

### 4) Next Plan
1. 请项目管理者人工查看新版 Web UI 的整体方向。
2. 若方向认可，下一切片可继续补“讨论/任务/实例状态”的可视化信息区。
3. 若希望更偏家庭聊天，可回调左侧工作台密度；若希望更偏 Agent Ops，可继续强化状态、轮次和任务面板。

### 5) Verification
- `python` HTML nesting check：通过。
- `git diff --check -- web\index.html web\style.css`：通过，仅有 Windows LF/CRLF 提示。
- Browser 桌面验证：`http://127.0.0.1:8000/` 登录后左侧控制台、右侧时间线、composer 正常渲染，无横向溢出。
- Browser 移动验证：390x844 viewport 下无横向溢出，工作台切为单列，控制台、搜索区、消息区和输入区可见。
- Browser 资源检查：页面已加载 `highlightjs/cdn-release@11.11.1/build/highlight.min.js`，替换旧的 `highlight.js/lib/common.min.js`。

### 6) Changed Files
- `web/index.html`
- `web/style.css`
- `docs/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
