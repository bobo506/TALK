"""GET /api/members/me/permissions 的本人能力查询测试（285）。

只回当前登录者本人；只暴露 member_id 与 can_view_all_conversations；
不泄漏配置名单 / Key / 其他权限；未知 Key 401、禁用 403 沿用现有语义。
"""

from datetime import datetime, timezone

import server.db as db

from tests.test_support import RouteTestCase


class MemberPermissionsRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.other_human = self.add_member("human:carol", api_key="carol-key", display_name="Carol")
        self.agent_ai1 = self.add_member("agent:AI1", api_key="ai1-key", display_name="AI1")

    def set_observer_config(self, section):
        old_config = db.CONFIG
        new_config = dict(old_config)
        if section is None:
            new_config.pop("conversation_access", None)
        else:
            new_config["conversation_access"] = section
        db.CONFIG = new_config
        self.addCleanup(setattr, db, "CONFIG", old_config)

    def get_permissions(self, key):
        with self.make_client() as client:
            return client.get("/api/members/me/permissions", headers={"X-API-Key": key})

    def test_unknown_key_gets_401(self):
        response = self.get_permissions("no-such-key")
        self.assertEqual(response.status_code, 401)

    def test_configured_human_gets_true(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        response = self.get_permissions("bobo-key")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["member_id"], "human:bobo")
        self.assertIs(payload["can_view_all_conversations"], True)
        # 不返回配置名单 / Key / 其他权限字段。
        self.assertEqual(set(payload), {"member_id", "can_view_all_conversations"})

    def test_unlisted_human_gets_false(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        response = self.get_permissions("carol-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"member_id": "human:carol", "can_view_all_conversations": False},
        )

    def test_agent_never_gets_permission_even_if_listed(self):
        self.set_observer_config({"observer_member_ids": ["agent:AI1", "human:bobo"]})
        response = self.get_permissions("ai1-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"member_id": "agent:AI1", "can_view_all_conversations": False},
        )

    def test_default_config_reports_false(self):
        self.set_observer_config(None)
        response = self.get_permissions("bobo-key")
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["can_view_all_conversations"], False)

    def test_invalid_config_reports_false(self):
        self.set_observer_config({"observer_member_ids": "*"})
        response = self.get_permissions("bobo-key")
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["can_view_all_conversations"], False)

    def test_disabled_member_gets_403(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        with self.session() as session:
            member = session.get(type(self.human), "human:bobo")
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        response = self.get_permissions("bobo-key")
        self.assertEqual(response.status_code, 403)

    def test_existing_me_endpoint_unchanged(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        with self.make_client() as client:
            response = client.get("/api/members/me", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], "human:bobo")
        self.assertNotIn("can_view_all_conversations", payload)
