"""Budget realism validator."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_budget_realism(
    itinerary: Itinerary,
    constraints: TripConstraints,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if itinerary.city == "北京" and itinerary.total_cost < 400:
        issues.append(
            ValidationIssue(
                code="BUDGET_UNREALISTIC",
                severity=Severity.MEDIUM,
                message=f"预算明显偏低: {itinerary.total_cost:.0f} 元",
                suggestions=["增加餐饮与交通最低成本", "使用真实门票估算"],
            )
        )

    if itinerary.budget_warning:
        issues.append(
            ValidationIssue(
                code="BUDGET_WARNING",
                severity=Severity.MEDIUM,
                message=itinerary.budget_warning,
                suggestions=["提高预算或减少收费景点"],
            )
        )
    return issues
