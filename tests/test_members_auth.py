from fastapi import HTTPException, Response

from server.models import MemberCreate
from server.routes.members import create_member
from tests.test_support import RouteTestCase


class MembersAuthTests(RouteTestCase):
    def test_agent_self_registration_is_idempotent_and_refreshes_fields(self):
        with self.session() as session:
            response = Response()
            created = create_member(
                MemberCreate(
                    id="agent:AI1",
                    display_name="Agent AI1",
                    api_key="key-ai1",
                ),
                response,
                session,
            )
            self.assertEqual(created.id, "agent:AI1")
            self.assertEqual(created.display_name, "Agent AI1")

        with self.session() as session:
            response = Response()
            updated = create_member(
                MemberCreate(
                    id="agent:AI1",
                    display_name="Agent AI1 v2",
                    api_key="key-ai1",
                    poll_hint=5,
                ),
                response,
                session,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(updated.display_name, "Agent AI1 v2")
            self.assertEqual(updated.poll_hint, 5)

        with self.session() as session:
            response = Response()
            with self.assertRaises(HTTPException) as ctx:
                create_member(
                    MemberCreate(
                        id="agent:AI1",
                        display_name="Agent AI1 bad",
                        api_key="other-key",
                    ),
                    response,
                    session,
                )
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("different API key", ctx.exception.detail)

    def test_human_duplicate_registration_still_conflicts(self):
        with self.session() as session:
            response = Response()
            create_member(
                MemberCreate(
                    id="human:bobo",
                    display_name="Bobo",
                    api_key="bobo-key",
                ),
                response,
                session,
            )

        with self.session() as session:
            response = Response()
            with self.assertRaises(HTTPException) as ctx:
                create_member(
                    MemberCreate(
                        id="human:bobo",
                        display_name="Bobo 2",
                        api_key="bobo-key-2",
                    ),
                    response,
                    session,
                )
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("already exists", ctx.exception.detail)
