"""Read-only history/export service."""

from __future__ import annotations

from app.application.context import AppContext
from app.persistence.models import PlanExportRecord, SessionHistoryItem, SessionSummaryItem


def list_session_history(*, ctx: AppContext, session_id: str, limit: int = 20) -> list[SessionHistoryItem]:
    repo = ctx.persistence_repo
    fetch = getattr(repo, "list_session_history", None)
    if not callable(fetch):
        return []
    safe_limit = max(1, min(limit, 100))
    return list(fetch(session_id, safe_limit))


def list_sessions(*, ctx: AppContext, limit: int = 20) -> list[SessionSummaryItem]:
    repo = ctx.persistence_repo
    fetch = getattr(repo, "list_sessions", None)
    if not callable(fetch):
        return []
    safe_limit = max(1, min(limit, 100))
    return list(fetch(safe_limit))


def get_plan_export(*, ctx: AppContext, request_id: str) -> PlanExportRecord | None:
    repo = ctx.persistence_repo
    fetch = getattr(repo, "get_plan_export", None)
    if not callable(fetch):
        return None
    return fetch(request_id)


__all__ = ["get_plan_export", "list_session_history", "list_sessions"]
