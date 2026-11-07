"""Pure recovery-host resolution for one already-owned role service.

The resolver maps persisted project/member/runner facts to the *same*
deterministic health file and host entry that the local runtime uses when it
starts a host. Resolution itself does not read health files, credentials, the
process table, or native configuration, and it never starts a resolver/host.

Fixed ``hosts`` recipes remain first priority.  Dynamic Kimi/Codex/DSH/WorkBuddy
are selected only from the original instance runtime plus the current managed
runner facts; a mere ``workbuddy`` config section is not identity evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import json
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]

# runtime -> (config section, manager directory, host module)
_DYNAMIC = {
    "kimi-code": ("kimi", "kimi-dynamic", "scripts.kimi_role_host"),
    "codex": ("codex", "codex-dynamic", "scripts.codex_role_host"),
    "dsh": ("dsh", "dsh-dynamic", "scripts.dsh_role_host"),
    "workbuddy": ("workbuddy", "workbuddy-native", "scripts.workbuddy_role_host"),
}


class RecoveryHostError(Exception):
    """Stable reason for refusing to resolve recovery evidence."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RecoveryHost:
    source: str
    runner: str | None
    health_file: Path
    host_entry: Path


def _sanitize(value: str) -> str:
    # Match the manager path contract exactly; this is a pure string transform.
    from scripts.role_service_host import _sanitize_token
    return _sanitize_token(value)


def _module_entry(module: str, project_root: Path) -> Path | None:
    if not isinstance(module, str) or not module.startswith("scripts."):
        return None
    parts = module.split(".")
    if len(parts) < 2 or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
        return None
    candidate = project_root.joinpath(*parts).with_suffix(".py")
    if candidate.is_file():
        return candidate
    # The runtime is normally spawned with cwd=project_root.  If this server's
    # candidate/embedded source root differs, only the same deterministic
    # scripts/<module>.py under this server is considered; no directory scan.
    return ROOT.joinpath(*parts).with_suffix(".py")


def entry_from_argv(argv: Sequence[Any], project_root: Path | None = None) -> Path | None:
    """Resolve the two real launch contracts, never a display name or model.

    Supported forms are ``python ... -m scripts.<module> ...`` and
    ``python ... <host>.py ...`` (absolute or relative to project_root).
    """
    if not isinstance(argv, (list, tuple)) or len(argv) < 2:
        return None
    if any(not isinstance(item, str) or not item for item in argv):
        return None
    base = Path(project_root) if project_root is not None else ROOT
    for index, item in enumerate(argv[:-1]):
        if item == "-m":
            return _module_entry(argv[index + 1], base)
    for item in argv[1:]:
        if item.endswith(".py"):
            path = Path(item)
            if not path.is_absolute():
                path = base / path
            return path
    return None


def workspace_manager_health_path(data_root: Path, project_id: str, member_id: str, runner: str) -> Path:
    """Return only the authoritative workspace manager health path."""
    from server.workspace_paths import manager_dir, _checked
    if runner not in _DYNAMIC or not Path(data_root).is_absolute():
        raise RecoveryHostError("local_recovery_host_unconfigured")
    return _checked(manager_dir(Path(data_root), project_id, member_id, _DYNAMIC[runner][0]) / "manager-health.json")


def workspace_capability_matches(health_file: Path, *, manager_protocol: str, project_id: str,
                                 member_id: str, runner: str, instance_id: str | None = None,
                                 generation: int | None = None, launch_id: str | None = None,
                                 host: str | None = None,
                                 manager_instance_id: str | None = None) -> bool:
    """Read role evidence, optionally requiring a complete launch binding."""
    try:
        health = json.loads(Path(health_file).read_text(encoding="utf-8"))
        capability = health.get("capability")
        if host is not None and (not host or health.get("host") != host):
            return False
        if manager_instance_id is not None and (not manager_instance_id
                or health.get("manager_instance_id") != manager_instance_id):
            return False
        if not isinstance(capability, dict):
            return False
        role, binding, layouts = (capability.get("role"), capability.get("binding"),
                                  capability.get("supported_layouts"))
        if not (capability.get("schema") == "talk-role-capability-1"
                and capability.get("manager_protocol") == manager_protocol
                and isinstance(layouts, list) and "workspace-v1" in layouts
                and isinstance(role, dict) and role.get("project_id") == project_id
                and role.get("member_id") == member_id and role.get("runner") == runner):
            return False
        if instance_id is None and generation is None and launch_id is None:
            return True
        return (isinstance(instance_id, str) and bool(instance_id)
                and type(generation) is int and isinstance(launch_id, str) and bool(launch_id)
                and isinstance(binding, dict) and binding.get("instance_id") == instance_id
                and type(binding.get("generation")) is int and binding.get("generation") == generation
                and binding.get("launch_id") == launch_id)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def resolve_recovery_host(*, config: Mapping[str, Any], project_id: str, member_id: str,
                          original_runtime: str | None, current_runtime: str | None,
                          control_kind: str | None, storage_layout: str = "legacy",
                          data_root: Path | None = None) -> RecoveryHost:
    """Resolve evidence path/entry or raise a stable recovery refusal code."""
    if not isinstance(project_id, str) or not project_id or not isinstance(member_id, str) or not member_id:
        raise RecoveryHostError("local_recovery_identity_unverified")
    if storage_layout == "workspace-v1":
        # The caller must obtain the layout from the project/member authority,
        # and supply the deployment data root used by the runtime.  In
        # particular, never consult configured fixed or legacy health paths.
        from server.workspace_paths import WorkspacePathError, manager_dir, _checked
        if original_runtime not in _DYNAMIC or current_runtime != original_runtime or control_kind != "managed_cli":
            raise RecoveryHostError("local_recovery_binding_changed")
        if data_root is None or not Path(data_root).is_absolute():
            raise RecoveryHostError("local_recovery_host_unconfigured")
        recipe_key, _, module = _DYNAMIC[original_runtime]
        recipe = config.get(recipe_key)
        if (not isinstance(recipe, Mapping) or not recipe
                or (original_runtime != "workbuddy" and recipe.get("enabled") is not True)):
            raise RecoveryHostError("local_recovery_host_unconfigured")
        configured_root = config.get("project_root")
        root = Path(configured_root) if isinstance(configured_root, str) and configured_root else ROOT
        entry = _module_entry(module, root)
        if entry is None:
            raise RecoveryHostError("local_recovery_entry_unverified")
        try:
            health = workspace_manager_health_path(Path(data_root), project_id, member_id, original_runtime)
        except (WorkspacePathError, OSError, ValueError) as exc:
            raise RecoveryHostError("local_recovery_host_unconfigured") from exc
        return RecoveryHost("workspace-" + original_runtime, original_runtime, health, entry)
    if storage_layout != "legacy":
        raise RecoveryHostError("local_recovery_identity_unverified")
    hosts = config.get("hosts") or []
    if not isinstance(hosts, list):
        raise RecoveryHostError("local_recovery_host_unconfigured")
    fixed = [spec for spec in hosts
             if isinstance(spec, Mapping) and spec.get("member_id") == member_id]
    if len(fixed) > 1:
        raise RecoveryHostError("local_recovery_host_ambiguous")
    if fixed:
        spec = fixed[0]
        declared_project = spec.get("project_id")
        if declared_project is not None and declared_project != project_id:
            raise RecoveryHostError("local_recovery_identity_mismatch")
        health = spec.get("health_file")
        if not isinstance(health, str) or not health:
            raise RecoveryHostError("local_recovery_host_unconfigured")
        configured_root = config.get("project_root")
        root = Path(configured_root) if isinstance(configured_root, str) and configured_root else None
        entry = entry_from_argv(spec.get("argv"), root)
        if entry is None:
            raise RecoveryHostError("local_recovery_entry_unverified")
        return RecoveryHost("fixed", None, Path(health), entry)

    if not isinstance(original_runtime, str) or not original_runtime:
        raise RecoveryHostError("local_recovery_runner_unverified")
    if original_runtime not in _DYNAMIC:
        raise RecoveryHostError("local_recovery_runner_unsupported")
    if not isinstance(current_runtime, str) or not current_runtime:
        raise RecoveryHostError("local_recovery_runner_unverified")
    if current_runtime != original_runtime:
        # Never use the new binding to prove an old process stopped.
        raise RecoveryHostError("local_recovery_binding_changed")
    if control_kind != "managed_cli":
        raise RecoveryHostError("local_recovery_binding_changed")

    recipe_key, directory, module = _DYNAMIC[original_runtime]
    recipe = config.get(recipe_key)
    if original_runtime in ("kimi-code", "codex", "dsh"):
        if not isinstance(recipe, Mapping) or recipe.get("enabled") is not True:
            raise RecoveryHostError("local_recovery_host_unconfigured")
    elif not isinstance(recipe, Mapping) or not recipe:
        raise RecoveryHostError("local_recovery_host_unconfigured")

    state_dir = config.get("state_dir")
    if not isinstance(state_dir, str) or not state_dir:
        raise RecoveryHostError("local_recovery_host_unconfigured")
    configured_root = config.get("project_root")
    root = Path(configured_root) if isinstance(configured_root, str) and configured_root else ROOT
    entry = _module_entry(module, root)
    if entry is None:
        raise RecoveryHostError("local_recovery_entry_unverified")
    health = (Path(state_dir) / directory / _sanitize(project_id)
              / _sanitize(member_id) / "manager-health.json")
    return RecoveryHost("dynamic-" + original_runtime, original_runtime, health, entry)
