"""Offline tests for the DSH context snapshot adapter and frozen 288 kernel.

Run with:
    python -B -X utf8 tests/test_dsh_context_metrics.py
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
CANDIDATE_ROOT = HERE.parents[1]
NODE_TEST = HERE.with_name("test_dsh_context_capture.mjs")

SCOPE_FIELDS = (
    "project_id",
    "target_member_id",
    "requester_id",
    "continuity_key",
    "workspace_identity",
    "runner_id",
    "native_home_namespace",
    "service_launch_id",
    "provider_id",
    "model_id",
    "model_binding_fingerprint",
    "config_permission_fingerprint",
)

KERNEL_SCOPE_FIELDS = SCOPE_FIELDS + (
    "runtime",
    "base_contract_version",
    "base_contract_sha256",
    "workspace_verified",
    "session_generation",
)

BASE = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
T1 = BASE + timedelta(seconds=1)
T2 = BASE + timedelta(seconds=2)
T3 = BASE + timedelta(seconds=3)
T4 = BASE + timedelta(seconds=4)
OBSERVED = T4 + timedelta(milliseconds=500)
NOW = OBSERVED + timedelta(seconds=1)
MAX_AGE = 60
REVISION = 100


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = _load_module(
    CANDIDATE_ROOT / "bridges" / "dsh_context_metrics.py",
    "dsh_context_metrics_under_test",
)
KERNEL = _load_module(
    CANDIDATE_ROOT / "bridges" / "execution_sessions.py",
    "candidate_execution_sessions_290",
)


def metric_known(value: int, seq: int, time: datetime) -> dict[str, Any]:
    return {
        "state": "known",
        "value": value,
        "reason_code": "ok",
        "source": {
            "kind": "native_projection_change",
            "seq": seq,
            "time": iso(time),
        },
    }


def metric_invalid(reason: str) -> dict[str, Any]:
    return {
        "state": "invalid",
        "value": None,
        "reason_code": reason,
        "source": None,
    }


def metric_missing() -> dict[str, Any]:
    return {
        "state": "missing",
        "value": None,
        "reason_code": "field_missing",
        "source": None,
    }


def make_snapshot(
    *,
    projected: int = 59900,
    pressure: int = 59900,
    capacity: int = 100000,
    projected_metric: dict[str, Any] | None = None,
    pressure_metric: dict[str, Any] | None = None,
    capacity_metric: dict[str, Any] | None = None,
    projected_time: datetime = T4,
    pressure_time: datetime = T3,
    capacity_time: datetime = T2,
    config_time: datetime = T1,
    model_time: datetime | None = None,
    observed_at: datetime = OBSERVED,
    revision: int = REVISION,
    provider: str = "deepseek-official",
    model: str = "deepseek-flash",
    binding: str = "a" * 64,
    permission: str = "b" * 64,
    capture_status: str = "available",
    blocking_issues: list[str] | None = None,
    cached_snapshot_used: bool = False,
    checkpoint_used: bool = False,
    native_session_id: str = "session-test",
    session_generation: int = 3,
) -> dict[str, Any]:
    if projected_metric is None:
        projected_metric = metric_known(projected, 4, projected_time)
    if pressure_metric is None:
        pressure_metric = metric_known(pressure, 3, pressure_time)
    if capacity_metric is None:
        capacity_metric = metric_known(capacity, 2, capacity_time)
    model_time = config_time if model_time is None else model_time
    config_source = {
        "kind": "request/context",
        "seq": 1,
        "time": iso(config_time),
    }
    return {
        "schema": "talk-dsh-context-snapshot-1",
        "schema_version": 1,
        "producer": {
            "module": "dsh_context_capture",
            "version": "1.0.0",
            "native_contract": {
                "package": "@deepseek-ai/dsh",
                "frozen_version": "0.1.5-rc.2",
                "projection_key": "contextPressure",
                "expected_state_version": 4,
                "session_read_api": "sessions.get",
                "projection_read_api": "sessionProjections.snapshot",
                "change_feed_api": "sessionProjections.onChanged",
            },
        },
        "observed_at": iso(observed_at),
        "host": {
            "project_id": "prj_e8fe7066bbec",
            "target_member_id": "agent:deepseek",
            "requester_id": "agent:codex",
            "continuity_key": "line:test",
            "workspace_identity": "workspace:talk",
            "workspace_verified": True,
            "native_home_namespace": "native-home:test",
            "runner_id": "runner:dsh-deepseek-local",
            "service_launch_id": "launch:test",
            "provider_id": provider,
            "model_id": model,
            "model_binding_fingerprint": binding,
            "config_permission_fingerprint": permission,
            "attestation": {"verified": True, "source": "test-host"},
            "verification": {
                "workspace": "native_header_cwd_exact_match",
                "native_home": "caller_attested",
                "service_launch": "caller_attested",
                "runner": "caller_attested",
                "project_scope": "caller_attested",
                "model_binding": "caller_attested",
            },
        },
        "session": {
            "native_session_id": native_session_id,
            "generation": session_generation,
            "generation_source": "caller_bound_live_session",
            "lifecycle": {"state": "live", "source": "sessions.get"},
            "session_seq": revision + 1,
            "first_live_seq": 0,
            "revision": revision,
            "revision_source": "projection_cut",
            "projection": {
                "key": "contextPressure",
                "authority": "registry_snapshot",
                "expected_state_version": 4,
                "cut": revision,
                "session_seq": revision + 1,
                "source": "sessionProjections.snapshot",
                "cached_snapshot_used": cached_snapshot_used,
                "checkpoint_used": checkpoint_used,
                "materializes_all_registered_units": True,
            },
        },
        "config": {
            "provider_id": {
                "state": "known",
                "value": provider,
                "reason_code": "ok",
                "source": config_source,
            },
            "model_id": {
                "state": "known",
                "value": model,
                "reason_code": "ok",
                "source": {
                    "kind": "request/context",
                    "seq": 1,
                    "time": iso(model_time),
                },
            },
            "model_binding_fingerprint": {
                "state": "caller_attested",
                "value": binding,
                "reason_code": "caller_attested",
                "source": None,
            },
            "config_permission_fingerprint": {
                "state": "caller_attested",
                "value": permission,
                "reason_code": "caller_attested",
                "source": None,
            },
        },
        "metrics": {
            "projected_tokens": projected_metric,
            "pressure_tokens": pressure_metric,
            "context_window": capacity_metric,
        },
        "capture": {
            "status": capture_status,
            "reason_code": None if capture_status == "available" else "source_time_unknown",
            "blocking_issues": [] if blocking_issues is None else blocking_issues,
            "listeners": {
                "projection_change": True,
                "session_event": True,
                "session_disposed": True,
            },
            "limitations": [
                "source_times_tracked_only_after_mount",
                "snapshot_materializes_all_registered_projection_units",
                "usage_and_capacity_sources_update_independently",
                "captured_at_observation_is_not_source_time",
                "no_cross_process_authentication",
            ],
        },
    }


def expected_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    host = snapshot["host"]
    session = snapshot["session"]
    result = {field: host[field] for field in SCOPE_FIELDS}
    result.update(
        {
            "native_session_id": session["native_session_id"],
            "session_generation": session["generation"],
            "session_revision": session["revision"],
        }
    )
    return result


TRUSTED_HOST = {"verified": True, "source": "test-host"}


def adapt(
    snapshot: dict[str, Any],
    *,
    expected: dict[str, Any] | None = None,
    now: datetime = NOW,
    max_age_seconds: int = MAX_AGE,
    trusted_host: dict[str, Any] = TRUSTED_HOST,
) -> dict[str, Any]:
    return ADAPTER.adapt_context_snapshot(
        snapshot,
        expected_scope=expected_from_snapshot(snapshot) if expected is None else expected,
        now=now,
        max_age_seconds=max_age_seconds,
        trusted_host=trusted_host,
    )


class AdapterKnownTests(unittest.TestCase):
    def test_59_9_and_zero_are_known_with_separate_sources(self) -> None:
        for used, capacity in ((59900, 100000), (0, 1000)):
            with self.subTest(used=used, capacity=capacity):
                snapshot = make_snapshot(projected=used, pressure=used, capacity=capacity)
                result = adapt(snapshot)
                self.assertEqual(result["status"], "known")
                self.assertEqual(result["reason_code"], "ok")
                sample = result["context_sample"]
                self.assertEqual(sample["projected_tokens"], used)
                self.assertNotIn("pressure_tokens", sample)
                self.assertEqual(sample["context_window"], capacity)
                self.assertEqual(sample["session_revision"], REVISION)
                self.assertEqual(
                    result["audit"]["metrics"]["pressure_source_time"], iso(T3)
                )
                self.assertEqual(
                    result["audit"]["metrics"]["capacity_source_time"], iso(T2)
                )
                self.assertFalse(result["audit"]["metrics"]["same_request_atomic"])
                json.dumps(result, allow_nan=False, ensure_ascii=False)

    def test_exact_sixty_can_be_left_to_kernel(self) -> None:
        snapshot = make_snapshot(projected=60000, pressure=60000)
        result = adapt(snapshot)
        self.assertEqual(result["status"], "known")
        self.assertEqual(result["context_sample"]["projected_tokens"], 60000)
        self.assertEqual(result["context_sample"]["context_window"], 100000)

    def test_pressure_fallback_only_when_projected_is_missing(self) -> None:
        snapshot = make_snapshot(projected_metric=metric_missing(), pressure=59900)
        result = adapt(snapshot)
        self.assertEqual(result["status"], "known")
        self.assertEqual(result["context_sample"]["pressure_tokens"], 59900)
        self.assertNotIn("projected_tokens", result["context_sample"])
        self.assertEqual(result["audit"]["metrics"]["chosen"], "pressure")

    def test_known_projected_has_priority_over_pressure(self) -> None:
        snapshot = make_snapshot(projected=59900, pressure=59000)
        result = adapt(snapshot)
        self.assertEqual(result["status"], "known")
        self.assertEqual(result["context_sample"]["projected_tokens"], 59900)
        self.assertNotIn("pressure_tokens", result["context_sample"])
        self.assertEqual(result["audit"]["metrics"]["chosen"], "projected")

    def test_max_age_boundary_and_zero_budget(self) -> None:
        snapshot = make_snapshot(
            projected_time=T4,
            pressure_time=T4,
            capacity_time=T4,
        )
        at_limit = T4 + timedelta(seconds=MAX_AGE)
        result = adapt(snapshot, now=at_limit)
        self.assertEqual(result["status"], "known")
        zero_snapshot = make_snapshot(
            projected_time=T4,
            pressure_time=T4,
            capacity_time=T4,
            observed_at=T4,
        )
        zero_budget = adapt(zero_snapshot, now=T4, max_age_seconds=0)
        self.assertEqual(zero_budget["status"], "known")
        expired = adapt(snapshot, now=T4 + timedelta(seconds=MAX_AGE + 1))
        self.assertEqual(expired["status"], "unknown")
        self.assertEqual(expired["context_sample"], None)


class AdapterRejectTests(unittest.TestCase):
    def assert_unknown(self, result: dict[str, Any], reason: str) -> None:
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason_code"], reason, result)
        self.assertIsNone(result["context_sample"])
        json.dumps(result, allow_nan=False, ensure_ascii=False)

    def test_invalid_projected_never_falls_back(self) -> None:
        snapshot = make_snapshot(
            projected_metric=metric_invalid("value_negative"),
            pressure=59900,
        )
        self.assert_unknown(adapt(snapshot), "projected_invalid")

    def test_unverified_projected_never_falls_back(self) -> None:
        snapshot = make_snapshot(
            projected_metric={
                "state": "unverified",
                "value": 59900,
                "reason_code": "source_time_unknown",
                "source": None,
            }
        )
        self.assert_unknown(adapt(snapshot), "projected_unverified")

    def test_capacity_missing_invalid_unverified(self) -> None:
        for metric, reason in (
            (metric_missing(), "capacity_missing"),
            (metric_invalid("value_not_positive"), "capacity_invalid"),
            (
                {
                    "state": "unverified",
                    "value": 100000,
                    "reason_code": "source_time_unknown",
                    "source": None,
                },
                "capacity_unverified",
            ),
        ):
            with self.subTest(reason=reason):
                snapshot = make_snapshot(capacity_metric=metric)
                self.assert_unknown(adapt(snapshot), reason)

    def test_both_tokens_missing_or_pressure_invalid(self) -> None:
        self.assert_unknown(
            adapt(make_snapshot(projected_metric=metric_missing(), pressure_metric=metric_missing())),
            "tokens_missing",
        )
        self.assert_unknown(
            adapt(
                make_snapshot(
                    projected_metric=metric_missing(),
                    pressure_metric=metric_invalid("value_negative"),
                )
            ),
            "pressure_invalid",
        )

    def test_config_mismatch_and_binding_mismatch(self) -> None:
        snapshot = make_snapshot()
        snapshot["config"]["provider_id"]["value"] = "other-provider"
        self.assert_unknown(adapt(snapshot), "provider_mismatch")
        snapshot = make_snapshot()
        snapshot["config"]["model_id"]["value"] = "other-model"
        self.assert_unknown(adapt(snapshot), "model_mismatch")
        snapshot = make_snapshot()
        snapshot["config"]["model_binding_fingerprint"]["value"] = "c" * 64
        self.assert_unknown(adapt(snapshot), "binding_mismatch")
        snapshot = make_snapshot()
        snapshot["config"]["config_permission_fingerprint"]["value"] = "d" * 64
        self.assert_unknown(adapt(snapshot), "permission_mismatch")

    def test_wrong_scope_each_field(self) -> None:
        snapshot = make_snapshot()
        expected = expected_from_snapshot(snapshot)
        for field in SCOPE_FIELDS:
            with self.subTest(field=field):
                changed = dict(expected)
                changed[field] = "different"
                result = adapt(snapshot, expected=changed)
                self.assert_unknown(result, "scope_mismatch")
                self.assertIn(field, result["audit"].get("mismatch_fields", []))

    def test_wrong_session_generation_revision(self) -> None:
        snapshot = make_snapshot()
        expected = expected_from_snapshot(snapshot)
        for field, value, reason in (
            ("native_session_id", "session-other", "session_id_mismatch"),
            ("session_generation", 4, "generation_mismatch"),
            ("session_revision", 99, "revision_mismatch"),
        ):
            with self.subTest(field=field):
                changed = dict(expected)
                changed[field] = value
                self.assert_unknown(adapt(snapshot, expected=changed), reason)
        bool_generation = make_snapshot()
        bool_generation_expected = expected_from_snapshot(bool_generation)
        bool_generation["session"]["generation"] = True
        self.assert_unknown(
            adapt(bool_generation, expected=bool_generation_expected),
            "generation_mismatch",
        )

    def test_cached_and_checkpoint_are_not_current(self) -> None:
        self.assert_unknown(
            adapt(make_snapshot(cached_snapshot_used=True)),
            "cached_not_current",
        )
        self.assert_unknown(
            adapt(make_snapshot(checkpoint_used=True)),
            "checkpoint_not_current",
        )

    def test_snapshot_future_and_source_future(self) -> None:
        snapshot = make_snapshot(observed_at=NOW + timedelta(seconds=1))
        self.assert_unknown(adapt(snapshot), "snapshot_future")
        snapshot = make_snapshot(
            projected_metric=metric_known(59900, 4, T4 + timedelta(seconds=10)),
            observed_at=T4 + timedelta(seconds=5),
        )
        result = adapt(snapshot, now=T4 + timedelta(seconds=6))
        self.assert_unknown(result, "projected_future_source")

    def test_config_after_pressure_and_capacity_after_pressure(self) -> None:
        later = T4 + timedelta(seconds=2)
        snapshot = make_snapshot(
            config_time=T4 + timedelta(seconds=1),
            observed_at=T4 + timedelta(seconds=2),
        )
        self.assert_unknown(
            adapt(snapshot, now=later + timedelta(seconds=1)),
            "config_changed_after_pressure_sample",
        )
        snapshot = make_snapshot(
            capacity_time=T4 + timedelta(seconds=1),
            observed_at=T4 + timedelta(seconds=2),
        )
        self.assert_unknown(
            adapt(snapshot, now=later + timedelta(seconds=1)),
            "capacity_changed_after_pressure_sample",
        )

    def test_metric_source_order_and_config_source_inconsistent(self) -> None:
        snapshot = make_snapshot(
            projected_metric=metric_known(59900, 4, T2),
            pressure_metric=metric_known(59900, 3, T3),
        )
        # Both are still within age; the projected source predates its base.
        snapshot["metrics"]["projected_tokens"]["source"]["time"] = iso(T2)
        self.assert_unknown(adapt(snapshot), "metric_source_order_invalid")
        snapshot = make_snapshot(config_time=T1, model_time=T2)
        self.assert_unknown(adapt(snapshot), "config_source_inconsistent")

    def test_capture_blocking_issue(self) -> None:
        snapshot = make_snapshot(
            capture_status="unknown",
            blocking_issues=["revision_anomaly"],
        )
        result = adapt(snapshot)
        self.assert_unknown(result, "capture_not_usable")

    def test_schema_and_producer_rejections(self) -> None:
        snapshot = make_snapshot()
        snapshot["schema"] = "talk-dsh-context-snapshot-2"
        self.assert_unknown(adapt(snapshot), "snapshot_schema_unsupported")
        snapshot = make_snapshot()
        snapshot["schema_version"] = 2
        self.assert_unknown(adapt(snapshot), "snapshot_version_unsupported")
        snapshot = make_snapshot()
        snapshot["schema_version"] = True
        self.assert_unknown(adapt(snapshot), "snapshot_version_unsupported")
        snapshot = make_snapshot()
        snapshot["producer"]["native_contract"]["frozen_version"] = "9.9.9"
        self.assert_unknown(adapt(snapshot), "producer_unsupported")
        snapshot = make_snapshot()
        snapshot["producer"]["native_contract"]["expected_state_version"] = 4.0
        self.assert_unknown(adapt(snapshot), "producer_unsupported")
        snapshot = make_snapshot()
        snapshot["extra"] = 1
        self.assert_unknown(adapt(snapshot), "snapshot_invalid")

    def test_trusted_host_and_expected_scope_required(self) -> None:
        snapshot = make_snapshot()
        self.assert_unknown(
            adapt(snapshot, trusted_host={"verified": False, "source": "x"}),
            "trusted_host_unverified",
        )
        expected = expected_from_snapshot(snapshot)
        del expected["requester_id"]
        self.assert_unknown(adapt(snapshot, expected=expected), "expected_scope_invalid")

    def test_invalid_number_types_do_not_become_zero(self) -> None:
        for value in (True, -1, 1.5, float("nan"), float("inf"), 2**53, "59900"):
            with self.subTest(value=repr(value)):
                metric = {
                    "state": "known",
                    "value": value,
                    "reason_code": "ok",
                    "source": {
                        "kind": "native_projection_change",
                        "seq": 4,
                        "time": iso(T4),
                    },
                }
                snapshot = make_snapshot(projected_metric=metric)
                result = adapt(snapshot)
                self.assertEqual(result["status"], "unknown")
                self.assertIn("projected_", result["reason_code"])
                self.assertIsNone(result["context_sample"])

    def test_same_old_snapshot_is_not_refreshed_by_reading_later(self) -> None:
        snapshot = make_snapshot()
        first = adapt(snapshot, now=NOW)
        self.assertEqual(first["status"], "known")
        later = adapt(snapshot, now=NOW + timedelta(seconds=2 * MAX_AGE + 1))
        self.assertEqual(later["status"], "unknown")
        self.assertEqual(later["reason_code"], "used_sample_expired")
        self.assertIsNone(later["context_sample"])

    def test_input_snapshot_is_not_mutated(self) -> None:
        snapshot = make_snapshot(projected_metric=metric_missing())
        before = copy.deepcopy(snapshot)
        adapt(snapshot)
        self.assertEqual(snapshot, before)

    def test_product_adapter_has_no_io_or_process_imports(self) -> None:
        source = (CANDIDATE_ROOT / "bridges" / "dsh_context_metrics.py").read_text(
            encoding="utf-8"
        )
        for token in (
            "import os",
            "import subprocess",
            "import socket",
            "import requests",
            "import pathlib",
            "open(",
            "urlopen",
            "Popen(",
        ):
            self.assertNotIn(token, source)

    def test_now_and_max_age_are_required_keywords(self) -> None:
        snapshot = make_snapshot()
        with self.assertRaises(TypeError):
            ADAPTER.adapt_context_snapshot(  # type: ignore[call-arg]
                snapshot,
                expected_scope=expected_from_snapshot(snapshot),
                trusted_host=TRUSTED_HOST,
            )
        with self.assertRaises(TypeError):
            ADAPTER.adapt_context_snapshot(  # type: ignore[call-arg]
                snapshot,
                expected_scope=expected_from_snapshot(snapshot),
                now=NOW,
                trusted_host=TRUSTED_HOST,
            )


def kernel_scope(expected: dict[str, Any]) -> dict[str, Any]:
    base_text = "BASE CONTRACT TEST"
    sha = hashlib.sha256(base_text.encode("utf-8")).hexdigest()
    scope = {field: expected[field] for field in SCOPE_FIELDS}
    scope.update(
        {
            "runtime": "dsh",
            "base_contract_version": "v1",
            "base_contract_sha256": sha,
            "workspace_verified": True,
            "session_generation": expected["session_generation"],
        }
    )
    return scope


def kernel_inputs(
    expected: dict[str, Any],
    context_sample: dict[str, Any] | None,
    *,
    candidate_revision: Any = None,
    candidate: bool = True,
    channel: dict[str, Any] | None = None,
    candidate_state: str = "ready",
    first_turn_confirmed: bool = True,
    context_unavailability: dict[str, Any] | None = None,
    window_count_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_text = "BASE CONTRACT TEST"
    sha = hashlib.sha256(base_text.encode("utf-8")).hexdigest()
    scope = kernel_scope(expected)
    candidate_value = None
    if candidate:
        candidate_value = {
            "native_session_id": expected["native_session_id"],
            "scope": copy.deepcopy(scope),
            "state": candidate_state,
            "execution_channel_exclusive": True,
            "active_writer": False,
            "first_turn_confirmed": first_turn_confirmed,
            "session_revision": (
                expected["session_revision"]
                if candidate_revision is None
                else candidate_revision
            ),
        }
    task = {
        "task_id": "289",
        "attempt": 0,
        "execution_id": "exec-289",
        "goal": "verify adapter and kernel",
        "authorization": "offline test",
        "body": "test increment",
    }
    return KERNEL.plan_execution_session(
        scope=scope,
        base_contract={"version": "v1", "sha256": sha, "text": base_text},
        task=task,
        selection="auto",
        candidate=candidate_value,
        context_sample=context_sample,
        new_messages=[],
        execution_channel=channel
        if channel is not None
        else {
            "state": "ready",
            "active_writer": False,
            "execution_channel_exclusive": True,
        },
        context_unavailability=context_unavailability,
        window_count_state=window_count_state,
        fallback_clock={"now": NOW + timedelta(seconds=MAX_AGE + 1), "max_age_seconds": 120},
    )


def kernel_count_state(expected: dict[str, Any], count: int = 1) -> dict[str, Any]:
    """Build a real candidate count state via initialize/confirm, not a fake dict."""

    scope = kernel_scope(expected)
    native_session_id = expected["native_session_id"]
    revision = expected["session_revision"]
    first = {
        "delivery_id": "deliv-1",
        "task_id": "289",
        "attempt": 0,
        "execution_id": "exec-289-1",
        "body_sha256": hashlib.sha256(b"increment-1").hexdigest(),
        "native_session_id": native_session_id,
        "session_generation": expected["session_generation"],
        "session_revision": revision,
        "outcome": "delivered",
        "first_turn": True,
    }
    initialized = KERNEL.initialize_window_count(
        scope=scope,
        native_session_id=native_session_id,
        first_delivery=first,
    )
    if initialized["status"] != "initialized":
        raise AssertionError(initialized)
    state = initialized["state"]
    for index in range(2, count + 1):
        receipt = {
            "delivery_id": f"deliv-{index}",
            "task_id": str(289 + index - 1),
            "attempt": 0,
            "execution_id": f"exec-289-{index}",
            "body_sha256": hashlib.sha256(
                f"increment-{index}".encode("utf-8")
            ).hexdigest(),
            "native_session_id": native_session_id,
            "session_generation": expected["session_generation"],
            "session_revision": revision,
            "outcome": "delivered",
            "first_turn": False,
        }
        merged = KERNEL.confirm_window_delivery(
            state=state, scope=scope, delivery=receipt
        )
        if merged["status"] != "incremented":
            raise AssertionError(merged)
        state = merged["state"]
    return state


class KernelIntegrationTests(unittest.TestCase):
    def test_59_9_reuses_and_60_starts_new(self) -> None:
        for used, action, mode in (
            (699, "reuse_session", "incremental"),
            (700, "new_session", "full"),
        ):
            with self.subTest(used=used):
                snapshot = make_snapshot(
                    projected=used,
                    pressure=used,
                    capacity=1000,
                )
                adapted = adapt(snapshot)
                self.assertEqual(adapted["status"], "known")
                plan = kernel_inputs(
                    expected_from_snapshot(snapshot),
                    adapted["context_sample"],
                )
                self.assertEqual(plan["action"], action)
                self.assertEqual(plan["briefing_mode"], mode)
                self.assertEqual(plan["metrics"]["source"], "projected")
                self.assertTrue(plan["delivery"]["text"])

    def test_zero_is_known_and_reuses(self) -> None:
        snapshot = make_snapshot(projected=0, pressure=0, capacity=1000)
        adapted = adapt(snapshot)
        self.assertEqual(adapted["status"], "known")
        plan = kernel_inputs(expected_from_snapshot(snapshot), adapted["context_sample"])
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["metrics"]["used_tokens"], 0)

    def test_pressure_fallback_reaches_kernel(self) -> None:
        snapshot = make_snapshot(projected_metric=metric_missing(), pressure=59900)
        adapted = adapt(snapshot)
        self.assertEqual(adapted["status"], "known")
        plan = kernel_inputs(expected_from_snapshot(snapshot), adapted["context_sample"])
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["metrics"]["source"], "pressure")

    def test_invalid_projected_goes_to_full_new_window_not_reuse(self) -> None:
        snapshot = make_snapshot(
            projected_metric=metric_invalid("value_negative"),
            pressure=59900,
        )
        adapted = adapt(snapshot)
        self.assertEqual(adapted["status"], "unknown")
        self.assertEqual(adapted["reason_code"], "projected_invalid")
        plan = kernel_inputs(expected_from_snapshot(snapshot), adapted["context_sample"])
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["briefing_mode"], "full")
        self.assertEqual(plan["reason_code"], "new_context_unknown")
        self.assertEqual(plan["metrics"]["status"], "unknown")

    def test_expired_wrong_session_model_generation_revision_become_new(self) -> None:
        wrong_model = make_snapshot()
        wrong_model["config"]["model_id"]["value"] = "other-model"
        cases = (
            ("expired", make_snapshot(), NOW + timedelta(seconds=MAX_AGE + 1), None, "used_sample_expired"),
            (
                "wrong_session",
                make_snapshot(),
                NOW,
                {"native_session_id": "session-other"},
                "session_id_mismatch",
            ),
            (
                "wrong_model",
                wrong_model,
                NOW,
                None,
                "model_mismatch",
            ),
            (
                "wrong_generation",
                make_snapshot(),
                NOW,
                {"session_generation": 4},
                "generation_mismatch",
            ),
            (
                "wrong_revision",
                make_snapshot(),
                NOW,
                {"session_revision": 99},
                "revision_mismatch",
            ),
            (
                "wrong_launch",
                make_snapshot(),
                NOW,
                {"service_launch_id": "launch:other"},
                "scope_mismatch",
            ),
            (
                "wrong_home",
                make_snapshot(),
                NOW,
                {"native_home_namespace": "native-home:other"},
                "scope_mismatch",
            ),
        )
        for name, snapshot, now, changes, reason in cases:
            with self.subTest(name=name):
                expected = expected_from_snapshot(snapshot)
                if changes:
                    expected.update(changes)
                adapted = adapt(snapshot, expected=expected, now=now)
                self.assertEqual(adapted["status"], "unknown")
                self.assertEqual(adapted["reason_code"], reason)
                plan = kernel_inputs(expected, adapted["context_sample"])
                self.assertEqual(plan["action"], "new_session")
                self.assertEqual(plan["reason_code"], "new_context_unknown")

    def test_no_candidate_first_turn_does_not_need_metrics(self) -> None:
        snapshot = make_snapshot()
        plan = kernel_inputs(
            expected_from_snapshot(snapshot),
            None,
            candidate=False,
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_no_candidate")
        self.assertEqual(plan["metrics"]["status"], "not_applicable")
        self.assertEqual(plan["metrics"]["reason_code"], "no_candidate")

    def test_busy_channel_still_waits_even_with_known_metrics(self) -> None:
        snapshot = make_snapshot(projected=59900, pressure=59900)
        adapted = adapt(snapshot)
        plan = kernel_inputs(
            expected_from_snapshot(snapshot),
            adapted["context_sample"],
            channel={"state": "busy", "active_writer": False, "execution_channel_exclusive": True},
        )
        self.assertEqual(plan["action"], "wait")
        self.assertEqual(plan["reason_code"], "wait_channel_busy")
        self.assertIsNone(plan["delivery"])

    def test_missing_tokens_and_invalid_capacity_go_to_full_new(self) -> None:
        cases = (
            (
                make_snapshot(
                    projected_metric=metric_missing(),
                    pressure_metric=metric_missing(),
                ),
                "tokens_missing",
            ),
            (
                make_snapshot(capacity_metric=metric_invalid("value_not_positive")),
                "capacity_invalid",
            ),
            (
                make_snapshot(capacity_metric=metric_missing()),
                "capacity_missing",
            ),
        )
        for snapshot, reason in cases:
            with self.subTest(reason=reason):
                expected = expected_from_snapshot(snapshot)
                adapted = adapt(snapshot)
                self.assertEqual(adapted["status"], "unknown")
                self.assertEqual(adapted["reason_code"], reason)
                plan = kernel_inputs(expected, adapted["context_sample"])
                self.assertEqual(plan["action"], "new_session")
                self.assertEqual(plan["briefing_mode"], "full")
                self.assertEqual(plan["reason_code"], "new_context_unknown")

    def test_old_snapshot_read_again_does_not_refresh(self) -> None:
        snapshot = make_snapshot()
        expected = expected_from_snapshot(snapshot)
        first = adapt(snapshot, now=NOW)
        self.assertEqual(first["status"], "known")
        plan_first = kernel_inputs(expected, first["context_sample"])
        self.assertEqual(plan_first["action"], "reuse_session")
        later = adapt(snapshot, now=NOW + timedelta(seconds=2 * MAX_AGE + 1))
        self.assertEqual(later["status"], "unknown")
        plan_later = kernel_inputs(expected, later["context_sample"])
        self.assertEqual(plan_later["action"], "new_session")
        self.assertEqual(plan_later["reason_code"], "new_context_unknown")

    def test_candidate_revision_mismatch_does_not_reuse_stale_sample(self) -> None:
        snapshot = make_snapshot()
        adapted = adapt(snapshot)
        self.assertEqual(adapted["status"], "known")
        plan = kernel_inputs(
            expected_from_snapshot(snapshot),
            adapted["context_sample"],
            candidate_revision=99,
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_context_unknown")
        self.assertEqual(plan["metrics"]["reason_code"], "revision_mismatch")


class CrossLanguageTests(unittest.TestCase):
    def test_node_capture_output_is_accepted_by_python_adapter_and_kernel(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "node executable is required for the cross-language test")
        self.assertTrue(NODE_TEST.exists(), NODE_TEST)
        temporary = tempfile.TemporaryDirectory(prefix="talk-dsh-cross-language-")
        self.addCleanup(temporary.cleanup)
        payload_path = Path(temporary.name) / "cases.json"
        subprocess.run(
            [node, str(NODE_TEST), "--emit-cross-language", str(payload_path)],
            check=True,
        )
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "talk-dsh-cross-language-cases-1")
        self.assertGreaterEqual(len(payload["cases"]), 5)
        seen: set[str] = set()
        for case in payload["cases"]:
            name = case["name"]
            seen.add(name)
            snapshot = case["snapshot"]
            expected = expected_from_snapshot(snapshot)
            now = datetime.fromisoformat(case["now"])
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            adapted = adapt(snapshot, expected=expected, now=now)
            plan = kernel_inputs(expected, adapted["context_sample"])
            if name in {"reuse_59_9", "zero", "pressure_fallback"}:
                self.assertEqual(adapted["status"], "known", name)
                self.assertEqual(plan["action"], "reuse_session", name)
            elif name in {"new_60"}:
                self.assertEqual(adapted["status"], "known", name)
                self.assertEqual(plan["action"], "new_session", name)
            elif name == "invalid_projected":
                self.assertEqual(adapted["status"], "unknown", name)
                self.assertEqual(adapted["reason_code"], "projected_invalid", name)
                self.assertEqual(plan["action"], "new_session", name)
            elif name == "expired":
                self.assertEqual(adapted["status"], "unknown", name)
                self.assertEqual(plan["action"], "new_session", name)
            else:
                self.fail(f"unexpected cross-language case {name}")
        self.assertEqual(
            seen,
            {"reuse_59_9", "new_60", "zero", "pressure_fallback", "invalid_projected", "expired"},
        )


class IndependentAdapterTests(unittest.TestCase):
    def assert_unknown(self, snapshot):
        result = adapt(snapshot)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["context_sample"])
        plan = kernel_inputs(expected_from_snapshot(snapshot), result["context_sample"])
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["briefing_mode"], "full")

    def test_sources_cannot_be_after_snapshot_cut(self):
        for name in ("projected_tokens", "pressure_tokens", "context_window", "config"):
            snapshot = make_snapshot()
            if name == "config":
                for field in ("provider_id", "model_id"):
                    snapshot["config"][field]["source"]["seq"] = 101
            else:
                snapshot["metrics"][name]["source"]["seq"] = 101
            with self.subTest(name=name):
                self.assert_unknown(snapshot)

    def test_source_order_uses_seq_when_timestamps_equal(self):
        for name in ("config", "capacity", "projected"):
            snapshot = make_snapshot()
            for metric in snapshot["metrics"].values():
                metric["source"]["time"] = iso(T3)
            for field in ("provider_id", "model_id"):
                snapshot["config"][field]["source"]["time"] = iso(T3)
            if name == "config":
                for field in ("provider_id", "model_id"):
                    snapshot["config"][field]["source"]["seq"] = 4
            elif name == "capacity":
                snapshot["metrics"]["context_window"]["source"]["seq"] = 4
            else:
                snapshot["metrics"]["projected_tokens"]["source"]["seq"] = 2
            with self.subTest(name=name):
                self.assert_unknown(snapshot)

    def test_missing_cannot_discard_explicit_invalid_projected(self):
        snapshot = make_snapshot()
        snapshot["metrics"]["projected_tokens"] = {"state": "missing", "value": -1, "source": None, "reason_code": "field_missing"}
        self.assert_unknown(snapshot)

    def test_metric_state_wrong_type_is_contained(self):
        for value in ([], {}, ["known"]):
            snapshot = make_snapshot()
            snapshot["metrics"]["projected_tokens"]["state"] = value
            self.assert_unknown(snapshot)

    def test_unsupported_producer_version_is_unknown(self):
        snapshot = make_snapshot()
        snapshot["producer"]["version"] = "999.0.0"
        self.assert_unknown(snapshot)

    def test_blocking_issues_do_not_echo_raw_error_text(self):
        snapshot = make_snapshot(blocking_issues=["PRIVATE_PROMPT_SENTINEL: raw error"])
        result = adapt(snapshot)
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", json.dumps(result))

    def test_one_source_event_cannot_have_conflicting_times(self):
        snapshot = make_snapshot()
        snapshot["metrics"]["projected_tokens"]["source"]["seq"] = 3
        self.assert_unknown(snapshot)

    def test_capacity_origin_must_match_current_native_config(self):
        snapshot = make_snapshot()
        for field in ("provider_id", "model_id"):
            snapshot["config"][field]["source"] = {"kind": "request/context", "seq": 3, "time": iso(T3)}
        self.assert_unknown(snapshot)

    def test_invalid_attestation_source_is_not_reflected(self):
        snapshot = make_snapshot()
        result = adapt(snapshot, trusted_host={"verified": False, "source": "PRIVATE_AUTH_SENTINEL"})
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("PRIVATE_AUTH_SENTINEL", json.dumps(result))


class ContextUnavailabilityTests(unittest.TestCase):
    """The adapter must expose a machine-checkable classification, not just None."""

    def test_known_result_has_no_unavailability(self) -> None:
        adapted = adapt(make_snapshot())
        self.assertEqual(adapted["status"], "known")
        self.assertIsNone(adapted["context_unavailability"])

    def test_missing_tokens_is_eligible_and_bound_to_exact_window(self) -> None:
        snapshot = make_snapshot(
            projected_metric=metric_missing(),
            pressure_metric=metric_missing(),
        )
        adapted = adapt(snapshot)
        self.assertEqual(adapted["status"], "unknown")
        self.assertEqual(adapted["reason_code"], "tokens_missing")
        self.assertIsNone(adapted["context_sample"])
        classification = adapted["context_unavailability"]
        self.assertEqual(classification["schema"], ADAPTER.UNAVAILABILITY_SCHEMA)
        self.assertEqual(classification["version"], 1)
        self.assertEqual(classification["reason_code"], "tokens_missing")
        self.assertEqual(classification["category"], "no_usage_sample")
        self.assertTrue(classification["fallback_eligible"])
        expected = expected_from_snapshot(snapshot)
        self.assertEqual(
            classification["window"]["native_session_id"],
            expected["native_session_id"],
        )
        self.assertEqual(
            classification["window"]["session_generation"],
            expected["session_generation"],
        )
        self.assertEqual(
            classification["window"]["session_revision"],
            expected["session_revision"],
        )
        self.assertEqual(
            classification["window"]["scope"],
            {field: expected[field] for field in SCOPE_FIELDS},
        )
        self.assertRegex(
            classification["window"]["scope_fingerprint"], r"^[0-9a-f]{64}$"
        )
        evidence = classification["evidence"]
        self.assertEqual(evidence["trust"], "adapter_verified_snapshot")
        self.assertTrue(evidence["producer_supported"])
        self.assertTrue(evidence["identity_verified"])
        self.assertFalse(evidence["sample_present"])
        self.assertTrue(
            all(
                evidence["checks"].get(key) is True
                for key in ADAPTER._IDENTITY_CHECK_KEYS
            )
        )

    def test_capacity_missing_is_eligible(self) -> None:
        snapshot = make_snapshot(capacity_metric=metric_missing())
        adapted = adapt(snapshot)
        self.assertEqual(adapted["reason_code"], "capacity_missing")
        classification = adapted["context_unavailability"]
        self.assertEqual(classification["category"], "capacity_missing")
        self.assertTrue(classification["fallback_eligible"])

    def test_expired_source_is_eligible(self) -> None:
        snapshot = make_snapshot()
        adapted = adapt(snapshot, now=NOW + timedelta(seconds=MAX_AGE + 1))
        self.assertEqual(adapted["status"], "unknown")
        self.assertEqual(adapted["reason_code"], "used_sample_expired")
        classification = adapted["context_unavailability"]
        self.assertEqual(classification["category"], "source_expired")
        self.assertTrue(classification["fallback_eligible"])
        self.assertTrue(classification["evidence"]["identity_verified"])

    def test_invalid_metric_is_blocked(self) -> None:
        snapshot = make_snapshot(
            projected_metric=metric_invalid("value_negative"),
            pressure=59900,
        )
        adapted = adapt(snapshot)
        self.assertEqual(adapted["reason_code"], "projected_invalid")
        classification = adapted["context_unavailability"]
        self.assertFalse(classification["fallback_eligible"])
        self.assertEqual(classification["category"], "invalid_metric")
        self.assertTrue(classification["evidence"]["identity_verified"])

    def test_identity_producer_and_source_failures_are_blocked(self) -> None:
        cases: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []
        snapshot = make_snapshot()
        snapshot["config"]["model_id"]["value"] = "other-model"
        cases.append(("wrong_model", snapshot, {}, "model_mismatch"))
        snapshot = make_snapshot()
        cases.append(
            (
                "wrong_session",
                snapshot,
                {"expected": {"native_session_id": "session-other"}},
                "session_id_mismatch",
            )
        )
        snapshot = make_snapshot()
        snapshot["producer"]["version"] = "999.0.0"
        cases.append(("producer", snapshot, {}, "producer_unsupported"))
        snapshot = make_snapshot()
        snapshot["metrics"]["projected_tokens"]["source"]["seq"] = 101
        cases.append(("after_cut", snapshot, {}, "source_after_snapshot_cut"))
        snapshot = make_snapshot()
        cases.append(
            ("future", snapshot, {"now": NOW - timedelta(seconds=10)}, "snapshot_future")
        )
        snapshot = make_snapshot(blocking_issues=["private raw event text"])
        cases.append(("capture_blocking", snapshot, {}, "capture_blocking_issue"))
        for name, snapshot, kwargs, reason in cases:
            with self.subTest(name=name):
                expected = expected_from_snapshot(snapshot)
                if "expected" in kwargs:
                    expected.update(kwargs["expected"])
                    kwargs = {"expected": expected}
                adapted = adapt(snapshot, **kwargs)
                self.assertEqual(adapted["status"], "unknown", name)
                self.assertEqual(adapted["reason_code"], reason, name)
                classification = adapted["context_unavailability"]
                self.assertFalse(classification["fallback_eligible"], name)

    def test_blocked_classification_never_echoes_raw_text(self) -> None:
        sentinel = "PRIVATE_RAW_EVENT_SENTINEL"
        snapshot = make_snapshot(blocking_issues=[sentinel])
        result = adapt(snapshot)
        serialized = json.dumps(result["context_unavailability"], ensure_ascii=False)
        self.assertNotIn(sentinel, serialized)
        self.assertEqual(
            result["context_unavailability"]["category"], "capture_blocked"
        )

    def test_host_attested_unavailability_requires_trust_and_exact_scope(self) -> None:
        snapshot = make_snapshot()
        expected = expected_from_snapshot(snapshot)
        classification = ADAPTER.build_metrics_unavailability(
            reason_code="metrics_not_provided",
            expected_scope=expected,
            observed_at=NOW,
            trusted_host=TRUSTED_HOST,
        )
        self.assertTrue(classification["fallback_eligible"])
        self.assertEqual(classification["category"], "metrics_not_provided")
        self.assertEqual(classification["evidence"]["trust"], "trusted_host_capability")
        self.assertEqual(
            classification["window"]["native_session_id"],
            expected["native_session_id"],
        )
        with self.assertRaises(ValueError):
            ADAPTER.build_metrics_unavailability(
                reason_code="not_a_real_reason",
                expected_scope=expected,
                observed_at=NOW,
                trusted_host=TRUSTED_HOST,
            )
        with self.assertRaises(ValueError):
            ADAPTER.build_metrics_unavailability(
                reason_code="metrics_not_provided",
                expected_scope=expected,
                observed_at=NOW,
                trusted_host={"verified": False, "source": "host"},
            )
        with self.assertRaises(ValueError):
            ADAPTER.build_metrics_unavailability(
                reason_code="metrics_not_provided",
                expected_scope={"project_id": "partial"},
                observed_at=NOW,
                trusted_host=TRUSTED_HOST,
            )
        with self.assertRaises(ValueError):
            ADAPTER.build_metrics_unavailability(
                reason_code="metrics_not_provided",
                expected_scope=expected,
                observed_at="not-a-time",
                trusted_host=TRUSTED_HOST,
            )

    def test_runtime_unsupported_is_eligible_without_fake_ratio(self) -> None:
        expected = expected_from_snapshot(make_snapshot())
        classification = ADAPTER.build_metrics_unavailability(
            reason_code="runtime_unsupported",
            expected_scope=expected,
            observed_at=NOW,
            trusted_host=TRUSTED_HOST,
            producer_supported=False,
        )
        self.assertTrue(classification["fallback_eligible"])
        self.assertEqual(classification["category"], "runtime_unsupported")
        self.assertFalse(classification["evidence"]["producer_supported"])
        state = kernel_count_state(expected, count=1)
        plan = kernel_inputs(
            expected,
            None,
            context_unavailability=classification,
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["reason_code"], "reuse_missing_metrics_fallback")
        self.assertEqual(plan["metrics"]["status"], "unknown")
        self.assertIsNone(plan["metrics"]["used_tokens"])

    def test_known_output_matches_frozen_contract(self) -> None:
        # ad46037 冻结结果的规范 JSON 哈希，正式测试不依赖本机 .tmp。
        candidate = adapt(make_snapshot(projected=599, pressure=599, capacity=1000))
        payload = {key: candidate[key] for key in ("status", "reason_code", "context_sample")}
        actual = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        self.assertEqual(actual, "f2da933a10722584050fdac1da05ab98fdb4dc40dd818c1d3a196584f1e964e5")
        self.assertIsNone(candidate["context_unavailability"])


class FallbackIntegrationTests(unittest.TestCase):
    """Actual 289 adapter output -> count state -> unified planning entry."""

    def missing_snapshot(self) -> dict[str, Any]:
        return make_snapshot(
            projected_metric=metric_missing(),
            pressure_metric=metric_missing(),
        )

    def test_actual_missing_tokens_output_allows_fallback(self) -> None:
        snapshot = self.missing_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        self.assertEqual(adapted["status"], "unknown")
        self.assertIsNone(adapted["context_sample"])
        classification = adapted["context_unavailability"]
        state = kernel_count_state(expected, count=1)
        plan = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=classification,
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["reason_code"], "reuse_missing_metrics_fallback")
        self.assertEqual(plan["briefing_mode"], "incremental")
        self.assertEqual(plan["window_count"]["status"], "eligible")
        self.assertEqual(plan["window_count"]["confirmed_count"], 1)
        self.assertEqual(plan["window_count"]["proposed_ordinal"], 2)
        self.assertTrue(plan["window_count"]["requires_delivery_confirmation"])
        self.assertEqual(
            plan["window_count"]["count_merge"], "after_confirmed_delivery"
        )
        self.assertNotIn("BASE CONTRACT TEST", plan["delivery"]["text"])

    def test_actual_capacity_missing_output_allows_tenth(self) -> None:
        snapshot = make_snapshot(capacity_metric=metric_missing())
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        self.assertEqual(adapted["reason_code"], "capacity_missing")
        state = kernel_count_state(expected, count=9)
        plan = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["window_count"]["confirmed_count"], 9)
        self.assertEqual(plan["window_count"]["proposed_ordinal"], 10)

    def test_actual_expired_output_allows_fallback(self) -> None:
        snapshot = make_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot, now=NOW + timedelta(seconds=MAX_AGE + 1))
        self.assertEqual(adapted["reason_code"], "used_sample_expired")
        state = kernel_count_state(expected, count=1)
        plan = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["reason_code"], "reuse_missing_metrics_fallback")

    def test_actual_count_10_goes_to_full_new(self) -> None:
        snapshot = self.missing_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        state = kernel_count_state(expected, count=10)
        plan = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_fallback_exhausted")
        self.assertEqual(plan["briefing_mode"], "full")
        self.assertEqual(plan["window_count"]["status"], "exhausted")
        self.assertIsNone(plan["window_count"]["proposed_ordinal"])
        self.assertIn("BASE CONTRACT TEST", plan["delivery"]["text"])

    def test_actual_missing_output_without_count_is_full_new(self) -> None:
        snapshot = self.missing_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        plan = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_fallback_count_unverified")
        self.assertEqual(plan["window_count"]["status"], "missing")
        self.assertTrue(plan["delivery"]["includes"]["base_contract"])

    def test_actual_invalid_projected_cannot_fallback(self) -> None:
        snapshot = make_snapshot(
            projected_metric=metric_invalid("value_negative"),
            pressure=59900,
        )
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        self.assertFalse(adapted["context_unavailability"]["fallback_eligible"])
        state = kernel_count_state(expected, count=1)
        plan = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["briefing_mode"], "full")
        self.assertNotEqual(plan["window_count"]["status"], "eligible")
        self.assertEqual(
            plan["window_count"]["classification_reason"],
            "projected_invalid",
        )

    def test_raw_invalid_sample_beats_eligible_classification(self) -> None:
        snapshot = self.missing_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        classification = adapted["context_unavailability"]
        self.assertTrue(classification["fallback_eligible"])
        invalid_sample = {
            "native_session_id": expected["native_session_id"],
            "session_generation": expected["session_generation"],
            "session_revision": expected["session_revision"],
            "provider_id": expected["provider_id"],
            "model_id": expected["model_id"],
            "model_binding_fingerprint": expected["model_binding_fingerprint"],
            "projected_tokens": -1,
            "pressure_tokens": 50000,
            "context_window": 100000,
            "sampled_at": iso(T4),
            "now": iso(NOW),
            "max_age_seconds": MAX_AGE,
        }
        state = kernel_count_state(expected, count=1)
        plan = kernel_inputs(
            expected,
            invalid_sample,
            context_unavailability=classification,
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["metrics"]["reason_code"], "projected_invalid")
        self.assertNotEqual(plan["window_count"]["status"], "eligible")

    def test_known_metrics_ignore_count_on_both_sides(self) -> None:
        expected = expected_from_snapshot(make_snapshot())
        low = adapt(make_snapshot(projected=200, pressure=200, capacity=1000))
        self.assertEqual(low["status"], "known")
        state20 = kernel_count_state(expected, count=20)
        low_plan = kernel_inputs(
            expected,
            low["context_sample"],
            window_count_state=state20,
        )
        self.assertEqual(low_plan["action"], "reuse_session")
        self.assertEqual(low_plan["window_count"]["status"], "verified")
        self.assertEqual(low_plan["window_count"]["confirmed_count"], 20)
        self.assertEqual(
            low_plan["window_count"]["observation_intent"]["observation"][
                "used_tokens"
            ],
            200,
        )
        high = adapt(make_snapshot(projected=700, pressure=700, capacity=1000))
        state1 = kernel_count_state(expected, count=1)
        high_plan = kernel_inputs(
            expected,
            high["context_sample"],
            window_count_state=state1,
        )
        self.assertEqual(high_plan["action"], "new_session")
        self.assertEqual(high_plan["reason_code"], "new_context_threshold")
        self.assertEqual(high_plan["window_count"]["confirmed_count"], 1)

    def test_count_1_9_10_actual_output(self) -> None:
        snapshot = self.missing_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        for count, action, status, ordinal in (
            (1, "reuse_session", "eligible", 2),
            (9, "reuse_session", "eligible", 10),
            (10, "new_session", "exhausted", None),
        ):
            with self.subTest(count=count):
                state = kernel_count_state(expected, count=count)
                plan = kernel_inputs(
                    expected,
                    adapted["context_sample"],
                    context_unavailability=adapted["context_unavailability"],
                    window_count_state=state,
                )
                self.assertEqual(plan["action"], action)
                self.assertEqual(plan["window_count"]["status"], status)
                self.assertEqual(
                    plan["window_count"]["proposed_ordinal"], ordinal
                )

    def test_planning_is_pure_and_count_is_not_preincremented(self) -> None:
        snapshot = self.missing_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        state = kernel_count_state(expected, count=1)
        before = copy.deepcopy(state)
        first = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=state,
        )
        second = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=state,
        )
        self.assertEqual(first, second)
        self.assertEqual(state, before)
        self.assertIsNone(first["window_count"].get("state"))
        self.assertNotIn("state", first["window_count"])

    def test_host_attested_not_provided_reaches_plan(self) -> None:
        expected = expected_from_snapshot(make_snapshot())
        classification = ADAPTER.build_metrics_unavailability(
            reason_code="metrics_not_provided",
            expected_scope=expected,
            observed_at=NOW,
            trusted_host=TRUSTED_HOST,
        )
        state = kernel_count_state(expected, count=1)
        plan = kernel_inputs(
            expected,
            None,
            context_unavailability=classification,
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(
            plan["window_count"]["classification_reason"],
            "metrics_not_provided",
        )

    def test_bare_none_never_auto_fallbacks(self) -> None:
        expected = expected_from_snapshot(make_snapshot())
        state = kernel_count_state(expected, count=1)
        plan = kernel_inputs(
            expected,
            None,
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_context_unknown")
        self.assertNotEqual(plan["window_count"]["status"], "eligible")

    def test_unknown_or_tampered_classification_is_rejected(self) -> None:
        snapshot = self.missing_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        state = kernel_count_state(expected, count=1)
        cases = []
        unknown = copy.deepcopy(adapted["context_unavailability"])
        unknown["reason_code"] = "unknown"
        unknown["category"] = "unknown"
        cases.append(("unknown_reason", unknown))
        extra = copy.deepcopy(adapted["context_unavailability"])
        extra["allow_fallback"] = True
        cases.append(("allow_flag", extra))
        no_identity = copy.deepcopy(adapted["context_unavailability"])
        no_identity["evidence"]["identity_verified"] = False
        cases.append(("identity_false", no_identity))
        for name, classification in cases:
            with self.subTest(name=name):
                plan = kernel_inputs(
                    expected,
                    adapted["context_sample"],
                    context_unavailability=classification,
                    window_count_state=state,
                )
                self.assertEqual(plan["action"], "new_session", name)
                self.assertNotEqual(
                    plan["window_count"]["status"], "eligible", name
                )

    def test_busy_channel_and_unconfirmed_first_turn_win_over_fallback(self) -> None:
        snapshot = self.missing_snapshot()
        expected = expected_from_snapshot(snapshot)
        adapted = adapt(snapshot)
        state = kernel_count_state(expected, count=1)
        busy = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=state,
            channel={
                "state": "busy",
                "active_writer": False,
                "execution_channel_exclusive": True,
            },
        )
        self.assertEqual(busy["action"], "wait")
        self.assertEqual(busy["reason_code"], "wait_channel_busy")
        unconfirmed = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=state,
            first_turn_confirmed=False,
        )
        self.assertEqual(unconfirmed["action"], "new_session")
        self.assertEqual(
            unconfirmed["reason_code"], "new_first_turn_unconfirmed"
        )

    def test_high_observation_blocks_missing_metrics(self) -> None:
        expected = expected_from_snapshot(make_snapshot())
        state = kernel_count_state(expected, count=1)
        scope = kernel_scope(expected)
        observed = KERNEL.record_threshold_observation(
            now="2026-10-20T15:02:00+00:00",
            state=state,
            scope=scope,
            observation={
                "native_session_id": expected["native_session_id"],
                "session_generation": expected["session_generation"],
                "session_revision": expected["session_revision"],
                "used_tokens": 700,
                "capacity_tokens": 1000,
                "source": "projected",
                "sampled_at": iso(T4),
            },
        )
        self.assertEqual(observed["status"], "recorded")
        self.assertEqual(observed["confirmed_count"], 1)
        self.assertTrue(
            observed["state"]["last_threshold_observation"]["threshold_met"]
        )
        snapshot = make_snapshot(
            projected_metric=metric_missing(),
            pressure_metric=metric_missing(),
        )
        adapted = adapt(snapshot)
        plan = kernel_inputs(
            expected,
            adapted["context_sample"],
            context_unavailability=adapted["context_unavailability"],
            window_count_state=observed["state"],
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(
            plan["reason_code"], "new_fallback_threshold_observed"
        )
        self.assertEqual(
            plan["window_count"]["last_threshold_observation_met"], True
        )

    def test_recovery_keeps_count_then_next_missing_uses_it(self) -> None:
        expected = expected_from_snapshot(make_snapshot())
        state = kernel_count_state(expected, count=1)
        low = adapt(make_snapshot(projected=200, pressure=200, capacity=1000))
        low_plan = kernel_inputs(
            expected, low["context_sample"], window_count_state=state
        )
        self.assertEqual(low_plan["action"], "reuse_session")
        intent = low_plan["window_count"]["observation_intent"]
        self.assertTrue(intent["requires_host_persist"])
        recorded = KERNEL.record_threshold_observation(
            now="2026-10-20T15:02:00+00:00",
            state=state,
            scope=kernel_scope(expected),
            observation=intent["observation"],
        )
        self.assertEqual(recorded["confirmed_count"], 1)
        self.assertFalse(
            recorded["state"]["last_threshold_observation"]["threshold_met"]
        )
        missing = adapt(
            make_snapshot(
                projected_metric=metric_missing(),
                pressure_metric=metric_missing(),
            )
        )
        plan = kernel_inputs(
            expected,
            missing["context_sample"],
            context_unavailability=missing["context_unavailability"],
            window_count_state=recorded["state"],
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["window_count"]["confirmed_count"], 1)
        self.assertEqual(plan["window_count"]["proposed_ordinal"], 2)

    def test_known_plan_matches_frozen_contract(self) -> None:
        expected = expected_from_snapshot(make_snapshot())
        adapted = adapt(make_snapshot(projected=599, pressure=599, capacity=1000))
        plan = kernel_inputs(expected, adapted["context_sample"])
        keys = ("action", "reason_code", "briefing_mode", "native_session_ref", "delivery", "archive", "metrics")
        payload = {key: plan[key] for key in keys}
        actual = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        self.assertEqual(actual, "e6d1c687fc90d36e0194925ffdcfb6a996227a2c1944f397f1365a7066dc6920")


class FallbackReviewRegressions(unittest.TestCase):
    def assert_blocked(self, snapshot):
        result = adapt(snapshot)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["context_unavailability"]["fallback_eligible"])
        expected = expected_from_snapshot(snapshot)
        plan = kernel_inputs(expected, result["context_sample"],
                             context_unavailability=result["context_unavailability"],
                             window_count_state=kernel_count_state(expected))
        self.assertEqual(plan["action"], "new_session")
        return result

    def test_capacity_missing_does_not_hide_invalid_or_unknown_metric(self):
        for field in ("projected_tokens", "pressure_tokens"):
            for state in ("invalid", "unverified", "unknown"):
                with self.subTest(field=field, state=state):
                    snapshot = make_snapshot(capacity_metric=metric_missing())
                    snapshot["metrics"][field] = dict(state=state, value=None, source=None, reason_code="bad")
                    self.assert_blocked(snapshot)

    def test_both_tokens_missing_does_not_hide_unknown_projected(self):
        snapshot = make_snapshot(projected_metric=dict(state="unknown", value=None, source=None), pressure_metric=metric_missing())
        self.assert_blocked(snapshot)

    def test_missing_capacity_or_tokens_does_not_hide_sources_after_cut(self):
        for field in ("projected_tokens", "pressure_tokens"):
            snapshot = make_snapshot(capacity_metric=metric_missing())
            snapshot["metrics"][field]["source"]["seq"] = 102
            self.assertEqual(self.assert_blocked(snapshot)["reason_code"], "source_after_snapshot_cut")
        snapshot = make_snapshot(projected_metric=metric_missing(), pressure_metric=metric_missing())
        for field in ("provider_id", "model_id"):
            snapshot["config"][field]["source"]["seq"] = 102
        self.assertEqual(self.assert_blocked(snapshot)["reason_code"], "source_after_snapshot_cut")

    def test_missing_capacity_does_not_hide_conflicting_event_time(self):
        snapshot = make_snapshot(capacity_metric=metric_missing())
        snapshot["metrics"]["projected_tokens"]["source"]["seq"] = snapshot["metrics"]["pressure_tokens"]["source"]["seq"]
        self.assertEqual(self.assert_blocked(snapshot)["reason_code"], "source_event_time_inconsistent")

    def test_missing_tokens_does_not_hide_backward_source_time(self):
        snapshot = make_snapshot(projected_metric=metric_missing(), pressure_metric=metric_missing())
        snapshot["metrics"]["context_window"]["source"]["time"] = iso(BASE)
        self.assertEqual(self.assert_blocked(snapshot)["reason_code"], "metric_source_order_invalid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
