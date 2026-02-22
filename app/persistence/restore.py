"""SQLite restore utility."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

_DEFAULT_DB = Path("data") / "trip_agent.sqlite3"


def restore_sqlite(backup_path: Path, target_db: Path) -> dict[str, str]:
    if not backup_path.exists():
        raise FileNotFoundError(f"backup file not found: {backup_path}")
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup_path) as src, sqlite3.connect(target_db) as dst:
        src.backup(dst)
    return {
        "backup_path": str(backup_path),
        "target_db": str(target_db),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore SQLite DB from backup file")
    parser.add_argument("--backup-path", required=True)
    parser.add_argument("--target-db", default=str(_DEFAULT_DB))
    args = parser.parse_args(argv)

    report = restore_sqlite(Path(str(args.backup_path)), Path(str(args.target_db)))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
