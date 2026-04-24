"""Create an online SQLite backup and retain only the newest snapshots."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server.db import BACKUP_DIR, BACKUP_KEEP_LAST, DB_PATH


def main() -> int:
    backup_dir = BACKUP_DIR if BACKUP_DIR.is_absolute() else (ROOT_DIR / BACKUP_DIR)
    backup_dir = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(DB_PATH)
    if not source_path.is_absolute():
        source_path = ROOT_DIR / source_path
    source_path = source_path.resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"database not found: {source_path}")

    backup_path = backup_dir / f"backup_{datetime.now().strftime('%Y-%m-%d')}.db"

    with sqlite3.connect(source_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)

    backups = sorted(backup_dir.glob("backup_*.db"))
    if BACKUP_KEEP_LAST > 0 and len(backups) > BACKUP_KEEP_LAST:
        for stale_backup in backups[:-BACKUP_KEEP_LAST]:
            stale_backup.unlink(missing_ok=True)

    print(str(backup_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
