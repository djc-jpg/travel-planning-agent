"""Retrieve node for POI candidates, weather, and calendar context."""

from __future__ import annotations

import json as _json
import os
from datetime import datetime
from typing import Any

from app.adapters.tool_factory import get_calendar_tool, get_poi_tool, get_weather_tool
from app.domain.models import POI, Severity, ValidationIssue
from app.infrastructure.logging import get_logger
from app.tools.interfaces import CalendarInput, POISearchInput, WeatherInput


def _strict_external_enabled() -> bool:
    value = os.getenv("STRICT_EXTERNAL_DATA", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _llm_generate_pois(city: str, themes: list[str], count: int = 15) -> list[POI]:
    """Generate fallback POIs from LLM only when external data is unavailable."""
    try:
        from app.infrastructure.llm_factory import get_llm

        llm = get_llm()
        if llm is None:
            return []

        prompt = (
            f"You are a travel expert for {city}. "
            f"Return exactly {count} real attractions for city={city} with themes={themes}. "
            "Output JSON array only with fields: "
            "id,name,city,lat,lon,themes,duration_hours,cost,indoor,open_time,description."
        )
        resp = llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        content = content.strip()

        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        raw_list = _json.loads(content)
        pois: list[POI] = []
        for idx, raw in enumerate(raw_list):
            try:
                raw["id"] = raw.get("id", f"llm_{idx:03d}")
                raw["city"] = city
                pois.append(POI.model_validate(raw))
            except Exception:
                continue
        return pois
    except Exception:
        return []


def retrieve_node(state: dict[str, Any]) -> dict[str, Any]:
    constraints = state.get("trip_constraints", {})
    profile = state.get("user_profile", {})
    logger = get_logger()
    strict_external = _strict_external_enabled()

    city = constraints.get("city", "") if isinstance(constraints, dict) else getattr(constraints, "city", "")
    themes = profile.get("themes", []) if isinstance(profile, dict) else getattr(profile, "themes", [])

    if not city:
        return {
            "attraction_candidates": [],
            "validation_issues": [
                ValidationIssue(
                    code="NO_CANDIDATES",
                    severity=Severity.HIGH,
                    message="City is missing. Cannot retrieve POIs.",
                ).model_dump(mode="json")
            ],
            "error_code": "NO_CANDIDATES",
            "error_message": "Missing city",
        }

    params = POISearchInput(city=city, themes=themes, max_results=30)
    try:
        poi_tool = get_poi_tool()
        candidates = poi_tool.search_poi(params)
    except Exception as exc:
        logger.error("retrieve", f"POI query failed: {exc}")
        return {
            "attraction_candidates": [],
            "validation_issues": [
                ValidationIssue(
                    code="TOOL_UNAVAILABLE",
                    severity=Severity.HIGH,
                    message=f"POI service unavailable: {exc}",
                ).model_dump(mode="json")
            ],
            "error_code": "TOOL_UNAVAILABLE",
            "error_message": "POI service unavailable",
        }

    if not candidates:
        try:
            candidates = poi_tool.search_poi(POISearchInput(city=city, max_results=30))
        except Exception as exc:
            logger.warning("retrieve", f"POI fallback query failed: {exc}")
            candidates = []

    if not candidates and not strict_external:
        candidates = _llm_generate_pois(city, themes)

    if not candidates:
        return {
            "attraction_candidates": [],
            "validation_issues": [
                ValidationIssue(
                    code="NO_CANDIDATES",
                    severity=Severity.HIGH,
                    message=f"No POI candidates found for city={city}",
                    suggestions=["Check city name", "Relax theme constraints"],
                ).model_dump(mode="json")
            ],
            "error_code": "NO_CANDIDATES",
            "error_message": "No POI candidates",
        }

    weather_data = None
    calendar_data = None
    days = constraints.get("days", 3) if isinstance(constraints, dict) else getattr(constraints, "days", 3)
    date_start = constraints.get("date_start") if isinstance(constraints, dict) else getattr(constraints, "date_start", None)
    date_str = str(date_start) if date_start else datetime.now().strftime("%Y-%m-%d")

    try:
        weather_tool = get_weather_tool()
        weather_result = weather_tool.get_weather(WeatherInput(city=city, date_start=date_str, days=days))
        weather_data = weather_result.model_dump(mode="json")
    except Exception as exc:
        logger.warning("retrieve", f"Weather query failed, continue without weather: {exc}")
        if strict_external:
            return {
                "attraction_candidates": [],
                "validation_issues": [
                    ValidationIssue(
                        code="TOOL_UNAVAILABLE",
                        severity=Severity.HIGH,
                        message=f"Weather service unavailable: {exc}",
                    ).model_dump(mode="json")
                ],
                "error_code": "TOOL_UNAVAILABLE",
                "error_message": "Weather service unavailable",
            }

    try:
        calendar_tool = get_calendar_tool()
        calendar_result = calendar_tool.get_calendar(CalendarInput(date_start=date_str, days=days))
        calendar_data = calendar_result.model_dump(mode="json")
    except Exception as exc:
        logger.warning("retrieve", f"Calendar query failed, continue without calendar: {exc}")

    return {
        "attraction_candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "validation_issues": [],
        "weather_data": weather_data,
        "calendar_data": calendar_data,
    }

