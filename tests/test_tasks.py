from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import server.db as db
from server.models import AgentInstance, AgentTask
from tests.test_support import RouteTestCase


class AgentTaskTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("human:alice", api_key="alice-key", display_name="Alice")
        self.add_member("agent:codex", api_key="codex-key", display_name="Codex")
        self.add_member("agent:other", api_key="other-key", display_name="Other")
        self.add_member("agent:third", api_key="third-key", display_name="Third")

    def test_human_can_create_task_for_agent_and_agent_can_list_it(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "title": "Smoke",
                    "content": "Run the smoke task",
                },
            )
            agent_tasks = client.get(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                params={"status": "queued"},
            )
            other_tasks = client.get("/api/tasks", headers={"X-API-Key": "other-key"})

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["created_by"], "human:bobo")
        self.assertEqual(created.json()["status"], "queued")
        self.assertEqual(created.json()["workflow_status"], "assigned")
        self.assertIsNone(created.json()["parent_task_id"])
        self.assertEqual(created.json()["root_task_id"], created.json()["id"])
        self.assertEqual(created.json()["delegation_depth"], 0)
        self.assertFalse(created.json()["may_delegate"])
        self.assertEqual(created.json()["max_delegation_depth"], 1)
        self.assertEqual(created.json()["max_running_descendants"], 3)
        self.assertEqual(created.json()["max_running_per_target"], 1)
        self.assertEqual(created.json()["max_nonterminal_descendants"], 8)
        self.assertEqual(created.json()["control_status"], "active")
        self.assertEqual(created.json()["authorization_epoch"], 0)
        self.assertEqual(created.json()["authorized_slice_budget"], 0)
        self.assertEqual(created.json()["reserved_slice_count"], 0)
        self.assertIsNone(created.json()["authorization_expires_at"])
        self.assertIsNotNone(created.json()["hall_group_id"])
        self.assertEqual([task["id"] for task in agent_tasks.json()], [created.json()["id"]])
        self.assertEqual(other_tasks.json(), [])

    def test_project_task_creates_dedicated_one_to_one_hall_and_supports_filters(self):
        with self.make_client() as client:
            project = client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_talk", "display_name": "TALK"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_talk",
                    "target_member_id": "agent:codex",
                    "title": "Task Hall foundation",
                    "content": "Build the first Task Hall slice",
                },
            )
            task = created.json()
            hall = client.get(
                f"/api/groups/{task['hall_group_id']}",
                headers={"X-API-Key": "bobo-key"},
            )
            filtered = client.get(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                params={"project_id": "prj_talk", "workflow_status": "assigned"},
            )
            hidden = client.get(
                f"/api/tasks/{task['id']}",
                headers={"X-API-Key": "other-key"},
            )

        self.assertEqual(project.status_code, 201)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(task["project_id"], "prj_talk")
        self.assertEqual(task["workflow_status"], "assigned")
        self.assertIsNone(task["result_collected_at"])
        self.assertEqual(hall.status_code, 200)
        self.assertEqual(hall.json()["type"], "task")
        self.assertEqual(hall.json()["project_id"], "prj_talk")
        self.assertEqual(hall.json()["name"], "Task Hall foundation")
        self.assertEqual(
            {member["member_id"]: member["role"] for member in hall.json()["members"]},
            {"human:bobo": "owner", "agent:codex": "member"},
        )
        self.assertEqual([item["id"] for item in filtered.json()], [task["id"]])
        self.assertEqual(hidden.status_code, 404)

    def test_task_rejects_unknown_project_and_self_assignment(self):
        with self.make_client() as client:
            unknown_project = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_missing",
                    "target_member_id": "agent:codex",
                    "content": "hello",
                },
            )
            self_assignment = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={"target_member_id": "agent:codex", "content": "hello"},
            )

        self.assertEqual(unknown_project.status_code, 400)
        self.assertEqual(self_assignment.status_code, 400)

    def test_task_tree_requires_explicit_delegation_and_inherits_root_governance(self):
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_tree", "display_name": "Task tree"},
            )
            locked_root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "No delegation"},
            ).json()
            client.post(
                f"/api/tasks/{locked_root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            blocked_child = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": locked_root["id"],
                    "authorization_epoch": locked_root["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "Must be blocked",
                },
            )

            root_response = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "project_id": "prj_tree",
                    "target_member_id": "agent:codex",
                    "content": "Delegating root",
                    "may_delegate": True,
                },
            )
            root = root_response.json()
            client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            excessive_grant = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "Cannot redelegate at depth one",
                    "may_delegate": True,
                },
            )
            child_response = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "Allowed child",
                },
            )
            agent_override = client.post(
                "/api/tasks",
                headers={"X-API-Key": "other-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Unauthorized root override",
                    "may_delegate": True,
                },
            )

        child = child_response.json()
        self.assertEqual(blocked_child.status_code, 409)
        self.assertIn("no delegation permission", blocked_child.json()["detail"])
        self.assertEqual(root_response.status_code, 201)
        self.assertTrue(root["may_delegate"])
        self.assertEqual(excessive_grant.status_code, 409)
        self.assertIn("depth limit", excessive_grant.json()["detail"])
        self.assertEqual(child_response.status_code, 201)
        self.assertEqual(child["parent_task_id"], root["id"])
        self.assertEqual(child["root_task_id"], root["id"])
        self.assertEqual(child["delegation_depth"], 1)
        self.assertEqual(child["project_id"], "prj_tree")
        self.assertFalse(child["may_delegate"])
        self.assertIsNone(child["max_delegation_depth"])
        self.assertEqual(agent_override.status_code, 403)

    def test_nonterminal_descendant_limit_is_atomic_during_concurrent_creation(self):
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "One child only",
                    "may_delegate": True,
                    "max_running_descendants": 1,
                    "max_running_per_target": 1,
                    "max_nonterminal_descendants": 1,
                },
            ).json()
            client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )

        barrier = Barrier(2)

        def create_child(target_member_id: str):
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    "/api/tasks",
                    headers={"X-API-Key": "codex-key"},
                    json={
                        "parent_task_id": root["id"],
                        "authorization_epoch": root["authorization_epoch"],
                        "target_member_id": target_member_id,
                        "content": f"Child for {target_member_id}",
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(create_child, ("agent:other", "agent:third")))

        self.assertEqual(sorted(response.status_code for response in responses), [201, 409])
        loser = next(response for response in responses if response.status_code == 409)
        self.assertIn("nonterminal descendant limit 1", loser.json()["detail"])
        with self.make_client() as client:
            tasks = client.get("/api/tasks", headers={"X-API-Key": "bobo-key"}).json()
        children = [task for task in tasks if task["parent_task_id"] == root["id"]]
        self.assertEqual(len(children), 1)

    def test_authorized_slice_budget_is_atomic_during_concurrent_creation(self):
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Authorize exactly one child slice",
                    "may_delegate": True,
                    "slice_budget": 1,
                    "max_running_descendants": 3,
                    "max_running_per_target": 1,
                    "max_nonterminal_descendants": 8,
                },
            ).json()
            claimed = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            self.assertEqual(claimed.status_code, 200)

        barrier = Barrier(2)

        def create_child(target_member_id: str):
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    "/api/tasks",
                    headers={"X-API-Key": "codex-key"},
                    json={
                        "parent_task_id": root["id"],
                        "authorization_epoch": root["authorization_epoch"],
                        "target_member_id": target_member_id,
                        "content": f"Authorized child for {target_member_id}",
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(create_child, ("agent:other", "agent:third")))

        self.assertEqual(sorted(response.status_code for response in responses), [201, 409])
        loser = next(response for response in responses if response.status_code == 409)
        self.assertIn("authorized slice budget 1 exhausted", loser.json()["detail"])
        with self.make_client() as client:
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            ).json()
        self.assertEqual(tree["root"]["reserved_slice_count"], 1)
        self.assertEqual(tree["remaining_slice_budget"], 0)
        self.assertEqual(len(tree["tasks"]), 2)

    def test_pause_resume_revoke_claims_and_open_a_new_authorization_epoch(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/codex-control",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Pause and resume this tree",
                    "may_delegate": True,
                    "slice_budget": 1,
                },
            ).json()
            claimed = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-control"},
            ).json()
            child = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "First authorized child",
                },
            ).json()
            paused = client.post(
                f"/api/tasks/{child['id']}/pause-tree",
                headers={"X-API-Key": "codex-key"},
            )
            blocked_claim = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            stale_complete = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": claimed["claim_token"]},
            )
            blocked_create = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Blocked while paused",
                },
            )
            forbidden_resume = client.post(
                f"/api/tasks/{root['id']}/resume-tree",
                headers={"X-API-Key": "other-key"},
                json={"slice_budget": 1, "authorization_ttl_seconds": 60},
            )
            resumed = client.post(
                f"/api/tasks/{root['id']}/resume-tree",
                headers={"X-API-Key": "bobo-key"},
                json={"slice_budget": 1, "authorization_ttl_seconds": 60},
            )
            reclaimed = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            stale_epoch_create = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Stale first-epoch request",
                },
            )
            second_child = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": resumed.json()["root"]["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Second epoch child",
                },
            )
            hidden_tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "third-key"},
            )
            instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"member_id": "agent:codex"},
            ).json()

        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["root"]["control_status"], "paused")
        self.assertEqual(paused.json()["root"]["status"], "queued")
        self.assertEqual(blocked_claim.status_code, 409)
        self.assertIn("control is paused", blocked_claim.json()["detail"])
        self.assertEqual(stale_complete.status_code, 409)
        self.assertEqual(blocked_create.status_code, 409)
        self.assertEqual(forbidden_resume.status_code, 403)
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["root"]["authorization_epoch"], 2)
        self.assertEqual(resumed.json()["root"]["reserved_slice_count"], 0)
        self.assertEqual(reclaimed.status_code, 200)
        self.assertEqual(stale_epoch_create.status_code, 409)
        self.assertIn("epoch 1 is stale", stale_epoch_create.json()["detail"])
        self.assertEqual(second_child.status_code, 201)
        self.assertEqual(hidden_tree.status_code, 404)
        self.assertEqual(instances[0]["status"], "idle")
        self.assertIsNone(instances[0]["current_task_id"])

    def test_expired_authorization_blocks_claim_and_creation_until_human_resume(self):
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Expire this authorization",
                    "may_delegate": True,
                },
            ).json()

        with self.session() as session:
            task = session.get(AgentTask, root["id"])
            task.authorization_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(task)
            session.commit()

        with self.make_client() as client:
            expired_claim = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            waiting = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )
            client.post(
                f"/api/tasks/{root['id']}/resume-tree",
                headers={"X-API-Key": "bobo-key"},
                json={"slice_budget": 1, "authorization_ttl_seconds": 60},
            )
            claimed = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            self.assertEqual(claimed.status_code, 200)

        with self.session() as session:
            task = session.get(AgentTask, root["id"])
            task.authorization_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(task)
            session.commit()

        with self.make_client() as client:
            expired_create = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": 2,
                    "target_member_id": "agent:other",
                    "content": "Blocked by elapsed authorization",
                },
            )
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(expired_claim.status_code, 409)
        self.assertIn("authorization has expired", expired_claim.json()["detail"])
        self.assertEqual(waiting.json()["root"]["control_status"], "awaiting_human")
        self.assertTrue(waiting.json()["authorization_expired"])
        self.assertEqual(expired_create.status_code, 409)
        self.assertIn("authorization has expired", expired_create.json()["detail"])
        self.assertEqual(tree.json()["root"]["checkpoint_reason"], "time_limit")

    def test_persisted_nonactive_root_immediately_blocks_heartbeat_and_complete(self):
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Simulate the pause propagation window",
                },
            ).json()
            claimed = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"lease_seconds": 60},
            ).json()

        with self.session() as session:
            task = session.get(AgentTask, root["id"])
            task.control_status = "pause_requested"
            session.add(task)
            session.commit()

        with self.make_client() as client:
            duplicate_claim = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            heartbeat = client.post(
                f"/api/tasks/{root['id']}/heartbeat",
                headers={"X-API-Key": "codex-key"},
                json={"claim_token": claimed["claim_token"], "lease_seconds": 60},
            )
            complete = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": claimed["claim_token"]},
            )

        self.assertEqual(duplicate_claim.status_code, 409)
        self.assertEqual(heartbeat.status_code, 409)
        self.assertEqual(complete.status_code, 409)

    def test_checkpoint_and_cancel_tree_enforce_roles_and_preserve_history(self):
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Checkpoint then cancel",
                    "may_delegate": True,
                },
            ).json()
            claimed = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            self.assertEqual(claimed.status_code, 200)
            forbidden_checkpoint = client.post(
                f"/api/tasks/{root['id']}/checkpoint",
                headers={"X-API-Key": "other-key"},
                json={"reason": "risk_boundary"},
            )
            checkpoint = client.post(
                f"/api/tasks/{root['id']}/checkpoint",
                headers={"X-API-Key": "codex-key"},
                json={"reason": "risk_boundary"},
            )
            resumed = client.post(
                f"/api/tasks/{root['id']}/resume-tree",
                headers={"X-API-Key": "bobo-key"},
                json={"slice_budget": 1, "authorization_ttl_seconds": 60},
            )
            client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            child = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": resumed.json()["root"]["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "Canceled descendant",
                },
            ).json()
            forbidden_cancel = client.post(
                f"/api/tasks/{root['id']}/cancel-tree",
                headers={"X-API-Key": "codex-key"},
            )
            canceled = client.post(
                f"/api/tasks/{child['id']}/cancel-tree",
                headers={"X-API-Key": "bobo-key"},
            )
            canceled_again = client.post(
                f"/api/tasks/{root['id']}/cancel-tree",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(forbidden_checkpoint.status_code, 403)
        self.assertEqual(checkpoint.status_code, 200)
        self.assertEqual(checkpoint.json()["root"]["control_status"], "awaiting_human")
        self.assertEqual(checkpoint.json()["root"]["checkpoint_reason"], "risk_boundary")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(forbidden_cancel.status_code, 403)
        self.assertEqual(canceled.status_code, 200)
        self.assertEqual(canceled.json()["root"]["control_status"], "canceled")
        self.assertEqual({task["status"] for task in canceled.json()["tasks"]}, {"canceled"})
        self.assertEqual(len(canceled_again.json()["tasks"]), 2)

    def test_running_descendant_limit_is_atomic_during_concurrent_claims(self):
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "One running child",
                    "may_delegate": True,
                    "max_running_descendants": 1,
                    "max_running_per_target": 1,
                },
            ).json()
            client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            children = [
                client.post(
                    "/api/tasks",
                    headers={"X-API-Key": "codex-key"},
                    json={
                        "parent_task_id": root["id"],
                        "authorization_epoch": root["authorization_epoch"],
                        "target_member_id": target,
                        "content": f"Run {target}",
                    },
                ).json()
                for target in ("agent:other", "agent:third")
            ]

        barrier = Barrier(2)

        def claim_child(task_and_key: tuple[dict, str]):
            task, api_key = task_and_key
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    f"/api/tasks/{task['id']}/claim",
                    headers={"X-API-Key": api_key},
                    json={},
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(claim_child, zip(children, ("other-key", "third-key"))))

        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        loser = next(response for response in responses if response.status_code == 409)
        self.assertIn("running descendant limit 1", loser.json()["detail"])

    def test_per_target_running_limit_is_atomic_during_concurrent_claims(self):
        with self.make_client() as client:
            root = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "One running task per target",
                    "may_delegate": True,
                    "max_running_descendants": 3,
                    "max_running_per_target": 1,
                },
            ).json()
            client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            children = [
                client.post(
                    "/api/tasks",
                    headers={"X-API-Key": "codex-key"},
                    json={
                        "parent_task_id": root["id"],
                        "authorization_epoch": root["authorization_epoch"],
                        "target_member_id": "agent:other",
                        "content": f"Same target {index}",
                    },
                ).json()
                for index in range(2)
            ]

        barrier = Barrier(2)

        def claim_child(task: dict):
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    f"/api/tasks/{task['id']}/claim",
                    headers={"X-API-Key": "other-key"},
                    json={},
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(claim_child, children))

        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        loser = next(response for response in responses if response.status_code == 409)
        self.assertIn("per-target running limit 1", loser.json()["detail"])

    def test_task_workflow_clarification_accept_submit_and_collect(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            task = created.json()
            wrong_clarification = client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "other-key"},
            )
            clarification = client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "codex-key"},
            )
            blocked_claim = client.post(
                f"/api/tasks/{task['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            accepted = client.post(
                f"/api/tasks/{task['id']}/accept",
                headers={"X-API-Key": "codex-key"},
            )
            claimed = client.post(
                f"/api/tasks/{task['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            client.post(
                "/api/groups",
                headers={"X-API-Key": "bobo-key"},
                json={"id": "group:unrelated", "name": "Unrelated", "member_ids": ["agent:codex"]},
            )
            unrelated_result = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id="group:unrelated",
                content="Wrong Hall",
            )
            wrong_submission = client.post(
                f"/api/tasks/{task['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "result_message_id": unrelated_result.id},
            )
            result = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="Done",
            )
            submitted = client.post(
                f"/api/tasks/{task['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "result_message_id": result.id},
            )
            wrong_collector = client.post(
                f"/api/tasks/{task['id']}/collect-result",
                headers={"X-API-Key": "alice-key"},
            )
            collected = client.post(
                f"/api/tasks/{task['id']}/collect-result",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(wrong_clarification.status_code, 403)
        self.assertEqual(clarification.json()["workflow_status"], "clarification_requested")
        self.assertEqual(blocked_claim.status_code, 409)
        self.assertEqual(accepted.json()["workflow_status"], "accepted")
        self.assertEqual(claimed.json()["workflow_status"], "in_progress")
        self.assertEqual(wrong_submission.status_code, 400)
        self.assertEqual(submitted.json()["status"], "succeeded")
        self.assertEqual(submitted.json()["workflow_status"], "submitted")
        self.assertIsNone(submitted.json()["result_collected_at"])
        self.assertEqual(wrong_collector.status_code, 403)
        self.assertEqual(collected.json()["workflow_status"], "completed")
        self.assertIsNotNone(collected.json()["result_collected_at"])

    def test_requester_can_cancel_unclaimed_task_but_not_running_task(self):
        with self.make_client() as client:
            pending = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Cancel before claim"},
            ).json()
            wrong_member = client.post(
                f"/api/tasks/{pending['id']}/cancel",
                headers={"X-API-Key": "alice-key"},
            )
            canceled = client.post(
                f"/api/tasks/{pending['id']}/cancel",
                headers={"X-API-Key": "bobo-key"},
            )
            canceled_again = client.post(
                f"/api/tasks/{pending['id']}/cancel",
                headers={"X-API-Key": "bobo-key"},
            )

            running = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Already running"},
            ).json()
            client.post(
                f"/api/tasks/{running['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            running_cancel = client.post(
                f"/api/tasks/{running['id']}/cancel",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(wrong_member.status_code, 403)
        self.assertEqual(canceled.status_code, 200)
        self.assertEqual(canceled.json()["status"], "canceled")
        self.assertEqual(canceled.json()["workflow_status"], "canceled")
        self.assertIsNotNone(canceled.json()["finished_at"])
        self.assertEqual(canceled_again.json()["status"], "canceled")
        self.assertEqual(running_cancel.status_code, 409)

    def test_task_hall_cannot_be_rewired_or_deleted_as_a_regular_group(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Protected Hall"},
            ).json()
            hall_group_id = created["hall_group_id"]
            add_member = client.put(
                f"/api/groups/{hall_group_id}/members/agent:other",
                headers={"X-API-Key": "bobo-key"},
                json={"role": "member"},
            )
            remove_member = client.delete(
                f"/api/groups/{hall_group_id}/members/agent:codex",
                headers={"X-API-Key": "bobo-key"},
            )
            delete_hall = client.delete(
                f"/api/groups/{hall_group_id}",
                headers={"X-API-Key": "bobo-key"},
            )
            still_there = client.get(
                f"/api/groups/{hall_group_id}",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(add_member.status_code, 409)
        self.assertEqual(remove_member.status_code, 409)
        self.assertEqual(delete_hall.status_code, 409)
        self.assertEqual(still_there.status_code, 200)

    def test_task_target_must_be_agent_member(self):
        with self.make_client() as client:
            missing = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:missing", "content": "hello"},
            )
            human = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "human:bobo", "content": "hello"},
            )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(human.status_code, 400)

    def test_agent_can_claim_own_task_and_instance_becomes_busy(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            claimed = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-1"},
            )
            instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"member_id": "agent:codex"},
            )

        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json()["status"], "running")
        self.assertEqual(claimed.json()["workflow_status"], "in_progress")
        self.assertEqual(claimed.json()["claimed_by"], "agent:codex")
        self.assertEqual(claimed.json()["instance_id"], "codex-1")
        self.assertEqual(instances.json()[0]["status"], "busy")
        self.assertEqual(instances.json()[0]["current_task_id"], str(created.json()["id"]))

    def test_human_and_wrong_agent_cannot_claim_task(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            human_claim = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "bobo-key"},
                json={},
            )
            other_claim = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "other-key"},
                json={},
            )

        self.assertEqual(human_claim.status_code, 403)
        self.assertEqual(other_claim.status_code, 403)

    def test_claim_is_atomic_idempotent_and_renews_with_heartbeat(self):
        with self.make_client() as client:
            for instance_id in ("codex-1", "codex-2"):
                client.put(
                    f"/api/instances/{instance_id}",
                    headers={"X-API-Key": "codex-key"},
                    json={"runtime": "codex", "status": "idle"},
                )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            task_id = created.json()["id"]

        barrier = Barrier(2)

        def claim(instance_id: str):
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    f"/api/tasks/{task_id}/claim",
                    headers={"X-API-Key": "codex-key"},
                    json={"instance_id": instance_id, "lease_seconds": 30},
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(claim, ("codex-1", "codex-2")))

        winner = next(response for response in responses if response.status_code == 200)
        loser = next(response for response in responses if response.status_code == 409)
        claimed = winner.json()
        winner_instance = claimed["instance_id"]
        claim_token = claimed["claim_token"]

        with self.make_client() as client:
            repeated = client.post(
                f"/api/tasks/{task_id}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": winner_instance, "lease_seconds": 30},
            )
            stale_heartbeat = client.post(
                f"/api/tasks/{task_id}/heartbeat",
                headers={"X-API-Key": "codex-key"},
                json={"claim_token": "stale", "lease_seconds": 30},
            )
            heartbeat = client.post(
                f"/api/tasks/{task_id}/heartbeat",
                headers={"X-API-Key": "codex-key"},
                json={"claim_token": claim_token, "lease_seconds": 30},
            )
            visible = client.get(f"/api/tasks/{task_id}", headers={"X-API-Key": "bobo-key"})

        self.assertEqual(loser.status_code, 409)
        self.assertEqual(claimed["attempt"], 1)
        self.assertIsNotNone(claimed["lease_expires_at"])
        self.assertEqual(repeated.json()["attempt"], 1)
        self.assertEqual(repeated.json()["claim_token"], claim_token)
        self.assertEqual(stale_heartbeat.status_code, 409)
        self.assertEqual(heartbeat.status_code, 200)
        self.assertIsNotNone(heartbeat.json()["heartbeat_at"])
        self.assertNotIn("claim_token", visible.json())

    def test_expired_claim_is_requeued_and_stale_attempt_cannot_complete(self):
        with self.make_client() as client:
            for instance_id in ("codex-1", "codex-2"):
                client.put(
                    f"/api/instances/{instance_id}",
                    headers={"X-API-Key": "codex-key"},
                    json={"runtime": "codex", "status": "idle"},
                )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Recover me"},
            )
            task_id = created.json()["id"]
            first_claim = client.post(
                f"/api/tasks/{task_id}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-1", "lease_seconds": 30},
            ).json()

        with self.session() as session:
            task = session.get(AgentTask, task_id)
            assert task is not None
            task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(task)
            session.commit()

        with self.make_client() as client:
            human_reap = client.post("/api/tasks/requeue-expired", headers={"X-API-Key": "bobo-key"})
            requeued = client.post("/api/tasks/requeue-expired", headers={"X-API-Key": "codex-key"})
            second_claim = client.post(
                f"/api/tasks/{task_id}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-2", "lease_seconds": 30},
            ).json()
            stale_complete = client.post(
                f"/api/tasks/{task_id}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": first_claim["claim_token"]},
            )
            missing_token = client.post(
                f"/api/tasks/{task_id}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded"},
            )
            completed = client.post(
                f"/api/tasks/{task_id}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": second_claim["claim_token"]},
            )

        with self.session() as session:
            first_instance = session.get(AgentInstance, "codex-1")
            second_instance = session.get(AgentInstance, "codex-2")

        self.assertEqual(human_reap.status_code, 403)
        self.assertEqual([task["id"] for task in requeued.json()], [task_id])
        self.assertEqual(requeued.json()[0]["status"], "queued")
        self.assertEqual(requeued.json()[0]["workflow_status"], "accepted")
        self.assertEqual(second_claim["attempt"], 2)
        self.assertNotEqual(second_claim["claim_token"], first_claim["claim_token"])
        self.assertEqual(stale_complete.status_code, 409)
        self.assertEqual(missing_token.status_code, 409)
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["status"], "succeeded")
        self.assertIsNotNone(first_instance)
        self.assertEqual(first_instance.status, "error")
        self.assertIsNotNone(second_instance)
        self.assertEqual(second_instance.status, "idle")

    def test_claim_rejects_instance_owned_by_another_agent(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/other-1",
                headers={"X-API-Key": "other-key"},
                json={"runtime": "pi", "status": "idle"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            response = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "other-1"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("another member", response.json()["detail"])

    def test_agent_can_complete_running_task_and_instance_returns_idle(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-1"},
            )
            result = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                content="Done",
            )
            completed = client.post(
                f"/api/tasks/{created.json()['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "result_message_id": result.id},
            )
            instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"member_id": "agent:codex"},
            )

        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["status"], "succeeded")
        self.assertEqual(completed.json()["workflow_status"], "submitted")
        self.assertEqual(completed.json()["result_message_id"], result.id)
        self.assertIsNotNone(completed.json()["finished_at"])
        self.assertEqual(instances.json()[0]["status"], "idle")
        self.assertIsNone(instances.json()[0]["current_task_id"])

    def test_failed_completion_requires_error_and_sets_instance_error(self):
        with self.make_client() as client:
            client.put(
                "/api/instances/codex-1",
                headers={"X-API-Key": "codex-key"},
                json={"runtime": "codex", "status": "idle"},
            )
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Do the thing"},
            )
            client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={"instance_id": "codex-1"},
            )
            missing_error = client.post(
                f"/api/tasks/{created.json()['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "failed"},
            )
            failed = client.post(
                f"/api/tasks/{created.json()['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "failed", "last_error": "boom"},
            )
            instances = client.get(
                "/api/instances",
                headers={"X-API-Key": "bobo-key"},
                params={"member_id": "agent:codex"},
            )

        self.assertEqual(missing_error.status_code, 422)
        self.assertEqual(failed.status_code, 200)
        self.assertEqual(failed.json()["status"], "failed")
        self.assertEqual(failed.json()["workflow_status"], "failed")
        self.assertEqual(instances.json()[0]["status"], "error")
        self.assertEqual(instances.json()[0]["last_error"], "boom")

    def test_human_can_create_schedule_and_agent_can_list_it(self):
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with self.make_client() as client:
            created = client.post(
                "/api/tasks/schedules",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "title": "Later",
                    "content": "Run later",
                    "run_at": run_at,
                },
            )
            agent_schedules = client.get(
                "/api/tasks/schedules",
                headers={"X-API-Key": "codex-key"},
                params={"status": "active"},
            )
            other_schedules = client.get("/api/tasks/schedules", headers={"X-API-Key": "other-key"})

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["created_by"], "human:bobo")
        self.assertEqual(created.json()["schedule_type"], "once")
        self.assertEqual(created.json()["status"], "active")
        self.assertEqual([schedule["id"] for schedule in agent_schedules.json()], [created.json()["id"]])
        self.assertEqual(other_schedules.json(), [])

    def test_run_due_once_schedule_creates_task_and_completes_schedule(self):
        run_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with self.make_client() as client:
            created = client.post(
                "/api/tasks/schedules",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Run now", "run_at": run_at},
            )
            materialized = client.post("/api/tasks/schedules/run-due", headers={"X-API-Key": "bobo-key"})
            materialized_task = materialized.json()["created_tasks"][0]
            hall = client.get(
                f"/api/groups/{materialized_task['hall_group_id']}",
                headers={"X-API-Key": "bobo-key"},
            )
            second_run = client.post("/api/tasks/schedules/run-due", headers={"X-API-Key": "bobo-key"})

        payload = materialized.json()
        self.assertEqual(materialized.status_code, 200)
        self.assertEqual(len(payload["created_tasks"]), 1)
        self.assertEqual(payload["created_tasks"][0]["schedule_id"], created.json()["id"])
        self.assertEqual(payload["created_tasks"][0]["status"], "queued")
        self.assertEqual(payload["created_tasks"][0]["workflow_status"], "assigned")
        self.assertIsNotNone(payload["created_tasks"][0]["hall_group_id"])
        self.assertEqual(hall.json()["type"], "task")
        self.assertEqual(
            {member["member_id"] for member in hall.json()["members"]},
            {"human:bobo", "agent:codex"},
        )
        self.assertEqual(payload["updated_schedules"][0]["status"], "completed")
        self.assertEqual(payload["updated_schedules"][0]["last_task_id"], payload["created_tasks"][0]["id"])
        self.assertEqual(second_run.json()["created_tasks"], [])

    def test_run_due_interval_schedule_advances_next_run(self):
        run_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with self.make_client() as client:
            created = client.post(
                "/api/tasks/schedules",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Run repeatedly",
                    "run_at": run_at,
                    "interval_seconds": 60,
                },
            )
            materialized = client.post("/api/tasks/schedules/run-due", headers={"X-API-Key": "codex-key"})
            fetched = client.get(
                f"/api/tasks/schedules/{created.json()['id']}",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(materialized.status_code, 200)
        updated = materialized.json()["updated_schedules"][0]
        self.assertEqual(updated["status"], "active")
        self.assertEqual(updated["schedule_type"], "interval")
        self.assertEqual(updated["interval_seconds"], 60)
        self.assertEqual(updated["last_task_id"], materialized.json()["created_tasks"][0]["id"])
        self.assertEqual(fetched.json()["last_task_id"], updated["last_task_id"])
        self.assertNotEqual(fetched.json()["next_run_at"], created.json()["next_run_at"])

    def test_pause_schedule_blocks_run_due_and_wrong_agent_cannot_update(self):
        run_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with self.make_client() as client:
            created = client.post(
                "/api/tasks/schedules",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Run later", "run_at": run_at},
            )
            wrong_agent = client.patch(
                f"/api/tasks/schedules/{created.json()['id']}",
                headers={"X-API-Key": "other-key"},
                json={"status": "paused"},
            )
            paused = client.patch(
                f"/api/tasks/schedules/{created.json()['id']}",
                headers={"X-API-Key": "bobo-key"},
                json={"status": "paused"},
            )
            materialized = client.post("/api/tasks/schedules/run-due", headers={"X-API-Key": "bobo-key"})

        self.assertEqual(wrong_agent.status_code, 404)
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["status"], "paused")
        self.assertEqual(materialized.json()["created_tasks"], [])

    def test_init_db_adds_task_hall_fields_and_backfills_legacy_workflow_status(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE agent_tasks")
            conn.exec_driver_sql(
                """
                CREATE TABLE agent_tasks (
                    id INTEGER PRIMARY KEY,
                    target_member_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    content TEXT NOT NULL,
                    title TEXT,
                    status TEXT NOT NULL,
                    claimed_by TEXT,
                    instance_id TEXT,
                    result_message_id INTEGER,
                    last_error TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    claimed_at TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )
            conn.exec_driver_sql(
                """
                INSERT INTO agent_tasks (
                    id, target_member_id, created_by, content, status, created_at, updated_at
                ) VALUES
                    (1, 'agent:codex', 'human:bobo', 'queued', 'queued', '2026-07-15', '2026-07-15'),
                    (2, 'agent:codex', 'human:bobo', 'running', 'running', '2026-07-15', '2026-07-15'),
                    (3, 'agent:codex', 'human:bobo', 'succeeded', 'succeeded', '2026-07-15', '2026-07-15'),
                    (4, 'agent:codex', 'human:bobo', 'failed', 'failed', '2026-07-15', '2026-07-15'),
                    (5, 'agent:codex', 'human:bobo', 'canceled', 'canceled', '2026-07-15', '2026-07-15')
                """
            )

        db.init_db()

        with self.engine.connect() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(agent_tasks)").fetchall()}
            indexes = {
                row[1]: row[2]
                for row in conn.exec_driver_sql("PRAGMA index_list(agent_tasks)").fetchall()
            }
            workflow_by_id = dict(
                conn.exec_driver_sql(
                    "SELECT id, workflow_status FROM agent_tasks ORDER BY id"
                ).fetchall()
            )
            tree_rows = conn.exec_driver_sql(
                """
                SELECT
                    id, parent_task_id, root_task_id, delegation_depth, may_delegate,
                    max_delegation_depth, max_running_descendants,
                    max_running_per_target, max_nonterminal_descendants
                FROM agent_tasks
                ORDER BY id
                """
            ).fetchall()
            control_rows = conn.exec_driver_sql(
                """
                SELECT
                    id, control_status, authorization_epoch,
                    authorized_slice_budget, reserved_slice_count,
                    authorization_expires_at, checkpoint_reason
                FROM agent_tasks
                ORDER BY id
                """
            ).fetchall()

        self.assertTrue({
            "project_id",
            "hall_group_id",
            "workflow_status",
            "result_collected_at",
            "attempt",
            "claim_token",
            "lease_expires_at",
            "heartbeat_at",
            "parent_task_id",
            "root_task_id",
            "delegation_depth",
            "may_delegate",
            "max_delegation_depth",
            "max_running_descendants",
            "max_running_per_target",
            "max_nonterminal_descendants",
            "control_status",
            "authorization_epoch",
            "authorized_slice_budget",
            "reserved_slice_count",
            "authorization_expires_at",
            "checkpoint_reason",
        }.issubset(columns))
        self.assertEqual(indexes["ix_agent_tasks_hall_group_id"], 1)
        self.assertEqual(indexes["ix_agent_tasks_lease_expires_at"], 0)
        self.assertEqual(indexes["ix_agent_tasks_parent_task_id"], 0)
        self.assertEqual(indexes["ix_agent_tasks_root_task_id"], 0)
        self.assertEqual(indexes["ix_agent_tasks_delegation_depth"], 0)
        self.assertEqual(indexes["ix_agent_tasks_control_status"], 0)
        self.assertEqual(indexes["ix_agent_tasks_authorization_expires_at"], 0)
        self.assertEqual(
            workflow_by_id,
            {
                1: "assigned",
                2: "in_progress",
                3: "submitted",
                4: "failed",
                5: "canceled",
            },
        )
        self.assertEqual(
            tree_rows,
            [
                (task_id, None, task_id, 0, 0, 1, 3, 1, 8)
                for task_id in range(1, 6)
            ],
        )
        self.assertEqual(
            control_rows,
            [
                (task_id, "active", 0, 0, 0, None, None)
                for task_id in range(1, 6)
            ],
        )

    def test_init_db_backfills_existing_delegating_tree_without_granting_extra_slices(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE agent_tasks")
            conn.exec_driver_sql(
                """
                CREATE TABLE agent_tasks (
                    id INTEGER PRIMARY KEY,
                    parent_task_id INTEGER,
                    root_task_id INTEGER,
                    delegation_depth INTEGER NOT NULL DEFAULT 0,
                    may_delegate INTEGER NOT NULL DEFAULT 0,
                    max_delegation_depth INTEGER,
                    max_running_descendants INTEGER,
                    max_running_per_target INTEGER,
                    max_nonterminal_descendants INTEGER,
                    target_member_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    content TEXT NOT NULL,
                    title TEXT,
                    status TEXT NOT NULL,
                    claimed_by TEXT,
                    instance_id TEXT,
                    result_message_id INTEGER,
                    last_error TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    claimed_at TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )
            conn.exec_driver_sql(
                """
                INSERT INTO agent_tasks (
                    id, parent_task_id, root_task_id, delegation_depth, may_delegate,
                    max_delegation_depth, max_running_descendants,
                    max_running_per_target, max_nonterminal_descendants,
                    target_member_id, created_by, content, status, created_at, updated_at
                ) VALUES
                    (1, NULL, 1, 0, 1, 1, 3, 1, 8,
                     'agent:codex', 'human:bobo', 'legacy root', 'running',
                     '2026-07-15', '2026-07-15'),
                    (2, 1, 1, 1, 0, NULL, NULL, NULL, NULL,
                     'agent:other', 'agent:codex', 'legacy child', 'queued',
                     '2026-07-15', '2026-07-15')
                """
            )

        db.init_db()

        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql(
                """
                SELECT
                    id, control_status, authorization_epoch,
                    authorized_slice_budget, reserved_slice_count,
                    authorization_expires_at
                FROM agent_tasks
                ORDER BY id
                """
            ).fetchall()

        self.assertEqual(rows[0][:5], (1, "active", 1, 2, 1))
        self.assertIsNotNone(rows[0][5])
        self.assertEqual(rows[1], (2, None, None, None, None, None))
