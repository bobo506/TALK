"""C1b-S2 角色页唯一项目主控指定：页面契约测试。"""

from pathlib import Path

from tests.test_support import RouteTestCase


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_VERSION = "20260919-c1b-s2-owner"


class ControllerWebUiTests(RouteTestCase):
    def test_homepage_exposes_project_controller_panel(self):
        with self.make_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.text
        for element_id in (
            "controller-panel",
            "controller-current",
            "controller-detail",
            "controller-clear-btn",
            "controller-retry-btn",
            "controller-status",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('aria-label="项目主控"', html)
        self.assertIn('role="status"', html)
        # 语义文案：长期保存、人工解除、离线不自动解除、assigned 不冒充在线/已确认/生效，
        # 且不改变现有派发/领取/完成/收取权限。
        self.assertIn("指定长期保存，直到人工解除后另选，离线不会自动解除", html)
        self.assertIn("不代表在线、已确认或会话已生效", html)
        self.assertIn("派发 / 领取 / 完成 / 收取权限", html)
        self.assertIn("解除主控", html)
        # 项目级面板位于开发要求编辑区之后、角色详情之前，不遮挡其它区域。
        self.assertLess(html.index('id="requirements-panel"'), html.index('id="controller-panel"'))
        self.assertLess(html.index('id="controller-panel"'), html.index('id="role-details-panel"'))
        # 静态资源版本同步刷新缓存。
        self.assertEqual(html.count(STATIC_VERSION), 4)
        self.assertNotIn("20260918-role-1", html)
        self.assertNotIn("20260918-req2-rework", html)
        # #114：旧版本不得以完整缓存串残留（新串含旧串前缀，需带终止引号判定）。
        self.assertNotIn('v=20260919-c1b-s2"', html)
        self.assertNotIn("20260919-c1b-s2-focus", html)
        # #114 R1：面板状态行 tabindex=-1，作为解除成功后的稳定可聚焦目标（仅程序化聚焦，不进 Tab 序）。
        self.assertIn('<p id="controller-current" class="controller-current" tabindex="-1">', html)

    def test_controller_script_contract(self):
        script = (PROJECT_ROOT / "web" / "workspace.js").read_text(encoding="utf-8")
        app_script = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        stylesheet = (PROJECT_ROOT / "web" / "workspace.css").read_text(encoding="utf-8")

        start = script.index("// ── C1b-S2 项目主控指定")
        end = script.index("function workspaceTaskNotice(")
        block = script[start:end]

        # 专用写入口：不用普通项目 PATCH 写主控；整份前端只有这一处写主控。
        self.assertIn("/controller-assignment`", block)
        self.assertIn('method: "PATCH"', block)
        self.assertIn("JSON.stringify({ member_id: targetId, expected_version: expected })", block)
        self.assertEqual(script.count("/controller-assignment`"), 1)
        self.assertNotIn("/controller-assignment", app_script)
        # expected_version 原样来自上次读取，不自己 +1；JS number 无法安全表示时禁止发送。
        self.assertIn("const expected = controllerUI.version;", block)
        self.assertNotIn("expected_version: expected + 1", block)
        self.assertIn("Number.isSafeInteger(controllerUI.version)", block)
        # 状态机与降级：六种已知状态 + 未知状态无法识别，不虚构成功。
        for status in ("unassigned", "assigned", "not_in_roster", "member_disabled", "member_missing", "not_agent"):
            self.assertIn(status, block)
        self.assertIn("指定状态无法识别", block)
        # 409/400 只重读不自动重试写：PATCH 调用点只有一处。
        self.assertIn("res.status === 409", block)
        self.assertIn("rereadControllerState(projectId, memberId)", block)
        self.assertEqual(block.count("apiFetch(`/api/projects/${encodeURIComponent(projectId)}/controller-assignment`"), 1)
        # 读取/保存响应校验项目+账号+请求代次。
        self.assertIn("projectId === activeProjectId", block)
        self.assertIn("memberId === myId", block)
        self.assertIn("request === controllerUI.request", block)
        self.assertIn("data.project_id !== projectId", block)
        self.assertIn("data.controller_member_id !== targetId", block)
        # 旧后端缺字段明确不支持，不当成未指定。
        self.assertIn('!("controller_member_id" in data)', block)
        self.assertIn("当前服务尚未支持项目主控指定", block)
        # S1 竞态：200 但配置无效时如实提示，不宣告已就绪。
        self.assertIn("已保存，但当前不可用", block)
        for forbidden in ("已就绪", "主控已生效", "已接管"):
            self.assertNotIn(forbidden, block)
        # REQ-2 隔离与其它边界：不碰开发要求字段/普通项目字段、localStorage、innerHTML；
        # 不引入租约/token/epoch，不自动指定 lead/Codex，不从 business_role 推导。
        self.assertNotIn("development_requirements", block)
        self.assertNotIn("localStorage.", block)
        self.assertNotIn("innerHTML", block)
        self.assertNotIn("lease", block)
        self.assertNotIn("epoch", block)
        self.assertNotIn("business_role", block)
        self.assertNotIn('"agent:codex"', block)
        # 列表/详情同步与消歧：徽标、摘要与 member_id 辅助。
        self.assertIn("workspaceControllerSummary()", script)
        self.assertIn("workspaceControllerBadge(role.member_id)", script)
        self.assertIn("workspaceControllerEntry(role)", script)
        self.assertIn("role.member_id", script)
        # 可见性统一由 renderTaskDetailsPanel 同步；刷新复用既有生命周期，不新增 timer。
        details_fn = app_script[app_script.index("function renderTaskDetailsPanel()"):app_script.index("async function openTaskHall(")]
        self.assertIn("renderControllerPanel();", details_fn)
        refresh_fn = app_script[app_script.index("async function refreshProjectWorkspace()"):app_script.index("function renderProjectStrip()")]
        self.assertIn("reloadControllerAssignment();", refresh_fn)
        self.assertNotIn("setInterval", block)
        # #114 R1：焦点去向 —— 同动作按钮优先，指定成功落到“解除主控”，否则落到稳定面板状态行；
        # 不把焦点放到 hidden/disabled 节点。
        self.assertIn("function controllerFocusable(node)", block)
        self.assertIn("function controllerFocusTarget(action)", block)
        self.assertIn('document.querySelector(\'[data-controller-action="clear"]\')', block)
        self.assertIn('controllerEl("controller-current")', block)
        self.assertIn('classList.contains("hidden")', block)
        # #114 R2：离开角色页或黑板关闭后，迟到响应只维护状态，不重绘列表/角色详情、不抢焦。
        self.assertIn('const inRoles = blackboardOpen && workspaceUI.mode === "roles";', block)
        sync_fn = block[block.index("function syncControllerViews()"):block.index("function reloadControllerAssignment()")]
        self.assertIn("if (inRoles) {", sync_fn)
        self.assertLess(sync_fn.index("if (inRoles) {"), sync_fn.index("renderWorkspaceList();"))
        self.assertIn("document.body", sync_fn)
        # #116 F1：保存状态按请求所有权（独立 token）清理，不用会被 409/400 内部重读递增的
        # 请求序号当所有权；上下文切换重置时一并作废旧保存的所有权。
        self.assertIn("saveToken: null", block)
        self.assertIn("controllerUI.saveToken = saveToken;", block)
        self.assertIn("controllerUI.saveToken === saveToken", block)
        self.assertIn("contextAlive() && ownsSave()", block)
        # #116 F2：焦点记忆绑定保存发起时选中的角色；保存期间切到其它角色行即取消回焦意图。
        self.assertIn("role: workspaceUI.selectedRole", block)
        self.assertIn("memory.role === workspaceUI.selectedRole", block)
        # 样式复用浅色工作台并含窄屏覆盖与可读禁用样式。
        self.assertIn("#controller-panel", stylesheet)
        self.assertIn(".controller-status", stylesheet)
        self.assertIn(".role-controller-badge", stylesheet)
        self.assertIn(".role-controller-section", stylesheet)
        self.assertIn("@media(max-width:700px)", stylesheet)
