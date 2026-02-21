"""Constraint engine: aggregate independent checks."""

from __future__ import annotations

from app.domain.models import UserProfile
from app.domain.planning.persona import persona_limits
from app.domain.models import Itinerary, TripConstraints, ValidationIssue
from app.domain.planning.constraints.backtracking_constraint import BacktrackingConstraint
from app.domain.planning.constraints.base import Constraint
from app.domain.planning.constraints.budget_constraint import BudgetConstraint
from app.domain.planning.constraints.intensity_constraint import IntensityConstraint
from app.domain.planning.constraints.open_hours_constraint import OpenHoursConstraint
from app.domain.planning.constraints.reservation_constraint import ReservationConstraint
from app.domain.planning.constraints.time_constraint import TimeConstraint


class ConstraintEngine:
    def __init__(self, constraints: tuple[Constraint, ...]) -> None:
        self._constraints = constraints

    @classmethod
    def default(cls, *, profile: UserProfile | None = None) -> "ConstraintEngine":
        max_pois_override = None
        if profile is not None:
            max_pois_override, _ = persona_limits(profile)
        return cls(
            (
                TimeConstraint(),
                BudgetConstraint(),
                IntensityConstraint(max_pois_override=max_pois_override),
                OpenHoursConstraint(),
                BacktrackingConstraint(),
                ReservationConstraint(),
            )
        )

    def evaluate(self, itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
        violations: list[ValidationIssue] = []
        for item in self._constraints:
            violations.extend(item.check(itinerary, constraints))
        return violations


__all__ = ["ConstraintEngine"]
