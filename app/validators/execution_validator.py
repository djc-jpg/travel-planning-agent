"""Execution validator for timeline feasibility and buffering."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_execution(itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        for idx, item in enumerate(main):
            if idx > 0 and item.travel_minutes <= 0:
                issues.append(
                    ValidationIssue(
                        code="TRAVEL_TIME_INVALID",
                        severity=Severity.HIGH,
                        day=day.day_number,
                        message=f"{item.poi.name} 交通时间不合理（<=0）",
                        suggestions=["使用routing provider重算交通时间"],
                    )
                )
            if item.buffer_minutes < 10:
                issues.append(
                    ValidationIssue(
                        code="BUFFER_TOO_LOW",
                        severity=Severity.MEDIUM,
                        day=day.day_number,
                        message=f"{item.poi.name} 缓冲时间不足（{item.buffer_minutes:.0f}分钟）",
                        suggestions=["增加安检/排队缓冲"],
                    )
                )
    return issues

