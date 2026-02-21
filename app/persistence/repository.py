"""Persistence repository interface and factory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from app.persistence.models import (
    ArtifactRecord,
    PlanExportRecord,
    PlanRecord,
    RequestRecord,
    SessionHistoryItem,
    SessionSummaryItem,
    SessionRecord,
)
from app.persistence.sqlite_repository import SQLitePlanPersistenceRepository

_TRUTHY = {"1", "true", "yes", "on"}
_DEFAULT_DB_PATH = Path("data") / "trip_agent.sqlite3"


class PlanPersistenceRepository(Protocol):
    backend: str

    def save_session(self, record: SessionRecord) -> None: ...

    def save_request(self, record: RequestRecord) -> None: ...

    def save_plan(self, record: PlanRecord) -> None: ...

    def save_artifact(self, record: ArtifactRecord) -> None: ...

    def list_sessions(self, limit: int = 20) -> list[SessionSummaryItem]: ...

    def list_session_history(self, session_id: str, limit: int = 20) -> list[SessionHistoryItem]: ...

    def get_plan_export(self, request_id: str) -> PlanExportRecord | None: ...


class NoopPlanPersistenceRepository:
    backend = "noop"

    def save_session(self, record: SessionRecord) -> None:
        _ = record

    def save_request(self, record: RequestRecord) -> None:
        _ = record

    def save_plan(self, record: PlanRecord) -> None:
        _ = record

    def save_artifact(self, record: ArtifactRecord) -> None:
        _ = record

    def list_sessions(self, limit: int = 20) -> list[SessionSummaryItem]:
        _ = limit
        return []

    def list_session_history(self, session_id: str, limit: int = 20) -> list[SessionHistoryItem]:
        _ = (session_id, limit)
        return []

    def get_plan_export(self, request_id: str) -> PlanExportRecord | None:
        _ = request_id
        return None


def _enabled() -> bool:
    raw = os.getenv("PLAN_PERSISTENCE_ENABLED", "true").strip().lower()
    return raw in _TRUTHY


def _db_path() -> Path:
    raw = os.getenv("PLAN_PERSISTENCE_DB", "").strip()
    return Path(raw) if raw else _DEFAULT_DB_PATH


def get_plan_persistence() -> PlanPersistenceRepository:
    if not _enabled():
        return NoopPlanPersistenceRepository()
    return SQLitePlanPersistenceRepository(_db_path())


__all__ = [
    "NoopPlanPersistenceRepository",
    "PlanPersistenceRepository",
    "get_plan_persistence",
]
