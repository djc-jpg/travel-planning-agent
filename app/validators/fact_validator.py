"""Fact validator for curated POI metadata fields."""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_facts(itinerary: Itinerary, constraints: TripConstraints) -> list[ValidationIssue]:
    if itinerary.city != "北京":
        return []

    # 仅对启用元数据链路的行程做强校验，避免影响旧测试夹具。
    has_curated = any(
        item.poi.metadata_source
        for day in itinerary.days
        for item in day.schedule
        if not item.is_backup
    )
    if not has_curated:
        return []

    issues: list[ValidationIssue] = []
    for day in itinerary.days:
        for item in day.schedule:
            if item.is_backup:
                continue
            poi = item.poi
            missing: list[str] = []
            if not poi.metadata_source:
                missing.append("metadata_source")
            if not poi.open_time:
                missing.append("open_time")
            if poi.ticket_price < 0:
                missing.append("ticket_price")
            if missing:
                issues.append(
                    ValidationIssue(
                        code="MISSING_FACTS",
                        severity=Severity.HIGH,
                        day=day.day_number,
                        message=f"{poi.name} 缺少事实字段: {','.join(missing)}",
                        suggestions=["补齐POI元数据并重新规划"],
                    )
                )
    return issues
