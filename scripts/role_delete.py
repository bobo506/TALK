"""Bounded cleanup for the runtime's own stopped project role; no PID adoption.

Only canonical per-role roots and explicitly registered key files are eligible.
Windows parent handles pin every ancestor; deletion addresses the checked HANDLE.
Shared native login/model directories and diagnostic logs are never targets.
"""
from __future__ import annotations
import hashlib
import json
import os
import stat
import time
from pathlib import Path

from bridges.runtime_log_retention import NativeFile, pinned, identity, _link
from scripts import role_provision as provision
from scripts import role_service_host as host

STEPS = ("manager", "profiles", "credentials", "private_state", "startup_config")
MAX_OPERATIONS = 4096


class CleanupError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Files:
    def __init__(self, deadline):
        self.deadline, self.count, self.deleted = deadline, 0, 0

    def budget(self):
        self.count += 1
        if self.count > MAX_OPERATIONS or time.monotonic() >= self.deadline:
            raise CleanupError("cleanup_budget")

    def read(self, path, limit=1024*1024):
        self.budget()
        with pinned(path.parent), NativeFile(path) as handle:
            return handle.read(limit)

    def remove(self, path, *, tree=False, digest=None, verify=None, skip=frozenset()):
        # lexists catches dangling symlinks too. Missing resources are idempotent.
        if not os.path.lexists(path):
            return
        self.budget()
        with pinned(path.parent):
            info = path.lstat()
            if _link(info) or (not stat.S_ISDIR(info.st_mode) and info.st_nlink != 1):
                raise CleanupError("unsafe_resource")
            if stat.S_ISDIR(info.st_mode):
                if not tree:
                    raise CleanupError("unsafe_resource")
                with NativeFile(path, directory=True):
                    for child in path.iterdir():
                        self.budget()
                        if child.name not in skip:
                            self.remove(child, tree=True)
                if skip and any(path.iterdir()):
                    return  # Permanent empty OS lock guards contain no role configuration.
                with NativeFile(path, directory=True, delete=True) as handle:
                    handle.expire(identity(os.fstat(handle.fd)))
                self.deleted += 1
            elif stat.S_ISREG(info.st_mode):
                with NativeFile(path, delete=True) as handle:
                    if digest is not None and hashlib.sha256(handle.read(16384).strip()).hexdigest() != digest:
                        raise CleanupError("credential_mismatch")
                    if verify is not None and not verify(handle.read(1024*1024)):
                        raise CleanupError("unsafe_resource")
                    handle.expire(identity(os.fstat(handle.fd)))
                self.deleted += 1
            else:
                raise CleanupError("unsafe_resource")


def _key_paths(config, member):
    root = Path(config["key_root"])
    paths = {provision.key_file_path(root, member)}
    mapped = (config.get("workbuddy") or {}).get("key_files", {}).get(member)
    if mapped:
        paths.add(Path(mapped))
    for spec in config.get("hosts", []):
        if spec["member_id"] != member:
            continue
        argv = spec["argv"]
        for i, arg in enumerate(argv):
            if arg == "--role-key-file" and i + 1 < len(argv):
                paths.add(Path(argv[i+1]))
            elif arg.startswith("--role-key-file="):
                paths.add(Path(arg.split("=",1)[1]))
    for path in paths:
        if not path.is_absolute() or path.parent.resolve() != root.resolve():
            raise CleanupError("unsafe_resource")
        provision.assert_inside_root(root, path.name)
    # The same file can be referenced by another explicitly configured host.
    for spec in config.get("hosts", []):
        arguments = {argument.split("=",1)[-1].replace("\\", "/").casefold() for argument in spec["argv"]}
        if spec["member_id"] != member and any(str(p).replace("\\", "/").casefold() in arguments for p in paths):
            raise CleanupError("unsafe_resource")
    for other, value in (config.get("workbuddy") or {}).get("key_files", {}).items():
        if other != member and Path(value).resolve() in {p.resolve() for p in paths}:
            raise CleanupError("unsafe_resource")
    return paths


def _drain(runtime, member, files):
    owned = runtime.hosts.get(member)
    specs = [s for s in runtime.config.get("hosts", []) if s["member_id"] == member]
    if owned:
        specs.append(owned["spec"])
    own_paths = {str(Path(s[k]).absolute()).casefold() for s in specs for k in ("health_file", "drain_file")}
    for other in runtime.config.get("hosts", []):
        if other["member_id"] != member and any(str(Path(other[k]).absolute()).casefold() in own_paths for k in ("health_file", "drain_file")):
            raise CleanupError("unsafe_resource")
    from scripts.role_service_recovery import recorded_process_state
    wb = Path(runtime.config["state_dir"])/"workbuddy-native"/host._sanitize_token(runtime.project)/host._sanitize_token(member)
    health_paths = {Path(s["health_file"]) for s in specs} | {wb/"manager-health.json"}
    owned_health = Path(owned["spec"]["health_file"]) if owned else None

    def verify_health():
        for path in health_paths:
            if not os.path.lexists(path):
                if path == owned_health:
                    raise CleanupError("manager_not_stopped")
                continue
            try:
                facts = json.loads(files.read(path))
                if not isinstance(facts,dict) or facts.get("owned_launches") != []:
                    raise CleanupError("manager_not_stopped")
            except (OSError,ValueError):
                raise CleanupError("manager_not_stopped") from None
            # Exited or absent managers do not prove their native children exited.
            # Every health receipt must first have an explicitly empty launch list.
            if path != owned_health and recorded_process_state(facts.get("pid"),facts.get("seen_at")) not in (
                    "absent", "exited", "previous_boot", "pid_reused"):
                raise CleanupError("manager_not_stopped")

    verify_health()
    if owned:
        spec = owned["spec"]
        if owned["process"].poll() is None:
            # The runtime retains the original Popen. A marker only requests normal exit.
            marker = Path(spec["drain_file"])
            if marker.exists() and not owned.get("delete_drain_written"):
                raise CleanupError("manager_not_stopped")
            if not owned.get("delete_drain_written"):
                with pinned(marker.parent):
                    host._publish_private_bytes(marker, b"talk-runtime-stop\n")
                owned["delete_drain_written"] = True
            try:
                owned["process"].wait(timeout=25)
            except Exception:
                raise CleanupError("manager_not_stopped") from None
        verify_health()
    for spec in specs:
        # Retain health evidence if removing a locked drain marker fails, for retry.
        for key in ("drain_file", "health_file"):
            path = Path(spec[key])
            root = Path(runtime.config["state_dir"])
            provision.assert_inside_root(root, path.relative_to(root))
            # Only delete explicit leaf metadata, not its potentially shared parent.
            if path.is_dir():
                raise CleanupError("unsafe_resource")
            files.remove(path)
    runtime.hosts.pop(member, None)
    runtime.statuses.pop(member, None)


def _records(runtime, member, files):
    """A stopped DB row is insufficient if a private native-child receipt is live."""
    from scripts.role_service_recovery import recorded_process_state
    directory = provision.assert_inside_root(Path(runtime.config["state_dir"]),
        Path("roles")/host._sanitize_token(runtime.project)/host._sanitize_token(member))
    controls = []
    if directory.exists():
        for path in directory.glob("*.json"):
            facts = json.loads(files.read(path))
            if facts.get("project_id") != runtime.project or facts.get("member_id") != member:
                raise CleanupError("unsafe_resource")
            if recorded_process_state(facts.get("pid"),facts.get("process_started_at")) not in (
                    "absent", "exited", "previous_boot", "pid_reused"):
                raise CleanupError("manager_not_stopped")
            launch = facts.get("launch_id")
            if not isinstance(launch,str) or host._sanitize_token(launch) != launch:
                raise CleanupError("unsafe_resource")
            controls.append(launch)
    return controls


def _config(runtime, member, files):
    path = runtime.config_path
    if path is None:
        raise CleanupError("local_runtime_required")
    lock = provision.lock_path_for(path)
    held = provision.acquire_lock(lock)
    try:
        raw = files.read(path)
        current = json.loads(raw)
        if current != runtime.config:
            raise CleanupError("runtime_config_changed")
        updated = dict(current)
        updated["hosts"] = [s for s in current.get("hosts", []) if s["member_id"] != member]
        if "workbuddy" in current:
            recipe = dict(current["workbuddy"])
            recipe["key_files"] = {k:v for k,v in recipe.get("key_files", {}).items() if k != member}
            updated["workbuddy"] = recipe
        if updated != current:
            with pinned(path.parent):
                # Recheck bytes under the same config OS lock, then private atomic replace.
                if files.read(path) != raw:
                    raise CleanupError("runtime_config_changed")
                payload = (json.dumps(updated, ensure_ascii=False, indent=2)+"\n").encode()
                temporary = host._windows_publish_temp_file(path, payload)
                try:
                    if files.read(temporary) != payload:
                        raise CleanupError("runtime_config_changed")
                    # The private temporary file is verified before the only replacement.
                    # Never delete the shared runtime config on a post-publication failure.
                    os.replace(temporary, path)
                    runtime.config = updated
                finally:
                    files.remove(temporary)
    finally:
        provision.release_lock(lock, held)


def cleanup(runtime, member, receipt):
    steps = {step:"pending" for step in STEPS}
    files = Files(time.monotonic()+120)
    handles = []
    step = "manager"
    try:
        if os.name != "nt":
            raise CleanupError("unsafe_resource")
        if not runtime.config_path:
            raise CleanupError("local_runtime_required")
        for name in ("project_root", "state_dir", "key_root"):
            if Path(runtime.config[name]).drive.startswith("\\\\"):
                raise CleanupError("unsafe_resource")
        _drain(runtime, member, files)
        controls = _records(runtime, member, files)
        steps[step] = "complete"
        root, keys = runtime.project_root, Path(runtime.config["key_root"])
        # Same locks as create/recover; no provision can recreate profiles during cleanup.
        handles = provision.acquire_provision_locks(root, keys, member)
        step = "profiles"
        directory = provision.profile_lock_path_for(root, member).parent
        files.remove(directory, tree=True, skip={".provision.lock", ".provision.lock.guard"})
        steps[step] = "complete"
        step = "credentials"
        if receipt["identity_disabled"]:
            for path in _key_paths(runtime.config, member):
                files.remove(path, digest=receipt["credential_digest"])
            metadata = provision.credential_metadata_path(keys, member)
            files.remove(metadata, verify=lambda data:json.loads(data).get("member_id")==member)
            steps[step] = "complete"
        else:
            steps[step] = "preserved"
        step = "private_state"
        state = Path(runtime.config["state_dir"])
        project_token, member_token = host._sanitize_token(runtime.project), host._sanitize_token(member)
        for launch in controls:
            files.remove(provision.assert_inside_root(state, Path("control")/(launch+".ctl")))
        for category in ("roles", "native", "workbuddy-native"):
            path = provision.assert_inside_root(state, Path(category)/project_token/member_token)
            files.remove(path, tree=True)
        steps[step] = "complete"
        step = "startup_config"
        _config(runtime, member, files)
        steps[step] = "complete"
        return {"outcome":"complete", "steps":steps, "error_code":None}
    except Exception as exc:
        code = exc.code if isinstance(exc, CleanupError) else "cleanup_busy" if isinstance(exc, provision.ProvisionError) and "lock" in exc.code else "cleanup_failed"
        if code == "cleanup_budget" and files.deleted > 0 and step != "manager":
            # Tangible progress yields the lease; the next runtime tick resumes
            # the same tombstone. Never turn a lock/ownership error into a retry loop.
            steps[step] = "pending"
            return {"outcome":"pending", "steps":steps, "error_code":None}
        steps[step] = "failed"
        return {"outcome":"failed", "steps":steps, "error_code":code}
    finally:
        provision.release_provision_locks(handles)
