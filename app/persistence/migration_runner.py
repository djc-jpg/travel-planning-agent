"""SQLite schema migration runner."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_FILES = (
    "0001_init.sql",
    "0002_indexes.sql",
)


def _load_migration_sql(filename: str) -> str:
    path = _MIGRATIONS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"migration file missing: {path}")
    return path.read_text(encoding="utf-8")


def _migration_version(filename: str) -> str:
    return filename.split(".", 1)[0]


def _migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def list_applied_migrations(conn: sqlite3.Connection) -> dict[str, str]:
    ensure_migration_table(conn)
    rows = conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    return {str(version): str(checksum) for version, checksum in rows}


def apply_sqlite_migrations(conn: sqlite3.Connection) -> list[str]:
    ensure_migration_table(conn)
    applied = list_applied_migrations(conn)
    applied_now: list[str] = []
    for filename in _MIGRATION_FILES:
        version = _migration_version(filename)
        sql = _load_migration_sql(filename)
        checksum = _migration_checksum(sql)
        existing = applied.get(version)
        if existing is not None:
            if existing != checksum:
                raise RuntimeError(f"migration checksum mismatch for version={version}")
            continue

        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
            (
                version,
                checksum,
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ),
        )
        applied_now.append(version)
    return applied_now


__all__ = ["apply_sqlite_migrations", "ensure_migration_table", "list_applied_migrations"]
