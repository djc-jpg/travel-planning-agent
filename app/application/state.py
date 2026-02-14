"""Canonical graph state type for orchestration."""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class GraphState(TypedDict, total=False):
    """Single source of truth for LangGraph state schema."""

    messages: list[dict[str, Any]]
    trip_constraints: dict[str, Any]
    user_profile: dict[str, Any]
    requirements_missing: list[str]
    attraction_candidates: list[dict[str, Any]]
    itinerary_draft: Optional[dict[str, Any]]
    validation_issues: list[dict[str, Any]]
    final_itinerary: Optional[dict[str, Any]]
    repair_attempts: int
    max_repair_attempts: int
    status: str
    metrics: dict[str, Any]
    error_message: str
    error_code: str
    error_details: list[str]
    error_response: dict[str, Any]
    weather_data: Optional[dict[str, Any]]
    calendar_data: Optional[dict[str, Any]]


__all__ = ["GraphState"]
