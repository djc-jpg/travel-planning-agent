"""SQLite backup utility."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

_DEFAULT_DB = Path("data") / "trip_agent.sqlite3"
_DEFAULT_BACKUP_DIR = Path("data") / "backups"


def backup_sqlite(source_db: Path, backup_path: Path) -> dict[str, str]:
    if not source_db.exists():
        raise FileNotFoundError(f"source db not found: {source_db}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_db) as src, sqlite3.connect(backup_path) as dst:
        src.backup(dst)
    return {
        "source_db": str(source_db),
        "backup_path": str(backup_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backup SQLite persistence DB")
    parser.add_argument("--source-db", default=str(_DEFAULT_DB))
    parser.add_argument("--backup-path", default="")
    parser.add_argument("--backup-dir", default=str(_DEFAULT_BACKUP_DIR))
    args = parser.parse_args(argv)

    source_db = Path(str(args.source_db))
    backup_path_raw = str(args.backup_path).strip()
    if backup_path_raw:
        backup_path = Path(backup_path_raw)
    else:
        backup_dir = Path(str(args.backup_dir))
        stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        backup_path = backup_dir / f"trip_agent_{stamp}.sqlite3"

    report = backup_sqlite(source_db, backup_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
