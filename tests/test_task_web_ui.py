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
            "task-create-agent",
            "task-create-content",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("20260716-task-blackboard-1", html)

    def test_task_ui_script_uses_project_scoped_api_and_safe_text_rendering(self):
        script = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        stylesheet = (PROJECT_ROOT / "web" / "style.css").read_text(encoding="utf-8")

        self.assertIn('new URLSearchParams({ project_id: activeProjectId })', script)
        self.assertIn('apiFetch("/api/tasks"', script)
        self.assertIn('runTaskAction(task, "collect-result")', script)
        self.assertIn('runTaskAction(task, "cancel", { confirmCancel: true })', script)
        self.assertIn("taskDetailsContent.textContent = task.content", script)
        self.assertIn("function renderBlackboard()", script)
        self.assertIn(".blackboard-columns", stylesheet)
        self.assertIn(".task-details-panel", stylesheet)
