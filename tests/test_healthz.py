from tests.test_support import RouteTestCase


class HealthzTests(RouteTestCase):
    def test_healthz_reports_ok_baseline(self):
        with self.make_client() as client:
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["db"], "ok")
        self.assertEqual(payload["storage"], "ok")
        self.assertIn("uptime_sec", payload)
        self.assertEqual(payload["online_members"], 0)
