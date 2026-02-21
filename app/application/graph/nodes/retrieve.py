"""Retrieve node orchestration: resolve dependencies then call retrieval service."""

from __future__ import annotations

import os
from typing import Any

from app.adapters.tool_factory import get_calendar_tool, get_poi_tool, get_weather_tool
from app.application.graph.nodes.retrieval_service import retrieve_trip_context
from app.infrastructure.logging import get_logger
from app.planner.poi_metadata import get_city_pois, has_curated_city


def _strict_external_enabled() -> bool:
    value = os.getenv("STRICT_EXTERNAL_DATA", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def retrieve_node(state: dict[str, Any]) -> dict[str, Any]:
    constraints = state.get("trip_constraints", {})
    profile = state.get("user_profile", {})

    service_result = retrieve_trip_context(
        constraints=constraints,
        profile=profile,
        logger=get_logger(),
        poi_tool=get_poi_tool(),
        weather_tool=get_weather_tool(),
        calendar_tool=get_calendar_tool(),
        strict_external=_strict_external_enabled(),
        has_curated_city_fn=has_curated_city,
        get_city_pois_fn=get_city_pois,
    )
    return service_result


__all__ = ["retrieve_node"]

