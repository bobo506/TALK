"""N1 统一任务标题“编号-任务名称”的定向测试。"""

from datetime import datetime, timedelta, timezone

from server.models import AgentTask
from server.routes.tasks import _normalize_task_title
from tests.test_support import RouteTestCase


class NormalizeTaskTitleUnitTests(RouteTestCase):
    """纯函数级规则：幂等、空白回退、数字/连字符/中文保留。"""

    def test_plain_title_gets_real_id_prefix(self):
        self.assertEqual(_normalize_task_title(58, "主控模式切换"), "58-主控模式切换")

    def test_already_normalized_title_is_idempotent(self):
        normalized = _normalize_task_title(58, "主控模式切换")
        self.assertEqual(_normalize_task_title(58, normalized), normalized)

    def test_blank_title_uses_named_fallback(self):
        self.assertEqual(_normalize_task_title(61, "   "), "61-未命名任务")

    def test_missing_title_uses_named_fallback(self):
        self.assertEqual(_normalize_task_title(7, None), "7-未命名任务")

    def test_digits_hyphens_and_chinese_in_name_are_preserved(self):
        self.assertEqual(_normalize_task_title(61, "v2-修复3-5天耗时"), "61-v2-修复3-5天耗时")

    def test_pure_numeric_title_matching_id_is_preserved(self):
        # 纯数字名称即使恰好等于真实编号也是合法名称，必须保留（原实现会吞掉）。
        self.assertEqual(_normalize_task_title(60, "60"), "60-60")

    def test_pure_numeric_title_with_whitespace_is_preserved(self):
        self.assertEqual(_normalize_task_title(60, "  60  "), "60-60")


class TaskTitleApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")

    def _create_task(self, client, **overrides):
        payload = {
            "target_member_id": "agent:codex",
            "content": "默认正文",
        }
        payload.update(overrides)
        response = client.post("/api/tasks", headers={"X-API-Key": "bobo-key"}, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_created_task_title_uses_real_id_and_hall_reuses_it(self):
        client = self.make_client()
        created = self._create_task(client, title="统一任务标题", content="正文")
        expected = f"{created['id']}-统一任务标题"
        self.assertEqual(created["title"], expected)

        detail = client.get(f"/api/tasks/{created['id']}", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["title"], expected)

        listed = client.get("/api/tasks", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(listed.status_code, 200)
        titles = {task["id"]: task["title"] for task in listed.json()}
        self.assertEqual(titles[created["id"]], expected)

        hall = client.get(
            f"/api/groups/{created['hall_group_id']}",
            headers={"X-API-Key": "bobo-key"},
        )
        self.assertEqual(hall.status_code, 200)
        self.assertEqual(hall.json()["name"], expected)

    def test_created_task_with_title_matching_its_real_id_is_preserved(self):
        # 定向回归：实际创建取得的真实分配 ID 与同值纯数字标题，标题必须保留为“编号-编号”。
        client = self.make_client()
        probe = self._create_task(client, title="探针", content="正文")
        expected_id = probe["id"] + 1  # 测试库自增 ID 连续分配
        created = self._create_task(client, title=str(expected_id), content="正文")
        self.assertEqual(created["id"], expected_id)
        self.assertEqual(created["title"], f"{created['id']}-{created['id']}")

        hall = client.get(
            f"/api/groups/{created['hall_group_id']}",
            headers={"X-API-Key": "bobo-key"},
        )
        self.assertEqual(hall.status_code, 200)
        self.assertEqual(hall.json()["name"], f"{created['id']}-{created['id']}")

    def test_created_task_without_title_uses_named_fallback(self):
        client = self.make_client()
        created = self._create_task(client, content="第一行内容\n第二行")
        self.assertEqual(created["title"], f"{created['id']}-未命名任务")
        self.assertNotIn("null", created["title"].lower())
        self.assertNotIn("undefined", created["title"].lower())

    def test_schedule_materialization_assigns_each_task_its_own_number(self):
        client = self.make_client()
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        for _ in range(2):
            response = client.post(
                "/api/tasks/schedules",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "周报正文",
                    "title": "周报",
                    "run_at": past,
                },
            )
            self.assertEqual(response.status_code, 201, response.text)

        due = client.post("/api/tasks/schedules/run-due", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(due.status_code, 200, due.text)
        created_tasks = due.json()["created_tasks"]
        self.assertEqual(len(created_tasks), 2)
        for task in created_tasks:
            self.assertEqual(task["title"], f"{task['id']}-周报")
        prefixes = {task["title"].split("-", 1)[0] for task in created_tasks}
        self.assertEqual(len(prefixes), 2, "两次物化必须各自使用新任务编号，不能残留旧编号")

    def test_legacy_task_without_title_still_readable(self):
        client = self.make_client()
        created = self._create_task(client, title="旧任务")
        with self.session() as session:
            task = session.get(AgentTask, created["id"])
            task.title = None  # 模拟归一化之前的历史数据
            session.add(task)
            session.commit()

        detail = client.get(f"/api/tasks/{created['id']}", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(detail.status_code, 200)
        self.assertIsNone(detail.json()["title"])
        listed = client.get("/api/tasks", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(listed.status_code, 200)
