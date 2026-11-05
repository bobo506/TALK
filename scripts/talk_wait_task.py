#!/usr/bin/env python3
"""等待 TALK 任务进入终态的程序轮询小工具（不调用模型）。

用途：在支持“后台任务完成通知”的终端（当前为 DSH）里由后台 job 运行。
任务进入终态或需要人工动作时本进程退出并触发终端通知；仅终态可进入取件、核验。
等待期间不产生任何模型调用。

边界：
- 只读 ``GET /api/tasks/{id}``，不领取、不完成、不取消、不写任务；
- 身份只来自显式 ``--key-file``、环境变量 ``TALK_API_KEY`` 或
  ``TALK_WAIT_KEY_FILE``；Key 不写命令行、不打印、不落日志；
- 默认每 15 秒查一次、单次 job 最长 1 小时；到时退出不是任务失败，而是**检查点**：发起者应核对任务与执行进程的实际活动，有活动则重启 job 继续等，无活动则停止并请示；到点或出错都输出单行可读结果。

退出码：0=任务已进入终态（任务本身成功与否看输出）；1=等待超时；
2=等待错误（Key/任务不可读等）；3=需要人工动作；64=用法错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib import error, request

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_INTERVAL = 15.0
DEFAULT_TIMEOUT = 3600.0
DEFAULT_REQUEST_TIMEOUT = 10.0
MIN_INTERVAL = 5.0

TERMINAL_STATUS = frozenset(("succeeded", "failed", "canceled"))
TERMINAL_WORKFLOW = frozenset(("submitted", "completed", "failed", "canceled"))
KEY_ENV_NAMES = ("TALK_API_KEY", "TALK_WAIT_KEY_FILE")


class WaitError(RuntimeError):
    """等待过程的可预期错误；消息不含 Key。"""

    def __init__(self, message: str, *, code: str = "wait_error") -> None:
        super().__init__(message)
        self.code = code


class WaitTimeout(WaitError):
    """等待到达总时长上限。"""

    def __init__(self, *, task_id: int, elapsed: float, last: dict | None) -> None:
        super().__init__(f"任务 {task_id} 在 {int(elapsed)} 秒内未进入终态", code="timeout")
        self.task_id = task_id
        self.elapsed = elapsed
        self.last = last


def is_terminal(task: dict) -> bool:
    """任务处于任一终态即为可停止等待。"""

    return (
        str(task.get("status") or "") in TERMINAL_STATUS
        or str(task.get("workflow_status") or "") in TERMINAL_WORKFLOW
    )


def attention_reason(task: dict) -> str | None:
    """返回需要发起者处理的原因；此状态不是交付终态。"""
    return {"clarification_requested": "clarification", "needs_decision": "decision"}.get(
        task.get("workflow_status")
    )


def wait_for_task(
    task_id: int,
    fetch,
    *,
    interval: float = DEFAULT_INTERVAL,
    timeout: float = DEFAULT_TIMEOUT,
    clock=time.monotonic,
    sleep=time.sleep,
) -> tuple[dict, float]:
    """轮询直到终态或需要人工动作；返回 ``(task, elapsed_seconds)``，超时抛 ``WaitTimeout``。

    ``fetch`` 接受 task_id 并返回任务字典；可预期的致命错误抛 ``WaitError``，
    其它 ``OSError`` 视为瞬时网络错误继续重试直到总时长上限。
    """

    if interval < MIN_INTERVAL:
        raise WaitError(f"轮询间隔不得小于 {int(MIN_INTERVAL)} 秒", code="invalid_interval")
    started = clock()
    last: dict | None = None
    while True:
        try:
            task = fetch(task_id)
        except WaitError:
            raise
        except OSError:
            task = None
        if isinstance(task, dict):
            last = task
            if is_terminal(task):
                return task, clock() - started
            if attention_reason(task):
                return task, clock() - started
        elapsed = clock() - started
        if elapsed >= timeout:
            raise WaitTimeout(task_id=task_id, elapsed=elapsed, last=last)
        sleep(interval)


def fetch_task(
    base_url: str,
    key: str,
    task_id: int,
    *,
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """只读任务；401/403/404 视为不可恢复错误，其余错误交给重试。"""

    url = f"{base_url.rstrip('/')}/api/tasks/{int(task_id)}"
    req = request.Request(url, headers={"X-API-Key": key}, method="GET")
    try:
        with request.urlopen(req, timeout=request_timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise WaitError(
                f"HTTP {exc.code}：任务不存在或当前 Key 无权读取", code="task_unavailable"
            ) from None
        raise OSError(f"HTTP {exc.code}") from None
    except error.URLError as exc:
        raise OSError(str(exc.reason)) from None
    except (ValueError, UnicodeDecodeError) as exc:
        raise OSError(f"响应不是合法 JSON: {exc}") from None
    if not isinstance(payload, dict):
        raise WaitError("任务响应不是对象", code="invalid_response")
    return payload


def resolve_key(key_file: str | None, environ: dict | None = None) -> tuple[str, str]:
    """返回 ``(key, source)``；source 只含来源说明，不含 Key 正文。"""

    env = os.environ if environ is None else environ
    if key_file:
        path = Path(key_file).expanduser()
        try:
            key = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise WaitError(f"密钥文件不可读：{path}（{exc.strerror or exc}）", code="key_missing")
        source = f"密钥文件 {path}"
    else:
        direct = (env.get("TALK_API_KEY") or "").strip()
        if direct:
            key, source = direct, "环境变量 TALK_API_KEY"
        else:
            env_file = (env.get("TALK_WAIT_KEY_FILE") or "").strip()
            if not env_file:
                raise WaitError(
                    "缺少密钥来源：请传 --key-file，或设置 TALK_API_KEY / TALK_WAIT_KEY_FILE",
                    code="key_missing",
                )
            path = Path(env_file).expanduser()
            try:
                key = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise WaitError(f"密钥文件不可读：{path}（{exc.strerror or exc}）", code="key_missing")
            source = f"密钥文件 {path}"
    if not key:
        raise WaitError("密钥为空", code="key_empty")
    if any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in key):
        raise WaitError("密钥必须是单行可打印 ASCII，检查 BOM/空白/换行", code="key_invalid")
    return key, source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="等待 TALK 任务进入终态（程序轮询，不调用模型）",
        allow_abbrev=False,
    )
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--key-file", default=None)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--request-timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT)
    parser.add_argument("--json", action="store_true", help="输出单行 JSON")
    return parser


def _summary(task: dict, elapsed: float) -> dict:
    return {
        "task_id": task.get("id"),
        "status": task.get("status"),
        "workflow_status": task.get("workflow_status"),
        "result_message_id": task.get("result_message_id"),
        "last_error": task.get("last_error"),
        "elapsed_seconds": int(elapsed),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse 用法错误
        return 0 if exc.code == 0 else 64
    try:
        key, _source = resolve_key(args.key_file)
        task, elapsed = wait_for_task(
            args.task_id,
            lambda task_id: fetch_task(
                args.base_url, key, task_id, request_timeout=args.request_timeout
            ),
            interval=args.interval,
            timeout=args.timeout,
        )
    except WaitTimeout as exc:
        if args.json:
            print(json.dumps({"event": "timeout", "task_id": exc.task_id,
                              "elapsed_seconds": int(exc.elapsed), "outcome": "timeout", "reason": None}, ensure_ascii=False))
        else:
            print(f"TALK_TASK_TIMEOUT task={exc.task_id} elapsed={int(exc.elapsed)}s")
        return 1
    except WaitError as exc:
        if args.json:
            print(json.dumps({"event": "error", "code": exc.code, "message": str(exc),
                              "outcome": "error", "reason": None},
                             ensure_ascii=False))
        else:
            print(f"TALK_TASK_ERROR code={exc.code} message={exc}")
        return 2
    except KeyboardInterrupt:
        print("TALK_TASK_CANCELED", file=sys.stderr)
        return 130

    payload = _summary(task, elapsed)
    reason = None if is_terminal(task) else attention_reason(task)
    payload["event"] = "attention" if reason else "done"
    payload["outcome"] = payload["event"]
    payload["reason"] = reason
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    elif reason:
        print(
            f"TALK_TASK_ATTENTION task={payload['task_id']} status={payload['status']} "
            f"workflow={payload['workflow_status']} reason={reason} "
            f"elapsed={payload['elapsed_seconds']}s"
        )
    else:
        print(
            "TALK_TASK_DONE task={0} status={1} workflow={2} result={3} elapsed={4}s".format(
                payload["task_id"],
                payload["status"],
                payload["workflow_status"],
                payload["result_message_id"],
                payload["elapsed_seconds"],
            )
        )
    return 3 if reason else 0


if __name__ == "__main__":
    sys.exit(main())
