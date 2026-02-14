"""Validator orchestration."""

from __future__ import annotations

from typing import Callable

from app.domain.models import Itinerary, TripConstraints, ValidationIssue
from app.validators.backup_validator import validate_backup
from app.validators.budget_validator import validate_budget
from app.validators.distance_validator import validate_distance
from app.validators.pace_validator import validate_pace
from app.validators.time_validator import validate_time

DistanceFn = Callable[[float, float, float, float], float]
TravelTimeFn = Callable[[float, str], float]


def run_all_validators(
    itinerary: Itinerary,
    constraints: TripConstraints,
    *,
    distance_fn: DistanceFn | None = None,
    travel_time_fn: TravelTimeFn | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(validate_time(itinerary, constraints))
    issues.extend(
        validate_distance(
            itinerary,
            constraints,
            **(
                {}
                if distance_fn is None or travel_time_fn is None
                else {"distance_fn": distance_fn, "travel_time_fn": travel_time_fn}
            ),
        )
    )
    issues.extend(validate_budget(itinerary, constraints))
    issues.extend(validate_pace(itinerary, constraints))
    issues.extend(validate_backup(itinerary, constraints))
    return issues

