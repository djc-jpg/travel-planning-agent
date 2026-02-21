"""Compatibility shim for planner entrypoint."""

from __future__ import annotations

from app.domain.models import Itinerary, POI, TripConstraints, UserProfile
from app.domain.planning.constraints import ConstraintEngine
from app.domain.planning.postprocess import generate_itinerary_impl
from app.domain.planning.repair import RepairEngine
from app.domain.planning.scheduling import DistanceFn, TravelTimeFn
from app.planner.distance import estimate_distance, estimate_travel_time
from app.planner.routing_provider import RoutingProvider


def _repair_action_to_user_note(action: str) -> str | None:
    parts = str(action).split(":")
    if len(parts) < 4:
        return None
    day_token, action_code = parts[0], parts[1]
    if action_code != "remove_poi" or parts[-1] != "budget_trim":
        return None
    if not day_token.startswith("day"):
        return None
    day_no = day_token[3:] or "?"
    poi_name = ":".join(parts[2:-1]).strip()
    if not poi_name:
        return None
    return f"预算优化：第{day_no}天移除了「{poi_name}」，以尽量满足预算上限。"


def generate_itinerary(
    constraints: TripConstraints,
    profile: UserProfile,
    poi_candidates: list[POI],
    *,
    transport_mode: str | None = None,
    weather_data: dict | None = None,
    calendar_data: dict | None = None,
    distance_fn: DistanceFn = estimate_distance,
    travel_time_fn: TravelTimeFn = estimate_travel_time,
    routing_provider: RoutingProvider | None = None,
) -> Itinerary:
    itinerary = generate_itinerary_impl(
        constraints,
        profile,
        poi_candidates,
        transport_mode=transport_mode,
        weather_data=weather_data,
        calendar_data=calendar_data,
        distance_fn=distance_fn,
        travel_time_fn=travel_time_fn,
        routing_provider=routing_provider,
    )
    constraint_engine = ConstraintEngine.default(profile=profile)
    repair_engine = RepairEngine(constraint_engine)
    repair_result = repair_engine.repair(itinerary, constraints, profile=profile)
    repaired = repair_result.itinerary
    if repair_result.actions:
        repaired.assumptions.extend([f"repair:{action}" for action in repair_result.actions])
        for action in repair_result.actions:
            note = _repair_action_to_user_note(action)
            if note:
                repaired.assumptions.append(note)
    if repair_result.remaining_violations:
        unresolved = ", ".join(v.code for v in repair_result.remaining_violations[:4])
        repaired.assumptions.append(f"constraints_unresolved:{unresolved}")
    return repaired


__all__ = ["generate_itinerary"]
