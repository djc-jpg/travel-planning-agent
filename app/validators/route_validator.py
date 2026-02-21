"""Route quality validator for duplicate POIs and backtracking signals."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_route_quality(itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_global: set[str] = set()

    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        if not main:
            continue

        day_seen: set[str] = set()
        for item in main:
            if item.poi.id in day_seen:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_POI_DAY",
                        severity=Severity.HIGH,
                        day=day.day_number,
                        message=f"{item.poi.name} 在同一天被重复安排",
                        suggestions=["去重后补充同片区备选景点"],
                    )
                )
            day_seen.add(item.poi.id)

            if item.poi.id in seen_global:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_POI_GLOBAL",
                        severity=Severity.MEDIUM,
                        day=day.day_number,
                        message=f"{item.poi.name} 在多天重复出现",
                        suggestions=["将重复景点替换为同区域新景点"],
                    )
                )
            seen_global.add(item.poi.id)

        clusters = [item.poi.cluster for item in main if item.poi.cluster]
        switches = 0
        for idx in range(1, len(clusters)):
            if clusters[idx] != clusters[idx - 1]:
                switches += 1
        if len(main) >= 3 and switches >= 2:
            issues.append(
                ValidationIssue(
                    code="ROUTE_BACKTRACKING",
                    severity=Severity.MEDIUM,
                    day=day.day_number,
                    message=f"日内片区切换较多（{switches}次）",
                    suggestions=["按地理片区重排，优先同片区连走"],
                )
            )

    return issues

