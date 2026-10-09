"""ROLE-DESC-F1 角色说明前端编辑：页面契约测试。"""

import re
from pathlib import Path

from tests.test_support import RouteTestCase


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_VERSION = "20261009-role-binding-b4"


class RoleDescriptionWebUiTests(RouteTestCase):
    def test_homepage_exposes_static_role_description_panel(self):
        with self.make_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.text
        for element_id in (
            "role-details-name-panel",
            "role-description-panel",
            "role-description-input",
            "role-description-save",
            "role-description-discard",
            "role-description-reset",
            "role-description-count",
            "role-description-status",
            "role-details-tasks-panel",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('aria-label="角色名称"', html)
        self.assertIn('aria-label="角色说明"', html)
        self.assertIn('aria-label="参与的任务"', html)
        self.assertIn('role="status"', html)
        # 语义文案：纯展示文本、不改变任务发起者归属/职责/权限，空白或恢复默认回到默认文案
        self.assertIn("纯展示文本 · 不改变职责与权限", html)
        self.assertIn("不改变任务发起者归属、职责分级", html)
        self.assertIn("恢复默认", html)
        # N4 修正（#137）：布局顺序 = 名称区 → 静态说明区 → 参与任务区，三者同级 section；
        # 说明区不得置于任一动态度量内部（replaceChildren 会销毁编辑区节点）。
        self.assertRegex(
            html,
            re.compile(
                r'<section id="role-details-name-panel"[^>]*></section>\s*'
                r'(<!--.*?-->\s*)*<section id="role-description-panel"[\s\S]*?</section>\s*'
                r'<section id="role-details-tasks-panel"[^>]*></section>',
                re.DOTALL,
            ),
        )
        self.assertLess(html.index('id="role-details-name-panel"'), html.index('id="role-description-panel"'))
        self.assertLess(html.index('id="role-description-panel"'), html.index('id="role-details-tasks-panel"'))
        self.assertLess(html.index('id="role-details-tasks-panel"'), html.index('id="group-members-panel"'))
        self.assertNotIn('id="role-details-panel"', html, "旧的整体动态角色详情容器已拆分")
        # 静态资源版本同步刷新缓存（4 处）。
        self.assertEqual(html.count(STATIC_VERSION), 4)
        self.assertEqual(len(re.findall(r"20261005-role-desc", html)), 0, "旧版本串不残留")
        self.assertNotIn("20260923-manual-task-cleanup-1", html)
        self.assertNotIn("20260919-c1b-s2-owner", html)
        self.assertNotIn("20260918-role-1", html)

    def test_role_description_script_contract(self):
        script = (PROJECT_ROOT / "web" / "workspace.js").read_text(encoding="utf-8")
        app_script = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        stylesheet = (PROJECT_ROOT / "web" / "workspace.css").read_text(encoding="utf-8")

        start = script.index("const ROLE_DESCRIPTION_MAX_CHARS")
        end = script.index("function renderWorkspaceList()")
        block = script[start:end]

        # 2000 码点上限与后端一致；空白判定复用 REQ2 的 Python str.isspace 集合，不以 JS trim 判空。
        self.assertIn("const ROLE_DESCRIPTION_MAX_CHARS = 2000", block)
        self.assertIn("REQUIREMENTS_BLANK.test(text)", block)
        self.assertNotRegex(block, re.compile(r"\.trim\(\)\s*===?\s*[\"']"))
        # 专用 PUT 入口：URL 绑定发起时项目与成员，body 只提交 description（归一化值）。
        self.assertIn(
            "apiFetch(`/api/projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(memberId)}/description`",
            block,
        )
        self.assertIn('method: "PUT"', block)
        self.assertIn("JSON.stringify({ description: normalized })", block)
        # 响应严格核实：同项目/同成员且带回与归一化提交一致的 description 才认成功。
        self.assertIn('data.project_id !== projectId', block)
        self.assertIn('data.member_id !== memberId', block)
        self.assertIn('!("description" in data)', block)
        self.assertIn("data.description !== normalized", block)
        # D2：核实通过后更新 projectAgents 缓存并显式重绘列表摘要。
        self.assertIn("agent.role_description = data.description", block)
        self.assertIn("renderWorkspaceList()", block)
        # N1 修正：超限判定先归一化空白再查非空长度（全空白归 null 不受 2000 码点约束）。
        self.assertIn("normalizeRoleDescriptionValue(input.value) !== null && length > ROLE_DESCRIPTION_MAX_CHARS", block)
        # N3 修正：PUT 404 区分名册/项目不存在/普通 404，均不武断翻转 supported 降级。
        self.assertIn("/not in the project roster/.test(detail)", block)
        self.assertIn("/project not found/.test(detail)", block)
        not_found_branch = block[block.index("res.status === 404"):block.index("if (!res.ok)")]
        self.assertNotIn("supported = false", not_found_branch)
        # N4 修正：agent 与旧服务只读态只 readOnly（可复制），不再 disabled。
        self.assertIn("input.readOnly = !human || !ready;", block)
        self.assertNotIn("input.disabled", block)
        # 展示安全：整个区块无 innerHTML（只走 textContent / textarea.value）。
        self.assertNotIn("innerHTML", block)
        # 默认文案 = 短标签 + 换行 + 解释；映射仅作默认值生成器保留。
        self.assertIn("function workspaceRoleDefaultDescription(", script)
        self.assertIn("`${label}\\n${explanation}`", script)
        # 角色详情动态面板不再渲染硬编码短标签/解释行（注释提及类名不算，断言元素创建与映射调用）。
        details_fn = script[script.index("function renderWorkspaceRoleDetails()"):]
        details_fn = details_fn[:details_fn.index("\nfunction workspaceTaskNotice(")]
        self.assertNotIn("workspaceRoleLabel(", details_fn)
        self.assertNotIn("workspaceRoleDescription(", details_fn)
        self.assertNotIn('workspaceEl("p", "role-description"', details_fn)
        self.assertNotIn('workspaceEl("p", "role-explanation"', details_fn)
        # N4 修正：动态角色详情拆为名称区与参与任务区两个容器，说明区不在其中。
        self.assertIn('getElementById("role-details-name-panel")', details_fn)
        self.assertIn('getElementById("role-details-tasks-panel")', details_fn)
        self.assertNotIn('getElementById("role-details-panel")', details_fn)
        self.assertNotIn('role-description-input', details_fn, "说明编辑区不经动态详情渲染")
        # N1：可见性同步点在 app.js renderTaskDetailsPanel，且排在调度模式面板之后
        # （I-2：原“主控面板之后”随固定主控入口退役改为调度模式面板）。
        details_panel_fn = app_script[app_script.index("function renderTaskDetailsPanel()"):]
        self.assertIn("renderRoleDescriptionPanel();", details_panel_fn)
        self.assertLess(
            details_panel_fn.index("renderControllerModePanel();"),
            details_panel_fn.index("renderRoleDescriptionPanel();"),
        )
        # 列表摘要取首个非空行（Python 空白集合判空，不把 U+FEFF 等合法自定义误回退硬编码）。
        self.assertIn("function workspaceRoleSummary(", script)
        self.assertIn("ROLE_DESCRIPTION_BLANK_EDGE", script)
        # 样式归 workspace.css：新增面板样式存在，被移除的硬编码样式不残留。
        self.assertIn("#role-description-panel", stylesheet)
        self.assertIn(".role-description-textarea", stylesheet)
        self.assertNotIn(".role-explanation", stylesheet)
        self.assertNotRegex(stylesheet, re.compile(r"^\.role-description \{", re.MULTILINE))
        # N2 修正：列表摘要明确省略号截断（最多 2 行），长无空格字符串不撑破布局。
        self.assertRegex(stylesheet, re.compile(r"\.role-row span \{[^}]*-webkit-line-clamp:\s*2"))
        self.assertRegex(stylesheet, re.compile(r"\.role-row span \{[^}]*overflow:\s*hidden"))
        self.assertRegex(stylesheet, re.compile(r"\.role-row span \{[^}]*overflow-wrap:\s*anywhere"))
        # N4 修正：名称区 / 参与任务区两个动态容器样式存在。
        self.assertIn("#role-details-tasks-panel", stylesheet)
