"""节奏验证器：检查每天景点数量是否匹配 pace"""

from __future__ import annotations

from app.domain.constants import PACE_MAX
from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_pace(
    itinerary: Itinerary,
    constraints: TripConstraints,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    max_poi = PACE_MAX.get(constraints.pace, 3)

    for day in itinerary.days:
        main_count = sum(1 for s in day.schedule if not s.is_backup)
        if main_count > max_poi:
            issues.append(
                ValidationIssue(
                    code="PACE_MISMATCH",
                    severity=Severity.MEDIUM,
                    message=f"第{day.day_number}天有 {main_count} 个景点，超过 {constraints.pace.value} 节奏上限 {max_poi}",
                    day=day.day_number,
                    suggestions=["减少景点数量以匹配节奏偏好"],
                )
            )
    return issues
