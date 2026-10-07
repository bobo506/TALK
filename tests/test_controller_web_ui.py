"""I-2 固定主控入口退役 + C2-B 调度模式面板（发起者语义）：页面契约测试。"""

import re
from pathlib import Path

from tests.test_support import RouteTestCase


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_VERSION = "20261007-initiator-mode-ui"

# I-2 自检符号集：退役后 web 运行时不得再出现（DOM id / 函数 / 状态 / 导出 / 按钮）。
RETIRED_SCRIPT_SYMBOLS = (
    "controllerUI",
    "controllerStatusMeta",
    "reloadControllerAssignment",
    "renderControllerPanel",
    "workspaceControllerBadge",
    "workspaceControllerSummary",
    "controllerCandidate",
    "controllerAssignedLabel",
    "saveControllerAssignment",
    "loadControllerAssignment",
    "controllerEl",
    "CONTROLLER_STATUSES",
    "controllerContextValid",
    "controllerVersionSafe",
    "syncControllerCandidates",
    "syncControllerPanel",
    "syncControllerViews",
    "applyControllerRead",
    "rereadControllerState",
    "controllerFocusMemory",
    "controllerFocusTarget",
    "controllerFocusable",
    "controllerModeControllerState",
    "controllerModeUnavailableReason",
    "controllerModeAvailabilityNote",
)
RETIRED_DOM_IDS = (
    "controller-panel",
    "controller-current",
    "controller-detail",
    "controller-assign-row",
    "controller-candidate-select",
    "controller-assign-btn",
    "controller-clear-btn",
    "controller-retry-btn",
    "controller-status",
)


class ControllerRetiredWebUiTests(RouteTestCase):
    """I-2：固定主控面板/徽标/前端依赖整体退役的反向契约（无入口、无引用、无写调用）。"""

    def test_homepage_has_no_controller_panel(self):
        with self.make_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.text
        # 主控面板区块与其全部控件 id 不复存在。
        for element_id in RETIRED_DOM_IDS:
            self.assertNotIn(f'id="{element_id}"', html)
        self.assertNotIn('aria-label="项目主控"', html)
        self.assertNotIn("设为项目主控", html)
        self.assertNotIn("解除主控", html)
        self.assertNotIn("data-controller-action", html)
        # 页面可见文案改为发起者语义。
        self.assertIn("任务由发起者分配；选中任务后可在详情中创建子任务。", html)
        self.assertIn("供任务发起者派发任务前读取", html)
        self.assertNotIn("任务由主控分配", html)
        self.assertNotIn("供主控派发任务前读取", html)
        # 静态资源版本同步刷新缓存（4 处一致）。
        self.assertEqual(html.count(STATIC_VERSION), 4)
        self.assertNotIn("20261006-controller-mode-c2b-ux", html)
        self.assertNotIn("20261005-role-desc-f2", html)
        self.assertNotIn("20260923-manual-task-cleanup-1", html)
        self.assertNotIn("20260919-c1b-s2-owner", html)

    def test_controller_script_fully_retired(self):
        script = (PROJECT_ROOT / "web" / "workspace.js").read_text(encoding="utf-8")
        app_script = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        stylesheet = (PROJECT_ROOT / "web" / "workspace.css").read_text(encoding="utf-8")

        # 前端完全退出对 controller-assignment 端点的读写依赖（后端端点暂留兼容，不在本片删除）。
        self.assertNotIn("/controller-assignment", script)
        self.assertNotIn("/controller-assignment", app_script)
        # 退役符号集在 web 运行时归零（函数、状态对象、徽标助手、焦点处理、DOM 事件引用）。
        for symbol in RETIRED_SCRIPT_SYMBOLS:
            self.assertNotIn(symbol, script)
            self.assertNotIn(symbol, app_script)
        for element_id in RETIRED_DOM_IDS:
            self.assertNotIn(element_id, script)
            self.assertNotIn(element_id, app_script)
        self.assertNotIn("role-controller-badge", script)
        self.assertNotIn("data-controller-action", script)
        # 模式面板不再携带指定相关状态键。
        self.assertNotIn("controllerId", script)
        self.assertNotIn("controllerStatus", script)
        # 保留的调度模式面板调用点不随退役删除：刷新与详情同步仍在。
        details_fn = app_script[app_script.index("function renderTaskDetailsPanel()"):app_script.index("async function openTaskHall(")]
        self.assertIn("renderControllerModePanel();", details_fn)
        self.assertNotIn("renderControllerPanel", details_fn)
        refresh_fn = app_script[app_script.index("async function refreshProjectWorkspace()"):app_script.index("function renderProjectStrip()")]
        self.assertIn("reloadControllerMode();", refresh_fn)
        self.assertNotIn("reloadControllerAssignment", refresh_fn)
        # 样式：主控专属选择器删除，模式面板样式全部保留。
        for selector in ("#controller-panel", ".controller-hint", ".controller-current", ".controller-detail",
                         ".controller-toolbar", ".controller-status", ".role-controller-badge", ".controller-assign-row"):
            self.assertNotIn(selector, stylesheet)
        self.assertIn("#controller-mode-panel", stylesheet)
        self.assertIn(".controller-mode-option", stylesheet)
        self.assertIn(".controller-mode-status", stylesheet)
        self.assertIn(".role-settings-row", stylesheet)
        # 混合/共享样式未误删：角色行 ID 与成员 ID 样式保留。
        self.assertIn(".role-row-id", stylesheet)
        self.assertIn(".role-member-id", stylesheet)


class ControllerModeWebUiTests(RouteTestCase):
    """C2-B 项目设置页“调度模式”面板（I-2 发起者语义文案）+ 角色详情“参与任务”单分隔线：页面契约测试。"""

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
        # I-2 发起者语义：模式只约束任务发起侧；主动说明与 hint 均不含任何指定前置。
        self.assertIn("模式只约束任务发起侧：被动为派发后结束、由你通知后继续；主动为任务发起者在已获授权的任务流程内等待交付、读取结果、安排独立复核并收尾。", html)
        self.assertIn("任务发起者在等待期间继续读取交付、交独立复核并收尾", html)
        self.assertIn("没有任何会话因此被唤醒或自动运行；已结束的对话仍需人工唤回", html)
        self.assertNotIn("主控会话", html)
        # 状态分两行：已保存设置 / 实际执行；effective=null 绝不显示成主动已启用。
        self.assertIn("已保存设置：读取中…", html)
        self.assertIn("实际执行：尚无生效的主动调度（本版本不支持自动生效）", html)
        self.assertNotIn("主动已启用", html)
        # 语义化表单：radio 同名分组 + fieldset/legend，键盘可用。
        self.assertIn('type="radio" name="controller-mode" value="passive"', html)
        self.assertIn('type="radio" name="controller-mode" value="active"', html)
        self.assertIn('role="status"', html)
        # 位置：项目设置右侧，排在“项目开发要求”之后、角色详情之前（主控面板已退役，不再参与排序）。
        self.assertLess(html.index('id="requirements-panel"'), html.index('id="controller-mode-panel"'))
        self.assertLess(html.index('id="controller-mode-panel"'), html.index('id="role-details-name-panel"'))
        # 静态资源版本四处一致。
        self.assertEqual(html.count(STATIC_VERSION), 4)
        self.assertNotIn("20261006-controller-mode-c2b-ux", html)
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
        # 状态分两行；effective=null 绝不写成启用。
        self.assertIn("已保存设置：", block)
        self.assertIn("实际执行：尚无生效的主动调度（本版本不支持自动生效）", block)
        self.assertNotIn("已启用", block)
        # I-2：保存“主动”为固定意向提示，无任何指定前置；不再出现指定可用性分支。
        self.assertIn("已保存“主动”。这只是设置意向：不会唤醒会话或自动运行，已结束的桌面对话仍需人工唤回。", block)
        self.assertNotIn("不会因此产生任何主动调度", block)
        self.assertNotIn("尚未指定项目主控", block)
        self.assertNotIn("主控", block)
        # C2-B-UX：已保存状态行只显示模式名，不显示（版本 N）等数字版本括号；
        # 版本仍参与 expected_version/CAS（上方断言保留），仅删展示。
        self.assertNotIn("（版本", block)
        # C2-B-UX：离开“项目设置”即放弃未保存选择（不 PATCH/不自动保存/不弹确认）。
        self.assertIn("即放弃未保存选择", block)
        self.assertIn("controllerModeUI.selection = null;", block)
        # 隔离纪律：不写普通项目字段、不碰 localStorage/innerHTML、不新增轮询。
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
