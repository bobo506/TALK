"""Read-only workspace identity and marker diagnostics.

Root aliases are followed only for identity. Marker reads reject links using the
existing workspace path guard. Results are observations, not authorization for
later file operations; concurrent replacements require a fresh secure check.
"""
from __future__ import annotations

import errno
import os
import socket
import stat
from datetime import datetime, timezone
from pathlib import Path

import yaml

from server.workspace_paths import WorkspacePathError, _checked

_MARKER_LIMIT = 64 * 1024
_MESSAGES = {
    "workspace_root_missing": "工作区目录不存在。",
    "workspace_root_inaccessible": "工作区目录无法访问或状态无法确定。",
    "workspace_root_invalid": "工作区根路径无效或不是目录。",
    "workspace_root_unconfigured": "未配置工作区根目录。",
    "workspace_identity_unknown": "无法取得可靠的工作区物理身份。",
}


def _issue(code):
    return {"code": code, "severity": "warning", "message": _MESSAGES[code]}


def _identity(info):
    # Python's Windows stat provides volume serial and file index when available.
    # Zero file IDs are not reliable (e.g. some network filesystems).
    if not isinstance(info.st_dev, int) or not isinstance(info.st_ino, int) or info.st_ino == 0:
        return None
    return {"platform": os.name, "machine": socket.gethostname(),
            "volume_id": info.st_dev, "file_id": info.st_ino,
            "collected_at": datetime.now(timezone.utc).isoformat()}


def _identity_key(identity):
    if not isinstance(identity, dict):
        return None
    values = tuple(identity.get(k) for k in ("platform", "machine", "volume_id", "file_id"))
    if (not all(isinstance(v, str) and v for v in values[:2])
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in values[2:])
            or values[3] == 0):
        return None
    return values


def _marker(root):
    result = {"exists": None, "project_id": None, "parseable": False}
    target = root / ".talk" / "project.yaml"
    try:
        # Refuse any link or reparse point, including the root, before reading.
        _checked(target)
        info = target.lstat()
        result["exists"] = True
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MARKER_LIMIT:
            return result
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or
                    (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
                return result
            raw = stream.read(_MARKER_LIMIT + 1)
        if len(raw) > _MARKER_LIMIT:
            return result
        # Parse only scalar project_id; reject duplicate IDs and YAML object tags.
        node = yaml.compose(raw.decode("utf-8"), Loader=yaml.SafeLoader)
        if not isinstance(node, yaml.MappingNode):
            return result
        ids = [v for k, v in node.value if isinstance(k, yaml.ScalarNode)
               and k.tag == "tag:yaml.org,2002:str" and k.value == "project_id"]
        if len(ids) != 1 or not isinstance(ids[0], yaml.ScalarNode) or ids[0].tag != "tag:yaml.org,2002:str" or not ids[0].value:
            return result
        # SafeLoader rejects unsupported tags anywhere, without constructing objects.
        yaml.safe_load(raw.decode("utf-8"))
        result.update(project_id=ids[0].value, parseable=True)
    except FileNotFoundError:
        result["exists"] = False
    except (OSError, WorkspacePathError, ValueError, UnicodeError, yaml.YAMLError, RecursionError):
        pass
    return result


def inspect_root(root):
    """Return root status, optional physical identity, marker and safe issues."""
    result = {"status": "unknown", "identity": None,
              "marker": {"exists": None, "project_id": None, "parseable": False}, "issues": []}
    if root is None or root == "":
        status, code = "unconfigured", "workspace_root_unconfigured"
    else:
        try:
            path = Path(os.fspath(root))
            if not path.is_absolute() or "\x00" in str(path):
                raise ValueError("invalid root")
            info = path.stat()
            if not stat.S_ISDIR(info.st_mode):
                status, code = "invalid", "workspace_root_invalid"
            else:
                result["status"] = "ok"
                try:
                    result["identity"] = _identity(info)
                except (OSError, ValueError):
                    pass
                if _identity_key(result["identity"]) is None:
                    result["identity"] = None
                    result["issues"].append(_issue("workspace_identity_unknown"))
                result["marker"] = _marker(path)
                return result
        except (TypeError, ValueError, OverflowError):
            status, code = "invalid", "workspace_root_invalid"
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                status, code = "missing", "workspace_root_missing"
            elif exc.errno in (errno.EINVAL, errno.ENOTDIR, errno.ENAMETOOLONG):
                status, code = "invalid", "workspace_root_invalid"
            else:
                status, code = "inaccessible", "workspace_root_inaccessible"
    result["status"] = status
    result["issues"].append(_issue(code))
    return result


def detect_duplicates(roots):
    """Return duplicate project ID groups and projects with unknown identity."""
    groups = {}
    unknown = []
    for project_id, root in roots:
        key = _identity_key(inspect_root(root)["identity"])
        if key is None:
            if project_id not in unknown:
                unknown.append(project_id)
        else:
            group = groups.setdefault(key, [])
            if project_id not in group:
                group.append(project_id)
    return {"duplicates": [{"code": "workspace_duplicate", "project_ids": ids}
                           for ids in groups.values() if len(ids) > 1],
            "unknown": unknown}


def evaluate_move(old, candidate_root):
    """Return candidate evidence; marker equality alone never proves identity."""
    candidate = inspect_root(candidate_root)
    old_marker = old.get("marker") or {}
    new_marker = candidate["marker"]
    old_id = old_marker.get("project_id") if old_marker.get("parseable") else None
    new_id = new_marker.get("project_id") if new_marker.get("parseable") else None
    old_key = _identity_key(old.get("identity"))
    new_key = _identity_key(candidate["identity"])
    if old_id and new_id and old_id != new_id:
        code = "workspace_marker_conflict"
    elif old_key is not None and old_key == new_key:
        code = "workspace_move_candidate"
    elif old_key is not None and old_id and new_id == old_id:
        code = "marker_only"
    else:
        code = "workspace_identity_unverified"
    return {"code": code, "candidate": candidate}
