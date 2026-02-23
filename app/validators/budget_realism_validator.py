"""Budget realism validator."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_budget_realism(
    itinerary: Itinerary,
    constraints: TripConstraints,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    budget_limit = 0.0
    if constraints.total_budget:
        budget_limit = float(constraints.total_budget)
    elif constraints.budget_per_day:
        budget_limit = float(constraints.budget_per_day) * float(max(constraints.days, 1))

    minimum_feasible = float(itinerary.minimum_feasible_budget or itinerary.total_cost or 0.0)
    if budget_limit > 0 and minimum_feasible > 0 and budget_limit + 1e-6 < minimum_feasible:
        gap = minimum_feasible - budget_limit
        issues.append(
            ValidationIssue(
                code="BUDGET_UNREALISTIC",
                severity=Severity.MEDIUM,
                message=(
                    f"budget {budget_limit:.0f} is below minimum feasible "
                    f"{minimum_feasible:.0f} (gap {gap:.0f})"
                ),
                suggestions=[
                    "increase budget",
                    "reduce paid attractions or cross-district transport",
                ],
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
