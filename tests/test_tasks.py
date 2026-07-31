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

    def _create_claimed_quality_root(
        self,
        client,
        *,
        project_id: str,
        slice_budget: int = 3,
        milestone_test_required: bool = False,
    ) -> dict:
        registered = client.post(
            "/api/projects",
            headers={"X-API-Key": "bobo-key"},
            json={"project_id": project_id, "display_name": project_id},
        )
        self.assertEqual(registered.status_code, 201)
        created = client.post(
            "/api/tasks",
            headers={"X-API-Key": "bobo-key"},
            json={
                "project_id": project_id,
                "target_member_id": "agent:codex",
                "content": "Coordinate a frozen quality batch",
                "may_delegate": True,
                "slice_budget": slice_budget,
                "max_running_descendants": 8,
                "max_running_per_target": 4,
                "max_nonterminal_descendants": 32,
                "milestone_test_required": milestone_test_required,
            },
        )
        self.assertEqual(created.status_code, 201)
        root = created.json()
        claimed = client.post(
            f"/api/tasks/{root['id']}/claim",
            headers={"X-API-Key": "codex-key"},
            json={},
        )
        self.assertEqual(claimed.status_code, 200)
        return claimed.json()

    def _create_quality_child(
        self,
        client,
        root: dict,
        *,
        target_member_id: str,
        content: str,
        task_kind: str,
        review_policy: str | None = None,
        related_task_ids: list[int] | None = None,
        trigger_task_id: int | None = None,
    ) -> dict:
        body = {
            "parent_task_id": root["id"],
            "authorization_epoch": root["authorization_epoch"],
            "target_member_id": target_member_id,
            "content": content,
            "task_kind": task_kind,
        }
        if review_policy is not None:
            body["review_policy"] = review_policy
        if related_task_ids is not None:
            body["related_task_ids"] = related_task_ids
        if trigger_task_id is not None:
            body["trigger_task_id"] = trigger_task_id
        response = client.post(
            "/api/tasks",
            headers={"X-API-Key": "codex-key"},
            json=body,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _claim_and_complete_quality_task(
        self,
        client,
        task: dict,
        *,
        api_key: str,
        from_id: str,
        result_text: str,
        gate_verdict: dict | None = None,
    ) -> tuple[dict, int]:
        claimed = client.post(
            f"/api/tasks/{task['id']}/claim",
            headers={"X-API-Key": api_key},
            json={},
        )
        self.assertEqual(claimed.status_code, 200, claimed.text)
        result = self.add_message(
            from_id=from_id,
            to_ids=f'["{task["created_by"]}"]',
            message_type="text",
            group_id=task["hall_group_id"],
            content=result_text,
        )
        body = {
            "status": "succeeded",
            "result_message_id": result.id,
            "claim_token": claimed.json()["claim_token"],
        }
        if gate_verdict is not None:
            body["gate_verdict"] = gate_verdict
        completed = client.post(
            f"/api/tasks/{task['id']}/complete",
            headers={"X-API-Key": api_key},
            json=body,
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        return completed.json(), int(result.id)

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
        self.assertEqual(created.json()["task_kind"], "general")
        self.assertIsNone(created.json()["review_policy"])
        self.assertIsNone(created.json()["gate_verdict"])
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
        self.assertEqual(created.json()["max_clarification_rounds"], 1)
        self.assertEqual(created.json()["clarification_round_count"], 0)
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

    def test_task_clarification_round_limit_is_bounded_to_one_or_two(self):
        with self.make_client() as client:
            custom = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Allow two rounds",
                    "max_clarification_rounds": 2,
                },
            )
            too_few = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Invalid zero rounds",
                    "max_clarification_rounds": 0,
                },
            )
            too_many = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Invalid unlimited rounds",
                    "max_clarification_rounds": 3,
                },
            )

        self.assertEqual(custom.status_code, 201)
        self.assertEqual(custom.json()["max_clarification_rounds"], 2)
        self.assertEqual(too_few.status_code, 422)
        self.assertEqual(too_many.status_code, 422)

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

    def test_typed_children_count_only_general_and_development_against_slice_budget(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_typed_budget",
                slice_budget=2,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Implement the first frozen slice",
                task_kind="development",
                review_policy="required",
            )
            completed_development, _ = self._claim_and_complete_quality_task(
                client,
                development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Development result",
            )
            collected_development = client.post(
                f"/api/tasks/{development['id']}/collect-result",
                headers={"X-API-Key": "codex-key"},
            )
            general = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Preserve a legacy general child",
                task_kind="general",
            )
            review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review the development result",
                task_kind="review",
                related_task_ids=[development["id"]],
            )
            reviewed, _ = self._claim_and_complete_quality_task(
                client,
                review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Please address the finding",
                gate_verdict={
                    "verdict": "changes_requested",
                    "summary": "One issue remains",
                    "findings": ["Add the missing boundary assertion"],
                },
            )
            rework = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Address the first review finding",
                task_kind="rework",
                related_task_ids=[development["id"]],
                trigger_task_id=review["id"],
            )
            blocked_extra_slice = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "Exceeds the two authorized slices",
                    "task_kind": "development",
                    "review_policy": "required",
                },
            )
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(development["task_kind"], "development")
        self.assertEqual(development["review_policy"], "required")
        self.assertEqual(completed_development["workflow_status"], "submitted")
        self.assertEqual(collected_development.status_code, 200)
        self.assertEqual(collected_development.json()["workflow_status"], "completed")
        self.assertEqual(general["task_kind"], "general")
        self.assertIsNone(general["review_policy"])
        self.assertEqual(review["task_kind"], "review")
        self.assertIsNone(review["review_policy"])
        self.assertEqual(reviewed["gate_verdict"]["verdict"], "changes_requested")
        self.assertEqual(rework["task_kind"], "rework")
        self.assertEqual(blocked_extra_slice.status_code, 409)
        self.assertIn("authorized slice budget 2 exhausted", blocked_extra_slice.json()["detail"])
        self.assertEqual(tree.status_code, 200)
        self.assertEqual(tree.json()["root"]["reserved_slice_count"], 2)
        self.assertEqual(tree.json()["remaining_slice_budget"], 0)
        self.assertEqual(
            {relation["relation_type"] for relation in tree.json()["relations"]},
            {"reviews", "reworks"},
        )

    def test_review_creation_enforces_policy_cardinality_and_reviewer_separation(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_review_policy",
                slice_budget=3,
            )
            required = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Required-review slice",
                task_kind="development",
                review_policy="required",
            )
            batch_targets = [
                self._create_quality_child(
                    client,
                    root,
                    target_member_id="agent:other",
                    content=f"Batch-review slice {index}",
                    task_kind="development",
                    review_policy="batch",
                )
                for index in range(2)
            ]
            for task in [required, *batch_targets]:
                self._claim_and_complete_quality_task(
                    client,
                    task,
                    api_key="other-key",
                    from_id="agent:other",
                    result_text=f"Frozen result for task {task['id']}",
                )

            same_reviewer = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "Reviewer cannot be the developer",
                    "task_kind": "review",
                    "related_task_ids": [required["id"]],
                },
            )
            required_with_two = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Required review cannot cover two slices",
                    "task_kind": "review",
                    "related_task_ids": [required["id"], batch_targets[0]["id"]],
                },
            )
            batch_with_one = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Batch review needs at least two slices",
                    "task_kind": "review",
                    "related_task_ids": [batch_targets[0]["id"]],
                },
            )
            batch_with_four = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Batch review cannot cover four slices",
                    "task_kind": "review",
                    "related_task_ids": [
                        *(task["id"] for task in batch_targets),
                        999_998,
                        999_999,
                    ],
                },
            )
            required_review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Independent required review",
                task_kind="review",
                related_task_ids=[required["id"]],
            )
            batch_review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Independent two-slice batch review",
                task_kind="review",
                related_task_ids=[task["id"] for task in batch_targets],
            )
            required_relations = client.get(
                f"/api/tasks/{required_review['id']}/relations",
                headers={"X-API-Key": "codex-key"},
            )
            batch_relations = client.get(
                f"/api/tasks/{batch_review['id']}/relations",
                headers={"X-API-Key": "codex-key"},
            )

        self.assertIn(same_reviewer.status_code, {400, 409})
        self.assertIn(required_with_two.status_code, {400, 409, 422})
        self.assertIn(batch_with_one.status_code, {400, 409, 422})
        self.assertIn(batch_with_four.status_code, {400, 409, 422})
        self.assertEqual(required_relations.status_code, 200)
        self.assertEqual(batch_relations.status_code, 200)
        self.assertEqual(
            [
                (item["relation_type"], item["target_task_id"])
                for item in required_relations.json()
            ],
            [("reviews", required["id"])],
        )
        self.assertEqual(
            {item["target_task_id"] for item in batch_relations.json()},
            {task["id"] for task in batch_targets},
        )
        self.assertEqual(
            {item["relation_type"] for item in batch_relations.json()},
            {"reviews"},
        )

    def test_batch_review_rejects_development_slices_from_different_authorization_epochs(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_review_epoch",
                slice_budget=2,
            )
            first = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Epoch one slice",
                task_kind="development",
                review_policy="batch",
            )
            self._claim_and_complete_quality_task(
                client,
                first,
                api_key="other-key",
                from_id="agent:other",
                result_text="Epoch one result",
            )
            checkpointed = client.post(
                f"/api/tasks/{root['id']}/checkpoint",
                headers={"X-API-Key": "codex-key"},
                json={"reason": "milestone"},
            )
            resumed = client.post(
                f"/api/tasks/{root['id']}/resume-tree",
                headers={"X-API-Key": "bobo-key"},
                json={"slice_budget": 2, "authorization_ttl_seconds": 60},
            )
            reclaimed = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            self.assertEqual(checkpointed.status_code, 200)
            self.assertEqual(resumed.status_code, 200)
            self.assertEqual(reclaimed.status_code, 200)
            current_root = reclaimed.json()
            second = self._create_quality_child(
                client,
                current_root,
                target_member_id="agent:other",
                content="Epoch two slice",
                task_kind="development",
                review_policy="batch",
            )
            self._claim_and_complete_quality_task(
                client,
                second,
                api_key="other-key",
                from_id="agent:other",
                result_text="Epoch two result",
            )
            mixed_epoch_review = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": current_root["id"],
                    "authorization_epoch": current_root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Must not cross authorization epochs",
                    "task_kind": "review",
                    "related_task_ids": [first["id"], second["id"]],
                },
            )

        self.assertIn(mixed_epoch_review.status_code, {400, 409})
        self.assertIn("authorization batch", mixed_epoch_review.json()["detail"].lower())

    def test_batch_review_accepts_three_slices_from_the_same_authorization_epoch(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_review_batch_three",
                slice_budget=3,
            )
            developments = [
                self._create_quality_child(
                    client,
                    root,
                    target_member_id="agent:other",
                    content=f"Same-epoch batch slice {index}",
                    task_kind="development",
                    review_policy="batch",
                )
                for index in range(3)
            ]
            for task in developments:
                self._claim_and_complete_quality_task(
                    client,
                    task,
                    api_key="other-key",
                    from_id="agent:other",
                    result_text=f"Same-epoch result {task['id']}",
                )
            review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review all three same-epoch slices",
                task_kind="review",
                related_task_ids=[task["id"] for task in developments],
            )
            relations = client.get(
                f"/api/tasks/{review['id']}/relations",
                headers={"X-API-Key": "codex-key"},
            )

        self.assertEqual(relations.status_code, 200)
        self.assertEqual(
            {relation["target_task_id"] for relation in relations.json()},
            {task["id"] for task in developments},
        )

    def test_legacy_general_task_still_completes_and_collects_without_quality_payload(self):
        with self.make_client() as client:
            created = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Legacy clients do not send quality fields",
                },
            )
            claimed = client.post(
                f"/api/tasks/{created.json()['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            result = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id=created.json()["hall_group_id"],
                content="Legacy general result",
            )
            completed = client.post(
                f"/api/tasks/{created.json()['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "result_message_id": result.id},
            )
            collected = client.post(
                f"/api/tasks/{created.json()['id']}/collect-result",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["task_kind"], "general")
        self.assertIsNone(created.json()["review_policy"])
        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["workflow_status"], "submitted")
        self.assertIsNone(completed.json()["gate_verdict"])
        self.assertEqual(collected.status_code, 200)
        self.assertEqual(collected.json()["workflow_status"], "completed")

    def test_review_completion_requires_a_valid_structured_verdict(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_verdict",
                slice_budget=2,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Produce a reviewable result",
                task_kind="development",
                review_policy="required",
            )
            self._claim_and_complete_quality_task(
                client,
                development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Reviewable development result",
            )
            review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Return a structured verdict",
                task_kind="review",
                related_task_ids=[development["id"]],
            )
            claimed = client.post(
                f"/api/tasks/{review['id']}/claim",
                headers={"X-API-Key": "third-key"},
                json={},
            )
            self.assertEqual(claimed.status_code, 200)
            result = self.add_message(
                from_id="agent:third",
                to_ids='["agent:codex"]',
                message_type="text",
                group_id=review["hall_group_id"],
                content="Structured review result",
            )
            base_body = {
                "status": "succeeded",
                "result_message_id": result.id,
                "claim_token": claimed.json()["claim_token"],
            }
            missing_verdict = client.post(
                f"/api/tasks/{review['id']}/complete",
                headers={"X-API-Key": "third-key"},
                json=base_body,
            )
            invalid_verdict = client.post(
                f"/api/tasks/{review['id']}/complete",
                headers={"X-API-Key": "third-key"},
                json={
                    **base_body,
                    "gate_verdict": {
                        "verdict": "looks_good",
                        "summary": "Not a supported verdict",
                        "findings": [],
                    },
                },
            )
            empty_change_findings = client.post(
                f"/api/tasks/{review['id']}/complete",
                headers={"X-API-Key": "third-key"},
                json={
                    **base_body,
                    "gate_verdict": {
                        "verdict": "changes_requested",
                        "summary": "A change is required",
                        "findings": [],
                    },
                },
            )
            wrong_reviewer = client.post(
                f"/api/tasks/{review['id']}/complete",
                headers={"X-API-Key": "other-key"},
                json={
                    **base_body,
                    "gate_verdict": {
                        "verdict": "approved",
                        "summary": "The developer cannot approve their own result",
                        "findings": [],
                    },
                },
            )
            approved = client.post(
                f"/api/tasks/{review['id']}/complete",
                headers={"X-API-Key": "third-key"},
                json={
                    **base_body,
                    "gate_verdict": {
                        "verdict": "approved",
                        "summary": "The frozen result is acceptable",
                        "findings": [],
                    },
                },
            )
            fetched = client.get(
                f"/api/tasks/{review['id']}",
                headers={"X-API-Key": "codex-key"},
            )

            blocked_development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Produce a result with an external blocker",
                task_kind="development",
                review_policy="required",
            )
            self._claim_and_complete_quality_task(
                client,
                blocked_development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Result awaiting an external dependency",
            )
            blocked_review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Record a blocked review",
                task_kind="review",
                related_task_ids=[blocked_development["id"]],
            )
            blocked, _ = self._claim_and_complete_quality_task(
                client,
                blocked_review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Cannot finish this review yet",
                gate_verdict={
                    "verdict": "blocked",
                    "summary": "External dependency is unavailable",
                    "findings": ["Wait for the dependency owner"],
                },
            )
            retry_after_blocked = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Retry the same frozen version after the blocker clears",
                task_kind="review",
                related_task_ids=[blocked_development["id"]],
            )

        self.assertIn(missing_verdict.status_code, {400, 422})
        self.assertEqual(invalid_verdict.status_code, 422)
        self.assertIn(empty_change_findings.status_code, {400, 422})
        self.assertEqual(wrong_reviewer.status_code, 403)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(
            approved.json()["gate_verdict"],
            {
                "verdict": "approved",
                "summary": "The frozen result is acceptable",
                "findings": [],
            },
        )
        self.assertEqual(fetched.json()["gate_verdict"], approved.json()["gate_verdict"])
        self.assertEqual(blocked["gate_verdict"]["verdict"], "blocked")
        self.assertEqual(retry_after_blocked["task_kind"], "review")

    def test_development_success_requires_result_message_but_not_gate_verdict(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_development_result",
                slice_budget=2,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Development must point to its frozen result",
                task_kind="development",
                review_policy="required",
            )
            claimed = client.post(
                f"/api/tasks/{development['id']}/claim",
                headers={"X-API-Key": "other-key"},
                json={},
            )
            missing_result = client.post(
                f"/api/tasks/{development['id']}/complete",
                headers={"X-API-Key": "other-key"},
                json={
                    "status": "succeeded",
                    "claim_token": claimed.json()["claim_token"],
                },
            )
            result = self.add_message(
                from_id="agent:other",
                to_ids='["agent:codex"]',
                message_type="text",
                group_id=development["hall_group_id"],
                content="Frozen development result",
            )
            completed = client.post(
                f"/api/tasks/{development['id']}/complete",
                headers={"X-API-Key": "other-key"},
                json={
                    "status": "succeeded",
                    "result_message_id": result.id,
                    "claim_token": claimed.json()["claim_token"],
                },
            )

        self.assertIn(missing_result.status_code, {400, 422})
        self.assertEqual(completed.status_code, 200)
        self.assertIsNone(completed.json()["gate_verdict"])

    def test_root_success_waits_for_latest_rework_review_and_exposes_quality_context(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_quality_gate",
                slice_budget=2,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Implement a required-review slice",
                task_kind="development",
                review_policy="required",
            )
            _, development_result_id = self._claim_and_complete_quality_task(
                client,
                development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Initial frozen result",
            )
            unreviewed_root = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": root["claim_token"]},
            )

            first_review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review the initial result",
                task_kind="review",
                related_task_ids=[development["id"]],
            )
            self._claim_and_complete_quality_task(
                client,
                first_review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Initial review requests changes",
                gate_verdict={
                    "verdict": "changes_requested",
                    "summary": "Boundary handling is incomplete",
                    "findings": ["Add the missing boundary behavior"],
                },
            )
            changed_root = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": root["claim_token"]},
            )
            duplicate_review = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "A second review cannot overwrite a rejected frozen version",
                    "task_kind": "review",
                    "related_task_ids": [development["id"]],
                },
            )

            rework = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Address the boundary finding",
                task_kind="rework",
                related_task_ids=[development["id"]],
                trigger_task_id=first_review["id"],
            )
            _, rework_result_id = self._claim_and_complete_quality_task(
                client,
                rework,
                api_key="other-key",
                from_id="agent:other",
                result_text="Updated frozen result",
            )
            pending_latest_review = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": root["claim_token"]},
            )
            latest_review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review the latest rework",
                task_kind="review",
                related_task_ids=[rework["id"]],
            )
            approved_review, _ = self._claim_and_complete_quality_task(
                client,
                latest_review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Latest rework is approved",
                gate_verdict={
                    "verdict": "approved",
                    "summary": "The boundary behavior is now covered",
                    "findings": [],
                },
            )
            rework_relations = client.get(
                f"/api/tasks/{rework['id']}/relations",
                headers={"X-API-Key": "codex-key"},
            )
            latest_review_relations = client.get(
                f"/api/tasks/{latest_review['id']}/relations",
                headers={"X-API-Key": "codex-key"},
            )
            rework_context = client.get(
                f"/api/tasks/{rework['id']}/quality-context",
                headers={"X-API-Key": "codex-key"},
            )
            review_context = client.get(
                f"/api/tasks/{latest_review['id']}/quality-context",
                headers={"X-API-Key": "third-key"},
            )
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )
            completed_root = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": root["claim_token"]},
            )

        self.assertEqual(unreviewed_root.status_code, 409)
        self.assertEqual(changed_root.status_code, 409)
        self.assertEqual(duplicate_review.status_code, 409)
        self.assertEqual(pending_latest_review.status_code, 409)
        self.assertEqual(approved_review["gate_verdict"]["verdict"], "approved")
        self.assertEqual(rework_relations.status_code, 200)
        self.assertEqual(len(rework_relations.json()), 1)
        self.assertEqual(rework_relations.json()[0]["relation_type"], "reworks")
        self.assertEqual(rework_relations.json()[0]["target_task_id"], development["id"])
        self.assertEqual(rework_relations.json()[0]["trigger_task_id"], first_review["id"])
        self.assertEqual(rework_relations.json()[0]["round_index"], 1)
        self.assertEqual(latest_review_relations.status_code, 200)
        self.assertEqual(
            [
                (item["relation_type"], item["target_task_id"], item["round_index"])
                for item in latest_review_relations.json()
            ],
            [("reviews", rework["id"], 1)],
        )
        self.assertEqual(rework_context.status_code, 200)
        self.assertEqual(rework_context.json()["task_id"], rework["id"])
        self.assertEqual(
            [item["task"]["id"] for item in rework_context.json()["related_tasks"]],
            [development["id"]],
        )
        self.assertEqual(
            [item["task"]["id"] for item in rework_context.json()["trigger_tasks"]],
            [first_review["id"]],
        )
        self.assertIn(
            development_result_id,
            [
                message["id"]
                for item in rework_context.json()["related_tasks"]
                for message in item["messages"]
            ],
        )
        self.assertEqual(review_context.status_code, 200)
        self.assertEqual(
            [item["task"]["id"] for item in review_context.json()["related_tasks"]],
            [rework["id"]],
        )
        self.assertIn(
            rework_result_id,
            [
                message["id"]
                for item in review_context.json()["related_tasks"]
                for message in item["messages"]
            ],
        )
        self.assertEqual(review_context.json()["trigger_tasks"], [])
        self.assertEqual(tree.status_code, 200)
        self.assertEqual(len(tree.json()["review_gates"]), 1)
        gate = tree.json()["review_gates"][0]
        self.assertEqual(gate["development_task_id"], development["id"])
        self.assertEqual(gate["current_subject_task_id"], rework["id"])
        self.assertEqual(gate["review_policy"], "required")
        self.assertEqual(
            gate["current_verdict"],
            {
                "verdict": "approved",
                "summary": "The boundary behavior is now covered",
                "findings": [],
            },
        )
        self.assertEqual(gate["review_task_id"], latest_review["id"])
        self.assertEqual(gate["rework_round"], 1)
        self.assertEqual(completed_root.status_code, 200)
        self.assertEqual(completed_root.json()["status"], "succeeded")

    def test_passed_milestone_test_pauses_for_human_acceptance_before_root_completion(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_milestone_gate",
                slice_budget=1,
                milestone_test_required=True,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Implement the milestone slice",
                task_kind="development",
                review_policy="required",
            )
            self._claim_and_complete_quality_task(
                client,
                development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Frozen milestone result",
            )
            premature_test = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Test before review approval",
                    "task_kind": "test",
                    "related_task_ids": [development["id"]],
                },
            )
            review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review the milestone slice",
                task_kind="review",
                related_task_ids=[development["id"]],
            )
            self._claim_and_complete_quality_task(
                client,
                review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Review approved",
                gate_verdict={
                    "verdict": "approved",
                    "summary": "The frozen slice is ready for milestone testing",
                    "findings": [],
                },
            )
            test_task = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Run full regression and black-box checks",
                task_kind="test",
                related_task_ids=[development["id"]],
            )
            duplicate_test = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Duplicate test for the same frozen version",
                    "task_kind": "test",
                    "related_task_ids": [development["id"]],
                },
            )
            passed_test, _ = self._claim_and_complete_quality_task(
                client,
                test_task,
                api_key="third-key",
                from_id="agent:third",
                result_text="Regression and black-box checks passed",
                gate_verdict={
                    "verdict": "passed",
                    "summary": "The latest frozen version passed the milestone suite",
                    "findings": [],
                },
            )
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )
            stale_root_completion = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": root["claim_token"]},
            )
            agent_accept = client.post(
                f"/api/tasks/{root['id']}/accept-milestone",
                headers={"X-API-Key": "codex-key"},
            )
            accepted = client.post(
                f"/api/tasks/{root['id']}/accept-milestone",
                headers={"X-API-Key": "bobo-key"},
            )
            reclaimed = client.post(
                f"/api/tasks/{root['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            completed_root = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={
                    "status": "succeeded",
                    "claim_token": reclaimed.json()["claim_token"],
                },
            )

        self.assertEqual(premature_test.status_code, 409)
        self.assertEqual(duplicate_test.status_code, 409)
        self.assertEqual(passed_test["gate_verdict"]["verdict"], "passed")
        self.assertEqual(tree.status_code, 200)
        payload = tree.json()
        self.assertEqual(payload["root"]["control_status"], "awaiting_human")
        self.assertEqual(payload["root"]["checkpoint_reason"], "milestone")
        self.assertTrue(payload["test_gate"]["required"])
        self.assertEqual(payload["test_gate"]["frozen_task_ids"], [development["id"]])
        self.assertEqual(payload["test_gate"]["test_task_id"], test_task["id"])
        self.assertTrue(payload["test_gate"]["satisfied"])
        self.assertEqual(stale_root_completion.status_code, 409)
        self.assertEqual(agent_accept.status_code, 403)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["root"]["control_status"], "active")
        self.assertEqual(accepted.json()["remaining_slice_budget"], 0)
        self.assertEqual(reclaimed.status_code, 200)
        self.assertEqual(completed_root.status_code, 200)
        self.assertEqual(completed_root.json()["status"], "succeeded")

    def test_exhausted_non_milestone_batch_auto_checkpoints_after_review(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_batch_checkpoint",
                slice_budget=1,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Implement the only authorized slice",
                task_kind="development",
                review_policy="required",
            )
            self._claim_and_complete_quality_task(
                client,
                development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Frozen batch result",
            )
            review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review the exhausted batch",
                task_kind="review",
                related_task_ids=[development["id"]],
            )
            self._claim_and_complete_quality_task(
                client,
                review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Batch review approved",
                gate_verdict={
                    "verdict": "approved",
                    "summary": "The authorized batch is safe to checkpoint",
                    "findings": [],
                },
            )
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(tree.status_code, 200)
        self.assertEqual(tree.json()["root"]["control_status"], "awaiting_human")
        self.assertEqual(tree.json()["root"]["checkpoint_reason"], "batch_limit")
        self.assertEqual(tree.json()["remaining_slice_budget"], 0)

    def test_milestone_test_must_cover_every_latest_frozen_slice(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_complete_milestone_set",
                slice_budget=2,
                milestone_test_required=True,
            )
            developments = [
                self._create_quality_child(
                    client,
                    root,
                    target_member_id="agent:other",
                    content=f"Implement batch slice {index}",
                    task_kind="development",
                    review_policy="batch",
                )
                for index in (1, 2)
            ]
            for index, development in enumerate(developments, start=1):
                self._claim_and_complete_quality_task(
                    client,
                    development,
                    api_key="other-key",
                    from_id="agent:other",
                    result_text=f"Frozen batch slice {index}",
                )
            review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review the complete frozen batch",
                task_kind="review",
                related_task_ids=[task["id"] for task in developments],
            )
            self._claim_and_complete_quality_task(
                client,
                review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Complete batch review approved",
                gate_verdict={
                    "verdict": "approved",
                    "summary": "Both frozen slices are ready for milestone testing",
                    "findings": [],
                },
            )
            partial_test = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:third",
                    "content": "Incorrectly test only one frozen slice",
                    "task_kind": "test",
                    "related_task_ids": [developments[0]["id"]],
                },
            )
            complete_test = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Test the complete latest frozen set",
                task_kind="test",
                related_task_ids=[task["id"] for task in developments],
            )
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(partial_test.status_code, 409)
        self.assertEqual(complete_test["task_kind"], "test")
        self.assertEqual(
            tree.json()["test_gate"]["frozen_task_ids"],
            [task["id"] for task in developments],
        )
        self.assertEqual(tree.json()["test_gate"]["test_task_id"], complete_test["id"])

    def test_failed_test_can_trigger_rework_and_old_verdict_does_not_cover_new_version(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_test_rework",
                slice_budget=1,
                milestone_test_required=True,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Implement the milestone",
                task_kind="development",
                review_policy="required",
            )
            self._claim_and_complete_quality_task(
                client,
                development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Initial milestone version",
            )
            review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review the initial version",
                task_kind="review",
                related_task_ids=[development["id"]],
            )
            self._claim_and_complete_quality_task(
                client,
                review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Initial review approved",
                gate_verdict={
                    "verdict": "approved",
                    "summary": "Ready for milestone testing",
                    "findings": [],
                },
            )
            failed_test = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Run the milestone suite",
                task_kind="test",
                related_task_ids=[development["id"]],
            )
            self._claim_and_complete_quality_task(
                client,
                failed_test,
                api_key="third-key",
                from_id="agent:third",
                result_text="Milestone suite found a regression",
                gate_verdict={
                    "verdict": "failed",
                    "summary": "The black-box workflow regressed",
                    "findings": ["The submit action does not reach the result state"],
                },
            )
            rework = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Repair the failed black-box workflow",
                task_kind="rework",
                related_task_ids=[development["id"]],
                trigger_task_id=failed_test["id"],
            )
            self._claim_and_complete_quality_task(
                client,
                rework,
                api_key="other-key",
                from_id="agent:other",
                result_text="Repaired milestone version",
            )
            latest_review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Review the repaired version",
                task_kind="review",
                related_task_ids=[rework["id"]],
            )
            self._claim_and_complete_quality_task(
                client,
                latest_review,
                api_key="third-key",
                from_id="agent:third",
                result_text="Repaired version approved",
                gate_verdict={
                    "verdict": "approved",
                    "summary": "The repair is ready for a fresh milestone test",
                    "findings": [],
                },
            )
            stale_test_root_completion = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": root["claim_token"]},
            )
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )
            fresh_test = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="Retest the repaired frozen version",
                task_kind="test",
                related_task_ids=[rework["id"]],
            )

        self.assertEqual(stale_test_root_completion.status_code, 409)
        self.assertEqual(tree.status_code, 200)
        self.assertEqual(tree.json()["root"]["control_status"], "active")
        self.assertEqual(tree.json()["test_gate"]["frozen_task_ids"], [rework["id"]])
        self.assertIsNone(tree.json()["test_gate"]["test_task_id"])
        self.assertFalse(tree.json()["test_gate"]["satisfied"])
        self.assertEqual(fresh_test["task_kind"], "test")

    def test_third_changes_requested_exhausts_two_rework_rounds_and_pauses_root(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_rework_limit",
                slice_budget=1,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Initial implementation",
                task_kind="development",
                review_policy="required",
            )
            self._claim_and_complete_quality_task(
                client,
                development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Initial result",
            )

            current_subject = development
            reviews: list[dict] = []
            reworks: list[dict] = []
            for round_index in range(1, 4):
                review = self._create_quality_child(
                    client,
                    root,
                    target_member_id="agent:third",
                    content=f"Review quality round {round_index}",
                    task_kind="review",
                    related_task_ids=[current_subject["id"]],
                )
                reviews.append(review)
                self._claim_and_complete_quality_task(
                    client,
                    review,
                    api_key="third-key",
                    from_id="agent:third",
                    result_text=f"Round {round_index} requests another change",
                    gate_verdict={
                        "verdict": "changes_requested",
                        "summary": f"Round {round_index} is not approved",
                        "findings": [f"Unresolved finding {round_index}"],
                    },
                )
                if round_index <= 2:
                    rework = self._create_quality_child(
                        client,
                        root,
                        target_member_id="agent:other",
                        content=f"Rework round {round_index}",
                        task_kind="rework",
                        related_task_ids=[development["id"]],
                        trigger_task_id=review["id"],
                    )
                    reworks.append(rework)
                    self._claim_and_complete_quality_task(
                        client,
                        rework,
                        api_key="other-key",
                        from_id="agent:other",
                        result_text=f"Reworked result {round_index}",
                    )
                    current_subject = rework

            forbidden_third_rework = client.post(
                "/api/tasks",
                headers={"X-API-Key": "codex-key"},
                json={
                    "parent_task_id": root["id"],
                    "authorization_epoch": root["authorization_epoch"],
                    "target_member_id": "agent:other",
                    "content": "A third automatic rework must not be created",
                    "task_kind": "rework",
                    "related_task_ids": [development["id"]],
                    "trigger_task_id": reviews[-1]["id"],
                },
            )
            blocked_root_completion = client.post(
                f"/api/tasks/{root['id']}/complete",
                headers={"X-API-Key": "codex-key"},
                json={"status": "succeeded", "claim_token": root["claim_token"]},
            )
            tree = client.get(
                f"/api/tasks/{root['id']}/tree",
                headers={"X-API-Key": "bobo-key"},
            )
            rework_relations = [
                client.get(
                    f"/api/tasks/{task['id']}/relations",
                    headers={"X-API-Key": "codex-key"},
                ).json()[0]
                for task in reworks
            ]

        self.assertEqual(forbidden_third_rework.status_code, 409)
        self.assertEqual(blocked_root_completion.status_code, 409)
        self.assertEqual(tree.status_code, 200)
        payload = tree.json()
        self.assertEqual(payload["root"]["control_status"], "awaiting_human")
        self.assertEqual(payload["root"]["checkpoint_reason"], "review_exhausted")
        self.assertEqual(
            [task["task_kind"] for task in payload["tasks"]].count("review"),
            3,
        )
        self.assertEqual(
            [task["task_kind"] for task in payload["tasks"]].count("rework"),
            2,
        )
        self.assertEqual(
            [relation["round_index"] for relation in rework_relations],
            [1, 2],
        )
        self.assertEqual(payload["root"]["reserved_slice_count"], 1)
        self.assertEqual(payload["remaining_slice_budget"], 0)
        self.assertEqual(len(payload["review_gates"]), 1)
        self.assertEqual(
            payload["review_gates"][0]["current_verdict"],
            {
                "verdict": "changes_requested",
                "summary": "Round 3 is not approved",
                "findings": ["Unresolved finding 3"],
            },
        )
        self.assertEqual(payload["review_gates"][0]["rework_round"], 2)

    def test_concurrent_reviews_cannot_cover_the_same_frozen_version_twice(self):
        with self.make_client() as client:
            root = self._create_claimed_quality_root(
                client,
                project_id="prj_review_race",
                slice_budget=1,
            )
            development = self._create_quality_child(
                client,
                root,
                target_member_id="agent:other",
                content="Produce one frozen version for a review race",
                task_kind="development",
                review_policy="required",
            )
            self._claim_and_complete_quality_task(
                client,
                development,
                api_key="other-key",
                from_id="agent:other",
                result_text="Frozen result for concurrent review creation",
            )
            failed_review = self._create_quality_child(
                client,
                root,
                target_member_id="agent:third",
                content="A runner failure must not permanently lock this version",
                task_kind="review",
                related_task_ids=[development["id"]],
            )
            failed_claim = client.post(
                f"/api/tasks/{failed_review['id']}/claim",
                headers={"X-API-Key": "third-key"},
                json={},
            )
            failed_completion = client.post(
                f"/api/tasks/{failed_review['id']}/complete",
                headers={"X-API-Key": "third-key"},
                json={
                    "status": "failed",
                    "last_error": "review runner crashed",
                    "claim_token": failed_claim.json()["claim_token"],
                },
            )
            failed_relations = client.get(
                f"/api/tasks/{failed_review['id']}/relations",
                headers={"X-API-Key": "codex-key"},
            )

        self.assertEqual(failed_completion.status_code, 200)
        self.assertIsNone(failed_relations.json()[0]["round_index"])

        barrier = Barrier(2)

        def create_review(label: str):
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    "/api/tasks",
                    headers={"X-API-Key": "codex-key"},
                    json={
                        "parent_task_id": root["id"],
                        "authorization_epoch": root["authorization_epoch"],
                        "target_member_id": "agent:third",
                        "content": f"Concurrent review {label}",
                        "task_kind": "review",
                        "related_task_ids": [development["id"]],
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(create_review, ("A", "B")))

        self.assertEqual(
            sorted(response.status_code for response in responses),
            [201, 409],
        )
        created_review = next(
            response.json()
            for response in responses
            if response.status_code == 201
        )
        with self.make_client() as client:
            relations = client.get(
                f"/api/tasks/{created_review['id']}/relations",
                headers={"X-API-Key": "codex-key"},
            )
        self.assertEqual(relations.status_code, 200)
        self.assertEqual(relations.json()[0]["round_index"], 0)

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
            wrong_question = self.add_message(
                from_id="human:bobo",
                to_ids='["agent:codex"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="This is not an assignee question",
            )
            invalid_boundary = client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "codex-key"},
                json={"question_message_id": wrong_question.id},
            )
            question = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="Which format should I use?",
            )
            clarification = client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "codex-key"},
                json={"question_message_id": question.id},
            )
            clarification_again = client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "codex-key"},
                json={"question_message_id": question.id},
            )
            blocked_claim = client.post(
                f"/api/tasks/{task['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            blocked_accept = client.post(
                f"/api/tasks/{task['id']}/accept",
                headers={"X-API-Key": "codex-key"},
            )
            first_answer = self.add_message(
                from_id="human:bobo",
                to_ids='["agent:codex"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="Use Markdown.",
            )
            answer_end = self.add_message(
                from_id="human:bobo",
                to_ids='["agent:codex"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="Include a short summary too.",
            )
            before_submit = client.get(
                f"/api/tasks/{task['id']}",
                headers={"X-API-Key": "bobo-key"},
            )
            answered = client.post(
                f"/api/tasks/{task['id']}/submit-clarification-answer",
                headers={"X-API-Key": "bobo-key"},
                json={"answer_message_id": answer_end.id},
            )
            answered_again = client.post(
                f"/api/tasks/{task['id']}/submit-clarification-answer",
                headers={"X-API-Key": "bobo-key"},
                json={"answer_message_id": answer_end.id},
            )
            rounds = client.get(
                f"/api/tasks/{task['id']}/clarification-rounds",
                headers={"X-API-Key": "bobo-key"},
            )
            blocked_claim_after_answer = client.post(
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
        self.assertEqual(invalid_boundary.status_code, 400)
        self.assertEqual(clarification.json()["workflow_status"], "clarification_requested")
        self.assertEqual(clarification_again.json()["clarification_round_count"], 1)
        self.assertEqual(clarification.json()["clarification_round_count"], 1)
        self.assertEqual(blocked_claim.status_code, 409)
        self.assertEqual(blocked_accept.status_code, 409)
        self.assertEqual(before_submit.json()["workflow_status"], "clarification_requested")
        self.assertEqual(answered.json()["workflow_status"], "clarification_answered")
        self.assertEqual(answered_again.json()["workflow_status"], "clarification_answered")
        self.assertEqual(blocked_claim_after_answer.status_code, 409)
        self.assertEqual(len(rounds.json()), 1)
        self.assertEqual(rounds.json()[0]["question_message_id"], question.id)
        self.assertEqual(rounds.json()[0]["answer_start_message_id"], first_answer.id)
        self.assertEqual(rounds.json()[0]["answer_end_message_id"], answer_end.id)
        self.assertEqual(accepted.json()["workflow_status"], "accepted")
        self.assertEqual(claimed.json()["workflow_status"], "in_progress")
        self.assertEqual(wrong_submission.status_code, 400)
        self.assertEqual(submitted.json()["status"], "succeeded")
        self.assertEqual(submitted.json()["workflow_status"], "submitted")
        self.assertIsNone(submitted.json()["result_collected_at"])
        self.assertEqual(wrong_collector.status_code, 403)
        self.assertEqual(collected.json()["workflow_status"], "completed")
        self.assertIsNotNone(collected.json()["result_collected_at"])

    def test_clarification_round_limit_escalates_and_requires_explicit_resolution(self):
        with self.make_client() as client:
            task = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "target_member_id": "agent:codex",
                    "content": "Bounded clarification",
                    "max_clarification_rounds": 1,
                },
            ).json()
            question_one = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="First question",
            )
            client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "codex-key"},
                json={"question_message_id": question_one.id},
            )
            answer_one = self.add_message(
                from_id="human:bobo",
                to_ids='["agent:codex"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="First answer",
            )
            client.post(
                f"/api/tasks/{task['id']}/submit-clarification-answer",
                headers={"X-API-Key": "bobo-key"},
                json={"answer_message_id": answer_one.id},
            )
            question_two = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="Second question",
            )
            escalated = client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "codex-key"},
                json={"question_message_id": question_two.id},
            )
            blocked_claim = client.post(
                f"/api/tasks/{task['id']}/claim",
                headers={"X-API-Key": "codex-key"},
                json={},
            )
            wrong_resolver = client.post(
                f"/api/tasks/{task['id']}/resolve-clarification",
                headers={"X-API-Key": "other-key"},
                json={"allow_additional_round": True},
            )
            resolved = client.post(
                f"/api/tasks/{task['id']}/resolve-clarification",
                headers={"X-API-Key": "bobo-key"},
                json={"allow_additional_round": True},
            )
            resumed = client.post(
                f"/api/tasks/{task['id']}/resume-tree",
                headers={"X-API-Key": "bobo-key"},
                json={"slice_budget": 0, "authorization_ttl_seconds": 60},
            )
            second_round = client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "codex-key"},
                json={"question_message_id": question_two.id},
            )
            answer_two = self.add_message(
                from_id="human:bobo",
                to_ids='["agent:codex"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="Second answer",
            )
            client.post(
                f"/api/tasks/{task['id']}/submit-clarification-answer",
                headers={"X-API-Key": "bobo-key"},
                json={"answer_message_id": answer_two.id},
            )
            question_three = self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content="Third question",
            )
            escalated_again = client.post(
                f"/api/tasks/{task['id']}/request-clarification",
                headers={"X-API-Key": "codex-key"},
                json={"question_message_id": question_three.id},
            )
            cannot_exceed_limit = client.post(
                f"/api/tasks/{task['id']}/resolve-clarification",
                headers={"X-API-Key": "bobo-key"},
                json={"allow_additional_round": True},
            )

        self.assertEqual(escalated.status_code, 200)
        self.assertEqual(escalated.json()["workflow_status"], "needs_decision")
        self.assertEqual(escalated.json()["control_status"], "awaiting_human")
        self.assertEqual(blocked_claim.status_code, 409)
        self.assertEqual(wrong_resolver.status_code, 403)
        self.assertEqual(resolved.json()["workflow_status"], "clarification_answered")
        self.assertEqual(resolved.json()["max_clarification_rounds"], 2)
        self.assertEqual(resolved.json()["control_status"], "awaiting_human")
        self.assertEqual(resumed.json()["root"]["control_status"], "active")
        self.assertEqual(second_round.json()["workflow_status"], "clarification_requested")
        self.assertEqual(second_round.json()["clarification_round_count"], 2)
        self.assertEqual(escalated_again.json()["workflow_status"], "needs_decision")
        self.assertEqual(cannot_exceed_limit.status_code, 409)

    def test_concurrent_clarification_requests_open_only_one_round(self):
        with self.make_client() as client:
            task = client.post(
                "/api/tasks",
                headers={"X-API-Key": "bobo-key"},
                json={"target_member_id": "agent:codex", "content": "Concurrent clarification"},
            ).json()
        questions = [
            self.add_message(
                from_id="agent:codex",
                to_ids='["human:bobo"]',
                message_type="text",
                group_id=task["hall_group_id"],
                content=f"Question {index}",
            )
            for index in range(2)
        ]
        barrier = Barrier(2)

        def request_round(question_id: int):
            with self.make_client() as client:
                barrier.wait()
                return client.post(
                    f"/api/tasks/{task['id']}/request-clarification",
                    headers={"X-API-Key": "codex-key"},
                    json={"question_message_id": question_id},
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(request_round, [int(item.id) for item in questions]))

        with self.make_client() as client:
            current = client.get(
                f"/api/tasks/{task['id']}",
                headers={"X-API-Key": "bobo-key"},
            ).json()
            rounds = client.get(
                f"/api/tasks/{task['id']}/clarification-rounds",
                headers={"X-API-Key": "bobo-key"},
            ).json()

        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        self.assertEqual(current["clarification_round_count"], 1)
        self.assertEqual(len(rounds), 1)

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
            conn.exec_driver_sql("DROP TABLE IF EXISTS agent_task_relations")
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
            clarification_indexes = {
                row[1]: row[2]
                for row in conn.exec_driver_sql(
                    "PRAGMA index_list(agent_task_clarification_rounds)"
                ).fetchall()
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
                    authorization_expires_at, checkpoint_reason,
                    max_clarification_rounds, clarification_round_count
                FROM agent_tasks
                ORDER BY id
                """
            ).fetchall()
            quality_rows = conn.exec_driver_sql(
                """
                SELECT id, task_kind, review_policy, gate_verdict, milestone_test_required
                FROM agent_tasks
                ORDER BY id
                """
            ).fetchall()
            relation_columns = {
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA table_info(agent_task_relations)"
                ).fetchall()
            }
            relation_indexes = conn.exec_driver_sql(
                "PRAGMA index_list(agent_task_relations)"
            ).fetchall()
            relation_index_columns = {
                tuple(
                    item[2]
                    for item in conn.exec_driver_sql(
                        f"PRAGMA index_info('{row[1]}')"
                    ).fetchall()
                ): bool(row[2])
                for row in relation_indexes
            }
            relation_rows = conn.exec_driver_sql(
                """
                SELECT
                    source_task_id, target_task_id, relation_type,
                    trigger_task_id, round_index
                FROM agent_task_relations
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
            "max_clarification_rounds",
            "clarification_round_count",
            "task_kind",
            "review_policy",
            "gate_verdict",
            "milestone_test_required",
        }.issubset(columns))
        self.assertEqual(indexes["ix_agent_tasks_hall_group_id"], 1)
        self.assertEqual(indexes["ix_agent_tasks_lease_expires_at"], 0)
        self.assertEqual(indexes["ix_agent_tasks_parent_task_id"], 0)
        self.assertEqual(indexes["ix_agent_tasks_root_task_id"], 0)
        self.assertEqual(indexes["ix_agent_tasks_delegation_depth"], 0)
        self.assertEqual(indexes["ix_agent_tasks_control_status"], 0)
        self.assertEqual(indexes["ix_agent_tasks_authorization_expires_at"], 0)
        self.assertEqual(clarification_indexes["uq_task_clarification_round_index"], 1)
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
                (task_id, "active", 0, 0, 0, None, None, 1, 0)
                for task_id in range(1, 6)
            ],
        )
        self.assertEqual(
            quality_rows,
            [
                (task_id, "general", None, None, 0)
                for task_id in range(1, 6)
            ],
        )
        self.assertTrue(
            {
                "id",
                "source_task_id",
                "target_task_id",
                "relation_type",
                "trigger_task_id",
                "round_index",
                "created_at",
            }.issubset(relation_columns)
        )
        self.assertTrue(
            any(
                columns == ("source_task_id",)
                for columns in relation_index_columns
            )
        )
        self.assertTrue(
            any(
                columns == ("target_task_id",)
                for columns in relation_index_columns
            )
        )
        self.assertTrue(
            any(
                columns == ("trigger_task_id",)
                for columns in relation_index_columns
            )
        )
        self.assertTrue(
            any(
                is_unique
                and columns[:3]
                == ("source_task_id", "target_task_id", "relation_type")
                for columns, is_unique in relation_index_columns.items()
            )
        )
        self.assertEqual(relation_rows, [])

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
