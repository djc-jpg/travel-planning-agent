"""Buffer and minute-budget helpers for daily feasibility."""

from __future__ import annotations

from app.domain.models import POI

DAY_START_HOUR = 8.5
DAY_END_HOUR = 20.0
DAY_MAX_MINUTES = int((DAY_END_HOUR - DAY_START_HOUR) * 60)


def stay_minutes(poi: POI, *, fallback_minutes: float) -> float:
    duration_hours = float(poi.duration_hours or 0.0)
    if duration_hours > 0:
        return duration_hours * 60.0
    return fallback_minutes


def buffer_ratio(crowd_level: str, holiday_hint: str | None) -> float:
    ratio = 0.10
    if crowd_level == "high":
        ratio = 0.12
    if crowd_level == "very_high":
        ratio = 0.15
    if holiday_hint:
        ratio = max(ratio, 0.15)
    return ratio


def compute_buffer_minutes(
    poi: POI,
    *,
    stay_minutes_value: float,
    crowd_level: str,
    holiday_hint: str | None,
) -> float:
    base = stay_minutes_value * buffer_ratio(crowd_level, holiday_hint)
    floor = 10.0
    if crowd_level == "high":
        floor = 20.0
    if crowd_level == "very_high" or holiday_hint:
        floor = 30.0
    if poi.requires_reservation or poi.reservation_required:
        base += 8.0
    return round(max(floor, min(45.0, base)), 1)


def exceeds_daily_limit(total_minutes: float, *, max_minutes: float = DAY_MAX_MINUTES) -> bool:
    return total_minutes - max_minutes > 1e-6


__all__ = [
    "DAY_END_HOUR",
    "DAY_MAX_MINUTES",
    "DAY_START_HOUR",
    "compute_buffer_minutes",
    "exceeds_daily_limit",
    "stay_minutes",
]
