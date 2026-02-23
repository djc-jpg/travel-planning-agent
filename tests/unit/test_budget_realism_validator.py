"""Tests for budget realism validator behavior."""

from __future__ import annotations

from app.domain.models import Itinerary, TripConstraints
from app.validators.budget_realism_validator import validate_budget_realism


def test_budget_realism_no_budget_constraint_does_not_raise_unrealistic() -> None:
    itinerary = Itinerary(city="beijing", total_cost=260.0, minimum_feasible_budget=260.0)
    constraints = TripConstraints(city="beijing", days=2)

    issues = validate_budget_realism(itinerary, constraints)

    assert all(issue.code != "BUDGET_UNREALISTIC" for issue in issues)


def test_budget_realism_raises_when_budget_below_minimum_feasible() -> None:
    itinerary = Itinerary(city="beijing", total_cost=900.0, minimum_feasible_budget=900.0)
    constraints = TripConstraints(city="beijing", days=3, budget_per_day=200.0)

    issues = validate_budget_realism(itinerary, constraints)

    assert any(issue.code == "BUDGET_UNREALISTIC" for issue in issues)


def test_budget_realism_keeps_budget_warning_issue() -> None:
    itinerary = Itinerary(
        city="beijing",
        total_cost=900.0,
        minimum_feasible_budget=900.0,
        budget_warning="budget too low",
    )
    constraints = TripConstraints(city="beijing", days=3, budget_per_day=200.0)

    issues = validate_budget_realism(itinerary, constraints)

    assert any(issue.code == "BUDGET_WARNING" for issue in issues)
