"""备选验证器：检查每天是否有备选方案"""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_backup(
    itinerary: Itinerary,
    constraints: TripConstraints,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for day in itinerary.days:
        backup_count = len(day.backups) + sum(1 for s in day.schedule if s.is_backup)
        if backup_count == 0:
            issues.append(
                ValidationIssue(
                    code="MISSING_BACKUP",
                    severity=Severity.LOW,
                    message=f"第{day.day_number}天没有备选方案",
                    day=day.day_number,
                    suggestions=["添加室内景点作为雨天备选", "添加附近景点作为人多时备选"],
                )
            )
    return issues
