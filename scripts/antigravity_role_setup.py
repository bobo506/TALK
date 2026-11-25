"""Antigravity CLI (``agy``) 角色准备、目录探测与运行器/模型登记辅助。

Antigravity CLI 通过本机账户会话鉴权，即使将 ``HOME`` / ``USERPROFILE`` /
``APPDATA`` / ``LOCALAPPDATA`` / ``XDG_*`` 隔离到角色私有目录也能独立工作，
不采用 Codex/Kimi 的设备码登录流程，也不读取或复制任何用户原生凭据文件。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridges.antigravity_effort import (
    EFFORT_ORDER,
    SUPPORTED_BASE_MODELS,
    SUPPORTED_MODEL_ORDER,
)
from bridges.antigravity_execution_native import (
    AntigravityNativeError,
    check_antigravity,
    discover_antigravity_models,
    find_antigravity_executable,
)
from scripts import role_provision as provision
from scripts import role_service_host as host

RUNNER_ID = "runner:antigravity-local"
RUNTIME = "antigravity"
RUNNER_DISPLAY_NAME = "Antigravity CLI"
PROVIDER_ID = "google-antigravity"
CONNECTION_REF = "native-antigravity-login"
CANONICAL_PROXY_ENV_VARS: tuple[str, ...] = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
)
PROXY_ENV_VARS: tuple[str, ...] = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def _canonical_capabilities(efforts: Sequence[str], default_effort: str) -> list[str]:
    ordered = [item for item in EFFORT_ORDER if item in efforts]
    caps = [f"effort:{item}" for item in ordered]
    if default_effort in ordered:
        caps.append(f"effort_default:{default_effort}")
    return caps


MODEL_CHOICES: tuple[tuple[str, str, str, str, str, list[str]], ...] = tuple(
    (
        base,
        base,
        str(SUPPORTED_BASE_MODELS[base]["display_name"]),
        PROVIDER_ID,
        CONNECTION_REF,
        _canonical_capabilities(
            SUPPORTED_BASE_MODELS[base]["supported_efforts"],
            str(SUPPORTED_BASE_MODELS[base]["default_effort"]),
        ),
    )
    for base in SUPPORTED_MODEL_ORDER
)


class SetupError(RuntimeError):
    """稳定机器可读的准备失败分类（不携带原始凭据或敏感路径）。"""


def validate_executable_path(value: Any, *, must_exist: bool = True) -> str:
    """严格校验 Antigravity CLI 可执行路径：绝对路径、无重解析点、原始与解析文件名均为 agy/agy.exe。"""
    if not isinstance(value, str) or not value.strip():
        raise SetupError("native_cli_missing")
    raw = Path(value)
    if not raw.is_absolute() or raw.name.lower() not in ("agy.exe", "agy"):
        raise SetupError("native_cli_missing")
    try:
        provision._assert_root_chain_has_no_reparse(raw)
    except provision.ProvisionError:
        raise SetupError("native_cli_missing") from None
    if host._is_reparse_point(raw):
        raise SetupError("native_cli_missing")
    if must_exist and not raw.is_file():
        raise SetupError("native_cli_missing")
    try:
        resolved = raw.resolve()
    except (OSError, RuntimeError):
        raise SetupError("native_cli_missing") from None
    if resolved.name.lower() not in ("agy.exe", "agy"):
        raise SetupError("native_cli_missing")
    if must_exist and not resolved.is_file():
        raise SetupError("native_cli_missing")
    return str(resolved)


def detect_executable(environ: Mapping[str, str] | None = None) -> str | None:
    """仅检测文档约定位置与 PATH 中的 ``agy`` 可执行文件，绝不扫描用户私有目录。"""
    found = find_antigravity_executable(environ)
    if not found:
        return None
    try:
        return validate_executable_path(found, must_exist=True)
    except SetupError:
        return None


def antigravity_recipe(environ: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    """生成可供 ``runtime.json`` 使用的公开 Antigravity 宿主配方。"""
    exe = detect_executable(environ)
    if not exe:
        return None
    return {"enabled": True, "executable": exe, "task_profiles": {}}


def executable(config: Mapping[str, Any]) -> str:
    """从 runtime 配置解析已启用的绝对路径 ``agy`` 可执行文件。"""
    recipe = config.get("antigravity") if isinstance(config, Mapping) else None
    value = recipe.get("executable") if isinstance(recipe, Mapping) and recipe.get("enabled") is True else None
    return validate_executable_path(value, must_exist=True)


def _clean_proxy_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or any(ch in stripped for ch in ("\r", "\n", "\x00")):
        return None
    return stripped


def _merge_no_proxy_tokens(*raw_values: str) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for item in raw.split(","):
            token = item.strip()
            if not token:
                continue
            low = token.lower()
            if low not in seen:
                tokens.append(token)
                seen.add(low)
    if "*" in seen:
        return "*"
    for host_token in ("127.0.0.1", "localhost", "::1"):
        if host_token not in seen:
            tokens.append(host_token)
            seen.add(host_token)
    return ",".join(tokens)


def apply_proxy_env(env: dict[str, str], source: Mapping[str, str] | None = None) -> dict[str, str]:
    """透传系统代理变量供 ``agy`` 访问模型服务，同时保证本机回环地址直连 TALK API。

    - Windows 下 ``os.environ`` 大小写不敏感：读取 ``os.environ`` 时仅写入规范大写键
      并清除重复小写别名，避免向 Win32 子进程环境块写入重复键；
    - 合并已有 ``NO_PROXY`` / ``no_proxy`` 条目，避免新写 ``NO_PROXY`` 遮蔽用户的 ``no_proxy``；
    - 保留 ``NO_PROXY="*"`` 通配语义，避免破坏 Python ``urllib`` 的通配绕过判定。
    """
    src = os.environ if source is None else source
    windows_case_insensitive = os.name == "nt" and src is os.environ
    keys_to_read = CANONICAL_PROXY_ENV_VARS if windows_case_insensitive else PROXY_ENV_VARS
    has_proxy = False
    for name in keys_to_read:
        cleaned = _clean_proxy_value(src.get(name))
        if cleaned is not None:
            env[name] = cleaned
            if name.lower() != "no_proxy":
                has_proxy = True
    if windows_case_insensitive:
        for lower_name in ("http_proxy", "https_proxy", "all_proxy"):
            env.pop(lower_name, None)
    if not has_proxy:
        return env
    if windows_case_insensitive:
        pre_lower = env.pop("no_proxy", "")
        env["NO_PROXY"] = _merge_no_proxy_tokens(env.get("NO_PROXY", ""), pre_lower)
    else:
        merged = _merge_no_proxy_tokens(env.get("NO_PROXY", ""), env.get("no_proxy", ""))
        env["NO_PROXY"] = merged
        if "no_proxy" in env:
            env["no_proxy"] = merged
    return env


def sensitive_proxy_values(source: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """返回含凭据的代理 URL 及解析出的 userinfo/密码，供宿主诊断日志自动脱敏。"""
    from urllib.parse import unquote, urlsplit

    src = os.environ if source is None else source
    keys = CANONICAL_PROXY_ENV_VARS if (os.name == "nt" and src is os.environ) else PROXY_ENV_VARS
    values: list[str] = []

    def add(item: str | None) -> None:
        if isinstance(item, str) and item and item not in values:
            values.append(item)

    for name in keys:
        if name.lower() == "no_proxy":
            continue
        raw = src.get(name)
        if not isinstance(raw, str):
            continue
        stripped = raw.strip()
        if not stripped or "@" not in stripped:
            continue
        try:
            parsed = urlsplit(stripped if "://" in stripped else f"http://{stripped}")
        except ValueError:
            continue
        userinfo, sep, hostport = parsed.netloc.rpartition("@")
        if not sep or not userinfo or not hostport:
            continue
        add(stripped)
        if raw != stripped:
            add(raw)
        add(userinfo)
        add(unquote(userinfo))
        if ":" in userinfo:
            raw_pass = userinfo.split(":", 1)[1]
            add(raw_pass)
            add(unquote(raw_pass))
    return tuple(values)


def environment(home: Path | str) -> dict[str, str]:
    """构造仅含系统必要白名单 + 代理透传 + 角色私有隔离根的子进程环境。"""
    resolved = Path(home).resolve()
    env = {name: value for name in host.CHILD_ENV_ALLOWLIST if (value := os.environ.get(name))}
    apply_proxy_env(env)
    env.update({name: str(resolved) for name in host.NATIVE_HOME_ENV_VARS})
    env["ANTIGRAVITY_HOME"] = str(resolved)
    return env


def prepare_role_home(home: Path | str) -> Path:
    """确保角色隔离 ``native-home`` 目录存在且具备私有权限，拒绝任意祖先或目标符号链接/重解析点。"""
    target = Path(home)
    try:
        provision._assert_root_chain_has_no_reparse(target)
    except provision.ProvisionError:
        raise SetupError("state_dir_insecure") from None
    if host._is_reparse_point(target):
        raise SetupError("state_dir_insecure")
    return host.ensure_private_dir(target)


def _map_native_error(exc: AntigravityNativeError) -> str:
    code = getattr(exc, "reason_code", "")
    if code in ("antigravity_cli_missing", "antigravity_native_executable_required"):
        return "native_cli_missing"
    if code == "antigravity_probe_failed":
        cause = getattr(exc, "__cause__", None)
        if isinstance(cause, FileNotFoundError) or "FileNotFoundError" in str(exc):
            return "native_cli_missing"
        return "native_cli_version_unsupported"
    if code in ("antigravity_models_probe_failed", "antigravity_model_catalog_unavailable"):
        return "native_model_catalog_unavailable"
    return "native_cli_version_unsupported"


def probe_catalog(
    exe: str,
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 20.0,
    use_cache: bool = False,
) -> dict[str, Any]:
    """只读探测 ``agy`` 版本、无头能力与本机真实可用的 3 个目标模型目录。"""
    validated_exe = validate_executable_path(exe, must_exist=True)
    try:
        probe = check_antigravity(validated_exe, cwd=cwd, env=env, use_cache=use_cache)
        models = discover_antigravity_models(validated_exe, cwd=cwd, env=env, timeout=timeout)
    except AntigravityNativeError as exc:
        raise SetupError(_map_native_error(exc)) from exc
    if probe.get("warning"):
        warnings.warn(
            f"{probe['warning']}: Antigravity CLI {probe['version']}",
            RuntimeWarning,
            stacklevel=2,
        )
    if not models:
        raise SetupError("native_model_catalog_unavailable")
    return {
        "executable": validated_exe,
        "version": probe["version"],
        "warning": probe.get("warning"),
        "capabilities": dict(probe.get("capabilities") or {}),
        "models": models,
    }


def choice_id_for(
    model_id: str,
    *,
    runner_id: str = RUNNER_ID,
    model_alias: str | None = None,
    provider_id: str = PROVIDER_ID,
    connection_ref: str = CONNECTION_REF,
) -> str:
    """与 ``portable_bootstrap.seed_runners`` 完全同源的稳定 ``choice_id``。"""
    alias = model_alias or model_id
    digest = hashlib.sha256(
        f"{runner_id}|{model_id}|{alias}|{provider_id}|{connection_ref}".encode("utf-8")
    ).hexdigest()[:12]
    return f"rmc_{digest}"


def seed_antigravity_choices(
    session: Any,
    actor_id: str,
    *,
    catalog: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    """幂等登记 Antigravity CLI 运行器与 3 个目标基础模型；保留既有登记记录。"""
    from sqlmodel import select
    from server.models import RunnerModelChoice, RunnerRegistry

    created = {"runners": 0, "models": 0}
    if session.get(RunnerRegistry, RUNNER_ID) is None:
        session.add(
            RunnerRegistry(
                runner_id=RUNNER_ID,
                runtime=RUNTIME,
                display_name=RUNNER_DISPLAY_NAME,
                adapter_status="unverified",
                adapter_note=None,
                capabilities=[],
                control_kind="managed_cli",
                created_by=actor_id,
            )
        )
        created["runners"] += 1
        session.commit()

    catalog_by_model: dict[str, Mapping[str, Any]] = {}
    if catalog is not None:
        for entry in catalog:
            if isinstance(entry, Mapping) and entry.get("model_id") in SUPPORTED_BASE_MODELS:
                catalog_by_model[str(entry["model_id"])] = entry

    for model_id, alias, display, provider, connection, default_caps in MODEL_CHOICES:
        existing = session.exec(
            select(RunnerModelChoice).where(
                RunnerModelChoice.runner_id == RUNNER_ID,
                RunnerModelChoice.model_id == model_id,
                RunnerModelChoice.model_source == "builtin",
                RunnerModelChoice.provider_id == provider,
                RunnerModelChoice.connection_ref == connection,
                RunnerModelChoice.model_alias == alias,
            )
        ).first()
        if existing is not None:
            continue
        capabilities = list(default_caps)
        if catalog is not None:
            observed = catalog_by_model.get(model_id)
            if observed is None:
                continue
            allowed = set(SUPPORTED_BASE_MODELS[model_id]["supported_efforts"])
            efforts = [
                item
                for item in EFFORT_ORDER
                if item in (observed.get("supported_efforts") or ()) and item in allowed
            ]
            if not efforts:
                continue
            preferred = str(observed.get("default_effort") or SUPPORTED_BASE_MODELS[model_id]["default_effort"])
            default_effort = preferred if preferred in efforts else efforts[0]
            capabilities = _canonical_capabilities(efforts, default_effort)
        session.add(
            RunnerModelChoice(
                choice_id=choice_id_for(
                    model_id,
                    runner_id=RUNNER_ID,
                    model_alias=alias,
                    provider_id=provider,
                    connection_ref=connection,
                ),
                runner_id=RUNNER_ID,
                model_id=model_id,
                model_source="builtin",
                provider_id=provider,
                connection_ref=connection,
                model_alias=alias,
                model_display_name=display,
                source_kind="declared",
                capabilities=capabilities,
                created_by=actor_id,
            )
        )
        created["models"] += 1
    session.commit()
    return created


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--antigravity-executable",
        default=None,
        help="Absolute path to agy executable (defaults to PATH or Windows default install path)",
    )
    parser.add_argument(
        "--seed-db",
        default=None,
        help="Optional SQLite DB path to seed runner:antigravity-local and the 3 models (dry-run unless --apply)",
    )
    parser.add_argument("--actor-id", default="human:operator", help="Creator member_id when seeding")
    parser.add_argument("--apply", action="store_true", help="Apply DB seeding changes")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raw_exe = args.antigravity_executable or detect_executable()
    try:
        exe = validate_executable_path(raw_exe, must_exist=True)
        info = probe_catalog(exe, cwd=ROOT)
    except SetupError as exc:
        print(json.dumps({"ok": False, "error_code": str(exc)}, ensure_ascii=False))
        return 1
    payload: dict[str, Any] = {
        "ok": True,
        "mode": "apply" if (args.seed_db and args.apply) else "dry_run",
        "version": info["version"],
        "warning": info["warning"],
        "models": [
            {
                "model_id": item["model_id"],
                "display_name": item["display_name"],
                "default_effort": item["default_effort"],
                "supported_efforts": item["supported_efforts"],
            }
            for item in info["models"]
        ],
    }
    if args.seed_db:
        if not args.apply:
            payload["seed"] = "dry_run"
        else:
            from sqlmodel import Session, create_engine
            from server.models import SQLModel

            db_path = Path(args.seed_db).resolve()
            engine = create_engine(f"sqlite:///{db_path.as_posix()}")
            try:
                SQLModel.metadata.create_all(engine)
                with Session(engine) as session:
                    payload["seed"] = seed_antigravity_choices(
                        session, args.actor_id, catalog=info["models"]
                    )
            finally:
                engine.dispose()
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
