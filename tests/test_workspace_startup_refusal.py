"""W3a workspace-v1 启动拒绝：真实 startup API + 隔离 SQLite，不启动真实角色。"""
from __future__ import annotations

import unittest
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from server import role_startup
from scripts import talk_runtime
from scripts.role_service_host import HostError
from tests.test_role_services import PROJECT_ID, RoleServiceTestCase, encode


class WorkspaceStartupRefusalTests(RoleServiceTestCase):
    def setUp(self):
        super().setUp()
        self.set_layout("workspace-v1")
        self.health = {
            "pid": 123,
            # runtime 启动晚于偏好写入，避免被既有“人工选择变更”守卫跳过。
            "started_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        self.runtime_config = {"hosts": []}
        proof = patch.object(
            role_startup,
            "verified_runtime",
            side_effect=lambda *args: (self.runtime_config, self.health, datetime.now(timezone.utc)),
        )
        proof.start()
        self.addCleanup(proof.stop)

    def set_layout(self, layout):
        with self.session() as session:
            from server.models import ProjectRole
            role = session.get(ProjectRole, (PROJECT_ID, self.role_a))
            role.storage_layout = layout
            session.add(role)
            session.commit()

    def preference(self):
        with self.make_client() as client:
            response = client.put(
                f"/api/projects/{PROJECT_ID}/roles/{encode(self.role_a)}/startup",
                headers={"X-API-Key": "bobo-key"},
                json={"enabled": True},
            )
        self.assertEqual(response.status_code, 200, response.text)

    def runtime(self):
        case = self

        class ApiClient:
            def __init__(self):
                self.bodies = []

            def request(self, method, path, body=None, **kwargs):
                if body is not None:
                    self.bodies.append(body)
                with case.make_client() as client:
                    response = client.request(
                        method,
                        path,
                        headers={"X-API-Key": "bobo-key"},
                        json=body,
                    )
                if response.status_code >= 400:
                    raise HostError(str(response.json().get("detail") or response.status_code))
                return response.json()

        client = ApiClient()
        instance = talk_runtime.TalkRuntime(
            {
                "project_id": PROJECT_ID,
                "project_root": self._tmpdir,
                "state_dir": self._tmpdir,
            },
            client=client,
            attach_api=True,
        )
        instance.startup_support = "supported"
        return instance, client

    def activate_once(self, instance):
        instance.startup_tick()
        instance.startup_thread.join(5)
        self.assertFalse(instance.startup_thread.is_alive())
        self.assertEqual(instance.startup_state, "complete", instance.startup_error)

    def test_runtime_startup_skips_workspace_without_service_or_launch(self):
        self.preference()
        instance, client = self.runtime()
        self.activate_once(instance)
        self.assertEqual(client.bodies, [{
            "activation_id": instance.activation_id,
            "workspace_runtime_guard": True,
        }])
        self.assertIsNone(self.state_row())
        self.assertEqual(self.launch_rows(), [])
        self.assertEqual(instance.statuses[self.role_a], {
            "state": "workspace_runtime_not_ready",
            "error_code": "workspace_runtime_not_ready",
            "error_message": "角色已准备，运行时隔离待启用",
        })
        with self.session() as session:
            from server.models import RoleStartupActivation
            receipt = session.get(
                RoleStartupActivation,
                (PROJECT_ID, instance.activation_id, self.role_a),
            )
        self.assertEqual(receipt.status, "skipped")
        self.assertEqual(receipt.error_code, "workspace_runtime_not_ready")

    def test_runtime_startup_keeps_legacy_original_path(self):
        self.set_layout("legacy")
        self.preference()
        instance, client = self.runtime()
        self.activate_once(instance)
        state = self.state_row()
        self.assertEqual(state.observed_state, "starting")
        self.assertEqual(state.generation, 1)
        self.assertEqual(len(self.launch_rows()), 1)
        self.assertNotIn(self.role_a, instance.statuses)

    def test_single_start_and_batch_skip_without_writing(self):
        response = self.start()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "workspace_runtime_not_ready")
        response = self.start_all()
        self.assertEqual(response.status_code, 200, response.text)
        result = next(r for r in response.json()["results"] if r["member_id"] == self.role_a)
        self.assertEqual(result["status"], "skipped_workspace_runtime_not_ready")
        self.assertEqual(result["error_code"], "workspace_runtime_not_ready")
        self.assertEqual(response.json()["counts"]["skipped"], 1)
        self.assertIsNone(self.state_row())
        self.assertEqual(self.launch_rows(), [])

    def test_startup_ignores_client_guard_for_every_value(self):
        self.preference()
        for index, guard in enumerate((None, False, True)):
            body = {"activation_id": str(index + 1) * 32}
            if guard is not None:
                body["workspace_runtime_guard"] = guard
            with patch.object(role_startup, "_cold_recover", side_effect=AssertionError("unexpected recovery")):
                with self.make_client() as client:
                    response = client.post(
                        f"/api/projects/{PROJECT_ID}/role-services/startup",
                        headers={"X-API-Key": "bobo-key"}, json=body)
            self.assertEqual(response.status_code, 200, response.text)
            result = next(r for r in response.json()["results"] if r["member_id"] == self.role_a)
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["error_code"], "workspace_runtime_not_ready")
            self.assertIsNone(self.state_row())
            self.assertEqual(self.launch_rows(), [])

    def test_first_configuration_enqueue_rejects_without_writes(self):
        import server.db as db
        from server.role_services import enqueue_auto_start_launch, _now
        with self.session() as session:
            db.begin_immediate_write(session)
            launch, error = enqueue_auto_start_launch(PROJECT_ID, self.role_a, session=session, now=_now())
            session.commit()
        self.assertIsNone(launch)
        self.assertEqual(error, "workspace_runtime_not_ready")
        self.assertIsNone(self.state_row())
        self.assertEqual(self.launch_rows(), [])

    def test_deployment_flag_cannot_open_unimplemented_capability(self):
        import os
        with patch.dict(os.environ, {"TALK_WORKSPACE_RUNTIME_ENABLED": "true"}):
            response = self.start()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "workspace_runtime_not_ready")
        self.assertIsNone(self.state_row())
        self.assertEqual(self.launch_rows(), [])

    def test_startup_does_not_recover_existing_workspace_ownership(self):
        self.preference()
        self.set_layout("legacy")
        started, claim = self.start_and_claim()
        self.set_layout("workspace-v1")
        before = self.state_row()
        with patch.object(role_startup, "_cold_recover", side_effect=AssertionError("unexpected recovery")):
            with self.make_client() as client:
                response = client.post(
                    f"/api/projects/{PROJECT_ID}/role-services/startup",
                    headers={"X-API-Key": "bobo-key"}, json={"activation_id": "f" * 32})
        self.assertEqual(response.status_code, 200, response.text)
        result = next(r for r in response.json()["results"] if r["member_id"] == self.role_a)
        self.assertEqual(result["error_code"], "workspace_runtime_not_ready")
        after = self.state_row()
        self.assertEqual((after.generation, after.desired_state, after.process_launch_id),
                         (before.generation, before.desired_state, before.process_launch_id))
        self.assertEqual(len(self.launch_rows()), 1)

    def test_unknown_layout_fails_closed(self):
        from fastapi import HTTPException
        from server.role_services import start_role_service
        self.set_layout("future-layout")
        with self.session() as session:
            with self.assertRaises(HTTPException) as caught:
                start_role_service(PROJECT_ID, self.role_a, self.human_member(), session)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertEqual(caught.exception.detail, "workspace_runtime_not_ready")
            session.rollback()
        self.assertIsNone(self.state_row())
        self.assertEqual(self.launch_rows(), [])

    def test_stop_still_cancels_existing_start(self):
        self.set_layout("legacy")
        started = self.start()
        self.assertEqual(started.status_code, 200, started.text)
        self.set_layout("workspace-v1")
        stopped = self.stop()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(self.state_row().desired_state, "stopped")

    def test_layout_query_exposes_layout_and_legacy_absence_is_allowed(self):
        with self.make_client() as client:
            response = client.get(
                f"/api/projects/{PROJECT_ID}/role-storage-layouts",
                headers={"X-API-Key": "bobo-key"},
            )
        row = next(item for item in response.json() if item["member_id"] == self.role_a)
        self.assertEqual(row["storage_layout"], "workspace-v1")
        from scripts.role_service_host import is_workspace_v1
        self.assertFalse(is_workspace_v1({"member_id": "agent:old"}))
        self.assertFalse(is_workspace_v1({"member_id": "agent:old", "storage_layout": "legacy"}))


class WorkspaceCapabilityGateTests(WorkspaceStartupRefusalTests):
    def setUp(self):
        super().setUp()
        self.capability_path = Path(self._tmpdir) / "runtime" / "capability.json"
        self.capability_path.parent.mkdir(exist_ok=True)
        self.manifest = {
            "schema": "talk-runtime-capability-1", "runtime_protocol": "talk-runtime-1",
            "supported_layouts": ["legacy", "workspace-v1"], "pid": os.getpid(),
            "started_at": "2026-11-07T00:00:00Z", "written_at": "2026-11-07T00:00:00+00:00",
        }
        binding = patch("server.local_runtime.configured_runtime", return_value=(
            Path(self._tmpdir) / "config.json", {
                "state_dir": self._tmpdir, "project_id": "fixture-unrelated"}))
        binding.start()
        self.addCleanup(binding.stop)
        launcher = patch("server.local_runtime.ensure_local_runtime", return_value="disabled")
        launcher.start()
        self.addCleanup(launcher.stop)
        flag = patch.dict(os.environ, {}, clear=False)
        flag.start()
        os.environ.pop("TALK_WORKSPACE_RUNTIME_ENABLED", None)
        self.addCleanup(flag.stop)

    def write_manifest(self, value):
        self.capability_path.write_text(json.dumps(value), encoding="utf-8")

    def test_rejection_matrix_at_single_start(self):
        variants = [
            (None, self.manifest), ("False", self.manifest), ("true", self.manifest),
            ("1", None), ("1", {**self.manifest, "schema": "bad"}),
            ("1", {**self.manifest, "runtime_protocol": 1}),
            ("1", {**self.manifest, "supported_layouts": ["legacy"]}),
            ("1", {**self.manifest, "pid": 4294967295}),
            ("1", {**self.manifest, "pid": True}),
            ("1", {**self.manifest, "started_at": "bad"}),
            ("1", {**self.manifest, "written_at": "bad"}),
        ]
        for flag, manifest in variants:
            with self.subTest(flag=flag, manifest=manifest):
                if flag is None:
                    os.environ.pop("TALK_WORKSPACE_RUNTIME_ENABLED", None)
                else:
                    os.environ["TALK_WORKSPACE_RUNTIME_ENABLED"] = flag
                if manifest is None:
                    self.capability_path.unlink(missing_ok=True)
                else:
                    self.write_manifest(manifest)
                response = self.start()
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["detail"], "workspace_runtime_not_ready")
                self.assertIsNone(self.state_row())
                self.assertEqual(self.launch_rows(), [])

    def test_valid_manifest_enqueues_single_start(self):
        self.write_manifest(self.manifest)
        os.environ["TALK_WORKSPACE_RUNTIME_ENABLED"] = "1"
        response = self.start()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.launch_rows()), 1)
        self.assertEqual(self.state_row().observed_state, "starting")

    def test_valid_manifest_enqueues_first_configuration(self):
        import server.db as db
        from server.role_services import enqueue_auto_start_launch, _now
        self.write_manifest(self.manifest)
        os.environ["TALK_WORKSPACE_RUNTIME_ENABLED"] = "1"
        with self.session() as session:
            db.begin_immediate_write(session)
            launch, error = enqueue_auto_start_launch(PROJECT_ID, self.role_a, session=session, now=_now())
            session.commit()
        self.assertIsNone(error)
        self.assertIsNotNone(launch)
        self.assertEqual(len(self.launch_rows()), 1)

    def test_startup_allows_valid_manifest(self):
        self.write_manifest(self.manifest)
        os.environ["TALK_WORKSPACE_RUNTIME_ENABLED"] = "1"
        self.preference()
        instance, _ = self.runtime()
        self.activate_once(instance)
        self.assertEqual(self.state_row().observed_state, "starting")
        self.assertEqual(len(self.launch_rows()), 1)

    def test_startup_rechecks_gate_before_cold_recovery(self):
        self.preference()
        self.set_layout("legacy")
        self.start_and_claim()
        self.set_layout("workspace-v1")
        self.write_manifest(self.manifest)
        os.environ["TALK_WORKSPACE_RUNTIME_ENABLED"] = "1"
        from server import role_services
        real_gate = role_services._require_start_layout
        def expire_proof(project, member, session):
            real_gate(project, member, session)
            os.environ.pop("TALK_WORKSPACE_RUNTIME_ENABLED", None)
        with patch.object(role_startup, "_require_start_layout", side_effect=expire_proof), \
             patch("server.role_service_recovery.candidate", side_effect=AssertionError("unexpected recovery")):
            with self.make_client() as client:
                response = client.post(f"/api/projects/{PROJECT_ID}/role-services/startup",
                    headers={"X-API-Key": "bobo-key"}, json={"activation_id": "e" * 32})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.launch_rows()), 1)
        result = next(r for r in response.json()["results"] if r["member_id"] == self.role_a)
        self.assertEqual(result["error_code"], "workspace_runtime_not_ready")

    def test_mixed_start_all_skips_then_enqueues_workspace(self):
        legacy, _ = self.make_second_role()
        os.environ["TALK_WORKSPACE_RUNTIME_ENABLED"] = "1"
        response = self.start_all()
        self.assertEqual(response.status_code, 200, response.text)
        results = {r["member_id"]: r for r in response.json()["results"]}
        self.assertEqual(results[legacy]["status"], "requested")
        self.assertEqual(results[self.role_a]["status"], "skipped_workspace_runtime_not_ready")
        self.assertIsNone(self.state_row())
        self.write_manifest(self.manifest)
        response = self.start_all()
        self.assertEqual(response.status_code, 200, response.text)
        results = {r["member_id"]: r for r in response.json()["results"]}
        self.assertEqual(results[legacy]["status"], "skipped_running")
        self.assertEqual(results[self.role_a]["status"], "requested")
        self.assertEqual(len(self.launch_rows()), 1)
        self.assertEqual(len(self.launch_rows(legacy)), 1)

    def test_invalid_manifest_and_binding_errors_are_safe(self):
        from server.local_runtime import workspace_runtime_capability
        self.capability_path.write_text("{", encoding="utf-8")
        with self.assertLogs("server.local_runtime", level="DEBUG") as logs:
            self.assertIsNone(workspace_runtime_capability(None))
        self.assertIn("capability_unreadable", logs.output[0])
        self.assertNotIn(str(self._tmpdir), logs.output[0])
        with patch("server.local_runtime.configured_runtime", side_effect=ValueError("private path")):
            with self.assertLogs("server.local_runtime", level="DEBUG") as logs:
                self.assertIsNone(workspace_runtime_capability(None))
            self.assertNotIn("private path", logs.output[0])


if __name__ == "__main__":
    unittest.main()
