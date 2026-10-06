"""C2-A1 受控等待（``controlled_wait``）与 ``caller_identity`` 的定向回归。

覆盖：
- 非受控路径零新增 HTTP / 零新字段 / query_stats 四键不变；
- G1–G7 进入门禁（含严格 timeout 输入矩阵、旧服务、human 身份、身份不匹配、status 失效）；
- 30 秒重读节奏与 mode_changed / controller_changed（含字段失效、两个独立版本）；
- 单次 deadline 记账（身份/项目/轮询/重读/sleep）、per-request min(10, remaining) clamp；
- R5 早退：预算耗尽返回最近一次成功轮询集合，从未轮询时 tasks=[] / task_count=0；
- 连接、getresponse/read 阶段裸 TimeoutError / 网络 OSError 归一为 TalkToolError；
- ``talk_list_agents`` 的 caller_identity 三键（成功 / 失败不阻断 / 非项目 null 且不发身份请求）；
- 工具 schema / 描述 / --check 说明 / 九工具集合不变。

测试使用脚本化假 HTTP、假时钟与真实隔离服务，不做真实长等待、不调用模型、不操作浏览器。
"""

import copy
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import httpx
from sqlmodel import select

import server.main as main
from bridges import talk_task_tools
from bridges import talk_terminal_mcp as terminal
from bridges.talk_task_tools import (
    CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS,
    TOOL_SCHEMAS,
    WAIT_CLIENT_MARGIN_SECONDS,
    WAIT_DEFAULT_TIMEOUT_SECONDS,
    WAIT_MAX_TIMEOUT_SECONDS,
    WAIT_REQUEST_TIMEOUT_SECONDS,
    TalkToolError,
    dispatch_tool,
    wait_tasks,
)
from server.models import AgentTask, Message, Project
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

PROJECT_ID = "prj_ctrl"
LEGACY_WAIT_FIELDS = {
    "timed_out",
    "return_reason",
    "workflow_statuses",
    "project_id",
    "task_ids",
    "requested_timeout_seconds",
    "timeout_seconds",
    "max_timeout_seconds",
    "elapsed_seconds",
    "task_count",
    "tasks_returned",
    "tasks_truncated",
    "tasks_omitted_count",
    "omitted_task_ids",
    "matched_task_ids",
    "tasks",
    "tasks_note",
    "query_stats",
    "counting_note",
}
TOOL_NAMES = (
    "talk_list_agents",
    "talk_delegate_task",
    "talk_get_task",
    "talk_list_tasks",
    "talk_wait_tasks",
    "talk_reply_task",
    "talk_cancel_task",
    "talk_collect_result",
    "talk_get_delivery",
)
MEMBERS_ME_AGENT = {"id": "agent:worker", "kind": "agent", "display_name": "Worker"}


def project_payload(**overrides):
    """默认是一个“门禁全过”的项目响应：active + agent:worker assigned（两个独立版本为 1）。"""
    payload = {
        "project_id": PROJECT_ID,
        "development_requirements": None,
        "controller_mode": "active",
        "controller_mode_version": 1,
        "controller_member_id": "agent:worker",
        "controller_assignment_version": 1,
        "controller_assignment_status": "assigned",
    }
    payload.update(overrides)
    return payload


def task_payload(task_id=7, workflow_status="assigned"):
    return {
        "id": task_id,
        "title": "受控等待任务",
        "project_id": PROJECT_ID,
        "task_kind": "general",
        "status": "queued",
        "workflow_status": workflow_status,
        "created_by": "human:bobo",
        "target_member_id": "agent:worker",
        "hall_group_id": "group:ctrl",
        "result_message_id": None,
        "updated_at": "2026-10-06T00:00:00+00:00",
    }


class FakeApi:
    """脚本化 ``_api_request``：路由命中则返回脚本值，未命中直接失败（防止意外请求）。"""

    def __init__(self, routes=None, *, clock=None, advance=0.0):
        self.routes = dict(routes or {})
        self.clock = clock
        self.advance = advance
        self.calls = []

    def __call__(self, method, path, *, json_body=None, params=None, stats=None, timeout=None):
        self.calls.append(
            {
                "method": method.upper(),
                "path": path,
                "params": params,
                "timeout": timeout,
            }
        )
        # 与真实 _api_request 一致：计数在发请求前自增，失败尝试也计入。
        if stats is not None:
            stats["http_requests"] = int(stats.get("http_requests", 0)) + 1
        if self.clock is not None and self.advance:
            self.clock["now"] += self.advance
        handler = self.routes.get((method.upper(), path))
        if handler is None:
            raise AssertionError(f"unexpected TALK request: {method} {path}")
        if isinstance(handler, BaseException):
            raise handler
        if callable(handler):
            return handler()
        return copy.deepcopy(handler)

    def paths(self):
        return [call["path"] for call in self.calls]

    def timeouts(self):
        return [call["timeout"] for call in self.calls]


def fake_clock(start=1000.0):
    clock = {"now": start}
    slept = []

    def monotonic():
        return clock["now"]

    def sleep(seconds):
        slept.append(seconds)
        clock["now"] += seconds

    return clock, slept, monotonic, sleep


class FakeResponse:
    """urlopen 的替身：可让 __enter__ 或 read 抛异常。"""

    def __init__(self, *, read_error=None, enter_error=None, payload=b"{}"):
        self.read_error = read_error
        self.enter_error = enter_error
        self.payload = payload

    def __enter__(self):
        if self.enter_error is not None:
            raise self.enter_error
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        if self.read_error is not None:
            raise self.read_error
        return self.payload


class ControlledWaitUnitTests(RouteTestCase):
    """不依赖真实服务的门禁 / 记账 / 归一化单测。"""

    def setUp(self):
        super().setUp()
        self.env = {
            "TALK_BASE_URL": "http://talk.test",
            "TALK_API_KEY": "fake-key",
            "TALK_PROJECT_ID": PROJECT_ID,
            "TALK_MEMBER_ID": "agent:env-should-not-be-used",
        }

    def test_controlled_wait_flag_must_be_boolean(self):
        for value in (None, False):
            self.assertFalse(talk_task_tools._normalize_controlled_wait(value))
        self.assertTrue(talk_task_tools._normalize_controlled_wait(True))
        for value in (1, 0, "true", "false", [], {}):
            with self.subTest(value=value), self.assertRaises(TalkToolError) as caught:
                talk_task_tools._normalize_controlled_wait(value)
            self.assertIn("controlled_wait", str(caught.exception))

    def test_g1_requires_project_context(self):
        env = dict(self.env, TALK_PROJECT_ID="")
        with patch.dict(os.environ, env, clear=False), self.assertRaises(TalkToolError) as caught:
            dispatch_tool("talk_wait_tasks", {"controlled_wait": True, "timeout_seconds": 30})
        self.assertIn("G1", str(caught.exception))

    def test_g2_rejects_missing_or_non_positive_or_non_numeric_timeout(self):
        api = FakeApi({})
        cases = [
            {},  # 省略 timeout_seconds
            {"timeout_seconds": None},
            {"timeout_seconds": True},
            {"timeout_seconds": "600"},
            {"timeout_seconds": 0},
            {"timeout_seconds": -5},
            {"timeout_seconds": float("nan")},
            {"timeout_seconds": float("inf")},
        ]
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", api
        ):
            for extra in cases:
                arguments = {"controlled_wait": True}
                arguments.update(extra)
                with self.subTest(arguments=extra), self.assertRaises(TalkToolError) as caught:
                    dispatch_tool("talk_wait_tasks", arguments)
                self.assertIn("timeout_seconds", str(caught.exception))
            # 直接调用（未显式传 timeout）同样拒绝，不受签名默认 600 影响。
            with self.assertRaises(TalkToolError):
                wait_tasks(controlled_wait=True, project_id=PROJECT_ID)
        self.assertEqual(api.calls, [])
        # 非受控路径的旧语义不受影响：负数归零、数字字符串可接受、缺省 600。
        self.assertEqual(talk_task_tools._normalize_wait_timeout(-5), (-5.0, 0.0))
        self.assertEqual(talk_task_tools._normalize_wait_timeout("600"), (600.0, 600.0))
        self.assertEqual(
            talk_task_tools._normalize_wait_timeout(None),
            (WAIT_DEFAULT_TIMEOUT_SECONDS, WAIT_DEFAULT_TIMEOUT_SECONDS),
        )
        self.assertEqual(
            talk_task_tools._normalize_wait_timeout(talk_task_tools.WAIT_TIMEOUT_UNSET),
            (WAIT_DEFAULT_TIMEOUT_SECONDS, WAIT_DEFAULT_TIMEOUT_SECONDS),
        )
        self.assertEqual(wait_tasks.__kwdefaults__["timeout_seconds"], 600.0)

    def test_entry_gates_reject_without_polling_tasks(self):
        stats_path = self._tmpdir / "entry.jsonl"
        cases = [
            (
                "G3-identity-api",
                {
                    ("GET", "/api/members/me"): TalkToolError("TALK API HTTP 401: 无效的 API Key"),
                },
                "G3",
                "api_error",
            ),
            (
                "G3-identity-shape",
                {("GET", "/api/members/me"): {"id": "", "kind": "agent"}},
                "G3",
                None,
            ),
            (
                "G4-human",
                {("GET", "/api/members/me"): {"id": "human:bobo", "kind": "human"}},
                "G4",
                None,
            ),
            (
                "G5-legacy-service",
                {
                    ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
                    ("GET", f"/api/projects/{PROJECT_ID}"): {"project_id": PROJECT_ID},
                },
                "G5",
                None,
            ),
            (
                "G5-project-api-error",
                {
                    ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
                    ("GET", f"/api/projects/{PROJECT_ID}"): TalkToolError(
                        "TALK API HTTP 404: 项目不存在"
                    ),
                },
                "G5",
                "api_error",
            ),
            (
                "G6-not-assigned",
                {
                    ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
                    ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(
                        controller_member_id="agent:ghost",
                        controller_assignment_status="not_in_roster",
                    ),
                },
                "G6",
                None,
            ),
            (
                "G7-passive",
                {
                    ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
                    ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(
                        controller_mode="passive"
                    ),
                },
                "G7",
                None,
            ),
            (
                "G7-not-controller",
                {
                    ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
                    ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(
                        controller_member_id="agent:other"
                    ),
                },
                "G7",
                None,
            ),
        ]
        with patch.dict(
            os.environ, dict(self.env, TALK_WAIT_STATS_FILE=str(stats_path)), clear=False
        ):
            for name, routes, gate, expected_reason in cases:
                api = FakeApi(routes)
                with self.subTest(case=name), patch.object(
                    talk_task_tools, "_api_request", api
                ), self.assertRaises(TalkToolError) as caught:
                    dispatch_tool(
                        "talk_wait_tasks",
                        {"controlled_wait": True, "timeout_seconds": 30, "task_ids": [7]},
                    )
                self.assertIn(gate, str(caught.exception), name)
                # 进入失败绝不轮询任务，也绝不放行到等待。
                self.assertNotIn("/api/tasks", "".join(api.paths()), name)
        records = [
            json.loads(line)
            for line in stats_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual([record["entry_gate"] for record in records[-len(cases):]], [case[2] for case in cases])
        self.assertEqual(
            [record["return_reason"] for record in records[-len(cases):]],
            [case[3] for case in cases],
        )
        for record in records:
            self.assertTrue(record["controlled_wait"])
            self.assertIn("entry_error", record)

    def test_entry_success_records_snapshot_and_counts_every_request(self):
        routes = {
            ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
            ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(),
            ("GET", "/api/tasks/7"): task_payload(7, "canceled"),
        }
        api = FakeApi(routes)
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", api
        ):
            result = dispatch_tool(
                "talk_wait_tasks",
                {
                    "controlled_wait": True,
                    "timeout_seconds": 60,
                    "task_ids": [7],
                    "workflow_statuses": ["canceled"],
                },
            )
        self.assertTrue(result["controlled_wait"])
        self.assertEqual(
            result["controlled_entry"],
            {
                "requested_mode": "active",
                "requested_version": 1,
                "member_id": "agent:worker",
                "assignment_version": 1,
                "status": "assigned",
            },
        )
        self.assertEqual(result["controlled_rechecks"], 0)
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["return_reason"], "matched")
        self.assertEqual(result["requested_timeout_seconds"], 60.0)
        self.assertEqual(result["timeout_seconds"], 60.0)
        self.assertEqual(LEGACY_WAIT_FIELDS | {"controlled_wait", "controlled_entry", "controlled_rechecks"}, set(result))
        # 身份 GET + 项目 GET + 任务轮询：全部计入 query_stats.http_requests。
        self.assertEqual(api.paths(), ["/api/members/me", f"/api/projects/{PROJECT_ID}", "/api/tasks/7"])
        self.assertEqual(result["query_stats"]["http_requests"], 3)
        self.assertEqual(result["query_stats"]["http_requests"], len(api.calls))
        self.assertEqual(
            set(result["query_stats"]),
            {"poll_rounds", "http_requests", "elapsed_seconds", "return_reason"},
        )

    def test_effective_timeout_is_clamped_to_600_for_controlled(self):
        routes = {
            ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
            ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(),
            ("GET", "/api/tasks/7"): task_payload(7, "canceled"),
        }
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", FakeApi(routes)
        ):
            result = dispatch_tool(
                "talk_wait_tasks",
                {
                    "controlled_wait": True,
                    "timeout_seconds": 10**9,
                    "task_ids": [7],
                    "workflow_statuses": ["canceled"],
                },
            )
        self.assertEqual(result["requested_timeout_seconds"], 1e9)
        self.assertEqual(result["timeout_seconds"], WAIT_MAX_TIMEOUT_SECONDS)

    def test_recheck_exits_mode_changed_and_controller_changed(self):
        def run(recheck_project, *, expected_reason, stats_path=None):
            state = {"project_calls": 0}

            def project_handler():
                state["project_calls"] += 1
                if state["project_calls"] == 1:
                    return project_payload()
                return recheck_project

            routes = {
                ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
                ("GET", f"/api/projects/{PROJECT_ID}"): project_handler,
                ("GET", "/api/tasks/7"): task_payload(7, "assigned"),
            }
            clock, slept, monotonic, sleep = fake_clock()
            env = self.env if stats_path is None else dict(self.env, TALK_WAIT_STATS_FILE=str(stats_path))
            with patch.dict(os.environ, env, clear=False), patch.object(
                talk_task_tools, "_api_request", FakeApi(routes, clock=clock)
            ), patch.object(talk_task_tools, "_monotonic", side_effect=monotonic), patch.object(
                talk_task_tools, "_sleep", side_effect=sleep
            ):
                result = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "controlled_wait": True,
                        "timeout_seconds": 65,
                        "task_ids": [7],
                        "workflow_statuses": ["submitted"],
                    },
                )
            self.assertEqual(result["return_reason"], expected_reason)
            self.assertFalse(result["timed_out"])
            self.assertEqual(result["controlled_rechecks"], 1)
            self.assertEqual(result["controlled_entry"]["requested_mode"], "active")
            self.assertEqual(result["controlled_entry"]["requested_version"], 1)
            # 正常退出时 tasks 是本轮轮询集合（仍是上一次成功轮询到的任务）。
            self.assertEqual([task["id"] for task in result["tasks"]], [7])
            self.assertGreaterEqual(result["elapsed_seconds"], CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS)
            self.assertLess(result["elapsed_seconds"], 65.0)
            return result, slept

        result, _ = run(project_payload(controller_mode="passive", controller_mode_version=2), expected_reason="mode_changed")
        # 版本变化（模式值不变）同样按 mode_changed 退出。
        run(project_payload(controller_mode_version=2), expected_reason="mode_changed")
        # 模式字段消失 = 旧服务/字段失效。
        run({"project_id": PROJECT_ID}, expected_reason="mode_changed")
        # 主控解除 / 更换 / 版本变化 / 指定字段消失 = controller_changed。
        run(
            project_payload(
                controller_member_id=None,
                controller_assignment_version=2,
                controller_assignment_status="unassigned",
            ),
            expected_reason="controller_changed",
        )
        run(
            project_payload(controller_member_id="agent:other", controller_assignment_version=2),
            expected_reason="controller_changed",
        )
        run(
            project_payload(controller_assignment_version=2),
            expected_reason="controller_changed",
        )
        run(
            {
                "project_id": PROJECT_ID,
                "controller_mode": "active",
                "controller_mode_version": 1,
            },
            expected_reason="controller_changed",
        )
        self.assertEqual(result["return_reason"], "mode_changed")

    def test_recheck_api_error_is_wrapped_and_recorded_exactly_once(self):
        """F-1：30 秒重读节点的项目 GET 失败与轮询失败同形——api_error + elapsed/rounds + 恰好一条统计。

        矩阵覆盖 HTTP 服务错误、请求超时，以及"先成功重读一次、第二次重读才失败"，
        并验证失败尝试只计一次、之后不再发出任何请求、不写成 matched/timeout。
        """
        cases = [
            (
                "http-500",
                TalkToolError("TALK API HTTP 500: 重读时服务不可用"),
                "HTTP 500",
                0,
            ),
            (
                "request-timeout",
                TalkToolError(
                    "TALK API 请求超时（2.5 秒）：这不是任务等待 deadline 的正常 timeout"
                ),
                "请求超时",
                0,
            ),
            (
                "second-recheck",
                TalkToolError("TALK API HTTP 503: 重读时服务暂不可用"),
                "HTTP 503",
                1,
            ),
        ]
        for name, error, expected_text, expected_rechecks in cases:
            stats_path = self._tmpdir / f"recheck-{name}.jsonl"
            state = {"project_calls": 0}

            def project_handler(error=error, state=state):
                state["project_calls"] += 1
                if state["project_calls"] == 1:
                    return project_payload()
                if name == "second-recheck" and state["project_calls"] == 2:
                    # 第一次重读成功且无变化 → 计数 1；第二次重读才失败。
                    return project_payload()
                raise error

            routes = {
                ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
                ("GET", f"/api/projects/{PROJECT_ID}"): project_handler,
                ("GET", "/api/tasks/7"): task_payload(7, "assigned"),
            }
            clock, slept, monotonic, sleep = fake_clock()
            api = FakeApi(routes, clock=clock)
            with self.subTest(case=name), patch.dict(
                os.environ,
                dict(self.env, TALK_WAIT_STATS_FILE=str(stats_path)),
                clear=False,
            ), patch.object(talk_task_tools, "_api_request", api), patch.object(
                talk_task_tools, "_monotonic", side_effect=monotonic
            ), patch.object(talk_task_tools, "_sleep", side_effect=sleep):
                with self.assertRaises(TalkToolError) as caught:
                    dispatch_tool(
                        "talk_wait_tasks",
                        {
                            "controlled_wait": True,
                            "timeout_seconds": 65,
                            "task_ids": [7],
                            "workflow_statuses": ["submitted"],
                        },
                    )
            message = str(caught.exception)
            self.assertIn("api_error", message, name)
            self.assertIn("不伪装成正常 timeout", message, name)
            # 异常形态与 #156 的任务轮询路径逐字一致（不因共用包装改变既有文案）。
            self.assertIn("已等待", message, name)
            self.assertIn("轮询", message, name)
            self.assertIn(expected_text, message, name)
            self.assertNotIn("失败节点", message, name)
            # 确实走到 30 秒重读节点（不是进入期或首个轮询失败），且失败后不再发请求。
            self.assertGreaterEqual(
                sum(slept), CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS, name
            )
            self.assertEqual(state["project_calls"], 2 + expected_rechecks, name)
            self.assertEqual(api.paths()[-1], f"/api/projects/{PROJECT_ID}", name)
            self.assertEqual(
                [call["method"] for call in api.calls], ["GET"] * len(api.calls), name
            )
            records = [
                json.loads(line)
                for line in stats_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            # 恰好一条统计记录：不因共用包装重复落盘。
            self.assertEqual(len(records), 1, name)
            record = records[0]
            self.assertEqual(record["event"], "talk_wait_tasks", name)
            self.assertEqual(record["return_reason"], "api_error", name)
            self.assertNotIn(record["return_reason"], ("matched", "timeout"), name)
            self.assertFalse(record["timed_out"], name)
            self.assertTrue(record["controlled_wait"], name)
            self.assertEqual(record["failure_stage"], "recheck", name)
            self.assertEqual(record["controlled_rechecks"], expected_rechecks, name)
            self.assertEqual(record["controlled_entry"]["requested_mode"], "active", name)
            # 实际 HTTP 尝试数：失败的重读 GET 只计一次，且 http_requests 与调用面一致。
            self.assertEqual(record["http_requests"], len(api.calls), name)
            self.assertEqual(record["poll_rounds"], len(slept) + 1, name)
            self.assertGreaterEqual(
                record["elapsed_seconds"], CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS, name
            )
            self.assertLess(record["elapsed_seconds"], 65.0, name)
            # 异常正文的 elapsed 与统计记录同源。
            self.assertIn(f"已等待 {record['elapsed_seconds']:.1f} 秒", message, name)
            self.assertNotIn("fake-key", message, name)

    def test_matched_wins_over_mode_change_in_the_same_round(self):
        project_calls = {"count": 0}

        def project_handler():
            # 进入时仍是 active；若真走到重读节点则会是 passive（本用例不应走到）。
            project_calls["count"] += 1
            if project_calls["count"] == 1:
                return project_payload()
            return project_payload(controller_mode="passive", controller_mode_version=2)

        def task_handler():
            # 重读节点所在的同一轮里任务先命中：matched 优先于 mode_changed。
            return task_payload(7, "canceled" if clock["now"] >= 1030 else "assigned")

        clock, _slept, monotonic, sleep = fake_clock()
        routes = {
            ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
            ("GET", f"/api/projects/{PROJECT_ID}"): project_handler,
            ("GET", "/api/tasks/7"): task_handler,
        }
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", FakeApi(routes, clock=clock)
        ), patch.object(talk_task_tools, "_monotonic", side_effect=monotonic), patch.object(
            talk_task_tools, "_sleep", side_effect=sleep
        ):
            result = dispatch_tool(
                "talk_wait_tasks",
                {
                    "controlled_wait": True,
                    "timeout_seconds": 65,
                    "task_ids": [7],
                    "workflow_statuses": ["canceled"],
                },
            )
        self.assertEqual(result["return_reason"], "matched")
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["controlled_rechecks"], 0)
        self.assertEqual(result["matched_task_ids"], [7])

    def test_deadline_accounting_covers_entry_and_poll_requests(self):
        # 每次 HTTP 推进 40 秒：身份 + 项目读完后预算已耗尽，未发任务轮询请求。
        clock, _slept, monotonic, sleep = fake_clock()
        routes = {
            ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
            ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(),
        }
        api = FakeApi(routes, clock=clock, advance=40.0)
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", api
        ), patch.object(talk_task_tools, "_monotonic", side_effect=monotonic), patch.object(
            talk_task_tools, "_sleep", side_effect=sleep
        ):
            result = dispatch_tool(
                "talk_wait_tasks",
                {"controlled_wait": True, "timeout_seconds": 60, "task_ids": [7]},
            )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["return_reason"], "timeout")
        # R5：从未完成任何任务轮询 → tasks=[] / task_count=0，且不再发请求。
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["task_count"], 0)
        self.assertEqual(result["tasks_returned"], 0)
        self.assertEqual(api.paths(), ["/api/members/me", f"/api/projects/{PROJECT_ID}"])
        self.assertEqual(result["query_stats"]["http_requests"], 2)
        self.assertEqual(result["controlled_rechecks"], 0)

    def test_budget_exhaustion_returns_last_successful_poll_set(self):
        routes = {
            ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
            ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(),
            ("GET", "/api/tasks/7"): task_payload(7, "assigned"),
        }
        clock, slept, monotonic, sleep = fake_clock()
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", FakeApi(routes, clock=clock)
        ), patch.object(talk_task_tools, "_monotonic", side_effect=monotonic), patch.object(
            talk_task_tools, "_sleep", side_effect=sleep
        ):
            result = dispatch_tool(
                "talk_wait_tasks",
                {"controlled_wait": True, "timeout_seconds": 10, "task_ids": [7]},
            )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["return_reason"], "timeout")
        self.assertGreater(len(result["tasks"]), 0)
        self.assertEqual([task["id"] for task in result["tasks"]], [7])
        self.assertEqual(result["task_count"], len(result["tasks"]))
        self.assertAlmostEqual(sum(slept), 10.0, places=6)
        self.assertLessEqual(max(slept), 5.0)
        self.assertEqual(result["elapsed_seconds"], 10.0)
        # 身份 + 项目 + 每一次真正发出的任务轮询；最后一轮在发请求前就因预算耗尽退出。
        self.assertEqual(result["query_stats"]["poll_rounds"], 6)
        self.assertEqual(result["query_stats"]["http_requests"], 7)
        self.assertEqual(
            result["query_stats"]["http_requests"],
            2 + result["query_stats"]["poll_rounds"] - 1,
        )

    def test_entry_budget_exhausted_before_identity_get(self):
        calls = {"count": 0}

        def monotonic():
            calls["count"] += 1
            return 1000.0 if calls["count"] == 1 else 1005.0

        api = FakeApi({})
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", api
        ), patch.object(talk_task_tools, "_monotonic", side_effect=monotonic):
            with self.assertRaises(TalkToolError) as caught:
                dispatch_tool(
                    "talk_wait_tasks",
                    {"controlled_wait": True, "timeout_seconds": 1, "task_ids": [7]},
                )
        self.assertIn("G3", str(caught.exception))
        self.assertIn("预算", str(caught.exception))
        self.assertEqual(api.calls, [])

    def test_per_request_timeout_is_clamped_by_remaining_budget(self):
        # 默认参数保持 10 秒（旧 helper 行为不变）。
        self.assertEqual(
            inspect.signature(talk_task_tools._api_request).parameters["timeout"].default,
            WAIT_REQUEST_TIMEOUT_SECONDS,
        )
        # 正常剩余预算：单次请求 10 秒。
        routes = {
            ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
            ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(),
            ("GET", "/api/tasks/7"): task_payload(7, "canceled"),
        }
        api = FakeApi(routes)
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", api
        ):
            dispatch_tool(
                "talk_wait_tasks",
                {
                    "controlled_wait": True,
                    "timeout_seconds": 600,
                    "task_ids": [7],
                    "workflow_statuses": ["canceled"],
                },
            )
        self.assertEqual(api.timeouts(), [10.0, 10.0, 10.0])

        # 剩余预算不足 10 秒：单次请求超时取 min(10, remaining)。
        clock, _slept, monotonic, sleep = fake_clock()
        api = FakeApi(
            {
                ("GET", "/api/members/me"): MEMBERS_ME_AGENT,
                ("GET", f"/api/projects/{PROJECT_ID}"): project_payload(),
            },
            clock=clock,
            advance=55.0,
        )
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", api
        ), patch.object(talk_task_tools, "_monotonic", side_effect=monotonic), patch.object(
            talk_task_tools, "_sleep", side_effect=sleep
        ):
            result = dispatch_tool(
                "talk_wait_tasks",
                {"controlled_wait": True, "timeout_seconds": 60, "task_ids": [7]},
            )
        self.assertEqual(api.timeouts(), [10.0, 5.0])
        self.assertTrue(result["timed_out"])

    def test_legacy_path_does_not_pass_request_timeout_or_new_fields(self):
        routes = {
            ("GET", "/api/tasks/7"): task_payload(7, "canceled"),
        }
        api = FakeApi(routes)
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", api
        ):
            result = dispatch_tool(
                "talk_wait_tasks",
                {"task_ids": [7], "workflow_statuses": ["canceled"], "timeout_seconds": 0},
            )
        # 旧路径不传 timeout → 走 _api_request 自己的 10 秒默认值（未被 clamp 改写）。
        self.assertEqual(api.timeouts(), [None])
        self.assertEqual(api.paths(), ["/api/tasks/7"])
        self.assertEqual(set(result), LEGACY_WAIT_FIELDS)
        self.assertEqual(
            set(result["query_stats"]),
            {"poll_rounds", "http_requests", "elapsed_seconds", "return_reason"},
        )


class HttpErrorNormalizationTests(unittest.TestCase):
    """R1：连接 / getresponse / read 阶段的裸超时与网络 OSError 归一。"""

    def setUp(self):
        super().setUp()
        self.env = {
            "TALK_BASE_URL": "http://talk.test",
            "TALK_API_KEY": "secret-key",
            "TALK_PROJECT_ID": PROJECT_ID,
        }

    def _request(self, fake_urlopen, *, stats=None, timeout=WAIT_REQUEST_TIMEOUT_SECONDS):
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "urlopen", fake_urlopen
        ):
            return talk_task_tools._api_request(
                "GET", "/api/members/me", stats=stats, timeout=timeout
            )

    def test_bare_timeouts_are_normalized_and_classified(self):
        for label, error in (
            ("connect-timeout", TimeoutError("timed out")),
            ("urlerror-timeout", URLError(TimeoutError("timed out"))),
        ):
            with self.subTest(case=label), self.assertRaises(TalkToolError) as caught:
                self._request(lambda request, timeout: (_ for _ in ()).throw(error))
            message = str(caught.exception)
            self.assertIn("请求超时", message)
            self.assertIn("不是任务等待 deadline 的正常 timeout", message)
            self.assertNotIn("secret-key", message)

        for label, error in (
            ("connection-refused", URLError(ConnectionRefusedError(10061, "拒绝连接"))),
            ("bare-oserror", ConnectionResetError(10054, "连接被重置")),
        ):
            with self.subTest(case=label), self.assertRaises(TalkToolError) as caught:
                self._request(lambda request, timeout: (_ for _ in ()).throw(error))
            message = str(caught.exception)
            self.assertIn("无法连接 TALK API", message)
            self.assertNotIn("请求超时", message)
            self.assertNotIn("secret-key", message)

    def test_getresponse_and_read_stage_timeouts_are_normalized(self):
        cases = [
            ("getresponse", FakeResponse(enter_error=TimeoutError("read timeout"))),
            ("read", FakeResponse(read_error=TimeoutError("read timeout"))),
            ("read-oserror", FakeResponse(read_error=ConnectionResetError(10054, "重置"))),
        ]
        for label, response in cases:
            with self.subTest(case=label), self.assertRaises(TalkToolError) as caught:
                self._request(lambda request, timeout, response=response: response)
            message = str(caught.exception)
            if label == "read-oserror":
                self.assertIn("无法连接 TALK API", message)
            else:
                self.assertIn("请求超时", message)

    def test_http_error_keeps_status_and_counts_failed_attempt(self):
        stats = {"http_requests": 0}

        def failing(request, timeout):
            raise HTTPError(
                request.full_url,
                403,
                "Forbidden",
                {},
                io.BytesIO(json.dumps({"detail": "forbidden"}).encode("utf-8")),
            )

        with self.assertRaises(TalkToolError) as caught:
            with patch.dict(os.environ, self.env, clear=False), patch.object(
                talk_task_tools, "urlopen", failing
            ):
                talk_task_tools._api_request("GET", "/api/members/me", stats=stats)
        self.assertIn("TALK API HTTP 403", str(caught.exception))
        self.assertEqual(stats["http_requests"], 1)

    def test_controlled_entry_and_poll_timeouts_never_escape_as_bare_errors(self):
        # 进入期身份 GET 超时 → 进入错误（G3），不是裸 TimeoutError。
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools,
            "urlopen",
            lambda request, timeout: (_ for _ in ()).throw(TimeoutError("timed out")),
        ):
            with self.assertRaises(TalkToolError) as caught:
                dispatch_tool(
                    "talk_wait_tasks",
                    {"controlled_wait": True, "timeout_seconds": 30, "task_ids": [7]},
                )
        self.assertIn("G3", str(caught.exception))
        self.assertIn("请求超时", str(caught.exception))

        # 门禁通过后的任务轮询 read 阶段超时 → api_error 抛错，不伪装成 timeout。
        stats_path = Path(self._tmpdir()) / "http-poll-timeout.jsonl"
        calls = {"count": 0}

        def read_timeout_on_poll(request, timeout):
            calls["count"] += 1
            if calls["count"] <= 2:  # members/me + project
                payload = json.dumps(
                    MEMBERS_ME_AGENT if calls["count"] == 1 else project_payload()
                ).encode("utf-8")
                return FakeResponse(payload=payload)
            return FakeResponse(read_error=TimeoutError("read timeout"))

        with patch.dict(
            os.environ,
            dict(self.env, TALK_WAIT_STATS_FILE=str(stats_path)),
            clear=False,
        ), patch.object(talk_task_tools, "urlopen", read_timeout_on_poll):
            with self.assertRaises(TalkToolError) as caught:
                dispatch_tool(
                    "talk_wait_tasks",
                    {"controlled_wait": True, "timeout_seconds": 30, "task_ids": [7]},
                )
        message = str(caught.exception)
        self.assertIn("api_error", message)
        self.assertIn("不伪装成正常 timeout", message)
        self.assertIn("已等待", message)
        records = [
            json.loads(line)
            for line in stats_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(records[-1]["return_reason"], "api_error")
        self.assertFalse(records[-1]["timed_out"])
        self.assertTrue(records[-1]["controlled_wait"])

        # 旧通用路径保持 api_error 分类与“这不是超时”的既有文案。
        api = FakeApi({("GET", "/api/tasks/7"): TalkToolError("TALK API 请求超时（10 秒）")})
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            talk_task_tools, "_api_request", api
        ):
            with self.assertRaises(TalkToolError) as legacy:
                dispatch_tool(
                    "talk_wait_tasks",
                    {"task_ids": [7], "timeout_seconds": 5, "workflow_statuses": ["submitted"]},
                )
        self.assertIn("不是超时", str(legacy.exception))

    def test_controlled_recheck_error_counts_the_failed_get_once(self):
        """F-1：真实 ``_api_request`` + 假 urlopen 在 30 秒重读节点注入 500 / 读阶段超时。

        证明真实计数路径上失败的重读 GET 只让 ``http_requests`` +1，且恰好落一条 api_error 统计。
        """
        cases = [
            ("http-500", "http", "TALK API HTTP 500"),
            ("read-timeout", "timeout", "请求超时"),
        ]
        for name, mode, expected in cases:
            stats_path = Path(self._tmpdir()) / f"real-recheck-{name}.jsonl"
            calls = {"attempts": 0, "project": 0}

            def urlopen_fake(request, timeout, mode=mode, calls=calls):
                calls["attempts"] += 1
                url = request.full_url
                if url.endswith("/api/members/me"):
                    return FakeResponse(payload=json.dumps(MEMBERS_ME_AGENT).encode("utf-8"))
                if "/api/projects/" in url:
                    calls["project"] += 1
                    if calls["project"] == 1:
                        return FakeResponse(
                            payload=json.dumps(project_payload()).encode("utf-8")
                        )
                    if mode == "timeout":
                        return FakeResponse(read_error=TimeoutError("read timeout"))
                    raise HTTPError(
                        url,
                        500,
                        "Internal Server Error",
                        {},
                        io.BytesIO(
                            json.dumps({"detail": "重读时服务不可用"}).encode("utf-8")
                        ),
                    )
                if url.endswith("/api/tasks/7"):
                    return FakeResponse(
                        payload=json.dumps(task_payload(7, "assigned")).encode("utf-8")
                    )
                raise AssertionError(f"unexpected TALK request: {url}")

            clock, slept, monotonic, sleep = fake_clock()
            with self.subTest(case=name), patch.dict(
                os.environ,
                dict(self.env, TALK_WAIT_STATS_FILE=str(stats_path)),
                clear=False,
            ), patch.object(talk_task_tools, "urlopen", urlopen_fake), patch.object(
                talk_task_tools, "_monotonic", side_effect=monotonic
            ), patch.object(talk_task_tools, "_sleep", side_effect=sleep):
                with self.assertRaises(TalkToolError) as caught:
                    dispatch_tool(
                        "talk_wait_tasks",
                        {
                            "controlled_wait": True,
                            "timeout_seconds": 65,
                            "task_ids": [7],
                            "workflow_statuses": ["submitted"],
                        },
                    )
            message = str(caught.exception)
            self.assertIn(expected, message, name)
            self.assertIn("已等待", message, name)
            self.assertIn("轮询", message, name)
            self.assertEqual(calls["project"], 2, name)
            records = [
                json.loads(line)
                for line in stats_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(records), 1, name)
            record = records[0]
            self.assertEqual(record["return_reason"], "api_error", name)
            self.assertEqual(record["failure_stage"], "recheck", name)
            self.assertFalse(record["timed_out"], name)
            # members/me + 进入期项目 GET + poll_rounds 次任务轮询 + 1 次失败重读 = poll_rounds + 3。
            self.assertEqual(calls["attempts"], record["http_requests"], name)
            self.assertEqual(calls["attempts"], record["poll_rounds"] + 3, name)
            self.assertNotIn("secret-key", message, name)
            self.assertNotIn("secret-key", json.dumps(record, ensure_ascii=False), name)

    @staticmethod
    def _tmpdir() -> str:
        import tempfile

        return tempfile.mkdtemp(prefix="ctrl-wait-http-")


class ToolSurfaceTests(unittest.TestCase):
    """schema / 描述 / --check 说明与九工具集合。"""

    def test_tool_schema_surface_is_unchanged_and_documents_controlled_wait(self):
        self.assertEqual(len(TOOL_SCHEMAS), 9)
        self.assertEqual(tuple(tool["name"] for tool in TOOL_SCHEMAS), TOOL_NAMES)
        schema = next(tool for tool in TOOL_SCHEMAS if tool["name"] == "talk_wait_tasks")
        properties = schema["inputSchema"]["properties"]
        self.assertEqual(properties["controlled_wait"]["type"], "boolean")
        self.assertFalse(properties["controlled_wait"]["default"])
        self.assertEqual(properties["timeout_seconds"]["maximum"], 600)
        self.assertEqual(properties["timeout_seconds"]["default"], 600)
        description = schema["description"]
        for fragment in (
            "controlled_wait",
            "opt-in",
            "G1–G7",
            "30 秒",
            "mode_changed",
            "controller_changed",
            "advisory",
            "min(10 秒",
            "query_stats.http_requests",
            "controlled_entry",
            "controlled_rechecks",
            "排队",
            "取消",
            "600",
            "660",
            "omitted_task_ids",
            "不保证宿主外层零回合",
            "不保证带走 MCP 子进程",
            "不改变任务状态",
            "程序内部不调用模型",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, description)
        self.assertIn(f"预留 {WAIT_CLIENT_MARGIN_SECONDS:.0f} 秒", description)
        self.assertIn(str(talk_task_tools.WAIT_MAX_TASK_REFERENCES), description)

        list_schema = next(tool for tool in TOOL_SCHEMAS if tool["name"] == "talk_list_agents")
        self.assertIn("caller_identity", list_schema["description"])
        self.assertIn("/api/members/me", list_schema["description"])
        self.assertIn("不阻断", list_schema["description"])

        note = talk_task_tools.WAIT_COUNTING_NOTE
        self.assertIn("http_requests", note)
        self.assertIn("重读", note)
        self.assertIn("主控", note)

    def test_terminal_check_reports_controlled_wait_boundaries(self):
        defaults = terminal.wait_defaults()
        self.assertEqual(defaults["default_timeout_seconds"], 600.0)
        self.assertEqual(defaults["max_timeout_seconds"], 600.0)
        self.assertGreaterEqual(defaults["recommended_client_tool_timeout_seconds"], 660.0)
        self.assertIn("660", defaults["note"])
        controlled = defaults["controlled_wait"]
        self.assertEqual(controlled["parameter"], "controlled_wait")
        self.assertFalse(controlled["default"])
        self.assertTrue(controlled["opt_in"])
        self.assertEqual(controlled["entry_gates"], ["G1", "G2", "G3", "G4", "G5", "G6", "G7"])
        self.assertEqual(controlled["recheck_interval_seconds"], CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS)
        self.assertEqual(controlled["client_margin_seconds"], WAIT_CLIENT_MARGIN_SECONDS)
        self.assertEqual(controlled["per_request_timeout_seconds"], WAIT_REQUEST_TIMEOUT_SECONDS)
        self.assertIn("advisory", controlled["note"])
        self.assertIn("30", controlled["note"])
        self.assertIn("取消", defaults["cancellation_note"])


class ControlledWaitLiveTests(RouteTestCase):
    """真实隔离服务：旧路径零新增请求、门禁实际生效、caller_identity 三键。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")
        self.add_member("agent:worker", api_key="worker-key", display_name="Worker")
        self.add_member("agent:other", api_key="other-key", display_name="Other")
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": PROJECT_ID, "display_name": "Controlled"},
            ).raise_for_status()
            client.post(
                f"/api/projects/{PROJECT_ID}/sync",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "agents": [
                        {"member_id": "agent:worker", "business_role": "dev"},
                        {"member_id": "agent:other"},
                    ]
                },
            ).raise_for_status()

    def environment(self, base_url, *, key="worker-key", member="agent:worker"):
        return {
            "TALK_BASE_URL": base_url,
            "TALK_API_KEY": key,
            "TALK_MEMBER_ID": member,
            "TALK_PROJECT_ID": PROJECT_ID,
        }

    def set_mode(self, mode, expected_version, *, project_id=PROJECT_ID):
        with self.make_client() as client:
            response = client.patch(
                f"/api/projects/{project_id}/controller-mode",
                headers={"X-API-Key": "bobo-key"},
                json={"mode": mode, "expected_version": expected_version},
            )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def set_controller(self, member_id, expected_version, *, project_id=PROJECT_ID):
        with self.make_client() as client:
            response = client.patch(
                f"/api/projects/{project_id}/controller-assignment",
                headers={"X-API-Key": "bobo-key"},
                json={"member_id": member_id, "expected_version": expected_version},
            )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def enable_active_controller(self):
        self.set_controller("agent:worker", 0)
        self.set_mode("active", 0)

    def create_task(self, base_url, *, content="受控等待任务", key="bobo-key"):
        with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
            response = client.post(
                "/api/tasks",
                headers={"X-API-Key": key},
                json={
                    "target_member_id": "agent:worker",
                    "content": content,
                    "project_id": PROJECT_ID,
                },
            )
            response.raise_for_status()
            return response.json()

    def cancel_task(self, base_url, task_id, *, key="bobo-key"):
        with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
            response = client.post(
                f"/api/tasks/{task_id}/cancel",
                headers={"X-API-Key": key},
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def record_requests(recorder):
        real_request = talk_task_tools._api_request

        def wrapper(method, path, **kwargs):
            recorder.append((method.upper(), path, kwargs.get("timeout")))
            return real_request(method, path, **kwargs)

        return wrapper

    def test_legacy_path_stays_byte_compatible_without_new_requests(self):
        with LiveTalkServer(main.app) as base_url:
            task = self.create_task(base_url)
            self.cancel_task(base_url, task["id"])
            legacy = self.environment(base_url, key="bobo-key", member="human:bobo")
            with patch.dict(os.environ, legacy, clear=False):
                calls = []
                with patch.object(
                    talk_task_tools, "_api_request", self.record_requests(calls)
                ):
                    default_result = dispatch_tool(
                        "talk_wait_tasks",
                        {"task_ids": [task["id"]], "workflow_statuses": ["canceled"]},
                    )
                    explicit_false = dispatch_tool(
                        "talk_wait_tasks",
                        {
                            "task_ids": [task["id"]],
                            "workflow_statuses": ["canceled"],
                            "timeout_seconds": 0,
                            "controlled_wait": False,
                        },
                    )
                    project_scope = dispatch_tool(
                        "talk_wait_tasks",
                        {"workflow_statuses": ["submitted"], "timeout_seconds": 0},
                    )
        for result in (default_result, explicit_false, project_scope):
            self.assertEqual(set(result), LEGACY_WAIT_FIELDS)
            self.assertEqual(
                set(result["query_stats"]),
                {"poll_rounds", "http_requests", "elapsed_seconds", "return_reason"},
            )
            self.assertNotIn("controlled_wait", result)
        self.assertEqual(default_result["return_reason"], "matched")
        self.assertEqual(project_scope["return_reason"], "timeout")
        paths = [path for _method, path, _timeout in calls]
        # 非受控路径既不发身份 GET，也不重读项目；只轮询任务。
        self.assertNotIn("/api/members/me", paths)
        self.assertNotIn(f"/api/projects/{PROJECT_ID}", paths)
        self.assertEqual(paths.count(f"/api/tasks/{task['id']}"), 2)
        self.assertIn("/api/tasks", paths)
        self.assertTrue(all(timeout is None for _m, _p, timeout in calls))

    def test_controlled_entry_passes_on_real_project_and_returns_snapshot(self):
        self.enable_active_controller()
        with LiveTalkServer(main.app) as base_url:
            task = self.create_task(base_url)
            self.cancel_task(base_url, task["id"])
            env = self.environment(base_url)
            with patch.dict(os.environ, env, clear=False):
                calls = []
                with patch.object(
                    talk_task_tools, "_api_request", self.record_requests(calls)
                ):
                    result = dispatch_tool(
                        "talk_wait_tasks",
                        {
                            "controlled_wait": True,
                            "timeout_seconds": 60,
                            "task_ids": [task["id"]],
                            "workflow_statuses": ["canceled"],
                        },
                    )
        self.assertTrue(result["controlled_wait"])
        self.assertEqual(result["return_reason"], "matched")
        self.assertEqual(result["matched_task_ids"], [task["id"]])
        self.assertEqual(
            result["controlled_entry"],
            {
                "requested_mode": "active",
                "requested_version": 1,
                "member_id": "agent:worker",
                "assignment_version": 1,
                "status": "assigned",
            },
        )
        self.assertEqual(result["controlled_rechecks"], 0)
        self.assertEqual(result["timeout_seconds"], 60.0)
        self.assertEqual([path for _m, path, _t in calls], ["/api/members/me", f"/api/projects/{PROJECT_ID}", f"/api/tasks/{task['id']}"])
        self.assertEqual(result["query_stats"]["http_requests"], 3)
        # 等待只读：任务状态不被改动，也不产生收取（直接读隔离库，避免服务器关闭后再发 HTTP）。
        with self.session() as session:
            row = session.get(AgentTask, task["id"])
        self.assertEqual(row.workflow_status, "canceled")
        self.assertIsNone(row.result_collected_at)

    def test_controlled_entry_gates_reject_real_credentials(self):
        # human 凭据（G4）：故意继承一个伪造的 TALK_MEMBER_ID，证明门禁不复用环境身份
        self.enable_active_controller()
        with LiveTalkServer(main.app) as base_url:
            task = self.create_task(base_url)
            with patch.dict(
                os.environ,
                self.environment(base_url, key="bobo-key", member="agent:env-forged"),
                clear=False,
            ):
                with self.assertRaises(TalkToolError) as human:
                    dispatch_tool(
                        "talk_wait_tasks",
                        {"controlled_wait": True, "timeout_seconds": 30, "task_ids": [task["id"]]},
                    )
            self.assertIn("G4", str(human.exception))
            self.assertIn("human:bobo", str(human.exception))
            self.assertNotIn("agent:env-forged", str(human.exception))

            # 身份可核验但不是当前指定主控（G7）
            with patch.dict(os.environ, self.environment(base_url, key="other-key", member="agent:other"), clear=False):
                with self.assertRaises(TalkToolError) as mismatch:
                    dispatch_tool(
                        "talk_wait_tasks",
                        {"controlled_wait": True, "timeout_seconds": 30, "task_ids": [task["id"]]},
                    )
            self.assertIn("G7", str(mismatch.exception))

        # 模式被动（G7）
        self.set_mode("passive", 1)
        with LiveTalkServer(main.app) as base_url:
            task = self.create_task(base_url)
            with patch.dict(os.environ, self.environment(base_url), clear=False):
                with self.assertRaises(TalkToolError) as passive:
                    dispatch_tool(
                        "talk_wait_tasks",
                        {"controlled_wait": True, "timeout_seconds": 30, "task_ids": [task["id"]]},
                    )
            self.assertIn("G7", str(passive.exception))
            self.assertIn("passive", str(passive.exception))

        # status != assigned（G6）：把 worker 移出名册，指定保留；模式恢复 active 以隔离原因
        self.set_mode("active", 2)
        with LiveTalkServer(main.app) as base_url:
            with self.make_client() as client:
                client.post(
                    f"/api/projects/{PROJECT_ID}/sync",
                    headers={"X-API-Key": "bobo-key"},
                    json={"agents": [{"member_id": "agent:other"}]},
                ).raise_for_status()
            task = self.create_task(base_url)
            with patch.dict(os.environ, self.environment(base_url), clear=False):
                with self.assertRaises(TalkToolError) as roster:
                    dispatch_tool(
                        "talk_wait_tasks",
                        {"controlled_wait": True, "timeout_seconds": 30, "task_ids": [task["id"]]},
                    )
            self.assertIn("G6", str(roster.exception))
            self.assertIn("not_in_roster", str(roster.exception))

    def test_controlled_entry_rejects_old_service_without_controller_fields(self):
        self.enable_active_controller()
        real_request = talk_task_tools._api_request

        def legacy_request(method, path, **kwargs):
            payload = real_request(method, path, **kwargs)
            if path == f"/api/projects/{PROJECT_ID}" and isinstance(payload, dict):
                payload = {
                    key: value
                    for key, value in payload.items()
                    if key
                    not in {
                        "controller_mode",
                        "controller_mode_version",
                        "controller_member_id",
                        "controller_assignment_version",
                        "controller_assignment_status",
                    }
                }
            return payload

        with LiveTalkServer(main.app) as base_url:
            task = self.create_task(base_url)
            with patch.dict(os.environ, self.environment(base_url), clear=False):
                with patch.object(talk_task_tools, "_api_request", legacy_request):
                    with self.assertRaises(TalkToolError) as caught:
                        dispatch_tool(
                            "talk_wait_tasks",
                            {
                                "controlled_wait": True,
                                "timeout_seconds": 30,
                                "task_ids": [task["id"]],
                            },
                        )
        self.assertIn("G5", str(caught.exception))
        self.assertIn("不支持受控等待", str(caught.exception))

    def test_caller_identity_reports_three_keys_and_never_blocks_agents_list(self):
        with LiveTalkServer(main.app) as base_url:
            with patch.dict(os.environ, self.environment(base_url), clear=False):
                agent_view = dispatch_tool("talk_list_agents", {})
            with patch.dict(
                os.environ,
                self.environment(base_url, key="bobo-key", member="agent:env-forged"),
                clear=False,
            ):
                human_view = dispatch_tool("talk_list_agents", {})

        self.assertEqual(
            agent_view["caller_identity"],
            {"member_id": "agent:worker", "kind": "agent", "note": None},
        )
        # 继承的 TALK_MEMBER_ID 不参与身份披露：仍以 API Key 反查结果为准。
        self.assertEqual(
            human_view["caller_identity"],
            {"member_id": "human:bobo", "kind": "human", "note": None},
        )
        # 身份披露不改变原有清单，也不放纵输出：caller_identity 带来的增量必须保持有界。
        self.assertEqual(
            sorted(agent["member_id"] for agent in agent_view["agents"]),
            ["agent:other", "agent:worker"],
        )
        without_identity = dict(agent_view)
        without_identity.pop("caller_identity")
        delta = len(json.dumps(agent_view, ensure_ascii=False)) - len(
            json.dumps(without_identity, ensure_ascii=False)
        )
        self.assertGreater(delta, 0)
        self.assertLess(delta, 160)

    def test_caller_identity_failure_and_non_project_path(self):
        real_request = talk_task_tools._api_request

        def failing_identity(method, path, **kwargs):
            if path == "/api/members/me":
                raise TalkToolError("TALK API HTTP 500: 身份服务不可用")
            return real_request(method, path, **kwargs)

        def broken_shape(method, path, **kwargs):
            if path == "/api/members/me":
                return {"id": "", "kind": "agent"}
            return real_request(method, path, **kwargs)

        with LiveTalkServer(main.app) as base_url:
            with patch.dict(os.environ, self.environment(base_url), clear=False):
                with patch.object(talk_task_tools, "_api_request", failing_identity):
                    failed = dispatch_tool("talk_list_agents", {})
                with patch.object(talk_task_tools, "_api_request", broken_shape):
                    invalid = dispatch_tool("talk_list_agents", {})
            # 非项目路径：caller_identity 为 null，且不额外请求身份。
            non_project = dict(self.environment(base_url), TALK_PROJECT_ID="")
            with patch.dict(os.environ, non_project, clear=False):
                calls = []
                with patch.object(
                    talk_task_tools, "_api_request", self.record_requests(calls)
                ):
                    plain = dispatch_tool("talk_list_agents", {})
        self.assertIsNone(failed["caller_identity"]["member_id"])
        self.assertIsNone(failed["caller_identity"]["kind"])
        self.assertIn("身份核验失败", failed["caller_identity"]["note"])
        self.assertNotIn("500", failed["caller_identity"]["note"])
        self.assertEqual(sorted(failed["caller_identity"]), ["kind", "member_id", "note"])
        # 身份失败不阻断角色清单。
        self.assertEqual(
            sorted(agent["member_id"] for agent in failed["agents"]),
            ["agent:other", "agent:worker"],
        )

        self.assertIsNone(invalid["caller_identity"]["member_id"])
        self.assertIsNone(invalid["caller_identity"]["kind"])
        self.assertIn("合法", invalid["caller_identity"]["note"])

        self.assertIsNone(plain["caller_identity"])
        self.assertNotIn("/api/members/me", [path for _m, path, _t in calls])

    def test_controlled_wait_does_not_touch_tasks_or_messages(self):
        self.enable_active_controller()
        with LiveTalkServer(main.app) as base_url:
            task = self.create_task(base_url)
            env = self.environment(base_url)
            messages_before = self._message_count()
            with patch.dict(os.environ, env, clear=False):
                result = dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "controlled_wait": True,
                        "timeout_seconds": 1,
                        "task_ids": [task["id"]],
                        "workflow_statuses": ["submitted"],
                    },
                )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["return_reason"], "timeout")
        self.assertEqual(result["tasks"][0]["workflow_status"], "assigned")
        with self.session() as session:
            row = session.get(AgentTask, task["id"])
        self.assertEqual(row.workflow_status, "assigned")
        self.assertIsNone(row.result_collected_at)
        self.assertEqual(self._message_count(), messages_before)

    def _message_count(self) -> int:
        with self.session() as session:
            return len(session.exec(select(Message)).all())

    def test_task_rows_are_untouched_by_controlled_wait(self):
        self.enable_active_controller()
        with LiveTalkServer(main.app) as base_url:
            task = self.create_task(base_url)
            with patch.dict(os.environ, self.environment(base_url), clear=False):
                dispatch_tool(
                    "talk_wait_tasks",
                    {
                        "controlled_wait": True,
                        "timeout_seconds": 1,
                        "task_ids": [task["id"]],
                        "workflow_statuses": ["submitted"],
                    },
                )
        with self.session() as session:
            row = session.get(AgentTask, task["id"])
            project = session.get(Project, PROJECT_ID)
        self.assertEqual(row.workflow_status, "assigned")
        self.assertEqual(row.status, "queued")
        self.assertIsNone(row.result_collected_at)
        # 受控等待从不写入项目模式/主控。
        self.assertEqual(project.controller_mode, "active")
        self.assertEqual(project.controller_member_id, "agent:worker")


if __name__ == "__main__":
    unittest.main()
