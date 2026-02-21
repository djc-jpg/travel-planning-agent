"""Backtracking / route churn constraint."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def _cluster_of(item) -> str:
    if item.poi.cluster:
        return str(item.poi.cluster)
    notes = str(item.notes or "")
    marker = "cluster="
    if marker in notes:
        return notes.split(marker, 1)[1].split(" ", 1)[0].split("|", 1)[0].strip()
    return "geo:unknown"


class BacktrackingConstraint:
    def check(self, itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for day in itinerary.days:
            main = [item for item in day.schedule if not item.is_backup]
            if len(main) < 3:
                continue
            clusters = [_cluster_of(item) for item in main]
            switches = sum(1 for idx in range(1, len(clusters)) if clusters[idx] != clusters[idx - 1])
            ping_pong = sum(
                1
                for idx in range(2, len(clusters))
                if clusters[idx] == clusters[idx - 2] and clusters[idx] != clusters[idx - 1]
            )
            if switches >= 2 or ping_pong >= 1:
                issues.append(
                    ValidationIssue(
                        code="ROUTE_BACKTRACKING",
                        severity=Severity.MEDIUM,
                        day=day.day_number,
                        message=f"cluster switches={switches}, ping_pong={ping_pong}",
                    )
                )
        return issues


__all__ = ["BacktrackingConstraint"]
