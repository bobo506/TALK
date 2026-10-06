"""C1b-S2 角色页唯一项目主控指定：页面契约测试。"""

import re
from pathlib import Path

from tests.test_support import RouteTestCase


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_VERSION = "20261006-controller-mode-c2b-ux"


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
            "controller-assign-row",
            "controller-candidate-select",
            "controller-assign-btn",
            "controller-clear-btn",
            "controller-retry-btn",
            "controller-status",
        ):
            self.assertIn(f'id="{element_id}"', html)
        # ROLE-SETTINGS-1：指定走面板候选选择器 + 设为按钮（带动作标识供焦点解算）
        self.assertIn('aria-label="选择要设为项目主控的角色"', html)
        self.assertIn('id="controller-assign-btn" type="button" class="room-primary-btn" data-controller-action="assign">设为项目主控</button>', html)
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
        self.assertLess(html.index('id="controller-panel"'), html.index('id="role-details-name-panel"'))
        # 静态资源版本同步刷新缓存。
        self.assertEqual(html.count(STATIC_VERSION), 4)
        self.assertNotIn("20261005-role-desc-f2", html)
        self.assertNotIn("20260923-manual-task-cleanup-1", html)
        self.assertNotIn("20260919-c1b-s2-owner", html)
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
        self.assertIn("role.member_id", script)
        # ROLE-SETTINGS-1：主控管理集中在“项目设置”页；逐角色管理入口（workspaceControllerEntry）已移除。
        self.assertNotIn("workspaceControllerEntry", script)
        # 候选选择器：名册候选、签名不变不重建、写请求始终用 select.value 的 member_id。
        self.assertIn("function syncControllerCandidates(select, candidates)", block)
        self.assertIn('controllerEl("controller-candidate-select")', block)
        self.assertIn("saveControllerAssignment(select.value)", script)
        # 已有指定时不再提供候选指定入口，详情显示先解除理由。
        self.assertIn("请先解除当前指定，再另选", block)
        # 面板可见性绑定“项目设置”选中态，与具体角色互斥。
        self.assertIn("workspaceSettingsSelected()", block)
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
        # ROLE-SETTINGS-1：焦点记忆绑定项目/账号；保存期间切到具体角色或离开设置页即取消回焦。
        self.assertIn("controllerFocusMemory = { action, projectId: activeProjectId, memberId: myId }", block)
        self.assertIn("const inSettings = inRoles && workspaceSettingsSelected();", block)
        # 解除成功后焦点落到可见候选选择器（下一步是另选），再到稳定状态行。
        focus_fn = block[block.index("function controllerFocusTarget(action)"):block.index("// 读取/保存完成后刷新列表徽标")]
        self.assertIn('controllerEl("controller-candidate-select")', focus_fn)
        # 样式复用浅色工作台并含窄屏覆盖与可读禁用样式。
        self.assertIn("#controller-panel", stylesheet)
        self.assertIn(".controller-status", stylesheet)
        self.assertIn(".role-controller-badge", stylesheet)
        # ROLE-SETTINGS-1：角色详情管理面板样式随入口一并移除；设置首项与候选选择器有新样式。
        self.assertNotIn(".role-controller-section", stylesheet)
        self.assertIn(".role-settings-row", stylesheet)
        self.assertIn(".controller-assign-row", stylesheet)
        self.assertIn("@media(max-width:700px)", stylesheet)


class ControllerModeWebUiTests(RouteTestCase):
    """C2-B 项目设置页“调度模式”面板 + 角色详情“参与任务”单分隔线：页面契约测试。"""

    def test_homepage_exposes_controller_mode_panel(self):
        with self.make_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.text
        for element_id in (
            "controller-mode-panel",
            "controller-mode-saved",
            "controller-mode-effective",
            "controller-mode-options",
            "controller-mode-passive",
            "controller-mode-active",
            "controller-mode-save-btn",
            "controller-mode-retry-btn",
            "controller-mode-status",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('aria-label="调度模式"', html)
        self.assertIn("<h3>调度模式</h3>", html)
        # 副标与两态说明：仅保存设置意向；被动默认；主动不唤醒/不自动运行/人工唤回。
        self.assertIn("项目级 · 仅保存设置意向", html)
        self.assertIn("被动（默认）", html)
        self.assertIn("派发任务后本轮结束，由你通知完成后再读取与收取", html)
        self.assertIn("主控会话在等待期间继续取件、交独立复核并收尾", html)
        self.assertIn("没有任何会话因此被唤醒或自动运行；已结束的桌面对话仍需人工唤回", html)
        # 状态分两行：已保存设置 / 实际执行；effective=null 绝不显示成主动已启用。
        self.assertIn("已保存设置：读取中…", html)
        self.assertIn("实际执行：尚无生效的主动调度（本版本不支持自动生效）", html)
        self.assertNotIn("主动已启用", html)
        # 语义化表单：radio 同名分组 + fieldset/legend，键盘可用。
        self.assertIn('type="radio" name="controller-mode" value="passive"', html)
        self.assertIn('type="radio" name="controller-mode" value="active"', html)
        self.assertIn('role="status"', html)
        # 位置：项目设置右侧，排在“项目开发要求”“项目主控”之后、角色详情之前。
        self.assertLess(html.index('id="controller-panel"'), html.index('id="controller-mode-panel"'))
        self.assertLess(html.index('id="controller-mode-panel"'), html.index('id="role-details-name-panel"'))
        # 静态资源版本四处一致。
        self.assertEqual(html.count(STATIC_VERSION), 4)
        self.assertNotIn("20261006-controller-mode-c2b-f1", html)
        self.assertNotIn("20261005-role-desc-f2", html)

    def test_controller_mode_script_contract(self):
        script = (PROJECT_ROOT / "web" / "workspace.js").read_text(encoding="utf-8")
        app_script = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        stylesheet = (PROJECT_ROOT / "web" / "workspace.css").read_text(encoding="utf-8")

        start = script.index("// ── C2-B 项目调度模式")
        end = script.index("function renderWorkspaceTaskStory(")
        block = script[start:end]

        # 专用写入口：整份前端只有这一处写模式，不走普通项目 PATCH 旁路。
        self.assertIn("/controller-mode`", block)
        self.assertIn('method: "PATCH"', block)
        self.assertIn("JSON.stringify({ mode: submitted, expected_version: expected })", block)
        self.assertEqual(script.count("/controller-mode`"), 1)
        self.assertNotIn("/controller-mode", app_script)
        # expected_version 原样来自上次读取，不自己 +1；版本必须安全整数且 >=0 才能写。
        self.assertIn("const expected = controllerModeUI.version;", block)
        self.assertNotIn("expected_version: expected + 1", block)
        self.assertIn("Number.isSafeInteger(controllerModeUI.version)", block)
        self.assertIn("Number.isSafeInteger(data.controller_mode_version)", block)
        # 读取校验项目+字段存在；缺字段明确不支持并禁用保存，不把缺失当成 passive。
        self.assertIn('!("controller_mode" in data)', block)
        self.assertIn("当前服务尚未支持调度模式设置", block)
        self.assertIn("无法识别的模式", block)
        # 保存核实：同项目、返回模式与提交值一致，否则“服务未确认本次保存”。
        self.assertIn("data.project_id !== projectId", block)
        self.assertIn("data.controller_mode !== submitted", block)
        self.assertIn("服务未确认本次保存", block)
        # 409 只 GET 刷新最新模式/版本，不自动重写；PATCH 调用点只有一处。
        self.assertIn("res.status === 409", block)
        self.assertIn("rereadControllerModeState(projectId, memberId)", block)
        self.assertIn("已刷新到最新状态，请确认后再保存", block)
        self.assertIn("自动刷新最新状态失败", block)
        self.assertEqual(block.count("apiFetch(`/api/projects/${encodeURIComponent(projectId)}/controller-mode`"), 1)
        # 404 明确不支持并禁用保存。
        self.assertIn("res.status === 404", block)
        # 状态绑定 项目/账号/请求序号；保存收尾用独立 saveToken 所有权。
        self.assertIn("projectId === activeProjectId", block)
        self.assertIn("memberId === myId", block)
        self.assertIn("request === controllerModeUI.request", block)
        self.assertIn("controllerModeUI.saveToken = saveToken;", block)
        self.assertIn("controllerModeUI.saveToken === saveToken", block)
        self.assertIn("contextAlive() && ownsSave()", block)
        # 状态分两行；effective=null 绝不写成启用；无主控/失效保存主动显示原因且不产生主动调度。
        self.assertIn("已保存设置：", block)
        self.assertIn("实际执行：尚无生效的主动调度（本版本不支持自动生效）", block)
        self.assertNotIn("已启用", block)
        self.assertIn("不会因此产生任何主动调度", block)
        self.assertIn("尚未指定项目主控", block)
        # C2-B-UX：已保存状态行只显示模式名，不显示（版本 N）等数字版本括号；
        # 版本仍参与 expected_version/CAS（上方断言保留），仅删展示。
        self.assertNotIn("（版本", block)
        # C2-B-UX：离开“项目设置”即放弃未保存选择（不 PATCH/不自动保存/不弹确认）。
        self.assertIn("即放弃未保存选择", block)
        self.assertIn("controllerModeUI.selection = null;", block)
        # 两块面板独立：不写主控指定、不写普通项目字段；主控变更只读缓存刷新提示。
        self.assertNotIn("/controller-assignment", block)
        self.assertNotIn("development_requirements", block)
        self.assertNotIn("localStorage.", block)
        self.assertNotIn("innerHTML", block)
        self.assertNotIn("setInterval", block)
        self.assertNotRegex(
            block,
            re.compile(
                r"project\.(display_name|description|controller_member_id|controller_assignment_version|controller_assignment_status)\s*="
            ),
        )
        # 不自动提交：radio change 只更新未保存选择。
        self.assertIn("function selectControllerMode(mode)", block)
        self.assertIn("同步视图、不再发写请求", block)
        # 可见性统一由 renderTaskDetailsPanel 同步；刷新复用既有生命周期。
        details_fn = app_script[app_script.index("function renderTaskDetailsPanel()"):app_script.index("async function openTaskHall(")]
        self.assertIn("renderControllerModePanel();", details_fn)
        refresh_fn = app_script[app_script.index("async function refreshProjectWorkspace()"):app_script.index("function renderProjectStrip()")]
        self.assertIn("reloadControllerMode();", refresh_fn)
        # 面板可见性绑定“项目设置”选中态，与具体角色互斥。
        self.assertIn("workspaceSettingsSelected()", block)
        # 样式：面板样式存在且含窄屏覆盖。
        self.assertIn("#controller-mode-panel", stylesheet)
        self.assertIn(".controller-mode-option", stylesheet)
        self.assertIn(".controller-mode-status", stylesheet)

    def test_role_tasks_single_divider(self):
        """C2-B 双横线清理：内部 .role-task-section 不再叠加 border-top/margin-top，
        分隔线只保留面板容器 #role-details-tasks-panel 的一条。"""
        stylesheet = (PROJECT_ROOT / "web" / "workspace.css").read_text(encoding="utf-8")

        section_rule = re.search(r"\.role-task-section\s*\{[^}]*\}", stylesheet)
        self.assertIsNotNone(section_rule)
        self.assertNotIn("border-top", section_rule.group(0))
        self.assertNotIn("margin-top", section_rule.group(0))
        panel_rule = re.search(r"#role-details-tasks-panel\s*\{[^}]*\}", stylesheet)
        self.assertIsNotNone(panel_rule)
        self.assertIn("border-top", panel_rule.group(0))
        self.assertIn("margin-top", panel_rule.group(0))
        # 窄屏与桌面 80% 密度规则未给这两个选择器补回额外分隔线。
        for rule in re.findall(r"@media[^{]*\{(?:[^{}]*\{[^}]*\})*[^{}]*\}", stylesheet):
            if ".role-task-section" in rule or "#role-details-tasks-panel" in rule:
                self.fail(f"媒体查询不应再为分隔线相关选择器补样式: {rule[:120]}")
