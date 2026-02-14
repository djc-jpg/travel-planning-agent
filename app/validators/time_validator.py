"""Time validator: ensure daily itinerary duration is not excessive."""

from __future__ import annotations

from app.domain.constants import DEFAULT_DAILY_HOURS
from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_time(itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for day in itinerary.days:
        total_hours = sum(
            item.poi.duration_hours + item.travel_minutes / 60 for item in day.schedule if not item.is_backup
        )
        if total_hours > DEFAULT_DAILY_HOURS:
            issues.append(
                ValidationIssue(
                    code="OVER_TIME",
                    severity=Severity.HIGH,
                    message=(
                        f"Day {day.day_number} total duration {total_hours:.1f}h exceeds "
                        f"limit {DEFAULT_DAILY_HOURS:.1f}h"
                    ),
                    day=day.day_number,
                    suggestions=[
                        "Reduce POI count",
                        "Remove long-duration POIs",
                        "Move some POIs to another day",
                    ],
                )
            )
    return issues

