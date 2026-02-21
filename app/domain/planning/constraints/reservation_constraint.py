"""Reservation readiness constraint."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


class ReservationConstraint:
    def check(self, itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for day in itinerary.days:
            for item in day.schedule:
                if item.is_backup:
                    continue
                required = bool(item.poi.requires_reservation or item.poi.reservation_required)
                if not required:
                    continue
                notes = str(item.notes or "").lower()
                if "reservation" in notes or "预约" in notes:
                    continue
                issues.append(
                    ValidationIssue(
                        code="RESERVATION_RISK",
                        severity=Severity.MEDIUM,
                        day=day.day_number,
                        message=f"{item.poi.name} requires reservation but no reminder in notes",
                    )
                )
        return issues


__all__ = ["ReservationConstraint"]
