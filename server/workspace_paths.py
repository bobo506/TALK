"""Trusted workspace paths; encoded components are limited to 120 ASCII bytes.

All methods only inspect paths. Callers must recheck at each filesystem side effect;
these checks alone do not prevent concurrent filesystem replacement.
"""
from __future__ import annotations

import base64
import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath


class WorkspacePathError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _component(value: str, prefix: str) -> str:
    if not isinstance(value, str) or not value:
        raise WorkspacePathError("invalid_id")
    try:
        name = prefix + base64.b32encode(value.encode("utf-8")).decode("ascii").rstrip("=").lower()
    except UnicodeError as exc:
        raise WorkspacePathError("invalid_id") from exc
    if len(name) > 120:
        raise WorkspacePathError("component_too_long")
    return name


def project_component(project_id: str) -> str:
    return _component(project_id, "p-")


def member_component(member_id: str) -> str:
    return _component(member_id, "m-")


def _checked(path: Path) -> Path:
    path = Path(os.path.abspath(os.path.expanduser(str(path))))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise WorkspacePathError("path_unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise WorkspacePathError("link_refused")
    try:
        return path.resolve()
    except (OSError, RuntimeError) as exc:
        raise WorkspacePathError("path_unavailable") from exc


def is_within(path: Path, root: Path) -> bool:
    target, base = _checked(path), _checked(root)
    a = tuple(os.path.normcase(x) for x in target.parts)
    b = tuple(os.path.normcase(x) for x in base.parts)
    return a[:len(b)] == b


def _child(root: Path, *parts: str) -> Path:
    root = _checked(root)
    target = _checked(root.joinpath(*parts))
    if not is_within(target, root):
        raise WorkspacePathError("path_escape")
    return target


def deployment_shape(data_root: Path) -> str:
    root = _checked(data_root)
    try:
        root_info = root.stat()
    except OSError as exc:
        raise WorkspacePathError("shape_unknown") from exc
    if not stat.S_ISDIR(root_info.st_mode):
        raise WorkspacePathError("shape_unknown")
    marker = root / ".git"
    try:
        info = marker.lstat()
    except FileNotFoundError:
        return "non_git"
    except OSError as exc:
        raise WorkspacePathError("shape_unknown") from exc
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise WorkspacePathError("shape_unknown")
    if stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode):
        return "git"
    raise WorkspacePathError("shape_unknown")


def workspace_root(data_root: Path, project_id: str) -> Path:
    return _child(Path(data_root), "workspaces", project_component(project_id))


def role_dir(data_root: Path, project_id: str, member_id: str) -> Path:
    return _child(workspace_root(data_root, project_id), "roles", member_component(member_id))


def profiles_dir(data_root: Path, project_id: str, member_id: str) -> Path:
    return _child(role_dir(data_root, project_id, member_id), "profiles")


def key_path(data_root: Path, project_id: str, member_id: str, *, git_key_root: Path | None = None) -> Path:
    if deployment_shape(data_root) == "git":
        root = Path.home() / ".talk" / "keys" if git_key_root is None else Path(git_key_root)
        if is_within(root, data_root):
            raise WorkspacePathError("key_root_inside_repo")
        return _child(root, member_component(member_id) + ".key")
    return _child(Path(data_root), "keys", project_component(project_id), member_component(member_id) + ".key")


def resolve_profile_reference(data_root: Path, project_id: str, member_id: str, layout: str, reference: str) -> Path:
    from cli.profiles import PROFILE_FILES
    prefix = "workspace-v1:"
    if layout != "workspace-v1" or not isinstance(reference, str) or not reference.startswith(prefix):
        raise WorkspacePathError("layout_mismatch")
    rel = reference[len(prefix):]
    posix, windows = PurePosixPath(rel), PureWindowsPath(rel)
    if windows.is_absolute() or windows.drive or posix.is_absolute() or "\\" in rel or any(p in ("", ".", "..") for p in rel.split("/")):
        raise WorkspacePathError("invalid_reference")
    parts = rel.split("/")
    if len(parts) != 4 or parts[:3] != ["roles", member_component(member_id), "profiles"] or parts[3] not in PROFILE_FILES.values():
        raise WorkspacePathError("invalid_reference")
    return _child(workspace_root(data_root, project_id), *parts)
