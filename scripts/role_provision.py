#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R1-2 B 片：宿主侧角色一键配置脚本 ``scripts/role_provision.py``。

正式依据
--------
- ``docs/spec/ROLE_PROVISION_CONTRACT.md`` §3（本脚本的正式配置合同）；
- ``docs/spec/ROLE_LIFECYCLE_DESIGN.md`` §7.4–7.6、§7.8、§12、§15.2 D3/D5/D7。

本模块做什么
------------
- 只作用于显式 ``--project/--member/--operation-key`` 三元组，绝不扫描/批量同步名册；
- 默认 **dry-run**：只读本地检查 + 打印计划，**零文件写入、零 HTTP**（GET 也不发），可完全离线；
- ``--apply`` 才写身份档与仓库外 Key 文件，并在显式提供 operator（human）凭据时先确保
  provision 作业存在（GET → 缺失则创建；``--resume`` 时定向续跑），再按步 ACK；
- 三步幂等：``profile``（已存在保留人工修改，仅 ``--overwrite-profile`` 覆盖；只补缺失文件）、
  ``key_file``（已存在且身份核验通过则 ``skipped``）、``preflight``（只证可配置事实）。

本模块不做什么
--------------
- 不调用 rotate-key，不再次读取服务端 Key，不把 Key 写进 argv / stdout / stderr / 作业记录；
- 不启动任何 CLI（``--cli-executable`` 只做“路径存在”检查），不声明 native_login / 模型版本 /
  服务就绪，不猜官方登录目录；
- 不做全量 ``POST /sync``；名册路径不一致时只允许对本角色调用 human-only 的
  ``POST /api/projects/{project_id}/roles/{member_id}/provision/roster-paths``
  （且必须在有 operator 凭据时）。

退出码：``0`` 计划完整或全部成功；``1`` partial/failed；``2`` 用法/参数错误。

补充的脚本层错误码
------------------
合同 §3.5 的稳定码之外，本脚本额外使用 ``cli_executable_missing``：显式 ``--cli-executable``
指向的路径不存在时，preflight 必须失败，而合同码表没有对应项（不伪造 ``http_error``）。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import secrets
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
# 复用既有模块（``cli.profiles``）；只调整 sys.path，不读环境、不触网、不启进程。
for _path_entry in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from cli import profiles as profile_helpers  # noqa: E402

__all__ = [
    "CREDENTIAL_METADATA_SCHEMA",
    "DEFAULT_BASE_URL",
    "DEFAULT_KEY_ROOT",
    "DEFAULT_LOCK_STALE_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "HttpResponse",
    "ProvisionError",
    "REQUEST_ENDPOINT_ERROR_WHITELIST",
    "SCHEMA",
    "STEP_ORDER",
    "UrlLibTransport",
    "acquire_lock",
    "acquire_provision_locks",
    "assert_inside_root",
    "build_parser",
    "create_role_for_request",
    "credential_metadata_path",
    "key_file_path",
    "lock_path_for",
    "main",
    "parse_steps",
    "profile_lock_path_for",
    "profile_target_paths",
    "read_credential_metadata",
    "release_lock",
    "release_provision_locks",
    "rotate_role_key_for_request",
    "run_provision",
    "run_request_provision",
    "write_credential_metadata",
]

SCHEMA = "talk-role-provision-1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_LOCK_STALE_SECONDS = 900.0
#: 默认 Key 根：仓库外的用户目录（``--key-root`` 必须位于仓库之外）。
DEFAULT_KEY_ROOT = Path.home() / ".talk" / "keys"

ROLE_KEY_ENV = "TALK_ROLE_API_KEY"
OPERATOR_KEY_ENV = "TALK_OPERATOR_API_KEY"
OPERATOR_KEY_FILE_ENV = "TALK_OPERATOR_KEY_FILE"

STEP_ORDER: tuple[str, ...] = ("profile", "key_file", "preflight")
PROFILE_KINDS: tuple[str, ...] = ("identity", "soul", "user")
PROFILE_FILENAMES: dict[str, str] = {
    "identity": "IDENTITY.md",
    "soul": "SOUL.md",
    "user": "USER.md",
}
#: 身份档目录内的独占锁文件名（同一身份档、不同 Key 根也必须串行；补正 F5）。
PROFILE_LOCK_FILENAME = ".provision.lock"

LOCK_SCHEMA = "talk-role-provision-lock-1"

STATE_PENDING = "pending"
STATE_PLANNED = "planned"
STATE_SUCCEEDED = "succeeded"
STATE_FAILED = "failed"
STATE_SKIPPED = "skipped"

MODE_DRY_RUN = "dry-run"
MODE_APPLY = "apply"

#: 稳定错误码 → 固定说明（只回 code / 字段名 / 固定说明，不含任何正文或路径正文）。
_REASON_DETAILS: dict[str, str] = {
    "role_key_unknown": "未找到可用的角色 Key 来源（--key-input-file 或环境变量 TALK_ROLE_API_KEY）",
    "identity_mismatch": "核到的身份/名册/绑定投影与目标角色不一致",
    "role_key_stale": "现有 Key 文件已无法通过服务端身份核验（可能已轮换或失效）",
    "key_write_failed": "写入角色 Key 文件失败（未留下半截目标文件）",
    "key_permissions_failed": "无法设置或核验 Key 文件的私有访问权限；拒绝按成功上报",
    "provision_lock_busy": "同一目标已有并发的 provision 正在执行（或无法确认锁持有者已退出）",
    "path_escape_refused": "解析后的目标路径逃出了声明根目录",
    "symlink_refused": "目标路径经过符号链接/junction（含声明根自身或其祖先 reparse point）",
    "key_root_inside_repo": "--key-root 必须位于仓库之外",
    "profile_root_invalid": "项目身份档根目录无效或身份档写入失败",
    "operator_key_missing": "缺少 operator（human）凭据，未发送 ACK/单角色注册",
    "ack_failed": "ACK 请求失败",
    "ack_stale": "作业代际已变化（revision/attempt/凭据版本不再匹配），本次结果被服务端拒绝",
    "resume_required": "服务端作业仍有失败步骤；需显式 --resume 才能重开这些步骤",
    "http_error": "HTTP 请求失败",
    "not_apply_mode": "dry-run 模式不写文件、不发写请求",
    "cli_executable_missing": "显式给出的 --cli-executable 路径不存在",
}


class ProvisionError(ValueError):
    """稳定错误码异常：只携带 ``code`` 与固定说明，不携带原值/路径/凭据。"""

    def __init__(self, code: str, detail: Optional[str] = None) -> None:
        self.code = code
        self.detail = detail or _REASON_DETAILS.get(code, code)
        super().__init__(f"{code}: {self.detail}")


# ---------------------------------------------------------------------------
# 路径与文件名安全
# ---------------------------------------------------------------------------


def _safe_dir_name(member_id: str) -> str:
    """``member_dir_name`` 的加严版本：拒绝空名、``..`` 与任何目录分隔符。"""
    name = profile_helpers.member_dir_name(str(member_id))
    if not name or name in {".", ".."}:
        raise ProvisionError("path_escape_refused", "member_id 不能映射为空目录名")
    if "/" in name or "\\" in name or ":" in name or Path(name).name != name:
        raise ProvisionError("path_escape_refused", "member_id 不能映射出目录分隔符")
    return name


def _is_reparse_point(path: Path) -> bool:
    """符号链接或 Windows junction/其它 reparse point。"""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and (attributes & reparse_flag))


def _assert_root_chain_has_no_reparse(root_input: Path) -> None:
    """在 ``resolve()`` **之前**检查声明根自身及其全部祖先（补正 F8）。

    只检查 ``_is_reparse_point`` 的目录链，不跟随链接、不创建目录。规范化之前发现
    junction/symlink/reparse point 一律 ``symlink_refused``，因此 ``--project-root`` 或
    ``--key-root`` 指到一个链接根时不会被 ``resolve()`` 悄悄消去后继续写入。
    """
    current = root_input
    seen = 0
    while True:
        if _is_reparse_point(current):
            raise ProvisionError(
                "symlink_refused",
                "声明根自身或其祖先经过符号链接/junction/reparse point",
            )
        parent = current.parent
        if parent == current or seen > 256:  # 到达卷根或异常深链
            break
        current = parent
        seen += 1


def assert_inside_root(root: Any, candidate: Any) -> Path:
    """把 ``candidate`` 解析到 ``root`` 之内；否则抛稳定错误码。

    ``candidate`` 允许是绝对路径，或**相对 ``root``** 的路径（内部调用者一律传相对
    路径，避免 Windows 8.3 短名与 ``resolve()`` 结果在文本上前缀不一致）。

    - ``..`` 片段 → ``path_escape_refused``；
    - 声明根自身或任一祖先、以及路径链上任一已存在组件是符号链接/junction/reparse
      point → ``symlink_refused``；
    - 解析后的真实路径逃出 ``root`` → ``path_escape_refused``。

    返回解析后的绝对路径；不创建任何目录、不写任何文件。
    """
    root_input = Path(root).expanduser()
    _assert_root_chain_has_no_reparse(root_input)
    root_resolved = root_input.resolve()
    raw = Path(candidate)
    if ".." in raw.parts:
        raise ProvisionError("path_escape_refused", "路径包含 .. 片段")
    combined = raw if raw.is_absolute() else root_input / raw

    current = combined
    while current.is_relative_to(root_input):
        if _is_reparse_point(current):
            raise ProvisionError("symlink_refused", "目标路径经过符号链接/junction")
        if current == root_input:
            break
        parent = current.parent
        if parent == current:  # pragma: no cover - 文件系统根，正常不可达
            break
        current = parent

    resolved = combined.resolve()
    if not (resolved == root_resolved or resolved.is_relative_to(root_resolved)):
        raise ProvisionError("path_escape_refused", "解析后的路径逃出声明根目录")
    return resolved


def profile_lock_path_for(project_root: Any, member_id: str) -> Path:
    """同一身份档的独占锁：``<project>/.talk/agents/<dir>/.provision.lock``（补正 F5）。

    与 Key 根无关，因此同一角色即使换 ``--key-root`` 也会串行；路径同样经
    reparse/逃逸守卫。
    """
    name = _safe_dir_name(member_id)
    relative = Path(".talk") / "agents" / name / PROFILE_LOCK_FILENAME
    return assert_inside_root(project_root, relative)


def profile_target_paths(project_root: Any, member_id: str) -> dict[str, Path]:
    """本角色三个身份档的目标绝对路径（先过分隔符/reparse/逃逸守卫）。"""
    _safe_dir_name(member_id)
    paths: dict[str, Path] = {}
    for kind in PROFILE_KINDS:
        relative = Path(".talk") / "agents" / _safe_dir_name(member_id) / PROFILE_FILENAMES[kind]
        assert_inside_root(project_root, relative)
        try:
            paths[kind] = Path(profile_helpers.resolve_profile_path(project_root, member_id, kind))
        except ValueError as exc:  # pragma: no cover - 已被上面的守卫覆盖
            raise ProvisionError("path_escape_refused", str(exc)) from exc
    return paths


def key_file_path(key_root: Any, member_id: str) -> Path:
    """``<key-root>/<member_dir_name>.key`` 的解析路径（守卫同身份档）。"""
    name = _safe_dir_name(member_id)
    return assert_inside_root(key_root, Path(f"{name}.key"))


def lock_path_for(target: Any) -> Path:
    """同一目标的独占锁文件：``<target>.lock``。"""
    return Path(str(target) + ".lock")


def _path_is_within(path: Any, root: Any) -> bool:
    try:
        resolved = Path(path).expanduser().resolve()
        root_resolved = Path(root).expanduser().resolve()
    except OSError:  # pragma: no cover - 解析失败按不在仓库内处理会被外层拒绝
        return False
    return resolved == root_resolved or resolved.is_relative_to(root_resolved)


# ---------------------------------------------------------------------------
# Key 读取与脱敏（Key 只进内存，绝不进 argv / 输出 / 记录）
# ---------------------------------------------------------------------------


def _is_plausible_key(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return all(0x21 <= ord(ch) <= 0x7E for ch in text)


def _read_key_file(path: Any) -> Optional[str]:
    """读取 Key 文件的第一行可打印 ASCII；不可用/非法一律返回 ``None``。"""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    for line in text.splitlines():
        candidate = line.strip()
        if candidate and _is_plausible_key(candidate):
            return candidate
        if candidate:
            return None
    return None


def _load_key_source(key_input_file: Any, env: Mapping[str, str]) -> Optional[str]:
    """角色 Key 来源：``--key-input-file`` 优先，其次 ``TALK_ROLE_API_KEY``。"""
    if key_input_file:
        from_file = _read_key_file(Path(str(key_input_file)).expanduser())
        if from_file is not None:
            return from_file
    from_env = env.get(ROLE_KEY_ENV)
    if _is_plausible_key(from_env):
        return str(from_env).strip()
    return None


def _key_source_label(key_input_file: Any, env: Mapping[str, str]) -> Optional[str]:
    if key_input_file and _read_key_file(Path(str(key_input_file)).expanduser()) is not None:
        return "--key-input-file"
    if _is_plausible_key(env.get(ROLE_KEY_ENV)):
        return f"env:{ROLE_KEY_ENV}"
    return None


def _resolve_operator_key(env: Mapping[str, str]) -> Optional[str]:
    """operator（human）凭据：环境变量优先，其次其指向的仓库外 Key 文件。"""
    direct = env.get(OPERATOR_KEY_ENV)
    if _is_plausible_key(direct):
        return str(direct).strip()
    key_file = str(env.get(OPERATOR_KEY_FILE_ENV) or "").strip()
    if key_file:
        return _read_key_file(Path(key_file).expanduser())
    return None


# ---------------------------------------------------------------------------
# HTTP：Key 只进请求头；远端正文绝不回显/落盘，只提取固定白名单错误码
# ---------------------------------------------------------------------------

#: 允许从错误响应里提取的**固定白名单**错误码（补正 H1）。
#:
#: provision 入口用 ``HTTPException(detail="<code>")`` 表达精确拒绝原因，因此「409 是否
#: 为精确终态」只能靠这个码判断，不能靠随后的 GET 200 反推（禁用/离册/归档会被拒绝后
#: 事实恢复而 GET 又变 200）。白名单是字面量集合：只有逐字命中它的字符串才允许进入
#: 内存与报告的 detail；其余远端正文（可能含凭据/路径）一律丢弃，绝不落盘或回显。
PROVISION_ERROR_CODE_WHITELIST: frozenset[str] = frozenset(
    {
        "provision_job_terminal",
        "provision_job_failed",
        "provision_job_not_found",
        "provision_member_missing",
        "provision_member_not_agent",
        "provision_member_disabled",
        "provision_roster_missing",
        "provision_roster_path_invalid",
        "provision_roster_path_failed",
        "provision_operation_mismatch",
        "provision_operation_not_found",
        "provision_imported_identity_unsupported",
        "provision_credential_stale",
        "provision_revision_conflict",
        "provision_step_not_pending",
        "provision_stale_attempt",
        "provision_step_invalid",
        "provision_ack_state_invalid",
        "provision_ack_failed",
        "provision_error_code_invalid",
        "role_archived",
    }
)

#: 错误正文的有界读取上限：只够解析白名单错误码，绝不整段留用。
ERROR_BODY_READ_LIMIT_BYTES = 4096


@dataclass
class HttpResponse:
    status: int
    payload: Any = None
    #: 仅当响应体命中 :data:`PROVISION_ERROR_CODE_WHITELIST` 时填充（补正 H1）。
    error_code: Optional[str] = None


def _extract_whitelisted_error_code(
    raw: Any, whitelist: frozenset[str] = PROVISION_ERROR_CODE_WHITELIST
) -> Optional[str]:
    """从**有界**错误正文里只取固定白名单错误码；其余内容立即丢弃（补正 H1）。

    - 只解析 ``{"detail": "<code>"}`` 或 ``{"detail": {"code": "<code>"}}``；
    - ``code`` 必须逐字命中白名单，未知/自由文本一律 ``None``；
    - 不返回、不记录正文里的任何其它字段。
    """
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return None
    try:
        body = json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(body, Mapping):
        return None
    detail = body.get("detail")
    if isinstance(detail, str) and detail in whitelist:
        return detail
    if isinstance(detail, Mapping):
        code = detail.get("code")
        if isinstance(code, str) and code in whitelist:
            return code
    return None


def _whitelisted_response_error_code(
    response: Any, whitelist: frozenset[str] = PROVISION_ERROR_CODE_WHITELIST
) -> Optional[str]:
    """从任意同形状传输响应安全取白名单错误码（默认 HTTP 与测试假传输共用）。

    默认 :class:`UrlLibTransport` 只填 ``error_code``（正文已丢弃）；注入的假传输/端到端
    传输可能把 ``detail`` 留在 ``payload`` 里，这里同样只接受白名单命中值。
    """
    code = getattr(response, "error_code", None)
    if isinstance(code, str) and code in whitelist:
        return code
    payload = getattr(response, "payload", None)
    if isinstance(payload, Mapping):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail in whitelist:
            return detail
        if isinstance(detail, Mapping):
            inner = detail.get("code")
            if isinstance(inner, str) and inner in whitelist:
                return inner
    return None


class UrlLibTransport:
    """默认 HTTP 边界；测试用同形状的假传输替换（本模块不启进程、不读代理）。"""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = float(timeout)

    def request_json(
        self,
        method: str,
        url: str,
        *,
        api_key: Optional[str] = None,
        body: Any = None,
        timeout: Optional[float] = None,
    ) -> HttpResponse:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["X-API-Key"] = str(api_key)
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=str(method).upper())
        effective_timeout = self._timeout if timeout is None else float(timeout)
        try:
            with urlopen(request, timeout=effective_timeout) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200) or 200)
        except HTTPError as exc:
            # 远端正文可能原样回显凭据：有界读取后只保留白名单错误码，其余全丢。
            raw: Any = None
            try:
                raw = exc.read(ERROR_BODY_READ_LIMIT_BYTES)
            except Exception:  # noqa: BLE001 - 读错误正文失败等价于没有错误码
                raw = None
            finally:
                try:
                    exc.close()
                except Exception:  # noqa: BLE001 - 关闭失败不影响判定
                    pass
            return HttpResponse(
                status=int(exc.code),
                payload=None,
                error_code=_extract_whitelisted_error_code(raw),
            )
        except (URLError, OSError, TimeoutError):
            return HttpResponse(status=0, payload=None)
        if not raw:
            return HttpResponse(status=status, payload=None)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return HttpResponse(status=status, payload=None)
        return HttpResponse(status=status, payload=payload)


def _api(base_url: str, path: str) -> str:
    return f"{base_url}{path}"


def _me_path() -> str:
    return "/api/members/me"


def _roster_path(project_id: str) -> str:
    return f"/api/projects/{quote(project_id, safe='')}/agents"


def _roles_path(project_id: str) -> str:
    return f"/api/projects/{quote(project_id, safe='')}/roles"


def _agent_sub_path(project_id: str, member_id: str, suffix: str) -> str:
    return (
        f"/api/projects/{quote(project_id, safe='')}/agents/"
        f"{quote(member_id, safe='')}/{suffix}"
    )


def _provision_path(project_id: str, member_id: str) -> str:
    return (
        f"/api/projects/{quote(project_id, safe='')}/roles/"
        f"{quote(member_id, safe='')}/provision"
    )


def _provision_roster_paths_path(project_id: str, member_id: str) -> str:
    """Part A 的单角色名册路径登记入口（human/operator 凭据）。"""
    return _provision_path(project_id, member_id) + "/roster-paths"


def _roster_relative_paths(member_id: str) -> dict[str, str]:
    """本角色三个身份档的**仓库相对 posix 路径**（服务端名册只存相对路径）。"""
    name = _safe_dir_name(member_id)
    return {
        "identity_path": f".talk/agents/{name}/{PROFILE_FILENAMES['identity']}",
        "soul_path": f".talk/agents/{name}/{PROFILE_FILENAMES['soul']}",
        "user_path": f".talk/agents/{name}/{PROFILE_FILENAMES['user']}",
    }


def _role_key_verdict(
    transport: Any, base_url: str, key: str, member_id: str, timeout: float
) -> tuple[str, Optional[str]]:
    """用角色 Key 做 ``GET /api/members/me``；返回 ``(ok|mismatch|invalid|http, actual_id)``。"""
    response = transport.request_json(
        "GET", _api(base_url, _me_path()), api_key=key, timeout=timeout
    )
    if response.status == 200 and isinstance(response.payload, Mapping):
        actual = response.payload.get("id")
        actual_text = actual.strip() if isinstance(actual, str) else None
        if actual_text == member_id:
            return "ok", actual_text
        return "mismatch", actual_text
    if response.status in (401, 403):
        return "invalid", None
    return "http", None


# ---------------------------------------------------------------------------
# 结果形状
# ---------------------------------------------------------------------------


def _step(state: str, attempts: int, error_code: Optional[str], detail: str) -> dict[str, Any]:
    return {
        "state": state,
        "attempts": int(attempts),
        "error_code": error_code,
        "detail": detail,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 独占锁（有所有权的租约 + OS 互斥守卫；补正 F5/G2）
#
# 旧实现只按 mtime 年龄回收，导致：活锁被第二 owner 抢走、首 owner 释放时删掉
# 第二 owner 的锁、第三 owner 在第二 owner 仍活动时也拿到锁。F5 补上了
# ``schema/token/pid/started_at`` 记录与「持有者确认已退出 + 租约过期」判定，但
# **判定与删除之间仍有窗口**：两个回收者可以都先判定同一死锁可回收，再先后
# unlink 并各自新建活锁（G2 反例）。
#
# 现在再加一层**OS 互斥守卫**（``<lock>.guard``，只增不删，避免 ABA）：
#   - ``acquire_lock`` 先非阻塞拿 OS 独占字节锁（Windows ``msvcrt.locking`` /
#     POSIX ``flock``），拿不到直接 ``provision_lock_busy``；
#   - 「判定陈旧 → unlink 旧锁 → 原子发布新锁」整段都在守卫内，因此回收与占有是真正
#     互斥的原子协议，不再依赖“再读一次 token”；
#   - 守卫由 **OS 在进程退出时自动释放**（崩溃/被杀也成立），所以死 owner 之后
#     重开仍然可行；活 owner 持有守卫期间任何第二进程都无法进入临界区；
#   - 可见锁文件仍保留 token/pid 记录：释放只删自己代际，审计与排障语义不变。
#
# 补正 H2：可见锁记录改为**原子发布**——先把完整记录写进同目录临时文件（flush+fsync），
# 再 ``os.link`` 成可见锁。可见锁要么不存在、要么是完整记录，创建/写入/flush 中断不再
# 留下 0 字节锁；残留的发布临时文件按 pid 确认退出后在下一次持守卫时清理。旧协议/未知
# 来源的不可解析锁一律 fail closed（不按年龄或内容抢占，需人工确认）。
# ---------------------------------------------------------------------------

#: 与可见锁文件配对的 OS 守卫文件名后缀（守卫文件本身从不删除）。
LOCK_GUARD_SUFFIX = ".guard"

#: 进程内登记的守卫句柄：``(锁路径, token) -> fd``；仅本进程可见。
_LOCK_GUARD_FDS: dict[tuple[str, str], int] = {}


def lock_guard_path_for(lock_path: Any) -> Path:
    """守卫文件路径：``<lock>.guard``；与锁文件同目录、同生命周期（不删除）。"""
    return Path(str(lock_path) + LOCK_GUARD_SUFFIX)


def _assert_lock_paths_safe(lock_path: Path) -> None:
    """在碰可见锁/守卫之前，把**两者**一并纳入自身与祖先链接保护（补正 H3）。

    旧实现只经 :func:`assert_inside_root` 校验 ``<target>.lock``；新增的
    ``<lock>.guard`` 后缀从未被校验：预置一个指向外部对象的符号链接/junction 后，
    ``os.open(O_CREAT|O_RDWR)`` 会跟随它，可能把初始化字节写进外部文件或对外部对象加锁。
    这里在**任何 open/write 之前**统一拒绝：

    - 锁目录自身或其任一祖先（含声明根本身）是 reparse point → ``symlink_refused``；
    - 可见锁文件自身是 reparse point → ``symlink_refused``；
    - 守卫文件自身是 reparse point → ``symlink_refused``（不能只检原 lock 就认为 guard 已受检）。
    """
    _assert_root_chain_has_no_reparse(lock_path.parent)
    if _is_reparse_point(lock_path):
        raise ProvisionError("symlink_refused", "锁文件是符号链接/junction/reparse point")
    if _is_reparse_point(lock_guard_path_for(lock_path)):
        raise ProvisionError(
            "symlink_refused", "锁守卫文件是符号链接/junction/reparse point"
        )


def _lock_guard_acquire(lock_path: Path) -> Optional[int]:
    """非阻塞拿 OS 独占字节锁；拿到返回 fd，拿不到/平台不支持返回 ``None``。

    守卫自身与锁目录先过链接守卫（H3），因此本函数可能在**没有 open 任何文件**的情况下
    抛 ``symlink_refused``。
    """
    _assert_lock_paths_safe(lock_path)
    guard = lock_guard_path_for(lock_path)
    try:
        fd = os.open(guard, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return None
    try:
        if os.fstat(fd).st_size < 1:  # 字节锁需要至少 1 字节的锁定区间
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"talk-role-provision-lock-guard\n")
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            os.close(fd)
        except OSError:
            pass
        return None
    return fd


def _lock_guard_release(fd: Optional[int]) -> None:
    """释放并关闭守卫句柄；任何失败都不抛出（调用方已进入清理路径）。"""
    if fd is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _lock_is_stale(lock_path: Path, stale_seconds: float) -> bool:
    try:
        mtime = lock_path.stat().st_mtime
    except OSError:
        return False
    return (time.time() - mtime) > max(0.0, float(stale_seconds))


def _read_lock_record(lock_path: Path) -> Optional[Mapping[str, Any]]:
    """读锁文件 JSON；不可读/不可解析一律 ``None``（调用方据此 fail closed）。"""
    try:
        raw = lock_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    try:
        record = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return record if isinstance(record, Mapping) else None


def _windows_pid_alive(pid: int) -> Optional[bool]:
    """Windows 三态存活判定；只用 OpenProcess/GetExitCodeProcess，不发信号。"""
    try:
        from ctypes import wintypes
    except Exception:  # pragma: no cover - 非 Windows 走不到
        return None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5
    ERROR_INVALID_PARAMETER = 87
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
    except (OSError, AttributeError, ValueError):  # pragma: no cover - 平台能力缺失
        return None
    if not handle:
        error = ctypes.get_last_error()
        if error == ERROR_ACCESS_DENIED:
            return True  # 进程存在但无查询权限：按存活处理（fail closed）
        if error == ERROR_INVALID_PARAMETER:
            return False
        return None
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _process_is_alive(pid: Any) -> Optional[bool]:
    """``True`` 存活 / ``False`` 已退出 / ``None`` 无法判定（调用方 fail closed）。"""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if pid == os.getpid():
        return True
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _lock_reclaimable(lock_path: Path, stale_seconds: float) -> bool:
    """锁是否可回收：记录可解析 + 持有者确认已退出 + 租约已过期。

    只在**持有 OS 守卫**时调用（:func:`acquire_lock`），因此判定结果到随后的
    ``unlink`` 之间没有窗口：并发的回收者根本进不来。
    """
    record = _read_lock_record(lock_path)
    if record is None:
        return False
    token = record.get("token")
    if not isinstance(token, str) or not token:
        return False
    if _process_is_alive(record.get("pid")) is not False:
        # 存活或无法判定：绝不按年龄抢占（活锁不能被年龄回收）。
        return False
    return _lock_is_stale(lock_path, stale_seconds)


def _lock_conflict_detail(lock_path: Path) -> str:
    """区分「并发持有」与「旧/未知来源不可解析锁」（补正 H2 的兼容边界）。

    旧协议在 O_EXCL 创建与写记录之间崩溃会留下 0 字节锁；本协议改为原子发布后，
    这种残留只可能来自**旧版本/人为**来源，因此明确 fail closed，绝不按年龄或内容抢占。
    """
    if _read_lock_record(lock_path) is None:
        return (
            "存在不可解析的可见锁（旧协议残留或人为放置，非本脚本原子发布产物）；"
            "拒绝按年龄/内容抢占，需人工确认后移除"
        )
    return "锁由并发执行持有"


def _lock_record(token: str) -> dict[str, Any]:
    """本次代际的完整锁记录（可见锁里出现的唯一形态）。"""
    return {
        "schema": LOCK_SCHEMA,
        "token": token,
        "pid": os.getpid(),
        "started_at": _now_iso(),
    }


#: 原子发布临时文件：``<lock>.publish-<pid>-<token>.tmp``，只在持守卫的临界区内存在。
LOCK_PUBLISH_MARKER = ".publish-"
LOCK_PUBLISH_TEMP_SUFFIX = ".tmp"


def _lock_publish_temp_name(lock_path: Path, pid: int, token: str) -> str:
    return f"{lock_path.name}{LOCK_PUBLISH_MARKER}{pid}-{token}{LOCK_PUBLISH_TEMP_SUFFIX}"


def _sweep_lock_publish_temps(lock_path: Path) -> list[str]:
    """清掉本协议自己留下的发布临时文件（只在持有守卫时调用；补正 H2）。

    持守卫 ⇒ 不可能有协作进程正在发布，残留临时文件必然是某个已中断/已退出进程的产物。
    名字里带 pid，因此仍按「pid 已确认退出或就是本进程」才删；pid 存活/无法判定的一律
    不动（不按年龄、不按内容乱删非本进程的状态）。
    """
    removed: list[str] = []
    prefix = len(lock_path.name) + len(LOCK_PUBLISH_MARKER)
    pattern = f"{lock_path.name}{LOCK_PUBLISH_MARKER}*{LOCK_PUBLISH_TEMP_SUFFIX}"
    try:
        candidates = sorted(lock_path.parent.glob(pattern))
    except OSError:  # pragma: no cover - 目录不可读时无法清理
        return removed
    for candidate in candidates:
        head = candidate.name[prefix:].split("-", 1)[0]
        if not head.isdigit():
            continue
        pid = int(head)
        if pid != os.getpid() and _process_is_alive(pid) is not False:
            continue
        try:
            candidate.unlink()
            removed.append(candidate.name)
        except OSError:  # pragma: no cover - 清理失败不影响主流程
            pass
    return removed


def _write_lock_record_temp(lock_path: Path, token: str) -> Path:
    """把**完整**锁记录写进同目录临时文件并 flush+fsync（H2 发布前半段）。

    任何失败都只留下可被 :func:`_sweep_lock_publish_temps` 清理的临时文件，绝不产生
    半截可见锁。
    """
    temp_path = lock_path.with_name(
        _lock_publish_temp_name(lock_path, os.getpid(), token)
    )
    handle_fd = os.open(temp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        handle = os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n")
    except BaseException:
        try:
            os.close(handle_fd)
        except OSError:  # pragma: no cover - 已关闭/无效 fd
            pass
        _remove_quietly(temp_path)
        raise
    try:
        with handle:
            handle.write(json.dumps(_lock_record(token), ensure_ascii=False))
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        _remove_quietly(temp_path)
        raise
    return temp_path


def _remove_quietly(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _publish_lock_record(temp_path: Path, lock_path: Path) -> None:
    """把完整记录**原子发布**为可见锁；目标已存在一律冲突（补正 H2）。

    首选 ``os.link``：同目录硬链接是「要么不存在、要么完整」的原子独占发布，目标已存在
    直接 ``FileExistsError``。文件系统不支持硬链接时退回守卫内的同目录原子替换，并在
    替换前再确认目标不存在（持守卫期间没有协作进程能并发创建）。
    """
    try:
        os.link(temp_path, lock_path)
        return
    except FileExistsError:
        raise ProvisionError("provision_lock_busy", "锁由并发执行持有") from None
    except OSError:
        pass  # 平台/文件系统不支持硬链接：走守卫内的原子替换
    if lock_path.exists():
        raise ProvisionError("provision_lock_busy", "锁由并发执行持有")
    try:
        os.replace(temp_path, lock_path)
    except OSError as exc:
        raise ProvisionError("key_write_failed", "无法发布锁文件") from exc


def acquire_lock(
    lock_path: Path, stale_seconds: float = DEFAULT_LOCK_STALE_SECONDS
) -> dict[str, Any]:
    """独占创建 ``<target>.lock``；冲突抛 ``provision_lock_busy``。

    协议（G2 守卫 + 补正 H2 原子发布）：

    1. 先拿 ``<lock>.guard`` 的 OS 独占字节锁（死 owner 由 OS 自动释放；守卫文件不删）；
    2. 守卫内清掉本协议残留的发布临时文件，再按「记录可解析 + 持有者确认退出 + 租约过期」
       决定是否回收旧锁；**不可解析的旧锁一律 fail closed**（不按年龄/内容抢）；
    3. 把**完整**记录写进同目录临时文件（flush+fsync）后 ``os.link`` 原子发布：可见锁要么
       不存在、要么就是完整记录 —— 创建/写入/flush 各中断点都不再留下 0 字节锁，同路径
       重试可直接完成，无需人工清理。

    返回的 handle 含本次代际 ``token``，必须原样交给 :func:`release_lock`，
    否则不会删除任何锁文件（也不会释放守卫）。
    """
    # 检查必须先于 mkdir：链接祖先下的缺失子目录也属于写入副作用。
    _assert_lock_paths_safe(lock_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProvisionError("key_write_failed", "无法创建锁目录") from exc

    # H3：可见锁与守卫的自身/祖先链接检查都在任何 open/write 之前（内部调用）。
    guard_fd = _lock_guard_acquire(lock_path)
    if guard_fd is None:
        raise ProvisionError("provision_lock_busy", "锁由并发执行持有")

    token = secrets.token_hex(16)
    reclaimed = False
    try:
        _sweep_lock_publish_temps(lock_path)
        if lock_path.exists():
            if not _lock_reclaimable(lock_path, stale_seconds):
                raise ProvisionError(
                    "provision_lock_busy", _lock_conflict_detail(lock_path)
                )
            try:
                os.remove(lock_path)
            except OSError as exc:
                raise ProvisionError("provision_lock_busy", "陈旧锁无法清理") from exc
            reclaimed = True
        temp_path = _write_lock_record_temp(lock_path, token)
        try:
            _publish_lock_record(temp_path, lock_path)
        finally:
            _remove_quietly(temp_path)
        _LOCK_GUARD_FDS[(str(lock_path), token)] = guard_fd
        return {
            "acquired": True,
            "reclaimed": reclaimed,
            "path": str(lock_path),
            "token": token,
            "pid": os.getpid(),
        }
    except BaseException:
        _lock_guard_release(guard_fd)
        raise


def release_lock(lock_path: Path, handle: Any = None) -> bool:
    """只释放**自己代际**的锁；token 不一致或缺失时绝不删除别人的锁。

    返回 ``True`` 表示确实删除了自己的锁文件。守卫句柄按 handle 里的 ``token``
    回收并释放，因此即便可见锁文件已被别人改代际，也不会把自己的守卫泄漏给
    进程生命周期之外（最坏情况只是本进程不再持锁）。
    """
    token = handle.get("token") if isinstance(handle, Mapping) else None
    removed = False
    if isinstance(token, str) and token:
        record = _read_lock_record(Path(lock_path))
        if record is not None and record.get("token") == token:
            try:
                os.remove(lock_path)
                removed = True
            except OSError:
                removed = False
    guard_fd = (
        _LOCK_GUARD_FDS.pop((str(lock_path), token), None)
        if isinstance(token, str) and token
        else None
    )
    _lock_guard_release(guard_fd)
    return removed


# ---------------------------------------------------------------------------
# 身份档
# ---------------------------------------------------------------------------


def _profile_template(kind: str, project_id: str, member_id: str) -> str:
    titles = {"identity": "IDENTITY", "soul": "SOUL", "user": "USER"}
    bodies = {
        "identity": "## 我是谁\n\n（待人工补全：Agent 类型、擅长领域）",
        "soul": "## 语气与边界\n\n（待人工补全：语气、决策风格、不可逾越的边界）",
        "user": "## 项目搭档\n\n（待人工补全：本项目里的搭档信息）",
    }
    return (
        f"# {titles[kind]}\n\n"
        f"- member_id: `{member_id}`\n"
        f"- project_id: `{project_id}`\n\n"
        f"{bodies[kind]}\n\n"
        "> 由 `scripts/role_provision.py` 生成的最小身份档；只登记可配置事实，"
        "不声明模型版本、原生登录或服务就绪。\n"
    )


def _profile_plan(paths: Mapping[str, Path], *, overwrite: bool) -> dict[str, list[str]]:
    create: list[str] = []
    keep: list[str] = []
    overwritten: list[str] = []
    for kind in PROFILE_KINDS:
        name = PROFILE_FILENAMES[kind]
        if paths[kind].is_file():
            (overwritten if overwrite else keep).append(name)
        else:
            create.append(name)
    return {"create": create, "keep": keep, "overwrite": overwritten}


def _run_profile_step(
    *,
    project_root: Path,
    member_id: str,
    project_id: str,
    paths: Mapping[str, Path],
    overwrite: bool,
) -> dict[str, Any]:
    plan = _profile_plan(paths, overwrite=overwrite)
    for kind in PROFILE_KINDS:
        name = PROFILE_FILENAMES[kind]
        if name not in plan["create"] and name not in plan["overwrite"]:
            continue
        content = _profile_template(kind, project_id, member_id)
        try:
            profile_helpers.write_profile_file_atomic(project_root, member_id, kind, content)
        except (OSError, ValueError) as exc:
            raise ProvisionError(
                "profile_root_invalid", f"写入 {name} 失败（未留半截文件）"
            ) from exc
    state = STATE_SUCCEEDED if (plan["create"] or plan["overwrite"]) else STATE_SKIPPED
    detail = (
        f"create={plan['create']} keep={plan['keep']} "
        f"overwrite={plan['overwrite']} atomic=true"
    )
    return _step(state, 1, None, detail)


# ---------------------------------------------------------------------------
# Key 文件
#
# 补正 F6：Windows 上不再「尽力而为」。私有 DACL 在**文件创建时**就用本机安全接口
# （CreateFileW + SECURITY_ATTRIBUTES）带上，只允许「当前用户 + SYSTEM +
# Administrators」；随后回读实际 DACL 核验（无继承 ACE、无其它主体、有 DENY 一律失败）。
# 该环境实测不允许事后修改既有 DACL（SetNamedSecurityInfo/icacls 均 ACCESS_DENIED），
# 因此创建时带入是唯一可行且没有「先明文后收紧」窗口的做法；任何一步失败都报失败，
# 绝不按 succeeded 上报，也不留下宽权限的 Key 文件。
# ---------------------------------------------------------------------------

#: 除当前用户外只额外保留本机必要的系统/管理员主体。
WINDOWS_ACL_ALLOWED_SIDS: tuple[str, ...] = ("S-1-5-18", "S-1-5-32-544")
_WINDOWS_FILE_ALL_ACCESS = 0x001F01FF


class _WindowsAclError(RuntimeError):
    """Windows ACL 操作失败的内部信号（对外只映射稳定错误码）。"""


def _windows_current_user_sid() -> str:
    """当前进程令牌的用户 SID（字符串形式）。"""
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    class _SidAndAttributes(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    class _TokenUser(ctypes.Structure):
        _fields_ = [("User", _SidAndAttributes)]

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
    ):
        raise _WindowsAclError("OpenProcessToken failed")
    try:
        size = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not size.value:
            raise _WindowsAclError("GetTokenInformation size failed")
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, 1, buffer, size.value, ctypes.byref(size)
        ):
            raise _WindowsAclError("GetTokenInformation failed")
        user = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents
        text = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(user.User.Sid, ctypes.byref(text)):
            raise _WindowsAclError("ConvertSidToStringSidW failed")
        return str(text.value)
    finally:
        kernel32.CloseHandle(token)


def _windows_acl_sids() -> list[str]:
    """私有 ACL 允许的主体：当前用户 + SYSTEM + Administrators（去重保序）。"""
    return list(
        dict.fromkeys([_windows_current_user_sid(), *WINDOWS_ACL_ALLOWED_SIDS])
    )


def _windows_build_private_security_attributes():
    """构造带私有 DACL 的 ``SECURITY_ATTRIBUTES``（含全部 keepalive 引用）。"""
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    advapi32.InitializeAcl.restype = wintypes.BOOL
    advapi32.AddAccessAllowedAceEx.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    advapi32.AddAccessAllowedAceEx.restype = wintypes.BOOL
    advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.InitializeSecurityDescriptor.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    advapi32.InitializeSecurityDescriptor.restype = wintypes.BOOL
    advapi32.SetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        ctypes.c_void_p,
        wintypes.BOOL,
    ]
    advapi32.SetSecurityDescriptorDacl.restype = wintypes.BOOL

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    acl = ctypes.create_string_buffer(4096)
    if not advapi32.InitializeAcl(acl, 4096, 2):
        raise _WindowsAclError("InitializeAcl failed")
    sid_pointers: list[Any] = []
    for sid_text in _windows_acl_sids():
        psid = ctypes.c_void_p()
        if not advapi32.ConvertStringSidToSidW(sid_text, ctypes.byref(psid)):
            raise _WindowsAclError("ConvertStringSidToSidW failed")
        sid_pointers.append(psid)
        if not advapi32.AddAccessAllowedAceEx(
            acl, 2, 0, _WINDOWS_FILE_ALL_ACCESS, psid
        ):
            raise _WindowsAclError("AddAccessAllowedAceEx failed")
    descriptor = ctypes.create_string_buffer(64)
    if not advapi32.InitializeSecurityDescriptor(descriptor, 1):
        raise _WindowsAclError("InitializeSecurityDescriptor failed")
    if not advapi32.SetSecurityDescriptorDacl(descriptor, True, acl, False):
        raise _WindowsAclError("SetSecurityDescriptorDacl failed")
    attributes = _SecurityAttributes(
        nLength=ctypes.sizeof(_SecurityAttributes),
        lpSecurityDescriptor=ctypes.cast(descriptor, ctypes.c_void_p),
        bInheritHandle=False,
    )
    # 返回 SECURITY_ATTRIBUTES 时必须同时保留 buffer/SID 指针，避免被 GC 回收。
    return attributes, (acl, descriptor, sid_pointers)


def _windows_create_file_with_private_acl(path: Path, payload: bytes) -> None:
    """创建文件时直接带入私有 DACL 并写入正文（不留「先明文后收紧」窗口）。

    使用 ``CREATE_NEW``：目标已存在时失败而不是覆盖（调用方在目标存在时已有既有的
    「核验通过则跳过」路径）。``WriteFile`` 短写或 ``FlushFileBuffers`` 失败都抛错，
    并尽力删掉**本次刚创建**的半截文件；写入后由调用方回读校验。
    """
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel32.FlushFileBuffers.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    attributes, keepalive = _windows_build_private_security_attributes()
    invalid = ctypes.c_void_p(-1).value
    handle = kernel32.CreateFileW(
        str(path),
        0x40000000,  # GENERIC_WRITE
        0,  # 独占
        ctypes.byref(attributes),
        1,  # CREATE_NEW：不覆盖既有文件
        0x80,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    if not handle or handle == invalid:
        raise _WindowsAclError(f"CreateFileW failed err={ctypes.get_last_error()}")
    failed = True
    try:
        written = wintypes.DWORD(0)
        buffer = ctypes.create_string_buffer(payload, len(payload))
        if not kernel32.WriteFile(
            handle, buffer, len(payload), ctypes.byref(written), None
        ):
            raise _WindowsAclError("WriteFile failed")
        if written.value != len(payload):
            raise _WindowsAclError("WriteFile short write")
        if not kernel32.FlushFileBuffers(handle):
            raise _WindowsAclError("FlushFileBuffers failed")
        failed = False
    finally:
        kernel32.CloseHandle(handle)
        del keepalive
        if failed:
            # 只清理本次 CREATE_NEW 成功创建的文件；失败时尽力删除，不掩盖原异常。
            try:
                os.remove(path)
            except OSError:
                pass


def _windows_verify_private_acl(path: Path) -> tuple[bool, str]:
    """回读实际 DACL：只允许私有主体、无继承 ACE、无 DENY；否则失败。"""
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetAclInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_int,
    ]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetAce.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    class _AclSizeInformation(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    class _AceHeader(ctypes.Structure):
        _fields_ = [
            ("AceType", ctypes.c_ubyte),
            ("AceFlags", ctypes.c_ubyte),
            ("AceSize", ctypes.c_ushort),
        ]

    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = advapi32.GetNamedSecurityInfoW(
        str(path),
        1,  # SE_FILE_OBJECT
        0x00000004,  # DACL_SECURITY_INFORMATION
        None,
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if status != 0 or not dacl:
        return False, f"read_dacl_failed status={status}"
    try:
        info = _AclSizeInformation()
        if not advapi32.GetAclInformation(
            dacl, ctypes.byref(info), ctypes.sizeof(info), 2
        ):
            return False, "acl_info_failed"
        if info.AceCount == 0:
            return False, "acl_empty"
        allowed = set(_windows_acl_sids())
        seen: list[str] = []
        for index in range(info.AceCount):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                return False, "get_ace_failed"
            header = ctypes.cast(ace, ctypes.POINTER(_AceHeader)).contents
            sid_text = ctypes.c_wchar_p()
            if not advapi32.ConvertSidToStringSidW(
                ctypes.c_void_p(ace.value + 8), ctypes.byref(sid_text)
            ):
                return False, "sid_decode_failed"
            sid = str(sid_text.value)
            seen.append(sid)
            if header.AceFlags & 0x10:  # INHERITED_ACE
                return False, f"inherited_ace:{sid}"
            if header.AceType != 0x00:  # ACCESS_ALLOWED_ACE_TYPE
                return False, f"non_allowed_ace:{sid}"
            if sid not in allowed:
                return False, f"extra_principal:{sid}"
        if _windows_current_user_sid() not in seen:
            return False, "current_user_missing"
        return True, "acl=" + ",".join(seen)
    finally:
        kernel32.LocalFree(descriptor)


def _enforce_private_permissions(path: Path) -> str:
    """把已存在的 Key 文件核验为私有权限；不通过 → ``key_permissions_failed``。"""
    if os.name == "nt":
        ok, detail = _windows_verify_private_acl(Path(path))
        if not ok:
            raise ProvisionError(
                "key_permissions_failed", f"Windows ACL 核验失败（{detail}）"
            )
        return f"windows_acl_verified({detail})"
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError as exc:
        raise ProvisionError("key_permissions_failed", "无法读取文件权限位") from exc
    if mode != 0o600:
        try:
            os.chmod(path, 0o600)
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError as exc:
            raise ProvisionError("key_permissions_failed", "无法收紧文件权限位") from exc
    if mode != 0o600:
        raise ProvisionError(
            "key_permissions_failed", f"POSIX 权限位仍为 {oct(mode)}，不是 0600"
        )
    return "0600"


def _key_temp_pattern(key_path: Path) -> str:
    """本目标专用的临时发布文件名模式（同目录、非递归 glob 用）。"""
    return f".{key_path.name}.*.tmp"


def _windows_sweep_stale_key_temps(key_path: Path) -> None:
    """清理本目标遗留的**临时**发布文件（只列同目录、不递归、不跟随链接）。

    调用方（``run_provision`` 的 key_file 步骤）持有本目标的 Key 锁，因此同一目标
    不会有两个发布者并存；这些 ``.tmp`` 只可能来自上一次中断，且是本次原子提交阶段
    的产物，不属于正式目标。清理只是尽力而为，失败不影响后续发布。
    """
    parent = key_path.parent
    try:
        candidates = list(parent.glob(_key_temp_pattern(key_path)))
    except OSError:
        return
    for candidate in candidates:
        try:
            if candidate.is_file() and not _is_reparse_point(candidate):
                os.remove(candidate)
        except OSError:
            continue


def _windows_publish_temp_file(key_path: Path, payload: bytes) -> Path:
    """在正式目标同目录发布一个**私有 ACL** 临时文件并回读校验，返回其路径。

    只创建临时文件；正式目标仍由调用方用 ``os.replace`` 原子替换。任何失败都在
    这里删除自己刚创建的临时文件后抛出。
    """
    parent = key_path.parent
    token = secrets.token_hex(8)
    temp_path = parent / f".{key_path.name}.{token}.tmp"
    if temp_path.parent != parent or _is_reparse_point(temp_path):
        raise ProvisionError("symlink_refused", "临时 Key 文件路径不合法")
    try:
        _windows_create_file_with_private_acl(temp_path, payload)
    except (_WindowsAclError, OSError) as exc:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise ProvisionError(
            "key_permissions_failed", "创建私有权限临时 Key 文件失败"
        ) from exc
    try:
        written = temp_path.read_bytes()
    except OSError as exc:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise ProvisionError("key_permissions_failed", "回读临时 Key 文件失败") from exc
    if written != payload:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise ProvisionError("key_write_failed", "临时 Key 文件回读内容不一致")
    ok, detail = _windows_verify_private_acl(temp_path)
    if not ok:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise ProvisionError(
            "key_permissions_failed", f"临时 Key 文件私有 ACL 核验失败（{detail}）"
        )
    return temp_path


def _write_private_payload(target_path: Path, payload: bytes) -> str:
    """把 ``payload`` 私有、原子地发布到 ``target_path``；返回权限描述。

    正式目标任意时刻都「完整或不存在」：

    - Windows：先用 ``CreateFileW(CREATE_NEW)`` + 私有 DACL 在**同目录**写临时文件并回读
      校验，全部通过后才 ``os.replace`` 原子替换正式目标。这样在 CreateFile 之后、
      WriteFile/Flush/回读过程中的任意崩溃/短写/失败都只会留下 ``.tmp``，正式目标保持
      「不存在」，原内容 + 原操作可直接续跑。宿主若拒绝 ``os.replace``（沙箱/文件系统
      限制），如实按能力受阻报错，**不**降级为直接写正式目标。
    - POSIX：同目录临时文件 + ``os.replace`` 原子落地，权限 0600。

    该函数同时服务角色 Key 文件与不含 Key 的私有元数据文件（R1-4b）。
    """
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProvisionError("key_write_failed", "无法创建私有文件目录") from exc

    if os.name == "nt":
        _windows_sweep_stale_key_temps(target_path)
        temp_path = _windows_publish_temp_file(target_path, payload)
        try:
            os.replace(temp_path, target_path)
        except OSError as exc:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise ProvisionError(
                "key_permissions_failed",
                "宿主/文件系统拒绝 Windows 原子提交（移动私有临时文件到正式目标失败）",
            ) from exc
        try:
            written = target_path.read_bytes()
        except OSError as exc:
            try:
                os.remove(target_path)
            except OSError:
                pass
            raise ProvisionError("key_permissions_failed", "回读私有文件失败") from exc
        if written != payload:
            try:
                os.remove(target_path)
            except OSError:
                pass
            raise ProvisionError("key_write_failed", "私有文件回读内容不一致")
        return _enforce_private_permissions(target_path)

    handle_fd, temp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.", suffix=".tmp", dir=str(target_path.parent)
    )
    temp_path = Path(temp_name)
    try:
        os.close(handle_fd)
        os.chmod(temp_path, 0o600)
        with open(temp_path, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target_path)
    except OSError as exc:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise ProvisionError("key_write_failed", "写入私有权限文件失败") from exc
    return _enforce_private_permissions(target_path)


def _write_key_file(key_path: Path, key: str) -> str:
    """写入 Key 文件；成功返回权限描述，正式目标任意时刻都「完整或不存在」。"""
    payload = (key.rstrip("\r\n") + "\n").encode("utf-8")
    return _write_private_payload(key_path, payload)


def _run_key_step(
    *,
    key_path: Path,
    member_id: str,
    key_input_file: Any,
    env: Mapping[str, str],
    transport: Any,
    base_url: str,
    timeout: float,
) -> dict[str, Any]:
    if key_path.is_file():
        existing = _read_key_file(key_path)
        if existing is None:
            return _step(
                STATE_FAILED,
                1,
                "role_key_stale",
                "现有 Key 文件为空/不可读/含非法字符；拒绝覆盖",
            )
        try:
            permissions = _enforce_private_permissions(key_path)
        except ProvisionError as exc:
            return _step(STATE_FAILED, 1, exc.code, exc.detail)
        verdict, actual = _role_key_verdict(transport, base_url, existing, member_id, timeout)
        if verdict == "ok":
            return _step(
                STATE_SKIPPED,
                1,
                None,
                f"现有 Key 文件身份核验通过（member_id={actual}）；"
                f"未改写；permissions={permissions}",
            )
        code = {
            "mismatch": "identity_mismatch",
            "invalid": "role_key_stale",
        }.get(verdict, "http_error")
        return _step(
            STATE_FAILED, 1, code, f"现有 Key 文件核验失败 verdict={verdict}；拒绝覆盖"
        )

    candidate = _load_key_source(key_input_file, env)
    if candidate is None:
        return _step(
            STATE_FAILED,
            1,
            "role_key_unknown",
            f"未提供可用的 --key-input-file，且环境变量 {ROLE_KEY_ENV} 为空/不可用",
        )
    verdict, actual = _role_key_verdict(transport, base_url, candidate, member_id, timeout)
    if verdict != "ok":
        code = {
            "mismatch": "identity_mismatch",
            "invalid": "role_key_unknown",
        }.get(verdict, "http_error")
        return _step(
            STATE_FAILED, 1, code, f"Key 来源核验失败 verdict={verdict}；未写入"
        )

    try:
        permissions = _write_key_file(key_path, candidate)
    except ProvisionError as exc:
        return _step(STATE_FAILED, 1, exc.code, exc.detail)
    return _step(
        STATE_SUCCEEDED,
        1,
        None,
        f"已原子写入 Key 文件（permissions={permissions}，member_id={actual}）",
    )


# ---------------------------------------------------------------------------
# preflight（只证可配置事实；不启动 CLI）
# ---------------------------------------------------------------------------


def _path_matches(value: Any, expected: Path, project_root: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = Path(value.strip())
    if not candidate.is_absolute():
        candidate = Path(project_root) / candidate
    try:
        normalized = os.path.normcase(os.path.normpath(str(candidate.resolve())))
        wanted = os.path.normcase(os.path.normpath(str(expected.resolve())))
    except OSError:  # pragma: no cover - 解析失败按不匹配处理
        return False
    return normalized == wanted


def _is_hex_fingerprint(value: Any) -> bool:
    """64 位十六进制内容指纹（只做形状校验；语义比较由调用方完成）。"""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _roster_row(payload: Any, member_id: str) -> Optional[Mapping[str, Any]]:
    if not isinstance(payload, list):
        return None
    for entry in payload:
        if isinstance(entry, Mapping) and str(entry.get("member_id") or "") == member_id:
            return entry
    return None


def _run_preflight_step(
    *,
    project_id: str,
    member_id: str,
    operation_key: str,
    project_root: Path,
    paths: Mapping[str, Path],
    role_key: Optional[str],
    operator_key: Optional[str],
    expected_choice_fingerprint: Optional[str],
    cli_executable: Any,
    transport: Any,
    base_url: str,
    timeout: float,
) -> dict[str, Any]:
    if role_key is None:
        return _step(
            STATE_FAILED,
            1,
            "role_key_unknown",
            "没有可用于预检的角色 Key（先完成 key_file 步骤）",
        )
    verdict, actual = _role_key_verdict(transport, base_url, role_key, member_id, timeout)
    if verdict == "mismatch":
        return _step(
            STATE_FAILED,
            1,
            "identity_mismatch",
            f"GET {_me_path()} 返回 member_id={actual}，不是目标角色",
        )
    if verdict == "invalid":
        return _step(STATE_FAILED, 1, "role_key_stale", "角色 Key 已无法通过身份核验")
    if verdict != "ok":
        return _step(STATE_FAILED, 1, "http_error", f"GET {_me_path()} 请求失败")

    roster_response = transport.request_json(
        "GET", _api(base_url, _roster_path(project_id)), api_key=role_key, timeout=timeout
    )
    if roster_response.status != 200:
        return _step(STATE_FAILED, 1, "http_error", "GET 项目名册失败")
    row = _roster_row(roster_response.payload, member_id)
    if row is None:
        return _step(
            STATE_FAILED, 1, "identity_mismatch", "目标角色不在项目名册（project_agents）中"
        )

    paths_registered = all(
        _path_matches(row.get(f"{kind}_path"), paths[kind], project_root)
        for kind in PROFILE_KINDS
    )
    registration = "not_needed"
    local_files = sum(1 for kind in PROFILE_KINDS if paths[kind].is_file())
    if not paths_registered:
        # 绝不调用全量 POST /sync；也不再用 PUT .../profile 做登记（那只写文件正文）。
        # 只允许对本角色调用 human-only 的 provision/roster-paths 登记三个相对路径。
        if operator_key is None:
            return _step(
                STATE_FAILED,
                1,
                "operator_key_missing",
                "名册 identity/soul/user 路径与本角色生成文件不一致；"
                "缺少 operator 凭据，未做单角色路径登记（可恢复）；"
                "roster_paths=not_registered roster_path_fields=not_reflected "
                "registration=operator_key_missing",
            )
        register_response = transport.request_json(
            "POST",
            _api(base_url, _provision_roster_paths_path(project_id, member_id)),
            api_key=operator_key,
            body={"operation_key": operation_key, **_roster_relative_paths(member_id)},
            timeout=timeout,
        )
        if register_response.status != 200:
            return _step(
                STATE_FAILED,
                1,
                "http_error",
                f"单角色名册路径登记失败（HTTP {register_response.status}）",
            )
        registration = "roster_paths_endpoint"
        refreshed = transport.request_json(
            "GET", _api(base_url, _roster_path(project_id)), api_key=role_key, timeout=timeout
        )
        if refreshed.status != 200:
            return _step(
                STATE_FAILED, 1, "http_error", "单角色名册路径登记后回读名册失败"
            )
        refreshed_row = _roster_row(refreshed.payload, member_id)
        paths_registered = refreshed_row is not None and all(
            _path_matches(refreshed_row.get(f"{kind}_path"), paths[kind], project_root)
            for kind in PROFILE_KINDS
        )
        if not paths_registered:
            # 登记接口报告成功，但名册路径索引仍未指向本角色生成文件：如实失败，不假装成功。
            return _step(
                STATE_FAILED,
                1,
                "identity_mismatch",
                "单角色名册路径登记后仍未指向本角色生成文件；"
                "roster_paths=registration_attempted roster_path_fields=not_reflected "
                "registration=roster_paths_endpoint",
            )
    paths_state = "registered"
    roster_path_fields = "registered"

    # 补正 F4：三档必须真实存在、可读（非空、非 reparse point），否则不算配置成功。
    unreadable: list[str] = []
    for kind in PROFILE_KINDS:
        path = paths[kind]
        if not path.is_file() or _is_reparse_point(path):
            unreadable.append(PROFILE_FILENAMES[kind])
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            unreadable.append(PROFILE_FILENAMES[kind])
            continue
        if not text.strip():
            unreadable.append(PROFILE_FILENAMES[kind])
    if unreadable:
        return _step(
            STATE_FAILED,
            1,
            "identity_mismatch",
            "本角色身份档缺失/不可读/为空：" + ",".join(unreadable)
            + f"；roster_paths={paths_state} roster_path_fields={roster_path_fields} "
            f"registration={registration} local_files={local_files}/3 "
            "profile_files=not_readable",
        )
    local_files = len(PROFILE_KINDS)

    # 补正 F4：角色列表读取必须成功**并且**包含目标；失败/找不到目标一律失败，
    # 绝不跳过 expected 比较。
    roles_response = transport.request_json(
        "GET", _api(base_url, _roles_path(project_id)), api_key=role_key, timeout=timeout
    )
    if roles_response.status != 200 or not isinstance(roles_response.payload, list):
        return _step(
            STATE_FAILED, 1, "http_error", "GET 项目角色列表失败或响应形状不是列表"
        )
    roles_item: Optional[Mapping[str, Any]] = None
    for item in roles_response.payload:
        if isinstance(item, Mapping) and str(item.get("member_id") or "") == member_id:
            roles_item = item
            break
    if roles_item is None:
        return _step(
            STATE_FAILED, 1, "identity_mismatch", "目标角色不在 GET 角色列表投影中"
        )
    runner_out = (
        roles_item.get("runner") if isinstance(roles_item.get("runner"), Mapping) else {}
    )
    model_out = (
        roles_item.get("model") if isinstance(roles_item.get("model"), Mapping) else {}
    )
    expected_runner = runner_out.get("runner_id")
    expected_model = model_out.get("model_id")
    expected_alias = model_out.get("model_alias")
    roles_binding_state = roles_item.get("binding_state")
    choice_source = model_out.get("choice_source")
    choice_id = model_out.get("choice_id")
    choice_mismatch = bool(model_out.get("choice_binding_mismatch"))
    if not (isinstance(expected_runner, str) and expected_runner.strip()):
        return _step(STATE_FAILED, 1, "identity_mismatch", "角色列表投影缺少 runner_id")
    if not (isinstance(expected_model, str) and expected_model.strip()):
        return _step(STATE_FAILED, 1, "identity_mismatch", "角色列表投影缺少 model_id")
    if roles_binding_state != "bound":
        return _step(
            STATE_FAILED,
            1,
            "identity_mismatch",
            f"角色列表 binding_state={roles_binding_state}，不是 bound",
        )
    # choice_source=creation_operation 由服务端按“当前绑定六维事实 == 创建操作所选 choice”
    # 现算，是绑定来源/指纹一致的权威证据；legacy/mismatch 一律不通过。
    if choice_source != "creation_operation" or not (
        isinstance(choice_id, str) and choice_id.strip()
    ) or choice_mismatch:
        return _step(
            STATE_FAILED,
            1,
            "identity_mismatch",
            f"角色绑定来源/指纹未与创建操作一致（choice_source={choice_source}，"
            f"choice_binding_mismatch={choice_mismatch}）",
        )
    # 补正 G3：还要拿到**创建操作所选 choice** 的预期指纹（由作业投影给出，与绑定投影
    # 同一算法），稍后与本次读取的绑定投影逐对比较；只有非空/64hex 形状不算通过。
    if not _is_hex_fingerprint(expected_choice_fingerprint):
        if operator_key is None:
            return _step(
                STATE_FAILED,
                1,
                "operator_key_missing",
                "缺少 operator 凭据，无法取得创建操作所选 choice 的预期绑定指纹；"
                "不宣称绑定一致（可恢复）",
            )
        return _step(
            STATE_FAILED,
            1,
            "identity_mismatch",
            "作业响应缺少创建操作所选 choice 的预期绑定指纹"
            f"（choice_source={choice_source}）；拒绝只按形状宣称绑定一致",
        )

    binding_response = transport.request_json(
        "GET",
        _api(base_url, _agent_sub_path(project_id, member_id, "binding")),
        api_key=role_key,
        timeout=timeout,
    )
    if binding_response.status != 200:
        return _step(STATE_FAILED, 1, "http_error", "GET 角色绑定投影失败")
    binding_payload = (
        binding_response.payload if isinstance(binding_response.payload, Mapping) else {}
    )
    if binding_payload.get("binding_state") != "bound":
        return _step(
            STATE_FAILED,
            1,
            "identity_mismatch",
            f"绑定投影 binding_state={binding_payload.get('binding_state')}，不是 bound",
        )
    binding = binding_payload.get("binding")
    if not isinstance(binding, Mapping):
        return _step(
            STATE_FAILED, 1, "identity_mismatch", "绑定投影缺失（binding=null），拒绝宣称已配置"
        )
    binding_runner = binding.get("runner_id")
    binding_model = binding.get("model_id")
    binding_alias = binding.get("model_alias")
    binding_source = binding.get("model_source")
    binding_provider = binding.get("provider_id")
    binding_connection = binding.get("connection_ref")
    binding_fingerprint = binding.get("binding_fingerprint")
    for field, value in (
        ("runner_id", binding_runner),
        ("model_id", binding_model),
        ("model_source", binding_source),
        ("provider_id", binding_provider),
        ("connection_ref", binding_connection),
    ):
        if not (isinstance(value, str) and value.strip()):
            return _step(
                STATE_FAILED, 1, "identity_mismatch", f"绑定投影缺少 {field}"
            )
    if binding_runner != expected_runner:
        return _step(
            STATE_FAILED, 1, "identity_mismatch", "绑定投影 runner_id 与角色列表投影不一致"
        )
    if binding_model != expected_model:
        return _step(
            STATE_FAILED, 1, "identity_mismatch", "绑定投影 model_id 与角色列表投影不一致"
        )
    if (binding_alias or None) != (expected_alias or None):
        return _step(
            STATE_FAILED, 1, "identity_mismatch", "绑定投影 model_alias 与角色列表投影不一致"
        )
    if not _is_hex_fingerprint(binding_fingerprint):
        return _step(
            STATE_FAILED, 1, "identity_mismatch", "绑定投影缺少可解析的 binding_fingerprint"
        )
    # 补正 G3：把“创建操作所选 choice 的预期指纹”与**本次读取**的绑定投影指纹逐对比较。
    # 两次 GET 之间连接/来源/provider 漂移会在这里暴露（不只比 runner/model/alias 三个
    # 直接字段，也不只检 64hex 形状）；不一致即失败，绝不升级为“精确绑定通过”。
    if (
        str(binding_fingerprint).lower()
        != str(expected_choice_fingerprint).lower()
    ):
        return _step(
            STATE_FAILED,
            1,
            "identity_mismatch",
            "绑定投影指纹与创建操作所选 choice 的预期指纹不一致"
            "（choice_source=creation_operation choice/fingerprint 矛盾；"
            "两次投影之间绑定事实已变更）；拒绝按已配置上报",
        )

    cli_entry = "not_checked"
    if cli_executable:
        if os.path.exists(Path(str(cli_executable)).expanduser()):
            cli_entry = "present"
        else:
            return _step(
                STATE_FAILED,
                1,
                "cli_executable_missing",
                "显式 --cli-executable 路径不存在（只做存在性检查，未执行）",
            )

    detail = (
        f"member_id={actual} roster_paths={paths_state} roster_path_fields={roster_path_fields} "
        f"registration={registration} local_files={local_files}/3 "
        f"profile_files=readable binding_state={binding_payload.get('binding_state')} "
        f"runner_id={binding_runner} model_id={binding_model} "
        f"model_alias={binding_alias} model_source={binding_source} "
        f"connection_ref_present=true choice_source={choice_source} "
        f"choice_fingerprint=verified binding_fingerprint=verified cli_entry={cli_entry}"
    )
    return _step(STATE_SUCCEEDED, 1, None, detail)


# ---------------------------------------------------------------------------
# ACK（targeted 单步回报；operator 凭据缺失则绝不 ACK）
# ---------------------------------------------------------------------------


def _capture_generation(job: Mapping[str, Any]) -> dict[str, Any]:
    """从作业公开响应捕获**本次作业代际**（补正 F1）。

    代际 = ``revision`` + ``credential_version`` + 每一步的 ``state/attempts``。它必须在
    任何本地副作用之前捕获，并在 ACK 时原样回传；绝不在回报时用新的 GET 把旧工作套到
    新 attempt 上。
    """
    revision = job.get("revision")
    credential_version = job.get("credential_version")
    steps_raw = job.get("steps")
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or isinstance(credential_version, bool)
        or not isinstance(credential_version, int)
        or not isinstance(steps_raw, Mapping)
    ):
        raise ProvisionError("http_error", "作业响应缺少 revision/credential_version/steps")
    steps: dict[str, dict[str, Any]] = {}
    for step in STEP_ORDER:
        entry = steps_raw.get(step)
        if not isinstance(entry, Mapping) or not isinstance(entry.get("attempts"), int):
            raise ProvisionError("http_error", f"作业响应缺少步骤 {step} 的 attempts")
        steps[step] = {
            "state": str(entry.get("state") or ""),
            "attempts": int(entry.get("attempts")),
        }
    return {
        "revision": int(revision),
        "credential_version": int(credential_version),
        "steps": steps,
    }


def _credential_version_field(payload: Mapping[str, Any], field: str) -> Optional[int]:
    """读作业响应里的正整数凭据版本计数；缺失/非法一律 ``None``（调用方 fail closed）。"""
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return int(value)


def _job_expected_fingerprint(payload: Mapping[str, Any]) -> Optional[str]:
    """读作业响应里创建操作所选 choice 的预期绑定指纹；缺失/形状非法一律 ``None``。"""
    value = payload.get("expected_binding_fingerprint")
    return str(value) if _is_hex_fingerprint(value) else None


def _ensure_job(
    *,
    transport: Any,
    base_url: str,
    project_id: str,
    member_id: str,
    operation_key: str,
    resume: bool,
    resume_steps: Any,
    operator_key: str,
    timeout: float,
    request_key: Optional[str] = None,
    lease_token: Optional[str] = None,
) -> dict[str, Any]:
    """在**本地副作用之前**确保 provision 作业存在并捕获作业代际。

    先 ``GET``；404 时按合同创建；已存在且 ``--resume`` 时定向续跑；已存在且未给
    ``--resume`` 时保持既有作业不动（零写）。返回 ``action/status/revision/generation``；
    任何非预期状态都抛 ``ProvisionError``，调用方据此**不执行本地副作用**、不 ACK，也不把
    旧结果套到新代际（补正 F1/F3/G1）。

    补正 G1：作业快照里的 ``credential_version`` 必须与**读取时角色行当前**的
    ``role_credential_version`` 一致，否则旧成功已被轮换作废：
    - ``--resume`` 未给 → 抛 ``resume_required``（不写任何本地文件），恢复必须显式；
    - 给了 ``--resume`` → 服务端会强制重开凭据相关步骤，按新代际继续。

    续跑一个已 ``succeeded`` 的作业时服务端返回 409 ``provision_job_terminal``（凭据版本
    未变）——这等价于“没有待执行步骤”，按 ``action='terminal'`` 如实返回，由调用方走
    幂等 no-op，而不是把重复 apply 变成失败。补正 H1 后，降为 no-op 需要**两个都成立**：

    - 409 响应体里逐字命中白名单的精确错误码 ``provision_job_terminal``（默认
      :class:`UrlLibTransport` 有界解析后只保留白名单码；未知/缺失/非法码一律失败）；
    - 当前事实吻合：POST 前快照未轮换且状态已 ``succeeded``，409 之后重新读取仍然 200、
      仍是**同一 revision/凭据版本**的 ``succeeded``。

    其它任何 409（禁用/离册/归档/权限/操作不匹配），即便随后事实恢复、GET 又变 200，也
    按失败拒绝，绝不改判成功、绝不继续本地副作用。
    """
    url = _api(base_url, _provision_path(project_id, member_id))
    query = urlencode({"operation_key": operation_key})
    response = transport.request_json(
        "GET", f"{url}?{query}", api_key=operator_key, timeout=timeout
    )
    if response.status == 200:
        current = response.payload if isinstance(response.payload, Mapping) else {}
        snapshot_version = _credential_version_field(current, "credential_version")
        role_version = _credential_version_field(current, "role_credential_version")
        if snapshot_version is None or role_version is None:
            # 缺任一版本都无法判断“旧成功是否仍然有效”：fail closed，不猜。
            raise ProvisionError(
                "http_error",
                "作业响应缺少可核验的凭据版本（credential_version/role_credential_version）",
            )
        rotated = snapshot_version != role_version
        if not resume:
            if rotated:
                raise ProvisionError(
                    "resume_required",
                    "角色凭据版本已变化（credential_version="
                    f"{snapshot_version}→{role_version}）；旧成功不再有效，需显式 --resume 重开",
                )
            return {
                "action": "existing",
                "status": current.get("status"),
                "revision": current.get("revision"),
                "generation": _capture_generation(current),
                "expected_binding_fingerprint": _job_expected_fingerprint(current),
            }
        body = {
            "operation_key": operation_key,
            "resume": True,
            "steps": list(resume_steps) if resume_steps is not None else None,
        }
        if request_key is not None:
            body["request_key"] = request_key
        if lease_token is not None:
            body["lease_token"] = lease_token
        posted = transport.request_json(
            "POST", url, api_key=operator_key, body=body, timeout=timeout
        )
        if posted.status == 409:
            # 补正 H1：409 只有**逐字命中白名单**的精确 ``provision_job_terminal`` 才可能
            # 是幂等 no-op。禁用/离册/归档/权限/操作不匹配等 409 即使随后事实恢复、GET 又
            # 变 200，也不得改判成功；未知/缺失/非法错误码同样失败。默认
            # :class:`UrlLibTransport` 只在有界读取后把白名单码带进内存，不回显/落盘远端正文。
            posted_code = _whitelisted_response_error_code(posted)
            if posted_code != "provision_job_terminal":
                recognized = (
                    f"错误码 {posted_code}"
                    if posted_code is not None
                    else "错误码缺失/不在白名单"
                )
                raise ProvisionError(
                    "http_error",
                    f"续跑 provision 作业被拒绝（HTTP 409，{recognized}）；"
                    "当前事实不满足精确终态，拒绝改判成功",
                )
            if current.get("status") != STATE_SUCCEEDED or rotated:
                raise ProvisionError(
                    "http_error",
                    "续跑 provision 作业被拒绝（HTTP 409，provision_job_terminal），"
                    "但 POST 前快照不是未轮换的 succeeded；拒绝改判成功",
                )
            # POST 前已是未轮换的成功快照，且错误码精确：409 之后**重新读取**当前事实，
            # 必须仍是同一代际（revision/凭据版本一致）的 succeeded（GET 200 也再次通过
            # 项目/角色/成员/名册/归档与身份守卫），才允许幂等 no-op。
            fresh = transport.request_json(
                "GET", f"{url}?{query}", api_key=operator_key, timeout=timeout
            )
            fresh_payload = (
                fresh.payload if isinstance(fresh.payload, Mapping) else {}
            )
            fresh_snapshot = _credential_version_field(
                fresh_payload, "credential_version"
            )
            fresh_role = _credential_version_field(
                fresh_payload, "role_credential_version"
            )
            fresh_revision = fresh_payload.get("revision")
            snapshot_revision = current.get("revision")
            if (
                fresh.status == 200
                and fresh_payload.get("status") == STATE_SUCCEEDED
                and fresh_snapshot is not None
                and fresh_snapshot == fresh_role
                and fresh_snapshot == snapshot_version
                and not isinstance(fresh_revision, bool)
                and isinstance(fresh_revision, int)
                and fresh_revision == snapshot_revision
            ):
                return {
                    "action": "terminal",
                    "status": fresh_payload.get("status"),
                    "revision": fresh_payload.get("revision"),
                    "generation": _capture_generation(fresh_payload),
                    "expected_binding_fingerprint": _job_expected_fingerprint(
                        fresh_payload
                    ),
                }
            raise ProvisionError(
                "http_error",
                "续跑 provision 作业被拒绝（HTTP 409，provision_job_terminal），"
                f"但当前事实核验未确认同一代际的精确终态（HTTP {fresh.status}）；"
                "拒绝改判成功",
            )
        if posted.status not in (200, 201):
            raise ProvisionError("http_error", f"续跑 provision 作业失败（HTTP {posted.status}）")
        job = posted.payload if isinstance(posted.payload, Mapping) else {}
        job_snapshot = _credential_version_field(job, "credential_version")
        job_role = _credential_version_field(job, "role_credential_version")
        if job_snapshot is None or job_role is None or job_snapshot != job_role:
            # 续跑响应仍带着已作废/不可核验的代际：绝不据此 ACK。
            raise ProvisionError(
                "http_error",
                "续跑 provision 作业响应缺少一致的可核验凭据版本；拒绝按旧成功继续",
            )
        return {
            "action": "resumed",
            "status": job.get("status"),
            "revision": job.get("revision"),
            "generation": _capture_generation(job),
            "expected_binding_fingerprint": _job_expected_fingerprint(job),
        }
    if response.status == 404:
        body = {"operation_key": operation_key, "resume": False, "steps": None}
        if request_key is not None:
            body["request_key"] = request_key
        if lease_token is not None:
            body["lease_token"] = lease_token
        posted = transport.request_json(
            "POST", url, api_key=operator_key, body=body, timeout=timeout
        )
        if posted.status not in (200, 201):
            raise ProvisionError("http_error", f"创建 provision 作业失败（HTTP {posted.status}）")
        job = posted.payload if isinstance(posted.payload, Mapping) else {}
        job_snapshot = _credential_version_field(job, "credential_version")
        job_role = _credential_version_field(job, "role_credential_version")
        if job_snapshot is None or job_role is None or job_snapshot != job_role:
            raise ProvisionError(
                "http_error",
                "创建 provision 作业响应缺少一致的可核验凭据版本；拒绝继续本地副作用",
            )
        return {
            "action": "created",
            "status": job.get("status"),
            "revision": job.get("revision"),
            "generation": _capture_generation(job),
            "expected_binding_fingerprint": _job_expected_fingerprint(job),
        }
    raise ProvisionError("http_error", f"读取 provision 作业失败（HTTP {response.status}）")


def _send_acks(
    *,
    transport: Any,
    base_url: str,
    project_id: str,
    member_id: str,
    operation_key: str,
    steps: Sequence[str],
    states: Mapping[str, Mapping[str, Any]],
    generation: Mapping[str, Any],
    operator_key: str,
    timeout: float,
    request_key: Optional[str] = None,
    lease_token: Optional[str] = None,
) -> dict[str, Any]:
    """按**捕获的代际**回报单步结果（补正 F1/F3）。

    - 每一步的 ``attempt`` 取捕获代际里的值，绝不重新 GET 作业；
    - ``revision`` 从捕获值开始，之后只用**本次 ACK 响应**推进（同一代际的自推进）；
    - ``credential_version`` 恒为捕获值，服务端在写事务内比对作业快照与角色当前值；
    - 只回报调用方给定的 ``steps``（本次真正待执行的步骤），已完成的步骤不重复 ACK。
    """
    ack: dict[str, Any] = {"sent": False, "reason": None, "results": []}
    ack_url = _api(base_url, _provision_path(project_id, member_id)) + "/ack"
    current_revision = int(generation["revision"])
    credential_version = int(generation["credential_version"])
    for step in steps:
        result = states[step]
        attempt = int(generation["steps"][step]["attempts"])
        body = {
            "operation_key": operation_key,
            "step": step,
            "attempt": attempt,
            "revision": current_revision,
            "credential_version": credential_version,
            "state": result["state"],
            "error_code": result.get("error_code"),
        }
        if request_key is not None:
            body["request_key"] = request_key
        if lease_token is not None:
            body["lease_token"] = lease_token
        response = transport.request_json(
            "POST", ack_url, api_key=operator_key, body=body, timeout=timeout
        )
        if response.status != 200:
            ack["results"].append(
                {
                    "step": step,
                    "sent": False,
                    "http_status": response.status,
                    "reason": "ack_stale" if response.status == 409 else "ack_failed",
                }
            )
            ack["reason"] = "ack_stale" if response.status == 409 else "ack_failed"
            break
        payload = response.payload if isinstance(response.payload, Mapping) else {}
        next_revision = payload.get("revision")
        if isinstance(next_revision, bool) or not isinstance(next_revision, int):
            ack["results"].append(
                {
                    "step": step,
                    "sent": False,
                    "http_status": response.status,
                    "reason": "ack_failed",
                }
            )
            ack["reason"] = "ack_failed"
            break
        current_revision = int(next_revision)
        ack["results"].append(
            {
                "step": step,
                "sent": True,
                "http_status": response.status,
                "state": result["state"],
                "attempt": attempt,
                "revision": current_revision,
                "credential_version": credential_version,
            }
        )
    ack["sent"] = bool(ack["results"]) and all(item["sent"] for item in ack["results"])
    if ack["sent"]:
        ack["reason"] = None
    elif ack["reason"] is None:
        ack["reason"] = "ack_failed"
    return ack


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def parse_steps(value: Any) -> list[str]:
    """解析 ``--steps``（``profile,key_file,preflight`` 的非空子集，按固定顺序）。"""
    if value is None:
        return list(STEP_ORDER)
    if isinstance(value, str):
        tokens = [token.strip() for token in value.split(",")]
    else:
        tokens = [str(token).strip() for token in value]
    tokens = [token for token in tokens if token]
    if not tokens:
        raise ValueError("--steps 不能为空；可选 profile,key_file,preflight")
    unknown = sorted({token for token in tokens if token not in STEP_ORDER})
    if unknown:
        raise ValueError(
            "--steps 只支持 profile,key_file,preflight，实际包含：" + ",".join(unknown)
        )
    wanted = set(tokens)
    return [step for step in STEP_ORDER if step in wanted]


def _validate_operation_key(value: Any) -> str:
    text = str(value or "")
    if not (8 <= len(text) <= 128):
        raise ValueError("--operation-key 长度必须在 8–128 之间")
    if any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in text):
        raise ValueError("--operation-key 只允许可打印 ASCII 安全 token")
    return text


def _resolve_project_root(project_root: Any) -> Path:
    declared = Path(project_root).expanduser()
    # 补正 F8：必须在 resolve() **之前**检查声明根自身及其祖先，否则 junction 会被
    # canonicalize 悄悄消去，后续守卫再也看不到链接边界。
    _assert_root_chain_has_no_reparse(declared)
    try:
        resolved = declared.resolve()
    except OSError as exc:
        raise ProvisionError("profile_root_invalid", "项目根无法解析") from exc
    if not resolved.is_dir():
        raise ProvisionError("profile_root_invalid", "项目根不是已存在的目录")
    return resolved


def _abort(
    document: dict[str, Any],
    states: Mapping[str, dict[str, Any]],
    selected: Sequence[str],
    code: str,
    detail: str,
) -> tuple[dict[str, Any], int]:
    for step in selected:
        states[step].update(
            {"state": STATE_FAILED, "attempts": 0, "error_code": code, "detail": detail}
        )
    document["error_code"] = code
    document["conclusion"] = "failed"
    return document, 1


def run_provision(
    *,
    project_id: str,
    member_id: str,
    operation_key: str,
    project_root: Any,
    key_root: Any = None,
    base_url: str = DEFAULT_BASE_URL,
    apply: bool = False,
    overwrite_profile: bool = False,
    steps: Any = None,
    resume: bool = False,
    resume_steps: Any = None,
    key_input_file: Any = None,
    cli_executable: Any = None,
    lock_stale_seconds: float = DEFAULT_LOCK_STALE_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    transport: Any = None,
    environ: Any = None,
    repo_root: Any = REPO_ROOT,
) -> tuple[dict[str, Any], int]:
    """执行一次 provision；返回 ``(JSON 文档, 退出码)``。

    默认 dry-run：零写入、零 HTTP；只有 ``apply=True`` 才写身份档/Key 文件并按需 ACK。
    """
    env = (
        {str(key): str(value) for key, value in os.environ.items()}
        if environ is None
        else {str(key): str(value) for key, value in environ.items()}
    )
    # 构造默认传输不做任何 IO；dry-run 永不调用它。
    active_transport = transport if transport is not None else UrlLibTransport(timeout_seconds)
    base = str(base_url or DEFAULT_BASE_URL).rstrip("/")
    selected = parse_steps(steps)
    states: dict[str, dict[str, Any]] = {
        step: _step(STATE_PENDING, 0, None, "not selected by --steps") for step in STEP_ORDER
    }
    for step in selected:
        states[step]["detail"] = "not run"

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": MODE_APPLY if apply else MODE_DRY_RUN,
        "project_id": project_id,
        "member_id": member_id,
        "operation_key": operation_key,
        "base_url": base,
        "steps": states,
        "ack": {"sent": False, "reason": None, "results": []},
        "job": {"action": "none", "status": None, "revision": None},
        "lock": None,
        "identity_lock": None,
        "error_code": None,
        "conclusion": "failed",
    }

    # 1) 显式根与路径守卫：任何逃逸/仓库内 Key 根都在写任何文件之前拒绝。
    try:
        project_root_resolved = _resolve_project_root(project_root)
    except ProvisionError as exc:
        document["project_root"] = str(project_root)
        return _abort(document, states, selected, exc.code, exc.detail)
    document["project_root"] = str(project_root_resolved)

    key_root_value = DEFAULT_KEY_ROOT if key_root is None else key_root
    try:
        key_root_declared = Path(key_root_value).expanduser()
        _assert_root_chain_has_no_reparse(key_root_declared)
        key_root_resolved = key_root_declared.resolve()
    except ProvisionError as exc:
        return _abort(document, states, selected, exc.code, exc.detail)
    except OSError:
        return _abort(
            document, states, selected, "key_write_failed", "Key 根无法解析"
        )
    document["key_root"] = str(key_root_resolved)
    if _path_is_within(key_root_resolved, repo_root):
        return _abort(
            document,
            states,
            selected,
            "key_root_inside_repo",
            _REASON_DETAILS["key_root_inside_repo"],
        )

    try:
        profile_paths = profile_target_paths(project_root_resolved, member_id)
    except ProvisionError as exc:
        return _abort(document, states, selected, exc.code, exc.detail)
    try:
        target_key_path = key_file_path(key_root_resolved, member_id)
    except ProvisionError as exc:
        return _abort(document, states, selected, exc.code, exc.detail)
    document["key_file_path"] = str(target_key_path)
    lock_path = lock_path_for(target_key_path)

    # 2) dry-run：只读本地检查 + 打印计划，零写入、零 HTTP。
    if not apply:
        if "profile" in selected:
            plan = _profile_plan(profile_paths, overwrite=overwrite_profile)
            local_problem = None
            for kind in PROFILE_KINDS:
                if profile_paths[kind].parent.exists() and not profile_paths[kind].parent.is_dir():
                    local_problem = "身份档目录不是目录"
            if local_problem:
                states["profile"] = _step(
                    STATE_FAILED, 0, "profile_root_invalid", local_problem
                )
            else:
                states["profile"] = _step(
                    STATE_PLANNED,
                    0,
                    None,
                    f"create={plan['create']} keep={plan['keep']} "
                    f"overwrite={plan['overwrite']} atomic=true",
                )
        if "key_file" in selected:
            if target_key_path.is_file():
                if _read_key_file(target_key_path) is None:
                    states["key_file"] = _step(
                        STATE_FAILED, 0, "role_key_stale", "现有 Key 文件为空/不可读/含非法字符"
                    )
                else:
                    states["key_file"] = _step(
                        STATE_PLANNED,
                        0,
                        None,
                        "现有 Key 文件将在 --apply 时做只读身份核验；dry-run 不发 HTTP",
                    )
            else:
                label = _key_source_label(key_input_file, env)
                if label is None:
                    states["key_file"] = _step(
                        STATE_FAILED,
                        0,
                        "role_key_unknown",
                        f"未找到 Key 来源（--key-input-file / {ROLE_KEY_ENV}）",
                    )
                else:
                    states["key_file"] = _step(
                        STATE_PLANNED,
                        0,
                        None,
                        f"将从 {label} 读取 Key；--apply 时先核身份再原子写入",
                    )
        if "preflight" in selected:
            states["preflight"] = _step(
                STATE_PLANNED,
                0,
                None,
                "计划：GET /api/members/me + 名册路径 + roles 投影 + binding；"
                "名册路径不一致时仅在有 operator 凭据时对单角色调用 "
                "POST .../provision/roster-paths 登记相对路径；"
                "dry-run 零 HTTP；不启动 CLI；cli_entry=not_checked",
            )
        document["ack"] = {"sent": False, "reason": "not_apply_mode", "results": []}
        failed = [step for step in selected if states[step]["state"] == STATE_FAILED]
        if failed:
            document["error_code"] = states[failed[0]]["error_code"]
            document["conclusion"] = "failed"
            return document, 1
        document["conclusion"] = "planned"
        return document, 0

    # 3) apply：身份档锁 + Key 锁 → 捕获作业代际 → 三步 → ACK → 反向释放锁。
    #
    # 补正 F5：同一个身份档可能在**不同的 --key-root** 下被并发配置，因此除 Key 锁之外
    # 还要拿身份档目录内的锁；两者按固定顺序获取，失败时反向释放自己已持有的锁。
    try:
        profile_lock_path = profile_lock_path_for(project_root_resolved, member_id)
    except ProvisionError as exc:
        return _abort(document, states, selected, exc.code, exc.detail)

    lock_handles: list[tuple[Path, dict[str, Any]]] = []
    try:
        for candidate in (profile_lock_path, lock_path):
            lock_handles.append(
                (candidate, acquire_lock(candidate, lock_stale_seconds))
            )
    except ProvisionError as exc:
        for held_path, held_handle in reversed(lock_handles):
            release_lock(held_path, held_handle)
        return _abort(document, states, selected, exc.code, exc.detail)
    document["lock"] = lock_handles[-1][1]
    document["identity_lock"] = lock_handles[0][1]

    try:
        operator_key = _resolve_operator_key(env)
        generation: Optional[dict[str, Any]] = None
        expected_choice_fingerprint: Optional[str] = None

        # 1) 本地副作用之前先确保作业存在并捕获作业代际（补正 F1）。
        if operator_key is not None:
            try:
                job_info: dict[str, Any] = _ensure_job(
                    transport=active_transport,
                    base_url=base,
                    project_id=project_id,
                    member_id=member_id,
                    operation_key=operation_key,
                    resume=resume,
                    resume_steps=resume_steps,
                    operator_key=operator_key,
                    timeout=timeout_seconds,
                )
            except ProvisionError as exc:
                # 补正 G1：作业无法确认（轮换作废 / 权限 / 离册 / 归档 / 其它 409 或 HTTP
                # 错误）时**绝不继续本地副作用**，也不把结果改判成成功。显式区分
                # resume_required，让恢复动作明确可见。
                reason = "resume_required" if exc.code == "resume_required" else "ack_failed"
                for step in selected:
                    states[step] = _step(STATE_FAILED, 0, exc.code, exc.detail)
                document["job"] = {
                    "action": "none",
                    "status": None,
                    "revision": None,
                    "error_code": exc.code,
                    "detail": exc.detail,
                }
                document["ack"] = {"sent": False, "reason": reason, "results": []}
                document["error_code"] = exc.code
                document["conclusion"] = "failed"
                return document, 1
            else:
                generation = job_info.get("generation")
                expected_choice_fingerprint = job_info.get(
                    "expected_binding_fingerprint"
                )
        else:
            job_info = {"action": "none", "status": None, "revision": None}

        # 2) 本地三步（顺序固定）。
        if "profile" in selected:
            try:
                states["profile"] = _run_profile_step(
                    project_root=project_root_resolved,
                    member_id=member_id,
                    project_id=project_id,
                    paths=profile_paths,
                    overwrite=overwrite_profile,
                )
            except ProvisionError as exc:
                states["profile"] = _step(STATE_FAILED, 1, exc.code, exc.detail)

        if "key_file" in selected:
            try:
                states["key_file"] = _run_key_step(
                    key_path=target_key_path,
                    member_id=member_id,
                    key_input_file=key_input_file,
                    env=env,
                    transport=active_transport,
                    base_url=base,
                    timeout=timeout_seconds,
                )
            except ProvisionError as exc:
                states["key_file"] = _step(STATE_FAILED, 1, exc.code, exc.detail)

        if "preflight" in selected:
            role_key = (
                _read_key_file(target_key_path) if target_key_path.is_file() else None
            )
            try:
                states["preflight"] = _run_preflight_step(
                    project_id=project_id,
                    member_id=member_id,
                    operation_key=operation_key,
                    project_root=project_root_resolved,
                    paths=profile_paths,
                    role_key=role_key,
                    operator_key=operator_key,
                    expected_choice_fingerprint=expected_choice_fingerprint,
                    cli_executable=cli_executable,
                    transport=active_transport,
                    base_url=base,
                    timeout=timeout_seconds,
                )
            except ProvisionError as exc:
                states["preflight"] = _step(STATE_FAILED, 1, exc.code, exc.detail)

        # 3) 只回报“捕获代际里仍是 pending”的本次待执行步骤（补正 F1/F3）。
        document["job"] = {
            "action": job_info["action"],
            "status": job_info["status"],
            "revision": job_info["revision"],
        }
        if operator_key is None:
            document["ack"] = {
                "sent": False,
                "reason": "operator_key_missing",
                "results": [],
            }
        elif generation is None:
            document["ack"] = {"sent": False, "reason": "ack_failed", "results": []}
        else:
            pending_steps = [
                step
                for step in selected
                if generation["steps"][step]["state"] == STATE_PENDING
            ]
            failed_steps = [
                step
                for step in selected
                if generation["steps"][step]["state"] == STATE_FAILED
            ]
            if pending_steps:
                document["ack"] = _send_acks(
                    transport=active_transport,
                    base_url=base,
                    project_id=project_id,
                    member_id=member_id,
                    operation_key=operation_key,
                    steps=pending_steps,
                    states=states,
                    generation=generation,
                    operator_key=operator_key,
                    timeout=timeout_seconds,
                )
            elif failed_steps:
                # 服务端仍有失败步骤：不重复 ACK 已完成项，也不假装成功。
                document["ack"] = {
                    "sent": False,
                    "reason": "resume_required",
                    "results": [
                        {"step": step, "sent": False, "reason": "resume_required"}
                        for step in failed_steps
                    ],
                }
            else:
                # 全部选中步骤已在服务端完成：重复 apply 的正常 no-op。
                document["ack"] = {"sent": False, "reason": "not_required", "results": []}
    finally:
        for held_path, held_handle in reversed(lock_handles):
            release_lock(held_path, held_handle)

    failed = [step for step in selected if states[step]["state"] == STATE_FAILED]
    done = [
        step
        for step in selected
        if states[step]["state"] in (STATE_SUCCEEDED, STATE_SKIPPED)
    ]
    ack = document["ack"]
    if failed and not done:
        document["conclusion"] = "failed"
    elif failed:
        document["conclusion"] = "partial"
    elif ack.get("sent") or ack.get("reason") == "not_required":
        document["conclusion"] = "applied"
    else:
        document["conclusion"] = "partial"

    # 名册路径登记缺 operator 凭据是可恢复状态（本地步骤可能已完成、登记待补）：即使本步
    # 全部未成功，也按 partial 报告而不是 failed。
    if (
        document["conclusion"] == "failed"
        and ack.get("reason") == "operator_key_missing"
        and any(
            states[step]["state"] == STATE_FAILED
            and states[step]["error_code"] == "operator_key_missing"
            for step in selected
        )
    ):
        document["conclusion"] = "partial"

    if failed:
        document["error_code"] = states[failed[0]]["error_code"]
    elif document["job"].get("error_code"):
        document["error_code"] = document["job"]["error_code"]
    elif ack.get("reason") == "operator_key_missing":
        document["error_code"] = "operator_key_missing"
    elif ack.get("reason") == "resume_required":
        document["error_code"] = "resume_required"
    elif ack.get("reason") == "ack_stale":
        document["error_code"] = "ack_stale"
    elif ack.get("reason") == "ack_failed":
        document["error_code"] = "ack_failed"

    return document, 0 if document["conclusion"] == "applied" else 1


# ---------------------------------------------------------------------------
# 请求驱动宿主入口（R1-4b）
#
# 只新增“请求来源”最小原语：一次性 Key 的创建/轮换响应解析、不含 Key 的私有
# credential.json 元数据、以及在请求来源/租约下的三步配置入口。默认 dry-run 的旧入口、
# 旧无请求路径、旧错误码与旧响应结构全部保持；本段不 spawn、不读原生认证目录、不做模型调用。
# ---------------------------------------------------------------------------

#: 请求驱动端点允许从**有界**错误正文里提取的稳定错误码白名单（REQUEST_CONTRACT §3/§5/§8）。
#: 只允许逐字命中；未知/自由文本/疑似凭据一律丢弃，绝不回显正文。
REQUEST_ENDPOINT_ERROR_WHITELIST: frozenset[str] = frozenset(
    set(PROVISION_ERROR_CODE_WHITELIST)
    | {
        "role_request_not_found",
        "role_request_key_conflict",
        "role_request_kind_invalid",
        "role_request_payload_invalid",
        "role_request_confirm_required",
        "role_request_role_conflict",
        "role_provision_payload_mismatch",
        "operation_key_conflict",
        "role_request_operation_mismatch",
        "provision_lease_required",
        "role_request_lease_invalid",
        "role_request_lease_seconds_invalid",
        "role_request_lease_conflict",
        "role_request_revision_conflict",
        "role_request_status_conflict",
        "role_request_not_resumable",
        "role_request_cancel_refused",
        "member_created",
        "role_request_choice_unavailable",
        "role_request_binding_mismatch",
        "role_request_credential_mismatch",
        "role_request_credential_stale",
        "role_request_completion_incomplete",
        "role_request_stale_report",
        "role_request_host_mismatch",
        "provision_host_disabled",
        "provision_host_version_conflict",
        "provision_host_busy",
        "provision_host_config_invalid",
        "role_name_invalid",
        "role_name_conflict",
        "runner_not_found",
        "runner_retired",
        "choice_not_found",
        "choice_retired",
        "role_not_found",
        "role_archived",
        "rotate_not_managed_identity",
        "rotate_member_not_agent",
        "rotate_member_disabled",
        "rotate_shared_identity_refused",
        "provision_imported_identity_unsupported",
        "api_key_generation_failed",
        "operation_key_invalid",
    }
)

#: 私有元数据文件（仓库外、与角色 Key 同根、**不含 Key/可复用令牌**）。
CREDENTIAL_METADATA_SUFFIX = ".credential.json"
CREDENTIAL_METADATA_SCHEMA = "talk-role-credential-metadata-1"
#: 元数据允许的 ``source`` 值。
CREDENTIAL_METADATA_SOURCES: frozenset[str] = frozenset(
    {"create", "recover", "existing_key"}
)


def credential_metadata_path(key_root: Any, member_id: str) -> Path:
    """``<key-root>/<member_dir_name>.credential.json``（守卫与 Key 文件同一规则）。"""
    name = _safe_dir_name(member_id)
    return assert_inside_root(key_root, Path(f"{name}{CREDENTIAL_METADATA_SUFFIX}"))


def _metadata_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_credential_metadata(
    key_root: Any,
    member_id: str,
    *,
    credential_version: int,
    source: str,
    intent: Optional[str] = None,
    intent_kind: Optional[str] = None,
    now: Optional[str] = None,
) -> Path:
    """私有、原子发布不含 Key 的 ``credential.json``；返回其路径。

    元数据与 Key 文件**不是**一起原子提交：Key 先发布，元数据单独发布。元数据失败不回滚、
    不删除已发布 Key，由调用方按 ``key_provenance_write_failed`` 记录并在下一次以本人当前
    Key 与角色当前版本核验后重建。
    """
    if source not in CREDENTIAL_METADATA_SOURCES:
        raise ProvisionError("key_provenance_write_failed", "元数据 source 非法")
    if isinstance(credential_version, bool) or not isinstance(credential_version, int):
        raise ProvisionError("key_provenance_write_failed", "元数据版本非法")
    if credential_version < 1:
        raise ProvisionError("key_provenance_write_failed", "元数据版本非法")
    timestamp = now or _now_iso()
    target = credential_metadata_path(key_root, member_id)
    payload = {
        "schema": CREDENTIAL_METADATA_SCHEMA,
        "member_id": member_id,
        "credential_version": int(credential_version),
        "source": source,
        "intent": intent,
        "intent_kind": intent_kind,
        "updated_at": timestamp,
    }
    _write_private_payload(target, _metadata_text(payload).encode("utf-8"))
    return target


def read_credential_metadata(key_root: Any, member_id: str) -> Optional[dict[str, Any]]:
    """读回并**形状校验**私有元数据；缺失/非法/异成员一律 ``None``（调用方 fail closed）。"""
    try:
        target = credential_metadata_path(key_root, member_id)
    except ProvisionError:
        return None
    if not target.is_file() or _is_reparse_point(target):
        return None
    try:
        raw = target.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, Mapping):
        return None
    if payload.get("schema") != CREDENTIAL_METADATA_SCHEMA:
        return None
    if str(payload.get("member_id") or "") != member_id:
        return None
    version = payload.get("credential_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return None
    source = payload.get("source")
    if source not in CREDENTIAL_METADATA_SOURCES:
        return None
    if "api_key" in raw or ROLE_KEY_ENV in raw:
        # 防御性：元数据里出现任何 Key 形态字段一律视为不可信，绝不据此继续。
        return None
    return {
        "schema": CREDENTIAL_METADATA_SCHEMA,
        "member_id": member_id,
        "credential_version": int(version),
        "source": str(source),
        "intent": payload.get("intent"),
        "intent_kind": payload.get("intent_kind"),
        "updated_at": payload.get("updated_at"),
    }


def _response_json(response: Any) -> Mapping[str, Any]:
    payload = getattr(response, "payload", None)
    return payload if isinstance(payload, Mapping) else {}


def _optional_key(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and _is_plausible_key(value) else None


def _optional_version(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return int(value)


def create_role_for_request(
    *,
    transport: Any,
    base_url: str,
    project_id: str,
    payload: Mapping[str, Any],
    request_key: str,
    lease_token: str,
    operator_key: str,
    timeout: float,
) -> dict[str, Any]:
    """C1：用原 ``POST /roles`` + ``operation_key=request_key`` + ``lease_token`` 首次创建。

    返回**脱敏**结果：``status/member_id/reused/credential_version/error_code``，以及仅在
    201 响应里出现一次的 ``api_key``。调用方必须让 ``api_key`` 只留在内存里，绝不进
    argv/env/日志/普通输出/交付；本函数不打印任何请求或响应正文。
    """
    body: dict[str, Any] = {
        "role_name": payload.get("role_name"),
        "runner_id": payload.get("runner_id"),
        "choice_id": payload.get("choice_id"),
        "operation_key": request_key,
        "lease_token": lease_token,
    }
    if payload.get("role_description") is not None:
        body["role_description"] = payload.get("role_description")
    response = transport.request_json(
        "POST",
        _api(base_url, _roles_path(project_id)),
        api_key=operator_key,
        body=body,
        timeout=timeout,
    )
    data = _response_json(response)
    reused = bool(data.get("reused")) if response.status == 200 else False
    return {
        "status": int(getattr(response, "status", 0) or 0),
        "member_id": str(data.get("member_id")) if data.get("member_id") else None,
        "reused": reused,
        "credential_version": _optional_version(data.get("credential_version")),
        "api_key": _optional_key(data.get("api_key")) if response.status == 201 else None,
        "error_code": _whitelisted_response_error_code(
            response, REQUEST_ENDPOINT_ERROR_WHITELIST
        ),
    }


def rotate_role_key_for_request(
    *,
    transport: Any,
    base_url: str,
    project_id: str,
    member_id: str,
    request_key: str,
    lease_token: str,
    expected_credential_version: Optional[int],
    operator_key: str,
    timeout: float,
) -> dict[str, Any]:
    """C2：请求驱动的**受限恢复**轮换（一次人类意图最多一次）。

    201 返回新 Key（只在内存）；200 ``reused=true`` 不返 Key；任何拒绝只回稳定错误码。
    """
    body: dict[str, Any] = {"request_key": request_key, "lease_token": lease_token}
    if expected_credential_version is not None:
        body["expected_credential_version"] = int(expected_credential_version)
    url = (
        _api(base_url, _roles_path(project_id))
        + "/"
        + quote(member_id, safe="")
        + "/rotate-key"
    )
    response = transport.request_json(
        "POST", url, api_key=operator_key, body=body, timeout=timeout
    )
    data = _response_json(response)
    return {
        "status": int(getattr(response, "status", 0) or 0),
        "member_id": str(data.get("member_id")) if data.get("member_id") else None,
        "reused": bool(data.get("reused")) if response.status == 200 else False,
        "credential_version": _optional_version(data.get("credential_version")),
        "api_key": _optional_key(data.get("api_key")) if response.status == 201 else None,
        "error_code": _whitelisted_response_error_code(
            response, REQUEST_ENDPOINT_ERROR_WHITELIST
        ),
    }


def acquire_provision_locks(
    project_root: Any,
    key_root: Any,
    member_id: str,
    *,
    stale_seconds: float = DEFAULT_LOCK_STALE_SECONDS,
) -> list[tuple[Path, dict[str, Any]]]:
    """按固定顺序取得同一角色的身份档锁 + Key 锁（失败时反向释放自己已持有的锁）。

    R1-4b：请求驱动 worker 需要在**同一临界区**内完成“核本机当前 Key / 受限轮换 / 私有
    发布 / 三步推进”，因此复用与 :func:`run_provision` 完全相同的两把锁，而不是另造一套。
    """
    profile_lock_path = profile_lock_path_for(project_root, member_id)
    target_key_path = key_file_path(key_root, member_id)
    lock_path = lock_path_for(target_key_path)
    handles: list[tuple[Path, dict[str, Any]]] = []
    try:
        for candidate in (profile_lock_path, lock_path):
            handles.append((candidate, acquire_lock(candidate, stale_seconds)))
    except ProvisionError:
        for held_path, held_handle in reversed(handles):
            release_lock(held_path, held_handle)
        raise
    return handles


def release_provision_locks(handles: Any) -> None:
    """反向释放在 :func:`acquire_provision_locks` 里取得的锁（只释放自己代际）。"""
    for held_path, held_handle in reversed(list(handles or [])):
        release_lock(held_path, held_handle)


def bounded_io_timeout(
    timeout_seconds: float, deadline: Any, clock: Any
) -> float:
    """把单次请求超时收敛到**本轮剩余预算**（R1-4b 返修 F2）。

    调用方（宿主 worker）把单轮 IO 预算的绝对期限传进来后，每次网络请求都用
    ``min(timeout_seconds, deadline - now)``，预算耗尽即抛 ``worker_io_budget_exceeded``，
    绝不把「剩余预算」只留在循环外层。
    """
    if deadline is None:
        return float(timeout_seconds)
    now = float(clock()) if clock is not None else time.monotonic()
    remaining = float(deadline) - now
    if remaining <= 0:
        raise ProvisionError("worker_io_budget_exceeded", "本轮 IO 预算已用完")
    return min(float(timeout_seconds), remaining)


class _RequestProvisionTransport:
    """请求驱动步骤的逐请求守卫；旧脚本传输保持原行为。"""

    def __init__(self, transport: Any, checkpoint: Any, timeout: Any):
        self._transport = transport
        self._checkpoint = checkpoint
        self._timeout = timeout

    def request_json(self, method: str, url: str, **kwargs: Any) -> HttpResponse:
        # 帮助函数内部也可能继续登记名册或发送多个 ACK；检查必须落在每次请求前。
        self._checkpoint()
        remaining_timeout = self._timeout()
        supplied_timeout = kwargs.get("timeout")
        kwargs["timeout"] = (
            remaining_timeout
            if supplied_timeout is None
            else min(float(supplied_timeout), remaining_timeout)
        )
        return self._transport.request_json(method, url, **kwargs)


def run_request_provision(
    *,
    project_id: str,
    member_id: str,
    operation_key: str,
    request_key: str,
    lease_token: str,
    project_root: Any,
    key_root: Any = None,
    base_url: str = DEFAULT_BASE_URL,
    steps: Any = None,
    resume: bool = False,
    resume_steps: Any = None,
    overwrite_profile: bool = False,
    cli_executable: Any = None,
    lock_stale_seconds: float = DEFAULT_LOCK_STALE_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    transport: Any = None,
    environ: Any = None,
    repo_root: Any = REPO_ROOT,
    locks: Any = None,
    operator_key: Optional[str] = None,
    eligibility_check: Any = None,
    deadline: Any = None,
    clock: Any = None,
) -> tuple[dict[str, Any], int]:
    """请求驱动（C3/C4）三步配置入口：**不写 Key**，其余复用 R1-2 私有原子/锁/预检。

    前置事实：Key 文件已由一次性响应私有发布、身份档目标已知、作业尚待推进。本函数只：
    捕获作业代际 → 跑 ``profile/key_file/preflight`` → 用 ``request_key/lease_token`` 按捕获
    代际 ACK。Key 文件在本步只做**只读身份核验**（``skipped``/``succeeded``），绝不重写、
    绝不从服务端重取旧 Key。返回 ``(文档, 退出码)``；任何失败都只回稳定错误码。

    R1-4b 返修（F2/F3/F4）新增三个可选参数，默认 ``None`` 时行为与 R1-2 完全一致：

    - ``operator_key``：调用方**已解析**的 operator 凭据（只在内存里贯穿），无需重配 env，
      也绝不写进 argv/子进程环境；为空时才回退到 ``environ`` 解析；
    - ``eligibility_check``：在 profile/Key 核验/预检/ACK 每个副作用边界前调用；断言当前
      请求/租约世代/期限/目标资格仍然有效，失效即抛异常，从而**不做后续写**；
    - ``deadline``/``clock``：单轮 IO 预算的绝对期限与时钟，每次网络请求都用剩余预算。
    """
    env = (
        {str(key): str(value) for key, value in os.environ.items()}
        if environ is None
        else {str(key): str(value) for key, value in environ.items()}
    )
    active_transport = transport if transport is not None else UrlLibTransport(timeout_seconds)
    base = str(base_url or DEFAULT_BASE_URL).rstrip("/")
    selected = parse_steps(steps)

    def _io_timeout() -> float:
        return bounded_io_timeout(timeout_seconds, deadline, clock)

    def _checkpoint() -> None:
        if eligibility_check is not None:
            eligibility_check()

    if eligibility_check is not None or deadline is not None:
        active_transport = _RequestProvisionTransport(
            active_transport, _checkpoint, _io_timeout
        )

    states: dict[str, dict[str, Any]] = {
        step: _step(STATE_PENDING, 0, None, "not run") for step in STEP_ORDER
    }
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": MODE_APPLY,
        "project_id": project_id,
        "member_id": member_id,
        "operation_key": operation_key,
        "request_key": request_key,
        "base_url": base,
        "steps": states,
        "ack": {"sent": False, "reason": None, "results": []},
        "job": {"action": "none", "status": None, "revision": None},
        "lock": None,
        "identity_lock": None,
        "error_code": None,
        "conclusion": "failed",
    }

    try:
        project_root_resolved = _resolve_project_root(project_root)
    except ProvisionError as exc:
        return _abort(document, states, selected, exc.code, exc.detail)
    document["project_root"] = str(project_root_resolved)

    key_root_value = DEFAULT_KEY_ROOT if key_root is None else key_root
    try:
        key_root_declared = Path(key_root_value).expanduser()
        _assert_root_chain_has_no_reparse(key_root_declared)
        key_root_resolved = key_root_declared.resolve()
    except ProvisionError as exc:
        return _abort(document, states, selected, exc.code, exc.detail)
    except OSError:
        return _abort(document, states, selected, "key_write_failed", "Key 根无法解析")
    document["key_root"] = str(key_root_resolved)
    if _path_is_within(key_root_resolved, repo_root):
        return _abort(
            document,
            states,
            selected,
            "key_root_inside_repo",
            _REASON_DETAILS["key_root_inside_repo"],
        )

    try:
        profile_paths = profile_target_paths(project_root_resolved, member_id)
        target_key_path = key_file_path(key_root_resolved, member_id)
    except ProvisionError as exc:
        return _abort(document, states, selected, exc.code, exc.detail)
    document["key_file_path"] = str(target_key_path)

    # R1-4b：调用方（worker）可在同一临界区里先核本机 Key 并做受限发布，再把已持有的锁
    # 交给本函数复用；未提供时按 R1-2 原顺序自行取锁。
    owns_locks = locks is None
    lock_handles: list[tuple[Path, dict[str, Any]]] = [] if owns_locks else list(locks)
    if owns_locks:
        try:
            lock_handles = acquire_provision_locks(
                project_root_resolved,
                key_root_resolved,
                member_id,
                stale_seconds=lock_stale_seconds,
            )
        except ProvisionError as exc:
            return _abort(document, states, selected, exc.code, exc.detail)
    if lock_handles:
        document["lock"] = lock_handles[-1][1]
        document["identity_lock"] = lock_handles[0][1]

    try:
        # R1-4b 返修 F3：调用方已解析的 operator 优先，且只在内存里贯穿；仅当缺省时
        # 才回退到 environ（兼容旧脚本来源规则），绝不把 Key 写进 argv/子进程环境。
        if operator_key is None:
            operator_key = _resolve_operator_key(env)
        if operator_key is None:
            for step in selected:
                states[step] = _step(
                    STATE_FAILED, 0, "operator_key_missing", "缺少 operator 凭据"
                )
            document["error_code"] = "operator_key_missing"
            document["conclusion"] = "failed"
            return document, 1

        _checkpoint()
        try:
            job_info = _ensure_job(
                transport=active_transport,
                base_url=base,
                project_id=project_id,
                member_id=member_id,
                operation_key=operation_key,
                resume=resume,
                resume_steps=resume_steps,
                operator_key=operator_key,
                timeout=_io_timeout(),
                request_key=request_key,
                lease_token=lease_token,
            )
        except ProvisionError as exc:
            for step in selected:
                states[step] = _step(STATE_FAILED, 0, exc.code, exc.detail)
            document["job"] = {
                "action": "none",
                "status": None,
                "revision": None,
                "error_code": exc.code,
                "detail": exc.detail,
            }
            document["error_code"] = exc.code
            document["conclusion"] = "failed"
            return document, 1

        generation = job_info.get("generation")
        expected_choice_fingerprint = job_info.get("expected_binding_fingerprint")
        document["job"] = {
            "action": job_info["action"],
            "status": job_info["status"],
            "revision": job_info["revision"],
        }

        if "profile" in selected:
            _checkpoint()
            try:
                states["profile"] = _run_profile_step(
                    project_root=project_root_resolved,
                    member_id=member_id,
                    project_id=project_id,
                    paths=profile_paths,
                    overwrite=overwrite_profile,
                )
            except ProvisionError as exc:
                states["profile"] = _step(STATE_FAILED, 1, exc.code, exc.detail)

        if "key_file" in selected:
            _checkpoint()
            try:
                states["key_file"] = _run_key_step(
                    key_path=target_key_path,
                    member_id=member_id,
                    key_input_file=None,
                    env={},
                    transport=active_transport,
                    base_url=base,
                    timeout=_io_timeout(),
                )
            except ProvisionError as exc:
                states["key_file"] = _step(STATE_FAILED, 1, exc.code, exc.detail)

        if "preflight" in selected:
            _checkpoint()
            role_key = (
                _read_key_file(target_key_path) if target_key_path.is_file() else None
            )
            try:
                states["preflight"] = _run_preflight_step(
                    project_id=project_id,
                    member_id=member_id,
                    operation_key=operation_key,
                    project_root=project_root_resolved,
                    paths=profile_paths,
                    role_key=role_key,
                    operator_key=operator_key,
                    expected_choice_fingerprint=expected_choice_fingerprint,
                    cli_executable=cli_executable,
                    transport=active_transport,
                    base_url=base,
                    timeout=_io_timeout(),
                )
            except ProvisionError as exc:
                states["preflight"] = _step(STATE_FAILED, 1, exc.code, exc.detail)

        if generation is None:
            document["ack"] = {"sent": False, "reason": "ack_failed", "results": []}
        else:
            pending_steps = [
                step
                for step in selected
                if generation["steps"][step]["state"] == STATE_PENDING
            ]
            failed_steps = [
                step
                for step in selected
                if generation["steps"][step]["state"] == STATE_FAILED
            ]
            if pending_steps:
                _checkpoint()
                document["ack"] = _send_acks(
                    transport=active_transport,
                    base_url=base,
                    project_id=project_id,
                    member_id=member_id,
                    operation_key=operation_key,
                    steps=pending_steps,
                    states=states,
                    generation=generation,
                    operator_key=operator_key,
                    timeout=_io_timeout(),
                    request_key=request_key,
                    lease_token=lease_token,
                )
            elif failed_steps:
                document["ack"] = {
                    "sent": False,
                    "reason": "resume_required",
                    "results": [
                        {"step": step, "sent": False, "reason": "resume_required"}
                        for step in failed_steps
                    ],
                }
            else:
                document["ack"] = {"sent": False, "reason": "not_required", "results": []}
    finally:
        if owns_locks:
            release_provision_locks(lock_handles)

    failed = [step for step in selected if states[step]["state"] == STATE_FAILED]
    done = [
        step
        for step in selected
        if states[step]["state"] in (STATE_SUCCEEDED, STATE_SKIPPED)
    ]
    ack = document["ack"]
    if failed and not done:
        document["conclusion"] = "failed"
    elif failed:
        document["conclusion"] = "partial"
    elif ack.get("sent") or ack.get("reason") == "not_required":
        document["conclusion"] = "applied"
    else:
        document["conclusion"] = "partial"

    if failed:
        document["error_code"] = states[failed[0]]["error_code"]
    elif ack.get("reason") in ("ack_stale", "ack_failed", "resume_required"):
        document["error_code"] = ack["reason"]

    return document, 0 if document["conclusion"] == "applied" else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def render_text(document: Mapping[str, Any]) -> str:
    lines = [
        f"role_provision schema={document.get('schema')} mode={document.get('mode')}",
        f"project_id={document.get('project_id')} member_id={document.get('member_id')} "
        f"operation_key={document.get('operation_key')}",
        f"project_root={document.get('project_root')} key_root={document.get('key_root')}",
        "steps:",
    ]
    steps = document.get("steps") or {}
    for step in STEP_ORDER:
        info = steps.get(step) or {}
        lines.append(
            f"  {step}: state={info.get('state')} attempts={info.get('attempts')} "
            f"error_code={info.get('error_code')} detail={info.get('detail')}"
        )
    ack = document.get("ack") or {}
    lines.append(f"ack: sent={ack.get('sent')} reason={ack.get('reason')}")
    job = document.get("job") or {}
    lines.append(
        f"job: action={job.get('action')} status={job.get('status')} "
        f"revision={job.get('revision')}"
    )
    lock = document.get("lock")
    if lock:
        lines.append(f"lock: reclaimed={lock.get('reclaimed')}")
    lines.append(
        f"error_code={document.get('error_code')} conclusion={document.get('conclusion')}"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="角色一键配置（R1-2 B）：身份档 / 仓库外 Key 文件 / 启动前检查；默认 dry-run",
    )
    parser.add_argument("--project", required=True, help="目标 project_id（必填）")
    parser.add_argument("--member", required=True, help="目标 member_id（必填）")
    parser.add_argument("--operation-key", required=True, help="R1-1 创建操作的 operation_key（必填）")
    parser.add_argument("--project-root", default=str(REPO_ROOT), help="项目根目录")
    parser.add_argument("--key-root", default=None, help=f"Key 根目录（仓库之外；默认 {DEFAULT_KEY_ROOT}）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="TALK API 基地址")
    parser.add_argument("--apply", action="store_true", help="真实写入身份档/Key 文件并按需 ACK")
    parser.add_argument("--overwrite-profile", action="store_true", help="覆盖已存在的身份档")
    parser.add_argument(
        "--steps",
        default=None,
        help="要执行的步骤子集（逗号分隔）：profile,key_file,preflight",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="作业已存在时定向续跑（POST resume=true；steps 取显式 --steps，未显式则 null）",
    )
    parser.add_argument("--key-input-file", default=None, help="角色 Key 输入文件（不在 argv 传 Key）")
    parser.add_argument("--cli-executable", default=None, help="可选：只检查该 CLI 路径是否存在，不执行")
    parser.add_argument(
        "--lock-stale-seconds",
        type=float,
        default=DEFAULT_LOCK_STALE_SECONDS,
        help="陈旧锁可回收阈值（秒，默认 900）",
    )
    parser.add_argument("--json", action="store_true", help="stdout 输出单个 JSON 对象")
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP 超时（秒）"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None, *, transport: Any = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):  # pragma: no cover - 非标准流
                pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        steps = parse_steps(args.steps)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        operation_key = _validate_operation_key(args.operation_key)
    except ValueError as exc:
        parser.error(str(exc))
    if not str(args.project).strip():
        parser.error("--project 不能为空")
    if not str(args.member).strip():
        parser.error("--member 不能为空")
    try:
        document, code = run_provision(
            project_id=str(args.project).strip(),
            member_id=str(args.member).strip(),
            operation_key=operation_key,
            project_root=args.project_root,
            key_root=args.key_root,
            base_url=args.base_url,
            apply=bool(args.apply),
            overwrite_profile=bool(args.overwrite_profile),
            steps=steps,
            resume=bool(args.resume),
            resume_steps=(list(steps) if args.steps is not None else None),
            key_input_file=args.key_input_file,
            cli_executable=args.cli_executable,
            lock_stale_seconds=args.lock_stale_seconds,
            timeout_seconds=args.timeout_seconds,
            transport=transport,
        )
    except Exception as exc:  # noqa: BLE001 - 绝不回显可能含凭据的异常正文
        print(f"role_provision 执行失败：{type(exc).__name__}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(document, ensure_ascii=False))
    else:
        print(render_text(document))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
