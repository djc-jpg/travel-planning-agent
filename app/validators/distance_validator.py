"""Distance validator: check whether daily commute time is excessive."""

from __future__ import annotations

from typing import Callable

from app.domain.constants import MAX_DAILY_TRAVEL_MINUTES
from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue
from app.planner.distance import estimate_distance, estimate_travel_time

DistanceFn = Callable[[float, float, float, float], float]
TravelTimeFn = Callable[[float, str], float]


def validate_distance(
    itinerary: Itinerary,
    constraints: TripConstraints,
    *,
    distance_fn: DistanceFn = estimate_distance,
    travel_time_fn: TravelTimeFn = estimate_travel_time,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    mode = constraints.transport_mode.value

    for day in itinerary.days:
        main_items = [s for s in day.schedule if not s.is_backup]
        total_travel = 0.0
        for i in range(len(main_items) - 1):
            a, b = main_items[i].poi, main_items[i + 1].poi
            dist_km = distance_fn(a.lat, a.lon, b.lat, b.lon)
            total_travel += travel_time_fn(dist_km, mode)

        if total_travel > MAX_DAILY_TRAVEL_MINUTES:
            issues.append(
                ValidationIssue(
                    code="TOO_MUCH_TRAVEL",
                    severity=Severity.HIGH,
                    message=(
                        f"Day {day.day_number} travel time {total_travel:.0f}m exceeds "
                        f"limit {MAX_DAILY_TRAVEL_MINUTES:.0f}m"
                    ),
                    day=day.day_number,
                    suggestions=[
                        "Use faster transport mode",
                        "Replace POIs with nearby options",
                        "Reduce POI count",
                    ],
                )
            )
    return issues

