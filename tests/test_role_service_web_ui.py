"""角色生命周期 R1-3：角色页受管服务启停的页面契约测试（静态字节 + 接线断言）。

真实请求/禁用/重复点击/轮询/离页清理的交互契约由
``tests/workspace_role_services.test.cjs`` 在 ``vm`` 里加载**真实** ``web/workspace.js``
后验证；本模块只做 Python 侧可机械检查的接线与文案合同（沿用仓库既有做法）。
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_support import RouteTestCase

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_VERSION = "20261016-task-initiator-label"

#: 设计 §5.3 的六个入口里，页面只允许调用 human 意图写与只读投影这四个。
PAGE_API_PATHS = (
    "/service/start",
    "/service/stop",
    "/role-services/start-all",
    "/role-services",
)


class RoleServiceWebUiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.script = (PROJECT_ROOT / "web" / "workspace.js").read_text(encoding="utf-8")
        self.styles = (PROJECT_ROOT / "web" / "workspace.css").read_text(encoding="utf-8")

    def test_static_assets_are_versioned_for_r1_3(self):
        self.assertIn(STATIC_VERSION, self.html)
        self.assertNotIn("20261011-role-lifecycle-r1-2", self.html)
        with self.make_client() as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(STATIC_VERSION, response.text)

    def test_role_page_wires_start_stop_and_start_all(self):
        for path in PAGE_API_PATHS:
            self.assertIn(path, self.script, f"页面必须真实接线 {path}")
        for function in (
            "startRoleService",
            "stopRoleService",
            "startAllRoleServices",
            "workspaceRoleServiceControls",
            "workspaceRoleServiceStartAllButton",
            "workspaceRoleServiceBatchFeedback",
            "pollRoleServices",
            "stopRoleServicePolling",
        ):
            self.assertIn(f"function {function}", self.script)
        # 角色列表行是 <button>，服务控制必须是其同级块（不能嵌套按钮）。
        self.assertIn("workspaceRoleServiceControls(role)", self.script)
        self.assertIn("workspaceRoleServiceStartAllButton()", self.script)
        self.assertIn("workspaceRoleServiceBatchFeedback()", self.script)
        # 真实请求：POST 而不是空回调。
        self.assertRegex(
            self.script,
            re.compile(r'role-services/start-all`,\s*\{[^}]*method:\s*"POST"', re.DOTALL),
        )

    def test_layout_containers_are_wired_separately(self):
        """R1-3 页面验收反馈：批量入口与反馈区是独立容器，按钮不进任务筛选标签行。"""
        self.assertIn('id="blackboard-toolbar"', self.html)
        self.assertIn('id="role-service-batch-feedback"', self.html)
        # 搜索与批量入口同处顶栏操作区，角色页由 workspace.js 显式隐藏任务页筛选容器。
        self.assertIn('id="workspace-search"', self.html)
        self.assertIn("batchActions.appendChild(workspaceRoleServiceStartAllButton())", self.script)
        self.assertIn("batchFeedbackContainer.appendChild(batchFeedback)", self.script)
        # 反馈区由独立容器承载，不是任务筛选标签行（.blackboard-summary）的子节点。
        self.assertIn('workspaceEl("div", "role-service-batch-feedback-content")', self.script)
        self.assertIn('workspaceEl("div", "role-entry")', self.script)

    def test_service_status_label_only_rendered_in_the_role_list(self):
        """列表只展示一个当前状态标签；角色详情不再重复状态标签。"""
        self.assertIn('function workspaceRoleServiceStateLabel(status)', self.script)
        self.assertIn('function workspaceRoleServiceActions(role, className)', self.script)
        self.assertIn('box.appendChild(workspaceRoleServiceStateLabel(control.status));', self.script)
        self.assertIn('workspaceRoleServiceActions(role, "role-service-controls role-service-detail-controls")', self.script)
        # 详情面板函数体内不得再挂状态标签（只保留标题、说明、操作与提示）。
        panel = self.script.split("function workspaceRoleServicePanel(role) {", 1)[1]
        self.assertNotIn("role-service-state", panel.split("\nfunction ", 1)[0])

    def test_start_button_is_gated_by_control_kind_not_by_idle_instances(self):
        self.assertIn('kind !== "managed_cli"', self.script)
        self.assertIn('kind === "managed_cli"', self.script)
        # 启动门控必须同时要求服务自述 can_start，不看绑定状态或“旧实例自报 idle”。
        self.assertRegex(
            self.script,
            re.compile(r"const canStart = managed && service\.can_start === true"),
        )
        self.assertNotRegex(
            self.script,
            re.compile(r"canStart[^;\n]*binding_state"),
        )
        # external_session / 未声明如实禁用并给引导，不靠 availability 开放。
        self.assertIn("external_session", self.script)
        self.assertNotRegex(self.script, re.compile(r"canStart[^;\n]*availability"))

    def test_status_text_matches_the_projection_contract(self):
        for text in (
            "未启动（已关闭）",
            "未启动",
            "启动中…",
            "关闭中…",
            "启动成功",
            "启动成功（原生登录未核验）",
            "启动失败（未就绪）",
            "启动失败",
            "未知",
        ):
            self.assertIn(text, self.script, f"缺少状态文案：{text}")

    def test_three_readiness_facts_are_not_merged(self):
        # running 只有 readiness_service === "ready" 才是成功；native_login 独立附注。
        self.assertRegex(
            self.script,
            re.compile(r'if \(observed === "running"\) \{\s*if \(readiness !== "ready"\)'),
        )
        self.assertIn("native_login", self.script)
        self.assertIn("readiness_service", self.script)

    def test_polling_and_cleanup_are_wired(self):
        self.assertIn("pollDelayMs: 2000", self.script)
        # 每次导航/刷新都会经 syncWorkspaceLayout；离页/切项目/切账号必须停止轮询。
        self.assertIn("syncRoleServicePollingContext();", self.script)
        self.assertRegex(
            self.script,
            re.compile(r"function syncRoleServicePollingContext\(\) \{\s*if \(!roleServicePageActive\(\)\) \{ stopRoleServicePolling\(\); return; \}"),
        )
        self.assertIn("roleServiceUI.projectId === activeProjectId", self.script)
        self.assertIn("roleServiceUI.pollToken", self.script)

    def test_duplicate_clicks_and_partial_failure_retry(self):
        self.assertIn("roleServiceUI.busy.has(memberId)", self.script)
        self.assertIn("重试失败项", self.script)
        self.assertIn("member_ids", self.script)
        self.assertIn('status === "failed"', self.script)

    def test_page_never_reads_credentials_or_fakes_success(self):
        for forbidden in ("owner_token", "claim_token", "api_key", "argv"):
            self.assertNotIn(forbidden, self.script)
        for forbidden in ("假成功", "demo", "演示数据"):
            self.assertNotIn(forbidden, self.script)

    def test_styles_exist_for_service_controls(self):
        for selector in (
            ".role-service-controls",
            ".role-service-row",
            ".role-service-state",
            ".role-service-button",
            ".role-service-hint",
            ".role-service-section",
            ".role-service-batch",
            ".role-service-batch-feedback",
            ".role-entry",
            ".blackboard-toolbar",
        ):
            self.assertIn(selector, self.styles, f"缺少样式：{selector}")
        # 布局修正：控制块不再用负外边距压线，也不在列表条目内自带横线。
        self.assertRegex(self.styles, re.compile(r"\.role-service-controls \{[^}]*margin:0;"))
        self.assertNotRegex(self.styles, re.compile(r"\.role-service-controls \{[^}]*border-bottom"))
        # 批量入口不再继承任务筛选标签的下划线样式。
        self.assertNotIn(".blackboard-summary .role-service-batch", self.styles)

    def test_node_contract_test_exists(self):
        node_test = PROJECT_ROOT / "tests" / "workspace_role_services.test.cjs"
        self.assertTrue(node_test.exists())
        source = node_test.read_text(encoding="utf-8")
        self.assertIn("workspace.js", source)
        self.assertIn("/service/start", source)
        self.assertIn("managed_cli", source)


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
