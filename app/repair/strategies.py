"""Repair strategies for deterministic issue handling."""

from __future__ import annotations

from app.domain.constants import PACE_MAX
from app.domain.models import Itinerary, ItineraryDay, POI, ScheduleItem, TimeSlot, TripConstraints, UserProfile
from app.planner.budget import apply_realistic_budget


def _recalc_cost(itinerary: Itinerary, constraints: TripConstraints) -> None:
    for day in itinerary.days:
        main = [s for s in day.schedule if not s.is_backup]
        if main:
            main[0].travel_minutes = 0.0
        day.total_travel_minutes = round(sum(s.travel_minutes for s in main), 1)
    apply_realistic_budget(itinerary, constraints, UserProfile())


def repair_over_time(itinerary: Itinerary, day_number: int | None, constraints: TripConstraints) -> Itinerary:
    for day in itinerary.days:
        if day_number and day.day_number != day_number:
            continue
        main = [s for s in day.schedule if not s.is_backup]
        if len(main) > 1:
            longest = max(main, key=lambda s: s.poi.duration_hours)
            day.schedule.remove(longest)
    _recalc_cost(itinerary, constraints)
    return itinerary


def repair_too_much_travel(
    itinerary: Itinerary, day_number: int | None, constraints: TripConstraints
) -> Itinerary:
    for day in itinerary.days:
        if day_number and day.day_number != day_number:
            continue
        main = [s for s in day.schedule if not s.is_backup]
        if len(main) > 1:
            farthest = max(main, key=lambda s: s.travel_minutes)
            day.schedule.remove(farthest)
    _recalc_cost(itinerary, constraints)
    return itinerary


def repair_over_budget(itinerary: Itinerary, day_number: int | None, constraints: TripConstraints) -> Itinerary:
    all_items: list[tuple[ItineraryDay, ScheduleItem]] = []
    for day in itinerary.days:
        for item in [s for s in day.schedule if not s.is_backup]:
            all_items.append((day, item))
    if not all_items:
        return itinerary

    target_day, target_item = max(all_items, key=lambda x: x[1].poi.cost)
    if target_item.poi.cost > 0:
        target_day.schedule.remove(target_item)
        itinerary.assumptions.append(
            f"Removed {target_item.poi.name} to reduce cost (cost={target_item.poi.cost:.0f})"
        )
    _recalc_cost(itinerary, constraints)
    return itinerary


def repair_pace_mismatch(
    itinerary: Itinerary, day_number: int | None, constraints: TripConstraints
) -> Itinerary:
    max_poi = PACE_MAX.get(constraints.pace, 3)
    for day in itinerary.days:
        if day_number and day.day_number != day_number:
            continue
        main = [s for s in day.schedule if not s.is_backup]
        while len(main) > max_poi:
            removed = main.pop()
            day.schedule.remove(removed)
    return itinerary


def repair_missing_backup(
    itinerary: Itinerary, day_number: int | None, constraints: TripConstraints
) -> Itinerary:
    for day in itinerary.days:
        if day_number and day.day_number != day_number:
            continue
        has_backup = any(s.is_backup for s in day.schedule) or len(day.backups) > 0
        if not has_backup:
            backup_poi = POI(
                id=f"backup_day{day.day_number}",
                name="Indoor backup option",
                city=itinerary.city,
                themes=["indoor"],
                duration_hours=2.0,
                cost=0.0,
                indoor=True,
            )
            day.backups.append(
                ScheduleItem(
                    poi=backup_poi,
                    time_slot=TimeSlot.AFTERNOON,
                    notes="Backup for rain or crowd",
                    is_backup=True,
                )
            )
    return itinerary


REPAIR_DISPATCH = {
    "OVER_TIME": repair_over_time,
    "TOO_MUCH_TRAVEL": repair_too_much_travel,
    "OVER_BUDGET": repair_over_budget,
    "PACE_MISMATCH": repair_pace_mismatch,
    "MISSING_BACKUP": repair_missing_backup,
}

