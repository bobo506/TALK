#!/usr/bin/env python3
"""宿主侧受管服务管理器（角色生命周期 R1-3，含首轮返修 F1–F6）。

本脚本是设计 §10.1 的“宿主侧服务管理器”：**它**负责 spawn/kill/等待就绪，并通过
§5.3 的 claim/report 协议领取动作、回报观测结果。TALK 服务端**不** spawn 进程。

明确入口
--------
- ``serve``     常驻管理器：轮询本项目 ``managed_cli`` 角色的 pending 动作并执行。
  **启动管理器本身不会启动任何角色**；只有人类在页面/API 上点过启动、确实产生 pending
  动作后才会被执行。服务端也不会隐式启动本管理器。**这是唯一会 spawn 子进程的入口**，
  因此受控子进程的生命周期始终由一个常驻进程持有。
- ``start`` / ``start-all``  只写**启动请求**（调用服务端意图写 API）并交常驻管理器承接，
  **不**在本进程内 spawn。常规 CLI 进程退出后不会留下无主受控进程。
- ``stop``      只写**关闭请求**（调用服务端意图写 API）并交常驻管理器承接。
- ``status``    只读状态（不返回任何 token）。

所有权与安全边界（返修 F2/F3/F4/F5）
------------------------------------
- 原 start 的 owner token、launch、project/member、host 与**活进程句柄**在本进程内关联
  持有；本地私有记录按 ``(project, member, launch)`` **逐启动**存放，**不**互相覆盖；
- stop 必须同时满足：本进程仍持有该动作的活句柄、磁盘记录与句柄逐字段一致、
  ``(pid, 真实进程创建时刻)`` 与 OS 事实一致、控制文件仍在本次私有根之内且非链接；
  任一条不成立 → ``unknown_owner``，**零写入、零停止、不清记录**；
- PID 只作诊断：没有活句柄时**绝不**用 PID/磁盘记录重新认领旧进程；
- 已 spawn 的失败/超时**保留**所有权记录与句柄；只有子进程被证明停止后才清记录；
- 私有记录用 R1-2 已验的 Windows 私有 ACL 原子发布（创建时带入 DACL + 回读核验），
  目录同样以私有 DACL 创建；默认状态根在用户私有目录（``~/.talk/role-service-host``），
  不再默认落在仓库工作区；
- 角色 Key 只以 ``--key-file``（路径）传入子进程；operator Key 只从环境/文件读取，
  **绝不**进 argv；owner/claim token 只留在管理器内存与私有记录里；
- 受管子进程的环境**不**整体继承 ``os.environ``：只放行系统必要变量，并把
  HOME/USERPROFILE/APPDATA/LOCALAPPDATA/XDG_*/TEMP 指向**本角色私有**目录，
  因此不同角色默认不共享原生会话/认证目录（未核验的原生认证目录一律不复制）。

入口兼容（返修 F1）
-------------------
- 内置运行器入口模板对**真实仓库入口**做解析核验：调用该模块真实的
  ``build_parser()`` + ``parse_args()``，证明模板 argv 能被真正会运行的原生入口接受，
  而不是只证明“Python 存在”；
- 精确 alias 只在真实入口确实有模型参数时才接入（``kimi-code`` 的 ``--kimi-model`` 会被
  ``bridges.kimi_bridge`` 转成真实 Kimi CLI 的 ``--model``）；真实入口没有模型参数
  （``codex``）或必须由本地登记命令承载（``dsh``/``cli``）时，**稳定禁用**并给出稳定
  错误码，绝不用 ``--model`` 猜参数、也不接受服务端下发的任意 shell 正文；
- 真实运行器能力**未验收**：内置模板还必须由人类用 ``--runtime-verified`` 显式登记才会
  被执行，否则稳定拒绝 ``runtime_unverified``。本片只用隔离固定文本 Python 子进程
  （``--cli-executable`` + 私有 ``--key-file``）证明协议闭环。
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import importlib
import io
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.role_provision import (  # noqa: E402 - 复用 R1-2 已验私有创建/路径/锁保护
    ProvisionError,
    _assert_root_chain_has_no_reparse,
    _is_reparse_point,
    _windows_build_private_security_attributes,
    _windows_publish_temp_file,
    _windows_verify_private_acl,
    acquire_lock,
    assert_inside_root,
    lock_path_for,
    profile_target_paths,
    release_lock,
)

SCHEMA = "talk-role-service-host-1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0
DEFAULT_READY_TIMEOUT_SECONDS = 60.0
DEFAULT_STOP_TIMEOUT_SECONDS = 20.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
#: R1-4b 返修 F2：worker 轮次在宿主退出时的**有界**收集窗口。
#: 主控制循环绝不 join 未结束的网络 IO；只在循环结束（once/上限/停止）后按 worker 自己的
#: 单轮 IO 预算 + 单次请求超时 + 余量收集一次，并对仍然卡住的轮次显式请求停止后收尾。
PROVISION_WORKER_SHUTDOWN_SLACK_SECONDS = 5.0
PROVISION_WORKER_SHUTDOWN_GRACE_CAP_SECONDS = 180.0
PROVISION_WORKER_SHUTDOWN_GRACE_DEFAULT_SECONDS = 30.0
#: 默认状态根在**用户私有目录**（与 R1-2 的 ``~/.talk/keys`` 同级），不落在仓库工作区。
DEFAULT_STATE_DIR = Path.home() / ".talk" / "role-service-host"

OPERATOR_KEY_ENV = "TALK_OPERATOR_API_KEY"
OPERATOR_KEY_FILE_ENV = "TALK_OPERATOR_KEY_FILE"
ROLE_KEY_ENV = "TALK_ROLE_API_KEY"
#: 宿主 → 受管子进程的优雅停止通道（控制文件路径；不用管道、不用 argv 传值）。
CONTROL_FILE_ENV = "TALK_ROLE_SERVICE_CONTROL_FILE"
#: 人类显式登记“已核对该运行器受管启动能力”的环境变量（逗号分隔；与 CLI 等价的本地登记）。
VERIFIED_RUNTIMES_ENV = "TALK_HOST_VERIFIED_RUNTIMES"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

#: 宿主认作**可信选择来源**的投影口径（ROLE_LEGACY_ATTACH_DESIGN §投影与宿主守卫）。
#: ``creation_operation`` = 本流程创建的新身份；``legacy_attach`` = 存量身份经 human-only
#: 补录接口登记、且补录映射与**当前绑定**六维精确相等。其余来源（``legacy_manual``、
#: ``creation_operation_mismatch``、``legacy_attach_mismatch``、未知/空值）继续稳定拒绝；
#: 本片只放宽来源口径，归档/绑定/能力/归属/所有权守卫逐项保持。
TRUSTED_CHOICE_SOURCES: frozenset[str] = frozenset(
    {"creation_operation", "legacy_attach"}
)

#: 受管子进程允许继承的**系统必要**变量白名单（其余一律不复制，尤其原生认证目录相关）。
CHILD_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "COMSPEC",
    "WINDIR",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "OS",
    "LANG",
    "LC_ALL",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "TZ",
)

#: 会被**本角色私有目录**覆盖的原生会话/缓存变量（不同角色默认隔离）。
NATIVE_HOME_ENV_VARS: tuple[str, ...] = (
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
    "TEMP",
    "TMP",
)

#: 公共输出白名单（严格白名单，而不是黑名单；未列出的键一律不进公共面）。
PUBLIC_KEYS: frozenset[str] = frozenset(
    {
        "schema",
        "ok",
        "mode",
        "result",
        "note",
        "executor",
        "roles",
        "project_id",
        "member_id",
        "role_name",
        "archived",
        "desired",
        "observed",
        "last_action",
        "last_result",
        "error_code",
        "error_message",
        "control_kind",
        "manager_kind",
        "generation",
        "current_launch",
        "observed_instance_id",
        "native_login",
        "model_alias",
        "readiness_service",
        "can_start",
        "can_stop",
        "ownership_held",
        "started_at",
        "stopped_at",
        "updated_at",
        "launch_id",
        "action",
        "state",
        "expected_instance_id",
        "launch_expires_at",
        "claimed_at",
        "reported_at",
        "outcome",
        "instance_id",
        "pid",
        "requested",
        "results",
        "counts",
        "started",
        "skipped",
        "failed",
        "status",
        "executed",
        "idempotent_stopped",
        "observed_state",
        "replayed",
        "entry_fingerprint",
        "runtime",
        "argv_checked",
        # R1-4b：请求 worker 的进度投影（仍是严格白名单；不含 Key/token/绝对私有路径）。
        "stage",
        "plan",
        "planned",
        "count",
        "requests",
        "request_key",
        "kind",
        "effective_status",
        "origin_operation_key",
        "credential_version",
        "lease_generation",
        "lease_config_version",
        "expires_at",
        "attempts",
        "claimable",
        "retry_exhausted",
        "steps",
        "ack",
        "job",
        "report",
        "reused",
        "rotation",
        "metadata_repaired",
        "key_published",
        "host_label",
        "worker_host",
        "rounds",
        "outcomes",
        "results",
    }
)


class HostError(RuntimeError):
    """稳定错误码 + 脱敏说明（绝不携带 Key/token/命令正文）。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sanitize_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:120] or "role"


# ---------------------------------------------------------------------------
# 真实 Windows 进程创建时刻（身份核对事实，不用 spawn 前 wall-clock）
# ---------------------------------------------------------------------------


def process_creation_time(pid: int) -> Optional[float]:
    """进程真实创建时刻（epoch 秒）；无法取得时返回 ``None``。

    Windows 用 ``OpenProcess`` + ``GetProcessTimes``（内核给出的创建 FILETIME），
    Linux 用 ``/proc/<pid>/stat`` 的 starttime 与 ``/proc/uptime``。该值是
    “实际进程创建证据”，刻意**不**使用 spawn 之前的 wall-clock。
    """
    if os.name == "nt":  # pragma: no cover - 平台相关，测试在 Windows 上实测
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetProcessTimes.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            kernel32.GetProcessTimes.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

            class _FileTime(ctypes.Structure):
                _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return None
            try:
                creation = _FileTime()
                exit_time = _FileTime()
                kernel = _FileTime()
                user = _FileTime()
                if not kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(creation),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel),
                    ctypes.byref(user),
                ):
                    return None
                ticks = (creation.high << 32) | creation.low
                return ticks / 10_000_000.0 - 11_644_473_600.0
            finally:
                kernel32.CloseHandle(handle)
        except Exception:  # pragma: no cover - 受限环境按“无 OS 证据”处理
            return None
    try:  # pragma: no cover - POSIX
        fields = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8").split()
        start_ticks = int(fields[21])
        hz = float(os.sysconf("SC_CLK_TCK"))
        uptime = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        boot = time.time() - uptime
        return boot + start_ticks / hz
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 私有根 / 目录 / 记录（复用 R1-2 已验私有创建，失败绝不降级）
# ---------------------------------------------------------------------------


def _windows_create_dir_with_private_acl(path: Path) -> None:
    """（保留给未来显式私有根）用 ``CreateDirectoryW`` + 私有 DACL 创建目录。

    本环境实测：以本机安全接口在**目录上**带私有 DACL 后，受限令牌下连子项都无法再
    创建（``ERROR_ACCESS_DENIED``），因此本片**不**依赖目录级私有 DACL；秘密只落在
    逐记录的私有 ACL 文件里（复用 R1-2 已验流程）。该函数保留以便人类在受支持的宿主
    上显式开启目录级私有 ACL 时复用，当前实现不调用它。
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p]
    kernel32.CreateDirectoryW.restype = wintypes.BOOL
    attributes, keepalive = _windows_build_private_security_attributes()
    try:
        ok = kernel32.CreateDirectoryW(str(path), ctypes.byref(attributes))
        error = ctypes.get_last_error()
    finally:
        del keepalive
    if not ok and error != 183:  # ERROR_ALREADY_EXISTS：已存在，交给调用方核验
        raise HostError("state_dir_insecure", "无法创建私有状态目录")


def ensure_private_dir(path: Path) -> Path:
    """创建目录并做**链接/逃逸守卫**；不写任何秘密，因此不要求目录级私有 DACL。

    秘密（owner token 等）只存在于 :meth:`OwnershipStore.save` 原子发布的**记录文件**里，
    那些文件用 R1-2 已验的 ``CreateFileW`` + 私有 DACL 创建并**回读核验**（见
    :func:`_publish_private_bytes`）。目录层只保证：自身/祖先不是符号链接、junction 或
    reparse point（绝不被重定向到公共面），POSIX 下权限位收 0700。
    """
    path = Path(path)
    if path.exists():
        if _is_reparse_point(path):
            raise HostError("state_dir_insecure", "状态路径是符号链接/junction/reparse point")
    else:
        parent = path.parent
        if parent == path:
            raise HostError("state_dir_insecure", "状态目录路径不合法")
        if not parent.exists():
            ensure_private_dir(parent)
        if os.name == "nt":
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                os.chmod(path, 0o700)
    if os.name != "nt":
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & 0o077:
            with contextlib.suppress(OSError):
                os.chmod(path, 0o700)
            mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & 0o077:
            raise HostError("state_dir_insecure", f"目录权限位 {oct(mode)} 不是私有")
    return path


def _publish_private_bytes(target: Path, payload: bytes) -> None:
    """原子发布一个私有权限文件（R1-2 已验流程：私有 ACL 临时文件 + 回读 + replace）。"""
    target = Path(target)
    ensure_private_dir(target.parent)
    if os.name == "nt":  # pragma: no cover - 平台相关
        temp_path = _windows_publish_temp_file(target, payload)
        try:
            os.replace(temp_path, target)
        except OSError as exc:
            with contextlib.suppress(OSError):
                os.remove(temp_path)
            raise HostError("storage_unavailable", "宿主拒绝私有记录原子发布") from exc
        try:
            written = target.read_bytes()
        except OSError as exc:
            with contextlib.suppress(OSError):
                os.remove(target)
            raise HostError("storage_unavailable", "私有记录回读失败") from exc
        if written != payload:
            with contextlib.suppress(OSError):
                os.remove(target)
            raise HostError("storage_unavailable", "私有记录回读不一致")
        ok, detail = _windows_verify_private_acl(target)
        if not ok:
            with contextlib.suppress(OSError):
                os.remove(target)
            raise HostError(
                "state_dir_insecure", f"私有记录 ACL 核验失败（{detail}）"
            )
        return
    handle_fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    temp_path = Path(temp_name)
    try:  # pragma: no cover - POSIX
        os.close(handle_fd)
        os.chmod(temp_path, 0o600)
        with open(temp_path, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except OSError as exc:
        with contextlib.suppress(OSError):
            temp_path.unlink()
        raise HostError("storage_unavailable", "写入私有记录失败") from exc


class OwnershipStore:
    """按 ``(project, member, launch)`` **逐启动**存放私有所有权记录。

    记录含本宿主自己持有的 owner token，因此必须落在私有 ACL 目录里；路径一律经
    R1-2 的根/链接/逃逸守卫，发布是加锁 + 原子 + 私有 ACL 回读核验。
    """

    def __init__(self, state_dir: Path):
        root = Path(state_dir).expanduser()
        _assert_root_chain_has_no_reparse(root)
        ensure_private_dir(root)
        self.state_dir = root.resolve()

    # ── 路径 ────────────────────────────────────────────────────────

    def _role_relative(self, project_id: str, member_id: str) -> Path:
        return Path("roles") / _sanitize_token(str(project_id)) / _sanitize_token(
            str(member_id)
        )

    def role_dir(self, project_id: str, member_id: str) -> Path:
        return ensure_private_dir(
            assert_inside_root(self.state_dir, self._role_relative(project_id, member_id))
        )

    def record_path(self, project_id: str, member_id: str, launch_id: str) -> Path:
        name = f"{_sanitize_token(str(launch_id))}.json"
        relative = self._role_relative(project_id, member_id) / name
        return assert_inside_root(self.state_dir, relative)

    def control_path(self, launch_id: str) -> Path:
        relative = Path("control") / f"{_sanitize_token(str(launch_id))}.ctl"
        return assert_inside_root(self.state_dir, relative)

    def native_home_dir(self, project_id: str, member_id: str) -> Path:
        relative = (
            Path("native")
            / _sanitize_token(str(project_id))
            / _sanitize_token(str(member_id))
        )
        return ensure_private_dir(assert_inside_root(self.state_dir, relative))

    # ── 读写 ────────────────────────────────────────────────────────

    def save(self, record: dict[str, Any]) -> Path:
        path = self.record_path(
            str(record["project_id"]), str(record["member_id"]), str(record["launch_id"])
        )
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
        handle = None
        try:
            handle = acquire_lock(lock_path_for(path))
        except ProvisionError as exc:
            raise HostError("ownership_lock_busy", "所有权记录被并发持有") from exc
        try:
            _publish_private_bytes(path, payload)
        finally:
            release_lock(lock_path_for(path), handle)
        return path

    def load(
        self, project_id: str, member_id: str, launch_id: str
    ) -> Optional[dict[str, Any]]:
        try:
            path = self.record_path(project_id, member_id, launch_id)
        except ProvisionError:
            return None
        if not path.exists() or _is_reparse_point(path):
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - 损坏按缺失处理
            return None

    def latest(self, project_id: str, member_id: str) -> Optional[dict[str, Any]]:
        """本角色最近一条记录（**只作诊断**；不能替代活句柄证明归属）。"""
        try:
            directory = assert_inside_root(
                self.state_dir, self._role_relative(project_id, member_id)
            )
        except (ProvisionError, OSError):
            return None
        if not directory.is_dir() or _is_reparse_point(directory):
            return None
        best: Optional[dict[str, Any]] = None
        best_key = ""
        try:
            candidates = sorted(directory.glob("*.json"))
        except OSError:  # pragma: no cover
            return None
        for candidate in candidates:
            if _is_reparse_point(candidate):
                continue
            try:
                record = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            key = str(record.get("created_at") or "")
            if best is None or key > best_key:
                best, best_key = record, key
        return best

    def clear(self, project_id: str, member_id: str, launch_id: str) -> None:
        try:
            path = self.record_path(project_id, member_id, launch_id)
        except ProvisionError:  # pragma: no cover - 非法 launch_id 不清理任何东西
            return
        if _is_reparse_point(path):
            return
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:  # pragma: no cover - 清理失败不掩盖成功停止事实
            pass


def redact(record: Any) -> Any:
    """公共输出：**严格白名单**（未列出的键一律丢弃），递归处理列表/字典。"""
    if isinstance(record, list):
        return [redact(item) for item in record]
    if isinstance(record, dict):
        return {k: redact(v) for k, v in record.items() if k in PUBLIC_KEYS}
    return record


def _coerce_worker_outcomes(raw: Any) -> list[dict[str, Any]]:
    """把 worker 轮次返回值收敛成 ``list[dict]``（返修 F5）。

    ``run_round`` 现在恒返回 ``list[dict]``；宿主仍做最后一道收敛，避免历史 dict 返回值被
    按键名遍历、字符串被逐个字符并进 outcomes、或非映射条目丢失错误形状。
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [dict(raw)]
    if isinstance(raw, (list, tuple)):
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(dict(item))
            else:
                out.append(
                    {"stage": "worker", "outcome": "failed", "error_code": "http_error"}
                )
        return out
    return [{"stage": "worker", "outcome": "failed", "error_code": "http_error"}]


# ---------------------------------------------------------------------------
# 真实仓库入口：模板 + 别名接线 + 真实 parser 解析核验（返修 F1）
# ---------------------------------------------------------------------------


class RuntimeRecipe:
    """一个运行器的**本地**受管入口配方（不含任何服务端下发正文）。"""

    __slots__ = ("module", "argv", "alias_flag", "command_flag", "command_required")

    def __init__(
        self,
        module: str,
        argv: Sequence[str],
        *,
        alias_flag: Optional[str] = None,
        command_flag: Optional[str] = None,
        command_required: bool = False,
    ):
        self.module = module
        self.argv = tuple(argv)
        self.alias_flag = alias_flag
        self.command_flag = command_flag
        self.command_required = command_required


#: runtime → 真实仓库入口配方。``alias_flag`` 只有真实 parser 确实接受模型参数时才非空；
#: 需要把 alias 放进**本地登记命令**的运行器用 ``command_flag``（``{model}`` 占位）。
RUNTIME_RECIPES: dict[str, RuntimeRecipe] = {
    "kimi-code": RuntimeRecipe(
        "bridges.kimi_bridge",
        ("{python}", "-m", "bridges.kimi_bridge"),
        alias_flag="--kimi-model",
    ),
    "codex": RuntimeRecipe(
        "bridges.codex_bridge",
        ("{python}", "-m", "bridges.codex_bridge"),
        command_flag="--codex-command",
        command_required=True,
    ),
    "dsh": RuntimeRecipe(
        "bridges.cli_bridge",
        ("{python}", "-m", "bridges.cli_bridge"),
        command_flag="--command",
        command_required=True,
    ),
    "cli": RuntimeRecipe(
        "bridges.cli_bridge",
        ("{python}", "-m", "bridges.cli_bridge"),
        command_flag="--command",
        command_required=True,
    ),
}
#: 兼容旧调用点：运行器 → 模型 alias 参数名。
RUNTIME_ALIAS_FLAGS: dict[str, str] = {
    name: recipe.alias_flag
    for name, recipe in RUNTIME_RECIPES.items()
    if recipe.alias_flag
}


def resolve_alias_flag(runtime: Optional[str], explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    recipe = RUNTIME_RECIPES.get(str(runtime or "").strip())
    if recipe is not None and recipe.alias_flag:
        return recipe.alias_flag
    return "--model"


def _python_executable() -> str:
    return getattr(sys, "_base_executable", None) or sys.executable


def runtime_module_file(recipe: RuntimeRecipe) -> Path:
    return REPO_ROOT / (recipe.module.replace(".", "/") + ".py")


def build_runtime_argv(
    runtime: str,
    *,
    model_alias: str,
    command_template: Optional[str] = None,
) -> list[str]:
    """组装**真实仓库入口**的 base argv（含精确 alias 接线）；不支持则稳定失败。

    - ``kimi-code``：``-m bridges.kimi_bridge --kimi-model <alias>``，该参数会被真实
      bridge 转成 Kimi CLI 的 ``--model <alias>``；
    - ``codex``：真实 parser **没有**模型参数，必须由本地登记的 ``--cli-command-template``
      承载 alias，否则 ``runtime_alias_unsupported``（绝不塞 ``--model`` 猜参数）；
    - ``dsh``/``cli``：真实 parser 要求 ``--command``，同样必须本地登记命令模板，
      否则 ``cli_command_unresolved``。
    """
    key = str(runtime or "").strip()
    recipe = RUNTIME_RECIPES.get(key)
    if recipe is None:
        raise HostError("cli_missing", "该运行器没有受管入口配方，需显式 --cli-executable")
    if not model_alias:
        raise HostError("model_alias_unresolved", "绑定未提供可用的模型 alias")
    resolved = [
        _python_executable() if part == "{python}" else part for part in recipe.argv
    ]
    if recipe.alias_flag:
        resolved += [recipe.alias_flag, model_alias]
    if recipe.command_required:
        template = str(command_template or "").strip()
        if not template:
            code = (
                "runtime_alias_unsupported"
                if recipe.command_flag == "--codex-command"
                else "cli_command_unresolved"
            )
            raise HostError(code, "该真实入口需要本地登记的命令模板才能接入模型 alias")
        if "{model}" not in template:
            raise HostError(
                "runtime_alias_unsupported", "本地命令模板缺少 {model} 占位，无法接入精确 alias"
            )
        resolved += [str(recipe.command_flag), template.replace("{model}", model_alias)]
    return resolved


def verify_runtime_entry(runtime: str, argv: Sequence[str]) -> str:
    """用**真实仓库入口**的 parser 解析核验 argv；返回入口指纹（模块路径 + sha256）。"""
    key = str(runtime or "").strip()
    recipe = RUNTIME_RECIPES.get(key)
    if recipe is None:
        raise HostError("cli_missing", "该运行器没有受管入口配方")
    module_file = runtime_module_file(recipe)
    if not module_file.is_file():
        raise HostError("cli_missing", "真实入口模块不存在")
    try:
        module = importlib.import_module(recipe.module)
    except Exception as exc:  # pragma: no cover - 依赖导入失败按入口不可用
        raise HostError("cli_missing", "真实入口模块无法导入") from exc
    builder = getattr(module, "build_parser", None)
    if not callable(builder):
        raise HostError("cli_incompatible", "真实入口没有 build_parser")
    if (
        len(argv) < 3
        or str(argv[0]) != _python_executable()
        or str(argv[1]) != "-m"
        or str(argv[2]) != recipe.module
    ):
        raise HostError("cli_incompatible", "受管 argv 必须以本解释器 + -m <真实入口模块> 开头")
    rest = [str(part) for part in argv[3:]]
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            builder().parse_args(rest)
    except SystemExit as exc:
        raise HostError(
            "cli_incompatible", "真实入口 parser 不接受该 argv（解析失败或缺少必填参数）"
        ) from exc
    digest = __import__("hashlib").sha256(
        module_file.read_bytes()
    ).hexdigest()[:16]
    return f"{recipe.module}@{digest}"


def parse_unit_count(argv: Sequence[str], runtime: str) -> int:
    """诊断用：真实 parser 解析后产生的属性个数（证明不是“只检查文件存在”）。"""
    recipe = RUNTIME_RECIPES[str(runtime or "").strip()]
    module = importlib.import_module(recipe.module)
    namespace = module.build_parser().parse_args([str(part) for part in argv[3:]])
    return len(vars(namespace))


# ---------------------------------------------------------------------------
# HTTP（只用标准库；Key 只进 header，绝不进 argv/日志）
# ---------------------------------------------------------------------------


class TalkHostClient:
    """最小的宿主 HTTP 客户端（``X-API-Key`` 鉴权）。"""

    def __init__(
        self,
        base_url: str,
        key: str,
        *,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self._key = key
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        body: Optional[dict[str, Any]] = None,
        *,
        key: Optional[str] = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        headers["X-API-Key"] = key or self._key
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    status = response.status
            except urllib.error.HTTPError as exc:
                # 错误响应的正文读取也可能超时/截断，须由外层统一处理。
                with exc:
                    raw = exc.read().decode("utf-8", errors="replace")
                    status = exc.code
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            # urlopen 不保证连接/读阶段均包装为 URLError；IncompleteRead
            # 也不属于 OSError。统一成可恢复的宿主错误，不暴露原始请求/Key。
            raise HostError("host_unreachable", "TALK API 不可达") from exc
        payload: Any = None
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
        if status >= 400:
            detail = ""
            if isinstance(payload, dict):
                detail = str(payload.get("detail") or "")
            raise HostError(detail or f"http_{status}", f"HTTP {status}")
        return payload if isinstance(payload, dict) else {"data": payload}


# ---------------------------------------------------------------------------
# 子进程 argv / spawn
# ---------------------------------------------------------------------------


def build_child_argv(
    base_argv: Sequence[str],
    *,
    member_id: str,
    key_file: Path,
    runtime: str,
    model_alias: str,
    alias_flag: Optional[str],
    instance_id: str,
    project_id: str,
    project_root: str,
    launch_id: str,
    process_started_at: datetime,
    base_url: str,
) -> list[str]:
    """受管子进程 argv：显式列表、无 shell、无明文 Key/token。

    ``model_alias`` 为空一律由调用方在**启动前**稳定失败（``model_alias_unresolved``）。
    ``alias_flag`` 为空表示 alias 已经由 :func:`build_runtime_argv` 接进真实入口，
    这里**不**再追加任何模型参数（防止给不认 ``--model`` 的真实入口塞参数）。
    """
    argv = [str(part) for part in base_argv]
    argv += [
        "--name",
        member_id,
        "--key-file",
        str(key_file),
        "--instance-id",
        instance_id,
        "--runtime",
        runtime,
        "--base-url",
        base_url,
        "--project",
        project_root,
        "--project-id",
        project_id,
        "--launch-id",
        launch_id,
        "--process-started-at",
        _iso(process_started_at) or "",
    ]
    if alias_flag:
        argv += [alias_flag, model_alias]
    return argv


def _hidden_startupinfo() -> Any:
    """Windows 隐藏窗口的 ``STARTUPINFO``（``SW_HIDE``）。

    刻意**不**用 ``CREATE_NO_WINDOW``：在本项目的受限宿主环境里该标志会让子进程
    以 ``0xC0000142``（DLL 初始化失败）立即退出（已用隔离探针实测），而
    ``STARTF_USESHOWWINDOW + SW_HIDE`` 同样不显示任何窗口且能正常启动。
    """
    if os.name != "nt":  # pragma: no cover - 平台相关
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


def spawn_hidden(
    argv: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    stdout_target: Any = subprocess.DEVNULL,
    stderr_target: Any = subprocess.DEVNULL,
) -> subprocess.Popen:
    """spawn 一个**隐藏窗口**的受控子进程（Windows 不开无关可见窗口）。

    标准通道默认全部走 ``DEVNULL``：受管启动**不**用管道捕获子进程输出，也不依赖
    stdin 下发指令。优雅停止通过**控制文件**通知子进程自行退出。
    """
    return subprocess.Popen(  # noqa: S603 - 列表 argv，无 shell
        list(argv),
        cwd=str(cwd) if cwd else None,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout_target,
        stderr=stderr_target,
        startupinfo=_hidden_startupinfo(),
    )


# ---------------------------------------------------------------------------
# 管理器
# ---------------------------------------------------------------------------


class PreflightFacts:
    """启动前核验过的事实（真实入口 argv、凭据、指纹、隔离子进程环境）。"""

    __slots__ = (
        "argv",
        "key_file",
        "entry_fingerprint",
        "binding_fingerprint",
        "profile_fingerprint",
        "child_env",
        "runtime",
    )

    def __init__(
        self,
        *,
        argv: list[str],
        key_file: Path,
        entry_fingerprint: str,
        binding_fingerprint: str,
        profile_fingerprint: str,
        child_env: dict[str, str],
        runtime: str,
    ):
        self.argv = argv
        self.key_file = key_file
        self.entry_fingerprint = entry_fingerprint
        self.binding_fingerprint = binding_fingerprint
        self.profile_fingerprint = profile_fingerprint
        self.child_env = child_env
        self.runtime = runtime


class HostManager:
    """受管服务的宿主执行者：claim → 执行 → report，并持有活进程句柄。"""

    def __init__(
        self,
        client: TalkHostClient,
        *,
        host: Optional[str] = None,
        state_dir: Optional[Path] = None,
        operator_key: Optional[str] = None,
        role_key_root: Optional[Path] = None,
        role_key_file: Optional[Path] = None,
        cli_executable: Optional[str] = None,
        cli_args: Optional[Sequence[str]] = None,
        cli_command_template: Optional[str] = None,
        alias_flag: Optional[str] = None,
        verified_runtimes: Optional[Sequence[str]] = None,
        child_env: Optional[dict[str, str]] = None,
        ready_timeout: float = DEFAULT_READY_TIMEOUT_SECONDS,
        stop_timeout: float = DEFAULT_STOP_TIMEOUT_SECONDS,
        project_root: Optional[Path] = None,
        child_log_dir: Optional[Path] = None,
    ):
        self.client = client
        self.host = host or socket.gethostname()
        self.store = OwnershipStore(state_dir or DEFAULT_STATE_DIR)
        self.operator_key = operator_key
        self.role_key_root = Path(role_key_root) if role_key_root else None
        self.role_key_file = Path(role_key_file) if role_key_file else None
        self.cli_executable = cli_executable
        self.cli_args = list(cli_args or [])
        self.cli_command_template = cli_command_template
        self.alias_flag = alias_flag
        self.verified_runtimes = {
            str(item).strip() for item in (verified_runtimes or []) if str(item).strip()
        }
        self.child_env_extra = {
            str(k): str(v) for k, v in (child_env or {}).items() if str(k)
        }
        self.ready_timeout = ready_timeout
        self.stop_timeout = stop_timeout
        self.project_root = Path(project_root) if project_root else REPO_ROOT
        self.child_log_dir = Path(child_log_dir) if child_log_dir else None
        self._handles: dict[str, dict[str, Any]] = {}

    # ── 凭据与入口 ──────────────────────────────────────────────────

    def role_key_path(self, member_id: str) -> Path:
        if self.role_key_file is not None:
            return self.role_key_file
        if self.role_key_root is None:
            raise HostError("role_key_missing", "缺少 --key-root 或 --role-key-file")
        try:
            from scripts.role_provision import key_file_path
        except Exception as exc:  # pragma: no cover - 依赖导入失败按凭据缺失处理
            raise HostError("role_key_missing", "无法解析角色 Key 路径") from exc
        return Path(key_file_path(self.role_key_root, member_id))

    def base_argv(self, runtime: Optional[str], model_alias: str) -> list[str]:
        """真实入口 base argv：显式 ``--cli-executable`` 优先，否则用真实配方。"""
        if self.cli_executable:
            executable = Path(self.cli_executable)
            if not executable.is_file():
                raise HostError("cli_missing", "显式 CLI 入口不是可执行文件")
            return [str(executable), *self.cli_args]
        return build_runtime_argv(
            str(runtime or ""),
            model_alias=model_alias,
            command_template=self.cli_command_template,
        )

    def _require_runtime_registered(self, runtime: str) -> None:
        """真实运行器的受管能力必须由人类在本机显式登记；未登记稳定拒绝。"""
        key = str(runtime or "").strip()
        if key not in RUNTIME_RECIPES:
            raise HostError("cli_missing", "该运行器没有受管入口配方")
        if key not in self.verified_runtimes:
            raise HostError(
                "runtime_unverified",
                "该运行器的真实受管启动能力未由人类显式核对登记",
            )

    def _role_facts(
        self, project_id: str, member_id: str, role_key: str, *, action: str
    ) -> dict[str, Any]:
        """核当前资格/绑定/creation choice 事实（真实 API，不用事务前缓存）。

        ``GET /api/projects/{id}/roles`` 的公开投影已经包含 runner/model/binding_state/
        creation choice 与本次 service 投影；这里要求逐项与本动作一致，任何缺失或不一致
        都稳定拒绝，绝不“只看 bound + control_kind 就放行”。
        """
        try:
            payload = self.client.request(
                "GET",
                f"/api/projects/{urllib.parse.quote(project_id)}/roles",
                key=role_key,
            )
        except HostError as exc:
            raise HostError("role_facts_unavailable", "无法读取项目角色事实") from exc
        rows = payload.get("data") if isinstance(payload, dict) else None
        row: Optional[dict[str, Any]] = None
        for item in rows or []:
            if isinstance(item, dict) and str(item.get("member_id")) == member_id:
                row = item
                break
        if row is None:
            raise HostError("role_facts_unavailable", "项目角色投影里没有该成员")
        if row.get("archived") is True:
            raise HostError("role_facts_unavailable", "角色已归档，不具备启动资格")
        binding_state = str(row.get("binding_state") or "")
        if not binding_state or binding_state != "bound":
            raise HostError("binding_fingerprint_mismatch", "角色绑定不是 bound 状态")
        model = row.get("model") if isinstance(row.get("model"), dict) else {}
        runner = row.get("runner") if isinstance(row.get("runner"), dict) else {}
        service = row.get("service") if isinstance(row.get("service"), dict) else {}
        choice_source = str(model.get("choice_source") or "")
        if not model.get("choice_id") or choice_source not in TRUSTED_CHOICE_SOURCES:
            raise HostError(
                "choice_unverified",
                "可信 choice 缺失、来源不受支持或已与当前绑定不一致",
            )
        if model.get("choice_binding_mismatch") is True:
            raise HostError("choice_unverified", "creation choice 与当前绑定不一致")
        if not service:
            raise HostError("role_facts_unavailable", "缺少服务投影，无法核当前资格")
        return {
            "member_id": member_id,
            "project_id": project_id,
            "archived": False,
            "runner": runner,
            "model": model,
            "service": service,
            "action": action,
        }

    def binding_fingerprint(
        self, facts: dict[str, Any], command: dict[str, Any]
    ) -> str:
        """绑定 + creation choice 的**精确指纹**（本动作放行的事实指纹）。"""
        model = facts.get("model") or {}
        runner = facts.get("runner") or {}
        payload = {
            "member_id": facts.get("member_id"),
            "project_id": facts.get("project_id"),
            "runner_id": runner.get("runner_id"),
            "runtime": runner.get("runtime"),
            "choice_id": model.get("choice_id"),
            "choice_source": model.get("choice_source"),
            "model_id": model.get("model_id"),
            "model_alias": model.get("model_alias"),
            "command_runner_id": command.get("runner_id"),
            "command_runtime": command.get("runtime"),
            "command_model_alias": command.get("model_alias"),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return __import__("hashlib").sha256(canonical.encode("utf-8")).hexdigest()

    def profile_fingerprint(self, member_id: str) -> str:
        """本人三档（IDENTITY/SOUL/USER）的存在性 + 内容指纹；缺一档即稳定拒绝。"""
        try:
            paths = profile_target_paths(self.project_root, member_id)
        except (ProvisionError, ValueError, OSError) as exc:
            raise HostError("profile_missing", "无法解析本人三档路径") from exc
        digest = __import__("hashlib").sha256()
        for kind in sorted(paths):
            path = Path(paths[kind])
            if not path.is_file() or _is_reparse_point(path):
                raise HostError("profile_missing", f"本人三档缺失或不是普通文件：{kind}")
            try:
                content = path.read_bytes()
            except OSError as exc:
                raise HostError("profile_missing", "本人三档不可读") from exc
            if not content.strip():
                raise HostError("profile_missing", f"本人三档内容为空：{kind}")
            digest.update(kind.encode("utf-8"))
            digest.update(b"\0")
            digest.update(content)
            digest.update(b"\0")
        return digest.hexdigest()

    def child_environment(self, project_id: str, member_id: str) -> dict[str, str]:
        """按角色隔离的子进程环境：白名单系统变量 + 本角色私有原生目录。"""
        env: dict[str, str] = {}
        for name in CHILD_ENV_ALLOWLIST:
            value = os.environ.get(name)
            if value:
                env[name] = value
        home = self.store.native_home_dir(project_id, member_id)
        for name in NATIVE_HOME_ENV_VARS:
            env[name] = str(home)
        env["TALK_ROLE_SERVICE_MANAGED"] = "1"
        env.update(self.child_env_extra)
        return env

    # ── 预检 ────────────────────────────────────────────────────────

    def preflight(
        self, command: dict[str, Any], member_id: str, *, project_id: str, action: str = "start"
    ) -> PreflightFacts:
        """启动前检查：Key 身份、真实入口、精确 binding/choice 指纹、本人三档、当前资格。

        只读；不做任何写入（私有原生目录除外），也不执行模型或访问生产资源。
        """
        key_file = self.role_key_path(member_id)
        if not key_file.is_file():
            raise HostError("identity_mismatch", "角色 Key 文件不存在")
        try:
            role_key = key_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise HostError("identity_mismatch", "角色 Key 文件不可读") from exc
        if not role_key:
            raise HostError("identity_mismatch", "角色 Key 文件为空")
        me = self.client.request("GET", "/api/members/me", key=role_key)
        if str(me.get("id") or "") != member_id:
            raise HostError("identity_mismatch", "角色 Key 与目标 member_id 不匹配")
        alias = str(command.get("model_alias") or "").strip()
        if not alias:
            raise HostError("model_alias_unresolved", "绑定未提供可用的模型 alias")
        runtime = str(command.get("runtime") or "").strip()
        if not self.cli_executable:
            # 真实运行器必须先由人类显式登记；未登记时**先**稳定拒绝，不进入入口组装。
            self._require_runtime_registered(runtime)
        base = self.base_argv(runtime, alias)
        if not self.cli_executable:
            entry_fingerprint = verify_runtime_entry(runtime, base)
        else:
            # 隔离固定文本能力：显式本地入口，只证明“入口文件真实存在且可执行”。
            if not Path(base[0]).is_file():
                raise HostError("cli_missing", "CLI 入口不可解析")
            entry_fingerprint = f"local:{Path(base[0]).name}"
        facts = self._role_facts(project_id, member_id, role_key, action=action)
        runner = facts.get("runner") or {}
        model = facts.get("model") or {}
        if str(runner.get("runner_id") or "") != str(command.get("runner_id") or ""):
            raise HostError("binding_fingerprint_mismatch", "绑定 runner 与本次动作不一致")
        if str(runner.get("runtime") or "") != runtime:
            raise HostError("binding_fingerprint_mismatch", "绑定 runtime 与本次动作不一致")
        if str(model.get("model_alias") or "") != alias:
            raise HostError("binding_fingerprint_mismatch", "绑定 alias 与本次动作不一致")
        return PreflightFacts(
            argv=base,
            key_file=key_file,
            entry_fingerprint=entry_fingerprint,
            binding_fingerprint=self.binding_fingerprint(facts, command),
            profile_fingerprint=self.profile_fingerprint(member_id),
            child_env=self.child_environment(project_id, member_id),
            runtime=runtime,
        )

    # ── 活句柄查找（所有权事实的唯一权威）────────────────────────────

    def _live_handles(self, project_id: str, member_id: str) -> list[tuple[str, dict[str, Any]]]:
        found: list[tuple[str, dict[str, Any]]] = []
        for launch_id, handle in self._handles.items():
            record = handle.get("record") or {}
            if (
                str(record.get("project_id")) == project_id
                and str(record.get("member_id")) == member_id
            ):
                found.append((launch_id, handle))
        return found

    def live_launch_id(self, project_id: str, member_id: str) -> Optional[str]:
        found = self._live_handles(project_id, member_id)
        if len(found) != 1:
            return None
        return found[0][0]

    # ── start ───────────────────────────────────────────────────────

    def execute_start(self, launch: dict[str, Any]) -> dict[str, Any]:
        """claim → 预检 → spawn → 等就绪 → report（严格四条件由服务端裁决）。"""
        launch_id = str(launch["launch_id"])
        project_id = str(launch["project_id"])
        member_id = str(launch["member_id"])

        # F2：本宿主仍持有同角色活进程时**不**领取新动作、**不**覆盖所有权。
        live = self._live_handles(project_id, member_id)
        if live:
            return {
                "launch_id": launch_id,
                "member_id": member_id,
                "outcome": "failed",
                "error_code": "ownership_unreleased",
            }

        response = self.client.request(
            "POST",
            f"/api/role-service-launches/{launch_id}/claim",
            {
                "host": self.host,
                "expected_instance_id": launch["expected_instance_id"],
            },
        )
        owner_token = str(response.get("owner_token") or "")
        claim_token = str(response.get("claim_token") or "")
        command = dict(response.get("command") or {})
        instance_id = str(response["expected_instance_id"])
        generation = int(launch["generation"])

        try:
            facts = self.preflight(
                command, member_id, project_id=project_id, action="start"
            )
            argv = build_child_argv(
                facts.argv,
                member_id=member_id,
                key_file=facts.key_file,
                runtime=facts.runtime,
                model_alias=str(command.get("model_alias") or ""),
                alias_flag=None if not self.cli_executable else self.alias_flag,
                instance_id=instance_id,
                project_id=project_id,
                project_root=str(command.get("project_root") or self.project_root),
                launch_id=launch_id,
                process_started_at=_utcnow(),
                base_url=self.client.base_url,
            )
        except HostError as exc:
            # 纯预检失败：**没有** spawn，`spawned=False` 让服务端安全释放所有权。
            self._report(
                launch_id,
                generation=generation,
                action="start",
                claim_token=claim_token,
                owner_token=owner_token,
                outcome="failed",
                instance_id=None,
                pid=None,
                process_started_at=None,
                error_code=exc.code,
                spawned=False,
            )
            return {
                "launch_id": launch_id,
                "member_id": member_id,
                "outcome": "failed",
                "error_code": exc.code,
            }

        control_file = self.store.control_path(launch_id)
        child_env = dict(facts.child_env)
        child_env[CONTROL_FILE_ENV] = str(control_file)
        stdout_target: Any = subprocess.DEVNULL
        stderr_target: Any = subprocess.DEVNULL
        opened: list[Any] = []
        if self.child_log_dir is not None:
            self.child_log_dir.mkdir(parents=True, exist_ok=True)
            name = _sanitize_token(launch_id)
            stdout_target = open(self.child_log_dir / f"{name}.out", "ab")
            stderr_target = open(self.child_log_dir / f"{name}.err", "ab")
            opened = [stdout_target, stderr_target]
        try:
            process = spawn_hidden(
                argv,
                cwd=self.project_root,
                env=child_env,
                stdout_target=stdout_target,
                stderr_target=stderr_target,
            )
        except OSError as exc:
            self._report(
                launch_id,
                generation=generation,
                action="start",
                claim_token=claim_token,
                owner_token=owner_token,
                outcome="failed",
                instance_id=None,
                pid=None,
                process_started_at=None,
                error_code="cli_missing",
                spawned=False,
            )
            return {
                "launch_id": launch_id,
                "member_id": member_id,
                "outcome": "failed",
                "error_code": "cli_missing",
            }
        finally:
            for stream in opened:
                with contextlib.suppress(OSError):
                    stream.close()

        # spawn 事实：pid 来自真实子进程；创建时刻优先取 OS 事实，取不到才退化为观测时刻。
        os_creation = process_creation_time(process.pid)
        created_at = _utcnow()
        source = "os" if os_creation is not None else "observed"
        started_wall = (
            datetime.fromtimestamp(os_creation, tz=timezone.utc)
            if os_creation is not None
            else created_at
        )
        record = {
            "project_id": project_id,
            "member_id": member_id,
            "launch_id": launch_id,
            "owner_token": owner_token,
            "host": self.host,
            "pid": process.pid,
            "process_started_at": _iso(started_wall),
            "process_identity_source": source,
            "instance_id": instance_id,
            "runtime": facts.runtime,
            "control_file": str(control_file),
            "entry_fingerprint": facts.entry_fingerprint,
            "binding_fingerprint": facts.binding_fingerprint,
            "profile_fingerprint": facts.profile_fingerprint,
            "created_at": _iso(created_at),
        }
        # 先登记活句柄（内存是所有权权威），再落私有记录：
        # 落盘失败也**不会**丢句柄，更不会留下无失败报告的无主子进程。
        self._handles[launch_id] = {
            "process": process, "record": record, "record_persisted": False
        }
        try:
            self.store.save(record)
            self._handles[launch_id]["record_persisted"] = True
        except (HostError, OSError, ProvisionError) as exc:
            error_code = exc.code if isinstance(exc, HostError) else "storage_unavailable"
            stopped = self._abort_spawned_child(process, control_file)
            if stopped:
                self._report(
                    launch_id,
                    generation=generation,
                    action="start",
                    claim_token=claim_token,
                    owner_token=owner_token,
                    outcome="failed",
                    instance_id=None,
                    pid=None,
                    process_started_at=None,
                    error_code=error_code,
                    spawned=False,
                )
                # 回报被确认后才丢弃原句柄；网络失败时保留已退出的原进程证明，
                # 后续仍可领取关闭动作并释放服务端归属。
                self._handles.pop(launch_id, None)
                self.store.clear(project_id, member_id, launch_id)
                return {
                    "launch_id": launch_id,
                    "member_id": member_id,
                    "outcome": "failed",
                    "error_code": error_code,
                }
            # 子进程仍存活：保留句柄与失败报告（服务端据此保留所有权、允许 stop）。
            self._report(
                launch_id,
                generation=generation,
                action="start",
                claim_token=claim_token,
                owner_token=owner_token,
                outcome="failed",
                instance_id=None,
                pid=process.pid,
                process_started_at=started_wall,
                error_code=error_code,
                spawned=True,
            )
            return {
                "launch_id": launch_id,
                "member_id": member_id,
                "outcome": "failed",
                "error_code": error_code,
            }

        try:
            self._wait_ready(instance_id, project_id, member_id)
        except HostError as exc:
            # 超时/失败**不**杀子进程：保留句柄与所有权记录，等人类显式 stop。
            self._report(
                launch_id,
                generation=generation,
                action="start",
                claim_token=claim_token,
                owner_token=owner_token,
                outcome="failed",
                instance_id=None,
                pid=process.pid,
                process_started_at=started_wall,
                error_code=exc.code,
                spawned=True,
            )
            return {
                "launch_id": launch_id,
                "member_id": member_id,
                "outcome": "failed",
                "error_code": exc.code,
            }

        self._report(
            launch_id,
            generation=generation,
            action="start",
            claim_token=claim_token,
            owner_token=owner_token,
            outcome="ready",
            instance_id=instance_id,
            pid=process.pid,
            process_started_at=started_wall,
            error_code=None,
            spawned=True,
        )
        return {
            "launch_id": launch_id,
            "member_id": member_id,
            "instance_id": instance_id,
            "pid": process.pid,
            "outcome": "ready",
        }

    def _wait_ready(
        self, instance_id: str, project_id: str, member_id: str
    ) -> bool:
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            payload = self.client.request(
                "GET",
                f"/api/instances?member_id={urllib.parse.quote(member_id)}"
                f"&project_id={urllib.parse.quote(project_id)}",
            )
            rows = payload.get("data")
            if isinstance(rows, list):
                for row in rows:
                    if (
                        isinstance(row, dict)
                        and str(row.get("id")) == instance_id
                        and str(row.get("status")) in ("idle", "busy")
                    ):
                        return True
            time.sleep(0.2)
        raise HostError("readiness_timeout", "子进程未在期限内上报本次预分配实例")

    def _abort_spawned_child(self, process: subprocess.Popen, control_file: Path) -> bool:
        """尽力优雅停掉“落盘失败”的刚 spawn 子进程；成功返回 ``True``。"""
        with contextlib.suppress(HostError, OSError, ProvisionError):
            payload = b"shutdown\n"
            _publish_private_bytes(control_file, payload)
        if os.name != "nt":
            with contextlib.suppress(OSError):
                process.terminate()
        try:
            process.wait(timeout=self.stop_timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    # ── stop ────────────────────────────────────────────────────────

    def _identity_evidence(
        self, launch: dict[str, Any], record: dict[str, Any], handle: dict[str, Any]
    ) -> Optional[str]:
        """核对活句柄 + 磁盘记录 + OS 事实；不一致返回稳定错误码，一致返回 ``None``。

        **不做任何写入**：只要这里返回错误码，调用方必须零写入、零停止、不清记录。
        """
        project_id = str(launch["project_id"])
        member_id = str(launch["member_id"])
        process = handle.get("process")
        if process is None or not isinstance(process, subprocess.Popen):
            return "unknown_owner"
        handle_record = handle.get("record") or {}
        try:
            record_path = self.store.record_path(
                project_id, member_id, str(handle_record.get("launch_id"))
            )
            disk = self.store.load(project_id, member_id, str(handle_record.get("launch_id")))
        except (ProvisionError, OSError, ValueError):
            return "unknown_owner"
        if disk is None:
            # 只允许本管理器明确记录的发布失败使用原内存事实；成功发布后
            # 文件被删除、不可读或被替换仍按未知归属处理，不能静默降级。
            if handle.get("record_persisted", True):
                return "unknown_owner"
            try:
                if record_path.exists() or _is_reparse_point(record_path):
                    return "unknown_owner"
            except OSError:
                return "unknown_owner"
            disk = handle_record
        # 磁盘记录只允许与不可变活句柄事实**逐字段一致**；任何被改动的记录都不被信任。
        immutable = (
            "launch_id",
            "project_id",
            "member_id",
            "host",
            "pid",
            "instance_id",
            "control_file",
            "process_started_at",
            "owner_token",
        )
        for field in immutable:
            if str(disk.get(field)) != str(handle_record.get(field)):
                return "unknown_owner"
        if str(record.get("launch_id")) != str(handle_record.get("launch_id")):
            return "unknown_owner"
        if str(record.get("project_id")) != project_id:
            return "unknown_owner"
        if str(record.get("member_id")) != member_id:
            return "unknown_owner"
        if str(record.get("host") or "") != self.host:
            return "unknown_owner"
        if int(record.get("pid") or 0) != int(process.pid):
            return "unknown_owner"
        # 控制文件必须是本次私有根内、由本宿主推导出的路径（不可被磁盘记录改写）。
        try:
            expected_control = self.store.control_path(str(handle_record.get("launch_id")))
            actual_control = Path(str(record.get("control_file"))).resolve()
        except (ProvisionError, OSError, ValueError):
            return "unknown_owner"
        if actual_control != expected_control or _is_reparse_point(expected_control):
            return "unknown_owner"
        if process.poll() is not None:
            return None
        # 实际进程创建时刻：OS 事实优先；记录来源为 os 时必须可复核且一致。
        os_creation = process_creation_time(process.pid)
        recorded = _parse_iso(record.get("process_started_at"))
        if str(record.get("process_identity_source")) == "os":
            if os_creation is None or recorded is None:
                return "unknown_owner"
            if abs(os_creation - recorded.timestamp()) > 2.0:
                return "unknown_owner"
        return None

    def execute_stop(self, launch: dict[str, Any]) -> dict[str, Any]:
        """claim（须原 owner token + 原 host）→ 活句柄身份核对 → 优雅停止 → report。"""
        launch_id = str(launch["launch_id"])
        project_id = str(launch["project_id"])
        member_id = str(launch["member_id"])
        found = self._live_handles(project_id, member_id)
        if len(found) != 1:
            # 无活句柄/句柄歧义：无法证明归属 → 不认领、不写控制文件、不 kill、不清记录。
            return {
                "launch_id": launch_id,
                "member_id": member_id,
                "outcome": "failed",
                "error_code": "unknown_owner",
            }
        original_launch_id, handle = found[0]
        record = handle.get("record") or {}
        failure = self._identity_evidence(launch, record, handle)
        if failure is not None:
            return {
                "launch_id": launch_id,
                "member_id": member_id,
                "outcome": "failed",
                "error_code": failure,
            }
        process = handle["process"]
        generation = int(launch["generation"])
        started_at = _parse_iso(record.get("process_started_at"))

        if process.poll() is not None:
            # 进程已自行退出：仍按“宿主记录 + 已死”证明停止（claim 拿新 claim_token）。
            self._report(
                launch_id,
                generation=generation,
                action="stop",
                claim_token=self._claim_stop(launch_id, record),
                owner_token=str(record["owner_token"]),
                outcome="stopped",
                instance_id=None,
                pid=int(record["pid"]),
                process_started_at=started_at,
                error_code=None,
                spawned=True,
            )
            self._handles.pop(original_launch_id, None)
            self.store.clear(project_id, member_id, original_launch_id)
            return {"launch_id": launch_id, "member_id": member_id, "outcome": "stopped"}

        claim_token = self._claim_stop(launch_id, record)
        control_file = self.store.control_path(original_launch_id)
        graceful = self._graceful_stop(process, control_file)
        if not graceful:
            # 超时显式失败：不强杀，所有权记录与句柄继续保留。
            self._report(
                launch_id,
                generation=generation,
                action="stop",
                claim_token=claim_token,
                owner_token=str(record["owner_token"]),
                outcome="failed",
                instance_id=None,
                pid=int(record["pid"]),
                process_started_at=started_at,
                error_code="stop_timeout",
                spawned=True,
            )
            return {
                "launch_id": launch_id,
                "member_id": member_id,
                "outcome": "failed",
                "error_code": "stop_timeout",
            }
        self._report(
            launch_id,
            generation=generation,
            action="stop",
            claim_token=claim_token,
            owner_token=str(record["owner_token"]),
            outcome="stopped",
            instance_id=None,
            pid=int(record["pid"]),
            process_started_at=started_at,
            error_code=None,
            spawned=True,
        )
        self._handles.pop(original_launch_id, None)
        self.store.clear(project_id, member_id, original_launch_id)
        return {"launch_id": launch_id, "member_id": member_id, "outcome": "stopped"}

    def _claim_stop(self, launch_id: str, record: dict[str, Any]) -> str:
        response = self.client.request(
            "POST",
            f"/api/role-service-launches/{launch_id}/claim",
            {
                "host": str(record["host"]),
                "expected_instance_id": str(record["instance_id"]),
                "owner_token": str(record["owner_token"]),
            },
        )
        return str(response.get("claim_token") or "")

    def _graceful_stop(self, process: subprocess.Popen, control_file: Path) -> bool:
        """请求子进程自行退出；超时返回 ``False``（**不**强杀、不留无主进程）。"""
        control_file = Path(control_file)
        try:
            # 控制文件严格限制在本次私有状态根内，且发布本身带私有 ACL 核验。
            assert_inside_root(self.store.state_dir, control_file.relative_to(self.store.state_dir))
            _publish_private_bytes(control_file, b"shutdown\n")
        except (ProvisionError, HostError, ValueError, OSError):
            pass
        if os.name != "nt":
            with contextlib.suppress(OSError):
                process.terminate()
        try:
            process.wait(timeout=self.stop_timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    # ── report ──────────────────────────────────────────────────────

    def _report(
        self,
        launch_id: str,
        *,
        generation: int,
        action: str,
        claim_token: str,
        owner_token: str,
        outcome: str,
        instance_id: Optional[str],
        pid: Optional[int],
        process_started_at: Optional[datetime],
        error_code: Optional[str],
        spawned: Optional[bool] = None,
    ) -> dict[str, Any]:
        return self.client.request(
            "POST",
            f"/api/role-service-launches/{launch_id}/report",
            {
                "generation": generation,
                "action": action,
                "claim_token": claim_token,
                "owner_token": owner_token,
                "outcome": outcome,
                "instance_id": instance_id,
                "pid": pid,
                "process_started_at": _iso(process_started_at),
                "host": self.host,
                "error_code": error_code,
                "spawned": spawned,
            },
        )

    # ── 批量与常驻 ──────────────────────────────────────────────────

    def status(self, project_id: str) -> list[dict[str, Any]]:
        payload = self.client.request(
            "GET", f"/api/projects/{project_id}/role-services"
        )
        rows = payload.get("data")
        return rows if isinstance(rows, list) else []

    def request_start(self, project_id: str, member_id: str) -> dict[str, Any]:
        """只写启动请求（意图写），**不** spawn；由常驻管理器承接执行。"""
        return self.client.request(
            "POST",
            f"/api/projects/{project_id}/roles/{urllib.parse.quote(member_id)}/service/start",
        )

    def request_stop(self, project_id: str, member_id: str) -> dict[str, Any]:
        """只写关闭请求（意图写），**不** spawn；由常驻管理器承接执行。"""
        return self.client.request(
            "POST",
            f"/api/projects/{project_id}/roles/{urllib.parse.quote(member_id)}/service/stop",
        )

    def start_all(
        self, project_id: str, member_ids: Optional[Sequence[str]] = None
    ) -> dict[str, Any]:
        """只写批量启动请求（意图写），**不** spawn；返回服务端的逐角色请求结果。"""
        body: dict[str, Any] = {}
        if member_ids is not None:
            body["member_ids"] = list(member_ids)
        payload = self.client.request(
            "POST", f"/api/projects/{project_id}/role-services/start-all", body
        )
        payload["executor"] = "serve"
        payload["note"] = "启动请求已写入；由常驻管理器 serve 承接执行，本进程不 spawn。"
        return payload

    def claimable_actions(self, project_id: str) -> list[dict[str, Any]]:
        """只读取待领取动作：启动核当前分类，关闭保留原进程释放路径。"""
        actions: list[dict[str, Any]] = []
        for row in self.status(project_id):
            current = row.get("current_launch")
            if not isinstance(current, dict) or current.get("state") != "pending":
                continue
            # 新启动受当前分类限制；关闭必须仍能释放原 start 的进程。
            # 分类变化不会撤销原宿主持有的活句柄与 owner 证明。
            if current.get("action") != "stop" and str(row.get("control_kind") or "") != "managed_cli":
                continue
            actions.append(
                {
                    "launch_id": current.get("launch_id"),
                    "project_id": project_id,
                    "member_id": row.get("member_id"),
                    "generation": row.get("generation"),
                    "expected_instance_id": current.get("expected_instance_id"),
                    "action": current.get("action"),
                }
            )
        return actions

    def _start_worker_round(self, provision_worker: Any) -> tuple[Any, dict[str, Any]]:
        """独立受控线程里跑一轮 worker：同一请求串行、绝不与下一轮重叠（返修 F2）。"""
        box: dict[str, Any] = {"outcomes": None}

        def run() -> None:
            try:
                raw = provision_worker.run_round()
            except Exception:  # noqa: BLE001 - 配置 IO/超时不得阻塞服务控制循环
                raw = [{"stage": "worker", "outcome": "failed", "error_code": "http_error"}]
            box["outcomes"] = _coerce_worker_outcomes(raw)

        thread = threading.Thread(
            target=run, name="role-provision-worker", daemon=True
        )
        thread.start()
        return thread, box

    def _collect_worker_round(
        self, thread: Any, box: dict[str, Any], *, grace: float
    ) -> Optional[list[dict[str, Any]]]:
        """有界收集一轮 worker 结果：未结束返回 ``None``，绝不无限等待。"""
        if thread is None:
            return None
        thread.join(max(0.0, float(grace)))
        if thread.is_alive():
            return None
        return box.get("outcomes")

    def _worker_shutdown_grace(self, provision_worker: Any) -> float:
        """退出收集窗口 = worker 单轮 IO 预算 + 单次请求超时 + 余量（有上限）。"""
        def _positive(value: Any, fallback: float) -> float:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return fallback
            return number if number > 0 else fallback

        budget = _positive(
            getattr(provision_worker, "io_budget_seconds", None),
            PROVISION_WORKER_SHUTDOWN_GRACE_DEFAULT_SECONDS,
        )
        timeout = _positive(getattr(provision_worker, "timeout_seconds", None), 0.0)
        return min(
            budget + timeout + PROVISION_WORKER_SHUTDOWN_SLACK_SECONDS,
            PROVISION_WORKER_SHUTDOWN_GRACE_CAP_SECONDS,
        )

    def serve(
        self,
        project_id: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        once: bool = False,
        max_rounds: Optional[int] = None,
        provision_worker: Any = None,
    ) -> list[dict[str, Any]]:
        """常驻管理循环。**启动它本身不会启动任何角色**，只执行已经存在的 pending 动作。

        R1-4b：可选的请求 worker（默认 ``None`` = 关闭）在同一循环里推进，但它

        - 在**独立受控线程**里跑整轮（返修 F2）：慢网络 IO 不会阻塞本循环继续 poll/执行
          ``stop``/阶段取消；同一时刻最多一轮在飞，绝不重叠领取；
        - **不共享**本管理器的 Popen 句柄/所有权，也不捕获 ``BaseException``；
        - 任何配置 IO 失败或超时都被收敛成 outcome 列表（返修 F1/F5），绝不影响服务控制
          循环；循环结束时按有界窗口收集，仍卡住则显式请求停止并如实记录。
        """
        outcomes: list[dict[str, Any]] = []
        rounds = 0
        worker_thread: Any = None
        worker_box: dict[str, Any] = {}
        while True:
            rounds += 1
            try:
                actions = self.claimable_actions(project_id)
            except (HostError, OSError, http.client.HTTPException) as exc:
                # 服务端重载或暂时断连不能使宿主退出并丢失其它角色的活句柄。
                # 连续同一读错误只保留一次，继续原管理循环等待恢复。
                error_code = exc.code if isinstance(exc, HostError) else "host_unreachable"
                failure = {"action": "poll", "outcome": "failed", "error_code": error_code}
                if not outcomes or outcomes[-1] != failure:
                    outcomes.append(failure)
                actions = []
            for action in actions:
                try:
                    if action.get("action") == "stop":
                        outcomes.append(self.execute_stop(action))
                    else:
                        outcomes.append(self.execute_start(action))
                except (HostError, OSError, http.client.HTTPException) as exc:
                    outcomes.append(
                        {
                            "launch_id": action.get("launch_id"),
                            "member_id": action.get("member_id"),
                            "outcome": "failed",
                            "error_code": exc.code if isinstance(exc, HostError) else "host_unreachable",
                        }
                    )
            if provision_worker is not None:
                # 先**非阻塞**收上一轮（grace=0 只在已结束时取回），再决定是否开新一轮。
                finished = self._collect_worker_round(worker_thread, worker_box, grace=0.0)
                if finished is not None:
                    outcomes.extend(self._tag_worker_outcomes(finished))
                    worker_thread, worker_box = None, {}
                if worker_thread is None:
                    worker_thread, worker_box = self._start_worker_round(provision_worker)
            if once or (max_rounds is not None and rounds >= max_rounds):
                break
            time.sleep(poll_interval)
        if provision_worker is not None and worker_thread is not None:
            self._finish_worker_round(provision_worker, worker_thread, worker_box, outcomes)
        return outcomes

    def _tag_worker_outcomes(
        self, items: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        tagged: list[dict[str, Any]] = []
        for item in items:
            entry = dict(item)
            entry["action"] = "provision-worker"
            tagged.append(entry)
        return tagged

    def _finish_worker_round(
        self,
        provision_worker: Any,
        thread: Any,
        box: dict[str, Any],
        outcomes: list[dict[str, Any]],
    ) -> None:
        """退出时的有界收尾：先给足预算；仍卡住则请求停止后再等一个窗口。"""
        grace = self._worker_shutdown_grace(provision_worker)
        finished = self._collect_worker_round(thread, box, grace=grace)
        if finished is None:
            stop = getattr(provision_worker, "request_stop", None)
            if callable(stop):
                with contextlib.suppress(Exception):
                    stop()
            finished = self._collect_worker_round(thread, box, grace=grace)
        if finished is None:
            outcomes.append(
                {
                    "action": "provision-worker",
                    "stage": "worker",
                    "outcome": "stopped",
                    "error_code": "worker_stopped",
                    "note": "退出时该轮仍未结束；已请求停止，绝不 join 未结束网络 IO",
                }
            )
            return
        outcomes.extend(self._tag_worker_outcomes(finished))


# ---------------------------------------------------------------------------
# 凭据来源
# ---------------------------------------------------------------------------


def load_operator_key(explicit: Optional[str], env: dict[str, str]) -> str:
    """operator Key 来源：环境变量或 Key 文件。

    ``explicit`` 仅供**程序内嵌入方/测试**直接传入；CLI 永远不提供明文 argv 通道
    （``--operator-key`` 已被移除）。
    """
    if explicit:
        return explicit
    env_key = str(env.get(OPERATOR_KEY_ENV) or "").strip()
    if env_key:
        return env_key
    key_file = str(env.get(OPERATOR_KEY_FILE_ENV) or "").strip()
    if key_file:
        try:
            value = Path(key_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise HostError("operator_key_missing", "operator Key 文件不可读") from exc
        if value:
            return value
    raise HostError("operator_key_missing", "缺少 operator Key（env 或 --operator-key-file）")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TALK 受管服务宿主管理器（角色生命周期 R1-3）",
        # 关闭前缀缩写：`--operator-key` 不得被当成 `--operator-key-file` 的缩写而接受，
        # 否则明文 Key 会从 argv 通道回到命令行（返修 F4）。
        allow_abbrev=False,
    )
    parser.add_argument(
        "mode",
        choices=("start", "stop", "start-all", "status", "serve"),
        help="serve=唯一执行者；start/stop/start-all=只写请求并交 serve 执行；status=只读",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--project", default=None, help="目标 project_id")
    parser.add_argument("--member", default=None, help="目标 member_id（start/stop）")
    parser.add_argument(
        "--members",
        default=None,
        help="逗号分隔的 member_id 子集（start-all 只重试失败子集时使用）",
    )
    parser.add_argument("--host", default=None, help="宿主稳定标识（默认主机名）")
    parser.add_argument("--operator-key-file", default=None)
    parser.add_argument("--key-root", default=None, help="角色 Key 根（仓库之外）")
    parser.add_argument("--role-key-file", default=None, help="单角色 Key 文件覆盖")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--project-root", default=str(REPO_ROOT))
    parser.add_argument("--cli-executable", default=None)
    parser.add_argument("--cli-arg", action="append", default=None)
    parser.add_argument(
        "--cli-command-template",
        default=None,
        help="本地登记的入口命令模板（必须含 {model}），用于 codex/dsh 这类无模型参数的入口",
    )
    parser.add_argument("--alias-flag", default=None)
    parser.add_argument(
        "--runtime-verified",
        action="append",
        default=None,
        help="人类显式登记“已核对该运行器受管启动能力”；可重复",
    )
    parser.add_argument(
        "--child-env",
        action="append",
        default=None,
        help="显式追加给受管子进程的 KEY=VALUE（其余环境不继承）",
    )
    parser.add_argument("--ready-timeout", type=float, default=DEFAULT_READY_TIMEOUT_SECONDS)
    parser.add_argument("--stop-timeout", type=float, default=DEFAULT_STOP_TIMEOUT_SECONDS)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    # R1-4b：默认关闭的请求 worker（只接线，不改变服务语义；不 spawn 角色 CLI）。
    parser.add_argument(
        "--provision-worker",
        action="store_true",
        help="在 serve 循环内接线默认关闭的角色请求 worker",
    )
    parser.add_argument(
        "--provision-worker-apply",
        action="store_true",
        help="worker 真实领取/写入/回报（默认只读发现计划）",
    )
    parser.add_argument(
        "--provision-worker-max-rounds",
        type=int,
        default=None,
        help="仅用于受限运行：serve 循环与 worker 轮次共用的上限",
    )
    parser.add_argument("--provision-worker-io-budget-seconds", type=float, default=None)
    parser.add_argument("--provision-worker-discovery-limit", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def _parse_child_env(values: Optional[Sequence[str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values or []:
        text = str(raw)
        if "=" not in text:
            continue
        name, _, value = text.partition("=")
        name = name.strip()
        if name:
            out[name] = value
    return out


def _verified_runtimes(values: Optional[Sequence[str]], env: dict[str, str]) -> list[str]:
    out = [str(item).strip() for item in (values or []) if str(item).strip()]
    extra = str(env.get(VERIFIED_RUNTIMES_ENV) or "")
    out += [part.strip() for part in extra.split(",") if part.strip()]
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        operator_key = load_operator_key(
            None,
            {
                OPERATOR_KEY_ENV: os.environ.get(OPERATOR_KEY_ENV, ""),
                OPERATOR_KEY_FILE_ENV: args.operator_key_file
                or os.environ.get(OPERATOR_KEY_FILE_ENV, ""),
            },
        )
    except HostError as exc:
        print(json.dumps({"schema": SCHEMA, "ok": False, "error_code": exc.code}))
        return EXIT_FAILED
    if not args.project:
        print(json.dumps({"schema": SCHEMA, "ok": False, "error_code": "project_required"}))
        return EXIT_USAGE

    client = TalkHostClient(args.base_url, operator_key)
    try:
        manager = HostManager(
            client,
            host=args.host,
            state_dir=Path(args.state_dir),
            operator_key=operator_key,
            role_key_root=Path(args.key_root) if args.key_root else None,
            role_key_file=Path(args.role_key_file) if args.role_key_file else None,
            cli_executable=args.cli_executable,
            cli_args=args.cli_arg,
            cli_command_template=args.cli_command_template,
            alias_flag=args.alias_flag,
            verified_runtimes=_verified_runtimes(args.runtime_verified, os.environ),
            child_env=_parse_child_env(args.child_env),
            ready_timeout=args.ready_timeout,
            stop_timeout=args.stop_timeout,
            project_root=Path(args.project_root),
        )
    except HostError as exc:
        print(json.dumps({"schema": SCHEMA, "ok": False, "error_code": exc.code}))
        return EXIT_FAILED

    try:
        if args.mode == "status":
            result: Any = {"roles": manager.status(args.project)}
        elif args.mode == "start-all":
            members = (
                [part.strip() for part in args.members.split(",") if part.strip()]
                if args.members
                else None
            )
            result = manager.start_all(args.project, members)
        elif args.mode == "serve":
            provision_worker = None
            if args.provision_worker:
                # 延迟导入：未开启 worker 的 serve 完全不加载 worker 模块。
                from scripts.role_provision_worker import (  # noqa: PLC0415
                    RoleProvisionWorker,
                    WorkerError,
                )

                try:
                    provision_worker = RoleProvisionWorker(
                        project_id=args.project,
                        host_label=args.host or socket.gethostname(),
                        base_url=args.base_url,
                        project_root=Path(args.project_root),
                        key_root=Path(args.key_root) if args.key_root else None,
                        operator_key=operator_key,
                        enabled=True,
                        apply=bool(args.provision_worker_apply),
                        discovery_limit=(
                            args.provision_worker_discovery_limit
                            if args.provision_worker_discovery_limit is not None
                            else 20
                        ),
                        **(
                            {
                                "io_budget_seconds": args.provision_worker_io_budget_seconds
                            }
                            if args.provision_worker_io_budget_seconds is not None
                            else {}
                        ),
                    )
                except WorkerError as exc:
                    print(
                        json.dumps(
                            {"schema": SCHEMA, "ok": False, "error_code": exc.code},
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                    return EXIT_FAILED
            result = {
                "outcomes": manager.serve(
                    args.project,
                    poll_interval=args.poll_interval,
                    once=False,
                    # 返修 F5：CLI 的轮次上限必须真正传到宿主循环（否则是无效选项）。
                    max_rounds=(
                        args.provision_worker_max_rounds
                        if args.provision_worker
                        else None
                    ),
                    provision_worker=provision_worker,
                )
            }
        elif args.mode == "start":
            if not args.member:
                raise HostError("member_required", "start 需要 --member")
            created = manager.request_start(args.project, args.member)
            result = {
                "member_id": args.member,
                "launch_id": created.get("launch_id"),
                "generation": created.get("generation"),
                "expected_instance_id": created.get("expected_instance_id"),
                "status": "requested",
                "executor": "serve",
                "note": "启动请求已写入；由常驻管理器 serve 承接执行，本进程不 spawn。",
            }
        else:
            if not args.member:
                raise HostError("member_required", "stop 需要 --member")
            created = manager.request_stop(args.project, args.member)
            if created.get("idempotent_stopped"):
                result = {
                    "member_id": args.member,
                    "status": "stopped",
                    "idempotent_stopped": True,
                    "executor": "serve",
                }
            else:
                result = {
                    "member_id": args.member,
                    "launch_id": created.get("launch_id"),
                    "generation": created.get("generation"),
                    "expected_instance_id": created.get("expected_instance_id"),
                    "status": "requested",
                    "executor": "serve",
                    "note": "关闭请求已写入；由常驻管理器 serve 承接执行，本进程不 kill。",
                }
    except HostError as exc:
        payload = {"schema": SCHEMA, "ok": False, "error_code": exc.code}
        print(json.dumps(redact(payload), ensure_ascii=False, sort_keys=True))
        return EXIT_FAILED

    payload = {"schema": SCHEMA, "ok": True, "mode": args.mode, "result": redact(result)}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    # 返修 F5：serve 的结果是 ``{"outcomes": [...]}``；只要任一 outcome 是业务 failed，
    # 宿主 CLI 必须以非零退出码反映，不能因为顶层没有 ``outcome`` 键就丢掉错误。
    failed = False
    if isinstance(result, Mapping):
        rows = result.get("outcomes")
        if isinstance(rows, (list, tuple)):
            failed = any(
                isinstance(item, Mapping)
                and item.get("outcome") in ("failed", "reported")
                for item in rows
            )
        else:
            failed = result.get("outcome") in ("failed", "reported")
    return EXIT_FAILED if failed else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
