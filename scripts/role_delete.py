"""Bounded cleanup for the runtime's own stopped project role; no PID adoption.

Only canonical per-role roots and explicitly registered key files are eligible.
Windows parent handles pin every ancestor; deletion addresses the checked HANDLE.
Shared native login/model directories and diagnostic logs are never targets.
A completed deletion also reclaims the role's own lock guards and empty shells
(an occupied guard keeps its residue; that never changes the result).
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


def _remove_native_junction(path, expected):
    """Delete only the checked junction entry; never open its target or reparse data.

    Caller pins the ordinary native-home ancestors. OPEN_REPARSE_POINT plus a
    no-write/no-delete-share handle prevents a path swap after verification.
    Other tags, non-junction replacements and changed identities fail closed.
    """
    import ctypes
    import msvcrt
    from ctypes import wintypes as w

    tag=0xA0000003  # IO_REPARSE_TAG_MOUNT_POINT: directory junction
    if (not _link(expected) or not stat.S_ISDIR(expected.st_mode)
            or getattr(expected,"st_reparse_tag",None)!=tag or expected.st_nlink!=1):
        raise CleanupError("unsafe_resource")
    k=ctypes.WinDLL("kernel32",use_last_error=True)
    k.GetLongPathNameW.argtypes=[w.LPCWSTR,w.LPWSTR,w.DWORD]
    k.GetLongPathNameW.restype=w.DWORD
    path=Path(os.path.abspath(path))
    # Normalize only the ordinary, pinned parent: even exists() on the junction
    # would follow it to obtain target metadata. Dangling links use the same path.
    buffer=ctypes.create_unicode_buffer(32768)
    length=k.GetLongPathNameW(str(path.parent),buffer,len(buffer))
    if not length or length>=len(buffer):
        raise CleanupError("unsafe_resource")
    canonical=Path(buffer.value)/path.name
    k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
    k.CreateFileW.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
    handle=k.CreateFileW(str(canonical),0x10000|0x80,1,None,3,0x00200000|0x02000000,None)
    if handle==ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(),"junction_open_unavailable")
    fd=None
    try:
        class Attributes(ctypes.Structure):
            _fields_=[("attributes",w.DWORD),("tag",w.DWORD)]
        k.GetFileInformationByHandleEx.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD]
        k.GetFileInformationByHandleEx.restype=w.BOOL
        attributes=Attributes()
        if (not k.GetFileInformationByHandleEx(handle,9,ctypes.byref(attributes),ctypes.sizeof(attributes))
                or attributes.tag!=tag or not attributes.attributes&0x400 or not attributes.attributes&0x10):
            raise CleanupError("unsafe_resource")
        k.GetFinalPathNameByHandleW.argtypes=[w.HANDLE,w.LPWSTR,w.DWORD,w.DWORD]
        k.GetFinalPathNameByHandleW.restype=w.DWORD
        length=k.GetFinalPathNameByHandleW(handle,buffer,len(buffer),0)
        actual=buffer.value
        if actual.startswith("\\\\?\\"):actual=actual[4:]
        if not length or length>=len(buffer) or os.path.normcase(actual)!=os.path.normcase(str(canonical)):
            raise CleanupError("unsafe_resource")
        fd=msvcrt.open_osfhandle(handle,os.O_BINARY|os.O_RDONLY)
        handle=None
        if identity(os.fstat(fd))!=identity(expected):
            raise CleanupError("unsafe_resource")
        class Disposition(ctypes.Structure):
            _fields_=[("delete",ctypes.c_ubyte)]
        k.SetFileInformationByHandle.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD]
        k.SetFileInformationByHandle.restype=w.BOOL
        disposition=Disposition(1)
        if not k.SetFileInformationByHandle(msvcrt.get_osfhandle(fd),4,ctypes.byref(disposition),ctypes.sizeof(disposition)):
            raise OSError(ctypes.get_last_error(),"junction_delete_unavailable")
    finally:
        if fd is not None:os.close(fd)
        if handle is not None:k.CloseHandle(handle)


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

    def remove(self, path, *, tree=False, digest=None, verify=None, skip=frozenset(), native_root=None):
        # lexists catches dangling symlinks too. Missing resources are idempotent.
        if not os.path.lexists(path):
            return
        self.budget()
        with pinned(path.parent):
            info = path.lstat()
            if _link(info):
                # Only descendants of the canonical, ordinary native-home root
                # may unlink a junction. Profiles/credentials/control stay strict.
                if (native_root is None or not tree or path==native_root
                        or not path.is_relative_to(native_root)):
                    raise CleanupError("unsafe_resource")
                _remove_native_junction(path,info)
                self.deleted += 1
                return
            if not stat.S_ISDIR(info.st_mode) and info.st_nlink != 1:
                raise CleanupError("unsafe_resource")
            if stat.S_ISDIR(info.st_mode):
                if not tree:
                    raise CleanupError("unsafe_resource")
                with NativeFile(path, directory=True):
                    for child in path.iterdir():
                        self.budget()
                        if child.name not in skip:
                            self.remove(child, tree=True, native_root=native_root)
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


def _drain(runtime, member, files, workspace_root=None):
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
    if workspace_root is not None:
        health_paths |= {workspace_root / "state" / "manager" / runner / "manager-health.json"
                         for runner in ("codex", "kimi", "dsh", "workbuddy")}
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
            if workspace_root is not None and path.is_relative_to(workspace_root):
                relative = path.relative_to(workspace_root)
                if (len(relative.parts) != 4 or relative.parts[:2] != ("state", "manager")
                        or relative.parts[2] not in ("codex", "kimi", "dsh", "workbuddy")
                        or relative.parts[3] != ("drain.request" if key == "drain_file" else "manager-health.json")):
                    raise CleanupError("unsafe_resource")
                provision.assert_inside_root(workspace_root, relative)
            else:
                provision.assert_inside_root(root, path.relative_to(root))
            # Only delete explicit leaf metadata, not its potentially shared parent.
            if path.is_dir():
                raise CleanupError("unsafe_resource")
            files.remove(path)
    runtime.hosts.pop(member, None)
    runtime.statuses.pop(member, None)


def _records(runtime, member, files, workspace_root=None):
    """A stopped DB row is insufficient if a private native-child receipt is live."""
    from scripts.role_service_recovery import recorded_process_state
    directory = provision.assert_inside_root(Path(runtime.config["state_dir"]),
        Path("roles")/host._sanitize_token(runtime.project)/host._sanitize_token(member))
    controls = []
    directories = [directory]
    if workspace_root is not None:
        directories.append(workspace_root / "state" / "records")
    for directory in directories:
        if not directory.exists():
            continue
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


def _sweep_guard(path):
    """Remove a deleted role's lock guard; leave it if anything still holds it.

    守卫文件在锁路径存活期间从不删除——它让字节锁的对象身份保持稳定，创建/恢复
    才不会被“删除后重建的另一个文件”绕过。角色删除完成即退役，其 member id 不再
    复用，守卫与空目录成为纯残留，可在锁释放后回收。Windows 上被打开/加锁的守卫
    无法删除（共享冲突），残留由持有者保留；本函数从不因此报错。
    """
    try:
        info = os.lstat(path)
    except OSError:
        return
    if not stat.S_ISREG(info.st_mode) or _link(info):
        return
    try:
        os.remove(path)
    except OSError:
        return


def _sweep_empty_dir(path):
    """Remove the deleted role's own empty shell; never recurse into content.

    Only an empty directory is removed (``os.rmdir``), so a non-empty
    ``native-home`` (native login state) and anything else inside stays. Link
    entries are never followed or removed.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return
    if not stat.S_ISDIR(info.st_mode) or _link(info):
        return
    try:
        os.rmdir(path)
    except OSError:
        return


def _sweep_shell(profile_dir, key_files, extra_dirs):
    """Best-effort shell cleanup after a completed deletion released its locks.

    Addresses only the enumerated guard files and the role's own empty
    directories: the profile shell, an empty ``native-home`` and (workspace-v1)
    the now empty role directory.  A still visible ``.lock`` means another
    operation generation is in flight, so its guard is left alone.  Failures are
    ignored by design; the deletion result and its receipts are decided by the
    steps, not by residue.
    """
    lock = Path(profile_dir) / provision.PROFILE_LOCK_FILENAME
    if not os.path.lexists(lock):
        _sweep_guard(provision.lock_guard_path_for(lock))
    for key_file in key_files:
        key_lock = provision.lock_path_for(key_file)
        if not os.path.lexists(key_lock):
            _sweep_guard(provision.lock_guard_path_for(key_lock))
    for directory in (profile_dir, *extra_dirs):
        _sweep_empty_dir(directory)


def cleanup(runtime, member, receipt, role=None):
    steps = {step:"pending" for step in STEPS}
    files = Files(time.monotonic()+120)
    handles = []
    profile_dir = None
    sweep_dirs = ()
    sweep_keys = ()
    step = "manager"
    try:
        if os.name != "nt":
            raise CleanupError("unsafe_resource")
        if not runtime.config_path:
            raise CleanupError("local_runtime_required")
        for name in ("project_root", "state_dir", "key_root"):
            if Path(runtime.config[name]).drive.startswith("\\\\"):
                raise CleanupError("unsafe_resource")
        workspace_root = None
        if role is not None and role.get("storage_layout") == "workspace-v1":
            from server.workspace_paths import key_path, role_dir
            from scripts.talk_runtime import ROOT
            if role.get("member_id") != member or role.get("project_id", runtime.project) != runtime.project:
                raise CleanupError("unsafe_resource")
            workspace_root = role_dir(ROOT, runtime.project, member)
            profile_lock = workspace_root / "profiles" / provision.PROFILE_LOCK_FILENAME
            key = key_path(ROOT, runtime.project, member, git_key_root=Path(runtime.config["key_root"]))
            # Match the workspace provisioners' profile-then-key ordering before
            # touching even manager evidence. Both locks are released in finally.
            for candidate in (profile_lock, provision.lock_path_for(key)):
                handles.append((candidate, provision.acquire_lock(candidate)))
        _drain(runtime, member, files, workspace_root)
        controls = _records(runtime, member, files, workspace_root)
        steps[step] = "complete"
        root, keys = runtime.project_root, Path(runtime.config["key_root"])
        # Same locks as create/recover; no provision can recreate profiles during cleanup.
        if workspace_root is None:
            handles = provision.acquire_provision_locks(root, keys, member)
        step = "profiles"
        profile_dir = (workspace_root / "profiles" if workspace_root is not None
                       else provision.profile_lock_path_for(root, member).parent)
        sweep_dirs = ((workspace_root / "native-home", workspace_root)
                      if workspace_root is not None else ())
        files.remove(profile_dir, tree=True, skip={".provision.lock", ".provision.lock.guard"})
        steps[step] = "complete"
        step = "credentials"
        if receipt["identity_disabled"]:
            credential_paths = ({key} if workspace_root is not None
                                else _key_paths(runtime.config, member))
            for path in credential_paths:
                files.remove(path, digest=receipt["credential_digest"])
            sweep_keys = tuple(credential_paths)
            metadata = provision.credential_metadata_path(key.parent if workspace_root is not None else keys, member)
            files.remove(metadata, verify=lambda data:json.loads(data).get("member_id")==member)
            steps[step] = "complete"
        else:
            steps[step] = "preserved"
        step = "private_state"
        state = Path(runtime.config["state_dir"])
        if workspace_root is not None:
            for name in ("sessions", "state", "logs"):
                files.remove(workspace_root / name, tree=True)
        project_token, member_token = host._sanitize_token(runtime.project), host._sanitize_token(member)
        for launch in controls:
            files.remove(provision.assert_inside_root(state, Path("control")/(launch+".ctl")))
        for category in ("roles", "native", "workbuddy-native", "codex-dynamic", "kimi-dynamic", "dsh-dynamic"):
            path = provision.assert_inside_root(state, Path(category)/project_token/member_token)
            files.remove(path, tree=True, native_root=path if category=="native" else None)
        # Dynamic manager directories are per member; after the member
        # directory is gone, only remove empty project/category parents. A shared
        # parent with another role or project is never removed.
        for category in ("codex-dynamic", "kimi-dynamic", "dsh-dynamic"):
            project_dir = provision.assert_inside_root(state, Path(category)/project_token)
            category_dir = provision.assert_inside_root(state, Path(category))
            for candidate in (project_dir, category_dir):
                try:
                    if candidate.is_dir() and not any(candidate.iterdir()):
                        candidate.rmdir()
                except OSError:
                    pass
        steps[step] = "complete"
        step = "startup_config"
        _config(runtime, member, files)
        steps[step] = "complete"
        result = {"outcome":"complete", "steps":steps, "error_code":None}
    except Exception as exc:
        code = exc.code if isinstance(exc, CleanupError) else "cleanup_busy" if isinstance(exc, provision.ProvisionError) and "lock" in exc.code else "cleanup_failed"
        if code == "cleanup_budget" and files.deleted > 0 and step != "manager":
            # Tangible progress yields the lease; the next runtime tick resumes
            # the same tombstone. Never turn a lock/ownership error into a retry loop.
            steps[step] = "pending"
            result = {"outcome":"pending", "steps":steps, "error_code":None}
        else:
            steps[step] = "failed"
            result = {"outcome":"failed", "steps":steps, "error_code":code}
    finally:
        provision.release_provision_locks(handles)
    # Only a completed deletion retires the member id, so only then can the
    # guard files and the now empty shells be reclaimed. Residue never changes
    # the result decided above.
    if result["outcome"] == "complete" and profile_dir is not None:
        try:
            _sweep_shell(profile_dir, sweep_keys, sweep_dirs)
        except Exception:
            pass
    return result
