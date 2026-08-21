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
        self.assertIn("20260821-task-modal-context-1", html)
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
        self.assertIn('childMode ? "创建子任务" : "委派根任务"', script)
        self.assertIn('childMode ? "子任务执行 Agent" : "根任务负责人"', script)
        self.assertIn("根任务负责人继续负责拆分、协调和汇总", script)
        self.assertIn(".blackboard-columns", stylesheet)
        self.assertIn(".task-details-panel", stylesheet)
        self.assertRegex(
            stylesheet,
            re.compile(
                r"\.modal-card\s*\{[^}]*background:\s*var\(--card\);[^}]*box-shadow:\s*var\(--shadow\);",
                re.DOTALL,
            ),
        )
