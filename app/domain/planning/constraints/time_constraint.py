"""Time feasibility constraint."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue
from app.domain.planning.buffer import DAY_MAX_MINUTES
from app.domain.planning.constraints.common import item_duration_minutes, parse_hhmm


class TimeConstraint:
    def check(self, itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for day in itinerary.days:
            main = [item for item in day.schedule if not item.is_backup]
            total_minutes = 0.0
            prev_end: int | None = None
            for item in main:
                start = parse_hhmm(item.start_time)
                end = parse_hhmm(item.end_time)
                if prev_end is not None and start is not None and start < prev_end:
                    issues.append(
                        ValidationIssue(
                            code="TIME_CONFLICT",
                            severity=Severity.HIGH,
                            day=day.day_number,
                            message=f"{item.poi.name} start={item.start_time} overlaps previous stop",
                        )
                    )
                if end is not None:
                    prev_end = end
                total_minutes += item_duration_minutes(item) + float(item.travel_minutes) + float(item.buffer_minutes)
            if total_minutes > DAY_MAX_MINUTES:
                issues.append(
                    ValidationIssue(
                        code="DAY_OVERLOAD",
                        severity=Severity.HIGH,
                        day=day.day_number,
                        message=f"day minutes {total_minutes:.0f} exceed limit {DAY_MAX_MINUTES:.0f}",
                    )
                )
        return issues


__all__ = ["TimeConstraint"]
