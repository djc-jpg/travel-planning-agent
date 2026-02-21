"""Pace/intensity constraint."""

from __future__ import annotations

from app.domain.constants import PACE_MAX
from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


class IntensityConstraint:
    def __init__(self, *, max_pois_override: int | None = None) -> None:
        self._max_pois_override = max_pois_override

    def check(self, itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        max_poi = int(PACE_MAX.get(constraints.pace, 3))
        if self._max_pois_override:
            max_poi = min(max_poi, int(self._max_pois_override))
        for day in itinerary.days:
            count = sum(1 for item in day.schedule if not item.is_backup)
            if count <= max_poi:
                continue
            issues.append(
                ValidationIssue(
                    code="INTENSITY_OVERLOAD",
                    severity=Severity.MEDIUM,
                    day=day.day_number,
                    message=f"day {day.day_number} has {count} POIs > pace limit {max_poi}",
                )
            )
        return issues


__all__ = ["IntensityConstraint"]
