"""Backup/restore drill for SQLite persistence DB."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from app.persistence.backup import backup_sqlite
from app.persistence.migrate import _resolve_db_path
from app.persistence.migration_runner import apply_sqlite_migrations
from app.persistence.restore import restore_sqlite

_DEFAULT_BACKUP_DIR = Path("data") / "backups"


def _write_marker(conn: sqlite3.Connection, *, marker_value: str) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS persistence_drill_markers (
            marker_key TEXT PRIMARY KEY,
            marker_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO persistence_drill_markers(marker_key, marker_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(marker_key) DO UPDATE SET
            marker_value=excluded.marker_value,
            updated_at=excluded.updated_at
        """,
        ("drill_marker", marker_value, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )


def _read_marker(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT marker_value FROM persistence_drill_markers WHERE marker_key='drill_marker' LIMIT 1"
    ).fetchone()
    return str(row[0]) if row else ""


def run_backup_restore_drill(db_path: Path, backup_dir: Path) -> dict[str, object]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        apply_sqlite_migrations(conn)
        baseline = f"baseline_{int(time.time())}"
        _write_marker(conn, marker_value=baseline)

    backup_file = backup_dir / f"drill_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.sqlite3"
    backup_sqlite(db_path, backup_file)

    with sqlite3.connect(db_path) as conn:
        _write_marker(conn, marker_value="corrupted_after_backup")
        corrupted_marker = _read_marker(conn)

    restore_sqlite(backup_file, db_path)
    with sqlite3.connect(db_path) as conn:
        restored_marker = _read_marker(conn)

    passed = restored_marker == baseline and corrupted_marker == "corrupted_after_backup"
    return {
        "db_path": str(db_path),
        "backup_file": str(backup_file),
        "baseline_marker": baseline,
        "corrupted_marker": corrupted_marker,
        "restored_marker": restored_marker,
        "passed": passed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SQLite backup/restore drill")
    parser.add_argument("--db", default="")
    parser.add_argument("--backup-dir", default=str(_DEFAULT_BACKUP_DIR))
    parser.add_argument(
        "--output",
        default=str(Path("eval") / "reports" / "persistence_drill_latest.json"),
    )
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(str(args.db))
    report = run_backup_restore_drill(db_path, Path(str(args.backup_dir)))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)

    out_path = Path(str(args.output))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered + "\n", encoding="utf-8")
    return 0 if bool(report.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
