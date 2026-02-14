"""Deterministic itinerary planner."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from app.domain.constants import PACE_POI_COUNT, TRANSPORT_COST_PER_SEGMENT
from app.domain.models import (
    Itinerary,
    ItineraryDay,
    POI,
    ScheduleItem,
    TimeSlot,
    TripConstraints,
    UserProfile,
)
from app.planner.distance import estimate_distance, estimate_travel_time

DistanceFn = Callable[[float, float, float, float], float]
TravelTimeFn = Callable[[float, str], float]


def _nearest_neighbor_sort(
    pois: list[POI],
    *,
    distance_fn: DistanceFn,
    start_lat: float = 0,
    start_lon: float = 0,
) -> list[POI]:
    if len(pois) <= 1:
        return list(pois)
    remaining = list(pois)
    sorted_list: list[POI] = []
    cur_lat, cur_lon = start_lat or remaining[0].lat, start_lon or remaining[0].lon

    while remaining:
        nearest = min(remaining, key=lambda p: distance_fn(cur_lat, cur_lon, p.lat, p.lon))
        remaining.remove(nearest)
        sorted_list.append(nearest)
        cur_lat, cur_lon = nearest.lat, nearest.lon

    return sorted_list


def _assign_time_slots(
    pois: list[POI],
    *,
    transport_mode: str,
    distance_fn: DistanceFn,
    travel_time_fn: TravelTimeFn,
) -> list[ScheduleItem]:
    items: list[ScheduleItem] = []
    hour = 9.0

    for i, poi in enumerate(pois):
        travel_min = 0.0
        if i > 0:
            prev = pois[i - 1]
            dist = distance_fn(prev.lat, prev.lon, poi.lat, poi.lon)
            travel_min = travel_time_fn(dist, transport_mode)
            hour += travel_min / 60

        if hour < 12:
            slot = TimeSlot.MORNING
        elif hour < 13.5:
            slot = TimeSlot.LUNCH
        elif hour < 17:
            slot = TimeSlot.AFTERNOON
        elif hour < 19:
            slot = TimeSlot.DINNER
        else:
            slot = TimeSlot.EVENING

        start_h, start_m = int(hour), int((hour % 1) * 60)
        end_hour = hour + poi.duration_hours
        end_h, end_m = int(end_hour), int((end_hour % 1) * 60)

        items.append(
            ScheduleItem(
                poi=poi,
                time_slot=slot,
                start_time=f"{start_h:02d}:{start_m:02d}",
                end_time=f"{end_h:02d}:{end_m:02d}",
                travel_minutes=round(travel_min, 1),
            )
        )
        hour = end_hour

    return items


def _pick_backup(poi_pool: list[POI], day_pois: list[POI]) -> list[ScheduleItem]:
    used_ids = {p.id for p in day_pois}
    indoor_candidates = [p for p in poi_pool if p.indoor and p.id not in used_ids]
    backup_poi = indoor_candidates[0] if indoor_candidates else None
    if backup_poi is None:
        remaining = [p for p in poi_pool if p.id not in used_ids]
        backup_poi = remaining[0] if remaining else None
    if backup_poi is None:
        return []
    return [
        ScheduleItem(
            poi=backup_poi,
            time_slot=TimeSlot.AFTERNOON,
            notes="Backup plan for rain or crowds",
            is_backup=True,
        )
    ]


def generate_itinerary(
    constraints: TripConstraints,
    profile: UserProfile,
    poi_candidates: list[POI],
    *,
    transport_mode: str | None = None,
    weather_data: dict | None = None,
    calendar_data: dict | None = None,
    distance_fn: DistanceFn = estimate_distance,
    travel_time_fn: TravelTimeFn = estimate_travel_time,
) -> Itinerary:
    mode = transport_mode or constraints.transport_mode.value
    daily_count = PACE_POI_COUNT.get(constraints.pace, 3)
    start_date = constraints.date_start or date.today()

    day_weather_map: dict[int, dict] = {}
    day_calendar_map: dict[int, dict] = {}

    if weather_data and isinstance(weather_data, dict):
        for i, fc in enumerate(weather_data.get("forecasts", [])):
            day_weather_map[i + 1] = fc
    if calendar_data and isinstance(calendar_data, dict):
        for i, ci in enumerate(calendar_data.get("days", [])):
            day_calendar_map[i + 1] = ci

    seen_ids: set[str] = set()
    unique: list[POI] = []
    for p in poi_candidates:
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            unique.append(p)

    if profile.themes:
        theme_set = set(profile.themes)
        unique.sort(key=lambda p: len(set(p.themes) & theme_set), reverse=True)

    days: list[ItineraryDay] = []
    assumptions: list[str] = []
    global_used_ids: set[str] = set()
    idx = 0

    for d in range(1, constraints.days + 1):
        day_pois = unique[idx : idx + daily_count]
        idx += daily_count
        if not day_pois:
            remaining = [p for p in unique if p.id not in global_used_ids]
            day_pois = remaining[:daily_count]
            if not day_pois and unique:
                day_pois = unique[:daily_count]
                assumptions.append(f"Day {d} has repeated POIs due limited candidates")

        weather_info = day_weather_map.get(d)
        is_rainy = False
        if weather_info:
            is_rainy = not weather_info.get("is_outdoor_friendly", True)
            if is_rainy:
                indoor = [p for p in day_pois if p.indoor]
                outdoor = [p for p in day_pois if not p.indoor]
                used_ids = {p.id for p in day_pois}
                extra_indoor = [
                    p for p in unique if p.indoor and p.id not in used_ids and p.id not in global_used_ids
                ]
                if extra_indoor and len(indoor) < daily_count:
                    replace_count = min(len(extra_indoor), len(outdoor))
                    indoor.extend(extra_indoor[:replace_count])
                    outdoor = outdoor[replace_count:]
                    assumptions.append(f"Day {d} adjusted for rainy weather")
                day_pois = indoor + outdoor

        for p in day_pois:
            global_used_ids.add(p.id)

        sorted_pois = _nearest_neighbor_sort(day_pois, distance_fn=distance_fn)
        schedule = _assign_time_slots(
            sorted_pois,
            transport_mode=mode,
            distance_fn=distance_fn,
            travel_time_fn=travel_time_fn,
        )

        day_summary_parts: list[str] = []
        if weather_info:
            cond = weather_info.get("condition", "")
            temp_h = weather_info.get("temp_high", "")
            temp_l = weather_info.get("temp_low", "")
            day_summary_parts.append(f"天气：{cond} {temp_l}~{temp_h}℃")
            if is_rainy:
                day_summary_parts.append("建议携带雨具")

        cal_info = day_calendar_map.get(d)
        if cal_info:
            holiday = cal_info.get("holiday_name", "")
            crowd = cal_info.get("crowd_level", "normal")
            if holiday:
                day_summary_parts.append(f"节假日：{holiday}")
            if crowd in ("high", "very_high"):
                day_summary_parts.append("⚠ 预计人流量较高，建议错峰出行")
                assumptions.append(f"第{d}天人流量{crowd}")

        backups = _pick_backup(unique, day_pois)
        if is_rainy and backups:
            for b in backups:
                b.notes = "Indoor backup plan for rainy weather"

        total_travel = sum(s.travel_minutes for s in schedule)
        main_items = [s for s in schedule if not s.is_backup]
        day_poi_cost = sum(s.poi.cost for s in main_items)
        segments = max(0, len(main_items) - 1)
        transport_cost = segments * TRANSPORT_COST_PER_SEGMENT.get(mode, 5.0)
        day_cost = round(day_poi_cost + transport_cost, 2)

        days.append(
            ItineraryDay(
                day_number=d,
                date=start_date + timedelta(days=d - 1),
                schedule=schedule,
                backups=backups,
                total_travel_minutes=round(total_travel, 1),
                day_summary=" | ".join(day_summary_parts) if day_summary_parts else "",
                estimated_cost=day_cost,
            )
        )

    city = constraints.city or ""
    if not city and poi_candidates:
        city = poi_candidates[0].city
    total_cost = round(sum(d.estimated_cost for d in days), 2)

    return Itinerary(city=city, days=days, assumptions=assumptions, total_cost=total_cost)
