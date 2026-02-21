"""Base types for planning constraints."""

from __future__ import annotations

from typing import Protocol

from app.domain.models import Itinerary, TripConstraints, ValidationIssue


class Constraint(Protocol):
    """Single-responsibility constraint contract."""

    def check(self, itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
        ...


__all__ = ["Constraint"]
