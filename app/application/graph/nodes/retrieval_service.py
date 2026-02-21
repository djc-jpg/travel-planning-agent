"""Pure retrieval service for POIs, weather, and calendar context."""

from __future__ import annotations

import json as _json
import os
import time
from datetime import datetime
from typing import Any, Callable

from app.application.graph.nodes.tool_ports import CalendarToolPort, LoggerPort, POIToolPort, WeatherToolPort
from app.domain.models import POI, Severity, ValidationIssue
from app.domain.poi_semantics import filter_semantic_candidates
from app.observability.plan_metrics import observe_tool_call
from app.tools.interfaces import CalendarInput, POISearchInput, WeatherInput

_CRITICAL_FACT_FIELDS = (
    "ticket_price",
    "reservation_required",
    "open_hours",
    "closed_rules",
)


def _read_field(payload: Any, field: str, default: Any) -> Any:
    if isinstance(payload, dict):
        return payload.get(field, default)
    return getattr(payload, field, default)


def _normalize_poi_facts(poi: POI, *, source: str) -> POI:
    normalized = poi.model_copy(deep=True)
    facts = dict(normalized.fact_sources)

    for key in _CRITICAL_FACT_FIELDS:
        facts.setdefault(key, source)
    normalized.fact_sources = facts

    if source == "unknown":
        # Never expose fabricated hard facts when we only have model guesses.
        normalized.ticket_price = 0.0
        normalized.cost = 0.0
        normalized.open_time = None
        normalized.open_hours = None
        normalized.closed_rules = ""
        normalized.requires_reservation = False
        normalized.reservation_required = False
        normalized.reservation_days_ahead = 0
        normalized.metadata_source = "llm_generated"
        return normalized

    if not normalized.metadata_source:
        normalized.metadata_source = "tool_data"

    normalized.ticket_price = max(float(normalized.ticket_price or 0.0), float(normalized.cost or 0.0), 0.0)
    if normalized.cost <= 0:
        normalized.cost = normalized.ticket_price
    if not normalized.open_time and normalized.open_hours:
        normalized.open_time = normalized.open_hours
    if not normalized.open_hours and normalized.open_time:
        normalized.open_hours = normalized.open_time
    if not normalized.open_time:
        normalized.open_time = "以景区公告为准"
        normalized.open_hours = normalized.open_time
    if not normalized.closed_rules:
        normalized.closed_rules = "以景区当日公告为准"
    normalized.reservation_required = bool(normalized.reservation_required)
    normalized.requires_reservation = bool(normalized.reservation_required)
    return normalized


def llm_generate_pois(city: str, themes: list[str], count: int = 15) -> list[POI]:
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
                raw["metadata_source"] = "llm_generated"
                raw["fact_sources"] = {key: "unknown" for key in _CRITICAL_FACT_FIELDS}
                parsed = POI.model_validate(raw)
                pois.append(_normalize_poi_facts(parsed, source="unknown"))
            except Exception:
                continue
        return pois
    except Exception:
        return []


def _record_tool_metric(
    *,
    logger: LoggerPort,
    tool_name: str,
    started: float,
    ok: bool,
    returned_count: int = 0,
    error_code: str = "",
) -> None:
    latency_ms = (time.perf_counter() - started) * 1000.0
    observe_tool_call(
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        error_code=error_code,
        returned_count=returned_count,
    )
    if hasattr(logger, "tool_call"):
        try:
            logger.tool_call(
                tool_name,
                latency_ms=round(latency_ms, 2),
                ok=ok,
                error_code=error_code,
                returned_count=returned_count,
            )
        except Exception:
            return


def retrieve_trip_context(
    *,
    constraints: Any,
    profile: Any,
    logger: LoggerPort,
    poi_tool: POIToolPort,
    weather_tool: WeatherToolPort,
    calendar_tool: CalendarToolPort,
    strict_external: bool,
    has_curated_city_fn: Callable[[str], bool],
    get_city_pois_fn: Callable[..., list[POI]],
    llm_generator: Callable[[str, list[str]], list[POI]] = llm_generate_pois,
    default_spring_festival_date: str | None = None,
) -> dict[str, Any]:
    city = str(_read_field(constraints, "city", "") or "")
    themes = _read_field(profile, "themes", [])
    days = int(_read_field(constraints, "days", 3) or 3)
    target_count = max(8, min(30, days * 3))

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

    candidates: list[POI] = []
    if has_curated_city_fn(city):
        candidates = get_city_pois_fn(city, themes=themes, max_results=30)
        logger.summary(
            stage="retrieve",
            message=f"Using curated metadata POIs for city={city}, count={len(candidates)}",
        )
    else:
        params = POISearchInput(city=city, themes=themes, max_results=30)
        started = time.perf_counter()
        try:
            candidates = poi_tool.search_poi(params)
            _record_tool_metric(
                logger=logger,
                tool_name="poi.search",
                started=started,
                ok=True,
                returned_count=len(candidates),
            )
        except Exception as exc:
            _record_tool_metric(
                logger=logger,
                tool_name="poi.search",
                started=started,
                ok=False,
                error_code=type(exc).__name__,
            )
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
            started = time.perf_counter()
            try:
                candidates = poi_tool.search_poi(POISearchInput(city=city, max_results=30))
                _record_tool_metric(
                    logger=logger,
                    tool_name="poi.search_fallback",
                    started=started,
                    ok=True,
                    returned_count=len(candidates),
                )
            except Exception as exc:
                _record_tool_metric(
                    logger=logger,
                    tool_name="poi.search_fallback",
                    started=started,
                    ok=False,
                    error_code=type(exc).__name__,
                )
                logger.warning("retrieve", f"POI fallback query failed: {exc}")
                candidates = []
        else:
            if len(candidates) < target_count:
                started = time.perf_counter()
                try:
                    fallback = poi_tool.search_poi(POISearchInput(city=city, max_results=30))
                    _record_tool_metric(
                        logger=logger,
                        tool_name="poi.search_backfill",
                        started=started,
                        ok=True,
                        returned_count=len(fallback),
                    )
                except Exception as exc:
                    _record_tool_metric(
                        logger=logger,
                        tool_name="poi.search_backfill",
                        started=started,
                        ok=False,
                        error_code=type(exc).__name__,
                    )
                    logger.warning("retrieve", f"POI backfill query failed: {exc}")
                    fallback = []
                existing = {candidate.id for candidate in candidates}
                for poi in fallback:
                    if poi.id in existing:
                        continue
                    candidates.append(poi)
                    existing.add(poi.id)
                    if len(candidates) >= target_count:
                        break

        if not candidates and not strict_external:
            candidates = llm_generator(city, themes)

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

    normalized_candidates: list[POI] = []
    for poi in candidates:
        source = "unknown" if "llm" in str(poi.metadata_source).lower() else "data"
        normalized_candidates.append(_normalize_poi_facts(poi, source=source))
    candidates, semantic_stats = filter_semantic_candidates(
        normalized_candidates,
        strict_external=strict_external,
        minimum_count=target_count,
    )
    logger.summary(
        stage="retrieve",
        message=(
            f"Semantic filter city={city}, selected={semantic_stats['selected']}, "
            f"experience={semantic_stats['experience']}, "
            f"unknown={semantic_stats['unknown']}, "
            f"infrastructure={semantic_stats['infrastructure']}"
        ),
    )

    if not candidates:
        return {
            "attraction_candidates": [],
            "validation_issues": [
                ValidationIssue(
                    code="NO_CANDIDATES",
                    severity=Severity.HIGH,
                    message=f"No experience POIs after semantic filtering for city={city}",
                    suggestions=["Relax theme constraints", "Disable strict mode for fallback unknown POIs"],
                ).model_dump(mode="json")
            ],
            "error_code": "NO_CANDIDATES",
            "error_message": "No semantic POI candidates",
        }

    weather_data = None
    calendar_data = None
    date_start = _read_field(constraints, "date_start", None)
    holiday_hint = _read_field(constraints, "holiday_hint", None)
    date_str = str(date_start) if date_start else datetime.now().strftime("%Y-%m-%d")
    if not date_start and holiday_hint == "spring_festival":
        date_str = default_spring_festival_date or os.getenv(
            "DEFAULT_SPRING_FESTIVAL_DATE", "2026-02-17"
        )

    started = time.perf_counter()
    try:
        weather_result = weather_tool.get_weather(
            WeatherInput(city=city, date_start=date_str, days=days)
        )
        forecast_rows = list(getattr(weather_result, "forecasts", []) or [])
        _record_tool_metric(
            logger=logger,
            tool_name="weather.get_weather",
            started=started,
            ok=True,
            returned_count=len(forecast_rows),
        )
        weather_data = weather_result.model_dump(mode="json")
    except Exception as exc:
        _record_tool_metric(
            logger=logger,
            tool_name="weather.get_weather",
            started=started,
            ok=False,
            error_code=type(exc).__name__,
        )
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

    started = time.perf_counter()
    try:
        calendar_result = calendar_tool.get_calendar(
            CalendarInput(date_start=date_str, days=days)
        )
        day_rows = list(getattr(calendar_result, "days", []) or [])
        _record_tool_metric(
            logger=logger,
            tool_name="calendar.get_calendar",
            started=started,
            ok=True,
            returned_count=len(day_rows),
        )
        calendar_data = calendar_result.model_dump(mode="json")
    except Exception as exc:
        _record_tool_metric(
            logger=logger,
            tool_name="calendar.get_calendar",
            started=started,
            ok=False,
            error_code=type(exc).__name__,
        )
        logger.warning("retrieve", f"Calendar query failed, continue without calendar: {exc}")

    return {
        "attraction_candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "validation_issues": [],
        "weather_data": weather_data,
        "calendar_data": calendar_data,
    }


__all__ = ["llm_generate_pois", "retrieve_trip_context"]
