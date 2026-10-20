"""conversation_access 只读旁观策略与 Group 读路由的边界测试（285）。

覆盖：默认空配置、配置 human:bobo、另一 human、成员 / 非成员 Agent、未知 Key 401、
禁用 403、误配 Agent、各类非法配置 fail closed；旁观者读历史 / 分页 / 搜索，
不产生 GroupMember 写入；legacy/global 可见性不扩大。
"""

from datetime import datetime, timezone

import server.db as db
import server.main as main
from server.conversation_access import (
    active_human_observer_ids,
    can_read_group_conversation,
    is_conversation_observer,
    merge_observer_targets,
    observer_member_ids,
)
from server.models import Group, GroupMember, Member, Message
from sqlmodel import select

from tests.test_support import RouteTestCase


class ConversationAccessTestCase(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.other_human = self.add_member("human:carol", api_key="carol-key", display_name="Carol")
        self.agent_ai1 = self.add_member("agent:AI1", api_key="ai1-key", display_name="AI1")
        self.agent_ai2 = self.add_member("agent:AI2", api_key="ai2-key", display_name="AI2")

    def set_observer_config(self, section):
        """替换 conversation_access 配置段；None 表示整段缺失。"""
        old_config = db.CONFIG
        new_config = dict(old_config)
        if section is None:
            new_config.pop("conversation_access", None)
        else:
            new_config["conversation_access"] = section
        db.CONFIG = new_config
        self.addCleanup(setattr, db, "CONFIG", old_config)

    def make_group(self, group_id="group:lab", member_ids=()):
        with self.make_client() as client:
            response = client.post(
                "/api/groups",
                headers={"X-API-Key": "ai1-key"},
                json={"id": group_id, "name": "Local Lab", "member_ids": list(member_ids)},
            )
        assert response.status_code == 201, response.text

    def post_group_message(self, group_id, content, key="ai1-key"):
        with self.make_client() as client:
            response = client.post(
                "/api/messages",
                headers={"X-API-Key": key},
                json={"type": "text", "group_id": group_id, "content": content},
            )
        assert response.status_code == 201, response.text
        return response.json()

    def get_group_messages(self, key, group_id="group:lab", **params):
        with self.make_client() as client:
            return client.get(
                "/api/messages",
                headers={"X-API-Key": key},
                params={"group_id": group_id, **params},
            )


class ObserverPolicyUnitTests(ConversationAccessTestCase):
    def test_default_config_has_no_observers(self):
        self.set_observer_config(None)
        self.assertEqual(observer_member_ids(), frozenset())
        self.assertFalse(is_conversation_observer(self.human))

    def test_empty_list_means_disabled(self):
        self.set_observer_config({"observer_member_ids": []})
        self.assertEqual(observer_member_ids(), frozenset())
        self.assertFalse(is_conversation_observer(self.human))

    def test_configured_human_is_observer(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.assertEqual(observer_member_ids(), frozenset({"human:bobo"}))
        self.assertTrue(is_conversation_observer(self.human))
        self.assertFalse(is_conversation_observer(self.other_human))

    def test_agent_in_list_never_becomes_observer(self):
        self.set_observer_config({"observer_member_ids": ["agent:AI1", "human:bobo"]})
        self.assertFalse(is_conversation_observer(self.agent_ai1))
        self.assertTrue(is_conversation_observer(self.human))

    def test_disabled_member_in_list_is_not_observer(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        with self.session() as session:
            member = session.get(type(self.human), "human:bobo")
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        with self.session() as session:
            disabled = session.get(type(self.human), "human:bobo")
            self.assertFalse(is_conversation_observer(disabled))

    def test_invalid_configs_fail_closed(self):
        invalid_sections = [
            {"observer_member_ids": "*"},
            {"observer_member_ids": ["*"]},
            {"observer_member_ids": ["human:*"]},
            {"observer_member_ids": "human:bobo"},
            {"observer_member_ids": ["human:bobo"] * 17},
            {"observer_member_ids": ["human:bobo", 42]},
            {"observer_member_ids": ["human:bobo", "human:bad\x07id"]},
            {"observer_member_ids": ["human:bobo", "human: bad"]},
            {"observer_member_ids": ["human:bobo", ""]},
            {"observer_member_ids": ["human:bobo", None]},
        ]
        for section in invalid_sections:
            with self.subTest(section=section):
                self.set_observer_config(section)
                self.assertEqual(observer_member_ids(), frozenset())
                self.assertFalse(is_conversation_observer(self.human))

    def test_section_not_a_table_fails_closed(self):
        self.set_observer_config(["human:bobo"])
        self.assertEqual(observer_member_ids(), frozenset())

    def test_member_id_shape_is_enforced(self):
        self.set_observer_config({"observer_member_ids": ["bobo"]})
        self.assertEqual(observer_member_ids(), frozenset())
        self.set_observer_config({"observer_member_ids": ["other:bobo"]})
        self.assertEqual(observer_member_ids(), frozenset())

    def test_active_human_observer_ids_filters_agents_and_disabled(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo", "agent:AI1", "human:ghost"]})
        with self.session() as session:
            self.assertEqual(active_human_observer_ids(session), ["human:bobo"])
        with self.session() as session:
            member = session.get(type(self.human), "human:bobo")
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        with self.session() as session:
            self.assertEqual(active_human_observer_ids(session), [])

    def test_merge_observer_targets_appends_without_duplicates(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        with self.session() as session:
            merged = merge_observer_targets(["agent:AI1"], session)
            self.assertEqual(merged, ["agent:AI1", "human:bobo"])
            merged_again = merge_observer_targets(["agent:AI1", "human:bobo"], session)
            self.assertEqual(merged_again, ["agent:AI1", "human:bobo"])
        self.set_observer_config(None)
        with self.session() as session:
            self.assertEqual(merge_observer_targets(["agent:AI1"], session), ["agent:AI1"])

    def test_can_read_group_conversation_member_or_observer_only(self):
        self.make_group(member_ids=[])
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        with self.session() as session:
            member = session.get(type(self.agent_ai1), "agent:AI1")
            self.assertTrue(can_read_group_conversation("group:lab", member, session))
        with self.session() as session:
            observer = session.get(type(self.human), "human:bobo")
            self.assertTrue(can_read_group_conversation("group:lab", observer, session))
        with self.session() as session:
            outsider = session.get(type(self.other_human), "human:carol")
            self.assertFalse(can_read_group_conversation("group:lab", outsider, session))


class ObserverGroupReadRouteTests(ConversationAccessTestCase):
    def test_default_config_non_member_human_gets_403(self):
        self.set_observer_config(None)
        self.make_group(member_ids=[])
        self.post_group_message("group:lab", "hello hall")
        response = self.get_group_messages("bobo-key")
        self.assertEqual(response.status_code, 403)

    def test_observer_reads_full_history_pagination_and_search(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=["agent:AI2"])
        first = self.post_group_message("group:lab", "first message")
        second = self.post_group_message("group:lab", "second needle message")
        third = self.post_group_message("group:lab", "third message")

        response = self.get_group_messages("bobo-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m["id"] for m in response.json()], [first["id"], second["id"], third["id"]])

        paged = self.get_group_messages("bobo-key", before=third["id"])
        self.assertEqual([m["id"] for m in paged.json()], [first["id"], second["id"]])

        incremental = self.get_group_messages("bobo-key", since=first["id"])
        self.assertEqual([m["id"] for m in incremental.json()], [second["id"], third["id"]])

        searched = self.get_group_messages("bobo-key", q="needle")
        self.assertEqual([m["id"] for m in searched.json()], [second["id"]])

    def test_observer_reads_task_hall_without_membership(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        with self.make_client() as client:
            created = client.post(
                "/api/groups",
                headers={"X-API-Key": "ai1-key"},
                json={"id": "group:task-hall", "name": "Task Hall", "type": "task", "member_ids": []},
            )
            self.assertEqual(created.status_code, 201)
        posted = self.post_group_message("group:task-hall", "task progress")
        response = self.get_group_messages("bobo-key", group_id="group:task-hall")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m["id"] for m in response.json()], [posted["id"]])

    def test_other_human_not_listed_still_gets_403(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        self.post_group_message("group:lab", "hello hall")
        response = self.get_group_messages("carol-key")
        self.assertEqual(response.status_code, 403)

    def test_misconfigured_agent_gets_no_read_access(self):
        self.set_observer_config({"observer_member_ids": ["agent:AI2", "human:bobo"]})
        self.make_group(member_ids=[])
        self.post_group_message("group:lab", "hello hall")
        response = self.get_group_messages("ai2-key")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.get_group_messages("bobo-key").status_code, 200)

    def test_unknown_key_gets_401(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        response = self.get_group_messages("no-such-key")
        self.assertEqual(response.status_code, 401)

    def test_disabled_observer_gets_403(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        with self.session() as session:
            member = session.get(type(self.human), "human:bobo")
            member.disabled_at = datetime.now(timezone.utc)
            session.add(member)
            session.commit()
        response = self.get_group_messages("bobo-key")
        self.assertEqual(response.status_code, 403)

    def test_invalid_config_disables_observer_read(self):
        self.make_group(member_ids=[])
        self.post_group_message("group:lab", "hello hall")
        for section in (
            {"observer_member_ids": "*"},
            {"observer_member_ids": "human:bobo"},
            {"observer_member_ids": ["human:bobo"] * 17},
        ):
            with self.subTest(section=section):
                self.set_observer_config(section)
                self.assertEqual(self.get_group_messages("bobo-key").status_code, 403)

    def test_observer_read_does_not_create_membership(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        self.post_group_message("group:lab", "hello hall")
        self.assertEqual(self.get_group_messages("bobo-key").status_code, 200)
        with self.session() as session:
            membership = session.exec(
                select(GroupMember).where(
                    GroupMember.group_id == "group:lab",
                    GroupMember.member_id == "human:bobo",
                )
            ).first()
        self.assertIsNone(membership)

    def test_group_not_found_keeps_400(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        response = self.get_group_messages("bobo-key", group_id="group:missing")
        self.assertEqual(response.status_code, 400)

    def test_legacy_global_visibility_not_expanded_for_observer(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        direct = self.add_message(
            from_id="agent:AI1",
            to_ids='["agent:AI2"]',
            message_type="text",
            content="direct between agents",
        )
        broadcast = self.add_message(
            from_id="agent:AI1",
            to_ids=None,
            message_type="text",
            content="broadcast to everyone",
        )
        with self.make_client() as client:
            response = client.get("/api/messages", headers={"X-API-Key": "bobo-key"})
        self.assertEqual(response.status_code, 200)
        ids = [m["id"] for m in response.json()]
        self.assertIn(broadcast.id, ids)
        self.assertNotIn(direct.id, ids)

    def test_observer_cannot_send_to_group_via_rest(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        with self.make_client() as client:
            response = client.post(
                "/api/messages",
                headers={"X-API-Key": "bobo-key"},
                json={"type": "text", "group_id": "group:lab", "content": "observer must not write"},
            )
        self.assertEqual(response.status_code, 403)

    def test_observer_cannot_revoke_others_message(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        posted = self.post_group_message("group:lab", "someone else message")
        with self.make_client() as client:
            response = client.post(
                f"/api/messages/{posted['id']}/revoke",
                headers={"X-API-Key": "bobo-key"},
            )
        self.assertEqual(response.status_code, 403)

    def test_observer_cannot_reply_in_group(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=[])
        posted = self.post_group_message("group:lab", "root message")
        with self.make_client() as client:
            response = client.post(
                "/api/messages",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "type": "text",
                    "group_id": "group:lab",
                    "content": "reply attempt",
                    "reply_to": posted["id"],
                },
            )
        self.assertEqual(response.status_code, 403)

    def test_member_read_path_unchanged_with_observer_config(self):
        self.set_observer_config({"observer_member_ids": ["human:bobo"]})
        self.make_group(member_ids=["agent:AI2"])
        posted = self.post_group_message("group:lab", "member visible")
        member_view = self.get_group_messages("ai2-key")
        self.assertEqual(member_view.status_code, 200)
        self.assertEqual([m["id"] for m in member_view.json()], [posted["id"]])


class ObserverBackfillRevocationTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member('human:bobo', api_key='fake-bobo')
        self.add_member('agent:writer', api_key='fake-writer')
        previous = db.CONFIG
        db.CONFIG = {**previous, 'conversation_access': {'observer_member_ids':['human:bobo']}}
        self.addCleanup(setattr,db,'CONFIG',previous)
        with self.session() as session:
            session.add(Group(id='group:private',name='Private',created_by='agent:writer'))
            session.add(GroupMember(group_id='group:private',member_id='agent:writer'))
            session.add_all([Message(group_id='group:private',from_id='agent:writer',type='text',content='synthetic') for _ in range(main.SSE_BACKFILL_BATCH_SIZE+1)])
            session.commit()

    def assert_backfill_stops_after(self, revoke):
        with self.session() as session:
            events=main._sse_backfill_events('human:bobo',0,session,include_all_groups=True)
            first_page=[next(events) for _ in range(main.SSE_BACKFILL_BATCH_SIZE)]
            self.assertEqual(len(first_page),main.SSE_BACKFILL_BATCH_SIZE)
            revoke()
            self.assertEqual(list(events),[],'later pages must recheck current observer authority')

    def test_config_revoked_between_pages_does_not_leak_later_group_messages(self):
        def revoke():
            db.CONFIG={**db.CONFIG,'conversation_access':{'observer_member_ids':[]}}
        self.assert_backfill_stops_after(revoke)

    def test_member_disabled_between_pages_does_not_leak_later_group_messages(self):
        def disable():
            with self.session() as session:
                member=session.get(Member,'human:bobo')
                member.disabled_at=datetime.now(timezone.utc)
                session.add(member)
                session.commit()
        self.assert_backfill_stops_after(disable)
