"""SQLite implementation for plan persistence records."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.persistence.models import (
    ArtifactPayload,
    ArtifactRecord,
    PlanExportRecord,
    PlanRecord,
    RequestRecord,
    SessionHistoryItem,
    SessionSummaryItem,
    SessionRecord,
)


def _to_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _from_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


class SQLitePlanPersistenceRepository:
    backend = "sqlite"

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_status TEXT NOT NULL,
                    last_trace_id TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    constraints_json TEXT NOT NULL,
                    user_profile_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS plans (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    degrade_level TEXT NOT NULL,
                    confidence_score REAL,
                    run_fingerprint_json TEXT,
                    itinerary_json TEXT,
                    issues_json TEXT NOT NULL,
                    next_questions_json TEXT NOT NULL,
                    field_evidence_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES requests(request_id)
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES requests(request_id)
                );

                CREATE INDEX IF NOT EXISTS idx_requests_session_id ON requests(session_id);
                CREATE INDEX IF NOT EXISTS idx_plans_session_id ON plans(session_id);
                CREATE INDEX IF NOT EXISTS idx_artifacts_request_id ON artifacts(request_id);
                """
            )

    def save_session(self, record: SessionRecord) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, created_at, updated_at, last_status, last_trace_id
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    last_status=excluded.last_status,
                    last_trace_id=excluded.last_trace_id
                """,
                (
                    record.session_id,
                    record.updated_at,
                    record.updated_at,
                    record.status,
                    record.trace_id,
                ),
            )

    def save_request(self, record: RequestRecord) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO requests (
                    request_id, session_id, trace_id, message,
                    constraints_json, user_profile_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.request_id,
                    record.session_id,
                    record.trace_id,
                    record.message,
                    _to_json(record.constraints),
                    _to_json(record.user_profile),
                    _to_json(record.metadata),
                    record.created_at,
                ),
            )

    def save_plan(self, record: PlanRecord) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO plans (
                    request_id, session_id, trace_id, status, degrade_level, confidence_score,
                    run_fingerprint_json, itinerary_json, issues_json, next_questions_json,
                    field_evidence_json, metrics_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.request_id,
                    record.session_id,
                    record.trace_id,
                    record.status,
                    record.degrade_level,
                    record.confidence_score,
                    _to_json(record.run_fingerprint),
                    _to_json(record.itinerary),
                    _to_json(record.issues),
                    _to_json(record.next_questions),
                    _to_json(record.field_evidence),
                    _to_json(record.metrics),
                    record.created_at,
                ),
            )

    def save_artifact(self, record: ArtifactRecord) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    request_id, artifact_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    record.request_id,
                    record.artifact_type,
                    _to_json(record.payload),
                    record.created_at,
                ),
            )

    def list_sessions(self, limit: int = 20) -> list[SessionSummaryItem]:
        safe_limit = max(1, min(limit, 100))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    session_id,
                    updated_at,
                    last_status,
                    last_trace_id
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [
            SessionSummaryItem(
                session_id=row[0],
                updated_at=row[1],
                last_status=row[2],
                last_trace_id=row[3],
            )
            for row in rows
        ]

    def list_session_history(self, session_id: str, limit: int = 20) -> list[SessionHistoryItem]:
        safe_limit = max(1, min(limit, 100))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    r.request_id,
                    r.session_id,
                    r.trace_id,
                    r.message,
                    COALESCE(p.status, 'pending'),
                    COALESCE(p.degrade_level, 'L3'),
                    p.confidence_score,
                    p.run_fingerprint_json,
                    r.created_at
                FROM requests r
                LEFT JOIN plans p ON p.request_id = r.request_id
                WHERE r.session_id = ?
                ORDER BY r.created_at DESC, r.rowid DESC
                LIMIT ?
                """,
                (session_id, safe_limit),
            ).fetchall()

        return [
            SessionHistoryItem(
                request_id=row[0],
                session_id=row[1],
                trace_id=row[2],
                message=row[3],
                status=row[4],
                degrade_level=row[5],
                confidence_score=row[6],
                run_fingerprint=_from_json(row[7], {}),
                created_at=row[8],
            )
            for row in rows
        ]

    def get_plan_export(self, request_id: str) -> PlanExportRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    r.request_id,
                    r.session_id,
                    r.trace_id,
                    r.message,
                    r.constraints_json,
                    r.user_profile_json,
                    r.metadata_json,
                    p.status,
                    p.degrade_level,
                    p.confidence_score,
                    p.run_fingerprint_json,
                    p.itinerary_json,
                    p.issues_json,
                    p.next_questions_json,
                    p.field_evidence_json,
                    p.metrics_json,
                    p.created_at
                FROM requests r
                JOIN plans p ON p.request_id = r.request_id
                WHERE r.request_id = ?
                LIMIT 1
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                return None

            artifact_rows = conn.execute(
                """
                SELECT artifact_type, payload_json, created_at
                FROM artifacts
                WHERE request_id = ?
                ORDER BY artifact_id ASC
                """,
                (request_id,),
            ).fetchall()

        artifacts = [
            ArtifactPayload(
                artifact_type=item[0],
                payload=_from_json(item[1], {}),
                created_at=item[2],
            )
            for item in artifact_rows
        ]
        return PlanExportRecord(
            request_id=row[0],
            session_id=row[1],
            trace_id=row[2],
            message=row[3],
            constraints=_from_json(row[4], {}),
            user_profile=_from_json(row[5], {}),
            metadata=_from_json(row[6], {}),
            status=row[7],
            degrade_level=row[8],
            confidence_score=row[9],
            run_fingerprint=_from_json(row[10], {}),
            itinerary=_from_json(row[11], None),
            issues=_from_json(row[12], []),
            next_questions=_from_json(row[13], []),
            field_evidence=_from_json(row[14], {}),
            metrics=_from_json(row[15], {}),
            created_at=row[16],
            artifacts=artifacts,
        )


__all__ = ["SQLitePlanPersistenceRepository"]
