"""Run SQLite schema migrations for plan persistence DB."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from app.persistence.migration_runner import apply_sqlite_migrations

_DEFAULT_DB = Path("data") / "trip_agent.sqlite3"


def _resolve_db_path(cli_value: str) -> Path:
    value = cli_value.strip()
    if value:
        return Path(value)
    env_path = os.getenv("PLAN_PERSISTENCE_DB", "").strip()
    if env_path:
        return Path(env_path)
    return _DEFAULT_DB


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply SQLite schema migrations")
    parser.add_argument("--db", default="", help="Target SQLite DB path")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(str(args.db))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        applied = apply_sqlite_migrations(conn)

    report = {
        "db_path": str(db_path),
        "applied_count": len(applied),
        "applied_versions": applied,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
