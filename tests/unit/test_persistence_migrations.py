from __future__ import annotations

import sqlite3
from pathlib import Path

from app.persistence.backup import backup_sqlite
from app.persistence.drill import run_backup_restore_drill
from app.persistence.migration_runner import apply_sqlite_migrations, list_applied_migrations
from app.persistence.restore import restore_sqlite


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def test_apply_sqlite_migrations_creates_schema_and_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "migrations.sqlite3"
    with sqlite3.connect(db_path) as conn:
        first = apply_sqlite_migrations(conn)
        second = apply_sqlite_migrations(conn)
        applied = list_applied_migrations(conn)

        assert "0001_init" in applied
        assert "0002_indexes" in applied
        assert _table_exists(conn, "sessions")
        assert _table_exists(conn, "requests")
        assert _table_exists(conn, "plans")
        assert _table_exists(conn, "artifacts")
        assert first == ["0001_init", "0002_indexes"]
        assert second == []


def test_backup_restore_roundtrip(tmp_path: Path):
    db_path = tmp_path / "source.sqlite3"
    backup_path = tmp_path / "backup.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE t(k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        conn.execute("INSERT INTO t(k, v) VALUES ('x', 'v1')")

    backup_sqlite(db_path, backup_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE t SET v='v2' WHERE k='x'")

    restore_sqlite(backup_path, db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT v FROM t WHERE k='x'").fetchone()
    assert row is not None
    assert row[0] == "v1"


def test_backup_restore_drill_passes(tmp_path: Path):
    db_path = tmp_path / "drill.sqlite3"
    backup_dir = tmp_path / "backups"
    report = run_backup_restore_drill(db_path, backup_dir)
    assert report["passed"] is True
    assert Path(str(report["backup_file"])).exists()
