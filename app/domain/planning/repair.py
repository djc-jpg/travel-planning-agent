"""Lightweight repair engine for planning constraints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.models import Itinerary, ScheduleItem, TripConstraints, UserProfile, ValidationIssue
from app.domain.planning.constraints.engine import ConstraintEngine
from app.domain.planning.ordering import optimize_daily_order
from app.domain.planning.scheduling import assign_time_slots
from app.planner.budget import apply_realistic_budget
from app.planner.distance import estimate_distance, estimate_travel_time


@dataclass
class RepairResult:
    itinerary: Itinerary
    actions: list[str]
    remaining_violations: list[ValidationIssue]


def _main_items(day) -> list[ScheduleItem]:
    return [item for item in day.schedule if not item.is_backup]


def _cluster_lookup(day) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in _main_items(day):
        result[item.poi.id] = item.poi.cluster or "geo:0"
    return result


def _reflow_day(day, constraints: TripConstraints) -> None:
    mains = _main_items(day)
    if not mains:
        return
    ordered = optimize_daily_order([item.poi for item in mains], distance_fn=estimate_distance)
    backups = [item for item in day.schedule if item.is_backup]
    rescheduled, meals = assign_time_slots(
        ordered,
        plan_date=day.date or date.today(),
        transport_mode=constraints.transport_mode.value,
        distance_fn=estimate_distance,
        travel_time_fn=estimate_travel_time,
        cluster_lookup=_cluster_lookup(day),
        holiday_hint=constraints.holiday_hint,
    )
    if rescheduled:
        day.schedule = rescheduled + backups
        day.meal_windows = meals or day.meal_windows
        day.total_travel_minutes = round(sum(item.travel_minutes for item in rescheduled), 1)


def _remove_overload_poi(day, *, over_budget: bool) -> str | None:
    mains = _main_items(day)
    if len(mains) <= 1:
        return None
    target = max(mains, key=lambda item: item.poi.cost if over_budget else item.poi.duration_hours)
    day.schedule.remove(target)
    return f"remove_poi:{target.poi.name}"


def _replace_with_backup(day) -> str | None:
    mains = _main_items(day)
    if not mains or not day.backups:
        return None
    target = mains[-1]
    existing_ids = {item.poi.id for item in mains}
    backup = next(
        (
            item
            for item in day.backups
            if item.poi.id not in existing_ids or item.poi.id == target.poi.id
        ),
        None,
    )
    if backup is None:
        return None
    replaced = ScheduleItem(
        poi=backup.poi,
        time_slot=target.time_slot,
        start_time=target.start_time,
        end_time=target.end_time,
        travel_minutes=target.travel_minutes,
        buffer_minutes=target.buffer_minutes,
        notes=f"{target.notes} | replaced_with_backup",
        is_backup=False,
    )
    day.schedule.remove(target)
    day.schedule.append(replaced)
    return f"replace_with_backup:{target.poi.name}->{backup.poi.name}"


def _increase_buffers(day) -> str | None:
    changed = False
    for item in _main_items(day):
        next_value = min(45.0, float(item.buffer_minutes) + 5.0)
        if next_value > float(item.buffer_minutes):
            item.buffer_minutes = next_value
            changed = True
    return "increase_buffer:+5m" if changed else None


def _budget_limit(constraints: TripConstraints) -> float:
    if constraints.total_budget:
        return float(constraints.total_budget)
    if constraints.budget_per_day:
        return float(constraints.budget_per_day) * float(constraints.days)
    return 0.0


def _trim_global_budget(
    itinerary: Itinerary,
    constraints: TripConstraints,
    *,
    profile: UserProfile,
) -> list[str]:
    limit = _budget_limit(constraints)
    if limit <= 0:
        return []

    actions: list[str] = []
    max_steps = max(1, len(itinerary.days) * 2)
    for _ in range(max_steps):
        apply_realistic_budget(itinerary, constraints, profile)
        if itinerary.total_cost <= limit + 1e-6:
            break

        best_day = None
        best_item = None
        best_cost = 0.0
        for day in itinerary.days:
            mains = _main_items(day)
            if len(mains) <= 1:
                continue
            for item in mains:
                cost = max(0.0, float(item.poi.cost))
                if cost > best_cost:
                    best_cost = cost
                    best_day = day
                    best_item = item

        if best_day is None or best_item is None:
            break

        best_day.schedule.remove(best_item)
        actions.append(f"day{best_day.day_number}:remove_poi:{best_item.poi.name}:budget_trim")
        _reflow_day(best_day, constraints)

    return actions


def _promote_unique_backup(day, seen_ids: set[str]) -> str | None:
    day_ids = {item.poi.id for item in _main_items(day)}
    for backup in day.backups:
        poi_id = backup.poi.id
        if poi_id in seen_ids or poi_id in day_ids:
            continue
        promoted = ScheduleItem(
            poi=backup.poi,
            time_slot=backup.time_slot,
            start_time=backup.start_time,
            end_time=backup.end_time,
            travel_minutes=backup.travel_minutes,
            buffer_minutes=backup.buffer_minutes,
            notes=f"{backup.notes} | promoted_from_backup",
            is_backup=False,
        )
        day.schedule.append(promoted)
        return f"promote_backup:{backup.poi.name}"
    return None


def _dedupe_main_schedule(itinerary: Itinerary, constraints: TripConstraints) -> list[str]:
    actions: list[str] = []
    seen_ids: set[str] = set()

    for day in itinerary.days:
        mains = _main_items(day)
        if not mains:
            continue

        keep: list[ScheduleItem] = []
        day_changed = False
        for item in mains:
            poi_id = item.poi.id
            if poi_id in seen_ids:
                day_changed = True
                actions.append(f"day{day.day_number}:drop_duplicate:{item.poi.name}")
                continue
            seen_ids.add(poi_id)
            keep.append(item)

        if not day_changed:
            continue

        backups = [item for item in day.schedule if item.is_backup]
        day.schedule = keep + backups
        promoted = _promote_unique_backup(day, seen_ids)
        if promoted:
            actions.append(f"day{day.day_number}:{promoted}")
        _reflow_day(day, constraints)
        for item in _main_items(day):
            seen_ids.add(item.poi.id)

    return actions


class RepairEngine:
    """Single-pass repair: mutate day-level schedule, then revalidate once."""

    def __init__(self, constraint_engine: ConstraintEngine) -> None:
        self._constraint_engine = constraint_engine

    def repair(
        self,
        itinerary: Itinerary,
        constraints: TripConstraints,
        *,
        profile: UserProfile | None = None,
    ) -> RepairResult:
        working = itinerary.model_copy(deep=True)
        violations = self._constraint_engine.evaluate(working, constraints)
        if not violations:
            dedupe_actions = _dedupe_main_schedule(working, constraints)
            if not dedupe_actions:
                return RepairResult(itinerary=working, actions=[], remaining_violations=[])
            apply_realistic_budget(working, constraints, profile or UserProfile())
            remaining = self._constraint_engine.evaluate(working, constraints)
            return RepairResult(itinerary=working, actions=dedupe_actions, remaining_violations=remaining)

        actions: list[str] = []
        for issue in violations:
            if issue.day is None:
                if issue.code == "OVER_BUDGET":
                    actions.extend(
                        _trim_global_budget(
                            working,
                            constraints,
                            profile=profile or UserProfile(),
                        )
                    )
                continue
            day = next((row for row in working.days if row.day_number == issue.day), None)
            if day is None:
                continue
            action = self._apply_issue(day, issue)
            if action:
                actions.append(f"day{day.day_number}:{action}")
                _reflow_day(day, constraints)

        dedupe_actions = _dedupe_main_schedule(working, constraints)
        actions.extend(dedupe_actions)
        apply_realistic_budget(working, constraints, profile or UserProfile())
        remaining = self._constraint_engine.evaluate(working, constraints)
        return RepairResult(itinerary=working, actions=actions, remaining_violations=remaining)

    def _apply_issue(self, day, issue: ValidationIssue) -> str | None:
        if issue.code in {"TIME_CONFLICT", "ROUTE_BACKTRACKING"}:
            return "reorder_day"
        if issue.code in {"DAY_OVERLOAD", "INTENSITY_OVERLOAD"}:
            return _remove_overload_poi(day, over_budget=False)
        if issue.code == "OVER_BUDGET":
            return _remove_overload_poi(day, over_budget=True)
        if issue.code in {"OPEN_HOURS_VIOLATION", "RESERVATION_RISK"}:
            return _replace_with_backup(day) or _increase_buffers(day)
        return None


__all__ = ["RepairEngine", "RepairResult"]
