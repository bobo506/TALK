import re
from pathlib import Path

from tests.test_support import RouteTestCase


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TaskWebUiTests(RouteTestCase):
    def test_homepage_exposes_project_blackboard_and_task_hall_controls(self):
        with self.make_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.text
        for element_id in (
            "project-select",
            "project-blackboard-btn",
            "blackboard-columns",
            "task-details-panel",
            "task-create-overlay",
            "task-create-heading",
            "task-create-context",
            "task-create-agent-label",
            "task-create-agent",
            "task-create-content",
            "task-create-milestone",
            "task-create-kind",
            "task-create-related",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("20261006-controller-mode-c2b-f1", html)
        self.assertNotIn("20261006-controller-mode-c2b\"", html)
        self.assertNotIn("20261005-role-desc-f2", html)
        self.assertNotIn("20261005-role-desc-f1-fix", html)
        self.assertNotIn("20260923-manual-task-cleanup-1", html)
        self.assertNotIn("20260919-c1b-s2-owner", html)
        self.assertNotIn("20260919-c1b-s2-focus", html)
        self.assertNotIn('v=20260919-c1b-s2"', html)
        self.assertNotIn("20260918-role-1", html)
        self.assertNotIn("20260918-req2-rework", html)
        self.assertNotIn("20260918-req2-requirements", html)
        self.assertNotIn("20260913-task-duration", html)
        self.assertNotIn("20260910-task-chat-layout", html)
        # ROLE-DESC-F2：顶部“新建任务”入口已移除，共享创建弹窗与子任务入口保留。
        self.assertNotIn('id="delegate-task-btn"', html)
        self.assertNotIn("project-delegate-btn", html)
        self.assertIn("任务由主控分配；选中任务后可在详情中创建子任务。", html)
        self.assertNotIn("点击“新建任务”开始委派工作", html)
        self.assertIn('id="task-create-overlay"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-labelledby="task-create-heading"', html)
        self.assertIn('aria-labelledby="task-create-agent-label"', html)

    def test_task_ui_script_uses_project_scoped_api_and_safe_text_rendering(self):
        script = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        stylesheet = (PROJECT_ROOT / "web" / "style.css").read_text(encoding="utf-8")

        self.assertIn('new URLSearchParams({ project_id: activeProjectId })', script)
        self.assertIn('apiFetch("/api/tasks"', script)
        self.assertIn('runTaskAction(task, "collect-result")', script)
        self.assertIn('runTaskAction(task, "cancel", { confirmCancel: true })', script)
        self.assertIn('runTaskTreeAction(root, "accept-milestone")', script)
        self.assertIn('runTaskTreeAction(root, "pause-tree")', script)
        self.assertIn('submitLatestClarificationAnswer(task)', script)
        self.assertIn('payload.milestone_test_required = taskCreateMilestone.checked', script)
        self.assertIn("taskDetailsContent.textContent = task.content", script)
        self.assertIn("function renderBlackboard()", script)
        # ROLE-DESC-F2：delegateTaskBtn 常量/点击绑定/disabled 同步已随入口移除，不得残留空引用；
        # 共享弹窗的子任务打开路径与根模式 ternary 保留。
        self.assertNotIn("delegateTaskBtn", script)
        self.assertNotIn("delegate-task-btn", script)
        self.assertNotIn("canDelegate", script)
        self.assertIn("setTaskCreateOpen(true, { parentRoot: root })", script)
        self.assertIn('childMode ? "创建子任务" : "委派根任务"', script)
        self.assertIn('childMode ? "子任务执行 Agent" : "根任务负责人"', script)
        self.assertIn("根任务负责人继续负责拆分、协调和汇总", script)
        self.assertIn(".blackboard-columns", stylesheet)
        self.assertIn(".task-details-panel", stylesheet)
        # 按钮专属样式已删除；混合选择器中其它控件样式保留。
        self.assertNotIn("project-delegate-btn", stylesheet)
        self.assertIn(".project-nav-btn", stylesheet)
        self.assertRegex(
            stylesheet,
            re.compile(
                r"\.modal-card\s*\{[^}]*background:\s*var\(--card\);[^}]*box-shadow:\s*var\(--shadow\);",
                re.DOTALL,
            ),
        )
