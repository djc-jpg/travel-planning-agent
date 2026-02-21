"""Open-hours feasibility constraint."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue
from app.domain.planning.constraints.common import parse_hhmm, parse_open_hours


class OpenHoursConstraint:
    def check(self, itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for day in itinerary.days:
            for item in day.schedule:
                if item.is_backup:
                    continue
                hours = parse_open_hours(item.poi.open_hours or item.poi.open_time)
                if hours is None:
                    continue
                start = parse_hhmm(item.start_time)
                end = parse_hhmm(item.end_time)
                if start is None or end is None:
                    continue
                open_start, open_end = hours
                if start < open_start or end > open_end:
                    issues.append(
                        ValidationIssue(
                            code="OPEN_HOURS_VIOLATION",
                            severity=Severity.HIGH,
                            day=day.day_number,
                            message=f"{item.poi.name} {item.start_time}-{item.end_time} outside {item.poi.open_time}",
                        )
                    )
        return issues


__all__ = ["OpenHoursConstraint"]
