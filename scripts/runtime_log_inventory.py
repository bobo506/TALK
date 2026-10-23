#!/usr/bin/env python3
"""Read-only metadata inventory; never a deletion plan or a liveness probe.

No log/manifest bodies, private configuration, database or process table are read.
The root is explicit. Linked/reparse directories are rejected or skipped, and
bounded/inaccessible/changing trees are reported as partial observations.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENT = re.compile(r"^events-[0-9]+\.jsonl$")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
KINDS = ("events", "manifest", "rotation", "retention", "other")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _mtime_text(modified_ns):
    # Windows CRT fromtimestamp rejects valid pre-1970 NTFS timestamps.
    # Integer UTC arithmetic also avoids float rounding near date boundaries.
    try:
        return (EPOCH + timedelta(microseconds=modified_ns // 1000)).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _linked(st):
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & 0x400
    )


def _chain(path):
    """Check every ancestor, without resolving through a link first."""
    result = []
    for part in reversed((path, *path.parents)):
        st = part.lstat()
        if _linked(st) or not stat.S_ISDIR(st.st_mode):
            raise ValueError("unsafe_directory")
        result.append((str(part), st.st_dev, st.st_ino, st.st_mode))
    return tuple(result)


def _kind(name, depth):
    if depth != 4:
        return "other"
    if EVENT.fullmatch(name):
        return "events"
    return {"manifest.json": "manifest", "rotation.jsonl": "rotation",
            "retention.jsonl": "retention"}.get(name, "other")


def inventory(root, *, retention_days=30.0, max_total_bytes=1024**3,
              max_entries=20000, max_seconds=5.0, preview_limit=20, now=None):
    """Stat one root. Limits/policy are proposals, never writer configuration.

    File mtime measures age only. Even the latest segment is not a proven active
    file, and older segments are not proven closed. No bytes are 'reclaimable'.
    Directory identity checks detect observed replacements; this is not an
    atomic filesystem snapshot or a security boundary against hostile races.
    """
    if (not isinstance(retention_days, (int, float)) or isinstance(retention_days, bool)
            or not math.isfinite(retention_days) or not 0 < retention_days <= 36500):
        raise ValueError("invalid_retention_days")
    for value, upper in ((max_total_bytes, 2**63-1), (max_entries, 100000),
                         (preview_limit, 100)):
        if type(value) is not int or not 1 <= value <= upper:
            raise ValueError("invalid_limit")
    if (not isinstance(max_seconds, (int, float)) or isinstance(max_seconds, bool)
            or not math.isfinite(max_seconds) or not 0 < max_seconds <= 60):
        raise ValueError("invalid_seconds")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone_required")
    now_ns = int(now.timestamp() * 10**9)
    cutoff_ns = now_ns - int(retention_days * 86400 * 10**9)
    root_text = os.fspath(root)
    if not isinstance(root_text, str) or not root_text.strip() or "\x00" in root_text:
        raise ValueError("invalid_root")
    root = Path(os.path.abspath(root_text))
    counts = {kind: {"files": 0, "bytes": 0} for kind in KINDS}
    reasons = set()
    runs = {}
    entries = 0
    links = 0
    future = 0
    started = time.monotonic()
    status = "complete"
    try:
        root_chain = _chain(root)
    except FileNotFoundError:
        status = "missing"
        reasons.add("root_missing")
        root_chain = None
    except (OSError, ValueError):
        status = "unavailable"
        reasons.add("root_unavailable_or_unsafe")
        root_chain = None

    def expired():
        if entries >= max_entries:
            reasons.add("entry_limit")
            return True
        if time.monotonic() - started >= max_seconds:
            reasons.add("time_limit")
            return True
        return False

    stack = [(root, root_chain)] if root_chain else []
    # Full chains are retained for a final metadata recheck. Memory is bounded
    # by max_entries and the fixed directory depth (root/member/instance/run).
    directories = []
    events = []
    while stack and not expired():
        directory, expected = stack.pop()
        try:
            if _chain(directory) != expected:
                reasons.add("directory_changed")
                continue
            directories.append((directory, expected))
            with os.scandir(directory) as scan:
                for entry in scan:
                    if expired():
                        break
                    entries += 1
                    path = Path(entry.path)
                    rel = path.relative_to(root)
                    st = path.lstat()
                    if _linked(st):
                        links += 1
                        reasons.add("link_or_reparse_skipped")
                        continue
                    if stat.S_ISDIR(st.st_mode):
                        if len(rel.parts) > 3 or not TOKEN.fullmatch(path.name):
                            reasons.add("unexpected_directory_skipped")
                        else:
                            chain = _chain(path)
                            if chain[:-1] != expected:
                                reasons.add("directory_changed")
                            else:
                                stack.append((path, chain))
                        continue
                    if not stat.S_ISREG(st.st_mode):
                        reasons.add("special_file_skipped")
                        continue
                    kind = _kind(path.name, len(rel.parts))
                    counts[kind]["files"] += 1
                    counts[kind]["bytes"] += st.st_size
                    if st.st_mtime_ns > now_ns:
                        future += 1
                    if len(rel.parts) == 4:
                        run = rel.parent.as_posix()
                        data = runs.setdefault(run, {"bytes": 0, "latest_index": -1})
                        data["bytes"] += st.st_size
                        if kind == "events":
                            index = int(path.stem[7:])
                            data["latest_index"] = max(data["latest_index"], index)
                            events.append((rel.as_posix(), run, index, st.st_size,
                                           st.st_mtime_ns))
        except OSError:
            reasons.add("entry_unavailable_or_changed")
        except ValueError:
            reasons.add("unsafe_directory")
    for path, expected in directories:
        if expired():
            break
        try:
            if _chain(path) != expected:
                reasons.add("directory_changed")
        except (OSError, ValueError):
            reasons.add("directory_changed")

    flagged = []
    latest_bytes = 0
    mtime_unavailable = 0
    for path, run, index, size, modified in events:
        if index == runs[run]["latest_index"]:
            latest_bytes += size
        elif modified < cutoff_ns:
            modified_at = _mtime_text(modified)
            if modified_at is None:
                mtime_unavailable += 1
                reasons.add("mtime_format_unavailable")
            flagged.append({"relative_path": path, "bytes": size,
                            "modified_ns": modified, "modified_at": modified_at})
    flagged.sort(key=lambda item: (item["modified_ns"], item["relative_path"]))
    total = sum(value["bytes"] for value in counts.values())
    if status == "complete" and reasons:
        status = "partial"
    measured = root_chain is not None
    return {
        "schema": "talk-runtime-log-inventory-1",
        "observed_at": now.astimezone(timezone.utc).isoformat(),
        "mode": "metadata_only_no_deletion",
        "scan": {"status": status, "reasons": sorted(reasons),
                 "entries": entries, "max_entries": max_entries,
                 "max_seconds": max_seconds, "links_skipped": links,
                 "future_mtime_files": future, "atomic_snapshot": False},
        "observed": {"bytes": total if measured else None, "by_kind": counts,
                     "runs": len(runs) if measured else None},
        "proposal_only": {"retention_days": retention_days,
                          "max_total_bytes": max_total_bytes,
                          "over_capacity_bytes": max(0, total-max_total_bytes)
                          if measured else None,
                          "capacity_assessment": "partial_observation"
                          if status == "partial" else status},
        "age_review": {
            "closed_run_verified": False, "eligible_for_deletion_bytes": 0,
            "mtime_unavailable_files": mtime_unavailable,
            "latest_segment_bytes_excluded": latest_bytes,
            "older_segment_files": len(flagged),
            "older_segment_bytes": sum(item["bytes"] for item in flagged),
            "preview": flagged[:preview_limit],
            "preview_truncated": len(flagged) > preview_limit,
            "requires": ["closed_run_proof", "complete_rescan",
                         "unchanged_file_identity", "human_approval"],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", required=True,
                        help="Non-empty explicit local diagnostics root; '.' is allowed")
    parser.add_argument("--retention-days", type=float, default=30.0)
    parser.add_argument("--max-total-bytes", type=int, default=1024**3)
    parser.add_argument("--max-entries", type=int, default=20000)
    parser.add_argument("--max-seconds", type=float, default=5.0)
    parser.add_argument("--preview-limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        result = inventory(args.log_dir, retention_days=args.retention_days,
                           max_total_bytes=args.max_total_bytes,
                           max_entries=args.max_entries, max_seconds=args.max_seconds,
                           preview_limit=args.preview_limit)
    except (ValueError, OSError, OverflowError):
        parser.error("invalid inventory arguments")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["scan"]["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
