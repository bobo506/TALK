"""角色生命周期 R1-4b：**默认关闭**的宿主持久请求 worker。

职责边界（REQUEST_CONTRACT §10）
--------------------------------
- 只发现**已启用项目**里的人类请求（``GET role-requests?claimable=true``，覆盖
  ``requested``、失效 ``leased`` 与失联 ``created``）；不扫描未配置成员，不猜 member；
- 通过 ``claim`` 取得一次性 ``lease_token``（只留内存），再用原 ``POST /roles`` +
  ``operation_key=request_key`` + ``lease_token`` 做首次创建；201 响应里的 Key 只留内存，
  随后私有原子写入仓库外 Key 文件；
- ``recover`` 先在角色锁下核本机当前有效 Key 与当前代际：已有则续跑，没有才凭本次人类
  明确意图调用一次 ``rotate-key``（200 reused 不返 Key）；仍无当前 Key 则报
  ``manual_recovery_required``，**不自动再次轮换**；
- 新增私有 ``credential.json`` 只记录 member/version/source/intent/时间，**不含 Key**；
  Key 与元数据不是一起原子提交，元数据失败不删除已发布 Key；
- 每步在副作用前捕获作业 revision/attempt/credential_version 与请求资格，真实本地工作或
  复核后才 ACK；``report(provisioned)`` 仅三步真的成功时提交；
- 不 spawn 任何角色 CLI、不做原生登录/模型调用、不复制原生认证目录。

安全/可用性
-----------
- 默认关闭：``enabled=False`` 时零 HTTP、零文件写入；``apply=False`` 时只读发现（不 claim）；
- 只允许 **回环** 基址；重定向一律拒绝跨机目标，同源重定向也会先摘掉 ``X-API-Key``；
- token/Key/完整 HTTP 正文/绝对私有路径不进控制台、日志、普通返回或交付；公共输出走
  **严格白名单**，并对 ``lease_token`` 字段名做额外遮蔽；
- 有明确停止/阶段取消与有限 IO 预算；worker 不持有也不修改 R1-3 的 Popen 所有权。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.role_provision import (  # noqa: E402 - 复用 R1-2 已验私有路径/锁/原子写
    DEFAULT_BASE_URL,
    DEFAULT_LOCK_STALE_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    ERROR_BODY_READ_LIMIT_BYTES,
    HttpResponse,
    ProvisionError,
    REQUEST_ENDPOINT_ERROR_WHITELIST,
    STATE_SKIPPED,
    STATE_SUCCEEDED,
    STEP_ORDER,
    _assert_root_chain_has_no_reparse,
    _extract_whitelisted_error_code,
    _is_reparse_point,
    _path_is_within,
    _read_key_file,
    _resolve_operator_key,
    _role_key_verdict,
    _write_key_file,
    acquire_provision_locks,
    create_role_for_request,
    credential_metadata_path,
    key_file_path,
    profile_lock_path_for,
    read_credential_metadata,
    release_provision_locks,
    rotate_role_key_for_request,
    run_request_provision,
    write_credential_metadata,
)

SCHEMA = "talk-role-provision-worker-1"
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_DISCOVERY_LIMIT = 20
DEFAULT_IO_BUDGET_SECONDS = 120.0

#: 允许的回环主机名（server 与 worker 必须同机）。
LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

#: 请求驱动 worker 可用的稳定错误码（与 models.ROLE_REQUEST_HOST_ERROR_CODES 对齐的
#: 子集 + 本片新增的有限宿主码）。未知码在回报前一律降级为 ``http_error``。
WORKER_ERROR_CODES: frozenset[str] = frozenset(
    {
        "worker_disabled",
        "worker_base_url_not_loopback",
        "worker_redirect_refused",
        "worker_io_budget_exceeded",
        "worker_stopped",
        "role_key_foreign_refused",
        "key_provenance_write_failed",
        "manual_recovery_required",
        "operator_key_missing",
        "provision_lock_busy",
        "profile_write_failed",
        "profile_root_invalid",
        "key_file_write_failed",
        "key_write_failed",
        "key_permissions_failed",
        "key_root_inside_repo",
        "role_key_unknown",
        "role_key_stale",
        "identity_mismatch",
        "preflight_failed",
        "path_escape_refused",
        "symlink_refused",
        "resume_required",
        "ack_failed",
        "ack_stale",
        "http_error",
        "cli_executable_missing",
        "not_apply_mode",
        # R1-4b 返修 F1/F4/F5：入口关闭/只读、资格复查与统一轮次结果的稳定码。
        "role_request_lease_invalid",
        "role_request_lease_conflict",
        "role_request_status_conflict",
        "role_request_host_mismatch",
        "role_request_credential_stale",
    }
)

#: 公共输出严格白名单：未列出的键一律不进入普通返回/交付。
PUBLIC_KEYS: frozenset[str] = frozenset(
    {
        "schema",
        "mode",
        "enabled",
        "applied",
        "stage",
        "outcome",
        "project_id",
        "host_label",
        "worker_host",
        "request_key",
        "kind",
        "status",
        "effective_status",
        "member_id",
        "origin_operation_key",
        "credential_version",
        "lease_generation",
        "lease_config_version",
        "revision",
        "attempts",
        "claimable",
        "retry_exhausted",
        "expires_at",
        "planned",
        "count",
        "requests",
        "steps",
        "profile",
        "key_file",
        "preflight",
        "state",
        "sent",
        "reason",
        "ack",
        "job",
        "report",
        "reused",
        "error_code",
        "replayed",
        "metadata_repaired",
        "key_published",
        "rotation",
        "rounds",
        "outcomes",
        "note",
    }
)

#: 公共输出里额外遮蔽的键名（即使白名单里有同名字段也不外泄明文）。
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"lease_token", "api_key", "token", "lease_token_hash", "operator_key"}
)


class WorkerError(RuntimeError):
    """稳定错误码 + 脱敏说明（绝不携带 Key/token/正文/绝对私有路径）。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class WorkerStopped(RuntimeError):
    """停止/阶段取消请求：在阶段边界安全退出，不影响任何外部进程。"""


class LeaseInvalidated(WorkerError):
    """复查发现当前请求/租约已失效（R1-4b 返修 F4）。

    语义：本地副作用/ACK/report **一律不写**，也不尝试用新版本给旧工作补证。它继承
    ``WorkerError``，因此宿主与公共输出的稳定码语义不变；但返回形状额外标注
    ``report.sent=false``，区别于“真正回报过 failed”的业务失败。
    """


# ---------------------------------------------------------------------------
# 传输：只允许回环基址，绝不跟随把凭据转到别处的重定向
# ---------------------------------------------------------------------------


def loopback_host(value: Any) -> Optional[str]:
    """把基址解析成回环主机名；非回环/非法一律 ``None``。"""
    try:
        parsed = urllib.parse.urlsplit(str(value or ""))
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").strip().lower()
    if host in ("", "0.0.0.0", "::", "[::]"):
        return None
    return host if host in LOOPBACK_HOSTS else None


def assert_loopback_base_url(base_url: Any) -> str:
    """只接受 server/worker 同机的回环基址；否则稳定拒绝（不发任何凭据）。"""
    host = loopback_host(base_url)
    if host is None:
        raise WorkerError(
            "worker_base_url_not_loopback",
            "只允许回环基址（server 与 worker 必须同机）",
        )
    return str(base_url).rstrip("/")


class _LoopbackRedirectHandler(urllib.request.HTTPRedirectHandler):
    """重定向守卫：跨机目标直接拒绝；同源目标也先摘掉 ``X-API-Key``。

    凭据只允许发往 ``claim`` 时的回环来源，绝不因为一次 3xx 被带到别的机器。
    """

    def __init__(self, origin_host: Optional[str] = None):
        super().__init__()
        self.origin_host = (origin_host or "").lower()

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        target_host = loopback_host(newurl)
        if target_host is None or (self.origin_host and target_host != self.origin_host):
            raise urllib.error.HTTPError(
                req.full_url, 403, "redirect_refused", headers, None
            )
        stripped = urllib.request.Request(newurl, method=req.get_method())
        for name, value in req.header_items():
            if name.lower() in ("x-api-key", "authorization", "cookie"):
                continue
            stripped.add_header(name, value)
        return stripped


class WorkerTransport:
    """宿主 worker 的 HTTP 边界（``X-API-Key`` 只进 header；正文绝不回显/落盘）。"""

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = assert_loopback_base_url(base_url)
        self._timeout = float(timeout)
        self._origin = loopback_host(self.base_url) or ""
        self._opener = urllib.request.build_opener(
            _LoopbackRedirectHandler(self._origin)
        )

    def request_json(
        self,
        method: str,
        url: str,
        *,
        api_key: Optional[str] = None,
        body: Any = None,
        timeout: Optional[float] = None,
    ) -> HttpResponse:
        host = loopback_host(url)
        if host is None or host != self._origin:
            raise WorkerError(
                "worker_base_url_not_loopback", "请求 URL 不是本机回环来源"
            )
        headers = {"Accept": "application/json"}
        if api_key:
            headers["X-API-Key"] = str(api_key)
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=str(method).upper()
        )
        effective_timeout = self._timeout if timeout is None else float(timeout)
        try:
            with self._opener.open(request, timeout=effective_timeout) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200) or 200)
        except urllib.error.HTTPError as exc:
            raw: Any = None
            try:
                raw = exc.read(ERROR_BODY_READ_LIMIT_BYTES)
            except Exception:  # noqa: BLE001 - 读错误正文失败等价于没有错误码
                raw = None
            finally:
                try:
                    exc.close()
                except Exception:  # noqa: BLE001
                    pass
            if int(exc.code) == 403 and str(exc.reason) == "redirect_refused":
                raise WorkerError(
                    "worker_redirect_refused", "重定向目标不是本机回环来源；已拒绝"
                ) from exc
            return HttpResponse(
                status=int(exc.code),
                payload=None,
                error_code=_extract_whitelisted_error_code(
                    raw, REQUEST_ENDPOINT_ERROR_WHITELIST
                ),
            )
        except (urllib.error.URLError, OSError, TimeoutError):
            return HttpResponse(status=0, payload=None)
        if not raw:
            return HttpResponse(status=status, payload=None)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return HttpResponse(status=status, payload=None)
        return HttpResponse(status=status, payload=payload)


# ---------------------------------------------------------------------------
# 公共输出
# ---------------------------------------------------------------------------


def redact(record: Any) -> Any:
    """严格白名单 + 敏感键遮蔽；不打印 Key/token/正文/绝对私有路径。"""
    if isinstance(record, list):
        return [redact(item) for item in record]
    if isinstance(record, Mapping):
        out: dict[str, Any] = {}
        for key, value in record.items():
            text = str(key)
            if text in SENSITIVE_KEYS or text not in PUBLIC_KEYS:
                continue
            out[text] = redact(value)
        return out
    return record


def _safe_step_view(steps: Any) -> dict[str, Any]:
    if not isinstance(steps, Mapping):
        return {}
    out: dict[str, Any] = {}
    for name in STEP_ORDER:
        entry = steps.get(name)
        if isinstance(entry, Mapping):
            out[name] = {
                "state": entry.get("state"),
                "attempts": entry.get("attempts"),
                "error_code": entry.get("error_code"),
            }
    return out


def coerce_outcomes(raw: Any) -> list[dict[str, Any]]:
    """把任意轮次返回值收敛成 ``list[dict]``（返修 F5）。

    ``run_round`` 现在恒返回列表；本函数仍作为宿主/CLI 边界的最后一道防线：单个映射包成
    单元素列表，``None`` 当作空轮次，其它类型（含旧实现的字符串误并入）一律收敛为一条
    稳定失败 outcome，绝不把字符串拆成列表或按键名遍历。
    """
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        return [dict(raw)]
    if isinstance(raw, (list, tuple)):
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, Mapping):
                out.append(dict(item))
            else:
                out.append(
                    {"stage": "worker", "outcome": "failed", "error_code": "http_error"}
                )
        return out
    return [{"stage": "worker", "outcome": "failed", "error_code": "http_error"}]


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------


class RoleProvisionWorker:
    """单请求串行处理的人类请求 worker（默认关闭、默认只读计划）。"""

    def __init__(
        self,
        *,
        project_id: str,
        host_label: str,
        base_url: str = DEFAULT_BASE_URL,
        project_root: Any = REPO_ROOT,
        key_root: Any = None,
        operator_key: Optional[str] = None,
        transport: Any = None,
        enabled: bool = False,
        apply: bool = False,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        io_budget_seconds: float = DEFAULT_IO_BUDGET_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        discovery_limit: int = DEFAULT_DISCOVERY_LIMIT,
        lock_stale_seconds: float = DEFAULT_LOCK_STALE_SECONDS,
        cli_executable: Any = None,
        environ: Any = None,
        clock: Any = None,
        repo_root: Any = REPO_ROOT,
    ):
        if not str(project_id or "").strip():
            raise WorkerError("http_error", "缺少 project_id")
        if not str(host_label or "").strip():
            raise WorkerError("http_error", "缺少 host_label（显式宿主标签）")
        self.project_id = str(project_id).strip()
        self.host_label = str(host_label).strip()
        self.base_url = str(base_url or DEFAULT_BASE_URL).rstrip("/")
        self.project_root = Path(project_root)
        self.key_root = Path(key_root).expanduser() if key_root else None
        self.operator_key = operator_key
        self.enabled = bool(enabled)
        self.apply = bool(apply)
        self.timeout_seconds = float(timeout_seconds)
        self.io_budget_seconds = float(io_budget_seconds)
        self.poll_interval = float(poll_interval)
        self.discovery_limit = int(discovery_limit)
        self.lock_stale_seconds = float(lock_stale_seconds)
        self.cli_executable = cli_executable
        self.environ = (
            {str(k): str(v) for k, v in os.environ.items()}
            if environ is None
            else {str(k): str(v) for k, v in environ.items()}
        )
        self._clock = clock or time.monotonic
        self.repo_root = Path(repo_root)
        # 注入传输（测试/嵌入）时不做真实回环校验；否则默认传输本身强制回环。
        if transport is not None:
            self.transport = transport
        else:
            assert_loopback_base_url(self.base_url)
            self.transport = WorkerTransport(self.base_url, self.timeout_seconds)
        self._stopping = False
        self._stage_cancelled = False
        self._deadline: Optional[float] = None
        #: 轮次内已开过预算：``process`` 在同一个 ``run_round`` 里不再重开（返修 F2）。
        self._in_round = False

    # ── 生命周期控制 ─────────────────────────────────────────────────

    def request_stop(self) -> None:
        """请求停止：只在阶段边界生效，不触碰任何外部进程/句柄。"""
        self._stopping = True

    def cancel_stage(self) -> None:
        """取消当前阶段：下一次阶段检查点抛 ``WorkerStopped``。"""
        self._stage_cancelled = True

    def _check_alive(self) -> None:
        if self._stopping or self._stage_cancelled:
            raise WorkerStopped("worker stopped")
        if self._deadline is not None and self._clock() > self._deadline:
            raise WorkerError("worker_io_budget_exceeded", "本轮 IO 预算已用完")

    def _begin_budget(self, *, fresh: bool = True) -> None:
        """开一轮 IO 预算；``fresh=False`` 表示复用轮次内已开的预算（不重置也不清取消）。"""
        if fresh or self._deadline is None:
            self._deadline = self._clock() + self.io_budget_seconds
        if fresh:
            self._stage_cancelled = False

    def _end_budget(self) -> None:
        self._deadline = None

    def _io_timeout(self) -> float:
        """每次网络请求的超时：收敛到本轮**剩余预算**，耗尽即稳定拒绝（返修 F2）。"""
        if self._deadline is None:
            return self.timeout_seconds
        remaining = self._deadline - self._clock()
        if remaining <= 0:
            raise WorkerError("worker_io_budget_exceeded", "本轮 IO 预算已用完")
        return min(self.timeout_seconds, remaining)

    # ── HTTP 便捷封装 ────────────────────────────────────────────────

    def _operator(self) -> str:
        if self.operator_key:
            return self.operator_key
        resolved = _resolve_operator_key(self.environ)
        if not resolved:
            raise WorkerError("operator_key_missing", "缺少 operator（human）凭据")
        self.operator_key = resolved
        return resolved

    def _api(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request_key_path(self, request_key: str) -> str:
        quoted = urllib.parse.quote(request_key, safe="")
        project = urllib.parse.quote(self.project_id, safe="")
        return f"/api/projects/{project}/role-requests/{quoted}"

    def list_claimable(self) -> list[dict[str, Any]]:
        """只读发现：``claimable=true``，不写库、不扫描未配置成员。"""
        url = (
            f"{self._api('/api/projects/' + urllib.parse.quote(self.project_id, safe=''))}"
            f"/role-requests?claimable=true&limit={int(self.discovery_limit)}"
        )
        response = self.transport.request_json(
            "GET", url, api_key=self._operator(), timeout=self._io_timeout()
        )
        if response.status == 0:
            raise WorkerError("http_error", "TALK API 不可达")
        if response.status != 200 or not isinstance(response.payload, list):
            raise WorkerError("http_error", f"发现请求失败（HTTP {response.status}）")
        return [item for item in response.payload if isinstance(item, Mapping)]

    def get_request(self, request_key: str) -> dict[str, Any]:
        response = self.transport.request_json(
            "GET",
            self._api(self._request_key_path(request_key)),
            api_key=self._operator(),
            timeout=self._io_timeout(),
        )
        if response.status != 200 or not isinstance(response.payload, Mapping):
            raise WorkerError("http_error", f"读取请求失败（HTTP {response.status}）")
        return dict(response.payload)

    def claim(self, request_key: str, expected_revision: int) -> dict[str, Any]:
        url = self._api(self._request_key_path(request_key) + "/claim")
        response = self.transport.request_json(
            "POST",
            url,
            api_key=self._operator(),
            body={"host": self.host_label, "expected_revision": int(expected_revision)},
            timeout=self._io_timeout(),
        )
        if response.status != 200 or not isinstance(response.payload, Mapping):
            code = getattr(response, "error_code", None) or "http_error"
            raise WorkerError(str(code), f"claim 被拒绝（HTTP {response.status}）")
        return dict(response.payload)

    def report(
        self,
        request_key: str,
        *,
        lease_token: str,
        expected_revision: int,
        outcome: str,
        error_code: Optional[str],
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "lease_token": lease_token,
            "expected_revision": int(expected_revision),
            "outcome": outcome,
        }
        if error_code is not None:
            body["error_code"] = error_code
        url = self._api(self._request_key_path(request_key) + "/report")
        response = self.transport.request_json(
            "POST", url, api_key=self._operator(), body=body, timeout=self._io_timeout()
        )
        return {
            "status": int(getattr(response, "status", 0) or 0),
            "payload": dict(response.payload)
            if isinstance(response.payload, Mapping)
            else {},
            "error_code": getattr(response, "error_code", None),
        }

    # ── 本地 Key / 元数据 ────────────────────────────────────────────

    def _key_root(self) -> Path:
        if self.key_root is None:
            raise WorkerError("key_root_inside_repo", "缺少显式 key_root")
        declared = self.key_root
        _assert_root_chain_has_no_reparse(declared)
        resolved = declared.resolve()
        if _path_is_within(resolved, self.repo_root):
            raise WorkerError("key_root_inside_repo", "Key 根必须位于仓库之外")
        return resolved

    def _paths(self, member_id: str) -> dict[str, Any]:
        key_root = self._key_root()
        return {
            "key_root": key_root,
            "key_path": key_file_path(key_root, member_id),
            "metadata_path": credential_metadata_path(key_root, member_id),
            "profile_lock": profile_lock_path_for(self.project_root, member_id),
        }

    def _local_key_status(self, member_id: str, key_path: Path) -> str:
        """本机当前 Key 状态：``ok`` / ``stale`` / ``absent`` / ``unknown``。"""
        if not key_path.is_file():
            return "absent"
        if _read_key_file(key_path) is None:
            return "stale"
        key = _read_key_file(key_path)
        verdict, _actual = _role_key_verdict(
            self.transport, self.base_url, key, member_id, self._io_timeout()
        )
        return "ok" if verdict == "ok" else ("stale" if verdict == "invalid" else "unknown")

    def _provenance_allows_replace(
        self,
        member_id: str,
        key_path: Path,
        *,
        expected_credential_version: Optional[int],
    ) -> str:
        """专用旧文件替换的来源证明（合同 §10）。

        - 目标不存在：可直接发布（``absent``）；
        - 存在但不可读/含非法字符：``role_key_foreign_refused``（未知文件不覆盖）；
        - 缺少本人来源记录、记录属于别的成员、或记录不是本人已知旧代：
          ``role_key_foreign_refused``；
        - 普通脚本 ``role_key_stale`` 拒覆盖语义不变（不经本函数）。
        """
        if not key_path.is_file():
            return "absent"
        if _is_reparse_point(key_path):
            raise WorkerError("symlink_refused", "Key 目标经过符号链接/junction")
        if _read_key_file(key_path) is None:
            raise WorkerError(
                "role_key_foreign_refused", "现有 Key 文件不可读/含非法字符；拒绝覆盖"
            )
        metadata = read_credential_metadata(self._key_root(), member_id)
        if metadata is None:
            raise WorkerError(
                "role_key_foreign_refused", "缺少本人来源记录；拒绝覆盖现有 Key 文件"
            )
        if str(metadata.get("member_id") or "") != member_id:
            raise WorkerError("role_key_foreign_refused", "来源记录属于其它成员")
        if (
            expected_credential_version is not None
            and int(metadata.get("credential_version") or 0)
            != int(expected_credential_version)
        ):
            raise WorkerError(
                "role_key_foreign_refused", "来源记录不是本人已知旧代；拒绝覆盖"
            )
        return "provenance_ok"

    def publish_key(
        self,
        member_id: str,
        new_key: str,
        *,
        source: str,
        request_key: str,
        kind: str,
        credential_version: Optional[int],
        expected_old_version: Optional[int],
    ) -> dict[str, Any]:
        """私有发布 Key + 元数据；Key 只留在内存与私有文件里。"""
        paths = self._paths(member_id)
        key_path = paths["key_path"]
        provenance = self._provenance_allows_replace(
            member_id,
            key_path,
            expected_credential_version=(
                expected_old_version if source == "recover" else None
            ),
        )
        _write_key_file(key_path, new_key)
        result: dict[str, Any] = {
            "key_published": True,
            "provenance": provenance,
            "metadata_repaired": False,
            "error_code": None,
        }
        try:
            write_credential_metadata(
                paths["key_root"],
                member_id,
                credential_version=int(credential_version or 1),
                source=source,
                intent=request_key,
                intent_kind=kind,
            )
        except ProvisionError as exc:
            # Key 已发布且有效：**不删除**，只记录失败；下一次以本人当前 Key 认证重建。
            result["error_code"] = "key_provenance_write_failed"
            result["detail"] = exc.code
        return result

    def repair_metadata(
        self, member_id: str, *, request_key: str, kind: str, server_version: Optional[int]
    ) -> Optional[str]:
        """以本人当前 Key + 服务端当前版本核验后重建同路径元数据；不轮换、不重取旧 Key。

        返回 ``None`` 表示无需修复或修复成功；否则返回稳定错误码。
        """
        paths = self._paths(member_id)
        key_path = paths["key_path"]
        if not key_path.is_file():
            return None
        metadata = read_credential_metadata(paths["key_root"], member_id)
        if (
            metadata is not None
            and server_version is not None
            and int(metadata["credential_version"]) == int(server_version)
        ):
            return None
        key = _read_key_file(key_path)
        if key is None or server_version is None:
            return None
        verdict, _actual = _role_key_verdict(
            self.transport, self.base_url, key, member_id, self._io_timeout()
        )
        if verdict != "ok":
            return None
        try:
            write_credential_metadata(
                paths["key_root"],
                member_id,
                credential_version=int(server_version),
                source="existing_key",
                intent=request_key,
                intent_kind=kind,
            )
        except ProvisionError:
            return "key_provenance_write_failed"
        return None

    # ── 副作用前的资格复查（返修 F4）───────────────────────────────────

    #: 投影里仍允许继续本地工作的活动状态。
    ACTIVE_STATUSES: tuple[str, ...] = ("requested", "leased", "created")

    def _verify_lease(
        self,
        request_key: str,
        claimed: Mapping[str, Any],
        *,
        member_id: Optional[str] = None,
        expected_credential_version: Optional[int] = None,
        stage: str = "check",
    ) -> dict[str, Any]:
        """任何本地副作用/ACK/report 前复查当前请求资格；失效即 :class:`LeaseInvalidated`。

        复查项（全部来自**只读** ``GET`` 投影，绝不靠写请求反推）：

        - ``lease_held``：服务端判定的「项目启用 + ``config_version`` 未换代 + 未到期 +
          世代/哈希齐全」，这是 disable/re-enable、期限失效、人工 resume 的统一事实；
        - ``claimed_at``/``expires_at``：与本次 claim 响应逐字相同，用于发现**被别的
          领取者换代**（同 token 已被替换）；
        - ``status``：仍在活动状态，且不是 ``failed``/``cancelled``/``provisioned``；
        - ``member_id``/``credential_version``：目标与预期代际仍然一致，绝不用新版本给
          旧工作补证。
        """
        self._check_alive()
        fresh = self.get_request(request_key)
        status = str(fresh.get("status") or "")
        if fresh.get("lease_held") is not True:
            raise LeaseInvalidated("role_request_lease_invalid", "当前租约已失效")
        if status not in self.ACTIVE_STATUSES:
            raise LeaseInvalidated(
                "role_request_status_conflict", "当前请求状态已不允许继续本地工作"
            )
        claimed_at = claimed.get("claimed_at")
        if claimed_at is not None and fresh.get("claimed_at") != claimed_at:
            raise LeaseInvalidated(
                "role_request_lease_invalid", "本次租约已被别的领取者换代"
            )
        expires_at = claimed.get("expires_at")
        if expires_at is not None and fresh.get("expires_at") != expires_at:
            raise LeaseInvalidated("role_request_lease_invalid", "租约期限已换代")
        if member_id is not None:
            actual_member = str(fresh.get("member_id") or "")
            if actual_member != str(member_id):
                raise LeaseInvalidated("identity_mismatch", "请求目标成员与预期不一致")
        if expected_credential_version is not None:
            actual_version = fresh.get("credential_version")
            if actual_version is None or int(actual_version) != int(
                expected_credential_version
            ):
                raise LeaseInvalidated(
                    "role_request_credential_stale", "目标凭据代际与预期不一致"
                )
        fresh["_verified_stage"] = stage
        return fresh

    def _verify_new_key(
        self,
        member_id: str,
        new_key: str,
        *,
        request_key: str,
        claimed: Mapping[str, Any],
        expected_credential_version: Optional[int],
    ) -> None:
        """一次性响应里的新 Key 必须**先**核本人身份与代际，之后才允许私有发布。"""
        self._check_alive()
        verdict, _actual = _role_key_verdict(
            self.transport, self.base_url, new_key, member_id, self._io_timeout()
        )
        if verdict != "ok":
            raise WorkerError("identity_mismatch", "新 Key 未通过本人身份核验；拒绝发布")
        self._verify_lease(
            request_key,
            claimed,
            member_id=member_id,
            expected_credential_version=expected_credential_version,
            stage="key",
        )

    def _eligibility_guard(
        self,
        request_key: str,
        claimed: Mapping[str, Any],
        *,
        member_id: str,
        expected_credential_version: Optional[int],
    ) -> Any:
        """交给 :func:`run_request_provision` 的边界回调：每个副作用前复查同一资格。"""

        def guard() -> None:
            self._verify_lease(
                request_key,
                claimed,
                member_id=member_id,
                expected_credential_version=expected_credential_version,
                stage="steps",
            )

        return guard

    # ── 单请求处理 ───────────────────────────────────────────────────

    def process(self, request_key: str) -> dict[str, Any]:
        """处理单个请求：claim → 创建/恢复 → 私有 Key/元数据 → 三步 → report。

        返修 F1：``process`` 是**可执行入口**，因此必须与 ``serve``/``run_round`` 同语义——
        关闭时零 HTTP/零写入；只读（``apply=False``）时不 claim/不写，只回稳定 ``skipped``。
        """
        if not self.enabled:
            return redact(
                {
                    "stage": "disabled",
                    "outcome": "skipped",
                    "request_key": request_key,
                    "project_id": self.project_id,
                    "error_code": "worker_disabled",
                }
            )
        if not self.apply:
            return redact(
                {
                    "stage": "plan",
                    "outcome": "skipped",
                    "request_key": request_key,
                    "project_id": self.project_id,
                    "error_code": "not_apply_mode",
                }
            )
        if not self._in_round:
            self._begin_budget(fresh=True)
        result: dict[str, Any] = {
            "stage": "discover",
            "outcome": "pending",
            "request_key": request_key,
            "project_id": self.project_id,
        }
        lease_token: Optional[str] = None
        try:
            self._check_alive()
            detail = self.get_request(request_key)
            result["kind"] = detail.get("kind")
            result["status"] = detail.get("status")
            result["revision"] = detail.get("revision")
            result["member_id"] = detail.get("member_id")
            if not detail.get("claimable"):
                result["stage"] = "claim"
                result["outcome"] = "skipped"
                result["error_code"] = "role_request_lease_conflict"
                return redact(result)

            claimed = self.claim(request_key, int(detail.get("revision") or 0))
            lease_token = claimed.get("lease_token")
            if not isinstance(lease_token, str) or not lease_token:
                raise WorkerError("http_error", "claim 响应缺少一次性租约 token")
            result["stage"] = "claim"
            result["kind"] = claimed.get("kind")
            result["status"] = claimed.get("status")
            result["effective_status"] = claimed.get("effective_status")
            result["revision"] = claimed.get("revision")
            result["member_id"] = claimed.get("member_id")
            result["lease_generation"] = claimed.get("lease_generation")
            result["lease_config_version"] = claimed.get("lease_config_version")
            result["credential_version"] = claimed.get("credential_version")
            result["expires_at"] = claimed.get("expires_at")
            self._verify_lease(request_key, claimed, stage="claim")

            member_id = str(claimed.get("member_id") or "").strip()
            kind = str(claimed.get("kind") or "")
            payload = claimed.get("payload") if isinstance(claimed.get("payload"), Mapping) else {}

            new_key: Optional[str] = None
            publish_source: Optional[str] = None
            expected_old_version: Optional[int] = None
            if not member_id:
                created = create_role_for_request(
                    transport=self.transport,
                    base_url=self.base_url,
                    project_id=self.project_id,
                    payload=payload,
                    request_key=request_key,
                    lease_token=lease_token,
                    operator_key=self._operator(),
                    timeout=self._io_timeout(),
                )
                result["stage"] = "create"
                if created["status"] == 201:
                    member_id = str(created.get("member_id") or "")
                    new_key = created.get("api_key")
                    publish_source = "create"
                    result["credential_version"] = created.get("credential_version") or 1
                elif created["status"] == 200:
                    # 幂等重放：请求已创建但本次响应**不返 Key**；先核本机当前有效 Key。
                    member_id = str(created.get("member_id") or "")
                    result["credential_version"] = claimed.get("credential_version")
                else:
                    code = created.get("error_code") or "http_error"
                    result["outcome"] = "failed"
                    result["error_code"] = code
                    return self._finish_failed(
                        request_key, lease_token, result, code
                    )
                result["member_id"] = member_id or None
                if not member_id:
                    raise WorkerError("http_error", "创建响应缺少真实 member_id")
                # 返修 F4：成员已在服务端真实创建后，**先**复查当前请求/租约/目标代际，
                # 再核新 Key 本人身份，最后才允许任何本地发布或后续步骤。
                expected_version = (
                    created.get("credential_version")
                    if created.get("status") == 201
                    else claimed.get("credential_version")
                )
                self._verify_lease(
                    request_key,
                    claimed,
                    member_id=member_id,
                    expected_credential_version=expected_version,
                    stage="post-create",
                )
                if new_key is not None:
                    self._verify_new_key(
                        member_id,
                        new_key,
                        request_key=request_key,
                        claimed=claimed,
                        expected_credential_version=expected_version,
                    )

            paths = self._paths(member_id)
            result["stage"] = "key"
            # R1-4b：核本机 Key / 受限轮换 / 私有发布 / 三步推进在**同一临界区**内完成，
            # 复用 R1-2 的身份档锁 + Key 锁（不另造一套弱化实现）。
            locks = None
            try:
                locks = acquire_provision_locks(
                    self.project_root,
                    paths["key_root"],
                    member_id,
                    stale_seconds=self.lock_stale_seconds,
                )
            except ProvisionError as exc:
                result["outcome"] = "failed"
                result["error_code"] = exc.code
                return self._finish_failed(request_key, lease_token, result, exc.code)
            try:
                if new_key is None:
                    status = self._local_key_status(member_id, paths["key_path"])
                    if status == "ok":
                        publish_source = None
                    elif status == "unknown":
                        # 无法核验本机 Key（HTTP/超时）：既不轮换也不猜；留待下一次重试。
                        result["outcome"] = "failed"
                        result["error_code"] = "http_error"
                        return self._finish_failed(
                            request_key, lease_token, result, "http_error"
                        )
                    elif kind == "recover":
                        # 本机没有当前有效 Key：只凭本次人类明确意图轮换一次。
                        rotation = rotate_role_key_for_request(
                            transport=self.transport,
                            base_url=self.base_url,
                            project_id=self.project_id,
                            member_id=member_id,
                            request_key=request_key,
                            lease_token=lease_token,
                            expected_credential_version=(
                                payload.get("expected_credential_version")
                                if isinstance(payload, Mapping)
                                else None
                            ),
                            operator_key=self._operator(),
                            timeout=self._io_timeout(),
                        )
                        result["rotation"] = {
                            "status": rotation["status"],
                            "reused": rotation["reused"],
                            "credential_version": rotation["credential_version"],
                        }
                        if rotation["status"] == 201:
                            new_key = rotation.get("api_key")
                            publish_source = "recover"
                            expected_old_version = (
                                int(payload.get("expected_credential_version"))
                                if isinstance(payload, Mapping)
                                and payload.get("expected_credential_version") is not None
                                else None
                            )
                            result["credential_version"] = rotation.get(
                                "credential_version"
                            )
                            # 返修 F4：轮换回来的新 Key 先核本人身份与代际，再私有发布。
                            if new_key is not None:
                                self._verify_new_key(
                                    member_id,
                                    new_key,
                                    request_key=request_key,
                                    claimed=claimed,
                                    expected_credential_version=rotation.get(
                                        "credential_version"
                                    ),
                                )
                        elif rotation["status"] == 200 and rotation["reused"]:
                            # 同意图已执行过：不返 Key。仍无本机当前 Key 时需人类新意图。
                            status = self._local_key_status(member_id, paths["key_path"])
                            if status != "ok":
                                result["outcome"] = "failed"
                                result["error_code"] = "manual_recovery_required"
                                return self._finish_failed(
                                    request_key,
                                    lease_token,
                                    result,
                                    "manual_recovery_required",
                                )
                        else:
                            code = rotation.get("error_code") or "http_error"
                            result["outcome"] = "failed"
                            result["error_code"] = code
                            return self._finish_failed(
                                request_key, lease_token, result, code
                            )
                    else:
                        # create 已原子 created 但 201 响应丢失：不自动重取旧 Key、不轮换。
                        result["outcome"] = "failed"
                        result["error_code"] = "manual_recovery_required"
                        return self._finish_failed(
                            request_key, lease_token, result, "manual_recovery_required"
                        )

                # 返修 F4：无论走“新 Key 私有发布”还是“本人修复元数据”，都在写本地文件
                # 之前再复查一次当前请求/租约/目标代际；失效即放弃本地写与后续 ACK/report。
                self._verify_lease(
                    request_key,
                    claimed,
                    member_id=member_id,
                    expected_credential_version=result.get("credential_version"),
                    stage="pre-publish",
                )
                metadata_error: Optional[str] = None
                if new_key is not None and publish_source is not None:
                    published = self.publish_key(
                        member_id,
                        new_key,
                        source=publish_source,
                        request_key=request_key,
                        kind=kind or "create",
                        credential_version=result.get("credential_version"),
                        expected_old_version=expected_old_version,
                    )
                    result["key_published"] = True
                    metadata_error = published.get("error_code")
                else:
                    metadata_error = self.repair_metadata(
                        member_id,
                        request_key=request_key,
                        kind=kind or "create",
                        server_version=claimed.get("credential_version"),
                    )
                    result["metadata_repaired"] = metadata_error is None
                    if metadata_error:
                        result["error_code"] = metadata_error

                self._check_alive()
                result["stage"] = "steps"
                operation_key = str(claimed.get("origin_operation_key") or request_key)
                # 返修 F2/F3/F4：轮次预算/取消检查贯穿到三步与 ACK 边界；已解析 operator
                # 只在内存里贯穿（不写 argv/env）；每个本地副作用/ACK 前复查请求资格。
                steps_kwargs: dict[str, Any] = {
                    "project_id": self.project_id,
                    "member_id": member_id,
                    "operation_key": operation_key,
                    "request_key": request_key,
                    "lease_token": lease_token,
                    "project_root": self.project_root,
                    "key_root": paths["key_root"],
                    "base_url": self.base_url,
                    "overwrite_profile": False,
                    "cli_executable": self.cli_executable,
                    "lock_stale_seconds": self.lock_stale_seconds,
                    "timeout_seconds": self.timeout_seconds,
                    "transport": self.transport,
                    "environ": self.environ,
                    "repo_root": self.repo_root,
                    "locks": locks,
                    "operator_key": self._operator(),
                    "eligibility_check": self._eligibility_guard(
                        request_key,
                        claimed,
                        member_id=member_id,
                        expected_credential_version=result.get("credential_version"),
                    ),
                    "deadline": self._deadline,
                    "clock": self._clock,
                }
                document, _code = run_request_provision(**steps_kwargs)
                if document.get("error_code") == "resume_required":
                    # ACK/作业丢响应后的**受控续跑**：只重开服务端仍待跑的步骤。
                    document, _code = run_request_provision(**steps_kwargs, resume=True)
                elif document.get("error_code") in ("ack_failed", "ack_stale"):
                    # ACK 响应丢失：**先重读同一代际事实**（本函数每次调用都重新捕获作业
                    # 代际、只回报仍 pending 的步骤），再做一次受限重试；绝不把未确认的
                    # ACK 当成成功。
                    document, _code = run_request_provision(**steps_kwargs)
            finally:
                release_provision_locks(locks)

            result["steps"] = _safe_step_view(document.get("steps"))
            result["ack"] = {
                "sent": bool((document.get("ack") or {}).get("sent")),
                "reason": (document.get("ack") or {}).get("reason"),
            }
            result["job"] = {
                "action": (document.get("job") or {}).get("action"),
                "status": (document.get("job") or {}).get("status"),
                "revision": (document.get("job") or {}).get("revision"),
            }
            steps = document.get("steps") or {}
            applied = document.get("conclusion") == "applied" and all(
                (steps.get(step) or {}).get("state") in (STATE_SUCCEEDED, STATE_SKIPPED)
                for step in STEP_ORDER
            )
            if metadata_error:
                result["stage"] = "report"
                result["outcome"] = "failed"
                result["error_code"] = metadata_error
                return self._finish_failed(
                    request_key, lease_token, result, metadata_error
                )
            if not applied:
                code = str(document.get("error_code") or "preflight_failed")
                result["outcome"] = "failed"
                result["error_code"] = code
                return self._finish_failed(request_key, lease_token, result, code)

            result["stage"] = "report"
            return self._finish_provisioned(request_key, lease_token, result)
        except LeaseInvalidated as exc:
            # 返修 F4：资格已在本地副作用前失效 → 不继续本地、不 ACK、不 report，
            # 也绝不用新版本给旧工作补证；真实已创建成员按原样保留。
            result["stage"] = "invalidated"
            result["outcome"] = "failed"
            result["error_code"] = exc.code
            result["report"] = {"sent": False, "reason": "lease_invalid"}
            return redact(result)
        except WorkerStopped:
            result["stage"] = "stopped"
            result["outcome"] = "stopped"
            result["error_code"] = "worker_stopped"
            result["report"] = {"sent": False, "reason": "worker_stopped"}
            return redact(result)
        except WorkerError as exc:
            result["outcome"] = "failed"
            result["error_code"] = exc.code
            if lease_token:
                return self._finish_failed(request_key, lease_token, result, exc.code)
            return redact(result)
        except ProvisionError as exc:
            result["outcome"] = "failed"
            result["error_code"] = exc.code
            if lease_token:
                return self._finish_failed(request_key, lease_token, result, exc.code)
            return redact(result)
        except Exception:  # noqa: BLE001 - 绝不回显可能含凭据的异常正文
            result["outcome"] = "failed"
            result["error_code"] = "http_error"
            if lease_token:
                return self._finish_failed(request_key, lease_token, result, "http_error")
            return redact(result)

    def _reportable(self, code: Any) -> str:
        text = str(code or "")
        return text if text in WORKER_ERROR_CODES else "http_error"

    def _current_revision(self, request_key: str) -> Optional[int]:
        try:
            fresh = self.get_request(request_key)
        except WorkerError:
            return None
        revision = fresh.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            return None
        return int(revision)

    def _finish_failed(
        self,
        request_key: str,
        lease_token: str,
        result: dict[str, Any],
        code: Optional[str],
    ) -> dict[str, Any]:
        """回报 failed：只落有限稳定 error_code；丢响应先读同版本事实再判定。"""
        error_code = self._reportable(code)
        revision = self._current_revision(request_key)
        if revision is None:
            result["error_code"] = error_code
            return redact(result)
        report = self.report(
            request_key,
            lease_token=lease_token,
            expected_revision=revision,
            outcome="failed",
            error_code=error_code,
        )
        result["revision"] = revision
        if report["status"] == 200:
            result["outcome"] = "reported"
            result["error_code"] = error_code
            result["replayed"] = bool(report["payload"].get("replayed"))
            return redact(result)
        # 丢响应/代际冲突：只读重查事实；不改判成功，也不重试写。
        fresh = None
        try:
            fresh = self.get_request(request_key)
        except WorkerError:
            fresh = None
        result["report"] = {"status": report["status"], "error_code": report["error_code"]}
        if isinstance(fresh, Mapping) and fresh.get("status") == "failed":
            result["outcome"] = "reported"
            result["replayed"] = True
        else:
            result["outcome"] = "failed"
        result["error_code"] = error_code
        return redact(result)

    def _finish_provisioned(
        self, request_key: str, lease_token: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        """回报 provisioned：只有三步真实成功才算；409 不泛化成成功。"""
        revision = self._current_revision(request_key)
        if revision is None:
            result["outcome"] = "failed"
            result["error_code"] = "http_error"
            return redact(result)
        report = self.report(
            request_key,
            lease_token=lease_token,
            expected_revision=revision,
            outcome="provisioned",
            error_code=None,
        )
        result["revision"] = revision
        if report["status"] == 200:
            result["outcome"] = "provisioned"
            result["error_code"] = None
            result["replayed"] = bool(report["payload"].get("replayed"))
            return redact(result)
        # 先只读重查同版本事实，再受控续跑；绝不把 409/丢响应泛化成功。
        fresh = None
        try:
            fresh = self.get_request(request_key)
        except WorkerError:
            fresh = None
        if isinstance(fresh, Mapping) and fresh.get("status") == "provisioned":
            result["outcome"] = "provisioned"
            result["replayed"] = True
            result["error_code"] = None
            return redact(result)
        result["outcome"] = "failed"
        result["error_code"] = self._reportable(report["error_code"] or "http_error")
        result["report"] = {"status": report["status"]}
        return redact(result)

    # ── 循环 ─────────────────────────────────────────────────────────

    def plan(self) -> dict[str, Any]:
        """只读计划：不 claim、不写文件。"""
        self._begin_budget()
        try:
            rows = self.list_claimable()
        except WorkerStopped:
            return redact(
                {
                    "stage": "plan",
                    "outcome": "stopped",
                    "error_code": "worker_stopped",
                }
            )
        except WorkerError as exc:
            return redact({"stage": "plan", "outcome": "failed", "error_code": exc.code})
        planned = [
            {
                "request_key": row.get("request_key"),
                "kind": row.get("kind"),
                "status": row.get("status"),
                "effective_status": row.get("effective_status"),
                "revision": row.get("revision"),
                "attempts": row.get("attempts"),
                "member_id": row.get("member_id"),
                "claimable": row.get("claimable"),
                "retry_exhausted": row.get("retry_exhausted"),
            }
            for row in rows
        ]
        return redact(
            {
                "stage": "plan",
                "outcome": "planned",
                "count": len(planned),
                "requests": planned,
            }
        )

    def run_round(self) -> list[dict[str, Any]]:
        """一个轮次：发现 → 单请求处理。**始终**返回 ``list[dict]``，异常一律收敛。

        返修 F1/F5：``run_round`` 也是可执行入口，必须与 ``serve`` 同语义——

        - ``enabled=False``：零 HTTP、零文件/DB 写，只回 ``worker_disabled``；
        - ``apply=False``：只回**只读发现计划**，不 claim/create/rotate/ACK/report/建锁；
        - 发现失败/停止：同样返回 outcome **列表**，宿主不再按键名遍历或把字符串并进列表。
        """
        if not self.enabled:
            return [
                redact(
                    {
                        "stage": "disabled",
                        "outcome": "skipped",
                        "error_code": "worker_disabled",
                    }
                )
            ]
        if not self.apply:
            return [self.plan()]
        if self._stopping or self._stage_cancelled:
            return [
                redact(
                    {
                        "stage": "stopped",
                        "outcome": "stopped",
                        "error_code": "worker_stopped",
                    }
                )
            ]
        self._begin_budget(fresh=True)
        self._in_round = True
        try:
            try:
                rows = self.list_claimable()
            except WorkerStopped:
                return [
                    redact(
                        {
                            "stage": "stopped",
                            "outcome": "stopped",
                            "error_code": "worker_stopped",
                        }
                    )
                ]
            except WorkerError as exc:
                return [
                    redact(
                        {"stage": "discover", "outcome": "failed", "error_code": exc.code}
                    )
                ]
            except Exception:  # noqa: BLE001 - 配置 IO/超时绝不阻塞宿主控制循环
                return [
                    redact(
                        {
                            "stage": "discover",
                            "outcome": "failed",
                            "error_code": "http_error",
                        }
                    )
                ]
            outcomes: list[dict[str, Any]] = []
            for row in rows[:1]:
                request_key = str(row.get("request_key") or "")
                if not request_key:
                    continue
                outcomes.append(self.process(request_key))
            return outcomes
        finally:
            self._in_round = False
            self._end_budget()

    def serve(
        self, *, once: bool = False, max_rounds: Optional[int] = None
    ) -> dict[str, Any]:
        """worker 循环；默认关闭时零 HTTP/零写入。"""
        if not self.enabled:
            return redact(
                {
                    "schema": SCHEMA,
                    "mode": "disabled",
                    "enabled": False,
                    "applied": False,
                    "outcomes": [
                        {
                            "stage": "disabled",
                            "outcome": "skipped",
                            "error_code": "worker_disabled",
                        }
                    ],
                }
            )
        if not self.apply:
            return redact(
                {
                    "schema": SCHEMA,
                    "mode": "dry-run",
                    "enabled": True,
                    "applied": False,
                    "outcomes": coerce_outcomes(self.plan()),
                }
            )
        outcomes: list[dict[str, Any]] = []
        rounds = 0
        while True:
            rounds += 1
            outcomes.extend(coerce_outcomes(self.run_round()))
            if once or (max_rounds is not None and rounds >= max_rounds):
                break
            if self._stopping or self._stage_cancelled:
                break
            self._interruptible_sleep(self.poll_interval)
        return redact(
            {
                "schema": SCHEMA,
                "mode": "apply",
                "enabled": True,
                "applied": True,
                "rounds": rounds,
                "outcomes": outcomes,
            }
        )

    def _interruptible_sleep(self, seconds: float) -> None:
        remaining = max(0.0, float(seconds))
        while remaining > 0 and not (self._stopping or self._stage_cancelled):
            step = min(0.1, remaining)
            time.sleep(step)
            remaining -= step


# ---------------------------------------------------------------------------
# CLI（默认关闭；--apply 才真实写入）
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="角色请求 worker（R1-4b）：默认关闭 + 默认只读计划",
        allow_abbrev=False,
    )
    parser.add_argument("--project", required=True, help="目标 project_id（必填）")
    parser.add_argument("--host", default=None, help="显式宿主标签（默认主机名）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="TALK API 回环基址")
    parser.add_argument("--project-root", default=str(REPO_ROOT))
    parser.add_argument("--key-root", default=None, help="角色 Key 根（仓库之外；必填才写入）")
    parser.add_argument("--operator-key-file", default=None)
    parser.add_argument(
        "--enable",
        action="store_true",
        help="打开 worker（默认关闭；关闭时零 HTTP、零写入）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真实 claim/写入/回报（默认只读发现计划）",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument("--io-budget-seconds", type=float, default=DEFAULT_IO_BUDGET_SECONDS)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--discovery-limit", type=int, default=DEFAULT_DISCOVERY_LIMIT)
    parser.add_argument("--cli-executable", default=None)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):  # pragma: no cover
                pass
    args = build_parser().parse_args(argv)
    env = dict(os.environ)
    if args.operator_key_file:
        env["TALK_OPERATOR_KEY_FILE"] = args.operator_key_file
    try:
        worker = RoleProvisionWorker(
            project_id=args.project,
            host_label=args.host or socket.gethostname(),
            base_url=args.base_url,
            project_root=Path(args.project_root),
            key_root=Path(args.key_root) if args.key_root else None,
            enabled=bool(args.enable),
            apply=bool(args.apply),
            timeout_seconds=args.timeout_seconds,
            io_budget_seconds=args.io_budget_seconds,
            poll_interval=args.poll_interval,
            discovery_limit=args.discovery_limit,
            cli_executable=args.cli_executable,
            environ=env,
        )
    except WorkerError as exc:
        print(json.dumps({"schema": SCHEMA, "ok": False, "error_code": exc.code}))
        return EXIT_FAILED
    document = worker.serve(once=args.once, max_rounds=args.max_rounds)
    payload = {"schema": SCHEMA, "ok": True, **document}
    print(json.dumps(redact(payload), ensure_ascii=False, sort_keys=True))
    # 返修 F5：轮次结果统一为 ``list[dict]``；业务 failed 必须以非零退出码反映，
    # ``reported`` 表示失败结果已送达，也仍是业务失败；关闭/只读/停止保持 EXIT_OK。
    failed = any(
        str(item.get("outcome") or "") in ("failed", "reported")
        for item in coerce_outcomes(document.get("outcomes"))
    )
    return EXIT_FAILED if failed else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
