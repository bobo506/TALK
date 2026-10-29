# 绑定重置页面等待状态修复（2026-10-29）

## 问题与修正

用户报告小K绑定重置多轮修复后仍停留在“等待宿主”。本轮由 agent:codex 本人处理，用户明确授权最小配置路径/健康读取、本机认证在内存查询接口及小K必要运行验收；未派发开发任务。

实际检查发现旧交接的路径分歧已经被后续操作修正：小K宿主与 worker 均使用同一个私有 Key 路径。最新既有恢复请求 `role-d32ae14cb48af4c790686466a9de454c` 于 20:30:27 已成为 `provisioned`，凭据代际仍为 2、预检成功。但浏览器仍显示等待和“恢复结果尚未确认”。

浏览器真实错误为 `TypeError: Illegal invocation`，堆栈指向 `schedule` 中的 `deps.setTimeout`。页面入口直接把 Window 定时器保存为依赖对象的方法，调用时接收者变成 deps，导致自动刷新中断。修正入口为显式 `window.setTimeout` / `window.clearTimeout` 包装，并更新静态资源版本以避免旧页面脚本缓存。

本轮没有修改后台恢复合同、身份、模型、Key 文件或生产运行配置，也没有停止后台或其他角色。旧失败请求保留。

## 验证

- 隔离候选及原始基线：`.tmp/binding-reset-timer-20261029/`；集成前逐文件 SHA-256 核对无漂移。
- 新增从真实页面入口加载的回归测试，要求定时器保持 Window 接收者，覆盖恢复成功、失败自动刷新和离页取消定时器。修复前失败证据保留 `evidence/before.txt`。
- `node --test tests/workspace_role_creation.test.cjs tests/workspace_role_creation_integration.test.cjs tests/workspace_role_catalog.test.cjs tests/workspace_role_services.test.cjs`：101 项通过。
- `python -B -X utf8 -m unittest tests.test_role_creation_web_ui -v`：3 项通过，候选使用独立测试配置/数据库/日志，没有连接生产数据库。
- `node --check web/role-creation.js` 通过；最终差异及新增行空白检查通过。
- 真实浏览器加载新版后，既有成功请求不再显示“等待宿主”。新一次按钮点击已打开确认框，但浏览器控制在确认框超时，原生工具报告窗口最小化；已请用户恢复窗口并确认。**新一次真实点击到自动完成的验收仍待完成，不能由104项测试外推。**

## 验收入口与边界

已运行的本机 TALK：`http://127.0.0.1:8000/`，使用现有真人账号进入“角色 → 小K → 绑定重置”，确认后等待页面自动更新。无需新增账号、获取 Key 或重新模型登录。完成后等待提示消失；角色保持关闭，启动需另点启动。失败应显示实际错误，不应永久停留在旧等待状态。

本轮为本人自检，不冒称独立复核。Git/GitHub 按用户要求留给 DeepSeek，本轮未执行提交或推送；尚未派发 Git 收尾。
