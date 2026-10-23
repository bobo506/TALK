"""288 首片 + 290 缺指标备用离线测试。

仅标准库；候选模块通过 importlib 明确加载，无运行器或服务接线。运行方式：

    python -B -X utf8 tests/test_execution_sessions.py -v

不启动 runner/API/原生会话，不读取真实配置/日志，不写产品文件。
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import unittest
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "bridges" / "execution_sessions.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "execution_sessions_test_290", MODULE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("无法加载候选 execution_sessions 模块")
execution_sessions = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = execution_sessions
_SPEC.loader.exec_module(execution_sessions)

_ADAPTER_PATH = (
    Path(__file__).resolve().parents[1] / "bridges" / "dsh_context_metrics.py"
)
_ADAPTER_SPEC = importlib.util.spec_from_file_location(
    "dsh_context_metrics_for_execution_test_290", _ADAPTER_PATH
)
if _ADAPTER_SPEC is None or _ADAPTER_SPEC.loader is None:
    raise RuntimeError("无法加载候选 dsh_context_metrics 模块")
dsh_context_metrics = importlib.util.module_from_spec(_ADAPTER_SPEC)
sys.modules[_ADAPTER_SPEC.name] = dsh_context_metrics
_ADAPTER_SPEC.loader.exec_module(dsh_context_metrics)

plan_execution_session = execution_sessions.plan_execution_session
reconstruct_full_requirements = execution_sessions.reconstruct_full_requirements
initialize_window_count = execution_sessions.initialize_window_count
confirm_window_delivery = execution_sessions.confirm_window_delivery
record_threshold_observation = execution_sessions.record_threshold_observation
MAX_SAFE_INTEGER = execution_sessions.MAX_SAFE_INTEGER
COUNT_STATE_SCHEMA = execution_sessions.COUNT_STATE_SCHEMA
FALLBACK_LIMIT = execution_sessions.FALLBACK_LIMIT

BASE_ONLY = "BASE_ONLY_SENTINEL_288"
SHARED_PHRASE = "SHARED_PHRASE_288"
BASE_TEXT = (
    "PROJECT BRIEF / FIXED ROLE / FIXED RULES / AUTHORIZATION BASE. "
    + BASE_ONLY
    + " "
    + SHARED_PHRASE
)
BASE_SHA = hashlib.sha256(BASE_TEXT.encode("utf-8")).hexdigest()
TASK_BODY = "CURRENT_TASK_BODY_SENTINEL_288"
SECRET_BASE = BASE_TEXT + " SECRET_BASE_SENTINEL_288"
SECRET_BASE_SHA = hashlib.sha256(SECRET_BASE.encode("utf-8")).hexdigest()

_MISSING = object()


def make_scope(**overrides):
    scope = {
        "project_id": "prj_test_288",
        "target_member_id": "agent:deepseek",
        "requester_id": "agent:codex",
        "continuity_key": "execution-session-core-v1",
        "workspace_identity": "workspace:talk-288",
        "workspace_verified": True,
        "runtime": "dsh",
        "runner_id": "runner:dsh-test",
        "native_home_namespace": "native-home:deepseek-288",
        "provider_id": "provider:test",
        "model_id": "model:test",
        "model_binding_fingerprint": "binding:cfg-288",
        "config_permission_fingerprint": "perm:cfg-288",
        "service_launch_id": "launch:288-1",
        "session_generation": 7,
        "base_contract_version": "v1",
        "base_contract_sha256": BASE_SHA,
    }
    scope.update(overrides)
    return scope


def make_base(text=BASE_TEXT, version="v1", declared_sha=None):
    sha = (
        declared_sha
        if declared_sha is not None
        else hashlib.sha256(text.encode("utf-8")).hexdigest()
    )
    return {"version": version, "sha256": sha, "text": text}


def make_task(**overrides):
    task = {
        "task_id": "288",
        "attempt": 0,
        "execution_id": "exec-288-a",
        "goal": "实现会话选择、70% 阈值与增量交办离线内核。",
        "authorization": "仅写 deepseek/ 候选目录；不部署、不接生产。",
        "body": TASK_BODY,
    }
    task.update(overrides)
    return task


def make_candidate(base_scope, **overrides):
    candidate = {
        "native_session_id": "sess-288-1",
        "scope": copy.deepcopy(base_scope),
        "state": "ready",
        "execution_channel_exclusive": True,
        "active_writer": False,
        "first_turn_confirmed": True,
        "session_revision": "rev-1",
    }
    candidate.update(overrides)
    if "scope" in overrides:
        candidate["scope"] = copy.deepcopy(overrides["scope"])
    return candidate


def make_sample(scope, candidate, **overrides):
    sample = {
        "native_session_id": candidate.get("native_session_id"),
        "session_generation": scope.get("session_generation"),
        "session_revision": candidate.get("session_revision"),
        "provider_id": scope.get("provider_id"),
        "model_id": scope.get("model_id"),
        "model_binding_fingerprint": scope.get("model_binding_fingerprint"),
        "projected_tokens": 100,
        "pressure_tokens": 900,
        "context_window": 1000,
        "sampled_at": "2026-10-20T13:00:00+00:00",
        "now": "2026-10-20T13:01:00+00:00",
        "max_age_seconds": 600,
    }
    sample.update(overrides)
    return sample


def call_plan(**overrides):
    """便于测试的调用包装；显式传 None 不会被当作缺省值。"""

    scope = overrides.pop("scope", _MISSING)
    if scope is _MISSING:
        scope = make_scope()
    base = overrides.pop("base_contract", _MISSING)
    if base is _MISSING:
        base = make_base()
    task = overrides.pop("task", _MISSING)
    if task is _MISSING:
        task = make_task()
    selection = overrides.pop("selection", "auto")
    candidate = overrides.pop("candidate", _MISSING)
    if candidate is _MISSING:
        candidate = make_candidate(scope) if isinstance(scope, Mapping) else None
    sample = overrides.pop("context_sample", _MISSING)
    if sample is _MISSING:
        sample = (
            make_sample(scope, candidate)
            if isinstance(scope, Mapping) and isinstance(candidate, Mapping)
            else None
        )
    new_messages = overrides.pop("new_messages", None)
    channel = overrides.pop("execution_channel", {
        "state": "ready", "active_writer": False,
        "execution_channel_exclusive": True,
    })
    unavailability = overrides.pop("context_unavailability", None)
    count_state = overrides.pop("window_count_state", None)
    clock = overrides.pop("fallback_clock", {"now": "2026-10-20T13:02:00+00:00", "max_age_seconds": 600})
    if overrides:
        raise TypeError(f"unexpected overrides: {sorted(overrides)}")
    return plan_execution_session(
        scope=scope,
        base_contract=base,
        task=task,
        selection=selection,
        candidate=candidate,
        context_sample=sample,
        new_messages=new_messages,
        execution_channel=channel,
        context_unavailability=unavailability,
        window_count_state=count_state,
        fallback_clock=clock,
    )


def make_unavailability(
    scope,
    candidate,
    *,
    reason="metrics_not_provided",
    observed_at="2026-10-20T13:01:00+00:00",
    trusted_host=None,
):
    expected = {
        field: scope[field] for field in dsh_context_metrics._SCOPE_FIELDS
    }
    expected.update(
        {
            "native_session_id": candidate["native_session_id"],
            "session_generation": scope["session_generation"],
            "session_revision": candidate["session_revision"],
        }
    )
    return dsh_context_metrics.build_metrics_unavailability(
        reason_code=reason,
        expected_scope=expected,
        observed_at=observed_at,
        trusted_host=(
            {"verified": True, "source": "test-host"}
            if trusted_host is None
            else trusted_host
        ),
        producer_supported=False if reason == "runtime_unsupported" else True,
    )


def make_receipt(scope, candidate, **overrides):
    receipt = {
        "delivery_id": "deliv-1",
        "task_id": "288",
        "attempt": 0,
        "execution_id": "exec-288-1",
        "body_sha256": hashlib.sha256(TASK_BODY.encode("utf-8")).hexdigest(),
        "native_session_id": candidate["native_session_id"],
        "session_generation": scope["session_generation"],
        "session_revision": candidate["session_revision"],
        "outcome": "delivered",
        "first_turn": False,
    }
    receipt.update(overrides)
    return receipt


def make_count_state(scope, candidate, count=1):
    first = make_receipt(scope, candidate, first_turn=True)
    initialized = initialize_window_count(
        scope=scope,
        native_session_id=candidate["native_session_id"],
        first_delivery=first,
    )
    if initialized["status"] != "initialized":
        raise AssertionError(initialized)
    state = initialized["state"]
    for index in range(2, count + 1):
        receipt = make_receipt(
            scope,
            candidate,
            delivery_id=f"deliv-{index}",
            task_id=str(287 + index),
            execution_id=f"exec-288-{index}",
            body_sha256=hashlib.sha256(
                f"TASK_BODY_{index}".encode("utf-8")
            ).hexdigest(),
            first_turn=False,
        )
        merged = confirm_window_delivery(
            state=state, scope=scope, delivery=receipt
        )
        if merged["status"] != "incremented":
            raise AssertionError(merged)
        state = merged["state"]
    return state


def make_fallback_plan(scope, candidate, count=1, **overrides):
    state = overrides.pop(
        "window_count_state", make_count_state(scope, candidate, count)
    )
    classification = overrides.pop(
        "context_unavailability", make_unavailability(scope, candidate)
    )
    return call_plan(
        scope=scope,
        candidate=candidate,
        context_sample=None,
        context_unavailability=classification,
        window_count_state=state,
        **overrides,
    )


class KernelTestCase(unittest.TestCase):
    def assert_json_safe(self, value):
        try:
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:  # pragma: no cover - 失败即测试失败
            self.fail(f"计划不是 JSON 可序列化对象：{exc}")

    def assert_consistent(self, result):
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("schema"), "execution-session-plan-1")
        self.assertIn(
            result.get("action"),
            {"reuse_session", "new_session", "wait", "reject"},
        )
        self.assertIsInstance(result.get("reason_code"), str)
        self.assertTrue(result["reason_code"])
        self.assertIsInstance(result.get("reason"), str)
        self.assertTrue(result["reason"])
        self.assert_json_safe(result)
        self.assertIn("window_count", result)
        window_count = result["window_count"]
        self.assertIsInstance(window_count, dict)
        self.assertEqual(window_count.get("schema"), COUNT_STATE_SCHEMA)
        self.assertIn(
            window_count.get("status"),
            {
                "not_started",
                "not_evaluated",
                "not_required",
                "verified",
                "eligible",
                "exhausted",
                "unverified",
                "invalid",
                "missing",
                "not_eligible",
                "blocked_by_observation",
            },
        )
        self.assertIsInstance(window_count.get("reason_code"), str)
        self.assert_json_safe(window_count)

        action = result["action"]
        if action == "reuse_session":
            self.assertEqual(result["briefing_mode"], "incremental")
            self.assertIsInstance(result["native_session_ref"], str)
            self.assertIsNotNone(result["delivery"])
            self.assertFalse(result["delivery"]["includes"]["base_contract"])
            self.assertEqual(result["archive"]["mode"], "incremental")
            self.assertEqual(
                result["archive"]["session"]["status"], "selected_existing"
            )
            self.assertEqual(
                result["archive"]["session"]["native_session_id"],
                result["native_session_ref"],
            )
            self.assertEqual(
                result["archive"]["session"]["session_generation"],
                result["session_generation"],
            )
            self.assertFalse(result["errors"])
        elif action == "new_session":
            self.assertEqual(result["briefing_mode"], "full")
            self.assertIsNone(result["native_session_ref"])
            self.assertIsNone(result["session_generation"])
            self.assertIsNotNone(result["delivery"])
            self.assertTrue(result["delivery"]["includes"]["base_contract"])
            self.assertEqual(result["archive"]["mode"], "full")
            self.assertEqual(
                result["archive"]["session"]["status"], "not_created"
            )
            self.assertIsNone(
                result["archive"]["session"]["native_session_id"]
            )
            self.assertIsNone(
                result["archive"]["session"]["session_generation"]
            )
            self.assertFalse(result["errors"])
        else:
            self.assertEqual(result["briefing_mode"], "none")
            self.assertIsNone(result["native_session_ref"])
            self.assertIsNone(result["session_generation"])
            self.assertIsNone(result["delivery"])
            self.assertIsNone(result["archive"])
            if action == "reject":
                self.assertTrue(result["errors"])
            else:
                self.assertFalse(result["errors"])

        if result["delivery"] is not None:
            text = result["delivery"]["text"]
            encoded = text.encode("utf-8")
            self.assertEqual(result["delivery"]["bytes"], len(encoded))
            self.assertEqual(
                result["delivery"]["sha256"],
                hashlib.sha256(encoded).hexdigest(),
            )
            self.assertEqual(
                result["archive"]["delivery"]["sha256"],
                result["delivery"]["sha256"],
            )
            self.assertEqual(
                result["archive"]["delivery"]["bytes"], len(encoded)
            )
            self.assertEqual(
                result["archive"]["scope_fingerprint"],
                result["scope_fingerprint"],
            )

    def assert_full(self, result, body=TASK_BODY):
        self.assertEqual(result["action"], "new_session")
        self.assertEqual(result["briefing_mode"], "full")
        text = result["delivery"]["text"]
        self.assertIn(BASE_ONLY, text)
        self.assertIn(body, text)
        self.assertIsNone(result["native_session_ref"])

    def assert_incremental(self, result, body=TASK_BODY):
        self.assertEqual(result["action"], "reuse_session")
        self.assertEqual(result["briefing_mode"], "incremental")
        text = result["delivery"]["text"]
        self.assertNotIn(BASE_ONLY, text)
        self.assertIn(body, text)
        self.assertIsInstance(result["native_session_ref"], str)

    def usage_plan(
        self,
        used,
        capacity=1000,
        *,
        source="projected",
        pressure=100,
        **overrides,
    ):
        scope = overrides.pop("scope", make_scope())
        candidate = overrides.pop("candidate", make_candidate(scope))
        sample = make_sample(
            scope,
            candidate,
            projected_tokens=used,
            pressure_tokens=pressure,
            context_window=capacity,
        )
        if source == "pressure":
            sample.pop("projected_tokens", None)
            sample["pressure_tokens"] = used
        elif source != "projected":
            raise ValueError(source)
        return call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=sample,
            **overrides,
        )


class NewWindowTests(KernelTestCase):
    def test_no_candidate_returns_full_first_turn(self):
        result = call_plan(candidate=None)
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_no_candidate")
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["metrics"]["status"], "not_applicable")
        self.assertEqual(result["metrics"]["reason_code"], "no_candidate")
        self.assertEqual(
            result["archive"]["session"]["status"], "not_created"
        )
        self.assertIsNone(
            result["archive"]["session"]["native_session_id"]
        )

    def test_no_candidate_does_not_require_old_metrics(self):
        result = call_plan(candidate=None, context_sample=None)
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_no_candidate")
        self.assertEqual(result["metrics"]["status"], "not_applicable")

    def test_explicit_new_with_ready_candidate_is_full(self):
        result = call_plan(selection="new")
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_explicit")
        self.assertFalse(result["candidate"]["selected"])
        self.assertIsNone(result["native_session_ref"])

    def test_explicit_new_ignores_below_threshold_metrics(self):
        result = self.usage_plan(100, 1000, selection="new")
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_explicit")
        self.assertEqual(result["metrics"]["status"], "not_applicable")

    def test_reuse_without_candidate_is_rejected(self):
        result = call_plan(candidate=None, selection="reuse")
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertEqual(
            result["reason_code"], "reject_reuse_without_candidate"
        )
        self.assertTrue(
            any("candidate" in error for error in result["errors"])
        )

    def test_failed_reject_does_not_echo_task_or_base(self):
        task = make_task(body="TASK_SECRET_SENTINEL_288", attempt=True)
        result = call_plan(
            scope=make_scope(base_contract_sha256=SECRET_BASE_SHA),
            base_contract=make_base(text=SECRET_BASE),
            task=task,
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("TASK_SECRET_SENTINEL_288", rendered)
        self.assertNotIn("SECRET_BASE_SENTINEL_288", rendered)


class ThresholdTests(KernelTestCase):
    def test_below_threshold_reuses_incrementally(self):
        result = self.usage_plan(699, 1000)
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertEqual(result["action"], "reuse_session")
        self.assertEqual(result["metrics"]["source"], "projected")
        self.assertEqual(result["metrics"]["used_tokens"], 699)
        self.assertEqual(result["metrics"]["capacity_tokens"], 1000)
        self.assertFalse(result["metrics"]["threshold_met"])
        self.assertEqual(
            result["metrics"]["exact_comparison"]["used_times_10"], "6990"
        )
        self.assertEqual(
            result["metrics"]["exact_comparison"]["capacity_times_7"],
            "7000",
        )

    def test_exact_70_percent_starts_new_window(self):
        result = self.usage_plan(700, 1000)
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_context_threshold")
        self.assertTrue(result["metrics"]["threshold_met"])
        self.assertEqual(result["metrics"]["source"], "projected")

    def test_above_threshold_starts_new_window(self):
        result = self.usage_plan(701, 1000)
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_context_threshold")
        self.assertTrue(result["metrics"]["threshold_met"])

    def test_ui_rounding_69_6_percent_does_not_trigger(self):
        result = self.usage_plan(6960, 10000)
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertFalse(result["metrics"]["threshold_met"])

    def test_ui_rounding_69_9_percent_does_not_trigger(self):
        result = self.usage_plan(699, 1000)
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertFalse(result["metrics"]["threshold_met"])

    def test_zero_usage_is_valid_and_below_threshold(self):
        result = self.usage_plan(0, 1000)
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertEqual(result["metrics"]["used_tokens"], 0)
        self.assertFalse(result["metrics"]["threshold_met"])

    def test_usage_over_capacity_still_meets_threshold(self):
        result = self.usage_plan(1001, 1000)
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertTrue(result["metrics"]["threshold_met"])
        self.assertEqual(result["metrics"]["used_tokens"], 1001)

    def test_big_integers_compare_exactly(self):
        capacity = 9_000_000_000_000_000
        exact = 6_300_000_000_000_000
        below = exact - 1
        above = exact + 1
        with self.subTest("below"):
            result = self.usage_plan(below, capacity)
            self.assert_incremental(result)
            self.assertFalse(result["metrics"]["threshold_met"])
        with self.subTest("exact"):
            result = self.usage_plan(exact, capacity)
            self.assert_full(result)
            self.assertTrue(result["metrics"]["threshold_met"])
        with self.subTest("above"):
            result = self.usage_plan(above, capacity)
            self.assert_full(result)
            self.assertTrue(result["metrics"]["threshold_met"])

    def test_safe_integer_max_is_valid(self):
        result = self.usage_plan(MAX_SAFE_INTEGER, MAX_SAFE_INTEGER)
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertTrue(result["metrics"]["threshold_met"])
        self.assertEqual(
            result["metrics"]["used_tokens"], MAX_SAFE_INTEGER
        )

    def test_value_over_safe_integer_is_unknown_not_below(self):
        result = self.usage_plan(MAX_SAFE_INTEGER + 1, 1000)
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["metrics"]["status"], "unknown")
        self.assertEqual(
            result["metrics"]["reason_code"], "projected_invalid"
        )
        self.assertIsNone(result["metrics"]["used_tokens"])
        self.assertIsNone(result["metrics"]["source"])

    def test_invalid_projected_never_falls_back_to_pressure(self):
        invalid_values = [
            True,
            False,
            -1,
            1.0,
            "100",
            None,
            float("nan"),
            float("inf"),
            float("-inf"),
        ]
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                result = self.usage_plan(value, 1000, pressure=100)
                self.assert_consistent(result)
                self.assert_full(result)
                self.assertEqual(result["metrics"]["status"], "unknown")
                self.assertEqual(
                    result["metrics"]["reason_code"], "projected_invalid"
                )
                self.assertIsNone(result["metrics"]["source"])
                self.assertIsNone(result["metrics"]["used_tokens"])
                self.assertIn(
                    "projected_invalid", result["reason"]
                )

    def test_invalid_pressure_is_unknown_when_projected_absent(self):
        for value in (True, -1, 1.0, "100", None, float("inf")):
            with self.subTest(value=repr(value)):
                result = self.usage_plan(value, 1000, source="pressure")
                self.assert_consistent(result)
                self.assert_full(result)
                self.assertEqual(
                    result["metrics"]["reason_code"], "pressure_invalid"
                )
                self.assertIsNone(result["metrics"]["source"])

    def test_invalid_capacity_is_unknown(self):
        for value in (
            0,
            -1,
            True,
            1.0,
            "1000",
            None,
            float("inf"),
            MAX_SAFE_INTEGER + 1,
        ):
            with self.subTest(value=repr(value)):
                result = self.usage_plan(100, value)
                self.assert_consistent(result)
                self.assert_full(result)
                self.assertEqual(
                    result["metrics"]["reason_code"], "capacity_invalid"
                )
                self.assertIsNone(result["metrics"]["used_tokens"])

    def test_missing_capacity_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        sample.pop("context_window")
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "capacity_missing"
        )

    def test_projected_has_priority_over_pressure(self):
        for pressure in (999, "invalid-pressure", None):
            with self.subTest(pressure=repr(pressure)):
                result = self.usage_plan(100, 1000, pressure=pressure)
                self.assert_consistent(result)
                self.assert_incremental(result)
                self.assertEqual(result["metrics"]["source"], "projected")
                self.assertEqual(result["metrics"]["used_tokens"], 100)

    def test_pressure_is_used_only_when_projected_missing(self):
        result = self.usage_plan(700, 1000, source="pressure")
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["metrics"]["source"], "pressure")
        self.assertEqual(result["metrics"]["used_tokens"], 700)
        self.assertTrue(result["metrics"]["threshold_met"])

    def test_missing_both_token_fields_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        sample.pop("projected_tokens", None)
        sample.pop("pressure_tokens", None)
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "tokens_missing"
        )

    def test_missing_context_sample_is_unknown(self):
        result = call_plan(context_sample=None)
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "context_missing"
        )

    def test_non_mapping_context_sample_is_unknown(self):
        result = call_plan(context_sample="not-a-mapping")
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "sample_invalid"
        )

    def test_expired_sample_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(
            scope,
            candidate,
            sampled_at="2026-10-20T13:00:00+00:00",
            now="2026-10-20T13:20:00+00:00",
            max_age_seconds=600,
        )
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "sample_expired"
        )

    def test_future_sample_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(
            scope,
            candidate,
            sampled_at="2026-10-20T13:02:00+00:00",
            now="2026-10-20T13:01:00+00:00",
            max_age_seconds=600,
        )
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "sample_future"
        )

    def test_sample_exactly_at_max_age_is_valid(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(
            scope,
            candidate,
            sampled_at="2026-10-20T13:00:00+00:00",
            now="2026-10-20T13:10:00+00:00",
            max_age_seconds=600,
        )
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertEqual(result["metrics"]["status"], "known")

    def test_max_age_zero_with_equal_times_is_valid(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(
            scope,
            candidate,
            sampled_at="2026-10-20T13:00:00+00:00",
            now="2026-10-20T13:00:00+00:00",
            max_age_seconds=0,
        )
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_incremental(result)

    def test_invalid_sample_time_is_unknown(self):
        for value in (
            "not-a-time",
            "2026-10-20T13:00:00",
            "",
            None,
            True,
        ):
            with self.subTest(value=repr(value)):
                scope = make_scope()
                candidate = make_candidate(scope)
                sample = make_sample(scope, candidate, sampled_at=value)
                result = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=sample,
                )
                self.assert_consistent(result)
                self.assert_full(result)
                self.assertEqual(
                    result["metrics"]["reason_code"], "time_invalid"
                )

    def test_missing_time_field_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        sample.pop("now")
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "time_missing"
        )

    def test_invalid_max_age_is_unknown(self):
        for value in (-1, True, "600", 600.0):
            with self.subTest(value=repr(value)):
                scope = make_scope()
                candidate = make_candidate(scope)
                sample = make_sample(
                    scope, candidate, max_age_seconds=value
                )
                result = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=sample,
                )
                self.assert_consistent(result)
                self.assert_full(result)
                self.assertEqual(
                    result["metrics"]["reason_code"], "max_age_invalid"
                )

    def test_wrong_session_identity_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(
            scope, candidate, native_session_id="sess-other"
        )
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "session_id_mismatch"
        )

    def test_wrong_generation_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, session_generation=8)
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "generation_mismatch"
        )

    def test_invalid_generation_type_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, session_generation="7")
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "generation_invalid"
        )

    def test_wrong_revision_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, session_revision="rev-2")
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "revision_mismatch"
        )

    def test_revision_type_mismatch_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope, session_revision=1)
        sample = make_sample(scope, candidate, session_revision="1")
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "revision_mismatch"
        )

    def test_candidate_revision_missing_is_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        del candidate["session_revision"]
        sample = make_sample(scope, candidate)
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"],
            "candidate_revision_missing",
        )

    def test_wrong_model_identity_is_unknown(self):
        for key, value in (
            ("provider_id", "provider:other"),
            ("model_id", "model:other"),
            ("model_binding_fingerprint", "binding:other"),
        ):
            with self.subTest(key=key):
                scope = make_scope()
                candidate = make_candidate(scope)
                sample = make_sample(scope, candidate, **{key: value})
                result = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=sample,
                )
                self.assert_consistent(result)
                self.assert_full(result)
                self.assertEqual(
                    result["metrics"]["reason_code"], "model_mismatch"
                )

    def test_explicit_zero_projected_wins(self):
        result = self.usage_plan(0, 1000, pressure=999)
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertEqual(result["metrics"]["source"], "projected")
        self.assertEqual(result["metrics"]["used_tokens"], 0)

    def test_datetime_and_epoch_times_are_json_safe(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sampled = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)
        now = datetime(2026, 10, 20, 13, 1, tzinfo=timezone.utc)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(
                scope,
                candidate,
                sampled_at=sampled,
                now=now,
                max_age_seconds=600,
            ),
        )
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertIsInstance(
            result["metrics"]["sample"]["sampled_at"], str
        )
        self.assertNotIn("datetime", json.dumps(result))

        stamp = int(sampled.timestamp())
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(
                scope,
                candidate,
                sampled_at=stamp,
                now=stamp + 60,
                max_age_seconds=600,
            ),
        )
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertIsInstance(
            result["metrics"]["sample"]["sampled_at"], str
        )


class ProjectionAliasTests(KernelTestCase):
    def test_camel_case_projected_and_capacity_are_supported(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        sample["projectedTokens"] = 599
        sample["contextWindow"] = 1000
        sample.pop("projected_tokens")
        sample.pop("context_window")
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertEqual(result["metrics"]["source"], "projected")
        self.assertEqual(result["metrics"]["used_tokens"], 599)

    def test_camel_case_pressure_fallback_is_supported(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        sample.pop("projected_tokens")
        sample.pop("pressure_tokens")
        sample["pressureTokens"] = 700
        sample["contextWindow"] = 1000
        sample.pop("context_window")
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["metrics"]["source"], "pressure")
        self.assertEqual(result["metrics"]["used_tokens"], 700)

    def test_ambiguous_projected_aliases_are_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        sample["projected_tokens"] = 100
        sample["projectedTokens"] = 200
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "projected_ambiguous"
        )

    def test_ambiguous_capacity_aliases_are_unknown(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        sample["context_window"] = 1000
        sample["contextWindow"] = 2000
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "capacity_ambiguous"
        )

    def test_camel_case_invalid_projected_does_not_fall_back(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        sample.pop("projected_tokens")
        sample["projectedTokens"] = "100"
        sample["pressureTokens"] = 700
        sample["contextWindow"] = 1000
        sample.pop("context_window")
        result = call_plan(
            scope=scope, candidate=candidate, context_sample=sample
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["metrics"]["reason_code"], "projected_invalid"
        )
        self.assertIsNone(result["metrics"]["source"])


class ScopeAndStateTests(KernelTestCase):
    def test_different_task_ids_reuse_same_work_line(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        task_a = make_task(
            task_id="288", execution_id="exec-288-a", body="BODY_A_288"
        )
        task_b = make_task(
            task_id="289",
            attempt=2,
            execution_id="exec-289-b",
            body="BODY_B_289",
        )
        result_a = call_plan(
            scope=scope,
            candidate=candidate,
            task=task_a,
            context_sample=sample,
        )
        result_b = call_plan(
            scope=scope,
            candidate=candidate,
            task=task_b,
            context_sample=sample,
        )
        self.assert_incremental(result_a, "BODY_A_288")
        self.assert_incremental(result_b, "BODY_B_289")
        self.assertEqual(result_a["archive"]["task"]["task_id"], "288")
        self.assertEqual(result_b["archive"]["task"]["task_id"], "289")
        self.assertEqual(result_a["archive"]["task"]["attempt"], 0)
        self.assertEqual(result_b["archive"]["task"]["attempt"], 2)
        self.assertIn("BODY_A_288", result_a["delivery"]["text"])
        self.assertNotIn("BODY_B_289", result_a["delivery"]["text"])
        self.assertIn("BODY_B_289", result_b["delivery"]["text"])
        self.assertNotIn("BODY_A_288", result_b["delivery"]["text"])

    def test_no_ten_round_fallback(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, projected_tokens=100)
        for index in range(12):
            task = make_task(
                task_id=str(700 + index),
                attempt=0,
                execution_id=f"exec-{700 + index}",
                body=f"BODY_SENTINEL_{700 + index}",
            )
            result = call_plan(
                scope=scope,
                candidate=candidate,
                task=task,
                context_sample=sample,
            )
            self.assert_consistent(result)
            self.assertEqual(
                result["action"],
                "reuse_session",
                msg=f"第 {index + 1} 个任务不应因轮数被强制新窗",
            )
            self.assertEqual(
                result["native_session_ref"], "sess-288-1"
            )

    def test_different_continuity_key_does_not_cross(self):
        scope = make_scope()
        candidate = make_candidate(
            scope, scope=dict(scope, continuity_key="other-line")
        )
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["reason_code"], "new_continuity_changed"
        )
        self.assertFalse(result["candidate"]["scope_match"])

    def test_scope_field_changes_do_not_reuse(self):
        cases = {
            "project_id": ("prj-other", "new_scope_mismatch"),
            "target_member_id": ("agent:other", "new_scope_mismatch"),
            "requester_id": ("agent:other", "new_scope_mismatch"),
            "workspace_identity": ("workspace:other", "new_scope_mismatch"),
            "runtime": ("other-runtime", "new_scope_mismatch"),
            "runner_id": ("runner:other", "new_scope_mismatch"),
            "native_home_namespace": ("native:other", "new_scope_mismatch"),
            "provider_id": ("provider:other", "new_scope_mismatch"),
            "model_id": ("model:other", "new_scope_mismatch"),
            "model_binding_fingerprint": ("binding:other", "new_scope_mismatch"),
            "config_permission_fingerprint": ("perm:other", "new_scope_mismatch"),
            "service_launch_id": ("launch:other", "new_service_launch_changed"),
            "session_generation": (8, "new_session_generation_changed"),
            "base_contract_version": ("v2", "new_base_contract_changed"),
            "base_contract_sha256": ("0" * 64, "new_base_contract_changed"),
        }
        scope = make_scope()
        for field, (value, expected_reason) in cases.items():
            with self.subTest(field=field):
                changed_scope = dict(scope)
                changed_scope[field] = value
                candidate = make_candidate(scope, scope=changed_scope)
                result = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=make_sample(scope, candidate),
                )
                self.assert_consistent(result)
                self.assert_full(result)
                self.assertEqual(result["reason_code"], expected_reason)
                self.assertFalse(result["candidate"]["scope_match"])
                self.assertIn(field, result["candidate"]["scope_differences"])

    def test_scope_key_order_does_not_matter(self):
        scope = make_scope()
        reordered = dict(reversed(list(scope.items())))
        candidate = make_candidate(scope, scope=reordered)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertTrue(result["candidate"]["scope_match"])

    def test_naive_concatenation_would_collide_but_canonical_json_does_not(self):
        current = make_scope(project_id="ab", target_member_id="c")
        other = make_scope(project_id="a", target_member_id="bc")
        candidate = make_candidate(other)
        result = call_plan(
            scope=current,
            candidate=candidate,
            context_sample=make_sample(current, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_scope_mismatch")
        self.assertIn("project_id", result["candidate"]["scope_differences"])
        self.assertIn(
            "target_member_id", result["candidate"]["scope_differences"]
        )

    def test_candidate_scope_missing_is_unverifiable(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        del candidate["scope"]
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["reason_code"], "new_scope_unverifiable"
        )
        self.assertFalse(result["candidate"]["scope_verifiable"])

    def test_candidate_scope_with_unknown_field_is_unverifiable(self):
        scope = make_scope()
        bad_scopes = {
            "unknown_field": dict(scope, task_id="288"),
            "workspace_unverified": dict(scope, workspace_verified=False),
        }
        for label, bad_scope in bad_scopes.items():
            with self.subTest(label=label):
                candidate = make_candidate(scope, scope=bad_scope)
                result = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=make_sample(scope, candidate),
                )
                self.assert_consistent(result)
                self.assert_full(result)
                self.assertEqual(
                    result["reason_code"], "new_scope_unverifiable"
                )

    def test_candidate_native_id_missing_is_unverifiable(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        del candidate["native_session_id"]
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["reason_code"], "new_candidate_unverifiable"
        )
        self.assertIsNone(result["candidate"]["native_session_id"])

    def test_tainted_candidate_starts_new(self):
        scope = make_scope()
        candidate = make_candidate(scope, state="tainted")
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_session_tainted")

    def test_closed_candidate_starts_new(self):
        scope = make_scope()
        candidate = make_candidate(scope, state="closed")
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_session_closed")

    def test_busy_candidate_waits(self):
        scope = make_scope()
        candidate = make_candidate(scope, state="busy")
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "wait")
        self.assertEqual(result["reason_code"], "wait_candidate_busy")
        self.assertFalse(result["candidate"]["selected"])

    def test_active_writer_waits(self):
        scope = make_scope()
        candidate = make_candidate(scope, active_writer=True)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "wait")
        self.assertEqual(result["reason_code"], "wait_active_writer")

    def test_unknown_writer_waits(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        del candidate["active_writer"]
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "wait")
        self.assertEqual(result["reason_code"], "wait_writer_unknown")

    def test_not_exclusive_waits(self):
        scope = make_scope()
        candidate = make_candidate(
            scope, execution_channel_exclusive=False
        )
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "wait")
        self.assertEqual(
            result["reason_code"], "wait_channel_not_exclusive"
        )

    def test_unknown_exclusivity_waits(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        del candidate["execution_channel_exclusive"]
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "wait")
        self.assertEqual(result["reason_code"], "wait_exclusive_unknown")

    def test_unknown_state_waits(self):
        for value in ("mystery", None, 3):
            with self.subTest(value=repr(value)):
                scope = make_scope()
                candidate = make_candidate(scope, state=value)
                result = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=make_sample(scope, candidate),
                )
                self.assert_consistent(result)
                self.assertEqual(result["action"], "wait")
                self.assertEqual(
                    result["reason_code"], "wait_candidate_state_unknown"
                )

    def test_busy_candidate_blocks_explicit_new_bypass(self):
        scope = make_scope()
        candidate = make_candidate(scope, state="busy")
        result = call_plan(
            scope=scope,
            candidate=candidate,
            selection="new",
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "wait")
        self.assertEqual(result["reason_code"], "wait_candidate_busy")
        self.assertIsNone(result["native_session_ref"])

    def test_tainted_candidate_with_unconfirmed_channel_waits(self):
        scope = make_scope()
        candidate = make_candidate(
            scope,
            state="tainted",
            execution_channel_exclusive=False,
        )
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "wait")
        self.assertEqual(
            result["reason_code"], "wait_channel_not_exclusive"
        )

    def test_explicit_new_with_tainted_but_available_channel_is_new(self):
        scope = make_scope()
        candidate = make_candidate(scope, state="tainted")
        result = call_plan(
            scope=scope,
            candidate=candidate,
            selection="new",
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_explicit")

    def test_first_turn_unconfirmed_starts_new_with_full_base(self):
        scope = make_scope()
        candidate = make_candidate(scope, first_turn_confirmed=False)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["reason_code"], "new_first_turn_unconfirmed"
        )
        self.assertIn(BASE_ONLY, result["delivery"]["text"])

    def test_first_turn_missing_starts_new_with_full_base(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        del candidate["first_turn_confirmed"]
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(
            result["reason_code"], "new_first_turn_unconfirmed"
        )

    def test_reuse_selection_with_mismatch_still_returns_new_plan(self):
        scope = make_scope()
        candidate = make_candidate(
            scope, scope=dict(scope, project_id="prj-other")
        )
        result = call_plan(
            scope=scope,
            candidate=candidate,
            selection="reuse",
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_full(result)
        self.assertEqual(result["reason_code"], "new_scope_mismatch")

    def test_candidate_not_mapping_is_rejected(self):
        result = call_plan(candidate="not-a-candidate")
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("candidate" in error for error in result["errors"])
        )

    def test_invalid_selection_is_rejected(self):
        result = call_plan(selection="bogus")
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertIsNone(result["selection"])
        self.assertTrue(
            any("selection" in error for error in result["errors"])
        )

    def test_current_scope_missing_field_is_rejected(self):
        scope = make_scope()
        del scope["provider_id"]
        result = call_plan(scope=scope)
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("provider_id" in error for error in result["errors"])
        )

    def test_current_workspace_unverified_is_rejected(self):
        result = call_plan(scope=make_scope(workspace_verified=False))
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any(
                "workspace_verified" in error
                for error in result["errors"]
            )
        )

    def test_current_generation_invalid_is_rejected(self):
        for value in (0, True, 1.5, "7", MAX_SAFE_INTEGER + 1):
            with self.subTest(value=repr(value)):
                result = call_plan(
                    scope=make_scope(session_generation=value)
                )
                self.assert_consistent(result)
                self.assertEqual(result["action"], "reject")
                self.assertTrue(
                    any(
                        "session_generation" in error
                        for error in result["errors"]
                    )
                )

    def test_scope_unknown_field_is_rejected(self):
        result = call_plan(scope=make_scope(task_id="288"))
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("不支持的字段" in error for error in result["errors"])
        )

    def test_base_contract_hash_mismatch_is_rejected(self):
        result = call_plan(
            base_contract=make_base(declared_sha="0" * 64)
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("base_contract.sha256" in error for error in result["errors"])
        )
        self.assertNotIn(BASE_ONLY, json.dumps(result, ensure_ascii=False))

    def test_scope_base_version_mismatch_is_rejected(self):
        result = call_plan(
            scope=make_scope(base_contract_version="v2")
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertEqual(
            result["reason_code"], "reject_scope_base_mismatch"
        )

    def test_scope_base_hash_mismatch_is_rejected(self):
        result = call_plan(
            scope=make_scope(base_contract_sha256="0" * 64)
        )
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertEqual(
            result["reason_code"], "reject_scope_base_mismatch"
        )

    def test_task_missing_field_is_rejected(self):
        task = make_task()
        del task["goal"]
        result = call_plan(task=task)
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("task.goal" in error for error in result["errors"])
        )

    def test_task_attempt_bool_is_rejected(self):
        result = call_plan(task=make_task(attempt=True))
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("task.attempt" in error for error in result["errors"])
        )

    def test_task_unknown_field_is_rejected(self):
        task = make_task()
        task["title"] = "should not be silently dropped"
        result = call_plan(task=task)
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("不支持的字段" in error for error in result["errors"])
        )

    def test_task_authorization_missing_is_rejected(self):
        task = make_task()
        del task["authorization"]
        result = call_plan(task=task)
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("task.authorization" in error for error in result["errors"])
        )

    def test_task_authorization_empty_is_rejected(self):
        result = call_plan(task=make_task(authorization=[]))
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")

    def test_new_messages_not_list_is_rejected(self):
        result = call_plan(new_messages="not-a-list")
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("new_messages" in error for error in result["errors"])
        )

    def test_new_messages_empty_item_is_rejected(self):
        result = call_plan(new_messages=["ok", ""])
        self.assert_consistent(result)
        self.assertEqual(result["action"], "reject")
        self.assertTrue(
            any("new_messages[1]" in error for error in result["errors"])
        )

    def test_candidate_extra_outer_fields_are_ignored(self):
        scope = make_scope()
        candidate = make_candidate(
            scope, last_seen_at="2026-10-20T13:00:00+00:00"
        )
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_incremental(result)


class DeliveryAndArchiveTests(KernelTestCase):
    def test_incremental_omits_base_and_old_hall(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
            new_messages=["NEW_HALL_ONLY_288"],
        )
        self.assert_consistent(result)
        self.assert_incremental(result)
        text = result["delivery"]["text"]
        self.assertIn("NEW_HALL_ONLY_288", text)
        self.assertNotIn("OLD_HALL_SENTINEL_288", text)
        self.assertNotIn("FULL_HISTORY_SENTINEL_288", text)
        self.assertFalse(result["delivery"]["includes"]["base_contract"])
        self.assertTrue(result["delivery"]["includes"]["new_hall"])

    def test_full_includes_base_once_and_increment_and_hall(self):
        result = call_plan(
            candidate=None, new_messages=["NEW_HALL_ONLY_288"]
        )
        self.assert_consistent(result)
        self.assert_full(result)
        text = result["delivery"]["text"]
        self.assertEqual(text.count(BASE_ONLY), 1)
        self.assertIn("NEW_HALL_ONLY_288", text)
        self.assertTrue(result["delivery"]["includes"]["new_hall"])

    def test_body_sharing_base_phrase_is_not_deleted(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        body = f"{SHARED_PHRASE} / TASK_BODY_WITH_SHARED_PHRASE"
        task = make_task(body=body)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            task=task,
            context_sample=make_sample(scope, candidate),
        )
        self.assert_consistent(result)
        self.assert_incremental(result, body)
        text = result["delivery"]["text"]
        self.assertIn(SHARED_PHRASE, text)
        self.assertNotIn(BASE_ONLY, text)
        reconstructed = reconstruct_full_requirements(result["archive"], base_contract=make_base())
        self.assertIn(BASE_ONLY, reconstructed)
        self.assertIn(body, reconstructed)

    def test_no_new_messages_means_no_hall_block(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=make_sample(scope, candidate),
            new_messages=[],
        )
        self.assert_consistent(result)
        self.assert_incremental(result)
        self.assertNotIn("NEW HALL MESSAGES", result["delivery"]["text"])
        self.assertFalse(result["delivery"]["includes"]["new_hall"])
        self.assertEqual(result["delivery"]["new_message_count"], 0)

    def test_archive_reconstructs_full_requirements(self):
        for selection in ("auto", "new"):
            with self.subTest(selection=selection):
                result = call_plan(
                    selection=selection,
                    new_messages=["HALL_RECONSTRUCT_288"],
                )
                self.assert_consistent(result)
                reconstructed = reconstruct_full_requirements(
                    result["archive"], base_contract=make_base()
                )
                self.assertIn(BASE_ONLY, reconstructed)
                self.assertIn(TASK_BODY, reconstructed)
                self.assertIn("HALL_RECONSTRUCT_288", reconstructed)
                self.assertEqual(
                    result["archive"]["base_contract"]["sha256"],
                    BASE_SHA,
                )
                if selection == "new" or result["action"] == "new_session":
                    self.assertEqual(
                        result["delivery"]["text"], reconstructed
                    )

    def test_input_objects_are_not_mutated(self):
        scope = make_scope()
        base = make_base()
        task = make_task(
            authorization=["perm-a", "perm-b"],
            baseline_change="baseline moved",
            authorization_change="added read-only",
            acceptance_difference="new acceptance",
        )
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        messages = ["HALL_MUTATION_288"]
        snapshots = copy.deepcopy(
            (scope, base, task, candidate, sample, messages)
        )
        result = call_plan(
            scope=scope,
            base_contract=base,
            task=task,
            candidate=candidate,
            context_sample=sample,
            new_messages=messages,
        )
        self.assert_consistent(result)
        self.assertEqual(
            (scope, base, task, candidate, sample, messages),
            snapshots,
        )
        result["archive"]["task"]["authorization"].append("MUTATED")
        result["archive"]["new_messages"].append("MUTATED")
        result["archive"]["base_contract"]["version"] += "MUTATED"
        self.assertEqual(
            (scope, base, task, candidate, sample, messages),
            snapshots,
        )

    def test_two_task_archives_are_independent(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate)
        task_a = make_task(
            task_id="801",
            execution_id="exec-801",
            body="UNIQUE_BODY_A_801",
        )
        task_b = make_task(
            task_id="802",
            execution_id="exec-802",
            body="UNIQUE_BODY_B_802",
        )
        result_a = call_plan(
            scope=scope,
            candidate=candidate,
            task=task_a,
            context_sample=sample,
        )
        result_b = call_plan(
            scope=scope,
            candidate=candidate,
            task=task_b,
            context_sample=sample,
        )
        self.assert_incremental(result_a, "UNIQUE_BODY_A_801")
        self.assert_incremental(result_b, "UNIQUE_BODY_B_802")
        archive_a = result_a["archive"]
        archive_b = result_b["archive"]
        self.assertEqual(archive_a["task"]["task_id"], "801")
        self.assertEqual(archive_b["task"]["task_id"], "802")
        self.assertEqual(archive_a["task"]["execution_id"], "exec-801")
        self.assertEqual(archive_b["task"]["execution_id"], "exec-802")
        self.assertIn("UNIQUE_BODY_A_801", result_a["delivery"]["text"])
        self.assertNotIn("UNIQUE_BODY_B_802", result_a["delivery"]["text"])
        self.assertIn("UNIQUE_BODY_B_802", result_b["delivery"]["text"])
        self.assertNotIn("UNIQUE_BODY_A_801", result_b["delivery"]["text"])
        reconstructed_a = reconstruct_full_requirements(archive_a, base_contract=make_base())
        reconstructed_b = reconstruct_full_requirements(archive_b, base_contract=make_base())
        self.assertIn("UNIQUE_BODY_A_801", reconstructed_a)
        self.assertNotIn("UNIQUE_BODY_B_802", reconstructed_a)
        self.assertIn("UNIQUE_BODY_B_802", reconstructed_b)
        self.assertNotIn("UNIQUE_BODY_A_801", reconstructed_b)

    def test_authorization_and_changes_are_retained(self):
        task = make_task(
            authorization=["perm-a", "perm-b"],
            baseline_change="baseline moved to X",
            authorization_change="added read-only scope",
            acceptance_difference="acceptance now includes Y",
        )
        result = call_plan(task=task)
        self.assert_consistent(result)
        text = result["delivery"]["text"]
        self.assertIn("实现会话选择", text)
        for expected in (
            "perm-a",
            "perm-b",
            "baseline moved to X",
            "added read-only scope",
            "acceptance now includes Y",
        ):
            self.assertIn(expected, text)
        archived = result["archive"]["task"]
        self.assertEqual(archived["authorization"], ["perm-a", "perm-b"])
        self.assertEqual(
            archived["authorization_change"], ["added read-only scope"]
        )
        self.assertEqual(
            archived["baseline_change"], "baseline moved to X"
        )
        self.assertEqual(
            archived["acceptance_difference"],
            "acceptance now includes Y",
        )
        reconstructed = reconstruct_full_requirements(result["archive"], base_contract=make_base())
        self.assertIn("perm-a", reconstructed)
        self.assertIn("acceptance now includes Y", reconstructed)

    def test_reconstruct_rejects_bad_archive(self):
        result = call_plan()
        self.assert_consistent(result)
        bad = copy.deepcopy(result["archive"])
        bad["base_contract"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            reconstruct_full_requirements(bad, base_contract=make_base())
        bad_schema = copy.deepcopy(result["archive"])
        bad_schema["schema"] = "other"
        with self.assertRaises(ValueError):
            reconstruct_full_requirements(bad_schema, base_contract=make_base())
        with self.assertRaises(ValueError):
            reconstruct_full_requirements("not-an-archive")

    def test_all_action_shapes_are_json_safe_and_consistent(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        cases = [
            call_plan(candidate=None),
            call_plan(),
            call_plan(candidate=make_candidate(scope, state="busy")),
            call_plan(selection="bogus"),
        ]
        actions = [case["action"] for case in cases]
        self.assertEqual(actions[0], "new_session")
        self.assertEqual(actions[1], "reuse_session")
        self.assertEqual(actions[2], "wait")
        self.assertEqual(actions[3], "reject")
        for case in cases:
            self.assert_consistent(case)

    def test_repeated_calls_are_deterministic(self):
        first = call_plan(new_messages=["DETERMINISTIC_288"])
        second = call_plan(new_messages=["DETERMINISTIC_288"])
        self.assertEqual(first, second)

    def test_module_has_no_io_or_process_imports(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "import os",
            "from os",
            "subprocess",
            "socket",
            "requests",
            "urllib",
            "pathlib",
            "open(",
            "__file__",
        ):
            self.assertNotIn(forbidden, source)


class IndependentRegressions(unittest.TestCase):
    def kwargs(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        return dict(scope=scope, base_contract=make_base(), task=make_task(), candidate=candidate, context_sample=make_sample(scope, candidate))

    def test_no_candidate_requires_current_channel_evidence(self):
        args = self.kwargs()
        args["candidate"] = None
        result = plan_execution_session(**args)
        self.assertEqual(result["action"], "wait")
        self.assertIsNone(result["delivery"])

    def test_current_channel_checked_even_with_available_candidate(self):
        for candidate_present in (True, False):
            for channel in (None, {}, {"state": "busy", "active_writer": False, "execution_channel_exclusive": True}, {"state": "ready", "active_writer": True, "execution_channel_exclusive": True}, {"state": "ready", "active_writer": False, "execution_channel_exclusive": False}):
                args = self.kwargs()
                if not candidate_present:
                    args["candidate"] = None
                result = plan_execution_session(**args, selection="new", execution_channel=channel)
                self.assertEqual(result["action"], "wait")
                self.assertIsNone(result["delivery"])

    def test_reference_only_reuse_and_reference_archive(self):
        args = self.kwargs()
        args["base_contract"].pop("text")
        result = plan_execution_session(**args, execution_channel={"state": "ready", "active_writer": False, "execution_channel_exclusive": True})
        self.assertEqual(result["action"], "reuse_session")
        self.assertNotIn("text", result["archive"]["base_contract"])
        self.assertNotIn(BASE_ONLY, json.dumps(result))
        text = reconstruct_full_requirements(result["archive"], base_contract=make_base())
        self.assertIn(BASE_ONLY, text)

    def test_new_requires_full_body(self):
        args = self.kwargs()
        args["base_contract"].pop("text")
        args["context_sample"]["projected_tokens"] = 700
        result = plan_execution_session(**args, execution_channel={"state": "ready", "active_writer": False, "execution_channel_exclusive": True})
        self.assertEqual(result["action"], "reject")
        self.assertEqual(result["reason_code"], "reject_base_text_required")
        self.assertIsNone(result["delivery"])

    def test_reconstruction_verifies_referenced_body(self):
        args = self.kwargs()
        result = plan_execution_session(**args, execution_channel={"state": "ready", "active_writer": False, "execution_channel_exclusive": True})
        with self.assertRaises(ValueError):
            reconstruct_full_requirements(result["archive"])
        with self.assertRaises(ValueError):
            reconstruct_full_requirements(result["archive"], base_contract=make_base("wrong body"))

    def test_invalid_unicode_returns_sanitized_reject(self):
        for field in ("scope", "base", "task"):
            args = self.kwargs()
            if field == "scope":
                args["scope"]["continuity_key"] = "\ud800"
            elif field == "base":
                args["base_contract"]["text"] = "\ud800"
            else:
                args["task"]["body"] = "\ud800"
            result = plan_execution_session(**args)
            self.assertEqual(result["action"], "reject")
            json.dumps(result, ensure_ascii=False).encode("utf-8")

    def test_archive_changes_cannot_keep_old_delivery_receipt(self):
        result = call_plan()
        for field in ("task", "new_messages", "mode", "delivery"):
            archive = copy.deepcopy(result["archive"])
            if field == "task":
                archive["task"]["authorization"] = ["unauthorized edit"]
            elif field == "new_messages":
                archive["new_messages"].append("unrecorded new message")
            elif field == "mode":
                archive["mode"] = "full"
            else:
                archive["delivery"]["bytes"] = False
            with self.subTest(field=field), self.assertRaises(ValueError):
                reconstruct_full_requirements(archive, base_contract=make_base())

    def test_current_channel_not_inherited_from_other_scope_candidate(self):
        args = self.kwargs()
        args["candidate"]["scope"]["native_home_namespace"] = "other-home"
        result = plan_execution_session(**args, selection="new")
        self.assertEqual(result["action"], "wait")
        self.assertIsNone(result["delivery"])


class WindowCountStateTests(KernelTestCase):
    def setUp(self):
        self.scope = make_scope()
        self.candidate = make_candidate(self.scope)
        self.state = make_count_state(self.scope, self.candidate, 1)

    def test_initialize_counts_first_turn_once(self):
        state = copy.deepcopy(self.state)
        self.assertEqual(state["schema"], COUNT_STATE_SCHEMA)
        self.assertEqual(state["confirmed_count"], 1)
        self.assertTrue(state["first_turn_confirmed"])
        self.assertEqual(len(state["deliveries"]), 1)
        self.assertEqual(state["deliveries"][0]["ordinal"], 1)
        self.assertTrue(state["deliveries"][0]["first_turn"])
        self.assertIsNone(state["last_threshold_observation"])
        receipt = make_receipt(self.scope, self.candidate, first_turn=True)
        before = copy.deepcopy(state)
        duplicate = confirm_window_delivery(
            state=state, scope=self.scope, delivery=receipt
        )
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertFalse(duplicate["incremented"])
        self.assertEqual(duplicate["confirmed_count"], 1)
        self.assertEqual(state, before)

    def test_retry_with_new_delivery_id_is_idempotent(self):
        retry = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-retry",
            first_turn=False,
        )
        result = confirm_window_delivery(
            state=self.state, scope=self.scope, delivery=retry
        )
        self.assertEqual(result["status"], "duplicate")
        self.assertFalse(result["incremented"])
        self.assertEqual(result["confirmed_count"], 1)

    def test_duplicate_delivery_id_with_newer_revision_is_idempotent(self):
        retry = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-1",
            session_revision="rev-1b",
            first_turn=True,
        )
        result = confirm_window_delivery(
            state=self.state, scope=self.scope, delivery=retry
        )
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["confirmed_count"], 1)

    def test_same_identity_different_body_conflicts(self):
        conflict = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-conflict",
            body_sha256=hashlib.sha256(b"different body").hexdigest(),
            first_turn=False,
        )
        result = confirm_window_delivery(
            state=self.state, scope=self.scope, delivery=conflict
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["reason_code"], "logical_delivery_conflict")
        self.assertEqual(result["confirmed_count"], 1)

    def test_same_delivery_id_different_logical_identity_conflicts(self):
        conflict = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-1",
            task_id="900",
            execution_id="exec-other",
            first_turn=False,
        )
        result = confirm_window_delivery(
            state=self.state, scope=self.scope, delivery=conflict
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["reason_code"], "delivery_id_conflict")
        self.assertEqual(result["confirmed_count"], 1)

    def test_failed_preflight_tool_and_dry_run_do_not_count(self):
        for index, outcome in enumerate(
            (
                "failed",
                "rejected",
                "preflight",
                "dry_run",
                "planned",
                "repeated_planning",
                "tool_call",
                "internal_step",
                "canceled_before_delivery",
                "timed_out_before_delivery",
            )
        ):
            with self.subTest(outcome=outcome, index=index):
                receipt = make_receipt(
                    self.scope,
                    self.candidate,
                    delivery_id=f"deliv-{outcome}",
                    task_id=str(500 + index),
                    execution_id=f"exec-{outcome}",
                    outcome=outcome,
                    first_turn=False,
                )
                result = confirm_window_delivery(
                    state=self.state, scope=self.scope, delivery=receipt
                )
                self.assertEqual(result["status"], "not_counted")
                self.assertFalse(result["incremented"])
                self.assertEqual(result["confirmed_count"], 1)

    def test_cancelled_after_delivery_counts_and_does_not_decrement(self):
        receipt = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-cancelled",
            task_id="700",
            execution_id="exec-cancelled",
            outcome="canceled_after_delivery",
            first_turn=False,
        )
        counted = confirm_window_delivery(
            state=self.state, scope=self.scope, delivery=receipt
        )
        self.assertEqual(counted["status"], "incremented")
        self.assertEqual(counted["confirmed_count"], 2)
        late_failure = dict(receipt, outcome="failed")
        after = confirm_window_delivery(
            state=counted["state"], scope=self.scope, delivery=late_failure
        )
        self.assertEqual(after["status"], "duplicate")
        self.assertEqual(after["confirmed_count"], 2)

    def test_timeout_after_delivery_counts(self):
        receipt = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-timeout",
            task_id="701",
            execution_id="exec-timeout",
            outcome="timed_out_after_delivery",
            first_turn=False,
        )
        result = confirm_window_delivery(
            state=self.state, scope=self.scope, delivery=receipt
        )
        self.assertEqual(result["status"], "incremented")
        self.assertEqual(result["confirmed_count"], 2)

    def test_state_and_receipt_inputs_are_not_mutated(self):
        state_before = copy.deepcopy(self.state)
        receipt = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-new",
            task_id="702",
            execution_id="exec-new",
            first_turn=False,
        )
        receipt_before = copy.deepcopy(receipt)
        result = confirm_window_delivery(
            state=self.state, scope=self.scope, delivery=receipt
        )
        self.assertEqual(result["status"], "incremented")
        self.assertEqual(self.state, state_before)
        self.assertEqual(receipt, receipt_before)

    def test_invalid_state_and_count_zero_are_rejected(self):
        bad = copy.deepcopy(self.state)
        bad["confirmed_count"] = 0
        bad["deliveries"] = []
        receipt = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-new",
            task_id="703",
            execution_id="exec-new",
            first_turn=False,
        )
        result = confirm_window_delivery(
            state=bad, scope=self.scope, delivery=receipt
        )
        self.assertEqual(result["status"], "invalid")
        self.assertIsNone(result["state"])

    def test_ordinal_gap_and_duplicate_identity_are_invalid(self):
        gap = copy.deepcopy(self.state)
        gap["deliveries"][0]["ordinal"] = 2
        receipt = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-new",
            task_id="704",
            execution_id="exec-new",
            first_turn=False,
        )
        self.assertEqual(
            confirm_window_delivery(
                state=gap, scope=self.scope, delivery=receipt
            )["status"],
            "invalid",
        )
        second = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-1",
            first_turn=False,
        )
        count_two = make_count_state(self.scope, self.candidate, 2)
        duplicate_identity = copy.deepcopy(count_two)
        duplicate_identity["deliveries"][1]["delivery_id"] = "deliv-1"
        self.assertEqual(
            confirm_window_delivery(
                state=duplicate_identity, scope=self.scope, delivery=second
            )["status"],
            "invalid",
        )

    def test_revision_rollback_conflicts(self):
        numeric_candidate = make_candidate(self.scope, session_revision=1)
        numeric_state = make_count_state(self.scope, numeric_candidate, 1)
        second = make_receipt(
            self.scope,
            numeric_candidate,
            delivery_id="deliv-2",
            task_id="705",
            execution_id="exec-2",
            session_revision=2,
            first_turn=False,
        )
        counted = confirm_window_delivery(
            state=numeric_state, scope=self.scope, delivery=second
        )
        self.assertEqual(counted["status"], "incremented")
        rollback = make_receipt(
            self.scope,
            numeric_candidate,
            delivery_id="deliv-3",
            task_id="706",
            execution_id="exec-3",
            session_revision=1,
            first_turn=False,
        )
        result = confirm_window_delivery(
            state=counted["state"], scope=self.scope, delivery=rollback
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["reason_code"], "revision_rollback")
        self.assertEqual(result["confirmed_count"], 2)

    def test_string_revision_change_is_unverifiable(self):
        receipt = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-string-revision",
            task_id="706",
            execution_id="exec-string-revision",
            session_revision="rev-2",
            first_turn=False,
        )
        result = confirm_window_delivery(
            state=self.state, scope=self.scope, delivery=receipt
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["reason_code"], "revision_unverifiable")
        self.assertEqual(result["confirmed_count"], 1)

    def test_wrong_scope_generation_and_window_conflict(self):
        wrong_window = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-wrong-window",
            task_id="707",
            execution_id="exec-wrong-window",
            native_session_id="sess-other",
            first_turn=False,
        )
        self.assertEqual(
            confirm_window_delivery(
                state=self.state, scope=self.scope, delivery=wrong_window
            )["status"],
            "conflict",
        )
        other_scope = make_scope(service_launch_id="launch:other")
        wrong_scope = make_receipt(
            other_scope,
            self.candidate,
            delivery_id="deliv-wrong-scope",
            task_id="708",
            execution_id="exec-wrong-scope",
            first_turn=False,
        )
        self.assertEqual(
            confirm_window_delivery(
                state=self.state, scope=other_scope, delivery=wrong_scope
            )["status"],
            "conflict",
        )
        other_generation = make_scope(session_generation=8)
        wrong_generation = make_receipt(
            other_generation,
            self.candidate,
            delivery_id="deliv-wrong-generation",
            task_id="709",
            execution_id="exec-wrong-generation",
            first_turn=False,
        )
        self.assertEqual(
            confirm_window_delivery(
                state=self.state,
                scope=other_generation,
                delivery=wrong_generation,
            )["status"],
            "conflict",
        )

    def test_initialize_does_not_reset_existing_window(self):
        new_first = make_receipt(
            self.scope,
            self.candidate,
            delivery_id="deliv-new-first",
            task_id="710",
            execution_id="exec-new-first",
            first_turn=True,
        )
        result = initialize_window_count(
            scope=self.scope,
            native_session_id=self.candidate["native_session_id"],
            first_delivery=new_first,
            previous_state=self.state,
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["reason_code"], "state_already_initialized")
        self.assertEqual(result["confirmed_count"], 1)
        again = initialize_window_count(
            scope=self.scope,
            native_session_id=self.candidate["native_session_id"],
            first_delivery=make_receipt(
                self.scope, self.candidate, first_turn=True
            ),
            previous_state=self.state,
        )
        self.assertEqual(again["status"], "duplicate")
        self.assertEqual(again["confirmed_count"], 1)

    def test_initialize_with_previous_state_for_other_window_conflicts(self):
        other_scope = make_scope(session_generation=8)
        other_candidate = make_candidate(
            other_scope, native_session_id="sess-288-8", session_revision="rev-8"
        )
        first = make_receipt(
            other_scope, other_candidate, first_turn=True
        )
        result = initialize_window_count(
            scope=other_scope,
            native_session_id="sess-288-8",
            first_delivery=first,
            previous_state=self.state,
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["reason_code"], "previous_state_scope_mismatch")

    def test_observation_update_does_not_increment_count(self):
        observation = {
            "native_session_id": self.candidate["native_session_id"],
            "session_generation": self.scope["session_generation"],
            "session_revision": self.candidate["session_revision"],
            "used_tokens": 700,
            "capacity_tokens": 1000,
            "source": "projected",
            "sampled_at": "2026-10-20T13:00:00+00:00",
        }
        state_before = copy.deepcopy(self.state)
        recorded = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=self.state, scope=self.scope, observation=observation
        )
        self.assertEqual(recorded["status"], "recorded")
        self.assertFalse(recorded["incremented"])
        self.assertEqual(recorded["confirmed_count"], 1)
        self.assertTrue(
            recorded["state"]["last_threshold_observation"]["threshold_met"]
        )
        self.assertEqual(self.state, state_before)
        duplicate = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=recorded["state"], scope=self.scope, observation=observation
        )
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertEqual(duplicate["confirmed_count"], 1)

    def test_observation_rejects_rollback_and_bad_numbers(self):
        numeric_candidate = make_candidate(self.scope, session_revision=1)
        numeric_state = make_count_state(self.scope, numeric_candidate, 1)
        second = make_receipt(
            self.scope,
            numeric_candidate,
            delivery_id="deliv-2",
            task_id="711",
            execution_id="exec-2",
            session_revision=2,
            first_turn=False,
        )
        state = confirm_window_delivery(
            state=numeric_state, scope=self.scope, delivery=second
        )["state"]
        rollback = {
            "native_session_id": numeric_candidate["native_session_id"],
            "session_generation": self.scope["session_generation"],
            "session_revision": 1,
            "used_tokens": 100,
            "capacity_tokens": 1000,
            "source": "projected",
            "sampled_at": "2026-10-20T13:00:00+00:00",
        }
        result = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=state, scope=self.scope, observation=rollback
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["reason_code"], "revision_rollback")
        invalid = dict(rollback, session_revision=2, used_tokens=-1)
        result = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=state, scope=self.scope, observation=invalid
        )
        self.assertEqual(result["status"], "invalid")


class FallbackPlanningTests(KernelTestCase):
    def test_adapter_and_kernel_fallback_whitelists_match(self):
        self.assertEqual(
            execution_sessions.UNAVAILABILITY_SCHEMA,
            dsh_context_metrics.UNAVAILABILITY_SCHEMA,
        )
        self.assertEqual(
            execution_sessions._FALLBACK_REASON_CATEGORIES,
            dsh_context_metrics._FALLBACK_REASON_CATEGORIES,
        )

    def test_missing_metrics_count_1_allows_second(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        plan = make_fallback_plan(scope, candidate, 1)
        self.assert_consistent(plan)
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["reason_code"], "reuse_missing_metrics_fallback")
        self.assertEqual(plan["briefing_mode"], "incremental")
        self.assertEqual(plan["window_count"]["confirmed_count"], 1)
        self.assertEqual(plan["window_count"]["proposed_ordinal"], 2)
        self.assertTrue(
            plan["window_count"]["requires_delivery_confirmation"]
        )
        self.assertEqual(
            plan["window_count"]["count_merge"], "after_confirmed_delivery"
        )
        self.assertNotIn("state", plan["window_count"])
        self.assertNotIn(BASE_ONLY, plan["delivery"]["text"])
        reconstructed = reconstruct_full_requirements(
            plan["archive"], base_contract=make_base()
        )
        self.assertIn(BASE_ONLY, reconstructed)
        self.assertIn(TASK_BODY, reconstructed)
        self.assertEqual(
            plan["archive"]["task"]["authorization"],
            [make_task()["authorization"]],
        )
        self.assertEqual(state["confirmed_count"], 1)

    def test_missing_metrics_count_9_allows_tenth(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        plan = make_fallback_plan(scope, candidate, 9)
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["window_count"]["confirmed_count"], 9)
        self.assertEqual(plan["window_count"]["proposed_ordinal"], 10)

    def test_missing_metrics_count_10_forces_full_new(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        plan = make_fallback_plan(scope, candidate, 10)
        self.assert_consistent(plan)
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_fallback_exhausted")
        self.assertEqual(plan["briefing_mode"], "full")
        self.assertIn(BASE_ONLY, plan["delivery"]["text"])
        self.assertEqual(plan["window_count"]["status"], "exhausted")
        self.assertIsNone(plan["window_count"]["proposed_ordinal"])

    def test_count_9_confirm_10_then_11_new(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        plan = make_fallback_plan(scope, candidate, 9)
        self.assertEqual(plan["window_count"]["proposed_ordinal"], 10)
        state = make_count_state(scope, candidate, 9)
        tenth = make_receipt(
            scope,
            candidate,
            delivery_id="deliv-10",
            task_id="810",
            execution_id="exec-10",
            first_turn=False,
        )
        merged = confirm_window_delivery(
            state=state, scope=scope, delivery=tenth
        )
        self.assertEqual(merged["status"], "incremented")
        self.assertEqual(merged["confirmed_count"], 10)
        next_plan = make_fallback_plan(
            scope, candidate, 9, window_count_state=merged["state"]
        )
        self.assertEqual(next_plan["action"], "new_session")
        self.assertEqual(next_plan["reason_code"], "new_fallback_exhausted")

    def test_missing_metrics_without_count_forces_new(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        plan = make_fallback_plan(
            scope, candidate, 1, window_count_state=None
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_fallback_count_unverified")
        self.assertEqual(plan["window_count"]["status"], "missing")
        self.assertIn(BASE_ONLY, plan["delivery"]["text"])

    def test_missing_metrics_with_corrupt_state_forces_new(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        bad = make_count_state(scope, candidate, 1)
        bad["deliveries"][0]["ordinal"] = 99
        plan = make_fallback_plan(
            scope, candidate, 1, window_count_state=bad
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["window_count"]["status"], "invalid")
        self.assertIn("state_error", plan["window_count"])

    def test_state_revision_below_confirmed_count_is_invalid(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        bad = make_count_state(scope, candidate, 2)
        bad["state_revision"] = 1
        plan = make_fallback_plan(
            scope, candidate, 2, window_count_state=bad
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_fallback_count_unverified")
        self.assertEqual(plan["window_count"]["status"], "invalid")

    def test_missing_metrics_wrong_window_scope_generation_launch_base(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        other_scope = make_scope(session_generation=8)
        other_candidate = make_candidate(
            other_scope,
            native_session_id="sess-288-8",
            session_revision="rev-8",
        )
        cases = {
            "wrong_window": make_count_state(
                scope,
                make_candidate(scope, native_session_id="sess-other"),
                1,
            ),
            "wrong_generation": make_count_state(
                other_scope, other_candidate, 1
            ),
            "wrong_launch": make_count_state(
                make_scope(service_launch_id="launch:other"),
                candidate,
                1,
            ),
            "wrong_base": make_count_state(
                make_scope(base_contract_version="v2"), candidate, 1
            ),
        }
        for name, state in cases.items():
            with self.subTest(name=name):
                plan = make_fallback_plan(
                    scope,
                    candidate,
                    1,
                    window_count_state=state,
                    context_unavailability=make_unavailability(scope, candidate),
                )
                self.assertEqual(plan["action"], "new_session", name)
                self.assertEqual(
                    plan["reason_code"], "new_fallback_count_unverified", name
                )
                self.assertNotEqual(
                    plan["window_count"]["status"], "eligible", name
                )

    def test_bare_none_and_unknown_reason_do_not_fallback(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        bare = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=None,
            window_count_state=state,
        )
        self.assertEqual(bare["action"], "new_session")
        self.assertEqual(bare["reason_code"], "new_context_unknown")
        classification = make_unavailability(scope, candidate)
        classification["reason_code"] = "unknown"
        classification["category"] = "unknown"
        unknown = make_fallback_plan(
            scope,
            candidate,
            1,
            context_unavailability=classification,
            window_count_state=state,
        )
        self.assertEqual(unknown["action"], "new_session")
        self.assertEqual(
            unknown["reason_code"], "new_fallback_classification_unverified"
        )

    def test_high_observation_blocks_fallback(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        observed = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=state,
            scope=scope,
            observation={
                "native_session_id": candidate["native_session_id"],
                "session_generation": scope["session_generation"],
                "session_revision": candidate["session_revision"],
                "used_tokens": 700,
                "capacity_tokens": 1000,
                "source": "projected",
                "sampled_at": "2026-10-20T13:00:00+00:00",
            },
        )
        plan = make_fallback_plan(
            scope, candidate, 1, window_count_state=observed["state"]
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(
            plan["reason_code"], "new_fallback_threshold_observed"
        )
        self.assertTrue(
            plan["window_count"]["last_threshold_observation_met"]
        )

    def test_low_or_absent_observation_allows_fallback(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        observed = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=state,
            scope=scope,
            observation={
                "native_session_id": candidate["native_session_id"],
                "session_generation": scope["session_generation"],
                "session_revision": candidate["session_revision"],
                "used_tokens": 599,
                "capacity_tokens": 1000,
                "source": "projected",
                "sampled_at": "2026-10-20T13:00:00+00:00",
            },
        )
        plan = make_fallback_plan(
            scope, candidate, 1, window_count_state=observed["state"]
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertFalse(
            plan["window_count"]["last_threshold_observation_met"]
        )
        absent = make_fallback_plan(scope, candidate, 1)
        self.assertEqual(absent["action"], "reuse_session")
        self.assertIsNone(
            absent["window_count"]["last_threshold_observation_met"]
        )

    def test_known_high_metrics_ignore_eligible_classification(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, projected_tokens=700)
        state = make_count_state(scope, candidate, 1)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=sample,
            context_unavailability=make_unavailability(scope, candidate),
            window_count_state=state,
        )
        self.assertEqual(result["action"], "new_session")
        self.assertEqual(result["reason_code"], "new_context_threshold")

    def test_known_low_metrics_override_old_high_observation(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        observed = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=state,
            scope=scope,
            observation={
                "native_session_id": candidate["native_session_id"],
                "session_generation": scope["session_generation"],
                "session_revision": candidate["session_revision"],
                "used_tokens": 700,
                "capacity_tokens": 1000,
                "source": "projected",
                "sampled_at": "2026-10-20T12:59:00+00:00",
            },
        )
        sample = make_sample(scope, candidate, projected_tokens=200)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=sample,
            window_count_state=observed["state"],
        )
        self.assertEqual(result["action"], "reuse_session")
        intent = result["window_count"]["observation_intent"]
        updated = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=observed["state"],
            scope=scope,
            observation=intent["observation"],
        )
        self.assertFalse(
            updated["state"]["last_threshold_observation"]["threshold_met"]
        )

    def test_confirmed_first_turn_with_zero_count_is_unverified_in_plan(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        bad = make_count_state(scope, candidate, 1)
        bad["confirmed_count"] = 0
        bad["deliveries"] = []
        plan = make_fallback_plan(
            scope, candidate, 1, window_count_state=bad
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_fallback_count_unverified")
        self.assertEqual(plan["window_count"]["status"], "invalid")

    def test_different_function_20_percent_does_not_reuse(self):
        scope = make_scope()
        other_scope = make_scope(project_id="prj-other")
        candidate = make_candidate(scope, scope=other_scope)
        sample = make_sample(
            scope, candidate, projected_tokens=200, pressure_tokens=200
        )
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=sample,
        )
        self.assertEqual(result["action"], "new_session")
        self.assertEqual(result["reason_code"], "new_scope_mismatch")
        self.assertIn(BASE_ONLY, result["delivery"]["text"])

    def test_writer_or_no_exclusive_waits_before_fallback(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        classification = make_unavailability(scope, candidate)
        cases = (
            (
                {
                    "state": "ready",
                    "active_writer": True,
                    "execution_channel_exclusive": True,
                },
                "wait_active_writer",
            ),
            (
                {
                    "state": "ready",
                    "active_writer": False,
                    "execution_channel_exclusive": False,
                },
                "wait_channel_not_exclusive",
            ),
            (
                {"state": "ready", "active_writer": False},
                "wait_exclusive_unknown",
            ),
        )
        for channel, reason in cases:
            with self.subTest(reason=reason):
                result = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=None,
                    context_unavailability=classification,
                    window_count_state=state,
                    execution_channel=channel,
                )
                self.assertEqual(result["action"], "wait")
                self.assertEqual(result["reason_code"], reason)

    def test_known_missing_known_missing_keeps_count(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        low = make_sample(scope, candidate, projected_tokens=200)
        first = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=low,
            window_count_state=state,
        )
        self.assertEqual(first["action"], "reuse_session")
        recorded = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=state,
            scope=scope,
            observation=first["window_count"]["observation_intent"]["observation"],
        )
        missing = make_unavailability(scope, candidate)
        first_missing = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=None,
            context_unavailability=missing,
            window_count_state=recorded["state"],
        )
        self.assertEqual(first_missing["action"], "reuse_session")
        self.assertEqual(first_missing["window_count"]["confirmed_count"], 1)
        self.assertEqual(first_missing["window_count"]["proposed_ordinal"], 2)
        receipt = make_receipt(
            scope,
            candidate,
            delivery_id="deliv-cycle-2",
            task_id="900",
            execution_id="exec-cycle-2",
            first_turn=False,
        )
        counted = confirm_window_delivery(
            state=recorded["state"], scope=scope, delivery=receipt
        )
        self.assertEqual(counted["confirmed_count"], 2)
        second = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=low,
            window_count_state=counted["state"],
        )
        self.assertEqual(second["action"], "reuse_session")
        recorded_again = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=counted["state"],
            scope=scope,
            observation=second["window_count"]["observation_intent"]["observation"],
        )
        second_missing = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=None,
            context_unavailability=missing,
            window_count_state=recorded_again["state"],
        )
        self.assertEqual(second_missing["action"], "reuse_session")
        self.assertEqual(
            second_missing["window_count"]["confirmed_count"], 2
        )
        self.assertEqual(
            second_missing["window_count"]["proposed_ordinal"], 3
        )

    def test_known_metrics_ignore_missing_or_invalid_count(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, projected_tokens=100)
        for label, state in (
            ("missing", None),
            ("invalid", {"schema": "bad"}),
            ("count20", make_count_state(scope, candidate, 20)),
        ):
            with self.subTest(label=label):
                result = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=sample,
                    window_count_state=state,
                )
                self.assertEqual(result["action"], "reuse_session", label)
                self.assertEqual(result["reason_code"], "reuse_session", label)

    def test_known_high_metrics_ignore_count_one(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, projected_tokens=700)
        state = make_count_state(scope, candidate, 1)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=sample,
            window_count_state=state,
        )
        self.assertEqual(result["action"], "new_session")
        self.assertEqual(result["reason_code"], "new_context_threshold")
        self.assertEqual(result["window_count"]["confirmed_count"], 1)

    def test_known_metrics_observation_intent_does_not_increment_count(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, projected_tokens=200)
        state = make_count_state(scope, candidate, 1)
        before = copy.deepcopy(state)
        result = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=sample,
            window_count_state=state,
        )
        self.assertEqual(result["action"], "reuse_session")
        intent = result["window_count"]["observation_intent"]
        self.assertTrue(intent["requires_host_persist"])
        self.assertEqual(state, before)
        recorded = record_threshold_observation(
            now="2026-10-20T13:02:00+00:00",
            state=state,
            scope=scope,
            observation=intent["observation"],
        )
        self.assertEqual(recorded["confirmed_count"], 1)
        self.assertFalse(recorded["incremented"])

    def test_plan_does_not_preincrement_and_repeats_identically(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 3)
        before = copy.deepcopy(state)
        first = make_fallback_plan(scope, candidate, 3)
        second = make_fallback_plan(scope, candidate, 3)
        self.assertEqual(first, second)
        self.assertEqual(state, before)
        self.assertEqual(first["window_count"]["confirmed_count"], 3)
        self.assertEqual(first["window_count"]["proposed_ordinal"], 4)
        self.assertNotIn("state", first["window_count"])

    def test_busy_channel_and_candidate_wait_before_fallback(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        classification = make_unavailability(scope, candidate)
        busy_channel = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=None,
            context_unavailability=classification,
            window_count_state=state,
            execution_channel={
                "state": "busy",
                "active_writer": False,
                "execution_channel_exclusive": True,
            },
        )
        self.assertEqual(busy_channel["action"], "wait")
        self.assertEqual(busy_channel["reason_code"], "wait_channel_busy")
        busy_candidate = call_plan(
            scope=scope,
            candidate=make_candidate(scope, state="busy"),
            context_sample=None,
            context_unavailability=classification,
            window_count_state=state,
        )
        self.assertEqual(busy_candidate["action"], "wait")
        self.assertEqual(busy_candidate["reason_code"], "wait_candidate_busy")

    def test_first_turn_and_contract_guards_win_before_fallback(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        classification = make_unavailability(scope, candidate)
        unconfirmed = call_plan(
            scope=scope,
            candidate=make_candidate(scope, first_turn_confirmed=False),
            context_sample=None,
            context_unavailability=classification,
            window_count_state=state,
        )
        self.assertEqual(unconfirmed["action"], "new_session")
        self.assertEqual(
            unconfirmed["reason_code"], "new_first_turn_unconfirmed"
        )
        changed_scope = dict(scope, base_contract_version="v2")
        changed_candidate = make_candidate(scope, session_revision="rev-2")
        changed = call_plan(
            scope=changed_scope,
            base_contract=make_base(version="v2"),
            candidate=changed_candidate,
            context_sample=None,
            context_unavailability=make_unavailability(
                changed_scope, changed_candidate
            ),
            window_count_state=state,
        )
        self.assertEqual(changed["action"], "new_session")
        self.assertEqual(changed["reason_code"], "new_base_contract_changed")

    def test_invalid_projected_with_eligible_classification_is_new(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        sample = make_sample(
            scope, candidate, projected_tokens=-1, pressure_tokens=100
        )
        plan = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=sample,
            context_unavailability=make_unavailability(scope, candidate),
            window_count_state=state,
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["metrics"]["reason_code"], "projected_invalid")
        self.assertNotEqual(plan["window_count"]["status"], "eligible")

    def test_classification_wrong_scope_session_or_revision(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 1)
        cases = {
            "wrong_scope": make_unavailability(
                make_scope(project_id="prj-other"), candidate
            ),
            "wrong_session": make_unavailability(
                scope,
                make_candidate(scope, native_session_id="sess-other"),
            ),
            "wrong_revision": make_unavailability(
                scope,
                make_candidate(scope, session_revision="rev-other"),
            ),
        }
        for name, classification in cases.items():
            with self.subTest(name=name):
                plan = call_plan(
                    scope=scope,
                    candidate=candidate,
                    context_sample=None,
                    context_unavailability=classification,
                    window_count_state=state,
                )
                self.assertEqual(plan["action"], "new_session", name)
                self.assertEqual(
                    plan["reason_code"],
                    "new_fallback_classification_unverified",
                    name,
                )

    def test_allow_fallback_kwarg_is_rejected(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        with self.assertRaises(TypeError):
            plan_execution_session(
                scope=scope,
                base_contract=make_base(),
                task=make_task(),
                candidate=candidate,
                context_sample=None,
                execution_channel={
                    "state": "ready",
                    "active_writer": False,
                    "execution_channel_exclusive": True,
                },
                allow_fallback=True,
            )

    def test_runtime_unsupported_classification_reaches_fallback(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        plan = make_fallback_plan(
            scope,
            candidate,
            1,
            context_unavailability=make_unavailability(
                scope, candidate, reason="runtime_unsupported"
            ),
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(
            plan["window_count"]["classification_reason"],
            "runtime_unsupported",
        )

    def test_different_task_ids_do_not_reset_count(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        state = make_count_state(scope, candidate, 2)
        plan = make_fallback_plan(
            scope,
            candidate,
            2,
            task=make_task(
                task_id="999", execution_id="exec-999", body="BODY_999"
            ),
        )
        self.assertEqual(plan["action"], "reuse_session")
        self.assertEqual(plan["window_count"]["confirmed_count"], 2)
        self.assertEqual(plan["window_count"]["proposed_ordinal"], 3)
        self.assertEqual(plan["archive"]["task"]["task_id"], "999")

    def test_new_generation_has_independent_state(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        old_state = make_count_state(scope, candidate, 2)
        new_scope = make_scope(session_generation=8)
        new_candidate = make_candidate(
            new_scope, native_session_id="sess-288-8", session_revision="rev-8"
        )
        plan = make_fallback_plan(
            new_scope,
            new_candidate,
            1,
            window_count_state=old_state,
            context_unavailability=make_unavailability(
                new_scope, new_candidate
            ),
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_fallback_count_unverified")
        self.assertNotEqual(plan["window_count"]["status"], "eligible")
        new_state = make_count_state(new_scope, new_candidate, 1)
        self.assertEqual(new_state["session_generation"], 8)
        self.assertEqual(new_state["confirmed_count"], 1)
        self.assertEqual(old_state["confirmed_count"], 2)

    def test_known_metrics_without_count_then_missing_forces_new(self):
        scope = make_scope()
        candidate = make_candidate(scope)
        sample = make_sample(scope, candidate, projected_tokens=200)
        known = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=sample,
            window_count_state=None,
        )
        self.assertEqual(known["action"], "reuse_session")
        missing = call_plan(
            scope=scope,
            candidate=candidate,
            context_sample=None,
            window_count_state=None,
        )
        self.assertEqual(missing["action"], "new_session")
        self.assertEqual(missing["reason_code"], "new_context_unknown")

    def test_candidate_revision_rollback_forces_new(self):
        scope = make_scope()
        candidate = make_candidate(scope, session_revision=2)
        state = make_count_state(scope, candidate, 2)
        stale_candidate = make_candidate(scope, session_revision=1)
        plan = make_fallback_plan(
            scope,
            stale_candidate,
            2,
            window_count_state=state,
            context_unavailability=make_unavailability(scope, stale_candidate),
        )
        self.assertEqual(plan["action"], "new_session")
        self.assertEqual(plan["reason_code"], "new_fallback_count_unverified")
        self.assertEqual(
            plan["window_count"]["reason_code"], "state_revision_rollback"
        )


class FallbackReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.scope = make_scope()
        self.candidate = make_candidate(self.scope, session_revision=100)
        self.state = make_count_state(self.scope, self.candidate)
        self.now = "2026-10-20T13:02:00+00:00"
        self.clock = {"now": self.now, "max_age_seconds": 60}

    def plan(self, **kwargs):
        return make_fallback_plan(self.scope, self.candidate, **kwargs)

    def observation(self, **changes):
        value = dict(native_session_id=self.candidate["native_session_id"],
                     session_generation=self.scope["session_generation"],
                     session_revision=100, used_tokens=700, capacity_tokens=1000,
                     source="projected", sampled_at="2026-10-20T13:01:00+00:00")
        value.update(changes)
        return value

    def test_fallback_requires_explicit_valid_clock(self):
        for clock in (None, {}, {"now": self.now, "max_age_seconds": True},
                      {"now": "bad", "max_age_seconds": 60}):
            with self.subTest(clock=clock):
                result = self.plan(fallback_clock=clock)
                self.assertEqual(result["action"], "new_session")
                self.assertEqual(result["window_count"]["reason_code"], "classification_clock_invalid")

    def test_future_or_expired_classification_never_reuses(self):
        for when in ("2099-01-01T00:00:00+00:00", "2026-10-20T12:00:00+00:00"):
            with self.subTest(when=when):
                classification = make_unavailability(self.scope, self.candidate, observed_at=when)
                self.assertEqual(self.plan(context_unavailability=classification, fallback_clock=self.clock)["action"], "new_session")

    def test_classification_clock_boundary_is_exact(self):
        self.assertEqual(self.plan(fallback_clock=self.clock)["action"], "reuse_session")
        self.clock["now"] = "2026-10-20T13:02:00.000001+00:00"
        self.assertEqual(self.plan(fallback_clock=self.clock)["action"], "new_session")

    def test_known_metric_does_not_need_fallback_clock(self):
        for used, action in ((699, "reuse_session"), (700, "new_session")):
            result = call_plan(scope=self.scope, candidate=self.candidate,
                               context_sample=make_sample(self.scope, self.candidate, projected_tokens=used),
                               window_count_state=make_count_state(self.scope, self.candidate, 12),
                               fallback_clock=None)
            self.assertEqual(result["action"], action)

    def test_raw_missing_capacity_cannot_hide_invalid_projected(self):
        raw = make_sample(self.scope, self.candidate, projected_tokens=-1)
        raw.pop("context_window")
        classification = make_unavailability(self.scope, self.candidate)
        classification["reason_code"] = "capacity_missing"
        classification["category"] = "capacity_missing"
        result = call_plan(scope=self.scope, candidate=self.candidate, context_sample=raw,
                           context_unavailability=classification, window_count_state=self.state)
        self.assertEqual(result["action"], "new_session")
        self.assertEqual(result["window_count"]["reason_code"], "raw_projected_invalid")

    def test_expired_raw_sample_cannot_hide_invalid_capacity_or_aliases(self):
        for changes in ({"context_window": -1}, {"projected_tokens": True}, {"pressureTokens": 50}):
            raw = make_sample(self.scope, self.candidate, now="2026-10-20T13:30:00+00:00", **changes)
            result = call_plan(scope=self.scope, candidate=self.candidate, context_sample=raw,
                               context_unavailability=make_unavailability(self.scope, self.candidate),
                               window_count_state=self.state)
            self.assertEqual(result["action"], "new_session")
            self.assertTrue(result["window_count"]["reason_code"].startswith("raw_"))

    def test_observation_requires_now_and_rejects_future(self):
        for now in (None, "2026-10-20T13:00:00+00:00"):
            result = execution_sessions.record_threshold_observation(state=self.state, scope=self.scope,
                                                                     observation=self.observation(), now=now)
            self.assertEqual(result["status"], "invalid")
        self.assertIsNone(self.state["last_threshold_observation"])

    def test_old_low_cannot_erase_high_observation(self):
        high = record_threshold_observation(state=self.state, scope=self.scope, observation=self.observation(), now=self.now)["state"]
        result = record_threshold_observation(state=high, scope=self.scope,
                    observation=self.observation(used_tokens=100, sampled_at="2026-10-20T13:00:00+00:00"), now=self.now)
        self.assertEqual(result["reason_code"], "observation_time_rollback")
        self.assertEqual(result["state"], high)
        self.assertEqual(self.plan(window_count_state=result["state"])["reason_code"], "new_fallback_threshold_observed")

    def test_same_event_conflicting_low_is_not_overwritten(self):
        high = record_threshold_observation(state=self.state, scope=self.scope, observation=self.observation(), now=self.now)["state"]
        result = record_threshold_observation(state=high, scope=self.scope, observation=self.observation(used_tokens=100), now=self.now)
        self.assertEqual(result["reason_code"], "observation_event_conflict")
        self.assertEqual(result["state"], high)

    def test_newer_low_records_without_resetting_count(self):
        state = make_count_state(self.scope, self.candidate, 9)
        high = record_threshold_observation(state=state, scope=self.scope, observation=self.observation(), now=self.now)["state"]
        low = record_threshold_observation(state=high, scope=self.scope,
                    observation=self.observation(used_tokens=100, sampled_at="2026-10-20T13:01:01+00:00"), now=self.now)["state"]
        self.assertEqual(low["confirmed_count"], 9)
        self.assertEqual(self.plan(window_count_state=low)["window_count"]["proposed_ordinal"], 10)

    def test_future_persisted_observation_is_untrusted(self):
        result = record_threshold_observation(state=self.state, scope=self.scope,
                    observation=self.observation(used_tokens=100), now=self.now)
        state = result["state"]
        state["last_threshold_observation"]["sampled_at"] = "2099-01-01T00:00:00+00:00"
        result = self.plan(window_count_state=state)
        self.assertEqual(result["action"], "new_session")
        self.assertIsNone(result["window_count"]["proposed_ordinal"])

    def test_non_string_outcome_returns_invalid_without_throwing(self):
        for outcome in ([], {}, True, None):
            receipt = make_receipt(self.scope, self.candidate, outcome=outcome)
            result = confirm_window_delivery(state=self.state, scope=self.scope, delivery=receipt)
            self.assertEqual(result["status"], "invalid")
            self.assertEqual(result["state"], self.state)

    def test_reversed_delivery_revisions_are_not_complete_history(self):
        state = make_count_state(self.scope, self.candidate, 2)
        state["deliveries"][1]["session_revision"] = 99
        self.assertEqual(self.plan(window_count_state=state)["reason_code"], "new_fallback_count_unverified")

    def test_host_capability_cannot_masquerade_as_adapter_reason(self):
        classification = make_unavailability(self.scope, self.candidate)
        classification["reason_code"] = "capacity_missing"
        classification["category"] = "capacity_missing"
        result = self.plan(context_unavailability=classification)
        self.assertEqual(result["action"], "new_session")


if __name__ == "__main__":
    unittest.main(verbosity=2)
