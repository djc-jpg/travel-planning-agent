"""Budget feasibility constraint."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


class BudgetConstraint:
    def check(self, itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
        budget_limit = 0.0
        if constraints.total_budget:
            budget_limit = float(constraints.total_budget)
        elif constraints.budget_per_day:
            budget_limit = float(constraints.budget_per_day) * float(constraints.days)
        if budget_limit <= 0:
            return []
        if float(itinerary.total_cost) <= budget_limit + 1e-6:
            return []
        return [
            ValidationIssue(
                code="OVER_BUDGET",
                severity=Severity.HIGH,
                message=f"total_cost {itinerary.total_cost:.0f} exceeds budget {budget_limit:.0f}",
            )
        ]


__all__ = ["BudgetConstraint"]
