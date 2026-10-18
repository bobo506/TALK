#!/usr/bin/env python3
"""Controlled local query entry for TALK runtime diagnostics.

This maintainer-only tool searches the controlled local diagnostics directory.
It never accepts a file path or resolves a log reference into one.  The default
output is a bounded summary (identity, stage, exception type/message preview,
budgets and integrity flags); sanitized stack frames are printed only when
``--detail`` is explicitly requested.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridges import runtime_diagnostics as runtime_diag


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query the controlled local TALK bridge runtime diagnostics.",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help=(
            "Controlled diagnostics root. Defaults to TALK_RUNTIME_LOG_DIR or "
            "<project>/logs/runtime."
        ),
    )
    parser.add_argument("--ref", default=None, help="Exact stable log_id reference")
    parser.add_argument(
        "--member",
        "--role",
        dest="member",
        default=None,
        help="Filter by member_id (role identity, e.g. agent:deepseek)",
    )
    parser.add_argument("--instance", default=None, help="Filter by instance_id")
    parser.add_argument("--task", default=None, help="Filter by task_id")
    parser.add_argument("--event", default=None, help="Filter by event name")
    parser.add_argument("--stage", default=None, help="Filter by stage name")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum matching records (1..200). Default: 20",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Print sanitized traceback frames and cause chain (default: summary only)",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def _resolve_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser()
    env_value = os.environ.get("TALK_RUNTIME_LOG_DIR")
    if env_value:
        return Path(env_value).expanduser()
    return runtime_diag.DEFAULT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _resolve_root(args.log_dir)
    try:
        result = runtime_diag.query_records(
            root,
            ref=args.ref,
            member_id=args.member,
            instance_id=args.instance,
            task_id=args.task,
            event=args.event,
            stage=args.stage,
            limit=args.limit,
        )
    except runtime_diag.DiagnosticsQueryError as exc:
        print(f"runtime diagnostics: {exc}", file=sys.stderr)
        return 2

    records = result["records"]
    if not records:
        print(
            "runtime diagnostics: no matching records"
            + (" (scan limit reached)" if result.get("truncated") else ""),
            file=sys.stderr,
        )
        return 1

    if args.json:
        if args.detail:
            payload = records
        else:
            payload = [runtime_diag.record_summary_dict(record) for record in records]
        print(
            json.dumps(
                {
                    "records": payload,
                    "scan": {
                        "scanned_files": result["scanned_files"],
                        "scanned_bytes": result["scanned_bytes"],
                        "malformed_lines": result["malformed_lines"],
                        "truncated": result["truncated"],
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        blocks = [
            (
                runtime_diag.format_record_detail(record)
                if args.detail
                else runtime_diag.format_record_summary(record)
            )
            for record in records
        ]
        print("\n\n".join(blocks))
    if result["truncated"]:
        print(
            "runtime diagnostics: scan was limited; narrow the query or inspect "
            "the controlled directory deliberately",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
