"""Shared helpers for planning constraints."""

from __future__ import annotations

from app.domain.models import ScheduleItem


def parse_hhmm(value: str | None) -> int | None:
    if not value:
        return None
    text = str(value).strip()
    if ":" not in text:
        return None
    hh, mm = text.split(":", 1)
    try:
        return int(hh) * 60 + int(mm)
    except ValueError:
        return None


def parse_open_hours(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    text = str(value).strip().split(" ")[0]
    if "-" not in text:
        return None
    left, right = text.split("-", 1)
    start = parse_hhmm(left)
    end = parse_hhmm(right)
    if start is None or end is None:
        return None
    return start, end


def item_duration_minutes(item: ScheduleItem) -> float:
    start = parse_hhmm(item.start_time)
    end = parse_hhmm(item.end_time)
    if start is not None and end is not None and end > start:
        return float(end - start)
    return float(item.poi.duration_hours or 0.0) * 60.0


__all__ = ["item_duration_minutes", "parse_hhmm", "parse_open_hours"]
