"""Deterministic planning algorithms."""

from __future__ import annotations

from app.domain.models import Itinerary, POI, TripConstraints, UserProfile
from app.domain.planning.scheduling import DistanceFn, TravelTimeFn
from app.planner.routing_provider import RoutingProvider


def generate_itinerary(
    constraints: TripConstraints,
    profile: UserProfile,
    poi_candidates: list[POI],
    *,
    transport_mode: str | None = None,
    weather_data: dict | None = None,
    calendar_data: dict | None = None,
    distance_fn: DistanceFn | None = None,
    travel_time_fn: TravelTimeFn | None = None,
    routing_provider: RoutingProvider | None = None,
) -> Itinerary:
    from app.planner.core import generate_itinerary as _generate_itinerary

    kwargs: dict[str, object] = {
        "transport_mode": transport_mode,
        "weather_data": weather_data,
        "calendar_data": calendar_data,
        "routing_provider": routing_provider,
    }
    if distance_fn is not None:
        kwargs["distance_fn"] = distance_fn
    if travel_time_fn is not None:
        kwargs["travel_time_fn"] = travel_time_fn
    return _generate_itinerary(constraints, profile, poi_candidates, **kwargs)


__all__ = ["generate_itinerary"]
