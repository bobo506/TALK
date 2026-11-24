from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import quote

from server.models import Project, ProjectAgent, ProjectRole
from server.routes.projects import _TERMINAL_IDENTITY_IDS
from tests.test_support import RouteTestCase


class TestTerminalIdentityFilter(RouteTestCase):
    def test_project_lists_and_terminal_authentication(self):
        terminal = {"agent:codex-t", "agent:kimi-t", "agent:dsh-t", "agent:workbuddy-t", "agent:antigravity-t"}
        execution = {"agent:terra", "agent:k2.8", "agent:astra", "agent:test-t", "agent:test", "agent:prj-example.terra-123", "agent:codex", "agent:kimi", "agent:workbuddy", "agent:antigravity"}
        self.add_member("human:test", api_key="human-key")
        for index, member_id in enumerate(sorted(terminal | execution)):
            self.add_member(member_id, api_key=f"agent-key-{index}")
        with self.session() as session:
            session.add(Project(project_id="prj_test", display_name="Test", maintainer_member_id="human:test"))
            for member_id in terminal | execution:
                session.add(ProjectAgent(project_id="prj_test", member_id=member_id))
            for member_id in terminal | execution:
                archived_at = datetime.now(timezone.utc) if member_id in {"agent:codex", "agent:kimi", "agent:workbuddy"} else None
                session.add(ProjectRole(project_id="prj_test", member_id=member_id, role_name=member_id, created_by="human:test", archived_at=archived_at))
            session.commit()
        with self.make_client() as client:
            for endpoint in ("agents", "roles"):
                response = client.get(f"/api/projects/prj_test/{endpoint}", headers={"X-API-Key": "human-key"})
                self.assertEqual(response.status_code, 200, response.text)
                ids = [row["member_id"] for row in response.json()]
                self.assertEqual(ids, sorted(execution))
            for index, member_id in enumerate(sorted(terminal | execution)):
                if member_id in terminal:
                    response = client.get("/api/members/me", headers={"X-API-Key": f"agent-key-{index}"})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["id"], member_id)
                response = client.get(
                    f"/api/projects/prj_test/roles/{quote(member_id, safe='')}/tasks",
                    headers={"X-API-Key": "human-key"},
                )
                self.assertEqual(response.status_code, 200, response.text)

    def test_frontend_terminal_identity_set_matches_backend(self):
        workspace_js = (Path(__file__).resolve().parents[1] / "web/workspace.js").read_text(encoding="utf-8")
        match = re.search(r"const terminalIds = new Set\((\[[^\]]+\])\);", workspace_js)
        self.assertIsNotNone(match, "terminalIds Set declaration missing in web/workspace.js")
        frontend_ids = set(json.loads(match.group(1)))
        self.assertEqual(frontend_ids, set(_TERMINAL_IDENTITY_IDS))
