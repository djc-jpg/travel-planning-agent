"""Routing provider abstraction with transparent fallback diagnostics."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.config.settings import resolve_route_provider_default
from app.adapters.tool_factory import get_route_tool
from app.domain.models import POI
from app.planner.distance import estimate_distance, estimate_travel_time
from app.planner.route_realism import adjust_travel_minutes, estimate_routing_confidence
from app.tools.interfaces import RouteInput

_FIXTURE_FILE = Path(__file__).resolve().parents[1] / "data" / "routing_fixture_beijing.json"
_FALLBACK_SOURCE = "fallback_fixture"
_FALLBACK_CONFIDENCE_CAP = 0.45
_MAX_DIAGNOSTIC_EVENTS = 50
_LOGGER = logging.getLogger("trip-agent.routing")


class RoutingProvider(Protocol):
    def get_travel_time(
        self,
        origin: POI,
        destination: POI,
        mode: str,
        departure_time: datetime | None = None,
    ) -> float:
        """Return travel time in minutes between two POIs."""

    def get_confidence(
        self,
        origin: POI,
        destination: POI,
        mode: str,
        departure_time: datetime | None = None,
    ) -> float:
        """Return routing confidence in [0, 1]."""

    def get_route_source(self, origin: POI, destination: POI, mode: str) -> str:
        """Return route source type (real/fixture/fallback_fixture)."""

    def get_fallback_count(self) -> int:
        """Return fallback count."""

    def get_diagnostics(self) -> dict[str, Any]:
        """Return routing diagnostics for observability."""


@lru_cache(maxsize=1)
def _load_fixture() -> dict[tuple[str, str], dict[str, float]]:
    with open(_FIXTURE_FILE, encoding="utf-8") as fh:
        data = json.load(fh)

    pairs: dict[tuple[str, str], dict[str, float]] = {}
    for row in data.get("pairs", []):
        a = str(row.get("origin", "")).strip()
        b = str(row.get("destination", "")).strip()
        minutes = {k: float(v) for k, v in row.get("minutes", {}).items()}
        if not a or not b or not minutes:
            continue
        pairs[(a, b)] = minutes
        pairs[(b, a)] = minutes
    return pairs


class FixtureRoutingProvider:
    def __init__(self) -> None:
        self._pairs = _load_fixture()

    def get_travel_time(
        self,
        origin: POI,
        destination: POI,
        mode: str,
        departure_time: datetime | None = None,
    ) -> float:
        if origin.id == destination.id:
            return 0.0

        base_minutes: float | None = None
        direct = self._pairs.get((origin.name, destination.name))
        if direct is not None and mode in direct:
            base_minutes = max(5.0, round(direct[mode], 1))

        if base_minutes is None:
            dist = estimate_distance(origin.lat, origin.lon, destination.lat, destination.lon)
            base = estimate_travel_time(dist, mode)
            penalty = {
                "walking": 0.0,
                "public_transit": 8.0,
                "taxi": 4.0,
                "driving": 6.0,
            }.get(mode, 6.0)
            value = base + penalty
            if mode == "public_transit" and dist >= 10:
                value += 6.0
            base_minutes = round(max(8.0, value), 1)

        return adjust_travel_minutes(
            base_minutes=base_minutes,
            origin=origin,
            destination=destination,
            mode=mode,
            departure_time=departure_time,
        )

    def get_confidence(
        self,
        origin: POI,
        destination: POI,
        mode: str,
        departure_time: datetime | None = None,
    ) -> float:
        return estimate_routing_confidence(
            origin=origin,
            destination=destination,
            mode=mode,
            departure_time=departure_time,
            source="fixture",
        )

    def get_route_source(self, origin: POI, destination: POI, mode: str) -> str:
        _ = origin, destination, mode
        return "fixture"

    def get_fallback_count(self) -> int:
        return 0

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "routing_source": "fixture",
            "fallback_count": 0,
            "events": [],
        }


class RealMapRoutingProvider:
    def __init__(self, fallback: RoutingProvider | None = None) -> None:
        self._route_tool = get_route_tool()
        self._fallback = fallback or FixtureRoutingProvider()
        self._cache: dict[tuple[str, str, str], float] = {}
        self._source_cache: dict[tuple[str, str, str], str] = {}
        self._fallback_count = 0
        self._diagnostic_events: list[dict[str, Any]] = []

    def _record_fallback(
        self,
        *,
        origin: POI,
        destination: POI,
        mode: str,
        error: Exception,
    ) -> None:
        self._fallback_count += 1
        event = {
            "routing_source": _FALLBACK_SOURCE,
            "origin_id": origin.id,
            "destination_id": destination.id,
            "mode": mode,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        self._diagnostic_events.append(event)
        if len(self._diagnostic_events) > _MAX_DIAGNOSTIC_EVENTS:
            self._diagnostic_events = self._diagnostic_events[-_MAX_DIAGNOSTIC_EVENTS:]
        _LOGGER.warning(
            "routing fallback to fixture: %s -> %s mode=%s error=%s",
            origin.id,
            destination.id,
            mode,
            type(error).__name__,
        )

    def get_travel_time(
        self,
        origin: POI,
        destination: POI,
        mode: str,
        departure_time: datetime | None = None,
    ) -> float:
        key = (origin.id, destination.id, mode)
        if key in self._cache:
            return self._cache[key]

        try:
            result = self._route_tool.estimate_route(
                RouteInput(
                    origin_lat=origin.lat,
                    origin_lon=origin.lon,
                    dest_lat=destination.lat,
                    dest_lon=destination.lon,
                    mode=mode,
                )
            )
            minutes = max(5.0, round(float(result.duration_minutes), 1))
            self._source_cache[key] = "real"
        except Exception as exc:
            minutes = self._fallback.get_travel_time(
                origin,
                destination,
                mode,
                departure_time=departure_time,
            )
            self._source_cache[key] = _FALLBACK_SOURCE
            self._record_fallback(
                origin=origin,
                destination=destination,
                mode=mode,
                error=exc,
            )

        self._cache[key] = minutes
        return minutes

    def get_confidence(
        self,
        origin: POI,
        destination: POI,
        mode: str,
        departure_time: datetime | None = None,
    ) -> float:
        source = self.get_route_source(origin, destination, mode)
        baseline = estimate_routing_confidence(
            origin=origin,
            destination=destination,
            mode=mode,
            departure_time=departure_time,
            source="fixture" if source == _FALLBACK_SOURCE else source,
        )
        if source == _FALLBACK_SOURCE:
            return round(min(_FALLBACK_CONFIDENCE_CAP, baseline), 2)
        return baseline

    def get_route_source(self, origin: POI, destination: POI, mode: str) -> str:
        key = (origin.id, destination.id, mode)
        return self._source_cache.get(key, "real")

    def get_fallback_count(self) -> int:
        return self._fallback_count

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "routing_source": _FALLBACK_SOURCE if self._fallback_count else "real",
            "fallback_count": self._fallback_count,
            "events": list(self._diagnostic_events),
        }


def build_routing_provider() -> RoutingProvider:
    mode = resolve_route_provider_default()
    if mode == "real":
        return RealMapRoutingProvider()
    if mode == "auto":
        try:
            return RealMapRoutingProvider()
        except Exception as exc:
            _LOGGER.warning(
                "routing provider auto fallback to fixture during init: %s",
                type(exc).__name__,
            )
            return FixtureRoutingProvider()
    return FixtureRoutingProvider()
