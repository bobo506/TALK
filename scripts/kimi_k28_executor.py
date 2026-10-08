#!/usr/bin/env python3
"""Kimi Code + K2.8 Preview 独立执行入口：无密钥合同 / 离线检查 / 启动。

本脚本**不新增模型推理循环**，只把既有 `bridges/kimi_bridge.py` 已经具备的能力
按一条固定合同配置起来，供独立成员 `agent:kimi-code-k28-preview` 使用：

- 成员身份独立：默认成员 id 是本入口常量，不复用 `agent:kimi` 的 TALK Key；
- 项目/实例独立：`--project` 指向本仓库，实例 id 由成员 id 派生（`<member_id>:<uuid4>`）；
- 模型 alias 显式锁定：三个运行档都带 `--model kimi-code/kimi-for-coding`；
- 受控固定命令：本入口与 `command_override_allowed=false` 一致，argv 里**显式**写入
  固定命令 `kimi --output-format stream-json -p`，因此 `TALK_KIMI_COMMAND` 等环境
  继承与任何显式自定义命令都不能绕过模型锁与工具档隔离；
- 固定执行分级：argv 显式写入 `--decision-tier execution`；远端名册核验的是 execution，
  本地 `.talk/groups.yaml` 的 `decision`/缺省不得让实际运行按 decision 执行；
- 单一服务地址：只读身份预检与实际 bridge argv 使用同一个 `--base-url`。
- 工具档：任务执行 `tools`（Edit/Write），讨论与领取前预检保持无工具；
- 凭据安全：只从环境变量或**仓库外**密钥文件读取，绝不打印、不落盘到仓库；
- 启动门禁：`launch` 先走与 bridge **同一条**检查路径（固定命令、本次实际 native
  配置与项目绑定），再做一次**只读**服务端身份核验（`GET /api/members/me` +
  项目名册），全部通过后才进入既有 bridge 的 `client.register`。

四个子命令互相独立，`contract` / `check` / `render` 全程零密钥、零模型调用：

``contract``
    打印本入口的配置合同（成员 / 运行器 / 模型 / 身份与预算字段彼此分开）。
``check``
    离线检查：固定参数、受控固定命令、native `config.toml` 里的 alias 与绑定、
    模型锁、工具档隔离、argv 运输、项目绑定、凭据来源。全部只读，默认不联网；
    只有显式 `--online-identity` 才会加一次只读在线身份核验。
``render``
    打印可由操作者复制的 bridge argv（`--key` 位置是**占位符**，不含密钥）。
``launch``
    解析本人 TALK Key 后先做启动前检查与只读身份核验，再在本进程内直接启动
    现有 Kimi bridge；密钥只作为 Python 对象存在，不进入任何命令行、日志或文件。
    `--dry-run` 只做离线检查并打印脱敏 argv，**不做**在线身份核验、不启动。

退出码：0 通过；1 检查失败或启动前置条件不满足；2 用法错误。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

CONTRACT_SCHEMA = "kimi-k28-executor-contract-1"

# --- 成员与项目（本入口常量；名称不等于已注册身份） -------------------------
MEMBER_ID = "agent:kimi-code-k28-preview"
DISPLAY_NAME = "Kimi Code · K2.8 Preview 执行"
BUSINESS_ROLE = "dev"
DECISION_TIER = "execution"
PROJECT_ID = "prj_e8fe7066bbec"
DEFAULT_PROJECT_ROOT = "D:/claude-test/TALK"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# --- 运行器（复用现有 bridge，不新建推理循环） ------------------------------
RUNNER_ENTRY = "bridges/kimi_bridge.py"
RUNTIME = "kimi-code"
PROMPT_TRANSPORT = "argv"
TASK_TOOL_PROFILE = "tools"
DISCUSSION_TOOL_PROFILE = "none"
PREFLIGHT_TOOL_PROFILE = "none"
TASK_PROFILE_SUMMARY = f"{TASK_TOOL_PROFILE}（讨论/预检保持 {DISCUSSION_TOOL_PROFILE}）"
COMMAND_OVERRIDE_ALLOWED = False
# 受控固定命令：必须等于 bridges/kimi_bridge.py 的 DEFAULT_KIMI_COMMAND，否则 bridge 会
# 走“自定义命令”分支，三档都不生成 Agent 文件，模型锁与工具档隔离会一起失效。
# 本入口把该值显式写进 argv，因此 TALK_KIMI_COMMAND 的环境继承不会生效。
CONTROLLED_KIMI_COMMAND = "kimi --output-format stream-json -p"
CONTROLLED_COMMAND_SOURCE = "explicit_fixed_contract"
ENV_COMMAND_VAR = "TALK_KIMI_COMMAND"
EXECUTION_TIMEOUT_SECONDS = 3600

# --- 只读在线身份核验（launch 门禁；不是注册写入） --------------------------
HTTP_TIMEOUT_SECONDS = 15.0
MEMBERS_ME_PATH = "/api/members/me"
PROJECT_AGENTS_PATH = "/api/projects/{project_id}/agents"

# --- 模型来源：builtin 原生 managed 连接，本入口不改全局 default_model ------
MODEL_SOURCE = "builtin"
PROVIDER_ID = "managed:kimi-code"
CONNECTION_REF = "native-kimi-code-managed-login"
# CLI `--model` 取值 = 本机 config.toml 的**配置别名**（不是后端 API 模型 ID）
MODEL_ALIAS = "kimi-code/kimi-for-coding"
# 别名背后的后端模型 ID：显示名可原地升级，不能承诺永久锁版本
MODEL_ID = "kimi-for-coding"
MODEL_VERSION_LABEL = "K2.8 Preview"
MODEL_VERSION_PINNED = False
# 只读记录用：本入口不修改全局默认模型
DEFAULT_MODEL_BASELINE = "kimi-code/k3"

# --- TALK 身份凭据：环境变量优先，其次仓库外密钥文件 ------------------------
KEY_ENV = "TALK_K28_KEY"
KEY_FILE_NAME = "agent-kimi-code-k28-preview.key"
FORBIDDEN_KEY_FILE_NAME = "agent-kimi.key"
KEY_PLACEHOLDER = "<TALK_K28_KEY>"

# --- 等待预算（模板事实，不等于宿主已加载能力） -----------------------------
CLIENT_TOOL_TIMEOUT_TEMPLATE_MS = 660000
TEMPLATE_SOURCE = "deploy/kimi-code/mcp.talk.template.json"

REDACT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{8,}"),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
)


class K28ExecutorError(RuntimeError):
    """可预期的中文短错误；调用方只打印 message，不打印 traceback。"""


# ---------------------------------------------------------------------------
# 路径与凭据
# ---------------------------------------------------------------------------


def default_kimi_config_path(environ: dict | None = None) -> Path:
    """`$KIMI_CODE_HOME/config.toml`，否则 `~/.kimi-code/config.toml`。"""
    env = os.environ if environ is None else environ
    home = (env.get("KIMI_CODE_HOME") or "").strip()
    if home:
        return (Path(home).expanduser() / "config.toml").resolve()
    base = (env.get("USERPROFILE") or env.get("HOME") or "").strip()
    root = Path(base).expanduser() if base else Path.home()
    return (root / ".kimi-code" / "config.toml").resolve()


def default_key_file(environ: dict | None = None) -> Path:
    """仓库外的默认密钥文件：`~/.talk/agent-kimi-code-k28-preview.key`。"""
    env = os.environ if environ is None else environ
    base = (env.get("USERPROFILE") or env.get("HOME") or "").strip()
    root = Path(base).expanduser() if base else Path.home()
    return (root / ".talk" / KEY_FILE_NAME).resolve()


def forbidden_key_file(environ: dict | None = None) -> Path:
    """既有成员 `agent:kimi` 的密钥文件；本入口拒绝复用它冒充新成员。"""
    env = os.environ if environ is None else environ
    base = (env.get("USERPROFILE") or env.get("HOME") or "").strip()
    root = Path(base).expanduser() if base else Path.home()
    return (root / ".talk" / FORBIDDEN_KEY_FILE_NAME).resolve()


def validate_key(key: str, *, source: str) -> str:
    if any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in key):
        raise K28ExecutorError(
            f"{source} 的内容不是可用的 API Key：只应包含一行可打印 ASCII 字符"
        )
    return key


def resolve_api_key(
    *,
    environ: dict | None = None,
    key_file: Path | None = None,
    repo_root: Path = REPO_ROOT,
    key_env: str = KEY_ENV,
) -> tuple[str, str]:
    """返回 `(api_key, 来源说明)`；来源说明不含密钥正文。

    `key_env` 只应当是本入口合同环境变量（`TALK_K28_KEY`）：调用方先用
    `check_env_var_name()` 明确校验，不接受未知变量名，避免“传了却不生效”。
    """
    env = os.environ if environ is None else environ
    from_env = (env.get(key_env) or "").strip()
    if from_env:
        return validate_key(from_env, source=f"环境变量 {key_env}"), f"环境变量 {key_env}"

    path = (
        Path(key_file).expanduser().resolve()
        if key_file is not None
        else default_key_file(env)
    )
    if path == forbidden_key_file(env):
        raise K28ExecutorError(
            f"拒绝复用既有成员 agent:kimi 的 TALK Key（{path}）；"
            f"请为新成员准备独立密钥，例如 {default_key_file(env)}"
        )
    try:
        path.relative_to(Path(repo_root).resolve())
    except ValueError:
        pass
    else:
        raise K28ExecutorError(f"密钥文件位于仓库内（{path}）；请移到仓库外再使用")
    if not path.is_file():
        raise K28ExecutorError(
            f"未找到密钥文件 {path}；请创建该文件，或设置环境变量 {KEY_ENV}"
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise K28ExecutorError(f"读取密钥文件失败（{path}）：{exc}") from exc
    for line in text.splitlines():
        candidate = line.strip()
        if candidate:
            return validate_key(candidate, source=f"密钥文件 {path}"), f"密钥文件 {path}"
    raise K28ExecutorError(f"密钥文件为空：{path}")


def redact(text: str, *, secrets: tuple[str, ...] = ()) -> str:
    """去掉常见密钥形态与**本次实际解析出的凭据**；错误信息只走这里输出。

    `secrets` 用于显式隐藏本次启动/请求真正使用的 Key：仓库外文件提供的凭据可以是
    任意可打印 ASCII（不是 `sk-`/`ghp_` 形态），只靠格式或全局环境变量无法覆盖。
    """
    cleaned = str(text)
    for secret in secrets:
        value = str(secret or "")
        if value:
            cleaned = cleaned.replace(value, "[REDACTED]")
    for pattern in REDACT_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    for name in (KEY_ENV, "TALK_API_KEY", "TALK_KIMI_KEY_FILE"):
        value = (os.environ.get(name) or "").strip()
        if value:
            cleaned = cleaned.replace(value, "[REDACTED]")
    return cleaned


def check_env_var_name(key_env: str | None) -> str | None:
    """校验 `--key-env` 是否是合同环境变量；返回问题文本或 None。

    旧版把 `--key-env` 只用于 `require` 判断、却仍固定读 `TALK_K28_KEY`，
    会让一个看似生效的参数被静默忽略。现在只支持合同变量，其它名字直接报错。
    """
    name = (key_env or "").strip()
    if not name:
        return f"--key-env 不能为空；本入口只支持合同环境变量 {KEY_ENV}"
    if name != KEY_ENV:
        return f"--key-env 只支持合同环境变量 {KEY_ENV}，实际 {name!r}；不会静默忽略该参数"
    return None


def bridge_default_command() -> str:
    """只读取得 bridge 的受限默认命令，用于核对固定命令合同没有漂移。"""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from bridges import kimi_bridge  # noqa: PLC0415

    return str(kimi_bridge.DEFAULT_KIMI_COMMAND)


# ---------------------------------------------------------------------------
# native 配置只读解析
# ---------------------------------------------------------------------------


def load_native_config(path: Path) -> dict:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise K28ExecutorError(f"未找到 Kimi Code 配置文件 {path}")
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise K28ExecutorError(f"Kimi Code 配置文件无法解析（{path}）：{exc}") from exc


def native_model_binding(config: dict, alias: str = MODEL_ALIAS) -> dict:
    """从 native 配置里取出 alias 的 provider / model / 显示名 / 能力。

    配置结构非法（`models` 不是表、条目不是表、`capabilities` 不是字符串数组、
    `provider`/`model` 不是字符串）时抛可预期的中文短错误，而不是 `AttributeError` 崩溃。
    """
    models = config.get("models")
    if models is None:
        return {"alias_present": False}
    if not isinstance(models, dict):
        raise K28ExecutorError("native 配置的 models 不是表结构，无法核对模型绑定")
    entry = models.get(alias)
    if entry is None:
        return {"alias_present": False}
    if not isinstance(entry, dict):
        raise K28ExecutorError(f"native 配置 models[{alias!r}] 不是表结构，无法核对模型绑定")

    capabilities = entry.get("capabilities")
    if capabilities is None:
        capabilities = []
    if not isinstance(capabilities, list) or not all(
        isinstance(item, str) for item in capabilities
    ):
        raise K28ExecutorError(
            f"native 配置 models[{alias!r}].capabilities 不是字符串数组"
        )
    for field in ("provider", "model", "display_name"):
        value = entry.get(field)
        if value is not None and not isinstance(value, str):
            raise K28ExecutorError(f"native 配置 models[{alias!r}].{field} 不是字符串")

    return {
        "alias_present": True,
        "provider": entry.get("provider"),
        "model_id": entry.get("model"),
        "display_name": entry.get("display_name"),
        "capabilities": list(capabilities),
        "tool_use": "tool_use" in capabilities,
    }


def kimi_cli_version(environ: dict | None = None) -> dict:
    """只读解析官方 rollout.log 的 `current`；不执行 `kimi --version`。"""
    env = os.environ if environ is None else environ
    config = default_kimi_config_path(env)
    log_path = config.parent / "updates" / "rollout.log"
    if not log_path.is_file():
        return {"version": None, "source": f"{log_path}（不存在）", "executed_cli": False}
    current = None
    try:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            value = payload.get("current")
            if value:
                current = str(value)
    except OSError as exc:
        return {"version": None, "source": f"{log_path}（读取失败：{exc}）", "executed_cli": False}
    return {"version": current, "source": f"{log_path} 最后一条 current", "executed_cli": False}


# ---------------------------------------------------------------------------
# 合同与 argv
# ---------------------------------------------------------------------------


def build_contract(
    *,
    project_root: Path = REPO_ROOT,
    kimi_config: Path | None = None,
    environ: dict | None = None,
) -> dict:
    env = os.environ if environ is None else environ
    config_path = Path(kimi_config) if kimi_config else default_kimi_config_path(env)
    return {
        "schema_version": CONTRACT_SCHEMA,
        "member": {
            "member_id": MEMBER_ID,
            "display_name": DISPLAY_NAME,
            "business_role": BUSINESS_ROLE,
            "decision_tier": DECISION_TIER,
            "project_id": PROJECT_ID,
            "project_root": str(Path(project_root).resolve()),
            "registration_status": "not_registered_in_this_slice",
        },
        "runner": {
            "entry": RUNNER_ENTRY,
            "runtime": RUNTIME,
            "model_source": MODEL_SOURCE,
            "prompt_transport": PROMPT_TRANSPORT,
            "task_tool_profile": TASK_TOOL_PROFILE,
            "discussion_tool_profile": DISCUSSION_TOOL_PROFILE,
            "preflight_tool_profile": PREFLIGHT_TOOL_PROFILE,
            "command_override_allowed": COMMAND_OVERRIDE_ALLOWED,
            "controlled_command": CONTROLLED_KIMI_COMMAND,
            "controlled_command_source": CONTROLLED_COMMAND_SOURCE,
            "env_command_var": ENV_COMMAND_VAR,
            "env_command_ignored": True,
            "decision_tier_argv": DECISION_TIER,
            "base_url_default": DEFAULT_BASE_URL,
            "execution_timeout_seconds": EXECUTION_TIMEOUT_SECONDS,
            "instance_id": f"{MEMBER_ID}:<uuid4>",
        },
        "model": {
            "provider_id": PROVIDER_ID,
            "connection_ref": CONNECTION_REF,
            "config_path": str(config_path),
            "model_config_key": MODEL_ALIAS,
            "model_id": MODEL_ID,
            "model_version_label": MODEL_VERSION_LABEL,
            "version_pinned": MODEL_VERSION_PINNED,
            "default_model_untouched": DEFAULT_MODEL_BASELINE,
            "display_name_is_not_model_id": True,
        },
        "talk_identity": {
            "key_env": KEY_ENV,
            "key_file": str(default_key_file(env)),
            "reuse_agent_kimi_key": False,
        },
        "budget": budget_contract(),
    }


def budget_contract() -> dict:
    return {
        "client_tool_timeout_ms": {
            "value": CLIENT_TOOL_TIMEOUT_TEMPLATE_MS,
            "unit": "ms",
            "source": f"{TEMPLATE_SOURCE}（模板事实）",
            "loaded_on_host": False,
            "verified_on_host": False,
            "note": "模板值 660000ms 不是本机已核验的运行时上限，不得当作实际能力",
        },
        "explicit_wait_seconds": {
            "value": None,
            "margin_seconds": None,
            "enabled": False,
            "reason": "宿主单次工具上限 T 未核验；未核验 T 时不启用主动长等待",
        },
        "bridge_execution_timeout_seconds": {
            "value": EXECUTION_TIMEOUT_SECONDS,
            "source": "本入口合同显式值；沿用 2026-09-12 本机 Kimi/DeepSeek 启动示例的 3600 秒整轮预算",
        },
        "identity_preflight_http_timeout_seconds": {
            "value": HTTP_TIMEOUT_SECONDS,
            "source": "本入口只读身份核验单次 GET 超时；与 bridge 整轮预算分开，最多两次 GET",
        },
        "initiator_wait_in_this_slice": False,
    }


def build_bridge_argv(
    *,
    key_placeholder: str = KEY_PLACEHOLDER,
    project_root: Path = REPO_ROOT,
    base_url: str = DEFAULT_BASE_URL,
    name: str = MEMBER_ID,
    runtime: str = RUNTIME,
    prompt_transport: str = PROMPT_TRANSPORT,
    task_profile: str = TASK_TOOL_PROFILE,
    model: str = MODEL_ALIAS,
    kimi_command: str = CONTROLLED_KIMI_COMMAND,
    decision_tier: str = DECISION_TIER,
    timeout: int = EXECUTION_TIMEOUT_SECONDS,
    instance_id: str | None = None,
) -> list[str]:
    """生成 bridge argv：显式携带受控固定命令与**固定执行分级**，环境/本地来源不生效。"""
    argv = [
        "--name", name,
        "--key", key_placeholder,
        "--base-url", base_url,
        "--display-name", DISPLAY_NAME,
        "--runtime", runtime,
        "--workdir", str(Path(project_root).resolve()),
        "--project", str(Path(project_root).resolve()),
        "--prompt-transport", prompt_transport,
        "--kimi-task-profile", task_profile,
        "--kimi-model", model,
        "--kimi-command", kimi_command,
        # 固定执行分级：远端名册核验的是 execution，argv 必须显式注入同一个值，
        # 否则既有 cli_bridge 会回读本地 .talk/groups.yaml，出现“验 execution、跑 decision”。
        "--decision-tier", decision_tier,
        "--timeout", str(timeout),
    ]
    if instance_id:
        argv += ["--instance-id", instance_id]
    return argv


def resolve_argv_decision_tier(argv: list[str], *, member_id: str = MEMBER_ID) -> str:
    """用**既有 bridge parser**解析真实 argv，再走 bridge 的 `resolve_decision_tier`。

    这是“检查对象 == 执行对象”的证据路径：解析的是本入口真正传给 bridge 的 argv，
    解析函数也是既有 bridge 使用的那一个。
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from bridges import cli_bridge, kimi_bridge  # noqa: PLC0415 - 延迟导入保持离线轻量

    parsed = kimi_bridge.build_parser().parse_args(argv)
    return str(cli_bridge.resolve_decision_tier(parsed, member_id))


def render_launch(
    *,
    project_root: Path = REPO_ROOT,
    base_url: str = DEFAULT_BASE_URL,
    environ: dict | None = None,
) -> dict:
    """可供操作者复制的最小启动命令；密钥位置是占位符。"""
    env = os.environ if environ is None else environ
    argv = build_bridge_argv(project_root=project_root, base_url=base_url)
    key_argv = ["--key", KEY_PLACEHOLDER]
    python = sys.executable or "python"
    command = " ".join(
        shlex.quote(item) for item in [python, str((REPO_ROOT / RUNNER_ENTRY).resolve()), *argv]
    )
    return {
        "ok": True,
        "mode": "render",
        "member_id": MEMBER_ID,
        "model_alias": MODEL_ALIAS,
        "base_url": base_url,
        "key_env": KEY_ENV,
        "default_key_file": str(default_key_file(env)),
        "bridge_argv": argv,
        "key_argv_placeholder": key_argv,
        "command_template": command,
        "contains_secret": False,
        "note": (
            "recommended: `scripts/kimi_k28_executor.py launch` 在本进程内注入密钥；"
            "上面命令行只用于核对参数，--key 处必须换成真实密钥，不要写入仓库或日志"
        ),
    }


# ---------------------------------------------------------------------------
# 离线检查
# ---------------------------------------------------------------------------


def _add(checks: list[dict], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def _materialize_reference_commands(
    argv: list[str],
    runtime_dir: Path,
) -> tuple[object, tuple[str, str, str]]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from bridges import kimi_bridge  # noqa: PLC0415 - 延迟导入，contract/render 保持离线轻量

    args = kimi_bridge.build_parser().parse_args(argv)
    return kimi_bridge, kimi_bridge.materialize_kimi_commands(args, runtime_dir)


def run_check(
    *,
    project_root: Path = REPO_ROOT,
    kimi_config: Path | None = None,
    key_file: Path | None = None,
    key_env: str = KEY_ENV,
    require_key: bool = False,
    name: str = MEMBER_ID,
    runtime: str = RUNTIME,
    prompt_transport: str = PROMPT_TRANSPORT,
    task_profile: str = TASK_TOOL_PROFILE,
    model: str = MODEL_ALIAS,
    kimi_command: str | None = None,
    decision_tier: str = DECISION_TIER,
    timeout: int = EXECUTION_TIMEOUT_SECONDS,
    identity_report: dict | None = None,
    online_identity: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    http_timeout: float = HTTP_TIMEOUT_SECONDS,
    environ: dict | None = None,
) -> dict:
    env = os.environ if environ is None else environ
    checks: list[dict] = []
    problems: list[str] = []
    not_run: list[str] = []
    network_calls = 0

    # 1) 固定身份 / 运行器参数
    _add(checks, "member_identity", name == MEMBER_ID, f"member_id={name}")
    if name != MEMBER_ID:
        problems.append(f"成员身份必须是 {MEMBER_ID}，实际 {name}")

    base_url_ok = bool(str(base_url or "").strip())
    _add(
        checks,
        "base_url_contract",
        base_url_ok,
        f"base_url={base_url!r}（argv 与实际只读预检必须使用同一个值）",
    )
    if not base_url_ok:
        problems.append("base_url 不能为空；argv 与只读身份预检必须使用同一个有效服务地址")

    runner_ok = runtime == RUNTIME and prompt_transport == PROMPT_TRANSPORT
    _add(
        checks,
        "runner_binding",
        runner_ok,
        f"runtime={runtime} prompt_transport={prompt_transport}",
    )
    if runtime != RUNTIME:
        problems.append(f"runtime 必须是 {RUNTIME}，实际 {runtime}")

    profile_ok = task_profile == TASK_TOOL_PROFILE
    _add(
        checks,
        "task_tool_profile",
        profile_ok,
        f"task={task_profile} discussion={DISCUSSION_TOOL_PROFILE} preflight={PREFLIGHT_TOOL_PROFILE}",
    )
    if not profile_ok:
        problems.append(f"任务工具档必须是 {TASK_TOOL_PROFILE}，实际 {task_profile}")

    transport_ok = prompt_transport == PROMPT_TRANSPORT
    if not transport_ok:
        problems.append(f"prompt 传递必须是 {PROMPT_TRANSPORT}，实际 {prompt_transport}")

    alias_lock_ok = model == MODEL_ALIAS
    _add(checks, "model_alias_lock", alias_lock_ok, f"model alias={model}")
    if not alias_lock_ok:
        problems.append(f"模型 alias 必须锁定为 {MODEL_ALIAS}，实际 {model}")

    budget_ok = isinstance(timeout, int) and timeout > 0
    _add(
        checks,
        "execution_budget",
        budget_ok,
        f"bridge execution timeout={timeout}s（显式合同值，不等同发起者等待预算）",
    )
    if not budget_ok:
        problems.append("bridge 执行预算必须是显式正整数秒")

    # 2) native 配置合同（只读；期间核对文件未被写入）
    config_path = Path(kimi_config) if kimi_config else default_kimi_config_path(env)
    config_path = config_path.expanduser().resolve()
    before_hash = None
    native = {}
    config_error = None
    if config_path.is_file():
        before_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
        try:
            native = load_native_config(config_path)
        except K28ExecutorError as exc:
            config_error = redact(str(exc))
    else:
        config_error = f"未找到 Kimi Code 配置文件 {config_path}"

    _add(
        checks,
        "native_config_present",
        config_error is None,
        config_error or f"已只读解析 {config_path}",
    )
    if config_error:
        problems.append(config_error)

    binding: dict = {"alias_present": False}
    binding_error = None
    if native:
        try:
            binding = native_model_binding(native)
        except K28ExecutorError as exc:
            binding_error = redact(str(exc))
            problems.append(binding_error)

    alias_ok = bool(binding.get("alias_present"))
    _add(
        checks,
        "native_model_alias",
        alias_ok,
        f"models[{MODEL_ALIAS!r}] {'存在' if alias_ok else '缺失'}（alias 不存在时不得启动）",
    )
    if not alias_ok and native and binding_error is None:
        problems.append(f"native 配置缺少模型 alias {MODEL_ALIAS}")

    binding_ok = bool(alias_ok)
    binding_detail = binding_error or "alias 缺失，未比对绑定"
    if alias_ok:
        binding_ok = (
            binding.get("provider") == PROVIDER_ID
            and binding.get("model_id") == MODEL_ID
            and bool(binding.get("tool_use"))
        )
        binding_detail = (
            f"provider={binding.get('provider')} model={binding.get('model_id')} "
            f"display_name={binding.get('display_name')!r} tool_use={binding.get('tool_use')}"
        )
        if binding.get("provider") != PROVIDER_ID:
            problems.append(
                f"alias {MODEL_ALIAS} 的 provider 期望 {PROVIDER_ID}，实际 {binding.get('provider')}"
            )
        if binding.get("model_id") != MODEL_ID:
            problems.append(
                f"alias {MODEL_ALIAS} 的 model 期望 {MODEL_ID}，实际 {binding.get('model_id')}"
            )
        if not binding.get("tool_use"):
            problems.append(f"alias {MODEL_ALIAS} 未声明 tool_use 能力")
    if binding_error is not None:
        binding_ok = False
    _add(checks, "native_model_binding", binding_ok, binding_detail)

    after_hash = hashlib.sha256(config_path.read_bytes()).hexdigest() if config_path.is_file() else None
    untouched = before_hash is not None and before_hash == after_hash
    _add(
        checks,
        "default_model_untouched",
        untouched,
        (
            f"default_model={native.get('default_model')!r}（本入口只读，未修改）；"
            f"sha256 {str(before_hash)[:12]} → {str(after_hash)[:12]}"
        ),
    )
    if before_hash is not None and not untouched:
        problems.append("检查过程修改了 native 配置文件")

    # 3) 受控固定命令：拒绝任何自定义 --kimi-command；核对合同命令与 bridge 默认一致
    try:
        default_command = bridge_default_command()
    except Exception as exc:  # noqa: BLE001 - 依赖缺失时如实报错，不让 traceback 逃出
        default_command = ""
        problems.append(f"无法读取 bridge 默认命令：{redact(exc)}")
    command_contract_ok = default_command == CONTROLLED_KIMI_COMMAND
    _add(
        checks,
        "controlled_command_contract",
        command_contract_ok,
        f"合同固定命令={CONTROLLED_KIMI_COMMAND!r}；bridge DEFAULT={default_command!r}",
    )
    if not command_contract_ok and default_command:
        problems.append(
            "受控固定命令与 bridges/kimi_bridge.py 的 DEFAULT_KIMI_COMMAND 不一致；"
            "命令合同漂移时本入口拒绝启动"
        )

    override = (kimi_command or "").strip() or None
    override_ok = override is None or override == CONTROLLED_KIMI_COMMAND
    if override is None:
        override_detail = (
            f"未使用自定义命令；argv 显式携带合同固定命令（忽略环境变量 {ENV_COMMAND_VAR}）"
        )
    elif override_ok:
        override_detail = "显式命令与合同固定命令一致"
    else:
        override_detail = "自定义命令被拒绝（command_override_allowed=false）"
        problems.append(
            "command_override_allowed=false：本入口拒绝任何非合同 --kimi-command；"
            f"收到 {redact(override)[:120]!r}"
        )
    _add(checks, "command_override", override_ok, override_detail)

    argv = build_bridge_argv(
        project_root=project_root,
        base_url=base_url,
        name=name,
        runtime=runtime,
        prompt_transport=prompt_transport,
        task_profile=task_profile,
        model=model,
        kimi_command=override or CONTROLLED_KIMI_COMMAND,
        decision_tier=decision_tier,
        timeout=timeout,
    )

    # 4) 执行分级合同：argv 显式固定 execution；用既有 bridge parser + resolve_decision_tier
    #    解析**同一份 argv**，本地 .talk/groups.yaml 的 decision 不得覆盖固定执行合同。
    tier_resolved = ""
    tier_error = None
    try:
        tier_resolved = resolve_argv_decision_tier(argv)
    except Exception as exc:  # noqa: BLE001 - 解析失败按门禁失败处理，不回显原文
        tier_error = redact(exc)
    tier_ok = tier_error is None and tier_resolved == DECISION_TIER
    _add(
        checks,
        "decision_tier_binding",
        tier_ok,
        (
            f"argv 显式 --decision-tier {decision_tier}；bridge resolve_decision_tier → "
            f"{tier_resolved or '无法解析'}（本地 groups.yaml 不得覆盖固定 {DECISION_TIER}）"
        ),
    )
    if not tier_ok:
        problems.append(
            tier_error
            or f"执行分级必须是 {DECISION_TIER}，bridge 实际解析为 {tier_resolved or '未知'}；"
            "固定执行合同不允许改按本地 decision 执行"
        )

    materialize_ok = False
    materialize_detail = "参数未通过前置检查，未生成运行命令"
    fixture_files: dict[str, str] = {}
    if override_ok and command_contract_ok and runner_ok and profile_ok and transport_ok and budget_ok:
        try:
            with tempfile.TemporaryDirectory(prefix="k28-executor-check-") as temp_dir:
                kimi_bridge, commands = _materialize_reference_commands(argv, Path(temp_dir))
                parsed = [shlex.split(command, posix=True) for command in commands]
                # 环境继承/覆盖命令一旦生效，三档都会退化成不带 --agent-file 的字面命令。
                all_have_agent = all("--agent-file" in item for item in parsed)
                all_have_skills = all("--skills-dir" in item for item in parsed)
                all_generated = all(
                    command not in {CONTROLLED_KIMI_COMMAND, override} for command in commands
                )
                pinned = all(
                    "--model" in item and item[item.index("--model") + 1] == model
                    for item in parsed
                )
                stream_json = all(
                    item[item.index("--output-format") + 1] == "stream-json" for item in parsed
                )
                ends_with_p = all(item[-1] == "-p" for item in parsed)
                tools_isolated = False
                if all_have_agent:
                    task_file = parsed[1][parsed[1].index("--agent-file") + 1]
                    message_file = parsed[0][parsed[0].index("--agent-file") + 1]
                    preflight_file = parsed[2][parsed[2].index("--agent-file") + 1]
                    for label, path in (
                        ("discussion", message_file),
                        ("task", task_file),
                        ("preflight", preflight_file),
                    ):
                        fixture_files[label] = Path(path).read_text(encoding="utf-8")
                    tools_isolated = (
                        "tools: []" in fixture_files["discussion"]
                        and "tools: []" in fixture_files["preflight"]
                        and "  - Edit" in fixture_files["task"]
                        and "  - Write" in fixture_files["task"]
                        and all("subagents: []" in text for text in fixture_files.values())
                    )
                materialize_ok = (
                    all_have_agent
                    and all_have_skills
                    and all_generated
                    and pinned
                    and stream_json
                    and ends_with_p
                    and tools_isolated
                )
                materialize_detail = (
                    f"三档命令均锁定 --model {model} 且带受控 Agent 文件；task 档含 Edit/Write，"
                    f"讨论/预检 tools: []，三档 subagents: []"
                )
                if not all_have_agent:
                    problems.append("三档运行命令缺少 --agent-file：受控命令被环境变量或覆盖命令替换")
                if not all_have_skills:
                    problems.append("三档运行命令缺少 --skills-dir，Agent 工具档无法隔离")
                if not all_generated:
                    problems.append("三档命令退化为字面固定命令，未生成受控 Agent 文件")
                if not pinned:
                    problems.append("生成的任务命令未锁定模型 alias")
                if not stream_json:
                    problems.append("生成命令缺少 stream-json 输出格式")
                if not ends_with_p:
                    problems.append("生成命令未以 -p 结尾，argv prompt 运输不符合合同")
                if not tools_isolated:
                    problems.append("工具档隔离不符合合同（讨论/预检必须无工具，任务档才含 Edit/Write）")
        except (ValueError, OSError, SystemExit) as exc:  # pragma: no cover - 防御性
            materialize_ok = False
            materialize_detail = f"生成运行命令失败：{redact(exc)}"
            problems.append(materialize_detail)
    else:
        not_run.append("materialize_commands")
    _add(checks, "model_lock_and_tool_isolation", materialize_ok, materialize_detail)

    # 4) 项目绑定
    project_ok = True
    project_detail = ""
    try:
        from cli.talk import load_project  # noqa: PLC0415

        meta = load_project(Path(project_root).expanduser().resolve())
        actual_project = str(meta.get("project_id") or "")
        project_ok = actual_project == PROJECT_ID
        project_detail = f"{Path(project_root).resolve()} → project_id={actual_project or '未知'}"
        if not project_ok:
            problems.append(f"项目绑定不匹配：期望 {PROJECT_ID}，实际 {actual_project or '未知'}")
    except (FileNotFoundError, OSError, ValueError) as exc:
        project_ok = False
        project_detail = f"读取 .talk/project.yaml 失败：{redact(exc)}"
        problems.append(project_detail)
    _add(checks, "project_binding", project_ok, project_detail)

    # 5) 凭据来源（只报来源，不打印正文）；--key-env 只接受合同环境变量
    key_env_problem = check_env_var_name(key_env)
    _add(checks, "key_env_contract", key_env_problem is None, key_env_problem or f"--key-env={KEY_ENV}")
    if key_env_problem:
        problems.append(key_env_problem)

    key_ok = False
    key_detail = ""
    key_source = None
    resolved_key = None
    effective_key_env = key_env if key_env_problem is None else KEY_ENV
    force_require = require_key or bool((env.get(effective_key_env) or "").strip())
    try:
        resolved_key, key_source = resolve_api_key(
            environ=env, key_file=key_file, key_env=effective_key_env
        )
        key_ok = True
        key_detail = f"凭据来源：{key_source}（未复用 agent:kimi 的 Key）"
    except K28ExecutorError as exc:
        key_detail = redact(str(exc))
        if force_require or online_identity:
            problems.append(key_detail)
        else:
            not_run.append("talk_identity_key")
            key_detail = f"{key_detail}；未提供凭据，本轮按 not_run 记录"
    _add(checks, "talk_identity_key", key_ok or not (force_require or online_identity), key_detail)

    # 6) 身份一致性
    identity_verified = False
    if online_identity:
        if resolved_key is None:
            _add(checks, "identity_binding", False, "在线身份核验需要可解析的 TALK Key")
            not_run.append("online_identity_check")
        else:
            online = identity_preflight(
                base_url=base_url,
                api_key=resolved_key,
                http_timeout=http_timeout,
            )
            network_calls += int(online.get("network_calls") or 0)
            identity_verified = bool(online.get("ok"))
            _add(
                checks,
                "identity_binding",
                identity_verified,
                "; ".join(online["problems"]) if online["problems"] else "只读在线身份与项目名册一致",
            )
            problems.extend(online["problems"])
    elif identity_report is None:
        not_run.append("online_identity_check")
        _add(
            checks,
            "identity_binding",
            True,
            "未提供身份报告且未启用 --online-identity：本轮不做在线身份核对（离线边界见测试）",
        )
    else:
        identity_problems = identity_check(identity_report)
        _add(
            checks,
            "identity_binding",
            not identity_problems,
            "; ".join(identity_problems) if identity_problems else "离线身份报告与项目一致（非在线核验）",
        )
        problems.extend(identity_problems)

    return {
        "ok": all(check["ok"] for check in checks) and not problems,
        "mode": "check",
        "member_id": MEMBER_ID,
        "model_alias": MODEL_ALIAS,
        "checks": checks,
        "problems": problems,
        "not_run": not_run,
        "native_config": {
            "path": str(config_path),
            "exists": config_path.is_file(),
            "default_model": native.get("default_model"),
            "binding": binding,
        },
        "cli_version": kimi_cli_version(env),
        "budget": budget_contract(),
        "controlled_command": CONTROLLED_KIMI_COMMAND,
        "identity_verified": identity_verified,
        "online_identity_checked": bool(online_identity),
        "network_calls": network_calls,
        "note": (
            "离线检查只证明配置合同与生成命令一致；只有 --online-identity 才做只读身份核验。"
            "真实模型推理、宿主 MCP 工具加载、新成员注册与领取交付均未验证"
        ),
    }


def identity_check(
    report: dict,
    *,
    expect_member: str = MEMBER_ID,
    expect_project: str = PROJECT_ID,
) -> list[str]:
    """核对“凭证对应的成员/项目就是本入口身份”；返回中文问题列表。"""
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from kimi_talk_precheck import assert_identity  # noqa: PLC0415

    return assert_identity(
        report,
        expect_member=expect_member,
        expect_project=expect_project,
    )


def _http_error_detail(exc: HTTPError) -> str:
    """只回 HTTP 状态与固定短说明；**不读取、不回显**服务端错误正文。

    远端正文可能原样回显本次凭据，而文件来源的 Key 可以是任意可打印 ASCII
    （不是 `sk-`/`ghp_` 形态），因此这里不解析 body，也不依赖密钥格式或全局
    环境变量做脱敏；调用方另有 `redact(..., secrets=(api_key,))` 精确兜底。
    """
    return f"HTTP {exc.code}：服务端错误正文已隐藏"


def _http_get_json(url: str, *, api_key: str, timeout: float) -> object:
    """只读 GET JSON；密钥只进请求头，任何错误文本都不含密钥。"""
    request = Request(
        url,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as exc:
        raise K28ExecutorError(
            f"只读身份请求失败：{_http_error_detail(exc)}"
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise K28ExecutorError(f"只读身份请求失败：无法连接 TALK API（{reason}）") from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise K28ExecutorError("只读身份请求失败：服务端返回了无效 JSON") from exc


def identity_preflight(
    *,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str,
    expect_member: str = MEMBER_ID,
    expect_project: str = PROJECT_ID,
    expect_kind: str = "agent",
    expect_business_role: str = BUSINESS_ROLE,
    expect_decision_tier: str = DECISION_TIER,
    http_timeout: float = HTTP_TIMEOUT_SECONDS,
    get_json=None,
) -> dict:
    """真实启动前的**只读**服务端身份核验；不注册、不上报实例、不调用模型。

    步骤与失败边界：

    1. `GET /api/members/me`：Key 必须对应**已存在**的本人（`id == expect_member`）
       且 `kind == agent`；未注册 Key（HTTP 401）、其它成员 Key（id 不符）直接失败。
    2. `GET /api/projects/{project_id}/agents`：本人必须在项目名册中，且
       `business_role` / `decision_tier` 与本入口分级一致；错误项目（HTTP 404）、
       非 agent、名册缺失或角色不一致都失败。
    3. 任一网络错误都在此返回失败；调用方必须在 `client.register` 之前终止。

    返回结构化报告（不抛异常给调用方，便于记录与测试）；`problems` 为短中文，
    不含任何 Key 正文。
    """
    getter = get_json or _http_get_json
    base = str(base_url or "").rstrip("/")
    checks: list[dict] = []
    problems: list[str] = []
    network_calls = 0

    member_id: object = None
    kind: object = None
    me: object = None
    if not base:
        problems.append("身份核验失败：base_url 为空，拒绝启动")
    else:
        try:
            network_calls += 1
            me = getter(f"{base}{MEMBERS_ME_PATH}", api_key=api_key, timeout=http_timeout)
        except K28ExecutorError as exc:
            problems.append(redact(str(exc), secrets=(api_key,)))

    if not problems:
        if not isinstance(me, dict):
            problems.append("身份核验失败：GET /api/members/me 响应不是对象")
        else:
            member_id = me.get("id")
            kind = me.get("kind")
            if not isinstance(member_id, str) or not member_id.strip():
                problems.append("身份核验失败：GET /api/members/me 未返回合法 id")
            elif member_id.strip() != expect_member:
                problems.append(
                    f"身份核验失败：该 Key 对应 {member_id}，不是本入口成员 {expect_member}；"
                    "不得用其它成员的 Key 启动"
                )
            if kind != expect_kind:
                problems.append(f"身份核验失败：成员 kind 期望 {expect_kind}，实际 {kind!r}")
        _add(
            checks,
            "members_me",
            not problems,
            f"member_id={member_id!r} kind={kind!r}（只读 GET {MEMBERS_ME_PATH}）",
        )

    roster_entry: dict | None = None
    if not problems:
        try:
            network_calls += 1
            roster = getter(
                f"{base}{PROJECT_AGENTS_PATH.format(project_id=expect_project)}",
                api_key=api_key,
                timeout=http_timeout,
            )
        except K28ExecutorError as exc:
            problems.append(redact(str(exc), secrets=(api_key,)))
        else:
            if not isinstance(roster, list):
                problems.append("身份核验失败：项目名册响应不是数组")
            else:
                for entry in roster:
                    if isinstance(entry, dict) and str(entry.get("member_id") or "") == expect_member:
                        roster_entry = entry
                        break
                if roster_entry is None:
                    problems.append(
                        f"身份核验失败：{expect_member} 不在项目 {expect_project} 的 agent 名册中；"
                        "本入口不自动首次注册"
                    )
                else:
                    actual_role = roster_entry.get("business_role")
                    actual_tier = roster_entry.get("decision_tier")
                    if str(actual_role or "") != expect_business_role:
                        problems.append(
                            f"身份核验失败：名册 business_role 期望 {expect_business_role}，实际 {actual_role!r}"
                        )
                    if str(actual_tier or "") != expect_decision_tier:
                        problems.append(
                            f"身份核验失败：名册 decision_tier 期望 {expect_decision_tier}，实际 {actual_tier!r}"
                        )
        _add(
            checks,
            "project_roster",
            not problems,
            (
                f"project={expect_project} roster_found={roster_entry is not None} "
                f"business_role={(roster_entry or {}).get('business_role')!r} "
                f"decision_tier={(roster_entry or {}).get('decision_tier')!r}"
            ),
        )

    return {
        "ok": not problems,
        "mode": "identity-preflight",
        "base_url": base,
        "read_only": True,
        "expect_member": expect_member,
        "project_id": expect_project,
        "member_id": member_id,
        "kind": kind,
        "business_role": (roster_entry or {}).get("business_role"),
        "decision_tier": (roster_entry or {}).get("decision_tier"),
        "roster_found": roster_entry is not None,
        "checks": checks,
        "problems": problems,
        "network_calls": network_calls,
        "note": (
            "只读 GET /api/members/me 与项目名册；不注册成员、不上报实例、不调用模型；"
            "离线 fixture 不等于本核验"
        ),
    }


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------


def run_launch(
    *,
    project_root: Path = REPO_ROOT,
    key_file: Path | None = None,
    environ: dict | None = None,
    dry_run: bool = False,
    base_url: str = DEFAULT_BASE_URL,
) -> int:
    env = os.environ if environ is None else environ
    key, source = resolve_api_key(environ=env, key_file=key_file)

    # 1) 启动前检查：与 bridge 同一条路径（固定受控命令 + 固定执行分级 + 本次实际 native
    #    配置 + 项目绑定 + **同一个 base_url**）。这里默认 kimi_config=None，即读取 CLI 真正
    #    使用的那份 config.toml；不接受“检查一个、启动另一个”。任何一项失败都在任何
    #    bridge/模型/生产写操作之前退出。
    gate = run_check(
        project_root=project_root,
        key_file=key_file,
        require_key=True,
        environ=env,
        base_url=base_url,
    )
    if not gate["ok"]:
        raise K28ExecutorError(
            "启动前检查未通过：" + "；".join(gate["problems"][:3])
        )

    # B1：argv 与只读预检使用**同一个** base_url，否则会出现“验 19091、跑 8000”。
    argv = build_bridge_argv(project_root=project_root, base_url=base_url)
    redacted = " ".join(
        shlex.quote("[REDACTED]" if item == KEY_PLACEHOLDER else item) for item in argv
    )
    print(
        f"Kimi K2.8 独立执行入口：成员 {MEMBER_ID}；密钥来源 {source}；"
        f"模型 alias {MODEL_ALIAS}；任务档 {TASK_PROFILE_SUMMARY}；"
        f"执行分级 {DECISION_TIER}；服务地址 {base_url}；"
        f"受控命令 {CONTROLLED_KIMI_COMMAND!r}",
        file=sys.stderr,
    )
    if dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "launch-dry-run",
                    "argv": redacted,
                    "base_url": base_url,
                    "decision_tier": DECISION_TIER,
                    "controlled_command": CONTROLLED_KIMI_COMMAND,
                    "identity_verified": False,
                    "online_identity_checked": False,
                    "note": (
                        "dry-run 只做了启动前离线检查并打印脱敏 argv；"
                        "未做在线身份核验、未启动 bridge"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    # 2) 真实启动前的只读身份核验：必须早于 client.register / 实例上报 / 模型调用。
    identity = identity_preflight(base_url=base_url, api_key=key)
    if not identity["ok"]:
        raise K28ExecutorError(
            "启动前身份核验未通过：" + "；".join(identity["problems"][:3])
        )
    print(
        f"在线身份核验通过（只读）：member_id={identity['member_id']} kind={identity['kind']} "
        f"business_role={identity['business_role']} decision_tier={identity['decision_tier']}",
        file=sys.stderr,
    )

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from bridges import cli_bridge, kimi_bridge  # noqa: PLC0415

    args = kimi_bridge.build_parser().parse_args(argv)
    # 密钥只在内存里替换占位符：不进入命令行、日志或仓库文件。
    args.key = key
    # B2 双保险：既有 bridge 会用同一个 resolve_decision_tier 解析 argv；固定执行合同
    # 必须解析为 execution，任何本地来源都不能让实际运行按 decision 执行。
    resolved_tier = cli_bridge.resolve_decision_tier(args, MEMBER_ID)
    if resolved_tier != DECISION_TIER:
        raise K28ExecutorError(
            f"执行分级解析为 {resolved_tier}，固定合同要求 {DECISION_TIER}；拒绝以 decision 启动"
        )
    asyncio.run(kimi_bridge.run_bridge(args))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kimi Code + K2.8 Preview 独立执行入口（无密钥合同 / 离线检查 / 启动）",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    contract_parser = sub.add_parser("contract", help="打印本入口配置合同（零密钥）")
    contract_parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    contract_parser.add_argument("--kimi-config", type=Path, default=None)

    check_parser = sub.add_parser("check", help="离线检查配置合同与失败边界")
    check_parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    check_parser.add_argument("--kimi-config", type=Path, default=None)
    check_parser.add_argument("--key-file", type=Path, default=None)
    check_parser.add_argument("--key-env", default=KEY_ENV)
    check_parser.add_argument("--require-key", action="store_true")
    check_parser.add_argument("--name", default=MEMBER_ID)
    check_parser.add_argument("--runtime", default=RUNTIME)
    check_parser.add_argument("--prompt-transport", default=PROMPT_TRANSPORT)
    check_parser.add_argument("--kimi-task-profile", default=TASK_TOOL_PROFILE)
    check_parser.add_argument("--kimi-model", default=MODEL_ALIAS)
    check_parser.add_argument("--kimi-command", default=None)
    check_parser.add_argument("--timeout", type=int, default=EXECUTION_TIMEOUT_SECONDS)
    check_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    check_parser.add_argument(
        "--online-identity",
        action="store_true",
        help="额外做一次只读在线身份核验（GET /api/members/me + 项目名册）；需要可解析的 Key",
    )
    check_parser.add_argument(
        "--identity-report",
        type=Path,
        default=None,
        help="离线身份报告 JSON（member_id/project_id/ok），用于核对绑定不一致边界",
    )

    render_parser = sub.add_parser("render", help="打印 bridge argv 模板（密钥为占位符）")
    render_parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    render_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)

    launch_parser = sub.add_parser("launch", help="解析本人 Key 后在本进程内启动现有 Kimi bridge")
    launch_parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    launch_parser.add_argument("--key-file", type=Path, default=None)
    launch_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    launch_parser.add_argument("--dry-run", action="store_true", help="只做离线检查并打印脱敏 argv，不启动")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):  # pragma: no cover
                pass
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "contract":
            print(
                json.dumps(
                    build_contract(project_root=args.project_root, kimi_config=args.kimi_config),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.mode == "render":
            print(
                json.dumps(
                    render_launch(project_root=args.project_root, base_url=args.base_url),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.mode == "launch":
            return run_launch(
                project_root=args.project_root,
                key_file=args.key_file,
                dry_run=args.dry_run,
                base_url=args.base_url,
            )
        identity_report = None
        if args.identity_report is not None:
            try:
                identity_report = json.loads(args.identity_report.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise K28ExecutorError(f"身份报告无法解析：{redact(exc)}") from exc
        report = run_check(
            project_root=args.project_root,
            kimi_config=args.kimi_config,
            key_file=args.key_file,
            key_env=args.key_env,
            require_key=args.require_key,
            name=args.name,
            runtime=args.runtime,
            prompt_transport=args.prompt_transport,
            task_profile=args.kimi_task_profile,
            model=args.kimi_model,
            kimi_command=args.kimi_command,
            timeout=args.timeout,
            identity_report=identity_report,
            online_identity=args.online_identity,
            base_url=args.base_url,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    except K28ExecutorError as exc:
        print(f"Kimi K2.8 执行入口失败：{redact(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
