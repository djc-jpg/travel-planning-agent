"""Daily schedule construction helpers."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Callable

from app.domain.models import POI, ScheduleItem, TimeSlot
from app.domain.planning.buffer import DAY_END_HOUR, DAY_MAX_MINUTES, DAY_START_HOUR, compute_buffer_minutes, exceeds_daily_limit
from app.domain.planning.cluster import cross_cluster_penalty_minutes

if TYPE_CHECKING:
    from app.planner.routing_provider import RoutingProvider

DistanceFn = Callable[[float, float, float, float], float]
TravelTimeFn = Callable[[float, str], float]
DEFAULT_DURATION_MINUTES = {"museum": 120.0, "temple": 60.0, "park": 90.0, "shopping": 90.0, "night_view": 60.0, "food_market": 90.0, "landmark": 60.0}
_CATEGORY_KEYWORDS = (
    ("museum", ("museum", "gallery", "history", "art")),
    ("temple", ("temple", "shrine", "church")),
    ("park", ("park", "garden", "nature")),
    ("shopping", ("shopping", "mall", "outlet", "bazaar")),
    ("night_view", ("night", "sunset", "viewpoint", "observation")),
    ("food_market", ("food", "market", "snack", "street")),
    ("landmark", ("landmark", "tower", "square", "monument")),
)


def _to_hour(text: str) -> float:
    hh, mm = text.split(":")
    return int(hh) + int(mm) / 60.0


def _fmt_hour(value: float) -> str:
    hh = int(value)
    mm = int(round((value - hh) * 60))
    if mm == 60:
        hh += 1
        mm = 0
    return f"{hh:02d}:{mm:02d}"


def _parse_open_hours_range(open_time: str | None) -> tuple[float, float] | None:
    if not open_time:
        return None
    segment = str(open_time).strip().split(" ")[0]
    if "-" not in segment:
        return None
    start, end = segment.split("-", 1)
    try:
        return _to_hour(start), _to_hour(end)
    except Exception:
        return None


def infer_duration_category(poi: POI) -> str:
    text = " ".join([poi.name, *poi.themes]).lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return category
    return "park"


def resolve_duration_minutes(poi: POI) -> float:
    if float(poi.duration_hours or 0.0) > 0.0:
        return float(poi.duration_hours) * 60.0
    return DEFAULT_DURATION_MINUTES.get(infer_duration_category(poi), 90.0)


def _slot_for_hour(hour: float) -> TimeSlot:
    if hour < 12.0:
        return TimeSlot.MORNING
    if hour < 13.5:
        return TimeSlot.LUNCH
    if hour < 17.0:
        return TimeSlot.AFTERNOON
    if hour < 19.0:
        return TimeSlot.DINNER
    return TimeSlot.EVENING


def _apply_lunch_window(hour: float, meal_windows: list[str]) -> tuple[float, float]:
    if hour < 12.0:
        return hour, 0.0
    lunch_start = max(12.0, min(hour, 13.2))
    lunch_end = lunch_start + 0.8
    meal_windows.append(f"{_fmt_hour(lunch_start)}-{_fmt_hour(lunch_end)}")
    return lunch_end, (lunch_end - lunch_start) * 60.0


def _compose_notes(
    poi: POI,
    *,
    crowd_level: str,
    buffer_minutes: float,
    cluster_id: str,
    routing_confidence: float,
) -> str:
    details: list[str] = [f"cluster={cluster_id}", f"buffer={int(buffer_minutes)}m"]
    details.append(f"routing_confidence={routing_confidence:.2f}")
    if poi.requires_reservation:
        details.append("reservation_required")
    if crowd_level in {"high", "very_high"}:
        details.append("avoid_peak_hours")
    if poi.closed_rules:
        details.append(f"closed_rules={poi.closed_rules}")
    return " | ".join(details)


def _compute_travel_minutes(
    *,
    last_poi: POI | None,
    poi: POI,
    plan_date: date,
    hour: float,
    transport_mode: str,
    distance_fn: DistanceFn,
    travel_time_fn: TravelTimeFn,
    provider: RoutingProvider | None,
    cluster_lookup: dict[str, str] | None,
) -> tuple[float, float]:
    if last_poi is None:
        return 0.0, 1.0
    if provider is not None:
        dep = datetime.combine(plan_date, time(hour=int(hour), minute=int((hour % 1) * 60)))
        travel = provider.get_travel_time(last_poi, poi, transport_mode, departure_time=dep)
        confidence = provider.get_confidence(last_poi, poi, transport_mode, departure_time=dep)
    else:
        dist = distance_fn(last_poi.lat, last_poi.lon, poi.lat, poi.lon)
        travel = travel_time_fn(dist, transport_mode)
        confidence = 0.62
    minutes = travel + cross_cluster_penalty_minutes(last_poi, poi, cluster_map=cluster_lookup)
    return minutes, confidence


def _adjust_for_open_hours(*, hour: float, elapsed_minutes: float, open_time: str | None) -> tuple[float, float] | None:
    open_range = _parse_open_hours_range(open_time)
    if not open_range:
        return hour, elapsed_minutes
    open_start, open_end = open_range
    if hour < open_start:
        elapsed_minutes += (open_start - hour) * 60.0
        hour = open_start
    if hour >= open_end - 0.2:
        return None
    return hour, elapsed_minutes


def _fit_schedule_item(
    *,
    poi: POI,
    hour: float,
    elapsed_minutes: float,
    travel_minutes: float,
    routing_confidence: float,
    meal_windows: list[str],
    lunch_added: bool,
    crowd_level: str,
    holiday_hint: str | None,
    cluster_lookup: dict[str, str] | None,
    items: list[ScheduleItem],
    day_max_minutes: float,
) -> tuple[ScheduleItem, float, float, bool] | None:
    stay_minutes = resolve_duration_minutes(poi)
    buffer_minutes = compute_buffer_minutes(poi, stay_minutes_value=stay_minutes, crowd_level=crowd_level, holiday_hint=holiday_hint)
    candidate_hour = hour + (travel_minutes + buffer_minutes) / 60.0
    candidate_elapsed = elapsed_minutes + travel_minutes + buffer_minutes
    adjusted = _adjust_for_open_hours(hour=candidate_hour, elapsed_minutes=candidate_elapsed, open_time=poi.open_time or poi.open_hours)
    if adjusted is None:
        return None
    candidate_hour, candidate_elapsed = adjusted
    if not lunch_added:
        candidate_hour, lunch_minutes = _apply_lunch_window(candidate_hour, meal_windows)
        candidate_elapsed += lunch_minutes
        lunch_added = lunch_minutes > 0
    if items and items[-1].end_time:
        candidate_hour = max(candidate_hour, _to_hour(items[-1].end_time))
    end_hour = candidate_hour + stay_minutes / 60.0
    projected = candidate_elapsed + stay_minutes
    if end_hour > DAY_END_HOUR or exceeds_daily_limit(projected, max_minutes=day_max_minutes):
        return None
    cluster_id = (cluster_lookup or {}).get(poi.id, "geo:0")
    item = ScheduleItem(
        poi=poi,
        time_slot=_slot_for_hour(candidate_hour),
        start_time=_fmt_hour(candidate_hour),
        end_time=_fmt_hour(end_hour),
        travel_minutes=round(travel_minutes, 1),
        buffer_minutes=round(buffer_minutes, 1),
        notes=_compose_notes(
            poi,
            crowd_level=crowd_level,
            buffer_minutes=buffer_minutes,
            cluster_id=cluster_id,
            routing_confidence=routing_confidence,
        ),
    )
    return item, end_hour, projected, lunch_added


def assign_time_slots(
    pois: list[POI],
    *,
    plan_date: date,
    transport_mode: str,
    distance_fn: DistanceFn,
    travel_time_fn: TravelTimeFn,
    routing_provider: RoutingProvider | None = None,
    crowd_level: str = "normal",
    holiday_hint: str | None = None,
    cluster_lookup: dict[str, str] | None = None,
    day_max_minutes: float = DAY_MAX_MINUTES,
) -> tuple[list[ScheduleItem], list[str]]:
    items: list[ScheduleItem] = []
    meal_windows: list[str] = []
    hour = DAY_START_HOUR
    elapsed_minutes = 0.0
    lunch_added = False
    last_poi: POI | None = None
    provider = routing_provider
    for poi in pois:
        travel_minutes, routing_confidence = _compute_travel_minutes(
            last_poi=last_poi,
            poi=poi,
            plan_date=plan_date,
            hour=hour,
            transport_mode=transport_mode,
            distance_fn=distance_fn,
            travel_time_fn=travel_time_fn,
            provider=provider,
            cluster_lookup=cluster_lookup,
        )
        fitted = _fit_schedule_item(
            poi=poi,
            hour=hour,
            elapsed_minutes=elapsed_minutes,
            travel_minutes=travel_minutes,
            routing_confidence=routing_confidence,
            meal_windows=meal_windows,
            lunch_added=lunch_added,
            crowd_level=crowd_level,
            holiday_hint=holiday_hint,
            cluster_lookup=cluster_lookup,
            items=items,
            day_max_minutes=day_max_minutes,
        )
        if fitted is None:
            continue
        item, hour, elapsed_minutes, lunch_added = fitted
        items.append(item)
        last_poi = poi
    if not meal_windows:
        meal_windows.append("12:00-13:00")
    return items, meal_windows


def pick_backup(poi_pool: list[POI], day_pois: list[POI]) -> list[ScheduleItem]:
    used_ids = {poi.id for poi in day_pois}
    same_cluster = {poi.cluster for poi in day_pois if poi.cluster}
    backup_poi: POI | None = None
    for poi in poi_pool:
        if poi.id in used_ids:
            continue
        if same_cluster and poi.cluster in same_cluster:
            backup_poi = poi
            break
    if backup_poi is None:
        for poi in poi_pool:
            if poi.id not in used_ids:
                backup_poi = poi
                break
    if backup_poi is None:
        return []
    return [ScheduleItem(poi=backup_poi, time_slot=TimeSlot.AFTERNOON, notes="backup_option", is_backup=True)]


__all__ = ["DAY_END_HOUR", "DAY_MAX_MINUTES", "DistanceFn", "TravelTimeFn", "assign_time_slots", "infer_duration_category", "pick_backup", "resolve_duration_minutes"]
